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
| 2026-11-01 | 0043 freeze baseline | `e830a21` (merge below) | Freeze baseline on c0f1c48: client 26/1 F/3 R, team 7/7, robustness 34/5 F (39 cases); 35/37 and 30/31 identical to e3c8add; patches 0038 to 0042 changed no answer | BASE-8 | 1495, 1 skipped (L) |
| 2026-11-01 | 0044 staff-audience probes | `accaa0c` (merge below) | ROB-MD-01 and ROB-CF-01 settled (team decision: staff get the staff rule); MD-01 passes; CF-01 fails on the patron rule told to staff (known defect) | GRD-12, GRD-1 | 1503, 1 skipped (L) |
| 2026-11-01 | 0045 spend limits for BPL | `dd79704` (merge below) | docs/SPEND_LIMITS.md: steps and cost estimates for spend limits on the three providers; BPL sets the amounts; handover guide points to it | NFR-8 | unchanged (docs only) |
| 2026-11-01 | 0046 GRD-11 proposal for BPL | `6dd23e8` (merge below) | docs/design/GRD-11_claim_level_grounding.md: costed proposal, not built (team decision option B); evidence, plan, effort and cost, how to start, BPL decisions | GRD-11 | 1504, 1 skipped (L) |
| 2026-11-01 | 0047 staff get the staff rule | `8ea34b4` (merge below) | Answer prompt v5 adds WHO THE RULE IS FOR: a staff asker gets the employee rule, never a customer rule as theirs. ROB-CF-01 FAIL 0/3 to PASS 3/3; no PASS to FAIL against the freeze baseline (runs `eval_20261101T195550Z_8ea34b4`, `eval_20261101T200435Z_8ea34b4`) | GRD-1, GRD-12, PRD 19.4 | 1505, 1 skipped (L) |
| 2026-11-01 | 0048 group exceptions named | `263ebf4`, `a56aa42` (merge below) | ROB-UI-03 must say union employees follow the Collective Bargaining Agreement (re-scored: 0/3 before); answer prompt v6 adds GROUPS THE EXCERPTS TREAT DIFFERENTLY. UI-03 FAIL 0/3 to PASS 3/3; no PASS to FAIL; BPL-VM-05 answered once in 3 (honest, no group sentence; seen before on c265fb1) (runs `eval_20261101T202658Z_a56aa42`, `eval_20261101T203545Z_a56aa42`) | GRD-1, NFR-1, PRD 19.4 | 1508, 1 skipped (L) |
| 2026-11-01 | 0049 short chunk labels | `5be9ee4` (merge below) | The model cites C1, C2... instead of 36-character UUIDs (BPL-FR-01 was refused 4 in 118 asks on a miscopied id); server maps them back; unknown citations fail closed; `citation_labels` log counts. FR-01 10/10 targeted; full runs: no PASS to FAIL, client and team identical to 0048, 0 unknown citations in 195 answers (runs `eval_20261101T204538Z`, `eval_20261101T205320Z`, `eval_20261101T210022Z`, all `5be9ee4`) | GRD-5, GRD-8 | 1518, 1 skipped (L) |
| 2026-11-01 | 0050 gate calibration finding | `29e949a` (merge below) | docs/SCORE_REPORT.md: ROB-W1-04 analysed on 1,123 recorded asks; admitting it needs strong 0.419 and would also admit a 'should my coworker be fired' probe; recommendation: no threshold change; three alternatives for BPL | GRD-2 | unchanged (docs only) |
| 2026-11-01 | 0051 handover walkthrough | `9f2fd85` (merge below) | docs/HANDOVER_WALKTHROUGH.md: read-only 30-60 minute checklist for a newcomer to test the handover and curator guides (OK / Unclear / Blocked); linked from the handover guide; guard test | ING-7, AC-13, NFR-6 | 1519, 1 skipped (L) |
| 2026-11-01 | 0052 RTG-6 last two causes | `0006b35` (merge below) | Intent guard detects sensitive content (security codes, shared passwords, ways round alarms or cameras) and unverified current operations (open today, on duty, system down); draft wording pending BPL; probes ROB-RC-01 to 05. Live: the new causes fired on the 12 intended asks only; no PASS to FAIL; robustness 41/44 (runs `eval_20261101T212726Z`, `eval_20261101T213509Z`, `eval_20261101T214205Z`, all `0006b35`) | RTG-6, SAF-7 | 1607, 1 skipped (L) |
| 2026-11-01 | 0053 handover facts | `ee8a54e` (merge below) | docs/HANDOVER.md: P0 figure 46.0 of 67 (about 69%, progress report v4 after the team's rescoring of RTG-6, GRD-8 and GRD-2); decision request renamed to its revision date (2026-11-01); no fixed commit in the header | NFR-6 | unchanged (docs only) |
| 2026-11-01 | 0054 Show evidence | `0499dd3` (merge below) | GRD-6 audit of the inherited source viewer: cards now say Show evidence; viewer closes with Hide evidence and marks the cited passage in words (WCAG 1.4.1); sources beyond the first three reachable; no scores or identifiers shown (tested). Web only, no answer change | GRD-6, UX-2 | unchanged; web 61 (L) |
| 2026-11-01 | 0055 plain language on the staff screen | `cc15a25` (merge below) | UX-1 audit: jargon removed from the default staff screen and its screen-reader announcements; trust label redrafted in plain words (pending BPL, SAF-6); the crisis card is now announced to screen readers (it was silent); guard tests. No answer change | UX-1, SAF-6, UX-9 | 1607, 1 skipped; web 67 (L) |
| 2026-11-01 | 0056 routing approval audit trail | `f92eb1e` (merge below) | RTG-5 audit: every routing approval or withdrawal, every rule added by the seed, and every approved rule changed by a re-seed (which now needs approval again) is logged on `ask_bpl.routing_audit`; approval endpoint tested (credential, 400, 404). Who approved cannot be shown with the shared admin login (BPL decision). No answer change | RTG-5, RTG-3 | 1612, 1 skipped (L) |
| 2026-11-01 | 0057 admin access tests | `431fb6b` (merge below) | ADM-1 audit: no gap found. All 22 admin and internal routes refuse no credential, a wrong one, a staff sign-in token, and any login when the admin password is empty; oversight figures present; routes found from the schema so new ones are covered. Tests and handover row only | ADM-1, NFR-3 | 1660, 1 skipped (L) |
| 2026-11-01 | 0058 Evaluated stage | `1f83569` (merge below) | `askbpl-corpus-report` counts answerable documents asked about in a recorded live run (18 of 18 today) and shows per-document question counts and latest automated result; notes any never evaluated; read-only | ING-9, ING-13 | 1664, 1 skipped (L) |
| 2026-11-01 | 0059 handover P0 figure | `642a788` (merge below) | docs/HANDOVER.md: P0 figure 49.0 of 67 (about 73%) after the team rescored GRD-6, UX-1, RTG-5, ADM-1, ING-9 and ING-13 | NFR-6 | unchanged (docs only) |
| 2026-11-01 | 0060 procedures kept distinct | `a16f99b` (merge below) | Migration 009 `documents.document_type` from the workbook's Source type; carried on each passage to the model; prompt v8: a procedure or guidance is named as such, never called a policy. ROB-W1-02 now requires it: 0/3 to 3/3 (and 5/5 targeted); no PASS to FAIL; policy answers unaffected (runs `eval_20261101T223911Z`, `eval_20261101T223949Z`, `eval_20261101T224741Z`, `eval_20261101T225438Z`, all `a16f99b`). Existing databases: `alembic upgrade head` then `askbpl-apply-inventory` | ING-10 | 1682, 1 skipped (L) |
| 2026-11-01 | 0062 GRD-11 evidence from the GRD-7 attempt | `715831c` (merge below) | docs/design/GRD-11_claim_level_grounding.md: records patch 0061 (GRD-7 'suggestion' field, **not merged**): in 3 prompt revisions and 45 live answers the model never separated its inferences from policy text; branch kept | GRD-7, GRD-11 | unchanged (docs only) |

## Not merged

| Branch | What | Status |
|---|---|---|
| `design/grd-11-claim-grounding` (`7dd682d`), patch 0037 | GRD-11 design note, first version | Superseded: brought to `main` and expanded for BPL in patch 0046 (`docs/design/GRD-11_claim_level_grounding.md`); the branch is kept for history |

## How to add a row

When a change is merged into `main`: add a row with the date, the change name, the commit(s) or merge, a one-line
plain description, the PRD IDs, and the backend (and web, if changed) test counts from the run before the merge. If the
change affects answers, also record the evaluation run files and compare them with the baseline
(`scripts/compare_runs.py`). `tests/test_setup_guards.py` checks that every hash on this page is a real commit.
