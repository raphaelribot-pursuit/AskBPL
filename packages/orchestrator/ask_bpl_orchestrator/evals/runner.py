"""askbpl-eval: run the evaluation set against the real pipeline (default) or re-score a recorded run.

  askbpl-eval                      client 30 + team regression/safety cases, live (uses your real API keys)
  askbpl-eval --set client         only the client's 30 questions
  askbpl-eval --set glossary       the glossary probes (patch 0016); not part of --set all
  askbpl-eval --set robustness     the GRD-12 robustness probes (patch 0017); not part of --set all
  askbpl-eval --only BPL-AL-03 --repeat 5
  askbpl-eval --role staff         ask every selected question as that role lens (patch 0025); recorded in the run
  askbpl-eval --compare general.json staff.json manager.json
                                   line the recorded runs up side by side against the first (offline, free)
  askbpl-eval --replay eval_data/results/<run>.json    re-score a recorded run offline: free, deterministic,
                                                       cannot detect model drift (nothing is re-asked)

Each question is asked on its own (no conversation history), exactly as worded in the fixture.
Exit status is 1 if any case FAILS or ERRORS, so it can gate a release; REVIEW and BLOCKED do not.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import logging
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ask_bpl_orchestrator.evals.cases import (
    CLIENT_CSV, DATA_DIR, GLOSSARY_CSV, REGRESSION_CSV, ROBUSTNESS_CSV, Case, file_sha256, load_cases, questions_sha256,
)
from ask_bpl_orchestrator.evals.compare import CompareError, compare_runs, load_run, print_compare, write_compare_csv
from ask_bpl_orchestrator.evals.scoring import aggregate, summarize

HUMAN_COLUMNS = ["Accuracy_1to5", "Grounding_1to5", "Completeness_1to5", "Clarity_1to5",
                 "Boundary_handling_1to5", "evaluator_rationale", "evidence_reference"]


def _git(*args: str) -> Optional[str]:
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True, timeout=10,
                              cwd=Path(__file__).resolve().parent).stdout.strip() or None
    except Exception:  # noqa: BLE001
        return None


def _role_meta(role: Optional[str]) -> Dict[str, Any]:
    """Which lens a run used. `system_prompt_sha256` covers only the base template, so the lens text is hashed apart."""
    from ask_bpl_orchestrator.services.roles import get_roles, render_role_block

    roles = get_roles()
    # With no --role nothing is sent and the server applies its default role (Staff since patch 0028). The run records
    # the role that was actually applied, and whether it was asked for, so a no-flag run is never mistaken for General.
    resolved = roles.resolve(role) if role else roles.default
    block = render_role_block(resolved)
    return {"role": resolved.key, "role_sent": bool(role), "default_role": roles.default_key,
            "role_lens_label": resolved.label,
            "role_lens_sha256": hashlib.sha256(block.encode()).hexdigest()[:16] if block else None}


def run_metadata(cases: List[Case], *, mode: str, env_label: str, repeat: int, role: Optional[str] = None) -> Dict[str, Any]:
    from ask_bpl_orchestrator.config import get_settings
    from ask_bpl_orchestrator.services.generation import SYSTEM_PROMPT

    s = get_settings()
    return {
        "mode": mode, "run_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "env_label": env_label, "commit": _git("rev-parse", "--short", "HEAD"),
        "working_tree_dirty": bool(_git("status", "--porcelain", "--untracked-files=no")),  # tracked changes only
        "untracked_files_present": bool(_git("ls-files", "--others", "--exclude-standard")),
        "python": platform.python_version(), "repeat": repeat,
        "anthropic_model": s.anthropic_model, "embedding_model": s.openai_embedding_model,
        "allow_test_index": s.allow_test_index, "top_k": s.pinecone_top_k,
        "grounding_floor": s.grounding_threshold, "grounding_strong": s.grounding_strong_threshold,
        "system_prompt_sha256": hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest()[:16],
        **_role_meta(role),
        "client_questions_file_sha256": file_sha256(CLIENT_CSV)[:16],
        "client_question_wording_sha256": questions_sha256([c for c in cases if c.is_client])[:16]
        if any(c.is_client for c in cases) else None,
        "note": "Automated checks only. Sources marked provisional are not BPL-confirmed. No BPL-approved answer key exists.",
    }


# ------------------------------------------------------------------------------------------ live
async def _ask_all(cases: List[Case], repeat: int, delay: float, role: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
    """Ask every question through the real app inside ONE event loop.

    The app keeps long-lived database/OpenAI connections that are bound to the loop that created them, so every
    request (and the later database lookups) must share a single loop. A per-request loop, as a synchronous test
    client uses, breaks with "attached to a different loop" / "Event loop is closed".
    """
    import httpx

    from ask_bpl_orchestrator.main import app

    email = os.environ.get("PILOT_DEMO_EMAIL", "pilot-demo@bklynlibrary.org")
    code = os.environ.get("PILOT_DEMO_ACCESS_CODE", "DEMO2026")
    transport = httpx.ASGITransport(app=app)
    records: Dict[str, List[Dict[str, Any]]] = {}
    async with httpx.AsyncClient(transport=transport, base_url="http://askbpl-eval", timeout=180.0) as client:
        signed = await client.post("/auth/sign-in", json={"email": email, "access_code": code, "attribution_mode": "anonymous"})
        if signed.status_code != 200:
            raise SystemExit(f"sign-in failed ({signed.status_code}). Run askbpl-seed and check PILOT_DEMO_ACCESS_CODE in .env")
        headers = {"Authorization": f"Bearer {signed.json()['token']}"}
        for case in cases:
            records[case.test_id] = []
            for _ in range(repeat):
                t0 = time.perf_counter()
                try:
                    body: Dict[str, Any] = {"question": case.question}
                    if role:
                        body["user_role"] = role  # only the framing lens; the question text is untouched
                    resp = await client.post("/v1/ask", headers=headers, json=body)
                    payload = resp.json()
                    status = resp.status_code
                except Exception as exc:  # noqa: BLE001
                    payload, status = {"type": "error_client", "message": f"{type(exc).__name__}: {str(exc)[:200]}"}, 0
                rec: Dict[str, Any] = {"http_status": status, "payload": payload, "latency_s": round(time.perf_counter() - t0, 2)}
                if role:
                    rec["role_requested"] = role
                records[case.test_id].append(rec)
                await asyncio.sleep(delay)
            print(f"  asked {case.test_id}", flush=True)
        await _collect_states(cases, records)  # same loop as the asks
    return records


async def _collect_states(cases: List[Case], records: Dict[str, List[Dict[str, Any]]]) -> None:
    """Attach, from the database, the eligibility of every cited document and of each case's own policy."""
    import uuid

    from sqlalchemy import select

    from ask_bpl_orchestrator.config import get_settings
    from ask_bpl_orchestrator.db.models import Document
    from ask_bpl_orchestrator.db.session import async_session_factory
    from ask_bpl_orchestrator.services.eligibility import is_retrievable

    cfg = get_settings()
    async with async_session_factory() as db:
        def state(doc: Optional[Document]) -> Dict[str, Any]:
            if doc is None:
                return {"found": False, "retrievable": False, "eligibility": None}
            return {"found": True, "retrievable": is_retrievable(doc, cfg), "eligibility": doc.eligibility.value,
                    "test_index_member": doc.test_index_member, "source_id": doc.source_id, "title": doc.title}

        by_source = {}
        for sid in {c.source_id for c in cases if c.source_id}:
            doc = (await db.execute(select(Document).where(Document.source_id == sid))).scalars().first()
            by_source[sid] = state(doc)
        by_case = {c.test_id: c for c in cases}
        for tid, recs in records.items():
            for rec in recs:
                rec["group_state"] = by_source.get(by_case[tid].source_id) if by_case[tid].source_id else None
                rec["citation_states"] = []
                for cite in (rec["payload"].get("citations") or []):
                    try:
                        doc = await db.get(Document, uuid.UUID(str(cite.get("document_id"))))
                    except ValueError:
                        doc = None
                    st = state(doc)
                    st.update({"chunk_id": cite.get("chunk_id"), "document_id": cite.get("document_id")})
                    rec["citation_states"].append(st)


async def _run_live(cases: List[Case], repeat: int, delay: float, role: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
    from ask_bpl_orchestrator.db.session import engine

    try:
        return await _ask_all(cases, repeat, delay, role)
    finally:
        await engine.dispose()  # close pooled connections inside the loop that owns them


def _redirect_app_logs(out_dir: Path) -> Path:
    """Send the app's own logging (including tracebacks) to a file so the console shows only the report."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"eval_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_app.log"
    logging.basicConfig(filename=path, level=logging.INFO, force=True,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return path


# ----------------------------------------------------------------------------------------- output
def _write(out_dir: Path, meta: Dict[str, Any], results: List[Dict[str, Any]], records, summary) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    role_part = (f"_{meta['role']}" if meta.get("role_sent") else f"_default-{meta['role']}") if meta.get("role") else ""
    base = out_dir / f"eval_{stamp}_{meta.get('commit') or 'nocommit'}_{meta['mode']}{role_part}"
    base.with_suffix(".json").write_text(
        json.dumps({"meta": meta, "summary": summary, "results": results, "records": records}, indent=2, default=str),
        encoding="utf-8")
    with open(base.with_suffix(".csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["test_id", "group", "cls", "question", "status", "provisional", "outcomes", "pass_runs", "runs",
                    "failed_checks", "warnings", "response_text", "cited_documents", "reference_status"] + HUMAN_COLUMNS)
        for r in results:
            recs = records[r["test_id"]]
            last = recs[-1]
            p = last["payload"]
            cited = sorted({c.get("title") or "?" for c in (last.get("citation_states") or [])})
            w.writerow([r["test_id"], r["group"], r["cls"], r["question"], r["status"], r["provisional"],
                        "/".join(r["outcomes"]), r["pass_runs"], r["runs"], ";".join(r["failed_checks"]),
                        " | ".join(r["warnings"]), (p.get("answer") or p.get("refusal_explanation") or p.get("message") or ""),
                        "; ".join(cited), r["reference_status"]] + [""] * len(HUMAN_COLUMNS))
    return base


def _print_report(meta, results, summary, path: Path, app_log: Optional[Path] = None) -> None:
    role_note = ""
    if meta.get("role"):
        role_note = f", role {meta['role']}" if meta.get("role_sent") else f", role {meta['role']} (server default; no --role given)"
    print(f"\n== RESULTS ({meta['mode']}{role_note}, commit {meta['commit']}{'+dirty' if meta['working_tree_dirty'] else ''})")
    for r in results:
        flag = " (provisional)" if r["provisional"] and r["status"] == "PASS" else ""
        extra = f"  failed: {','.join(r['failed_checks'])}" if r["failed_checks"] and r["status"] == "FAIL" else ""
        print(f"{r['status']:<8} {r['test_id']:<14} {'/'.join(sorted(set(r['outcomes']))):<12} "
              f"{r['pass_runs']}/{r['runs']}{flag}{extra}")
        for w in r["warnings"]:
            print(f"           ! {w}")
    print("\n== SUMMARY")
    for k, v in summary.items():
        print(f"{k}: {v}")
    if app_log is not None:
        print(f"\napp log (server-side errors and tracebacks): {app_log}")
    print(f"\nwritten: {path.with_suffix('.json')}\n         {path.with_suffix('.csv')}  (human score columns left blank)")


def select_cases(which: str, only: Optional[List[str]]) -> List[Case]:
    cases: List[Case] = []
    if which in {"client", "all"}:
        cases += load_cases(CLIENT_CSV)
    if which in {"regression", "all"}:
        cases += load_cases(REGRESSION_CSV)
    if which == "glossary" or (which == "all" and only):  # --only may name a glossary probe; a plain "all" never does
        cases += load_cases(GLOSSARY_CSV)
    if which == "robustness" or (which == "all" and only):  # same rule as the glossary probes
        cases += load_cases(ROBUSTNESS_CSV)
    if only:
        wanted = set(only)
        cases = [c for c in cases if c.test_id in wanted]
        unknown = wanted - {c.test_id for c in cases}
        if unknown:
            raise SystemExit(f"unknown test id(s): {sorted(unknown)}")
    return cases


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Ask BPL evaluation runner")
    ap.add_argument("--set", choices=["client", "regression", "glossary", "robustness", "all"], default="all")
    ap.add_argument("--only", nargs="+", metavar="TEST_ID")
    ap.add_argument("--repeat", type=int, default=1, help="ask each question N times (model output varies)")
    ap.add_argument("--delay", type=float, default=0.5, help="seconds between questions")
    ap.add_argument("--out-dir", default=str(DATA_DIR / "results"))
    ap.add_argument("--env-label", default=os.environ.get("EVAL_ENV_LABEL", "local"))
    ap.add_argument("--replay", metavar="RESULTS_JSON", help="re-score a recorded run; asks nothing")
    ap.add_argument("--list", action="store_true", help="list the selected cases and exit")
    from ask_bpl_orchestrator.services.roles import get_roles

    ap.add_argument("--role", choices=[x.key for x in get_roles().roles], default=None,
                    help="ask every question as this role lens (sends user_role); omitted = send none, i.e. General")
    ap.add_argument("--compare", nargs="+", metavar="RESULTS_JSON",
                    help="compare recorded runs, first file = baseline; asks nothing")
    a = ap.parse_args(argv)

    if a.compare:
        if a.replay or a.role:
            raise SystemExit("--compare reads recorded files only; do not combine it with --replay or --role")
        try:
            result = compare_runs([load_run(Path(p)) for p in a.compare])
        except CompareError as exc:
            raise SystemExit(f"cannot compare: {exc}") from exc
        out = write_compare_csv(result, Path(a.out_dir))
        print_compare(result, out)
        return 1 if result["hard"] or result["echo_failures"] else 0
    if a.replay and a.role:
        raise SystemExit("--role applies to a live run; a replay uses the role recorded in the file")

    app_log: Optional[Path] = None
    cases = select_cases(a.set, a.only)
    if a.list:
        for c in cases:
            print(f"{c.test_id:<14} {c.cls:<4} expect={c.expect:<10} {c.question}")
        return 0

    if a.replay:
        recorded = json.loads(Path(a.replay).read_text(encoding="utf-8"))
        records = {tid: recs for tid, recs in recorded["records"].items() if tid in {c.test_id for c in cases}}
        cases = [c for c in cases if c.test_id in records]
        mode, repeat = "replay", recorded["meta"].get("repeat", 1)
    else:
        app_log = _redirect_app_logs(Path(a.out_dir))
        print(f"asking {len(cases)} question(s) x{a.repeat} against the real pipeline...", flush=True)
        records = asyncio.run(_run_live(cases, a.repeat, a.delay, a.role))
        mode, repeat = "live", a.repeat

    results = [aggregate(c, records[c.test_id]) for c in cases]
    summary = summarize(results, records)
    meta = run_metadata(cases, mode=mode, env_label=a.env_label, repeat=repeat, role=None if a.replay else a.role)
    if a.replay:  # keep what the recorded run used; the roles file may have changed since
        meta.update({k: recorded["meta"].get(k) for k in ("role", "role_sent", "default_role", "role_lens_label", "role_lens_sha256")})
    path = _write(Path(a.out_dir), meta, results, records, summary)
    _print_report(meta, results, summary, path, app_log)
    return 1 if any(r["status"] in {"FAIL", "ERROR"} for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
