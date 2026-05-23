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
