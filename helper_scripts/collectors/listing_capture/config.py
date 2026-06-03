#!/usr/bin/env python3
"""production listing capture-only collector — 配置層（全 env-overridable + clamp）。

MODULE_NOTE:
  模塊用途：listing capture collector 的所有可調常數集中於此，全部 env-overridable
    且保守 clamp（避免極端值打爆 rate budget / 記憶體 / PG）。對齊 PA 設計 §3.4
    capture-window 生命週期（HOLD 72h / quota 20，OQ-6）+ §3.6 真 listing 判據
    （capture_lag SLA 5min）+ §3.1 firehose 殺手（persist_control_ticks）。
  主要類/函數：
    - ``ListingCollectorConfig`` — frozen dataclass，全欄位 env clamp。
    - ``current_collector_config`` — 讀環境變數組出當前配置（保守 clamp）。
  依賴：僅 Python 標準庫（os / dataclasses）。
  硬邊界（capture-only 旁路）:
    - 本檔零 import 生產模組、零 auth、零 order、零 DB。只定義純數值配置。
    - capture window HOLD / quota 是 fail-closed 上限（防 first-detection deadlock：
      window 必有過期、quota 滿不收新 symbol，見 PA 設計 §3.4）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass


# ── COLLECTOR_VERSION：寫進每筆 research row 的 collector_version（provenance）──
# 變更採集語義時 bump，使 PG 端可區分不同版本捕捉的資料。
COLLECTOR_VERSION = "listing_capture_v1.0.0"


def _env_float(name: str, default: float, *, lower: float, upper: float) -> float:
    """讀 float env，解析失敗回 default，並 clamp 到 [lower, upper]。"""
    raw = os.environ.get(name, "").strip()
    try:
        parsed = float(raw) if raw else default
    except ValueError:
        parsed = default
    return max(lower, min(parsed, upper))


def _env_int(name: str, default: int, *, lower: int, upper: int) -> int:
    """讀 int env，解析失敗回 default，並 clamp 到 [lower, upper]。"""
    raw = os.environ.get(name, "").strip()
    try:
        parsed = int(raw) if raw else default
    except ValueError:
        parsed = default
    return max(lower, min(parsed, upper))


@dataclass(frozen=True)
class ListingCollectorConfig:
    """listing capture collector 運行配置（全 env-overridable，保守 clamp）。

    為什麼 frozen：配置在 daemon 啟動時讀一次定型，運行期不變（避免熱路徑競態）；
    需要改配置就重啟 daemon（systemd restart），讓配置變更顯式可追。
    """

    # ── REST 輪詢（沿用 gate_b_rest 的 env 名 + clamp 口徑，但 collector 有自己的預設）──
    poll_interval_seconds: float
    rest_max_attempts: int
    rest_base_backoff_ms: int
    rest_timeout_seconds: float
    rest_limit: int

    # ── capture-window 生命週期（OQ-6；防 first-detection deadlock）──
    # HOLD：symbol 進 capture window 後保留訂閱多久（過期自動退訂）。預設 72h 覆蓋
    # pump-fade 研究窗（QC 用首 6h，留充裕餘量）。
    capture_hold_hours: float
    # quota：同時 capture 的 symbol 硬上限（fail-closed；滿了不收新 symbol，等舊的過期）。
    # 預設 20 遠超實際同時上市數（~6-10/月）。
    max_concurrent_symbols: int

    # ── capture_lag SLA（真 listing 判據之一，PA 設計 §3.6）──
    # 首筆 publicTrade 距 launchTime ≤ 此值視為 PASS_CAPTURE。預設 5min（與探針一致）。
    capture_lag_sla_ms: int

    # ── poison 隔離（forced reconnect on control stale，PA 設計 §3.1）──
    # control 哨兵多久沒 tick 視為疑似毒化 → daemon 主動重連 WS。
    control_stale_reconnect_ms: int
    # 兩次 forced reconnect 之間最小間隔（防 reconnect thrash）。
    reconnect_min_interval_ms: int

    # ── PG 寫（pg_sink）──
    # PG 寫失敗重試次數（重試耗盡後落 JSONL fallback + 記 healthcheck error，WS 繼續收）。
    pg_write_max_attempts: int
    # 批次大小（execute_batch page_size）。
    pg_batch_size: int

    # ── G1 firehose 殺手（PA 設計 §3.1）──
    # production 模式 control tick 不落盤（只更新 in-memory liveness）。預設 False
    # = collector 行為（探針預設 True 維持逐筆 control 落盤，向後相容）。
    persist_control_ticks: bool

    # ── restart-resume（PA 設計 §3.4 / G4）──
    # daemon 啟動時從 PG 讀「最近 N 小時內有事件」的 symbol resume capture window。
    # 應 ≥ capture_hold_hours（否則漏掉仍在 window 內但事件較舊的 symbol）。
    resume_lookback_hours: float


def current_collector_config() -> ListingCollectorConfig:
    """讀環境變數組出當前 collector 配置（保守 clamp）。

    為什麼集中在此：daemon / pg_sink / capture_state 都讀同一份配置，集中保證
    clamp 口徑一致（如 poll_interval 與 gate_b_rest 對齊 5-300s）。
    """
    capture_hold_hours = _env_float(
        "OPENCLAW_LISTING_CAPTURE_HOLD_HOURS", 72.0, lower=1.0, upper=720.0
    )
    return ListingCollectorConfig(
        # REST 輪詢（與 gate_b_rest.current_rest_poll_policy clamp 口徑一致）
        poll_interval_seconds=_env_float(
            "OPENCLAW_LISTING_COLLECTOR_POLL_INTERVAL_S", 30.0, lower=5.0, upper=300.0
        ),
        rest_max_attempts=_env_int(
            "OPENCLAW_LISTING_COLLECTOR_REST_RETRY_MAX_ATTEMPTS", 3, lower=1, upper=5
        ),
        rest_base_backoff_ms=_env_int(
            "OPENCLAW_LISTING_COLLECTOR_REST_BACKOFF_BASE_MS", 250, lower=50, upper=2_000
        ),
        rest_timeout_seconds=_env_float(
            "OPENCLAW_LISTING_COLLECTOR_REST_TIMEOUT_S", 12.0, lower=2.0, upper=30.0
        ),
        rest_limit=_env_int(
            "OPENCLAW_LISTING_COLLECTOR_REST_LIMIT", 1000, lower=1, upper=1000
        ),
        # capture-window 生命週期（OQ-6）
        capture_hold_hours=capture_hold_hours,
        max_concurrent_symbols=_env_int(
            "OPENCLAW_LISTING_CAPTURE_MAX_CONCURRENT", 20, lower=1, upper=100
        ),
        # capture_lag SLA（PA §3.6；預設 300_000ms = 5min）
        capture_lag_sla_ms=_env_int(
            "OPENCLAW_LISTING_CAPTURE_LAG_SLA_MS", 5 * 60 * 1000,
            lower=1_000, upper=24 * 60 * 60 * 1000
        ),
        # poison forced-reconnect（PA §3.1）
        control_stale_reconnect_ms=_env_int(
            "OPENCLAW_LISTING_COLLECTOR_CONTROL_STALE_MS", 60 * 1000,
            lower=10_000, upper=600_000
        ),
        reconnect_min_interval_ms=_env_int(
            "OPENCLAW_LISTING_COLLECTOR_RECONNECT_MIN_INTERVAL_MS", 30 * 1000,
            lower=5_000, upper=600_000
        ),
        # PG 寫
        pg_write_max_attempts=_env_int(
            "OPENCLAW_LISTING_COLLECTOR_PG_RETRY_MAX_ATTEMPTS", 3, lower=1, upper=10
        ),
        pg_batch_size=_env_int(
            "OPENCLAW_LISTING_COLLECTOR_PG_BATCH_SIZE", 500, lower=1, upper=5_000
        ),
        # G1 firehose 殺手（collector 預設 False = control tick 不落盤）
        persist_control_ticks=os.environ.get(
            "OPENCLAW_LISTING_COLLECTOR_PERSIST_CONTROL_TICKS", "0"
        ).strip().lower() in ("1", "true", "yes"),
        # restart-resume：預設等於 HOLD（覆蓋仍在 window 內的所有 symbol）
        resume_lookback_hours=_env_float(
            "OPENCLAW_LISTING_COLLECTOR_RESUME_LOOKBACK_HOURS",
            capture_hold_hours, lower=1.0, upper=720.0
        ),
    )


__all__ = [
    "COLLECTOR_VERSION",
    "ListingCollectorConfig",
    "current_collector_config",
]
