use super::config::AgentSpineMode;
use super::contracts::{StrategySignalDirection, STRATEGY_SIGNAL_SCHEMA_VERSION};
use super::signal_adapter::{strategy_signal_from_open_intent, strategy_signal_to_trading_msg};
use crate::database::TradingMsg;
use crate::intent_processor::OrderIntent;
use crate::order_manager::TimeInForce;
use std::str::FromStr;

fn sample_intent(is_long: bool) -> OrderIntent {
    OrderIntent {
        symbol: "BTCUSDT".to_string(),
        is_long,
        qty: 1.25,
        confidence: 0.72,
        strategy: "grid_trading".to_string(),
        order_type: "limit".to_string(),
        limit_price: Some(101.25),
        confluence_score: Some(33.0),
        persistence_elapsed_ms: Some(42_000),
        time_in_force: Some(TimeInForce::PostOnly),
        maker_timeout_ms: Some(90_000),
    }
}

#[test]
fn agent_spine_mode_defaults_disabled_and_shadow_is_non_enforcing() {
    assert_eq!(AgentSpineMode::default(), AgentSpineMode::Disabled);
    assert!(!AgentSpineMode::Disabled.writes_enabled());
    assert!(AgentSpineMode::Shadow.writes_enabled());
    assert!(!AgentSpineMode::Shadow.enforces_new_exposure());
    assert!(!AgentSpineMode::Shadow.store_error_blocks_new_exposure());
    assert!(AgentSpineMode::Primary.enforces_new_exposure());
    assert!(AgentSpineMode::Primary.store_error_blocks_new_exposure());
    assert_eq!(
        AgentSpineMode::from_str("canary").unwrap(),
        AgentSpineMode::Canary
    );
    assert!(AgentSpineMode::from_str("legacy_gate").is_err());
}

#[test]
fn open_intent_maps_to_typed_strategy_signal_without_execution_authority() {
    let signal = strategy_signal_from_open_intent(
        "sig-paper-grid_trading-BTCUSDT-123",
        "ctx-paper-BTCUSDT-123",
        123,
        "paper",
        &sample_intent(true),
    );

    assert_eq!(signal.schema_version, STRATEGY_SIGNAL_SCHEMA_VERSION);
    assert_eq!(signal.signal_id, "sig-paper-grid_trading-BTCUSDT-123");
    assert_eq!(signal.context_id.as_deref(), Some("ctx-paper-BTCUSDT-123"));
    assert_eq!(signal.engine_mode, "paper");
    assert_eq!(signal.symbol, "BTCUSDT");
    assert_eq!(signal.strategy, "grid_trading");
    assert_eq!(signal.direction, StrategySignalDirection::Long);
    assert_eq!(signal.raw_signal_strength, 0.72);
    assert_eq!(signal.confidence, 0.72);
    assert_eq!(signal.order_type.as_deref(), Some("limit"));
    assert_eq!(signal.limit_price, Some(101.25));
    assert_eq!(signal.time_in_force.as_deref(), Some("PostOnly"));
    assert_eq!(signal.maker_timeout_ms, Some(90_000));
    assert_eq!(signal.evidence_refs, vec!["ctx-paper-BTCUSDT-123"]);

    let json = serde_json::to_value(&signal).unwrap();
    assert!(json.get("decision_id").is_none());
    assert!(json.get("verdict_id").is_none());
    assert!(json.get("order_plan_id").is_none());
    assert!(json.get("lease_id").is_none());
}

#[test]
fn typed_strategy_signal_preserves_legacy_trading_signal_persistence_shape() {
    let signal = strategy_signal_from_open_intent(
        "sig-live_demo-grid_trading-BTCUSDT-456",
        "ctx-live_demo-BTCUSDT-456",
        456,
        "live_demo",
        &sample_intent(false),
    );

    let msg = strategy_signal_to_trading_msg(&signal);

    match msg {
        TradingMsg::Signal {
            signal_id,
            ts_ms,
            symbol,
            strategy_name,
            timeframe,
            signal_type,
            strength,
            context_id,
        } => {
            assert_eq!(signal_id, "sig-live_demo-grid_trading-BTCUSDT-456");
            assert_eq!(ts_ms, 456);
            assert_eq!(symbol, "BTCUSDT");
            assert_eq!(strategy_name, "grid_trading");
            assert_eq!(timeframe, "1m");
            assert_eq!(signal_type, "OpenShort");
            assert_eq!(strength, 0.72);
            assert_eq!(context_id, "ctx-live_demo-BTCUSDT-456");
        }
        other => panic!("expected TradingMsg::Signal, got {other:?}"),
    }
}
