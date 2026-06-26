"use client";

import { useEffect, useState } from "react";
import { getAuthHeaders } from "../../lib/auth";

type Props = {
  companyId: string;
  title?: string;
  className?: string;
  /** 标题行下方占满剩余视口，无内边距/圆角/副标题 */
  fullscreen?: boolean;
};

/** 经鉴权 fetch PDF blob 后嵌入 iframe（sessionStorage JWT 无法直挂 iframe src）。 */
export function VerticalPdfViewer({ companyId, title, className = "", fullscreen = false }: Props) {
  const [src, setSrc] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let revoked: string | null = null;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setSrc(null);

    fetch(`/api/competitor/vertical-pdf/${encodeURIComponent(companyId)}`, {
      credentials: "include",
      headers: getAuthHeaders(),
    })
      .then(async (res) => {
        if (!res.ok) {
          const t = await res.text().catch(() => "");
          throw new Error(t || `加载失败（${res.status}）`);
        }
        return res.blob();
      })
      .then((blob) => {
        if (cancelled) return;
        const url = URL.createObjectURL(blob);
        revoked = url;
        setSrc(url);
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "PDF 加载失败");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
      if (revoked) URL.revokeObjectURL(revoked);
    };
  }, [companyId]);

  const shellClass = fullscreen
    ? `flex min-h-0 flex-1 flex-col overflow-hidden bg-zinc-950 ${className}`
    : `overflow-hidden rounded-lg border border-zinc-800 bg-zinc-950 ${className}`;

  const frameClass = fullscreen ? "min-h-0 w-full flex-1 bg-white" : "h-[min(85vh,1200px)] w-full bg-white";

  const loadingMinH = fullscreen ? "min-h-0 flex-1" : "min-h-[70vh]";

  return (
    <div className={shellClass} data-testid={`vertical-pdf-${companyId}`}>
      {!fullscreen && title ? (
        <p className="border-b border-zinc-800 px-4 py-2 text-xs text-zinc-500">{title} · PDF 原文</p>
      ) : null}
      {loading ? (
        <div className={`flex items-center justify-center text-sm text-zinc-500 ${loadingMinH}`}>加载 PDF…</div>
      ) : null}
      {error ? (
        <div className={`flex items-center justify-center px-4 text-sm text-red-400 ${loadingMinH}`}>{error}</div>
      ) : null}
      {src && !error ? (
        <iframe
          title={title ? `${title} PDF` : "纵向分析 PDF"}
          src={src}
          className={frameClass}
        />
      ) : null}
    </div>
  );
}
