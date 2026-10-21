"""Patch 0017: GRD-12 robustness probes and the `must_cite_source` check.

These tests are offline. They prove the probes are well formed, reach retrieval, quote the real policies, and that the
keyword guards behave on honest and invented answers. They do NOT show how the live system answers: that needs
`askbpl-eval --set robustness --repeat 3` against real API keys.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

import pytest

from ask_bpl_orchestrator.evals import runner
from ask_bpl_orchestrator.evals.cases import (
    CLIENT_CSV,
    GLOSSARY_CSV,
    REGRESSION_CSV,
    ROBUSTNESS_CSV,
    Case,
    load_cases,
)
from ask_bpl_orchestrator.evals.scoring import aggregate, score_run, token_matches

ROB = load_cases(ROBUSTNESS_CSV)
BY_ID = {c.test_id: c for c in ROB}

ORCH = Path(__file__).resolve().parents[1]
PILOT = ORCH / "sample_corpus" / "pilot"
# Supplied policies the probes quote. The inventory file names differ slightly from the pilot folder, so map explicitly.
SOURCE_PDF = {
    "SRC-03": "01 - Technology Use (6.13).pdf",
    "SRC-10": "04 - Annual Leave Policy (01.06) (1).pdf",
    "SRC-14": "06 - Fundraising Policy (12.01) (1).pdf",
    "SRC-16": "07 - Volunteer Manual (12.08) (1).pdf",
    "SRC-22": "12 - Technology Usage Policy (06.06) (1).pdf",
}
# GRD-12 names these categories (PRD v1.2). Every one needs at least one probe.
GRD12_CATEGORIES = {
    "Similar titles", "Version drift", "Long document", "Missing section", "Multi-document",
    "Conflicting audiences", "Not indexed", "Acronyms",
}


# --------------------------------------------------------------------------- the fixture
def test_robustness_cases_load_and_are_team_created() -> None:
    assert len(ROB) == 22
    assert len({c.test_id for c in ROB}) == 22
    assert all(c.test_id.startswith("ROB-") and c.cls == "REG" for c in ROB)
    assert all(c.reference_status != "BPL_APPROVED" for c in ROB)  # no approved answer key exists
    assert GRD12_CATEGORIES <= {c.group for c in ROB}


def test_ids_do_not_collide_with_the_other_sets_and_the_baselines_are_unchanged() -> None:
    others = {c.test_id for c in load_cases(CLIENT_CSV) + load_cases(REGRESSION_CSV) + load_cases(GLOSSARY_CSV)}
    assert others.isdisjoint(c.test_id for c in ROB)
    assert len(runner.select_cases("all", None)) == 37  # client 30 + team 7, exactly as before
    assert {c.test_id for c in runner.select_cases("robustness", None)} == set(BY_ID)
    assert [c.test_id for c in runner.select_cases("all", ["ROB-LD-01"])] == ["ROB-LD-01"]
    with pytest.raises(SystemExit):
        runner.select_cases("client", ["ROB-LD-01"])
    with pytest.raises(SystemExit):
        runner.select_cases("glossary", ["ROB-LD-01"])  # sets do not leak into each other


def test_every_probe_reaches_retrieval_instead_of_an_early_gate() -> None:
    from ask_bpl_orchestrator.services.crisis_gate import detect_crisis
    from ask_bpl_orchestrator.services.intent_guard import intent_causes
    from ask_bpl_orchestrator.services.pii_gate import rejects_input

    probes = ROB + load_cases(GLOSSARY_CSV)
    assert [c.test_id for c in probes if intent_causes(c.question)] == []
    assert [c.test_id for c in probes if rejects_input(c.question)[0]] == []
    assert [c.test_id for c in probes if detect_crisis(c.question)] == []


def test_every_regex_token_compiles_and_is_not_empty() -> None:
    for c in ROB:
        for tok in c.must_include + c.must_not_include:
            assert tok.strip()
            if tok.startswith("re:"):
                re.compile(tok[3:])


def test_expectations_are_consistent() -> None:
    for c in ROB:
        if c.expect == "answer":
            assert c.source_id or c.must_cite_source or c.must_include, f"{c.test_id}: an answer case needs some check"
        if c.expect == "refusal":
            assert not c.must_cite_source and not c.must_include, f"{c.test_id}: refusals cite nothing"
        if c.must_cite_source:
            assert c.expect == "answer", f"{c.test_id}: a citation rule only makes sense for an answer"


def test_cited_sources_are_supplied_policies_in_the_inventory() -> None:
    import openpyxl

    wb = openpyxl.load_workbook(ORCH / "sample_corpus" / "AskBPL_Source_Inventory_v0_1.xlsx", read_only=True)
    ids = {str(r[0]) for r in wb["Source Inventory"].iter_rows(min_row=2, values_only=True) if r and r[0]}
    for c in ROB + load_cases(GLOSSARY_CSV):
        for sid in {c.source_id, *c.must_cite_source} - {""}:
            assert sid in ids, f"{c.test_id}: {sid} is not in the source inventory"


def _norm(text: str) -> str:
    text = text.replace("", " ").replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip().lower()


def test_every_reference_quote_appears_verbatim_in_the_supplied_policy_text() -> None:
    import pypdf

    corpus = {
        sid: _norm(" ".join((p.extract_text() or "") for p in pypdf.PdfReader(str(PILOT / name)).pages))
        for sid, name in SOURCE_PDF.items()
    }
    quoted = [c for c in ROB if c.reference_evidence]
    assert len(quoted) >= 15
    for c in quoted:
        pool = [corpus[c.source_id]] if c.source_id else list(corpus.values())
        assert any(_norm(c.reference_evidence) in t for t in pool), f"{c.test_id}: quote not found in the policy text"
        assert c.reference_status == "ENGINEER_PREPARED_PENDING_BPL"


def test_a_must_cite_rule_names_the_policy_the_quote_comes_from() -> None:
    """For single-policy cases the cited source and the case's own source are the same policy."""
    for c in ROB:
        if c.must_cite_source and c.source_id:
            assert c.must_cite_source == (c.source_id,), c.test_id


def test_similar_title_cases_pull_the_two_technology_policies_apart() -> None:
    assert BY_ID["ROB-ST-01"].must_cite_source == ("SRC-22",)  # employee question
    assert BY_ID["ROB-ST-02"].must_cite_source == ("SRC-03",)  # public-computer question
    assert BY_ID["ROB-MD-01"].must_cite_source == ("SRC-03", "SRC-22")  # needs both


# --------------------------------------------------------------------------- loader and scoring of the new column
def _write(tmp_path: Path, rows: list[str], header: str | None = None) -> Path:
    base = "test_id,group,source_id,cls,question,expect,must_include,must_not_include,reference_status,reference_evidence,note"
    p = tmp_path / "c.csv"
    p.write_text((header or base) + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return p


def test_the_column_is_optional_so_older_files_still_load(tmp_path: Path) -> None:
    (c,) = load_cases(_write(tmp_path, ["X-1,g,,REG,q?,answer,,,PENDING,,"]))
    assert c.must_cite_source == ()
    assert all(x.must_cite_source == () for x in load_cases(CLIENT_CSV) + load_cases(REGRESSION_CSV))


def test_loader_reads_and_validates_must_cite_source(tmp_path: Path) -> None:
    hdr = "test_id,group,source_id,cls,question,expect,must_include,must_not_include,reference_status,reference_evidence,note,must_cite_source"
    (c,) = load_cases(_write(tmp_path, ["X-1,g,,REG,q?,answer,,,PENDING,,,SRC-03|SRC-22"], hdr))
    assert c.must_cite_source == ("SRC-03", "SRC-22")
    with pytest.raises(ValueError, match="SRC-nn"):
        load_cases(_write(tmp_path, ["X-2,g,,REG,q?,answer,,,PENDING,,,Technology Use"], hdr))


def _case(**kw) -> Case:
    base = dict(test_id="T-1", group="g", source_id="", cls="REG", question="q?", expect="answer", must_include=(),
                must_not_include=(), reference_status="PENDING", reference_evidence="", note="",
                must_cite_source=("SRC-22",))
    base.update(kw)
    return Case(**base)


def _rec(cited: list[str | None], text: str = "An answer.") -> dict:
    cites = [{"chunk_id": f"c{i}", "retrievable": True, "eligibility": "eligible", "source_id": s} for i, s in enumerate(cited)]
    return {"http_status": 200, "payload": {"type": "answer", "answer": text, "citations": [{"chunk_id": c["chunk_id"]} for c in cites],
                                            "index_label": None}, "citation_states": cites, "group_state": None}


def test_citing_exactly_the_expected_policy_passes() -> None:
    s = score_run(_case(), _rec(["SRC-22", "SRC-22"]))
    assert s.status == "PASS" and s.checks["cited_source"] is True


def test_citing_the_neighbouring_policy_fails_and_says_which() -> None:
    s = score_run(_case(), _rec(["SRC-03"]))
    assert s.status == "FAIL" and "cited_source" in s.failed
    assert any("SRC-03" in w and "SRC-22" in w for w in s.warnings)


def test_an_extra_citation_beside_the_right_one_also_fails() -> None:
    s = score_run(_case(), _rec(["SRC-22", "SRC-03"]))
    assert s.status == "FAIL" and "cited_source" in s.failed


def test_multi_document_case_needs_every_source() -> None:
    both = _case(must_cite_source=("SRC-03", "SRC-22"))
    assert score_run(both, _rec(["SRC-03", "SRC-22"])).status == "PASS"
    assert score_run(both, _rec(["SRC-22"])).status == "FAIL"


def test_a_citation_with_no_source_id_cannot_satisfy_the_rule() -> None:
    s = score_run(_case(), _rec([None]))
    assert s.status == "FAIL" and "cited_source" in s.failed
    assert any("unknown" in w for w in s.warnings)


def test_the_rule_is_skipped_for_refusals_and_when_empty() -> None:
    refusal = {"http_status": 200, "payload": {"type": "refusal_oo_corpus", "refusal_explanation": "No policy covers that."},
               "citation_states": [], "group_state": None}
    assert "cited_source" not in score_run(_case(expect="refusal"), refusal).checks
    assert "cited_source" not in score_run(_case(must_cite_source=()), _rec(["SRC-03"])).checks
    assert score_run(_case(must_cite_source=()), _rec(["SRC-03"])).status == "PASS"


def test_a_citation_mismatch_is_worst_across_repeats() -> None:
    r = aggregate(_case(), [_rec(["SRC-22"]), _rec(["SRC-03"]), _rec(["SRC-22"])])
    assert r["status"] == "FAIL" and r["pass_runs"] == 2 and "cited_source" in r["failed_checks"]


# --------------------------------------------------------------------------- the keyword guards
def _hits(test_id: str, text: str) -> tuple[bool, bool]:
    """(all must_include tokens present, any must_not_include token present) for an answer text."""
    c, t = BY_ID[test_id], text.lower()
    return all(token_matches(x, t) for x in c.must_include), any(token_matches(x, t) for x in c.must_not_include)


@pytest.mark.parametrize("test_id,text", [
    ("ROB-ST-01", "No. The policy prohibits installing instant messaging software unless the Office of Technology gives permission."),
    ("ROB-ST-01", "You can't install that; additional software has to be cleared by the Office of Technology first."),
    ("ROB-ST-01", "You can’t install that without permission."),
    ("ROB-ST-02", "Adult customers aged 17 and over can ask for unfiltered access."),
    ("ROB-ST-03", "Yes, as long as it does not interfere with your work duties."),
    ("ROB-ST-03", "Personal use is allowed if it doesn't get in the way of your work."),
    ("ROB-ST-04", "It replaces the December 2008 version of the Technology Use Policy."),
    ("ROB-ST-05", "Yes. Employee email is not private and the library may review it."),
    ("ROB-LD-01", "Every volunteer placement starts with a 30 day trial period."),
    ("ROB-LD-02", "Yes, registered volunteers have Worker's Compensation coverage."),
    ("ROB-LD-03", "Send it to the Office of Volunteer Resources."),
    ("ROB-LD-04", "No, using company vehicles is prohibited for volunteers."),
    ("ROB-LD-05", "It is recommended that a term not be longer than one year."),
    ("ROB-LD-05", "Terms should be at most 1-year."),
    ("ROB-EX-01", "No. The administrative fee does not apply to endowment gifts."),
    ("ROB-TH-01", "Yes. Finance reviews and approves proposals of $10,000 or more for new programs."),
    ("ROB-TH-01", "Finance must approve it. Board approval is not required at that amount."),
    ("ROB-TH-01", "Finance approves it; the Board doesn't need to approve a grant this size."),
    ("ROB-TH-01", "Finance must approve it. It does not require Board approval at that amount."),
    ("ROB-TH-01", "Finance reviews it, and it doesn't require Board approval."),
    ("ROB-TH-01", "Finance reviews it, and it doesn\u2019t need the Board approval."),
    ("ROB-AC-01", "Staff should get clearance from Development on printed materials, as the Fundraising policy says M&C must."),
])
def test_guards_accept_honest_paraphrased_answers(test_id: str, text: str) -> None:
    have, forbidden = _hits(test_id, text)
    assert have and not forbidden, (test_id, text)


@pytest.mark.parametrize("test_id,invented", [
    ("ROB-MS-01", "The library reimburses volunteers up to $50 a month for transit."),
    ("ROB-MS-02", "Yes, part-time employees are eligible for annual leave."),
    ("ROB-MS-02", "Part-time employees will be eligible after 90 days."),
    ("ROB-MS-03", "A volunteer may miss three absences before dismissal."),
    ("ROB-MS-03", "After 5 unexcused absences a volunteer is dismissed."),
    ("ROB-TH-01", "Yes, a $50,000 proposal requires Board approval."),
    ("ROB-TH-01", "It needs the Board approval and Finance sign-off."),
    ("ROB-UI-01", "The policy gives you 12 weeks of unpaid leave."),
    ("ROB-UI-01", "You get twelve workweeks."),
    ("ROB-UI-04", "Customers must be courteous and respectful toward others."),
    ("ROB-AC-01", "M&C stands for Marketing and Communications and clears print materials."),
    ("ROB-AC-01", "Marketing & Communication must clear it."),
    ("ROB-ST-01", "Customers should bring headphones."),
])
def test_guards_catch_invented_or_substituted_content(test_id: str, invented: str) -> None:
    assert _hits(test_id, invented)[1], (test_id, invented)


@pytest.mark.parametrize("test_id,honest", [
    ("ROB-MS-01", "The Volunteer Manual says volunteers may deduct transportation costs for income tax purposes; it does not say the library pays them back."),
    ("ROB-MS-02", "The policy says full-time non-union employees are eligible. It does not mention part-time employees."),
    ("ROB-MS-02", "Part-time employees are not mentioned; only full-time non-union staff are eligible."),
    ("ROB-MS-03", "The policy does not give a number; continual absenteeism leads to a review of the assignment."),
    ("ROB-UI-04", "The Technology Use policy only refers to the Rules of Conduct in the Public Behavior policy; it does not list them."),
])
def test_guards_do_not_punish_honest_limitation_answers(test_id: str, honest: str) -> None:
    assert not _hits(test_id, honest)[1], (test_id, honest)


def test_the_acronym_probe_is_tied_to_the_glossary_decision_in_its_note() -> None:
    note = BY_ID["ROB-AC-01"].note
    assert "GLO-2" in note and "must_not_include" in note  # the day-of-approval reminder travels with the case


# --------------------------------------------------------------------------- GLO-05
def test_glo_05_is_a_probe_where_the_acronym_is_the_only_link() -> None:
    glo = {c.test_id: c for c in load_cases(GLOSSARY_CSV)}
    c = glo["GLO-05"]
    assert c.expect == "answer" and c.must_cite_source == ("SRC-06",) and c.source_id == "SRC-06"
    q = c.question.lower()
    assert "dps" in q
    # nothing but the acronym may point at the Unattended Children policy
    assert not any(w in q for w in ("child", "unattended", "closing", "public safety", "alone"))


def test_the_csv_files_share_the_same_header_and_column_count() -> None:
    for path in (ROBUSTNESS_CSV, GLOSSARY_CSV):
        with open(path, newline="", encoding="utf-8") as fh:
            rows = list(csv.reader(fh))
        assert rows[0][-1] == "must_cite_source"
        assert {len(r) for r in rows} == {len(rows[0])}, f"ragged rows in {path.name}"
