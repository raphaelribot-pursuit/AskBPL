# Handover walkthrough: test the handover guide as a newcomer (ING-7, AC-13)

**Who:** one team member who did **not** write `docs/HANDOVER.md` or `docs/CURATOR_WORKFLOW.md` (later, a BPL staff
member taking it over). **Time:** 30 to 60 minutes. **Cost:** none. Every step is read-only or local: no live
questions, no ingest, nothing sent to OpenAI, Anthropic or Pinecone except where a step says so.

**The rule:** use only what the documents say. Do not ask the person who wrote them, and do not read the code to fill a
gap. When you get stuck, **that is the finding**: write it down and move on. A walkthrough with findings is a success;
the guide gets fixed and ING-7 moves to Done.

Record each step as **OK**, **Unclear** (you got there, but the guide did not make it easy) or **Blocked** (you could
not do it from the documents), with a note.

## Part 1. Orientation (about 10 minutes): `docs/HANDOVER.md`

| # | Using only the handover guide, can you... | Result | Note |
|---|---|---|---|
| 1.1 | Say in one sentence what Ask BPL does and what it refuses to do? (section 1) | | |
| 1.2 | Say how many documents can answer, how many are held back, and why? (section 1) | | |
| 1.3 | Find the full history of changes, and the explanation for one change of your choice (for example patch 0047)? (section 2, the archive index) | | |
| 1.4 | Find the list of decisions BPL still has to make? (section 2) | | |
| 1.5 | Name the safety gates that run before a question reaches the policy search, in order? (section 3) | | |
| 1.6 | Say what must happen before real staff use it? (section 8) | | |
| 1.7 | Name two known limits a staff member might notice? (section 9) | | |

## Part 2. Is it healthy? (about 10 minutes): section 5

On a machine already set up for Ask BPL (`docs/TESTER_SETUP.md`), from `packages/orchestrator` with the virtual
environment active:

| # | Run | Expected | Result | Note |
|---|---|---|---|---|
| 2.1 | `askbpl-doctor` (without `--live`) | No **[FIX]** lines | | |
| 2.2 | `askbpl-corpus-report --strict` | Exits 0; 18 documents can answer | | |
| 2.3 | `askbpl-vector-report --strict` | Exits 0 (it reads Pinecone; no cost) | | |
| 2.4 | `python -m pytest -q` | All pass (1 skipped is normal) | | |
| 2.5 | Could you tell from the guide what to do if one of these failed? | Each command's output says; section 5 says so | | |

## Part 3. Changing a document (about 15 minutes): `docs/CURATOR_WORKFLOW.md`

**Do not run an ingest.** Read the recipe and answer from it.

| # | Scenario | What you should be able to say from the curator guide | Result | Note |
|---|---|---|---|---|
| 3.1 | HR sends a new version of the Dress Code with a new file name | Which recipe (supersede), which workbook rows change, which commands run, in what order | | |
| 3.2 | A scanned PDF arrives | Why it will be refused, and how its text gets validated (section 5, `docs/EXTRACTION_REVIEW.md`) | | |
| 3.3 | A policy is withdrawn with no replacement | Which recipe (retire) and how to confirm it can no longer answer | | |
| 3.4 | A document contains staff names and phone numbers | That it must not be loaded, and which test stops it (handover section 7) | | |
| 3.5 | After any change | The checklist in section 6 of the curator guide | | |

## Part 4. Changing the code safely (about 5 minutes): handover section 6

| # | Can you say... | Result | Note |
|---|---|---|---|
| 4.1 | How to check that a prompt change did not make any answer worse (the two evaluation commands and `scripts/compare_runs.py`) and roughly what one full run costs (`docs/SPEND_LIMITS.md`)? | | |
| 4.2 | Which reference run to compare with (`docs/BASELINE_2026-11-01_freeze.md` and the later runs in `docs/CHANGE_LOG.md`)? | | |
| 4.3 | What has to be recorded for every change? | | |

## Part 5. Record the result

1. Count: ____ OK, ____ Unclear, ____ Blocked. Date: ________. Walked through by (role): ________.
2. Give the filled-in tables to the team. Each **Unclear** or **Blocked** becomes a fix to the guide (a numbered patch,
   like every other change).
3. **ING-7 is Done** when a walkthrough has no **Blocked** steps, and every **Unclear** step has either been fixed or
   been accepted, with a reason.
