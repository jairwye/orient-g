"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getAuthHeaders } from "../lib/auth";

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

type Citation = Record<string, any>;

type KnowledgeOptionsResponse = {
  collections: KnowledgeCollection[];
  tables: KnowledgeTable[];
  default_selected_collection_ids: string[];
  default_selected_table_ids: string[];
};

type AskResponse = {
  denied?: boolean;
  deny_reason?: string;
  // 当后端以 HTTPException 返回 403 时，Next/TS 侧可能拿到 `detail` 字段
  detail?: string;
  reply?: string;
  citations?: Citation[];
};

const BIG_PDF_SIZE_MB = 15;
const BIG_PDF_PAGES = 60;

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
  const [loading, setLoading] = useState(true);
  const [options, setOptions] = useState<KnowledgeOptionsResponse | null>(null);
  const [selectedCollectionIds, setSelectedCollectionIds] = useState<string[]>([]);
  const [selectedTableIds, setSelectedTableIds] = useState<string[]>([]);

  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [messages, setMessages] = useState<
    Array<{ role: "user" | "assistant"; content: string; citations?: Citation[]; deny_reason?: string }>
  >([]);
  const [uploadHint, setUploadHint] = useState<string | null>(null);
  const [uploadBusy, setUploadBusy] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const refreshKnowledgeOptions = useCallback(async () => {
    const res = await fetch("/api/knowledge/options", { credentials: "include", headers: getAuthHeaders() });
    if (!res.ok) return;
    const data = (await res.json()) as KnowledgeOptionsResponse;
    setOptions(data);
    setSelectedCollectionIds((prev) => {
      const s = new Set(prev);
      for (const id of data.default_selected_collection_ids ?? []) s.add(id);
      return Array.from(s);
    });
    setSelectedTableIds((prev) => {
      const s = new Set(prev);
      for (const id of data.default_selected_table_ids ?? []) s.add(id);
      return Array.from(s);
    });
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
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
    setMessages((prev) => [...prev, { role: "user", content: q }]);
    try {
      const res = await fetch("/api/knowledge/ask", {
        method: "POST",
        headers: { ...getAuthHeaders(), "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          query: q,
          selected_collection_ids: selectedCollectionIds.length ? selectedCollectionIds : undefined,
          selected_table_ids: selectedTableIds.length ? selectedTableIds : undefined,
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
        const data = await res.json().catch(() => ({} as any));
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
        window.location.href = `/utils/pdf-knowledge?${q.toString()}`;
        return;
      }

      const fd = new FormData();
      fd.append("file", file);
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
      setUploadHint(`已上传「${file.name}」，默认进入私人知识库；可在知识库页管理。`);
      await refreshKnowledgeOptions();
    } catch (err) {
      setUploadHint(err instanceof Error ? err.message : "上传失败");
    } finally {
      setUploadBusy(false);
    }
  };

  return (
    <div className="p-6 md:p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-100">AI 互动</h1>
        <p className="mt-1 text-sm text-zinc-500">可选择知识库加载范围后发起自然语言提问。上传文件默认进入您的私人知识库。</p>
      </div>

      <div className="flex gap-4">
        {/* 左侧：知识库加载 */}
        <aside className="w-80 shrink-0 rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <h2 className="mb-3 text-sm font-medium text-zinc-200">知识库加载</h2>
          {loading ? (
            <p className="text-sm text-zinc-500">加载知识库选项…</p>
          ) : (
            <>
              <div className="mb-4">
                <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-zinc-500">Collections</h3>
                <div className="space-y-3">
                  {groupedCollections.map(([spaceType, items]) => (
                    <div key={spaceType}>
                      <div className="mb-1 text-xs text-zinc-400">{spaceType}</div>
                      <div className="space-y-1">
                        {items.map((c) => (
                          <label key={c.collection_id} className="flex items-center gap-2 text-sm text-zinc-300">
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
                <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-zinc-500">Tables</h3>
                <div className="space-y-3">
                  {groupedTables.map(([spaceType, items]) => (
                    <div key={spaceType}>
                      <div className="mb-1 text-xs text-zinc-400">{spaceType}</div>
                      <div className="space-y-1">
                        {items.map((t) => (
                          <label key={t.table_id} className="flex items-center gap-2 text-sm text-zinc-300">
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
            </>
          )}
        </aside>

        {/* 主区：聊天 */}
        <main className="flex-1 rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="mb-3">
            <div className="text-sm text-zinc-400">对话</div>
          </div>

          <div className="mb-4 max-h-[520px] overflow-y-auto space-y-3 pr-2">
            {messages.length === 0 ? (
              <p className="text-sm text-zinc-500">选择知识库后提问，例如：财务审核 T+2 是什么？或询问某张表的“本年累计净利润是多少”。</p>
            ) : (
              messages.map((m, idx) => (
                <div key={idx} className={m.role === "user" ? "text-right" : "text-left"}>
                  <div
                    className="inline-block max-w-[85%] rounded-lg px-3 py-2 text-sm"
                    style={{
                      backgroundColor: m.role === "user" ? "#3b82f6" : "#27272a",
                      color: "#e4e4e7",
                    }}
                  >
                    {m.content}
                  </div>
                  {m.role === "assistant" && m.citations && m.citations.length > 0 && (
                    <div className="mt-2">
                      <details className="cursor-pointer">
                        <summary className="text-xs text-zinc-400 hover:text-zinc-200">citations（{m.citations.length}）</summary>
                        <pre className="mt-2 whitespace-pre-wrap text-xs text-zinc-300">{JSON.stringify(m.citations, null, 2)}</pre>
                      </details>
                    </div>
                  )}
                </div>
              ))
            )}
          </div>

          <input ref={fileInputRef} type="file" className="hidden" onChange={handleUploadFile} />

          <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-zinc-500">
            <button
              type="button"
              disabled={uploadBusy}
              onClick={() => fileInputRef.current?.click()}
              className="rounded border border-zinc-600 bg-zinc-800 px-2 py-1 text-zinc-300 hover:bg-zinc-700 disabled:opacity-50"
            >
              {uploadBusy ? "上传中…" : "上传文档"}
            </button>
            {uploadHint && <span className={uploadHint.includes("失败") ? "text-red-400" : "text-emerald-400"}>{uploadHint}</span>}
          </div>

          <div className="flex gap-2 items-center">
            <input
              type="text"
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleAsk()}
              placeholder="输入问题，例如：财务审核 T+2 是什么？或：项目核算本年累计净利润是多少？"
              className="flex-1 rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-500"
            />
            <button
              type="button"
              onClick={handleAsk}
              disabled={chatLoading || !chatInput.trim()}
              className="rounded bg-zinc-600 px-4 py-2 text-sm font-medium text-zinc-200 hover:bg-zinc-500 disabled:opacity-50"
            >
              {chatLoading ? "发送中…" : "发送"}
            </button>
          </div>
        </main>
      </div>
    </div>
  );
}
