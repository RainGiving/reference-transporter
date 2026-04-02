# Data Contracts

## Reference Text File Input

Accepted forms:

1. Each reference on its own line:

```text
[1] Luscombe N M, Greenbaum D, Gerstein M. What is bioinformatics? ...
[2] International Human Genome Sequencing Consortium. Finishing ...
```

2. Blank-line separated blocks:

```text
[1] Luscombe N M, Greenbaum D, Gerstein M. What is bioinformatics? ...

[2] International Human Genome Sequencing Consortium. Finishing ...
```

3. Unnumbered lines:

```text
Luscombe N M, Greenbaum D, Gerstein M. What is bioinformatics? ...
International Human Genome Sequencing Consortium. Finishing ...
```

When unnumbered, numbering is assigned sequentially.

## DOCX Input Assumptions

- There is a visible heading `参考文献`
- References after that heading are numbered
- In-text citations are visible numeric tokens such as:
  - `[1]`
  - `[12,13]`
  - `[14-16]`

## JSON Report Output

Each reference record includes at least:

- `number`
- `raw`
- `title`
- `item_type`
- `creators`
- `fields`
- `item_key`
- `resolution_source`
- `resolution_score`
- `used_fallback`
- `failure_reason`
- `created_new_item`

## failure_ref.txt Output

Each fallback reference records:

- visible number
- original reference string
- failure reason
- Zotero item key
