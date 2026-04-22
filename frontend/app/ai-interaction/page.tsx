"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { getAuthHeaders } from "../lib/auth";
import { KnowledgeWorkspacePanel } from "../components/KnowledgeWorkspacePanel";
import {
  emptyKbScopeCapsule,
  parseKbScopeFromSearchParams,
  readKbScopeCapsule,
  writeKbScopeCapsule,
} from "../lib/kb_scope_capsule";
import { ArrowUp, Check, ChevronLeft, ChevronRight, FileText, Folder, Home, MoreHorizontal, Plus, Sparkles, Trash2, Upload, Wrench, Workflow, X } from "lucide-react";

type SkillConfig = {
  id: string;
  label: string;
  description?: string;
  trigger_hint?: string;
  example?: string;
};

type ToolConfig = {
  id: string;
  label: string;
  description?: string;
};

type WorkflowConfig = {
  id: string;
  label: string;
  description?: string;
  example_prompt?: string;
};

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
  attachments?: Array<Omit<ComposerAttachment, "phase" | "progress"> & { phase: "done" | "error"; progress?: number }>;
};

const SESSIONS_LS_KEY = "orientg.ai_interaction.sessions.v1";
const SKILL_CONFIGS_LS_KEY = "orientg.ai_interaction.skill_configs.v1";
const TOOL_CONFIGS_LS_KEY = "orientg.ai_interaction.tool_configs.v1";
const WORKFLOW_CONFIGS_LS_KEY = "orientg.ai_interaction.workflow_configs.v1";

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

function formatBytes(n: number) {
  if (!Number.isFinite(n) || n < 0) return "0 B";
  if (n < 1024) return `${Math.round(n)} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

type ComposerAttachment = {
  localId: string;
  name: string;
  size: number;
  phase: "uploading" | "done" | "error";
  progress: number;
  docId?: string;
  error?: string;
};

/** 与 fetch 等价的 my-documents 上传，支持 upload 进度（XHR）。 */
function uploadMyDocumentWithProgress(
  file: File,
  opts: { folderId?: string; onProgress: (pct: number) => void }
): Promise<{ doc_id?: string }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/knowledge/my-documents/upload");
    const headers = getAuthHeaders();
    for (const [k, v] of Object.entries(headers)) {
      if (v) xhr.setRequestHeader(k, v);
    }
    let indeterminateBump = 5;
    xhr.upload.onprogress = (ev) => {
      if (ev.lengthComputable && ev.total > 0) {
        opts.onProgress(Math.min(100, Math.round((100 * ev.loaded) / ev.total)));
      } else {
        indeterminateBump = Math.min(90, indeterminateBump + 3);
        opts.onProgress(indeterminateBump);
      }
    };
    xhr.onload = () => {
      let json: Record<string, unknown> = {};
      try {
        json = JSON.parse(xhr.responseText || "{}") as Record<string, unknown>;
      } catch {
        reject(new Error("响应解析失败"));
        return;
      }
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(new Error(typeof json.detail === "string" ? json.detail : `HTTP ${xhr.status}`));
        return;
      }
      const doc_id = typeof json.doc_id === "string" ? json.doc_id : undefined;
      resolve({ doc_id });
    };
    xhr.onerror = () => reject(new Error("网络错误"));
    xhr.onabort = () => reject(new Error("已取消"));
    const fd = new FormData();
    fd.append("file", file);
    if (opts.folderId) fd.append("folder_id", opts.folderId);
    opts.onProgress(1);
    xhr.send(fd);
  });
}

export default function AiInteractionPage() {
  const sp = useSearchParams();
  const scopeHydratedRef = useRef(false);
  const sessionsHydratedRef = useRef(false);
  const [activeLeftView, setActiveLeftView] = useState<"chat" | "workspace">("chat");
  const [workspaceTab, setWorkspaceTab] = useState<"knowledge" | "skills" | "tools" | "workflows">("knowledge");
  const [startAreaHint, setStartAreaHint] = useState<string | null>(null);
  const [sessionMenuOpenId, setSessionMenuOpenId] = useState<string | null>(null);
  const suppressNextSessionClickRef = useRef(false);
  const [loading, setLoading] = useState(true);
  const [options, setOptions] = useState<KnowledgeOptionsResponse | null>(null);
  const [selectedCollectionIds, setSelectedCollectionIds] = useState<string[]>([]);
  const [selectedTableIds, setSelectedTableIds] = useState<string[]>([]);
  const [selectedFolderIds, setSelectedFolderIds] = useState<string[]>([]);

  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [uploadHint, setUploadHint] = useState<string | null>(null);
  const [composerAttachments, setComposerAttachments] = useState<ComposerAttachment[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const composingRef = useRef(false);

  const [plusOpen, setPlusOpen] = useState(false);
  const [plusTab, setPlusTab] = useState<"" | "kb" | "kb_advanced">("");
  const plusBtnRef = useRef<HTMLButtonElement>(null);

  const [toolsOpen, setToolsOpen] = useState(false);
  const [skillsOpen, setSkillsOpen] = useState(false);
  const [workflowOpen, setWorkflowOpen] = useState(false);
  const toolsBtnRef = useRef<HTMLButtonElement>(null);
  const skillsBtnRef = useRef<HTMLButtonElement>(null);
  const workflowBtnRef = useRef<HTMLButtonElement>(null);

  const [skillConfigs, setSkillConfigs] = useState<SkillConfig[]>([]);
  const [toolConfigs, setToolConfigs] = useState<ToolConfig[]>([]);
  const [workflowConfigs, setWorkflowConfigs] = useState<WorkflowConfig[]>([]);

  const [configModal, setConfigModal] = useState<null | { kind: "skills" | "tools" | "workflows"; draftJson: string; error?: string }>(null);

  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);

  // Persist sessions to localStorage as a side-effect of state changes.
  // Keeping persistence out of the state-update path avoids update loops.
  useEffect(() => {
    if (!sessionsHydratedRef.current) return;
    // 防御：若读取阶段异常导致 sessions 为空，避免把现有 localStorage 覆盖成 []
    if (sessions.length === 0) {
      try {
        const existing = localStorage.getItem(SESSIONS_LS_KEY);
        if (existing && existing.trim() && existing.trim() !== "[]") return;
      } catch {
        // ignore
      }
    }
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
                  const obj = x as {
                    id: string;
                    title?: unknown;
                    updated_at?: unknown;
                    messages?: unknown;
                    attachments?: unknown;
                  };
                  const rawMessages = (obj.messages as unknown[] | undefined) || [];
                  const messages = rawMessages
                    .filter((m): m is ChatMessage => {
                      if (!m || typeof m !== "object") return false;
                      const mm = m as { role?: unknown; content?: unknown; citations?: unknown; deny_reason?: unknown };
                      return (mm.role === "user" || mm.role === "assistant") && typeof mm.content === "string";
                    })
                    .map((m) => ({ role: m.role, content: m.content, citations: m.citations, deny_reason: m.deny_reason }));
                  const attachmentsRaw = Array.isArray(obj.attachments) ? (obj.attachments as unknown[]) : [];
                  const attachments = attachmentsRaw
                    .filter((a): a is ComposerAttachment => {
                      if (!a || typeof a !== "object") return false;
                      const aa = a as { localId?: unknown; name?: unknown; size?: unknown; phase?: unknown; docId?: unknown; error?: unknown };
                      const phaseOk = aa.phase === "done" || aa.phase === "error";
                      return (
                        typeof aa.localId === "string" &&
                        typeof aa.name === "string" &&
                        typeof aa.size === "number" &&
                        phaseOk &&
                        (aa.docId === undefined || typeof aa.docId === "string") &&
                        (aa.error === undefined || typeof aa.error === "string")
                      );
                    })
                    .map((a) => ({
                      localId: a.localId,
                      name: a.name,
                      size: a.size,
                      phase: a.phase as "done" | "error",
                      progress: 100,
                      docId: a.docId,
                      error: a.error,
                    }));
                  return {
                    id: obj.id,
                    title: typeof obj.title === "string" && obj.title.trim() ? obj.title : "对话",
                    updated_at: typeof obj.updated_at === "number" ? obj.updated_at : Date.now(),
                    messages,
                    attachments,
                  } satisfies ChatSession;
                })
                .sort((a, b) => (b.updated_at || 0) - (a.updated_at || 0));
              setSessions(cleaned);
              if (cleaned.length) {
                setActiveSessionId(cleaned[0].id);
                setMessages(cleaned[0].messages);
                setComposerAttachments((cleaned[0].attachments as ComposerAttachment[] | undefined) ?? []);
              }
            }
          }
        } catch {
          // ignore
        }
        sessionsHydratedRef.current = true;
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

  const composerUploading = useMemo(() => composerAttachments.some((a) => a.phase === "uploading"), [composerAttachments]);

  const adjustTextareaHeight = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(320, Math.max(48, el.scrollHeight))}px`;
  }, []);

  useEffect(() => {
    adjustTextareaHeight();
  }, [chatInput, adjustTextareaHeight]);

  const removeComposerAttachment = useCallback((localId: string) => {
    setComposerAttachments((prev) => prev.filter((a) => a.localId !== localId));
  }, []);

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
    if (!q || chatLoading || composerUploading) return;
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
  const ALL_SKILLS: SkillConfig[] = [
    {
      id: "skill.project_accounting_table.v1",
      label: "基础数据生成项目核算表",
      description: "根据项目与期间生成项目核算表（示例技能）。",
      trigger_hint: "勾选技能后，在提问中包含“项目核算表/生成核算表”等关键词。",
      example: "请生成项目核算表 projA 2026-04",
    },
  ];
  const ALL_TOOLS: ToolConfig[] = [
    { id: "tool.docling.convert", label: "Docling（文档解析/转换）", description: "在对话中引用 ud_xxx 并提到“docling/解析”时触发（最小闭环）。" },
    { id: "tool.mcp.*", label: "MCP 工具（按配置）", description: "占位：后续可在此编辑/管理 MCP 工具配置。" },
  ];
  const ALL_WORKFLOWS: WorkflowConfig[] = [
    {
      id: "wf.nl_finance_process.v1",
      label: "自然语言生成财务流程",
      description: "把自然语言需求整理为可执行的财务流程步骤（占位工作流）。",
      example_prompt: "把“月末结账”整理为可执行的财务流程清单，包含角色、输入输出与检查点。",
    },
  ];
  const [enabledSkills, setEnabledSkills] = useState<string[]>([]);
  const [enabledTools, setEnabledTools] = useState<string[]>([]);
  const toggleEnabledSkill = (id: string) =>
    setEnabledSkills((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  const toggleEnabledTool = (id: string) =>
    setEnabledTools((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));

  const openConfigEditor = useCallback(
    (kind: "skills" | "tools" | "workflows") => {
      const value = kind === "skills" ? skillConfigs : kind === "tools" ? toolConfigs : workflowConfigs;
      setConfigModal({ kind, draftJson: JSON.stringify(value, null, 2) });
    },
    [skillConfigs, toolConfigs, workflowConfigs]
  );

  const saveConfigEditor = useCallback(() => {
    if (!configModal) return;
    try {
      const parsed = JSON.parse(configModal.draftJson) as unknown;
      if (!Array.isArray(parsed)) throw new Error("必须是数组 JSON");
      if (configModal.kind === "skills") {
        const next = parsed as SkillConfig[];
        setSkillConfigs(next);
        localStorage.setItem(SKILL_CONFIGS_LS_KEY, JSON.stringify(next));
      } else if (configModal.kind === "tools") {
        const next = parsed as ToolConfig[];
        setToolConfigs(next);
        localStorage.setItem(TOOL_CONFIGS_LS_KEY, JSON.stringify(next));
      } else {
        const next = parsed as WorkflowConfig[];
        setWorkflowConfigs(next);
        localStorage.setItem(WORKFLOW_CONFIGS_LS_KEY, JSON.stringify(next));
      }
      setConfigModal(null);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "JSON 解析失败";
      setConfigModal((prev) => (prev ? { ...prev, error: msg } : prev));
    }
  }, [configModal]);

  useEffect(() => {
    // 载入可编辑配置（默认用内置列表；本地有则覆盖）
    try {
      const rawSkills = localStorage.getItem(SKILL_CONFIGS_LS_KEY);
      const rawTools = localStorage.getItem(TOOL_CONFIGS_LS_KEY);
      const rawWfs = localStorage.getItem(WORKFLOW_CONFIGS_LS_KEY);
      setSkillConfigs(rawSkills ? (JSON.parse(rawSkills) as SkillConfig[]) : ALL_SKILLS);
      setToolConfigs(rawTools ? (JSON.parse(rawTools) as ToolConfig[]) : ALL_TOOLS);
      setWorkflowConfigs(rawWfs ? (JSON.parse(rawWfs) as WorkflowConfig[]) : ALL_WORKFLOWS);
    } catch {
      setSkillConfigs(ALL_SKILLS);
      setToolConfigs(ALL_TOOLS);
      setWorkflowConfigs(ALL_WORKFLOWS);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 进入页面/切回对话视图时自动聚焦输入框（光标闪烁，可直接输入）
  useEffect(() => {
    if (activeLeftView !== "chat") return;
    if (configModal) return;
    if (plusOpen || toolsOpen || skillsOpen || workflowOpen) return;
    const el = textareaRef.current;
    if (!el) return;
    // 等待布局稳定后再 focus（避免首次渲染时被覆盖）
    const t = window.setTimeout(() => {
      try {
        el.focus();
      } catch {
        // ignore
      }
    }, 0);
    return () => window.clearTimeout(t);
  }, [activeLeftView, messages.length, configModal, plusOpen, toolsOpen, skillsOpen, workflowOpen]);

  // 点击空白处关闭工具/skill 菜单
  useEffect(() => {
    if (!toolsOpen && !skillsOpen && !plusOpen) return;
    const onDown = (ev: MouseEvent) => {
      const t = ev.target as HTMLElement | null;
      const toolsBtn = toolsBtnRef.current;
      const skillsBtn = skillsBtnRef.current;
      const plusBtn = plusBtnRef.current;
      const wfBtn = workflowBtnRef.current;
      if (toolsBtn && t && (toolsBtn === t || toolsBtn.contains(t))) return;
      if (skillsBtn && t && (skillsBtn === t || skillsBtn.contains(t))) return;
      if (wfBtn && t && (wfBtn === t || wfBtn.contains(t))) return;
      if (plusBtn && t && (plusBtn === t || plusBtn.contains(t))) return;
      const toolsPop = document.getElementById("ai-tools-popover");
      const skillsPop = document.getElementById("ai-skills-popover");
      const plusPop = document.getElementById("ai-plus-popover");
      const wfPop = document.getElementById("ai-workflow-popover");
      if (toolsPop && t && toolsPop.contains(t)) return;
      if (skillsPop && t && skillsPop.contains(t)) return;
      if (wfPop && t && wfPop.contains(t)) return;
      if (plusPop && t && plusPop.contains(t)) return;
      setToolsOpen(false);
      setSkillsOpen(false);
      setWorkflowOpen(false);
      setPlusOpen(false);
    };
    window.addEventListener("mousedown", onDown, true);
    return () => window.removeEventListener("mousedown", onDown, true);
  }, [toolsOpen, skillsOpen, plusOpen, workflowOpen]);

  // 点击空白处关闭“会话更多”菜单
  useEffect(() => {
    if (!sessionMenuOpenId) return;
    const onDown = (ev: MouseEvent) => {
      const t = ev.target as HTMLElement | null;
      if (!t) return;
      if (t.closest("[data-session-menu-root='1']")) return;
      setSessionMenuOpenId(null);
    };
    window.addEventListener("mousedown", onDown, true);
    return () => window.removeEventListener("mousedown", onDown, true);
  }, [sessionMenuOpenId]);

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
      const next: ChatSession = { ...current, title, updated_at: Date.now(), messages, attachments: current.attachments ?? [] };
      const merged = [next, ...prev.filter((s) => s.id !== activeSessionId)].sort((a, b) => b.updated_at - a.updated_at);
      return merged;
    });
  }, [messages, activeSessionId]);

  // attachments -> sessions（仅持久化 done/error；uploading 不入库）
  useEffect(() => {
    if (!activeSessionId) return;
    const stable = composerAttachments
      .filter((a): a is ComposerAttachment & { phase: "done" | "error" } => a.phase === "done" || a.phase === "error")
      .map((a) => ({
        localId: a.localId,
        name: a.name,
        size: a.size,
        phase: a.phase,
        docId: a.docId,
        error: a.error,
        progress: 100,
      }));
    setSessions((prev) => {
      const idx = prev.findIndex((s) => s.id === activeSessionId);
      if (idx < 0) return prev;
      const current = prev[idx];
      const next: ChatSession = { ...current, attachments: stable };
      return [next, ...prev.filter((s) => s.id !== activeSessionId)].sort((a, b) => b.updated_at - a.updated_at);
    });
  }, [composerAttachments, activeSessionId]);

  const startNewChat = () => {
    const id = `s_${Date.now()}_${Math.random().toString(16).slice(2)}`;
    const s: ChatSession = { id, title: "新对话", updated_at: Date.now(), messages: [], attachments: [] };
    setActiveSessionId(id);
    setMessages([]);
    setComposerAttachments([]);
    setUploadHint(null);
    setSessions((prev) => [s, ...prev]);
  };

  const openSession = (id: string) => {
    const s = sessions.find((x) => x.id === id);
    if (!s) return;
    setActiveSessionId(id);
    setMessages(s.messages || []);
    setComposerAttachments((s.attachments as ComposerAttachment[] | undefined) ?? []);
    setUploadHint(null);
  };

  const deleteSession = useCallback(
    (id: string) => {
      setSessions((prev) => prev.filter((s) => s.id !== id));
      setSessionMenuOpenId((cur) => (cur === id ? null : cur));
      if (activeSessionId !== id) return;
      // 删除当前会话：优先切到最新一条，否则新建
      const remaining = sessions.filter((s) => s.id !== id).sort((a, b) => (b.updated_at || 0) - (a.updated_at || 0));
      if (remaining.length) {
        const next = remaining[0];
        setActiveSessionId(next.id);
        setMessages(next.messages || []);
        setComposerAttachments((next.attachments as ComposerAttachment[] | undefined) ?? []);
        setUploadHint(null);
        setActiveLeftView("chat");
      } else {
        startNewChat();
        setActiveLeftView("chat");
        setChatInput("");
        setStartAreaHint(null);
      }
    },
    [activeSessionId, sessions]
  );

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

  const handleUploadFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    void (async () => {
      setUploadHint(null);
      const sizeMb = formatMb(file.size);
      const isPdf = (file.name || "").toLowerCase().endsWith(".pdf") || file.type === "application/pdf";
      let pages: number | null = null;
      if (isPdf && sizeMb <= BIG_PDF_SIZE_MB) {
        pages = await estimatePdfPages(file);
      }
      const isBig = isPdf && (sizeMb > BIG_PDF_SIZE_MB || (pages !== null && pages > BIG_PDF_PAGES));
      if (isBig) {
        const reasons: string[] = [];
        if (sizeMb > BIG_PDF_SIZE_MB) reasons.push(`大小约 ${sizeMb}MB > ${BIG_PDF_SIZE_MB}MB`);
        if (pages !== null && pages > BIG_PDF_PAGES) reasons.push(`页数约 ${pages} > ${BIG_PDF_PAGES}`);
        setUploadHint("检测为大 PDF：正在创建任务并跳转至「大 PDF 生知识库」…");
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

      const localId = `a_${Date.now()}_${Math.random().toString(16).slice(2)}`;
      // 默认上传到“私人知识库”（不传 folder_id），避免上传即隐式绑定 RAG 范围
      const bindFolder: string | undefined = undefined;
      setComposerAttachments((prev) => [
        ...prev,
        { localId, name: file.name, size: file.size, phase: "uploading", progress: 0 },
      ]);
      try {
        const { doc_id } = await uploadMyDocumentWithProgress(file, {
          folderId: bindFolder,
          onProgress: (pct) =>
            setComposerAttachments((prev) => prev.map((a) => (a.localId === localId ? { ...a, progress: pct } : a))),
        });
        setComposerAttachments((prev) =>
          prev.map((a) =>
            a.localId === localId ? { ...a, phase: "done" as const, progress: 100, docId: doc_id } : a
          )
        );
        await refreshKnowledgeOptions();
      } catch (err) {
        const msg = err instanceof Error ? err.message : "上传失败";
        setComposerAttachments((prev) =>
          prev.map((a) => (a.localId === localId ? { ...a, phase: "error" as const, error: msg } : a))
        );
      }
    })();
  };

  const renderComposer = (variant: "center" | "bottom") => {
    const boxClass =
      variant === "center"
        ? "w-full max-w-4xl rounded-2xl border border-zinc-800 bg-zinc-950/60 shadow-[0_10px_40px_rgba(0,0,0,0.35)]"
        : "w-full max-w-4xl rounded-2xl border border-zinc-800 bg-zinc-950/60";
    const sendDisabled = chatLoading || composerUploading || !chatInput.trim();
    return (
      <div className="w-full">
        <div className={`${boxClass} mx-auto`}>
          <div className="relative flex flex-col">
            {uploadHint ? (
              <div
                className={`px-3 pt-3 text-xs ${uploadHint.includes("失败") ? "text-red-400" : "text-emerald-400/90"}`}
              >
                {uploadHint}
              </div>
            ) : null}

            {composerAttachments.length > 0 ? (
              <div className="flex flex-wrap gap-2 px-3 pt-3">
                {composerAttachments.map((a) => (
                  <div
                    key={a.localId}
                    className="flex min-w-[160px] max-w-[240px] flex-col gap-1.5 rounded-lg border border-zinc-800 bg-zinc-900/45 px-2 py-1.5"
                  >
                    <div className="flex items-start gap-2">
                      <FileText size={14} className="mt-0.5 shrink-0 text-zinc-400" aria-hidden />
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-xs font-medium text-zinc-200" title={a.name}>
                          {a.name}
                        </div>
                        <div className="text-[11px] text-zinc-500">{formatBytes(a.size)}</div>
                      </div>
                      <button
                        type="button"
                        onClick={() => removeComposerAttachment(a.localId)}
                        className="shrink-0 rounded p-0.5 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200"
                        aria-label="移除附件"
                      >
                        <X size={14} />
                      </button>
                    </div>
                    {a.phase === "uploading" ? (
                      <div className="h-1 overflow-hidden rounded-full bg-zinc-800">
                        <div
                          className="h-full rounded-full bg-emerald-500/80 transition-[width] duration-150"
                          style={{ width: `${Math.max(6, a.progress)}%` }}
                        />
                      </div>
                    ) : null}
                    {a.phase === "done" ? (
                      <div className="flex items-center gap-1 text-[11px] text-emerald-400/90">
                        <Check size={12} strokeWidth={3} aria-hidden />
                        已上传
                      </div>
                    ) : null}
                    {a.phase === "error" ? (
                      <div className="text-[11px] leading-snug text-red-400">{a.error ?? "上传失败"}</div>
                    ) : null}
                  </div>
                ))}
              </div>
            ) : null}

          <textarea
            ref={textareaRef}
            value={chatInput}
            onChange={(e) => setChatInput(e.target.value)}
            onCompositionStart={() => {
              composingRef.current = true;
            }}
            onCompositionEnd={() => {
              composingRef.current = false;
            }}
            onKeyDown={(e) => {
              const ne = e.nativeEvent as unknown as { isComposing?: boolean } | undefined;
              const isComposing = composingRef.current || Boolean(ne?.isComposing);
              if (isComposing) return;
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void handleAsk();
              }
            }}
            placeholder="有什么我能帮您的吗？"
            rows={1}
            className="w-full min-h-[52px] max-h-[320px] resize-none overflow-y-auto border-0 bg-transparent px-3 py-3 text-base text-zinc-200 placeholder:text-zinc-500 focus:outline-none focus:ring-0"
          />

          <div className="flex items-center justify-between gap-3 px-3 pb-3 pt-2">
            <div className="flex min-w-0 flex-1 items-center gap-2 text-xs text-zinc-400">
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
                    setWorkflowOpen(false);
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
                      {toolConfigs.map((t) => (
                        <label key={t.id} className="flex items-center gap-2 text-xs text-zinc-200">
                          <input type="checkbox" checked={enabledTools.includes(t.id)} onChange={() => toggleEnabledTool(t.id)} />
                          <span className="truncate">{t.label}</span>
                        </label>
                      ))}
                    </div>
                    <div className="mt-3 flex items-center justify-between">
                      <button
                        type="button"
                        onClick={() => openConfigEditor("tools")}
                        className="rounded-lg border border-zinc-800 bg-zinc-950/40 px-3 py-1 text-xs text-zinc-200 hover:bg-zinc-900/60"
                      >
                        编辑配置
                      </button>
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
                    setWorkflowOpen(false);
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
                      {skillConfigs.map((s) => (
                        <label key={s.id} className="flex items-center gap-2 text-xs text-zinc-200">
                          <input type="checkbox" checked={enabledSkills.includes(s.id)} onChange={() => toggleEnabledSkill(s.id)} />
                          <span className="truncate">{s.label}</span>
                        </label>
                      ))}
                    </div>
                    <div className="mt-3 flex items-center justify-between">
                      <button
                        type="button"
                        onClick={() => openConfigEditor("skills")}
                        className="rounded-lg border border-zinc-800 bg-zinc-950/40 px-3 py-1 text-xs text-zinc-200 hover:bg-zinc-900/60"
                      >
                        编辑配置
                      </button>
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

              {configModal ? (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
                  <div className="w-full max-w-3xl rounded-xl border border-zinc-800 bg-zinc-950 p-4 shadow-[0_30px_90px_rgba(0,0,0,0.6)]">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="text-sm font-medium text-zinc-200">
                          编辑配置：{configModal.kind === "skills" ? "技能" : configModal.kind === "tools" ? "工具" : "工作流"}
                        </div>
                        <div className="mt-1 text-xs text-zinc-500">保存后仅影响本机页面展示与勾选列表；执行逻辑后端后续再接。</div>
                      </div>
                      <button
                        type="button"
                        onClick={() => setConfigModal(null)}
                        className="rounded-lg border border-zinc-800 bg-zinc-950/40 px-3 py-1 text-xs text-zinc-200 hover:bg-zinc-900/60"
                      >
                        关闭
                      </button>
                    </div>
                    <textarea
                      value={configModal.draftJson}
                      onChange={(e) => setConfigModal((prev) => (prev ? { ...prev, draftJson: e.target.value, error: undefined } : prev))}
                      className="mt-3 h-[50vh] w-full rounded-lg border border-zinc-800 bg-zinc-950/40 p-3 font-mono text-xs text-zinc-200 focus:outline-none"
                      spellCheck={false}
                    />
                    {configModal.error ? <div className="mt-2 text-xs text-red-400">{configModal.error}</div> : null}
                    <div className="mt-3 flex items-center justify-end gap-2">
                      <button
                        type="button"
                        onClick={() => setConfigModal(null)}
                        className="rounded-lg border border-zinc-800 bg-zinc-950/40 px-3 py-1.5 text-xs text-zinc-200 hover:bg-zinc-900/60"
                      >
                        取消
                      </button>
                      <button
                        type="button"
                        onClick={saveConfigEditor}
                        className="rounded-lg bg-zinc-200 px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-white"
                      >
                        保存
                      </button>
                    </div>
                  </div>
                </div>
              ) : null}

              <div className="relative">
                <button
                  ref={workflowBtnRef}
                  type="button"
                  onClick={() => {
                    setWorkflowOpen((v) => !v);
                    setToolsOpen(false);
                    setSkillsOpen(false);
                  }}
                  className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-zinc-800 bg-zinc-950/40 text-zinc-200 hover:bg-zinc-900/60"
                  title="工作流"
                >
                  <Workflow size={16} />
                </button>
                {workflowOpen && (
                  <div
                    id="ai-workflow-popover"
                    className="absolute left-0 top-[calc(100%+10px)] z-20 w-[340px] rounded-xl border border-zinc-800 bg-zinc-950/95 p-3 shadow-[0_20px_60px_rgba(0,0,0,0.5)] backdrop-blur"
                  >
                    <div className="text-xs text-zinc-500 mb-2">工作流</div>
                    <div className="space-y-2">
                      {workflowConfigs.map((wf) => (
                        <button
                          key={wf.id}
                          type="button"
                          onClick={() => {
                            const prompt = (wf.example_prompt || "").trim();
                            if (prompt) setChatInput((prev) => (prev ? `${prev}\n${prompt}` : prompt));
                            setWorkflowOpen(false);
                          }}
                          className="w-full rounded-lg border border-zinc-800 bg-zinc-950/40 px-3 py-2 text-left text-xs text-zinc-200 hover:bg-zinc-900/60"
                        >
                          <div className="font-medium">{wf.label}</div>
                          {wf.description ? <div className="mt-1 text-[11px] text-zinc-500 line-clamp-2">{wf.description}</div> : null}
                        </button>
                      ))}
                    </div>
                    <div className="mt-3 flex items-center justify-between">
                      <button
                        type="button"
                        onClick={() => openConfigEditor("workflows")}
                        className="rounded-lg border border-zinc-800 bg-zinc-950/40 px-3 py-1 text-xs text-zinc-200 hover:bg-zinc-900/60"
                      >
                        编辑配置
                      </button>
                      <button
                        type="button"
                        onClick={() => setWorkflowOpen(false)}
                        className="rounded-lg border border-zinc-800 bg-zinc-950/40 px-3 py-1 text-xs text-zinc-200 hover:bg-zinc-900/60"
                      >
                        关闭
                      </button>
                    </div>
                  </div>
                )}
              </div>

            </div>
            <button
              type="button"
              onClick={() => void handleAsk()}
              disabled={sendDisabled}
              className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-zinc-200 text-zinc-900 hover:bg-white disabled:opacity-50"
              title="发送"
              aria-label="发送"
            >
              {chatLoading ? <span className="text-[11px] font-medium">…</span> : <ArrowUp size={20} strokeWidth={2.2} />}
            </button>
          </div>
        </div>
      </div>
        {variant === "center" ? (
          <>
            {/* 常用工作流（参考 Open WebUI 建议区：更大留白 + 列表项） */}
            <div className="mx-auto mt-6 w-full max-w-4xl">
              <div className="text-xs text-zinc-500">常用工作流</div>
              <div className="mt-3 space-y-1">
                {[
                  ...workflowConfigs.slice(0, 3).map((wf) => ({
                    key: wf.id,
                    title: wf.label,
                    subtitle: wf.description || "",
                    prompt: wf.example_prompt || "",
                  })),
                  {
                    key: "wf.project_accounting_table.quick",
                    title: "一键生成项目核算表",
                    subtitle: "根据你提供的项目与期间，生成项目核算表结果（占位）。",
                    prompt: "请一键生成项目核算表：项目=，期间=YYYY-MM",
                  },
                  {
                    key: "wf.contracts_ledger.write",
                    title: "写入合同台账",
                    subtitle: "把当前对话/文本整理为合同台账记录并写入（占位）。",
                    prompt: "写入合同台账：请从以下信息生成台账记录并写入：",
                  },
                ].map((it) => (
                  <button
                    key={it.key}
                    type="button"
                    onClick={() => {
                      const p = (it.prompt || "").trim();
                      if (p) setChatInput((prev) => (prev ? `${prev}\n${p}` : p));
                      if (it.subtitle) setStartAreaHint(it.subtitle);
                    }}
                    className="group w-full rounded-xl bg-transparent px-4 py-2.5 text-left hover:bg-zinc-900/20"
                  >
                    <div className="text-sm font-medium text-zinc-200 group-hover:text-zinc-100">{it.title}</div>
                    {it.subtitle ? <div className="mt-1 text-xs text-zinc-500 line-clamp-2">{it.subtitle}</div> : null}
                  </button>
                ))}
                <button
                  type="button"
                  onClick={() => {
                    setActiveLeftView("workspace");
                    setWorkspaceTab("workflows");
                  }}
                  className="w-full rounded-xl bg-transparent px-4 py-2.5 text-left text-xs text-zinc-400 hover:bg-zinc-900/10"
                >
                  查看更多工作流…
                </button>
              </div>
            </div>
          </>
        ) : null}
      </div>
    );
  };

  return (
    <div className="flex h-[calc(100vh-64px)]">
      {/* 左侧：更严格贴近 Open-WebUI：顶部动作 + 导航项（带文字）+ 对话历史 */}
      <aside className="hidden md:flex flex-col w-[320px] shrink-0 border-r border-zinc-900 bg-zinc-950/30">
        <div className="p-6">
          <div className="text-2xl font-semibold tracking-tight text-zinc-100">AI 互动</div>

          <div className="mt-3 space-y-1">
            <button
              type="button"
              onClick={() => {
                startNewChat();
                setActiveLeftView("chat");
              }}
              className="flex w-full items-center gap-3 rounded-lg px-0 py-2 text-sm text-zinc-100 hover:bg-zinc-900/40"
              title="新对话"
            >
              <Plus size={16} className="shrink-0" />
              新对话
            </button>
            <button
              type="button"
              onMouseDown={() => {
                // 防止极少数情况下“点击穿透/误触”到下方会话条目导致自动切回聊天
                suppressNextSessionClickRef.current = true;
                window.setTimeout(() => {
                  suppressNextSessionClickRef.current = false;
                }, 0);
              }}
              onClick={() => setActiveLeftView("workspace")}
              className={[
                "flex w-full items-center gap-3 rounded-lg px-0 py-2 text-sm hover:bg-zinc-900/40",
                activeLeftView === "workspace" ? "bg-zinc-900/60 text-zinc-100" : "text-zinc-200",
              ].join(" ")}
              title="工作空间"
            >
              <Folder size={16} className="shrink-0" />
              工作空间
            </button>
          </div>
        </div>

        <div className="px-6 pb-2 text-xs font-medium uppercase tracking-wide text-zinc-500">对话历史</div>
        <div className="flex-1 overflow-y-auto px-6 pb-6 space-y-2">
          {sessions.length === 0 ? (
            <div className="text-sm text-zinc-500">暂无历史（本页会把对话保存在浏览器本地）。</div>
          ) : (
            sessions.slice(0, 30).map((s) => (
              <div key={s.id} className="group relative" data-session-menu-root="1">
                <button
                  type="button"
                  onClick={() => {
                    if (suppressNextSessionClickRef.current) return;
                    openSession(s.id);
                    setActiveLeftView("chat");
                  }}
                  className={[
                    "w-full text-left rounded-lg px-0 py-2 pr-10",
                    s.id === activeSessionId
                      ? "bg-transparent"
                      : "bg-transparent",
                  ].join(" ")}
                >
                  <div className="text-sm text-zinc-200 truncate">{s.title || "对话"}</div>
                  <div className="mt-1 text-xs text-zinc-500">{formatSessionTime(s.updated_at || 0)}</div>
                  {Array.isArray((s as { attachments?: unknown }).attachments) && (s as { attachments?: unknown[] }).attachments!.length ? (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {(s as { attachments?: Array<{ name?: string }> }).attachments!.slice(0, 3).map((a, i) => (
                        <span key={i} className="max-w-[140px] truncate rounded bg-zinc-900/60 px-1.5 py-0.5 text-[10px] text-zinc-300">
                          {a?.name || "附件"}
                        </span>
                      ))}
                      {(s as { attachments?: unknown[] }).attachments!.length > 3 ? <span className="text-[10px] text-zinc-500">…</span> : null}
                    </div>
                  ) : null}
                </button>

                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    e.preventDefault();
                    setSessionMenuOpenId((cur) => (cur === s.id ? null : s.id));
                  }}
                  className={[
                    "absolute right-1 top-1 inline-flex h-8 w-8 items-center justify-center rounded-md",
                    "text-white/90 hover:text-white",
                  ].join(" ")}
                  title="更多"
                  aria-label="更多"
                >
                  <MoreHorizontal size={18} />
                </button>

                {sessionMenuOpenId === s.id ? (
                  <div className="absolute right-1 top-9 z-30 w-32 rounded-lg border border-zinc-800 bg-zinc-950/95 p-1 shadow-[0_20px_60px_rgba(0,0,0,0.5)] backdrop-blur">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        e.preventDefault();
                        deleteSession(s.id);
                      }}
                      className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-xs text-red-300 hover:bg-zinc-900/50"
                    >
                      <Trash2 size={14} />
                      删除
                    </button>
                  </div>
                ) : null}
              </div>
            ))
          )}
        </div>
      </aside>

      {/* 右侧：聊天主面板 */}
      <main className="flex-1 flex flex-col bg-zinc-950/20">
        <input ref={fileInputRef} type="file" className="hidden" onChange={handleUploadFile} />
        {activeLeftView === "workspace" ? (
          <div className="sticky top-0 z-10 border-b border-zinc-900 bg-zinc-950/30 backdrop-blur">
            <div className="px-6 pt-5">
              <div className="flex items-center justify-between gap-3">
                <div className="text-lg font-medium text-zinc-200">工作空间</div>
              </div>
              <div className="mt-4 flex items-center gap-5 text-sm text-zinc-400">
                {(
                  [
                    ["knowledge", "知识库"],
                    ["skills", "技能"],
                    ["tools", "工具"],
                    ["workflows", "工作流"],
                  ] as const
                ).map(([id, label]) => (
                  <button
                    key={id}
                    type="button"
                    onClick={() => setWorkspaceTab(id)}
                    className={[
                      "pb-3 transition-colors",
                      workspaceTab === id
                        ? "border-b-2 border-zinc-200 text-zinc-200"
                        : "border-b-2 border-transparent hover:text-zinc-200",
                    ].join(" ")}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : null}

        {activeLeftView === "chat" ? (
          <>
            {/* 对话区 */}
            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {messages.length === 0 ? (
                <div className="h-full flex items-start justify-center pt-[38vh] md:pt-[34vh]">
                  <div className="w-full max-w-5xl px-4">
                    <div className="mx-auto max-w-3xl text-center">
                      <div className="text-lg font-medium text-zinc-200">开始对话</div>
                      <div className="mt-2 text-sm text-zinc-500">
                        {startAreaHint ??
                          "未选择范围时为纯对话；在下方「+」里选择文件夹/高级集合后，再提问即可启用知识库检索（RAG）。"}
                      </div>
                    </div>
                    <div className="mt-6 flex justify-center">{renderComposer("center")}</div>
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
                <div className="px-4 pt-3">
                  <div className="mx-auto w-full max-w-4xl">
                    <div className="flex items-center gap-1.5 overflow-x-auto pb-3">
                      {[
                        ...workflowConfigs.slice(0, 3).map((wf) => ({
                          key: wf.id,
                          label: wf.label,
                          subtitle: wf.description || "",
                          prompt: wf.example_prompt || "",
                        })),
                        {
                          key: "wf.project_accounting_table.quick",
                          label: "一键生成项目核算表",
                          subtitle: "根据你提供的项目与期间，生成项目核算表结果（占位）。",
                          prompt: "请一键生成项目核算表：项目=，期间=YYYY-MM",
                        },
                        {
                          key: "wf.contracts_ledger.write",
                          label: "写入合同台账",
                          subtitle: "把当前对话/文本整理为合同台账记录并写入（占位）。",
                          prompt: "写入合同台账：请从以下信息生成台账记录并写入：",
                        },
                      ].map((it) => (
                        <button
                          key={it.key}
                          type="button"
                          onClick={() => {
                            const p = (it.prompt || "").trim();
                            if (p) setChatInput((prev) => (prev ? `${prev}\n${p}` : p));
                            if (it.subtitle) setStartAreaHint(it.subtitle);
                          }}
                          className="shrink-0 rounded-full bg-transparent px-2.5 py-1 text-xs text-zinc-200 hover:bg-zinc-900/20"
                          title={it.subtitle || it.label}
                        >
                          {it.label}
                        </button>
                      ))}
                      <button
                        type="button"
                        onClick={() => {
                          setActiveLeftView("workspace");
                          setWorkspaceTab("workflows");
                        }}
                        className="shrink-0 rounded-full bg-transparent px-2.5 py-1 text-xs text-zinc-400 hover:bg-zinc-900/10"
                      >
                        更多…
                      </button>
                    </div>
                  </div>
                </div>
                <div className="p-4 pt-0">{renderComposer("bottom")}</div>
              </div>
            )}
          </>
        ) : (
          <div className="flex-1 overflow-y-auto p-4">
            {workspaceTab === "knowledge" ? (
              <div className="relative min-h-[70vh] overflow-hidden rounded-xl border border-zinc-900 bg-zinc-950/40">
                <div className="p-4">
                  <KnowledgeWorkspacePanel mode="embedded" initialFolderId={null} />
                </div>
              </div>
            ) : workspaceTab === "skills" ? (
              <div className="rounded-xl border border-zinc-900 bg-zinc-950/40 p-4">
                <div className="flex items-center justify-between">
                  <div className="text-sm font-medium text-zinc-200">技能配置</div>
                  <button
                    type="button"
                    onClick={() => openConfigEditor("skills")}
                    className="rounded-lg border border-zinc-800 bg-zinc-950/40 px-3 py-1 text-xs text-zinc-200 hover:bg-zinc-900/60"
                  >
                    编辑 JSON
                  </button>
                </div>
                <div className="mt-3 space-y-2">
                  {skillConfigs.map((s) => (
                    <div key={s.id} className="rounded-lg border border-zinc-800 bg-zinc-950/20 p-3">
                      <div className="flex items-center justify-between gap-3">
                        <div className="min-w-0">
                          <div className="text-sm font-medium text-zinc-200">{s.label}</div>
                          <div className="mt-1 text-xs text-zinc-500 font-mono">{s.id}</div>
                        </div>
                        <label className="flex items-center gap-2 text-xs text-zinc-200">
                          <input type="checkbox" checked={enabledSkills.includes(s.id)} onChange={() => toggleEnabledSkill(s.id)} />
                          启用
                        </label>
                      </div>
                      {s.description ? <div className="mt-2 text-xs text-zinc-400">{s.description}</div> : null}
                      {s.trigger_hint ? <div className="mt-1 text-[11px] text-zinc-500">触发：{s.trigger_hint}</div> : null}
                      {s.example ? <div className="mt-2 rounded border border-zinc-900 bg-zinc-950/40 p-2 text-[11px] text-zinc-300">{s.example}</div> : null}
                    </div>
                  ))}
                </div>
              </div>
            ) : workspaceTab === "tools" ? (
              <div className="rounded-xl border border-zinc-900 bg-zinc-950/40 p-4">
                <div className="flex items-center justify-between">
                  <div className="text-sm font-medium text-zinc-200">工具配置</div>
                  <button
                    type="button"
                    onClick={() => openConfigEditor("tools")}
                    className="rounded-lg border border-zinc-800 bg-zinc-950/40 px-3 py-1 text-xs text-zinc-200 hover:bg-zinc-900/60"
                  >
                    编辑 JSON
                  </button>
                </div>
                <div className="mt-3 space-y-2">
                  {toolConfigs.map((t) => (
                    <div key={t.id} className="rounded-lg border border-zinc-800 bg-zinc-950/20 p-3">
                      <div className="flex items-center justify-between gap-3">
                        <div className="min-w-0">
                          <div className="text-sm font-medium text-zinc-200">{t.label}</div>
                          <div className="mt-1 text-xs text-zinc-500 font-mono">{t.id}</div>
                        </div>
                        <label className="flex items-center gap-2 text-xs text-zinc-200">
                          <input type="checkbox" checked={enabledTools.includes(t.id)} onChange={() => toggleEnabledTool(t.id)} />
                          启用
                        </label>
                      </div>
                      {t.description ? <div className="mt-2 text-xs text-zinc-400">{t.description}</div> : null}
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="rounded-xl border border-zinc-900 bg-zinc-950/40 p-4">
                <div className="flex items-center justify-between">
                  <div className="text-sm font-medium text-zinc-200">工作流</div>
                  <button
                    type="button"
                    onClick={() => openConfigEditor("workflows")}
                    className="rounded-lg border border-zinc-800 bg-zinc-950/40 px-3 py-1 text-xs text-zinc-200 hover:bg-zinc-900/60"
                  >
                    编辑 JSON
                  </button>
                </div>
                <div className="mt-3 grid grid-cols-1 gap-2 lg:grid-cols-2">
                  {workflowConfigs.map((wf) => (
                    <button
                      key={wf.id}
                      type="button"
                      onClick={() => {
                        const prompt = (wf.example_prompt || "").trim();
                        if (prompt) setChatInput((prev) => (prev ? `${prev}\n${prompt}` : prompt));
                        setActiveLeftView("chat");
                      }}
                      className="rounded-lg border border-zinc-800 bg-zinc-950/20 p-3 text-left hover:bg-zinc-900/40"
                    >
                      <div className="text-sm font-medium text-zinc-200">{wf.label}</div>
                      {wf.description ? <div className="mt-1 text-xs text-zinc-500">{wf.description}</div> : null}
                      {wf.example_prompt ? (
                        <div className="mt-2 rounded border border-zinc-900 bg-zinc-950/40 p-2 text-[11px] text-zinc-300 line-clamp-4">
                          {wf.example_prompt}
                        </div>
                      ) : null}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
