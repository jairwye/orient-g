"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { getAuthHeaders, setAuthToken } from "../lib/auth";
import DashboardLayout from "./DashboardLayout";

const LOGIN_PATH = "/login";
const CHANGE_PASSWORD_PATH = "/change-password";
/** 路由切换时鉴权缓存 TTL（毫秒），已鉴权且在此时间内切换页面则跳过重复请求 */
const AUTH_CACHE_TTL_MS = 5000;

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [authCheckDone, setAuthCheckDone] = useState(false); // 未完成鉴权前不 redirect，避免登录后刚跳到 / 就被立刻 redirect 回 /login
  const [authEnabled, setAuthEnabled] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [mustChangePassword, setMustChangePassword] = useState(false);
  const initialAuthDoneRef = useRef(false); // 是否已完成首次鉴权；完成后路由切换只做静默鉴权，不卸掉侧边栏
  const lastAuthCheckRef = useRef(0); // 上次完整鉴权时间戳，用于路由切换时跳过重复请求

  useEffect(() => {
    if (pathname === LOGIN_PATH) {
      setLoading(false);
      setAuthCheckDone(false); // 在登录页时清掉，避免跳到 / 后仍用旧值 true 立刻被 redirect 回 /login
      return;
    }
    const isFirstCheck = !initialAuthDoneRef.current;
    if (isFirstCheck) {
      setLoading(true);
      setAuthCheckDone(false);
    }
    // 已鉴权且缓存未过期时跳过 fetch，减少路由切换时的重复请求
    const now = Date.now();
    if (!isFirstCheck && authenticated && now - lastAuthCheckRef.current < AUTH_CACHE_TTL_MS) {
      return;
    }
    let cancelled = false;
    let willRetry = false;
    const run = (isRetry = false) => {
      willRetry = false;
      Promise.all([
        fetch("/api/settings", { credentials: "include" }).then((r) => (r.ok ? r.json() : { auth_enabled: false })),
        fetch("/api/auth/me", { credentials: "include", headers: getAuthHeaders() }).then(async (r) => {
          const meData = await r.json().catch(() => ({}));
          if (r.ok && meData.token) setAuthToken(meData.token);
          return { ok: r.ok, must_change_password: !!meData.must_change_password, status: r.status };
        }),
      ])
        .then(([settings, me]) => {
          if (cancelled) return;
          lastAuthCheckRef.current = Date.now();
          const enabled = !!settings?.auth_enabled;
          setAuthEnabled(enabled);
          if (!enabled) {
            setAuthenticated(true);
            setMustChangePassword(false);
          } else if (me.ok) {
            setAuthenticated(true);
            setMustChangePassword(!!me.must_change_password);
          } else if (!isRetry && (me.status === 502 || me.status === 0)) {
            willRetry = true;
            setTimeout(() => run(true), 600);
            return;
          } else {
            setAuthenticated(false);
          }
        })
        .catch(() => {
          if (cancelled) return;
          if (!isRetry) {
            willRetry = true;
            setTimeout(() => run(true), 600);
          } else setAuthenticated(false);
        })
        .finally(() => {
          if (!cancelled && !willRetry) {
            initialAuthDoneRef.current = true;
            setLoading(false);
            setAuthCheckDone(true);
          }
        });
    };
    run();
    return () => {
      cancelled = true;
    };
  }, [pathname, authenticated]);

  useEffect(() => {
    if (loading || pathname === LOGIN_PATH) return;
    if (!authCheckDone) return; // 鉴权未完成不 redirect，避免登录后跳到 / 时立刻被 redirect 回 /login
    if (authEnabled && !authenticated) {
      router.replace(LOGIN_PATH);
      return;
    }
    if (authenticated && mustChangePassword && pathname !== CHANGE_PASSWORD_PATH && pathname !== LOGIN_PATH) {
      router.replace(CHANGE_PASSWORD_PATH);
    }
  }, [loading, authCheckDone, authEnabled, authenticated, mustChangePassword, pathname, router]);

  if (pathname === LOGIN_PATH || pathname === CHANGE_PASSWORD_PATH) {
    return <>{children}</>;
  }
  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-950">
        <span className="text-sm text-zinc-500">加载中…</span>
      </div>
    );
  }
  if (authEnabled && !authenticated) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-950">
        <span className="text-sm text-zinc-500">正在跳转登录…</span>
      </div>
    );
  }
  return <DashboardLayout>{children}</DashboardLayout>;
}
