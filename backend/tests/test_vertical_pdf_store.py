"""vertical_pdf_store 单元测试。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.services import competitor_edition_store as ed
from backend.services import vertical_pdf_store as vps
from backend.config import settings


class TestVerticalPdfStore(unittest.TestCase):
    def test_persist_and_load(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            settings.upload_dir = str(root)
            pdf_a = root / "a.pdf"
            pdf_b = root / "b.pdf"
            pdf_a.write_bytes(b"%PDF-1.4 test")
            pdf_b.write_bytes(b"%PDF-1.4 test2")

            ed.ensure_edition("2025-annual", kind="annual", has_vertical=True)
            ed.set_current("2025-annual")

            meta = vps.persist_vertical_pdfs(
                [("wm", pdf_a, "完美世界"), ("37", pdf_b, "三七互娱")],
                uploaded_by="admin",
                source_filename="7pdf.zip",
                edition_id="2025-annual",
            )
            self.assertEqual(meta["company_count"], 2)
            loaded = vps.load_vertical_pdf_meta(edition_id="2025-annual")
            assert loaded is not None
            self.assertEqual(loaded["company_count"], 2)
            self.assertEqual(vps.list_vertical_pdf_ids(edition_id="2025-annual"), ["37", "wm"])
            self.assertTrue(vps.vertical_pdf_path("wm", edition_id="2025-annual").is_file())
            dest_root = root / "competitor" / "editions" / "2025-annual" / "vertical" / "pdfs"
            self.assertTrue((dest_root / "wm.pdf").is_file())
            vps.persist_vertical_pdfs(
                [("wm", pdf_a, "完美世界")],
                uploaded_by="admin",
                source_filename="1pdf.zip",
                edition_id="2025-annual",
            )
            self.assertEqual(vps.list_vertical_pdf_ids(edition_id="2025-annual"), ["wm"])
            self.assertFalse((dest_root / "37.pdf").exists())
            with self.assertRaises(ValueError):
                vps.vertical_pdf_path("../evil", edition_id="2025-annual")


if __name__ == "__main__":
    unittest.main()
