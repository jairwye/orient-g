"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { getAuthHeaders } from "../../lib/auth";
import { buildAiInteractionHref } from "../../lib/kb_scope_capsule";
import { BigpdfProgressCard } from "../../components/bigpdf/BigpdfProgressCard";
import { BigpdfUploadModal } from "../../components/bigpdf/BigpdfUploadModal";
import { BigpdfQueueStatus } from "../../components/bigpdf/BigpdfQueueStatus";
import { BigpdfMyTasksPanel } from "../../components/bigpdf/BigpdfMyTasksPanel";
import { useDoclingStatus } from "../../hooks/useDoclingStatus";
import { useBigpdfTask } from "../../hooks/useBigpdfTask";
import { useBigpdfStore } from "../../stores/bigpdfStore";
import { registerPendingBigpdfTask } from "../../lib/bigpdfTaskUtils";


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
  return (
    <Suspense
      fallback={
        <div className="flex min-h-[40vh] items-center justify-center p-6 md:p-8">
          <span className="text-sm text-zinc-500">加载中…</span>
        </div>
      }
    >
      <PdfKnowledgePageContent />
    </Suspense>
  );
}

export function PdfKnowledgePageContent() {
  const sp = useSearchParams();
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [, setCancelling] = useState(false);
  const [msg, setMsg] = useState<{ type: "info" | "success" | "error"; text: string } | null>(null);
  const [isPageVisible, setIsPageVisible] = useState(true);
  const [showUploadModal, setShowUploadModal] = useState(false);
  const queryTaskId = useMemo(() => (sp.get("task_id") || "").trim(), [sp]);
  const [overrideTaskId, setOverrideTaskId] = useState<string | null>(null);
  const [uploadMeta, setUploadMeta] = useState<{ name: string; sizeMb: number; pages?: number } | null>(null);

  // Session persistence: check localStorage for active task on mount
  const [restoredTaskId, setRestoredTaskId] = useState<string | null>(null);
  useEffect(() => {
    // Only restore if no query param task_id is present and user is authenticated
    if (queryTaskId) return;
    if (typeof window !== "undefined" && !sessionStorage.getItem("orient_g_token")) return;
    
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

  const taskId = overrideTaskId || queryTaskId || restoredTaskId || "";
  const prevTaskIdRef = useRef<string | null>(null);

  const { task: trackedTask, cancelTask, abandonTask, setTask: setTrackedTask, isLoading: taskLoading } = useBigpdfTask({
    taskId: taskId || null,
    enabled: isPageVisible && Boolean(taskId),
  });

  useEffect(() => {
    if (overrideTaskId && queryTaskId === overrideTaskId) {
      setOverrideTaskId(null);
    }
  }, [overrideTaskId, queryTaskId]);

  useEffect(() => {
    if (prevTaskIdRef.current !== null && prevTaskIdRef.current !== taskId) {
      setTrackedTask(undefined);
      useBigpdfStore.getState().clearActiveTask();
    }
    prevTaskIdRef.current = taskId;
  }, [taskId, setTrackedTask]);

  useEffect(() => {
    if (!queryTaskId) return;
    if (!trackedTask?.taskId) return;
    if (shownQueryInfoMsgRef.current) return;
    shownQueryInfoMsgRef.current = true;
    setMsg({ type: "info", text: "已加载任务进度（来自跳转参数）。" });
  }, [queryTaskId, trackedTask?.taskId]);

  const handleCancel = async () => {
    if (!taskId) return;
    if (!confirm("确定要取消这个任务吗？")) return;
    setCancelling(true);
    setMsg(null);
    try {
      const result = await cancelTask();
      if (result.success) {
        setTrackedTask((prev) => prev ? { ...prev, status: "cancelled", stage: "completed" } : prev);
        setMsg({ type: "info", text: "任务已取消。" });
      } else {
        const res = await fetch(`/api/knowledge/bigpdf/tasks/${encodeURIComponent(taskId)}/cancel`, {
          method: "POST",
          credentials: "include",
          headers: getAuthHeaders(),
        });
        const data = (await res.json().catch(() => ({}))) as { detail?: string };
        if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "取消失败");
        setTrackedTask((prev) => prev ? { ...prev, status: "cancelled", stage: "completed" } : prev);
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
      const sizeMb = Math.round((f.size / (1024 * 1024)) * 10) / 10;
      setUploadMeta({ name: f.name, sizeMb });
      setOverrideTaskId(data.task_id);
      setRestoredTaskId(data.task_id);
      registerPendingBigpdfTask(data.task_id);
      useBigpdfStore.getState().persistTaskId(data.task_id);
      useBigpdfStore.getState().clearActiveTask();
      const nextParams = new URLSearchParams(sp.toString());
      nextParams.set("task_id", data.task_id);
      nextParams.set("name", f.name);
      nextParams.set("size_mb", String(sizeMb));
      if (!nextParams.get("from")) nextParams.set("from", "pdf-knowledge");
      router.replace(`/utils/pdf-knowledge?${nextParams.toString()}`, { scroll: false });
      setMsg({ type: "success", text: "任务已创建，开始处理…" });
    } catch (e) {
      setMsg({ type: "error", text: e instanceof Error ? e.message : "上传失败" });
    } finally {
      setBusy(false);
    }
  };

  const displayMeta = useMemo(() => {
    const sizeMb = uploadMeta?.sizeMb ?? (info.sizeMb ? parseFloat(info.sizeMb) : 0);
    return {
      fileName: uploadMeta?.name || info.name || "未知文件",
      fileSize: sizeMb > 0 ? Math.round(sizeMb * 1024 * 1024) : 0,
      pageCount: uploadMeta?.pages ?? (info.pages ? parseInt(info.pages, 10) : 0),
    };
  }, [uploadMeta, info.name, info.sizeMb, info.pages]);

  const activeTaskForCard = useMemo(() => {
    if (!trackedTask || trackedTask.taskId !== taskId) return null;

    const fallbackName = displayMeta.fileName;
    const needsName = !trackedTask.fileName || trackedTask.fileName === "未知文件";
    if (needsName && fallbackName && fallbackName !== "未知文件") {
      return {
        ...trackedTask,
        fileName: fallbackName,
        fileSize: trackedTask.fileSize || displayMeta.fileSize,
        pageCount: trackedTask.pageCount || displayMeta.pageCount,
      };
    }
    return trackedTask;
  }, [trackedTask, taskId, displayMeta]);

  return (
    <div className="p-6 md:p-8">
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

      <BigpdfMyTasksPanel currentTaskId={taskId || undefined} className="mb-4" />

      {/* Active Task Progress Card */}
      {taskId && taskLoading && !activeTaskForCard ? (
        <div className="mb-4 rounded-lg border border-zinc-800 bg-zinc-950/40 px-4 py-3 text-sm text-zinc-400">
          正在加载任务进度…
        </div>
      ) : null}
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
            <strong className="text-zinc-400">自动组织：</strong>解析完成后，系统会自动创建与上传 PDF 同名的文件夹（去掉 .pdf 后缀），所有知识片段按文档结构自动整理
          </p>
          <p>
            <strong className="text-zinc-400">权限说明：</strong>私人知识库仅您自己可见，不会共享给其他用户或进入公共知识库
          </p>
          <p>
            <strong className="text-zinc-400">耗时提示：</strong>大 PDF 解析通常需要较长时间（约 3 分钟/MB），支持排队等待，您可以随时离开页面，完成后会通过站内提醒通知您
          </p>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <Link
            href={(() => { const base = buildAiInteractionHref(info.folderId ? { folder_ids: [info.folderId] } : {}); return base + (base.includes("?") ? "&" : "?") + "tab=pdf_packages"; })()}
            className="rounded border border-zinc-600 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 hover:bg-zinc-700"
          >
            去 AI 互动页查看 RAG 包
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
