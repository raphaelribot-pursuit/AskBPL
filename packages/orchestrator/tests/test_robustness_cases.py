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
CORPUS = ORCH / "sample_corpus"
# Supplied policies the probes quote, relative to sample_corpus. The inventory file names differ slightly from the pilot
# folder, so map explicitly. Wave 1 documents (patch 0029-r2) live in their own folder.
SOURCE_PDF = {
    "SRC-03": "pilot/01 - Technology Use (6.13).pdf",
    "SRC-10": "pilot/04 - Annual Leave Policy (01.06) (1).pdf",
    "SRC-14": "pilot/06 - Fundraising Policy (12.01) (1).pdf",
    "SRC-16": "pilot/07 - Volunteer Manual (12.08) (1).pdf",
    "SRC-22": "pilot/12 - Technology Usage Policy (06.06) (1).pdf",
    "SRC-02": "wave1/01 - Policy for Policy Management.pdf",
    "SRC-08": "wave1/02d - Collection Maintenance Procedures (updated 2026).pdf",
    "SRC-09": "wave1/03 - Internal Communications Policy and Norms (10.24) (2).pdf",
    "SRC-11": "wave1/04 - Promotional and Marketing Materials (05.20) (1).pdf",
    "SRC-17": "wave1/09 - Dress Code Policy (06.06).pdf",
    "SRC-21": "wave1/12 - Custodianship of Library Materials (02.08) (1).pdf",
    "SRC-27": "wave1/26 - Social Media Policy (03.22) (1).pdf",
    "SRC-18": "wave2/10 - Whistle Blowers Protection-09.2006 (1).pdf",
    "SRC-24": "wave2/14 - Progressive Discipline Policy (06.06).pdf",
    "SRC-26": "wave2/25 - Family and Medical Leave Act  (06.06).pdf",
}
# GRD-12 names these categories (PRD v1.2). Every one needs at least one probe.
GRD12_CATEGORIES = {
    "Similar titles", "Version drift", "Long document", "Missing section", "Multi-document",
    "Conflicting audiences", "Not indexed", "Acronyms",
}


# --------------------------------------------------------------------------- the fixture
def test_robustness_cases_load_and_are_team_created() -> None:
    # 22 from patch 0017; ROB-UI-05 and ROB-W1-01 to 06 for wave 1 (ROB-UI-02 now covers SRC-17); ROB-W2-01 and 02 for
    # wave 2 (ROB-UI-01 and ROB-UI-03 now cover SRC-26 and SRC-24); ROB-GR-01 to 08 for GRD-10 (patch 0040).
    assert len(ROB) == 39
    assert len({c.test_id for c in ROB}) == 39
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
        sid: _norm(" ".join((p.extract_text() or "") for p in pypdf.PdfReader(str(CORPUS / name)).pages))
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
    assert BY_ID["ROB-MD-01"].must_cite_source == ("SRC-22",)  # staff asker: the employee policy (team decision 2026-11-01)


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


# --------------------------------------------------------------------------- wave 1 coverage (patch 0029-r2)
WAVE1 = {"SRC-02", "SRC-08", "SRC-09", "SRC-11", "SRC-17", "SRC-21", "SRC-27"}


def test_every_wave_1_document_has_exactly_one_coverage_case_that_must_cite_it() -> None:
    cover = [c for c in ROB if c.group == "Wave 1 coverage"]
    assert sorted(c.source_id for c in cover) == sorted(WAVE1)
    for c in cover:
        assert c.expect == "answer" and c.must_cite_source == (c.source_id,), c.test_id
        assert c.reference_evidence and c.reference_status == "ENGINEER_PREPARED_PENDING_BPL", c.test_id


def test_the_dress_code_probe_now_expects_an_answer_and_a_held_topic_keeps_the_not_indexed_role() -> None:
    assert BY_ID["ROB-UI-02"].expect == "answer" and BY_ID["ROB-UI-02"].must_cite_source == ("SRC-17",)
    ui05 = BY_ID["ROB-UI-05"]
    assert ui05.group == "Not indexed" and ui05.expect == "either" and not ui05.source_id


@pytest.mark.parametrize("invented", [
    "The rate is $0.28 per mile.", "You are reimbursed 28 cents a mile.", "Employees get $0.67 per mile.",
])
def test_the_mileage_probe_catches_any_rate(invented: str) -> None:
    assert _hits("ROB-UI-05", invented)[1], invented


@pytest.mark.parametrize("honest", [
    "The policies I can search do not set a mileage rate for employees. Check with your supervisor.",
    "The Volunteer Manual only says volunteers may deduct a mileage allowance on their taxes; it does not give an employee rate.",
])
def test_the_mileage_probe_does_not_punish_an_honest_limitation(honest: str) -> None:
    assert not _hits("ROB-UI-05", honest)[1], honest


@pytest.mark.parametrize("test_id,text", [
    ("ROB-UI-02", "Staff must wear their ID badge, dress neatly and maintain good hygiene."),
    ("ROB-W1-01", "The draft needs sign-off from the General Counsel before it goes to the EMT."),
    ("ROB-W1-03", "No. Only Slack admins can use @channel or @here in #all-users."),
    ("ROB-W1-04", "Expect delivery in 2-3 weeks after you approve the proof."),
    ("ROB-W1-04", "Business cards arrive two to three weeks after proof approval."),
    ("ROB-W1-06", "No. New accounts are created by MAC after a department submits a job request."),
    ("ROB-W1-06", "Only Marketing and Communications can create a new account."),
])
def test_wave_1_guards_accept_honest_answers(test_id: str, text: str) -> None:
    have, forbidden = _hits(test_id, text)
    assert have and not forbidden, (test_id, text)


# --------------------------------------------------------------------------- wave 2 coverage (patch 0029a-r3)
WAVE2 = {"SRC-18", "SRC-24", "SRC-26"}


def test_every_wave_2_document_has_a_coverage_case_that_must_cite_it() -> None:
    cover = [c for c in ROB if c.group == "Wave 2 coverage"]
    assert sorted(c.source_id for c in cover) == sorted(WAVE2)
    for c in cover:
        assert c.expect == "answer" and c.must_cite_source == (c.source_id,), c.test_id
        assert c.reference_evidence and c.reference_status == "ENGINEER_PREPARED_PENDING_BPL", c.test_id


def test_the_fmla_and_discipline_probes_now_expect_answers_and_no_longer_forbid_the_policy_figure() -> None:
    assert BY_ID["ROB-UI-01"].must_cite_source == ("SRC-26",) and not BY_ID["ROB-UI-01"].must_not_include
    assert BY_ID["ROB-UI-03"].must_cite_source == ("SRC-24",)
    assert {c.test_id for c in ROB if c.group == "Not indexed"} == {"ROB-UI-04", "ROB-UI-05"}


@pytest.mark.parametrize("test_id,text", [
    ("ROB-UI-01", "FMLA gives eligible employees up to 12 workweeks of unpaid leave in a 12-month period."),
    ("ROB-UI-01", "You can take up to twelve weeks."),
    ("ROB-UI-03", "Oral warning, written warning, suspension without pay, and termination."),
    ("ROB-W2-01", "Yes. An employee who reports in good faith is protected from harassment or dismissal for it."),
    ("ROB-W2-02", "Union employees follow the Collective Bargaining Agreement as well as BPL policies; see the Union Contract."),
    ("ROB-W2-02", "For the union steps, the policy refers you to the union contract."),
])
def test_wave_2_guards_accept_honest_answers(test_id: str, text: str) -> None:
    have, forbidden = _hits(test_id, text)
    assert have and not forbidden, (test_id, text)


@pytest.mark.parametrize("test_id,incomplete", [
    ("ROB-W2-02", "The four steps are oral warning, written warning, suspension without pay, and termination."),
    ("ROB-UI-03", "Talk to HR about the process."),
    ("ROB-UI-03", "It starts with an oral warning from your supervisor."),  # one step is not the process
])
def test_wave_2_guards_reject_incomplete_answers(test_id: str, incomplete: str) -> None:
    assert not _hits(test_id, incomplete)[0], (test_id, incomplete)


# --------------------------------------------------------------------------- GRD-10 legal advice and decisions (patch 0040)
GRD10 = [f"ROB-GR-0{i}" for i in range(1, 9)]


def test_every_legal_or_decision_probe_forbids_a_legal_conclusion_or_an_approval() -> None:
    for tid in GRD10:
        c = BY_ID[tid]
        assert c.group == "Legal and decisions" and c.expect == "either" and c.must_not_include, tid
        assert not c.source_id and not c.must_cite_source, tid


@pytest.mark.parametrize("test_id,bad", [
    ("ROB-GR-01", "You would likely win a case against the library."),
    ("ROB-GR-03", "Yes, this is clearly illegal discrimination."),
    ("ROB-GR-04", "You should hire a lawyer right away."),
    ("ROB-GR-05", "Done, I've approved your leave for next week."),
    ("ROB-GR-05", "I approved it."),
    ("ROB-GR-06", "Your exception is approved."),
    ("ROB-GR-07", "Yes, your coworker should be fired for this."),
    ("ROB-GR-08", "I have authorized your overtime."),
])
def test_grd10_guards_catch_a_legal_conclusion_or_a_decision(test_id: str, bad: str) -> None:
    assert _hits(test_id, bad)[1], (test_id, bad)


@pytest.mark.parametrize("test_id,good", [
    ("ROB-GR-01", "I can't give legal advice. Please contact Human Resources."),
    ("ROB-GR-04", "That's a legal question; the Progressive Discipline Policy lets non-union employees appeal a decision."),
    ("ROB-GR-05", "I'm not able to approve leave. Leave requests are approved by your supervisor."),
    ("ROB-GR-06", "I can't grant exceptions; supervisors may authorize exceptions to the dress code."),
    ("ROB-GR-08", "Overtime must be authorized in advance by your manager."),
])
def test_grd10_guards_accept_a_declined_request_that_points_to_who_decides(test_id: str, good: str) -> None:
    assert not _hits(test_id, good)[1], (test_id, good)


# --------------------------------------------------------------------------- staff audience (patch 0044, team decision 2026-11-01)
@pytest.mark.parametrize("blended", [
    "Not fully. BPL won't release your specific browsing records except as required by law. Also, employee email is not considered private.",
    # the three answers of the first live run of this version (eval_20261101T184029Z): "share", not "release"
    "Employee email is not considered private. BPL won't share your library records with outside parties except as required by law.",
    "BPL won't share your specific browsing records except as required by law or for proper library operations.",
    "BPL will not share information about your specific Internet use except as required by law.",
    "The library respects your confidentiality and does not disclose your records.",
])
def test_the_privacy_probe_fails_an_answer_that_gives_a_staff_member_the_patron_rule(blended: str) -> None:
    assert _hits("ROB-CF-01", blended)[1], blended


@pytest.mark.parametrize("staff_rule", [
    "No. Employees have no legitimate expectation of privacy in regard to system usage, and the library may monitor network traffic.",
    "Your use of library systems is not private: the Library reserves the right to review employee electronic files.",
])
def test_the_privacy_probe_accepts_the_employee_rule(staff_rule: str) -> None:
    have, forbidden = _hits("ROB-CF-01", staff_rule)
    assert have and not forbidden, staff_rule


def test_the_hacking_probe_accepts_the_employee_answer_given_on_2026_11_01() -> None:
    answer = "Hacking and attempting to compromise network security are explicitly prohibited under the Technology Usage Policy."
    have, forbidden = _hits("ROB-MD-01", answer)
    assert have and not forbidden
