"use client";

import { useCallback, useEffect, useRef } from "react";
import { getAuthHeaders, AUTH_TOKEN_KEY } from "../lib/auth";
import {
  isActiveBigpdfStatus,
  isTerminalBigpdfStatus,
  mapListItemToSummary,
  markBigpdfTaskNotified,
  normalizeBigpdfStatus,
  wasBigpdfTaskNotified,
  type BigpdfTaskSummary,
} from "../lib/bigpdfTaskUtils";
import { useBigpdfStore } from "../stores/bigpdfStore";

type ListItem = {
  task_id: string;
  status: string;
  stage: string;
  progress?: number;
  detail?: string | null;
  file_name?: string | null;
  result_package_id?: string | null;
  updated_at?: string | null;
  docling_task_id?: string | null;
};

function notifyTerminalTask(
  summary: BigpdfTaskSummary,
  addNotification: ReturnType<typeof useBigpdfStore.getState>["addNotification"],
) {
  if (wasBigpdfTaskNotified(summary.taskId)) return;
  markBigpdfTaskNotified(summary.taskId);

  if (summary.status === "completed") {
    addNotification({
      type: "success",
      title: "大 PDF 解析完成",
      message: `${summary.fileName} 已完成解析`,
      action: summary.resultPackageId
        ? {
            label: "立即查看",
            onClick: () => {
              window.location.href = `/ai-interaction?workspace=knowledge&package=${summary.resultPackageId}`;
            },
          }
        : {
            label: "查看进度",
            onClick: () => {
              window.location.href = `/utils/pdf-knowledge?task_id=${encodeURIComponent(summary.taskId)}`;
            },
          },
    });
    return;
  }

  if (summary.status === "failed") {
    addNotification({
      type: "error",
      title: "大 PDF 解析失败",
      message: `${summary.fileName} 解析失败`,
      action: {
        label: "查看详情",
        onClick: () => {
          window.location.href = `/utils/pdf-knowledge?task_id=${encodeURIComponent(summary.taskId)}`;
        },
      },
    });
    return;
  }

  if (summary.status === "cancelled" || summary.status === "force_cancelled") {
    addNotification({
      type: "warning",
      title: "大 PDF 解析已取消",
      message: `${summary.fileName} 已取消解析`,
    });
  }
}

export function useBigpdfCompletionFeed(options?: { pollIntervalMs?: number; enabled?: boolean }) {
  const pollIntervalMs = options?.pollIntervalMs ?? 8000;
  const enabled = options?.enabled ?? true;

  const addNotification = useBigpdfStore((s) => s.addNotification);
  const setMyTaskSummaries = useBigpdfStore((s) => s.setMyTaskSummaries);

  const statusByTaskRef = useRef<Map<string, string>>(new Map());
  const seededRef = useRef(false);
  const hadActiveTasksRef = useRef(false);
  const inFlightRef = useRef(false);
  const authLostRef = useRef(false);

  const poll = useCallback(async () => {
    if (!enabled) return;
    if (inFlightRef.current) return;
    if (authLostRef.current) return;
    if (typeof window !== "undefined" && !sessionStorage.getItem(AUTH_TOKEN_KEY)) return;

    inFlightRef.current = true;
    try {
      const res = await fetch("/api/knowledge/bigpdf/tasks?limit=20", {
        credentials: "include",
        headers: getAuthHeaders(),
      });
      if (res.status === 401) {
        authLostRef.current = true;
        return;
      }
      if (!res.ok) return;

      const data = (await res.json().catch(() => ({}))) as { items?: ListItem[] };
      const items = Array.isArray(data.items) ? data.items : [];
      const summaries = items.map(mapListItemToSummary);
      setMyTaskSummaries(summaries);

      const activeCount = summaries.filter((s) => isActiveBigpdfStatus(s.status)).length;
      if (seededRef.current && hadActiveTasksRef.current && activeCount === 0) {
        addNotification({
          type: "info",
          title: "大 PDF 队列已全部处理完成",
          message: "您提交的任务均已结束，可以继续上传或前往知识库查看结果。",
          action: {
            label: "打开工具页",
            onClick: () => {
              window.location.href = "/utils/pdf-knowledge";
            },
          },
        });
      }
      hadActiveTasksRef.current = activeCount > 0;

      for (const item of items) {
        const taskId = item.task_id;
        const status = normalizeBigpdfStatus(item.status);
        const prev = statusByTaskRef.current.get(taskId);

        if (!seededRef.current) {
          statusByTaskRef.current.set(taskId, status);
          continue;
        }

        if (prev && prev !== status && isTerminalBigpdfStatus(status)) {
          notifyTerminalTask(mapListItemToSummary(item), addNotification);
        }
        statusByTaskRef.current.set(taskId, status);
      }

      seededRef.current = true;
    } finally {
      inFlightRef.current = false;
    }
  }, [addNotification, enabled, setMyTaskSummaries]);

  useEffect(() => {
    if (!enabled) return;

    void poll();
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") void poll();
    }, pollIntervalMs);

    const onVisible = () => void poll();
    document.addEventListener("visibilitychange", onVisible);

    return () => {
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [enabled, poll, pollIntervalMs]);
}
