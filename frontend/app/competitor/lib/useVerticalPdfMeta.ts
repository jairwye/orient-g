"use client";

import { useCallback, useEffect, useState } from "react";
import { getAuthHeaders } from "../../lib/auth";

export type VerticalPdfMeta = {
  uploaded_at?: string;
  uploaded_by?: string;
  source_filename?: string;
  company_count?: number;
  companies?: { id: string; name: string; filename?: string }[];
};

export type VerticalPdfMetaState =
  | { status: "loading" }
  | { status: "empty" }
  | { status: "ready"; data: VerticalPdfMeta }
  | { status: "error"; message: string };

export function useVerticalPdfMeta() {
  const [state, setState] = useState<VerticalPdfMetaState>({ status: "loading" });

  const reload = useCallback(async () => {
    setState({ status: "loading" });
    try {
      const res = await fetch("/api/competitor/vertical-pdf/meta", {
        credentials: "include",
        headers: getAuthHeaders(),
      });
      if (res.status === 404) {
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
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { state, reload };
}
