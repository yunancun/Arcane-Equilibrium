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
    assert_eq!(
        ip.last_arm_selection().map(|s| s.arm_id.clone()),
        Some("trending__ma_crossover".to_string())
    );
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
        confluence_score: None,
        persistence_elapsed_ms: None,
        time_in_force: None,
        maker_timeout_ms: None,
    }
}

/// AMD-2026-05-02-01 Track E E-1 retrofit helper: seed an Active SM-02 lease on a
/// Production-profile GovernanceCore fixture. PA push back #4 requires Production
/// fixtures must NOT use LeaseId::Bypass short-circuit — the helper invokes the
/// real `acquire_lease()` facade and asserts `is_active()` so any future router-gate
/// bug surfaces in failures rather than being masked.
/// AMD-2026-05-02-01 Track E E-1 retrofit helper：在 Production profile 的
/// GovernanceCore fixture 上播下一個 Active SM-02 lease。PA push back #4 嚴格要求
/// Production fixture 禁用 LeaseId::Bypass 短路 — helper 呼真實 `acquire_lease()`
/// facade 並 assert `is_active()`，讓未來 router-gate bug 直接表面化而非被掩蓋。
///
/// Returned `LeaseId::Active(_)` is intentionally unused by current callers — once
/// E-2 wires the router gate, fixtures still pass because the lease is real.
/// 目前呼叫端故意不取用回傳的 `LeaseId::Active(_)` — E-2 接 router gate 後 fixture
/// 仍通過，因為 lease 是真實的。
#[allow(dead_code)] // E-2 wires consumers; helper itself fully exercised in fixtures below.
fn seed_production_lease(gov: &GovernanceCore, intent_id: &str) -> LeaseId {
    let lease = gov
        .acquire_lease(
            intent_id,
            "TRADE_ENTRY",
            30_000,
            GovernanceProfile::Production,
            "production_fixture",
        )
        .expect(
            "AMD-2026-05-02-01: Production fixture acquire_lease() must succeed; \
             check that gov has effective auth before this helper",
        );
    assert!(
        lease.is_active(),
        "AMD-2026-05-02-01 PA push back #4: Production fixture lease MUST be Active, \
         not Bypass — Bypass short-circuit masks router-gate bugs"
    );
    lease
}

#[test]
fn test_rejected_no_auth() {
    let proc = IntentProcessor::new();
    let gov = GovernanceCore::new(); // no auth
    let state = PaperState::new(10_000.0);
    let result = proc.process(
        &make_intent("BTC", true),
        &gov,
        &state,
        500.0,
        GovernanceProfile::Exploration,
    );
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
    // PH5-WIRE-0: ATR=2000 so EV=2000×0.7×0.006×0.2=$1.68 >> k×fee=1.5×$0.33=$0.50
    // (ATR raised from 500 to clear the 0.2 cold-start dampening factor)
    let result = proc.process(
        &make_intent("BTC", true),
        &gov,
        &state,
        2000.0,
        GovernanceProfile::Exploration,
    );
    assert!(result.submitted);
    assert!(result.fill.is_some());
}

#[test]
fn test_per_strategy_blocked_symbol_rejects_new_entry() {
    let mut proc = IntentProcessor::new();
    let mut cfg = RiskConfig::default();
    cfg.per_strategy.insert(
        "ma_crossover".into(),
        crate::config::risk_config::StrategyOverride {
            blocked_symbols: Some(vec!["NAORISUSDT".into()]),
            ..Default::default()
        },
    );
    proc.update_risk_config(cfg);
    let mut gov = GovernanceCore::new();
    gov.grant_paper_authorization(None).unwrap();
    let mut state = PaperState::new(10_000.0);
    state.set_latest_price("NAORISUSDT", 0.1);
    let mut intent = make_intent("NAORISUSDT", true);
    intent.strategy = "ma_crossover".into();

    let result = proc.process(&intent, &gov, &state, 0.01, GovernanceProfile::Exploration);
    assert!(!result.submitted);
    assert!(result
        .rejected_reason
        .unwrap_or_default()
        .contains("blocked_symbols"));
}

#[test]
fn test_per_strategy_blocked_symbol_allows_reducing_order() {
    let mut proc = IntentProcessor::new();
    let mut cfg = RiskConfig::default();
    cfg.per_strategy.insert(
        "ma_crossover".into(),
        crate::config::risk_config::StrategyOverride {
            blocked_symbols: Some(vec!["NAORISUSDT".into()]),
            ..Default::default()
        },
    );
    proc.update_risk_config(cfg);
    let mut gov = GovernanceCore::new();
    gov.grant_paper_authorization(None).unwrap();
    let mut state = PaperState::new(10_000.0);
    state.set_latest_price("NAORISUSDT", 0.1);
    state.import_positions(vec![("NAORISUSDT".into(), true, 100.0, 0.1, 0)]);
    let mut intent = make_intent("NAORISUSDT", false);
    intent.strategy = "ma_crossover".into();
    intent.qty = 100.0;

    let result = proc.process(&intent, &gov, &state, 0.01, GovernanceProfile::Exploration);
    assert!(
        result.submitted,
        "reducing order should bypass blocked_symbols, got {:?}",
        result.rejected_reason
    );
}

#[test]
fn test_position_sizing_caps_qty() {
    // P1 cap: 3% of 10,000 / 50,000 = 0.006 BTC
    // Intent qty 0.01 should be reduced to 0.006.
    // P1 上限：10,000 * 3% / 50,000 = 0.006 BTC；意圖 qty 0.01 縮小為 0.006。
    // PH5-WIRE-0: ATR=2000 so EV=2000×0.7×0.006×0.2=$1.68 >> k×fee=$0.50
    let proc = IntentProcessor::new();
    let mut gov = GovernanceCore::new();
    gov.grant_paper_authorization(None).unwrap();
    let mut state = PaperState::new(10_000.0);
    state.set_latest_price("BTC", 50_000.0);
    let intent = make_intent("BTC", true); // qty=0.01
    let result = proc.process(
        &intent,
        &gov,
        &state,
        2000.0,
        GovernanceProfile::Exploration,
    );
    assert!(result.submitted);
    let fill = result.fill.unwrap();
    // fill.fill_qty should be 0.006 (= 10000 * 0.03 / 50000), not 0.01
    assert!(
        (fill.fill_qty - 0.006).abs() < 1e-9,
        "Expected qty ~0.006 from P1 sizing, got {}",
        fill.fill_qty
    );
}

#[test]
fn test_governor_cautious_scales_new_entry_qty() {
    // RC-005: governor constraints must participate in admission.
    // Cautious multiplier=0.7 should scale post-P1 qty.
    // RC-005：governor 約束需進入准入路徑；Cautious 0.7 應縮放 P1 後 qty。
    let proc = IntentProcessor::new();
    let mut gov = GovernanceCore::new();
    gov.grant_paper_authorization(None).unwrap();
    gov.risk
        .escalate_to(
            openclaw_core::sm::risk_gov::RiskLevel::Cautious,
            "test",
            openclaw_core::sm::risk_gov::RiskEvent::DrawdownWarning,
        )
        .unwrap();
    let mut state = PaperState::new(10_000.0);
    state.set_latest_price("BTC", 50_000.0);

    let result = proc.process(
        &make_intent("BTC", true),
        &gov,
        &state,
        2000.0,
        GovernanceProfile::Exploration,
    );
    assert!(result.submitted);
    let fill = result.fill.unwrap();
    // Base P1 qty = 0.006, Cautious multiplier 0.7 => 0.0042.
    assert!(
        (fill.fill_qty - 0.0042).abs() < 1e-9,
        "expected governor-scaled qty 0.0042, got {}",
        fill.fill_qty
    );
}

#[test]
fn test_governor_reduced_blocks_new_entries() {
    // RC-005: Reduced tier is reduce-only; new entries must be rejected.
    // RC-005：Reduced 等級為 reduce-only；新開倉必須被拒絕。
    let proc = IntentProcessor::new();
    let mut gov = GovernanceCore::new();
    gov.grant_paper_authorization(None).unwrap();
    gov.risk
        .escalate_to(
            openclaw_core::sm::risk_gov::RiskLevel::Reduced,
            "test",
            openclaw_core::sm::risk_gov::RiskEvent::DrawdownWarning,
        )
        .unwrap();
    let mut state = PaperState::new(10_000.0);
    state.set_latest_price("BTC", 50_000.0);

    let result = proc.process(
        &make_intent("BTC", true),
        &gov,
        &state,
        2000.0,
        GovernanceProfile::Exploration,
    );
    assert!(!result.submitted);
    let reason = result.rejected_reason.unwrap_or_default();
    assert!(
        reason.contains("risk_governor"),
        "expected governor rejection, got: {reason}"
    );
}

#[test]
fn test_governor_reduced_caps_opposite_order_to_existing_qty() {
    // RC-005 follow-up: in reduce-only governor states, opposite-side intents
    // may reduce existing exposure but must never exceed it and flip position.
    let proc = IntentProcessor::new();
    let mut gov = GovernanceCore::new();
    gov.grant_paper_authorization(None).unwrap();
    gov.risk
        .escalate_to(
            openclaw_core::sm::risk_gov::RiskLevel::Reduced,
            "test",
            openclaw_core::sm::risk_gov::RiskEvent::DrawdownWarning,
        )
        .unwrap();
    let mut state = PaperState::new(10_000.0);
    state.set_latest_price("BTC", 50_000.0);
    state.import_positions(vec![("BTC".into(), true, 0.001, 50_000.0, 0)]);

    let mut intent = make_intent("BTC", false);
    intent.qty = 0.01;
    let result = proc.process(
        &intent,
        &gov,
        &state,
        2000.0,
        GovernanceProfile::Exploration,
    );

    assert!(
        result.submitted,
        "reducing order should stay admitted, got {:?}",
        result.rejected_reason
    );
    assert!(
        (result.approved_qty - 0.001).abs() < 1e-12,
        "approved_qty must cap to existing position, got {}",
        result.approved_qty
    );
    let fill = result.fill.expect("paper reducing fill expected");
    assert!(
        (fill.fill_qty - 0.001).abs() < 1e-12,
        "fill qty must cap to existing position, got {}",
        fill.fill_qty
    );
}

#[test]
fn test_governor_reduced_caps_exchange_opposite_order_to_existing_qty() {
    // Demo/live gates-only path must enforce the same cap before dispatch so
    // the later OrderDispatchRequest cannot flip via an over-sized opposite order.
    let proc = IntentProcessor::new();
    let mut gov = GovernanceCore::new();
    gov.grant_paper_authorization(None).unwrap();
    gov.risk
        .escalate_to(
            openclaw_core::sm::risk_gov::RiskLevel::Reduced,
            "test",
            openclaw_core::sm::risk_gov::RiskEvent::DrawdownWarning,
        )
        .unwrap();
    let mut state = PaperState::new(10_000.0);
    state.set_latest_price("BTC", 50_000.0);
    state.import_positions(vec![("BTC".into(), true, 0.001, 50_000.0, 0)]);

    let mut intent = make_intent("BTC", false);
    intent.qty = 0.01;
    let result = proc.process_gates_only(
        &intent,
        &gov,
        &state,
        2000.0,
        GovernanceProfile::Exploration,
    );

    assert!(
        result.approved,
        "reducing exchange order should stay admitted, got {:?}",
        result.rejected_reason
    );
    assert!(
        (result.approved_qty - 0.001).abs() < 1e-12,
        "exchange approved_qty must cap to existing position, got {}",
        result.approved_qty
    );
}

#[test]
fn test_position_sizing_tiny_balance() {
    // With tiny balance, P1 calc gives very small qty — no artificial floor.
    // 餘額極小時，P1 計算給出極小 qty — 無人為下限。
    // PH5-WIRE-0: need ATR=2000 to clear cost_gate with dampening 0.2 at tiny notional.
    // final_qty=0.00006, notional=$3 → k=3.0, fee=$0.0033, need EV=2000×0.7×0.00006×0.2=$0.0168>$0.0099
    let proc = IntentProcessor::new();
    let mut gov = GovernanceCore::new();
    gov.grant_paper_authorization(None).unwrap();
    let mut state = PaperState::new(100.0); // tiny balance
    state.set_latest_price("BTC", 50_000.0);
    let intent = make_intent("BTC", true); // qty=0.01
    let result = proc.process(
        &intent,
        &gov,
        &state,
        2000.0,
        GovernanceProfile::Exploration,
    );
    assert!(result.submitted);
    let fill = result.fill.unwrap();
    // P1 calc: 100 * 0.03 / 50000 = 0.00006 — used directly, no MIN_QTY floor.
    assert!(
        (fill.fill_qty - 0.00006).abs() < 1e-9,
        "Expected P1-sized qty 0.00006, got {}",
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
    // P1 cap: 1,000,000 * 0.03 / 3000 = 10.0; intent qty=0.01 is smaller
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
    let result = proc.process(
        &intent,
        &gov,
        &state,
        2000.0,
        GovernanceProfile::Exploration,
    );
    assert!(result.submitted, "intent must pass gates");
    // P1 cap at 3%: 10000 * 0.03 / 50000 = 0.006 BTC
    assert!(
        (result.approved_qty - 0.006).abs() < 1e-9,
        "approved_qty should be P1-capped (0.006), got {}",
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
    let result = proc.process(
        &make_intent("BTC", true),
        &gov,
        &state,
        500.0,
        GovernanceProfile::Exploration,
    );
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
    let result = proc.process(
        &make_intent("BTC", true),
        &gov,
        &state,
        500.0,
        GovernanceProfile::Exploration,
    );
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
        confluence_score: None,
        persistence_elapsed_ms: None,
        time_in_force: None,
        maker_timeout_ms: None,
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
        confluence_score: None,
        persistence_elapsed_ms: None,
        time_in_force: None,
        maker_timeout_ms: None,
    };
    // ATR=20 (very compressed for BTC) — previously rejected by ATR cold-start gate,
    // now allowed in paper exploration mode to accumulate data.
    let result = proc.process(&intent, &gov, &state, 20.0, GovernanceProfile::Exploration);
    assert!(
        result.submitted,
        "cold-start paper should allow through for data accumulation"
    );
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
        confluence_score: None,
        persistence_elapsed_ms: None,
        time_in_force: None,
        maker_timeout_ms: None,
    };
    // ATR=0 (indicator unavailable) — would have been waved through pre-SEC-11
    let result = proc.process(&intent, &gov, &state, 0.0, GovernanceProfile::Exploration);
    assert!(!result.submitted, "ATR=0 must fail-closed");
    assert!(result.rejected_reason.unwrap().contains("ATR unavailable"));

    // AMD-2026-05-02-01 Track E E-1: seed real Active lease before Production
    // gates_only call (PA push back #4). Lease must be Active not Bypass.
    // AMD-2026-05-02-01 Track E E-1：呼 Production gates_only 前播下真實 Active
    // lease（PA push back #4）。lease 必為 Active 非 Bypass。
    let lease = seed_production_lease(&gov, "intent-atr-zero");
    // Same on the exchange-mode path
    let gate = proc.process_gates_only(&intent, &gov, &state, 0.0, GovernanceProfile::Production);
    assert!(!gate.approved, "ATR=0 must fail-closed in gates_only too");
    assert!(gate.rejected_reason.unwrap().contains("ATR unavailable"));
    // Cancel the lease (intent never made it to fill).
    // 取消 lease（intent 未抵達 fill 階段）。
    gov.release_lease(&lease, LeaseOutcome::Cancelled).unwrap();
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
        confluence_score: None,
        persistence_elapsed_ms: None,
        time_in_force: None,
        maker_timeout_ms: None,
    };
    // AMD-2026-05-02-01 Track E E-1: seed real Active lease before Production
    // gates_only call (PA push back #4).
    // AMD-2026-05-02-01 Track E E-1：呼 Production gates_only 前播下真實 Active lease。
    let lease = seed_production_lease(&gov, "intent-low-ev");
    // ATR=20 compressed → EV << fee → reject
    let result =
        proc.process_gates_only(&intent, &gov, &state, 20.0, GovernanceProfile::Production);
    assert!(!result.approved);
    assert!(result.rejected_reason.unwrap().contains("cost_gate"));
    gov.release_lease(&lease, LeaseOutcome::Failed).unwrap();
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
        confluence_score: None,
        persistence_elapsed_ms: None,
        time_in_force: None,
        maker_timeout_ms: None,
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
        confluence_score: None,
        persistence_elapsed_ms: None,
        time_in_force: None,
        maker_timeout_ms: None,
    };
    let result = proc.process(&intent, &gov, &state, 0.1, GovernanceProfile::Exploration);
    assert!(
        result.submitted,
        "cold-start paper should allow low-volatility for data accumulation"
    );
}

#[test]
fn test_slippage_tier_lookup() {
    // Verify slippage tiers match Python cost_gate.py SLIPPAGE_TIERS.
    // 驗證滑點分級與 Python cost_gate.py 一致。
    // G7-07: now resolved via `SlippageConfig::default()` (TOML-backed) — values
    // unchanged so this regression guards default bit-identicality.
    // G7-07：經 SlippageConfig::default() 解析（TOML 支援），值不變，本測作為
    // default bit-identical 的回歸保險。
    assert_eq!(lookup_slippage_default(2_000_000_000.0), 0.0001); // >$1B: 1 bps
    assert_eq!(lookup_slippage_default(500_000_000.0), 0.0002); // >$100M: 2 bps
    assert_eq!(lookup_slippage_default(50_000_000.0), 0.0005); // >$10M: 5 bps
    assert_eq!(lookup_slippage_default(5_000_000.0), 0.0015); // >$1M: 15 bps
    assert_eq!(lookup_slippage_default(100_000.0), 0.0030); // <$1M: 30 bps
    assert_eq!(lookup_slippage_default(0.0), DEFAULT_SLIPPAGE_RATE);
    assert_eq!(lookup_slippage_default(-1.0), DEFAULT_SLIPPAGE_RATE);
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
        confluence_score: None,
        persistence_elapsed_ms: None,
        time_in_force: None,
        maker_timeout_ms: None,
    };
    let result = proc.process(&intent, &gov, &state, 500.0, GovernanceProfile::Exploration);
    assert!(
        !result.submitted,
        "Low win_rate should tighten JS gate threshold"
    );
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
        confluence_score: None,
        persistence_elapsed_ms: None,
        time_in_force: None,
        maker_timeout_ms: None,
    };
    // BTC $67k, ATR=300 → atr_pct = 0.4478%
    // cost_pct = (0.00055 + 0.0001) × 2 × 100 = 0.13% (with 1bps slip)
    // min_move = 0.13 / 0.5 × 1.3 = 0.338%
    // 0.4478% > 0.338% → passes
    let result = proc.process(&intent, &gov, &state, 300.0, GovernanceProfile::Exploration);
    assert!(
        result.submitted,
        "BTC with high volume should pass: {:?}",
        result.rejected_reason
    );
}

#[test]
fn test_pnl1_rejects_qty_zero_process() {
    // PNL-1: zero balance must reject. Gate 1.6 (insufficient_balance) fires
    // first on the paper path now — both it and the downstream qty_zero guard
    // represent the same outcome (no funds → no open). Either prefix passes.
    // PNL-1：零餘額必被拒。paper 路徑由 Gate 1.6（insufficient_balance）優先觸發；
    // 下游 qty_zero 守衛作為第二道保險，兩者語意等價（無資金 → 禁止開倉）。
    let proc = IntentProcessor::new();
    let mut gov = GovernanceCore::new();
    gov.grant_paper_authorization(None).unwrap();
    let mut state = PaperState::new(0.0); // zero balance
    state.set_latest_price("BTC", 50_000.0);
    let intent = make_intent("BTC", true);
    let result = proc.process(&intent, &gov, &state, 500.0, GovernanceProfile::Exploration);
    assert!(!result.submitted);
    let reason = result.rejected_reason.unwrap();
    assert!(
        reason.starts_with("insufficient_balance:") || reason.starts_with("qty_zero:"),
        "got: {}",
        reason,
    );
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
    // AMD-2026-05-02-01 Track E E-1: real Active lease before Production gates_only.
    // AMD-2026-05-02-01 Track E E-1：呼 Production gates_only 前真實 Active lease。
    let lease = seed_production_lease(&gov, "intent-qty-zero");
    let result =
        proc.process_gates_only(&intent, &gov, &state, 500.0, GovernanceProfile::Production);
    assert!(!result.approved);
    assert_eq!(result.approved_qty, 0.0);
    assert!(result.rejected_reason.unwrap().starts_with("qty_zero:"));
    gov.release_lease(&lease, LeaseOutcome::Failed).unwrap();
}

// ── 3E-2a: GovernanceProfile + cost_gate_moderate tests ──

#[test]
fn test_governance_core_new_with_profile_exploration_auto_grants() {
    let gov = GovernanceCore::new_with_profile(GovernanceProfile::Exploration);
    assert!(
        gov.is_authorized(),
        "Exploration profile should auto-grant auth"
    );
}

#[test]
fn test_governance_core_new_with_profile_validation_auto_grants() {
    let gov = GovernanceCore::new_with_profile(GovernanceProfile::Validation);
    assert!(
        gov.is_authorized(),
        "Validation profile should auto-grant auth"
    );
}

#[test]
fn test_governance_core_new_with_profile_production_fail_closed() {
    let gov = GovernanceCore::new_with_profile(GovernanceProfile::Production);
    assert!(
        !gov.is_authorized(),
        "Production profile should NOT auto-grant auth"
    );

    // AMD-2026-05-02-01 Track E E-1: acquire_lease() must AuthNotEffective when
    // Production has no auth — proves facade fail-closed contract (CLAUDE.md §4
    // hard boundary). NOT Bypass — Bypass is for Exploration / Validation only.
    // AMD-2026-05-02-01 Track E E-1：Production 無 auth 時 acquire_lease() 必回
    // AuthNotEffective — 證 facade fail-closed 契約（CLAUDE.md §四 硬邊界）。
    // 不是 Bypass — Bypass 僅用於 Exploration / Validation。
    let lease_attempt = gov.acquire_lease(
        "intent-production-no-auth",
        "TRADE_ENTRY",
        30_000,
        GovernanceProfile::Production,
        "production_fail_closed_test",
    );
    assert!(
        matches!(lease_attempt, Err(GovernanceError::AuthNotEffective)),
        "Production-without-auth must AuthNotEffective, got {:?}",
        lease_attempt
    );
}

#[test]
fn test_cost_gate_moderate_positive_edge_passes() {
    let mut proc = IntentProcessor::new();
    // Build estimates with a high positive edge (50 bps > any realistic threshold)
    let json = r#"{"ma_crossover::BTCUSDT": {"shrunk_bps": 50.0, "win_rate": 0.6, "n": 100, "std_bps": 5.0}}"#;
    let estimates = crate::edge_estimates::EdgeEstimates::load_from_str(json).unwrap();
    proc.set_edge_estimates(estimates);
    let result = proc.cost_gate_moderate("ma_crossover", "BTCUSDT", 0.00055, 1_000_000_000.0);
    assert!(result.is_none(), "positive edge should pass moderate gate");
}

#[test]
fn test_cost_gate_moderate_negative_edge_blocks() {
    let mut proc = IntentProcessor::new();
    let json = r#"{"ma_crossover::BTCUSDT": {"shrunk_bps": -5.0, "win_rate": 0.4, "n": 50, "std_bps": 2.0}}"#;
    let estimates = crate::edge_estimates::EdgeEstimates::load_from_str(json).unwrap();
    proc.set_edge_estimates(estimates);
    let result = proc.cost_gate_moderate("ma_crossover", "BTCUSDT", 0.00055, 1_000_000_000.0);
    assert!(
        result.is_some(),
        "negative edge should be blocked in moderate mode"
    );
    assert!(result.unwrap().rejected_reason.unwrap().contains("demo"));
}

#[test]
fn test_cost_gate_moderate_cold_start_allows() {
    let proc = IntentProcessor::new();
    // No edge estimates set = cold start
    let result = proc.cost_gate_moderate("ma_crossover", "BTCUSDT", 0.00055, 1_000_000_000.0);
    assert!(
        result.is_none(),
        "cold start should be allowed in moderate mode (data accumulation)"
    );
}

#[test]
fn test_fee_rate_staleness_rejects_cold_boot_account_manager() {
    let mut proc = IntentProcessor::new();
    let acct = std::sync::Arc::new(crate::account_manager::AccountManager::new());
    proc.set_account_manager(acct);

    let reason = proc
        .fee_rate_staleness_rejection(1_000)
        .expect("never-refreshed account manager must fail closed");

    assert!(reason.starts_with("cost_gate: fee rates unavailable"));
}

#[test]
fn test_fee_rate_staleness_rejects_after_two_hours() {
    let mut proc = IntentProcessor::new();
    let acct = std::sync::Arc::new(crate::account_manager::AccountManager::new());
    acct.set_last_fee_refresh_ms_for_test(1_000);
    proc.set_account_manager(acct);

    let now = 1_000 + MAX_FEE_RATE_STALENESS_MS + 1;
    let reason = proc
        .fee_rate_staleness_rejection(now)
        .expect("stale fee rates must fail closed");

    assert!(reason.contains("fee rates stale"));
}

#[test]
fn test_fee_rate_staleness_allows_demo_cached_defaults_after_two_hours() {
    let mut proc = IntentProcessor::new();
    proc.set_endpoint_env(crate::bybit_rest_client::BybitEnvironment::Demo);
    let acct = std::sync::Arc::new(crate::account_manager::AccountManager::new());
    acct.seed_default_fee_rates(["BTCUSDT", "ETHUSDT"]);
    acct.set_last_fee_refresh_ms_for_test(1_000);
    proc.set_account_manager(acct);

    let now = 1_000 + MAX_FEE_RATE_STALENESS_MS + 1;

    assert!(proc.fee_rate_staleness_rejection(now).is_none());
}

#[test]
fn test_fee_rate_staleness_mainnet_cached_rates_still_fail_closed() {
    let mut proc = IntentProcessor::new();
    proc.set_endpoint_env(crate::bybit_rest_client::BybitEnvironment::Mainnet);
    let acct = std::sync::Arc::new(crate::account_manager::AccountManager::new());
    acct.seed_default_fee_rates(["BTCUSDT", "ETHUSDT"]);
    acct.set_last_fee_refresh_ms_for_test(1_000);
    proc.set_account_manager(acct);

    let now = 1_000 + MAX_FEE_RATE_STALENESS_MS + 1;
    let reason = proc
        .fee_rate_staleness_rejection(now)
        .expect("mainnet stale cached rates must fail closed");

    assert!(reason.contains("fee rates stale"));
}

#[test]
fn test_fee_rate_staleness_allows_fresh_rates() {
    let mut proc = IntentProcessor::new();
    let acct = std::sync::Arc::new(crate::account_manager::AccountManager::new());
    acct.set_last_fee_refresh_ms_for_test(1_000);
    proc.set_account_manager(acct);

    let now = 1_000 + MAX_FEE_RATE_STALENESS_MS;

    assert!(proc.fee_rate_staleness_rejection(now).is_none());
}

// ── EDGE-DIAG-2 (2026-04-28) low-sample exploration branch ──
// EDGE-DIAG-2（2026-04-28）：低樣本探索分支

#[test]
fn test_cost_gate_moderate_low_sample_negative_routes_to_exploration() {
    // EDGE-DIAG-2: a negative shrunk_bps with n_trades < default 30 must NOT
    // block — it routes to exploration mode (allow + log) so demo can
    // accumulate fills toward statistically robust estimates.
    // EDGE-DIAG-2：低樣本（n<30）負 shrunk_bps 不阻擋，走探索模式。
    let mut proc = IntentProcessor::new();
    let json = r#"{"ma_crossover::BTCUSDT": {"shrunk_bps": -50.0, "win_rate": 0.3, "n": 6, "std_bps": 5.0}}"#;
    let estimates = crate::edge_estimates::EdgeEstimates::load_from_str(json).unwrap();
    proc.set_edge_estimates(estimates);
    let result = proc.cost_gate_moderate("ma_crossover", "BTCUSDT", 0.00055, 1_000_000_000.0);
    assert!(
        result.is_none(),
        "low-sample negative edge (n=6 < 30) should route to exploration, not block"
    );
}

#[test]
fn test_cost_gate_moderate_low_sample_positive_below_threshold_routes_to_exploration() {
    // EDGE-DIAG-2 symmetric behavior: positive shrunk_bps with low n that
    // would normally fail the win-rate-weighted threshold also gets routed
    // to exploration (estimate is noise; don't trust the magnitude either way).
    // EDGE-DIAG-2 對稱：低樣本正 shrunk_bps 即便未達門檻也走探索模式。
    let mut proc = IntentProcessor::new();
    // win_rate 0.4 + fee_bps ≈ 13 → threshold ≈ 13/0.4*1.3 ≈ 42 bps; shrunk 5 bps fails it.
    let json = r#"{"ma_crossover::BTCUSDT": {"shrunk_bps": 5.0, "win_rate": 0.4, "n": 10, "std_bps": 5.0}}"#;
    let estimates = crate::edge_estimates::EdgeEstimates::load_from_str(json).unwrap();
    proc.set_edge_estimates(estimates);
    let result = proc.cost_gate_moderate("ma_crossover", "BTCUSDT", 0.00055, 1_000_000_000.0);
    assert!(
        result.is_none(),
        "low-sample positive-below-threshold edge (n=10 < 30) should route to exploration, not block"
    );
}

#[test]
fn test_cost_gate_moderate_n_at_threshold_negative_still_blocks() {
    // EDGE-DIAG-2 boundary: n_trades exactly equal to default min_n (30) is
    // considered "robust enough" — keep blocking on negative shrunk_bps.
    // Boundary chosen as `cell.n_trades < min_n` (strict less than).
    // EDGE-DIAG-2 邊界：n_trades 恰等於 min_n 視為足夠穩健，仍阻擋負估計。
    let mut proc = IntentProcessor::new();
    let json = r#"{"ma_crossover::BTCUSDT": {"shrunk_bps": -10.0, "win_rate": 0.4, "n": 30, "std_bps": 3.0}}"#;
    let estimates = crate::edge_estimates::EdgeEstimates::load_from_str(json).unwrap();
    proc.set_edge_estimates(estimates);
    let result = proc.cost_gate_moderate("ma_crossover", "BTCUSDT", 0.00055, 1_000_000_000.0);
    assert!(
        result.is_some(),
        "n=30 negative edge should still block (>= min_n threshold)"
    );
}

#[test]
fn test_cost_gate_live_low_sample_negative_still_fails_closed() {
    // EDGE-DIAG-2 invariant: the "demo loose" loosening MUST NOT leak into
    // cost_gate_live. Live path stays strict regardless of n_trades — a
    // negative shrunk_bps (even n=3) fails closed (CLAUDE.md §四 / root #5).
    // EDGE-DIAG-2 不變量：demo 放寬不可滲透到 cost_gate_live。
    // Live 路徑無視 n_trades 嚴格 fail-closed（CLAUDE.md §四 / 根原則 #5）。
    let mut proc = IntentProcessor::new();
    let json = r#"{"ma_crossover::BTCUSDT": {"shrunk_bps": -5.0, "win_rate": 0.4, "n": 3, "std_bps": 2.0}}"#;
    let estimates = crate::edge_estimates::EdgeEstimates::load_from_str(json).unwrap();
    proc.set_edge_estimates(estimates);
    let result = proc.cost_gate_live("ma_crossover", "BTCUSDT", 0.00055, 1_000_000_000.0);
    assert!(
        result.is_some(),
        "live: low-sample negative must still fail-closed (no min_n exemption)"
    );
    assert!(result.unwrap().rejected_reason.unwrap().contains("live"));
}

#[test]
fn test_cost_gate_live_postonly_cost_excludes_taker_slippage() {
    let mut proc = IntentProcessor::new();
    let json = r#"{"grid_trading::BTCUSDT": {"shrunk_bps": 10.0, "win_rate": 1.0, "n": 100, "std_bps": 2.0}}"#;
    let estimates = crate::edge_estimates::EdgeEstimates::load_from_str(json).unwrap();
    proc.set_edge_estimates(estimates);

    let postonly_cost = proc.cost_gate_live_with_slippage(
        "grid_trading",
        "BTCUSDT",
        0.0002, // maker fee
        0.0,    // PostOnly maker path: no taker-style slippage tier
    );
    let taker_slippage_cost =
        proc.cost_gate_live_with_slippage("grid_trading", "BTCUSDT", 0.00055, 0.0030);

    assert!(
        postonly_cost.is_none(),
        "10 bps edge should pass maker-only cost"
    );
    assert!(
        taker_slippage_cost.is_some(),
        "same edge should fail when taker slippage is included"
    );
}

#[test]
fn test_cost_gate_moderate_high_sample_negative_still_blocks() {
    // EDGE-DIAG-2 regression guard for existing behavior: a robust negative
    // estimate (n >> 30) keeps blocking — operator's "demo loose" rule is
    // about ignoring noise, NOT ignoring real losses.
    // EDGE-DIAG-2：高樣本穩健負估計仍阻擋（"demo 放寬"是忽略噪音，不是忽略真虧損）。
    let mut proc = IntentProcessor::new();
    let json = r#"{"ma_crossover::BTCUSDT": {"shrunk_bps": -25.0, "win_rate": 0.35, "n": 200, "std_bps": 2.0}}"#;
    let estimates = crate::edge_estimates::EdgeEstimates::load_from_str(json).unwrap();
    proc.set_edge_estimates(estimates);
    let result = proc.cost_gate_moderate("ma_crossover", "BTCUSDT", 0.00055, 1_000_000_000.0);
    assert!(
        result.is_some(),
        "high-sample (n=200) negative edge should still block"
    );
    let reason = result.unwrap().rejected_reason.unwrap();
    assert!(
        reason.contains("demo") && reason.contains("blocked"),
        "expected demo-negative block reason, got: {}",
        reason
    );
}

#[test]
fn test_process_with_exploration_profile() {
    let proc = IntentProcessor::new();
    let gov = GovernanceCore::new_with_profile(GovernanceProfile::Exploration);
    let mut state = PaperState::new(10_000.0);
    state.set_latest_price("BTC", 50_000.0);
    let intent = make_intent("BTC", true);
    let result = proc.process(&intent, &gov, &state, 500.0, GovernanceProfile::Exploration);
    assert!(
        result.submitted,
        "Exploration profile should process successfully"
    );
}

#[test]
fn test_process_gates_with_production_no_auth_rejects() {
    let proc = IntentProcessor::new();
    let gov = GovernanceCore::new_with_profile(GovernanceProfile::Production);
    let mut state = PaperState::new(10_000.0);
    state.set_latest_price("BTC", 50_000.0);
    let intent = make_intent("BTC", true);

    // AMD-2026-05-02-01 Track E E-1: facade must AuthNotEffective when Production
    // no auth — confirms fail-closed contract before exercising router.
    // AMD-2026-05-02-01 Track E E-1：Production 無 auth 時 facade 必回
    // AuthNotEffective — 在進 router 前確認 fail-closed 契約。
    let lease_attempt = gov.acquire_lease(
        "intent-no-auth-router",
        "TRADE_ENTRY",
        30_000,
        GovernanceProfile::Production,
        "production_no_auth_test",
    );
    assert!(
        matches!(lease_attempt, Err(GovernanceError::AuthNotEffective)),
        "Production no auth must AuthNotEffective"
    );

    let result =
        proc.process_gates_only(&intent, &gov, &state, 500.0, GovernanceProfile::Production);
    assert!(!result.approved, "Production without auth should reject");
    assert!(result
        .rejected_reason
        .unwrap()
        .contains("governance_not_authorized"));
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
    assert!(
        reason.contains("10100.00"),
        "should show projected: {reason}"
    );
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
    let result = proc.process(
        &intent,
        &gov,
        &state,
        2000.0,
        GovernanceProfile::Exploration,
    );
    assert!(!result.submitted, "cap should block");
    assert!(result
        .rejected_reason
        .unwrap()
        .contains("global_notional_cap"));
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
    // AMD-2026-05-02-01 Track E E-1: Exploration core auto-granted paper auth →
    // is_authorized()=true → acquire_lease(Production) succeeds with real Active
    // lease (the auth content is paper but is_authorized() is content-agnostic).
    // The original test still depends on cap gate (not auth) to reject the
    // Production gates_only call below; lease seed proves facade works under
    // is_authorized()=true semantic.
    // AMD-2026-05-02-01 Track E E-1：Exploration core 自動授了 paper auth →
    // is_authorized()=true → acquire_lease(Production) 真實創 Active lease
    // （auth 內容是 paper 但 is_authorized() 不檢內容）。原測試仍靠 cap gate（非
    // auth）拒絕下方 Production gates_only 呼叫；lease seed 證 facade 在
    // is_authorized()=true 語意下工作。
    let lease_prod = gov
        .acquire_lease(
            "intent-d15-prod",
            "TRADE_ENTRY",
            30_000,
            GovernanceProfile::Production,
            "d15_exchange_path",
        )
        .expect("Exploration core auto-granted auth → Production acquire_lease must succeed");
    assert!(lease_prod.is_active());
    let _result =
        proc.process_gates_only(&intent, &gov, &state, 2000.0, GovernanceProfile::Production);
    // Cap gate already rejected; release as Failed.
    // cap gate 已拒絕；release 為 Failed。
    gov.release_lease(&lease_prod, LeaseOutcome::Failed)
        .unwrap();
    // Production needs auth, so it'll reject on governance first. Use Validation.
    // Validation profile → acquire_lease must short-circuit to Bypass.
    // Validation profile → acquire_lease 必短路為 Bypass。
    let lease_val = gov
        .acquire_lease(
            "intent-d15-val",
            "TRADE_ENTRY",
            30_000,
            GovernanceProfile::Validation,
            "d15_exchange_path",
        )
        .unwrap();
    assert_eq!(lease_val, LeaseId::Bypass);
    let result =
        proc.process_gates_only(&intent, &gov, &state, 2000.0, GovernanceProfile::Validation);
    assert!(!result.approved, "cap should block exchange path");
    assert!(result
        .rejected_reason
        .unwrap()
        .contains("global_notional_cap"));
    gov.release_lease(&lease_val, LeaseOutcome::Cancelled)
        .unwrap();
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
    let result = proc.process(
        &make_intent("BTC", true),
        &gov,
        &state,
        2000.0,
        GovernanceProfile::Exploration,
    );
    assert!(!result.submitted);
    assert!(result
        .rejected_reason
        .unwrap()
        .contains("duplicate_position"));
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
        confluence_score: None,
        persistence_elapsed_ms: None,
        time_in_force: None,
        maker_timeout_ms: None,
    };
    let result = proc.process(
        &intent,
        &gov,
        &state,
        2000.0,
        GovernanceProfile::Exploration,
    );
    // May be rejected by other gates (guardian drawdown, etc.), but NOT by duplicate check
    if let Some(reason) = &result.rejected_reason {
        assert!(
            !reason.contains("duplicate_position"),
            "opposite direction should not be rejected as duplicate, got: {reason}"
        );
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
    let result = proc.process(
        &intent,
        &gov,
        &state,
        -100.0,
        GovernanceProfile::Exploration,
    );
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
        confluence_score: None,
        persistence_elapsed_ms: None,
        time_in_force: None,
        maker_timeout_ms: None,
    };
    let result = proc.process_gates_only(&intent, &gov, &state, 5.0, GovernanceProfile::Validation);
    assert!(
        result.approved,
        "Validation profile should pass: {:?}",
        result.rejected_reason
    );
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
        confluence_score: None,
        persistence_elapsed_ms: None,
        time_in_force: None,
        maker_timeout_ms: None,
    };
    let result =
        proc.process_gates_only(&intent, &gov, &state, 50.0, GovernanceProfile::Validation);
    assert!(!result.approved);
    assert!(result
        .rejected_reason
        .unwrap()
        .contains("duplicate_position"));
}

/// P0-6 permanent fix: pre-Guardian rejection on paper path must carry a
/// synthetic Rejected `VerdictInfo` so `persist_verdict` writes the real reason
/// into `trading.risk_verdicts` (was `verdict_info: None` → silently skipped).
/// P0-6 永久修復：Paper 管線的前置 gate 拒絕必須帶 synthetic Rejected VerdictInfo，
/// 使 `persist_verdict` 能寫入真實拒絕理由（原本 None → 寫入被跳過）。
#[test]
fn test_p06_pre_guardian_reject_paper_carries_synthetic_verdict_info() {
    let proc = IntentProcessor::new();
    let gov = GovernanceCore::new(); // no auth → governance_not_authorized
    let state = PaperState::new(10_000.0);
    let result = proc.process(
        &make_intent("BTC", true),
        &gov,
        &state,
        500.0,
        GovernanceProfile::Exploration,
    );
    assert!(!result.submitted);
    let reason = result.rejected_reason.as_ref().expect("rejection reason");
    let vi = result
        .verdict_info
        .as_ref()
        .expect("P0-6: synthetic VerdictInfo must be present on pre-Guardian rejection");
    assert_eq!(vi.verdict, "Rejected");
    assert_eq!(vi.reasons.len(), 1);
    assert_eq!(&vi.reasons[0], reason);
    assert!(vi.modified_qty.is_none());
}

/// P0-6 permanent fix: same invariant on the exchange (gates-only) path.
/// P0-6 永久修復：Exchange 管線（gates-only）同樣必須帶 synthetic VerdictInfo。
#[test]
fn test_p06_pre_guardian_reject_exchange_carries_synthetic_verdict_info() {
    let proc = IntentProcessor::new();
    let gov = GovernanceCore::new_with_profile(GovernanceProfile::Validation);
    let mut state = PaperState::new(10_000.0);
    state.set_latest_price("ETH", 3000.0);
    state.import_positions(vec![("ETH".into(), false, 0.1, 3000.0, 0)]);
    let intent = OrderIntent {
        symbol: "ETH".into(),
        is_long: false,
        qty: 0.05,
        confidence: 0.7,
        strategy: "test".into(),
        order_type: "market".into(),
        limit_price: None,
        confluence_score: None,
        persistence_elapsed_ms: None,
        time_in_force: None,
        maker_timeout_ms: None,
    };
    let result =
        proc.process_gates_only(&intent, &gov, &state, 50.0, GovernanceProfile::Validation);
    assert!(!result.approved);
    let reason = result.rejected_reason.as_ref().expect("rejection reason");
    let vi = result
        .verdict_info
        .as_ref()
        .expect("P0-6: synthetic VerdictInfo must be present on pre-Guardian rejection");
    assert_eq!(vi.verdict, "Rejected");
    assert_eq!(vi.reasons.len(), 1);
    assert_eq!(&vi.reasons[0], reason);
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

// Larger nested modules are split out to keep this file under the LOC cap.
include!("tests_predictor_router.rs");
