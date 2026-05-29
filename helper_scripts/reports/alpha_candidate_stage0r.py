#!/usr/bin/env python3
"""Alpha Tournament Candidate Stage 0R Runner 頂層 wrapper（mirror 8b/8c shim）。

MODULE_NOTE
模塊用途：alpha tournament candidate Stage 0R runner 的頂層 operator 入口，
等同 sibling `w_audit_8c_liquidation_cluster_stage0r.py` 的 shim 模式。
為什麼存在：operator 慣性 — Stage 0R 系列都從
`helper_scripts/reports/<topic>_stage0r.py` 一條指令觸發；本檔僅做 sys.path
補位 + 委派至 `alpha_candidate_stage0r/candidate_stage0r_report.main`。
主要類/函數：直接呼 main()，所有 argparse / PG / metrics / render 邏輯都在
            被委派模塊。
依賴：`helper_scripts/reports/alpha_candidate_stage0r/candidate_stage0r_report.py`
      （內部委派 candidate_stage0r_runner.run_candidates；復用 w_audit_8c
      metrics + w_audit_8b 統計原語）。
硬邊界：不放任何業務邏輯；僅 import + delegate。
"""

from __future__ import annotations

import sys
from pathlib import Path

# sys.path 補位：被委派模塊 + adapter 在 alpha_candidate_stage0r/ 內以裸名
# import sibling（w_audit_8c / w_audit_8b 純統計原語）；直接執行（非 -m）時
# 需把這三個目錄都加進 sys.path（package-relative import fallback 路徑）。
HERE = Path(__file__).resolve().parent
for _sub in ("alpha_candidate_stage0r", "w_audit_8c", "w_audit_8b"):
    _pkg = HERE / _sub
    if str(_pkg) not in sys.path:
        sys.path.insert(0, str(_pkg))

from candidate_stage0r_report import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
