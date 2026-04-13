"use client";

import { useEffect, useState } from "react";
import { getAuthHeaders } from "./auth";

type LatestSnapshotResponse = { snapshot_name: string };

/**
 * 股权相关页共用：URL/调用方若已给出 snapshot 则沿用；否则拉取最新一批次。
 */
export function useEquitySnapshotName(initialTrimmed: string) {
  const [snapshotName, setSnapshotName] = useState(() => initialTrimmed.trim());

  useEffect(() => {
    if (snapshotName.trim()) return;
    let cancelled = false;
    fetch("/api/equity/snapshots/latest", {
      cache: "no-store",
      credentials: "include",
      headers: getAuthHeaders(),
    })
      .then(async (r) => {
        if (!r.ok) throw new Error(await r.text());
        return (await r.json()) as LatestSnapshotResponse;
      })
      .then((d) => {
        if (cancelled) return;
        if (d?.snapshot_name) setSnapshotName(d.snapshot_name);
      })
      .catch(() => {
        /* 无数据或无权限：保留空，由页面提示手输 */
      });
    return () => {
      cancelled = true;
    };
  }, [snapshotName]);

  return { snapshotName, setSnapshotName };
}
