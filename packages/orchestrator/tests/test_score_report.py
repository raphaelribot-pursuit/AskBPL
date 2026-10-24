"""Patch 0018: the retrieval-gate log event and `askbpl-score-report` (PRD GRD-2).

What these tests protect:
  * the new `retrieval_gate` log event only REPORTS: the gate decides exactly as before at every boundary;
  * the event holds numbers and flags only, never the question, a chunk or a title;
  * the report joins results to the log by `request_id` (never by order), says so when a log line is missing or
    predates this patch, and never claims more than the recorded runs show;
  * the report is read-only: it never opens the database.

No network. The model and the vector search are faked.
"""

from __future__ import annotations

import csv
import json
import logging
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from ask_bpl_orchestrator import score_report as sr
from ask_bpl_orchestrator.config import get_settings
from ask_bpl_orchestrator.db.models import Question
from ask_bpl_orchestrator.db.session import async_session_factory
from ask_bpl_orchestrator.main import app
from ask_bpl_orchestrator.services.retrieval import RetrievedChunk, VectorRetriever

SETTINGS = get_settings()
FLOOR, STRONG = SETTINGS.grounding_threshold, SETTINGS.grounding_strong_threshold

# The three ask_completed lines the team's live run wrote for ROB-ST-01 (2026-10-20, commit b779420), verbatim.
REAL_LOG = """\
2026-10-20 22:08:44,911 INFO ask_bpl_orchestrator.services.ask_service: {"event": "ask_completed", "request_id": "4b7a4632-7025-4e5a-ade8-f97bcc4e3eb6", "timestamp": "2026-10-21T02:08:44.911334+00:00", "session": "anonymous", "retrieval_hit": true, "chunks_returned": 6, "top_score": 0.402305067, "grounding_passed": false, "refusal": true, "refusal_reason": "weak_evidence", "inferred_policy_type": "technology_usage_policy", "routing_teams": ["Information Technology"], "citation_verified": false, "latency_ms": 1659.549, "refusal_stage": "retrieval_gate"}
2026-10-20 22:08:46,137 INFO ask_bpl_orchestrator.services.ask_service: {"event": "ask_completed", "request_id": "5fb1b3cf-7625-4054-929c-28fd69fd8aef", "timestamp": "2026-10-21T02:08:46.137728+00:00", "session": "anonymous", "retrieval_hit": true, "chunks_returned": 6, "top_score": 0.402305067, "grounding_passed": false, "refusal": true, "refusal_reason": "weak_evidence", "inferred_policy_type": "technology_usage_policy", "routing_teams": ["Information Technology"], "citation_verified": false, "latency_ms": 711.775, "refusal_stage": "retrieval_gate"}
2026-10-20 22:08:47,336 INFO ask_bpl_orchestrator.services.ask_service: {"event": "ask_completed", "request_id": "150ecd06-e632-49d6-9f78-73f95f1dcf47", "timestamp": "2026-10-21T02:08:47.335975+00:00", "session": "anonymous", "retrieval_hit": true, "chunks_returned": 6, "top_score": 0.402305067, "grounding_passed": false, "refusal": true, "refusal_reason": "weak_evidence", "inferred_policy_type": "technology_usage_policy", "routing_teams": ["Information Technology"], "citation_verified": false, "latency_ms": 687.524, "refusal_stage": "retrieval_gate"}
"""
REAL_IDS = ["4b7a4632-7025-4e5a-ade8-f97bcc4e3eb6", "5fb1b3cf-7625-4054-929c-28fd69fd8aef",
            "150ecd06-e632-49d6-9f78-73f95f1dcf47"]


# ----------------------------------------------------------------------------- helpers for the report tests
ANSWERABLE = {"found": True, "retrievable": True, "eligibility": "authority_pending", "source_id": "SRC-X"}  # as the runner records it


def refusal_rec(rid: str | None) -> Dict[str, Any]:
    payload = {"type": "refusal_oo_corpus", "refusal_explanation": "I could not find enough approved policy information."}
    if rid:
        payload["request_id"] = rid
    return {"http_status": 200, "payload": payload, "citation_states": [], "group_state": ANSWERABLE}


def answer_rec(rid: str) -> Dict[str, Any]:
    cites = [{"chunk_id": "c1", "retrievable": True, "eligibility": "eligible", "source_id": "SRC-22"}]
    return {"http_status": 200, "payload": {"type": "answer", "answer": "Answer text.", "request_id": rid,
                                            "citations": [{"chunk_id": "c1"}]}, "citation_states": cites, "group_state": ANSWERABLE}


def log_line(event: str, rid: str, **kw: Any) -> str:
    return "2026-10-21 02:00:00,000 INFO x: " + json.dumps({"event": event, "request_id": rid, **kw})


def completed(rid: str, top: float | None, stage: str | None = None, reason: str | None = None, n: int = 6) -> str:
    return log_line("ask_completed", rid, top_score=top, chunks_returned=n, refusal_reason=reason, refusal_stage=stage)


def gate(rid: str, top: float, second: float | None, at_floor: int, passed: bool = False, n: int = 6) -> str:
    return log_line("retrieval_gate", rid, top_score=top, second_score=second, chunks_at_floor=at_floor, chunks_returned=n,
                    floor=0.40, strong=0.45, passed=passed, passed_by=None)


def write(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def results_file(tmp_path: Path, records: Dict[str, List[Dict[str, Any]]], **meta: Any) -> Path:
    return write(tmp_path, "run.json", json.dumps({"meta": meta, "records": records}))


# ----------------------------------------------------------------------------- the log reader
def test_the_reader_parses_the_real_log_format(tmp_path: Path) -> None:
    log = write(tmp_path, "app.log", "starting up\n" + REAL_LOG + "not json {\"event\": broken\n")
    events = sr.read_log_events([log])
    assert set(events) == set(REAL_IDS)
    e = events[REAL_IDS[0]]["ask_completed"]
    assert e["top_score"] == 0.402305067 and e["refusal_stage"] == "retrieval_gate"


def test_the_reader_ignores_other_events_and_lines_without_a_request_id(tmp_path: Path) -> None:
    log = write(tmp_path, "app.log", "\n".join([
        log_line("glossary", "r1", matched_terms=1),
        'x: {"event": "ask_completed", "top_score": 0.5}',
        completed("r2", 0.5),
    ]))
    assert set(sr.read_log_events([log])) == {"r2"}


def test_the_reader_merges_several_logs(tmp_path: Path) -> None:
    a, b = write(tmp_path, "a.log", completed("r1", 0.41)), write(tmp_path, "b.log", completed("r2", 0.42))
    assert set(sr.read_log_events([a, b])) == {"r1", "r2"}


# ----------------------------------------------------------------------------- the join
def _rows(tmp_path: Path, records, log_text: str):
    run = json.loads(results_file(tmp_path, records).read_text())
    return sr.build_rows([run], sr.read_log_events([write(tmp_path, "app.log", log_text)]), sr.all_cases())


def test_join_is_by_request_id_not_by_order(tmp_path: Path) -> None:
    records = {"ROB-ST-01": [refusal_rec("r1"), refusal_rec("r2"), refusal_rec("r3")]}
    # the log lists the asks in a different order from the results
    log = "\n".join([completed("r3", 0.43, "retrieval_gate", "weak_evidence"),
                     completed("r1", 0.41, "retrieval_gate", "weak_evidence"),
                     completed("r2", 0.42, "retrieval_gate", "weak_evidence")])
    rows = _rows(tmp_path, records, log)
    assert [r.top for r in rows] == [0.41, 0.42, 0.43]
    assert all(r.joined for r in rows)


def test_extra_log_lines_from_other_asks_do_not_shift_anything(tmp_path: Path) -> None:
    records = {"ROB-ST-01": [refusal_rec("r1")]}
    log = "\n".join([completed("zz1", 0.9), completed("zz2", 0.8), completed("r1", 0.41, "retrieval_gate", "weak_evidence")])
    (row,) = _rows(tmp_path, records, log)
    assert row.top == 0.41


def test_an_ask_with_no_log_line_is_flagged_not_guessed(tmp_path: Path) -> None:
    rows = _rows(tmp_path, {"ROB-ST-01": [refusal_rec("missing"), refusal_rec(None)]}, completed("other", 0.5))
    assert [r.joined for r in rows] == [False, False] and all(r.top is None for r in rows)
    text = sr.render(rows, 0.40, 0.45)
    assert "no log line" in text and "2 ask(s)" in text


def test_the_real_log_lines_join_to_the_real_case(tmp_path: Path) -> None:
    records = {"ROB-ST-01": [refusal_rec(r) for r in REAL_IDS]}
    rows = _rows(tmp_path, records, REAL_LOG)
    assert [round(r.top, 4) for r in rows] == [0.4023] * 3
    assert {r.reason for r in rows} == {"weak_evidence"} and {r.stage for r in rows} == {"retrieval_gate"}
    assert {r.kind for r in rows} == {sr.OVER_REFUSED}  # ROB-ST-01 expects an answer
    assert {r.status for r in rows} == {"FAIL"}  # scored by the same scorer the runner uses
    text = sr.render(rows, 0.40, 0.45)
    assert "before patch 0018" in text  # the old log has no gate event


def test_old_logs_show_the_best_score_and_no_gate_fields(tmp_path: Path) -> None:
    (row,) = _rows(tmp_path, {"ROB-ST-01": [refusal_rec("r1")]}, completed("r1", 0.41, "retrieval_gate", "weak_evidence"))
    assert row.joined and not row.gate_known and row.top == 0.41 and row.second is None and row.at_floor is None


def test_a_new_log_gives_second_score_and_chunks_at_floor(tmp_path: Path) -> None:
    log = completed("r1", 0.4023, "retrieval_gate", "weak_evidence") + "\n" + gate("r1", 0.4023, 0.3611, 1)
    (row,) = _rows(tmp_path, {"ROB-ST-01": [refusal_rec("r1")]}, log)
    assert row.gate_known and row.second == 0.3611 and row.at_floor == 1
    assert "before patch 0018" not in sr.render([row], 0.40, 0.45)


def test_unknown_case_ids_are_kept_with_a_question_mark(tmp_path: Path) -> None:
    (row,) = _rows(tmp_path, {"NOT-A-CASE": [refusal_rec("r1")]}, completed("r1", 0.5))
    assert row.expect == "?" and row.status == "?" and row.kind == sr.UNSCORED


# ----------------------------------------------------------------------------- classification
@pytest.mark.parametrize("expect,outcome,kind", [
    ("answer", "answer", sr.ANSWERED_OK), ("answer", "refusal", sr.OVER_REFUSED),
    ("refusal", "refusal", sr.REFUSED_OK), ("refusal", "answer", sr.ANSWERED_WRONG),
    ("either", "answer", sr.UNSCORED), ("either", "refusal", sr.UNSCORED),
    ("pii_reject", "pii_reject", sr.UNSCORED), ("crisis", "crisis", sr.UNSCORED),
    ("answer", "error", sr.UNSCORED), ("refusal", "error", sr.UNSCORED),
])
def test_classification_table(expect: str, outcome: str, kind: str) -> None:
    assert sr.classify(expect, outcome) == kind


# ----------------------------------------------------------------------------- the summary
def _scenario(tmp_path: Path):
    """ROB-ST-01 (answer expected) refused at 0.4023 twice; ROB-UI-02 and BPL-UC-05 (refusal expected) stopped at the gate;
    ROB-LD-01 answered; ROB-UI-01 refused later by the model; ROB-MS-01 ('either') ignored."""
    records = {
        "ROB-ST-01": [refusal_rec("a1"), refusal_rec("a2")],
        "ROB-UI-02": [refusal_rec("b1")],
        "BPL-UC-05": [refusal_rec("b2")],
        "ROB-LD-01": [answer_rec("c1")],
        "ROB-UI-01": [refusal_rec("d1")],
        "ROB-MS-01": [refusal_rec("e1")],
        "ROB-LD-02": [refusal_rec("f1")],  # answer expected, but the MODEL refused after the gate let it through
    }
    log = "\n".join([
        completed("a1", 0.4023, "retrieval_gate", "weak_evidence"), gate("a1", 0.4023, 0.3611, 1),
        completed("a2", 0.4023, "retrieval_gate", "weak_evidence"), gate("a2", 0.4023, 0.3500, 1),
        completed("b1", 0.3000, "retrieval_gate", "absent_source"), gate("b1", 0.30, 0.25, 0),
        completed("b2", 0.4200, "retrieval_gate", "weak_evidence"), gate("b2", 0.42, 0.38, 1),
        completed("c1", 0.4800), gate("c1", 0.48, 0.41, 2, passed=True),
        completed("d1", 0.4600, "generation", "weak_evidence"), gate("d1", 0.46, 0.20, 1, passed=True),
        completed("e1", 0.3500, "retrieval_gate", "absent_source"),
        completed("f1", 0.4700, "generation", "weak_evidence"), gate("f1", 0.47, 0.30, 1, passed=True),
    ])
    return _rows(tmp_path, records, log)


def test_over_refusals_are_listed_with_both_shortfalls(tmp_path: Path) -> None:
    text = sr.render(_scenario(tmp_path), 0.40, 0.45)
    section = text.split("-- Over-refusals")[1].split("--")[0]
    assert "ROB-ST-01" in section
    assert "0.0477" in section  # 0.45 - 0.4023
    assert "0.0389" in section  # 0.40 - 0.3611 (second chunk shortfall)
    assert section.count("ROB-ST-01") == 2


def test_only_gate_stopped_refusals_form_the_protected_group(tmp_path: Path) -> None:
    rows = _scenario(tmp_path)
    text = sr.render(rows, 0.40, 0.45)
    import re

    assert re.search(r"refused at the gate, refusal expected\s+n=2\b", text)  # ROB-UI-02 and BPL-UC-05, not ROB-UI-01
    assert "refused later (model/citation), refusal expected: 1 run(s)" in text
    assert "ROB-MS-01" not in text.split("-- Best score")[1]  # 'either' takes no part


def test_what_if_counts_recorded_runs_at_each_cut_off(tmp_path: Path) -> None:
    text = sr.render(_scenario(tmp_path), 0.40, 0.45)
    table = {line.split()[0]: line for line in text.split("-- What-if")[1].splitlines() if line.strip()[:1] == "0"}
    assert "2 of 2" in table["0.400"] and "1 of 2" in table["0.400"]  # both over-refusals; only b2 (0.42) is >= 0.40
    assert "0 of 2" in table["0.430"] and "0 of 2" in table["0.450"]  # nothing is admitted at 0.43 or above
    # a run scoring exactly on a cut-off is admitted at that cut-off (0.42 >= 0.42), not lost to float error
    assert "0 of 2" in table["0.420"] and "1 of 2" in table["0.420"]
    assert "1 of 2" in table["0.420"] and "0 of 2" in table["0.430"]


def test_a_refusal_after_the_gate_is_not_a_threshold_problem_and_stays_out_of_the_what_if(tmp_path: Path) -> None:
    text = sr.render(_scenario(tmp_path), 0.40, 0.45)
    what_if = text.split("-- What-if")[1]
    assert "1 over-refusal run(s) were refused after the gate" in what_if
    assert "of 2" in what_if and "of 3" not in what_if  # ROB-ST-01 twice; ROB-LD-02 (0.47, refused by the model) is excluded
    assert "ROB-LD-02" in text.split("-- Over-refusals")[1].split("--")[0]  # but it is still listed for reading


def test_overlap_is_reported_when_scores_do_not_separate_the_groups(tmp_path: Path) -> None:
    text = sr.render(_scenario(tmp_path), 0.40, 0.45)  # protected max 0.42 > over-refusals at 0.4023
    assert "Highest score among gate-stopped expected refusals: 0.4200" in text
    assert "score alone does not separate" in text


def test_separation_is_reported_when_every_over_refusal_scores_higher(tmp_path: Path) -> None:
    records = {"ROB-ST-01": [refusal_rec("a1")], "ROB-UI-02": [refusal_rec("b1")]}
    log = "\n".join([completed("a1", 0.44, "retrieval_gate", "weak_evidence"), gate("a1", 0.44, 0.30, 1),
                     completed("b1", 0.35, "retrieval_gate", "absent_source"), gate("b1", 0.35, 0.30, 0)])
    text = sr.render(_rows(tmp_path, records, log), 0.40, 0.45)
    assert "would separate these runs" in text


def test_answers_where_a_refusal_was_expected_are_listed_for_reading(tmp_path: Path) -> None:
    records = {"BPL-AL-05": [answer_rec("a1")]}
    text = sr.render(_rows(tmp_path, records, completed("a1", 0.47) + "\n" + gate("a1", 0.47, 0.41, 2, passed=True)), 0.40, 0.45)
    assert "Answered although a refusal was expected" in text and "BPL-AL-05" in text


def test_the_report_states_that_it_is_evidence_not_a_recommendation(tmp_path: Path) -> None:
    text = sr.render(_scenario(tmp_path), 0.40, 0.45)
    assert "not a recommendation" in text and "full before-and-after run" in text


def test_an_empty_comparison_does_not_crash(tmp_path: Path) -> None:
    rows = _rows(tmp_path, {"ROB-LD-01": [answer_rec("c1")]}, completed("c1", 0.5))
    text = sr.render(rows, 0.40, 0.45)
    assert "answered, answer expected" in text and "What-if" not in text


# ----------------------------------------------------------------------------- the command
def test_cli_prints_and_writes_csv_and_reads_thresholds_from_the_results(tmp_path: Path, capsys) -> None:
    res = results_file(tmp_path, {"ROB-ST-01": [refusal_rec(r) for r in REAL_IDS]}, grounding_floor=0.4, grounding_strong=0.45)
    log, out = write(tmp_path, "app.log", REAL_LOG), tmp_path / "scores.csv"
    assert sr.main([str(res), "--log", str(log), "--csv", str(out)]) == 0
    shown = capsys.readouterr().out
    assert "floor 0.4, strong 0.45" in shown and "ROB-ST-01" in shown and f"written: {out}" in shown
    rows = list(csv.DictReader(open(out, encoding="utf-8")))
    assert len(rows) == 3 and {r["top_score"] for r in rows} == {"0.402305067"} and rows[0]["joined_to_log"] == "True"


def test_cli_flags_override_the_thresholds_and_summary_only_skips_the_table(tmp_path: Path, capsys) -> None:
    res = results_file(tmp_path, {"ROB-ST-01": [refusal_rec(REAL_IDS[0])]})
    log = write(tmp_path, "app.log", REAL_LOG)
    assert sr.main([str(res), "--log", str(log), "--floor", "0.3", "--strong", "0.5", "--summary-only"]) == 0
    shown = capsys.readouterr().out
    assert "floor 0.3, strong 0.5" in shown and "refusal_reason" not in shown.splitlines()[0]


def test_cli_accepts_several_results_and_logs(tmp_path: Path, capsys) -> None:
    r1 = results_file(tmp_path, {"ROB-ST-01": [refusal_rec("r1")]})
    r2 = write(tmp_path, "run2.json", json.dumps({"meta": {}, "records": {"ROB-UI-02": [refusal_rec("r2")]}}))
    l1, l2 = write(tmp_path, "1.log", completed("r1", 0.41, "retrieval_gate", "weak_evidence")), write(tmp_path, "2.log", completed("r2", 0.3))
    assert sr.main([str(r1), str(r2), "--log", str(l1), str(l2)]) == 0
    assert "2 recorded asks" in capsys.readouterr().out


def test_cli_exits_2_on_bad_input_and_zero_for_findings(tmp_path: Path, capsys) -> None:
    good = results_file(tmp_path, {"ROB-ST-01": [refusal_rec("r1")]})
    log = write(tmp_path, "app.log", "")
    assert sr.main([str(tmp_path / "nope.json"), "--log", str(log)]) == 2
    assert sr.main([str(good), "--log", str(tmp_path / "nope.log")]) == 2
    bad = write(tmp_path, "bad.json", "{not json")
    assert sr.main([str(bad), "--log", str(log)]) == 2
    nothing = write(tmp_path, "empty.json", json.dumps({"meta": {}, "records": {}}))
    assert sr.main([str(nothing), "--log", str(log)]) == 2
    norec = write(tmp_path, "norec.json", json.dumps({"meta": {}}))
    assert sr.main([str(norec), "--log", str(log)]) == 2
    assert sr.main([str(good), "--log", str(log)]) == 0  # unjoined asks are reported, not an error
    assert "no log line" in capsys.readouterr().out


def test_the_report_never_imports_the_database() -> None:
    code = ("import sys; import ask_bpl_orchestrator.score_report as m; "
            "bad = [n for n in sys.modules if n.startswith(('sqlalchemy', 'asyncpg', 'pinecone', 'anthropic', 'openai'))]; "
            "print(','.join(sorted(bad)))")
    out = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1])
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "", f"read-only report imported: {out.stdout.strip()}"


def test_the_command_is_registered() -> None:
    assert 'askbpl-score-report = "ask_bpl_orchestrator.score_report:main"' in (
        Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")


# ----------------------------------------------------------------------------- the log event, through the real ask pipeline
client = TestClient(app)
GENERATE = "ask_bpl_orchestrator.services.ask_service.generation.generate_answer"
QUESTION = "Can I install instant messaging software on my work computer?"


@pytest.fixture(autouse=True)
def _no_live_vector_lookup():
    with patch.object(VectorRetriever, "_pinecone_scores", new_callable=AsyncMock, return_value={}):
        yield


def _chunk(score: float) -> RetrievedChunk:
    return RetrievedChunk(chunk_id=uuid.uuid4(), score=score, document_id=uuid.uuid4(), title="Gate Test Doc",
                          policy_type="generic_policy", version="g-1", section_heading=None,
                          text="Installation of software requires approval.")


def _ask(question: str) -> Any:
    token = client.post("/auth/sign-in", json={"email": "pilot-demo@bklynlibrary.org", "access_code": "DEMO2026",
                                               "attribution_mode": "anonymous"}).json()["token"]
    return client.post("/questions/ask", headers={"Authorization": f"Bearer {token}"}, json={"question": question})


def _forget(rid: str) -> None:
    import asyncio

    async def go() -> None:
        async with async_session_factory() as s:
            await s.execute(delete(Question).where(Question.request_id == uuid.UUID(rid)))
            await s.commit()

    asyncio.run(go())


def _run(scores: List[float], caplog: pytest.LogCaptureFixture):
    """Ask once with fake search results at the given scores. Returns (response body, model mock, gate event, raw lines)."""
    caplog.clear()
    caplog.set_level(logging.INFO)
    chunks = [_chunk(s) for s in scores]
    model = AsyncMock(return_value=("", True, [], '{"answer": "", "refuse": true, "cited_chunk_ids": []}'))

    async def fake(self_: VectorRetriever, db: Any, question: str, top_k: int) -> List[RetrievedChunk]:
        self_.excluded_best_score = 0.0
        return chunks

    with patch.object(VectorRetriever, "query", fake), patch(GENERATE, model):
        r = _ask(QUESTION)
    body = r.json()
    msgs = [rec.getMessage() for rec in caplog.records]
    events = [json.loads(m) for m in msgs if m.startswith("{") and '"event": "retrieval_gate"' in m]
    _forget(body["request_id"])
    return body, model, events, msgs


# (scores, decision the gate must make, chunks at the floor, passed_by). Boundaries first: the decision is the OLD one.
GATE_CASES = [
    ([0.4023, 0.36, 0.30], False, 1, None),  # the ROB-ST-01 shape: one chunk just over the floor
    ([STRONG], True, 1, "strong"),  # exactly the strong threshold
    ([STRONG - 0.0001], False, 1, None),  # a hair below it
    ([FLOOR, FLOOR], True, 2, "two_at_floor"),  # two chunks exactly at the floor
    ([FLOOR, FLOOR - 0.0001], False, 1, None),  # the second a hair short
    ([0.46, 0.41], True, 2, "strong"),  # both rules hold: reported as strong
    ([0.35, 0.30], False, 0, None),  # everything below the floor
    ([], False, 0, None),  # nothing retrieved
]


@pytest.mark.parametrize("scores,passes,at_floor,passed_by", GATE_CASES)
def test_the_gate_decides_exactly_as_before_and_the_event_reports_it(scores, passes, at_floor, passed_by, caplog) -> None:
    body, model, events, _ = _run(scores, caplog)
    assert len(events) == 1
    ev = events[0]
    assert ev["request_id"] == body["request_id"]
    assert ev["passed"] is passes and ev["passed_by"] == passed_by and ev["chunks_at_floor"] == at_floor
    assert ev["chunks_returned"] == len(scores)
    assert ev["floor"] == FLOOR and ev["strong"] == STRONG
    assert ev["top_score"] == (max(scores) if scores else 0.0)
    ranked = sorted(scores, reverse=True)
    assert ev["second_score"] == (ranked[1] if len(ranked) > 1 else None)
    # the decision itself: the model is reached only when the gate passes
    assert (model.await_count == 1) is passes
    if not passes:
        assert body["type"] == "refusal_oo_corpus"


def test_the_event_holds_numbers_and_flags_only(caplog) -> None:
    _, _, events, msgs = _run([0.4023], caplog)
    raw = next(m for m in msgs if '"event": "retrieval_gate"' in m)
    for forbidden in ("install", "instant", "software", "computer", "Gate Test Doc", "approval", "generic_policy"):
        assert forbidden.lower() not in raw.lower()
    assert set(events[0]) == {"event", "request_id", "chunks_returned", "top_score", "second_score", "chunks_at_floor",
                              "floor", "strong", "passed", "passed_by"}


def test_the_event_and_the_completion_line_share_a_request_id_and_join_in_the_report(caplog, tmp_path: Path) -> None:
    body, _, _, msgs = _run([0.4023, 0.36], caplog)
    log = write(tmp_path, "app.log", "\n".join(f"x: {m}" for m in msgs if m.startswith("{")))
    got = sr.read_log_events([log])[body["request_id"]]
    assert set(got) == {"ask_completed", "retrieval_gate"}
    assert got["ask_completed"]["top_score"] == got["retrieval_gate"]["top_score"] == 0.4023
    assert got["ask_completed"]["refusal_stage"] == "retrieval_gate"
    # and the report sees it end to end
    run = {"meta": {}, "records": {"ROB-ST-01": [{"http_status": 200, "payload": body, "citation_states": [], "group_state": None}]}}
    (row,) = sr.build_rows([run], sr.read_log_events([log]), sr.all_cases())
    assert row.gate_known and row.at_floor == 1 and row.second == 0.36 and row.kind == sr.OVER_REFUSED


def test_a_question_stopped_before_retrieval_logs_no_gate_event(caplog) -> None:
    caplog.set_level(logging.INFO)
    r = _ask("Can jane.synthetic@example.com take annual leave starting Monday?")
    assert r.json()["type"] == "error_pii"
    assert not any('"event": "retrieval_gate"' in rec.getMessage() for rec in caplog.records)
    rid = r.json().get("request_id")
    if rid:
        _forget(rid)
