from __future__ import annotations

import html
import re
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import requests
from lxml import etree, html as lxml_html

from .utils import clean_whitespace, normalize_doi, split_name

DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.I)
PMID_RE = re.compile(r"\bPMID[:\s]*([0-9]{5,9})\b", re.I)
ARXIV_RE = re.compile(r"(?:arxiv[:/\s]+)(\d{4}\.\d{4,5}(?:v\d+)?)\b", re.I)
ISBN_RE = re.compile(r"\b(?:97[89][- ]?)?\d(?:[- ]?\d){8,16}\b")
ISBN_CONTEXT_RE = re.compile(r"\bISBN(?:-1[03])?\b|international standard book number", re.I)
BOOK_TAG_RE = re.compile(r"\[(?:M|BOOK)\]", re.I)
URL_RE = re.compile(r"https?://[^\s>]+", re.I)
TITLE_NORMALIZER_RE = re.compile(r"[^a-z0-9]+")
REFERENCE_NUMBER_RE = re.compile(r"^\s*\[\d+\]\s*")
REFERENCE_TAG_RE = re.compile(r"\[(?:[A-Z]|[A-Z]{1,3}/[A-Z]{1,3})+\]", re.I)
HIGH_CONFIDENCE_THRESHOLD = 1.15


@dataclass(slots=True)
class MetadataIdentifiers:
    doi: str | None = None
    pmid: str | None = None
    arxiv_id: str | None = None
    isbn: str | None = None
    url: str | None = None


@dataclass(slots=True)
class MetadataResolution:
    source: str
    score: float
    item: dict[str, Any]
    identifiers: MetadataIdentifiers = field(default_factory=MetadataIdentifiers)
    notes: list[str] = field(default_factory=list)


def normalize_title(value: str) -> str:
    return TITLE_NORMALIZER_RE.sub("", value.lower())


def strip_markup(value: str) -> str:
    text = re.sub(r"<[^>]+>", "", html.unescape(value or ""))
    text = re.sub(r":(?=[A-Za-z])", ": ", text)
    return clean_whitespace(text)


def _reference_tokens(value: str | None) -> set[str]:
    return set(re.findall(r"[a-z0-9]{2,}", clean_whitespace(value).lower()))


def _token_overlap(query: str | None, reference: str | None) -> float:
    query_tokens = _reference_tokens(query)
    reference_tokens = _reference_tokens(reference)
    if not query_tokens or not reference_tokens:
        return 0.0
    return len(query_tokens & reference_tokens) / len(query_tokens)


def _normalize_reference_query(raw_reference: str | None) -> str:
    value = clean_whitespace(raw_reference)
    if not value:
        return ""
    value = REFERENCE_NUMBER_RE.sub("", value)
    value = URL_RE.sub(" ", value)
    value = DOI_RE.sub(" ", value)
    value = PMID_RE.sub(" ", value)
    value = REFERENCE_TAG_RE.sub(" ", value)
    value = re.sub(r"\s+", " ", value)
    return value[:240].strip()


def _isbn10_is_valid(value: str) -> bool:
    if len(value) != 10:
        return False
    total = 0
    for index, char in enumerate(value[:9], start=1):
        if not char.isdigit():
            return False
        total += index * int(char)
    check = value[9]
    if check in {"X", "x"}:
        total += 100
    elif check.isdigit():
        total += 10 * int(check)
    else:
        return False
    return total % 11 == 0


def _isbn13_is_valid(value: str) -> bool:
    if len(value) != 13 or not value.isdigit():
        return False
    total = 0
    for index, char in enumerate(value[:12]):
        total += int(char) * (1 if index % 2 == 0 else 3)
    check = (10 - (total % 10)) % 10
    return check == int(value[12])


def _extract_isbn(raw_reference: str) -> str | None:
    for match in ISBN_RE.finditer(raw_reference):
        digits = re.sub(r"[^0-9Xx]", "", match.group(0)).upper()
        if len(digits) == 10:
            valid = _isbn10_is_valid(digits)
        elif len(digits) == 13:
            valid = _isbn13_is_valid(digits)
        else:
            valid = False
        if not valid:
            continue

        window = raw_reference[max(0, match.start() - 48) : min(len(raw_reference), match.end() + 48)]
        if ISBN_CONTEXT_RE.search(window) or BOOK_TAG_RE.search(raw_reference):
            return digits
    return None


def _extract_title_signal(raw_reference: str | None) -> str:
    value = clean_whitespace(raw_reference)
    if not value:
        return ""
    value = REFERENCE_NUMBER_RE.sub("", value)
    value = URL_RE.sub(" ", value)
    value = DOI_RE.sub(" ", value)
    tag_match = REFERENCE_TAG_RE.search(value)
    if tag_match:
        left = value[: tag_match.start()]
    else:
        left = value.split("//", 1)[0]
    left = REFERENCE_TAG_RE.sub(" ", left)
    segments = [clean_whitespace(seg) for seg in re.split(r"\.\s+", left) if clean_whitespace(seg)]
    if not segments:
        return ""
    candidates = [seg for seg in segments if len(re.findall(r"[A-Za-z]{2,}", seg)) >= 3]
    if not candidates:
        candidates = segments
    title = candidates[-1]
    title = re.sub(r"^[^A-Za-z0-9]+", "", title)
    return title[:220].strip(" .;,:")


def _structured_title(parsed) -> str:
    explicit_title = clean_whitespace(getattr(parsed, "title", ""))
    body = clean_whitespace(getattr(parsed, "body", "") or getattr(parsed, "raw", ""))
    if explicit_title and explicit_title != body:
        return explicit_title
    return _extract_title_signal(body)


def _raw_reference_score(parsed, title: str, year: str | int | None, authors: list[str], container: str = "") -> float:
    raw_reference = clean_whitespace(getattr(parsed, "body", "") or getattr(parsed, "raw", ""))
    if not raw_reference:
        return 0.0

    score = 0.0
    if title:
        score += 0.75 * _token_overlap(title, raw_reference)
    if container:
        score += 0.2 * _token_overlap(container, raw_reference)
    if year and str(year) in raw_reference:
        score += 0.2

    if authors:
        raw_tokens = _reference_tokens(raw_reference)
        author_tokens = []
        for author in authors[:4]:
            parts = re.findall(r"[A-Za-z]{2,}", clean_whitespace(author).lower())
            if parts:
                author_tokens.append(parts[-1])
        if author_tokens:
            matches = sum(1 for token in author_tokens if token in raw_tokens)
            score += 0.25 * (matches / len(author_tokens))
    return score


def extract_identifiers(raw_reference: str) -> MetadataIdentifiers:
    doi_match = DOI_RE.search(raw_reference)
    pmid_match = PMID_RE.search(raw_reference)
    arxiv_match = ARXIV_RE.search(raw_reference)
    url_match = URL_RE.search(raw_reference)

    url = url_match.group(0).rstrip(".,;") if url_match else None
    doi = normalize_doi(doi_match.group(0)) if doi_match else None
    pmid = pmid_match.group(1) if pmid_match else None
    arxiv_id = None
    if arxiv_match:
        arxiv_id = (arxiv_match.group(1) or arxiv_match.group(2) or "").strip()
    isbn = _extract_isbn(raw_reference)

    if url and not doi:
        parsed = urlparse(url)
        if parsed.netloc.endswith("doi.org"):
            doi = normalize_doi(parsed.path.lstrip("/"))
        elif parsed.netloc.endswith("arxiv.org"):
            path = parsed.path.strip("/")
            if path.startswith("abs/"):
                arxiv_id = path.split("/", 1)[1]

    return MetadataIdentifiers(doi=doi or None, pmid=pmid, arxiv_id=arxiv_id or None, isbn=isbn, url=url)


def _build_creators(author_names: list[str]) -> list[dict[str, str]]:
    creators = []
    for name in author_names:
        name = clean_whitespace(name)
        if not name:
            continue
        first_name, last_name = split_name(name)
        if last_name:
            creators.append({"creatorType": "author", "firstName": first_name, "lastName": last_name})
        else:
            creators.append({"creatorType": "author", "name": name})
    return creators


def _first_author_last_name(creators: list[dict[str, Any]]) -> str:
    if not creators:
        return ""
    first = creators[0]
    return (first.get("lastName") or first.get("name") or "").lower()


def _score_candidate(parsed, title: str, year: str | int | None, authors: list[str], container: str = "") -> float:
    score = _raw_reference_score(parsed, title, year, authors, container)
    structured_title = _structured_title(parsed)
    if title and structured_title:
        score += 0.7 * _ratio(normalize_title(structured_title), normalize_title(title))
    parsed_year = str(parsed.fields.get("date", "")).strip()
    if parsed_year and year and str(year) == parsed_year:
        score += 0.2
    parsed_first_author = _first_author_last_name(parsed.creators)
    if parsed_first_author and authors:
        first_author = clean_whitespace(authors[0]).lower()
        if parsed_first_author in first_author or first_author in parsed_first_author:
            score += 0.15
    expected_container = parsed.fields.get("publicationTitle") or parsed.fields.get("proceedingsTitle") or ""
    if expected_container and container:
        score += 0.1 * _ratio(normalize_title(expected_container), normalize_title(container))
    return score


def _search_query(parsed) -> str:
    normalized_raw = _normalize_reference_query(getattr(parsed, "body", "") or getattr(parsed, "raw", ""))
    if normalized_raw and not _structured_title(parsed):
        return normalized_raw

    pieces = []
    title = _structured_title(parsed)
    if title:
        pieces.append(title)
    elif normalized_raw:
        pieces.append(normalized_raw)
    first_author = _first_author_last_name(parsed.creators)
    if first_author:
        pieces.append(first_author)
    year = clean_whitespace(str(parsed.fields.get("date", "")))
    if year:
        pieces.append(year)
    return " ".join(piece for piece in pieces if piece)


def _normalize_item_type(item_type: str | None) -> str:
    if item_type in {"journalArticle", "conferencePaper", "preprint", "webpage", "book", "thesis", "report", "patent"}:
        return item_type
    return "unknown"


def _ratio(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    # Lightweight ratio without difflib dependency in this module
    left_tokens = {left[i : i + 3] for i in range(max(len(left) - 2, 1))}
    right_tokens = {right[i : i + 3] for i in range(max(len(right) - 2, 1))}
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


class MetadataResolver:
    def __init__(self, mailto: str = "yuqing@example.com") -> None:
        self.mailto = mailto
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "zotero-word-bridge/0.2"})

    def _get(self, url: str, *, timeout: int = 20, **kwargs):
        last_error = None
        for attempt in range(4):
            try:
                response = self.session.get(url, timeout=timeout, **kwargs)
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < 3:
                        retry_after = clean_whitespace(response.headers.get("Retry-After", ""))
                        delay = float(retry_after) if retry_after.isdigit() else 1.5 * (attempt + 1)
                        time.sleep(delay)
                        continue
                response.raise_for_status()
                return response
            except requests.RequestException as exc:
                last_error = exc
                if attempt >= 3:
                    raise
                time.sleep(1.5 * (attempt + 1))
        if last_error:
            raise last_error

    def resolve(self, parsed) -> tuple[MetadataResolution | None, str | None]:
        parsed.item_type = _normalize_item_type(getattr(parsed, "item_type", None))
        ids = extract_identifiers(parsed.raw)
        attempted: list[str] = []
        candidates: list[MetadataResolution] = []

        if ids.doi:
            attempted.append(f"doi:{ids.doi}")
            try:
                resolution = self._crossref_by_doi(parsed, ids)
            except Exception:
                resolution = None
            if resolution:
                return resolution, None
        if ids.pmid:
            attempted.append(f"pmid:{ids.pmid}")
            try:
                resolution = self._pubmed_by_pmid(parsed, ids)
            except Exception:
                resolution = None
            if resolution:
                return resolution, None
        if ids.arxiv_id:
            attempted.append(f"arxiv:{ids.arxiv_id}")
            try:
                resolution = self._arxiv_by_id(parsed, ids)
            except Exception:
                resolution = None
            if resolution:
                return resolution, None
        if ids.isbn:
            attempted.append(f"isbn:{ids.isbn}")
            try:
                resolution = self._openlibrary_by_isbn(parsed, ids)
            except Exception:
                resolution = None
            if resolution:
                return resolution, None
        if ids.url and not ids.doi and not ids.arxiv_id:
            attempted.append(f"url:{ids.url}")
            try:
                resolution = self._url_metadata(parsed, ids.url)
            except Exception:
                resolution = None
            if resolution and resolution.score >= HIGH_CONFIDENCE_THRESHOLD:
                return resolution, None
            if resolution:
                candidates.append(resolution)

        search_chain = []
        if parsed.item_type == "journalArticle":
            search_chain = [self._crossref_search, self._pubmed_search, self._openalex_search]
        elif parsed.item_type == "conferencePaper":
            search_chain = [self._dblp_search, self._crossref_search, self._openalex_search]
        elif parsed.item_type == "preprint":
            search_chain = [self._arxiv_search, self._crossref_search]
        elif parsed.item_type == "webpage":
            if ids.url:
                search_chain = [lambda p: self._url_metadata(p, ids.url)]
            else:
                search_chain = [self._openalex_search]
        else:
            if ids.url and not ids.doi and not ids.arxiv_id:
                search_chain.append(lambda p: self._url_metadata(p, ids.url))
            if ids.arxiv_id:
                search_chain.append(self._arxiv_search)
            search_chain.extend([self._crossref_search, self._pubmed_search, self._openalex_search, self._dblp_search])

        for resolver in search_chain:
            try:
                resolution = resolver(parsed)
            except Exception:
                resolution = None
            if resolution and resolution.score >= HIGH_CONFIDENCE_THRESHOLD:
                return resolution, None
            if resolution:
                candidates.append(resolution)
            attempted.append(resolver.__name__)

        if candidates:
            best = max(candidates, key=lambda x: x.score)
            return None, f"best low-confidence match: {best.source} score={best.score:.2f}"
        return None, f"no metadata source produced a high-confidence match; attempted: {', '.join(attempted)}"

    def _crossref_by_doi(self, parsed, ids: MetadataIdentifiers) -> MetadataResolution | None:
        response = self._get(f"https://api.crossref.org/works/{ids.doi}", timeout=20)
        message = response.json()["message"]
        item = self._crossref_to_item(message, parsed.item_type)
        score = _score_candidate(parsed, item.get("title", ""), item.get("date"), self._creator_names(item), item.get("publicationTitle") or item.get("proceedingsTitle") or "")
        return MetadataResolution(source="crossref-doi", score=max(score, 1.5), item=item, identifiers=ids)

    def _crossref_search(self, parsed) -> MetadataResolution | None:
        query = _search_query(parsed)
        response = self._get(
            "https://api.crossref.org/works",
            params={"query.bibliographic": query, "rows": 8, "mailto": self.mailto},
            timeout=20,
        )
        best: MetadataResolution | None = None
        for message in response.json().get("message", {}).get("items", []):
            item = self._crossref_to_item(message, parsed.item_type)
            container = item.get("publicationTitle") or item.get("proceedingsTitle") or ""
            score = _score_candidate(parsed, item.get("title", ""), item.get("date"), self._creator_names(item), container)
            if normalize_doi(item.get("DOI")):
                score += 0.05
            candidate = MetadataResolution(source="crossref-search", score=score, item=item)
            if best is None or candidate.score > best.score:
                best = candidate
        return best

    def _pubmed_by_pmid(self, parsed, ids: MetadataIdentifiers) -> MetadataResolution | None:
        article = self._pubmed_fetch_article(ids.pmid)
        if article is None:
            return None
        item = self._pubmed_article_to_item(article)
        score = _score_candidate(parsed, item.get("title", ""), item.get("date"), self._creator_names(item), item.get("publicationTitle", ""))
        return MetadataResolution(source="pubmed-pmid", score=max(score, 1.5), item=item, identifiers=ids)

    def _pubmed_search(self, parsed) -> MetadataResolution | None:
        title = _structured_title(parsed)
        if not title:
            return None
        term = f"{title}[Title]"
        response = self._get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            params={"db": "pubmed", "term": term, "retmode": "json", "retmax": 5},
            timeout=20,
        )
        ids = response.json().get("esearchresult", {}).get("idlist", [])
        best: MetadataResolution | None = None
        for pmid in ids:
            article = self._pubmed_fetch_article(pmid)
            if article is None:
                continue
            item = self._pubmed_article_to_item(article)
            score = _score_candidate(parsed, item.get("title", ""), item.get("date"), self._creator_names(item), item.get("publicationTitle", ""))
            candidate = MetadataResolution(source="pubmed-search", score=score, item=item, identifiers=MetadataIdentifiers(pmid=pmid))
            if best is None or candidate.score > best.score:
                best = candidate
        return best

    def _openalex_search(self, parsed) -> MetadataResolution | None:
        query = _search_query(parsed)
        response = self._get(
            "https://api.openalex.org/works",
            params={"search": query, "per-page": 5, "mailto": self.mailto},
            timeout=20,
        )
        best: MetadataResolution | None = None
        for result in response.json().get("results", []):
            item = self._openalex_to_item(result, parsed.item_type)
            container = item.get("publicationTitle") or item.get("proceedingsTitle") or ""
            score = _score_candidate(parsed, item.get("title", ""), item.get("date"), self._creator_names(item), container)
            if normalize_doi(item.get("DOI")):
                score += 0.05
            candidate = MetadataResolution(source="openalex-search", score=score, item=item)
            if best is None or candidate.score > best.score:
                best = candidate
        return best

    def _dblp_search(self, parsed) -> MetadataResolution | None:
        query = _search_query(parsed)
        response = self._get(
            "https://dblp.org/search/publ/api",
            params={"q": query, "format": "json", "h": 10},
            timeout=20,
        )
        hits = response.json().get("result", {}).get("hits", {}).get("hit", [])
        if isinstance(hits, dict):
            hits = [hits]
        best: MetadataResolution | None = None
        for hit in hits:
            info = hit.get("info", {})
            item = self._dblp_to_item(info)
            score = _score_candidate(parsed, item.get("title", ""), item.get("date"), self._creator_names(item), item.get("proceedingsTitle", ""))
            if normalize_doi(item.get("DOI")):
                score += 0.05
            candidate = MetadataResolution(source="dblp-search", score=score, item=item)
            if best is None or candidate.score > best.score:
                best = candidate
        return best

    def _arxiv_by_id(self, parsed, ids: MetadataIdentifiers) -> MetadataResolution | None:
        response = self._get("http://export.arxiv.org/api/query", params={"id_list": ids.arxiv_id}, timeout=20)
        entry = self._parse_arxiv_entry(response.content)
        if entry is None:
            return None
        item = self._arxiv_entry_to_item(entry)
        score = _score_candidate(parsed, item.get("title", ""), item.get("date"), self._creator_names(item), "arXiv")
        return MetadataResolution(source="arxiv-id", score=max(score, 1.5), item=item, identifiers=ids)

    def _arxiv_search(self, parsed) -> MetadataResolution | None:
        title = _structured_title(parsed)
        if not title:
            return None
        query = f'ti:\"{title}\"'
        response = self._get(
            "http://export.arxiv.org/api/query",
            params={"search_query": query, "start": 0, "max_results": 5},
            timeout=20,
        )
        root = etree.fromstring(response.content)
        entries = root.xpath("/*[local-name()='feed']/*[local-name()='entry']")
        best: MetadataResolution | None = None
        for entry in entries:
            item = self._arxiv_entry_to_item(entry)
            score = _score_candidate(parsed, item.get("title", ""), item.get("date"), self._creator_names(item), "arXiv")
            candidate = MetadataResolution(source="arxiv-search", score=score, item=item)
            if best is None or candidate.score > best.score:
                best = candidate
        return best

    def _openlibrary_by_isbn(self, parsed, ids: MetadataIdentifiers) -> MetadataResolution | None:
        response = self._get(
            "https://openlibrary.org/api/books",
            params={"bibkeys": f"ISBN:{ids.isbn}", "format": "json", "jscmd": "data"},
            timeout=20,
        )
        data = response.json().get(f"ISBN:{ids.isbn}")
        if not data:
            return None
        authors = [author.get("name", "") for author in data.get("authors", [])]
        item = {
            "itemType": "book",
            "title": clean_whitespace(data.get("title", parsed.title)),
            "creators": _build_creators(authors),
            "publisher": clean_whitespace((data.get("publishers") or [{}])[0].get("name", "")),
            "place": clean_whitespace((data.get("publish_places") or [{}])[0].get("name", "")),
            "date": str((data.get("publish_date") or "").split()[-1]) if data.get("publish_date") else "",
            "ISBN": ids.isbn,
            "url": data.get("url", ""),
        }
        score = _score_candidate(parsed, item.get("title", ""), item.get("date"), authors, "")
        return MetadataResolution(source="openlibrary-isbn", score=max(score, 1.5), item=item, identifiers=ids)

    def _url_metadata(self, parsed, url: str) -> MetadataResolution | None:
        response = self._get(url, timeout=20, headers={"Accept-Language": "en-US,en;q=0.9"})
        doc = lxml_html.fromstring(response.content)
        meta_map: dict[str, list[str]] = {}
        for meta in doc.xpath("//meta[@content]"):
            key = meta.get("name") or meta.get("property") or meta.get("itemprop")
            if not key:
                continue
            meta_map.setdefault(key.lower(), []).append(clean_whitespace(meta.get("content")))

        title = self._pick(meta_map, "citation_title", "dc.title", "og:title") or clean_whitespace(doc.xpath("string(//title)"))
        authors = meta_map.get("citation_author") or meta_map.get("author") or meta_map.get("article:author") or []
        doi = self._pick(meta_map, "citation_doi")
        journal = self._pick(meta_map, "citation_journal_title")
        conference = self._pick(meta_map, "citation_conference_title")
        pages_first = self._pick(meta_map, "citation_firstpage")
        pages_last = self._pick(meta_map, "citation_lastpage")
        published = self._pick(meta_map, "citation_publication_date", "article:published_time", "pubdate", "date")
        year = ""
        m = re.search(r"(19|20)\d{2}", published or "")
        if m:
            year = m.group(0)

        if journal:
            item = {
                "itemType": "journalArticle",
                "title": title,
                "creators": _build_creators(authors),
                "publicationTitle": journal,
                "volume": self._pick(meta_map, "citation_volume") or "",
                "issue": self._pick(meta_map, "citation_issue") or "",
                "pages": "-".join(x for x in [pages_first, pages_last] if x),
                "date": year,
                "DOI": normalize_doi(doi),
                "url": url,
            }
        elif conference:
            item = {
                "itemType": "conferencePaper",
                "title": title,
                "creators": _build_creators(authors),
                "proceedingsTitle": conference,
                "conferenceName": conference,
                "pages": "-".join(x for x in [pages_first, pages_last] if x),
                "date": year,
                "DOI": normalize_doi(doi),
                "url": url,
            }
        else:
            website_title = self._pick(meta_map, "og:site_name") or re.sub(r"^www\.", "", urlparse(url).netloc)
            item = {
                "itemType": "webpage",
                "title": title,
                "creators": _build_creators(authors),
                "websiteTitle": website_title,
                "date": year,
                "DOI": normalize_doi(doi),
                "url": url,
            }

        container = item.get("publicationTitle") or item.get("proceedingsTitle") or item.get("websiteTitle") or ""
        score = _score_candidate(parsed, item.get("title", ""), item.get("date", ""), self._creator_names(item), container)
        if doi:
            score += 0.1
        if meta_map.get("citation_title"):
            score += 0.1
        return MetadataResolution(source="url-meta", score=score, item=item, identifiers=MetadataIdentifiers(url=url, doi=normalize_doi(doi) or None))

    @staticmethod
    def _pick(meta_map: dict[str, list[str]], *keys: str) -> str | None:
        for key in keys:
            values = meta_map.get(key.lower())
            if values:
                return values[0]
        return None

    @staticmethod
    def _creator_names(item: dict[str, Any]) -> list[str]:
        values = []
        for creator in item.get("creators", []):
            values.append(clean_whitespace(" ".join(x for x in [creator.get("firstName", ""), creator.get("lastName", "")] if x) or creator.get("name", "")))
        return [v for v in values if v]

    def _crossref_to_item(self, message: dict[str, Any], preferred_type: str) -> dict[str, Any]:
        preferred_type = _normalize_item_type(preferred_type)
        authors = []
        for author in message.get("author", []):
            given = clean_whitespace(author.get("given", ""))
            family = clean_whitespace(author.get("family", ""))
            literal = clean_whitespace(author.get("name", ""))
            if family:
                authors.append({"creatorType": "author", "firstName": given, "lastName": family})
            elif literal:
                authors.append({"creatorType": "author", "name": literal})

        year = ""
        for key in ("published-print", "published-online", "issued", "created"):
            part = message.get(key, {}).get("date-parts")
            if part and part[0]:
                year = str(part[0][0])
                break

        title = strip_markup((message.get("title") or [""])[0])
        container = strip_markup((message.get("container-title") or [""])[0])
        short_container = clean_whitespace((message.get("short-container-title") or [""])[0])
        item_type = preferred_type
        if item_type == "unknown":
            item_type = "conferencePaper" if message.get("type") in {"proceedings-article", "journal-issue"} or message.get("event") else "journalArticle"
        item = {
            "itemType": item_type,
            "title": title,
            "creators": authors,
            "date": year,
            "DOI": normalize_doi(message.get("DOI")),
            "url": message.get("URL", ""),
        }
        if item_type == "conferencePaper":
            event = message.get("event") or {}
            item.update(
                {
                    "proceedingsTitle": container,
                    "conferenceName": clean_whitespace(event.get("name", "")) or container,
                    "place": clean_whitespace(event.get("location", "")),
                    "pages": clean_whitespace(message.get("page", "")),
                    "volume": clean_whitespace(message.get("volume", "")),
                }
            )
        else:
            item.update(
                {
                    "publicationTitle": container,
                    "journalAbbreviation": short_container,
                    "volume": clean_whitespace(message.get("volume", "")),
                    "issue": clean_whitespace(message.get("issue", "")),
                    "pages": clean_whitespace(message.get("page", "")),
                }
            )
        return item

    def _pubmed_fetch_article(self, pmid: str):
        response = self._get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
            params={"db": "pubmed", "id": pmid, "retmode": "xml"},
            timeout=20,
        )
        root = etree.fromstring(response.content)
        articles = root.xpath("/*[local-name()='PubmedArticleSet']/*[local-name()='PubmedArticle']")
        return articles[0] if articles else None

    def _pubmed_article_to_item(self, article) -> dict[str, Any]:
        title = clean_whitespace("".join(article.xpath(".//*[local-name()='ArticleTitle']//text()")))
        journal = clean_whitespace("".join(article.xpath(".//*[local-name()='Journal']/*[local-name()='Title'][1]//text()")))
        iso = clean_whitespace("".join(article.xpath(".//*[local-name()='Journal']/*[local-name()='ISOAbbreviation'][1]//text()")))
        volume = clean_whitespace("".join(article.xpath(".//*[local-name()='JournalIssue']/*[local-name()='Volume'][1]//text()")))
        issue = clean_whitespace("".join(article.xpath(".//*[local-name()='JournalIssue']/*[local-name()='Issue'][1]//text()")))
        pages = clean_whitespace("".join(article.xpath(".//*[local-name()='Pagination']/*[local-name()='MedlinePgn'][1]//text()")))
        year = clean_whitespace("".join(article.xpath(".//*[local-name()='JournalIssue']/*[local-name()='PubDate']/*[local-name()='Year'][1]//text()")))
        if not year:
            medline_date = clean_whitespace("".join(article.xpath(".//*[local-name()='JournalIssue']/*[local-name()='PubDate']/*[local-name()='MedlineDate'][1]//text()")))
            year_match = re.search(r"(19|20)\d{2}", medline_date)
            year = year_match.group(0) if year_match else ""

        creators = []
        for author in article.xpath(".//*[local-name()='AuthorList']/*[local-name()='Author']"):
            last_name = clean_whitespace("".join(author.xpath("./*[local-name()='LastName'][1]//text()")))
            fore_name = clean_whitespace("".join(author.xpath("./*[local-name()='ForeName'][1]//text()")))
            collective = clean_whitespace("".join(author.xpath("./*[local-name()='CollectiveName'][1]//text()")))
            if last_name:
                creators.append({"creatorType": "author", "firstName": fore_name, "lastName": last_name})
            elif collective:
                creators.append({"creatorType": "author", "name": collective})

        doi = ""
        for article_id in article.xpath(".//*[local-name()='ArticleIdList']/*[local-name()='ArticleId']"):
            if article_id.get("IdType") == "doi":
                doi = clean_whitespace("".join(article_id.xpath(".//text()")))
                break
        pmid = clean_whitespace("".join(article.xpath(".//*[local-name()='PMID'][1]//text()")))
        extra = f"PMID: {pmid}" if pmid else ""
        return {
            "itemType": "journalArticle",
            "title": title,
            "creators": creators,
            "publicationTitle": journal,
            "journalAbbreviation": iso,
            "volume": volume,
            "issue": issue,
            "pages": pages,
            "date": year,
            "DOI": normalize_doi(doi),
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
            "extra": extra,
        }

    def _openalex_to_item(self, result: dict[str, Any], preferred_type: str) -> dict[str, Any]:
        preferred_type = _normalize_item_type(preferred_type)
        authors = []
        for authorship in result.get("authorships", []):
            display_name = clean_whitespace(authorship.get("author", {}).get("display_name", ""))
            if display_name:
                first_name, last_name = split_name(display_name)
                if last_name:
                    authors.append({"creatorType": "author", "firstName": first_name, "lastName": last_name})
                else:
                    authors.append({"creatorType": "author", "name": display_name})
        biblio = result.get("biblio") or {}
        source = (result.get("primary_location") or {}).get("source") or {}
        title = clean_whitespace(result.get("display_name", ""))
        item_type = preferred_type if preferred_type != "unknown" else ("conferencePaper" if (result.get("type") or "").lower() == "proceedings-article" else "journalArticle")
        item = {
            "itemType": item_type,
            "title": title,
            "creators": authors,
            "date": str(result.get("publication_year") or ""),
            "DOI": normalize_doi(result.get("doi")),
            "url": result.get("doi") or result.get("id") or "",
        }
        pages = "-".join(x for x in [clean_whitespace(biblio.get("first_page", "")), clean_whitespace(biblio.get("last_page", ""))] if x)
        if item_type == "conferencePaper":
            container = clean_whitespace(source.get("display_name", ""))
            item.update({"proceedingsTitle": container, "conferenceName": container, "pages": pages, "volume": clean_whitespace(biblio.get("volume", ""))})
        else:
            item.update(
                {
                    "publicationTitle": clean_whitespace(source.get("display_name", "")),
                    "volume": clean_whitespace(biblio.get("volume", "")),
                    "issue": clean_whitespace(biblio.get("issue", "")),
                    "pages": pages,
                }
            )
        return item

    def _dblp_to_item(self, info: dict[str, Any]) -> dict[str, Any]:
        authors_field = info.get("authors", {}).get("author", [])
        if isinstance(authors_field, dict):
            authors_field = [authors_field]
        author_names = []
        for author in authors_field:
            if isinstance(author, dict):
                text = author.get("text", "")
                text = re.sub(r"\s+\d{4}$", "", text)
                author_names.append(text)
            else:
                author_names.append(re.sub(r"\s+\d{4}$", "", str(author)))
        venue = clean_whitespace(info.get("venue", ""))
        item_type = "conferencePaper" if venue and venue.lower() != "corr" else "preprint"
        item = {
            "itemType": item_type,
            "title": clean_whitespace(html.unescape(info.get("title", "")).rstrip(".")),
            "creators": _build_creators(author_names),
            "date": clean_whitespace(str(info.get("year", ""))),
            "DOI": normalize_doi(info.get("doi")),
            "url": info.get("url", ""),
        }
        if item_type == "conferencePaper":
            item.update(
                {
                    "proceedingsTitle": venue,
                    "conferenceName": venue,
                    "pages": clean_whitespace(info.get("pages", "")),
                }
            )
        else:
            item.update({"repository": venue or "CoRR"})
        return item

    def _parse_arxiv_entry(self, xml_bytes: bytes):
        root = etree.fromstring(xml_bytes)
        entries = root.xpath("/*[local-name()='feed']/*[local-name()='entry']")
        return entries[0] if entries else None

    def _arxiv_entry_to_item(self, entry) -> dict[str, Any]:
        title = clean_whitespace("".join(entry.xpath("./*[local-name()='title'][1]//text()")))
        published = clean_whitespace("".join(entry.xpath("./*[local-name()='published'][1]//text()")))
        year_match = re.search(r"(19|20)\d{2}", published)
        year = year_match.group(0) if year_match else ""
        authors = [clean_whitespace("".join(author.xpath("./*[local-name()='name'][1]//text()"))) for author in entry.xpath("./*[local-name()='author']")]
        abs_url = ""
        for link in entry.xpath("./*[local-name()='link']"):
            if link.get("rel") == "alternate":
                abs_url = link.get("href", "")
                break
        arxiv_id = abs_url.rsplit("/", 1)[-1] if abs_url else ""
        return {
            "itemType": "preprint",
            "title": title,
            "creators": _build_creators(authors),
            "date": year,
            "archiveID": arxiv_id,
            "repository": "arXiv",
            "url": abs_url,
        }
