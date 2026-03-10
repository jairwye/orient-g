import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const CANONICAL_ADMIN_PATH = "/admin";

async function getAdminPath(origin: string): Promise<string> {
  try {
    const res = await fetch(new URL("/api/settings", origin), {
      next: { revalidate: 0 },
      headers: { "Cache-Control": "no-store" },
    });
    if (res.ok) {
      const data = await res.json();
      const path = typeof data?.admin_path === "string" ? data.admin_path.trim() : CANONICAL_ADMIN_PATH;
      if (path.startsWith("/") && /^\/[a-zA-Z0-9_]+$/.test(path)) {
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
  // 用 Host 头拼 origin，保证与 Caddy 的 header_up Host 一致，避免用域名访问时容器内请求 /api/settings 失败回退到 /admin
  const host = request.headers.get("host") || request.nextUrl.hostname;
  const origin = `${request.nextUrl.protocol}//${host}`;
  const adminPath = await getAdminPath(origin);

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
