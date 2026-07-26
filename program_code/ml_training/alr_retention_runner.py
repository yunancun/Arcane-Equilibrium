"""Retention backlog 的獨立入口——S2.4 §2.1 engine-scanner/retention 權限拆分(W2a)。

MODULE_NOTE
模塊用途:承接原 ``alr_event_consumer.process_retention_backlog``(逐位元組等值搬移;
    行為/異常身分不變),讓 retention apply 面(``alr_retention_repository`` 的
    UPDATE/DELETE/INSERT)與 engine-scanner 進程徹底 import-level 分離。
主要函數:process_retention_backlog。
硬邊界(§2.1):engine-scanner 進程(``ml_training.alr_event_consumer``)「絕不可」
    匯入或呼叫本模組與 ``alr_retention_repository``(無 lazy/條件路徑;由
    ``derive_engine_scanner_privilege_split`` 靜態 AST 執法)。retention 源碼留在
    repo,但只能從本入口到達;未來 deleter session 將另建獨立 entrypoint/UID/
    PG role/授權/receipt(本模組僅為過渡期的 user-level P0-B lane 入口)。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# 同一 typed error 類別(定義於 consumer 家族 import-DAG 根;consumer re-export 同物件),
# 搬移前後 caller 捕捉面不變。刻意不經 alr_event_consumer 取得——retention 入口不得反向
# 拉起 engine-scanner 的完整匯入鏈。
from ml_training.alr_candidate_board_events import AlrEventConsumerError
from ml_training.alr_retention_repository import run_retention_pass


# 原 alr_event_consumer._RETENTION_GRACE_SECONDS(等值搬移)。
_RETENTION_GRACE_SECONDS = 900


def process_retention_backlog(connection: Any, *, max_batch: int) -> dict[str, int]:
    """Run one bounded two-phase pass over ALR-owned derived cache only."""
    if isinstance(max_batch, bool) or not isinstance(max_batch, int) or not 1 <= max_batch <= 256:
        raise AlrEventConsumerError("retention_batch_limit_invalid")
    result = run_retention_pass(
        connection,
        now=datetime.now(timezone.utc),
        grace_seconds=_RETENTION_GRACE_SECONDS,
        limit=min(max_batch, 64),
    )
    required = {"scanned", "quarantined", "restored", "swept", "retained", "skipped"}
    if set(result) != required or any(
        isinstance(result[key], bool) or not isinstance(result[key], int) or result[key] < 0
        for key in required
    ):
        raise AlrEventConsumerError("retention_result_invalid")
    return {f"retention_{key}": result[key] for key in required}
