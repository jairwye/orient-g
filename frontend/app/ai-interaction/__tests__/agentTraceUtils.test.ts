import {
  appendAgentTraceStep,
  agentTierLabel,
  buildAgentMetaFromDone,
  doneTraceMessage,
  formatEvidencePackStatusLine,
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
  });

  it("merges thinking chunks", () => {
    const a = appendAgentTraceStep([], { kind: "thinking", message: "分析" });
    const b = appendAgentTraceStep(a, { kind: "thinking", message: "成本" });
    expect(b).toHaveLength(1);
    expect(b[0].message).toBe("分析成本");
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
