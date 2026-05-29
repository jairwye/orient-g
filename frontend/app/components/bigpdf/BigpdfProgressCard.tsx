"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp, FileText, Clock, AlertTriangle, CheckCircle, XCircle, Loader2 } from "lucide-react";
import { CHART_POSITIVE_CLASS } from "../../lib/business_chart_colors";
import { useBigpdfStore, calculateProgress, formatDuration, type BigpdfTaskInfo } from "../../stores/bigpdfStore";

interface BigpdfProgressCardProps {
  task?: BigpdfTaskInfo | null;
  onCancel?: () => void;
  onAbandon?: () => void;
  onForceCancel?: () => void;
  className?: string;
}

export function BigpdfProgressCard({
  task: externalTask,
  onCancel,
  onAbandon,
  onForceCancel,
  className = "",
}: BigpdfProgressCardProps) {
  const storeTask = useBigpdfStore((s) => s.activeTask);
  const isCollapsed = useBigpdfStore((s) => s.isProgressCardCollapsed);
  const setCollapsed = useBigpdfStore((s) => s.setProgressCardCollapsed);

  const task = externalTask ?? storeTask;
  const [showForceConfirm, setShowForceConfirm] = useState(false);
  const [showAbandonConfirm, setShowAbandonConfirm] = useState(false);

  if (!task) return null;

  const progress = calculateProgress(task);
  const isTerminal =
    task.status === "completed" ||
    task.status === "failed" ||
    task.status === "cancelled" ||
    task.status === "force_cancelled" ||
    task.status === "user_abandoned";

  const stageLabels: Record<string, string> = {
    queued: "排队中",
    uploading: "上传中",
    running: "解析中",
    parsing: "解析中",
    packaging: "打包中",
    completed: "已完成",
  };

  const stageText =
    task.displayLabel ||
    stageLabels[task.stage] ||
    (task.isProcessing ? "解析中" : task.status);

  const statusConfig: Record<
    string,
    { icon: React.ReactNode; color: string; bgColor: string }
  > = {
    queued: {
      icon: <Clock className="h-4 w-4" />,
      color: "text-amber-400",
      bgColor: "bg-amber-500",
    },
    running: {
      icon: <Loader2 className="h-4 w-4 animate-spin" />,
      color: "text-blue-400",
      bgColor: "bg-blue-500",
    },
    parsing: {
      icon: <Loader2 className="h-4 w-4 animate-spin" />,
      color: "text-blue-400",
      bgColor: "bg-blue-500",
    },
    packaging: {
      icon: <Loader2 className="h-4 w-4 animate-spin" />,
      color: "text-purple-400",
      bgColor: "bg-purple-500",
    },
    completed: {
      icon: <CheckCircle className="h-4 w-4" />,
      color: CHART_POSITIVE_CLASS.statusText,
      bgColor: CHART_POSITIVE_CLASS.statusBg,
    },
    failed: {
      icon: <XCircle className="h-4 w-4" />,
      color: "text-red-400",
      bgColor: "bg-red-500",
    },
    cancelled: {
      icon: <XCircle className="h-4 w-4" />,
      color: "text-zinc-400",
      bgColor: "bg-zinc-500",
    },
    force_cancelled: {
      icon: <AlertTriangle className="h-4 w-4" />,
      color: "text-red-400",
      bgColor: "bg-red-500",
    },
    user_abandoned: {
      icon: <XCircle className="h-4 w-4" />,
      color: "text-zinc-400",
      bgColor: "bg-zinc-500",
    },
  };

  const config = statusConfig[task.isProcessing ? "parsing" : task.stage] || statusConfig[task.status] || statusConfig.running;

  return (
    <div
      className={`rounded-lg border border-zinc-800 bg-zinc-950/80 shadow-lg backdrop-blur-sm ${className}`}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3">
        <div className="flex items-center gap-2">
          <FileText className="h-4 w-4 text-zinc-400" />
          <span className="text-sm font-medium text-zinc-200 truncate max-w-[200px]">
            {task.fileName}
          </span>
          <span className={`flex items-center gap-1 text-xs ${config.color}`}>
            {config.icon}
            {stageText}
          </span>
        </div>
        <button
          type="button"
          onClick={() => setCollapsed(!isCollapsed)}
          className="text-zinc-400 hover:text-zinc-200 transition-colors"
          aria-label={isCollapsed ? "展开" : "折叠"}
        >
          {isCollapsed ? (
            <ChevronDown className="h-4 w-4" />
          ) : (
            <ChevronUp className="h-4 w-4" />
          )}
        </button>
      </div>

      {/* Expanded content */}
      {!isCollapsed && (
        <div className="px-4 pb-4 space-y-3">
          {/* Progress bar */}
          <div className="space-y-1">
            <div className="flex justify-between text-xs text-zinc-400">
              <span>进度</span>
              <span>{Math.round(progress)}%</span>
            </div>
            <div className="h-2 w-full rounded-full bg-zinc-800 overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-500 ${config.bgColor}`}
                style={{ width: `${Math.max(0, Math.min(100, progress))}%` }}
              />
            </div>
          </div>

          {/* Info grid */}
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="text-zinc-500">
              页数：<span className="text-zinc-300">{task.pageCount} 页</span>
            </div>
            <div className="text-zinc-500">
              任务ID：
              <span className="font-mono text-zinc-400">{task.taskId}</span>
            </div>
          </div>

          {/* Error message */}
          {task.error && (
            <div className="text-xs text-red-400 bg-red-950/30 rounded px-2 py-1.5">
              {task.error}
            </div>
          )}

          {/* Result */}
          {task.status === "completed" && task.result && (
            <div className={`text-xs rounded px-2 py-1.5 ${CHART_POSITIVE_CLASS.resultBox}`}>
              已生成 {task.result.documentCount} 个知识片段
            </div>
          )}

          {/* Actions */}
          {!isTerminal && (
            <div className="flex flex-wrap gap-2 pt-1">
              <button
                type="button"
                onClick={() => setShowAbandonConfirm(true)}
                className="rounded border border-zinc-700 bg-zinc-800 px-2.5 py-1 text-xs text-zinc-300 hover:bg-zinc-700 transition-colors"
              >
                停止跟踪
              </button>
              {onCancel && (
                <button
                  type="button"
                  onClick={onCancel}
                  className="rounded border border-red-800 bg-red-950 px-2.5 py-1 text-xs text-red-300 hover:bg-red-900 transition-colors"
                >
                  取消任务
                </button>
              )}
              {task.isMine && onForceCancel && (
                <button
                  type="button"
                  onClick={() => setShowForceConfirm(true)}
                  className="rounded border border-red-900 bg-red-950/50 px-2.5 py-1 text-xs text-red-400 hover:bg-red-900/50 transition-colors"
                >
                  强制终止
                </button>
              )}
            </div>
          )}

          {/* Tip */}
          {!isTerminal && (
            <div className="flex items-center justify-between">
              <div className="text-xs text-zinc-500 italic">
                💡 提示：此过程耗时较长，您可以去处理其他工作，完成后我们会通过站内提醒通知您
              </div>
              <a
                href="/ai-interaction"
                className="text-xs text-blue-400 hover:text-blue-300 transition-colors ml-2"
              >
                返回 AI 互动 →
              </a>
            </div>
          )}
        </div>
      )}

      {/* Abandon confirmation */}
      {showAbandonConfirm && (
        <div className="px-4 pb-4">
          <div className="rounded border border-amber-800/50 bg-amber-950/20 p-3 space-y-2">
            <p className="text-xs text-amber-200/80">
              取消后，我们将停止跟踪此任务的进度。解析仍会在后台继续（约需
              {formatDuration(task.estimatedRemaining)}），但完成后不会提醒您。
            </p>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setShowAbandonConfirm(false)}
                className="rounded border border-zinc-700 bg-zinc-800 px-3 py-1 text-xs text-zinc-300 hover:bg-zinc-700"
              >
                继续跟踪
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowAbandonConfirm(false);
                  onAbandon?.();
                }}
                className="rounded border border-amber-800 bg-amber-950 px-3 py-1 text-xs text-amber-300 hover:bg-amber-900"
              >
                确认取消
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Force cancel confirmation */}
      {showForceConfirm && (
        <div className="px-4 pb-4">
          <div className="rounded border border-red-800/50 bg-red-950/20 p-3 space-y-2">
            <p className="text-xs text-red-300">
              ⚠️ 强制终止将立即停止解析进程，此操作不可恢复。
            </p>
            <p className="text-xs text-red-400/80">
              注意：这会中断当前所有正在进行的解析任务（包括其他用户的）。
            </p>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setShowForceConfirm(false)}
                className="rounded border border-zinc-700 bg-zinc-800 px-3 py-1 text-xs text-zinc-300 hover:bg-zinc-700"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowForceConfirm(false);
                  onForceCancel?.();
                }}
                className="rounded border border-red-800 bg-red-950 px-3 py-1 text-xs text-red-300 hover:bg-red-900"
              >
                确认强制终止
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
