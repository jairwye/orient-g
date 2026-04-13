"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { getAuthHeaders } from "../lib/auth";
import { useEquitySnapshotName } from "../lib/equitySnapshot";

type EntityGeoItem = {
  entity_id: string;
  name: string;
  entity_type?: string;
  credit_code?: string | null;
  geo?: { province?: string | null; city?: string | null };
  is_target?: boolean;
  is_key_target?: boolean;
};

type EntitiesGeoResponse = { snapshot: { name: string }; items: EntityGeoItem[] };

type TargetListItem = { entity_id: string; name: string; is_key: boolean };
type TargetsListResponse = { snapshot: { name: string }; items: TargetListItem[] };

type PanoramaGraphNode = {
  id: string;
  name: string;
  geo?: { province?: string | null; city?: string | null; reg_location?: string | null };
  tags?: { is_target?: boolean; is_key_target?: boolean };
};

type PanoramaResponse = {
  snapshot: { name: string };
  nodes: PanoramaGraphNode[];
  stats: { node_count: number; edge_count: number; truncated?: boolean };
};

function hashToUnit(str: string) {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) h = Math.imul(h ^ str.charCodeAt(i), 16777619);
  return ((h >>> 0) % 10_000) / 10_000;
}

function jitter(entityId: string) {
  const a = hashToUnit(entityId + "a");
  const b = hashToUnit(entityId + "b");
  return { dx: (a - 0.5) * 10, dy: (b - 0.5) * 10 };
}

type ChinaGeoJSON = {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    properties?: Record<string, any>;
    geometry:
      | { type: "Polygon"; coordinates: number[][][] }
      | { type: "MultiPolygon"; coordinates: number[][][][] };
  }>;
};

type LocationNode = {
  adcode: number;
  name: string;
  center?: [number, number]; // [lng, lat]
  centroid?: [number, number];
  level?: string;
  children?: LocationNode[];
};

type LocationsRoot = Record<string, { children: LocationNode[] }>;

function stripCnSuffix(s: string) {
  return String(s || "")
    .trim()
    .replaceAll(/(省|市|自治区|壮族自治区|回族自治区|维吾尔自治区|特别行政区)$/g, "")
    .trim();
}

function toRad(d: number) {
  return (d * Math.PI) / 180;
}

function mercatorProject(lng: number, lat: number) {
  // WebMercator（简化），返回归一化坐标 [0..1]
  const x = (lng + 180) / 360;
  const y = (1 - Math.log(Math.tan(Math.PI / 4 + toRad(lat) / 2)) / Math.PI) / 2;
  return { x, y };
}

type MapPoint = {
  entity_id: string;
  name: string;
  province: string;
  city: string;
  is_target: boolean;
  is_key_target: boolean;
  lng: number;
  lat: number;
};

function buildMapPointsFromGeoRows(
  rows: Array<{
    id: string;
    name: string;
    province: string;
    city: string;
    is_target: boolean;
    is_key_target: boolean;
  }>,
  locRoot: LocationsRoot | null,
): MapPoint[] {
  if (!locRoot) return [];

  const nodes: LocationNode[] = (locRoot["100000"]?.children || []) as LocationNode[];
  const byName = new Map<string, LocationNode>();
  const stack = [...nodes];
  while (stack.length) {
    const n = stack.pop();
    if (!n) break;
    const k = stripCnSuffix(n.name);
    if (k) byName.set(k, n);
    if (Array.isArray(n.children)) {
      for (const c of n.children) stack.push(c);
    }
  }

  return rows
    .map((t) => {
      const provRaw = (t.province || "").trim();
      const cityRaw = (t.city || "").trim();
      const provKey = stripCnSuffix(provRaw);
      const cityKey = stripCnSuffix(cityRaw);

      const cityNode = cityKey ? byName.get(cityKey) : null;
      const provNode = provKey ? byName.get(provKey) : null;
      const center = (cityNode?.center || cityNode?.centroid || provNode?.center || provNode?.centroid) as
        | [number, number]
        | undefined;
      if (!center) return null;
      const [lng, lat] = center;

      return {
        entity_id: t.id,
        name: t.name,
        province: provRaw || "未知",
        city: cityRaw || "未知",
        is_target: t.is_target,
        is_key_target: t.is_key_target,
        lng,
        lat,
      };
    })
    .filter((x): x is MapPoint => Boolean(x));
}

/** 中国地图默认缩放（在 1.35 基础上再放大约 10% → 1.485） */
const EQUITY_MAP_DEFAULT_SCALE = 1.485;

export default function EquityEntryPage() {
  const { snapshotName, setSnapshotName } = useEquitySnapshotName("");
  const router = useRouter();
  const [entities, setEntities] = useState<EntityGeoItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [targets, setTargets] = useState<TargetListItem[]>([]);
  const [heatmapFocusTargetId, setHeatmapFocusTargetId] = useState("");
  const [panoramaNodes, setPanoramaNodes] = useState<PanoramaGraphNode[]>([]);
  const [panoramaLoading, setPanoramaLoading] = useState(false);
  const [panoramaError, setPanoramaError] = useState<string | null>(null);

  const [mapScale, setMapScale] = useState(EQUITY_MAP_DEFAULT_SCALE);
  const [mapTx, setMapTx] = useState(0);
  const [mapTy, setMapTy] = useState(0);
  const [isMapPanning, setIsMapPanning] = useState(false);
  const [mapPanStart, setMapPanStart] = useState<{ x: number; y: number; tx: number; ty: number } | null>(null);

  const [chinaGeo, setChinaGeo] = useState<ChinaGeoJSON | null>(null);
  const [locRoot, setLocRoot] = useState<LocationsRoot | null>(null);
  const didInitViewRef = useRef(false);
  const [clusterOpen, setClusterOpen] = useState<{
    key: string;
    title: string;
    items: Array<{ entity_id: string; name: string; province: string; city: string; is_key_target: boolean; is_target: boolean }>;
    x: number;
    y: number;
  } | null>(null);

  const links = useMemo(() => {
    const s = encodeURIComponent(snapshotName);
    return {
      analysis: `/analysis?snapshot_name=${s}`,
      targets: `/targets?snapshot_name=${s}`,
      compare: `/compare?snapshot_name=${s}`,
      csvEntities: `/api/equity/export/csv?type=entities&snapshot_name=${s}`,
      csvEdges: `/api/equity/export/csv?type=equity_edges&snapshot_name=${s}`,
      csvTargets: `/api/equity/export/csv?type=targets&snapshot_name=${s}`,
    };
  }, [snapshotName]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    if (!snapshotName.trim()) {
      setLoading(false);
      setEntities([]);
      return;
    }
    fetch(`/api/equity/entities/geo?snapshot_name=${encodeURIComponent(snapshotName)}&limit=20000&include_unknown=true`, {
      cache: "no-store",
      credentials: "include",
      headers: getAuthHeaders(),
    })
      .then(async (r) => {
        if (!r.ok) throw new Error(await r.text());
        return (await r.json()) as EntitiesGeoResponse;
      })
      .then((d) => {
        if (cancelled) return;
        setEntities(d.items ?? []);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(String(e?.message || e));
        setEntities([]);
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [snapshotName]);

  useEffect(() => {
    let cancelled = false;
    if (!snapshotName.trim()) {
      setTargets([]);
      return;
    }
    fetch(`/api/equity/targets?snapshot_name=${encodeURIComponent(snapshotName)}`, {
      cache: "no-store",
      credentials: "include",
      headers: getAuthHeaders(),
    })
      .then(async (r) => {
        if (!r.ok) throw new Error(await r.text());
        return (await r.json()) as TargetsListResponse;
      })
      .then((d) => {
        if (cancelled) return;
        setTargets(d.items ?? []);
      })
      .catch(() => {
        if (cancelled) return;
        setTargets([]);
      });
    return () => {
      cancelled = true;
    };
  }, [snapshotName]);

  useEffect(() => {
    let cancelled = false;
    setPanoramaError(null);
    if (!snapshotName.trim() || !heatmapFocusTargetId.trim()) {
      setPanoramaLoading(false);
      setPanoramaNodes([]);
      return;
    }
    setPanoramaLoading(true);
    const q = new URLSearchParams({
      snapshot_name: snapshotName,
      target_entity_id: heatmapFocusTargetId,
      min_pct: "0",
      max_depth: "10",
      max_nodes: "5000",
    });
    fetch(`/api/equity/graph/panorama?${q.toString()}`, {
      cache: "no-store",
      credentials: "include",
      headers: getAuthHeaders(),
    })
      .then(async (r) => {
        if (!r.ok) throw new Error(await r.text());
        return (await r.json()) as PanoramaResponse;
      })
      .then((d) => {
        if (cancelled) return;
        setPanoramaNodes(d.nodes ?? []);
      })
      .catch((e) => {
        if (cancelled) return;
        setPanoramaError(String(e?.message || e));
        setPanoramaNodes([]);
      })
      .finally(() => {
        if (cancelled) return;
        setPanoramaLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [snapshotName, heatmapFocusTargetId]);

  useEffect(() => {
    setHeatmapFocusTargetId("");
    setClusterOpen(null);
  }, [snapshotName]);

  useEffect(() => {
    let cancelled = false;
    // 真实底图：阿里 DataV GeoJSON（省级轮廓）
    if (!chinaGeo) {
      fetch("https://geo.datav.aliyun.com/areas_v2/bound/100000_full.json", { cache: "force-cache" })
        .then(async (r) => {
          if (!r.ok) throw new Error(await r.text());
          return (await r.json()) as ChinaGeoJSON;
        })
        .then((d) => {
          if (!cancelled) setChinaGeo(d);
        })
        .catch(() => {
          // 底图失败时：仍允许展示点（但会缺少底图）
        });
    }
    // 真实中心点：省/市/区县中心经纬度（用于圆点定位）
    if (!locRoot) {
      fetch("https://raw.githubusercontent.com/HunterPan/GeoMapData_CN/master/location.json", { cache: "force-cache" })
        .then(async (r) => {
          if (!r.ok) throw new Error(await r.text());
          return (await r.json()) as LocationsRoot;
        })
        .then((d) => {
          if (!cancelled) setLocRoot(d);
        })
        .catch(() => {
          // ignore
        });
    }
    return () => {
      cancelled = true;
    };
  }, [chinaGeo, locRoot]);

  const points = useMemo(() => {
    if (heatmapFocusTargetId.trim()) {
      const rows = panoramaNodes.map((n) => {
        const g = n.geo || {};
        const tags = n.tags || {};
        const isFocus = n.id === heatmapFocusTargetId;
        return {
          id: n.id,
          name: n.name,
          province: String(g.province ?? "").trim(),
          city: String(g.city ?? "").trim(),
          is_target: Boolean(tags.is_target) || isFocus,
          is_key_target: Boolean(tags.is_key_target) || isFocus,
        };
      });
      return buildMapPointsFromGeoRows(rows, locRoot);
    }

    const rows = entities.map((t) => ({
      id: t.entity_id,
      name: t.name,
      province: String(t.geo?.province ?? "").trim(),
      city: String(t.geo?.city ?? "").trim(),
      is_target: Boolean(t.is_target),
      is_key_target: Boolean(t.is_key_target),
    }));
    return buildMapPointsFromGeoRows(rows, locRoot);
  }, [entities, locRoot, heatmapFocusTargetId, panoramaNodes]);

  type HexBin = {
    key: string;
    cx: number;
    cy: number;
    count: number;
    weight: number;
    items: Array<{ entity_id: string; name: string; province: string; city: string; is_key_target: boolean; is_target: boolean }>;
    path: string;
  };

  function hexToPixel(q: number, r: number, size: number) {
    // pointy-top axial -> pixel
    const x = size * Math.sqrt(3) * (q + r / 2);
    const y = size * (3 / 2) * r;
    return { x, y };
  }

  function pixelToHex(x: number, y: number, size: number) {
    // pixel -> axial (fractional)
    const q = ((Math.sqrt(3) / 3) * x - (1 / 3) * y) / size;
    const r = ((2 / 3) * y) / size;
    return { q, r };
  }

  function cubeRound(q: number, r: number) {
    // axial -> cube round -> axial int
    let x = q;
    let z = r;
    let y = -x - z;
    let rx = Math.round(x);
    let ry = Math.round(y);
    let rz = Math.round(z);
    const xDiff = Math.abs(rx - x);
    const yDiff = Math.abs(ry - y);
    const zDiff = Math.abs(rz - z);
    if (xDiff > yDiff && xDiff > zDiff) rx = -ry - rz;
    else if (yDiff > zDiff) ry = -rx - rz;
    else rz = -rx - ry;
    return { q: rx, r: rz };
  }

  function hexPath(cx: number, cy: number, size: number) {
    const pts: Array<[number, number]> = [];
    for (let i = 0; i < 6; i++) {
      const ang = toRad(60 * i - 30); // pointy-top
      pts.push([cx + size * Math.cos(ang), cy + size * Math.sin(ang)]);
    }
    let d = "";
    for (let i = 0; i < pts.length; i++) {
      const [x, y] = pts[i];
      d += (i === 0 ? "M" : "L") + x.toFixed(2) + " " + y.toFixed(2) + " ";
    }
    return d + "Z";
  }

  const mapModel = useMemo(() => {
    // 把 GeoJSON 投影到 viewBox(1000x700) 的坐标系，保证底图与点同坐标
    const W = 1000;
    const H = 700;
    const PAD = 18;

    const features = chinaGeo?.features || [];
    if (!features.length) {
      return {
        W,
        H,
        paths: [] as string[],
        projectPoint: (lng: number, lat: number) => ({ x: W / 2, y: H / 2 }),
      };
    }

    // 先用经纬度做整体 bounds（用投影归一化后算 min/max）
    let minX = Infinity,
      minY = Infinity,
      maxX = -Infinity,
      maxY = -Infinity;
    const scanPoint = (lng: number, lat: number) => {
      const p = mercatorProject(lng, lat);
      if (Number.isFinite(p.x) && Number.isFinite(p.y)) {
        minX = Math.min(minX, p.x);
        minY = Math.min(minY, p.y);
        maxX = Math.max(maxX, p.x);
        maxY = Math.max(maxY, p.y);
      }
    };
    for (const f of features) {
      const g = f.geometry;
      const polys = g.type === "Polygon" ? [g.coordinates] : g.coordinates;
      for (const poly of polys) {
        for (const ring of poly) {
          for (const pt of ring) {
            scanPoint(pt[0], pt[1]);
          }
        }
      }
    }

    if (!Number.isFinite(minX) || !Number.isFinite(minY) || !Number.isFinite(maxX) || !Number.isFinite(maxY)) {
      return {
        W,
        H,
        paths: [] as string[],
        projectPoint: (lng: number, lat: number) => ({ x: W / 2, y: H / 2 }),
      };
    }

    const spanX = Math.max(1e-9, maxX - minX);
    const spanY = Math.max(1e-9, maxY - minY);
    const scale = Math.min((W - PAD * 2) / spanX, (H - PAD * 2) / spanY);
    const offX = PAD - minX * scale + (W - PAD * 2 - spanX * scale) / 2;
    const offY = PAD - minY * scale + (H - PAD * 2 - spanY * scale) / 2;

    const projectPoint = (lng: number, lat: number) => {
      const p = mercatorProject(lng, lat);
      return { x: p.x * scale + offX, y: p.y * scale + offY };
    };

    const paths: string[] = [];
    for (const f of features) {
      const g = f.geometry;
      const polys = g.type === "Polygon" ? [g.coordinates] : g.coordinates;
      for (const poly of polys) {
        for (const ring of poly) {
          let d = "";
          for (let i = 0; i < ring.length; i++) {
            const p = projectPoint(ring[i][0], ring[i][1]);
            d += (i === 0 ? "M" : "L") + p.x.toFixed(2) + " " + p.y.toFixed(2) + " ";
          }
          d += "Z";
          paths.push(d);
        }
      }
    }

    return { W, H, paths, projectPoint };
  }, [chinaGeo]);

  useEffect(() => {
    // 仅首次在底图 ready 后做一次“默认视图”初始化（避免每次数据刷新都打断用户缩放/拖拽）
    if (didInitViewRef.current) return;
    if (!mapModel.paths.length) return;
    didInitViewRef.current = true;
    setMapScale(EQUITY_MAP_DEFAULT_SCALE);
    setMapTx(0);
    setMapTy(0);
  }, [mapModel.paths.length]);

  const hexbins = useMemo<HexBin[]>(() => {
    // Hexbin：在投影后的屏幕坐标系里分箱
    if (!points.length) return [];
    const size = 18; // hex 半径（像素，越大越平滑）

    const groups = new Map<
      string,
      {
        q: number;
        r: number;
        cx: number;
        cy: number;
        items: HexBin["items"];
        count: number;
        weight: number;
      }
    >();

    for (const p of points) {
      const proj = mapModel.projectPoint(p.lng, p.lat);
      const j = jitter(p.entity_id);
      // 轻微抖动避免“同一中心点完全重合”导致边界处跳动
      const x = proj.x + j.dx * 0.6;
      const y = proj.y + j.dy * 0.6;

      // 转到以地图中心为原点的坐标系，再做 hex 分箱
      const ox = x - mapModel.W / 2;
      const oy = y - mapModel.H / 2;
      const frac = pixelToHex(ox, oy, size);
      const h = cubeRound(frac.q, frac.r);
      const pix = hexToPixel(h.q, h.r, size);
      const cx = pix.x + mapModel.W / 2;
      const cy = pix.y + mapModel.H / 2;
      const key = `${h.q},${h.r}`;

      const item = {
        entity_id: p.entity_id,
        name: p.name,
        province: p.province,
        city: p.city,
        is_key_target: p.is_key_target,
        is_target: p.is_target,
      };

      const w = 1 + (p.is_target ? 0.6 : 0) + (p.is_key_target ? 1.2 : 0);
      const cur = groups.get(key);
      if (!cur) {
        groups.set(key, { q: h.q, r: h.r, cx, cy, items: [item], count: 1, weight: w });
      } else {
        cur.items.push(item);
        cur.count += 1;
        cur.weight += w;
      }
    }

    const bins: HexBin[] = [];
    for (const [key, g] of groups.entries()) {
      g.items.sort(
        (a, b) =>
          Number(b.is_key_target) - Number(a.is_key_target) ||
          Number(b.is_target) - Number(a.is_target) ||
          a.name.localeCompare(b.name),
      );
      bins.push({
        key,
        cx: g.cx,
        cy: g.cy,
        count: g.count,
        weight: g.weight,
        items: g.items,
        path: hexPath(g.cx, g.cy, size),
      });
    }
    // 稳定排序：大密度优先（便于 hover/点击）
    bins.sort((a, b) => b.weight - a.weight || b.count - a.count);
    return bins;
  }, [points, mapModel, heatmapFocusTargetId]);

  const focusTargetLabel = useMemo(() => {
    const t = targets.find((x) => x.entity_id === heatmapFocusTargetId);
    return t?.name?.trim() || "";
  }, [targets, heatmapFocusTargetId]);

  const panoramaGeoMiss = useMemo(() => {
    if (!heatmapFocusTargetId.trim()) return 0;
    return Math.max(0, panoramaNodes.length - points.length);
  }, [heatmapFocusTargetId, panoramaNodes.length, points.length]);

  const hexLegend = useMemo(() => {
    const maxW = hexbins.reduce((m, b) => Math.max(m, b.weight), 0);
    return { maxW };
  }, [hexbins]);

  function hexColor(weight: number, maxW: number, mode: "all" | "focus") {
    if (!maxW || maxW <= 0) return "rgba(148,163,184,0.18)";
    // 0..1
    const t = clamp(weight / maxW, 0, 1);
    if (mode === "focus") {
      // 琥珀/橙系，与全量蓝紫区分开
      const r = Math.round(120 + 135 * t);
      const g = Math.round(55 + 85 * (1 - t));
      const b = Math.round(20 + 35 * (1 - t));
      const a = 0.18 + 0.52 * t;
      return `rgba(${r},${g},${b},${a.toFixed(3)})`;
    }
    // cool -> warm（蓝 -> 紫 -> 红）
    const r = Math.round(40 + 215 * t);
    const g = Math.round(90 + 40 * (1 - t));
    const b = Math.round(220 - 150 * t);
    const a = 0.16 + 0.55 * t;
    return `rgba(${r},${g},${b},${a.toFixed(3)})`;
  }

  function clamp(n: number, a: number, b: number) {
    return Math.max(a, Math.min(b, n));
  }

  const heatmapMode = heatmapFocusTargetId.trim() ? "focus" : "all";

  function handleMapWheel(e: React.WheelEvent<HTMLDivElement>) {
    // 简易缩放：围绕鼠标位置缩放（只做“视觉上够用”的交互）
    e.preventDefault();
    const delta = e.deltaY;
    const nextScale = clamp(mapScale * (delta > 0 ? 0.9 : 1.1), 0.6, 4);
    setMapScale(nextScale);
  }

  function handleMapMouseDown(e: React.MouseEvent<HTMLDivElement>) {
    // 仅左键拖拽
    if (e.button !== 0) return;
    setIsMapPanning(true);
    setMapPanStart({ x: e.clientX, y: e.clientY, tx: mapTx, ty: mapTy });
  }

  function handleMapMouseMove(e: React.MouseEvent<HTMLDivElement>) {
    if (!isMapPanning || !mapPanStart) return;
    const dx = e.clientX - mapPanStart.x;
    const dy = e.clientY - mapPanStart.y;
    setMapTx(mapPanStart.tx + dx);
    setMapTy(mapPanStart.ty + dy);
  }

  function handleMapMouseUp() {
    setIsMapPanning(false);
    setMapPanStart(null);
  }

  return (
    <div className="p-4 md:p-6">
      <div className="mb-4 flex flex-col gap-3 border-b border-zinc-800/80 pb-4 lg:flex-row lg:items-center lg:justify-between lg:gap-4">
        <div className="min-w-0 flex-1">
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-100">股权全景</h1>
          <p className="mt-1 text-sm text-zinc-500">
            选择 snapshot 后进入工作台与图谱；CSV 在页尾下载。资料包上传请在{" "}
            <Link href="/finance" className="text-zinc-300 underline underline-offset-2 hover:text-white">
              财务后台
            </Link>{" "}
            完成。
          </p>
        </div>
        <div className="flex shrink-0 flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:justify-end">
          <label className="flex items-center gap-2">
            <span className="whitespace-nowrap text-[11px] text-zinc-500">snapshot</span>
            <input
              value={snapshotName}
              onChange={(e) => setSnapshotName(e.target.value)}
              className="h-8 w-36 rounded-md border border-zinc-800 bg-zinc-950 px-2 text-xs text-zinc-100 outline-none focus:border-zinc-700 sm:w-44"
              placeholder="2026-04-08_run1"
            />
          </label>
          <div className="flex flex-wrap items-center gap-1.5">
            <Link
              href={links.analysis}
              className="whitespace-nowrap rounded-md bg-zinc-100 px-2 py-1.5 text-[11px] font-medium text-zinc-900 hover:bg-white"
            >
              全景工作台
            </Link>
            <Link
              href={links.targets}
              className="whitespace-nowrap rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1.5 text-[11px] text-zinc-200 hover:bg-zinc-900"
            >
              目标列表
            </Link>
            <Link
              href={links.compare}
              className="whitespace-nowrap rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1.5 text-[11px] text-zinc-200 hover:bg-zinc-900"
            >
              公司对比
            </Link>
          </div>
        </div>
      </div>

      <div className="mb-4 flex min-h-0 flex-1 flex-col rounded-lg border border-zinc-800 bg-zinc-950 p-3 md:p-4">
        <div className="mb-2 flex flex-col gap-2 xl:flex-row xl:items-center xl:justify-between xl:gap-3">
          <div className="shrink-0 text-sm font-medium text-zinc-200">公司分布（中国）</div>
          <div className="flex min-w-0 flex-1 flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:justify-end sm:gap-2">
            <label className="flex min-w-0 items-center gap-2">
              <span className="hidden shrink-0 text-[11px] text-zinc-500 sm:inline">聚焦</span>
              <select
                className="h-8 min-w-0 max-w-full flex-1 rounded-md border border-zinc-800 bg-zinc-950 px-2 text-xs text-zinc-100 outline-none focus:border-zinc-700 sm:max-w-[220px] md:max-w-[280px]"
                title="热力图聚焦（标的股权架构全景）"
                value={
                  heatmapFocusTargetId && targets.some((t) => t.entity_id === heatmapFocusTargetId)
                    ? heatmapFocusTargetId
                    : ""
                }
                onChange={(e) => {
                  setHeatmapFocusTargetId(e.target.value);
                  setClusterOpen(null);
                }}
                disabled={!snapshotName.trim() || !targets.length}
              >
                <option value="">全量主体（默认）</option>
                {targets.map((t) => (
                  <option key={t.entity_id} value={t.entity_id}>
                    {(t.is_key ? "★ " : "") + t.name}
                  </option>
                ))}
              </select>
            </label>
            <div className="hidden shrink-0 text-[11px] text-zinc-500 md:block md:max-w-[200px] md:truncate lg:max-w-xs">
              {loading || panoramaLoading ? (
                "加载中…"
              ) : error ? (
                "地理全量加载失败"
              ) : heatmapFocusTargetId.trim() ? (
                <>
                  {focusTargetLabel
                    ? `「${focusTargetLabel.slice(0, 14)}${focusTargetLabel.length > 14 ? "…" : ""}」`
                    : ""}{" "}
                  节点 {panoramaNodes.length} · 落点 {points.length}
                  {panoramaGeoMiss ? ` · 未定位 ${panoramaGeoMiss}` : ""}
                </>
              ) : (
                `全量 ${entities.length} 家`
              )}
            </div>
            <div className="flex shrink-0 items-center gap-1">
              <button
                type="button"
                className="rounded border border-zinc-800 bg-zinc-950 px-2 py-1 text-[11px] text-zinc-400 hover:bg-zinc-900"
                onClick={() => setMapScale((s) => clamp(s * 0.9, 0.5, 6))}
              >
                缩小
              </button>
              <button
                type="button"
                className="rounded border border-zinc-800 bg-zinc-950 px-2 py-1 text-[11px] text-zinc-400 hover:bg-zinc-900"
                onClick={() => setMapScale((s) => clamp(s * 1.1, 0.5, 6))}
              >
                放大
              </button>
              <button
                type="button"
                className="rounded border border-zinc-800 bg-zinc-950 px-2 py-1 text-[11px] text-zinc-400 hover:bg-zinc-900"
                onClick={() => {
                  setMapScale(EQUITY_MAP_DEFAULT_SCALE);
                  setMapTx(0);
                  setMapTy(0);
                  setClusterOpen(null);
                }}
              >
                复位
              </button>
            </div>
          </div>
        </div>
        <div className="mb-2 text-[11px] text-zinc-500 md:hidden">
          {loading || panoramaLoading ? (
            "加载中…"
          ) : error ? (
            "地理全量加载失败"
          ) : heatmapFocusTargetId.trim() ? (
            <>
              节点 {panoramaNodes.length} · 落点 {points.length}
              {panoramaGeoMiss ? ` · 未定位 ${panoramaGeoMiss}` : ""}
            </>
          ) : (
            `全量 ${entities.length} 家`
          )}
        </div>
        {panoramaError && heatmapFocusTargetId.trim() ? (
          <div className="mb-2 rounded-md border border-amber-900/40 bg-amber-950/30 p-2 text-xs text-amber-100">
            全景子图加载失败（热力图可能为空）：{panoramaError}
          </div>
        ) : null}
        {error && (
          <div className="mb-2 rounded-md border border-red-900/40 bg-red-950/40 p-3 text-xs text-red-200">
            读取公司地理信息失败：{error}
          </div>
        )}
        {/* 地图与「密度」公司列表：大屏左右分栏，小屏上图下列 */}
        <div className="flex flex-col gap-3 lg:flex-row lg:items-stretch lg:gap-3">
          <div
            className="relative min-h-[360px] h-[clamp(360px,calc(100vh-13.5rem),min(88vh,960px))] min-w-0 flex-1 overflow-hidden rounded-md border border-zinc-800 bg-zinc-900/20"
            onWheel={handleMapWheel}
            onMouseDown={handleMapMouseDown}
            onMouseMove={handleMapMouseMove}
            onMouseUp={handleMapMouseUp}
            onMouseLeave={handleMapMouseUp}
            style={{ cursor: isMapPanning ? "grabbing" : "grab" }}
          >
            <svg
              className="absolute inset-0 h-full w-full"
              viewBox={`0 0 ${mapModel.W} ${mapModel.H}`}
              preserveAspectRatio="xMidYMid meet"
              role="img"
              aria-label="China map"
              onClick={() => setClusterOpen(null)}
            >
              <g
                style={{
                  transform: `translate(${mapTx}px, ${mapTy}px) scale(${mapScale})`,
                  transformOrigin: `${mapModel.W / 2}px ${mapModel.H / 2}px`,
                }}
              >
                {/* 真实中国行政区轮廓（GeoJSON 渲染，省级边界） */}
                {mapModel.paths.map((d, i) => (
                  <path
                    key={i}
                    d={d}
                    fill="rgba(59,130,246,0.08)"
                    stroke="rgba(148,163,184,0.55)"
                    strokeWidth="1"
                  />
                ))}

                {/* Hexbin 密度层 */}
                {hexbins.map((hb) => {
                  const title = `密度：${hb.count} 家（权重 ${hb.weight.toFixed(1)}）`;
                  const fill = hexColor(hb.weight, hexLegend.maxW, heatmapMode);
                  return (
                    <g
                      key={hb.key}
                      onClick={(e) => {
                        e.stopPropagation();
                        if (hb.items.length === 1) {
                          const only = hb.items[0];
                          router.push(
                            `/targets/${encodeURIComponent(only.entity_id)}` +
                              `?snapshot_name=${encodeURIComponent(snapshotName)}` +
                              `&min_pct=0&max_depth=10&max_nodes=5000`
                          );
                          return;
                        }
                        setClusterOpen({
                          key: hb.key,
                          title,
                          items: hb.items,
                          x: hb.cx,
                          y: hb.cy,
                        });
                      }}
                      style={{ cursor: "pointer" }}
                    >
                      <title>{title}</title>
                      <path d={hb.path} fill={fill} stroke="rgba(255,255,255,0.22)" strokeWidth="1" />
                      {hb.count >= 6 ? (
                        <text
                          x={hb.cx}
                          y={hb.cy + 4}
                          textAnchor="middle"
                          fontSize="12"
                          fill="rgba(0,0,0,0.75)"
                          style={{ userSelect: "none", pointerEvents: "none" }}
                        >
                          {hb.count}
                        </text>
                      ) : null}
                    </g>
                  );
                })}
              </g>
            </svg>
          </div>
          {clusterOpen ? (
            <div className="flex min-h-[240px] w-full shrink-0 flex-col rounded-md border border-zinc-800 bg-zinc-950/70 lg:min-h-0 lg:h-[clamp(360px,calc(100vh-13.5rem),min(88vh,960px))] lg:w-80 lg:max-w-[min(22rem,36vw)]">
              <div className="flex shrink-0 items-center justify-between gap-2 border-b border-zinc-800 px-3 py-2">
                <div className="min-w-0 text-sm font-medium text-zinc-200">{clusterOpen.title}</div>
                <button
                  type="button"
                  className="shrink-0 rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-900"
                  onClick={() => setClusterOpen(null)}
                >
                  关闭
                </button>
              </div>
              <div className="min-h-0 flex-1 overflow-auto rounded-b-md">
                {clusterOpen.items.map((it) => (
                  <button
                    key={it.entity_id}
                    type="button"
                    className="flex w-full items-center justify-between gap-3 border-b border-zinc-800 bg-zinc-950 px-3 py-2 text-left text-sm text-zinc-200 last:border-b-0 hover:bg-zinc-900"
                    onClick={() =>
                      router.push(
                        `/targets/${encodeURIComponent(it.entity_id)}` +
                          `?snapshot_name=${encodeURIComponent(snapshotName)}` +
                          `&min_pct=0&max_depth=10&max_nodes=5000`
                      )
                    }
                  >
                    <span className="min-w-0 truncate">
                      {it.is_key_target ? "★ " : it.is_target ? "• " : ""}
                      {it.name}
                    </span>
                    <span className="shrink-0 text-xs text-zinc-500">
                      {it.province}
                      {it.city ? `/${it.city}` : ""}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          ) : null}
        </div>
        <div className="mt-2 text-xs text-zinc-500">
          说明：底图为真实中国行政区（省级）GeoJSON；密度层使用 Hexbin（六边形蜂窝）按公司数量/标的权重聚合。
          下拉选择某一标的后，热力图仅统计该标的「股权架构全景」子图中的主体地理分布（参数与全景页一致：min_pct=0、max_depth=10、max_nodes=5000）。
          点击含多家公司的六边形时，公司列表显示在地图右侧（窄屏在地图下方）；单格仅一家时直接进入该公司全景。支持滚轮缩放、按住拖拽平移。
        </div>
      </div>

      <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-4">
        <div className="mb-2 text-sm font-medium text-zinc-200">数据表下载（CSV）</div>
        <p className="text-xs text-zinc-500">按当前 snapshot 导出标准化表，UTF-8。</p>
        <div className="mt-3 flex flex-wrap gap-2">
          <a href={links.csvEntities} className="rounded-md border border-zinc-800 bg-zinc-900 px-3 py-2 text-xs text-zinc-200 hover:bg-zinc-800">
            entities.csv
          </a>
          <a href={links.csvEdges} className="rounded-md border border-zinc-800 bg-zinc-900 px-3 py-2 text-xs text-zinc-200 hover:bg-zinc-800">
            equity_edges.csv
          </a>
          <a href={links.csvTargets} className="rounded-md border border-zinc-800 bg-zinc-900 px-3 py-2 text-xs text-zinc-200 hover:bg-zinc-800">
            targets.csv
          </a>
        </div>
      </div>
    </div>
  );
}
