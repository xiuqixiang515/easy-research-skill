#!/usr/bin/env python3
"""CLI integration suite: 7 disciplines x 11 records, repeatable rounds."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C

FIXTURES = [
    ("computer", "计算机", "F1=0.81; seed=42; split=user", "用户分组",
     {"单位": "FLOPs", "重复": "3 seeds", "仪器": "单卡 4090"}),
    ("chemistry", "化学", "c=0.10 mol/L; T=298 K; yield=82%; batch=A", "独立批次",
     {"单位": "mg/L", "重复": "3 独立批次", "仪器": "UV-Vis"}),
    ("biology", "生物", "n_bio=3; n_tech=2; ΔCt=-1.2; gene=TP53", "生物重复",
     {"重复": "3 生物学 + 2 技术", "批次": "2", "仪器": "qPCR"}),
    ("medicine", "医学", "synthetic only; AUC=0.81; 95% CI=[0.72,0.90]; t0=admission", "时间外验证",
     {"单位": "ng/mL", "仪器": "化学发光", "重复": "双孔均值"}),
    ("mechanical", "机械", "σ=120 MPa; δ=0.20 mm; mass=0.50 kg; mesh=1 mm", "网格收敛",
     {"单位": "MPa/mm", "重复": "3 根试样", "仪器": "万能试验机"}),
    ("energy", "能源", "η=0.82; E=10 kWh; boundary=system; SOC0=SOC1", "系统边界",
     {"功能单位": "1 t 产品", "边界": "使用阶段", "时间跨度": "1 年"}),
    ("electronics", "电子信息", "SNR=10 dB; fs=20 MHz; BW=5 MHz; BER=1e-3", "采样条件",
     {"单位": "bit; dBFS", "重复": "5 次上电", "仪器": "示波器 1 GHz"}),
]

HARNESS = ["common.py", "run_cli_suite.py"]


def db_field(db: Path, card_id: str, field: str):
    for card in json.loads(db.read_text(encoding="utf-8-sig")):
        if card.get("id") == card_id:
            if field.startswith("扩展."):
                return (card.get("扩展") or {}).get(field.split(".", 1)[1])
            return card.get(field)
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="CLI integration suite for easy-research-skill")
    ap.add_argument("--source-root", default=str(C.DEFAULT_SOURCE))
    ap.add_argument("--out", required=True)
    ap.add_argument("--run-label", required=True)
    ap.add_argument("--expect-branch", default="")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    source = Path(args.source_root).resolve()
    work = C.TEMP / args.run_label
    if not args.force:
        C.ensure_fresh(work)
    work.mkdir(parents=True, exist_ok=True)
    C.guard_paths(source, work)
    C.require_branch(source, args.expect_branch)

    guard_db = work / "_guard.json"
    before = C.product_hashes(source)
    started = C.now_iso()
    records = []

    for slug, name, content, keyword, extras in FIXTURES:
        db = work / f"{slug}.json"
        base = ["--db", str(db)]

        def case(label, script, argv, expected, need_db_state=False):
            db_before = C.sha_file(db) if (need_db_state and db.exists()) else None
            observed = C.run_cmd(source, script, base + argv, guard_db)
            ok, notes = C.evaluate(observed, expected, db if need_db_state else None, db_before)
            records.append(C.record(f"{slug}.{label}", observed, expected, ok, notes))
            return observed

        case("add.constraint", "idea_card.py",
             ["add", "--title", f"{name}约束", "--problem", content, "--gap", keyword,
              "--source", "synthetic fixture; not real evidence",
              "--validation", "units retained; expert review pending",
              "--tags", f"{slug},constraint"],
             {"exit_code": 0, "stdout_contains": ["[已添加]", "c001"]})

        case("add.method", "idea_card.py",
             ["add", "--title", f"{name}方法", "--problem", f"method baseline for {slug}",
              "--gap", keyword, "--tags", f"{slug},method"],
             {"exit_code": 0, "stdout_contains": ["[已添加]", "c002"]})

        extra_argv = ["add", "--title", f"{name}元数据", "--problem", f"metadata probe for {slug}",
                      "--tags", f"{slug},extras"]
        for key, value in extras.items():
            extra_argv += ["--set-extra", f"{key}={value}"]
        observed = case("add.extras", "idea_card.py", extra_argv,
                        {"exit_code": 0,
                         "stdout_contains": ["c003", "[已保留自定义字段]"],
                         "stderr_not_contains": ["Traceback"]})
        expected_extra = {"db_field.扩展." + k: v for k, v in extras.items()}
        extra_ok = observed["exit_code"] == 0 and all(
            db_field(db, "c003", "扩展." + k) == v for k, v in extras.items()
        )
        records[-1]["expected"].update(expected_extra)
        records[-1]["actual_extra"] = {k: db_field(db, "c003", "扩展." + k) for k in extras}
        if not extra_ok:
            records[-1]["passed"] = False
            records[-1]["notes"].append("extras not persisted verbatim")

        case("search", "idea_card.py", ["search", keyword],
             {"exit_code": 0, "stdout_contains": ["c001", "c002"]})

        case("show", "idea_card.py", ["show", "c001"],
             {"exit_code": 0, "stdout_contains": [content]})

        case("combine", "idea_card.py", ["combine", "--tag", "constraint", "--tag2", "method"],
             {"exit_code": 0, "stdout_contains": ["## c001 × c002"]})

        case("duplicate", "idea_card.py",
             ["add", "--title", f"{name}约束", "--problem", content, "--gap", keyword,
              "--source", "synthetic fixture; not real evidence",
              "--validation", "units retained; expert review pending",
              "--tags", f"{slug},constraint"],
             {"exit_code": 2, "stderr_contains": ["重复"], "db_unchanged": True},
             need_db_state=True)

        weekly_texts = []
        for i in (1, 2, 3):
            out = work / f"{slug}-weekly-{i}.md"
            observed = case(f"weekly{i}", "report_render.py",
                            ["--weekly", "--out", str(out), "--force"],
                            {"exit_code": 0, "stdout_contains": ["[已生成]"],
                             "db_unchanged": True}, need_db_state=True)
            weekly_texts.append(out.read_text(encoding="utf-8") if out.is_file() else "")

        normalized = [C.sha_text(C.normalize_weekly(t)) for t in weekly_texts]
        stable = len(set(normalized)) == 1
        records.append({
            "case": f"{slug}.repeat_consistency",
            "command_argv": [],
            "cwd": str(source),
            "exit_code": None,
            "stdout_excerpt": "normalized hashes: " + json.dumps(normalized),
            "stdout_sha256": C.sha_text(json.dumps(normalized)),
            "stdout_lines": 1,
            "stderr_excerpt": "",
            "seconds": 0.0,
            "expected": {"weeks_equal": True, "sections": ["按方向分布", "待补充"]},
            "passed": stable and all(("按方向分布" in t and "待补充" in t) for t in weekly_texts),
            "notes": [] if stable else ["three weekly outputs differ after normalization"],
        })

    after = C.product_hashes(source)
    failed = [r["case"] for r in records if not r["passed"]]
    payload = C.envelope(source, HARNESS, C.protocol_digest(), {
        "run_label": args.run_label,
        "started_at": started,
        "finished_at": C.now_iso(),
        "summary": {
            "checks": len(records),
            "executions": sum(1 for r in records if r["command_argv"]),
            "passed": len(records) - len(failed),
            "failed": failed,
            "source_unchanged": before == after,
            "total_seconds": round(sum(r["seconds"] for r in records), 3),
        },
        "cases": records,
    })
    C.write_json(Path(args.out), payload)
    print(json.dumps(payload["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
