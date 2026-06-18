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
        // Sprint 1B Earn first stake — IntentType backward-compat 占位。
        intent_type: super::IntentType::OpenLong,
        earn_payload: None,
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
fn test_per_strategy_max_concurrent_positions_hard_reject() {
    // CC/E3 must-fix #1 HARD-layer regression（E2 HIGH-1）：
    // 注入 3 個由 flash_dip_buy 擁有的真倉（owner_strategy 經 apply_fill 設定），
    // 第 4 筆新開倉必須被「風控層」拒（per_strategy.max_concurrent_positions），
    // 而非僅靠 producer soft skip。驗證 backstop 在 import_positions 把 owner 重置
    // 後仍能依 owner_strategy 重數真倉 fail-closed。
    let mut proc = IntentProcessor::new();
    let mut cfg = RiskConfig::default();
    cfg.per_strategy.insert(
        "flash_dip_buy".into(),
        crate::config::risk_config::StrategyOverride {
            max_concurrent_positions: Some(3),
            ..Default::default()
        },
    );
    proc.update_risk_config(cfg);
    let mut gov = GovernanceCore::new();
    gov.grant_paper_authorization(None).unwrap();
    let mut state = PaperState::new(100_000.0);

    // 注入 3 個 flash_dip_buy 擁有的真倉（不同 symbol，owner_strategy 經 fill 設定）。
    for (sym, px) in [("ADAUSDT", 0.5), ("AVAXUSDT", 30.0), ("SOLUSDT", 150.0)] {
        state.set_latest_price(sym, px);
        state.apply_fill(sym, true, 1.0, px, 0.0, 0, "flash_dip_buy");
    }
    assert_eq!(
        state
            .positions()
            .iter()
            .filter(|p| p.owner_strategy == "flash_dip_buy")
            .count(),
        3,
        "fixture must seed exactly 3 flash_dip_buy-owned positions"
    );

    // 第 4 筆新開倉（新 symbol）必須被風控層 max_concurrent_positions 擋。
    state.set_latest_price("BTCUSDT", 50_000.0);
    let mut intent = make_intent("BTCUSDT", true);
    intent.strategy = "flash_dip_buy".into();
    let result = proc.process(&intent, &gov, &state, 2000.0, GovernanceProfile::Exploration);
    assert!(
        !result.submitted,
        "4th flash_dip_buy entry must be rejected by risk layer"
    );
    let reason = result.rejected_reason.unwrap_or_default();
    assert!(
        reason.contains("max_concurrent_positions=3"),
        "rejection must come from the risk-config concurrency cap, got: {reason}"
    );

    // Sanity：cap 內（同策略 2 倉）的第 3 筆仍應放行（驗證不是無條件全擋）。
    let mut state3 = PaperState::new(100_000.0);
    for (sym, px) in [("ADAUSDT", 0.5), ("AVAXUSDT", 30.0)] {
        state3.set_latest_price(sym, px);
        state3.apply_fill(sym, true, 1.0, px, 0.0, 0, "flash_dip_buy");
    }
    state3.set_latest_price("BTCUSDT", 50_000.0);
    let mut intent3 = make_intent("BTCUSDT", true);
    intent3.strategy = "flash_dip_buy".into();
    let result3 = proc.process(&intent3, &gov, &state3, 2000.0, GovernanceProfile::Exploration);
    assert!(
        result3.submitted,
        "3rd entry under cap=3 must pass concurrency gate, got {:?}",
        result3.rejected_reason
    );
}

#[test]
fn test_per_strategy_max_concurrent_allows_reducing_at_cap() {
    // 不變量：達上限時平倉/減倉永不被並發 gate 擋（survival 路徑）。
    let mut proc = IntentProcessor::new();
    let mut cfg = RiskConfig::default();
    cfg.per_strategy.insert(
        "flash_dip_buy".into(),
        crate::config::risk_config::StrategyOverride {
            max_concurrent_positions: Some(3),
            ..Default::default()
        },
    );
    proc.update_risk_config(cfg);
    let mut gov = GovernanceCore::new();
    gov.grant_paper_authorization(None).unwrap();
    let mut state = PaperState::new(100_000.0);
    for (sym, px) in [("ADAUSDT", 0.5), ("AVAXUSDT", 30.0), ("SOLUSDT", 150.0)] {
        state.set_latest_price(sym, px);
        state.apply_fill(sym, true, 1.0, px, 0.0, 0, "flash_dip_buy");
    }
    // 反向 (Sell) 對既有 long 倉 = reducing；應繞過並發上限。
    let mut intent = make_intent("ADAUSDT", false);
    intent.strategy = "flash_dip_buy".into();
    intent.qty = 1.0;
    let result = proc.process(&intent, &gov, &state, 0.01, GovernanceProfile::Exploration);
    assert!(
        result.submitted,
        "reducing order at cap must bypass concurrency gate, got {:?}",
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
fn test_kelly_config_reanchors_to_risk_config_per_trade_pct() {
    let mut proc = IntentProcessor::new();
    proc.set_kelly_config(crate::ml::kelly_sizer::KellyConfig::default());

    let mut cfg = RiskConfig::default();
    cfg.limits.per_trade_risk_pct = crate::config::MIN_PER_TRADE_RISK_PCT;
    cfg.kelly.young_fraction = 0.10;
    cfg.kelly.mature_fraction = 0.20;
    cfg.kelly.established_fraction = 0.30;
    proc.update_risk_config(cfg.clone());

    let kelly = proc
        .kelly_config
        .as_ref()
        .expect("existing KellyConfig must be re-derived on risk update");
    assert!(
        (proc.p1_risk_pct - crate::config::MIN_PER_TRADE_RISK_PCT).abs() < 1e-12,
        "IntentProcessor P1 cap should share the RiskConfig lower bound"
    );
    assert!(
        (kelly.risk_pct - cfg.limits.per_trade_risk_pct).abs() < 1e-12,
        "Kelly cold-start risk_pct must come from RiskConfig.limits"
    );
    assert!((kelly.young_fraction - cfg.kelly.young_fraction).abs() < 1e-12);
    assert!((kelly.mature_fraction - cfg.kelly.mature_fraction).abs() < 1e-12);
    assert!((kelly.established_fraction - cfg.kelly.established_fraction).abs() < 1e-12);
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
        // Sprint 1B Earn first stake — IntentType backward-compat 占位。
        intent_type: super::IntentType::OpenLong,
        earn_payload: None,
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
        // Sprint 1B Earn first stake — IntentType backward-compat 占位。
        intent_type: super::IntentType::OpenLong,
        earn_payload: None,
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
        // Sprint 1B Earn first stake — IntentType backward-compat 占位。
        intent_type: super::IntentType::OpenLong,
        earn_payload: None,
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
        // Sprint 1B Earn first stake — IntentType backward-compat 占位。
        intent_type: super::IntentType::OpenLong,
        earn_payload: None,
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
        // Sprint 1B Earn first stake — IntentType backward-compat 占位。
        intent_type: super::IntentType::OpenLong,
        earn_payload: None,
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
        // Sprint 1B Earn first stake — IntentType backward-compat 占位。
        intent_type: super::IntentType::OpenLong,
        earn_payload: None,
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
        // Sprint 1B Earn first stake — IntentType backward-compat 占位。
        intent_type: super::IntentType::OpenLong,
        earn_payload: None,
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
        // Sprint 1B Earn first stake — IntentType backward-compat 占位。
        intent_type: super::IntentType::OpenLong,
        earn_payload: None,
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
fn test_cost_gate_moderate_low_sample_deep_neg_blocks() {
    // EDGE-DIAG-2 v2(2026-05-23 PM RCA + MIT sensitivity sweep):
    // low-sample deep-negative arm 已上線:n<min_n 且 shrunk_bps<-15 改為 BLOCK,
    // 不再無條件走探索。原因:NEARUSDT(n=18, shrunk_bps=-16.46)在 noise band 內
    // 累損 6 天 -21.98 USD demo。新 arm 把 deep tail(< -15)從探索分離出來直接 deny;
    // noise band [-15, 0) 仍走探索,維持「demo 放寬」精神。
    // 本 test 從 routes_to_exploration 改 deep_neg_blocks,fixture(shrunk=-50, n=6)
    // 同時滿足 n<min_n AND shrunk<-15 → 新 arm 攔截。
    // EDGE-DIAG-2 v2:低樣本深負(n<30 且 < -15bps)改為 BLOCK,避免噪音帶累損。
    let mut proc = IntentProcessor::new();
    let json = r#"{"ma_crossover::BTCUSDT": {"shrunk_bps": -50.0, "win_rate": 0.3, "n": 6, "std_bps": 5.0}}"#;
    let estimates = crate::edge_estimates::EdgeEstimates::load_from_str(json).unwrap();
    proc.set_edge_estimates(estimates);
    let result = proc.cost_gate_moderate("ma_crossover", "BTCUSDT", 0.00055, 1_000_000_000.0);
    assert!(
        result.is_some(),
        "low-sample deep-negative (n=6 < 30 AND shrunk -50 < -15) should BLOCK via EDGE-DIAG-2 v2 arm"
    );
    let reason = result.unwrap().rejected_reason.unwrap();
    assert!(
        reason.contains("JS-demo"),
        "block reason should be CostGateJsDemoNegative variant, got: {reason}"
    );
}

#[test]
fn test_cost_gate_moderate_low_sample_noise_band_explore() {
    // EDGE-DIAG-2 v2 boundary:low-sample 但 shrunk 落在 noise band [-15, 0) 內
    // 仍走探索 — 統計上 50% 命中率,deep tail 才方向可靠。
    // Fixture: n=6 < min_n=30,shrunk=-10.0 ∈ [-15, 0) → 不觸發新 arm,
    // fall-through 到既有 low-sample arm 探索。
    // EDGE-DIAG-2 v2 邊界:noise band 內低樣本續走探索。
    let mut proc = IntentProcessor::new();
    let json = r#"{"ma_crossover::BTCUSDT": {"shrunk_bps": -10.0, "win_rate": 0.3, "n": 6, "std_bps": 5.0}}"#;
    let estimates = crate::edge_estimates::EdgeEstimates::load_from_str(json).unwrap();
    proc.set_edge_estimates(estimates);
    let result = proc.cost_gate_moderate("ma_crossover", "BTCUSDT", 0.00055, 1_000_000_000.0);
    assert!(
        result.is_none(),
        "low-sample shrunk -10 ∈ [-15, 0) noise band should still explore, not block"
    );
}

#[test]
fn test_cost_gate_moderate_low_sample_at_neg15_boundary_explore() {
    // EDGE-DIAG-2 v2 嚴格 `<` 邊界:shrunk_bps == -15.0 恰在 cutoff,
    // 新 arm guard 是 `cell.shrunk_bps < -15.0`(strict less-than),
    // -15.0 不觸發,fall-through 到 low-sample 探索 arm。
    // 守住「邊界不攔」契約,避免 cutoff 移動造成 flip-flop。
    // EDGE-DIAG-2 v2 邊界:cutoff -15.0 嚴格 `<`,等號不攔。
    let mut proc = IntentProcessor::new();
    let json = r#"{"ma_crossover::BTCUSDT": {"shrunk_bps": -15.0, "win_rate": 0.3, "n": 6, "std_bps": 5.0}}"#;
    let estimates = crate::edge_estimates::EdgeEstimates::load_from_str(json).unwrap();
    proc.set_edge_estimates(estimates);
    let result = proc.cost_gate_moderate("ma_crossover", "BTCUSDT", 0.00055, 1_000_000_000.0);
    assert!(
        result.is_none(),
        "shrunk == -15.0 at boundary (strict `<` not `<=`) should not block, fall-through to explore"
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
    // P1-09: this test pins the slippage-math intent, so the cell must satisfy
    // the new freshness gate (fresh + runtime + validated) — otherwise live
    // would reject on freshness before reaching the threshold compare.
    // P1-09：本測試釘住滑點數學意圖，cell 須通過新鮮度門（fresh+runtime+validated），
    // 否則 live 會在門檻比較前因新鮮度先行拒絕。
    let now = super::gates::TEST_NOW_SECS;
    let json = format!(
        r#"{{
            "_meta": {{"grand_mean_bps": 1.0, "updated_at": "{ts}"}},
            "grid_trading::BTCUSDT": {{"runtime_bps": 10.0, "shrunk_bps": 10.0, "win_rate": 1.0, "n": 100, "std_bps": 2.0, "validation_passed": true}}
        }}"#,
        ts = chrono::DateTime::<chrono::Utc>::from_timestamp(now, 0)
            .unwrap()
            .to_rfc3339(),
    );
    let estimates = crate::edge_estimates::EdgeEstimates::load_from_str(&json).unwrap();
    proc.set_edge_estimates(estimates);

    let postonly_cost = proc.cost_gate_live_with_slippage(
        "grid_trading",
        "BTCUSDT",
        0.0002, // maker fee
        0.0,    // PostOnly maker path: no taker-style slippage tier
        now,
    );
    let taker_slippage_cost =
        proc.cost_gate_live_with_slippage("grid_trading", "BTCUSDT", 0.00055, 0.0030, now);

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

// ─── Track1 (2026-06-14): demo explore-gate（branch A/B 翻 reject 為探索放行）───
// 只改 demo gate（cost_gate_moderate_with_slippage）。覆蓋：
//   (A) low-sample deep-negative + explore_eligible+remaining>0 → 放行
//   (B) robust-negative(n≥min_n) + explore_eligible+remaining>0 → 放行
//   fail-closed：缺欄 / explore_remaining=0 / explore_eligible=false → 維持現行 block
//   隔離：相同 explore 欄位餵 live gate 不改變 live 行為（live 不讀新欄）

#[test]
fn test_cost_gate_moderate_branch_a_explore_allows_deep_neg_low_sample() {
    // branch A：低樣本(n<min_n) + 深負(<-15bps)，現行會 block；
    // explore_eligible=true + remaining>0 → 探索放行（None）。
    let mut proc = IntentProcessor::new();
    let json = r#"{"ma_crossover::BTCUSDT": {"shrunk_bps": -25.0, "win_rate": 0.35, "n": 5, "std_bps": 2.0, "explore_eligible": true, "explore_remaining": 18}}"#;
    let estimates = crate::edge_estimates::EdgeEstimates::load_from_str(json).unwrap();
    proc.set_edge_estimates(estimates);
    let result = proc.cost_gate_moderate("ma_crossover", "BTCUSDT", 0.00055, 1_000_000_000.0);
    assert!(
        result.is_none(),
        "branch A: explore-eligible deep-neg low-sample should be allowed (explore)"
    );
}

#[test]
fn test_cost_gate_moderate_branch_a_remaining_zero_still_blocks() {
    // branch A：explore_eligible=true 但 remaining=0（探索滿額）→ 仍 block（誠實死）。
    let mut proc = IntentProcessor::new();
    let json = r#"{"ma_crossover::BTCUSDT": {"shrunk_bps": -25.0, "win_rate": 0.35, "n": 5, "std_bps": 2.0, "explore_eligible": true, "explore_remaining": 0}}"#;
    let estimates = crate::edge_estimates::EdgeEstimates::load_from_str(json).unwrap();
    proc.set_edge_estimates(estimates);
    let result = proc.cost_gate_moderate("ma_crossover", "BTCUSDT", 0.00055, 1_000_000_000.0);
    assert!(
        result.is_some(),
        "branch A: explore_remaining=0 should still block (budget exhausted)"
    );
}

#[test]
fn test_cost_gate_moderate_branch_a_not_eligible_still_blocks() {
    // branch A：remaining>0 但 explore_eligible=false（allocator 不指示探索）→ 仍 block。
    let mut proc = IntentProcessor::new();
    let json = r#"{"ma_crossover::BTCUSDT": {"shrunk_bps": -25.0, "win_rate": 0.35, "n": 5, "std_bps": 2.0, "explore_eligible": false, "explore_remaining": 18}}"#;
    let estimates = crate::edge_estimates::EdgeEstimates::load_from_str(json).unwrap();
    proc.set_edge_estimates(estimates);
    let result = proc.cost_gate_moderate("ma_crossover", "BTCUSDT", 0.00055, 1_000_000_000.0);
    assert!(
        result.is_some(),
        "branch A: explore_eligible=false should still block (allocator not exploring)"
    );
}

#[test]
fn test_cost_gate_moderate_branch_b_explore_allows_robust_neg() {
    // branch B：高樣本穩健負(n≥min_n)，現行會 block；
    // explore_eligible=true + remaining>0 → 探索放行（regime-driven）。
    let mut proc = IntentProcessor::new();
    let json = r#"{"ma_crossover::BTCUSDT": {"shrunk_bps": -25.0, "win_rate": 0.35, "n": 200, "std_bps": 2.0, "explore_eligible": true, "explore_remaining": 7}}"#;
    let estimates = crate::edge_estimates::EdgeEstimates::load_from_str(json).unwrap();
    proc.set_edge_estimates(estimates);
    let result = proc.cost_gate_moderate("ma_crossover", "BTCUSDT", 0.00055, 1_000_000_000.0);
    assert!(
        result.is_none(),
        "branch B: explore-eligible robust-neg should be allowed (regime-driven explore)"
    );
}

#[test]
fn test_cost_gate_moderate_branch_b_remaining_zero_still_blocks() {
    // branch B：robust-negative + explore_eligible=true 但 remaining=0 → 仍 block。
    let mut proc = IntentProcessor::new();
    let json = r#"{"ma_crossover::BTCUSDT": {"shrunk_bps": -25.0, "win_rate": 0.35, "n": 200, "std_bps": 2.0, "explore_eligible": true, "explore_remaining": 0}}"#;
    let estimates = crate::edge_estimates::EdgeEstimates::load_from_str(json).unwrap();
    proc.set_edge_estimates(estimates);
    let result = proc.cost_gate_moderate("ma_crossover", "BTCUSDT", 0.00055, 1_000_000_000.0);
    assert!(
        result.is_some(),
        "branch B: robust-neg explore_remaining=0 should still block"
    );
}

#[test]
fn test_cost_gate_moderate_missing_explore_fields_fail_closed_block() {
    // fail-closed：JSON 完全無 explore 欄（舊格式）→ unwrap_or(false/0) → 維持現行 block。
    // 同時驗 branch A（deep-neg low-sample）的舊行為 byte-identical。
    let mut proc = IntentProcessor::new();
    let json = r#"{"ma_crossover::BTCUSDT": {"shrunk_bps": -25.0, "win_rate": 0.35, "n": 5, "std_bps": 2.0}}"#;
    let estimates = crate::edge_estimates::EdgeEstimates::load_from_str(json).unwrap();
    proc.set_edge_estimates(estimates);
    let result = proc.cost_gate_moderate("ma_crossover", "BTCUSDT", 0.00055, 1_000_000_000.0);
    assert!(
        result.is_some(),
        "missing explore fields must fail-closed to existing block (absence=no-explore)"
    );
}

#[test]
fn test_cost_gate_live_ignores_explore_fields_robust_neg_still_blocks() {
    // 隔離鐵則：相同 explore_eligible=true + remaining>0 餵 LIVE gate，
    // live 必仍 block（負估計）—— live gate 不讀 explore 欄，demo↔live 隔離。
    let mut proc = IntentProcessor::new();
    let json = r#"{"ma_crossover::BTCUSDT": {"shrunk_bps": -25.0, "win_rate": 0.35, "n": 200, "std_bps": 2.0, "explore_eligible": true, "explore_remaining": 30}}"#;
    let estimates = crate::edge_estimates::EdgeEstimates::load_from_str(json).unwrap();
    proc.set_edge_estimates(estimates);
    let result = proc.cost_gate_live("ma_crossover", "BTCUSDT", 0.00055, 1_000_000_000.0);
    assert!(
        result.is_some(),
        "live gate must IGNORE explore fields — negative estimate still fail-closed"
    );
    let reason = result.unwrap().rejected_reason.unwrap();
    assert!(
        reason.contains("live"),
        "expected live rejection reason, got: {}",
        reason
    );
}

// ─── Track1 E4 (2026-06-14): file-based end-to-end（真檔 reload seam）───
//   上面 7 個 E1 單測用 load_from_str（in-memory）。以下 E4 補測走真實
//   reload 路徑：寫 scratch settings/edge_estimates.json → load_for_mode("demo")
//   → set_edge_estimates → demo gate。驗證 (a) Python sink 落檔的同一 file 契約
//   被 Rust 正確解析並翻 reject 為 explore-pass；(b) 同檔 explore_remaining=0
//   與缺欄仍 fail-closed block；(c) 同檔餵 live（load_for_mode("live") 讀同檔名）
//   仍 block（demo↔live 隔離在真檔層成立）。

/// 把 JSON 寫進 tempdir 的 settings/edge_estimates.json（demo+live 共用檔名），
/// 回 (TempDir, base_dir)。base_dir/settings/edge_estimates.json 即 load_for_mode
/// 對 demo/live 讀的路徑（edge_estimates.rs:253-258）。
#[cfg(test)]
fn write_scratch_edge_file(json: &str) -> (tempfile::TempDir, std::path::PathBuf) {
    let dir = tempfile::tempdir().expect("tempdir");
    let base = dir.path().to_path_buf();
    let settings = base.join("settings");
    std::fs::create_dir_all(&settings).expect("mkdir settings");
    std::fs::write(settings.join("edge_estimates.json"), json).expect("write edge file");
    (dir, base)
}

#[test]
fn test_e2e_file_reload_demo_gate_flips_reject_to_explore() {
    // 端到端：scratch edge_estimates.json 帶 explore_eligible=true/remaining>0 的
    // robust-negative cell → 真檔 load_for_mode("demo") → demo gate 翻 None（放行）。
    let json = r#"{
        "_meta": {"grand_mean_bps": 0.0, "updated_at": "2026-06-13T00:00:00+00:00"},
        "ma_crossover::BTCUSDT": {"shrunk_bps": -25.0, "win_rate": 0.35, "n": 200, "std_bps": 2.0, "explore_eligible": true, "explore_remaining": 12}
    }"#;
    let (_dir, base) = write_scratch_edge_file(json);
    let estimates = crate::edge_estimates::EdgeEstimates::load_for_mode(&base, "demo");
    // 真檔解析正確：cell 存在且 explore 欄被讀到。
    let cell = estimates
        .get_cell("ma_crossover", "BTCUSDT")
        .expect("cell loaded from scratch file");
    assert!(cell.explore_eligible, "explore_eligible must parse true from file");
    assert_eq!(cell.explore_remaining, 12, "explore_remaining must parse from file");

    let mut proc = IntentProcessor::new();
    proc.set_edge_estimates(estimates);
    let result = proc.cost_gate_moderate("ma_crossover", "BTCUSDT", 0.00055, 1_000_000_000.0);
    assert!(
        result.is_none(),
        "E2E: file-loaded explore-eligible robust-neg should flip reject→explore-pass"
    );
}

#[test]
fn test_e2e_file_reload_remaining_zero_still_blocks() {
    // 同真檔路徑：explore_remaining=0（探索滿額）→ 仍 block（fail-closed）。
    let json = r#"{
        "ma_crossover::BTCUSDT": {"shrunk_bps": -25.0, "win_rate": 0.35, "n": 200, "std_bps": 2.0, "explore_eligible": true, "explore_remaining": 0}
    }"#;
    let (_dir, base) = write_scratch_edge_file(json);
    let estimates = crate::edge_estimates::EdgeEstimates::load_for_mode(&base, "demo");
    let mut proc = IntentProcessor::new();
    proc.set_edge_estimates(estimates);
    let result = proc.cost_gate_moderate("ma_crossover", "BTCUSDT", 0.00055, 1_000_000_000.0);
    assert!(
        result.is_some(),
        "E2E: file-loaded explore_remaining=0 must still block (budget exhausted)"
    );
}

#[test]
fn test_e2e_file_reload_missing_fields_fail_closed_block() {
    // 同真檔路徑：舊格式 JSON（無 explore 欄）→ unwrap_or(false/0) → 仍 block。
    let json = r#"{
        "ma_crossover::BTCUSDT": {"shrunk_bps": -25.0, "win_rate": 0.35, "n": 200, "std_bps": 2.0}
    }"#;
    let (_dir, base) = write_scratch_edge_file(json);
    let estimates = crate::edge_estimates::EdgeEstimates::load_for_mode(&base, "demo");
    let cell = estimates.get_cell("ma_crossover", "BTCUSDT").expect("cell");
    assert!(!cell.explore_eligible, "missing field → fail-closed false");
    assert_eq!(cell.explore_remaining, 0, "missing field → fail-closed 0");
    let mut proc = IntentProcessor::new();
    proc.set_edge_estimates(estimates);
    let result = proc.cost_gate_moderate("ma_crossover", "BTCUSDT", 0.00055, 1_000_000_000.0);
    assert!(
        result.is_some(),
        "E2E: file-loaded old-format (no explore fields) must fail-closed block"
    );
}

#[test]
fn test_e2e_file_reload_same_file_live_gate_isolated_still_blocks() {
    // demo↔live 隔離在真檔層：load_for_mode("demo") 與 ("live") 讀同一檔名
    // edge_estimates.json（edge_estimates.rs:256 demo+live 共用）。同一 explore=true
    // 檔餵 live gate 必仍 block（live 不讀 explore 欄）。
    let json = r#"{
        "ma_crossover::BTCUSDT": {"shrunk_bps": -25.0, "win_rate": 0.35, "n": 200, "std_bps": 2.0, "explore_eligible": true, "explore_remaining": 30}
    }"#;
    let (_dir, base) = write_scratch_edge_file(json);
    // demo 讀同檔 → 放行
    let demo_est = crate::edge_estimates::EdgeEstimates::load_for_mode(&base, "demo");
    let mut demo_proc = IntentProcessor::new();
    demo_proc.set_edge_estimates(demo_est);
    assert!(
        demo_proc
            .cost_gate_moderate("ma_crossover", "BTCUSDT", 0.00055, 1_000_000_000.0)
            .is_none(),
        "E2E: demo gate flips on shared file"
    );
    // live 讀同檔 → 仍 block（隔離）
    let live_est = crate::edge_estimates::EdgeEstimates::load_for_mode(&base, "live");
    let mut live_proc = IntentProcessor::new();
    live_proc.set_edge_estimates(live_est);
    let live_result =
        live_proc.cost_gate_live("ma_crossover", "BTCUSDT", 0.00055, 1_000_000_000.0);
    assert!(
        live_result.is_some(),
        "E2E: live gate reading SAME shared file must IGNORE explore fields and block"
    );
}

// ─── P1-09 (2026-05-29): positive-edge freshness gate ───
// 正 edge 新鮮度門：fresh + runtime-derived + validated 才允許過生產門；
// live → reject / demo → exploration（非對稱）。`now` 注入 TEST_NOW_SECS。

/// P1-09 fixture：構造一個正 edge cell，可選 fresh / runtime / validated。
/// `age_secs` = now - updated_at（None → 不寫 updated_at，模擬舊快照無時間戳）。
fn p1_09_estimates(
    age_secs: Option<i64>,
    has_runtime: bool,
    validated: bool,
) -> crate::edge_estimates::EdgeEstimates {
    let now = super::gates::TEST_NOW_SECS;
    let meta = match age_secs {
        Some(age) => format!(
            r#""_meta": {{"grand_mean_bps": 1.0, "updated_at": "{ts}"}},"#,
            ts = chrono::DateTime::<chrono::Utc>::from_timestamp(now - age, 0)
                .unwrap()
                .to_rfc3339(),
        ),
        None => String::from(r#""_meta": {"grand_mean_bps": 1.0},"#),
    };
    // 高正 edge（50 bps）確保不會因門檻比較失敗；只測新鮮度分支。
    let bps_field = if has_runtime {
        r#""runtime_bps": 50.0, "shrunk_bps": 50.0"#
    } else {
        r#""shrunk_bps": 50.0"#
    };
    let json = format!(
        r#"{{
            {meta}
            "ma_crossover::BTCUSDT": {{{bps}, "win_rate": 0.6, "n": 100, "std_bps": 5.0, "validation_passed": {val}}}
        }}"#,
        meta = meta,
        bps = bps_field,
        val = validated,
    );
    crate::edge_estimates::EdgeEstimates::load_from_str(&json).unwrap()
}

#[test]
fn test_p1_09_live_all_three_fresh_runtime_validated_passes() {
    let mut proc = IntentProcessor::new();
    proc.set_edge_estimates(p1_09_estimates(Some(3_600), true, true)); // 1h old
    let result = proc.cost_gate_live("ma_crossover", "BTCUSDT", 0.00055, 1_000_000_000.0);
    assert!(
        result.is_none(),
        "fresh + runtime + validated positive edge must pass live"
    );
}

#[test]
fn test_p1_09_live_stale_positive_rejected() {
    let mut proc = IntentProcessor::new();
    // age 49h > 48h TTL → stale.
    proc.set_edge_estimates(p1_09_estimates(Some(49 * 3_600), true, true));
    let result = proc.cost_gate_live("ma_crossover", "BTCUSDT", 0.00055, 1_000_000_000.0);
    let reason = result
        .expect("stale positive edge must reject in live")
        .rejected_reason
        .unwrap();
    assert!(
        reason.contains("JS-live") && reason.contains("fail-closed"),
        "expected stale-or-unvalidated live reject, got: {reason}"
    );
}

#[test]
fn test_p1_09_live_missing_runtime_field_rejected() {
    let mut proc = IntentProcessor::new();
    // fresh + validated but legacy shrunk_bps only (no runtime_bps).
    proc.set_edge_estimates(p1_09_estimates(Some(3_600), false, true));
    let result = proc.cost_gate_live("ma_crossover", "BTCUSDT", 0.00055, 1_000_000_000.0);
    let reason = result
        .expect("legacy-only positive edge must reject in live")
        .rejected_reason
        .unwrap();
    assert!(
        reason.contains("has_runtime=false"),
        "expected has_runtime=false in reason, got: {reason}"
    );
}

#[test]
fn test_p1_09_live_validation_failed_rejected() {
    let mut proc = IntentProcessor::new();
    // fresh + runtime but validation_passed=false.
    proc.set_edge_estimates(p1_09_estimates(Some(3_600), true, false));
    let result = proc.cost_gate_live("ma_crossover", "BTCUSDT", 0.00055, 1_000_000_000.0);
    let reason = result
        .expect("unvalidated positive edge must reject in live")
        .rejected_reason
        .unwrap();
    assert!(
        reason.contains("validated=false"),
        "expected validated=false in reason, got: {reason}"
    );
}

#[test]
fn test_p1_09_live_no_timestamp_rejected() {
    let mut proc = IntentProcessor::new();
    // 舊快照無 _meta.updated_at → is_fresh False → reject（age=none）。
    proc.set_edge_estimates(p1_09_estimates(None, true, true));
    let result = proc.cost_gate_live("ma_crossover", "BTCUSDT", 0.00055, 1_000_000_000.0);
    let reason = result
        .expect("no-timestamp positive edge must reject in live")
        .rejected_reason
        .unwrap();
    assert!(
        reason.contains("age=none"),
        "expected age=none in reason, got: {reason}"
    );
}

#[test]
fn test_p1_09_demo_stale_positive_enters_exploration_not_reject() {
    let mut proc = IntentProcessor::new();
    // 同樣 stale 正 edge：demo 路徑必須走探索（None），NOT reject。
    // 這是 Phase 5 死循環防護的核心非對稱。
    proc.set_edge_estimates(p1_09_estimates(Some(49 * 3_600), true, true));
    let result = proc.cost_gate_moderate("ma_crossover", "BTCUSDT", 0.00055, 1_000_000_000.0);
    assert!(
        result.is_none(),
        "demo stale positive edge must enter exploration (None), not reject"
    );
}

#[test]
fn test_p1_09_demo_unvalidated_positive_enters_exploration_not_reject() {
    let mut proc = IntentProcessor::new();
    proc.set_edge_estimates(p1_09_estimates(Some(3_600), false, false));
    let result = proc.cost_gate_moderate("ma_crossover", "BTCUSDT", 0.00055, 1_000_000_000.0);
    assert!(
        result.is_none(),
        "demo legacy/unvalidated positive edge must enter exploration, not reject"
    );
}

#[test]
fn test_p1_09_demo_all_three_proven_still_threshold_checked() {
    let mut proc = IntentProcessor::new();
    // fresh + runtime + validated 正 edge（50 bps）→ 通過新鮮度門後做門檻比較 → pass。
    proc.set_edge_estimates(p1_09_estimates(Some(3_600), true, true));
    let result = proc.cost_gate_moderate("ma_crossover", "BTCUSDT", 0.00055, 1_000_000_000.0);
    assert!(
        result.is_none(),
        "demo proven high positive edge must pass threshold check"
    );
}

// ─── A-4 (B2, 2026-06-01)：移除 Python edge 歸零後的雙路徑接管鎖死 ───
//
// 背景 root cause：james_stein_estimator.py 原本對「未過驗證的正 edge」做歸零
// (runtime_bps=0.0)。歸零後 Rust edge_estimates.rs:149 優先讀 runtime_bps →
// CellEstimate.shrunk_bps=0.0 → demo gate(gates.rs:177 `shrunk_bps > 0.0`) 為
// false → 跳過 demo 探索臂(:177-194)，誤落 :216 當負 edge 阻擋。B2 移除 Python
// 歸零，讓 runtime_bps 保留真實正值，靠 Rust demo/live 非對稱接管。
//
// 以下兩測試模擬「移除歸零後」的真實快照形態 = runtime_bps 帶真實正值
// (has_runtime=true) + validation_passed=false，鎖死非對稱契約：
//   - live：fail-closed 仍 reject（不被連帶鬆動，根原則 #5 生存 > 利潤）。
//   - demo：探索臂正確觸發回 None（不再誤落負阻擋），demo-loose 設計復原。
// 二者皆不依賴 Python 歸零，純靠 gates.rs 對 validation_passed 的檢查。

#[test]
fn test_a4_live_unvalidated_positive_runtime_still_rejects() {
    // A-4 live fail-closed 鎖：cell 為「正 edge(runtime_bps>0) + 未驗證」——
    // 即移除 Python 歸零後 live 仍會遇到的形態。cost_gate_live 必 reject
    // (CostGateJsLiveStaleOrUnvalidated, gates.rs:275)，證明 live 不靠歸零保護。
    // fresh=true + has_runtime=true 隔離掉新鮮度 / 舊格式分支，使 reject 唯一
    // 歸因於 validation_passed=false。
    let mut proc = IntentProcessor::new();
    proc.set_edge_estimates(p1_09_estimates(Some(3_600), true, false));
    let result = proc.cost_gate_live("ma_crossover", "BTCUSDT", 0.00055, 1_000_000_000.0);
    let reason = result
        .expect("A-4: live unvalidated positive (runtime_bps>0) must fail-closed")
        .rejected_reason
        .unwrap();
    assert!(
        reason.contains("validated=false"),
        "A-4: live reject 必歸因 validation_passed=false（不依賴 Python 歸零），got: {reason}"
    );
}

#[test]
fn test_a4_demo_mature_unvalidated_positive_runtime_enters_exploration() {
    // A-4 demo-loose 復原鎖：同一 cell（mature n=100 ≥ min_n(30) + 正 edge
    // runtime_bps>0 + 未驗證）在 demo cost_gate_moderate 必回 None（探索放行），
    // 證明移除歸零後 demo 探索臂(gates.rs:184)正確觸發、不再因 shrunk_bps=0.0
    // 誤落 :216 負阻擋。這是修復前被架空的那條臂。
    // 注意：p1_09_estimates 內 n=100（> 預設 min_n=30），故走的是「正 edge
    // 未驗證 → 探索」臂(:184)，而非低樣本臂(:163)；二者皆 None 但路徑不同，
    // 本測試鎖的是成熟 cell 的非對稱（demo None vs 同 cell live reject）。
    let mut proc = IntentProcessor::new();
    proc.set_edge_estimates(p1_09_estimates(Some(3_600), true, false));
    let result = proc.cost_gate_moderate("ma_crossover", "BTCUSDT", 0.00055, 1_000_000_000.0);
    assert!(
        result.is_none(),
        "A-4: demo mature unvalidated positive(runtime_bps>0) 必入探索(None)，不誤落負阻擋"
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
        // Sprint 1B Earn first stake — IntentType backward-compat 占位。
        intent_type: super::IntentType::OpenLong,
        earn_payload: None,
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
        // Sprint 1B Earn first stake — IntentType backward-compat 占位。
        intent_type: super::IntentType::OpenLong,
        earn_payload: None,
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
        // Sprint 1B Earn first stake — IntentType backward-compat 占位。
        intent_type: super::IntentType::OpenLong,
        earn_payload: None,
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
        // Sprint 1B Earn first stake — IntentType backward-compat 占位。
        intent_type: super::IntentType::OpenLong,
        earn_payload: None,
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

// 為控制本 file LOC,將 nested test mod 拆出獨立 file 並由此處 include!。
// portfolio resting-order 測試組（P1/P2-PORTFOLIO-RESTING-EXPOSURE-1）亦因 2000
// 行硬上限拆出 tests_portfolio_resting.rs，內聯位置與原順序一致。
include!("tests_predictor_router.rs");
include!("tests_sprint1b_earn.rs");
include!("tests_portfolio_resting.rs");
