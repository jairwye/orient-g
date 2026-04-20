from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from backend.config import settings


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 本仓库当前以 SQLAlchemy Core + text SQL 为主，没有 ORM metadata 可用于 autogenerate。
target_metadata = None


def get_url() -> str:
    return str(getattr(settings, "database_url", "") or "")


def run_migrations_offline() -> None:
    url = get_url()
    if not url:
        raise RuntimeError("DATABASE_URL 未配置，无法运行迁移")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

