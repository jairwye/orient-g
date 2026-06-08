import type { AgentMeta, AgentTraceStep, ChatMessage, EvidencePackSummary, HermesStreamStats } from "./types";

export function hydrateChatMessage(raw: unknown): ChatMessage | null {
  if (!raw || typeof raw !== "object") return null;
  const mm = raw as ChatMessage;
  if (mm.role !== "user" && mm.role !== "assistant") return null;
  if (typeof mm.content !== "string") return null;
  const trace = Array.isArray(mm.agentTrace)
    ? mm.agentTrace.filter((t): t is AgentTraceStep => {
        if (!t || typeof t !== "object") return false;
        const o = t as AgentTraceStep;
        return typeof o.message === "string" && typeof o.at === "number";
      })
    : undefined;
  const reasoning =
    typeof mm.agentReasoning === "string" && mm.agentReasoning.trim()
      ? mm.agentReasoning
      : undefined;
  const meta =
    mm.agentMeta && typeof mm.agentMeta === "object"
      ? buildAgentMetaFromDone(mm.agentMeta as Record<string, unknown>)
      : undefined;
  return {
    role: mm.role,
    content: mm.content,
    citations: Array.isArray(mm.citations) ? mm.citations : undefined,
    deny_reason: typeof mm.deny_reason === "string" ? mm.deny_reason : undefined,
    chart_spec: mm.chart_spec ?? null,
    table_spec: mm.table_spec ?? null,
    agentTrace: trace?.length ? trace : undefined,
    agentReasoning: reasoning,
    agentMeta: meta,
    evidence_pack: parseEvidencePackSummary(mm.evidence_pack),
  };
}

export function chatMessagesSnapshotEqual(a: ChatMessage[], b: ChatMessage[]): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) {
    const x = a[i];
    const y = b[i];
    if (x.role !== y.role || x.content !== y.content) return false;
    if ((x.agentReasoning || "") !== (y.agentReasoning || "")) return false;
    if (JSON.stringify(x.agentMeta ?? null) !== JSON.stringify(y.agentMeta ?? null)) return false;
    if (JSON.stringify(x.agentTrace ?? null) !== JSON.stringify(y.agentTrace ?? null)) return false;
  }
  return true;
}

export function parseEvidencePackSummary(raw: unknown): EvidencePackSummary | undefined {
  if (!raw || typeof raw !== "object") return undefined;
  const o = raw as Record<string, unknown>;
  const pack: EvidencePackSummary = {};
  if (typeof o.task_type === "string") pack.task_type = o.task_type;
  if (Array.isArray(o.gaps)) {
    pack.gaps = o.gaps.filter((g): g is string => typeof g === "string" && g.trim().length > 0);
  }
  if (typeof o.coverage_score === "number" && !Number.isNaN(o.coverage_score)) {
    pack.coverage_score = o.coverage_score;
  }
  if (Array.isArray(o.retrieval_queries)) {
    pack.retrieval_queries = o.retrieval_queries.filter(
      (q): q is string => typeof q === "string" && q.trim().length > 0,
    );
  }
  return Object.keys(pack).length ? pack : undefined;
}

export function formatEvidencePackStatusLine(pack?: EvidencePackSummary): string {
  if (!pack) return "";
  const parts: string[] = [];
  if (pack.task_type) parts.push(`任务 ${pack.task_type}`);
  if (typeof pack.coverage_score === "number") {
    parts.push(`覆盖率 ${Math.round(pack.coverage_score * 100)}%`);
  }
  const nq = pack.retrieval_queries?.length;
  if (nq && nq > 0) parts.push(`子检索 ${nq} 条`);
  const gaps = pack.gaps || [];
  if (gaps.length) parts.push(`缺项 ${gaps.length}`);
  if (!parts.length) return "";
  let line = `Evidence Pack：${parts.join(" · ")}`;
  if (gaps.length) line += `（${gaps.slice(0, 2).join("；")}）`;
  return line;
}

export function agentTierLabel(tier?: number): string {
  if (tier === 0) return "Tier 0（本地证据综合）";
  if (tier === 1) return "Tier 1（Hermes 受限）";
  if (tier === 2) return "Tier 2（Hermes 深度）";
  return "";
}

export function agentTraceStepsEqual(a: AgentTraceStep[], b: AgentTraceStep[]): boolean {
  if (a === b) return true;
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) {
    const x = a[i];
    const y = b[i];
    if (
      x.kind !== y.kind ||
      x.message !== y.message ||
      (x.step || "") !== (y.step || "") ||
      (x.toolCallId || "") !== (y.toolCallId || "") ||
      (x.toolStatus || "") !== (y.toolStatus || "")
    ) {
      return false;
    }
  }
  return true;
}

function mergeHermesDraftTrace(tail: string, incoming: string): string | null {
  if (!incoming) return null;
  if (incoming === tail) return null;
  if (incoming.startsWith(tail)) return incoming;
  if (tail.startsWith(incoming)) return tail;
  const score = (s: string) => {
    let pts = s.length;
    if (s.includes("|") && (s.includes("---") || s.includes("变动"))) pts += 800;
    if (/###\s[\u4e00-\u9fff]/.test(s)) pts += 400;
    if (/[\u4e00-\u9fff]{30,}/.test(s)) pts += 200;
    if (/###[^\s#\u4e00-\u9fff]{0,5}[\u4e00-\u9fff]/.test(s)) pts -= 300;
    return pts;
  };
  const st = score(tail);
  const si = score(incoming);
  if (Math.abs(st - si) > 80) return si >= st ? incoming : tail;
  return incoming.length >= tail.length ? incoming : tail;
}

function mergeThinkingTraceMessage(
  tailMessage: string,
  incoming: string,
  step?: string,
): string | null {
  const tailRaw = tailMessage || "";
  const msgRaw = incoming || "";
  if (!msgRaw) return null;
  if (msgRaw === tailRaw) return null;
  if (msgRaw.startsWith(tailRaw)) return msgRaw;
  if (tailRaw.startsWith(msgRaw)) return tailRaw;
  const norm = (s: string) => s.replace(/\s+/g, " ").trim();
  const tailN = norm(tailRaw);
  const msgN = norm(msgRaw);
  if (msgN && tailN) {
    if (msgN.startsWith(tailN)) return msgRaw;
    if (tailN.startsWith(msgN)) return tailRaw;
    if (tailN.includes(msgN) && msgN.length <= tailN.length) return null;
    if (msgN.includes(tailN) && tailN.length <= msgN.length) return msgRaw;
  }
  if (tailRaw.endsWith(msgRaw) || tailN.endsWith(msgN)) return null;
  if (step === "hermes_draft") {
    return mergeHermesDraftTrace(tailRaw, msgRaw);
  }
  return tailRaw + msgRaw;
}

export function appendAgentTraceStep(
  trace: AgentTraceStep[],
  step: Omit<AgentTraceStep, "at">,
): AgentTraceStep[] {
  const msg = (step.message || "").trim();
  if (!msg) return trace;
  const tail = trace[trace.length - 1];
  if (step.kind === "thinking" && tail?.kind === "thinking" && tail.message.length < 12000) {
    const sameStep = (tail.step || "") === (step.step || "");
    if (sameStep) {
      const merged = mergeThinkingTraceMessage(tail.message, msg, step.step);
      if (merged === null) return trace;
      const next = [...trace];
      next[next.length - 1] = { ...tail, message: merged };
      return next.slice(-80);
    }
  }
  if (tail?.kind === step.kind && tail.message === msg && step.kind === "status") {
    return trace;
  }
  const next = [...trace];
  next.push({ at: Date.now(), ...step, message: msg });
  return next.slice(-80);
}

/** Hermes `tool_progress`：按 toolCallId 更新 running → completed。 */
/** Hermes completed 事件常只有工具名，保留 running 时的 label/命令预览。 */
export function mergeToolProgressMessage(
  previous: AgentTraceStep,
  incoming: { message: string; tool?: string; toolStatus: "running" | "completed" },
): string {
  if (incoming.toolStatus !== "completed") {
    return incoming.message;
  }
  const prevMsg = (previous.message || "").trim();
  const bare = (incoming.message || "").trim();
  const toolName = (incoming.tool || previous.tool || "").trim();
  if (!prevMsg) return bare || toolName;
  if (!bare || bare === toolName) return prevMsg;
  if (bare.length < prevMsg.length && prevMsg.toLowerCase().includes(bare.toLowerCase())) {
    return prevMsg;
  }
  return incoming.message;
}

export function upsertAgentToolTrace(
  trace: AgentTraceStep[],
  step: {
    toolCallId: string;
    message: string;
    toolStatus: "running" | "completed";
    emoji?: string;
    tool?: string;
  },
): AgentTraceStep[] {
  const id = (step.toolCallId || "").trim();
  if (!id) {
    return appendAgentTraceStep(trace, {
      kind: "tool",
      message: step.message,
      toolStatus: step.toolStatus,
      emoji: step.emoji,
      tool: step.tool,
    });
  }
  const idx = trace.findIndex((t) => t.kind === "tool" && t.toolCallId === id);
  if (idx >= 0) {
    const prev = trace[idx];
    const mergedMsg = mergeToolProgressMessage(prev, step);
    if (
      mergedMsg === prev.message &&
      step.toolStatus === prev.toolStatus &&
      (step.emoji ?? prev.emoji) === prev.emoji &&
      (step.tool ?? prev.tool) === prev.tool
    ) {
      return trace;
    }
    const next = [...trace];
    next[idx] = {
      ...prev,
      message: mergedMsg,
      toolStatus: step.toolStatus,
      emoji: step.emoji ?? prev.emoji,
      tool: step.tool ?? prev.tool,
    };
    return next;
  }
  return appendAgentTraceStep(trace, {
    kind: "tool",
    message: step.message,
    toolCallId: id,
    toolStatus: step.toolStatus,
    emoji: step.emoji,
    tool: step.tool,
  });
}

export function parseHermesStreamStats(raw: unknown): HermesStreamStats | undefined {
  if (!raw || typeof raw !== "object") return undefined;
  const o = raw as Record<string, unknown>;
  const n = (k: string) => {
    const v = o[k];
    return typeof v === "number" && !Number.isNaN(v) ? v : undefined;
  };
  const stats: HermesStreamStats = {
    thinking_chars: n("thinking_chars"),
    delta_chars: n("delta_chars"),
    tool_progress_events: n("tool_progress_events"),
    tool_call_events: n("tool_call_events"),
    orientg_kb_ask_calls: n("orientg_kb_ask_calls"),
    orientg_kb_supplemental_calls: n("orientg_kb_supplemental_calls"),
  };
  return Object.values(stats).some((v) => v !== undefined) ? stats : undefined;
}

export function formatHermesStreamStatsLine(
  stats?: HermesStreamStats,
  meta?: Pick<
    AgentMeta,
    "hermes_stream_mode" | "agent_tier" | "kb_supplemental" | "supplemental_adopted"
  >,
): string {
  if (!stats) return "";
  const parts: string[] = [];
  if (meta?.hermes_stream_mode) parts.push(`通道 ${meta.hermes_stream_mode}`);
  if (stats.thinking_chars && stats.thinking_chars > 0) {
    parts.push(`推理流 ${stats.thinking_chars} 字`);
  } else if (meta?.agent_tier === 2 && !meta?.kb_supplemental) {
    parts.push("推理流 0（上游未推送 thinking）");
  }
  if (typeof stats.delta_chars === "number") parts.push(`正文流 ${stats.delta_chars} 字`);
  const toolProg = stats.tool_progress_events;
  if (typeof toolProg === "number") {
    parts.push(
      toolProg === 0
        ? "Hermes 工具进度 0（本 run 未调用 MCP）"
        : `Hermes 工具进度 ${toolProg} 次`,
    );
  }
  const kb = stats.orientg_kb_ask_calls ?? 0;
  const supp = stats.orientg_kb_supplemental_calls ?? 0;
  if (kb > 0) {
    parts.push(`Hermes 内 orientg_kb_ask ×${kb}`);
  } else if (meta?.kb_supplemental) {
    parts.push(
      supp > 0
        ? `Hermes 单轮未调 MCP；Orient-G 网关补检索 ×${supp}`
        : "Hermes 单轮未调 MCP；已由 Orient-G 网关修订终稿",
    );
  } else if (meta?.agent_tier === 2) {
    parts.push("Hermes 单轮 completion（深度可触发 Orient-G 网关补检索）");
  }
  return parts.length ? `编排观测：${parts.join(" · ")}` : "";
}

export function buildAgentMetaFromDone(evt: Record<string, unknown>): AgentMeta {
  const tierRaw = evt.agent_tier;
  const agent_tier =
    typeof tierRaw === "number" && tierRaw >= 0 && tierRaw <= 2 ? tierRaw : undefined;
  return {
    agent_route: typeof evt.agent_route === "string" ? evt.agent_route : undefined,
    agent_tier,
    evidence_pack: parseEvidencePackSummary(evt.evidence_pack),
    hermes_used: evt.hermes_used === true,
    kb_fast_path: evt.kb_fast_path === true,
    hermes_fallback: evt.hermes_fallback === true,
    hermes_salvaged:
      evt.hermes_salvaged === true || evt.synthesis === "hermes_salvaged",
    synthesis: typeof evt.synthesis === "string" ? evt.synthesis : undefined,
    llm_model: typeof evt.llm_model === "string" ? evt.llm_model : undefined,
    hermes_stream_mode:
      typeof evt.hermes_stream_mode === "string" ? evt.hermes_stream_mode : undefined,
    hermes_stream_stats: parseHermesStreamStats(evt.hermes_stream_stats),
    kb_supplemental: evt.kb_supplemental === true,
    supplemental_adopted:
      typeof evt.supplemental_adopted === "boolean" ? evt.supplemental_adopted : undefined,
  };
}

function supplementalDoneSuffix(meta: AgentMeta): string {
  if (!meta.kb_supplemental) return "";
  if (meta.supplemental_adopted === false) {
    return " · Orient-G 补检索完成（保留 Hermes 原文）";
  }
  return " · Orient-G 自动补检索修订";
}

export function routeLabel(meta?: AgentMeta): string {
  if (!meta) return "";
  const tier = agentTierLabel(meta.agent_tier);
  if (meta.kb_fast_path || meta.agent_route === "fast" || meta.agent_tier === 0) {
    const base = "标准 · Tier 0（Orient-G 本地证据综合，未走 Hermes）";
    return tier ? `${tier} · ${base}` : base;
  }
  if (meta.hermes_fallback) return "标准 · Hermes 失败后回退本地 LLM";
  if (meta.agent_route === "hermes_full" || meta.agent_tier === 2) {
    return tier ? `${tier} · 深度（Hermes 全编排）` : "深度（Hermes 全编排）";
  }
  if (meta.agent_route === "hermes_lite" || meta.agent_tier === 1) {
    return tier ? `${tier} · 标准（Hermes lite + Evidence Pack）` : "标准（Hermes lite + 预检索）";
  }
  if (meta.hermes_used) {
    if (meta.hermes_stream_mode === "runs") return "Hermes（Runs API）";
    return "Hermes";
  }
  return meta.agent_route || meta.synthesis || "";
}

export function doneTraceMessage(meta: AgentMeta): string {
  const packLine = formatEvidencePackStatusLine(meta.evidence_pack);
  const packSuffix = packLine ? ` · ${packLine}` : "";
  if (meta.kb_fast_path || meta.agent_route === "fast" || meta.agent_tier === 0) {
    return `完成：Tier 0（Orient-G 本地证据综合，未使用 Hermes）${packSuffix}`;
  }
  if (meta.hermes_fallback) {
    return "完成：Hermes 已结束，最终答案由 Orient-G 本地 LLM 基于预检索生成";
  }
  if (meta.hermes_salvaged) {
    return `完成：Hermes 中断后已 salvage 过程稿为终稿${packSuffix}`;
  }
  if (meta.agent_route === "hermes_full" || meta.agent_tier === 2) {
    const obs = formatHermesStreamStatsLine(meta.hermes_stream_stats, meta);
    const sup = supplementalDoneSuffix(meta);
    return `完成：Tier 2（Hermes 深度编排）${packSuffix}${sup}${obs ? ` · ${obs}` : ""}`;
  }
  if (meta.agent_route === "hermes_lite" || meta.agent_tier === 1) {
    const sup = supplementalDoneSuffix(meta);
    return `完成：Tier 1（Hermes lite）；若本机 GPU 仍占用，可能为 Gateway 后台收尾${packSuffix}${sup}`;
  }
  if (meta.hermes_used) return `完成：Hermes 流式已结束${packSuffix}`;
  return packLine ? `完成${packSuffix}` : "完成";
}

/** 合并 SSE done 元数据到助手消息；保留 agentTrace，不清空过程。 */
export function mergeAssistantOnAgentDone(
  msg: ChatMessage,
  opts: {
    content: string;
    agentMeta?: AgentMeta;
    citations?: ChatMessage["citations"];
    chart_spec?: ChatMessage["chart_spec"];
    table_spec?: ChatMessage["table_spec"];
    appendMetaTrace?: boolean;
  },
): ChatMessage {
  let trace = msg.agentTrace || [];
  if (opts.appendMetaTrace && opts.agentMeta) {
    trace = appendAgentTraceStep(trace, {
      kind: "meta",
      message: doneTraceMessage(opts.agentMeta),
    });
  }
  return {
    ...msg,
    content: opts.content,
    agentTrace: trace.length ? trace : msg.agentTrace,
    agentMeta: opts.agentMeta ?? msg.agentMeta,
    citations: opts.citations ?? msg.citations,
    chart_spec: opts.chart_spec ?? msg.chart_spec,
    table_spec: opts.table_spec ?? msg.table_spec,
    streamStatus: undefined,
  };
}

export function traceStepLabel(step?: string): string {
  if (step === "hermes_draft") return "Hermes 过程稿";
  if (step === "hermes_reasoning") return "Hermes 推理流";
  return "";
}

/** @deprecated use traceStepLabel */
export function hermesDraftTraceLabel(step?: string): string {
  return traceStepLabel(step);
}

export function traceFromLegacyStreamStatus(lines: string[]): AgentTraceStep[] {
  return lines.map((line, i) => ({
    at: i,
    kind: "status" as const,
    message: line,
  }));
}
