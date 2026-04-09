"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { getAuthHeaders } from "../lib/auth";

type MyDoc = {
  doc_id: string;
  title: string;
  original_filename?: string;
  size_bytes?: number;
  created_at?: string | null;
  collection_ids?: string[];
};

type RagPackage = {
  package_id: string;
  name: string;
  manifest_json?: string | null;
  created_at?: string | null;
  created_by_task_id?: string | null;
};

type KbKindItem = { kb_kind: string; label: string };

type MeOut = {
  username?: string;
  department?: string;
  projects?: Array<{ project_id: string; is_project_lead?: boolean }>;
};

type OptCol = {
  collection_id: string;
  type?: string;
  department_id?: string;
  project_id?: string;
  name?: string;
};

function RagTaskProgress({ taskId }: { taskId: string }) {
  const [task, setTask] = useState<{ status: string; stage: string; progress: number; detail?: string | null } | null>(null);

  useEffect(() => {
    let stop = false;
    async function load() {
      try {
        const res = await fetch(`/api/knowledge/bigpdf/tasks/${encodeURIComponent(taskId)}`, {
          credentials: "include",
          headers: getAuthHeaders(),
        });
        const data = (await res.json().catch(() => ({}))) as any;
        if (!stop && res.ok && data?.task_id) setTask(data);
      } catch {
        // ignore
      }
    }
    load();
    const t = setInterval(load, 2000);
    return () => {
      stop = true;
      clearInterval(t);
    };
  }, [taskId]);

  if (!task) return null;
  const pct = Math.max(0, Math.min(100, task.progress || 0));
  const isFailed = task.status === "failed";
  const isDone = task.status === "done";
  return (
    <div className="mt-2">
      <div className="flex items-center justify-between text-xs text-zinc-500">
        <span>{task.stage}</span>
        <span>{pct}%</span>
      </div>
      <div className="mt-1 h-1.5 w-full rounded bg-zinc-900">
        <div className={`h-1.5 rounded ${isFailed ? "bg-red-500" : isDone ? "bg-emerald-500" : "bg-blue-500"}`} style={{ width: `${pct}%` }} />
      </div>
      {isFailed && task.detail ? <div className="mt-1 text-xs text-red-400">失败：{task.detail}</div> : null}
    </div>
  );
}

export default function KnowledgePage() {
  const [myDocs, setMyDocs] = useState<MyDoc[]>([]);
  const [ragItems, setRagItems] = useState<RagPackage[]>([]);
  const [kbKinds, setKbKinds] = useState<KbKindItem[]>([]);
  const [collections, setCollections] = useState<OptCol[]>([]);
  const [me, setMe] = useState<MeOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [ragDetail, setRagDetail] = useState<any | null>(null);
  const [ragExportKind, setRagExportKind] = useState<"openwebui" | "cn_kb" | "standard">("cn_kb");

  const [shareDoc, setShareDoc] = useState<MyDoc | null>(null);
  const [shareKind, setShareKind] = useState("");
  const [shareDepts, setShareDepts] = useState<string[]>([]);
  const [shareProjs, setShareProjs] = useState<string[]>([]);
  const [shareCompany, setShareCompany] = useState(false);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [meRes, docsRes, ragRes, kindsRes, optRes] = await Promise.all([
        fetch("/api/auth/me", { credentials: "include", headers: getAuthHeaders() }),
        fetch("/api/knowledge/my-documents", { credentials: "include", headers: getAuthHeaders() }),
        fetch("/api/knowledge/rag-packages", { credentials: "include", headers: getAuthHeaders() }),
        fetch("/api/knowledge/meta/kb-kinds", { credentials: "include", headers: getAuthHeaders() }),
        fetch("/api/knowledge/options", { credentials: "include", headers: getAuthHeaders() }),
      ]);
      if (meRes.ok) setMe(await meRes.json());
      if (docsRes.ok) {
        const d = await docsRes.json();
        setMyDocs(d.items ?? []);
      }
      if (ragRes.ok) {
        const r = await ragRes.json();
        setRagItems(r.items ?? []);
      }
      if (kindsRes.ok) {
        const k = await kindsRes.json();
        setKbKinds(k.items ?? []);
      }
      if (optRes.ok) {
        const o = await optRes.json();
        setCollections((o.collections ?? []) as OptCol[]);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  const openRagDetail = async (pkg: RagPackage) => {
    // 切换包时先清掉旧内容，避免“展示错包的预览/sections”
    setRagDetail({ package_id: pkg.package_id, _loading: true, _preview: null });
    setRagExportKind("cn_kb");
    setMsg(null);
    try {
      const res = await fetch(`/api/knowledge/rag-packages/${encodeURIComponent(pkg.package_id)}`, {
        credentials: "include",
        headers: getAuthHeaders(),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "加载失败");
      setRagDetail((prev: any) => ({ ...(prev || {}), _preview: null, ...data }));
    } catch (e) {
      setMsg({ type: "error", text: e instanceof Error ? e.message : "加载失败" });
    }
  };

  const deleteRagPackage = async (pkgId: string) => {
    if (!confirm("确定删除该大文档 RAG 包？（将同时删除磁盘产物）")) return;
    setMsg(null);
    try {
      const res = await fetch(`/api/knowledge/rag-packages/${encodeURIComponent(pkgId)}`, {
        method: "DELETE",
        credentials: "include",
        headers: getAuthHeaders(),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "删除失败");
      setMsg({ type: "success", text: "已删除 RAG 包。" });
      setRagDetail(null);
      await loadAll();
    } catch (e) {
      setMsg({ type: "error", text: e instanceof Error ? e.message : "删除失败" });
    }
  };

  const retryBigPdfTask = async (taskId: string) => {
    setMsg(null);
    try {
      const res = await fetch(`/api/knowledge/bigpdf/tasks/${encodeURIComponent(taskId)}/retry`, {
        method: "POST",
        credentials: "include",
        headers: getAuthHeaders(),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "重试失败");
      setMsg({ type: "success", text: "已提交重试任务。" });
      await loadAll();
    } catch (e) {
      setMsg({ type: "error", text: e instanceof Error ? e.message : "重试失败" });
    }
  };

  const previewRagText = async (pkgId: string, kind: "merged" | "section", filename?: string) => {
    setMsg(null);
    try {
      const u = new URL(`/api/knowledge/rag-packages/${encodeURIComponent(pkgId)}/preview`, window.location.origin);
      u.searchParams.set("kind", kind);
      if (filename) u.searchParams.set("filename", filename);
      const res = await fetch(u.toString(), { credentials: "include", headers: getAuthHeaders() });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "预览失败");
      setRagDetail((prev: any) => ({ ...(prev || {}), _preview: data }));
    } catch (e) {
      setMsg({ type: "error", text: e instanceof Error ? e.message : "预览失败" });
    }
  };

  const downloadRagExport = async (pkgId: string, profile: string) => {
    setMsg(null);
    try {
      const res = await fetch(
        `/api/knowledge/rag-packages/${encodeURIComponent(pkgId)}/export?profile=${encodeURIComponent(profile)}`,
        {
          credentials: "include",
          headers: getAuthHeaders(),
        }
      );
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(typeof data.detail === "string" ? data.detail : "下载失败");
      }
      const blob = await res.blob();
      const cd = res.headers.get("content-disposition") || "";
      const m = cd.match(/filename="([^"]+)"/i);
      const filename = m?.[1] || `${pkgId}_${profile}.zip`;
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      setMsg({ type: "error", text: e instanceof Error ? e.message : "下载失败" });
    }
  };

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const departmentChoices = useMemo(() => {
    const s = new Set<string>();
    for (const c of collections) {
      if (c.type === "department" && c.department_id) s.add(c.department_id);
    }
    return Array.from(s).sort();
  }, [collections]);

  const projectChoices = useMemo(() => {
    const m = new Map<string, string>();
    for (const c of collections) {
      if (c.type === "project" && c.project_id) m.set(c.project_id, c.name || c.project_id);
    }
    return Array.from(m.entries()).map(([project_id, name]) => ({ project_id, name }));
  }, [collections]);

  const openShare = (d: MyDoc) => {
    setShareDoc(d);
    setShareKind("");
    const u = me;
    setShareDepts(u?.department ? [u.department] : []);
    setShareProjs((u?.projects ?? []).map((p) => p.project_id).filter(Boolean));
    setShareCompany(false);
  };

  const toggleDept = (d: string) => {
    setShareDepts((prev) => (prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d]));
  };

  const toggleProj = (p: string) => {
    setShareProjs((prev) => (prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]));
  };

  const handleShareSave = async () => {
    if (!shareDoc || !shareKind) return;
    setMsg(null);
    try {
      const res = await fetch(`/api/knowledge/my-documents/${encodeURIComponent(shareDoc.doc_id)}/share`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        credentials: "include",
        body: JSON.stringify({
          kb_kind: shareKind,
          department_ids: shareDepts,
          project_ids: shareProjs,
          company_public: shareCompany,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "共享失败");
      setMsg({ type: "success", text: "已更新共享目标。" });
      setShareDoc(null);
      await loadAll();
    } catch (e) {
      setMsg({ type: "error", text: e instanceof Error ? e.message : "共享失败" });
    }
  };

  const handleDelete = async (docId: string) => {
    if (!confirm("确定删除该文档？")) return;
    setMsg(null);
    try {
      const res = await fetch(`/api/knowledge/my-documents/${encodeURIComponent(docId)}`, {
        method: "DELETE",
        credentials: "include",
        headers: getAuthHeaders(),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "删除失败");
      setMsg({ type: "success", text: "已删除。" });
      await loadAll();
    } catch (e) {
      setMsg({ type: "error", text: e instanceof Error ? e.message : "删除失败" });
    }
  };

  return (
    <div className="p-6 md:p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-100">知识库</h1>
        <p className="mt-1 text-sm text-zinc-500">左侧管理您上传的文档（默认在私人知识库）；右侧查看大文档 RAG 包（docling 产物）。</p>
      </div>

      {msg && (
        <p className={`mb-4 text-sm ${msg.type === "success" ? "text-emerald-400" : "text-red-400"}`}>{msg.text}</p>
      )}

      <div className="grid gap-6 md:grid-cols-2">
        <section className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
          <h2 className="mb-2 text-lg font-medium text-zinc-200">我的知识库文档</h2>
          <p className="mb-4 text-sm text-zinc-500">上传入口在「AI 互动」页；此处可删除或共享到其他知识库类型。</p>
          {loading ? (
            <p className="text-sm text-zinc-500">加载中…</p>
          ) : myDocs.length === 0 ? (
            <div className="flex min-h-[20vh] items-center justify-center rounded-lg border border-dashed border-zinc-700 text-zinc-500 text-sm">
              暂无文档，请前往 AI 互动页上传。
            </div>
          ) : (
            <ul className="space-y-2">
              {myDocs.map((d) => (
                <li
                  key={d.doc_id}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-zinc-700 bg-zinc-800/50 px-3 py-2 text-sm"
                >
                  <div className="min-w-0">
                    <div className="truncate text-zinc-200">{d.title}</div>
                    <div className="text-xs text-zinc-500">
                      {d.original_filename} · {(d.collection_ids ?? []).length} 个归属知识库
                    </div>
                  </div>
                  <div className="flex shrink-0 gap-2">
                    <button
                      type="button"
                      onClick={() => openShare(d)}
                      className="rounded border border-zinc-600 bg-zinc-700 px-2 py-1 text-xs text-zinc-200 hover:bg-zinc-600"
                    >
                      共享到
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDelete(d.doc_id)}
                      className="rounded border border-red-900/50 bg-red-900/20 px-2 py-1 text-xs text-red-300 hover:bg-red-900/40"
                    >
                      删除
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
          <h2 className="mb-2 text-lg font-medium text-zinc-200">大文档 RAG 包</h2>
          <p className="mb-4 text-sm text-zinc-500">docling 处理后的文档包与清单，后续可在此管理版本与索引状态。</p>
          {loading ? (
            <p className="text-sm text-zinc-500">加载中…</p>
          ) : ragItems.length === 0 ? (
            <div className="flex min-h-[20vh] items-center justify-center rounded-lg border border-dashed border-zinc-700 text-zinc-500 text-sm">
              暂无 RAG 包
            </div>
          ) : (
            <ul className="space-y-2">
              {ragItems.map((p) => (
                <li key={p.package_id} className="rounded-md border border-zinc-700 bg-zinc-800/50 px-3 py-2 text-sm">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="font-medium text-zinc-200 truncate">{p.name}</div>
                      <div className="text-xs text-zinc-500">{p.package_id}</div>
                    </div>
                    <button
                      type="button"
                      onClick={() => openRagDetail(p)}
                      className="shrink-0 rounded border border-zinc-600 bg-zinc-700 px-2 py-1 text-xs text-zinc-200 hover:bg-zinc-600"
                    >
                      管理
                    </button>
                  </div>
                  {p.created_by_task_id ? (
                    <RagTaskProgress taskId={p.created_by_task_id} />
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      {ragDetail && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-lg border border-zinc-700 bg-zinc-900 p-5 shadow-xl">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <h3 className="text-lg font-medium text-zinc-100 truncate">大文档 RAG 包管理</h3>
                <p className="mt-1 text-sm text-zinc-400 font-mono">{ragDetail.package_id}</p>
              </div>
              <button
                type="button"
                onClick={() => setRagDetail(null)}
                aria-label="关闭"
                className="rounded border border-zinc-700 bg-zinc-800 px-2 py-1 text-sm text-zinc-200 hover:bg-zinc-700"
              >
                ×
              </button>
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-zinc-400">
              <span className="text-zinc-500">切换包：</span>
              {ragItems.slice(0, 8).map((p) => (
                <button
                  key={p.package_id}
                  type="button"
                  onClick={() => openRagDetail(p)}
                  className={`rounded border px-2 py-1 font-mono hover:bg-zinc-800 ${
                    p.package_id === ragDetail.package_id ? "border-blue-700 bg-blue-900/20 text-blue-200" : "border-zinc-700 bg-zinc-900 text-zinc-300"
                  }`}
                  title={p.name}
                >
                  {p.package_id.slice(-6)}
                </button>
              ))}
              {ragItems.length > 8 ? <span className="text-zinc-500">…（列表仅显示前 8 个）</span> : null}
            </div>

            <div className="mt-4 rounded border border-zinc-800 bg-zinc-950/40 p-3">
              <div className="mb-2 text-xs text-zinc-400">导出包类型（合并同类项）：</div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setRagExportKind("openwebui");
                    setRagDetail((prev: any) => ({ ...(prev || {}), _preview: null }));
                  }}
                  className={`rounded border px-2 py-1 text-xs ${
                    ragExportKind === "openwebui"
                      ? "border-blue-700 bg-blue-900/20 text-blue-200"
                      : "border-zinc-700 bg-zinc-900 text-zinc-200 hover:bg-zinc-800"
                  }`}
                >
                  Open WebUI 专用包
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setRagExportKind("cn_kb");
                    setRagDetail((prev: any) => ({ ...(prev || {}), _preview: null }));
                  }}
                  className={`rounded border px-2 py-1 text-xs ${
                    ragExportKind === "cn_kb"
                      ? "border-blue-700 bg-blue-900/20 text-blue-200"
                      : "border-zinc-700 bg-zinc-900 text-zinc-200 hover:bg-zinc-800"
                  }`}
                >
                  通用中文AI知识库包（秘塔/千问/ima/豆包/CherryStudio/ChatBot）
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setRagExportKind("standard");
                    setRagDetail((prev: any) => ({ ...(prev || {}), _preview: null }));
                  }}
                  className={`rounded border px-2 py-1 text-xs ${
                    ragExportKind === "standard"
                      ? "border-blue-700 bg-blue-900/20 text-blue-200"
                      : "border-zinc-700 bg-zinc-900 text-zinc-200 hover:bg-zinc-800"
                  }`}
                >
                  标准包（raw/archive/kb，审计/再处理）
                </button>
              </div>
            </div>

            <div className="mt-4 rounded border border-zinc-800 bg-zinc-950/40 p-3 text-xs text-zinc-300">
              <div className="mb-2 text-zinc-400">使用方法（按外部端）：</div>
              <ul className="space-y-1 text-zinc-300">
                {ragExportKind === "openwebui" ? (
                  <>
                    <li>
                      <span className="text-zinc-400">适用端：</span>Open WebUI（Knowledge Base / RAG 文件导入）
                    </li>
                    <li>
                      <span className="text-zinc-400">推荐导入：</span>优先上传 `sections/*.md`（更稳，避免单文件过大/卡住）。
                    </li>
                    <li>
                      <span className="text-zinc-400">备选：</span>若只能上传单文件，可用 `merged.md`（可能更容易触发大小限制）。
                    </li>
                    <li>
                      <span className="text-zinc-400">注意：</span>如遇上传挂起，优先把文档切得更碎（本包已按章节分段）。
                    </li>
                  </>
                ) : ragExportKind === "cn_kb" ? (
                  <>
                    <li>
                      <span className="text-zinc-400">适用端：</span>秘塔 / 豆包 / 通义千问 / ima / CherryStudio / 各类带知识库的 ChatBot 客户端（通常支持上传 Markdown 文件或文件夹）
                    </li>
                    <li>
                      <span className="text-zinc-400">推荐导入：</span>上传 `sections/*.md` 或导入 `sections/` 目录（文件夹导入通常最稳）。
                    </li>
                    <li>
                      <span className="text-zinc-400">备选：</span>若产品仅支持单文件导入，上传 `merged.md`。
                    </li>
                    <li>
                      <span className="text-zinc-400">注意：</span>不同产品对单文件大小/数量有限制，优先用分段文件导入。
                    </li>
                  </>
                ) : (
                  <>
                    <li>
                      <span className="text-zinc-400">适用场景：</span>审计追溯 / 二次加工 / 重新切分 / 研发联调
                    </li>
                    <li>
                      <span className="text-zinc-400">内容：</span>包含 `raw/`（原文件）、`archive/`（docling 输出）、`kb/`（分段与 manifest）
                    </li>
                    <li>
                      <span className="text-zinc-400">注意：</span>这是“资源包全量产物”，不一定适合直接喂给外部知识库产品。
                    </li>
                  </>
                )}
              </ul>
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => previewRagText(ragDetail.package_id, "merged")}
                className="rounded border border-zinc-700 bg-zinc-800/60 px-3 py-2 text-sm text-zinc-200 hover:bg-zinc-700"
              >
                预览 merged（archive/full.md）
              </button>
              {Array.isArray(ragDetail?.sections) && ragDetail.sections.length > 0 ? (
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs text-zinc-500">sections：</span>
                  {ragDetail.sections.slice(0, 10).map((s: any) => (
                    <button
                      key={s.filename}
                      type="button"
                      onClick={() => previewRagText(ragDetail.package_id, "section", s.filename)}
                      className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs font-mono text-zinc-200 hover:bg-zinc-800"
                      title={`${s.filename} (${s.size_bytes ?? 0} bytes)`}
                    >
                      {String(s.filename).replace(".md", "")}
                    </button>
                  ))}
                  {ragDetail.sections.length > 10 ? <span className="text-xs text-zinc-500">…</span> : null}
                </div>
              ) : null}
              {ragDetail?.created_by_task_id ? (
                <button
                  type="button"
                  onClick={() => retryBigPdfTask(ragDetail.created_by_task_id)}
                  className="rounded border border-zinc-700 bg-zinc-800/60 px-3 py-2 text-sm text-zinc-200 hover:bg-zinc-700"
                >
                  重试该任务
                </button>
              ) : null}
            </div>

            {ragDetail?._preview?.text ? (
              <div className="mt-4 rounded border border-zinc-800 bg-zinc-950/40 p-3">
                <div className="mb-2 flex items-center justify-between text-xs text-zinc-400">
                  <span>
                    预览：{ragDetail._preview.filename}
                    {ragDetail._preview.truncated ? "（已截断）" : ""}
                  </span>
                  <button
                    type="button"
                    onClick={() => setRagDetail((prev: any) => ({ ...(prev || {}), _preview: null }))}
                    className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-800"
                  >
                    清除预览
                  </button>
                </div>
                <pre className="max-h-[40vh] overflow-auto whitespace-pre-wrap break-words text-xs text-zinc-200">
                  {ragDetail._preview.text}
                </pre>
              </div>
            ) : null}

            <div className="mt-4 rounded border border-zinc-800 bg-zinc-950/40 p-3 text-xs text-zinc-400">
              <div>产物路径（后端）：{ragDetail?.paths?.root}</div>
              <div>sections：{Array.isArray(ragDetail.sections) ? ragDetail.sections.length : 0}</div>
            </div>

            <div className="mt-4 flex flex-wrap justify-end gap-2">
              <button
                type="button"
                onClick={() => downloadRagExport(ragDetail.package_id, ragExportKind)}
                className="rounded border border-zinc-700 bg-zinc-800/60 px-3 py-2 text-sm text-zinc-200 hover:bg-zinc-700"
              >
                下载
              </button>
              <button
                type="button"
                onClick={() => deleteRagPackage(ragDetail.package_id)}
                className="rounded border border-red-900/50 bg-red-900/20 px-3 py-2 text-sm text-red-300 hover:bg-red-900/40"
              >
                删除整个资源包
              </button>
            </div>
          </div>
        </div>
      )}

      {shareDoc && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-lg border border-zinc-700 bg-zinc-900 p-5 shadow-xl">
            <h3 className="text-lg font-medium text-zinc-100">共享文档</h3>
            <p className="mt-1 text-sm text-zinc-500">{shareDoc.title}</p>
            <div className="mt-4 space-y-3">
              <div>
                <label className="mb-1 block text-xs text-zinc-400">目标知识库类型</label>
                <select
                  value={shareKind}
                  onChange={(e) => setShareKind(e.target.value)}
                  className="w-full rounded border border-zinc-600 bg-zinc-800 px-2 py-2 text-sm text-zinc-200"
                >
                  <option value="">请选择</option>
                  {kbKinds.map((k) => (
                    <option key={k.kb_kind} value={k.kb_kind}>
                      {k.label}（{k.kb_kind}）
                    </option>
                  ))}
                </select>
              </div>
              {(shareKind === "DeptPublic" || shareKind === "DeptLead") && (
                <div>
                  <div className="mb-1 text-xs text-zinc-400">部门（默认已选您所属部门，可增删）</div>
                  <div className="flex flex-wrap gap-2">
                    {departmentChoices.map((d) => (
                      <label key={d} className="flex cursor-pointer items-center gap-1.5 text-xs text-zinc-300">
                        <input type="checkbox" checked={shareDepts.includes(d)} onChange={() => toggleDept(d)} />
                        {d}
                      </label>
                    ))}
                  </div>
                </div>
              )}
              {(shareKind === "ProjectPublic" || shareKind === "ProjectLead") && (
                <div>
                  <div className="mb-1 text-xs text-zinc-400">项目（默认已选您参与项目，可增删）</div>
                  <div className="flex flex-wrap gap-2">
                    {projectChoices.map((p) => (
                      <label key={p.project_id} className="flex cursor-pointer items-center gap-1.5 text-xs text-zinc-300">
                        <input type="checkbox" checked={shareProjs.includes(p.project_id)} onChange={() => toggleProj(p.project_id)} />
                        {p.name}
                      </label>
                    ))}
                  </div>
                </div>
              )}
              {shareKind === "CompanyPublic" && (
                <label className="flex items-center gap-2 text-sm text-zinc-300">
                  <input type="checkbox" checked={shareCompany} onChange={(e) => setShareCompany(e.target.checked)} />
                  同时发布到公司公共库
                </label>
              )}
              {["MultiDeptPublic", "MultiDeptLead", "MultiProjectPublic", "MultiProjectLead"].includes(shareKind) && (
                <p className="text-xs text-zinc-500">将共享到系统配置的多部门/多项目逻辑库（scope 由管理端维护）。</p>
              )}
            </div>
            <div className="mt-6 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setShareDoc(null)}
                className="rounded border border-zinc-600 px-3 py-1.5 text-sm text-zinc-300"
              >
                取消
              </button>
              <button
                type="button"
                disabled={!shareKind}
                onClick={handleShareSave}
                className="rounded bg-zinc-600 px-3 py-1.5 text-sm text-white disabled:opacity-50"
              >
                保存
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
