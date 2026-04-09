"""
Orient-G Docling sidecar：内网专用，供 backend 以 DOCLING_MODE=http 调用。
POST /convert 上传原始文件，返回 markdown + document JSON（与本地 Docling CLI --to md/json 对齐）。
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile

app = FastAPI(title="Orient-G Docling Sidecar", version="1.0.0")


def _docling_version() -> str | None:
    try:
        cp = subprocess.run(
            ["docling", "--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return (cp.stdout or cp.stderr or "").strip() or None
    except Exception:
        return None


@app.get("/health")
def health():
    return {"ok": True, "docling_version": _docling_version()}


@app.post("/convert")
async def convert(file: UploadFile = File(...)):
    safe = Path(file.filename or "upload").name.replace("..", "_")
    suffix = Path(safe).suffix or ".pdf"
    raw = await file.read()
    if len(raw) > 80 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件过大（最大 80MB）")

    cli_timeout_s = int(os.environ.get("DOCLING_CLI_TIMEOUT_S", "600") or "600")

    try:
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            in_path = td_path / f"in{suffix}"
            in_path.write_bytes(raw)
            out_dir = td_path / "out"
            out_dir.mkdir()
            artifacts_path = (os.environ.get("DOCLING_ARTIFACTS_PATH") or "").strip()
            cmd = ["docling"]
            if artifacts_path:
                cmd += ["--artifacts-path", artifacts_path]
            cmd += ["--to", "md", "--to", "json", "--output", str(out_dir), str(in_path)]
            t0 = time.time()
            cp = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=cli_timeout_s,
            )
            elapsed_s = time.time() - t0
            if cp.returncode != 0:
                msg = (cp.stderr or cp.stdout or "docling failed")[:4000]
                raise HTTPException(status_code=500, detail=f"docling CLI 失败（{elapsed_s:.1f}s）: {msg}")

            mds = list(out_dir.glob("*.md"))
            jss = [p for p in out_dir.glob("*.json") if p.is_file()]
            if len(mds) != 1 or len(jss) != 1:
                raise HTTPException(
                    status_code=500,
                    detail=f"docling 输出文件不唯一：md={len(mds)} json={len(jss)}",
                )
            md_text = mds[0].read_text(encoding="utf-8")
            doc = json.loads(jss[0].read_text(encoding="utf-8"))
            return {
                "markdown": md_text,
                "document": doc,
                "docling_version": _docling_version(),
                "elapsed_s": round(elapsed_s, 3),
            }
    except HTTPException:
        raise
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail=f"docling 处理超时（{cli_timeout_s}s）") from None
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"docling JSON 无效: {e}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
