//! MICRO-PROFIT-FIX-1 integration tests (worklog §4.9).
//! Covers: narrow cost-edge band config wiring, fast_track notional floor
//! pre-conditions, entry_notional accumulation, legacy budget-config migration.
//! Uses only the crate's public API — deeper per-tick evaluator / fast_track
//! filter paths are covered by module-level unit tests in the respective
//! source files (see `paper_state::tests`, `position_risk_evaluator::tests`,
//! `risk_checks::tests`, `config::budget_config::tests`).
//! MICRO-PROFIT-FIX-1 整合測試（worklog §4.9）：窄帶配置、快速通道底線、
//! entry_notional 累積、舊 budget 配置遷移。僅用 crate 公開 API。

use openclaw_engine::config::legacy_migration::sanitize_legacy_budget_config;
use openclaw_engine::config::{BudgetConfig, RiskConfig};
use openclaw_engine::paper_state::PaperState;

// ── §4.9 #1: narrow lock-in band config wired through BudgetConfig default ─
#[test]
fn micro_profit_fix_default_band_config() {
    let cfg = BudgetConfig::default();
    assert!(
        (cfg.attention_tax.cost_edge_max_ratio - 0.2).abs() < 1e-9,
        "cost_edge_max_ratio default should be 0.2 (MICRO-PROFIT-FIX-1), got {}",
        cfg.attention_tax.cost_edge_max_ratio
    );
    assert!(
        (cfg.attention_tax.min_profit_to_close_pct - 0.3).abs() < 1e-9,
        "min_profit_to_close_pct default should be 0.3 (MICRO-PROFIT-FIX-1), got {}",
        cfg.attention_tax.min_profit_to_close_pct
    );
    assert!(cfg.validate().is_ok(), "default config must validate");
}

// ── §4.9 #2: shrunk cost_edge range rejects legacy 100.0 via validate ──────
#[test]
fn micro_profit_fix_validate_rejects_legacy_cost_edge_range() {
    let mut cfg = BudgetConfig::default();
    cfg.attention_tax.cost_edge_max_ratio = 100.0;
    assert!(
        cfg.validate().is_err(),
        "validate must reject 100.0 after MICRO-PROFIT-FIX-1 range shrink"
    );
    cfg.attention_tax.cost_edge_max_ratio = 10.5;
    assert!(cfg.validate().is_err(), "validate must reject 10.5 (above 10 ceiling)");
    cfg.attention_tax.cost_edge_max_ratio = 10.0;
    assert!(cfg.validate().is_ok(), "validate must accept the 10.0 boundary");
}

// ── §4.9 #3: min_profit_to_close_pct range ─────────────────────────────────
#[test]
fn micro_profit_fix_min_profit_range_enforced() {
    let mut cfg = BudgetConfig::default();
    cfg.attention_tax.min_profit_to_close_pct = -0.01;
    assert!(cfg.validate().is_err(), "validate must reject negative min_profit");
    cfg.attention_tax.min_profit_to_close_pct = 5.01;
    assert!(cfg.validate().is_err(), "validate must reject min_profit above 5.0 ceiling");
    cfg.attention_tax.min_profit_to_close_pct = 5.0;
    assert!(cfg.validate().is_ok(), "validate must accept 5.0 boundary");
}

// ── §4.9 #4: legacy BudgetConfig migration clamps 100 → 0.2 + validates ───
#[test]
fn micro_profit_fix_legacy_cost_edge_migration_end_to_end() {
    let mut cfg = BudgetConfig::default();
    cfg.attention_tax.cost_edge_max_ratio = 100.0; // simulate persisted legacy snapshot
    assert!(cfg.validate().is_err(), "pre-migration: fail");

    let rewritten = sanitize_legacy_budget_config(&mut cfg);
    assert_eq!(rewritten.len(), 1, "should rewrite exactly one field");
    assert!(rewritten[0].contains("cost_edge_max_ratio"));

    assert!(
        (cfg.attention_tax.cost_edge_max_ratio - 0.2).abs() < 1e-9,
        "post-migration: clamped to default 0.2"
    );
    assert!(cfg.validate().is_ok(), "post-migration: validate passes");

    // Idempotent: already-sanitised values are a no-op.
    // 冪等：已遷移值再跑一次應為 no-op。
    let second_pass = sanitize_legacy_budget_config(&mut cfg);
    assert_eq!(second_pass.len(), 0);
}

// ── §4.9 #5: PaperPosition.entry_notional accumulates across same-direction
// fills; reductions leave the peak baseline intact (option 2 semantics) ───
#[test]
fn micro_profit_fix_entry_notional_accumulates_and_persists_through_reduce() {
    let mut s = PaperState::new(10_000.0);
    s.apply_fill("BTC", true, 0.1, 50_000.0, 0.0, 0, "test"); // +5_000
    s.apply_fill("BTC", true, 0.1, 52_000.0, 0.0, 1_000, "test"); // +5_200
    s.apply_fill("BTC", true, 0.1, 54_000.0, 0.0, 2_000, "test"); // +5_400

    let peak = 0.1 * 50_000.0 + 0.1 * 52_000.0 + 0.1 * 54_000.0;
    let pos = s.get_position("BTC").expect("position exists after opens");
    assert!(
        (pos.entry_notional - peak).abs() < 1e-6,
        "entry_notional accumulates to peak {}, got {}",
        peak,
        pos.entry_notional
    );

    // Halve: entry_notional must stay at peak for future floor checks.
    // 半倉後 entry_notional 保持峰值，作為後續底線判斷基準。
    s.set_latest_price("BTC", 54_000.0);
    let _ = s.reduce_position("BTC", 0.15, 54_000.0);
    let pos = s.get_position("BTC").expect("position still open after halve");
    assert!(
        (pos.qty - 0.15).abs() < 1e-10,
        "qty halved to 0.15, got {}",
        pos.qty
    );
    assert!(
        (pos.entry_notional - peak).abs() < 1e-6,
        "entry_notional stays at peak {} after halve, got {}",
        peak,
        pos.entry_notional
    );
}

// ── §4.9 #6: notional-floor pre-condition — position with current notional
// below 25% of entry_notional would be filtered out by fast_track ReduceToHalf
// (mirrors the on_tick.rs §4.7 predicate) ─────────────────────────────────
#[test]
fn micro_profit_fix_ft_notional_floor_predicate() {
    let mut s = PaperState::new(10_000.0);
    s.apply_fill("BTC", true, 0.4, 50_000.0, 0.0, 0, "open"); // entry_notional = 20_000
    s.set_latest_price("BTC", 50_000.0);
    // Drive qty down to 0.08 (20% of original) — current notional = 4_000.
    // 把 qty 壓到 0.08（原始 20%），當前名義值 4_000。
    let _ = s.reduce_position("BTC", 0.32, 50_000.0);

    let pos = s.get_position("BTC").expect("position persists under reduce");
    assert!((pos.entry_notional - 20_000.0).abs() < 1e-6);

    let ratio = RiskConfig::default().limits.ft_min_notional_ratio_of_entry;
    assert!((ratio - 0.25).abs() < 1e-9);
    let current_notional = pos.qty * 50_000.0;
    let floor = ratio * pos.entry_notional;
    // Mirrors on_tick.rs §4.7 filter: keep iff current_notional >= floor.
    // 與 on_tick.rs §4.7 過濾同規則：current ≥ floor 才保留。
    let keep = current_notional >= floor;
    assert!(
        !keep,
        "position at 20% of entry_notional must be filtered out by the 25% floor \
         (current {} vs floor {})",
        current_notional, floor
    );
}

// ── §4.9 #7: RiskConfig.limits.ft_min_notional_ratio_of_entry wiring + range
#[test]
fn micro_profit_fix_risk_config_ft_ratio_wiring() {
    let risk = RiskConfig::default();
    assert!(
        (risk.limits.ft_min_notional_ratio_of_entry - 0.25).abs() < 1e-9,
        "default ratio should be 0.25, got {}",
        risk.limits.ft_min_notional_ratio_of_entry
    );

    let mut bad = RiskConfig::default();
    bad.limits.ft_min_notional_ratio_of_entry = 1.5;
    assert!(bad.validate().is_err(), "ratio > 1.0 must be rejected");

    bad.limits.ft_min_notional_ratio_of_entry = -0.1;
    assert!(bad.validate().is_err(), "negative ratio must be rejected");

    bad.limits.ft_min_notional_ratio_of_entry = 0.0;
    assert!(bad.validate().is_ok(), "0.0 (disabled) must validate");

    bad.limits.ft_min_notional_ratio_of_entry = 1.0;
    assert!(bad.validate().is_ok(), "1.0 boundary must validate");
}
