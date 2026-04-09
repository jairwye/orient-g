"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import mermaid from "mermaid";

type ProcessTypeRule = {
  id: string;
  name?: string | null;
  description?: string | null;
  output_schema?: unknown;
  prompt_instruction?: string | null;
  natural_language_rule?: string | null;
};

type RulesPayload = {
  schema_version?: string | null;
  process_types: ProcessTypeRule[];
};

function ruleToSummary(pt: ProcessTypeRule): string {
  const name = pt.name || pt.id;
  const desc = pt.description || "";
  const schema = pt.output_schema as { title?: string; steps?: unknown[]; roles?: string[] } | undefined;
  let schemaDesc = "";
  if (schema) {
    const parts: string[] = [];
    if (schema.title) parts.push("流程名称");
    if (Array.isArray(schema.steps) && schema.steps.length > 0) {
      const first = schema.steps[0] as Record<string, string>;
      const fields = first ? Object.keys(first).filter((k) => k !== "step_no").join("、") : "步骤描述";
      parts.push(`步骤列表（每步包含：${fields}）`);
    }
    if (schema.roles && schema.roles.length) parts.push("角色列表");
    if (parts.length) schemaDesc = "输出包含：" + parts.join("；") + "。";
  }
  return `本规则（${name}）要求：${desc || "按结构化流程输出"}。${schemaDesc}`.trim();
}

function ruleToMermaid(pt: ProcessTypeRule): string {
  const schema = pt.output_schema as { steps?: Array<Record<string, string>> } | undefined;
  const steps = Array.isArray(schema?.steps) ? schema.steps : [];
  const stepLabels: string[] = [];
  if (steps.length === 0) {
    stepLabels.push("步骤: 描述、角色、输入、输出、时限");
  } else {
    const first = steps[0];
    const fields = first ? Object.keys(first).filter((k) => k !== "step_no").join("、") : "描述";
    const n = Math.max(3, steps.length);
    for (let i = 0; i < n; i++) {
      stepLabels.push(`步骤${i + 1}: ${fields}`);
    }
  }
  const safe = (s: string) => s.replace(/\[|\]|\(|\)/g, " ");
  const lines = ["flowchart TD", `  Start[开始] --> S1[${safe(stepLabels[0])}]`];
  for (let i = 0; i < stepLabels.length - 1; i++) {
    lines.push(`  S${i + 1}[${safe(stepLabels[i])}] --> S${i + 2}[${safe(stepLabels[i + 1])}]`);
  }
  lines.push(`  S${stepLabels.length}[${safe(stepLabels[stepLabels.length - 1])}] --> End[结束]`);
  return lines.join("\n");
}

type RuleViewMode = "naturalLanguage" | "flowchart" | "edit";

function MermaidDiagram({ chart, id }: { chart: string; id: string }) {
  const [svg, setSvg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    mermaid.initialize({ startOnLoad: false });
  }, []);
  useEffect(() => {
    if (!chart.trim()) {
      setSvg(null);
      setErr(null);
      return;
    }
    let cancelled = false;
    const uid = `mermaid-${id}-${Date.now()}`;
    mermaid
      .render(uid, chart)
      .then((result) => {
        if (!cancelled) {
          setSvg(result.svg);
          setErr(null);
        }
      })
      .catch((e) => {
        if (!cancelled) setErr(e?.message || "流程图渲染失败");
      });
    return () => {
      cancelled = true;
    };
  }, [chart, id]);
  if (err) return <p className="text-sm text-red-400">{err}</p>;
  if (!svg) return <p className="text-sm text-zinc-500">加载中…</p>;
  return <div className="mermaid-container [&_svg]:max-w-full [&_svg]:h-auto" dangerouslySetInnerHTML={{ __html: svg }} />;
}

export default function ProcessDocPage() {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ markdown: string; structured: unknown } | null>(null);
  const [feishuAvailable, setFeishuAvailable] = useState(false);
  const [feishuSyncing, setFeishuSyncing] = useState(false);
  const [feishuLink, setFeishuLink] = useState<string | null>(null);
  const [feishuError, setFeishuError] = useState<string | null>(null);

  const [rules, setRules] = useState<RulesPayload | null>(null);
  const [rulesLoading, setRulesLoading] = useState(true);
  const [rulesSaving, setRulesSaving] = useState(false);
  const [rulesMessage, setRulesMessage] = useState<{ type: "ok" | "err"; text: string } | null>(null);
  const [rulesSectionOpen, setRulesSectionOpen] = useState(false);
  const [ollamaConfigured, setOllamaConfigured] = useState(false);
  const [suggestLoading, setSuggestLoading] = useState<number | null>(null);
  const [ruleViewMode, setRuleViewMode] = useState<Record<string, RuleViewMode>>({});

  const updateProcessType = useCallback((index: number, patch: Partial<ProcessTypeRule>) => {
    setRules((prev) => {
      if (!prev?.process_types?.length) return prev;
      const next = { ...prev, process_types: [...prev.process_types] };
      next.process_types[index] = { ...next.process_types[index], ...patch };
      return next;
    });
  }, []);

  useEffect(() => {
    fetch("/api/process-doc/schema", { credentials: "include" })
      .then((r) => r.ok ? r.json() : {})
      .then((data: { feishu_configured?: boolean; ollama_configured?: boolean }) => {
        setFeishuAvailable(!!data.feishu_configured);
        setOllamaConfigured(!!data.ollama_configured);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    fetch("/api/process-doc/rules", { credentials: "include" })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.statusText))))
      .then((data: RulesPayload) => setRules(data))
      .catch(() => setRules({ schema_version: "1", process_types: [] }))
      .finally(() => setRulesLoading(false));
  }, []);

  const handleGenerate = async () => {
    const text = input.trim();
    if (!text) {
      setError("请填写自然语言描述");
      return;
    }
    setError(null);
    setResult(null);
    setLoading(true);
    try {
      const res = await fetch("/api/process-doc/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ natural_language: text }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(data.detail || "生成失败");
        return;
      }
      setResult({ markdown: data.markdown || "", structured: data.structured });
    } catch (e) {
      setError(e instanceof Error ? e.message : "请求失败");
    } finally {
      setLoading(false);
    }
  };

  const handleDownload = () => {
    if (!result?.markdown) return;
    const blob = new Blob([result.markdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "流程文档.md";
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleSyncFeishu = async () => {
    if (!result?.markdown) return;
    setFeishuError(null);
    setFeishuLink(null);
    setFeishuSyncing(true);
    try {
      const title = (result.structured as { title?: string })?.title || "流程文档";
      const res = await fetch("/api/process-doc/sync-feishu", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ title, markdown: result.markdown }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setFeishuError(data.detail || "同步失败");
        return;
      }
      setFeishuLink(data.url || null);
    } catch (e) {
      setFeishuError(e instanceof Error ? e.message : "请求失败");
    } finally {
      setFeishuSyncing(false);
    }
  };

  const handleSuggestFromNaturalLanguage = async (idx: number) => {
    const pt = rules?.process_types?.[idx];
    if (!pt) return;
    const text = (pt.natural_language_rule ?? "").trim();
    if (!text) {
      setRulesMessage({ type: "err", text: "请先填写自然语言描述" });
      return;
    }
    setRulesMessage(null);
    setSuggestLoading(idx);
    try {
      const res = await fetch("/api/process-doc/rules/suggest-from-natural-language", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ natural_language: text, process_type_id: pt.id }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setRulesMessage({ type: "err", text: data.detail || "生成建议失败" });
        return;
      }
      updateProcessType(idx, {
        prompt_instruction: data.prompt_instruction ?? pt.prompt_instruction,
        output_schema: data.output_schema ?? pt.output_schema,
      });
      setRulesMessage({ type: "ok", text: "已生成提示词，可微调后保存" });
    } catch (e) {
      setRulesMessage({ type: "err", text: e instanceof Error ? e.message : "请求失败" });
    } finally {
      setSuggestLoading(null);
    }
  };

  const handleSaveRules = async () => {
    if (!rules?.process_types?.length) return;
    setRulesMessage(null);
    setRulesSaving(true);
    try {
      const res = await fetch("/api/process-doc/rules", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          schema_version: rules.schema_version ?? "1",
          process_types: rules.process_types.map((t) => ({
            id: t.id,
            name: t.name ?? null,
            description: t.description ?? null,
            output_schema: t.output_schema ?? null,
            prompt_instruction: t.prompt_instruction ?? "",
            natural_language_rule: t.natural_language_rule ?? null,
          })),
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setRulesMessage({ type: "err", text: data.detail || "保存失败" });
        return;
      }
      setRulesMessage({ type: "ok", text: "规则已更新" });
    } catch (e) {
      setRulesMessage({ type: "err", text: e instanceof Error ? e.message : "请求失败" });
    } finally {
      setRulesSaving(false);
    }
  };

  return (
    <div className="p-6 md:p-8">
      <div className="mb-4">
        <Link
          href="/utils"
          className="text-sm text-zinc-400 hover:text-zinc-200"
        >
          ← 实用工具
        </Link>
      </div>
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-100">流程文档</h1>
        <p className="mt-1 text-sm text-zinc-500">
          用自然语言描述工作内容，由 AI 按规则生成标准财务业务流程文档，可站内预览与下载。
        </p>
      </div>

      <div className="space-y-6">
        <section className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
          <h2 className="mb-3 text-sm font-medium text-zinc-300">自然语言描述</h2>
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="例如：我每月 5 号从系统导出销售表，和上个月对比后做差异分析，发给经理"
            className="w-full min-h-[120px] rounded-md border border-zinc-700 bg-zinc-800/50 px-3 py-2 text-zinc-100 placeholder:text-zinc-500 focus:border-zinc-600 focus:outline-none"
            disabled={loading}
          />
          <div className="mt-3 flex items-center gap-3">
            <button
              type="button"
              onClick={handleGenerate}
              disabled={loading}
              className="rounded-md bg-zinc-700 px-4 py-2 text-sm font-medium text-zinc-100 hover:bg-zinc-600 disabled:opacity-50"
            >
              {loading ? "生成中…" : "生成流程文档"}
            </button>
            {error && <span className="text-sm text-red-400">{error}</span>}
          </div>
        </section>

        {result && (
          <section className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-sm font-medium text-zinc-300">预览与下载</h2>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleDownload}
                  className="rounded-md bg-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-100 hover:bg-zinc-600"
                >
                  下载 Markdown
                </button>
                {feishuAvailable && (
                  <button
                    type="button"
                    onClick={handleSyncFeishu}
                    disabled={feishuSyncing}
                    className="rounded-md bg-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-100 hover:bg-zinc-600 disabled:opacity-50"
                  >
                    {feishuSyncing ? "同步中…" : "同步到飞书"}
                  </button>
                )}
              </div>
            </div>
            {feishuLink && (
              <p className="mb-2 text-sm text-zinc-400">
                已同步：<a href={feishuLink} target="_blank" rel="noopener noreferrer" className="text-sky-400 hover:underline">{feishuLink}</a>
              </p>
            )}
            {feishuError && <p className="mb-2 text-sm text-red-400">{feishuError}</p>}
            <pre className="whitespace-pre-wrap rounded-md border border-zinc-700 bg-zinc-800/30 p-4 text-sm text-zinc-200 font-sans">
              {result.markdown}
            </pre>
          </section>
        )}

        <section className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
          <button
            type="button"
            onClick={() => setRulesSectionOpen((o) => !o)}
            className="flex w-full items-center justify-between text-left"
          >
            <h2 className="text-sm font-medium text-zinc-300">规则管理</h2>
            <span className="text-zinc-500">{rulesSectionOpen ? "收起" : "展开"}</span>
          </button>
          {rulesSectionOpen && (
            <div className="mt-4 space-y-4">
              {rulesLoading ? (
                <p className="text-sm text-zinc-500">加载规则中…</p>
              ) : rules?.process_types?.length ? (
                <>
                  {rules.process_types.map((pt, idx) => {
                    const viewMode = ruleViewMode[pt.id] ?? "edit";
                    return (
                      <div
                        key={pt.id}
                        className="rounded-md border border-zinc-700 bg-zinc-800/30 p-4 space-y-3"
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span className="text-xs font-medium text-zinc-500">流程类型 ID：{pt.id}</span>
                          <div className="flex gap-1">
                            {(["naturalLanguage", "flowchart", "edit"] as const).map((mode) => (
                              <button
                                key={mode}
                                type="button"
                                onClick={() => setRuleViewMode((m) => ({ ...m, [pt.id]: mode }))}
                                className={`rounded px-2 py-1 text-xs ${viewMode === mode ? "bg-zinc-600 text-zinc-100" : "text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200"}`}
                              >
                                {mode === "naturalLanguage" ? "自然语言" : mode === "flowchart" ? "流程图" : "编辑"}
                              </button>
                            ))}
                          </div>
                        </div>
                        {viewMode === "naturalLanguage" && (
                          <p className="text-sm text-zinc-300 whitespace-pre-wrap">{ruleToSummary(pt)}</p>
                        )}
                        {viewMode === "flowchart" && (
                          <div className="rounded border border-zinc-700 bg-zinc-900/50 p-4 min-h-[120px]">
                            <MermaidDiagram chart={ruleToMermaid(pt)} id={pt.id} />
                          </div>
                        )}
                        {viewMode === "edit" && (
                          <>
                            <div>
                              <label className="block text-xs text-zinc-400 mb-1">自然语言描述（用于生成提示词）</label>
                              <textarea
                                value={pt.natural_language_rule ?? ""}
                                onChange={(e) => updateProcessType(idx, { natural_language_rule: e.target.value })}
                                placeholder="用自然语言描述你希望流程文档包含哪些内容、格式要求等"
                                rows={2}
                                className="w-full rounded border border-zinc-600 bg-zinc-800 px-2 py-1.5 text-sm text-zinc-100 placeholder:text-zinc-500"
                              />
                              <button
                                type="button"
                                onClick={() => handleSuggestFromNaturalLanguage(idx)}
                                disabled={!ollamaConfigured || suggestLoading !== null}
                                className="mt-1 rounded bg-zinc-600 px-2 py-1 text-xs text-zinc-100 hover:bg-zinc-500 disabled:opacity-50"
                              >
                                {suggestLoading === idx ? "生成中…" : "根据自然语言生成提示词"}
                              </button>
                              {!ollamaConfigured && (
                                <span className="ml-2 text-xs text-zinc-500">需配置 Ollama 后可用</span>
                              )}
                            </div>
                            <div>
                              <label className="block text-xs text-zinc-400 mb-1">名称</label>
                              <input
                                type="text"
                                value={pt.name ?? ""}
                                onChange={(e) => updateProcessType(idx, { name: e.target.value })}
                                className="w-full rounded border border-zinc-600 bg-zinc-800 px-2 py-1.5 text-sm text-zinc-100"
                              />
                            </div>
                            <div>
                              <label className="block text-xs text-zinc-400 mb-1">描述</label>
                              <input
                                type="text"
                                value={pt.description ?? ""}
                                onChange={(e) => updateProcessType(idx, { description: e.target.value })}
                                className="w-full rounded border border-zinc-600 bg-zinc-800 px-2 py-1.5 text-sm text-zinc-100"
                              />
                            </div>
                            <div>
                              <label className="block text-xs text-zinc-400 mb-1">LLM 提示词（prompt_instruction）</label>
                              <textarea
                                value={pt.prompt_instruction ?? ""}
                                onChange={(e) => updateProcessType(idx, { prompt_instruction: e.target.value })}
                                rows={4}
                                className="w-full rounded border border-zinc-600 bg-zinc-800 px-2 py-1.5 text-sm text-zinc-100 font-mono"
                              />
                            </div>
                            {pt.output_schema != null && (
                              <div>
                                <label className="block text-xs text-zinc-400 mb-1">输出结构（只读）</label>
                                <pre className="rounded border border-zinc-700 bg-zinc-800/50 p-2 text-xs text-zinc-400 overflow-x-auto">
                                  {JSON.stringify(pt.output_schema, null, 2)}
                                </pre>
                              </div>
                            )}
                          </>
                        )}
                      </div>
                    );
                  })}
                  <div className="flex items-center gap-3">
                    <button
                      type="button"
                      onClick={handleSaveRules}
                      disabled={rulesSaving}
                      className="rounded-md bg-zinc-700 px-4 py-2 text-sm font-medium text-zinc-100 hover:bg-zinc-600 disabled:opacity-50"
                    >
                      {rulesSaving ? "保存中…" : "保存规则"}
                    </button>
                    {rulesMessage && (
                      <span className={rulesMessage.type === "ok" ? "text-sm text-green-400" : "text-sm text-red-400"}>
                        {rulesMessage.text}
                      </span>
                    )}
                  </div>
                </>
              ) : (
                <p className="text-sm text-zinc-500">暂无流程类型规则</p>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
