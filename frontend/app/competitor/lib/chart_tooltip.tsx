"use client";

import { formatDecimal2 } from "../lib/format";

export function CompetitorTooltip({  active,
  payload,
  label,
  unit,
}: {
  active?: boolean;
  payload?: { name: string; value: number; dataKey: string; color?: string }[];
  label?: string;
  unit?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border border-zinc-600 bg-zinc-900 px-3 py-2 shadow-lg">
      {label != null && <p className="mb-1.5 text-xs font-medium text-zinc-400">{label}</p>}
      <ul className="space-y-0.5 text-sm tabular-nums text-zinc-100">
        {payload.map((entry) => (
          <li key={entry.dataKey} className="flex items-center gap-2">
            {entry.color ? (
              <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: entry.color }} />
            ) : null}
            <span>
              {entry.name}: {formatDecimal2(entry.value)}
              {unit ?? ""}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
