# 参考文献转运使

语言切换：[English](./README.md) | **简体中文**

[![Skill](https://img.shields.io/badge/skill-reference--transporter-0A66C2)](./SKILL.md)
[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB)](./pyproject.toml)
[![Zotero](https://img.shields.io/badge/zotero-local%20api%20%2B%20connector-CC2936)](https://www.zotero.org/)
[![GROBID](https://img.shields.io/badge/grobid-required-4B8BBE)](https://github.com/kermitt2/grobid)
[![Status](https://img.shields.io/badge/status-active-2EA44F)](./references/workflow.md)

Reference Transporter 用来把参考文献列表导入 Zotero，并把 DOCX 稿件中可见的数字编号引用替换成 Zotero Word 字段。它以 **GROBID 作为主解析器**，**不预设输入参考文献必须符合 GB/T 7714 或任何单一格式**。

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

### 1. 文本参考文献列表 -> Zotero

```bash
python scripts/refsync.py import-refs \
  --refs /abs/path/references.txt \
  --collection "master degree"
```

### 2. DOCX 稿件 -> Zotero 字段稿件

```bash
python scripts/refsync.py tag-manuscript \
  --input /abs/path/draft.docx \
  --collection "master degree"
```

### 3. AI 修改后的 DOCX -> 重新同步

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

## 运行要求

- 本机运行中的 Zotero 7
- 已启用 Zotero local API 和 connector：
  - `http://127.0.0.1:23119/api`
  - `http://127.0.0.1:23119/connector`
- 本机运行中的 GROBID 服务：`http://127.0.0.1:8070`
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

- GROBID 优先解析参考文献字符串
- 强标识符优先元数据解析：
  - DOI
  - PMID
  - arXiv ID
  - ISBN
  - URL metadata
- 多源学术元数据检索：
  - 期刊：Crossref -> PubMed -> OpenAlex
  - 会议：DBLP -> Crossref -> OpenAlex
  - 预印本：arXiv -> Crossref
  - 网页：URL metadata
- 高置信命中才自动导入
- 没有高置信元数据的条目输出到 `failure_ref.txt`
- `.docx` 引文替换按 run 级进行，尽量保留上标格式
- 默认样式继承：
  - 优先继承输入 DOCX 的 Zotero 文档属性
  - 否则继承本机 Zotero 当前样式设置
  - 只有用户显式传 `--style-id` / `--locale` 才覆盖

## 输出

- `*_report.json`
  - 参考文献编号
  - 元数据来源
  - 置信分数
  - 最终 Zotero item key
- `*failure_ref.txt`
  - 所有未获得高置信元数据的 fallback 条目
- `*_zotero.docx` / `*_zotero_synced.docx`
  - 已替换成 Zotero Word 字段的稿件

## 当前边界

- 不自动找 PDF
- 不自动把手工参考文献区替换成 Zotero bibliography 字段
- 当前版本不强制清理 Zotero collection 中的重复条目
