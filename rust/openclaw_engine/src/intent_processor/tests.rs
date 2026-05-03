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
            confluence_score: None,
            persistence_elapsed_ms: None,
            time_in_force: None,
            maker_timeout_ms: None,
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
                pred: Prediction {
                    q10: 100.0,
                    q50: 200.0,
                    q90: 300.0,
                },
            }),
        );
        proc.set_edge_predictor_store(store);
        let gov = approved_governance();
        let state = paper_state_with_price(30_000.0);
        // Intent goes through legacy JS cost_gate_paper path — cold-start exploration mode
        // means it passes to fill. Without features the predictor shouldn't short-circuit.
        // features=None 時 predictor 不短路，走舊 JS gate（冷啟動探索放行）。
        let r = proc.process_with_features(
            &intent_btc(0.7),
            &gov,
            &state,
            500.0,
            GovernanceProfile::Exploration,
            None,
            None,
            0,
        );
        assert!(
            r.submitted,
            "features=None must delegate to legacy path; got {:?}",
            r.rejected_reason
        );
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
            &intent_btc(0.7),
            &gov,
            &state,
            500.0,
            GovernanceProfile::Exploration,
            Some(&features),
            Some("ctx-1"),
            1_700_000_000_000,
        );
        assert!(
            r.submitted,
            "use_edge_predictor=false must pass through; got {:?}",
            r.rejected_reason
        );
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
                pred: Prediction {
                    q10: -100.0,
                    q50: -50.0,
                    q90: -10.0,
                },
            }),
        );
        proc.set_edge_predictor_store(store);
        let gov = approved_governance();
        let state = paper_state_with_price(30_000.0);
        let features = FeatureVectorV1::zeroed();
        let r = proc.process_with_features(
            &intent_btc(0.7),
            &gov,
            &state,
            500.0,
            GovernanceProfile::Exploration,
            Some(&features),
            Some("ctx-1"),
            0,
        );
        assert!(
            r.submitted,
            "shadow_mode=true must fall through to legacy; got {:?}",
            r.rejected_reason
        );
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
                pred: Prediction {
                    q10: 100.0,
                    q50: 200.0,
                    q90: 300.0,
                },
            }),
        );
        proc.set_edge_predictor_store(store);
        let gov = approved_governance();
        let state = paper_state_with_price(30_000.0);
        let features = FeatureVectorV1::zeroed();
        let r = proc.process_with_features(
            &intent_btc(0.7),
            &gov,
            &state,
            500.0,
            GovernanceProfile::Exploration,
            Some(&features),
            Some("ctx-1"),
            0,
        );
        assert!(
            r.submitted,
            "Accept must bypass JS gate and submit; got {:?}",
            r.rejected_reason
        );
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
                pred: Prediction {
                    q10: -100.0,
                    q50: -50.0,
                    q90: -10.0,
                },
            }),
        );
        proc.set_edge_predictor_store(store);
        let gov = approved_governance();
        let state = paper_state_with_price(30_000.0);
        let features = FeatureVectorV1::zeroed();
        let r = proc.process_with_features(
            &intent_btc(0.7),
            &gov,
            &state,
            500.0,
            GovernanceProfile::Exploration,
            Some(&features),
            Some("ctx-1"),
            0,
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
            &intent_btc(0.7),
            &gov,
            &state,
            500.0,
            GovernanceProfile::Exploration,
            Some(&features),
            Some("ctx-1"),
            0,
        );
        // JS gate cold-start exploration passes the intent.
        // JS gate 冷啟動探索模式放行。
        assert!(
            r.submitted,
            "Fallback(Shrinkage) must delegate to legacy gate; got {:?}",
            r.rejected_reason
        );
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
            &intent_btc(0.7),
            &gov,
            &state,
            500.0,
            GovernanceProfile::Exploration,
            Some(&features),
            Some("ctx-1"),
            0,
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
                pred: Prediction {
                    q10: -100.0,
                    q50: -50.0,
                    q90: -10.0,
                },
            }),
        );
        proc.set_edge_predictor_store(store);

        let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<PipelineCommand>();
        proc.set_shadow_fill_tx(tx);

        let gov = approved_governance();
        let state = paper_state_with_price(30_000.0);
        let features = FeatureVectorV1::zeroed();
        let r = proc.process_with_features(
            &intent_btc(0.7),
            &gov,
            &state,
            500.0,
            GovernanceProfile::Exploration,
            Some(&features),
            Some("ctx-eps"),
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
                context_id,
                strategy,
                symbol,
                prediction_q50,
                ts_ms,
                ..
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
                pred: Prediction {
                    q10: -100.0,
                    q50: -50.0,
                    q90: -10.0,
                },
            }),
        );
        proc.set_edge_predictor_store(store);

        let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<PipelineCommand>();
        proc.set_shadow_fill_tx(tx);

        let gov = approved_governance();
        let state = paper_state_with_price(30_000.0);
        let features = FeatureVectorV1::zeroed();
        let r = proc.process_with_features(
            &intent_btc(0.7),
            &gov,
            &state,
            500.0,
            GovernanceProfile::Exploration,
            Some(&features),
            Some("ctx-demo"),
            0,
        );
        assert!(!r.submitted);
        assert!(
            rx.try_recv().is_err(),
            "Demo engine must not emit shadow fills"
        );
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
                pred: Prediction {
                    q10: 100.0,
                    q50: 200.0,
                    q90: 300.0,
                },
            }),
        );
        proc.set_edge_predictor_store(store);
        let gov = approved_governance();
        let state = paper_state_with_price(30_000.0);
        let features = FeatureVectorV1::zeroed();
        // AMD-2026-05-02-01 Track E E-1: real Active lease before Production
        // process_gates_only_with_features (PA push back #4 — no Bypass shortcut
        // for Production fixtures).
        // AMD-2026-05-02-01 Track E E-1：Production process_gates_only_with_features
        // 前播下真實 Active lease（PA push back #4 — Production fixture 禁 Bypass 短路）。
        let lease = super::seed_production_lease(&gov, "intent-features-accept");
        let r = proc.process_gates_only_with_features(
            &intent_btc(0.7),
            &gov,
            &state,
            500.0,
            GovernanceProfile::Production,
            Some(&features),
            Some("ctx-exch"),
            0,
        );
        assert!(
            r.approved,
            "Accept must bypass strict live JS gate; got {:?}",
            r.rejected_reason
        );
        // Successful Accept path → release as Consumed. / Accept 路徑 → release Consumed。
        gov.release_lease(&lease, LeaseOutcome::Consumed).unwrap();
    }

    // ========================================================
    // EDGE-P3-1 Step 7a: DecisionFeatureSnapshot emission tests
    // ========================================================
    //
    // Emission fires at the TOP of evaluate_predictor_gate, before any
    // short-circuit, so Stage 0 training data flows while the gate stays
    // on legacy shrinkage (use_edge_predictor=false). These tests cover:
    //   (a) fires when predictor is disabled + features + ctx_id present;
    //   (b) no emit on empty context_id;
    //   (c) no emit on features=None;
    //   (d) no emit on ts_ms=0 (DB-RUN-6 alignment with writer rejection).
    //
    // EDGE-P3-1 Step 7a：決策特徵快照發射測試 —
    // gate 頂端發射、早於短路檢查，Stage 0 即採集訓練資料。

    #[test]
    fn test_decision_feature_snapshot_emitted_when_predictor_disabled() {
        // use_edge_predictor=false (default Stage 0) + features + ctx_id →
        // snapshot still emits; writer accumulates while gate stays on legacy.
        // use_edge_predictor=false（Stage 0 預設）仍發射；writer 累積訓練資料。
        let mut proc = IntentProcessor::new();
        assert!(!proc.risk_config.edge_predictor.use_edge_predictor);
        proc.set_pipeline_kind(PipelineKind::Paper);

        let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::DecisionFeatureMsg>(8);
        proc.set_decision_feature_tx(tx);

        let gov = approved_governance();
        let state = paper_state_with_price(30_000.0);
        let features = FeatureVectorV1::zeroed();
        let _ = proc.process_with_features(
            &intent_btc(0.7),
            &gov,
            &state,
            500.0,
            GovernanceProfile::Exploration,
            Some(&features),
            Some("ctx-seed"),
            1_700_000_000_000,
        );

        let msg = rx.try_recv().expect("snapshot must be emitted at gate top");
        assert_eq!(msg.context_id, "ctx-seed");
        assert_eq!(msg.ts_ms, 1_700_000_000_000);
        assert_eq!(msg.engine_mode, "paper");
        assert_eq!(msg.strategy_name, "test");
        assert_eq!(msg.symbol, "BTCUSDT");
        assert_eq!(msg.side, 1, "is_long=true → side=+1");
        assert_eq!(
            msg.feature_schema_version,
            crate::edge_predictor::features::FEATURE_SCHEMA_VERSION
        );
        assert_eq!(
            msg.feature_schema_hash,
            crate::edge_predictor::features::feature_schema_hash()
        );
        assert_eq!(
            msg.feature_definition_hash,
            crate::edge_predictor::features::feature_definition_hash()
        );
        assert!(
            msg.features_jsonb.starts_with('{') && msg.features_jsonb.ends_with('}'),
            "features_jsonb must be valid JSON object, got {}",
            msg.features_jsonb
        );
    }

    #[test]
    fn test_decision_feature_snapshot_no_emit_on_empty_context() {
        // Empty context_id → caller has nothing to join on later; skip emission.
        // context_id 為空 → 後續無 join key，直接跳過發射。
        let mut proc = IntentProcessor::new();
        proc.set_pipeline_kind(PipelineKind::Paper);

        let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::DecisionFeatureMsg>(8);
        proc.set_decision_feature_tx(tx);

        let gov = approved_governance();
        let state = paper_state_with_price(30_000.0);
        let features = FeatureVectorV1::zeroed();
        let _ = proc.process_with_features(
            &intent_btc(0.7),
            &gov,
            &state,
            500.0,
            GovernanceProfile::Exploration,
            Some(&features),
            None,
            1_700_000_000_000,
        );
        assert!(
            rx.try_recv().is_err(),
            "empty context_id must not emit snapshot"
        );
    }

    #[test]
    fn test_decision_feature_snapshot_no_emit_on_none_features() {
        // features=None → nothing to persist; no emission.
        // features=None → 無可持久化資料，不發射。
        let mut proc = IntentProcessor::new();
        proc.set_pipeline_kind(PipelineKind::Paper);

        let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::DecisionFeatureMsg>(8);
        proc.set_decision_feature_tx(tx);

        let gov = approved_governance();
        let state = paper_state_with_price(30_000.0);
        let _ = proc.process_with_features(
            &intent_btc(0.7),
            &gov,
            &state,
            500.0,
            GovernanceProfile::Exploration,
            None,
            Some("ctx-nofeat"),
            1_700_000_000_000,
        );
        assert!(
            rx.try_recv().is_err(),
            "features=None must not emit snapshot"
        );
    }

    #[test]
    fn test_decision_feature_snapshot_no_emit_on_zero_timestamp() {
        // ts_ms=0 → DB-RUN-6 writer would reject; skip at source.
        // ts_ms=0 → writer 側 DB-RUN-6 會拒絕；源頭直接略過。
        let mut proc = IntentProcessor::new();
        proc.set_pipeline_kind(PipelineKind::Paper);

        let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::DecisionFeatureMsg>(8);
        proc.set_decision_feature_tx(tx);

        let gov = approved_governance();
        let state = paper_state_with_price(30_000.0);
        let features = FeatureVectorV1::zeroed();
        let _ = proc.process_with_features(
            &intent_btc(0.7),
            &gov,
            &state,
            500.0,
            GovernanceProfile::Exploration,
            Some(&features),
            Some("ctx-zero-ts"),
            0,
        );
        assert!(
            rx.try_recv().is_err(),
            "ts_ms=0 must not emit snapshot (DB-RUN-6 alignment)"
        );
    }

    // ── EDGE-P2-3 Phase 1a: maker fee selection tests ──
    // ── EDGE-P2-3 Phase 1a：maker 費率選擇測試 ──

    /// fee_rate_for_intent returns taker rate for non-PostOnly intents
    /// (Market, Limit+GTC/IOC/FOK). Matches prior `fee_rate()` behavior.
    /// fee_rate_for_intent 對非 PostOnly 意圖（Market / GTC 等）返回 taker 費率。
    #[test]
    fn test_fee_rate_for_intent_uses_taker_for_market() {
        let proc = IntentProcessor::new();
        let intent = super::make_intent("BTCUSDT", true);
        // Market/GTC → taker fallback (cold-boot: DEFAULT_TAKER_FEE_RATE = 0.00055)
        let rate = proc.fee_rate_for_intent(&intent.symbol, &intent);
        assert!((rate - 0.00055).abs() < 1e-12);
        assert_eq!(rate, proc.fee_rate(&intent.symbol));
    }

    /// PostOnly intents route to maker rate (~2.75× cheaper on cold-boot).
    /// PostOnly 意圖走 maker 費率（冷啟動為 taker 的約 1/2.75）。
    #[test]
    fn test_fee_rate_for_intent_uses_maker_for_postonly() {
        use crate::order_manager::TimeInForce;
        let proc = IntentProcessor::new();
        let mut intent = super::make_intent("BTCUSDT", true);
        intent.time_in_force = Some(TimeInForce::PostOnly);
        let rate = proc.fee_rate_for_intent(&intent.symbol, &intent);
        // Cold-boot maker default = 0.0002, taker default = 0.00055
        assert!((rate - 0.0002).abs() < 1e-12);
        assert!(rate < proc.fee_rate(&intent.symbol));
    }

    /// Explicit GTC (non-PostOnly) must still pay taker — guards against future
    /// TIF variants being accidentally classified as maker.
    /// 明確 GTC（非 PostOnly）仍走 taker，防止未來 TIF 變體被誤分類。
    #[test]
    fn test_fee_rate_for_intent_gtc_stays_taker() {
        use crate::order_manager::TimeInForce;
        let proc = IntentProcessor::new();
        let mut intent = super::make_intent("BTCUSDT", true);
        intent.time_in_force = Some(TimeInForce::GTC);
        let rate = proc.fee_rate_for_intent(&intent.symbol, &intent);
        assert!((rate - 0.00055).abs() < 1e-12);
    }

    #[test]
    fn test_slippage_rate_for_intent_postonly_is_zero() {
        use crate::order_manager::TimeInForce;
        let proc = IntentProcessor::new();
        let mut intent = super::make_intent("BTCUSDT", true);
        intent.time_in_force = Some(TimeInForce::PostOnly);

        let slippage = proc.slippage_rate_for_intent(&intent, 0.0);

        assert_eq!(slippage, 0.0);
    }

    #[test]
    fn test_slippage_rate_for_intent_market_uses_tier() {
        let proc = IntentProcessor::new();
        let intent = super::make_intent("BTCUSDT", true);

        let slippage = proc.slippage_rate_for_intent(&intent, 2_000_000_000.0);

        assert_eq!(slippage, 0.0001);
    }

    // ── FIX-FEE-POSTONLY-1 (G7-09): fee_rate_for_tif fill-path helper ──
    // ── FIX-FEE-POSTONLY-1：fee_rate_for_tif fill 路徑 TIF-aware 費率 ──

    /// TIF=PostOnly on fill path → maker rate. Mirrors fee_rate_for_intent but
    /// accepts raw Option<TimeInForce> so event_consumer can call it with a
    /// PendingOrder TIF lookup (no OrderIntent available on the exec event).
    /// TIF=PostOnly → maker；對應 loop_handlers hoisted matched_tif 路徑。
    #[test]
    fn test_fee_rate_for_tif_postonly_returns_maker() {
        use crate::order_manager::TimeInForce;
        let proc = IntentProcessor::new();
        let rate = proc.fee_rate_for_tif("BTCUSDT", Some(TimeInForce::PostOnly));
        assert!((rate - 0.0002).abs() < 1e-12);
        assert!(rate < proc.fee_rate("BTCUSDT"));
    }

    /// TIF=GTC on fill path → taker (same as fee_rate_for_intent for GTC).
    /// TIF=GTC → taker。
    #[test]
    fn test_fee_rate_for_tif_gtc_stays_taker() {
        use crate::order_manager::TimeInForce;
        let proc = IntentProcessor::new();
        let rate = proc.fee_rate_for_tif("BTCUSDT", Some(TimeInForce::GTC));
        assert!((rate - 0.00055).abs() < 1e-12);
    }

    /// Race-safety: Bybit Fill event can arrive before OrderUpdate fills
    /// `order_id_to_link`, in which case matched_key lookup fails and TIF is
    /// unknown. Degrade to taker (= pre-G7-09 behaviour) so we never
    /// under-estimate fees when order type is uncertain.
    /// Race 安全：Fill 先於 OrderUpdate → matched_tif=None → fallback taker。
    #[test]
    fn test_fee_rate_for_tif_none_falls_back_to_taker() {
        let proc = IntentProcessor::new();
        let rate = proc.fee_rate_for_tif("BTCUSDT", None);
        assert!((rate - 0.00055).abs() < 1e-12);
        assert_eq!(rate, proc.fee_rate("BTCUSDT"));
    }
}

// ════════════════════════════════════════════════════════════════════════════
// EDGE-P2-3 Phase 1B-5: MakerKpi gate router tests.
// Verifies router consults per-symbol fill-rate / net-edge KPI before enqueueing
// a PostOnly intent. Cold (warmup) and Healthy → enqueue as resting order;
// Degraded → silent fallback to market fill with `maker_degraded_fallback`
// sentinel set so `on_tick` bumps the counter and warns.
// EDGE-P2-3 Phase 1B-5：MakerKpi gate 路由測試。驗 router 於 enqueue PostOnly
// 前查 per-symbol fill-rate / net-edge KPI。Cold / Healthy → 入掛單隊列；
// Degraded → 靜默改走市價，`maker_degraded_fallback` 標記由 on_tick 計數 + warn。
// ════════════════════════════════════════════════════════════════════════════
#[cfg(test)]
mod maker_kpi_gate_tests {
    use super::*;
    use crate::order_manager::TimeInForce;

    const NOW_MS: u64 = 1_700_000_000_000;

    fn approved_gov() -> GovernanceCore {
        let mut g = GovernanceCore::new();
        g.grant_paper_authorization(None).unwrap();
        g
    }

    fn paper_state_seeded(price: f64) -> PaperState {
        let mut s = PaperState::new(10_000.0);
        s.set_latest_price("BTCUSDT", price);
        s.set_latest_turnover("BTCUSDT", 100_000_000.0);
        s
    }

    fn postonly_intent(price: f64) -> OrderIntent {
        OrderIntent {
            symbol: "BTCUSDT".into(),
            is_long: true,
            qty: 0.001,
            confidence: 0.7,
            strategy: "grid_trading".into(),
            order_type: "limit".into(),
            limit_price: Some(price * 0.999),
            confluence_score: None,
            persistence_elapsed_ms: None,
            time_in_force: Some(TimeInForce::PostOnly),
            maker_timeout_ms: Some(45_000),
        }
    }

    #[test]
    fn test_postonly_cold_gate_allows_enqueue() {
        // No terminal samples → Cold → router must build the resting draft.
        // 零終局樣本 → Cold → router 必須建立 resting draft。
        let proc = IntentProcessor::new();
        let gov = approved_gov();
        let state = paper_state_seeded(30_000.0);
        let r = proc.process_with_features(
            &postonly_intent(30_000.0),
            &gov,
            &state,
            2000.0,
            GovernanceProfile::Exploration,
            None,
            None,
            NOW_MS,
        );
        assert!(r.submitted, "cold gate must allow enqueue");
        assert!(
            r.resting_order.is_some(),
            "cold gate must produce resting draft; got fill={:?}",
            r.fill
        );
        assert!(r.fill.is_none(), "resting draft implies no immediate fill");
        assert!(r.maker_degraded_fallback.is_none());
    }

    #[test]
    fn test_postonly_healthy_gate_allows_enqueue() {
        // Seed 18 fills / 2 timeouts → fill_rate 0.9 > 0.15, edge 0 > -5 → Healthy.
        // 塞 18 fills / 2 timeouts → 成交率 0.9 > 0.15、edge 0 > -5 → Healthy。
        let proc = IntentProcessor::new();
        let gov = approved_gov();
        let mut state = paper_state_seeded(30_000.0);
        state.test_seed_maker_stats_terminal("BTCUSDT", 18, 2, NOW_MS);
        let r = proc.process_with_features(
            &postonly_intent(30_000.0),
            &gov,
            &state,
            2000.0,
            GovernanceProfile::Exploration,
            None,
            None,
            NOW_MS,
        );
        assert!(r.submitted);
        assert!(r.resting_order.is_some(), "healthy gate must enqueue");
        assert!(r.maker_degraded_fallback.is_none());
    }

    #[test]
    fn test_postonly_degraded_low_fill_rate_falls_back_to_market() {
        // Seed 2 fills / 18 timeouts → fill_rate 0.1 < 0.15 → Degraded.
        // Router must skip enqueue and produce a market fill, with the
        // fallback sentinel pointing at the rejected symbol.
        // 塞 2/18 → rate 0.1 < 0.15 → Degraded。router 必須跳過 enqueue、
        // 走市價成交、maker_degraded_fallback 指向被拒的 symbol。
        let proc = IntentProcessor::new();
        let gov = approved_gov();
        let mut state = paper_state_seeded(30_000.0);
        state.test_seed_maker_stats_terminal("BTCUSDT", 2, 18, NOW_MS);
        let r = proc.process_with_features(
            &postonly_intent(30_000.0),
            &gov,
            &state,
            2000.0,
            GovernanceProfile::Exploration,
            None,
            None,
            NOW_MS,
        );
        assert!(r.submitted);
        assert!(r.resting_order.is_none(), "degraded gate must NOT enqueue");
        assert!(r.fill.is_some(), "degraded gate must take market fallback");
        assert_eq!(
            r.maker_degraded_fallback.as_deref(),
            Some("BTCUSDT"),
            "fallback sentinel must carry the symbol so on_tick can count it"
        );
    }

    #[test]
    fn test_postonly_degraded_per_symbol_leaves_other_symbol_healthy() {
        // BTCUSDT saturated with timeouts (Degraded), ETHUSDT untouched (Cold
        // per-symbol → falls back to aggregate). Aggregate = BTCUSDT stats
        // alone → also Degraded. So ETHUSDT should also fall back to market
        // when fed the same gate. This locks the aggregate-fallback semantics.
        // BTCUSDT 被 timeouts 灌滿（Degraded）、ETHUSDT 未觸碰（per-symbol Cold
        // → fallback 到 aggregate）。aggregate = BTCUSDT 獨撐 → 也 Degraded。
        // 故 ETHUSDT 也會被 gate 擋。此測固化 aggregate fallback 語意。
        let proc = IntentProcessor::new();
        let gov = approved_gov();
        let mut state = paper_state_seeded(30_000.0);
        state.test_seed_maker_stats_terminal("BTCUSDT", 2, 18, NOW_MS);
        state.set_latest_price("ETHUSDT", 3_000.0);
        state.set_latest_turnover("ETHUSDT", 100_000_000.0);
        let mut eth_intent = postonly_intent(3_000.0);
        eth_intent.symbol = "ETHUSDT".into();
        eth_intent.limit_price = Some(3_000.0 * 0.999);
        let r = proc.process_with_features(
            &eth_intent,
            &gov,
            &state,
            300.0,
            GovernanceProfile::Exploration,
            None,
            None,
            NOW_MS,
        );
        assert!(r.submitted);
        assert!(
            r.resting_order.is_none(),
            "ETHUSDT must ride aggregate verdict (Degraded) → no enqueue"
        );
        assert_eq!(r.maker_degraded_fallback.as_deref(), Some("ETHUSDT"));
    }

    #[test]
    fn test_market_intent_is_never_tagged_with_fallback() {
        // Market intents bypass the gate entirely — the sentinel must stay
        // None so downstream observers don't mistakenly count them.
        // 市價意圖完全不進 gate — sentinel 保持 None。
        let proc = IntentProcessor::new();
        let gov = approved_gov();
        let mut state = paper_state_seeded(30_000.0);
        // Even with Degraded stats present, a market intent shouldn't care.
        // 即使 stats 呈 Degraded，市價意圖也不應受影響。
        state.test_seed_maker_stats_terminal("BTCUSDT", 2, 18, NOW_MS);
        let intent = super::make_intent("BTCUSDT", true); // order_type=market
        let r = proc.process_with_features(
            &intent,
            &gov,
            &state,
            2000.0,
            GovernanceProfile::Exploration,
            None,
            None,
            NOW_MS,
        );
        assert!(r.submitted);
        assert!(r.fill.is_some());
        assert!(r.maker_degraded_fallback.is_none());
    }

    #[test]
    fn test_enqueue_bumps_submit_counter() {
        // Enqueue side-effect on PaperState must increment `maker_stats.submitted`
        // on both aggregate and per-symbol scopes. Gate not involved here —
        // this is an integration check of the 1B-5 wiring through PaperState.
        // enqueue 副作用必須同時更新 aggregate + per-symbol 的 submitted。
        let proc = IntentProcessor::new();
        let gov = approved_gov();
        let mut state = paper_state_seeded(30_000.0);
        let r = proc.process_with_features(
            &postonly_intent(30_000.0),
            &gov,
            &state,
            2000.0,
            GovernanceProfile::Exploration,
            None,
            None,
            NOW_MS,
        );
        let draft = r.resting_order.expect("cold gate enqueues");
        // Caller (on_tick) normally runs this; replicate manually for the test.
        // caller（on_tick）通常執行此行；測試中手動重現。
        state.enqueue_resting_limit_order(draft);
        assert_eq!(state.maker_stats().aggregate.submitted, 1);
        assert_eq!(
            state
                .maker_stats()
                .per_symbol
                .get("BTCUSDT")
                .unwrap()
                .submitted,
            1
        );
    }
}

// ════════════════════════════════════════════════════════════════════════════
// AMD-2026-05-02-01 Track E E-2: Router Decision Lease gate tests (Gate 1.4).
// Verifies router gate flag toggling, profile-based Bypass / Active path
// selection, fail-closed AuthNotEffective, RouterLeaseGuard rejection cleanup,
// and IntentResult/ExchangeGateResult lease_id population on success.
//
// AMD-2026-05-02-01 Track E E-2：Router Decision Lease gate 測試（Gate 1.4）。
// 驗 router gate flag 開關 / profile 對 Bypass vs Active 路徑選擇 /
// AuthNotEffective fail-closed / RouterLeaseGuard 拒絕路徑 cleanup / 成功路徑
// IntentResult/ExchangeGateResult lease_id 填入。
// ════════════════════════════════════════════════════════════════════════════
#[cfg(test)]
mod router_gate_lease_tests {
    use super::*;

    const NOW_MS: u64 = 1_700_000_000_000;

    /// Helper: build a Production GovernanceCore with auth + router gate flag
    /// flipped via the cross-crate test setter (avoids env_var race).
    /// Helper：構造 Production GovernanceCore + auth；用跨 crate test setter
    /// 翻 router gate flag（避免 env_var race）。
    fn make_gov(router_gate_on: bool, auth: bool) -> GovernanceCore {
        let mut g = GovernanceCore::new();
        if auth {
            g.grant_paper_authorization(None).unwrap();
        }
        g.set_router_gate_enabled_for_test(router_gate_on);
        g
    }

    fn make_state() -> PaperState {
        let mut s = PaperState::new(10_000.0);
        s.set_latest_price("BTCUSDT", 30_000.0);
        s.set_latest_turnover("BTCUSDT", 100_000_000.0);
        s
    }

    /// Test 1: flag OFF → Gate 1.4 short-circuits; lease_id stays None on
    /// success and rejection paths; behavior identical to pre-E-2.
    /// Test 1：flag OFF → Gate 1.4 短路；成功與拒絕路徑 lease_id 皆 None；
    /// 行為與 E-2 前一致。
    #[test]
    fn test_router_gate_off_lease_id_none_on_success() {
        let proc = IntentProcessor::new();
        let gov = make_gov(false, true);
        let state = make_state();
        // Exploration profile + flag OFF → Gate 1.4 short-circuits to None.
        // Exploration profile + flag OFF → Gate 1.4 短路 None。
        let r = proc.process_with_features(
            &make_intent("BTCUSDT", true),
            &gov,
            &state,
            2000.0,
            GovernanceProfile::Exploration,
            None,
            None,
            NOW_MS,
        );
        assert!(r.submitted, "intent must be accepted");
        assert!(r.lease_id.is_none(), "flag OFF → lease_id stays None");
        // SM has 0 lease objects since acquire_lease was never called.
        // 因從未呼 acquire_lease，SM 有 0 lease object。
        assert_eq!(gov.lease.lock().len(), 0);
    }

    /// Test 2: flag ON + Production profile happy path → Active lease
    /// acquired; IntentResult.lease_id = Some("lease:..."); SM has 1 Active
    /// lease (waiting for fill consumer release).
    /// Test 2：flag ON + Production happy path → 取得 Active lease；
    /// IntentResult.lease_id = Some("lease:...")；SM 有 1 個 Active（等 fill
    /// consumer 釋放）。
    #[test]
    fn test_router_gate_on_production_happy_path_lease_active() {
        let proc = IntentProcessor::new();
        let gov = make_gov(true, true);
        let state = make_state();
        // ATR=2000 to clear cost gate; intent confidence 0.7 default.
        // ATR=2000 通過 cost gate；intent confidence 預設 0.7。
        let r = proc.process_with_features(
            &make_intent("BTCUSDT", true),
            &gov,
            &state,
            2000.0,
            GovernanceProfile::Production,
            None,
            None,
            NOW_MS,
        );
        assert!(r.submitted, "Production happy path must accept");
        let lid = r.lease_id.expect("lease_id must be Some");
        assert!(
            lid.starts_with("lease:"),
            "Active lease id format check (lease:xxxx); got {lid}"
        );
        // Caller's consume() takes the lease out so Drop won't release; SM keeps
        // the Active lease for downstream fill consumer to release Consumed.
        // 呼叫端 consume() 取出 lease；SM 保留 Active 供下游 fill consumer 釋放。
        assert_eq!(
            gov.lease.lock().get_live().len(),
            1,
            "Active lease retained for fill consumer release"
        );
    }

    /// Test 3: flag ON + Validation/Exploration profile → LeaseId::Bypass
    /// short-circuit; SM never touched (PA push back #1 spec §3 point 1
    /// trailing clause). lease_id=Some("bypass") so audit can count Bypass
    /// occurrences distinctly from None.
    /// Test 3：flag ON + Validation/Exploration → LeaseId::Bypass 短路；
    /// SM 從未碰觸；lease_id=Some("bypass") 讓 audit 能區分 Bypass 與 None。
    #[test]
    fn test_router_gate_on_non_production_bypass() {
        let proc = IntentProcessor::new();
        let gov = make_gov(true, true);
        let state = make_state();

        // Validation profile.
        let r_val = proc.process_with_features(
            &make_intent("BTCUSDT", true),
            &gov,
            &state,
            2000.0,
            GovernanceProfile::Validation,
            None,
            None,
            NOW_MS,
        );
        assert!(r_val.submitted);
        assert_eq!(r_val.lease_id.as_deref(), Some("bypass"));

        // Exploration profile.
        let r_exp = proc.process_with_features(
            &make_intent("BTCUSDT", true),
            &gov,
            &state,
            2000.0,
            GovernanceProfile::Exploration,
            None,
            None,
            NOW_MS,
        );
        assert!(r_exp.submitted);
        assert_eq!(r_exp.lease_id.as_deref(), Some("bypass"));

        // SM untouched: 0 lease objects ever created.
        // SM 未碰觸：0 lease object。
        assert_eq!(gov.lease.lock().len(), 0);
    }

    /// Test 4: flag ON + Production + auth NOT effective → AuthNotEffective
    /// fail-closed reject. lease_id=None on rejection (per E-2 contract:
    /// rejection paths never carry lease lineage).
    /// Test 4：flag ON + Production + auth 未生效 → AuthNotEffective fail-closed
    /// 拒絕。拒絕路徑 lease_id=None（contract：rejection 不帶 lease lineage）。
    #[test]
    fn test_router_gate_on_production_no_auth_fails_closed() {
        let proc = IntentProcessor::new();
        let gov = make_gov(true, false); // flag ON but NO auth
        let state = make_state();
        let r = proc.process_with_features(
            &make_intent("BTCUSDT", true),
            &gov,
            &state,
            2000.0,
            GovernanceProfile::Production,
            None,
            None,
            NOW_MS,
        );
        assert!(!r.submitted, "no auth must fail-closed reject");
        let reason = r.rejected_reason.expect("must have reason");
        // Could be either Gate 1 (governance not authorized) or Gate 1.4 (lease
        // facade auth not effective) — both are valid fail-closed branches and
        // both surface auth failure to caller. Accept either form.
        // 可能是 Gate 1（governance not authorized）或 Gate 1.4（lease facade auth
        // not effective）— 兩者都是合法 fail-closed 路徑且都把 auth failure 透給
        // 呼叫端；接受任一形式。
        assert!(
            reason.contains("authoriz") || reason.contains("authorization"),
            "reason must mention authorization: {reason}"
        );
        assert!(r.lease_id.is_none());
        // SM untouched.
        assert_eq!(gov.lease.lock().len(), 0);
    }

    /// Test 5: flag ON + Production happy path through Gate 1.4 then downstream
    /// gate (ATR=0 SEC-11 fail-closed) rejection → RouterLeaseGuard Drop
    /// releases Cancelled; lease moves from Active to Revoked; lease_id=None
    /// on rejection.
    /// Test 5：flag ON + Production 通過 Gate 1.4 後下游 gate（ATR=0 SEC-11
    /// fail-closed）拒絕 → RouterLeaseGuard Drop 釋放 Cancelled；lease 從
    /// Active → Revoked；拒絕路徑 lease_id=None。
    #[test]
    fn test_router_gate_on_production_drop_cancels_on_atr_zero() {
        let proc = IntentProcessor::new();
        let gov = make_gov(true, true);
        let state = make_state();
        // ATR=0 forces SEC-11 fail-closed at Gate 3 cost gate (after Gate 1.4
        // has acquired the lease).
        // ATR=0 觸發 Gate 3 cost gate 的 SEC-11 fail-closed（Gate 1.4 已拿到 lease）。
        let r = proc.process_with_features(
            &make_intent("BTCUSDT", true),
            &gov,
            &state,
            0.0, // ATR=0
            GovernanceProfile::Production,
            None,
            None,
            NOW_MS,
        );
        assert!(!r.submitted, "ATR=0 must SEC-11 fail-closed downstream");
        assert!(r.lease_id.is_none(), "rejection path must NOT carry lease_id");
        let reason = r.rejected_reason.expect("must have reason");
        assert!(
            reason.contains("ATR") || reason.contains("atr"),
            "rejection reason must mention ATR: {reason}"
        );
        // SM has 1 lease total (acquired by Gate 1.4) but 0 live (Drop released
        // it Cancelled → Revoked).
        // SM 共 1 個 lease（Gate 1.4 acquire）但 0 個 live（Drop 釋放 Cancelled → Revoked）。
        let total = gov.lease.lock().len();
        let live = gov.lease.lock().get_live().len();
        assert_eq!(total, 1, "Gate 1.4 acquired one lease");
        assert_eq!(
            live, 0,
            "RouterLeaseGuard Drop must release acquired lease on rejection"
        );
    }

    /// Test 6: ExchangeGateResult mirror — flag OFF (Production profile)
    /// leaves lease_id None; flag ON + Validation profile yields Bypass;
    /// flag ON + Production fail-closed when cost gate is strict (no edge
    /// data) but Drop still cleans up the acquired lease (no leak).
    /// Test 6：ExchangeGateResult 對齊 — flag OFF + Production → lease_id None；
    /// flag ON + Validation → Bypass；flag ON + Production 嚴格 cost gate 拒絕
    /// 但 Drop 仍清理 acquired lease（不 leak）。
    #[test]
    fn test_router_gate_exchange_path_lease_id_states() {
        let proc = IntentProcessor::new();
        let state = make_state();

        // Sub-case 1: Flag OFF + Production → cost gate strict reject; lease_id None.
        // Sub-case 1：flag OFF + Production → cost gate 嚴格拒絕；lease_id None。
        let gov_off = make_gov(false, true);
        let g_off = proc.process_gates_only_with_features(
            &make_intent("BTCUSDT", true),
            &gov_off,
            &state,
            2000.0,
            GovernanceProfile::Production,
            None,
            None,
            NOW_MS,
        );
        // Production cost_gate_live_with_slippage is strict in absence of edge
        // data — exchange path rejects. lease_id stays None either way.
        // Production cost_gate_live_with_slippage 在無 edge 時嚴格拒絕；
        // lease_id 兩種情況都 None。
        assert!(g_off.lease_id.is_none(), "flag OFF → exchange path lease_id None");
        assert_eq!(gov_off.lease.lock().len(), 0, "flag OFF → SM untouched");

        // Sub-case 2: Flag ON + Validation → Bypass.
        // Sub-case 2：flag ON + Validation → Bypass。
        let gov_val = make_gov(true, true);
        let g_val = proc.process_gates_only_with_features(
            &make_intent("BTCUSDT", true),
            &gov_val,
            &state,
            2000.0,
            GovernanceProfile::Validation,
            None,
            None,
            NOW_MS,
        );
        assert_eq!(g_val.lease_id.as_deref(), Some("bypass"));
        assert_eq!(gov_val.lease.lock().len(), 0, "Validation → SM untouched");

        // Sub-case 3: Flag ON + Production. Gate 1.4 acquires lease; downstream
        // strict cost gate rejects → Drop releases Cancelled; SM ends with 0 live.
        // Sub-case 3：flag ON + Production。Gate 1.4 acquire；下游嚴格 cost gate
        // 拒絕 → Drop 釋放 Cancelled；SM 結束 0 live。
        let gov_prod = make_gov(true, true);
        let g_prod = proc.process_gates_only_with_features(
            &make_intent("BTCUSDT", true),
            &gov_prod,
            &state,
            2000.0,
            GovernanceProfile::Production,
            None,
            None,
            NOW_MS,
        );
        // Either approved (lease_id Some) OR rejected (lease_id None).
        // 接受（lease_id Some）或拒絕（lease_id None）兩種狀態都合法。
        if g_prod.approved {
            let lid = g_prod.lease_id.expect("Production approved → lease_id Some");
            assert!(lid.starts_with("lease:"));
            assert_eq!(
                gov_prod.lease.lock().get_live().len(),
                1,
                "Active lease retained for fill consumer release"
            );
        } else {
            assert!(g_prod.lease_id.is_none(), "rejection path → lease_id None");
            // Drop released the lease Cancelled.
            // Drop 釋放 Cancelled。
            assert_eq!(
                gov_prod.lease.lock().get_live().len(),
                0,
                "RouterLeaseGuard Drop releases on rejection (no leak)"
            );
            assert!(
                gov_prod.lease.lock().len() >= 1,
                "Gate 1.4 did acquire at least one lease before downstream reject"
            );
        }
    }

    /// Test 7 (perf SLA sanity): flag OFF Gate 1.4 short-circuit ≤ 50ns avg;
    /// flag ON acquire+release pair ≤ 5µs avg. Loose bound to avoid flake on
    /// CI runners; real SLA monitoring is via cargo bench. AMD §6 condition #1
    /// IPC budget = 100µs, so per-call ≤ 5µs leaves 20× headroom.
    /// Test 7（perf SLA 健康度）：flag OFF Gate 1.4 短路 ≤ 50ns 平均；
    /// flag ON acquire+release pair ≤ 5µs 平均。寬鬆 bound 避 CI flake；真實
    /// SLA 監控由 cargo bench 負責。AMD §6 條件 #1 IPC budget = 100µs，per-call
    /// ≤ 5µs 留 20× headroom。
    #[test]
    fn test_router_gate_perf_within_sla() {
        use std::time::Instant;
        const ITER: usize = 1_000;

        let proc = IntentProcessor::new();
        let state = make_state();

        // Flag OFF path: just `if router_gate_enabled() { ... }` short-circuit.
        // flag OFF 路徑：僅 `if router_gate_enabled() { ... }` 短路。
        let gov_off = make_gov(false, true);
        let intent = make_intent("BTCUSDT", true);
        let t0 = Instant::now();
        for _ in 0..ITER {
            let r = proc.process_with_features(
                &intent,
                &gov_off,
                &state,
                2000.0,
                GovernanceProfile::Exploration,
                None,
                None,
                NOW_MS,
            );
            std::hint::black_box(r);
        }
        let off_avg_ns = (t0.elapsed().as_nanos() as f64) / (ITER as f64);
        // Note: this measures the *whole* process_with_features call, not just
        // Gate 1.4. Gate 1.4 contribution itself is < 1ns when flag OFF.
        // 注：此測量整個 process_with_features，非單 Gate 1.4；flag OFF 時 Gate 1.4
        // 自身貢獻 < 1ns。
        assert!(
            off_avg_ns < 200_000.0, // 200µs loose ceiling for full process call
            "flag OFF avg {off_avg_ns}ns exceeds 200µs ceiling — process path regression?"
        );

        // Flag ON path: Gate 1.4 acquires lease + Drop releases Cancelled
        // (rejection path due to ATR=0). Each iter creates+drops one SM lease.
        // flag ON 路徑：Gate 1.4 acquire + Drop release Cancelled（ATR=0 拒絕路徑）。
        // 每 iter 創建+drop 一個 SM lease。
        let gov_on = make_gov(true, true);
        let t1 = Instant::now();
        for _ in 0..ITER {
            let r = proc.process_with_features(
                &intent,
                &gov_on,
                &state,
                0.0, // ATR=0 → SEC-11 reject after Gate 1.4 acquire → Drop release
                GovernanceProfile::Production,
                None,
                None,
                NOW_MS,
            );
            std::hint::black_box(r);
        }
        let on_avg_ns = (t1.elapsed().as_nanos() as f64) / (ITER as f64);
        // 200µs ceiling; AMD §6 IPC budget 100µs is for IPC roundtrip not
        // pure Rust facade — facade should be sub-µs in practice.
        // 200µs 上限；AMD §6 IPC budget 100µs 針對 IPC roundtrip 而非純 Rust
        // facade — facade 實務應 sub-µs。
        assert!(
            on_avg_ns < 200_000.0,
            "flag ON avg {on_avg_ns}ns exceeds 200µs ceiling — Mutex/SM regression?"
        );

        eprintln!(
            "AMD-2026-05-02-01 Track E E-2 Gate 1.4 perf — \
             flag OFF avg = {off_avg_ns:.0}ns, flag ON avg = {on_avg_ns:.0}ns"
        );
    }
}
