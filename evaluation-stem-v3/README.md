# evaluation-stem-v3

对 `easy-research-skill` **v1.2.0**（`5b83e65`）的第三轮七专业评测：7 个独立子 agent 扮演 7 个专业研究生，各答 3 道全新题（共 21 题），配套 26 个行为探针与 3 轮 CLI 集成。

- 这不是产品发布。产品代码在本分支上未改动（受测版本即 `main` 的 v1.2.0）。
- 7 个子 agent 是同一底层模型的不同会话，**不是真人研究生、不是专家评审**。
- 全程离线，未检索文献；所有新颖性判断为"未核实"。

## 文件

| 路径 | 内容 |
|---|---|
| `protocol.md` / `protocol.sha256` | 预注册协议（21 题、槽位指向、停止条件） |
| `stem-evaluation-report-v3-zh.md` | 主报告 |
| `diff-v2-v3.md` | 与 stem-v2 的对比 |
| `roles/` | 7 份角色文件（每题含题目、回答、槽位自检） |
| `probes/` | `probes.json`（26 项）+ 两版本矩阵 + 红绿对比 |
| `results/` | `cli-run-1..3.json`、`summary.json`、`role-structure.json`、`slot-v2.json`、`slot-v3.json` |
| `harness/` | 复用 v2 的 6 个脚本，新增 `slot_coverage.py`，`grade_text.py` 增加 roles 模式 |
| `temp-data/` | 运行数据（gitignored） |

## 复现

```bash
git worktree add -b eval/stem-v3 ../er-eval-v3 main
cd ../er-eval-v3

python -X utf8 evaluation-stem-v3/harness/run_probes.py \
  --out evaluation-stem-v3/probes/matrix-v1.2.0.json --work-label probes-v120 --version-label v1.2.0

python -X utf8 evaluation-stem-v3/harness/run_cli_suite.py \
  --out evaluation-stem-v3/results/cli-run-1.json --run-label run1 --expect-branch eval/stem-v3

python -X utf8 evaluation-stem-v3/harness/slot_coverage.py \
  --dir evaluation-stem-v3/roles --arm v1.2.0 --out evaluation-stem-v3/results/slot-v3.json
```

## 已知限制

- 无无 Skill 对照臂，结构项饱和（全 7/7），不能据此声称路由提升了输出质量。
- 正则打分在长文本上出现 5 处假阳性，已人工复核并降级为粗筛。
- 未做文本层稳定性复跑，未做并发加压。
