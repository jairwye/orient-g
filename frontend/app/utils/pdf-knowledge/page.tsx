"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { getAuthHeaders } from "../../lib/auth";
import { buildAiInteractionHref, buildKnowledgeHref } from "../../lib/kb_scope_capsule";
import { useSmartPoll } from "../../lib/smartPoll";
import { BigpdfProgressCard } from "../../components/bigpdf/BigpdfProgressCard";
import { BigpdfUploadModal } from "../../components/bigpdf/BigpdfUploadModal";
import { BigpdfQueueStatus } from "../../components/bigpdf/BigpdfQueueStatus";
import { GlobalNotification } from "../../components/bigpdf/GlobalNotification";
import { useDoclingStatus } from "../../hooks/useDoclingStatus";
import { useBigpdfTask } from "../../hooks/useBigpdfTask";
import { useBigpdfStore } from "../../stores/bigpdfStore";


type BigPdfTask = {
  task_id: string;
  kind: string;
  status: string;
  stage: string;
  progress: number;
  detail?: string | null;
  result_package_id?: string | null;
};

export default function PdfKnowledgePage() {
  const sp = useSearchParams();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [msg, setMsg] = useState<{ type: "info" | "success" | "error"; text: string } | null>(null);
  const [isPageVisible, setIsPageVisible] = useState(true);
  const [showUploadModal, setShowUploadModal] = useState(false);
  const queryTaskId = useMemo(() => (sp.get("task_id") || "").trim(), [sp]);
  
  // Session persistence: check localStorage for active task on mount
  const [restoredTaskId, setRestoredTaskId] = useState<string | null>(null);
  useEffect(() => {
    // Only restore if no query param task_id is present
    if (queryTaskId) return;
    
    try {
      const persisted = localStorage.getItem("bigpdf_active_task_id");
      if (persisted) {
        setRestoredTaskId(persisted);
        setMsg({ type: "info", text: "已恢复上次未完成的任务进度。" });
      }
    } catch {
      // localStorage not available (e.g., private mode)
    }
  }, [queryTaskId]);
  const shownQueryInfoMsgRef = useRef(false);

  const info = useMemo(() => {
    const from = sp.get("from") || "";
    const name = sp.get("name") || "";
    const sizeMb = sp.get("size_mb") || "";
    const pages = sp.get("pages") || "";
    const reason = sp.get("reason") || "";
    const folderId = (sp.get("folder_id") || "").trim();
    return { from, name, sizeMb, pages, reason, folderId };
  }, [sp]);

  useEffect(() => {
    const update = () => setIsPageVisible(document.visibilityState !== "hidden");
    update();
    document.addEventListener("visibilitychange", update);
    return () => document.removeEventListener("visibilitychange", update);
  }, []);

  // Use new hooks for system status and task tracking
  const { systemStatus, queueStatus, isBusy, myQueuePosition } = useDoclingStatus({
    autoStart: true,
    pollInterval: 10000,
  });

  const taskId = queryTaskId || restoredTaskId || "";
  const {
    data: task,
    setData: setTask,
  } = useSmartPoll<BigPdfTask>({
    enabled: isPageVisible && Boolean(taskId),
    load: async () => {
      const res = await fetch(`/api/knowledge/bigpdf/tasks/${encodeURIComponent(taskId)}`, {
        credentials: "include",
        headers: getAuthHeaders(),
      });
      if (!res.ok) throw new Error("任务查询失败");
      const data = (await res.json().catch(() => ({}))) as BigPdfTask;
      if (!data?.task_id) throw new Error("任务查询返回无效");
      return data;
    },
    isTerminal: (data) => data.status === "completed" || data.status === "done" || data.status === "failed" || data.status === "cancelled",
    isActive: (data) => {
      if (data.status === "completed" || data.status === "done" || data.status === "failed" || data.status === "cancelled") return false;
      const stage = (data.stage || "").toLowerCase();
      if (!stage) return true;
      return !["queued", "queue", "waiting", "pending"].includes(stage);
    },
    activeMs: 2500,
    stableMs: 20000,
    errorMaxMs: 60000,
    errorCooldownAfter: 3,
    errorCooldownMs: 120000,
  });

  // Also use the new hook for task tracking if we have a task ID
  const { task: trackedTask, cancelTask, abandonTask } = useBigpdfTask({
    taskId: taskId || null,
  });

  useEffect(() => {
    if (!queryTaskId) return;
    if (!task?.task_id) return;
    if (shownQueryInfoMsgRef.current) return;
    shownQueryInfoMsgRef.current = true;
    setMsg({ type: "info", text: "已加载任务进度（来自跳转参数）。" });
  }, [queryTaskId, task?.task_id]);

  const handleCancel = async () => {
    if (!task?.task_id) return;
    if (!confirm("确定要取消这个任务吗？")) return;
    setCancelling(true);
    setMsg(null);
    try {
      // Try new cancel API first
      const result = await cancelTask();
      if (result.success) {
        setTask((prev) => prev ? { ...prev, status: "cancelled", stage: "cancelled" } : prev);
        setMsg({ type: "info", text: "任务已取消。" });
      } else {
        // Fallback to old API
        const res = await fetch(`/api/knowledge/bigpdf/tasks/${encodeURIComponent(task.task_id)}/cancel`, {
          method: "POST",
          credentials: "include",
          headers: getAuthHeaders(),
        });
        const data = (await res.json().catch(() => ({}))) as { detail?: string };
        if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "取消失败");
        setTask((prev) => prev ? { ...prev, status: "cancelled", stage: "cancelled" } : prev);
        setMsg({ type: "info", text: "任务已取消。" });
      }
    } catch (e) {
      setMsg({ type: "error", text: e instanceof Error ? e.message : "取消失败" });
    } finally {
      setCancelling(false);
    }
  };

  const handleUpload = async (f: File, options?: { queueIfBusy: boolean }) => {
    setBusy(true);
    setMsg(null);
    try {
      const fd = new FormData();
      fd.append("file", f);
      if (options) {
        fd.append("queue_if_busy", String(options.queueIfBusy));
      }
      const res = await fetch("/api/knowledge/bigpdf/tasks", {
        method: "POST",
        credentials: "include",
        headers: getAuthHeaders(),
        body: fd,
      });
      const data = (await res.json().catch(() => ({}))) as BigPdfTask & { detail?: string };
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "创建任务失败");
      setTask(data);
      setRestoredTaskId(data.task_id);
      useBigpdfStore.getState().persistTaskId(data.task_id);
      setMsg({ type: "success", text: "任务已创建，开始处理…" });
    } catch (e) {
      setMsg({ type: "error", text: e instanceof Error ? e.message : "上传失败" });
    } finally {
      setBusy(false);
    }
  };

  // Convert old task format to new format for the progress card
  const activeTaskForCard = trackedTask || (task ? {
    taskId: task.task_id,
    status: task.status as "running" | "completed" | "failed" | "cancelled" | "user_abandoned" | "force_cancelled" | "queued",
    stage: task.stage as "queued" | "uploading" | "parsing" | "packaging" | "completed",
    progress: task.progress,
    fileName: info.name || "未知文件",
    fileSize: info.sizeMb ? parseInt(info.sizeMb) * 1024 * 1024 : 0,
    pageCount: info.pages ? parseInt(info.pages) : 0,
    estimatedRemaining: 0,
    elapsedTime: 0,
    owner: "",
    isMine: true,
  } : null);

  return (
    <div className="p-6 md:p-8">
      <GlobalNotification />

      <div className="mb-4">
        <Link href="/utils" className="text-sm text-zinc-400 hover:text-zinc-200">
          ← 实用工具
        </Link>
      </div>
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-100">大 PDF 生知识库用文档工具</h1>
        <p className="mt-1 text-sm text-zinc-500">用于处理大 PDF（Docling 解析 → 生成大文档 RAG 包）。</p>
      </div>

      {/* System Status / Queue Info */}
      {isBusy && (
        <div className="mb-4">
          <BigpdfQueueStatus queueStatus={queueStatus} />
        </div>
      )}

      {/* Active Task Progress Card */}
      {activeTaskForCard && (
        <div className="mb-4">
          <BigpdfProgressCard
            task={activeTaskForCard}
            onCancel={handleCancel}
            onAbandon={abandonTask}
          />
        </div>
      )}

      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
        {info.name || info.folderId ? (
          <div className="mb-4 text-sm text-zinc-300">
            {info.name ? (
              <>
                <div className="text-zinc-200">已从「{info.from || "其他入口"}」跳转。</div>
                <div className="mt-2 text-zinc-400">
                  文件：<span className="text-zinc-200">{info.name}</span>
                  {info.sizeMb ? <span className="ml-2">大小：{info.sizeMb}MB</span> : null}
                  {info.pages ? <span className="ml-2">页数：约 {info.pages}</span> : null}
                </div>
                {info.reason ? <div className="mt-2 text-zinc-400">判定原因：{info.reason}</div> : null}
              </>
            ) : null}
            {info.folderId ? (
              <div className={`text-xs text-zinc-400 ${info.name ? "mt-2" : ""}`}>
                关联文件夹：<span className="font-mono text-zinc-200">{info.folderId}</span>（完成后可从知识库该文件夹继续管理）
              </div>
            ) : null}
          </div>
        ) : null}

        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,application/pdf"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            e.target.value = "";
            if (f) handleUpload(f);
          }}
        />

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={() => setShowUploadModal(true)}
            className="rounded border border-zinc-600 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 hover:bg-zinc-700 disabled:opacity-50"
          >
            {busy ? "提交中…" : "上传大 PDF 开始处理"}
          </button>
          {msg && <span className={msg.type === "error" ? "text-red-400 text-sm" : msg.type === "success" ? "text-emerald-400 text-sm" : "text-zinc-400 text-sm"}>{msg.text}</span>}
        </div>

        <div className="mt-4 rounded-lg border border-dashed border-zinc-700 p-5 text-sm text-zinc-500 space-y-2">
          <p>
            <strong className="text-zinc-400">处理流程：</strong>大 PDF 通过 Docling 解析 → 生成结构化知识片段 → 自动归入您的「私人知识库」
          </p>
          <p>
            <strong className="text-zinc-400">自动组织：</strong>解析完成后，系统会自动创建 <code className="bg-zinc-800 px-1 rounded">大PDF-&#123;文件名&#125;</code> 文件夹，所有知识片段按文档结构自动整理
          </p>
          <p>
            <strong className="text-zinc-400">权限说明：</strong>私人知识库仅您自己可见，不会共享给其他用户或进入公共知识库
          </p>
          <p>
            <strong className="text-zinc-400">耗时提示：</strong>大 PDF 解析通常需要较长时间（约 3 分钟/MB），支持排队等待，您可以随时离开页面，完成后会通过站内提醒通知您
          </p>
        </div>

        {/* Legacy task display (keep for backward compatibility) */}
        {task && !activeTaskForCard && (
          <div className="mt-4 rounded-lg border border-zinc-800 bg-zinc-950/40 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
              <div className="text-zinc-200">
                任务：<span className="font-mono text-zinc-300">{task.task_id}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-zinc-400">
                  {task.stage} · {task.progress}%
                </span>
                {(task.status === "queued" || task.status === "running" || task.status === "parsing" || task.status === "packaging") && (
                  <button
                    type="button"
                    disabled={cancelling}
                    onClick={handleCancel}
                    className="rounded border border-red-800 bg-red-950 px-2 py-1 text-xs text-red-300 hover:bg-red-900 disabled:opacity-50"
                  >
                    {cancelling ? "取消中…" : "取消任务"}
                  </button>
                )}
              </div>
            </div>
            <div className="mt-2 h-2 w-full rounded bg-zinc-800">
              <div className="h-2 rounded bg-blue-500" style={{ width: `${Math.max(0, Math.min(100, task.progress || 0))}%` }} />
            </div>
            {task.status === "cancelled" && <div className="mt-3 text-sm text-amber-400">任务已取消。</div>}
            {task.status === "failed" && task.detail && <div className="mt-3 text-sm text-red-400">失败：{task.detail}</div>}
            {task.status === "done" && (
              <div className="mt-3 text-sm text-emerald-400">
                处理完成。RAG 包：<span className="font-mono">{task.result_package_id || "-"}</span>
              </div>
            )}
          </div>
        )}

        <div className="mt-4 flex flex-wrap gap-2">
          <Link
            href={buildKnowledgeHref(info.folderId || null)}
            className="rounded border border-zinc-600 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 hover:bg-zinc-700"
          >
            去知识库页查看 RAG 包
          </Link>
          <Link
            href={buildAiInteractionHref(info.folderId ? { folder_ids: [info.folderId] } : {})}
            className="rounded border border-zinc-600 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 hover:bg-zinc-700"
          >
            返回 AI 互动
          </Link>
        </div>
      </div>

      {/* Upload Modal */}
      <BigpdfUploadModal
        isOpen={showUploadModal}
        onClose={() => setShowUploadModal(false)}
        onUpload={(file, options) => handleUpload(file, options)}
        systemBusy={isBusy}
        currentTaskInfo={systemStatus?.runningTask ? {
          fileName: systemStatus.runningTask.fileName,
          estimatedRemaining: systemStatus.runningTask.estimatedRemaining,
        } : null}
        queuePosition={myQueuePosition}
      />
    </div>
  );
}
