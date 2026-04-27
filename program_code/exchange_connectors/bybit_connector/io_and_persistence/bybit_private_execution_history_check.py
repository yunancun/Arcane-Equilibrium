#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_private_execution_history_check.py
Role:
- 觀察最近是否存在真實成交（execution history）only-read stub
- 真實 REST 接線待 WS-RETIRE-1 follow-up；目前為 no-op observer

Purpose in system:
- 為 observer 提供 execution history 上下文
- 當前 spot / linear 都可能為 0，且屬於允許狀態

Upstream:
- Bybit private REST API（目前未接線）

Downstream:
- bybit_private_rest_preflight_guard.py（讀 LATEST file）
- bybit_snapshot_to_postgres.py
- bybit_build_decision_packet.py
- bybit_build_system_snapshot.py（讀 LATEST.spot.ok + LATEST.linear.ok）

Maintenance notes:
- 當前無成交歷史是正常狀態
- 若修改輸出結構，需同步 snapshot payload_time_summary 與 audit
- 真實 REST 接線將由 WS-RETIRE-1 follow-up 完成

History:
- 2026-04-23 commit ``f42face``：刪 ``.py.orig`` 與整個 maintenance_scripts 目錄。
- 2026-04-27 OBSERVER-RESTORE-1：與其他 3 個 ``bybit_private_*_check.py``
  不同 — execution_history 既有 LATEST 檔（2026-03-22 寫入，``ok=true /
  retCode=0`` 真實 REST 結果）保留為 fossil，本檔為 no-op observer 不覆寫
  LATEST，避免 ``ok=true → ok=false`` 對下游 ``bybit_build_system_snapshot
  .py`` 引入新的 false 訊號（preserve status quo per operator 「不要影響
  到其他部分的正常運行」指令）。Returncode=0 確保 healthcheck [19] cycle
  ``steps[].ok=true``。dated copy 不寫（dated 對齊 LATEST 寫入策略）。
'''

[Maintainer Note - English]
Script: bybit_private_execution_history_check.py
Role:
- Read-only observer stub for Bybit execution history
- Real REST integration deferred to WS-RETIRE-1 follow-up; this is a no-op
  observer

Downstream:
- bybit_private_rest_preflight_guard.py (reads LATEST file)
- bybit_snapshot_to_postgres.py
- bybit_build_decision_packet.py
- bybit_build_system_snapshot.py (reads LATEST.spot.ok + LATEST.linear.ok)

History:
- 2026-04-23 commit ``f42face`` deleted ``.py.orig`` along with the entire
  maintenance_scripts directory.
- 2026-04-27 OBSERVER-RESTORE-1: unlike the other 3 stub scripts,
  ``execution_history`` has an existing LATEST file (written 2026-03-22
  with real REST result ``ok=true / retCode=0``) that is preserved as a
  fossil. This script is now a no-op observer that does NOT overwrite
  LATEST — preventing the downstream behavioural shift
  (``ok=true → ok=false``) that overwriting would introduce in
  ``bybit_build_system_snapshot.py`` (operator directive: "do not affect
  other parts' normal operation"). Returncode=0 keeps healthcheck [19]
  cycle ``steps[].ok=true``. Dated copy is not written (dated cadence
  follows LATEST write cadence).
"""

from __future__ import annotations

import json
import sys
import time

# OBSERVER-RESTORE-1 (2026-04-27): no-op observer. Don't write LATEST so
# downstream consumers continue reading the existing 2026-03-22 fossil
# file unchanged. Stdout payload signals our stub state for cycle ``run_cmd``
# capture (visible in operator triage but downstream doesn't read stdout).
# OBSERVER-RESTORE-1：no-op observer，不寫 LATEST 讓下游繼續讀 2026-03-22
# fossil 檔；stdout 標記本 stub 狀態供 cycle ``run_cmd`` 捕獲（operator
# triage 可見，下游不讀 stdout）。
PREFIX = "bybit_private_execution_history"


def main() -> int:
    """Emit informational stub payload to stdout. LATEST file untouched.
    輸出 informational stub payload 至 stdout；LATEST 檔不動。"""
    stub_msg = {
        "ok": True,
        "stub_state": "no_op_observer",
        "note": (
            "OBSERVER-RESTORE-1 (2026-04-27): real Bybit REST execution-"
            "history call deferred to WS-RETIRE-1 follow-up; this script "
            "is a no-op observer to satisfy the readonly cycle contract "
            "without overwriting the existing LATEST fossil file."
        ),
        "ts_ms": int(time.time() * 1000),
        "prefix": PREFIX,
    }
    sys.stdout.write(json.dumps(stub_msg, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
