"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { getAuthHeaders } from "../lib/auth";
import { KnowledgeWorkspacePanel } from "../components/KnowledgeWorkspacePanel";
import { PdfPackagesPanel } from "../knowledge/components/PdfPackagesPanel";
import {
  emptyKbScopeCapsule,
  parseKbScopeFromSearchParams,
  readKbScopeCapsule,
  writeKbScopeCapsule,
} from "../lib/kb_scope_capsule";
import {
  ArrowUp,
  Bot,
  Check,
  ChevronLeft,
  ChevronRight,
  FileText,
  Folder,
  MoreHorizontal,
  Plus,
  ScrollText,
  Sparkles,
  Table,
  Trash2,
  Upload,
  Wrench,
  Workflow,
  X,
} from "lucide-react";
import {
  Bar,
  BarChart,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from "recharts";

type SkillConfig = {
  id: string;
  label: string;
  description?: string;
  trigger_hint?: string;
  example?: string;
};

/** 与 GET /api/ai-interaction/skills 返回项一致（后端 agent_skills_loader） */
type SkillCatalogDoc = {
  id: string;
  name: string;
  description: string;
  body_markdown: string;
  raw_markdown: string;
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
  /** 空会话时「开始对话」下方的引导文案 */
  start_hint?: string;
  default_enabled_prompt_ids?: string[];
  default_enabled_skill_ids?: string[];
  default_enabled_tool_ids?: string[];
};

/** 内置工作流与 localStorage 合并：新条目插入，同 id 以本地覆盖字段 */
function mergeConfigById<T extends { id: string }>(builtins: T[], saved: T[] | null | undefined): T[] {
  if (!saved?.length) return builtins.slice();
  const sm = new Map(saved.map((x) => [x.id, x]));
  const out: T[] = [];
  for (const b of builtins) {
    const s = sm.get(b.id);
    out.push(s ? ({ ...b, ...s } as T) : b);
  }
  for (const s of saved) {
    if (!builtins.some((b) => b.id === s.id)) out.push(s);
  }
  return out;
}

/** 与规划 1.2.2.f 第五节及工作流默认勾选一致 */
const WF_DATA_PARSE_EXCEL_ID = "wf.data_parse.excel.v1";

/** 工作空间「提示词」：全站可复用的 Prompt 设计条目（摘要 + 可选正文，供列示与后续链路引用） */
type PromptConfig = {
  id: string;
  label: string;
  description?: string;
  /** system | user | other */
  role?: string;
  /** 如 data_parse、global */
  scope?: string;
  /** 列示用短摘要，避免把长 prompt 塞进列表 */
  summary?: string;
  /** 设计稿/正文，本地编辑；勿存生产密钥 */
  body?: string;
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

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  deny_reason?: string;
  chart_spec?: Record<string, unknown> | null;
  table_spec?: { columns: string[]; rows: string[][] } | null;
};

type ChatSession = {
  id: string;
  title: string;
  updated_at: number;
  messages: ChatMessage[];
  attachments?: Array<Omit<ComposerAttachment, "phase" | "progress"> & { phase: "done" | "error"; progress?: number }>;
  data_parse_session_id?: string | null;
  active_workflow_id?: string | null;
  enabled_skills?: string[];
  enabled_tools?: string[];
  enabled_prompt_ids?: string[];
  start_area_hint?: string | null;
};

const SESSIONS_LS_KEY = "orientg.ai_interaction.sessions.v1";
const SKILL_CONFIGS_LS_KEY = "orientg.ai_interaction.skill_configs.v1";
const TOOL_CONFIGS_LS_KEY = "orientg.ai_interaction.tool_configs.v1";
const WORKFLOW_CONFIGS_LS_KEY = "orientg.ai_interaction.workflow_configs.v1";
const PROMPT_CONFIGS_LS_KEY = "orientg.ai_interaction.prompt_configs.v1";

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
  /** 知识库上传 ud_… */
  docId?: string;
  error?: string;
  /** kb_doc（默认）| 电子表数据解析工作流上传 */
  kind?: "kb_doc" | "excel_parse";
  /** kind=excel_parse 且 phase=done 时由 /api/data-parse/upload 返回 */
  dataParseSessionId?: string;
};

function activeExcelParseSessionId(attachments: ComposerAttachment[]): string | null {
  const row = attachments.find(
    (a) =>
      a.kind === "excel_parse" &&
      a.phase === "done" &&
      typeof a.dataParseSessionId === "string" &&
      a.dataParseSessionId.trim().length > 0
  );
  return row?.dataParseSessionId?.trim() ?? null;
}

type ChartSpecLike = {
  xAxis?: { data?: Array<string | number> };
  series?: Array<{ name?: string; type?: string; data?: Array<number | string | null> }>;
};

const AI_CHART_COLORS = {
  current: "#2563eb",
  previous: "#3f3f46",
  actual: "#22c55e",
  lastYear: "#52525b",
};

function aiChartRowsFromSpec(spec: ChartSpecLike): Array<Record<string, string | number>> {
  const labels = spec?.xAxis?.data ?? [];
  const series = spec?.series ?? [];
  return labels.map((name, i) => {
    const row: Record<string, string | number> = { name: String(name ?? "") };
    for (const s of series) {
      const key = String(s?.name || "系列");
      const raw = s?.data?.[i];
      const num = typeof raw === "number" ? raw : Number(raw);
      row[key] = Number.isFinite(num) ? num : 0;
    }
    return row;
  });
}

function aiSeriesColor(name: string, idx: number): string {
  const n = (name || "").toLowerCase();
  if (n.includes("本年") || n.includes("current")) return AI_CHART_COLORS.current;
  if (n.includes("去年") || n.includes("往年") || n.includes("last") || n.includes("previous")) return AI_CHART_COLORS.previous;
  if (n.includes("目标") || n.includes("target") || n.includes("预算")) return AI_CHART_COLORS.lastYear;
  if (idx === 0) return AI_CHART_COLORS.actual;
  return [AI_CHART_COLORS.current, AI_CHART_COLORS.previous, AI_CHART_COLORS.actual, AI_CHART_COLORS.lastYear][idx % 4];
}

function AiInlineChart({ spec }: { spec: Record<string, unknown> }) {
  const opt = spec as ChartSpecLike;
  const rows = aiChartRowsFromSpec(opt);
  const series = opt?.series ?? [];
  if (!rows.length || !series.length) return null;
  const isLine = series.every((s) => (s?.type || "bar").toLowerCase() === "line");
  return (
    <div className="mt-2 rounded border border-zinc-700 bg-zinc-900/60 p-2">
      <ResponsiveContainer width="100%" height={220}>
        {isLine ? (
          <LineChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <XAxis dataKey="name" tick={{ fontSize: 11 }} stroke="#71717a" />
            <YAxis tick={{ fontSize: 11 }} stroke="#71717a" />
            <RechartsTooltip contentStyle={{ backgroundColor: "#18181b", border: "1px solid #3f3f46" }} />
            <Legend />
            {series.map((s, idx) => {
              const name = String(s?.name || `系列${idx + 1}`);
              return (
                <Line key={`${name}-${idx}`} type="monotone" dataKey={name} stroke={aiSeriesColor(name, idx)} strokeWidth={2} dot={{ r: 2 }} />
              );
            })}
          </LineChart>
        ) : (
          <BarChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <XAxis dataKey="name" tick={{ fontSize: 11 }} stroke="#71717a" />
            <YAxis tick={{ fontSize: 11 }} stroke="#71717a" />
            <RechartsTooltip contentStyle={{ backgroundColor: "#18181b", border: "1px solid #3f3f46" }} />
            <Legend />
            {series.map((s, idx) => {
              const name = String(s?.name || `系列${idx + 1}`);
              return <Bar key={`${name}-${idx}`} dataKey={name} fill={aiSeriesColor(name, idx)} radius={[4, 4, 0, 0]} />;
            })}
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}

/** AI 对手方头像 + 名称 + 动态状态（参考 Open-WebUI） */
function AiAvatar({ status }: { status?: "idle" | "thinking" | "typing" }) {
  const statusText =
    status === "thinking" ? "思考中…" : status === "typing" ? "正在输入…" : null;
  return (
    <div className="flex items-center gap-2">
      <div className="relative flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-emerald-500/15 text-emerald-400">
        <Bot size={15} strokeWidth={2} />
        {status === "thinking" && (
          <span className="absolute -right-0.5 -top-0.5 flex h-2.5 w-2.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-400" />
          </span>
        )}
      </div>
      <div className="flex items-center gap-1.5">
        <span className="text-xs font-medium text-zinc-300">AI 助手</span>
        {statusText ? (
          <span className="text-[11px] text-emerald-400/80 animate-pulse">{statusText}</span>
        ) : null}
      </div>
    </div>
  );
}

/** 打字机动画（三个跳动圆点） */
function TypingIndicator() {
  return (
    <div className="flex items-center gap-1 px-1 py-2">
      <span
        className="inline-block h-1.5 w-1.5 rounded-full bg-zinc-400"
        style={{ animation: "typingBounce 1.4s infinite ease-in-out both", animationDelay: "0ms" }}
      />
      <span
        className="inline-block h-1.5 w-1.5 rounded-full bg-zinc-400"
        style={{ animation: "typingBounce 1.4s infinite ease-in-out both", animationDelay: "160ms" }}
      />
      <span
        className="inline-block h-1.5 w-1.5 rounded-full bg-zinc-400"
        style={{ animation: "typingBounce 1.4s infinite ease-in-out both", animationDelay: "320ms" }}
      />
      <style jsx>{`
        @keyframes typingBounce {
          0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
          40% { transform: scale(1); opacity: 1; }
        }
      `}</style>
    </div>
  );
}

function AiInlineTable({ spec }: { spec: { columns: string[]; rows: string[][] } }) {
  const columns = spec.columns || [];
  const rows = spec.rows || [];
  if (!columns.length) return null;
  return (
    <div className="mt-2 overflow-x-auto rounded border border-zinc-700">
      <table className="w-full min-w-[240px] text-left text-xs">
        <thead>
          <tr className="border-b border-zinc-700 bg-zinc-900/70">
            {columns.map((c, i) => (
              <th key={`${c}-${i}`} className="px-2 py-1.5 text-zinc-300">
                {c || `列${i + 1}`}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 30).map((row, i) => (
            <tr key={i} className="border-b border-zinc-800">
              {columns.map((_, j) => (
                <td key={j} className="px-2 py-1 text-zinc-400">
                  {String(row[j] ?? "")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

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
  const [workspaceTab, setWorkspaceTab] = useState<"knowledge" | "pdf_packages" | "prompts" | "skills" | "tools" | "workflows">("knowledge");
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
  const [ragItems, setRagItems] = useState<Array<{ package_id: string; name: string; created_at?: string | null }>>([]);
  const [ragBusyId, setRagBusyId] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const composingRef = useRef(false);
  /** 上传解析完成后立即发消息时，React state 可能尚未提交；优先用 ref 携带 session_id */
  const excelParseSidRef = useRef<string | null>(null);

  const [plusOpen, setPlusOpen] = useState(false);
  const [plusTab, setPlusTab] = useState<"" | "kb" | "kb_advanced">("");
  const plusBtnRef = useRef<HTMLButtonElement>(null);

  const [toolsOpen, setToolsOpen] = useState(false);
  const [skillsOpen, setSkillsOpen] = useState(false);
  const [promptsOpen, setPromptsOpen] = useState(false);
  const [workflowOpen, setWorkflowOpen] = useState(false);
  const toolsBtnRef = useRef<HTMLButtonElement>(null);
  const skillsBtnRef = useRef<HTMLButtonElement>(null);
  const promptsBtnRef = useRef<HTMLButtonElement>(null);
  const workflowBtnRef = useRef<HTMLButtonElement>(null);

  const [skillConfigs, setSkillConfigs] = useState<SkillConfig[]>([]);
  const [toolConfigs, setToolConfigs] = useState<ToolConfig[]>([]);
  const [workflowConfigs, setWorkflowConfigs] = useState<WorkflowConfig[]>([]);
  const [promptConfigs, setPromptConfigs] = useState<PromptConfig[]>([]);
  const [skillCatalog, setSkillCatalog] = useState<SkillCatalogDoc[] | null>(null);
  const [skillCatalogLoading, setSkillCatalogLoading] = useState(false);
  const [skillCatalogError, setSkillCatalogError] = useState<string | null>(null);

  const [configModal, setConfigModal] = useState<null | { kind: "skills" | "tools" | "workflows" | "prompts"; draftJson: string; error?: string }>(null);

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

  const refreshRagPackages = useCallback(async () => {
    try {
      const res = await fetch("/api/knowledge/rag-packages", { credentials: "include", headers: getAuthHeaders() });
      const data = (await res.json().catch(() => ({}))) as { items?: Array<{ package_id: string; name: string; created_at?: string | null }> };
      const items = Array.isArray(data.items) ? data.items : [];
      setRagItems(items);
    } catch {
      // ignore
    }
  }, []);

  const downloadRagExport = useCallback(async (pkgId: string, profile: "openwebui" | "cn_kb" | "standard") => {
    setRagBusyId(pkgId);
    try {
      const res = await fetch(
        `/api/knowledge/rag-packages/${encodeURIComponent(pkgId)}/export?profile=${encodeURIComponent(profile)}`,
        { credentials: "include", headers: getAuthHeaders() },
      );
      if (!res.ok) return;
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
    } finally {
      setRagBusyId(null);
    }
  }, []);

  const deleteRagPackage = useCallback(async (pkgId: string) => {
    if (!confirm("确定删除该大文档 RAG 包？（将同时删除磁盘产物）")) return;
    setRagBusyId(pkgId);
    try {
      const res = await fetch(`/api/knowledge/rag-packages/${encodeURIComponent(pkgId)}`, {
        method: "DELETE",
        credentials: "include",
        headers: getAuthHeaders(),
      });
      if (!res.ok) return;
      await refreshRagPackages();
    } finally {
      setRagBusyId(null);
    }
  }, [refreshRagPackages]);

  // 清理已消费的 URL 参数（同页面「带到 AI 互动」会通过 router.push 改变 search params）
  const replaceConsumedParams = useCallback((keys: string[]) => {
    if (typeof window === "undefined") return;
    try {
      const url = new URL(window.location.href);
      for (const k of keys) url.searchParams.delete(k);
      const qs = url.searchParams.toString();
      window.history.replaceState({}, "", qs ? `${url.pathname}?${qs}` : url.pathname);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    if (workspaceTab !== "pdf_packages") return;
    void refreshRagPackages();
  }, [workspaceTab, refreshRagPackages]);

  // 首次加载：合并「范围胶囊」localStorage + URL 参数 → 显式范围（仅执行一次）
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
    if (hadUrlScope) {
      replaceConsumedParams(["folder_id", "folders", "collections", "tables"]);
    }
    scopeHydratedRef.current = true;
  }, [loading, sp, replaceConsumedParams]);

  // 响应后续 URL 参数变化（如从工作空间「带到 AI 互动」按钮）：处理 doc_ids / view / scope
  useEffect(() => {
    if (loading || !scopeHydratedRef.current) return;
    const docIdsRaw = (sp.get("doc_ids") || "").trim();
    const view = (sp.get("view") || "").trim().toLowerCase();
    const fromUrl = parseKbScopeFromSearchParams(new URLSearchParams(sp.toString()));
    const hadUrlScope = Boolean(
      (fromUrl.folder_ids && fromUrl.folder_ids.length) ||
        (fromUrl.collection_ids && fromUrl.collection_ids.length) ||
        (fromUrl.table_ids && fromUrl.table_ids.length)
    );

    let consumed = false;

    // 响应 scope 参数（folder_id/collections/tables）
    if (hadUrlScope) {
      if (fromUrl.folder_ids?.length) setSelectedFolderIds(fromUrl.folder_ids);
      if (fromUrl.collection_ids?.length) setSelectedCollectionIds(fromUrl.collection_ids);
      if (fromUrl.table_ids?.length) setSelectedTableIds(fromUrl.table_ids);
      writeKbScopeCapsule({
        folder_ids: fromUrl.folder_ids ?? [],
        collection_ids: fromUrl.collection_ids ?? [],
        table_ids: fromUrl.table_ids ?? [],
      });
      replaceConsumedParams(["folder_id", "folders", "collections", "tables"]);
      consumed = true;
    }

    // v3：从 Knowledge「带到 AI」带入 doc_ids，直接在输入区显示引用（不隐式绑定 RAG 范围）
    if (docIdsRaw) {
      const ids = Array.from(new Set(docIdsRaw.split(",").map((x) => x.trim()).filter(Boolean)));
      void (async () => {
        try {
          const res = await fetch("/api/knowledge/my-documents", { credentials: "include", headers: getAuthHeaders() });
          const data = (await res.json().catch(() => ({}))) as { items?: Array<{ doc_id: string; title?: string; original_filename?: string; size_bytes?: number }> };
          const items = Array.isArray(data.items) ? data.items : [];
          const byId = new Map(items.map((d) => [String(d.doc_id || "").trim(), d]));
          const now = Date.now();
          const atts: ComposerAttachment[] = ids.map((id, idx) => {
            const d = byId.get(id);
            const name = String(d?.original_filename || d?.title || id);
            return {
              localId: `kb_${now}_${idx}`,
              name,
              size: Number(d?.size_bytes ?? 0) || 0,
              phase: "done",
              progress: 100,
              docId: id,
              kind: "kb_doc",
            };
          });
          setComposerAttachments((prev) => {
            const existed = new Set(prev.map((p) => String(p.docId || "")));
            const mergedAtts = [...prev];
            for (const a of atts) {
              if (a.docId && existed.has(a.docId)) continue;
              mergedAtts.push(a);
            }
            return mergedAtts;
          });
        } catch {
          // ignore
        }
      })();
      replaceConsumedParams(["doc_ids", "view"]);
      consumed = true;
    }
    // 如果 URL 明确指定 view=chat，或带入 scope/doc_ids，优先回到聊天界面
    if (view === "chat" || consumed) {
      setActiveLeftView("chat");
    }
  }, [loading, sp, replaceConsumedParams]);

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
                      const aa = a as {
                        localId?: unknown;
                        name?: unknown;
                        size?: unknown;
                        phase?: unknown;
                        docId?: unknown;
                        error?: unknown;
                        kind?: unknown;
                        dataParseSessionId?: unknown;
                      };
                      const phaseOk = aa.phase === "done" || aa.phase === "error";
                      const kindOk =
                        aa.kind === undefined || aa.kind === "kb_doc" || aa.kind === "excel_parse";
                      return (
                        typeof aa.localId === "string" &&
                        typeof aa.name === "string" &&
                        typeof aa.size === "number" &&
                        phaseOk &&
                        kindOk &&
                        (aa.docId === undefined || typeof aa.docId === "string") &&
                        (aa.error === undefined || typeof aa.error === "string") &&
                        (aa.dataParseSessionId === undefined || typeof aa.dataParseSessionId === "string")
                      );
                    })
                    .map((a) => {
                      const aa = a as ComposerAttachment & { kind?: unknown; dataParseSessionId?: unknown };
                      return {
                        localId: a.localId,
                        name: a.name,
                        size: a.size,
                        phase: a.phase as "done" | "error",
                        progress: 100,
                        docId: a.docId,
                        error: a.error,
                        ...(aa.kind === "excel_parse" || aa.kind === "kb_doc" ? { kind: aa.kind } : {}),
                        ...(typeof aa.dataParseSessionId === "string" ? { dataParseSessionId: aa.dataParseSessionId } : {}),
                      };
                    });
                  const wf = obj as {
                    data_parse_session_id?: unknown;
                    active_workflow_id?: unknown;
                    enabled_skills?: unknown;
                    enabled_tools?: unknown;
                    enabled_prompt_ids?: unknown;
                    start_area_hint?: unknown;
                  };
                  return {
                    id: obj.id,
                    title: typeof obj.title === "string" && obj.title.trim() ? obj.title : "对话",
                    updated_at: typeof obj.updated_at === "number" ? obj.updated_at : Date.now(),
                    messages,
                    attachments,
                    data_parse_session_id: typeof wf.data_parse_session_id === "string" ? wf.data_parse_session_id : null,
                    active_workflow_id: typeof wf.active_workflow_id === "string" ? wf.active_workflow_id : null,
                    enabled_skills: Array.isArray(wf.enabled_skills)
                      ? (wf.enabled_skills as unknown[]).filter((x): x is string => typeof x === "string")
                      : undefined,
                    enabled_tools: Array.isArray(wf.enabled_tools)
                      ? (wf.enabled_tools as unknown[]).filter((x): x is string => typeof x === "string")
                      : undefined,
                    enabled_prompt_ids: Array.isArray(wf.enabled_prompt_ids)
                      ? (wf.enabled_prompt_ids as unknown[]).filter((x): x is string => typeof x === "string")
                      : undefined,
                    start_area_hint: typeof wf.start_area_hint === "string" ? wf.start_area_hint : null,
                  } satisfies ChatSession;
                })
                .sort((a, b) => (b.updated_at || 0) - (a.updated_at || 0));
              setSessions(cleaned);
              if (cleaned.length) {
                const s0 = cleaned[0];
                setActiveSessionId(s0.id);
                setMessages(s0.messages);
                const att0 = (s0.attachments as ComposerAttachment[] | undefined) ?? [];
                setComposerAttachments(att0);
                setDataParseSessionId(activeExcelParseSessionId(att0) ?? s0.data_parse_session_id ?? null);
                excelParseSidRef.current =
                  activeExcelParseSessionId(att0) ??
                  (typeof s0.data_parse_session_id === "string" ? s0.data_parse_session_id : null) ??
                  null;
                setActiveWorkflowId(s0.active_workflow_id ?? null);
                setEnabledSkills(Array.isArray(s0.enabled_skills) ? [...s0.enabled_skills] : []);
                setEnabledTools(Array.isArray(s0.enabled_tools) ? [...s0.enabled_tools] : []);
                setEnabledPromptIds(Array.isArray(s0.enabled_prompt_ids) ? [...s0.enabled_prompt_ids] : []);
                setStartAreaHint(s0.start_area_hint ?? null);
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

  useEffect(() => {
    if (loading || activeLeftView !== "workspace" || workspaceTab !== "skills") return;
    let cancelled = false;
    void (async () => {
      setSkillCatalogLoading(true);
      setSkillCatalogError(null);
      try {
        const res = await fetch("/api/ai-interaction/skills", {
          credentials: "include",
          headers: getAuthHeaders(),
        });
        const data = (await res.json().catch(() => ({}))) as { skills?: SkillCatalogDoc[]; detail?: string };
        if (!res.ok) {
          throw new Error(typeof data.detail === "string" ? data.detail : `HTTP ${res.status}`);
        }
        if (!cancelled) setSkillCatalog(Array.isArray(data.skills) ? data.skills : []);
      } catch (e) {
        if (!cancelled) setSkillCatalogError(e instanceof Error ? e.message : "加载技能文档失败");
      } finally {
        if (!cancelled) setSkillCatalogLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [loading, activeLeftView, workspaceTab]);

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
    setComposerAttachments((prev) => {
      const victim = prev.find((a) => a.localId === localId);
      const next = prev.filter((a) => a.localId !== localId);
      if (victim?.kind === "excel_parse") {
        const still = next.some((a) => a.kind === "excel_parse" && a.phase === "done" && a.dataParseSessionId);
        if (!still) {
          setDataParseSessionId(null);
          excelParseSidRef.current = null;
        }
      }
      return next;
    });
  }, []);

  const toggleFolder = (id: string) => {
    setSelectedFolderIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const toggleCollection = (id: string) => {
    setSelectedCollectionIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const toggleTable = (id: string) => {
    setSelectedTableIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
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
    {
      id: "skill.data_parse.interpret.v1",
      label: "电子表解读（聚合指标 + 工具调用）",
      description: "与「数据解析」后端会话配合：仅基于 read_metrics 等工具返回作答（工作流默认勾选）。",
      trigger_hint: "上传 Excel 并存在解析会话后，在提问中描述分析或画图需求。",
      example: "根据当前表做收入趋势分析，并提示主要风险。",
    },
    {
      id: "skill.data_parse.playbook.v1",
      label: "数据解析 Playbook（口径与话术包）",
      description: "原「Playbook」口径类内容的工作流封装：注入只读合规话术，与 kanban_skills 及 prompt.* 勾选项协同。",
      trigger_hint: "工作流「电子表数据解析」默认勾选；也可单独勾选后上传表格解读。",
      example: "按 Playbook 口径总结各表可信度与缺失项。",
    },
    {
      id: "skill.data_parse.xlsx.v1",
      label: "电子表解析工作流（XLSX）",
      description:
        "中文版工作流技能：清洗/口径/汇总/制图等行为约束；与「电子表解读」「Playbook」叠加注入 System；仅基于 read_metrics 等工具结果，禁止编造与行级明文外泄。",
      trigger_hint: "工作流「电子表数据解析」默认勾选；走 /api/data-parse/chat 时随 enabled_skills 生效。",
      example: "根据当前上传表格，列出各工作表用途与主要风险（勿编造具体数值）。",
    },
  ];
  const ALL_TOOLS: ToolConfig[] = [
    { id: "tool.docling.convert", label: "Docling（文档解析/转换）", description: "在对话中引用 ud_xxx 并提到“docling/解析”时触发（最小闭环）。" },
    {
      id: "tool.data_parse.read_metrics",
      label: "read_metrics（聚合指标）",
      description: "数据解析会话内只读：表结构摘要、列画像、聚合指标（与规划 1.2.2.f §6.1 一致；走 /api/data-parse/chat 时由模型侧工具调用）。",
    },
    {
      id: "tool.data_parse.template_render",
      label: "template_render（模板短文本）",
      description: "数据解析链路内按白名单模板渲染结论/风险/建议片段（§6.2）。",
    },
    { id: "tool.mcp.*", label: "MCP 工具（按配置）", description: "占位：后续可在此编辑/管理 MCP 工具配置。" },
  ];
  const ALL_WORKFLOWS: WorkflowConfig[] = [
    {
      id: "wf.nl_finance_process.v1",
      label: "自然语言生成财务流程",
      description: "把自然语言需求整理为可执行的财务流程步骤（占位工作流）。",
      example_prompt: "把“月末结账”整理为可执行的财务流程清单，包含角色、输入输出与检查点。",
      start_hint: "把需求整理为可执行步骤时可直接发送；未选知识库范围时为纯对话。",
    },
    {
      id: WF_DATA_PARSE_EXCEL_ID,
      label: "电子表数据解析",
      description: "上传 Excel → 解析会话 → 基于聚合指标与工具解读/画图；与 /utils/excel-kanban 同源后端。",
      start_hint: "请先通过「+ → 上传文件」选择 .xlsx/.xls；上传成功后可提问或要求画图。未上传前发送将提示先上传表格。",
      example_prompt: "请根据已上传的表格，用要点列出各工作表用途与主要风险（勿编造具体数值）。",
      default_enabled_prompt_ids: [
        "prompt.data_parse.lexicon.financial_terms.v1",
        "prompt.data_parse.lexicon.industry_metrics.v1",
        "prompt.data_parse.table_layout_conventions.v1",
        "prompt.data_parse.risk_and_missing_data_copy.v1",
        "prompt.data_parse.output_shape.v1",
      ],
      default_enabled_skill_ids: [
        "skill.data_parse.interpret.v1",
        "skill.data_parse.playbook.v1",
        "skill.data_parse.xlsx.v1",
      ],
      default_enabled_tool_ids: ["tool.data_parse.read_metrics", "tool.data_parse.template_render"],
    },
  ];
  /** 与规划文档 `规划/1.2.2.f_数据解析设计.md` 第五节 prompt.* 表一致 */
  const ALL_PROMPTS: PromptConfig[] = [
    {
      id: "prompt.data_parse.lexicon.financial_terms.v1",
      label: "财务术语（lexicon）",
      role: "system",
      scope: "data_parse",
      description: "一行一条财务术语定义，供拼接 system。",
      summary: "无真实金额/人名；仅定义。",
      body: "",
    },
    {
      id: "prompt.data_parse.lexicon.industry_metrics.v1",
      label: "指标口径（lexicon）",
      role: "system",
      scope: "data_parse",
      description: "流水、毛利、同比等口径，与经营看板一致。",
      summary: "与经营看板口径一致，变更走评审。",
      body: "",
    },
    {
      id: "prompt.data_parse.table_layout_conventions.v1",
      label: "表格布局约定",
      role: "system",
      scope: "data_parse",
      description: "汇总/分组/透视等布局约定。",
      summary: "指导重排表格结构，不提供可执行脚本。",
      body: "",
    },
    {
      id: "prompt.data_parse.risk_and_missing_data_copy.v1",
      label: "缺失与风险提示话术",
      role: "system",
      scope: "data_parse",
      description: "缺失/异常时的表述模板。",
      summary: "缺数据不说有数据。",
      body: "",
    },
    {
      id: "prompt.data_parse.output_shape.v1",
      label: "输出 JSON 形状说明",
      role: "system",
      scope: "data_parse",
      description: "与解读 JSON Schema 一致的人类可读摘要。",
      summary: "conclusion / risks[] / suggestions[] 等字段说明。",
      body: "",
    },
  ];
  const [enabledSkills, setEnabledSkills] = useState<string[]>([]);
  const [enabledTools, setEnabledTools] = useState<string[]>([]);
  const [enabledPromptIds, setEnabledPromptIds] = useState<string[]>([]);
  const [activeWorkflowId, setActiveWorkflowId] = useState<string | null>(null);
  const [dataParseSessionId, setDataParseSessionId] = useState<string | null>(null);
  const toggleEnabledSkill = (id: string) =>
    setEnabledSkills((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  const toggleEnabledTool = (id: string) =>
    setEnabledTools((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  const toggleEnabledPrompt = (id: string) =>
    setEnabledPromptIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));

  useEffect(() => {
    excelParseSidRef.current = activeExcelParseSessionId(composerAttachments) ?? dataParseSessionId ?? null;
  }, [composerAttachments, dataParseSessionId]);

  const applyWorkflow = useCallback((wf: WorkflowConfig) => {
    setActiveWorkflowId(wf.id);
    setStartAreaHint((wf.start_hint ?? wf.description ?? "").trim() || null);
    setEnabledPromptIds([...(wf.default_enabled_prompt_ids ?? [])]);
    setEnabledSkills([...(wf.default_enabled_skill_ids ?? [])]);
    setEnabledTools([...(wf.default_enabled_tool_ids ?? [])]);
    // 切换工作流时移除电子表附件，进入新工作流的「等待上传 / 重新绑定」态
    setComposerAttachments((prev) => prev.filter((a) => a.kind !== "excel_parse"));
    setDataParseSessionId(null);
    excelParseSidRef.current = null;
    const prompt = (wf.example_prompt || "").trim();
    if (prompt) setChatInput((prev) => (prev ? `${prev}\n${prompt}` : prompt));
    setWorkflowOpen(false);
    setToolsOpen(false);
    setSkillsOpen(false);
    setPromptsOpen(false);
  }, []);

  const deactivateWorkflow = useCallback(() => {
    setActiveWorkflowId(null);
    setStartAreaHint(null);
    // 不主动清空 enabled_*：避免用户误触后丢失已勾选能力；仅解除“工作流门禁/路由”。
    setWorkflowOpen(false);
  }, []);

  const buildPromptAddon = useCallback(() => {
    const parts: string[] = [];
    for (const pid of enabledPromptIds) {
      const p = promptConfigs.find((x) => x.id === pid);
      if (!p) continue;
      const head = [p.id, p.label].filter(Boolean).join(" — ");
      const bits = [p.summary, p.body].filter((x) => typeof x === "string" && x.trim());
      parts.push(bits.length ? `${head}\n${bits.join("\n")}` : head);
    }
    return parts.join("\n\n---\n\n");
  }, [enabledPromptIds, promptConfigs]);

  const handleAsk = async () => {
    const q = chatInput.trim();
    if (!q || chatLoading || composerUploading) return;
    const excelSid =
      excelParseSidRef.current?.trim() ||
      activeExcelParseSessionId(composerAttachments) ||
      dataParseSessionId ||
      null;
    setChatLoading(true);
    setChatInput("");
    ensureActiveSession();
    setMessages((prev) => [...prev, { role: "user", content: q }]);
    try {
      if (activeWorkflowId === WF_DATA_PARSE_EXCEL_ID && !excelSid) {
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content:
              "当前为「电子表数据解析」工作流：请先用下方「+」→「上传文件」选择 .xlsx 或 .xls，等待解析完成后再提问。",
            citations: [],
          },
        ]);
        return;
      }

      // 电子表数据解析：已存在解析会话时走 /api/data-parse/chat（与 excel-kanban 同源）
      if (excelSid && activeWorkflowId === WF_DATA_PARSE_EXCEL_ID) {
        const dpSkills = enabledSkills.filter((id) => id.startsWith("skill.data_parse."));
        const prompt_addon = buildPromptAddon().trim() || undefined;
        const extra_session_ids = composerAttachments
          .filter((a) => a.kind === "excel_parse" && a.phase === "done" && a.dataParseSessionId && a.dataParseSessionId !== excelSid)
          .map((a) => String(a.dataParseSessionId || "").trim())
          .filter(Boolean);
        const res = await fetch("/api/data-parse/chat", {
          method: "POST",
          headers: { ...getAuthHeaders(), "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({
            session_id: excelSid,
            extra_session_ids: extra_session_ids.length ? extra_session_ids : undefined,
            message: q,
            enabled_skills: dpSkills.length ? dpSkills : undefined,
            prompt_addon,
          }),
        });
        const raw = (await res.json().catch(() => ({}))) as {
          detail?: string;
          reply?: string;
          chart_spec?: Record<string, unknown> | null;
          table_spec?: { columns: string[]; rows: string[][] } | null;
        };
        if (!res.ok) {
          const deny = typeof raw.detail === "string" ? raw.detail : "数据解析对话失败";
          setMessages((prev) => [...prev, { role: "assistant", content: deny, citations: [] }]);
          return;
        }
        const reply = raw.reply ?? "";
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: reply,
            citations: [],
            chart_spec: raw.chart_spec ?? null,
            table_spec: raw.table_spec ?? null,
          },
        ]);
        return;
      }

      const nextMessages = [...messages, { role: "user" as const, content: q }];
      // 收集 composerAttachments 中 kb_doc 类型的文档引用，作为 attached_doc_ids 发送
      const attachedIds = composerAttachments
        .filter((a) => a.kind === "kb_doc" && a.docId)
        .map((a) => String(a.docId!).trim())
        .filter(Boolean);
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
          enabled_skills: enabledSkills.length ? enabledSkills : undefined,
          enabled_tools: enabledTools.length ? enabledTools : undefined,
          attached_doc_ids: attachedIds.length ? attachedIds : undefined,
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

  const openConfigEditor = useCallback(
    (kind: "skills" | "tools" | "workflows" | "prompts") => {
      const value =
        kind === "skills"
          ? skillConfigs
          : kind === "tools"
            ? toolConfigs
            : kind === "workflows"
              ? workflowConfigs
              : promptConfigs;
      setConfigModal({ kind, draftJson: JSON.stringify(value, null, 2) });
    },
    [skillConfigs, toolConfigs, workflowConfigs, promptConfigs]
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
      } else if (configModal.kind === "workflows") {
        const next = parsed as WorkflowConfig[];
        setWorkflowConfigs(next);
        localStorage.setItem(WORKFLOW_CONFIGS_LS_KEY, JSON.stringify(next));
      } else {
        const next = parsed as PromptConfig[];
        setPromptConfigs(next);
        localStorage.setItem(PROMPT_CONFIGS_LS_KEY, JSON.stringify(next));
      }
      setConfigModal(null);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "JSON 解析失败";
      setConfigModal((prev) => (prev ? { ...prev, error: msg } : prev));
    }
  }, [configModal]);

  useEffect(() => {
    // 载入可编辑配置（默认用内置列表；本地有则按 id 合并，保证新增内置条目仍出现）
    try {
      const rawSkills = localStorage.getItem(SKILL_CONFIGS_LS_KEY);
      const rawTools = localStorage.getItem(TOOL_CONFIGS_LS_KEY);
      const rawWfs = localStorage.getItem(WORKFLOW_CONFIGS_LS_KEY);
      const rawPrompts = localStorage.getItem(PROMPT_CONFIGS_LS_KEY);
      setSkillConfigs(mergeConfigById(ALL_SKILLS, rawSkills ? (JSON.parse(rawSkills) as SkillConfig[]) : null));
      setToolConfigs(mergeConfigById(ALL_TOOLS, rawTools ? (JSON.parse(rawTools) as ToolConfig[]) : null));
      let mergedWfs = mergeConfigById(ALL_WORKFLOWS, rawWfs ? (JSON.parse(rawWfs) as WorkflowConfig[]) : null);
      let wfsPatched = false;
      mergedWfs = mergedWfs.map((w) => {
        if (w.id !== WF_DATA_PARSE_EXCEL_ID) return w;
        const ids = [...(w.default_enabled_skill_ids ?? [])];
        if (!ids.includes("skill.data_parse.xlsx.v1")) {
          wfsPatched = true;
          return { ...w, default_enabled_skill_ids: [...ids, "skill.data_parse.xlsx.v1"] };
        }
        return w;
      });
      setWorkflowConfigs(mergedWfs);
      if (wfsPatched) {
        try {
          localStorage.setItem(WORKFLOW_CONFIGS_LS_KEY, JSON.stringify(mergedWfs));
        } catch {
          // ignore
        }
      }
      setPromptConfigs(mergeConfigById(ALL_PROMPTS, rawPrompts ? (JSON.parse(rawPrompts) as PromptConfig[]) : null));
    } catch {
      setSkillConfigs(ALL_SKILLS);
      setToolConfigs(ALL_TOOLS);
      setWorkflowConfigs(
        ALL_WORKFLOWS.map((w) => {
          if (w.id !== WF_DATA_PARSE_EXCEL_ID) return w;
          const ids = [...(w.default_enabled_skill_ids ?? [])];
          return ids.includes("skill.data_parse.xlsx.v1")
            ? w
            : { ...w, default_enabled_skill_ids: [...ids, "skill.data_parse.xlsx.v1"] };
        }),
      );
      setPromptConfigs(ALL_PROMPTS);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 进入页面/切回对话视图时自动聚焦输入框（光标闪烁，可直接输入）
  useEffect(() => {
    if (activeLeftView !== "chat") return;
    if (configModal) return;
    if (plusOpen || toolsOpen || skillsOpen || promptsOpen || workflowOpen) return;
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
  }, [activeLeftView, messages.length, configModal, plusOpen, toolsOpen, skillsOpen, promptsOpen, workflowOpen]);

  // 点击空白处关闭工具/skill/提示词/工作流 菜单
  useEffect(() => {
    if (!toolsOpen && !skillsOpen && !promptsOpen && !plusOpen && !workflowOpen) return;
    const onDown = (ev: MouseEvent) => {
      const t = ev.target as HTMLElement | null;
      const toolsBtn = toolsBtnRef.current;
      const skillsBtn = skillsBtnRef.current;
      const promptsBtn = promptsBtnRef.current;
      const plusBtn = plusBtnRef.current;
      const wfBtn = workflowBtnRef.current;
      if (toolsBtn && t && (toolsBtn === t || toolsBtn.contains(t))) return;
      if (skillsBtn && t && (skillsBtn === t || skillsBtn.contains(t))) return;
      if (promptsBtn && t && (promptsBtn === t || promptsBtn.contains(t))) return;
      if (wfBtn && t && (wfBtn === t || wfBtn.contains(t))) return;
      if (plusBtn && t && (plusBtn === t || plusBtn.contains(t))) return;
      const toolsPop = document.getElementById("ai-tools-popover");
      const skillsPop = document.getElementById("ai-skills-popover");
      const promptsPop = document.getElementById("ai-prompts-popover");
      const plusPop = document.getElementById("ai-plus-popover");
      const wfPop = document.getElementById("ai-workflow-popover");
      if (toolsPop && t && toolsPop.contains(t)) return;
      if (skillsPop && t && skillsPop.contains(t)) return;
      if (promptsPop && t && promptsPop.contains(t)) return;
      if (wfPop && t && wfPop.contains(t)) return;
      if (plusPop && t && plusPop.contains(t)) return;
      setToolsOpen(false);
      setSkillsOpen(false);
      setPromptsOpen(false);
      setWorkflowOpen(false);
      setPlusOpen(false);
    };
    window.addEventListener("mousedown", onDown, true);
    return () => window.removeEventListener("mousedown", onDown, true);
  }, [toolsOpen, skillsOpen, promptsOpen, plusOpen, workflowOpen]);

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

  // 会话胶囊：消息、附件（done/error）、工作流与数据解析会话 id → 本地历史持久化
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
        ...(a.kind ? { kind: a.kind } : {}),
        ...(a.dataParseSessionId ? { dataParseSessionId: a.dataParseSessionId } : {}),
      }));
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
      const next: ChatSession = {
        ...current,
        title,
        updated_at: Date.now(),
        messages,
        attachments: stable,
        data_parse_session_id: dataParseSessionId,
        active_workflow_id: activeWorkflowId,
        enabled_skills: [...enabledSkills],
        enabled_tools: [...enabledTools],
        enabled_prompt_ids: [...enabledPromptIds],
        start_area_hint: startAreaHint,
      };
      return [next, ...prev.filter((s) => s.id !== activeSessionId)].sort((a, b) => b.updated_at - a.updated_at);
    });
  }, [
    messages,
    composerAttachments,
    activeSessionId,
    dataParseSessionId,
    activeWorkflowId,
    enabledSkills,
    enabledTools,
    enabledPromptIds,
    startAreaHint,
  ]);

  const startNewChat = () => {
    const id = `s_${Date.now()}_${Math.random().toString(16).slice(2)}`;
    const s: ChatSession = { id, title: "新对话", updated_at: Date.now(), messages: [], attachments: [] };
    setActiveSessionId(id);
    setMessages([]);
    setComposerAttachments([]);
    excelParseSidRef.current = null;
    setUploadHint(null);
    setDataParseSessionId(null);
    setActiveWorkflowId(null);
    setEnabledSkills([]);
    setEnabledTools([]);
    setEnabledPromptIds([]);
    setStartAreaHint(null);
    setSelectedCollectionIds([]);
    setSelectedTableIds([]);
    setSelectedFolderIds([]);
    setSessions((prev) => [s, ...prev]);
  };

  const openSession = (id: string) => {
    const s = sessions.find((x) => x.id === id);
    if (!s) return;
    setActiveSessionId(id);
    setMessages(s.messages || []);
    const att = (s.attachments as ComposerAttachment[] | undefined) ?? [];
    setComposerAttachments(att);
    setUploadHint(null);
    setDataParseSessionId(activeExcelParseSessionId(att) ?? s.data_parse_session_id ?? null);
    excelParseSidRef.current = activeExcelParseSessionId(att) ?? (typeof s.data_parse_session_id === "string" ? s.data_parse_session_id : null) ?? null;
    setActiveWorkflowId(s.active_workflow_id ?? null);
    setEnabledSkills(Array.isArray(s.enabled_skills) ? [...s.enabled_skills] : []);
    setEnabledTools(Array.isArray(s.enabled_tools) ? [...s.enabled_tools] : []);
    setEnabledPromptIds(Array.isArray(s.enabled_prompt_ids) ? [...s.enabled_prompt_ids] : []);
    setStartAreaHint(s.start_area_hint ?? null);
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
        const attN = (next.attachments as ComposerAttachment[] | undefined) ?? [];
        setComposerAttachments(attN);
        setUploadHint(null);
        setDataParseSessionId(activeExcelParseSessionId(attN) ?? next.data_parse_session_id ?? null);
        excelParseSidRef.current =
          activeExcelParseSessionId(attN) ?? (typeof next.data_parse_session_id === "string" ? next.data_parse_session_id : null) ?? null;
        setActiveWorkflowId(next.active_workflow_id ?? null);
        setEnabledSkills(Array.isArray(next.enabled_skills) ? [...next.enabled_skills] : []);
        setEnabledTools(Array.isArray(next.enabled_tools) ? [...next.enabled_tools] : []);
        setEnabledPromptIds(Array.isArray(next.enabled_prompt_ids) ? [...next.enabled_prompt_ids] : []);
        setStartAreaHint(next.start_area_hint ?? null);
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

      const nameLow = (file.name || "").toLowerCase();
      const isExcel = nameLow.endsWith(".xlsx") || nameLow.endsWith(".xls");
      if (isExcel && activeWorkflowId === WF_DATA_PARSE_EXCEL_ID) {
        ensureActiveSession();
        const localId = `a_${Date.now()}_${Math.random().toString(16).slice(2)}`;
        setComposerAttachments((prev) => [
          ...prev,
          {
            localId,
            name: file.name,
            size: file.size,
            phase: "uploading",
            progress: 1,
            kind: "excel_parse",
          },
        ]);
        setUploadHint(null);
        const form = new FormData();
        form.append("file", file);
        try {
          const res = await fetch("/api/data-parse/upload", {
            method: "POST",
            body: form,
            credentials: "include",
            headers: getAuthHeaders(),
          });
          const data = (await res.json().catch(() => ({}))) as { detail?: string; session_id?: string; analysis?: string };
          if (!res.ok) {
            const msg = typeof data.detail === "string" ? data.detail : "电子表上传失败";
            setUploadHint(msg);
            setComposerAttachments((prev) =>
              prev.map((a) => (a.localId === localId ? { ...a, phase: "error" as const, error: msg, progress: 100 } : a))
            );
            return;
          }
          const sid = typeof data.session_id === "string" ? data.session_id : "";
          if (!sid) {
            setUploadHint("上传成功但未返回 session_id");
            setComposerAttachments((prev) =>
              prev.map((a) =>
                a.localId === localId ? { ...a, phase: "error" as const, error: "缺少 session_id", progress: 100 } : a
              )
            );
            return;
          }
          excelParseSidRef.current = sid;
          setDataParseSessionId(sid);
          setComposerAttachments((prev) =>
            prev.map((a) =>
              a.localId === localId
                ? { ...a, phase: "done" as const, progress: 100, dataParseSessionId: sid, kind: "excel_parse" as const }
                : a
            )
          );
          setUploadHint(`「${file.name}」已解析并激活，可在下方输入分析或画图需求（与知识库附件相同展示在输入区上方）。`);
          // 按规划：AI 互动上传文档默认保留在私人知识库。电子表解析链路这里做异步归档，不阻塞对话可用性。
          void (async () => {
            try {
              await uploadMyDocumentWithProgress(file, {
                folderId: undefined,
                onProgress: () => {},
              });
              await refreshKnowledgeOptions();
              setUploadHint((prev) => (prev ? `${prev} 文件已同步归档到私人知识库。` : "文件已同步归档到私人知识库。"));
            } catch {
              // 归档失败不影响数据解析会话
            }
          })();
        } catch (err) {
          const msg = err instanceof Error ? err.message : "电子表上传失败";
          setUploadHint(msg);
          setComposerAttachments((prev) =>
            prev.map((a) => (a.localId === localId ? { ...a, phase: "error" as const, error: msg, progress: 100 } : a))
          );
        }
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
            a.localId === localId
              ? { ...a, phase: "done" as const, progress: 100, docId: doc_id, kind: "kb_doc" as const }
              : a
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
    const waitingExcelUpload =
      activeWorkflowId === WF_DATA_PARSE_EXCEL_ID &&
      !composerAttachments.some((a) => a.kind === "excel_parse" && (a.phase === "uploading" || a.phase === "done"));
    const taPlaceholder = waitingExcelUpload
      ? "等待电子表：请用「+」→「上传文件」选择 .xlsx / .xls；上传成功后附件会显示在上方，再输入分析或画图需求。"
      : "有什么我能帮您的吗？";
    return (
      <div className="w-full">
        <div className={`${boxClass} mx-auto`}>
          <div className="relative flex flex-col">
            {waitingExcelUpload ? (
              <div className="mx-3 mt-3 rounded-lg border border-amber-900/50 bg-amber-950/25 px-3 py-2 text-xs text-amber-200/90">
                当前工作流：<span className="font-medium">电子表数据解析</span> — 处于<strong>等待上传</strong>
                状态。请使用下方「+」→「上传文件」选择电子表；上传完成后文件将固定在输入区上方（与知识库附件一致），即可提问、画图或要表格。
              </div>
            ) : null}
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
                    className={[
                      "flex min-w-[160px] max-w-[260px] flex-col gap-1.5 rounded-lg border px-2 py-1.5",
                      a.kind === "excel_parse" ? "border-emerald-900/50 bg-emerald-950/20" : "border-zinc-800 bg-zinc-900/45",
                    ].join(" ")}
                  >
                    <div className="flex items-start gap-2">
                      {a.kind === "excel_parse" ? (
                        <Table size={14} className="mt-0.5 shrink-0 text-emerald-400/90" aria-hidden />
                      ) : (
                        <FileText size={14} className="mt-0.5 shrink-0 text-zinc-400" aria-hidden />
                      )}
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-xs font-medium text-zinc-200" title={a.name}>
                          {a.name}
                        </div>
                        <div className="text-[11px] text-zinc-500">{formatBytes(a.size)}</div>
                        {a.kind === "excel_parse" && a.phase === "done" && a.dataParseSessionId ? (
                          <div className="mt-0.5 truncate font-mono text-[10px] text-zinc-500" title={a.dataParseSessionId}>
                            会话 {a.dataParseSessionId.slice(0, 10)}…
                          </div>
                        ) : null}
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
                        {a.kind === "excel_parse" ? "已应用 · 电子表解析" : "已上传"}
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
            placeholder={taPlaceholder}
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
                          <span className="text-xs text-zinc-500">
                            {activeWorkflowId === WF_DATA_PARSE_EXCEL_ID ? "PDF / Doc / Excel" : "PDF/Doc"}
                          </span>
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
                    setPromptsOpen(false);
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
                    setPromptsOpen(false);
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

              <div className="relative">
                <button
                  ref={promptsBtnRef}
                  type="button"
                  onClick={() => {
                    setPromptsOpen((v) => !v);
                    setToolsOpen(false);
                    setSkillsOpen(false);
                    setWorkflowOpen(false);
                  }}
                  className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-zinc-800 bg-zinc-950/40 text-zinc-200 hover:bg-zinc-900/60"
                  title="提示词（注入数据解析等）"
                >
                  <ScrollText size={16} />
                </button>
                {promptsOpen && (
                  <div
                    id="ai-prompts-popover"
                    className="absolute left-0 top-[calc(100%+10px)] z-20 w-[340px] rounded-xl border border-zinc-800 bg-zinc-950/95 p-3 shadow-[0_20px_60px_rgba(0,0,0,0.5)] backdrop-blur"
                  >
                    <div className="text-xs text-zinc-500 mb-2">提示词（勾选后随「电子表数据解析」请求拼接为 prompt_addon）</div>
                    <div className="max-h-64 space-y-2 overflow-y-auto">
                      {promptConfigs.map((p) => (
                        <label key={p.id} className="flex items-start gap-2 text-xs text-zinc-200">
                          <input
                            type="checkbox"
                            className="mt-0.5"
                            checked={enabledPromptIds.includes(p.id)}
                            onChange={() => toggleEnabledPrompt(p.id)}
                          />
                          <span className="min-w-0">
                            <span className="font-medium">{p.label}</span>
                            <span className="ml-1 text-zinc-500">{p.id}</span>
                            {p.summary ? <div className="mt-0.5 text-[11px] text-zinc-500">{p.summary}</div> : null}
                          </span>
                        </label>
                      ))}
                    </div>
                    <div className="mt-3 flex items-center justify-between">
                      <button
                        type="button"
                        onClick={() => openConfigEditor("prompts")}
                        className="rounded-lg border border-zinc-800 bg-zinc-950/40 px-3 py-1 text-xs text-zinc-200 hover:bg-zinc-900/60"
                      >
                        编辑配置
                      </button>
                      <button
                        type="button"
                        onClick={() => setPromptsOpen(false)}
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
                          编辑配置：
                          {configModal.kind === "skills"
                            ? "技能"
                            : configModal.kind === "tools"
                              ? "工具"
                              : configModal.kind === "workflows"
                                ? "工作流"
                                : "提示词"}
                        </div>
                        <div className="mt-1 text-xs text-zinc-500">
                          保存后影响本机展示与勾选；「电子表数据解析」工作流已接 /api/data-parse 上传与对话及 prompt_addon。
                        </div>
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
                    setPromptsOpen(false);
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
                            if (activeWorkflowId === wf.id) {
                              deactivateWorkflow();
                              return;
                            }
                            applyWorkflow(wf);
                          }}
                          className={[
                            "w-full rounded-lg border px-3 py-2 text-left text-xs hover:bg-zinc-900/60",
                            activeWorkflowId === wf.id ? "border-emerald-800/60 bg-emerald-950/25 text-emerald-100" : "border-zinc-800 bg-zinc-950/40 text-zinc-200",
                          ].join(" ")}
                        >
                          <div className="flex items-center justify-between gap-2">
                            <div className="font-medium">{wf.label}</div>
                            {activeWorkflowId === wf.id ? <Check size={14} strokeWidth={3} aria-hidden /> : null}
                          </div>
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
                    subtitle: (wf.start_hint || wf.description || "").trim(),
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
                      const full = workflowConfigs.find((w) => w.id === it.key);
                      if (full) {
                        if (activeWorkflowId === full.id) {
                          deactivateWorkflow();
                        } else {
                          applyWorkflow(full);
                        }
                        return;
                      }
                      setActiveWorkflowId(null);
                      setDataParseSessionId(null);
                      setEnabledPromptIds([]);
                      setEnabledTools([]);
                      if (it.key === "wf.project_accounting_table.quick") {
                        setEnabledSkills(["skill.project_accounting_table.v1"]);
                      } else {
                        setEnabledSkills([]);
                      }
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
                    ["pdf_packages", "大PDF文档包"],
                    ["prompts", "提示词"],
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
                      {m.role === "assistant" ? (
                        <div className="flex max-w-[85%] gap-3">
                          <div className="shrink-0 pt-1">
                            <AiAvatar status={chatLoading && idx === messages.length - 1 ? "thinking" : "idle"} />
                          </div>
                          <div
                            className="rounded-2xl px-4 py-2 text-sm leading-relaxed"
                            style={{ backgroundColor: "#27272a", color: "#e4e4e7" }}
                          >
                            {m.content ? (
                              m.content
                            ) : chatLoading && idx === messages.length - 1 ? (
                              <TypingIndicator />
                            ) : null}
                            {m.chart_spec && Object.keys(m.chart_spec).length > 0 && (
                              <div className="mt-2">
                                <AiInlineChart spec={m.chart_spec} />
                                <details className="mt-1 cursor-pointer">
                                  <summary className="text-xs text-zinc-200/70 hover:text-zinc-100">查看 chart_spec 原始数据</summary>
                                  <pre className="mt-1 max-h-36 overflow-auto whitespace-pre-wrap text-[11px] text-zinc-200/80">
                                    {JSON.stringify(m.chart_spec, null, 2)}
                                  </pre>
                                </details>
                              </div>
                            )}
                            {m.table_spec && m.table_spec.columns?.length ? (
                              <div className="mt-2">
                                <AiInlineTable spec={m.table_spec} />
                                <details className="mt-1 cursor-pointer">
                                  <summary className="text-xs text-zinc-200/70 hover:text-zinc-100">查看 table_spec 原始数据</summary>
                                  <pre className="mt-1 max-h-36 overflow-auto whitespace-pre-wrap text-[11px] text-zinc-200/80">
                                    {JSON.stringify(m.table_spec, null, 2)}
                                  </pre>
                                </details>
                              </div>
                            ) : null}
                            {m.citations && m.citations.length > 0 && (
                              <div className="mt-2">
                                <details className="cursor-pointer">
                                  <summary className="text-xs text-zinc-200/80 hover:text-zinc-100">citations（{m.citations.length}）</summary>
                                  <pre className="mt-2 whitespace-pre-wrap text-xs text-zinc-200/80">{JSON.stringify(m.citations, null, 2)}</pre>
                                </details>
                              </div>
                            )}
                          </div>
                        </div>
                      ) : (
                        <div
                          className="max-w-[85%] rounded-2xl px-4 py-2 text-sm leading-relaxed"
                          style={{ backgroundColor: "#3b82f6", color: "#e4e4e7" }}
                        >
                          {m.content}
                        </div>
                      )}
                    </div>
                  ))}
                  {/* AI 正在思考/输入时的占位消息（还没有 assistant 消息时） */}
                  {chatLoading && messages.length > 0 && messages[messages.length - 1].role === "user" && (
                    <div className="flex justify-start">
                      <div className="flex max-w-[85%] gap-3">
                        <div className="shrink-0 pt-1">
                          <AiAvatar status="thinking" />
                        </div>
                        <div
                          className="rounded-2xl px-4 py-2 text-sm leading-relaxed"
                          style={{ backgroundColor: "#27272a", color: "#e4e4e7" }}
                        >
                          <TypingIndicator />
                        </div>
                      </div>
                    </div>
                  )}
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
                          subtitle: (wf.start_hint || wf.description || "").trim(),
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
                            const full = workflowConfigs.find((w) => w.id === it.key);
                            if (full) {
                              applyWorkflow(full);
                              return;
                            }
                            setActiveWorkflowId(null);
                            setDataParseSessionId(null);
                            setEnabledPromptIds([]);
                            setEnabledTools([]);
                            if (it.key === "wf.project_accounting_table.quick") {
                              setEnabledSkills(["skill.project_accounting_table.v1"]);
                            } else {
                              setEnabledSkills([]);
                            }
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
                  <KnowledgeWorkspacePanel />
                </div>
              </div>
            ) : workspaceTab === "pdf_packages" ? (
              <div className="rounded-xl border border-zinc-900 bg-zinc-950/40 p-4">
                <PdfPackagesPanel
                  items={ragItems}
                  busyPackageId={ragBusyId}
                  onDownload={downloadRagExport}
                  onDelete={deleteRagPackage}
                />
              </div>
            ) : workspaceTab === "prompts" ? (
              <div className="rounded-xl border border-zinc-900 bg-zinc-950/40 p-4">
                <div className="flex items-center justify-between">
                  <div className="text-sm font-medium text-zinc-200">提示词（全站）</div>
                  <button
                    type="button"
                    onClick={() => openConfigEditor("prompts")}
                    className="rounded-lg border border-zinc-800 bg-zinc-950/40 px-3 py-1 text-xs text-zinc-200 hover:bg-zinc-900/60"
                  >
                    编辑 JSON
                  </button>
                </div>
                <p className="mt-2 text-xs text-zinc-500">
                  术语与分层见仓库 <span className="font-mono text-zinc-400">docs/agent-skills-glossary.md</span>
                  ：此处登记<strong>全站可复用</strong>的 Prompt 设计（摘要 + 可选正文）；成熟 prompt/口径素材可写入{" "}
                  <span className="font-mono text-zinc-400">body</span> 或拆条。Agent Skill 正文见「技能」Tab 中的仓库{" "}
                  <span className="font-mono text-zinc-400">SKILL.md</span>。
                </p>
                <div className="mt-3 space-y-2">
                  {promptConfigs.map((p) => (
                    <div key={p.id} className="rounded-lg border border-zinc-800 bg-zinc-950/20 p-3">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="text-sm font-medium text-zinc-200">{p.label}</div>
                          <div className="mt-1 text-xs text-zinc-500 font-mono">{p.id}</div>
                        </div>
                        <div className="flex shrink-0 flex-wrap gap-2 text-[11px] text-zinc-500">
                          {p.role ? (
                            <span className="rounded border border-zinc-800 px-1.5 py-0.5 font-mono">{p.role}</span>
                          ) : null}
                          {p.scope ? (
                            <span className="rounded border border-zinc-800 px-1.5 py-0.5 font-mono">{p.scope}</span>
                          ) : null}
                        </div>
                      </div>
                      {p.description ? <div className="mt-2 text-xs text-zinc-400">{p.description}</div> : null}
                      {p.summary ? <div className="mt-2 text-[11px] text-zinc-500">摘要：{p.summary}</div> : null}
                      {p.body && p.body.trim() ? (
                        <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap rounded border border-zinc-900 bg-zinc-950/40 p-2 text-[11px] text-zinc-300">
                          {p.body}
                        </pre>
                      ) : (
                        <div className="mt-2 text-[11px] text-zinc-600">（正文可在「编辑 JSON」中填写 body 字段）</div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ) : workspaceTab === "skills" ? (
              <div className="rounded-xl border border-zinc-900 bg-zinc-950/40 p-4">
                <div className="flex items-center justify-between">
                  <div className="text-sm font-medium text-zinc-200">技能（SKILL.md）</div>
                  <button
                    type="button"
                    onClick={() => openConfigEditor("skills")}
                    className="rounded-lg border border-zinc-800 bg-zinc-950/40 px-3 py-1 text-xs text-zinc-200 hover:bg-zinc-900/60"
                  >
                    编辑 JSON
                  </button>
                </div>
                <p className="mt-2 text-xs text-zinc-500">
                  正文来自后端{" "}
                  <span className="font-mono text-zinc-400">backend/data/agent_skills/&lt;skill_id&gt;/SKILL.md</span>（
                  <span className="font-mono text-zinc-400">manifest.json</span> 登记）。勾选「启用」后，对应文档会注入当前对话的 system，模型须按文档约束执行。
                </p>
                {skillCatalogLoading ? (
                  <div className="mt-3 text-xs text-zinc-500">正在加载 SKILL.md…</div>
                ) : skillCatalogError ? (
                  <div className="mt-3 text-xs text-amber-400">{skillCatalogError}</div>
                ) : null}
                <div className="mt-3 space-y-2">
                  {skillConfigs.map((s) => {
                    const doc = skillCatalog?.find((d) => d.id === s.id);
                    return (
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
                        {doc?.name && doc.name !== s.id ? (
                          <div className="mt-1 text-[11px] text-zinc-500">SKILL 名：{doc.name}</div>
                        ) : null}
                        {doc?.description ? <div className="mt-1 text-[11px] text-zinc-500">{doc.description}</div> : null}
                        {s.description ? <div className="mt-2 text-xs text-zinc-400">{s.description}</div> : null}
                        {s.trigger_hint ? <div className="mt-1 text-[11px] text-zinc-500">触发：{s.trigger_hint}</div> : null}
                        {s.example ? <div className="mt-2 rounded border border-zinc-900 bg-zinc-950/40 p-2 text-[11px] text-zinc-300">{s.example}</div> : null}
                        <details className="mt-2 rounded border border-zinc-900 bg-zinc-950/40">
                          <summary className="cursor-pointer select-none px-2 py-1.5 text-[11px] text-zinc-400 hover:text-zinc-300">
                            查看 SKILL.md 全文
                          </summary>
                          {doc?.raw_markdown ? (
                            <pre className="max-h-[min(70vh,520px)] overflow-auto whitespace-pre-wrap border-t border-zinc-900 p-2 text-[11px] leading-relaxed text-zinc-300">
                              {doc.raw_markdown}
                            </pre>
                          ) : (
                            <div className="border-t border-zinc-900 px-2 py-2 text-[11px] text-zinc-600">
                              未找到该技能的 SKILL.md（请检查后端 manifest 与文件路径）。
                            </div>
                          )}
                        </details>
                      </div>
                    );
                  })}
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
            ) : workspaceTab === "workflows" ? (
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
            ) : null}
          </div>
        )}
      </main>
    </div>
  );
}
