# Sentence-aware chunk boundaries (patch 0014; PRD ING-11, GRD-4)

Chunks are now cut at sentence ends and at every confident heading, instead of at a fixed token count.
Setting: `CHUNK_STRATEGY=sentence` (default) or `token` (the pre-0014 fixed windows, kept unchanged).
**It takes effect only when a document is re-ingested.** Documents already in the index are untouched.

## Why
Measured on the 27 text-layer policy PDFs with the real extractor and chunker (byte-level stand-in tokenizer,
so treat the absolute numbers as approximate):

| | token (before) | sentence (0014) |
|---|---|---|
| Chunks start mid-sentence | 86% | 1% (list items only) |
| Chunks straddle a confident heading | 56% | 12% |
| Seven indexed policies: mid-sentence / straddle | 90% / 60% | 0% / 7% |
| Seven indexed policies: chunk count | 70 | 97 |
| Median chunk size (tokens) | ~400 | ~250 |

Every non-space character of every policy is still in at least one chunk (checked on all 27).

## Rules (`ingest/chunking.py`)
1. A chunk's text is an exact slice of the document, and never longer than `CHUNK_SIZE_TOKENS` (exact count).
2. Cut points: sentence ends, list items (including inline bullets), and **every confident heading**
   (the 0013 rule). Because of the heading cuts, the heading label now covers the whole chunk.
3. A period after an abbreviation ("Dr.", "e.g.", "No."), an initial ("J. Smith") or a list number ("1.") is not a
   sentence end. When unsure it does not cut, which only makes a unit longer.
4. Overlap is whole trailing sentences, at most `CHUNK_OVERLAP_TOKENS`, and **never reaches back across a heading**.
5. A section under 1/10 of a chunk (a heading with almost nothing under it, such as a heading directly above another
   heading) joins the section after it. That is the remaining 7% that straddle a heading. The label is the first heading.
6. A run with no sentence end (flattened table, long bullet list) is cut at lines, then words. Only a single word
   longer than a whole chunk falls back to fixed token windows.
7. The conflict-of-interest chunk-size override in `ingest/service.py` is unchanged.

## What 0014 does NOT do
- **Broken words** ("fr om", "thei r", "wh o", "fina l") come from the PDF reader (`pypdf`), not the chunker, and
  are still there. See "Broken words" below: the recommended fix is a different reader, not text repair.
- Tables (the Annual Leave accrual table is still flattened) and bold-only headings (Volunteer Manual).

## Before re-ingesting (no keys needed; use the real tokenizer)
    askbpl-provenance-report "path/to/Policy.pdf" ... --strategy token
    askbpl-provenance-report "path/to/Policy.pdf" ...
The last two lines of each report give mid-sentence starts and heading straddles for that strategy. Read the
chunks it lists: each should start at a sentence or heading, and each heading should be the right one.

## Re-ingest and evaluate (needs your keys)
1. Re-ingest the seven text PDFs (see `docs/PROVENANCE.md`; eligibility and dispositions are kept).
2. Run the live evaluation with `--repeat 3`. **This changes what the model sees and what retrieval scores**, so it
   is unproven until that run. Chunks are smaller (median ~250 vs ~400 tokens) and there are about 40% more, while
   `PINECONE_TOP_K` is still 6 and the grounding thresholds (0.40 / 0.45) were tuned on the old chunks. Watch:
   refusal counts (more `weak_evidence` or `absent_source` would mean scores fell below the thresholds),
   answers that lose a second half (top-k too small for smaller chunks), and citations verified.
   Do not change `PINECONE_TOP_K` or the thresholds in the same run; change one thing at a time.
3. Record the commit hash and results (BASE-8, AC-10).

## Rollback
Set `CHUNK_STRATEGY=token` and re-ingest. Nothing else needs to change.

## Broken words
Chunk boundaries do not fix words that the PDF reader breaks ("overal l", "T o p r o m o t e"). A text-repair rule was
tried and rejected (it turned the real phrase "voice mail" into "voicemail"). Patch 0015 adds an opt-in second reader
instead, with a read-only comparison tool: see `docs/PDF_READER.md`. The default reader is unchanged.
