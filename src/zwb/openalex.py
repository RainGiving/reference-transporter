from __future__ import annotations

from pathlib import Path

import requests

from .models import Author, LiteratureRecord
from .utils import clean_whitespace, first_sentence, split_name


class OpenAlexClient:
    def __init__(self, base_url: str = "https://api.openalex.org", mailto: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.mailto = mailto
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "zotero-word-bridge/0.1"})

    def search_works(self, query: str, limit: int = 10) -> list[LiteratureRecord]:
        params = {
            "search": query,
            "per-page": max(1, min(limit, 50)),
        }
        if self.mailto:
            params["mailto"] = self.mailto
        response = self.session.get(f"{self.base_url}/works", params=params, timeout=30)
        response.raise_for_status()
        payload = response.json()
        return [self._map_work(item) for item in payload.get("results", [])[:limit]]

    def write_summary(self, query: str, records: list[LiteratureRecord], output_path: str | Path) -> None:
        output = Path(output_path)
        lines = [f"# Literature Summary", "", f"Query: `{query}`", ""]
        for index, record in enumerate(records, start=1):
            authors = ", ".join(author.display_name for author in record.authors[:5])
            if len(record.authors) > 5:
                authors += ", et al."
            lines.extend(
                [
                    f"## {index}. {record.title}",
                    "",
                    f"- Year: {record.year or 'Unknown'}",
                    f"- Authors: {authors or 'Unknown'}",
                    f"- Venue: {record.venue or 'Unknown'}",
                    f"- DOI: {record.doi or 'N/A'}",
                    f"- Citations: {record.cited_by_count if record.cited_by_count is not None else 'N/A'}",
                ]
            )
            if record.pdf_url:
                lines.append(f"- PDF: {record.pdf_url}")
            if record.landing_page_url:
                lines.append(f"- URL: {record.landing_page_url}")
            summary = first_sentence(record.abstract) or "No abstract returned by OpenAlex."
            lines.extend(["", summary, ""])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("\n".join(lines), encoding="utf-8")

    def _map_work(self, work: dict) -> LiteratureRecord:
        authors: list[Author] = []
        for authorship in work.get("authorships", []):
            display_name = clean_whitespace(authorship.get("author", {}).get("display_name"))
            if not display_name:
                continue
            first_name, last_name = split_name(display_name)
            authors.append(Author(display_name=display_name, first_name=first_name, last_name=last_name))

        primary_location = work.get("primary_location") or {}
        best_oa_location = work.get("best_oa_location") or {}
        pdf_url = primary_location.get("pdf_url") or best_oa_location.get("pdf_url")
        source = (primary_location.get("source") or {}).get("display_name")
        doi = work.get("doi")
        abstract = self._rebuild_abstract(work.get("abstract_inverted_index"))
        return LiteratureRecord(
            title=clean_whitespace(work.get("display_name")) or "Untitled",
            authors=authors,
            year=work.get("publication_year"),
            doi=doi,
            abstract=abstract,
            venue=clean_whitespace(source),
            pdf_url=pdf_url,
            landing_page_url=doi or work.get("id"),
            openalex_id=work.get("id"),
            cited_by_count=work.get("cited_by_count"),
            work_type=work.get("type"),
        )

    @staticmethod
    def _rebuild_abstract(inverted_index: dict | None) -> str | None:
        if not inverted_index:
            return None
        positions: dict[int, str] = {}
        for token, token_positions in inverted_index.items():
            for position in token_positions:
                positions[position] = token
        return " ".join(token for _, token in sorted(positions.items()))
