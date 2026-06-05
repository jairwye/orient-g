"""Hermes session_key 与 Orient-G 智能体会话绑定。"""

from __future__ import annotations

from backend.services.hermes_session_resolve import resolve_hermes_session_key


def test_explicit_hermes_session_id_wins():
    key = resolve_hermes_session_key(
        username="wangjia",
        hermes_session_id="abc-123",
        orientg_chat_session_id="s_chat_1",
    )
    assert key == "orientg-abc-123"


def test_chat_session_derives_stable_key_per_user():
    k1 = resolve_hermes_session_key(
        username="wangjia",
        hermes_session_id=None,
        orientg_chat_session_id="s_agent_99",
    )
    k2 = resolve_hermes_session_key(
        username="wangjia",
        hermes_session_id=None,
        orientg_chat_session_id="s_agent_99",
    )
    assert k1 == k2
    assert "wangjia" in k1
    assert "s_agent_99" in k1


def test_different_users_same_chat_id_differ():
    a = resolve_hermes_session_key(
        username="user_a",
        orientg_chat_session_id="s_same",
    )
    b = resolve_hermes_session_key(
        username="user_b",
        orientg_chat_session_id="s_same",
    )
    assert a != b
