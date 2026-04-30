# 知识库 Tab 布局 v3 实施计划

> **For agentic workers：** 实施前请确认设计稿 `docs/superpowers/specs/2026-04-28-knowledge-tab-layout-v3-design.md` 已评审通过，尤其 §6 大 PDF 区块方案（默认按方案 1）。

**Goal：** 按 v3 设计稿重构知识库 Tab：私人根级文档、去虚拟未归类、全宽布局、顶栏收敛、右下大 PDF 面板、左侧无 ⋯、字号升级、日志默认展开；AI 互动上传进私人库；带到 AI 时文档引用入框。

**Architecture：** 以 `knowledge/page.tsx` 为主拆分「顶栏 / 左栏树 / 右栏上下文 / 右下 PDF 区 / 底部日志」；删除 `UNCLASSIFIED_FOLDER_ID` 路径；扩展 AI 互动 URL 或 capsule 承载 `doc_ids`；`PdfProductsModal` 逻辑下沉为内嵌面板组件。

**Tech Stack：** Next.js App Router、React、现有 `fetch` API、`kb_scope_capsule`、`getAuthHeaders`。

---

## 文件映射

| 文件 | 职责 |
|------|------|
| `frontend/app/knowledge/page.tsx` | 主布局与状态机重构 |
| `frontend/app/knowledge/components/KbPdfPackagesPanel.tsx`（新建） | 原 Modal 列表 UI，可 props `embedded` |
| `frontend/app/components/PdfProductsModal.tsx` 或内联迁移 | 视情况删除 Modal 或保留给其它入口 |
| `frontend/app/ai-interaction/page.tsx` | 解析 `doc_ids`（或 capsule）并写入 composer 引用 |
| `frontend/app/lib/kb_scope_capsule.ts` | 可选：`doc_ids` + `merge`/`buildAiInteractionHref` |
| `frontend/tests/…` | 若有纯函数（chip 默认顺序、可见性）则 TDD |

---

### Task 1：设计冻结与常量

- [ ] 确认设计稿 §6 方案 1 或 2。
- [ ] 在代码中集中定义 `DEFAULT_KB_SCOPE_ORDER` 与「项目公共是否展示」判定函数（依赖 `me` + `foldersByKind` 或后端 meta）。

**验证：** 代码审查自检。

---

### Task 2：移除 `UNCLASSIFIED_FOLDER_ID` 与左栏结构

- [ ] 左栏在 `Private` 且 chip 选中时：先渲染「根级文档」（`folder_ids` 为空），再渲染文件夹列表。
- [ ] 选中根级文档：右侧 `folderDetail` 改为合成视图（仅 docs 列表）或复用表格数据源；**不再**调用 `/folders/__unclassified__/resources`。
- [ ] 删除 `unclassifiedAsFolderDetail`、相关 `useEffect`、`useSmartPoll` 对虚拟 id 的排除分支可简化。

**验证：** 手动：私人下可见根级 + 合同管理；切换公司公共无根级区。

---

### Task 3：顶栏与去 frame

- [ ] 去掉包裹主内容的外层大 border 容器；`p-6` 可保留页面边距。
- [ ] 顶栏仅保留：chips、搜索、带到 AI、大 PDF 文档包；移除顶栏上传/新建/重复 file input（上传放到右栏 KB 菜单或文档区）。
- [ ] Chips 默认选中顺序：私人 → 部门公共 → 项目公共（条件）→ 公司公共。

**验证：** 截图对比全宽；`npm run build`。

---

### Task 4：大 PDF 文档包 → 右下内嵌

- [ ] 从 `PdfProductsModal` 抽出列表为 `KbPdfPackagesPanel`；`page.tsx` 内 `useState` 控制展开。
- [ ] 按钮文案改为「大 PDF 文档包」。

**验证：** 点击展开/收起；导出与删除仍调原 API。

---

### Task 5：左侧去 ⋯，右侧上下文 ⋯ + KB 大菜单

- [ ] 左栏移除所有 `openMenu` 的 doc/folder/kb 触发点。
- [ ] 右栏顶部：`当前知识库：{label}` + **KB 大 ⋯**（合并原 kb 级「创建文件夹」等）。
- [ ] 右栏选中行：文档 **⋯**、文件夹选中时文件夹 **⋯**（复用原菜单项）。

**验证：** 创建文件夹、分享、删除仍可用。

---

### Task 6：带到 AI 互动 + 文档引用

- [ ] `buildAiInteractionHref` 或新 helper 支持 `doc_ids`。
- [ ] AI 互动页 hydrate：读取 URL → `fetch` 文档摘要 → 写入 `composerAttachments`（或现有等价结构）。
- [ ] 无选中文档时按钮 disabled 或 toast。

**验证：** 选 2 个文档 → 跳转 → 输入区可见 2 条引用。

---

### Task 7：AI 互动上传 → 私人知识库

- [ ] 核对 `ai-interaction` 上传成功回调：确保 `upload` 目标为私人 KB 且 `folder_id` 为空或明确私人根级策略。
- [ ] 与 Task 2 根级列表联调。

**验证：** 上传后知识库私人根级可见。

---

### Task 8：字号 + 日志默认打开

- [ ] 统一提升 typography 一级。
- [ ] `<details id="kb-upload-log" open>`。

**验证：** 视觉检查；build。

---

### Task 9：全量验证

- [ ] `node --test`、`pytest`、`npm run build`。

---

## 回滚策略

保留 git 分支；`UNCLASSIFIED_FOLDER_ID` 删除前可单 commit 便于 bisect。
