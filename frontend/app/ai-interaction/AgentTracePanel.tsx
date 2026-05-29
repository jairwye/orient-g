"use client";

import { routeLabel } from "./agentTraceUtils";
import type { AgentMeta, AgentTraceStep } from "./types";

function stepIcon(kind: AgentTraceStep["kind"]): string {
  switch (kind) {
    case "tool":
      return "◇";
    case "thinking":
      return "◈";
    case "error":
      return "✕";
    case "meta":
      return "●";
    default:
      return "›";
  }
}

export default function AgentTracePanel({
  trace,
  meta,
  defaultOpen = false,
}: {
  trace?: AgentTraceStep[];
  meta?: AgentMeta;
  defaultOpen?: boolean;
}) {
  const steps = trace || [];
  if (steps.length === 0 && !meta) return null;

  const summary = routeLabel(meta) || `共 ${steps.length} 步`;

  return (
    <details
      className="mb-2 w-full rounded-lg border border-zinc-800/80 bg-zinc-950/40 text-xs"
      open={defaultOpen}
    >
      <summary className="cursor-pointer select-none px-2.5 py-2 text-zinc-400 hover:text-zinc-200">
        执行过程
        <span className="ml-2 text-zinc-500">({summary})</span>
      </summary>
      <ul className="max-h-48 space-y-1 overflow-y-auto border-t border-zinc-800/60 px-2.5 py-2">
        {steps.map((s, i) => (
          <li
            key={`${s.at}-${i}-${s.kind}`}
            className={[
              "whitespace-pre-wrap break-words leading-relaxed",
              s.kind === "thinking" ? "text-zinc-500 italic" : "text-zinc-500",
              s.kind === "error" ? "text-red-400/90" : "",
              s.kind === "meta" ? "text-blue-400/80" : "",
              s.kind === "tool" && s.toolStatus === "completed" ? "text-zinc-600" : "",
            ].join(" ")}
          >
            <span className="mr-1.5 font-mono text-[10px] text-zinc-600">{stepIcon(s.kind)}</span>
            {s.message}
            {s.kind === "tool" && s.toolStatus === "completed" ? (
              <span className="ml-1.5 text-[10px] text-zinc-600">（完成）</span>
            ) : null}
          </li>
        ))}
      </ul>
      {meta?.llm_model ? (
        <p className="border-t border-zinc-800/60 px-2.5 py-1.5 text-[11px] text-zinc-600">
          模型：{meta.llm_model}
        </p>
      ) : null}
    </details>
  );
}
