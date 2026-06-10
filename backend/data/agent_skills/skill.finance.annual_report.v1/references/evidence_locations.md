# 证据位点（按披露制度）

> 机器可读配置见 `disclosure_regimes.yaml`；本文为编排与 Hermes 可读摘要。

## 通用优先级（余额/两期对比）

| 优先级 | 位点 | 合格证据 |
| --- | --- | --- |
| P0 | 报表主表 | 科目标签 + **两个** `x,xxx.xx` 金额（同行或邻近行） |
| P1 | 附注 | 分项明细、账龄、坏账等 |
| P2 | 主要会计数据 / 财务摘要 | 摘要数字（交叉验证） |
| P3 | 变动说明 / MD&A | 同比%、原因；**不可替代 P0** |

## cn_sz_main / cn_neeq（当前七家）

- **三七、完美、掌趣**：cn_sz_main → 合并三表 + 主要会计数据 + 附注。
- **华清、绿岸、塔人、像素**：cn_neeq → 同上结构，但附注可能更短；P0 权重更高。

### 示例：应收账款两期对比

1. `## 合并资产负债表` 或表格中含「应收账款」与 2024/2025 列金额  
2. `## … 应收账款` 附注  
3. 主要会计数据  
4. 财务报表项目重大变动说明（仅 -xx% 不够）

## hk_main（预留）

- 同时检索：`应收账款` / `Trade receivables` / `Receivables`  
- 表名：`综合财务状况表` 与 `Consolidated Statement of Financial Position`  
- 期次：`于十二月三十一日`、`as at 31 December`

## sec_us（预留）

- Item 8 → `Consolidated Balance Sheets` 等  
- MD&A Item 7 仅叙事  
- 期次：`FY2024`、`fiscal year ended December 31, 2024`  
- **运行时仍只查 KB**，不访问 EDGAR
