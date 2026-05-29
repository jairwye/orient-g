# Resource Governance (方案A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 统一治理本仓库“持续/突发资源消耗”点（前端轮询、后端 worker 空转、失败重试放大），在生产网络不稳场景下避免请求/写入风暴，同时保留活跃任务的可见性。

**Architecture:** 前端用一个 `useSmartPoll` 统一轮询规则（可见性 gate、无活跃即停、动态退避、失败冷却、请求合并）；后端 task worker 增加 idle backoff 与 retry backoff 上限（均可配置、可回滚）。

**Tech Stack:** Next.js (App Router) + React hooks、FastAPI、Python threading、APScheduler、PostgreSQL、Docker Compose

---

## File Structure (将新增/修改的文件)

**Frontend**
- Create: `frontend/app/lib/smartPoll.ts`（统一轮询 hook）
- Modify: `frontend/app/components/KbInProgressBanner.tsx`
- Modify: `frontend/app/utils/pdf-knowledge/page.tsx`
- Modify: `frontend/app/knowledge/page.tsx`
- (Investigate/Optional) `frontend/app/ai-interaction/page.tsx`：确认是否存在轮询/重复拉取，并按规范改造

**Backend**
- Modify: `backend/config.py`（新增配置项）
- Modify: `backend/services/task_queue.py`（idle backoff + retry backoff 上限）

**Config/Docs**
- Modify: `.env.example`（新增/解释相关配置；生产更保守默认值建议写注释）
- Modify: `README.md`（补充“资源治理/轮询策略”简短说明与排查指引）

---

### Task 1: 新增前端统一轮询 Hook（useSmartPoll）

**Files:**
- Create: `frontend/app/lib/smartPoll.ts`

- [ ] **Step 1: Add `smartPoll.ts`**

```typescript
// frontend/app/lib/smartPoll.ts
"use client";

import { useEffect, useMemo, useRef, useState } from "react";

export type SmartPollPhase = "idle" | "polling" | "cooldown" | "stopped";

export type SmartPollOptions<T> = {
  /**
   * 是否允许轮询（通常包含：页面可见 + 业务需要 + 组件挂载）
   */
  enabled: boolean;
  /**
   * 拉取函数：必须幂等；内部由 hook 防并发
   */
  load: () => Promise<T>;
  /**
   * 终态判断：返回 true 表示应停止轮询
   */
  isTerminal: (data: T | null) => boolean;
  /**
   * 是否“活跃态”：用于决定 active/stable 两档间隔
   */
  isActive: (data: T | null) => boolean;
  /**
   * 间隔（毫秒）
   */
  activeMs: number;
  stableMs: number;
  /**
   * 错误退避上限与冷却（毫秒）
   */
  errorMaxMs: number;
  errorCooldownMs: number;
  /**
   * 连续错误阈值：达到后进入 cooldown
   */
  errorCooldownAfter: number;
};

export function useSmartPoll<T>(opts: SmartPollOptions<T>) {
  const {
    enabled,
    load,
    isTerminal,
    isActive,
    activeMs,
    stableMs,
    errorMaxMs,
    errorCooldownMs,
    errorCooldownAfter,
  } = opts;

  const [data, setData] = useState<T | null>(null);
  const [phase, setPhase] = useState<SmartPollPhase>("idle");
  const [errorCount, setErrorCount] = useState(0);

  const inFlightRef = useRef(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const canRun = enabled;

  const terminal = useMemo(() => isTerminal(data), [data, isTerminal]);
  const active = useMemo(() => isActive(data), [data, isActive]);

  const clearTimer = () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  };

  const computeNextMs = () => {
    // 若连续错误较多，指数退避：stable/active 基础上倍增
    const base = active ? Math.max(500, activeMs) : Math.max(1000, stableMs);
    const k = Math.max(0, errorCount);
    if (k <= 0) return base;
    const next = Math.floor(base * Math.pow(2, Math.min(6, k))); // 最多 x64
    return Math.min(Math.max(base, next), Math.max(base, errorMaxMs));
  };

  const runOnce = async () => {
    if (!canRun) return;
    if (terminal) return;
    if (inFlightRef.current) return;
    inFlightRef.current = true;
    try {
      const next = await load();
      setData(next);
      setErrorCount(0);
    } catch {
      setErrorCount((x) => x + 1);
    } finally {
      inFlightRef.current = false;
    }
  };

  useEffect(() => {
    // disabled 时停止
    if (!canRun) {
      clearTimer();
      setPhase("stopped");
      return;
    }

    // enabled 后先跑一次（尽快拿到首屏数据）
    void runOnce();

    return () => {
      clearTimer();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canRun]);

  useEffect(() => {
    clearTimer();
    if (!canRun) return;
    if (terminal) {
      setPhase("stopped");
      return;
    }

    // 连续错误达到阈值进入 cooldown：一段时间后再尝试
    if (errorCount >= Math.max(1, errorCooldownAfter)) {
      setPhase("cooldown");
      timerRef.current = setTimeout(() => {
        setErrorCount(0);
        void runOnce();
      }, Math.max(1000, errorCooldownMs));
      return;
    }

    setPhase("polling");
    timerRef.current = setTimeout(() => {
      void runOnce();
    }, computeNextMs());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canRun, terminal, active, errorCount, activeMs, stableMs, errorMaxMs, errorCooldownMs, errorCooldownAfter]);

  const trigger = async () => {
    await runOnce();
  };

  return { data, setData, phase, errorCount, trigger };
}
```

- [ ] **Step 2: Verify typecheck/lint (frontend)**

Run (PowerShell):
```powershell
cd frontend
npm run lint:fast
```

Expected: no new errors.

---

### Task 2: Banner 任务列表轮询迁移到 useSmartPoll（可见性 gate + 无活跃即停 + 退避）

**Files:**
- Modify: `frontend/app/components/KbInProgressBanner.tsx`

- [ ] **Step 1: Refactor to use `useSmartPoll` and visibility gate**

Implementation sketch (关键点必须保留)：
- `enabled` = 页面可见（visibilitychange）+ 组件挂载
- `isActive` = 任务列表存在非 done/failed
- `isTerminal` = 任务列表不存在活跃任务（即停）
- `load` 只在需要时打 `GET /api/knowledge/bigpdf/tasks?limit=12`

- [ ] **Step 2: Manual verification**

Checklist:
- 无活跃任务时：Network 不应持续出现 `/api/knowledge/bigpdf/tasks`
- 有活跃任务时：开始轮询；切到后台 tab 暂停；切回立刻刷新并继续
- 连续网络错误：轮询间隔退避，不应高频打爆

---

### Task 3: pdf-knowledge 单任务进度轮询改为 smartPoll（替代 1.2s 固定轮询）

**Files:**
- Modify: `frontend/app/utils/pdf-knowledge/page.tsx`

- [ ] **Step 1: Replace `setInterval(poll, 1200)`**

目标：
- 活跃期：2–5s（开发可更快，生产更慢）
- 终态（done/failed）立即停止
- 错误退避 + cooldown

- [ ] **Step 2: Manual verification**

Checklist:
- 创建任务后：进度会更新
- done/failed 后：停止请求

---

### Task 4: knowledge page folder detail 轮询治理（只在 running 才轮询 + 退避）

**Files:**
- Modify: `frontend/app/knowledge/page.tsx`

- [ ] **Step 1: Replace the 3s interval in folderDetail effect**

目标：
- 只有 folder docs 中存在 `queued/parsing/parsed/packaged` 才启用
- 页面不可见暂停
- 错误退避

- [ ] **Step 2: Avoid redundant requests where possible**

原则：
- Banner 与 folder detail 属于不同数据源（tasks vs folder resources）。不强行合并，但要保证各自“无活跃即停”。

---

### Task 5: 后端 worker idle backoff + retry backoff 上限（可配置可回滚）

**Files:**
- Modify: `backend/config.py`
- Modify: `backend/services/task_queue.py`

- [ ] **Step 1: Add config fields in `backend/config.py`**

新增 settings（示例命名，需与现有 settings 风格一致）：
- `queue_worker_idle_min_s: float = 0.2`
- `queue_worker_idle_max_s: float = 5.0`
- `queue_worker_idle_backoff: bool = True`
- `queue_retry_backoff_max_seconds: int = 900`

- [ ] **Step 2: Implement idle backoff in `start_worker` loop**

要求：
- 连续空转时 sleep 逐步增加，最多到 max
- 一旦 `run_next()` 返回 true（有任务跑了），立即恢复到 min
- `queue_worker_idle_backoff=false` 时保持原行为（固定 sleep）

- [ ] **Step 3: Cap retry backoff in `_run_next_persisted` exception path**

当前逻辑：
- `bo = base * attempts`

改为：
- `bo = min(bo, queue_retry_backoff_max_seconds)`（最小 1）

- [ ] **Step 4: Verify backend still starts**

Run (PowerShell, local dev):
```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn backend.main:app --reload
```

Expected: 能启动；`/api/health` 正常；无语法/配置解析错误。

---

### Task 6: 配置与文档收口（.env.example + README）

**Files:**
- Modify: `.env.example`
- Modify: `README.md`

- [ ] **Step 1: Add frontend polling envs (NEXT_PUBLIC_*)**

在 `.env.example` 增加（带解释：生产建议更保守）：
- `NEXT_PUBLIC_POLL_MODE=smart`
- `NEXT_PUBLIC_POLL_ACTIVE_MS=...`
- `NEXT_PUBLIC_POLL_STABLE_MS=...`
- `NEXT_PUBLIC_POLL_ERROR_MAX_MS=...`
- `NEXT_PUBLIC_POLL_ERROR_COOLDOWN_MS=...`
- `NEXT_PUBLIC_POLL_ERROR_COOLDOWN_AFTER=...`

- [ ] **Step 2: Add backend worker/backoff envs**

同样补充解释与推荐默认。

- [ ] **Step 3: README 增加“资源治理”短节**

内容：解释“为什么无活跃就不轮询、后台 tab 暂停、网络失败退避”的必要性；给出排查思路（看 Network、看 `/api/queue/stats`）。

---

### Task 7 (Optional): AI interaction 页复核并纳入治理

**Files:**
- Modify: `frontend/app/ai-interaction/page.tsx`（如发现轮询/重复拉取）

- [ ] **Step 1: Find and catalog any polling / repeated fetch patterns**
- [ ] **Step 2: Apply `useSmartPoll` where applicable**

---

## Self-Review Checklist (plan)

- Spec coverage: 前端轮询统一 + 后端 idle backoff + retry cap + 配置/回滚/验证均有对应任务
- Placeholder scan: 仅“可选/需要确认是否存在轮询”的部分放在 Optional Task 7，其他任务均可直接执行
- Type consistency: `NEXT_PUBLIC_*` 与 `backend.config` 字段命名需在实施时与实际代码保持一致

