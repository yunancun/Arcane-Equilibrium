//! Tick-time `ExitFeatures` builder: 每 tick 對活躍持倉組裝快照供 Priority 6
//! 4-Gate 決策消費。
//! Tick-time `ExitFeatures` builder: assembles a snapshot for every live
//! position on each tick for Priority 6 4-Gate decision consumption.
//!
//! TRACK-P-T4-WIRING-1（commit `e95c779`, 2026-04-21）把本檔拉進 runtime
//! 路徑：`tick_pipeline/on_tick.rs` 從硬編碼 `|_| None` 改呼叫此 builder，
//! Priority 6 從此才真正能 fire（之前 runtime 影響 = 0）。
//! TRACK-P-T4-WIRING-1 (commit `e95c779`, 2026-04-21) wired this builder
//! into the runtime path; `tick_pipeline/on_tick.rs` went from hard-coded
//! `|_| None` to calling this builder, making Priority 6 actually fireable
//! (prior runtime impact was 0).

use super::core::ExitFeatures;

/// DUAL-TRACK-EXIT-1 Track P **T4 wiring** (2026-04-21): assemble an
/// `ExitFeatures` snapshot for a **live** position on every tick (mid-life),
/// so the Priority-6 4-Gate `physical_micro_profit_lock` (v1 linear / v2
/// non-linear) can actually fire. Before T4, `tick_pipeline/on_tick.rs`
/// hard-coded `|_| None` and Priority-6 was inert in production (0 fires
/// observed over the full decision_outcomes history; see
/// `memory/project_track_p_runtime_dead.md`).
///
/// Mirrors the close-time derivation inside `tick_pipeline::build_exit_feature_row`
/// so label/feature semantics stay stable between mid-life decision input and
/// post-close DB row, with one difference: no `realized_net_bps` (the position
/// is still open) and no `exit_source` tag (no close happened yet).
///
/// **Purity**: no I/O, no allocation beyond returning `ExitFeatures`. All six
/// derived fields (peak/current pnl, giveback, time-since-peak, entry age;
/// plus the two caller-supplied market-layer fields `atr_pct` and
/// `price_roc_short`; plus `est_net_bps` from the edge-estimates cache) are
/// computed from scalar inputs. Designed for unit tests that don't spin up a
/// full `TickPipeline`.
///
/// **Fail-soft**: any `Option::None` in outputs propagates to the 4-Gate lock
/// which responds with a conservative Hold (pre-T3 semantics). No panic path.
///
/// ### Inputs
/// - `snap`           : snapshot of the live position (not pre-close — any
///                      call time during the position's life). Use
///                      `PaperState::position_exit_snapshot(symbol)`.
/// - `current_price`  : latest tick price for `snap.symbol`.
/// - `atr_pct`        : `price_tracker.compute_atr_pct(symbol)`; `None` until
///                      the tracker has enough samples.
/// - `price_roc_short`: `price_tracker.compute_roc(symbol, 300)` (300 ms
///                      short-horizon ROC); `None` until ≥ 2 samples in window.
/// - `est_net_bps`    : `EdgeEstimates::get_cell(snap.owner_strategy, symbol)
///                      .map(|c| c.shrunk_bps as f32)`; `None` on cache miss.
/// - `ts_ms`          : wall-clock tick timestamp (same as `event.ts_ms`).
///
/// ### Derivations (match `tick_pipeline::build_exit_feature_row` at close)
/// - `peak_pnl_pct`       = `snap.max_favorable_pnl_pct`
/// - `current_pnl_pct`    = side-signed `(current_price − snap.entry_price) /
///                          snap.entry_price × 100`; defensive 0.0 when
///                          `snap.entry_price ≤ 0` or non-finite.
/// - `giveback_atr_norm`  = `(peak_pnl_pct − current_pnl_pct) / atr_pct`,
///                          clamped to `0` when current exceeds peak (fresh
///                          high); `None` when `atr_pct` is `None | ≤ 0 |
///                          non-finite`.
/// - `time_since_peak_ms` = `max(ts_ms_i64 − snap.peak_reached_ts_ms, 0)`;
///                          `None` when `snap.peak_reached_ts_ms == 0`
///                          (legacy snapshot, no peak tracked yet).
/// - `entry_age_secs`     = `(ts_ms − snap.entry_ts_ms) / 1000`; `None` when
///                          `ts_ms < snap.entry_ts_ms` (clock skew guard).
///
/// DUAL-TRACK-EXIT-1 Track P **T4 接線**（2026-04-21）：對活躍持倉每 tick
/// 計算 ExitFeatures 快照，讓 Priority 6 4-Gate `physical_micro_profit_lock`
/// 實際能 fire。T4 接線前 `tick_pipeline/on_tick.rs` 硬編碼 `|_| None`，
/// Priority 6 在生產 0 次觸發（見 `memory/project_track_p_runtime_dead.md`）。
///
/// 衍生規則鏡像 close-time `tick_pipeline::build_exit_feature_row`，保持
/// mid-life 決策輸入與 post-close DB row 語意一致。差異：無 `realized_net_bps`
/// （持倉未平）、無 `exit_source` 標籤（尚未 close）。
///
/// **純函數**：無 I/O / 除回傳 ExitFeatures 外零分配；可脫離 TickPipeline 單測。
/// **Fail-soft**：任一 `Option::None` 透傳至 4-Gate 保守 Hold（pre-T3 語意）。
pub fn build_exit_features_for_tick(
    snap: &crate::paper_state::PositionExitSnapshot,
    current_price: f64,
    atr_pct: Option<f64>,
    price_roc_short: Option<f32>,
    est_net_bps: Option<f32>,
    ts_ms: u64,
) -> ExitFeatures {
    let ts_ms_i64 = ts_ms as i64;

    // current_pnl_pct (side-signed, in %); defensive against entry_price ≤ 0
    // or non-finite (would have failed the open path, but guard anyway).
    // current_pnl_pct（side-signed，單位 %）；entry_price 非正或非有限時回 0
    // （開倉路徑早已過濾,防禦性守衛）。
    let current_pnl_pct = if snap.entry_price > 0.0 && snap.entry_price.is_finite() {
        let side = if snap.is_long { 1.0f64 } else { -1.0f64 };
        ((current_price - snap.entry_price) / snap.entry_price) * 100.0 * side
    } else {
        0.0
    };

    let peak_pnl_pct = snap.max_favorable_pnl_pct;

    // giveback_atr_norm: (peak − current) / atr in %-normalised units; clamped
    // to 0 if current exceeds peak (fresh high mid-life).
    // giveback_atr_norm：(peak − current) / atr；current 超過 peak 時夾回 0。
    let giveback_atr_norm = match atr_pct {
        Some(atr) if atr > 0.0 && atr.is_finite() => {
            let gb = f64::from(peak_pnl_pct) - current_pnl_pct;
            if gb < 0.0 {
                Some(0.0f32)
            } else {
                Some((gb / atr) as f32)
            }
        }
        _ => None,
    };

    // time_since_peak_ms: None when legacy snapshot with peak_reached_ts_ms=0
    // (pre-EXIT-FEATURES-TABLE-1 before update_best_prices_at ran even once),
    // else saturating non-negative delta.
    // time_since_peak_ms：legacy 快照（peak_reached_ts_ms=0）回 None，否則
    // 以飽和非負差值回傳。
    let time_since_peak_ms = if snap.peak_reached_ts_ms > 0 {
        Some((ts_ms_i64 - snap.peak_reached_ts_ms).max(0))
    } else {
        None
    };

    // entry_age_secs: clock-skew guard — None if ts_ms < entry_ts_ms.
    // entry_age_secs：時鐘倒流守衛 — ts_ms < entry_ts_ms 時回 None。
    let entry_age_secs = if ts_ms >= snap.entry_ts_ms {
        Some(((ts_ms - snap.entry_ts_ms) as f32) / 1000.0)
    } else {
        None
    };

    ExitFeatures {
        est_net_bps,
        peak_pnl_pct,
        current_pnl_pct,
        atr_pct,
        giveback_atr_norm,
        time_since_peak_ms,
        price_roc_short,
        entry_age_secs,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    // End-to-end feed tests reach into the v2 consumer in the sibling module.
    // End-to-end feed tests 需呼叫兄弟模組 v2 consumer。
    use super::super::v2::{physical_micro_profit_lock_v2, ExitConfig};
    use super::super::core::PhysicalDecision;

    /// Minimal snapshot helper for builder tests. Side + entry_ts_ms +
    /// peak_reached_ts_ms + entry_price + max_favorable_pnl_pct cover the
    /// full derivation surface; remaining fields are harmless defaults.
    /// Builder 測試用最小 snapshot helper。覆蓋 side / entry_ts_ms /
    /// peak_reached_ts_ms / entry_price / max_favorable_pnl_pct 五個衍生源。
    fn mk_snap(
        is_long: bool,
        entry_price: f64,
        max_favorable_pnl_pct: f32,
        entry_ts_ms: u64,
        peak_reached_ts_ms: i64,
    ) -> crate::paper_state::PositionExitSnapshot {
        crate::paper_state::PositionExitSnapshot {
            symbol: "BTCUSDT".to_string(),
            is_long,
            qty_at_snapshot: 0.1,
            entry_price,
            entry_ts_ms,
            entry_fee: 0.0,
            max_favorable_pnl_pct,
            peak_reached_ts_ms,
            owner_strategy: "bb_breakout".to_string(),
            entry_context_id: String::new(),
            entry_notional: 0.1 * entry_price,
        }
    }

    /// Happy path: long in profit, every input populated. All 8 fields emerge
    /// fully populated; arithmetic of current_pnl / giveback matches hand-computed.
    /// 長倉盈利，每個輸入皆有值；8 欄位完整，current_pnl / giveback 對齊手算值。
    #[test]
    fn test_build_for_tick_long_profit_happy() {
        // Entry 100 → current 103 → +3% side=+1, peak already 4% (price hit 104 earlier).
        let snap = mk_snap(true, 100.0, 4.0, 1_000_000, 1_005_000);
        let f = build_exit_features_for_tick(
            &snap,
            103.0,
            Some(1.5),            // atr_pct
            Some(-0.0012),        // price_roc_short
            Some(12.5),           // est_net_bps
            1_010_000,            // ts_ms
        );
        assert_eq!(f.est_net_bps, Some(12.5));
        assert_eq!(f.peak_pnl_pct, 4.0);
        assert!((f.current_pnl_pct - 3.0).abs() < 1e-9);
        assert_eq!(f.atr_pct, Some(1.5));
        // giveback = (4 - 3) / 1.5 ≈ 0.6667
        let gb = f.giveback_atr_norm.expect("giveback should compute");
        assert!((gb - 0.6667).abs() < 1e-3);
        // time_since_peak_ms = 1_010_000 - 1_005_000 = 5_000
        assert_eq!(f.time_since_peak_ms, Some(5_000));
        assert_eq!(f.price_roc_short, Some(-0.0012));
        // entry_age_secs = (1_010_000 - 1_000_000) / 1000 = 10.0
        assert_eq!(f.entry_age_secs, Some(10.0));
    }

    /// Short-side symmetry: entry 100, current 97 → +3% side=-1 still +3.
    /// 空倉對稱：entry 100 / current 97 → +3% PnL。
    #[test]
    fn test_build_for_tick_short_profit_side_sign() {
        let snap = mk_snap(false, 100.0, 3.5, 0, 100);
        let f = build_exit_features_for_tick(&snap, 97.0, Some(1.0), None, None, 1_000);
        assert!((f.current_pnl_pct - 3.0).abs() < 1e-9);
        assert_eq!(f.peak_pnl_pct, 3.5);
        // giveback = (3.5 - 3.0) / 1.0 = 0.5
        let gb = f.giveback_atr_norm.expect("giveback should compute");
        assert!((gb - 0.5).abs() < 1e-6);
    }

    /// Current above peak (fresh high mid-tick) → giveback clamped to 0,
    /// not a negative number. Guards against `physical_micro_profit_lock_v2`
    /// picking a bogus Lock via a negative giveback accidentally matching.
    /// 當前 PnL 高於 peak（tick 中突破新高）→ giveback 夾回 0，不得為負。
    #[test]
    fn test_build_for_tick_giveback_clamped_to_zero_when_fresh_high() {
        let snap = mk_snap(true, 100.0, 2.0, 0, 100);
        let f = build_exit_features_for_tick(&snap, 105.0, Some(1.0), None, None, 1_000);
        // current_pnl = +5%, peak = +2% → raw giveback = -3 → clamp to 0.
        assert_eq!(f.giveback_atr_norm, Some(0.0));
    }

    /// ATR `None` → giveback `None`; all other deterministic fields still filled.
    /// Ensures 4-Gate Gate 3 sees `atr_pct=None` and Holds rather than panicking.
    /// atr=None → giveback=None；其他確定性欄位仍填值。
    #[test]
    fn test_build_for_tick_atr_none_giveback_none() {
        let snap = mk_snap(true, 100.0, 2.0, 0, 100);
        let f = build_exit_features_for_tick(&snap, 101.0, None, None, Some(7.0), 1_000);
        assert_eq!(f.atr_pct, None);
        assert_eq!(f.giveback_atr_norm, None);
        assert_eq!(f.est_net_bps, Some(7.0));
        assert_eq!(f.peak_pnl_pct, 2.0);
    }

    /// ATR ≤ 0 (pathological tracker output) → giveback `None`, no division.
    /// ATR ≤ 0（病態 tracker 回值）→ giveback=None，不做除法。
    #[test]
    fn test_build_for_tick_atr_nonpositive_giveback_none() {
        let snap = mk_snap(true, 100.0, 2.0, 0, 100);
        let f_zero = build_exit_features_for_tick(&snap, 101.0, Some(0.0), None, None, 1_000);
        assert_eq!(f_zero.giveback_atr_norm, None);
        let f_neg = build_exit_features_for_tick(&snap, 101.0, Some(-0.5), None, None, 1_000);
        assert_eq!(f_neg.giveback_atr_norm, None);
        let f_nan = build_exit_features_for_tick(&snap, 101.0, Some(f64::NAN), None, None, 1_000);
        assert_eq!(f_nan.giveback_atr_norm, None);
    }

    /// Legacy snapshot with `peak_reached_ts_ms == 0` → `time_since_peak_ms`
    /// is `None` (rather than a huge number), matching the close-time
    /// derivation in `tick_pipeline::build_exit_feature_row`.
    /// legacy snapshot（peak_reached_ts_ms=0）→ time_since_peak_ms=None，
    /// 與 close-time 衍生對齊，避免泄漏巨大時間差。
    #[test]
    fn test_build_for_tick_legacy_peak_ts_none() {
        let snap = mk_snap(true, 100.0, 1.0, 0, 0);
        let f = build_exit_features_for_tick(&snap, 100.5, Some(1.0), None, None, 5_000);
        assert_eq!(f.time_since_peak_ms, None);
    }

    /// Non-legacy peak-ts; `time_since_peak_ms` is a non-negative delta even
    /// when `ts_ms == peak_reached_ts_ms` (i.e. same tick as peak hit).
    /// 非 legacy；即便 ts_ms == peak_reached_ts_ms 也回 0（不溢位為負）。
    #[test]
    fn test_build_for_tick_peak_same_tick_zero() {
        let snap = mk_snap(true, 100.0, 1.0, 0, 2_000);
        let f = build_exit_features_for_tick(&snap, 101.0, Some(1.0), None, None, 2_000);
        assert_eq!(f.time_since_peak_ms, Some(0));
    }

    /// Clock skew: `ts_ms < snap.entry_ts_ms` (restored from persisted state
    /// whose entry is after tick ts, or out-of-order event) → `entry_age_secs`
    /// is `None`, not a negative/underflowed value. Gate 2 then Holds.
    /// 時鐘倒流：ts_ms < entry_ts_ms → entry_age_secs=None（非負值/下溢）。
    /// Gate 2 將 Hold。
    #[test]
    fn test_build_for_tick_clock_skew_entry_age_none() {
        let snap = mk_snap(true, 100.0, 1.0, 5_000, 6_000);
        let f = build_exit_features_for_tick(&snap, 101.0, Some(1.0), None, None, 2_000);
        assert_eq!(f.entry_age_secs, None);
    }

    /// Entry price 0 → defensive `current_pnl_pct = 0.0` (no divide-by-zero
    /// explosion). peak_pnl_pct preserved from snap since it's pre-computed.
    /// entry_price=0 → 防禦性 current_pnl_pct=0.0；peak_pnl_pct 沿用 snap。
    #[test]
    fn test_build_for_tick_entry_price_zero_defensive() {
        let snap = mk_snap(true, 0.0, 1.5, 0, 100);
        let f = build_exit_features_for_tick(&snap, 123.0, Some(1.0), None, None, 1_000);
        assert_eq!(f.current_pnl_pct, 0.0);
        assert_eq!(f.peak_pnl_pct, 1.5);
        // giveback = (1.5 - 0) / 1.0 = 1.5
        let gb = f.giveback_atr_norm.expect("giveback should compute");
        assert!((gb - 1.5).abs() < 1e-6);
    }

    /// Non-finite entry price (impossible but defensive) → same fallback.
    /// entry_price 非有限 → fallback current_pnl_pct=0.0。
    #[test]
    fn test_build_for_tick_entry_price_nonfinite_defensive() {
        let snap = mk_snap(true, f64::INFINITY, 1.0, 0, 100);
        let f = build_exit_features_for_tick(&snap, 200.0, Some(1.0), None, None, 1_000);
        assert_eq!(f.current_pnl_pct, 0.0);
    }

    /// Builder output feeds `physical_micro_profit_lock_v2` end-to-end:
    /// constructed snapshot with age ≥ min_hold, peak ≥ min_peak_atr_norm,
    /// giveback crossing the non-linear threshold → Lock via Gate 4a.
    /// Documents the happy-path lock chain the T4 wiring unblocks.
    /// Builder 輸出直接餵 `physical_micro_profit_lock_v2` 端對端：age/peak/giveback
    /// 皆滿足 → Lock via Gate 4a。文件化 T4 接線所解鎖的 happy-path。
    #[test]
    fn test_build_for_tick_feeds_v2_gate4_lock() {
        let cfg = ExitConfig::default();
        // entry_ts=0, ts=120_000 → entry_age_secs=120 >> 30 min_hold.
        // peak=2.5 pct with atr=1 → peak_atr_norm=2.5 > 0.5 min.
        // current=1.2 → giveback_raw=1.3 / atr=1 = 1.3.
        // Threshold @ peak_atr_norm=2.5 = max(1.0 - 0.15*2.5, 0.3) = 0.625.
        // 1.3 > 0.625 → Lock gate4_giveback.
        let snap = mk_snap(true, 100.0, 2.5, 0, 60_000);
        let features = build_exit_features_for_tick(
            &snap,
            101.2,          // +1.2% current
            Some(1.0),      // atr_pct
            Some(-0.001),   // price_roc_short (negative, doesn't matter here)
            Some(10.0),     // est_net_bps > 5.0 floor
            120_000,        // ts_ms = entry_ts + 120s
        );
        assert_eq!(
            physical_micro_profit_lock_v2(&features, &cfg),
            PhysicalDecision::Lock("phys_lock_gate4_giveback".to_string())
        );
    }

    /// Same inputs but edge missing (est_net_bps=None) → v2 Gate 1 conservative
    /// Hold, confirming the fail-soft chain: missing edge → no premature lock.
    /// Same inputs 但 edge 缺失 → Gate 1 保守 Hold，驗證 fail-soft 鏈。
    #[test]
    fn test_build_for_tick_none_edge_feeds_v2_hold() {
        let cfg = ExitConfig::default();
        let snap = mk_snap(true, 100.0, 2.5, 0, 60_000);
        let features = build_exit_features_for_tick(
            &snap,
            101.2,
            Some(1.0),
            Some(-0.001),
            None, // ← edge missing
            120_000,
        );
        assert_eq!(
            physical_micro_profit_lock_v2(&features, &cfg),
            PhysicalDecision::Hold
        );
    }
}
