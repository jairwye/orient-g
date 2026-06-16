"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";

export type ChartCarouselSlide = {
  id: string;
  title: string;
  content: ReactNode;
};

type Props = {
  slides: ChartCarouselSlide[];
  autoMs?: number;
  height?: string;
  /** Recharts 绘图区像素高度（避免 flex 链上 height:100% 塌缩为 0） */
  chartHeightPx?: number;
  /** 挂载后延迟多久再开始自动轮播（毫秒） */
  autoStartDelayMs?: number;
  hideArrows?: boolean;
};

/** 中间主图占比；两侧各 peek 露出邻图 */
const CENTER_RATIO = 0.84;
const PEEK_RATIO = (1 - CENTER_RATIO) / 2;
/** peek 列内 slide 宽度 = center / peek，使邻图与主图同比例 */
const PEEK_INNER_SCALE = CENTER_RATIO / PEEK_RATIO;

function SlideCard({
  slide,
  active,
  onClick,
  className = "",
  chartHeightPx,
}: {
  slide: ChartCarouselSlide;
  active: boolean;
  onClick?: () => void;
  className?: string;
  chartHeightPx: number;
}) {
  const Tag = onClick ? "button" : "div";
  return (
    <Tag
      type={onClick ? "button" : undefined}
      onClick={onClick}
      className={
        "flex h-full min-h-0 flex-col rounded-xl border bg-zinc-900/50 text-left transition-[opacity,box-shadow,border-color] duration-500 " +
        (active
          ? "border-zinc-600/80 opacity-100 shadow-lg"
          : "border-zinc-800/50 opacity-55 hover:opacity-75") +
        " " +
        className
      }
      aria-label={slide.title}
      aria-current={active ? "true" : undefined}
    >
      <div className="shrink-0 border-b border-zinc-800/80 px-4 py-2.5">
        <p className="truncate text-sm font-medium text-zinc-200">{slide.title}</p>
      </div>
      <div className="min-h-0 flex-1 p-3 sm:p-4">
        <div className="w-full" style={{ height: chartHeightPx }}>
          {slide.content}
        </div>
      </div>
    </Tag>
  );
}

/**
 * 无限循环轮播：当前图完整居中，左右始终露出上一张 / 下一张边缘（取模）。
 */
export function ChartCarousel({
  slides,
  autoMs = 8000,
  height = "h-[min(580px,64vh)]",
  chartHeightPx = 420,
  autoStartDelayMs = 0,
  hideArrows = true,
}: Props) {
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  const [autoReady, setAutoReady] = useState(autoStartDelayMs <= 0);
  const count = slides.length;

  const go = useCallback(
    (delta: number) => {
      if (!count) return;
      setIndex((i) => (i + delta + count) % count);
    },
    [count],
  );

  useEffect(() => {
    if (autoStartDelayMs <= 0) {
      setAutoReady(true);
      return;
    }
    setAutoReady(false);
    const timer = window.setTimeout(() => setAutoReady(true), autoStartDelayMs);
    return () => window.clearTimeout(timer);
  }, [autoStartDelayMs, count]);

  useEffect(() => {
    if (!autoMs || !autoReady || count <= 1 || paused) return;
    const timer = window.setInterval(() => go(1), autoMs);
    return () => window.clearInterval(timer);
  }, [autoMs, autoReady, count, paused, go]);

  if (!count) return null;

  const prevIndex = (index - 1 + count) % count;
  const nextIndex = (index + 1) % count;
  const centerPct = CENTER_RATIO * 100;
  const peekPct = PEEK_RATIO * 100;
  const innerPct = PEEK_INNER_SCALE * 100;

  return (
    <div
      className={"relative flex flex-col overflow-hidden " + height}
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
    >
      <div
        className="grid min-h-0 flex-1 gap-3 overflow-hidden"
        style={{
          gridTemplateColumns: `${peekPct}% ${centerPct}% ${peekPct}%`,
          gridTemplateRows: "minmax(0, 1fr)",
        }}
      >
        {/* 左侧：上一张的右缘 */}
        <div className="pointer-events-none relative z-0 h-full min-h-0 overflow-hidden rounded-xl">
          <div
            className="pointer-events-auto absolute top-0 bottom-0 right-0"
            style={{ width: `${innerPct}%` }}
          >
            <SlideCard
              slide={slides[prevIndex]}
              active={false}
              onClick={() => go(-1)}
              className="h-full w-full"
              chartHeightPx={chartHeightPx}
            />
          </div>
        </div>

        {/* 中间：当前完整图 */}
        <div className="relative z-10 flex h-full min-h-0 flex-col overflow-hidden">
          <SlideCard slide={slides[index]} active className="h-full" chartHeightPx={chartHeightPx} />
        </div>

        {/* 右侧：下一张的左缘 */}
        <div className="pointer-events-none relative z-0 h-full min-h-0 overflow-hidden rounded-xl">
          <div
            className="pointer-events-auto absolute top-0 bottom-0 left-0"
            style={{ width: `${innerPct}%` }}
          >
            <SlideCard
              slide={slides[nextIndex]}
              active={false}
              onClick={() => go(1)}
              className="h-full w-full"
              chartHeightPx={chartHeightPx}
            />
          </div>
        </div>
      </div>

      {count > 1 ? (
        <div className="flex shrink-0 items-center justify-center gap-3 py-3">
          {!hideArrows ? (
            <button
              type="button"
              aria-label="上一图"
              onClick={() => go(-1)}
              className="rounded-md border border-zinc-700/80 px-2 py-1 text-xs text-zinc-400 hover:text-zinc-200"
            >
              上一张
            </button>
          ) : null}
          <div className="flex gap-1.5">
            {slides.map((slide, i) => (
              <button
                key={slide.id}
                type="button"
                aria-label={`切换到 ${slide.title}`}
                onClick={() => setIndex(i)}
                className={
                  "h-1.5 rounded-full transition-all " +
                  (i === index ? "w-5 bg-blue-500" : "w-1.5 bg-zinc-600 hover:bg-zinc-500")
                }
              />
            ))}
          </div>
          {!hideArrows ? (
            <button
              type="button"
              aria-label="下一图"
              onClick={() => go(1)}
              className="rounded-md border border-zinc-700/80 px-2 py-1 text-xs text-zinc-400 hover:text-zinc-200"
            >
              下一张
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
