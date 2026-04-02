# Reference Transporter

Language: **English** | [简体中文](./README.zh-CN.md)

[![Skill](https://img.shields.io/badge/skill-reference--transporter-0A66C2)](./SKILL.md)
[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB)](./pyproject.toml)
[![Zotero](https://img.shields.io/badge/zotero-local%20api%20%2B%20connector-CC2936)](https://www.zotero.org/)
[![DOCX](https://img.shields.io/badge/docx-zotero%20field%20sync-6A4C93)](./references/workflow.md)
[![Status](https://img.shields.io/badge/status-active-2EA44F)](./references/confidence-rules.md)

Reference Transporter is a local skill for Codex and Claude Code that:

1. imports plain-text reference lists into a specified Zotero collection using identifier-first metadata resolution,
2. converts plain numeric citations in DOCX manuscripts into Zotero Word fields, and
3. rebuilds Zotero citation fields after AI-revised manuscript changes.

## Why This Skill Exists

Most AI-assisted literature workflows produce:

- a plain-text reference list,
- a DOCX manuscript with visible numeric citations such as `[12]` or `[14,15]`,
- and no Zotero-native citation objects.

This skill bridges that gap without manual Zotero re-entry.

## Features

- Identifier-first metadata resolution:
  - DOI
  - PMID
  - arXiv ID
  - ISBN
  - URL metadata
- Multi-source academic lookup:
  - Journal articles: Crossref -> PubMed -> OpenAlex
  - Conference papers: DBLP -> Crossref -> OpenAlex
  - Preprints: arXiv -> Crossref
  - Webpages: URL metadata
- Confidence-gated auto-import
- Fallback parsing when no high-confidence metadata is found
- `failure_ref.txt` output for human review
- Run-level DOCX citation replacement that preserves superscript formatting
- Style inheritance by default:
  - inherit from the input DOCX if Zotero document properties already exist
  - otherwise inherit from the current local Zotero style settings
  - only override when the user explicitly passes `--style-id` or `--locale`

## One-Line Install

### One-Line Prompt for Codex

Use this exact sentence with Codex:

```text
Clone https://github.com/RainGiving/reference-transporter.git into ~/.codex/skills/reference-transporter, make sure the skill is discoverable as $reference-transporter, and verify that python scripts/refsync.py --help runs successfully.
```

### One-Line Prompt for Claude Code

Use this exact sentence with Claude Code:

```text
Clone https://github.com/RainGiving/reference-transporter.git into ~/.claude/skills/reference-transporter, make sure the skill is discoverable as $reference-transporter, and verify that python scripts/refsync.py --help runs successfully.
```

### Codex

```bash
git clone https://github.com/RainGiving/reference-transporter.git "$HOME/.codex/skills/reference-transporter"
```

### Claude Code

```bash
git clone https://github.com/RainGiving/reference-transporter.git "$HOME/.claude/skills/reference-transporter"
```

### Windows PowerShell

```powershell
git clone https://github.com/RainGiving/reference-transporter.git "$HOME\\.codex\\skills\\reference-transporter"
git clone https://github.com/RainGiving/reference-transporter.git "$HOME\\.claude\\skills\\reference-transporter"
```

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

## Runtime Requirements

- Zotero 7 running locally
- Zotero local API and connector available:
  - `http://127.0.0.1:23119/api`
  - `http://127.0.0.1:23119/connector`
- Python 3.11+
- Python packages:
  - `requests`
  - `lxml`
  - `python-docx`

Install dependencies:

```bash
python -m pip install requests lxml python-docx
```

## Commands

### 1. Import a Plain-Text Reference List

```bash
python scripts/refsync.py import-refs \
  --refs /abs/path/references.txt \
  --collection "master degree"
```

### 2. Tag a Manuscript with Zotero Fields

```bash
python scripts/refsync.py tag-manuscript \
  --input /abs/path/draft.docx \
  --collection "master degree"
```

### 3. Sync a Revised Manuscript

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

## Outputs

- `*_report.json`
  - reference number
  - parsed fields
  - metadata source
  - confidence score
  - final Zotero item key
- `*failure_ref.txt`
  - all fallback references that did not get a high-confidence metadata match
- `*_zotero.docx` / `*_zotero_synced.docx`
  - manuscripts whose plain numeric citations were replaced with Zotero Word fields

## Important Boundaries

- PDF discovery is not included
- bibliography-field replacement for the manually typed reference section is not included
- duplicate cleanup inside Zotero collections is intentionally not enforced in this version

## Entry Points for Skill Runners

- Skill metadata: [SKILL.md](./SKILL.md)
- UI metadata: [agents/openai.yaml](./agents/openai.yaml)
- Workflow reference: [references/workflow.md](./references/workflow.md)
- Confidence and source rules: [references/confidence-rules.md](./references/confidence-rules.md)
- Data contracts: [references/data-contracts.md](./references/data-contracts.md)
