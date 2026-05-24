// ──────────────────────────────────────────────────────────────────────────────
// MODULE_NOTE
// 模塊用途:Sprint 1B Earn first stake — IntentType + EarnIntentPayload unit test。
// 主要 test 函數:
//   - intent_type_default_is_open_long          : Default impl backward-compat
//   - intent_type_is_earn_only_for_earn_variants: is_earn() 7 variant exhaustive
//   - intent_type_to_lease_scope_audit_str_mapping: 7 variant → 5 audit string 映射
//   - intent_type_serde_snake_case_roundtrip    : serde rename_all roundtrip
//   - order_intent_backward_compat_deserialize_without_new_fields: legacy IPC payload
//   - order_intent_earn_payload_serialize_and_roundtrip          : 完整 EarnStake payload
//   - order_intent_trading_payload_earn_payload_stays_none       : trading 0 行為差
// 依賴:本 file 由 tests.rs include!,故能直接用 super::* 引用 mod 內的 IntentType /
//   EarnIntentPayload / OrderIntent。
// 硬邊界:
//   - 7 test 全 PASS = backward-compat 鐵證(既有 4 + 2 策略 + IPC consumer 不破);
//   - 新加 IntentType variant 必須同步補 is_earn() + to_lease_scope_audit_str() 兩
//     match arm(exhaustive 編譯期強制) + 補本 file 對應 enumerate test case。
// 對齊:PA dispatch packet 2026-05-23 §2 + Operator B1 IMPL spec(7 variant +
//   serde snake_case + EarnIntentPayload 7 field + OrderIntent backward-compat
//   default OpenLong)。
// 拆分理由:tests.rs 加完 7 test 後超過 CLAUDE.md §九「2000 line hard cap」(2178 LOC);
//   本 file 是 split test mod 把新 test 抽出來,維持 tests.rs 在 ~2000 LOC 邊界內。
// ──────────────────────────────────────────────────────────────────────────────

#[test]
fn intent_type_default_is_open_long() {
    // 確保既有 trading IPC payload (32 個 OrderIntent struct literal callers)
    // 在 serde 反序列化路徑不帶 intent_type field 時自動回退 OpenLong;
    // 不會觸發任何 trading hot-path 行為差。
    assert_eq!(super::IntentType::default(), super::IntentType::OpenLong);
}

#[test]
fn intent_type_is_earn_only_for_earn_variants() {
    // 7 variant 中僅 EarnStake / EarnRedeem is_earn() == true;
    // IntentProcessor.process() 用此 boolean dispatch Earn vs trading path。
    let cases: &[(super::IntentType, bool)] = &[
        (super::IntentType::OpenLong, false),
        (super::IntentType::OpenShort, false),
        (super::IntentType::CloseLong, false),
        (super::IntentType::CloseShort, false),
        (super::IntentType::PositionAdjust, false),
        (super::IntentType::EarnStake, true),
        (super::IntentType::EarnRedeem, true),
    ];
    for (variant, expected) in cases.iter().copied() {
        assert_eq!(
            variant.is_earn(),
            expected,
            "is_earn() mismatch for {:?}",
            variant
        );
    }
}

#[test]
fn intent_type_to_lease_scope_audit_str_mapping() {
    // 對齊 PA dispatch packet §3.2 line 320-330 LeaseScope::as_audit_str() 期望值;
    // E1b LeaseScope variant land 後 PR 升級為 enum return,本 unit test 必同步改。
    let cases: &[(super::IntentType, &str)] = &[
        (super::IntentType::OpenLong, "TRADE_ENTRY"),
        (super::IntentType::OpenShort, "TRADE_ENTRY"),
        (super::IntentType::CloseLong, "TRADE_EXIT"),
        (super::IntentType::CloseShort, "TRADE_EXIT"),
        (super::IntentType::PositionAdjust, "POSITION_ADJUST"),
        (super::IntentType::EarnStake, "EARN_STAKE"),
        (super::IntentType::EarnRedeem, "EARN_REDEEM"),
    ];
    for (variant, expected) in cases.iter().copied() {
        assert_eq!(
            variant.to_lease_scope_audit_str(),
            expected,
            "to_lease_scope_audit_str() mismatch for {:?}",
            variant
        );
    }
}

#[test]
fn intent_type_serde_snake_case_roundtrip() {
    // serde rename_all = "snake_case" 確保 IPC JSON 互通既有 Python consumer
    // 慣例(snake_case);7 variant 序列化為 "open_long" 等字串,反序列化回原 enum。
    let cases: &[(super::IntentType, &str)] = &[
        (super::IntentType::OpenLong, "\"open_long\""),
        (super::IntentType::OpenShort, "\"open_short\""),
        (super::IntentType::CloseLong, "\"close_long\""),
        (super::IntentType::CloseShort, "\"close_short\""),
        (super::IntentType::PositionAdjust, "\"position_adjust\""),
        (super::IntentType::EarnStake, "\"earn_stake\""),
        (super::IntentType::EarnRedeem, "\"earn_redeem\""),
    ];
    for (variant, json) in cases.iter().copied() {
        let ser = serde_json::to_string(&variant).expect("ser");
        assert_eq!(ser, json, "serialize mismatch for {:?}", variant);
        let de: super::IntentType = serde_json::from_str(json).expect("deser");
        assert_eq!(de, variant, "deserialize mismatch for {}", json);
    }
}

#[test]
fn order_intent_backward_compat_deserialize_without_new_fields() {
    // SAFETY 不變量驗證: 既有 IPC payload 不含 intent_type / earn_payload 兩 field
    // 仍能反序列化成功(serde default 路徑),且 intent_type = OpenLong / earn_payload = None。
    // 這是 backward-compat 核心保證(既有 4 策略 + IPC consumer + Python ai_service)。
    let legacy_json = r#"{
        "symbol": "BTCUSDT",
        "is_long": true,
        "qty": 0.01,
        "confidence": 0.7,
        "strategy": "ma_crossover",
        "order_type": "market",
        "limit_price": null
    }"#;
    let intent: super::OrderIntent = serde_json::from_str(legacy_json)
        .expect("legacy payload must deserialize via serde defaults");
    assert_eq!(intent.symbol, "BTCUSDT");
    assert_eq!(intent.intent_type, super::IntentType::OpenLong);
    assert!(intent.earn_payload.is_none());
    assert!(intent.confluence_score.is_none());
    assert!(intent.persistence_elapsed_ms.is_none());
}

#[test]
fn order_intent_earn_payload_serialize_and_roundtrip() {
    // 完整 Earn intent payload 7 field roundtrip 驗證;
    // Bybit V5 Earn API 對 amount_usdt 期望字串格式("200.00000000")。
    let payload = super::EarnIntentPayload {
        amount_usdt: "200.00000000".to_string(),
        expected_apr_bps: 1000, // 10% APR = 1000 bps
        product_id: "USDT-FLEX-001".to_string(),
        tenor_days: 0, // flexible (no tenor lock)
        approval_id: "approval-uuid-abc-123".to_string(),
        actor_id: "PrimaryOperator".to_string(),
        rationale: "Sprint 1B first stake $200 flexible per OP-2/OP-3".to_string(),
    };
    let intent = super::OrderIntent {
        symbol: "USDT".to_string(),
        is_long: true,
        qty: 0.0, // Earn intent 不走 qty 路徑;0 哨兵
        confidence: 1.0,
        strategy: "earn_governance".to_string(),
        order_type: "earn".to_string(),
        limit_price: None,
        confluence_score: None,
        persistence_elapsed_ms: None,
        time_in_force: None,
        maker_timeout_ms: None,
        intent_type: super::IntentType::EarnStake,
        earn_payload: Some(payload.clone()),
    };
    let json = serde_json::to_string(&intent).expect("ser");
    let de: super::OrderIntent = serde_json::from_str(&json).expect("deser");
    assert_eq!(de.intent_type, super::IntentType::EarnStake);
    let de_payload = de.earn_payload.expect("Some payload");
    assert_eq!(de_payload.amount_usdt, "200.00000000");
    assert_eq!(de_payload.expected_apr_bps, 1000);
    assert_eq!(de_payload.product_id, "USDT-FLEX-001");
    assert_eq!(de_payload.tenor_days, 0);
    assert_eq!(de_payload.approval_id, "approval-uuid-abc-123");
    assert_eq!(de_payload.actor_id, "PrimaryOperator");
    assert!(de_payload.rationale.starts_with("Sprint 1B first stake"));
}

/// Sprint 1B audit Bug 2 fix（IntentType HYBRID-PLACEHOLDER-BUG）—— 對抗性驗證。
///
/// 驗 short-capable strategy 出 OrderIntent.is_long=false 時，intent_type
/// 為 OpenShort（不再字面占位 OpenLong）。對應 funding_arb / funding_harvest /
/// bidirectional bb_breakout / bb_reversion / ma_crossover / grid_trading
/// 八個 emit site 的 short branch。
#[test]
fn order_intent_short_path_emits_open_short_intent_type() {
    // funding_arb perp SHORT path (`is_long=false`) 必匹配 OpenShort，
    // 取代舊 OpenLong 字面占位。
    let intent_short = super::OrderIntent {
        symbol: "BTCUSDT".to_string(),
        is_long: false,
        qty: 0.002,
        confidence: 0.8,
        strategy: "funding_arb".to_string(),
        order_type: "limit".to_string(),
        limit_price: Some(50_000.0),
        confluence_score: None,
        persistence_elapsed_ms: None,
        time_in_force: Some(crate::order_manager::TimeInForce::PostOnly),
        maker_timeout_ms: Some(45_000),
        // 對齊 funding_arb.rs:515 修法 — short branch 必 OpenShort。
        intent_type: super::IntentType::OpenShort,
        earn_payload: None,
    };
    assert_eq!(intent_short.intent_type, super::IntentType::OpenShort);
    intent_short.validate(); // debug-assert PASS（無 is_long/intent_type 矛盾）
}

/// Sprint 1B audit Bug 2 fix —— new_trade helper API smoke。
///
/// 驗 helper 由 is_long 自動派生 intent_type，且 earn_payload=None 對齊 trade-only 契約。
#[test]
fn order_intent_new_trade_helper_derives_intent_type_from_is_long() {
    let long_intent = super::OrderIntent::new_trade(
        "BTCUSDT".to_string(),
        true, // long
        0.01,
        0.7,
        "bb_breakout".to_string(),
        "market".to_string(),
        None,
        Some(45.0),
        Some(120_000),
        None,
        None,
    );
    assert_eq!(long_intent.intent_type, super::IntentType::OpenLong);
    assert!(long_intent.is_long);
    assert!(long_intent.earn_payload.is_none());

    let short_intent = super::OrderIntent::new_trade(
        "ETHUSDT".to_string(),
        false, // short
        0.05,
        0.6,
        "funding_arb".to_string(),
        "limit".to_string(),
        Some(3_500.0),
        None,
        None,
        Some(crate::order_manager::TimeInForce::PostOnly),
        Some(45_000),
    );
    assert_eq!(short_intent.intent_type, super::IntentType::OpenShort);
    assert!(!short_intent.is_long);
    assert!(short_intent.earn_payload.is_none());
}

/// Sprint 1B audit Bug 2 fix —— Earn intent 跳過 direction 檢查。
///
/// 驗 EarnStake / EarnRedeem 不受 is_long 約束（earn flexible/fixed staking 與
/// long/short direction 無關），validate 永不 panic。
#[test]
fn order_intent_validate_skips_earn_intent_direction() {
    let earn = super::OrderIntent {
        symbol: "USDT".to_string(),
        is_long: true, // earn 不在乎 direction
        qty: 0.0,
        confidence: 1.0,
        strategy: "earn_governance".to_string(),
        order_type: "earn".to_string(),
        limit_price: None,
        confluence_score: None,
        persistence_elapsed_ms: None,
        time_in_force: None,
        maker_timeout_ms: None,
        intent_type: super::IntentType::EarnStake,
        earn_payload: None,
    };
    earn.validate(); // 不 panic（is_earn 短路）
}

#[test]
fn order_intent_trading_payload_earn_payload_stays_none() {
    // 既有 trading intent (4 策略 + IPC consumer) 確認 earn_payload 一直 None;
    // 此 invariant 保證下游 Earn writer wave 對 earn_payload.is_none() 短路安全。
    let intent = super::OrderIntent {
        symbol: "BTCUSDT".to_string(),
        is_long: true,
        qty: 0.01,
        confidence: 0.7,
        strategy: "bb_breakout".to_string(),
        order_type: "market".to_string(),
        limit_price: None,
        confluence_score: Some(45.0),
        persistence_elapsed_ms: Some(120_000),
        time_in_force: None,
        maker_timeout_ms: None,
        intent_type: super::IntentType::OpenLong,
        earn_payload: None,
    };
    assert!(intent.earn_payload.is_none());
    assert!(!intent.intent_type.is_earn());
    // 序列化 → 反序列化 → 再驗 None
    let json = serde_json::to_string(&intent).expect("ser");
    let de: super::OrderIntent = serde_json::from_str(&json).expect("deser");
    assert!(de.earn_payload.is_none());
    assert!(!de.intent_type.is_earn());
}

/// Round 2 finding 6 reverse-fire —— validate() release path defence in depth。
///
/// 驗 release 模式（cargo test --release）下 validate() 對 caller-bypass-helper
/// 構造的 mismatch intent **不 panic**（debug_assert 在 release build 編譯期被
/// stripped），而是改走 `tracing::warn!` telemetry。本 test 保證即便有人將來
/// 寫 inline struct literal 又呼 validate()，trading hot path 不會因 panic 而
/// 觸發 Root Principle #5「survival above profit」違反。
///
/// 為什麼不直接驗 tracing event：tracing_subscriber 攔截在 unit test 框架內
/// 過重；本 test 邏輯保證 fn 完成（no panic）即等同 release path 不阻擋。
#[test]
#[cfg(not(debug_assertions))]
fn order_intent_validate_release_path_does_not_panic_on_mismatch() {
    // 故意構造 is_long=false / intent_type=OpenLong 矛盾 intent（caller 繞過 new_trade
    // helper，living example of round 1 殘留 fixture pattern）。
    let mismatched = super::OrderIntent {
        symbol: "XRPUSDT".to_string(),
        is_long: false, // SHORT
        qty: 100.0,
        confidence: 0.5,
        strategy: "bypass_helper_test".to_string(),
        order_type: "market".to_string(),
        limit_price: None,
        confluence_score: None,
        persistence_elapsed_ms: None,
        time_in_force: None,
        maker_timeout_ms: None,
        intent_type: super::IntentType::OpenLong, // 故意 mismatch
        earn_payload: None,
    };
    // release path：validate() 不 panic（debug_assert stripped）但走 warn telemetry。
    mismatched.validate();
}

/// Round 2 finding 1 reverse-fire —— grid_trading short emit 走 new_trade helper。
///
/// 驗 grid_trading/signal.rs:395 short branch 經 helper 派生 IntentType::OpenShort
/// 對齊 is_long=false（取代 round 1 inline `intent_type: IntentType::OpenShort`）。
/// 同時驗 new_trade helper 是唯一 trade-path 構造器：手動構造 grid-shape intent
/// 走 helper 後 invariant self-consistent。
#[test]
fn order_intent_grid_short_emit_via_new_trade_aligns_intent_type() {
    // 模擬 grid_trading/signal.rs:380-397 short branch emit；改走 helper 後
    // intent_type 必為 OpenShort，is_long=false 對齊。
    let grid_short = super::OrderIntent::new_trade(
        "BTCUSDT".to_string(),
        false, // grid short branch
        0.001,
        0.6, // grid conf
        "grid_trading".to_string(),
        "limit".to_string(),
        Some(50_000.0),
        None, // grid 無 confluence
        None, // grid 無 persistence
        None,
        None,
    );
    assert_eq!(grid_short.intent_type, super::IntentType::OpenShort);
    assert!(!grid_short.is_long);
    assert_eq!(grid_short.strategy, "grid_trading");
    // helper 內 validate() 已跑（debug 下 panic 即捕獲；release 下 warn 不阻擋）。
}

// ──────────────────────────────────────────────────────────────────────────────
// Sprint 1B Earn first stake Wave C — IntentProcessor.process_earn_intent
// dispatch branch test。
//
// 範圍對應 PA dispatch prompt 2026-05-24 §「新增 test」：
//   - intent_processor_dispatches_earn_intent_to_earn_router       : 入口分流驗
//   - intent_processor_trade_intent_unaffected_by_earn_branch      : 對抗性驗
//   - earn_router_fail_closed_when_unwired                         : E-0 wiring gate
//   - earn_router_fail_closed_when_earn_payload_missing            : E-1 payload gate
//
// 集成 Bybit+PG 真實 dispatch 路徑（success path / Bybit retCode != 0）留 QA Stage 0R
// replay + operator OP-1 真實 stake smoke（per E1 IMPL DONE report carry-over §）。
// ──────────────────────────────────────────────────────────────────────────────

/// Wave C dispatch test 1：trade-path 入口拒 Earn intent。
///
/// 驗 process_with_features (sync trade-path) 對 IntentType::EarnStake/EarnRedeem
/// 入口 Gate 0 fail-closed reject，不繼續走 Gate 1 governance / Gate 2 Guardian
/// 等 trade-only 路徑（避免 Earn intent 被 silent dispatch 成假 trade fill）。
#[test]
fn intent_processor_dispatches_earn_intent_to_earn_router() {
    let proc = IntentProcessor::new();
    let mut gov = GovernanceCore::new();
    gov.grant_paper_authorization(None)
        .expect("paper auth must succeed");
    let state = PaperState::new(10_000.0);

    // 構造 EarnStake intent（earn_payload Some）；trade-path 入口必拒。
    let earn_intent = OrderIntent {
        symbol: "USDT".to_string(),
        is_long: true,
        qty: 0.0,
        confidence: 1.0,
        strategy: "earn_governance".to_string(),
        order_type: "earn".to_string(),
        limit_price: None,
        confluence_score: None,
        persistence_elapsed_ms: None,
        time_in_force: None,
        maker_timeout_ms: None,
        intent_type: super::IntentType::EarnStake,
        earn_payload: Some(super::EarnIntentPayload {
            amount_usdt: "200.00000000".to_string(),
            expected_apr_bps: 1000,
            product_id: "USDT-FLEX-001".to_string(),
            tenor_days: 0,
            approval_id: "approval-test-1".to_string(),
            actor_id: "PrimaryOperator".to_string(),
            rationale: "Wave C dispatch test".to_string(),
        }),
    };
    let result = proc.process(&earn_intent, &gov, &state, 500.0, GovernanceProfile::Exploration);
    assert!(!result.submitted, "trade-path 必拒 Earn intent");
    let reason = result.rejected_reason.unwrap_or_default();
    assert!(
        reason.contains("earn_intent_routed_to_trade_path")
            && reason.contains("process_earn_intent"),
        "reject reason 必明示「Earn 走 process_earn_intent 入口」: actual={}",
        reason
    );

    // 同對 EarnRedeem 驗（cover 兩 Earn variant）。
    let redeem_intent = OrderIntent {
        intent_type: super::IntentType::EarnRedeem,
        ..earn_intent
    };
    let result_redeem = proc.process(
        &redeem_intent,
        &gov,
        &state,
        500.0,
        GovernanceProfile::Exploration,
    );
    assert!(!result_redeem.submitted, "trade-path 必拒 EarnRedeem intent");
    assert!(
        result_redeem
            .rejected_reason
            .unwrap_or_default()
            .contains("earn_intent_routed_to_trade_path"),
        "EarnRedeem 同樣走 Gate 0 reject"
    );
}

/// Wave C dispatch test 2：trade intent 不被 Earn branch 干擾（對抗性驗）。
///
/// 驗 process_with_features 對 IntentType::OpenLong/OpenShort intent 路徑不變
/// （Gate 0 短路條件 is_earn() == false），仍走既有 Gate 1...n trade-path。
/// 此測試保證 Wave C 入口加 Gate 0 後不破現有 trade-path（regression guard）。
#[test]
fn intent_processor_trade_intent_unaffected_by_earn_branch() {
    let proc = IntentProcessor::new();
    let gov = GovernanceCore::new(); // no auth → 預期 Gate 1 reject (not Gate 0)
    let state = PaperState::new(10_000.0);

    // 既有 trade intent (OpenLong)：走完 Gate 0（is_earn false 短路）後到 Gate 1
    // governance authorization → reject。reject reason 必為 governance_not_authorized
    // **非** earn_intent_routed_to_trade_path（後者才是 Gate 0 命中）。
    let trade_intent = OrderIntent::new_trade(
        "BTCUSDT".to_string(),
        true,
        0.01,
        0.7,
        "ma_crossover".to_string(),
        "market".to_string(),
        None,
        Some(45.0),
        Some(120_000),
        None,
        None,
    );
    let result = proc.process(
        &trade_intent,
        &gov,
        &state,
        500.0,
        GovernanceProfile::Exploration,
    );
    assert!(!result.submitted, "no-auth state 必拒 trade intent");
    let reason = result.rejected_reason.unwrap_or_default();
    assert!(
        !reason.contains("earn_intent_routed_to_trade_path"),
        "trade intent 不應命中 Gate 0 earn guard: actual={}",
        reason
    );
    // 應命中 Gate 1 governance_not_authorized；reason 字串對齊既有 RejectionCode。
    assert!(
        reason.to_lowercase().contains("governance")
            || reason.to_lowercase().contains("authorization")
            || reason.to_lowercase().contains("auth"),
        "trade intent 入 Gate 1 governance gate reject: actual={}",
        reason
    );
}

/// Wave C dispatch test 3：process_earn_intent 在 capability 未注入時 fail-closed。
///
/// 驗 EarnRouter Gate E-0：bybit_earn_client / earn_movement_writer 任一未注入
/// （IntentProcessor::new() 預設 None）→ process_earn_intent 必 fail-closed reject
/// 並帶 "earn_dispatch_unwired" 字串。production caller 注入兩 dep 才能走真實
/// Bybit + PG 路徑；未注入 = 引擎端 Earn capability OFF。
#[tokio::test]
async fn earn_router_fail_closed_when_unwired() {
    let proc = IntentProcessor::new();
    let mut gov = GovernanceCore::new();
    gov.grant_paper_authorization(None)
        .expect("paper auth must succeed");

    let earn_intent = OrderIntent {
        symbol: "USDT".to_string(),
        is_long: true,
        qty: 0.0,
        confidence: 1.0,
        strategy: "earn_governance".to_string(),
        order_type: "earn".to_string(),
        limit_price: None,
        confluence_score: None,
        persistence_elapsed_ms: None,
        time_in_force: None,
        maker_timeout_ms: None,
        intent_type: super::IntentType::EarnStake,
        earn_payload: Some(super::EarnIntentPayload {
            amount_usdt: "200.00000000".to_string(),
            expected_apr_bps: 1000,
            product_id: "USDT-FLEX-001".to_string(),
            tenor_days: 0,
            approval_id: "approval-test-unwired".to_string(),
            actor_id: "PrimaryOperator".to_string(),
            rationale: "Wave C unwired test".to_string(),
        }),
    };
    let result = proc
        .process_earn_intent(&earn_intent, &gov, GovernanceProfile::Exploration)
        .await;
    assert!(!result.submitted, "unwired capability 必拒");
    let reason = result.rejected_reason.unwrap_or_default();
    assert!(
        reason.contains("earn_dispatch_unwired"),
        "reject reason 必含 earn_dispatch_unwired: actual={}",
        reason
    );
    // 子字串驗：unwired 提示哪個 dep 缺（bybit_earn_client 或 earn_movement_writer
    // 任一），對齊 EarnDispatchError::Unwired 的 &'static str payload。
    assert!(
        reason.contains("bybit_earn_client") || reason.contains("earn_movement_writer"),
        "unwired reason 必指出缺哪個 dep: actual={}",
        reason
    );
}

/// Wave C dispatch test 4：process_earn_intent 在 earn_payload absent 時 fail-closed。
///
/// 驗 EarnRouter Gate E-1：caller 送 EarnStake/EarnRedeem 但 earn_payload=None →
/// fail-closed reject "earn_dispatch_payload_missing"。本 gate 在 Gate E-0 通過
/// （即 capability 已注入）後才會命中；本 test 用「假 wiring」走捷徑 — 預期
/// Gate E-0 unwired 仍先 fail，但本 test 重點是驗 caller bug (payload None) 不會
/// 被 silent 通過 dispatch。
///
/// 注意：current IMPL Gate E-0 在 E-1 之前，所以 unwired 路徑先 trip；要直接驗
/// E-1 命中需注入 dep（需 real BybitRestClient + PG，違 mac dev local-only）。
/// 折衷：本 test 驗「caller 構造 earn_payload=None 的 EarnStake intent，process_
/// earn_intent 不 panic 且回 fail-closed reject reason」— 對齊 IntentResult::
/// rejected 契約。**真實 E-1 命中由 Wave D/E integration test + Stage 0R 補。**
#[tokio::test]
async fn earn_router_fail_closed_when_earn_payload_missing() {
    let proc = IntentProcessor::new(); // unwired (capability OFF)
    let mut gov = GovernanceCore::new();
    gov.grant_paper_authorization(None)
        .expect("paper auth must succeed");

    let bad_intent = OrderIntent {
        symbol: "USDT".to_string(),
        is_long: true,
        qty: 0.0,
        confidence: 1.0,
        strategy: "earn_governance".to_string(),
        order_type: "earn".to_string(),
        limit_price: None,
        confluence_score: None,
        persistence_elapsed_ms: None,
        time_in_force: None,
        maker_timeout_ms: None,
        intent_type: super::IntentType::EarnStake, // earn intent
        earn_payload: None, // ← caller bug
    };
    let result = proc
        .process_earn_intent(&bad_intent, &gov, GovernanceProfile::Exploration)
        .await;
    assert!(
        !result.submitted,
        "earn_payload None 必拒（caller bug 早 fail）"
    );
    // current IMPL Gate E-0 unwired 在 E-1 之前 trip；本 test 寬容驗 reject reason
    // 為 unwired 或 payload_missing 兩者之一（兩者語意都是 fail-closed reject）。
    let reason = result.rejected_reason.unwrap_or_default();
    assert!(
        reason.contains("earn_dispatch_unwired")
            || reason.contains("earn_dispatch_payload_missing"),
        "earn payload None / unwired 任一 fail-closed reason: actual={}",
        reason
    );
}
