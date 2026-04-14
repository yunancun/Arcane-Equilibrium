use super::*;

#[test]
fn test_intent_processor_linucb_optional_no_panic_when_unset() {
    // EN: Default constructor leaves linucb=None; select_arm_after_gates
    //     must return None without panicking.
    // 中文：預設未設 linucb 時，select_arm_after_gates 不可 panic，回 None。
    let mut ip = IntentProcessor::new();
    let ctx = vec![0.5; crate::linucb::CONTEXT_DIM_V1];
    assert!(ip
        .select_arm_after_gates("trending", "ma_crossover", &ctx)
        .is_none());
    assert!(ip.last_arm_selection().is_none());
}

#[test]
fn test_intent_processor_linucb_select_called_after_gates_pass() {
    // EN: With a real LinUcbRuntime injected, select_arm_after_gates returns
    //     a valid selection and stores it as last_arm_selection.
    // 中文：注入真實 LinUcbRuntime 後，select_arm_after_gates 返回合法
    //     selection 並存入 last_arm_selection。
    let mut ip = IntentProcessor::new();
    ip.set_linucb_runtime(crate::linucb::LinUcbRuntime::cold_start_v1_15());
    let ctx = vec![0.5; crate::linucb::CONTEXT_DIM_V1];
    let sel = ip
        .select_arm_after_gates("trending", "ma_crossover", &ctx)
        .expect("arm exists");
    assert_eq!(sel.arm_id, "trending__ma_crossover");
    assert_eq!(ip.last_arm_selection().map(|s| s.arm_id.clone()),
               Some("trending__ma_crossover".to_string()));
}

fn make_intent(symbol: &str, is_long: bool) -> OrderIntent {
    OrderIntent {
        symbol: symbol.into(),
        is_long,
        qty: 0.01,
        confidence: 0.7,
        strategy: "test".into(),
        order_type: "market".into(),
        limit_price: None,
    }
}

#[test]
fn test_rejected_no_auth() {
    let proc = IntentProcessor::new();
    let gov = GovernanceCore::new(); // no auth
    let state = PaperState::new(10_000.0);
    let result = proc.process(&make_intent("BTC", true), &gov, &state, 500.0, GovernanceProfile::Exploration);
    assert!(!result.submitted);
    assert!(result.rejected_reason.unwrap().contains("governance"));
}

#[test]
fn test_approved_with_auth() {
    let proc = IntentProcessor::new();
    let mut gov = GovernanceCore::new();
    gov.grant_paper_authorization(None).unwrap();
    let mut state = PaperState::new(10_000.0);
    state.set_latest_price("BTC", 50000.0);
    // PH5-WIRE-0: ATR=2000 so EV=2000×0.7×0.004×0.2=$1.12 >> k×fee=1.5×$0.22=$0.33
    // (ATR raised from 500 to clear the 0.2 cold-start dampening factor)
    let result = proc.process(&make_intent("BTC", true), &gov, &state, 2000.0, GovernanceProfile::Exploration);
    assert!(result.submitted);
    assert!(result.fill.is_some());
}

#[test]
fn test_position_sizing_caps_qty() {
    // P1 cap: 2% of 10,000 / 50,000 = 0.004 BTC
    // Intent qty 0.01 should be reduced to 0.004.
    // P1 上限：10,000 * 2% / 50,000 = 0.004 BTC；意圖 qty 0.01 縮小為 0.004。
    // PH5-WIRE-0: ATR=2000 so EV=2000×0.7×0.004×0.2=$1.12 >> k×fee=$0.33
    let proc = IntentProcessor::new();
    let mut gov = GovernanceCore::new();
    gov.grant_paper_authorization(None).unwrap();
    let mut state = PaperState::new(10_000.0);
    state.set_latest_price("BTC", 50_000.0);
    let intent = make_intent("BTC", true); // qty=0.01
    let result = proc.process(&intent, &gov, &state, 2000.0, GovernanceProfile::Exploration);
    assert!(result.submitted);
    let fill = result.fill.unwrap();
    // fill.fill_qty should be 0.004 (= 10000 * 0.02 / 50000), not 0.01
    assert!(
        (fill.fill_qty - 0.004).abs() < 1e-9,
        "Expected qty ~0.004 from P1 sizing, got {}",
        fill.fill_qty
    );
}

#[test]
fn test_position_sizing_tiny_balance() {
    // With tiny balance, P1 calc gives very small qty — no artificial floor.
    // 餘額極小時，P1 計算給出極小 qty — 無人為下限。
    // PH5-WIRE-0: need ATR=2000 to clear cost_gate with dampening 0.2 at tiny notional.
    // final_qty=0.00004, notional=$2 → k=3.0, fee=$0.0022, need EV=2000×0.7×0.00004×0.2=$0.0112>$0.0066
    let proc = IntentProcessor::new();
    let mut gov = GovernanceCore::new();
    gov.grant_paper_authorization(None).unwrap();
    let mut state = PaperState::new(100.0); // tiny balance
    state.set_latest_price("BTC", 50_000.0);
    let intent = make_intent("BTC", true); // qty=0.01
    let result = proc.process(&intent, &gov, &state, 2000.0, GovernanceProfile::Exploration);
    assert!(result.submitted);
    let fill = result.fill.unwrap();
    // P1 calc: 100 * 0.02 / 50000 = 0.00004 — used directly, no MIN_QTY floor.
    assert!(
        (fill.fill_qty - 0.00004).abs() < 1e-9,
        "Expected P1-sized qty 0.00004, got {}",
        fill.fill_qty
    );
}

#[test]
fn test_position_sizing_small_intent_unchanged() {
    // If intent.qty < P1 cap, intent.qty is used (sizing never increases).
    // 如果 intent.qty < P1 上限，使用 intent.qty（sizing 只會縮小）。
    let proc = IntentProcessor::new();
    let mut gov = GovernanceCore::new();
    gov.grant_paper_authorization(None).unwrap();
    let mut state = PaperState::new(1_000_000.0); // large balance
    state.set_latest_price("ETH", 3_000.0);
    // P1 cap: 1,000,000 * 0.02 / 3000 = 6.67; intent qty=0.01 is smaller
    let intent = make_intent("ETH", true); // qty=0.01
    let result = proc.process(&intent, &gov, &state, 500.0, GovernanceProfile::Exploration);
    assert!(result.submitted);
    let fill = result.fill.unwrap();
    assert!(
        (fill.fill_qty - 0.01).abs() < 1e-9,
        "Expected intent qty 0.01 (under P1 cap), got {}",
        fill.fill_qty
    );
}

#[test]
fn test_fup8_phase2_approved_qty_exposed_on_success() {
    // FUP-8 Phase 2: paper path must expose the post-Kelly/P1 sized qty via
    // IntentResult.approved_qty so persist_intent writes the real qty to
    // trading.intents.details instead of the strategy's 1e9 sentinel.
    // FUP-8 Phase 2：paper 路徑必須通過 approved_qty 暴露 sizing 後的 qty，
    // 讓 persist_intent 寫入真實 qty 而非策略的 1e9 sentinel。
    let proc = IntentProcessor::new();
    let mut gov = GovernanceCore::new();
    gov.grant_paper_authorization(None).unwrap();
    let mut state = PaperState::new(10_000.0);
    state.set_latest_price("BTC", 50_000.0);
    // Mimic real strategy: submit 1e9 sentinel — processor must size it down.
    let mut intent = make_intent("BTC", true);
    intent.qty = 1e9;
    let result = proc.process(&intent, &gov, &state, 2000.0, GovernanceProfile::Exploration);
    assert!(result.submitted, "intent must pass gates");
    // P1 cap at 2%: 10000 * 0.02 / 50000 = 0.004 BTC
    assert!(
        (result.approved_qty - 0.004).abs() < 1e-9,
        "approved_qty should be P1-capped (0.004), got {}",
        result.approved_qty
    );
    assert!(
        result.approved_qty < 1.0,
        "approved_qty must NOT carry 1e9 sentinel, got {}",
        result.approved_qty
    );
    // Sanity: approved_qty matches the executed fill's qty.
    let fill = result.fill.expect("success path must have fill");
    assert!(
        (result.approved_qty - fill.fill_qty).abs() < 1e-9,
        "approved_qty ({}) must match fill.fill_qty ({})",
        result.approved_qty,
        fill.fill_qty
    );
}

#[test]
fn test_fup8_phase2_approved_qty_zero_on_rejection() {
    // FUP-8 Phase 2: rejection paths carry approved_qty=0.0.
    // FUP-8 Phase 2：拒絕路徑的 approved_qty 應為 0.0。
    let proc = IntentProcessor::new();
    let gov = GovernanceCore::new(); // not authorized → Gate 1 blocks
    let mut state = PaperState::new(10_000.0);
    state.set_latest_price("BTC", 50_000.0);
    let result = proc.process(&make_intent("BTC", true), &gov, &state, 500.0, GovernanceProfile::Exploration);
    assert!(!result.submitted);
    assert_eq!(result.approved_qty, 0.0);
}

#[test]
fn test_guardian_drawdown_rejection() {
    let proc = IntentProcessor::new();
    let mut gov = GovernanceCore::new();
    gov.grant_paper_authorization(None).unwrap();
    let mut state = PaperState::new(10_000.0);
    state.set_latest_price("BTC", 50000.0);
    // Simulate high drawdown
    state.force_drawdown(20.0);
    let result = proc.process(&make_intent("BTC", true), &gov, &state, 500.0, GovernanceProfile::Exploration);
    assert!(!result.submitted);
}

#[test]
fn test_cost_gate_rejects_low_confidence() {
    // Confidence below 0.15 → always rejected regardless of ATR
    // 信心低於 0.15 → 無論 ATR 如何都拒絕
    let proc = IntentProcessor::new();
    let mut gov = GovernanceCore::new();
    gov.grant_paper_authorization(None).unwrap();
    let mut state = PaperState::new(10_000.0);
    state.set_latest_price("ETH", 2000.0);
    let intent = OrderIntent {
        symbol: "ETH".into(),
        is_long: true,
        qty: 0.01,
        confidence: 0.10,
        strategy: "test".into(),
        order_type: "market".into(),
        limit_price: None,
    };
    let result = proc.process(&intent, &gov, &state, 10.0, GovernanceProfile::Exploration);
    assert!(!result.submitted);
    assert!(result
        .rejected_reason
        .unwrap()
        .contains("cost_gate: confidence"));
}

#[test]
fn test_cost_gate_cold_start_exploration_mode() {
    // Cold-start (no JS estimate) in paper mode → exploration mode (allow through).
    // Paper needs to accumulate trades; blocking creates dead-loop.
    // 冷啟動（無 JS 估計）在 paper 模式 → 探索模式（放行以積累數據）。
    let proc = IntentProcessor::new();
    let mut gov = GovernanceCore::new();
    gov.grant_paper_authorization(None).unwrap();
    let mut state = PaperState::new(10_000.0);
    state.set_latest_price("BTC", 67000.0);
    let intent = OrderIntent {
        symbol: "BTC".into(),
        is_long: true,
        qty: 0.001,
        confidence: 0.30,
        strategy: "test".into(),
        order_type: "market".into(),
        limit_price: None,
    };
    // ATR=20 (very compressed for BTC) — previously rejected by ATR cold-start gate,
    // now allowed in paper exploration mode to accumulate data.
    let result = proc.process(&intent, &gov, &state, 20.0, GovernanceProfile::Exploration);
    assert!(result.submitted, "cold-start paper should allow through for data accumulation");
}

#[test]
fn test_sec11_cost_gate_fail_closed_on_zero_atr() {
    // SEC-11: ATR=0 must reject (fail-closed), not bypass the gate.
    // SEC-11：ATR=0 必須拒絕（fail-closed），不可繞過。
    let proc = IntentProcessor::new();
    let mut gov = GovernanceCore::new();
    gov.grant_paper_authorization(None).unwrap();
    let mut state = PaperState::new(10_000.0);
    state.set_latest_price("BTC", 67000.0);
    let intent = OrderIntent {
        symbol: "BTC".into(),
        is_long: true,
        qty: 0.001,
        confidence: 0.50,
        strategy: "test".into(),
        order_type: "market".into(),
        limit_price: None,
    };
    // ATR=0 (indicator unavailable) — would have been waved through pre-SEC-11
    let result = proc.process(&intent, &gov, &state, 0.0, GovernanceProfile::Exploration);
    assert!(!result.submitted, "ATR=0 must fail-closed");
    assert!(result
        .rejected_reason
        .unwrap()
        .contains("ATR unavailable"));

    // Same on the exchange-mode path
    let gate = proc.process_gates_only(&intent, &gov, &state, 0.0, GovernanceProfile::Production);
    assert!(!gate.approved, "ATR=0 must fail-closed in gates_only too");
    assert!(gate.rejected_reason.unwrap().contains("ATR unavailable"));
}

#[test]
fn test_process_gates_only_cost_gate_rejects_low_ev() {
    // I-01: process_gates_only must enforce Gate 3 cost gate like process().
    // I-01：process_gates_only 必須像 process() 一樣執行 Gate 3 成本門控。
    let proc = IntentProcessor::new();
    let mut gov = GovernanceCore::new();
    gov.grant_paper_authorization(None).unwrap();
    let mut state = PaperState::new(10_000.0);
    state.set_latest_price("BTC", 67000.0);
    let intent = OrderIntent {
        symbol: "BTC".into(),
        is_long: true,
        qty: 0.001,
        confidence: 0.30,
        strategy: "test".into(),
        order_type: "market".into(),
        limit_price: None,
    };
    // ATR=20 compressed → EV << fee → reject
    let result = proc.process_gates_only(&intent, &gov, &state, 20.0, GovernanceProfile::Production);
    assert!(!result.approved);
    assert!(result.rejected_reason.unwrap().contains("cost_gate"));
}

#[test]
fn test_cost_gate_accepts_good_ev() {
    // High ATR + high confidence → EV >> fee → accepted.
    // 高 ATR + 高信心 → EV >> 手續費 → 接受。
    // PH5-WIRE-0 (cold-start 0.2 dampening):
    //   ATR=5.0, EV=5.0×0.7×0.2×0.2=$0.14, notional=$16 → k=3.0, rt_fee=$0.018 → k×fee=$0.053
    //   EV=$0.14 >> $0.053 ✓  (ATR raised from 1.5 to clear the 0.2 dampening at k=3.0)
    let proc = IntentProcessor::new();
    let mut gov = GovernanceCore::new();
    gov.grant_paper_authorization(None).unwrap();
    let mut state = PaperState::new(10_000.0);
    state.set_latest_price("SOL", 80.0);
    let intent = OrderIntent {
        symbol: "SOL".into(),
        is_long: true,
        qty: 0.2,
        confidence: 0.7,
        strategy: "test".into(),
        order_type: "market".into(),
        limit_price: None,
    };
    let result = proc.process(&intent, &gov, &state, 5.0, GovernanceProfile::Exploration);
    assert!(result.submitted);
}

#[test]
fn test_pnl5_cost_gate_k_tiers() {
    // PNL-5: k=3.0 below $50, k=2.0 below $200, k=1.5 otherwise (defaults).
    let proc = IntentProcessor::new();
    assert_eq!(proc.cost_gate_k(20.0), 3.0);
    assert_eq!(proc.cost_gate_k(49.99), 3.0);
    assert_eq!(proc.cost_gate_k(50.0), 2.0);
    assert_eq!(proc.cost_gate_k(199.99), 2.0);
    assert_eq!(proc.cost_gate_k(200.0), 1.5);
    assert_eq!(proc.cost_gate_k(10_000.0), 1.5);
}

#[test]
fn test_cost_gate_cold_start_allows_low_volatility_paper() {
    // Cold-start in paper mode: even low ATR% → exploration mode (allow through).
    // Previously rejected by ATR% gate, now allowed to accumulate data.
    // 冷啟動 paper 模式：即使低 ATR% → 探索模式放行以積累數據。
    let proc = IntentProcessor::new();
    let mut gov = GovernanceCore::new();
    gov.grant_paper_authorization(None).unwrap();
    let mut state = PaperState::new(1_000.0);
    state.set_latest_price("SOL", 80.0);
    let intent = OrderIntent {
        symbol: "SOL".into(),
        is_long: true,
        qty: 0.005,
        confidence: 0.4,
        strategy: "test".into(),
        order_type: "market".into(),
        limit_price: None,
    };
    let result = proc.process(&intent, &gov, &state, 0.1, GovernanceProfile::Exploration);
    assert!(result.submitted, "cold-start paper should allow low-volatility for data accumulation");
}

#[test]
fn test_slippage_tier_lookup() {
    // Verify slippage tiers match Python cost_gate.py SLIPPAGE_TIERS.
    // 驗證滑點分級與 Python cost_gate.py 一致。
    assert_eq!(lookup_slippage(2_000_000_000.0), 0.0001); // >$1B: 1 bps
    assert_eq!(lookup_slippage(500_000_000.0), 0.0002);   // >$100M: 2 bps
    assert_eq!(lookup_slippage(50_000_000.0), 0.0005);    // >$10M: 5 bps
    assert_eq!(lookup_slippage(5_000_000.0), 0.0015);     // >$1M: 15 bps
    assert_eq!(lookup_slippage(100_000.0), 0.0030);       // <$1M: 30 bps
    assert_eq!(lookup_slippage(0.0), DEFAULT_SLIPPAGE_RATE);
    assert_eq!(lookup_slippage(-1.0), DEFAULT_SLIPPAGE_RATE);
}

#[test]
fn test_cost_gate_js_win_rate_weighting() {
    // JS estimate with low win rate should require higher edge to pass.
    // win_rate=0.3 → threshold = fee_bps / 0.3 × 1.3 (tighter than wr=0.5)
    // 低勝率需要更高 edge 才能通過。
    let mut proc = IntentProcessor::new();
    let mut gov = GovernanceCore::new();
    gov.grant_paper_authorization(None).unwrap();
    let mut state = PaperState::new(10_000.0);
    state.set_latest_price("BTC", 67_000.0);
    // Set edge estimate with positive edge but low win_rate
    // fee_bps = 2 * (0.00055 + 0.0005) * 10000 = 21 bps (with 5bps default slippage)
    // threshold at wr=0.3: 21 / 0.3 × 1.3 = 91 bps
    // edge=25bps < 91bps → should reject
    let json = r#"{"test::BTC":{"shrunk_bps":25.0,"win_rate_shrunk":0.3,"n":50},"_meta":{"grand_mean_bps":10.0}}"#;
    let estimates = crate::edge_estimates::EdgeEstimates::load_from_str(json).unwrap_or_default();
    proc.set_edge_estimates(estimates);
    let intent = OrderIntent {
        symbol: "BTC".into(),
        is_long: true,
        qty: 0.001,
        confidence: 0.5,
        strategy: "test".into(),
        order_type: "market".into(),
        limit_price: None,
    };
    let result = proc.process(&intent, &gov, &state, 500.0, GovernanceProfile::Exploration);
    assert!(!result.submitted, "Low win_rate should tighten JS gate threshold");
    assert!(result.rejected_reason.unwrap().contains("cost_gate(JS)"));
}

#[test]
fn test_cost_gate_high_volume_reduces_slippage() {
    // High-volume symbol (BTC >$1B turnover) → slippage 1bps → lower cost → passes easier.
    // 高成交量幣種 → 滑點低 → 成本低 → 更容易通過。
    let proc = IntentProcessor::new();
    let mut gov = GovernanceCore::new();
    gov.grant_paper_authorization(None).unwrap();
    let mut state = PaperState::new(10_000.0);
    state.set_latest_price("BTC", 67_000.0);
    state.set_latest_turnover("BTC", 2_000_000_000.0); // $2B → 1bps slippage
    let intent = OrderIntent {
        symbol: "BTC".into(),
        is_long: true,
        qty: 0.001,
        confidence: 0.5,
        strategy: "test".into(),
        order_type: "market".into(),
        limit_price: None,
    };
    // BTC $67k, ATR=300 → atr_pct = 0.4478%
    // cost_pct = (0.00055 + 0.0001) × 2 × 100 = 0.13% (with 1bps slip)
    // min_move = 0.13 / 0.5 × 1.3 = 0.338%
    // 0.4478% > 0.338% → passes
    let result = proc.process(&intent, &gov, &state, 300.0, GovernanceProfile::Exploration);
    assert!(result.submitted, "BTC with high volume should pass: {:?}", result.rejected_reason);
}

#[test]
fn test_pnl1_rejects_qty_zero_process() {
    // PNL-1: When P1 sizing produces final_qty=0 (e.g. balance=0), reject.
    // PNL-1：P1 sizing 產生 final_qty=0 時拒絕（餘額=0 等情況）
    let proc = IntentProcessor::new();
    let mut gov = GovernanceCore::new();
    gov.grant_paper_authorization(None).unwrap();
    let mut state = PaperState::new(0.0); // zero balance → p1_max_qty=0
    state.set_latest_price("BTC", 50_000.0);
    let intent = make_intent("BTC", true);
    let result = proc.process(&intent, &gov, &state, 500.0, GovernanceProfile::Exploration);
    assert!(!result.submitted);
    let reason = result.rejected_reason.unwrap();
    assert!(reason.starts_with("qty_zero:"), "got: {}", reason);
}

#[test]
fn test_pnl1_rejects_qty_zero_gates_only() {
    // PNL-1 (exchange path): same guard in process_gates_only.
    // PNL-1（exchange 路徑）：process_gates_only 同一守衛
    let proc = IntentProcessor::new();
    let mut gov = GovernanceCore::new();
    gov.grant_paper_authorization(None).unwrap();
    let mut state = PaperState::new(0.0);
    state.set_latest_price("BTC", 50_000.0);
    let intent = make_intent("BTC", true);
    let result = proc.process_gates_only(&intent, &gov, &state, 500.0, GovernanceProfile::Production);
    assert!(!result.approved);
    assert_eq!(result.approved_qty, 0.0);
    assert!(result.rejected_reason.unwrap().starts_with("qty_zero:"));
}

// ── 3E-2a: GovernanceProfile + cost_gate_moderate tests ──

#[test]
fn test_governance_core_new_with_profile_exploration_auto_grants() {
    let gov = GovernanceCore::new_with_profile(GovernanceProfile::Exploration);
    assert!(gov.is_authorized(), "Exploration profile should auto-grant auth");
}

#[test]
fn test_governance_core_new_with_profile_validation_auto_grants() {
    let gov = GovernanceCore::new_with_profile(GovernanceProfile::Validation);
    assert!(gov.is_authorized(), "Validation profile should auto-grant auth");
}

#[test]
fn test_governance_core_new_with_profile_production_fail_closed() {
    let gov = GovernanceCore::new_with_profile(GovernanceProfile::Production);
    assert!(!gov.is_authorized(), "Production profile should NOT auto-grant auth");
}

#[test]
fn test_cost_gate_moderate_positive_edge_passes() {
    let mut proc = IntentProcessor::new();
    // Build estimates with a high positive edge (50 bps > any realistic threshold)
    let json = r#"{"ma_crossover::BTCUSDT": {"shrunk_bps": 50.0, "win_rate": 0.6, "n_trades": 100, "std_bps": 5.0}}"#;
    let estimates = crate::edge_estimates::EdgeEstimates::load_from_str(json).unwrap();
    proc.set_edge_estimates(estimates);
    let result = proc.cost_gate_moderate("ma_crossover", "BTCUSDT", 0.00055, 1_000_000_000.0);
    assert!(result.is_none(), "positive edge should pass moderate gate");
}

#[test]
fn test_cost_gate_moderate_negative_edge_blocks() {
    let mut proc = IntentProcessor::new();
    let json = r#"{"ma_crossover::BTCUSDT": {"shrunk_bps": -5.0, "win_rate": 0.4, "n_trades": 50, "std_bps": 2.0}}"#;
    let estimates = crate::edge_estimates::EdgeEstimates::load_from_str(json).unwrap();
    proc.set_edge_estimates(estimates);
    let result = proc.cost_gate_moderate("ma_crossover", "BTCUSDT", 0.00055, 1_000_000_000.0);
    assert!(result.is_some(), "negative edge should be blocked in moderate mode");
    assert!(result.unwrap().rejected_reason.unwrap().contains("demo"));
}

#[test]
fn test_cost_gate_moderate_cold_start_allows() {
    let proc = IntentProcessor::new();
    // No edge estimates set = cold start
    let result = proc.cost_gate_moderate("ma_crossover", "BTCUSDT", 0.00055, 1_000_000_000.0);
    assert!(result.is_none(), "cold start should be allowed in moderate mode (data accumulation)");
}

#[test]
fn test_process_with_exploration_profile() {
    let proc = IntentProcessor::new();
    let gov = GovernanceCore::new_with_profile(GovernanceProfile::Exploration);
    let mut state = PaperState::new(10_000.0);
    state.set_latest_price("BTC", 50_000.0);
    let intent = make_intent("BTC", true);
    let result = proc.process(&intent, &gov, &state, 500.0, GovernanceProfile::Exploration);
    assert!(result.submitted, "Exploration profile should process successfully");
}

#[test]
fn test_process_gates_with_production_no_auth_rejects() {
    let proc = IntentProcessor::new();
    let gov = GovernanceCore::new_with_profile(GovernanceProfile::Production);
    let mut state = PaperState::new(10_000.0);
    state.set_latest_price("BTC", 50_000.0);
    let intent = make_intent("BTC", true);
    let result = proc.process_gates_only(&intent, &gov, &state, 500.0, GovernanceProfile::Production);
    assert!(!result.approved, "Production without auth should reject");
    assert!(result.rejected_reason.unwrap().contains("governance_not_authorized"));
}

// ═══════════════════════════════════════════════════════════════════════
// BLOCKER-10 / D15: Global notional cap tests
// D15 全局名目上限測試
// ═══════════════════════════════════════════════════════════════════════

#[test]
fn test_d15_global_cap_disabled_when_zero() {
    // cap=0 (default) → check returns None regardless of exposure.
    // 上限=0（預設）→ 無論曝險多大都放行。
    let proc = IntentProcessor::new();
    assert!(proc.check_global_notional_cap(999_999.0).is_none());
}

#[test]
fn test_d15_global_cap_allows_under_limit() {
    // Projected exposure under cap → allowed.
    // 預估曝險低於上限 → 放行。
    let mut proc = IntentProcessor::new();
    proc.risk_config.limits.global_notional_cap_usdt = 100_000.0;
    let exposure = std::sync::Arc::new(std::sync::atomic::AtomicU64::new(5000_00)); // 5000 USDT
    proc.set_global_exposure(exposure);
    assert!(proc.check_global_notional_cap(10_000.0).is_none()); // 5000+10000=15000 < 100000
}

#[test]
fn test_d15_global_cap_blocks_over_limit() {
    // Projected exposure exceeds cap → blocked with reason.
    // 預估曝險超出上限 → 阻擋並附理由。
    let mut proc = IntentProcessor::new();
    proc.risk_config.limits.global_notional_cap_usdt = 10_000.0;
    let exposure = std::sync::Arc::new(std::sync::atomic::AtomicU64::new(9500_00)); // 9500 USDT
    proc.set_global_exposure(exposure);
    let result = proc.check_global_notional_cap(600.0); // 9500+600=10100 > 10000
    assert!(result.is_some());
    let reason = result.unwrap();
    assert!(reason.contains("global_notional_cap"), "reason: {reason}");
    assert!(reason.contains("10100.00"), "should show projected: {reason}");
}

#[test]
fn test_d15_global_cap_no_atomic_wired_allows() {
    // No shared atomic → cap check is a no-op (returns None).
    // 無共享原子量 → 上限檢查無效（返回 None）。
    let mut proc = IntentProcessor::new();
    proc.risk_config.limits.global_notional_cap_usdt = 10_000.0;
    // global_exposure_usdt remains None
    assert!(proc.check_global_notional_cap(999_999.0).is_none());
}

#[test]
fn test_d15_global_cap_exact_boundary_allows() {
    // Projected exactly == cap → allowed (strict >).
    // 預估剛好等於上限 → 放行（嚴格大於才阻擋）。
    let mut proc = IntentProcessor::new();
    proc.risk_config.limits.global_notional_cap_usdt = 10_000.0;
    let exposure = std::sync::Arc::new(std::sync::atomic::AtomicU64::new(9000_00)); // 9000
    proc.set_global_exposure(exposure);
    assert!(proc.check_global_notional_cap(1000.0).is_none()); // 9000+1000=10000 == cap → ok
}

#[test]
fn test_d15_global_cap_negative_cap_disabled() {
    // Negative cap value treated as disabled.
    // 負上限值視為禁用。
    let mut proc = IntentProcessor::new();
    proc.risk_config.limits.global_notional_cap_usdt = -100.0;
    let exposure = std::sync::Arc::new(std::sync::atomic::AtomicU64::new(999_999_00));
    proc.set_global_exposure(exposure);
    assert!(proc.check_global_notional_cap(100_000.0).is_none());
}

#[test]
fn test_d15_paper_path_cap_blocks_intent() {
    // Full process() path: cap blocks an intent that would otherwise pass.
    // 完整 process() 路徑：上限阻擋原本會通過的意圖。
    let mut proc = IntentProcessor::new();
    proc.risk_config.limits.global_notional_cap_usdt = 100.0; // very low cap
    let exposure = std::sync::Arc::new(std::sync::atomic::AtomicU64::new(99_00)); // 99 USDT
    proc.set_global_exposure(exposure);
    let gov = GovernanceCore::new_with_profile(GovernanceProfile::Exploration);
    let mut state = PaperState::new(10_000.0);
    state.set_latest_price("BTC", 50_000.0);
    let intent = make_intent("BTC", true); // qty=0.01 → notional=~200 USDT (after P1 sizing)
    let result = proc.process(&intent, &gov, &state, 2000.0, GovernanceProfile::Exploration);
    assert!(!result.submitted, "cap should block");
    assert!(result.rejected_reason.unwrap().contains("global_notional_cap"));
}

#[test]
fn test_d15_exchange_path_cap_blocks_intent() {
    // Full process_gates_only() path: cap blocks an exchange intent.
    // 完整 process_gates_only() 路徑：上限阻擋交易所意圖。
    let mut proc = IntentProcessor::new();
    proc.risk_config.limits.global_notional_cap_usdt = 100.0;
    let exposure = std::sync::Arc::new(std::sync::atomic::AtomicU64::new(99_00));
    proc.set_global_exposure(exposure);
    let gov = GovernanceCore::new_with_profile(GovernanceProfile::Exploration);
    let mut state = PaperState::new(10_000.0);
    state.set_latest_price("BTC", 50_000.0);
    let intent = make_intent("BTC", true);
    let _result = proc.process_gates_only(&intent, &gov, &state, 2000.0, GovernanceProfile::Production);
    // Production needs auth, so it'll reject on governance first. Use Exploration.
    let result = proc.process_gates_only(&intent, &gov, &state, 2000.0, GovernanceProfile::Validation);
    assert!(!result.approved, "cap should block exchange path");
    assert!(result.rejected_reason.unwrap().contains("global_notional_cap"));
}

// ═══════════════════════════════════════════════════════════════════════
// Router coverage — duplicate position / negative ATR / gates_only profiles
// 路由器覆蓋 — 重複持倉 / 負 ATR / gates_only 分支
// ═══════════════════════════════════════════════════════════════════════

/// EN: Same-direction duplicate position is rejected (Gate 1.5 in router.rs).
/// 中文: 同方向重複持倉被拒絕（router.rs Gate 1.5）。
#[test]
fn test_duplicate_position_same_direction_rejected() {
    let proc = IntentProcessor::new();
    let gov = GovernanceCore::new_with_profile(GovernanceProfile::Exploration);
    let mut state = PaperState::new(10_000.0);
    state.set_latest_price("BTC", 50_000.0);
    // Manually open a long BTC position in paper_state
    state.import_positions(vec![("BTC".into(), true, 0.001, 50_000.0, 0)]);
    // Try to open another long BTC → rejected
    let result = proc.process(&make_intent("BTC", true), &gov, &state, 2000.0, GovernanceProfile::Exploration);
    assert!(!result.submitted);
    assert!(result.rejected_reason.unwrap().contains("duplicate_position"));
}

/// EN: Opposite-direction intent on existing position is allowed (closes existing).
/// 中文: 現有持倉的反向意圖被允許（平掉現有持倉）。
#[test]
fn test_opposite_direction_on_existing_position_allowed() {
    let proc = IntentProcessor::new();
    let gov = GovernanceCore::new_with_profile(GovernanceProfile::Exploration);
    let mut state = PaperState::new(10_000.0);
    state.set_latest_price("BTC", 50_000.0);
    state.import_positions(vec![("BTC".into(), true, 0.001, 50_000.0, 0)]);
    // Short intent on existing long → should pass gate 1.5 (not duplicate)
    let intent = OrderIntent {
        symbol: "BTC".into(),
        is_long: false,
        qty: 0.001,
        confidence: 0.7,
        strategy: "test".into(),
        order_type: "market".into(),
        limit_price: None,
    };
    let result = proc.process(&intent, &gov, &state, 2000.0, GovernanceProfile::Exploration);
    // May be rejected by other gates (guardian drawdown, etc.), but NOT by duplicate check
    if let Some(reason) = &result.rejected_reason {
        assert!(!reason.contains("duplicate_position"),
            "opposite direction should not be rejected as duplicate, got: {reason}");
    }
}

/// EN: Negative ATR (impossible in practice) also triggers fail-closed (SEC-11).
/// 中文: 負 ATR（實際不應發生）同樣觸發 fail-closed（SEC-11）。
#[test]
fn test_negative_atr_fails_closed() {
    let proc = IntentProcessor::new();
    let gov = GovernanceCore::new_with_profile(GovernanceProfile::Exploration);
    let mut state = PaperState::new(10_000.0);
    state.set_latest_price("BTC", 50_000.0);
    let intent = make_intent("BTC", true);
    let result = proc.process(&intent, &gov, &state, -100.0, GovernanceProfile::Exploration);
    assert!(!result.submitted, "negative ATR must fail-closed");
    assert!(result.rejected_reason.unwrap().contains("ATR unavailable"));
}

/// EN: process_gates_only with Validation profile passes authorized intent.
/// 中文: process_gates_only 以 Validation 模式通過授權意圖。
#[test]
fn test_gates_only_validation_profile_passes() {
    let proc = IntentProcessor::new();
    let gov = GovernanceCore::new_with_profile(GovernanceProfile::Validation);
    let mut state = PaperState::new(10_000.0);
    state.set_latest_price("SOL", 80.0);
    let intent = OrderIntent {
        symbol: "SOL".into(),
        is_long: true,
        qty: 0.5,
        confidence: 0.7,
        strategy: "test".into(),
        order_type: "market".into(),
        limit_price: None,
    };
    let result = proc.process_gates_only(&intent, &gov, &state, 5.0, GovernanceProfile::Validation);
    assert!(result.approved, "Validation profile should pass: {:?}", result.rejected_reason);
    assert!(result.approved_qty > 0.0);
}

/// EN: process_gates_only duplicate same-direction also rejected.
/// 中文: process_gates_only 的同方向重複持倉也被拒絕。
#[test]
fn test_gates_only_duplicate_rejected() {
    let proc = IntentProcessor::new();
    let gov = GovernanceCore::new_with_profile(GovernanceProfile::Validation);
    let mut state = PaperState::new(10_000.0);
    state.set_latest_price("ETH", 3000.0);
    state.import_positions(vec![("ETH".into(), false, 0.1, 3000.0, 0)]);
    let intent = OrderIntent {
        symbol: "ETH".into(),
        is_long: false, // same direction as existing short
        qty: 0.05,
        confidence: 0.7,
        strategy: "test".into(),
        order_type: "market".into(),
        limit_price: None,
    };
    let result = proc.process_gates_only(&intent, &gov, &state, 50.0, GovernanceProfile::Validation);
    assert!(!result.approved);
    assert!(result.rejected_reason.unwrap().contains("duplicate_position"));
}
