"""Hermes / Agent 对话历史窗口：控 token，保留最近轮次与当前 user 问句。"""

from __future__ import annotations

from typing import Any


def _as_msg(m: dict[str, Any]) -> dict[str, str]:
    role = str(m.get("role") or "user")
    if role not in {"user", "assistant", "system"}:
        role = "user"
    return {"role": role, "content": str(m.get("content") or "")}


def _dialog_turns(dialog: list[dict[str, str]]) -> list[list[dict[str, str]]]:
    """将 user/assistant 对话切成轮次：每轮以一条 user 开头，后接连续 assistant。"""
    turns: list[list[dict[str, str]]] = []
    cur: list[dict[str, str]] = []
    for m in dialog:
        if m["role"] == "user":
            if cur:
                turns.append(cur)
            cur = [m]
        elif m["role"] == "assistant":
            if not cur:
                cur = [m]
            else:
                cur.append(m)
        else:
            if cur:
                turns.append(cur)
                cur = []
    if cur:
        turns.append(cur)
    return turns


def trim_dialog_messages(
    messages: list[dict[str, Any]] | None,
    *,
    max_turns: int | None = 16,
    max_chars: int | None = 48000,
) -> list[dict[str, str]]:
    """
    裁剪发给 LLM 的历史：
    - 保留全部前置 system
    - 按「轮次」保留最近 max_turns（含当前 user）
    - 再按总 content 字符从旧到新丢弃，直至 ≤ max_chars
    - 永不丢弃最后一条 user（当前问句）；若其单独超限则只保留该条
    """
    raw = [_as_msg(m) for m in (messages or [])]
    systems = [m for m in raw if m["role"] == "system"]
    dialog = [m for m in raw if m["role"] in {"user", "assistant"}]
    if not dialog:
        return systems

    turns_n = int(max_turns) if max_turns is not None and int(max_turns) > 0 else 0
    if turns_n > 0:
        turns = _dialog_turns(dialog)
        kept_turns = turns[-turns_n:] if len(turns) > turns_n else turns
        dialog = [m for t in kept_turns for m in t]

    char_cap = int(max_chars) if max_chars is not None and int(max_chars) > 0 else 0
    if char_cap > 0 and dialog:
        last_user_idx = None
        for i in range(len(dialog) - 1, -1, -1):
            if dialog[i]["role"] == "user":
                last_user_idx = i
                break
        if last_user_idx is None:
            last_user_idx = len(dialog) - 1
        must_keep = dialog[last_user_idx:]
        must_chars = sum(len(m["content"]) for m in must_keep)
        if must_chars >= char_cap:
            dialog = must_keep
        else:
            prefix = dialog[:last_user_idx]
            budget = char_cap - must_chars
            selected_rev: list[dict[str, str]] = []
            used = 0
            for m in reversed(prefix):
                c = len(m["content"])
                if used + c > budget:
                    # 装不下则停止，保证剩余 dialog 为连续后缀（勿跳过大消息保留更旧碎片）
                    break
                selected_rev.append(m)
                used += c
            dialog = list(reversed(selected_rev)) + must_keep

    return systems + dialog
