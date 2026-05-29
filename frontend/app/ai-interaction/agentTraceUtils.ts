import type { AgentMeta, AgentTraceStep, ChatMessage, EvidencePackSummary } from "./types";

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

export function appendAgentTraceStep(
  trace: AgentTraceStep[],
  step: Omit<AgentTraceStep, "at">,
): AgentTraceStep[] {
  const msg = (step.message || "").trim();
  if (!msg) return trace;
  const next = [...trace];
  const tail = next[next.length - 1];
  if (step.kind === "thinking" && tail?.kind === "thinking" && tail.message.length < 12000) {
    next[next.length - 1] = { ...tail, message: tail.message + msg };
    return next.slice(-80);
  }
  if (tail?.kind === step.kind && tail.message === msg && step.kind === "status") {
    return next;
  }
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
    const next = [...trace];
    const prev = next[idx];
    next[idx] = {
      ...prev,
      message: mergeToolProgressMessage(prev, step),
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
    synthesis: typeof evt.synthesis === "string" ? evt.synthesis : undefined,
    llm_model: typeof evt.llm_model === "string" ? evt.llm_model : undefined,
    hermes_stream_mode:
      typeof evt.hermes_stream_mode === "string" ? evt.hermes_stream_mode : undefined,
  };
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
  if (meta.agent_route === "hermes_full" || meta.agent_tier === 2) {
    return `完成：Tier 2（Hermes 深度编排）${packSuffix}`;
  }
  if (meta.agent_route === "hermes_lite" || meta.agent_tier === 1) {
    return `完成：Tier 1（Hermes lite）；若本机 GPU 仍占用，可能为 Gateway 后台收尾${packSuffix}`;
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

export function traceFromLegacyStreamStatus(lines: string[]): AgentTraceStep[] {
  return lines.map((line, i) => ({
    at: i,
    kind: "status" as const,
    message: line,
  }));
}
