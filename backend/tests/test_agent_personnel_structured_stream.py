"""人员横比：struct gate 须 emit replace_reply 以便浏览器 DOM 与终稿一致。"""

from __future__ import annotations

import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app
from backend.routers.settings import DEPARTMENT_FINANCE
from backend.services.dev_users import ensure_department_test_user
from backend.tests.test_acl_folder_shared_docs import FOLDER_JINGPIN_CAIBAO_25

QUERY = "对比分析YYCQ和可比公司A25年的人员结构"
client = TestClient(app)

PERSONNEL_DUMP = (
    "YYCQ vs 可比公司A · 2025 人员结构对比\n"
    "以下对比基于知识库 docling section / excel chunk 证据（非硬编码数值）。\n"
    "可比公司A 研发人员数量 1,378\nYYCQ 1.1信息-人员 研发 70\n"
    "对比说明\n两家主体人员结构口径可能不同。\ncitations（12）"
)

BAD_HERMES_DRAFT = (
    "## YYCQ vs 可比公司A · 2025 人员结构对比\n"
    "### 核心指标对照\n| 主体 | 研发/分项人数 |\n| YYCQ | 1 |\n"
    "可比公司A 1378\n"
)

STRUCTURED = (
    "## YYCQ vs 可比公司A · 2025 人员结构对比\n\n"
    "### 人员结构对照\n\n"
    "| 职能归属 | 可比公司A | YYCQ |\n"
    "| --- | --- | --- |\n"
    "| 研发 | 1378 人（占员工 43.91%） | 70 人 |\n"
    "| 运营 | 242 人 | 61 人 |\n"
    "| 销售 | 946 人 | 证据未覆盖 |\n\n"
    "### 对比分析\n\n"
    "- **结构差异**：YYCQ为 excel 职能分项。\n"
)

PREFETCH = {
    "ok": True,
    "citations": [{"doc_id": "d1", "chunk_id": "c1"}],
    "evidence_pack": {"task_type": "compare"},
}


def _finance_token() -> str:
    ensure_department_test_user(
        "finance_test",
        password="FinanceTest!2026",
        department=DEPARTMENT_FINANCE,
    )
    r = client.post(
        "/api/auth/login",
        json={"username": "finance_test", "password": "FinanceTest!2026"},
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _parse_events(body: str) -> list[dict]:
    out: list[dict] = []
    for block in body.split("\n\n"):
        for line in block.split("\n"):
            if not line.strip().startswith("data:"):
                continue
            raw = line.strip()[5:].strip()
            if not raw or raw == "[DONE]":
                continue
            try:
                out.append(json.loads(raw))
            except json.JSONDecodeError:
                pass
    return out


def test_personnel_struct_gate_emits_replace_reply(monkeypatch):
    monkeypatch.setattr(settings, "hermes_enabled", True)
    monkeypatch.setattr(settings, "hermes_base_url", "http://127.0.0.1:8642")
    monkeypatch.setattr(settings, "hermes_dev_mock", False)
    monkeypatch.setattr(settings, "hermes_agent_kb_prefetch", True)
    monkeypatch.setattr(settings, "hermes_agent_kb_synthesize", False)
    monkeypatch.setattr(settings, "hermes_native_mcp_reply", False)
    monkeypatch.setattr(settings, "hermes_native_skip_supplemental", False)

    def _fake_stream(**kwargs):
        yield {"type": "delta", "content": PERSONNEL_DUMP[:80]}
        yield {
            "type": "done",
            "reply": PERSONNEL_DUMP,
            "tool_calls": [{"name": "orientg_kb_ask"}],
            "hermes_stream_stats": {"orientg_kb_ask_calls": 1},
        }

    monkeypatch.setattr(
        "backend.routers.agent.prefetch_kb_context",
        lambda *a, **k: (
            [{"role": "user", "content": QUERY}],
            PREFETCH,
            [{"name": "orientg_kb_ask", "prefetch": True, "status": "ok"}],
        ),
    )
    monkeypatch.setattr("backend.routers.agent.stream_agent_chat", _fake_stream)
    monkeypatch.setattr(
        "backend.services.agent_kb_supplemental.needs_hermes_supplemental",
        lambda **k: False,
    )

    with patch(
        "backend.services.kb_ask_mcp_reply.personnel_compare_reply_from_prefetch",
        return_value=STRUCTURED,
    ):
        r = client.post(
            "/api/agent/chat/stream",
            headers={
                "Authorization": f"Bearer {_finance_token()}",
                "X-Agent-Run-Id": "test-personnel-struct-replace",
            },
            json={
                "messages": [{"role": "user", "content": QUERY}],
                "kb_scope": {"selected_folder_ids": [FOLDER_JINGPIN_CAIBAO_25]},
                "agent_mode": "deep",
            },
        )
    assert r.status_code == 200, r.text[:500]
    evts = _parse_events(r.text)
    replaces = [e for e in evts if e.get("type") == "replace_reply"]
    assert replaces, "struct gate 应下发 replace_reply"
    assert "### 人员结构对照" in str(replaces[-1].get("content"))
    done = next(e for e in evts if e.get("type") == "done")
    assert "### 人员结构对照" in str(done.get("reply"))


def test_personnel_mcp_coerce_emits_replace_reply(monkeypatch):
    """目标3：MCP 骨架纠偏后必须 replace_reply，否则浏览器仍停在过程稿。"""
    monkeypatch.setattr(settings, "hermes_enabled", True)
    monkeypatch.setattr(settings, "hermes_base_url", "http://127.0.0.1:8642")
    monkeypatch.setattr(settings, "hermes_dev_mock", False)
    monkeypatch.setattr(settings, "hermes_agent_kb_prefetch", True)
    monkeypatch.setattr(settings, "hermes_agent_kb_synthesize", False)
    monkeypatch.setattr(settings, "hermes_native_mcp_reply", True)
    monkeypatch.setattr(settings, "hermes_native_skip_supplemental", True)

    scale_draft = (
        "I need to compare personnel structure.\n"
        "可比公司A：总员工3138人，销售人员946人，运营人员242人，研发人员1378人；"
        "YYCQ：研发70人，运营61人。对比分析两家口径不同。\n"
    )

    def _fake_stream(**kwargs):
        yield {"type": "delta", "content": scale_draft}
        yield {
            "type": "done",
            "reply": scale_draft,
            "tool_calls": [{"name": "orientg_kb_ask"}],
            "hermes_stream_stats": {"orientg_kb_ask_calls": 2},
        }

    prefetch = {
        "ok": True,
        "reply": (
            "可比公司A 研发人员数量 1378；销售人员 946人；运营人员 242人。"
            "YYCQ 1.1信息-人员 研发 70.00 运营 61.00。"
        ),
        "citations": [{"doc_id": "d1"}, {"doc_id": "d2"}],
        "evidence_pack": {"task_type": "compare"},
        "evidence_excerpts": [
            {
                "entity": "可比公司A",
                "doc_id": "d1",
                "excerpt": "研发人员数量 1378；销售人员 946人；运营人员 242人",
            },
            {
                "entity": "YYCQ",
                "doc_id": "d2",
                "excerpt": "1.1信息-人员 研发 70.00 运营 61.00",
            },
        ],
    }
    monkeypatch.setattr(
        "backend.routers.agent.prefetch_kb_context",
        lambda *a, **k: (
            [{"role": "user", "content": QUERY}],
            prefetch,
            [{"name": "orientg_kb_ask", "prefetch": True, "status": "ok"}],
        ),
    )
    monkeypatch.setattr("backend.routers.agent.stream_agent_chat", _fake_stream)
    monkeypatch.setattr(
        "backend.services.agent_kb_supplemental.needs_hermes_supplemental",
        lambda **k: False,
    )
    monkeypatch.setattr(
        "backend.services.agent_kb_supplemental.apply_personnel_structured_final_gate",
        lambda reply, **k: (reply, False),
    )
    monkeypatch.setattr(
        "backend.services.agent_kb_supplemental.apply_personnel_misattribution_gate",
        lambda reply, **k: (reply, False),
    )

    r = client.post(
        "/api/agent/chat/stream",
        headers={
            "Authorization": f"Bearer {_finance_token()}",
            "X-Agent-Run-Id": "test-personnel-mcp-coerce-replace",
        },
        json={
            "messages": [{"role": "user", "content": QUERY}],
            "kb_scope": {"selected_folder_ids": [FOLDER_JINGPIN_CAIBAO_25]},
            "agent_mode": "deep",
        },
    )
    assert r.status_code == 200, r.text[:500]
    evts = _parse_events(r.text)
    replaces = [e for e in evts if e.get("type") == "replace_reply"]
    assert replaces, "MCP coerce 后必须下发 replace_reply（否则 CDP 仍读过程稿）"
    content = str(replaces[-1].get("content") or "")
    assert "人员结构对照" in content
    assert "1378" in content and "946" in content
    assert "以上数据均来自当前知识库 citations 节选" not in content
    done = next(e for e in evts if e.get("type") == "done")
    assert done.get("reply_source") == "hermes"
    assert done.get("structured_gate_applied") is False


def test_personnel_early_replace_on_bad_hermes_draft(monkeypatch):
    """深度横比：流式中途不 replace；done 后 struct gate 一次 replace。"""
    monkeypatch.setattr(settings, "hermes_enabled", True)
    monkeypatch.setattr(settings, "hermes_base_url", "http://127.0.0.1:8642")
    monkeypatch.setattr(settings, "hermes_dev_mock", False)
    monkeypatch.setattr(settings, "hermes_agent_kb_prefetch", True)
    monkeypatch.setattr(settings, "hermes_agent_kb_synthesize", False)
    # legacy：允许 structured gate 整页纠偏（非 native 保险丝路径）
    monkeypatch.setattr(settings, "hermes_native_mcp_reply", False)
    monkeypatch.setattr(settings, "hermes_native_skip_supplemental", False)

    def _fake_stream(**kwargs):
        yield {"type": "delta", "content": BAD_HERMES_DRAFT}
        yield {
            "type": "done",
            "reply": BAD_HERMES_DRAFT,
            "tool_calls": [{"name": "orientg_kb_ask"}],
            "hermes_stream_stats": {"orientg_kb_ask_calls": 1},
        }

    monkeypatch.setattr(
        "backend.routers.agent.prefetch_kb_context",
        lambda *a, **k: (
            [{"role": "user", "content": QUERY}],
            PREFETCH,
            [{"name": "orientg_kb_ask", "prefetch": True, "status": "ok"}],
        ),
    )
    monkeypatch.setattr("backend.routers.agent.stream_agent_chat", _fake_stream)
    monkeypatch.setattr(
        "backend.services.agent_kb_supplemental.needs_hermes_supplemental",
        lambda **k: False,
    )

    with patch(
        "backend.services.kb_ask_mcp_reply.personnel_compare_reply_from_prefetch",
        return_value=STRUCTURED,
    ):
        r = client.post(
            "/api/agent/chat/stream",
            headers={
                "Authorization": f"Bearer {_finance_token()}",
                "X-Agent-Run-Id": "test-personnel-early-replace",
            },
            json={
                "messages": [{"role": "user", "content": QUERY}],
                "kb_scope": {"selected_folder_ids": [FOLDER_JINGPIN_CAIBAO_25]},
                "agent_mode": "deep",
            },
        )
    assert r.status_code == 200, r.text[:500]
    evts = _parse_events(r.text)
    early = [e for e in evts if e.get("type") == "replace_reply" and e.get("step") == "personnel_early_structured"]
    assert not early, "流式中途不应 early replace（避免终稿闪烁）"
    replaces = [e for e in evts if e.get("type") == "replace_reply"]
    assert replaces, "done 后应 replace 结构化终稿"
    assert "### 人员结构对照" in str(replaces[-1].get("content"))
