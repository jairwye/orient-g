import type { ReactNode } from "react";

/** 单屏 scroll-snap 页：占满滚动区高度 */
export function SnapPanel({
  id,
  children,
  dense = false,
}: {
  id: string;
  children: ReactNode;
  /** 内容较多时自顶排列，避免垂直居中裁切 */
  dense?: boolean;
}) {
  return (
    <div
      id={id}
      data-competitor-snap={id}
      className={
        "competitor-snap-panel snap-start flex min-h-[var(--competitor-viewport-h,100%)] flex-col " +
        (dense ? "justify-start" : "justify-center")
      }
    >
      {children}
    </div>
  );
}

export function SnapContent({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={"w-full px-6 py-3 md:px-8 md:py-4 " + className}>{children}</div>
  );
}
