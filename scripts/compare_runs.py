"""Compare two recorded askbpl-eval runs question by question (read-only; asks nothing).

Lists every question whose status, per-repeat outcomes or cited documents changed between a baseline run and a new run.
`askbpl-eval --compare` compares role lenses and refuses two runs with the same role; use this for before/after.
Usage (from packages/orchestrator):
    python ../../scripts/compare_runs.py <baseline.json> <new.json>
See docs/BASELINE_2026-10-31.md for the current baseline files.
"""
import json, sys, collections
def load(p):
    d = json.load(open(p))
    res = {r["test_id"]: r for r in d["results"]}
    cites = {tid: sorted({c.get("document_title") for rec in recs for c in ((rec.get("payload") or {}).get("citations") or [])} - {None})
             for tid, recs in d["records"].items()}
    return d, res, cites
_, B, BC = load(sys.argv[1]); _, A, AC = load(sys.argv[2])
ids = list(dict.fromkeys(list(B) + list(A)))
moved, same = [], 0
for t in ids:
    b, a = B.get(t), A.get(t)
    bs = f"{b['status']} {b['pass_runs']}/{len(b['outcomes'])} {'/'.join(sorted(set(b['outcomes'])))}" if b else "(not in run)"
    as_ = f"{a['status']} {a['pass_runs']}/{len(a['outcomes'])} {'/'.join(sorted(set(a['outcomes'])))}" if a else "(not in run)"
    chg_status = (b or {}).get("status") != (a or {}).get("status") or (b or {}).get("outcomes") != (a or {}).get("outcomes")
    chg_cite = BC.get(t, []) != AC.get(t, [])
    if b and a and not chg_status and not chg_cite: same += 1; continue
    exp_b = b["expect"] if b else "-"; exp_a = a["expect"] if a else "-"
    moved.append((t, bs, as_, exp_b, exp_a, BC.get(t, []), AC.get(t, [])))
print(f"questions: {len(ids)}   unchanged (status, outcomes and cited documents identical): {same}   changed or new: {len(moved)}\n")
for t, bs, as_, eb, ea, bc, ac in moved:
    print(f"{t:12} {bs:32} -> {as_:32}" + (f"  [expect {eb} -> {ea}]" if eb != ea else ""))
    if bc != ac: print(f"{'':12} cites {bc or '-'} -> {ac or '-'}")
