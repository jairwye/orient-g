"""Hermes Runs API 循环护栏：禁止工具反复尝试后仍无限推理。"""

from __future__ import annotations

import re
import time


def runs_read_timeout_s(*, orientg_route: str | None, configured: int) -> float:
    """深度档对齐浏览器矩阵 1200s；标准档 720s。"""
    route = (orientg_route or "").strip().lower()
    base = max(60, int(configured or 600))
    if route == "hermes_full":
        return float(max(1200, base))
    if route == "hermes_lite":
        return float(max(720, base))
    return float(max(600, base))


class HermesRunsLoopGuard:
    def __init__(
        self,
        *,
        orientg_route: str | None,
        max_forbidden_blocks: int = 5,
        max_wall_s_full: float = 1080.0,
        max_wall_s_lite: float = 720.0,
    ) -> None:
        self.route = (orientg_route or "").strip().lower()
        self.max_forbidden_blocks = max(2, int(max_forbidden_blocks))
        self.max_wall_s = max_wall_s_full if self.route == "hermes_full" else max_wall_s_lite
        self.forbidden_blocks = 0
        self.started = time.monotonic()
        self.accumulated_len = 0
        self.has_report_anchor = False

    def on_forbidden_block(self) -> None:
        self.forbidden_blocks += 1

    def on_stream_evt(self, evt: dict) -> None:
        t = str(evt.get("type") or "")
        if t == "delta":
            chunk = str(evt.get("content") or "")
            if chunk:
                self.accumulated_len += len(chunk)
        elif t == "thinking":
            chunk = str(evt.get("content") or "")
            if chunk:
                self.accumulated_len += len(chunk)
        text = str(evt.get("content") or evt.get("message") or "")
        if re.search(r"#{1,3}\s*[\u4e00-\u9fff]|管理费用|对比分析报告", text):
            self.has_report_anchor = True

    def should_abort(self) -> tuple[bool, str, str]:
        """返回 (abort, code, user_message)。"""
        if self.forbidden_blocks >= self.max_forbidden_blocks:
            return (
                True,
                "hermes_run_forbidden_loop",
                "Hermes 多次尝试 shell/execute_code 已被网关拦截；已根据已有输出收束编排。",
            )
        elapsed = time.monotonic() - self.started
        if elapsed >= self.max_wall_s and not self.has_report_anchor and self.accumulated_len < 1200:
            return (
                True,
                "hermes_run_wall_timeout",
                f"Hermes Runs 已运行超过 {int(self.max_wall_s)} 秒仍未成稿，已主动收束。",
            )
        return False, "", ""
