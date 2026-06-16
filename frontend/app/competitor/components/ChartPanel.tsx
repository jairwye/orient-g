import type { ReactNode } from "react";
import { FadeInView } from "./FadeInView";

type Props = {
  title: string;
  children: ReactNode;
  className?: string;
  height?: string;
  delayMs?: number;
};

export function ChartPanel({
  title,
  children,
  className = "",
  height = "h-[min(560px,74vh)]",
  delayMs = 0,
}: Props) {
  return (
    <FadeInView delayMs={delayMs} immediate>
      <div
        className={
          "flex flex-col rounded-lg border border-zinc-800/80 bg-zinc-900/45 p-3 sm:p-4 md:p-5 " +
          height +
          " " +
          className
        }
      >
        <h3 className="mb-2 shrink-0 text-sm font-medium text-zinc-300">{title}</h3>
        <div className="min-h-0 flex-1">{children}</div>
      </div>
    </FadeInView>
  );
}
