from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Author:
    display_name: str
    first_name: str = ""
    last_name: str = ""


@dataclass(slots=True)
class LiteratureRecord:
    title: str
    authors: list[Author]
    year: int | None = None
    doi: str | None = None
    abstract: str | None = None
    venue: str | None = None
    pdf_url: str | None = None
    landing_page_url: str | None = None
    openalex_id: str | None = None
    cited_by_count: int | None = None
    work_type: str | None = None


@dataclass(slots=True)
class CitationItemSpec:
    key: str
    locator: str | None = None
    label: str | None = None
    prefix: str | None = None
    suffix: str | None = None
    suppress_author: bool = False
    author_only: bool = False


@dataclass(slots=True)
class CitationSpec:
    placeholder: str
    items: list[CitationItemSpec]
    preview_text: str | None = None
    note_index: int = 0


@dataclass(slots=True)
class SearchHit:
    attachment_key: str
    parent_key: str | None
    parent_title: str
    creators: str
    attachment_title: str
    file_url: str | None
    snippet: str
    score: float


@dataclass(slots=True)
class ZoteroImportResult:
    created: list[str] = field(default_factory=list)
    skipped_existing: list[str] = field(default_factory=list)
    collection_key: str | None = None
