"use client";

import { useCompetitorScroll } from "./scroll_context";

/** 当前 snap 是否为滚动焦点（与顶部刻度 / ProgressScale 一致） */
export function useSnapFocused(snapId: string): boolean {
  const { activeSnapId } = useCompetitorScroll();
  return activeSnapId === snapId;
}
