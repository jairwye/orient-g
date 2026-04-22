"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { getAuthHeaders } from "../../lib/auth";
import { buildAiInteractionHref, buildKnowledgeHref } from "../../lib/kb_scope_capsule";
import { useSmartPoll } from "../../lib/smartPoll";

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
  const [msg, setMsg] = useState<{ type: "info" | "success" | "error"; text: string } | null>(null);
  const [isPageVisible, setIsPageVisible] = useState(true);
  const queryTaskId = useMemo(() => (sp.get("task_id") || "").trim(), [sp]);
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

  const taskId = queryTaskId;
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
    isTerminal: (data) => data.status === "done" || data.status === "failed",
    isActive: (data) => {
      if (data.status === "done" || data.status === "failed") return false;
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

  useEffect(() => {
    if (!queryTaskId) return;
    if (!task?.task_id) return;
    if (shownQueryInfoMsgRef.current) return;
    shownQueryInfoMsgRef.current = true;
    setMsg({ type: "info", text: "已加载任务进度（来自跳转参数）。" });
  }, [queryTaskId, task?.task_id]);

  const handleUpload = async (f: File) => {
    setBusy(true);
    setMsg(null);
    try {
      const fd = new FormData();
      fd.append("file", f);
      const res = await fetch("/api/knowledge/bigpdf/tasks", {
        method: "POST",
        credentials: "include",
        headers: getAuthHeaders(),
        body: fd,
      });
      const data = (await res.json().catch(() => ({}))) as BigPdfTask & { detail?: string };
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "创建任务失败");
      setTask(data);
      setMsg({ type: "success", text: "任务已创建，开始处理…" });
    } catch (e) {
      setMsg({ type: "error", text: e instanceof Error ? e.message : "上传失败" });
    } finally {
      setBusy(false);
    }
  };

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
            onClick={() => fileInputRef.current?.click()}
            className="rounded border border-zinc-600 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 hover:bg-zinc-700 disabled:opacity-50"
          >
            {busy ? "提交中…" : "上传大 PDF 开始处理"}
          </button>
          {msg && <span className={msg.type === "error" ? "text-red-400 text-sm" : msg.type === "success" ? "text-emerald-400 text-sm" : "text-zinc-400 text-sm"}>{msg.text}</span>}
        </div>

        <div className="mt-4 rounded-lg border border-dashed border-zinc-700 p-5 text-sm text-zinc-500">
          说明：大 PDF 将通过 Docling 解析并生成「大文档 RAG 包」。完成后出现在「知识库」页右侧（不进入“我的知识库文档”）。
        </div>

        {task && (
          <div className="mt-4 rounded-lg border border-zinc-800 bg-zinc-950/40 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
              <div className="text-zinc-200">
                任务：<span className="font-mono text-zinc-300">{task.task_id}</span>
              </div>
              <div className="text-zinc-400">
                {task.stage} · {task.progress}%
              </div>
            </div>
            <div className="mt-2 h-2 w-full rounded bg-zinc-800">
              <div className="h-2 rounded bg-blue-500" style={{ width: `${Math.max(0, Math.min(100, task.progress || 0))}%` }} />
            </div>
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
    </div>
  );
}
