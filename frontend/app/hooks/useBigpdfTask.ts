"use client";

import { useCallback, useEffect } from "react";
import { useBigpdfStore, type BigpdfTaskInfo } from "../stores/bigpdfStore";
import { getAuthHeaders } from "../lib/auth";
import { useSmartPoll } from "../lib/smartPoll";

interface UseBigpdfTaskOptions {
  taskId: string | null;
  onComplete?: (task: BigpdfTaskInfo) => void;
  onError?: (task: BigpdfTaskInfo) => void;
  onCancel?: (task: BigpdfTaskInfo) => void;
}

export function useBigpdfTask(options: UseBigpdfTaskOptions) {
  const { taskId, onComplete, onError, onCancel } = options;

  const setActiveTask = useBigpdfStore((s) => s.setActiveTask);
  const updateActiveTask = useBigpdfStore((s) => s.updateActiveTask);
  const addNotification = useBigpdfStore((s) => s.addNotification);

  const load = useCallback(async () => {
    if (!taskId) throw new Error("No task ID provided");
    const res = await fetch(
      `/api/knowledge/bigpdf/tasks/${encodeURIComponent(taskId)}`,
      {
        credentials: "include",
        headers: getAuthHeaders(),
      }
    );
    if (!res.ok) throw new Error("任务查询失败");
    const data = (await res.json().catch(() => ({}))) as BigpdfTaskInfo;
    if (!data?.taskId) throw new Error("任务查询返回无效");
    return data;
  }, [taskId]);

  const { data: task, setData: setTask, phase, errorCount, trigger } = useSmartPoll<BigpdfTaskInfo>({
    enabled: Boolean(taskId),
    load,
    isTerminal: (data) =>
      data.status === "completed" ||
      data.status === "failed" ||
      data.status === "cancelled" ||
      data.status === "force_cancelled" ||
      data.status === "user_abandoned",
    isActive: (data) => {
      if (
        data.status === "completed" ||
        data.status === "failed" ||
        data.status === "cancelled" ||
        data.status === "force_cancelled" ||
        data.status === "user_abandoned"
      ) {
        return false;
      }
      const stage = (data.stage || "").toLowerCase();
      if (!stage) return true;
      return stage !== "queued";
    },
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

  // Handle terminal states
  useEffect(() => {
    if (!task) return;

    if (task.status === "completed") {
      onComplete?.(task);
      addNotification({
        type: "success",
        title: "大 PDF 解析完成",
        message: `${task.fileName} 已完成解析${task.result ? `，共生成 ${task.result.documentCount} 个知识片段` : ""}`,
        action: task.result
          ? {
              label: "立即查看",
              onClick: () => {
                window.location.href = `/ai-interaction?workspace=knowledge&package=${task.result!.packageId}`;
              },
            }
          : undefined,
      });
    } else if (task.status === "failed") {
      onError?.(task);
      addNotification({
        type: "error",
        title: "大 PDF 解析失败",
        message: task.error || `${task.fileName} 解析失败`,
      });
    } else if (
      task.status === "cancelled" ||
      task.status === "force_cancelled"
    ) {
      onCancel?.(task);
      addNotification({
        type: "warning",
        title: "大 PDF 解析已取消",
        message: `${task.fileName} 已取消解析`,
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [task?.status, task?.taskId]);

  const cancelTask = useCallback(
    async (force = false) => {
      if (!taskId) return { success: false, message: "无任务" };
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
    isLoading: phase === "polling" || phase === "idle",
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
