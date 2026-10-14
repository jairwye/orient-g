"""DATABASE_URL 归一化：path 斜杠 + PostgreSQL 驱动锁定。"""

from backend.database import _normalize_database_url


def test_normalize_strips_double_slash_in_path():
    assert (
        _normalize_database_url("postgresql://u:p@db:5432//mgmt_web")
        == "postgresql+psycopg2://u:p@db:5432/mgmt_web"
    )


def test_normalize_locks_psycopg2_for_bare_postgresql():
    assert (
        _normalize_database_url("postgresql://mgmt:changeme@db:5432/mgmt_web")
        == "postgresql+psycopg2://mgmt:changeme@db:5432/mgmt_web"
    )


def test_normalize_preserves_explicit_psycopg2():
    url = "postgresql+psycopg2://u:p@localhost:5432/db"
    assert _normalize_database_url(url) == url


def test_normalize_preserves_explicit_psycopg3():
    # 显式指定时不改写（便于日后切 v3）
    url = "postgresql+psycopg://u:p@localhost:5432/db"
    assert _normalize_database_url(url) == url
