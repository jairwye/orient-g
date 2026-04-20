from __future__ import annotations

from typing import Any

from backend.services.kb_tables import create_table_instance_from_rows


SKILL_ID = "skill.project_accounting_table.v1"


def _safe(s: str) -> str:
    return (s or "").strip()


def run(
    tenant_id: str,
    owner_username: str,
    *,
    project_key: str,
    period: str | None = None,
    fixtures: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    v1 最小实现：从 fixtures 的项目利润表示例抽取基础指标，生成一个可引用的 TableInstance。
    后续可扩展为：从已入库表/经营数据等来源生成更完整核算表。
    """
    pk = _safe(project_key) or "项目"
    per = _safe(period or "")
    fx = fixtures or {}
    # 找一个示例表作为基础（优先 t_project_profit_1）
    base = None
    for t in fx.get("tables") or []:
        if str(t.get("table_id") or "") == "t_project_profit_1":
            base = t
            break
    if base is None:
        for t in fx.get("tables") or []:
            if "核算" in str(t.get("name") or "") or "利润" in str(t.get("name") or ""):
                base = t
                break
    columns = ["项目", "期间", "指标", "数值"]
    rows: list[list[Any]] = []
    if isinstance(base, dict):
        for r in base.get("rows") or []:
            vals = r.get("values") or {}
            metric = vals.get("col_metric") or vals.get("指标") or vals.get("metric") or ""
            amount = vals.get("col_amount") or vals.get("数值") or vals.get("amount") or ""
            rows.append([pk, per, metric, amount])
    if not rows:
        rows = [[pk, per, "本年累计净利润", 0]]
    name = f"项目核算表（{pk}{(' ' + per) if per else ''}）"
    info = create_table_instance_from_rows(
        tenant_id,
        owner_username,
        name=name,
        source_type="generated",
        source_ref=SKILL_ID,
        headers=columns,
        rows=rows,
        assign_to_private=True,
    )
    first_row_key = info.get("first_row_key")
    first_values = info.get("first_values") or {}
    # pick a representative column for citation
    chosen_col = None
    for k, v in first_values.items():
        if isinstance(v, (int, float)):
            chosen_col = str(k)
            break
    if chosen_col is None:
        for k in first_values.keys():
            chosen_col = str(k)
            break
    return {
        "ok": True,
        "table_id": info.get("table_id"),
        "row_count": info.get("row_count"),
        "collection_id": info.get("private_collection_id"),
        "summary": f"已生成项目核算表：{name}。",
        "citations": [
            {
                "evidence_type": "table_row",
                "table_id": info.get("table_id"),
                "collection_id": info.get("private_collection_id"),
                "row_key": first_row_key,
                "column_id": chosen_col,
            }
        ],
    }

