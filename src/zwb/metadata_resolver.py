from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import requests
from lxml import etree, html as lxml_html

from .utils import clean_whitespace, normalize_doi, split_name

DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.I)
PMID_RE = re.compile(r"\bPMID[:\s]*([0-9]{5,9})\b", re.I)
ARXIV_RE = re.compile(r"(?:arxiv[:/ ]\s*)(\d{4}\.\d{4,5}(?:v\d+)?)|\b(\d{4}\.\d{4,5}(?:v\d+)?)\b", re.I)
ISBN_RE = re.compile(r"\b(?:97[89][- ]?)?\d(?:[- ]?\d){8,16}\b")
URL_RE = re.compile(r"https?://[^\s>]+", re.I)
TITLE_NORMALIZER_RE = re.compile(r"[^a-z0-9]+")
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


def extract_identifiers(raw_reference: str) -> MetadataIdentifiers:
    doi_match = DOI_RE.search(raw_reference)
    pmid_match = PMID_RE.search(raw_reference)
    arxiv_match = ARXIV_RE.search(raw_reference)
    isbn_match = ISBN_RE.search(raw_reference)
    url_match = URL_RE.search(raw_reference)

    url = url_match.group(0).rstrip(".,;") if url_match else None
    doi = normalize_doi(doi_match.group(0)) if doi_match else None
    pmid = pmid_match.group(1) if pmid_match else None
    arxiv_id = None
    if arxiv_match:
        arxiv_id = (arxiv_match.group(1) or arxiv_match.group(2) or "").strip()
    isbn = None
    if isbn_match:
        digits = re.sub(r"[^0-9Xx]", "", isbn_match.group(0))
        if len(digits) in {10, 13}:
            isbn = digits.upper()

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
    score = 0.0
    title_score = 0.0
    if title:
        title_score = 1.0 * _ratio(normalize_title(parsed.title), normalize_title(title))
        score += title_score
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

    def resolve(self, parsed) -> tuple[MetadataResolution | None, str | None]:
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
        response = self.session.get(f"https://api.crossref.org/works/{ids.doi}", timeout=20)
        response.raise_for_status()
        message = response.json()["message"]
        item = self._crossref_to_item(message, parsed.item_type)
        score = _score_candidate(parsed, item.get("title", ""), item.get("date"), self._creator_names(item), item.get("publicationTitle") or item.get("proceedingsTitle") or "")
        return MetadataResolution(source="crossref-doi", score=max(score, 1.5), item=item, identifiers=ids)

    def _crossref_search(self, parsed) -> MetadataResolution | None:
        query = " ".join(x for x in [parsed.title, _first_author_last_name(parsed.creators), parsed.fields.get("date", "")] if x)
        response = self.session.get(
            "https://api.crossref.org/works",
            params={"query.bibliographic": query, "rows": 8, "mailto": self.mailto},
            timeout=20,
        )
        response.raise_for_status()
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
        term = f'{parsed.title}[Title]'
        response = self.session.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            params={"db": "pubmed", "term": term, "retmode": "json", "retmax": 5},
            timeout=20,
        )
        response.raise_for_status()
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
        query = " ".join(x for x in [parsed.title, _first_author_last_name(parsed.creators), parsed.fields.get("date", "")] if x)
        response = self.session.get(
            "https://api.openalex.org/works",
            params={"search": query, "per-page": 5, "mailto": self.mailto},
            timeout=20,
        )
        response.raise_for_status()
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
        query = " ".join(x for x in [parsed.title, _first_author_last_name(parsed.creators), parsed.fields.get("date", "")] if x)
        response = self.session.get(
            "https://dblp.org/search/publ/api",
            params={"q": query, "format": "json", "h": 10},
            timeout=20,
        )
        response.raise_for_status()
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
        response = self.session.get("http://export.arxiv.org/api/query", params={"id_list": ids.arxiv_id}, timeout=20)
        response.raise_for_status()
        entry = self._parse_arxiv_entry(response.content)
        if entry is None:
            return None
        item = self._arxiv_entry_to_item(entry)
        score = _score_candidate(parsed, item.get("title", ""), item.get("date"), self._creator_names(item), "arXiv")
        return MetadataResolution(source="arxiv-id", score=max(score, 1.5), item=item, identifiers=ids)

    def _arxiv_search(self, parsed) -> MetadataResolution | None:
        query = f'ti:\"{parsed.title}\"'
        response = self.session.get(
            "http://export.arxiv.org/api/query",
            params={"search_query": query, "start": 0, "max_results": 5},
            timeout=20,
        )
        response.raise_for_status()
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
        response = self.session.get(
            "https://openlibrary.org/api/books",
            params={"bibkeys": f"ISBN:{ids.isbn}", "format": "json", "jscmd": "data"},
            timeout=20,
        )
        response.raise_for_status()
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
        response = self.session.get(url, timeout=20, headers={"Accept-Language": "en-US,en;q=0.9"})
        response.raise_for_status()
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
        response = self.session.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
            params={"db": "pubmed", "id": pmid, "retmode": "xml"},
            timeout=20,
        )
        response.raise_for_status()
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
        item = {
            "itemType": preferred_type,
            "title": title,
            "creators": authors,
            "date": str(result.get("publication_year") or ""),
            "DOI": normalize_doi(result.get("doi")),
            "url": result.get("doi") or result.get("id") or "",
        }
        pages = "-".join(x for x in [clean_whitespace(biblio.get("first_page", "")), clean_whitespace(biblio.get("last_page", ""))] if x)
        if preferred_type == "conferencePaper":
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
