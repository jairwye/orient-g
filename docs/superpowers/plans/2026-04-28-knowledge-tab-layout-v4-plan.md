# 知识库 Tab 布局 v4 实施计划

> **Goal：** 落地 v4 设计稿（`docs/superpowers/specs/2026-04-28-knowledge-tab-layout-v4-design.md`）：吃满页面、搜索/chips 对调、左栏仅文件夹可滚、右栏文档/夹分区、可选中知识库、修复「合同管理」加载失败、强化视觉区分；以 TDD 补充纯函数与关键回归。

**Architecture：** 在 `frontend/app/knowledge/page.tsx` 引入 `KbSelection` 状态；抽出轻量子组件（`KbTopBar`、`KbFolderSidebar`、`KbContextPanel`）或同文件分段；纯逻辑进 `frontend/app/knowledge/lib/` 以便 `node:test`。

**Tech Stack：** React + TS + Tailwind + 既有 API。

---

## 文件映射

| 文件 | 变更 |
|------|------|
| `frontend/app/knowledge/page.tsx` | 主重构：布局、选择模型、左右栏内容 |
| `frontend/app/knowledge/lib/kb_selection.ts` + `.js` | 纯函数：`normalizeSelection`、可选 `folderBelongsToKind` |
| `frontend/tests/kb_selection.test.mjs` | TDD：选择态与分支 |
| `backend`（按需） | 仅当文件夹 resources 权限/错误码需修正时 |

---

## 任务拆分

### Task 1：TDD — 选择模型纯函数

- [ ] 新增 `kb_selection` 纯函数与测试（至少覆盖：kb 选中、folder 选中、非法组合）。

### Task 2：顶栏布局

- [ ] 顶栏按设计稿 v4 §7「布局 2」实现：第一行搜索+动作，第二行 chips；默认四 chip 同步设计稿 §2.1。

### Task 3：左栏

- [ ] 去掉左栏零散文档块；新增可选中 KB 头行；仅文件夹列表。  
- [ ] 左栏滚动容器按视口高度占满并保持滚动条可见。

### Task 4：右栏

- [ ] 文档区/文件夹区分区与样式强化。  
- [ ] KB 选中时展示 KB 管理区（承接原 kb 菜单能力）。

### Task 5：合同管理加载失败

- [ ] 复现路径：选中该 folder → `/resources`。  
- [ ] 透传错误 `detail`；修根因（前端误用 id / 后端 403）。

### Task 6：验证

- [ ] `node --test`、`npm run build`、`pytest -q`。

---

## 备注

原型图：`assets/knowledge-tab-v4-wireframe-a.png`（路径见设计稿）。
