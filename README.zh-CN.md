# 参考文献转运使

语言切换：[English](./README.md) | **简体中文**

[![Skill](https://img.shields.io/badge/skill-reference--transporter-0A66C2)](./SKILL.md)
[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB)](./pyproject.toml)
[![Zotero](https://img.shields.io/badge/zotero-local%20api%20%2B%20connector-CC2936)](https://www.zotero.org/)
[![Metadata](https://img.shields.io/badge/metadata-crossref%20%2B%20openalex%20%2B%20dblp%20%2B%20pubmed-4B8BBE)](./references/workflow.md)
[![Status](https://img.shields.io/badge/status-active-2EA44F)](./references/workflow.md)

Reference Transporter 用来把参考文献导入 Zotero，并把 DOCX 稿件中可见的数字编号引用替换成 Zotero Word 字段。

## 给代理的一句话安装

### Codex

把下面这句话直接发给 Codex：

```text
Clone https://github.com/RainGiving/reference-transporter.git into ~/.codex/skills/reference-transporter, make sure the skill is discoverable as $reference-transporter, and verify that python scripts/refsync.py --help runs successfully.
```

### Claude Code

把下面这句话直接发给 Claude Code：

```text
Clone https://github.com/RainGiving/reference-transporter.git into ~/.claude/skills/reference-transporter, make sure the skill is discoverable as $reference-transporter, and verify that python scripts/refsync.py --help runs successfully.
```

## 快速使用

### 把参考文献列表导入 Zotero

把下面这句话直接发给代理：

```text
Use $reference-transporter to import the references in /abs/path/references.txt into the Zotero collection "master degree" and write unresolved references to failure_ref.txt.
```

### 把带可见数字编号引用的 DOCX 转成 Zotero 字段稿件

把下面这句话直接发给代理：

```text
Use $reference-transporter to import the references from /abs/path/draft.docx into the Zotero collection "master degree", then replace the visible numeric citations in the manuscript with Zotero Word fields and save the result as a new DOCX.
```

### 重新同步修改后的 DOCX 稿件

把下面这句话直接发给代理：

```text
Use $reference-transporter to resync Zotero citation fields in /abs/path/revised.docx against the Zotero collection "master degree", rebuilding the in-text citation markers after the manuscript changes.
```

## 运行要求

- 本机运行中的 Zotero 7
- 已启用 Zotero local API 和 connector：
  - `http://127.0.0.1:23119/api`
  - `http://127.0.0.1:23119/connector`
- 可访问外部元数据检索接口：
  - Crossref
  - OpenAlex
  - DBLP
  - PubMed
- Python 3.11+
- Python 包：
  - `requests`
  - `lxml`
  - `python-docx`

安装依赖：

```bash
python -m pip install requests lxml python-docx
```

## 主要能力

- 强标识符优先元数据解析：
  - DOI
  - PMID
  - arXiv ID
  - ISBN
  - URL metadata
- 使用原始参考文献字符串直接检索远程元数据
- 多源学术元数据检索：
  - 期刊：Crossref -> PubMed -> OpenAlex
  - 会议：DBLP -> Crossref -> OpenAlex
  - 预印本：arXiv -> Crossref
  - 网页：URL metadata
- 高置信命中才自动导入
- 没有高置信元数据的条目输出到 `failure_ref.txt`
- `.docx` 引文替换按 run 级进行，尽量保留上标格式
- 支持中文和英文参考文献标题，如 `参考文献`、`Reference`、`References`、`Bibliography`
- 默认样式继承：
  - 优先继承输入 DOCX 的 Zotero 文档属性
  - 否则继承本机 Zotero 当前样式设置
  - 只有用户显式传 `--style-id` / `--locale` 才覆盖

## 输出

- `failure_ref.txt`
  - 所有未获得高置信元数据的条目
- `*_zotero.docx` / `*_zotero_synced.docx`
  - 已替换成 Zotero Word 字段的稿件
