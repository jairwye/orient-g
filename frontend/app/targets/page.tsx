"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { getAuthHeaders } from "../lib/auth";

type TargetItem = {
  id: string;
  entity_id: string;
  name: string;
  credit_code: string | null;
  alias: string | null;
  is_key: boolean;
};

type TargetsResponse = {
  snapshot: { name: string };
  items: TargetItem[];
};

const DEFAULT_SNAPSHOT = "2026-04-08_run1";

export default function TargetsPage() {
  const [snapshotName, setSnapshotName] = useState(DEFAULT_SNAPSHOT);
  const [q, setQ] = useState("");
  const [data, setData] = useState<TargetsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetch(`/api/equity/targets?snapshot_name=${encodeURIComponent(snapshotName)}`, {
      cache: "no-store",
      credentials: "include",
      headers: getAuthHeaders(),
    })
      .then(async (r) => {
        if (!r.ok) throw new Error(await r.text());
        return (await r.json()) as TargetsResponse;
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

  const items = data?.items || [];
  const filtered = useMemo(() => {
    const qq = q.trim();
    if (!qq) return items;
    return items.filter((x) => x.name.includes(qq) || (x.credit_code || "").includes(qq) || (x.alias || "").includes(qq));
  }, [items, q]);

  return (
    <div className="p-6 md:p-8">
        <div className="mb-6 flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-zinc-100">股权全景</h1>
            <p className="mt-1 text-sm text-zinc-500">目标公司列表（按 snapshot 展示），点击进入公司全景图谱。</p>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <div className="flex items-center gap-2">
              <span className="text-xs text-zinc-400">snapshot</span>
              <input
                value={snapshotName}
                onChange={(e) => setSnapshotName(e.target.value)}
                className="h-9 w-52 rounded-md border border-zinc-800 bg-zinc-950 px-3 text-sm text-zinc-100 outline-none focus:border-zinc-700"
                placeholder="2026-04-08_run1"
              />
            </div>
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              className="h-9 w-64 rounded-md border border-zinc-800 bg-zinc-950 px-3 text-sm text-zinc-100 outline-none focus:border-zinc-700"
              placeholder="搜索公司名/信用代码/别名"
            />
          </div>
        </div>

        {loading && <div className="text-sm text-zinc-400">加载中…</div>}
        {error && (
          <div className="rounded-md border border-red-900/40 bg-red-950/40 p-3 text-sm text-red-200">
            请求失败：{error}
          </div>
        )}

        {!loading && !error && (
          <div className="overflow-hidden rounded-lg border border-zinc-800">
            <div className="grid grid-cols-12 bg-zinc-900/60 px-4 py-2 text-xs text-zinc-400">
              <div className="col-span-5">公司</div>
              <div className="col-span-3">信用代码</div>
              <div className="col-span-2">别名</div>
              <div className="col-span-2 text-right">操作</div>
            </div>
            <div className="divide-y divide-zinc-800 bg-zinc-950">
              {filtered.map((it) => (
                <div key={it.id} className="grid grid-cols-12 items-center px-4 py-3">
                  <div className="col-span-5">
                    <div className="flex items-center gap-2">
                      {it.is_key && <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-200">重点</span>}
                      <div className="truncate text-sm text-zinc-100">{it.name}</div>
                    </div>
                  </div>
                  <div className="col-span-3 truncate text-xs text-zinc-400">{it.credit_code || "—"}</div>
                  <div className="col-span-2 truncate text-xs text-zinc-400">{it.alias || "—"}</div>
                  <div className="col-span-2 flex justify-end">
                    <Link
                      href={`/targets/${encodeURIComponent(it.entity_id)}?snapshot_name=${encodeURIComponent(snapshotName)}`}
                      className="rounded-md bg-zinc-100 px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-white"
                    >
                      查看全景
                    </Link>
                  </div>
                </div>
              ))}
              {filtered.length === 0 && <div className="px-4 py-6 text-sm text-zinc-500">无匹配结果</div>}
            </div>
          </div>
        )}
    </div>
  );
}

