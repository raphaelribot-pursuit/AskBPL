"""askbpl-eval --compare: line up recorded runs made under different roles (patch 0025; PRD ROLE-2, ROLE-3, ROLE-7).

Offline and free: it reads recorded run files and asks nothing. The first file is the baseline (normally the General
run); every other file is compared with it, case by case.

What it can and cannot show
  * It flags a different answer-or-refuse decision, a different set of cited documents, and an answer with more
    sentences than the baseline. These are the things a role lens must NOT change (ROLE-2) or add (ROLE-7).
  * Model output varies from run to run. A difference is only a HARD flag when both sides were stable (every repeat
    of the case gave the same outcome) and still disagree. A difference where either side wavered is a SOFT flag:
    look at the case, and compare with how much the General run varies on its own.
  * It cannot say whether a lens invented a duty or framed the answer well. That needs a person reading the
    answers side by side; the CSV it writes has the answers next to each other and blank score columns for that.
"""

from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ask_bpl_orchestrator.evals.scoring import outcome_of, response_text

REVIEW_COLUMNS = ["Same_substance_YN", "Invented_duty_YN", "Framing_helpful_1to5", "reviewer_notes"]
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])[\"')\]]*\s+(?=[\"'(\[]*[A-Z0-9])")
HARD = ("DECISION_DIFFERS_STABLE",)


class CompareError(ValueError):
    """A run file cannot be compared; the message says why."""


def sentence_count(text: str) -> int:
    """Approximate sentence count (advisory: abbreviations such as "U.S." can add one)."""
    text = " ".join((text or "").split())
    return len(_SENTENCE_SPLIT.split(text)) if text else 0


def load_run(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CompareError(f"cannot read {path}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("records"), dict) or not data["records"]:
        raise CompareError(f"{path} is not a recorded askbpl-eval run (no 'records')")
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    role = meta.get("role")
    label = str(role) if role else "general"  # a run recorded before patch 0024 sent no role and is General
    if role and meta.get("role_sent") is False:
        label += "-default"  # run with no --role: the server's default role was applied, nothing was requested
    data["_label"] = label
    data["_path"] = str(path)
    return data


def _case_view(recs: List[Dict[str, Any]], status: Optional[str]) -> Dict[str, Any]:
    outcomes = [outcome_of(r.get("http_status", 0), r.get("payload") or {}) for r in recs]
    cited: set = set()
    for r in recs:
        if outcome_of(r.get("http_status", 0), r.get("payload") or {}) == "answer":
            for c in r.get("citation_states") or []:
                cited.add(str(c.get("title") or c.get("document_id") or "?"))
    answers = [r for r, o in zip(recs, outcomes) if o == "answer"]
    shown = (answers or recs)[-1].get("payload") or {}
    return {
        "outcomes": outcomes, "cited": cited, "status": status or "",
        "sentences": max((sentence_count((r.get("payload") or {}).get("answer", "")) for r in answers), default=0),
        "text": response_text(shown),
        "role_labels": sorted({str(((r.get("payload") or {}).get("role") or {}).get("label")) for r in answers
                               if (r.get("payload") or {}).get("role")}),
    }


def compare_runs(runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compare runs[1:] with runs[0]. Pure: takes loaded runs, returns rows and a summary."""
    if len(runs) < 2:
        raise CompareError("give at least two run files to compare (the baseline first)")
    labels = [r["_label"] for r in runs]
    if len(set(labels)) != len(labels):
        raise CompareError(f"two runs have the same role label {labels}; compare one run per role")
    ids = [set(r["records"]) for r in runs]
    shared = sorted(set.intersection(*ids))
    skipped = sorted(set.union(*ids) - set(shared))
    status_of = [{x["test_id"]: x["status"] for x in (r.get("results") or []) if isinstance(x, dict)} for r in runs]
    rows: List[Dict[str, Any]] = []
    for tid in shared:
        views = {lab: _case_view(r["records"][tid], status_of[i].get(tid)) for i, (lab, r) in enumerate(zip(labels, runs))}
        base = views[labels[0]]
        question = next((x.get("question") for x in (runs[0].get("results") or []) if x.get("test_id") == tid), "")
        flags: Dict[str, List[str]] = {}
        for lab in labels[1:]:
            v, f = views[lab], []
            if set(v["outcomes"]) != set(base["outcomes"]):
                stable = len(set(v["outcomes"])) == 1 and len(set(base["outcomes"])) == 1
                f.append("DECISION_DIFFERS_STABLE" if stable else "DECISION_DIFFERS_UNSTABLE")
            if base["cited"] and v["cited"] and base["cited"] != v["cited"]:
                f.append("CITATIONS_DIFFER")
            if v["sentences"] > base["sentences"] > 0:
                f.append("LONGER_THAN_BASELINE")
            if f:
                flags[lab] = f
        rows.append({"test_id": tid, "question": question, "views": views, "flags": flags})
    counts: Dict[str, int] = {}
    for row in rows:
        for fl in row["flags"].values():
            for name in fl:
                counts[name] = counts.get(name, 0) + 1
    return {
        "labels": labels, "baseline": labels[0], "rows": rows, "skipped_ids": skipped,
        "counts": counts, "hard": sum(counts.get(h, 0) for h in HARD),
        "echo_failures": sum(1 for r in runs for x in (r.get("results") or [])
                             if isinstance(x, dict) and "role_echo" in (x.get("failed_checks") or [])),
    }


def write_compare_csv(result: Dict[str, Any], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = out_dir / f"eval_{stamp}_compare_{'_vs_'.join(result['labels'])}.csv"
    labels = result["labels"]
    header = ["test_id", "question"]
    for lab in labels:
        header += [f"{lab}_outcomes", f"{lab}_status", f"{lab}_cited", f"{lab}_sentences", f"{lab}_answer"]
    header += ["flags"] + REVIEW_COLUMNS
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        for row in result["rows"]:
            line: List[Any] = [row["test_id"], row["question"]]
            for lab in labels:
                v = row["views"][lab]
                line += ["/".join(v["outcomes"]), v["status"], "; ".join(sorted(v["cited"])), v["sentences"], v["text"]]
            line.append(" | ".join(f"{lab}: {', '.join(f)}" for lab, f in row["flags"].items()))
            w.writerow(line + [""] * len(REVIEW_COLUMNS))
    return path


def print_compare(result: Dict[str, Any], path: Path) -> None:
    print(f"\n== ROLE COMPARISON (baseline: {result['baseline']}; compared: {', '.join(result['labels'][1:])})")
    print(f"cases compared: {len(result['rows'])}" + (f"; not in every file, skipped: {', '.join(result['skipped_ids'])}"
                                                      if result["skipped_ids"] else ""))
    for row in result["rows"]:
        for lab, flags in row["flags"].items():
            base, v = row["views"][result["baseline"]], row["views"][lab]
            print(f"{', '.join(flags):<26} {row['test_id']:<14} {result['baseline']}={'/'.join(base['outcomes'])}  "
                  f"{lab}={'/'.join(v['outcomes'])}")
    if not result["counts"]:
        print("no differences in decision, cited documents or length")
    print(f"\nhard flags (a stable decision changed with the role): {result['hard']}")
    print(f"role echo failures (the server reported a different role than was sent): {result['echo_failures']}")
    print("A person must still read the answers side by side: this cannot see an invented duty or a poor framing.")
    print(f"\nwritten: {path}  (review columns left blank)")
