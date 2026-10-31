# Corpus waves: bringing the 21 unevaluated documents into the marked test index

Patch 0029 (wave 1) and 0029a (wave 2). PRD: ING-1, ING-2, ING-3, ING-6, ING-9, ING-10, OD-01, OD-02, OD-03, OD-11.

**What this is.** Of the 30 files BPL supplied, 8 were in the pilot index and 1 (SRC-28) is the test script. The other
**21** had never been evaluated for inclusion. On 2026-10-31 the team evaluated each one and decided: **12 go into the
marked test index in two waves; 9 are held back.** This page records who is where and why, and the exact steps.

**What this is not.** Nothing here makes a document BPL-confirmed. Every one of the 12 enters as *Authority pending,
test index* (OD-11): answerable only while `ALLOW_TEST_INDEX=true`, and labelled to staff as not yet confirmed by BPL.
Placement in a wave is a team decision, not a BPL decision. OD-01 (who confirms authority) is still open.

## 1. The 30 files, by disposition

| Group | Source IDs | Count |
|---|---|---|
| Pilot index (before the waves) | SRC-03, 05, 06, 10, 13, 14, 16, 22 | 8 |
| **Wave 1** (patch 0029) | SRC-02, 08, 09, 11, 17, 21, 27 | 7 |
| **Wave 2** (patch 0029a) | SRC-12, 18, 19, 24, 26 | 5 |
| **Held** | SRC-01, 04, 07, 15, 20, 23, 25, 29, 30 | 9 |
| Excluded (test script) | SRC-28 | 1 |

## 2. How each of the 21 was evaluated

Every file was read, run through `askbpl-reader-compare` and `askbpl-provenance-report` (stand-in tokenizer), and
checked against PRD 19.3 / 19.4. **All 19 PDFs have a real text layer and read in the right order; none is a scan
and none has a thin page that matters.** Extraction quality did not decide any disposition. Content risk did.

| ID | Document | Dated | Applies to (per document) | Extract / chunks* | Disposition | Why |
|---|---|---|---|---|---|---|
| SRC-02 | Policy for Policy Management | Apr 2026 | (not stated) | clean; narrow columns split some words; 3 | **Wave 1** | The approval process itself. Check viewer text for split words ("pro cedures"). |
| SRC-08 | Collection Maintenance Procedures | Jan 2026 | Librarians, branch managers | spacing noise (both readers); 12; no headings | **Wave 1** | A procedure, not a policy (ING-10). Cites documents that are not in the corpus (Collection Management Policy, BookOps ticketing, donation guides). |
| SRC-09 | Internal Communications Policy | Oct 2024 | Staff, temps, contractors | clean; 11 | **Wave 1** | Generic "the Organization" wording. Refers to the Social Media and Harassment policies. |
| SRC-11 | Promotional and Marketing Materials | May 2020 | All staff | clean; 8 | **Wave 1** | Generic "company" wording. |
| SRC-17 | Dress Code (HR09) | Jun 2006 | All staff | clean; 5 | **Wave 1** | Routed to HR (an HR policy number). Has the typo "Orhganization". |
| SRC-21 | Custodianship of Library Materials | Feb 2008 | All staff | clean; 5 | **Wave 1** | Mentions the Millennium system; check it is still the system in use. |
| SRC-27 | Social Media Use | Mar 2022 | All staff | clean; 17 (all with headings) | **Wave 1** | Largest document. Two-column layout reads correctly. |
| SRC-12 | Anti-Harassment (HR08) | Oct 2018 | All employees, volunteers, vendors, visitors | clean; U+F0A7 bullets | **Wave 2** | HR/legal authority. Contains a named HR contact (email and phone) and a compliance hotline number that may be stale. |
| SRC-18 | Whistle-Blower Protection | Sep 2006, upd. Oct 2009 | Trustees, officers, all employees | clean | **Wave 2** | Legal/HR. Reports go to the HR Employee Relations Manager (routed to HR). |
| SRC-24 | Progressive Discipline (HR14) | Jun 2006 | All staff | clean; 3 pages | **Wave 2** | Splits union and non-union staff and points to the union contract, which is not in the corpus. |
| SRC-26 | Family and Medical Leave Act (HR25) | Jun 2006 | All employees | clean | **Wave 2** | A legal entitlement from 2006. PRD 19.4: never calculate current entitlements from outdated sources. |
| SRC-19 | Photography, Filming and Videography | Mar 2024 | **All visitors** | clean | **Wave 2** | Written for visitors, not staff (PRD 19.4: keep audiences distinct). Contains named individuals' emails and phone numbers; one email domain looks misspelled ("bkynlibrary.org"). |
| SRC-01 | Emergency Response Procedure | Oct 2002 | All staff | clean | **Held** | See section 3. |
| SRC-07 | Emergency System-wide Closing | Oct 2002 | All staff | clean | **Held** | See section 3. |
| SRC-23 | Crisis Management Policy | Sep 2008 | All staff, volunteers | clean; 1 thin page | **Held** | See section 3. |
| SRC-04 | Use of Personal Vehicles | Oct 1995 | **Managerial staff only** | clean | **Held** | States a 1995 rate: "twenty-eight cents ($0.28) per mile" (PRD 19.3: do not repeat an old rate as current). |
| SRC-25 | Service Rating Manual | 1974 reference | All staff | clean; 9 pages | **Held** | The document's own Policy #, Date Issued and Effective Date fields are blank (ING-6: block when metadata is ambiguous). Employee-agreement implications. |
| SRC-20 | Update to BPL Rules (design deck) | Apr 2026 | Patrons | clean | **Held** | A poster design deck, not a policy (ING-10, PRD 19.3). Repeats "For the complete policy, visit bklynlib.org/public-behavior-policy" many times, which would flood retrieval with near-duplicate chunks. |
| SRC-29 | Guidelines for Public Behavior Violations | 2025 | Staff, about patrons | clean | **Held** | Supporting guidance that "cannot override" the policy (PRD 19.4), and the policy it supports is unsettled (OD-02). |
| SRC-30 | Public Behavior in the Library Policy | "Issued: June 2026 (TBD)" | Patrons | clean (.docx) | **Held** | Filename says "updated Jan-26"; the text says "June 2026 (TBD)". OD-02 is open. |
| SRC-15 | Media Relations and Publicity | Oct 2018 | All staff | clean; 5 | **Held** | SRC-11 (Promotional and Marketing Materials, revised 05/26/2020) lists "Media Relations Policy (I. #07)" under *Supersedes policy #*. SRC-15 is numbered I. Organization 7 and is older. ING-12: block and ask BPL. |

\* Chunk counts are from `askbpl-provenance-report --stand-in-tokenizer`, so they are approximate. Wave 1 expects about
61 chunks in total (3 + 12 + 11 + 8 + 5 + 5 + 17). The real count after ingest may differ a little. Compare
`askbpl-corpus-report`, not this table, once it has run.

## 3. Why nine are held

* **Emergency and crisis documents (SRC-01, 07, 23).** The cost of a wrong answer is highest here, because staff would
  act on it in an emergency. SRC-01 lists 2002 numbers, including a gas utility under a name that I believe no longer
  exists (verify), 230-xxxx security extensions and regional librarians' phone numbers. SRC-07 depends on a
  telephone tree built on staff home numbers. SRC-23 carries extension strings. PRD 19.3 names all three, and OD-03
  (current emergency instructions) is marked "Before real staff use". The test-index banner says "not yet confirmed",
  but a person looking for an emergency number will not weigh it.
* **A stale figure (SRC-04) and an undated document (SRC-25).** Both are the failure modes PRD 19.3 and ING-6 name.
* **Not policies, or not settled (SRC-20, 29, 30).** A design deck, supporting guidance, and a draft. OD-02.
* **Named as superseded (SRC-15).** SRC-11 (revised 05/26/2020, wave 1) lists "Media Relations Policy (I. #07)" under
  *Supersedes policy #*; SRC-15 is "I. Organization 7", dated October 2018. With both in the index, media questions
  could be answered from the replaced text. ING-12: block the conflict and ask BPL whether SRC-15 is still in force.
  Note that SRC-11 also names "Social Media Policy (II. #06)" as superseded, while SRC-27 (II. Staff 26, March 2022)
  is later than SRC-11; read as a reissue, so SRC-27 stays in wave 1. Ask BPL to confirm both.
* **The cost of holding.** Front-line (Staff) questions about patron behavior and emergencies will refuse or give the
  neutral referral until these are brought in. That is the intended, safe behavior, but it is a real gap.
* **Holding is not excluding.** The rows stay *Authority pending* and can be brought in by a later patch, one wave at a
  time. `tests/test_corpus_waves.py` pins this list: a held document cannot be added to a manifest, or marked in the
  workbook, without changing the test and this page together.

## 4. Wave 1: exact steps (patch 0029)

The patch does **not** ship the inventory workbook, because your copy carries edits this repository does not (the
SRC-13 activation). The workbook is the curator's file (recipe A step 3), so the one change to it is made by hand.

All commands run from `packages/orchestrator` with the virtual environment active.

1. **Baseline first.** On the current `main`, before changing anything:
   ```
   askbpl-corpus-report --strict
   askbpl-eval --set all --repeat 3
   askbpl-eval --set robustness --repeat 3
   ```
   Keep the output and the two run file names. This is the "before" in the before/after comparison.
2. **Apply the patch** on its own branch from `main`: `git am --3way 0029-wave1-corpus-and-routing.patch`.
   No migration and no new dependency. Then `askbpl-seed` so the new routing slugs exist. The new rules are stored
   **unapproved**, so staff see the neutral supervisor referral for these documents until BPL approves a team.
3. **Edit the workbook by hand.** In `AskBPL_Source_Inventory_v0_1.xlsx`, sheet `Source Inventory`, column G
   (`In current pilot index`), change `No` to `Yes` on these seven rows and **nothing else**:

   | Source ID | Row | File |
   |---|---|---|
   | SRC-02 | 3 | 01 - Policy for Policy Management.pdf |
   | SRC-08 | 9 | 02d - Collection Maintenance Procedures (updated 2026).pdf |
   | SRC-09 | 10 | 03 - Internal Communications Policy and Norms (10.24) (2).pdf |
   | SRC-11 | 12 | 04 - Promotional and Marketing Materials (05.20) (1).pdf |
   | SRC-17 | 18 | 09 - Dress Code Policy (06.06).pdf |
   | SRC-21 | 22 | 12 - Custodianship of Library Materials (02.08) (1).pdf |
   | SRC-27 | 28 | 26 - Social Media Policy (03.22) (1).pdf |

   Leave `Lifecycle status` as `Authority pending` and `Reviewer / date` empty. Do not type `Eligible`.
4. **Check what the workbook now says** (reads only the workbook):
   ```
   askbpl-apply-inventory --dry-run
   ```
   Exactly these seven rows should read `authority_pending:test_index`, in addition to the eight already there.
5. **Ingest** (calls OpenAI and Pinecone, a small cost; read every line, `indexed:` is good):
   ```
   askbpl-ingest-batch --manifest sample_corpus/corpus_manifest_wave1.yaml
   ```
6. **Apply, then reconcile:**
   ```
   askbpl-apply-inventory
   askbpl-corpus-report --strict
   askbpl-vector-report --strict
   ```
   Expect **15 answerable, all test index, 0 BPL-confirmed**; `--strict` exits 0; the vector report shows no missing
   vectors. If you ran step 5 before step 3, run `askbpl-apply-inventory` after the edit; nothing answers until it has.
7. **After.** `askbpl-eval --set all --repeat 3` and `askbpl-eval --set robustness --repeat 3`, then read the results
   against step 1. Do not tune a threshold, prompt or probe from one case.
8. **Read the first answers.** Open each new document in the citation viewer once. See section 6.
9. Record the date, commit, counts and run file names in the baseline record, and the decision (section 7) in the log.

## 5. What to watch in the evaluation

Adding documents changes the candidates for **every** question, so compare questions, not totals.

* **Materials Selection (BPL-MS-01 to 05 and ROB-MS-*).** SRC-08 (weeding and replacing) and SRC-21 (custodianship) are
  close in topic to SRC-05 (materials selection). This is the most likely place for a retrieval shift.
* **Similar-title and multi-policy probes (ROB-ST-04, ROB-MD-01).** Two more candidates for a wrong-document answer.
* **Volunteer Manual (BPL-VM-*).** SRC-16 probably has sections on dress, conduct and social media that now overlap SRC-17
  and SRC-27.
* **The known-unstable cases** (BPL-AL-05, MS-05, UC-05, CI-01). Re-read them; they were unstable before.
* **Answers that say a rule exists elsewhere.** SRC-08 and SRC-09 point to documents that are not in the corpus. An
  answer must stay inside the excerpts and say so, not describe the missing document.

## 6. What patch 0029 does not establish

* Not run against live OpenAI, Pinecone or Anthropic, and not run in a browser. Only the offline checks below.
* That the 7 documents are current, approved or correct. They are not BPL-confirmed.
* That answers about them are good. No evaluation questions exist for them yet; writing them is a separate, reviewed
  change (curator recipe A step 9).
* Routing for the new slugs is **proposed** (SUPERVISOR, or HR for the Dress Code) and is not approved by BPL.
* Chunk counts use a stand-in tokenizer.

## 7. Suggested decision-log entry (yours to record)

> **DEC-17.** On 2026-10-31 the team evaluated the 21 documents not yet in the pilot index. 12 will enter the marked
> test index in two waves (OD-11); 9 are held (emergency/crisis OD-03; 1995 mileage rate; 1974 manual with blank
> metadata; design deck; Public Behavior draft and its supporting guidance, OD-02; Media Relations, named as superseded by SRC-11, ING-12). Team decision only: BPL has
> approved nothing (OD-01 open). Wave 1: SRC-02, 08, 09, 11, 17, 21, 27. Wave 2: SRC-12, 18, 19, 24, 26.
> Decided by: ________. Reviewed by: ________.
