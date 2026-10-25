#!/usr/bin/env python3
"""Grid-search the three conflict-detection thresholds on synthetic families with ground truth."""
from __future__ import annotations
import argparse
import itertools
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C

KEYS = ["功能单位", "边界", "t0", "时间跨度", "初末状态", "重复", "判据", "单位", "验证范围", "切分", "种子", "样本量"]
CURRENT = {"theta": 0.40, "min_cards": 5, "max_signatures": 2}


def _card(i, disc, proj, tags, ext, truth=None):
    """proj 是可选的「项目」字段；truth 是构造时的真项目，两者必须分开。"""
    e = {"学科": disc}
    if proj is not None:
        e["项目"] = proj
    e.update(ext)
    real = truth if truth is not None else proj
    return {"id": f"c{i:05d}", "标签": sorted(tags), "扩": e, "_proj": f"{disc}::{real if real else 'none'}"}


def build_family(name: str):
    """每个族对应一种真实形态；多数族故意不填「项目」，让标签判据真正受力。"""
    cards = []
    i = 0
    def add(disc, proj_field, tags, ext, truth=None):
        nonlocal i
        i += 1
        cards.append(_card(i, disc, proj_field, tags, ext, truth))

    if name == "F1_dense":  # 填了项目字段：考项目闸门
        for disc in ("能源", "医学", "计算机"):
            for p_, proj in enumerate(("P1", "P2", "P3", "P4")):
                conflict = p_ in (0, 2)
                for k in range(10):
                    unit = "A" if not (conflict and k >= 5) else "B"
                    tags = {proj, "通用"} | ({"方法"} if k % 2 == 0 else set())
                    add(disc, proj, tags, {"功能单位": unit})
    elif name == "F2_sparse":  # 没填项目；只有一半卡片带项目标签
        for disc in ("生物", "机械"):
            for p_, proj in enumerate(("Q1", "Q2", "Q3", "Q4", "Q5", "Q6")):
                conflict = p_ in (1, 3, 5)
                for k in range(8):
                    unit = "A" if not (conflict and k >= 4) else "B"
                    tags = {"通用"}
                    if k % 2 == 0:
                        tags.add(proj)
                    add(disc, None, tags, {"功能单位": unit}, truth=proj)
    elif name == "F3_umbrella":  # 没填项目；主题标签正好覆盖一半项目（50%）
        for p_, proj in enumerate(("R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8")):
            conflict = p_ == 0
            for k in range(12):
                unit = "A" if not (conflict and k >= 6) else "B"
                tags = {"通用", proj}
                if p_ < 4:
                    tags.add("空调")
                add("能源", None, tags, {"功能单位": unit}, truth=proj)
    elif name == "F7_few":  # 没填项目；只有 3 个项目，项目标签占 33%
        for p_, proj in enumerate(("T1", "T2", "T3")):
            conflict = p_ in (0, 2)
            for k in range(10):
                unit = "A" if not (conflict and k >= 5) else "B"
                add("机械", None, {proj, "通用"}, {"功能单位": unit}, truth=proj)
    elif name in ("F6_noisy", "F6_ambiguous"):
        # 验证族：没填项目 + 跨项目噪声标签
        # F6_noisy 的噪声覆盖 2/4 项目（50%），与项目标签（25%）可分；
        # F6_ambiguous 的噪声覆盖 3 个项目（33%），与项目标签几乎同频，任何单一阈值都分不开
        spread = 2 if name == "F6_noisy" else 3
        for disc in ("化学", "医学", "电子信息"):
            for p_, proj in enumerate(("S1", "S2", "S3", "S4")):
                conflict = p_ < 2
                for k in range(10):
                    unit = "A" if not (conflict and k >= 5) else "B"
                    tags = {"通用", proj}
                    if p_ < spread and k % 3 == 0:
                        tags.add("噪声1")
                    add(disc, None, tags, {"功能单位": unit}, truth=proj)
    elif name == "F4_tiny":  # 测试族：每学科只有 3 张卡
        for disc in ("能源", "医学", "生物", "机械"):
            for k in range(3):
                unit = "A" if (disc != "能源" or k < 1) else "B"
                add(disc, None, {"通用", "小组"}, {"功能单位": unit}, truth=f"{disc}-唯一项目")
    elif name == "F5_cross":  # 测试族：项目名跨学科复用
        for disc in ("能源", "医学"):
            for proj in ("楼A", "楼B", "楼C"):
                for k in range(10):
                    conflict = proj == "楼A" and k >= 5
                    unit = "A" if not conflict else "B"
                    add(disc, proj, {"通用", proj}, {"功能单位": unit})
    else:
        raise SystemExit(f"unknown family {name}")
    return prepare(cards)


def prepare(cards):
    gold, pairs = set(), []
    for a, b in itertools.combinations(range(len(cards)), 2):
        ca, cb = cards[a], cards[b]
        if ca["扩"]["学科"] != cb["扩"]["学科"]:
            continue
        diff = tuple(k for k in KEYS if ca["扩"].get(k) and cb["扩"].get(k) and ca["扩"][k] != cb["扩"][k])
        shared = frozenset(ca["标签"]) & frozenset(cb["标签"])
        same_project = ca["扩"].get("项目") and cb["扩"].get("项目") and ca["扩"]["项目"] == cb["扩"]["项目"]
        pairs.append((a, b, shared, bool(same_project), diff))
        if ca["_proj"] == cb["_proj"]:
            for key in diff:
                gold.add((ca["id"], cb["id"], key))
    return {"name": cards and "", "cards": cards, "pairs": pairs, "gold": gold}


def generic_sets(fam, theta, min_cards, max_signatures):
    counts, totals, sigs = {}, {}, {}
    for c in fam["cards"]:
        d = c["扩"]["学科"]
        totals[d] = totals.get(d, 0) + 1
        sigs.setdefault(d, set()).add(tuple(c["标签"]))
        for t in c["标签"]:
            counts[(d, t)] = counts.get((d, t), 0) + 1
    generic = {}
    for (d, t), n in counts.items():
        if len(sigs.get(d, ())) <= max_signatures:
            continue
        if totals[d] >= min_cards and n / totals[d] >= theta:
            generic.setdefault(d, set()).add(t)
    return generic


def evaluate(fam, theta, min_cards, max_signatures):
    generic = generic_sets(fam, theta, min_cards, max_signatures)
    cards = fam["cards"]
    flagged = set()
    for a, b, shared, same_project, diff in fam["pairs"]:
        extra = cards[a]["扩"]
        project_a, project_b = extra.get("项目"), cards[b]["扩"].get("项目")
        if project_a and project_b:
            if project_a != project_b:
                continue
        else:
            if not (shared - generic.get(extra["学科"], set())):
                continue
        for key in diff:
            flagged.add((cards[a]["id"], cards[b]["id"], key))
    tp = len(flagged & fam["gold"]); fp = len(flagged - fam["gold"]); fn = len(fam["gold"] - flagged)
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    return {"tp": tp, "fp": fp, "fn": fn, "p": round(p, 4), "r": round(r, 4),
            "f1": round(2 * p * r / (p + r), 4) if tp else 0.0, "flagged": len(flagged)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(C.EVAL_DIR / "results" / "runs.json"))
    args = ap.parse_args()

    families = {n: build_family(n) for n in ("F1_dense", "F2_sparse", "F3_umbrella", "F7_few", "F6_noisy", "F6_ambiguous", "F4_tiny", "F5_cross")}
    train = ["F1_dense", "F2_sparse", "F3_umbrella", "F7_few"]
    runs = []

    def record(rid, phase, params, fam_name, metrics):
        runs.append({"run": rid, "phase": phase, **params, "family": fam_name, **metrics})

    # R0 baseline
    for fam in families:
        record("R0", "baseline", CURRENT, fam, evaluate(families[fam], **CURRENT))

    # R1..R81 grid on training families
    grid = list(itertools.product(
        [0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60], [3, 5, 8], [1, 2, 3]))
    scored = []
    for idx, (theta, min_cards, max_sig) in enumerate(grid, start=1):
        params = {"theta": theta, "min_cards": min_cards, "max_signatures": max_sig}
        metrics = {fam: evaluate(families[fam], **params) for fam in train}
        macro_f1 = round(sum(m["f1"] for m in metrics.values()) / len(metrics), 4)
        macro_p = round(sum(m["p"] for m in metrics.values()) / len(metrics), 4)
        scored.append({"params": params, "train_f1": macro_f1, "train_p": macro_p})
        for fam in train:
            record(f"R{idx}", "grid", params, fam, metrics[fam])

    # R82 selection on validation
    best, feasible = None, False
    best_train = max(r["train_f1"] for r in scored)
    for row in scored:
        val = evaluate(families["F6_noisy"], **row["params"])
        row["val"] = val
        record("R82", "validation", row["params"], "F6_noisy", val)
        if val["p"] >= 0.90 and not feasible:
            feasible = True
        if row["train_f1"] < best_train - 0.02:  # 训练上明显更差的配置不进入选择
            continue
        params = row["params"]
        key = (-val["f1"], -val["p"],
               abs(params["theta"] - CURRENT["theta"]), abs(params["min_cards"] - CURRENT["min_cards"]),
               abs(params["max_signatures"] - CURRENT["max_signatures"]))
        if best is None or key < best[0]:
            best = (key, row)
    chosen = best[1]["params"] if best else CURRENT
    stress = evaluate(families["F6_ambiguous"], **chosen)
    record("R82b", "stress", chosen, "F6_ambiguous", stress)

    # R83 held-out test
    test = {}
    for fam in ("F4_tiny", "F5_cross"):
        test[fam] = evaluate(families[fam], **chosen)
        record("R83", "test", chosen, fam, test[fam])

    payload = {"schema": "eval-tuning/1", "chosen": chosen, "current": CURRENT,
               "grid_size": len(grid), "runs": runs,
               "selection": {"rule": "train F1 within 0.02 of best, then max val F1, tie: precision, then closest to current params",
                             "precision_floor_met": feasible,
                             "val_precision": best[1]["val"]["p"] if best else None,
                             "val_f1": best[1]["val"]["f1"] if best else None,
                             "stress_ambiguous": stress},
               "test": test,
               "top5_train": sorted(scored, key=lambda r: -r["train_f1"])[:5]}
    C.write_json(Path(args.out), payload)

    print("baseline:", {f: evaluate(families[f], **CURRENT)["f1"] for f in families})
    print("chosen:", chosen, "val P/F1:", payload["selection"]["val_precision"], payload["selection"]["val_f1"])
    print("stress(F6_ambiguous):", stress)
    print("test:", test)
    print("top5:", [(r["params"], r["train_f1"]) for r in payload["top5_train"]])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
