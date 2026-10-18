# Page and heading provenance (patch 0013; PRD ING-11, GRD-4)

Every chunk can now carry a **page range** and, only where a strict rule is confident, a **section heading**.
Nothing else about a chunk changes: its text and boundaries are identical to before.

## What staff see
"p. 2", "pp. 2-3" and a heading in sources and the evidence viewer. A chunk with no confident heading shows
no heading. Rows ingested before 0013 show neither until the document is re-ingested.

## The heading rule (`ingest/provenance.py`)
Accepted: short capitalised lines ending in a colon (6 words or fewer, Title Case), short ALL-CAPS lines,
Roman-numeral headings ("I. Policy Statement"). Rejected: list lead-ins, lower-case fragments, metadata labels
("Revision Date:", "Supersedes policies:"), conjunction-led continuation lines. A wrapped ALL-CAPS heading is rejoined.
A colon line that follows an unfinished sentence (five or more words, no closing punctuation) is the wrapped tail of that sentence, not a heading (patch 0013b). Bullets, numbered items, short lines, blank lines and other headings above it do not trigger this.
Bold or large type cannot be seen in extracted text and is never inferred.

Known limits
- The label is the heading where the chunk **starts**. Under the old fixed-size chunker about 60% of chunks on the seven indexed PDFs ran across a heading; the sentence-aware chunker (0014, `docs/CHUNKING.md`) cuts at headings, so about 7% do.
- If a real heading is missed, chunks under it show the previous heading.
- Page footers such as "8 of 11" are part of the extracted text.
- Form-field and date lines can still pass as headings ("Work Address: Work Phone", "February 1999 Related Policy" were seen in policies outside the seven indexed). Not yet addressed.
- Tables are not handled (the Annual Leave accrual table is still flattened).

## Before re-ingesting (needs the real tokenizer; no keys needed)
    askbpl-provenance-report "path/to/Policy.pdf" ...
Read the headings it lists. A wrong heading is worse than none: if you see one, tighten the rule before ingesting.

## Re-ingest
1. `alembic upgrade head` (adds migration 006; old rows stay NULL).
2. Re-ingest the seven text PDFs with your usual command (needs OpenAI and Pinecone keys). Re-ingest keeps eligibility and dispositions.
3. Run the live evaluation with `--repeat 3`. The model's excerpt pack now includes headings, so this counts as a model-input change and is unproven until that run.
4. Record the commit hash and results (BASE-8).
SRC-13 (scanned) is untouched: its "## Page N" markers become page numbers, with no heading.
