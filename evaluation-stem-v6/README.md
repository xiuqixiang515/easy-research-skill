# evaluation-stem-v6

对 `easy-research-skill` 冲突检测做精确率/召回率研究：造 120 张带真值的库（12 项目 × 150 组真冲突），比较四种判据，再端到端跑真实 `weekly`；另做 2000 张卡的规模测试。

- 结论：v1.5.0 的"同学科 + 共同标签"判据在真实库上 P=0.125，几乎不可用；改为"项目优先 + 通用标签剔除"后 P=1.000 / R=1.000。
- 顺手修了大库性能悬崖（2000 卡 12.7 s → 0.27 s）。
- 产品改动见 v1.6.0 / v1.6.1 / v1.6.2；本目录只放证据与脚本。

## 文件

| 路径 | 内容 |
|---|---|
| `conflict-precision-report-zh.md` | 主报告（含两次自身测量错误的记录） |
| `harness/conflict_bench.py` | 生成器 + 四种判据 + 离线打分 + `--e2e` 解析真实周报 |
| `results/conflict-bench.json` | 最新规则下的离线与端到端结果 |
| `results/conflict-bench-v1.5.0.json` | 改前基线（P=0.125 / R=0.167） |
| `results/conflict-bench-v1.6.2.json` | 改后（P=1.000 / R=1.000，0.159 s） |

## 复现

```bash
git worktree add -b eval/stem-v6 ../er-eval-v6 main
cd ../er-eval-v6
python -X utf8 evaluation-stem-v6/harness/conflict_bench.py \
  --e2e --source-root ../easy-research-skill-v1.1.0
```

## 限制

合成库标签较干净；2000 张只测性能不测精度；没有真人使用测试。
