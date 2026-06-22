"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from "react";
import { buildScaleEntries, NAV_SECTIONS } from "../lib/navigation";
import { collectSnapMetrics, collectSnapOffsets, resolveActiveSnap, resolveScrollEndTarget, snapOffsetTop } from "../lib/scroll_spy";

type Props = {
  activeSnapId: string;
  onNavigate: (id: string) => void;
  /** 自定义刻度条目；默认竞品财报九屏导航 */
  entries?: import("../lib/navigation").ScaleEntry[];
};

export function ProgressScale({ activeSnapId, onNavigate, entries: entriesProp }: Props) {
  const defaultEntries = useMemo(() => buildScaleEntries(), []);
  const entries = entriesProp ?? defaultEntries;
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  /** hover 优先；否则当前屏圆点 inline 展开文案 */
  const expandedId = hoveredId ?? activeSnapId;

  return (
    <nav
      className="hidden w-[min(94vw,984px)] shrink-0 sm:block"
      aria-label="章节进度"
      data-active-snap={activeSnapId}
      onMouseLeave={() => setHoveredId(null)}
    >
      <div className="ml-auto flex w-full items-center">
        {entries.map((entry) => {
          const isActive = activeSnapId === entry.snapId;
          const isMain = entry.kind === "main";
          const isExpanded = expandedId === entry.snapId;

          return (
            <button
              key={entry.snapId}
              type="button"
              data-testid={`snap-dot-${entry.snapId}`}
              data-active={isActive ? "true" : "false"}
              aria-label={entry.fullLabel}
              aria-current={isActive ? "true" : undefined}
              onMouseEnter={() => setHoveredId(entry.snapId)}
              onFocus={() => setHoveredId(entry.snapId)}
              onBlur={() => setHoveredId(null)}
              onClick={() => onNavigate(entry.snapId)}
              className={
                "group/dot relative flex h-8 items-center transition-all duration-300 ease-out " +
                (isExpanded
                  ? "z-10 min-w-0 flex-[3_1_0%] justify-start gap-1 overflow-visible"
                  : "min-w-[8px] flex-1 basis-0 justify-center overflow-hidden")
              }
            >
              <span className="flex shrink-0 items-center justify-center">
                <span
                  className={
                    "block rounded-full transition-all duration-300 ease-out " +
                    (isActive
                      ? isMain
                        ? "h-2.5 w-2.5 bg-blue-600 shadow-[0_0_10px_rgba(37,99,235,0.5)]"
                        : "h-2 w-2 bg-blue-400 shadow-[0_0_8px_rgba(96,165,250,0.45)]"
                      : isMain
                        ? "h-2 w-2 border border-zinc-600 bg-zinc-800 group-hover/dot:border-zinc-400"
                        : "h-1.5 w-1.5 bg-zinc-600 group-hover/dot:bg-zinc-400")
                  }
                />
              </span>
              <span
                className={
                  "leading-none transition-all duration-300 ease-out " +
                  (isExpanded ? "whitespace-nowrap text-[10px] opacity-100 sm:text-[11px]" : "max-w-0 overflow-hidden opacity-0") +
                  (isActive || isExpanded ? " font-medium text-blue-200" : " text-zinc-500")
                }
              >
                {entry.fullLabel}
              </span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}

export function useCompetitorScrollViewport(
  scrollRootRef: RefObject<HTMLElement | null>,
  enabled = true,
) {
  useEffect(() => {
    if (!enabled) return;
    const root = scrollRootRef.current;
    if (!root) return;

    const sync = () => {
      root.style.setProperty("--competitor-viewport-h", `${root.clientHeight}px`);
    };

    sync();
    const ro = new ResizeObserver(sync);
    ro.observe(root);
    window.addEventListener("resize", sync);

    return () => {
      ro.disconnect();
      window.removeEventListener("resize", sync);
    };
  }, [scrollRootRef, enabled]);
}

export function useSnapScrollObserver(
  snapIds: string[],
  scrollRootRef: RefObject<HTMLElement | null>,
  enabled = true,
) {
  const [activeSnapId, setActiveSnapId] = useState(snapIds[0] ?? "sec-01-a");
  const snapIdsRef = useRef(snapIds);
  snapIdsRef.current = snapIds;
  /** 点击刻度 smooth 滚动期间锁定高亮，避免 scroll 事件中途改回旧屏 */
  const navLockRef = useRef<string | null>(null);
  const lastScrollTopRef = useRef(0);
  /** 最近一次滚动手势：up = scrollTop 增大（内容上滚）；down = 回看上方 */
  const scrollDirectionRef = useRef<"up" | "down" | null>(null);

  useCompetitorScrollViewport(scrollRootRef, enabled);

  useEffect(() => {
    if (!enabled) return;
    const root = scrollRootRef.current;
    if (!root) return;

    lastScrollTopRef.current = root.scrollTop;

    const update = () => {
      const locked = navLockRef.current;
      if (locked) {
        root.dataset.activeSnap = locked;
        setActiveSnapId((prev) => (prev === locked ? prev : locked));
        return;
      }
      const ids = snapIdsRef.current;
      const offsets = collectSnapOffsets(root, ids);
      const next = resolveActiveSnap(ids, offsets, root.scrollTop);
      root.dataset.activeSnap = next;
      setActiveSnapId((prev) => (prev === next ? prev : next));
    };

    let raf = 0;
    const schedule = () => {
      if (raf) return;
      raf = window.requestAnimationFrame(() => {
        raf = 0;
        update();
      });
    };

    const applyScrollEndSnap = () => {
      if (navLockRef.current) return;
      const ids = snapIdsRef.current;
      const metrics = collectSnapMetrics(root, ids);
      const target = resolveScrollEndTarget(
        ids,
        metrics,
        root.scrollTop,
        root.clientHeight,
        scrollDirectionRef.current,
      );
      if (target.shouldSnap && Math.abs(target.scrollTop - root.scrollTop) > 6) {
        root.classList.add("competitor-snap-animating");
        root.scrollTo({ top: target.scrollTop, behavior: "smooth" });
        window.setTimeout(() => root.classList.remove("competitor-snap-animating"), 520);
      }
      root.dataset.activeSnap = target.activeId;
      setActiveSnapId((prev) => (prev === target.activeId ? prev : target.activeId));
      scrollDirectionRef.current = null;
    };

    let scrollEndTimer = 0;
    const scheduleScrollEndSnap = () => {
      if (navLockRef.current) return;
      const y = root.scrollTop;
      if (y > lastScrollTopRef.current + 1) scrollDirectionRef.current = "up";
      else if (y < lastScrollTopRef.current - 1) scrollDirectionRef.current = "down";
      lastScrollTopRef.current = y;
      if (scrollEndTimer) window.clearTimeout(scrollEndTimer);
      scrollEndTimer = window.setTimeout(() => {
        scrollEndTimer = 0;
        applyScrollEndSnap();
      }, 120);
    };

    update();
    root.addEventListener("scroll", schedule, { passive: true });
    root.addEventListener("scroll", scheduleScrollEndSnap, { passive: true });
    root.addEventListener("scrollend", applyScrollEndSnap);
    window.addEventListener("resize", schedule);

    const ro = new ResizeObserver(schedule);
    ro.observe(root);

    const mo = new MutationObserver(schedule);
    mo.observe(root, { childList: true, subtree: true });

    return () => {
      root.removeEventListener("scroll", schedule);
      root.removeEventListener("scroll", scheduleScrollEndSnap);
      root.removeEventListener("scrollend", applyScrollEndSnap);
      window.removeEventListener("resize", schedule);
      ro.disconnect();
      mo.disconnect();
      if (raf) window.cancelAnimationFrame(raf);
      if (scrollEndTimer) window.clearTimeout(scrollEndTimer);
    };
  }, [scrollRootRef, enabled]);

  const navigate = useCallback(
    (id: string, options?: { behavior?: ScrollBehavior }) => {
      const behavior = options?.behavior ?? "smooth";
      const root = scrollRootRef.current;
      const el =
        root?.querySelector<HTMLElement>(`[data-competitor-snap="${id}"]`) ??
        document.getElementById(id);
      if (!el || !root) {
        el?.scrollIntoView({ behavior, block: "start" });
        if (id) setActiveSnapId(id);
        return false;
      }
      const top = snapOffsetTop(el, root);
      navLockRef.current = id;
      setActiveSnapId(id);
      root.dataset.activeSnap = id;
      root.scrollTo({ top, behavior });
      const release = () => {
        navLockRef.current = null;
      };
      root.addEventListener("scrollend", release, { once: true });
      window.setTimeout(release, 900);
      return true;
    },
    [scrollRootRef],
  );

  const navigateRef = useRef(navigate);
  navigateRef.current = navigate;

  /** URL hash（如从纵向页返回 /competitor#sec-10-a）→ 定位到对应 snap；动态区块未挂载时重试 */
  useEffect(() => {
    if (!enabled) return;
    const hash = window.location.hash.replace(/^#/, "");
    if (!hash || !snapIds.includes(hash)) return;

    let cancelled = false;
    let timer = 0;
    let attempts = 0;

    const tryNavigate = () => {
      if (cancelled) return;
      attempts += 1;
      const ok = navigateRef.current(hash, { behavior: "auto" });
      if (ok || attempts >= 60) return;
      timer = window.setTimeout(tryNavigate, 50);
    };

    timer = window.setTimeout(tryNavigate, 80);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [enabled, snapIds]);

  return { activeSnapId, navigate };
}

/** @deprecated */
export const SECTION_NAV = NAV_SECTIONS.map((s) => ({
  id: s.id,
  label: s.id.replace("sec-", ""),
  title: s.title,
}));
