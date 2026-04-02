from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import requests

from .models import SearchHit
from .utils import authors_to_text, build_fts_query


class ZoteroLocalAPIClient:
    def __init__(self, base_url: str = "http://127.0.0.1:23119/api", user_id: str = "0") -> None:
        self.base_url = base_url.rstrip("/")
        self.user_id = user_id
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "zotero-word-bridge/0.1"})

    @property
    def user_prefix(self) -> str:
        return f"/users/{self.user_id}"

    def list_items(self) -> list[dict[str, Any]]:
        response = self._request("GET", f"{self.user_prefix}/items", params={"format": "json", "limit": 0})
        return response.json()

    def fulltext_versions(self, since: int = 0) -> dict[str, int]:
        response = self._request("GET", f"{self.user_prefix}/fulltext", params={"since": since})
        return response.json()

    def attachment_fulltext(self, item_key: str) -> dict[str, Any]:
        response = self._request("GET", f"{self.user_prefix}/items/{item_key}/fulltext")
        return response.json()

    def attachment_file_url(self, item_key: str) -> str | None:
        response = self._request("GET", f"{self.user_prefix}/items/{item_key}/file/view/url")
        return response.text.strip() or None

    def sync_to_index(self, index_path: str | Path) -> dict[str, int]:
        index = Path(index_path)
        index.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(index) as conn:
            conn.row_factory = sqlite3.Row
            self._ensure_schema(conn)

            items = self.list_items()
            fulltext_versions = self.fulltext_versions(0)
            item_count = 0
            attachment_count = 0
            fulltext_count = 0

            for entry in items:
                data = entry.get("data", {})
                item_type = data.get("itemType")
                key = data.get("key")
                if not key:
                    continue
                if item_type == "attachment":
                    attachment_count += 1
                    fulltext_version = fulltext_versions.get(key)
                    fulltext_payload = {"content": ""}
                    file_url = None
                    if fulltext_version is not None:
                        fulltext_payload = self.attachment_fulltext(key)
                        file_url = self.attachment_file_url(key)
                        fulltext_count += 1
                    conn.execute(
                        """
                        INSERT INTO attachments(
                            attachment_key, parent_key, attachment_title, content_type,
                            file_url, fulltext_version, fulltext_content, raw_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(attachment_key) DO UPDATE SET
                            parent_key=excluded.parent_key,
                            attachment_title=excluded.attachment_title,
                            content_type=excluded.content_type,
                            file_url=excluded.file_url,
                            fulltext_version=excluded.fulltext_version,
                            fulltext_content=excluded.fulltext_content,
                            raw_json=excluded.raw_json
                        """,
                        (
                            key,
                            data.get("parentItem"),
                            data.get("title") or data.get("filename") or key,
                            data.get("contentType") or "",
                            file_url,
                            fulltext_version,
                            fulltext_payload.get("content", ""),
                            json.dumps(entry, ensure_ascii=False),
                        ),
                    )
                    conn.execute("DELETE FROM attachment_fts WHERE attachment_key = ?", (key,))
                    conn.execute(
                        "INSERT INTO attachment_fts(attachment_key, parent_key, attachment_title, fulltext_content) VALUES (?, ?, ?, ?)",
                        (
                            key,
                            data.get("parentItem"),
                            data.get("title") or data.get("filename") or key,
                            fulltext_payload.get("content", ""),
                        ),
                    )
                else:
                    item_count += 1
                    creators = authors_to_text(
                        [
                            creator.get("name") or " ".join(
                                part for part in [creator.get("firstName", ""), creator.get("lastName", "")] if part
                            )
                            for creator in data.get("creators", [])
                        ]
                    )
                    conn.execute(
                        """
                        INSERT INTO items(
                            item_key, item_type, title, creators, year, doi, abstract, raw_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(item_key) DO UPDATE SET
                            item_type=excluded.item_type,
                            title=excluded.title,
                            creators=excluded.creators,
                            year=excluded.year,
                            doi=excluded.doi,
                            abstract=excluded.abstract,
                            raw_json=excluded.raw_json
                        """,
                        (
                            key,
                            item_type,
                            data.get("title") or key,
                            creators,
                            data.get("date") or "",
                            data.get("DOI") or "",
                            data.get("abstractNote") or "",
                            json.dumps(entry, ensure_ascii=False),
                        ),
                    )
            conn.commit()
            return {"items": item_count, "attachments": attachment_count, "fulltext": fulltext_count}

    @staticmethod
    def search_index(index_path: str | Path, query: str, limit: int = 5) -> list[SearchHit]:
        with sqlite3.connect(index_path) as conn:
            conn.row_factory = sqlite3.Row
            fts_query = build_fts_query(query)
            rows = conn.execute(
                """
                SELECT
                    a.attachment_key,
                    a.parent_key,
                    COALESCE(i.title, a.attachment_title) AS parent_title,
                    COALESCE(i.creators, '') AS creators,
                    a.attachment_title,
                    a.file_url,
                    snippet(attachment_fts, 3, '[', ']', ' ... ', 16) AS snippet,
                    bm25(attachment_fts) AS score
                FROM attachment_fts
                JOIN attachments a ON a.attachment_key = attachment_fts.attachment_key
                LEFT JOIN items i ON i.item_key = a.parent_key
                WHERE attachment_fts MATCH ?
                ORDER BY score
                LIMIT ?
                """,
                (fts_query, limit),
            ).fetchall()
        return [
            SearchHit(
                attachment_key=row["attachment_key"],
                parent_key=row["parent_key"],
                parent_title=row["parent_title"],
                creators=row["creators"],
                attachment_title=row["attachment_title"],
                file_url=row["file_url"],
                snippet=row["snippet"] or "",
                score=float(row["score"] if row["score"] is not None else 0.0),
            )
            for row in rows
        ]

    @staticmethod
    def write_context(index_path: str | Path, query: str, output_path: str | Path, limit: int = 5) -> list[SearchHit]:
        hits = ZoteroLocalAPIClient.search_index(index_path, query, limit=limit)
        lines = [f"# Zotero KB Context", "", f"Query: `{query}`", ""]
        for idx, hit in enumerate(hits, start=1):
            lines.extend(
                [
                    f"## {idx}. {hit.parent_title}",
                    "",
                    f"- Parent key: {hit.parent_key or 'N/A'}",
                    f"- Attachment key: {hit.attachment_key}",
                    f"- Creators: {hit.creators or 'Unknown'}",
                    f"- Attachment title: {hit.attachment_title}",
                    f"- File URL: {hit.file_url or 'Unavailable'}",
                    "",
                    hit.snippet or "(No snippet)",
                    "",
                ]
            )
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("\n".join(lines), encoding="utf-8")
        return hits

    @staticmethod
    def _ensure_schema(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS items(
                item_key TEXT PRIMARY KEY,
                item_type TEXT NOT NULL,
                title TEXT NOT NULL,
                creators TEXT NOT NULL,
                year TEXT NOT NULL,
                doi TEXT NOT NULL,
                abstract TEXT NOT NULL,
                raw_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS attachments(
                attachment_key TEXT PRIMARY KEY,
                parent_key TEXT,
                attachment_title TEXT NOT NULL,
                content_type TEXT NOT NULL,
                file_url TEXT,
                fulltext_version INTEGER,
                fulltext_content TEXT NOT NULL,
                raw_json TEXT NOT NULL
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS attachment_fts USING fts5(
                attachment_key UNINDEXED,
                parent_key UNINDEXED,
                attachment_title,
                fulltext_content,
                tokenize='unicode61'
            );
            """
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        response = self.session.request(method, f"{self.base_url}{path}", timeout=30, **kwargs)
        response.raise_for_status()
        return response
