"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { CAROUSEL_AUTO_MS } from "../lib/carousel_timing";
import { CarouselDotsBar } from "./CarouselDotsBar";

export type ChartCarouselSlide = {
  id: string;
  title: string;
  content: ReactNode;
};

type Props = {
  slides: ChartCarouselSlide[];
  autoMs?: number;
  height?: string;
  chartHeightPx?: number;
  autoStartDelayMs?: number;
  dotsPosition?: "top" | "bottom";
  activated?: boolean;
  activationKey?: number;
};

const CENTER_RATIO = 0.84;
const PEEK_RATIO = (1 - CENTER_RATIO) / 2;
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
      <div className="shrink-0 border-b border-zinc-800/80 px-4 py-2">
        <p className="truncate text-sm font-medium text-zinc-200">{slide.title}</p>
      </div>
      <div className="min-h-0 flex-1 overflow-hidden p-2.5 sm:p-3">
        <div className="w-full" style={{ height: chartHeightPx }}>
          {slide.content}
        </div>
      </div>
    </Tag>
  );
}

export function ChartCarousel({
  slides,
  autoMs = CAROUSEL_AUTO_MS,
  height = "h-[min(580px,64vh)]",
  chartHeightPx = 420,
  autoStartDelayMs = 0,
  dotsPosition = "bottom",
  activated = true,
  activationKey = 0,
}: Props) {
  const [index, setIndex] = useState(0);
  const [userPaused, setUserPaused] = useState(false);
  const [autoReady, setAutoReady] = useState(autoStartDelayMs <= 0);
  const count = slides.length;

  const pauseFromUser = useCallback(() => setUserPaused(true), []);

  const go = useCallback(
    (delta: number, fromUser = false) => {
      if (!count) return;
      if (fromUser) pauseFromUser();
      setIndex((i) => (i + delta + count) % count);
    },
    [count, pauseFromUser],
  );

  useEffect(() => {
    if (!activated) {
      setAutoReady(false);
      return;
    }
    if (autoStartDelayMs <= 0) {
      setAutoReady(true);
      return;
    }
    setAutoReady(false);
    const timer = window.setTimeout(() => setAutoReady(true), autoStartDelayMs);
    return () => window.clearTimeout(timer);
  }, [autoStartDelayMs, count, activationKey, activated]);

  useEffect(() => {
    if (!autoMs || !autoReady || !activated || count <= 1 || userPaused) return;
    const timer = window.setInterval(() => go(1), autoMs);
    return () => window.clearInterval(timer);
  }, [autoMs, autoReady, activated, count, userPaused, go]);

  if (!count) return null;

  const prevIndex = (index - 1 + count) % count;
  const nextIndex = (index + 1) % count;
  const centerPct = CENTER_RATIO * 100;
  const peekPct = PEEK_RATIO * 100;
  const innerPct = PEEK_INNER_SCALE * 100;

  const dots = (
    <CarouselDotsBar
      slides={slides}
      activeIndex={index}
      size="md"
      onSelect={(i) => {
        pauseFromUser();
        setIndex(i);
      }}
      onResume={() => setUserPaused(false)}
      showResume={userPaused && activated}
      className="py-3"
    />
  );

  const grid = (
    <div
      className="grid min-h-0 flex-1 gap-3 overflow-hidden"
      style={{
        gridTemplateColumns: `${peekPct}% ${centerPct}% ${peekPct}%`,
        gridTemplateRows: "minmax(0, 1fr)",
      }}
    >
      <div className="pointer-events-none relative z-0 h-full min-h-0 overflow-hidden rounded-xl">
        <div
          className="pointer-events-auto absolute top-0 bottom-0 right-0 overflow-hidden"
          style={{ width: `${innerPct}%` }}
        >
          <SlideCard
            slide={slides[prevIndex]!}
            active={false}
            onClick={() => go(-1, true)}
            className="h-full w-full"
            chartHeightPx={chartHeightPx}
          />
        </div>
      </div>
      <div className="relative z-10 flex h-full min-h-0 flex-col overflow-hidden">
        <SlideCard slide={slides[index]!} active className="h-full" chartHeightPx={chartHeightPx} />
      </div>
      <div className="pointer-events-none relative z-0 h-full min-h-0 overflow-hidden rounded-xl">
        <div
          className="pointer-events-auto absolute top-0 bottom-0 left-0 overflow-hidden"
          style={{ width: `${innerPct}%` }}
        >
          <SlideCard
            slide={slides[nextIndex]!}
            active={false}
            onClick={() => go(1, true)}
            className="h-full w-full"
            chartHeightPx={chartHeightPx}
          />
        </div>
      </div>
    </div>
  );

  return (
    <div className={"relative flex flex-col overflow-hidden " + height}>
      {dotsPosition === "top" ? dots : null}
      {grid}
      {dotsPosition === "bottom" ? dots : null}
    </div>
  );
}
