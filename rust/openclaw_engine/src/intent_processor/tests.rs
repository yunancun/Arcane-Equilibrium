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

// ============================================================
// EDGE-P3-1 A4: Predictor-gate wiring tests
// ============================================================
//
// These tests exercise `process_with_features()` / `process_gates_only_with_features()`
// and the `evaluate_predictor_gate()` helper. They prove:
//   1. features=None → predictor never consulted (no change in behavior).
//   2. use_edge_predictor=false → predictor never consulted.
//   3. shadow_mode=true → predictor runs but JS gate decides (observation).
//   4. shadow_mode=false + Accept → JS gate bypassed.
//   5. shadow_mode=false + Reject → hard reject.
//   6. Fallback(Shrinkage) → fall through to JS gate.
//   7. Fallback(FailClosed) → hard reject with metric-name suffix.
//   8. ShadowFill (ε-greedy paper) → emits EmitShadowFill IPC.
//
// 下列測試覆寫 predictor gate 與 process_with_features 的接線；
// 驗證 features=None / 禁用 / shadow / Accept / Reject / Fallback / ShadowFill。

#[cfg(test)]
mod predictor_wiring_tests {
    use super::*;
    use crate::config::risk_config::EdgePredictorFallback;
    use crate::edge_predictor::{
        features::FeatureVectorV1, EdgePredictor as EdgePredictorTrait, EdgePredictorStore,
        PredictError, Prediction,
    };
    use crate::tick_pipeline::PipelineCommand;
    use std::sync::Arc;

    struct StubOkPredictor {
        pred: Prediction,
    }

    impl EdgePredictorTrait for StubOkPredictor {
        fn predict(&self, _f: &FeatureVectorV1) -> Result<Prediction, PredictError> {
            Ok(self.pred)
        }
        fn age_seconds(&self) -> u64 {
            0
        }
        fn schema_hash(&self) -> &str {
            "stub-schema"
        }
        fn definition_hash(&self) -> &str {
            "stub-def"
        }
        fn model_id(&self) -> &str {
            "stub"
        }
    }

    fn approved_governance() -> GovernanceCore {
        let mut g = GovernanceCore::new();
        g.grant_paper_authorization(None).unwrap();
        g
    }

    fn paper_state_with_price(price: f64) -> PaperState {
        let mut s = PaperState::new(10_000.0);
        s.set_latest_price("BTCUSDT", price);
        s.set_latest_turnover("BTCUSDT", 100_000_000.0);
        s
    }

    fn intent_btc(confidence: f64) -> OrderIntent {
        OrderIntent {
            symbol: "BTCUSDT".into(),
            is_long: true,
            qty: 0.001,
            confidence,
            strategy: "test".into(),
            order_type: "market".into(),
            limit_price: None,
        }
    }

    #[test]
    fn test_process_with_features_none_behaves_identically_to_legacy() {
        // features=None → predictor skipped regardless of store/config.
        // features=None → 忽略 predictor，行為等同舊路徑。
        let mut proc = IntentProcessor::new();
        proc.risk_config.edge_predictor.use_edge_predictor = true;
        proc.risk_config.edge_predictor.shadow_mode = false;
        let store = Arc::new(EdgePredictorStore::new());
        store.swap(
            "test",
            Arc::new(StubOkPredictor {
                pred: Prediction { q10: 100.0, q50: 200.0, q90: 300.0 },
            }),
        );
        proc.set_edge_predictor_store(store);
        let gov = approved_governance();
        let state = paper_state_with_price(30_000.0);
        // Intent goes through legacy JS cost_gate_paper path — cold-start exploration mode
        // means it passes to fill. Without features the predictor shouldn't short-circuit.
        // features=None 時 predictor 不短路，走舊 JS gate（冷啟動探索放行）。
        let r = proc.process_with_features(
            &intent_btc(0.7), &gov, &state, 500.0,
            GovernanceProfile::Exploration, None, None, 0,
        );
        assert!(r.submitted, "features=None must delegate to legacy path; got {:?}", r.rejected_reason);
    }

    #[test]
    fn test_use_edge_predictor_false_skips_gate() {
        // cfg.use_edge_predictor=false (default) → predictor never called.
        // cfg.use_edge_predictor=false（預設）→ 不呼叫 predictor。
        let mut proc = IntentProcessor::new();
        assert!(!proc.risk_config.edge_predictor.use_edge_predictor);
        let store = Arc::new(EdgePredictorStore::new());
        proc.set_edge_predictor_store(store);
        let gov = approved_governance();
        let state = paper_state_with_price(30_000.0);
        let features = FeatureVectorV1::zeroed();
        let r = proc.process_with_features(
            &intent_btc(0.7), &gov, &state, 500.0,
            GovernanceProfile::Exploration, Some(&features), Some("ctx-1"), 1_700_000_000_000,
        );
        assert!(r.submitted, "use_edge_predictor=false must pass through; got {:?}", r.rejected_reason);
    }

    #[test]
    fn test_shadow_mode_falls_through_to_legacy_even_on_reject_outcome() {
        // shadow_mode=true + margin-insufficient predictor → gate would reject,
        // but shadow_mode forces fall-through to JS gate (observation stage).
        // shadow_mode=true 即使 margin 不足也回退 JS gate（觀察階段）。
        let mut proc = IntentProcessor::new();
        proc.risk_config.edge_predictor.use_edge_predictor = true;
        proc.risk_config.edge_predictor.shadow_mode = true;
        let store = Arc::new(EdgePredictorStore::new());
        store.swap(
            "test",
            Arc::new(StubOkPredictor {
                pred: Prediction { q10: -100.0, q50: -50.0, q90: -10.0 },
            }),
        );
        proc.set_edge_predictor_store(store);
        let gov = approved_governance();
        let state = paper_state_with_price(30_000.0);
        let features = FeatureVectorV1::zeroed();
        let r = proc.process_with_features(
            &intent_btc(0.7), &gov, &state, 500.0,
            GovernanceProfile::Exploration, Some(&features), Some("ctx-1"), 0,
        );
        assert!(r.submitted,
            "shadow_mode=true must fall through to legacy; got {:?}", r.rejected_reason);
    }

    #[test]
    fn test_accept_bypasses_legacy_gate() {
        // shadow_mode=false + predictor Accept → submitted (JS gate bypassed).
        // Use a Prediction with large positive margin vs tiny cost.
        // shadow_mode=false + Accept → submitted（跳過 JS gate）。
        let mut proc = IntentProcessor::new();
        proc.risk_config.edge_predictor.use_edge_predictor = true;
        proc.risk_config.edge_predictor.shadow_mode = false;
        let store = Arc::new(EdgePredictorStore::new());
        store.swap(
            "test",
            Arc::new(StubOkPredictor {
                pred: Prediction { q10: 100.0, q50: 200.0, q90: 300.0 },
            }),
        );
        proc.set_edge_predictor_store(store);
        let gov = approved_governance();
        let state = paper_state_with_price(30_000.0);
        let features = FeatureVectorV1::zeroed();
        let r = proc.process_with_features(
            &intent_btc(0.7), &gov, &state, 500.0,
            GovernanceProfile::Exploration, Some(&features), Some("ctx-1"), 0,
        );
        assert!(r.submitted, "Accept must bypass JS gate and submit; got {:?}", r.rejected_reason);
    }

    #[test]
    fn test_reject_short_circuits() {
        // shadow_mode=false + margin-insufficient + exploration_rate=0 → Reject.
        // shadow_mode=false + margin 不足 + exploration_rate=0 → 拒絕。
        let mut proc = IntentProcessor::new();
        proc.risk_config.edge_predictor.use_edge_predictor = true;
        proc.risk_config.edge_predictor.shadow_mode = false;
        proc.risk_config.edge_predictor.exploration_rate = 0.0;
        let store = Arc::new(EdgePredictorStore::new());
        store.swap(
            "test",
            Arc::new(StubOkPredictor {
                pred: Prediction { q10: -100.0, q50: -50.0, q90: -10.0 },
            }),
        );
        proc.set_edge_predictor_store(store);
        let gov = approved_governance();
        let state = paper_state_with_price(30_000.0);
        let features = FeatureVectorV1::zeroed();
        let r = proc.process_with_features(
            &intent_btc(0.7), &gov, &state, 500.0,
            GovernanceProfile::Exploration, Some(&features), Some("ctx-1"), 0,
        );
        assert!(!r.submitted);
        let reason = r.rejected_reason.expect("reason set");
        assert!(
            reason.contains("predictor_cost_margin_insufficient"),
            "expected margin-insufficient reason, got {reason}"
        );
    }

    #[test]
    fn test_fallback_shrinkage_uses_legacy_gate() {
        // use_edge_predictor=true but no model swapped in → Fallback(NoModel) → Shrinkage → legacy.
        // use_edge_predictor=true 但未 swap model → Fallback(NoModel) → Shrinkage → 走 JS gate。
        let mut proc = IntentProcessor::new();
        proc.risk_config.edge_predictor.use_edge_predictor = true;
        proc.risk_config.edge_predictor.shadow_mode = false;
        proc.risk_config.edge_predictor.fallback_on_error = EdgePredictorFallback::Shrinkage;
        let store = Arc::new(EdgePredictorStore::new());
        // No swap — gate returns Fallback(NoModel).
        proc.set_edge_predictor_store(store);
        let gov = approved_governance();
        let state = paper_state_with_price(30_000.0);
        let features = FeatureVectorV1::zeroed();
        let r = proc.process_with_features(
            &intent_btc(0.7), &gov, &state, 500.0,
            GovernanceProfile::Exploration, Some(&features), Some("ctx-1"), 0,
        );
        // JS gate cold-start exploration passes the intent.
        // JS gate 冷啟動探索模式放行。
        assert!(r.submitted,
            "Fallback(Shrinkage) must delegate to legacy gate; got {:?}", r.rejected_reason);
    }

    #[test]
    fn test_fallback_fail_closed_rejects_with_metric_suffix() {
        // fallback_on_error=FailClosed + no model → hard reject, reason ends with metric name.
        // fallback_on_error=FailClosed + 無 model → 硬拒絕，reason 以 metric 名結尾。
        let mut proc = IntentProcessor::new();
        proc.risk_config.edge_predictor.use_edge_predictor = true;
        proc.risk_config.edge_predictor.shadow_mode = false;
        proc.risk_config.edge_predictor.fallback_on_error = EdgePredictorFallback::FailClosed;
        let store = Arc::new(EdgePredictorStore::new());
        proc.set_edge_predictor_store(store);
        let gov = approved_governance();
        let state = paper_state_with_price(30_000.0);
        let features = FeatureVectorV1::zeroed();
        let r = proc.process_with_features(
            &intent_btc(0.7), &gov, &state, 500.0,
            GovernanceProfile::Exploration, Some(&features), Some("ctx-1"), 0,
        );
        assert!(!r.submitted);
        let reason = r.rejected_reason.expect("reason set");
        assert!(
            reason.starts_with("predictor_fallback_fail_closed:predict_no_model"),
            "expected fail-closed suffix, got {reason}"
        );
    }

    #[test]
    fn test_shadow_fill_emits_ipc_on_epsilon_greedy() {
        // exploration_rate=1.0 forces ε-greedy branch; verify EmitShadowFill arrives on channel.
        // exploration_rate=1.0 強制走 ε-greedy；驗證 EmitShadowFill 到達通道。
        let mut proc = IntentProcessor::new();
        proc.risk_config.edge_predictor.use_edge_predictor = true;
        proc.risk_config.edge_predictor.shadow_mode = false;
        proc.risk_config.edge_predictor.exploration_rate = 1.0;
        proc.set_pipeline_kind(PipelineKind::Paper);

        let store = Arc::new(EdgePredictorStore::new());
        store.swap(
            "test",
            Arc::new(StubOkPredictor {
                pred: Prediction { q10: -100.0, q50: -50.0, q90: -10.0 },
            }),
        );
        proc.set_edge_predictor_store(store);

        let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<PipelineCommand>();
        proc.set_shadow_fill_tx(tx);

        let gov = approved_governance();
        let state = paper_state_with_price(30_000.0);
        let features = FeatureVectorV1::zeroed();
        let r = proc.process_with_features(
            &intent_btc(0.7), &gov, &state, 500.0,
            GovernanceProfile::Exploration, Some(&features), Some("ctx-eps"),
            1_700_000_000_000,
        );
        assert!(!r.submitted);
        assert!(r
            .rejected_reason
            .unwrap()
            .contains("predictor_epsilon_greedy_exploration"));

        let cmd = rx.try_recv().expect("ShadowFill IPC must be emitted");
        match cmd {
            PipelineCommand::EmitShadowFill {
                context_id, strategy, symbol, prediction_q50, ts_ms, ..
            } => {
                assert_eq!(context_id, "ctx-eps");
                assert_eq!(strategy, "test");
                assert_eq!(symbol, "BTCUSDT");
                assert!((prediction_q50 - (-50.0)).abs() < 1e-6);
                assert_eq!(ts_ms, 1_700_000_000_000);
            }
            other => panic!("expected EmitShadowFill, got {:?}", other),
        }
    }

    #[test]
    fn test_non_paper_engine_never_emits_shadow_fill() {
        // Demo engine even at exploration_rate=1.0 must reject without emitting shadow fill.
        // Demo 引擎即使 exploration_rate=1.0 也必須拒絕且不發送 shadow fill。
        let mut proc = IntentProcessor::new();
        proc.risk_config.edge_predictor.use_edge_predictor = true;
        proc.risk_config.edge_predictor.shadow_mode = false;
        proc.risk_config.edge_predictor.exploration_rate = 1.0;
        proc.set_pipeline_kind(PipelineKind::Demo);

        let store = Arc::new(EdgePredictorStore::new());
        store.swap(
            "test",
            Arc::new(StubOkPredictor {
                pred: Prediction { q10: -100.0, q50: -50.0, q90: -10.0 },
            }),
        );
        proc.set_edge_predictor_store(store);

        let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<PipelineCommand>();
        proc.set_shadow_fill_tx(tx);

        let gov = approved_governance();
        let state = paper_state_with_price(30_000.0);
        let features = FeatureVectorV1::zeroed();
        let r = proc.process_with_features(
            &intent_btc(0.7), &gov, &state, 500.0,
            GovernanceProfile::Exploration, Some(&features), Some("ctx-demo"), 0,
        );
        assert!(!r.submitted);
        assert!(rx.try_recv().is_err(), "Demo engine must not emit shadow fills");
    }

    #[test]
    fn test_process_gates_only_with_features_accept_bypasses_legacy() {
        // Exchange path: Accept → approved, legacy JS shrinkage bypassed.
        // 交易所路徑：Accept → approved，跳過 JS shrinkage。
        let mut proc = IntentProcessor::new();
        proc.risk_config.edge_predictor.use_edge_predictor = true;
        proc.risk_config.edge_predictor.shadow_mode = false;
        let store = Arc::new(EdgePredictorStore::new());
        store.swap(
            "test",
            Arc::new(StubOkPredictor {
                pred: Prediction { q10: 100.0, q50: 200.0, q90: 300.0 },
            }),
        );
        proc.set_edge_predictor_store(store);
        let gov = approved_governance();
        let state = paper_state_with_price(30_000.0);
        let features = FeatureVectorV1::zeroed();
        let r = proc.process_gates_only_with_features(
            &intent_btc(0.7), &gov, &state, 500.0,
            GovernanceProfile::Production, Some(&features), Some("ctx-exch"), 0,
        );
        assert!(r.approved, "Accept must bypass strict live JS gate; got {:?}", r.rejected_reason);
    }
}
