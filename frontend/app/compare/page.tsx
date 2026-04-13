"use client";

import { useEffect, useMemo, useState } from "react";
import { getAuthHeaders } from "../lib/auth";
import { useEquitySnapshotName } from "../lib/equitySnapshot";

type TargetItem = { id: string; entity_id: string; name: string };
type TargetsResponse = { snapshot: { name: string }; items: TargetItem[] };

type CompareResponse = {
  snapshot: { name: string };
  params: { min_pct: number; max_depth: number; max_nodes: number };
  a: { entity_id: string; name: string };
  b: { entity_id: string; name: string };
  overlap: { common_shareholders: { entity_id: string; name: string }[] };
  diff_stats: {
    a_node_count: number;
    b_node_count: number;
    a_overseas_ratio: number;
    b_overseas_ratio: number;
    a_truncated: boolean;
    b_truncated: boolean;
  };
};

export default function ComparePage() {
  const { snapshotName, setSnapshotName } = useEquitySnapshotName("");
  const [targets, setTargets] = useState<TargetItem[]>([]);
  const [a, setA] = useState<string>("");
  const [b, setB] = useState<string>("");
  const [minPct, setMinPct] = useState(0.2);
  const [maxDepth, setMaxDepth] = useState(3);
  const [maxNodes, setMaxNodes] = useState(500);

  const [data, setData] = useState<CompareResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!snapshotName.trim()) {
      setTargets([]);
      return () => {
        cancelled = true;
      };
    }
    fetch(`/api/equity/targets?snapshot_name=${encodeURIComponent(snapshotName)}`, {
      cache: "no-store",
      credentials: "include",
      headers: getAuthHeaders(),
    })
      .then((r) => r.json())
      .then((d: TargetsResponse) => {
        if (cancelled) return;
        const items = d?.items || [];
        setTargets(items);
        if (!a && items[0]) setA(items[0].entity_id);
        if (!b && items[1]) setB(items[1].entity_id);
      })
      .catch(() => {
        if (cancelled) return;
        setTargets([]);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [snapshotName]);

  const canCompare = a && b && a !== b;

  const runCompare = () => {
    if (!canCompare) return;
    setLoading(true);
    setError(null);
    setData(null);
    const qs = new URLSearchParams();
    qs.set("snapshot_name", snapshotName);
    qs.set("entity_id_a", a);
    qs.set("entity_id_b", b);
    qs.set("min_pct", String(minPct));
    qs.set("max_depth", String(maxDepth));
    qs.set("max_nodes", String(maxNodes));
    fetch(`/api/equity/analysis/compare?${qs.toString()}`, {
      cache: "no-store",
      credentials: "include",
      headers: getAuthHeaders(),
    })
      .then(async (r) => {
        if (!r.ok) throw new Error(await r.text());
        return (await r.json()) as CompareResponse;
      })
      .then((d) => setData(d))
      .catch((e) => setError(String(e?.message || e)))
      .finally(() => setLoading(false));
  };

  const aName = useMemo(() => targets.find((x) => x.entity_id === a)?.name || a, [targets, a]);
  const bName = useMemo(() => targets.find((x) => x.entity_id === b)?.name || b, [targets, b]);

  return (
    <div className="p-6 md:p-8">
        <div className="mb-6">
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-100">公司对比</h1>
          <p className="mt-1 text-sm text-zinc-500">选择两家公司，对比共同股东与结构指标（MVP）。</p>
        </div>

        <div className="mb-4 grid gap-3 rounded-lg border border-zinc-800 bg-zinc-900/40 p-4 lg:grid-cols-4">
          <div className="flex items-center gap-2">
            <span className="text-xs text-zinc-400">snapshot</span>
            <input
              value={snapshotName}
              onChange={(e) => setSnapshotName(e.target.value)}
              className="h-9 w-full rounded-md border border-zinc-800 bg-zinc-950 px-3 text-sm text-zinc-100 outline-none focus:border-zinc-700"
            />
          </div>
          <div>
            <div className="mb-1 text-[10px] text-zinc-500">公司 A</div>
            <select
              value={a}
              onChange={(e) => setA(e.target.value)}
              className="h-9 w-full rounded-md border border-zinc-800 bg-zinc-950 px-2 text-sm text-zinc-100 outline-none focus:border-zinc-700"
            >
              <option value="" disabled>
                请选择
              </option>
              {targets.map((t) => (
                <option key={t.entity_id} value={t.entity_id}>
                  {t.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <div className="mb-1 text-[10px] text-zinc-500">公司 B</div>
            <select
              value={b}
              onChange={(e) => setB(e.target.value)}
              className="h-9 w-full rounded-md border border-zinc-800 bg-zinc-950 px-2 text-sm text-zinc-100 outline-none focus:border-zinc-700"
            >
              <option value="" disabled>
                请选择
              </option>
              {targets.map((t) => (
                <option key={t.entity_id} value={t.entity_id}>
                  {t.name}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-end gap-2">
            <button
              type="button"
              disabled={!canCompare || loading}
              onClick={runCompare}
              className={
                "h-9 w-full rounded-md px-3 text-sm font-medium " +
                (canCompare ? "bg-zinc-100 text-zinc-900 hover:bg-white" : "bg-zinc-800 text-zinc-500")
              }
            >
              {loading ? "对比中…" : "开始对比"}
            </button>
          </div>
        </div>

        <div className="mb-4 grid grid-cols-3 gap-2 rounded-lg border border-zinc-800 bg-zinc-950 p-4 lg:grid-cols-6">
          <div>
            <div className="mb-1 text-[10px] text-zinc-500">min_pct</div>
            <input
              type="number"
              step="0.05"
              min="0"
              max="1"
              value={minPct}
              onChange={(e) => setMinPct(Number(e.target.value))}
              className="h-9 w-full rounded-md border border-zinc-800 bg-zinc-950 px-2 text-sm text-zinc-100 outline-none focus:border-zinc-700"
            />
          </div>
          <div>
            <div className="mb-1 text-[10px] text-zinc-500">max_depth</div>
            <input
              type="number"
              min="1"
              max="10"
              value={maxDepth}
              onChange={(e) => setMaxDepth(Number(e.target.value))}
              className="h-9 w-full rounded-md border border-zinc-800 bg-zinc-950 px-2 text-sm text-zinc-100 outline-none focus:border-zinc-700"
            />
          </div>
          <div>
            <div className="mb-1 text-[10px] text-zinc-500">max_nodes</div>
            <input
              type="number"
              min="50"
              max="5000"
              value={maxNodes}
              onChange={(e) => setMaxNodes(Number(e.target.value))}
              className="h-9 w-full rounded-md border border-zinc-800 bg-zinc-950 px-2 text-sm text-zinc-100 outline-none focus:border-zinc-700"
            />
          </div>
        </div>

        {error && (
          <div className="rounded-md border border-red-900/40 bg-red-950/40 p-3 text-sm text-red-200">
            请求失败：{error}
          </div>
        )}

        {data && (
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-4">
              <div className="mb-2 text-sm font-medium text-zinc-200">
                指标对比：{aName} vs {bName}
              </div>
              <div className="space-y-2 text-sm text-zinc-300">
                <div className="flex justify-between">
                  <span className="text-zinc-400">节点数</span>
                  <span>
                    {data.diff_stats.a_node_count} / {data.diff_stats.b_node_count}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-400">境外占比</span>
                  <span>
                    {(data.diff_stats.a_overseas_ratio * 100).toFixed(1)}% / {(data.diff_stats.b_overseas_ratio * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-400">截断</span>
                  <span>
                    {data.diff_stats.a_truncated ? "是" : "否"} / {data.diff_stats.b_truncated ? "是" : "否"}
                  </span>
                </div>
              </div>
            </div>

            <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-4">
              <div className="mb-2 text-sm font-medium text-zinc-200">共同股东（Top 50）</div>
              <ul className="max-h-[420px] overflow-auto space-y-1 text-xs text-zinc-300">
                {data.overlap.common_shareholders.map((x) => (
                  <li key={x.entity_id} className="truncate">
                    {x.name}
                  </li>
                ))}
                {data.overlap.common_shareholders.length === 0 && <li className="text-zinc-500">暂无</li>}
              </ul>
            </div>
          </div>
        )}
    </div>
  );
}

