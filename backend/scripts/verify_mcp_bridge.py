"""一次性验证 MCP 跨进程 JWT 桥（L2）+ Hermes orientg 连通。"""
from __future__ import annotations

import json
import sys
import time
import uuid

import httpx

from backend.config import settings

BRIDGE_SECRET = (settings.orientg_mcp_bridge_secret or settings.auth_secret or "").strip()
BASE = (settings.orientg_internal_base_url or "http://127.0.0.1:8000").rstrip("/")
HERMES = (settings.hermes_base_url or "http://127.0.0.1:8642").rstrip("/")
HERMES_TOKEN = (settings.hermes_internal_token or "").strip()
FINANCE_USER = "finance_test"
FINANCE_PASS = "FinanceTest!2026"
VERIFY_CHAT_ID = "s_mcp_bridge_verify"
VERIFY_SESSION_KEY = f"orientg-{FINANCE_USER}--{VERIFY_CHAT_ID}"


def main() -> int:
    results: list[tuple[str, bool, str]] = []

    # 1) backend health
    try:
        r = httpx.get(f"{BASE}/api/health", timeout=5)
        results.append(("backend /api/health", r.status_code == 200, str(r.status_code)))
    except Exception as e:
        results.append(("backend /api/health", False, str(e)))

    # 2) hermes health
    try:
        r = httpx.get(f"{HERMES}/health", timeout=5)
        results.append(("hermes /health", r.status_code == 200, r.text[:80]))
    except Exception as e:
        results.append(("hermes /health", False, str(e)))

    # 3) bridge secret gate
    try:
        r = httpx.post(
            f"{BASE}/api/internal/hermes/session/resolve",
            json={"hermes_session_key": VERIFY_SESSION_KEY},
            timeout=5,
        )
        results.append(("bridge rejects missing secret", r.status_code == 403, str(r.status_code)))
    except Exception as e:
        results.append(("bridge rejects missing secret", False, str(e)))

    # 4) unknown session → 404（secret 正确）
    try:
        r = httpx.post(
            f"{BASE}/api/internal/hermes/session/resolve",
            json={"hermes_session_key": VERIFY_SESSION_KEY},
            headers={"X-OrientG-MCP-Bridge-Secret": BRIDGE_SECRET},
            timeout=5,
        )
        code = r.json().get("detail", {}).get("code") if r.status_code == 404 else ""
        ok = r.status_code == 404 and code == "session_not_found"
        results.append(("bridge 404 for unregistered session", ok, f"status={r.status_code} code={code}"))
    except Exception as e:
        results.append(("bridge 404 for unregistered session", False, str(e)))

    # 5) 登录 + /agent/chat 登记 session（uvicorn 进程内）
    user_jwt = ""
    try:
        lr = httpx.post(
            f"{BASE}/api/auth/login",
            json={"username": FINANCE_USER, "password": FINANCE_PASS},
            timeout=10,
        )
        user_jwt = (lr.json().get("token") or lr.json().get("access_token") or "").strip()
        ok_login = lr.status_code == 200 and bool(user_jwt)
        results.append(("finance_test login", ok_login, str(lr.status_code)))
    except Exception as e:
        results.append(("finance_test login", False, str(e)))

    if user_jwt:
        try:
            ar = httpx.post(
                f"{BASE}/api/agent/chat",
                headers={"Authorization": f"Bearer {user_jwt}"},
                json={
                    "messages": [{"role": "user", "content": "bridge-verify-ping"}],
                    "agent_mode": "fast",
                    "hermes_session_id": VERIFY_SESSION_KEY,
                    "orientg_chat_session_id": VERIFY_CHAT_ID,
                },
                timeout=120,
            )
            results.append(
                (
                    "agent/chat registers session",
                    ar.status_code == 200,
                    f"status={ar.status_code}",
                )
            )
        except Exception as e:
            results.append(("agent/chat registers session", False, str(e)))

    # 6) resolve registered session via HTTP bridge
    try:
        r = httpx.post(
            f"{BASE}/api/internal/hermes/session/resolve",
            json={"hermes_session_key": VERIFY_SESSION_KEY},
            headers={"X-OrientG-MCP-Bridge-Secret": BRIDGE_SECRET},
            timeout=5,
        )
        tok = (r.json().get("user_token") or "").strip()
        ok = r.status_code == 200 and bool(tok)
        results.append(("bridge resolve after agent/chat", ok, f"status={r.status_code} jwt_len={len(tok)}"))
    except Exception as e:
        results.append(("bridge resolve after agent/chat", False, str(e)))

    # 7) MCP subprocess path: orientg_kb_ask with session_key only（HTTP 取 JWT）
    if user_jwt:
        try:
            import os

            os.environ["ORIENTG_INTERNAL_BASE_URL"] = BASE
            os.environ["ORIENTG_MCP_BRIDGE_SECRET"] = BRIDGE_SECRET
            from backend.services.hermes_bridge_http import clear_session_cache_for_tests
            from backend.services import hermes_token_bridge as bridge
            from backend.services import orientg_mcp_tools as tools

            clear_session_cache_for_tests()
            orig = bridge.resolve
            bridge.resolve = lambda _k: None  # type: ignore[method-assign]
            try:
                res = tools.orientg_kb_ask("", "bridge verify", hermes_session_key=VERIFY_SESSION_KEY)
            finally:
                bridge.resolve = orig  # type: ignore[method-assign]
            ok = not res.get("denied") and res.get("reason") != "doc allowed scope empty"
            detail = json.dumps(
                {
                    "ok": res.get("ok"),
                    "denied": res.get("denied"),
                    "reason": res.get("reason"),
                    "citations": len(res.get("citations") or []),
                },
                ensure_ascii=False,
            )[:160]
            results.append(("MCP orientg_kb_ask via HTTP JWT", ok, detail))
        except Exception as e:
            results.append(("MCP orientg_kb_ask via HTTP JWT", False, str(e)))

    # 8) Hermes MCP server enabled（capabilities 或 models 侧证）
    if HERMES_TOKEN:
        try:
            r = httpx.get(
                f"{HERMES}/v1/models",
                headers={"Authorization": f"Bearer {HERMES_TOKEN}"},
                timeout=10,
            )
            results.append(("hermes /v1/models", r.status_code == 200, str(r.status_code)))
        except Exception as e:
            results.append(("hermes /v1/models", False, str(e)))

    print("=== Orient-G MCP Bridge Verification ===")
    all_ok = True
    for name, ok, detail in results:
        mark = "PASS" if ok else "FAIL"
        if not ok:
            all_ok = False
        print(f"[{mark}] {name}: {detail}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
