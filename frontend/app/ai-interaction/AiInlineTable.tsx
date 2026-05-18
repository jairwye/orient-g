export default function AiInlineTable({ spec }: { spec: { columns: string[]; rows: string[][] } }) {
  const columns = spec.columns || [];
  const rows = spec.rows || [];
  if (!columns.length) return null;
  return (
    <div className="mt-2 overflow-x-auto rounded border border-zinc-700">
      <table className="w-full min-w-[240px] text-left text-xs">
        <thead>
          <tr className="border-b border-zinc-700 bg-zinc-900/70">
            {columns.map((c, i) => (
              <th key={`${c}-${i}`} className="px-2 py-1.5 text-zinc-300">
                {c || `列${i + 1}`}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => (
            <tr key={ri} className="border-b border-zinc-800 last:border-b-0">
              {columns.map((c, ci) => (
                <td key={`${c}-${ci}`} className="px-2 py-1 text-zinc-400">
                  {row[ci] ?? ""}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
