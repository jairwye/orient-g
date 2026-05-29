"use client";

import { useCallback, useEffect } from "react";
import { useBigpdfStore, type BigpdfTaskInfo } from "../stores/bigpdfStore";
import { getAuthHeaders, AUTH_TOKEN_KEY } from "../lib/auth";
import { useSmartPoll } from "../lib/smartPoll";
import {
  resolveBigpdfUiState,
} from "../lib/bigpdfTaskUtils";

export { normalizeBigpdfTaskStage } from "../lib/bigpdfTaskUtils";

interface UseBigpdfTaskOptions {
  taskId: string | null;
  enabled?: boolean;
  onComplete?: (task: BigpdfTaskInfo) => void;
  onError?: (task: BigpdfTaskInfo) => void;
  onCancel?: (task: BigpdfTaskInfo) => void;
}

function mapTaskFromDetail(raw: {
  task_id?: string;
  status?: string;
  stage?: string;
  progress?: number;
  file_name?: string | null;
  file_size?: number | null;
  page_count?: number | null;
  estimated_remaining?: number;
  elapsed_time?: number;
  docling_task_id?: string | null;
  display_label?: string | null;
  is_processing?: boolean;
  queue_position?: number | null;
  is_waiting_for_slot?: boolean;
  result?: {
    package_id?: string;
    document_count?: number;
    folder_path?: string;
  } | null;
  error?: string | null;
}): BigpdfTaskInfo {
  const status = (raw.status === "done" ? "completed" : raw.status || "queued") as BigpdfTaskInfo["status"];
  const ui = resolveBigpdfUiState({
    taskId: raw.task_id!,
    status,
    stage: raw.stage || "queued",
    doclingTaskId: raw.docling_task_id,
    queuePosition: raw.queue_position,
  });
  const stage = (
    raw.display_label ? (raw.stage || ui.displayStage) : ui.displayStage
  ) as BigpdfTaskInfo["stage"];
  const effectiveStatus =
    ui.isProcessing && status === "queued" ? ("running" as BigpdfTaskInfo["status"]) : status;
  return {
    taskId: raw.task_id!,
    status: effectiveStatus,
    stage,
    progress: raw.progress ?? 0,
    fileName: raw.file_name?.trim() || "未知文件",
    fileSize: raw.file_size ?? 0,
    pageCount: raw.page_count ?? 0,
    estimatedRemaining: raw.estimated_remaining ?? 0,
    elapsedTime: raw.elapsed_time ?? 0,
    owner: "",
    isMine: true,
    doclingTaskId: raw.docling_task_id ?? undefined,
    displayLabel: raw.display_label || ui.displayLabel,
    isProcessing: raw.is_processing ?? ui.isProcessing,
    queuePosition: raw.queue_position ?? null,
    isWaitingForSlot: raw.is_waiting_for_slot ?? ui.isWaitingForSlot,
    result: raw.result?.package_id
      ? {
          packageId: raw.result.package_id,
          documentCount: raw.result.document_count ?? 0,
          folderPath: raw.result.folder_path ?? "",
        }
      : undefined,
    error: raw.error ?? undefined,
  };
}

export function useBigpdfTask(options: UseBigpdfTaskOptions) {
  const { taskId, enabled = true, onComplete, onError, onCancel } = options;

  const setActiveTask = useBigpdfStore((s) => s.setActiveTask);
  const updateActiveTask = useBigpdfStore((s) => s.updateActiveTask);

  const load = useCallback(async () => {
    if (!taskId) throw new Error("No task ID provided");
    // 未登录时不发请求，避免 401 风暴
    if (typeof window !== "undefined" && !sessionStorage.getItem(AUTH_TOKEN_KEY)) {
      throw new Error("not authenticated");
    }
    const res = await fetch(
      `/api/knowledge/bigpdf/tasks/${encodeURIComponent(taskId)}/detail`,
      {
        credentials: "include",
        headers: getAuthHeaders(),
      }
    );
    if (!res.ok) throw new Error("任务查询失败");
    const raw = (await res.json().catch(() => ({}))) as {
      task_id?: string;
      status?: string;
      stage?: string;
      progress?: number;
      file_name?: string | null;
      file_size?: number | null;
      page_count?: number | null;
      estimated_remaining?: number;
      elapsed_time?: number;
      docling_task_id?: string | null;
      display_label?: string | null;
      is_processing?: boolean;
      queue_position?: number | null;
      is_waiting_for_slot?: boolean;
      result?: {
        package_id?: string;
        document_count?: number;
        folder_path?: string;
      } | null;
      error?: string | null;
    };
    if (!raw?.task_id) throw new Error("任务查询返回无效");
    return mapTaskFromDetail(raw);
  }, [taskId]);

  const { data: task, setData: setTask, phase, errorCount, trigger } = useSmartPoll<BigpdfTaskInfo>({
    enabled: enabled && Boolean(taskId),
    pollKey: taskId,
    load,
    isTerminal: (data) =>
      data.status === "completed" ||
      data.status === "failed" ||
      data.status === "cancelled" ||
      data.status === "force_cancelled" ||
      data.status === "user_abandoned",
    isActive: (data) =>
      !(
        data.status === "completed" ||
        data.status === "failed" ||
        data.status === "cancelled" ||
        data.status === "force_cancelled" ||
        data.status === "user_abandoned"
      ),
    activeMs: 2500,
    stableMs: 20000,
    errorMaxMs: 60000,
    errorCooldownAfter: 3,
    errorCooldownMs: 120000,
  });

  // Sync task to store and persist task ID
  const persistTaskId = useBigpdfStore((s) => s.persistTaskId);
  useEffect(() => {
    if (task) {
      setActiveTask(task);
      persistTaskId(task.taskId);
    }
  }, [task, setActiveTask, persistTaskId]);

  // Terminal callbacks only — 站内提醒由 useBigpdfCompletionFeed 统一推送（支持连续上传/离开页面）
  useEffect(() => {
    if (!task) return;

    if (task.status === "completed") {
      onComplete?.(task);
    } else if (task.status === "failed") {
      onError?.(task);
    } else if (task.status === "cancelled" || task.status === "force_cancelled") {
      onCancel?.(task);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [task?.status, task?.taskId]);

  const cancelTask = useCallback(
    async (force = false) => {
      if (!taskId) return { success: false, message: "无任务" };
      // 未登录时不发请求
      if (typeof window !== "undefined" && !sessionStorage.getItem(AUTH_TOKEN_KEY)) {
        return { success: false, message: "not authenticated" };
      }
      try {
        const res = await fetch(
          `/api/knowledge/bigpdf/tasks/${encodeURIComponent(taskId)}/cancel`,
          {
            method: "POST",
            credentials: "include",
            headers: {
              ...getAuthHeaders(),
              "Content-Type": "application/json",
            },
            body: JSON.stringify({ force }),
          }
        );
        const data = (await res.json().catch(() => ({}))) as {
          success?: boolean;
          message?: string;
          task_status?: string;
        };
        if (!res.ok) throw new Error(data.message || "取消失败");

        // Update local state
        if (data.task_status) {
          updateActiveTask({ status: data.task_status as BigpdfTaskInfo["status"] });
        }
        return { success: true, message: data.message || "已取消" };
      } catch (e) {
        const message = e instanceof Error ? e.message : "取消失败";
        return { success: false, message };
      }
    },
    [taskId, updateActiveTask]
  );

  const abandonTask = useCallback(() => {
    if (!task) return;
    updateActiveTask({ status: "user_abandoned" });
    setActiveTask(null);
    persistTaskId(null);
  }, [task, updateActiveTask, setActiveTask, persistTaskId]);

  // Clear persisted task ID on terminal states
  useEffect(() => {
    if (!task) return;
    if (
      task.status === "completed" ||
      task.status === "failed" ||
      task.status === "cancelled" ||
      task.status === "force_cancelled" ||
      task.status === "user_abandoned"
    ) {
      persistTaskId(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [task?.status, task?.taskId]);

  return {
    task,
    phase,
    errorCount,
    isLoading:
      enabled &&
      Boolean(taskId) &&
      !task &&
      phase !== "stopped" &&
      phase !== "cooldown",
    isTerminal:
      task?.status === "completed" ||
      task?.status === "failed" ||
      task?.status === "cancelled" ||
      task?.status === "force_cancelled" ||
      task?.status === "user_abandoned",
    cancelTask,
    abandonTask,
    refresh: trigger,
    setTask,
  };
}
