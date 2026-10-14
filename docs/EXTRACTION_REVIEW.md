# Validating a scanned policy before it can be indexed (extraction review)

Patch 0009. PRD: ING-3, ING-11, GATE-04. First use: Conflict of Interest (SRC-13), a scanned PDF.

## Why

A scanned PDF has no trustworthy text layer. In SRC-13 only page 1 has one (about 2,500 characters); pages 2 to 10
have none. Plain extraction would therefore index one page of a ten-page policy. OCR reads all ten pages
(about 95% mean word confidence in our test) but is not proof: one wrong word in a policy becomes a wrong answer
with a verified-looking citation. So **a person compares every page image with its text, and only that person's
signed-off text can be indexed.**

## The two keys (nothing activates by accident)

| Key | What it is | Who holds it |
|---|---|---|
| 1. Review record | `validation_record.json` + `validated_text.md`, bound by SHA-256 to the exact PDF and the exact text, with reviewer name and date. Verified again at ingest. | The reviewer (Bath) |
| 2. Inventory decision | The SRC-13 row in the source inventory workbook, edited by the team to say the extraction is validated. | The team, deliberately |

* The workbook alone cannot make the document answerable: `askbpl-apply-inventory` keeps it **blocked** unless the
  stored document carries a verified record.
* The record alone cannot either: batch ingest **refuses** a row the workbook still marks blocked.
* Even then it is only a **marked test index** document (`authority_pending`), labelled to staff, and only while
  `ALLOW_TEST_INDEX=true`. BPL authority (OD-01) is a separate question this process does not answer.
* A document whose manifest entry says `extraction_review: required` and has no record is stored as
  `review_required` and is **never** answerable, even if marked Eligible.

## Steps

Requirements on the machine that does the OCR: `brew install tesseract poppler` (macOS) and
`pip install -e '.[ocr]'` in `packages/orchestrator`.

### 1. Prepare the packet (no database, no network)

```
cd packages/orchestrator
askbpl-extraction-review prepare \
  --pdf "sample_corpus/pilot/06 - Conflict of Interest (06.14) (1) (1).pdf" \
  --source-id SRC-13
```

Run it on **the exact file the manifest ingests** (the record is bound to that file's hash). It takes a few minutes
and writes `extraction_reviews/SRC-13/`:

* `report.html`: each page image beside its text, with flags (`thin`, `low_confidence`, `empty`).
* `pages/page-NN.txt`: the text you correct. `*.ocr.txt` is the untouched machine output (never edit);
  `*.textlayer.txt` is the PDF's own text layer, for comparison.
* `review.yaml`: the form.

It will not overwrite an existing packet (your review work) unless you pass `--force`.

### 2. Review (a person, page by page)

* Compare image and text. Fix wrong words, numbers, missing lines and stray symbols in `pages/page-NN.txt`.
  Pay particular attention to negatives ("shall not"), amounts, dates, names of bodies, and numbered exceptions.
* In `review.yaml` set each page to `verified`, or `excluded` with a reason in `note` (blank page, signature
  line only, unreadable). Excluded text is not indexed.
* Fill in `reviewer` (full name), `reviewed_on` (`YYYY-MM-DD`) and set `confirmed: true`.

### 3. Finalize

```
askbpl-extraction-review finalize --dir extraction_reviews/SRC-13
```

It refuses an incomplete or inconsistent review and says exactly what is missing. On success it writes
`validated_text.md` (pages marked `## Page N`, which become the section shown on citations) and
`validation_record.json`. **This does not activate anything.**

Check it any time without a database: `askbpl-extraction-review verify --record extraction_reviews/SRC-13/validation_record.json --pdf <pdf>`.

### 4. Commit the evidence

Commit `review.yaml`, `source.json`, `validation_record.json`, `validated_text.md` and `pages/*.txt`
(page images and `report.html` are git-ignored and can be regenerated). Use `git add` with these names.

### 5. Activate (a separate, deliberate decision)

Only after Steps 1 to 4 and a team decision (record it in the decision log):

1. In the inventory workbook, SRC-13 row: set **Parse check** to `Validated by manual review (<reviewer>, <date>)`,
   **Lifecycle status** to `Authority pending` (remove "extraction blocked"), **In current pilot index** to `Yes`.
2. In `sample_corpus/corpus_manifest_pilot.yaml`, uncomment the `validated_extraction:` line under SRC-13.
3. `askbpl-ingest-batch --manifest sample_corpus/corpus_manifest_pilot.yaml`
   Expect `indexed:...06 - Conflict of Interest...:validated`. Anything starting `failed:` or `refused:` names the reason.
4. `askbpl-apply-inventory`. Expect `SRC-13:authority_pending:test_index:...` and no `warning:SRC-13` line.
5. `askbpl-eval --only BPL-CI-01 BPL-CI-02 BPL-CI-03 BPL-CI-04 BPL-CI-05 --repeat 3`. The five questions should now be
   evaluable, not BLOCKED. Then run the full set.

### Roll back

Set the SRC-13 row back to `FAIL: scanned or image-only` / `Authority pending; extraction blocked` and run
`askbpl-apply-inventory --purge-vectors`. The document is non-answerable immediately; vectors are removed.

## What changes if the PDF or the text changes later

Verification fails (`not the file that was reviewed` / `changed after the review was finalized`) and the document
cannot be ingested as validated. Re-run `prepare` for the new file and review again. A plain re-ingest of the same
document without the record sets it back to `standard` (or `review_required`), so a stale "validated" can never stay
attached to newly extracted text.

## Known limits

* The review proves a named person compared the text with the page on a date. It does not prove the policy is
  current or approved (OD-01) and does not make the text legal-grade.
* Automatic detection of scanned documents at ingest (ING-3 as a gate) is not part of this patch. Today a scanned
  document is held back by the inventory's failed parse check, or by `extraction_review: required` in the manifest.
* The OCR fallback inside normal ingest still degrades quietly to empty pages when the OCR tools are missing.
  This process does not: `prepare` stops with an explicit message.
