"""Orient-G Agent 呈现策略：语言、Markdown 排版、产品范围（始终经 Hermes 网关）。"""

from __future__ import annotations

import re
from typing import Any

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def infer_reply_language(user_query: str) -> str:
    """用户问句含汉字则视为中文，否则英文。"""
    q = (user_query or "").strip()
    if _CJK_RE.search(q):
        return "zh"
    return "en"


def kb_scope_nonempty(kb_scope: dict[str, Any] | None) -> bool:
    scope = kb_scope or {}
    for key in ("selected_collection_ids", "selected_table_ids", "selected_folder_ids"):
        if any(str(x).strip() for x in (scope.get(key) or [])):
            return True
    return False


def orientg_answer_format_requirement() -> str:
    return (
        "终稿须 Markdown 排版：节标题用 ## 或 ###；无序列表每项单独一行以「- 」开头；"
        "标题与列表、节与节之间空一行；禁止把多节内容挤成一段无换行文字。"
    )


def orientg_agent_presentation_context(
    *,
    user_query: str,
    kb_scope: dict[str, Any] | None,
    enabled_skills: list[str] | None = None,
) -> dict[str, Any]:
    lang = infer_reply_language(user_query)
    has_kb = kb_scope_nonempty(kb_scope)
    skills = [str(s).strip() for s in (enabled_skills or []) if str(s).strip()]

    ctx: dict[str, Any] = {
        "orientg_product": "Orient-G 内网智能体",
        "orientg_reply_language": "zh-CN" if lang == "zh" else "en",
        "orientg_reply_language_rule": (
            "与用户最新问句使用相同语言作答；中文问句须全文使用简体中文。"
            if lang == "zh"
            else "Reply in the same language as the user's latest message."
        ),
        "orientg_answer_format": orientg_answer_format_requirement(),
        "orientg_agent_channel": "hermes",
    }

    if not has_kb:
        ctx["orientg_kb_scope_empty"] = True
        ctx["orientg_general_agent_mode"] = True
        intro = (
            "当前未选择知识库：可介绍 Orient-G Agent 在本环境的能力边界——"
            "知识库问答/证据分析需用户先在界面选择库或文件夹；"
            "已注册 MCP 工具 orientg_kb_*；用户已勾选的 agent_skills。"
            "勿复述 Hermes 通用英文能力清单，勿强调智能家居、Spotify、"
            "YouTube 等与 Orient-G 内网产品无关的能力。"
        )
        if skills:
            ctx["orientg_enabled_skills"] = skills[:20]
            intro += f" 当前已勾选技能：{', '.join(skills[:8])}。"
        ctx["orientg_product_intro_scope"] = intro
    else:
        ctx["orientg_kb_scope_empty"] = False

    return ctx


def normalize_markdown_bullet_lines(text: str) -> str:
    """行首 `-foo` → `- foo`，供 Markdown 列表解析。"""
    out: list[str] = []
    for line in (text or "").split("\n"):
        m = re.match(r"^(\s*)-(?!\s)(.+)$", line)
        if m:
            out.append(f"{m.group(1)}- {m.group(2).strip()}")
        else:
            out.append(line)
    return "\n".join(out)


def fix_glued_markdown_lists(text: str) -> str:
    """修复 Hermes 常输出的「**标题**-项1-项2」粘连列表。"""
    t = (text or "").strip()
    if not t:
        return ""
    t = re.sub(r"(\*\*[^*]+\*\*)\s*-", r"\1\n\n-", t)
    t = re.sub(r"([）\)\]」』。.!?；;])\s*-", r"\1\n\n-", t)
    t = re.sub(r"(\*\*[^*]+\*\*)\s*([📝💻📊🗂️🌐])", r"\1\n\n\2", t)
    prev = None
    while prev != t:
        prev = t
        t = re.sub(r"(-[^\n-]{4,}?)-(?=[^\n-])", r"\1\n-", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return normalize_markdown_bullet_lines(t.strip())


def orientg_tool_policy_for_route(
    *,
    orientg_route: str | None,
    kb_scope: dict[str, Any] | None,
    allow_kb_write: bool,
) -> dict[str, Any]:
    """Hermes 路由工具策略：无 KB 时不注入 KB MCP 约束。"""
    route = (orientg_route or "").strip().lower()
    if route not in ("hermes_lite", "hermes_full"):
        return {}
    from backend.services.hermes_orientg_policy import KB_FORBIDDEN_TOOL_NAMES

    if not kb_scope_nonempty(kb_scope):
        return {
            "orientg_tool_policy": (
                "当前未选择知识库：直接回答用户问题，勿调用 orientg_kb_* MCP；"
                "禁止 terminal/shell；能力介绍见 orientg_product_intro_scope。"
            ),
            "orientg_forbidden_tools": list(KB_FORBIDDEN_TOOL_NAMES),
            "orientg_allowed_kb_tools": [],
            "orientg_kb_write": False,
        }
    policy: dict[str, Any] = {
        "orientg_tool_policy": (
            "知识库类任务：仅通过 orientg_kb_* MCP 获取与引用证据；"
            "禁止用 terminal/shell/curl 探测 API 或读取本地路径；禁止编造文件内容充当 KB 答案。"
        ),
        "orientg_forbidden_tools": list(KB_FORBIDDEN_TOOL_NAMES),
        "orientg_allowed_kb_tools": ["orientg_kb_ask", "orientg_kb_list", "orientg_kb_import_artifact"],
    }
    if not allow_kb_write:
        policy["orientg_kb_write"] = False
        policy["orientg_allowed_kb_tools"] = ["orientg_kb_ask", "orientg_kb_list"]
    return policy
