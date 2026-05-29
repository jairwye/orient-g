"use client";

import { create } from "zustand";

import type { BigpdfTaskSummary } from "../lib/bigpdfTaskUtils";

export type BigpdfTaskStage =
  | "queued"
  | "uploading"
  | "parsing"
  | "packaging"
  | "completed";

export type BigpdfTaskStatus =
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "cancelled"
  | "user_abandoned"
  | "force_cancelled";

export interface BigpdfTaskInfo {
  taskId: string;
  status: BigpdfTaskStatus;
  stage: BigpdfTaskStage;
  progress: number;
  fileName: string;
  fileSize: number;
  pageCount: number;
  estimatedRemaining: number;
  elapsedTime: number;
  owner: string;
  isMine: boolean;
  startedAt?: string;
  completedAt?: string;
  doclingTaskId?: string;
  result?: {
    packageId: string;
    documentCount: number;
    folderPath: string;
  };
  error?: string;
  displayLabel?: string;
  isProcessing?: boolean;
  queuePosition?: number | null;
  isWaitingForSlot?: boolean;
}

export interface BigpdfSystemStatus {
  hasRunningTask: boolean;
  runningTask?: BigpdfTaskInfo;
  queuePosition?: number;
  queueLength: number;
}

export interface BigpdfNotification {
  id: string;
  type: "success" | "info" | "warning" | "error";
  title: string;
  message: string;
  action?: {
    label: string;
    onClick: () => void;
  };
  createdAt: number;
}

export interface BigpdfQueueTask {
  taskId: string;
  owner: string;
  fileName: string;
  queuedAt: string;
  position: number;
}

export interface BigpdfQueueStatus {
  runningTask?: {
    taskId: string;
    owner: string;
    fileName: string;
    startedAt: string;
    estimatedRemaining: number;
  };
  queuedTasks: BigpdfQueueTask[];
  totalQueueLength: number;
}

export interface BigpdfUploadEstimate {
  fileName: string;
  fileSize: number;
  pageCount: number;
  estimatedDuration: number; // seconds
}

interface BigpdfState {
  // Current active task (being tracked by current user)
  activeTask: BigpdfTaskInfo | null;

  // System status (current running task, queue info)
  systemStatus: BigpdfSystemStatus | null;

  // Queue status
  queueStatus: BigpdfQueueStatus | null;

  // Recent task summaries (from background feed)
  myTaskSummaries: BigpdfTaskSummary[];

  // Global notifications
  notifications: BigpdfNotification[];

  // UI state
  isProgressCardCollapsed: boolean;
  isUploadModalOpen: boolean;

  // Actions
  setActiveTask: (task: BigpdfTaskInfo | null) => void;
  updateActiveTask: (partial: Partial<BigpdfTaskInfo>) => void;
  clearActiveTask: () => void;

  setSystemStatus: (status: BigpdfSystemStatus | null) => void;
  setQueueStatus: (status: BigpdfQueueStatus | null) => void;
  setMyTaskSummaries: (summaries: BigpdfTaskSummary[]) => void;

  addNotification: (notification: Omit<BigpdfNotification, "id" | "createdAt">) => void;
  removeNotification: (id: string) => void;
  clearAllNotifications: () => void;

  setProgressCardCollapsed: (collapsed: boolean) => void;
  setUploadModalOpen: (open: boolean) => void;

  // Session persistence
  persistTaskId: (taskId: string | null) => void;
  getPersistedTaskId: () => string | null;
}

let notificationIdCounter = 0;

export const useBigpdfStore = create<BigpdfState>((set) => ({
  activeTask: null,
  systemStatus: null,
  queueStatus: null,
  myTaskSummaries: [],
  notifications: [],
  isProgressCardCollapsed: false,
  isUploadModalOpen: false,

  setActiveTask: (task) => set({ activeTask: task }),

  updateActiveTask: (partial) =>
    set((state) => ({
      activeTask: state.activeTask
        ? { ...state.activeTask, ...partial }
        : null,
    })),

  clearActiveTask: () => set({ activeTask: null }),

  setSystemStatus: (status) => set({ systemStatus: status }),

  setQueueStatus: (status) => set({ queueStatus: status }),

  setMyTaskSummaries: (summaries) => set({ myTaskSummaries: summaries }),

  addNotification: (notification) =>
    set((state) => ({
      notifications: [
        ...state.notifications,
        {
          ...notification,
          id: `notif_${++notificationIdCounter}_${Date.now()}`,
          createdAt: Date.now(),
        },
      ],
    })),

  removeNotification: (id) =>
    set((state) => ({
      notifications: state.notifications.filter((n) => n.id !== id),
    })),

  clearAllNotifications: () => set({ notifications: [] }),

  setProgressCardCollapsed: (collapsed) =>
    set({ isProgressCardCollapsed: collapsed }),

  setUploadModalOpen: (open) => set({ isUploadModalOpen: open }),

  // Session persistence - save/restore task ID to localStorage
  persistTaskId: (taskId) => {
    if (taskId) {
      localStorage.setItem("bigpdf_active_task_id", taskId);
    } else {
      localStorage.removeItem("bigpdf_active_task_id");
    }
  },

  getPersistedTaskId: () => {
    if (typeof window === "undefined") return null;
    return localStorage.getItem("bigpdf_active_task_id");
  },
}));

// Mock data generators for development/testing
export const mockBigpdfTask = (overrides?: Partial<BigpdfTaskInfo>): BigpdfTaskInfo => ({
  taskId: "t_mock_001",
  status: "running",
  stage: "parsing",
  progress: 45,
  fileName: "big.pdf",
  fileSize: 15728640,
  pageCount: 300,
  estimatedRemaining: 1200,
  elapsedTime: 1080,
  owner: "user1",
  isMine: true,
  startedAt: new Date(Date.now() - 1080 * 1000).toISOString(),
  ...overrides,
});

export const mockSystemStatus = (
  overrides?: Partial<BigpdfSystemStatus>
): BigpdfSystemStatus => ({
  hasRunningTask: true,
  runningTask: mockBigpdfTask(),
  queuePosition: 0,
  queueLength: 1,
  ...overrides,
});

export const mockQueueStatus = (
  overrides?: Partial<BigpdfQueueStatus>
): BigpdfQueueStatus => ({
  runningTask: {
    taskId: "t_mock_001",
    owner: "user1",
    fileName: "big.pdf",
    startedAt: new Date(Date.now() - 1080 * 1000).toISOString(),
    estimatedRemaining: 1200,
  },
  queuedTasks: [
    {
      taskId: "t_mock_002",
      owner: "user2",
      fileName: "another.pdf",
      queuedAt: new Date().toISOString(),
      position: 1,
    },
  ],
  totalQueueLength: 2,
  ...overrides,
});

export const mockNotification = (
  overrides?: Partial<BigpdfNotification>
): BigpdfNotification => ({
  id: "notif_mock_001",
  type: "success",
  title: "大 PDF 解析完成",
  message: "big.pdf 已完成解析，共生成 42 个知识片段",
  createdAt: Date.now(),
  ...overrides,
});

// Progress calculation helper
// Progress is calculated based on stage + time within stage
// queued: 0%, uploading: 0-5%, parsing: 5-90% (time-based), packaging: 90-100%, completed: 100%
export function calculateProgress(task: BigpdfTaskInfo): number {
  if (task.status === "running" && task.stage === "queued") {
    return 10;
  }
  switch (task.stage) {
    case "queued":
      return task.status === "running" ? 10 : 0;

    case "uploading":
      return 2; // Just started, show minimal progress

    case "parsing": {
      // Parsing is the main time-consuming stage (5% to 90%)
      // Calculate based on elapsed time vs estimated total time
      if (task.startedAt && task.estimatedRemaining > 0) {
        const elapsed = task.elapsedTime || 0;
        const total = elapsed + task.estimatedRemaining;
        if (total > 0) {
          // Map 0-100% of parsing time to 5-90% overall progress
          const parsingRatio = Math.min(1, elapsed / total);
          return Math.round(5 + parsingRatio * 85);
        }
      }
      // Fallback: if no time data, show low progress
      return 10;
    }
    
    case "packaging":
      return 95; // Almost done
    
    case "completed":
      return 100;
    
    default:
      return 0;
  }
}

// Format duration helper
export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.ceil(seconds)} 秒`;
  if (seconds < 3600) return `${Math.ceil(seconds / 60)} 分钟`;
  const hours = Math.floor(seconds / 3600);
  const mins = Math.ceil((seconds % 3600) / 60);
  return mins > 0 ? `${hours} 小时 ${mins} 分钟` : `${hours} 小时`;
}

// Format file size helper
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// Estimate duration based on file info
export function estimateDuration(fileSize: number, pageCount: number): number {
  const sizeMb = fileSize / (1024 * 1024);
  // ~3 minutes per MB, minimum 5 minutes
  const duration = Math.max(300, sizeMb * 180);
  // Add time for pages (roughly 10 seconds per page)
  const pageTime = pageCount * 10;
  return Math.max(duration, pageTime);
}
