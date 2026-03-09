"""
诊断 PostgreSQL 连接：打印 DATABASE_URL（隐藏密码）、端口是否通、以及用 127.0.0.1 重试。
在项目根目录、激活 .venv 后执行: python scripts/check_db_connect.py
"""
import socket
import sys
from urllib.parse import urlparse

sys.path.insert(0, ".")


def check_port(host: str, port: int) -> bool:
    """尝试 TCP 连接，返回是否有人监听。"""
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError as e:
        print(f"  端口 {host}:{port} -> {e}")
        return False


def main():
    from backend.config import settings
    import psycopg2

    url = settings.database_url
    p = urlparse(url)
    host = p.hostname or "localhost"
    port = p.port or 5432
    safe = f"{p.scheme}://***:***@{host}:{port}{p.path}"
    print("DATABASE_URL (密码已隐藏):", safe)
    print()

    # 1. 端口是否通
    print("1. 端口是否可连：")
    print(f"   {host}:{port} ", end="")
    if check_port(host, port):
        print("-> 有进程在监听")
    else:
        print("-> 无监听或连接被拒（请确认 PostgreSQL 已启动且监听 5432）")
    if host == "localhost":
        print("   127.0.0.1:5432 ", end="")
        if check_port("127.0.0.1", port):
            print("-> 有进程在监听（建议 .env 里把 localhost 改成 127.0.0.1 再试）")
        else:
            print("-> 无监听")
    print()

    # 2. 用当前 URL 连
    print("2. psycopg2 用当前 URL 连接：")
    try:
        psycopg2.connect(url)
        print("   连接成功")
        return
    except Exception as e:
        print("   失败:", type(e).__name__, getattr(e, "args", ()))
    print()

    # 3. 若当前是 localhost，改用 127.0.0.1 的 URL 再试
    if host == "localhost":
        url2 = url.replace("localhost", "127.0.0.1", 1)
        print("3. 改用 127.0.0.1 再连：")
        try:
            psycopg2.connect(url2)
            print("   连接成功 -> 请把 .env 里 DATABASE_URL 的 localhost 改成 127.0.0.1 后重启后端")
            return
        except Exception as e:
            print("   仍失败:", type(e).__name__, getattr(e, "args", ()))
    print()

    # 4. 用显式参数连接（避免 URL 里密码特殊字符等问题），并尝试关闭 SSL
    print("4. 用显式参数 + sslmode=disable 再连：")
    try:
        dbname = (p.path or "").lstrip("/") or "mgmt_web"
        user = p.username or ""
        password = p.password or ""
        conn = psycopg2.connect(
            host="127.0.0.1",
            port=port,
            dbname=dbname,
            user=user,
            password=password,
            connect_timeout=5,
            options="-c statement_timeout=3000",
        )
        conn.close()
        print("   连接成功 -> 建议在 .env 的 DATABASE_URL 末尾加上 ?sslmode=disable 再启动后端")
        return
    except Exception as e:
        err = getattr(e, "args", ())
        pgerror = getattr(e, "pgerror", None)
        print("   失败:", type(e).__name__, err if err else "(无文案)")
        if pgerror:
            print("   pgerror:", pgerror)
    print()

    # 5. 仅用 URL 加 sslmode=disable 再试
    sep = "&" if "?" in url else "?"
    url_ssl = f"{url}{sep}sslmode=disable"
    print("5. 当前 URL 加 ?sslmode=disable 再连：")
    try:
        psycopg2.connect(url_ssl)
        print("   连接成功 -> 请在 .env 的 DATABASE_URL 末尾加上 ?sslmode=disable 后重启后端")
        return
    except Exception as e:
        err = getattr(e, "args", ())
        print("   仍失败:", type(e).__name__, err if err else "(无文案)")
    print()
    print("请检查：.env 中用户名/密码/数据库名是否正确、数据库 mgmt_web 是否已创建；或用 psql -h 127.0.0.1 -U 用户名 -d mgmt_web 测试登录。")


if __name__ == "__main__":
    main()
