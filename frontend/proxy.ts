import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const CANONICAL_ADMIN_PATH = "/admin";
const BACKEND_BASE = process.env.API_URL || process.env.API_BASE_SERVER || "http://localhost:8000";

/** 内存缓存，避免每次请求都请求后端（导致页面切换慢）；TTL 5 秒，保存路径后最多等 5 秒生效 */
let cachedPath: string | null = null;
let cacheExpiry = 0;
const CACHE_TTL_MS = 5_000;

async function getAdminPath(): Promise<string> {
  const now = Date.now();
  if (cachedPath != null && now < cacheExpiry) return cachedPath;
  try {
    const res = await fetch(`${BACKEND_BASE}/api/settings`, {
      headers: { "Cache-Control": "no-store" },
      cache: "no-store",
    });
    if (res.ok) {
      const data = await res.json();
      const path = typeof data?.admin_path === "string" ? data.admin_path.trim() : CANONICAL_ADMIN_PATH;
      if (path.startsWith("/") && /^\/[a-zA-Z0-9_]+$/.test(path)) {
        cachedPath = path;
        cacheExpiry = now + CACHE_TTL_MS;
        return path;
      }
    }
  } catch {
    // ignore
  }
  return CANONICAL_ADMIN_PATH;
}

export async function proxy(request: NextRequest) {
  const pathname = request.nextUrl.pathname;
  const adminPath = await getAdminPath();
  const origin = request.nextUrl.origin;

  if (adminPath !== CANONICAL_ADMIN_PATH && pathname === adminPath) {
    return NextResponse.rewrite(new URL(CANONICAL_ADMIN_PATH, origin));
  }

  if (adminPath !== CANONICAL_ADMIN_PATH && pathname === CANONICAL_ADMIN_PATH) {
    return new NextResponse(null, { status: 404 });
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|.*\\.).*)"],
};
