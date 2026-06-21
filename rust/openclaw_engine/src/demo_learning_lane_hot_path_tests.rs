use crate::demo_learning_lane::{side_cell_key, ELIGIBLE_REJECT_REASON_CODE};
use crate::demo_learning_lane_hot_path::exchange_gate_reject_event;
use crate::intent_processor::{IntentType, OrderIntent};

fn intent(symbol: &str, is_long: bool) -> OrderIntent {
    OrderIntent {
        symbol: symbol.to_string(),
        is_long,
        qty: 0.1,
        confidence: 0.72,
        strategy: "ma_crossover".to_string(),
        order_type: "market".to_string(),
        limit_price: None,
        confluence_score: None,
        persistence_elapsed_ms: None,
        time_in_force: None,
        maker_timeout_ms: None,
        intent_type: if is_long {
            IntentType::OpenLong
        } else {
            IntentType::OpenShort
        },
        earn_payload: None,
    }
}

#[test]
fn builds_reject_event_for_demo_cost_gate_negative_reason() {
    let event = exchange_gate_reject_event(
        &intent("ethusdt", false),
        "Live_Demo",
        "cost_gate(JS-demo): negative edge -12.7 bps blocked",
        1_782_041_000_000,
        "ctx-live_demo-ETHUSDT-1782041000000",
        "sig-live_demo-ma_crossover-ETHUSDT-1782041000000",
    )
    .expect("eligible demo/live_demo cost-gate negative reject should produce event");

    assert_eq!(event.strategy_name, "ma_crossover");
    assert_eq!(event.symbol, "ETHUSDT");
    assert_eq!(event.side, "Sell");
    assert_eq!(event.reject_reason_code, ELIGIBLE_REJECT_REASON_CODE);
    assert_eq!(event.engine_mode, "live_demo");
    assert_eq!(event.ts_ms, 1_782_041_000_000);
    assert_eq!(
        event.context_id.as_deref(),
        Some("ctx-live_demo-ETHUSDT-1782041000000")
    );
    assert_eq!(
        event.signal_id.as_deref(),
        Some("sig-live_demo-ma_crossover-ETHUSDT-1782041000000")
    );
    assert_eq!(
        event.side_cell_key(),
        side_cell_key("ma_crossover", "ETHUSDT", "Sell")
    );
}

#[test]
fn hot_path_adapter_rejects_non_demo_or_non_cost_gate_reason() {
    assert!(exchange_gate_reject_event(
        &intent("ETHUSDT", false),
        "live",
        "cost_gate(JS-demo): negative edge -12.7 bps blocked",
        1_782_041_000_000,
        "ctx",
        "sig",
    )
    .is_none());

    assert!(exchange_gate_reject_event(
        &intent("ETHUSDT", false),
        "demo",
        "risk_gate:max_notional_exceeded",
        1_782_041_000_000,
        "ctx",
        "sig",
    )
    .is_none());
}

#[test]
fn hot_path_adapter_preserves_fallback_identifiers_without_empty_strings() {
    let event = exchange_gate_reject_event(
        &intent("nearusdt", true),
        "demo",
        ELIGIBLE_REJECT_REASON_CODE,
        1_782_041_111_000,
        " ",
        "sig-demo-ma_crossover-NEARUSDT-1782041111000",
    )
    .expect("signal id fallback should remain valid");

    assert_eq!(event.side, "Buy");
    assert!(event.context_id.is_none());
    assert_eq!(
        event.signal_id.as_deref(),
        Some("sig-demo-ma_crossover-NEARUSDT-1782041111000")
    );
}

#[test]
fn hot_path_adapter_requires_entry_intent_type_side_consistency() {
    let mut close_intent = intent("ETHUSDT", true);
    close_intent.intent_type = IntentType::CloseLong;
    assert!(exchange_gate_reject_event(
        &close_intent,
        "demo",
        ELIGIBLE_REJECT_REASON_CODE,
        1_782_041_000_000,
        "ctx",
        "sig",
    )
    .is_none());

    let mut mismatched_side = intent("ETHUSDT", true);
    mismatched_side.intent_type = IntentType::OpenShort;
    assert!(exchange_gate_reject_event(
        &mismatched_side,
        "demo",
        ELIGIBLE_REJECT_REASON_CODE,
        1_782_041_000_000,
        "ctx",
        "sig",
    )
    .is_none());
}

#[test]
fn hot_path_adapter_drops_malformed_event_identity() {
    let mut no_strategy = intent("ETHUSDT", false);
    no_strategy.strategy.clear();
    assert!(exchange_gate_reject_event(
        &no_strategy,
        "demo",
        ELIGIBLE_REJECT_REASON_CODE,
        1_782_041_000_000,
        "ctx",
        "sig",
    )
    .is_none());

    assert!(exchange_gate_reject_event(
        &intent("ETHUSDT", false),
        "demo",
        ELIGIBLE_REJECT_REASON_CODE,
        0,
        "ctx",
        "sig",
    )
    .is_none());
}
