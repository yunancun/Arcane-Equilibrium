//! Order admission and tick-level position risk checks (ARCH-RC1).
//! 訂單准入及 tick 級持倉風控檢查（ARCH-RC1）。
//!
//! MODULE_NOTE (中文):
//!   1C-1 從 openclaw_core::risk::checks 遷移過來，改讀新 RiskConfig。
//!   - 熱路徑使用 `&RiskConfig` lock-free 快照讀（ArcSwap）
//!   - cost_edge_max_ratio 為跨 Config 讀（契約允許執行時讀，禁止校準耦合），
//!     由 caller 從 BudgetConfig.attention_tax.cost_edge_max_ratio 取出後傳入
//!   - 風控檢查 fail-closed — 未知狀態 → 拒絕
//!
//! MODULE_NOTE (English):
//!   Migrated from openclaw_core::risk::checks in 1C-1; reads new RiskConfig.
//!   - Hot path uses `&RiskConfig` via ArcSwap lock-free snapshot
//!   - cost_edge_max_ratio is a cross-Config read (contract allows runtime reads,
//!     only forbids calibration coupling) — passed in by caller from
//!     BudgetConfig.attention_tax.cost_edge_max_ratio
//!   - Risk checks are fail-closed — unknown state → reject

use crate::config::risk_config::PhysLockConfig;
use crate::config::RiskConfig;
use crate::exit_features::{ExitFeatures, PhysicalDecision};
use openclaw_core::risk::{compute_dynamic_stop_pct, regime_multipliers};

// ---------------------------------------------------------------------------
// Order admission / 訂單准入
// ---------------------------------------------------------------------------

/// Result of an order admission check / 訂單准入檢查結果
#[derive(Debug, Clone)]
pub struct PositionCheck {
    pub allowed: bool,
    pub reason: String,
}

impl PositionCheck {
    fn allow() -> Self {
        Self {
            allowed: true,
            reason: "passed all checks".into(),
        }
    }
    fn reject(reason: String) -> Self {
        Self {
            allowed: false,
            reason,
        }
    }
}

/// Check whether a new order should be allowed, based on position sizing and risk limits.
/// 基於持倉大小和風控限制，檢查是否應允許新訂單。
///
/// Priority order: daily loss → leverage → single position size → total exposure → correlated.
/// 優先級：日損 → 槓桿 → 單一持倉 → 總曝險 → 相關曝險。
/// Reducing orders always pass (原則 #5: 生存 > 利潤).
#[allow(clippy::too_many_arguments)]
pub fn check_order_allowed(
    qty: f64,
    price: f64,
    balance: f64,
    current_exposure_pct: f64,
    correlated_exposure_pct: f64,
    leverage: f64,
    daily_loss_pct: f64,
    is_reducing: bool,
    config: &RiskConfig,
) -> PositionCheck {
    if is_reducing {
        return PositionCheck::allow();
    }

    let limits = &config.limits;

    if daily_loss_pct >= limits.daily_loss_max_pct {
        return PositionCheck::reject(format!(
            "daily loss {:.2}% >= limit {:.2}%",
            daily_loss_pct, limits.daily_loss_max_pct
        ));
    }

    if leverage > limits.leverage_max {
        return PositionCheck::reject(format!(
            "leverage {:.1}x > limit {:.1}x",
            leverage, limits.leverage_max
        ));
    }

    if balance > 0.0 {
        let position_value = qty * price;
        let position_pct = position_value / balance * 100.0;
        if position_pct > limits.position_size_max_pct {
            return PositionCheck::reject(format!(
                "position {:.2}% > limit {:.2}%",
                position_pct, limits.position_size_max_pct
            ));
        }
    }

    if current_exposure_pct >= limits.total_exposure_max_pct {
        return PositionCheck::reject(format!(
            "total exposure {:.2}% >= limit {:.2}%",
            current_exposure_pct, limits.total_exposure_max_pct
        ));
    }

    if correlated_exposure_pct >= limits.correlated_exposure_max_pct {
        return PositionCheck::reject(format!(
            "correlated exposure {:.2}% >= limit {:.2}%",
            correlated_exposure_pct, limits.correlated_exposure_max_pct
        ));
    }

    PositionCheck::allow()
}

// ---------------------------------------------------------------------------
// Tick-level position checks / Tick 級持倉檢查
// ---------------------------------------------------------------------------

/// Action to take after a tick-level risk check / Tick 級風控檢查後的動作
#[derive(Debug, Clone)]
pub enum RiskAction {
    Hold,
    ClosePosition(String),
    HaltSession(String),
    SetCooldown(u64),
}

/// Tick-level risk check for a single position. See priority order in MODULE_NOTE.
/// Tick 級持倉風控檢查。優先級：hard stop → dyn stop → TP → trailing → time → PHYS-LOCK → drawdown → consec loss → daily loss。
///
/// DUAL-TRACK-EXIT-1 Track P T3: Priority 6 is now `physical_micro_profit_lock`
/// (PHYS-LOCK) driven by an `ExitFeatures` snapshot when supplied. When
/// `exit_features` is `None` (bootstrap / T4 not yet wired), Priority 6 is inert
/// and behaviour is identical to "COST EDGE disabled" — i.e. the legacy
/// cost_ratio / cost_edge_max_ratio / min_profit_to_close_pct parameters are
/// silently ignored. They are kept on the ABI to avoid a caller storm until
/// T4 lands and ExitFeatures snapshots are always populated.
///
/// DUAL-TRACK-EXIT-1 Track P T3：優先級 6 替換為 `physical_micro_profit_lock`。
/// 當 `exit_features` 為 None 時（bootstrap / T4 尚未接線），此 gate 不觸發，
/// 舊 cost_ratio/cost_edge_max_ratio/min_profit_to_close_pct 參數保留在 ABI
/// 但被忽略，避免 caller 爆炸。
#[allow(clippy::too_many_arguments)]
pub fn check_position_on_tick(
    pnl_pct: f64,
    peak_pnl_pct: f64,
    holding_hours: f64,
    cost_ratio: f64,
    regime: &str,
    atr_pct: Option<f64>,
    symbol: &str,
    entry_ts_ms: u64,
    consecutive_losses: u32,
    daily_loss_pct: f64,
    session_drawdown_pct: f64,
    cost_edge_max_ratio: f64,
    min_profit_to_close_pct: f64,
    exit_features: Option<&ExitFeatures>,
    config: &RiskConfig,
) -> RiskAction {
    // Legacy COST EDGE inputs retained on ABI for T4; silence unused-param warnings.
    // T3：COST EDGE 相關參數保留 ABI，等 T4 接 ExitFeatures 真實值。
    let _ = (cost_ratio, cost_edge_max_ratio, min_profit_to_close_pct);
    let rm = regime_multipliers(regime);
    let limits = &config.limits;
    let agent = &config.agent;
    let dyn_cfg = &config.dynamic_stop;

    // 1. Hard stop
    if pnl_pct <= -limits.stop_loss_max_pct {
        return RiskAction::ClosePosition(format!(
            "HARD STOP: pnl {:.2}% <= -{:.2}%",
            pnl_pct, limits.stop_loss_max_pct
        ));
    }

    // 2. Dynamic stop — pass atr_stop_mult from DynamicStop config (was hardcoded 1.5 in core).
    // 動態止損 — 傳入 DynamicStop.atr_stop_mult（原本在 core 內寫死 1.5）。
    let dyn_stop = compute_dynamic_stop_pct(
        limits.stop_loss_max_pct * dyn_cfg.base_ratio,
        atr_pct,
        symbol,
        entry_ts_ms,
        regime,
        limits.stop_loss_max_pct,
        dyn_cfg.cap_ratio,
        dyn_cfg.atr_stop_mult,
    );
    if pnl_pct <= -dyn_stop {
        return RiskAction::ClosePosition(format!(
            "DYNAMIC STOP: pnl {:.2}% <= -{:.2}% (regime={}, atr={:?})",
            pnl_pct, dyn_stop, regime, atr_pct
        ));
    }

    // 3. Take profit (if enforced)
    if limits.take_profit_enforced {
        let tp_target = limits.take_profit_max_pct * rm.tp;
        if pnl_pct >= tp_target {
            return RiskAction::ClosePosition(format!(
                "TAKE PROFIT: pnl {:.2}% >= {:.2}% (regime={})",
                pnl_pct, tp_target, regime
            ));
        }
    }

    // 4. Trailing stop
    if agent.trailing_enabled && peak_pnl_pct >= agent.trailing_activation_pct {
        let drawdown_from_peak = peak_pnl_pct - pnl_pct;
        let min_locked_profit = dyn_stop * dyn_cfg.trailing_min_rr;
        if drawdown_from_peak >= agent.trailing_distance_pct && pnl_pct >= min_locked_profit {
            return RiskAction::ClosePosition(format!(
                "TRAILING STOP: peak {:.2}% - current {:.2}% = {:.2}% >= distance {:.2}% (locked {:.2}% >= floor {:.2}%)",
                peak_pnl_pct, pnl_pct, drawdown_from_peak,
                agent.trailing_distance_pct, pnl_pct, min_locked_profit
            ));
        }
    }

    // 5. Time stop
    let max_hours = limits.holding_hours_max * rm.time;
    if holding_hours >= max_hours {
        return RiskAction::ClosePosition(format!(
            "TIME STOP: held {:.1}h >= limit {:.1}h (regime={})",
            holding_hours, max_hours, regime
        ));
    }

    // 6. PHYS-LOCK (DUAL-TRACK-EXIT-1 Track P T3) — physical-layer micro-profit lock.
    // Replaces legacy COST EDGE; only fires when an ExitFeatures snapshot is
    // supplied (i.e. T4 has wired real features into the per-position closure).
    // Active emitted reasons: `phys_lock_gate4_giveback`, `phys_lock_gate4_stale_roc_neg`.
    // Historical reason `phys_lock_gate1_low_edge` retained for backward-compat
    // parsing (strip_phys_lock_prefix + Python parse_exit_tag) — no longer emitted
    // after GATE1-REVERSAL-1 (2026-04-21); Gate 1 now returns Hold to align with
    // DUAL-TRACK-EXIT-1 design intent "prevent micro-profit premature lock".
    //
    // 6. PHYS-LOCK（DUAL-TRACK-EXIT-1 Track P T3）：物理層微利鎖定，取代 COST EDGE。
    // 僅在 caller 傳入有效 ExitFeatures 時觸發；T4 接線前為 no-op。
    // 當前 emit：gate4_giveback / gate4_stale_roc_neg；`phys_lock_gate1_low_edge`
    // 歷史標籤保留下游解析向後兼容（GATE1-REVERSAL-1 後 v1 不再 emit，Gate 1 改 Hold
    // 對齊設計意圖「防止剛有大於 fee 的微利就套離場」）。
    if let Some(features) = exit_features {
        if let PhysicalDecision::Lock(reason) =
            physical_micro_profit_lock(features, &config.phys_lock)
        {
            return RiskAction::ClosePosition(format!("risk_close:{}", reason));
        }
    }
    // DEPRECATED (DUAL-TRACK-EXIT-1 Track P T3): legacy COST EDGE gate block
    // retained here as comment for historical reference only. Logic replaced
    // by PHYS-LOCK above. Do not re-enable without design review — the 4-gate
    // ExitFeatures-driven lock is strictly more conservative than the old
    // cost_ratio heuristic. See docs/references/2026-04-19--dual_track_exit_1_spec.md.
    //
    // // if cost_ratio >= cost_edge_max_ratio
    // //     && pnl_pct >= min_profit_to_close_pct
    // //     && pnl_pct > 0.0
    // // {
    // //     return RiskAction::ClosePosition(format!(
    // //         "COST EDGE: ratio {:.2} >= {:.2}, pnl {:.2}% >= min_profit {:.2}% ...",
    // //         cost_ratio, cost_edge_max_ratio, pnl_pct, min_profit_to_close_pct
    // //     ));
    // // }

    // 7. Session drawdown
    if session_drawdown_pct >= limits.session_drawdown_max_pct {
        return RiskAction::HaltSession(format!(
            "SESSION DRAWDOWN: {:.2}% >= {:.2}%",
            session_drawdown_pct, limits.session_drawdown_max_pct
        ));
    }

    // 8. Consecutive losses cooldown
    if consecutive_losses >= limits.consec_loss_cooldown_count {
        let cooldown_ms = u64::from(limits.consec_loss_cooldown_min) * 60 * 1000;
        return RiskAction::SetCooldown(cooldown_ms);
    }

    // 9. Daily loss limit
    if daily_loss_pct >= limits.daily_loss_max_pct {
        return RiskAction::HaltSession(format!(
            "DAILY LOSS: {:.2}% >= {:.2}%",
            daily_loss_pct, limits.daily_loss_max_pct
        ));
    }

    RiskAction::Hold
}

// ---------------------------------------------------------------------------
// PHYS-LOCK — DUAL-TRACK-EXIT-1 Track P T3 / 物理層微利鎖定
// ---------------------------------------------------------------------------

/// 4-gate sequential filter that decides whether a winning position should
/// lock in its current micro-profit. Conservative semantics: any required
/// Option::None returns Hold. Lock is reached **only** via Gate 4 (trailing)
/// — Gate 1-3 are pass-through guards (Hold early-return on failure).
///
/// Gates in order:
///   1. **Edge floor** — `est_net_bps < cfg.min_net_floor_bps` → Hold
///      (prevents micro-profit premature lock; design intent per DUAL-TRACK-EXIT-1).
///      `None` → Hold (unknown edge, conservative).
///   2. **Min hold** — `entry_age_secs < cfg.min_hold_secs` → Hold (too fresh).
///      `None` → Hold (unknown age, conservative).
///   3. **Peak/ATR threshold** — `peak_pnl_pct < cfg.min_peak_atr_norm × atr_pct`
///      → Hold (peak not meaningful yet). `atr_pct: None` → Hold.
///   4. **Lock trigger (only Lock path)** — either
///      a. giveback `>= cfg.giveback_atr_norm_threshold`
///         → Lock (`phys_lock_gate4_giveback`)
///      b. `time_since_peak_ms > cfg.stale_peak_ms` AND `price_roc_short < 0`
///         → Lock (`phys_lock_gate4_stale_roc_neg`)
///      else → Hold.
///
/// 4-gate 依序過濾：edge 底 → 最短持有 → peak/ATR 閾值 → giveback 或
/// stale-peak+negROC。保守：任一所需 Option=None 回 Hold；Gate 1-3 僅 Hold 路徑，
/// Lock 唯一合法路徑 = Gate 4 trailing（設計意圖：防止微利即套離場，追求最高單筆
/// close 盈利）。GATE1-REVERSAL-1 (2026-04-21)：Gate 1 由舊「edge<floor → Lock」
/// 反轉為 Hold，與 `exit_features::physical_micro_profit_lock_v2` 對齊。
pub fn physical_micro_profit_lock(
    f: &ExitFeatures,
    cfg: &PhysLockConfig,
) -> PhysicalDecision {
    // Gate 1: edge floor — conservative Hold when edge insufficient.
    // Gate 1：淨邊緣底線 — edge 不足時保守 Hold（防止微利即套離場）。
    // GATE1-REVERSAL-1 (2026-04-21): `< floor → Lock` → `< floor → Hold`
    // 對齊 DUAL-TRACK-EXIT-1 設計 + exit_features::physical_micro_profit_lock_v2.
    match f.est_net_bps {
        Some(edge) if edge < cfg.min_net_floor_bps => {
            return PhysicalDecision::Hold;
        }
        Some(_) => {} // edge above floor → proceed to later gates
        None => return PhysicalDecision::Hold, // unknown edge → conservative Hold
    }

    // Gate 2: min hold seconds.
    let age_secs = match f.entry_age_secs {
        Some(a) => a,
        None => return PhysicalDecision::Hold,
    };
    if age_secs < cfg.min_hold_secs {
        return PhysicalDecision::Hold;
    }

    // Gate 3: peak/ATR threshold — peak_pnl_pct must exceed N × ATR%.
    let atr = match f.atr_pct {
        Some(a) if a > 0.0 => a,
        _ => return PhysicalDecision::Hold,
    };
    let required_peak = f64::from(cfg.min_peak_atr_norm) * atr;
    if f64::from(f.peak_pnl_pct) < required_peak {
        return PhysicalDecision::Hold;
    }

    // Gate 4a: giveback ≥ threshold → lock.
    if let Some(gb) = f.giveback_atr_norm {
        if gb >= cfg.giveback_atr_norm_threshold {
            return PhysicalDecision::Lock("phys_lock_gate4_giveback".to_string());
        }
    }

    // Gate 4b: stale peak + negative short-ROC → lock.
    match (f.time_since_peak_ms, f.price_roc_short) {
        (Some(dt), Some(roc)) if dt > cfg.stale_peak_ms && roc < 0.0 => {
            PhysicalDecision::Lock("phys_lock_gate4_stale_roc_neg".to_string())
        }
        _ => PhysicalDecision::Hold,
    }
}

// ===========================================================================
// Tests / 測試
// ===========================================================================
#[cfg(test)]
mod tests {
    use super::*;

    /// MICRO-PROFIT-FIX-1 (2026-04-17): default lowered to 0.2. Tests that
    /// exercise the COST EDGE gate pick pnl / ratio that satisfy both
    /// `cost_ratio >= COST_EDGE_DEFAULT` and `pnl_pct >= MIN_PROFIT_DEFAULT`.
    /// MICRO-PROFIT-FIX-1：default 降到 0.2；cost-edge 相關測試需 ratio 與 pnl 雙條件達標。
    const COST_EDGE_DEFAULT: f64 = 0.2;
    /// MICRO-PROFIT-FIX-1: default min_profit_to_close_pct (%).
    const MIN_PROFIT_DEFAULT: f64 = 0.3;

    fn default_config() -> RiskConfig {
        RiskConfig::default()
    }

    // -- check_order_allowed tests --

    #[test]
    fn test_order_reducing_always_passes() {
        let cfg = default_config();
        let res = check_order_allowed(100.0, 50.0, 1000.0, 95.0, 70.0, 50.0, 10.0, true, &cfg);
        assert!(
            res.allowed,
            "reducing order must always pass: {}",
            res.reason
        );
    }

    #[test]
    fn test_order_daily_loss_exceeded() {
        let cfg = default_config();
        let res = check_order_allowed(1.0, 100.0, 10000.0, 10.0, 10.0, 5.0, 5.0, false, &cfg);
        assert!(!res.allowed);
        assert!(res.reason.contains("daily loss"));
    }

    #[test]
    fn test_order_leverage_exceeded() {
        let cfg = default_config();
        let res = check_order_allowed(1.0, 100.0, 10000.0, 10.0, 10.0, 25.0, 0.0, false, &cfg);
        assert!(!res.allowed);
        assert!(res.reason.contains("leverage"));
    }

    #[test]
    fn test_order_single_position_exceeded() {
        let cfg = default_config();
        // qty * price / balance = 30*100/10000 = 30% > default 20%
        let res = check_order_allowed(30.0, 100.0, 10000.0, 10.0, 10.0, 5.0, 0.0, false, &cfg);
        assert!(!res.allowed);
        assert!(res.reason.contains("position"));
    }

    #[test]
    fn test_order_total_exposure_exceeded() {
        let cfg = default_config();
        let res = check_order_allowed(1.0, 100.0, 10000.0, 100.0, 10.0, 5.0, 0.0, false, &cfg);
        assert!(!res.allowed);
        assert!(res.reason.contains("total exposure"));
    }

    #[test]
    fn test_order_correlated_exposure_exceeded() {
        let cfg = default_config();
        let res = check_order_allowed(1.0, 100.0, 10000.0, 50.0, 60.0, 5.0, 0.0, false, &cfg);
        assert!(!res.allowed);
        assert!(res.reason.contains("correlated"));
    }

    #[test]
    fn test_order_all_within_limits() {
        let cfg = default_config();
        let res = check_order_allowed(1.0, 100.0, 10000.0, 30.0, 20.0, 5.0, 1.0, false, &cfg);
        assert!(res.allowed, "should pass: {}", res.reason);
    }

    #[test]
    fn test_order_zero_balance_position_check() {
        let cfg = default_config();
        let res = check_order_allowed(1.0, 100.0, 0.0, 0.0, 0.0, 5.0, 0.0, false, &cfg);
        assert!(res.allowed, "zero balance should skip position check");
    }

    // -- check_position_on_tick tests --

    fn call_tick(
        pnl: f64,
        peak: f64,
        hold: f64,
        cost: f64,
        regime: &str,
        atr: Option<f64>,
        consec: u32,
        daily: f64,
        dd: f64,
        cfg: &RiskConfig,
    ) -> RiskAction {
        check_position_on_tick(
            pnl,
            peak,
            hold,
            cost,
            regime,
            atr,
            "BTCUSDT",
            1000,
            consec,
            daily,
            dd,
            COST_EDGE_DEFAULT,
            MIN_PROFIT_DEFAULT,
            None, // exit_features — PHYS-LOCK inert / PHYS-LOCK 不觸發
            cfg,
        )
    }

    /// Variant that exercises the PHYS-LOCK Priority 6 gate by threading an
    /// `ExitFeatures` snapshot through. Other args mirror `call_tick`.
    /// 測試 PHYS-LOCK 用變體，其他參數與 `call_tick` 一致。
    #[allow(clippy::too_many_arguments)]
    fn call_tick_with_features(
        pnl: f64,
        peak: f64,
        hold: f64,
        cost: f64,
        regime: &str,
        atr: Option<f64>,
        consec: u32,
        daily: f64,
        dd: f64,
        features: &ExitFeatures,
        cfg: &RiskConfig,
    ) -> RiskAction {
        check_position_on_tick(
            pnl,
            peak,
            hold,
            cost,
            regime,
            atr,
            "BTCUSDT",
            1000,
            consec,
            daily,
            dd,
            COST_EDGE_DEFAULT,
            MIN_PROFIT_DEFAULT,
            Some(features),
            cfg,
        )
    }

    /// Build an ExitFeatures snapshot with all-pass values for the PHYS-LOCK
    /// gates (caller can then override a single field to test a specific gate).
    /// 構造全通 ExitFeatures；caller 可針對某個 gate 覆蓋單一欄位。
    fn mk_features() -> ExitFeatures {
        ExitFeatures {
            est_net_bps: Some(50.0),          // well above 5.0 floor
            peak_pnl_pct: 5.0,                // well above 0.5×ATR
            current_pnl_pct: 3.0,
            atr_pct: Some(1.0),               // 1% ATR
            giveback_atr_norm: Some(0.0),     // no giveback yet
            time_since_peak_ms: Some(0),      // peak just reached
            price_roc_short: Some(0.0),
            entry_age_secs: Some(120.0),      // past min_hold
        }
    }

    #[test]
    fn test_tick_hard_stop() {
        let cfg = default_config();
        let action = call_tick(
            -5.0,
            0.0,
            1.0,
            0.0,
            "trending",
            Some(1.0),
            0,
            0.0,
            0.0,
            &cfg,
        );
        assert!(matches!(action, RiskAction::ClosePosition(ref r) if r.contains("HARD STOP")));
    }

    #[test]
    fn test_tick_dynamic_stop() {
        // Default atr_stop_mult=2.0, hard_stop=5%, base_ratio=0.6, cap_ratio=0.8:
        //   base=3%, cap=4%, ATR=2% → atr_stop=4% → effective=4%
        //   max dyn_stop with anti-cluster (+15%) = 4.6%; use -4.7 to guarantee trigger.
        // 預設 atr_stop_mult=2.0：atr_stop=4%，最大 dyn_stop≈4.6%，用 -4.7% 確保觸發。
        let cfg = default_config();
        let action = call_tick(
            -4.7,
            0.0,
            1.0,
            0.0,
            "trending",
            Some(2.0),
            0,
            0.0,
            0.0,
            &cfg,
        );
        assert!(
            matches!(action, RiskAction::ClosePosition(ref r) if r.contains("DYNAMIC STOP")),
            "expected dynamic stop, got {:?}",
            action
        );
    }

    #[test]
    fn test_tick_take_profit_disabled() {
        let cfg = default_config(); // take_profit_enforced = false by default
        let action = call_tick(
            25.0,
            25.0,
            1.0,
            0.0,
            "trending",
            Some(1.0),
            0,
            0.0,
            0.0,
            &cfg,
        );
        assert!(
            !matches!(action, RiskAction::ClosePosition(ref r) if r.contains("TAKE PROFIT")),
            "TP should be disabled"
        );
    }

    #[test]
    fn test_tick_take_profit_enabled() {
        let mut cfg = default_config();
        cfg.limits.take_profit_enforced = true;
        cfg.limits.take_profit_max_pct = 10.0;
        // trending TP mult = 1.5 -> target = 15%
        let action = call_tick(
            16.0,
            16.0,
            1.0,
            0.0,
            "trending",
            Some(1.0),
            0,
            0.0,
            0.0,
            &cfg,
        );
        assert!(matches!(action, RiskAction::ClosePosition(ref r) if r.contains("TAKE PROFIT")));
    }

    #[test]
    fn test_tick_trailing_stop() {
        let cfg = default_config();
        // peak=3 current=2 drawdown=1 >= distance=0.8; locked 2% > 3*0.5=1.5 floor
        let action = call_tick(2.0, 3.0, 1.0, 0.0, "trending", Some(1.0), 0, 0.0, 0.0, &cfg);
        assert!(matches!(action, RiskAction::ClosePosition(ref r) if r.contains("TRAILING")));
    }

    #[test]
    fn test_tick_trailing_stop_not_activated() {
        let cfg = default_config();
        let action = call_tick(0.1, 0.5, 1.0, 0.0, "trending", Some(1.0), 0, 0.0, 0.0, &cfg);
        assert!(
            !matches!(action, RiskAction::ClosePosition(ref r) if r.contains("TRAILING")),
            "trailing should not trigger below activation"
        );
    }

    #[test]
    fn test_tick_time_stop() {
        let cfg = default_config();
        // max_holding 72 * trending time 1.5 = 108h
        let action = call_tick(
            1.0,
            1.0,
            110.0,
            0.0,
            "trending",
            Some(1.0),
            0,
            0.0,
            0.0,
            &cfg,
        );
        assert!(matches!(action, RiskAction::ClosePosition(ref r) if r.contains("TIME STOP")));
    }

    #[test]
    fn test_tick_priority6_legacy_params_inert_when_no_features() {
        // DUAL-TRACK-EXIT-1 Track P T3: Priority 6 is now PHYS-LOCK. With
        // `exit_features = None` (what `call_tick` passes), the legacy
        // cost_ratio / cost_edge_max_ratio / min_profit_to_close_pct inputs are
        // silently ignored — they no longer drive any action. This test asserts
        // the inputs that used to fire COST EDGE now produce no Priority-6 close.
        // DUAL-TRACK-EXIT-1 T3：Priority 6 改為 PHYS-LOCK。`exit_features=None`
        // 時舊 cost_* 參數被忽略，不再觸發任何 Priority-6 close。
        let cfg = default_config();
        let action = call_tick(
            0.4,
            0.4,
            1.0,
            0.25,
            "trending",
            Some(1.0),
            0,
            0.0,
            0.0,
            &cfg,
        );
        // Neither the old COST EDGE reason nor any phys_lock reason should appear.
        // 舊 COST EDGE 字樣與新 phys_lock_* 字樣皆不得出現。
        assert!(
            !matches!(action, RiskAction::ClosePosition(ref r)
                if r.contains("COST EDGE") || r.contains("phys_lock")),
            "Priority 6 must be inert when exit_features is None, got {:?}",
            action
        );
    }

    #[test]
    fn test_tick_priority6_not_profitable_still_hold() {
        // Negative pnl with high cost_ratio used to NOT fire COST EDGE because
        // pnl was not positive. Under PHYS-LOCK with no features, also Hold —
        // just for a different reason (features=None → inert).
        // 負盈利下舊 COST EDGE 不觸發；PHYS-LOCK 下 features=None 同樣 Hold。
        let cfg = default_config();
        let action = call_tick(
            -0.5,
            0.0,
            1.0,
            0.9,
            "trending",
            Some(1.0),
            0,
            0.0,
            0.0,
            &cfg,
        );
        assert!(
            !matches!(action, RiskAction::ClosePosition(ref r)
                if r.contains("COST EDGE") || r.contains("phys_lock")),
            "Priority 6 must not fire in loss territory, got {:?}",
            action
        );
    }

    #[test]
    fn test_tick_priority6_phys_lock_gate1_holds_with_low_edge() {
        // GATE1-REVERSAL-1 (2026-04-21): ExitFeatures triggering gate 1 (edge
        // below floor) → Priority 6 does NOT close (Hold). Only Gate 4 paths
        // close via `risk_close:phys_lock_gate4_*`.
        // GATE1-REVERSAL-1：gate 1 edge 低 → Priority 6 不關倉（Hold）。
        // 僅 Gate 4 會觸發 `risk_close:phys_lock_gate4_*`。
        let cfg = default_config();
        let mut features = mk_features();
        features.est_net_bps = Some(1.0); // below default 5.0 floor
        let action = call_tick_with_features(
            0.4,
            0.4,
            1.0,
            0.25,
            "trending",
            Some(1.0),
            0,
            0.0,
            0.0,
            &features,
            &cfg,
        );
        assert!(
            !matches!(action, RiskAction::ClosePosition(ref r)
                if r.contains("phys_lock_gate1_low_edge")),
            "Gate 1 must Hold post-GATE1-REVERSAL-1, got {:?}",
            action
        );
    }

    #[test]
    fn test_tick_priority6_holds_when_features_all_pass() {
        // All-pass ExitFeatures → no gate fires → Hold (no Priority-6 close).
        // 全通 ExitFeatures → 所有 gate 都不觸發 → Priority-6 不關倉。
        let cfg = default_config();
        let features = mk_features();
        let action = call_tick_with_features(
            1.0,
            1.0,
            1.0,
            0.11,
            "trending",
            Some(1.0),
            0,
            0.0,
            0.0,
            &features,
            &cfg,
        );
        assert!(
            !matches!(action, RiskAction::ClosePosition(ref r) if r.contains("phys_lock")),
            "all-pass features must not trigger PHYS-LOCK, got {:?}",
            action
        );
    }

    #[test]
    fn test_tick_session_drawdown() {
        let cfg = default_config();
        let action = call_tick(
            0.0,
            0.0,
            1.0,
            0.0,
            "trending",
            Some(1.0),
            0,
            0.0,
            15.0,
            &cfg,
        );
        assert!(matches!(action, RiskAction::HaltSession(_)));
    }

    #[test]
    fn test_tick_consecutive_losses_cooldown() {
        let cfg = default_config();
        let action = call_tick(0.0, 0.0, 1.0, 0.0, "trending", Some(1.0), 3, 0.0, 0.0, &cfg);
        match action {
            RiskAction::SetCooldown(ms) => assert_eq!(ms, 30 * 60 * 1000),
            _ => panic!("expected SetCooldown, got {:?}", action),
        }
    }

    #[test]
    fn test_tick_daily_loss_halt() {
        let cfg = default_config();
        let action = call_tick(0.0, 0.0, 1.0, 0.0, "trending", Some(1.0), 0, 5.0, 0.0, &cfg);
        assert!(matches!(action, RiskAction::HaltSession(ref r) if r.contains("DAILY LOSS")));
    }

    #[test]
    fn test_tick_hold_all_ok() {
        // DUAL-TRACK-EXIT-1 Track P T3: Priority 6 is now PHYS-LOCK and inert
        // with exit_features=None (what call_tick passes). All other gates
        // (hard stop / dyn stop / TP / trailing / time / drawdown / consec
        // loss / daily loss) also pass, so result is Hold.
        // DUAL-TRACK-EXIT-1 T3：Priority 6=PHYS-LOCK, features=None 即不觸發；
        // 其他各 gate 皆未達閾值 → Hold。
        let cfg = default_config();
        let action = call_tick(0.5, 0.8, 2.0, 0.1, "trending", Some(1.0), 0, 1.0, 5.0, &cfg);
        assert!(matches!(action, RiskAction::Hold));
    }

    #[test]
    fn test_tick_priority_hard_stop_over_trailing() {
        let cfg = default_config();
        let action = call_tick(
            -5.0,
            3.0,
            1.0,
            0.0,
            "trending",
            Some(1.0),
            0,
            0.0,
            0.0,
            &cfg,
        );
        assert!(matches!(action, RiskAction::ClosePosition(ref r) if r.contains("HARD STOP")));
    }

    #[test]
    fn test_tick_atr_stop_mult_respected() {
        // Verify DynamicStop.atr_stop_mult is wired through to compute_dynamic_stop_pct.
        // 驗證 DynamicStop.atr_stop_mult 確實傳入 compute_dynamic_stop_pct。
        //
        // Setup: hard_stop=5%, base_ratio=0.6, cap_ratio=0.8, ATR=1.5%
        //   base = 3.0%,  cap = 4.0%
        //   mult=1.0 → atr_stop=1.5 < base → effective=3.0 → dyn_stop ≈ 3.3%  → -3.5 triggers
        //   mult=2.5 → atr_stop=3.75 > base → effective=3.75 → dyn_stop ≈ 4.2% → -3.5 holds
        let mut cfg_tight = RiskConfig::default();
        cfg_tight.dynamic_stop.atr_stop_mult = 1.0;

        let mut cfg_wide = RiskConfig::default();
        cfg_wide.dynamic_stop.atr_stop_mult = 2.5;

        let tight = call_tick(
            -3.5,
            0.0,
            1.0,
            0.0,
            "trending",
            Some(1.5),
            0,
            0.0,
            0.0,
            &cfg_tight,
        );
        let wide = call_tick(
            -3.5,
            0.0,
            1.0,
            0.0,
            "trending",
            Some(1.5),
            0,
            0.0,
            0.0,
            &cfg_wide,
        );

        assert!(
            matches!(tight, RiskAction::ClosePosition(ref r) if r.contains("DYNAMIC STOP")),
            "tight mult=1.0 should trigger dynamic stop, got {:?}",
            tight
        );
        assert!(
            matches!(wide, RiskAction::Hold),
            "wide mult=2.5 should hold (wider stop), got {:?}",
            wide
        );
    }

    #[test]
    fn test_pnl6_trailing_blocked_below_rr_floor() {
        // peak 1.1 current 0.2 drawdown 0.9 > 0.8, but locked 0.2 < dyn*0.5 floor
        let cfg = default_config();
        let action = call_tick(0.2, 1.1, 0.5, 0.0, "trending", Some(0.5), 0, 0.0, 0.0, &cfg);
        assert!(
            matches!(action, RiskAction::Hold),
            "expected Hold, got {:?}",
            action
        );
    }

    #[test]
    fn test_pnl6_trailing_fires_above_rr_floor() {
        // locked 2% > 1.5% floor -> fires
        let cfg = default_config();
        let action = call_tick(2.0, 3.0, 0.5, 0.0, "trending", Some(0.5), 0, 0.0, 0.0, &cfg);
        assert!(
            matches!(action, RiskAction::ClosePosition(ref r) if r.contains("TRAILING STOP")),
            "expected trailing close, got {:?}",
            action
        );
    }

    // -----------------------------------------------------------------------
    // PHYS-LOCK direct unit tests (DUAL-TRACK-EXIT-1 Track P T3)
    // PHYS-LOCK 直接單測（DUAL-TRACK-EXIT-1 Track P T3）
    // -----------------------------------------------------------------------

    #[test]
    fn test_phys_lock_gate1_low_edge_holds() {
        // GATE1-REVERSAL-1 (2026-04-21): est_net_bps below min_net_floor_bps → Hold
        // (was Lock pre-reversal; reversed to align with DUAL-TRACK-EXIT-1 intent
        // "prevent micro-profit premature lock"). Lock path is Gate 4 only.
        // GATE1-REVERSAL-1：edge 低於底線 → Hold（反轉前為 Lock）。防微利即套離場。
        let cfg = PhysLockConfig::default();
        let mut f = mk_features();
        f.est_net_bps = Some(1.0); // 1 < default 5.0 floor
        let decision = physical_micro_profit_lock(&f, &cfg);
        assert_eq!(
            decision,
            PhysicalDecision::Hold,
            "Gate 1 low edge must Hold (not Lock) post-GATE1-REVERSAL-1"
        );
    }

    #[test]
    fn test_phys_lock_gate1_pass_with_sufficient_edge() {
        // est_net_bps above floor + all later gates all-pass → Hold.
        let cfg = PhysLockConfig::default();
        let f = mk_features(); // est_net_bps=50.0 >> 5.0
        let decision = physical_micro_profit_lock(&f, &cfg);
        assert_eq!(decision, PhysicalDecision::Hold);
    }

    #[test]
    fn test_phys_lock_gate2_holds_within_min_hold_secs() {
        // entry_age_secs < min_hold_secs → Hold (even if everything else fires).
        let cfg = PhysLockConfig::default();
        let mut f = mk_features();
        f.entry_age_secs = Some(5.0); // < 30s default
        f.giveback_atr_norm = Some(10.0); // would fire gate4a if reached
        let decision = physical_micro_profit_lock(&f, &cfg);
        assert_eq!(
            decision,
            PhysicalDecision::Hold,
            "gate 2 must block gate 4 when position too fresh"
        );
    }

    #[test]
    fn test_phys_lock_gate3_holds_when_peak_below_atr_threshold() {
        // peak_pnl_pct < min_peak_atr_norm × atr_pct → Hold.
        // cfg default min_peak_atr_norm=0.5, atr_pct=2.0 → required=1.0.
        let cfg = PhysLockConfig::default();
        let mut f = mk_features();
        f.atr_pct = Some(2.0);
        f.peak_pnl_pct = 0.5; // < 1.0 required
        f.giveback_atr_norm = Some(10.0); // would fire gate4a if reached
        let decision = physical_micro_profit_lock(&f, &cfg);
        assert_eq!(
            decision,
            PhysicalDecision::Hold,
            "gate 3 must block gate 4 when peak insufficient"
        );
    }

    #[test]
    fn test_phys_lock_gate4_giveback_triggers_lock() {
        // giveback >= threshold → Lock(phys_lock_gate4_giveback).
        let cfg = PhysLockConfig::default();
        let mut f = mk_features();
        f.giveback_atr_norm = Some(1.0); // > default 0.7 threshold
        let decision = physical_micro_profit_lock(&f, &cfg);
        match decision {
            PhysicalDecision::Lock(r) => assert_eq!(r, "phys_lock_gate4_giveback"),
            other => panic!("expected Lock(gate4_giveback), got {:?}", other),
        }
    }

    #[test]
    fn test_phys_lock_gate4_stale_peak_with_negative_roc_locks() {
        // time_since_peak_ms > stale_peak_ms AND price_roc_short < 0
        // → Lock(phys_lock_gate4_stale_roc_neg).
        let cfg = PhysLockConfig::default();
        let mut f = mk_features();
        f.giveback_atr_norm = Some(0.0); // gate 4a does NOT fire
        f.time_since_peak_ms = Some(120_000); // > default 60_000
        f.price_roc_short = Some(-0.003);
        let decision = physical_micro_profit_lock(&f, &cfg);
        match decision {
            PhysicalDecision::Lock(r) => assert_eq!(r, "phys_lock_gate4_stale_roc_neg"),
            other => panic!("expected Lock(gate4_stale_roc_neg), got {:?}", other),
        }
    }

    #[test]
    fn test_phys_lock_holds_on_missing_atr_conservative() {
        // atr_pct = None → Hold (conservative: cannot normalise peak).
        let cfg = PhysLockConfig::default();
        let mut f = mk_features();
        f.atr_pct = None;
        f.giveback_atr_norm = Some(10.0); // would fire gate4a if reached
        let decision = physical_micro_profit_lock(&f, &cfg);
        assert_eq!(
            decision,
            PhysicalDecision::Hold,
            "missing ATR must block downstream gates"
        );
    }

    #[test]
    fn test_phys_lock_reason_string_format_stable() {
        // Active Lock reason strings must be byte-exact — downstream
        // `parse_exit_tag` relies on the `phys_lock_*` prefix + exact suffix.
        // GATE1-REVERSAL-1 (2026-04-21): Gate 1 no longer emits a reason (Hold);
        // only Gate 4a/4b segments remain. Historical `phys_lock_gate1_low_edge`
        // string retained in on_tick.rs t4_fix backward-compat test.
        // 兩種 Lock reason 字串須 byte-exact，下游依賴；GATE1-REVERSAL-1 後 Gate 1
        // 不再 emit（Hold），歷史 tag 由下游 parse 向後相容處理。
        let cfg = PhysLockConfig::default();

        // gate 4a
        let mut f4a = mk_features();
        f4a.giveback_atr_norm = Some(5.0);
        assert_eq!(
            physical_micro_profit_lock(&f4a, &cfg),
            PhysicalDecision::Lock("phys_lock_gate4_giveback".to_string())
        );

        // gate 4b
        let mut f4b = mk_features();
        f4b.giveback_atr_norm = Some(0.0);
        f4b.time_since_peak_ms = Some(500_000);
        f4b.price_roc_short = Some(-0.01);
        assert_eq!(
            physical_micro_profit_lock(&f4b, &cfg),
            PhysicalDecision::Lock("phys_lock_gate4_stale_roc_neg".to_string())
        );
    }
}
