//! Order dispatch task spawn — extracted from event_consumer/mod.rs (I-22).
//! 訂單派發任務 — 從 event_consumer/mod.rs 提取（I-22）。
//!
//! MODULE_NOTE (EN): Spawns the async task that drains the OrderDispatchRequest channel
//!   from TickPipeline and forwards orders to OrderManager. Handles both shadow (paper_only)
//!   and primary (exchange) modes. Returns the PendingOrder receiver used by the event
//!   consumer to track exchange-mode order confirmations.
//! MODULE_NOTE (中): 啟動從 TickPipeline 排出 OrderDispatchRequest 通道並轉發到 OrderManager
//!   的異步任務。同時處理 shadow（紙盤）和 primary（交易所）模式。返回 event consumer
//!   用於追蹤交易所模式訂單確認的 PendingOrder 接收端。

use super::types::PendingOrder;
use crate::bybit_rest_client::{BybitApiError, BybitRestClient};
use crate::instrument_info::InstrumentInfoCache;
use crate::tick_pipeline::TickPipeline;
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::mpsc;
use tracing::{debug, error, info, warn};

// ---------------------------------------------------------------------------
// Retry policy (DISPATCH-RETRY-1, 2026-04-19) / 重試策略
// ---------------------------------------------------------------------------

/// Exponential backoff delays between retry attempts for OPEN intents (ms).
/// Index i = delay BEFORE retry attempt (i+1). Total up to 3 retries
/// (= 4 total attempts: 1 initial + 3 retries; worst-case ~4.2 s sleep).
///
/// 開倉意圖的指數退避延遲（毫秒）。索引 i = 第 (i+1) 次重試前的延遲。
/// 最多重試 3 次（= 1 次初始 + 3 次重試共 4 次嘗試；worst-case ~4.2s 睡眠）。
pub(super) const RETRY_DELAY_MS: [u64; 3] = [200, 800, 3200];

/// Tighter retry budget for CLOSE intents: 2 retries max, 500 ms total sleep.
/// DISPATCH-RETRY-1 (E2 review 2026-04-19, Q2): slow-retrying a close amplifies
/// PnL bleed on exit paths. Genuine structural errors are rejected fast; a slow
/// transient is itself a degraded-exchange signal, waiting longer doesn't help.
/// `reduce_only=true` provides secondary dedup safety on close retries.
///
/// 關倉意圖的更短重試預算：最多 2 次重試，共 500 ms 睡眠。
/// DISPATCH-RETRY-1（E2 審查 2026-04-19, Q2）：關倉慢重試會放大 PnL 流失。
/// 真正結構性錯誤會被快速拒絕；慢暫時性本身即為交易所降級訊號，久等無益。
/// 關倉重試由 `reduce_only=true` 提供二級去重保護。
pub(super) const CLOSE_RETRY_DELAY_MS: [u64; 2] = [100, 400];

/// Classification of a dispatch error for retry decisioning.
/// DISPATCH-RETRY-1 (2026-04-19) — distinguish transient network / rate-limit
/// failures (worth retrying) from structural business rejections (retry-futile).
///
/// 派發錯誤的重試決策分類。DISPATCH-RETRY-1（2026-04-19）— 區分暫時性
/// 網路/限流失敗（值得重試）與結構性業務拒單（重試無效）。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(super) enum DispatchOutcome {
    /// Retry safe — network / HTTP / rate-limit / transient server issues.
    /// 可安全重試 — 網路、HTTP、限流、暫時性伺服器問題。
    Transient,
    /// No retry — exchange rejects on business grounds that retry won't fix.
    /// Includes min_notional, invalid param, API key, insufficient balance, etc.
    /// 不重試 — 交易所業務拒單，重試無效。
    /// 包含 min_notional、參數無效、API key、餘額不足等。
    Structural,
    /// Idempotent success-equivalent — duplicate / already-done / not-found-on-close.
    /// Treat the retry as successful and move on.
    /// 等價成功 — 重複 / 已完成 / close 時倉位已不存在。視為成功不再重試。
    NoOp,
}

/// Result of a retry-wrapped dispatch sequence.
/// DISPATCH-RETRY-1 (E2 review 2026-04-19): separates outcome classification
/// from side-effectful logging, enabling deterministic loop-level tests.
/// `last_error` on TransientExhausted is the FINAL attempt's error.
///
/// 帶重試派發序列的結果。DISPATCH-RETRY-1（E2 審查 2026-04-19）：
/// 將結果分類與副作用日誌分離，支援迴圈級確定性測試。
/// TransientExhausted 的 last_error 為最終嘗試的錯誤。
#[derive(Debug)]
pub(super) enum DispatchRetryResult<T> {
    /// Dispatch succeeded (possibly after retries). `attempts=1` if first-try.
    /// 派發成功（可能經重試）。attempts=1 表示首試即成功。
    Ok { value: T, attempts: u32 },
    /// Duplicate / already-done / not-found-on-close — treat as success.
    /// 重複/已完成/平倉時已不存在 — 視為成功。
    NoOp {
        last_error: BybitApiError,
        attempts: u32,
    },
    /// Business rejection not recoverable by retry.
    /// 業務拒單，重試無效。
    Structural {
        last_error: BybitApiError,
        attempts: u32,
    },
    /// Transient retries exhausted. `last_error` is the FINAL attempt's error.
    /// 暫時性重試耗盡。last_error 為最終嘗試的錯誤。
    TransientExhausted {
        last_error: BybitApiError,
        attempts: u32,
    },
}

/// Classify a Bybit API error for retry decisioning.
///
/// DISPATCH-RETRY-1 (E2 review 2026-04-19, Q3): `is_close` parameter removed.
/// Retry-budget divergence for close intents is implemented at the loop level
/// via CLOSE_RETRY_DELAY_MS vs RETRY_DELAY_MS (see run_dispatch_retry caller);
/// classification itself is symmetric because retry cannot resurrect a missing
/// position/order identity in either direction.
///
/// 為重試決策分類 Bybit API 錯誤。DISPATCH-RETRY-1（E2 審查 2026-04-19, Q3）：
/// 移除 `is_close` 參數。關倉的重試預算差異在迴圈層面以 CLOSE_RETRY_DELAY_MS
/// 與 RETRY_DELAY_MS 區分（見 run_dispatch_retry 的 caller）；分類本身對稱，
/// 因重試在兩種方向都無法救回已消失的倉位/訂單識別。
pub(super) fn classify_dispatch_error(err: &BybitApiError) -> DispatchOutcome {
    match err {
        // Network / HTTP / parse — assume transient and worth retry.
        // order_link_id idempotency guarantees a retry after mid-flight parse
        // failure on a successful response is dedup-safe (returns same order).
        //
        // 網路/HTTP/解析 — 視為暫時性，值得重試。成功響應的傳輸途中解析失敗
        // 也安全：order_link_id 冪等保證重試會返回同一訂單。
        BybitApiError::Transport(_) => DispatchOutcome::Transient,
        BybitApiError::JsonParse(_) => DispatchOutcome::Transient,

        // Credentials / signing — configuration bug, retry is futile.
        // 憑證/簽名 — 配置問題，重試無意義。
        BybitApiError::NoCredentials => DispatchOutcome::Structural,
        BybitApiError::SigningError(_) => DispatchOutcome::Structural,

        BybitApiError::Business {
            ret_code, ret_msg, ..
        } => classify_business_retcode(*ret_code, ret_msg),
    }
}

/// Classify a Bybit business retCode into a DispatchOutcome.
/// Extracted for pure-data testability.
///
/// 將 Bybit 業務 retCode 分類為 DispatchOutcome。提取為純資料以利測試。
fn classify_business_retcode(ret_code: i64, ret_msg: &str) -> DispatchOutcome {
    match ret_code {
        // Rate limit — classic transient.
        // 限流 — 典型暫時性。
        10006 => DispatchOutcome::Transient,

        // Bybit server maintenance / overload family — transient.
        // Bybit 伺服器維護/過載族 — 暫時性。
        10016 | 10017 | 10018 | 10019 => DispatchOutcome::Transient,

        // InvalidParam — usually structural, but Bybit returns 10001 for
        // duplicate order_link_id which (thanks to idempotency guarantee) is
        // equivalent to "already placed" → NoOp.
        //
        // E2 review 2026-04-19: narrowed substring match from {"duplicate",
        // "order_link_id"} to {"duplicate"} ONLY. The bare "order_link_id"
        // match was overly permissive — e.g. retMsg "invalid order_link_id
        // format" is structural (bad client-side format) but would be
        // misclassified as NoOp under the old rule, silently succeeding on a
        // genuinely broken request.
        //
        // InvalidParam — 通常結構性，但 Bybit 對重複 order_link_id 也回 10001；
        // 因為冪等保證，視為「已下單」→ NoOp。
        //
        // E2 審查 2026-04-19：子串匹配從 {"duplicate", "order_link_id"} 收窄為
        // 僅 {"duplicate"}。裸 "order_link_id" 匹配過寬 — 例如 "invalid
        // order_link_id format" 是結構性錯誤（client 側格式錯）卻會在舊規則下
        // 誤判為 NoOp，對一個實際壞掉的請求靜默回報成功。
        10001 => {
            if ret_msg.to_ascii_lowercase().contains("duplicate") {
                DispatchOutcome::NoOp
            } else {
                DispatchOutcome::Structural
            }
        }

        // 10002 — InvalidRequest / recv_window.
        // Generic 10002 is structural (malformed request). But Bybit also uses
        // 10002 for client timestamp drift outside recvWindow — that's
        // transient (NTP clock skew; next attempt with fresh ts will pass).
        //
        // E2 review 2026-04-19 (follow-up): substring-match "recv_window" or
        // "timestamp" → Transient, keeps generic 10002 Structural.
        //
        // 10002 — InvalidRequest / recv_window。
        // 一般 10002 為結構性（請求格式錯誤）。但 Bybit 對 client timestamp 超出
        // recvWindow 也回 10002 — 屬暫時性（NTP 時鐘偏差；下次重試 ts 更新後通過）。
        //
        // E2 審查 2026-04-19（後續）：子串匹配 "recv_window" 或 "timestamp"
        // → Transient，一般 10002 保持 Structural。
        10002 => {
            let lower = ret_msg.to_ascii_lowercase();
            if lower.contains("recv_window") || lower.contains("timestamp") {
                DispatchOutcome::Transient
            } else {
                DispatchOutcome::Structural
            }
        }

        // Auth / permissions / IP — structural.
        // 鑑權/權限/IP — 結構性。
        10003 | 10004 | 10005 | 10010 => DispatchOutcome::Structural,

        // Order / position not found on a close → equivalent success.
        // 平倉時找不到訂單/倉位 → 等效成功。
        110001 | 110009 => DispatchOutcome::NoOp,

        // Insufficient balance — not recoverable by retry.
        // 餘額不足 — 重試無法恢復。
        110012 => DispatchOutcome::Structural,

        // Leverage not modified = already at desired state.
        // 槓桿未修改 = 已為目標值。
        110043 => DispatchOutcome::NoOp,

        // Dust / min qty / exceed max qty — structural.
        // 粉塵/最小數量/超過最大數量 — 結構性。
        170124 | 170210 => DispatchOutcome::Structural,

        // Default conservative: unknown business codes → no retry (avoid
        // amplifying unknowable error shapes; operator can investigate logs).
        //
        // 保守預設：未知業務碼 → 不重試（避免放大未知錯誤；operator 可查日誌）。
        _ => DispatchOutcome::Structural,
    }
}

/// Run a dispatch retry loop with the given delay schedule.
///
/// DISPATCH-RETRY-1 (E2 review 2026-04-19): extracted from spawn_order_dispatch
/// so loop-level behaviour is deterministically testable — callers inject any
/// Future-returning closure (test mocks use RefCell<Vec<Result>>; production
/// uses `order_mgr.place_order(...)`).
///
/// `delays_ms` schedules sleeps BETWEEN attempts. Total attempts = 1 initial +
/// `delays_ms.len()` retries. A Transient error on the last attempt returns
/// `TransientExhausted`; NoOp and Structural return immediately with the
/// attempt count and last error.
///
/// Per-attempt debug! and per-retry warn! are emitted here for locality with
/// the sleep. The caller emits Ok/NoOp/Structural/Exhaustion summary logs
/// based on the returned variant.
///
/// 以給定延遲表執行派發重試迴圈。DISPATCH-RETRY-1（E2 審查 2026-04-19）：
/// 從 spawn_order_dispatch 抽出，使迴圈級行為可確定性測試 — caller 注入任意
/// 返回 Future 的 closure（測試用 RefCell<Vec<Result>>；生產用 `order_mgr.place_order(...)`）。
///
/// `delays_ms` 排定嘗試之間的睡眠。總嘗試數 = 1 次初始 + `delays_ms.len()` 次重試。
/// 最後一次嘗試的 Transient 錯誤會返回 `TransientExhausted`；NoOp 與 Structural
/// 立即返回並附嘗試次數與最終錯誤。
///
/// 每次嘗試的 debug! 與每次重試的 warn! 在此處發出以與 sleep 保持局部性。
/// caller 依返回變體發出 Ok/NoOp/Structural/Exhaustion 的摘要日誌。
pub(super) async fn run_dispatch_retry<T, F, Fut>(
    delays_ms: &[u64],
    symbol: &str,
    order_link_id: &str,
    mut place_fn: F,
) -> DispatchRetryResult<T>
where
    F: FnMut(u32) -> Fut,
    Fut: std::future::Future<Output = Result<T, BybitApiError>>,
{
    let mut attempt: u32 = 0;
    loop {
        debug!(
            symbol = %symbol,
            order_link_id = %order_link_id,
            attempt = attempt,
            "order dispatch attempt / 訂單派發嘗試"
        );
        match place_fn(attempt).await {
            Ok(value) => {
                return DispatchRetryResult::Ok {
                    value,
                    attempts: attempt + 1,
                };
            }
            Err(e) => {
                let outcome = classify_dispatch_error(&e);
                match outcome {
                    DispatchOutcome::NoOp => {
                        return DispatchRetryResult::NoOp {
                            last_error: e,
                            attempts: attempt + 1,
                        };
                    }
                    DispatchOutcome::Structural => {
                        return DispatchRetryResult::Structural {
                            last_error: e,
                            attempts: attempt + 1,
                        };
                    }
                    DispatchOutcome::Transient => {
                        if (attempt as usize) >= delays_ms.len() {
                            return DispatchRetryResult::TransientExhausted {
                                last_error: e,
                                attempts: attempt + 1,
                            };
                        }
                        let delay_ms = delays_ms[attempt as usize];
                        let (ret_code_opt, ret_msg_opt): (Option<i64>, Option<String>) = match &e {
                            BybitApiError::Business {
                                ret_code, ret_msg, ..
                            } => (Some(*ret_code), Some(ret_msg.clone())),
                            _ => (None, None),
                        };
                        warn!(
                            symbol = %symbol,
                            order_link_id = %order_link_id,
                            ret_code = ret_code_opt,
                            ret_msg = ret_msg_opt.as_deref(),
                            error = %e,
                            attempt = attempt + 1,
                            next_delay_ms = delay_ms,
                            "order dispatch transient error, retrying / 訂單派發暫時性錯誤，重試中"
                        );
                        tokio::time::sleep(Duration::from_millis(delay_ms)).await;
                        attempt += 1;
                    }
                }
            }
        }
    }
}

/// Spawn the order dispatch task and return the pending order receiver (exchange mode).
/// 啟動訂單派發任務並返回待處理訂單接收端（交易所模式）。
pub(super) fn spawn_order_dispatch(
    pipeline: &mut TickPipeline,
    shared_client: Option<&Arc<BybitRestClient>>,
    shared_instruments: Option<&Arc<InstrumentInfoCache>>,
    enable_dispatch: bool,
) -> Option<mpsc::UnboundedReceiver<PendingOrder>> {
    if !enable_dispatch {
        return None;
    }
    let client = match shared_client {
        Some(c) => c,
        None => {
            warn!("order dispatch enabled but no API credentials — skipping");
            return None;
        }
    };
    let icache = match shared_instruments {
        Some(i) => i,
        None => {
            warn!("order dispatch enabled but no instrument cache — skipping");
            return None;
        }
    };

    use crate::order_manager::{
        CreateOrderRequest, OrderCategory, OrderManager, OrderSide, OrderType,
    };
    let (shadow_tx, mut shadow_rx) =
        mpsc::unbounded_channel::<crate::tick_pipeline::OrderDispatchRequest>();
    pipeline.set_shadow_channel(shadow_tx);

    // Arc-wrapped so the retry closure can clone it per attempt without
    // consuming the captured binding (FnMut requires repeatable calls).
    // DISPATCH-RETRY-1 (E2 follow-up 2026-04-19).
    //
    // 以 Arc 包裹：重試 closure 每次嘗試可複製 Arc 而不消耗捕獲綁定
    // （FnMut 要求可重複呼叫）。DISPATCH-RETRY-1（E2 後續 2026-04-19）。
    let order_mgr = Arc::new(OrderManager::new(Arc::clone(client), Arc::clone(icache)));
    let icache_for_check = Arc::clone(icache);
    let (pending_reg_tx, pending_reg_rx) = mpsc::unbounded_channel::<PendingOrder>();

    tokio::spawn(async move {
        while let Some(req) = shadow_rx.recv().await {
            if req.qty <= 0.0 {
                warn!(symbol = %req.symbol, "order dispatch skipped: qty=0");
                continue;
            }

            // M-1 (2026-04-11) audit fix: pre-flight notional check for Market orders.
            // Bybit V5 enforces a min notional (typically 5 USDT) but local validate_order
            // skips that branch when req.price is None (Market orders carry no limit price).
            // Use OrderDispatchRequest.price (last tick reference price) as a proxy for notional.
            // Without this, sub-min orders round-trip to Bybit only to fail with retCode=10001.
            // M-1 審計修復：市價單的名義值預檢。Bybit V5 強制最小名義值（通常 5 USDT）但
            // 本地 validate_order 在 req.price=None（市價單無限價）時跳過該檢查。使用
            // OrderDispatchRequest.price（最近 tick 參考價）作為名義值代理。
            // 否則低於最小值的訂單會空跑到 Bybit 才被 retCode=10001 拒絕。
            if let Some(spec) = icache_for_check.get(&req.symbol) {
                if spec.min_notional > 0.0 && req.price > 0.0 {
                    let est_notional = req.qty * req.price;
                    if est_notional < spec.min_notional {
                        warn!(
                            symbol = %req.symbol,
                            qty = req.qty,
                            ref_price = req.price,
                            est_notional = est_notional,
                            min_notional = spec.min_notional,
                            "order dispatch skipped: notional below exchange minimum / 訂單跳過：名義值低於交易所最小值"
                        );
                        continue;
                    }
                }
            }
            // EXT-1: Register pending order BEFORE placing (for exchange mode)
            if req.is_primary {
                let now_ms = openclaw_core::now_ms();
                let _ = pending_reg_tx.send(PendingOrder {
                    order_link_id: req.order_link_id.clone(),
                    symbol: req.symbol.clone(),
                    is_long: req.is_long,
                    qty: req.qty,
                    strategy: req.strategy.clone(),
                    sent_ts_ms: now_ms,
                    cum_filled_qty: 0.0,
                    is_close: req.is_close,
                    // FILL-CONTEXT-LINKAGE-1: mirror OrderDispatchRequest.context_id
                    // so the WS-fill handler can pass it to apply_confirmed_fill.
                    // FILL-CONTEXT-LINKAGE-1：鏡射 OrderDispatchRequest.context_id，
                    // WS 成交處理器再傳給 apply_confirmed_fill。
                    context_id: req.context_id.clone(),
                    // EDGE-P2-3 Phase 1B-3.1: mirror order_type + time_in_force
                    // so the sweep can distinguish Market vs resting PostOnly.
                    // EDGE-P2-3 Phase 1B-3.1：鏡射 order_type + time_in_force，
                    // 便於逾時清理區分 Market 與掛中 PostOnly。
                    order_type: req.order_type.clone(),
                    time_in_force: req.time_in_force,
                    // EDGE-P2-3 Phase 1B-3.2: per-order maker sweep timeout.
                    // EDGE-P2-3 Phase 1B-3.2：每單 maker sweep 逾時。
                    maker_timeout_ms: req.maker_timeout_ms,
                });
            }
            let side = if req.is_long {
                OrderSide::Buy
            } else {
                OrderSide::Sell
            };
            let create_req = CreateOrderRequest {
                category: OrderCategory::Linear,
                symbol: req.symbol.clone(),
                side,
                order_type: if req.order_type.eq_ignore_ascii_case("limit") {
                    OrderType::Limit
                } else {
                    OrderType::Market
                },
                qty: req.qty,
                price: req.limit_price,
                time_in_force: req.time_in_force,
                reduce_only: if req.is_close { Some(true) } else { None },
                close_on_trigger: None,
                order_link_id: Some(req.order_link_id.clone()),
                trigger_price: None,
                trigger_direction: None,
                // I-08 雙軌止損：forward broker-side SL/TP only on primary opens
                take_profit: if req.is_primary && !req.is_close {
                    req.take_profit
                } else {
                    None
                },
                stop_loss: if req.is_primary && !req.is_close {
                    req.stop_loss
                } else {
                    None
                },
                tp_trigger_by: None,
                sl_trigger_by: None,
            };
            let dispatch_type = if req.is_primary { "primary" } else { "shadow" };
            // DISPATCH-RETRY-1 (2026-04-19): retry loop via run_dispatch_retry helper.
            //   - Open intents use RETRY_DELAY_MS (3 retries, ~4.2 s worst-case sleep).
            //   - Close intents use CLOSE_RETRY_DELAY_MS (2 retries, 500 ms; Q2 fix
            //     avoids amplifying PnL bleed during bleeding-exit retries).
            //   - Same `create_req` cloned per attempt (order_link_id unchanged =
            //     Bybit idempotency key; `reduce_only=true` adds secondary safety
            //     on close retries).
            //
            // DISPATCH-RETRY-1（2026-04-19）：透過 run_dispatch_retry helper 重試。
            //   - 開倉意圖使用 RETRY_DELAY_MS（3 次重試，worst-case ~4.2s 睡眠）。
            //   - 關倉意圖使用 CLOSE_RETRY_DELAY_MS（2 次重試，500ms；Q2 修復以
            //     避免出血倉重試放大 PnL）。
            //   - 每次嘗試複製同一 `create_req`（order_link_id 不變 = Bybit 冪等鍵；
            //     關倉重試 `reduce_only=true` 提供二級保護）。
            let delays: &[u64] = if req.is_close {
                &CLOSE_RETRY_DELAY_MS
            } else {
                &RETRY_DELAY_MS
            };
            let retry_result = run_dispatch_retry(
                delays,
                &req.symbol,
                &req.order_link_id,
                |_attempt| {
                    let req_for_attempt = create_req.clone();
                    let om = Arc::clone(&order_mgr);
                    // `async move` captures the Arc clone + cloned request by
                    // value. Each retry gets a fresh Future; the original
                    // `order_mgr` Arc binding stays alive in the outer closure
                    // for the next iteration.
                    //
                    // `async move` 捕獲 Arc 複製與複製後的請求（by value）。
                    // 每次重試產生新的 Future；原始 `order_mgr` Arc 綁定保留在
                    // 外層 closure 供下次迭代使用。
                    async move { om.place_order(req_for_attempt).await }
                },
            )
            .await;

            // Summary logging per outcome. retCode extraction lives here so the
            // generic helper stays untyped over log field shapes.
            //
            // 依結果類型發摘要日誌。retCode 解析集中於此，保留 helper 在日誌欄位
            // 類型上的通用性。
            match retry_result {
                DispatchRetryResult::Ok { value, attempts } => {
                    info!(
                        symbol = %req.symbol,
                        order_id = %value.order_id,
                        order_link_id = %req.order_link_id,
                        dispatch_type = dispatch_type,
                        close = req.is_close,
                        attempts = attempts,
                        "order dispatched / 訂單已派發"
                    );
                }
                DispatchRetryResult::NoOp {
                    last_error,
                    attempts,
                } => {
                    let (ret_code_opt, ret_msg_opt): (Option<i64>, Option<String>) =
                        match &last_error {
                            BybitApiError::Business {
                                ret_code, ret_msg, ..
                            } => (Some(*ret_code), Some(ret_msg.clone())),
                            _ => (None, None),
                        };
                    info!(
                        symbol = %req.symbol,
                        order_link_id = %req.order_link_id,
                        dispatch_type = dispatch_type,
                        close = req.is_close,
                        ret_code = ret_code_opt,
                        ret_msg = ret_msg_opt.as_deref(),
                        attempts = attempts,
                        "order dispatch noop / 訂單派發等效成功"
                    );
                }
                DispatchRetryResult::Structural {
                    last_error,
                    attempts,
                } => {
                    let (ret_code_opt, ret_msg_opt): (Option<i64>, Option<String>) =
                        match &last_error {
                            BybitApiError::Business {
                                ret_code, ret_msg, ..
                            } => (Some(*ret_code), Some(ret_msg.clone())),
                            _ => (None, None),
                        };
                    error!(
                        symbol = %req.symbol,
                        qty = req.qty,
                        order_link_id = %req.order_link_id,
                        dispatch_type = dispatch_type,
                        close = req.is_close,
                        ret_code = ret_code_opt,
                        ret_msg = ret_msg_opt.as_deref(),
                        error = %last_error,
                        attempts = attempts,
                        "order dispatch failed (structural, no retry) / 訂單派發失敗（結構性，不重試）"
                    );
                }
                DispatchRetryResult::TransientExhausted {
                    last_error,
                    attempts,
                } => {
                    let (ret_code_opt, ret_msg_opt): (Option<i64>, Option<String>) =
                        match &last_error {
                            BybitApiError::Business {
                                ret_code, ret_msg, ..
                            } => (Some(*ret_code), Some(ret_msg.clone())),
                            _ => (None, None),
                        };
                    error!(
                        symbol = %req.symbol,
                        qty = req.qty,
                        order_link_id = %req.order_link_id,
                        dispatch_type = dispatch_type,
                        close = req.is_close,
                        ret_code = ret_code_opt,
                        ret_msg = ret_msg_opt.as_deref(),
                        error = %last_error,
                        attempts = attempts,
                        "order dispatch failed (transient retry exhausted) / 訂單派發失敗（暫時性重試耗盡）"
                    );
                }
            }
        }
    });
    info!("order dispatch mode active / 訂單派發模式已啟用");
    Some(pending_reg_rx)
}

// ---------------------------------------------------------------------------
// Tests / 測試 (DISPATCH-RETRY-1)
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::bybit_rest_client::BybitApiError;
    use serde_json::json;

    /// Build a Business error helper for tests.
    /// 測試輔助：構造 Business 錯誤。
    fn biz(ret_code: i64, ret_msg: &str) -> BybitApiError {
        BybitApiError::Business {
            ret_code,
            ret_msg: ret_msg.to_string(),
            response: json!({"retCode": ret_code, "retMsg": ret_msg}),
        }
    }

    #[test]
    fn test_retry_delay_constants() {
        // Lock in the retry budget: 3 retries with exponential backoff 200/800/3200 ms.
        // 鎖定重試預算：3 次重試，指數退避 200/800/3200 ms。
        assert_eq!(RETRY_DELAY_MS, [200u64, 800, 3200]);
        assert_eq!(RETRY_DELAY_MS.len(), 3);
    }

    #[test]
    fn test_classify_transport_error() {
        // Deterministic construction of a reqwest::Error without real network I/O:
        // issue a `send()` with a 1 ns timeout against localhost; it reliably errors
        // out via the reqwest timeout/builder pipeline. We use a dedicated
        // current-thread runtime so the test remains synchronous.
        //
        // 不走真實網路的確定性 reqwest::Error 構造：對 localhost 用 1 ns timeout 的
        // send() — 可靠觸發 reqwest timeout/builder 錯誤。使用專用 current-thread
        // runtime 使測試保持同步。
        let rt = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .unwrap();
        let result = rt.block_on(async {
            reqwest::Client::builder()
                .timeout(Duration::from_nanos(1))
                .build()
                .unwrap()
                .get("http://127.0.0.1:1/")
                .send()
                .await
        });
        let err = result.expect_err("1 ns timeout must produce a reqwest::Error");
        let api_err: BybitApiError = BybitApiError::Transport(err);
        assert_eq!(
            classify_dispatch_error(&api_err),
            DispatchOutcome::Transient
        );
    }

    #[test]
    fn test_classify_json_parse_error() {
        let parse_err: serde_json::Error = serde_json::from_str::<serde_json::Value>("not-json")
            .err()
            .unwrap();
        let api_err: BybitApiError = BybitApiError::JsonParse(parse_err);
        assert_eq!(
            classify_dispatch_error(&api_err),
            DispatchOutcome::Transient
        );
    }

    #[test]
    fn test_classify_no_credentials() {
        let e = BybitApiError::NoCredentials;
        assert_eq!(
            classify_dispatch_error(&e),
            DispatchOutcome::Structural
        );
    }

    #[test]
    fn test_classify_signing_error() {
        let e = BybitApiError::SigningError("bad HMAC".into());
        assert_eq!(
            classify_dispatch_error(&e),
            DispatchOutcome::Structural
        );
    }

    #[test]
    fn test_classify_ip_rate_limit_is_transient() {
        let e = biz(10006, "Too many requests");
        assert_eq!(
            classify_dispatch_error(&e),
            DispatchOutcome::Transient
        );
    }

    #[test]
    fn test_classify_duplicate_order_link_id_is_noop() {
        let e = biz(10001, "duplicate order_link_id rejected");
        assert_eq!(classify_dispatch_error(&e), DispatchOutcome::NoOp);
    }

    #[test]
    fn test_classify_invalid_param_is_structural() {
        let e = biz(10001, "invalid param: qty must be > 0");
        assert_eq!(
            classify_dispatch_error(&e),
            DispatchOutcome::Structural
        );
    }

    #[test]
    fn test_classify_api_key_invalid_is_structural() {
        let e = biz(10003, "api key invalid");
        assert_eq!(
            classify_dispatch_error(&e),
            DispatchOutcome::Structural
        );
    }

    #[test]
    fn test_classify_order_not_found_is_noop() {
        let e = biz(110001, "order not exists");
        // NoOp — retry cannot resurrect a missing order identity, and on close
        // attempts the position is effectively already gone. Classifier is
        // direction-symmetric (DISPATCH-RETRY-1 Q3 2026-04-19).
        //
        // NoOp — 重試無法救回已消失的訂單識別，且關倉時倉位實際已消失。
        // 分類器在方向上對稱（DISPATCH-RETRY-1 Q3 2026-04-19）。
        assert_eq!(classify_dispatch_error(&e), DispatchOutcome::NoOp);
    }

    #[test]
    fn test_classify_position_not_found_is_noop() {
        let e = biz(110009, "position idx not match");
        assert_eq!(classify_dispatch_error(&e), DispatchOutcome::NoOp);
    }

    #[test]
    fn test_classify_insufficient_balance_is_structural() {
        let e = biz(110012, "insufficient available balance");
        assert_eq!(
            classify_dispatch_error(&e),
            DispatchOutcome::Structural
        );
    }

    #[test]
    fn test_classify_leverage_not_modified_is_noop() {
        let e = biz(110043, "leverage not modified");
        assert_eq!(classify_dispatch_error(&e), DispatchOutcome::NoOp);
    }

    #[test]
    fn test_classify_dust_min_qty_is_structural() {
        let e = biz(170124, "order qty below min");
        assert_eq!(
            classify_dispatch_error(&e),
            DispatchOutcome::Structural
        );
    }

    #[test]
    fn test_classify_bybit_server_busy_is_transient() {
        let e = biz(10016, "server busy");
        assert_eq!(
            classify_dispatch_error(&e),
            DispatchOutcome::Transient
        );
        // Sibling codes in the same transient family / 同族暫時性碼
        assert_eq!(
            classify_dispatch_error(&biz(10017, "gateway timeout")),
            DispatchOutcome::Transient
        );
        assert_eq!(
            classify_dispatch_error(&biz(10018, "service unavailable")),
            DispatchOutcome::Transient
        );
        assert_eq!(
            classify_dispatch_error(&biz(10019, "request timeout")),
            DispatchOutcome::Transient
        );
    }

    #[test]
    fn test_classify_unknown_retcode_is_structural() {
        // Conservative default — unknown codes must NOT retry to avoid amplifying
        // unmodeled error shapes against the exchange.
        // 保守預設 — 未知碼禁止重試，避免對交易所放大未建模錯誤。
        let e = biz(99999, "mystery error");
        assert_eq!(
            classify_dispatch_error(&e),
            DispatchOutcome::Structural
        );
    }

    #[test]
    fn test_classify_exceed_max_qty_is_structural() {
        let e = biz(170210, "order qty exceeds max");
        assert_eq!(
            classify_dispatch_error(&e),
            DispatchOutcome::Structural
        );
    }

    #[test]
    fn test_classify_sign_error_is_structural() {
        let e = biz(10004, "sign not match");
        assert_eq!(
            classify_dispatch_error(&e),
            DispatchOutcome::Structural
        );
    }

    #[test]
    fn test_classify_unmatched_ip_is_structural() {
        let e = biz(10010, "unmatched ip");
        assert_eq!(
            classify_dispatch_error(&e),
            DispatchOutcome::Structural
        );
    }

    // -----------------------------------------------------------------
    // DISPATCH-RETRY-1 E2 follow-up tests (2026-04-19)
    // 分類收窄 + 迴圈級行為
    // -----------------------------------------------------------------

    #[test]
    fn test_classify_10001_invalid_order_link_id_format_is_structural() {
        // E2 review 2026-04-19: substring match narrowed from
        // {"duplicate", "order_link_id"} to {"duplicate"} only. Previously a
        // retMsg like "invalid order_link_id format" would fall through the
        // `order_link_id` substring arm → NoOp, silently success-equivalent
        // for a genuinely structural client-side bug. Now correctly Structural.
        //
        // E2 審查 2026-04-19：子串收窄為僅 {"duplicate"}。之前 "invalid
        // order_link_id format" 會誤判為 NoOp（靜默回報成功，實為 client 側
        // 結構性錯誤），現正確歸為 Structural。
        let e = biz(10001, "invalid order_link_id format");
        assert_eq!(
            classify_dispatch_error(&e),
            DispatchOutcome::Structural
        );
        // Additional narrow check: case-insensitive "DUPLICATE" still matches.
        // 補充：大寫 "DUPLICATE" 仍匹配（子串比對前 to_ascii_lowercase）。
        let e_upper = biz(10001, "DUPLICATE order_link_id");
        assert_eq!(
            classify_dispatch_error(&e_upper),
            DispatchOutcome::NoOp
        );
    }

    #[test]
    fn test_classify_10002_recv_window_drift_is_transient() {
        // Bybit uses 10002 both for malformed requests (Structural) and for
        // client timestamp drift outside recvWindow (Transient — NTP skew;
        // next retry with fresh ts will pass). Substring match discriminates.
        //
        // Bybit 對 10002 兼作請求格式錯誤（Structural）與 client timestamp
        // 超出 recvWindow（Transient — NTP 偏差；下次 ts 更新後重試可通過）。
        // 子串匹配區分兩種情況。
        assert_eq!(
            classify_dispatch_error(&biz(10002, "invalid recv_window")),
            DispatchOutcome::Transient
        );
        assert_eq!(
            classify_dispatch_error(&biz(
                10002,
                "timestamp for this request is outside of recvWindow"
            )),
            DispatchOutcome::Transient
        );
    }

    #[test]
    fn test_classify_10002_generic_is_structural() {
        // Without drift keywords, 10002 stays Structural (deployment bug).
        // 無漂移關鍵字時 10002 保持 Structural（部署/參數錯誤）。
        assert_eq!(
            classify_dispatch_error(&biz(10002, "generic invalid request")),
            DispatchOutcome::Structural
        );
    }

    // Loop-level tests (E2 follow-up): inject scripted Result sequences via
    // RefCell to verify run_dispatch_retry control flow deterministically.
    //
    // 迴圈級測試（E2 後續）：透過 RefCell 注入受控 Result 序列，確定性地
    // 驗證 run_dispatch_retry 的控制流。

    #[tokio::test]
    async fn test_run_dispatch_retry_ok_first_try_attempts_1() {
        use std::cell::RefCell;
        let call_count = RefCell::new(0u32);
        let result = run_dispatch_retry::<i32, _, _>(
            &[10, 10, 10],
            "BTCUSDT",
            "oLidTest",
            |_attempt| {
                *call_count.borrow_mut() += 1;
                async move { Ok::<i32, BybitApiError>(42) }
            },
        )
        .await;
        match result {
            DispatchRetryResult::Ok { value, attempts } => {
                assert_eq!(value, 42);
                assert_eq!(attempts, 1, "first-try success must record attempts=1");
            }
            other => panic!("expected Ok, got {:?}", other),
        }
        assert_eq!(*call_count.borrow(), 1);
    }

    #[tokio::test]
    async fn test_run_dispatch_retry_ok_on_third_attempt_records_attempts_3() {
        use std::cell::RefCell;
        let results: RefCell<Vec<Result<i32, BybitApiError>>> = RefCell::new(vec![
            Err(biz(10006, "transient 1")),
            Err(biz(10006, "transient 2")),
            Ok(99),
        ]);
        let result = run_dispatch_retry::<i32, _, _>(
            &[5, 5, 5],
            "BTCUSDT",
            "oLid",
            |_| {
                let r = results.borrow_mut().remove(0);
                async move { r }
            },
        )
        .await;
        match result {
            DispatchRetryResult::Ok { value, attempts } => {
                assert_eq!(value, 99);
                assert_eq!(
                    attempts, 3,
                    "Ok after 2 transient retries must record attempts=3"
                );
            }
            other => panic!("expected Ok, got {:?}", other),
        }
    }

    #[tokio::test]
    async fn test_run_dispatch_retry_structural_breaks_without_retry() {
        use std::cell::RefCell;
        let call_count = RefCell::new(0u32);
        let result = run_dispatch_retry::<(), _, _>(
            &[5, 5, 5],
            "BTCUSDT",
            "oLid",
            |_| {
                *call_count.borrow_mut() += 1;
                async move {
                    Err::<(), BybitApiError>(biz(110012, "insufficient balance"))
                }
            },
        )
        .await;
        match result {
            DispatchRetryResult::Structural { attempts, .. } => {
                assert_eq!(attempts, 1, "structural on first try must break immediately");
            }
            other => panic!("expected Structural, got {:?}", other),
        }
        assert_eq!(
            *call_count.borrow(),
            1,
            "structural outcome must NOT trigger any retry"
        );
    }

    #[tokio::test]
    async fn test_run_dispatch_retry_noop_on_second_attempt_records_attempts_2() {
        use std::cell::RefCell;
        // Sequence: transient → NoOp (duplicate). Noop must break retry loop
        // without consuming further attempts.
        //
        // 序列：transient → NoOp（duplicate）。NoOp 必須中斷重試迴圈，不再消耗
        // 後續嘗試。
        let results: RefCell<Vec<Result<(), BybitApiError>>> = RefCell::new(vec![
            Err(biz(10006, "rate limit")),
            Err(biz(10001, "duplicate order_link_id rejected")),
            Err(biz(99999, "should_not_be_reached")), // guard — NoOp must stop here
        ]);
        let result = run_dispatch_retry::<(), _, _>(
            &[5, 5, 5],
            "BTCUSDT",
            "oLid",
            |_| {
                let r = results.borrow_mut().remove(0);
                async move { r }
            },
        )
        .await;
        match result {
            DispatchRetryResult::NoOp {
                last_error,
                attempts,
            } => {
                assert_eq!(attempts, 2, "NoOp on 2nd attempt must record attempts=2");
                match last_error {
                    BybitApiError::Business { ret_msg, .. } => {
                        assert!(
                            ret_msg.to_ascii_lowercase().contains("duplicate"),
                            "last_error should be the NoOp-triggering duplicate"
                        );
                    }
                    _ => panic!("expected Business error"),
                }
            }
            other => panic!("expected NoOp, got {:?}", other),
        }
        // Guard row should still be in the stack.
        // 守衛列應仍在 stack 中（確認 NoOp 已中斷）。
        assert_eq!(results.borrow().len(), 1);
    }

    #[tokio::test]
    async fn test_run_dispatch_retry_transient_exhaustion_returns_last_error() {
        use std::cell::RefCell;
        // 4 transient errors → exhaust RETRY_DELAY_MS (3 retries → 4 total
        // attempts). TransientExhausted.last_error must be the FINAL attempt's
        // error (#4), not the first.
        //
        // 4 個 transient 錯誤 → 耗盡 RETRY_DELAY_MS（3 次重試 → 4 次總嘗試）。
        // TransientExhausted.last_error 必須是最終嘗試的錯誤（#4），非首次。
        let results: RefCell<Vec<Result<(), BybitApiError>>> = RefCell::new(vec![
            Err(biz(10006, "rate limit #1")),
            Err(biz(10006, "rate limit #2")),
            Err(biz(10006, "rate limit #3")),
            Err(biz(10006, "rate limit #4-final")),
        ]);
        // Use tiny delays for fast test (schedule length equivalent to
        // RETRY_DELAY_MS = 3 retries).
        // 測試用極短延遲（表長等於 RETRY_DELAY_MS = 3 次重試）。
        let result = run_dispatch_retry::<(), _, _>(
            &[1, 1, 1],
            "BTCUSDT",
            "oLid",
            |_| {
                let r = results.borrow_mut().remove(0);
                async move { r }
            },
        )
        .await;
        match result {
            DispatchRetryResult::TransientExhausted {
                last_error,
                attempts,
            } => {
                assert_eq!(
                    attempts, 4,
                    "3 retries + 1 initial = 4 total attempts on exhaustion"
                );
                match last_error {
                    BybitApiError::Business { ret_msg, .. } => {
                        assert_eq!(
                            ret_msg, "rate limit #4-final",
                            "TransientExhausted.last_error must be the FINAL error, not the first"
                        );
                    }
                    _ => panic!("expected Business error"),
                }
            }
            other => panic!("expected TransientExhausted, got {:?}", other),
        }
        assert_eq!(results.borrow().len(), 0, "all 4 scripted results consumed");
    }

    #[tokio::test]
    async fn test_run_dispatch_retry_close_budget_caps_at_3_attempts() {
        use std::cell::RefCell;
        // CLOSE_RETRY_DELAY_MS has length 2 → total attempts = 3 (1 initial +
        // 2 retries). Proves Q2 budget divergence: close paths exhaust faster.
        //
        // CLOSE_RETRY_DELAY_MS 長度為 2 → 總嘗試數 3（1 初始 + 2 重試）。
        // 驗證 Q2 預算差異：close 路徑更快耗盡。
        assert_eq!(CLOSE_RETRY_DELAY_MS.len(), 2);
        let call_count = RefCell::new(0u32);
        let result = run_dispatch_retry::<(), _, _>(
            &CLOSE_RETRY_DELAY_MS,
            "BTCUSDT",
            "oLid-close",
            |_| {
                *call_count.borrow_mut() += 1;
                async move {
                    Err::<(), BybitApiError>(biz(10006, "rate limit"))
                }
            },
        )
        .await;
        match result {
            DispatchRetryResult::TransientExhausted { attempts, .. } => {
                assert_eq!(
                    attempts, 3,
                    "close budget = 1 initial + 2 retries (Q2 E2 fix)"
                );
            }
            other => panic!("expected TransientExhausted, got {:?}", other),
        }
        assert_eq!(*call_count.borrow(), 3);
    }

    #[test]
    fn test_close_retry_delay_constants() {
        // Q2 (E2 review 2026-04-19): close retries use [100, 400] = 500 ms
        // total sleep, 2 retries max. Pinned to catch unintended widening.
        //
        // Q2（E2 審查 2026-04-19）：關倉重試用 [100, 400] = 500ms 總睡眠，最多
        // 2 次重試。鎖定常數以偵測意外放寬。
        assert_eq!(CLOSE_RETRY_DELAY_MS, [100u64, 400]);
        assert_eq!(CLOSE_RETRY_DELAY_MS.len(), 2);
        // Invariant: close budget must be strictly smaller than open budget
        // 不變式：關倉預算必須嚴格小於開倉預算
        assert!(CLOSE_RETRY_DELAY_MS.len() < RETRY_DELAY_MS.len());
        let close_total: u64 = CLOSE_RETRY_DELAY_MS.iter().sum();
        let open_total: u64 = RETRY_DELAY_MS.iter().sum();
        assert!(
            close_total < open_total,
            "close retry sleep total must be < open retry sleep total (Q2 invariant)"
        );
    }
}
