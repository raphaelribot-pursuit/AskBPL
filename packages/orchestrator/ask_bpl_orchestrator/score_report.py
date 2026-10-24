"""askbpl-score-report: READ-ONLY evidence for the retrieval-gate thresholds (patch 0018, PRD GRD-2).

    askbpl-score-report eval_data/results/<run>_live.json --log eval_data/results/<matching>_app.log
    askbpl-score-report a.json b.json --log a_app.log b_app.log --csv /tmp/scores.csv

For every recorded ask it shows what the gate saw (best score, second score, chunks at the floor) next to what the
case expected, then summarises how the scores of wrongly refused questions compare with the scores of correctly refused
ones. It changes nothing: no database, no configuration, no thresholds, no glossary.

How the join works: each response in the results file and each `ask_completed` / `retrieval_gate` line in the app log
carry the same `request_id`, so the join is exact and does not depend on the order of asks. Logs written before patch
0018 have no `retrieval_gate` line: the best score is still shown (from `ask_completed`) but the second score and the
count of chunks at the floor are not, and the report says so.

What it cannot tell you: whether a threshold is right. The sample is small, scores are embedding similarities, and a
what-if line only says how many recorded runs a different single-chunk cut-off would have admitted, not whether the
model would then answer them well.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ask_bpl_orchestrator.evals.cases import (
    CLIENT_CSV,
    GLOSSARY_CSV,
    REGRESSION_CSV,
    ROBUSTNESS_CSV,
    Case,
    load_cases,
)
from ask_bpl_orchestrator.evals.scoring import outcome_of, score_run

DEFAULT_FLOOR, DEFAULT_STRONG = 0.40, 0.45
LOG_EVENTS = ("ask_completed", "retrieval_gate")
# What a run is, from the gate's point of view. Only expectations of an answer or a refusal take part in the
# comparison; "either", PII and crisis cases do not say what the gate should have done.
OVER_REFUSED = "refused, answer expected"
ANSWERED_OK = "answered, answer expected"
REFUSED_OK = "refused, refusal expected"
ANSWERED_WRONG = "answered, refusal expected"
UNSCORED = "no expectation about the gate"


@dataclass
class Row:
    test_id: str
    run: int
    expect: str
    outcome: str
    status: str
    request_id: Optional[str]
    joined: bool
    gate_known: bool
    top: Optional[float]
    second: Optional[float]
    chunks: Optional[int]
    at_floor: Optional[int]
    reason: str
    stage: str
    passed_by: str
    kind: str


def all_cases() -> Dict[str, Case]:
    cases: Dict[str, Case] = {}
    for path in (CLIENT_CSV, REGRESSION_CSV, GLOSSARY_CSV, ROBUSTNESS_CSV):
        for c in load_cases(path):
            cases[c.test_id] = c
    return cases


def read_log_events(paths: Sequence[Path]) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """{request_id: {event name: entry}} from one or more app logs. Lines that are not our JSON are ignored."""
    events: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for path in paths:
        for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
            start = line.find('{"event"')
            if start < 0:
                continue
            try:
                entry = json.loads(line[start:].strip())
            except ValueError:
                continue
            if isinstance(entry, dict) and entry.get("event") in LOG_EVENTS and entry.get("request_id"):
                events.setdefault(str(entry["request_id"]), {})[entry["event"]] = entry
    return events


def classify(expect: str, outcome: str) -> str:
    if expect == "answer":
        return ANSWERED_OK if outcome == "answer" else OVER_REFUSED if outcome == "refusal" else UNSCORED
    if expect == "refusal":
        return REFUSED_OK if outcome == "refusal" else ANSWERED_WRONG if outcome == "answer" else UNSCORED
    return UNSCORED


def build_rows(runs: Sequence[Dict[str, Any]], events: Dict[str, Dict[str, Dict[str, Any]]],
               cases: Dict[str, Case]) -> List[Row]:
    rows: List[Row] = []
    for run in runs:
        for tid, recs in run["records"].items():
            case = cases.get(tid)
            for i, rec in enumerate(recs):
                payload = rec.get("payload") or {}
                rid = payload.get("request_id")
                ev = events.get(str(rid), {}) if rid else {}
                done, gate = ev.get("ask_completed"), ev.get("retrieval_gate")
                outcome = outcome_of(rec.get("http_status", 0), payload)
                expect = case.expect if case else "?"
                top = (gate or done or {}).get("top_score")
                rows.append(Row(
                    test_id=tid, run=i, expect=expect, outcome=outcome,
                    status=score_run(case, rec).status if case else "?",
                    request_id=str(rid) if rid else None, joined=bool(done or gate), gate_known=gate is not None,
                    top=top, second=gate.get("second_score") if gate else None,
                    chunks=(gate or done or {}).get("chunks_returned"),
                    at_floor=gate.get("chunks_at_floor") if gate else None,
                    reason=(done or {}).get("refusal_reason") or "", stage=(done or {}).get("refusal_stage") or "",
                    passed_by=(gate or {}).get("passed_by") or "", kind=classify(expect, outcome),
                ))
    return rows


def _fmt(x: Optional[float]) -> str:
    return "-" if x is None else f"{x:.4f}"


def _spread(values: List[float]) -> str:
    if not values:
        return "none"
    return f"n={len(values)}  min {min(values):.4f}  median {statistics.median(values):.4f}  max {max(values):.4f}"


def render(rows: List[Row], floor: float, strong: float, *, show_rows: bool = True) -> str:
    out: List[str] = []
    if show_rows:
        out.append(f"{'case':<11}{'run':>3} {'expect':<8}{'outcome':<8}{'status':<8}{'top':>7}{'second':>8}{'at_floor':>9}"
                   f"  {'refusal_reason':<15}{'stage':<15}passed_by")
        for r in rows:
            note = "" if r.joined else "   (no log line for this request)"
            out.append(f"{r.test_id:<11}{r.run:>3} {r.expect:<8}{r.outcome:<8}{r.status:<8}{_fmt(r.top):>7}"
                       f"{_fmt(r.second):>8}{'-' if r.at_floor is None else r.at_floor:>9}  {r.reason:<15}{r.stage:<15}"
                       f"{r.passed_by}{note}")
        out.append("")

    unjoined = [r for r in rows if not r.joined]
    no_gate = [r for r in rows if r.joined and not r.gate_known]
    out.append(f"== {len(rows)} recorded asks; floor {floor}, strong {strong}")
    if unjoined:
        out.append(f"!! {len(unjoined)} ask(s) have no log line (use the app log written by the same run). "
                   f"First: {', '.join(f'{r.test_id}#{r.run}' for r in unjoined[:5])}")
    if no_gate:
        out.append(f"-- {len(no_gate)} ask(s) come from a log written before patch 0018: best score shown, but no second "
                   "score or chunks-at-floor count.")

    scored = [r for r in rows if r.top is not None and r.kind != UNSCORED]
    by: Dict[str, List[Row]] = {k: [r for r in scored if r.kind == k] for k in
                                (ANSWERED_OK, OVER_REFUSED, REFUSED_OK, ANSWERED_WRONG)}
    gate_stopped = [r for r in by[REFUSED_OK] if r.stage == "retrieval_gate"]
    model_stopped = [r for r in by[REFUSED_OK] if r.stage != "retrieval_gate"]

    out.append("\n-- Best score by what happened against what was expected")
    for label, group in (("answered, answer expected", by[ANSWERED_OK]),
                         ("refused, answer expected (over-refusal)", by[OVER_REFUSED]),
                         ("refused at the gate, refusal expected", gate_stopped),
                         ("answered, refusal expected", by[ANSWERED_WRONG])):
        out.append(f"  {label:<42}{_spread([r.top for r in group])}")
    out.append(f"  refused later (model/citation), refusal expected: {len(model_stopped)} run(s), not part of the gate comparison")

    if by[OVER_REFUSED]:
        out.append("\n-- Over-refusals (answer expected, refused), highest score first")
        out.append(f"  {'case':<11}{'run':>3}{'top':>8}{'second':>8}{'at_floor':>9}{'to_strong':>10}{'to_2nd_chunk':>13}  reason / stage")
        for r in sorted(by[OVER_REFUSED], key=lambda r: -(r.top or 0)):
            to_strong = None if r.top is None else max(0.0, strong - r.top)
            to_second = None if r.second is None else max(0.0, floor - r.second)
            out.append(f"  {r.test_id:<11}{r.run:>3}{_fmt(r.top):>8}{_fmt(r.second):>8}"
                       f"{'-' if r.at_floor is None else r.at_floor:>9}{_fmt(to_strong):>10}{_fmt(to_second):>13}  {r.reason} / {r.stage}")
        out.append("  to_strong: how far the best score is below the strong threshold. to_2nd_chunk: how far the second-best "
                   "score is below the floor (the other way through the gate).")

    if by[ANSWERED_WRONG]:
        out.append("\n-- Answered although a refusal was expected (read the answers; some are accurate limitation answers)")
        for r in sorted(by[ANSWERED_WRONG], key=lambda r: -(r.top or 0)):
            out.append(f"  {r.test_id:<11}{r.run:>3}  top {_fmt(r.top)}  status {r.status}")

    # What-if: lower the strong threshold only. Each recorded gate-stopped run that scored at or above the cut-off would
    # have been admitted to the model. Nothing else about the gate changes. Refusals made later by the model are not
    # about thresholds and are left out.
    over_gate = [r for r in by[OVER_REFUSED] if r.stage == "retrieval_gate"]
    later = len(by[OVER_REFUSED]) - len(over_gate)
    if over_gate or gate_stopped:
        out.append("\n-- What-if: a single chunk at or above X passes (two chunks at the floor still pass). Recorded runs only.")
        if later:
            out.append(f"  ({later} over-refusal run(s) were refused after the gate, by the model or citation check: not shown here.)")
        out.append(f"  {'X':>6}  {'over-refusals admitted':>24}  {'expected refusals admitted':>28}")
        steps = max(1, round((strong - floor) / 0.01))
        for k in range(steps + 1):
            x = round(floor + k * (strong - floor) / steps, 4)  # rounded so a score exactly on a cut-off is not lost to float error
            over = sum(1 for r in over_gate if (r.top or 0) >= x)
            prot = sum(1 for r in gate_stopped if (r.top or 0) >= x)
            out.append(f"  {x:>6.3f}  {f'{over} of {len(over_gate)}':>24}  {f'{prot} of {len(gate_stopped)}':>28}")
        if over_gate and gate_stopped:
            hi = max(r.top or 0 for r in gate_stopped)
            above = [r for r in over_gate if (r.top or 0) > hi]
            if len(above) == len(over_gate):
                verdict = "every over-refusal scores above it, so a cut-off between them would separate these runs."
            else:
                verdict = (f"{len(over_gate) - len(above)} of {len(over_gate)} over-refusals score at or below it: "
                           "score alone does not separate the two groups on this data.")
            out.append(f"  Highest score among gate-stopped expected refusals: {hi:.4f}; {verdict}")
        out.append("  This is evidence from the recorded runs, not a recommendation. Admitting a run only lets the model "
                   "see the evidence; it can still refuse. Thresholds change only with a full before-and-after run.")
    return "\n".join(out)


def write_csv(rows: List[Row], path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["test_id", "run", "expect", "outcome", "status", "kind", "top_score", "second_score", "chunks_returned",
                    "chunks_at_floor", "refusal_reason", "refusal_stage", "passed_by", "joined_to_log", "request_id"])
        for r in rows:
            w.writerow([r.test_id, r.run, r.expect, r.outcome, r.status, r.kind, r.top, r.second, r.chunks, r.at_floor,
                        r.reason, r.stage, r.passed_by, r.joined, r.request_id])


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Read-only: join eval results to the app log and show retrieval-gate scores")
    ap.add_argument("results", nargs="+", help="askbpl-eval results JSON file(s), live runs")
    ap.add_argument("--log", nargs="+", required=True, help="app log file(s) written by the same run(s)")
    ap.add_argument("--floor", type=float, help=f"override the floor (default: from the results, else {DEFAULT_FLOOR})")
    ap.add_argument("--strong", type=float, help=f"override the strong threshold (default: from the results, else {DEFAULT_STRONG})")
    ap.add_argument("--summary-only", action="store_true", help="skip the per-ask table")
    ap.add_argument("--csv", metavar="PATH", help="also write the per-ask table as CSV")
    a = ap.parse_args(argv)

    try:
        runs = [json.loads(Path(p).read_text(encoding="utf-8")) for p in a.results]
        if not all(isinstance(r.get("records"), dict) for r in runs):
            raise ValueError("a results file has no 'records'")
        events = read_log_events([Path(p) for p in a.log])
    except (OSError, ValueError) as exc:
        print(f"askbpl-score-report: {exc}", file=sys.stderr)
        return 2
    if not any(r["records"] for r in runs):
        print("askbpl-score-report: the results contain no recorded asks", file=sys.stderr)
        return 2

    meta = runs[0].get("meta") or {}
    floor = a.floor if a.floor is not None else float(meta.get("grounding_floor") or DEFAULT_FLOOR)
    strong = a.strong if a.strong is not None else float(meta.get("grounding_strong") or DEFAULT_STRONG)
    rows = build_rows(runs, events, all_cases())
    print(render(rows, floor, strong, show_rows=not a.summary_only))
    if a.csv:
        write_csv(rows, Path(a.csv))
        print(f"\nwritten: {a.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
