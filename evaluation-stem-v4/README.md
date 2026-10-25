# evaluation-stem-v4

对 `easy-research-skill` **v1.2.1**（`0de1b93`）的第四轮七专业评测：7 个独立子 agent 各答 6 题（共 42 题），外加一个**不读 Skill 的对照 agent**（7 题），配套 26 个行为探针。

- 不是产品发布；产品代码未被修改。
- 7+1 个 agent 是同一模型的不同会话，**不是真人研究生**。
- 离线，未检索文献；新颖性一律"未核实"。

## 文件

| 路径 | 内容 |
|---|---|
| `protocol.md` / `protocol.sha256` | 预注册（42 题 + 对照设计） |
| `stem-evaluation-report-v4-zh.md` | 主报告 |
| `diff-v3-v4.md` | 与 stem-v3 对比 |
| `roles/` | 7 份角色文件（6 题，含 D1 的真实命令输出） |
| `control/C0.md` | 无 Skill 对照臂（7 道 B1） |
| `results/arms.json` | S 臂 vs C0 臂逐项 k/7 |
| `results/slot-v4.json` | 槽位覆盖（50/50） |
| `results/role-structure.json` | 全文件结构项（S4 不适用，见报告） |
| `probes/` | 26 探针在 v1.2.1 上的结果 |
| `temp-data/` | 7 个 `role-*.json`（D1 实际落库），gitignored |

## 复现

```bash
git worktree add -b eval/stem-v4 ../er-eval-v4 main
cd ../er-eval-v4
python -X utf8 evaluation-stem-v4/harness/compare_arms.py \
  --roles evaluation-stem-v4/roles --control evaluation-stem-v4/control/C0.md \
  --out evaluation-stem-v4/results/arms.json
python -X utf8 evaluation-stem-v4/harness/run_probes.py \
  --out evaluation-stem-v4/probes/matrix-v1.2.1.json --work-label probes-v121 --version-label v1.2.1
```

## 限制

- 对照臂只 7 题，且字数（300）低于 S 臂（450），存在长度偏差。
- S7 代理失效；S8/X2 在长文本上有假阳性，报告已人工核对。
- 单次生成，无重复；结论只按 k/7 报。
