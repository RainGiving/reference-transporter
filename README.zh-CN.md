# 参考文献转运使

语言切换：[English](./README.md) | **简体中文**

[![Skill](https://img.shields.io/badge/skill-reference--transporter-0A66C2)](./SKILL.md)
[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB)](./pyproject.toml)
[![Zotero](https://img.shields.io/badge/zotero-local%20api%20%2B%20connector-CC2936)](https://www.zotero.org/)
[![DOCX](https://img.shields.io/badge/docx-zotero%20field%20sync-6A4C93)](./references/workflow.md)
[![Status](https://img.shields.io/badge/status-active-2EA44F)](./references/confidence-rules.md)

`reference-transporter` 是一个面向 Codex 和 Claude Code 的本地 skill，用来：

1. 把纯文本参考文献列表导入指定 Zotero collection，
2. 把 `.docx` 稿件中的纯文本数字编号引用替换成 Zotero Word 字段，
3. 在 AI 修改稿件后重新同步 Zotero 引文字段。

这个 skill 不再假设参考文献必须符合 GB/T 7714 或其他单一格式。

## 主要特点

- GROBID 优先解析：
  - 不再走硬编码的 GB/T 7714 解析路径
  - 不再把 `[J]`、`[C]`、`[M]`、`[EB/OL]` 当作主解析依据
- 强标识符优先：
  - DOI
  - PMID
  - arXiv ID
  - ISBN
  - URL metadata
- 多源学术元数据解析：
  - 期刊：Crossref -> PubMed -> OpenAlex
  - 会议：DBLP -> Crossref -> OpenAlex
  - 预印本：arXiv -> Crossref
  - 网页：URL metadata
- 只自动接受高置信命中
- 找不到高置信元数据时回退到文本解析条目
- 自动输出 `failure_ref.txt` 供人工复核
- `.docx` 替换按 run 级进行，尽量保留上标格式
- 默认优先继承样式：
  - 如果输入 docx 已有 Zotero 文档属性，优先继承其 `styleID` 和 `locale`
  - 否则继承本机 Zotero 当前样式设置
  - 只有用户显式传 `--style-id` 或 `--locale` 时才覆盖

## 一句话安装

### 给 Codex 的一句话

把下面这句话直接发给 Codex：

```text
Clone https://github.com/RainGiving/reference-transporter.git into ~/.codex/skills/reference-transporter, make sure the skill is discoverable as $reference-transporter, and verify that python scripts/refsync.py --help runs successfully.
```

### 给 Claude Code 的一句话

把下面这句话直接发给 Claude Code：

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

## 仓库结构

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

## 运行要求

- 本机运行中的 Zotero 7
- 本机运行中的 GROBID 服务，默认 `http://127.0.0.1:8070`
- 已启用 Zotero local API 和 connector：
  - `http://127.0.0.1:23119/api`
  - `http://127.0.0.1:23119/connector`
- Python 3.11+
- Python 包：
  - `requests`
  - `lxml`
  - `python-docx`

安装依赖：

```bash
python -m pip install requests lxml python-docx
```

Reference Transporter 现在要求本机有可用的 GROBID 服务，不再回退到 GB/T 特化本地解析。

## 命令

### 1. 文本参考文献列表 -> Zotero

```bash
python scripts/refsync.py import-refs \
  --refs /abs/path/references.txt \
  --collection "master degree"
```

### 2. `.docx` 稿件 -> Zotero 字段稿件

```bash
python scripts/refsync.py tag-manuscript \
  --input /abs/path/draft.docx \
  --collection "master degree"
```

### 3. AI 修改稿件 -> 重建 Zotero 字段

```bash
python scripts/refsync.py sync-manuscript \
  --input /abs/path/revised.docx \
  --collection "master degree"
```

如果你想显式覆盖样式：

```bash
python scripts/refsync.py tag-manuscript \
  --input /abs/path/draft.docx \
  --collection "master degree" \
  --style-id "http://www.zotero.org/styles/ieee" \
  --locale "en-US"
```

## 输出

- `*_report.json`
  - 参考文献编号
  - 解析结果
  - 元数据来源
  - 置信分数
  - 最终 Zotero item key
- `*failure_ref.txt`
  - 所有未获得高置信元数据的 fallback 条目
- `*_zotero.docx` / `*_zotero_synced.docx`
  - 已经替换成 Zotero Word 字段的稿件

## 当前边界

- 不自动找 PDF
- 不自动把手工参考文献区替换成 Zotero bibliography 字段
- 当前版本不强制清理 Zotero collection 中的重复条目
