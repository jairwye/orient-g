from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from backend.config import settings
from backend.services.upstream_guard import assert_upstream_allowed

@dataclass(frozen=True)
class DoclingResult:
    markdown_path: Path
    json_path: Path
    docling_version: str | None


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


def _convert_http(source_path: Path, output_dir: Path, timeout_s: int) -> DoclingResult:
    base = (settings.docling_http_base_url or "").strip().rstrip("/")
    if not base:
        raise RuntimeError("DOCLING_MODE=http 但未配置 DOCLING_HTTP_BASE_URL")
    assert_upstream_allowed(base, service_name="Docling")
    output_dir.mkdir(parents=True, exist_ok=True)
    url = f"{base}/convert"
    read_timeout = max(1, int(getattr(settings, "docling_http_read_timeout_s", timeout_s) or timeout_s))
    timeout = httpx.Timeout(
        connect=max(1.0, float(getattr(settings, "docling_http_connect_timeout_s", 10))),
        read=max(1.0, float(min(timeout_s, read_timeout))),
        write=max(1.0, float(getattr(settings, "docling_http_write_timeout_s", 60))),
        pool=max(1.0, float(getattr(settings, "docling_http_pool_timeout_s", 30))),
    )
    max_retries = max(0, int(getattr(settings, "docling_http_max_retries", 2)))
    backoff = max(0.1, float(getattr(settings, "docling_http_retry_backoff_s", 1.5)))
    last_exc: Exception | None = None
    data: dict | None = None
    for i in range(max_retries + 1):
        try:
            with httpx.Client(timeout=timeout) as client:
                with source_path.open("rb") as f:
                    r = client.post(url, files={"file": (source_path.name, f, "application/octet-stream")})
                r.raise_for_status()
                data = r.json()
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
    md = data.get("markdown")
    doc = data.get("document")
    if md is None or doc is None:
        raise RuntimeError("Docling HTTP 响应缺少 markdown 或 document 字段")
    full_md = output_dir / "full.md"
    full_json = output_dir / "full.json"
    full_md.write_text(str(md), encoding="utf-8")
    full_json.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    ver = data.get("docling_version")
    return DoclingResult(
        markdown_path=full_md,
        json_path=full_json,
        docling_version=str(ver) if ver is not None else None,
    )


def convert_to_md_and_json(
    source_path: Path,
    *,
    output_dir: Path,
    timeout_s: int | None = None,
) -> DoclingResult:
    t = timeout_s if timeout_s is not None else settings.docling_http_timeout_s
    mode = (settings.docling_mode or "local").strip().lower()
    if mode == "http":
        return _convert_http(source_path, output_dir, t)
    if mode != "local":
        raise RuntimeError(f"未知 DOCLING_MODE={mode!r}，仅支持 local | http")
    return _convert_local(source_path, output_dir, t)
