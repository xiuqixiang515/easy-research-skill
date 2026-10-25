# Easy Research（easy-research-skill）

科研构思与论文拆解助手：帮你把研究问题拆成**可验证的判断**，同时清楚标明事实、推断、建议和未知。

[![Skill checks](https://github.com/xiuqixiang515/easy-research-skill/actions/workflows/tests.yml/badge.svg)](https://github.com/xiuqixiang515/easy-research-skill/actions/workflows/tests.yml)

> 这是一个 **Skill**（提示词 + 参考文档 + 两个 Python 脚本），不是 pip 包，也不是模型权重。它不替你检索文献，也不判断科学内容对错；它负责的是**决策点上的纪律**：哪些结论有证据支撑、哪些槽位还没填、两套口径有没有并存。

## 它能做什么

| 模式 | 触发意图 | 产出 |
|---|---|---|
| A 找 idea | 找方向、形成候选问题 | 带来源状态和验证方案的候选 |
| B 拆论文 | 判断论文做了什么、证据支持到哪里 | 贡献、方法、证据与限制 |
| C 淬炼想法 | 评估一个已有研究设想 | 可检验假设和最小实验 |
| D 素材库 | 整理、检索、组合研究素材 | 可追溯卡片和库摘要 |

在四个模式之上，还有一层 **学科 × 研究类型** 路由：

- 7 个学科检查表：计算机、化学、生物、医学、机械、能源、电子信息
- 11 种研究类型：预测、因果、实验、仿真、理论、描述性、复现、工程验证、核算、诊断、记录

识别到学科与类型后按需加载对应检查表，用"必填槽位"核对证据，而不是把七份文件全读一遍。

## 目录结构

```
SKILL.md                    # 入口：四模式 + 学科×研究类型路由 + 证据规则
agents/openai.yaml          # 界面元数据（显示名、简介、默认提示）
references/
  idea-generation.md        # 模式 A
  demystify.md              # 模式 B
  sharpen.md                # 模式 C
  search-sources.md         # 检索源与检索要点
  report-template.md        # 报告结构
  research-types.md         # 11 种研究类型的必需槽位与越界清单
  disciplines/              # 7 个学科检查表
scripts/
  idea_card.py              # 素材库：建卡/检索/统计/组合（模式 D）
  report_render.py          # 周报与报告渲染
tests/
  test_scripts.py           # 48 项脚本测试
  validate_skill.py         # 元数据与资源校验
examples/                   # 示例卡片与报告
CHANGELOG.md / VERSION      # 版本
```

## 快速开始（模式 D：素材库）

脚本用标准库实现，无第三方依赖；CI 在 Python 3.11/3.12 上验证（3.9+ 应可运行，但未在 CI 覆盖）。建议在项目工作区显式指定库路径：

```bash
# 建卡（九个标准字段 + 任意扩展字段，含学科/研究类型/项目）
python3 scripts/idea_card.py --db ./research/cards.json template
python3 scripts/idea_card.py --db ./research/cards.json add --file card.md
python3 scripts/idea_card.py --db ./research/cards.json add \
  --title "教学楼空调节能评估" --problem "只有总电表与单点温湿度" \
  --discipline 能源 --research-type 核算 \
  --set-extra 项目=楼A --set-extra 功能单位=kWh/m2/a

# 检索 / 筛选 / 统计 / 组合
python3 scripts/idea_card.py --db ./research/cards.json search "分项计量"
python3 scripts/idea_card.py --db ./research/cards.json list --research-type 诊断
python3 scripts/idea_card.py --db ./research/cards.json stats
python3 scripts/idea_card.py --db ./research/cards.json combine --tag 约束 --tag2 方法

# 周报（含「口径冲突」检测）与完整报告
python3 scripts/report_render.py --db ./research/cards.json --weekly --out weekly.md
python3 scripts/report_render.py --db ./research/cards.json --title "研究分析" --from-cards --out report.md
```

所有命令用 `--help` 查看完整参数。库的修改走跨进程锁 + 原子替换 + `.bak` 备份；删除需显式 `--yes`；新增默认拒绝内容完全重复的卡。

## 关键设计

- **证据分层**：只把已读材料、实际运行或可追溯来源支持的内容写成事实，其余标「材料显示 / 我的推断 / 建议 / 尚未核实」。
- **必填槽位**：缺哪项就写"该槽位缺失，因此某结论只能判为信息不足"，不用推测填满。
- **口径冲突检测**：周报对同一项目/同一事项的卡片比较 12 个关键字段，出现并存取值就列出——只提示，不判断哪个对。填了 `项目` 的卡片只与同项目比较；否则用共同标签兜底（泛标签可能误配，故建议填 `项目`）。
- **不冒充标准**：检查表是清单，不是行业标准；不据此声称"符合某规范"。

## 测试与校验

```bash
python3 -m unittest discover -s tests        # 48 项
python3 tests/validate_skill.py              # 需 PyYAML（CI 里已装）
```

CI 在 ubuntu/windows × Python 3.11/3.12 上跑同一套测试（见 `.github/workflows/tests.yml`）。

## 版本

遵循语义化版本：`VERSION` + `CHANGELOG.md` + 打 `vX.Y.Z` 标签。当前 **1.6.2**。每次改动在特性分支上开发、`--no-ff` 合并到 `main` 后打标签。

## 评测（eval/* 分支）

仓库里有六轮评测记录，都不在 `main` 上、不参与发布：

| 分支 | 内容 |
|---|---|
| `eval/stem-v2` | 七专业角色评测（v1.1.0 前） |
| `eval/stem-v3` | 7 子 agent × 3 题，测 v1.2.0 学科路由 |
| `eval/stem-v4` | 42 题 + 无 Skill 对照臂 |
| `eval/stem-v5` | 4 个 SCI 级压力场景（漂移/冲突/抗压/数值） |
| `eval/stem-v6` | 冲突检测精确率研究（120 卡真值库） |
| `eval/stem-v7` | 阈值调参（81 组网格，结论：现值已最优） |

## 已知边界（如实列出）

- 离线：不联网检索，不引用真实文献；"未检索"不等于"没有相关工作"。
- 不判断科学正确性，不校验量纲（单位只做结构校验）。
- 冲突检测的天花板来自数据质量：不填「项目」且标签稀疏的库，查全率上限约 0.4。
- 这些边界不是缺陷，是设计取舍；详见各评测报告的"结论与局限"。

## 许可证

未声明。使用前请自行确认与团队规范一致。
