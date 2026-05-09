//! Strategy trait default behaviour + factory + TOML loader regression tests.
//! Strategy trait 默認行為 + 工廠 + TOML 載入器回歸測試。
//!
//! MODULE_NOTE (EN): All tests originally in `strategies::mod::tests` — moved verbatim
//!   to this sibling so the parent `mod.rs` stays under §九 1200-line hard cap.
//!   Kept under `#[cfg(test)]` and `mod tests` inside mod.rs (`#[path]` attribute),
//!   so test discovery / naming is identical (`strategies::tests::…`).
//! MODULE_NOTE (中): 原在 `strategies::mod::tests` 的全部測試 — 逐字搬到此 sibling，
//!   讓父層 `mod.rs` 保持在 §九 1200 行硬上限內。仍透過 `#[cfg(test)] mod tests`
//!   + `#[path]` 屬性掛回，測試命名（`strategies::tests::…`）與發現機制完全不變。

use super::*;
use crate::intent_processor::OrderIntent;
use crate::tick_pipeline::{PipelineKind, TickContext};

/// Minimal Strategy impl that exercises only the trait defaults.
/// 最小 Strategy 實現，僅用於驗證 trait 預設實現。
struct StubStrategy {
    active: bool,
}

impl Strategy for StubStrategy {
    fn name(&self) -> &str {
        "stub"
    }
    fn is_active(&self) -> bool {
        self.active
    }
    fn set_active(&mut self, active: bool) {
        self.active = active;
    }
    fn on_tick(&mut self, _ctx: &TickContext<'_>) -> Vec<StrategyAction> {
        Vec::new()
    }
}

#[test]
fn test_strategy_default_param_methods() {
    let mut s = StubStrategy { active: true };
    // update_params_json defaults to Err
    let err = s.update_params_json("{}").unwrap_err();
    assert!(err.contains("not implemented"));
    // get_params_json defaults to empty object
    assert_eq!(s.get_params_json(), "{}");
    // param_ranges_json defaults to empty array
    assert_eq!(s.param_ranges_json(), "[]");
}

#[test]
fn test_strategy_set_active_toggle() {
    let mut s = StubStrategy { active: false };
    assert!(!s.is_active());
    s.set_active(true);
    assert!(s.is_active());
    s.set_active(false);
    assert!(!s.is_active());
}

#[test]
fn test_strategy_default_on_rejection_and_on_fill_noop() {
    // Default impls should not panic on dummy inputs.
    // 預設實現對 dummy 輸入不應 panic。
    let mut s = StubStrategy { active: true };
    let intent = OrderIntent {
        symbol: "BTCUSDT".into(),
        is_long: true,
        qty: 0.01,
        confidence: 0.5,
        strategy: "stub".into(),
        order_type: "market".into(),
        limit_price: None,
        confluence_score: None,
        persistence_elapsed_ms: None,
        time_in_force: None,
        maker_timeout_ms: None,
    };
    s.on_rejection(&intent, "test reason");
    // No assertion — only checking no panic / 僅檢查不 panic
}

#[test]
fn test_param_range_serde_roundtrip() {
    let pr = ParamRange {
        name: "rsi_period".into(),
        min: 5.0,
        max: 50.0,
        step: Some(1.0),
        agent_adjustable: true,
        db_persisted: true,
    };
    let json = serde_json::to_string(&pr).expect("serialize");
    let de: ParamRange = serde_json::from_str(&json).expect("deserialize");
    assert_eq!(de.name, "rsi_period");
    assert!((de.min - 5.0).abs() < 1e-12);
    assert!((de.max - 50.0).abs() < 1e-12);
    assert_eq!(de.step, Some(1.0));
    assert!(de.agent_adjustable);
    assert!(de.db_persisted);
}

// ── 3E-9: StrategyFactory tests ──

#[test]
fn test_strategy_factory_creates_five_strategies() {
    let strategies = StrategyFactory::create_all();
    assert_eq!(
        strategies.len(),
        5,
        "factory should produce exactly 5 strategies"
    );
    let names: Vec<&str> = strategies.iter().map(|s| s.name()).collect();
    assert!(names.contains(&"ma_crossover"), "missing ma_crossover");
    assert!(names.contains(&"bb_reversion"), "missing bb_reversion");
    assert!(names.contains(&"bb_breakout"), "missing bb_breakout");
    assert!(names.contains(&"grid_trading"), "missing grid_trading");
    assert!(names.contains(&"funding_arb"), "missing funding_arb");
}

#[test]
fn test_strategy_factory_active_defaults() {
    let strategies = StrategyFactory::create_all();
    for s in &strategies {
        match s.name() {
            // OC-5: funding_arb inactive by default (TOML controls activation)
            "funding_arb" => {
                assert!(!s.is_active(), "funding_arb should be inactive by default")
            }
            _ => assert!(s.is_active(), "{} should be active by default", s.name()),
        }
    }
}

#[test]
fn test_param_range_continuous_step_none() {
    let pr = ParamRange {
        name: "weight".into(),
        min: 0.0,
        max: 1.0,
        step: None,
        agent_adjustable: false,
        db_persisted: false,
    };
    let json = serde_json::to_string(&pr).expect("serialize");
    assert!(json.contains("\"step\":null"));
}

// ── BLOCKER-8: StrategyParamsConfig + load_strategy_params tests ──

#[test]
fn test_strategy_params_config_default_matches_hardcoded() {
    // Default config must match what new() constructors produce.
    // 默認配置必須與 new() 構造器產出一致。
    let cfg = StrategyParamsConfig::default();
    assert_eq!(cfg.ma_crossover.cooldown_ms, 300_000);
    assert!((cfg.ma_crossover.adx_threshold - 20.0).abs() < 1e-10);
    assert!(cfg.ma_crossover.regime_filter_enabled);
    assert!((cfg.ma_crossover.higher_tf_alpha - 0.003).abs() < 1e-10);
    assert_eq!(cfg.bb_reversion.cooldown_ms, 600_000);
    assert!(!cfg.bb_reversion.use_limit);
    assert_eq!(cfg.bb_breakout.cooldown_ms, 600_000);
    assert!((cfg.bb_breakout.squeeze_bw - 0.02).abs() < 1e-10);
    assert!((cfg.bb_breakout.expansion_bw - 0.04).abs() < 1e-10);
    assert!(cfg.grid_trading.active);
    assert_eq!(cfg.grid_trading.grid_levels, 10);
}

#[test]
fn test_strategy_params_config_toml_roundtrip() {
    // Serialize to TOML and back — ensures no field mismatches.
    // 序列化到 TOML 再反序列化 — 確保無欄位不匹配。
    let cfg = StrategyParamsConfig::default();
    let toml_str = toml::to_string(&cfg).expect("serialize to TOML");
    let de: StrategyParamsConfig = toml::from_str(&toml_str).expect("deserialize from TOML");
    assert_eq!(de.ma_crossover.cooldown_ms, cfg.ma_crossover.cooldown_ms);
    assert!((de.bb_breakout.expansion_bw - cfg.bb_breakout.expansion_bw).abs() < 1e-10);
}

#[test]
fn test_load_strategy_params_from_file() {
    // Write a TOML with custom values, load it, verify non-default values applied.
    // 寫入自定義 TOML，加載並驗證非默認值已套用。
    let td = tempfile::tempdir().unwrap();
    let toml_content = r#"
[ma_crossover]
active = false
cooldown_ms = 120000
adx_threshold = 30.0
regime_filter_enabled = false
higher_tf_alpha = 0.005
conf_scale = 0.8

[bb_reversion]
cooldown_ms = 900000
use_limit = true
limit_offset_bps = 15.0

[bb_breakout]
squeeze_bw = 0.03
expansion_bw = 0.08

[grid_trading]
active = true
grid_levels = 20
"#;
    std::fs::write(td.path().join("strategy_params_paper.toml"), toml_content).unwrap();
    let cfg = load_strategy_params_from(PipelineKind::Paper, td.path());
    assert!(!cfg.ma_crossover.active);
    assert_eq!(cfg.ma_crossover.cooldown_ms, 120_000);
    assert!((cfg.ma_crossover.adx_threshold - 30.0).abs() < 1e-10);
    assert!(!cfg.ma_crossover.regime_filter_enabled);
    assert!((cfg.ma_crossover.higher_tf_alpha - 0.005).abs() < 1e-10);
    assert!((cfg.ma_crossover.conf_scale - 0.8).abs() < 1e-10);
    assert_eq!(cfg.bb_reversion.cooldown_ms, 900_000);
    assert!(cfg.bb_reversion.use_limit);
    assert!((cfg.bb_reversion.limit_offset_bps - 15.0).abs() < 1e-10);
    assert!((cfg.bb_breakout.squeeze_bw - 0.03).abs() < 1e-10);
    assert_eq!(cfg.grid_trading.grid_levels, 20);
}

#[test]
fn test_load_strategy_params_missing_file_demo_is_fail_closed_inactive() {
    // Demo/Live missing file must fail-closed to all inactive strategies.
    // Demo/Live 缺檔必須 fail-closed：所有策略 inactive。
    let td = tempfile::tempdir().unwrap();
    let cfg = load_strategy_params_from(PipelineKind::Demo, td.path());
    assert!(!cfg.ma_crossover.active);
    assert!(!cfg.bb_reversion.active);
    assert!(!cfg.bb_breakout.active);
    assert!(!cfg.grid_trading.active);
    assert!(!cfg.funding_arb.active);
}

#[test]
fn test_load_strategy_params_invalid_toml_live_is_fail_closed_inactive() {
    // Invalid Live TOML must fail closed (all strategies inactive).
    // Live TOML 解析失敗時必須 fail-closed（全部 inactive）。
    let td = tempfile::tempdir().unwrap();
    std::fs::write(td.path().join("strategy_params_live.toml"), "{{invalid}}").unwrap();
    let cfg = load_strategy_params_from(PipelineKind::Live, td.path());
    assert!(!cfg.ma_crossover.active);
    assert!(!cfg.bb_reversion.active);
    assert!(!cfg.bb_breakout.active);
    assert!(!cfg.grid_trading.active);
    assert!(!cfg.funding_arb.active);
}

#[test]
fn test_w_audit_6_real_strategy_params_keep_funding_arb_retired() {
    // W-AUDIT-6: funding_arb retirement is owned by strategy params, not by
    // RiskConfig per_strategy overrides.
    // W-AUDIT-6：funding_arb 退休由 strategy params 承載，不由 RiskConfig
    // per_strategy override 承載。
    let mut srv_root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    srv_root.pop(); // openclaw_engine -> rust
    srv_root.pop(); // rust -> srv
    let settings_dir = srv_root.join("settings");

    for kind in [PipelineKind::Paper, PipelineKind::Demo, PipelineKind::Live] {
        let cfg = load_strategy_params_from(kind, &settings_dir);
        assert!(
            !cfg.funding_arb.active,
            "{} funding_arb must stay inactive until a redesign explicitly re-enables it",
            kind
        );
        assert!(
            cfg.grid_trading
                .blocked_symbols
                .iter()
                .any(|s| s == "BILLUSDT"),
            "{} grid_trading must block BILLUSDT new entries after [40] negative-cell RCA",
            kind
        );
    }
}

#[test]
fn test_load_strategy_params_missing_file_paper_keeps_default_fallback() {
    // Paper keeps exploration fail-open defaults for local/dev workflows.
    // Paper 保留探索 fail-open 默認回退。
    let td = tempfile::tempdir().unwrap();
    let cfg = load_strategy_params_from(PipelineKind::Paper, td.path());
    assert!(cfg.ma_crossover.active);
    assert!(cfg.bb_reversion.active);
    assert!(cfg.bb_breakout.active);
    assert!(cfg.grid_trading.active);
}

#[test]
fn test_create_with_params_applies_active_flag() {
    // Strategies created with active=false should be inactive.
    // 使用 active=false 創建的策略應為非活躍。
    let mut p = StrategyParamsConfig::default();
    p.ma_crossover.active = false;
    p.bb_breakout.active = false;
    let strategies = StrategyFactory::create_with_params(&p);
    assert_eq!(strategies.len(), 5);
    for s in &strategies {
        match s.name() {
            "ma_crossover" | "bb_breakout" | "funding_arb" => {
                assert!(!s.is_active(), "{} should be inactive", s.name())
            }
            _ => assert!(s.is_active(), "{} should be active", s.name()),
        }
    }
}

#[test]
fn test_create_with_params_applies_conf_scale() {
    // Verify conf_scale is applied from params.
    // 驗證 conf_scale 從參數套用。
    let mut p = StrategyParamsConfig::default();
    p.ma_crossover.conf_scale = 0.5;
    let strategies = StrategyFactory::create_with_params(&p);
    let mac = strategies
        .iter()
        .find(|s| s.name() == "ma_crossover")
        .unwrap();
    assert!((mac.conf_scale() - 0.5).abs() < 1e-10);
}

// ── E5-P2-4: TOML default defaults must match pre-extraction hard-coded values ──
// ── E5-P2-4：TOML Default 需與原 hard-coded 值一致（bit-exact） ──

#[test]
fn test_e5_p2_4_bbb_toml_defaults_bit_exact() {
    // `strategies::BbBreakoutParams::default()` feeds factory → runtime when
    // TOML omits the fields. Must be byte-identical to previous hard-coded
    // literals so deployment without TOML changes is a no-op.
    // `strategies::BbBreakoutParams::default()` 是 TOML 缺欄位時的回退來源，
    // 需與原硬編碼數值位元相等，以保證不改 TOML 部署時行為零差異。
    let p = BbBreakoutParams::default();
    assert!(
        (p.hurst_regime_boost - 0.1).abs() < f64::EPSILON,
        "TOML default hurst_regime_boost must be 0.1"
    );
    assert!(
        (p.exit_bonus_trailing_stop - 0.2).abs() < f64::EPSILON,
        "TOML default exit_bonus_trailing_stop must be 0.2"
    );
    assert!(
        (p.exit_bonus_regime_shift - 0.1).abs() < f64::EPSILON,
        "TOML default exit_bonus_regime_shift must be 0.1"
    );
    assert!(
        (p.exit_bonus_pctb_revert - 0.05).abs() < f64::EPSILON,
        "TOML default exit_bonus_pctb_revert must be 0.05"
    );
    assert!(
        (p.exit_penalty_bw_squeeze - 0.05).abs() < f64::EPSILON,
        "TOML default exit_penalty_bw_squeeze must be 0.05"
    );
}

#[test]
fn test_e5_p2_4_bbb_toml_omitted_fields_fall_back_to_defaults() {
    // Writing a minimal TOML (only confluence bits) must leave the new
    // config-driven offsets at their hard-coded defaults.
    // 只寫入最小 TOML 時，新增的 config 欄位需回退到預設（bit-exact）。
    let td = tempfile::tempdir().unwrap();
    let toml_content = r#"
[bb_breakout]
squeeze_bw = 0.03
"#;
    std::fs::write(td.path().join("strategy_params_paper.toml"), toml_content).unwrap();
    let cfg = load_strategy_params_from(PipelineKind::Paper, td.path());
    assert!((cfg.bb_breakout.squeeze_bw - 0.03).abs() < f64::EPSILON);
    assert!(
        (cfg.bb_breakout.hurst_regime_boost - 0.1).abs() < f64::EPSILON,
        "omitted TOML → default 0.1"
    );
    assert!(
        (cfg.bb_breakout.exit_bonus_trailing_stop - 0.2).abs() < f64::EPSILON,
        "omitted TOML → default 0.2"
    );
}

#[test]
fn test_e5_p2_4_factory_wires_bbb_new_fields() {
    // Non-default TOML values must reach the live BbBreakout runtime via factory.
    // TOML 指定的非預設值需經工廠傳遞到運行時 BbBreakout。
    let mut p = StrategyParamsConfig::default();
    p.bb_breakout.hurst_regime_boost = 0.22;
    p.bb_breakout.exit_bonus_trailing_stop = 0.33;
    p.bb_breakout.exit_bonus_regime_shift = 0.11;
    p.bb_breakout.exit_bonus_pctb_revert = 0.09;
    p.bb_breakout.exit_penalty_bw_squeeze = 0.06;
    let strategies = StrategyFactory::create_with_params(&p);
    let bbb_any = strategies
        .iter()
        .find(|s| s.name() == "bb_breakout")
        .expect("bb_breakout strategy created");
    // Re-serialize via get_params_json for a type-erased runtime assertion.
    // 由於 trait object 無法 downcast，改用 get_params_json 做型別無關驗證。
    let json = bbb_any.get_params_json();
    assert!(
        json.contains("\"hurst_regime_boost\":0.22"),
        "factory must wire hurst_regime_boost=0.22 into runtime, got {json}"
    );
    assert!(
        json.contains("\"exit_bonus_trailing_stop\":0.33"),
        "factory must wire exit_bonus_trailing_stop=0.33 into runtime, got {json}"
    );
    assert!(
        json.contains("\"exit_bonus_regime_shift\":0.11"),
        "factory must wire exit_bonus_regime_shift=0.11 into runtime, got {json}"
    );
    assert!(
        json.contains("\"exit_bonus_pctb_revert\":0.09"),
        "factory must wire exit_bonus_pctb_revert=0.09 into runtime, got {json}"
    );
    assert!(
        json.contains("\"exit_penalty_bw_squeeze\":0.06"),
        "factory must wire exit_penalty_bw_squeeze=0.06 into runtime, got {json}"
    );
}

/// EDGE-P2-2 FUP #4: the TOML-path factory bypasses `bb_breakout::validate()`.
/// A malformed `oi_buffer_window_ms` (above upper bound) must fall back to the
/// serde default rather than silently poison the live strategy. The runtime
/// OI fields reach the live strategy only via `update_params_json` plumbing,
/// so we assert on the JSON echo.
/// EDGE-P2-2 FUP #4：TOML 路徑不走 validate，壞 window 需 fallback 默認，
/// 不靜默注入壞值。透過 get_params_json 驗證 runtime 接線。
#[test]
fn test_edge_p2_2_fup4_factory_falls_back_on_invalid_oi() {
    use serde_json::Value;

    let mut p = StrategyParamsConfig::default();
    p.bb_breakout.oi_buffer_window_ms = 10_000_000; // way above upper bound
    p.bb_breakout.oi_confluence_bonus = 0.8; // |value| > 0.5 invalid
    p.bb_breakout.oi_min_delta_pct = -0.01; // negative invalid

    let strategies = StrategyFactory::create_with_params(&p);
    let bbb = strategies
        .iter()
        .find(|s| s.name() == "bb_breakout")
        .expect("bb_breakout strategy created");
    let json = bbb.get_params_json();
    let v: Value = serde_json::from_str(&json).expect("runtime params deserialize");

    // Fallback to defaults (from default_bbb_oi_buffer_window_ms / _bonus / 0.0).
    assert_eq!(v["oi_buffer_window_ms"].as_u64(), Some(60_000));
    let bonus = v["oi_confluence_bonus"].as_f64().expect("f64");
    assert!((bonus - 0.10).abs() < f64::EPSILON);
    let floor = v["oi_min_delta_pct"].as_f64().expect("f64");
    assert!((floor - 0.0).abs() < f64::EPSILON);
}

/// FUP #4: happy-path — valid values reach the runtime untouched.
/// FUP #4 正向：合法值必須直通。
#[test]
fn test_edge_p2_2_fup4_factory_passes_valid_oi() {
    use serde_json::Value;

    let mut p = StrategyParamsConfig::default();
    p.bb_breakout.oi_buffer_window_ms = 120_000;
    p.bb_breakout.oi_confluence_bonus = 0.25;
    p.bb_breakout.oi_min_delta_pct = 0.03;

    let strategies = StrategyFactory::create_with_params(&p);
    let bbb = strategies
        .iter()
        .find(|s| s.name() == "bb_breakout")
        .expect("bb_breakout strategy created");
    let json = bbb.get_params_json();
    let v: Value = serde_json::from_str(&json).expect("runtime params deserialize");

    assert_eq!(v["oi_buffer_window_ms"].as_u64(), Some(120_000));
    let bonus = v["oi_confluence_bonus"].as_f64().expect("f64");
    assert!((bonus - 0.25).abs() < f64::EPSILON);
    let floor = v["oi_min_delta_pct"].as_f64().expect("f64");
    assert!((floor - 0.03).abs() < f64::EPSILON);
}

#[test]
fn test_e5_p2_4_grid_cooldown_toml_default_bit_exact() {
    // Default must match the `new_adaptive_with_mode` constructor literal
    // (60_000 ms) so the factory — now wiring cooldown_ms from TOML — does
    // not change behaviour for any existing deployment that omits the field.
    // 默認值需與 `new_adaptive_with_mode` constructor literal（60_000 ms）一致，
    // 使工廠新增的 TOML wiring 在未設 cooldown_ms 的部署下行為不變。
    let p = GridTradingParams::default();
    assert_eq!(
        p.cooldown_ms, 60_000,
        "grid_trading.cooldown_ms TOML default must equal constructor literal 60_000"
    );
}

#[test]
fn test_e5_p2_4_grid_cooldown_factory_wires_value() {
    // Factory must propagate TOML cooldown_ms to the runtime grid strategy.
    // Previously this field was unreachable from TOML; now covered.
    // 工廠需將 TOML cooldown_ms 傳遞到 grid 策略運行時；原本 TOML 無法觸及，現已補齊。
    let mut p = StrategyParamsConfig::default();
    p.grid_trading.cooldown_ms = 123_456;
    let strategies = StrategyFactory::create_with_params(&p);
    let gt_any = strategies
        .iter()
        .find(|s| s.name() == "grid_trading")
        .expect("grid_trading strategy created");
    let json = gt_any.get_params_json();
    assert!(
        json.contains("\"cooldown_ms\":123456"),
        "factory must wire cooldown_ms=123456 into runtime grid strategy, got {json}"
    );
}

#[test]
fn test_e5_p2_4_grid_cooldown_toml_roundtrip() {
    // TOML round-trip must preserve the new cooldown_ms value.
    // TOML 序列化往返需保留新的 cooldown_ms 值。
    let mut cfg = StrategyParamsConfig::default();
    cfg.grid_trading.cooldown_ms = 90_000;
    let toml_str = toml::to_string(&cfg).expect("serialize to TOML");
    let de: StrategyParamsConfig = toml::from_str(&toml_str).expect("deserialize from TOML");
    assert_eq!(de.grid_trading.cooldown_ms, 90_000);
}

// ── EDGE-P2-3 Phase 1B-3.1: maker_limit_timeout_ms plumbing ──
// ── EDGE-P2-3 Phase 1B-3.1：maker_limit_timeout_ms 配置接線 ──

#[test]
fn test_edge_p2_3_1b31_maker_timeout_toml_default_bit_exact() {
    // Default must equal the canonical 45_000 ms (P0 QC design budget).
    // 默認值需等於規格 45_000 ms（P0 QC 設計預算）。
    let p = GridTradingParams::default();
    assert_eq!(
        p.maker_limit_timeout_ms, 45_000,
        "grid_trading.maker_limit_timeout_ms default must be 45_000"
    );
}

#[test]
fn test_edge_p2_3_1b31_maker_timeout_toml_roundtrip() {
    // TOML round-trip must preserve the configured timeout.
    // TOML 往返需保留設定值。
    let mut cfg = StrategyParamsConfig::default();
    cfg.grid_trading.maker_limit_timeout_ms = 60_000;
    let toml_str = toml::to_string(&cfg).expect("serialize to TOML");
    let de: StrategyParamsConfig = toml::from_str(&toml_str).expect("deserialize from TOML");
    assert_eq!(de.grid_trading.maker_limit_timeout_ms, 60_000);
}

#[test]
fn test_edge_p2_3_1b31_maker_timeout_factory_clamps_low_value() {
    // Factory must clamp below-floor TOML values up to MIN (15_000 ms).
    // 工廠對低於下限的 TOML 值需 clamp 到 MIN (15_000 ms)。
    let mut p = StrategyParamsConfig::default();
    p.grid_trading.maker_limit_timeout_ms = 1_000; // below 15_000 floor
    let strategies = StrategyFactory::create_with_params(&p);
    let gt_any = strategies
        .iter()
        .find(|s| s.name() == "grid_trading")
        .expect("grid_trading strategy created");
    let json = gt_any.get_params_json();
    assert!(
        json.contains("\"maker_limit_timeout_ms\":15000"),
        "factory must clamp 1_000 → 15_000, got {json}"
    );
}

#[test]
fn test_edge_p2_3_1b31_maker_timeout_factory_clamps_high_value() {
    // Factory must clamp above-ceiling TOML values down to MAX (300_000 ms).
    // 工廠對超過上限的 TOML 值需 clamp 到 MAX (300_000 ms)。
    let mut p = StrategyParamsConfig::default();
    p.grid_trading.maker_limit_timeout_ms = 10_000_000; // above 300_000 ceiling
    let strategies = StrategyFactory::create_with_params(&p);
    let gt_any = strategies
        .iter()
        .find(|s| s.name() == "grid_trading")
        .expect("grid_trading strategy created");
    let json = gt_any.get_params_json();
    assert!(
        json.contains("\"maker_limit_timeout_ms\":300000"),
        "factory must clamp 10_000_000 → 300_000, got {json}"
    );
}

#[test]
fn test_edge_p2_3_1b31_maker_timeout_factory_passes_through_in_range() {
    // Within-range TOML value must flow through unchanged.
    // 在範圍內的 TOML 值需原樣傳遞。
    let mut p = StrategyParamsConfig::default();
    p.grid_trading.maker_limit_timeout_ms = 60_000;
    let strategies = StrategyFactory::create_with_params(&p);
    let gt_any = strategies
        .iter()
        .find(|s| s.name() == "grid_trading")
        .expect("grid_trading strategy created");
    let json = gt_any.get_params_json();
    assert!(
        json.contains("\"maker_limit_timeout_ms\":60000"),
        "factory must pass 60_000 through unchanged, got {json}"
    );
}
