# evaluation-stem-v7

对冲突检测的三个阈值做「训练」：81 组网格 × 8 个合成族，训练/验证/测试分离，最后决定要不要改产品常量。

- 结果：**最优配置 = 当前产品值**（θ=0.40 / m=5 / s=2），平台区 24 组并列，故不改代码。
- θ 可用区间 [0.35, 0.50]；天花板来自数据（标签缺失、标签同频），不来自阈值。
- 共 416 条运行记录（1 基线 × 8 族 + 81 组 × 4 训练族 + 81 验证 + 2 压力/测试 + 端到端/规模）。

## 文件

| 路径 | 内容 |
|---|---|
| `protocol-training.md` | 运行前写定的方案（目标、数据、超参、顺序、停止条件） |
| `training-log.md` | 执行记录与结论（含四次自身返工） |
| `harness/param_search.py` | 族生成器 + 判据模拟 + 网格 + 选择 + 留出测试 |
| `results/runs.json` | 416 条运行明细 |
| `results/tuning-summary.json` | 平台区、θ 曲线、选中配置 |

## 复现

```bash
git worktree add -b eval/stem-v7 ../er-eval-v7 main
cd ../er-eval-v7
python -X utf8 evaluation-stem-v7/harness/param_search.py
```

## 结论边界

合成族、单次划分、只搜三个参数；真实库的标签习惯未知。
