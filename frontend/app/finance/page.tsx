"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { getAuthHeaders } from "../lib/auth";
import { DEFAULT_EQUITY_SNAPSHOT, useEquitySnapshotName } from "../lib/equitySnapshot";

const DEFAULT_FINANCE_PATH = "/finance";

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

  useEffect(() => {
    fetch("/api/settings", { credentials: "include", headers: getAuthHeaders() })
      .then((r) => (r.ok ? r.json() : { finance_path: DEFAULT_FINANCE_PATH }))
      .then((data: { finance_path?: string }) => {
        const p = (data.finance_path ?? DEFAULT_FINANCE_PATH).trim();
        setFinancePath(p);
        setFinancePathEdit(p);
      })
      .catch(() => {});
  }, []);

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
      const statLine = statBits.length ? `；${statBits.join("、")}` : "";
      setCompetitorMessage({
        type: "success",
        text: `已解析 ${data.sections_parsed ?? 9} 章（sec-01～sec-09）${statLine}。侧栏「竞品财报」已更新。`,
      });
    } catch (err) {
      setCompetitorMessage({
        type: "error",
        text: err instanceof Error ? err.message : "上传失败",
      });
    } finally {
      setCompetitorUploading(false);
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

      {/* 4. 上传竞品财报汇析 MD */}
      <div className="mb-6 max-w-2xl rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
        <h2 className="mb-3 text-sm font-medium text-zinc-300">上传竞品财报汇析（Markdown）</h2>
        <p className="mb-2 text-xs text-zinc-500">
          上传后将解析为侧栏「竞品财报」分析页数据；与当前财务后台 URL 路径无关。
        </p>
        <ul className="mb-3 list-inside list-disc space-y-1 text-xs text-zinc-500">
          <li>仅修改仓库 <code className="text-zinc-400">uploads/*.md</code> 不会自动生效，须在此上传生成运行时 Snapshot。</li>
          <li>解析产物写入 <code className="text-zinc-400">uploads/competitor/report.snapshot.json</code>。</li>
          <li>本地开发若从未上传，竞品页会回退 minimal 预览数据（政府补助明细、sec-09-10 之后等屏会占位）。</li>
          <li>完整蓝本须含 <code className="text-zinc-400">sec-09-10</code>～<code className="text-zinc-400">sec-09-15</code> 及 sec-09-3 补助明细第二张表。</li>
        </ul>
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
          disabled={competitorUploading}
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
          <p className="mt-2">
            <Link href="/competitor" className="text-sm text-blue-400 hover:text-blue-300">
              打开竞品财报页 →
            </Link>
          </p>
        )}
        {competitorWarnings.length > 0 && (
          <ul className="mt-3 max-h-32 overflow-y-auto text-xs text-amber-400/90">
            {competitorWarnings.slice(0, 20).map((w) => (
              <li key={w}>{w}</li>
            ))}
            {competitorWarnings.length > 20 && (
              <li>…另有 {competitorWarnings.length - 20} 条告警</li>
            )}
          </ul>
        )}
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

