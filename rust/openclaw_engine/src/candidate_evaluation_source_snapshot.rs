//! Typed, immutable same-tick inputs retained for later candidate evaluation.
//! This schema carries no evaluation, proof, training, promotion, or order authority.

use crate::candidate_event_context::{
    canonical_sha256, CandidateEventContextV1, CANDIDATE_EVENT_CONTEXT_SCHEMA_VERSION,
    CAPTURE_COMPLETE_STATUS as EVENT_CAPTURE_COMPLETE_STATUS,
};
use crate::edge_predictor::features::{
    feature_definition_hash, feature_schema_hash, FeatureVectorV1, FEATURE_NAMES_V1,
    FEATURE_SCHEMA_VERSION,
};
use crate::intent_processor::OrderIntent;
use crate::paper_state::PaperState;
use openclaw_core::indicators::IndicatorSnapshot;
use openclaw_types::PriceEvent;
use serde::{Deserialize, Serialize};

pub const CANDIDATE_EVALUATION_SOURCE_SNAPSHOT_SCHEMA_VERSION: &str =
    "candidate_evaluation_source_snapshot_v1";
pub const CANDIDATE_EVALUATION_SOURCE_CAPTURE_COMPLETE_STATUS: &str = "CAPTURE_COMPLETE";
pub const CANDIDATE_EVALUATION_SOURCE_CAPTURE_BLOCKED_STATUS: &str = "CAPTURE_BLOCKED";
pub const CANDIDATE_EVALUATION_SOURCE_SNAPSHOT_BOUNDARY: &str =
    "immutable candidate evaluation source only; no evaluation, proof, training, promotion, order, lease, gate, config, broker, or runtime authority";
pub(crate) const CANDIDATE_EVALUATION_FEATURE_SOURCES_V1: [&str; FeatureVectorV1::DIM] = [
    "indicator_snapshot.adx.adx",
    "indicator_snapshot.bollinger.bandwidth",
    "tick.atr_value+price_event.last_price",
    "price_event.funding_rate",
    "indicator_snapshot.ewma_vol.ewma_vol",
    "price_event.index_price+price_event.last_price",
    "price_event.bids5+price_event.asks5",
    "price_event.bid_price+price_event.ask_price",
    "order_intent.confluence_score",
    "order_intent.persistence_elapsed_ms",
    "order_intent.is_long",
    "order_intent.qty+price_event.last_price+paper_state.balance",
    "paper_state.positions.count",
    "paper_state.positions.same_direction_count",
    "price_event.ts_ms.utc_hour_sin",
    "price_event.ts_ms.utc_hour_cos",
    "price_event.ts_ms.funding_settlement_window",
];

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CandidateEvaluationSourceSnapshotV1 {
    pub schema_version: String,
    pub captured_at_ms: u64,
    pub event_hash: String,
    pub scan: Option<CandidateEvaluationScanSourceV1>,
    pub decision_features: CandidateEvaluationFeatureSourceV1,
    pub portfolio: CandidateEvaluationPortfolioSourceV1,
    pub capture_status: String,
    pub capture_blockers: Vec<String>,
    pub snapshot_hash: String,
    pub boundary: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CandidateEvaluationScanSourceV1 {
    pub scan_id: String,
    pub scan_ts_ms: u64,
    pub symbol: String,
    pub sector: Option<String>,
    pub turnover_24h: Option<f64>,
    pub beta_proxy: Option<f64>,
    pub beta_proxy_status: CandidateEvaluationBetaProxyStatusV1,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CandidateEvaluationBetaProxyStatusV1 {
    Observed,
    UnavailableBtcMove,
    Invalid,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CandidateEvaluationFeatureSourceV1 {
    pub schema_version: String,
    pub schema_hash: String,
    pub definition_hash: String,
    pub observations: Vec<CandidateEvaluationFeatureObservationV1>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CandidateEvaluationFeatureObservationV1 {
    pub name: String,
    pub value: Option<f64>,
    pub raw_present: bool,
    pub source: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CandidateEvaluationPortfolioSourceV1 {
    pub portfolio_snapshot_hash: Option<String>,
    pub accepted_demo_equity_usdt: Option<f64>,
    pub positions: Vec<CandidateEvaluationPositionV1>,
    pub position_count: Option<usize>,
    pub gross_mark_notional_usdt: Option<f64>,
    pub net_mark_notional_usdt: Option<f64>,
    pub empty_position_attestation: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CandidateEvaluationPositionV1 {
    pub symbol: String,
    pub side: String,
    pub quantity: Option<f64>,
    pub mark_source: String,
    pub mark_price: Option<f64>,
    pub mark_notional_usdt: Option<f64>,
    pub owner_strategy: String,
    pub entry_context_id: String,
}

fn sorted_dedup(mut blockers: Vec<String>) -> Vec<String> {
    blockers.sort_unstable();
    blockers.dedup();
    blockers
}

fn hash_without_field<T: Serialize>(value: &T, field: &str) -> Option<String> {
    let mut value = serde_json::to_value(value).ok()?;
    value.as_object_mut()?.remove(field)?;
    Some(canonical_sha256(&value))
}

fn bound_event_hash(event_context: &CandidateEventContextV1) -> Option<String> {
    hash_without_field(event_context, "event_hash")
}

/// Canonical SHA-256 over every snapshot field except `snapshot_hash` itself.
pub fn candidate_evaluation_source_snapshot_hash(
    snapshot: &CandidateEvaluationSourceSnapshotV1,
) -> Option<String> {
    hash_without_field(snapshot, "snapshot_hash")
}

fn event_binding_blockers(
    snapshot: &CandidateEvaluationSourceSnapshotV1,
    event_context: &CandidateEventContextV1,
) -> Vec<String> {
    let mut blockers = Vec::new();
    if snapshot.schema_version != CANDIDATE_EVALUATION_SOURCE_SNAPSHOT_SCHEMA_VERSION {
        blockers.push("SNAPSHOT_SCHEMA_VERSION_INVALID".to_string());
    }
    if snapshot.boundary != CANDIDATE_EVALUATION_SOURCE_SNAPSHOT_BOUNDARY {
        blockers.push("SNAPSHOT_BOUNDARY_INVALID".to_string());
    }
    if event_context.schema_version != CANDIDATE_EVENT_CONTEXT_SCHEMA_VERSION
        || event_context.capture_status != EVENT_CAPTURE_COMPLETE_STATUS
        || !event_context.capture_blockers.is_empty()
    {
        blockers.push("BOUND_EVENT_CONTEXT_NOT_COMPLETE".to_string());
    }
    if bound_event_hash(event_context).as_deref() != Some(event_context.event_hash.as_str()) {
        blockers.push("BOUND_EVENT_HASH_INVALID".to_string());
    }
    if snapshot.event_hash != event_context.event_hash {
        blockers.push("EVENT_HASH_MISMATCH".to_string());
    }
    if snapshot.captured_at_ms == 0 || snapshot.captured_at_ms != event_context.captured_at_ms {
        blockers.push("CAPTURED_AT_MISMATCH".to_string());
    }
    sorted_dedup(blockers)
}

fn scan_blockers(
    snapshot: &CandidateEvaluationSourceSnapshotV1,
    event_context: &CandidateEventContextV1,
) -> Vec<String> {
    let mut blockers = Vec::new();
    let Some(scan) = snapshot.scan.as_ref() else {
        return vec!["SCAN_SOURCE_MISSING".to_string()];
    };
    let bound_scan_id = event_context
        .scan_id
        .as_deref()
        .filter(|value| !value.is_empty() && *value == value.trim());
    match bound_scan_id {
        None => blockers.push("BOUND_SCAN_ID_MISSING".to_string()),
        Some(bound_scan_id) if scan.scan_id != bound_scan_id => {
            blockers.push("SCAN_ID_MISMATCH".to_string());
        }
        Some(_) => {}
    }
    if scan.symbol != event_context.symbol {
        blockers.push("SCAN_SYMBOL_MISMATCH".to_string());
    }
    if scan.scan_ts_ms == 0 {
        blockers.push("SCAN_TIMESTAMP_INVALID".to_string());
    } else if scan.scan_ts_ms > snapshot.captured_at_ms {
        blockers.push("SCAN_TIMESTAMP_AFTER_CAPTURE".to_string());
    }
    if !scan
        .sector
        .as_deref()
        .is_some_and(|value| !value.is_empty() && value == value.trim())
    {
        blockers.push("SCAN_SECTOR_MISSING_OR_INVALID".to_string());
    }
    if !scan
        .turnover_24h
        .is_some_and(|value| value.is_finite() && value > 0.0)
    {
        blockers.push("SCAN_TURNOVER_MISSING_OR_INVALID".to_string());
    }
    match (scan.beta_proxy_status, scan.beta_proxy) {
        (CandidateEvaluationBetaProxyStatusV1::Observed, Some(value))
            if value.is_finite() && (-0.5..=3.0).contains(&value) => {}
        (CandidateEvaluationBetaProxyStatusV1::Observed, Some(value)) if value.is_finite() => {
            blockers.push("SCAN_BETA_PROXY_OUT_OF_RANGE".to_string());
        }
        (CandidateEvaluationBetaProxyStatusV1::UnavailableBtcMove, None) => {}
        _ => blockers.push("SCAN_BETA_PROXY_INVALID".to_string()),
    }
    sorted_dedup(blockers)
}

fn feature_value_in_declared_range(name: &str, value: f64) -> Option<bool> {
    let in_range = match name {
        "adx_1h" => (0.0..=100.0).contains(&value),
        "bb_width_pct" => (0.0..=50.0).contains(&value),
        "atr_pct" | "realized_vol_1h" => (0.0..=20.0).contains(&value),
        "funding_rate" => (-0.01..=0.01).contains(&value),
        "basis_bps" => (-500.0..=500.0).contains(&value),
        "orderbook_imbalance_top5" | "tod_sin" | "tod_cos" => (-1.0..=1.0).contains(&value),
        "spread_bps" => (0.0..=1_000.0).contains(&value),
        "confluence_score" => (0.0..=65.0).contains(&value),
        "persistence_elapsed_ms" => (0.0..=3_600_000.0).contains(&value),
        "side" => value == -1.0 || value == 1.0,
        "notional_pct_of_bal" => (0.0..=100.0).contains(&value),
        "concurrent_positions" | "same_direction_cnt" => {
            (0.0..=100.0).contains(&value) && value.fract() == 0.0
        }
        "is_funding_settlement_window" => value == 0.0 || value == 1.0,
        _ => return None,
    };
    Some(in_range)
}

fn feature_blockers(snapshot: &CandidateEvaluationSourceSnapshotV1) -> Vec<String> {
    let features = &snapshot.decision_features;
    let mut blockers = Vec::new();
    if features.schema_version != FEATURE_SCHEMA_VERSION {
        blockers.push("FEATURE_SCHEMA_VERSION_INVALID".to_string());
    }
    if features.schema_hash != feature_schema_hash() {
        blockers.push("FEATURE_SCHEMA_HASH_MISMATCH".to_string());
    }
    if features.definition_hash != feature_definition_hash() {
        blockers.push("FEATURE_DEFINITION_HASH_MISMATCH".to_string());
    }
    if features.observations.len() != FEATURE_NAMES_V1.len() {
        blockers.push("FEATURE_OBSERVATION_COUNT_INVALID".to_string());
    } else if features
        .observations
        .iter()
        .map(|observation| observation.name.as_str())
        .ne(FEATURE_NAMES_V1.iter().copied())
    {
        blockers.push("FEATURE_OBSERVATION_ORDER_INVALID".to_string());
    }
    for (index, observation) in features.observations.iter().enumerate() {
        if observation.source.is_empty() || observation.source != observation.source.trim() {
            blockers.push("FEATURE_SOURCE_MISSING_OR_INVALID".to_string());
        } else if CANDIDATE_EVALUATION_FEATURE_SOURCES_V1.get(index).copied()
            != Some(observation.source.as_str())
        {
            let name = FEATURE_NAMES_V1
                .get(index)
                .copied()
                .unwrap_or(observation.name.as_str());
            blockers.push(format!("FEATURE_SOURCE_MISMATCH:{name}"));
        }
        match (observation.raw_present, observation.value) {
            (false, None) => {
                blockers.push(format!("FEATURE_RAW_SOURCE_MISSING:{}", observation.name))
            }
            (true, Some(value)) if value.is_finite() => {
                if feature_value_in_declared_range(&observation.name, value) == Some(false) {
                    blockers.push(format!("FEATURE_VALUE_OUT_OF_RANGE:{}", observation.name));
                }
            }
            _ => blockers.push(format!(
                "FEATURE_VALUE_MISSING_OR_INVALID:{}",
                observation.name
            )),
        }
    }
    sorted_dedup(blockers)
}

fn bound_portfolio_snapshot_hash(event_context: &CandidateEventContextV1) -> Option<String> {
    let snapshot = event_context.portfolio_snapshot.as_ref()?;
    serde_json::to_value(snapshot)
        .ok()
        .map(|value| canonical_sha256(&value))
}

fn nonempty_trimmed(value: &str) -> bool {
    !value.is_empty() && value == value.trim()
}

fn portfolio_blockers(
    snapshot: &CandidateEvaluationSourceSnapshotV1,
    event_context: &CandidateEventContextV1,
) -> Vec<String> {
    let portfolio = &snapshot.portfolio;
    let mut blockers = Vec::new();
    let Some(bound) = event_context.portfolio_snapshot.as_ref() else {
        return vec!["BOUND_PORTFOLIO_SNAPSHOT_MISSING".to_string()];
    };
    let computed_bound_hash = bound_portfolio_snapshot_hash(event_context);
    let bound_hash_valid =
        computed_bound_hash.as_deref() == event_context.portfolio_snapshot_hash.as_deref();
    if !bound_hash_valid {
        blockers.push("BOUND_PORTFOLIO_SNAPSHOT_HASH_INVALID".to_string());
    }
    if portfolio.portfolio_snapshot_hash.as_deref() != computed_bound_hash.as_deref() {
        blockers.push("PORTFOLIO_SNAPSHOT_HASH_MISSING_OR_MISMATCH".to_string());
    }

    match (
        portfolio.accepted_demo_equity_usdt,
        bound.accepted_demo_equity_usdt,
    ) {
        (Some(source), Some(expected)) if source.is_finite() && source > 0.0 => {
            if source != expected {
                blockers.push("PORTFOLIO_EQUITY_MISMATCH".to_string());
            }
        }
        (Some(_), Some(_)) | (None, _) => {
            blockers.push("PORTFOLIO_EQUITY_MISSING_OR_INVALID".to_string());
        }
        (Some(_), None) => blockers.push("PORTFOLIO_EQUITY_MISMATCH".to_string()),
    }

    if portfolio.position_count != Some(bound.position_count)
        || portfolio.position_count != Some(portfolio.positions.len())
    {
        blockers.push("PORTFOLIO_POSITION_COUNT_MISSING_OR_MISMATCH".to_string());
    }
    if !portfolio
        .positions
        .windows(2)
        .all(|pair| pair[0].symbol < pair[1].symbol)
    {
        blockers.push("POSITION_SYMBOL_ORDER_OR_DUPLICATE_INVALID".to_string());
    }

    let mut computed_gross = 0.0;
    let mut computed_net = 0.0;
    let mut positions_reconcilable = true;
    for position in &portfolio.positions {
        if !nonempty_trimmed(&position.symbol)
            || position.symbol != position.symbol.to_ascii_uppercase()
        {
            blockers.push("POSITION_SYMBOL_MISSING_OR_INVALID".to_string());
        }
        let side_sign = match position.side.as_str() {
            "Long" => Some(1.0),
            "Short" => Some(-1.0),
            _ => {
                blockers.push("POSITION_SIDE_INVALID".to_string());
                positions_reconcilable = false;
                None
            }
        };
        let quantity = position
            .quantity
            .filter(|value| value.is_finite() && *value > 0.0);
        if quantity.is_none() {
            blockers.push("POSITION_QUANTITY_MISSING_OR_INVALID".to_string());
            positions_reconcilable = false;
        }
        if !matches!(
            position.mark_source.as_str(),
            "latest_price" | "entry_price_fallback"
        ) {
            blockers.push("POSITION_MARK_SOURCE_INVALID".to_string());
        }
        let mark_price = position
            .mark_price
            .filter(|value| value.is_finite() && *value > 0.0);
        if mark_price.is_none() {
            blockers.push("POSITION_MARK_PRICE_MISSING_OR_INVALID".to_string());
            positions_reconcilable = false;
        }
        let mark_notional = position
            .mark_notional_usdt
            .filter(|value| value.is_finite() && *value > 0.0);
        if mark_notional.is_none() {
            blockers.push("POSITION_MARK_NOTIONAL_MISSING_OR_INVALID".to_string());
            positions_reconcilable = false;
        }
        if let (Some(quantity), Some(mark_price), Some(mark_notional)) =
            (quantity, mark_price, mark_notional)
        {
            if mark_notional != quantity * mark_price {
                blockers.push("POSITION_MARK_NOTIONAL_RECONCILIATION_MISMATCH".to_string());
                positions_reconcilable = false;
            } else if let Some(side_sign) = side_sign {
                computed_gross += mark_notional;
                computed_net += side_sign * mark_notional;
            }
        }
        if !nonempty_trimmed(&position.owner_strategy) {
            blockers.push("POSITION_OWNER_STRATEGY_MISSING_OR_INVALID".to_string());
        }
        if !nonempty_trimmed(&position.entry_context_id) {
            blockers.push("POSITION_ENTRY_CONTEXT_ID_MISSING_OR_INVALID".to_string());
        }
    }

    let gross_matches_bound = portfolio
        .gross_mark_notional_usdt
        .is_some_and(|value| value.is_finite() && value >= 0.0)
        && portfolio.gross_mark_notional_usdt == Some(bound.gross_mark_notional_usdt);
    if !gross_matches_bound
        || (positions_reconcilable && portfolio.gross_mark_notional_usdt != Some(computed_gross))
    {
        blockers.push("PORTFOLIO_GROSS_MARK_NOTIONAL_MISSING_OR_MISMATCH".to_string());
    }
    let net_matches_bound = portfolio.net_mark_notional_usdt.is_some_and(f64::is_finite)
        && portfolio.net_mark_notional_usdt == Some(bound.net_mark_notional_usdt);
    if !net_matches_bound
        || (positions_reconcilable && portfolio.net_mark_notional_usdt != Some(computed_net))
    {
        blockers.push("PORTFOLIO_NET_MARK_NOTIONAL_MISSING_OR_MISMATCH".to_string());
    }

    if portfolio.positions.is_empty() {
        let valid_empty_attestation = portfolio.empty_position_attestation
            && portfolio.position_count == Some(0)
            && portfolio.gross_mark_notional_usdt == Some(0.0)
            && portfolio.net_mark_notional_usdt == Some(0.0)
            && portfolio
                .accepted_demo_equity_usdt
                .is_some_and(|value| value.is_finite() && value > 0.0)
            && bound_hash_valid;
        if !valid_empty_attestation {
            blockers.push("EMPTY_POSITION_ATTESTATION_INVALID".to_string());
        }
    } else if portfolio.empty_position_attestation {
        blockers.push("EMPTY_POSITION_ATTESTATION_INVALID".to_string());
    }
    sorted_dedup(blockers)
}

fn source_capture_blockers(
    snapshot: &CandidateEvaluationSourceSnapshotV1,
    event_context: &CandidateEventContextV1,
) -> Vec<String> {
    let mut blockers = event_binding_blockers(snapshot, event_context);
    blockers.extend(scan_blockers(snapshot, event_context));
    blockers.extend(feature_blockers(snapshot));
    blockers.extend(portfolio_blockers(snapshot, event_context));
    sorted_dedup(blockers)
}

fn finite(value: f64) -> bool {
    value.is_finite()
}

fn positive_finite(value: f64) -> bool {
    value.is_finite() && value > 0.0
}

fn orderbook_feature_inputs_present(event: &PriceEvent) -> bool {
    let (Some(bids), Some(asks)) = (event.bids5.as_ref(), event.asks5.as_ref()) else {
        return false;
    };
    let quantities_valid = bids
        .iter()
        .chain(asks)
        .all(|(_, quantity)| quantity.is_finite() && *quantity >= 0.0);
    let total_quantity = bids
        .iter()
        .chain(asks)
        .map(|(_, quantity)| *quantity)
        .sum::<f64>();
    quantities_valid && positive_finite(total_quantity)
}

/// Retain the predictor vector only where its underlying same-tick raw input
/// was actually present. Builder defaults remain absent evidence, not observed
/// zeroes.
pub fn build_candidate_evaluation_feature_source_from_runtime(
    features: &FeatureVectorV1,
    intent: &OrderIntent,
    event: &PriceEvent,
    indicators: Option<&IndicatorSnapshot>,
    atr_value: f64,
    paper_state: &PaperState,
) -> CandidateEvaluationFeatureSourceV1 {
    let adx_present = indicators
        .and_then(|snapshot| snapshot.adx.as_ref())
        .is_some_and(|value| finite(value.adx));
    let bollinger_present = indicators
        .and_then(|snapshot| snapshot.bollinger.as_ref())
        .is_some_and(|value| finite(value.bandwidth));
    let atr_present = positive_finite(atr_value) && positive_finite(event.last_price);
    let funding_present = event.funding_rate.is_some_and(finite);
    let realized_vol_present = indicators
        .and_then(|snapshot| snapshot.ewma_vol.as_ref())
        .is_some_and(|value| finite(value.ewma_vol));
    let basis_present =
        event.index_price.is_some_and(positive_finite) && positive_finite(event.last_price);
    let spread_present = positive_finite(event.bid_price)
        && positive_finite(event.ask_price)
        && positive_finite((event.bid_price + event.ask_price) * 0.5);
    let notional_present = positive_finite(intent.qty)
        && positive_finite(event.last_price)
        && positive_finite(paper_state.balance());
    let timestamp_present = event.ts_ms > 0;
    let raw_present = [
        adx_present,
        bollinger_present,
        atr_present,
        funding_present,
        realized_vol_present,
        basis_present,
        orderbook_feature_inputs_present(event),
        spread_present,
        intent.confluence_score.is_some_and(f32::is_finite),
        intent.persistence_elapsed_ms.is_some(),
        true,
        notional_present,
        true,
        true,
        timestamp_present,
        timestamp_present,
        timestamp_present,
    ];
    let values = features.to_array();
    let observations = FEATURE_NAMES_V1
        .iter()
        .enumerate()
        .map(|(index, name)| CandidateEvaluationFeatureObservationV1 {
            name: (*name).to_string(),
            value: raw_present[index].then_some(values[index] as f64),
            raw_present: raw_present[index],
            source: CANDIDATE_EVALUATION_FEATURE_SOURCES_V1[index].to_string(),
        })
        .collect();
    CandidateEvaluationFeatureSourceV1 {
        schema_version: FEATURE_SCHEMA_VERSION.to_string(),
        schema_hash: feature_schema_hash().to_string(),
        definition_hash: feature_definition_hash().to_string(),
        observations,
    }
}

pub(crate) fn canonical_candidate_mark_notionals_from_rows(
    mut rows: Vec<(String, bool, f64)>,
) -> (f64, f64) {
    rows.sort_by(|left, right| left.0.cmp(&right.0));
    let mut gross = 0.0;
    let mut net = 0.0;
    for (_, is_long, mark_notional) in rows {
        gross += mark_notional.abs();
        net += if is_long {
            mark_notional
        } else {
            -mark_notional
        };
    }
    (gross, net)
}

pub(crate) fn candidate_portfolio_mark_notionals_from_runtime(
    paper_state: &PaperState,
) -> (f64, f64) {
    let rows = paper_state
        .positions()
        .into_iter()
        .map(|position| {
            let mark_price = paper_state
                .latest_price(&position.symbol)
                .filter(|price| positive_finite(*price))
                .unwrap_or(position.entry_price);
            (
                position.symbol.clone(),
                position.is_long,
                position.qty * mark_price,
            )
        })
        .collect();
    canonical_candidate_mark_notionals_from_rows(rows)
}

/// Capture the same PaperState view bound into the event aggregate, retaining
/// per-position owner and entry lineage and an explicit mark-price fallback.
pub fn build_candidate_evaluation_portfolio_source_from_runtime(
    event_context: &CandidateEventContextV1,
    paper_state: &PaperState,
) -> CandidateEvaluationPortfolioSourceV1 {
    let mut positions = paper_state
        .positions()
        .into_iter()
        .map(|position| {
            let (mark_price, mark_source) = match paper_state
                .latest_price(&position.symbol)
                .filter(|price| positive_finite(*price))
            {
                Some(price) => (Some(price), "latest_price"),
                None => (
                    positive_finite(position.entry_price).then_some(position.entry_price),
                    "entry_price_fallback",
                ),
            };
            let quantity = positive_finite(position.qty).then_some(position.qty);
            let mark_notional_usdt = quantity
                .zip(mark_price)
                .map(|(quantity, mark_price)| quantity * mark_price)
                .filter(|value| positive_finite(*value));
            CandidateEvaluationPositionV1 {
                symbol: position.symbol.clone(),
                side: if position.is_long { "Long" } else { "Short" }.to_string(),
                quantity,
                mark_source: mark_source.to_string(),
                mark_price,
                mark_notional_usdt,
                owner_strategy: position.owner_strategy.clone(),
                entry_context_id: position.entry_context_id.clone(),
            }
        })
        .collect::<Vec<_>>();
    positions.sort_by(|left, right| left.symbol.cmp(&right.symbol));
    let (gross, net) = candidate_portfolio_mark_notionals_from_runtime(paper_state);
    CandidateEvaluationPortfolioSourceV1 {
        portfolio_snapshot_hash: event_context.portfolio_snapshot_hash.clone(),
        accepted_demo_equity_usdt: event_context
            .portfolio_snapshot
            .as_ref()
            .and_then(|snapshot| snapshot.accepted_demo_equity_usdt),
        position_count: Some(positions.len()),
        gross_mark_notional_usdt: (gross.is_finite() && gross >= 0.0).then_some(gross),
        net_mark_notional_usdt: net.is_finite().then_some(net),
        empty_position_attestation: positions.is_empty(),
        positions,
    }
}

/// Capture only caller-preassembled same-tick sources and bind them to the validated event.
pub fn capture_candidate_evaluation_source_snapshot(
    event_context: &CandidateEventContextV1,
    mut scan: Option<CandidateEvaluationScanSourceV1>,
    mut decision_features: CandidateEvaluationFeatureSourceV1,
    mut portfolio: CandidateEvaluationPortfolioSourceV1,
) -> CandidateEvaluationSourceSnapshotV1 {
    if let Some(scan) = scan.as_mut() {
        match (scan.beta_proxy_status, scan.beta_proxy) {
            (CandidateEvaluationBetaProxyStatusV1::Observed, Some(value)) if value.is_finite() => {}
            (CandidateEvaluationBetaProxyStatusV1::UnavailableBtcMove, None) => {}
            _ => {
                scan.beta_proxy = None;
                scan.beta_proxy_status = CandidateEvaluationBetaProxyStatusV1::Invalid;
            }
        }
        if scan
            .turnover_24h
            .is_some_and(|value| !value.is_finite() || value <= 0.0)
        {
            scan.turnover_24h = None;
        }
    }
    for observation in &mut decision_features.observations {
        if !observation.raw_present {
            observation.value = None;
        } else if !observation.value.is_some_and(f64::is_finite) {
            observation.raw_present = false;
            observation.value = None;
        }
    }
    if portfolio
        .accepted_demo_equity_usdt
        .is_some_and(|value| !value.is_finite() || value <= 0.0)
    {
        portfolio.accepted_demo_equity_usdt = None;
    }
    if portfolio
        .gross_mark_notional_usdt
        .is_some_and(|value| !value.is_finite() || value < 0.0)
    {
        portfolio.gross_mark_notional_usdt = None;
    }
    if portfolio
        .net_mark_notional_usdt
        .is_some_and(|value| !value.is_finite())
    {
        portfolio.net_mark_notional_usdt = None;
    }
    for position in &mut portfolio.positions {
        if position
            .quantity
            .is_some_and(|value| !value.is_finite() || value <= 0.0)
        {
            position.quantity = None;
        }
        if position
            .mark_price
            .is_some_and(|value| !value.is_finite() || value <= 0.0)
        {
            position.mark_price = None;
        }
        if position
            .mark_notional_usdt
            .is_some_and(|value| !value.is_finite() || value <= 0.0)
        {
            position.mark_notional_usdt = None;
        }
    }
    portfolio
        .positions
        .sort_by(|left, right| left.symbol.cmp(&right.symbol));
    let mut snapshot = CandidateEvaluationSourceSnapshotV1 {
        schema_version: CANDIDATE_EVALUATION_SOURCE_SNAPSHOT_SCHEMA_VERSION.to_string(),
        captured_at_ms: event_context.captured_at_ms,
        event_hash: event_context.event_hash.clone(),
        scan,
        decision_features,
        portfolio,
        capture_status: String::new(),
        capture_blockers: Vec::new(),
        snapshot_hash: String::new(),
        boundary: CANDIDATE_EVALUATION_SOURCE_SNAPSHOT_BOUNDARY.to_string(),
    };
    snapshot.capture_blockers = source_capture_blockers(&snapshot, event_context);
    snapshot.capture_status = if snapshot.capture_blockers.is_empty() {
        CANDIDATE_EVALUATION_SOURCE_CAPTURE_COMPLETE_STATUS
    } else {
        CANDIDATE_EVALUATION_SOURCE_CAPTURE_BLOCKED_STATUS
    }
    .to_string();
    snapshot.snapshot_hash =
        candidate_evaluation_source_snapshot_hash(&snapshot).unwrap_or_default();
    snapshot
}

/// Validate canonical integrity and exact binding to the supplied candidate event context.
pub fn validate_candidate_evaluation_source_snapshot(
    snapshot: &CandidateEvaluationSourceSnapshotV1,
    event_context: &CandidateEventContextV1,
) -> Result<(), Vec<String>> {
    let expected_blockers = source_capture_blockers(snapshot, event_context);
    let expected_status = if expected_blockers.is_empty() {
        CANDIDATE_EVALUATION_SOURCE_CAPTURE_COMPLETE_STATUS
    } else {
        CANDIDATE_EVALUATION_SOURCE_CAPTURE_BLOCKED_STATUS
    };
    let mut errors = Vec::new();
    if snapshot.capture_blockers != expected_blockers {
        errors.push("CAPTURE_BLOCKERS_MISMATCH".to_string());
    }
    if snapshot.capture_status != expected_status {
        errors.push("CAPTURE_STATUS_MISMATCH".to_string());
    }
    if candidate_evaluation_source_snapshot_hash(snapshot).as_deref()
        != Some(snapshot.snapshot_hash.as_str())
    {
        errors.push("SNAPSHOT_HASH_MISMATCH".to_string());
    }
    let errors = sorted_dedup(errors);
    if errors.is_empty() {
        Ok(())
    } else {
        Err(errors)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn orderbook_raw_presence_uses_only_quantities_consumed_by_feature_formula() {
        let mut event = PriceEvent::new("ETHUSDT".to_string(), 3_000.0, 1_782_041_000_000);

        event.bids5 = Some(vec![(0.0, 2.0)]);
        event.asks5 = Some(Vec::new());
        assert!(
            orderbook_feature_inputs_present(&event),
            "one empty side and an unused non-positive price remain observable when total quantity is positive"
        );

        event.bids5 = Some(Vec::new());
        event.asks5 = Some(vec![(f64::NAN, 3.0)]);
        assert!(
            orderbook_feature_inputs_present(&event),
            "unused non-finite prices must not erase valid quantity evidence"
        );

        event.bids5 = Some(Vec::new());
        event.asks5 = Some(Vec::new());
        assert!(!orderbook_feature_inputs_present(&event));

        event.bids5 = None;
        event.asks5 = Some(vec![(3_001.0, 1.0)]);
        assert!(!orderbook_feature_inputs_present(&event));

        for invalid_quantity in [-1.0, f64::NAN, f64::INFINITY] {
            event.bids5 = Some(vec![(3_000.0, invalid_quantity)]);
            event.asks5 = Some(vec![(3_001.0, 1.0)]);
            assert!(
                !orderbook_feature_inputs_present(&event),
                "invalid consumed quantity {invalid_quantity:?} must fail closed"
            );
        }

        event.bids5 = Some(vec![(3_000.0, 0.0)]);
        event.asks5 = Some(vec![(3_001.0, 0.0)]);
        assert!(
            !orderbook_feature_inputs_present(&event),
            "zero denominator is not observable orderbook imbalance evidence"
        );
    }
}
