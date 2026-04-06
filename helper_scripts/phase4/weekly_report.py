#!/usr/bin/env python3
"""CLI thin wrapper for Phase 4 weekly report generator (4-20).

Phase 4 週度報告生成器 CLI 薄包裝層（4-20）。

Usage / 用法:
    DSN=postgresql://redacted@host/db \\
        python helper_scripts/phase4/weekly_report.py \\
            --output reports/phase4_2026-W15.md --persist
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from program_code.ml_training.weekly_report_generator import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
