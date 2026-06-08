"use client";

import { useEffect, useRef } from "react";

import { routeLabel, traceStepLabel } from "./agentTraceUtils";
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
  forceOpen = false,
  streaming = false,
}: {
  trace?: AgentTraceStep[];
  meta?: AgentMeta;
  defaultOpen?: boolean;
  /** 流式阶段强制展开（Hermes 工具步同步可见） */
  forceOpen?: boolean;
  streaming?: boolean;
}) {
  const steps = trace || [];
  const listRef = useRef<HTMLUListElement>(null);
  const tailSig =
    steps.length > 0
      ? `${steps.length}:${(steps[steps.length - 1]?.message || "").length}`
      : "0";

  useEffect(() => {
    if (!streaming) return;
    const t = window.setTimeout(() => {
      const el = listRef.current;
      if (!el) return;
      el.scrollTop = el.scrollHeight;
    }, 80);
    return () => window.clearTimeout(t);
  }, [streaming, tailSig]);

  if (steps.length === 0 && !meta) return null;

  const summary = routeLabel(meta) || `共 ${steps.length} 步`;
  const panelClass =
    "mb-2 w-full rounded-lg border border-zinc-800/80 bg-zinc-950/40 text-xs";
  const header = (
    <>
      执行过程
      <span className="ml-2 text-zinc-500">({summary})</span>
      {streaming ? (
        <span className="ml-2 animate-pulse text-[#2563eb]/90">同步中…</span>
      ) : null}
    </>
  );
  const list = (
    <ul
      ref={listRef}
      className={[
        "space-y-1 overflow-y-auto border-t border-zinc-800/60 px-2.5 py-2",
        streaming ? "max-h-80" : "max-h-64",
      ].join(" ")}
    >
      {steps.map((s, i) => {
        const draftLabel = traceStepLabel(s.step);
        return (
        <li
          key={`${s.at}-${i}-${s.kind}`}
          className={[
            "whitespace-pre-wrap break-words leading-relaxed",
            s.kind === "thinking" ? "text-zinc-500 italic" : "text-zinc-500",
            s.kind === "error" ? "text-red-400/90" : "",
            s.kind === "meta" ? "text-blue-400/80" : "",
            s.kind === "tool" && s.toolStatus === "completed" ? "text-zinc-600" : "",
            s.step === "hermes_draft" || s.step === "hermes_reasoning"
              ? "rounded border border-zinc-800/50 bg-zinc-900/30 px-2 py-1.5"
              : "",
          ].join(" ")}
        >
          <span className="mr-1.5 font-mono text-[10px] text-zinc-600">{stepIcon(s.kind)}</span>
          {draftLabel ? (
            <span className="mr-1.5 not-italic text-zinc-400">{draftLabel} ·</span>
          ) : null}
          {s.message}
          {s.kind === "tool" && s.toolStatus === "completed" ? (
            <span className="ml-1.5 text-[10px] text-zinc-600">（完成）</span>
          ) : null}
        </li>
        );
      })}
    </ul>
  );

  if (forceOpen) {
    return (
      <div className={panelClass} role="log" aria-live="polite">
        <div className="px-2.5 py-2 text-zinc-400">{header}</div>
        {list}
        {meta?.llm_model ? (
          <p className="border-t border-zinc-800/60 px-2.5 py-1.5 text-[11px] text-zinc-600">
            模型：{meta.llm_model}
          </p>
        ) : null}
      </div>
    );
  }

  return (
    <details className={panelClass} open={defaultOpen}>
      <summary className="cursor-pointer select-none px-2.5 py-2 text-zinc-400 hover:text-zinc-200">
        {header}
      </summary>
      {list}
      {meta?.llm_model ? (
        <p className="border-t border-zinc-800/60 px-2.5 py-1.5 text-[11px] text-zinc-600">
          模型：{meta.llm_model}
        </p>
      ) : null}
    </details>
  );
}
