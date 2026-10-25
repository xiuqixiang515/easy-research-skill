# evaluation-stem-v5

对 `easy-research-skill` **v1.4.1** 的 SCI 级压力测试：不再堆题量，而是四个"长程/对抗"场景——漂移、跨月冲突、抗压、数值陷阱。

- 结果对产品不利：3/4 场景不能区分 Skill 与无 Skill，只有"跨月冲突"暴露真实缺口。
- 产品代码未改动；两臂均为同一模型的不同会话，不是真人。

## 文件

| 路径 | 内容 |
|---|---|
| `protocol.md` / `protocol.sha256` | 预注册（四场景与判据） |
| `stem-evaluation-report-v5-zh.md` | 主报告 |
| `diff-v4-v5.md` | 与 stem-v4 的对比 |
| `scenarios/S1-drift*.md` | 五轮漂移（Skill 臂 / 对照臂） |
| `scenarios/S3-pressure-*.md` | 抗压（双臂） |
| `scenarios/S4-numeric-*.md` | 数值陷阱（双臂） |
| `results/conflict.json` | 冲突探针（0 命中） |
| `results/drift.json` | 每轮强度词计数（仅参考，结论以原文为准） |
| `results/numeric.json` | 4 个埋点命中（两臂各 4/4） |
| `harness/` | 复用 v4，新增 `conflict_probe.py`、`drift_scan.py`、`numeric_scan.py` |

## 复现

```bash
git worktree add -b eval/stem-v5 ../er-eval-v5 main
cd ../er-eval-v5
python -X utf8 evaluation-stem-v5/harness/conflict_probe.py
python -X utf8 evaluation-stem-v5/harness/numeric_scan.py \
  evaluation-stem-v5/scenarios/S4-numeric-skill.md \
  evaluation-stem-v5/scenarios/S4-numeric-control.md \
  --out evaluation-stem-v5/results/numeric.json
```

## 限制

- S1 是单会话五轮，不是真实六个月；S3/S4 各一次。
- 冲突是人为埋的；真实冲突多为"措辞不同、含义相同"。
- 强度词计数会把"引用被拒绝的词"计入，最终判断以原文精读为准。
