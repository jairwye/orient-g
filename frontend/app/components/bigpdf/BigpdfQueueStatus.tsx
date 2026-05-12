"use client";

import { Clock, Users, FileText, Loader2 } from "lucide-react";
import { useBigpdfStore, formatDuration, type BigpdfQueueStatus } from "../../stores/bigpdfStore";

interface BigpdfQueueStatusProps {
  queueStatus?: BigpdfQueueStatus | null;
  className?: string;
}

export function BigpdfQueueStatus({
  queueStatus: externalQueueStatus,
  className = "",
}: BigpdfQueueStatusProps) {
  const storeQueueStatus = useBigpdfStore((s) => s.queueStatus);
  const queueStatus = externalQueueStatus ?? storeQueueStatus;

  if (!queueStatus) {
    return (
      <div className={`rounded-lg border border-zinc-800 bg-zinc-950/40 p-4 ${className}`}>
        <div className="flex items-center gap-2 text-sm text-zinc-500">
          <Loader2 className="h-4 w-4 animate-spin" />
          加载队列状态...
        </div>
      </div>
    );
  }

  const { runningTask, queuedTasks, totalQueueLength } = queueStatus;

  return (
    <div className={`rounded-lg border border-zinc-800 bg-zinc-950/40 p-4 ${className}`}>
      <div className="flex items-center gap-2 mb-3">
        <Users className="h-4 w-4 text-zinc-400" />
        <h3 className="text-sm font-medium text-zinc-200">队列状态</h3>
        <span className="text-xs text-zinc-500">
          （共 {totalQueueLength} 个任务）
        </span>
      </div>

      {/* Running task */}
      {runningTask ? (
        <div className="mb-3 rounded border border-blue-800/30 bg-blue-950/20 p-3">
          <div className="flex items-center gap-2 text-xs text-blue-300 mb-1">
            <Loader2 className="h-3 w-3 animate-spin" />
            <span className="font-medium">正在处理</span>
          </div>
          <div className="flex items-center justify-between text-xs">
            <div className="flex items-center gap-1 text-zinc-400">
              <FileText className="h-3 w-3" />
              <span className="truncate max-w-[150px]">{runningTask.fileName}</span>
            </div>
            <div className="flex items-center gap-1 text-zinc-500">
              <Clock className="h-3 w-3" />
              预计还需 {formatDuration(runningTask.estimatedRemaining)}
            </div>
          </div>
          <div className="mt-1 text-xs text-zinc-600">
            用户：{runningTask.owner}
          </div>
        </div>
      ) : (
        <div className="mb-3 rounded border border-zinc-800/50 bg-zinc-900/30 p-3 text-xs text-zinc-500">
          当前无运行中的任务
        </div>
      )}

      {/* Queued tasks */}
      {queuedTasks.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs text-zinc-500 font-medium">排队中</div>
          <ul className="space-y-1.5">
            {queuedTasks.map((task) => (
              <li
                key={task.taskId}
                className="flex items-center justify-between rounded border border-zinc-800/50 bg-zinc-900/30 px-2.5 py-1.5"
              >
                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono text-zinc-500 w-6">
                    #{task.position}
                  </span>
                  <FileText className="h-3 w-3 text-zinc-600" />
                  <span className="text-xs text-zinc-400 truncate max-w-[120px]">
                    {task.fileName}
                  </span>
                </div>
                <span className="text-xs text-zinc-600">{task.owner}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {queuedTasks.length === 0 && !runningTask && (
        <div className="text-xs text-zinc-600 italic">
          队列为空，可以立即上传新文件
        </div>
      )}
    </div>
  );
}
