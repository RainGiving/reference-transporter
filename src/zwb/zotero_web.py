from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import requests

from .models import LiteratureRecord, ZoteroImportResult
from .utils import normalize_doi


class ZoteroWebClient:
    def __init__(self, base_url: str, library_type: str, library_id: str, api_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.library_type = library_type
        self.library_id = library_id
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "zotero-word-bridge/0.1",
                "Zotero-API-Key": api_key,
            }
        )

    @property
    def library_prefix(self) -> str:
        if self.library_type not in {"users", "groups"}:
            raise ValueError("library_type must be 'users' or 'groups'")
        if not self.library_id:
            raise ValueError("library_id is required")
        return f"/{self.library_type}/{self.library_id}"

    def resolve_collection(self, collection_path: str | None, create_missing: bool = False) -> str | None:
        if not collection_path:
            return None
        if "/" not in collection_path and len(collection_path) == 8 and collection_path.isalnum():
            return collection_path

        target_parts = [part.strip() for part in collection_path.split("/") if part.strip()]
        if not target_parts:
            return None

        collections = self.list_collections()
        path_map = {self._collection_path(entry["data"], collections): entry["key"] for entry in collections}

        current_path: list[str] = []
        current_parent: str | bool = False
        for part in target_parts:
            current_path.append(part)
            resolved = path_map.get(tuple(current_path))
            if resolved:
                current_parent = resolved
                continue
            if not create_missing:
                raise ValueError(f"Collection path not found: {'/'.join(current_path)}")
            payload = [{"name": part, "parentCollection": current_parent or False}]
            self._request(
                "POST",
                f"{self.library_prefix}/collections",
                headers={"Zotero-Write-Token": str(uuid4()), "Content-Type": "application/json"},
                data=json.dumps(payload),
            )
            collections = self.list_collections()
            path_map = {self._collection_path(entry["data"], collections): entry["key"] for entry in collections}
            resolved = path_map.get(tuple(current_path))
            if not resolved:
                raise RuntimeError(f"Collection creation did not resolve for {'/'.join(current_path)}")
            current_parent = resolved
        return current_parent if current_parent else None

    def list_collections(self) -> list[dict[str, Any]]:
        response = self._request("GET", f"{self.library_prefix}/collections", params={"format": "json"})
        return response.json()

    def import_records(
        self,
        records: list[LiteratureRecord],
        collection_path: str | None = None,
        create_collections: bool = False,
        tags: list[str] | None = None,
    ) -> ZoteroImportResult:
        collection_key = self.resolve_collection(collection_path, create_missing=create_collections)
        result = ZoteroImportResult(collection_key=collection_key)
        items_to_create = []
        seen_dois: set[str] = set()

        for record in records:
            normalized_doi = normalize_doi(record.doi)
            if normalized_doi and normalized_doi in seen_dois:
                result.skipped_existing.append(record.title)
                continue
            if normalized_doi and self.find_item_by_doi(normalized_doi):
                result.skipped_existing.append(record.title)
                seen_dois.add(normalized_doi)
                continue
            items_to_create.append(self._record_to_zotero_item(record, collection_key, tags or []))
            if normalized_doi:
                seen_dois.add(normalized_doi)

        if items_to_create:
            response = self._request(
                "POST",
                f"{self.library_prefix}/items",
                headers={"Zotero-Write-Token": str(uuid4()), "Content-Type": "application/json"},
                data=json.dumps(items_to_create),
            )
            payload = response.json()
            successful = payload.get("successful", {})
            for write_result in successful.values():
                if isinstance(write_result, dict) and "key" in write_result:
                    result.created.append(write_result["key"])
        return result

    def find_item_by_doi(self, doi: str) -> dict[str, Any] | None:
        response = self._request(
            "GET",
            f"{self.library_prefix}/items",
            params={
                "format": "json",
                "q": doi,
                "qmode": "everything",
                "itemType": "-attachment",
            },
        )
        for item in response.json():
            data = item.get("data", {})
            if normalize_doi(data.get("DOI")) == normalize_doi(doi):
                return item
        return None

    def fetch_csljson(self, item_key: str) -> dict[str, Any]:
        response = self._request(
            "GET",
            f"{self.library_prefix}/items/{item_key}",
            params={"format": "csljson"},
        )
        data = response.json()
        if isinstance(data, list):
            if not data:
                raise KeyError(f"No CSL JSON returned for item {item_key}")
            return data[0]
        return data

    def build_item_uri(self, item_key: str) -> str:
        return f"http://zotero.org/{self.library_type}/{self.library_id}/items/{item_key}"

    def _record_to_zotero_item(self, record: LiteratureRecord, collection_key: str | None, tags: list[str]) -> dict[str, Any]:
        creators = []
        for author in record.authors:
            if author.last_name:
                creators.append(
                    {
                        "creatorType": "author",
                        "firstName": author.first_name,
                        "lastName": author.last_name,
                    }
                )
            else:
                creators.append({"creatorType": "author", "name": author.display_name})
        item = {
            "itemType": self._map_item_type(record.work_type),
            "title": record.title,
            "creators": creators,
            "abstractNote": record.abstract or "",
            "publicationTitle": record.venue or "",
            "date": str(record.year) if record.year else "",
            "DOI": normalize_doi(record.doi),
            "url": record.landing_page_url or "",
            "tags": [{"tag": tag} for tag in tags],
            "collections": [collection_key] if collection_key else [],
        }
        if record.pdf_url:
            item["extra"] = f"OpenAlex PDF: {record.pdf_url}"
        return item

    @staticmethod
    def _map_item_type(work_type: str | None) -> str:
        mapping = {
            "article": "journalArticle",
            "journal-article": "journalArticle",
            "book": "book",
            "book-chapter": "bookSection",
            "dissertation": "thesis",
            "preprint": "preprint",
            "report": "report",
            "dataset": "dataset",
        }
        return mapping.get((work_type or "").lower(), "journalArticle")

    def _collection_path(self, collection_data: dict[str, Any], all_collections: list[dict[str, Any]]) -> tuple[str, ...]:
        by_key = {entry["key"]: entry["data"] for entry in all_collections}
        path = [collection_data["name"]]
        parent = collection_data.get("parentCollection")
        while parent:
            parent_data = by_key[parent]
            path.append(parent_data["name"])
            parent = parent_data.get("parentCollection")
        return tuple(reversed(path))

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        response = self.session.request(method, f"{self.base_url}{path}", timeout=30, **kwargs)
        response.raise_for_status()
        return response
