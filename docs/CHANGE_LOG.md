# Engineering change log

PRD BASE-9 (engineering change log; regression tests after every change). One row per change merged into `main`,
oldest first. Commit hashes are on `main` (`git show <hash>`). Each change has a handoff in the team's handoff
files with the full evidence; this page is the index. Patch files are named by change number (for example
`0033-bpl-branding.patch`); `PROJECT_ARCHIVE_INDEX.md` in the patch and handoff archive maps each one to its handoff.

**Test counts** are the backend suite (`python -m pytest -q` in `packages/orchestrator`) after the change, as recorded
at the time. "S" = recorded in the build team's sandbox rebuild; "L" = recorded on the team Mac. Sandbox counts up to
0022 exclude 4 tests that need the team's local SRC-13 data, which is why some sandbox rows show 4 failed or 4 fewer.
The optional `Policies`-folder test is skipped in most runs. Web counts (`npx vitest run`) are given where they changed.

The current reference baseline is `docs/BASELINE_2026-11-01_freeze.md` (the code freeze); `docs/BASELINE_2026-10-31.md` is the previous one.

## Inherited pilot (before 2026-10-07)

Commits `44e2608` to `435e7d4` (2026-05-11 to 2026-06-23): the pilot as received (orchestrator, Pinecone retrieval,
web demo, SharePoint host page, crisis and PII gates, public demo flow). Not changed by these rows; the inherited test
claims (90/102 backend, 11/11 web) were re-checked under BASE-1 to BASE-4.

## Changes

| Date | Change | Commit(s) on `main` | What it did | PRD IDs | Backend tests after |
|---|---|---|---|---|---|
| 2026-10-07 | 0001 | `13f88a7` | Empty database migrates cleanly; bcrypt pinned; lock file; tests no longer depend on the real environment | BASE-1 to BASE-4 (OPS-2/3/4) | 102 (S, patch review) |
| 2026-10-10 | 0002 | `bae15b4` | Crisis gate runs first; real citation verifier in tests; no placeholder contacts; rewrite log holds lengths only | SAF-2, GRD-5, RTG-4, SAF-5 | 123 (S, patch review) |
| 2026-10-13 | 0003 to 0008 (with 0003a/b/c, 0007a) | merge `21ba435` (`dd5d59e` ... `ce5f448`) | Document eligibility model and retrieval/citation gate; inventory loader; test-index label in the web demo; earlier turns sent inside one user message with a JSON-only contract; answers stay inside the excerpts; `askbpl-eval` runner with the frozen 30 client questions; evaluation hygiene and boundary guards | ING-1, ING-2, ING-9, GRD-1, GRD-5, GRD-8, SAF-6, BASE-8 | 193 (S) |
| 2026-10-13 | 0009 | `1e36ebb`, `bc15c0d` | Extraction review for scanned policies: a person validates OCR text page by page; controlled activation; SRC-13 review evidence | ING-3, ING-11, GATE-04 | 241 (S) |
| 2026-10-14 | 0010 | `05fec11` | Routing names only approved owning teams from the config; no hardcoded teams in the prompt | RTG-2, RTG-4, RTG-7 | 241 (S) |
| 2026-10-15 | 0011, 0012 | `6e4405b`, `1122fb4` | Real refusal cause recorded (6 of 8 causes); outages return 5xx; questions about other people's private matters refused before retrieval | RTG-6, SAF-10 | 345 (L) |
| 2026-10-17 | 0013, 0013a, 0013b | merges `ced2ded`, `1cb6e6e`, `3162c8a` | Page range and conservative section headings on every chunk; shown on sources and in the viewer; a colon line after an unfinished sentence is not a heading | ING-11, GRD-4 | 431 (S) |
| 2026-10-18 | 0014 | `a7d0a6f` | Sentence-aware chunk boundaries; cut at confident headings | ING-11, GRD-4 | 471 (S) |
| 2026-10-18 | 0015 | `ad37f14` | Opt-in pdfium PDF reader (`PDF_READER`) and `askbpl-reader-compare` | ING-11, ING-3 | 502 (S) |
| 2026-10-19 | 0016 | merge `f545599` (`b3e1c73`) | Approved-glossary query expansion; unlisted acronyms logged as counts; review tools (`askbpl-glossary-check`, `askbpl-glossary-candidates`) | GLO-1 to GLO-6 | 558 (S) |
| 2026-10-20 | 0017 | `b779420` | 22 robustness probes (GRD-12 categories); `must_cite_source` check; acronym-only probe | GRD-12, GLO-4 | 619 (S) |
| 2026-10-24 | 0018 | `ff7f80f` | Retrieval-gate log event and `askbpl-score-report` (read-only threshold evidence) | GRD-2 | 665 (S) |
| 2026-10-24 | 0019 | `d2ddb9e` | `askbpl-doctor` read-only preflight and the tester setup guide | INT-1, NFR-3, NFR-6, NFR-8, SAF-5 | 720 (S) |
| 2026-10-25 | 0020 | `65a26c4` | `askbpl-corpus-report` (counts, things to reconcile) and `docs/CURATOR_WORKFLOW.md` | ING-13, ING-7, NFR-6 | 829, 1 skipped (L) |
| 2026-10-25 | 0021 | `2772e86`, `dfccdcc`, `2861b45` | Report notes stored text on blocked documents; batch ingest refuses Superseded rows; `/health/deep` returns fixed error labels, not exception text | ING-13, ING-5, SAF-5 | 848, 1 skipped (L) |
| 2026-10-25 | SRC-13 activation (DEC-15) | `718240b` | Conflict of Interest (scanned) activated in the test index from its validated extraction | ING-3, GATE-04 | (data) |
| 2026-10-25 | 0022, 0022-A | `7b4836d`, `54d9fb3`, `0aae4f2` | `askbpl-vector-report` compares stored chunks with Pinecone (read-only); curator guide checks vectors; shipped-workbook tests updated for SRC-13 | ING-13, ING-7 | 1047, 1 skipped (S, with local data) |
| 2026-10-26 | 0023 | `a67a0ad`, `d45fe5a` | An Eligible approval covers only the reviewed file (SHA-256; migration 007); curator recipe G | ING-2, ING-5, GATE-02 | 1196, 1 skipped (S) |
| 2026-10-27 | 0024 | `705f8e2`, `e8bc75c` | Role lens (General / Staff / Manager) changes framing only, never evidence or the decision; Explain-this-for selector and badge | ROLE-1 to 11 (P1) | 1256 (S, local expectation) |
| 2026-10-27 | 0025 | `c95107c` | `askbpl-eval --role` and `--compare` | ROLE-2, ROLE-3, ROLE-7 | 1277 (S, local expectation) |
| 2026-10-27 | 0026 | `c265fb1` | Lens wording revision 2 after reading live answers against the policies | ROLE-3, ROLE-7 | 1283 (S, local expectation) |
| 2026-10-28 | 0027 (rejected) | none | Lens wording revision 3, tested live and rejected; not applied | ROLE | n/a |
| 2026-10-29 | 0028 | `d93bf91` | Staff is the default role (team working choice; D-09 open) | ROLE-11 | 1293, 1 skipped (L) |
| 2026-10-28 | (local) | `720a36c` | Web demo `package-lock.json` update | NFR-6 | n/a |
| 2026-10-31 | 0029-r2 (+ 0029-r2-data) | merge `5b41ab8` (`acc5b62`, `2874782`) | Corpus wave 1 (SRC-02, 08, 09, 11, 17, 21, 27) in the marked test index; SRC-15 held (named as superseded by SRC-11); workbook rows marked | ING-1, ING-10, ING-12 | 1304, 1 skipped (L) |
| 2026-10-31 | 0029a-r3 (+ 0029a-r3-data) | merge `513a2db` (`5500a16`, `70b6975`) | Corpus wave 2 (SRC-18, 24, 26); SRC-12 and SRC-19 held (named staff contacts); guard: no manifest document may carry a personal email or phone number | ING-1, SAF-1, SAF-8 | 1310, 1 skipped (L) |
| 2026-10-31 | 0030 eval wave 1 | merge `7c27421` (`4bece61`) | Wave 1 coverage probes; ROB-UI-02 expects the Dress Code answer; ROB-UI-05 not-indexed probe (robustness 22 to 29) | GRD-12 | 1324, 1 skipped (L) |
| 2026-10-31 | 0031 eval wave 2 | merge `e3c8add` (`c5bfdcf`) | ROB-UI-01 / UI-03 expect the FMLA and discipline answers; whistle-blower and union-audience probes (29 to 31). **Reference baseline commit** | GRD-12 | 1333, 1 skipped (L) |
| 2026-10-31 | 0032 Windows setup | merge `d5c78ed` (`b583222`) | `.gitattributes` keeps checked files byte-exact on Windows; plain dense Pinecone index required in the setup docs | NFR-6 | 1341, 1 skipped (L) |
| 2026-10-31 | 0033 BPL branding (D-08) | merge `55c5c67` (`643cc2c`) | BPL logo and BPL Blue in the widget, per BPL's logo guide; `docs/BRANDING.md` | UX-3 (P1) | 1341, 1 skipped; web 46 (L) |
| 2026-11-01 | 0034 npm ci | merge `a2d1e3d` (`dbccf06`) | Setup docs install the web demo with `npm ci` | NFR-6 | 1344, 1 skipped (L) |
| 2026-11-01 | 0035 placeholder and baseline | merge `f122f51` (`92ec577`) | Plain-language question placeholder; `docs/BASELINE_2026-10-31.md`; `scripts/compare_runs.py` | UX-1, BASE-8 | 1345, 1 skipped; web 49 (L) |

| 2026-11-01 | 0036 change log | this page | This change log (BASE-9) and its guard test | BASE-9 | 1346, 1 skipped (L) |
| 2026-11-01 | 0038 safety gate suites | `4a7728e` (merge below) | Labelled crisis and PII suites (SAF-3); crisis gate 22/40 to 40/40 first-person statements, scheduling false alarm fixed, workplace injuries not sent to the crisis card; PII gate catches "Ave."/"Pl." addresses and driver licence numbers | SAF-3, SAF-1, SAF-2 | 1469, 1 skipped (L) |
| 2026-11-01 | 0039 ingest quality check | `33c3f8f` (merge below) | askbpl-ingest-batch refuses scanned or image-only PDFs before embedding (thin-page / median-text rule) and warns on heavy word-splitting; calibrated on every PDF held | ING-3, GATE-04 | 1478, 1 skipped (L) |
| 2026-11-01 | 0040 GRD-10 probes | `2d8ccae` (merge below) | Eight legal-advice and decision probes (robustness 31 to 39); live 24/24 runs decline correctly; intent guard measured (catches 3/17 phrasings) and left unchanged | GRD-10 | 1492, 1 skipped (L) |
| 2026-11-01 | 0041 crisis card and source-unavailable state | `08f33d9` (merge below) | The web demo showed the crisis response as an error with no support lines; now a crisis card (988, EAP, closing; 988 fail-safe); placeholder EAP text neutralised; plain "source unavailable" message | UX-9, SAF-2, UX-1 | 1493, 1 skipped; web 56 (L) |
| 2026-11-01 | 0042 handover guide | `700582f` (merge below) | docs/HANDOVER.md: BPL staff entry point (state, running, health checks, safe changes, safety controls, before real use, known limits, configuration, contacts by role); guard test | NFR-6 | 1494, 1 skipped (L) |

## Not merged

| Branch | What | Status |
|---|---|---|
| `design/grd-11-claim-grounding` (`7dd682d`), patch 0037 | GRD-11 claim-level grounding design note (proposal, no code) | Team review |

## How to add a row

When a change is merged into `main`: add a row with the date, the change name, the commit(s) or merge, a one-line
plain description, the PRD IDs, and the backend (and web, if changed) test counts from the run before the merge. If the
change affects answers, also record the evaluation run files and compare them with the baseline
(`scripts/compare_runs.py`). `tests/test_setup_guards.py` checks that every hash on this page is a real commit.
