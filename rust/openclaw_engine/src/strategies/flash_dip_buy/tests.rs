//! flash_dip_buy on_tick / lifecycle 整合測試。
//!
//! 注意：cadence 用 wall-clock `openclaw_core::now_ms()`（must-fix #6），故測試
//! 不直接斷言「特定 UTC 日」；改測「首次 on_tick 必武裝（last_acted=-1 < today）」、
//! symbol fence、active gate、cross-strategy skip、並發軟層、prior_close 缺則 inert、
//! 重啟重建。純 cadence 數學（UTC 日邊界 / hold 到期）由 params.rs 純函式測試覆蓋。

use super::*;
use crate::strategies::test_harness::StrategyHarness;
use openclaw_core::execution::FillResult;

/// 隔離 entry_ts checkpoint sidecar：每測試用獨立 OPENCLAW_DATA_DIR，避免污染。
/// 為什麼：persist_entry_ts/load_entry_ts_checkpoint/sidecar_owned_symbols 走
/// process 全局 OPENCLAW_DATA_DIR；`cargo test --lib` 預設多執行緒並行，會讓並發的
/// flash_dip 測試互相覆蓋此 env var（在 set_var 與 sidecar 讀取之間），導致
/// sidecar_owned_symbols() 讀到別的測試的 dir（E4 RED：~13% 並發 suite-fail，
/// 命中新 triage 測試 + 既有 restart_rebuild_* 測試）。
/// 修法（TEST-ONLY）：取 crate 全局 env-mutating 測試互鎖 `crate::test_env_lock::guard()`
/// 鎖住整個閉包執行期，使所有改 OPENCLAW_DATA_DIR 的 flash_dip 測試真正串行；
/// guard() 內部以 into_inner() 處理 poisoning，故某測試 panic 不會連鎖毒化後續測試。
/// 不改任何 production 簽名（不把 dir 參數穿進 load_entry_ts_checkpoint /
/// sidecar_owned_symbols）。
fn with_isolated_data_dir<F: FnOnce()>(tag: &str, f: F) {
    // 鎖必須涵蓋 set_var → f() → remove_dir_all 的「整段」，否則並發測試會在
    // 本測試讀 sidecar 前先 set_var 蓋掉本測試的 dir。
    let _env_guard = crate::test_env_lock::guard();
    let dir = std::env::temp_dir().join(format!("flash_dip_test_{tag}_{}", std::process::id()));
    let _ = std::fs::create_dir_all(&dir);
    std::env::set_var("OPENCLAW_DATA_DIR", &dir);
    f();
    let _ = std::fs::remove_dir_all(&dir);
}

fn active_strategy() -> FlashDipBuy {
    let mut s = FlashDipBuy::new();
    s.set_active(true);
    s
}

fn make_fill() -> FillResult {
    // on_fill 不消費 fill 內容（只用 intent.symbol + wall-clock now）；最小構造。
    FillResult {
        fill_price: 100.0,
        fill_qty: 1.0,
        fee: 0.0,
        slippage_bps: 0.0,
        is_taker: false,
    }
}

#[test]
fn inactive_emits_nothing() {
    let mut s = FlashDipBuy::new(); // active=false 預設
    let ctx = StrategyHarness::new("BTCUSDT").price(60_000.0).build();
    let surface = &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE;
    assert!(s.on_tick(&ctx, surface).is_empty());
}

#[test]
fn non_allowed_symbol_skipped() {
    let mut s = active_strategy();
    s.seed_prior_close("SOLUSDT", 150.0);
    // SOLUSDT ∈ universe 但用一個不在 26 內的 symbol 測 fence。
    let ctx = StrategyHarness::new("WIFUSDT").price(2.0).build();
    let surface = &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE;
    assert!(s.on_tick(&ctx, surface).is_empty());
}

#[test]
fn missing_prior_close_inert_failsafe_in_static_mode() {
    let mut s = active_strategy();
    s.bounded_demo_near_touch = false;
    // static 深價模式不 seed prior_close → 即使 UTC 日首 tick 也 inert（fail-safe，silent）。
    let ctx = StrategyHarness::new("BTCUSDT").price(60_000.0).build();
    let surface = &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE;
    assert!(s.on_tick(&ctx, surface).is_empty());
}

#[test]
fn bounded_near_touch_missing_prior_close_uses_current_price_fallback() {
    let mut s = active_strategy();
    // near-touch fill-discovery 不應被 boot-only 1d seed stale 阻斷；prior_close
    // fallback 僅用於 thesis logging，實際掛單價仍取 current_price*(1-offset)。
    let ctx = StrategyHarness::new("BTCUSDT").price(59_000.0).build();
    let surface = &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE;
    let actions = s.on_tick(&ctx, surface);
    assert_eq!(actions.len(), 1);
    match &actions[0] {
        StrategyAction::Open(intent) => {
            assert_eq!(intent.strategy, "flash_dip_buy");
            assert!((intent.limit_price.unwrap() - 58_941.0).abs() < 1e-6);
        }
        _ => panic!("expected Open"),
    }
}

#[test]
fn day_first_tick_emits_postonly_bounded_near_touch_limit() {
    let mut s = active_strategy();
    s.seed_prior_close("BTCUSDT", 60_000.0);
    let ctx = StrategyHarness::new("BTCUSDT").price(59_000.0).build();
    let surface = &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE;
    let actions = s.on_tick(&ctx, surface);
    assert_eq!(actions.len(), 1);
    match &actions[0] {
        StrategyAction::Open(intent) => {
            assert_eq!(intent.symbol, "BTCUSDT");
            assert!(intent.is_long, "dip-buy must be long");
            assert_eq!(intent.order_type, "limit");
            // bounded demo near-touch = 59000 * (1 - 10bps) = 58941。
            let limit = intent.limit_price.unwrap();
            assert!((limit - 58_941.0).abs() < 1e-6);
            assert!(
                limit < 59_000.0,
                "PostOnly BUY limit must stay below last price"
            );
            // PostOnly maker。
            assert!(matches!(
                intent.time_in_force,
                Some(crate::order_manager::TimeInForce::PostOnly)
            ));
            assert!(intent.maker_timeout_ms.is_some());
            assert!(
                s.pending_entry_expiry.contains_key("BTCUSDT"),
                "emitted resting order must count as pending"
            );
            // 誠實 confidence（非硬設高值；E3 #5）。在 (0, 0.6) 之間。
            assert!(intent.confidence > 0.0 && intent.confidence < 0.6);
        }
        _ => panic!("expected Open"),
    }
}

#[test]
fn static_deep_dip_mode_remains_available_when_near_touch_disabled() {
    let mut s = active_strategy();
    s.bounded_demo_near_touch = false;
    s.seed_prior_close("BTCUSDT", 60_000.0);
    let ctx = StrategyHarness::new("BTCUSDT").price(59_000.0).build();
    let surface = &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE;
    let actions = s.on_tick(&ctx, surface);
    assert_eq!(actions.len(), 1);
    match &actions[0] {
        StrategyAction::Open(intent) => {
            // 靜態深價 = 60000*(1-0.15) = 51000。
            assert!((intent.limit_price.unwrap() - 51_000.0).abs() < 1e-6);
        }
        _ => panic!("expected Open"),
    }
}

#[test]
fn same_day_second_tick_no_double_arm() {
    let mut s = active_strategy();
    s.seed_prior_close("BTCUSDT", 60_000.0);
    let ctx = StrategyHarness::new("BTCUSDT").price(59_000.0).build();
    let surface = &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE;
    // 首 tick 武裝。
    assert_eq!(s.on_tick(&ctx, surface).len(), 1);
    // 同 UTC 日後續 tick → no-op（daily cadence）。
    assert!(s.on_tick(&ctx, surface).is_empty());
}

#[test]
fn concurrency_soft_cap_blocks_entry() {
    with_isolated_data_dir("conc", || {
        let mut s = active_strategy();
        // 人為填滿 open_symbols 至 max_concurrent（3）。
        for sym in ["ETHUSDT", "SOLUSDT", "XRPUSDT"] {
            s.seed_prior_close(sym, 100.0);
            s.on_fill(
                &OrderIntent::new_trade(
                    sym.to_string(),
                    true,
                    1.0,
                    0.5,
                    "flash_dip_buy".to_string(),
                    "limit".to_string(),
                    Some(85.0),
                    None,
                    None,
                    Some(crate::order_manager::TimeInForce::PostOnly),
                    Some(60_000),
                ),
                &make_fill(),
            );
        }
        assert_eq!(s.open_symbols.len(), 3);
        // 第 4 個 symbol 即使 UTC 日首 tick 也被軟層擋。
        s.seed_prior_close("BTCUSDT", 60_000.0);
        let ctx = StrategyHarness::new("BTCUSDT").price(59_000.0).build();
        let surface = &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE;
        assert!(
            s.on_tick(&ctx, surface).is_empty(),
            "soft concurrency cap must block 4th"
        );
    });
}

#[test]
fn pending_working_order_cap_blocks_unfilled_entries() {
    with_isolated_data_dir("pendingcap", || {
        let mut s = active_strategy();
        s.max_concurrent = 1;
        s.seed_prior_close("BTCUSDT", 60_000.0);
        s.seed_prior_close("ETHUSDT", 3_000.0);
        let surface = &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE;

        let btc_ctx = StrategyHarness::new("BTCUSDT").price(59_000.0).build();
        let btc_actions = s.on_tick(&btc_ctx, surface);
        assert_eq!(btc_actions.len(), 1);
        assert!(s.pending_entry_expiry.contains_key("BTCUSDT"));
        assert_eq!(s.producer_active_entry_count(), 1);

        let eth_ctx = StrategyHarness::new("ETHUSDT").price(2_950.0).build();
        assert!(
            s.on_tick(&eth_ctx, surface).is_empty(),
            "unfilled BTC resting order must consume max_concurrent capacity"
        );

        let btc_intent = match &btc_actions[0] {
            StrategyAction::Open(intent) => intent.clone(),
            _ => panic!("expected Open"),
        };
        s.on_rejection(&btc_intent, "cost_gate(JS-demo): edge=-1.00bps < 0");
        assert!(!s.pending_entry_expiry.contains_key("BTCUSDT"));

        let eth_actions = s.on_tick(&eth_ctx, surface);
        assert_eq!(
            eth_actions.len(),
            1,
            "after rejection clears pending capacity, another symbol may arm"
        );
    });
}

#[test]
fn expired_pending_working_order_releases_capacity() {
    let mut s = active_strategy();
    s.max_concurrent = 1;
    s.pending_entry_expiry.insert("BTCUSDT".to_string(), 1);
    s.seed_prior_close("ETHUSDT", 3_000.0);
    let ctx = StrategyHarness::new("ETHUSDT").price(2_950.0).build();
    let surface = &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE;
    let actions = s.on_tick(&ctx, surface);
    assert_eq!(actions.len(), 1);
    assert!(!s.pending_entry_expiry.contains_key("BTCUSDT"));
}

#[test]
fn cross_strategy_position_skips_entry() {
    let mut s = active_strategy();
    s.seed_prior_close("BTCUSDT", 60_000.0);
    // 別的策略持有 BTCUSDT 倉位 → flash_dip 不入場。
    let pos = StrategyHarness::paper_position("BTCUSDT", true, "ma_crossover");
    let ctx = StrategyHarness::new("BTCUSDT")
        .price(59_000.0)
        .position_state(pos)
        .build();
    let surface = &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE;
    assert!(s.on_tick(&ctx, surface).is_empty());
}

#[test]
fn hold_expiry_emits_close() {
    with_isolated_data_dir("holdexp", || {
        let mut s = active_strategy();
        let sym = "BTCUSDT";
        // 人為設 entry_ts 為 4 日前（> N=3 日）→ 到期。
        let now = openclaw_core::now_ms();
        let four_days_ago = now - 4 * params::MS_PER_UTC_DAY;
        s.entry_ts.insert(sym.to_string(), four_days_ago);
        s.open_symbols.insert(sym.to_string());
        // 本策略持倉的 ctx（owner_strategy == flash_dip_buy）。
        let pos = StrategyHarness::paper_position(sym, true, "flash_dip_buy");
        let ctx = StrategyHarness::new("BTCUSDT")
            .price(58_000.0)
            .position_state(pos)
            .build();
        let surface = &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE;
        let actions = s.on_tick(&ctx, surface);
        assert_eq!(actions.len(), 1);
        match &actions[0] {
            StrategyAction::Close { symbol, reason, .. } => {
                assert_eq!(symbol, sym);
                assert!(reason.contains("hold_3d_expiry"));
            }
            _ => panic!("expected Close"),
        }
        // 同日第二 tick → no-op（day-clustered，當日只發一次 Close）。
        assert!(s.on_tick(&ctx, surface).is_empty());
    });
}

#[test]
fn hold_not_expired_holds() {
    with_isolated_data_dir("holdnot", || {
        let mut s = active_strategy();
        let sym = "BTCUSDT";
        // entry_ts 為 1 日前（< N=3 日）→ 持有不平。
        let now = openclaw_core::now_ms();
        s.entry_ts
            .insert(sym.to_string(), now - params::MS_PER_UTC_DAY);
        s.open_symbols.insert(sym.to_string());
        let pos = StrategyHarness::paper_position(sym, true, "flash_dip_buy");
        let ctx = StrategyHarness::new("BTCUSDT")
            .price(58_000.0)
            .position_state(pos)
            .build();
        let surface = &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE;
        assert!(s.on_tick(&ctx, surface).is_empty());
    });
}

#[test]
fn restart_rebuild_open_set_and_entry_ts_from_checkpoint() {
    use crate::paper_state::PaperState;
    with_isolated_data_dir("restart", || {
        let sym = "ETHUSDT";
        let true_entry = openclaw_core::now_ms() - 2 * params::MS_PER_UTC_DAY;
        // 第一個 strategy 實例：fill → 寫 sidecar（真 entry_ts）。
        {
            let mut s1 = active_strategy();
            s1.entry_ts.insert(sym.to_string(), true_entry);
            s1.open_symbols.insert(sym.to_string());
            s1.persist_entry_ts();
        }
        // 模擬重啟：paper_state 經 triage 後本策略持倉（owner=flash_dip_buy），
        // 但其 entry_ts_ms 帶 Bybit updated_time（比真 entry 晚 → 若用它 hold clock 會錯）。
        let mut paper = PaperState::new(10_000.0);
        let bybit_updated_time = openclaw_core::now_ms(); // 「現在」（非真 entry）
        paper.apply_fill(
            sym,
            true,
            1.0,
            100.0,
            0.0,
            bybit_updated_time,
            "flash_dip_buy",
        );
        let mut s2 = active_strategy();
        s2.import_positions(&paper);
        // open set 重建。
        assert!(s2.open_symbols.contains(sym));
        // entry_ts 從 sidecar 還原 = 真 entry（非 Bybit updated_time）。
        assert_eq!(s2.entry_ts.get(sym).copied(), Some(true_entry));
        assert_ne!(s2.entry_ts.get(sym).copied(), Some(bybit_updated_time));
    });
}

#[test]
fn import_positions_falls_back_to_paper_ts_when_no_checkpoint() {
    use crate::paper_state::PaperState;
    with_isolated_data_dir("nockpt", || {
        let sym = "BTCUSDT";
        let paper_ts = openclaw_core::now_ms() - params::MS_PER_UTC_DAY;
        // 無 sidecar（隔離空 dir）→ import_positions 退回 paper_state entry_ts_ms。
        let mut paper = PaperState::new(10_000.0);
        paper.apply_fill(sym, true, 1.0, 60_000.0, 0.0, paper_ts, "flash_dip_buy");
        let mut s = active_strategy();
        s.import_positions(&paper);
        assert!(s.open_symbols.contains(sym));
        assert_eq!(s.entry_ts.get(sym).copied(), Some(paper_ts));
    });
}

#[test]
fn import_positions_ignores_other_owner() {
    use crate::paper_state::PaperState;
    with_isolated_data_dir("otherowner", || {
        let mut paper = PaperState::new(10_000.0);
        paper.apply_fill("BTCUSDT", true, 1.0, 60_000.0, 0.0, 1_000, "ma_crossover");
        let mut s = active_strategy();
        s.import_positions(&paper);
        assert!(
            !s.open_symbols.contains("BTCUSDT"),
            "ma_crossover-owned position must not be imported"
        );
    });
}

#[test]
fn on_fill_records_entry_ts_first_write_wins() {
    with_isolated_data_dir("firstwrite", || {
        let mut s = active_strategy();
        let sym = "BTCUSDT";
        let intent = OrderIntent::new_trade(
            sym.to_string(),
            true,
            1.0,
            0.5,
            "flash_dip_buy".to_string(),
            "limit".to_string(),
            Some(51_000.0),
            None,
            None,
            Some(crate::order_manager::TimeInForce::PostOnly),
            Some(60_000),
        );
        s.pending_entry_expiry
            .insert(sym.to_string(), openclaw_core::now_ms() + 60_000);
        s.on_fill(&intent, &make_fill());
        assert!(
            !s.pending_entry_expiry.contains_key(sym),
            "fill must clear pending working order state"
        );
        let first_ts = *s.entry_ts.get(sym).unwrap();
        // 同向加倉第二次 fill：entry_ts 不被刷新（first-write-wins，防 hold clock 重置）。
        std::thread::sleep(std::time::Duration::from_millis(2));
        s.on_fill(&intent, &make_fill());
        assert_eq!(*s.entry_ts.get(sym).unwrap(), first_ts);
    });
}

#[test]
fn maker_timeout_floor_enforced() {
    // 接近 UTC 日終時 timeout 不應 < floor（15s）。
    let near_midnight = 5 * params::MS_PER_UTC_DAY - 1; // 距日終 1ms
    let to = FlashDipBuy::maker_timeout_to_day_end(near_midnight);
    assert!(
        to >= 15_000,
        "maker timeout must respect floor near midnight"
    );
}

#[test]
fn triage_retains_flash_dip_ownership_and_hard_reject_counts_them() {
    // E2 HIGH regression（restart triage ownership bypass）：驅動「完整 triage_bybit_sync
    // 路徑」—— 不直接 seed owner=="flash_dip_buy"，而是模擬真實重啟：
    //   1. PaperState::import_positions 把恢復倉統一標 "bybit_sync"（如 bootstrap:367）；
    //   2. flash_dip 寫過 sidecar（記 3 個 pilot symbol，如 on_fill 持久化）；
    //   3. reclaim_owner_for_symbols（bootstrap triage 前那一步）依 sidecar 重蓋；
    //   4. triage_bybit_sync（bootstrap:477）執行 —— 必須跳過已重蓋的 pilot 倉，
    //      不把它們改標 KNOWN_STRATEGY_NAMES[0]（= "ma_crossover"）。
    // 斷言：triage 後 3 倉 owner 仍 == "flash_dip_buy"（非被 adopt 成 ma_crossover），
    //       且 router per_strategy 並發硬層數到 3 → 第 4 筆新開倉被 fail-closed 拒。
    use crate::config::risk_config::StrategyOverride;
    use crate::config::RiskConfig;
    use crate::intent_processor::IntentProcessor;
    use crate::paper_state::PaperState;
    use crate::position_reconciler::orphan_handler::KNOWN_STRATEGY_NAMES;
    use openclaw_core::governance_core::{GovernanceCore, GovernanceProfile};

    with_isolated_data_dir("triagepath", || {
        let pilot_syms = ["ETHUSDT", "SOLUSDT", "XRPUSDT"];

        // (2) flash_dip 在崩潰前已 fill 並持久化 sidecar（記 3 個 pilot symbol）。
        {
            let mut s = active_strategy();
            let now = openclaw_core::now_ms();
            for sym in pilot_syms {
                s.entry_ts
                    .insert(sym.to_string(), now - params::MS_PER_UTC_DAY);
                s.open_symbols.insert(sym.to_string());
            }
            s.persist_entry_ts();
        }
        // sidecar reader 必須讀回 3 個 symbol。
        let mut sidecar = FlashDipBuy::sidecar_owned_symbols();
        sidecar.sort();
        assert_eq!(sidecar, vec!["ETHUSDT", "SOLUSDT", "XRPUSDT"]);

        // (1) 重啟：PaperState::import_positions 把恢復倉統一標 "bybit_sync"。
        let mut paper = PaperState::new(100_000.0);
        let seed: Vec<(String, bool, f64, f64, u64)> = pilot_syms
            .iter()
            .map(|s| (s.to_string(), true, 1.0, 100.0, openclaw_core::now_ms()))
            .collect();
        assert_eq!(paper.import_positions(seed), 3);
        for sym in pilot_syms {
            assert_eq!(
                paper.get_position(sym).unwrap().owner_strategy,
                "bybit_sync",
                "import_positions 必統一標 bybit_sync（重現 bootstrap:367）"
            );
        }

        // (3) bootstrap triage 前的 reclaim（依 sidecar 重蓋）。
        let reclaimed = paper.reclaim_owner_for_symbols(&sidecar, "flash_dip_buy");
        assert_eq!(reclaimed, 3, "reclaim 必重蓋 3 個 pilot 倉");
        for sym in pilot_syms {
            assert_eq!(
                paper.get_position(sym).unwrap().owner_strategy,
                "flash_dip_buy",
                "reclaim 後 pilot 倉 owner 必為 flash_dip_buy"
            );
        }

        // 加一個無關 bybit_sync 倉，證明 triage 仍正常 adopt 非-pilot 倉 → ma_crossover。
        paper.set_latest_price("DOGEUSDT", 0.1);
        paper.apply_fill("DOGEUSDT", true, 100.0, 0.1, 0.0, 0, "bybit_sync");

        // (4) 完整 triage_bybit_sync 路徑（universe 含 pilot symbol + 無關 bybit_sync 倉）。
        let active_symbols: Vec<String> = pilot_syms
            .iter()
            .map(|s| s.to_string())
            .chain(std::iter::once("DOGEUSDT".to_string()))
            .collect();
        let triage = paper.triage_bybit_sync(
            &active_symbols,
            KNOWN_STRATEGY_NAMES,
            |_sym, _qty| None, // 無 dust gate
        );

        // pilot 倉位歸屬未被 triage 改動（仍 flash_dip_buy）。
        for sym in pilot_syms {
            assert_eq!(
                paper.get_position(sym).unwrap().owner_strategy,
                "flash_dip_buy",
                "triage 不得把已 reclaim 的 pilot 倉改標 ma_crossover"
            );
        }
        // triage 只 adopt 那個無關 bybit_sync 倉（DOGEUSDT → ma_crossover）。
        assert_eq!(triage.adopted.len(), 1, "triage 只應 adopt 非-pilot 倉");
        assert_eq!(triage.adopted[0].0, "DOGEUSDT");
        assert_eq!(triage.adopted[0].1, "ma_crossover");

        // router 並發硬層：3 個 flash_dip_buy 真倉 → cap=3 → 第 4 筆新開倉被拒。
        let mut proc = IntentProcessor::new();
        let mut cfg = RiskConfig::default();
        cfg.per_strategy.insert(
            "flash_dip_buy".into(),
            StrategyOverride {
                max_concurrent_positions: Some(3),
                ..Default::default()
            },
        );
        proc.update_risk_config(cfg);
        let mut gov = GovernanceCore::new();
        gov.grant_paper_authorization(None).unwrap();

        paper.set_latest_price("BTCUSDT", 50_000.0);
        let intent = OrderIntent::new_trade(
            "BTCUSDT".to_string(),
            true,
            0.01,
            0.6,
            "flash_dip_buy".to_string(),
            "market".to_string(),
            None,
            None,
            None,
            None,
            None,
        );
        let result = proc.process(
            &intent,
            &gov,
            &paper,
            2000.0,
            GovernanceProfile::Exploration,
        );
        assert!(
            !result.submitted,
            "triage 保歸屬後，第 4 筆 flash_dip_buy 開倉必被並發硬層拒"
        );
        let reason = result.rejected_reason.unwrap_or_default();
        assert!(
            reason.contains("max_concurrent_positions=3"),
            "拒因須來自 per_strategy 並發硬層，got: {reason}"
        );
    });
}

#[test]
fn params_json_roundtrip() {
    let mut s = active_strategy();
    s.k_dip = 0.2;
    s.near_touch_offset_bps = 12.0;
    let json = s.get_params_json();
    let mut s2 = FlashDipBuy::new();
    s2.update_params_json(&json).unwrap();
    assert!((s2.k_dip - 0.2).abs() < 1e-9);
    assert!(s2.bounded_demo_near_touch);
    assert!((s2.near_touch_offset_bps - 12.0).abs() < 1e-9);
    assert!(s2.is_active());
}
