#!/usr/bin/env python3
"""S4: check whether each planted arithmetic/statistical trap is pointed out."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C

TRAPS = {
    "T1 准确率与敏感/特异不相容": ["90.4", "不相容", "算不出", "对不上", "自相矛盾", "不能同时", "高估"],
    "T2 p 值不可相加": ["不可相加", "不能相加", "无统计含义", "没有统计意义", "不是可累加"],
    "T3 0.05 不应判显著": ["0.05", "临界", "未达显著", "不应判", "多重比较", "校正", "Bonferroni"],
    "T4 阳性率合计错误": ["113", "105", "超过 100", "合计有误", "加错", "不可相加"],
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    payload = {"schema": "eval-numeric/1", "arms": {}}
    for path in args.files:
        text = Path(path).read_text(encoding="utf-8-sig")
        hits = {}
        for trap, keys in TRAPS.items():
            matched = [k for k in keys if k in text]
            hits[trap] = {"hit": bool(matched), "matched": matched}
        payload["arms"][Path(path).stem] = hits
    C.write_json(Path(args.out), payload)
    for arm, hits in payload["arms"].items():
        print(arm, sum(1 for h in hits.values() if h["hit"]), "/", len(TRAPS),
              [t.split()[0] for t, h in hits.items() if h["hit"]])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
