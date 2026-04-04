# Workflow

## 1. import-refs

1. Read the plain-text reference file.
2. Split references into normalized blocks.
3. Extract strong identifiers and query signals from each raw reference string, such as:
   - DOI
   - PMID
   - arXiv ID
   - ISBN
   - URL
4. Resolve metadata with source-specific priority:
   - Crossref
   - OpenAlex
   - DBLP
   - PubMed
5. Accept only high-confidence matches.
6. Import matched references into the requested Zotero collection.
7. Write `failure_ref.txt` for low-confidence or unresolved references.

## 2. tag-manuscript

1. Read the DOCX manuscript.
2. Find a reference heading such as `参考文献`, `Reference`, `References`, or `Bibliography`.
3. Extract numbered references after that heading.
4. Run the same import pipeline as `import-refs`.
5. Replace in-text numeric citations such as `[1]`, `[4,5]`, `[8-10]` with Zotero fields.
6. Preserve superscript and local run formatting.
7. Resolve citation style by priority:
   - explicit CLI override,
   - existing Zotero document properties in the input DOCX,
   - current local Zotero style settings.
8. Write DOCX-level Zotero properties for later refresh in Word.
8. Output:
   - tagged DOCX
   - `failure_ref.txt`

## 3. sync-manuscript

1. Read the revised DOCX.
2. Strip existing Zotero citation fields back to their visible numeric text.
3. Re-extract the current reference list.
4. Re-resolve/import references.
5. Rebuild in-text Zotero citation fields from the revised manuscript state.
6. Output a new synced DOCX and `failure_ref.txt`.
