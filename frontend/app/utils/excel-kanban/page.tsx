"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Bar,
  BarChart,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

type KanbanChart = { id: string; title: string; option: { xAxis?: { data?: string[] }; series?: { name: string; type: string; data: number[] }[] } };
type TableSchema = { sheet_name: string; headers: string[]; row_count: number };
type TablePreview = { headers: string[]; rows: string[][] };
type UploadResponse = {
  session_id: string;
  table_schemas?: TableSchema[];
  tables_preview?: Record<string, TablePreview>;
  kanban_config: KanbanChart[];
  analysis: string;
};
type ChatMessage = { role: "user" | "assistant"; content: string; chart_spec?: unknown; table_spec?: { columns: string[]; rows: unknown[][] } };
type ChatResponse = { reply: string; chart_spec?: unknown; table_spec?: { columns: string[]; rows: unknown[][] } };
type PromptSummary = { system_summary: string; user_summary: string };
type ToolsList = { tools: { name: string; description: string; constraint: string }[] };
type SkillsList = Record<string, { count: number; summary: string }>;

const LAST_SESSION_KEY = "orientg_data_parse_last_session";

/** 将后端图表配置（与 Recharts 兼容）转为 Recharts 所需 data */
function optionToRechartsData(option: KanbanChart["option"]) {
  const labels = option?.xAxis?.data ?? [];
  const series = option?.series ?? [];
  return labels.map((name, i) => {
    const row: Record<string, string | number> = { name };
    series.forEach((s) => {
      row[s.name] = s.data?.[i] ?? 0;
    });
    return row;
  });
}

function KanbanChartBlock({ chart }: { chart: KanbanChart }) {
  const data = optionToRechartsData(chart.option);
  const series = chart.option?.series ?? [];
  if (!data.length || !series.length) return null;
  const isLine = series.every((s) => s.type === "line");
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
      <h3 className="mb-3 text-sm font-medium text-zinc-300">{chart.title}</h3>
      <ResponsiveContainer width="100%" height={260}>
        {isLine ? (
          <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <XAxis dataKey="name" tick={{ fontSize: 12 }} stroke="#71717a" />
            <YAxis tick={{ fontSize: 12 }} stroke="#71717a" />
            <Tooltip contentStyle={{ backgroundColor: "#18181b", border: "1px solid #3f3f46" }} />
            <Legend />
            {series.map((s, idx) => (
              <Line
                key={`${s.name || "series"}-${idx}`}
                type="monotone"
                dataKey={s.name}
                stroke={s.name === "本年" ? "#2563eb" : "#71717a"}
                strokeWidth={2}
                dot={{ r: 3 }}
              />
            ))}
          </LineChart>
        ) : (
          <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <XAxis dataKey="name" tick={{ fontSize: 12 }} stroke="#71717a" />
            <YAxis tick={{ fontSize: 12 }} stroke="#71717a" />
            <Tooltip contentStyle={{ backgroundColor: "#18181b", border: "1px solid #3f3f46" }} />
            <Legend />
            {series.map((s, i) => (
              <Bar
                key={`${s.name || "series"}-${i}`}
                dataKey={s.name}
                fill={i === 0 ? "#22c55e" : "#52525b"}
                radius={[4, 4, 0, 0]}
              />
            ))}
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}

/** 内嵌图表（对话返回的 chart_spec 与 Recharts 兼容） */
function InlineChart({ spec }: { spec: unknown }) {
  const opt = spec as { xAxis?: { data?: string[] }; series?: { name: string; type: string; data: number[] }[] };
  const data = optionToRechartsData(opt);
  const series = opt?.series ?? [];
  if (!data.length || !series.length) return null;
  const isLine = series.every((s) => s.type === "line");
  return (
    <div className="my-2 rounded border border-zinc-700 bg-zinc-900/60 p-3">
      <ResponsiveContainer width="100%" height={200}>
        {isLine ? (
          <LineChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
            <XAxis dataKey="name" tick={{ fontSize: 11 }} stroke="#71717a" />
            <YAxis tick={{ fontSize: 11 }} stroke="#71717a" />
            <Tooltip contentStyle={{ backgroundColor: "#18181b", border: "1px solid #3f3f46" }} />
            {series.map((s, idx) => (
              <Line
                key={`${s.name || "series"}-${idx}`}
                type="monotone"
                dataKey={s.name}
                stroke="#2563eb"
                strokeWidth={2}
                dot={{ r: 2 }}
              />
            ))}
          </LineChart>
        ) : (
          <BarChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
            <XAxis dataKey="name" tick={{ fontSize: 11 }} stroke="#71717a" />
            <YAxis tick={{ fontSize: 11 }} stroke="#71717a" />
            <Tooltip contentStyle={{ backgroundColor: "#18181b", border: "1px solid #3f3f46" }} />
            {series.map((s, i) => (
              <Bar
                key={`${s.name || "series"}-${i}`}
                dataKey={s.name}
                fill={i === 0 ? "#22c55e" : "#52525b"}
                radius={[4, 4, 0, 0]}
              />
            ))}
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}

function InlineTable({ spec }: { spec: { columns: string[]; rows: unknown[][] } }) {
  const { columns, rows } = spec;
  return (
    <div className="my-2 overflow-x-auto rounded border border-zinc-700">
      <table className="w-full min-w-[200px] text-left text-sm">
        <thead>
          <tr className="border-b border-zinc-700 bg-zinc-800/80">
            {columns.map((c, idx) => {
              const key = c === "" ? `col-${idx}` : `${c}-${idx}`;
              return (
                <th key={key} className="px-3 py-2 font-medium text-zinc-300">
                  {c || `列${idx + 1}`}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b border-zinc-800">
              {columns.map((col, j) => (
                <td key={j} className="px-3 py-2 text-zinc-400">
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

export default function ExcelKanbanPage() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  // These are hydrated from session restore / uploads and used for future UI iteration.
  // Keep as setters-only for now to avoid unused vars warnings.
  const [, setTableSchemas] = useState<TableSchema[]>([]);
  const [, setTablesPreview] = useState<Record<string, TablePreview>>({});
  const [kanbanConfig, setKanbanConfig] = useState<KanbanChart[]>([]);
  const [analysis, setAnalysis] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [ollamaConfigured, setOllamaConfigured] = useState(false);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [promptSummary, setPromptSummary] = useState<PromptSummary | null>(null);
  const [toolsList, setToolsList] = useState<ToolsList | null>(null);
  const [skillsList, setSkillsList] = useState<SkillsList | null>(null);
  const [showListings, setShowListings] = useState(false);
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    fetch("/api/data-parse/status", { credentials: "include" })
      .then((r) => (r.ok ? r.json() : {}))
      .then((data: { ollama_configured?: boolean }) => setOllamaConfigured(!!data.ollama_configured))
      .catch(() => {});
  }, []);

  const restoreSession = useCallback(async (id: string) => {
    try {
      const res = await fetch(`/api/data-parse/session/${encodeURIComponent(id)}`, {
        credentials: "include",
      });
      if (!res.ok) {
        // 会话失效时清理本地记录
        if (typeof window !== "undefined") {
          window.localStorage.removeItem(LAST_SESSION_KEY);
        }
        return false;
      }
      const data = (await res.json()) as {
        table_schemas?: TableSchema[];
        tables_preview?: Record<string, TablePreview>;
        kanban_config?: KanbanChart[];
      };
      setSessionId(id);
      setTableSchemas(data.table_schemas ?? []);
      setTablesPreview(data.tables_preview ?? {});
      setKanbanConfig(data.kanban_config ?? []);
      setAnalysis("");
      setChatMessages([]);
      return true;
    } catch {
      return false;
    }
  }, []);

  // 初次进入时：优先用 URL 中的 session_id，其次用 localStorage 中最近一次会话
  useEffect(() => {
    const urlId = searchParams.get("session_id");
    if (urlId) {
      restoreSession(urlId);
      if (typeof window !== "undefined") {
        window.localStorage.setItem(LAST_SESSION_KEY, urlId);
      }
      return;
    }
    if (typeof window === "undefined") return;
    const last = window.localStorage.getItem(LAST_SESSION_KEY);
    if (last) {
      restoreSession(last);
    }
  }, [restoreSession, searchParams]);

  const fetchListings = useCallback(() => {
    Promise.all([
      fetch("/api/data-parse/prompt-summary", { credentials: "include" }).then((r) => (r.ok ? r.json() : null)),
      fetch("/api/data-parse/tools", { credentials: "include" }).then((r) => (r.ok ? r.json() : null)),
      fetch("/api/data-parse/skills", { credentials: "include" }).then((r) => (r.ok ? r.json() : null)),
    ]).then(([p, t, s]) => {
      setPromptSummary(p as PromptSummary);
      setToolsList(t as ToolsList);
      setSkillsList(s as SkillsList);
    });
  }, []);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadError(null);
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch("/api/data-parse/upload", { method: "POST", body: form, credentials: "include" });
      const data = (await res.json()) as UploadResponse | { detail?: string };
      if (!res.ok) {
        setUploadError("detail" in data ? String(data.detail) : "上传失败");
        return;
      }
      const up = data as UploadResponse;
      setSessionId(up.session_id);
      setTableSchemas(up.table_schemas ?? []);
      setTablesPreview(up.tables_preview ?? {});
      setKanbanConfig(up.kanban_config ?? []);
      setAnalysis(up.analysis ?? "");
      setChatMessages([]);
      // URL 携带当前会话 ID，便于返回后恢复
      router.replace(`/utils/excel-kanban?session_id=${encodeURIComponent(up.session_id)}`);
      if (typeof window !== "undefined") {
        window.localStorage.setItem(LAST_SESSION_KEY, up.session_id);
      }
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "上传失败");
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  };

  const handleChat = async () => {
    const msg = chatInput.trim();
    if (!msg || !sessionId || chatLoading) return;
    if (!ollamaConfigured) {
      setChatMessages((prev) => [...prev, { role: "user", content: msg }, { role: "assistant", content: "需配置 Ollama 后可用对话与按需生图/生表功能。请在 .env 中设置 OLLAMA_URL。" }]);
      setChatInput("");
      return;
    }
    setChatMessages((prev) => [...prev, { role: "user", content: msg }]);
    setChatInput("");
    setChatLoading(true);
    try {
      const res = await fetch("/api/data-parse/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, message: msg }),
        credentials: "include",
      });
      const data = (await res.json()) as ChatResponse | { detail?: string };
      if (!res.ok) {
        setChatMessages((prev) => [...prev, { role: "assistant", content: "detail" in data ? String(data.detail) : "请求失败" }]);
        return;
      }
      const cr = data as ChatResponse;
      setChatMessages((prev) => [...prev, { role: "assistant", content: cr.reply, chart_spec: cr.chart_spec, table_spec: cr.table_spec }]);
      if (cr.chart_spec && typeof cr.chart_spec === "object" && "xAxis" in cr.chart_spec && "series" in cr.chart_spec) {
        setKanbanConfig((prev) => [...prev, { id: `chat-${Date.now()}`, title: "按需生成", option: cr.chart_spec as KanbanChart["option"] }]);
      }
    } catch (err) {
      setChatMessages((prev) => [...prev, { role: "assistant", content: err instanceof Error ? err.message : "请求失败" }]);
    } finally {
      setChatLoading(false);
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
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-100">数据解析</h1>
        <p className="mt-1 text-sm text-zinc-500">上传 Excel 生成看板与解读，并支持自然语言问答、按需生图/生表。</p>
      </div>

      {/* 上传 */}
      <div className="mb-6 rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
        <label className="mb-2 block text-sm font-medium text-zinc-400">上传表格</label>
        <input
          type="file"
          accept=".xlsx,.xls"
          onChange={handleUpload}
          disabled={uploading}
          className="block w-full max-w-xs text-sm text-zinc-400 file:mr-3 file:rounded file:border-0 file:bg-zinc-700 file:px-3 file:py-1.5 file:text-zinc-200"
        />
        {uploading && <p className="mt-2 text-sm text-zinc-500">解析中…</p>}
        {uploadError && <p className="mt-2 text-sm text-red-400">{uploadError}</p>}
        {!ollamaConfigured && <p className="mt-2 text-xs text-zinc-500">未配置 Ollama 时仅展示看板，对话与解读需配置 OLLAMA_URL。</p>}
      </div>

      {sessionId && (
        <>
          {/* 自动看板（上传后基于聚合自动生成的图表 + 对话按需生成的图表） */}
          <section className="mb-8">
            <h2 className="mb-2 text-lg font-medium text-zinc-200">自动看板</h2>
            <p className="mb-3 text-sm text-zinc-500">
              根据表结构与聚合结果自动推荐的一组图表，对话中按需生成的图表也会追加到这里。
            </p>
            {kanbanConfig.length > 0 ? (
              <div className="grid gap-6 md:grid-cols-2">
                {kanbanConfig.map((c, idx) => (
                  <KanbanChartBlock key={`${c.id}-${idx}`} chart={c} />
                ))}
              </div>
            ) : (
              <p className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 text-sm text-zinc-500">
                暂无图表。可通过下方对话按需生图，例如：「用第一列做 X 轴、第二列做 Y 轴画柱状图」或「画一个按月份的趋势图」。
              </p>
            )}
          </section>

          {/* 解读 */}
          {analysis && (
            <section className="mb-8">
              <h2 className="mb-2 text-lg font-medium text-zinc-200">分析</h2>
              <p className="mb-3 text-sm text-zinc-500">
                基于表结构与聚合结果的自动分析，仅描述结构与趋势，不包含具体数值。
              </p>
              <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
                <pre className="whitespace-pre-wrap text-sm text-zinc-300">{analysis}</pre>
              </div>
            </section>
          )}

          {/* 对话 */}
          <section className="mb-8">
            <h2 className="mb-4 text-lg font-medium text-zinc-200">问答与按需生图/生表</h2>
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
              <div className="mb-4 max-h-[320px] space-y-3 overflow-y-auto">
                {chatMessages.length === 0 && <p className="text-sm text-zinc-500">在此对当前表格提问或要求生成图表、表格。</p>}
                {chatMessages.map((m, i) => (
                  <div key={i} className={m.role === "user" ? "text-right" : "text-left"}>
                    <span className="inline-block rounded-lg px-3 py-2 text-sm " style={{ backgroundColor: m.role === "user" ? "#3b82f6" : "#27272a", color: "#e4e4e7" }}>
                      {m.content}
                    </span>
                    {m.role === "assistant" && m.chart_spec !== undefined && <InlineChart spec={m.chart_spec} />}
                    {m.role === "assistant" && m.table_spec !== undefined && <InlineTable spec={m.table_spec} />}
                  </div>
                ))}
              </div>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleChat()}
                  placeholder="输入问题或要求，如：画一个利润趋势图"
                  className="flex-1 rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-500"
                />
                <button
                  type="button"
                  onClick={handleChat}
                  disabled={chatLoading || !chatInput.trim()}
                  className="rounded bg-zinc-600 px-4 py-2 text-sm font-medium text-zinc-200 hover:bg-zinc-500 disabled:opacity-50"
                >
                  {chatLoading ? "发送中…" : "发送"}
                </button>
              </div>
            </div>
          </section>
        </>
      )}

      {/* 列示：Prompt / 工具 / Skills */}
      <section className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
        <button
          type="button"
          onClick={() => {
            setShowListings((v) => !v);
            if (!showListings) fetchListings();
          }}
          className="flex w-full items-center justify-between text-left text-sm font-medium text-zinc-400 hover:text-zinc-300"
        >
          <span>使用的 Prompt / 工具 / Skills（列示）</span>
          <span>{showListings ? "收起" : "展开"}</span>
        </button>
        {showListings && (
          <div className="mt-4 space-y-4 border-t border-zinc-800 pt-4 text-sm text-zinc-500">
            {promptSummary && (
              <div>
                <h4 className="mb-1 font-medium text-zinc-400">Prompt 摘要</h4>
                <p>{promptSummary.system_summary}</p>
                <p className="mt-1">{promptSummary.user_summary}</p>
              </div>
            )}
            {toolsList?.tools?.length && (
              <div>
                <h4 className="mb-1 font-medium text-zinc-400">工具（MCP 风格）</h4>
                <ul className="list-inside list-disc space-y-0.5">
                  {toolsList.tools.map((t) => (
                    <li key={t.name}>
                      <strong>{t.name}</strong>：{t.description}（{t.constraint}）
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {skillsList && Object.keys(skillsList).length > 0 && (
              <div>
                <h4 className="mb-1 font-medium text-zinc-400">Skills</h4>
                <ul className="space-y-0.5">
                  {Object.entries(skillsList).map(([k, v]) => (
                    <li key={k}>
                      {v.summary}（条数：{v.count}）
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
