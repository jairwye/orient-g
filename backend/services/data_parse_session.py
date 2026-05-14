"""
数据解析 Session 存储：以 session_id 保存解析结果（通用表格 tables、表结构 table_schemas、按需生成的看板配置）。
内存 dict + 本地文件落盘（跨进程兜底），符合 规则/规则.md 内网与数据不外传要求。
"""
import json
import logging
import threading
import time
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# key=session_id, value={ tables, table_schemas, column_profiles, aggregations, auto_dashboards, kanban_config, created_at, chat_history }
_sessions: dict[str, dict[str, Any]] = {}
_sessions_lock = threading.Lock()
MAX_SESSIONS = 50
_SESSIONS_DIR = Path(__file__).resolve().parent.parent / "data" / ".data_parse_sessions"
_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


def _session_file(session_id: str) -> Path:
    return _SESSIONS_DIR / f"{session_id}.json"


def _persist_session(session_id: str, data: dict[str, Any]) -> None:
    try:
        p = _session_file(session_id)
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.warning("persist data_parse session failed: %s", e)


def _load_session_from_disk(session_id: str) -> dict[str, Any] | None:
    p = _session_file(session_id)
    if not p.exists():
        return None
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else None
    except Exception as e:
        logger.warning("load data_parse session failed: %s", e)
        return None


def _prune_session_files(max_files: int = MAX_SESSIONS * 2) -> None:
    try:
        files = sorted(_SESSIONS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
    except Exception:
        return
    for f in files[max_files:]:
        try:
            f.unlink(missing_ok=True)
        except Exception:
            pass


def create_session(pipeline_result: dict[str, Any], owner_username: str | None = None) -> str:
    """创建 session，返回 session_id。"""
    session_id = str(uuid.uuid4())
    session = {
        "tables": pipeline_result.get("tables") or {},
        "table_schemas": pipeline_result.get("table_schemas") or [],
        "column_profiles": pipeline_result.get("column_profiles") or {},
        "aggregations": pipeline_result.get("aggregations") or {},
        "auto_dashboards": pipeline_result.get("auto_dashboards") or [],
        "kanban_config": pipeline_result.get("kanban_config") or [],
        "validation_summary": pipeline_result.get("validation_summary") or {},
        "created_at": time.time(),
        "chat_history": [],
        "owner_username": (owner_username or "").strip() or None,
    }
    with _sessions_lock:
        _sessions[session_id] = session
        while len(_sessions) > MAX_SESSIONS:
            oldest_id = min(_sessions.keys(), key=lambda k: _sessions[k]["created_at"])
            del _sessions[oldest_id]
    _persist_session(session_id, session)
    _prune_session_files()
    return session_id


def get_session(session_id: str) -> dict[str, Any] | None:
    """获取 session 内容，不存在返回 None。"""
    with _sessions_lock:
        s = _sessions.get(session_id)
    if s is not None:
        return s
    # 跨进程兜底：当前进程没有命中时从本地落盘读取并回填内存
    loaded = _load_session_from_disk(session_id)
    if loaded is not None:
        with _sessions_lock:
            _sessions[session_id] = loaded
        return loaded
    return None


def set_session_owner(session_id: str, owner_username: str) -> bool:
    """为会话补写 owner（仅当 owner 为空时认领，避免并发覆盖）。"""
    owner = (owner_username or "").strip()
    if not owner:
        return False
    with _sessions_lock:
        s = _sessions.get(session_id)
        if s is None:
            loaded = _load_session_from_disk(session_id)
            if loaded is None:
                return False
            _sessions[session_id] = loaded
            s = loaded
        current = (s.get("owner_username") or "").strip()
        if current:
            return current == owner
        s["owner_username"] = owner
        _sessions[session_id] = s
    _persist_session(session_id, s)
    return True


def get_tables(session_id: str) -> dict[str, dict[str, Any]] | None:
    """返回该 session 的 tables（sheet_name -> { headers, rows }），供 generate_chart/generate_table 使用。"""
    s = get_session(session_id)
    return (s.get("tables") or {}) if s else None


def get_table_schemas(session_id: str) -> list[dict[str, Any]] | None:
    """返回该 session 的 table_schemas（供 read_metrics，不包含原始行）。"""
    s = get_session(session_id)
    return (s.get("table_schemas") or []) if s else None


def get_column_profiles(session_id: str) -> dict[str, list[dict[str, Any]]] | None:
    """返回该 session 的 column_profiles。"""
    s = get_session(session_id)
    return (s.get("column_profiles") or {}) if s else None


def get_aggregations(session_id: str) -> dict[str, dict[str, Any]] | None:
    """返回该 session 的 aggregations。"""
    s = get_session(session_id)
    return (s.get("aggregations") or {}) if s else None


def get_kanban_config(session_id: str) -> list | None:
    """返回该 session 的 kanban_config（按需生成的图表列表）。"""
    s = get_session(session_id)
    return s.get("kanban_config") if s else None


def append_kanban_chart(session_id: str, chart: dict[str, Any]) -> None:
    """对话中按需生图时追加到 kanban_config。"""
    s = get_session(session_id)
    if s is not None:
        config = s.get("kanban_config") or []
        config.append(chart)
        s["kanban_config"] = config
        _persist_session(session_id, s)


def get_chat_history(session_id: str) -> list[dict[str, str]]:
    """返回该 session 的对话历史（供 chat 多轮）。"""
    s = get_session(session_id)
    return (s.get("chat_history") or []) if s else []


def append_chat_history(session_id: str, role: str, content: str) -> None:
    """追加一条对话。"""
    s = get_session(session_id)
    if s is not None:
        hist = s.get("chat_history") or []
        hist.append({"role": role, "content": content})
        s["chat_history"] = hist
        _persist_session(session_id, s)


def get_validation_summary(session_id: str) -> dict | None:
    """返回该 session 的轻量数据质量摘要（validation_summary）。"""
    s = get_session(session_id)
    return (s.get("validation_summary") or {}) if s else None


# 兼容旧接口：read_metrics 用 table_schemas，并扩展返回 column_profiles / aggregations / validation_summary
def get_metrics(session_id: str) -> dict | None:
    """返回结构化摘要供 read_metrics 使用：table_schemas + column_profiles + aggregations + validation_summary。"""
    schemas = get_table_schemas(session_id)
    if schemas is None:
        return None
    profiles = get_column_profiles(session_id) or {}
    aggs = get_aggregations(session_id) or {}
    val = get_validation_summary(session_id) or {}
    return {
        "table_schemas": schemas,
        "column_profiles": profiles,
        "aggregations": aggs,
        "validation_summary": val,
    }


def get_table_views(session_id: str) -> dict | None:
    """兼容：返回 tables 的简化视图（仅结构），供需要时使用。"""
    tables = get_tables(session_id)
    if not tables:
        return None
    return {name: {"headers": t.get("headers", []), "row_count": len(t.get("rows") or [])} for name, t in tables.items()}
