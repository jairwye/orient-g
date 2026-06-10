#!/usr/bin/env python3
"""无人值守财务矩阵浏览器实测（Chrome DevTools Protocol，非 Playwright）。

与 user-chrome-devtools MCP 共用同一调试 Chrome（--remote-debugging-port）。
Python 侧轮询，避免 MCP evaluate 长循环超时。

用法:
  # 1) 启动调试 Chrome（与 MCP 可共用 profile）
  #    chrome.exe --remote-debugging-port=9222 --remote-allow-origins=* --user-data-dir=%TEMP%\\orientg-cdp
  # 2) 确保 :3000 / :8000 / Hermes 已就绪
  py -3.10 backend/scripts/finance_matrix_browser_cdp_runner.py
  py -3.10 backend/scripts/finance_matrix_browser_cdp_runner.py --cdp http://127.0.0.1:9222
  py -3.10 backend/scripts/finance_matrix_browser_cdp_runner.py --dry-run

失败策略（默认）:
  同条 timeout/send 失败 → 自动 reload 重测（--case-retries 2）
  验收 ok:false / console depth / 异常 → 写入 blocked.json 并 **停止**（须修代码后重跑）
  --continue-on-fail  仅排障：记录失败仍跑下一条（非产品验收）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import websocket

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
REPORTS = ROOT / "backend" / "tests" / "reports"
BLOCKED = REPORTS / "finance_matrix_browser_blocked.json"
POLL_TMP = REPORTS / "_cdp_poll_tmp.json"
ROW_TMP = REPORTS / "_browser_row_tmp.json"
HERMES_STALL_MS = 180_000
POLL_EVAL_TIMEOUT_S = 45.0

FOLDER_ID = "f_6f3638e4513f492c9610ddb5dda77c20"
AGENT_URL = (
    f"http://localhost:3000/ai-interaction?folder_id={FOLDER_ID}&view=agent"
)
LOGIN_URL = "http://localhost:3000/login"
INIT_SCRIPT = (
    "localStorage.setItem('orientg.kb_scope_capsule.v1', JSON.stringify({"
    f"folder_ids:['{FOLDER_ID}'], collection_ids:[], table_ids:[], updated_at: Date.now()"
    "}));"
)
_SESSION_TOKEN = ""


def _finance_test_password() -> str:
    return os.environ.get("ORIENTG_FINANCE_TEST_PASSWORD", "FinanceTest!2026")

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))
from finance_matrix_browser_retry_queue import retry_pending  # noqa: E402
from finance_matrix_browser_validate import (  # noqa: E402
    COOLDOWN_MS,
    POLL_INTERVAL_MS,
    WAIT_CITATIONS_MS,
)
from finance_matrix_cases import MODE_LABEL  # noqa: E402
from finance_matrix_browser_append import append_matrix_row  # noqa: E402


def _http_get_json(url: str, timeout: float = 5.0) -> Any:
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _preflight_backend() -> None:
    try:
        _http_get_json("http://127.0.0.1:8000/api/agent/status", timeout=8.0)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        raise SystemExit(f"backend :8000 不可用: {e}") from e


class CdpPage:
    """单 tab CDP 会话（websocket-client）。"""

    def __init__(self, ws_url: str, *, cdp_base: str = "") -> None:
        self._cdp_base = cdp_base
        self._ws_url = ws_url
        self._ws = websocket.create_connection(ws_url, timeout=120)
        self._id = 0
        self._console_errors: list[str] = []
        self._call("Runtime.enable", {})
        self._call("Log.enable", {})
        self._call("Page.enable", {})

    @classmethod
    def connect(cls, cdp_base: str) -> CdpPage:
        ws_url = _pick_page_target(cdp_base)
        return cls(ws_url, cdp_base=cdp_base)

    def reconnect(self) -> None:
        self.close()
        self._ws_url = _pick_page_target(self._cdp_base)
        self._ws = websocket.create_connection(self._ws_url, timeout=120)
        self._id = 0
        self._call("Runtime.enable", {})
        self._call("Log.enable", {})
        self._call("Page.enable", {})

    def close(self) -> None:
        try:
            self._ws.close()
        except Exception:
            pass

    def _recv_until(self, req_id: int, deadline: float) -> dict[str, Any]:
        while time.monotonic() < deadline:
            self._ws.settimeout(max(0.1, deadline - time.monotonic()))
            try:
                raw = self._ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            msg = json.loads(raw)
            if msg.get("method") == "Log.entryAdded":
                entry = msg.get("params", {}).get("entry", {})
                if str(entry.get("level", "")).lower() in ("error", "warning"):
                    text = str(entry.get("text") or "")
                    if text:
                        self._console_errors.append(text)
            if msg.get("method") == "Runtime.consoleAPICalled":
                p = msg.get("params", {})
                if p.get("type") == "error":
                    for a in p.get("args") or []:
                        v = a.get("value") or a.get("description") or ""
                        if v:
                            self._console_errors.append(str(v))
            if msg.get("id") == req_id:
                return msg
        raise TimeoutError(f"CDP 响应超时 id={req_id}")

    def _call(self, method: str, params: dict[str, Any], timeout: float = 60.0) -> dict[str, Any]:
        self._id += 1
        rid = self._id
        self._ws.send(json.dumps({"id": rid, "method": method, "params": params}))
        resp = self._recv_until(rid, time.monotonic() + timeout)
        if "error" in resp:
            raise RuntimeError(f"CDP {method}: {resp['error']}")
        return resp.get("result") or {}

    def reset_console(self) -> None:
        self._console_errors.clear()

    def console_depth_error(self) -> bool:
        blob = "\n".join(self._console_errors)
        return bool(re.search(r"Maximum update depth exceeded", blob, re.I))

    def navigate(self, url: str, *, init_script: str | None = None) -> None:
        if init_script:
            self._call(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": init_script},
            )
        self._call("Page.navigate", {"url": url})
        time.sleep(2.5)

    def evaluate(self, expression: str, *, await_promise: bool = True, timeout: float = 120.0) -> Any:
        result = self._call(
            "Runtime.evaluate",
            {
                "expression": expression,
                "awaitPromise": await_promise,
                "returnByValue": True,
            },
            timeout=timeout,
        )
        exc = result.get("exceptionDetails")
        if exc:
            raise RuntimeError(f"JS 异常: {exc}")
        return (result.get("result") or {}).get("value")

    def load_js_function(self, filename: str) -> str:
        return (SCRIPTS / filename).read_text(encoding="utf-8").strip()


def _as_iife(source: str) -> str:
    """`() => { ... };` → `( () => { ... } )()`，供 Runtime.evaluate 一次执行。"""
    s = source.strip()
    while s.startswith("/*"):
        end = s.find("*/")
        if end < 0:
            break
        s = s[end + 2 :].strip()
    if s.endswith(";"):
        s = s[:-1].rstrip()
    return f"({s})()"


def _pick_page_target(cdp_base: str, *, prefer_ai: bool = True) -> str:
    targets = _http_get_json(f"{cdp_base.rstrip('/')}/json/list")
    pages = [t for t in targets if t.get("type") == "page" and "webSocketDebuggerUrl" in t]
    if prefer_ai:
        ai_pages = [
            t
            for t in pages
            if "localhost:3000" in str(t.get("url") or "")
            or "127.0.0.1:3000" in str(t.get("url") or "")
        ]
        if ai_pages:
            return str(ai_pages[-1]["webSocketDebuggerUrl"])
    for t in pages:
        url = str(t.get("url") or "")
        if "localhost:3000" in url or "127.0.0.1:3000" in url:
            return str(t["webSocketDebuggerUrl"])
    if pages:
        return str(pages[-1]["webSocketDebuggerUrl"])
    raise SystemExit(f"CDP 无可用 page target: {cdp_base}")


def _page_init_script(token: str = "") -> str:
    parts: list[str] = []
    if token:
        parts.append(f"sessionStorage.setItem('orient_g_token', {json.dumps(token)});")
    parts.append(INIT_SCRIPT)
    return "".join(parts)


def _fetch_auth_token() -> str:
    req = urllib.request.Request(
        "http://127.0.0.1:8000/api/auth/login",
        data=json.dumps({"username": "finance_test", "password": _finance_test_password()}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    token = str(data.get("token") or "")
    if not data.get("ok") or not token:
        raise RuntimeError(f"API 登录失败: {data}")
    return token


def _js_login() -> str:
    pwd = json.dumps(_finance_test_password())
    return f"""(async () => {{
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  for (let i = 0; i < 40; i++) {{
    const user = document.querySelector('input[type="text"], input:not([type])');
    const pass = document.querySelector('input[type="password"]');
    if (user && pass) break;
    await sleep(250);
  }}
  const user = document.querySelector('input[type="text"], input:not([type])');
  const pass = document.querySelector('input[type="password"]');
  if (!user || !pass) return {{ ok: false, err: 'no login form', url: location.href }};
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
  setter?.call(user, 'finance_test');
  user.dispatchEvent(new Event('input', {{ bubbles: true }}));
  setter?.call(pass, {pwd});
  pass.dispatchEvent(new Event('input', {{ bubbles: true }}));
  Array.from(document.querySelectorAll('button')).find(b => b.textContent?.trim() === '登录')?.click();
  await sleep(3000);
  const stillLogin = !!document.querySelector('input[type="password"]');
  return {{ ok: !stillLogin, url: location.href, err: stillLogin ? 'still on login' : undefined }};
}})()"""


def _js_send(mode_label: str, query: str) -> str:
    q = json.dumps(query, ensure_ascii=False)
    m = json.dumps(mode_label, ensure_ascii=False)
    return f"""(async () => {{
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const modeLabel = {m};
  const query = {q};
  localStorage.setItem(
    "orientg.kb_scope_capsule.v1",
    JSON.stringify({{
      folder_ids: ["{FOLDER_ID}"],
      collection_ids: [],
      table_ids: [],
      updated_at: Date.now(),
    }}),
  );
  for (let i = 0; i < 60; i++) {{
    if (document.querySelector('[aria-label="智能体模式"]')) break;
    const nav = Array.from(document.querySelectorAll('nav button')).find(b => b.textContent?.trim() === '智能体');
    if (nav) nav.click();
    await sleep(800);
  }}
  const nav = Array.from(document.querySelectorAll('button')).find(b => b.textContent?.trim() === '智能体' && b.closest('nav'));
  if (nav) {{ nav.click(); await sleep(500); }}
  const skillBtn = Array.from(document.querySelectorAll('button')).find(b => b.getAttribute('title') === '技能');
  if (skillBtn && !document.getElementById('ai-skills-popover')) {{ skillBtn.click(); await sleep(400); }}
  const skillLabel = Array.from(document.querySelectorAll('#ai-skills-popover label')).find(l => l.textContent?.includes('年报财务分析'));
  if (skillLabel) {{
    const cb = skillLabel.querySelector('input[type="checkbox"]');
    if (cb && !cb.checked) {{ cb.click(); await sleep(200); }}
  }}
  const group = document.querySelector('[aria-label="智能体模式"]');
  const btn = group ? Array.from(group.querySelectorAll('button')).find(b => b.textContent?.trim() === modeLabel) : null;
  if (btn) {{ btn.click(); await sleep(modeLabel === '快速' ? 1500 : 300); }}
  const ta = document.querySelector('textarea');
  if (!ta) return {{ ok: false, err: 'no textarea' }};
  const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set;
  setter?.call(ta, query);
  ta.dispatchEvent(new Event('input', {{ bubbles: true }}));
  await sleep(150);
  const send = Array.from(document.querySelectorAll('button')).find(b => b.getAttribute('aria-label') === '发送' && !b.disabled);
  if (!send) return {{ ok: false, err: 'send disabled' }};
  send.click();
  return {{ ok: true }};
}})()"""


def _ensure_login(page: CdpPage) -> None:
    """API 登录 + sessionStorage 注入，避免 React 受控表单在 CDP 下偶发失败。"""
    global _SESSION_TOKEN
    _SESSION_TOKEN = _fetch_auth_token()
    page.navigate(LOGIN_URL, init_script=_page_init_script(_SESSION_TOKEN))
    time.sleep(2.0)
    page.evaluate(
        f"""(() => {{
  sessionStorage.setItem('orient_g_token', {json.dumps(_SESSION_TOKEN)});
  return {{ ok: true }};
}})()""",
        timeout=30,
    )
    page.navigate(AGENT_URL, init_script=_page_init_script(_SESSION_TOKEN))
    time.sleep(4.0)
    href = page.evaluate("location.href", timeout=30)
    if isinstance(href, str) and "/login" in href:
        raise RuntimeError("token 注入后仍停留在登录页")


def _safe_evaluate(
    page: CdpPage,
    expression: str,
    *,
    cdp_base: str,
    await_promise: bool = True,
    timeout: float = POLL_EVAL_TIMEOUT_S,
) -> tuple[CdpPage, Any]:
    try:
        return page, page.evaluate(expression, await_promise=await_promise, timeout=timeout)
    except (TimeoutError, RuntimeError, OSError, websocket.WebSocketException) as exc:
        print(json.dumps({"cdp_reconnect": str(exc)[:160]}, ensure_ascii=False), flush=True)
        try:
            page.reconnect()
            return page, page.evaluate(expression, await_promise=await_promise, timeout=timeout)
        except Exception as exc2:
            if cdp_base:
                page = CdpPage.connect(cdp_base)
                return page, page.evaluate(expression, await_promise=await_promise, timeout=timeout)
            raise exc2 from exc


def _poll_until_done(page: CdpPage, mode: str, *, cdp_base: str) -> tuple[CdpPage, dict[str, Any]]:
    poll_js = _as_iife(page.load_js_function("finance_matrix_browser_poll_state.js"))
    max_ms = WAIT_CITATIONS_MS[mode]
    interval_s = POLL_INTERVAL_MS / 1000.0
    stable_need = 2
    stable = 0
    last_len = -1
    t0 = time.monotonic()
    last: dict[str, Any] = {}
    idle_streak = 0
    hermes_stuck_since: float | None = None
    poll_n = 0
    eval_fail_streak = 0

    while (time.monotonic() - t0) * 1000 < max_ms:
        poll_n += 1
        try:
            page, polled = _safe_evaluate(page, poll_js, cdp_base=cdp_base, await_promise=False)
            eval_fail_streak = 0
        except Exception as exc:
            eval_fail_streak += 1
            print(
                json.dumps(
                    {"poll_eval_fail": poll_n, "streak": eval_fail_streak, "err": str(exc)[:120]},
                    ensure_ascii=False,
                ),
                flush=True,
            )
            if eval_fail_streak >= 3:
                fallback = last if isinstance(last, dict) else {}
                last = {"streamFail": True, "poll_eval_dead": True, "extract": fallback.get("extract") or {}}
                return page, last
            time.sleep(interval_s)
            continue
        last = polled if isinstance(polled, dict) else {"streamDone": False, "streamFail": True}
        if poll_n == 1 or poll_n % 4 == 0:
            ext = last.get("extract") or {}
            print(
                json.dumps(
                    {
                        "poll": poll_n,
                        "streamDone": last.get("streamDone"),
                        "loading": last.get("loading"),
                        "hermesStillRunning": last.get("hermesStillRunning"),
                        "citations": last.get("citations"),
                        "len": ext.get("len"),
                        "elapsed_s": int(time.monotonic() - t0),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
        if last.get("streamFail"):
            return page, last
        if last.get("agentIdleNoReply"):
            idle_streak += 1
            if idle_streak >= 3 and (time.monotonic() - t0) >= 45:
                last["streamFail"] = True
                last["lost_session"] = True
                return page, last
        else:
            idle_streak = 0
        if last.get("hermesStillRunning") or last.get("loading"):
            if hermes_stuck_since is None:
                hermes_stuck_since = time.monotonic()
            elif (time.monotonic() - hermes_stuck_since) * 1000 >= HERMES_STALL_MS:
                ext = last.get("extract") or {}
                if int(last.get("citations") or 0) > 0 and int(ext.get("len") or 0) >= 200:
                    last["streamDone"] = True
                    last["hermes_stall_salvage"] = True
        else:
            hermes_stuck_since = None
        ext = last.get("extract") or {}
        cur_len = int(ext.get("len") or 0)
        if last.get("streamDone"):
            if cur_len == last_len:
                stable += 1
            else:
                stable = 0
            last_len = cur_len
            if stable >= stable_need:
                return page, last
        else:
            stable = 0
            last_len = cur_len
        time.sleep(interval_s)
    last["streamFail"] = last.get("streamFail") or not last.get("streamDone")
    last["timeout"] = True
    return page, last


def _extract(page: CdpPage, *, cdp_base: str) -> tuple[CdpPage, dict[str, Any]]:
    ext_js = _as_iife(page.load_js_function("finance_matrix_browser_extract_row.js"))
    page, row = _safe_evaluate(page, ext_js, cdp_base=cdp_base, await_promise=False)
    if not isinstance(row, dict):
        raise RuntimeError(f"extract 返回异常: {row!r}")
    return page, row


def _append_row(
    poll: dict[str, Any],
    *,
    notes: str,
    console_depth: bool,
    case: tuple[str, str, str, str],
) -> dict[str, Any]:
    cat, subj, mode, query = case
    payload = {
        "category": cat,
        "subject": subj,
        "mode": mode,
        "query": query,
        "tier_line": poll.get("tier_line", ""),
        "citations": poll.get("citations", 0),
        "notes": notes,
        "extract": poll.get("extract") or {},
        "console_depth_error": console_depth,
    }
    POLL_TMP.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ROW_TMP.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return append_matrix_row(payload)


def _write_blocked(case: tuple[str, str, str, str], poll: dict[str, Any], result: dict[str, Any]) -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    BLOCKED.write_text(
        json.dumps(
            {
                "case": {"category": case[0], "subject": case[1], "mode": case[2], "query": case[3]},
                "poll": poll,
                "append": result,
                "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "hint": "修代码/配置后: py -3.10 backend/scripts/finance_matrix_browser_cdp_runner.py",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _open_fresh_cdp_tab(cdp_base: str) -> str | None:
    """每案换新 tab 并返回 ws URL；sessionStorage 须靠 init_script 重新注入。"""
    url = AGENT_URL.replace(" ", "%20")
    try:
        req = urllib.request.Request(
            f"{cdp_base.rstrip('/')}/json/new?{url}",
            method="PUT",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            target = json.loads(resp.read().decode("utf-8"))
        ws = str(target.get("webSocketDebuggerUrl") or "")
        if ws:
            time.sleep(1.5)
            return ws
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        pass
    time.sleep(1.0)
    return None


def _prune_stale_tabs(cdp_base: str, *, max_tabs: int = 4) -> None:
    """关闭多余 CDP tab，减轻长批次内存与僵死。"""
    try:
        targets = _http_get_json(f"{cdp_base.rstrip('/')}/json/list")
        pages = [t for t in targets if t.get("type") == "page" and t.get("id")]
        if len(pages) <= max_tabs:
            return
        for t in pages[: max(0, len(pages) - max_tabs)]:
            tid = str(t.get("id") or "")
            if not tid:
                continue
            try:
                urllib.request.urlopen(f"{cdp_base.rstrip('/')}/json/close/{tid}", timeout=5)
            except (urllib.error.URLError, TimeoutError, OSError):
                pass
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        pass


def _connect_case_page(cdp_base: str) -> CdpPage:
    _prune_stale_tabs(cdp_base)
    ws_url = _open_fresh_cdp_tab(cdp_base)
    if ws_url:
        return CdpPage(ws_url, cdp_base=cdp_base)
    return CdpPage.connect(cdp_base)


def _run_case_once(page: CdpPage, case: tuple[str, str, str, str], *, cdp_base: str) -> tuple[CdpPage, dict[str, Any]]:
    cat, subj, mode, query = case
    mode_label = MODE_LABEL[mode]
    page.reset_console()
    init = _page_init_script(_SESSION_TOKEN)
    page.navigate(AGENT_URL, init_script=init)
    time.sleep(2)
    page, sent = _safe_evaluate(page, _js_send(mode_label, query), cdp_base=cdp_base, timeout=60)
    if not isinstance(sent, dict) or not sent.get("ok"):
        return page, {"ok": False, "stage": "send", "detail": sent, "poll": {}}
    page, poll = _poll_until_done(page, mode, cdp_base=cdp_base)
    page, ext_row = _extract(page, cdp_base=cdp_base)
    poll_ex = poll.get("extract") if isinstance(poll.get("extract"), dict) else {}
    ext_ex = ext_row.get("extract") if isinstance(ext_row.get("extract"), dict) else {}
    poll_tier = str(poll.get("tier_line") or "")
    ext_tier = str(ext_row.get("tier_line") or "")
    tier_line = poll_tier if "完成：Tier" in poll_tier else (ext_tier or poll_tier)
    citations = max(int(poll.get("citations") or 0), int(ext_row.get("citations") or 0))
    merged = {
        **poll,
        **{k: v for k, v in ext_row.items() if k != "extract"},
        "tier_line": tier_line,
        "citations": citations,
        "extract": {**poll_ex, **ext_ex},
    }
    depth_err = page.console_depth_error()
    notes = f"cdp-unattended; console_depth={depth_err}"
    if poll.get("timeout"):
        notes += "; poll_timeout"
    if poll.get("hermes_stall_salvage"):
        notes += "; hermes_stall_salvage"
    append = _append_row(merged, notes=notes, console_depth=depth_err, case=case)
    ok = bool(append.get("ok"))
    return page, {
        "ok": ok,
        "poll": merged,
        "append": append,
        "console_depth_error": depth_err,
        "stage": "validate" if not ok else "pass",
    }


def _retriable(result: dict[str, Any]) -> bool:
    """超时 / 发送失败 / 流式未完成 / tier 未就绪 → 可 reload 重测同条。"""
    if result.get("stage") == "send":
        return True
    poll = result.get("poll") or {}
    if poll.get("timeout"):
        return True
    if poll.get("streamFail") and not result.get("ok"):
        extract = poll.get("extract") or {}
        if int(extract.get("len") or 0) < 200:
            return True
    if result.get("stage") == "validate":
        extract = poll.get("extract") or {}
        if poll.get("streamDone") and int(extract.get("len") or 0) >= 200:
            return False
    if not result.get("ok"):
        extract = poll.get("extract") or {}
        tier_line = str(poll.get("tier_line") or "")
        head = str(extract.get("head") or "")
        citations = int(poll.get("citations") or 0)
        if re.search(r"^思考中|^同步中", head):
            return True
        if citations == 0 and re.search(r"共 \d+ 步", tier_line) and not re.search(
            r"Tier [012]|深度|本地证据", tier_line
        ):
            return True
    return False


def run_case(
    page: CdpPage,
    case: tuple[str, str, str, str],
    *,
    case_retries: int = 2,
    cdp_base: str = "",
) -> tuple[CdpPage, dict[str, Any]]:
    cat, subj, mode, query = case
    print(f"\n=== {cat}/{subj}/{mode} ===", flush=True)
    last: dict[str, Any] = {"ok": False}
    for attempt in range(case_retries + 1):
        if attempt > 0:
            print(
                json.dumps(
                    {"retry": attempt, "max": case_retries, "reason": last.get("stage")},
                    ensure_ascii=False,
                ),
                flush=True,
            )
            try:
                page.navigate(AGENT_URL, init_script=_page_init_script(_SESSION_TOKEN))
            except (TimeoutError, RuntimeError, OSError, websocket.WebSocketException):
                if cdp_base:
                    page = _connect_case_page(cdp_base)
                page.navigate(AGENT_URL, init_script=_page_init_script(_SESSION_TOKEN))
            time.sleep(3)
        page, last = _run_case_once(page, case, cdp_base=cdp_base)
        if last.get("ok"):
            break
        if attempt < case_retries and _retriable(last):
            continue
        break
    print(
        json.dumps(
            {
                "ok": last.get("ok"),
                "append": last.get("append"),
                "console_depth_error": last.get("console_depth_error"),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    time.sleep(COOLDOWN_MS / 1000.0)
    return page, last


def _parse_only_keys(raw_list: list[str] | None) -> set[str]:
    out: set[str] = set()
    for item in raw_list or []:
        parts = re.split(r"[/:：]", item.strip())
        if len(parts) == 3:
            out.add(f"{parts[0]}::{parts[1]}::{parts[2]}")
    return out


def _cases_for_run(*, only_keys: set[str] | None) -> list[tuple[str, str, str, str]]:
    if only_keys:
        from finance_matrix_cases import MATRIX  # noqa: E402

        return [c for c in MATRIX if f"{c[0]}::{c[1]}::{c[2]}" in only_keys]
    return retry_pending()


def main() -> None:
    parser = argparse.ArgumentParser(description="无人值守财务矩阵 CDP runner")
    parser.add_argument("--cdp", default="http://127.0.0.1:9222", help="Chrome remote debugging URL")
    parser.add_argument("--continue-on-fail", action="store_true", help="失败仍继续（非产品验收模式）")
    parser.add_argument("--case-retries", type=int, default=2, help="同条 timeout/send 失败时 reload 重测次数")
    parser.add_argument("--dry-run", action="store_true", help="只打印待跑队列")
    parser.add_argument("--skip-login", action="store_true", help="跳过登录（已登录 session）")
    parser.add_argument(
        "--only",
        action="append",
        help="只跑指定条，格式 cat/subject/mode（可重复），忽略 report 已通过状态",
    )
    args = parser.parse_args()
    only_keys = _parse_only_keys(args.only)

    pending = _cases_for_run(only_keys=only_keys or None)
    print(json.dumps({"pending": len(pending), "total": 42}, ensure_ascii=False))
    if args.dry_run:
        for c in pending:
            print(f"{c[0]}\t{c[1]}\t{c[2]}")
        return
    if not pending:
        print("全部通过，无需跑。")
        return

    _preflight_backend()
    global _SESSION_TOKEN
    if not args.skip_login:
        page = CdpPage.connect(args.cdp)
        _ensure_login(page)
    else:
        _SESSION_TOKEN = _fetch_auth_token()
        page = CdpPage.connect(args.cdp)
    try:
        passed = 0
        failed = 0
        done_keys: set[str] = set()
        while True:
            if only_keys:
                pending = [
                    c
                    for c in _cases_for_run(only_keys=only_keys)
                    if f"{c[0]}::{c[1]}::{c[2]}" not in done_keys
                ]
            else:
                pending = [
                    c
                    for c in retry_pending()
                    if f"{c[0]}::{c[1]}::{c[2]}" not in done_keys
                ]
            if not pending:
                break
            case = pending[0]
            case_key = f"{case[0]}::{case[1]}::{case[2]}"
            try:
                try:
                    page.close()
                except Exception:
                    pass
                page = _connect_case_page(args.cdp)
                if _SESSION_TOKEN:
                    page.navigate(LOGIN_URL, init_script=_page_init_script(_SESSION_TOKEN))
                    page.evaluate(
                        f"sessionStorage.setItem('orient_g_token', {json.dumps(_SESSION_TOKEN)});",
                        await_promise=False,
                        timeout=20,
                    )
                page, result = run_case(page, case, case_retries=max(0, args.case_retries), cdp_base=args.cdp)
            except Exception as e:
                result = {"ok": False, "stage": "exception", "detail": str(e)}
                _write_blocked(case, {}, result)
                print(f"BLOCKED: {e}", flush=True)
                try:
                    page.close()
                except Exception:
                    pass
                try:
                    page = CdpPage.connect(args.cdp)
                    time.sleep(1.0)
                except Exception:
                    pass
                done_keys.add(case_key)
                if not args.continue_on_fail:
                    print(
                        "进程退出(exit 1)：异常须 Agent 修代码后重跑同一命令。"
                        " 这不是 bug——CDP runner 不能自动改代码。",
                        flush=True,
                    )
                    sys.exit(1)
                failed += 1
                continue
            done_keys.add(case_key)
            if result.get("ok"):
                passed += 1
                if BLOCKED.is_file():
                    BLOCKED.unlink()
                continue
            _write_blocked(case, result.get("poll") or {}, result.get("append") or result)
            failed += 1
            if not args.continue_on_fail:
                print(
                    "进程退出(exit 1)：本条验收未通过，已写 blocked.json。"
                    " 修代码后重跑: py -3.10 backend/scripts/finance_matrix_browser_cdp_runner.py --skip-login\n"
                    "说明: Cursor stop hook 仅在 Agent 对话结束时续跑；CDP runner 是独立进程，失败即停。",
                    flush=True,
                )
                sys.exit(1)
        remaining = len(_cases_for_run(only_keys=only_keys)) - len(done_keys) if only_keys else len(retry_pending())
        print(json.dumps({"passed_this_run": passed, "failed": failed, "remaining": remaining}, ensure_ascii=False))
    finally:
        page.close()


if __name__ == "__main__":
    main()
