from __future__ import annotations

import argparse
from pathlib import Path

from .thesis_docx import (
    extract_reference_paragraphs,
    import_references_to_collection,
    load_references_from_text,
    parse_reference,
    replace_document_citations,
    write_failure_refs,
    write_report,
)

def _default_report_path(path: Path, suffix: str) -> Path:
    return path.with_name(f"{path.stem}_{suffix}.json")


def _default_output_docx(path: Path, suffix: str) -> Path:
    return path.with_name(f"{path.stem}_{suffix}.docx")


def _default_failure_path(path: Path) -> Path:
    return path.with_name(f"{path.stem}_failure_ref.txt")


def import_refs(refs_path: Path, collection: str, report: Path, failure: Path) -> None:
    references = [parse_reference(raw) for raw in load_references_from_text(refs_path)]
    references = import_references_to_collection(references, collection_name=collection)
    write_report(references, report)
    write_failure_refs(references, failure)


def tag_manuscript(input_docx: Path, collection: str, output_docx: Path, report: Path, failure: Path, style_id: str | None, locale: str | None) -> None:
    references = [parse_reference(raw) for raw in extract_reference_paragraphs(input_docx)]
    references = import_references_to_collection(references, collection_name=collection)
    replace_document_citations(input_docx, output_docx, references, style_id=style_id, locale=locale)
    write_report(references, report)
    write_failure_refs(references, failure)


def sync_manuscript(input_docx: Path, collection: str, output_docx: Path, report: Path, failure: Path, style_id: str | None, locale: str | None, previous_report: Path | None) -> None:
    _ = previous_report
    tag_manuscript(input_docx, collection, output_docx, report, failure, style_id, locale)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="reference-transporter", description="Reference Transporter CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    import_refs_parser = sub.add_parser("import-refs", help="Import a plain-text reference list into a Zotero collection")
    import_refs_parser.add_argument("--refs", required=True, type=Path)
    import_refs_parser.add_argument("--collection", required=True)
    import_refs_parser.add_argument("--report", type=Path)
    import_refs_parser.add_argument("--failure", type=Path)

    tag_parser = sub.add_parser("tag-manuscript", help="Import manuscript references and replace plain-text numeric citations with Zotero fields")
    tag_parser.add_argument("--input", required=True, type=Path)
    tag_parser.add_argument("--collection", required=True)
    tag_parser.add_argument("--output", type=Path)
    tag_parser.add_argument("--report", type=Path)
    tag_parser.add_argument("--failure", type=Path)
    tag_parser.add_argument("--style-id")
    tag_parser.add_argument("--locale")

    sync_parser = sub.add_parser("sync-manuscript", help="Rebuild Zotero citation fields for a revised manuscript")
    sync_parser.add_argument("--input", required=True, type=Path)
    sync_parser.add_argument("--collection", required=True)
    sync_parser.add_argument("--output", type=Path)
    sync_parser.add_argument("--report", type=Path)
    sync_parser.add_argument("--failure", type=Path)
    sync_parser.add_argument("--style-id")
    sync_parser.add_argument("--locale")
    sync_parser.add_argument("--previous-report", type=Path)

    return parser


def main() -> None:
    args = build_parser().parse_args()

    if args.command == "import-refs":
        report = args.report or _default_report_path(args.refs, "import_report")
        failure = args.failure or _default_failure_path(args.refs)
        import_refs(args.refs, args.collection, report, failure)
        return

    if args.command == "tag-manuscript":
        output = args.output or _default_output_docx(args.input, "zotero")
        report = args.report or _default_report_path(args.input, "zotero_report")
        failure = args.failure or _default_failure_path(args.input)
        tag_manuscript(args.input, args.collection, output, report, failure, args.style_id, args.locale)
        return

    if args.command == "sync-manuscript":
        output = args.output or _default_output_docx(args.input, "zotero_synced")
        report = args.report or _default_report_path(args.input, "zotero_sync_report")
        failure = args.failure or _default_failure_path(args.input)
        sync_manuscript(args.input, args.collection, output, report, failure, args.style_id, args.locale, args.previous_report)
        return


if __name__ == "__main__":
    main()
