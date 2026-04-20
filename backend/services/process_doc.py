"""
自然语言 → 标准财务业务流程文档。
规则来自 backend/data/process_rules.json，可配置可更新；调用本地 Ollama 生成结构化输出后按模板渲染为 Markdown。
"""
import json
import logging
import re
from pathlib import Path
from typing import Optional

import httpx

from backend.config import settings
from backend.services.ollama_guard import post_json_with_guard
from backend.services.upstream_guard import assert_upstream_allowed

logger = logging.getLogger(__name__)

RULES_PATH = Path(__file__).resolve().parent.parent / "data" / "process_rules.json"
DEFAULT_MODEL = "qwen3:8b-q4_K_M"


def _load_rules() -> dict:
    if not RULES_PATH.exists():
        return {"schema_version": "1", "process_types": []}
    with open(RULES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_rules() -> dict:
    """供路由层读取完整规则（与 _load_rules 一致）。"""
    return _load_rules()


def save_rules(rules: dict) -> None:
    """将规则写回 process_rules.json。调用方需已校验结构。"""
    RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RULES_PATH, "w", encoding="utf-8") as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)


def _call_ollama(prompt: str, model: Optional[str] = None) -> str:
    """调用 Ollama /api/generate，返回完整响应文本。"""
    base = (settings.ollama_url or "").rstrip("/")
    if not base:
        raise ValueError("Ollama 未配置，请在 .env 中设置 OLLAMA_URL")
    assert_upstream_allowed(base, service_name="Ollama")
    url = f"{base}/api/generate"
    payload = {
        "model": model or getattr(settings, "ollama_model", None) or DEFAULT_MODEL,
        "prompt": prompt,
        "stream": False,
    }
    data = post_json_with_guard(url=url, payload=payload, timeout_s=60.0, kind="process_doc.generate")
    return (data.get("response") or "").strip()


def _extract_json(text: str) -> dict:
    """从模型输出中提取第一个完整 JSON 对象。"""
    text = text.strip()
    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 尝试提取 ```json ... ``` 或 { ... }
    for pattern in [r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", r"(\{[\s\S]*\})"]:
        m = re.search(pattern, text)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                continue
    raise ValueError("无法从模型输出中解析出有效 JSON")


def _structured_to_markdown(data: dict) -> str:
    """将结构化数据渲染为标准流程文档 Markdown。"""
    title = data.get("title") or "未命名流程"
    steps = data.get("steps") or []
    roles = data.get("roles") or []
    lines = [f"# {title}", ""]
    if roles:
        lines.append("## 责任角色")
        lines.extend([f"- {r}" for r in roles])
        lines.append("")
    lines.append("## 流程步骤")
    lines.append("")
    for s in steps if isinstance(steps, list) else []:
        if not isinstance(s, dict):
            continue
        step_no = s.get("step_no", "?")
        desc = s.get("desc") or "-"
        role = s.get("role") or "-"
        inp = s.get("input") or "-"
        out = s.get("output") or "-"
        deadline = s.get("deadline") or "-"
        lines.append(f"### 步骤 {step_no}")
        lines.append(f"- **描述**：{desc}")
        lines.append(f"- **责任角色**：{role}")
        lines.append(f"- **输入**：{inp}")
        lines.append(f"- **输出**：{out}")
        lines.append(f"- **时限**：{deadline}")
        lines.append("")
    return "\n".join(lines).strip()


SUGGEST_SYSTEM = """你是一个流程文档规则助手。用户会用自然语言描述「希望流程文档包含什么、长什么样」。
请根据用户的描述，输出一个 JSON 对象，且只输出这一份 JSON，不要其他文字。JSON 格式为：
{"prompt_instruction": "给 LLM 的完整提示词，用于把用户的自然语言转成流程文档。需明确要求输出 JSON，并写出期望的 JSON 结构说明。", "output_schema": {"title": "流程名称", "steps": [{"step_no": 1, "desc": "步骤描述", "role": "责任角色", "input": "输入", "output": "输出", "deadline": "时限"}], "roles": ["角色名"]}}
其中 output_schema 可选，若用户描述中涉及步骤结构则给出，否则可省略该键。"""


def suggest_prompt_from_natural_language(natural_language: str) -> dict:
    """
    根据用户自然语言描述，用 LLM 生成建议的 prompt_instruction 与可选的 output_schema。
    返回 {"prompt_instruction": str, "output_schema": dict | None}。
    """
    prompt = f"{SUGGEST_SYSTEM}\n\n用户的自然语言描述：\n{natural_language}"
    raw = _call_ollama(prompt)
    data = _extract_json(raw)
    prompt_instruction = (data.get("prompt_instruction") or "").strip()
    if not prompt_instruction:
        raise ValueError("模型未返回有效的 prompt_instruction")
    return {
        "prompt_instruction": prompt_instruction,
        "output_schema": data.get("output_schema") if isinstance(data.get("output_schema"), dict) else None,
    }


def generate_process_doc(natural_language: str, process_type_id: Optional[str] = None):
    """
    根据自然语言描述生成结构化流程数据与 Markdown 文档。
    返回 (structured_dict, markdown_string)。
    """
    rules = _load_rules()
    types_list = rules.get("process_types") or []
    process_type = None
    if process_type_id:
        for t in types_list:
            if t.get("id") == process_type_id:
                process_type = t
                break
    if not process_type and types_list:
        process_type = types_list[0]
    if not process_type:
        raise ValueError("未配置流程类型规则，请检查 backend/data/process_rules.json")

    instruction = process_type.get("prompt_instruction") or (
        "请将用户的自然语言描述转化为标准财务业务流程。"
        "输出 JSON：{\"title\": \"流程名称\", \"steps\": [{\"step_no\": 1, \"desc\": \"步骤描述\", \"role\": \"责任角色\", \"input\": \"输入\", \"output\": \"输出\", \"deadline\": \"时限\"}], \"roles\": [\"角色名\"]}。只输出 JSON。"
    )
    prompt = f"{instruction}\n\n用户描述：\n{natural_language}"

    raw = _call_ollama(prompt)
    structured = _extract_json(raw)
    markdown = _structured_to_markdown(structured)
    return structured, markdown
