//! Strategy output to `StrategySignal` adapter.

use super::contracts::{StrategySignal, StrategySignalDirection, STRATEGY_SIGNAL_SCHEMA_VERSION};
use crate::database::TradingMsg;
use crate::intent_processor::OrderIntent;

/// Build a typed Agent Spine StrategySignal from an existing Rust open intent.
pub fn strategy_signal_from_open_intent(
    signal_id: &str,
    context_id: &str,
    ts_ms: u64,
    engine_mode: &str,
    intent: &OrderIntent,
) -> StrategySignal {
    StrategySignal {
        schema_version: STRATEGY_SIGNAL_SCHEMA_VERSION.to_string(),
        signal_id: signal_id.to_string(),
        ts_ms,
        engine_mode: engine_mode.to_string(),
        symbol: intent.symbol.clone(),
        strategy: intent.strategy.clone(),
        direction: if intent.is_long {
            StrategySignalDirection::Long
        } else {
            StrategySignalDirection::Short
        },
        raw_signal_strength: intent.confidence,
        expected_edge_bps: None,
        expected_cost_bps: None,
        confidence: intent.confidence,
        regime: None,
        scanner_candidate_id: None,
        scanner_decay_id: None,
        context_id: Some(context_id.to_string()),
        evidence_refs: vec![context_id.to_string()],
        invalidation: None,
        order_type: Some(intent.order_type.clone()),
        limit_price: intent.limit_price,
        time_in_force: intent.time_in_force.map(|tif| tif.as_str().to_string()),
        maker_timeout_ms: intent.maker_timeout_ms,
    }
}

/// Downgrade a typed StrategySignal to the legacy `trading.signals` row shape.
///
/// MAG-032 will add the dedicated spine store. Until then this preserves the
/// existing persistence contract while making the hot path build the typed
/// signal first.
pub fn strategy_signal_to_trading_msg(signal: &StrategySignal) -> TradingMsg {
    TradingMsg::Signal {
        signal_id: signal.signal_id.clone(),
        ts_ms: signal.ts_ms,
        symbol: signal.symbol.clone(),
        strategy_name: signal.strategy.clone(),
        timeframe: "1m".to_string(),
        signal_type: signal.trading_signal_type().to_string(),
        strength: signal.confidence,
        context_id: signal.context_id.clone().unwrap_or_default(),
    }
}

pub fn trading_msg_from_open_intent(
    signal_id: &str,
    context_id: &str,
    ts_ms: u64,
    engine_mode: &str,
    intent: &OrderIntent,
) -> TradingMsg {
    let signal =
        strategy_signal_from_open_intent(signal_id, context_id, ts_ms, engine_mode, intent);
    strategy_signal_to_trading_msg(&signal)
}
