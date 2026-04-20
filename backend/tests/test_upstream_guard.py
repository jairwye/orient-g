from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.services.ai_interaction_llm import generate_chat_reply
from backend.services.docling_runner import convert_to_md_and_json
from backend.services.upstream_guard import assert_upstream_allowed


class TestUpstreamGuard(unittest.TestCase):
    def test_allows_localhost(self):
        with patch("backend.services.upstream_guard.settings.ai_upstream_block_remote", True):
            with patch(
                "backend.services.upstream_guard.settings.ai_upstream_allowed_hosts",
                "localhost,127.0.0.1,::1,ollama,docling",
            ):
                assert_upstream_allowed("http://127.0.0.1:11434", service_name="Ollama")
                assert_upstream_allowed("http://ollama:11434", service_name="Ollama")

    def test_blocks_remote_ip_by_default(self):
        with patch("backend.services.upstream_guard.settings.ai_upstream_block_remote", True):
            with patch(
                "backend.services.upstream_guard.settings.ai_upstream_allowed_hosts",
                "localhost,127.0.0.1,::1,ollama,docling",
            ):
                with self.assertRaisesRegex(RuntimeError, "已阻止访问远程"):
                    assert_upstream_allowed("http://192.168.104.108:11434", service_name="Ollama")

    def test_can_disable_block(self):
        with patch("backend.services.upstream_guard.settings.ai_upstream_block_remote", False):
            assert_upstream_allowed("http://192.168.104.108:11434", service_name="Ollama")

    def test_docling_http_convert_is_blocked_for_remote_host(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "x.pdf"
            out = root / "archive"
            src.write_bytes(b"%PDF-1.4\n")
            with patch("backend.services.docling_runner.settings.docling_mode", "http"):
                with patch("backend.services.docling_runner.settings.docling_http_base_url", "http://192.168.104.108:8080"):
                    with patch("backend.services.docling_runner.settings.ai_upstream_block_remote", True):
                        with patch(
                            "backend.services.docling_runner.settings.ai_upstream_allowed_hosts",
                            "localhost,127.0.0.1,::1,ollama,docling",
                        ):
                            with self.assertRaisesRegex(RuntimeError, "已阻止访问远程"):
                                convert_to_md_and_json(src, output_dir=out, timeout_s=5)

    def test_ai_chat_is_blocked_for_remote_ollama(self):
        with patch("backend.services.ai_interaction_llm.settings.ollama_url", "http://192.168.104.108:11434"):
            with patch("backend.services.ai_interaction_llm.settings.ai_upstream_block_remote", True):
                with patch(
                    "backend.services.ai_interaction_llm.settings.ai_upstream_allowed_hosts",
                    "localhost,127.0.0.1,::1,ollama,docling",
                ):
                    with self.assertRaisesRegex(RuntimeError, "已阻止访问远程"):
                        generate_chat_reply(model="qwen3:8b-q4_K_M", messages=[{"role": "user", "content": "hello"}])


if __name__ == "__main__":
    unittest.main()
