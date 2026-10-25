#!/usr/bin/env python3
"""S1: extract strength tokens per round so the reviewer can adjudicate drift by hand."""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C

LEVELS = {
    3: ["证明", "证实", "确立", "显著改善", "显著提升", "首次提出", "普适", "可推广", "诊断价值高"],
    2: ["支持", "表明", "说明", "一致"],
    1: ["提示", "可能", "倾向于", "相关"],
    0: ["信息不足", "无法判断", "不足以", "不能写", "不建议"],
}


def rounds(text: str) -> dict:
    parts = re.split(r"^## (R\d)\s*$", text, flags=re.M)
    out = {}
    for i in range(1, len(parts), 2):
        out[parts[i]] = parts[i + 1].strip()
    return out


def scan(block: str) -> dict:
    counts = {str(level): sum(block.count(t) for t in toks) for level, toks in LEVELS.items()}
    sentences = []
    for s in re.split(r"[。\n]", block):
        if any(t in s for t in LEVELS[3] + LEVELS[2] + LEVELS[1]):
            sentences.append(s.strip()[:120])
    return {"counts": counts, "sentences": sentences[:6]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill", required=True)
    ap.add_argument("--control", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    payload = {"schema": "eval-drift/1", "arms": {}}
    for arm, path in (("skill", args.skill), ("control", args.control)):
        text = Path(path).read_text(encoding="utf-8-sig")
        per_round = {name: scan(block) for name, block in rounds(text).items()}
        payload["arms"][arm] = per_round
    C.write_json(Path(args.out), payload)
    for arm, per_round in payload["arms"].items():
        print(arm, {r: v["counts"] for r, v in per_round.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
