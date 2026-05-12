"use client";

import { useCallback, useEffect, useState } from "react";
import { useBigpdfStore, type BigpdfSystemStatus, type BigpdfQueueStatus } from "../stores/bigpdfStore";
import { getAuthHeaders } from "../lib/auth";

interface UseDoclingStatusOptions {
  /** Poll interval in ms when page is visible */
  pollInterval?: number;
  /** Whether to start polling immediately */
  autoStart?: boolean;
}

export function useDoclingStatus(options: UseDoclingStatusOptions = {}) {
  const { pollInterval = 10000, autoStart = true } = options;

  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastFetchedAt, setLastFetchedAt] = useState<number | null>(null);

  const systemStatus = useBigpdfStore((s) => s.systemStatus);
  const queueStatus = useBigpdfStore((s) => s.queueStatus);
  const setSystemStatus = useBigpdfStore((s) => s.setSystemStatus);
  const setQueueStatus = useBigpdfStore((s) => s.setQueueStatus);

  const fetchStatus = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/knowledge/bigpdf/status", {
        credentials: "include",
        headers: getAuthHeaders(),
      });
      if (!res.ok) throw new Error("状态查询失败");
      const data = (await res.json().catch(() => ({}))) as BigpdfSystemStatus;
      setSystemStatus(data);
      setLastFetchedAt(Date.now());
      return data;
    } catch (e) {
      const msg = e instanceof Error ? e.message : "状态查询失败";
      setError(msg);
      return null;
    } finally {
      setIsLoading(false);
    }
  }, [setSystemStatus]);

  const fetchQueue = useCallback(async () => {
    try {
      const res = await fetch("/api/knowledge/bigpdf/queue", {
        credentials: "include",
        headers: getAuthHeaders(),
      });
      if (!res.ok) throw new Error("队列查询失败");
      const data = (await res.json().catch(() => ({}))) as BigpdfQueueStatus;
      setQueueStatus(data);
      return data;
    } catch (e) {
      const msg = e instanceof Error ? e.message : "队列查询失败";
      setError(msg);
      return null;
    }
  }, [setQueueStatus]);

  const forceCancel = useCallback(async () => {
    try {
      const res = await fetch("/api/knowledge/bigpdf/force-cancel", {
        method: "POST",
        credentials: "include",
        headers: getAuthHeaders(),
      });
      const data = (await res.json().catch(() => ({}))) as {
        success?: boolean;
        message?: string;
        restarted_at?: string;
      };
      if (!res.ok) throw new Error(data.message || "强制终止失败");
      // Refresh status after force cancel
      await fetchStatus();
      return { success: true, ...data };
    } catch (e) {
      const msg = e instanceof Error ? e.message : "强制终止失败";
      return { success: false, message: msg };
    }
  }, [fetchStatus]);

  // Polling effect
  useEffect(() => {
    if (!autoStart) return;

    let intervalId: number | null = null;

    const poll = () => {
      if (document.visibilityState === "visible") {
        void fetchStatus();
        void fetchQueue();
      }
    };

    // Initial fetch
    void fetchStatus();
    void fetchQueue();

    // Set up interval
    intervalId = window.setInterval(poll, pollInterval);

    // Handle visibility change
    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        void fetchStatus();
        void fetchQueue();
      }
    };
    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      if (intervalId) window.clearInterval(intervalId);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [autoStart, pollInterval, fetchStatus, fetchQueue]);

  const isBusy = Boolean(
    systemStatus?.hasRunningTask || (systemStatus?.queueLength ?? 0) > 0
  );

  const myQueuePosition = systemStatus?.queuePosition;

  const isMyTaskRunning = Boolean(
    systemStatus?.runningTask?.isMine && systemStatus?.hasRunningTask
  );

  return {
    systemStatus,
    queueStatus,
    isLoading,
    error,
    lastFetchedAt,
    isBusy,
    myQueuePosition,
    isMyTaskRunning,
    fetchStatus,
    fetchQueue,
    forceCancel,
  };
}
