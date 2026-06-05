"""MCP 写库 ACL：Hermes 会话 allow_kb_write + folder scope。"""

import base64
import time

import jwt
import pytest

from backend.config import settings
from backend.services import orientg_mcp_tools as mcp_tools
from backend.services.hermes_session_context import register as register_ctx
from backend.services.hermes_session_context import reset_for_tests


def _token(sub: str = "admin") -> str:
    payload = {"sub": sub, "iat": int(time.time()), "exp": int(time.time()) + 3600}
    return jwt.encode(payload, settings.auth_secret, algorithm="HS256")


@pytest.fixture(autouse=True)
def _reset_ctx():
    reset_for_tests()
    yield
    reset_for_tests()


def test_upload_denied_without_allow_kb_write_on_hermes_session(monkeypatch):
    monkeypatch.setattr(
        "backend.services.orientg_mcp_tools.compute_acl_scope",
        lambda *a, **k: {"writable_collection_ids": ["c_private_admin"], "writable_doc_ids": []},
    )
    monkeypatch.setattr("backend.services.orientg_mcp_tools.write_event", lambda *a, **k: None)
    register_ctx(
        "orientg-test-sess",
        allow_kb_write=False,
        kb_scope={"selected_folder_ids": ["f_scope"]},
        orientg_route="hermes_full",
    )
    tok = _token()
    from backend.services.hermes_token_bridge import register as register_tok

    register_tok("orientg-test-sess", tok)
    raw = b"# x"
    out = mcp_tools.orientg_kb_upload(
        "",
        filename="a.md",
        content_base64=base64.b64encode(raw).decode("ascii"),
        folder_id="f_scope",
        hermes_session_key="orientg-test-sess",
    )
    assert out.get("denied") is True
    assert out.get("reason") == "kb_write_not_allowed"


def test_upload_denied_when_folder_outside_scope(monkeypatch):
    monkeypatch.setattr(
        "backend.services.orientg_mcp_tools.compute_acl_scope",
        lambda *a, **k: {"writable_collection_ids": ["c_private_admin"], "writable_doc_ids": []},
    )
    monkeypatch.setattr(
        "backend.services.orientg_mcp_tools._folder_writable",
        lambda *a, **k: True,
    )
    monkeypatch.setattr("backend.services.orientg_mcp_tools.write_event", lambda *a, **k: None)
    register_ctx(
        "orientg-test-sess",
        allow_kb_write=True,
        kb_scope={"selected_folder_ids": ["f_allowed"]},
        orientg_route="hermes_full",
    )
    out = mcp_tools.orientg_kb_upload(
        _token(),
        filename="a.md",
        content_base64=base64.b64encode(b"x").decode("ascii"),
        folder_id="f_other",
        hermes_session_key="orientg-test-sess",
    )
    assert out.get("denied") is True
    assert out.get("reason") == "folder_not_in_kb_scope"


def test_import_artifact_requires_folder_on_hermes_session(monkeypatch):
    monkeypatch.setattr("backend.services.orientg_mcp_tools.write_event", lambda *a, **k: None)
    register_ctx(
        "orientg-test-sess",
        allow_kb_write=True,
        kb_scope={"selected_folder_ids": ["f1"]},
    )
    out = mcp_tools.orientg_kb_import_artifact(
        _token(),
        filename="r.md",
        content_base64=base64.b64encode(b"# r").decode("ascii"),
        hermes_session_key="orientg-test-sess",
    )
    assert out.get("denied") is True
    assert out.get("reason") == "folder_id_required"
