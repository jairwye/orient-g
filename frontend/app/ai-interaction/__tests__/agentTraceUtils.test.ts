import {
  appendAgentTraceStep,
  agentTierLabel,
  buildAgentMetaFromDone,
  chatMessagesSnapshotEqual,
  doneTraceMessage,
  formatEvidencePackStatusLine,
  formatHermesStreamStatsLine,
  hydrateChatMessage,
  mergeAssistantOnAgentDone,
  parseEvidencePackSummary,
  routeLabel,
  traceFromLegacyStreamStatus,
  upsertAgentToolTrace,
} from "../agentTraceUtils";
import type { ChatMessage } from "../types";

describe("appendAgentTraceStep", () => {
  it("appends status steps", () => {
    const t = appendAgentTraceStep([], { kind: "status", message: "预检索完成" });
    expect(t).toHaveLength(1);
    expect(t[0].message).toBe("预检索完成");
  });

  it("dedupes identical consecutive status", () => {
    const a = appendAgentTraceStep([], { kind: "status", message: "心跳" });
    const b = appendAgentTraceStep(a, { kind: "status", message: "心跳" });
    expect(b).toHaveLength(1);
    expect(b).toBe(a);
  });

  it("merges cumulative thinking chunks", () => {
    const a = appendAgentTraceStep([], { kind: "thinking", message: "2025年销售" });
    const b = appendAgentTraceStep(a, { kind: "thinking", message: "2025年销售费用" });
    expect(b).toHaveLength(1);
    expect(b[0].message).toBe("2025年销售费用");
  });

  it("merges hermes_draft disjoint chunks by structure not concat", () => {
    const a = appendAgentTraceStep([], {
      kind: "thinking",
      message: "乱码###清52销售1",
      step: "hermes_draft",
    });
    const b = appendAgentTraceStep(a, {
      kind: "thinking",
      message: "### 华清对比\n| 项目 | 2025 |\n| 销售费用 | 13,722,360.23 |",
      step: "hermes_draft",
    });
    expect(b).toHaveLength(1);
    expect(b[0].message).toContain("### 华清对比");
    expect(b[0].message).not.toContain("乱码###");
  });

  it("does not merge thinking chunks with different step", () => {
    const a = appendAgentTraceStep([], {
      kind: "thinking",
      message: "Hermes 过程稿 A",
      step: "hermes_draft",
    });
    const b = appendAgentTraceStep(a, {
      kind: "thinking",
      message: "其他推理",
      step: "hermes_reasoning",
    });
    expect(b).toHaveLength(2);
  });
});

describe("buildAgentMetaFromDone / routeLabel", () => {
  it("labels fast path / tier 0", () => {
    const meta = buildAgentMetaFromDone({
      agent_route: "fast",
      kb_fast_path: true,
      agent_tier: 0,
      evidence_pack: {
        task_type: "fact",
        coverage_score: 0.82,
        retrieval_queries: ["华清营收"],
      },
    });
    expect(routeLabel(meta)).toContain("未走 Hermes");
    expect(routeLabel(meta)).toContain("Tier 0");
    expect(doneTraceMessage(meta)).toContain("Tier 0");
    expect(doneTraceMessage(meta)).toContain("Evidence Pack");
  });

  it("parses evidence pack summary", () => {
    const pack = parseEvidencePackSummary({
      task_type: "breakdown",
      coverage_score: 0.6,
      retrieval_queries: ["q1", "q2"],
      gaps: ["未命中附注"],
    });
    const line = formatEvidencePackStatusLine(pack);
    expect(line).toContain("breakdown");
    expect(line).toContain("子检索 2 条");
    expect(line).toContain("缺项");
    expect(agentTierLabel(1)).toContain("Hermes 受限");
  });

  it("labels hermes lite", () => {
    const meta = buildAgentMetaFromDone({ agent_route: "hermes_lite", hermes_used: true });
    expect(routeLabel(meta)).toContain("Hermes lite");
  });

  it("tier2 with supplemental shows gateway kb line not warning", () => {
    const meta = buildAgentMetaFromDone({
      agent_route: "hermes_full",
      agent_tier: 2,
      kb_supplemental: true,
      supplemental_adopted: true,
      hermes_stream_mode: "runs",
      hermes_stream_stats: {
        thinking_chars: 500,
        delta_chars: 994,
        tool_progress_events: 0,
        orientg_kb_ask_calls: 0,
        orientg_kb_supplemental_calls: 4,
      },
    });
    const obs = formatHermesStreamStatsLine(meta.hermes_stream_stats, meta);
    expect(obs).toContain("Orient-G 网关补检索 ×4");
    expect(obs).not.toContain("⚠");
    expect(obs).toContain("Hermes 工具进度 0");
  });

  it("tier2 done warns when Hermes kb_ask not observed and no supplemental", () => {
    const meta = buildAgentMetaFromDone({
      agent_route: "hermes_full",
      agent_tier: 2,
      hermes_stream_mode: "chat_completions",
      hermes_stream_stats: {
        thinking_chars: 0,
        delta_chars: 1200,
        tool_progress_events: 0,
        orientg_kb_ask_calls: 0,
      },
    });
    const line = doneTraceMessage(meta);
    expect(line).toContain("Tier 2");
    expect(formatHermesStreamStatsLine(meta.hermes_stream_stats, meta)).toContain(
      "Hermes 单轮 completion",
    );
  });

  it("tier2 done shows Hermes kb_ask count when present", () => {
    const meta = buildAgentMetaFromDone({
      agent_route: "hermes_full",
      agent_tier: 2,
      hermes_stream_mode: "runs",
      hermes_stream_stats: {
        thinking_chars: 400,
        delta_chars: 800,
        tool_progress_events: 3,
        orientg_kb_ask_calls: 2,
      },
    });
    const line = doneTraceMessage(meta);
    expect(line).toContain("orientg_kb_ask ×2");
    expect(line).toContain("推理流 400");
  });

  it("tier1 supplemental kept hermes shows distinct done line", () => {
    const meta = buildAgentMetaFromDone({
      agent_route: "hermes_lite",
      agent_tier: 1,
      kb_supplemental: true,
      supplemental_adopted: false,
    });
    const line = doneTraceMessage(meta);
    expect(line).toContain("保留 Hermes 原文");
    expect(line).not.toContain("自动补检索修订");
  });
});

describe("hydrateChatMessage", () => {
  it("restores agent trace and reasoning from storage", () => {
    const m = hydrateChatMessage({
      role: "assistant",
      content: "答案",
      agentTrace: [{ at: 1, kind: "status", message: "预检索" }],
      agentReasoning: "思考片段",
      agentMeta: { agent_route: "hermes_full", agent_tier: 2, hermes_used: true },
    });
    expect(m?.agentTrace).toHaveLength(1);
    expect(m?.agentReasoning).toBe("思考片段");
    expect(m?.agentMeta?.agent_tier).toBe(2);
  });
});

describe("chatMessagesSnapshotEqual", () => {
  it("detects agentTrace changes", () => {
    const a: ChatMessage[] = [{ role: "assistant", content: "x", agentTrace: [{ at: 1, kind: "status", message: "a" }] }];
    const b: ChatMessage[] = [{ role: "assistant", content: "x" }];
    expect(chatMessagesSnapshotEqual(a, b)).toBe(false);
  });
});

describe("mergeAssistantOnAgentDone", () => {
  it("preserves agentTrace and sets meta", () => {
    const msg: ChatMessage = {
      role: "assistant",
      content: "",
      agentTrace: [{ at: 1, kind: "status", message: "预检索：orientg_kb_ask" }],
    };
    const meta = buildAgentMetaFromDone({ agent_route: "hermes_lite", hermes_used: true });
    const out = mergeAssistantOnAgentDone(msg, {
      content: "正文",
      agentMeta: meta,
      appendMetaTrace: true,
    });
    expect(out.content).toBe("正文");
    expect(out.agentTrace?.length).toBeGreaterThanOrEqual(2);
    expect(out.agentMeta?.agent_route).toBe("hermes_lite");
    expect(out.streamStatus).toBeUndefined();
  });
});

describe("upsertAgentToolTrace", () => {
  it("appends running then updates to completed by toolCallId", () => {
    const a = upsertAgentToolTrace([], {
      toolCallId: "call_1",
      message: "🔧 kb: ask",
      toolStatus: "running",
      emoji: "🔧",
    });
    expect(a).toHaveLength(1);
    expect(a[0].toolStatus).toBe("running");
    const b = upsertAgentToolTrace(a, {
      toolCallId: "call_1",
      message: "🔧 kb: ask",
      toolStatus: "completed",
    });
    expect(b).toHaveLength(1);
    expect(b[0].toolStatus).toBe("completed");
  });

  it("keeps terminal command label when completed only sends tool name", () => {
    const a = upsertAgentToolTrace([], {
      toolCallId: "t1",
      message: "🔧 terminal: cat foo.md",
      toolStatus: "running",
      tool: "terminal",
    });
    const b = upsertAgentToolTrace(a, {
      toolCallId: "t1",
      message: "terminal",
      toolStatus: "completed",
      tool: "terminal",
    });
    expect(b[0].message).toContain("cat foo.md");
    expect(b[0].toolStatus).toBe("completed");
  });
});

describe("traceFromLegacyStreamStatus", () => {
  it("maps old sessions", () => {
    const t = traceFromLegacyStreamStatus(["a", "b"]);
    expect(t).toHaveLength(2);
    expect(t[0].kind).toBe("status");
  });
});
