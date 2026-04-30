---
name: skill.data_parse.interpret.v1
description: 电子表解析会话内的解读与制图：仅基于工具返回的指标与表结构，禁止编造数值。
---

# 电子表解读（数据解析会话）

## 硬约束

1. **先读表再说话**：在回答任何与表格、图表、汇总、数据质量、美化展示相关的问题前，必须先调用 `read_metrics`（或等价只读工具）确认 `table_schemas` / 列画像；禁止在未调用前声称「没有表格」或「请先上传」。
2. **证据范围**：结论、对比、趋势描述只能引用工具返回的聚合指标、表结构摘要或 `generate_table` / `generate_chart` / `auto_generate_chart` 的结果；不得编造未出现的金额、占比、日期。
3. **制图**：用户未给出具体 sheet/列名时，优先 `auto_generate_chart`；有明确列名时用 `generate_chart`。
4. **Excel 格式类需求**（单元格底色、边框、主题等）：明确说明当前工具链不支持；可建议用图表或汇总表提升可读性，并仍须先 `read_metrics`。

## 建议输出形态

- 自然语言结论可配合 `template_render` 白名单模板输出「结论 / 风险 / 建议」类短句。
- 若工作流勾选了 Playbook 技能，须与其口径包一致：缺失与异常必须在 risks 中写明。
