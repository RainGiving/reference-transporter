# Data Contracts

## Reference Text File Input

The parser does not assume a specific house style such as GB/T 7714. Metadata resolution is driven by strong identifiers and remote scholarly search.

Accepted forms:

1. Each reference on its own line:

```text
[1] Luscombe N M, Greenbaum D, Gerstein M. What is bioinformatics? ...
[2] International Human Genome Sequencing Consortium. Finishing ...
```

2. Numbered lines without square brackets are also accepted:

```text
1. Luscombe N M, Greenbaum D, Gerstein M. What is bioinformatics? ...
2) International Human Genome Sequencing Consortium. Finishing ...
3、 Another reference ...
4 Another reference ...
```

3. Blank-line separated blocks:

```text
[1] Luscombe N M, Greenbaum D, Gerstein M. What is bioinformatics? ...

[2] International Human Genome Sequencing Consortium. Finishing ...
```

4. Unnumbered lines:

```text
Luscombe N M, Greenbaum D, Gerstein M. What is bioinformatics? ...
International Human Genome Sequencing Consortium. Finishing ...
```

When unnumbered, numbering is assigned sequentially.

## DOCX Input Assumptions

- There is a visible reference heading such as:
  - `参考文献`
  - `Reference`
  - `References`
  - `Bibliography`
- References after that heading are numbered
- In-text citations are visible numeric tokens such as:
  - `[1]`
  - `[12,13]`
  - `[14-16]`

## failure_ref.txt Output

Each fallback reference records:

- visible number
- original reference string
- failure reason
- Zotero item key
