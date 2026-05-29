"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { getAuthHeaders } from "../lib/auth";
import { KbInProgressBanner } from "../components/KbInProgressBanner";
import { useSmartPoll } from "../lib/smartPoll";
import {
  buildAiInteractionHref,
  writeKbScopeCapsule,
} from "../lib/kb_scope_capsule";
import { MoveCopyModal } from "./components/MoveCopyModal";
import { sortKbKindsPinned } from "./lib/kb_sort";
import { pickDeptDefaultFolderName } from "./lib/default_folders";
import { computeDefaultScopeKinds } from "./lib/kb_default_scope";
import { folderViewHeading, optimisticRemoveDocFromFolderDetail } from "./lib/kb_folder_view";
import { formatHttpError } from "./lib/kb_http_error";
import { computeMenuPosition } from "./lib/kb_menu_position";
import {
  folderBulkCheckState,
  folderBulkToggleAll,
  visibleFolderIdSet,
} from "./lib/private_root_docs";
import {
  isPrivateKbRootSelection,
  pickPrivateRootDocs,
  resolveDocsForActiveKb,
  toFolderDetailDocRows,
} from "./lib/kb_docs_for_panel.js";
import { FileText, Search } from "lucide-react";
import { KbBrowseTree } from "./components/KbBrowseTree";

type MyDoc = {
  doc_id: string;
  title: string;
  original_filename?: string;
  size_bytes?: number;
  status?: string;
  last_error?: string | null;
  created_at?: string | null;
  collection_ids?: string[];
  /** 文档绑定的文件夹（可多文件夹：复制链接后） */
  folder_ids?: string[];
};

type FolderItem = {
  folder_id: string;
  name: string;
  kind?: string | null;
  owner_username?: string | null;
  collection_ids?: string[];
  resource_counts?: Record<string, number>;
  subtree_doc_count?: number;
  parent_folder_id?: string | null;
};

type FolderResourcesResponse = {
  folder: FolderItem;
  resources: Array<{ resource_type: string; resource_id: string; created_at?: string | null }>;
  docs: Array<{ doc_id: string; title: string; original_filename?: string; size_bytes?: number; status?: string; last_error?: string | null; created_at?: string | null }>;
  subfolders?: FolderItem[];
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

const KB_KIND_PRIVATE = "Private";
const DEFAULT_PRIVATE_FOLDER_NAME = "合同管理";
const KB_KIND_DEPT_PUBLIC = "DeptPublic";

function isInternalPrivatePlaceholderFolder(f: { folder_id?: string; name?: string } | null | undefined) {
  const id = (f?.folder_id || "").trim();
  const name = (f?.name || "").trim();
  return id.startsWith("f_private_") && name === "我的私人知识库";
}

const DEFAULT_SCOPE_ORDER = ["Private", "DeptPublic", "ProjectPublic", "CompanyPublic"] as const;

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

function formatLogTime(iso?: string | null) {
  if (!iso) return "—";
  try {
    return iso.replace("T", " ").slice(0, 19);
  } catch {
    return "—";
  }
}

function docIsActive(s?: string) {
  return (s || "").toLowerCase() === "active";
}

function docDedupeKey(d: { original_filename?: string; title?: string; doc_id: string }) {
  const n = (d.original_filename || d.title || "").trim();
  return n || d.doc_id;
}

function parseTimeMs(iso?: string | null) {
  if (!iso) return 0;
  const t = Date.parse(iso);
  return Number.isFinite(t) ? t : 0;
}

export type KnowledgePageProps = {
  mode?: "embedded" | "page";
  initialFolderId?: string | null;
};

export default function KnowledgePage() {
  const sp = useSearchParams();
  const router = useRouter();
  const [myDocs, setMyDocs] = useState<MyDoc[]>([]);
  const [kbKinds, setKbKinds] = useState<KbKindItem[]>([]);
  const [collections, setCollections] = useState<OptCol[]>([]);
  const [me, setMe] = useState<MeOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState<{ type: "success" | "error" | "info"; text: string } | null>(null);
  // 大 PDF 文档包管理已迁移至 AI 互动工作空间 Tab（见 /ai-interaction）。

  const [shareDoc, setShareDoc] = useState<MyDoc | null>(null);
  const [shareFolder, setShareFolder] = useState<FolderItem | null>(null);
  const [shareKind, setShareKind] = useState("");
  const [shareDepts, setShareDepts] = useState<string[]>([]);
  const [shareProjs, setShareProjs] = useState<string[]>([]);
  const [shareCompany, setShareCompany] = useState(false);
  const [folderShareTarget, setFolderShareTarget] = useState<"company" | "department" | "project">("company");
  const [folderShareAccessKind, setFolderShareAccessKind] = useState<"public" | "lead">("public");
  const [folderMoveOpen, setFolderMoveOpen] = useState(false);
  const [folderMoveFolder, setFolderMoveFolder] = useState<FolderItem | null>(null);
  const [folderMoveTarget, setFolderMoveTarget] = useState<"private" | "company" | "department" | "project">("private");
  const [folderMoveDepts, setFolderMoveDepts] = useState<string[]>([]);
  const [folderMoveProjs, setFolderMoveProjs] = useState<string[]>([]);
  const [folderMoveAccessKind, setFolderMoveAccessKind] = useState<"public" | "lead">("public");

  const [folders, setFolders] = useState<FolderItem[]>([]);
  const [selection, setSelection] = useState<{ kind: "kb"; kb_kind: string } | { kind: "folder"; kb_kind: string; folder_id: string }>(
    { kind: "kb", kb_kind: KB_KIND_PRIVATE },
  );
  const [folderDetail, setFolderDetail] = useState<FolderResourcesResponse | null>(null);
  const [folderLoading, setFolderLoading] = useState(false);
  const [folderUploadBusy, setFolderUploadBusy] = useState(false);
  const [folderUploadProgress, setFolderUploadProgress] = useState<{ current: number; total: number; pct: number } | null>(null);
  const folderFileInputRef = useRef<HTMLInputElement>(null);
  const [isPageVisible, setIsPageVisible] = useState(true);

  /** v3：范围 chips 默认选中顺序：私人→部门公共→项目公共(若有)→公司公共 */
  const [scopeKinds, setScopeKinds] = useState<string[]>([]);
  const [kbGlobalSearch, setKbGlobalSearch] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const scopeInitRef = useRef(false);

  // 三点菜单 + 选择目标弹层
  // openMenu.id 使用复合 key，避免同一 doc 在多处出现时冲突：doc_id|loose 或 doc_id|<folder_id>
  const [openMenu, setOpenMenu] = useState<null | { kind: "doc" | "folder" | "kb"; id: string }>(null);
  const [menuPos, setMenuPos] = useState<null | { top: number; left: number; placement: "up" | "down" }>(null);
  const [docTargetModal, setDocTargetModal] = useState<null | { doc_id: string; mode: "move" | "copy"; source_folder_id?: string }>(null);
  const [docTargetKbKind, setDocTargetKbKind] = useState<string>("");
  const [docTargetFolderId, setDocTargetFolderId] = useState<string>("");

  const menuPanelRef = useRef<HTMLDivElement | null>(null);
  const [bulkSelection, setBulkSelection] = useState<{ doc_ids: string[]; source_folder_id?: string | null }>({ doc_ids: [], source_folder_id: null });
  const urlFolderInitRef = useRef(false);
  const userHasInteractedRef = useRef(false);
  const folderDetailReqRef = useRef(0);

  useEffect(() => {
    // 点击空白处关闭菜单（否则会“关不上”）
    if (!openMenu) return;
    const onDown = (ev: MouseEvent) => {
      const t = ev.target as HTMLElement | null;
      if (!t) return;
      if (t.closest("[data-kb-menu-root='1']")) return;
      setOpenMenu(null);
      setMenuPos(null);
    };
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === "Escape") {
        setOpenMenu(null);
        setMenuPos(null);
      }
    };
    window.addEventListener("mousedown", onDown, true);
    window.addEventListener("keydown", onKey, true);
    return () => {
      window.removeEventListener("mousedown", onDown, true);
      window.removeEventListener("keydown", onKey, true);
    };
  }, [openMenu]);

  const openAnchoredMenu = useCallback(
    (next: { kind: "doc" | "folder" | "kb"; id: string } | null, anchor: HTMLElement | null) => {
      if (!next) {
        setOpenMenu(null);
        setMenuPos(null);
        return;
      }
      if (!anchor) {
        setOpenMenu(next);
        setMenuPos(null);
        return;
      }
      const rect = anchor.getBoundingClientRect();
      const pos0 = computeMenuPosition({
        anchorTop: rect.top,
        anchorLeft: rect.left,
        anchorBottom: rect.bottom,
        anchorWidth: rect.width,
        menuWidth: 176,
        menuHeight: 200,
        viewportWidth: window.innerWidth,
        viewportHeight: window.innerHeight,
        gap: 8,
      });
      setMenuPos(pos0);
      setOpenMenu(next);
      requestAnimationFrame(() => {
        const menuEl = menuPanelRef.current;
        const menuRect = menuEl?.getBoundingClientRect();
        const pos1 = computeMenuPosition({
          anchorTop: rect.top,
          anchorLeft: rect.left,
          anchorBottom: rect.bottom,
          anchorWidth: rect.width,
          menuWidth: menuRect?.width ?? 176,
          menuHeight: menuRect?.height ?? 160,
          viewportWidth: window.innerWidth,
          viewportHeight: window.innerHeight,
          gap: 8,
        });
        setMenuPos(pos1);
      });
    },
    [],
  );

  const bringFolderToAi = useCallback(
    (folderId: string) => {
      // “带到 AI”应以当前文件夹为准，避免把历史选择也一并带过去导致误判“没带上”
      writeKbScopeCapsule({ folder_ids: [folderId], collection_ids: [], table_ids: [] });
      router.push(buildAiInteractionHref({ folder_ids: [folderId] }) + "&view=chat");
      openAnchoredMenu(null, null);
    },
    [router, openAnchoredMenu],
  );

  const bringDocsToAi = useCallback(
    (docIds: string[]) => {
      const ids = Array.from(new Set((docIds || []).map((x) => (x || "").trim()).filter(Boolean)));
      if (!ids.length) {
        setMsg({ type: "info", text: "请先选择要带到 AI 互动的文档。" });
        return;
      }
      const q = new URLSearchParams();
      q.set("doc_ids", ids.join(","));
      q.set("view", "chat");
      router.push(`/ai-interaction?${q.toString()}`);
      openAnchoredMenu(null, null);
    },
    [router, openAnchoredMenu],
  );

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

  const kbKindLabelById = useMemo(() => {
    const m = new Map<string, string>();
    for (const it of kbKinds) m.set(it.kb_kind, it.label || it.kb_kind);
    if (!m.has(KB_KIND_PRIVATE)) m.set(KB_KIND_PRIVATE, "私人知识库");
    return m;
  }, [kbKinds]);

  const visibleFolderIds = useMemo(() => visibleFolderIdSet(folders), [folders]);

  const foldersByKind = useMemo(() => {
    const m = new Map<string, FolderItem[]>();
    for (const f of folders) {
      const k = (f.kind || "Private").trim() || "Private";
      m.set(k, [...(m.get(k) || []), f]);
    }
    for (const [, arr] of m.entries()) arr.sort((a, b) => String(a.name || "").localeCompare(String(b.name || ""), "zh"));
    return m;
  }, [folders]);

  const activeKbKind = selection.kb_kind;
  const activeFolderId = selection.kind === "folder" ? selection.folder_id : null;

  const safeFolderDetail = useMemo(() => {
    if (!folderDetail?.folder?.folder_id) return null;
    const fid = String(folderDetail.folder.folder_id);
    if (activeFolderId) return fid === activeFolderId ? folderDetail : null;
    return fid === "__private_root__" ? folderDetail : null;
  }, [folderDetail, activeFolderId]);

  const activeFolderItem = useMemo(
    () => (activeFolderId ? folders.find((x) => x.folder_id === activeFolderId) ?? null : null),
    [folders, activeFolderId],
  );

  const folderForActions: FolderItem | null = safeFolderDetail?.folder ?? activeFolderItem;

  const folderHasRunningDocs = useMemo(() => {
    if (!safeFolderDetail?.docs?.length) return false;
    return safeFolderDetail.docs.some((d) => docIsRunning(d));
  }, [docIsRunning, safeFolderDetail?.docs]);

  const privateRootDocs = useMemo(
    () =>
      pickPrivateRootDocs(myDocs, visibleFolderIds, {
        includeRunning: true,
        docDedupeKey,
        parseTimeMs,
      }),
    [myDocs, visibleFolderIds],
  );

  const isPrivateKbRootView = isPrivateKbRootSelection(selection.kind, activeKbKind);

  // 后端 /meta/kb-kinds 不含 Private（仅列共享类 kind），但文件夹 API 会返回 kind=Private；必须合并否则「私人知识库」整块不渲染。
  const allKbKindsOrdered = useMemo(() => {
    const apiKinds = kbKinds.map((k) => k.kb_kind).filter(Boolean);
    const folderKinds = Array.from(foldersByKind.keys());
    const merged = Array.from(new Set<string>([KB_KIND_PRIVATE, ...apiKinds, ...folderKinds]));
    return sortKbKindsPinned(merged);
  }, [kbKinds, foldersByKind]);

  useEffect(() => {
    // v4：确保“默认四库全选”真正生效；当 scopeKinds 为空时强制初始化一次
    if (scopeInitRef.current && scopeKinds.length) return;
    // 避免 “只拿到 Private” 时过早初始化，导致后续 kinds 加载完也不会补全默认四库
    if (loading) return;
    if (!allKbKindsOrdered.length) return;
    const hasProjectAccess = Boolean((me?.projects || []).length) && allKbKindsOrdered.includes("ProjectPublic");
    const picked = computeDefaultScopeKinds({ availableKinds: allKbKindsOrdered, hasProjectAccess });
    setScopeKinds(picked.length ? picked : ["Private"]);
    setSelection({ kind: "kb", kb_kind: picked[0] || "Private" });
    scopeInitRef.current = true;
  }, [allKbKindsOrdered, me?.projects, scopeKinds.length, loading]);

  const kindsVisibleInTree = useMemo(() => {
    const picked = allKbKindsOrdered.filter((k) => scopeKinds.includes(k));
    return picked.length ? picked : allKbKindsOrdered;
  }, [allKbKindsOrdered, scopeKinds]);

  const toggleScopeKind = useCallback((kid: string) => {
    setScopeKinds((prev) => {
      const next = prev.includes(kid) ? prev.filter((x) => x !== kid) : [...prev, kid];
      if (!prev.includes(kid)) setSelection({ kind: "kb", kb_kind: kid });
      else if (activeKbKind === kid) setSelection({ kind: "kb", kb_kind: next[0] || KB_KIND_PRIVATE });
      return next;
    });
  }, [activeKbKind]);

  const privateRootAsFolderDetail: FolderResourcesResponse = useMemo(
    () => ({
      folder: {
        folder_id: "__private_root__",
        name: "私人知识库",
        kind: KB_KIND_PRIVATE,
      },
      resources: [],
      docs: toFolderDetailDocRows(privateRootDocs),
    }),
    [privateRootDocs],
  );

  const docsForActiveKb = useMemo(
    () =>
      resolveDocsForActiveKb({
        selectionKind: selection.kind,
        activeKbKind: activeKbKind || KB_KIND_PRIVATE,
        folderDocs: safeFolderDetail?.docs,
        privateRootDocs,
        myDocs,
        folders,
        docIsActive,
        docIsRunning,
      }),
    [
      selection.kind,
      activeKbKind,
      safeFolderDetail?.docs,
      privateRootDocs,
      myDocs,
      folders,
      docIsRunning,
    ],
  );

  const docsFilteredForTable = useMemo(() => {
    const raw = docsForActiveKb || [];
    const q = kbGlobalSearch.trim().toLowerCase();
    if (!q) return raw;
    return raw.filter((d) => {
      const blob = `${d.original_filename || ""} ${d.title || ""} ${d.doc_id}`.toLowerCase();
      return blob.includes(q);
    });
  }, [docsForActiveKb, kbGlobalSearch]);

  const toggleBulkDoc = useCallback((docId: string, source_folder_id: string | null) => {
    const did = (docId || "").trim();
    if (!did) return;
    setBulkSelection((prev) => {
      const src0 = (prev.source_folder_id || null) as string | null;
      const srcN = source_folder_id || null;
      // 跨上下文点击：先清空旧选择（避免“不同文件夹/未归类混选”导致语义不清）
      const base = src0 === srcN ? prev.doc_ids : [];
      const next = base.includes(did) ? base.filter((x) => x !== did) : [...base, did];
      return { doc_ids: next, source_folder_id: srcN };
    });
  }, []);

  const clearBulkSelection = useCallback(() => setBulkSelection({ doc_ids: [], source_folder_id: null }), []);

  const bulkContextFolderId = useMemo((): string | null | undefined => {
    if (activeFolderId && selection.kind === "folder") return activeFolderId;
    if (isPrivateKbRootView) return null;
    return undefined;
  }, [activeFolderId, isPrivateKbRootView, selection.kind]);

  const folderDocIdsForBulk = useMemo(() => {
    if (activeFolderId && selection.kind === "folder") {
      return (safeFolderDetail?.docs || []).map((d) => d.doc_id).filter(Boolean);
    }
    if (isPrivateKbRootView) {
      return docsFilteredForTable.map((d) => d.doc_id).filter(Boolean);
    }
    return [];
  }, [activeFolderId, selection.kind, safeFolderDetail?.docs, isPrivateKbRootView, docsFilteredForTable]);

  const folderBulkHeaderState = useMemo(() => {
    if (bulkContextFolderId === undefined) return "none" as const;
    if (!folderDocIdsForBulk.length) return "none" as const;
    const ctx = bulkContextFolderId ?? null;
    const selected =
      (bulkSelection.source_folder_id || null) === ctx ? bulkSelection.doc_ids.filter(Boolean) : [];
    return folderBulkCheckState(folderDocIdsForBulk, selected);
  }, [bulkContextFolderId, bulkSelection.doc_ids, bulkSelection.source_folder_id, folderDocIdsForBulk]);

  const folderBulkHeaderRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const el = folderBulkHeaderRef.current;
    if (!el) return;
    el.indeterminate = folderBulkHeaderState === "partial";
  }, [folderBulkHeaderState]);

  const toggleFolderBulkAll = useCallback(() => {
    if (bulkContextFolderId === undefined || !folderDocIdsForBulk.length) return;
    const next = folderBulkToggleAll(folderBulkHeaderState, folderDocIdsForBulk);
    setBulkSelection({ doc_ids: next, source_folder_id: bulkContextFolderId ?? null });
  }, [bulkContextFolderId, folderBulkHeaderState, folderDocIdsForBulk]);

  const folderNameById = useMemo(() => {
    const m = new Map<string, string>();
    for (const f of folders) m.set(f.folder_id, f.name || f.folder_id);
    return m;
  }, [folders]);

  const docPrimaryFolderNameById = useMemo(() => {
    const kind = (activeKbKind || KB_KIND_PRIVATE).trim() || KB_KIND_PRIVATE;
    const folderKindById = new Map<string, string>();
    for (const f of folders) folderKindById.set(f.folder_id, (f.kind || KB_KIND_PRIVATE).trim() || KB_KIND_PRIVATE);
    const m = new Map<string, string>();
    for (const d of myDocs) {
      const did = (d.doc_id || "").trim();
      if (!did) continue;
      const fids = Array.isArray(d.folder_ids) ? d.folder_ids : [];
      const hit = fids.find((fid) => (folderKindById.get(String(fid)) || KB_KIND_PRIVATE) === kind);
      if (!hit) continue;
      const name = folderNameById.get(String(hit));
      if (name) m.set(did, name);
    }
    return m;
  }, [activeKbKind, folders, myDocs, folderNameById]);

  /** 低调日志：每行一条，避免与文件夹内列表重复大块展示 */
  const uploadLogLines = useMemo(() => {
    return myDocs.slice(0, 80).map((d) => {
      const t = formatLogTime(d.created_at);
      const tail = d.doc_id.length > 10 ? `${d.doc_id.slice(0, 10)}…` : d.doc_id;
      const name = (d.original_filename || d.title || "").trim() || "(无文件名)";
      return `${t}  ${tail}  ${name}  ${statusLabel(d.status)}`;
    });
  }, [myDocs]);

  const fetchFolderDetail = useCallback(async (folderId: string): Promise<FolderResourcesResponse> => {
    const res = await fetch(`/api/knowledge/folders/${encodeURIComponent(folderId)}/resources`, {
      credentials: "include",
      headers: getAuthHeaders(),
    });
    const resClone = res.clone();
    const asJson = await res.json().catch(() => null);
    const data = (asJson || {}) as Partial<FolderResourcesResponse> & { detail?: string };
    if (!res.ok) {
      const detail = typeof data.detail === "string" ? data.detail : "";
      if (detail) throw new Error(`HTTP ${res.status}：${detail}`);
      const txt = await resClone.text().catch(() => "");
      const brief = (txt || "").trim().slice(0, 200);
      throw new Error(`HTTP ${res.status}${brief ? `：${brief}` : ""}`);
    }
    return data as FolderResourcesResponse;
  }, []);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [meRes, docsRes, kindsRes, optRes, foldersRes] = await Promise.all([
        fetch("/api/auth/me", { credentials: "include", headers: getAuthHeaders() }),
        fetch("/api/knowledge/my-documents", { credentials: "include", headers: getAuthHeaders() }),
        fetch("/api/knowledge/meta/kb-kinds", { credentials: "include", headers: getAuthHeaders() }),
        fetch("/api/knowledge/options", { credentials: "include", headers: getAuthHeaders() }),
        fetch("/api/knowledge/folders", { credentials: "include", headers: getAuthHeaders() }),
      ]);
      if (meRes.ok) setMe(await meRes.json());
      if (docsRes.ok) {
        const d = await docsRes.json();
        const raw = (d.items ?? []) as MyDoc[];
        setMyDocs(
          raw.map((it) => ({
            ...it,
            folder_ids: Array.isArray(it.folder_ids) ? it.folder_ids.filter(Boolean) : [],
          })),
        );
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
        // 隐藏内部“我的私人知识库”占位 folder（用于动态私有 collection 绑定，不属于 UI 侧可管理对象）
        setFolders(
          items.filter((it) => {
            const fid = String(it?.folder_id || "").trim();
            const nm = String(it?.name || "").trim();
            return !(fid.startsWith("f_private_") && nm === "我的私人知识库");
          }),
        );
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // 私人知识库的默认文件夹兜底：若不存在「合同管理」则自动创建一次（避免“默认不见了”）
    // 仅在 folders 已加载、且页面已拿到 me.username 时触发；失败不阻断。
    if (!me?.username) return;
    if (!folders.length) return;
    const has = folders.some((f) => (f.kind || KB_KIND_PRIVATE) === KB_KIND_PRIVATE && (f.name || "").trim() === DEFAULT_PRIVATE_FOLDER_NAME);
    if (has) return;
    void (async () => {
      try {
        const res = await fetch("/api/knowledge/folders", {
          method: "POST",
          headers: { "Content-Type": "application/json", ...getAuthHeaders() },
          credentials: "include",
          body: JSON.stringify({ name: DEFAULT_PRIVATE_FOLDER_NAME }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) return;
        const fid = String((data as any).folder_id || "");
        if (!fid) return;
        await loadAll();
      } catch {
        // ignore
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [me?.username, folders.length]);

  useEffect(() => {
    // wangjia：部门公共知识库默认文件夹兜底（合同管理/合同台账）
    // 若 DeptPublic 下缺失目标名，则创建一个文件夹并分享为 DeptPublic（失败不阻断；不提示）。
    const username = (me?.username || "").trim();
    if (username !== "wangjia") return;
    const deptId = (me?.department || "").trim();
    if (!deptId) return;
    if (!folders.length) return;

    const existingNames = folders
      .filter((f) => (f.kind || KB_KIND_PRIVATE) === KB_KIND_DEPT_PUBLIC)
      .map((f) => String(f.name || "").trim())
      .filter(Boolean);
    const targetName = pickDeptDefaultFolderName({ username, existingNames, candidates: ["合同管理", "合同台账"] });
    if (!targetName) return;
    const exists = folders.some((f) => (f.kind || KB_KIND_PRIVATE) === KB_KIND_DEPT_PUBLIC && (f.name || "").trim() === targetName);
    if (exists) return;

    void (async () => {
      try {
        const res = await fetch("/api/knowledge/folders", {
          method: "POST",
          headers: { "Content-Type": "application/json", ...getAuthHeaders() },
          credentials: "include",
          body: JSON.stringify({ name: targetName }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) return;
        const fid = String((data as any).folder_id || "");
        if (!fid) return;

        await fetch(`/api/knowledge/folders/${encodeURIComponent(fid)}/share`, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...getAuthHeaders() },
          credentials: "include",
          body: JSON.stringify({ kb_kind: KB_KIND_DEPT_PUBLIC, department_ids: [deptId], project_ids: [], company_public: false }),
        }).catch(() => {});

        await loadAll();
      } catch {
        // ignore
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [me?.username, me?.department, folders.length]);

  useEffect(() => {
    const fid = (sp.get("folder_id") || "").trim();
    if (!fid || !folders.length) return;
    if (userHasInteractedRef.current) return;
    if (urlFolderInitRef.current) return;
    const hit = folders.find((f) => f.folder_id === fid);
    if (hit) {
      urlFolderInitRef.current = true;
      setSelection({ kind: "folder", kb_kind: (hit.kind || KB_KIND_PRIVATE) as string, folder_id: fid });
    }
  }, [sp, folders]);

  const loadFolderDetail = useCallback(
    async (folderId: string) => {
      if (!folderId) return;
      setFolderLoading(true);
      const reqId = ++folderDetailReqRef.current;
      try {
        const data = await fetchFolderDetail(folderId);
        if (reqId !== folderDetailReqRef.current) return;
        setFolderDetail(data);
        const subs = (data.subfolders || []) as FolderItem[];
        if (subs.length) {
          setFolders((prev) => {
            const ids = new Set(prev.map((x) => x.folder_id));
            const add = subs
              .filter((sf) => sf.folder_id && !ids.has(sf.folder_id))
              .map((sf) => ({
                ...sf,
                parent_folder_id: (sf.parent_folder_id || "").trim() || folderId,
              }));
            return add.length ? [...prev, ...add] : prev;
          });
        }
      } catch (e) {
        if (reqId !== folderDetailReqRef.current) return;
        setFolderDetail(null);
        const msg = e instanceof Error ? e.message : "加载失败";
        setMsg({ type: "error", text: `加载失败：${msg}（folder_id=${folderId}）` });
      } finally {
        if (reqId !== folderDetailReqRef.current) return;
        setFolderLoading(false);
      }
    },
    [fetchFolderDetail]
  );

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  useEffect(() => {
    if (!activeFolderId) {
      // v3：不再有“未归类”虚拟节点；私人知识库根级在未选中文件夹时展示
      if ((activeKbKind || KB_KIND_PRIVATE) === KB_KIND_PRIVATE) setFolderDetail(privateRootAsFolderDetail);
      else setFolderDetail(null);
      setFolderLoading(false);
      return;
    }
    void loadFolderDetail(activeFolderId);
  }, [activeFolderId, activeKbKind, loadFolderDetail, privateRootAsFolderDetail]);

  useSmartPoll<FolderResourcesResponse>({
    enabled:
      isPageVisible &&
      Boolean(activeFolderId) &&
      folderHasRunningDocs,
    pollKey: activeFolderId,
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
    initialData: safeFolderDetail ?? undefined,
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
    setFolderShareAccessKind("public");
    const u = me;
    setShareDepts(u?.department ? [u.department] : []);
    setShareProjs((u?.projects ?? []).map((p) => p.project_id).filter(Boolean));
    setShareCompany(false);
  };

  const openFolderMoveModal = (f: FolderItem | null) => {
    if (!f) return;
    setFolderMoveFolder(f);
    setFolderMoveTarget("private");
    setFolderMoveAccessKind("public");
    const u = me;
    setFolderMoveDepts(u?.department ? [u.department] : []);
    setFolderMoveProjs((u?.projects ?? []).map((p) => p.project_id).filter(Boolean));
    setFolderMoveOpen(true);
    openAnchoredMenu(null, null);
  };

  const toggleFolderMoveDept = (d: string) => {
    setFolderMoveDepts((prev) => (prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d]));
  };

  const toggleFolderMoveProj = (p: string) => {
    setFolderMoveProjs((prev) => (prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]));
  };

  const confirmFolderMoveToKb = async () => {
    const f = folderMoveFolder;
    if (!f?.folder_id) return;
    let kb_kind = "Private";
    let department_ids: string[] = [];
    let project_ids: string[] = [];
    let company_public = false;
    if (folderMoveTarget === "company") {
      kb_kind = "CompanyPublic";
      company_public = true;
    } else if (folderMoveTarget === "department") {
      kb_kind = folderMoveAccessKind === "lead" ? "DeptLead" : "DeptPublic";
      department_ids = folderMoveDepts;
      if (!department_ids.length) {
        setMsg({ type: "error", text: "请至少选择一个部门。" });
        return;
      }
    } else if (folderMoveTarget === "project") {
      kb_kind = folderMoveAccessKind === "lead" ? "ProjectLead" : "ProjectPublic";
      project_ids = folderMoveProjs;
      if (!project_ids.length) {
        setMsg({ type: "error", text: "请至少选择一个项目。" });
        return;
      }
    } else {
      kb_kind = "Private";
    }
    setMsg(null);
    try {
      const res = await fetch(`/api/knowledge/folders/${encodeURIComponent(f.folder_id)}/move-to-kb`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        credentials: "include",
        body: JSON.stringify({ kb_kind, department_ids, project_ids, company_public }),
      });
      const resClone = res.clone();
      const data = await res.json().catch(() => ({} as any));
      if (!res.ok) {
        const detail = typeof (data as any)?.detail === "string" ? (data as any).detail : "";
        const txt = await resClone.text().catch(() => "");
        throw new Error(formatHttpError({ status: res.status, detail, text: txt, fallback: "移动失败" }));
      }
      setMsg({ type: "success", text: "已将文件夹移动到目标知识库范围。" });
      setFolderMoveFolder(null);
      setFolderMoveOpen(false);
      await loadAll();
      if (activeFolderId === f.folder_id) await loadFolderDetail(f.folder_id);
    } catch (e) {
      setMsg({ type: "error", text: e instanceof Error ? e.message : "移动失败" });
    }
  };

  const revokeFolderShareAll = async (f: FolderItem) => {
    if (!f.folder_id) return;
    if (!confirm("确定一键全撤该文件夹的共享？（将撤回所有部门/项目/公司公共共享）")) return;
    setMsg(null);
    try {
      const res = await fetch(`/api/knowledge/folders/${encodeURIComponent(f.folder_id)}/unshare`, {
        method: "POST",
        credentials: "include",
        headers: getAuthHeaders(),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof (data as any).detail === "string" ? (data as any).detail : "回收共享失败");
      setMsg({ type: "success", text: "已回收共享（已回到私有可见范围）。" });
      await loadAll();
      if (activeFolderId) await loadFolderDetail(activeFolderId);
      setShareFolder(null);
    } catch (e) {
      setMsg({ type: "error", text: e instanceof Error ? e.message : "回收共享失败" });
    }
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
        ? `/api/knowledge/folders/${encodeURIComponent(shareFolder!.folder_id)}/share-add-scope`
        : `/api/knowledge/my-documents/${encodeURIComponent(shareDoc!.doc_id)}/share`;
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        credentials: "include",
        body: JSON.stringify(
          isFolder
            ? {
                target: folderShareTarget,
                access_kind: folderShareAccessKind,
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

  const deleteDoc = async (
    docId: string,
    opts?: { skipConfirm?: boolean; skipReload?: boolean; quietSuccess?: boolean },
  ): Promise<boolean> => {
    if (!opts?.skipConfirm && !confirm("确定删除该文档？")) return false;
    if (!opts?.quietSuccess) setMsg(null);
    try {
      const res = await fetch(`/api/knowledge/my-documents/${encodeURIComponent(docId)}`, {
        method: "DELETE",
        credentials: "include",
        headers: getAuthHeaders(),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "删除失败");
      if (!opts?.quietSuccess) setMsg({ type: "success", text: "已删除。" });
      if (!opts?.skipReload) {
        await loadAll();
        if (activeFolderId) await loadFolderDetail(activeFolderId);
      }
      return true;
    } catch (e) {
      setMsg({ type: "error", text: e instanceof Error ? e.message : "删除失败" });
      return false;
    }
  };

  const handleDelete = async (docId: string) => {
    await deleteDoc(docId);
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
    if (isInternalPrivatePlaceholderFolder(f)) {
      setMsg({ type: "error", text: "系统预留文件夹不可删除。" });
      return;
    }
    if (!confirm(`确定删除文件夹「${f.name}」？（仅删除文件夹绑定关系）`)) return;
    setMsg(null);
    try {
      const res = await fetch(`/api/knowledge/folders/${encodeURIComponent(f.folder_id)}`, {
        method: "DELETE",
        credentials: "include",
        headers: getAuthHeaders(),
      });
      const resClone = res.clone();
      const data = await res.json().catch(() => ({} as any));
      if (!res.ok) {
        const detail = typeof (data as any)?.detail === "string" ? (data as any).detail : "";
        const txt = await resClone.text().catch(() => "");
        throw new Error(formatHttpError({ status: res.status, detail, text: txt, fallback: "删除失败" }));
      }
      setMsg({ type: "success", text: "已删除文件夹。" });
      setSelection({ kind: "kb", kb_kind: KB_KIND_PRIVATE });
      setFolderDetail(null);
      await loadAll();
    } catch (e) {
      setMsg({ type: "error", text: e instanceof Error ? e.message : "删除失败" });
    }
  };

  const moveDocBetweenFolders = async (docId: string, sourceFolderId: string, targetFolderId: string) => {
    const src = (sourceFolderId || "").trim();
    const dst = (targetFolderId || "").trim();
    if (!src || !dst || src === dst) return;
    // 即时反馈：若当前正查看源文件夹，先本地移除该文档，避免误以为“复制”
    setFolderDetail((prev) => (activeFolderId === src ? optimisticRemoveDocFromFolderDetail(prev, docId) : prev));
    setMsg(null);
    try {
      const res = await fetch(`/api/knowledge/folders/${encodeURIComponent(src)}/move-resources`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        credentials: "include",
        body: JSON.stringify({ target_folder_id: dst, doc_ids: [docId] }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "移动失败");
      setMsg({ type: "success", text: "已移动文档。" });
      await loadAll();
      if (activeFolderId === src) await loadFolderDetail(src);
    } catch (e) {
      setMsg({ type: "error", text: e instanceof Error ? e.message : "移动失败" });
    }
  };

  const handleFolderFileUpload = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = Array.from(e.target.files || []);
      e.target.value = "";
      if (!files.length || !activeFolderId) return;
      const fid = activeFolderId;
      setFolderUploadBusy(true);
      let ok = 0;
      let fail = 0;
      const total = files.length;
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        setFolderUploadProgress({ current: i + 1, total, pct: Math.round(((i + 1) / total) * 100) });
        try {
          const doc_id = await new Promise<string>((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            xhr.open("POST", "/api/knowledge/my-documents/upload");
            const headers = getAuthHeaders();
            for (const [k, v] of Object.entries(headers)) xhr.setRequestHeader(k, v);
            const form = new FormData();
            form.append("file", file);
            form.append("folder_id", fid);
            xhr.onload = () => {
              if (xhr.status >= 200 && xhr.status < 300) {
                try { const d = JSON.parse(xhr.responseText); resolve(d.doc_id || ""); } catch { resolve(""); }
              } else { reject(new Error(`HTTP ${xhr.status}`)); }
            };
            xhr.onerror = () => reject(new Error("网络错误"));
            xhr.send(form);
          });
          if (doc_id) ok++; else fail++;
        } catch {
          fail++;
        }
      }
      setFolderUploadProgress(null);
      if (ok > 0) setMsg({ type: "success", text: `已上传 ${ok} 个文件到文件夹` + (fail > 0 ? `（${fail} 个失败）` : "") });
      else setMsg({ type: "error", text: `全部 ${fail} 个文件上传失败` });
      setFolderUploadBusy(false);
      await loadAll();
      if (activeFolderId) await loadFolderDetail(activeFolderId);
    },
    [activeFolderId, loadAll, loadFolderDetail],
  );

  const unlinkDocFromFolder = useCallback(
    async (docId: string, folderId: string) => {
      const fid = (folderId || "").trim();
      const did = (docId || "").trim();
      if (!fid || !did) return;
      setFolderDetail((prev) => (activeFolderId === fid ? optimisticRemoveDocFromFolderDetail(prev, did) : prev));
      const res = await fetch(`/api/knowledge/folders/${encodeURIComponent(fid)}/unlink-doc`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        credentials: "include",
        body: JSON.stringify({ doc_id: did }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof (data as any).detail === "string" ? (data as any).detail : "移除失败");
    },
    [activeFolderId],
  );

  const copyDocToFolder = async (docId: string, targetFolderId: string) => {
    if (!targetFolderId) return;
    setMsg(null);
    try {
      const res = await fetch(`/api/knowledge/folders/${encodeURIComponent(targetFolderId)}/link-doc`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        credentials: "include",
        body: JSON.stringify({ doc_id: docId }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "复制失败");
      setMsg({ type: "success", text: "已复制到目标文件夹（同一文档，多文件夹可见）。" });
      await loadAll();
      if (activeFolderId) await loadFolderDetail(activeFolderId);
    } catch (e) {
      setMsg({ type: "error", text: e instanceof Error ? e.message : "复制失败" });
    }
  };

  const folderBulkActiveRight =
    bulkSelection.doc_ids.length > 0 &&
    bulkContextFolderId !== undefined &&
    (bulkSelection.source_folder_id || null) === (bulkContextFolderId ?? null);

  return (
    <div className="p-2 md:p-3">
      <div className="mb-3">
        {/* 顶栏：范围 chips + 搜索图标（点击展开输入框） */}
        <div className="flex flex-wrap items-center gap-2">
          {DEFAULT_SCOPE_ORDER.map((kid) => {
            if (!allKbKindsOrdered.includes(kid)) return null;
            const active = scopeKinds.includes(kid);
            return (
              <button
                key={kid}
                type="button"
                onClick={() => toggleScopeKind(kid)}
                className={`rounded-full border px-3 py-1 text-sm ${
                  active
                    ? "border-[#2563eb]/50 bg-[#2563eb]/14 text-zinc-100"
                    : "border-zinc-800 bg-zinc-950 text-zinc-500 hover:border-zinc-700 hover:text-zinc-300"
                }`}
              >
                {kbKindLabelById.get(kid) || kid}
              </button>
            );
          })}
          {allKbKindsOrdered
            .filter((kid) => !DEFAULT_SCOPE_ORDER.includes(kid as any))
            .map((kid) => {
              const active = scopeKinds.includes(kid);
              return (
                <button
                  key={kid}
                  type="button"
                  onClick={() => toggleScopeKind(kid)}
                  className={`rounded-full border px-3 py-1 text-sm ${
                    active
                      ? "border-[#2563eb]/50 bg-[#2563eb]/14 text-zinc-100"
                      : "border-zinc-800 bg-zinc-950 text-zinc-500 hover:border-zinc-700 hover:text-zinc-300"
                  }`}
                >
                  {kbKindLabelById.get(kid) || kid}
                </button>
              );
            })}

          <div className="ml-auto flex items-center gap-2">
            {!searchOpen ? (
              <button
                type="button"
                onClick={() => setSearchOpen(true)}
                className="rounded-full border border-zinc-800 bg-zinc-950 px-3 py-1 text-sm text-zinc-400 hover:border-zinc-700 hover:text-zinc-200"
                title="搜索"
                aria-label="搜索"
              >
                <Search className="h-4 w-4" />
              </button>
            ) : (
              <div className="flex items-center gap-2">
                <div className="flex items-center gap-2 rounded-full border border-zinc-800 bg-zinc-950 px-3 py-1">
                  <Search className="h-4 w-4 text-zinc-500" />
                  <input
                    value={kbGlobalSearch}
                    onChange={(e) => setKbGlobalSearch(e.target.value)}
                    placeholder="搜索文档/文件夹/ID"
                    className="w-[240px] bg-transparent text-sm text-zinc-200 placeholder:text-zinc-600 outline-none"
                  />
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setKbGlobalSearch("");
                    setSearchOpen(false);
                  }}
                  className="rounded-full border border-zinc-800 bg-zinc-950 px-3 py-1 text-sm text-zinc-500 hover:border-zinc-700 hover:text-zinc-200"
                >
                  取消
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {msg && (
        <p
          className={`mb-4 text-sm ${
            msg.type === "success" ? "text-[#22c55e]" : msg.type === "info" ? "text-zinc-300" : "text-red-400"
          }`}
        >
          {msg.text}
        </p>
      )}

      <div className="grid gap-3 md:grid-cols-[minmax(260px,34%)_1fr]">
        <section className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
          <div className="mb-2 flex items-center justify-between gap-2">
            <div className="text-base font-medium text-zinc-200">目录</div>
            <span className="text-[10px] uppercase tracking-wide text-zinc-600">Tree</span>
          </div>
          <div className="h-[calc(100vh-320px)] overflow-y-auto pr-1">
            <KbBrowseTree
              kinds={kindsVisibleInTree}
              allFolders={folders}
              kbKindLabelById={kbKindLabelById}
              selection={selection}
              activeKbKind={activeKbKind}
              activeFolderId={activeFolderId}
              privateUnfiledCount={privateRootDocs.length}
              kbGlobalSearch={kbGlobalSearch}
              onSelectKb={(kid) => {
                setSelection({ kind: "kb", kb_kind: kid });
                if (kid === KB_KIND_PRIVATE) {
                  setFolderLoading(false);
                } else {
                  setFolderDetail(null);
                  setFolderLoading(false);
                }
              }}
              onSelectFolder={(kid, folderId) => {
                setSelection({ kind: "folder", kb_kind: kid, folder_id: folderId });
              }}
              loadFolderDetail={loadFolderDetail}
              userHasInteractedRef={userHasInteractedRef}
            />
          </div>
        </section>

        <section className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div className="min-w-0 text-base text-zinc-200">
              <span className="font-medium">当前知识库：</span>
              <span className="font-medium">{kbKindLabelById.get(activeKbKind) || activeKbKind}</span>
              {selection.kind === "folder" ? (
                <span className="ml-2 text-sm text-zinc-500">
                  文件夹：
                  {safeFolderDetail?.folder?.name || folderNameById.get(selection.folder_id) || selection.folder_id}
                </span>
              ) : null}
            </div>
            <div className="flex items-center gap-2">
              <div className="relative" data-kb-menu-root="1">
                <button
                  type="button"
                  onClick={(e) => {
                    const next = openMenu?.kind === "kb" && openMenu.id === activeKbKind ? null : { kind: "kb" as const, id: activeKbKind };
                    openAnchoredMenu(next, e.currentTarget);
                  }}
                  className="rounded px-2 py-1 text-base text-zinc-300 hover:bg-zinc-950/40 hover:text-zinc-100"
                  aria-label="知识库菜单"
                  title="知识库菜单"
                >
                  ⋯
                </button>
                {openMenu?.kind === "kb" && openMenu.id === activeKbKind ? (
                  <div
                    ref={menuPanelRef}
                    data-kb-menu-panel="1"
                    data-kb-menu-root="1"
                    className="fixed z-50 w-44 rounded-md border border-zinc-800 bg-zinc-950 p-1 shadow"
                    style={menuPos ? { top: menuPos.top, left: menuPos.left } : undefined}
                  >
                    <button
                      type="button"
                      className="w-full rounded px-2 py-2 text-left text-sm text-zinc-200 hover:bg-zinc-900"
                      onClick={() => {
                        openAnchoredMenu(null, null);
                        const name = (prompt("新建文件夹名称") || "").trim();
                        if (!name) return;
                        void (async () => {
                          setMsg(null);
                          try {
                            const res = await fetch("/api/knowledge/folders", {
                              method: "POST",
                              headers: { "Content-Type": "application/json", ...getAuthHeaders() },
                              credentials: "include",
                              body: JSON.stringify({ name }),
                            });
                            const resClone = res.clone();
                            const data = await res.json().catch(() => ({} as any));
                            if (!res.ok) {
                              const detail = typeof (data as any)?.detail === "string" ? (data as any).detail : "";
                              const txt = await resClone.text().catch(() => "");
                              throw new Error(formatHttpError({ status: res.status, detail, text: txt, fallback: "创建失败" }));
                            }
                            const folder_id = String((data as any).folder_id || "");
                            if (!folder_id) throw new Error("创建失败（缺少 folder_id）");
                            // 分享到当前 kb（失败不阻断）
                            if (activeKbKind !== "Private") {
                              try {
                                const dept = (me?.department || "").trim();
                                const projs = (me?.projects || []).map((p) => String(p.project_id || "").trim()).filter(Boolean);
                                const department_ids =
                                  activeKbKind.startsWith("Dept") || activeKbKind.startsWith("MultiDept") ? (dept ? [dept] : []) : [];
                                const project_ids =
                                  activeKbKind.startsWith("Project") || activeKbKind.startsWith("MultiProject")
                                    ? projs.length
                                      ? projs
                                      : []
                                    : [];
                                const company_public = activeKbKind === "CompanyPublic";
                                await fetch(`/api/knowledge/folders/${encodeURIComponent(folder_id)}/share`, {
                                  method: "POST",
                                  headers: { "Content-Type": "application/json", ...getAuthHeaders() },
                                  credentials: "include",
                                  body: JSON.stringify({ kb_kind: activeKbKind, department_ids, project_ids, company_public }),
                                }).catch(() => {});
                              } catch {
                                // ignore
                              }
                            }
                            setMsg({ type: "success", text: "已创建文件夹。" });
                            await loadAll();
                          } catch (e) {
                            setMsg({ type: "error", text: e instanceof Error ? e.message : "创建失败" });
                          }
                        })();
                      }}
                    >
                      创建文件夹
                    </button>
                  </div>
                ) : null}
              </div>
              {/* “上传到文件夹” 属于文件夹层面的动作，改为放到文件夹视图的三点菜单里 */}
            </div>
          </div>

          {folderBulkActiveRight ? (
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-md border border-zinc-800 bg-zinc-950/40 px-2 py-2 text-xs text-zinc-300">
              <span>已选 {bulkSelection.doc_ids.length} 条</span>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setDocTargetModal({
                      doc_id: bulkSelection.doc_ids[0] || "",
                      mode: "move",
                      source_folder_id: activeFolderId || undefined,
                    });
                    setDocTargetKbKind("");
                    setDocTargetFolderId("");
                  }}
                  className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1 hover:bg-zinc-800"
                >
                  批量移动到…
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setDocTargetModal({ doc_id: bulkSelection.doc_ids[0] || "", mode: "copy" });
                    setDocTargetKbKind("");
                    setDocTargetFolderId("");
                  }}
                  className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1 hover:bg-zinc-800"
                >
                  批量复制到…
                </button>
                {activeFolderId ? (
                  <button
                    type="button"
                    onClick={async () => {
                      if (!confirm(`从该文件夹移除已选 ${bulkSelection.doc_ids.length} 条文档？（不会删除文件）`)) return;
                      try {
                        for (const did of bulkSelection.doc_ids) await unlinkDocFromFolder(did, activeFolderId);
                        setMsg({ type: "success", text: "已从文件夹移除。" });
                        await loadAll();
                        if (activeFolderId) await loadFolderDetail(activeFolderId);
                        clearBulkSelection();
                      } catch (e) {
                        setMsg({ type: "error", text: e instanceof Error ? e.message : "移除失败" });
                      }
                    }}
                    className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1 hover:bg-zinc-800"
                  >
                    批量从文件夹移除
                  </button>
                ) : null}
                <button
                  type="button"
                  onClick={async () => {
                    const ids = [...bulkSelection.doc_ids];
                    if (!ids.length) return;
                    if (!confirm(`确定删除已选 ${ids.length} 条文档？`)) return;
                    setMsg(null);
                    let deleted = 0;
                    for (const did of ids) {
                      if (await deleteDoc(did, { skipConfirm: true, skipReload: true, quietSuccess: true })) deleted += 1;
                    }
                    await loadAll();
                    if (activeFolderId) await loadFolderDetail(activeFolderId);
                    if (deleted > 0) {
                      setMsg({
                        type: "success",
                        text: deleted === ids.length ? `已删除 ${deleted} 条。` : `已删除 ${deleted}/${ids.length} 条（部分失败见上方提示）。`,
                      });
                      clearBulkSelection();
                    }
                  }}
                  className="rounded border border-red-900/40 bg-red-950/30 px-2 py-1 text-red-300/90 hover:bg-red-950/50"
                >
                  批量删除
                </button>
                <button type="button" onClick={clearBulkSelection} className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1 hover:bg-zinc-800">
                  清空选择
                </button>
              </div>
            </div>
          ) : null}

          {folderDetail || activeFolderId ? (
            <div className="relative min-h-[8rem]">
              {folderLoading && activeFolderId ? (
                <div className="pointer-events-none absolute right-1 top-0 z-20 rounded border border-zinc-800/80 bg-zinc-950/95 px-2 py-0.5 text-xs text-zinc-400">
                  加载中…
                </div>
              ) : null}
              {activeFolderId && !safeFolderDetail ? (
                <div className="rounded-lg border border-zinc-800 bg-zinc-950/30 py-12 text-center text-sm text-zinc-500">正在加载文件夹…</div>
              ) : !safeFolderDetail ? null : (
            <div className="overflow-x-auto overflow-y-visible">
              <div className="mb-2 flex items-center justify-between gap-2">
                <div className="min-w-0 truncate text-base font-medium text-zinc-200">
                  {selection.kind === "folder"
                    ? folderViewHeading({
                        folderName:
                          safeFolderDetail.folder?.name ||
                          folderNameById.get(activeFolderId || "") ||
                          activeFolderId ||
                          "",
                        folderId: activeFolderId || "",
                      })
                    : isPrivateKbRootView
                      ? "未归档文档"
                      : "文档"}
                </div>
                {selection.kind === "folder" && activeFolderId && folderForActions ? (
                  <div className="relative" data-kb-menu-root="1">
                    <button
                      type="button"
                      onClick={(e) => {
                        const next =
                          openMenu?.kind === "folder" && openMenu.id === activeFolderId
                            ? null
                            : { kind: "folder" as const, id: activeFolderId };
                        openAnchoredMenu(next, e.currentTarget);
                      }}
                      className="rounded px-2 py-1 text-sm text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
                      aria-label="文件夹菜单"
                      title="文件夹菜单"
                    >
                      …
                    </button>
                    {openMenu?.kind === "folder" && openMenu.id === activeFolderId ? (
                      <div
                        ref={menuPanelRef}
                        data-kb-menu-panel="1"
                        data-kb-menu-root="1"
                        className="fixed z-50 min-w-[11rem] w-52 rounded-lg border border-zinc-800 bg-zinc-950/95 p-1 text-xs shadow-[0_20px_60px_rgba(0,0,0,0.5)]"
                        style={menuPos ? { top: menuPos.top, left: menuPos.left } : undefined}
                      >
                        <button
                          type="button"
                          onClick={() => {
                            openAnchoredMenu(null, null);
                            folderFileInputRef.current?.click();
                          }}
                          disabled={folderUploadBusy}
                          className="w-full rounded px-2 py-1.5 text-left text-zinc-200 hover:bg-zinc-900/60 disabled:opacity-40"
                        >
                          上传到文件夹
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            openAnchoredMenu(null, null);
                            const name = (prompt("新建子文件夹名称") || "").trim();
                            if (!name) return;
                            void (async () => {
                              try {
                                const res = await fetch("/api/knowledge/folders", {
                                  method: "POST",
                                  headers: { "Content-Type": "application/json", ...getAuthHeaders() },
                                  credentials: "include",
                                  body: JSON.stringify({ name, parent_folder_id: activeFolderId }),
                                });
                                const data = await res.json().catch(() => ({}));
                                if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "创建失败");
                                setMsg({ type: "success", text: "子文件夹已创建。" });
                                await loadAll();
                              } catch (e) {
                                setMsg({ type: "error", text: e instanceof Error ? e.message : "创建失败" });
                              }
                            })();
                          }}
                          className="w-full rounded px-2 py-1.5 text-left text-zinc-200 hover:bg-zinc-900/60"
                        >
                          创建子文件夹
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            openAnchoredMenu(null, null);
                            bringFolderToAi(activeFolderId);
                          }}
                          className="w-full rounded px-2 py-1.5 text-left text-zinc-200 hover:bg-zinc-900/60"
                        >
                          带到 AI 互动
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            openAnchoredMenu(null, null);
                            openShareFolder(folderForActions);
                          }}
                          className="w-full rounded px-2 py-1.5 text-left text-zinc-200 hover:bg-zinc-900/60"
                        >
                          共享到…
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            openAnchoredMenu(null, null);
                            openFolderMoveModal(folderForActions);
                          }}
                          className="w-full rounded px-2 py-1.5 text-left text-zinc-200 hover:bg-zinc-900/60"
                        >
                          移动到…
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            openAnchoredMenu(null, null);
                            void renameFolder(folderForActions);
                          }}
                          className="w-full rounded px-2 py-1.5 text-left text-zinc-200 hover:bg-zinc-900/60"
                        >
                          重命名
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            openAnchoredMenu(null, null);
                            void deleteFolder(folderForActions);
                          }}
                          disabled={isInternalPrivatePlaceholderFolder(folderForActions)}
                          className="w-full rounded px-2 py-1.5 text-left text-red-300 hover:bg-red-950/40 disabled:cursor-not-allowed disabled:opacity-40"
                        >
                          删除
                        </button>
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>
              {/* 上传进度条 */}
              {folderUploadProgress ? (
                <div className="mb-3 rounded border border-zinc-700 bg-zinc-950/40 px-3 py-2">
                  <div className="mb-1 flex items-center justify-between text-xs text-zinc-400">
                    <span>上传中…</span>
                    <span>{folderUploadProgress.current}/{folderUploadProgress.total}</span>
                  </div>
                  <div className="h-1.5 w-full rounded-full bg-zinc-800">
                    <div className="h-1.5 rounded-full bg-blue-500 transition-all duration-300" style={{ width: `${folderUploadProgress.pct}%` }} />
                  </div>
                </div>
              ) : null}
              {docsFilteredForTable.length ? (
                <table className="w-full min-w-[520px] border-collapse text-left text-sm">
                  <thead>
                    <tr className="border-b border-zinc-800 text-sm text-zinc-500">
                      <th className="w-10 py-2 pr-2">
                        {bulkContextFolderId !== undefined && folderDocIdsForBulk.length > 0 ? (
                          <input
                            ref={folderBulkHeaderRef}
                            type="checkbox"
                            checked={folderBulkHeaderState === "all"}
                            aria-label={isPrivateKbRootView ? "全选未归档文档" : "全选文件夹内文档"}
                            title="全选 / 取消全选"
                            onChange={toggleFolderBulkAll}
                          />
                        ) : (
                          " "
                        )}
                      </th>
                      <th className="py-2 pr-2">名称</th>
                      <th className="w-28 py-2 pr-2">状态</th>
                      <th className="w-36 py-2 pr-2">位置</th>
                      <th className="w-40 py-2 pr-2">更新时间</th>
                      <th className="w-12 py-2 text-right"> </th>
                    </tr>
                  </thead>
                  <tbody>
                    {docsFilteredForTable.map((d) => {
                      const menuKey =
                        activeFolderId ? `${d.doc_id}|${activeFolderId}` : `${d.doc_id}|loose`;
                      const loc =
                        safeFolderDetail?.folder?.name ||
                        (activeFolderId ? folderNameById.get(activeFolderId) : docPrimaryFolderNameById.get(d.doc_id) || "私人根级") ||
                        "—";
                      const checked =
                        activeFolderId
                          ? bulkSelection.source_folder_id === activeFolderId && bulkSelection.doc_ids.includes(d.doc_id)
                          : !bulkSelection.source_folder_id && bulkSelection.doc_ids.includes(d.doc_id);
                      return (
                        <tr key={d.doc_id} className="border-b border-zinc-900/60 hover:bg-zinc-950/40">
                          <td className="py-2 pr-2 align-middle">
                            <input
                              type="checkbox"
                              checked={checked}
                              onClick={(e) => e.stopPropagation()}
                              onChange={() =>
                                toggleBulkDoc(
                                  d.doc_id,
                                  activeFolderId || null,
                                )
                              }
                            />
                          </td>
                          <td className="max-w-[220px] py-2 pr-2 align-middle">
                            <div className="flex items-center gap-2">
                          <FileText className="h-4 w-4 text-zinc-500" />
                              <div className="truncate text-zinc-100">{d.original_filename || d.title}</div>
                            </div>
                            <div className="truncate font-mono text-[11px] text-zinc-600">{d.doc_id}</div>
                          </td>
                          <td className="py-2 pr-2 align-middle text-xs text-zinc-400">{statusLabel(d.status)}</td>
                          <td className="py-2 pr-2 align-middle text-xs text-zinc-400">{loc}</td>
                          <td className="py-2 pr-2 align-middle text-xs text-zinc-500">{formatLogTime(d.created_at)}</td>
                          <td className="py-2 text-right align-middle">
                            <button
                              type="button"
                              onClick={(e) => openAnchoredMenu({ kind: "doc", id: menuKey }, e.currentTarget)}
                              className="rounded px-2 py-1 text-sm text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
                            >
                              …
                            </button>
                            {openMenu?.kind === "doc" && openMenu.id === menuKey ? (
                              <div data-kb-menu-root="1" className="relative inline-block">
                                <div
                                  ref={menuPanelRef}
                                  data-kb-menu-panel="1"
                                  data-kb-menu-root="1"
                                  className="fixed z-50 w-44 rounded-lg border border-zinc-800 bg-zinc-950/95 p-1 text-xs shadow-[0_20px_60px_rgba(0,0,0,0.5)]"
                                  style={menuPos ? { top: menuPos.top, left: menuPos.left } : undefined}
                                >
                                  <button
                                    type="button"
                                    onClick={() => {
                                      bringDocsToAi([d.doc_id]);
                                    }}
                                    className="w-full rounded px-2 py-1.5 text-left text-zinc-200 hover:bg-zinc-900/60"
                                  >
                                    带到 AI 互动
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => {
                                      setDocTargetModal({
                                        doc_id: d.doc_id,
                                        mode: "move",
                                        source_folder_id: activeFolderId || undefined,
                                      });
                                      setDocTargetKbKind("");
                                      setDocTargetFolderId("");
                                      openAnchoredMenu(null, null);
                                    }}
                                    className="w-full rounded px-2 py-1.5 text-left text-zinc-200 hover:bg-zinc-900/60"
                                  >
                                    移动到…
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => {
                                      setDocTargetModal({ doc_id: d.doc_id, mode: "copy" });
                                      setDocTargetKbKind("");
                                      setDocTargetFolderId("");
                                      openAnchoredMenu(null, null);
                                    }}
                                    className="w-full rounded px-2 py-1.5 text-left text-zinc-200 hover:bg-zinc-900/60"
                                  >
                                    复制到…
                                  </button>
                                  {activeFolderId ? (
                                    <button
                                      type="button"
                                      onClick={() => {
                                        openAnchoredMenu(null, null);
                                        void (async () => {
                                          if (!confirm("从该文件夹移除该文档？（不会删除文件）")) return;
                                          try {
                                            await unlinkDocFromFolder(d.doc_id, activeFolderId);
                                            setMsg({ type: "success", text: "已从文件夹移除。" });
                                            await loadAll();
                                            if (activeFolderId) await loadFolderDetail(activeFolderId);
                                          } catch (e) {
                                            setMsg({ type: "error", text: e instanceof Error ? e.message : "移除失败" });
                                          }
                                        })();
                                      }}
                                      className="w-full rounded px-2 py-1.5 text-left text-zinc-200 hover:bg-zinc-900/60"
                                    >
                                      从文件夹移除
                                    </button>
                                  ) : null}
                                  <button
                                    type="button"
                                    onClick={() => {
                                      openAnchoredMenu(null, null);
                                      handleDelete(d.doc_id);
                                    }}
                                    className="w-full rounded px-2 py-1.5 text-left text-red-300 hover:bg-red-950/40"
                                  >
                                    删除
                                  </button>
                                </div>
                              </div>
                            ) : null}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              ) : (
                <div className="rounded-lg border border-zinc-800 bg-zinc-950/30 p-4 text-base text-zinc-400">暂无文档。</div>
              )}

            </div>
              )}
            </div>
          ) : null}
        </section>
      </div>

      {/* v3：大 PDF 文档包不再弹层；由右侧栏整体切换展示（见右侧栏渲染） */}

      <details id="kb-upload-log" open className="mt-8 rounded-lg border border-zinc-800/50 bg-zinc-950/20 text-zinc-500">
        <summary className="cursor-pointer select-none px-3 py-2 text-sm hover:bg-zinc-900/40">
          上传与解析日志（大 PDF 任务、文档解析时间线）
        </summary>
        <div className="border-t border-zinc-800/40 px-3 py-2">
          <div className="mb-2">
            <KbInProgressBanner />
          </div>
          {uploadLogLines.length ? (
            <pre className="max-h-40 overflow-auto whitespace-pre-wrap font-mono text-[11px] leading-relaxed text-zinc-500">
              {uploadLogLines.join("\n")}
            </pre>
          ) : (
            <p className="text-[11px] text-zinc-600">暂无文档解析记录</p>
          )}
        </div>
      </details>

      <MoveCopyModal
        open={Boolean(docTargetModal)}
        mode={docTargetModal?.mode || "copy"}
        docId={docTargetModal?.doc_id || ""}
        count={
          docTargetModal && bulkSelection.doc_ids.length > 0 && bulkSelection.doc_ids.includes(docTargetModal.doc_id)
            ? bulkSelection.doc_ids.length
            : docTargetModal
              ? 1
              : 0
        }
        foldersByKind={foldersByKind}
        kbKindLabelById={kbKindLabelById}
        kbKind={docTargetKbKind}
        folderId={docTargetFolderId}
        onChangeKbKind={(v) => {
          setDocTargetKbKind(v);
          setDocTargetFolderId("");
        }}
        onChangeFolderId={setDocTargetFolderId}
        onClose={() => setDocTargetModal(null)}
        onConfirm={async (target) => {
          const m = docTargetModal;
          if (!m) return;
          try {
            const isBatch = bulkSelection.doc_ids.length > 0 && bulkSelection.doc_ids.includes(m.doc_id);
            const targets = isBatch ? bulkSelection.doc_ids : [m.doc_id];
            for (const did of targets) {
              if (m.mode === "move") {
                const src =
                  (m.source_folder_id || "").trim() ||
                  (bulkSelection.source_folder_id || "").trim() ||
                  myDocs.find((x) => x.doc_id === did)?.folder_ids?.[0] ||
                  "";
                if (src) await moveDocBetweenFolders(did, src, target);
                else await copyDocToFolder(did, target);
              } else {
                await copyDocToFolder(did, target);
              }
            }
            setDocTargetModal(null);
            clearBulkSelection();
          } catch {
            // copyDocToFolder 内会 setMsg
          }
        }}
      />

      {folderMoveOpen && folderMoveFolder ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-lg border border-zinc-700 bg-zinc-900 p-5 shadow-xl">
            <h3 className="text-lg font-medium text-zinc-100">将文件夹移动到知识库范围</h3>
            <p className="mt-1 text-sm text-zinc-500">{folderMoveFolder.name}</p>
            <p className="mt-2 text-xs text-zinc-500">
              将从当前共享范围撤回，并仅在所选目标范围出现（与「共享到」叠加不同）。
            </p>
            <div className="mt-4 space-y-3">
              <div>
                <div className="mb-1 block text-xs text-zinc-400">目标范围</div>
                <div className="flex flex-wrap gap-3 text-sm text-zinc-200">
                  <label className="flex items-center gap-2">
                    <input
                      type="radio"
                      name="folderMoveTarget"
                      checked={folderMoveTarget === "private"}
                      onChange={() => setFolderMoveTarget("private")}
                    />
                    私人
                  </label>
                  <label className="flex items-center gap-2">
                    <input
                      type="radio"
                      name="folderMoveTarget"
                      checked={folderMoveTarget === "company"}
                      onChange={() => setFolderMoveTarget("company")}
                    />
                    公司
                  </label>
                  <label className="flex items-center gap-2">
                    <input
                      type="radio"
                      name="folderMoveTarget"
                      checked={folderMoveTarget === "department"}
                      onChange={() => setFolderMoveTarget("department")}
                    />
                    部门
                  </label>
                  <label className="flex items-center gap-2">
                    <input
                      type="radio"
                      name="folderMoveTarget"
                      checked={folderMoveTarget === "project"}
                      onChange={() => setFolderMoveTarget("project")}
                    />
                    项目
                  </label>
                </div>
              </div>
              {folderMoveTarget === "department" ? (
                <div>
                  <div className="mb-1 text-xs text-zinc-400">目标库类型</div>
                  <div className="mb-2 flex flex-wrap gap-3 text-sm text-zinc-200">
                    <label className="flex items-center gap-2">
                      <input
                        type="radio"
                        name="folderMoveAccessKindDept"
                        checked={folderMoveAccessKind === "public"}
                        onChange={() => setFolderMoveAccessKind("public")}
                      />
                      公共库
                    </label>
                    <label className="flex items-center gap-2">
                      <input
                        type="radio"
                        name="folderMoveAccessKindDept"
                        checked={folderMoveAccessKind === "lead"}
                        onChange={() => setFolderMoveAccessKind("lead")}
                      />
                      负责人库
                    </label>
                  </div>
                  <div className="mb-1 text-xs text-zinc-400">部门（可多选）</div>
                  <div className="flex flex-wrap gap-2">
                    {departmentChoices.map((d) => (
                      <label key={d} className="flex cursor-pointer items-center gap-1.5 text-xs text-zinc-300">
                        <input type="checkbox" checked={folderMoveDepts.includes(d)} onChange={() => toggleFolderMoveDept(d)} />
                        {d}
                      </label>
                    ))}
                  </div>
                </div>
              ) : null}
              {folderMoveTarget === "project" ? (
                <div>
                  <div className="mb-1 text-xs text-zinc-400">目标库类型</div>
                  <div className="mb-2 flex flex-wrap gap-3 text-sm text-zinc-200">
                    <label className="flex items-center gap-2">
                      <input
                        type="radio"
                        name="folderMoveAccessKindProj"
                        checked={folderMoveAccessKind === "public"}
                        onChange={() => setFolderMoveAccessKind("public")}
                      />
                      公共库
                    </label>
                    <label className="flex items-center gap-2">
                      <input
                        type="radio"
                        name="folderMoveAccessKindProj"
                        checked={folderMoveAccessKind === "lead"}
                        onChange={() => setFolderMoveAccessKind("lead")}
                      />
                      负责人库
                    </label>
                  </div>
                  <div className="mb-1 text-xs text-zinc-400">项目（可多选）</div>
                  <div className="flex flex-wrap gap-2">
                    {projectChoices.map((p) => (
                      <label key={p.project_id} className="flex cursor-pointer items-center gap-1.5 text-xs text-zinc-300">
                        <input
                          type="checkbox"
                          checked={folderMoveProjs.includes(p.project_id)}
                          onChange={() => toggleFolderMoveProj(p.project_id)}
                        />
                        {p.name}
                      </label>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
            <div className="mt-6 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setFolderMoveOpen(false);
                  setFolderMoveFolder(null);
                }}
                className="rounded border border-zinc-600 px-3 py-1.5 text-sm text-zinc-300"
              >
                取消
              </button>
              <button
                type="button"
                disabled={
                  folderMoveTarget === "department"
                    ? folderMoveDepts.length === 0
                    : folderMoveTarget === "project"
                      ? folderMoveProjs.length === 0
                      : false
                }
                onClick={() => void confirmFolderMoveToKb()}
                className="rounded bg-zinc-600 px-3 py-1.5 text-sm text-white disabled:opacity-50"
              >
                确认移动
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {(shareDoc || shareFolder) && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-lg border border-zinc-700 bg-zinc-900 p-5 shadow-xl">
            <h3 className="text-lg font-medium text-zinc-100">{shareFolder ? "分享/权限（文件夹）" : "共享文档"}</h3>
            <p className="mt-1 text-sm text-zinc-500">{shareFolder ? shareFolder.name : shareDoc?.title}</p>
            <div className="mt-4 space-y-3">
              {shareFolder ? (
                <div className="space-y-3">
                  <div className="rounded border border-zinc-800 bg-zinc-950/40 p-3 text-xs text-zinc-300">
                    <div className="text-zinc-200 font-medium">权限模型（两层）</div>
                    <div className="mt-1 text-zinc-400">
                      可见范围由“共享到（公司/部门/项目）”决定；角色为 <span className="font-mono">viewer / editor / admin</span>（本期先展示，后端未启用时不做保存）。
                    </div>
                  </div>
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
                      <div className="mb-1 text-xs text-zinc-400">目标库类型</div>
                      <div className="mb-2 flex flex-wrap gap-3 text-sm text-zinc-200">
                        <label className="flex items-center gap-2">
                          <input
                            type="radio"
                            name="folderShareAccessKindDept"
                            checked={folderShareAccessKind === "public"}
                            onChange={() => setFolderShareAccessKind("public")}
                          />
                          公共库
                        </label>
                        <label className="flex items-center gap-2">
                          <input
                            type="radio"
                            name="folderShareAccessKindDept"
                            checked={folderShareAccessKind === "lead"}
                            onChange={() => setFolderShareAccessKind("lead")}
                          />
                          负责人库
                        </label>
                      </div>
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
                      <div className="mb-1 text-xs text-zinc-400">目标库类型</div>
                      <div className="mb-2 flex flex-wrap gap-3 text-sm text-zinc-200">
                        <label className="flex items-center gap-2">
                          <input
                            type="radio"
                            name="folderShareAccessKindProj"
                            checked={folderShareAccessKind === "public"}
                            onChange={() => setFolderShareAccessKind("public")}
                          />
                          公共库
                        </label>
                        <label className="flex items-center gap-2">
                          <input
                            type="radio"
                            name="folderShareAccessKindProj"
                            checked={folderShareAccessKind === "lead"}
                            onChange={() => setFolderShareAccessKind("lead")}
                          />
                          负责人库
                        </label>
                      </div>
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

                  <div className="rounded border border-zinc-800 bg-zinc-950/40 p-3">
                    <div className="flex items-center justify-between gap-3">
                      <div className="text-xs text-zinc-300">
                        <div className="text-zinc-200 font-medium">回收共享</div>
                        <div className="mt-1 text-zinc-500">“一键全撤”会撤回该文件夹对公司/部门/项目的可见性，使其回到仅自己可见（私人）。</div>
                      </div>
                      <button
                        type="button"
                        onClick={() => {
                          if (!shareFolder) return;
                          void revokeFolderShareAll(shareFolder);
                        }}
                        className="rounded border border-red-900/50 bg-red-950/30 px-2 py-1 text-xs text-red-200 hover:bg-red-950/40"
                      >
                        一键全撤
                      </button>
                    </div>
                  </div>
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
      <input ref={folderFileInputRef} type="file" className="hidden" multiple onChange={handleFolderFileUpload} />
    </div>
  );
}
