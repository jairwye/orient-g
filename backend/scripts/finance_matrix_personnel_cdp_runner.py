#!/usr/bin/env python3
"""人员结构浏览器 CDP runner（8 条，独立报告）。

用法:
  py -3.10 backend/scripts/finance_matrix_personnel_cdp_runner.py
  py -3.10 backend/scripts/finance_matrix_personnel_cdp_runner.py --dry-run
  py -3.10 backend/scripts/finance_matrix_personnel_cdp_runner.py --only personnel/A3-横比-深度/deep
"""
from __future__ import annotations

import sys

if __name__ == "__main__":
    argv = [sys.argv[0], "--suite", "personnel", *sys.argv[1:]]
    sys.argv = argv
    from finance_matrix_browser_cdp_runner import main

    main()
