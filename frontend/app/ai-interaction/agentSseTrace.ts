import type { AgentTraceStep } from "./types";

/** Hermes `tool_progress` SSE → 执行过程步骤。 */
export function mapToolProgressToTraceStep(
  evt: Record<string, unknown>,
): Omit<AgentTraceStep, "at"> {
  const status = evt.status === "completed" ? "completed" : "running";
  const tool = typeof evt.tool === "string" ? evt.tool : undefined;
  return {
    kind: "tool",
    message: String(evt.message || evt.label || tool || "工具执行"),
    toolCallId: String(evt.tool_call_id || evt.toolCallId || tool || ""),
    toolStatus: status,
    emoji: typeof evt.emoji === "string" ? evt.emoji : undefined,
    tool,
  };
}

/** 已有 Hermes tool_progress 时跳过 OpenAI delta.tool_calls 重复行。 */
export function shouldSkipRedundantToolCall(
  trace: AgentTraceStep[],
  evt: { name?: string },
): boolean {
  const name = String(evt.name || "").trim();
  if (!name) return false;
  const short = name.split("_").pop() || name;
  return trace.some((t) => {
    if (t.kind !== "tool") return false;
    const msg = (t.message || "").toLowerCase();
    return (
      (t.toolCallId && t.toolStatus === "running") ||
      msg.includes(name.toLowerCase()) ||
      msg.includes(short.toLowerCase())
    );
  });
}
