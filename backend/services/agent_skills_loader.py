"""
从仓库内 backend/data/agent_skills/<skill_id>/SKILL.md 加载 Agent Skill 文档。

- 仅允许 manifest.json 登记的技能 ID，防止路径穿越。
- 供 GET /api/ai-interaction/skills 展示与对话 system 注入（按用户勾选的 enabled_skills）。
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

_MANIFEST_NAME = "manifest.json"
_SKILL_FILE = "SKILL.md"
# 与 docs/skills-guidelines 推荐一致：skill.<domain>.<name>.v<major>
_SKILL_ID_RE = re.compile(r"^skill\.[a-z0-9_.-]+\.v\d+$", re.IGNORECASE)


def _skills_root() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "agent_skills"


@lru_cache(maxsize=1)
def _manifest_ids() -> frozenset[str]:
    root = _skills_root()
    p = root / _MANIFEST_NAME
    if not p.exists():
        return frozenset()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return frozenset()
    items = data.get("skills") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return frozenset()
    out: list[str] = []
    for it in items:
        if isinstance(it, dict) and isinstance(it.get("id"), str):
            sid = it["id"].strip()
            if sid and _SKILL_ID_RE.match(sid):
                out.append(sid)
    return frozenset(out)


def registered_skill_ids() -> list[str]:
    return sorted(_manifest_ids())


def _parse_frontmatter(raw: str) -> tuple[dict[str, str], str]:
    text = raw.lstrip("\ufeff")
    if not text.startswith("---"):
        return {}, text.strip()
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text.strip()
    header = parts[1].strip()
    body = parts[2].lstrip("\n").strip()
    meta: dict[str, str] = {}
    for line in header.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        key = k.strip()
        val = v.strip().strip('"').strip("'")
        if key:
            meta[key] = val
    return meta, body


def _skill_path(skill_id: str) -> Path | None:
    sid = (skill_id or "").strip()
    if not sid or sid not in _manifest_ids():
        return None
    p = _skills_root() / sid / _SKILL_FILE
    try:
        p.resolve().relative_to(_skills_root().resolve())
    except ValueError:
        return None
    return p if p.is_file() else None


def load_skill_document(skill_id: str) -> dict[str, Any] | None:
    """
    返回 { id, name, description, body_markdown, raw_markdown }；未知或未登记返回 None。
    """
    sid = (skill_id or "").strip()
    path = _skill_path(sid)
    if not path:
        return None
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    meta, body = _parse_frontmatter(raw)
    return {
        "id": sid,
        "name": meta.get("name") or sid,
        "description": meta.get("description") or "",
        "body_markdown": body,
        "raw_markdown": raw.strip(),
    }


def list_skill_documents() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for sid in registered_skill_ids():
        doc = load_skill_document(sid)
        if doc:
            out.append(
                {
                    "id": doc["id"],
                    "name": doc["name"],
                    "description": doc["description"],
                    "body_markdown": doc["body_markdown"],
                    "raw_markdown": doc["raw_markdown"],
                }
            )
    return out


def build_system_addon_for_enabled_skills(
    enabled_skill_ids: list[str] | None,
    *,
    max_total_chars: int = 16000,
    header: str = "## 已启用的技能文档（须严格遵守）\n",
) -> str:
    """
    将用户勾选且 manifest 登记的技能正文拼入 system（用于 Ollama 多轮 / 纯对话）。
    """
    ids = [str(x).strip() for x in (enabled_skill_ids or []) if str(x).strip()]
    if not ids:
        return ""
    chunks: list[str] = []
    for sid in ids:
        if sid not in _manifest_ids():
            continue
        doc = load_skill_document(sid)
        if not doc:
            continue
        body = (doc.get("body_markdown") or "").strip()
        if not body:
            continue
        title = doc.get("name") or sid
        chunks.append(f"### {title} (`{sid}`)\n{body}")
    if not chunks:
        return ""
    text = header + "\n\n".join(chunks)
    if len(text) > max_total_chars:
        text = text[: max_total_chars - 20] + "\n…（技能文档已截断）"
    return text.strip()


def clear_manifest_cache() -> None:
    """单测用：重载 manifest。"""
    _manifest_ids.cache_clear()
