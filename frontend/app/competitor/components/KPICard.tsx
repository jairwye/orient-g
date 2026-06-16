import { FadeInView } from "./FadeInView";

type Props = {
  label: string;
  value: string;
  hint?: string;
  delayMs?: number;
  prominent?: boolean;
};

export function KPICard({ label, value, hint, delayMs = 0, prominent = false }: Props) {
  return (
    <FadeInView delayMs={delayMs}>
      <div
        className={
          "relative rounded-lg border border-zinc-800 bg-zinc-900/50 " +
          (prominent ? "min-h-[168px] p-6" : "min-h-[140px] p-5")
        }
      >
        <p className="text-sm font-medium text-zinc-400">{label}</p>
        <p
          className={
            "mt-2 font-bold tabular-nums tracking-tight text-zinc-100 " +
            (prominent ? "text-4xl md:text-5xl" : "text-3xl md:text-4xl")
          }
        >
          {value}
        </p>
        {hint ? <p className="mt-2 text-xs leading-relaxed text-zinc-500">{hint}</p> : null}
      </div>
    </FadeInView>
  );
}
