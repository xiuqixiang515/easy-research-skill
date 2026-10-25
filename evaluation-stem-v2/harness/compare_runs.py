#!/usr/bin/env python3
"""Compare repeated runs and cross-version probe matrices."""
from __future__ import annotations
import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C


def compare_runs(paths: list[Path]) -> dict:
    runs = [C.read_json(p) for p in paths]
    labels = [r.get("run_label") or Path(p).stem for r, p in zip(runs, paths)]
    case_maps = []
    for run in runs:
        case_maps.append({c["case"]: c for c in run.get("cases", [])})
    all_cases = sorted(set().union(*[set(m) for m in case_maps]))
    rows = []
    for case in all_cases:
        entries = [m.get(case) for m in case_maps]
        present = [e for e in entries if e]
        passed = [bool(e.get("passed")) for e in present]
        hashes = [e.get("stdout_sha256") for e in present]
        durations = [e.get("seconds") for e in present if isinstance(e.get("seconds"), (int, float)) and e["seconds"] > 0]
        if all(passed):
            status = "stable_pass"
        elif not any(passed):
            status = "consistently_failed"
        else:
            status = "flaky"
        rows.append({
            "case": case,
            "status": status,
            "passed_by_run": dict(zip(labels, passed)),
            "output_hash_identical": len({h for h in hashes if h is not None}) == 1,
            "median_seconds": round(statistics.median(durations), 4) if durations else None,
            "spread_ratio": round((max(durations) - min(durations)) / statistics.median(durations), 3)
            if len(durations) > 1 and statistics.median(durations) else None,
        })
    summary = {
        "runs": labels,
        "cases": len(rows),
        "stable_pass": sum(1 for r in rows if r["status"] == "stable_pass"),
        "flaky": [r["case"] for r in rows if r["status"] == "flaky"],
        "consistently_failed": [r["case"] for r in rows if r["status"] == "consistently_failed"],
        "output_hash_mismatch": [r["case"] for r in rows if not r["output_hash_identical"]],
    }
    return {"schema": "eval-compare/1", "mode": "runs", "summary": summary, "rows": rows}


def compare_matrices(old_path: Path, new_path: Path) -> dict:
    old = C.read_json(old_path)
    new = C.read_json(new_path)
    old_map = {p["id"]: p for p in old.get("probes", [])}
    new_map = {p["id"]: p for p in new.get("probes", [])}
    rows = []
    for pid in sorted(set(old_map) | set(new_map)):
        o = old_map.get(pid, {})
        n = new_map.get(pid, {})
        o_pass, n_pass = o.get("passed"), n.get("passed")
        if o_pass is False and n_pass is True:
            transition = "red_to_green"
        elif o_pass is True and n_pass is False:
            transition = "green_to_red"
        elif n_pass is True:
            transition = "green"
        else:
            transition = "red"
        rows.append({
            "id": pid,
            "title": n.get("title") or o.get("title"),
            "v_old": bool(o_pass),
            "v_new": bool(n_pass),
            "transition": transition,
            "note": n.get("note") or o.get("note"),
            "old_expected_note": o.get("note"),
        })
    summary = {
        "old_version": old.get("version_label"),
        "new_version": new.get("version_label"),
        "old_rev": (old.get("git_rev") or "")[:7],
        "new_rev": (new.get("git_rev") or "")[:7],
        "red_to_green": [r["id"] for r in rows if r["transition"] == "red_to_green"],
        "green_to_red": [r["id"] for r in rows if r["transition"] == "green_to_red"],
        "both_green": [r["id"] for r in rows if r["transition"] == "green"],
        "both_red": [r["id"] for r in rows if r["transition"] == "red"],
    }
    return {"schema": "eval-compare/1", "mode": "matrix", "summary": summary, "rows": rows}


def main() -> int:
    ap = argparse.ArgumentParser(description="Compare eval runs or probe matrices")
    ap.add_argument("--runs", nargs="+", default=[])
    ap.add_argument("--matrix", nargs=2, default=[])
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    if args.matrix:
        payload = compare_matrices(Path(args.matrix[0]), Path(args.matrix[1]))
    elif len(args.runs) >= 2:
        payload = compare_runs([Path(p) for p in args.runs])
    else:
        raise SystemExit("需要 --runs a b c 或 --matrix old new")
    C.write_json(Path(args.out), payload)
    print(json.dumps(payload["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
