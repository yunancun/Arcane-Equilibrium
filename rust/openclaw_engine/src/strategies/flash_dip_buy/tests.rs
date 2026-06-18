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
/// 為什麼：persist_entry_ts/load_entry_ts_checkpoint 走 OPENCLAW_DATA_DIR；測試間
/// 必須隔離，否則 on_fill 寫的 sidecar 會跨測試殘留。
fn with_isolated_data_dir<F: FnOnce()>(tag: &str, f: F) {
    let dir = std::env::temp_dir().join(format!("flash_dip_test_{tag}_{}", std::process::id()));
    let _ = std::fs::create_dir_all(&dir);
    // SAFETY: 測試單執行緒序列化（cargo test 預設多執行緒，但本 helper 設 + 還原 env
    // 僅在本閉包同步區間；各測試用獨立 tag dir 故 sidecar 不衝突）。
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
fn missing_prior_close_inert_failsafe() {
    let mut s = active_strategy();
    // 不 seed prior_close → 即使 UTC 日首 tick 也 inert（fail-safe，silent）。
    let ctx = StrategyHarness::new("BTCUSDT").price(60_000.0).build();
    let surface = &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE;
    assert!(s.on_tick(&ctx, surface).is_empty());
}

#[test]
fn day_first_tick_emits_postonly_dip_limit() {
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
            // 靜態深價 = 60000*(1-0.15) = 51000。
            assert!((intent.limit_price.unwrap() - 51_000.0).abs() < 1e-6);
            // PostOnly maker。
            assert!(matches!(
                intent.time_in_force,
                Some(crate::order_manager::TimeInForce::PostOnly)
            ));
            assert!(intent.maker_timeout_ms.is_some());
            // 誠實 confidence（非硬設高值；E3 #5）。在 (0, 0.6) 之間。
            assert!(intent.confidence > 0.0 && intent.confidence < 0.6);
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
        assert!(s.on_tick(&ctx, surface).is_empty(), "soft concurrency cap must block 4th");
    });
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
        s.entry_ts.insert(sym.to_string(), now - params::MS_PER_UTC_DAY);
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
        paper.apply_fill(sym, true, 1.0, 100.0, 0.0, bybit_updated_time, "flash_dip_buy");
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
        s.on_fill(&intent, &make_fill());
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
    assert!(to >= 15_000, "maker timeout must respect floor near midnight");
}

#[test]
fn params_json_roundtrip() {
    let mut s = active_strategy();
    s.k_dip = 0.2;
    let json = s.get_params_json();
    let mut s2 = FlashDipBuy::new();
    s2.update_params_json(&json).unwrap();
    assert!((s2.k_dip - 0.2).abs() < 1e-9);
    assert!(s2.is_active());
}
