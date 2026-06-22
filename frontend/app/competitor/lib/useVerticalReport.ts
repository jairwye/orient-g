"use client";

import { useCallback, useEffect, useState } from "react";
import { getAuthHeaders } from "../../lib/auth";
import type { VerticalReportSnapshot } from "./vertical_types";

type State =
  | { status: "loading" }
  | { status: "empty" }
  | { status: "error"; message: string }
  | { status: "ready"; data: VerticalReportSnapshot };

export function useVerticalReport() {
  const [state, setState] = useState<State>({ status: "loading" });

  const reload = useCallback(async () => {
    setState({ status: "loading" });
    try {
      const res = await fetch("/api/competitor/vertical-report", {
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
      const data = (await res.json()) as VerticalReportSnapshot;
      setState({ status: "ready", data });
    } catch {
      setState({ status: "error", message: "无法连接后端" });
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  return { state, reload };
}
