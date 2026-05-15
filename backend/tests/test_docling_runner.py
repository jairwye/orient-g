"""docling_runner：解析命令与 HTTP 模式（不依赖真实 Docling 推理）。"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import backend.services.docling_runner as dr


class TestResolveDoclingArgv(unittest.TestCase):
    def test_prefers_which(self):
        with patch.object(dr.shutil, "which", return_value="/usr/bin/docling"):
            self.assertEqual(dr.resolve_docling_argv(), ["/usr/bin/docling"])

    def test_falls_back_to_venv_script(self):
        with tempfile.TemporaryDirectory() as td:
            scripts = Path(td)
            name = "docling.exe" if sys.platform == "win32" else "docling"
            (scripts / name).write_text("", encoding="utf-8")
            py_name = "python.exe" if sys.platform == "win32" else "python"
            py = scripts / py_name
            py.write_text("", encoding="utf-8")
            with patch.object(dr.shutil, "which", return_value=None):
                with patch.object(dr.sys, "executable", str(py.resolve())):
                    # Windows: avoid console launcher / wrong interpreter; match resolve_docling_argv docstring.
                    if sys.platform == "win32":
                        want = [str(py.resolve()), "-m", "docling.cli.main"]
                    else:
                        want = [str((scripts / name).resolve())]
                    self.assertEqual(dr.resolve_docling_argv(), want)

    def test_falls_back_to_python_m_docling(self):
        with tempfile.TemporaryDirectory() as td:
            scripts = Path(td)
            py_name = "python.exe" if sys.platform == "win32" else "python"
            py = scripts / py_name
            py.write_text("", encoding="utf-8")
            with patch.object(dr.shutil, "which", return_value=None):
                with patch.object(dr.sys, "executable", str(py.resolve())):
                    self.assertEqual(dr.resolve_docling_argv(), [str(py.resolve()), "-m", "docling"])


class TestConvertHttp(unittest.TestCase):
    def test_writes_full_md_and_json(self):
        out = Path(tempfile.mkdtemp())
        src = out / "in.txt"
        src.write_text("x", encoding="utf-8")

        class FakeResp:
            def __init__(self, payload):
                self._payload = payload

            def raise_for_status(self):
                return None

            def json(self):
                return self._payload

        class FakeClient:
            def __init__(self, *a, **k):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return None

            def post(self, url, files=None):
                self._url = url
                return FakeResp({"task_id": "task_1"})

            def get(self, url):
                if url.endswith("/status/poll/task_1"):
                    return FakeResp({"task_status": "success"})
                if url.endswith("/result/task_1"):
                    return FakeResp(
                        {
                            "document": {
                                "md_content": "# Title\n",
                                "json_content": {"k": 1},
                            },
                            "docling_version": "2.83.0",
                        }
                    )
                return FakeResp({})

        with patch.object(dr.settings, "docling_mode", "http"):
            with patch.object(dr.settings, "docling_http_base_url", "http://docling:8080"):
                with patch.object(dr.httpx, "Client", FakeClient):
                    with patch.object(dr.time, "sleep", lambda _s: None):
                        arc = out / "archive"
                        arc.mkdir(exist_ok=True)
                        res = dr.convert_to_md_and_json(src, output_dir=arc)
        self.assertEqual(res.markdown_path, arc / "full.md")
        self.assertEqual(res.json_path, arc / "full.json")
        self.assertEqual((arc / "full.md").read_text(encoding="utf-8"), "# Title\n")
        self.assertEqual(json.loads((arc / "full.json").read_text(encoding="utf-8")), {"k": 1})
        self.assertEqual(res.docling_version, "2.83.0")
        shutil.rmtree(out, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
