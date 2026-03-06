"""
页面登录鉴权：当设置中 auth_enabled 为 true 时，本项目页面需先登录。
Token 仅由前端 sessionStorage + Authorization 头传递，不读 Cookie，关闭标签页即需重新登录。
"""
import time
from typing import Optional

import jwt
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.config import settings as config
from backend.routers.settings import (
    DEFAULT_ADMIN_PASSWORD,
    _find_user_by_username,
    _hash_password,
    _load_settings,
    _save_settings,
    is_default_password,
    verify_password,
)

router = APIRouter()
ALGORITHM = "HS256"
COOKIE_NAME = "orient_g_token"
# 30 分钟无活动则过期；/me 时返回新 token 供前端滑动刷新
TOKEN_EXP_SECONDS = 30 * 60


def _get_token_from_request(request: Request) -> Optional[str]:
    """从 Authorization: Bearer 或 X-Auth-Token 读取（后者为代理环境备用），不读 Cookie。"""
    auth = request.headers.get("Authorization")
    if auth and auth.startswith("Bearer "):
        t = auth[7:].strip()
        if t:
            return t
    return request.headers.get("X-Auth-Token") or None


def _create_token(username: str) -> str:
    payload = {
        "sub": username,
        "iat": int(time.time()),
        "exp": int(time.time()) + TOKEN_EXP_SECONDS,
    }
    return jwt.encode(payload, config.auth_secret, algorithm=ALGORITHM)


def _decode_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, config.auth_secret, algorithms=[ALGORITHM])
        return payload.get("sub")
    except Exception:
        return None


class LoginBody(BaseModel):
    username: str
    password: str


class ChangePasswordBody(BaseModel):
    current_password: str
    new_password: str


@router.post("/login")
def login(body: LoginBody):
    """校验用户名密码，成功则设置 JWT Cookie 并返回 ok。"""
    data = _load_settings()
    if not data.get("auth_enabled"):
        return JSONResponse(
            status_code=400,
            content={"detail": "未启用页面登录，无需登录"},
        )
    username = (body.username or "").strip()
    password = body.password or ""
    if not username or not password:
        return JSONResponse(status_code=400, content={"detail": "请输入用户名和密码"})
    users = data.get("users") or []
    user = _find_user_by_username(users, username)
    if not user or not verify_password(password, (user.get("password_hash") or "").strip()):
        return JSONResponse(status_code=401, content={"detail": "用户名或密码错误"})
    canonical_username = (user.get("username") or "").strip()
    token = _create_token(canonical_username)
    admin_hash = (user.get("password_hash") or "").strip()
    # 若本次登录用的不是默认密码 123456，则不再要求修改密码，避免改密后仍被误判为默认密码
    if (password or "").strip() == DEFAULT_ADMIN_PASSWORD:
        must_change = is_default_password(admin_hash)
    else:
        must_change = False
    # 登录成功后将该用户密码哈希统一为新格式（SHA256+bcrypt）
    for i, u in enumerate(users):
        if (u.get("username") or "").strip().lower() == username.lower():
            users[i] = {"username": u.get("username", "").strip(), "password_hash": _hash_password(password)}
            break
    data["users"] = users
    _save_settings(data)
    # 仅返回 token 到 body，由前端存 sessionStorage；不写 Cookie，关闭标签页即失效
    response = JSONResponse(content={"ok": True, "token": token, "must_change_password": must_change})
    response.delete_cookie(COOKIE_NAME, path="/")  # 清除可能存在的旧 Cookie，避免关标签后仍带 Cookie
    return response


@router.get("/me")
def me(request: Request):
    """
    从 Authorization 头或 Cookie 读取 JWT，返回当前用户名；未登录或无效返回 401。
    有效时刷新 JWT（滑动 30 分钟），新 token 放在响应 body 供前端更新 sessionStorage。
    """
    token = _get_token_from_request(request)
    if not token:
        return JSONResponse(status_code=401, content={"detail": "未登录"})
    username = _decode_token(token)
    if not username:
        return JSONResponse(status_code=401, content={"detail": "登录已过期或无效"})
    data = _load_settings()
    users = data.get("users") or []
    user = _find_user_by_username(users, username)
    admin_hash = (user.get("password_hash") or "").strip() if user else ""
    must_change_password = is_default_password(admin_hash)
    new_token = _create_token(username)
    return JSONResponse(content={
        "username": username,
        "must_change_password": must_change_password,
        "token": new_token,
    })


@router.post("/change-password")
def change_password(body: ChangePasswordBody, request: Request):
    """
    已登录用户修改密码：校验当前密码后更新该用户的 password_hash。
    修改后不再为默认密码，后续 /me 返回 must_change_password: false。
    新密码不能为 123456。
    """
    token = _get_token_from_request(request)
    if not token:
        return JSONResponse(status_code=401, content={"detail": "未登录"})
    username = _decode_token(token)
    if not username:
        return JSONResponse(status_code=401, content={"detail": "登录已过期或无效"})
    new_password = (body.new_password or "").strip()
    if not new_password:
        return JSONResponse(status_code=400, content={"detail": "新密码不能为空"})
    if new_password == DEFAULT_ADMIN_PASSWORD:
        return JSONResponse(
            status_code=400,
            content={"detail": "新密码不能为默认密码 123456，请设置其他密码"},
        )
    data = _load_settings()
    users = data.get("users") or []
    user = _find_user_by_username(users, username)
    if not user:
        return JSONResponse(status_code=403, content={"detail": "无权限"})
    admin_hash = (user.get("password_hash") or "").strip()
    if not verify_password(body.current_password or "", admin_hash):
        return JSONResponse(status_code=401, content={"detail": "当前密码错误"})
    for i, u in enumerate(users):
        if (u.get("username") or "").strip().lower() == (username or "").lower():
            users[i] = {"username": (u.get("username") or "").strip(), "password_hash": _hash_password(new_password)}
            break
    data["users"] = users
    _save_settings(data)
    return {"ok": True}


@router.post("/logout")
def logout(response: Response):
    """清除登录 Cookie。"""
    res = JSONResponse(content={"ok": True})
    res.delete_cookie(key=COOKIE_NAME, path="/")
    return res
