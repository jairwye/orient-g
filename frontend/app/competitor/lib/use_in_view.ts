"use client";

import { useEffect, useRef, useState } from "react";

/** 元素进入视口时返回 true（可配置是否仅首次） */
export function useInView<T extends HTMLElement>(
  opts?: { threshold?: number; rootMargin?: string; once?: boolean },
) {
  const ref = useRef<T>(null);
  const [inView, setInView] = useState(false);
  const threshold = opts?.threshold ?? 0.35;
  const once = opts?.once ?? false;

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setInView(true);
        } else if (!once) {
          setInView(false);
        }
      },
      { threshold, rootMargin: opts?.rootMargin },
    );

    io.observe(el);
    return () => io.disconnect();
  }, [threshold, once, opts?.rootMargin]);

  return { ref, inView };
}
