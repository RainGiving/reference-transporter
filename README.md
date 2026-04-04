# Reference Transporter

Language: **English** | [简体中文](./README.zh-CN.md)

[![Skill](https://img.shields.io/badge/skill-reference--transporter-0A66C2)](./SKILL.md)
[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB)](./pyproject.toml)
[![Zotero](https://img.shields.io/badge/zotero-local%20api%20%2B%20connector-CC2936)](https://www.zotero.org/)
[![Metadata](https://img.shields.io/badge/metadata-crossref%20%2B%20openalex%20%2B%20dblp%20%2B%20pubmed-4B8BBE)](./references/workflow.md)
[![Status](https://img.shields.io/badge/status-active-2EA44F)](./references/workflow.md)

Reference Transporter imports references into Zotero and converts visible numeric citations in DOCX manuscripts into Zotero Word fields.

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

### Import a reference list into Zotero

Send this to the agent:

```text
Use $reference-transporter to import the references in /abs/path/references.txt into the Zotero collection "master degree" and write unresolved references to failure_ref.txt.
```

### Convert a DOCX manuscript with visible numeric citations

Send this to the agent:

```text
Use $reference-transporter to import the references from /abs/path/draft.docx into the Zotero collection "master degree", then replace the visible numeric citations in the manuscript with Zotero Word fields and save the result as a new DOCX.
```

### Resync a revised DOCX manuscript

Send this to the agent:

```text
Use $reference-transporter to resync Zotero citation fields in /abs/path/revised.docx against the Zotero collection "master degree", rebuilding the in-text citation markers after the manuscript changes.
```

## Runtime Requirements

- Zotero 7 running locally
- Zotero local API and connector available:
  - `http://127.0.0.1:23119/api`
  - `http://127.0.0.1:23119/connector`
- Network access to:
  - Crossref
  - OpenAlex
  - DBLP
  - PubMed
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

- Identifier-first metadata resolution:
  - DOI
  - PMID
  - arXiv ID
  - ISBN
  - URL metadata
- Query remote metadata sources directly from the raw reference string
- Multi-source academic metadata lookup:
  - Journal articles: Crossref -> PubMed -> OpenAlex
  - Conference papers: DBLP -> Crossref -> OpenAlex
  - Preprints: arXiv -> Crossref
  - Webpages: URL metadata
- Confidence-gated auto-import
- `failure_ref.txt` output for references without a high-confidence metadata match
- Run-level DOCX citation replacement that preserves superscript formatting
- Reference section headings can be Chinese or English, including `参考文献`, `Reference`, `References`, and `Bibliography`
- Style inheritance by default:
  - inherit from the input DOCX if Zotero document properties already exist
  - otherwise inherit from the current local Zotero style settings
  - only override when the user explicitly passes `--style-id` or `--locale`

## Outputs

- `failure_ref.txt`
  - all references that did not get a high-confidence metadata match
- `*_zotero.docx` / `*_zotero_synced.docx`
  - manuscripts whose visible numeric citations were replaced with Zotero Word fields

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
