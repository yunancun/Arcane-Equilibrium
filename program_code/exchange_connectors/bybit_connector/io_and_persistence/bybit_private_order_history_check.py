#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_private_order_history_check.py
Role:
- 讀取 Bybit 訂單歷史只讀資訊 stub（待真實 REST 接線）
- 提供近期訂單活動觀察依據

Purpose in system:
- observer 判斷近期是否存在掛單 / 訂單歷史
- 當前無訂單歷史也可能是正常狀態

Upstream:
- Bybit private REST API（目前 stub；canned ``api_key_not_configured``/
  ``not_implemented`` payload）

Downstream:
- bybit_private_rest_preflight_guard.py
- bybit_snapshot_to_postgres.py
- bybit_build_decision_packet.py
- bybit_build_system_snapshot.py

Maintenance notes:
- 不要把 ``order_count = 0`` 誤判為系統故障
- 欄位改動需同步 snapshot / packet / audit
- 真實 REST 接線將由 WS-RETIRE-1 follow-up 完成

History:
- 2026-04-23 commit ``f42face``：刪 ``.py.orig`` stub。
- 2026-04-27 OBSERVER-RESTORE-1：stub 邏輯內聯至 sibling helper；
  輸出與 ``f42face`` 前 stub byte-identical（含 ``order_count: 0 / orders: []``）。
'''

[Maintainer Note - English]
Script: bybit_private_order_history_check.py
Role:
- Read-only Bybit order history stub (until real REST is wired in)
- Reports recent order activity for observer

History:
- 2026-04-23 commit ``f42face`` deleted ``.py.orig`` stub.
- 2026-04-27 OBSERVER-RESTORE-1 inlined stub logic via sibling helper;
  output is byte-identical to pre-``f42face`` stub
  (``order_count: 0 / orders: []``).
"""

import sys
from pathlib import Path

# See sibling docstring for sys.path import note.
# 詳見 sibling helper docstring 的 sys.path import 說明。
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _bybit_private_check_stub import emit_stub, srv_root  # noqa: E402

PREFIX = "bybit_private_order_history_check"
LATEST = srv_root() / "log_files" / "connector_logs" / f"{PREFIX}_latest.json"


if __name__ == "__main__":
    # Order history stub schema: empty order list.
    # Order history stub schema：空 order list。
    sys.exit(emit_stub(PREFIX, LATEST, {"order_count": 0, "orders": []}))
