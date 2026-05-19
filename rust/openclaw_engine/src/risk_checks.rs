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

use crate::config::risk_config::{GlobalLimits, StrategyOverride};
use crate::config::RiskConfig;
use crate::exit_features::{physical_micro_profit_lock_v2, ExitFeatures, PhysicalDecision};
use openclaw_core::risk::{compute_dynamic_stop_pct, regime_multipliers};

/// P0-ENGINE-HALTSESSION-STUCK-FIX (2026-05-19): priority-9 `RiskAction::HaltSession`
/// reason 字首；用於 `HaltKind::classify` 分類 + V098 governance audit。
///
/// 與 `drawdown_revoke::DRAWDOWN_REASON_PREFIX` 並列；exact-prefix match。
/// 來源：本檔 priority 9 `format!("DAILY LOSS: {:.2}% >= {:.2}%", ...)` 是唯一
/// constructor —— 任何字串對齊改動必同步更新此常數，否則 TTL 與 forensic log
/// 分類會 drift。
///
/// P0-ENGINE-HALTSESSION-STUCK-FIX（2026-05-19）：priority 9 daily-loss halt
/// 的 reason 字首；exact-prefix match 與 drawdown 並列。同步契約：priority 9
/// format! 改字串時此常數必同步更新，否則 HaltKind 分類與 V098 audit drift。
pub const DAILY_LOSS_REASON_PREFIX: &str = "DAILY LOSS";

// ---------------------------------------------------------------------------
// G2-03 (2026-04-26) — per-strategy SL/TP effective-value helpers
// G2-03（2026-04-26）—— 每策略 SL/TP 有效值輔助函式
// ---------------------------------------------------------------------------
//
// Per PA RFC §3.1 enforcement model:
//   A. validate() rejects override > limits at IPC patch / TOML reload time
//   B. THESE helpers clamp at runtime — even if a stale override survives the
//      validate gate (race condition, future schema drift), runtime never
//      lets a strategy loosen SL/TP beyond P1. Belt-and-suspenders.
//   C. counterfactual_calibrator dry-run rejects before write (offline)
//
// PA RFC §3.1 三道防線：A. validate / B. 本 helper runtime clamp / C. calibrator
// dry-run。本 helper 即使 stale override 漏網仍守住 P1 硬頂。
//
// All four override fields are Optional; None = fall-through to global limits/agent.
// Helpers return f64 effective values that callers feed into the existing
// risk_checks math without changing the SL/TP logic shape.

/// G2-03 (2026-04-26): Effective stop-loss max pct for a position.
/// Returns `min(override, limits.stop_loss_max_pct)` when override is Some,
/// else `limits.stop_loss_max_pct`. The min() is defense line B (runtime cap).
///
/// G2-03：計算位置的有效 SL 上限。Some override 時取 min(override, P1)，
/// 防 stale override 越過 P1（防線 B）；None 走 P1 全局值。
#[inline]
pub(crate) fn effective_sl_max_pct(
    limits: &GlobalLimits,
    per_strategy: Option<&StrategyOverride>,
) -> f64 {
    match per_strategy.and_then(|o| o.stop_loss_max_pct_override) {
        // Defense line B: clamp override at limits even if validate let it through
        // (NaN/Inf/over-cap edge cases). NaN > limits is false → falls through to
        // limits via .min(), which is the conservative behaviour.
        // 防線 B：若 override 漏網（NaN/Inf/超頂），用 min(override, limits) 強制夾。
        Some(v) if v.is_finite() && v > 0.0 => v.min(limits.stop_loss_max_pct),
        _ => limits.stop_loss_max_pct,
    }
}

/// G2-03 (2026-04-26): Effective take-profit max pct for a position.
/// Symmetric to `effective_sl_max_pct` — Some override clamped at limits, None
/// falls back to global. Used by the take-profit-enforced gate where applicable.
///
/// G2-03：對稱於 effective_sl_max_pct，計算 TP 上限；Some 取 min(override, P1)。
#[inline]
pub(crate) fn effective_tp_max_pct(
    limits: &GlobalLimits,
    per_strategy: Option<&StrategyOverride>,
) -> f64 {
    match per_strategy.and_then(|o| o.take_profit_max_pct_override) {
        Some(v) if v.is_finite() && v > 0.0 => v.min(limits.take_profit_max_pct),
        _ => limits.take_profit_max_pct,
    }
}

/// Effective take-profit enforcement flag. A per-strategy override lets MA
/// enforce TP without flipping the global switch for grid / BB strategies.
/// 每策略 TP enforcement 覆蓋；允許 MA 單獨啟用止盈，不影響其他策略。
#[inline]
pub(crate) fn effective_take_profit_enforced(
    limits: &GlobalLimits,
    per_strategy: Option<&StrategyOverride>,
) -> bool {
    per_strategy
        .and_then(|o| o.take_profit_enforced_override)
        .unwrap_or(limits.take_profit_enforced)
}

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
    // G2-03 (2026-04-26): backward-compat thin wrapper. Delegates to
    // `check_position_on_tick_with_override(... per_strategy=None ...)` —
    // bit-identical pre-G2-03 behaviour for all existing callers (tests,
    // position_risk_evaluator chain, integration tests). New callers in
    // step_6_risk_checks.rs use the *_with_override variant directly to
    // thread per-strategy SL/TP overrides.
    // G2-03：向後兼容包裝；既有 caller 與 G2-03 前位元一致，新 caller 走
    // `_with_override` 直接傳 per_strategy。
    check_position_on_tick_with_override(
        pnl_pct,
        peak_pnl_pct,
        holding_hours,
        cost_ratio,
        regime,
        atr_pct,
        symbol,
        entry_ts_ms,
        consecutive_losses,
        daily_loss_pct,
        session_drawdown_pct,
        cost_edge_max_ratio,
        min_profit_to_close_pct,
        exit_features,
        None,
        config,
    )
}

/// G2-03 (2026-04-26): Tick-level position risk check with per-strategy SL/TP
/// override support. Same priority order as `check_position_on_tick` but the
/// hard-stop / dynamic-stop / take-profit / trailing gates use per-strategy
/// effective values when `per_strategy` is `Some` — defense line B (runtime
/// cap) is applied via `effective_sl_max_pct` / `effective_tp_max_pct`
/// helpers, so even if a stale override survives validate() (defense line A),
/// runtime never lets a strategy loosen SL/TP beyond P1.
///
/// G2-03：tick 級風控 + 每策略 SL/TP 覆蓋。priority 與原版相同；hard/dyn/TP/
/// trailing 4 gate 用 effective 值，per_strategy=None 與 G2-03 前行為位元一致；
/// per_strategy=Some 即使 override > limits 漏網仍夾於 P1（防線 B 守住硬頂）。
#[allow(clippy::too_many_arguments)]
pub fn check_position_on_tick_with_override(
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
    per_strategy: Option<&StrategyOverride>,
    config: &RiskConfig,
) -> RiskAction {
    // Legacy COST EDGE inputs retained on ABI for T4; silence unused-param warnings.
    // T3：COST EDGE 相關參數保留 ABI，等 T4 接 ExitFeatures 真實值。
    let _ = (cost_ratio, cost_edge_max_ratio, min_profit_to_close_pct);
    let rm = regime_multipliers(regime);
    let limits = &config.limits;
    let agent = &config.agent;
    let dyn_cfg = &config.dynamic_stop;

    // G2-03 (2026-04-26): compute effective SL/TP up front via helpers.
    // None per_strategy (or override None) → bit-identical pre-G2-03.
    // G2-03：先算 effective SL/TP；per_strategy=None 與 G2-03 前位元一致。
    let effective_sl = effective_sl_max_pct(limits, per_strategy);
    let effective_tp = effective_tp_max_pct(limits, per_strategy);
    let effective_tp_enforced = effective_take_profit_enforced(limits, per_strategy);

    // G2-03: trailing activation/distance — per_strategy override Some + finite + > 0
    // wins; else fall back to global agent values. Validates already enforced
    // > 0 + finite at line A so the filter is defensive (line B coverage).
    // G2-03：trailing 啟動/距離覆蓋；filter 為防線 B 防 stale override。
    let effective_trailing_activation = per_strategy
        .and_then(|o| o.trailing_activation_pct_override)
        .filter(|v| v.is_finite() && *v > 0.0)
        .unwrap_or(agent.trailing_activation_pct);
    let effective_trailing_distance = per_strategy
        .and_then(|o| o.trailing_distance_pct_override)
        .filter(|v| v.is_finite() && *v > 0.0)
        .unwrap_or(agent.trailing_distance_pct);

    // 1. Hard stop — uses effective_sl (= min(override, limits) when Some).
    // 1. 硬止損 — 用 effective_sl（Some 時取 min(override, limits)）。
    if pnl_pct <= -effective_sl {
        return RiskAction::ClosePosition(format!(
            "HARD STOP: pnl {:.2}% <= -{:.2}%",
            pnl_pct, effective_sl
        ));
    }

    // 2. Dynamic stop — uses effective_sl as the hard-stop ceiling fed into
    //    compute_dynamic_stop_pct. atr_stop_mult/cap_ratio/base_ratio remain
    //    global (per-strategy override of those is out of scope for G2-03).
    // 2. 動態止損 — 用 effective_sl 作硬頂；ATR 倍數仍走全局 dyn_cfg。
    let dyn_stop = compute_dynamic_stop_pct(
        effective_sl * dyn_cfg.base_ratio,
        atr_pct,
        symbol,
        entry_ts_ms,
        regime,
        effective_sl,
        dyn_cfg.cap_ratio,
        dyn_cfg.atr_stop_mult,
    );
    if pnl_pct <= -dyn_stop {
        return RiskAction::ClosePosition(format!(
            "DYNAMIC STOP: pnl {:.2}% <= -{:.2}% (regime={}, atr={:?})",
            pnl_pct, dyn_stop, regime, atr_pct
        ));
    }

    // 3. Take profit (if enforced) — uses effective_tp.
    // 3. 止盈（如強制）— 使用 effective_tp。
    if effective_tp_enforced {
        let tp_target = effective_tp * rm.tp;
        if pnl_pct >= tp_target {
            return RiskAction::ClosePosition(format!(
                "TAKE PROFIT: pnl {:.2}% >= {:.2}% (regime={})",
                pnl_pct, tp_target, regime
            ));
        }
    }

    // 4. Trailing stop — uses effective_trailing_activation / effective_trailing_distance.
    // 4. 追蹤止損 — 使用每策略覆蓋值。
    if agent.trailing_enabled && peak_pnl_pct >= effective_trailing_activation {
        let drawdown_from_peak = peak_pnl_pct - pnl_pct;
        let min_locked_profit = dyn_stop * dyn_cfg.trailing_min_rr;
        if drawdown_from_peak >= effective_trailing_distance && pnl_pct >= min_locked_profit {
            return RiskAction::ClosePosition(format!(
                "TRAILING STOP: peak {:.2}% - current {:.2}% = {:.2}% >= distance {:.2}% (locked {:.2}% >= floor {:.2}%)",
                peak_pnl_pct, pnl_pct, drawdown_from_peak,
                effective_trailing_distance, pnl_pct, min_locked_profit
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
            physical_micro_profit_lock_v2(features, &config.exit)
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
// PHYS-LOCK — DUAL-TRACK-EXIT-1 Track P / 物理層微利鎖定
// ---------------------------------------------------------------------------
//
// TRACK-P-V2-SWAP-1 (2026-04-22) retired the linear `physical_micro_profit_lock`
// pure fn + `PhysLockConfig` previously defined here. Priority 6 above now
// calls `exit_features::physical_micro_profit_lock_v2` with
// `RiskConfig.exit: ExitConfig` (non-linear giveback: threshold =
// max(base − slope × peak_atr_norm, floor)). Reason-string ABI unchanged —
// downstream `strip_phys_lock_prefix` + `parse_exit_tag` still see
// `phys_lock_gate4_giveback` / `phys_lock_gate4_stale_roc_neg`.
//
// TRACK-P-V2-SWAP-1（2026-04-22）退役舊線性 `physical_micro_profit_lock` +
// `PhysLockConfig`，Priority 6 改呼 `exit_features::physical_micro_profit_lock_v2`
// + `RiskConfig.exit: ExitConfig`（非線性 giveback 閾值）。reason 字串 ABI
// 不變，下游解析兼容。

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
            est_net_bps: Some(50.0), // well above 5.0 floor
            peak_pnl_pct: 5.0,       // well above 0.5×ATR
            current_pnl_pct: 3.0,
            atr_pct: Some(1.0),           // 1% ATR
            giveback_atr_norm: Some(0.0), // no giveback yet
            time_since_peak_ms: Some(0),  // peak just reached
            price_roc_short: Some(0.0),
            entry_age_secs: Some(120.0), // past min_hold
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
    // PHYS-LOCK direct unit tests retired by TRACK-P-V2-SWAP-1 (2026-04-22).
    // Priority 6 now dispatches to `exit_features::physical_micro_profit_lock_v2`,
    // whose 25 direct unit tests live in `exit_features/v2.rs`. The end-to-end
    // Priority 6 gating is covered above through `call_tick_with_features`,
    // which exercises the v2 path via `check_position_on_tick`.
    //
    // PHYS-LOCK 直接單測於 TRACK-P-V2-SWAP-1（2026-04-22）退役。
    // Priority 6 改呼 `exit_features::physical_micro_profit_lock_v2`，
    // 其 25 個直測位於 `exit_features/v2.rs`。Priority 6 的 end-to-end
    // 行為由上方 `call_tick_with_features` 測試經 `check_position_on_tick`
    // 覆蓋。
    // -----------------------------------------------------------------------
}

// G2-03 (2026-04-26) per-strategy override runtime tests live in a dedicated
// sibling test file to keep this file under §九 1200-line cap.
// G2-03 每策略覆蓋 runtime 測試在獨立 sibling，守 §九 1200 行上限。
#[cfg(test)]
#[path = "risk_checks_per_strategy_tests.rs"]
mod g2_03_per_strategy_tests;
