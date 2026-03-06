"""
应用级设置：财务后台路径、登录用户名与默认密码等，持久化到 upload_dir 下的 app_settings.json。
密码先 SHA256 再 bcrypt 存储，以支持任意长度且兼容 bcrypt 72 字节限制；直接使用 bcrypt 库，避免 passlib 与新版 bcrypt 不兼容。
"""
import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Optional

import bcrypt
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from backend.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

SETTINGS_FILENAME = "app_settings.json"
DEFAULT_ADMIN_PATH = "/admin"
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "123456"

# 路径：仅允许单段，以 / 开头，仅字母数字与下划线
ADMIN_PATH_PATTERN = re.compile(r"^/[a-zA-Z0-9_]+$")
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
    """默认用户列表：仅 admin，默认密码 123456。"""
    return [
        {"username": DEFAULT_ADMIN_USERNAME, "password_hash": _default_password_hash()},
    ]


def _load_settings() -> dict:
    p = _settings_path()
    defaults = {
        "admin_path": DEFAULT_ADMIN_PATH,
        "users": _default_users(),
        "auth_enabled": False,
    }
    if not p.exists():
        return defaults.copy()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        out = defaults.copy()
        if isinstance(data.get("admin_path"), str):
            path_str = data["admin_path"].strip()
            if ADMIN_PATH_PATTERN.fullmatch(path_str):
                out["admin_path"] = path_str
        if isinstance(data.get("auth_enabled"), bool):
            out["auth_enabled"] = data["auth_enabled"]
        # 用户列表：优先使用 users；若无则从旧字段 admin_username / admin_password_hash 迁移
        if isinstance(data.get("users"), list) and len(data["users"]) > 0:
            out["users"] = []
            for u in data["users"]:
                if isinstance(u, dict) and isinstance(u.get("username"), str) and isinstance(u.get("password_hash"), str):
                    un = u["username"].strip()
                    if USERNAME_PATTERN.fullmatch(un) and len((u.get("password_hash") or "").strip()) > 0:
                        out["users"].append({"username": un, "password_hash": (u["password_hash"] or "").strip()})
            if not out["users"]:
                out["users"] = _default_users().copy()
        else:
            un = (data.get("admin_username") or "").strip()
            h = (data.get("admin_password_hash") or "").strip()
            if USERNAME_PATTERN.fullmatch(un) and len(h) > 0:
                out["users"] = [{"username": un, "password_hash": h}]
        return out
    except Exception as e:
        logger.warning("读取设置文件失败，使用默认值: %s", e)
        return defaults.copy()


def _save_settings(data: dict) -> None:
    p = _settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _find_user_by_username(users: list, username: str):
    """按用户名查找（不区分大小写），返回该用户 dict 或 None。"""
    if not username or not users:
        return None
    u = (username or "").strip().lower()
    for x in users:
        if (x.get("username") or "").strip().lower() == u:
            return x
    return None


class SettingsBody(BaseModel):
    admin_path: Optional[str] = None
    auth_enabled: Optional[bool] = None

    @field_validator("admin_path")
    @classmethod
    def validate_admin_path(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v.startswith("/"):
            v = "/" + v
        if not ADMIN_PATH_PATTERN.fullmatch(v):
            raise ValueError("后台路径须为单段，仅含字母、数字、下划线，如 /admin")
        return v


class AddUserBody(BaseModel):
    username: str


class ResetPasswordBody(BaseModel):
    username: str


@router.get("")
def get_settings():
    """返回当前应用设置（含财务后台路径、用户列表；不含密码）。"""
    data = _load_settings()
    users = data.get("users") or []
    return {
        "admin_path": data["admin_path"],
        "users": [{"username": u.get("username", "")} for u in users if u.get("username")],
        "auth_enabled": data.get("auth_enabled", False),
    }


@router.patch("")
def patch_settings(body: SettingsBody):
    """更新应用设置（路径、是否启用登录）；未传的字段不修改。"""
    try:
        data = _load_settings()
        if body.admin_path is not None:
            data["admin_path"] = body.admin_path
        if body.auth_enabled is not None:
            data["auth_enabled"] = body.auth_enabled
        _save_settings(data)
        users = data.get("users") or []
        return {
            "admin_path": data["admin_path"],
            "users": [{"username": u.get("username", "")} for u in users if u.get("username")],
            "auth_enabled": data.get("auth_enabled", False),
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
def add_user(body: AddUserBody):
    """新增用户：仅设置用户名，默认密码 123456。首次登录须修改密码。"""
    username = (body.username or "").strip()
    if not USERNAME_PATTERN.fullmatch(username):
        raise HTTPException(status_code=400, detail="用户名仅允许字母、数字、下划线")
    try:
        data = _load_settings()
        users = data.get("users") or []
        if _find_user_by_username(users, username):
            raise HTTPException(status_code=400, detail="该用户名已存在")
        users.append({"username": username, "password_hash": _default_password_hash()})
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
    except Exception as e:
        logger.exception("添加用户失败")
        raise HTTPException(status_code=500, detail="添加用户失败")


@router.post("/users/reset-password")
def reset_user_password(body: ResetPasswordBody):
    """将指定用户密码重设为默认 123456。该用户下次登录须修改密码。"""
    username = (body.username or "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="请指定用户名")
    try:
        data = _load_settings()
        users = data.get("users") or []
        user = _find_user_by_username(users, username)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        for i, u in enumerate(users):
            if (u.get("username") or "").strip().lower() == username.lower():
                users[i] = {"username": u["username"].strip(), "password_hash": _default_password_hash()}
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
    except Exception as e:
        logger.exception("重设密码失败")
        raise HTTPException(status_code=500, detail="重设密码失败")


@router.delete("/users")
def delete_user(body: ResetPasswordBody):
    """删除指定用户。至少保留一名用户。"""
    username = (body.username or "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="请指定用户名")
    try:
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
