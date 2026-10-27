"use client";

import { useCallback, useEffect, useState } from "react";
import { getAuthHeaders } from "../../lib/auth";
import type { CompetitorReportSnapshot } from "./types";

type State =
  | { status: "loading" }
  | { status: "empty" }
  | { status: "error"; message: string }
  | { status: "ready"; data: CompetitorReportSnapshot };

export function useCompetitorReport(editionId?: string | null) {
  const [state, setState] = useState<State>({ status: "loading" });

  const reload = useCallback(async () => {
    setState({ status: "loading" });
    try {
      const q = editionId ? `?edition=${encodeURIComponent(editionId)}` : "";
      const res = await fetch(`/api/competitor/report${q}`, {
        credentials: "include",
        headers: getAuthHeaders(),
      });
      if (res.status === 404) {
        setState({ status: "empty" });
        return;
      }
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        const msg = typeof err.detail === "string" ? err.detail : `加载失败（${res.status}）`;
        setState({ status: "error", message: msg });
        return;
      }
      const data = (await res.json()) as CompetitorReportSnapshot;
      setState({ status: "ready", data });
    } catch {
      setState({ status: "error", message: "无法连接后端" });
    }
  }, [editionId]);

  useEffect(() => {
    reload();
  }, [reload]);

  return { state, reload };
}
