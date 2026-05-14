from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from backend.config import settings
from backend.services.upstream_guard import assert_upstream_allowed

# docling 并发控制：同一时刻只允许一个 docling 请求，防止多进程同时高负载触发 CPU 冻结
_docling_semaphore = threading.Semaphore(1)

@dataclass(frozen=True)
class DoclingResult:
    markdown_path: Path
    json_path: Path
    docling_version: str | None
    docling_task_id: str | None = None


def _run(cmd: list[str], *, cwd: Path | None = None, timeout_s: int = 600) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout_s,
    )

def resolve_docling_argv(cli: str = "docling") -> list[str]:
    """
    解析 Docling CLI 的 subprocess 前缀：
    - 优先 PATH 中的 docling
    - 其次当前 Python 解释器同目录下的 docling / docling.exe（Windows venv）
    - 最后 python -m docling
    """
    w = shutil.which(cli)
    if w:
        # On Windows, console launchers (.exe) can end up loading a different
        # base interpreter / DLL search behavior than the current venv Python.
        # Prefer running `python -m docling` to ensure we use the current
        # interpreter and site-packages when possible.
        if sys.platform == "win32" and w.lower().endswith(".exe"):
            # `docling` package may not provide docling.__main__.
            # Use the CLI module explicitly to stay on the current interpreter.
            return [sys.executable, "-m", "docling.cli.main"]
        return [w]
    parent = Path(sys.executable).resolve().parent
    for name in ("docling.exe", "docling"):
        p = parent / name
        if p.is_file():
            if sys.platform == "win32" and p.suffix.lower() == ".exe":
                return [sys.executable, "-m", "docling.cli.main"]
            return [str(p)]
    return [sys.executable, "-m", "docling"]


def get_docling_version(argv0: list[str] | None = None) -> str | None:
    cmd = list(argv0 or resolve_docling_argv())
    try:
        cp = _run(cmd + ["--version"], timeout_s=60)
        return (cp.stdout or cp.stderr or "").strip() or None
    except Exception:
        return None


def _convert_local(source_path: Path, output_dir: Path, timeout_s: int) -> DoclingResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    # 优先走 Python API：在 Windows 上，docling.exe 启动时可能触发 torch DLL 初始化失败（WinError 1114），
    # 但库 API 在同一解释器进程内通常可正常工作。
    try:
        from docling.document_converter import DocumentConverter

        converter = DocumentConverter()
        result = converter.convert(str(source_path))
        doc = result.document
        md_text = doc.export_to_markdown()
        doc_dict = doc.export_to_dict()
        md_path = output_dir / "full.md"
        json_path = output_dir / "full.json"
        md_path.write_text(md_text or "", encoding="utf-8")
        json_path.write_text(json.dumps(doc_dict, ensure_ascii=False, indent=2), encoding="utf-8")
        return DoclingResult(markdown_path=md_path, json_path=json_path, docling_version=None)
    except Exception as api_err:
        pass

    argv0 = resolve_docling_argv()
    cmd = argv0 + ["--to", "md", "--to", "json", "--output", str(output_dir), str(source_path)]
    try:
        _run(cmd, timeout_s=timeout_s)
    except subprocess.CalledProcessError as e:
        stderr = e.stderr or ""
        stdout = e.stdout or ""
        err = (stderr or stdout or str(e))[:4000]
        raise RuntimeError(f"Docling CLI 失败: {err}") from e

    stem = source_path.stem
    md_path = output_dir / f"{stem}.md"
    json_path = output_dir / f"{stem}.json"
    if not md_path.exists() or not json_path.exists():
        mds = list(output_dir.glob("*.md"))
        jss = list(output_dir.glob("*.json"))
        if len(mds) == 1:
            md_path = mds[0]
        if len(jss) == 1:
            json_path = jss[0]
    if not md_path.exists():
        raise RuntimeError(f"Docling 输出缺少 markdown：{md_path}")
    if not json_path.exists():
        raise RuntimeError(f"Docling 输出缺少 json：{json_path}")
    try:
        json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise RuntimeError(f"Docling JSON 无法解析：{json_path} ({e})") from e
    return DoclingResult(
        markdown_path=md_path,
        json_path=json_path,
        docling_version=get_docling_version(argv0),
    )


def _save_docling_task_id(tenant_id: str, kb_task_id: str, docling_task_id: str, task_position: int | None) -> None:
    """Save the docling task ID to kb_tasks immediately after submission."""
    try:
        from backend.services.kb_tasks import update_task
        update_task(tenant_id, kb_task_id, docling_task_id=docling_task_id, task_position=task_position)
    except Exception:
        pass  # best-effort; don't fail the conversion


def _save_task_position(tenant_id: str, kb_task_id: str, task_position: int) -> None:
    """Update the task_position in kb_tasks during polling."""
    try:
        from backend.services.kb_tasks import update_task
        update_task(tenant_id, kb_task_id, task_position=task_position)
    except Exception:
        pass


def _convert_http(
    source_path: Path,
    output_dir: Path,
    *,
    is_cancelled = None,
    tenant_id: str = "",
    kb_task_id: str = "",
) -> DoclingResult:
    base = (settings.docling_http_base_url or "").strip().rstrip("/")
    if not base:
        raise RuntimeError("DOCLING_MODE=http 但未配置 DOCLING_HTTP_BASE_URL")
    assert_upstream_allowed(base, service_name="Docling")
    output_dir.mkdir(parents=True, exist_ok=True)

    # docling-serve 官方 API：POST /v1/convert/file/async → 轮询 → GET /v1/result/{task_id}
    # 不设 HTTP 读写超时，依赖 queue lease 心跳 + is_cancelled 控制任务生命周期
    timeout = httpx.Timeout(
        connect=max(1.0, float(getattr(settings, "docling_http_connect_timeout_s", 10))),
        read=None,
        write=None,
        pool=30.0,
    )
    async_url = f"{base}/convert/file/async"
    poll_url_base = f"{base}/status/poll"
    result_url_base = f"{base}/result"

    max_retries = 2
    backoff = 1.5
    last_exc: Exception | None = None
    data: dict | None = None
    docling_task_id: str | None = None

    for i in range(max_retries + 1):
        try:
            with httpx.Client(timeout=timeout) as client:
                # 1. 提交异步任务
                with source_path.open("rb") as f:
                    r = client.post(async_url, files={"files": (source_path.name, f, "application/octet-stream")})
                r.raise_for_status()
                task = r.json()
                docling_task_id = task.get("task_id")
                if not docling_task_id:
                    raise RuntimeError("Docling async 响应缺少 task_id")

                # 立即保存 docling_task_id 到 kb_tasks，防止重启丢失
                if tenant_id and kb_task_id:
                    _save_docling_task_id(tenant_id, kb_task_id, docling_task_id, task.get("task_position"))

                # 2. 轮询任务状态（无限时硬上限，由 is_cancelled + queue lease 控制）
                while True:
                    time.sleep(5)
                    if is_cancelled is not None and is_cancelled():
                        raise RuntimeError("任务已取消")
                    r = client.get(f"{poll_url_base}/{docling_task_id}")
                    r.raise_for_status()
                    status = r.json()
                    task_status = status.get("task_status")
                    task_position = status.get("task_position")
                    # 更新排队位置
                    if tenant_id and kb_task_id and task_position is not None:
                        _save_task_position(tenant_id, kb_task_id, task_position)
                    if task_status == "success":
                        # 3. 获取结果
                        r = client.get(f"{result_url_base}/{docling_task_id}")
                        r.raise_for_status()
                        data = r.json()
                        break
                    elif task_status == "failure":
                        errors = status.get("errors", [])
                        raise RuntimeError(f"Docling 任务失败: {errors}")
                    # pending / processing → 继续轮询
            break
        except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError, httpx.HTTPStatusError) as e:
            last_exc = e
            if i >= max_retries:
                break
            time.sleep(backoff * (2**i))

    if data is None:
        raise RuntimeError(f"Docling HTTP 调用失败（重试后）: {last_exc}") from last_exc
    if not isinstance(data, dict):
        raise RuntimeError("Docling HTTP 响应不是 JSON 对象")

    # 提取结果：官方 API 响应 {"document": {"md_content": ..., "json_content": ...}}
    doc_obj = data.get("document") or {}
    md = doc_obj.get("md_content", "") or ""
    json_str = doc_obj.get("json_content")
    if isinstance(json_str, str):
        try:
            doc = json.loads(json_str)
        except Exception:
            doc = {"raw": json_str}
    elif isinstance(json_str, dict):
        doc = json_str
    else:
        doc = {"raw": str(json_str) if json_str is not None else ""}
    if md is None or doc is None:
        raise RuntimeError("Docling HTTP 响应缺少 markdown 或 document 字段")

    full_md = output_dir / "full.md"
    full_json = output_dir / "full.json"
    full_md.write_text(str(md), encoding="utf-8")
    full_json.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    ver = data.get("docling_version") or data.get("version")
    return DoclingResult(
        markdown_path=full_md,
        json_path=full_json,
        docling_version=str(ver) if ver is not None else None,
        docling_task_id=docling_task_id,
    )


def convert_to_md_and_json(
    source_path: Path,
    *,
    output_dir: Path,
    is_cancelled = None,
    tenant_id: str = "",
    kb_task_id: str = "",
) -> DoclingResult:
    mode = (settings.docling_mode or "local").strip().lower()
    if mode == "http":
        with _docling_semaphore:
            return _convert_http(source_path, output_dir, is_cancelled=is_cancelled, tenant_id=tenant_id, kb_task_id=kb_task_id)
    if mode != "local":
        raise RuntimeError(f"未知 DOCLING_MODE={mode!r}，仅支持 local | http")
    with _docling_semaphore:
        return _convert_local(source_path, output_dir)
