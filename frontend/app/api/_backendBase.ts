/** Next.js /api 代理到 FastAPI 的基址（与 [[...path]]/route.ts 一致） */
const RAW_BACKEND_BASE = process.env.API_URL || process.env.API_BASE_SERVER || "http://127.0.0.1:8000";

export const BACKEND_BASE = RAW_BACKEND_BASE.replace("://localhost", "://127.0.0.1");

export function copyProxyHeaders(request: Request): Headers {
  const headers = new Headers(request.headers);
  for (const h of [
    "host",
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "expect",
  ]) {
    headers.delete(h);
  }
  const authz = request.headers.get("Authorization");
  if (authz) headers.set("Authorization", authz);
  const xToken = request.headers.get("X-Auth-Token");
  if (xToken) headers.set("X-Auth-Token", xToken);
  const runId = request.headers.get("X-Agent-Run-Id");
  if (runId) headers.set("X-Agent-Run-Id", runId);
  return headers;
}
