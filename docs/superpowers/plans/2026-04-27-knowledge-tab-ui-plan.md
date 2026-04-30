# 知识库 Tab UI（方案 1）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不大改页面骨架（保留双栏）的前提下，优先把知识库 Tab 的“管理体验（B）”做清晰：右侧 Inspector（空状态/单选详情/多选批量）、统一移动/复制弹窗、文件夹级分享/权限面板（两层模型 + 回收分享），并保持删除语义按上下文区分。

**Architecture:** 以 `KnowledgePage` 为顶层状态与数据加载中心，把右侧“管理体验”收口为 `InspectorPanel`（新增组件）。涉及批量/删除语义的判断下沉为纯函数，配 Node 内置测试做 TDD 回归。

**Tech Stack:** Next.js App Router（React 18）、TypeScript、Tailwind、Node `node:test`（无 Jest/Vitest）

---

## File Structure（本次计划涉及的文件）

**Modify:**
- `frontend/app/knowledge/page.tsx`

**Create（建议新增，按需精简）：**
- `frontend/app/knowledge/components/InspectorPanel.tsx`
- `frontend/app/knowledge/components/InspectorEmptyState.tsx`
- `frontend/app/knowledge/components/BulkPanel.tsx`
- `frontend/app/knowledge/components/DocDetailPanel.tsx`
- `frontend/app/knowledge/components/MoveCopyModal.tsx`
- `frontend/app/knowledge/lib/selection_context.ts`（纯函数：批量上下文/删除语义）
- `frontend/tests/selection_context.test.mjs`（Node 内置测试）

**Already exists（复用）：**
- `frontend/app/lib/smartPoll.ts`
- `frontend/app/lib/kb_polling_utils.ts` / `frontend/app/lib/kb_polling_utils.js`
- `docs/superpowers/specs/2026-04-27-knowledge-tab-ui-design.md`

---

## Task 1: 建立“批量上下文/删除语义”纯函数（TDD）

**Files:**
- Create: `frontend/app/knowledge/lib/selection_context.ts`
- Test: `frontend/tests/selection_context.test.mjs`

- [ ] **Step 1: 写失败测试（删除语义 + 跨上下文清空规则）**

```javascript
// frontend/tests/selection_context.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import {
  normalizeSourceFolderId,
  isSameSelectionContext,
  deleteSemanticsForContext,
} from "../app/knowledge/lib/selection_context.js";

test("normalizeSourceFolderId", () => {
  assert.equal(normalizeSourceFolderId(null), null);
  assert.equal(normalizeSourceFolderId(undefined), null);
  assert.equal(normalizeSourceFolderId(""), null);
  assert.equal(normalizeSourceFolderId("  f1 "), "f1");
});

test("isSameSelectionContext: loose vs folder", () => {
  assert.equal(isSameSelectionContext(null, null), true);
  assert.equal(isSameSelectionContext(null, "f1"), false);
  assert.equal(isSameSelectionContext("f1", "f1"), true);
  assert.equal(isSameSelectionContext("f1", "f2"), false);
});

test("deleteSemanticsForContext", () => {
  assert.deepEqual(deleteSemanticsForContext(null), { kind: "hard_delete" });
  assert.deepEqual(deleteSemanticsForContext("f1"), { kind: "unlink_from_folder", folder_id: "f1" });
});
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
node --test "e:\jair\SynologyDrive\游艺春秋\Projects\orient-g\frontend\tests\selection_context.test.mjs"
```

Expected: FAIL（模块不存在或函数未定义）

- [ ] **Step 3: 写最小实现（让测试通过）**

```typescript
// frontend/app/knowledge/lib/selection_context.ts
export function normalizeSourceFolderId(v: string | null | undefined): string | null {
  const s = (v || "").trim();
  return s ? s : null;
}

export function isSameSelectionContext(a: string | null | undefined, b: string | null | undefined): boolean {
  return normalizeSourceFolderId(a) === normalizeSourceFolderId(b);
}

export function deleteSemanticsForContext(source_folder_id: string | null | undefined):
  | { kind: "hard_delete" }
  | { kind: "unlink_from_folder"; folder_id: string } {
  const fid = normalizeSourceFolderId(source_folder_id);
  return fid ? { kind: "unlink_from_folder", folder_id: fid } : { kind: "hard_delete" };
}
```

- [ ] **Step 4: 再次运行测试确认通过**

Run:

```powershell
node --test "e:\jair\SynologyDrive\游艺春秋\Projects\orient-g\frontend\tests\selection_context.test.mjs"
```

Expected: PASS

- [ ] **Step 5: 小步提交（可选；需用户明确要求后再做）**

---

## Task 2: 抽出右侧 Inspector（空状态 / 单选详情 / 多选批量）

**Files:**
- Create: `frontend/app/knowledge/components/InspectorPanel.tsx`
- Create: `frontend/app/knowledge/components/InspectorEmptyState.tsx`
- Create: `frontend/app/knowledge/components/BulkPanel.tsx`
- Create: `frontend/app/knowledge/components/DocDetailPanel.tsx`
- Modify: `frontend/app/knowledge/page.tsx`

### 目标行为
- **默认空状态（已确认）**：未选中任何文档时，右侧仅显示提示卡片。
- **单选**：点击某文档行（非 checkbox）进入单选详情。
- **多选**：任意列表勾选 ≥ 1 条，右侧切换为批量面板（展示数量、清空、移动/复制/删除）。

- [ ] **Step 1: 在 `KnowledgePage` 顶层新增“单选当前文档”状态**

在 `frontend/app/knowledge/page.tsx` 顶层 state 增加：

```typescript
const [activeDoc, setActiveDoc] = useState<MyDoc | null>(null);
```

并确保：
- 勾选进入多选时，可保持 `activeDoc` 不影响批量面板
- 清空批量选择时，不强制清空 `activeDoc`（除非你希望清空也重置右侧）

- [ ] **Step 2: 新增 `InspectorEmptyState`（纯展示组件）**

```tsx
// frontend/app/knowledge/components/InspectorEmptyState.tsx
export function InspectorEmptyState() {
  return (
    <section className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
      <h2 className="text-lg font-medium text-zinc-200">管理面板</h2>
      <p className="mt-2 text-sm text-zinc-500">选择一条文档查看详情；或勾选多条进行批量操作。</p>
    </section>
  );
}
```

- [ ] **Step 3: 新增 `BulkPanel`（承载批量操作区）**

输入建议：

```tsx
export function BulkPanel(props: {
  count: number;
  source_folder_id: string | null;
  onMove: () => void;
  onCopy: () => void;
  onDelete: () => void;
  onClear: () => void;
}) { /* ... */ }
```

实现最小 UI：
- 显示 `已选 N 条`
- 按钮：移动到… / 复制到… / 删除 / 清空选择
- 删除按钮文案随上下文变化（使用 Task 1 的 `deleteSemanticsForContext`）
  - 文件夹上下文：`批量从文件夹移除`
  - 未归类：`批量删除`

- [ ] **Step 4: 新增 `DocDetailPanel`（先做最小详情）**

先只展示：
- 文件名（original_filename/title）
- doc_id（短）
- 状态（`statusLabel` 复用）
- 快捷动作：移动到… / 复制到… / 删除（单条）

后续 A/C 再加 tabs（元数据、日志等）。

- [ ] **Step 5: 新增 `InspectorPanel`，把三态收口**

决策顺序（强制一致）：
1. `bulkSelection.doc_ids.length > 0` → `BulkPanel`
2. `activeDoc != null` → `DocDetailPanel`
3. else → `InspectorEmptyState`

- [ ] **Step 6: 在页面 JSX 中替换右侧 `<section>` 为 `InspectorPanel`**

Run（仅前端类型检查）：

```powershell
Set-Location "e:\jair\SynologyDrive\游艺春秋\Projects\orient-g\frontend"
npm run build
```

Expected: build 成功

---

## Task 3: 统一“移动到…/复制到…”弹窗（单条/多条复用）

**Files:**
- Create: `frontend/app/knowledge/components/MoveCopyModal.tsx`
- Modify: `frontend/app/knowledge/page.tsx`

### 目标行为
- 单条（右侧详情里点“移动到…”）与多条（批量面板点“移动到…”）走同一弹窗。
- 支持：
  - kb_kind 分组展示
  - 文件夹搜索
  - 确认文案：`将把 N 条文档移动到 <folder>` / `复制到 <folder>`

- [ ] **Step 1: 写 `MoveCopyModal` 的 props 与最小实现**

建议 props（可按现有 `docTargetModal` 状态对齐）：

```tsx
export function MoveCopyModal(props: {
  open: boolean;
  mode: "move" | "copy";
  count: number;
  onClose: () => void;
  onConfirm: (target_folder_id: string) => Promise<void>;
  foldersByKind: Map<string, { folder_id: string; name: string; kind?: string | null }[]>;
  kbKindLabelById: Map<string, string>;
}) { /* ... */ }
```

- [ ] **Step 2: 把现有“批量移动/复制”按钮的逻辑改为打开该 modal**

当前在左栏里有两套批量条：
- 未归类批量条（`source_folder_id = null`）
- 文件夹展开时的批量条（`source_folder_id = f.folder_id`）

计划：保留左栏“选中与入口”不动，但将实际执行收口到右侧批量面板 + 统一 modal。

- [ ] **Step 3: 执行逻辑**

move：
- 若 `source_folder_id` 非空：优先调用现有的 `unlinkDocFromFolder` + link（若现有是 move API 则直接用）
- 若 `source_folder_id` 为空：直接 link 到目标（若未归类表示没绑定任何文件夹）

copy：
- 直接 link 到目标（同一文档可多文件夹）

> 注意：实现必须保留 ACL 校验失败提示（后端返回非 2xx 时显示 detail）。

- [ ] **Step 4: Build 验证**

Run:

```powershell
Set-Location "e:\jair\SynologyDrive\游艺春秋\Projects\orient-g\frontend"
npm run build
```

Expected: PASS

---

## Task 4: 分享/权限面板升级为“两层模型 + 回收分享”

**Files:**
- Modify: `frontend/app/knowledge/page.tsx`
- (Optional) Create: `frontend/app/knowledge/components/FolderAclPanel.tsx`

### 目标行为
- 权限入口：文件夹 `⋯` → `分享到…`（现有）升级为 `分享/权限…`
- 面板内容：
  - Scope：私人/部门/项目/公司公共（展示当前已共享范围）
  - Role：viewer/editor/admin（最小 3 档；若后端暂未支持 role，则 UI 先做“展示/规划态”并隐藏保存）
  - Revoke：默认“一键全撤” + 高级“按范围撤回”

- [ ] **Step 1: 盘点现有分享状态字段与接口**

在 `KnowledgePage` 中已存在：
- `shareFolder`, `shareKind`, `shareDepts`, `shareProjs`, `shareCompany`
- `folderShareTarget`（company/department/project）

先读清当前分享弹窗的渲染与提交请求逻辑，把它抽象成：
- `FolderAclPanel`（或保留在 page.tsx 但需分段清晰）

- [ ] **Step 2: 添加“回收分享”动作**

实现顺序：
1. UI：在权限面板中加 `一键全撤` 按钮
2. 调用后端：若已有 share API 支持覆盖更新（把 dept/project/company 清空），复用该 API
3. 高级：按范围撤回
   - 部门撤回：从 `department_ids` 移除某 id 后提交
   - 项目撤回：同理
   - 公司公共撤回：关闭开关后提交

- [ ] **Step 3: “只对文件夹授权”的文案与禁用逻辑**

在文档详情/批量面板里：
- 不展示“分享文档”按钮
- 引导：需要共享请到文件夹 `⋯` → `分享/权限…`

- [ ] **Step 4: 手工验收清单（前端）**

在浏览器中验证：
- 分享到部门/项目/公司公共可见
- 一键全撤生效（回到私人）
- 高级撤回按范围生效
- 非管理员用户只能只读查看（按钮禁用或隐藏）

---

## Task 5: 把左栏“批量条”降级为提示，把真正的批量操作集中到右侧

**Files:**
- Modify: `frontend/app/knowledge/page.tsx`

### 目标行为
- 左栏保留 checkbox 选择与数量提示即可
- 右栏作为唯一批量操作面板（避免左栏与右栏两套按钮重复）

- [ ] **Step 1: 移除/隐藏左栏两处批量按钮组（未归类与文件夹展开处）**
- [ ] **Step 2: 保留“已选 N 条”提示 + 提示语：`在右侧批量面板执行操作`**
- [ ] **Step 3: Build 验证**

```powershell
Set-Location "e:\jair\SynologyDrive\游艺春秋\Projects\orient-g\frontend"
npm run build
```

Expected: PASS

---

## Task 6: 全量验证（不含后端改动）

**Files:**
- None

- [ ] **Step 1: 前端 build**

```powershell
Set-Location "e:\jair\SynologyDrive\游艺春秋\Projects\orient-g\frontend"
npm run build
```

- [ ] **Step 2: 运行 Node 单测**

```powershell
node --test "e:\jair\SynologyDrive\游艺春秋\Projects\orient-g\frontend\tests\kb_polling_utils.test.mjs"
node --test "e:\jair\SynologyDrive\游艺春秋\Projects\orient-g\frontend\tests\selection_context.test.mjs"
```

- [ ] **Step 3: 手工冒烟（最少 10 分钟）**
- 进入知识库页：右栏默认空状态
- 单击文档行：右栏显示详情
- 勾选多条：右栏切换批量面板；移动/复制/删除工作正常
- 在文件夹展开列表中勾选多条：删除语义为“从文件夹移除”
- 在未归类列表中勾选多条：删除语义为“彻底删除”

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-27-knowledge-tab-ui-plan.md`. Two execution options:

1. **Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration  
2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints  

Which approach?

