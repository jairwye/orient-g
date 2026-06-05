#!/usr/bin/env python3
"""财务矩阵 Chrome DevTools 串行闭环：激活后配合 .cursor/hooks stop 自动续跑。

用法:
  py -3.10 backend/scripts/finance_matrix_browser_loop.py activate
  py -3.10 backend/scripts/finance_matrix_browser_loop.py deactivate
  py -3.10 backend/scripts/finance_matrix_browser_loop.py status
  py -3.10 backend/scripts/finance_matrix_browser_loop.py on_stop   # hooks stdin -> stdout JSON
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "backend" / "tests" / "reports"
LOCK = REPORTS / ".finance_matrix_loop_active"
STATE = REPORTS / ".finance_matrix_loop_state.json"
RUNNER = ROOT / "docs" / "finance-matrix-browser-testing.md"
FOLDER_ID = "f_6f3638e4513f492c9610ddb5dda77c20"

_SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS))
from finance_matrix_browser_retry_queue import retry_pending  # noqa: E402
from finance_matrix_browser_validate import WAIT_CITATIONS_MS  # noqa: E402


def _write_state(**patch: object) -> dict:
    data: dict = {}
    if STATE.is_file():
        try:
            data = json.loads(STATE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    data.update(patch)
    data["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    STATE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data


def activate() -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    LOCK.write_text(datetime.now(timezone.utc).isoformat(timespec="seconds") + "\n", encoding="utf-8")
    pending = retry_pending()
    _write_state(active=True, started_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    print(
        json.dumps(
            {
                "active": True,
                "retry_pending": len(pending),
                "lock": str(LOCK),
                "hint": "Agent 每轮 stop 后 hook 将注入续跑指令；勿并行 Hermes/API 与浏览器用例",
            },
            ensure_ascii=False,
        )
    )


def deactivate() -> None:
    if LOCK.is_file():
        LOCK.unlink()
    _write_state(active=False)
    print(json.dumps({"active": False}, ensure_ascii=False))


def status() -> None:
    pending = retry_pending()
    latest_ok = 42 - len(pending)
    print(
        json.dumps(
            {
                "active": LOCK.is_file(),
                "ok_pass": latest_ok,
                "retry_pending": len(pending),
                "total": 42,
                "lock": str(LOCK) if LOCK.is_file() else None,
                "state": json.loads(STATE.read_text(encoding="utf-8")) if STATE.is_file() else None,
            },
            ensure_ascii=False,
        )
    )


def _followup_for_case(case: dict) -> str:
    mode = case["mode"]
    wait_s = WAIT_CITATIONS_MS[mode] // 1000
    return f"""## 财务矩阵串行闭环（hook 续跑）

**禁止** Playwright；仅用 **user-chrome-devtools** MCP。一次只跑 **1 条**，禁止与 API/Hermes 预检并行。

### 当前用例
- `{case['category']}/{case['subject']}/{case['mode']}`（{case['mode_label']} · {case['tier_expect']}）
- 问句（字面量嵌入 send 脚本）：`{case['query']}`
- 单条最长等待 **{wait_s}s**；poll 间隔 15–60s；须 `streamDone` 或 timeout 后再 extract

### 步骤（不得跳步）
1. 若上条 **send 仍禁用且 citations=0 超过 2 轮 poll**：`navigate_page` reload → 重新 `nav「智能体」` → 重发**同条**（勿 next）
2. `navigate` → `http://localhost:3000/ai-interaction?folder_id={FOLDER_ID}&view=agent` + initScript `folder_ids`
3. 等 `aria-label="智能体模式"` → nav「智能体」新会话 → 选 **{case['mode_label']}** → 发送问句
4. 确认 backend 日志 `POST /api/agent/chat/stream`
5. 每 15–60s 执行 `finance_matrix_browser_poll_state.js` 直至 streamDone（citations>0 或诚实缺证据+len≥80；无加载中）
6. `finance_matrix_browser_extract_row.js` → **审核** tier/正文/checks
7. **`list_console_messages` types=`["error"]`** → 写入 `console_depth_error`（含 Maximum update depth 则 fail）
8. `finance_matrix_browser_write_row.py` + `append.py`；**仅 `ok:true` 才可 next**
9. `ok:false` 或 streamFail/卡死/console 错误：查根因 → 改代码/配置 → **重测同条**
10. `retry_queue.py count`；若 pending>0 继续（本 hook 会在 stop 时再注入）

细则：`{RUNNER.as_posix()}`
"""


def on_stop() -> None:
    """Cursor stop hook：stdin 可为空或 JSON；stdout 为 hook 响应 JSON。"""
    if not LOCK.is_file():
        print("{}")
        return

    pending = retry_pending()
    if not pending:
        deactivate()
        print(
            json.dumps(
                {
                    "followup_message": (
                        "## 财务矩阵已全部通过（42/42）\n\n"
                        "已自动 `deactivate` 闭环 hook。无需再跑 Chrome 矩阵。"
                    )
                },
                ensure_ascii=False,
            )
        )
        return

    cat, subj, mode, query = pending[0]
    from finance_matrix_cases import MODE_LABEL, TIER_EXPECT  # noqa: E402

    case = {
        "category": cat,
        "subject": subj,
        "mode": mode,
        "mode_label": MODE_LABEL[mode],
        "tier_expect": TIER_EXPECT[mode],
        "query": query,
    }
    _write_state(last_hook_case=f"{cat}/{subj}/{mode}", retry_pending=len(pending))
    msg = _followup_for_case(case)
    print(json.dumps({"followup_message": msg}, ensure_ascii=False))


def main() -> None:
    cmd = (sys.argv[1] if len(sys.argv) > 1 else "status").strip().lower()
    if cmd == "activate":
        activate()
    elif cmd == "deactivate":
        deactivate()
    elif cmd == "status":
        status()
    elif cmd == "on_stop":
        on_stop()
    else:
        print(f"unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
