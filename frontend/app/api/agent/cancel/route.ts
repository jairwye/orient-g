import { NextRequest } from "next/server";
import { BACKEND_BASE, copyProxyHeaders } from "../../_backendBase";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(request: NextRequest) {
  const url = `${BACKEND_BASE}/api/agent/cancel`;
  const headers = copyProxyHeaders(request);
  const body = await request.text();
  try {
    const res = await fetch(url, {
      method: "POST",
      headers,
      body: body || undefined,
      cache: "no-store",
    });
    const text = await res.text();
    return new Response(text, {
      status: res.status,
      headers: { "Content-Type": res.headers.get("content-type") || "application/json" },
    });
  } catch {
    return new Response(JSON.stringify({ detail: "后端服务不可用，请确认已启动" }), {
      status: 502,
      headers: { "Content-Type": "application/json" },
    });
  }
}
