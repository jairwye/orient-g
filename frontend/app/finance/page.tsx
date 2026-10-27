"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { getAuthHeaders } from "../lib/auth";
import { DEFAULT_EQUITY_SNAPSHOT, useEquitySnapshotName } from "../lib/equitySnapshot";

const DEFAULT_FINANCE_PATH = "/finance";

function dedupeWarnings(warnings: string[]): string[] {
  const seen = new Set<string>();
  return warnings.filter((w) => {
    if (seen.has(w)) return false;
    seen.add(w);
    return true;
  });
}

function ParseWarningList({
  warnings,
  label,
  maxShow = 50,
}: {
  warnings: string[];
  label?: string;
  maxShow?: number;
}) {
  const items = dedupeWarnings(warnings);
  if (items.length === 0) return null;
  const copyAll = () => {
    void navigator.clipboard.writeText(items.join("\n"));
  };
  return (
    <div className="mt-3 rounded-md border border-amber-900/40 bg-amber-950/20 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-amber-500/90">
          {label ?? "解析告警"}（{items.length} 条）
        </p>
        <button
          type="button"
          onClick={copyAll}
          className="text-xs text-amber-400/80 hover:text-amber-300"
        >
          复制全部
        </button>
      </div>
      <ul className="mt-2 max-h-48 overflow-y-auto text-xs text-amber-400/90">
        {items.slice(0, maxShow).map((w, i) => (
          <li key={`${i}-${w}`} className="border-b border-amber-900/20 py-0.5 last:border-0">
            {w}
          </li>
        ))}
        {items.length > maxShow && <li className="pt-1 text-amber-500/70">…另有 {items.length - maxShow} 条告警</li>}
      </ul>
    </div>
  );
}

type BundleImportResult = {
  ok: boolean;
  snapshot_name: string;
  inserted?: { entities: number; targets: number; edges: number; created_entities: number };
  detail?: string;
};

export default function FinanceAdminPage() {
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [month, setMonth] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { snapshotName: equitySnapshotName, setSnapshotName: setEquitySnapshotName } = useEquitySnapshotName("");
  const [bundleFile, setBundleFile] = useState<File | null>(null);
  const [bundleImporting, setBundleImporting] = useState(false);
  const [bundleImportResult, setBundleImportResult] = useState<BundleImportResult | null>(null);
  const [bundleImportError, setBundleImportError] = useState<string | null>(null);

  const [financePath, setFinancePath] = useState(DEFAULT_FINANCE_PATH);
  const [financePathEdit, setFinancePathEdit] = useState(DEFAULT_FINANCE_PATH);
  const [pathSaving, setPathSaving] = useState(false);
  const [pathMessage, setPathMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const [competitorUploading, setCompetitorUploading] = useState(false);
  const [competitorMessage, setCompetitorMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [competitorWarnings, setCompetitorWarnings] = useState<string[]>([]);
  const competitorFileRef = useRef<HTMLInputElement>(null);
  const [competitorEditions, setCompetitorEditions] = useState<
    Array<{ edition_id: string; period_label: string; is_current?: boolean; has_vertical?: boolean }>
  >([]);
  const [competitorCurrentId, setCompetitorCurrentId] = useState<string | null>(null);
  const [competitorUploadEditionId, setCompetitorUploadEditionId] = useState("2025-annual");
  const [competitorSetAsCurrent, setCompetitorSetAsCurrent] = useState(true);
  const [competitorNewEditionId, setCompetitorNewEditionId] = useState("2026-h1");
  const [competitorNewKind, setCompetitorNewKind] = useState<"annual" | "interim">("interim");
  const [competitorNewLabel, setCompetitorNewLabel] = useState("2026 半年报");
  const [competitorNewHasVertical, setCompetitorNewHasVertical] = useState(false);
  const [competitorEditionBusy, setCompetitorEditionBusy] = useState(false);

  const [verticalUploading, setVerticalUploading] = useState(false);
  const [verticalMessage, setVerticalMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [verticalMessageSource, setVerticalMessageSource] = useState<"zip" | "md" | null>(null);
  /** 纵向上传目标期次（须 has_vertical） */
  const [verticalUploadEditionId, setVerticalUploadEditionId] = useState("2025-annual");
  /** 当前 vertical.snapshot.json 中的解析告警（页面加载时从 meta 拉取，上传完成后刷新） */
  const [verticalSnapshotWarnings, setVerticalSnapshotWarnings] = useState<string[]>([]);
  const verticalFileRef = useRef<HTMLInputElement>(null);

  const [verticalIngestUploading, setVerticalIngestUploading] = useState(false);
  const [verticalIngestJobId, setVerticalIngestJobId] = useState<string | null>(null);
  const [verticalIngestStatus, setVerticalIngestStatus] = useState<{
    status?: string;
    progress?: number;
    current_company?: string;
    companies_done?: number;
    companies_total?: number;
    error?: string;
    warnings?: string[];
  } | null>(null);
  const verticalIngestFileRef = useRef<HTMLInputElement>(null);
  const verticalPdfOnlyFileRef = useRef<HTMLInputElement>(null);
  const [verticalPdfOnlyUploading, setVerticalPdfOnlyUploading] = useState(false);

  const refreshCompetitorEditions = useCallback(() => {
    fetch("/api/competitor/editions", { credentials: "include", headers: getAuthHeaders() })
      .then((r) => (r.ok ? r.json() : null))
      .then(
        (data: {
          editions?: Array<{
            edition_id: string;
            period_label: string;
            is_current?: boolean;
            has_vertical?: boolean;
          }>;
          current?: string | null;
        } | null) => {
          if (!data) return;
          const list = Array.isArray(data.editions) ? data.editions : [];
          setCompetitorEditions(list);
          setCompetitorCurrentId(data.current ?? null);
          if (list.length && !list.some((e) => e.edition_id === competitorUploadEditionId)) {
            setCompetitorUploadEditionId(data.current || list[0].edition_id);
          }
          const withVertical = list.filter((e) => e.has_vertical);
          if (withVertical.length) {
            if (!withVertical.some((e) => e.edition_id === verticalUploadEditionId)) {
              const prefer =
                withVertical.find((e) => e.edition_id === data.current) || withVertical[0];
              setVerticalUploadEditionId(prefer.edition_id);
            }
          }
        },
      )
      .catch(() => {});
  }, [competitorUploadEditionId, verticalUploadEditionId]);

  const refreshVerticalSnapshotWarnings = useCallback(
    (editionId?: string) => {
      const eid = editionId || verticalUploadEditionId;
      const q = eid ? `?edition=${encodeURIComponent(eid)}` : "";
      fetch(`/api/competitor/vertical-report/meta${q}`, {
        credentials: "include",
        headers: getAuthHeaders(),
      })
        .then((r) => (r.ok ? r.json() : null))
        .then((meta: { warnings?: string[] } | null) => {
          if (meta && Array.isArray(meta.warnings)) {
            setVerticalSnapshotWarnings(meta.warnings);
          } else {
            setVerticalSnapshotWarnings([]);
          }
        })
        .catch(() => {});
    },
    [verticalUploadEditionId],
  );

  useEffect(() => {
    fetch("/api/settings", { credentials: "include", headers: getAuthHeaders() })
      .then((r) => (r.ok ? r.json() : { finance_path: DEFAULT_FINANCE_PATH }))
      .then((data: { finance_path?: string }) => {
        const p = (data.finance_path ?? DEFAULT_FINANCE_PATH).trim();
        setFinancePath(p);
        setFinancePathEdit(p);
      })
      .catch(() => {});
    refreshVerticalSnapshotWarnings();
    refreshCompetitorEditions();
  }, [refreshCompetitorEditions, refreshVerticalSnapshotWarnings]);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";
    setMessage(null);
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      if (month) form.append("month", month);
      const res = await fetch("/api/business/upload", {
        method: "POST",
        headers: getAuthHeaders(),
        body: form,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        const msg =
          (Array.isArray(err.detail) ? err.detail[0]?.msg : undefined) ??
          (typeof err.detail === "string" ? err.detail : undefined);
        throw new Error(msg ?? "上传失败");
      }
      setMessage({ type: "success", text: "已上传，经营数据展示页将显示最新数据。" });
    } catch (err) {
      setMessage({
        type: "error",
        text: err instanceof Error ? err.message : "上传失败，请重试",
      });
    } finally {
      setUploading(false);
    }
  };

  const doImportEquityBundle = async () => {
    if (!bundleFile) return;
    setBundleImporting(true);
    setBundleImportError(null);
    setBundleImportResult(null);
    try {
      const fd = new FormData();
      fd.append("file", bundleFile);
      const res = await fetch(
        `/api/equity/admin/import/bundle-zip?snapshot_name=${encodeURIComponent(equitySnapshotName)}`,
        {
          method: "POST",
          body: fd,
          credentials: "include",
          headers: getAuthHeaders(),
        },
      );
      if (!res.ok) throw new Error(await res.text());
      const data = (await res.json()) as BundleImportResult;
      setBundleImportResult(data);
    } catch (e: unknown) {
      setBundleImportError(String(e instanceof Error ? e.message : e));
    } finally {
      setBundleImporting(false);
    }
  };

  const handleCreateCompetitorEdition = async () => {
    setCompetitorMessage(null);
    setCompetitorEditionBusy(true);
    try {
      const res = await fetch("/api/competitor/admin/editions", {
        method: "POST",
        headers: { ...getAuthHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({
          edition_id: competitorNewEditionId.trim(),
          kind: competitorNewKind,
          period_label: competitorNewLabel.trim() || undefined,
          has_vertical: competitorNewHasVertical,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(typeof data.detail === "string" ? data.detail : "创建期次失败");
      }
      setCompetitorUploadEditionId(competitorNewEditionId.trim());
      setCompetitorMessage({ type: "success", text: `已创建/更新期次 ${competitorNewEditionId.trim()}` });
      refreshCompetitorEditions();
    } catch (err) {
      setCompetitorMessage({
        type: "error",
        text: err instanceof Error ? err.message : "创建期次失败",
      });
    } finally {
      setCompetitorEditionBusy(false);
    }
  };

  const handleSetCompetitorCurrent = async (editionId: string) => {
    const label =
      competitorEditions.find((e) => e.edition_id === editionId)?.period_label || editionId;
    if (!window.confirm(`将侧栏默认期次设为「${label}」？无参 /competitor 将打开本期。`)) return;
    setCompetitorEditionBusy(true);
    try {
      const res = await fetch("/api/competitor/admin/current", {
        method: "POST",
        headers: { ...getAuthHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({ edition_id: editionId }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(typeof data.detail === "string" ? data.detail : "设置失败");
      }
      setCompetitorMessage({ type: "success", text: `侧栏默认已设为 ${editionId}` });
      refreshCompetitorEditions();
    } catch (err) {
      setCompetitorMessage({
        type: "error",
        text: err instanceof Error ? err.message : "设置失败",
      });
    } finally {
      setCompetitorEditionBusy(false);
    }
  };

  const handleCompetitorUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";
    setCompetitorMessage(null);
    setCompetitorWarnings([]);
    setCompetitorUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("edition_id", competitorUploadEditionId.trim());
      if (competitorSetAsCurrent) form.append("set_as_current", "true");
      const res = await fetch("/api/competitor/admin/upload", {
        method: "POST",
        headers: getAuthHeaders(),
        body: form,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg =
          (typeof data.detail === "string" ? data.detail : undefined) ??
          (Array.isArray(data.detail) ? data.detail[0]?.msg : undefined);
        throw new Error(msg ?? "上传失败");
      }
      setCompetitorWarnings(Array.isArray(data.warnings) ? data.warnings : []);
      const stats = data.sec09_anchor_stats as Record<string, { table?: number; narrative?: number }> | undefined;
      const statBits: string[] = [];
      if (stats) {
        for (const key of ["sec-09-3", "sec-09-4", "sec-09-10", "sec-09-15"]) {
          const n = stats[key]?.table;
          if (n != null) statBits.push(`${key}: ${n} 表`);
        }
      }
      const eid = data.edition_id || competitorUploadEditionId;
      const statLine = statBits.length ? `；${statBits.join("、")}` : "";
      const currentHint = data.is_current ? "；已设为侧栏默认" : "；未改侧栏默认（可在下方「设为最新」）";
      setCompetitorMessage({
        type: "success",
        text: `期次 ${eid} 已解析 ${data.sections_parsed ?? 9} 章（sec-01～sec-09）${statLine}${currentHint}。其他期次不受影响。`,
      });
      refreshCompetitorEditions();
    } catch (err) {
      setCompetitorMessage({
        type: "error",
        text: err instanceof Error ? err.message : "上传失败",
      });
    } finally {
      setCompetitorUploading(false);
    }
  };

  const handleVerticalUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";
    if (!verticalUploadEditionId.trim()) {
      setVerticalMessage({ type: "error", text: "请选择 has_vertical 的期次后再上传" });
      setVerticalMessageSource("md");
      return;
    }
    setVerticalMessage(null);
    setVerticalMessageSource("md");
    setVerticalUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("edition_id", verticalUploadEditionId.trim());
      const res = await fetch("/api/competitor/admin/upload-vertical", {
        method: "POST",
        headers: getAuthHeaders(),
        body: form,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg =
          (typeof data.detail === "string" ? data.detail : undefined) ??
          (Array.isArray(data.detail) ? data.detail[0]?.msg : undefined);
        throw new Error(msg ?? "上传失败");
      }
      if (Array.isArray(data.warnings)) {
        setVerticalSnapshotWarnings(data.warnings);
      } else {
        refreshVerticalSnapshotWarnings(verticalUploadEditionId);
      }
      setVerticalMessage({
        type: "success",
        text: `已解析 ${data.companies_parsed ?? 0} 家公司纵向分析（${verticalUploadEditionId}）。详情链接屏与「纵向对比」页已更新。`,
      });
    } catch (err) {
      setVerticalMessage({
        type: "error",
        text: err instanceof Error ? err.message : "上传失败",
      });
    } finally {
      setVerticalUploading(false);
    }
  };

  useEffect(() => {
    if (!verticalIngestJobId) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const res = await fetch(`/api/competitor/admin/vertical-ingest/${encodeURIComponent(verticalIngestJobId)}`, {
          credentials: "include",
          headers: getAuthHeaders(),
        });
        if (!res.ok || cancelled) return;
        const data = await res.json();
        setVerticalIngestStatus(data);
        if (data.status === "completed") {
          setVerticalIngestUploading(false);
          if (Array.isArray(data.warnings)) {
            setVerticalSnapshotWarnings(data.warnings);
          } else {
            refreshVerticalSnapshotWarnings();
          }
          setVerticalMessage({
            type: "success",
            text: `Docling 解析完成，共 ${data.companies_parsed ?? data.companies_done ?? 0} 家公司。纵向对比页已更新。`,
          });
          setVerticalMessageSource("zip");
          setVerticalIngestJobId(null);
          return;
        }
        if (data.status === "failed") {
          setVerticalIngestUploading(false);
          setVerticalMessage({
            type: "error",
            text: typeof data.error === "string" ? data.error : "纵向 PDF 解析失败",
          });
          setVerticalMessageSource("zip");
          setVerticalIngestJobId(null);
          return;
        }
      } catch {
        /* retry on next tick */
      }
      if (!cancelled) window.setTimeout(poll, 3000);
    };
    poll();
    return () => {
      cancelled = true;
    };
  }, [verticalIngestJobId, refreshVerticalSnapshotWarnings]);

  const handleVerticalIngestUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";
    if (!verticalUploadEditionId.trim()) {
      setVerticalMessage({ type: "error", text: "请选择 has_vertical 的期次后再上传" });
      setVerticalMessageSource("zip");
      return;
    }
    setVerticalMessage(null);
    setVerticalMessageSource("zip");
    setVerticalIngestStatus(null);
    setVerticalIngestUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("edition_id", verticalUploadEditionId.trim());
      const res = await fetch("/api/competitor/admin/vertical-ingest", {
        method: "POST",
        headers: getAuthHeaders(),
        body: form,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg =
          (typeof data.detail === "string" ? data.detail : undefined) ??
          (Array.isArray(data.detail) ? data.detail[0]?.msg : undefined);
        throw new Error(msg ?? "上传失败");
      }
      setVerticalIngestJobId(String(data.job_id || ""));
      setVerticalIngestStatus({ status: "queued", progress: 0 });
    } catch (err) {
      setVerticalIngestUploading(false);
      setVerticalMessage({
        type: "error",
        text: err instanceof Error ? err.message : "上传失败",
      });
      setVerticalMessageSource("zip");
    }
  };

  const handleVerticalPdfOnlyUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";
    if (!verticalUploadEditionId.trim()) {
      setVerticalMessage({ type: "error", text: "请选择 has_vertical 的期次后再上传" });
      setVerticalMessageSource("zip");
      return;
    }
    setVerticalMessage(null);
    setVerticalMessageSource("zip");
    setVerticalPdfOnlyUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("edition_id", verticalUploadEditionId.trim());
      const res = await fetch("/api/competitor/admin/vertical-pdf-zip", {
        method: "POST",
        headers: getAuthHeaders(),
        body: form,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg =
          (typeof data.detail === "string" ? data.detail : undefined) ??
          (Array.isArray(data.detail) ? data.detail[0]?.msg : undefined);
        throw new Error(msg ?? "上传失败");
      }
      setVerticalMessage({
        type: "success",
        text: `已存档 ${data.companies_parsed ?? 0} 份 PDF（未解析 · ${verticalUploadEditionId}）。可在纵向页对照查看。`,
      });
    } catch (err) {
      setVerticalMessage({
        type: "error",
        text: err instanceof Error ? err.message : "上传失败",
      });
    } finally {
      setVerticalPdfOnlyUploading(false);
    }
  };

  const handleSaveFinancePath = async () => {
    let path = financePathEdit.trim();
    if (!path.startsWith("/")) path = "/" + path;
    if (!/^\/[a-zA-Z0-9_]+$/.test(path)) {
      setPathMessage({ type: "error", text: "路径须为单段，仅含字母、数字、下划线，如 /finance" });
      return;
    }
    setPathSaving(true);
    setPathMessage(null);
    try {
      const res = await fetch("/api/settings", {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        credentials: "include",
        body: JSON.stringify({ finance_path: path }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg =
          (Array.isArray(data.detail) ? data.detail[0]?.msg : undefined) ??
          (typeof data.detail === "string" ? data.detail : undefined);
        throw new Error(msg ?? `保存失败（${res.status}）`);
      }
      setFinancePath(data.finance_path);
      setFinancePathEdit(data.finance_path);
      setPathMessage({
        type: "success",
        text: "财务后台路径已保存。新路径生效后（最多约 5 秒），请使用新地址访问本页。",
      });
    } catch (err) {
      const text = err instanceof Error ? err.message : "保存失败，请重试";
      setPathMessage({
        type: "error",
        text:
          text.startsWith("Failed to fetch") || text === "NetworkError when fetching resource"
            ? "无法连接后端，请确认后端已启动（uvicorn backend.main:app --reload）"
            : text,
      });
    } finally {
      setPathSaving(false);
    }
  };

  return (
    <div className="p-6 md:p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-100">财务后台</h1>
        <p className="mt-1 text-sm text-zinc-500">上传经营数据、股权资料包，以及配置财务后台入口路径。</p>
        <p className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
          <Link href="/" className="text-sm text-zinc-400 hover:text-zinc-300">
            返回经营数据展示页
          </Link>
          <Link href="/equity" className="text-sm text-zinc-400 hover:text-zinc-300">
            股权全景（展示与下载）
          </Link>
          <Link href="/admin" className="text-sm text-zinc-400 hover:text-zinc-300">
            前往管理后台
          </Link>
        </p>
      </div>

      {/* 1. 上传经营数据 Excel */}
      <div className="mb-6 max-w-md rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
        <h2 className="mb-3 text-sm font-medium text-zinc-300">上传经营数据</h2>
        <p className="mb-3 text-xs text-zinc-500">上传 Excel 后，展示页将读取该数据。可填写月份便于后续按月份展示。</p>
        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-zinc-400">月份（可选，格式 YYYY-MM）</label>
            <input
              type="text"
              placeholder="如 2025-03"
              value={month}
              onChange={(e) => setMonth(e.target.value)}
              className="w-full rounded-md border border-zinc-600 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 placeholder-zinc-500"
            />
          </div>
          <div>
            <input
              ref={fileInputRef}
              type="file"
              accept=".xlsx,.xls"
              className="hidden"
              onChange={handleUpload}
              disabled={uploading}
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
              className="rounded-md border border-zinc-600 bg-zinc-800 px-4 py-2 text-sm text-zinc-200 hover:bg-zinc-700 disabled:opacity-50"
            >
              {uploading ? "上传中…" : "选择并上传 Excel"}
            </button>
          </div>
          {message && (
            <p className={message.type === "success" ? "text-sm text-emerald-400" : "text-sm text-red-400"}>
              {message.text}
            </p>
          )}
        </div>
      </div>

      {/* 2. 股权资料包 bundle.zip */}
      <div className="mb-6 max-w-2xl rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
        <h2 className="mb-3 text-sm font-medium text-zinc-300">上传股权资料包（bundle.zip）</h2>
        <p className="mb-3 text-xs text-zinc-500">
          zip 内可包含 <span className="text-zinc-300">targets.csv</span>、<span className="text-zinc-300">entities.csv</span>、
          <span className="text-zinc-300">equity_edges.csv</span>（任选其一或多个；文件可在子目录，按文件名匹配）。导入后请到{" "}
          <Link href="/equity" className="text-zinc-300 underline underline-offset-2 hover:text-white">
            股权全景
          </Link>{" "}
          选择同一 snapshot 查看与下载。
        </p>
        <p className="mb-4 text-xs text-zinc-500">
          <a
            href="/samples/equity-targets-30-sample.csv"
            download="equity-targets-30-sample.csv"
            className="inline-flex items-center rounded-md border border-zinc-600 bg-zinc-800 px-3 py-1.5 text-zinc-200 hover:bg-zinc-700"
          >
            下载 30 家标的公司样表（targets.csv）
          </a>
          <span className="ml-2 text-zinc-500">UTF-8，表头与导入一致；请把名称列改为真实工商全称后再打包 zip。</span>
        </p>
        <div className="mb-4">
          <label className="mb-1 block text-xs text-zinc-500">snapshot（批次名）</label>
          <input
            type="text"
            value={equitySnapshotName}
            onChange={(e) => {
              setEquitySnapshotName(e.target.value);
              setBundleImportResult(null);
              setBundleImportError(null);
            }}
            placeholder={DEFAULT_EQUITY_SNAPSHOT}
            className="w-full max-w-md rounded-md border border-zinc-600 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 placeholder-zinc-500"
          />
        </div>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <input
            type="file"
            accept=".zip,application/zip"
            onChange={(e) => {
              setBundleFile(e.target.files?.[0] || null);
              setBundleImportResult(null);
              setBundleImportError(null);
            }}
            className="block w-full text-xs text-zinc-300 file:mr-3 file:rounded-md file:border-0 file:bg-zinc-100 file:px-3 file:py-2 file:text-xs file:font-medium file:text-zinc-900 hover:file:bg-white sm:max-w-md"
          />
          <button
            type="button"
            onClick={doImportEquityBundle}
            disabled={!bundleFile || bundleImporting}
            className={
              "h-9 shrink-0 rounded-md px-3 text-xs font-medium " +
              (bundleFile && !bundleImporting ? "bg-zinc-100 text-zinc-900 hover:bg-white" : "bg-zinc-800 text-zinc-500")
            }
          >
            {bundleImporting ? "导入中…" : "导入"}
          </button>
        </div>
        {bundleImportError && (
          <p className="mt-3 text-sm text-red-400">导入失败：{bundleImportError}</p>
        )}
        {bundleImportResult && (
          <p className="mt-3 text-sm text-emerald-400">
            导入完成：entities={bundleImportResult.inserted?.entities ?? "—"} targets={bundleImportResult.inserted?.targets ?? "—"} edges=
            {bundleImportResult.inserted?.edges ?? "—"}（新增主体 {bundleImportResult.inserted?.created_entities ?? "—"}）
          </p>
        )}
      </div>

      {/* 4. 竞品财报期次 + 上传汇析 MD（1.2.3.e） */}
      <div className="mb-6 max-w-2xl rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
        <h2 className="mb-3 text-sm font-medium text-zinc-300">竞品财报期次与汇析上传</h2>
        <p className="mb-2 text-xs text-zinc-500">
          多期次并存（年报/半年报）。侧栏「竞品财报」打开 <strong className="font-medium text-zinc-400">current</strong>
          ；历史期次在展示页切换。上传只覆盖所选期次。
        </p>
        {competitorEditions.length > 0 ? (
          <ul className="mb-3 space-y-1 text-xs text-zinc-400">
            {competitorEditions.map((ed) => (
              <li key={ed.edition_id} className="flex flex-wrap items-center gap-2">
                <span>
                  {ed.period_label}{" "}
                  <code className="text-zinc-500">({ed.edition_id})</code>
                  {ed.is_current || ed.edition_id === competitorCurrentId ? (
                    <span className="ml-1 text-emerald-500/90">· 侧栏默认</span>
                  ) : null}
                </span>
                {!ed.is_current && ed.edition_id !== competitorCurrentId ? (
                  <button
                    type="button"
                    disabled={competitorEditionBusy}
                    onClick={() => handleSetCompetitorCurrent(ed.edition_id)}
                    className="text-blue-400 hover:text-blue-300 disabled:opacity-50"
                  >
                    设为最新
                  </button>
                ) : null}
                <Link
                  href={`/competitor/e/${encodeURIComponent(ed.edition_id)}`}
                  className="text-zinc-500 hover:text-zinc-300"
                >
                  打开本期
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mb-3 text-xs text-zinc-500">尚无期次；首次上传将创建所选 edition_id。</p>
        )}

        <div className="mb-4 rounded-md border border-zinc-800 bg-zinc-950/40 p-3">
          <p className="mb-2 text-xs font-medium text-zinc-400">新建 / 更新期次 meta</p>
          <div className="flex flex-wrap gap-2">
            <input
              value={competitorNewEditionId}
              onChange={(e) => setCompetitorNewEditionId(e.target.value)}
              placeholder="edition_id"
              className="w-36 rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-200"
            />
            <select
              value={competitorNewKind}
              onChange={(e) => setCompetitorNewKind(e.target.value as "annual" | "interim")}
              className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-200"
            >
              <option value="annual">年报</option>
              <option value="interim">半年报</option>
            </select>
            <input
              value={competitorNewLabel}
              onChange={(e) => setCompetitorNewLabel(e.target.value)}
              placeholder="展示名"
              className="w-36 rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-200"
            />
            <label className="flex items-center gap-1 text-xs text-zinc-500">
              <input
                type="checkbox"
                checked={competitorNewHasVertical}
                onChange={(e) => setCompetitorNewHasVertical(e.target.checked)}
              />
              含纵向
            </label>
            <button
              type="button"
              disabled={competitorEditionBusy}
              onClick={handleCreateCompetitorEdition}
              className="rounded border border-zinc-600 px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
            >
              保存期次
            </button>
          </div>
        </div>

        <ul className="mb-3 list-inside list-disc space-y-1 text-xs text-zinc-500">
          <li>
            产物目录：
            <code className="text-zinc-400">uploads/competitor/editions/&#123;edition_id&#125;/</code>
            + <code className="text-zinc-400">current.json</code>
          </li>
          <li>旧单例会在首次读取时自动迁入 <code className="text-zinc-400">2025-annual</code>。</li>
        </ul>

        <div className="mb-3 flex flex-wrap items-center gap-3 text-xs text-zinc-400">
          <label className="flex items-center gap-2">
            上传到期次
            <select
              value={competitorUploadEditionId}
              onChange={(e) => setCompetitorUploadEditionId(e.target.value)}
              className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-zinc-200"
            >
              {!competitorEditions.some((e) => e.edition_id === competitorUploadEditionId) ? (
                <option value={competitorUploadEditionId}>{competitorUploadEditionId}</option>
              ) : null}
              {competitorEditions.map((ed) => (
                <option key={ed.edition_id} value={ed.edition_id}>
                  {ed.period_label} ({ed.edition_id})
                </option>
              ))}
              {competitorEditions.length === 0 ? (
                <>
                  <option value="2025-annual">2025-annual</option>
                  <option value="2026-h1">2026-h1</option>
                </>
              ) : null}
            </select>
          </label>
          <label className="flex items-center gap-1">
            <input
              type="checkbox"
              checked={competitorSetAsCurrent}
              onChange={(e) => setCompetitorSetAsCurrent(e.target.checked)}
            />
            同时设为侧栏默认
          </label>
        </div>

        <input
          ref={competitorFileRef}
          type="file"
          accept=".md,text/markdown"
          className="hidden"
          onChange={handleCompetitorUpload}
          disabled={competitorUploading}
        />
        <button
          type="button"
          onClick={() => competitorFileRef.current?.click()}
          disabled={competitorUploading || !competitorUploadEditionId.trim()}
          className="rounded-md border border-zinc-600 bg-zinc-800 px-4 py-2 text-sm text-zinc-200 hover:bg-zinc-700 disabled:opacity-50"
        >
          {competitorUploading ? "上传解析中…" : "选择并上传 .md"}
        </button>
        {competitorMessage && (
          <p className={`mt-3 text-sm ${competitorMessage.type === "success" ? "text-emerald-400" : "text-red-400"}`}>
            {competitorMessage.text}
          </p>
        )}
        {competitorMessage?.type === "success" && (
          <p className="mt-2 flex flex-wrap gap-3">
            <Link href="/competitor" className="text-sm text-blue-400 hover:text-blue-300">
              打开侧栏默认 →
            </Link>
            <Link
              href={`/competitor/e/${encodeURIComponent(competitorUploadEditionId)}`}
              className="text-sm text-blue-400 hover:text-blue-300"
            >
              打开本期 →
            </Link>
          </p>
        )}
        <ParseWarningList warnings={competitorWarnings} label="竞品汇析解析告警" />
      </div>

      {/* 5. 上传纵向分析 PDF zip（Docling） */}
      <div className="mb-6 max-w-2xl rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
        <h2 className="mb-3 text-sm font-medium text-zinc-300">上传纵向分析 PDF（zip · Docling）</h2>
        <p className="mb-2 text-xs text-zinc-500">
          仅对 <code className="text-zinc-400">has_vertical=true</code> 的期次开放。写入
          <code className="text-zinc-400"> editions/&#123;edition_id&#125;/</code>；纵向页用
          <code className="text-zinc-400"> ?edition=</code> 打开对应期。
        </p>
        <label className="mb-3 block text-xs text-zinc-500">
          纵向上传期次
          <select
            value={verticalUploadEditionId}
            onChange={(e) => {
              setVerticalUploadEditionId(e.target.value);
              refreshVerticalSnapshotWarnings(e.target.value);
            }}
            className="mt-1 w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-200"
          >
            {competitorEditions.filter((e) => e.has_vertical).length === 0 ? (
              <option value="">无可上传纵向的期次</option>
            ) : null}
            {competitorEditions
              .filter((e) => e.has_vertical)
              .map((ed) => (
                <option key={ed.edition_id} value={ed.edition_id}>
                  {ed.period_label} ({ed.edition_id})
                </option>
              ))}
          </select>
        </label>
        <ul className="mb-3 list-inside list-disc space-y-1 text-xs text-zinc-500">
          <li>
            文件名须含 canonical 代号（如 <code className="text-zinc-400">wm2025_report.pdf</code>、
            <code className="text-zinc-400">37.pdf</code>），或已在 uploads 卷配置
            <code className="text-zinc-400">competitor/vertical_company_rules.json</code> 匹配内网中文 PDF 名。
          </li>
          <li>
            解析产物写入{" "}
            <code className="text-zinc-400">
              uploads/competitor/editions/&#123;edition_id&#125;/vertical.snapshot.json
            </code>
            。
          </li>
          <li>Docling 解析完成后也会存档 PDF，纵向页可切换「PDF 原文」与「结构化」对照。</li>
          <li>Docling 单线程排队，7 份 PDF 可能需数分钟；可离开页面后刷新查看进度。</li>
          <li>不走「大 PDF 知识库」队列；与 <code className="text-zinc-400">/utils/pdf-knowledge</code> 独立。</li>
        </ul>
        <input
          ref={verticalIngestFileRef}
          type="file"
          accept=".zip,application/zip"
          className="hidden"
          onChange={handleVerticalIngestUpload}
          disabled={verticalIngestUploading || !verticalUploadEditionId}
        />
        <button
          type="button"
          onClick={() => verticalIngestFileRef.current?.click()}
          disabled={verticalIngestUploading || !verticalUploadEditionId}
          className="rounded-md border border-zinc-600 bg-zinc-800 px-4 py-2 text-sm text-zinc-200 hover:bg-zinc-700 disabled:opacity-50"
        >
          {verticalIngestUploading ? "解析中…" : "选择并上传 PDF zip"}
        </button>
        {verticalIngestUploading && verticalIngestStatus ? (
          <p className="mt-3 text-sm text-zinc-400">
            {verticalIngestStatus.status === "running" && verticalIngestStatus.current_company
              ? `正在解析：${verticalIngestStatus.current_company}（${verticalIngestStatus.companies_done ?? 0}/${verticalIngestStatus.companies_total ?? "?"}）`
              : "已排队，等待 Docling…"}
            {typeof verticalIngestStatus.progress === "number" ? ` · ${verticalIngestStatus.progress}%` : ""}
          </p>
        ) : null}
        {verticalMessage && verticalMessageSource === "zip" ? (
          <p className={`mt-3 text-sm ${verticalMessage.type === "success" ? "text-emerald-400" : "text-red-400"}`}>
            {verticalMessage.text}
          </p>
        ) : null}
        {verticalMessage?.type === "success" && verticalMessageSource === "zip" ? (
          <p className="mt-2">
            <Link
              href={`/competitor/vertical?edition=${encodeURIComponent(verticalUploadEditionId)}`}
              className="text-sm text-blue-400 hover:text-blue-300"
            >
              打开纵向对比页 →
            </Link>
          </p>
        ) : null}
        <div className="mt-4 border-t border-zinc-800 pt-4">
          <p className="mb-2 text-xs text-zinc-500">
            若尚未存档 PDF，可在此快速上传 zip（不跑 Docling）；纵向对比页将直接预览 PDF。
          </p>
          <input
            ref={verticalPdfOnlyFileRef}
            type="file"
            accept=".zip,application/zip"
            className="hidden"
            onChange={handleVerticalPdfOnlyUpload}
            disabled={verticalPdfOnlyUploading || verticalIngestUploading || !verticalUploadEditionId}
          />
          <button
            type="button"
            onClick={() => verticalPdfOnlyFileRef.current?.click()}
            disabled={verticalPdfOnlyUploading || verticalIngestUploading || !verticalUploadEditionId}
            className="rounded-md border border-zinc-700 bg-zinc-900 px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
          >
            {verticalPdfOnlyUploading ? "存档中…" : "仅存档 PDF zip（不解析）"}
          </button>
        </div>
        <ParseWarningList
          warnings={verticalSnapshotWarnings}
          label="当前 snapshot 解析告警（含 dual value 等，刷新页面仍可查看）"
        />
      </div>

      {/* 6. 上传纵向分析 MD（人工修正） */}
      <div className="mb-6 max-w-2xl rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
        <h2 className="mb-3 text-sm font-medium text-zinc-300">上传纵向分析（Markdown · 人工修正）</h2>
        <p className="mb-2 text-xs text-zinc-500">
          可选：Docling 解析后若少数表格需修正，可编辑 MD 后在此覆写；须含 <code className="text-zinc-400">## 1. 公司名</code>{" "}
          章节。写入上方所选纵向期次。
        </p>
        <ul className="mb-3 list-inside list-disc space-y-1 text-xs text-zinc-500">
          <li>
            同时写入{" "}
            <code className="text-zinc-400">editions/&#123;id&#125;/vertical_report.md</code> 与{" "}
            <code className="text-zinc-400">vertical.snapshot.json</code>。
          </li>
        </ul>
        <input
          ref={verticalFileRef}
          type="file"
          accept=".md,text/markdown"
          className="hidden"
          onChange={handleVerticalUpload}
          disabled={verticalUploading || !verticalUploadEditionId}
        />
        <button
          type="button"
          onClick={() => verticalFileRef.current?.click()}
          disabled={verticalUploading || !verticalUploadEditionId}
          className="rounded-md border border-zinc-600 bg-zinc-800 px-4 py-2 text-sm text-zinc-200 hover:bg-zinc-700 disabled:opacity-50"
        >
          {verticalUploading ? "上传解析中…" : "选择并上传 .md"}
        </button>
        {verticalMessage && verticalMessageSource === "md" ? (
          <p className={`mt-3 text-sm ${verticalMessage.type === "success" ? "text-emerald-400" : "text-red-400"}`}>
            {verticalMessage.text}
          </p>
        ) : null}
        {verticalMessage?.type === "success" && verticalMessageSource === "md" ? (
          <p className="mt-2">
            <Link
              href={`/competitor/vertical?edition=${encodeURIComponent(verticalUploadEditionId)}`}
              className="text-sm text-blue-400 hover:text-blue-300"
            >
              打开纵向对比页 →
            </Link>
          </p>
        ) : null}
        {verticalMessageSource === "md" ? (
          <ParseWarningList warnings={verticalSnapshotWarnings} label="本次 MD 上传解析告警" />
        ) : null}
      </div>

      {/* 3. 设置财务后台路径 */}
      <div className="max-w-md rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
        <h2 className="mb-3 text-sm font-medium text-zinc-300">设置财务后台路径</h2>
        <p className="mb-3 text-xs text-zinc-500">
          默认路径为 {DEFAULT_FINANCE_PATH}，可修改为仅含字母、数字、下划线的单段路径。修改保存后，请使用新路径访问本页。
        </p>
        <div className="flex flex-wrap items-end gap-2">
          <div className="min-w-[120px]">
            <label className="mb-1 block text-xs text-zinc-500">当前路径</label>
            <input
              type="text"
              value={financePathEdit}
              onChange={(e) => setFinancePathEdit(e.target.value)}
              placeholder={DEFAULT_FINANCE_PATH}
              className="w-full rounded-md border border-zinc-600 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 placeholder-zinc-500"
            />
          </div>
          <button
            type="button"
            onClick={handleSaveFinancePath}
            disabled={pathSaving}
            className="rounded-md border border-zinc-600 bg-zinc-800 px-4 py-2 text-sm text-zinc-200 hover:bg-zinc-700 disabled:opacity-50"
          >
            {pathSaving ? "保存中…" : "保存路径"}
          </button>
        </div>
        {pathMessage && (
          <p className={`mt-2 text-sm ${pathMessage.type === "success" ? "text-emerald-400" : "text-red-400"}`}>
            {pathMessage.text}
          </p>
        )}
        {financePath !== DEFAULT_FINANCE_PATH && (
          <p className="mt-2 text-xs text-zinc-500">
            提示：你已将财务后台路径改为 <span className="text-zinc-300">{financePath}</span>，默认路径{" "}
            <span className="text-zinc-300">{DEFAULT_FINANCE_PATH}</span> 将返回 404（最多约 5 秒生效）。
          </p>
        )}
      </div>
    </div>
  );
}
