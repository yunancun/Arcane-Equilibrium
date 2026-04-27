#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_private_positions_check.py
Role:
- 讀取 Bybit 私有持倉只讀資訊 stub（待真實 REST 接線）
- 產出持倉 latest + dated JSON 檔案；下游用於判斷是否有非零持倉

Purpose in system:
- observer 風險判斷的基礎輸入
- 當前常見健康狀態為 position_count = 0（stub）

Upstream:
- Bybit private REST API（目前 stub；canned ``api_key_not_configured``/
  ``not_implemented`` payload）

Downstream:
- bybit_private_rest_preflight_guard.py
- bybit_snapshot_to_postgres.py
- bybit_build_decision_packet.py
- bybit_build_system_snapshot.py

Maintenance notes:
- 當前「無持倉」是正常健康狀態，不代表異常
- 若調整 category / symbol 邏輯，需同步檢查 packet 與 verdict
- 真實 REST 接線將由 WS-RETIRE-1 follow-up 完成

History:
- 2026-04-23 commit ``f42face``：刪 ``.py.orig`` stub；本檔 thin wrapper
  撞 file-not-found silent-fail 8 天。
- 2026-04-27 OBSERVER-RESTORE-1：stub 邏輯內聯至 sibling helper
  ``_bybit_private_check_stub.emit_stub``；輸出與 ``f42face`` 前 stub
  byte-identical（同 canned JSON 含 ``position_count: 0 / positions: []``、
  同 latest + dated 雙寫契約）。
'''

[Maintainer Note - English]
Script: bybit_private_positions_check.py
Role:
- Read-only Bybit private positions stub (until real REST is wired in)
- Emits positions latest + dated JSON; downstream evaluates non-zero
  position presence

Downstream:
- bybit_private_rest_preflight_guard.py
- bybit_snapshot_to_postgres.py
- bybit_build_decision_packet.py
- bybit_build_system_snapshot.py

History:
- 2026-04-23 commit ``f42face`` deleted ``.py.orig`` stub.
- 2026-04-27 OBSERVER-RESTORE-1 inlined stub logic via sibling helper;
  output is byte-identical to pre-``f42face`` stub
  (``position_count: 0 / positions: []``).
"""

import sys
from pathlib import Path

# See sibling docstring for sys.path import note.
# 詳見 sibling helper docstring 的 sys.path import 說明。
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _bybit_private_check_stub import emit_stub, srv_root  # noqa: E402

PREFIX = "bybit_private_positions_check"
LATEST = srv_root() / "log_files" / "connector_logs" / f"{PREFIX}_latest.json"


if __name__ == "__main__":
    # Positions stub schema: empty position list (matches pre-f42face .orig
    # which always returned position_count=0 / positions=[]).
    # Positions stub schema：空 position list（與 ``f42face`` 前 ``.orig``
    # 永遠回 ``position_count=0 / positions=[]`` 一致）。
    sys.exit(emit_stub(PREFIX, LATEST, {"position_count": 0, "positions": []}))
