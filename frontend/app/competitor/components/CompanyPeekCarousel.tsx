"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { CAROUSEL_AUTO_MS } from "../lib/carousel_timing";
import { CarouselDotsBar } from "./CarouselDotsBar";

export type PeekCarouselSlide = {
  id: string;
  title: string;
  content: ReactNode;
};

type Props = {
  slides: PeekCarouselSlide[];
  activeIndex: number;
  onActiveIndexChange: (index: number) => void;
  onUserNavigate?: () => void;
  onResume?: () => void;
  /** 含用户暂停或离焦 */
  paused?: boolean;
  /** 仅用户手动暂停（展示继续按钮） */
  userPaused?: boolean;
  autoMs?: number;
  initialDwellMs?: number;
  activated?: boolean;
  activationKey?: number;
  minHeight?: string;
};

const CENTER_RATIO = 0.84;
const PEEK_RATIO = (1 - CENTER_RATIO) / 2;
const PEEK_INNER_SCALE = CENTER_RATIO / PEEK_RATIO;

function PanelCard({
  slide,
  active,
  onClick,
  className = "",
  clipContent = false,
}: {
  slide: PeekCarouselSlide;
  active: boolean;
  onClick?: () => void;
  className?: string;
  clipContent?: boolean;
}) {
  const Tag = onClick ? "button" : "div";
  return (
    <Tag
      type={onClick ? "button" : undefined}
      onClick={onClick}
      className={
        "flex flex-col rounded-xl border bg-zinc-900/50 text-left transition-[opacity,box-shadow,border-color] duration-500 " +
        (clipContent ? "h-full min-h-0 " : "") +
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
      <div
        className={
          clipContent
            ? "min-h-0 flex-1 overflow-hidden p-3 sm:p-4"
            : "overflow-visible p-3 sm:p-4"
        }
      >
        {slide.content}
      </div>
    </Tag>
  );
}

/** 横向 peek 轮播：居中完整展示，左右与居中同高裁剪（无内滚动条） */
export function CompanyPeekCarousel({
  slides,
  activeIndex,
  onActiveIndexChange,
  onUserNavigate,
  onResume,
  paused = false,
  userPaused = false,
  autoMs = CAROUSEL_AUTO_MS,
  initialDwellMs = 1200,
  activated = true,
  activationKey = 0,
  minHeight = "min-h-[280px]",
}: Props) {
  const [autoReady, setAutoReady] = useState(initialDwellMs <= 0);
  const centerRef = useRef<HTMLDivElement>(null);
  const [centerPanelPx, setCenterPanelPx] = useState<number>();
  const count = slides.length;

  const pauseFromUser = useCallback(() => {
    onUserNavigate?.();
  }, [onUserNavigate]);

  const go = useCallback(
    (delta: number, fromUser = false) => {
      if (!count) return;
      if (fromUser) pauseFromUser();
      onActiveIndexChange((activeIndex + delta + count) % count);
    },
    [activeIndex, count, onActiveIndexChange, pauseFromUser],
  );

  useEffect(() => {
    if (!activated) {
      setAutoReady(false);
      return;
    }
    if (initialDwellMs <= 0) {
      setAutoReady(true);
      return;
    }
    setAutoReady(false);
    const timer = window.setTimeout(() => setAutoReady(true), initialDwellMs);
    return () => window.clearTimeout(timer);
  }, [initialDwellMs, count, activationKey, activated]);

  useEffect(() => {
    if (!autoMs || !autoReady || !activated || count <= 1 || paused) return;
    const timer = window.setInterval(() => {
      onActiveIndexChange((activeIndex + 1) % count);
    }, autoMs);
    return () => window.clearInterval(timer);
  }, [autoMs, autoReady, activated, count, paused, activeIndex, onActiveIndexChange]);

  const safeIndex = Math.min(Math.max(activeIndex, 0), count - 1);

  useEffect(() => {
    const el = centerRef.current;
    if (!el) return;
    const sync = () => setCenterPanelPx(el.offsetHeight);
    sync();
    const ro = new ResizeObserver(sync);
    ro.observe(el);
    return () => ro.disconnect();
  }, [safeIndex, slides, activated]);

  if (!count) return null;

  const prevIndex = (safeIndex - 1 + count) % count;
  const nextIndex = (safeIndex + 1) % count;
  const centerPct = CENTER_RATIO * 100;
  const peekPct = PEEK_RATIO * 100;
  const innerPct = PEEK_INNER_SCALE * 100;
  const peekClipStyle = centerPanelPx ? { height: centerPanelPx } : undefined;

  return (
    <div className={"relative flex flex-col " + minHeight}>
      <CarouselDotsBar
        slides={slides}
        activeIndex={safeIndex}
        onSelect={(i) => {
          pauseFromUser();
          onActiveIndexChange(i);
        }}
        onResume={onResume}
        showResume={Boolean(userPaused && activated && onResume)}
        className="pb-3"
      />

      <div
        className="grid gap-3 overflow-visible"
        style={{
          gridTemplateColumns: `${peekPct}% ${centerPct}% ${peekPct}%`,
          alignItems: "start",
        }}
      >
        <div className="relative z-0 overflow-hidden rounded-xl" style={peekClipStyle}>
          <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
            <div
              className="pointer-events-auto absolute top-0 bottom-0 right-0 overflow-hidden"
              style={{ width: `${innerPct}%` }}
            >
              <PanelCard
                slide={slides[prevIndex]!}
                active={false}
                onClick={() => go(-1, true)}
                className="h-full w-full"
                clipContent
              />
            </div>
          </div>
        </div>
        <div ref={centerRef} className="relative z-10 w-full overflow-visible">
          <PanelCard slide={slides[safeIndex]!} active className="w-full" />
        </div>
        <div className="relative z-0 overflow-hidden rounded-xl" style={peekClipStyle}>
          <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
            <div
              className="pointer-events-auto absolute top-0 bottom-0 left-0 overflow-hidden"
              style={{ width: `${innerPct}%` }}
            >
              <PanelCard
                slide={slides[nextIndex]!}
                active={false}
                onClick={() => go(1, true)}
                className="h-full w-full"
                clipContent
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
