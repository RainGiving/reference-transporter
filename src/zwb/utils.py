from __future__ import annotations

import random
import re
import string
from typing import Iterable


def random_id(length: int = 8) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choice(alphabet) for _ in range(length))


def chunk_string(value: str, size: int) -> list[str]:
    return [value[i : i + size] for i in range(0, len(value), size)]


def clean_whitespace(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def first_sentence(value: str | None, fallback_length: int = 220) -> str:
    text = clean_whitespace(value)
    if not text:
        return ""
    match = re.search(r"(.+?[.!?])(\s|$)", text)
    if match:
        return match.group(1).strip()
    return text[:fallback_length].rstrip()


def split_name(display_name: str) -> tuple[str, str]:
    parts = display_name.strip().split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return "", parts[0]
    return " ".join(parts[:-1]), parts[-1]


def normalize_doi(doi: str | None) -> str:
    if not doi:
        return ""
    doi = doi.strip()
    doi = doi.removeprefix("https://doi.org/")
    doi = doi.removeprefix("http://doi.org/")
    doi = doi.removeprefix("doi:")
    return doi.strip().lower()


def authors_to_text(authors: Iterable[str]) -> str:
    values = [clean_whitespace(author) for author in authors if clean_whitespace(author)]
    return ", ".join(values)


def build_fts_query(query: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9_]{2,}", query.lower())
    if not tokens:
        raise ValueError("Query must contain at least one searchable token")
    return " AND ".join(f"{token}*" for token in tokens)
