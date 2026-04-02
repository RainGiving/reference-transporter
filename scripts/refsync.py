from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from zwb.thesis_docx import (  # noqa: E402
    import_references_to_collection,
    load_references_from_text,
    parse_reference,
    replace_document_citations,
    extract_reference_paragraphs,
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
    raw_references = load_references_from_text(refs_path)
    references = [parse_reference(raw) for raw in raw_references]
    references = import_references_to_collection(references, collection_name=collection)
    write_report(references, report)
    write_failure_refs(references, failure)
    print(f"Imported {len(references)} references into collection '{collection}'")
    print(f"Report: {report}")
    print(f"Failure refs: {failure}")


def tag_manuscript(input_docx: Path, collection: str, output_docx: Path, report: Path, failure: Path, style_id: str | None, locale: str | None) -> None:
    raw_references = extract_reference_paragraphs(input_docx)
    references = [parse_reference(raw) for raw in raw_references]
    references = import_references_to_collection(references, collection_name=collection)
    replace_document_citations(input_docx, output_docx, references, style_id=style_id, locale=locale)
    write_report(references, report)
    write_failure_refs(references, failure)
    print(f"Tagged manuscript: {output_docx}")
    print(f"Report: {report}")
    print(f"Failure refs: {failure}")


def sync_manuscript(input_docx: Path, collection: str, output_docx: Path, report: Path, failure: Path, style_id: str | None, locale: str | None, previous_report: Path | None) -> None:
    # Current sync strategy is deterministic rebuild from the revised manuscript:
    # 1. strip any existing Zotero citation fields
    # 2. re-import/resolve current reference list
    # 3. rebuild all in-text citation fields
    # previous_report is reserved for future diff-aware reuse, but rebuild is the source of truth today
    _ = previous_report
    tag_manuscript(input_docx, collection, output_docx, report, failure, style_id, locale)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="refsync", description="Reference Transporter skill entrypoint")
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
