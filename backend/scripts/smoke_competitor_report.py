#!/usr/bin/env python3
"""竞品财报 smoke：admin 上传蓝本 MD → GET report 断言 10 sections。

用法（仓库根目录）：
  python backend/scripts/smoke_competitor_report.py
  python backend/scripts/smoke_competitor_report.py --base-url http://127.0.0.1:8000 --user admin
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import jwt
import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_MD = REPO_ROOT / "uploads" / "行业财报汇析-2025年_数据文档_YYCQ版.md"


def _token(secret: str, username: str) -> str:
    return jwt.encode({"sub": username}, secret, algorithm="HS256")


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test competitor report API")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--user", default="admin")
    parser.add_argument("--secret", default=None, help="AUTH secret; default from backend.config")
    args = parser.parse_args()

    if not FIXTURE_MD.is_file():
        print(f"FAIL: fixture missing: {FIXTURE_MD}", file=sys.stderr)
        return 1

    secret = args.secret
    if not secret:
        sys.path.insert(0, str(REPO_ROOT))
        from backend.config import settings

        secret = settings.auth_secret

    headers = {"Authorization": f"Bearer {_token(secret, args.user)}"}
    base = args.base_url.rstrip("/")

    upload = requests.post(
        f"{base}/api/competitor/admin/upload",
        headers=headers,
        files={"file": (FIXTURE_MD.name, FIXTURE_MD.read_bytes(), "text/markdown")},
        timeout=120,
    )
    if upload.status_code != 200:
        print(f"FAIL: upload {upload.status_code} {upload.text[:500]}", file=sys.stderr)
        return 1
    body = upload.json()
    if body.get("sections_parsed") != 10:
        print(f"FAIL: sections_parsed={body.get('sections_parsed')}", file=sys.stderr)
        return 1

    report = requests.get(f"{base}/api/competitor/report", headers=headers, timeout=60)
    if report.status_code != 200:
        print(f"FAIL: report {report.status_code}", file=sys.stderr)
        return 1
    snap = report.json()
    sections = snap.get("sections") or []
    if len(sections) != 10:
        print(f"FAIL: len(sections)={len(sections)}", file=sys.stderr)
        return 1

    summary = requests.get(f"{base}/api/competitor/summary", headers=headers, timeout=30)
    if summary.status_code != 200 or not summary.json().get("has_report"):
        print("FAIL: summary missing has_report", file=sys.stderr)
        return 1

    print(f"OK: upload + report ({len(sections)} sections) + summary")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
