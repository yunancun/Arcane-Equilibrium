//! Funding settlement handling for Bybit execution stream.
//! Bybit execution stream 資金費結算處理。

use crate::bybit_private_ws::ExecutionUpdate;
use crate::database::TradingMsg;
use crate::tick_pipeline::TickPipeline;
use tokio::sync::mpsc;
use tracing::warn;

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

    // ENGINE-CRASH-FIX A1 (2026-06-15): bounded send 取代無限阻塞 send().await。
    // 為什麼 fail-open drop 在此安全（survival > audit）：本 fn 跑在 demo/live
    // event_consumer select! arm 內，與 watchdog 讀的 health snapshot + tick
    // atomic 同一 async task。無界 `tx.send().await` 在 trading_writer 因 PG 慢
    // 塞滿 4096-cap channel 時無限阻塞此 task → 凍結 snapshot/tick → tick-stale
    // watchdog 對活著的 live 引擎發 SIGTERM 平倉（root cause）。改為 500ms 有界
    // send：通道未滿時與舊路徑逐位元組相同；只有背壓真正發生時才放棄這一筆
    // funding settlement *audit emit*。安全性：settlement 在 DB 以 settlement_id
    // 為 PK 冪等（funding-{exec_id}），WS 重連重發同 exec_id 由 ON CONFLICT 合併；
    // 且錢包餘額對賬走 reconcile_balance_from_exchange 另一路徑（paper_state 的
    // apply_funding_settlement 已在 send 前同步執行，不受丟棄影響）。Timeout/Full/
    // Closed 一律回 false，鏡像舊 channel-closed → false 路徑。
    let send_start = std::time::Instant::now();
    let result = tx
        .send_timeout(msg, std::time::Duration::from_millis(500))
        .await;
    let elapsed = send_start.elapsed();
    // C3 instrumentation：熱路徑背壓觀測（>200ms 代表 trading_writer 落後）。
    if elapsed.as_millis() > 200 {
        warn!(
            elapsed_ms = elapsed.as_millis() as u64,
            "funding settlement send slow — trading_tx backpressure \
             / funding settlement 送出緩慢 — trading_tx 背壓"
        );
    }
    match result {
        Ok(()) => true,
        Err(e) => {
            let total =
                FUNDING_AUDIT_DROPPED.fetch_add(1, std::sync::atomic::Ordering::Relaxed) + 1;
            if should_emit_funding_drop_warn() {
                warn!(
                    total_dropped = total,
                    elapsed_ms = elapsed.as_millis() as u64,
                    error = %e,
                    "funding settlement audit dropped under trading_tx backpressure \
                     (warn 1Hz sampled) — settlement_id PK keeps DB idempotent, \
                     wallet balance reconciled separately \
                     / funding settlement audit 因 trading_tx 背壓丟棄"
                );
            }
            false
        }
    }
}

// ENGINE-CRASH-FIX A1 (2026-06-15): 模組級單調丟棄計數 + 1Hz warn 節流。
// 鏡像 unattributed_emit / canary_writer 模式（leaf fn 無 handle 可掛計數）。
static FUNDING_AUDIT_DROPPED: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
static FUNDING_DROP_LAST_WARN_MS: std::sync::atomic::AtomicU64 =
    std::sync::atomic::AtomicU64::new(0);

/// 每 1000ms 至多回傳一次 true（CAS 序列化），避免持續背壓下 warn flood。
fn should_emit_funding_drop_warn() -> bool {
    const WARN_THROTTLE_MS: u64 = 1000;
    let now_ms = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0);
    let last = FUNDING_DROP_LAST_WARN_MS.load(std::sync::atomic::Ordering::Relaxed);
    if now_ms.saturating_sub(last) < WARN_THROTTLE_MS {
        return false;
    }
    FUNDING_DROP_LAST_WARN_MS
        .compare_exchange(
            last,
            now_ms,
            std::sync::atomic::Ordering::Relaxed,
            std::sync::atomic::Ordering::Relaxed,
        )
        .is_ok()
}
