# 首页用到的 API 契约

本文档约定首页各模块「摘要/入口」所需接口，供员工 X 在首页按契约调用；各模块实现方（X 或其他员工）需按此格式提供接口。

## 1. 汇率趋势

- **历史数据（汇率趋势页主接口）**：`GET /api/exchange/history`
  - **可选查询参数**：`days`（最近 N 天；不传则返回自 2025-04-02 起全部数据）
  - **响应**：适配 Recharts，供 `/exchange` 单页按币种展示折线图。

```json
{
  "data": [
    { "date": "2025-04-02", "usd": 7.21, "eur": 7.85, "jpy": 0.047 },
    { "date": "2025-04-03", "usd": 7.20, "eur": 7.84, "jpy": 0.047 }
  ]
}
```

- **摘要**：`GET /api/exchange/summary`
  - **可选查询参数**：`days=7` 或 `days=30`（默认 7）
  - **响应**：`labels` + `series`（USD/CNY、EUR/CNY、JPY/CNY 三条），可与 Recharts 共用。

- **取数状态**：`GET /api/exchange/status`
  - **用途**：供汇率趋势页展示取数进度（是否正在拉取、已入库条数、最后填充日期）。
  - **响应**：`{ "fetching": bool, "totalRecords": number, "lastFilledDate": string | null }`。

- **说明**：汇率趋势为单页（`/exchange`），按钮切换美元/欧元/日元，默认最近一个月，可拖动滑块查看至 2025-04-02；数据来源与定时更新见 `规划/汇率趋势页方案.md`。

---

## 2. 新闻政策

- **列表（新闻政策页主接口）**：`GET /api/policy-news/list`
  - **可选查询参数**：`category`（`观点` | `新闻` | `AI`），不传则返回全部三类。
  - **响应**：`categories`（分类 key 列表）、`itemsByCategory`（各分类下的条目列表）、`lastSuccessAt`、`lastError`。

```json
{
  "categories": ["观点", "新闻", "AI"],
  "itemsByCategory": {
    "观点": [
      {
        "id": "tag:...",
        "title": "标题",
        "published": "2025-03-01T12:00:00Z",
        "date": "2025-03-01",
        "link": "https://...",
        "originTitle": "来源 feed 名",
        "summary": "",
        "thumbnail": ""
      }
    ],
    "新闻": [],
    "AI": []
  },
  "lastSuccessAt": 1234567890,
  "lastError": null
}
```

- **摘要**：`GET /api/policy-news/summary`
  - **可选查询参数**：`limit=5`（条数，默认 5）
  - **响应**：首页展示最近几条新闻政策标题与链接/时间。

```json
{
  "items": [
    {
      "id": "1",
      "title": "政策标题示例",
      "date": "2025-03-01",
      "link": "https://..."
    }
  ]
}
```

- **单条详情**：`GET /api/policy-news/item`
  - **必需查询参数**：`id`（条目 id，与 list 返回的 `id` 一致）。
  - **用途**：供详情页 `/policy-news/item?id=xxx` 展示完整内容（含 HTML）。
  - **响应**：与 list 中单条结构类似，增加 `content` 等完整字段；404 表示未找到。

- **说明**：数据来自 FreshRSS GReader API 定时拉取，内存缓存不写库；侧栏入口为「新闻政策」，页上三按钮「观点 / 新闻 / AI」对应三类；详见规划/新闻页方案.md。

---

## 3. 经营数据摘要

- **路径**：`GET /api/business/summary`
- **响应**：首页展示经营数据概览（如关键指标、简单图表数据）。

```json
{
  "updatedAt": "2025-03-01",
  "indicators": [
    { "name": "营收", "value": "xxx", "unit": "万元" }
  ],
  "chart": {
    "labels": [],
    "series": []
  }
}
```

- **说明**：由员工 X 实现。**当前实现**：数据来源为财务人员在**后台**上传的 Excel，上传后覆盖单文件 `business.xlsx`；概览与摘要接口从该文件解析返回，响应仍为「经营数据标准结构」。接口暂不支持 `month` 参数。后续可扩展为数据库按月份存储，届时增加 `month=YYYY-MM` 及相应说明。

**上传（后台专用）**

- **路径**：`POST /api/business/upload`
- **用途**：供财务人员后台页使用；请求体为 multipart，上传 `file`。**当前实现**：上传后覆盖单文件 `uploads/business.xlsx`，不写入数据库、无月份参数。后续可扩展为按月份入库，届时请求体可带 `month=YYYY-MM`。
- **响应**：成功返回 `{ "ok": true, "message": "..." }` 等。

**概览与摘要**

- **概览**：`GET /api/business/overview`。**当前实现**：从已上传的单文件 `business.xlsx` 解析返回，响应格式见下方「经营数据标准结构」；暂不支持查询参数 `month`。后续扩展为 DB 时可按月份读取并支持 `month=YYYY-MM`。
- **摘要**：`GET /api/business/summary`。**当前实现**：同上，从该文件解析；响应格式见上文。后续可支持 `month=YYYY-MM`。

**经营数据标准结构（契约）**

- 前端与接口以**固定 JSON 形状**为准，与数据来源（Excel / DB）解耦；后端解析或存储时只负责将数据源**映射**到该结构。
- **概览** `GET /api/business/overview` 的响应即为此结构（类型与字段稳定，便于前端与 ECharts 使用）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `stats` | `Array<{ title, value, desc, completionRatio?, targetValue?, lastYearValue?, changePercent?, overseas?, overseasRatio? }>` | 三项指标：流水、利润、资金；`title` 为中文名，`value` 为展示值（字符串），`desc` 为单位（如「万元」）；第一项（流水）可选带 `completionRatio`、`targetValue`（区块 1 流水下「目标」行 C 列，用于卡片大数字下方「目标 xxx 万元」）；第二项（利润）可选带 `lastYearValue`、`changePercent`；第三项（资金）可选带 `overseas`（「海外」行的 C 列值）、`overseasRatio`（「海外占比」行的 C 列值，小数会转为百分比数字） |
| `profitTrend` | `{ labels: string[], currentYear: number[], previousYear: number[] }` | 利润趋势：月份标签、本年各月值、往年各月值 |
| `flowCompare` | `{ labels: string[], actual: number[], target: number[] }` | 流水对比：项目名、实际值、目标值 |
| `profitCompare` | `{ labels: string[], currentYear: number[], lastYear: number[] }` | 利润对比：项目名、本年值、去年值 |

- 若某块无数据，则对应数组为空或使用默认占位（如 `value: "—"`）；**解析层只做「数据源 → 上述结构」的映射**，不在此结构上增删字段。

**Excel → 标准结构的映射规则（当前约定，单张表）**

- Excel 仅为数据源之一；当前约定为**单张表**，列 A 留空，**列 B 为标签、列 C 为数值或标题、列 D 为对应数值的单位**（在区块 1 中与 C 列值一一对应，如「万元」），按区块连续排列。解析时按下列规则填充到标准结构，规则可随表格式扩展，标准结构不变。

**区块 1：流水 / 净利润 / 资金（三项指标）**

- 每个指标占一块：**列 C 出现区块标题**（「流水」「净利润」「资金」），紧接着若干行 **列 B 为子项名、列 C 为数值、列 D 为该行数值的单位**（与 C 列一一对应，如「万元」；D 为空时默认「万元」）。
- **流水**：C 列某行为「流水」后，下一行起 B=「本年累计」/「目标」/「完成比例」等，C=数值，D=单位；展示取「本年累计」行的 C 作为流水主值、D 作为单位（无则取首个子项，单位缺省为「万元」）；取「目标」行的 C 作为 `stats[0].targetValue`（卡片大数字下方「目标 xxx 万元」的单值）；取「完成比例」行的 C 作为 `stats[0].completionRatio`（表中已是百分比数字，直接引用）。
- **净利润（即利润）**：C 列某行为「净利润」后，下一行起 B=「本年累计」/「去年同期」/「变动百分比」等，C=数值，D=单位；展示取「本年累计」行的 C 作为利润主值、D 作为单位；取「去年同期」行的 C 作为 `stats[1].lastYearValue`；取「变动百分比」行的 C 作为 `stats[1].changePercent`（若为小数如 0.05 则转为 5）。
- **资金**：C 列某行为「资金」后，下一行起 B=「总额」/「海外」/「海外占比」等，C=数值，D=单位；展示取「总额」行的 C 作为资金主值、D 作为单位；取「海外」行的 C 作为 `stats[2].overseas`；取「海外占比」行的 C 作为 `stats[2].overseasRatio`（若为小数如 0.15 则转为 15）。

**区块 2：利润趋势（按月，最多 12 个月）**

- 某行 **列 B 为「净利润」、列 C～N 为月份名**（如「1月」…「12月」），视为表头。
- 下一行 **列 B 为「本年」**，列 C 起为各月数值（与表头一一对应）。
- 再下一行 **列 B 为「去年」**，列 C 起为各月数值。
- 解析得到：`labels` = 月份名数组（最多 12 个），`currentYear` = 本年行数值，`previousYear` = 去年行数值。

**区块 3：流水按项目（实际 vs 目标）**

- 某行 **列 B 为「流水」、列 C/D/E/F… 为项目名**（如「破天一剑」「丝路传说」等），视为表头。
- 下一行 **列 B 为「本年累计」**（或「实际」），列 C 起为各项目数值。
- 再下一行 **列 B 为「目标」**，列 C 起为各项目数值。
- 解析得到：`labels` = 项目名，`actual` = 本年累计/实际，`target` = 目标。

**区块 4：利润按项目（本年 vs 去年，最多 10 项）**

- 某行 **列 B 为「利润」、列 C～L 为项目名**（最多 10 个），视为表头。
- 后续行 **列 B 为「本年累计」/「去年」等**，列 C 起为各项目数值；解析得到 `labels`、`currentYear`、`lastYear`（若缺少某行则对应数组为空）。

**说明**：以上映射规则与当前 `uploads/business.xlsx` 单张表区块格式一致。当前实现为单文件解析；若后续改为多张表或数据库按月份存储，仅扩展映射规则与数据源逻辑即可，前端与 API 仍以「经营数据标准结构」为准。

**经营数据页第一个卡片（流水）「目标」的取数与逻辑**

- **展示位置**：经营数据页第一个卡片为「流水」卡片；大数字为「本年流水」（来自 `stats[0].value`），下方一行显示「目标 xxx 万元」。
- **目标数字**：**优先**使用区块 1 流水下「目标」行的单值，即 `stats[0].targetValue`（后端从区块 1 解析：B=「目标」那一行的 C 列）。若该值为空或「—」，则**回退**为 `flowCompare.target` 数组求和（区块 3 各项目目标之和）。前端据此展示「目标 {formatNumber(flowTarget)} {stats[0].desc}」。
- **完成比例**：卡片右上角「完成比例」来自区块 1 中流水下的「完成比例」行（`stats[0].completionRatio`），与「目标」取数无关。

---

## 4. 竞品财报摘要

- **路径**：`GET /api/competitor/summary`
- **响应**：首页展示竞品财报入口或最近更新摘要。

```json
{
  "updatedAt": "2025-03-01",
  "items": [
    { "name": "竞品 A", "summary": "简要说明", "link": "/competitor/1" }
  ]
}
```

- **说明**：由员工 X 实现。

---

## 5. 流程文档规则（读写）

- **读取规则**：`GET /api/process-doc/rules`
  - **用途**：供流程文档页「规则管理」区块展示与编辑；返回完整 `process_rules.json` 内容。
  - **响应**：与 `backend/data/process_rules.json` 结构一致，至少包含 `schema_version`、`process_types`；每项流程类型含 `id`、`name`、`description`、`output_schema`、`prompt_instruction`。

```json
{
  "schema_version": "1",
  "process_types": [
    {
      "id": "finance_workflow",
      "name": "标准财务业务流程",
      "description": "步骤、责任角色、输入输出、时限",
      "output_schema": { "title": "流程名称", "steps": [], "roles": [] },
      "prompt_instruction": "请将用户的自然语言描述转化为..."
    }
  ]
}
```

- **保存规则**：`PUT /api/process-doc/rules`
  - **请求体**：与上述响应结构一致的 JSON；`process_types` 不能为空，且每项必须包含 `id` 与 `prompt_instruction`。
  - **响应**：成功返回 `{ "ok": true }`；校验失败返回 422，写入失败返回 500 及 `detail`。
  - **说明**：保存后写回 `backend/data/process_rules.json`，后续「生成流程文档」即使用新规则（生成时后端会重新读取规则文件）。

---

## 6. 知识库（ACL / 文档上传与共享）

本模块用于「知识库页 / AI 互动页 / 管理后台」联动验收。核心约定：

- **文档与表的“读权限”默认随知识库（collection）归属决定**（assignment）。
- **文档所有者永远可读**（在管理后台默认可读模板中强制勾选并置灰）。
- **MultiDept/MultiProject 的可读范围**由“共享时选择的部门/项目范围（share_scope）”决定（管理后台只读展示）。

### 6.1 知识库可选项（供 AI 互动页加载范围）

- **路径**：`GET /api/knowledge/options`
- **用途**：返回当前用户可见的 collections/tables，以及默认选中项。

```json
{
  "collections": [
    {
      "collection_id": "c_company_public_1",
      "type": "public",
      "space_type": "CompanyPublic",
      "name": "公司财务规章制度"
    }
  ],
  "tables": [],
  "default_selected_collection_ids": [],
  "default_selected_table_ids": []
}
```

### 6.2 我的知识库文档（上传 / 列表 / 删除 / 共享）

- **列表**：`GET /api/knowledge/my-documents`

```json
{
  "items": [
    {
      "doc_id": "ud_xxx",
      "title": "文件标题",
      "original_filename": "a.txt",
      "collection_ids": ["c_private_dyn_user"]
    }
  ]
}
```

- **上传**：`POST /api/knowledge/my-documents/upload`（multipart，form-data `file`）

```json
{
  "ok": true,
  "doc_id": "ud_xxx",
  "title": "a",
  "private_collection_id": "c_private_dyn_admin",
  "chunk_count": 1
}
```

- **删除**：`DELETE /api/knowledge/my-documents/{doc_id}`（仅 owner）
- **共享到**：`POST /api/knowledge/my-documents/{doc_id}/share`

```json
{
  "kb_kind": "DeptPublic",
  "department_ids": [],
  "project_ids": [],
  "company_public": false
}
```

- **默认行为**：
  - `Dept*`：未传 `department_ids` → 默认取当前用户部门
  - `Project*`：未传 `project_ids` → 默认取当前用户参与项目
  - `Multi*`：同上（默认取当前用户部门/参与项目）

### 6.3 AI 问答（按可见范围检索）

- **路径**：`POST /api/knowledge/ask`

```json
{
  "query": "问题文本",
  "selected_collection_ids": ["c_company_public_1"],
  "selected_table_ids": []
}
```

### 6.4 管理后台：知识库类型默认可读（模板）

- **路径**：`GET /api/settings/kb-meta/default-read-policies`
- **说明**：`policy.allow_owner` 永远为 `true`（强制勾选不可取消）。

```json
{
  "tenant_id": "tenant1",
  "items": [
    { "kb_kind": "ProjectPublic", "policy": { "allow_project_member": true, "allow_owner": true } }
  ]
}
```

- **保存**：`PUT /api/settings/kb-meta/default-read-policies`（后端会强制 `allow_owner=true`）

### 6.5 管理后台：特殊知识库文档（只读展示 share_scope）

- **路径**：`GET /api/settings/kb-meta/special-docs`
- **说明**：
  - `special_collections` 用于展示“特殊知识库”的中文名称/类型
  - `share_scope` 仅用于展示 Multi* 的共享范围（部门/项目），不在后台修改
  - Multi* 默认不会返回 `allow_all=true`；CompanyPublic 默认会显示 `allow_all=true`

```json
{
  "items": [
    {
      "doc_id": "ud_xxx",
      "title": "doc_multi_proj",
      "special_collections": [
        { "collection_id": "c_multi_project_public_1", "label": "多项目公共库", "space_type": "MultiProjectPublic" }
      ],
      "share_scope": { "kinds": ["MultiProjectPublic"], "department_ids": [], "project_ids": ["proj2", "proj3"] },
      "acl": {}
    }
  ]
}
```

---

## 7. Docling Sidecar（内网，`docker/docling-sidecar`，不对外暴露）

仅供 **backend** 在 `DOCLING_MODE=http` 时调用，**不**作为前端或公网 API。

### 7.1 健康检查

- **路径**：`GET /health`
- **响应示例**：

```json
{
  "ok": true,
  "docling_version": "Docling CLI version x.y.z"
}
```

### 7.2 解析（multipart 上传）

- **路径**：`POST /convert`
- **请求**：`multipart/form-data`，字段名 `file`，内容为待解析文件（与 Docling 支持的格式一致，如 PDF）。
- **成功响应**：`application/json`

```json
{
  "markdown": "# 由 Docling 导出的 Markdown 全文",
  "document": {},
  "docling_version": "Docling CLI version x.y.z"
}
```

- **字段说明**：
  - `markdown`：与本地 `docling --to md` 等价的文本。
  - `document`：与本地 `docling --to json` 等价的结构化对象（JSON 可序列化）。
  - `docling_version`：sidecar 内 Docling CLI 版本信息（可选）。

- **错误**：HTTP 4xx/5xx，`detail` 为可读错误信息；超时返回 504。

**backend 侧约定**：将 `DOCLING_HTTP_BASE_URL` 设为 sidecar 根地址（如 `http://docling:8080`），由 [backend/services/docling_runner.py](backend/services/docling_runner.py) 请求 `POST {base}/convert` 并写入 `archive/full.md`、`archive/full.json`。
