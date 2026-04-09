"""
应用级设置：财务后台路径、用户与角色等，持久化到 upload_dir 下的 app_settings.json。
密码先 SHA256 再 bcrypt 存储；默认始终鉴权登录，默认账号 admin/123456 存在。
"""
import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Optional

import bcrypt
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from backend.config import settings
from backend.database import get_db
import jwt
from sqlalchemy import text
from backend.services.kb_acl_store import (
    get_all_resource_assignments,
    get_collection_scope,
    get_department_policy,
    get_private_owner_map,
    get_project_members,
    get_project_policy,
    get_resource_owner_map,
    set_department_policy,
    set_private_owner,
    set_project_members,
    set_project_policy,
    set_resource_owner,
    set_resource_assignments,
)
from backend.services import kb_documents as kb_docs_admin
from backend.services.user_acl_store import (
    delete_user as pg_delete_user,
    get_user,
    get_user_acl_overrides,
    list_projects as pg_list_projects,
    list_users as pg_list_users,
    get_user_collection_write_overrides,
    set_user_acl_overrides,
    set_user_collection_write_overrides,
    set_user_password,
    upsert_user,
)

logger = logging.getLogger(__name__)


def _summarize_doc_share_scope(doc_id: str, tenant_id: str) -> dict[str, list[str]]:
    """
    只读汇总：返回该 doc 在 share 记录里出现过的部门/项目范围（并集）。
    仅用于管理后台展示 Multi* 的“特别处”。
    """
    try:
        targets = kb_docs_admin.get_doc_share_targets(str(doc_id))
    except Exception:
        targets = []
    dept_ids: set[str] = set()
    proj_ids: set[str] = set()
    kinds: set[str] = set()
    for t in targets or []:
        k = str((t or {}).get("target_kind") or "").strip()
        if k:
            kinds.add(k)
        meta = (t or {}).get("target") if isinstance((t or {}).get("target"), dict) else {}
        if isinstance(meta, dict):
            for d in meta.get("department_ids") or []:
                if str(d).strip():
                    dept_ids.add(str(d).strip())
            for p in meta.get("project_ids") or []:
                if str(p).strip():
                    proj_ids.add(str(p).strip())
    return {
        "kinds": sorted(kinds),
        "department_ids": sorted(dept_ids),
        "project_ids": sorted(proj_ids),
    }
router = APIRouter()

SETTINGS_FILENAME = "app_settings.json"
DEFAULT_FINANCE_PATH = "/finance"
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "123456"
ROLE_ADMIN = "admin"
ROLE_MANAGEMENT = "管理层"
DEPARTMENT_FINANCE = "财务部"

# 路径：仅允许单段，以 / 开头，仅字母数字与下划线
PATH_PATTERN = re.compile(r"^/[a-zA-Z0-9_]+$")
USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_]+$")


def _settings_path() -> Path:
    """使用绝对路径，避免工作目录变化导致读写不同文件。"""
    return Path(settings.upload_dir).resolve() / SETTINGS_FILENAME


def _password_prehash(raw: str) -> bytes:
    """先 SHA256 再交给 bcrypt（64 字节），避免 bcrypt 的 72 字节限制。"""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest().encode("utf-8")


def _hash_password(raw: str) -> str:
    """对任意长度密码做 SHA256 后 bcrypt，返回可存 JSON 的字符串。"""
    return bcrypt.hashpw(_password_prehash(raw), bcrypt.gensalt()).decode("utf-8")


def verify_password(raw: str, stored_hash: str) -> bool:
    """
    校验明文密码与存储的 bcrypt 哈希。
    先按当前格式（SHA256 再 bcrypt）校验；失败则尝试兼容旧版 passlib 存的哈希（明文直接 bcrypt）。
    """
    stored = (stored_hash or "").strip()
    if not stored:
        return False
    h = stored.encode("utf-8")
    try:
        if bcrypt.checkpw(_password_prehash(raw), h):
            return True
    except Exception:
        pass
    try:
        raw_bytes = raw.encode("utf-8")
        if len(raw_bytes) <= 72 and bcrypt.checkpw(raw_bytes, h):
            return True
    except Exception:
        pass
    return False


def _default_password_hash() -> str:
    return _hash_password(DEFAULT_ADMIN_PASSWORD)


def is_default_password(stored_hash: str) -> bool:
    """当前存储的哈希是否对应默认密码 123456（用于首次登录强制修改密码）。"""
    return bool(stored_hash and verify_password(DEFAULT_ADMIN_PASSWORD, stored_hash))


def _default_users() -> list:
    """默认用户列表：仅 admin，默认密码 123456。未开登录时加载与关闭登录时会保证此账号存在；未开登录时不可删除。"""
    return [
        {"username": DEFAULT_ADMIN_USERNAME, "password_hash": _default_password_hash(), "roles": [ROLE_ADMIN], "department": ""},
    ]


def _load_settings() -> dict:
    p = _settings_path()
    defaults = {
        # finance_path 为财务后台入口路径（可配置）；管理后台固定为 /admin（由前端路由决定）
        "finance_path": DEFAULT_FINANCE_PATH,
        "users": _default_users(),
        "auth_enabled": True,  # 默认始终鉴权，不再提供关闭登录
    }
    if not p.exists():
        return defaults.copy()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        out = defaults.copy()
        # 兼容旧字段 admin_path（历史上代表财务后台入口）
        if isinstance(data.get("finance_path"), str):
            path_str = data["finance_path"].strip()
            if PATH_PATTERN.fullmatch(path_str):
                out["finance_path"] = path_str
        elif isinstance(data.get("admin_path"), str):
            path_str = data["admin_path"].strip()
            if PATH_PATTERN.fullmatch(path_str):
                out["finance_path"] = path_str
        if isinstance(data.get("auth_enabled"), bool):
            out["auth_enabled"] = data["auth_enabled"]
        # 用户主数据来源改为 PostgreSQL；读取失败时回退 JSON（迁移期容错）
        try:
            users = pg_list_users()
            out["users"] = users if users else _default_users().copy()
        except Exception:
            # 回退旧逻辑
            if isinstance(data.get("users"), list) and len(data["users"]) > 0:
                out["users"] = []
                for u in data["users"]:
                    if isinstance(u, dict) and isinstance(u.get("username"), str) and isinstance(u.get("password_hash"), str):
                        un = u["username"].strip()
                        if USERNAME_PATTERN.fullmatch(un) and len((u.get("password_hash") or "").strip()) > 0:
                            roles = u.get("roles")
                            if not isinstance(roles, list):
                                roles = [ROLE_ADMIN]
                            else:
                                roles = [str(x).strip() for x in roles if str(x).strip()]
                            dept = (u.get("department") or "").strip() if isinstance(u.get("department"), str) else ""
                            out["users"].append(
                                {"username": un, "password_hash": (u["password_hash"] or "").strip(), "roles": roles, "department": dept}
                            )
                if not out["users"]:
                    out["users"] = _default_users().copy()
            else:
                un = (data.get("admin_username") or "").strip()
                h = (data.get("admin_password_hash") or "").strip()
                if USERNAME_PATTERN.fullmatch(un) and len(h) > 0:
                    out["users"] = [{"username": un, "password_hash": h, "roles": [ROLE_ADMIN], "department": ""}]
            if not _find_user_by_username(out.get("users") or [], DEFAULT_ADMIN_USERNAME):
                out["users"] = (out.get("users") or []) + _default_users()
        return out
    except Exception as e:
        logger.warning("读取设置文件失败，使用默认值: %s", e)
        return defaults.copy()


def _save_settings(data: dict) -> None:
    # 写入 PG 用户主数据（若传入 users）
    users_payload = data.get("users")
    if isinstance(users_payload, list):
        for u in users_payload:
            if not isinstance(u, dict):
                continue
            username = (u.get("username") or "").strip()
            password_hash = (u.get("password_hash") or "").strip()
            if not username or not password_hash:
                continue
            upsert_user(
                username,
                password_hash=password_hash,
                roles=u.get("roles") or [],
                department=(u.get("department") or "").strip(),
                is_department_lead=bool(u.get("is_department_lead")),
                projects=u.get("projects") or [],
                is_active=bool(u.get("is_active", True)),
            )

    # app_settings.json 仅保留应用级设置（finance_path/auth_enabled）
    p = _settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    minimal = {
        "finance_path": data.get("finance_path") or DEFAULT_FINANCE_PATH,
        "auth_enabled": bool(data.get("auth_enabled", True)),
    }
    p.write_text(json.dumps(minimal, ensure_ascii=False, indent=2), encoding="utf-8")


def _find_user_by_username(users: list, username: str):
    """按用户名查找（不区分大小写），返回该用户 dict 或 None。"""
    if not username or not users:
        return None
    u = (username or "").strip().lower()
    for x in users:
        if (x.get("username") or "").strip().lower() == u:
            return x
    return None


def _is_admin_user(user: dict) -> bool:
    roles = user.get("roles")
    if not isinstance(roles, list):
        return False
    return any((str(x).strip().lower() == ROLE_ADMIN) for x in roles)


def _has_view_business_dashboard(user: dict) -> bool:
    """经营数据页可见：管理员 或 管理层 或 部门=财务部（规划 2.a）。"""
    if not user:
        return False
    roles = user.get("roles") or []
    if isinstance(roles, list):
        for r in roles:
            rn = str(r).strip()
            if rn.lower() == ROLE_ADMIN:
                return True
            if rn == ROLE_MANAGEMENT:
                return True
    dept = (user.get("department") or "").strip()
    if dept == DEPARTMENT_FINANCE:
        return True
    return False


def _require_view_business_dashboard(request: Request) -> None:
    """经营数据相关接口：须已登录且具备 view_business_dashboard 权限。"""
    data = _load_settings()
    auth = request.headers.get("Authorization") or ""
    token = ""
    if auth.startswith("Bearer "):
        token = auth[7:].strip()
    token = token or (request.headers.get("X-Auth-Token") or "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="未登录")
    try:
        payload = jwt.decode(token, settings.auth_secret, algorithms=["HS256"])
        username = (payload.get("sub") or "").strip()
    except Exception:
        raise HTTPException(status_code=401, detail="登录已过期或无效")
    users = data.get("users") or []
    user = _find_user_by_username(users, username)
    if not user or not _has_view_business_dashboard(user):
        raise HTTPException(status_code=403, detail="无权限")


def _require_admin(request: Request) -> None:
    """管理后台相关接口始终要求管理员 JWT。"""
    data = _load_settings()
    auth = request.headers.get("Authorization") or ""
    token = ""
    if auth.startswith("Bearer "):
        token = auth[7:].strip()
    token = token or (request.headers.get("X-Auth-Token") or "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="未登录")
    try:
        payload = jwt.decode(token, settings.auth_secret, algorithms=["HS256"])
        username = (payload.get("sub") or "").strip()
    except Exception:
        raise HTTPException(status_code=401, detail="登录已过期或无效")
    users = data.get("users") or []
    user = _find_user_by_username(users, username)
    if not user or not _is_admin_user(user):
        raise HTTPException(status_code=403, detail="无权限")


@router.get("/public")
def get_settings_public():
    """供前端 proxy 使用，不鉴权，仅返回财务后台路径以便自定义路径 rewrite 到 /finance。"""
    data = _load_settings()
    return {"finance_path": data["finance_path"]}


class SettingsBody(BaseModel):
    finance_path: Optional[str] = None

    @field_validator("finance_path")
    @classmethod
    def validate_path(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v.startswith("/"):
            v = "/" + v
        if not PATH_PATTERN.fullmatch(v):
            raise ValueError("后台路径须为单段，仅含字母、数字、下划线，如 /finance")
        return v


class AddUserBody(BaseModel):
    username: str


class ResetPasswordBody(BaseModel):
    username: str


@router.get("")
def get_settings(request: Request):
    """返回当前应用设置（含财务后台路径、用户列表；不含密码）。"""
    _require_admin(request)
    data = _load_settings()
    users = data.get("users") or []
    return {
        "finance_path": data["finance_path"],
        "users": [
            {
                "username": u.get("username", ""),
                "roles": u.get("roles") or [],
                "department": u.get("department") or "",
                "is_department_lead": bool(u.get("is_department_lead")),
                "projects": u.get("projects") or [],
            }
            for u in users
            if u.get("username")
        ],
        "auth_enabled": True,
    }


@router.patch("")
def patch_settings(body: SettingsBody, request: Request):
    """更新应用设置（路径等）；未传的字段不修改。"""
    try:
        _require_admin(request)
        data = _load_settings()
        if body.finance_path is not None:
            data["finance_path"] = body.finance_path
        _save_settings(data)
        users = data.get("users") or []
        return {
            "finance_path": data["finance_path"],
            "users": [
                {
                    "username": u.get("username", ""),
                    "roles": u.get("roles") or [],
                    "department": u.get("department") or "",
                    "is_department_lead": bool(u.get("is_department_lead")),
                    "projects": u.get("projects") or [],
                }
                for u in users
                if u.get("username")
            ],
            "auth_enabled": True,
        }
    except OSError as e:
        raise HTTPException(
            status_code=503,
            detail=f"无法写入设置文件（{_settings_path()}），请检查 UPLOAD_DIR 目录是否存在且可写：{e!s}",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("保存设置失败")
        raise HTTPException(status_code=500, detail=f"保存设置失败：{e!s}")


@router.post("/users")
def add_user(body: AddUserBody, request: Request):
    """新增用户：仅设置用户名，默认密码 123456。首次登录须修改密码。"""
    username = (body.username or "").strip()
    if not USERNAME_PATTERN.fullmatch(username):
        raise HTTPException(status_code=400, detail="用户名仅允许字母、数字、下划线")
    try:
        _require_admin(request)
        data = _load_settings()
        users = data.get("users") or []
        if _find_user_by_username(users, username):
            raise HTTPException(status_code=400, detail="该用户名已存在")
        users.append({"username": username, "password_hash": _default_password_hash(), "roles": [], "department": ""})
        data["users"] = users
        _save_settings(data)
        return {"ok": True, "username": username, "roles": [], "department": ""}
    except HTTPException:
        raise
    except OSError as e:
        raise HTTPException(
            status_code=503,
            detail=f"无法写入设置文件（{_settings_path()}），请检查 UPLOAD_DIR 目录是否存在且可写：{e!s}",
        )
    except Exception as e:
        logger.exception("添加用户失败")
        raise HTTPException(status_code=500, detail="添加用户失败")


@router.post("/users/reset-password")
def reset_user_password(body: ResetPasswordBody, request: Request):
    """将指定用户密码重设为默认 123456。该用户下次登录须修改密码。"""
    username = (body.username or "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="请指定用户名")
    try:
        _require_admin(request)
        data = _load_settings()
        users = data.get("users") or []
        user = _find_user_by_username(users, username)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        for i, u in enumerate(users):
            if (u.get("username") or "").strip().lower() == username.lower():
                users[i] = {
                    "username": u["username"].strip(),
                    "password_hash": _default_password_hash(),
                    "roles": u.get("roles") or [],
                    "department": u.get("department") or "",
                }
                break
        data["users"] = users
        _save_settings(data)
        return {"ok": True, "username": username}
    except HTTPException:
        raise
    except OSError as e:
        raise HTTPException(
            status_code=503,
            detail=f"无法写入设置文件（{_settings_path()}），请检查 UPLOAD_DIR 目录是否存在且可写：{e!s}",
        )
    except Exception:
        logger.exception("重设密码失败")
        raise HTTPException(status_code=500, detail="重设密码失败")


class UpdateUserRolesBody(BaseModel):
    username: str
    roles: list[str]
    department: Optional[str] = None
    is_department_lead: Optional[bool] = None
    projects: Optional[list[dict]] = None


@router.patch("/users/roles")
def update_user_roles(body: UpdateUserRolesBody, request: Request):
    """更新用户角色与部门（管理员、管理层、部门=财务部等）。"""
    _require_admin(request)
    username = (body.username or "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="请指定用户名")
    roles = []
    for x in body.roles or []:
        s = str(x).strip()
        if not s:
            continue
        if s.lower() == ROLE_ADMIN:
            roles.append(ROLE_ADMIN)
        else:
            roles.append(s)
    roles = sorted(set(roles))
    try:
        data = _load_settings()
        users = data.get("users") or []
        user = _find_user_by_username(users, username)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        dept = user.get("department") or ""
        if body.department is not None:
            dept = str(body.department).strip()
        is_dep_lead = bool(body.is_department_lead) if body.is_department_lead is not None else bool(user.get("is_department_lead"))
        projects = body.projects if body.projects is not None else (user.get("projects") or [])
        upsert_user(
            (user.get("username") or "").strip(),
            password_hash=(user.get("password_hash") or "").strip(),
            roles=roles,
            department=dept,
            is_department_lead=is_dep_lead,
            projects=projects,
            is_active=bool(user.get("is_active", True)),
        )
        return {
            "ok": True,
            "username": username,
            "roles": roles,
            "department": dept,
            "is_department_lead": is_dep_lead,
            "projects": projects,
        }
    except HTTPException:
        raise
    except OSError as e:
        raise HTTPException(
            status_code=503,
            detail=f"无法写入设置文件（{_settings_path()}），请检查 UPLOAD_DIR 目录是否存在且可写：{e!s}",
        )
    except Exception:
        logger.exception("更新用户角色失败")
        raise HTTPException(status_code=500, detail="更新用户角色失败")


@router.delete("/users")
def delete_user(body: ResetPasswordBody, request: Request):
    """删除指定用户。至少保留一名用户。"""
    username = (body.username or "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="请指定用户名")
    try:
        _require_admin(request)
        data = _load_settings()
        users = data.get("users") or []
        if len(users) <= 1:
            raise HTTPException(status_code=400, detail="至少需保留一名用户，无法删除")
        user = _find_user_by_username(users, username)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        new_users = [u for u in users if (u.get("username") or "").strip().lower() != username.lower()]
        data["users"] = new_users
        _save_settings(data)
        return {"ok": True, "username": username}
    except HTTPException:
        raise
    except OSError as e:
        raise HTTPException(
            status_code=503,
            detail=f"无法写入设置文件（{_settings_path()}），请检查 UPLOAD_DIR 目录是否存在且可写：{e!s}",
        )
    except Exception as e:
        logger.exception("删除用户失败")
        raise HTTPException(status_code=500, detail="删除用户失败")


def _load_kb_acl_fixtures() -> dict:
    """
    为避免与 `backend.services.knowledge_acl` 形成循环依赖，这里直接读取 fixtures 文件。
    """
    p = Path(settings.upload_dir).resolve().parent / "backend" / "data" / "knowledge_acl_fixtures.json"
    alt = Path(__file__).resolve().parent.parent / "data" / "knowledge_acl_fixtures.json"
    for candidate in [p, alt]:
        try:
            if candidate.exists():
                return json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:
            continue
    return {}


def _collection_display_name(collection_id: str, fixtures: dict) -> str:
    c = next((x for x in (fixtures.get("collections") or []) if x.get("collection_id") == collection_id), None)
    if not isinstance(c, dict):
        return collection_id
    t = (c.get("type") or "").strip()
    name = (c.get("name") or "").strip()
    if t == "public":
        prefix = "公司-公共"
    elif t == "department":
        dep = (c.get("department_id") or "").strip() or "部门"
        prefix = f"{dep}-公共"
    elif t == "project":
        pname = (c.get("name") or "").strip() or (c.get("project_id") or "项目")
        prefix = f"{pname}-公共"
    elif t == "private":
        owner = (c.get("owner_user_id") or "").strip() or "个人"
        prefix = f"{owner}-私有"
    else:
        prefix = "知识库"
    return f"{prefix}{('：' + name) if name else ''}"


class ProjectPolicyBody(BaseModel):
    allow_leads: bool
    allow_members: bool


class ProjectMembersBody(BaseModel):
    leads: list[str] = []
    members: list[str] = []


class DepartmentPolicyBody(BaseModel):
    allow_leads: bool
    allow_members: bool


class PrivateOwnerItem(BaseModel):
    private_collection_id: str
    owner_username: str | None = None


class PrivateOwnersBody(BaseModel):
    items: list[PrivateOwnerItem] = []


class ResourceAssignmentDocItem(BaseModel):
    doc_id: str
    collection_ids: list[str] = []


class ResourceAssignmentTableItem(BaseModel):
    table_id: str
    collection_ids: list[str] = []


class ResourceAssignmentsBody(BaseModel):
    docs: list[ResourceAssignmentDocItem] = []
    tables: list[ResourceAssignmentTableItem] = []


class ResourceOwnerItem(BaseModel):
    resource_type: str  # doc|table
    resource_id: str
    owner_username: str


class ResourceOwnersBody(BaseModel):
    items: list[ResourceOwnerItem] = []


class UserOverridesBody(BaseModel):
    username: str
    overrides: list[dict[str, str]] = []


class UserWriteOverridesBody(BaseModel):
    username: str
    overrides: list[dict[str, str]] = []  # {effect, collection_id}


@router.get("/kb-acl/projects")
def kb_acl_projects(request: Request):
    _require_admin(request)
    fixtures = _load_kb_acl_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"

    projects = fixtures.get("projects") or []
    out: list[dict] = []
    for p in projects:
        pid = p.get("project_id")
        if not pid:
            continue
        policy = get_project_policy(tenant_id, pid) or {"allow_leads": True, "allow_members": True}
        members = get_project_members(tenant_id, pid) or {}
        leads = sorted([u for u, r in members.items() if r == "lead"])
        members_only = sorted([u for u, r in members.items() if r == "member"])
        out.append(
            {
                "project_id": pid,
                "name": p.get("name"),
                "policy": {"allow_leads": policy.get("allow_leads", True), "allow_members": policy.get("allow_members", True)},
                "members": {"leads": leads, "members": members_only},
            }
        )
    return {"items": out}


@router.get("/kb-acl/departments")
def kb_acl_departments(request: Request):
    _require_admin(request)
    fixtures = _load_kb_acl_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    deps = [str(x or "").strip() for x in (fixtures.get("departments") or []) if str(x or "").strip()]
    out: list[dict] = []
    for dep_id in deps:
        policy = get_department_policy(tenant_id, dep_id) or {"allow_leads": True, "allow_members": True}
        out.append(
            {
                "department_id": dep_id,
                "name": dep_id,
                "policy": {
                    "allow_leads": bool(policy.get("allow_leads", True)),
                    "allow_members": bool(policy.get("allow_members", True)),
                },
            }
        )
    return {"items": out}


@router.put("/kb-acl/departments/{department_id}/policy")
def kb_acl_set_department_policy(department_id: str, body: DepartmentPolicyBody, request: Request):
    _require_admin(request)
    fixtures = _load_kb_acl_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    dep_id = (department_id or "").strip()
    if not dep_id:
        raise HTTPException(status_code=400, detail="department_id 不能为空")
    set_department_policy(tenant_id, dep_id, allow_leads=body.allow_leads, allow_members=body.allow_members)
    return {"ok": True}


@router.put("/kb-acl/projects/{project_id}/policy")
def kb_acl_set_project_policy(project_id: str, body: ProjectPolicyBody, request: Request):
    _require_admin(request)
    fixtures = _load_kb_acl_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    set_project_policy(tenant_id, project_id, allow_leads=body.allow_leads, allow_members=body.allow_members)
    return {"ok": True}


@router.put("/kb-acl/projects/{project_id}/members")
def kb_acl_set_project_members(project_id: str, body: ProjectMembersBody, request: Request):
    _require_admin(request)
    fixtures = _load_kb_acl_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    set_project_members(tenant_id, project_id, leads=body.leads, members=body.members)
    return {"ok": True}


@router.get("/kb-acl/private-owners")
def kb_acl_private_owners(request: Request):
    _require_admin(request)
    fixtures = _load_kb_acl_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    owner_map = get_private_owner_map(tenant_id) or {}

    out: list[dict] = []
    for c in fixtures.get("collections") or []:
        if c.get("type") != "private":
            continue
        cid = c.get("collection_id")
        if not cid:
            continue
        out.append(
            {
                "private_collection_id": cid,
                "name": c.get("name"),
                "owner_username": owner_map.get(cid) or c.get("owner_user_id"),
            }
        )
    return {"items": out}


@router.put("/kb-acl/private-owners")
def kb_acl_set_private_owners(body: PrivateOwnersBody, request: Request):
    _require_admin(request)
    fixtures = _load_kb_acl_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    for item in body.items or []:
        cid = item.private_collection_id
        owner = item.owner_username
        if not cid or not owner:
            continue
        set_private_owner(tenant_id, cid, owner)
    return {"ok": True}


@router.get("/kb-acl/resource-assignments")
def kb_acl_get_resource_assignments(request: Request):
    _require_admin(request)
    fixtures = _load_kb_acl_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"

    doc_assignments = get_all_resource_assignments(tenant_id, resource_type="doc") or []
    table_assignments = get_all_resource_assignments(tenant_id, resource_type="table") or []

    doc_to_cids: dict[str, set[str]] = {}
    for a in doc_assignments:
        doc_to_cids.setdefault(str(a.get("resource_id")), set()).add(str(a.get("collection_id")))
    table_to_cids: dict[str, set[str]] = {}
    for a in table_assignments:
        table_to_cids.setdefault(str(a.get("resource_id")), set()).add(str(a.get("collection_id")))

    docs_out: list[dict] = []
    for d in fixtures.get("documents") or []:
        did = d.get("doc_id")
        if not did:
            continue
        docs_out.append(
            {
                "doc_id": did,
                "title": d.get("title"),
                "collection_ids": sorted(list(doc_to_cids.get(str(did), set()))),
                "collections_display": [
                    {"collection_id": cid, "display_name": _collection_display_name(cid, fixtures)}
                    for cid in sorted(list(doc_to_cids.get(str(did), set())))
                ],
            }
        )

    tables_out: list[dict] = []
    for t in fixtures.get("tables") or []:
        tid = t.get("table_id")
        if not tid:
            continue
        tables_out.append(
            {
                "table_id": tid,
                "name": t.get("name"),
                "collection_ids": sorted(list(table_to_cids.get(str(tid), set()))),
                "collections_display": [
                    {"collection_id": cid, "display_name": _collection_display_name(cid, fixtures)}
                    for cid in sorted(list(table_to_cids.get(str(tid), set())))
                ],
            }
        )
    collections_out = [
        {
            "collection_id": c.get("collection_id"),
            "display_name": _collection_display_name(c.get("collection_id"), fixtures),
            "type": c.get("type"),
            "space_type": c.get("space_type"),
        }
        for c in (fixtures.get("collections") or [])
        if c.get("collection_id")
    ]
    return {"docs": docs_out, "tables": tables_out, "collections": collections_out}


@router.get("/kb-acl/resource-owners")
def kb_acl_get_resource_owners(request: Request):
    _require_admin(request)
    fixtures = _load_kb_acl_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"

    doc_owner = get_resource_owner_map(tenant_id, resource_type="doc") or {}
    table_owner = get_resource_owner_map(tenant_id, resource_type="table") or {}

    docs_out: list[dict] = []
    for d in fixtures.get("documents") or []:
        did = d.get("doc_id")
        if not did:
            continue
        docs_out.append({"doc_id": did, "title": d.get("title"), "owner_username": doc_owner.get(str(did)) or None})

    tables_out: list[dict] = []
    for t in fixtures.get("tables") or []:
        tid = t.get("table_id")
        if not tid:
            continue
        tables_out.append({"table_id": tid, "name": t.get("name"), "owner_username": table_owner.get(str(tid)) or None})

    return {"docs": docs_out, "tables": tables_out}


@router.put("/kb-acl/resource-owners")
def kb_acl_set_resource_owners(body: ResourceOwnersBody, request: Request):
    _require_admin(request)
    fixtures = _load_kb_acl_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    for it in body.items or []:
        rtype = str(it.resource_type or "").strip()
        rid = str(it.resource_id or "").strip()
        owner = str(it.owner_username or "").strip()
        if rtype not in {"doc", "table"} or not rid or not owner:
            continue
        set_resource_owner(tenant_id, resource_type=rtype, resource_id=rid, owner_username=owner)
    return {"ok": True}


@router.put("/kb-acl/resource-assignments")
def kb_acl_set_resource_assignments(body: ResourceAssignmentsBody, request: Request):
    _require_admin(request)
    fixtures = _load_kb_acl_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"

    for d in body.docs or []:
        if not d.doc_id:
            continue
        set_resource_assignments(tenant_id, resource_type="doc", resource_id=d.doc_id, collection_ids=d.collection_ids or [])
    for t in body.tables or []:
        if not t.table_id:
            continue
        set_resource_assignments(tenant_id, resource_type="table", resource_id=t.table_id, collection_ids=t.collection_ids or [])
    return {"ok": True}


@router.get("/users/projects")
def get_user_projects_dimension(request: Request):
    _require_admin(request)
    fixtures = _load_kb_acl_fixtures()
    departments = [str(x or "").strip() for x in (fixtures.get("departments") or []) if str(x or "").strip()]
    return {"projects": pg_list_projects(), "departments": departments, "users": _load_settings().get("users") or []}


@router.get("/kb-acl/preview/{username}")
def kb_acl_preview_user_scope(username: str, request: Request):
    _require_admin(request)
    from backend.services.knowledge_acl import compute_acl_scope

    token = jwt.encode({"sub": username}, settings.auth_secret, algorithm="HS256")
    scope = compute_acl_scope(token)
    return {"username": username, "scope": scope}


@router.get("/kb-acl/user-overrides/{username}")
def kb_acl_get_user_overrides(username: str, request: Request):
    _require_admin(request)
    ov = get_user_acl_overrides(username)
    # set -> list
    return {
        "username": username,
        "overrides": [
            {"effect": "allow", "resource_type": "collection", "resource_id": x} for x in sorted(list(ov["allow"]["collection"]))
        ]
        + [{"effect": "allow", "resource_type": "doc", "resource_id": x} for x in sorted(list(ov["allow"]["doc"]))]
        + [{"effect": "allow", "resource_type": "table", "resource_id": x} for x in sorted(list(ov["allow"]["table"]))]
        + [{"effect": "deny", "resource_type": "collection", "resource_id": x} for x in sorted(list(ov["deny"]["collection"]))]
        + [{"effect": "deny", "resource_type": "doc", "resource_id": x} for x in sorted(list(ov["deny"]["doc"]))]
        + [{"effect": "deny", "resource_type": "table", "resource_id": x} for x in sorted(list(ov["deny"]["table"]))],
    }


@router.put("/kb-acl/user-overrides")
def kb_acl_set_user_overrides(body: UserOverridesBody, request: Request):
    _require_admin(request)
    set_user_acl_overrides(body.username, body.overrides or [])
    return {"ok": True}


@router.get("/kb-acl/user-write-overrides/{username}")
def kb_acl_get_user_write_overrides(username: str, request: Request):
    _require_admin(request)
    ov = get_user_collection_write_overrides(username)
    return {
        "username": username,
        "overrides": [{"effect": "allow", "collection_id": x} for x in sorted(list(ov["allow"]))]
        + [{"effect": "deny", "collection_id": x} for x in sorted(list(ov["deny"]))],
    }


@router.put("/kb-acl/user-write-overrides")
def kb_acl_set_user_write_overrides(body: UserWriteOverridesBody, request: Request):
    _require_admin(request)
    set_user_collection_write_overrides(body.username, body.overrides or [])
    return {"ok": True}


class KbKindPolicyItem(BaseModel):
    kb_kind: str
    policy: dict = Field(default_factory=dict)


class KbKindPoliciesPutBody(BaseModel):
    items: list[KbKindPolicyItem] = Field(default_factory=list)


@router.get("/kb-meta/default-read-policies")
def kb_meta_default_read_policies_get(request: Request):
    _require_admin(request)
    fixtures = _load_kb_acl_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    with get_db() as db:
        rows = db.execute(
            text(
                """
                SELECT kb_kind, policy_json
                FROM kb_kind_default_read_policy
                WHERE tenant_id = :t
                ORDER BY kb_kind
                """
            ),
            {"t": tenant_id},
        ).fetchall()
    items: list[dict] = []
    for r in rows:
        try:
            pol = json.loads(r[1] or "{}")
        except Exception:
            pol = {}
        if not isinstance(pol, dict):
            pol = {}
        # 文档 owner 永远可读：在管理后台强制呈现为勾选
        pol["allow_owner"] = True
        items.append({"kb_kind": str(r[0]), "policy": pol})
    return {"tenant_id": tenant_id, "items": items}


@router.put("/kb-meta/default-read-policies")
def kb_meta_default_read_policies_put(body: KbKindPoliciesPutBody, request: Request):
    _require_admin(request)
    fixtures = _load_kb_acl_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    with get_db() as db:
        for it in body.items or []:
            k = str((it.kb_kind or "").strip())
            if not k:
                continue
            pol = it.policy or {}
            if not isinstance(pol, dict):
                pol = {}
            # 文档 owner 永远可读：不允许保存为 false
            pol["allow_owner"] = True
            db.execute(
                text(
                    """
                    INSERT INTO kb_kind_default_read_policy (tenant_id, kb_kind, policy_json)
                    VALUES (:t, :k, :j)
                    ON CONFLICT (tenant_id, kb_kind) DO UPDATE
                    SET policy_json = EXCLUDED.policy_json
                    """
                ),
                {"t": tenant_id, "k": k, "j": json.dumps(pol, ensure_ascii=False)},
            )
    return {"ok": True}


class SpecialDocAclPutItem(BaseModel):
    doc_id: str
    acl: dict = Field(default_factory=dict)


class SpecialDocAclPutBody(BaseModel):
    items: list[SpecialDocAclPutItem] = Field(default_factory=list)


@router.get("/kb-meta/special-docs")
def kb_meta_special_docs_get(request: Request):
    _require_admin(request)
    fixtures = _load_kb_acl_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    trig = set(kb_docs_admin.SPECIAL_ADMIN_COLLECTION_IDS)
    collections = fixtures.get("collections") or []
    col_by_id = {str((c or {}).get("collection_id") or ""): (c or {}) for c in collections if str((c or {}).get("collection_id") or "")}
    raw = kb_docs_admin.list_docs_touching_collections(tenant_id, trig)
    items: list[dict] = []
    for r in raw:
        overlap = set(r["collection_ids"]) & trig
        if not overlap:
            continue
        did = r["doc_id"]
        overlap_sorted = sorted(overlap)
        special_collections = []
        for cid in overlap_sorted:
            c = col_by_id.get(str(cid)) or {}
            name = (c.get("name") or "").strip() if isinstance(c.get("name"), str) else ""
            space_type = (c.get("space_type") or "").strip() if isinstance(c.get("space_type"), str) else ""
            label = name or space_type or str(cid)
            special_collections.append({"collection_id": str(cid), "label": label, "space_type": space_type, "name": name})
        share_scope = _summarize_doc_share_scope(did, tenant_id)

        # 若没有 share 记录（或未写入 ids），对 Multi* 用 collection scope 兜底展示范围（只读展示）
        if isinstance(share_scope, dict):
            dep_ids = share_scope.get("department_ids") or []
            proj_ids = share_scope.get("project_ids") or []
            if not dep_ids and not proj_ids:
                for sc in special_collections:
                    st = str((sc or {}).get("space_type") or "").strip()
                    cid = str((sc or {}).get("collection_id") or "").strip()
                    if not cid or st not in {"MultiDeptPublic", "MultiDeptLead", "MultiProjectPublic", "MultiProjectLead"}:
                        continue
                    scope = get_collection_scope(tenant_id, cid) or {}
                    if st in {"MultiDeptPublic", "MultiDeptLead"}:
                        dep_ids = [str(x).strip() for x in (scope.get("department_ids") or []) if str(x).strip()]
                    if st in {"MultiProjectPublic", "MultiProjectLead"}:
                        proj_ids = [str(x).strip() for x in (scope.get("project_ids") or []) if str(x).strip()]
                    if dep_ids or proj_ids:
                        share_scope = {
                            "kinds": [st],
                            "department_ids": sorted(set(dep_ids)),
                            "project_ids": sorted(set(proj_ids)),
                        }
                        break
        acl = kb_docs_admin.get_special_doc_acl(tenant_id, did)
        # CompanyPublic：特殊文档权限默认全员可读（避免后台出现“公司公共库但全不勾”的困惑）
        if "c_company_public_1" in overlap_sorted and (not isinstance(acl, dict) or len(acl) == 0):
            acl = {"allow_all": True}
        items.append(
            {
                "doc_id": did,
                "title": kb_docs_admin.resolve_doc_title(tenant_id, did, fixtures),
                "collection_ids": r["collection_ids"],
                "special_collection_ids": overlap_sorted,
                "special_collections": special_collections,
                "acl": acl,
                # 只读展示：Multi* 共享时选择的部门/项目范围（按文档 share 记录合并）
                "share_scope": share_scope,
            }
        )
    return {"tenant_id": tenant_id, "items": items}


@router.put("/kb-meta/special-docs")
def kb_meta_special_docs_put(body: SpecialDocAclPutBody, request: Request):
    _require_admin(request)
    fixtures = _load_kb_acl_fixtures()
    tenant_id = fixtures.get("tenant_id") or "tenant1"
    for it in body.items or []:
        did = str((it.doc_id or "").strip())
        if not did:
            continue
        kb_docs_admin.set_special_doc_acl(tenant_id, did, it.acl or {})
    return {"ok": True}
