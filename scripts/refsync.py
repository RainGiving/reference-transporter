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
    write_correction_map,
)


def _default_output_docx(path: Path, suffix: str) -> Path:
    return path.with_name(f"{path.stem}_{suffix}.docx")


def _default_failure_path(path: Path) -> Path:
    return path.with_name(f"{path.stem}_failure_ref.txt")


def _default_correction_path(path: Path) -> Path:
    return path.with_name(f"{path.stem}_item_corrections.txt")


def import_refs(refs_path: Path, collection: str, failure: Path, corrections: Path) -> None:
    raw_references = load_references_from_text(refs_path)
    references = [parse_reference(raw) for raw in raw_references]
    references = import_references_to_collection(references, collection_name=collection)
    write_failure_refs(references, failure)
    write_correction_map(references, corrections)
    print(f"Imported {len(references)} references into collection '{collection}'")
    print(f"Failure refs: {failure}")
    print(f"Correction map: {corrections}")


def tag_manuscript(input_docx: Path, collection: str, output_docx: Path, failure: Path, corrections: Path, style_id: str | None, locale: str | None) -> None:
    raw_references = extract_reference_paragraphs(input_docx)
    references = [parse_reference(raw) for raw in raw_references]
    references = import_references_to_collection(references, collection_name=collection)
    replace_document_citations(input_docx, output_docx, references, style_id=style_id, locale=locale)
    write_failure_refs(references, failure)
    write_correction_map(references, corrections)
    print(f"Tagged manuscript: {output_docx}")
    print(f"Failure refs: {failure}")
    print(f"Correction map: {corrections}")


def sync_manuscript(input_docx: Path, collection: str, output_docx: Path, failure: Path, corrections: Path, style_id: str | None, locale: str | None) -> None:
    tag_manuscript(input_docx, collection, output_docx, failure, corrections, style_id, locale)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="refsync", description="Reference Transporter skill entrypoint")
    sub = parser.add_subparsers(dest="command", required=True)

    import_refs_parser = sub.add_parser("import-refs", help="Import a plain-text reference list into a Zotero collection")
    import_refs_parser.add_argument("--refs", required=True, type=Path)
    import_refs_parser.add_argument("--collection", required=True)
    import_refs_parser.add_argument("--failure", type=Path)
    import_refs_parser.add_argument("--corrections", type=Path)

    tag_parser = sub.add_parser("tag-manuscript", help="Import manuscript references and replace plain-text numeric citations with Zotero fields")
    tag_parser.add_argument("--input", required=True, type=Path)
    tag_parser.add_argument("--collection", required=True)
    tag_parser.add_argument("--output", type=Path)
    tag_parser.add_argument("--failure", type=Path)
    tag_parser.add_argument("--corrections", type=Path)
    tag_parser.add_argument("--style-id")
    tag_parser.add_argument("--locale")

    sync_parser = sub.add_parser("sync-manuscript", help="Rebuild Zotero citation fields for a revised manuscript")
    sync_parser.add_argument("--input", required=True, type=Path)
    sync_parser.add_argument("--collection", required=True)
    sync_parser.add_argument("--output", type=Path)
    sync_parser.add_argument("--failure", type=Path)
    sync_parser.add_argument("--corrections", type=Path)
    sync_parser.add_argument("--style-id")
    sync_parser.add_argument("--locale")

    return parser


def main() -> None:
    args = build_parser().parse_args()

    if args.command == "import-refs":
        failure = args.failure or _default_failure_path(args.refs)
        corrections = args.corrections or _default_correction_path(args.refs)
        import_refs(args.refs, args.collection, failure, corrections)
        return

    if args.command == "tag-manuscript":
        output = args.output or _default_output_docx(args.input, "zotero")
        failure = args.failure or _default_failure_path(args.input)
        corrections = args.corrections or _default_correction_path(args.input)
        tag_manuscript(args.input, args.collection, output, failure, corrections, args.style_id, args.locale)
        return

    if args.command == "sync-manuscript":
        output = args.output or _default_output_docx(args.input, "zotero_synced")
        failure = args.failure or _default_failure_path(args.input)
        corrections = args.corrections or _default_correction_path(args.input)
        sync_manuscript(args.input, args.collection, output, failure, corrections, args.style_id, args.locale)
        return


if __name__ == "__main__":
    main()
