#!/usr/bin/env python3
"""Count how many discipline-specific mandatory slots each role file actually fills."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C

SLOTS = {
    "computer": {
        "切分单位": ["切分", "划分", "按用户", "按时间"],
        "泄漏": ["泄漏", "污染", "测试集参与"],
        "随机性": ["种子", "seed", "重复实验"],
        "算力预算": ["预算", "算力", "同步数", "参数量"],
        "指标口径": ["指标", "macro", "口径"],
        "环境版本": ["版本", "依赖", "commit", "环境"],
    },
    "chemistry": {
        "物质身份": ["身份", "结构确认", "NMR", "MS"],
        "纯度": ["纯度", "含量"],
        "计量定义": ["转化率", "选择性", "产率"],
        "独立批次": ["独立批次", "批间", "批次"],
        "空白与回收": ["空白", "回收率", "LOD", "LOQ"],
        "条件": ["温度", "溶剂", "浓度", "气氛"],
        "正交表征": ["正交", "第二种", "独立手段"],
    },
    "biology": {
        "实验单位": ["实验单位", "个体", "小区", "孔"],
        "重复类型": ["生物学重复", "技术重复"],
        "批次": ["批次", "批间"],
        "随机化盲法": ["随机", "盲法"],
        "多重比较": ["多重比较", "校正"],
        "样本量": ["样本量", "功效", "效应量"],
        "资源身份": ["细胞系", "抗体", "菌株", "编号"],
    },
    "medicine": {
        "t0": ["t0", "时间零点", "基线时点"],
        "目标人群": ["目标人群", "入组", "纳入"],
        "参考标准": ["参考标准", "金标准"],
        "盲法": ["盲法"],
        "验证范围": ["验证范围", "外部验证", "时间外", "内部验证"],
        "区间": ["区间", "CI", "置信"],
        "校准": ["校准", "calibration"],
        "事件数": ["事件数", "EPV"],
    },
    "mechanical": {
        "材料": ["材料", "牌号", "热处理"],
        "边界": ["边界", "固支", "约束"],
        "网格收敛": ["网格", "收敛", "无关性"],
        "求解设置": ["单元", "接触", "非线性", "求解器"],
        "实测校核": ["校核", "实测", "试验"],
        "工况覆盖": ["工况"],
        "失效模式": ["失效", "屈曲", "疲劳", "刚度"],
    },
    "energy": {
        "功能单位": ["功能单位", "每吨", "每 kWh", "单位面积", "单位床位"],
        "系统边界": ["边界"],
        "时间跨度": ["时间跨度", "季节", "年度", "代表"],
        "初末状态": ["SOC", "初末", "初始", "末状态"],
        "辅助能耗": ["辅助能耗", "泵", "风机", "寄生"],
        "因子来源": ["因子", "电网", "排放因子"],
        "敏感性": ["敏感性", "区间", "情景"],
    },
    "electronics": {
        "被测量定义": ["ENOB", "SNR", "BER", "线性度", "口径"],
        "激励条件": ["频率", "幅度", "采样率", "频点"],
        "公平性": ["带宽", "功率", "公平", "同等"],
        "噪声信道": ["噪声", "信道", "SNR"],
        "同步前端": ["同步", "前端", "时钟"],
        "测量本底": ["本底", "参考源", "不确定度"],
        "重复维度": ["板间", "上电", "温度", "多次"],
        "仿真实测": ["仿真", "实测"],
    },
}


def coverage(text: str, slug: str) -> dict:
    slots = SLOTS[slug]
    hits, missing = {}, []
    for name, words in slots.items():
        hit = any(word.lower() in text.lower() for word in words)
        hits[name] = hit
        if not hit:
            missing.append(name)
    return {"filled": sum(hits.values()), "total": len(slots), "missing": missing, "detail": hits}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="role files directory")
    ap.add_argument("--arm", required=True, help="label for this arm")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    rows = {}
    for path in sorted(Path(args.dir).glob("*.md")):
        slug = path.stem
        if slug not in SLOTS:
            continue
        text = path.read_text(encoding="utf-8-sig")
        rows[slug] = {"file": path.name, **coverage(text, slug)}
    payload = {
        "schema": "eval-slot-coverage/1",
        "arm": args.arm,
        "slots_per_discipline": {k: len(v) for k, v in SLOTS.items()},
        "summary": {
            "disciplines": len(rows),
            "filled_total": sum(r["filled"] for r in rows.values()),
            "slots_total": sum(r["total"] for r in rows.values()),
        },
        "rows": rows,
    }
    if args.out:
        C.write_json(Path(args.out), payload)
    print(json.dumps(payload["summary"], ensure_ascii=False))
    for slug, row in rows.items():
        print(f"  {slug:<12} {row['filled']}/{row['total']}  缺: {', '.join(row['missing']) or '无'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
