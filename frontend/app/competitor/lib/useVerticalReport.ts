"use client";

import { useCallback, useEffect, useState } from "react";
import { getAuthHeaders } from "../../lib/auth";
import type { VerticalReportSnapshot } from "./vertical_types";

type State =
  | { status: "loading" }
  | { status: "empty" }
  | { status: "no_vertical" }
  | { status: "error"; message: string }
  | { status: "ready"; data: VerticalReportSnapshot };

export function useVerticalReport(editionId?: string | null) {
  const [state, setState] = useState<State>({ status: "loading" });

  const reload = useCallback(async () => {
    setState({ status: "loading" });
    try {
      const q = editionId ? `?edition=${encodeURIComponent(editionId)}` : "";
      const res = await fetch(`/api/competitor/vertical-report${q}`, {
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
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        const msg = typeof err.detail === "string" ? err.detail : `加载失败（${res.status}）`;
        setState({ status: "error", message: msg });
        return;
      }
      const data = (await res.json()) as VerticalReportSnapshot;
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
