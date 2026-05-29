"use client";

import Link from "next/link";
import { Loader2, Clock, CheckCircle, XCircle } from "lucide-react";
import { useBigpdfStore } from "../../stores/bigpdfStore";
import { CHART_POSITIVE_CLASS } from "../../lib/business_chart_colors";
import { isActiveBigpdfStatus } from "../../lib/bigpdfTaskUtils";

const stageLabel: Record<string, string> = {
  queued: "排队中",
  uploading: "上传中",
  parsing: "解析中",
  packaging: "打包中",
  completed: "已完成",
};

interface BigpdfMyTasksPanelProps {
  currentTaskId?: string;
  className?: string;
}

export function BigpdfMyTasksPanel({ currentTaskId, className = "" }: BigpdfMyTasksPanelProps) {
  const summaries = useBigpdfStore((s) => s.myTaskSummaries);
  const active = summaries.filter((s) => isActiveBigpdfStatus(s.status));

  if (active.length === 0) return null;

  return (
    <div className={`rounded-lg border border-zinc-800 bg-zinc-950/40 p-4 ${className}`}>
      <div className="mb-2 text-sm font-medium text-zinc-200">我的解析任务</div>
      <p className="mb-3 text-xs text-zinc-500">
        连续上传时会按队列依次处理；切换任务可查看各自进度，完成后会收到右上角提醒。
      </p>
      <ul className="space-y-2">
        {active.map((task) => {
          const isCurrent = task.taskId === currentTaskId;
          const isQueued = !task.isProcessing && task.stage === "queued";
          return (
            <li
              key={task.taskId}
              className={`flex items-center justify-between gap-2 rounded border px-3 py-2 text-xs ${
                isCurrent
                  ? "border-blue-800/50 bg-blue-950/20"
                  : "border-zinc-800/50 bg-zinc-900/30"
              }`}
            >
              <div className="flex min-w-0 items-center gap-2">
                {isQueued ? (
                  <Clock className="h-3.5 w-3.5 shrink-0 text-amber-400" />
                ) : (
                  <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-blue-400" />
                )}
                <span className="truncate text-zinc-300">{task.fileName}</span>
                <span className="shrink-0 text-zinc-500">
                  {task.displayLabel || stageLabel[task.stage] || task.status}
                </span>
              </div>
              {!isCurrent ? (
                <Link
                  href={`/utils/pdf-knowledge?task_id=${encodeURIComponent(task.taskId)}&name=${encodeURIComponent(task.fileName)}`}
                  className="shrink-0 text-blue-400 hover:text-blue-300"
                >
                  查看
                </Link>
              ) : (
                <span className="shrink-0 text-zinc-500">当前</span>
              )}
            </li>
          );
        })}
      </ul>
      {summaries.some((s) => s.status === "completed") && (
        <div className={`mt-3 flex items-center gap-1 text-xs ${CHART_POSITIVE_CLASS.bannerText}`}>
          <CheckCircle className="h-3 w-3" />
          最近已有任务完成，可在 AI 互动 → 大 PDF 文档包中查看
        </div>
      )}
      {summaries.some((s) => s.status === "failed") && (
        <div className="mt-1 flex items-center gap-1 text-xs text-red-400/80">
          <XCircle className="h-3 w-3" />
          部分任务失败，点击「查看」了解详情
        </div>
      )}
    </div>
  );
}
