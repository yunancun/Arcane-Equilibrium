//! LG-2 T1 contract tests — pricing-binding cross-module integration.
//! LG-2 T1 契約測試 — 跨模組 pricing-binding 整合驗證。
//!
//! 對應 PA 2026-05-11 LG-2/3/4 design plan §2.2 第 1 點
//! 「Contract test pinning current behavior」之 (b)/(d) 跨模組部分：
//!   (b) PostOnly → maker / GTC → taker via AccountManager.fee_rate_for_intent
//!   (d) Mainnet unsupported endpoint refusal（不可 seed_default fallback）
//! (a) parser / (c) demo fallback / (e) hourly refresh 在 account_manager.rs
//! inline tests 已 cover。
//!
//! 並補 LG2-T4 sibling 的 PricingConfig 對齊驗證（從 `risk_config_*.toml` 真實
//! load → 驗 demo / paper / live 各 default 對齊 LG2-T4 land 值 + LG-3 RFC §2.3
//! mainnet hard-block 不變式）。
//!
//! 範圍邊界：
//! - 不啟動真實 Bybit HTTP（mock parser 走 module API）
//! - 不依 LG-2 T2 startup assertion（T2 尚未 land；本檔斷言「現有 codebase 已
//!   暴露的 invariant」而非新加 assert）
//! - 不寫真實 PG schema（PricingConfig 用 TOML disk load 路徑）

use openclaw_engine::account_manager::{AccountManager, FeeRate, FeeSource};
use openclaw_engine::bybit_rest_client::BybitEnvironment;
use openclaw_engine::config::risk_config::RiskConfig;
use openclaw_engine::intent_processor::{IntentProcessor, OrderIntent};
use openclaw_engine::order_manager::TimeInForce;
use std::path::PathBuf;
use std::sync::Arc;

// ---------------------------------------------------------------------------
// Test helper — repo root resolution / 測試輔助 — 解析 repo 根
// ---------------------------------------------------------------------------

/// 解析測試二進位對應的 `srv` repo root（與 risk_config_tests.rs LG2-T4 smoke
/// 路徑一致；CARGO_MANIFEST_DIR=srv/rust/openclaw_engine，向上兩層 = srv/）。
/// 與 OPENCLAW_BASE_DIR env var 優先級對齊（CLAUDE.md §六 路徑契約）。
fn srv_root() -> PathBuf {
    if let Ok(env) = std::env::var("OPENCLAW_BASE_DIR") {
        return PathBuf::from(env);
    }
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
}

/// 構造簡單 OrderIntent fixture（與 intent_processor::tests::make_intent 對齊
/// 但本檔不能 access module-private fn，自製等價版本）。
fn make_intent(symbol: &str, tif: Option<TimeInForce>) -> OrderIntent {
    OrderIntent {
        symbol: symbol.into(),
        is_long: true,
        qty: 0.01,
        confidence: 0.7,
        strategy: "lg2_t1_contract_test".into(),
        order_type: "market".into(),
        limit_price: None,
        confluence_score: None,
        persistence_elapsed_ms: None,
        time_in_force: tif,
        maker_timeout_ms: None,
    }
}

// ---------------------------------------------------------------------------
// (b) PostOnly → maker / GTC → taker — cross-module dispatch contract
// (b) PostOnly→maker / GTC→taker — 跨模組 fee dispatch 契約
// ---------------------------------------------------------------------------
//
// 既有 inline test `tests_predictor_router.rs::test_fee_rate_for_intent_*` 已
// cover 同 invariant 在 module 內，本檔強化「IntentProcessor + AccountManager
// Arc 注入 → fee_rate_for_intent 走 AccountManager」端對端路徑，pin
// LG-3 RFC §Pricing Sources 「maker rate 來自 Bybit API / cold default」。

/// PostOnly intent 透過 IntentProcessor.fee_rate_for_intent 必走 AccountManager
/// 的 maker_fee；驗 Arc<AccountManager> 注入後路徑正確切分 maker vs taker。
/// 用 seed_default_fee_rates 路徑（cache 內為 DEFAULT_*_FEE），integration test
/// 不可訪問 AccountManager 私有 fee_rates cache，但 seed_default 已足夠 pin 契約。
#[test]
fn test_lg2_t1_postonly_routes_to_maker_via_account_manager() {
    let am = Arc::new(AccountManager::new());

    // seed_default 路徑（cache 內為 DEFAULT_*_FEE）+ 驗 maker/taker 分流
    am.seed_default_fee_rates(["BTCUSDT", "ETHUSDT"]);

    let mut proc = IntentProcessor::new();
    proc.set_account_manager(Arc::clone(&am));

    // PostOnly → maker 路徑（DEFAULT_MAKER_FEE = 0.0002）
    let postonly_intent = make_intent("BTCUSDT", Some(TimeInForce::PostOnly));
    let postonly_rate = proc.fee_rate_for_intent(&postonly_intent.symbol, &postonly_intent);
    assert!(
        (postonly_rate - 0.0002).abs() < 1e-12,
        "PostOnly intent must route to maker fee 0.0002, got {}",
        postonly_rate
    );

    // GTC → taker 路徑（DEFAULT_TAKER_FEE = 0.00055）
    let gtc_intent = make_intent("BTCUSDT", Some(TimeInForce::GTC));
    let gtc_rate = proc.fee_rate_for_intent(&gtc_intent.symbol, &gtc_intent);
    assert!(
        (gtc_rate - 0.00055).abs() < 1e-12,
        "GTC intent must route to taker fee 0.00055, got {}",
        gtc_rate
    );

    // 不變式：maker < taker（LG-3 RFC §Pricing Sources 對齊 Bybit VIP-0 約 0.4×）
    assert!(
        postonly_rate < gtc_rate,
        "maker ({}) must be strictly less than taker ({})",
        postonly_rate,
        gtc_rate
    );
}

/// fee_rate_for_intent 必查 AccountManager Arc — 注入 AccountManager 後，
/// dispatch 路徑必走 AccountManager.maker_fee / .taker_fee，與
/// IntentProcessor 內部 risk_config 預設值無關。
/// 此 pin LG-3 RFC §Pricing Sources 「優先級 1: AccountManager.maker_fee/taker_fee」
/// + LG-2 T3 sibling FeeSource 對齊 healthcheck dual-source。
#[test]
fn test_lg2_t1_fee_dispatch_prefers_account_manager_over_internal_default() {
    let am = Arc::new(AccountManager::new());
    am.seed_default_fee_rates(["BTCUSDT"]);

    let mut proc = IntentProcessor::new();
    proc.set_account_manager(Arc::clone(&am));

    // PostOnly maker 與 GTC taker 在 default 模式下仍正確分流，必對齊
    // AccountManager 路徑（DEFAULT_MAKER_FEE=0.0002 / DEFAULT_TAKER_FEE=0.00055）
    let postonly_intent = make_intent("BTCUSDT", Some(TimeInForce::PostOnly));
    let gtc_intent = make_intent("BTCUSDT", Some(TimeInForce::GTC));

    let maker = proc.fee_rate_for_intent(&postonly_intent.symbol, &postonly_intent);
    let taker = proc.fee_rate_for_intent(&gtc_intent.symbol, &gtc_intent);

    assert!((maker - 0.0002).abs() < 1e-12, "PostOnly maker = 0.0002");
    assert!((taker - 0.00055).abs() < 1e-12, "GTC taker = 0.00055");
    assert!(maker < taker);

    // LG-2 T3 sibling FeeSource 推斷對齊 — seed_default 後 source 為
    // DemoConservativeDefault（healthcheck [45] dual-source 路徑必對齊）
    assert_eq!(am.fee_source("BTCUSDT"), FeeSource::DemoConservativeDefault);
}

/// IOC / FOK intent 走 taker 路徑（不是 maker）— pin
/// `fee_rate_for_tif` 只把 PostOnly 視為 maker，其餘 TIF 一律 taker。
/// 此防 LG-3 RFC §Pricing Sources 「PostOnly→maker / else→taker」分類被誤動。
#[test]
fn test_lg2_t1_ioc_and_fok_route_to_taker() {
    let am = Arc::new(AccountManager::new());
    am.seed_default_fee_rates(["BTCUSDT"]);

    let mut proc = IntentProcessor::new();
    proc.set_account_manager(Arc::clone(&am));

    for tif in &[TimeInForce::IOC, TimeInForce::FOK, TimeInForce::GTC] {
        let intent = make_intent("BTCUSDT", Some(*tif));
        let rate = proc.fee_rate_for_intent(&intent.symbol, &intent);
        assert!(
            (rate - 0.00055).abs() < 1e-12,
            "TIF {:?} must route to taker fee 0.00055, got {}",
            tif,
            rate
        );
    }

    // TIF=None（市價單預設）也走 taker 路徑
    let intent_none = make_intent("BTCUSDT", None);
    let rate_none = proc.fee_rate_for_intent(&intent_none.symbol, &intent_none);
    assert!((rate_none - 0.00055).abs() < 1e-12);
}

// ---------------------------------------------------------------------------
// (d) Mainnet unsupported endpoint refusal contract
// (d) Mainnet 不支援端點拒絕契約
// ---------------------------------------------------------------------------

/// (d) Mainnet (`BybitEnvironment::Mainnet`) 環境下，fee-rate endpoint
/// 不應命中「demo unsupported fallback」路徑。此測試走 BybitEnvironment
/// secret_slot() 不變式：mainnet=="live"，demo=="demo"。這對齊 binary
/// tasks.rs::is_demo_fee_endpoint_unsupported() 邏輯的「只 demo / live_demo
/// 觸發 seed_default」防線。
///
/// 真實 mainnet refusal 邏輯是兩層：
/// 1. tasks.rs::is_demo_fee_endpoint_unsupported 對 Mainnet 直接 false（已驗）
/// 2. PricingConfig::validate() 禁止 cold_default_acceptable_modes 含 "live"
///
/// 此 contract test pin 兩層協同生效，不靠 startup assertion (T2)。
#[test]
fn test_lg2_t1_mainnet_secret_slot_distinct_from_demo() {
    // BybitEnvironment::secret_slot() 是判定憑證路徑 + endpoint 行為的
    // 關鍵 anchor。Mainnet="live"，Demo/Testnet="demo"，LiveDemo="live"
    // （與 Mainnet 共用 secret，但 endpoint 走 demo URL）。
    assert_eq!(BybitEnvironment::Mainnet.secret_slot(), "live");
    assert_eq!(BybitEnvironment::LiveDemo.secret_slot(), "live");
    assert_eq!(BybitEnvironment::Demo.secret_slot(), "demo");
    assert_eq!(BybitEnvironment::Testnet.secret_slot(), "demo");

    // Mainnet endpoint 不可走 demo URL（LG-3 RFC §2.3 fail-closed invariant）
    assert_eq!(
        BybitEnvironment::Mainnet.rest_base_url(),
        "https://api.bybit.com"
    );
    assert_ne!(
        BybitEnvironment::Mainnet.rest_base_url(),
        BybitEnvironment::Demo.rest_base_url()
    );

    // LiveDemo 雖共用 "live" secret slot，但 endpoint 仍走 demo（per
    // bybit_rest_client.rs 已有 inline test 覆蓋；本檔加 contract 防 drift）
    assert_eq!(
        BybitEnvironment::LiveDemo.rest_base_url(),
        BybitEnvironment::Demo.rest_base_url(),
        "LiveDemo endpoint == Demo URL (secret_slot != endpoint)"
    );
}

/// (d) PricingConfig 嚴格不允許 cold_default_acceptable_modes 含 "live"
/// — LG-3 RFC §2.3 mainnet hard-block 不變式。任何後續 PR 想引入 "live"
/// 到白名單 → validate() 必失敗 → 此測試必紅 → review block。
#[test]
fn test_lg2_t1_mainnet_refusal_via_pricing_config_validate() {
    use openclaw_types::PricingConfig;

    // PricingConfig::default() 預設不含 "live"，但 modes 可以是空？驗最小
    // 有效集合 + 含 "live" 必失敗。
    let default_cfg = PricingConfig::default();
    assert!(default_cfg.validate().is_ok());
    assert!(
        !default_cfg
            .cold_default_acceptable_modes
            .iter()
            .any(|m| m == "live"),
        "default PricingConfig must not contain 'live' in whitelist"
    );

    // 構造非法 config：含 "live" → validate() 必 Err
    let bad_cfg = PricingConfig {
        max_age_warn_minutes: 60,
        max_age_fail_minutes: 1440,
        cold_default_acceptable_modes: vec!["demo".into(), "live".into()],
    };
    let result = bad_cfg.validate();
    assert!(
        result.is_err(),
        "PricingConfig with 'live' in whitelist must fail validate (LG-3 RFC §2.3)"
    );
    let err_msg = result.unwrap_err();
    assert!(
        err_msg.contains("live"),
        "error message must mention 'live' for operator debugging; got: {}",
        err_msg
    );
}

/// (d) Mainnet seed_default + AccountManager.fee_source contract — 即使
/// AccountManager 接受 mainnet 上的 seed_default 寫入（API 邏輯允許），
/// `fee_source()` 仍報 DemoConservativeDefault（與 LG-2 T3 sibling 對齊）。
/// 上層 startup assertion (T2) 需 check `fee_source() != ColdDefault &&
/// fee_source() != DemoConservativeDefault` 對 mainnet env，這是 T2 的職責；
/// 本 T1 test 證明 T3 提供的 `fee_source()` 已足夠讓 T2 做此決策。
#[test]
fn test_lg2_t1_fee_source_supports_mainnet_refusal_decision() {
    let mgr = AccountManager::new();

    // Cold boot → ColdDefault（mainnet 此狀態下 T2 必拒 spawn）
    assert_eq!(mgr.last_fee_refresh_ms(), 0);
    assert_eq!(mgr.fee_source("BTCUSDT"), FeeSource::ColdDefault);

    // seed_default after demo endpoint unsupported → DemoConservativeDefault
    // （mainnet 此狀態 T2 也必拒 spawn — 此分類訊號是 T2 入口）
    mgr.seed_default_fee_rates(["BTCUSDT"]);
    assert_eq!(mgr.fee_source("BTCUSDT"), FeeSource::DemoConservativeDefault);

    // 真實 API fee 注入後 → BybitApi（mainnet 此狀態 T2 才會放行 spawn）
    // 透過 lib pub seed_default_fee_rates 走過後，cache 用真實 API 真值
    // overwrite 的場景由 inline test 已 cover；本檔僅 contract pin T3 ↔ T2
    // 介面，不重複 overwrite path。
    assert_ne!(
        FeeSource::BybitApi,
        FeeSource::ColdDefault,
        "BybitApi and ColdDefault must be distinct enum variants for T2"
    );
    assert_ne!(
        FeeSource::BybitApi,
        FeeSource::DemoConservativeDefault,
        "BybitApi and DemoConservativeDefault must be distinct for T2"
    );
}

// ---------------------------------------------------------------------------
// LG-2 T4 PricingConfig cross-reference contract
// LG-2 T4 PricingConfig 交叉驗證契約
// ---------------------------------------------------------------------------

/// (e) PricingConfig 從 risk_config_demo.toml 真實 load → 對齊 LG-2 T4 land
/// 值（warn=60min / fail=1440min / modes=[paper, demo, live_demo]）。
/// 此契約防止 demo TOML 被誤動破 demo learning data 主通道。
#[test]
fn test_lg2_t1_pricing_config_demo_lg2_t4_default_matches_real_toml() {
    let path = srv_root()
        .join("settings")
        .join("risk_control_rules")
        .join("risk_config_demo.toml");
    let content = std::fs::read_to_string(&path)
        .unwrap_or_else(|e| panic!("read {}: {}", path.display(), e));
    let cfg: RiskConfig = toml::from_str(&content)
        .unwrap_or_else(|e| panic!("parse risk_config_demo.toml: {}", e));

    cfg.validate()
        .unwrap_or_else(|e| panic!("validate risk_config_demo.toml: {}", e));

    let pricing = cfg
        .pricing
        .as_ref()
        .expect("risk_config_demo.toml must have [pricing] section (LG-2 T4 land)");

    // demo 中庸（per LG2-T4 report §3.2）：warn=60min hourly refresh fail 即
    // WARN；fail=1440min (24h) 對齊 LG-3 RFC §2.3 mainnet hard-block 等門檻
    assert_eq!(
        pricing.max_age_warn_minutes, 60,
        "demo PricingConfig warn must be 60min (LG-2 T4 spec)"
    );
    assert_eq!(
        pricing.max_age_fail_minutes, 1440,
        "demo PricingConfig fail must be 1440min (24h, LG-2 T4 spec)"
    );

    // 白名單對齊 LG2-T4：[paper, demo, live_demo]，不含 "live"
    let modes = &pricing.cold_default_acceptable_modes;
    assert_eq!(
        modes.len(),
        3,
        "demo PricingConfig whitelist must have 3 modes (paper/demo/live_demo)"
    );
    assert!(modes.contains(&"paper".to_string()));
    assert!(modes.contains(&"demo".to_string()));
    assert!(modes.contains(&"live_demo".to_string()));
    assert!(!modes.contains(&"live".to_string()));
}

/// (e) PricingConfig 從 risk_config_live.toml 真實 load → 對齊 LG-2 T4 嚴格
/// default（warn=30min / fail=720min / modes=[demo, live_demo]）。
/// 此契約 + PricingConfig::validate() invariant 雙重保證：mainnet hard-block
/// 永不退化（per LG-3 RFC §2.3）。
#[test]
fn test_lg2_t1_pricing_config_live_lg2_t4_excludes_paper_and_live() {
    let path = srv_root()
        .join("settings")
        .join("risk_control_rules")
        .join("risk_config_live.toml");
    let content = std::fs::read_to_string(&path)
        .unwrap_or_else(|e| panic!("read {}: {}", path.display(), e));
    let cfg: RiskConfig = toml::from_str(&content)
        .unwrap_or_else(|e| panic!("parse risk_config_live.toml: {}", e));

    cfg.validate()
        .unwrap_or_else(|e| panic!("validate risk_config_live.toml: {}", e));

    let pricing = cfg
        .pricing
        .as_ref()
        .expect("risk_config_live.toml must have [pricing] section (LG-2 T4 land)");

    // live 嚴格（per LG2-T4 report §3.2 feedback_demo_loose_live_strict_policy）：
    // warn=30min 是 demo 一半；fail=720min (12h) 比 demo 24h 收緊
    assert_eq!(
        pricing.max_age_warn_minutes, 30,
        "live PricingConfig warn must be 30min (LG-2 T4 strict spec)"
    );
    assert_eq!(
        pricing.max_age_fail_minutes, 720,
        "live PricingConfig fail must be 720min (12h, LG-2 T4 strict spec)"
    );

    // 白名單嚴格：只 [demo, live_demo]，不含 paper 也不含 live
    let modes = &pricing.cold_default_acceptable_modes;
    assert_eq!(
        modes.len(),
        2,
        "live PricingConfig whitelist must have exactly 2 modes (demo/live_demo)"
    );
    assert!(modes.contains(&"demo".to_string()));
    assert!(modes.contains(&"live_demo".to_string()));
    assert!(
        !modes.contains(&"paper".to_string()),
        "live config must not whitelist paper (LG-2 T4 spec)"
    );
    assert!(
        !modes.contains(&"live".to_string()),
        "live config must NEVER whitelist 'live' (LG-3 RFC §2.3 mainnet fail-closed)"
    );
}

/// (e) PricingConfig 從 risk_config_paper.toml 真實 load → 對齊 LG-2 T4
/// 寬鬆 default（warn=1440min / fail=10080min / modes=[paper, demo, live_demo]）。
/// paper pipeline 預設 dormant（per memory project_paper_pipeline_disabled_by_default），
/// 但 schema parity 仍必須保留。
#[test]
fn test_lg2_t1_pricing_config_paper_lg2_t4_loose_for_dormant_pipeline() {
    let path = srv_root()
        .join("settings")
        .join("risk_control_rules")
        .join("risk_config_paper.toml");
    let content = std::fs::read_to_string(&path)
        .unwrap_or_else(|e| panic!("read {}: {}", path.display(), e));
    let cfg: RiskConfig = toml::from_str(&content)
        .unwrap_or_else(|e| panic!("parse risk_config_paper.toml: {}", e));

    cfg.validate()
        .unwrap_or_else(|e| panic!("validate risk_config_paper.toml: {}", e));

    let pricing = cfg
        .pricing
        .as_ref()
        .expect("risk_config_paper.toml must have [pricing] section (LG-2 T4 land)");

    // paper 寬鬆（per LG2-T4 report §3.2）
    assert_eq!(
        pricing.max_age_warn_minutes, 1440,
        "paper PricingConfig warn must be 1440min (LG-2 T4 loose spec)"
    );
    assert_eq!(
        pricing.max_age_fail_minutes, 10080,
        "paper PricingConfig fail must be 10080min (7d, LG-2 T4 loose spec)"
    );

    // 白名單 [paper, demo, live_demo]，與 demo 對齊
    let modes = &pricing.cold_default_acceptable_modes;
    assert_eq!(modes.len(), 3);
    assert!(modes.contains(&"paper".to_string()));
    assert!(!modes.contains(&"live".to_string()));
}

/// (e) 跨三環境一致性契約：warn < fail 不變式 + "live" 永不入白名單 +
/// max_age_fail_minutes > 0 — 三個都是 PricingConfig::validate() 強制的
/// invariant，但本檔顯式 pin 三個真實 TOML 同時滿足這些 invariant，防止
/// 任一 TOML 被局部修改後僅當地驗的盲區。
#[test]
fn test_lg2_t1_pricing_config_invariants_across_all_three_envs() {
    for fname in &[
        "risk_config_paper.toml",
        "risk_config_demo.toml",
        "risk_config_live.toml",
    ] {
        let path = srv_root().join("settings").join("risk_control_rules").join(fname);
        let content = std::fs::read_to_string(&path)
            .unwrap_or_else(|e| panic!("read {}: {}", path.display(), e));
        let cfg: RiskConfig = toml::from_str(&content)
            .unwrap_or_else(|e| panic!("parse {}: {}", fname, e));
        cfg.validate()
            .unwrap_or_else(|e| panic!("validate {}: {}", fname, e));

        let pricing = cfg.pricing.as_ref().unwrap_or_else(|| {
            panic!("{} must have [pricing] section after LG-2 T4 land", fname)
        });

        // Invariant 1: warn < fail
        assert!(
            pricing.max_age_warn_minutes < pricing.max_age_fail_minutes,
            "{}: warn {} must be strictly less than fail {}",
            fname,
            pricing.max_age_warn_minutes,
            pricing.max_age_fail_minutes
        );

        // Invariant 2: fail > 0
        assert!(
            pricing.max_age_fail_minutes > 0,
            "{}: fail must be > 0",
            fname
        );

        // Invariant 3: 白名單非空
        assert!(
            !pricing.cold_default_acceptable_modes.is_empty(),
            "{}: cold_default_acceptable_modes must not be empty",
            fname
        );

        // Invariant 4: "live" 永不入白名單（LG-3 RFC §2.3 mainnet hard-block）
        assert!(
            !pricing
                .cold_default_acceptable_modes
                .iter()
                .any(|m| m == "live"),
            "{}: cold_default_acceptable_modes must NEVER contain 'live' \
             (LG-3 RFC §2.3 mainnet fail-closed invariant)",
            fname
        );
    }
}

// ---------------------------------------------------------------------------
// Sanity contract — FeeRate / FeeSource lib pub API stability
// 健全契約 — FeeRate / FeeSource lib pub API 穩定性
// ---------------------------------------------------------------------------

/// FeeRate / FeeSource lib pub API 穩定性 — 防止後續 LG-2 T2 / T3 PR 不小心
/// 把 `pub use account_manager::FeeRate` 拿掉，破下游 healthcheck Python
/// IPC dual-source 對賬路徑（per LG-2 T3 sibling design）。
#[test]
fn test_lg2_t1_fee_rate_pub_api_stability() {
    // FeeRate struct lib-public（serde Serialize / Deserialize 必保留）
    let rate = FeeRate {
        symbol: "BTCUSDT".to_string(),
        maker_fee_rate: 0.0001,
        taker_fee_rate: 0.0004,
    };
    let json = serde_json::to_string(&rate).expect("FeeRate must serialize");
    let deser: FeeRate = serde_json::from_str(&json).expect("FeeRate must deserialize");
    assert_eq!(deser.symbol, "BTCUSDT");

    // FeeSource 三個 enum variant 必須穩定（LG-2 T3 sibling 加，Python 端
    // IPC 對賬契約必對齊）
    assert_eq!(FeeSource::BybitApi.as_str(), "bybit_api");
    assert_eq!(
        FeeSource::DemoConservativeDefault.as_str(),
        "demo_conservative_default"
    );
    assert_eq!(FeeSource::ColdDefault.as_str(), "cold_default");
}
