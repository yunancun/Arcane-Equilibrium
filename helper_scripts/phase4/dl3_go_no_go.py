#!/usr/bin/env python3
"""CLI thin wrapper for DL-3 Go/No-Go report generator (Phase 4 4-13).

DL-3 Go/No-Go 報告生成器的 CLI 薄包裝層。

The actual logic lives in `program_code/ml_training/dl3_go_no_go.py` to keep
it import-friendly for unit tests. This file is just a CLI entry point.

實際邏輯在 program_code/ml_training/dl3_go_no_go.py，方便單元測試 import。
本檔僅為 CLI 入口。

Usage / 用法:
    python helper_scripts/phase4/dl3_go_no_go.py \\
        --ab-result-json reports/ab_result.json \\
        --metadata-json reports/dl3_metadata.json \\
        --output reports/dl3_go_no_go.md
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add repo root to sys.path so the import works when running from helper_scripts/.
# 將 repo root 加入 sys.path，使從 helper_scripts/ 執行時 import 能成功。
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from program_code.ml_training.dl3_go_no_go import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
