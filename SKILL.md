---
name: reference-transporter
description: Import plain-text reference lists into Zotero with identifier-first metadata resolution, convert numeric text citations in DOCX manuscripts into Zotero Word fields, and resync revised manuscripts after AI edits. Use this skill when the user has a reference list, a manuscript with plain numeric citations, or a revised DOCX that needs Zotero citation synchronization.
---

# Reference Transporter

Use this skill when:

- a user has a plain-text reference list and wants it imported into a Zotero collection,
- a DOCX manuscript contains visible numeric citations like `[12]` instead of Zotero fields,
- or an AI-revised manuscript needs Zotero citation field synchronization rebuilt.

This skill does not assume that references follow GB/T 7714 or any other single citation format.

## Preconditions

- Zotero is running locally
- A local GROBID service is required
- Zotero local API and connector are available:
  - `http://127.0.0.1:23119/api`
  - `http://127.0.0.1:23119/connector`
- Python is available with:
  - `requests`
  - `lxml`
  - `python-docx`

## Primary Entrypoint

Always prefer:

```bash
python scripts/refsync.py <subcommand> ...
```

## Commands

### 1. `import-refs`

Input: a plain-text reference list and a Zotero collection  
Output: imported references, JSON report, `failure_ref.txt`

```bash
python scripts/refsync.py import-refs \
  --refs /abs/path/references.txt \
  --collection "master degree"
```

### 2. `tag-manuscript`

Input: a DOCX manuscript with a visible reference section  
Output: a new DOCX whose visible numeric citations are replaced with Zotero Word fields

```bash
python scripts/refsync.py tag-manuscript \
  --input /abs/path/draft.docx \
  --collection "master degree"
```

### 3. `sync-manuscript`

Input: an AI-revised DOCX manuscript  
Output: a new DOCX with rebuilt Zotero citation fields based on the revised manuscript state

```bash
python scripts/refsync.py sync-manuscript \
  --input /abs/path/revised.docx \
  --collection "master degree"
```

## Style Behavior

Style inheritance is the default behavior.

Priority order:

1. If the user explicitly passes `--style-id` or `--locale`, use those values.
2. Otherwise, if the input DOCX already has Zotero document properties, inherit its `styleID` and `locale`.
3. Otherwise, inherit the current local Zotero style settings from the active profile.

Do not force a hard-coded citation style unless the user explicitly asks for one.

## Resolution Rules

- Use GROBID as the primary reference parser.
- Do not rely on `[J]`, `[C]`, `[M]`, `[EB/OL]`, or any GB/T-specific local parsing as the main path.
- Strong identifiers first:
  - DOI
  - PMID
  - arXiv ID
  - ISBN
  - URL metadata
- High-confidence metadata matches are imported automatically.
- Low-confidence or unresolved references must fall back to parsed text items.
- Every fallback reference must be appended to `failure_ref.txt`.

## DOCX Rules

- Replace citations at run level, not by rewriting whole paragraphs.
- Preserve superscript formatting whenever possible.
- For revised manuscripts, strip existing Zotero citation fields back to visible numeric text before rebuilding.

## References

- Workflow details: [references/workflow.md](references/workflow.md)
- Input/output contracts: [references/data-contracts.md](references/data-contracts.md)
- Metadata source and confidence rules: [references/confidence-rules.md](references/confidence-rules.md)

## Explicit Non-Goals

- No automatic PDF attachment discovery
- No automatic conversion of the manually typed reference section into a Zotero bibliography field
- No mandatory duplicate cleanup inside Zotero collections in this version
