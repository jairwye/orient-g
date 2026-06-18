"use client";

import { useEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import { carouselHeightFromTableBody, peekCarouselHeightPx } from "./peek_carousel_height";

/** 测量多份明细表自然高度，取最大值用于轮播固定高度（完整展示、无内滚动） */
export function usePeekCarouselHeight(
  measurePanels: ReactNode[],
  maxRowCount: number,
): { heightPx: number; measureRef: RefObject<HTMLDivElement> } {
  const ref = useRef<HTMLDivElement>(null);
  const fallback = peekCarouselHeightPx(maxRowCount);
  const [heightPx, setHeightPx] = useState(fallback);

  useEffect(() => {
    setHeightPx(fallback);
  }, [fallback]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const sync = () => {
      let maxBody = 0;
      for (const child of el.children) {
        maxBody = Math.max(maxBody, (child as HTMLElement).offsetHeight);
      }
      if (maxBody > 0) {
        setHeightPx(carouselHeightFromTableBody(maxBody));
      }
    };

    sync();
    const ro = new ResizeObserver(sync);
    ro.observe(el);
    for (const child of el.children) {
      ro.observe(child);
    }
    return () => ro.disconnect();
  }, [measurePanels]);

  return { heightPx, measureRef: ref };
}
