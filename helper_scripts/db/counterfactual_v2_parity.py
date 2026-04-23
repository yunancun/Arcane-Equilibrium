#!/usr/bin/env python3
"""V2-parity gate evaluation for counterfactual_exit_replay.

MODULE_NOTE (EN): Ports the Rust v2 production path
`rust/openclaw_engine/src/exit_features/v2.rs::physical_micro_profit_lock_v2`
+ `non_linear_giveback_fn` + `ExitConfig` defaults into a pure-Python
pure-fn so the replay script can simulate v2 production behavior
(Gate 1 edge floor → Gate 2 min hold → Gate 3 peak/ATR norm → Gate 4
non-linear giveback) instead of the v1 linear k×ATR approximation.

Addresses FA adversarial finding: v1 linear `giveback_atr_norm >= k`
diverges from v2 `non_linear_giveback_fn` + Gate 1/2/3 sequencing, so
the 7d pooled +223 bps improvement is partially a v1-model artifact.
Per-parameter CLI overrides enable sensitivity analysis (what if
`gate1_floor` were 3 instead of 5? what if `missing_edge_fallback` were
20 instead of 10?).

MODULE_NOTE (中): 將 Rust v2 生產路徑
`rust/openclaw_engine/src/exit_features/v2.rs` 的 `physical_micro_profit_lock_v2`
+ `non_linear_giveback_fn` + `ExitConfig` 預設值 port 成純 Python 純函數，
讓 replay 腳本能模擬 v2 生產行為（Gate 1 淨邊緣底線 → Gate 2 最短持有 →
Gate 3 peak/ATR 比 → Gate 4 非線性 giveback），取代 v1 線性 k×ATR 近似。

回應 FA 對抗性審查：v1 線性 `giveback_atr_norm >= k` 偏離 v2
`non_linear_giveback_fn` + Gate 1/2/3 排序，故 7d 池化 +223 bps 改善
部分是 v1 模型假象。逐參數 CLI 覆寫可做敏感度分析。

Mapping to v2.rs fields (verify in rust/openclaw_engine/src/exit_features/v2.rs):
  gate1_floor              → ExitConfig.min_net_floor_bps       (v2.rs:75, default 5.0)
  missing_edge_fallback    → ExitConfig.missing_edge_fallback_bps (v2.rs:125, default -10.0 in Rust;
                             settings/risk_control_rules/risk_config_demo.toml:152 overrides to 10.0)
  min_hold_secs            → ExitConfig.min_hold_secs            (v2.rs:79, default 30.0)
  min_peak_atr_norm        → ExitConfig.min_peak_atr_norm        (v2.rs:83, default 0.5)
  giveback_base            → ExitConfig.giveback_base            (v2.rs:92, default 1.0)
  giveback_slope           → ExitConfig.giveback_slope           (v2.rs:97, default 0.15)
  giveback_floor           → ExitConfig.giveback_floor           (v2.rs:102, default 0.3)
"""
from __future__ import annotations

import math
from dataclasses import dataclass


# ---- V2 defaults (mirror Rust ExitConfig::default + TOML overrides) ----
# v2 預設值（對齊 Rust ExitConfig::default + TOML 覆寫）

V2_DEFAULT_GATE1_FLOOR_BPS = 5.0
# Rust default = -10.0 (fail-safe Hold). TOML demo override = 10.0 as of
# 2026-04-23 (settings/risk_control_rules/risk_config_demo.toml:152).
# CLI default tracks the TOML runtime value so --v2-parity matches what
# demo engine is actually running; flip via --missing-edge-fallback.
# Rust 預設 -10.0（fail-safe Hold）；TOML demo 2026-04-23 覆寫為 10.0。
# CLI 預設追蹤 TOML runtime 值，確保 --v2-parity 與實際 demo 行為一致。
V2_DEFAULT_MISSING_EDGE_FALLBACK_BPS = 10.0
V2_DEFAULT_MIN_HOLD_SECS = 30.0
V2_DEFAULT_MIN_PEAK_ATR_NORM = 0.5
V2_DEFAULT_GIVEBACK_BASE = 1.0
V2_DEFAULT_GIVEBACK_SLOPE = 0.15
V2_DEFAULT_GIVEBACK_FLOOR = 0.3


@dataclass(frozen=True)
class V2Config:
    """Pure-Python mirror of Rust `ExitConfig` (gate params only).

    Pure-Python 鏡像 Rust `ExitConfig`（只含 gate 參數，無 shadow/stale_peak 等
    replay 不需要的欄位；replay 用不到 Gate 4b stale_peak+ROC 分支因 writer
    未持久化 time_since_peak_ms 的外源 tick stream）。
    """
    gate1_floor_bps: float = V2_DEFAULT_GATE1_FLOOR_BPS
    missing_edge_fallback_bps: float = V2_DEFAULT_MISSING_EDGE_FALLBACK_BPS
    min_hold_secs: float = V2_DEFAULT_MIN_HOLD_SECS
    min_peak_atr_norm: float = V2_DEFAULT_MIN_PEAK_ATR_NORM
    giveback_base: float = V2_DEFAULT_GIVEBACK_BASE
    giveback_slope: float = V2_DEFAULT_GIVEBACK_SLOPE
    giveback_floor: float = V2_DEFAULT_GIVEBACK_FLOOR


def non_linear_giveback_threshold(peak_atr_norm: float, cfg: V2Config) -> float:
    """Pure-Python port of Rust `non_linear_giveback_fn` (v2.rs:258-265).

    Formula:   max(giveback_base - giveback_slope * peak_atr_norm, giveback_floor)
    Guards:    non-finite or negative peak_atr_norm clamps to 0 (returns base),
               matching Rust behavior (never returns NaN).

    公式同 Rust；NaN/負值夾到 0（回傳 base），與 Rust 一致，永不回 NaN。
    """
    if not math.isfinite(peak_atr_norm) or peak_atr_norm < 0.0:
        norm = 0.0
    else:
        norm = peak_atr_norm
    return max(cfg.giveback_base - cfg.giveback_slope * norm, cfg.giveback_floor)


def evaluate_v2_gates(
    est_net_bps: float | None,
    entry_age_secs: float | None,
    peak_pnl_pct: float | None,
    atr_pct: float | None,
    giveback_atr_norm: float | None,
    cfg: V2Config,
    *,
    entry_age_column_present: bool = True,
) -> tuple[bool, str]:
    """Run the 4-gate v2 sequence against one exit-feature row.

    Returns (cf_fired, reason).

    When `entry_age_column_present=False`, Gate 2 is skipped with reason
    suffix ``gate2_skipped_no_column`` so the caller can surface a WARN;
    this handles the forward-compat case where the writer hasn't
    populated `entry_age_secs` yet (current writer does — verified in
    `exit_feature_writer.rs:157`).

    回傳 (cf_fired, reason)。entry_age_column_present=False 時 Gate 2 跳過，
    reason 加 gate2_skipped_no_column 後綴以便 caller 發 WARN（當前 writer
    已持久化 entry_age_secs — 已核驗 exit_feature_writer.rs:157）。

    Does NOT implement Gate 4b (stale_peak_ms + price_roc_short) — replay
    rows carry close-time snapshots, not intra-tick streams, so the 4b
    path's "peak was stale AND decaying" is not reconstructible here.
    Gate 4a (non-linear giveback) is the only Lock path evaluated.

    不實作 Gate 4b（stale_peak_ms + price_roc_short）— replay row 為 close-time
    快照而非 tick stream，4b 的「peak 陳舊且下行」無法重建。只評估 Gate 4a
    （非線性 giveback）作為 Lock 路徑。
    """
    # Gate 1: net-edge floor (with missing-edge fallback for sync-label rows).
    # Gate 1：淨邊緣底線（sync-label 缺 edge 時用 missing_edge_fallback_bps）。
    if est_net_bps is None or not math.isfinite(est_net_bps):
        effective_edge = cfg.missing_edge_fallback_bps
    else:
        effective_edge = float(est_net_bps)
    if effective_edge <= cfg.gate1_floor_bps:
        return (False, "gate1_edge_below_floor")

    # Gate 2: min hold time. Skip gracefully if column absent.
    # Gate 2：最短持有秒數；欄位缺席時跳過。
    if not entry_age_column_present:
        pass  # skipped; fall through
    else:
        if entry_age_secs is None or not math.isfinite(entry_age_secs):
            return (False, "gate2_no_entry_age")
        if float(entry_age_secs) < cfg.min_hold_secs:
            return (False, "gate2_too_fresh")

    # Gate 3: peak / atr_pct >= min_peak_atr_norm.
    # Gate 3：peak 高度（ATR 單位）不足。
    if peak_pnl_pct is None or not math.isfinite(peak_pnl_pct) or peak_pnl_pct <= 0:
        return (False, "gate3_no_peak")
    if atr_pct is None or not math.isfinite(atr_pct) or atr_pct <= 0:
        return (False, "gate3_no_atr")
    peak_atr_norm = float(peak_pnl_pct) / float(atr_pct)
    if peak_atr_norm < cfg.min_peak_atr_norm:
        return (False, "gate3_peak_below_atr_threshold")

    # Gate 4a: non-linear giveback threshold (only Lock path in replay).
    # Gate 4a：非線性 giveback 閾值（replay 中唯一 Lock 路徑）。
    if (
        giveback_atr_norm is None
        or not math.isfinite(giveback_atr_norm)
    ):
        return (False, "gate4a_no_giveback")
    threshold = non_linear_giveback_threshold(peak_atr_norm, cfg)
    suffix = "" if entry_age_column_present else "_gate2_skipped_no_column"
    if float(giveback_atr_norm) >= threshold:
        return (True, f"gate4a_fired{suffix}")
    return (False, f"gate4a_below_threshold{suffix}")
