"""部门公共库文件夹分享：文件夹内文档应进入 allowed_doc_ids。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.main import app
from backend.routers.settings import DEPARTMENT_FINANCE
from backend.services.dev_users import ensure_department_test_user
from backend.services.kb_folders import collect_doc_ids_in_visible_folders, collect_subtree_doc_ids
from backend.services.knowledge_acl import compute_acl_scope, load_fixtures
from backend.services.knowledge_pipeline import ask_knowledge

# 竞品财报25（分享到财务部门公共库）
FOLDER_JINGPIN_CAIBAO_25 = "f_6f3638e4513f492c9610ddb5dda77c20"
HUAQING_DOC_IN_FOLDER = "ud_0308b5860e704ac1af6a2f584c324901"


client = TestClient(app)


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


def test_finance_acl_includes_docs_in_shared_dept_folder():
    token = _finance_token()
    fixtures = load_fixtures()
    scope = compute_acl_scope(token, fixtures=fixtures)
    allowed = set(scope.get("allowed_doc_ids") or [])
    subtree = set(collect_subtree_doc_ids("tenant1", FOLDER_JINGPIN_CAIBAO_25))
    assert len(subtree) > 50, "folder should have many docs"
    assert HUAQING_DOC_IN_FOLDER in subtree
    assert HUAQING_DOC_IN_FOLDER in allowed, "shared folder docs must be readable by finance_test"


def test_collect_doc_ids_in_visible_folders_matches_visibility_rule():
    token = _finance_token()
    fixtures = load_fixtures()
    scope = compute_acl_scope(token, fixtures=fixtures)
    via_folder = collect_doc_ids_in_visible_folders(
        "tenant1",
        username="finance_test",
        allowed_collection_ids=set(scope.get("allowed_collection_ids") or []),
    )
    assert HUAQING_DOC_IN_FOLDER in via_folder


def test_ask_knowledge_via_folder_scope_finds_huaqing_chunk():
    token = _finance_token()
    fixtures = load_fixtures()
    from backend.services.kb_scope_resolve import resolve_kb_scope_for_ask

    resolved = resolve_kb_scope_for_ask(
        "tenant1",
        {"selected_folder_ids": [FOLDER_JINGPIN_CAIBAO_25]},
    )
    out2 = ask_knowledge(
        token,
        "华清25、24两年损益对比分析表",
        selected_collection_ids=resolved["collection_ids"] or None,
        attached_doc_ids=resolved["attached_doc_ids"] or None,
        limit_to_attached=bool(resolved.get("limit_to_attached")),
        fixtures=fixtures,
    )
    assert not out2.get("denied"), out2
    cites = out2.get("citations") or []
    doc_ids = {c.get("doc_id") for c in cites if c.get("doc_id")}
    assert HUAQING_DOC_IN_FOLDER in doc_ids, f"got {sorted(doc_ids)[:8]}"


def test_top_citations_prefers_pl_table_over_toc():
    """目录 chunk 不应压过含营业收入与金额的利润表 chunk。"""
    from backend.services.agent_kb_prefetch import _top_citations_for_llm

    token = _finance_token()
    fixtures = load_fixtures()
    from backend.services.kb_scope_resolve import resolve_kb_scope_for_ask

    q = "做一张华清25和24年损益对比的表，仅依据知识库证据，缺项请说明。"
    resolved = resolve_kb_scope_for_ask(
        "tenant1",
        {"selected_folder_ids": [FOLDER_JINGPIN_CAIBAO_25]},
    )
    out = ask_knowledge(
        token,
        q,
        selected_collection_ids=resolved["collection_ids"] or None,
        attached_doc_ids=resolved["attached_doc_ids"] or None,
        limit_to_attached=bool(resolved.get("limit_to_attached")),
        fixtures=fixtures,
    )
    top = _top_citations_for_llm(
        list(out.get("citations") or []),
        q,
        limit=5,
        tenant_id="tenant1",
        fixtures=fixtures,
    )
    top_ids = [c.get("doc_id") for c in top]
    # 损益对比默认合并口径优先于母公司表、目录
    assert "ud_91f55322e2594b9c9d3ba7ceb89fafb2" in top_ids[:2], top_ids
    assert "ud_903a91400a1d4e6e846a219bc602d9fd" not in top_ids[:3], top_ids
