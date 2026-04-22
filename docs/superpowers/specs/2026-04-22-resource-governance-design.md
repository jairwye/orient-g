# 资源/网络消耗治理（方案 A）设计稿

日期：2026-04-22  
范围：Orient-G（frontend + backend + docker compose）  
目标：减少持续资源消耗、避免网络不稳时的突发放大，同时不牺牲关键链路可用性与可观测性。

## 背景与问题陈述

本仓库存在若干“按固定间隔轮询/空转”的实现，用于展示任务进度、刷新数据、后台任务调度等。在生产环境网络不稳定、或上游服务不可达时，这些机制可能导致：

- **持续轻度消耗**：空闲时仍频繁 wakeup/请求（CPU、网络、DB 写入）
- **突发放大**：失败时重试、心跳、多个页面/组件重复拉取造成请求风暴
- **可用性误判**：用户感知“断网/服务挂”，实际可能是容器端口发布/网络抖动/上游失败导致的连锁反应

本设计选择“方案 A”：统一治理规则 + 动态退避 + 按需触发 + 可回滚开关。

## 成功标准

- **闲时请求接近 0**：无活跃任务时，不应存在持续轮询（除非明确允许“低频基线”）
- **页面不可见时不消耗**：浏览器 tab 不可见时暂停轮询
- **网络错误不放大**：连续错误进入退避/冷却，避免高频重试
- **活跃期体验可接受**：有活跃任务时仍能看到进度变化（生产可更保守）
- **可控可回滚**：新策略可通过开关退回 legacy 行为，便于线上快速止血

## 资源消耗点盘点（需治理）

### 前端（轮询/定时刷新）

- `frontend/app/components/KbInProgressBanner.tsx`
  - 刷新任务列表：`GET /api/knowledge/bigpdf/tasks?limit=12`
- `frontend/app/utils/pdf-knowledge/page.tsx`
  - 单任务进度：`GET /api/knowledge/bigpdf/tasks/:task_id`（当前 1.2s）
- `frontend/app/knowledge/page.tsx`
  - 文件夹详情：存在 running 状态时 3s 轮询
- `frontend/app/ai-interaction/page.tsx`
  - 文件较大，需进一步确认是否存在轮询或重复拉取（本次治理中纳入“统一轮询器”规范）

### 后端（后台线程/调度/队列）

- `backend/main.py`
  - APScheduler：每小时汇率更新；每天 20:00 finalize；FreshRSS 按 interval 轮询
- `backend/services/task_queue.py`
  - 常驻 worker：空闲时固定 `sleep(0.2)`，可能造成持续 CPU 唤醒
  - 持久化队列：heartbeat、reap、fail/retry backoff，网络不稳时可能放大 DB 写入与重试压力

### 部署（健康检查与重启策略）

- `docker-compose.yml`
  - backend 健康检查（30s interval）
  - 容器 restart 策略
- `scripts/caddy-health-recreate.sh`
  - 可选健康检查脚本（必须保证低频、仅失败时触发恢复动作）

## 方案 A 总体设计

核心思想：所有“轮询/空转”都改成 **按需** + **动态退避** + **可见性暂停**，并尽量做 **请求合并**。

### 1）前端：统一“智能轮询”规范

#### 统一规则

- **允许轮询的前置条件**
  - 页面可见：`document.visibilityState === "visible"`
  - 组件挂载且确实需要显示“活跃状态”
  - 存在活跃对象（例：任务状态非终态；folder 内存在 running）
- **停止条件（任一满足立即停）**
  - 页面不可见
  - 业务已终态（无活跃任务/无 running）
  - 连续失败达到阈值，进入冷却期（cooldown）
- **间隔策略（动态退避）**
  - 活跃期：2–5s（生产建议 5–10s）
  - 稳定期：10–30s（生产建议 20–60s）
  - 失败退避：指数退避，上限 60s（生产可更大），成功一次则恢复到活跃/稳定间隔
- **请求合并**
  - 同一页面多个组件依赖同一份状态时，应共享同一份拉取结果，避免重复请求

#### 落地形态

- 新增通用工具（建议路径）：`frontend/app/lib/smartPoll.ts`
  - 提供 `useSmartPoll(...)` hook 或等价封装
  - 关键参数：
    - `isEnabled(): boolean`（含 visibility gate + 业务 gate）
    - `isTerminal(data): boolean`（终态判断）
    - `load(): Promise<Data>`（请求函数，内部防并发）
    - `getIntervalMs(ctx): number`（基于 data/错误次数/是否活跃动态给 interval）
    - `onData/onError` 回调
- 将现有轮询逐个迁移到统一封装
  - `KbInProgressBanner`：仅在有活跃任务时轮询；页面不可见暂停（已具备雏形，但需统一到 smartPoll 并加入退避）
  - `pdf-knowledge`：从固定 1.2s 改为活跃 2–5s + 退避 + 终态停
  - `knowledge` folder detail：从固定 3s 改为活跃 5–10s + 退避；并避免与 banner 重复请求同类数据
  - `ai-interaction`：复核是否存在隐藏轮询/重复拉取；若存在统一纳入

#### 生产/开发默认策略

- 允许“同一套逻辑，不同默认值”
- 通过环境变量注入（Next.js 运行时可读）：
  - `NEXT_PUBLIC_POLL_ACTIVE_MS`
  - `NEXT_PUBLIC_POLL_STABLE_MS`
  - `NEXT_PUBLIC_POLL_ERROR_MAX_MS`
  - `NEXT_PUBLIC_POLL_ERROR_COOLDOWN_MS`
  - 可选 `NEXT_PUBLIC_POLL_MODE=legacy|smart`（回滚）

### 2）后端：worker 空闲退避 + 重试上限

#### 空闲退避（idle backoff）

目标：空闲时不应 0.2s 高频 wakeup。

- 设计：连续空转时 sleep 逐步加大（示例）
  - 0.2s → 0.5s → 1s → 2s → 5s（上限 5–10s）
  - 一旦取到任务立即恢复到最小 sleep

配置建议（后端 `.env`）：

- `QUEUE_WORKER_IDLE_MIN_S=0.2`
- `QUEUE_WORKER_IDLE_MAX_S=5`
- 可选开关：`QUEUE_WORKER_IDLE_BACKOFF=true|false`

#### 重试 backoff 上限（避免失败放大）

当前 backoff 与 attempts 相关，建议增加上限，避免上游不可达时重试间隔不断扩大且伴随状态写入压力。

配置建议：

- `QUEUE_RETRY_BACKOFF_MAX_SECONDS=900`（示例：15min）

#### 可观测点

现有 `/api/queue/stats` 可作为观测入口；建议在治理后关注：

- 空闲时 CPU 占用下降、wakeup 降低
- DB `kb_tasks` 表写入速率在上游失败时不出现尖峰
- 前端请求量（尤其 tasks/health）显著下降

## 风险与回滚

### 风险

- 轮询降频可能导致“进度更新不够实时”
- 请求合并/状态共享可能引入状态不一致或更新时序问题（需明确数据来源与刷新触发）

### 回滚策略

- 前端：`NEXT_PUBLIC_POLL_MODE=legacy` 回到原逻辑（或仅关闭 smartPoll）
- 后端：`QUEUE_WORKER_IDLE_BACKOFF=false` 回到固定 sleep；`QUEUE_RETRY_BACKOFF_MAX_SECONDS` 设高/不启用上限

## 测试与验证（实施后验收）

- 前端：
  - 打开相关页面但无活跃任务：不应持续打 `/api/knowledge/bigpdf/tasks`
  - 有活跃任务：轮询应开始；页面切到后台暂停；切回恢复
  - 模拟网络失败：轮询应退避，不应 2–5s 一直打
- 后端：
  - 无任务时：worker 空闲 CPU 下降
  - 上游失败：任务重试间隔可控，不会写入/请求风暴

