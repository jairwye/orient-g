"""
飞书云文档同步：获取 tenant_access_token、创建文档并写入流程文档内容。
仅内网调用；需配置 FEISHU_APP_ID、FEISHU_APP_SECRET，并申请云文档相关权限。
"""
import logging
from typing import Optional

import httpx

from backend.config import settings

logger = logging.getLogger(__name__)

FEISHU_BASE = "https://open.feishu.cn/open-apis"
TOKEN_URL = f"{FEISHU_BASE}/auth/v3/tenant_access_token/internal"
DOCX_CREATE_URL = f"{FEISHU_BASE}/docx/v1/documents"
# 单次写入文本长度上限（飞书块内容不宜过长）
MAX_BODY_LENGTH = 8000


def _get_tenant_access_token() -> str:
    resp = httpx.post(
        TOKEN_URL,
        json={"app_id": settings.feishu_app_id, "app_secret": settings.feishu_app_secret},
        timeout=10.0,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise ValueError(data.get("msg", "获取飞书 token 失败"))
    return data["tenant_access_token"]


def _create_doc_with_content(token: str, title: str, body: str) -> dict:
    """创建一篇 docx 文档并写入标题与正文。返回含 document_id、url 的 dict。"""
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
    # 1. 创建文档（仅标题）
    create_payload = {"title": title or "流程文档"}
    if settings.feishu_doc_folder_token:
        create_payload["folder_token"] = settings.feishu_doc_folder_token
    create_resp = httpx.post(DOCX_CREATE_URL, headers=headers, json=create_payload, timeout=15.0)
    create_resp.raise_for_status()
    create_data = create_resp.json()
    if create_data.get("code") != 0:
        raise ValueError(create_data.get("msg", "创建飞书文档失败"))
    doc = create_data.get("data", {})
    document_id = doc.get("document_id")
    if not document_id:
        raise ValueError("飞书返回无 document_id")
    # 2. 向根块追加正文（文档创建后根块 id 即 document_id）
    body_trim = (body or "")[:MAX_BODY_LENGTH]
    if len(body or "") > MAX_BODY_LENGTH:
        body_trim += "\n\n（内容已截断）"
    children_payload = {
        "children": [
            {
                "block_type": "text",
                "text": {
                    "elements": [{"type": "textRun", "text_run": {"content": body_trim}}]
                },
            }
        ],
        "index": -1,
    }
    block_url = f"{FEISHU_BASE}/docx/v1/documents/{document_id}/blocks/{document_id}/children"
    block_resp = httpx.post(block_url, headers=headers, json=children_payload, timeout=15.0)
    if block_resp.status_code != 200 or block_resp.json().get("code") != 0:
        # 创建已成功，仅写入正文失败时记录但不抛错，仍返回文档链接
        logger.warning("飞书文档正文写入失败: %s", block_resp.text)
    # 3. 组装文档 URL（飞书 docx 在网页端打开格式）
    url = f"https://open.feishu.cn/document/d/{document_id}"
    return {"document_id": document_id, "url": url}


def sync_doc_to_feishu(title: str, markdown_body: str) -> dict:
    """
    将流程文档同步到飞书云文档。
    返回 {"url": "https://...", "document_id": "..."} 或抛错。
    """
    if not settings.feishu_configured:
        raise ValueError("飞书未配置，请设置 FEISHU_APP_ID、FEISHU_APP_SECRET")
    token = _get_tenant_access_token()
    return _create_doc_with_content(token, title or "标准财务流程文档", markdown_body)
