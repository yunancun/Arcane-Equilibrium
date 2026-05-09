//! G2-03 per-strategy SL/TP runtime tests (extracted from risk_checks.rs).
//! G2-03 每策略 SL/TP runtime 測試（從 risk_checks.rs 抽出）。
//!
//! MODULE_NOTE (English):
//!   G2-03 (2026-04-26) extracted to a sibling test file (parent
//!   risk_checks.rs was approaching the §九 1200-line cap after the 8
//!   G2-03 runtime cap tests + helpers landed). Loaded via
//!   `#[cfg(test)] #[path = ...]` mod inclusion. These tests cover
//!   defense line B (runtime cap clamps stale overrides at P1 even if
//!   they survived validate). Defense line A (validate) is tested in
//!   config/risk_config_per_strategy_tests.rs.
//!
//! MODULE_NOTE (中文):
//!   G2-03（2026-04-26）抽至 sibling 測試檔（parent risk_checks.rs 加入 8 個
//!   G2-03 runtime tests + helpers 後接近 §九 1200 行上限）。經
//!   `#[cfg(test)] #[path]` mod 載入。覆蓋防線 B（runtime cap 即使 stale
//!   override 漏網仍夾於 P1）；防線 A（validate）測試在
//!   config/risk_config_per_strategy_tests.rs。

// Sibling sees `super` = risk_checks.rs file scope (where the parent
// `#[path]` mod include lives). pub fns + types accessible directly:
//   RiskAction, check_position_on_tick_with_override, effective_sl_max_pct.
// mod tests internal helpers (default_config, COST_EDGE_DEFAULT,
// MIN_PROFIT_DEFAULT) are NOT visible here, so we re-define mini-versions
// inline below — keeps this sibling self-contained.
// sibling 的 super = risk_checks.rs 檔案層級，pub fn 可拿；mod tests 內部
// helpers 不可拿，本檔自帶迷你版以保自足。
use super::*;
use crate::config::risk_config::StrategyOverride;

// ========================================================================
// G2-03 (2026-04-26) — per-strategy SL/TP override runtime tests
// G2-03（2026-04-26）—— 每策略 SL/TP 覆蓋 runtime 測試
//
// Defense line B (PA RFC §3.1): even if a stale override survives validate(),
// runtime never lets a strategy loosen SL/TP beyond P1. These tests lock
// in the runtime cap behaviour. Schema/validate tests are in
// config/risk_config_per_strategy_tests.rs (defense line A).
//
// 防線 B（PA RFC §3.1）：即使 stale override 漏網，runtime 必須夾於 P1。
// 本測試組鎖定 runtime cap 行為；validate（防線 A）測試在
// config/risk_config_per_strategy_tests.rs。
// ========================================================================

/// G2-03 sibling-local mirror of MIN_PROFIT_DEFAULT / COST_EDGE_DEFAULT
/// (mod tests internals are not visible here). Values match those in
/// risk_checks.rs mod tests so behaviour is identical to the parent.
/// G2-03 sibling 自帶 mirror 常量；mod tests 內部不可見。
const COST_EDGE_DEFAULT: f64 = 0.2;
const MIN_PROFIT_DEFAULT: f64 = 0.3;

/// G2-03 sibling-local default_config() mirror (mod tests internal not visible
/// here). Returns a fresh RiskConfig::default(); identical behaviour.
/// G2-03 sibling 自帶 default_config 鏡像。
fn default_config() -> RiskConfig {
    RiskConfig::default()
}

/// Helper: call check_position_on_tick_with_override with sensible defaults.
/// 輔助：以合理預設呼叫 _with_override 變體。
#[allow(clippy::too_many_arguments)]
fn call_tick_with_override(
    pnl: f64,
    peak: f64,
    hold: f64,
    regime: &str,
    atr: Option<f64>,
    per_strategy: Option<&StrategyOverride>,
    cfg: &RiskConfig,
) -> RiskAction {
    check_position_on_tick_with_override(
        pnl,
        peak,
        hold,
        0.0,
        regime,
        atr,
        "BTCUSDT",
        1000,
        0,
        0.0,
        0.0,
        COST_EDGE_DEFAULT,
        MIN_PROFIT_DEFAULT,
        None, // exit_features
        per_strategy,
        cfg,
    )
}

#[test]
fn test_g2_03_runtime_per_strategy_none_falls_back_to_limits() {
    // G2-03: per_strategy=None must give bit-identical pre-G2-03 behaviour.
    // hard-stop fires at -limits.stop_loss_max_pct (default 5.0).
    // G2-03：per_strategy=None 與 G2-03 前行為位元一致；hard-stop -5%。
    let cfg = default_config();
    let action = call_tick_with_override(-5.0, 0.0, 1.0, "trending", Some(1.0), None, &cfg);
    assert!(matches!(action, RiskAction::ClosePosition(ref r) if r.contains("HARD STOP")));
}

#[test]
fn test_g2_03_runtime_sl_override_tightens_hard_stop() {
    // G2-03: SL override = 2.0 (tighter than P1=5.0) → hard stop fires at -2.0.
    // -3% pnl: without override would hold (only -3% > -5%); with override fires.
    // G2-03：SL override 2.0 緊縮，-3% pnl 觸發 HARD STOP（無 override 時 hold）。
    let cfg = default_config();
    let mut so = StrategyOverride::default();
    so.stop_loss_max_pct_override = Some(2.0);

    // With override: -3% triggers (<=  -2.0 effective) HARD STOP.
    // 有 override：-3% 觸發 HARD STOP。
    let action_with =
        call_tick_with_override(-3.0, 0.0, 1.0, "trending", Some(0.0), Some(&so), &cfg);
    assert!(
        matches!(action_with, RiskAction::ClosePosition(ref r) if r.contains("HARD STOP")
            && r.contains("-2.00")),
        "tighter SL override must fire hard stop at -2%, got {:?}",
        action_with
    );

    // Without override: -3% does not trigger hard stop (P1=5%); should Hold
    // or fire dynamic stop. Use atr=0 to keep dyn_stop = base_ratio*5 = 3,
    // so -3% sits exactly at the boundary; check that any HARD STOP message
    // contains -5% (the P1 default), not -2%.
    // 無 override：-3% 不觸發 HARD STOP（P1=5%）；確認任何 close 訊息含 -5%。
    let action_no = call_tick_with_override(-3.0, 0.0, 1.0, "trending", Some(0.0), None, &cfg);
    if let RiskAction::ClosePosition(reason) = &action_no {
        assert!(
            !reason.contains("HARD STOP") || reason.contains("-5.00"),
            "without override hard stop must reflect P1 (-5%), got {}",
            reason
        );
    }
}

#[test]
fn test_g2_03_runtime_tp_override_tightens_take_profit() {
    // G2-03: TP override = 5.0 (tighter than P1=20.0) → TP fires at 5.0 * regime.
    // For trending (tp mult=1.5): effective tp_target = 5.0 * 1.5 = 7.5%.
    // pnl = 10% > 7.5 → fire; without override target = 30% → hold.
    // G2-03：TP override 5.0 緊縮，10% pnl trending 觸發 TP（target 7.5%）。
    let mut cfg = default_config();
    cfg.limits.take_profit_enforced = true;
    let mut so = StrategyOverride::default();
    so.take_profit_max_pct_override = Some(5.0);

    let action_with =
        call_tick_with_override(10.0, 10.0, 1.0, "trending", Some(1.0), Some(&so), &cfg);
    assert!(
        matches!(action_with, RiskAction::ClosePosition(ref r) if r.contains("TAKE PROFIT")),
        "TP override 5% must fire TP at 10% pnl, got {:?}",
        action_with
    );

    // Without override: P1 TP=20%, trending mult=1.5 → target 30%. 10% holds.
    // 無 override：P1 TP=20%, target 30%；10% pnl 不觸發 TP。
    let action_no = call_tick_with_override(10.0, 10.0, 1.0, "trending", Some(1.0), None, &cfg);
    assert!(
        !matches!(action_no, RiskAction::ClosePosition(ref r) if r.contains("TAKE PROFIT")),
        "without TP override 10% pnl must hold (target 30%), got {:?}",
        action_no
    );
}

#[test]
fn test_g2_03_runtime_sl_override_clamps_to_p1_when_over() {
    // G2-03 defense line B: even if a stale override > P1 survives validate
    // (race / future schema drift), runtime clamps to P1. Override 10.0 > P1
    // 5.0 → effective_sl = min(10, 5) = 5. -3% must hold (P1 not breached).
    // G2-03 防線 B：override > P1 漏網，runtime 夾到 P1（5%），-3% 不觸發。
    let cfg = default_config();
    let mut so = StrategyOverride::default();
    so.stop_loss_max_pct_override = Some(10.0); // > P1 5%, would normally be rejected

    let action = call_tick_with_override(-3.0, 0.0, 1.0, "trending", Some(0.0), Some(&so), &cfg);
    // -3% should NOT trigger HARD STOP (P1 effective = 5).
    // -3% 不應觸發 HARD STOP（effective 仍 5%）。
    if let RiskAction::ClosePosition(reason) = &action {
        assert!(
            !reason.contains("HARD STOP"),
            "stale over-cap override must be clamped to P1 — should not fire HARD STOP at -3%, got: {}",
            reason
        );
    }
}

#[test]
fn test_g2_03_runtime_tp_override_clamps_to_p1_when_over() {
    // G2-03 defense line B (TP variant): override > P1 → effective_tp clamped.
    // P1 TP=20%, override 100% → effective = min(100, 20) = 20%.
    // trending mult=1.5 → target = 30%. 25% pnl < target → hold.
    // G2-03 防線 B（TP）：override 100% > P1 20% → 夾到 20%，target 30%，25% hold。
    let mut cfg = default_config();
    cfg.limits.take_profit_enforced = true;
    let mut so = StrategyOverride::default();
    so.take_profit_max_pct_override = Some(100.0);

    let action = call_tick_with_override(25.0, 25.0, 1.0, "trending", Some(1.0), Some(&so), &cfg);
    assert!(
        !matches!(action, RiskAction::ClosePosition(ref r) if r.contains("TAKE PROFIT")),
        "stale over-cap TP override must be clamped to P1 — should not fire TP at 25%, got {:?}",
        action
    );
}

#[test]
fn test_g2_03_runtime_partial_override_only_sl() {
    // G2-03: setting only SL override (TP / trailing None) — TP/trailing must
    // still use global agent values, only SL tightens.
    // G2-03：只設 SL override（TP/trailing 走全局），verify TP/trailing 不受影響。
    let mut cfg = default_config();
    cfg.limits.take_profit_enforced = true;
    let mut so = StrategyOverride::default();
    so.stop_loss_max_pct_override = Some(2.0);
    // tp/trailing intentionally None
    // tp/trailing 故意保留 None

    // SL: -3% triggers (effective 2%).
    // SL：-3% 觸發 HARD STOP（effective 2%）。
    let action_sl = call_tick_with_override(-3.0, 0.0, 1.0, "trending", Some(0.0), Some(&so), &cfg);
    assert!(
        matches!(action_sl, RiskAction::ClosePosition(ref r) if r.contains("HARD STOP")),
        "partial SL override must fire HARD STOP, got {:?}",
        action_sl
    );

    // TP: 25% pnl trending → P1 20% * 1.5 = 30% target → hold (no TP override).
    // TP：25% pnl，P1 target 30%，無 override 仍 hold。
    let action_tp =
        call_tick_with_override(25.0, 25.0, 1.0, "trending", Some(1.0), Some(&so), &cfg);
    assert!(
        !matches!(action_tp, RiskAction::ClosePosition(ref r) if r.contains("TAKE PROFIT")),
        "partial override (SL only) must not affect TP gate, got {:?}",
        action_tp
    );
}

#[test]
fn test_g2_03_runtime_trailing_override_tightens() {
    // G2-03: trailing_distance_pct_override = 0.3 (tighter than agent default 0.8).
    // Setup: peak=3.0 current=2.5 drawdown=0.5; pnl 2.5 above floor.
    // drawdown 0.5 >= 0.3 (override) → fires; default 0.8 would not fire.
    // dyn_stop from atr=0.5 ≈ 1.0; min_locked = 0.5 < pnl 2.5 → floor passes.
    // G2-03：trailing distance 0.3 緊縮；setup pnl 2.5 / peak 3 / drawdown 0.5；
    // override 0.3 觸發，default 0.8 不觸發；floor 0.5 < pnl 2.5 不阻擋。
    let cfg = default_config();
    let mut so = StrategyOverride::default();
    so.trailing_distance_pct_override = Some(0.3);

    let action = call_tick_with_override(2.5, 3.0, 1.0, "trending", Some(0.5), Some(&so), &cfg);
    assert!(
        matches!(action, RiskAction::ClosePosition(ref r) if r.contains("TRAILING STOP")),
        "tighter trailing_distance override must fire trailing, got {:?}",
        action
    );

    // Same setup without the override → should NOT fire (drawdown 0.5 < default 0.8).
    // 同 setup 無 override → 不觸發（drawdown 0.5 < default 0.8）。
    let action_no = call_tick_with_override(2.5, 3.0, 1.0, "trending", Some(0.5), None, &cfg);
    assert!(
        !matches!(action_no, RiskAction::ClosePosition(ref r) if r.contains("TRAILING STOP")),
        "default trailing_distance 0.8 must NOT fire at drawdown 0.5, got {:?}",
        action_no
    );
}

#[test]
fn test_g2_03_runtime_helper_effective_sl_returns_min() {
    // G2-03 helper unit test: effective_sl_max_pct correctly returns
    // min(override, P1) when both finite + > 0; falls through to P1 on None
    // / NaN / Inf / non-positive.
    // G2-03 helper 單測：override Some + finite + >0 取 min；其他走 P1。
    let cfg = default_config();
    let limits = &cfg.limits; // P1 stop_loss_max_pct = 5.0

    // None override → limits.
    // None → P1。
    let none_so = StrategyOverride::default();
    assert_eq!(effective_sl_max_pct(limits, Some(&none_so)), 5.0);
    assert_eq!(effective_sl_max_pct(limits, None), 5.0);

    // Override 2.0 (under P1) → 2.0 (the tighter value wins).
    // override 2.0 緊縮 → 2.0。
    let mut tight = StrategyOverride::default();
    tight.stop_loss_max_pct_override = Some(2.0);
    assert_eq!(effective_sl_max_pct(limits, Some(&tight)), 2.0);

    // Override 10.0 (over P1) → 5.0 (defense line B clamp).
    // override 10.0 > P1 → 5.0（防線 B 夾）。
    let mut over_cap = StrategyOverride::default();
    over_cap.stop_loss_max_pct_override = Some(10.0);
    assert_eq!(effective_sl_max_pct(limits, Some(&over_cap)), 5.0);

    // NaN / Inf / negative override → fall through to P1.
    // NaN/Inf/負值 → 走 P1。
    let mut nan_so = StrategyOverride::default();
    nan_so.stop_loss_max_pct_override = Some(f64::NAN);
    assert_eq!(effective_sl_max_pct(limits, Some(&nan_so)), 5.0);

    let mut inf_so = StrategyOverride::default();
    inf_so.stop_loss_max_pct_override = Some(f64::INFINITY);
    // Inf is .is_finite() == false so filter rejects → P1.
    // Inf 非 finite，filter 拒 → P1。
    assert_eq!(effective_sl_max_pct(limits, Some(&inf_so)), 5.0);

    let mut neg_so = StrategyOverride::default();
    neg_so.stop_loss_max_pct_override = Some(-1.0);
    assert_eq!(effective_sl_max_pct(limits, Some(&neg_so)), 5.0);
}

// ===========================================================================
// W-AUDIT-6 — risk_config_demo.toml round-trip + retired funding_arb cleanup
// W-AUDIT-6 —— risk_config_demo.toml 解析 + retired funding_arb 清理
//
// Anchors the post-RCA shape: demo `dynamic_stop.base_ratio` 0.4→0.25 plus
// no `[per_strategy.funding_arb]` risk override. `funding_arb` retirement now
// belongs to `strategy_params_{paper,demo,live}.toml::funding_arb.active=false`,
// not to RiskConfig active/override state.
//
// Locks the *demo TOML wire-shape* in tandem with G2-03 schema (Defense A,
// validate). Acts as an early sentinel for any future TOML parse / schema drift
// that would reintroduce retired funding_arb risk overrides or lose the
// tightened base_ratio.
//
// 鎖定 demo TOML 線格式：dyn_stop base_ratio=0.25 + RiskConfig 不再承載
// funding_arb active/override；同檔驗 Defense A (validate)。
// ===========================================================================

#[test]
fn test_demo_toml_retired_funding_arb_removed_from_risk_config() {
    use std::fs;
    use std::path::PathBuf;

    // Locate srv/settings/risk_control_rules/risk_config_demo.toml relative
    // to this crate's CARGO_MANIFEST_DIR (= srv/rust/openclaw_engine).
    // 由 CARGO_MANIFEST_DIR 上溯 2 層至 srv 根定位 demo TOML。
    let mut srv_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    srv_root.pop(); // openclaw_engine -> rust
    srv_root.pop(); // rust -> srv
    let toml_path = srv_root
        .join("settings")
        .join("risk_control_rules")
        .join("risk_config_demo.toml");
    let toml_str = fs::read_to_string(&toml_path)
        .unwrap_or_else(|e| panic!("failed to read {:?}: {}", toml_path, e));
    let cfg: RiskConfig = toml::from_str(&toml_str)
        .unwrap_or_else(|e| panic!("TOML parse failed for risk_config_demo.toml: {}", e));

    // ── dynamic_stop.base_ratio = 0.25 (was 0.4) ──
    // ── dynamic_stop.base_ratio 0.4→0.25 ──
    assert!(
        (cfg.dynamic_stop.base_ratio - 0.25).abs() < 1e-9,
        "dynamic_stop.base_ratio expected 0.25, got {}",
        cfg.dynamic_stop.base_ratio
    );

    // ── retired funding_arb must not live in RiskConfig overrides ──
    // ── 已退休 funding_arb 不應再出現在 RiskConfig override ──
    assert!(
        !cfg.per_strategy.contains_key("funding_arb"),
        "funding_arb active/override state belongs to strategy_params_*.toml"
    );

    // ── Pre-existing ma_crossover schema-only block must remain None ──
    // ── 既有 ma_crossover schema-only 區塊維持 None（不被本次改動影響）──
    let ma = cfg
        .per_strategy
        .get("ma_crossover")
        .expect("[per_strategy.ma_crossover] missing in demo TOML");
    assert_eq!(
        ma.stop_loss_max_pct_override, None,
        "ma_crossover SL override must remain commented-out (None)"
    );
    assert!(
        ma.blocked_symbols
            .as_ref()
            .map(|symbols| symbols.iter().any(|s| s == "LABUSDT"))
            .unwrap_or(false),
        "ma_crossover.blocked_symbols must include LABUSDT after P1-EDGE-1"
    );

    // ── Defense A: full RiskConfig::validate() must PASS ──
    // ── 防線 A：validate() 必通過 ──
    cfg.validate()
        .expect("demo TOML must pass RiskConfig::validate() (Defense A)");
}
