"""Hermes Runs API 循环护栏：禁止工具反复尝试后仍无限推理。"""

from __future__ import annotations

import re
import time

_PERMISSION_KB_STALL_RE = re.compile(
    r"知识库.{0,24}权限受限|权限受限.{0,24}无法检索",
    re.I,
)
_WEB_MEMORY_ESCAPE_RE = re.compile(
    r"web[- ]?search|web_search|web-tools|webtools|外网搜索|\bmemory\b",
    re.I,
)


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
        max_permission_web_stalls: int = 3,
        max_wall_s_full: float = 1080.0,
        max_wall_s_lite: float = 720.0,
        lite_report_ready_grace_s: float = 60.0,
        full_report_ready_grace_s: float = 120.0,
    ) -> None:
        self.route = (orientg_route or "").strip().lower()
        self.max_forbidden_blocks = max(2, int(max_forbidden_blocks))
        self.max_wall_s = max_wall_s_full if self.route == "hermes_full" else max_wall_s_lite
        self.forbidden_blocks = 0
        self.started = time.monotonic()
        self.accumulated_len = 0
        self.has_report_anchor = False
        self.report_ready_at: float | None = None
        self.lite_report_ready_grace_s = float(lite_report_ready_grace_s)
        self.full_report_ready_grace_s = float(full_report_ready_grace_s)
        self.kb_ask_calls = 0
        self.max_planning_chars = 5000 if self.route == "hermes_full" else 8000
        self.max_planning_s = 180.0 if self.route == "hermes_full" else 240.0
        # 人员深度常需取证+核证多轮 MCP；过早 kb_ask_loop 会在成稿前收束导致「未成稿」
        self.max_kb_ask_without_report = 6
        self.max_permission_web_stalls = max(2, int(max_permission_web_stalls))
        self.permission_web_stall_cycles = 0
        self._last_activity_at: float | None = None

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
                self._last_activity_at = time.monotonic()
                # 立锚后仍有实质 delta → 刷新宽限，避免 enrichment 中途被收束
                if self.has_report_anchor and self.report_ready_at is not None and len(chunk) >= 40:
                    self.report_ready_at = time.monotonic()
        elif t == "thinking":
            chunk = str(evt.get("content") or "")
            if chunk:
                self.accumulated_len += len(chunk)
                self._last_activity_at = time.monotonic()
        elif t == "tool_progress":
            self._last_activity_at = time.monotonic()
            # 仍在调工具 → 刷新宽限起点
            if self.has_report_anchor and self.report_ready_at is not None:
                self.report_ready_at = time.monotonic()
        text = str(evt.get("content") or evt.get("message") or "")
        if (
            self.route == "hermes_full"
            and not self.has_report_anchor
            and text
            and _PERMISSION_KB_STALL_RE.search(text)
            and _WEB_MEMORY_ESCAPE_RE.search(text)
        ):
            self.permission_web_stall_cycles += 1
        # 立锚点：delta 正文；或较长 thinking 中的实质对照稿（defer 时终稿常走 thinking）。
        # thinking 须与 delta 同等 has_struct，避免仅标题+短段误锚。
        # 禁止用 tool_progress / 短 MCP 骨架标题误触发。
        if text and t in ("delta", "thinking"):
            has_pc = bool(
                re.search(
                    r"人员结构对照|YYCQ vs 可比公司A · 2025 人员结构对比",
                    text,
                )
            )
            has_struct = bool(
                re.search(r"#{1,3}\s*[\u4e00-\u9fff]|管理费用|对比分析报告", text)
                and re.search(r"1378|1[,，]?378", text)
                and re.search(r"70(?:\.00)?|1\.1信息-人员", text)
            )
            multi_role = bool(
                re.search(r"研发", text)
                and re.search(r"销售|运营|管理|支持", text)
            )
            if t == "delta" and (has_pc or has_struct):
                self.has_report_anchor = True
            elif (
                t == "thinking"
                and has_pc
                and (has_struct or multi_role)
                and re.search(r"\d{2,}", text)
                and len(text) >= 280
                and ("|" in text or "\t" in text or re.search(r"对比分析|口径说明", text))
            ):
                self.has_report_anchor = True
        if self.has_report_anchor and self.report_ready_at is None:
            self.report_ready_at = time.monotonic()

    def should_abort(self) -> tuple[bool, str, str]:
        """返回 (abort, code, user_message)。"""
        if self.forbidden_blocks >= self.max_forbidden_blocks:
            # 已有 MCP 取证：收束为「写终稿」续跑，禁止 abort→Orient-G 门禁整篇顶替
            if self.kb_ask_calls >= 1 or self.has_report_anchor:
                return (
                    True,
                    "hermes_forbidden_write_final",
                    "Hermes 多次尝试 shell/execute_code 已被拦截；"
                    "请基于已有 MCP 输出直接用中文成稿，勿再调禁工具。",
                )
            return (
                True,
                "hermes_run_forbidden_loop",
                "Hermes 多次尝试 shell/execute_code 已被网关拦截；已根据已有输出收束编排。",
            )
        if (
            self.route == "hermes_full"
            and not self.has_report_anchor
            and self.permission_web_stall_cycles >= self.max_permission_web_stalls
        ):
            return (
                True,
                "hermes_permission_web_stall",
                "Hermes 过程稿反复声称 KB 权限受限并转向 web/memory 空转；Orient-G 将收束并改走 MCP 补检索。",
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
        # 标准档：对照表已齐后继续空转会 defer 主气泡永不 done；收束累积稿交给 Orient-G finalize。
        if (
            self.route == "hermes_lite"
            and self.report_ready_at is not None
            and self.accumulated_len >= 400
            and (time.monotonic() - self.report_ready_at) >= self.lite_report_ready_grace_s
        ):
            return (
                True,
                "personnel_lite_report_ready",
                "Hermes lite 人员对照稿已齐，Orient-G 收束编排以免空转。",
            )
        # 深度档：对照终稿锚点已出现且已取证后，再空转会挂住前端（send 禁用、无完成行）。
        # 宽限后收束；已有 user-facing 则跳过核证/成稿连环。
        if (
            self.route == "hermes_full"
            and self.report_ready_at is not None
            and self.kb_ask_calls >= 1
            and self.accumulated_len >= 360
            and (time.monotonic() - self.report_ready_at) >= self.full_report_ready_grace_s
        ):
            return (
                True,
                "hermes_full_report_ready",
                "Hermes 深度对照终稿已齐，Orient-G 收束编排以免空转挂流。",
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
