#!/usr/bin/env python3
"""Rule-based structural scoring for control-arm and role texts (regex proxies only)."""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C

CONTROL_KEYWORDS = {
    "computer": ["0.4", "官方划分", "测试集", "随机种子", "算力"],
    "chemistry": ["98%", "单批次", "LOD", "回收率", "空白"],
    "biology": ["n=3", "重复", "参考基因", "校正", "调控网络"],
    "medicine": ["92%", "88%", "健康对照", "盲法", "置信区间"],
    "mechanical": ["4%", "单工况", "网格", "固支", "名义值"],
    "energy": ["35%", "使用阶段", "电网因子", "功能单位", "辅助能耗"],
    "electronics": ["9.1", "9.8", "单板", "频点", "不确定度"],
}

MARKERS = {
    "fact": r"材料显示|题面|材料中|摘要中|文中报",
    "inference": r"我的推断|推断|推测",
    "advice": r"建议|推荐",
    "unverified": r"尚未核实|未核实|未检索|未验证",
}

ITEMS = {
    "S1": "事实/推断/建议分离",
    "S2": "新颖性状态显式",
    "S3": "无虚构来源",
    "S4": "输入约束保留",
    "S5": "阈值标注待设定",
    "S6": "保留不确定结论",
    "S7": "最小验证≥3要素",
    "S8": "不按占比评贡献",
}

ERRORS = {"X1": "虚构来源", "X2": "未核实新颖性断言", "X3": "丢条件/单位", "X4": "因果越界", "X5": "假设写成事实"}


def sentences(text: str) -> list[str]:
    return [s for s in re.split(r"[。\n；;]+", text) if s.strip()]


def grade(text: str, slug: str) -> dict:
    text_l = text.lower()
    categories = [name for name, pattern in MARKERS.items() if re.search(pattern, text)]
    keywords = CONTROL_KEYWORDS.get(slug, [])
    hit = [k for k in keywords if k in text]
    ratio = len(hit) / len(keywords) if keywords else 1.0

    has_novelty_state = bool(re.search(r"未核实|未检索|部分重叠|不确定是否有人|尚未检索", text))
    claims_first = bool(re.search(r"首次提出|尚无研究|无人做过|首个(提出|实现)|首次报道", text))

    threshold_like = re.search(r"\d+(\.\d+)?\s*(%|分|倍|天|周|个月|ms|dB|bit)", text)
    threshold_guarded = bool(re.search(r"待设定|建议.{0,8}选择|未定|由.{0,8}决定|需.{0,6}校准", text))

    facts = {
        "S1": len(categories) >= 2,
        "S2": has_novelty_state and not claims_first,
        "S3": not re.search(r"doi:|arxiv|et al\.|等\s*\(20\d\d\)|据.{0,8}研究(表明|发现)", text_l),
        "S4": ratio >= 0.8,
        "S5": (not threshold_like) or threshold_guarded,
        "S6": bool(re.search(r"无法判断|信息不足|不确定|无法确认|不能判断", text)),
        "S7": sum(1 for w in ["数据", "对照", "基线", "指标", "判据"] if w in text) >= 3,
        "S8": not re.search(r"占比|代码行数|模块数量", text),
    }

    errors = {
        "X1": not facts["S3"],
        "X2": any(("首次" in s or "尚无" in s or "无人" in s) and "未核实" not in s for s in sentences(text)),
        "X3": not facts["S4"],
        "X4": any(re.search(r"(证明|证实)", s) and re.search(r"因果|机制|有效|导致", s)
                  and not re.search(r"未|待|无法|不能", s) for s in sentences(text)),
        "X5": bool(re.search(r"显然|众所周知|毫无疑问|事实是", text)),
    }
    return {
        "chars": len(text),
        "items": facts,
        "item_hits": sum(1 for v in facts.values() if v),
        "errors": errors,
        "error_hits": sum(1 for v in errors.values() if v),
        "keyword_ratio": round(ratio, 2),
        "keywords_hit": hit,
        "marker_categories": categories,
    }


def arm_of(name: str) -> str:
    return name.split("-", 1)[0]


def main() -> int:
    ap = argparse.ArgumentParser(description="Score control/role texts with structural proxies")
    ap.add_argument("--dir", required=True)
    ap.add_argument("--pattern", default="*.md")
    ap.add_argument("--out", required=True)
    ap.add_argument("--min-chars", type=int, default=80)
    args = ap.parse_args()

    root = Path(args.dir)
    rows = []
    for path in sorted(root.glob(args.pattern)):
        if path.name.startswith("_"):
            continue
        text = path.read_text(encoding="utf-8-sig").strip()
        slug = path.stem.split("-", 1)[1] if "-" in path.stem else "unknown"
        scored = grade(text, slug)
        scored.update({"file": path.name, "arm": arm_of(path.name), "slug": slug,
                       "below_min_chars": len(text) < args.min_chars})
        rows.append(scored)

    summary = {}
    for arm in sorted({r["arm"] for r in rows}):
        subset = [r for r in rows if r["arm"] == arm]
        summary[arm] = {
            "files": len(subset),
            "per_item": {k: f"{sum(1 for r in subset if r['items'][k])}/{len(subset)}" for k in ITEMS},
            "per_error": {k: f"{sum(1 for r in subset if r['errors'][k])}/{len(subset)}" for k in ERRORS},
            "mean_chars": round(sum(r["chars"] for r in subset) / len(subset), 1) if subset else 0,
        }

    payload = {
        "schema": "eval-text-grades/1",
        "scorer": "regex proxies; scorer and generator are the same model",
        "items": ITEMS,
        "errors": ERRORS,
        "summary": summary,
        "rows": rows,
    }
    C.write_json(Path(args.out), payload)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
