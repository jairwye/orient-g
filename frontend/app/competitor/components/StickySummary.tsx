import type { ReactNode } from "react";

/** 本节首张汇总表吸顶；滚出本节（父级 snap）后松开。滚动容器为 .competitor-scroll。 */
const STICKY_CLASS =
  "sticky top-0 z-20 bg-zinc-950 pb-2 shadow-[0_14px_22px_-16px_rgba(0,0,0,0.9)]";

export function StickySummary({
  active,
  children,
}: {
  /** 下方仍有明细可滚时才吸顶，避免单表空吸。 */
  active: boolean;
  children: ReactNode;
}) {
  return <div className={active ? STICKY_CLASS : undefined}>{children}</div>;
}
