from __future__ import annotations

from dataclasses import dataclass


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
