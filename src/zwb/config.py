from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class OpenAlexConfig:
    base_url: str = "https://api.openalex.org"
    mailto: str | None = None


@dataclass(slots=True)
class ZoteroWebConfig:
    base_url: str = "https://api.zotero.org"
    library_type: str = "users"
    library_id: str = ""
    api_key: str = ""

    @property
    def library_prefix(self) -> str:
        if not self.library_id:
            raise ValueError("zotero_web.library_id is required")
        if self.library_type not in {"users", "groups"}:
            raise ValueError("zotero_web.library_type must be 'users' or 'groups'")
        return f"/{self.library_type}/{self.library_id}"

    def require_write_access(self) -> None:
        _ = self.library_prefix
        if not self.api_key:
            raise ValueError("zotero_web.api_key is required for write operations")


@dataclass(slots=True)
class ZoteroLocalConfig:
    base_url: str = "http://127.0.0.1:23119/api"
    user_id: str = "0"

    @property
    def user_prefix(self) -> str:
        return f"/users/{self.user_id}"


@dataclass(slots=True)
class DefaultsConfig:
    citation_style_id: str = "http://www.zotero.org/styles/apa"
    citation_locale: str = "en-US"
    bibliography_placeholder: str = "[[BIBLIOGRAPHY]]"


@dataclass(slots=True)
class AppConfig:
    openalex: OpenAlexConfig = field(default_factory=OpenAlexConfig)
    zotero_web: ZoteroWebConfig = field(default_factory=ZoteroWebConfig)
    zotero_local: ZoteroLocalConfig = field(default_factory=ZoteroLocalConfig)
    defaults: DefaultsConfig = field(default_factory=DefaultsConfig)


def _merge_env(data: dict) -> dict:
    web = data.setdefault("zotero_web", {})
    local = data.setdefault("zotero_local", {})
    openalex = data.setdefault("openalex", {})

    web.setdefault("api_key", os.getenv("ZWB_ZOTERO_API_KEY", ""))
    web.setdefault("library_id", os.getenv("ZWB_ZOTERO_LIBRARY_ID", ""))
    web.setdefault("library_type", os.getenv("ZWB_ZOTERO_LIBRARY_TYPE", "users"))
    web.setdefault("base_url", os.getenv("ZWB_ZOTERO_BASE_URL", "https://api.zotero.org"))

    local.setdefault("base_url", os.getenv("ZWB_ZOTERO_LOCAL_BASE_URL", "http://127.0.0.1:23119/api"))
    local.setdefault("user_id", os.getenv("ZWB_ZOTERO_LOCAL_USER_ID", "0"))

    openalex.setdefault("mailto", os.getenv("ZWB_OPENALEX_MAILTO"))
    openalex.setdefault("base_url", os.getenv("ZWB_OPENALEX_BASE_URL", "https://api.openalex.org"))
    return data


def load_config(path: str | Path | None) -> AppConfig:
    raw: dict = {}
    if path:
        config_path = Path(path)
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    raw = _merge_env(raw)
    return AppConfig(
        openalex=OpenAlexConfig(**raw.get("openalex", {})),
        zotero_web=ZoteroWebConfig(**raw.get("zotero_web", {})),
        zotero_local=ZoteroLocalConfig(**raw.get("zotero_local", {})),
        defaults=DefaultsConfig(**raw.get("defaults", {})),
    )
