import { NextRequest } from "next/server";
import { BACKEND_BASE, copyProxyHeaders } from "../../../_backendBase";

/** Agent SSE 长连接：避免 catch-all 代理默认 ~300s 超时导致 502 */
export const maxDuration = 900;
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(request: NextRequest) {
  const url = `${BACKEND_BASE}/api/agent/chat/stream`;
  const headers = copyProxyHeaders(request);
  const init: RequestInit & { duplex?: "half" } = {
    method: "POST",
    headers,
    cache: "no-store",
  };
  if (request.body) {
    init.body = request.body;
    init.duplex = "half";
  }
  try {
    const res = await fetch(url, init);
    const outHeaders = new Headers();
    const ct = res.headers.get("content-type");
    if (ct) outHeaders.set("Content-Type", ct);
    outHeaders.set("Cache-Control", "no-cache");
    outHeaders.set("Connection", "keep-alive");
    outHeaders.set("X-Accel-Buffering", "no");
    return new Response(res.body, { status: res.status, statusText: res.statusText, headers: outHeaders });
  } catch {
    return new Response(JSON.stringify({ detail: "后端服务不可用，请确认已启动" }), {
      status: 502,
      headers: { "Content-Type": "application/json" },
    });
  }
}
