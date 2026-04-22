"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { getAuthHeaders } from "../lib/auth";
import { KbInProgressBanner } from "../components/KbInProgressBanner";
import { buildAiInteractionHref, writeKbScopeCapsule } from "../lib/kb_scope_capsule";
import { useSmartPoll } from "../lib/smartPoll";

type MyDoc = {
  doc_id: string;
  title: string;
  original_filename?: string;
  size_bytes?: number;
  status?: string;
  last_error?: string | null;
  created_at?: string | null;
  collection_ids?: string[];
};

type FolderItem = {
  folder_id: string;
  name: string;
  kind?: string | null;
  owner_username?: string | null;
  collection_ids?: string[];
  resource_counts?: Record<string, number>;
};

type FolderResourcesResponse = {
  folder: FolderItem;
  resources: Array<{ resource_type: string; resource_id: string; created_at?: string | null }>;
  docs: Array<{ doc_id: string; title: string; original_filename?: string; size_bytes?: number; status?: string; last_error?: string | null; created_at?: string | null }>;
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

const BIG_PDF_SIZE_MB = 15;
const BIG_PDF_PAGES = 60;

function formatMb(bytes: number) {
  return Math.round((bytes / 1024 / 1024) * 10) / 10;
}

function statusLabel(s?: string) {
  const k = (s || "").toLowerCase();
  if (k === "queued") return "排队中";
  if (k === "parsing") return "解析中";
  if (k === "active") return "已可用";
  if (k === "failed") return "失败";
  if (k === "packaged") return "打包中";
  if (k === "parsed") return "已解析";
  return s || "未知";
}

async function estimatePdfPages(file: File): Promise<number | null> {
  try {
    const buf = await file.arrayBuffer();
    const text = new TextDecoder("latin1").decode(buf);
    const pages = (text.match(/\/Type\s*\/Page\b/g) || []).length;
    const pagesContainer = (text.match(/\/Type\s*\/Pages\b/g) || []).length;
    const approx = Math.max(0, pages - pagesContainer);
    return approx > 0 ? approx : null;
  } catch {
    return null;
  }
}

function RagTaskProgress({ taskId }: { taskId: string }) {
  const [task, setTask] = useState<{
    task_id?: string;
    status: string;
    stage: string;
    progress: number;
    detail?: string | null;
  } | null>(null);

  useEffect(() => {
    let stop = false;
    async function load() {
      try {
        const res = await fetch(`/api/knowledge/bigpdf/tasks/${encodeURIComponent(taskId)}`, {
          credentials: "include",
          headers: getAuthHeaders(),
        });
        const data = (await res.json().catch(() => ({}))) as Partial<{ task_id: string; status: string; stage: string; progress: number; detail?: string | null }>;
        if (!stop && res.ok && typeof data.task_id === "string") {
          setTask({
            task_id: data.task_id,
            status: String(data.status ?? ""),
            stage: String(data.stage ?? ""),
            progress: Number(data.progress ?? 0),
            detail: typeof data.detail === "string" ? data.detail : null,
          });
        }
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
  const sp = useSearchParams();
  const [myDocs, setMyDocs] = useState<MyDoc[]>([]);
  const [ragItems, setRagItems] = useState<RagPackage[]>([]);
  const [kbKinds, setKbKinds] = useState<KbKindItem[]>([]);
  const [collections, setCollections] = useState<OptCol[]>([]);
  const [me, setMe] = useState<MeOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState<{ type: "success" | "error" | "info"; text: string } | null>(null);
  const [ragDetail, setRagDetail] = useState<(Record<string, unknown> & { _preview?: unknown; _loading?: boolean; package_id?: string }) | null>(null);
  const [ragExportKind, setRagExportKind] = useState<"openwebui" | "cn_kb" | "standard">("cn_kb");

  const [shareDoc, setShareDoc] = useState<MyDoc | null>(null);
  const [shareFolder, setShareFolder] = useState<FolderItem | null>(null);
  const [shareKind, setShareKind] = useState("");
  const [shareDepts, setShareDepts] = useState<string[]>([]);
  const [shareProjs, setShareProjs] = useState<string[]>([]);
  const [shareCompany, setShareCompany] = useState(false);
  const [folderShareTarget, setFolderShareTarget] = useState<"company" | "department" | "project">("company");

  const [folders, setFolders] = useState<FolderItem[]>([]);
  const [activeFolderId, setActiveFolderId] = useState<string | null>(null);
  const [folderDetail, setFolderDetail] = useState<FolderResourcesResponse | null>(null);
  const [folderLoading, setFolderLoading] = useState(false);
  const [folderUploadBusy, setFolderUploadBusy] = useState(false);
  const folderFileInputRef = useRef<HTMLInputElement>(null);
  const [isPageVisible, setIsPageVisible] = useState(true);

  useEffect(() => {
    const update = () => setIsPageVisible(document.visibilityState === "visible");
    update();
    document.addEventListener("visibilitychange", update);
    return () => document.removeEventListener("visibilitychange", update);
  }, []);

  const docIsRunning = useCallback((d: { status?: string }) => {
    const s = (d.status || "").toLowerCase();
    return ["queued", "parsing", "parsed", "packaged"].includes(s);
  }, []);

  const folderHasRunningDocs = useMemo(() => {
    if (!folderDetail?.docs?.length) return false;
    return folderDetail.docs.some((d) => docIsRunning(d));
  }, [docIsRunning, folderDetail?.docs]);

  const fetchFolderDetail = useCallback(async (folderId: string): Promise<FolderResourcesResponse> => {
    const res = await fetch(`/api/knowledge/folders/${encodeURIComponent(folderId)}/resources`, {
      credentials: "include",
      headers: getAuthHeaders(),
    });
    const data = (await res.json().catch(() => ({}))) as Partial<FolderResourcesResponse> & { detail?: string };
    if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "加载失败");
    return data as FolderResourcesResponse;
  }, []);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [meRes, docsRes, ragRes, kindsRes, optRes, foldersRes] = await Promise.all([
        fetch("/api/auth/me", { credentials: "include", headers: getAuthHeaders() }),
        fetch("/api/knowledge/my-documents", { credentials: "include", headers: getAuthHeaders() }),
        fetch("/api/knowledge/rag-packages", { credentials: "include", headers: getAuthHeaders() }),
        fetch("/api/knowledge/meta/kb-kinds", { credentials: "include", headers: getAuthHeaders() }),
        fetch("/api/knowledge/options", { credentials: "include", headers: getAuthHeaders() }),
        fetch("/api/knowledge/folders", { credentials: "include", headers: getAuthHeaders() }),
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
      if (foldersRes.ok) {
        const f = await foldersRes.json().catch(() => ({}));
        const items = (f.items ?? []) as FolderItem[];
        setFolders(items);
        if (!activeFolderId && items.length) setActiveFolderId(items[0].folder_id);
      }
    } finally {
      setLoading(false);
    }
  }, [activeFolderId]);

  useEffect(() => {
    const fid = (sp.get("folder_id") || "").trim();
    if (!fid || !folders.length) return;
    if (folders.some((f) => f.folder_id === fid)) setActiveFolderId(fid);
  }, [sp, folders]);

  const bringCurrentFolderToAi = () => {
    if (!activeFolderId) return;
    writeKbScopeCapsule({ folder_ids: [activeFolderId], collection_ids: [], table_ids: [] });
    window.location.href = buildAiInteractionHref({ folder_ids: [activeFolderId] });
  };

  const loadFolderDetail = useCallback(
    async (folderId: string) => {
      if (!folderId) return;
      setFolderLoading(true);
      try {
        const data = await fetchFolderDetail(folderId);
        setFolderDetail(data);
      } catch (e) {
        setFolderDetail(null);
        setMsg({ type: "error", text: e instanceof Error ? e.message : "加载失败" });
      } finally {
        setFolderLoading(false);
      }
    },
    [fetchFolderDetail]
  );

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
      setRagDetail((prev) => ({ ...(prev || {}), _preview: null, ...(data as Record<string, unknown>) }));
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
      setRagDetail((prev) => ({ ...(prev || {}), _preview: data }));
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

  useEffect(() => {
    if (activeFolderId) loadFolderDetail(activeFolderId);
  }, [activeFolderId, loadFolderDetail]);

  useSmartPoll<FolderResourcesResponse>({
    enabled: isPageVisible && Boolean(activeFolderId) && folderHasRunningDocs,
    load: async () => {
      const fid = activeFolderId;
      if (!fid) throw new Error("missing folder id");
      const data = await fetchFolderDetail(fid);
      setFolderDetail(data);
      return data;
    },
    isTerminal: (data) => !data.docs.some((d) => docIsRunning(d)),
    isActive: (data) => data.docs.some((d) => docIsRunning(d)),
    activeMs: 5000,
    stableMs: 30000,
    errorMaxMs: 60000,
    errorCooldownAfter: 3,
    errorCooldownMs: 120000,
    initialData: folderDetail ?? undefined,
  });

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

  const openShareFolder = (f: FolderItem) => {
    setShareFolder(f);
    setShareDoc(null);
    setShareKind("");
    setFolderShareTarget("company");
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
    if (!shareDoc && !shareFolder) return;
    setMsg(null);
    try {
      const isFolder = Boolean(shareFolder);
      const url = isFolder
        ? `/api/knowledge/folders/${encodeURIComponent(shareFolder!.folder_id)}/share-scope`
        : `/api/knowledge/my-documents/${encodeURIComponent(shareDoc!.doc_id)}/share`;
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        credentials: "include",
        body: JSON.stringify(
          isFolder
            ? {
                target: folderShareTarget,
                department_ids: shareDepts,
                project_ids: shareProjs,
              }
            : {
                kb_kind: shareKind,
                department_ids: shareDepts,
                project_ids: shareProjs,
                company_public: shareCompany,
              }
        ),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "共享失败");
      setMsg({ type: "success", text: isFolder ? "已更新文件夹共享目标。" : "已更新共享目标。" });
      setShareDoc(null);
      setShareFolder(null);
      await loadAll();
      if (activeFolderId) await loadFolderDetail(activeFolderId);
    } catch (e) {
      setMsg({ type: "error", text: e instanceof Error ? e.message : "共享失败" });
    }
  };

  const unshareActiveFolder = async () => {
    if (!folderDetail?.folder?.folder_id) return;
    if (!confirm("确定取消共享并回到私有？（仅 owner 可见）")) return;
    setMsg(null);
    try {
      const res = await fetch(`/api/knowledge/folders/${encodeURIComponent(folderDetail.folder.folder_id)}/unshare`, {
        method: "POST",
        credentials: "include",
        headers: getAuthHeaders(),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "取消共享失败");
      setMsg({ type: "success", text: "已取消共享，文件夹已回到私有。" });
      await loadAll();
      if (activeFolderId) await loadFolderDetail(activeFolderId);
    } catch (e) {
      setMsg({ type: "error", text: e instanceof Error ? e.message : "取消共享失败" });
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
      if (activeFolderId) await loadFolderDetail(activeFolderId);
    } catch (e) {
      setMsg({ type: "error", text: e instanceof Error ? e.message : "删除失败" });
    }
  };

  const createNewFolder = async () => {
    const name = prompt("新建文件夹名称");
    if (!name) return;
    setMsg(null);
    try {
      const res = await fetch("/api/knowledge/folders", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        credentials: "include",
        body: JSON.stringify({ name }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "创建失败");
      setMsg({ type: "success", text: "已创建文件夹。" });
      await loadAll();
    } catch (e) {
      setMsg({ type: "error", text: e instanceof Error ? e.message : "创建失败" });
    }
  };

  const renameFolder = async (f: FolderItem) => {
    const name = prompt("重命名文件夹", f.name || "");
    if (!name) return;
    setMsg(null);
    try {
      const res = await fetch(`/api/knowledge/folders/${encodeURIComponent(f.folder_id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        credentials: "include",
        body: JSON.stringify({ name }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "重命名失败");
      setMsg({ type: "success", text: "已重命名文件夹。" });
      await loadAll();
    } catch (e) {
      setMsg({ type: "error", text: e instanceof Error ? e.message : "重命名失败" });
    }
  };

  const deleteFolder = async (f: FolderItem) => {
    if (!confirm(`确定删除文件夹「${f.name}」？（仅删除文件夹绑定关系）`)) return;
    setMsg(null);
    try {
      const res = await fetch(`/api/knowledge/folders/${encodeURIComponent(f.folder_id)}`, {
        method: "DELETE",
        credentials: "include",
        headers: getAuthHeaders(),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "删除失败");
      setMsg({ type: "success", text: "已删除文件夹。" });
      setActiveFolderId(null);
      setFolderDetail(null);
      await loadAll();
    } catch (e) {
      setMsg({ type: "error", text: e instanceof Error ? e.message : "删除失败" });
    }
  };

  const moveDocToFolder = async (docId: string, targetFolderId: string) => {
    if (!activeFolderId || !targetFolderId || targetFolderId === activeFolderId) return;
    setMsg(null);
    try {
      const res = await fetch(`/api/knowledge/folders/${encodeURIComponent(activeFolderId)}/move-resources`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        credentials: "include",
        body: JSON.stringify({ target_folder_id: targetFolderId, doc_ids: [docId] }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "移动失败");
      setMsg({ type: "success", text: "已移动文档。" });
      await loadAll();
      await loadFolderDetail(activeFolderId);
    } catch (e) {
      setMsg({ type: "error", text: e instanceof Error ? e.message : "移动失败" });
    }
  };

  const uploadToActiveFolder = async (file: File) => {
    if (!activeFolderId) return;
    setMsg(null);
    setFolderUploadBusy(true);
    try {
      const sizeMb = formatMb(file.size);
      const isPdf = (file.name || "").toLowerCase().endsWith(".pdf") || file.type === "application/pdf";
      let pages: number | null = null;
      if (isPdf && sizeMb <= BIG_PDF_SIZE_MB) {
        pages = await estimatePdfPages(file);
      }
      const isBig = sizeMb > BIG_PDF_SIZE_MB || (pages !== null && pages > BIG_PDF_PAGES);
      if (isPdf && isBig) {
        const reasons: string[] = [];
        if (sizeMb > BIG_PDF_SIZE_MB) reasons.push(`大小约 ${sizeMb}MB > ${BIG_PDF_SIZE_MB}MB`);
        if (pages !== null && pages > BIG_PDF_PAGES) reasons.push(`页数约 ${pages} > ${BIG_PDF_PAGES}`);
        const ok = confirm(`检测为大 PDF（${reasons.join("；") || "可能耗时较长"}）。是否跳转到「大 PDF 上传流程」？`);
        if (ok) {
          const fd = new FormData();
          fd.append("file", file);
          const res = await fetch("/api/knowledge/bigpdf/tasks", {
            method: "POST",
            credentials: "include",
            headers: getAuthHeaders(),
            body: fd,
          });
          const data = (await res.json().catch(() => ({}))) as { detail?: string; task_id?: string };
          if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "创建大文档任务失败");
          const taskId = typeof data.task_id === "string" ? data.task_id : "";
          if (!taskId) throw new Error("创建任务失败（缺少 task_id）");
          const q = new URLSearchParams();
          q.set("task_id", taskId);
          q.set("from", "knowledge");
          q.set("folder_id", activeFolderId);
          q.set("name", file.name);
          q.set("size_mb", String(sizeMb));
          if (pages !== null) q.set("pages", String(pages));
          window.location.href = `/utils/pdf-knowledge?${q.toString()}`;
          return;
        }
        return;
      }

      setMsg({ type: "info", text: "文件已上传，正在后台排队解析入库（耗时较长可在列表查看状态）…" });
      const fd = new FormData();
      fd.append("file", file);
      fd.append("folder_id", activeFolderId);
      const res = await fetch("/api/knowledge/my-documents/upload", {
        method: "POST",
        credentials: "include",
        headers: getAuthHeaders(),
        body: fd,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "上传失败");
      setMsg({ type: "success", text: "已上传到当前文件夹，后台正在解析入库。" });
      await loadAll();
      await loadFolderDetail(activeFolderId);
    } catch (e) {
      setMsg({ type: "error", text: e instanceof Error ? e.message : "上传失败" });
    } finally {
      setFolderUploadBusy(false);
    }
  };

  return (
    <div className="p-6 md:p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-100">知识库</h1>
        <p className="mt-1 text-sm text-zinc-500">左侧管理您上传的文档（默认在私人知识库）；右侧查看大文档 RAG 包（docling 产物）。</p>
      </div>

      <div className="mb-4">
        <KbInProgressBanner />
      </div>

      {msg && (
        <p
          className={`mb-4 text-sm ${
            msg.type === "success" ? "text-emerald-400" : msg.type === "info" ? "text-zinc-300" : "text-red-400"
          }`}
        >
          {msg.text}
        </p>
      )}

      <div className="grid gap-6 md:grid-cols-2">
        <section className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="mb-1 text-lg font-medium text-zinc-200">文件夹</h2>
              <p className="text-sm text-zinc-500">知识库以文件夹组织；共享与移动都以文件夹为入口。</p>
            </div>
            <button
              type="button"
              onClick={createNewFolder}
              className="shrink-0 rounded border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-sm text-zinc-200 hover:bg-zinc-700"
            >
              新建文件夹
            </button>
          </div>

          <div className="mt-4 rounded-lg border border-zinc-800 bg-zinc-950/30 p-3">
            <div className="mb-2 text-sm text-zinc-300">我的上传进度（全局）</div>
            {myDocs.length === 0 ? (
              <div className="text-xs text-zinc-500">暂无上传记录</div>
            ) : (
              <ul className="space-y-1">
                {myDocs.slice(0, 6).map((d) => (
                  <li key={`global-${d.doc_id}`} className="flex items-center justify-between gap-2 text-xs">
                    <span className="truncate text-zinc-400">{d.original_filename || d.title}</span>
                    <span
                      className={`inline-flex rounded border px-1.5 py-0.5 ${
                        (d.status || "").toLowerCase() === "active"
                          ? "border-emerald-800/60 bg-emerald-900/20 text-emerald-300"
                          : (d.status || "").toLowerCase() === "failed"
                          ? "border-red-900/50 bg-red-900/20 text-red-300"
                          : "border-zinc-700 bg-zinc-900 text-zinc-300"
                      }`}
                    >
                      {statusLabel(d.status)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="mt-4 grid gap-4 md:grid-cols-[220px_1fr]">
            <aside className="rounded-lg border border-zinc-800 bg-zinc-950/30 p-2">
              {loading ? (
                <div className="p-2 text-sm text-zinc-500">加载中…</div>
              ) : folders.length === 0 ? (
                <div className="p-2 text-sm text-zinc-500">暂无文件夹</div>
              ) : (
                <div className="space-y-1">
                  {folders.map((f) => (
                    <button
                      key={f.folder_id}
                      type="button"
                      onClick={() => setActiveFolderId(f.folder_id)}
                      className={[
                        "w-full text-left rounded-md border px-2 py-2",
                        f.folder_id === activeFolderId ? "border-zinc-700 bg-zinc-900/60" : "border-zinc-900 bg-zinc-950/10 hover:bg-zinc-900/30",
                      ].join(" ")}
                    >
                      <div className="truncate text-sm text-zinc-200">{f.name}</div>
                      <div className="mt-0.5 text-xs text-zinc-500">
                        文档 {f.resource_counts?.doc ?? 0}
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </aside>

            <div className="rounded-lg border border-zinc-800 bg-zinc-950/30 p-3">
              {!activeFolderId ? (
                <div className="text-sm text-zinc-500">请选择一个文件夹</div>
              ) : folderLoading ? (
                <div className="text-sm text-zinc-500">加载文件夹内容…</div>
              ) : !folderDetail ? (
                <div className="text-sm text-zinc-500">暂无内容</div>
              ) : (
                <>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="min-w-0">
                      <div className="truncate text-sm text-zinc-200">{folderDetail.folder?.name}</div>
                      <div className="text-xs text-zinc-500 font-mono">{folderDetail.folder?.folder_id}</div>
                    </div>
                    <div className="flex gap-2">
                      <input
                        ref={folderFileInputRef}
                        type="file"
                        className="hidden"
                        onChange={(e) => {
                          const f = e.target.files?.[0];
                          e.target.value = "";
                          if (f) uploadToActiveFolder(f);
                        }}
                      />
                      <button
                        type="button"
                        disabled={folderUploadBusy}
                        onClick={() => folderFileInputRef.current?.click()}
                        className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-200 hover:bg-zinc-800 disabled:opacity-50"
                      >
                        {folderUploadBusy ? "上传中…" : "上传文档"}
                      </button>
                      <button
                        type="button"
                        onClick={() => renameFolder(folderDetail.folder)}
                        className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-200 hover:bg-zinc-800"
                      >
                        重命名
                      </button>
                      <button
                        type="button"
                        onClick={() => openShareFolder(folderDetail.folder)}
                        className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-200 hover:bg-zinc-800"
                      >
                        共享
                      </button>
                      <button
                        type="button"
                        onClick={bringCurrentFolderToAi}
                        className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-200 hover:bg-zinc-800"
                        title="将当前文件夹写入统一范围并打开 AI 互动"
                      >
                        带到 AI 互动
                      </button>
                      {folderDetail.folder?.kind && folderDetail.folder.kind !== "Private" ? (
                        <button
                          type="button"
                          onClick={unshareActiveFolder}
                          className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-200 hover:bg-zinc-800"
                        >
                          取消共享
                        </button>
                      ) : null}
                      <button
                        type="button"
                        onClick={() => deleteFolder(folderDetail.folder)}
                        className="rounded border border-red-900/50 bg-red-900/20 px-2 py-1 text-xs text-red-300 hover:bg-red-900/40"
                      >
                        删除文件夹
                      </button>
                    </div>
                  </div>

                  <div className="mt-3">
                    {folderDetail.docs.length === 0 ? (
                      <div className="text-sm text-zinc-500">该文件夹暂无文档。你可以点击上方「上传文档」直接上传。</div>
                    ) : (
                      <ul className="space-y-2">
                        {folderDetail.docs.map((d) => (
                          <li key={d.doc_id} className="rounded-md border border-zinc-800 bg-zinc-900/30 px-3 py-2 text-sm">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <div className="min-w-0">
                                <div className="truncate text-zinc-200">{d.title}</div>
                                <div className="text-xs text-zinc-500">{d.original_filename}</div>
                                <div className="mt-1 flex items-center gap-2">
                                  <span
                                    className={`inline-flex rounded border px-1.5 py-0.5 text-[11px] ${
                                      (d.status || "").toLowerCase() === "active"
                                        ? "border-emerald-800/60 bg-emerald-900/20 text-emerald-300"
                                        : (d.status || "").toLowerCase() === "failed"
                                        ? "border-red-900/50 bg-red-900/20 text-red-300"
                                        : "border-zinc-700 bg-zinc-900 text-zinc-300"
                                    }`}
                                  >
                                    {statusLabel(d.status)}
                                  </span>
                                  {(d.status || "").toLowerCase() === "failed" && d.last_error ? (
                                    <span className="text-[11px] text-red-300 truncate max-w-[360px]" title={d.last_error}>
                                      {d.last_error}
                                    </span>
                                  ) : null}
                                </div>
                              </div>
                              <div className="flex items-center gap-2">
                                <select
                                  className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-200"
                                  defaultValue=""
                                  onChange={(e) => {
                                    const target = e.target.value;
                                    if (target) moveDocToFolder(d.doc_id, target);
                                    e.currentTarget.value = "";
                                  }}
                                >
                                  <option value="">移动到…</option>
                                  {folders
                                    .filter((f) => f.folder_id !== activeFolderId)
                                    .map((f) => (
                                      <option key={f.folder_id} value={f.folder_id}>
                                        {f.name}
                                      </option>
                                    ))}
                                </select>
                                <button
                                  type="button"
                                  onClick={() => handleDelete(d.doc_id)}
                                  className="rounded border border-red-900/50 bg-red-900/20 px-2 py-1 text-xs text-red-300 hover:bg-red-900/40"
                                >
                                  删除
                                </button>
                              </div>
                            </div>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </>
              )}
            </div>
          </div>
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
                    setRagDetail((prev) => ({ ...(prev || {}), _preview: null }));
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
                    setRagDetail((prev) => ({ ...(prev || {}), _preview: null }));
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
                    setRagDetail((prev) => ({ ...(prev || {}), _preview: null }));
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
                onClick={() => {
                  if (!ragDetail.package_id) return;
                  previewRagText(ragDetail.package_id, "merged");
                }}
                className="rounded border border-zinc-700 bg-zinc-800/60 px-3 py-2 text-sm text-zinc-200 hover:bg-zinc-700"
              >
                预览 merged（archive/full.md）
              </button>
              {Array.isArray(ragDetail?.sections) && ragDetail.sections.length > 0 ? (
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs text-zinc-500">sections：</span>
                  {ragDetail.sections
                    .slice(0, 10)
                    .map((s: { filename: string; size_bytes?: number }) => (
                    <button
                      key={s.filename}
                      type="button"
                      onClick={() => {
                        if (!ragDetail.package_id) return;
                        previewRagText(ragDetail.package_id, "section", s.filename);
                      }}
                      className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs font-mono text-zinc-200 hover:bg-zinc-800"
                      title={`${s.filename} (${s.size_bytes ?? 0} bytes)`}
                    >
                      {String(s.filename).replace(".md", "")}
                    </button>
                  ))}
                  {ragDetail.sections.length > 10 ? <span className="text-xs text-zinc-500">…</span> : null}
                </div>
              ) : null}
              {typeof ragDetail?.created_by_task_id === "string" && ragDetail.created_by_task_id ? (
                <button
                  type="button"
                  onClick={() => retryBigPdfTask(ragDetail.created_by_task_id as string)}
                  className="rounded border border-zinc-700 bg-zinc-800/60 px-3 py-2 text-sm text-zinc-200 hover:bg-zinc-700"
                >
                  重试该任务
                </button>
              ) : null}
            </div>

            {typeof (ragDetail?._preview as any)?.text === "string" ? (
              <div className="mt-4 rounded border border-zinc-800 bg-zinc-950/40 p-3">
                <div className="mb-2 flex items-center justify-between text-xs text-zinc-400">
                  <span>
                    预览：{String((ragDetail?._preview as any)?.filename ?? "")}
                    {(ragDetail?._preview as any)?.truncated ? "（已截断）" : ""}
                  </span>
                  <button
                    type="button"
                    onClick={() => setRagDetail((prev) => ({ ...(prev || {}), _preview: null }))}
                    className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-800"
                  >
                    清除预览
                  </button>
                </div>
                <pre className="max-h-[40vh] overflow-auto whitespace-pre-wrap break-words text-xs text-zinc-200">
                  {String((ragDetail?._preview as any)?.text ?? "")}
                </pre>
              </div>
            ) : null}

            <div className="mt-4 rounded border border-zinc-800 bg-zinc-950/40 p-3 text-xs text-zinc-400">
              <div>产物路径（后端）：{String((ragDetail as any)?.paths?.root ?? "")}</div>
              <div>sections：{Array.isArray(ragDetail.sections) ? ragDetail.sections.length : 0}</div>
            </div>

            <div className="mt-4 flex flex-wrap justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  if (!ragDetail.package_id) return;
                  downloadRagExport(ragDetail.package_id, ragExportKind);
                }}
                className="rounded border border-zinc-700 bg-zinc-800/60 px-3 py-2 text-sm text-zinc-200 hover:bg-zinc-700"
              >
                下载
              </button>
              <button
                type="button"
                onClick={() => {
                  if (!ragDetail.package_id) return;
                  deleteRagPackage(ragDetail.package_id);
                }}
                className="rounded border border-red-900/50 bg-red-900/20 px-3 py-2 text-sm text-red-300 hover:bg-red-900/40"
              >
                删除整个资源包
              </button>
            </div>
          </div>
        </div>
      )}

      {(shareDoc || shareFolder) && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-lg border border-zinc-700 bg-zinc-900 p-5 shadow-xl">
            <h3 className="text-lg font-medium text-zinc-100">{shareFolder ? "共享文件夹" : "共享文档"}</h3>
            <p className="mt-1 text-sm text-zinc-500">{shareFolder ? shareFolder.name : shareDoc?.title}</p>
            <div className="mt-4 space-y-3">
              {shareFolder ? (
                <div className="space-y-3">
                  <div>
                    <div className="mb-1 block text-xs text-zinc-400">共享到</div>
                    <div className="flex flex-wrap gap-3 text-sm text-zinc-200">
                      <label className="flex items-center gap-2">
                        <input type="radio" checked={folderShareTarget === "company"} onChange={() => setFolderShareTarget("company")} />
                        公司
                      </label>
                      <label className="flex items-center gap-2">
                        <input type="radio" checked={folderShareTarget === "department"} onChange={() => setFolderShareTarget("department")} />
                        部门
                      </label>
                      <label className="flex items-center gap-2">
                        <input type="radio" checked={folderShareTarget === "project"} onChange={() => setFolderShareTarget("project")} />
                        项目
                      </label>
                    </div>
                  </div>

                  {folderShareTarget === "department" ? (
                    <div>
                      <div className="mb-1 text-xs text-zinc-400">部门（可多选）</div>
                      <div className="flex flex-wrap gap-2">
                        {departmentChoices.map((d) => (
                          <label key={d} className="flex cursor-pointer items-center gap-1.5 text-xs text-zinc-300">
                            <input type="checkbox" checked={shareDepts.includes(d)} onChange={() => toggleDept(d)} />
                            {d}
                          </label>
                        ))}
                      </div>
                    </div>
                  ) : null}

                  {folderShareTarget === "project" ? (
                    <div>
                      <div className="mb-1 text-xs text-zinc-400">项目（可多选）</div>
                      <div className="flex flex-wrap gap-2">
                        {projectChoices.map((p) => (
                          <label key={p.project_id} className="flex cursor-pointer items-center gap-1.5 text-xs text-zinc-300">
                            <input type="checkbox" checked={shareProjs.includes(p.project_id)} onChange={() => toggleProj(p.project_id)} />
                            {p.name}
                          </label>
                        ))}
                      </div>
                    </div>
                  ) : null}

                  <div className="text-xs text-zinc-500">提示：共享以文件夹为单位，文件夹内所有文档权限一致。</div>
                </div>
              ) : (
                <>
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
                </>
              )}
            </div>
            <div className="mt-6 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setShareDoc(null);
                  setShareFolder(null);
                }}
                className="rounded border border-zinc-600 px-3 py-1.5 text-sm text-zinc-300"
              >
                取消
              </button>
              <button
                type="button"
                disabled={shareFolder ? (folderShareTarget === "department" ? shareDepts.length === 0 : folderShareTarget === "project" ? shareProjs.length === 0 : false) : !shareKind}
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
