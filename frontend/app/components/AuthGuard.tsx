"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { getAuthHeaders, isSessionExpiredHttpStatus, redirectToLogin, setAuthToken } from "../lib/auth";
import { AuthContext } from "../contexts/AuthContext";
import DashboardLayout from "./DashboardLayout";

const LOGIN_PATH = "/login";
const CHANGE_PASSWORD_PATH = "/change-password";
/** 股权全景实验模块：仅管理员可见（2026-05） */
const EQUITY_ROUTE_PREFIXES = ["/equity", "/compare", "/analysis", "/targets"];
/** 路由切换时鉴权缓存 TTL（毫秒），已鉴权且在此时间内切换页面则跳过重复请求 */
const AUTH_CACHE_TTL_MS = 5000;

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [authCheckDone, setAuthCheckDone] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);
  const [viewBusinessDashboard, setViewBusinessDashboard] = useState(false);
  const [financePath, setFinancePath] = useState("/finance");
  const [mustChangePassword, setMustChangePassword] = useState(false);
  const initialAuthDoneRef = useRef(false);
  const lastAuthCheckRef = useRef(0);
  const authenticatedRef = useRef(false);

  useEffect(() => {
    authenticatedRef.current = authenticated;
  }, [authenticated]);

  useEffect(() => {
    if (pathname === LOGIN_PATH) {
      setLoading(false);
      setAuthCheckDone(false);
      return;
    }
    const isFirstCheck = !initialAuthDoneRef.current;
    const hasToken =
      typeof window !== "undefined" && !!sessionStorage.getItem("orient_g_token");
    if (isFirstCheck && !hasToken) {
      setLoading(true);
      setAuthCheckDone(false);
    }
    const now = Date.now();
    if (
      !isFirstCheck &&
      authenticatedRef.current &&
      now - lastAuthCheckRef.current < AUTH_CACHE_TTL_MS
    ) {
      return;
    }
    let cancelled = false;
    let willRetry = false;
    const run = (isRetry = false) => {
      willRetry = false;
      fetch("/api/auth/me", { credentials: "include", headers: getAuthHeaders() })
        .then(async (r) => {
          const meData = await r.json().catch(() => ({}));
          if (r.ok && meData.token) setAuthToken(meData.token);
          return {
            ok: r.ok,
            must_change_password: !!meData.must_change_password,
            is_admin: !!meData.is_admin,
            view_business_dashboard: !!meData.view_business_dashboard,
            finance_path: typeof meData.finance_path === "string" ? meData.finance_path.trim() || "/finance" : "/finance",
            status: r.status,
          };
        })
        .then((me) => {
          if (cancelled) return;
          lastAuthCheckRef.current = Date.now();
          if (me.ok) {
            setAuthenticated(true);
            setMustChangePassword(!!me.must_change_password);
            setIsAdmin(!!me.is_admin);
            setViewBusinessDashboard(!!me.view_business_dashboard);
            setFinancePath(me.finance_path ?? "/finance");
          } else if (!isRetry && (me.status === 502 || me.status === 0)) {
            willRetry = true;
            setTimeout(() => run(true), 600);
            return;
          } else {
            if (isSessionExpiredHttpStatus(me.status)) {
              redirectToLogin(true);
              return;
            }
            setAuthenticated(false);
            setIsAdmin(false);
            setViewBusinessDashboard(false);
          }
        })
        .catch(() => {
          if (cancelled) return;
          if (!isRetry) {
            willRetry = true;
            setTimeout(() => run(true), 600);
          } else {
            setAuthenticated(false);
            setIsAdmin(false);
            setViewBusinessDashboard(false);
          }
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
  }, [pathname]);

  /** 标签页从后台切回或窗口获焦时复检登录态，避免长时间停留同页 JWT 过期仍显示已登录 */
  useEffect(() => {
    if (pathname === LOGIN_PATH || pathname === CHANGE_PASSWORD_PATH) return;
    const recheck = () => {
      if (document.visibilityState !== "visible") return;
      fetch("/api/auth/me", { credentials: "include", headers: getAuthHeaders() })
        .then(async (r) => {
          const meData = await r.json().catch(() => ({}));
          if (r.ok && meData.token) {
            setAuthToken(meData.token);
            return;
          }
          if (isSessionExpiredHttpStatus(r.status)) {
            redirectToLogin(true);
            return;
          }
        })
        .catch(() => undefined);
    };
    document.addEventListener("visibilitychange", recheck);
    window.addEventListener("focus", recheck);
    return () => {
      document.removeEventListener("visibilitychange", recheck);
      window.removeEventListener("focus", recheck);
    };
  }, [pathname]);

  useEffect(() => {
    if (loading || pathname === LOGIN_PATH) return;
    if (!authCheckDone) return;
    if (!authenticated) {
      router.replace(LOGIN_PATH);
      return;
    }
    if (mustChangePassword && pathname !== CHANGE_PASSWORD_PATH && pathname !== LOGIN_PATH) {
      router.replace(CHANGE_PASSWORD_PATH);
      return;
    }
    // 无 view_business_dashboard（管理层/管理员/财务部）不可进入根路径经营数据页，见规划 2.a
    if (pathname === "/" && !viewBusinessDashboard) {
      router.replace("/ai-interaction");
      return;
    }
    // 非管理员不可进入管理后台（仅管理员可见入口，直接输入 URL 也须拦截）
    if (pathname.startsWith("/admin") && !isAdmin) {
      router.replace("/ai-interaction");
      return;
    }
    // 非管理员不可进入财务后台（含自定义路径，规划 2.a：仅管理员可进）
    if ((pathname === financePath || pathname === "/finance") && !isAdmin) {
      router.replace("/ai-interaction");
      return;
    }
    // 股权全景及相关分析页：仅管理员
    if (
      !isAdmin &&
      EQUITY_ROUTE_PREFIXES.some((p) => pathname === p || pathname.startsWith(`${p}/`))
    ) {
      router.replace("/ai-interaction");
    }
  }, [loading, authCheckDone, authenticated, mustChangePassword, pathname, router, viewBusinessDashboard, isAdmin, financePath]);

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
  if (!authenticated) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-950">
        <span className="text-sm text-zinc-500">正在跳转登录…</span>
      </div>
    );
  }
  // 权限不足时只渲染跳转中占位，不渲染受保护页面（避免一闪而过）；实际重定向在 useEffect 中执行，不可在 render 里调用 router.replace
  const unauthorizedRedirect = (
    <div className="flex min-h-screen items-center justify-center bg-zinc-950">
      <span className="text-sm text-zinc-500">正在跳转…</span>
    </div>
  );
  if (authCheckDone && authenticated && !mustChangePassword) {
    if (pathname === "/" && !viewBusinessDashboard) {
      return unauthorizedRedirect;
    }
    if (pathname.startsWith("/admin") && !isAdmin) {
      return unauthorizedRedirect;
    }
    if ((pathname === financePath || pathname === "/finance") && !isAdmin) {
      return unauthorizedRedirect;
    }
  }
  return (
    <AuthContext.Provider value={{ is_admin: isAdmin, view_business_dashboard: viewBusinessDashboard }}>
      <DashboardLayout>{children}</DashboardLayout>
    </AuthContext.Provider>
  );
}
