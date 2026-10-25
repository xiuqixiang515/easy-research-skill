# evaluation-stem-v2

对 `easy-research-skill` **v1.1.1**（`product_rev=b4173dd`）的七专业评测：7 个 AI 扮演的研究生角色 × A/B/C/D 四模式，加无 Skill 三臂对照、20 个行为探针、双版本效率基准。

- 这不是产品发布，是评测材料。产品代码（`SKILL.md` / `references/` / `scripts/` / `tests/`）在本分支上一字未改。
- 评测者与生成者是同一个模型；所有"专业意见"是 AI 角色扮演，**不是真人研究生、不是同行评审、不是专家背书**。
- 全程离线：未检索任何数据库，未引用任何真实或伪造文献；所有新颖性判断为"未核实"。

## 文件

| 路径 | 内容 |
|---|---|
| `protocol.md` | 预注册协议（跑题前冻结；题目、判据、探针、停止条件） |
| `protocol.sha256` | 协议哈希 |
| `stem-evaluation-report-v2-zh.md` | 主报告（结论、四维、七专业意见、v1.2.0 建议） |
| `roles/` | 7 份角色文件（原始回答 + 四维评价 + 规则缺口定位） |
| `control/` | 三臂对照：C0 裸提示 / C1 三行规则 / S 完整 Skill + `rubric.md` |
| `stability/` | 文本层稳定性复跑（每角色 1 题 × 3 次） |
| `harness/` | 6 个脚本：CLI 套件、探针、基准、打分、比较、溯源 |
| `probes/` | `probes.json` 冻结清单 + `probe-matrix.json` 双版本红绿 |
| `results/` | `cli-run-1..3.json`、`summary.json`、`bench.csv`、`text-grades.json`、`stability.json` |
| `diff-v1-v2.md` | 与 `eval-stem-v1` 的逐项对比 |
| `MANIFEST.sha256` | 所有已提交产物的哈希 |
| `temp-data/` | 运行时数据（gitignored，不提交） |

## 复现（约 3 分钟）

```bash
# 在 linked worktree 里，branch 必须是 eval/stem-v2
git worktree add -b eval/stem-v2 ../er-eval-v2 b4173dd
cd ../er-eval-v2

python -X utf8 evaluation-stem-v2/harness/run_cli_suite.py \
  --out evaluation-stem-v2/results/cli-run-1.json --run-label run1 --expect-branch eval/stem-v2

python -X utf8 evaluation-stem-v2/harness/run_probes.py \
  --out evaluation-stem-v2/probes/matrix-v1.1.1.json --work-label probes-v111 --version-label v1.1.1

python -X utf8 evaluation-stem-v2/harness/bench_scaling.py \
  --out evaluation-stem-v2/results/bench-v1.1.1.csv --label v1.1.1 --work-label bench-v111

python -X utf8 evaluation-stem-v2/harness/verify_provenance.py --product-rev b4173dd
```

对照版本：

```bash
git worktree add --detach ../er-baseline-v110 a03c344
python -X utf8 evaluation-stem-v2/harness/run_probes.py \
  --source-root ../er-baseline-v110 \
  --out evaluation-stem-v2/probes/matrix-v1.1.0.json --work-label probes-v110 --version-label v1.1.0
git worktree remove ../er-baseline-v110
```

## 已知限制

- 本机 Python 3.13.14 不在 CI 矩阵（3.11/3.12），结果不外推；本机无 PyYAML，`validate_skill.py` 未执行（由 CI 覆盖）。
- 28 个主案例每题只生成一次，属单次观察；稳定性只在 7 个短题上复跑 3 次。
- 效率数据是墙钟时间，不含 token、网络与真人操作，不代表 Agent 响应速度。
- 打分器是正则代理，与生成器同源，已做 20% 人工抽查（见报告 §5）。

## 标签

`eval-stem-v2`（annotated，指向本分支的评测提交）。上一轮为 `eval/stem-v1`（`a01d69b`）。
