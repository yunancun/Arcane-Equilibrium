#!/usr/bin/env python3
"""production listing capture-only collector — 健康檢查（運行狀態快照）。

MODULE_NOTE:
  模塊用途：彙整 collector 運行健康指標供 operator / 監控判讀（PA 設計 §0.4 G1 驗證
    + DoD #9）。純函數式：吃 daemon 暴露的子狀態（REST last poll / WS connected /
    control liveness / capture window 數 / pg_sink stats）→ 組出三態 verdict + 指標。
  主要類/函數：``build_healthcheck`` — 純函數，回傳 dict（PASS/WARN/FAIL + 指標）。
  依賴：僅標準庫。read-only（不連 PG、不連 WS；只讀傳入的狀態快照）。
  硬邊界（capture-only 旁路）:
    - 零 import 生產模組、零 auth、零 order、零 DB write。只組裝傳入指標。
"""

from __future__ import annotations

import time
from typing import Any, Optional


# 健康閾值（運行語義；非交易硬邊界，純監控判讀）。
# REST poll 超過此久沒成功 → WARN（poll_interval 預設 30s，2 倍餘量）。
_POLL_STALE_WARN_MS = 5 * 60 * 1000
# pg_write 連續 error 達此數 → WARN（資料正落 JSONL fallback 但需 operator 關注）。
_PG_ERROR_WARN_THRESHOLD = 10


def build_healthcheck(
    *,
    started_at_ms: int,
    last_poll_ok_ms: Optional[int],
    ws_connected: bool,
    control_liveness: dict[str, Any],
    active_window_count: int,
    pg_stats: dict[str, Any],
    clock_ms: Any = lambda: int(time.time() * 1000),
) -> dict[str, Any]:
    """組出 collector 健康快照（三態 verdict + 指標）。

    為什麼三態而非二元：listing 窗常無真上市（capture window=0 是正常的，不是 fail）；
    poison 疑似 / poll stale / PG error 才升 WARN；WS 完全斷且無法重連才 FAIL。
    這與探針 verdict「INCONCLUSIVE 非 fail」一致語義。
    """
    now = clock_ms()
    poll_stale_ms = None if last_poll_ok_ms is None else now - last_poll_ok_ms
    poisoned_suspect = bool(control_liveness.get("poisoned_suspect"))
    pg_errors = int(pg_stats.get("pg_write_errors") or 0)
    fallback_rows = int(pg_stats.get("fallback_rows_written") or 0)

    warnings: list[str] = []
    if not ws_connected:
        # WS 未連上是 WARN（daemon 會嘗試重連）；持續斷由 operator 從 journal 判 FAIL。
        warnings.append("ws_not_connected")
    if poisoned_suspect:
        warnings.append("control_poisoned_suspect")
    if poll_stale_ms is not None and poll_stale_ms > _POLL_STALE_WARN_MS:
        warnings.append("rest_poll_stale")
    if pg_errors >= _PG_ERROR_WARN_THRESHOLD:
        warnings.append("pg_write_errors_high")
    if fallback_rows > 0:
        warnings.append("jsonl_fallback_active")

    verdict = "WARN" if warnings else "PASS"

    return {
        "verdict": verdict,
        "warnings": warnings,
        "uptime_ms": now - started_at_ms,
        "last_poll_ok_ms": last_poll_ok_ms,
        "rest_poll_stale_ms": poll_stale_ms,
        "ws_connected": ws_connected,
        "control_tick_count": control_liveness.get("control_tick_count"),
        "control_poisoned_suspect": poisoned_suspect,
        "active_window_count": active_window_count,
        "research_rows_written": pg_stats.get("research_rows_written"),
        "klines_rows_written": pg_stats.get("klines_rows_written"),
        "pg_write_errors": pg_errors,
        "fallback_rows_written": fallback_rows,
        "last_write_ok_ms": pg_stats.get("last_write_ok_ms"),
    }


__all__ = ["build_healthcheck"]
