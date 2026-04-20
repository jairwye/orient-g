"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getAuthHeaders } from "../lib/auth";

type BigPdfTaskRow = {
  task_id: string;
  status?: string;
  stage?: string;
  progress?: number;
  detail?: string | null;
};

function isActive(status?: string) {
  const s = (status || "").toLowerCase();
  return s !== "done" && s !== "failed";
}

export function KbInProgressBanner() {
  const [items, setItems] = useState<BigPdfTaskRow[]>([]);

  useEffect(() => {
    let stop = false;
    async function load() {
      try {
        const res = await fetch("/api/knowledge/bigpdf/tasks?limit=12", {
          credentials: "include",
          headers: getAuthHeaders(),
        });
        const data = (await res.json().catch(() => ({}))) as { items?: BigPdfTaskRow[] };
        if (!stop && res.ok && Array.isArray(data.items)) setItems(data.items);
      } catch {
        // ignore
      }
    }
    load();
    const t = setInterval(load, 5000);
    return () => {
      stop = true;
      clearInterval(t);
    };
  }, []);

  const active = items.filter((x) => isActive(x.status));
  if (!active.length) return null;

  return (
    <div className="rounded-lg border border-amber-900/40 bg-amber-950/30 px-3 py-2 text-xs text-amber-100/90">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-medium text-amber-200">大 PDF 处理中</span>
        <Link href="/utils/pdf-knowledge" className="text-amber-300/90 underline hover:text-amber-100">
          打开工具页
        </Link>
      </div>
      <ul className="mt-1 space-y-1">
        {active.slice(0, 4).map((t) => (
          <li key={t.task_id} className="flex flex-wrap items-center justify-between gap-2 font-mono text-[11px] text-amber-100/80">
            <span className="truncate">{t.task_id}</span>
            <span className="shrink-0 text-amber-200/80">
              {t.stage || t.status || "?"} · {Math.max(0, Math.min(100, t.progress || 0))}%
            </span>
            <Link
              href={`/utils/pdf-knowledge?task_id=${encodeURIComponent(t.task_id)}`}
              className="shrink-0 text-amber-300/90 underline hover:text-amber-100"
            >
              查看
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
