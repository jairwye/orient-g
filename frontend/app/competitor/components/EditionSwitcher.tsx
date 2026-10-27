"use client";

import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";
import { useRouter } from "next/navigation";
import type { CompetitorEdition } from "../lib/types";
import { competitorEditionHref, competitorHomeHref } from "../lib/navigation";

type Props = {
  editions: CompetitorEdition[];
  /** 当前页展示的期次；null/undefined = current 路由 */
  activeEditionId: string | null;
  currentEditionId: string | null;
};

/** uploaded_at 优先，否则 edition_id 数字友好降序；新→旧 */
function sortEditionsNewestFirst(editions: CompetitorEdition[]): CompetitorEdition[] {
  return [...editions].sort((a, b) => {
    const ta = a.uploaded_at ? Date.parse(a.uploaded_at) : NaN;
    const tb = b.uploaded_at ? Date.parse(b.uploaded_at) : NaN;
    const aOk = !Number.isNaN(ta);
    const bOk = !Number.isNaN(tb);
    if (aOk && bOk && ta !== tb) return tb - ta;
    if (aOk && !bOk) return -1;
    if (!aOk && bOk) return 1;
    return b.edition_id.localeCompare(a.edition_id, undefined, { numeric: true });
  });
}

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      aria-hidden
      viewBox="0 0 12 12"
      className={
        "h-3 w-3 shrink-0 self-center text-zinc-500 transition-transform duration-200 " +
        (open ? "rotate-180" : "")
      }
    >
      <path
        fill="currentColor"
        d="M2.2 4.2a.75.75 0 0 1 1.06 0L6 6.94l2.74-2.74a.75.75 0 1 1 1.06 1.06l-3.27 3.27a.75.75 0 0 1-1.06 0L2.2 5.26a.75.75 0 0 1 0-1.06z"
      />
    </svg>
  );
}

type MenuPanelProps = {
  id: string;
  editions: CompetitorEdition[];
  resolvedActive: string;
  pending: boolean;
  onSelect: (editionId: string) => void;
};

/** Ghost 触发钮共用的下拉面板；菜单紧贴触发钮 */
function EditionMenuPanel({
  id,
  editions,
  resolvedActive,
  pending,
  onSelect,
}: MenuPanelProps) {
  return (
    <ul
      id={id}
      role="listbox"
      aria-label="选择财报期次"
      className={
        "absolute left-0 top-full z-40 w-max min-w-[max(100%,11rem)] max-w-[16rem] " +
        "overflow-hidden rounded-md border border-zinc-800 bg-zinc-900 py-1 " +
        "shadow-xl shadow-black/40"
      }
    >
      {editions.map((ed) => {
        const active = ed.edition_id === resolvedActive;
        return (
          <li key={ed.edition_id} role="presentation">
            <button
              type="button"
              role="option"
              aria-selected={active}
              title={ed.edition_id}
              disabled={pending}
              onClick={() => onSelect(ed.edition_id)}
              className={
                "flex w-full items-center border-l-2 px-3 py-1.5 text-left text-xs " +
                "transition-colors disabled:opacity-50 " +
                (active
                  ? "border-l-[#2563eb] bg-zinc-800/70 text-zinc-100"
                  : "border-l-transparent text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-200")
              }
            >
              <span className="min-w-0 flex-1 truncate">{ed.period_label}</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

/** 页头期次切换：Ghost 文字触发 + listbox */
export function EditionSwitcher({
  editions,
  activeEditionId,
  currentEditionId,
}: Props) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const listboxId = useId();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  const sorted = useMemo(() => sortEditionsNewestFirst(editions), [editions]);

  const resolvedActive =
    activeEditionId ||
    currentEditionId ||
    sorted.find((e) => e.is_current)?.edition_id ||
    sorted[0]?.edition_id ||
    "";

  const activeEd = sorted.find((e) => e.edition_id === resolvedActive) ?? sorted[0];
  const periodLabel = activeEd?.period_label ?? "期次";

  // 路由变更后复位 pending（同壳层内 /e/[id] ↔ /e/[id] 组件不卸载）
  useEffect(() => {
    setPending(false);
  }, [activeEditionId, resolvedActive]);

  const navigateTo = useCallback(
    (id: string) => {
      if (!id || pending || id === resolvedActive) {
        setOpen(false);
        return;
      }
      setOpen(false);
      setPending(true);
      if (id === currentEditionId) {
        router.push(competitorHomeHref());
      } else {
        router.push(competitorEditionHref(id));
      }
    },
    [pending, resolvedActive, currentEditionId, router],
  );

  useEffect(() => {
    if (!open) return;
    const onDoc = (ev: MouseEvent) => {
      if (!rootRef.current?.contains(ev.target as Node)) setOpen(false);
    };
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (sorted.length <= 1) return null;

  return (
    <div ref={rootRef} className="relative flex max-w-[14rem] shrink-0 items-baseline">
      <button
        type="button"
        aria-label="选择财报期次"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listboxId}
        disabled={pending}
        title={activeEd?.edition_id}
        onClick={() => setOpen(!open)}
        className={
          "inline-flex max-w-full items-baseline gap-1 bg-transparent px-0 py-0 " +
          "text-sm font-normal leading-5 transition-colors hover:text-zinc-300 " +
          "focus-visible:outline focus-visible:outline-2 " +
          "focus-visible:outline-offset-2 focus-visible:outline-[#2563eb] " +
          "disabled:opacity-50 " +
          (open ? "text-zinc-300" : "text-zinc-500")
        }
      >
        <span className="truncate">{periodLabel}</span>
        <Chevron open={open} />
      </button>

      {open ? (
        <EditionMenuPanel
          id={listboxId}
          editions={sorted}
          resolvedActive={resolvedActive}
          pending={pending}
          onSelect={navigateTo}
        />
      ) : null}
    </div>
  );
}
