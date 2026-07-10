//! MODULE_NOTE
//! 模塊用途：捕獲 Cost Gate organic reject 當刻的不可變候選事件上下文。
//! 主要接口：`capture_candidate_event_context`、canonical JSON/hash helpers。
//! 依賴：只接受呼叫端提供的當刻值，不讀目前策略設定、不接 DB/Bybit。
//! 硬邊界：缺失或無效 lineage 必須 durable `CAPTURE_BLOCKED`，不得 panic、
//! backfill、訓練、送單、修改 Cost Gate 或取得任何交易權限。

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};

pub const CANDIDATE_EVENT_CONTEXT_SCHEMA_VERSION: &str = "candidate_event_context_v1";
pub const CANDIDATE_HORIZON_POLICY_SCHEMA_VERSION: &str = "candidate_horizon_policy_v1";
pub const CANDIDATE_PORTFOLIO_SNAPSHOT_SCHEMA_VERSION: &str = "candidate_portfolio_snapshot_v1";
pub const CAPTURE_COMPLETE_STATUS: &str = "CAPTURE_COMPLETE";
pub const CAPTURE_BLOCKED_STATUS: &str = "CAPTURE_BLOCKED";
pub const CANDIDATE_EVENT_CONTEXT_BOUNDARY: &str =
    "immutable learning evidence only; no training, serving, promotion, order, lease, gate, config, broker, or runtime authority";
pub const OUTCOME_HORIZON_ENV: &str = "OPENCLAW_COST_GATE_LEARNING_OUTCOME_HORIZON_MINUTES";

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CandidateHorizonPolicyV1 {
    pub schema_version: String,
    pub source: String,
    pub outcome_horizon_minutes: Option<u64>,
    pub default_applied: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CandidateScannerInputsV1 {
    pub authority_mode: String,
    pub legacy_would_block: bool,
    pub legacy_block_reason: Option<String>,
    pub scan_id: String,
    pub best_strategy: String,
    pub intent_strategy: String,
    pub market_regime: String,
    pub trend_phase: String,
    pub trend_score: f64,
    pub range_score: f64,
    pub shock_score: f64,
    pub close_alignment: f64,
    pub range_position: f64,
    pub crowding_score: f64,
    pub reversal_risk_score: f64,
    pub directional_efficiency: f64,
    pub dir_pct: f64,
    pub signed_dir_pct: f64,
    pub range_pct: f64,
    pub fr_bps: f64,
    pub f_ma: f64,
    pub f_grid: f64,
    pub f_bbrv: f64,
    pub f_bkout: f64,
    pub f_funding_arb: f64,
    pub edge_bps: Option<f64>,
    pub edge_n: u32,
    pub edge_status: String,
    pub route_mode: String,
    pub market_status: String,
    pub route_reason: String,
    pub opportunity: Option<Value>,
    pub final_score: f64,
    pub raw_score: f64,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CandidateMarketInputsV1 {
    pub observed_at_ms: u64,
    pub last_price: Option<f64>,
    pub best_bid: Option<f64>,
    pub best_ask: Option<f64>,
    pub tick_size: Option<f64>,
    pub index_price: Option<f64>,
    pub funding_rate: Option<f64>,
    pub open_interest: Option<f64>,
    pub atr_value: Option<f64>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CandidateRiskContextV1 {
    pub risk_state: String,
    pub governance_profile: String,
    pub risk_config_hash: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CandidatePortfolioSnapshotV1 {
    pub schema_version: String,
    pub captured_at_ms: u64,
    pub balance: f64,
    pub accepted_demo_equity_usdt: Option<f64>,
    pub peak_balance: f64,
    pub drawdown_pct: f64,
    pub position_count: usize,
    pub gross_mark_notional_usdt: f64,
    pub net_mark_notional_usdt: f64,
    pub total_realized_pnl: f64,
    pub total_fees: f64,
    pub total_funding_pnl: f64,
    pub trade_count: u32,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CandidateEventContextV1 {
    pub schema_version: String,
    pub captured_at_ms: u64,
    pub strategy_name: String,
    pub strategy_version: String,
    pub build_git_sha: String,
    pub strategy_params_json: String,
    pub strategy_params_canonical_json: Option<String>,
    pub conf_scale: Option<f64>,
    pub strategy_config_hash: Option<String>,
    pub symbol: String,
    pub side: String,
    pub horizon_policy: CandidateHorizonPolicyV1,
    pub evidence_engine_mode: String,
    pub pipeline_kind: String,
    pub endpoint_environment: Option<String>,
    pub venue: String,
    pub product: String,
    pub context_id: Option<String>,
    pub signal_id: Option<String>,
    pub scan_id: Option<String>,
    pub scanner_inputs: Option<CandidateScannerInputsV1>,
    pub market_inputs: CandidateMarketInputsV1,
    pub risk_context: CandidateRiskContextV1,
    pub portfolio_snapshot: Option<CandidatePortfolioSnapshotV1>,
    pub portfolio_snapshot_ref: Option<String>,
    pub portfolio_snapshot_hash: Option<String>,
    pub capture_status: String,
    pub capture_blockers: Vec<String>,
    pub event_hash: String,
    pub boundary: String,
}

#[derive(Debug, Clone)]
pub struct CandidateEventCaptureInput {
    pub captured_at_ms: u64,
    pub strategy_name: String,
    pub runtime_strategy_name: String,
    pub build_git_sha: String,
    pub strategy_params_json: String,
    pub conf_scale: f64,
    pub symbol: String,
    pub side: String,
    pub horizon_env_value: Option<String>,
    pub evidence_engine_mode: String,
    pub pipeline_kind: String,
    pub endpoint_environment: Option<String>,
    pub context_id: Option<String>,
    pub signal_id: Option<String>,
    pub scanner_inputs: Option<CandidateScannerInputsV1>,
    pub market_inputs: CandidateMarketInputsV1,
    pub risk_state: String,
    pub governance_profile: String,
    pub risk_config: Option<Value>,
    pub portfolio_snapshot_ref: Option<String>,
    pub portfolio_snapshot: Option<CandidatePortfolioSnapshotV1>,
}

/// 依 `ipc_server::live_authz` 慣例輸出遞迴排序、緊湊、UTF-8 canonical JSON。
pub fn canonical_json(value: &Value) -> String {
    fn push(value: &Value, out: &mut String) {
        match value {
            Value::Null => out.push_str("null"),
            Value::Bool(value) => out.push_str(if *value { "true" } else { "false" }),
            Value::Number(value) => out.push_str(&value.to_string()),
            Value::String(value) => out.push_str(
                &serde_json::to_string(value).expect("JSON string serialization is infallible"),
            ),
            Value::Array(values) => {
                out.push('[');
                for (index, value) in values.iter().enumerate() {
                    if index > 0 {
                        out.push(',');
                    }
                    push(value, out);
                }
                out.push(']');
            }
            Value::Object(values) => {
                let mut keys: Vec<&String> = values.keys().collect();
                keys.sort_unstable();
                out.push('{');
                for (index, key) in keys.iter().enumerate() {
                    if index > 0 {
                        out.push(',');
                    }
                    out.push_str(
                        &serde_json::to_string(key)
                            .expect("JSON object-key serialization is infallible"),
                    );
                    out.push(':');
                    push(&values[*key], out);
                }
                out.push('}');
            }
        }
    }

    let mut out = String::new();
    push(value, &mut out);
    out
}

/// 對 canonical UTF-8 bytes 計算 lowercase SHA-256。
pub fn canonical_sha256(value: &Value) -> String {
    let mut hasher = Sha256::new();
    hasher.update(canonical_json(value).as_bytes());
    hex::encode(hasher.finalize())
}

fn horizon_policy(raw: Option<&str>) -> CandidateHorizonPolicyV1 {
    match raw {
        None => CandidateHorizonPolicyV1 {
            schema_version: CANDIDATE_HORIZON_POLICY_SCHEMA_VERSION.to_string(),
            source: "default_60_minutes".to_string(),
            outcome_horizon_minutes: Some(60),
            default_applied: true,
        },
        Some(raw) => {
            let parsed = (raw == raw.trim())
                .then(|| raw.parse::<u64>().ok())
                .flatten()
                .filter(|value| (1..=1_440).contains(value));
            CandidateHorizonPolicyV1 {
                schema_version: CANDIDATE_HORIZON_POLICY_SCHEMA_VERSION.to_string(),
                source: OUTCOME_HORIZON_ENV.to_string(),
                outcome_horizon_minutes: parsed,
                default_applied: false,
            }
        }
    }
}

fn non_empty(value: Option<&str>) -> Option<String> {
    value
        .filter(|value| !value.is_empty() && *value == value.trim())
        .map(ToString::to_string)
}

fn valid_build_git_sha(value: &str) -> bool {
    value.len() == 40
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn scanner_inputs_valid(scanner: &CandidateScannerInputsV1, strategy_name: &str) -> bool {
    let required_strings = [
        scanner.authority_mode.as_str(),
        scanner.scan_id.as_str(),
        scanner.best_strategy.as_str(),
        scanner.intent_strategy.as_str(),
        scanner.market_regime.as_str(),
        scanner.trend_phase.as_str(),
        scanner.edge_status.as_str(),
        scanner.route_mode.as_str(),
        scanner.market_status.as_str(),
        scanner.route_reason.as_str(),
    ];
    let values = [
        scanner.trend_score,
        scanner.range_score,
        scanner.shock_score,
        scanner.close_alignment,
        scanner.range_position,
        scanner.crowding_score,
        scanner.reversal_risk_score,
        scanner.directional_efficiency,
        scanner.dir_pct,
        scanner.signed_dir_pct,
        scanner.range_pct,
        scanner.fr_bps,
        scanner.f_ma,
        scanner.f_grid,
        scanner.f_bbrv,
        scanner.f_bkout,
        scanner.f_funding_arb,
        scanner.final_score,
        scanner.raw_score,
    ];
    required_strings
        .iter()
        .all(|value| !value.is_empty() && *value == value.trim())
        && scanner
            .legacy_block_reason
            .as_deref()
            .is_none_or(|value| !value.trim().is_empty())
        && values.iter().all(|value| value.is_finite())
        && scanner.edge_bps.is_none_or(f64::is_finite)
        && scanner.intent_strategy == strategy_name
}

fn sanitize_market_inputs(mut market: CandidateMarketInputsV1) -> CandidateMarketInputsV1 {
    fn positive(value: Option<f64>) -> Option<f64> {
        value.filter(|value| value.is_finite() && *value > 0.0)
    }
    fn finite(value: Option<f64>) -> Option<f64> {
        value.filter(|value| value.is_finite())
    }

    market.last_price = positive(market.last_price);
    market.best_bid = positive(market.best_bid);
    market.best_ask = positive(market.best_ask);
    market.tick_size = positive(market.tick_size);
    market.index_price = positive(market.index_price);
    market.funding_rate = finite(market.funding_rate);
    market.open_interest = positive(market.open_interest);
    market.atr_value = positive(market.atr_value);
    market
}

fn portfolio_snapshot_valid(
    snapshot: &CandidatePortfolioSnapshotV1,
    snapshot_ref: Option<&str>,
    expected_snapshot_ref: Option<&str>,
    captured_at_ms: u64,
) -> bool {
    snapshot.schema_version == CANDIDATE_PORTFOLIO_SNAPSHOT_SCHEMA_VERSION
        && snapshot.captured_at_ms == captured_at_ms
        && snapshot_ref.is_some()
        && snapshot_ref == expected_snapshot_ref
        && snapshot.balance.is_finite()
        && snapshot.balance > 0.0
        && snapshot.peak_balance.is_finite()
        && snapshot.peak_balance >= snapshot.balance
        && snapshot.drawdown_pct.is_finite()
        && (0.0..=100.0).contains(&snapshot.drawdown_pct)
        && snapshot.gross_mark_notional_usdt.is_finite()
        && snapshot.gross_mark_notional_usdt >= 0.0
        && snapshot.net_mark_notional_usdt.is_finite()
        && snapshot.net_mark_notional_usdt.abs() <= snapshot.gross_mark_notional_usdt
        && snapshot.total_realized_pnl.is_finite()
        && snapshot.total_fees.is_finite()
        && snapshot.total_funding_pnl.is_finite()
        && snapshot
            .accepted_demo_equity_usdt
            .is_some_and(|value| value.is_finite() && value > 0.0)
}

fn endpoint_binding_valid(
    evidence_mode: &str,
    pipeline_kind: &str,
    endpoint: Option<&str>,
) -> bool {
    matches!(
        (evidence_mode, pipeline_kind, endpoint),
        ("demo", "demo", Some("demo")) | ("live_demo", "live", Some("demo" | "live_demo"))
    )
}

fn risk_context_valid(risk_state: &str, governance_profile: &str) -> bool {
    matches!(
        risk_state,
        "NORMAL" | "CAUTIOUS" | "REDUCED" | "DEFENSIVE" | "MANUAL_REVIEW" | "CIRCUIT_BREAKER"
    ) && governance_profile == "Validation"
}

/// 捕獲 organic reject 當刻的 flat `candidate_event_context_v1`。
///
/// 此接口只消費 caller 已持有的當刻資料；不讀目前 HEAD/config，也不產生任何權限。
pub fn capture_candidate_event_context(
    input: CandidateEventCaptureInput,
) -> CandidateEventContextV1 {
    let strategy_name = input.strategy_name.trim().to_string();
    let runtime_strategy_name = input.runtime_strategy_name.trim();
    let symbol = input.symbol.trim().to_string();
    let side = input.side.trim().to_string();
    let build_sha_valid = valid_build_git_sha(&input.build_git_sha);
    let capture_timestamp_valid = input.captured_at_ms > 0;
    let strategy_name_matches = !strategy_name.is_empty()
        && !runtime_strategy_name.is_empty()
        && strategy_name == runtime_strategy_name;
    let symbol_valid =
        !symbol.is_empty() && symbol == input.symbol && symbol == symbol.to_ascii_uppercase();
    let side_valid = matches!(side.as_str(), "Buy" | "Sell") && side == input.side;
    let parsed_params = serde_json::from_str::<Value>(&input.strategy_params_json)
        .ok()
        .filter(Value::is_object);
    let strategy_params_canonical_json = parsed_params.as_ref().map(canonical_json);
    let conf_scale = (input.conf_scale.is_finite() && (0.0..=2.0).contains(&input.conf_scale))
        .then_some(input.conf_scale);
    let strategy_config_hash = parsed_params
        .as_ref()
        .zip(conf_scale)
        .map(|(params, scale)| {
            canonical_sha256(&json!({
                "strategy_params": params,
                "conf_scale": scale,
            }))
        });
    let horizon_policy = horizon_policy(input.horizon_env_value.as_deref());
    let context_id = non_empty(input.context_id.as_deref());
    let signal_id = non_empty(input.signal_id.as_deref());
    let scanner_valid = input
        .scanner_inputs
        .as_ref()
        .is_some_and(|scanner| scanner_inputs_valid(scanner, &strategy_name));
    let scanner_inputs = scanner_valid.then_some(input.scanner_inputs).flatten();
    let scan_id = scanner_inputs
        .as_ref()
        .map(|scanner| scanner.scan_id.clone());
    let endpoint_valid = endpoint_binding_valid(
        input.evidence_engine_mode.trim(),
        input.pipeline_kind.trim(),
        input.endpoint_environment.as_deref(),
    );
    let market_inputs = sanitize_market_inputs(input.market_inputs);
    let bbo_valid = market_inputs.observed_at_ms == input.captured_at_ms
        && market_inputs.last_price.is_some()
        && market_inputs.best_bid.is_some()
        && market_inputs.best_ask.is_some()
        && market_inputs.tick_size.is_some();
    let bbo_crossed = market_inputs
        .best_bid
        .zip(market_inputs.best_ask)
        .is_some_and(|(bid, ask)| bid >= ask);
    let portfolio_snapshot_ref = non_empty(input.portfolio_snapshot_ref.as_deref());
    let expected_portfolio_snapshot_ref = context_id.as_ref().map(|context_id| {
        format!(
            "paper_state:{}:{}:{}",
            input.evidence_engine_mode.trim(),
            context_id,
            input.captured_at_ms
        )
    });
    let accepted_equity_valid = input
        .portfolio_snapshot
        .as_ref()
        .and_then(|snapshot| snapshot.accepted_demo_equity_usdt)
        .is_some_and(|value| value.is_finite() && value > 0.0);
    let portfolio_valid = input.portfolio_snapshot.as_ref().is_some_and(|snapshot| {
        portfolio_snapshot_valid(
            snapshot,
            portfolio_snapshot_ref.as_deref(),
            expected_portfolio_snapshot_ref.as_deref(),
            input.captured_at_ms,
        )
    });
    let portfolio_snapshot = portfolio_valid
        .then_some(input.portfolio_snapshot)
        .flatten();
    let portfolio_snapshot_hash = portfolio_snapshot
        .as_ref()
        .and_then(|snapshot| serde_json::to_value(snapshot).ok())
        .map(|snapshot| canonical_sha256(&snapshot));
    let risk_config_hash = input
        .risk_config
        .as_ref()
        .filter(|value| value.is_object())
        .map(canonical_sha256);
    let risk_state = input.risk_state.trim().to_string();
    let governance_profile = input.governance_profile.trim().to_string();
    let risk_valid =
        risk_context_valid(&risk_state, &governance_profile) && risk_config_hash.is_some();
    let mut blockers = Vec::new();
    if !build_sha_valid {
        blockers.push("BUILD_GIT_SHA_UNKNOWN_OR_INVALID".to_string());
    }
    if !capture_timestamp_valid {
        blockers.push("CAPTURE_TIMESTAMP_INVALID".to_string());
    }
    if !strategy_name_matches {
        blockers.push("STRATEGY_NAME_MISMATCH".to_string());
    }
    if !symbol_valid {
        blockers.push("SYMBOL_MISSING_OR_INVALID".to_string());
    }
    if !side_valid {
        blockers.push("SIDE_MISSING_OR_INVALID".to_string());
    }
    if parsed_params.is_none() {
        blockers.push("STRATEGY_PARAMS_JSON_INVALID_OR_NOT_OBJECT".to_string());
    }
    if conf_scale.is_none() {
        blockers.push("CONF_SCALE_INVALID".to_string());
    }
    if horizon_policy.outcome_horizon_minutes.is_none() {
        blockers.push("HORIZON_POLICY_INVALID".to_string());
    }
    if context_id.is_none() {
        blockers.push("CONTEXT_ID_MISSING".to_string());
    }
    if signal_id.is_none() {
        blockers.push("SIGNAL_ID_MISSING".to_string());
    }
    if !scanner_valid {
        blockers.push("SCAN_CONTEXT_MISSING_OR_INVALID".to_string());
    }
    if !endpoint_valid {
        blockers.push("ENDPOINT_BINDING_MISSING_OR_INCOMPATIBLE".to_string());
    }
    if !bbo_valid {
        blockers.push("BBO_MISSING_OR_INVALID".to_string());
    }
    if bbo_crossed {
        blockers.push("BBO_CROSSED".to_string());
    }
    if !portfolio_valid {
        blockers.push("PORTFOLIO_SNAPSHOT_INVALID".to_string());
    }
    if !accepted_equity_valid {
        blockers.push("ACCEPTED_DEMO_EQUITY_MISSING_OR_INVALID".to_string());
    }
    if !risk_valid {
        blockers.push("RISK_CONTEXT_INVALID".to_string());
    }
    if risk_config_hash.is_none() {
        blockers.push("RISK_CONFIG_HASH_UNCOMPUTABLE".to_string());
    }
    let strategy_version = input.build_git_sha.clone();
    let capture_status = if blockers.is_empty() {
        CAPTURE_COMPLETE_STATUS
    } else {
        CAPTURE_BLOCKED_STATUS
    };

    let mut context = CandidateEventContextV1 {
        schema_version: CANDIDATE_EVENT_CONTEXT_SCHEMA_VERSION.to_string(),
        captured_at_ms: input.captured_at_ms,
        strategy_name,
        strategy_version,
        build_git_sha: input.build_git_sha,
        strategy_params_json: input.strategy_params_json,
        strategy_params_canonical_json,
        conf_scale,
        strategy_config_hash,
        symbol,
        side,
        horizon_policy,
        evidence_engine_mode: input.evidence_engine_mode.trim().to_string(),
        pipeline_kind: input.pipeline_kind.trim().to_string(),
        endpoint_environment: non_empty(input.endpoint_environment.as_deref()),
        venue: "bybit".to_string(),
        product: "linear_perpetual".to_string(),
        context_id,
        signal_id,
        scan_id,
        scanner_inputs,
        market_inputs,
        risk_context: CandidateRiskContextV1 {
            risk_state,
            governance_profile,
            risk_config_hash,
        },
        portfolio_snapshot,
        portfolio_snapshot_ref,
        portfolio_snapshot_hash,
        capture_status: capture_status.to_string(),
        capture_blockers: blockers,
        event_hash: String::new(),
        boundary: CANDIDATE_EVENT_CONTEXT_BOUNDARY.to_string(),
    };
    let mut hash_value =
        serde_json::to_value(&context).expect("validated candidate event context serializes");
    hash_value
        .as_object_mut()
        .expect("candidate event context serializes as object")
        .remove("event_hash");
    context.event_hash = canonical_sha256(&hash_value);
    context
}

#[cfg(test)]
#[path = "candidate_event_context_tests.rs"]
mod tests;
