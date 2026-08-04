"""深度档人员结构：MCP 不得因 bridge 未命中而 doc allowed scope empty。"""

from __future__ import annotations

import time

import jwt
import pytest

from backend.config import settings
from backend.database import init_hermes_session_store_table
from backend.services import hermes_session_context as session_ctx
from backend.services import hermes_token_bridge as bridge
from backend.services import hermes_shared_session as shared
from backend.services import orientg_mcp_tools as tools
from backend.services.hermes_client import _register_session
from backend.tests.test_acl_folder_shared_docs import FOLDER_JINGPIN_CAIBAO_25

PERSONNEL_QUERY = "对比分析YYCQ和可比公司A25年的人员结构"


@pytest.fixture(autouse=True)
def _reset():
    init_hermes_session_store_table()
    bridge.reset_for_tests()
    session_ctx.reset_for_tests()
    shared.reset_for_tests()
    yield
    bridge.reset_for_tests()
    session_ctx.reset_for_tests()
    shared.reset_for_tests()


def _jwt(sub: str = "finance_test") -> str:
    return jwt.encode(
        {"sub": sub, "iat": int(time.time()), "exp": int(time.time()) + 3600},
        settings.auth_secret,
        algorithm="HS256",
    )


def test_mcp_kb_scope_token_acl_when_session_empty():
    """Session 无 kb_scope 时 MCP 继承 JWT ACL，避免 doc allowed scope empty。"""
    tok = _jwt()
    sk = _register_session(
        tok,
        "s_personnel_acl",
        username="finance_test",
        orientg_chat_session_id="s_personnel_acl",
        kb_scope={},
        orientg_route="hermes_full",
    )
    bridge.reset_for_tests()
    session_ctx.reset_for_tests()

    res = tools.orientg_kb_ask("", PERSONNEL_QUERY, hermes_session_key=sk)
    assert res.get("denied") is not True, res.get("reason")
    assert res.get("reason") != "doc allowed scope empty"


def test_mcp_kb_scope_empty_lists_falls_to_token_acl():
    """Session 登记空 list kb_scope 时仍走 JWT ACL，避免 resolve 空 cols 阻断 fallback。"""
    tok = _jwt()
    sk = _register_session(
        tok,
        "s_personnel_empty_lists",
        username="finance_test",
        orientg_chat_session_id="s_personnel_empty_lists",
        kb_scope={
            "selected_folder_ids": [],
            "selected_collection_ids": [],
            "selected_table_ids": [],
        },
        orientg_route="hermes_full",
    )
    bridge.reset_for_tests()
    session_ctx.reset_for_tests()

    res = tools.orientg_kb_ask("", PERSONNEL_QUERY, hermes_session_key=sk)
    assert res.get("denied") is not True, res.get("reason")
    assert res.get("reason") != "doc allowed scope empty"


def test_mcp_kb_ask_personnel_after_register_session_persists_to_db():
    tok = _jwt()
    sk = _register_session(
        tok,
        "s_personnel_tdd",
        username="finance_test",
        orientg_chat_session_id="s_personnel_tdd",
        kb_scope={"selected_folder_ids": [FOLDER_JINGPIN_CAIBAO_25]},
        orientg_route="hermes_full",
    )
    bridge.reset_for_tests()
    session_ctx.reset_for_tests()

    res = tools.orientg_kb_ask("", PERSONNEL_QUERY, hermes_session_key=sk)
    assert res.get("denied") is not True, res.get("reason")
    assert res.get("reason") != "doc allowed scope empty"
    assert len(res.get("citations") or []) >= 1


def test_mcp_list_docs_denies_unresolved_session_token():
    bridge.reset_for_tests()
    session_ctx.reset_for_tests()
    res = tools.orientg_kb_list_docs("", hermes_session_key="orientg-missing-session")
    assert res.get("denied") is True
    assert res.get("reason") == "session_token_unresolved"


def test_mcp_list_docs_uses_session_folder_when_no_folder_id():
    tok = _jwt()
    sk = _register_session(
        tok,
        "s_personnel_list",
        username="finance_test",
        orientg_chat_session_id="s_personnel_list",
        kb_scope={"selected_folder_ids": [FOLDER_JINGPIN_CAIBAO_25]},
        orientg_route="hermes_full",
    )
    bridge.reset_for_tests()
    session_ctx.reset_for_tests()
    res = tools.orientg_kb_list_docs("", hermes_session_key=sk)
    assert res.get("denied") is not True, res.get("reason")
    assert res.get("reason") != "session_token_unresolved"
    # folder 子树与 ACL 交集在部分 fixture 环境可能为空；至少不应 silent empty token


def test_personnel_compare_hermes_draft_is_bad_old_template():
    from backend.services.personnel_compare_report import personnel_compare_hermes_draft_is_bad

    bad = (
        "## YYCQ vs 可比公司A · 2025 人员结构对比\n"
        "### 核心指标对照\n| 主体 | 研发 |\n| YYCQ | 1 |\n"
    )
    assert personnel_compare_hermes_draft_is_bad(bad, user_query=PERSONNEL_QUERY)
