//! Strategy trait default behaviour + factory + TOML loader regression tests.
//! Strategy trait 默認行為 + 工廠 + TOML 載入器回歸測試。
//!
//! MODULE_NOTE (EN): All tests originally in `strategies::mod::tests` — moved verbatim
//!   to this sibling so the parent `mod.rs` stays under §九 2000-line hard cap.
//!   Kept under `#[cfg(test)]` and `mod tests` inside mod.rs (`#[path]` attribute),
//!   so test discovery / naming is identical (`strategies::tests::…`).
//! MODULE_NOTE (中): 原在 `strategies::mod::tests` 的全部測試 — 逐字搬到此 sibling，
//!   讓父層 `mod.rs` 保持在 §九 2000 行硬上限內。仍透過 `#[cfg(test)] mod tests`
//!   + `#[path]` 屬性掛回，測試命名（`strategies::tests::…`）與發現機制完全不變。

use super::*;
use crate::intent_processor::OrderIntent;
use crate::tick_pipeline::{PipelineKind, TickContext};
use openclaw_core::alpha_surface::{AlphaSourceTag, AlphaSurface};

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
    fn declared_alpha_sources(&self) -> &[AlphaSourceTag] {
        const TAGS: &[AlphaSourceTag] = &[AlphaSourceTag::Ta1m];
        TAGS
    }
    fn on_tick(
        &mut self,
        _ctx: &TickContext<'_>,
        _surface: &AlphaSurface<'_>,
    ) -> Vec<StrategyAction> {
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
        // Sprint 1B Earn first stake — IntentType backward-compat 占位。
        intent_type: crate::intent_processor::IntentType::OpenLong,
        earn_payload: None,
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
fn test_strategy_factory_creates_six_strategies() {
    // Sprint 1B Pending 3.1 C10：funding_harvest 作為第 6 個 strategy。
    // Sprint 2 W2-B：funding_short_v2 + liquidation_cascade_fade 加入為第 7-8 strategy
    // （Alpha Tournament Stream A Candidate #1 + #4；與 funding_arb V2 dormant 並列）。
    // 測試名稱保留為 `creates_six_strategies` 以保留歷史檢核；但 assertion 更新為 8。
    let strategies = StrategyFactory::create_all();
    assert_eq!(
        strategies.len(),
        8,
        "factory should produce exactly 8 strategies after Sprint 2 W2-B funding_short_v2 + liquidation_cascade_fade landing"
    );
    let names: Vec<&str> = strategies.iter().map(|s| s.name()).collect();
    assert!(names.contains(&"ma_crossover"), "missing ma_crossover");
    assert!(names.contains(&"bb_reversion"), "missing bb_reversion");
    assert!(names.contains(&"bb_breakout"), "missing bb_breakout");
    assert!(names.contains(&"grid_trading"), "missing grid_trading");
    assert!(names.contains(&"funding_arb"), "missing funding_arb");
    assert!(
        names.contains(&"funding_harvest"),
        "missing funding_harvest (Sprint 1B C10)"
    );
    assert!(
        names.contains(&"funding_short_v2"),
        "missing funding_short_v2 (Sprint 2 W2-B Candidate #1)"
    );
    assert!(
        names.contains(&"liquidation_cascade_fade"),
        "missing liquidation_cascade_fade (Sprint 2 W2-B Candidate #4)"
    );
}

// ── FLASH-DIP-PILOT kind-aware demo-gate 負測（CC 條件 4 / E3 MED-1 grep-proof）──

/// 序列化 env-sensitive 測試。
///
/// 為什麼要鎖：`create_for_engine` 讀兩個 process-wide 狀態——
/// `OPENCLAW_FLASH_DIP_PILOT_ENABLED`（flag）與 `OPENCLAW_BASE_DIR`
/// （`settings_dir()` 據此定位 `strategy_params_demo.toml`）。多測試並行改
/// 同一 env 會互相污染，故所有讀寫此二 env 的測試共用同一鎖串行化。
static FLASH_DIP_ENV_LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());

fn flash_dip_count(strategies: &[Box<dyn super::Strategy>]) -> usize {
    strategies
        .iter()
        .filter(|s| s.name() == "flash_dip_buy")
        .count()
}

/// 在受控 env 下執行 flash_dip gate 測試，回傳閉包結果。
///
/// 為什麼需要此 helper（根因）：`create_for_engine` 經 `settings_dir()` 讀
/// `OPENCLAW_BASE_DIR/settings/strategy_params_demo.toml`（缺 BASE_DIR 時退回
/// cwd-相對 `./settings`）。直接依賴 ambient 磁碟會令測試同時受「cwd」與
/// 「operator 可變的 repo toml `[flash_dip_buy].active`」影響——後者現為
/// `active=true`（operator 2026-06-18 啟用 pilot），使斷言 active=false 的測試
/// 在 BASE_DIR 存在時 FAIL、缺失時 PASS，成環境相依的脆弱測試。
///
/// 此 helper 把 BASE_DIR 指向臨時目錄並寫入 test 自控的 demo toml（`active`
/// 值由參數決定），閉包結束後還原原 env，讓測試 cwd-independent 且
/// env-isolated。`pilot_flag_on` 控制是否設 flag。全程持 `FLASH_DIP_ENV_LOCK`。
fn with_flash_dip_env<T>(demo_active: bool, pilot_flag_on: bool, body: impl FnOnce() -> T) -> T {
    const FLAG_ENV: &str = "OPENCLAW_FLASH_DIP_PILOT_ENABLED";
    const BASE_ENV: &str = "OPENCLAW_BASE_DIR";
    let _g = FLASH_DIP_ENV_LOCK.lock().unwrap();

    // 保存原 env，測試後精確還原（成對 set/remove，禁洩漏到其他測試）。
    let prev_flag = std::env::var(FLAG_ENV).ok();
    let prev_base = std::env::var(BASE_ENV).ok();

    let td = tempfile::tempdir().unwrap();
    let settings = td.path().join("settings");
    std::fs::create_dir_all(&settings).unwrap();
    // 只寫 gate 決策所需欄位；其餘 `#[serde(default)]`。active=true 時附合法參數
    // 以通過 `FlashDipBuyParams::validate()`（否則 fail-closed 不註冊會混淆語意）。
    let toml = if demo_active {
        "[flash_dip_buy]\nactive = true\nk_dip = 0.15\nhold_days = 3\nmax_concurrent = 1\nnotional_frac = 0.01\nallowed_symbols = [\"BTCUSDT\"]\n"
    } else {
        "[flash_dip_buy]\nactive = false\n"
    };
    std::fs::write(settings.join("strategy_params_demo.toml"), toml).unwrap();

    std::env::set_var(BASE_ENV, td.path());
    if pilot_flag_on {
        std::env::set_var(FLAG_ENV, "1");
    } else {
        std::env::remove_var(FLAG_ENV);
    }

    let out = body();

    // 還原：有原值則寫回，無則移除。
    match prev_base {
        Some(v) => std::env::set_var(BASE_ENV, v),
        None => std::env::remove_var(BASE_ENV),
    }
    match prev_flag {
        Some(v) => std::env::set_var(FLAG_ENV, v),
        None => std::env::remove_var(FLAG_ENV),
    }
    out
}

#[test]
fn test_flash_dip_never_in_create_all_or_create_with_params() {
    // create_all / create_with_params 為 kind-blind（亦被 replay_runner 用）→ 必 0 次。
    assert_eq!(
        flash_dip_count(&StrategyFactory::create_all()),
        0,
        "flash_dip_buy must NEVER be in create_all (kind-blind path)"
    );
    let cfg = super::params::StrategyParamsConfig::default();
    assert_eq!(
        flash_dip_count(&StrategyFactory::create_with_params(&cfg)),
        0,
        "flash_dip_buy must NEVER be in create_with_params (kind-blind path)"
    );
}

#[test]
fn test_flash_dip_demo_gate_flag_off_zero_registration() {
    // flag OFF → 即使 Demo + toml active=true 也 0 次（flag 為第一必要條件）。
    // 參數：demo_active=true（施壓，證 flag 短路先於 active），pilot_flag_on=false。
    let demo = with_flash_dip_env(true, false, || {
        flash_dip_count(&StrategyFactory::create_for_engine(
            PipelineKind::Demo,
            None,
        ))
    });
    assert_eq!(
        demo, 0,
        "flag OFF must yield 0 flash_dip_buy registration even in Demo"
    );
}

#[test]
fn test_flash_dip_never_in_paper_or_live_even_with_flag_on() {
    // 強制 flag ON + toml active=true：仍只有 Demo 可能註冊；Paper / Live 結構性 0 次。
    // 參數：demo_active=true（施壓，證 kind gate 單獨即擋住 Paper/Live，與 active 無關），
    // pilot_flag_on=true。
    let (paper, live) = with_flash_dip_env(true, true, || {
        let paper = flash_dip_count(&StrategyFactory::create_for_engine(
            PipelineKind::Paper,
            None,
        ));
        let live = flash_dip_count(&StrategyFactory::create_for_engine(
            PipelineKind::Live,
            None,
        ));
        (paper, live)
    });
    assert_eq!(
        paper, 0,
        "flash_dip_buy must NEVER register in Paper pipeline"
    );
    assert_eq!(
        live, 0,
        "flash_dip_buy must NEVER register in Live pipeline"
    );
}

#[test]
fn test_flash_dip_demo_gate_requires_all_three_conditions() {
    // 三合一 gate：Demo + flag-ON + active=true。此測試以 test 自控 toml
    // 顯式設 [flash_dip_buy].active=false，證「flag-ON + Demo 但 active=false
    // → 不註冊」（active 為第三必要條件）。
    //
    // 為何用受控 toml 而非 repo settings：repo `strategy_params_demo.toml` 的
    // active 由 operator 掌控（現為 true，2026-06-18 啟用 pilot），直接讀會使
    // 本測試變環境相依而 flaky；`with_flash_dip_env` 令其 cwd/env-independent。
    // 參數：demo_active=false（第三 gate active 缺席），pilot_flag_on=true。
    let demo = with_flash_dip_env(false, true, || {
        flash_dip_count(&StrategyFactory::create_for_engine(
            PipelineKind::Demo,
            None,
        ))
    });
    assert_eq!(
        demo, 0,
        "Demo + flag-ON but active=false must NOT register \
         (active is the third required gate condition)"
    );
}

#[test]
fn test_strategy_factory_liquidation_cascade_consumer_gate_after_stage0r_launch() {
    // W-AUDIT-8a C1 / W-AUDIT-8c boundary guard 演進至 Sprint 2 W2-B：
    //
    // 原 invariant：「factory must not expose a live LiquidationCascade consumer
    //   before an explicit Stage 0R launch packet」。Sprint 2 W2-B 落地 explicit
    //   launch packet = `2026-05-25--alpha_candidate_4_liquidation_cascade_fade_spec.md v1.1`
    //   + W2-A finalize report；因此 LiquidationCascade consumer 已允許暴露於 factory，
    //   但仍須 active=false default（5-gate auto path inheritance + operator
    //   IPC active=true 才啟）。
    //
    // 新 invariant：
    //   (a) 唯一允許的 LiquidationCascade consumer = `liquidation_cascade_fade`；
    //   (b) 其 active flag 在 `create_all()` (default params) 必為 false；
    //   (c) 任何其他策略仍禁止 declare LiquidationCascade。
    let strategies = StrategyFactory::create_all();
    let mut lcf_consumer_found = false;
    for strategy in &strategies {
        let consumes_liq = strategy
            .declared_alpha_sources()
            .contains(&AlphaSourceTag::LiquidationCascade);
        if strategy.name() == "liquidation_cascade_fade" {
            assert!(
                consumes_liq,
                "liquidation_cascade_fade must declare LiquidationCascade"
            );
            assert!(
                !strategy.is_active(),
                "liquidation_cascade_fade default must be inactive (Stage 1 Demo fail-closed)"
            );
            lcf_consumer_found = true;
        } else {
            assert!(
                !consumes_liq,
                "{} must not consume LiquidationCascade (only liquidation_cascade_fade allowed)",
                strategy.name()
            );
        }
    }
    assert!(
        lcf_consumer_found,
        "liquidation_cascade_fade must be present in StrategyFactory (Sprint 2 W2-B)"
    );
}

#[test]
fn test_strategy_factory_active_defaults() {
    let strategies = StrategyFactory::create_all();
    for s in &strategies {
        match s.name() {
            // OC-5: funding_arb inactive by default (TOML controls activation)。
            // Sprint 1B C10: funding_harvest inactive by default (Stage 0R PASS +
            //   operator IPC active=true 才啟；參見 strategies/funding_harvest/params.rs)。
            // Sprint 2 W2-B: funding_short_v2 + liquidation_cascade_fade inactive
            //   by default (5-gate auto path inheritance fail-closed + operator
            //   IPC active=true 才啟；per CR-15)。
            "funding_arb"
            | "funding_harvest"
            | "funding_short_v2"
            | "liquidation_cascade_fade" => {
                assert!(!s.is_active(), "{} should be inactive by default", s.name())
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
    assert_eq!(cfg.bb_breakout.signal_timeframe, "1m");
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
signal_timeframe = "5m"
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
    assert_eq!(cfg.bb_breakout.signal_timeframe, "5m");
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
        assert_eq!(
            cfg.bb_breakout.signal_timeframe, "5m",
            "{} bb_breakout must use the W-AUDIT-6 5m signal family",
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
    // Sprint 1B C10：funding_harvest 也是 default active=false（fail-closed）。
    // Sprint 2 W2-B：funding_short_v2 + liquidation_cascade_fade 同 default false。
    let mut p = StrategyParamsConfig::default();
    p.ma_crossover.active = false;
    p.bb_breakout.active = false;
    let strategies = StrategyFactory::create_with_params(&p);
    assert_eq!(strategies.len(), 8);
    for s in &strategies {
        match s.name() {
            "ma_crossover"
            | "bb_breakout"
            | "funding_arb"
            | "funding_harvest"
            | "funding_short_v2"
            | "liquidation_cascade_fade" => {
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
    assert_eq!(
        p.signal_timeframe, "1m",
        "TOML default signal_timeframe must stay 1m for backward compatibility"
    );
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
    p.bb_breakout.signal_timeframe = "5m".to_string();
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
        json.contains("\"signal_timeframe\":\"5m\""),
        "factory must wire signal_timeframe=5m into runtime, got {json}"
    );
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
fn test_w_audit_6_factory_falls_back_on_invalid_bbb_signal_timeframe() {
    use serde_json::Value;

    let mut p = StrategyParamsConfig::default();
    p.bb_breakout.signal_timeframe = "15m".to_string();

    let strategies = StrategyFactory::create_with_params(&p);
    let bbb = strategies
        .iter()
        .find(|s| s.name() == "bb_breakout")
        .expect("bb_breakout strategy created");
    let json = bbb.get_params_json();
    let v: Value = serde_json::from_str(&json).expect("runtime params deserialize");

    assert_eq!(v["signal_timeframe"].as_str(), Some("1m"));
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

// ── b85ac3f3 confluence DB-load guard 回歸測試 ──────────────────────────────

/// DB/TOML 來源的非法權重（和≠65）必須觸發 fail-closed 退回預設值。
/// 驗證三個策略的 build_confluence_config() 在非法輸入下均安全退回。
/// 額外驗證：bb_breakout 退回時保留 confluence_as_gate 語意（不翻轉）。
#[test]
fn test_build_confluence_config_invalid_weights_falls_back_to_default() {
    // ── ma_crossover：權重和 73≠65，預期退回 ConfluenceConfig::default() ──
    let mut ma_p = MaCrossoverParams::default();
    ma_p.weight_adx = 30.0; // 30+20+12+8 = 70 ≠ 65
    let cfg_ma = ma_p.build_confluence_config();
    let expected_ma = confluence::ConfluenceConfig::default();
    assert!(
        (cfg_ma.weight_adx - expected_ma.weight_adx).abs() < 1e-10,
        "ma_crossover 非法權重應退回預設 weight_adx={}, got {}",
        expected_ma.weight_adx,
        cfg_ma.weight_adx
    );
    assert!(
        (cfg_ma.weight_regime - expected_ma.weight_regime).abs() < 1e-10,
        "ma_crossover 非法權重應退回預設 weight_regime={}, got {}",
        expected_ma.weight_regime,
        cfg_ma.weight_regime
    );
    assert_eq!(
        cfg_ma.confluence_as_gate, expected_ma.confluence_as_gate,
        "ma_crossover 退回時 confluence_as_gate 應為 true"
    );

    // ── bb_reversion：權重和 80≠65，預期退回 ConfluenceConfig::reversion() ──
    let mut bbr_p = BbReversionParams::default();
    bbr_p.weight_regime = 45.0; // 15+45+10+10 = 80 ≠ 65
    let cfg_bbr = bbr_p.build_confluence_config();
    let expected_bbr = confluence::ConfluenceConfig::reversion();
    assert!(
        (cfg_bbr.weight_adx - expected_bbr.weight_adx).abs() < 1e-10,
        "bb_reversion 非法權重應退回 reversion weight_adx={}, got {}",
        expected_bbr.weight_adx,
        cfg_bbr.weight_adx
    );
    assert!(
        (cfg_bbr.weight_regime - expected_bbr.weight_regime).abs() < 1e-10,
        "bb_reversion 非法權重應退回 reversion weight_regime={}, got {}",
        expected_bbr.weight_regime,
        cfg_bbr.weight_regime
    );
    // invert_adx 由 reversion() 提供 true
    assert!(
        cfg_bbr.invert_adx,
        "bb_reversion 退回時 invert_adx 應為 true"
    );

    // ── bb_breakout：權重和 60≠65，confluence_as_gate=true 語意必須保留 ──
    let mut bbb_p = BbBreakoutParams::default();
    bbb_p.weight_adx = 20.0; // 20+20+12+8 = 60 ≠ 65
    bbb_p.confluence_as_gate = true; // 故意設成非默認值以驗證語意保留
    let cfg_bbb = bbb_p.build_confluence_config();
    // 權重應退回 ConfluenceConfig::breakout() 的預設權重
    let expected_bbb = confluence::ConfluenceConfig::breakout();
    assert!(
        (cfg_bbb.weight_adx - expected_bbb.weight_adx).abs() < 1e-10,
        "bb_breakout 非法權重應退回 breakout weight_adx={}, got {}",
        expected_bbb.weight_adx,
        cfg_bbb.weight_adx
    );
    // confluence_as_gate 保留 self 的值（true），不被退回邏輯翻轉
    assert!(
        cfg_bbb.confluence_as_gate,
        "bb_breakout 退回時 confluence_as_gate 語意必須保留（self.confluence_as_gate=true）"
    );

    // ── 正常路徑驗證：合法權重（和=65）直通不退回 ──
    let valid_p = MaCrossoverParams::default(); // 25+20+12+8 = 65
    let cfg_valid = valid_p.build_confluence_config();
    assert!(
        (cfg_valid.weight_adx - 25.0).abs() < 1e-10,
        "合法權重應直通，weight_adx 應為 25.0, got {}",
        cfg_valid.weight_adx
    );
}
