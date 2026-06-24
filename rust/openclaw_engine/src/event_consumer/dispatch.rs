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

use super::types::{PendingOrder, PendingOrderEvent};
use crate::bybit_rest_client::{BybitApiError, BybitRestClient};
use crate::instrument_info::InstrumentInfoCache;
use crate::order_manager::TimeInForce;
use crate::strategies::common::canonical_close_maker_reason;
use crate::tick_pipeline::{CloseMakerFillAudit, OrderDispatchRequest, TickPipeline};
use openclaw_core::governance_core::LeaseOutcome;
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::mpsc;
use tracing::{debug, error, info, warn};

// ---------------------------------------------------------------------------
// Retry policy (DISPATCH-RETRY-1, 2026-04-19) / 重試策略
// ---------------------------------------------------------------------------

// P1-07（cold audit pkg B）：OPEN（create）重試已移除 — operator decision STRICT
// FAIL-CLOSED。OPEN 路徑現以空 delay slice 走 run_dispatch_retry（單次嘗試，0 重試）。
// 原 RETRY_DELAY_MS = [200, 800, 3200]（3 重試）已刪除（無生產 caller）。
pub(super) const OPEN_NO_RETRY: [u64; 0] = [];

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

/// Per-attempt hard timeout for CLOSE dispatch (ms).
/// Ensures "fast-exit" close retry budget is real wall-clock, not only sleep.
/// 關倉單次派發硬逾時（毫秒），避免「快退場」只限制 sleep 而不限制請求等待。
pub(super) const CLOSE_ATTEMPT_TIMEOUT_MS: u64 = 500;

/// 根據 intent 類型選擇 dispatch retry budget。
///
/// 為什麼獨立成 helper：P1-07 的安全邊界是「open/create 永遠 0 重試」，
/// 不能只靠 call-site 註釋。測試直接鎖此 helper，防止未來把 OPEN 重試表悄悄接回。
pub(super) fn dispatch_retry_delays_for_intent(is_close: bool) -> &'static [u64] {
    if is_close {
        &CLOSE_RETRY_DELAY_MS
    } else {
        &OPEN_NO_RETRY
    }
}

fn send_decision_lease_release(
    pending_reg_tx: &mpsc::UnboundedSender<PendingOrderEvent>,
    req: &OrderDispatchRequest,
    outcome: LeaseOutcome,
    reason: impl Into<String>,
) {
    if !req.is_primary || req.decision_lease_id.is_none() {
        return;
    }
    if let Err(e) = pending_reg_tx.send(PendingOrderEvent::ReleaseDecisionLease {
        order_link_id: req.order_link_id.clone(),
        decision_lease_id: req.decision_lease_id.clone(),
        outcome,
        reason: reason.into(),
        ts_ms: openclaw_core::now_ms(),
    }) {
        warn!(
            order_link_id = %req.order_link_id,
            outcome = ?outcome,
            error = %e,
            "decision lease release event dropped — ExpiryGuardian may need to sweep \
             / 決策租約釋放事件丟失，可能需由 ExpiryGuardian 清理"
        );
    }
}

fn close_maker_audit_for_dispatch_req(req: &OrderDispatchRequest) -> Option<CloseMakerFillAudit> {
    req.close_maker_audit.clone().or_else(|| {
        if req.is_close
            && req.order_type.eq_ignore_ascii_case("limit")
            && req.time_in_force == Some(TimeInForce::PostOnly)
        {
            Some(CloseMakerFillAudit {
                initial_limit_price: req.limit_price,
                eligible_reason: canonical_close_maker_reason(&req.strategy).to_string(),
                fallback_reason: None,
                rate_limit_scope: None,
            })
        } else {
            None
        }
    })
}

fn send_close_maker_dispatch_failed(
    pending_reg_tx: &mpsc::UnboundedSender<PendingOrderEvent>,
    req: &OrderDispatchRequest,
    terminal_status: &str,
    reason: impl Into<String>,
) {
    if !req.is_primary || !req.is_close {
        return;
    }
    let Some(close_maker_audit) = close_maker_audit_for_dispatch_req(req) else {
        return;
    };
    if let Err(e) = pending_reg_tx.send(PendingOrderEvent::DispatchFailed {
        order_link_id: req.order_link_id.clone(),
        symbol: req.symbol.clone(),
        is_long: req.is_long,
        qty: req.qty,
        strategy: req.strategy.clone(),
        context_id: req.context_id.clone(),
        is_close: req.is_close,
        order_type: req.order_type.clone(),
        time_in_force: req.time_in_force,
        maker_timeout_ms: req.maker_timeout_ms,
        close_maker_audit: Some(close_maker_audit),
        terminal_status: terminal_status.to_string(),
        reason: reason.into(),
        ts_ms: openclaw_core::now_ms(),
    }) {
        warn!(
            order_link_id = %req.order_link_id,
            error = %e,
            "close-maker dispatch failure terminal event dropped \
             / close-maker 派發失敗終態事件丟失"
        );
    }
}

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
        // Client-side invariant failure（例如分頁 cursor 不前進 / 超頁數上限）不是交易所
        // 暫時錯，也不是 retCode；重試同一請求只會重撞同一壞狀態，故按 Structural fail-closed。
        BybitApiError::Other(_) => DispatchOutcome::Structural,

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

        // InvalidParam — 通常結構性。Bybit 對重複 order_link_id 也可能回
        // 10001（泛 InvalidParam 帶 retMsg "duplicate"），與 110072（專屬重複碼）
        // 同類。
        //
        // P2-ORDERLINKID-110072 follow-up（2026-06-07，E2/BB flag）：10001+duplicate
        // 由無條件 NoOp 改為 **Structural**，與 110072 arm 對齊。為什麼：原 NoOp
        // 把 open 與 close 都當成功，但 open 單次無重試（OPEN_NO_RETRY），撞重複
        // order_link_id 只可能是 id 撞歷史 = 開倉未成功，絕不可靜默回報成功
        // （silent-success 風險）。預設 Structural 保護 open path fail-closed；
        // close retry 的冪等成功 upgrade（首次 attempt 已達 Bybit、response 丟失，
        // retry 重發同一 id 撞此碼）在 consumption Structural 分支由
        // close_dup_is_idempotent_success 以 is_close guard 處理（見本檔
        // DispatchRetryResult::Structural 分支 + close_dup_is_idempotent_success，
        // 該 helper 同時涵蓋 110072 與 10001+duplicate）。對 close 是同一 observable
        // 成功結果（lease Consumed），無回歸。
        //
        // 歷史背景：E2 審查 2026-04-19 曾把 duplicate 子串匹配從
        // {"duplicate", "order_link_id"} 收窄為僅 {"duplicate"}，以避免
        // "invalid order_link_id format"（結構性 client 格式錯）被誤判。follow-up
        // 後 duplicate 與非-duplicate 的 10001 同歸 Structural，故 classify 層
        // 不再需要區分子串；duplicate 的偵測下移到 consumption 層的
        // close_dup_is_idempotent_success（僅該處需要 close+duplicate 的細分以
        // upgrade 成冪等成功）。retMsg 在此 arm 不再被讀。
        10001 => DispatchOutcome::Structural,

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

        // Order not found on a close → equivalent success. 110009 is not a
        // position-not-found code in the current Bybit V5 table; it means the
        // stop-order count limit was exceeded and must fail closed.
        // 平倉時找不到訂單 → 等效成功。110009 當前官方語意為 stop orders
        // 數量超上限，不是倉位不存在，故不得當 NoOp。
        110001 => DispatchOutcome::NoOp,

        // 110017 ReduceOnlyReject「current position is zero」— reduce-only 平倉
        // 被拒，因交易所端該倉位已不存在。語意上與 110001 的「平倉時訂單
        // 已不在」同屬 close-equivalent success；110009 已移出此族。
        // 同樣歸 NoOp，重試無法救回不存在的倉。
        //
        // 為什麼從 Structural 改為 NoOp（P1-110017-POSITION-DRIFT-CLOSE-LOOP）：
        // 舊分類把 110017 落入 `_ => Structural`，no-retry 但也不收斂；當本地
        // persisted state 與交易所 position truth 漂移（本地殘倉 + 交易所已平）
        // 時，每 tick 的 close 決策重發 reduce-only close → Bybit 持續回 110017
        // → 倉永不本地刪 → 自持迴圈（TRXUSDT demo 案例 ~1.4/sec）。
        // close 的 fail-closed 目的是「不要讓倉沒平掉」；110017 恰證明倉已不在，
        // NoOp + 本地收斂才是 survival-correct（Root Principle 5）。
        //
        // 安全邊界：110017 三種觸發為 (a) 無倉 (b) 方向反 (c) qty>倉量
        // （dict §4.2）。其中 (c) C-1 是災難 case：partial reduce-only close
        // （qty>0 > 實際倉）會回 110017 但倉仍在，裸收斂會誤刪真倉。
        //
        // BB 2026-05-29 APPROVE-WITH-MANDATORY-GUARD（one-way + qty=0 form 安全收斂；
        // 報告 docs/CCAgentWorkSpace/BB/workspace/reports/
        // 2026-05-29--retcode_110017_convergence_semantics.md）：classifier 把 110017
        // 歸 NoOp（no-retry，重試救不回不存在的倉）是正確且自洽的；本地倉收斂則受
        // send_exchange_zero_close 的 MANDATORY guard（is_primary ∧ is_close ∧
        // reduce_only ∧ **qty==0 全平 form** ∧ 110017）保護——qty=0 form 結構性排除
        // C-1（無顯式 qty，Bybit 不會回 qty>size）；one-way mode 排除 C-2（方向/
        // positionIdx 不符）。故收斂只發生在「交易所確認該倉已不在」的安全集。
        110017 => DispatchOutcome::NoOp,

        // Insufficient balance — not recoverable by retry.
        // 餘額不足 — 重試無法恢復。
        110012 => DispatchOutcome::Structural,

        // Leverage not modified = already at desired state.
        // 槓桿未修改 = 已為目標值。
        110043 => DispatchOutcome::NoOp,

        // 110072 OrderLinkedID is duplicate — Bybit 專屬「重複 orderLinkId」碼。
        // 預設 Structural（fail-closed）保護 OPEN path：open 單次無重試（OPEN_NO_RETRY），
        // 撞 110072 只可能是 id 撞歷史 = 開倉未成功，絕不可當成功。
        // close retry 場景（首次 attempt 已成功但 response 丟失、retry 重發同一 id 撞此碼）
        // 的冪等成功 upgrade 在 consumption Structural 分支以 is_close guard 處理
        // （見本檔 DispatchRetryResult::Structural 分支 + close_dup_is_idempotent_success）。
        // 與 110017 不同：110072 **不**觸發本地倉收斂，只把 lease 釋放為 Consumed。
        // BB 2026-06-06 APPROVE-WITH-MANDATORY-GUARD：docs/CCAgentWorkSpace/BB/workspace/reports/
        // 內 110072 報告。語意上與舊 `_ => Structural` 對 110072 相同，顯式化讓
        // classify test 可錨定 + 可發現。
        110072 => DispatchOutcome::Structural,

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

/// P1-110017-POSITION-DRIFT-CLOSE-LOOP：判斷此 NoOp 是否為「交易所端倉位
/// 已 zero」的 reduce-only 平倉（Bybit retCode 110017）。
///
/// 為什麼只認 110017：110017 retMsg「current position is zero」是交易所
/// 對「無倉可 reduce」的權威信號，須觸發本地倉收斂；110001 雖同為 NoOp，
/// 但語意是「訂單找不到」，沿用既有不收斂行為。110009 是 stop-order limit
/// structural failure，不在 NoOp/收斂語意域。
fn noop_is_exchange_zero_position(err: &BybitApiError) -> bool {
    matches!(
        err,
        BybitApiError::Business { ret_code, .. } if *ret_code == 110017
    )
}

/// P1-110017-POSITION-DRIFT-CLOSE-LOOP（BB G-1/G-2）：判斷此 dispatch 是否為
/// reduce-only 平倉。
///
/// 為什麼顯式檢查 reduce_only 而非只看 is_close：本系統 create_req 以
/// `reduce_only: if req.is_close { Some(true) } else { None }` 推導（dispatch.rs
/// create_req），故 is_close==true 即蘊含送出 reduceOnly=true。BB MANDATORY guard
/// 要求收斂條件**顯式**對齊 reduce_only==true（不可只靠 is_close 隱式蘊含），確保
/// 未來若 create_req 的 reduce_only 推導改變時此 guard 仍語意正確。當前兩者等價，
/// 此 helper 把「is_close ⇒ reduce_only」的不變量集中為單一 SSOT。
fn noop_is_reduce_only_close(req: &OrderDispatchRequest) -> bool {
    // is_close==true 在 create_req 對應 reduce_only=Some(true)；二者語意綁定。
    req.is_close
}

/// P2-ORDERLINKID-110072（+ 2026-06-07 follow-up）：判斷此 Structural 結果是否為
/// 「close 重發撞重複 order_link_id」= 冪等成功（首次 close attempt 已達 Bybit、
/// response 丟失，retry 重發同一 id 撞此碼）。
///
/// 涵蓋兩個 duplicate retCode（皆為「重複 order_link_id」同類）：
///   - 110072：Bybit 專屬「OrderLinkedID is duplicate」碼。
///   - 10001 + retMsg contains "duplicate"：泛 InvalidParam 帶 duplicate 訊息。
///     需顯式比對 retMsg；非-duplicate 的 10001（如 "invalid order_link_id
///     format"、"qty must be > 0"）為真結構性錯誤，**不**屬冪等成功。
///
/// 僅 close intent 成立（req.is_close）；open path 維持 fail-closed——open 單次
/// 無重試（OPEN_NO_RETRY），撞重複 order_link_id 只可能是 id 撞歷史 = 開倉未成功，
/// 絕不可當成功（BB 2026-06-06 MANDATORY guard；110072 與 10001+duplicate 同此語意）。
/// 注意：兩碼皆 **不**觸發本地倉收斂——不加入 noop_is_exchange_zero_position；
/// 此處只把 lease 釋放為 Consumed（成功），倉位真相由首次成功 attempt 的
/// WS fill / position update 自然回填。
fn close_dup_is_idempotent_success(req: &OrderDispatchRequest, err: &BybitApiError) -> bool {
    req.is_close
        && match err {
            BybitApiError::Business { ret_code, .. } if *ret_code == 110072 => true,
            BybitApiError::Business {
                ret_code, ret_msg, ..
            } if *ret_code == 10001 => ret_msg.to_ascii_lowercase().contains("duplicate"),
            _ => false,
        }
}

/// P1-110017-POSITION-DRIFT-CLOSE-LOOP：對 reduce-only 平倉收到 110017 時，
/// 向 event consumer 發 ExchangeZeroClose，請求本地倉收斂為 flat。
///
/// BB MANDATORY GUARD（2026-05-29 APPROVE-WITH-MANDATORY-GUARD；報告：
/// docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-29--retcode_110017_convergence_semantics.md）：
/// 110017 在 Bybit V5 **不是零倉專屬碼**，是 ReduceOnlyReject 族，三觸發
/// (a) 無倉 (b) 方向反 (c) **qty > 倉量**。其中 (c) C-1 是災難 case：partial
/// reduce-only close（qty>0 但 > 實際倉）會回 110017 但**倉仍在**——此時收斂
/// 會誤刪真倉。因此收斂前必須滿足全部 AND guard（缺一不收斂）：
///   G-1 is_close==true     —— 僅平倉意圖。
///   G-2 reduce_only==true  —— 本系統 close create_req 必設 reduce_only=Some(true)
///                             （dispatch.rs create_req：is_close ⇒ reduce_only），
///                             此處 is_close 即蘊含 reduce_only；BB 要求顯式對齊，
///                             故 helper noop_is_reduce_only_close 顯式檢查兩者。
///   G-4 qty==0 全平 form   —— **最關鍵**。qty=0 全平 form（reduceOnly+closeOnTrigger，
///                             交易所自行 flatten，不送顯式 qty）下 Bybit 不可能因
///                             「qty>size」回 110017，故 110017 在 qty=0 form 下可靠
///                             等價零倉，C-1 結構性排除。qty>0 partial reduce-only
///                             close 收到 110017（倉可能仍在）→ **絕不收斂**。
///   is_primary             —— paper shadow（fire-and-forget，無交易所倉）不收斂。
///   ret_code==110017       —— 110001 維持原 NoOp 不收斂；110009 非 NoOp。
///
/// G-3 hedge-mode 前提守衛：本收斂僅在 **Bybit one-way mode** 安全（BB §3 已以 4
/// 指紋驗：OrderDispatchRequest 無 positionIdx 欄位 / switch_position_mode 0
/// production caller / demo_state position_idx=None / close side 正確反向）。
/// one-way mode 下 §1 corner case C-2（hedge positionIdx/方向不符回 110017 但倉仍在）
/// **結構性不存在**。⚠️ 若未來啟用 hedge mode（switch_position_mode 被接線），
/// 本收斂路徑 = MANDATORY re-review：C-2 會復活，無 positionIdx-aware 比對會誤刪倉。
///
/// ≥2 連續 110017（BB G-5 recommended，非 mandatory）DEFER：見報告論證——
/// qty==0 form + idempotent 收斂（upsert_position_from_exchange size=0 對已 flat 倉
/// 為 no-op；apply_confirmed_fill 對已移除倉 realized=0 不雙記）已足夠安全，C-3
/// just-opened race 即使單發誤收斂亦會被下一筆交易所 WS PositionUpdate 自癒；新增
/// per-symbol 計數需顯著新可變狀態，複雜度不值。列 follow-up。
fn send_exchange_zero_close(
    pending_reg_tx: &mpsc::UnboundedSender<PendingOrderEvent>,
    req: &OrderDispatchRequest,
    last_error: &BybitApiError,
) {
    // BB MANDATORY GUARD（全 AND，缺一不收斂；防 C-1 誤刪真倉）：
    //   is_primary（非 paper shadow）∧ is_close ∧ reduce_only ∧ qty==0 全平 form
    //   ∧ ret_code==110017。
    let is_qty_zero_full_close = req.qty == 0.0;
    if !req.is_primary
        || !noop_is_reduce_only_close(req)
        || !is_qty_zero_full_close
        || !noop_is_exchange_zero_position(last_error)
    {
        return;
    }
    if let Err(e) = pending_reg_tx.send(PendingOrderEvent::ExchangeZeroClose {
        order_link_id: req.order_link_id.clone(),
        symbol: req.symbol.clone(),
        is_long: req.is_long,
        strategy: req.strategy.clone(),
        ts_ms: openclaw_core::now_ms(),
    }) {
        warn!(
            order_link_id = %req.order_link_id,
            symbol = %req.symbol,
            error = %e,
            "exchange-zero close convergence event dropped — local drift position may persist \
             / 交易所 zero 倉收斂事件丟失，本地漂移倉可能殘留"
        );
    }
}

fn close_dispatch_timeout_error(timeout_ms: u64) -> BybitApiError {
    BybitApiError::Business {
        ret_code: 10019,
        ret_msg: format!("close dispatch timed out after {timeout_ms}ms"),
        response: serde_json::json!({
            "layer": "dispatch",
            "kind": "close_attempt_timeout",
            "timeout_ms": timeout_ms
        }),
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
) -> Option<mpsc::UnboundedReceiver<PendingOrderEvent>> {
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
    // P1-03（cold audit pkg B）：把同一 order_mgr Arc 注入 pipeline 供 CancelAllOrders
    // IPC 命令使用（reuse shared live client，不另建客戶端）。在 move 進 spawn 前 clone。
    pipeline.set_cancel_all_order_mgr(Arc::clone(&order_mgr));
    let icache_for_check = Arc::clone(icache);
    let (pending_reg_tx, pending_reg_rx) = mpsc::unbounded_channel::<PendingOrderEvent>();

    tokio::spawn(async move {
        while let Some(req) = shadow_rx.recv().await {
            let is_qty_zero_full_close = req.is_close && req.qty == 0.0;
            if req.qty < 0.0 || (req.qty == 0.0 && !is_qty_zero_full_close) {
                warn!(symbol = %req.symbol, "order dispatch skipped: qty=0");
                send_close_maker_dispatch_failed(
                    &pending_reg_tx,
                    &req,
                    "Rejected",
                    "dispatch_preflight_qty_zero",
                );
                send_decision_lease_release(
                    &pending_reg_tx,
                    &req,
                    LeaseOutcome::Failed,
                    "dispatch_preflight_qty_zero",
                );
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
            if !is_qty_zero_full_close {
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
                            send_close_maker_dispatch_failed(
                                &pending_reg_tx,
                                &req,
                                "Rejected",
                                format!(
                                    "dispatch_preflight_min_notional: est_notional={est_notional}; min_notional={}",
                                    spec.min_notional
                                ),
                            );
                            send_decision_lease_release(
                                &pending_reg_tx,
                                &req,
                                LeaseOutcome::Failed,
                                "dispatch_preflight_min_notional",
                            );
                            continue;
                        }
                    }
                }
            }
            // EXT-1: Register pending order BEFORE placing (for exchange mode)
            if req.is_primary {
                let now_ms = openclaw_core::now_ms();
                let close_maker_audit = close_maker_audit_for_dispatch_req(&req);
                let _ = pending_reg_tx.send(PendingOrderEvent::Register(PendingOrder {
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
                    limit_price: req.limit_price,
                    time_in_force: req.time_in_force,
                    // EDGE-P2-3 Phase 1B-3.2: per-order maker sweep timeout.
                    // EDGE-P2-3 Phase 1B-3.2：每單 maker sweep 逾時。
                    maker_timeout_ms: req.maker_timeout_ms,
                    close_maker_audit,
                    reference_price: req.reference_price,
                    reference_ts_ms: req.reference_ts_ms,
                    reference_source: req.reference_source.clone(),
                    cancel_requested_ts_ms: None,
                    // MAKER-CLOSE-REPRICE-1：鏡射 OrderDispatchRequest.reprice_count
                    // （初始 dispatch=0；toward-touch 重掛產生的單帶累計值），
                    // 使 sweep 對重掛單繼續累計至 CLOSE_MAKER_MAX_REPRICES 硬上限。
                    reprice_count: req.reprice_count,
                    // W-C Caveat 2 修復（2026-05-11）：鏡射 OrderDispatchRequest
                    // 帶來的 4 個 Spine id，loop_exchange.rs 成交確認後讀此
                    // 4 欄位呼叫 emit_fill_completion_lineage 補寫真實
                    // ExecutionReport。req.is_primary=false 的 paper shadow
                    // 路徑全為 None，下游自然 short-circuit。
                    spine_order_plan_id: req.spine_order_plan_id.clone(),
                    spine_decision_id: req.spine_decision_id.clone(),
                    spine_verdict_id: req.spine_verdict_id.clone(),
                    spine_stub_report_id: req.spine_stub_report_id.clone(),
                    // P2-ORDERS-INTENT-ID-WRITER-GAP-1（2026-05-19）：鏡射
                    // OrderDispatchRequest.intent_id 到 PendingOrder，下游
                    // handle_pending_registration 從 PendingOrder.intent_id 讀
                    // 寫入 TradingMsg::Order，再進 trading.orders.intent_id。
                    intent_id: req.intent_id.clone(),
                }));
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
                close_on_trigger: if is_qty_zero_full_close {
                    Some(true)
                } else {
                    None
                },
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
            // DISPATCH-RETRY-1 (2026-04-19) + P1-07 (2026-05-29): retry loop via
            // run_dispatch_retry helper.
            //   - Open (create) intents: NO retry (empty delay slice → single attempt,
            //     fail-closed; P1-07 STRICT FAIL-CLOSED, ambiguous create never re-sent).
            //   - Close intents use CLOSE_RETRY_DELAY_MS (2 retries, 500 ms; Q2 fix
            //     avoids amplifying PnL bleed; documented idempotent reduce-only exception).
            //   - Same `create_req` cloned per attempt (order_link_id unchanged =
            //     Bybit idempotency key; `reduce_only=true` adds secondary safety
            //     on close retries).
            //
            // DISPATCH-RETRY-1（2026-04-19）+ P1-07（2026-05-29）：透過 run_dispatch_retry。
            //   - 開倉（create）意圖：不重試（空 delay slice → 單次嘗試，fail-closed；
            //     P1-07 STRICT FAIL-CLOSED，曖昧 create 絕不重發）。
            //   - 關倉意圖使用 CLOSE_RETRY_DELAY_MS（2 次重試，500ms；Q2 修復以避免
            //     出血倉重試放大 PnL；文檔化的 reduce-only 冪等例外）。
            //   - 每次嘗試複製同一 `create_req`（order_link_id 不變 = Bybit 冪等鍵；
            //     關倉重試 `reduce_only=true` 提供二級保護）。
            // P1-07（cold audit pkg B；operator decision STRICT FAIL-CLOSED）：
            //   - OPEN（create）意圖：單次嘗試（空 delay slice → run_dispatch_retry 在
            //     attempt(0) >= len(0) 時立即回 TransientExhausted，等於 0 重試）。任何
            //     timeout / parse / transport / nonzero retCode 直接 fail-closed，
            //     Decision Lease 以非-Consumed（Failed）釋放，不發第二筆 create。
            //     為什麼：mutating create 回應曖昧（timeout/parse/transport）時絕不可重發
            //     —— order_link_id 冪等是 Bybit 側緩解，不是隱藏重試交易效果的許可
            //     （CLAUDE.md §四）。曖昧 create 由 reconciler / pending tracking 對帳。
            //   - CLOSE（reduce-only）意圖：保留有界冪等重試預算（CLOSE_RETRY_DELAY_MS），
            //     是文檔化的唯一例外（root principle 5 survival > profit）：fail-close 一筆
            //     close 會留下未平的活倉，比重試 reduce-only 更危險。
            let delays: &[u64] = dispatch_retry_delays_for_intent(req.is_close);
            let retry_result =
                run_dispatch_retry(delays, &req.symbol, &req.order_link_id, |_attempt| {
                    let req_for_attempt = create_req.clone();
                    let om = Arc::clone(&order_mgr);
                    let is_close = req.is_close;
                    // `async move` captures the Arc clone + cloned request by
                    // value. Each retry gets a fresh Future; the original
                    // `order_mgr` Arc binding stays alive in the outer closure
                    // for the next iteration.
                    //
                    // `async move` 捕獲 Arc 複製與複製後的請求（by value）。
                    // 每次重試產生新的 Future；原始 `order_mgr` Arc 綁定保留在
                    // 外層 closure 供下次迭代使用。
                    async move {
                        if is_close {
                            match tokio::time::timeout(
                                Duration::from_millis(CLOSE_ATTEMPT_TIMEOUT_MS),
                                om.place_order(req_for_attempt),
                            )
                            .await
                            {
                                Ok(result) => result,
                                Err(_) => {
                                    Err(close_dispatch_timeout_error(CLOSE_ATTEMPT_TIMEOUT_MS))
                                }
                            }
                        } else {
                            om.place_order(req_for_attempt).await
                        }
                    }
                })
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
                    if req.is_primary && !value.order_id.is_empty() && !req.order_link_id.is_empty()
                    {
                        if let Err(e) =
                            pending_reg_tx.send(PendingOrderEvent::ExchangeOrderIdMapped {
                                order_link_id: req.order_link_id.clone(),
                                exchange_order_id: value.order_id.clone(),
                            })
                        {
                            warn!(
                                order_link_id = %req.order_link_id,
                                exchange_order_id = %value.order_id,
                                error = %e,
                                "exchange order id mapping event dropped; OrderUpdate fallback still applies \
                                 / 交易所 orderId 映射事件丟失；仍可等待 OrderUpdate fallback"
                            );
                        }
                    }
                    send_decision_lease_release(
                        &pending_reg_tx,
                        &req,
                        LeaseOutcome::Consumed,
                        "exchange_dispatch_accepted",
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
                    // P1-110017-POSITION-DRIFT-CLOSE-LOOP：reduce-only **qty=0 全平
                    // form** 收到 110017（交易所端倉位已 zero）時，請求 event consumer
                    // 把本地漂移倉收斂為 flat，斷開「每 tick 重發 close → 110017」迴圈。
                    // BB MANDATORY guard 全在 send_exchange_zero_close 內（is_primary ∧
                    // is_close ∧ reduce_only ∧ qty==0 form ∧ 110017）；qty>0 partial
                    // reduce-only close 收到 110017（C-1，倉可能仍在）絕不收斂；
                    // 110001 維持原不收斂行為；110009 非 NoOp（stop-order
                    // limit exceeded，fail-closed）。
                    send_exchange_zero_close(&pending_reg_tx, &req, &last_error);
                    send_decision_lease_release(
                        &pending_reg_tx,
                        &req,
                        LeaseOutcome::Consumed,
                        "exchange_dispatch_noop_success",
                    );
                }
                DispatchRetryResult::Structural {
                    last_error,
                    attempts,
                } => {
                    // P2-ORDERLINKID-110072（+ 2026-06-07 follow-up）：close 重發撞
                    // 重複 order_link_id（110072 專屬碼，或 10001+retMsg "duplicate"
                    // 泛 InvalidParam）= 冪等成功（首次 close attempt 已達 Bybit、
                    // response 丟失，retry 重發同一 id 撞此碼）。走成功收尾（**不**發
                    // DispatchFailed、**不**收斂本地倉），鏡像 Ok/NoOp 成功路徑。
                    // open path 維持 fail-closed：close_dup_is_idempotent_success 僅
                    // is_close 成立（open 撞重複 id = id 撞歷史，開倉未成功，落 else
                    // 失敗路徑）。BB 2026-06-06 APPROVE-WITH-MANDATORY-GUARD；helper
                    // 同時涵蓋 110072 與 10001+duplicate（見其 docstring）。
                    // last_error 在本分支僅被借用（match &last_error / Display），
                    // helper 取 &req,&last_error 在 extract 之前，無 move 衝突。
                    if close_dup_is_idempotent_success(&req, &last_error) {
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
                            "close duplicate order_link_id — idempotent success / 平倉重複 order_link_id 等效成功"
                        );
                        send_decision_lease_release(
                            &pending_reg_tx,
                            &req,
                            LeaseOutcome::Consumed,
                            "exchange_dispatch_close_duplicate_idempotent",
                        );
                    } else {
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
                        if req.is_primary {
                            let reason =
                                format!("dispatch_structural: attempts={attempts}; error={last_error}");
                            if let Err(e) = pending_reg_tx.send(PendingOrderEvent::DispatchFailed {
                                order_link_id: req.order_link_id.clone(),
                                symbol: req.symbol.clone(),
                                is_long: req.is_long,
                                qty: req.qty,
                                strategy: req.strategy.clone(),
                                context_id: req.context_id.clone(),
                                is_close: req.is_close,
                                order_type: req.order_type.clone(),
                                time_in_force: req.time_in_force,
                                maker_timeout_ms: req.maker_timeout_ms,
                                close_maker_audit: req.close_maker_audit.clone(),
                                terminal_status: "Rejected".to_string(),
                                reason,
                                ts_ms: openclaw_core::now_ms(),
                            }) {
                                warn!(
                                    order_link_id = %req.order_link_id,
                                    error = %e,
                                    "dispatch failure terminal event dropped — pending state may require sweep \
                                     / 派發失敗 terminal event 發送失敗 — pending 狀態可能需 sweep"
                                );
                            }
                            send_decision_lease_release(
                                &pending_reg_tx,
                                &req,
                                LeaseOutcome::Failed,
                                "exchange_dispatch_structural_failed",
                            );
                        }
                    }
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
                    if req.is_primary {
                        let reason = format!(
                            "dispatch_transient_exhausted: attempts={attempts}; error={last_error}"
                        );
                        if let Err(e) = pending_reg_tx.send(PendingOrderEvent::DispatchFailed {
                            order_link_id: req.order_link_id.clone(),
                            symbol: req.symbol.clone(),
                            is_long: req.is_long,
                            qty: req.qty,
                            strategy: req.strategy.clone(),
                            context_id: req.context_id.clone(),
                            is_close: req.is_close,
                            order_type: req.order_type.clone(),
                            time_in_force: req.time_in_force,
                            maker_timeout_ms: req.maker_timeout_ms,
                            close_maker_audit: req.close_maker_audit.clone(),
                            terminal_status: "Failed".to_string(),
                            reason,
                            ts_ms: openclaw_core::now_ms(),
                        }) {
                            warn!(
                                order_link_id = %req.order_link_id,
                                error = %e,
                                "dispatch failure terminal event dropped — pending state may require sweep \
                                 / 派發失敗 terminal event 發送失敗 — pending 狀態可能需 sweep"
                            );
                        }
                        send_decision_lease_release(
                            &pending_reg_tx,
                            &req,
                            LeaseOutcome::Failed,
                            "exchange_dispatch_transient_exhausted",
                        );
                    }
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
#[path = "dispatch_tests.rs"]
mod tests;
