# Reference Transporter

Language: **English** | [简体中文](./README.zh-CN.md)

[![Skill](https://img.shields.io/badge/skill-reference--transporter-0A66C2)](./SKILL.md)
[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB)](./pyproject.toml)
[![Zotero](https://img.shields.io/badge/zotero-local%20api%20%2B%20connector-CC2936)](https://www.zotero.org/)
[![GROBID](https://img.shields.io/badge/grobid-required-4B8BBE)](https://github.com/kermitt2/grobid)
[![Status](https://img.shields.io/badge/status-active-2EA44F)](./references/workflow.md)

Reference Transporter imports reference lists into Zotero and converts visible numeric citations in DOCX manuscripts into Zotero Word fields. It uses **GROBID as the primary parser** and does **not** assume GB/T 7714 or any other single citation style as the input format.

## One-Line Agent Install

### Codex

Send this exact sentence to Codex:

```text
Clone https://github.com/RainGiving/reference-transporter.git into ~/.codex/skills/reference-transporter, make sure the skill is discoverable as $reference-transporter, and verify that python scripts/refsync.py --help runs successfully.
```

### Claude Code

Send this exact sentence to Claude Code:

```text
Clone https://github.com/RainGiving/reference-transporter.git into ~/.claude/skills/reference-transporter, make sure the skill is discoverable as $reference-transporter, and verify that python scripts/refsync.py --help runs successfully.
```

## Quick Usage

### 1. Import a Plain-Text Reference List into Zotero

```bash
python scripts/refsync.py import-refs \
  --refs /abs/path/references.txt \
  --collection "master degree"
```

### 2. Convert a DOCX Manuscript with Plain Numeric Citations

```bash
python scripts/refsync.py tag-manuscript \
  --input /abs/path/draft.docx \
  --collection "master degree"
```

### 3. Resync a Revised DOCX Manuscript

```bash
python scripts/refsync.py sync-manuscript \
  --input /abs/path/revised.docx \
  --collection "master degree"
```

Optional explicit style override:

```bash
python scripts/refsync.py tag-manuscript \
  --input /abs/path/draft.docx \
  --collection "master degree" \
  --style-id "http://www.zotero.org/styles/ieee" \
  --locale "en-US"
```

## Runtime Requirements

- Zotero 7 running locally
- Zotero local API and connector available:
  - `http://127.0.0.1:23119/api`
  - `http://127.0.0.1:23119/connector`
- A local GROBID service at `http://127.0.0.1:8070`
- Python 3.11+
- Python packages:
  - `requests`
  - `lxml`
  - `python-docx`

Install dependencies:

```bash
python -m pip install requests lxml python-docx
```

## Features

- GROBID-first parsing for reference strings
- Identifier-first metadata resolution:
  - DOI
  - PMID
  - arXiv ID
  - ISBN
  - URL metadata
- Multi-source academic metadata lookup:
  - Journal articles: Crossref -> PubMed -> OpenAlex
  - Conference papers: DBLP -> Crossref -> OpenAlex
  - Preprints: arXiv -> Crossref
  - Webpages: URL metadata
- Confidence-gated auto-import
- `failure_ref.txt` output for references without a high-confidence metadata match
- Run-level DOCX citation replacement that preserves superscript formatting
- Style inheritance by default:
  - inherit from the input DOCX if Zotero document properties already exist
  - otherwise inherit from the current local Zotero style settings
  - only override when the user explicitly passes `--style-id` or `--locale`

## Outputs

- `*_report.json`
  - reference number
  - metadata source
  - confidence score
  - final Zotero item key
- `*failure_ref.txt`
  - all fallback references that did not get a high-confidence metadata match
- `*_zotero.docx` / `*_zotero_synced.docx`
  - manuscripts whose plain numeric citations were replaced with Zotero Word fields

## Boundaries

- PDF discovery is not included
- bibliography-field replacement for the manually typed reference section is not included
- duplicate cleanup inside Zotero collections is not enforced in this version

## Repository Layout

```text
reference-transporter/
|-- SKILL.md
|-- README.md
|-- README.zh-CN.md
|-- agents/
|   `-- openai.yaml
|-- scripts/
|   `-- refsync.py
|-- references/
|-- examples/
`-- src/
    `-- zwb/
```

## Entry Points

- Skill metadata: [SKILL.md](./SKILL.md)
- UI metadata: [agents/openai.yaml](./agents/openai.yaml)
- Workflow reference: [references/workflow.md](./references/workflow.md)
- Confidence rules: [references/confidence-rules.md](./references/confidence-rules.md)
- Data contracts: [references/data-contracts.md](./references/data-contracts.md)
