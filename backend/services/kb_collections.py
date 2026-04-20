from __future__ import annotations

from typing import Any


def dynamic_private_collection_id(username: str) -> str:
    u = "".join(c if c.isalnum() or c in "_-" else "_" for c in (username or "").strip())
    return f"c_private_dyn_{u}"


def resolve_share_collection_ids(
    fixtures: dict[str, Any],
    tenant_id: str,
    *,
    kb_kind: str,
    department_ids: list[str],
    project_ids: list[str],
    company_public: bool,
) -> list[str]:
    kind = (kb_kind or "").strip()
    cols: list[str] = []
    collections = fixtures.get("collections") or []

    def dept_collections(dep: str) -> list[str]:
        dep = (dep or "").strip()
        out = []
        for c in collections:
            if c.get("type") != "department":
                continue
            if str(c.get("department_id") or "").strip() == dep:
                out.append(str(c.get("collection_id")))
        return out

    def project_collections(pid: str) -> list[str]:
        pid = (pid or "").strip()
        out = []
        for c in collections:
            if c.get("type") != "project":
                continue
            if str(c.get("project_id") or "").strip() == pid:
                out.append(str(c.get("collection_id")))
        return out

    if kind in {"DeptPublic", "DeptLead"}:
        for d in department_ids or []:
            cols.extend(dept_collections(d))
    elif kind in {"ProjectPublic", "ProjectLead"}:
        for p in project_ids or []:
            cols.extend(project_collections(p))
    elif kind == "CompanyPublic":
        for c in collections:
            if c.get("type") == "public" and str(c.get("space_type") or "") == "CompanyPublic":
                cid = c.get("collection_id")
                if cid:
                    cols.append(str(cid))
                break
        if not cols:
            for c in collections:
                if c.get("type") == "public" and str(c.get("tenant_id") or "") == tenant_id:
                    cols.append(str(c.get("collection_id")))
                    break
    elif kind == "MultiDeptPublic":
        for c in collections:
            if str(c.get("space_type") or "") == "MultiDeptPublic":
                cols.append(str(c.get("collection_id")))
                break
    elif kind == "MultiDeptLead":
        for c in collections:
            if str(c.get("space_type") or "") == "MultiDeptLead":
                cols.append(str(c.get("collection_id")))
                break
    elif kind == "MultiProjectPublic":
        for c in collections:
            if str(c.get("space_type") or "") == "MultiProjectPublic":
                cols.append(str(c.get("collection_id")))
                break
    elif kind == "MultiProjectLead":
        for c in collections:
            if str(c.get("space_type") or "") == "MultiProjectLead":
                cols.append(str(c.get("collection_id")))
                break

    return sorted(set([x for x in cols if x]))

