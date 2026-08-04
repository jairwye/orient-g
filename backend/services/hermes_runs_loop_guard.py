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
        self.kb_ask_calls = 0
        self.max_planning_chars = 5000 if self.route == "hermes_full" else 8000
        self.max_planning_s = 180.0 if self.route == "hermes_full" else 240.0
        self.max_kb_ask_without_report = 4 if self.route == "hermes_full" else 6

    def sync_stats(self, stats: dict) -> None:
        self.kb_ask_calls = int(stats.get("hermes_orientg_kb_ask_calls") or 0)

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
        if re.search(
            r"人员结构对照|YYCQ vs 可比公司A · 2025 人员结构对比",
            text,
        ):
            self.has_report_anchor = True
        elif re.search(r"#{1,3}\s*[\u4e00-\u9fff]|管理费用|对比分析报告", text):
            if re.search(r"1378|1[,，]?378", text) and re.search(
                r"70(?:\.00)?|1\.1信息-人员",
                text,
            ):
                self.has_report_anchor = True

    def should_abort(self) -> tuple[bool, str, str]:
        """返回 (abort, code, user_message)。"""
        if self.forbidden_blocks >= self.max_forbidden_blocks:
            return (
                True,
                "hermes_run_forbidden_loop",
                "Hermes 多次尝试 shell/execute_code 已被网关拦截；已根据已有输出收束编排。",
            )
        if (
            self.route == "hermes_full"
            and self.kb_ask_calls >= self.max_kb_ask_without_report
            and not self.has_report_anchor
        ):
            return (
                True,
                "hermes_kb_ask_loop",
                "Hermes 已多次调用 orientg_kb_ask 仍未成稿；Orient-G 将改走补检索与本地综合。",
            )
        elapsed = time.monotonic() - self.started
        # 深度档：长推理但未调 MCP 时不主动掐断 Runs（由 mcp_retry / wall timeout 收束）。
        # 过程稿推理不等于空转；过早 abort 会导致 defer 模式下 accumulated 为空 → hermes_empty → 劣质本地 synth。
        if elapsed >= self.max_wall_s and not self.has_report_anchor and self.accumulated_len < 1200:
            return (
                True,
                "hermes_run_wall_timeout",
                f"Hermes Runs 已运行超过 {int(self.max_wall_s)} 秒仍未成稿，已主动收束。",
            )
        return False, "", ""
