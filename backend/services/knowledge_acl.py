"""
最小 Knowledge ACL（用于端到端验收）。

本实现优先满足 2.b 的验收目标：
- 能计算 allowed scope（collections/docs/chunks/tables）
- 空 scope 时应能触发 deny（由上层路由/检索链路处理）

当前阶段：使用 fixture（backend/data/knowledge_acl_fixtures.json）或内置默认最小数据。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import jwt

from backend.config import settings
from backend.routers.settings import _find_user_by_username, _load_settings
from backend.services.kb_acl_store import (
    get_all_resource_assignments,
    get_collection_scope,
    get_department_policy,
    get_private_owner_map,
    get_project_members,
    get_project_policy,
    get_resource_owner_map,
)
from backend.services.user_acl_store import get_user, get_user_acl_overrides
from backend.services.user_acl_store import get_user_collection_write_overrides

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UserContext:
    username: str
    tenant_id: str
    department: str
    roles: list[str]
    project_memberships: list[str]


def _decode_username_from_token(token: str) -> Optional[str]:
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.auth_secret, algorithms=["HS256"])
        return (payload.get("sub") or "").strip() or None
    except Exception:
        return None


def _extract_user_context_from_token(token: str, fixtures: dict[str, Any]) -> Optional[UserContext]:
    username = _decode_username_from_token(token)
    if not username:
        return None
    data = _load_settings()
    users = data.get("users") or []
    u = _find_user_by_username(users, username)
    if not isinstance(u, dict):
        u = get_user(username) or {}

    # fixture 优先提供 project membership 等测试关系
    user_key = username
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    department = (u.get("department") if isinstance(u, dict) else "") or ""
    roles = (u.get("roles") if isinstance(u, dict) else []) or []
    roles = [str(x).strip() for x in roles if str(x).strip()]

    # 先用 PG 用户维度里的 projects，再回退 fixtures
    project_memberships = [str((x or {}).get("project_id") or "").strip() for x in (u.get("projects") or []) if str((x or {}).get("project_id") or "").strip()]
    if not project_memberships:
        memberships_by_user = fixtures.get("user_project_memberships") or {}
        project_memberships = memberships_by_user.get(user_key) or []
        project_memberships = [str(x).strip() for x in project_memberships if str(x).strip()]

    return UserContext(
        username=username,
        tenant_id=tenant_id,
        department=department,
        roles=roles,
        project_memberships=project_memberships,
    )


def _default_fixtures() -> dict[str, Any]:
    # 内置最小数据：用于“先把验收链路跑通”，后续由 acc-3 替换为完整 fixture。
    return {
        "tenant_id": "tenant1",
        "departments": ["财务部", "研发部"],
        "projects": [{"project_id": "proj1", "name": "项目A"}],
        "user_project_memberships": {"admin": ["proj1"]},
        "collections": [
            {
                "collection_id": "c_company_public_1",
                "type": "public",
                "space_type": "CompanyPublic",
                "tenant_id": "tenant1",
                "name": "公司财务规章制度",
            },
            {
                "collection_id": "c_finance_public_1",
                "type": "department",
                "space_type": "FinancePublic",
                "tenant_id": "tenant1",
                "department_id": "财务部",
                "name": "财务公共制度",
            },
            {
                "collection_id": "c_dept_public_1",
                "type": "department",
                "space_type": "DeptPublic",
                "tenant_id": "tenant1",
                "department_id": "研发部",
                "name": "研发部门流程手册",
            },
            {
                "collection_id": "c_project_public_1",
                "type": "project",
                "space_type": "ProjectPublic",
                "tenant_id": "tenant1",
                "project_id": "proj1",
                "name": "项目核算电子表",
            },
            {
                "collection_id": "c_private_admin_1",
                "type": "private",
                "space_type": "Private",
                "tenant_id": "tenant1",
                "owner_user_id": "admin",
                "name": "个人私有资料（示例）",
            },
        ],
        "documents": [
            {
                "doc_id": "d_finance_rules_1",
                "tenant_id": "tenant1",
                "title": "公司财务规章制度示例",
                "collection_ids": ["c_company_public_1"],
                "sections": [
                    {
                        "section_id": "s1",
                        "keywords": ["规章", "制度"],
                        "text": "本制度规定：财务报销流程、审批链与归档要求。",
                        "chunks": [
                            {"chunk_id": "ch1", "chunk_seq_no": 1, "text": "财务报销流程：提交申请→部门审批→财务审核→归档。"}
                        ],
                    }
                ],
            },
            {
                "doc_id": "d_finance_public_rules_1",
                "tenant_id": "tenant1",
                "title": "财务公共制度示例",
                "collection_ids": ["c_finance_public_1"],
                "sections": [
                    {
                        "section_id": "s2",
                        "keywords": ["报销", "审核"],
                        "text": "财务审核口径与时间要求。",
                        "chunks": [
                            {"chunk_id": "ch2", "chunk_seq_no": 1, "text": "财务审核：T+2 工作日完成；逾期需补充材料说明。"}
                        ],
                    }
                ],
            },
        ],
        "tables": [
            {
                "table_id": "t_project_profit_1",
                "tenant_id": "tenant1",
                "collection_id": "c_project_public_1",
                "name": "项目A利润表（示例）",
                "columns": [
                    {"column_id": "col_metric", "name": "指标"},
                    {"column_id": "col_amount", "name": "数值"},
                ],
                "rows": [
                    {
                        "row_key": "row_total_profit",
                        "values": {"col_metric": "本年累计净利润", "col_amount": 1234.56},
                        "keywords": ["净利润", "本年累计"],
                    }
                ],
            }
        ],
    }


def load_fixtures() -> dict[str, Any]:
    p = Path(settings.upload_dir).resolve().parent / "backend" / "data" / "knowledge_acl_fixtures.json"
    # 上面推断依赖运行目录；为稳妥，再尝试 workspase 相对位置：backend/data
    alt = Path(__file__).resolve().parent.parent / "data" / "knowledge_acl_fixtures.json"
    for candidate in [p, alt]:
        try:
            if candidate.exists():
                return json.loads(candidate.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("load fixtures failed: %s", e)
    return _default_fixtures()


def compute_acl_scope(
    user_token: str,
    intent_sources: Optional[dict[str, Any]] = None,
    *,
    fixtures: Optional[dict[str, Any]] = None,
) -> dict[str, list[str]]:
    """
    计算 allowed scope。

    返回：
    - allowed_collection_ids
    - allowed_doc_ids
    - allowed_chunk_ids
    - allowed_table_ids
    - writable_collection_ids
    - writable_doc_ids
    - writable_table_ids
    """
    fixtures = fixtures or load_fixtures()
    ctx = _extract_user_context_from_token(user_token, fixtures)
    if not ctx:
        # 未鉴权：返回空 scope（上层应触发 deny）
        return {
            "allowed_collection_ids": [],
            "allowed_doc_ids": [],
            "allowed_chunk_ids": [],
            "allowed_table_ids": [],
            "writable_collection_ids": [],
            "writable_doc_ids": [],
            "writable_table_ids": [],
        }

    # 管理类角色：在最小验收阶段默认放开所有知识库，便于你验证 citation/deny 链路
    if any(r.lower() in {"admin", "管理层"} for r in ctx.roles):
        all_collection_ids = [c["collection_id"] for c in fixtures.get("collections") or []]
        all_doc_ids = [d["doc_id"] for d in fixtures.get("documents") or []]
        all_chunk_ids: list[str] = []
        for d in fixtures.get("documents") or []:
            for s in d.get("sections") or []:
                for ch in s.get("chunks") or []:
                    cid = ch.get("chunk_id")
                    if cid:
                        all_chunk_ids.append(str(cid))
        all_table_ids = [t["table_id"] for t in fixtures.get("tables") or []]
        try:
            from backend.services import kb_documents as _kbd

            extra_docs = _kbd.list_all_uploaded_doc_ids(ctx.tenant_id)
            all_doc_ids = sorted(set([x for x in all_doc_ids if x] + extra_docs))
            for did in extra_docs:
                all_chunk_ids.extend(_kbd.list_chunk_ids_for_doc(ctx.tenant_id, did))
        except Exception:
            pass
        return {
            "allowed_collection_ids": [x for x in all_collection_ids if x],
            "allowed_doc_ids": [x for x in all_doc_ids if x],
            "allowed_chunk_ids": [x for x in all_chunk_ids if x],
            "allowed_table_ids": [x for x in all_table_ids if x],
            "writable_collection_ids": [x for x in all_collection_ids if x],
            "writable_doc_ids": [x for x in all_doc_ids if x],
            "writable_table_ids": [x for x in all_table_ids if x],
        }

    collections = fixtures.get("collections") or []
    allowed_collection_ids: list[str] = []
    # DB 关系：private owner、project policy/members
    try:
        private_owner_map = get_private_owner_map(ctx.tenant_id)
    except Exception:
        private_owner_map = {}

    # 先用 fixtures 的 department/public 规则确定集合
    for c in collections:
        c_type = c.get("type")
        if c_type == "department":
            dep_id = str(c.get("department_id") or "").strip()
            if not dep_id or dep_id != ctx.department:
                continue
            # 部门：按 DB policy 判定（成员/负责人）
            try:
                policy = get_department_policy(ctx.tenant_id, dep_id) or {"allow_leads": True, "allow_members": True}
                allow_leads = bool(policy.get("allow_leads", True))
                allow_members = bool(policy.get("allow_members", True))
                is_dep_lead = bool((get_user(ctx.username) or {}).get("is_department_lead"))
                if allow_members:
                    allowed_collection_ids.append(c["collection_id"])
                if is_dep_lead and allow_leads:
                    allowed_collection_ids.append(c["collection_id"])
            except Exception:
                # DB 不可用时回退：成员仅本部门、负责人按 is_department_lead 放开本部门
                allowed_collection_ids.append(c["collection_id"])
        elif c_type == "public":
            st_pub = str(c.get("space_type") or "")
            if st_pub in {
                "MultiDeptPublic",
                "MultiDeptLead",
                "MultiProjectPublic",
                "MultiProjectLead",
            }:
                pass
            elif str(c.get("tenant_id") or "") == ctx.tenant_id:
                allowed_collection_ids.append(c["collection_id"])
        elif c_type == "private":
            # private：owner 由 DB 决定（若 DB 不可用则回退 fixtures）
            db_owner = private_owner_map.get(c.get("collection_id"))
            if db_owner is not None:
                if str(db_owner) == ctx.username:
                    allowed_collection_ids.append(c["collection_id"])
            else:
                if str(c.get("owner_user_id") or "") == ctx.username:
                    allowed_collection_ids.append(c["collection_id"])
        elif c_type == "project":
            # project：允许由 DB policy + DB members 共同决定（区分 lead/member）
            project_id = c.get("project_id")
            if not project_id:
                continue
            try:
                policy = get_project_policy(ctx.tenant_id, project_id) or {}
                allow_leads = bool(policy.get("allow_leads", True))
                allow_members = bool(policy.get("allow_members", True))
                members = get_project_members(ctx.tenant_id, project_id) or {}
                role = members.get(ctx.username)
                if role == "lead" and allow_leads:
                    allowed_collection_ids.append(c["collection_id"])
                if role == "member" and allow_members:
                    allowed_collection_ids.append(c["collection_id"])
            except Exception:
                # DB 不可用时回退：用 fixtures 的 project membership（不区分 lead/member）
                if str(project_id) in ctx.project_memberships:
                    allowed_collection_ids.append(c["collection_id"])

    # 动态私人库 collection（上传文档时注册到 kb_private_collection_owner）
    for pcid, owner in (private_owner_map or {}).items():
        if str(owner) == ctx.username and str(pcid).startswith("c_private_dyn_"):
            allowed_collection_ids.append(str(pcid))

    # 多部门/多项目 逻辑集合（scope 在 kb_collection_scope）
    urow = get_user(ctx.username) or {}
    dep_u = str(urow.get("department") or "").strip()
    is_dep_lead_u = bool(urow.get("is_department_lead"))
    for c in collections:
        st_m = str(c.get("space_type") or "")
        if st_m not in {
            "MultiDeptPublic",
            "MultiDeptLead",
            "MultiProjectPublic",
            "MultiProjectLead",
        }:
            continue
        cid_m = c.get("collection_id")
        if not cid_m:
            continue
        scope = get_collection_scope(ctx.tenant_id, str(cid_m))
        dept_ids = [str(x).strip() for x in (scope.get("department_ids") or []) if str(x).strip()]
        proj_ids = [str(x).strip() for x in (scope.get("project_ids") or []) if str(x).strip()]
        ok = False
        if st_m == "MultiDeptPublic" and dep_u and dep_u in dept_ids:
            ok = True
        elif st_m == "MultiDeptLead" and dep_u and dep_u in dept_ids and is_dep_lead_u:
            ok = True
        elif st_m == "MultiProjectPublic":
            for pid in proj_ids:
                try:
                    mem = get_project_members(ctx.tenant_id, pid) or {}
                    if ctx.username in mem:
                        ok = True
                        break
                except Exception:
                    if pid in ctx.project_memberships:
                        ok = True
                        break
        elif st_m == "MultiProjectLead":
            for pid in proj_ids:
                try:
                    mem = get_project_members(ctx.tenant_id, pid) or {}
                    if mem.get(ctx.username) == "lead":
                        ok = True
                        break
                except Exception:
                    pass
        if ok:
            allowed_collection_ids.append(str(cid_m))

    allowed_collection_ids = [x for x in allowed_collection_ids if x]

    # allowed_doc_ids/allowed_chunk_ids/allowed_table_ids：从 DB 的 resource->collection assignment 计算
    allowed_doc_ids_set: set[str] = set()
    allowed_table_ids_set: set[str] = set()
    doc_to_cols: dict[str, set[str]] = {}
    try:
        doc_assignments = get_all_resource_assignments(ctx.tenant_id, resource_type="doc")
        for a in doc_assignments:
            cid = str(a.get("collection_id") or "").strip()
            rid = str(a.get("resource_id") or "").strip()
            if rid and cid:
                doc_to_cols.setdefault(rid, set()).add(cid)
            if cid in allowed_collection_ids and rid:
                allowed_doc_ids_set.add(rid)
        table_assignments = get_all_resource_assignments(ctx.tenant_id, resource_type="table")
        for a in table_assignments:
            if a.get("collection_id") in allowed_collection_ids:
                table_id = a.get("resource_id")
                if table_id:
                    allowed_table_ids_set.add(str(table_id))
    except Exception:
        # DB 不可用：回退 fixtures 的静态归属
        for d in fixtures.get("documents") or []:
            doc_collections = d.get("collection_ids") or []
            if any(cid in allowed_collection_ids for cid in doc_collections):
                doc_id = d.get("doc_id")
                if doc_id:
                    allowed_doc_ids_set.add(str(doc_id))
        for t in fixtures.get("tables") or []:
            cid = str(t.get("collection_id") or "")
            if cid in allowed_collection_ids:
                tid = t.get("table_id")
                if tid:
                    allowed_table_ids_set.add(str(tid))

    allowed_doc_ids = sorted(allowed_doc_ids_set)
    allowed_table_ids = sorted(allowed_table_ids_set)

    # 文档 owner 永远可读（无论归属到哪类知识库）
    try:
        from backend.services import kb_documents as _kbd_owner

        owned_doc_ids = _kbd_owner.list_uploaded_doc_ids_by_owner(ctx.tenant_id, ctx.username)
        allowed_doc_ids = sorted(set(allowed_doc_ids).union(set(owned_doc_ids)))
    except Exception:
        pass

    # Multi*：可读范围按“共享时选择的部门/项目”过滤（按文档记录 share 元数据）
    try:
        from backend.services import kb_documents as _kbd_shares

        multi_collection_ids: set[str] = set()
        multi_space_types = {"MultiDeptPublic", "MultiDeptLead", "MultiProjectPublic", "MultiProjectLead"}
        for c in collections:
            if str(c.get("space_type") or "") in multi_space_types and c.get("collection_id"):
                multi_collection_ids.add(str(c.get("collection_id")))

        if multi_collection_ids and allowed_doc_ids:
            urow = get_user(ctx.username) or {}
            dep_u = str(urow.get("department") or "").strip()
            is_dep_lead_u = bool(urow.get("is_department_lead"))

            # 预取用户项目 membership（以 PG 用户维度为准，回退 ctx.project_memberships）
            proj_memberships = set([x for x in ctx.project_memberships if x])

            def _ok_multi_doc(doc_id: str) -> bool:
                # owner 永远可读
                try:
                    if _kbd_shares.get_document_owner(ctx.tenant_id, str(doc_id)) == ctx.username:
                        return True
                except Exception:
                    return True
                cols = doc_to_cols.get(str(doc_id), set())
                if not cols or len(cols.intersection(multi_collection_ids)) == 0:
                    return True  # 非 Multi* 资源不走此过滤

                targets = _kbd_shares.get_doc_share_targets(str(doc_id))
                if not targets:
                    return False

                # 合并所有 share 记录的范围（同一 doc 多次共享取并集）
                allow_depts: set[str] = set()
                allow_projs: set[str] = set()
                kinds: set[str] = set()
                for t in targets:
                    k = str(t.get("target_kind") or "").strip()
                    kinds.add(k)
                    meta = t.get("target") if isinstance(t.get("target"), dict) else {}
                    for d in (meta.get("department_ids") or []) if isinstance(meta, dict) else []:
                        if str(d).strip():
                            allow_depts.add(str(d).strip())
                    for p in (meta.get("project_ids") or []) if isinstance(meta, dict) else []:
                        if str(p).strip():
                            allow_projs.add(str(p).strip())

                # Dept 类
                if any(k in {"MultiDeptPublic", "MultiDeptLead"} for k in kinds):
                    if dep_u and dep_u in allow_depts:
                        # lead 变体：必须是本部门负责人
                        if "MultiDeptLead" in kinds:
                            return bool(is_dep_lead_u)
                        return True

                # Project 类
                if any(k in {"MultiProjectPublic", "MultiProjectLead"} for k in kinds):
                    if len(proj_memberships.intersection(allow_projs)) > 0:
                        if "MultiProjectLead" in kinds:
                            # 需要在至少一个被选项目里是 lead
                            for pid in proj_memberships.intersection(allow_projs):
                                try:
                                    mem = get_project_members(ctx.tenant_id, pid) or {}
                                    if mem.get(ctx.username) == "lead":
                                        return True
                                except Exception:
                                    pass
                            return False
                        return True

                return False

            allowed_doc_ids = [did for did in allowed_doc_ids if _ok_multi_doc(did)]
    except Exception:
        pass

    # 写权限：
    # - 默认 owner 可写（owner 映射来自 DB）
    # - 手工覆盖：按 collection 维度 allow/deny（用于“同步到其它知识库后可编辑”的长期演进）
    writable_collection_ids: list[str] = []
    writable_doc_ids: list[str] = []
    writable_table_ids: list[str] = []
    try:
        wov = get_user_collection_write_overrides(ctx.username)
        write_allow_cols = set(wov.get("allow") or set())
        write_deny_cols = set(wov.get("deny") or set())
        writable_collection_ids = sorted(set([c for c in allowed_collection_ids if c]).intersection(write_allow_cols).difference(write_deny_cols))

        doc_owner = get_resource_owner_map(ctx.tenant_id, resource_type="doc")
        table_owner = get_resource_owner_map(ctx.tenant_id, resource_type="table")

        # 反查 resource -> collection，用于 collection write 覆盖
        table_to_cols: dict[str, set[str]] = {}
        try:
            doc_assignments = get_all_resource_assignments(ctx.tenant_id, resource_type="doc")
            for a in doc_assignments:
                rid = str(a.get("resource_id") or "").strip()
                cid = str(a.get("collection_id") or "").strip()
                if rid and cid:
                    doc_to_cols.setdefault(rid, set()).add(cid)
            table_assignments = get_all_resource_assignments(ctx.tenant_id, resource_type="table")
            for a in table_assignments:
                rid = str(a.get("resource_id") or "").strip()
                cid = str(a.get("collection_id") or "").strip()
                if rid and cid:
                    table_to_cols.setdefault(rid, set()).add(cid)
        except Exception:
            doc_to_cols = {}
            table_to_cols = {}

        writable_doc_ids = sorted(
            [
                did
                for did in allowed_doc_ids
                if (doc_owner.get(str(did)) == ctx.username)
                or (len(doc_to_cols.get(str(did), set()).intersection(set(writable_collection_ids))) > 0)
            ]
        )
        writable_table_ids = sorted(
            [
                tid
                for tid in allowed_table_ids
                if (table_owner.get(str(tid)) == ctx.username)
                or (len(table_to_cols.get(str(tid), set()).intersection(set(writable_collection_ids))) > 0)
            ]
        )
    except Exception:
        writable_collection_ids = []
        writable_doc_ids = []
        writable_table_ids = []

    # 用户级覆盖（allow/deny）
    try:
        ov = get_user_acl_overrides(ctx.username)
        allow_cols = ov["allow"]["collection"]
        deny_cols = ov["deny"]["collection"]
        allow_docs = ov["allow"]["doc"]
        deny_docs = ov["deny"]["doc"]
        allow_tables = ov["allow"]["table"]
        deny_tables = ov["deny"]["table"]

        allowed_collection_ids = sorted(set([x for x in allowed_collection_ids if x]).union(allow_cols).difference(deny_cols))
        allowed_doc_ids = sorted(set([x for x in allowed_doc_ids if x]).union(allow_docs).difference(deny_docs))
        allowed_table_ids = sorted(set([x for x in allowed_table_ids if x]).union(allow_tables).difference(deny_tables))
    except Exception:
        pass

    allowed_chunk_ids: list[str] = []
    if allowed_doc_ids:
        allowed_doc_ids_for_check = set(allowed_doc_ids)
        for d in fixtures.get("documents") or []:
            doc_id = d.get("doc_id")
            if str(doc_id) not in allowed_doc_ids_for_check:
                continue
            for s in d.get("sections") or []:
                for ch in s.get("chunks") or []:
                    cid = ch.get("chunk_id")
                    if cid:
                        allowed_chunk_ids.append(str(cid))
        try:
            from backend.services import kb_documents as _kbd2

            for did in allowed_doc_ids:
                if str(did).startswith("ud_"):
                    allowed_chunk_ids.extend(_kbd2.list_chunk_ids_for_doc(ctx.tenant_id, str(did)))
        except Exception:
            pass

    # 去空与去重
    return {
        "allowed_collection_ids": sorted(set([x for x in allowed_collection_ids if x])),
        "allowed_doc_ids": sorted(set([x for x in allowed_doc_ids if x])),
        "allowed_chunk_ids": sorted(set([x for x in allowed_chunk_ids if x])),
        "allowed_table_ids": sorted(set([x for x in allowed_table_ids if x])),
        "writable_collection_ids": sorted(set([x for x in writable_collection_ids if x])),
        "writable_doc_ids": sorted(set([x for x in writable_doc_ids if x])),
        "writable_table_ids": sorted(set([x for x in writable_table_ids if x])),
    }

