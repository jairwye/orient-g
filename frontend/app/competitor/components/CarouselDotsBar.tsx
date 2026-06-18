"use client";

type SlideRef = { id: string; title: string };

type Props = {
  slides: SlideRef[];
  activeIndex: number;
  onSelect: (index: number) => void;
  onResume?: () => void;
  /** 用户手动暂停时为 true，展示播放按钮 */
  showResume?: boolean;
  size?: "sm" | "md";
  className?: string;
};

function PlayIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" fill="currentColor" className={className} aria-hidden>
      <path d="M4 2.5v11L14 8 4 2.5z" />
    </svg>
  );
}

/** 轮播刻度 + 右侧播放小钮（与刻度行同高对齐） */
export function CarouselDotsBar({
  slides,
  activeIndex,
  onSelect,
  onResume,
  showResume = false,
  size = "sm",
  className = "",
}: Props) {
  if (slides.length <= 1) return null;

  const activeDot = size === "md" ? "h-3 w-9 bg-blue-500" : "h-2.5 w-8 bg-blue-500";
  const idleDot = size === "md" ? "h-3 w-3 bg-zinc-600 hover:bg-zinc-400" : "h-2.5 w-2.5 bg-zinc-600 hover:bg-zinc-400";
  const barH = size === "md" ? "h-3" : "h-2.5";
  const playBtn = size === "md" ? "h-6 w-6" : "h-5 w-5";
  const playIcon = size === "md" ? "h-2.5 w-2.5" : "h-2 w-2";

  return (
    <div className={"flex shrink-0 items-center justify-center gap-2.5 " + className}>
      <div className={"flex items-center gap-2.5 " + barH}>
        {slides.map((slide, i) => (
          <button
            key={slide.id}
            type="button"
            aria-label={`切换到 ${slide.title}`}
            onClick={() => onSelect(i)}
            className={"rounded-full transition-all " + (i === activeIndex ? activeDot : idleDot)}
          />
        ))}
      </div>
      {showResume ? (
        <button
          type="button"
          aria-label="继续轮播"
          title="继续轮播"
          onClick={onResume}
          className={
            "inline-flex shrink-0 items-center justify-center rounded-full border border-blue-500/55 bg-blue-950/45 text-blue-300 transition-colors hover:border-blue-400/70 hover:bg-blue-900/55 hover:text-blue-100 " +
            playBtn
          }
        >
          <PlayIcon className={playIcon} />
        </button>
      ) : null}
    </div>
  );
}
