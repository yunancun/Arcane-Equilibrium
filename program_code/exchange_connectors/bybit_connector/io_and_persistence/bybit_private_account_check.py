#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_private_account_check.py
Role:
- 讀取 Bybit 私有帳戶只讀資訊 stub（待真實 REST 接線）
- 產出帳戶餘額/權益相關的 latest + dated JSON 檔案

Purpose in system:
- 是 readonly observer 鏈路最基礎的資料源之一
- 為 preflight guard / snapshot / audit 提供帳戶側輸入

Upstream:
- Bybit private REST API（目前 stub；canned ``api_key_not_configured``/
  ``not_implemented`` payload）

Downstream:
- bybit_private_rest_preflight_guard.py
- bybit_snapshot_to_postgres.py
- bybit_full_readonly_observer_cycle.py
- bybit_build_system_snapshot.py（讀取本檔產出的 latest JSON）

Maintenance notes:
- 當前定位是只讀 stub，不允許出現任何下單或寫操作
- 如修改輸出欄位，需同步檢查 snapshot 和 guard 的欄位引用
- 真實 REST 接線將由 WS-RETIRE-1 follow-up 完成

History:
- 2026-04-23 commit ``f42face``：刪 ``helper_scripts/maintenance_scripts/
  bybit_connector/`` 含 ``.py.orig`` stub；本檔 thin wrapper 撞 file-not-found
  silent-fail 8 天（healthcheck [19] 2026-04-26 補上後揭發）。
- 2026-04-27 OBSERVER-RESTORE-1：stub 邏輯內聯至 ``_bybit_private_check_stub
  .emit_stub``；移除對已刪 wrapper/.orig 依賴；輸出與 ``f42face`` 前 stub
  byte-identical（同 canned JSON、同 latest + dated 雙寫契約）。
'''

[Maintainer Note - English]
Script: bybit_private_account_check.py
Role:
- Read-only Bybit private account stub (until real REST is wired in)
- Emits account balance/equity latest + dated JSON files

Downstream:
- bybit_private_rest_preflight_guard.py
- bybit_snapshot_to_postgres.py
- bybit_full_readonly_observer_cycle.py
- bybit_build_system_snapshot.py

History:
- 2026-04-23 commit ``f42face``: deleted the
  ``helper_scripts/maintenance_scripts/bybit_connector/`` directory
  containing the ``.py.orig`` stub this thin wrapper used to ``execv`` into;
  ``returncode=2`` silent-fail for 8 days until healthcheck [19] caught it.
- 2026-04-27 OBSERVER-RESTORE-1: inlined stub logic into
  ``_bybit_private_check_stub.emit_stub``; removed dependency on deleted
  wrapper/.orig; output is byte-identical to pre-``f42face`` stub.
"""

import sys
from pathlib import Path

# Ensure sibling helper is importable regardless of how the script is
# invoked (cycle subprocess, cron, ad-hoc shell). ``Path(__file__).parent``
# is always the io_and_persistence/ directory containing the helper.
# 確保 sibling helper 可被 import — 不論 invoke 來源（cycle subprocess /
# cron / ad-hoc shell），``Path(__file__).parent`` 永遠是本目錄。
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _bybit_private_check_stub import emit_stub, srv_root  # noqa: E402

PREFIX = "bybit_private_account_check"
LATEST = srv_root() / "log_files" / "connector_logs" / f"{PREFIX}_latest.json"


if __name__ == "__main__":
    # Account-side stub has no schema-specific fields beyond the shared
    # base payload (ok / retCode / retMsg / health_state / issues / data).
    # 帳戶 stub 無 schema-specific 欄位，沿用共用 base payload。
    sys.exit(emit_stub(PREFIX, LATEST, {"data": {}}))
