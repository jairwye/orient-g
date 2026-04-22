"use client";

import type { Dispatch, SetStateAction } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

export type SmartPollOptions<T> = {
  enabled: boolean;
  load: () => Promise<T>;
  isTerminal: (data: T) => boolean;
  isActive: (data: T) => boolean;
  activeMs: number;
  stableMs: number;
  errorMaxMs: number;
  errorCooldownMs: number;
  errorCooldownAfter: number;
  initialData?: T;
};

export type UseSmartPollResult<T> = {
  data: T | undefined;
  setData: Dispatch<SetStateAction<T | undefined>>;
  phase: "idle" | "polling" | "cooldown" | "stopped";
  errorCount: number;
  /** 立即触发一次（若当前未启用或已终止，则不触发；会清除 cooldown 并重置 errorCount）。 */
  trigger: () => void;
};

function clampMs(ms: number): number {
  if (!Number.isFinite(ms)) return 0;
  return Math.max(0, Math.floor(ms));
}

function calcBackoffMs(errorCount: number, errorMaxMs: number): number {
  const baseMs = 1000;
  const exp = Math.max(0, errorCount - 1);
  return clampMs(Math.min(errorMaxMs, baseMs * Math.pow(2, exp)));
}

export function useSmartPoll<T>(opts: SmartPollOptions<T>): UseSmartPollResult<T> {
  const {
    enabled,
    load,
    isTerminal,
    isActive,
    activeMs,
    stableMs,
    errorMaxMs,
    errorCooldownMs,
    errorCooldownAfter,
    initialData,
  } = opts;

  const [data, setData] = useState<T | undefined>(initialData);
  const [phase, setPhase] = useState<"idle" | "polling" | "cooldown" | "stopped">("idle");
  const [errorCount, setErrorCount] = useState(0);
  const [cooldownUntil, setCooldownUntil] = useState<number | null>(null);

  const timeoutRef = useRef<number | null>(null);
  const inFlightRef = useRef(false);
  const runSeqRef = useRef(0);
  const mountedRef = useRef(false);
  const forceRunRef = useRef(false);

  const enabledRef = useRef(enabled);
  const dataRef = useRef<T | undefined>(data);
  const errorCountRef = useRef(errorCount);
  const cooldownUntilRef = useRef<number | null>(cooldownUntil);

  useEffect(() => {
    enabledRef.current = enabled;
  }, [enabled]);
  useEffect(() => {
    dataRef.current = data;
  }, [data]);
  useEffect(() => {
    errorCountRef.current = errorCount;
  }, [errorCount]);
  useEffect(() => {
    cooldownUntilRef.current = cooldownUntil;
  }, [cooldownUntil]);

  const clearTimer = useCallback(() => {
    if (timeoutRef.current == null) return;
    window.clearTimeout(timeoutRef.current);
    timeoutRef.current = null;
  }, []);

  const schedule = useCallback(
    (ms: number, fn: () => void) => {
      clearTimer();
      timeoutRef.current = window.setTimeout(fn, clampMs(ms));
    },
    [clearTimer]
  );

  const terminalNow = useMemo(() => {
    if (!data) return false;
    return Boolean(isTerminal(data));
  }, [data, isTerminal]);

  const pollIntervalMs = useMemo(() => {
    if (!data) return clampMs(activeMs);
    const businessActive = Boolean(isActive(data));
    return clampMs(businessActive ? activeMs : stableMs);
  }, [activeMs, data, isActive, stableMs]);

  const runOnce = useCallback(async () => {
    if (!mountedRef.current) return;
    if (!enabledRef.current) return;
    if (inFlightRef.current) return;

    const currentData = dataRef.current;
    if (currentData && isTerminal(currentData)) {
      setPhase("stopped");
      return;
    }

    inFlightRef.current = true;
    clearTimer();
    const seq = (runSeqRef.current += 1);

    try {
      const next = await load();
      if (!mountedRef.current) return;
      if (seq !== runSeqRef.current) return;

      setData(next);
      setErrorCount(0);
      setCooldownUntil(null);

      if (isTerminal(next)) {
        setPhase("stopped");
        return;
      }

      setPhase("polling");
    } catch {
      if (!mountedRef.current) return;
      if (seq !== runSeqRef.current) return;

      const nextCount = errorCountRef.current + 1;
      setErrorCount(nextCount);

      if (nextCount >= errorCooldownAfter) {
        const until = Date.now() + clampMs(errorCooldownMs);
        setCooldownUntil(until);
        setPhase("cooldown");
      } else {
        setPhase("polling");
      }
    } finally {
      inFlightRef.current = false;
    }
  }, [clearTimer, errorCooldownAfter, errorCooldownMs, isTerminal, load]);

  const trigger = useCallback(() => {
    if (!enabledRef.current) return;
    const currentData = dataRef.current;
    if (currentData && isTerminal(currentData)) return;
    // 手动触发：清除 cooldown 并重置错误计数，下一轮立即执行。
    forceRunRef.current = true;
    setErrorCount(0);
    setCooldownUntil(null);
    setPhase("idle");
  }, [isTerminal]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    if (!enabled || terminalNow) {
      clearTimer();
      runSeqRef.current += 1;
      setCooldownUntil(null);
      setPhase("stopped");
      return;
    }

    if (phase === "stopped") setPhase("idle");

    return () => {
      clearTimer();
      runSeqRef.current += 1;
    };
  }, [clearTimer, enabled, phase, terminalNow]);

  useEffect(() => {
    if (!enabled) return;
    if (terminalNow) return;

    if (phase === "idle") {
      forceRunRef.current = false;
      schedule(0, () => void runOnce());
      return;
    }

    if (phase === "cooldown") {
      const until = cooldownUntilRef.current;
      const remaining = until == null ? 0 : Math.max(0, until - Date.now());
      schedule(remaining, () => {
        if (!mountedRef.current) return;
        if (!enabledRef.current) return;
        const currentData = dataRef.current;
        if (currentData && isTerminal(currentData)) {
          setPhase("stopped");
          return;
        }
        // cooldown 到期：自动重置并继续
        setErrorCount(0);
        setCooldownUntil(null);
        void runOnce();
      });
      return;
    }

    if (phase === "polling") {
      const delay = errorCount > 0 ? calcBackoffMs(errorCount, errorMaxMs) : pollIntervalMs;
      schedule(delay, () => void runOnce());
    }
  }, [cooldownUntil, enabled, errorCount, errorMaxMs, isTerminal, phase, pollIntervalMs, runOnce, schedule, terminalNow]);

  useEffect(() => () => clearTimer(), [clearTimer]);

  return { data, setData, phase, errorCount, trigger };
}

