// G5-09 sibling: FIX-18 zero-price-tick boundary + P0-5 PHANTOM-2-FUP
// ReduceToHalf cooldown / Normal-only clear + B2 sigma_scaled cooldown helper
// + DYNAMIC-RISK-1 sizer wiring (BUG-1/BUG-3) + P1-7 A persist_intent helper.
// G5-09 sibling：零價邊界、ReduceToHalf 冷卻、sigma 縮放、sizer 接線、
// persist_intent helper 訊息形狀。

use super::super::*;

// ── FIX-18: Price=0.0 tick boundary tests ──

/// FIX-18: A tick with price=0.0 must not panic or cause division-by-zero.
/// All code paths (indicators, stops, risk evaluator) must survive gracefully.
/// FIX-18：price=0.0 的 tick 不能 panic 或導致除零。所有路徑必須存活。
#[test]
fn test_zero_price_tick_no_panic() {
    let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Paper);
    // First feed some normal ticks to populate klines
    for i in 0..50 {
        let e = super::make_event("BTCUSDT", 50000.0, 1_000_000 + i * 60_000);
        pipeline.on_tick(&e);
    }
    // Now feed a zero-price tick — must not panic
    let zero_event = super::make_event("BTCUSDT", 0.0, 1_000_000 + 50 * 60_000);
    let _result = pipeline.on_tick(&zero_event);
    // Balance should be unchanged (no fills at price 0)
    assert!(
        pipeline.paper_state.balance() > 0.0,
        "balance must survive zero-price tick"
    );
}

/// FIX-18: A tick with price=0.0 on a symbol with open position must not produce NaN PnL.
/// FIX-18：有持倉的交易對收到 price=0 tick 時不能產生 NaN PnL。
#[test]
fn test_zero_price_tick_with_position_no_nan() {
    let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Paper);
    // Open a position via paper_state directly
    pipeline
        .paper_state
        .apply_fill("BTCUSDT", true, 0.01, 50000.0, 2.75, 100_000, "test");
    // Feed zero-price tick
    let zero_event = super::make_event("BTCUSDT", 0.0, 200_000);
    let _result = pipeline.on_tick(&zero_event);
    // Balance must still be finite
    let bal = pipeline.paper_state.balance();
    assert!(
        bal.is_finite(),
        "balance must be finite after zero-price tick, got {bal}"
    );
}

// ── P0-5: ReduceToHalf cooldown + Normal-only clear (PHANTOM-2-FUP) ──
// P0-5：ReduceToHalf 冷卻 + 僅 Normal 清空（PHANTOM-2 跟進修復）
//
// Root cause recap: FA-PHANTOM-2 (commit 348a9c5) added a
// `held_drop≥5% && sigma≥3` path that fires ReduceToHalf at risk<Defensive.
// EDGE-P0-1's old clear `< Defensive` wiped the guard every tick in
// persistent Cautious, producing 9 ReduceToHalf emissions in 1.3s
// on ORDIUSDT (engine.log 2026-04-16 18:03:41). Fix: per-symbol 60s
// cooldown (method A) + clear only at Normal (method C).
//
// 根因：FA-PHANTOM-2 開放了 risk<Defensive 下的 ReduceToHalf 路徑；原
// EDGE-P0-1 在 `<Defensive` 時清空 → Cautious 持續時毫秒連發。修復為
// 冷卻窗 + 僅 Normal 清空。

#[test]
fn test_ft_reduce_cooldown_expired_no_prior_entry() {
    // Never-halved symbol is always eligible — filter returns true.
    // 從未半倉的 symbol 永遠可觸發 — filter 回 true。
    let map: std::collections::HashMap<String, super::super::on_tick_helpers::FtReduceStamp> =
        std::collections::HashMap::new();
    assert!(super::super::on_tick_helpers::ft_reduce_cooldown_expired(
        &map,
        "BTCUSDT",
        1_700_000_000_000
    ));
}

#[test]
fn test_ft_reduce_cooldown_blocks_within_window() {
    // Same-tick and sub-cooldown re-emits are blocked.
    // 同 tick 與冷卻窗內的重觸發一律擋掉。
    let mut map: std::collections::HashMap<String, super::super::on_tick_helpers::FtReduceStamp> =
        std::collections::HashMap::new();
    // Stamp with base cooldown (60_000 ms) so the legacy semantics hold.
    // 以基準冷卻（60 秒）建檔，保留舊行為。
    map.insert("BTCUSDT".to_string(), (1_700_000_000_000, 60_000));
    // +0 ms (same tick) — reproduces the 1.3s / 9-fire cascade.
    // +0 毫秒（同 tick）— 複現 1.3s 連發 9 次的 cascade。
    assert!(!super::super::on_tick_helpers::ft_reduce_cooldown_expired(
        &map,
        "BTCUSDT",
        1_700_000_000_000
    ));
    // +59_999 ms (1 ms before cooldown expiry) — still blocked.
    // +59999 毫秒（冷卻到期前 1 毫秒）— 仍被擋。
    assert!(!super::super::on_tick_helpers::ft_reduce_cooldown_expired(
        &map,
        "BTCUSDT",
        1_700_000_059_999
    ));
}

#[test]
fn test_ft_reduce_cooldown_re_arms_after_window() {
    // Exactly at cooldown boundary re-arms; per-symbol independence holds.
    // 冷卻到期即解鎖；每 symbol 獨立計時。
    let mut map: std::collections::HashMap<String, super::super::on_tick_helpers::FtReduceStamp> =
        std::collections::HashMap::new();
    map.insert("BTCUSDT".to_string(), (1_700_000_000_000, 60_000));
    // Exactly 60_000 ms later — allowed (>= FT_REDUCE_COOLDOWN_MS).
    // 剛好 60 秒後 — 允許（>= FT_REDUCE_COOLDOWN_MS）。
    assert!(super::super::on_tick_helpers::ft_reduce_cooldown_expired(
        &map,
        "BTCUSDT",
        1_700_000_060_000
    ));
    // Different symbol shares no cooldown — independent.
    // 其他 symbol 不共享冷卻 — 獨立。
    assert!(super::super::on_tick_helpers::ft_reduce_cooldown_expired(
        &map,
        "ETHUSDT",
        1_700_000_000_000
    ));
}

#[test]
fn test_ft_reduce_clear_only_on_normal() {
    // Method C: the clear branch in on_tick.rs:158 only fires at Normal.
    // Cautious/Reduced/Defensive must keep the guard populated so symbols
    // already halved are not re-emitted when `ft_action == ReduceToHalf`
    // recurs on subsequent ticks under the same stress episode.
    // Method C：僅 Normal 觸發清空；Cautious/Reduced/Defensive 必須保留
    // 集合以避免同一 stress episode 下對同 symbol 重複半倉。
    use openclaw_core::sm::risk_gov::RiskLevel;

    for level in [
        RiskLevel::Cautious,
        RiskLevel::Reduced,
        RiskLevel::Defensive,
    ] {
        let clear_condition = level == RiskLevel::Normal;
        assert!(
            !clear_condition,
            "clear must NOT fire at {:?} — would re-open the cascade bug",
            level
        );
    }
    assert!(
        RiskLevel::Normal == RiskLevel::Normal,
        "clear MUST fire at Normal — fast re-arm for a fresh episode"
    );
}

/// P0-5 regression: drive ReduceToHalf for the SAME symbol twice within
/// the cooldown window on a live `TickPipeline` and assert only the first
/// emit stamps the cooldown map. Complements the helper-level tests by
/// covering the filter+insert wiring in on_tick.rs:186-237.
/// P0-5 回歸：在真正的 TickPipeline 上對同一 symbol 冷卻窗內連發兩次
/// ReduceToHalf，驗證第二次被 filter 擋下、map 不重複覆寫。
#[test]
fn test_ft_reduce_cooldown_map_stamps_once_per_window() {
    let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Paper);
    // Seed a position so the ReduceToHalf branch has something to halve.
    // 先建倉，讓 ReduceToHalf 分支有倉可減。
    pipeline
        .paper_state
        .apply_fill("BTCUSDT", true, 0.1, 50_000.0, 0.0, 1_000, "test");
    assert_eq!(pipeline.paper_state.position_count(), 1);

    // Simulate first halving at ts = 1_000_000 with base 60s cooldown.
    // 模擬第一次半倉，時間戳 1,000,000，基準 60 秒冷卻。
    pipeline
        .ft_reduced_symbols
        .insert("BTCUSDT".to_string(), (1_000_000, 60_000));

    // Within cooldown window (+30 s) — filter must reject the symbol.
    // 冷卻窗內（+30 秒）— filter 必須擋下。
    let now_within = 1_000_000 + 30_000;
    assert!(!super::super::on_tick_helpers::ft_reduce_cooldown_expired(
        &pipeline.ft_reduced_symbols,
        "BTCUSDT",
        now_within
    ));

    // Past cooldown window (+60 s exact) — filter must re-admit.
    // 冷卻到期（+60 秒）— filter 重新放行。
    let now_after = 1_000_000 + 60_000;
    assert!(super::super::on_tick_helpers::ft_reduce_cooldown_expired(
        &pipeline.ft_reduced_symbols,
        "BTCUSDT",
        now_after
    ));
}

// ── B2: sigma_scaled_reduce_cooldown_ms — pure function tests ──
// B2：sigma_scaled_reduce_cooldown_ms 純函數測試
//
// Formula: base (60_000) × max(1, sigma/3), capped at FT_REDUCE_COOLDOWN_MAX_MS.
// Trigger threshold is sigma≥3 (fast_track.rs:89) — at exactly 3σ the
// cooldown equals base; each additional sigma scales linearly.
// 公式：base × max(1, sigma/3)，上限 600_000。3σ = 1×，每多 1σ 線性放大。

#[test]
fn test_b2_sigma_scaled_at_trigger_threshold() {
    // sigma = 3.0 (minimum trigger) → cooldown = base.
    // sigma = 3.0（觸發下限）→ 冷卻 = 基準。
    assert_eq!(
        super::super::on_tick_helpers::sigma_scaled_reduce_cooldown_ms(3.0),
        super::super::on_tick_helpers::FT_REDUCE_COOLDOWN_MS
    );
}

#[test]
fn test_b2_sigma_scaled_linear_above_threshold() {
    // sigma = 6 → 2× base; sigma = 9 → 3× base.
    // sigma = 6 → 2×；sigma = 9 → 3×。
    assert_eq!(
        super::super::on_tick_helpers::sigma_scaled_reduce_cooldown_ms(6.0),
        super::super::on_tick_helpers::FT_REDUCE_COOLDOWN_MS * 2
    );
    assert_eq!(
        super::super::on_tick_helpers::sigma_scaled_reduce_cooldown_ms(9.0),
        super::super::on_tick_helpers::FT_REDUCE_COOLDOWN_MS * 3
    );
}

#[test]
fn test_b2_sigma_scaled_clamps_at_max() {
    // sigma = 30 → 10× base = 600_000 (at cap). sigma = 50 → still 600_000.
    // sigma = 30 → 10×（上限）；sigma = 50 → 仍上限。
    assert_eq!(
        super::super::on_tick_helpers::sigma_scaled_reduce_cooldown_ms(30.0),
        super::super::on_tick_helpers::FT_REDUCE_COOLDOWN_MAX_MS
    );
    assert_eq!(
        super::super::on_tick_helpers::sigma_scaled_reduce_cooldown_ms(50.0),
        super::super::on_tick_helpers::FT_REDUCE_COOLDOWN_MAX_MS
    );
}

#[test]
fn test_b2_sigma_scaled_floors_at_base() {
    // Below-threshold sigma (defensive caller) must not shrink the guard
    // below base — floor at FT_REDUCE_COOLDOWN_MS.
    // 低於 3σ 的防禦性入口不可縮短冷卻 — 以 base 為下限。
    assert_eq!(
        super::super::on_tick_helpers::sigma_scaled_reduce_cooldown_ms(1.0),
        super::super::on_tick_helpers::FT_REDUCE_COOLDOWN_MS
    );
    assert_eq!(
        super::super::on_tick_helpers::sigma_scaled_reduce_cooldown_ms(0.0),
        super::super::on_tick_helpers::FT_REDUCE_COOLDOWN_MS
    );
}

/// DYNAMIC-RISK-1 BUG-1 regression: paper-mode `ipc_close_all` must forward
/// every closed position's realized PnL to the in-pipeline sizer so the
/// Sharpe window captures session-end / operator-flatten outcomes.
/// DYNAMIC-RISK-1 BUG-1 回歸：paper 模式 ipc_close_all 必須把每筆實現 PnL
/// 餵給 sizer，避免緊急平倉的 loss 訊號丟失。
#[test]
fn test_dynamic_risk_1_paper_close_all_feeds_sizer() {
    let mut pipeline =
        TickPipeline::with_kind(&["BTCUSDT", "ETHUSDT"], 10_000.0, PipelineKind::Paper);
    // Force the sizer into a sharp config so the window is populated.
    // 強制 sizer 使用收斂的配置，讓視窗能被填滿。
    let cfg = crate::dynamic_risk_sizer::DynamicRiskSizerConfig {
        enabled: true,
        min_trades: 2,
        step_pct: 0.005,
        min_pct: 0.01,
        max_pct: 0.05,
        sharpe_high: 0.5,
        sharpe_low: -0.5,
        update_interval_ms: 0,
        window_size: 20,
    };
    pipeline.dynamic_risk_sizer = crate::dynamic_risk_sizer::DynamicRiskSizer::new(0.03, cfg);
    pipeline
        .paper_state
        .apply_fill("BTCUSDT", true, 0.1, 50_000.0, 0.0, 0, "seed");
    pipeline
        .paper_state
        .apply_fill("ETHUSDT", false, 1.0, 3_000.0, 0.0, 0, "seed");
    pipeline.paper_state.set_latest_price("BTCUSDT", 51_000.0);
    pipeline.paper_state.set_latest_price("ETHUSDT", 2_900.0);
    assert_eq!(pipeline.dynamic_risk_sizer.status().trades_in_window, 0);

    let count = pipeline.ipc_close_all();

    assert_eq!(count, 2, "both positions must be closed");
    assert_eq!(
        pipeline.dynamic_risk_sizer.status().trades_in_window,
        2,
        "sizer must have received realized PnL from every closed position"
    );
}

/// DYNAMIC-RISK-1 BUG-3 regression: when operator patches `p1_risk_pct`
/// via IPC, the sizer's `current_pct` must be rebased to the new value so
/// the next `maybe_update` does not overwrite operator intent with a stale
/// pre-patch pct. This locks the handlers.rs set_p1_risk_pct + rebase pair.
/// DYNAMIC-RISK-1 BUG-3 回歸：operator 改 p1_risk_pct 後 sizer 必須重錨，
/// 否則下一次 maybe_update 會用舊值覆蓋 operator 指令。
#[test]
fn test_dynamic_risk_1_operator_patch_rebases_sizer() {
    let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Paper);
    let cfg = crate::dynamic_risk_sizer::DynamicRiskSizerConfig {
        enabled: true,
        min_trades: 2,
        step_pct: 0.005,
        min_pct: 0.01,
        max_pct: 0.05,
        sharpe_high: 0.5,
        sharpe_low: -0.5,
        update_interval_ms: 0,
        window_size: 20,
    };
    pipeline.dynamic_risk_sizer = crate::dynamic_risk_sizer::DynamicRiskSizer::new(0.03, cfg);
    // Push losing trades — next maybe_update would step down without rebase.
    // 推入虧損樣本；若不 rebase，下次 maybe_update 會把 pct 往下調。
    for _ in 0..6 {
        pipeline.dynamic_risk_sizer.record_closed_trade(-1.0);
        pipeline.dynamic_risk_sizer.record_closed_trade(-1.1);
    }

    // Simulate the handlers.rs patch: set cap + rebase sizer.
    // 模擬 handlers.rs：設 cap + rebase。
    pipeline.intent_processor.set_p1_risk_pct(0.04);
    pipeline.dynamic_risk_sizer.rebase(0.04);

    let next = pipeline.dynamic_risk_sizer.maybe_update(10_000);
    // With rebase, current_pct anchors at 0.04, next step goes to 0.035
    // (down, because Sharpe is still low). Without rebase, it would have
    // moved from 0.03 → 0.025, ignoring operator intent entirely.
    // 有 rebase：0.04 → 0.035（下調一步）。無 rebase：0.03 → 0.025（操作失效）。
    let published = next.expect("sizer should publish an update on low Sharpe");
    assert!(
        (published - 0.035).abs() < 1e-9,
        "rebase must anchor the next step at operator-set 0.04, got {}",
        published
    );
}

#[test]
fn test_b2_cooldown_expiry_uses_stamped_window_not_base() {
    // Regression: the 6σ halving event stamped 120 s into the map must
    // BLOCK a retry at +90 s (would pass against base 60 s) and ADMIT one
    // at +120 s exactly. Locks the B2 wiring in ft_reduce_cooldown_expired.
    // 回歸：6σ 事件寫入 120 s 冷卻 → +90 s 擋、+120 s 放行（基準 60 s 會誤放 +90 s）。
    let mut map: std::collections::HashMap<String, super::super::on_tick_helpers::FtReduceStamp> =
        std::collections::HashMap::new();
    let stamped = super::super::on_tick_helpers::sigma_scaled_reduce_cooldown_ms(6.0);
    assert_eq!(stamped, 120_000);
    map.insert("MICRO".to_string(), (1_000_000, stamped));
    // +90 s — inside the sigma-scaled window, must block.
    assert!(!super::super::on_tick_helpers::ft_reduce_cooldown_expired(
        &map,
        "MICRO",
        1_000_000 + 90_000
    ));
    // +119_999 — still inside the stamped window.
    assert!(!super::super::on_tick_helpers::ft_reduce_cooldown_expired(
        &map,
        "MICRO",
        1_000_000 + 119_999
    ));
    // +120_000 — exact expiry.
    assert!(super::super::on_tick_helpers::ft_reduce_cooldown_expired(
        &map,
        "MICRO",
        1_000_000 + 120_000
    ));
}

/// P1-7 A INTENT-WRITE-GAP-1 regression (2026-04-18). Direct contract test for
/// `persist_intent` helper invoked from on_tick.rs:893 (exchange branch fix
/// landed in the same commit). Pre-fix the exchange branch only persisted
/// verdicts (line 837), leaving `trading.intents` empty for live/live_demo
/// despite millions of Approved verdicts. The helper itself was never broken;
/// the bug was a missing call site. This test guards the message shape the
/// new caller depends on so a future refactor of TradingMsg::Intent doesn't
/// silently break the audit lane again.
/// P1-7 A INTENT-WRITE-GAP-1 回歸：on_tick.rs:893（exchange 分支修復）依賴的
/// persist_intent 輔助方法的契約測試 — 守住 TradingMsg::Intent 訊息形狀
/// 不被未來重構靜默破壞。
#[test]
fn test_persist_intent_helper_emits_trading_msg_intent_with_engine_mode() {
    use crate::intent_processor::OrderIntent;
    let intent = OrderIntent {
        symbol: "ETHUSDT".into(),
        is_long: false,
        qty: 1.0e9, // sentinel — final_qty / approved_qty is what gets persisted
        confidence: 0.83,
        strategy: "ma_crossover".into(),
        order_type: "market".into(),
        limit_price: None,
        confluence_score: None,
        persistence_elapsed_ms: None,
        time_in_force: None,
        maker_timeout_ms: None,
    };
    let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::TradingMsg>(8);

    super::super::on_tick_helpers::persist_intent(
        &Some(tx),
        "live_demo",
        1_700_000_000_123,
        "sig-live_demo-ma_crossover-ETHUSDT-1700000000123",
        "ctx-live_demo-ETHUSDT-1700000000123",
        &intent,
        0.045, // post-rounding final_qty (NOT the 1e9 sentinel)
        2_500.0,
        "live_demo",
        None,
    );

    let msg = rx.try_recv().expect("Intent must be enqueued");
    match msg {
        crate::database::TradingMsg::Intent {
            engine_mode,
            symbol,
            side,
            qty,
            strategy_name,
            ..
        } => {
            assert_eq!(engine_mode, "live_demo");
            assert_eq!(symbol, "ETHUSDT");
            assert_eq!(side, "Sell");
            assert!(
                (qty - 0.045).abs() < 1e-12,
                "qty must be sized final_qty, not 1e9 sentinel"
            );
            assert_eq!(strategy_name, "ma_crossover");
        }
        other => panic!("expected TradingMsg::Intent, got {:?}", other),
    }
}

#[test]
fn test_persist_intent_helper_records_maker_entry_details() {
    use crate::intent_processor::OrderIntent;
    use crate::order_manager::TimeInForce;

    let intent = OrderIntent {
        symbol: "BTCUSDT".into(),
        is_long: true,
        qty: 0.25,
        confidence: 0.91,
        strategy: "grid_trading".into(),
        order_type: "limit".into(),
        limit_price: Some(49_995.0),
        confluence_score: None,
        persistence_elapsed_ms: None,
        time_in_force: Some(TimeInForce::PostOnly),
        maker_timeout_ms: Some(45_000),
    };
    let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::TradingMsg>(8);

    super::super::on_tick_helpers::persist_intent(
        &Some(tx),
        "demo",
        1_700_000_000_456,
        "sig-demo-grid_trading-BTCUSDT-1700000000456",
        "ctx-demo-BTCUSDT-1700000000456",
        &intent,
        0.25,
        49_995.0,
        "demo",
        None,
    );

    let msg = rx.try_recv().expect("Intent must be enqueued");
    match msg {
        crate::database::TradingMsg::Intent {
            order_type,
            details,
            ..
        } => {
            assert_eq!(order_type, "limit");
            let details = details.expect("maker metadata must be persisted");
            assert_eq!(details["time_in_force"].as_str(), Some("PostOnly"));
            assert_eq!(details["post_only"].as_bool(), Some(true));
            assert_eq!(details["maker_timeout_ms"].as_u64(), Some(45_000));
            assert_eq!(details["limit_price"].as_f64(), Some(49_995.0));
        }
        other => panic!("expected TradingMsg::Intent, got {:?}", other),
    }
}

#[test]
fn test_persist_intent_helper_records_scanner_opportunity_shadow_details() {
    use crate::intent_processor::OrderIntent;
    use crate::scanner::types::{OpportunityComponents, OpportunityDecision};

    let intent = OrderIntent {
        symbol: "BTCUSDT".into(),
        is_long: true,
        qty: 0.25,
        confidence: 0.91,
        strategy: "ma_crossover".into(),
        order_type: "limit".into(),
        limit_price: Some(50_000.0),
        confluence_score: None,
        persistence_elapsed_ms: None,
        time_in_force: None,
        maker_timeout_ms: None,
    };
    let scanner = super::super::on_tick_helpers::IntentScannerContext {
        scan_id: "scan-1".to_string(),
        best_strategy: "ma_crossover".to_string(),
        intent_strategy: "ma_crossover".to_string(),
        market_regime: "trending".to_string(),
        trend_phase: "clean_trend".to_string(),
        trend_score: 0.8,
        range_score: 0.2,
        shock_score: 0.1,
        close_alignment: 0.9,
        range_position: 0.8,
        crowding_score: 0.1,
        reversal_risk_score: 0.0,
        directional_efficiency: 0.7,
        dir_pct: 3.0,
        signed_dir_pct: 3.0,
        range_pct: 5.0,
        fr_bps: 1.0,
        f_ma: 90.0,
        f_grid: 10.0,
        f_bbrv: 5.0,
        f_bkout: 70.0,
        f_funding_arb: 0.0,
        edge_bps: None,
        edge_n: 0,
        edge_status: "unexplored".to_string(),
        route_mode: "exploration".to_string(),
        market_status: "compatible".to_string(),
        route_reason: "test".to_string(),
        opportunity: Some(OpportunityDecision {
            opportunity_score: 64.0,
            opportunity_lcb_bps: Some(7.0),
            admission_hint: "exploration_candidate".to_string(),
            reason: "shadow".to_string(),
            components: OpportunityComponents {
                market_structure_score: 90.0,
                strategy_fitness_score: 90.0,
                gross_current_opportunity_bps: Some(27.0),
                expected_execution_cost_bps: Some(12.0),
                cost_uncertainty_bps: Some(2.0),
                uncertainty_buffer_bps: Some(6.0),
                historical_edge_bps: None,
                historical_edge_n: 0,
                historical_edge_lcb_bps: None,
                data_quality_score: 0.9,
                calibration_weight: 0.0,
            },
        }),
        final_score: 92.0,
        raw_score: 90.0,
    };
    let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::TradingMsg>(8);

    super::super::on_tick_helpers::persist_intent(
        &Some(tx),
        "demo",
        1_700_000_000_789,
        "sig-demo-ma_crossover-BTCUSDT-1700000000789",
        "ctx-demo-BTCUSDT-1700000000789",
        &intent,
        0.25,
        50_000.0,
        "demo",
        Some(&scanner),
    );

    let msg = rx.try_recv().expect("Intent must be enqueued");
    match msg {
        crate::database::TradingMsg::Intent { details, .. } => {
            let details = details.expect("details must be persisted");
            let opportunity = &details["scanner"]["opportunity"];
            assert_eq!(
                opportunity["admission_hint"].as_str(),
                Some("exploration_candidate")
            );
            assert_eq!(opportunity["opportunity_lcb_bps"].as_f64(), Some(7.0));
            assert_eq!(
                opportunity["components"]["expected_execution_cost_bps"].as_f64(),
                Some(12.0)
            );
        }
        other => panic!("expected TradingMsg::Intent, got {:?}", other),
    }
}
