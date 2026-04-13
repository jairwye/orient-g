"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { getAuthHeaders } from "../../lib/auth";
import { useEquitySnapshotName } from "../../lib/equitySnapshot";
import { MermaidDiagram } from "../../components/MermaidDiagram";

type GraphNode = {
  id: string;
  name: string;
  entity_type: string;
  credit_code?: string | null;
  tags?: Record<string, any>;
  geo?: { province?: string | null; city?: string | null; reg_location?: string | null };
  industry?: string | null;
};

type GraphEdge = {
  id: string;
  from: string;
  to: string;
  hold_pct?: number | null;
  hold_pct_text?: string | null;
  source?: string | null;
};

type GraphResponse = {
  snapshot: { name: string };
  params: { direction: "up" | "down"; min_pct: number; max_depth: number; max_nodes: number };
  nodes: GraphNode[];
  edges: GraphEdge[];
  stats: { node_count: number; edge_count: number; depth_max: number; truncated: boolean; truncate_reason: string | null };
};

type PanoramaResponse = {
  snapshot: { name: string };
  params: { min_pct: number; max_depth: number; max_nodes: number };
  nodes: GraphNode[];
  edges: GraphEdge[];
  stats: { node_count: number; edge_count: number; depth_max: number; truncated: boolean; truncate_reason: string | null };
};

type TargetListItem = { entity_id: string; name: string; is_key: boolean };

function mergePanoramaFromOwnership(up: GraphResponse, down: GraphResponse): PanoramaResponse {
  const nodesById = new Map<string, GraphNode>();
  for (const n of down.nodes || []) nodesById.set(n.id, n);
  for (const n of up.nodes || []) nodesById.set(n.id, { ...(nodesById.get(n.id) as any), ...n });

  const edgesById = new Map<string, GraphEdge>();
  for (const e of down.edges || []) edgesById.set(e.id, e);
  for (const e of up.edges || []) edgesById.set(e.id, e);

  const truncated = Boolean(down.stats?.truncated) || Boolean(up.stats?.truncated);
  const truncate_reason = down.stats?.truncate_reason || up.stats?.truncate_reason || null;
  const depth_max = Math.max(Number(down.stats?.depth_max || 0), Number(up.stats?.depth_max || 0));

  return {
    snapshot: down.snapshot,
    params: { min_pct: down.params.min_pct, max_depth: down.params.max_depth, max_nodes: down.params.max_nodes },
    nodes: Array.from(nodesById.values()),
    edges: Array.from(edgesById.values()),
    stats: {
      node_count: nodesById.size,
      edge_count: edgesById.size,
      depth_max,
      truncated,
      truncate_reason,
    },
  };
}

export default function TargetDetailPage() {
  const params = useParams<{ id: string }>();
  const search = useSearchParams();
  const router = useRouter();

  const entityId = String(params?.id || "");
  const fromQs = search.get("snapshot_name")?.trim() ?? "";
  const { snapshotName, setSnapshotName } = useEquitySnapshotName(fromQs);
  const [direction, setDirection] = useState<"up" | "down">((search.get("direction") as any) === "up" ? "up" : "down");
  const [minPct, setMinPct] = useState(Number(search.get("min_pct") || 0));
  const [maxDepth, setMaxDepth] = useState(Number(search.get("max_depth") || 10));
  const [maxNodes, setMaxNodes] = useState(Number(search.get("max_nodes") || 5000));

  const [data, setData] = useState<GraphResponse | null>(null);
  const [panorama, setPanorama] = useState<PanoramaResponse | null>(null);
  const [viewMode, setViewMode] = useState<"panorama" | "single">("panorama");
  const [focusTargetPaths, setFocusTargetPaths] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [targetsList, setTargetsList] = useState<TargetListItem[]>([]);

  const qs = useMemo(() => {
    const u = new URLSearchParams();
    u.set("snapshot_name", snapshotName);
    u.set("target_entity_id", entityId);
    u.set("direction", direction);
    u.set("min_pct", String(minPct));
    u.set("max_depth", String(maxDepth));
    u.set("max_nodes", String(maxNodes));
    return u.toString();
  }, [snapshotName, entityId, direction, minPct, maxDepth, maxNodes]);

  useEffect(() => {
    if (!snapshotName.trim()) {
      setTargetsList([]);
      return;
    }
    let cancelled = false;
    fetch(`/api/equity/targets?snapshot_name=${encodeURIComponent(snapshotName)}`, {
      cache: "no-store",
      credentials: "include",
      headers: getAuthHeaders(),
    })
      .then(async (r) => {
        if (!r.ok) throw new Error(await r.text());
        return r.json() as Promise<{ items?: TargetListItem[] }>;
      })
      .then((d) => {
        if (!cancelled) setTargetsList(d.items ?? []);
      })
      .catch(() => {
        if (!cancelled) setTargetsList([]);
      });
    return () => {
      cancelled = true;
    };
  }, [snapshotName]);

  useEffect(() => {
    if (!entityId) return;
    if (!snapshotName.trim()) {
      setLoading(false);
      setData(null);
      setPanorama(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    const run = async () => {
      try {
        // 1) 先尝试后端全景接口；若失败则前端合并 up+down 两个子图
        const panoUrl =
          `/api/equity/graph/panorama` +
          `?snapshot_name=${encodeURIComponent(snapshotName)}` +
          `&target_entity_id=${encodeURIComponent(entityId)}` +
          `&min_pct=${encodeURIComponent(String(minPct))}` +
          `&max_depth=${encodeURIComponent(String(maxDepth))}` +
          `&max_nodes=${encodeURIComponent(String(maxNodes))}`;
        let pano: PanoramaResponse | null = null;
        try {
          const rp = await fetch(panoUrl, {
            cache: "no-store",
            credentials: "include",
            headers: getAuthHeaders(),
          });
          if (rp.ok) {
            pano = (await rp.json()) as PanoramaResponse;
          } else {
            throw new Error(await rp.text());
          }
        } catch (e) {
          // fallback: fetch both directions and merge on client
          const mk = (direction: "up" | "down") => {
            const u = new URLSearchParams();
            u.set("snapshot_name", snapshotName);
            u.set("target_entity_id", entityId);
            u.set("direction", direction);
            u.set("min_pct", String(minPct));
            u.set("max_depth", String(maxDepth));
            u.set("max_nodes", String(maxNodes));
            return `/api/equity/graph/ownership?${u.toString()}`;
          };
          const [ru, rd] = await Promise.all([
            fetch(mk("up"), { cache: "no-store", credentials: "include", headers: getAuthHeaders() }),
            fetch(mk("down"), { cache: "no-store", credentials: "include", headers: getAuthHeaders() }),
          ]);
          if (!ru.ok) throw new Error(await ru.text());
          if (!rd.ok) throw new Error(await rd.text());
          const up = (await ru.json()) as GraphResponse;
          const down = (await rd.json()) as GraphResponse;
          pano = mergePanoramaFromOwnership(up, down);
        }
        if (!cancelled) setPanorama(pano);

        // 2) 单向子图（用于列表预览/参数对照）
        const r = await fetch(`/api/equity/graph/ownership?${qs}`, {
          cache: "no-store",
          credentials: "include",
          headers: getAuthHeaders(),
        });
        if (!r.ok) throw new Error(await r.text());
        const d = (await r.json()) as GraphResponse;
        if (!cancelled) setData(d);
      } catch (e: any) {
        if (!cancelled) {
          setError(String(e?.message || e));
          setData(null);
          setPanorama(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    run();
    return () => {
      cancelled = true;
    };
  }, [entityId, qs, snapshotName, entityId, minPct, maxDepth, maxNodes]);

  useEffect(() => {
    // 对“非标的主体”的全景，默认聚焦到与标的相连的路径，避免“毛线球”看不清
    const me = panorama?.nodes?.find((n) => n.id === entityId);
    const isTarget = Boolean((me?.tags as any)?.is_target) || Boolean((me?.tags as any)?.is_key_target);
    if (!isTarget) setFocusTargetPaths(true);
  }, [panorama, entityId]);

  function buildFocusedSubgraph(p: PanoramaResponse, centerId: string) {
    const nodes = p.nodes || [];
    const edges = p.edges || [];
    const byId = new Map(nodes.map((n) => [n.id, n]));
    const isTarget = (n: GraphNode | undefined) => Boolean((n?.tags as any)?.is_target) || Boolean((n?.tags as any)?.is_key_target);
    const targetIds = nodes.filter((n) => isTarget(n)).map((n) => n.id);
    if (!targetIds.length) return { nodes, edges };

    // undirected adjacency (to find any shortest connection)
    const adj = new Map<string, string[]>();
    const pushAdj = (a: string, b: string) => {
      const arr = adj.get(a) || [];
      arr.push(b);
      adj.set(a, arr);
    };
    for (const e of edges) {
      pushAdj(e.from, e.to);
      pushAdj(e.to, e.from);
    }

    // BFS from center; keep prev to reconstruct paths to targets
    const prev = new Map<string, string>();
    const depth = new Map<string, number>();
    const q: string[] = [];
    q.push(centerId);
    depth.set(centerId, 0);
    let qi = 0;
    const MAX_BFS = 12000;
    while (qi < q.length && q.length < MAX_BFS) {
      const cur = q[qi++];
      const d = depth.get(cur) || 0;
      if (d >= 12) continue;
      for (const nb of adj.get(cur) || []) {
        if (depth.has(nb)) continue;
        depth.set(nb, d + 1);
        prev.set(nb, cur);
        q.push(nb);
      }
    }

    const keep = new Set<string>();
    keep.add(centerId);
    // reconstruct path for each target reachable
    for (const tid of targetIds) {
      if (!depth.has(tid)) continue;
      let cur: string | undefined = tid;
      let steps = 0;
      while (cur && steps++ < 50) {
        keep.add(cur);
        if (cur === centerId) break;
        cur = prev.get(cur);
      }
    }
    // add 1-hop neighbors around kept nodes for context (bounded)
    const extraLimit = 1600;
    for (const id of Array.from(keep)) {
      for (const nb of adj.get(id) || []) {
        keep.add(nb);
        if (keep.size >= extraLimit) break;
      }
      if (keep.size >= extraLimit) break;
    }

    const nodes2 = nodes.filter((n) => keep.has(n.id));
    const keepSet = new Set(nodes2.map((n) => n.id));
    const edges2 = edges.filter((e) => keepSet.has(e.from) && keepSet.has(e.to));
    return { nodes: nodes2, edges: edges2 };
  }

  const panoramaChart = useMemo(() => {
    if (!panorama) return "";
    const rawNodes = panorama.nodes || [];
    const rawEdges = panorama.edges || [];
    const focused = focusTargetPaths ? buildFocusedSubgraph(panorama, entityId) : { nodes: rawNodes, edges: rawEdges };
    const nodes = focused.nodes || [];
    const edges = focused.edges || [];
    const byId = new Map(nodes.map((n) => [n.id, n]));

    const safe = (s: string) => String(s || "").replaceAll("\"", "'");
    const labelOf = (n: GraphNode) => {
      const g = n.geo;
      let geo = "";
      if (g?.city) geo = g.province ? `${g.city}（${g.province}）` : g.city;
      else if (g?.province) geo = g.province;
      const isKey = Boolean((n.tags as any)?.is_key_target);
      const isTarget = Boolean((n.tags as any)?.is_target);
      const prefix = isKey ? "【标的★】" : isTarget ? "【标的】" : "";
      return `${prefix}${n.name}${geo ? `（${geo}）` : ""}`;
    };

    const lines: string[] = ["flowchart TB"];
    for (const n of nodes.slice(0, 1100)) {
      // mermaid id 不能含特殊字符
      const id = `N_${n.id.replaceAll("-", "_")}`;
      const isKey = Boolean((n.tags as any)?.is_key_target);
      const isTarget = Boolean((n.tags as any)?.is_target);
      const shape = isKey ? "{{" : isTarget ? "([" : "[";
      const close = isKey ? "}}" : isTarget ? "])" : "]";
      lines.push(`${id}${shape}\"${safe(labelOf(n))}\"${close}`);
    }
    const seen = new Set<string>();
    for (const e of edges.slice(0, 3200)) {
      const f = byId.get(e.from);
      const t = byId.get(e.to);
      if (!f || !t) continue;
      const fromId = `N_${e.from.replaceAll("-", "_")}`;
      const toId = `N_${e.to.replaceAll("-", "_")}`;
      const k = `${fromId}-->${toId}:${e.hold_pct_text || e.hold_pct || ""}`;
      if (seen.has(k)) continue;
      seen.add(k);
      const lbl = e.hold_pct_text || (e.hold_pct != null ? `${e.hold_pct}%` : "");
      lines.push(lbl ? `${fromId} -->|\"${safe(lbl)}\"| ${toId}` : `${fromId} --> ${toId}`);
    }
    if (panorama.stats?.truncated) {
      lines.push(`Note[\"已截断：${safe(panorama.stats.truncate_reason || "未知原因")}\" ]`);
    }
    // 与经营数据页图表「当期」一致的亮蓝底，突出本页标的公司（当前 entityId）
    const centerMermaidId = `N_${entityId.replaceAll("-", "_")}`;
    if (nodes.some((n) => n.id === entityId)) {
      lines.push("classDef equityTarget fill:#2563eb,stroke:#60a5fa,color:#ffffff");
      lines.push(`class ${centerMermaidId} equityTarget`);
    }
    return lines.join("\n");
  }, [panorama, focusTargetPaths, entityId]);

  // (旧 fetch 已替换为 panorama + ownership 的组合请求)

  const titleName = useMemo(() => {
    const n = data?.nodes?.find((x) => x.id === entityId);
    return n?.name || entityId;
  }, [data, entityId]);

  const targetOptions = useMemo(() => {
    const items = [...targetsList];
    if (entityId && !items.some((t) => t.entity_id === entityId)) {
      items.unshift({ entity_id: entityId, name: titleName || entityId, is_key: false });
    }
    return items;
  }, [targetsList, entityId, titleName]);

  function hrefForTarget(targetId: string) {
    const u = new URLSearchParams();
    u.set("snapshot_name", snapshotName);
    u.set("min_pct", String(minPct));
    u.set("max_depth", String(maxDepth));
    u.set("max_nodes", String(maxNodes));
    u.set("direction", direction);
    return `/targets/${encodeURIComponent(targetId)}?${u.toString()}`;
  }

  const seg = "rounded-md px-2.5 py-1.5 text-[11px] font-medium transition-colors";
  const segOn = "bg-zinc-100 text-zinc-900";
  const segOff = "bg-zinc-950 text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200";

  return (
    <div className="p-4 md:p-8">
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <h1 className="text-xl font-semibold tracking-tight text-zinc-100">公司全景：{titleName}</h1>
            <div className="mt-1 text-xs text-zinc-500">
              子图 nodes {data?.stats?.node_count ?? "—"} · edges {data?.stats?.edge_count ?? "—"}
              {snapshotName ? ` · 批次 ${snapshotName}` : ""}
            </div>
          </div>
          <Link
            href="/equity"
            className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-zinc-700/90 bg-zinc-900/80 px-3 py-2 text-xs font-medium text-zinc-300 transition-colors hover:border-zinc-600 hover:bg-zinc-800 hover:text-zinc-100"
          >
            <span className="text-zinc-500" aria-hidden>
              ←
            </span>
            股权全景
          </Link>
        </div>

        <div className="mb-4 rounded-xl border border-zinc-800/90 bg-gradient-to-b from-zinc-900/60 to-zinc-950/80 p-3 shadow-sm md:p-4">
          <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:gap-4">
            <div className="flex min-w-0 flex-1 flex-col gap-2.5 sm:flex-row sm:items-stretch sm:gap-3">
              <label className="flex min-w-0 flex-1 flex-col gap-1 sm:max-w-xs">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">数据批次</span>
                <input
                  value={snapshotName}
                  onChange={(e) => setSnapshotName(e.target.value)}
                  placeholder="snapshot 名称"
                  className="h-8 w-full rounded-lg border border-zinc-700/80 bg-zinc-950 px-2.5 font-mono text-xs text-zinc-100 placeholder:text-zinc-600 outline-none ring-zinc-600 focus:border-blue-500/60 focus:ring-1"
                />
              </label>
              <label className="flex min-w-0 flex-[1.4] flex-col gap-1">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">标的公司</span>
                <select
                  className="h-8 w-full min-w-0 cursor-pointer rounded-lg border border-zinc-700/80 bg-zinc-950 px-2 text-xs text-zinc-100 outline-none focus:border-blue-500/60 focus:ring-1"
                  value={snapshotName.trim() ? entityId : ""}
                  onChange={(e) => {
                    const next = e.target.value;
                    if (next && next !== entityId) router.push(hrefForTarget(next));
                  }}
                  disabled={!snapshotName.trim()}
                  title="切换为另一标的公司的全景架构图"
                >
                  {!snapshotName.trim() ? (
                    <option value="">请先填写批次</option>
                  ) : targetOptions.length === 0 ? (
                    <option value={entityId}>{titleName || entityId}</option>
                  ) : (
                    targetOptions.map((t) => (
                      <option key={t.entity_id} value={t.entity_id}>
                        {(t.is_key ? "★ " : "") + t.name}
                      </option>
                    ))
                  )}
                </select>
              </label>
            </div>
            <div className="flex flex-wrap items-center gap-2 border-t border-zinc-800/70 pt-3 xl:border-l xl:border-t-0 xl:pl-4 xl:pt-0">
              <span className="mr-0.5 text-[10px] font-semibold uppercase tracking-wider text-zinc-600">方向</span>
              <div className="inline-flex overflow-hidden rounded-lg border border-zinc-800 p-0.5">
                <button type="button" onClick={() => setDirection("up")} className={`${seg} ${direction === "up" ? segOn : segOff}`}>
                  上游
                </button>
                <button type="button" onClick={() => setDirection("down")} className={`${seg} ${direction === "down" ? segOn : segOff}`}>
                  下游
                </button>
              </div>
              <span className="ml-1 text-[10px] font-semibold uppercase tracking-wider text-zinc-600">视图</span>
              <div className="inline-flex overflow-hidden rounded-lg border border-zinc-800 p-0.5">
                <button type="button" onClick={() => setViewMode("panorama")} className={`${seg} ${viewMode === "panorama" ? segOn : segOff}`}>
                  全景
                </button>
                <button type="button" onClick={() => setViewMode("single")} className={`${seg} ${viewMode === "single" ? segOn : segOff}`}>
                  单向
                </button>
              </div>
              <span className="ml-1 text-[10px] font-semibold uppercase tracking-wider text-zinc-600">聚焦</span>
              <div className="inline-flex overflow-hidden rounded-lg border border-zinc-800 p-0.5">
                <button type="button" onClick={() => setFocusTargetPaths(true)} className={`${seg} ${focusTargetPaths ? segOn : segOff}`}>
                  连标路径
                </button>
                <button type="button" onClick={() => setFocusTargetPaths(false)} className={`${seg} ${!focusTargetPaths ? segOn : segOff}`}>
                  全量
                </button>
              </div>
            </div>
          </div>
          <div className="mt-3 flex flex-wrap items-end gap-x-4 gap-y-2 border-t border-zinc-800/50 pt-3">
            <label className="flex items-center gap-1.5">
              <span className="text-[10px] text-zinc-500">min_pct</span>
              <input
                type="number"
                step="0.05"
                min="0"
                max="1"
                value={minPct}
                onChange={(e) => setMinPct(Number(e.target.value))}
                className="h-8 w-20 rounded-lg border border-zinc-800 bg-zinc-950 px-2 text-xs text-zinc-100 outline-none focus:border-zinc-600"
              />
            </label>
            <label className="flex items-center gap-1.5">
              <span className="text-[10px] text-zinc-500">depth</span>
              <input
                type="number"
                min="1"
                max="10"
                value={maxDepth}
                onChange={(e) => setMaxDepth(Number(e.target.value))}
                className="h-8 w-16 rounded-lg border border-zinc-800 bg-zinc-950 px-2 text-xs text-zinc-100 outline-none focus:border-zinc-600"
              />
            </label>
            <label className="flex items-center gap-1.5">
              <span className="text-[10px] text-zinc-500">nodes</span>
              <input
                type="number"
                min="50"
                max="5000"
                value={maxNodes}
                onChange={(e) => setMaxNodes(Number(e.target.value))}
                className="h-8 w-20 rounded-lg border border-zinc-800 bg-zinc-950 px-2 text-xs text-zinc-100 outline-none focus:border-zinc-600"
              />
            </label>
          </div>
        </div>

        {data?.stats?.truncated && (
          <div className="mb-4 rounded-lg border border-amber-900/40 bg-amber-950/30 p-3 text-sm text-amber-200">
            已截断：{data.stats.truncate_reason || "未知原因"}。可尝试提高 `max_nodes/max_depth` 或收紧 `min_pct`。
          </div>
        )}

        {loading && <div className="text-sm text-zinc-400">加载中…</div>}
        {error && (
          <div className="rounded-md border border-red-900/40 bg-red-950/40 p-3 text-sm text-red-200">
            请求失败：{error}
          </div>
        )}

        {!loading && !error && viewMode === "panorama" && panorama && (
          <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-4">
            <div className="mb-2 text-sm font-medium text-zinc-200">股权架构全景图（上游 + 下游）</div>
            <p className="mb-3 text-xs text-zinc-500">
              标记说明：<span className="text-zinc-200">★</span> 为标的公司（30 家），<span className="text-zinc-200">•</span> 为目标清单中的其它公司。
              本页公司在图中以亮蓝底高亮，与经营数据页图表「当期」同色。
              全景接口对上游、下游共用同一「depth」参数（见下方 depth，默认 10），不是「上 4 层、下 10 层」这种分别配置。
            </p>
            <MermaidDiagram chart={panoramaChart} id={`equity-panorama-${entityId}-${snapshotName}`} />
          </div>
        )}
        {!loading && !error && viewMode === "panorama" && !panorama && (
          <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-4 text-sm text-zinc-300">
            未能生成全景图谱。你可以切换到“单向预览”，或稍后重试（常见原因：接口未重启、风控导致数据缺失、或超大图谱被截断）。
          </div>
        )}

        {!loading && !error && viewMode === "single" && data && (
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-4">
              <div className="mb-2 text-sm font-medium text-zinc-200">快速预览（列表）</div>
              <div className="max-h-[520px] overflow-auto">
                <div className="text-xs text-zinc-400">节点</div>
                <ul className="mt-1 space-y-1">
                  {data.nodes.slice(0, 80).map((n) => (
                    <li key={n.id} className="truncate text-xs text-zinc-300">
                      {n.name} <span className="text-zinc-500">({n.entity_type})</span>
                    </li>
                  ))}
                </ul>
                {data.nodes.length > 80 && <div className="mt-2 text-xs text-zinc-500">仅展示前 80 个节点</div>}
                <div className="mt-4 text-xs text-zinc-400">边</div>
                <ul className="mt-1 space-y-1">
                  {data.edges.slice(0, 80).map((e) => (
                    <li key={e.id} className="truncate text-xs text-zinc-300">
                      {e.from} → {e.to}{" "}
                      <span className="text-zinc-500">{e.hold_pct_text || (e.hold_pct != null ? `${e.hold_pct}%` : "")}</span>
                    </li>
                  ))}
                </ul>
                {data.edges.length > 80 && <div className="mt-2 text-xs text-zinc-500">仅展示前 80 条边</div>}
              </div>
            </div>

            <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-4">
              <div className="mb-2 text-sm font-medium text-zinc-200">导出</div>
              <p className="text-xs text-zinc-500">导出当前参数下的子图复现包（JSON）。</p>
              <a
                href={`/api/equity/export/subgraph?${qs}`}
                className="mt-3 inline-flex rounded-md bg-zinc-100 px-3 py-2 text-xs font-medium text-zinc-900 hover:bg-white"
              >
                下载子图复现包
              </a>
              <div className="mt-6 text-xs text-zinc-400">批次 CSV 下载</div>
              <div className="mt-2 flex flex-wrap gap-2">
                <a
                  href={`/api/equity/export/csv?type=entities&snapshot_name=${encodeURIComponent(snapshotName)}`}
                  className="rounded-md border border-zinc-800 bg-zinc-900 px-3 py-2 text-xs text-zinc-200 hover:bg-zinc-800"
                >
                  entities.csv
                </a>
                <a
                  href={`/api/equity/export/csv?type=equity_edges&snapshot_name=${encodeURIComponent(snapshotName)}`}
                  className="rounded-md border border-zinc-800 bg-zinc-900 px-3 py-2 text-xs text-zinc-200 hover:bg-zinc-800"
                >
                  equity_edges.csv
                </a>
                <a
                  href={`/api/equity/export/csv?type=targets&snapshot_name=${encodeURIComponent(snapshotName)}`}
                  className="rounded-md border border-zinc-800 bg-zinc-900 px-3 py-2 text-xs text-zinc-200 hover:bg-zinc-800"
                >
                  targets.csv
                </a>
              </div>
            </div>
          </div>
        )}
    </div>
  );
}

