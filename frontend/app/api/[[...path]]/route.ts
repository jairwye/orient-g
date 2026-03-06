/**
 * 将 /api/* 代理到后端，并转发全部请求头（含 Authorization），
 * 以便关闭标签页后仅靠 sessionStorage 的 token 不再存在、重新开页需登录。
 */
// 本地开发用 API_URL 或默认 localhost:8000；Docker 中 compose 传 API_BASE_SERVER
const BACKEND_BASE = process.env.API_URL || process.env.API_BASE_SERVER || "http://localhost:8000";

function buildBackendUrl(path: string[], search: string): string {
  const pathPart = path.length ? `/${path.join("/")}` : "";
  return `${BACKEND_BASE}/api${pathPart}${search}`;
}

export async function GET(
  request: Request,
  context: { params: Promise<{ path?: string[] }> }
) {
  return proxy(request, await context.params, "GET");
}

export async function POST(
  request: Request,
  context: { params: Promise<{ path?: string[] }> }
) {
  return proxy(request, await context.params, "POST");
}

export async function PUT(
  request: Request,
  context: { params: Promise<{ path?: string[] }> }
) {
  return proxy(request, await context.params, "PUT");
}

export async function PATCH(
  request: Request,
  context: { params: Promise<{ path?: string[] }> }
) {
  return proxy(request, await context.params, "PATCH");
}

export async function DELETE(
  request: Request,
  context: { params: Promise<{ path?: string[] }> }
) {
  return proxy(request, await context.params, "DELETE");
}

async function proxy(
  request: Request,
  params: { path?: string[] },
  method: string
): Promise<Response> {
  const path = params.path ?? [];
  const url = new URL(request.url);
  const backendUrl = buildBackendUrl(path, url.search);
  const headers = new Headers(request.headers);
  headers.delete("host");
  // 显式转发鉴权相关头，避免在部分环境下被丢弃导致 /me 返回 401
  const authz = request.headers.get("Authorization");
  if (authz) headers.set("Authorization", authz);
  const xToken = request.headers.get("X-Auth-Token");
  if (xToken) headers.set("X-Auth-Token", xToken);
  const init: RequestInit = {
    method,
    headers,
    cache: "no-store",
  };
  if (method !== "GET" && method !== "HEAD" && request.body) {
    init.body = request.body;
    (init as RequestInit & { duplex?: string }).duplex = "half"; // Node fetch 要求流式 body 时设置
  }
  try {
    const res = await fetch(backendUrl, init);
    const resHeaders = new Headers(res.headers);
    return new Response(res.body, {
      status: res.status,
      statusText: res.statusText,
      headers: resHeaders,
    });
  } catch (err) {
    // 后端不可达时返回 JSON 而非 HTML 错误页，避免前端把 HTML 当 JSON 解析导致登录态错乱
    return new Response(
      JSON.stringify({ detail: "后端服务不可用，请确认已启动" }),
      { status: 502, headers: { "Content-Type": "application/json" } }
    );
  }
}
