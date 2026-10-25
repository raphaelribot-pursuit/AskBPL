# Curator workflow: add, replace, supersede, validate and re-ingest a policy

Patch 0020. PRD: ING-7 (this document), ING-9 (lifecycle), ING-5 and ING-6 (versions), ING-13 (counts), NFR-6.

**Who it is for.** The person who looks after the policy collection. You do not need to write code. Every step is a
command copied from this page, and every command is checked by a test so this page cannot name one that does not exist.

**What it does not settle.** Who at BPL may approve a document, and what counts as the current version, are **open BPL
decisions** (section 8). This page says what the *system* does with each decision once it is recorded. It does not make
the decisions and it does not make any document "approved".

---

## 1. Four things to know before you touch anything

1. **Putting a file into the system does not let it answer questions.** Two separate things must be true: the
   **inventory workbook** (`sample_corpus/AskBPL_Source_Inventory_v0_1.xlsx`, sheet `Source Inventory`) says the document
   may answer, and the **database** has been told so by `askbpl-apply-inventory`. The workbook is the source of truth
   (PRD ING-2). Anything the workbook does not list is treated as *not answerable*.
2. **Today nothing is BPL-confirmed.** The seven documents that can answer are a **marked test index**: answerable only
   while `ALLOW_TEST_INDEX=true`, and labelled to staff as "not yet confirmed current by BPL". Nothing in this workflow
   changes that. Only a row with a named reviewer **and** a review date can be `Eligible`.
3. **Ingesting sends policy text to outside services** (OpenAI turns it into searchable numbers; Pinecone stores them).
   Whether BPL permits that for unconfirmed documents is an open decision (section 8). Do not ingest anything you are
   not allowed to send out.
4. **Check before and after.** `askbpl-corpus-report` shows, in plain counts, what can answer. Run it before you start
   and after every change. It never changes anything.

Every command is run from `packages/orchestrator` with the virtual environment active (see `docs/TESTER_SETUP.md`).

## 2. The life of a document (PRD ING-9)

| Stage | Where it lives in the system |
|---|---|
| Received | The file is in the corpus folder. |
| Inventoried | A row exists in the workbook with a Source ID. **Every received file needs one** (AC-1). |
| Authority pending | Workbook: Lifecycle status `Authority pending`. The default for everything. |
| Eligible | Workbook: `Eligible` **plus** a reviewer name and date in `Reviewer / date`. Without both, the system quietly treats the row as Authority pending and warns. |
| Extracted / validated | Normal PDFs: text extracted automatically. Scanned PDFs: a person's validated record is required first (section 5). |
| Indexed | `askbpl-ingest-batch` has stored its chunks and vectors. |
| Evaluated | **Not recorded anywhere yet.** The report says "not tracked" rather than guess. |
| Excluded / Superseded | Workbook: Lifecycle status starts with `Excluded` or `Superseded`. Never answerable. |

A row whose `Parse check` starts with `FAIL`, or whose lifecycle says `extraction blocked` or `Blocked`, is **blocked**
whatever else the row says. A lifecycle value the system does not recognise stops the whole run with an error; it is
never guessed.

## 3. Before you start

```
askbpl-doctor
askbpl-corpus-report
```

Keep the output. After a change you will compare against it, and it is the evidence for the baseline record and the
change log (BASE-8, BASE-9). If `askbpl-doctor` shows a **[FIX]** line, solve that first.

## 4. Recipes

### A. Add a new policy

1. **Put the file in the corpus folder** named in the manifest (`corpus_root` in `sample_corpus/corpus_manifest_pilot.yaml`).
   Allowed types: PDF, Word (`.docx`), Markdown, text.
2. **Look at how it reads (PDFs).** These two commands only read; they store nothing.
   ```
   askbpl-reader-compare "sample_corpus/pilot/<file name>.pdf"
   askbpl-provenance-report "sample_corpus/pilot/<file name>.pdf"
   ```
   `reader-compare` shows characters per page and **thin pages** (under 100 characters): a thin page is often a scan or
   an image. `provenance-report` shows the page and heading each chunk would carry. Add `--stand-in-tokenizer` to the
   second if the tokenizer cannot be downloaded (counts are then approximate). A scanned or mostly empty PDF goes to
   section 5 **before** anything else.
3. **Add a row to the workbook** (`Source Inventory` sheet): the next Source ID, the exact file name, the parse result,
   `In current pilot index` (`Yes` only if the team has decided it joins the test index), and Lifecycle status
   `Authority pending`. Leave `Reviewer / date` empty. Do not type `Eligible` unless BPL has confirmed the document and
   you can write the reviewer and the date.
4. **Add the document to the manifest** (`path`, `policy`, `title`, `version`). The `policy` value must be a `slug` in
   `config/routing_seed.yaml`. A new slug is a routing change: add it there and run `askbpl-seed`. Routing wording is
   itself an approved-configuration item, so record who approved it.
5. **Check what the workbook says.** This reads only the workbook:
   ```
   askbpl-apply-inventory --dry-run
   ```
   Your new row should read `authority_pending` (with `:test_index` if you marked it `Yes`).
6. **Ingest it.** This calls OpenAI and Pinecone and costs a small amount per document.
   ```
   askbpl-ingest-batch --manifest sample_corpus/corpus_manifest_pilot.yaml
   ```
   Read every output line. `indexed:` is good. `refused:` means the workbook says blocked or excluded. `failed:` names
   the reason.
7. **Tell the database what the workbook says.** This writes to the database.
   ```
   askbpl-apply-inventory
   ```
   Lines beginning `error:` mean nothing was changed; fix the cause (section 7) and run it again.
8. **Confirm.**
   ```
   askbpl-corpus-report --strict
   ```
   Your document should show as `answerable (test index)` if it was marked `Yes`, or `indexed, not answerable` if not.
   Exit code 0 means nothing needs reconciling.
9. **Re-run the evaluation.** A new document gives every question new candidates, so existing answers can change. Run the
   sets separately and read each result; do not tune anything from one case.
   ```
   askbpl-eval --set all --repeat 3
   askbpl-eval --set robustness --repeat 3
   ```
   Write questions for the new policy and add them to the evaluation data (a separate, reviewed change).

### B. Replace a file in place (same name, same folder)

Use this to **re-extract the same document** (for example after a reader or chunking change) or when BPL gives you a
corrected copy and the old copy should not be kept. Because a document's identity comes from its **relative path**
(upper and lower case do not matter), re-ingesting the same path replaces the old chunks and vectors; it does not make a
second document.

1. Overwrite the file, keeping its name and folder.
2. **Reset the approval yourself.** If the content changed and the row says `Eligible`, set the lifecycle back to
   `Authority pending` and clear `Reviewer / date`. **The system cannot see that the content changed.** Re-ingesting
   keeps the approval: the single-file command leaves the stored eligibility alone, and batch ingest re-applies whatever
   the workbook row says. A changed policy would stay approved on the strength of the old review.
3. `askbpl-ingest-batch --manifest ...`, then `askbpl-apply-inventory`, then `askbpl-corpus-report --strict`, as in recipe A.
4. Re-run the evaluation (A, step 9).

If BPL issues a **new version** of a policy, do not overwrite: use recipe C so the old version stays on record.

### C. Supersede (a new version replaces an older one)

The supersession rule (what makes a version current) is **not yet validated with BPL** (ING-5; section 8). Until it is,
an ambiguous or conflicting pair is **blocked for BPL to decide**, not guessed (ING-6, ING-12). Use this recipe only when
the newer version is clearly identified.

1. Add the new file and its **own new** workbook row (new Source ID, `Authority pending`).
2. On the **old** row set Lifecycle status to `Superseded` and say in the notes column which Source ID replaces it.
3. **Remove the old file from the manifest.** `askbpl-ingest-batch` refuses blocked and excluded rows but **does not
   refuse superseded ones**, so a superseded file left in the manifest would be uploaded again.
4. Find the old document's id. The report prints every stored document's full id:
   ```
   askbpl-corpus-report
   ```
   Look under `STORED DOCUMENTS` for the old row's Source ID and copy its id.
5. Ingest the new file and mark the old one replaced. This single-file command does **not** read the workbook, so the
   new document starts as not answerable.
   ```
   askbpl-ingest --path "sample_corpus/pilot/<new file>.pdf" --corpus-root sample_corpus/pilot --policy <slug> --title "<title>" --version "<version>" --supersedes <old document id>
   ```
   `--supersedes` removes the old document's vectors and links it to the new one. Its text stays in the database for the
   record, but **the citation viewer will no longer open it**: a superseded document is treated as not found, so an old
   citation that points at it leads nowhere. Plan for that when you retire a policy that people have already cited.
6. Apply the workbook, and purge any vectors left over from superseded rows:
   ```
   askbpl-apply-inventory --purge-vectors
   ```
7. `askbpl-corpus-report --strict`. The old row should show `superseded`; the new row should show its own stage.
8. Re-run the evaluation (A, step 9).

### D. Retire a policy (no replacement)

Set Lifecycle status to `Excluded` (not a policy, or withdrawn) in the workbook, then
`askbpl-apply-inventory --purge-vectors` and `askbpl-corpus-report --strict`. **There is no command that deletes a stored
document.** An excluded or superseded document stays in the database, can never answer, cannot be opened in the citation viewer,
and has its vectors removed.

### E. Re-ingest after a setting change

Reader and chunking settings (`PDF_READER`, `CHUNK_STRATEGY`) change how every file is cut up. After changing one:

1. Run `askbpl-provenance-report` on each file and check the page and heading labels.
2. Run `askbpl-ingest-batch --manifest ...`, then `askbpl-apply-inventory`, then `askbpl-corpus-report --strict`.
3. Change **one** thing at a time, and run the evaluation (A, step 9) before and after, so a change in answers has one
   possible cause.

### F. A file was renamed or moved

A different path is a **different document**. The old and new copies now both exist, and `askbpl-apply-inventory`
stops with `error:duplicate` until one is gone. Treat the new path as the live one and retire the old id with recipe C
(`--supersedes`). The report lists both under `duplicate_documents`.

## 5. Validate: scanned or unreadable files (PRD ING-3, GATE-04)

A scanned PDF has no trustworthy text. OCR is a **fallback** and is never trusted on its own: a person compares every page
image with its text, and only that person's signed-off text can be indexed. The full procedure is in
`docs/EXTRACTION_REVIEW.md`. The three commands are:

```
askbpl-extraction-review prepare --pdf "<scanned file>.pdf" --source-id SRC-13
askbpl-extraction-review finalize --dir extraction_reviews/SRC-13
askbpl-extraction-review verify --record extraction_reviews/SRC-13/validation_record.json --pdf "<scanned file>.pdf"
```

Two keys are needed and neither works alone: the person's record, **and** the team's deliberate edit of the workbook row.
Do not activate a scanned document before the decision to do so is logged. SRC-13 (Conflict of Interest) is the current
example and is blocked.

## 6. After every change: the checklist

1. `askbpl-corpus-report --strict` exits 0 (nothing to reconcile), and the counts moved the way you expected.
2. `askbpl-doctor` shows no **[FIX]**.
3. The evaluation was re-run live with `--repeat 3` and the results were read, not just counted.
4. The report output, the commit and the date are saved in the baseline record, and the change is in the change log
   (BASE-8, BASE-9).

## 7. When something goes wrong

| What you see | What it means | What to do |
|---|---|---|
| `refused:<file>:blocked` or `:excluded` | The workbook says the document may not be ingested. | Correct the workbook only if the decision was wrong, and record why. |
| `failed:<file>:file_missing` | The manifest names a file that is not in the corpus folder. | Fix the path or the file name. |
| `Policy <slug> missing — run routing seed` | The `policy` slug is not in `config/routing_seed.yaml`, or `askbpl-seed` was not run. | Add the slug, run `askbpl-seed`. |
| `Unrecognised lifecycle status` | A Lifecycle cell holds a value the system does not know. It never guesses. | Use `Authority pending`, `Eligible`, `Excluded`, `Superseded` or `Blocked`. |
| `warning: marked Eligible without reviewer and date` | The row was treated as Authority pending. | Add both the reviewer and the date, or change the status back. |
| `unlisted:<path>` | A stored document has no workbook row. It cannot answer. | Add its row (AC-1). |
| `error:duplicate` | Two stored documents match one row (usually a renamed file). | Recipe F. Nothing was changed. |
| `warning: ... validated ... no verified review record` | The workbook says a scan is validated but the database has no record. It stays blocked. | Section 5. |
| report: `answerable_but_not_allowed` | The database lets a document answer that the workbook blocks. | Run `askbpl-apply-inventory --purge-vectors` now. |

## 8. Decisions BPL still has to make (not made here)

| Decision | Why it matters here | Owner (as the PRD records it) |
|---|---|---|
| Who may mark a document `Eligible`, and on what evidence | Nothing is BPL-confirmed until this is answered (OD-01). | Selvon / a designated BPL policy authority |
| What makes a version "current" (the supersession rule) | Recipe C depends on it (ING-5). | Selvon, to validate with BPL |
| Who owns corpus updates and re-ingestion approval | Someone must say "yes, ingest this" (PRD ING-7, N6). | Open |
| Whether unconfirmed documents may be sent to OpenAI and stored in Pinecone, and for how long | Every ingest does this. | Open (retention and external processing) |
| Who fills the yellow workbook cells (owner, policy number, reviewer, date) | Needed before any `Eligible`. | Bath Bilissalou / BPL |
| The list of the full policy set | The report's "uncovered policy areas" stays "unknown" without it. | Selvon / BPL |

## 9. Known gaps (so you are not surprised)

- **No remove command.** Retire documents with `Excluded` or `Superseded` (recipe D).
- **Batch ingest does not refuse superseded rows** (recipe C, step 3 works around it).
- **A changed file does not reset its approval** (recipe B, step 2 is a manual step).
- **"Evaluated" is not recorded.** The report says so instead of showing a number.
- **The report cannot see Pinecone.** It confirms the database; it cannot confirm that the vectors match.
- **No automatic ingestion from SharePoint** in this build (PRD ING-8).
- **The manifest and the workbook are edited by hand** and can disagree; `askbpl-corpus-report` finds many such
  disagreements but cannot fix them.
