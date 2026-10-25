#!/usr/bin/env python3
"""Declarative behavioural probes; one implementation drives every product version."""
from __future__ import annotations
import argparse
import concurrent.futures
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C

PROBES = [
    ("P01", "Markdown 非法风险被拒绝", "v1.1.0 红 / v1.1.1 绿"),
    ("P02", "未知字段进入扩展对象", "v1.1.0 红 / v1.1.1 绿"),
    ("P03", "未知字段续行保留", "v1.1.0 红 / v1.1.1 绿"),
    ("P04", "cli --set-extra 可读写", "v1.1.0 无此参数"),
    ("P05", "仅扩展不同的卡片不判重", "v1.1.0 红 / v1.1.1 绿"),
    ("P06", "存量非法风险不被无关更新改写", "两版均绿"),
    ("P07", "cli --risk 非法值被 argparse 拒绝", "两版均绿"),
    ("P08", "BOM 的 JSON 与 Markdown 可读", "两版均绿"),
    ("P09", "损坏 JSON 不覆盖原库", "两版均绿"),
    ("P10", "多卡 Markdown 被拒绝且不建库", "两版均绿"),
    ("P11", "16 进程并发 add 不丢卡", "v1.1.0 flaky / v1.1.1 绿"),
    ("P12", "报告不得覆盖数据库", "两版均绿"),
    ("P13", "中文与空格路径可用", "v1.1.0 未测 / v1.1.1 绿"),
    ("P14", "空库周报含卡片一览标题", "v1.1.0 红 / v1.1.1 绿"),
    ("P15", "同标签组合只输出一行", "两版均绿"),
    ("P16", "退出码契约与文档一致", "两版均绿"),
    ("P17", "模板往返无损", "两版均绿"),
    ("P18", "Unicode 大小写折叠检索", "两版均绿"),
    ("P19", "combine 排除自组合与完全重复", "两版均绿"),
    ("P20", "2000 张卡片周报 30 秒内完成", "v1.1.0 超时 / v1.1.1 绿"),
]


def make_run(source: Path, work: Path, guard: Path):
    def run(script: str, *args, timeout: int = 30):
        return C.run_cmd(source, script, list(args), guard, timeout=timeout)
    run.source = source  # handlers need the product root for direct subprocess calls
    return run


def checks_passed(checks):
    return all(c["passed"] for c in checks)


def chk(name, passed, expected=None, actual=None):
    return {"name": name, "passed": bool(passed), "expected": expected, "actual": actual}


def card(db: Path, cid: str):
    if not db.is_file():
        return None
    for item in json.loads(db.read_text(encoding="utf-8-sig")):
        if item.get("id") == cid:
            return item
    return None


def cards(db: Path):
    return json.loads(db.read_text(encoding="utf-8-sig")) if db.is_file() else []


def p01(run, d: Path):
    src = d / "bad-risk.md"
    src.write_text("## 风险校验\n- 问题: synthetic\n- 风险: 极低\n", encoding="utf-8")
    db = d / "cards.json"
    obs = run("idea_card.py", "--db", db, "add", "--file", src)
    return [
        chk("exit_code==2", obs["exit_code"] == 2, 2, obs["exit_code"]),
        chk("stderr 指出枚举", "风险必须为" in obs["stderr"], "风险必须为", obs["stderr"].strip()[:80]),
        chk("未创建数据库", not db.exists(), False, db.exists()),
    ]


def p02(run, d: Path):
    src = d / "meta.md"
    src.write_text("## 单位元数据\n- 问题: 比较两组浓度\n- 单位: mol/L\n- 风险: 中\n", encoding="utf-8")
    db = d / "cards.json"
    obs = run("idea_card.py", "--db", db, "add", "--file", src)
    shown = run("idea_card.py", "--db", db, "show", "c001")
    c = card(db, "c001") or {}
    return [
        chk("exit_code==0", obs["exit_code"] == 0, 0, obs["exit_code"]),
        chk("扩展.单位 保留", (c.get("扩展") or {}).get("单位") == "mol/L", "mol/L", (c.get("扩展") or {}).get("单位")),
        chk("show 可见单位", "单位: mol/L" in shown["stdout"], True, "单位: mol/L" in shown["stdout"]),
    ]


def p03(run, d: Path):
    src = d / "cont.md"
    src.write_text("## 续行\n- 问题: 第一行\n  第二行\n- 单位: mg/L\n", encoding="utf-8")
    db = d / "cards.json"
    obs = run("idea_card.py", "--db", db, "add", "--file", src)
    c = card(db, "c001") or {}
    return [
        chk("exit_code==0", obs["exit_code"] == 0, 0, obs["exit_code"]),
        chk("题目续行保留", c.get("问题") == "第一行\n第二行", "第一行\\n第二行", c.get("问题")),
        chk("扩展续行保留", (c.get("扩展") or {}).get("单位") == "mg/L", "mg/L", (c.get("扩展") or {}).get("单位")),
    ]


def p04(run, d: Path):
    db = d / "cards.json"
    add = run("idea_card.py", "--db", db, "add", "--title", "温度卡", "--problem", "p", "--set-extra", "温度=25C")
    upd = run("idea_card.py", "--db", db, "update", "c001", "--set-extra", "湿度=40%")
    c = card(db, "c001") or {}
    return [
        chk("add rc==0", add["exit_code"] == 0, 0, add["exit_code"]),
        chk("update rc==0", upd["exit_code"] == 0, 0, upd["exit_code"]),
        chk("两个键都在", (c.get("扩展") or {}) == {"温度": "25C", "湿度": "40%"}, "两个键", c.get("扩展")),
    ]


def p05(run, d: Path):
    db = d / "cards.json"
    a = run("idea_card.py", "--db", db, "add", "--title", "同名", "--problem", "p")
    b = run("idea_card.py", "--db", db, "add", "--title", "同名", "--problem", "p", "--set-extra", "单位=mol/L")
    return [
        chk("第一张成功", a["exit_code"] == 0, 0, a["exit_code"]),
        chk("扩展不同不判重", b["exit_code"] == 0, 0, b["exit_code"]),
        chk("共 2 张卡", len(cards(db)) == 2, 2, len(cards(db))),
    ]


def p06(run, d: Path):
    db = d / "cards.json"
    db.parent.mkdir(parents=True, exist_ok=True)
    legacy = {"title": "legacy", "来源": "", "问题": "p", "现有做法": "", "短板": "", "可延伸方向": "",
              "一句话": "", "标签": "", "风险": "极低", "最小验证": "", "created": "2026-01-01",
              "updated": "2026-01-01", "id": "c001"}
    db.write_text(json.dumps([legacy], ensure_ascii=False), encoding="utf-8")
    obs = run("idea_card.py", "--db", db, "update", "c001", "--gap", "new")
    c = card(db, "c001") or {}
    return [
        chk("update rc==0", obs["exit_code"] == 0, 0, obs["exit_code"]),
        chk("短板已更新", c.get("短板") == "new", "new", c.get("短板")),
        chk("风险未被改写", c.get("风险") == "极低", "极低", c.get("风险")),
    ]


def p07(run, d: Path):
    db = d / "cards.json"
    obs = run("idea_card.py", "--db", db, "add", "--title", "x", "--problem", "p", "--risk", "极低")
    return [
        chk("rc==2", obs["exit_code"] == 2, 2, obs["exit_code"]),
        chk("argparse 拒绝", "invalid choice" in obs["stderr"], "invalid choice", obs["stderr"].strip()[:80]),
        chk("无 Traceback", "Traceback" not in obs["stderr"], True, "Traceback" in obs["stderr"]),
    ]


def p08(run, d: Path):
    db = d / "cards.json"
    db.parent.mkdir(parents=True, exist_ok=True)
    db.write_text("\ufeff[]", encoding="utf-8")
    src = d / "bom.md"
    src.write_text("\ufeff## BOM 标题\n- 问题: 首行\n", encoding="utf-8")
    add = run("idea_card.py", "--db", db, "add", "--file", src)
    listing = run("idea_card.py", "--db", db, "list")
    return [
        chk("BOM 库可读", listing["exit_code"] == 0, 0, listing["exit_code"]),
        chk("BOM 卡可导入", add["exit_code"] == 0, 0, add["exit_code"]),
        chk("标题正确", (card(db, "c001") or {}).get("title") == "BOM 标题", "BOM 标题", (card(db, "c001") or {}).get("title")),
    ]


def p09(run, d: Path):
    db = d / "cards.json"
    db.parent.mkdir(parents=True, exist_ok=True)
    db.write_text("{broken", encoding="utf-8")
    before = C.sha_file(db)
    obs = run("idea_card.py", "--db", db, "add", "--title", "new", "--problem", "p")
    return [
        chk("rc==2", obs["exit_code"] == 2, 2, obs["exit_code"]),
        chk("提示 JSON 损坏", "JSON损坏" in obs["stderr"], "JSON损坏", obs["stderr"].strip()[:80]),
        chk("库未改变", C.sha_file(db) == before, before, C.sha_file(db)),
    ]


def p10(run, d: Path):
    src = d / "two.md"
    src.write_text("## A\n- 问题: a\n## B\n- 问题: b\n", encoding="utf-8")
    db = d / "cards.json"
    obs = run("idea_card.py", "--db", db, "add", "--file", src)
    return [
        chk("rc==2", obs["exit_code"] == 2, 2, obs["exit_code"]),
        chk("未建库", not db.exists(), False, db.exists()),
    ]


def p11(run, d: Path):
    db = d / "cards.json"
    db.parent.mkdir(parents=True, exist_ok=True)
    script = str(run.source / "scripts" / "idea_card.py")
    results = []
    for attempt in range(3):
        if db.exists():
            db.unlink()
        cmds = [[sys.executable, "-X", "utf8", script, "--db", str(db),
                 "add", "--title", f"p{attempt}-{i}", "--problem", f"p{i}"] for i in range(16)]
        env = C.child_env(d / "_guard.json")
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
            outs = list(pool.map(lambda c: subprocess.run(c, env=env, capture_output=True, text=True,
                                                          encoding="utf-8", timeout=40), cmds))
        ok = all(p.returncode == 0 for p in outs)
        stored = cards(db)
        results.append({"attempt": attempt + 1, "all_ok": ok, "cards": len(stored),
                        "unique_ids": len({c["id"] for c in stored}),
                        "errors": [p.stderr.strip()[:120] for p in outs if p.returncode != 0][:3]})
    good = [r for r in results if r["all_ok"] and r["cards"] == 16 and r["unique_ids"] == 16]
    return [
        chk("三次全部 16 卡", len(good) == 3, "3/3", f"{len(good)}/3"),
        chk("失败形态已记录", True, "记录", json.dumps([r["errors"] for r in results if r["errors"]], ensure_ascii=False)[:200]),
    ], results


def p12(run, d: Path):
    db = d / "cards.json"
    run("idea_card.py", "--db", db, "add", "--title", "x", "--problem", "p")
    before = C.sha_file(db)
    obs = run("report_render.py", "--db", db, "--from-cards", "--out", db)
    return [
        chk("rc==2", obs["exit_code"] == 2, 2, obs["exit_code"]),
        chk("拒绝写入", "拒绝" in obs["stderr"], "拒绝", obs["stderr"].strip()[:80]),
        chk("库未改变", C.sha_file(db) == before, before, C.sha_file(db)),
    ]


def p13(run, d: Path):
    db = d / "中文 目录" / "卡片 库.json"
    add = run("idea_card.py", "--db", db, "add", "--title", "中文标题", "--problem", "中文问题")
    listing = run("idea_card.py", "--db", db, "list")
    return [
        chk("add rc==0", add["exit_code"] == 0, 0, add["exit_code"]),
        chk("list 命中", "中文标题" in listing["stdout"], True, "中文标题" in listing["stdout"]),
    ]


def p14(run, d: Path):
    db = d / "empty.json"
    db.parent.mkdir(parents=True, exist_ok=True)
    db.write_text("[]", encoding="utf-8")
    out = d / "weekly.md"
    obs = run("report_render.py", "--db", db, "--weekly", "--out", out)
    text = out.read_text(encoding="utf-8") if out.is_file() else ""
    return [
        chk("rc==0", obs["exit_code"] == 0, 0, obs["exit_code"]),
        chk("含卡片一览标题", "## 卡片一览" in text, True, "## 卡片一览" in text),
    ]


def p15(run, d: Path):
    db = d / "cards.json"
    for i, tag in enumerate(["red", "red", "red", "blue", "blue", "blue"]):
        run("idea_card.py", "--db", db, "add", "--title", f"c{i}", "--problem", "p", "--tags", tag)
    out = d / "weekly.md"
    obs = run("report_render.py", "--db", db, "--weekly", "--out", out)
    text = out.read_text(encoding="utf-8") if out.is_file() else ""
    rows = text.count("| blue × red |") + text.count("| red × blue |")
    return [
        chk("rc==0", obs["exit_code"] == 0, 0, obs["exit_code"]),
        chk("组合行数==1", rows == 1, 1, rows),
    ]


def p16(run, d: Path):
    missing = d / "missing.json"
    listing = run("idea_card.py", "--db", missing, "list")
    stats = run("idea_card.py", "--db", missing, "stats")
    report = run("report_render.py", "--db", missing, "--from-cards")
    add = run("idea_card.py", "--db", d / "x.json", "add", "--file", d / "nope.md")
    return [
        chk("list 空库 rc==0", listing["exit_code"] == 0, 0, listing["exit_code"]),
        chk("stats 空库 rc==0", stats["exit_code"] == 0, 0, stats["exit_code"]),
        chk("report 缺库 rc==2", report["exit_code"] == 2, 2, report["exit_code"]),
        chk("add 缺文件 rc==2", add["exit_code"] == 2, 2, add["exit_code"]),
        chk("均无 Traceback", all("Traceback" not in x["stderr"] for x in [listing, stats, report, add]), True, "有"),
    ]


def p17(run, d: Path):
    db = d / "cards.json"
    tpl = run("idea_card.py", "--db", db, "template")
    src = d / "card.md"
    src.write_text(tpl["stdout"], encoding="utf-8")
    add = run("idea_card.py", "--db", db, "add", "--file", src)
    c = card(db, "c001") or {}
    return [
        chk("模板可打印", tpl["exit_code"] == 0 and "- 一句话:" in tpl["stdout"], True, tpl["exit_code"]),
        chk("回灌 rc==0", add["exit_code"] == 0, 0, add["exit_code"]),
        chk("标题与风险正确", c.get("title") == "标题" and c.get("风险") == "中", "标题/中", f"{c.get('title')}/{c.get('风险')}"),
    ]


def p18(run, d: Path):
    db = d / "cards.json"
    run("idea_card.py", "--db", db, "add", "--title", "多语言", "--problem", "Unicode α 与中文")
    obs = run("idea_card.py", "--db", db, "search", "UNICODE")
    return [
        chk("rc==0", obs["exit_code"] == 0, 0, obs["exit_code"]),
        chk("命中 c001", "c001" in obs["stdout"], True, "c001" in obs["stdout"]),
    ]


def p19(run, d: Path):
    db = d / "cards.json"
    base = ["add", "--title", "same", "--problem", "p", "--tags", "red"]
    run("idea_card.py", "--db", db, *base)
    run("idea_card.py", "--db", db, *(base + ["--allow-duplicate"]))
    obs = run("idea_card.py", "--db", db, "combine", "--tag", "red", "--tag2", "red")
    return [
        chk("rc==2", obs["exit_code"] == 2, 2, obs["exit_code"]),
        chk("无可用组合", "没有可组合" in obs["stderr"], "没有可组合", obs["stderr"].strip()[:80]),
    ]


def p20(run, d: Path):
    db = d / "big.json"
    db.parent.mkdir(parents=True, exist_ok=True)
    items = [{"id": f"c{i+1:04d}", "title": f"卡片{i}", "标签": "a" if i % 2 else "b",
              "短板": "synthetic", "可延伸方向": "later"} for i in range(2000)]
    db.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    out = d / "big-weekly.md"
    obs = run("report_render.py", "--db", db, "--weekly", "--out", out, timeout=30)
    return [
        chk("30 秒内完成", obs["exit_code"] == 0, 0, obs["exit_code"] if obs["exit_code"] is not None else "timeout"),
        chk("耗时记录", True, "<30s", f"{obs['seconds']}s"),
    ]


HANDLERS = {
    "P01": p01, "P02": p02, "P03": p03, "P04": p04, "P05": p05,
    "P06": p06, "P07": p07, "P08": p08, "P09": p09, "P10": p10,
    "P11": p11, "P12": p12, "P13": p13, "P14": p14, "P15": p15,
    "P16": p16, "P17": p17, "P18": p18, "P19": p19, "P20": p20,
}


def main() -> int:
    ap = argparse.ArgumentParser(description="Behavioural probes across product versions")
    ap.add_argument("--source-root", default=str(C.DEFAULT_SOURCE))
    ap.add_argument("--out", default="")
    ap.add_argument("--work-label", default="probes")
    ap.add_argument("--version-label", default="current")
    ap.add_argument("--only", default="")
    ap.add_argument("--emit-manifest", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    manifest = C.EVAL_DIR / "probes" / "probes.json"
    if args.emit_manifest:
        manifest.parent.mkdir(parents=True, exist_ok=True)
        C.write_json(manifest, [{"id": pid, "title": title, "note": note} for pid, title, note in PROBES])
        print(f"manifest written: {manifest}")
        return 0
    if manifest.is_file():
        frozen = {row["id"] for row in C.read_json(manifest)}
        drift = sorted(frozen ^ {pid for pid, _, _ in PROBES})
        if drift:
            raise SystemExit(f"probe registry drift vs frozen manifest: {drift}")

    source = Path(args.source_root).resolve()
    if not args.out:
        raise SystemExit("--out is required when running probes")
    work = C.TEMP / args.work_label
    if work.exists():
        if not args.force:
            raise SystemExit(f"refusing to reuse existing probe workdir: {work}")
        import shutil
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)

    registry = {pid: (title, note) for pid, title, note in PROBES}
    wanted = [pid for pid in registry if not args.only or pid in args.only.split(",")]
    results = []
    for pid in wanted:
        d = work / pid
        d.mkdir(parents=True, exist_ok=True)
        run = make_run(source, d, work / "_guard.json")
        handler = HANDLERS[pid]
        outcome = handler(run, d)
        extra = None
        if isinstance(outcome, tuple):
            checks, extra = outcome
        else:
            checks = outcome
        title, note = registry[pid]
        results.append({
            "id": pid, "title": title, "note": note,
            "passed": checks_passed(checks), "checks": checks, "extra": extra,
        })

    matrix = C.envelope(source, ["common.py", "run_probes.py"], C.protocol_digest(), {
        "version_label": args.version_label,
        "finished_at": C.now_iso(),
        "summary": {
            "probes": len(results),
            "passed": sum(1 for r in results if r["passed"]),
            "failed": [r["id"] for r in results if not r["passed"]],
        },
        "probes": results,
    })
    C.write_json(Path(args.out), matrix)
    print(json.dumps(matrix["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
