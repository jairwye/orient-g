import { Bot } from "lucide-react";

export default function AiAvatar({ status }: { status?: "idle" | "thinking" | "typing" }) {
  const statusText =
    status === "thinking" ? "思考中…" : status === "typing" ? "正在输入…" : null;
  return (
    <div className="flex items-center gap-2">
      <div className="relative flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-emerald-500/15 text-emerald-400">
        <Bot size={15} strokeWidth={2} />
        {status === "thinking" && (
          <span className="absolute -right-0.5 -top-0.5 flex h-2.5 w-2.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-400" />
          </span>
        )}
      </div>
      <div className="flex items-center gap-1.5">
        <span className="text-xs font-medium text-zinc-300">AI 助手</span>
        {statusText ? (
          <span className="text-[11px] text-emerald-400/80 animate-pulse">{statusText}</span>
        ) : null}
      </div>
    </div>
  );
}
