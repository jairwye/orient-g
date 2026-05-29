import { Bot } from "lucide-react";
import { BUSINESS_CHART_COLORS } from "../lib/business_chart_colors";

const accent = BUSINESS_CHART_COLORS.current;

export default function AiAvatar({
  status,
  compact = false,
}: {
  status?: "idle" | "thinking" | "typing";
  /** 对话流内仅显示图标，便于与侧栏标题顶对齐 */
  compact?: boolean;
}) {
  const statusText =
    status === "thinking" ? "思考中…" : status === "typing" ? "正在输入…" : null;
  return (
    <div className={compact ? "flex items-start" : "flex items-center gap-2"}>
      <div
        className="relative flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-zinc-800"
        style={{ backgroundColor: `${accent}22`, color: accent }}
      >
        <Bot size={15} strokeWidth={2} />
        {status === "thinking" && (
          <span className="absolute -right-0.5 -top-0.5 flex h-2.5 w-2.5">
            <span
              className="absolute inline-flex h-full w-full animate-ping rounded-full opacity-75"
              style={{ backgroundColor: accent }}
            />
            <span className="relative inline-flex h-2.5 w-2.5 rounded-full" style={{ backgroundColor: accent }} />
          </span>
        )}
      </div>
      {!compact ? (
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-medium text-zinc-300">AI 助手</span>
          {statusText ? (
            <span className="text-[11px] animate-pulse" style={{ color: `${accent}cc` }}>
              {statusText}
            </span>
          ) : null}
        </div>
      ) : statusText ? (
        <span className="sr-only">{statusText}</span>
      ) : null}
    </div>
  );
}
