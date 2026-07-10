//! Demo-learning lane hot-path adapter.
//!
//! This module is intentionally pure: it only converts an exchange gate
//! rejection into the learning-lane `RejectEvent` shape. It performs no plan
//! evaluation, no ledger write, no DB/Bybit call, and grants no order authority.

use crate::demo_learning_lane::{
    normalize_reject_reason_code, RejectEvent, ELIGIBLE_REJECT_REASON_CODE,
};
use crate::intent_processor::{IntentType, OrderIntent};

pub fn exchange_gate_reject_event(
    intent: &OrderIntent,
    engine_mode: &str,
    rejected_reason: &str,
    ts_ms: u64,
    context_id: &str,
    signal_id: &str,
) -> Option<RejectEvent> {
    let normalized_engine_mode = engine_mode.trim().to_ascii_lowercase();
    if !matches!(normalized_engine_mode.as_str(), "demo" | "live_demo") {
        return None;
    }

    let normalized_reason = normalize_reject_reason_code(rejected_reason);
    if normalized_reason != ELIGIBLE_REJECT_REASON_CODE {
        return None;
    }
    if ts_ms == 0 || intent.strategy.trim().is_empty() || intent.symbol.trim().is_empty() {
        return None;
    }
    let side = match intent.intent_type {
        IntentType::OpenLong if intent.is_long => "Buy",
        IntentType::OpenShort if !intent.is_long => "Sell",
        _ => return None,
    };

    Some(RejectEvent {
        strategy_name: intent.strategy.trim().to_string(),
        symbol: intent.symbol.trim().to_ascii_uppercase(),
        side: side.to_string(),
        reject_reason_code: normalized_reason,
        engine_mode: normalized_engine_mode,
        ts_ms,
        context_id: non_empty(context_id),
        signal_id: non_empty(signal_id),
        candidate_event_context: None,
    })
}

fn non_empty(value: &str) -> Option<String> {
    let trimmed = value.trim();
    if trimmed.is_empty() {
        None
    } else {
        Some(trimmed.to_string())
    }
}
