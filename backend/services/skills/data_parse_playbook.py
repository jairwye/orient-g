"""
数据解析 Playbook 技能（skill.data_parse.playbook.v1）

正文以 `backend/data/agent_skills/skill.data_parse.playbook.v1/SKILL.md` 为准；
本函数保留为兼容入口（单测或其它模块若仍 import，可读到与 SKILL.md 一致的内容）。
"""


def playbook_system_fragment() -> str:
    from backend.services.agent_skills_loader import load_skill_document

    doc = load_skill_document("skill.data_parse.playbook.v1")
    body = (doc or {}).get("body_markdown") if doc else None
    if isinstance(body, str) and body.strip():
        return body.strip()
    return (
        "## Playbook（口径包，只读）\n"
        "- 所有数值与结论必须来自工具返回的聚合指标或表结构摘要；禁止编造未在数据中出现的金额、占比或期间。\n"
        "- 遇缺失数据、校验异常、混合类型列时须在结论与 risks 中显式说明，不得用猜测补全。\n"
        "- 若输出结构化 JSON，字段须与业务约定的 output_shape（conclusion / risks / suggestions 等）一致。\n"
        "- 术语与指标口径优先遵循本对话中「用户勾选的提示词资产」摘要；冲突时以工具返回为准。\n"
    ).strip()
