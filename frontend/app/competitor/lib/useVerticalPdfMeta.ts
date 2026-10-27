"use client";

import { useCallback, useEffect, useState } from "react";
import { getAuthHeaders } from "../../lib/auth";

export type VerticalPdfMeta = {
  uploaded_at?: string;
  uploaded_by?: string;
  source_filename?: string;
  company_count?: number;
  companies?: { id: string; name: string; filename?: string }[];
  edition_id?: string;
};

export type VerticalPdfMetaState =
  | { status: "loading" }
  | { status: "empty" }
  | { status: "no_vertical" }
  | { status: "ready"; data: VerticalPdfMeta }
  | { status: "error"; message: string };

export function useVerticalPdfMeta(editionId?: string | null) {
  const [state, setState] = useState<VerticalPdfMetaState>({ status: "loading" });

  const reload = useCallback(async () => {
    setState({ status: "loading" });
    try {
      const q = editionId ? `?edition=${encodeURIComponent(editionId)}` : "";
      const res = await fetch(`/api/competitor/vertical-pdf/meta${q}`, {
        credentials: "include",
        headers: getAuthHeaders(),
      });
      if (res.status === 404) {
        const err = await res.json().catch(() => ({}));
        if (err?.detail === "no_vertical") {
          setState({ status: "no_vertical" });
          return;
        }
        setState({ status: "empty" });
        return;
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = (await res.json()) as VerticalPdfMeta;
      setState({ status: "ready", data });
    } catch (e: unknown) {
      setState({
        status: "error",
        message: e instanceof Error ? e.message : "加载 PDF 元数据失败",
      });
    }
  }, [editionId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { state, reload };
}
