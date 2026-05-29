"""
将本地库 admin 密码重置为 123456（仅开发机使用）。
用法（项目根目录）：
  .\\.venv\\Scripts\\python.exe scripts\\reset_local_admin_password.py
  .\\.venv\\Scripts\\python.exe scripts\\reset_local_admin_password.py --password MyNewPass
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.routers.settings import DEFAULT_ADMIN_USERNAME, _hash_password
from backend.services.user_acl_store import list_users, set_user_password, upsert_user


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", default=DEFAULT_ADMIN_USERNAME)
    parser.add_argument("--password", default="123456")
    args = parser.parse_args()
    uname = (args.username or "").strip()
    pwd = args.password or "123456"
    ph = _hash_password(pwd)

    users = list_users()
    names = [u.get("username") for u in users]
    if uname not in names:
        upsert_user(uname, password_hash=ph, roles=["admin"], department="", is_active=True)
        print(f"[OK] 已创建用户 {uname}，密码已设为指定值")
    else:
        set_user_password(uname, ph)
        print(f"[OK] 已重置用户 {uname} 的密码")

    print("请用以下凭据登录后再 reindex：")
    print(f"  username: {uname}")
    print(f"  password: {pwd}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
