# 版本说明（2026-04-30）

本版本聚焦「知识库」与「AI 互动」联动的交互修复与能力补齐，包含菜单浮层、共享/移动语义、搜索体验、大 PDF 文档包入口迁移、以及跳转/竞态类问题修复。

## 关键变更

### 知识库页（`/knowledge`）
- 搜索改为与知识库范围 chips 同行的小图标，点击展开输入框；移除常驻搜索栏。
- 移除顶栏并列按钮：`带到 AI 互动`、`大 PDF 文档包`。
- 修复“搜索文档不生效”：在 **kb 视图** 也能聚合 `myDocs` 并按 `kb_kind` 过滤，再由搜索词过滤。
- 文档行 `…` 菜单新增 **带到 AI 互动**（按 `doc_ids` 以引用附件方式带入 AI 页）。
- 文件夹层面 **带到 AI 互动**：写入范围胶囊（仅当前 folder），并跳转 AI 页强制进入聊天视图（`view=chat`）。
- 文件夹/文档图标统一为站内灰色线性风格（替换彩色 emoji）。
- 修复偶发“点 A 文件夹后一闪跳到 B 文件夹”：URL 初始化只首帧生效 + folderDetail 请求序号避免竞态覆盖。

### AI 互动页（`/ai-interaction`）
- 工作空间 Tab 新增 **大PDF文档包**，与 知识库/提示词/技能/工具/工作流 并列。
- `view=chat` 或 URL 带入 `folder_id/doc_ids` 时，自动切回聊天视图，确保“带到 AI 互动”稳定落在聊天界面。
- URL 参数消费后不再一刀切清空 query：改为仅删除已消费 key，保留其它潜在参数（深链安全）。

### 后端（Knowledge 路由）
- 新增 **共享（加法）**：`POST /api/knowledge/folders/{folder_id}/share-add-scope`
  - 语义：追加可见范围，不产生两份 folder/doc；并保留 owner 私有可见性。
- 新增 **移动（替换）**：`POST /api/knowledge/folders/{folder_id}/move-to-kb`
  - 语义：撤回原共享后移动到目标范围，仅在目标范围出现。
- 部门/项目支持 **公共库/负责人库**（`access_kind=public|lead` / `kb_kind=DeptPublic|DeptLead|ProjectPublic|ProjectLead`）。

## 影响文件（主路径）
- `frontend/app/knowledge/page.tsx`
- `frontend/app/ai-interaction/page.tsx`
- `frontend/app/knowledge/components/PdfPackagesPanel.tsx`（复用）
- `backend/routers/knowledge.py`
- `backend/services/kb_folders.py`
- `backend/tests/test_kb_move_folder_to_kb.py`
- `backend/tests/test_kb_share_add_scope_api.py`

## 预提交校验（本机已跑通）
- 前端：`node --test tests/*.test.mjs`
- 前端：`npm run build`
- 后端：`python -m pytest backend/tests -q`

## 已知限制
- 当前环境 `git.exe` 运行会崩溃（`--version` 异常退出），因此无法自动完成 `git add/commit/tag`。建议先修复 Git 安装/环境后再执行提交。

