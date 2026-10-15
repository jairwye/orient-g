"""Hermes 对话历史裁剪：控 token 成本，保留最近轮次与当前 user 问句。"""

from backend.services.hermes_message_window import trim_dialog_messages


def _ua(n: int) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for i in range(n):
        out.append({"role": "user", "content": f"u{i}"})
        out.append({"role": "assistant", "content": f"a{i}"})
    return out


def test_trim_keeps_last_n_turns_and_current_user():
    msgs = _ua(20) + [{"role": "user", "content": "current-q"}]
    trimmed = trim_dialog_messages(msgs, max_turns=3, max_chars=None)
    # 3 turns ≈ 最近 2 轮完整 UA + 当前 user（或等价：最近 3 个 user 起）
    assert trimmed[-1] == {"role": "user", "content": "current-q"}
    contents = [m["content"] for m in trimmed]
    assert "u0" not in contents
    assert "u17" in contents or "u18" in contents or "u19" in contents
    assert "current-q" in contents
    # 不超过约 3 轮（user 条数 ≤ 3）
    assert sum(1 for m in trimmed if m["role"] == "user") <= 3


def test_trim_respects_max_chars_from_recent_end():
    msgs = [
        {"role": "user", "content": "OLD" * 200},
        {"role": "assistant", "content": "OLDANS" * 200},
        {"role": "user", "content": "mid"},
        {"role": "assistant", "content": "mid-a"},
        {"role": "user", "content": "now"},
    ]
    trimmed = trim_dialog_messages(msgs, max_turns=20, max_chars=40)
    assert trimmed[-1]["content"] == "now"
    total = sum(len(m.get("content") or "") for m in trimmed)
    assert total <= 40 or trimmed == [{"role": "user", "content": "now"}]
    assert all(m["content"] != "OLD" * 200 for m in trimmed)


def test_trim_char_budget_keeps_contiguous_suffix():
    """超大中间消息装不下时不得跳过它而保留更旧小消息（须连续后缀窗口）。"""
    msgs = [
        {"role": "user", "content": "tiny-old"},
        {"role": "assistant", "content": "tiny-old-a"},
        {"role": "user", "content": "HUGE" * 80},
        {"role": "assistant", "content": "mid-a"},
        {"role": "user", "content": "now"},
    ]
    # budget 仅够 must_keep("now") + 少量 prefix；HUGE 装不下 → 不得留下 tiny-old*
    trimmed = trim_dialog_messages(msgs, max_turns=20, max_chars=30)
    contents = [m["content"] for m in trimmed if m["role"] != "system"]
    assert contents[-1] == "now"
    assert "tiny-old" not in contents
    assert "tiny-old-a" not in contents
    assert not any(c.startswith("HUGE") for c in contents)


def test_trim_never_drops_current_user_even_if_over_char_budget():
    long_q = "Q" * 500
    msgs = [{"role": "user", "content": long_q}]
    trimmed = trim_dialog_messages(msgs, max_turns=1, max_chars=10)
    assert len(trimmed) == 1
    assert trimmed[0]["content"] == long_q


def test_trim_preserves_incoming_system_messages():
    msgs = [
        {"role": "system", "content": "keep-me"},
        {"role": "user", "content": "u0"},
        {"role": "assistant", "content": "a0"},
        {"role": "user", "content": "u1"},
    ]
    trimmed = trim_dialog_messages(msgs, max_turns=1, max_chars=None)
    assert trimmed[0] == {"role": "system", "content": "keep-me"}
    assert trimmed[-1]["content"] == "u1"


def test_build_messages_applies_window(monkeypatch):
    from backend.config import settings
    from backend.services import hermes_client as hc

    monkeypatch.setattr(settings, "hermes_chat_history_max_turns", 2)
    monkeypatch.setattr(settings, "hermes_chat_history_max_chars", 0)
    long = _ua(10) + [{"role": "user", "content": "latest"}]
    built = hc._build_messages(
        long,
        username="u",
        kb_scope={},
        allow_kb_write=False,
        attached_doc_ids=[],
        hermes_session_id=None,
    )
    assert built[0]["role"] == "system"
    dialog = [m for m in built if m["role"] != "system"]
    assert dialog[-1]["content"] == "latest"
    assert sum(1 for m in dialog if m["role"] == "user") <= 2
    assert not any(m["content"] == "u0" for m in dialog)
