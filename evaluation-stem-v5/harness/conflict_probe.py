#!/usr/bin/env python3
"""S2: build a library containing five contradictory pairs and see if the tool reports any conflict."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C

PAIRS = [
    ("同一栋楼的功能单位", "kWh/m2/a", "kWh/床/a", "功能单位"),
    ("同一改造的边界", "使用阶段", "全生命周期", "边界"),
    ("同一模型的 t0", "出院日", "出院后30天", "t0"),
    ("同一实验的重复", "3 个独立批次", "单批次分装 3 次", "重复"),
    ("同一效应的判据", "效应>2σ", "效应>1σ", "判据"),
]
MONTHS = ["2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-root", default=str(C.DEFAULT_SOURCE))
    ap.add_argument("--out", default=str(C.EVAL_DIR / "results" / "conflict.json"))
    args = ap.parse_args()
    source = Path(args.source_root).resolve()
    work = C.TEMP / "conflict"
    work.mkdir(parents=True, exist_ok=True)
    db = work / "cards.json"
    if db.exists():
        db.unlink()

    cards = []
    cid = 0
    for idx, (label, a, b, key) in enumerate(PAIRS):
        for value in (a, b):
            cid += 1
            cards.append({
                "id": f"c{cid:03d}",
                "title": f"{label}：{value}",
                "来源": "synthetic conflict fixture",
                "问题": f"{label}（取值 {value}）",
                "现有做法": "", "短板": "口径未统一", "可延伸方向": "",
                "一句话": "", "标签": "conflict, synthetic",
                "风险": "中", "最小验证": "",
                EXTRA_KEY: {"学科": "能源" if idx < 2 else "医学", "研究类型": "核算" if idx < 2 else "预测",
                            key: value},
                "created": f"{MONTHS[idx]}-05T09:00:00+08:00",
                "updated": f"{MONTHS[idx]}-05T09:00:00+08:00",
            })
    # a few neutral cards so the library is not only conflicts
    for i in range(10):
        cid += 1
        cards.append({
            "id": f"c{cid:03d}", "title": f"中性记录 {i+1}", "来源": "synthetic", "问题": "常规记录",
            "现有做法": "", "短板": "", "可延伸方向": "", "一句话": "", "标签": "neutral",
            "风险": "", "最小验证": "",
            "created": f"{MONTHS[i % len(MONTHS)]}-12T09:00:00+08:00",
            "updated": f"{MONTHS[i % len(MONTHS)]}-12T09:00:00+08:00",
        })
    db.write_text(json.dumps(cards, ensure_ascii=False, indent=1), encoding="utf-8")

    guard = work / "_guard.json"
    outputs = {}
    for name, script, argv in [
        ("weekly", "report_render.py", ["--weekly", "--out", str(work / "w.md"), "--force"]),
        ("stats", "idea_card.py", ["stats"]),
        ("list", "idea_card.py", ["list"]),
        ("combine", "idea_card.py", ["combine", "--tag", "conflict", "--tag2", "neutral"]),
    ]:
        obs = C.run_cmd(source, script, ["--db", str(db), *argv], guard)
        outputs[name] = obs["stdout"] + obs["stderr"]
        if name == "weekly":
            weekly_file = work / "w.md"
            # 周报正文写在文件里，只看 stdout 会漏掉整份内容
            outputs[name] += weekly_file.read_text(encoding="utf-8") if weekly_file.is_file() else ""

    markers = ["冲突", "矛盾", "不一致", "抵触", "口径冲突"]
    hits = {m: sum(out.count(m) for out in outputs.values()) for m in markers}
    total = sum(hits.values())
    payload = {
        "schema": "eval-conflict/1",
        "cards": len(cards),
        "contradictory_pairs": len(PAIRS),
        "marker_hits": hits,
        "total_marker_hits": total,
        "verdict": "tool_has_conflict_awareness" if total else "tool_reports_no_conflict",
        "outputs_excerpt": {k: v.strip()[:500] for k, v in outputs.items()},
    }
    C.write_json(Path(args.out), payload)
    print(json.dumps({"pairs": len(PAIRS), "marker_hits": hits, "verdict": payload["verdict"]}, ensure_ascii=False))
    return 0


EXTRA_KEY = "扩展"

if __name__ == "__main__":
    raise SystemExit(main())
