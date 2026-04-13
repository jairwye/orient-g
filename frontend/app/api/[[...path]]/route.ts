/**
 * 将 /api/* 代理到后端，并转发全部请求头（含 Authorization），
 * 以便关闭标签页后仅靠 sessionStorage 的 token 不再存在、重新开页需登录。
 */
// 本地开发用 API_URL 或默认 127.0.0.1:8000；Docker 中 compose 传 API_BASE_SERVER
const RAW_BACKEND_BASE = process.env.API_URL || process.env.API_BASE_SERVER || "http://127.0.0.1:8000";
// 避免 Node fetch 在 localhost 解析到 ::1 而后端仅监听 IPv4 导致 502
const BACKEND_BASE = RAW_BACKEND_BASE.replace("://localhost", "://127.0.0.1");

// #region agent log
fetch('http://127.0.0.1:7661/ingest/23552c26-aa5a-4956-8d58-0ca24af11a9c',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'6378ff'},body:JSON.stringify({sessionId:'6378ff',runId:'pre-fix',hypothesisId:'A',location:'frontend/app/api/[[...path]]/route.ts:module',message:'proxy module loaded',data:{RAW_BACKEND_BASE:String(RAW_BACKEND_BASE||''),BACKEND_BASE:String(BACKEND_BASE||'')},timestamp:Date.now()})}).catch(()=>{});
// #endregion

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
  // #region agent log
  fetch('http://127.0.0.1:7661/ingest/23552c26-aa5a-4956-8d58-0ca24af11a9c',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'6378ff'},body:JSON.stringify({sessionId:'6378ff',runId:'pre-fix',hypothesisId:'A',location:'frontend/app/api/[[...path]]/route.ts:proxy',message:'proxy request',data:{method,String_url:String(request.url||''),backendUrl:String(backendUrl||''),contentType:String(request.headers.get('content-type')||''),hasBody:method!=='GET'&&method!=='HEAD'},timestamp:Date.now()})}).catch(()=>{});
  // #endregion
  const headers = new Headers(request.headers);
  // 移除 hop-by-hop 与易导致 Node fetch 失败的头
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
  if (method !== "GET" && method !== "HEAD") {
    const contentType = request.headers.get("content-type") || "";
    if (contentType.toLowerCase().includes("multipart/form-data")) {
      // Next/Undici 在某些环境下转发 multipart 流会出现 fetch failed，这里改为 buffer 转发更稳
      const ab = await request.arrayBuffer();
      init.body = Buffer.from(ab);
      headers.delete("content-length");
    } else if (request.body) {
      init.body = request.body;
      (init as RequestInit & { duplex?: string }).duplex = "half"; // Node fetch 要求流式 body 时设置
    }
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
    const e = err as any;
    // #region agent log
    fetch('http://127.0.0.1:7661/ingest/23552c26-aa5a-4956-8d58-0ca24af11a9c',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'6378ff'},body:JSON.stringify({sessionId:'6378ff',runId:'pre-fix',hypothesisId:'B',location:'frontend/app/api/[[...path]]/route.ts:catch',message:'proxy fetch failed',data:{method,backendUrl:String(backendUrl||''),errType:String(e?.name||typeof err),errMsg:String(e?.message||''),errCode:String(e?.code||''),stackHead:String(e?.stack||'').slice(0,800)},timestamp:Date.now()})}).catch(()=>{});
    // #endregion
    // 后端不可达时返回 JSON 而非 HTML 错误页，避免前端把 HTML 当 JSON 解析导致登录态错乱
    return new Response(
      JSON.stringify({ detail: "后端服务不可用，请确认已启动" }),
      { status: 502, headers: { "Content-Type": "application/json" } }
    );
  }
}
