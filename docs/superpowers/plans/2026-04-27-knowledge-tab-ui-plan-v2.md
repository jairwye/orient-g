# 知识库 Tab UI（方案 A 终稿 v2）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按终稿 A（v2）将知识库 Tab 重做为极简同 frame：去掉多余标题层、同一 frame 容纳所有知识库范围、移除常驻右栏管理面板；所有管理动作回归 `⋯` 菜单；大 PDF 产物包管理改为顶栏入口弹层（产物视角：包列表 + 行内导出类型 + `⋯` 菜单下载/删除）；修复三点菜单“新建文件夹”失效；排序规则（私人/公司公共置顶）；补齐 `wangjia` 部门公共默认文件夹（合同管理/合同台账）。

**Architecture:** 以 `frontend/app/knowledge/page.tsx` 为核心重构 UI 结构，但将易测试的逻辑（排序、范围筛选、默认文件夹兜底决策）下沉到 `frontend/app/knowledge/lib/*.ts` 纯函数，并用 Node 内置 `node:test` 做 TDD。UI 侧以“顶栏 + 左侧文件夹树 + 右侧文档列表 + 若干 modal”的最小结构实现。

**Tech Stack:** Next.js 16 (App Router)、React 18、TypeScript、Tailwind、Node `node:test`

---

## File Structure

**Modify:**
- `frontend/app/knowledge/page.tsx`

**Create:**
- `frontend/app/knowledge/lib/kb_sort.ts`（kb kind 排序、范围置顶逻辑）
- `frontend/app/knowledge/lib/default_folders.ts`（wangjia 部门公共默认文件夹兜底策略）
- `frontend/app/knowledge/components/PdfProductsModal.tsx`（大 PDF 产物弹层：包列表 + 行内导出类型 + ⋯）
- `frontend/tests/kb_sort.test.mjs`
- `frontend/tests/default_folders.test.mjs`

**Remove/Stop using (in UI):**
- `frontend/app/knowledge/components/InspectorPanel.tsx`（不再在页面常驻使用；可先保留文件但从页面移除引用）

---

## Task 1: TDD — kb kind 排序（私人/公司公共置顶）

**Files:**
- Create: `frontend/app/knowledge/lib/kb_sort.ts`
- Test: `frontend/tests/kb_sort.test.mjs`

- [ ] **Step 1: 写失败测试**

```javascript
import test from "node:test";
import assert from "node:assert/strict";
import { sortKbKindsPinned } from "../app/knowledge/lib/kb_sort.js";

test("sortKbKindsPinned pins Private and CompanyPublic first", () => {
  const input = ["DeptPublic", "Private", "ProjectPublic", "CompanyPublic", "MultiDeptPublic"];
  const out = sortKbKindsPinned(input);
  assert.deepEqual(out.slice(0, 2), ["Private", "CompanyPublic"]);
});
```

- [ ] **Step 2: 跑测试确认失败**

Run:

```powershell
node --test "e:\jair\SynologyDrive\游艺春秋\Projects\orient-g\frontend\tests\kb_sort.test.mjs"
```

- [ ] **Step 3: 最小实现让测试通过**
- [ ] **Step 4: 再跑测试 PASS**

---

## Task 2: TDD — wangjia 部门公共默认文件夹兜底策略（决策函数）

**Files:**
- Create: `frontend/app/knowledge/lib/default_folders.ts`
- Test: `frontend/tests/default_folders.test.mjs`

策略（可测试部分）：给定 `username`、现有 `folders[]`、候选默认名列表（["合同管理","合同台账"]），决定是否需要创建、创建哪个名字。

- [ ] **Step 1: 写失败测试**

```javascript
import test from "node:test";
import assert from "node:assert/strict";
import { pickDeptDefaultFolderName } from "../app/knowledge/lib/default_folders.js";

test("pickDeptDefaultFolderName returns null when not wangjia", () => {
  assert.equal(pickDeptDefaultFolderName({ username: "alice", existingNames: [], candidates: ["合同管理","合同台账"] }), null);
});

test("pickDeptDefaultFolderName picks first missing candidate", () => {
  assert.equal(pickDeptDefaultFolderName({ username: "wangjia", existingNames: ["财务报表"], candidates: ["合同管理","合同台账"] }), "合同管理");
  assert.equal(pickDeptDefaultFolderName({ username: "wangjia", existingNames: ["合同管理"], candidates: ["合同管理","合同台账"] }), "合同台账");
});
```

- [ ] **Step 2: 跑测试确认失败**
- [ ] **Step 3: 最小实现让测试通过**
- [ ] **Step 4: 再跑测试 PASS**

---

## Task 3: UI 重构（终稿 A）— 去标题层、同 frame、去右栏管理面板

**Files:**
- Modify: `frontend/app/knowledge/page.tsx`

目标：
- 去掉页面 H1 “知识库”标题块与“文件浏览器”标题块（不再占行）。
- 同一 frame：顶栏（范围 chips + 搜索 + 上传/新建文件夹/大PDF产物/⋯）。
- 左侧文件夹树 + 右侧文档列表。
- 移除常驻 Inspector（管理面板），仍保留行 `⋯` 菜单与 modal。
- 移除/降级“解析该文件夹”显著按钮（若仍存在）。

- [ ] **Step 1: 在 JSX 中改为：顶栏 + split 布局（树/列表）**
- [ ] **Step 2: 引入 kb kind 排序函数 sortKbKindsPinned 用于范围 chips 渲染**
- [ ] **Step 3: 删除/隐藏旧的右侧 Inspector 使用**

验证：
- [ ] `npm run build` 通过

---

## Task 4: “新建文件夹”与三点菜单修复（可用性优先）

**Files:**
- Modify: `frontend/app/knowledge/page.tsx`

目标：
- 三点菜单至少包含：新建文件夹，并确保不依赖 `me` / share 也能成功创建。
- 如果创建后需要共享到部门/项目/公司公共：可以引导打开“分享/权限”弹窗（但创建本身必须成功）。

- [ ] **Step 1: 调整 kb kind `⋯` 菜单的“新建文件夹”**：只负责创建 folder，成功后刷新列表；共享步骤若缺少 me 信息则跳过并提示。
- [ ] **Step 2: 确保左侧树与右侧列表的 `⋯` 菜单仍存在且可打开**

验证：
- [ ] `npm run build` 通过

---

## Task 5: 大 PDF 产物弹层（产物视角：列表 + 行内导出类型 + ⋯）

**Files:**
- Create: `frontend/app/knowledge/components/PdfProductsModal.tsx`
- Modify: `frontend/app/knowledge/page.tsx`

目标：
- 顶栏按钮“**大PDF产物**”打开弹层。
- 弹层展示 RAG 包列表（来源：现有 `ragItems`）。
- 每行有导出类型选择（Open-WebUI / cn_kb / standard），操作收起在 `⋯`：
  - 下载（调用现有 `downloadRagExport(package_id, exportKind)`）
  - 删除整个资源包（调用现有 `deleteRagPackage(package_id)`）
- 不在主界面占用额外 panel（移除常驻“大文档 RAG 包”区块）。

验证：
- [ ] `npm run build` 通过

---

## Task 6: wangjia 部门公共默认文件夹落地（可回归）

**Files:**
- Modify: `frontend/app/knowledge/page.tsx`

目标：
- 在 `loadAll()` 拉到 `me` 与 `folders` 后，若 `me.username === "wangjia"`，并且在“部门公共范围”未存在候选默认文件夹，则自动创建并共享到其部门范围（复用现有 `share-scope` 逻辑）。
- 必须遵守同名冲突约束：若后端拒绝同名（400），则不重试并给出提示。

验证：
- [ ] 手工：登录 wangjia，切到部门公共范围能看到默认文件夹

---

## Task 7: 全量验证（必须）

- [ ] **Node tests**

```powershell
node --test "e:\jair\SynologyDrive\游艺春秋\Projects\orient-g\frontend\tests\kb_sort.test.mjs"
node --test "e:\jair\SynologyDrive\游艺春秋\Projects\orient-g\frontend\tests\default_folders.test.mjs"
node --test "e:\jair\SynologyDrive\游艺春秋\Projects\orient-g\frontend\tests\kb_polling_utils.test.mjs"
node --test "e:\jair\SynologyDrive\游艺春秋\Projects\orient-g\frontend\tests\selection_context.test.mjs"
```

- [ ] **Frontend build**

```powershell
Set-Location "e:\jair\SynologyDrive\游艺春秋\Projects\orient-g\frontend"
if (Test-Path .next) { Remove-Item -Recurse -Force .next }
npm run build
```

- [ ] **Dev sanity**
  - `npm run dev` 页面可打开
  - `/knowledge` 页面无多余标题层、无常驻右栏管理面板
  - `⋯` 菜单可用（至少能创建文件夹）
  - 大PDF产物弹层可打开，能下载/删除（若后端数据存在）

