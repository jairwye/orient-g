"""vertical_pdf_to_md 单元测试（不依赖 uploads PDF）。"""
from __future__ import annotations

from backend.services.vertical_pdf_to_md import replace_company_section_in_md


def test_replace_company_section_in_md():
    src = "## 1. 可比公司A\n\n旧正文\n\n## 2. 可比公司B\n\n其他\n"
    out = replace_company_section_in_md(src, 1, "可比公司A", "新正文\n\n段落二")
    assert "## 1. 可比公司A" in out
    assert "新正文" in out
    assert "## 2. 可比公司B" in out
