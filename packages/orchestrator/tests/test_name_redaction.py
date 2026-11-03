"""Patch 0064 (SAF-1, SAF-10; team decision 2026-11-02): people's names are replaced before a question is stored or sent
to an outside service. Offline detection from config/person_names.txt (SSA public data) plus three rules."""

from __future__ import annotations

import glob
from pathlib import Path

import pytest

from ask_bpl_orchestrator.evals.cases import load_cases
from ask_bpl_orchestrator.services import name_redaction as nr

ORCH = Path(__file__).resolve().parents[1]

POSITIVES = [
    ("Can Maria approve my leave?", "Can a colleague approve my leave?"),
    ("Is it okay if John Smith covers my shift?", "Is it okay if a colleague covers my shift?"),
    ("My supervisor Denise said I can't wear jeans, is that right?", "My supervisor said I can't wear jeans, is that right?"),
    ("Can I report Tom for harassment?", "Can I report a colleague for harassment?"),
    ("What should I do if Ms. Rodriguez asks me to check out her books?", "What should I do if a colleague asks me to check out her books?"),
    ("Does Dr. Patel need to approve my FMLA?", "Does a colleague need to approve my FMLA?"),
    ("Kevin keeps posting @channel in all-users, is that allowed?", "A colleague keeps posting @channel in all-users, is that allowed?"),
    ("Can Aisha and I swap annual leave days?", "Can a colleague and I swap annual leave days?"),
    ("Is Priya allowed to take home weeded books?", "Is a colleague allowed to take home weeded books?"),
    ("my manager jennifer wants me to work overtime, can she?", "my manager wants me to work overtime, can she?"),
    ("Can Mr. Okafor donate to the library fundraiser?", "Can a colleague donate to the library fundraiser?"),
    ("What if Carlos from IT installs Slack on my computer?", "What if a colleague from IT installs Slack on my computer?"),
    ("Can I tell Lawrence about the conflict of interest?", "Can I tell a colleague about the conflict of interest?"),
    ("Is Ana Lopez eligible for annual leave after 90 days?", "Is a colleague eligible for annual leave after 90 days?"),
    ("Can Jamal use the library computer for personal email?", "Can a colleague use the library computer for personal email?"),
    ("Does Wei need approval to post on Instagram for the branch?", "Does a colleague need approval to post on Instagram for the branch?"),
    ("Can Sarah's daughter volunteer at the branch?", "Can a colleague's daughter volunteer at the branch?"),
    ("If Mike is out sick, who approves my leave?", "If a colleague is out sick, who approves my leave?"),
    ("Can Grace Kim approve the gift?", "Can a colleague approve the gift?"),
    ("Is it a conflict of interest if I hire my cousin Marcus?", "Is it a conflict of interest if I hire my cousin?"),
    ("Can my coworker Tasha check out books for me?", "Can my coworker check out books for me?"),
    ("Does Rebecca Cohen in HR handle FMLA?", "Does a colleague in HR handle FMLA?"),
    ("Can Luis wear a hoodie at the desk?", "Can a colleague wear a hoodie at the desk?"),
    ("Should I tell Ms. Nguyen about the donation?", "Should I tell a colleague about the donation?"),
]

NEAR_MISSES = [
    "What is the annual leave policy?",
    "Can I take FMLA leave for my mother?",
    "Who approves overtime at Central Library?",
    "Does the Brooklyn Public Library allow personal email?",
    "Can I apply for a grant through the Development Office?",
    "Will I be paid if I'm sent home for my clothing?",
    "What is the dress code at Grand Army Plaza?",
    "Can I use Slack @channel in #all-users?",
    "What does the Whistle-Blower Protection Policy say about retaliation?",
    "Does the Volunteer Manual cover teens?",
    "Can I post on Instagram or Facebook about a branch event?",
    "What is HR's role in progressive discipline?",
    "Can I accept a gift from a patron during Thanksgiving?",
    "Do union employees follow the Collective Bargaining Agreement?",
    "What does the Executive Director approve?",
    "Can I wear Crocs to work?",
    "Is ThriftBooks the approved vendor for weeded items?",
    "What happens on Monday if I'm late?",
    "Can I take annual leave in May?",
    "Can patrons use Microsoft Word on the public computers?",
    "What is the NYS Child Abuse Hotline?",
    "Does the Materials Selection Policy cover religious books like the Bible?",
    "Can I bring my dog to the Flatbush branch?",
    "What does the Technology Usage Policy say about Google Drive?",
    "Is Juneteenth a paid holiday?",
    "Is there a grace period for returning library materials?",
    "May I wear a hat at the desk?",
    "Will Mark-to-market rules apply?",
    "What does the LIBRARY BILL OF RIGHTS say?",
    "Does the Grace Policy apply here?",
]


@pytest.mark.parametrize("question,expected", POSITIVES)
def test_a_name_is_replaced_and_the_question_still_reads_naturally(question: str, expected: str) -> None:
    r = nr.redact(question)
    assert r.text == expected and r.removed >= 1


@pytest.mark.parametrize("question", NEAR_MISSES)
def test_policy_questions_without_a_person_are_left_exactly_as_typed(question: str) -> None:
    r = nr.redact(question)
    assert (r.text, r.removed) == (question, 0), nr.find_names(question)


def test_none_of_the_evaluation_questions_is_changed() -> None:
    """So patch 0064 cannot change what the model is asked for any evaluation question, and needs no paid run."""
    seen = 0
    for f in sorted(glob.glob(str(ORCH / "eval_data" / "*.csv"))):
        for case in load_cases(Path(f)):
            seen += 1
            assert nr.redact(case.question).text == case.question, (case.test_id, case.question)
    assert seen >= 81


def test_earlier_turns_are_redacted_too() -> None:
    turns = [{"role": "user", "content": "Can Maria approve my leave?"}, {"role": "assistant", "content": "The policy says HR approves."}]
    out, n = nr.redact_context(turns)
    assert n == 1 and out[0]["content"] == "Can a colleague approve my leave?" and out[1] == turns[1]
    assert turns[0]["content"] == "Can Maria approve my leave?"  # the caller's list is not modified
    assert nr.redact_context(None) == (None, 0)


def test_known_limits_are_what_the_documentation_says() -> None:
    assert nr.redact("Should Selvon sign my volunteer form?").removed == 0  # a rare name not in the list
    assert nr.redact("Can staff remove Toni Morrison books?").removed == 1  # public figures are replaced too


def test_the_names_file_is_shipped_with_its_source_note() -> None:
    names = nr._names()
    assert 30000 < len(names) < 50000
    assert {"maria", "priya", "jamal", "aisha", "tasha"} <= names
    assert not {"manual", "brooklyn", "media", "monday", "any", "key"} & names
    note = (ORCH / "config" / "person_names_SOURCE.md").read_text(encoding="utf-8")
    assert "public domain" in note and "ssa.gov" in note


@pytest.mark.parametrize("question", ["Was Maria fired for that?", "Was my coworker disciplined?", "Has my manager been suspended?"])
def test_a_named_persons_personnel_history_is_refused_by_the_guard(question: str) -> None:
    from ask_bpl_orchestrator.services.intent_guard import intent_causes
    from ask_bpl_orchestrator.services.refusal import RefusalCause

    redacted = nr.redact(question).text
    assert RefusalCause.private_employee_details in (intent_causes(question) + intent_causes(redacted))


@pytest.mark.parametrize("question", ["Can an employee be fired for being late?", "Is a colleague disciplined if they are late?"])
def test_policy_questions_about_discipline_are_still_answered(question: str) -> None:
    from ask_bpl_orchestrator.services.intent_guard import intent_causes

    assert intent_causes(question) == [] and intent_causes(nr.redact(question).text) == []
