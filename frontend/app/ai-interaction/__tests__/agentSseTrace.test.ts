import {
  mapToolProgressToTraceStep,
  shouldSkipRedundantToolCall,
} from "../agentSseTrace";
import type { AgentTraceStep } from "../types";

describe("mapToolProgressToTraceStep", () => {
  it("maps running tool_progress SSE", () => {
    const step = mapToolProgressToTraceStep({
      type: "tool_progress",
      tool_call_id: "c1",
      message: "📚 kb: ask",
      status: "running",
      emoji: "📚",
    });
    expect(step.kind).toBe("tool");
    expect(step.toolCallId).toBe("c1");
    expect(step.toolStatus).toBe("running");
    expect(step.message).toBe("📚 kb: ask");
  });
});

describe("shouldSkipRedundantToolCall", () => {
  it("skips OpenAI tool_call when tool_progress already recorded", () => {
    const trace: AgentTraceStep[] = [
      {
        at: 1,
        kind: "tool",
        message: "📚 orientg_kb_ask",
        toolCallId: "c1",
        toolStatus: "running",
      },
    ];
    expect(
      shouldSkipRedundantToolCall(trace, {
        name: "mcp_orientg_orientg_kb_ask",
      }),
    ).toBe(true);
  });

  it("does not skip unrelated tools", () => {
    expect(shouldSkipRedundantToolCall([], { name: "terminal" })).toBe(false);
  });
});
