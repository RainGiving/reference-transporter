# Workflow

## 1. import-refs

1. Read the plain-text reference file.
2. Split references into normalized blocks.
3. Parse each reference into:
   - number
   - authors
   - title
   - type code
   - basic fields
4. Extract identifiers:
   - DOI
   - PMID
   - arXiv ID
   - ISBN
   - URL
5. Resolve metadata with source-specific priority.
6. Accept only high-confidence matches.
7. Fallback to text-parsed Zotero item if no high-confidence source exists.
8. Import into the requested Zotero collection.
9. Write report and `failure_ref.txt`.

## 2. tag-manuscript

1. Read the DOCX manuscript.
2. Find the `参考文献` heading.
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
   - JSON report
   - `failure_ref.txt`

## 3. sync-manuscript

1. Read the revised DOCX.
2. Strip existing Zotero citation fields back to their visible numeric text.
3. Re-extract the current reference list.
4. Re-resolve/import references.
5. Rebuild in-text Zotero citation fields from the revised manuscript state.
6. Output a new synced DOCX and updated reports.
