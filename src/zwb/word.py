from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from lxml import etree

from .models import CitationItemSpec, CitationSpec
from .utils import chunk_string, random_id

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CP_NS = "http://schemas.openxmlformats.org/officeDocument/2006/custom-properties"
VT_NS = "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"

CUSTOM_FMTID = "{D5CDD505-2E9C-101B-9397-08002B2CF9AE}"
CUSTOM_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/custom-properties"
CUSTOM_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.custom-properties+xml"


@dataclass(slots=True)
class InjectionConfig:
    style_id: str
    locale: str
    note_type: int
    citations: dict[str, CitationSpec]
    bibliography_placeholders: list[str]


def load_manifest(path: str | Path) -> InjectionConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    citations: dict[str, CitationSpec] = {}
    for placeholder, spec in raw.get("citations", {}).items():
        items = [
            CitationItemSpec(
                key=item["key"],
                locator=item.get("locator"),
                label=item.get("label"),
                prefix=item.get("prefix"),
                suffix=item.get("suffix"),
                suppress_author=bool(item.get("suppress_author", False)),
                author_only=bool(item.get("author_only", False)),
            )
            for item in spec.get("items", [])
        ]
        citations[placeholder] = CitationSpec(
            placeholder=placeholder,
            items=items,
            preview_text=spec.get("preview_text"),
            note_index=int(spec.get("note_index", 0)),
        )
    return InjectionConfig(
        style_id=raw["style_id"],
        locale=raw.get("locale", "en-US"),
        note_type=int(raw.get("note_type", 0)),
        citations=citations,
        bibliography_placeholders=raw.get("bibliography_placeholders", ["[[BIBLIOGRAPHY]]"]),
    )


class WordZoteroInjector:
    def __init__(self, zotero_web_client, zotero_version: str = "zwb-0.1") -> None:
        self.zotero_web_client = zotero_web_client
        self.zotero_version = zotero_version

    def inject(self, input_docx: str | Path, output_docx: str | Path, manifest: InjectionConfig) -> None:
        input_path = Path(input_docx)
        output_path = Path(output_docx)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        citation_replacements = {
            placeholder: self._build_citation_replacement(spec)
            for placeholder, spec in manifest.citations.items()
        }
        bibliography_replacements = {
            placeholder: self._build_bibliography_replacement()
            for placeholder in manifest.bibliography_placeholders
        }

        with ZipFile(input_path, "r") as source:
            files = {name: source.read(name) for name in source.namelist()}

        for part_name in ["word/document.xml", "word/footnotes.xml", "word/endnotes.xml"]:
            if part_name in files:
                files[part_name] = self._replace_in_xml(
                    files[part_name],
                    {**citation_replacements, **bibliography_replacements},
                )

        document_data = self._build_document_data(
            style_id=manifest.style_id,
            locale=manifest.locale,
            note_type=manifest.note_type,
        )
        files = self._upsert_custom_properties(files, document_data)

        with ZipFile(output_path, "w", compression=ZIP_DEFLATED) as target:
            for name, data in files.items():
                target.writestr(name, data)

    def _build_citation_replacement(self, spec: CitationSpec) -> dict:
        citation_items = []
        preview_parts = []
        for item_spec in spec.items:
            item_data = self.zotero_web_client.fetch_csljson(item_spec.key)
            citation_item = {
                "uris": [self.zotero_web_client.build_item_uri(item_spec.key)],
                "itemData": item_data,
            }
            if item_spec.locator:
                citation_item["locator"] = item_spec.locator
            if item_spec.label:
                citation_item["label"] = item_spec.label
            if item_spec.prefix:
                citation_item["prefix"] = item_spec.prefix
            if item_spec.suffix:
                citation_item["suffix"] = item_spec.suffix
            if item_spec.suppress_author:
                citation_item["suppress-author"] = True
            if item_spec.author_only:
                citation_item["author-only"] = True
            citation_items.append(citation_item)
            preview_parts.append(self._preview_from_csl(item_data))

        code_payload = {
            "citationID": random_id(),
            "properties": {"noteIndex": spec.note_index},
            "citationItems": citation_items,
            "schema": "https://github.com/citation-style-language/schema/raw/master/csl-citation.json",
        }
        preview_text = spec.preview_text or "(" + "; ".join(preview_parts) + ")"
        field_code = f" ADDIN ZOTERO_ITEM CSL_CITATION {json.dumps(code_payload, ensure_ascii=False)} "
        return {"type": "citation", "field_code": field_code, "preview_text": preview_text}

    @staticmethod
    def _build_bibliography_replacement() -> dict:
        payload = {"uncited": [], "omitted": [], "custom": []}
        field_code = f" ADDIN ZOTERO_BIBL {json.dumps(payload, ensure_ascii=False)} CSL_BIBLIOGRAPHY "
        preview_text = "Bibliography will be generated by Zotero after Refresh."
        return {"type": "bibliography", "field_code": field_code, "preview_text": preview_text}

    def _build_document_data(self, style_id: str, locale: str, note_type: int) -> str:
        payload = {
            "style": {
                "styleID": style_id,
                "locale": locale,
                "hasBibliography": True,
                "bibliographyStyleHasBeenSet": True,
            },
            "prefs": {
                "fieldType": "Field",
                "automaticJournalAbbreviations": False,
                "noteType": note_type,
            },
            "sessionID": random_id(10),
            "zoteroVersion": self.zotero_version,
            "dataVersion": 4,
        }
        return json.dumps(payload, ensure_ascii=False)

    def _replace_in_xml(self, xml_bytes: bytes, replacements: dict[str, dict]) -> bytes:
        parser = etree.XMLParser(remove_blank_text=False)
        root = etree.fromstring(xml_bytes, parser=parser)
        paragraphs = root.xpath(".//w:p", namespaces={"w": W_NS})
        for paragraph in paragraphs:
            text = "".join(paragraph.xpath(".//w:t/text()", namespaces={"w": W_NS}))
            if not text:
                continue
            if not any(placeholder in text for placeholder in replacements):
                continue
            self._rewrite_paragraph(paragraph, text, replacements)
        return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone="yes")

    def _rewrite_paragraph(self, paragraph, text: str, replacements: dict[str, dict]) -> None:
        ppr = paragraph.find(f"{{{W_NS}}}pPr")
        new_children = [deepcopy(ppr)] if ppr is not None else []
        cursor = 0

        while cursor < len(text):
            next_hit = None
            for placeholder, replacement in replacements.items():
                index = text.find(placeholder, cursor)
                if index == -1:
                    continue
                if next_hit is None or index < next_hit[0]:
                    next_hit = (index, placeholder, replacement)
            if next_hit is None:
                tail = text[cursor:]
                if tail:
                    new_children.append(self._text_run(tail))
                break

            index, placeholder, replacement = next_hit
            if index > cursor:
                new_children.append(self._text_run(text[cursor:index]))
            new_children.extend(self._field_runs(replacement["field_code"], replacement["preview_text"]))
            cursor = index + len(placeholder)

        for child in list(paragraph):
            paragraph.remove(child)
        for child in new_children:
            paragraph.append(child)

    @staticmethod
    def _text_run(value: str):
        run = etree.Element(f"{{{W_NS}}}r")
        text = etree.SubElement(run, f"{{{W_NS}}}t")
        if value[:1].isspace() or value[-1:].isspace():
            text.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        text.text = value
        return run

    @staticmethod
    def _field_runs(field_code: str, preview_text: str):
        begin_run = etree.Element(f"{{{W_NS}}}r")
        etree.SubElement(begin_run, f"{{{W_NS}}}fldChar", attrib={f"{{{W_NS}}}fldCharType": "begin"})

        instr_run = etree.Element(f"{{{W_NS}}}r")
        instr = etree.SubElement(instr_run, f"{{{W_NS}}}instrText")
        instr.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        instr.text = field_code

        separate_run = etree.Element(f"{{{W_NS}}}r")
        etree.SubElement(separate_run, f"{{{W_NS}}}fldChar", attrib={f"{{{W_NS}}}fldCharType": "separate"})

        text_run = etree.Element(f"{{{W_NS}}}r")
        t = etree.SubElement(text_run, f"{{{W_NS}}}t")
        t.text = preview_text

        end_run = etree.Element(f"{{{W_NS}}}r")
        etree.SubElement(end_run, f"{{{W_NS}}}fldChar", attrib={f"{{{W_NS}}}fldCharType": "end"})
        return [begin_run, instr_run, separate_run, text_run, end_run]

    def _upsert_custom_properties(self, files: dict[str, bytes], document_data: str) -> dict[str, bytes]:
        custom_xml = files.get("docProps/custom.xml")
        if custom_xml:
            root = etree.fromstring(custom_xml)
        else:
            root = etree.Element(f"{{{CP_NS}}}Properties", nsmap={None: CP_NS, "vt": VT_NS})

        for prop in root.findall(f"{{{CP_NS}}}property"):
            name = prop.get("name", "")
            if name.startswith("ZOTERO_PREF_"):
                root.remove(prop)

        chunks = chunk_string(document_data, 255)
        existing_pids = [int(prop.get("pid", "1")) for prop in root.findall(f"{{{CP_NS}}}property")]
        next_pid = max(existing_pids, default=1) + 1
        for index, chunk in enumerate(chunks, start=1):
            prop = etree.SubElement(
                root,
                f"{{{CP_NS}}}property",
                attrib={
                    "fmtid": CUSTOM_FMTID,
                    "pid": str(next_pid),
                    "name": f"ZOTERO_PREF_{index}",
                },
            )
            value = etree.SubElement(prop, f"{{{VT_NS}}}lpwstr")
            value.text = chunk
            next_pid += 1

        files["docProps/custom.xml"] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone="yes")
        files["[Content_Types].xml"] = self._ensure_content_type(files["[Content_Types].xml"])
        files["_rels/.rels"] = self._ensure_root_relationship(files["_rels/.rels"])
        return files

    @staticmethod
    def _ensure_content_type(content_types_xml: bytes) -> bytes:
        root = etree.fromstring(content_types_xml)
        exists = root.xpath("/*/*[local-name()='Override' and @PartName='/docProps/custom.xml']")
        if not exists:
            etree.SubElement(
                root,
                "Override",
                PartName="/docProps/custom.xml",
                ContentType=CUSTOM_CONTENT_TYPE,
            )
        return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone="yes")

    @staticmethod
    def _ensure_root_relationship(rels_xml: bytes) -> bytes:
        root = etree.fromstring(rels_xml)
        exists = root.xpath(
            "/*/*[local-name()='Relationship' and @Type=$rel_type]",
            rel_type=CUSTOM_REL_TYPE,
        )
        if not exists:
            rel_ids = {
                int(rel.get("Id", "rId0").replace("rId", ""))
                for rel in root.xpath("/*/*[local-name()='Relationship']")
                if rel.get("Id", "").startswith("rId") and rel.get("Id", "")[3:].isdigit()
            }
            next_id = max(rel_ids, default=0) + 1
            etree.SubElement(
                root,
                f"{{{R_NS}}}Relationship",
                Id=f"rId{next_id}",
                Type=CUSTOM_REL_TYPE,
                Target="docProps/custom.xml",
            )
        return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone="yes")

    @staticmethod
    def _preview_from_csl(item_data: dict) -> str:
        authors = item_data.get("author") or []
        if authors:
            if len(authors) == 1:
                author_text = authors[0].get("family") or authors[0].get("literal") or "Unknown"
            elif len(authors) == 2:
                left = authors[0].get("family") or authors[0].get("literal") or "Unknown"
                right = authors[1].get("family") or authors[1].get("literal") or "Unknown"
                author_text = f"{left} & {right}"
            else:
                author_text = (authors[0].get("family") or authors[0].get("literal") or "Unknown") + " et al."
        else:
            author_text = "Unknown"
        year = "n.d."
        issued = item_data.get("issued", {}).get("date-parts", [])
        if issued and issued[0]:
            year = str(issued[0][0])
        return f"{author_text}, {year}"
