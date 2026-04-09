"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { getAuthHeaders } from "../lib/auth";

type SummaryResponse = {
  snapshot: { name: string };
  distributions: {
    province: Record<string, number>;
    entity_type: Record<string, number>;
  };
};

const DEFAULT_SNAPSHOT = "2026-04-08_run1";

export default function AnalysisDashboardPage() {
  const [snapshotName, setSnapshotName] = useState(DEFAULT_SNAPSHOT);
  const [data, setData] = useState<SummaryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetch(`/api/equity/analysis/summary?snapshot_name=${encodeURIComponent(snapshotName)}`, {
      cache: "no-store",
      credentials: "include",
      headers: getAuthHeaders(),
    })
      .then(async (r) => {
        if (!r.ok) throw new Error(await r.text());
        return (await r.json()) as SummaryResponse;
      })
      .then((d) => {
        if (cancelled) return;
        setData(d);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(String(e?.message || e));
        setData(null);
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [snapshotName]);

  const topProvinces = useMemo(() => {
    const p = data?.distributions?.province || {};
    return Object.entries(p).sort((a, b) => b[1] - a[1]).slice(0, 12);
  }, [data]);

  const topTypes = useMemo(() => {
    const t = data?.distributions?.entity_type || {};
    return Object.entries(t).sort((a, b) => b[1] - a[1]);
  }, [data]);

  return (
    <div className="p-6 md:p-8">
        <div className="mb-6 flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-zinc-100">股权全景工作台</h1>
            <p className="mt-1 text-sm text-zinc-500">地区/类型分布与一键跳转到目标公司列表。</p>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-zinc-400">snapshot</span>
            <input
              value={snapshotName}
              onChange={(e) => setSnapshotName(e.target.value)}
              className="h-9 w-52 rounded-md border border-zinc-800 bg-zinc-950 px-3 text-sm text-zinc-100 outline-none focus:border-zinc-700"
              placeholder="2026-04-08_run1"
            />
          </div>
        </div>

        {loading && <div className="text-sm text-zinc-400">加载中…</div>}
        {error && (
          <div className="rounded-md border border-red-900/40 bg-red-950/40 p-3 text-sm text-red-200">
            请求失败：{error}
          </div>
        )}

        {!loading && !error && data && (
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-4">
              <div className="mb-2 text-sm font-medium text-zinc-200">地区分布（Top 12）</div>
              <div className="space-y-2">
                {topProvinces.map(([k, v]) => (
                  <div key={k} className="flex items-center gap-3">
                    <div className="w-20 truncate text-xs text-zinc-300">{k}</div>
                    <div className="flex-1">
                      <div className="h-2 overflow-hidden rounded bg-zinc-900">
                        <div
                          className="h-2 bg-zinc-200"
                          style={{ width: `${Math.min(100, (v / Math.max(1, topProvinces[0]?.[1] || 1)) * 100)}%` }}
                        />
                      </div>
                    </div>
                    <div className="w-12 text-right text-xs text-zinc-400">{v}</div>
                    <Link
                      href={`/targets?snapshot_name=${encodeURIComponent(snapshotName)}#province=${encodeURIComponent(k)}`}
                      className="text-xs text-zinc-200 underline underline-offset-2 hover:text-white"
                    >
                      查看
                    </Link>
                  </div>
                ))}
                {topProvinces.length === 0 && <div className="text-sm text-zinc-500">暂无数据</div>}
              </div>
            </div>

            <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-4">
              <div className="mb-2 text-sm font-medium text-zinc-200">主体类型分布</div>
              <div className="space-y-2">
                {topTypes.map(([k, v]) => (
                  <div key={k} className="flex items-center justify-between">
                    <div className="text-xs text-zinc-300">{k}</div>
                    <div className="text-xs text-zinc-400">{v}</div>
                  </div>
                ))}
                {topTypes.length === 0 && <div className="text-sm text-zinc-500">暂无数据</div>}
              </div>

              <div className="mt-4">
                <Link
                  href={`/targets?snapshot_name=${encodeURIComponent(snapshotName)}`}
                  className="inline-flex rounded-md bg-zinc-100 px-3 py-2 text-xs font-medium text-zinc-900 hover:bg-white"
                >
                  打开目标公司列表
                </Link>
              </div>
            </div>
          </div>
        )}
    </div>
  );
}

