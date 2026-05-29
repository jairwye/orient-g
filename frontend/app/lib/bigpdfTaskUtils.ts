import type { BigpdfTaskStage, BigpdfTaskStatus } from "../stores/bigpdfStore";

export type BigpdfTaskSummary = {
  taskId: string;
  status: BigpdfTaskStatus;
  stage: BigpdfTaskStage;
  fileName: string;
  progress: number;
  displayLabel?: string;
  isProcessing?: boolean;
  queuePosition?: number | null;
  isWaitingForSlot?: boolean;
  resultPackageId?: string;
  updatedAt?: string;
};

export function normalizeBigpdfStatus(status: string): BigpdfTaskStatus {
  const s = (status || "queued").toLowerCase();
  if (s === "done") return "completed";
  return s as BigpdfTaskStatus;
}

export function isTerminalBigpdfStatus(status: string): boolean {
  const s = normalizeBigpdfStatus(status);
  return (
    s === "completed" ||
    s === "failed" ||
    s === "cancelled" ||
    s === "force_cancelled" ||
    s === "user_abandoned"
  );
}

export function isActiveBigpdfStatus(status: string): boolean {
  const s = normalizeBigpdfStatus(status);
  return s === "queued" || s === "running";
}

export function normalizeBigpdfTaskStage(
  status: string,
  stage: string,
  doclingTaskId?: string | null,
): BigpdfTaskStage {
  const st = normalizeBigpdfStatus(status);
  const sg = (stage || "queued").toLowerCase();
  if (st === "completed") return "completed";
  if (st === "running" || doclingTaskId) {
    if (sg === "queued" || sg === "running" || !sg) return "parsing";
  }
  if (sg === "running") return "parsing";
  if (sg === "packaging") return "packaging";
  if (sg === "uploading") return "uploading";
  if (sg === "completed") return "completed";
  return "queued";
}

/** 前端兜底：与 backend/services/bigpdf_status.py 规则一致 */
export function resolveBigpdfUiState(input: {
  taskId: string;
  status: string;
  stage: string;
  doclingTaskId?: string | null;
  workerId?: string | null;
  runningTaskId?: string | null;
  queuePosition?: number | null;
}): {
  displayStage: BigpdfTaskStage;
  displayLabel: string;
  isProcessing: boolean;
  isWaitingForSlot: boolean;
} {
  const status = normalizeBigpdfStatus(input.status);
  const displayStage = normalizeBigpdfTaskStage(status, input.stage, input.doclingTaskId);

  if (isTerminalBigpdfStatus(status)) {
    const labels: Record<string, string> = {
      completed: "已完成",
      failed: "失败",
      cancelled: "已取消",
      force_cancelled: "已强制终止",
      user_abandoned: "已停止跟踪",
    };
    return {
      displayStage: displayStage === "queued" ? "completed" : displayStage,
      displayLabel: labels[status] || status,
      isProcessing: false,
      isWaitingForSlot: false,
    };
  }

  const isThisRunning = Boolean(input.runningTaskId && input.runningTaskId === input.taskId);
  const isProcessing =
    isThisRunning ||
    status === "running" ||
    Boolean(input.doclingTaskId) ||
    Boolean(input.workerId) ||
    displayStage === "parsing" ||
    displayStage === "packaging";

  if (isProcessing) {
    const label =
      displayStage === "packaging"
        ? "打包中"
        : input.doclingTaskId
          ? "解析中（Docling）"
          : "解析中";
    return {
      displayStage: displayStage === "queued" ? "parsing" : displayStage,
      displayLabel: label,
      isProcessing: true,
      isWaitingForSlot: false,
    };
  }

  const waitingForSlot = Boolean(input.runningTaskId && input.runningTaskId !== input.taskId);
  const label = waitingForSlot
    ? input.queuePosition
      ? `排队中（第 ${input.queuePosition} 位）`
      : "排队中（等待前序任务）"
    : "排队中（等待调度）";

  return {
    displayStage: "queued",
    displayLabel: label,
    isProcessing: false,
    isWaitingForSlot: waitingForSlot,
  };
}

export function bigpdfDisplayFileName(item: {
  file_name?: string | null;
  detail?: string | null;
}): string {
  const fn = String(item.file_name || "").trim();
  if (fn) return fn;
  const detail = String(item.detail || "").trim();
  if (detail && !detail.startsWith("folder:") && !detail.includes("user_doc:")) {
    return detail;
  }
  return "未知文件";
}

export function mapListItemToSummary(item: {
  task_id: string;
  status: string;
  stage: string;
  progress?: number;
  detail?: string | null;
  file_name?: string | null;
  result_package_id?: string | null;
  updated_at?: string | null;
  docling_task_id?: string | null;
  worker_id?: string | null;
  display_label?: string | null;
  is_processing?: boolean;
  queue_position?: number | null;
  is_waiting_for_slot?: boolean;
}): BigpdfTaskSummary {
  const status = normalizeBigpdfStatus(item.status);
  const ui = resolveBigpdfUiState({
    taskId: item.task_id,
    status: item.status,
    stage: item.stage,
    doclingTaskId: item.docling_task_id,
    workerId: item.worker_id,
    queuePosition: item.queue_position,
  });
  return {
    taskId: item.task_id,
    status,
    stage: (item.display_label ? (item.stage as BigpdfTaskStage) : ui.displayStage),
    fileName: bigpdfDisplayFileName(item),
    progress: item.progress ?? 0,
    displayLabel: item.display_label || ui.displayLabel,
    isProcessing: item.is_processing ?? ui.isProcessing,
    queuePosition: item.queue_position ?? null,
    isWaitingForSlot: item.is_waiting_for_slot ?? ui.isWaitingForSlot,
    resultPackageId: item.result_package_id || undefined,
    updatedAt: item.updated_at || undefined,
  };
}

export const BIGPDF_PENDING_TASKS_KEY = "bigpdf_pending_task_ids";
export const BIGPDF_NOTIFIED_TASKS_KEY = "bigpdf_notified_task_ids";

export function readSessionJsonArray(key: string): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = sessionStorage.getItem(key);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((x) => typeof x === "string") : [];
  } catch {
    return [];
  }
}

export function writeSessionJsonArray(key: string, values: string[]) {
  if (typeof window === "undefined") return;
  sessionStorage.setItem(key, JSON.stringify(values.slice(0, 30)));
}

export function registerPendingBigpdfTask(taskId: string) {
  const ids = readSessionJsonArray(BIGPDF_PENDING_TASKS_KEY);
  if (!ids.includes(taskId)) {
    writeSessionJsonArray(BIGPDF_PENDING_TASKS_KEY, [taskId, ...ids]);
  }
}

export function markBigpdfTaskNotified(taskId: string) {
  const ids = readSessionJsonArray(BIGPDF_NOTIFIED_TASKS_KEY);
  if (!ids.includes(taskId)) {
    writeSessionJsonArray(BIGPDF_NOTIFIED_TASKS_KEY, [taskId, ...ids]);
  }
}

export function wasBigpdfTaskNotified(taskId: string): boolean {
  return readSessionJsonArray(BIGPDF_NOTIFIED_TASKS_KEY).includes(taskId);
}
