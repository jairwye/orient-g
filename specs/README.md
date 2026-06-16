# Orient-G 规制与实施计划（`specs/`）

本目录存放**已评审或已落地的规制文档**及对应的**实施计划**。改 UI、改契约、做较大功能前，应先查此处是否已有 baseline。

与 `docs/` 的分工见 [docs/README.md](../docs/README.md)。

---

## 目录结构

| 路径 | 用途 |
|------|------|
| [`ui/`](ui/) | 页面级 UI 规制（布局、对齐、配色、截断、验收） |
| [`api/`](api/) | **API 契约**（前后端接口形状，如 [`api-contract.md`](api/api-contract.md)） |
| [`features/`](features/) | 非 UI 专向的功能/架构规制（RBAC、大 PDF、RAG 差距说明等） |
| [`plans/`](plans/) | 实施计划（对应上层 spec，含 TDD/任务拆解） |

---

## UI 规制（当前 baseline）

| 文档 | 状态 | 说明 |
|------|------|------|
| [ui/ai-interaction.md](ui/ai-interaction.md) | **baseline** | AI 互动页 |
| [ui/1.2.3-agent-page.md](ui/1.2.3-agent-page.md) | **draft** | Agent 页（与 AI 互动并列，1.2.3） |
| [ui/1.2.0.b-知识库页UI现状.md](ui/1.2.0.b-知识库页UI现状.md) | **baseline** | 知识库页（已合并并删除 2026-04 历史稿） |
| [ui/1.2.3.c-竞品财报可视化-ui.md](ui/1.2.3.c-竞品财报可视化-ui.md) | **draft** | 竞品财报 10 屏 scroll-snap + Recharts（1.2.3.c） |

外部视觉参考（**非规制**）：[docs/reference/kimi-ui-reference.md](../docs/reference/kimi-ui-reference.md)

---

## 功能规制（baseline）

| 文档 | 说明 |
|------|------|
| [features/1.2.0.a-权限模型与页面可见性.md](features/1.2.0.a-权限模型与页面可见性.md) | **baseline** — 1.2.0.a RBAC |
| [features/1.2.2.g-大PDF解析流程重构方案.md](features/1.2.2.g-大PDF解析流程重构方案.md) | **baseline** — 1.2.2.g 大 PDF |
| [features/1.2.0.c-d-RAG检索与入库差距.md](features/1.2.0.c-d-RAG检索与入库差距.md) | 1.2.0.c / 1.2.0.d 差距（living） |
| [features/1.2.3-Hermes-Agent与Orient-G融合方案.md](features/1.2.3-Hermes-Agent与Orient-G融合方案.md) | **draft** — 1.2.3 Hermes 融合 |
| [features/1.2.3-agent-kb-router-design.md](features/1.2.3-agent-kb-router-design.md) | **draft** — Agent KB 三路分流（fast / hermes_lite / hermes_full） |
| [features/1.2.3.c-竞品财报可视化.md](features/1.2.3.c-竞品财报可视化.md) | **draft** — 1.2.3.c 竞品财报 MD → Snapshot → `/competitor` |
| [features/2026-04-22-resource-governance-design.md](features/2026-04-22-resource-governance-design.md) | 资源治理 |
| [plans/2026-04-22-resource-governance-plan.md](plans/2026-04-22-resource-governance-plan.md) | 对应实施计划 |
| [plans/1.2.3.b-acceptance-tests.md](plans/1.2.3.b-acceptance-tests.md) | Evidence Pack + Tier pytest / 冒烟 |
| [plans/1.2.3.b-finance-matrix-browser-testing.md](plans/1.2.3.b-finance-matrix-browser-testing.md) | **baseline** — 财务矩阵 Chrome DevTools / CDP 浏览器实测规制 |
| [plans/1.2.3.c-竞品财报可视化-plan.md](plans/1.2.3.c-竞品财报可视化-plan.md) | **draft** — 1.2.3.c 解析器 / API / 前端分屏实施 |

## API 契约

| 文档 | 说明 |
|------|------|
| [api/api-contract.md](api/api-contract.md) | 前后端 API **baseline** |

---

## 实施计划索引

知识库 UI 见 [ui/1.2.0.b-知识库页UI现状.md](ui/1.2.0.b-知识库页UI现状.md)。RAG 见 [plans/1.2.0.d-1.2.0.c-audit-and-manifest-plan.md](plans/1.2.0.d-1.2.0.c-audit-and-manifest-plan.md)。Hermes 方案见 [plans/1.2.3-hermes-integration-plan.md](plans/1.2.3-hermes-integration-plan.md)；Agent KB 分流见 [plans/1.2.3-agent-kb-router-plan.md](plans/1.2.3-agent-kb-router-plan.md)；Evidence Pack 验收见 [plans/1.2.3.b-acceptance-tests.md](plans/1.2.3.b-acceptance-tests.md)；**财务矩阵浏览器实测**见 [plans/1.2.3.b-finance-matrix-browser-testing.md](plans/1.2.3.b-finance-matrix-browser-testing.md)；**竞品财报可视化**见 [plans/1.2.3.c-竞品财报可视化-plan.md](plans/1.2.3.c-竞品财报可视化-plan.md)（feature / UI 同前缀）。**联调操作**见 [../docs/hermes.md](../docs/hermes.md)。

---

## 与其它文档的关系

| 位置 | 角色 |
|------|------|
| [`规则/`](../规则/) | 项目强制约束（不上传 GitHub）；见 [规则/文档索引.md](../规则/文档索引.md) |
| [`规划/`](../规划/) | 方案论证、版本路线图（不上传 GitHub）；见 [规划/文档索引.md](../规划/文档索引.md) |
| [`docs/`](../docs/) | 参考截图、实施手册、API 契约、术语、归档 |
| [`CONTRIBUTING.md`](../CONTRIBUTING.md) | 对外协作入口（分支、PR、迁移、校验） |

**流程建议**：`规则` 定边界 → `规划` 论证目标 → `specs` 固化可验收规制 → `plans` 拆解实施 → 代码 + `docs` 手册/契约同步。

---

## 变更约定

1. **UI 改动**：先更新 `specs/ui/<page>.md` 或新建 spec，再改 `frontend/`；开发机须 Read `frontend-design` skill（见 `.cursor/rules/frontend-ui-design.mdc`）。
2. **规制状态**：文首注明 `status: baseline | draft | superseded` 及日期；superseded 文保留并链到替代 spec。
3. **自 `docs/superpowers/` 迁出**：旧路径仅留一行重定向 stub，避免断链。
4. **自 `规划/` 迁入（1.2.x.x）**：文件名**必须保留版本前缀**；迁入后**删除** `规划/` 原稿，仅在 [`规划/文档索引.md`](../规划/文档索引.md) 保留一行指向 `specs/`（不保留 stub 重定向文件）。
