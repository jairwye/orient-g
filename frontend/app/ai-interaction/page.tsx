"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { getAuthHeaders } from "../lib/auth";
import { KbInProgressBanner } from "../components/KbInProgressBanner";
import {
  buildKnowledgeHref,
  emptyKbScopeCapsule,
  parseKbScopeFromSearchParams,
  readKbScopeCapsule,
  writeKbScopeCapsule,
} from "../lib/kb_scope_capsule";
import { ChevronLeft, ChevronRight, Folder, Plus, Sparkles, Upload, Wrench } from "lucide-react";

type KnowledgeCollection = {
  collection_id: string;
  space_type: string;
  name: string;
  type: "private" | "department" | "public" | "project";
  department_id?: string;
  project_id?: string;
  owner_user_id?: string;
};

type KnowledgeTable = {
  table_id: string;
  collection_id: string;
  space_type: string;
  name: string;
  row_count: number;
};

type KnowledgeFolder = {
  folder_id: string;
  name: string;
  collection_ids: string[];
};

type Citation = Record<string, unknown>;

type KnowledgeOptionsResponse = {
  collections: KnowledgeCollection[];
  tables: KnowledgeTable[];
  folders: KnowledgeFolder[];
  default_selected_collection_ids: string[];
  default_selected_table_ids: string[];
  default_selected_folder_ids: string[];
};

type AskResponse = {
  denied?: boolean;
  deny_reason?: string;
  // 当后端以 HTTPException 返回 403 时，Next/TS 侧可能拿到 `detail` 字段
  detail?: string;
  reply?: string;
  citations?: Citation[];
  llm_model?: string;
};

const BIG_PDF_SIZE_MB = 15;
const BIG_PDF_PAGES = 60;

type ChatMessage = { role: "user" | "assistant"; content: string; citations?: Citation[]; deny_reason?: string };

type ChatSession = {
  id: string;
  title: string;
  updated_at: number;
  messages: ChatMessage[];
};

const SESSIONS_LS_KEY = "orientg.ai_interaction.sessions.v1";

function formatMb(bytes: number) {
  return Math.round((bytes / 1024 / 1024) * 10) / 10;
}

async function estimatePdfPages(file: File): Promise<number | null> {
  // 轻量估算：统计 PDF 内容中 `/Type /Page` 出现次数（排除 `/Type /Pages`）。
  // 只用于“大小+页数阈值分流”，不用于精确展示。
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

export default function AiInteractionPage() {
  const sp = useSearchParams();
  const scopeHydratedRef = useRef(false);
  const [loading, setLoading] = useState(true);
  const [options, setOptions] = useState<KnowledgeOptionsResponse | null>(null);
  const [selectedCollectionIds, setSelectedCollectionIds] = useState<string[]>([]);
  const [selectedTableIds, setSelectedTableIds] = useState<string[]>([]);
  const [selectedFolderIds, setSelectedFolderIds] = useState<string[]>([]);

  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [uploadHint, setUploadHint] = useState<string | null>(null);
  const [uploadBusy, setUploadBusy] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const composingRef = useRef(false);

  const [plusOpen, setPlusOpen] = useState(false);
  const [plusTab, setPlusTab] = useState<"" | "kb" | "kb_advanced">("");
  const plusBtnRef = useRef<HTMLButtonElement>(null);

  const [toolsOpen, setToolsOpen] = useState(false);
  const [skillsOpen, setSkillsOpen] = useState(false);
  const toolsBtnRef = useRef<HTMLButtonElement>(null);
  const skillsBtnRef = useRef<HTMLButtonElement>(null);

  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);

  // Persist sessions to localStorage as a side-effect of state changes.
  // Keeping persistence out of the state-update path avoids update loops.
  useEffect(() => {
    try {
      localStorage.setItem(SESSIONS_LS_KEY, JSON.stringify(sessions));
    } catch {
      // ignore
    }
  }, [sessions]);

  const ensureActiveSession = useCallback(() => {
    if (activeSessionId) return activeSessionId;
    const id = `s_${Date.now()}_${Math.random().toString(16).slice(2)}`;
    const s: ChatSession = { id, title: "新对话", updated_at: Date.now(), messages: [] };
    setActiveSessionId(id);
    setSessions((prev) => [s, ...prev]);
    return id;
  }, [activeSessionId]);

  const refreshKnowledgeOptions = useCallback(async () => {
    const res = await fetch("/api/knowledge/options", { credentials: "include", headers: getAuthHeaders() });
    if (!res.ok) return;
    const data = (await res.json()) as KnowledgeOptionsResponse;
    setOptions(data);
    // 方案 B：不在此页自动合并 default_selected_*，避免未操作即开启 RAG。
  }, []);

  // 首次加载完成后：合并「范围胶囊」localStorage + URL 参数 → 显式范围
  useEffect(() => {
    if (loading || scopeHydratedRef.current) return;
    const fromUrl = parseKbScopeFromSearchParams(new URLSearchParams(sp.toString()));
    const fromLs = readKbScopeCapsule() || emptyKbScopeCapsule();
    const merged = {
      folder_ids: fromUrl.folder_ids ?? fromLs.folder_ids,
      collection_ids: fromUrl.collection_ids ?? fromLs.collection_ids,
      table_ids: fromUrl.table_ids ?? fromLs.table_ids,
    };
    if (merged.folder_ids.length) setSelectedFolderIds(merged.folder_ids);
    if (merged.collection_ids.length) setSelectedCollectionIds(merged.collection_ids);
    if (merged.table_ids.length) setSelectedTableIds(merged.table_ids);
    writeKbScopeCapsule(merged);
    const hadUrlScope = Boolean(
      (fromUrl.folder_ids && fromUrl.folder_ids.length) ||
        (fromUrl.collection_ids && fromUrl.collection_ids.length) ||
        (fromUrl.table_ids && fromUrl.table_ids.length)
    );
    if (hadUrlScope && typeof window !== "undefined") {
      window.history.replaceState({}, "", "/ai-interaction");
    }
    scopeHydratedRef.current = true;
  }, [loading, sp]);

  // 用户调整范围后写回胶囊（hydrate 之后）
  useEffect(() => {
    if (!scopeHydratedRef.current || loading) return;
    writeKbScopeCapsule({
      folder_ids: selectedFolderIds,
      collection_ids: selectedCollectionIds,
      table_ids: selectedTableIds,
    });
  }, [selectedFolderIds, selectedCollectionIds, selectedTableIds, loading]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        // sessions（本地对话历史）
        try {
          const raw = localStorage.getItem(SESSIONS_LS_KEY);
          if (raw) {
            const parsed = JSON.parse(raw) as ChatSession[];
            if (Array.isArray(parsed)) {
              const cleaned = parsed
                .filter(
                  (x) =>
                    x &&
                    typeof (x as { id?: unknown }).id === "string" &&
                    Array.isArray((x as { messages?: unknown }).messages)
                )
                .map((x) => {
                  const obj = x as { id: string; title?: unknown; updated_at?: unknown; messages?: unknown };
                  const rawMessages = (obj.messages as unknown[] | undefined) || [];
                  const messages = rawMessages
                    .filter((m): m is ChatMessage => {
                      if (!m || typeof m !== "object") return false;
                      const mm = m as { role?: unknown; content?: unknown; citations?: unknown; deny_reason?: unknown };
                      return (mm.role === "user" || mm.role === "assistant") && typeof mm.content === "string";
                    })
                    .map((m) => ({ role: m.role, content: m.content, citations: m.citations, deny_reason: m.deny_reason }));
                  return {
                    id: obj.id,
                    title: typeof obj.title === "string" && obj.title.trim() ? obj.title : "对话",
                    updated_at: typeof obj.updated_at === "number" ? obj.updated_at : Date.now(),
                    messages,
                  } satisfies ChatSession;
                })
                .sort((a, b) => (b.updated_at || 0) - (a.updated_at || 0));
              setSessions(cleaned);
              if (cleaned.length) {
                setActiveSessionId(cleaned[0].id);
                setMessages(cleaned[0].messages);
              }
            }
          }
        } catch {
          // ignore
        }
        await refreshKnowledgeOptions();
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [refreshKnowledgeOptions]);

  const groupedCollections = useMemo(() => {
    const map = new Map<string, KnowledgeCollection[]>();
    for (const c of options?.collections ?? []) {
      const k = c.space_type || "Unknown";
      map.set(k, [...(map.get(k) ?? []), c]);
    }
    return Array.from(map.entries()).sort((a, b) => a[0].localeCompare(b[0]));
  }, [options]);

  const groupedTables = useMemo(() => {
    const map = new Map<string, KnowledgeTable[]>();
    for (const t of options?.tables ?? []) {
      const k = t.space_type || "Unknown";
      map.set(k, [...(map.get(k) ?? []), t]);
    }
    return Array.from(map.entries()).sort((a, b) => a[0].localeCompare(b[0]));
  }, [options]);

  const folders = useMemo(() => {
    return (options?.folders ?? []).slice().sort((a, b) => (a.name || "").localeCompare(b.name || ""));
  }, [options]);

  const kbScopeSummary = useMemo(() => {
    const parts: string[] = [];
    if (selectedFolderIds.length) {
      const names = selectedFolderIds.map((id) => folders.find((f) => f.folder_id === id)?.name || id);
      parts.push(`文件夹：${names.join("、")}`);
    }
    if (selectedCollectionIds.length) parts.push(`集合：${selectedCollectionIds.length} 个`);
    if (selectedTableIds.length) parts.push(`表：${selectedTableIds.length} 个`);
    return parts.join(" · ") || "未选择（当前为纯对话，不发 RAG）";
  }, [selectedFolderIds, selectedCollectionIds, selectedTableIds, folders]);

  const hasExplicitKbScope = selectedFolderIds.length > 0 || selectedCollectionIds.length > 0 || selectedTableIds.length > 0;

  const clearKbScope = () => {
    setSelectedFolderIds([]);
    setSelectedCollectionIds([]);
    setSelectedTableIds([]);
    writeKbScopeCapsule(emptyKbScopeCapsule());
  };

  const toggleFolder = (id: string) => {
    setSelectedFolderIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const toggleCollection = (id: string) => {
    setSelectedCollectionIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const toggleTable = (id: string) => {
    setSelectedTableIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const handleAsk = async () => {
    const q = chatInput.trim();
    if (!q || chatLoading) return;
    setChatLoading(true);
    setChatInput("");
    ensureActiveSession();
    setMessages((prev) => [...prev, { role: "user", content: q }]);
    try {
      const nextMessages = [...messages, { role: "user" as const, content: q }];
      const res = await fetch("/api/ai-interaction/chat", {
        method: "POST",
        headers: { ...getAuthHeaders(), "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          messages: nextMessages,
          kb_scope: {
            selected_collection_ids: selectedCollectionIds.length ? selectedCollectionIds : undefined,
            selected_table_ids: selectedTableIds.length ? selectedTableIds : undefined,
            selected_folder_ids: selectedFolderIds.length ? selectedFolderIds : undefined,
          },
          // v1.2.2：后端会做 allow-list 强制；具体执行逻辑后续落地
          enabled_skills: enabledSkills.length ? enabledSkills : undefined,
          enabled_tools: enabledTools.length ? enabledTools : undefined,
          model: modelId,
        }),
      });
      const data = (await res.json().catch(() => ({}))) as AskResponse;
      if (!res.ok) {
        const deny = data?.deny_reason || data?.detail || "权限拒绝";
        setMessages((prev) => [...prev, { role: "assistant", content: deny, deny_reason: deny, citations: [] }]);
        return;
      }
      const reply = data.reply ?? "";
      const citations = (data.citations ?? []) as Citation[];
      setMessages((prev) => [...prev, { role: "assistant", content: reply, citations }]);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "请求失败";
      setMessages((prev) => [...prev, { role: "assistant", content: msg, citations: [] }]);
    } finally {
      setChatLoading(false);
    }
  };

  // v1.2.2：skills/tools allow-list（UI 先落地；后端执行后续补齐）
  const ALL_SKILLS = [
    { id: "skill.project_accounting_table.v1", label: "基础数据生成项目核算表" },
  ];
  const ALL_TOOLS = [
    { id: "tool.docling.convert", label: "Docling（文档解析/转换）" },
    { id: "tool.mcp.*", label: "MCP 工具（按配置）" },
  ];
  const [enabledSkills, setEnabledSkills] = useState<string[]>([]);
  const [enabledTools, setEnabledTools] = useState<string[]>(["tool.docling.convert"]);
  const [modelId, setModelId] = useState<string>("qwen3:8b-q4_K_M");
  const [models, setModels] = useState<Array<{ id: string; label: string }>>([{ id: "qwen3:8b-q4_K_M", label: "qwen3:8b-q4_K_M" }]);
  const toggleEnabledSkill = (id: string) =>
    setEnabledSkills((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  const toggleEnabledTool = (id: string) =>
    setEnabledTools((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));

  useEffect(() => {
    fetch("/api/ai-interaction/models", { credentials: "include", headers: getAuthHeaders() })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.statusText))))
      .then((d: { items?: Array<{ id: string; label?: string }>; default?: string }) => {
        const items = Array.isArray(d.items) ? d.items.filter((x) => x?.id) : [];
        const mapped = items.map((x) => ({ id: x.id, label: x.label || x.id }));
        if (mapped.length) setModels(mapped);
        if (d.default) setModelId(d.default);
      })
      .catch(() => {});
  }, []);

  // 点击空白处关闭工具/skill 菜单
  useEffect(() => {
    if (!toolsOpen && !skillsOpen && !plusOpen) return;
    const onDown = (ev: MouseEvent) => {
      const t = ev.target as HTMLElement | null;
      const toolsBtn = toolsBtnRef.current;
      const skillsBtn = skillsBtnRef.current;
      const plusBtn = plusBtnRef.current;
      if (toolsBtn && t && (toolsBtn === t || toolsBtn.contains(t))) return;
      if (skillsBtn && t && (skillsBtn === t || skillsBtn.contains(t))) return;
      if (plusBtn && t && (plusBtn === t || plusBtn.contains(t))) return;
      const toolsPop = document.getElementById("ai-tools-popover");
      const skillsPop = document.getElementById("ai-skills-popover");
      const plusPop = document.getElementById("ai-plus-popover");
      if (toolsPop && t && toolsPop.contains(t)) return;
      if (skillsPop && t && skillsPop.contains(t)) return;
      if (plusPop && t && plusPop.contains(t)) return;
      setToolsOpen(false);
      setSkillsOpen(false);
      setPlusOpen(false);
    };
    window.addEventListener("mousedown", onDown, true);
    return () => window.removeEventListener("mousedown", onDown, true);
  }, [toolsOpen, skillsOpen, plusOpen]);

  // messages -> sessions（本地历史持久化）
  useEffect(() => {
    if (!activeSessionId) return;
    setSessions((prev) => {
      const idx = prev.findIndex((s) => s.id === activeSessionId);
      if (idx < 0) return prev;
      const current = prev[idx];
      const title =
        current.title && current.title !== "新对话"
          ? current.title
          : (() => {
              const firstUser = messages.find((m) => m.role === "user")?.content?.trim();
              return firstUser ? firstUser.slice(0, 20) : "新对话";
            })();
      const next: ChatSession = { ...current, title, updated_at: Date.now(), messages };
      const merged = [next, ...prev.filter((s) => s.id !== activeSessionId)].sort((a, b) => b.updated_at - a.updated_at);
      return merged;
    });
  }, [messages, activeSessionId]);

  const startNewChat = () => {
    const id = `s_${Date.now()}_${Math.random().toString(16).slice(2)}`;
    const s: ChatSession = { id, title: "新对话", updated_at: Date.now(), messages: [] };
    setActiveSessionId(id);
    setMessages([]);
    setSessions((prev) => [s, ...prev]);
  };

  const openSession = (id: string) => {
    const s = sessions.find((x) => x.id === id);
    if (!s) return;
    setActiveSessionId(id);
    setMessages(s.messages || []);
  };

  const formatSessionTime = (ts: number) => {
    try {
      const d = new Date(ts);
      return `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(
        d.getMinutes()
      ).padStart(2, "0")}`;
    } catch {
      return "";
    }
  };

  const handleUploadFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setUploadBusy(true);
    setUploadHint(null);
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
        // 大 PDF：直接创建后台任务，然后跳转到工具页看进度（避免二次选择文件）。
        setUploadHint("检测为大 PDF：正在创建处理任务并跳转到「大 PDF 生知识库」查看进度（暂不支持在 AI 互动页直接问答）。");
        const fd = new FormData();
        fd.append("file", file);
        const res = await fetch("/api/knowledge/bigpdf/tasks", {
          method: "POST",
          credentials: "include",
          headers: getAuthHeaders(),
          body: fd,
        });
        const data = (await res.json().catch(() => ({}))) as { detail?: string; task_id?: string };
        if (!res.ok) {
          setUploadHint(typeof data.detail === "string" ? data.detail : "创建大文档任务失败");
          return;
        }
        const taskId = typeof data.task_id === "string" ? data.task_id : "";
        if (!taskId) {
          setUploadHint("创建任务失败（缺少 task_id）");
          return;
        }
        const q = new URLSearchParams();
        q.set("task_id", taskId);
        q.set("from", "ai-interaction");
        q.set("name", file.name);
        q.set("size_mb", String(sizeMb));
        if (pages !== null) q.set("pages", String(pages));
        if (reasons.length) q.set("reason", reasons.join("；"));
        const bindFolder = selectedFolderIds[0];
        if (bindFolder) q.set("folder_id", bindFolder);
        window.location.href = `/utils/pdf-knowledge?${q.toString()}`;
        return;
      }

      const fd = new FormData();
      fd.append("file", file);
      const bindFolder = selectedFolderIds[0];
      if (bindFolder) fd.append("folder_id", bindFolder);
      const res = await fetch("/api/knowledge/my-documents/upload", {
        method: "POST",
        credentials: "include",
        headers: getAuthHeaders(),
        body: fd,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setUploadHint(typeof data.detail === "string" ? data.detail : "上传失败");
        return;
      }
      setUploadHint(
        bindFolder
          ? `已上传「${file.name}」到当前所选文件夹，正在后台排队解析；也可在知识库页查看状态。`
          : `已上传「${file.name}」，正在后台排队解析；请在知识库页选择文件夹或绑定默认私人库后管理。`
      );
      await refreshKnowledgeOptions();
    } catch (err) {
      setUploadHint(err instanceof Error ? err.message : "上传失败");
    } finally {
      setUploadBusy(false);
    }
  };

  const renderComposer = (variant: "center" | "bottom") => {
    const boxClass =
      variant === "center"
        ? "w-full max-w-4xl rounded-2xl border border-zinc-800 bg-zinc-950/60 shadow-[0_10px_40px_rgba(0,0,0,0.35)]"
        : "w-full max-w-4xl rounded-2xl border border-zinc-800 bg-zinc-950/60";
    return (
      <div className={boxClass}>
        <div className="p-3 relative">
          <div className="flex items-end gap-2">
            <input
              type="text"
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onCompositionStart={() => {
                composingRef.current = true;
              }}
              onCompositionEnd={() => {
                composingRef.current = false;
              }}
              onKeyDown={(e) => {
                // 兼容中文输入法：回车用于“上屏/确认候选”时不应发送
                const ne = e.nativeEvent as unknown as { isComposing?: boolean } | undefined;
                const isComposing = composingRef.current || Boolean(ne?.isComposing);
                if (isComposing) return;
                if (e.key === "Enter" && !e.shiftKey) handleAsk();
              }}
              placeholder="输入问题…（Enter 发送）"
              className="flex-1 rounded-xl border border-zinc-700 bg-zinc-900 px-5 py-4 text-base text-zinc-200 placeholder:text-zinc-500"
            />
            <button
              type="button"
              onClick={handleAsk}
              disabled={chatLoading || !chatInput.trim()}
              className="rounded-xl bg-zinc-200 px-5 py-4 text-sm font-medium text-zinc-900 hover:bg-white disabled:opacity-50"
            >
              {chatLoading ? "发送中…" : "发送"}
            </button>
          </div>

          {/* 输入框下方：小图标按钮（工具 / 技能 / 上传） */}
          <div className="mt-2 flex items-center justify-between">
            <div className="flex items-center gap-2 text-xs text-zinc-400">
              {/* + 菜单：上传 + 知识库（按文件夹） */}
              <div className="relative">
                <button
                  ref={plusBtnRef}
                  type="button"
                  onClick={() => {
                    setPlusOpen((v) => !v);
                    setPlusTab("");
                  }}
                  className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-zinc-800 bg-zinc-950/40 text-zinc-200 hover:bg-zinc-900/60"
                  title="更多"
                >
                  <Plus size={16} />
                </button>
                {plusOpen && (
                  <div
                    id="ai-plus-popover"
                    className="absolute left-0 top-[calc(100%+10px)] z-30 w-[340px] rounded-xl border border-zinc-800 bg-zinc-950/95 p-2 shadow-[0_20px_60px_rgba(0,0,0,0.5)] backdrop-blur"
                  >
                    {plusTab === "" ? (
                      <div className="py-1">
                        <button
                          type="button"
                          disabled={uploadBusy}
                          onClick={() => {
                            setPlusOpen(false);
                            setPlusTab("");
                            fileInputRef.current?.click();
                          }}
                          className="w-full flex items-center justify-between rounded-lg px-3 py-2 text-sm text-zinc-200 hover:bg-zinc-900/50 disabled:opacity-50"
                        >
                          <span className="flex items-center gap-2">
                            <Upload size={16} />
                            上传文件
                          </span>
                          <span className="text-xs text-zinc-500">PDF/Doc</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => setPlusTab("kb")}
                          className="w-full flex items-center justify-between rounded-lg px-3 py-2 text-sm text-zinc-200 hover:bg-zinc-900/50"
                        >
                          <span className="flex items-center gap-2">
                            <Folder size={16} />
                            选择知识库
                          </span>
                          <span className="flex items-center gap-1 text-xs text-zinc-500">
                            {selectedFolderIds.length ? `${selectedFolderIds.length} 个` : "未选择"}
                            <ChevronRight size={14} />
                          </span>
                        </button>
                      </div>
                    ) : plusTab === "kb" ? (
                      <div className="p-2">
                        <div className="flex items-center justify-between">
                          <button
                            type="button"
                            onClick={() => setPlusTab("")}
                            className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-sm text-zinc-200 hover:bg-zinc-900/50"
                          >
                            <ChevronLeft size={16} />
                            返回
                          </button>
                          <button
                            type="button"
                            onClick={refreshKnowledgeOptions}
                            className="rounded-lg px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-900/50"
                          >
                            刷新
                          </button>
                        </div>
                        <div className="mt-2 text-xs text-zinc-500">按文件夹选择（更简洁）</div>
                        <div className="mt-2 max-h-64 overflow-y-auto rounded-lg border border-zinc-900 bg-zinc-950/40 p-2">
                          {loading ? (
                            <div className="text-sm text-zinc-500">加载中…</div>
                          ) : folders.length === 0 ? (
                            <div className="text-sm text-zinc-500">暂无文件夹</div>
                          ) : (
                            <div className="space-y-1">
                              {folders.map((f) => (
                                <label key={f.folder_id} className="flex items-center gap-2 rounded-md px-2 py-1 text-sm text-zinc-200 hover:bg-zinc-900/40">
                                  <input type="checkbox" checked={selectedFolderIds.includes(f.folder_id)} onChange={() => toggleFolder(f.folder_id)} />
                                  <span className="truncate">{f.name}</span>
                                </label>
                              ))}
                            </div>
                          )}
                        </div>
                        <div className="mt-2 flex items-center justify-between">
                          <button
                            type="button"
                            onClick={() => setSelectedFolderIds([])}
                            className="rounded-lg px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-900/50"
                          >
                            清空
                          </button>
                          <button
                            type="button"
                            onClick={() => setPlusTab("kb_advanced")}
                            className="rounded-lg px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-900/50"
                          >
                            高级
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              setPlusOpen(false);
                              setPlusTab("");
                            }}
                            className="rounded-lg border border-zinc-800 bg-zinc-950/40 px-3 py-1 text-xs text-zinc-200 hover:bg-zinc-900/60"
                          >
                            完成
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="p-2">
                        <div className="flex items-center justify-between">
                          <button
                            type="button"
                            onClick={() => setPlusTab("kb")}
                            className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-sm text-zinc-200 hover:bg-zinc-900/50"
                          >
                            <ChevronLeft size={16} />
                            返回
                          </button>
                          <button
                            type="button"
                            onClick={refreshKnowledgeOptions}
                            className="rounded-lg px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-900/50"
                          >
                            刷新
                          </button>
                        </div>

                        <div className="mt-2 text-xs text-zinc-500">高级范围：按集合/表细选（可与文件夹叠加）</div>

                        <div className="mt-2 max-h-72 overflow-y-auto space-y-3 rounded-lg border border-zinc-900 bg-zinc-950/40 p-2">
                          <div>
                            <div className="mb-1 text-xs text-zinc-400">集合</div>
                            <div className="space-y-2">
                              {groupedCollections.map(([spaceType, items]) => (
                                <div key={spaceType}>
                                  <div className="mb-1 text-[11px] text-zinc-500">{spaceType}</div>
                                  <div className="space-y-1">
                                    {items.map((c) => (
                                      <label key={c.collection_id} className="flex items-center gap-2 rounded-md px-2 py-1 text-xs text-zinc-200 hover:bg-zinc-900/40">
                                        <input
                                          type="checkbox"
                                          checked={selectedCollectionIds.includes(c.collection_id)}
                                          onChange={() => toggleCollection(c.collection_id)}
                                        />
                                        <span className="truncate">{c.name}</span>
                                      </label>
                                    ))}
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>

                          <div>
                            <div className="mb-1 text-xs text-zinc-400">表</div>
                            <div className="space-y-2">
                              {groupedTables.map(([spaceType, items]) => (
                                <div key={spaceType}>
                                  <div className="mb-1 text-[11px] text-zinc-500">{spaceType}</div>
                                  <div className="space-y-1">
                                    {items.map((t) => (
                                      <label key={t.table_id} className="flex items-center gap-2 rounded-md px-2 py-1 text-xs text-zinc-200 hover:bg-zinc-900/40">
                                        <input type="checkbox" checked={selectedTableIds.includes(t.table_id)} onChange={() => toggleTable(t.table_id)} />
                                        <span className="truncate">
                                          {t.name}（{t.row_count}）
                                        </span>
                                      </label>
                                    ))}
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        </div>

                        <div className="mt-2 flex items-center justify-between">
                          <button
                            type="button"
                            onClick={() => {
                              setSelectedCollectionIds([]);
                              setSelectedTableIds([]);
                            }}
                            className="rounded-lg px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-900/50"
                          >
                            清空高级
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              setPlusOpen(false);
                              setPlusTab("");
                            }}
                            className="rounded-lg border border-zinc-800 bg-zinc-950/40 px-3 py-1 text-xs text-zinc-200 hover:bg-zinc-900/60"
                          >
                            完成
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>

              <div className="relative">
                <button
                  ref={toolsBtnRef}
                  type="button"
                  onClick={() => {
                    setToolsOpen((v) => !v);
                    setSkillsOpen(false);
                  }}
                  className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-zinc-800 bg-zinc-950/40 text-zinc-200 hover:bg-zinc-900/60"
                  title="工具"
                >
                  <Wrench size={16} />
                </button>
                {toolsOpen && (
                  <div
                    id="ai-tools-popover"
                    className="absolute left-0 top-[calc(100%+10px)] z-20 w-[340px] rounded-xl border border-zinc-800 bg-zinc-950/95 p-3 shadow-[0_20px_60px_rgba(0,0,0,0.5)] backdrop-blur"
                  >
                    <div className="text-xs text-zinc-500 mb-2">工具（允许调用）</div>
                    <div className="space-y-2">
                      {ALL_TOOLS.map((t) => (
                        <label key={t.id} className="flex items-center gap-2 text-xs text-zinc-200">
                          <input type="checkbox" checked={enabledTools.includes(t.id)} onChange={() => toggleEnabledTool(t.id)} />
                          <span className="truncate">{t.label}</span>
                        </label>
                      ))}
                    </div>
                    <div className="mt-3 flex justify-end">
                      <button
                        type="button"
                        onClick={() => setToolsOpen(false)}
                        className="rounded-lg border border-zinc-800 bg-zinc-950/40 px-3 py-1 text-xs text-zinc-200 hover:bg-zinc-900/60"
                      >
                        关闭
                      </button>
                    </div>
                  </div>
                )}
              </div>

              <div className="relative">
                <button
                  ref={skillsBtnRef}
                  type="button"
                  onClick={() => {
                    setSkillsOpen((v) => !v);
                    setToolsOpen(false);
                  }}
                  className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-zinc-800 bg-zinc-950/40 text-zinc-200 hover:bg-zinc-900/60"
                  title="技能"
                >
                  <Sparkles size={16} />
                </button>
                {skillsOpen && (
                  <div
                    id="ai-skills-popover"
                    className="absolute left-0 top-[calc(100%+10px)] z-20 w-[340px] rounded-xl border border-zinc-800 bg-zinc-950/95 p-3 shadow-[0_20px_60px_rgba(0,0,0,0.5)] backdrop-blur"
                  >
                    <div className="text-xs text-zinc-500 mb-2">技能（允许调用）</div>
                    <div className="space-y-2">
                      {ALL_SKILLS.map((s) => (
                        <label key={s.id} className="flex items-center gap-2 text-xs text-zinc-200">
                          <input type="checkbox" checked={enabledSkills.includes(s.id)} onChange={() => toggleEnabledSkill(s.id)} />
                          <span className="truncate">{s.label}</span>
                        </label>
                      ))}
                    </div>
                    <div className="mt-3 flex justify-end">
                      <button
                        type="button"
                        onClick={() => setSkillsOpen(false)}
                        className="rounded-lg border border-zinc-800 bg-zinc-950/40 px-3 py-1 text-xs text-zinc-200 hover:bg-zinc-900/60"
                      >
                        关闭
                      </button>
                    </div>
                  </div>
                )}
              </div>

              {uploadHint && <span className={uploadHint.includes("失败") ? "text-red-400" : "text-emerald-400"}>{uploadHint}</span>}
            </div>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="flex h-[calc(100vh-64px)]">
      {/* 左侧：对话历史（知识库选择移到 + 菜单，界面更简洁） */}
      <aside className="hidden md:flex w-80 shrink-0 flex-col bg-zinc-950/30">
        <div className="p-4">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm font-medium text-zinc-200">AI 互动</div>
              <div className="mt-1 text-xs text-zinc-500">对话历史</div>
            </div>
            <button
              type="button"
              onClick={startNewChat}
              className="rounded-full border border-zinc-800 bg-zinc-950/40 px-3 py-1 text-xs text-zinc-200 hover:bg-zinc-900/60"
            >
              新建
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          <details open>
            <summary className="cursor-pointer select-none text-xs font-medium uppercase tracking-wide text-zinc-500">对话历史</summary>
            <div className="mt-2 space-y-2">
              {sessions.length === 0 ? (
                <div className="text-sm text-zinc-500">暂无历史（本页会把对话保存在浏览器本地）。</div>
              ) : (
                sessions.slice(0, 30).map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => openSession(s.id)}
                    className={[
                      "w-full text-left rounded-lg border px-3 py-2",
                      s.id === activeSessionId ? "border-zinc-700 bg-zinc-900/60" : "border-zinc-800 bg-zinc-950/20 hover:bg-zinc-900/40",
                    ].join(" ")}
                  >
                    <div className="text-sm text-zinc-200 truncate">{s.title || "对话"}</div>
                    <div className="mt-1 text-xs text-zinc-500">{formatSessionTime(s.updated_at || 0)}</div>
                  </button>
                ))
              )}
            </div>
          </details>
        </div>
      </aside>

      {/* 右侧：聊天主面板 */}
      <main className="flex-1 flex flex-col bg-zinc-950/20">
        <input ref={fileInputRef} type="file" className="hidden" onChange={handleUploadFile} />
        {/* 顶栏：模型选择（参考 Open-WebUI 左上角下拉） */}
        <div className="sticky top-0 z-10 bg-zinc-950/30 backdrop-blur">
          <div className="p-4 flex flex-wrap items-center gap-2">
            <div className="text-sm text-zinc-200 truncate">模型</div>
            <select
              value={modelId}
              onChange={(e) => setModelId(e.target.value)}
              className="rounded-lg border border-zinc-800 bg-zinc-950/40 px-3 py-1 text-sm text-zinc-200"
            >
              {models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                </option>
              ))}
            </select>
          </div>
          <div className="px-4 pb-3 space-y-2">
            <KbInProgressBanner />
            <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-400">
              <span className="min-w-0 flex-1">
                <span className="text-zinc-500">知识库范围</span>{" "}
                <span className={hasExplicitKbScope ? "text-emerald-300/90" : "text-zinc-300"}>{kbScopeSummary}</span>
              </span>
              {hasExplicitKbScope ? (
                <button
                  type="button"
                  onClick={clearKbScope}
                  className="shrink-0 rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-200 hover:bg-zinc-800"
                >
                  清空范围
                </button>
              ) : null}
              <Link
                href={buildKnowledgeHref(selectedFolderIds[0] || null)}
                className="shrink-0 rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-200 hover:bg-zinc-800"
              >
                去知识库
              </Link>
              <Link
                href="/utils/pdf-knowledge"
                className="shrink-0 rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-200 hover:bg-zinc-800"
              >
                大 PDF 工具
              </Link>
            </div>
          </div>
        </div>

        {/* 对话区 */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {messages.length === 0 ? (
            <div className="h-full flex items-center justify-center">
              <div className="w-full max-w-5xl px-4">
                <div className="mx-auto max-w-3xl text-center">
                  <div className="text-lg font-medium text-zinc-200">开始对话</div>
                  <div className="mt-2 text-sm text-zinc-500">
                    未选择范围时为纯对话；在下方「+」里选择文件夹/高级集合后，再提问即可启用知识库检索（RAG）。
                  </div>
                </div>
                <div className="mt-6 flex justify-center">
                  {renderComposer("center")}
                </div>
              </div>
            </div>
          ) : (
            <div className="mx-auto max-w-3xl space-y-3">
              {messages.map((m, idx) => (
                <div key={idx} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
                  <div
                    className="max-w-[85%] rounded-2xl px-4 py-2 text-sm leading-relaxed"
                    style={{
                      backgroundColor: m.role === "user" ? "#3b82f6" : "#27272a",
                      color: "#e4e4e7",
                    }}
                  >
                    {m.content}
                    {m.role === "assistant" && m.citations && m.citations.length > 0 && (
                      <div className="mt-2">
                        <details className="cursor-pointer">
                          <summary className="text-xs text-zinc-200/80 hover:text-zinc-100">citations（{m.citations.length}）</summary>
                          <pre className="mt-2 whitespace-pre-wrap text-xs text-zinc-200/80">{JSON.stringify(m.citations, null, 2)}</pre>
                        </details>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 输入栏（底部粘住，Open-WebUI 风格） */}
        {messages.length > 0 && (
          <div className="bg-zinc-950/60 backdrop-blur">
            <div className="p-4 flex justify-center">
              {renderComposer("bottom")}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
