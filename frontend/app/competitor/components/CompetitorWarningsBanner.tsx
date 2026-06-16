"use client";

type Props = {
  warnings: string[];
  isFixture?: boolean;
};

export function CompetitorWarningsBanner({ warnings, isFixture }: Props) {
  if (!isFixture && warnings.length === 0) return null;

  return (
    <div className="shrink-0 space-y-2 border-b border-zinc-800 bg-zinc-900/90 px-4 py-2 md:px-6">
      {isFixture ? (
        <p className="text-xs text-amber-400/90">
          当前为开发预览数据（未实际上传 Snapshot）；生产环境请由管理员在财务后台上传 MD 蓝本。
        </p>
      ) : null}
      {warnings.length > 0 ? (
        <details className="text-xs text-zinc-400">
          <summary className="cursor-pointer text-amber-400/90">
            解析告警（{warnings.length}）
          </summary>
          <ul className="mt-1 max-h-32 list-inside list-disc overflow-y-auto text-zinc-500">
            {warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}
