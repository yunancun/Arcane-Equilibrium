#!/usr/bin/env python3
"""W-AUDIT-8c Stage 0R CLI 頂層 wrapper（mirror sibling 8b precedent）。

MODULE_NOTE
模塊用途：W-AUDIT-8c Liquidation Cluster Stage 0R replay 的頂層 operator
入口，等同 sibling `w_audit_8b_funding_skew_stage0r.py` 的 8b wrapper 模式。
為什麼存在：operator 慣性 — Stage 0R 系列 (w2 / 8b / 8c) 都從
`helper_scripts/reports/<topic>_stage0r.py` 一條指令觸發；本檔僅做
sys.path 補位 + 委派至 `w_audit_8c/liquidation_cluster_stage0r_report.main`。
主要類/函數：直接呼 `main()`，所有 argparse / PG / metrics / render 邏輯
            都在被委派模塊。
依賴：`helper_scripts/reports/w_audit_8c/liquidation_cluster_stage0r_report.py`。
硬邊界：不放任何業務邏輯；僅 import + delegate。
"""

from __future__ import annotations

import sys
from pathlib import Path

# sys.path 補位：當 operator 直接執行 `python helper_scripts/reports/
# w_audit_8c_liquidation_cluster_stage0r.py` 時，被委派模塊與 sibling
# metrics 在 w_audit_8c/ 內部以 sibling import 互引（package-relative
# 或裸名兩種 import 模式），需把 package 目錄加進 sys.path。
HERE = Path(__file__).resolve().parent
PKG = HERE / "w_audit_8c"
if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

from liquidation_cluster_stage0r_report import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
