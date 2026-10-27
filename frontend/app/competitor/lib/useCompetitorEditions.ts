"use client";

import { useCallback, useEffect, useState } from "react";
import { getAuthHeaders } from "../../lib/auth";
import type { CompetitorEdition } from "./types";

type State =
  | { status: "loading" }
  | { status: "ready"; editions: CompetitorEdition[]; current: string | null }
  | { status: "error"; message: string };

export function useCompetitorEditions() {
  const [state, setState] = useState<State>({ status: "loading" });

  const reload = useCallback(async () => {
    setState({ status: "loading" });
    try {
      const res = await fetch("/api/competitor/editions", {
        credentials: "include",
        headers: getAuthHeaders(),
      });
      if (!res.ok) {
        setState({ status: "error", message: `加载期次失败（${res.status}）` });
        return;
      }
      const data = (await res.json()) as {
        editions?: CompetitorEdition[];
        current?: string | null;
      };
      setState({
        status: "ready",
        editions: Array.isArray(data.editions) ? data.editions : [],
        current: data.current ?? null,
      });
    } catch {
      setState({ status: "error", message: "无法连接后端" });
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  return { state, reload };
}
