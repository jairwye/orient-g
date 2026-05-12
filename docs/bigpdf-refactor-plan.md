# 大 PDF 解析流程重构方案

## 1. 用户流程设计

### 1.1 进入页面时的状态检查

```
用户进入 /utils/pdf-knowledge
    ↓
前端调用 GET /api/knowledge/bigpdf/status
    ↓
后端返回当前系统状态：
{
  "has_running_task": true,
  "running_task": {
    "task_id": "t_xxx",
    "owner": "user1",
    "is_mine": false,
    "status": "running",
    "stage": "parsing",
    "progress": 45,
    "estimated_remaining": 1200,  // 秒
    "file_name": "big.pdf",
    "file_size": 15728640,  // 15MB
    "page_count": 300
  },
  "queue_position": 2,  // 如果当前用户有排队任务
  "queue_length": 3     // 总排队人数
}
```

**UI 展示：**
- 如果 `has_running_task` 且 `is_mine=true`：
  - 显示进度卡片（可展开/折叠）
  - 显示 [取消任务] 按钮
  - 提示"您的任务正在解析，预计还需 XX 分钟"

- 如果 `has_running_task` 且 `is_mine=false`：
  - 显示系统状态："当前有用户正在解析大 PDF（预计还需 XX 分钟）"
  - 显示排队信息："您前面还有 X 个任务在等待"
  - [排队上传] 按钮

- 如果无运行中任务：
  - 正常显示上传界面

### 1.2 上传前的预估

```
用户选择文件
    ↓
前端读取文件信息：
- file.size (字节)
- 通过 pdf.js 快速读取页数（只读前几页获取总页数）
    ↓
显示预估信息：
"文件：big.pdf
 大小：15 MB
 页数：约 300 页
 预计解析时间：30-45 分钟
 提示：解析耗时较长，您可以关闭页面去处理其他事务，完成后我们会提醒您"
    ↓
[确认并开始解析]
```

### 1.3 解析中的进度展示

**进度卡片设计（可折叠，固定在页面角落）：**

```
┌─────────────────────────────────────┐
│ 📄 big.pdf  解析中...          [-]  │
├─────────────────────────────────────┤
│                                     │
│ [=====>          ] 约 40%          │
│                                     │
│ 阶段：解析中                         │
│ 已用时：18 分钟                      │
│ 预计剩余：25 分钟                    │
│                                     │
│ [停止跟踪]  [强制终止]               │
│                                     │
│ 💡 提示：您可以关闭此页面，完成后    │
│    我们会通过站内提醒通知您          │
│                                     │
└─────────────────────────────────────┘
```

**阶段定义：**
1. `queued` - 排队中：显示排队位置
2. `uploading` - 上传中：传输文件到 docling
3. `parsing` - 解析中：主要耗时阶段，显示时间估算
4. `packaging` - 打包中：生成知识库文档包
5. `completed` - 完成

**进度估算算法（前端）：**
```typescript
function calculateProgress(task: TaskInfo): number {
  const stageWeights = {
    queued: 0,
    uploading: 5,
    parsing: 75,      // 主要阶段
    packaging: 15,
    completed: 100
  };
  
  const baseProgress = stageWeights[task.stage];
  
  if (task.stage === 'parsing') {
    // 基于已用时间和预估总时间计算
    const elapsed = Date.now() - task.startTime;
    const estimated = task.estimatedDuration;
    const parsingProgress = Math.min(95, (elapsed / estimated) * 100);
    return 5 + (parsingProgress * 0.75);  // 5-80%
  }
  
  return baseProgress;
}
```

### 1.4 取消功能

**点击 [停止跟踪]：**
```
确认弹窗：
"停止跟踪后，解析仍会在后台继续进行（约需 XX 分钟）。
 完成后您可以在「知识库」中查看结果。
 
 [继续跟踪]  [确认停止]"
 
效果：
- 前端停止轮询
- 任务状态变为 "user_abandoned"
- 进度卡片收起，显示"后台解析中..."
```

**点击 [强制终止]（仅管理员/所有者）：**
```
确认弹窗（红色警告）：
"⚠️ 强制终止将立即停止解析进程，此操作不可恢复。
 
 注意：这会中断当前所有正在进行的解析任务（包括其他用户的）。
 
 [取消]  [确认强制终止]"
 
效果：
- 调用 POST /api/knowledge/bigpdf/force-cancel
- 后端执行 docker restart orient-g-docling-1
- 任务状态变为 "force_cancelled"
- 显示"已强制终止"
```

### 1.5 完成通知

**全局 Toast 通知（站点级别）：**
```
┌────────────────────────────────────────┐
│ ✅ 大 PDF 解析完成                      │
│    big.pdf 已完成解析，共生成 XX 个知识片段 │
│    [立即查看]  [稍后处理]                │
└────────────────────────────────────────┘
```

**点击 [立即查看]：**
- 跳转到 `/ai-interaction?workspace=knowledge&package=xxx`
- 或 `/knowledge?folder=big-pdf-big`

**通知触发时机：**
- 轮询检测到 `status="completed"`
- 通过 React Context 推送到全局通知队列
- 显示在页面右上角（类似 Ant Design 的 message/notification）

### 1.6 无响应处理

**启动超时检测：**
```
用户点击 [开始解析]
    ↓
前端设置超时计时器（30 秒）
    ↓
如果 30 秒内没有收到 task_id：
    弹窗："解析服务响应较慢，可能原因：
           1. 服务正在初始化（首次使用需加载模型）
           2. 网络连接不稳定
           
           [重新尝试]  [取消]"
```

## 2. API 设计

### 2.1 新增/修改的 API 端点

```typescript
// 1. 获取系统状态（当前是否有运行中的任务）
GET /api/knowledge/bigpdf/status
Response: {
  has_running_task: boolean;
  running_task?: {
    task_id: string;
    owner: string;
    is_mine: boolean;
    status: string;
    stage: string;
    progress: number;
    estimated_remaining: number;
    file_name: string;
    file_size: number;
    page_count: number;
    started_at: string;
  };
  queue_position?: number;  // 当前用户的排队位置
  queue_length: number;     // 总排队数
}

// 2. 创建解析任务（增强版）
POST /api/knowledge/bigpdf/tasks
Body: {
  file: File;           // 上传的文件
  force: boolean;       // 是否强制开始（取消当前任务）
  queue_if_busy: boolean; // 如果忙是否排队
}
Response: {
  task_id: string;
  status: string;
  estimated_duration: number;  // 预估总时间（秒）
  message: string;             // "任务已创建，预计解析时间 30-45 分钟"
}

// 3. 获取任务详情（增强版）
GET /api/knowledge/bigpdf/tasks/{task_id}
Response: {
  task_id: string;
  status: string;           // queued/running/completed/failed/cancelled/user_abandoned/force_cancelled
  stage: string;            // queued/uploading/parsing/packaging/completed
  progress: number;         // 0-100
  estimated_remaining: number;
  elapsed_time: number;
  file_name: string;
  file_size: number;
  page_count: number;
  docling_task_id?: string; // docling 的异步任务 ID
  result?: {
    package_id: string;
    document_count: number;
    folder_path: string;
  };
  error?: string;
}

// 4. 取消任务（增强版）
POST /api/knowledge/bigpdf/tasks/{task_id}/cancel
Body: {
  force: boolean;  // false=软取消, true=强制终止
}
Response: {
  success: boolean;
  message: string;
  task_status: string;
}

// 5. 强制终止 docling（管理员/所有者）
POST /api/knowledge/bigpdf/force-cancel
Headers: {
  Authorization: Bearer xxx
}
Response: {
  success: boolean;
  message: string;
  restarted_at: string;
}

// 6. 获取队列状态
GET /api/knowledge/bigpdf/queue
Response: {
  running_task?: {
    task_id: string;
    owner: string;
    file_name: string;
    started_at: string;
    estimated_remaining: number;
  };
  queued_tasks: Array<{
    task_id: string;
    owner: string;
    file_name: string;
    queued_at: string;
    position: number;
  }>;
  total_queue_length: number;
}
```

### 2.2 后端实现逻辑

**获取系统状态：**
```python
@router.get("/bigpdf/status")
def get_bigpdf_status(request: Request):
    tenant_id = get_tenant_id(request)
    user = get_current_user(request)
    
    # 1. 检查是否有 running 任务
    running = kb_tasks.get_running_task(tenant_id)
    
    # 2. 检查当前用户是否有排队任务
    my_queued = kb_tasks.get_user_queued_task(tenant_id, user.username)
    
    # 3. 获取队列长度
    queue_length = kb_tasks.get_queue_length(tenant_id)
    
    return {
        "has_running_task": running is not None,
        "running_task": {
            ...,
            "is_mine": running.owner == user.username,
        } if running else None,
        "queue_position": my_queued.position if my_queued else None,
        "queue_length": queue_length,
    }
```

**强制终止：**
```python
@router.post("/bigpdf/force-cancel")
def force_cancel_docling(request: Request):
    user = get_current_user(request)
    tenant_id = get_tenant_id(request)
    
    # 1. 权限检查：管理员或任务所有者
    running = kb_tasks.get_running_task(tenant_id)
    if not running:
        raise HTTPException(404, "没有运行中的任务")
    
    if not (user.is_admin or running.owner == user.username):
        raise HTTPException(403, "无权操作")
    
    # 2. 记录操作日志
    logger.warning(f"User {user.username} force-cancelled docling task {running.task_id}")
    
    # 3. 标记任务状态
    kb_tasks.update_task_status(
        tenant_id, 
        running.task_id, 
        status="force_cancelled",
        detail=f"Force cancelled by {user.username}"
    )
    
    # 4. 执行强制终止
    try:
        import subprocess
        subprocess.run(
            ["docker", "restart", "orient-g-docling-1"], 
            check=True, 
            timeout=30
        )
        return {
            "success": True,
            "message": "已强制终止解析进程，docling 容器正在重启",
            "restarted_at": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Failed to restart docling: {e}")
        raise HTTPException(500, f"终止失败: {e}")
```

## 3. 数据库变更

### 3.1 kb_tasks 表增强

```sql
-- 新增字段（如果不存在）
ALTER TABLE kb_tasks ADD COLUMN IF NOT EXISTS file_name VARCHAR(255);
ALTER TABLE kb_tasks ADD COLUMN IF NOT EXISTS file_size BIGINT;
ALTER TABLE kb_tasks ADD COLUMN IF NOT EXISTS page_count INTEGER;
ALTER TABLE kb_tasks ADD COLUMN IF NOT EXISTS docling_task_id VARCHAR(255);
ALTER TABLE kb_tasks ADD COLUMN IF NOT EXISTS estimated_duration INTEGER;  -- 预估时间（秒）
ALTER TABLE kb_tasks ADD COLUMN IF NOT EXISTS started_at TIMESTAMP;
ALTER TABLE kb_tasks ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP;
ALTER TABLE kb_tasks ADD COLUMN IF NOT EXISTS result_package_id VARCHAR(255);
ALTER TABLE kb_tasks ADD COLUMN IF NOT EXISTS cancelled_by VARCHAR(100);  -- 取消者用户名
ALTER TABLE kb_tasks ADD COLUMN IF NOT EXISTS cancel_type VARCHAR(20);    -- soft/force/user_abandoned
```

### 3.2 新增索引

```sql
-- 加速查询运行中任务
CREATE INDEX IF NOT EXISTS idx_kb_tasks_status_kind 
ON kb_tasks(tenant_id, status, kind) 
WHERE status IN ('queued', 'running');

-- 加速查询用户的任务
CREATE INDEX IF NOT EXISTS idx_kb_tasks_owner 
ON kb_tasks(tenant_id, owner_username, created_at DESC);
```

## 4. 前端组件设计

### 4.1 全局状态管理

```typescript
// stores/bigpdfStore.ts
interface BigpdfState {
  // 当前活跃任务
  activeTask: {
    taskId: string;
    status: string;
    stage: string;
    progress: number;
    fileName: string;
    estimatedRemaining: number;
  } | null;
  
  // 全局通知队列
  notifications: Array<{
    id: string;
    type: 'success' | 'info' | 'warning';
    title: string;
    message: string;
    action?: {
      label: string;
      onClick: () => void;
    };
  }>;
  
  // 操作
  setActiveTask: (task: TaskInfo) => void;
  clearActiveTask: () => void;
  addNotification: (notification: Notification) => void;
  removeNotification: (id: string) => void;
}
```

### 4.2 主要组件

```typescript
// components/BigpdfProgressCard.tsx
// 进度卡片（可折叠）

// components/BigpdfUploadModal.tsx
// 上传弹窗（含预估信息）

// components/BigpdfQueueStatus.tsx
// 队列状态展示

// components/BigpdfCancelModal.tsx
// 取消确认弹窗（软取消/强制终止）

// components/GlobalNotification.tsx
// 全局通知组件（挂载在 Layout 上）

// hooks/useBigpdfTask.ts
// 任务管理 Hook（轮询、状态管理）

// hooks/useDoclingStatus.ts
// Docling 状态查询 Hook
```

### 4.3 轮询策略

```typescript
// hooks/useBigpdfTask.ts
function useBigpdfTask(taskId: string) {
  const [task, setTask] = useState<TaskInfo | null>(null);
  const [isPolling, setIsPolling] = useState(true);
  
  useEffect(() => {
    if (!taskId || !isPolling) return;
    
    const poll = async () => {
      try {
        const data = await fetchTaskStatus(taskId);
        setTask(data);
        
        // 检测完成
        if (data.status === 'completed') {
          setIsPolling(false);
          // 推送全局通知
          pushNotification({
            type: 'success',
            title: '大 PDF 解析完成',
            message: `${data.file_name} 已完成解析`,
            action: {
              label: '立即查看',
              onClick: () => router.push(`/ai-interaction?workspace=knowledge&package=${data.result.package_id}`),
            },
          });
        }
        
        // 检测失败/取消
        if (['failed', 'cancelled', 'force_cancelled'].includes(data.status)) {
          setIsPolling(false);
        }
      } catch (e) {
        console.error('Poll error:', e);
      }
    };
    
    // 初始查询
    poll();
    
    // 定时轮询（页面可见时）
    const interval = setInterval(() => {
      if (document.visibilityState === 'visible') {
        poll();
      }
    }, 5000);  // 5 秒轮询
    
    return () => clearInterval(interval);
  }, [taskId, isPolling]);
  
  return { task, isPolling, stopPolling: () => setIsPolling(false) };
}
```

## 5. 知识库自动组织

### 5.1 解析完成后的处理

```python
# backend/services/bigpdf_tasks.py

def process_bigpdf_task(tenant_id, task_id, owner_username, is_cancelled=None):
    # ... 解析逻辑 ...
    
    # 解析完成后，自动创建知识库文件夹
    if res and not (is_cancelled and is_cancelled()):
        package_id = create_rag_package(...)
        
        # 自动创建知识库文件夹
        folder_name = f"大PDF-{title[:50]}"  # 截断避免过长
        folder = kb_documents.create_folder(
            tenant_id=tenant_id,
            owner_username=owner_username,
            name=folder_name,
            parent_path="/",  # 放在根目录或"私有知识库"下
            auto_created=True,
        )
        
        # 将解析结果关联到文件夹
        kb_documents.move_to_folder(
            tenant_id=tenant_id,
            doc_ids=[doc_id for doc_id in generated_docs],
            folder_path=folder.path,
        )
        
        # 更新任务结果
        kb_tasks.update_task_result(
            tenant_id, 
            task_id,
            package_id=package_id,
            folder_path=folder.path,
        )
```

### 5.2 文件夹结构

```
私有知识库/
├── 大PDF-财务报表2024.pdf/          # 自动创建
│   ├── 第1章-概述.md
│   ├── 第2章-财务数据.md
│   └── ...
├── 大PDF-项目计划书.pdf/
│   └── ...
└── ...
```

## 6. 多用户排队逻辑

### 6.1 队列规则

```
1. 系统同时只能处理 1 个大 PDF 任务（docling 单线程限制）
2. 新任务默认进入队列（FIFO）
3. 用户可以选择：
   a. 排队等待
   b. 取消自己的排队任务
   c. 管理员/所有者可以强制终止当前任务
4. 队列对用户透明，显示排队位置和预计等待时间
```

### 6.2 实现

```python
# backend/services/kb_tasks.py

def enqueue_bigpdf_task(tenant_id, owner_username, file_info):
    """添加大 PDF 任务到队列"""
    
    # 1. 检查是否有运行中的任务
    running = get_running_task(tenant_id)
    
    # 2. 创建任务（状态为 queued 或 running）
    if running:
        status = 'queued'
        position = get_queue_length(tenant_id) + 1
    else:
        status = 'running'
        position = 0
    
    task_id = generate_task_id()
    create_task(
        tenant_id=tenant_id,
        task_id=task_id,
        kind='bigpdf',
        status=status,
        owner_username=owner_username,
        payload={
            'file_name': file_info.name,
            'file_size': file_info.size,
            'page_count': file_info.page_count,
            'estimated_duration': estimate_duration(file_info),
        },
    )
    
    return {
        'task_id': task_id,
        'status': status,
        'position': position,
    }

def estimate_duration(file_info):
    """估算解析时间"""
    # 基于历史数据的简单估算
    # 约 3 分钟/MB，最少 5 分钟
    size_mb = file_info.size / (1024 * 1024)
    duration = max(300, size_mb * 180)  # 秒
    return int(duration)
```

## 7. 实施计划

### Phase 1: 后端基础（1-2 天）
- [ ] 增强 kb_tasks 表结构
- [ ] 实现状态查询 API
- [ ] 实现强制终止 API
- [ ] 实现队列管理逻辑
- [ ] 实现知识库自动组织

### Phase 2: 前端核心（2-3 天）
- [ ] 全局状态管理（Zustand）
- [ ] 进度卡片组件
- [ ] 上传弹窗（含预估）
- [ ] 取消功能（软/硬）
- [ ] 全局通知组件

### Phase 3: 流程整合（1-2 天）
- [ ] 页面状态检查（进入时）
- [ ] 轮询策略优化
- [ ] 完成跳转逻辑
- [ ] 多用户排队 UI

### Phase 4: 测试优化（1-2 天）
- [ ] 各种场景测试
- [ ] 性能优化
- [ ] 边界情况处理

**总计：5-9 天**

---

## 8. 需要确认的技术细节

1. **文件页数读取**：前端用 pdf.js 读取页数是否需要额外加载？是否影响上传体验？

2. **全局通知持久化**：用户刷新页面后，未读通知是否保留？（建议用 localStorage）

3. **强制终止的恢复时间**：docling 容器重启后，模型需要重新加载，首次请求会变慢（30-60 秒），是否需要提示？

4. **队列任务的持久化**：用户关闭浏览器后，排队任务是否保留？（建议保留，用户回来后可以继续查看）

5. **知识库文件夹权限**：自动创建的文件夹是否只有上传者可见？还是团队可见？

确认后我可以开始 Phase 1 的实现。