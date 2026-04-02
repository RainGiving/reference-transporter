from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

import requests
from lxml import etree

from .utils import clean_whitespace, normalize_doi, split_name

TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}


@dataclass(slots=True)
class GrobidParsedReference:
    title: str
    creators: list[dict[str, str]]
    fields: dict[str, Any]
    item_type: str
    identifiers: dict[str, str]
    raw: str | None = None


class GrobidClient:
    def __init__(self, base_url: str | None = None, timeout: int = 60) -> None:
        configured = base_url or os.getenv("GROBID_URL") or os.getenv("REFERENCE_TRANSPORTER_GROBID_URL")
        self.base_url = (configured or "http://127.0.0.1:8070").rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "reference-transporter/0.2"})

    @property
    def process_citation_list_url(self) -> str:
        if self.base_url.endswith("/api"):
            return f"{self.base_url}/processCitationList"
        return f"{self.base_url}/api/processCitationList"

    @property
    def process_citation_url(self) -> str:
        if self.base_url.endswith("/api"):
            return f"{self.base_url}/processCitation"
        return f"{self.base_url}/api/processCitation"

    def parse_many(self, references: list[str]) -> list[GrobidParsedReference | None]:
        if not references:
            return []
        try:
            response = self.session.post(
                self.process_citation_list_url,
                data=[("citations", reference) for reference in references] + [("includeRawCitations", "1")],
                headers={"Accept": "application/xml"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            parsed = self._parse_list_response(response.content)
            if len(parsed) == len(references):
                return parsed
        except Exception:
            pass

        results: list[GrobidParsedReference | None] = []
        for reference in references:
            results.append(self.parse_one(reference))
        return results

    def parse_one(self, reference: str) -> GrobidParsedReference | None:
        try:
            response = self.session.post(
                self.process_citation_url,
                data={"citations": reference, "includeRawCitations": "1"},
                headers={"Accept": "application/xml"},
                timeout=self.timeout,
            )
            response.raise_for_status()
        except Exception:
            return None
        parsed = self._parse_list_response(response.content)
        return parsed[0] if parsed else None

    def _parse_list_response(self, xml_bytes: bytes) -> list[GrobidParsedReference | None]:
        try:
            root = etree.fromstring(xml_bytes)
        except Exception:
            return []

        bibl_structs = root.xpath(".//*[local-name()='biblStruct']")
        if not bibl_structs and root.tag.endswith("biblStruct"):
            bibl_structs = [root]
        results = [self._parse_bibl_struct(node) for node in bibl_structs]
        return results

    def _parse_bibl_struct(self, node) -> GrobidParsedReference | None:
        title = self._extract_title(node)
        if not title:
            return None

        creators = self._extract_creators(node)
        fields, identifiers = self._extract_fields(node)
        item_type = self._infer_item_type(node, identifiers, fields)
        return GrobidParsedReference(
            title=title,
            creators=creators,
            fields=fields,
            item_type=item_type,
            identifiers=identifiers,
            raw=self._extract_raw(node),
        )

    def _extract_title(self, node) -> str:
        candidates = [
            ".//tei:analytic/tei:title[1]",
            ".//tei:title[@level='a'][1]",
            ".//tei:title[@type='main'][1]",
            ".//tei:monogr/tei:title[1]",
            ".//tei:title[1]",
        ]
        for expr in candidates:
            text = clean_whitespace("".join(node.xpath(f"{expr}//text()", namespaces=TEI_NS)))
            if text:
                return text
        return ""

    def _extract_creators(self, node) -> list[dict[str, str]]:
        creators: list[dict[str, str]] = []
        for author in node.xpath(".//tei:author", namespaces=TEI_NS):
            surname = clean_whitespace("".join(author.xpath(".//tei:surname[1]//text()", namespaces=TEI_NS)))
            forenames = [
                clean_whitespace("".join(name.xpath(".//text()")))
                for name in author.xpath(".//tei:forename", namespaces=TEI_NS)
            ]
            forenames = [name for name in forenames if name]
            if surname:
                creators.append(
                    {
                        "creatorType": "author",
                        "firstName": " ".join(forenames),
                        "lastName": surname,
                    }
                )
                continue
            literal = clean_whitespace("".join(author.xpath(".//text()", namespaces=TEI_NS)))
            if literal:
                first_name, last_name = split_name(literal)
                if last_name:
                    creators.append({"creatorType": "author", "firstName": first_name, "lastName": last_name})
                else:
                    creators.append({"creatorType": "author", "name": literal})
        return creators

    def _extract_fields(self, node) -> tuple[dict[str, Any], dict[str, str]]:
        identifiers: dict[str, str] = {}
        for idno in node.xpath(".//tei:idno", namespaces=TEI_NS):
            id_type = clean_whitespace(idno.get("type", "")).lower()
            value = clean_whitespace("".join(idno.xpath(".//text()")))
            if not value:
                continue
            if id_type == "doi":
                identifiers["DOI"] = normalize_doi(value)
            elif id_type in {"pmid", "pubmed"}:
                identifiers["PMID"] = value
            elif id_type in {"arxiv", "arxivid"}:
                identifiers["arXiv"] = value
            elif id_type == "isbn":
                identifiers["ISBN"] = value

        ptr_url = clean_whitespace("".join(node.xpath(".//tei:ptr/@target", namespaces=TEI_NS)))
        if ptr_url:
            identifiers["URL"] = ptr_url

        fields: dict[str, Any] = {}

        journal_title = clean_whitespace("".join(node.xpath(".//tei:monogr/tei:title[@level='j'][1]//text()", namespaces=TEI_NS)))
        monogr_title = clean_whitespace("".join(node.xpath(".//tei:monogr/tei:title[1]//text()", namespaces=TEI_NS)))
        if journal_title:
            fields["publicationTitle"] = journal_title
        elif monogr_title:
            fields["proceedingsTitle"] = monogr_title
            fields["conferenceName"] = monogr_title

        publisher = clean_whitespace("".join(node.xpath(".//tei:imprint/tei:publisher[1]//text()", namespaces=TEI_NS)))
        pub_place = clean_whitespace("".join(node.xpath(".//tei:imprint/tei:pubPlace[1]//text()", namespaces=TEI_NS)))
        if publisher:
            fields["publisher"] = publisher
        if pub_place:
            fields["place"] = pub_place

        year = ""
        date_node = node.xpath(".//tei:imprint/tei:date[1]", namespaces=TEI_NS)
        if date_node:
            when = clean_whitespace(date_node[0].get("when", ""))
            year_match = re.search(r"(19|20)\d{2}", when or clean_whitespace("".join(date_node[0].xpath(".//text()"))))
            if year_match:
                year = year_match.group(0)
        if year:
            fields["date"] = year

        for unit, zotero_field in [("volume", "volume"), ("issue", "issue")]:
            value = clean_whitespace(
                "".join(node.xpath(f".//tei:biblScope[@unit='{unit}'][1]//text()", namespaces=TEI_NS))
            )
            if value:
                fields[zotero_field] = value

        page_node = node.xpath(".//tei:biblScope[@unit='page'][1]", namespaces=TEI_NS)
        if page_node:
            start = clean_whitespace(page_node[0].get("from", ""))
            end = clean_whitespace(page_node[0].get("to", ""))
            text = clean_whitespace("".join(page_node[0].xpath(".//text()")))
            if start or end:
                fields["pages"] = "-".join(x for x in [start, end] if x)
            elif text:
                fields["pages"] = text

        if "DOI" in identifiers:
            fields["DOI"] = identifiers["DOI"]
        if "URL" in identifiers:
            fields["url"] = identifiers["URL"]
        if "ISBN" in identifiers:
            fields["ISBN"] = identifiers["ISBN"]
        if "arXiv" in identifiers:
            fields["archiveID"] = identifiers["arXiv"]
            fields["repository"] = "arXiv"

        meeting = clean_whitespace("".join(node.xpath(".//tei:meeting[1]//text()", namespaces=TEI_NS)))
        if meeting and not fields.get("conferenceName"):
            fields["conferenceName"] = meeting
        return fields, identifiers

    def _infer_item_type(self, node, identifiers: dict[str, str], fields: dict[str, Any]) -> str:
        if identifiers.get("arXiv") or clean_whitespace(str(fields.get("repository", ""))).lower() == "arxiv":
            return "preprint"
        if fields.get("ISBN") and not fields.get("publicationTitle") and not fields.get("proceedingsTitle"):
            return "book"
        if fields.get("publicationTitle"):
            return "journalArticle"
        meeting = clean_whitespace("".join(node.xpath(".//tei:meeting[1]//text()", namespaces=TEI_NS)))
        if fields.get("proceedingsTitle") or fields.get("conferenceName") or meeting:
            return "conferencePaper"
        if identifiers.get("URL") and not identifiers.get("DOI"):
            return "webpage"
        return "journalArticle"

    def _extract_raw(self, node) -> str | None:
        raw = clean_whitespace("".join(node.xpath(".//*[local-name()='note' and @type='raw_reference'][1]//text()")))
        return raw or None
