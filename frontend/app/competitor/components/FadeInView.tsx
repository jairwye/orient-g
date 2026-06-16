"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

const SCROLL_ROOT_SELECTOR = '[data-testid="competitor-scroll-root"]';

function findScrollRoot(el: HTMLElement): HTMLElement | null {
  return el.closest(SCROLL_ROOT_SELECTOR) as HTMLElement | null;
}

function isInScrollView(el: HTMLElement, root: HTMLElement | null): boolean {
  const elRect = el.getBoundingClientRect();
  if (!root) {
    const vh = window.innerHeight || document.documentElement.clientHeight;
    return elRect.top < vh * 0.92 && elRect.bottom > vh * 0.06;
  }
  const rootRect = root.getBoundingClientRect();
  return elRect.bottom > rootRect.top + 8 && elRect.top < rootRect.bottom - 8;
}

type Props = {
  children: ReactNode;
  className?: string;
  delayMs?: number;
  /** 禁用动效，首帧即显示（数据卡等不宜 invisible 占位） */
  immediate?: boolean;
};

export function FadeInView({ children, className = "", delayMs = 0, immediate = false }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(immediate);

  useEffect(() => {
    if (immediate) return;
    const el = ref.current;
    if (!el) return;

    const reveal = () => setVisible(true);
    const root = findScrollRoot(el);

    if (isInScrollView(el, root)) {
      reveal();
      return;
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          reveal();
          observer.disconnect();
        }
      },
      { threshold: 0.06, root, rootMargin: "0px" },
    );
    observer.observe(el);

    const fallback = window.setTimeout(() => {
      if (isInScrollView(el, findScrollRoot(el))) reveal();
    }, 480);

    return () => {
      observer.disconnect();
      window.clearTimeout(fallback);
    };
  }, [immediate]);

  return (
    <div
      ref={ref}
      className={
        (immediate ? "" : "competitor-fade-in ") +
        (visible || immediate ? "competitor-fade-in--visible " : "") +
        className
      }
      style={delayMs && !immediate ? { transitionDelay: `${delayMs}ms` } : undefined}
    >
      {children}
    </div>
  );
}
