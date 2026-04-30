"""
数据解析回复体检（validate_analysis_json 的最小落地）：若模型返回整块 JSON 且自称结构化结论，
则校验是否含第七节约定键；不通过时在 reply 末尾追加警示，不阻断主流程。
"""

from __future__ import annotations

import json
import re
from typing import Any


def _try_parse_json_object(text: str) -> dict[str, Any] | None:
    t = (text or "").strip()
    if not t.startswith("{"):
        return None
    try:
        obj = json.loads(t)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", t)
        if m:
            try:
                obj = json.loads(m.group(1))
                return obj if isinstance(obj, dict) else None
            except json.JSONDecodeError:
                return None
    return None


def append_output_shape_audit(reply: str, *, prompt_addon: str | None = None) -> str:
    """
    当 prompt_addon 显式包含 output_shape 或用户要求 JSON 结论时，对「整段 JSON」做键级体检。
    """
    pa = (prompt_addon or "").lower()
    care = "output_shape" in pa or "conclusion" in pa and "risks" in pa
    if not care:
        return reply

    obj = _try_parse_json_object(reply)
    if obj is None:
        return reply

    missing = [k for k in ("conclusion", "risks", "suggestions") if k not in obj]
    if missing:
        return (
            reply.rstrip()
            + "\n\n（系统：检测到 JSON 形态输出，但缺少字段 "
            + ", ".join(missing)
            + "，与 prompt.data_parse.output_shape 约定不一致，请勿用于自动落库。）"
        )
    return reply
