# Ask BPL: handover guide for Brooklyn Public Library

**Start here.** This page is for the BPL staff who look after Ask BPL once the capstone team's work ends. It says what
the system is, what state it is in, how to run and maintain it, how to change it safely, and what is still undecided.
Each section points to the detailed document; nothing here replaces them. Prepared 2026-11-01 at the code freeze;
`main` at the time of writing is `520e7fd` plus this page.

## 1. What Ask BPL is, and is not (at the freeze)

Ask BPL answers staff questions about BPL policies **only from the policy documents loaded into it**, and shows which
policy each answer comes from. When the documents do not cover a question, it says so and suggests who to ask instead
of guessing.

| Fact at the freeze | Detail |
|---|---|
| Documents that can answer | **18** of the 29 BPL documents received (`docs/CORPUS_WAVES.md`) |
| Documents BPL has confirmed as current | **0**. Every answer carries a "not yet confirmed by BPL" label (OD-01) |
| Documents held back | 11 (emergency procedures, a 1995 rate, a 1974 manual, a design deck, the Public Behavior draft and its guidance, a superseded policy, two documents with staff contact details) |
| Users | A developmental build: the build team, testers and BPL IT. **Not approved for real staff use** (section 8) |
| Hosting | Runs locally. `render.yaml` describes a possible deployment; nothing is deployed |
| P0 requirements in place | About 64% (43.0 of 67), `AskBPL_P0_Progress_Report_v3` in the project archive |

## 2. Where everything is

| What | Where |
|---|---|
| Code | GitHub `raphaelribot-pursuit/AskBPL`. `packages/orchestrator` (Python API, ingest, evaluation), `packages/web-demo` (the staff widget) |
| History of every change | `docs/CHANGE_LOG.md` (from the code); the **project archive** `AskBPL_Project_Archive/` (every patch file and the handoff that explains it, indexed in `PROJECT_ARCHIVE_INDEX.md`) |
| Current reference point | `docs/BASELINE_2026-11-01_freeze.md` (the earlier `docs/BASELINE_2026-10-31.md` is history) |
| Policy files and their status | `packages/orchestrator/sample_corpus/` and the workbook `AskBPL_Source_Inventory_v0_1.xlsx` (the workbook decides what may answer) |
| Decisions BPL still has to make | `AskBPL_BPL_Decision_Request_2026-10-31.md` (project archive, `reports/`) |

## 3. How it works (one paragraph)

A staff question goes to the API (`packages/orchestrator`, FastAPI). **Safety gates run first**: a crisis statement
gets support resources (988 and the EAP line), personal details (email, phone, ID numbers, addresses) are rejected, and
requests for legal advice or other people's personnel history are refused. Otherwise the question is turned into an
embedding (OpenAI) and matched against policy passages in Pinecone. Only passages from documents the workbook allows
are used, and only if they match closely enough. The answer is written by Claude (Anthropic) from those passages alone,
then a verifier checks that every citation points to a retrieved passage before anything is shown. Postgres holds the
documents, passages, questions (hashed) and settings.

## 4. Running it

Follow `docs/TESTER_SETUP.md` (step by step, including Windows). In short, from `packages/orchestrator` with the
virtual environment active: `alembic upgrade head`, `askbpl-seed`, then load the documents with `askbpl-ingest-batch`
for each manifest (`docs/CORPUS_WAVES.md`), then start the API; in `packages/web-demo`, `npm ci` and `npm run dev`.
The Pinecone index must be a plain dense index (`docs/PINECONE_CORPUS_INGEST.md`).

## 5. Keeping it healthy

Run these read-only checks after any change and before any demonstration (each says what to do about a problem):

| Command | What it checks |
|---|---|
| `askbpl-doctor` (add `--live` to test the keys; costs a fraction of a cent) | Settings, database, migrations, keys |
| `askbpl-corpus-report --strict` | What can answer, and whether the workbook and the database agree |
| `askbpl-vector-report --strict` | Whether every stored passage has its vector in Pinecone |

Changing the documents (add, replace, supersede, retire, re-ingest, validate a scan, approve a reviewed file) is
covered recipe by recipe in `docs/CURATOR_WORKFLOW.md`. Scanned PDFs are refused automatically until a person has
validated their text (`docs/EXTRACTION_REVIEW.md`).

## 6. Changing it safely

The team's working rules, which kept every change traceable:

1. One change per branch, from `main`. Run the full tests (`python -m pytest -q` in `packages/orchestrator`;
   `npm run test` in `packages/web-demo`) before and after.
2. Anything that can change answers (prompts, thresholds, documents, retrieval) is evaluated live before and after,
   **one change per run**: `askbpl-eval --set all --repeat 3` and `askbpl-eval --set robustness --repeat 3`, then
   compare question by question with `python ../../scripts/compare_runs.py <before.json> <after.json>`. Read the answers;
   a PASS is an automated check, not proof the answer is right.
3. Deliberately break each new safeguard once to prove its test catches it.
4. Record the change: a row in `docs/CHANGE_LOG.md`, and (to keep the archive complete) a patch file and a handoff.

## 7. Safety controls and where they live

| Control | Enforced in | Tested by |
|---|---|---|
| Crisis statements get support resources, before anything else | `services/crisis_gate.py`; the web demo's crisis card | `tests/test_gate_suites.py`, `test_crisis_gate.py`, `CrisisCard.test.tsx` |
| Personal details rejected before retrieval | `services/pii_gate.py` | `tests/test_gate_suites.py`, `test_pii_gate.py` |
| Legal advice, decisions and other people's personnel history refused | `services/intent_guard.py` and the answer prompt | `tests/test_intent_guard.py`; live probes ROB-GR-01 to 08 |
| Only allowed documents can answer; a changed file loses its approval | `services/eligibility.py`; the workbook via `askbpl-apply-inventory` | `tests/test_eligibility.py`, `test_approval_bound_to_file.py` |
| Every displayed citation was retrieved | `services/citation_verifier.py` | live evaluation (100% verified at the baseline) |
| No invented contacts; referrals only to approved teams | `config/routing_seed.yaml` (rules stored unapproved until BPL approves) | routing tests |
| No document carrying staff contact details is sent to outside services | `tests/test_corpus_waves.py` (blocks any manifest document with an email or phone number) | the same test |

## 8. Before real staff use (not done)

- **BPL decisions** in the decision request, above all: whether policy text and questions may be processed by outside
  AI services and how long questions are kept (SAF-9, DEC-10); who may confirm a policy is current (OD-01); the
  approved crisis / EAP wording (SAF-2); approved referral teams.
- **Spend alerts** on the OpenAI, Anthropic and Pinecone accounts (NFR-8).
- **Hosting and access**: a reviewed deployment with HTTPS and sign-in (INT-1, NFR-3). The demo access code and the
  shared demo user are for testing only.
- **Wording kept for the developmental build**: the widget's intro says answers come from "authorized BPL policy
  documentation". That was a deliberate choice for demonstrations to BPL IT; change it before real staff see the tool.
- **BPL review** of the branded widget and of the answer and refusal screens (UX-9 acceptance).

## 9. Known limits (measured, not hidden)

- Answers can add a small next step the policy does not state (GRD-11). A design for sentence-level citations is on branch
  `design/grd-11-claim-grounding` (patch 0037 and Handoff 28 in the project archive; proposal, not merged, not built).
- General discipline answers do not mention that union staff follow the Union Contract (the explicit union question does).
- Some phrasings fail the retrieval threshold (e.g. a business-card question); some stored text has split words
  (SRC-02, SRC-08). Details in `docs/BASELINE_2026-11-01_freeze.md`.
- The safety gates are pattern based: the crisis suite has 40 positive and 35 near-miss cases, written by the build
  team, not by clinicians. Unusual phrasings can still be missed.

## 10. Configuration (names only; never put values in documents or chat)

Server settings live in `packages/orchestrator/.env` (template: the repository's `.env.example`): database URL, JWT
secret, the OpenAI, Pinecone and Anthropic keys and model names, `ALLOW_TEST_INDEX` (must stay `true` while no
document is BPL-confirmed), `PDF_READER`, `GROUNDING_THRESHOLD`, `CORS_ORIGINS`, admin credentials. The web demo's
settings live in `packages/web-demo/.env.local` (`VITE_API_BASE_URL`). If a key is ever exposed, replace it at the
provider.

## 11. Who to ask (by role)

| Topic | Role |
|---|---|
| Policy authority, current versions, approvals | BPL's designated policy authority (through the project liaison) |
| Branding and the logo guide | BPL Art & Design Department |
| Accounts, keys, hosting | BPL IT |
| What a past change did and why | The handoff named for it in `PROJECT_ARCHIVE_INDEX.md` |
