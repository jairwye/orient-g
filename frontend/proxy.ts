import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// NOTE: 财务后台路径 rewrite 已迁移至 frontend/middleware.ts（Next.js 自动加载）。
// 本文件保留作逻辑对照；修改时请同步 middleware.ts。

const CANONICAL_FINANCE_PATH = "/finance";
const RAW_BACKEND_BASE = process.env.API_URL || process.env.API_BASE_SERVER || "http://127.0.0.1:8000";
const BACKEND_BASE = RAW_BACKEND_BASE.replace("://localhost", "://127.0.0.1");

/** 内存缓存，避免每次请求都请求后端（导致页面切换慢）；TTL 5 秒，保存路径后最多等 5 秒生效 */
let cachedPath: string | null = null;
let cacheExpiry = 0;
const CACHE_TTL_MS = 5_000;

async function getFinancePath(): Promise<string> {
  const now = Date.now();
  if (cachedPath != null && now < cacheExpiry) return cachedPath;
  try {
    const res = await fetch(`${BACKEND_BASE}/api/settings/public`, {
      headers: { "Cache-Control": "no-store" },
      cache: "no-store",
    });
    if (res.ok) {
      const data = await res.json();
      const path = typeof data?.finance_path === "string" ? data.finance_path.trim() : CANONICAL_FINANCE_PATH;
      if (path.startsWith("/") && /^\/[a-zA-Z0-9_]+$/.test(path)) {
        cachedPath = path;
        cacheExpiry = now + CACHE_TTL_MS;
        return path;
      }
    }
  } catch {
    // ignore
  }
  return CANONICAL_FINANCE_PATH;
}

export async function proxy(request: NextRequest) {
  const pathname = request.nextUrl.pathname;
  const financePath = await getFinancePath();
  const origin = request.nextUrl.origin;

  // 财务后台：canonical 为 /finance；若用户配置了其他路径，则将配置路径 rewrite 到 /finance
  if (financePath !== CANONICAL_FINANCE_PATH && pathname === financePath) {
    return NextResponse.rewrite(new URL(CANONICAL_FINANCE_PATH, origin));
  }

  // 若财务后台路径被改走，则 canonical /finance 不再对外暴露（避免同时存在两个入口）
  if (financePath !== CANONICAL_FINANCE_PATH && pathname === CANONICAL_FINANCE_PATH) {
    return new NextResponse(null, { status: 404 });
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|.*\\.).*)"],
};
