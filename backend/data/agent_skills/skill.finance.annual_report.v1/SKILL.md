---
name: skill.finance.annual_report.v1
description: |
  竞品/上市公司年报 KB 问答与对比：仅基于 Orient-G 知识库 citations 与 orientg_kb_ask 结果；
  按 disclosure_regimes 选择证据位点（A股/新三板/港股/SEC），禁止外网抓取与编造金额。
---

# 年报财务分析（KB 证据驱动）

## 何时启用

- 工作流 **竞品财报分析**（`wf.competitor_finance_reports.v1`）默认勾选本技能。
- 用户勾选本技能且已选知识库文件夹（如竞品财报25）时，预检索与 Hermes 须加载 `references/` 下 profile，**不得**使用通用 Agent 路径里「对比=利润表」的默认假设。

## 硬约束

1. **证据仅来自 KB**：`orientg_kb_ask`、预检索 citations；禁止 SEC EDGAR、akshare、Yahoo 等外网补数。
2. **披露制度**：按 `references/disclosure_regimes.yaml` 的 `entities` 与 `regimes` 选择章节别名与检索词；当前竞品池以 **A 股深交 + 新三板** 为主，**港股 / SEC 为预留**。
3. **余额 vs 变动率**：问「期末余额/两期对比」时，P0 须为报表主表行（科目 + 两期金额）；「项目重大变动说明 / MD&A」中的同比% **不能替代** P0。
4. **口径**：未指定时默认 **合并** 报表；仅命中母公司表须在答复中标明口径。
5. **禁止 shell/python** 查库；缺证据须诚实说明 gap，不得估算。

## 资源文件

| 文件 | 用途 |
| --- | --- |
| `references/disclosure_regimes.json` | 制度定义 + 七家竞品实体映射 + 港股/SEC 预留（运行时加载） |
| `references/disclosure_regimes.yaml` | 同上（人类可读镜像，改 JSON 时须同步） |
| `references/retrieval_profile.json` | 科目类型 → 子 query、缺口规则、评分提示 |
| `references/evidence_locations.md` | 各制度下证据位点优先级（人类可读） |
| `resources/qc_checklist.md` | 成稿前质检 |

## 竞品池（公开仓库中性代号，2026-05）

| 代号 | 制度 | 说明 |
| --- | --- | --- |
| 可比公司A | cn_sz_main | A 股深主板示例 |
| 可比公司B | cn_sz_main | A 股深主板示例 |
| 可比公司C | cn_sz_main | 创业板体例 |
| 可比公司D | cn_neeq | 新三板示例 |
| 可比公司E | cn_neeq | 新三板示例 |
| 可比公司F | cn_neeq | 新三板示例 |
| 可比公司G | cn_neeq | 新三板示例 |

完整别名见 `disclosure_regimes.yaml` → `entities`（内网部署可覆盖为真实主体映射）。

## 与 xlsx 子技能边界

- 本技能：**从 KB 年报读数、对比表、分析报告**。
- `skill.data_parse.xlsx.v1` / 三表建模：用户明确要求 Excel 建模时再启用，不得用本技能编造模型数字。
