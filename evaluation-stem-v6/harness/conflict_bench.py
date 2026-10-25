#!/usr/bin/env python3
"""Conflict-detection precision bench: synthetic library with ground truth, three rule variants."""
from __future__ import annotations
import argparse
import itertools
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C

EXTRA = "扩展"
CARDS_PER_PROJECT = 10
CONFLICT_KEYS = ["功能单位", "边界", "t0", "时间跨度", "重复", "判据", "单位", "切分", "种子", "验证范围", "SOC"]

# 学科, 项目名, 专属标签, 通用标签, 基础口径, 冲突键, 冲突后取值
PROJECTS = [
    ("能源", "楼A空调", "楼A", "节能", {"功能单位": "kWh/m2/a", "边界": "使用阶段"}, "功能单位", "kWh/m2/月"),
    ("能源", "楼B空调", "楼B", "节能", {"功能单位": "kWh/床/a", "边界": "使用阶段"}, None, None),
    ("能源", "厂区照明", "厂区", "节电", {"功能单位": "kWh/m2/a", "边界": "使用阶段"}, "边界", "全生命周期"),
    ("能源", "储能调度", "储能", "节电", {"功能单位": "kWh/a", "边界": "使用阶段", "SOC": "初末一致"}, None, None),
    ("医学", "再入院队列", "队列A", "预测", {"t0": "出院日", "验证范围": "时间外"}, "t0", "出院后30天"),
    ("医学", "ICU转出", "队列B", "预测", {"t0": "转出日", "验证范围": "内部"}, None, None),
    ("医学", "急诊分诊", "分诊", "预测", {"t0": "就诊", "验证范围": "内部"}, "验证范围", "外部"),
    ("医学", "慢病随访", "随访", "预测", {"t0": "入组", "验证范围": "外部"}, None, None),
    ("计算机", "日志异常", "日志", "复现", {"切分": "按设备", "种子": "3"}, "种子", "1"),
    ("计算机", "代码补全", "补全", "复现", {"切分": "按仓库", "种子": "5"}, None, None),
    ("计算机", "长尾评测", "长尾", "基准", {"切分": "按用户", "种子": "3"}, "切分", "按样本"),
    ("计算机", "检索复现", "检索", "基准", {"切分": "按查询", "种子": "3"}, None, None),
]


def build(seed_project: bool) -> list[dict]:
    cards = []
    n = 0
    for discipline, project, own_tag, common_tag, base, ckey, cnew in PROJECTS:
        for i in range(CARDS_PER_PROJECT):
            n += 1
            extra = {"学科": discipline, **base}
            if ckey and i >= CARDS_PER_PROJECT // 2:
                extra[ckey] = cnew
            if seed_project:
                extra["项目"] = project
            tags = [own_tag, common_tag] + (["方法"] if i % 2 == 0 else [])
            if project in ("楼A空调", "楼B空调"):
                tags.append("空调")
            cards.append({"id": f"c{n:04d}", "title": f"{project}-{i+1}", "标签": ", ".join(tags),
                          "风险": "", EXTRA: extra, "_truth_project": project})
    return cards


def truth(cards: list[dict]) -> set:
    """同一项目、同一关键字段、取值不同的卡片对。"""
    pairs = set()
    for a, b in itertools.combinations(cards, 2):
        ea, eb = a[EXTRA], b[EXTRA]
        if a["_truth_project"] != b["_truth_project"]:
            continue
        for key in CONFLICT_KEYS:
            if ea.get(key) and eb.get(key) and ea[key] != eb[key]:
                pairs.add((a["id"], b["id"], key))
    return pairs


def shared_tags(a: dict, b: dict) -> set:
    split = lambda s: {t.strip() for t in str(s or "").replace("，", ",").split(",") if t.strip()}
    return split(a.get("标签")) & split(b.get("标签"))


def flagged(cards: list[dict], rule: str, theta: float = 0.4) -> set:
    generic = {}
    totals_discipline = {}
    for c in cards:
        totals_discipline[c[EXTRA]["学科"]] = totals_discipline.get(c[EXTRA]["学科"], 0) + 1
    for c in cards:
        generic.setdefault(c[EXTRA]["学科"], {})
    if rule in ("v1", "v2", "v3"):
        counts, totals = {}, {}
        for c in cards:
            d = c[EXTRA]["学科"]
            totals[d] = totals.get(d, 0) + 1
            for t in {t.strip() for t in str(c.get("标签") or "").replace("，", ",").split(",") if t.strip()}:
                counts[(d, t)] = counts.get((d, t), 0) + 1
        for (d, t), n in counts.items():
            if totals[d] and n / totals[d] >= theta:
                generic[d][t] = True
    out = set()
    for a, b in itertools.combinations(cards, 2):
        ea, eb = a[EXTRA], b[EXTRA]
        if ea.get("学科") != eb.get("学科"):
            continue
        if rule == "v0":
            ok = bool(shared_tags(a, b))
        elif rule == "v1":
            ok = any(not generic[ea["学科"]].get(t) for t in shared_tags(a, b))
        elif rule == "v3":
            if ea.get("项目") and eb.get("项目"):
                ok = ea["项目"] == eb["项目"]
            else:
                shared = shared_tags(a, b)
                if totals_discipline.get(ea["学科"], 0) >= 5:
                    shared = {t for t in shared if not generic[ea["学科"]].get(t)}
                ok = bool(shared)
        else:  # v2: 项目字段优先，缺字段时退回 v1 判据
            if ea.get("项目") and eb.get("项目"):
                ok = ea["项目"] == eb["项目"]
            else:
                ok = any(not generic[ea["学科"]].get(t) for t in shared_tags(a, b))
        if not ok:
            continue
        for key in CONFLICT_KEYS:
            if ea.get(key) and eb.get(key) and ea[key] != eb[key]:
                out.add((a["id"], b["id"], key))
    return out


def score(flag: set, gold: set) -> dict:
    tp = len(flag & gold); fp = len(flag - gold); fn = len(gold - flag)
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": round(precision, 4), "recall": round(recall, 4),
            "f1": round(2 * precision * recall / (precision + recall), 4) if tp else 0.0}


def e2e(source: Path, cards: list[dict], gold: set, with_project: bool) -> dict:
    """Run the real weekly report and parse its conflict table."""
    import subprocess, time
    work = C.TEMP / ("e2e-project" if with_project else "e2e-noproject")
    work.mkdir(parents=True, exist_ok=True)
    db = work / "cards.json"
    payload = [{k: v for k, v in c.items() if not k.startswith("_")} for c in cards]
    db.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    out = work / "w.md"
    started = time.perf_counter()
    obs = C.run_cmd(source, "report_render.py", ["--db", str(db), "--weekly", "--out", str(out), "--force"], db)
    elapsed = round(time.perf_counter() - started, 3)
    text = out.read_text(encoding="utf-8") if out.is_file() else ""
    import re as _re
    section = _re.search(r"## 口径冲突.*?(?=\n## )", text, _re.S)
    text = section.group(0) if section else ""
    flagged_pairs = set()
    field_col, pair_col = None, None
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if "字段" in cells:
            # 表头兼容两种布局：v1.5.0 为 学科|字段|卡片|取值|共同标签；v1.6+ 多了“项目”列
            field_col = cells.index("字段")
            pair_col = next((i for i, c in enumerate(cells) if c in ("涉及卡片", "卡片")), None)
            continue
        if "---" in line or field_col is None or pair_col is None:
            continue
        if len(cells) <= max(field_col, pair_col):
            continue
        ids = [x.strip() for x in cells[pair_col].split("/")]
        if len(ids) != 2:
            continue
        flagged_pairs.add((ids[0], ids[1], cells[field_col]))
    return {"rc": obs["exit_code"], "elapsed_s": elapsed, "flagged": len(flagged_pairs),
            **score(flagged_pairs, gold)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(C.EVAL_DIR / "results" / "conflict-bench.json"))
    ap.add_argument("--source-root", default="")
    ap.add_argument("--e2e", action="store_true")
    args = ap.parse_args()

    payload = {"schema": "eval-conflict-bench/1", "cards_per_project": CARDS_PER_PROJECT,
               "projects": len(PROJECTS), "variants": {}}
    for label, with_project in (("with_project_field", True), ("without_project_field", False)):
        cards = build(with_project)
        gold = truth(cards)
        payload["variants"][label] = {"cards": len(cards), "gold_pairs": len(gold), "rules": {}}
        for rule in ("v0", "v1", "v2", "v3"):
            payload["variants"][label]["rules"][rule] = score(flagged(cards, rule), gold)
        for theta in (0.2, 0.3, 0.4, 0.5, 0.6):
            payload["variants"][label]["rules"][f"v1_theta{int(theta*100)}"] = score(flagged(cards, "v1", theta), gold)

    if args.e2e and args.source_root:
        source = Path(args.source_root).resolve()
        payload["e2e"] = {}
        for label, with_project in (("with_project_field", True), ("without_project_field", False)):
            cards = build(with_project)
            payload["e2e"][label] = e2e(source, cards, truth(cards), with_project)

    C.write_json(Path(args.out), payload)
    if "e2e" in payload:
        for label, block in payload["e2e"].items():
            print(f"e2e {label}: P={block['precision']:.3f} R={block['recall']:.3f} flagged={block['flagged']} rc={block['rc']} {block['elapsed_s']}s")
    for label, block in payload["variants"].items():
        print(label, "cards", block["cards"], "gold", block["gold_pairs"])
        for rule, s in block["rules"].items():
            print(f"  {rule:<10} P={s['precision']:.3f} R={s['recall']:.3f} F1={s['f1']:.3f} (tp={s['tp']} fp={s['fp']} fn={s['fn']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
