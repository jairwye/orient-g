"""vertical_pdf_store 单元测试。"""
from __future__ import annotations

import tempfile
import unittest
import unittest.mock
from pathlib import Path

from backend.services import vertical_pdf_store as vps


class TestVerticalPdfStore(unittest.TestCase):
    def test_persist_and_load(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pdf_a = root / "a.pdf"
            pdf_b = root / "b.pdf"
            pdf_a.write_bytes(b"%PDF-1.4 test")
            pdf_b.write_bytes(b"%PDF-1.4 test2")

            with unittest.mock.patch.object(vps, "competitor_dir", return_value=root / "competitor"):
                meta = vps.persist_vertical_pdfs(
                    [("wm", pdf_a, "完美世界"), ("37", pdf_b, "三七互娱")],
                    uploaded_by="admin",
                    source_filename="7pdf.zip",
                )
                self.assertEqual(meta["company_count"], 2)
                loaded = vps.load_vertical_pdf_meta()
                assert loaded is not None
                self.assertEqual(loaded["company_count"], 2)
                self.assertEqual(vps.list_vertical_pdf_ids(), ["37", "wm"])
                self.assertTrue(vps.vertical_pdf_path("wm").is_file())
                vps.persist_vertical_pdfs(
                    [("wm", pdf_a, "完美世界")],
                    uploaded_by="admin",
                    source_filename="1pdf.zip",
                )
                self.assertEqual(vps.list_vertical_pdf_ids(), ["wm"])
                self.assertFalse((root / "competitor" / "vertical" / "pdfs" / "37.pdf").exists())
                with self.assertRaises(ValueError):
                    vps.vertical_pdf_path("../evil")


if __name__ == "__main__":
    unittest.main()
