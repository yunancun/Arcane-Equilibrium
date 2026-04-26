//! Tests for StrategyOverride per-strategy SL/TP override schema (G2-03).
//! StrategyOverride 每策略 SL/TP 覆蓋 schema 測試（G2-03）。
//!
//! MODULE_NOTE (English):
//!   G2-03 (2026-04-26) extracted to a dedicated sibling test file (parent
//!   `risk_config_tests.rs` was approaching the §九 1200-line cap after the
//!   12 G2-03 tests landed). Loaded via `#[path]` mod inclusion in
//!   `risk_config_tests.rs`. The 12 tests cover defense line A
//!   (`RiskConfig::validate()` rejection of bad overrides + accepts good ones)
//!   and the TOML round-trip wire format. Defense line B (runtime cap)
//!   is tested in `risk_checks.rs` mod tests.
//!
//! MODULE_NOTE (中文):
//!   G2-03（2026-04-26）抽至獨立 sibling 測試檔（parent risk_config_tests.rs
//!   加入 12 個 G2-03 tests 後接近 §九 1200 行上限）。經 risk_config_tests.rs
//!   `#[path]` mod 載入。12 tests 覆蓋防線 A（validate 拒壞值 + 接好值）+
//!   TOML round-trip wire format；防線 B（runtime cap）測試在 risk_checks.rs。

use super::*;


// ===========================================================================
// G2-03 (2026-04-26) — StrategyOverride SL/TP override validation tests
// G2-03（2026-04-26）—— StrategyOverride SL/TP 覆蓋驗證測試
//
// Defense line A (PA RFC §3.1): RiskConfig::validate() rejects any per-strategy
// override that loosens SL/TP beyond P1 limits, or contains NaN/Inf/non-positive
// values. These tests lock in the schema + validate behaviour for G2-02 binding
// (T4 SOP) — failures here indicate a regression that would let bad config
// reach the runtime via IPC patch / TOML reload.
//
// 防線 A（PA RFC §3.1）：validate() 拒所有「比 P1 更鬆」的 per_strategy 覆蓋
// 與 NaN/Inf/非正值。這些測試鎖定 schema + validate 行為，回歸即代表 IPC patch
// / TOML reload 可能讓壞 config 進 runtime。
// ===========================================================================

#[test]
fn test_g2_03_strategy_override_default_all_overrides_none() {
    // G2-03: Default StrategyOverride has all SL/TP override fields = None
    // (i.e. fall back to global limits). Locks the "default = no override"
    // invariant — operators must explicitly opt in, never accidentally tighten.
    // G2-03：預設 StrategyOverride 所有 SL/TP 覆蓋為 None（走全局 limits）。
    let so = StrategyOverride::default();
    assert_eq!(so.stop_loss_max_pct_override, None);
    assert_eq!(so.take_profit_max_pct_override, None);
    assert_eq!(so.trailing_activation_pct_override, None);
    assert_eq!(so.trailing_distance_pct_override, None);
}

#[test]
fn test_g2_03_strategy_override_valid_within_limits() {
    // G2-03: Override <= limit must validate. Models the typical G2-03 binding
    // where ma_crossover gets tighter SL/TP after counterfactual review.
    // G2-03：override <= limits 應通過 validate（典型 binding 情境）。
    let mut cfg = RiskConfig::default();
    let mut so = StrategyOverride::default();
    so.stop_loss_max_pct_override = Some(3.0); // 3% < default 5%
    so.take_profit_max_pct_override = Some(15.0); // 15% < default 20%
    so.trailing_activation_pct_override = Some(0.8);
    so.trailing_distance_pct_override = Some(0.5);
    cfg.per_strategy.insert("ma_crossover".into(), so);
    let result = cfg.validate();
    assert!(
        result.is_ok(),
        "override within limits must pass: {:?}",
        result
    );
}

#[test]
fn test_g2_03_strategy_override_sl_over_limit_rejected() {
    // G2-03 defense line A: override > P1 stop-loss ceiling MUST be rejected.
    // This is the primary guarantee — never let a strategy loosen SL beyond P1.
    // G2-03 防線 A：override 超 P1 stop-loss 上限必拒（核心 P1 保證）。
    let mut cfg = RiskConfig::default(); // default stop_loss_max_pct = 5.0
    let mut so = StrategyOverride::default();
    so.stop_loss_max_pct_override = Some(7.0); // 7% > P1 5%, must reject
    cfg.per_strategy.insert("ma_crossover".into(), so);
    let result = cfg.validate();
    assert!(
        result.is_err(),
        "override > P1 stop_loss_max_pct must be rejected"
    );
    let err_msg = result.unwrap_err();
    assert!(
        err_msg.contains("ma_crossover")
            && err_msg.contains("stop_loss_max_pct_override")
            && err_msg.contains("P1"),
        "error message must reference strategy + field + P1: {}",
        err_msg
    );
}

#[test]
fn test_g2_03_strategy_override_tp_over_limit_rejected() {
    // G2-03 defense line A: TP override > P1 take_profit_max_pct must reject.
    // G2-03 防線 A：TP override 超 P1 必拒。
    let mut cfg = RiskConfig::default(); // default take_profit_max_pct = 20.0
    let mut so = StrategyOverride::default();
    so.take_profit_max_pct_override = Some(25.0); // > P1 20%
    cfg.per_strategy.insert("ma_crossover".into(), so);
    let result = cfg.validate();
    assert!(
        result.is_err(),
        "override > P1 take_profit_max_pct must be rejected"
    );
    assert!(result.unwrap_err().contains("take_profit_max_pct_override"));
}

#[test]
fn test_g2_03_strategy_override_nan_rejected() {
    // G2-03: NaN must be rejected — would silently bypass P1 comparison.
    // f64 NaN > 5.0 is false (IEEE 754); without explicit is_finite() guard,
    // NaN would slip past line A and reach runtime as a stealth value.
    // G2-03：NaN 必拒 —— 無 is_finite 守線時，NaN 比較皆 false，會偷渡 P1。
    let mut cfg = RiskConfig::default();
    let mut so = StrategyOverride::default();
    so.stop_loss_max_pct_override = Some(f64::NAN);
    cfg.per_strategy.insert("ma_crossover".into(), so);
    let result = cfg.validate();
    assert!(result.is_err(), "NaN override must be rejected");
    assert!(result.unwrap_err().contains("must be finite"));
}

#[test]
fn test_g2_03_strategy_override_infinity_rejected() {
    // G2-03: +Inf must be rejected. Like NaN, Inf would bypass naive < check
    // since `Inf > 5.0` is true (so > guard catches it) BUT we still want a
    // distinct "must be finite" error for diagnostics, not "exceeds P1".
    // G2-03：+Inf 必拒；雖 `Inf > 5.0` 真，但要求 finite 訊息利診斷。
    let mut cfg = RiskConfig::default();
    let mut so = StrategyOverride::default();
    so.take_profit_max_pct_override = Some(f64::INFINITY);
    cfg.per_strategy.insert("ma_crossover".into(), so);
    let result = cfg.validate();
    assert!(result.is_err(), "Inf override must be rejected");
    assert!(result.unwrap_err().contains("must be finite"));
}

#[test]
fn test_g2_03_strategy_override_negative_rejected() {
    // G2-03: Negative or zero override must be rejected — SL/TP pct must be
    // strictly positive (a 0% or -1% SL would be nonsensical).
    // G2-03：負值或零必拒（SL/TP pct 必正）。
    let mut cfg = RiskConfig::default();
    let mut so = StrategyOverride::default();
    so.stop_loss_max_pct_override = Some(-1.0);
    cfg.per_strategy.insert("ma_crossover".into(), so);
    let result = cfg.validate();
    assert!(result.is_err(), "negative override must be rejected");
    assert!(result.unwrap_err().contains("must be > 0"));

    // Zero is also rejected (>0 is required, not >=0).
    // 零亦拒（要求 >0 非 >=0）。
    let mut cfg2 = RiskConfig::default();
    let mut so2 = StrategyOverride::default();
    so2.take_profit_max_pct_override = Some(0.0);
    cfg2.per_strategy.insert("ma_crossover".into(), so2);
    assert!(cfg2.validate().is_err());
}

#[test]
fn test_g2_03_strategy_override_partial_fields_only_validates() {
    // G2-03: Setting only sl_override (not tp/trailing) must still validate
    // correctly — the other 3 None fields are no-op. Models the realistic case
    // where binding only constrains stop-loss (e.g. asymmetric counterfactual).
    // G2-03：只設一個 override 欄位也須通過 validate（其餘 None 不檢查）。
    let mut cfg = RiskConfig::default();
    let mut so = StrategyOverride::default();
    so.stop_loss_max_pct_override = Some(2.5);
    // tp/trailing intentionally None
    // tp/trailing 故意保留 None
    cfg.per_strategy.insert("ma_crossover".into(), so);
    assert!(cfg.validate().is_ok(), "partial override must validate");
}

#[test]
fn test_g2_03_strategy_override_trailing_negative_rejected() {
    // G2-03: trailing_*_override is not capped by P1 (no global limit) but must
    // still be > 0 + finite. Confirms the validate path covers all 4 fields.
    // G2-03：trailing_* override 不受 P1 限但須 >0 + finite，確保 4 欄位皆檢查。
    let mut cfg = RiskConfig::default();
    let mut so = StrategyOverride::default();
    so.trailing_activation_pct_override = Some(-0.5);
    cfg.per_strategy.insert("ma_crossover".into(), so);
    let result = cfg.validate();
    assert!(result.is_err(), "negative trailing must be rejected");
    let err = result.unwrap_err();
    assert!(err.contains("trailing_activation_pct_override") && err.contains("must be > 0"));
}

#[test]
fn test_g2_03_strategy_override_position_size_over_limit_rejected() {
    // G2-03: As a side benefit, validate_against_limits also covers existing
    // position_size_max_pct field (previously unvalidated). Confirms the new
    // validate hook closes a pre-G2-03 gap without breaking existing default.
    // G2-03 順帶驗：原 position_size_max_pct 之前未驗，本次 validate hook 補上。
    let mut cfg = RiskConfig::default(); // default position_size_max_pct = 20.0
    let mut so = StrategyOverride::default();
    so.position_size_max_pct = Some(30.0); // > P1 20%
    cfg.per_strategy.insert("ma_crossover".into(), so);
    let result = cfg.validate();
    assert!(
        result.is_err(),
        "position_size_max_pct > P1 must be rejected"
    );
    assert!(result.unwrap_err().contains("position_size_max_pct"));
}

#[test]
fn test_g2_03_real_toml_files_load_with_ma_crossover_section() {
    // G2-03 (2026-04-26): all three env risk_config_*.toml files must load + validate
    // with the new `[per_strategy.ma_crossover]` schema-only block. Catches typos
    // in commented-out field names + section header drift across env TOMLs.
    // Comments-only fields stay None; enabled=true is the only live setting.
    // G2-03：3 環境真實 TOML 必須 load + validate；catch 欄位拼寫漂移。
    // 註解欄位仍 None，僅 enabled=true 為 live 設定。
    use std::fs;
    use std::path::PathBuf;
    let mut srv_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    // CARGO_MANIFEST_DIR = srv/rust/openclaw_engine; up 3 levels → srv/.
    // CARGO_MANIFEST_DIR = srv/rust/openclaw_engine；上溯 3 層 → srv。
    srv_root.pop(); // openclaw_engine -> rust
    srv_root.pop(); // rust -> srv

    for toml_name in &[
        "risk_config_paper.toml",
        "risk_config_demo.toml",
        "risk_config_live.toml",
    ] {
        let path = srv_root
            .join("settings")
            .join("risk_control_rules")
            .join(toml_name);
        let toml_str = fs::read_to_string(&path)
            .unwrap_or_else(|e| panic!("failed to read {:?}: {}", path, e));
        let cfg: RiskConfig = toml::from_str(&toml_str)
            .unwrap_or_else(|e| panic!("TOML parse failed for {}: {}", toml_name, e));
        cfg.validate()
            .unwrap_or_else(|e| panic!("validate failed for {}: {}", toml_name, e));

        // Confirm the new ma_crossover section is present + override fields None
        // (commented-out in TOML, schema-only landing).
        // 確認 ma_crossover section 存在且 override 欄位為 None（schema-only）。
        let ma = cfg
            .per_strategy
            .get("ma_crossover")
            .unwrap_or_else(|| panic!("[per_strategy.ma_crossover] missing in {}", toml_name));
        assert!(ma.enabled, "ma_crossover.enabled must be true in {}", toml_name);
        assert_eq!(
            ma.stop_loss_max_pct_override, None,
            "{}: sl override must remain commented out (None)",
            toml_name
        );
        assert_eq!(
            ma.take_profit_max_pct_override, None,
            "{}: tp override must remain commented out (None)",
            toml_name
        );
        assert_eq!(
            ma.trailing_activation_pct_override, None,
            "{}: trailing_activation override must remain commented out",
            toml_name
        );
        assert_eq!(
            ma.trailing_distance_pct_override, None,
            "{}: trailing_distance override must remain commented out",
            toml_name
        );
    }
}

#[test]
fn test_g2_03_strategy_override_toml_round_trip_with_overrides() {
    // G2-03: TOML serialize/deserialize round-trip preserves override fields.
    // Locks the wire format invariant — operator-edited TOML must reach the
    // runtime exactly as written (no silent field drop).
    // G2-03：TOML round-trip 保留 override 欄位（防 wire format 漏寫漏讀）。
    let mut cfg = RiskConfig::default();
    let mut so = StrategyOverride::default();
    so.stop_loss_max_pct_override = Some(2.0);
    so.take_profit_max_pct_override = Some(8.0);
    so.trailing_activation_pct_override = Some(0.6);
    so.trailing_distance_pct_override = Some(0.4);
    cfg.per_strategy.insert("ma_crossover".into(), so);
    let toml_str = toml::to_string(&cfg).unwrap();
    let de: RiskConfig = toml::from_str(&toml_str).unwrap();
    let de_so = de.per_strategy.get("ma_crossover").expect("ma_crossover");
    assert_eq!(de_so.stop_loss_max_pct_override, Some(2.0));
    assert_eq!(de_so.take_profit_max_pct_override, Some(8.0));
    assert_eq!(de_so.trailing_activation_pct_override, Some(0.6));
    assert_eq!(de_so.trailing_distance_pct_override, Some(0.4));
    assert!(de.validate().is_ok());
}
