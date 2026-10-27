"""Patch 0025: askbpl-eval --role and --compare (PRD ROLE-2, ROLE-3, ROLE-7). The model is faked; Postgres is real."""

from __future__ import annotations

import asyncio
import csv
import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete

from ask_bpl_orchestrator.db.models import Chunk, Document, Eligibility, IngestStatus, Question, SourceFormat
from ask_bpl_orchestrator.db.session import async_session_factory
from ask_bpl_orchestrator.evals import runner
from ask_bpl_orchestrator.evals.compare import (
    REVIEW_COLUMNS, CompareError, compare_runs, load_run, sentence_count, write_compare_csv,
)
from ask_bpl_orchestrator.evals.scoring import score_run
from ask_bpl_orchestrator.services.retrieval import VectorRetriever
from tests.test_evals import CITE_OK, GROUP_OK, answer_rec, case, refusal_rec


def _with_role(rec: dict, key: str, label: str | None = None) -> dict:
    rec = json.loads(json.dumps(rec))
    rec["payload"]["role"] = {"key": key, "label": label or key.title()}
    rec["role_requested"] = key
    return rec


def _run_file(tmp: Path, name: str, role, records: dict, statuses: dict | None = None) -> Path:
    results = [{"test_id": t, "question": f"Q {t}?", "status": (statuses or {}).get(t, "PASS"), "failed_checks": []}
               for t in records]
    p = tmp / name
    p.write_text(json.dumps({"meta": {"role": role, "mode": "live"}, "results": results, "records": records}),
                 encoding="utf-8")
    return p


# ------------------------------------------------------------------------------- scoring: the role echo
def test_role_echo_passes_when_the_server_reports_the_requested_role() -> None:
    s = score_run(case(must_include=()), _with_role(answer_rec("Staff may carry over seven days."), "staff"))
    assert s.status == "PASS" and s.checks["role_echo"] is True


def test_role_echo_fails_when_the_server_reports_a_different_role() -> None:
    rec = _with_role(answer_rec("Staff may carry over seven days."), "manager")
    rec["role_requested"] = "staff"
    s = score_run(case(must_include=()), rec)
    assert s.status == "FAIL" and "role_echo" in s.failed
    assert any("roles file" in w for w in s.warnings)


def test_role_echo_fails_when_no_role_comes_back() -> None:
    rec = answer_rec("Staff may carry over seven days.")
    rec["role_requested"] = "staff"
    assert "role_echo" in score_run(case(must_include=()), rec).failed


def test_records_without_a_requested_role_score_exactly_as_before() -> None:
    s = score_run(case(must_include=()), answer_rec("Staff may carry over seven days."))
    assert "role_echo" not in s.checks and s.status == "PASS"


def test_a_refusal_is_not_checked_for_a_role_echo() -> None:
    rec = refusal_rec()
    rec["role_requested"] = "manager"
    assert "role_echo" not in score_run(case(cls="OUT", expect="refusal", must_include=()), rec).checks


# ------------------------------------------------------------------------------- run metadata and file names
def test_metadata_records_the_lens_text_hash_that_the_prompt_hash_cannot_see() -> None:
    plain = runner.run_metadata([], mode="live", env_label="t", repeat=1)
    staff = runner.run_metadata([], mode="live", env_label="t", repeat=1, role="staff")
    manager = runner.run_metadata([], mode="live", env_label="t", repeat=1, role="manager")
    general = runner.run_metadata([], mode="live", env_label="t", repeat=1, role="general")
    assert plain["role"] is None and plain["role_lens_sha256"] is None
    assert general["role"] == "general" and general["role_lens_sha256"] is None  # General has no lens text
    assert staff["role"] == "staff" and len(staff["role_lens_sha256"]) == 16
    assert staff["role_lens_sha256"] != manager["role_lens_sha256"]
    assert plain["system_prompt_sha256"] == staff["system_prompt_sha256"] == manager["system_prompt_sha256"]


def test_replay_keeps_the_recorded_role_and_refuses_a_new_one(tmp_path: Path) -> None:
    f = tmp_path / "rec.json"
    f.write_text(json.dumps({"meta": {"role": "staff", "role_lens_sha256": "abc", "role_lens_label": "Staff"},
                             "records": {"REG-AL-02": [_with_role(answer_rec("New hires wait 90 days."), "staff")]}}),
                 encoding="utf-8")
    assert runner.main(["--replay", str(f), "--only", "REG-AL-02", "--out-dir", str(tmp_path)]) == 0
    out = sorted(tmp_path.glob("eval_*_replay_staff.json"))
    assert len(out) == 1
    meta = json.loads(out[0].read_text())["meta"]
    assert meta["role"] == "staff" and meta["role_lens_sha256"] == "abc"
    with pytest.raises(SystemExit, match="--role applies to a live run"):
        runner.main(["--replay", str(f), "--role", "manager", "--out-dir", str(tmp_path)])


def test_an_unknown_role_is_rejected_at_the_command_line() -> None:
    with pytest.raises(SystemExit):
        runner.main(["--role", "executive", "--list"])


# ------------------------------------------------------------------------------- live: sends user_role, one loop
def test_live_run_sends_the_role_and_it_comes_back_on_every_answer() -> None:
    tag = uuid.uuid4().hex[:8]
    sid = f"SRC-T{tag}"
    ids: dict = {}

    async def _seed() -> None:
        async with async_session_factory() as s:
            did, cid = uuid.uuid4(), uuid.uuid4()
            s.add(Document(document_id=did, title="role eval policy", version="t", policy_type="generic_policy",
                           source_format=SourceFormat.md, ingest_status=IngestStatus.indexed,
                           eligibility=Eligibility.authority_pending, test_index_member=True, source_id=sid,
                           source_path=f"zz-{tag}.md"))
            await s.flush()
            s.add(Chunk(chunk_id=cid, document_id=did, ordinal=0, text="Staff may carry over seven days.", token_count=6))
            await s.commit()
            ids["d"], ids["c"] = did, cid

    asyncio.run(_seed())
    cases = [case(test_id="T-IN", source_id=sid, question="How many days can staff carry over?", must_include=("seven",))]
    seen_roles: list = []

    async def fake_scores(self, question, top_k):
        return {ids["c"]: 0.95}

    async def fake_generate(*, question, chunks, conversation_context=None, routing=None, role=None):
        seen_roles.append(role.key if role else None)
        return "Staff may carry over seven days.", False, [c.chunk_id for c in chunks], "{}"

    records: dict = {}
    try:
        with patch.object(VectorRetriever, "_pinecone_scores", fake_scores), \
             patch("ask_bpl_orchestrator.services.ask_service.generation.generate_answer", side_effect=fake_generate):
            records = asyncio.run(runner._run_live(cases, repeat=2, delay=0, role="manager"))
            no_role = asyncio.run(runner._run_live(cases, repeat=1, delay=0))
        assert seen_roles == ["manager", "manager", "general"]
        recs = records["T-IN"]
        assert all(r["role_requested"] == "manager" and r["payload"]["role"]["key"] == "manager" for r in recs)
        assert aggregate_status(cases[0], recs) == "PASS"
        assert "role_requested" not in no_role["T-IN"][0]  # no --role: the request and the record are as before
    finally:
        rids = [uuid.UUID(r["payload"]["request_id"]) for rs in (records.get("T-IN", []) + locals().get("no_role", {}).get("T-IN", []),)
                for r in rs if r["payload"].get("request_id")]

        async def _clean() -> None:
            async with async_session_factory() as s:
                for rid in rids:
                    await s.execute(delete(Question).where(Question.request_id == rid))
                await s.execute(delete(Chunk).where(Chunk.document_id == ids["d"]))
                await s.execute(delete(Document).where(Document.document_id == ids["d"]))
                await s.commit()

        asyncio.run(_clean())


def aggregate_status(c, recs) -> str:
    from ask_bpl_orchestrator.evals.scoring import aggregate

    return aggregate(c, recs)["status"]


# ------------------------------------------------------------------------------- compare
def _answer(text: str, role: str, cite: dict = CITE_OK) -> dict:
    return _with_role(answer_rec(text, cites=(cite,)), role)


BASE_TEXT = "Staff may carry over seven days. The rest goes to the sick leave bank."


def test_sentence_count_is_a_simple_advisory_split() -> None:
    assert sentence_count("") == 0
    assert sentence_count("One. Two! Three? Four.") == 4
    assert sentence_count("Only one sentence here") == 1
    assert sentence_count('She said "stop." Then left.') == 2


def test_identical_decisions_and_citations_raise_no_flags(tmp_path: Path) -> None:
    a = _run_file(tmp_path, "g.json", None, {"T1": [answer_rec(BASE_TEXT)] * 3})
    b = _run_file(tmp_path, "s.json", "staff", {"T1": [_answer(BASE_TEXT, "staff")] * 3})
    res = compare_runs([load_run(a), load_run(b)])
    assert res["labels"] == ["general", "staff"] and res["counts"] == {} and res["hard"] == 0


def test_a_stable_decision_that_changes_with_the_role_is_a_hard_flag(tmp_path: Path) -> None:
    a = _run_file(tmp_path, "g.json", None, {"T1": [answer_rec(BASE_TEXT)] * 3})
    b = _run_file(tmp_path, "m.json", "manager", {"T1": [refusal_rec()] * 3})
    res = compare_runs([load_run(a), load_run(b)])
    assert res["rows"][0]["flags"]["manager"] == ["DECISION_DIFFERS_STABLE"] and res["hard"] == 1


def test_a_difference_where_a_side_wavered_is_only_a_soft_flag(tmp_path: Path) -> None:
    a = _run_file(tmp_path, "g.json", None, {"T1": [answer_rec(BASE_TEXT), refusal_rec(), answer_rec(BASE_TEXT)]})
    b = _run_file(tmp_path, "s.json", "staff", {"T1": [_with_role(refusal_rec(), "staff")] * 3})
    res = compare_runs([load_run(a), load_run(b)])
    assert res["rows"][0]["flags"]["staff"] == ["DECISION_DIFFERS_UNSTABLE"] and res["hard"] == 0


def test_a_different_cited_document_set_is_flagged(tmp_path: Path) -> None:
    other = {"retrievable": True, "eligibility": "authority_pending", "title": "Sick Leave"}
    a = _run_file(tmp_path, "g.json", None, {"T1": [answer_rec(BASE_TEXT)]})
    b = _run_file(tmp_path, "s.json", "staff", {"T1": [_answer(BASE_TEXT, "staff", other)]})
    assert compare_runs([load_run(a), load_run(b)])["rows"][0]["flags"]["staff"] == ["CITATIONS_DIFFER"]


def test_a_longer_answer_than_the_baseline_is_flagged(tmp_path: Path) -> None:
    longer = BASE_TEXT + " As a supervisor, you approve it. You also file the form."
    a = _run_file(tmp_path, "g.json", None, {"T1": [answer_rec(BASE_TEXT)]})
    b = _run_file(tmp_path, "m.json", "manager", {"T1": [_answer(longer, "manager")]})
    assert compare_runs([load_run(a), load_run(b)])["rows"][0]["flags"]["manager"] == ["LONGER_THAN_BASELINE"]


def test_three_runs_compare_each_role_with_the_baseline(tmp_path: Path) -> None:
    a = _run_file(tmp_path, "g.json", None, {"T1": [answer_rec(BASE_TEXT)] * 2})
    b = _run_file(tmp_path, "s.json", "staff", {"T1": [_answer(BASE_TEXT, "staff")] * 2})
    c = _run_file(tmp_path, "m.json", "manager", {"T1": [refusal_rec()] * 2})
    res = compare_runs([load_run(p) for p in (a, b, c)])
    assert set(res["rows"][0]["flags"]) == {"manager"} and res["baseline"] == "general"


def test_cases_missing_from_a_file_are_skipped_and_named(tmp_path: Path) -> None:
    a = _run_file(tmp_path, "g.json", None, {"T1": [answer_rec(BASE_TEXT)], "T2": [answer_rec(BASE_TEXT)]})
    b = _run_file(tmp_path, "s.json", "staff", {"T1": [_answer(BASE_TEXT, "staff")]})
    res = compare_runs([load_run(a), load_run(b)])
    assert [r["test_id"] for r in res["rows"]] == ["T1"] and res["skipped_ids"] == ["T2"]


def test_bad_inputs_are_explained(tmp_path: Path) -> None:
    good = _run_file(tmp_path, "g.json", None, {"T1": [answer_rec(BASE_TEXT)]})
    with pytest.raises(CompareError, match="at least two"):
        compare_runs([load_run(good)])
    with pytest.raises(CompareError, match="same role label"):
        compare_runs([load_run(good), load_run(good)])
    (tmp_path / "x.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(CompareError, match="cannot read"):
        load_run(tmp_path / "x.json")
    (tmp_path / "y.json").write_text(json.dumps({"meta": {}}), encoding="utf-8")
    with pytest.raises(CompareError, match="no 'records'"):
        load_run(tmp_path / "y.json")


def test_the_csv_puts_answers_side_by_side_with_blank_review_columns(tmp_path: Path) -> None:
    a = _run_file(tmp_path, "g.json", None, {"T1": [answer_rec(BASE_TEXT)]})
    b = _run_file(tmp_path, "s.json", "staff", {"T1": [_answer("Ask your supervisor first.", "staff")]})
    path = write_compare_csv(compare_runs([load_run(a), load_run(b)]), tmp_path)
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    assert rows[0]["general_answer"] == BASE_TEXT and rows[0]["staff_answer"] == "Ask your supervisor first."
    assert rows[0]["question"] == "Q T1?" and rows[0]["general_cited"] == "Annual Leave"
    assert all(rows[0][c] == "" for c in REVIEW_COLUMNS)


def test_main_compare_exit_codes_and_no_asking(tmp_path: Path) -> None:
    g = _run_file(tmp_path, "g.json", None, {"T1": [answer_rec(BASE_TEXT)] * 3})
    ok = _run_file(tmp_path, "s.json", "staff", {"T1": [_answer(BASE_TEXT, "staff")] * 3})
    bad = _run_file(tmp_path, "m.json", "manager", {"T1": [refusal_rec()] * 3})
    with patch.object(runner, "_run_live", side_effect=AssertionError("must not ask")):
        assert runner.main(["--compare", str(g), str(ok), "--out-dir", str(tmp_path)]) == 0
        assert runner.main(["--compare", str(g), str(bad), "--out-dir", str(tmp_path)]) == 1
    with pytest.raises(SystemExit, match="cannot compare"):
        runner.main(["--compare", str(g), "--out-dir", str(tmp_path)])
    with pytest.raises(SystemExit, match="do not combine"):
        runner.main(["--compare", str(g), str(ok), "--role", "staff"])


def test_main_compare_exits_nonzero_on_a_role_echo_failure(tmp_path: Path) -> None:
    g = _run_file(tmp_path, "g.json", None, {"T1": [answer_rec(BASE_TEXT)]})
    s = _run_file(tmp_path, "s.json", "staff", {"T1": [_answer(BASE_TEXT, "staff")]})
    data = json.loads(s.read_text())
    data["results"][0]["failed_checks"] = ["role_echo"]
    s.write_text(json.dumps(data), encoding="utf-8")
    assert runner.main(["--compare", str(g), str(s), "--out-dir", str(tmp_path)]) == 1
