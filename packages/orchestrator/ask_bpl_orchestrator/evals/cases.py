"""Test-case fixtures (Document 06 s.4). Question wording is frozen: never edit client_questions.csv text."""

from __future__ import annotations

import csv
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

DATA_DIR = Path(__file__).resolve().parents[2] / "eval_data"
CLIENT_CSV = DATA_DIR / "client_questions.csv"
REGRESSION_CSV = DATA_DIR / "regression_cases.csv"
# Glossary probes (patch 0016). Run only with `askbpl-eval --set glossary`; never part of `--set all`, so the client-30 and
# team-set baselines stay comparable from run to run.
GLOSSARY_CSV = DATA_DIR / "glossary_cases.csv"
# Robustness probes (patch 0017; PRD GRD-12): similar titles, version drift, long documents, silent policies,
# thresholds, multi-document questions, policies that are not indexed, acronyms. Run only with
# `askbpl-eval --set robustness`; never part of `--set all`, for the same reason as the glossary probes.
ROBUSTNESS_CSV = DATA_DIR / "robustness_cases.csv"

_CLS = {"IN", "OUT", "REG", "SEC"}
_EXPECT = {"answer", "refusal", "either", "pii_reject", "crisis"}
_COLUMNS = {"test_id", "group", "source_id", "cls", "question", "expect",
            "must_include", "must_not_include", "reference_status", "reference_evidence", "note"}


_SOURCE_ID = re.compile(r"^SRC-\d+$")


@dataclass(frozen=True)
class Case:
    test_id: str
    group: str
    source_id: str
    cls: str  # IN / OUT = client script; REG / SEC = team-created, never blended into client results
    question: str
    expect: str
    must_include: Tuple[str, ...]
    must_not_include: Tuple[str, ...]
    reference_status: str  # PENDING | ENGINEER_PREPARED_PENDING_BPL  (never "approved": BPL has not approved any key)
    reference_evidence: str
    note: str
    # Optional column (patch 0017). SRC ids the answer's citations must come from, ``|``-separated. The set of cited
    # sources must equal this set: a missing one (multi-document question) and an extra one (the neighbouring policy
    # with a similar title) both fail. Empty means "do not check". Only applies to answers, never to refusals.
    must_cite_source: Tuple[str, ...] = ()

    @property
    def is_client(self) -> bool:
        return self.cls in {"IN", "OUT"}


def _split(value: str) -> Tuple[str, ...]:
    """Split a CSV cell into tokens on ``|``, but not on a ``|`` inside parentheses or square brackets.

    That lets a ``re:`` token use alternation inside a group, e.g. ``re:\\b\\d+\\s+(days|weeks)\\b``. A top-level
    ``|`` always separates tokens, so wrap any alternation in a group.
    """
    parts: list[str] = []
    depth = 0
    cur: list[str] = []
    for ch in value:
        if ch in "([":
            depth += 1
        elif ch in ")]" and depth:
            depth -= 1
        if ch == "|" and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return tuple(p.strip() for p in parts if p.strip())


def load_cases(path: Path) -> List[Case]:
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        missing = _COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path.name}: missing columns {sorted(missing)}")
        cases: List[Case] = []
        seen: set[str] = set()
        for n, row in enumerate(reader, start=2):
            tid = (row["test_id"] or "").strip()
            if not tid or tid in seen:
                raise ValueError(f"{path.name} line {n}: empty or duplicate test_id {tid!r}")
            seen.add(tid)
            if row["cls"] not in _CLS or row["expect"] not in _EXPECT:
                raise ValueError(f"{path.name} line {n}: bad cls/expect for {tid}")
            if not row["question"].strip():
                raise ValueError(f"{path.name} line {n}: empty question for {tid}")
            cite_src = _split(row.get("must_cite_source") or "")
            bad = [t for t in cite_src if not _SOURCE_ID.match(t)]
            if bad:
                raise ValueError(f"{path.name} line {n}: must_cite_source for {tid} must be SRC-nn ids, got {bad}")
            cases.append(Case(
                test_id=tid, group=row["group"], source_id=row["source_id"].strip(), cls=row["cls"],
                question=row["question"], expect=row["expect"],
                must_include=_split(row["must_include"]), must_not_include=_split(row["must_not_include"]),
                reference_status=row["reference_status"], reference_evidence=row["reference_evidence"],
                note=row["note"], must_cite_source=cite_src,
            ))
    return cases


def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def questions_sha256(cases: List[Case]) -> str:
    """Hash of the question wording only, in order (freeze check for the 30 client questions)."""
    return hashlib.sha256("\n".join(c.question for c in cases).encode()).hexdigest()
