#!/usr/bin/env python3
"""Backward-compatible W2 paper edge report CLI shim.

MODULE_NOTE:
    兼容舊入口 `python3 helper_scripts/reports/w2_paper_edge_report.py`。
    真正實作已依 W2 spec v1.2 §7.1 六項 metric 拆到 `reports/w2/`
    sibling modules；本檔僅保留一個 sprint 的 thin wrapper。
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from .w2.w2_paper_edge_report import main
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from w2.w2_paper_edge_report import main


if __name__ == "__main__":
    sys.exit(main())
