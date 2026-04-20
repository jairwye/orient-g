"""
数据库连接与汇率表。与 config.database_url（PostgreSQL）一致，启动时建表。
"""
import json
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator
from urllib.parse import urlparse, urlunparse

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from backend.config import settings

logger = logging.getLogger(__name__)
Base = declarative_base()

def _migration_mode() -> str:
    return str(getattr(settings, "db_migration_mode", "legacy") or "legacy").strip().lower()

def _should_manage_schema() -> bool:
    # legacy: 启动时 CREATE/ALTER（现状）
    # alembic: schema 由 alembic 显式迁移管理，启动时不再隐式改 schema
    return _migration_mode() != "alembic"


def _normalize_database_url(url: str) -> str:
    """去掉 path 中多余斜杠，避免 localhost:5432//mgmt_web 导致连接失败。"""
    try:
        p = urlparse(url)
        path = p.path.replace("//", "/").strip() or "/"
        return urlunparse((p.scheme, p.netloc, path, p.params, p.query, p.fragment))
    except Exception:
        return url


engine = create_engine(
    _normalize_database_url(settings.database_url),
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_exchange_rates_table() -> None:
    """若 exchange_rates 表不存在则创建。"""
    if not _should_manage_schema():
        return
    sql = """
    CREATE TABLE IF NOT EXISTS exchange_rates (
        date DATE PRIMARY KEY,
        usd_rate REAL,
        eur_rate REAL,
        jpy_rate REAL,
        is_final INTEGER DEFAULT 0
    )
    """
    with engine.connect() as conn:
        conn.execute(text(sql))
        conn.commit()
    logger.info("exchange_rates table ready")


def init_kb_acl_tables() -> None:
    if not _should_manage_schema():
        return
    """
    初始化知识库 ACL（Project lead/member、private owner、resource->collection assignment）。

    该阶段实现 B(rel_only)：仅关系与分配落库；文档/表对象仍从 fixtures/对象层读取。
    """

    # 1) 创建表
    create_sql = [
        """
        CREATE TABLE IF NOT EXISTS kb_project_members (
            tenant_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            username TEXT NOT NULL,
            membership_role TEXT NOT NULL,
            PRIMARY KEY (tenant_id, project_id, username)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS kb_project_access_policy (
            tenant_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            allow_leads BOOLEAN NOT NULL,
            allow_members BOOLEAN NOT NULL,
            PRIMARY KEY (tenant_id, project_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS kb_department_access_policy (
            tenant_id TEXT NOT NULL,
            department_id TEXT NOT NULL,
            allow_leads BOOLEAN NOT NULL,
            allow_members BOOLEAN NOT NULL,
            PRIMARY KEY (tenant_id, department_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS kb_private_collection_owner (
            tenant_id TEXT NOT NULL,
            private_collection_id TEXT NOT NULL,
            owner_username TEXT NOT NULL,
            PRIMARY KEY (tenant_id, private_collection_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS kb_resource_collection_assignments (
            tenant_id TEXT NOT NULL,
            resource_type TEXT NOT NULL, -- 'doc' | 'table'
            resource_id TEXT NOT NULL,   -- doc_id | table_id
            collection_id TEXT NOT NULL, -- target collection_id
            PRIMARY KEY (tenant_id, resource_type, resource_id, collection_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS kb_resource_owner (
            tenant_id TEXT NOT NULL,
            resource_type TEXT NOT NULL, -- 'doc' | 'table'
            resource_id TEXT NOT NULL,
            owner_username TEXT NOT NULL,
            PRIMARY KEY (tenant_id, resource_type, resource_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS kb_user_collection_write_overrides (
            username TEXT NOT NULL,
            collection_id TEXT NOT NULL,
            effect TEXT NOT NULL, -- allow|deny
            PRIMARY KEY (username, collection_id, effect)
        )
        """,
    ]

    with engine.connect() as conn:
        for sql in create_sql:
            conn.execute(text(sql))
        conn.commit()

    # 2) 若为空则 seed（只 seed 默认值，后续由 /admin 编辑）
    fixture_path = Path(__file__).resolve().parent / "data" / "knowledge_acl_fixtures.json"
    if not fixture_path.exists():
        logger.info("kb_acl seed skipped: fixtures not found: %s", fixture_path)
        return

    try:
        seed_data = json.loads(fixture_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("kb_acl seed failed to load fixtures: %s", e)
        return

    tenant_id = seed_data.get("tenant_id") or "tenant1"
    # 如果 policy 表有数据，则认为已 seed
    with engine.connect() as conn:
        chk = conn.execute(
            text("SELECT COUNT(*) AS c FROM kb_project_access_policy WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        ).fetchone()
        count = int(chk[0] if chk else 0)
        if count > 0:
            logger.info("kb_acl tables already seeded (tenant_id=%s)", tenant_id)
            return

        projects = seed_data.get("projects") or []
        user_project_memberships = seed_data.get("user_project_memberships") or {}
        departments = seed_data.get("departments") or []

        # 默认 policy：先允许 leads/member（UI 可之后改）
        for p in projects:
            project_id = p.get("project_id")
            if not project_id:
                continue
            conn.execute(
                text(
                    """
                    INSERT INTO kb_project_access_policy (tenant_id, project_id, allow_leads, allow_members)
                    VALUES (:tid, :pid, :al, :am)
                    ON CONFLICT (tenant_id, project_id) DO NOTHING
                    """
                ),
                {"tid": tenant_id, "pid": project_id, "al": True, "am": True},
            )

        # 默认部门 policy：先允许 leads/member（UI 可之后改）
        for dep in departments:
            dep_id = str(dep or "").strip()
            if not dep_id:
                continue
            conn.execute(
                text(
                    """
                    INSERT INTO kb_department_access_policy (tenant_id, department_id, allow_leads, allow_members)
                    VALUES (:tid, :did, :al, :am)
                    ON CONFLICT (tenant_id, department_id) DO NOTHING
                    """
                ),
                {"tid": tenant_id, "did": dep_id, "al": True, "am": True},
            )

        # 默认成员关系：
        # - fixtures 没有显式 lead/member 字段，因此用规则：admin=lead，其它已加入=member
        for username, project_ids in user_project_memberships.items():
            if not isinstance(project_ids, list):
                continue
            for pid in project_ids:
                if not pid:
                    continue
                role = "lead" if str(username).strip().lower() == "admin" else "member"
                conn.execute(
                    text(
                        """
                        INSERT INTO kb_project_members (tenant_id, project_id, username, membership_role)
                        VALUES (:tid, :pid, :un, :role)
                        ON CONFLICT (tenant_id, project_id, username) DO UPDATE
                        SET membership_role = EXCLUDED.membership_role
                        """
                    ),
                    {"tid": tenant_id, "pid": pid, "un": username, "role": role},
                )

        # private owner
        for c in seed_data.get("collections") or []:
            if c.get("type") != "private":
                continue
            pcid = c.get("collection_id")
            owner = c.get("owner_user_id")
            if not pcid or not owner:
                continue
            conn.execute(
                text(
                    """
                    INSERT INTO kb_private_collection_owner (tenant_id, private_collection_id, owner_username)
                    VALUES (:tid, :pcid, :owner)
                    ON CONFLICT (tenant_id, private_collection_id) DO UPDATE
                    SET owner_username = EXCLUDED.owner_username
                    """
                ),
                {"tid": tenant_id, "pcid": pcid, "owner": owner},
            )

        # resource->collection assignment
        for d in seed_data.get("documents") or []:
            doc_id = d.get("doc_id")
            if not doc_id:
                continue
            for cid in d.get("collection_ids") or []:
                if not cid:
                    continue
                conn.execute(
                    text(
                        """
                        INSERT INTO kb_resource_collection_assignments
                            (tenant_id, resource_type, resource_id, collection_id)
                        VALUES (:tid, 'doc', :did, :cid)
                        ON CONFLICT (tenant_id, resource_type, resource_id, collection_id) DO NOTHING
                        """
                    ),
                    {"tid": tenant_id, "did": doc_id, "cid": cid},
                )

        for t in seed_data.get("tables") or []:
            table_id = t.get("table_id")
            cid = t.get("collection_id")
            if not table_id or not cid:
                continue
            conn.execute(
                text(
                    """
                    INSERT INTO kb_resource_collection_assignments
                        (tenant_id, resource_type, resource_id, collection_id)
                    VALUES (:tid, 'table', :tid2, :cid)
                    ON CONFLICT (tenant_id, resource_type, resource_id, collection_id) DO NOTHING
                    """
                ),
                {"tid": tenant_id, "tid2": table_id, "cid": cid},
            )

        conn.commit()
        logger.info("kb_acl seed completed (tenant_id=%s)", tenant_id)


def init_user_permission_tables() -> None:
    if not _should_manage_schema():
        return
    """
    全 PG 用户权限主数据（用户、部门、项目、负责人关系）初始化。
    若 PG 中用户为空，则从 app_settings.json + fixtures 做一次迁移导入。
    """
    create_sql = [
        """
        CREATE TABLE IF NOT EXISTS app_users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            roles_json TEXT NOT NULL DEFAULT '[]',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS departments (
            department_id TEXT PRIMARY KEY,
            name TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS projects (
            project_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            department_id TEXT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS user_department_roles (
            username TEXT NOT NULL,
            department_id TEXT NOT NULL,
            is_department_lead BOOLEAN NOT NULL DEFAULT FALSE,
            PRIMARY KEY (username, department_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS user_project_roles (
            username TEXT NOT NULL,
            project_id TEXT NOT NULL,
            is_project_lead BOOLEAN NOT NULL DEFAULT FALSE,
            PRIMARY KEY (username, project_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS kb_user_acl_overrides (
            username TEXT NOT NULL,
            resource_type TEXT NOT NULL, -- collection|doc|table
            resource_id TEXT NOT NULL,
            effect TEXT NOT NULL,        -- allow|deny
            PRIMARY KEY (username, resource_type, resource_id, effect)
        )
        """,
    ]
    with engine.connect() as conn:
        for sql in create_sql:
            conn.execute(text(sql))
        conn.commit()

    with engine.connect() as conn:
        settings_path = Path(settings.upload_dir).resolve() / "app_settings.json"
        settings_data: dict[str, Any] = {}
        try:
            if settings_path.exists():
                settings_data = json.loads(settings_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("init_user_permission_tables: read app_settings failed: %s", e)

        fixtures_path = Path(__file__).resolve().parent / "data" / "knowledge_acl_fixtures.json"
        fixtures_data: dict[str, Any] = {}
        try:
            if fixtures_path.exists():
                fixtures_data = json.loads(fixtures_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("init_user_permission_tables: read fixtures failed: %s", e)

        # 先确保维表存在（即使 users 已存在，也允许补齐 projects/departments 维表）
        # 部门
        for d in fixtures_data.get("departments") or []:
            dep = str(d or "").strip()
            if not dep:
                continue
            conn.execute(
                text(
                    """
                    INSERT INTO departments (department_id, name)
                    VALUES (:d, :n)
                    ON CONFLICT (department_id) DO NOTHING
                    """
                ),
                {"d": dep, "n": dep},
            )

        # 项目
        for p in fixtures_data.get("projects") or []:
            pid = str((p or {}).get("project_id") or "").strip()
            if not pid:
                continue
            conn.execute(
                text(
                    """
                    INSERT INTO projects (project_id, name, department_id)
                    VALUES (:pid, :name, :dep)
                    ON CONFLICT (project_id) DO UPDATE
                    SET name = EXCLUDED.name
                    """
                ),
                {"pid": pid, "name": str((p or {}).get("name") or pid), "dep": (p or {}).get("department_id")},
            )

        # 一次性迁移：PG users 为空时导入（用户主数据只迁一次，避免覆盖你在后台的修改）
        row = conn.execute(text("SELECT COUNT(*) FROM app_users")).fetchone()
        exists_count = int(row[0] if row else 0)
        if exists_count > 0:
            conn.commit()
            return

        # 部门
        for d in fixtures_data.get("departments") or []:
            dep = str(d or "").strip()
            if not dep:
                continue
            conn.execute(
                text(
                    """
                    INSERT INTO departments (department_id, name)
                    VALUES (:d, :n)
                    ON CONFLICT (department_id) DO NOTHING
                    """
                ),
                {"d": dep, "n": dep},
            )

        # 项目
        for p in fixtures_data.get("projects") or []:
            pid = str((p or {}).get("project_id") or "").strip()
            if not pid:
                continue
            conn.execute(
                text(
                    """
                    INSERT INTO projects (project_id, name, department_id)
                    VALUES (:pid, :name, :dep)
                    ON CONFLICT (project_id) DO UPDATE
                    SET name = EXCLUDED.name
                    """
                ),
                {"pid": pid, "name": str((p or {}).get("name") or pid), "dep": (p or {}).get("department_id")},
            )

        # 用户（主来源 app_settings）
        for u in settings_data.get("users") or []:
            username = str((u or {}).get("username") or "").strip()
            password_hash = str((u or {}).get("password_hash") or "").strip()
            if not username or not password_hash:
                continue
            roles = [str(x).strip() for x in ((u or {}).get("roles") or []) if str(x).strip()]
            conn.execute(
                text(
                    """
                    INSERT INTO app_users (username, password_hash, roles_json, is_active)
                    VALUES (:u, :ph, :roles, TRUE)
                    ON CONFLICT (username) DO NOTHING
                    """
                ),
                {"u": username, "ph": password_hash, "roles": json.dumps(roles, ensure_ascii=False)},
            )
            dep = str((u or {}).get("department") or "").strip()
            if dep:
                conn.execute(
                    text(
                        """
                        INSERT INTO user_department_roles (username, department_id, is_department_lead)
                        VALUES (:u, :d, FALSE)
                        ON CONFLICT (username, department_id) DO NOTHING
                        """
                    ),
                    {"u": username, "d": dep},
                )

        # 项目关系（fixtures 迁移：admin 默认 lead，其它默认 member）
        memberships = fixtures_data.get("user_project_memberships") or {}
        for username, project_ids in memberships.items():
            if not isinstance(project_ids, list):
                continue
            for pid in project_ids:
                p = str(pid or "").strip()
                if not p:
                    continue
                conn.execute(
                    text(
                        """
                        INSERT INTO user_project_roles (username, project_id, is_project_lead)
                        VALUES (:u, :pid, :lead)
                        ON CONFLICT (username, project_id) DO UPDATE
                        SET is_project_lead = EXCLUDED.is_project_lead
                        """
                    ),
                    {"u": str(username), "pid": p, "lead": str(username).strip().lower() == "admin"},
                )
        conn.commit()


def init_kb_documents_tables() -> None:
    if not _should_manage_schema():
        return
    """
    用户上传文档、RAG 包、知识库 kind 默认策略、多实体集合 scope、特殊文档 ACL。
    """
    create_sql = [
        """
        CREATE TABLE IF NOT EXISTS kb_folders (
            folder_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            name TEXT NOT NULL,
            kind TEXT,
            scope_json TEXT NOT NULL DEFAULT '{}',
            owner_username TEXT,
            created_by TEXT,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS kb_folder_collections (
            tenant_id TEXT NOT NULL,
            folder_id TEXT NOT NULL,
            collection_id TEXT NOT NULL,
            PRIMARY KEY (tenant_id, folder_id, collection_id)
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_kb_folder_collections_tenant_folder
        ON kb_folder_collections (tenant_id, folder_id)
        """,
        """
        CREATE TABLE IF NOT EXISTS kb_folder_resources (
            tenant_id TEXT NOT NULL,
            folder_id TEXT NOT NULL,
            resource_type TEXT NOT NULL, -- 'doc' | 'table'
            resource_id TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (tenant_id, folder_id, resource_type, resource_id)
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_kb_folder_resources_tenant_resource
        ON kb_folder_resources (tenant_id, resource_type, resource_id)
        """,
        """
        CREATE TABLE IF NOT EXISTS kb_user_documents (
            doc_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            owner_username TEXT NOT NULL,
            title TEXT NOT NULL,
            original_filename TEXT,
            storage_path TEXT NOT NULL,
            mime TEXT,
            size_bytes BIGINT,
            status TEXT NOT NULL DEFAULT 'uploaded',
            doc_version TEXT,
            source_hash TEXT,
            parser_version TEXT,
            manifest_json TEXT,
            last_error TEXT,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS kb_user_document_chunks (
            doc_id TEXT NOT NULL,
            chunk_id TEXT NOT NULL,
            chunk_seq_no INTEGER NOT NULL,
            chunk_text TEXT NOT NULL,
            PRIMARY KEY (doc_id, chunk_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS kb_document_shares (
            id SERIAL PRIMARY KEY,
            doc_id TEXT NOT NULL,
            shared_by TEXT NOT NULL,
            target_kind TEXT NOT NULL,
            target_json TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS kb_collection_scope (
            tenant_id TEXT NOT NULL,
            collection_id TEXT NOT NULL,
            scope_kind TEXT NOT NULL,
            scope_json TEXT NOT NULL,
            PRIMARY KEY (tenant_id, collection_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS kb_kind_default_read_policy (
            tenant_id TEXT NOT NULL,
            kb_kind TEXT NOT NULL,
            policy_json TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY (tenant_id, kb_kind)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS kb_special_doc_acl (
            tenant_id TEXT NOT NULL,
            resource_type TEXT NOT NULL DEFAULT 'doc',
            resource_id TEXT NOT NULL,
            acl_json TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY (tenant_id, resource_type, resource_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS kb_rag_packages (
            package_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            name TEXT NOT NULL,
            manifest_json TEXT,
            storage_path TEXT,
            owner_username TEXT,
            created_by_task_id TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS kb_table_instances (
            table_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            owner_username TEXT NOT NULL,
            name TEXT NOT NULL,
            source_type TEXT NOT NULL,            -- excel_session|generated|upload
            source_ref TEXT,                      -- session_id 或其它来源标识
            columns_json TEXT NOT NULL DEFAULT '[]',  -- [{column_id,name},...]
            row_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'active',    -- active|disabled|archived
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS kb_table_rows (
            id BIGSERIAL PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            table_id TEXT NOT NULL,
            row_key TEXT NOT NULL,               -- stable citation key (surrogate)
            row_json TEXT NOT NULL DEFAULT '{}', -- {"colA":"...",...}
            search_text TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_kb_table_rows_tenant_table ON kb_table_rows (tenant_id, table_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_kb_table_rows_search ON kb_table_rows (tenant_id, table_id, search_text)
        """,
        """
        CREATE TABLE IF NOT EXISTS kb_tasks (
            task_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            owner_username TEXT NOT NULL,
            kind TEXT NOT NULL,
            status TEXT NOT NULL,         -- queued|running|done|failed
            stage TEXT NOT NULL,          -- queued|parsing|packaging|done|failed
            progress INTEGER NOT NULL DEFAULT 0,
            detail TEXT,
            result_package_id TEXT,
            payload_json TEXT NOT NULL DEFAULT '{}',
            queue_priority INTEGER NOT NULL DEFAULT 1,
            attempts INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 3,
            worker_id TEXT,
            lease_until TIMESTAMP NULL,
            heartbeat_at TIMESTAMP NULL,
            started_at TIMESTAMP NULL,
            finished_at TIMESTAMP NULL,
            next_run_at TIMESTAMP NULL,
            last_error TEXT,
            dedupe_key TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS contract_ledger (
            contract_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            owner_username TEXT NOT NULL,
            doc_id TEXT NOT NULL,
            original_filename TEXT,
            storage_path TEXT,
            extracted_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_contract_ledger_tenant_created
        ON contract_ledger (tenant_id, created_at DESC)
        """,
    ]
    with engine.connect() as conn:
        for sql in create_sql:
            conn.execute(text(sql))
        conn.commit()

    # 轻量“迁移”：老表缺列时补齐（避免本地已有数据库无法启动）
    alter_sql = [
        "ALTER TABLE kb_folders ADD COLUMN IF NOT EXISTS kind TEXT",
        "ALTER TABLE kb_folders ADD COLUMN IF NOT EXISTS scope_json TEXT NOT NULL DEFAULT '{}'",
        "ALTER TABLE kb_folders ADD COLUMN IF NOT EXISTS owner_username TEXT",
        "ALTER TABLE kb_folders ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
        "ALTER TABLE kb_user_documents ADD COLUMN IF NOT EXISTS doc_version TEXT",
        "ALTER TABLE kb_user_documents ADD COLUMN IF NOT EXISTS source_hash TEXT",
        "ALTER TABLE kb_user_documents ADD COLUMN IF NOT EXISTS parser_version TEXT",
        "ALTER TABLE kb_user_documents ADD COLUMN IF NOT EXISTS manifest_json TEXT",
        "ALTER TABLE kb_user_documents ADD COLUMN IF NOT EXISTS last_error TEXT",
        "ALTER TABLE kb_user_documents ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
        "ALTER TABLE kb_rag_packages ADD COLUMN IF NOT EXISTS created_by_task_id TEXT",
        "ALTER TABLE kb_table_instances ADD COLUMN IF NOT EXISTS columns_json TEXT",
        "ALTER TABLE kb_table_instances ADD COLUMN IF NOT EXISTS row_count INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE kb_table_instances ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
        "ALTER TABLE kb_tasks ADD COLUMN IF NOT EXISTS payload_json TEXT NOT NULL DEFAULT '{}'",
        "ALTER TABLE kb_tasks ADD COLUMN IF NOT EXISTS queue_priority INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE kb_tasks ADD COLUMN IF NOT EXISTS attempts INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE kb_tasks ADD COLUMN IF NOT EXISTS max_attempts INTEGER NOT NULL DEFAULT 3",
        "ALTER TABLE kb_tasks ADD COLUMN IF NOT EXISTS worker_id TEXT",
        "ALTER TABLE kb_tasks ADD COLUMN IF NOT EXISTS lease_until TIMESTAMP NULL",
        "ALTER TABLE kb_tasks ADD COLUMN IF NOT EXISTS heartbeat_at TIMESTAMP NULL",
        "ALTER TABLE kb_tasks ADD COLUMN IF NOT EXISTS started_at TIMESTAMP NULL",
        "ALTER TABLE kb_tasks ADD COLUMN IF NOT EXISTS finished_at TIMESTAMP NULL",
        "ALTER TABLE kb_tasks ADD COLUMN IF NOT EXISTS next_run_at TIMESTAMP NULL",
        "ALTER TABLE kb_tasks ADD COLUMN IF NOT EXISTS last_error TEXT",
        "ALTER TABLE kb_tasks ADD COLUMN IF NOT EXISTS dedupe_key TEXT",
    ]
    with engine.connect() as conn:
        for sql in alter_sql:
            try:
                conn.execute(text(sql))
            except Exception:
                # 某些 PG 版本/权限下 IF NOT EXISTS 可能不生效；忽略以保证启动不中断
                pass
        conn.commit()

    # kb_tasks 新增列补齐后再建索引，避免旧库缺列时启动失败
    post_alter_index_sql = [
        """
        CREATE INDEX IF NOT EXISTS ix_kb_tasks_queue
        ON kb_tasks (status, queue_priority, next_run_at, created_at)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_kb_tasks_dedupe
        ON kb_tasks (tenant_id, dedupe_key)
        """,
    ]
    with engine.connect() as conn:
        for sql in post_alter_index_sql:
            conn.execute(text(sql))
        conn.commit()

    # 修正历史数据：Multi* 文档不应默认 allow_all（全员）
    # 仅对 kb_special_doc_acl 表中 doc 的 acl_json 含 allow_all=true 的记录做纠正
    # CompanyPublic 保持原行为（可通过 special_docs_get 默认 allow_all 展示）
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT tenant_id, resource_id, acl_json
                FROM kb_special_doc_acl
                WHERE resource_type='doc'
                """
            )
        ).fetchall()
        for r in rows:
            t = str(r[0] or "").strip()
            rid = str(r[1] or "").strip()
            raw = str(r[2] or "").strip()
            if not t or not rid:
                continue
            try:
                acl = json.loads(raw) if raw else {}
            except Exception:
                acl = {}
            if not isinstance(acl, dict):
                continue
            if acl.get("allow_all") is not True:
                continue
            # 若该 doc 触达 Multi* collection，则清掉 allow_all
            try:
                cols = conn.execute(
                    text(
                        """
                        SELECT collection_id
                        FROM kb_resource_collection_assignments
                        WHERE tenant_id=:t AND resource_type='doc' AND resource_id=:rid
                        """
                    ),
                    {"t": t, "rid": rid},
                ).fetchall()
                col_ids = {str(x[0] or "").strip() for x in cols if x and str(x[0] or "").strip()}
            except Exception:
                col_ids = set()
            if len(col_ids.intersection({"c_multi_dept_public_1", "c_multi_dept_lead_1", "c_multi_project_public_1", "c_multi_project_lead_1"})) == 0:
                continue
            acl.pop("allow_all", None)
            conn.execute(
                text(
                    """
                    UPDATE kb_special_doc_acl
                    SET acl_json = :j
                    WHERE tenant_id=:t AND resource_type='doc' AND resource_id=:rid
                    """
                ),
                {"t": t, "rid": rid, "j": json.dumps(acl, ensure_ascii=False)},
            )
        conn.commit()

    tenant_id = "tenant1"
    with engine.connect() as conn:
        chk = conn.execute(
            text("SELECT COUNT(*) AS c FROM kb_collection_scope WHERE tenant_id = :t"),
            {"t": tenant_id},
        ).fetchone()
        n = int(chk[0] if chk else 0)
        if n == 0:
            rows = [
                ("c_multi_dept_public_1", "MultiDeptPublic", '{"department_ids":["财务部","研发部"]}'),
                ("c_multi_dept_lead_1", "MultiDeptLead", '{"department_ids":["财务部","研发部"]}'),
                ("c_multi_project_public_1", "MultiProjectPublic", '{"project_ids":["proj1","proj2","proj3"]}'),
                ("c_multi_project_lead_1", "MultiProjectLead", '{"project_ids":["proj1","proj2","proj3"]}'),
            ]
            for cid, kind, sj in rows:
                conn.execute(
                    text(
                        """
                        INSERT INTO kb_collection_scope (tenant_id, collection_id, scope_kind, scope_json)
                        VALUES (:t, :c, :k, :j)
                        ON CONFLICT (tenant_id, collection_id) DO NOTHING
                        """
                    ),
                    {"t": tenant_id, "c": cid, "k": kind, "j": sj},
                )
            conn.commit()

    # 预置文件夹：合同管理（v1.2.2.e）
    # 说明：Folder 只是 collection 的分组；ACL 仍以 collection 为准。
    with engine.connect() as conn:
        conn.execute(
            text(
                """
                INSERT INTO kb_folders (folder_id, tenant_id, name, created_by)
                VALUES ('f_contracts', :t, '合同管理', 'system')
                ON CONFLICT (folder_id) DO UPDATE
                SET name = EXCLUDED.name
                """
            ),
            {"t": tenant_id},
        )
        # 将合同管理 folder 绑定到“合同管理”collection（fixtures 中定义）
        conn.execute(
            text(
                """
                INSERT INTO kb_folder_collections (tenant_id, folder_id, collection_id)
                VALUES (:t, 'f_contracts', 'c_contracts_public_1')
                ON CONFLICT (tenant_id, folder_id, collection_id) DO NOTHING
                """
            ),
            {"t": tenant_id},
        )
        conn.commit()

    kinds = [
        "Private",
        "DeptPublic",
        "DeptLead",
        "ProjectPublic",
        "ProjectLead",
        "MultiDeptPublic",
        "MultiDeptLead",
        "MultiProjectPublic",
        "MultiProjectLead",
        "CompanyPublic",
    ]
    with engine.connect() as conn:
        chk2 = conn.execute(
            text("SELECT COUNT(*) AS c FROM kb_kind_default_read_policy WHERE tenant_id = :t"),
            {"t": tenant_id},
        ).fetchone()
        # 默认可读模板：按 kb_kind 语义预置勾选（与前端勾选维度一致）
        defaults = {
            "Private": {"allow_owner": True},
            "DeptPublic": {"allow_dept_member": True},
            "DeptLead": {"allow_dept_lead": True},
            "ProjectPublic": {"allow_project_member": True},
            "ProjectLead": {"allow_project_lead": True},
            "MultiDeptPublic": {"allow_dept_member": True},
            "MultiDeptLead": {"allow_dept_lead": True},
            "MultiProjectPublic": {"allow_project_member": True},
            "MultiProjectLead": {"allow_project_lead": True},
            "CompanyPublic": {"allow_all": True},
        }

        # 1) 若表为空，先插入全部 kb_kind 行（带默认 policy）
        if int(chk2[0] if chk2 else 0) == 0:
            for k in kinds:
                conn.execute(
                    text(
                        """
                        INSERT INTO kb_kind_default_read_policy (tenant_id, kb_kind, policy_json)
                        VALUES (:t, :k, :j)
                        ON CONFLICT (tenant_id, kb_kind) DO NOTHING
                        """
                    ),
                    {"t": tenant_id, "k": k, "j": json.dumps(defaults.get(k, {}), ensure_ascii=False)},
                )
            conn.commit()

        # 2) 若已有记录但 policy_json 为空/{}，则补齐默认值（不覆盖已配置的非空策略）
        rows = conn.execute(
            text(
                """
                SELECT kb_kind, policy_json
                FROM kb_kind_default_read_policy
                WHERE tenant_id = :t
                """
            ),
            {"t": tenant_id},
        ).fetchall()
        for r in rows:
            kb_kind = str(r[0] or "").strip()
            raw = str(r[1] or "").strip()
            try:
                pol = json.loads(raw) if raw else {}
            except Exception:
                pol = {}
            if isinstance(pol, dict) and len(pol) == 0 and kb_kind in defaults:
                conn.execute(
                    text(
                        """
                        UPDATE kb_kind_default_read_policy
                        SET policy_json = :j
                        WHERE tenant_id = :t AND kb_kind = :k
                        """
                    ),
                    {"t": tenant_id, "k": kb_kind, "j": json.dumps(defaults[kb_kind], ensure_ascii=False)},
                )
        conn.commit()

    with engine.connect() as conn:
        rp = conn.execute(text("SELECT COUNT(*) FROM kb_rag_packages WHERE tenant_id=:t"), {"t": tenant_id}).fetchone()
        if int(rp[0] if rp else 0) == 0:
            conn.execute(
                text(
                    """
                    INSERT INTO kb_rag_packages (package_id, tenant_id, name, manifest_json, storage_path, owner_username)
                    VALUES ('rp_demo_1', :t, '示例大文档RAG包', :m, '', 'system')
                    """
                ),
                {"t": tenant_id, "m": '{"note":"docling 产物占位，后续接入流水线"}'},
            )
            conn.commit()


def init_kb_audit_tables() -> None:
    if not _should_manage_schema():
        return
    """
    知识库检索/回答审计事件（追加写）。

    约束：
    - 不存敏感明文（不写入 chunk_text、原始 query 明文等）
    - 仅存可追溯的 evidence id 列表/摘要
    """
    create_sql = [
        """
        CREATE TABLE IF NOT EXISTS kb_audit_events (
            id BIGSERIAL PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            username TEXT,
            event_type TEXT NOT NULL,
            query_sha256 TEXT,
            query_len INTEGER,
            meta_json TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_kb_audit_events_tenant_time
        ON kb_audit_events (tenant_id, created_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_kb_audit_events_tenant_user_time
        ON kb_audit_events (tenant_id, username, created_at DESC)
        """,
    ]
    with engine.connect() as conn:
        for sql in create_sql:
            conn.execute(text(sql))
        conn.commit()
    logger.info("kb_audit_events table ready")


def init_kb_vector_tables() -> None:
    if not _should_manage_schema():
        return
    """
    向量检索（pgvector）最小表结构。

    说明：
    - 向量为可再生数据：允许按 model/version 重建
    - 为兼容“默认 keyword-only”，此处对扩展/建表做容错，不阻塞启动
    """
    # 尝试启用 pgvector 扩展（无权限/未安装时不阻塞启动）
    with engine.connect() as conn:
        try:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
        except Exception:
            return

    dim = int(getattr(settings, "kb_embedding_dim", 1024) or 1024)
    if dim <= 0 or dim > 8192:
        dim = 1024

    create_sql = [
        f"""
        CREATE TABLE IF NOT EXISTS kb_doc_chunk_embeddings (
            tenant_id TEXT NOT NULL,
            doc_id TEXT NOT NULL,
            chunk_id TEXT NOT NULL,
            chunk_seq_no INTEGER NOT NULL,
            embedding vector({dim}) NOT NULL,
            embed_model TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (tenant_id, doc_id, chunk_id, embed_model)
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_kb_doc_chunk_embeddings_tenant_model
        ON kb_doc_chunk_embeddings (tenant_id, embed_model)
        """,
    ]
    with engine.connect() as conn:
        for sql in create_sql:
            conn.execute(text(sql))
        conn.commit()
    logger.info("kb_doc_chunk_embeddings table ready (dim=%s)", dim)


def init_equity_schema_patches() -> None:
    if not _should_manage_schema():
        return
    """
    股权表增量列。表不存在（尚未导入过 equity）时单条 ALTER 会失败，忽略即可。
    """
    patches = [
        "ALTER TABLE equity_entities ADD COLUMN IF NOT EXISTS reg_location TEXT",
    ]
    try:
        with engine.connect() as conn:
            for sql in patches:
                try:
                    conn.execute(text(sql))
                except Exception as e:
                    logger.debug("equity schema patch skipped: %s", e)
            conn.commit()
    except Exception as e:
        logger.debug("init_equity_schema_patches: %s", e)


def init_equity_tables() -> None:
    if not _should_manage_schema():
        return
    """
    初始化股权全景相关表（最小可运行结构）。

    说明：
    - 目前项目未使用 Alembic；因此采用“启动时 CREATE TABLE IF NOT EXISTS”的方式保证生产库可用。
    - 表结构应与 backend/routers/equity.py 中的 SQL 保持一致（必要列必须存在）。
    """
    create_sql = [
        """
        CREATE TABLE IF NOT EXISTS equity_snapshots (
            snapshot_name TEXT PRIMARY KEY,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS equity_entities (
            id TEXT PRIMARY KEY,
            snapshot_name TEXT NOT NULL,
            name TEXT NOT NULL,
            entity_type TEXT,
            credit_code TEXT,
            province TEXT,
            city TEXT,
            district TEXT,
            reg_location TEXT,
            industry TEXT,
            status TEXT,
            established_date TEXT,
            is_listed BOOLEAN,
            is_state_owned BOOLEAN,
            is_overseas BOOLEAN,
            source_url TEXT,
            raw_source_json TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_equity_entities_snapshot_name_name
        ON equity_entities (snapshot_name, name)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_equity_entities_snapshot_created_at
        ON equity_entities (snapshot_name, created_at DESC)
        """,
        """
        CREATE TABLE IF NOT EXISTS equity_targets (
            id TEXT PRIMARY KEY,
            snapshot_name TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            name TEXT NOT NULL,
            credit_code TEXT,
            alias TEXT,
            is_key BOOLEAN NOT NULL DEFAULT FALSE,
            notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_equity_targets_snapshot_entity
        ON equity_targets (snapshot_name, entity_id)
        """,
        """
        CREATE TABLE IF NOT EXISTS equity_edges (
            id TEXT PRIMARY KEY,
            snapshot_name TEXT NOT NULL,
            from_entity_id TEXT NOT NULL,
            to_entity_id TEXT NOT NULL,
            hold_pct DOUBLE PRECISION,
            hold_pct_text TEXT,
            source_platform TEXT,
            source_doc TEXT,
            collected_at TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_equity_edges_snapshot_from_to
        ON equity_edges (snapshot_name, from_entity_id, to_entity_id)
        """,
    ]

    with engine.connect() as conn:
        for sql in create_sql:
            conn.execute(text(sql))
        conn.commit()
    logger.info("equity tables ready")


@contextmanager
def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
