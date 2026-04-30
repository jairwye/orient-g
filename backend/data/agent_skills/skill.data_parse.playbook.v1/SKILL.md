---
name: skill.data_parse.playbook.v1
description: 数据解析 Playbook：合规话术、禁止编造、与提示词资产协同时的优先级说明。
---

## Playbook（口径包，只读）

- 所有数值与结论必须来自工具返回的聚合指标或表结构摘要；禁止编造未在数据中出现的金额、占比或期间。
- 遇缺失数据、校验异常、混合类型列时须在结论与 `risks` 中显式说明，不得用猜测补全。
- 若输出结构化 JSON，字段须与业务约定的 output_shape（`conclusion` / `risks` / `suggestions` 等）一致。
- 术语与指标口径优先遵循本对话中「用户勾选的提示词资产」摘要；**冲突时以工具返回为准**。
