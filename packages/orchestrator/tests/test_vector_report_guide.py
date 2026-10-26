"""Patch 0022: the curator guide and corpus report stay in step with `askbpl-vector-report`."""

from __future__ import annotations

import re
from pathlib import Path

from ask_bpl_orchestrator import corpus_report as cr

ORCH = Path(__file__).resolve().parents[1]
REPO = ORCH.parents[1]

GUIDE = REPO / "docs" / "CURATOR_WORKFLOW.md"


def test_the_guide_names_the_vector_report_with_a_real_flag_and_every_finding_code_it_can_raise() -> None:
    g = GUIDE.read_text()
    assert "askbpl-vector-report --strict" in g
    scripts = dict(re.findall(r'^(askbpl-[a-z\-]+) = "([^"]+)"', (ORCH / "pyproject.toml").read_text(), re.M))
    assert set(re.findall(r"`(askbpl-[a-z]+(?:-[a-z]+)*)[ `]", g)) <= set(scripts)
    src = (ORCH / "ask_bpl_orchestrator" / "vector_report.py").read_text()
    raised = set(re.findall(r'Finding\(\s*"([a-z_]+)"', src)) - {"list_truncated", "count_surplus"}  # minor notes need no row
    assert raised, "no finding codes found in the source"
    for code in raised:
        assert f"`{code}`" in g, f"the guide's error table has no row for {code}"


def test_the_guide_no_longer_claims_nothing_can_see_pinecone() -> None:
    low = " ".join(GUIDE.read_text().lower().split())
    assert "askbpl-corpus-report` cannot see pinecone" in low and "there is still no command that deletes stray vectors" in low
    assert "cannot see pinecone" in low  # the 0020 guide test still pins this phrase


def test_the_corpus_report_points_to_the_vector_report_but_still_never_calls_pinecone() -> None:
    assert any("askbpl-vector-report" in line for line in cr.CANNOT_TELL)
    src = (ORCH / "ask_bpl_orchestrator" / "corpus_report.py").read_text()
    code = re.sub(r'"""(.*?)"""', "", src, flags=re.S)
    assert "get_pinecone_index" not in code and "describe_index_stats" not in code
