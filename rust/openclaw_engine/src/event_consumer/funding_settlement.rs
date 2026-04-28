//! Funding settlement handling for Bybit execution stream.
//! Bybit execution stream 資金費結算處理。

use crate::bybit_private_ws::ExecutionUpdate;
use crate::database::TradingMsg;
use crate::tick_pipeline::TickPipeline;
use tokio::sync::mpsc;

pub(super) fn is_funding_execution(exec: &ExecutionUpdate) -> bool {
    exec.exec_type.eq_ignore_ascii_case("Funding")
}

fn parse_f64_str(s: &str) -> Option<f64> {
    let v = s.parse::<f64>().ok()?;
    v.is_finite().then_some(v)
}

fn raw_f64(exec: &ExecutionUpdate, key: &str) -> Option<f64> {
    match exec.raw.get(key)? {
        serde_json::Value::String(s) => parse_f64_str(s),
        serde_json::Value::Number(n) => n.as_f64().filter(|v| v.is_finite()),
        _ => None,
    }
}

pub(super) fn funding_amount_from_exec(exec: &ExecutionUpdate) -> f64 {
    if let Some(v) = parse_f64_str(&exec.exec_fee).filter(|v| *v != 0.0) {
        return v;
    }
    for key in [
        "fundingFee",
        "funding",
        "fundingAmount",
        "cashFlow",
        "walletBalanceChange",
        "transactionAmount",
    ] {
        if let Some(v) = raw_f64(exec, key).filter(|v| *v != 0.0) {
            return v;
        }
    }
    0.0
}

fn settlement_id(exec: &ExecutionUpdate, ts_ms: u64) -> String {
    if exec.exec_id.is_empty() {
        format!("funding-{}-{}", exec.symbol, ts_ms)
    } else {
        format!("funding-{}", exec.exec_id)
    }
}

fn funding_strategy_name(pipeline: &TickPipeline, symbol: &str) -> String {
    pipeline
        .paper_state
        .get_position(symbol)
        .map(|p| p.owner_strategy.clone())
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| "unattributed:funding".to_string())
}

pub(super) async fn apply_and_emit_funding_settlement(
    pipeline: &mut TickPipeline,
    exec: &ExecutionUpdate,
    order_tx: Option<&mpsc::Sender<TradingMsg>>,
) -> bool {
    let ts_ms = exec.exec_time.parse::<u64>().unwrap_or(0);
    let amount = funding_amount_from_exec(exec);
    pipeline.paper_state.apply_funding_settlement(amount);

    let tx = match order_tx {
        Some(tx) => tx,
        None => return false,
    };

    let raw = (!exec.raw.is_null()).then_some(exec.raw.clone());
    let msg = TradingMsg::FundingSettlement {
        settlement_id: settlement_id(exec, ts_ms),
        ts_ms,
        exec_id: exec.exec_id.clone(),
        symbol: exec.symbol.clone(),
        side: exec.side.clone(),
        amount,
        fee_currency: if exec.fee_currency.is_empty() {
            "USDT".to_string()
        } else {
            exec.fee_currency.clone()
        },
        exec_value: parse_f64_str(&exec.exec_value).unwrap_or(0.0),
        exec_price: parse_f64_str(&exec.exec_price).unwrap_or(0.0),
        exec_qty: parse_f64_str(&exec.exec_qty).unwrap_or(0.0),
        strategy_name: funding_strategy_name(pipeline, &exec.symbol),
        engine_mode: pipeline.effective_engine_mode().to_string(),
        raw,
    };

    tx.send(msg).await.is_ok()
}
