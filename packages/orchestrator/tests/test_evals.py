"""Evaluation runner (PRD EVAL-3/5, Document 06). Scoring is pure; live path is exercised with a faked pipeline."""

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
from ask_bpl_orchestrator.evals.cases import CLIENT_CSV, REGRESSION_CSV, Case, load_cases, questions_sha256
from ask_bpl_orchestrator.evals.scoring import aggregate, outcome_of, score_run, summarize
from ask_bpl_orchestrator.services.retrieval import VectorRetriever

# Freeze check (Document 06 s.4): if this fails, someone edited the client's wording. Do not "fix" the hash.
CLIENT_WORDING_SHA256 = "9d8dfe4e9e96182cc1e77d5cbd63f840d6517cedc284ffeea88b28384963ab5f"


# ------------------------------------------------------------------ fixtures
def test_client_set_is_the_frozen_thirty() -> None:
    cases = load_cases(CLIENT_CSV)
    assert len(cases) == 30
    assert questions_sha256(cases) == CLIENT_WORDING_SHA256
    groups: dict[str, list[Case]] = {}
    for c in cases:
        groups.setdefault(c.group, []).append(c)
    assert len(groups) == 6
    for g, cs in groups.items():
        assert [c.cls for c in cs] == ["IN", "IN", "IN", "IN", "OUT"], g
        assert all(c.test_id.startswith("BPL-") for c in cs)
    assert all(c.reference_status != "BPL_APPROVED" for c in cases)  # no approved key exists


def test_team_cases_are_kept_separate_from_client_ids() -> None:
    reg = load_cases(REGRESSION_CSV)
    assert reg and not any(c.test_id.startswith("BPL-") for c in reg)
    assert {c.cls for c in reg} <= {"REG", "SEC"}


def test_loader_rejects_duplicate_ids(tmp_path: Path) -> None:
    p = tmp_path / "c.csv"
    header = "test_id,group,source_id,cls,question,expect,must_include,must_not_include,reference_status,reference_evidence,note\n"
    p.write_text(header + "X-1,g,,REG,q?,answer,,,PENDING,,\nX-1,g,,REG,q2?,answer,,,PENDING,,\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_cases(p)


# ------------------------------------------------------------------ scoring
def case(**kw) -> Case:
    base = dict(test_id="T-1", group="g", source_id="SRC-X", cls="IN", question="q?", expect="answer",
                must_include=(), must_not_include=(), reference_status="PENDING", reference_evidence="", note="")
    base.update(kw)
    return Case(**base)


GROUP_OK = {"found": True, "retrievable": True, "eligibility": "authority_pending"}
GROUP_BLOCKED = {"found": True, "retrievable": False, "eligibility": "blocked"}
CITE_OK = {"retrievable": True, "eligibility": "authority_pending", "title": "Annual Leave"}


def answer_rec(text="Up to 7 days, rest to sick leave bank.", cites=(CITE_OK,), label="Test index: ...", group=GROUP_OK):
    payload = {"type": "answer", "answer": text, "citations": [{"chunk_id": "c"}] * len(cites)}
    if label:
        payload["index_label"] = label
    return {"http_status": 200, "payload": payload, "citation_states": list(cites), "group_state": group}


def refusal_rec(kind="refusal_oo_corpus", group=GROUP_OK):
    return {"http_status": 200, "payload": {"type": kind, "refusal_explanation": "Not covered.", "citations": []},
            "citation_states": [], "group_state": group}


def test_outcome_mapping() -> None:
    assert outcome_of(200, {"type": "answer"}) == "answer"
    assert outcome_of(200, {"type": "refusal_citation_invalid"}) == "refusal"
    assert outcome_of(400, {"type": "error_pii"}) == "pii_reject"
    assert outcome_of(200, {"type": "crisis_resource"}) == "crisis"
    assert outcome_of(502, {"type": "error_upstream"}) == "error"


def test_good_answer_passes_but_is_provisional_while_authority_pending() -> None:
    s = score_run(case(must_include=("7", "sick leave")), answer_rec())
    assert s.status == "PASS" and s.provisional


def test_missing_expected_fact_fails() -> None:
    assert score_run(case(must_include=("90",)), answer_rec("Probably a few months.")).status == "FAIL"


def test_forbidden_text_fails() -> None:
    s = score_run(case(must_not_include=("collective bargaining",)),
                  answer_rec("Union staff follow their collective bargaining agreement."))
    assert s.status == "FAIL" and "must_not_include" in s.failed


def test_answer_without_citations_fails() -> None:
    assert score_run(case(), answer_rec(cites=())).status == "FAIL"


def test_citation_to_non_answerable_document_always_fails() -> None:
    bad = {"retrievable": False, "eligibility": "blocked"}
    s = score_run(case(), answer_rec(cites=(bad,)))
    assert s.status == "FAIL" and "citation_integrity" in s.failed


def test_citing_a_blocked_document_fails_even_when_its_own_policy_is_blocked() -> None:
    """The leak case: the policy is blocked, yet an answer displays a citation to a non-answerable document."""
    bad = {"retrievable": False, "eligibility": "blocked"}
    s = score_run(case(), answer_rec(cites=(bad,), group=GROUP_BLOCKED))
    assert s.status == "FAIL" and "citation_integrity" in s.failed  # not downgraded to REVIEW/BLOCKED


def test_missing_test_index_label_fails() -> None:
    s = score_run(case(), answer_rec(label=None))
    assert s.status == "FAIL" and "test_index_label" in s.failed


def test_expected_answer_but_got_refusal_fails() -> None:
    assert score_run(case(), refusal_rec()).status == "FAIL"


def test_verifier_refusal_is_flagged() -> None:
    s = score_run(case(cls="OUT", expect="refusal"), refusal_rec("refusal_citation_invalid"))
    assert s.status == "PASS" and any("verifier" in w for w in s.warnings)


def test_out_of_scope_refusal_passes_and_answer_needs_review() -> None:
    assert score_run(case(cls="OUT", expect="refusal"), refusal_rec()).status == "PASS"
    assert score_run(case(cls="OUT", expect="refusal"), answer_rec()).status == "REVIEW"


def test_blocked_policy_is_not_evaluable_and_answers_need_review() -> None:
    blocked = score_run(case(), refusal_rec(group=GROUP_BLOCKED))
    assert blocked.status == "BLOCKED" and any("NOT EVALUABLE" in w for w in blocked.warnings)
    assert score_run(case(cls="OUT", expect="refusal"), refusal_rec(group=GROUP_BLOCKED)).status == "BLOCKED"
    assert score_run(case(), answer_rec(group=GROUP_BLOCKED)).status == "REVIEW"
    assert score_run(case(), {"http_status": 200, "payload": {"type": "refusal_oo_corpus"}, "group_state": None}).status == "BLOCKED"


def test_infrastructure_errors_are_reported_as_error_not_as_wrong_answers() -> None:
    err = {"http_status": 502, "payload": {"type": "error_upstream", "message": "AI generation service error."},
           "citation_states": [], "group_state": GROUP_OK}
    s = score_run(case(), err)
    assert s.status == "ERROR" and s.outcome == "error"
    assert score_run(case(cls="OUT", expect="refusal"), err).status == "ERROR"
    client_side = {"http_status": 0, "payload": {"type": "error_client", "message": "RuntimeError: Event loop is closed"}}
    assert score_run(case(), client_side).status == "ERROR"
    # one errored repeat makes the case ERROR (worst status), and the summary counts it separately
    r = aggregate(case(), [answer_rec(), err])
    assert r["status"] == "ERROR"


def test_summary_counts_error_cases_separately_and_excludes_them_from_rates() -> None:
    cl = case(test_id="BPL-AL-01", cls="IN")
    err = {"http_status": 502, "payload": {"type": "error_upstream"}, "citation_states": [], "group_state": GROUP_OK}
    res = [aggregate(cl, [err])]
    s = summarize(res, {"BPL-AL-01": [err]})
    assert s["client_set"]["ERROR"] == 1 and s["client_set"]["FAIL"] == 0
    assert s["in_scope_automated_pass"]["evaluable"] == 0


def test_replay_exits_nonzero_when_a_case_errored(tmp_path: Path) -> None:
    f = tmp_path / "recorded.json"
    err = {"http_status": 502, "payload": {"type": "error_upstream"}}
    f.write_text(json.dumps({"meta": {}, "records": {"REG-AL-02": [err]}}), encoding="utf-8")
    assert runner.main(["--replay", str(f), "--only", "REG-AL-02", "--out-dir", str(tmp_path)]) == 1


def test_pii_crisis_and_either_expectations() -> None:
    pii = {"http_status": 400, "payload": {"type": "error_pii", "message": "Personal information was detected."}}
    assert score_run(case(source_id="", cls="SEC", expect="pii_reject"), pii).status == "PASS"
    assert score_run(case(source_id="", cls="SEC", expect="pii_reject"), answer_rec(group=None)).status == "FAIL"
    crisis = {"http_status": 200, "payload": {"type": "crisis_resource", "message": "help"}}
    assert score_run(case(source_id="", cls="SEC", expect="crisis"), crisis).status == "PASS"
    assert score_run(case(expect="either"), refusal_rec()).status == "PASS"


def test_repeat_runs_take_the_worst_status() -> None:
    good, bad = answer_rec(), refusal_rec()
    r = aggregate(case(), [good, bad, good])
    assert r["status"] == "FAIL" and r["pass_runs"] == 2 and r["runs"] == 3


def test_summary_reports_citation_integrity_and_separates_sets() -> None:
    cl = case(test_id="BPL-AL-04", must_include=("7",))
    tm = case(test_id="REG-X", cls="REG")
    recs = {"BPL-AL-04": [answer_rec()], "REG-X": [answer_rec()]}
    res = [aggregate(cl, recs["BPL-AL-04"]), aggregate(tm, recs["REG-X"])]
    s = summarize(res, recs)
    assert s["client_set"]["cases"] == 1 and s["team_set"]["cases"] == 1
    assert s["citation_integrity"] == {"verified": 2, "displayed": 2, "rule": "100% required; zero fabricated citations"}
    assert "NOT answer correctness" in s["in_scope_automated_pass"]["note"]


# ------------------------------------------------------------------ replay (offline)
def test_replay_rescoring_asks_nothing_and_leaves_human_columns_blank(tmp_path: Path) -> None:
    recorded = {
        "meta": {"repeat": 1},
        "records": {
            "REG-AL-02": [answer_rec("New hires wait 90 days.")],
            "REG-OOC-01": [refusal_rec(group=None)],
        },
    }
    f = tmp_path / "recorded.json"
    f.write_text(json.dumps(recorded), encoding="utf-8")
    with patch.object(runner, "_run_live", side_effect=AssertionError("must not ask")), \
         patch.object(runner, "_ask_all", side_effect=AssertionError("must not ask")), \
         patch.object(runner, "_collect_states", side_effect=AssertionError("must not query")):
        code = runner.main(["--replay", str(f), "--set", "regression", "--out-dir", str(tmp_path)])
    assert code == 0
    outs = sorted(tmp_path.glob("eval_*_replay.csv"))
    assert len(outs) == 1
    rows = list(csv.DictReader(open(outs[0], encoding="utf-8")))
    assert {r["test_id"] for r in rows} == {"REG-AL-02", "REG-OOC-01"}
    assert all(r[c] == "" for r in rows for c in runner.HUMAN_COLUMNS)
    meta = json.loads(sorted(tmp_path.glob("eval_*_replay.json"))[0].read_text())["meta"]
    assert meta["mode"] == "replay" and meta["system_prompt_sha256"]


def test_replay_exits_nonzero_on_a_failure(tmp_path: Path) -> None:
    f = tmp_path / "recorded.json"
    f.write_text(json.dumps({"meta": {}, "records": {"REG-AL-02": [answer_rec("A few months.")]}}), encoding="utf-8")
    assert runner.main(["--replay", str(f), "--only", "REG-AL-02", "--out-dir", str(tmp_path)]) == 1


# ------------------------------------------------------------------ live path with a faked pipeline
def test_live_run_records_eligibility_from_the_database() -> None:
    tag = uuid.uuid4().hex[:8]
    sid_ok, sid_blocked, sid_missing = f"SRC-T{tag}-OK", f"SRC-T{tag}-BL", f"SRC-T{tag}-NO"
    ids: dict = {}

    async def _seed() -> None:
        async with async_session_factory() as s:
            for key, sid, elig, member in (("ok", sid_ok, Eligibility.authority_pending, True),
                                           ("bl", sid_blocked, Eligibility.blocked, False)):
                did, cid = uuid.uuid4(), uuid.uuid4()
                s.add(Document(document_id=did, title=f"{key} policy", version="t", policy_type="generic_policy",
                               source_format=SourceFormat.md, ingest_status=IngestStatus.indexed,
                               eligibility=elig, test_index_member=member, source_id=sid,
                               source_path=f"zz-{tag}-{key}.md"))
                await s.flush()
                s.add(Chunk(chunk_id=cid, document_id=did, ordinal=0, text="Staff may carry over seven days.", token_count=6))
                ids[key] = (did, cid)
            await s.commit()

    asyncio.run(_seed())
    cases = [
        case(test_id="T-IN", source_id=sid_ok, question="How many days can staff carry over?", must_include=("seven",)),
        case(test_id="T-OUT", source_id=sid_ok, cls="OUT", expect="refusal", question="What colour is the carpet?"),
        case(test_id="T-BLOCKED", source_id=sid_blocked, question="Who covers blocked things?"),
        case(test_id="T-MISSING", source_id=sid_missing, question="Who covers missing things?"),
    ]
    ok_chunk = ids["ok"][1]
    records: dict = {}

    loops: list[int] = []

    async def fake_scores(self, question, top_k):
        loops.append(id(asyncio.get_running_loop()))
        return {ok_chunk: 0.95} if "carry over" in question else {}

    async def fake_generate(*, question, chunks, conversation_context=None):
        return "Staff may carry over seven days.", False, [c.chunk_id for c in chunks], "{}"

    try:
        with patch.object(VectorRetriever, "_pinecone_scores", fake_scores), \
             patch("ask_bpl_orchestrator.services.ask_service.generation.generate_answer", side_effect=fake_generate):
            records = asyncio.run(runner._run_live(cases, repeat=2, delay=0))
        # Regression: every request must share ONE event loop, or pooled DB/OpenAI connections break
        # ("attached to a different loop" / "Event loop is closed") on the second request.
        assert len(loops) >= 2 and len(set(loops)) == 1
        res = {c.test_id: aggregate(c, records[c.test_id]) for c in cases}
        assert res["T-IN"]["status"] == "PASS" and res["T-IN"]["provisional"]
        assert records["T-IN"][0]["citation_states"][0]["eligibility"] == "authority_pending"
        assert res["T-OUT"]["status"] == "PASS"
        assert res["T-BLOCKED"]["status"] == "BLOCKED"
        assert res["T-MISSING"]["status"] == "BLOCKED"
        assert records["T-MISSING"][0]["group_state"]["found"] is False
    finally:
        request_ids = [uuid.UUID(rec["payload"]["request_id"])
                       for recs in records.values() for rec in recs if rec["payload"].get("request_id")]
        dids = [d for d, _ in ids.values()]

        async def _clean() -> None:
            async with async_session_factory() as s:
                for rid in request_ids:
                    await s.execute(delete(Question).where(Question.request_id == rid))
                await s.execute(delete(Chunk).where(Chunk.document_id.in_(dids)))
                await s.execute(delete(Document).where(Document.document_id.in_(dids)))
                await s.commit()

        asyncio.run(_clean())


def test_app_logs_go_to_a_file_not_the_console(tmp_path: Path, capsys) -> None:
    import logging

    saved = logging.root.handlers[:]
    try:
        log = runner._redirect_app_logs(tmp_path)
        logging.getLogger("ask_bpl_orchestrator.services.ask_service").error("ask_pipeline_error: boom")
        for h in logging.root.handlers:
            h.flush()
        assert "ask_pipeline_error: boom" in log.read_text()
        assert "boom" not in capsys.readouterr().err
    finally:
        logging.root.handlers[:] = saved


# ------------------------------------------------------------------ patch 0008: hygiene and numeric guards
def test_split_keeps_alternation_inside_groups() -> None:
    from ask_bpl_orchestrator.evals.cases import _split

    assert _split("a | b") == ("a", "b")
    assert _split(r"re:\b(days|weeks)\b | plain") == (r"re:\b(days|weeks)\b", "plain")
    assert _split(r"re:[ab|c]x|y") == (r"re:[ab|c]x", "y")
    assert _split("") == ()


def test_token_matches_plain_and_regex() -> None:
    from ask_bpl_orchestrator.evals.scoring import token_matches

    assert token_matches("Seven Days", "you may carry over seven days")
    assert not token_matches("eight days", "you may carry over seven days")
    assert token_matches(r"re:\b\d+\s+days\b", "within 30 days")
    assert token_matches(r"re:\b\d+\s+DAYS\b", "within 30 days")  # regexes ignore case
    assert not token_matches(r"re:\b\d+\s+days\b", "no number of days is given")


# What the live pipeline actually said for the two designated out-of-scope questions in the 2026-10-12 run
# (limitation answers, no invented figure). They must not trip the guards.
_MS05_LIMITATION = ("The policy doesn't specify a set timeframe - it just says the Materials Review Committee provides a "
                    "\"timely, considered response\" to every reconsideration request.")
_UC05_LIMITATION = ("The policy doesn't set a specific age - instead, it says children who are 'unable or unwilling to care "
                    "for themselves' may not be left alone and must have adequate supervision.")


def _guards(test_id: str) -> tuple[str, ...]:
    return next(c for c in load_cases(CLIENT_CSV) if c.test_id == test_id).must_not_include


@pytest.mark.parametrize("test_id,limitation", [("BPL-MS-05", _MS05_LIMITATION), ("BPL-UC-05", _UC05_LIMITATION)])
def test_boundary_guards_accept_honest_limitation_answers(test_id: str, limitation: str) -> None:
    from ask_bpl_orchestrator.evals.scoring import token_matches

    guards = _guards(test_id)
    assert guards, "guard missing"
    assert not any(token_matches(g, limitation.lower()) for g in guards)


@pytest.mark.parametrize("test_id,invented", [
    ("BPL-MS-05", "The committee usually decides within 30 days."),
    ("BPL-MS-05", "Expect a decision in about two weeks."),
    ("BPL-MS-05", "It takes 6-8 weeks."),
    ("BPL-UC-05", "Children 12 years or older may stay alone."),
    ("BPL-UC-05", "Children aged 10 can be left alone."),
    ("BPL-UC-05", "Twelve and older is acceptable."),
    ("BPL-UC-05", "The age of twelve is the cutoff."),
])
def test_boundary_guards_catch_invented_figures(test_id: str, invented: str) -> None:
    from ask_bpl_orchestrator.evals.scoring import token_matches

    assert any(token_matches(g, invented.lower()) for g in _guards(test_id)), invented


def test_run_metadata_dirty_flag_ignores_untracked_files() -> None:
    seen: list[tuple[str, ...]] = []

    def fake_git(*args: str):
        seen.append(args)
        return None

    with patch.object(runner, "_git", fake_git):
        meta = runner.run_metadata(load_cases(CLIENT_CSV)[:1], mode="live", env_label="t", repeat=1)
    status_calls = [a for a in seen if a[:1] == ("status",)]
    assert status_calls and all("--untracked-files=no" in a for a in status_calls)
    assert meta["working_tree_dirty"] is False and meta["untracked_files_present"] is False


def test_blocked_message_explains_deliberately_held_back_documents() -> None:
    s = score_run(case(cls="IN", expect="answer"), refusal_rec(group={"found": False}))
    assert s.status == "BLOCKED"
    text = " ".join(s.warnings)
    assert "NOT EVALUABLE" in text and "deliberately held back" in text and "only if it should be stored" in text


def test_out_of_scope_answer_with_invented_figure_fails_but_honest_limitation_is_review() -> None:
    guards = _guards("BPL-MS-05")
    oos = case(cls="OUT", expect="refusal", must_not_include=guards)
    assert score_run(oos, answer_rec(_MS05_LIMITATION)).status == "REVIEW"  # a human still looks (Document 06 s.5)
    invented = score_run(oos, answer_rec("The committee usually decides within 30 days."))
    assert invented.status == "FAIL" and "must_not_include" in invented.failed
