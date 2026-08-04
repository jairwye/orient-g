"""
Orient-G MCP Server（stdio）。

JWT 来源（优先级）：
  1. 工具参数 hermes_session_key（/agent → Hermes，与 system 上下文 orientg_hermes_session_key 一致）
  2. 环境变量 ORIENTG_USER_TOKEN（开发 Hermes CLI 单人调试）

  python -m backend.mcp.orientg_server
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from backend.services import orientg_mcp_tools as tools

mcp = FastMCP("orientg")


def _token(hermes_session_key: str | None = None) -> str:
    return tools.resolve_user_token("", hermes_session_key)


@mcp.tool()
def orientg_kb_ask(
    query: str,
    selected_collection_ids: list[str] | None = None,
    selected_table_ids: list[str] | None = None,
    attached_doc_ids: list[str] | None = None,
    hermes_session_key: str | None = None,
) -> dict:
    """竞品财报/知识库检索（Hermes 原生 v2 时含 agent_payload 成稿契约）。

    在 ACL 范围内检索并返回 reply、citations、证据节选；启用 HERMES_NATIVE_MCP_REPLY 时还返回
    agent_payload（orientg_kb_ask_v2：entities、metrics、output_contract）。
    hermes_session_key 必填，须与 system 上下文 orientg_hermes_session_key 一致。
    收到 evidence_sufficient=true 后应直接以中文写终稿，勿重复相同 query 或改用 terminal。
    """
    return tools.orientg_kb_ask(
        "",
        query,
        selected_collection_ids=selected_collection_ids,
        selected_table_ids=selected_table_ids,
        attached_doc_ids=attached_doc_ids,
        hermes_session_key=hermes_session_key,
    )


@mcp.tool()
def orientg_kb_list_docs(
    folder_id: str | None = None,
    limit: int = 50,
    hermes_session_key: str | None = None,
) -> dict:
    """列出当前用户可读文档（可选限定文件夹）。"""
    return tools.orientg_kb_list_docs("", folder_id=folder_id, limit=limit, hermes_session_key=hermes_session_key)


@mcp.tool()
def orientg_kb_upload(
    filename: str,
    content_base64: str,
    folder_id: str | None = None,
    hermes_session_key: str | None = None,
) -> dict:
    """上传文件到私人库并异步解析（需写权限）。"""
    return tools.orientg_kb_upload(
        "",
        filename=filename,
        content_base64=content_base64,
        folder_id=folder_id,
        hermes_session_key=hermes_session_key,
    )


@mcp.tool()
def orientg_kb_assign(
    doc_id: str,
    collection_ids: list[str],
    folder_id: str | None = None,
    hermes_session_key: str | None = None,
) -> dict:
    """将文档归属到 collection，可选绑定文件夹（需写权限）。"""
    return tools.orientg_kb_assign(
        "",
        doc_id=doc_id,
        collection_ids=collection_ids,
        folder_id=folder_id,
        hermes_session_key=hermes_session_key,
    )


@mcp.tool()
def orientg_kb_import_artifact(
    filename: str,
    content_base64: str,
    title: str | None = None,
    folder_id: str | None = None,
    hermes_session_key: str | None = None,
) -> dict:
    """将 Agent 生成的 md/xlsx 等产物写入知识库（需写权限）。"""
    return tools.orientg_kb_import_artifact(
        "",
        filename=filename,
        content_base64=content_base64,
        title=title,
        folder_id=folder_id,
        hermes_session_key=hermes_session_key,
    )


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
