"use client";

/** Hermes / LLM reasoning 流式片段（展示在助手气泡内，非折叠到执行过程底部）。 */

export default function AgentReasoningPanel({
  text,
  streaming = false,
}: {
  text?: string;
  streaming?: boolean;
}) {
  const body = (text || "").trim();
  if (!body && !streaming) return null;

  return (
    <details
      className="mb-2 w-full rounded-lg border border-zinc-700/60 bg-zinc-950/60 text-xs"
      open
    >
      <summary className="cursor-pointer select-none px-2.5 py-2 text-zinc-400 hover:text-zinc-200">
        推理过程
        {streaming ? (
          <span className="ml-2 animate-pulse text-[#2563eb]/90">生成中…</span>
        ) : null}
      </summary>
      <div
        className="max-h-56 overflow-y-auto whitespace-pre-wrap break-words border-t border-zinc-800/60 px-2.5 py-2 font-mono text-[11px] leading-relaxed text-zinc-500"
        role="log"
        aria-live="polite"
      >
        {body || (streaming ? "…" : "")}
      </div>
    </details>
  );
}
