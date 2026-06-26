"""纵向对比：7×PDF zip → Docling → vertical.snapshot.json。"""
from __future__ import annotations

import json
import shutil
import threading
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.config import settings
from backend.services.competitor_report_store import competitor_dir
from backend.services.docling_runner import convert_to_md_and_json
from backend.services.vertical_company_resolve import order_pdf_entries
from backend.services.vertical_docling_adapter import (
    build_vertical_snapshot,
    company_from_docling,
    merged_markdown_from_companies,
)
from backend.services.vertical_pdf_store import persist_vertical_pdfs
from backend.services.vertical_report_store import save_vertical_snapshot

INGEST_DIRNAME = "vertical/ingest"
MAX_ZIP_BYTES = 120 * 1024 * 1024


def decode_zip_entry_filename(filename: str, *, flag_bits: int = 0) -> str:
    """Windows 资源管理器 zip 常把中文文件名按 GBK 写入；Python 按 cp437 读出乱码时需还原。"""
    name = Path(filename).name
    if any("\u4e00" <= c <= "\u9fff" for c in name):
        return name
    for encoding in ("gbk", "gb18030"):
        try:
            decoded = name.encode("cp437").decode(encoding)
            if any("\u4e00" <= c <= "\u9fff" for c in decoded):
                return decoded
        except UnicodeError:
            continue
    return name

_jobs_lock = threading.Lock()
_running_jobs: set[str] = set()


def ingest_root() -> Path:
    return competitor_dir() / "vertical" / "ingest"


def _job_dir(job_id: str) -> Path:
    return ingest_root() / job_id


def _write_job_status(job_id: str, payload: dict[str, Any]) -> None:
    d = _job_dir(job_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "status.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def get_ingest_job(job_id: str) -> dict[str, Any] | None:
    path = _job_dir(job_id) / "status.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_pdfs_from_zip(zip_bytes: bytes, dest: Path) -> list[tuple[str, Path]]:
    dest.mkdir(parents=True, exist_ok=True)
    zip_path = dest / "upload.zip"
    zip_path.write_bytes(zip_bytes)
    entries: list[tuple[str, Path]] = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            raw_name = Path(info.filename).name
            if not raw_name.lower().endswith(".pdf"):
                continue
            name = decode_zip_entry_filename(raw_name, flag_bits=info.flag_bits)
            if info.file_size > 40 * 1024 * 1024:
                raise ValueError(f"PDF 过大：{name}")
            out = dest / "pdfs" / name
            out.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, out.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            entries.append((name, out))
    if not entries:
        raise ValueError("zip 内未找到 .pdf 文件")
    return entries


def run_vertical_ingest_job(job_id: str, *, uploaded_by: str, source_filename: str) -> None:
    job_dir = _job_dir(job_id)
    status = get_ingest_job(job_id) or {}
    warnings: list[str] = []
    companies: list[dict[str, Any]] = []

    try:
        pdf_entries = []
        pdfs_dir = job_dir / "pdfs"
        for p in sorted(pdfs_dir.glob("*.pdf")):
            pdf_entries.append((p.name, p))
        ordered = order_pdf_entries(pdf_entries)
        if not ordered:
            names = [n for n, _ in pdf_entries]
            sample = "、".join(names[:5])
            if len(names) > 5:
                sample += f" 等 {len(names)} 个"
            raise ValueError(
                "无法从文件名识别公司。"
                " 请在 PDF 文件名中含 canonical 代号（如 wm、37），"
                "或在 uploads/competitor/vertical_company_rules.json 配置内网中文名规则"
                "（亦可设环境变量 VERTICAL_COMPANY_RULES_JSON）。"
                f" zip 内 PDF：{sample}"
            )

        total = len(ordered)
        persist_vertical_pdfs(
            [(cid, pdf_path, display_name) for cid, pdf_path, display_name in ordered],
            uploaded_by=uploaded_by,
            source_filename=source_filename,
        )
        _write_job_status(
            job_id,
            {
                **status,
                "status": "running",
                "stage": "parsing",
                "progress": 0,
                "companies_total": total,
                "companies_done": 0,
                "warnings": warnings,
            },
        )

        for idx, (cid, pdf_path, display_name) in enumerate(ordered):
            archive = job_dir / "archive" / cid
            archive.mkdir(parents=True, exist_ok=True)
            res = convert_to_md_and_json(pdf_path, output_dir=archive)
            md_text = res.markdown_path.read_text(encoding="utf-8", errors="replace")
            co_warnings: list[str] = []
            company = company_from_docling(
                company_id=cid,
                company_name=display_name,
                company_index=idx,
                md_text=md_text,
                json_path=res.json_path,
                warnings=co_warnings,
            )
            company["_warnings"] = co_warnings
            companies.append(company)
            warnings.extend(co_warnings)
            pct = int(((idx + 1) / total) * 100)
            _write_job_status(
                job_id,
                {
                    **status,
                    "status": "running",
                    "stage": "parsing",
                    "progress": pct,
                    "companies_total": total,
                    "companies_done": idx + 1,
                    "current_company": display_name,
                    "warnings": warnings,
                },
            )

        now = datetime.now(timezone.utc).isoformat()
        snapshot = build_vertical_snapshot(
            companies,
            uploaded_by=uploaded_by,
            uploaded_at=now,
            source_filename=source_filename,
        )
        snapshot["warnings"] = list(snapshot.get("warnings") or []) + warnings
        save_vertical_snapshot(snapshot)
        merged_md = merged_markdown_from_companies(companies, snapshot["meta"]["title"])
        (job_dir / "merged.md").write_text(merged_md, encoding="utf-8")

        _write_job_status(
            job_id,
            {
                **status,
                "status": "completed",
                "stage": "done",
                "progress": 100,
                "companies_total": total,
                "companies_done": total,
                "companies_parsed": len(companies),
                "warnings": snapshot.get("warnings") or [],
                "completed_at": now,
            },
        )
    except Exception as exc:
        _write_job_status(
            job_id,
            {
                **status,
                "status": "failed",
                "stage": "failed",
                "progress": 100,
                "error": str(exc),
                "warnings": warnings,
            },
        )
    finally:
        with _jobs_lock:
            _running_jobs.discard(job_id)


def start_vertical_ingest_from_zip(
    zip_bytes: bytes,
    *,
    uploaded_by: str,
    source_filename: str,
) -> str:
    if len(zip_bytes) > MAX_ZIP_BYTES:
        raise ValueError("zip 文件过大（上限 120MB）")
    with _jobs_lock:
        if _running_jobs:
            raise ValueError("已有纵向解析任务进行中，请稍后再试")
    job_id = f"ving_{uuid.uuid4().hex[:12]}"
    job_dir = _job_dir(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    _extract_pdfs_from_zip(zip_bytes, job_dir)
    _write_job_status(
        job_id,
        {
            "job_id": job_id,
            "status": "queued",
            "stage": "queued",
            "progress": 0,
            "source_filename": source_filename,
            "uploaded_by": uploaded_by,
            "created_at": now,
            "warnings": [],
        },
    )

    def _run() -> None:
        run_vertical_ingest_job(job_id, uploaded_by=uploaded_by, source_filename=source_filename)

    with _jobs_lock:
        _running_jobs.add(job_id)
    threading.Thread(target=_run, daemon=True, name=f"vertical-ingest-{job_id}").start()
    return job_id


def start_vertical_pdf_only_from_zip(
    zip_bytes: bytes,
    *,
    uploaded_by: str,
    source_filename: str,
) -> dict[str, Any]:
    """仅存档 PDF 供纵向页直显，不调用 Docling。"""
    if len(zip_bytes) > MAX_ZIP_BYTES:
        raise ValueError("zip 文件过大（上限 120MB）")
    job_id = f"vpdf_{uuid.uuid4().hex[:12]}"
    job_dir = _job_dir(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    _extract_pdfs_from_zip(zip_bytes, job_dir)
    pdf_entries = []
    pdfs_dir = job_dir / "pdfs"
    for p in sorted(pdfs_dir.glob("*.pdf")):
        pdf_entries.append((p.name, p))
    ordered = order_pdf_entries(pdf_entries)
    if not ordered:
        names = [n for n, _ in pdf_entries]
        sample = "、".join(names[:5])
        if len(names) > 5:
            sample += f" 等 {len(names)} 个"
        raise ValueError(
            "无法从文件名识别公司。"
            " 请在 PDF 文件名中含 canonical 代号（如 wm、37），"
            "或在 uploads/competitor/vertical_company_rules.json 配置内网中文名规则。"
            f" zip 内 PDF：{sample}"
        )
    meta = persist_vertical_pdfs(
        ordered,
        uploaded_by=uploaded_by,
        source_filename=source_filename,
    )
    return {
        "job_id": job_id,
        "status": "completed",
        "companies_parsed": len(ordered),
        "pdf_meta": meta,
        "created_at": now,
    }
