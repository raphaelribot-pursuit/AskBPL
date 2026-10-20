"""Patch 0016: approved glossary (PRD GLO-1 to GLO-6).

What these tests protect:
  * only entries with status "approved" and a source, approver and date are ever used (GLO-1, GLO-2, GLO-5);
  * an approved term adds its expansion to the SEARCH query only: the model still gets the staff member's own words
    and a match can never rescue weak evidence (GLO-6);
  * an empty glossary changes nothing, byte for byte;
  * unlisted acronyms are only counted in the log, never logged by name, and never change an answer yet;
  * the review tools are read-only.

No network. The model and the vector search are faked.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, patch

import openpyxl
import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import delete

from ask_bpl_orchestrator import glossary_tools
from ask_bpl_orchestrator.config import get_settings
from ask_bpl_orchestrator.db.models import Question
from ask_bpl_orchestrator.db.session import async_session_factory
from ask_bpl_orchestrator.main import app
from ask_bpl_orchestrator.services import glossary as gl
from ask_bpl_orchestrator.services.glossary import (
    Glossary,
    GlossaryError,
    acronyms_missing_from,
    load_glossary,
    parse_glossary,
)
from ask_bpl_orchestrator.services.query_rewriter import REWRITE_SYSTEM_PROMPT
from ask_bpl_orchestrator.services.retrieval import RetrievedChunk, VectorRetriever

SETTINGS = get_settings()
FLOOR, STRONG = SETTINGS.grounding_threshold, SETTINGS.grounding_strong_threshold


def entry(term: str = "CBH", **over: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "term": term,
        "expansion": "Center for Brooklyn History",
        "source": "BPL confirmation 2026-10-18",
        "status": "approved",
        "owner": "BPL Archives",
        "approved_by": "A. Reviewer",
        "approved_on": "2026-10-18",
    }
    base.update(over)
    return base


def make(*entries: Dict[str, Any], allowlist: List[str] | None = None) -> Glossary:
    data: Dict[str, Any] = {"entries": list(entries)}
    if allowlist is not None:
        data["common_words_allowlist"] = allowlist
    return parse_glossary(data)


# ----------------------------------------------------------------------------- loading and validation
def test_empty_and_missing_sections_are_an_empty_glossary() -> None:
    assert parse_glossary(None).entries == () and parse_glossary({}).entries == ()
    assert parse_glossary({"entries": []}).approved == ()


def test_an_approved_entry_loads_with_all_its_fields() -> None:
    g = make(entry(aliases=["cbh", "the CBH"], context="Archives"))
    (e,) = g.entries
    assert (e.term, e.expansion, e.aliases, e.status) == (
        "CBH",
        "Center for Brooklyn History",
        ("cbh", "the CBH"),
        "approved",
    )
    assert (
        e.approved_on == dt.date(2026, 10, 18)
        and e.owner == "BPL Archives"
        and e.context == "Archives"
    )


@pytest.mark.parametrize("missing", ["expansion", "source", "approved_by", "approved_on"])
def test_an_approved_entry_without_expansion_source_approver_or_date_is_rejected(
    missing: str,
) -> None:
    raw = entry()
    raw.pop(missing)
    with pytest.raises(GlossaryError, match=missing):
        make(raw)


def test_draft_and_conflict_entries_may_be_incomplete() -> None:
    g = make(
        {"term": "BCC", "status": "draft"},
        {"term": "XYZ", "status": "conflict", "expansion": "two meanings"},
    )
    assert [e.status for e in g.entries] == ["draft", "conflict"] and g.approved == ()


@pytest.mark.parametrize(
    "data, fragment",
    [
        ({"entries": [{"term": "A", "status": "verified"}]}, "status must be one of"),
        ({"entries": [{"term": "A", "statuss": "draft"}]}, "unknown field"),
        ({"entries": [{"status": "draft"}]}, "term is required"),
        ({"entries": ["CBH"]}, "mapping of fields"),
        ({"entries": [{"term": "A", "aliases": "a"}]}, "aliases must be a list"),
        ({"entries": [{"term": "A", "aliases": [""]}]}, "aliases must be a list"),
        ({"entries": [entry(approved_on="18/10/2026")]}, "approved_on must be a date"),
        ({"entries": "none"}, "'entries' must be a list"),
        ({"entrys": []}, "unknown top-level key"),
        ({"entries": [], "common_words_allowlist": "US"}, "common_words_allowlist"),
        (["a"], "must be a mapping"),
    ],
)
def test_malformed_files_are_rejected_with_a_clear_message(data: Any, fragment: str) -> None:
    with pytest.raises(GlossaryError, match=fragment):
        parse_glossary(data)


def test_two_approved_entries_cannot_claim_the_same_form() -> None:
    with pytest.raises(GlossaryError, match="claimed by two approved entries"):
        make(entry("CBH"), entry("CBX", aliases=["cbh"]))  # compared without case
    # a draft or conflict record of the same term is allowed: it is how a disagreement is kept for review
    assert len(make(entry("CBH"), {"term": "CBH", "status": "conflict"}).entries) == 2


def test_load_glossary_reports_unreadable_and_invalid_files(tmp_path: Path) -> None:
    with pytest.raises(GlossaryError, match="cannot read"):
        load_glossary(tmp_path / "nope.yaml")
    bad = tmp_path / "bad.yaml"
    bad.write_text("entries: [unclosed", encoding="utf-8")
    with pytest.raises(GlossaryError, match="not valid YAML"):
        load_glossary(bad)
    good = tmp_path / "ok.yaml"
    good.write_text(yaml.safe_dump({"entries": [entry()]}), encoding="utf-8")
    assert load_glossary(good).approved[0].term == "CBH"


def test_the_bundled_file_is_valid_and_ships_with_nothing_approved_by_default() -> None:
    g = load_glossary(gl.BUNDLED_PATH)
    assert g.approved == (), (
        "an approved entry needs BPL's sign-off: change this test only with the approval logged"
    )


# ----------------------------------------------------------------------------- matching
@pytest.mark.parametrize(
    "question, hits",
    [
        ("What does CBH do?", True),
        ("Does CBH's reading room open?", True),  # possessive
        ("Who runs (CBH)?", True),
        ("What does cbh do?", False),  # short all-capital terms are case-sensitive
        ("Is MACHINE access allowed?", False),  # whole words only
        ("Is XCBH2 a thing?", False),
    ],
)
def test_acronyms_match_whole_words_and_exact_case(question: str, hits: bool) -> None:
    assert bool(make(entry("CBH")).find(question)) is hits


def test_mac_does_not_fire_on_mac_the_computer() -> None:
    g = make(entry("MAC", expansion="Marketing and Communications"))
    assert g.find("Who is in the MAC team?") and not g.find("Can I use a Mac laptop?")


def test_phrases_and_aliases_match_without_regard_to_case() -> None:
    g = make(entry("Book Ops", expansion="BookOps", aliases=["bookops"]))
    assert (
        g.find("what does BOOK OPS do")
        and g.find("who is in bookops?")
        and not g.find("Bookkeeping help")
    )


def test_draft_and_conflict_entries_never_match() -> None:
    g = make(
        {"term": "DPS", "expansion": "Department of Public Safety", "status": "draft"},
        {"term": "BCC", "status": "conflict"},
    )
    assert g.find("What does DPS do about BCC?") == ()
    assert g.expand_query("What does DPS do?").text == "What does DPS do?"


def test_one_match_per_entry_in_order_of_appearance() -> None:
    g = make(
        entry("CBH", aliases=["the archive"]), entry("DPS", expansion="Department of Public Safety")
    )
    found = g.find("Ask DPS, then CBH, then CBH again, then the archive")
    assert [m.entry.term for m in found] == ["DPS", "CBH"]


# ----------------------------------------------------------------------------- expansion (search query only)
def test_expansion_is_appended_to_the_query() -> None:
    g = make(entry("CBH"), entry("DPS", expansion="Department of Public Safety"))
    out = g.expand_query("Do CBH and DPS share a desk?")
    assert (
        out.text
        == "Do CBH and DPS share a desk? (CBH = Center for Brooklyn History; DPS = Department of Public Safety)"
    )
    assert len(out.matches) == 2


def test_nothing_is_added_when_the_term_is_already_spelled_out_or_absent() -> None:
    g = make(entry("CBH"))
    spelled = "Does CBH (Center for Brooklyn History) open late?"
    assert g.expand_query(spelled).text == spelled
    plain = "What is the leave policy?"
    assert g.expand_query(plain).text == plain and g.expand_query(plain).matches == ()


def test_an_empty_glossary_leaves_the_query_byte_identical() -> None:
    q = "What does CBH do? DPS? \u00e9\u00e0"
    assert (
        Glossary().expand_query(q).text == q
        and parse_glossary({"entries": []}).expand_query(q).text == q
    )


# ----------------------------------------------------------------------------- unlisted acronyms (log only)
def test_unlisted_acronyms_exclude_approved_allowlisted_and_roman_numerals() -> None:
    g = make(entry("CBH", aliases=["CBHX"]), allowlist=["WIFI"])
    text = "Does CBH or CBHX apply under Section IV to the PDF, NYC and WIFI rules at DPS and XQZ?"
    assert g.unlisted_acronyms(text) == ["DPS", "XQZ"]


def test_a_draft_acronym_is_still_unlisted_because_it_is_not_approved() -> None:
    g = make({"term": "DPS", "status": "draft"})
    assert g.unlisted_acronyms("What does DPS do?") == ["DPS"]


@pytest.mark.parametrize(
    "text, expected",
    [
        (
            "WHAT DOES THE POLICY SAY ABOUT LEAVE",
            [],
        ),  # typed in capitals: every word would look like an acronym
        (
            "Is X or ABCDEFG or iPHONE ok?",
            [],
        ),  # 1 letter, 7 letters, and a token inside a word are not acronyms
        ("Does ABC apply? And ABC again, and DEF?", ["ABC", "DEF"]),  # once each, in order
    ],
)
def test_unlisted_acronym_shape_rules(text: str, expected: List[str]) -> None:
    assert Glossary().unlisted_acronyms(text) == expected


def test_acronyms_missing_from_the_evidence() -> None:
    texts = ["Staff may ask DPS for help.", "See the HR office."]
    assert acronyms_missing_from(["DPS", "XQZ", "HR", "HRX"], texts) == ["XQZ", "HRX"]
    assert acronyms_missing_from(["XQZ"], []) == ["XQZ"]


# ----------------------------------------------------------------------------- get_glossary
def test_get_glossary_uses_the_configured_file_and_degrades_to_empty_on_error(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    good = tmp_path / "g.yaml"
    good.write_text(yaml.safe_dump({"entries": [entry()]}), encoding="utf-8")
    gl.get_glossary.cache_clear()
    try:
        with patch(
            "ask_bpl_orchestrator.config.get_settings",
            return_value=type("S", (), {"glossary_path": str(good)})(),
        ):
            assert gl.get_glossary().approved[0].term == "CBH"
            gl.get_glossary.cache_clear()
        bad = tmp_path / "bad.yaml"
        bad.write_text("entries: [unclosed", encoding="utf-8")
        with patch(
            "ask_bpl_orchestrator.config.get_settings",
            return_value=type("S", (), {"glossary_path": str(bad)})(),
        ):
            caplog.set_level(logging.ERROR)
            assert gl.get_glossary().entries == ()
            assert any(
                "glossary file could not be loaded" in r.getMessage() for r in caplog.records
            )
    finally:
        gl.get_glossary.cache_clear()


def test_the_rewriter_is_told_never_to_expand_acronyms() -> None:
    assert (
        "Keep every acronym and abbreviation exactly as the user wrote it" in REWRITE_SYSTEM_PROMPT
    )
    assert "Never expand, define or guess" in REWRITE_SYSTEM_PROMPT


# ----------------------------------------------------------------------------- through the real ask pipeline
client = TestClient(app)
GENERATE = "ask_bpl_orchestrator.services.ask_service.generation.generate_answer"
GET_GLOSSARY = "ask_bpl_orchestrator.services.ask_service.get_glossary"
QUESTION = "What does DPS do when a child is left alone?"


def _chunk(
    score: float, text: str = "The Department of Public Safety may be contacted at closing."
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        score=score,
        document_id=uuid.uuid4(),
        title="Glossary Test Doc",
        policy_type="generic_policy",
        version="g-1",
        section_heading=None,
        text=text,
    )


def _ask(question: str) -> Any:
    token = client.post(
        "/auth/sign-in",
        json={
            "email": "pilot-demo@bklynlibrary.org",
            "access_code": "DEMO2026",
            "attribution_mode": "anonymous",
        },
    ).json()["token"]
    return client.post(
        "/questions/ask", headers={"Authorization": f"Bearer {token}"}, json={"question": question}
    )


def _forget(rid: str) -> None:
    import asyncio

    async def go() -> None:
        async with async_session_factory() as s:
            await s.execute(delete(Question).where(Question.request_id == uuid.UUID(rid)))
            await s.commit()

    asyncio.run(go())


class Spy:
    """Fake search that records the exact query it was given."""

    def __init__(self, chunks: List[RetrievedChunk]) -> None:
        self.chunks, self.queries = chunks, []

    def patch(self):
        spy = self

        async def fake(
            self_: VectorRetriever, db: Any, question: str, top_k: int
        ) -> List[RetrievedChunk]:
            spy.queries.append(question)
            self_.excluded_best_score = 0.0
            return spy.chunks

        return patch.object(VectorRetriever, "query", fake)


@pytest.fixture(autouse=True)
def _no_live_vector_lookup():
    with patch.object(VectorRetriever, "_pinecone_scores", new_callable=AsyncMock, return_value={}):
        yield


def _glossary_logs(caplog: pytest.LogCaptureFixture) -> List[Dict[str, Any]]:
    out = []
    for rec in caplog.records:
        try:
            entry_ = json.loads(rec.getMessage())
        except (ValueError, TypeError):
            continue
        if isinstance(entry_, dict) and entry_.get("event") == "glossary":
            out.append(entry_)
    return out


def _refusing_model() -> AsyncMock:
    return AsyncMock(
        return_value=("", True, [], '{"answer": "", "refuse": true, "cited_chunk_ids": []}')
    )


def test_the_expansion_reaches_the_search_but_the_model_gets_the_original_question() -> None:
    g = make(entry("DPS", expansion="Department of Public Safety"))
    spy, model = Spy([_chunk(0.95)]), _refusing_model()
    with patch(GET_GLOSSARY, return_value=g), spy.patch(), patch(GENERATE, model):
        r = _ask(QUESTION)
    assert spy.queries == [f"{QUESTION} (DPS = Department of Public Safety)"]
    assert model.await_args.kwargs["question"] == QUESTION  # GLO-6: nothing added reaches the model
    _forget(r.json()["request_id"])


def test_an_empty_glossary_sends_the_question_to_the_search_unchanged() -> None:
    spy, model = Spy([_chunk(0.95)]), _refusing_model()
    with patch(GET_GLOSSARY, return_value=Glossary()), spy.patch(), patch(GENERATE, model):
        r = _ask(QUESTION)
    assert spy.queries == [QUESTION]
    _forget(r.json()["request_id"])


def test_a_glossary_match_cannot_rescue_weak_evidence(caplog: pytest.LogCaptureFixture) -> None:
    """GLO-6: the term matched and the query was expanded, but the policy text is not strong enough, so it refuses."""
    caplog.set_level(logging.INFO)
    g = make(entry("DPS", expansion="Department of Public Safety"))
    weak = FLOOR + (STRONG - FLOOR) / 2  # above the floor, below strong, one chunk only
    spy, model = Spy([_chunk(weak)]), _refusing_model()
    with patch(GET_GLOSSARY, return_value=g), spy.patch(), patch(GENERATE, model):
        r = _ask(QUESTION)
    body = r.json()
    assert "(DPS = Department of Public Safety)" in spy.queries[0]
    assert body["type"] == "refusal_oo_corpus"
    model.assert_not_awaited()  # the gate stopped it before any model call
    assert _glossary_logs(caplog)[-1]["matched_terms"] == 1
    _forget(body["request_id"])


def test_the_glossary_log_has_counts_only_never_the_acronym_or_the_question(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    question = "Does XQZ or DPS apply when a child is left alone?"
    g = make(entry("DPS", expansion="Department of Public Safety"))
    spy = Spy([_chunk(0.95, text="Staff may ask the Department of Public Safety for help.")])
    with patch(GET_GLOSSARY, return_value=g), spy.patch(), patch(GENERATE, _refusing_model()):
        r = _ask(question)
    (log,) = _glossary_logs(caplog)[-1:]
    assert (log["matched_terms"], log["unlisted_acronyms"], log["unlisted_not_in_evidence"]) == (
        1,
        1,
        1,
    )
    raw = [rec.getMessage() for rec in caplog.records if '"event": "glossary"' in rec.getMessage()][
        -1
    ]
    assert "XQZ" not in raw and "DPS" not in raw and "child" not in raw
    _forget(r.json()["request_id"])


def test_an_unlisted_acronym_alone_changes_nothing_yet(caplog: pytest.LogCaptureFixture) -> None:
    """GLO-2 behaviour is a team decision: for now the acronym is only counted. The query and the model call are unchanged."""
    caplog.set_level(logging.INFO)
    q = "What does the XQZ rule say about leave?"
    spy, model = Spy([_chunk(0.95)]), _refusing_model()
    with patch(GET_GLOSSARY, return_value=Glossary()), spy.patch(), patch(GENERATE, model):
        r = _ask(q)
    assert spy.queries == [q] and model.await_args.kwargs["question"] == q
    assert _glossary_logs(caplog)[-1]["unlisted_acronyms"] == 1
    _forget(r.json()["request_id"])


def test_no_glossary_log_line_when_there_is_nothing_to_report(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    with (
        patch(GET_GLOSSARY, return_value=Glossary()),
        Spy([_chunk(0.95)]).patch(),
        patch(GENERATE, _refusing_model()),
    ):
        r = _ask("What is the leave policy for new staff?")
    assert _glossary_logs(caplog) == []
    _forget(r.json()["request_id"])


# ----------------------------------------------------------------------------- tools
def _write_general(path: Path, rows: List[List[str]]) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Master Glossary"
    ws.append(["BPL Acronyms, Institutional Terms and Knowledge Dictionary"])
    ws.append(["300 entries"])
    ws.append([])
    ws.append(
        [
            "Category",
            "Term / Acronym",
            "Meaning / BPL Context",
            "Entry Type",
            "Verification Status",
            "Source Basis",
            "Review Notes",
        ]
    )
    for term, meaning, source in rows:
        ws.append(["Departments", term, meaning, "Acronym", "Verified", source, ""])
    wb.save(path)


def _write_policy(path: Path, rows: List[List[str]]) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "BPL Glossary"
    ws.append(
        [
            "Acronym / Term",
            "Category",
            "Meaning / Expansion",
            "BPL Context / Notes",
            "Source File(s)",
            "Page(s)",
            "Verification Status",
        ]
    )
    for term, meaning, status in rows:
        ws.append([term, "Acronym", meaning, "", "Some Policy", "1", status])
    wb.save(path)


@pytest.fixture()
def workbooks(tmp_path: Path) -> tuple[Path, Path]:
    general, policy = tmp_path / "general.xlsx", tmp_path / "policy.xlsx"
    _write_general(
        general,
        [
            ["BCC", "Business and Career Center", "Master list"],
            ["MAC", "Marketing and Communications", "Master list"],
            ["DPS", "Department of Public Safety", "Master list"],
            ["Selection", "BookOps materials selection and ordering", ""],
            ["DPS", "Department of Public Safety (dup)", "Master list"],
        ],
    )
    _write_policy(
        policy,
        [
            ["BCC", "Blind carbon copy", "Confirmed in source"],
            ["MAC", "Marketing & Communications", "Confirmed in source"],
            ["PDA", "", "Meaning not stated"],
        ],
    )
    return general, policy


def test_candidates_flag_conflicts_unknowns_missing_sources_and_duplicates(
    workbooks: tuple[Path, Path],
) -> None:
    general, policy = workbooks
    cands = {
        c.key: c
        for c in glossary_tools.merge(
            glossary_tools.read_general(general), glossary_tools.read_policy(policy)
        )
    }
    assert "MEANINGS DIFFER" in cands["bcc"].flags and "in both workbooks" in cands["bcc"].flags
    assert "MEANINGS DIFFER" not in cands["mac"].flags, (
        "'&' versus 'and' is a wording difference, not a conflict"
    )
    assert "unknown meaning" in cands["pda"].flags
    assert "no source" in cands["selection"].flags
    assert "duplicate in a workbook" in cands["dps"].flags


def test_candidates_count_use_in_questions_and_policy_text(workbooks: tuple[Path, Path]) -> None:
    general, policy = workbooks
    cands = glossary_tools.merge(
        glossary_tools.read_general(general), glossary_tools.read_policy(policy)
    )
    glossary_tools.count_hits(
        cands,
        questions=["What does DPS do?", "Who is MAC?", "Unrelated"],
        policy_texts=[
            "Staff may call the Department of Public Safety. DPS answers.",
            "Plain text.",
        ],
    )
    by = {c.key: c for c in cands}
    assert (by["dps"].eval_hits, by["dps"].text_hits, by["dps"].spelled_out_hits) == (1, 1, 1)
    assert by["dps"].score == 3 * 1 + 2 * 1 + 1
    assert by["bcc"].score == 0


def test_candidates_cli_prints_a_report_and_writes_a_blank_review_csv_without_touching_the_glossary(
    workbooks: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    general, policy = workbooks
    evals = tmp_path / "q.csv"
    evals.write_text("test_id,question\nQ1,What does DPS do?\n", encoding="utf-8")
    out = tmp_path / "review.csv"
    before = gl.BUNDLED_PATH.read_bytes()
    code = glossary_tools.candidates_main(
        [
            "--general",
            str(general),
            "--policy",
            str(policy),
            "--eval-csv",
            str(evals),
            "--csv",
            str(out),
        ]
    )
    text = capsys.readouterr().out
    assert code == 0 and "approves nothing" in text
    assert "BCC: general = 'Business and Career Center'" in text and "DPS" in text
    import csv

    rows = list(csv.DictReader(open(out, newline="", encoding="utf-8")))
    assert {r["term"] for r in rows} == {"BCC", "MAC", "DPS", "Selection", "PDA"}
    assert all(r[c] == "" for r in rows for c in glossary_tools.REVIEW_COLUMNS), (
        "review columns must start blank"
    )
    assert gl.BUNDLED_PATH.read_bytes() == before, "the tool must never write the glossary file"


def test_candidates_acronyms_only_hides_ordinary_words(
    workbooks: tuple[Path, Path], tmp_path: Path, capsys
) -> None:
    general, policy = workbooks
    evals = tmp_path / "q.csv"
    evals.write_text("test_id,question\nQ1,Does selection matter for DPS?\n", encoding="utf-8")
    glossary_tools.candidates_main(
        ["--general", str(general), "--policy", str(policy), "--eval-csv", str(evals)]
    )
    assert "Selection " in capsys.readouterr().out.split("Review first")[0]
    glossary_tools.candidates_main(
        [
            "--general",
            str(general),
            "--policy",
            str(policy),
            "--eval-csv",
            str(evals),
            "--acronyms-only",
        ]
    )
    ranked = capsys.readouterr().out.split("Review first")[0]
    assert "DPS " in ranked and "Selection " not in ranked


def test_candidates_cli_rejects_a_missing_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        glossary_tools.candidates_main(
            ["--general", str(tmp_path / "x.xlsx"), "--policy", str(tmp_path / "y.xlsx")]
        )
        == 2
    )


def test_check_cli_exit_codes_and_messages(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ok = tmp_path / "ok.yaml"
    ok.write_text(
        yaml.safe_dump({"entries": [entry(), {"term": "BCC", "status": "draft"}]}), encoding="utf-8"
    )
    assert glossary_tools.check_main([str(ok)]) == 0
    out = capsys.readouterr().out
    assert "approved 1, draft 1, conflict 0" in out and out.rstrip().endswith("OK")
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.safe_dump({"entries": [entry(approved_by="")]}), encoding="utf-8")
    assert glossary_tools.check_main([str(bad)]) == 1
    assert "approved_by" in capsys.readouterr().err
    empty = tmp_path / "empty.yaml"
    empty.write_text("entries: []\n", encoding="utf-8")
    assert glossary_tools.check_main([str(empty)]) == 0
    assert "changes nothing until BPL approves" in capsys.readouterr().out
    assert glossary_tools.check_main([]) == 0  # the bundled file


# ----------------------------------------------------------------------------- eval cases
def test_glossary_cases_are_valid_separate_from_baselines_and_pass_the_intent_guard() -> None:
    from ask_bpl_orchestrator.evals import runner
    from ask_bpl_orchestrator.evals.cases import (
        CLIENT_CSV,
        GLOSSARY_CSV,
        REGRESSION_CSV,
        load_cases,
    )
    from ask_bpl_orchestrator.services.intent_guard import intent_causes

    glo = load_cases(GLOSSARY_CSV)
    assert [c.test_id for c in glo] == ["GLO-01", "GLO-02", "GLO-03", "GLO-04"]
    assert all(c.cls == "REG" and c.reference_status == "PENDING" for c in glo)
    assert [c for c in glo if intent_causes(c.question)] == [], (
        "a probe must reach retrieval, not an early refusal"
    )
    baseline = {c.test_id for c in load_cases(CLIENT_CSV) + load_cases(REGRESSION_CSV)}
    assert baseline.isdisjoint(c.test_id for c in glo)
    # the baselines are unchanged: `all` is still the client 30 plus the 7 team cases
    assert len(runner.select_cases("all", None)) == 37
    assert {c.test_id for c in runner.select_cases("glossary", None)} == {c.test_id for c in glo}
    assert [c.test_id for c in runner.select_cases("all", ["GLO-02"])] == ["GLO-02"]
    with pytest.raises(SystemExit):
        runner.select_cases("client", ["GLO-02"])


def test_the_no_guessing_probe_forbids_the_real_expansion() -> None:
    from ask_bpl_orchestrator.evals.cases import GLOSSARY_CSV, load_cases

    glo = {c.test_id: c for c in load_cases(GLOSSARY_CSV)}
    assert (
        "Center for Brooklyn History" in glo["GLO-01"].must_not_include
        and glo["GLO-01"].expect == "either"
    )
    assert glo["GLO-02"].expect == glo["GLO-03"].expect == "refusal"
    assert glo["GLO-04"].expect == "answer" and "Public Safety" in glo["GLO-04"].must_include
