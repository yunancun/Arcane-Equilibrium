#!/usr/bin/env python3
"""
MODULE_NOTE
模塊用途：P0-LG-3 supervised-live 稽核軌跡 passive-wait healthcheck（check [59]/[60]/[61]）。
          驗 learning.supervised_live_audit（V104）表存在 + 近窗 row 累積，
          作為 supervised-live 部署後「audit writer 是否真在寫」的被動觀察門控。
主要類/函數：
  - HealthStatus：PASS / SKIP / FAIL 三態（對齊既有 healthcheck 語意）。
  - HealthCheckResult：單一 check 結果（name / status / message / detail）。
  - check_supervised_live_audit_table_exists：[59] 表存在性（缺 = V104 未 apply = FAIL）。
  - check_supervised_live_audit_recent_rows：[60] 近窗 row 累積。
  - check_supervised_live_audit_engine_mode_purity：[61] 無 paper engine_mode（LiveDemo 不降級反向驗）。
  - run_all：聚合三 check，CLI 入口。
依賴：psycopg2（與 repo 其他 healthcheck 一致）；DSN 由環境變數提供（不硬編碼路徑）。
硬邊界：
  - fail-loud：表不存在 = FAIL（不 silent pass）；DB 連線失敗 = FAIL（不吞例外）。
  - 為什麼 SKIP 而非 FAIL（無近期 row 時）：supervised-live 未啟用時無事件是預期，
    不可誤報為故障；只有「表不存在」與「出現 paper engine_mode」才是真異常。
  - 不硬編碼 DB 路徑：DSN 從 OPENCLAW_PG_URL / DATABASE_URL 讀（跨平台可遷移）。
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger("checks_supervised_live_audit")

# 近窗門檻：近 N 分鐘內有 row 才視為 writer 活躍（supervised-live 低頻寫入）。
RECENT_WINDOW_MINUTES = 60


class HealthStatus(str, Enum):
    PASS = "PASS"
    SKIP = "SKIP"
    FAIL = "FAIL"


@dataclass
class HealthCheckResult:
    name: str
    status: HealthStatus
    message: str
    detail: dict[str, Any] = field(default_factory=dict)

    def is_failure(self) -> bool:
        return self.status is HealthStatus.FAIL


def _get_dsn() -> str:
    """從環境變數讀 PG DSN。

    為什麼不硬編碼：Linux runtime 與未來 Mac 部署 DSN 不同；production code 禁
    硬編碼機器路徑（CLAUDE §六 / feedback_cross_platform）。
    """
    dsn = os.environ.get("OPENCLAW_PG_URL") or os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError(
            "DSN 未設定：需 OPENCLAW_PG_URL 或 DATABASE_URL 環境變數（不硬編碼）"
        )
    return dsn


def _table_exists(cur) -> bool:
    """learning.supervised_live_audit 表是否存在（V104 是否已 apply）。"""
    cur.execute("SELECT to_regclass('learning.supervised_live_audit') IS NOT NULL")
    return bool(cur.fetchone()[0])


def check_supervised_live_audit_table_exists(cur) -> HealthCheckResult:
    """[59] 表存在性。

    為什麼 fail-loud：表不存在代表 V104 migration 未 apply，supervised audit writer
    runtime 將全數寫入失敗（合規斷鏈）；必 FAIL 提早暴露，不可 silent pass。
    """
    name = "supervised_live_audit_table_exists"
    if not _table_exists(cur):
        return HealthCheckResult(
            name,
            HealthStatus.FAIL,
            "learning.supervised_live_audit 表不存在（V104 migration 未 apply）",
        )
    return HealthCheckResult(
        name, HealthStatus.PASS, "learning.supervised_live_audit 表存在"
    )


def check_supervised_live_audit_recent_rows(cur) -> HealthCheckResult:
    """[60] 近窗 row 累積。

    表存在但近 RECENT_WINDOW_MINUTES 分鐘無 row → SKIP（supervised-live 可能未啟用，
    無事件是預期，不誤報）；有 row → PASS。
    """
    name = "supervised_live_audit_recent_rows"
    if not _table_exists(cur):
        return HealthCheckResult(
            name,
            HealthStatus.FAIL,
            "前置 [59] 失敗：表不存在，無法檢查 row 累積",
        )
    cur.execute(
        "SELECT count(*) FROM learning.supervised_live_audit "
        "WHERE created_at > now() - interval '%s minutes'" % int(RECENT_WINDOW_MINUTES)
    )
    recent = int(cur.fetchone()[0])
    if recent == 0:
        return HealthCheckResult(
            name,
            HealthStatus.SKIP,
            f"近 {RECENT_WINDOW_MINUTES} 分鐘無 audit row（supervised-live 可能未啟用）",
            {"recent_rows": 0, "window_minutes": RECENT_WINDOW_MINUTES},
        )
    return HealthCheckResult(
        name,
        HealthStatus.PASS,
        f"近 {RECENT_WINDOW_MINUTES} 分鐘 {recent} 筆 audit",
        {"recent_rows": recent, "window_minutes": RECENT_WINDOW_MINUTES},
    )


def check_supervised_live_audit_engine_mode_purity(cur) -> HealthCheckResult:
    """[61] engine_mode 純度（無 paper）。

    為什麼是健康指標：supervised-live 是 Live 管線，engine_mode 只應為 live / live_demo。
    若出現 paper（DB CHECK 理應擋下），代表寫入路徑繞過約束或 schema drift → FAIL。
    這是 LiveDemo 不降級硬邊界的反向驗（feedback_live_no_degradation_by_endpoint）。
    """
    name = "supervised_live_audit_engine_mode_purity"
    if not _table_exists(cur):
        return HealthCheckResult(
            name,
            HealthStatus.FAIL,
            "前置 [59] 失敗：表不存在，無法檢查 engine_mode 純度",
        )
    cur.execute(
        "SELECT count(*) FROM learning.supervised_live_audit "
        "WHERE engine_mode NOT IN ('live', 'live_demo')"
    )
    impure = int(cur.fetchone()[0])
    if impure > 0:
        return HealthCheckResult(
            name,
            HealthStatus.FAIL,
            f"偵測 {impure} 筆非 live/live_demo engine_mode（疑繞過 CHECK 或 schema drift）",
            {"impure_rows": impure},
        )
    return HealthCheckResult(
        name,
        HealthStatus.PASS,
        "engine_mode 全為 live / live_demo（LiveDemo 不降級邊界保持）",
        {"impure_rows": 0},
    )


# check 註冊表（id 對齊 spec [59]/[60]/[61]）。
CHECKS: list[tuple[str, Callable[[Any], HealthCheckResult]]] = [
    ("59", check_supervised_live_audit_table_exists),
    ("60", check_supervised_live_audit_recent_rows),
    ("61", check_supervised_live_audit_engine_mode_purity),
]


def run_all() -> list[HealthCheckResult]:
    """連 PG 跑全部 check。連線失敗 fail-loud（不吞例外）。"""
    import psycopg2  # 延遲 import：純語法 self-check 不需安裝 psycopg2

    results: list[HealthCheckResult] = []
    conn = psycopg2.connect(_get_dsn())
    try:
        with conn.cursor() as cur:
            for _cid, fn in CHECKS:
                results.append(fn(cur))
    finally:
        conn.close()
    return results


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    results = run_all()
    any_fail = False
    for r in results:
        logger.info("[%s] %s — %s", r.status.value, r.name, r.message)
        if r.is_failure():
            any_fail = True
    # fail-loud：任一 FAIL → 非零退出碼（CI / passive-wait gate 紅燈）。
    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(main())
