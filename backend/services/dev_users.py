"""开发/测试用：创建或更新指定部门用户（非默认密码）。"""
from __future__ import annotations

from backend.routers.settings import DEPARTMENT_FINANCE, _hash_password
from backend.services.user_acl_store import get_user, upsert_user


def ensure_department_test_user(
    username: str,
    *,
    password: str,
    department: str = DEPARTMENT_FINANCE,
    roles: list[str] | None = None,
    is_department_lead: bool = False,
) -> dict[str, str]:
    """
    创建或更新测试用户，密码为自定义值（非 123456）。
    返回 username / password / department 供测试或脚本打印。
    """
    uname = (username or "").strip()
    pwd = (password or "").strip()
    if not uname:
        raise ValueError("username required")
    if not pwd:
        raise ValueError("password required")
    if pwd == "123456":
        raise ValueError("测试用户密码不能为默认 123456")

    ph = _hash_password(pwd)
    existing = get_user(uname)
    upsert_user(
        uname,
        password_hash=ph,
        roles=list(roles or []),
        department=(department or "").strip(),
        is_department_lead=is_department_lead,
        projects=existing.get("projects") if existing else [],
        is_active=True,
    )
    return {"username": uname, "password": pwd, "department": (department or "").strip()}
