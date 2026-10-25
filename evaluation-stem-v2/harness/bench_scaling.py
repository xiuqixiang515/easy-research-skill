#!/usr/bin/env python3
"""Timing benchmark: interpreter baseline, single commands, and card-count scaling."""
from __future__ import annotations
import argparse
import csv
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C

SINGLE = [
    ("template", "idea_card.py", ["template"]),
    ("list", "idea_card.py", ["list"]),
    ("search", "idea_card.py", ["search", "synthetic"]),
    ("show", "idea_card.py", ["show", "c0001"]),
    ("combine", "idea_card.py", ["combine", "--tag", "a", "--tag2", "b"]),
    ("stats", "idea_card.py", ["stats"]),
    ("weekly", "report_render.py", ["--weekly"]),
]


def build_db(path: Path, n: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cards = [{"id": f"c{i+1:04d}", "title": f"卡片{i}", "来源": "synthetic", "问题": "synthetic",
              "现有做法": "", "短板": f"gap{i % 37}", "可延伸方向": "later", "一句话": "",
              "标签": "a, b" if i % 2 else "a, c", "风险": "中", "最小验证": "",
              "created": "2026-10-01T00:00:00+08:00", "updated": "2026-10-20T00:00:00+08:00"}
             for i in range(n)]
    path.write_text(json.dumps(cards, ensure_ascii=False), encoding="utf-8")


def timed(argv: list, cwd: Path, timeout: int = 60) -> float | None:
    started = time.perf_counter()
    try:
        subprocess.run(argv, cwd=str(cwd), capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None
    return round(time.perf_counter() - started, 4)


def main() -> int:
    ap = argparse.ArgumentParser(description="Timing benchmark (wall clock, same machine)")
    ap.add_argument("--source-root", default=str(C.DEFAULT_SOURCE))
    ap.add_argument("--out", required=True)
    ap.add_argument("--label", default="current")
    ap.add_argument("--work-label", default="bench")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    source = Path(args.source_root).resolve()
    work = C.TEMP / args.work_label
    if work.exists():
        if not args.force:
            raise SystemExit(f"refusing to reuse existing bench workdir: {work}")
        import shutil
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)

    rows = []
    guard = work / "_guard.json"
    env = C.child_env(guard)

    base = []
    for _ in range(5):
        started = time.perf_counter()
        subprocess.run([sys.executable, "-X", "utf8", "-c", "import sys"], cwd=str(source),
                       env=env, capture_output=True, timeout=60)
        base.append(round(time.perf_counter() - started, 4))
    rows.append({"kind": "interpreter", "label": args.label, "case": "startup", "n": "",
                 "seconds": round(statistics.median(base), 4)})

    db500 = work / "cards-500.json"
    build_db(db500, 500)
    for name, script, argv in SINGLE:
        times = []
        for _ in range(3):
            full = [sys.executable, "-X", "utf8", str(source / "scripts" / script),
                    "--db", str(db500), *argv]
            if argv and argv[0] == "--weekly":
                full += ["--out", str(work / "weekly-single.md"), "--force"]
            value = timed(full, source)
            times.append(value)
        ok = [t for t in times if t is not None]
        rows.append({"kind": "single", "label": args.label, "case": name, "n": 500,
                     "seconds": round(statistics.median(ok), 4) if ok else "timeout",
                     "min": min(ok) if ok else "", "max": max(ok) if ok else "",
                     "samples": len(ok)})

    for n in (100, 500, 1000, 2000):
        db = work / f"cards-{n}.json"
        if not db.exists():
            build_db(db, n)
        for sample in range(1, 4):
            out = work / f"weekly-{n}-{sample}.md"
            full = [sys.executable, "-X", "utf8", str(source / "scripts" / "report_render.py"),
                    "--db", str(db), "--weekly", "--out", str(out), "--force"]
            seconds = timed(full, source, timeout=30)
            rows.append({"kind": "scale", "label": args.label, "case": f"weekly-{n}-{sample}",
                         "n": n, "seconds": seconds if seconds is not None else "timeout"})

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["kind", "label", "case", "n", "seconds", "min", "max", "samples"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    print(f"rows={len(rows)} out={out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
