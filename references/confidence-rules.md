# Confidence Rules

## Strong Identifier Priority

Resolve in this order when available:

1. DOI
2. PMID
3. arXiv ID
4. ISBN
5. URL metadata

## Search Order by Reference Type

### Journal Articles

- Crossref
- PubMed
- OpenAlex

### Conference Papers

- DBLP
- Crossref
- OpenAlex

### Preprints

- arXiv
- Crossref

### Webpages

- URL metadata

## Acceptance Rule

Only accept a metadata candidate automatically when the score is above the high-confidence threshold.

Scoring factors:

- title similarity
- year match
- first-author match
- journal/proceedings container match
- presence of a strong identifier

If no candidate reaches threshold:

- import a fallback text-parsed Zotero item
- append the reference to `failure_ref.txt`

## Merge Rule

When a high-confidence metadata record is available:

- use it as the primary source of truth
- keep any parsed fields that the source does not provide
- never reduce metadata richness by overwriting a filled field with an empty field
