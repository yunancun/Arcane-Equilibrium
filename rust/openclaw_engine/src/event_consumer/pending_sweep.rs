//! Pending-order sweep classifier + PostOnly maker cancel helper.
//! 待處理訂單掃描分類器 + PostOnly 掛單取消輔助。
//!
//! MODULE_NOTE (EN): Extracted from `event_consumer/mod.rs` as Wave 1 G1-02
//!   Step 1 (commit see header). Pure decision core (`classify_pending_sweep`)
//!   stays unit-testable; `cancel_resting_maker_order` is the fail-soft REST
//!   cancel dispatched by the main loop every 5s for timed-out PostOnly makers.
//! MODULE_NOTE (中): 從 `event_consumer/mod.rs` 抽出（Wave 1 G1-02 Step 1）。
//!   `classify_pending_sweep` 為純決策核心，易於單元測試；`cancel_resting_maker_order`
//!   為主迴圈每 5s 派發的 fail-soft REST 取消，用於超時 PostOnly 掛單。

use super::PendingOrder;
use crate::strategies::maker_rejection::CloseMakerFallbackReason;
use tracing::{info, warn};

/// After a PostOnly entry partially fills, do not let the remaining stale quote
/// sit for the full maker timeout. Give it a short grace window, then the
/// existing sweep cancels by orderLinkId and the strategy can re-evaluate.
/// PostOnly entry 部分成交後，不再讓剩餘掛單等完整 maker timeout；
/// 給短暫 grace，之後沿用 sweep 取消並讓策略重新評估。
pub(crate) const PARTIAL_FILL_REMAINDER_GRACE_MS: u64 = 5_000;
/// Keep a maker pending row after dispatching cancel so racing fills that
/// arrive before the WS cancel ack can still match order context. If neither
/// fill nor cancel ack arrives inside this window, drop the tracker row to
/// avoid unbounded stale state.
/// 派發 maker cancel 後保留 pending row，讓 cancel ack 前 race 到的成交仍能匹配；
/// 若 grace 內無成交/取消回報，才丟棄 tracker，避免狀態無界累積。
pub(crate) const MAKER_CANCEL_ACK_GRACE_MS: u64 = 60_000;
/// Close maker orders carry exposure-reduction intent, so after a cancel
/// request we wait only a short grace before the future dispatcher must market
/// fallback. Entry makers keep the longer audit-matching grace above.
/// close maker 單代表降低曝險；發出 cancel 後只等短 grace，之後 future dispatcher
/// 必須 market fallback。entry maker 保留上方較長 grace 以便匹配 race fill。
pub(crate) const CLOSE_MAKER_CANCEL_ACK_GRACE_MS: u64 = 2_000;

/// EDGE-P2-3 Phase 1B-3.2: Sweep classification for a pending order at `elapsed_ms`.
/// Pure function so the Market vs PostOnly branching is unit-testable.
/// EDGE-P2-3 Phase 1B-3.2：pending order 超時掃描的純函數分類器，便於單元測試。
#[derive(Debug, PartialEq, Eq)]
pub(crate) enum PendingSweepAction {
    /// Keep tracking — no action this sweep tick / 繼續追蹤
    Keep,
    /// Market legacy: soft warn (elapsed > 5s but ≤ 60s) / Market 軟警告
    LegacySoftWarn,
    /// Market legacy: hard remove (elapsed > 60s) / Market 硬移除
    LegacyHardRemove,
    /// PostOnly maker: spawn REST cancel + mark in-flight (elapsed ≥ maker_timeout_ms)
    /// PostOnly 掛單超時：派發 REST 取消並標記 cancel in-flight
    MakerTimeoutCancel,
    /// PostOnly maker: cancel was already requested, but no fill/cancel ack
    /// arrived within the grace window; remove the stale tracker row.
    /// PostOnly 掛單已請求取消，但 grace 內無成交/取消回報；移除過期 tracker。
    MakerCancelGraceExpired,
}

pub(crate) fn pending_elapsed_ms(po: &PendingOrder, now_ms: u64) -> u64 {
    now_ms.saturating_sub(po.sent_ts_ms)
}

pub(crate) fn classify_pending_sweep(po: &PendingOrder, now_ms: u64) -> PendingSweepAction {
    let elapsed_ms = pending_elapsed_ms(po, now_ms);
    if po.time_in_force == Some(crate::order_manager::TimeInForce::PostOnly) {
        if let Some(cancel_ts) = po.cancel_requested_ts_ms {
            let grace_ms = if po.is_close {
                CLOSE_MAKER_CANCEL_ACK_GRACE_MS
            } else {
                MAKER_CANCEL_ACK_GRACE_MS
            };
            return if now_ms.saturating_sub(cancel_ts) >= grace_ms {
                PendingSweepAction::MakerCancelGraceExpired
            } else {
                PendingSweepAction::Keep
            };
        }
        let deadline_ms = po.maker_timeout_ms.unwrap_or(45_000);
        if elapsed_ms >= deadline_ms {
            PendingSweepAction::MakerTimeoutCancel
        } else {
            PendingSweepAction::Keep
        }
    } else if elapsed_ms > 60_000 {
        PendingSweepAction::LegacyHardRemove
    } else if elapsed_ms > 5000 {
        PendingSweepAction::LegacySoftWarn
    } else {
        PendingSweepAction::Keep
    }
}

/// MAKER-CLOSE-REPRICE-1 (2026-06-17): decision for toward-the-touch close-maker
/// repricing. Pure so the eligibility logic is unit-testable independent of the
/// async sweep loop / REST cancel.
///
/// `Some(new_limit_price)` = the sweep should cancel the resting close maker and
/// re-submit PostOnly at `new_limit_price`. `None` = no reprice (let the existing
/// timeout / cancel-grace path handle it).
///
/// **生存 gate 結構互斥（與 A.4 證明對齊）**：本 fn 第一道門 `is_close &&
/// tif==PostOnly`，而 PostOnly close 只可能由 close_order_dispatch_shape 的
/// close_maker_price_policy.is_some() 產生（=8 個正白名單 reason）。stops /
/// urgent / operator / circuit-breaker 等負白名單 reason 永遠走 market（tif=None），
/// 結構上到不了這裡。reprice 只把已過 gate 的 PostOnly close 拉回 inside quote，
/// 不新增任何 maker 准入，不碰任何 gate 函數。
/// MODULE_NOTE: new_inside_limit 由呼叫端以 compute_close_limit_price（同一安全
/// 函數，strict-passive + spread guard 全套）產生並傳入；本 fn 只做「是否值得重掛」
/// 的純決策，不自行計價。
pub(crate) fn close_maker_reprice_decision(
    po: &PendingOrder,
    now_ms: u64,
    new_inside_limit: Option<f64>,
    max_reprices: u32,
    reprice_after_ms: u64,
) -> Option<f64> {
    // Gate 1：僅 PostOnly close maker。entry maker / market / 非 PostOnly 一律不 reprice。
    if !po.is_close || po.time_in_force != Some(crate::order_manager::TimeInForce::PostOnly) {
        return None;
    }
    // Gate 2：reprice 關閉（降級開關）或已達硬上限。
    if max_reprices == 0 || po.reprice_count >= max_reprices {
        return None;
    }
    // Gate 3：cancel 已在途（不可同時 reprice + cancel 同一單，避免 double dispatch）。
    if po.cancel_requested_ts_ms.is_some() {
        return None;
    }
    // Gate 4：尚未到 reprice 觀察窗（首掛 reprice_after_ms 內不動，給原掛價成交機會）；
    //   且必須仍在 timeout 之前（達 timeout 走既有 MakerTimeoutCancel→taker，不 reprice）。
    let elapsed_ms = pending_elapsed_ms(po, now_ms);
    let timeout_ms = po.maker_timeout_ms.unwrap_or(45_000);
    if elapsed_ms < reprice_after_ms || elapsed_ms >= timeout_ms {
        return None;
    }
    // Gate 5：新 inside quote 必須「嚴格優於」原掛價（book 朝對我方向移動才值得重掛）。
    //   原掛價 = close_maker_audit.initial_limit_price（dispatch 時 compute_close_limit_price
    //   產出的 PostOnly 限價）。
    //   **方向修正（2026-06-17 E2/E4 RETURN HIGH）**：`po.is_long` 是 **訂單方向**，
    //   非持倉方向——close order 在 dispatch 時已 inverted（commands.rs `is_long: !is_long`），
    //   故 PendingOrder.is_long 鏡射的是訂單側：平多倉 = SELL → is_long=false；
    //   平空倉 = BUY → is_long=true。toward-touch 的「嚴格優於」按 **訂單側**判定：
    //     - SELL（po.is_long=false）：賣價越高越好 → 新限價 > 原限價；
    //     - BUY （po.is_long=true）：買價越低越好 → 新限價 < 原限價。
    //   先前註釋/比較把 is_long 誤當持倉方向 → 比較反向（unit test 因 fixture 共用同一
    //   錯誤假設而綠），會把 toward-touch 算反 → 壞 fill / PostOnly 穿越 spread。
    let new_limit = new_inside_limit.filter(|v| v.is_finite() && *v > 0.0)?;
    let original_limit = po
        .close_maker_audit
        .as_ref()
        .and_then(|a| a.initial_limit_price)
        .filter(|v| v.is_finite() && *v > 0.0)?;
    let strictly_better = if po.is_long {
        // 訂單側 BUY（平空倉）：新買價更低才重掛。
        new_limit < original_limit
    } else {
        // 訂單側 SELL（平多倉）：新賣價更高才重掛。
        new_limit > original_limit
    };
    if strictly_better {
        Some(new_limit)
    } else {
        None
    }
}

/// Classify only close-maker sweep states into required market fallback reasons.
///
/// The event loop can continue using `classify_pending_sweep()` for generic
/// tracking. Future close dispatch can call this helper to attach the V094
/// reason when a close maker timeout/cancel-grace branch must re-submit as
/// taker market.
///
/// 只把 close-maker sweep 狀態分類成必須 market fallback 的原因。event loop 可
/// 繼續使用 `classify_pending_sweep()` 做通用追蹤；future close dispatch 可用此
/// helper 在 close maker timeout / cancel-grace 分支補 V094 原因並改走 taker market。
#[allow(dead_code)]
pub(crate) fn close_maker_sweep_fallback_reason(
    po: &PendingOrder,
    now_ms: u64,
) -> Option<CloseMakerFallbackReason> {
    if !po.is_close || po.time_in_force != Some(crate::order_manager::TimeInForce::PostOnly) {
        return None;
    }
    match classify_pending_sweep(po, now_ms) {
        PendingSweepAction::MakerTimeoutCancel => Some(CloseMakerFallbackReason::TimeoutTaker),
        PendingSweepAction::MakerCancelGraceExpired => {
            Some(CloseMakerFallbackReason::CancelGraceExpired)
        }
        PendingSweepAction::Keep
        | PendingSweepAction::LegacySoftWarn
        | PendingSweepAction::LegacyHardRemove => None,
    }
}

pub(crate) fn tighten_postonly_entry_after_partial(po: &mut PendingOrder, exec_ts_ms: u64) -> bool {
    if po.is_close
        || po.time_in_force != Some(crate::order_manager::TimeInForce::PostOnly)
        || po.cum_filled_qty <= 0.0
        || po.cum_filled_qty >= po.qty * 0.999
    {
        return false;
    }

    po.maker_timeout_ms = Some(
        po.maker_timeout_ms
            .unwrap_or(PARTIAL_FILL_REMAINDER_GRACE_MS)
            .min(PARTIAL_FILL_REMAINDER_GRACE_MS),
    );
    if exec_ts_ms > 0 {
        po.sent_ts_ms = exec_ts_ms;
    }
    true
}

/// EDGE-P2-3 Phase 1B-3.2: Non-blocking REST cancel for a timed-out PostOnly
/// resting maker order. Uses client-minted `orderLinkId` (idempotent across
/// restart + WS lag). Fail-soft: any API error is logged and swallowed — the
/// tracker row has already been removed by the caller, so a racing fill after
/// a failed cancel lands in the position reconciler's normal recovery path.
///
/// 1B-5 FUP-3: routes through the shared `cancel_by_link_id_raw` helper in
/// `order_manager` so the Bybit endpoint / body / success-log fields stay
/// aligned with `OrderManager::cancel_order_by_link_id` (the typed caller).
/// The fail-soft warn branch remains local because this sweep path swallows
/// the error instead of surfacing a typed response to a caller.
///
/// EDGE-P2-3 Phase 1B-3.2：非阻塞 REST 取消超時的 PostOnly 掛單。
/// 使用客戶端 orderLinkId（跨重啟/WS 延遲冪等）。fail-soft：API 失敗僅記 log 不回退；
/// 調用端已移除 tracker，若取消失敗後 race 到成交，走對帳器常規恢復路徑。
///
/// 1B-5 FUP-3：改走 `order_manager::cancel_by_link_id_raw` 共用輔助，
/// 使 endpoint / body / 成功日誌欄位與 `OrderManager::cancel_order_by_link_id`
/// 對齊。fail-soft warn 分支仍保留於此（本路徑吞錯，不回傳類型化結果）。
pub(super) async fn cancel_resting_maker_order(
    client: std::sync::Arc<crate::bybit_rest_client::BybitRestClient>,
    symbol: String,
    order_link_id: String,
) {
    match crate::order_manager::cancel_by_link_id_raw(
        &client,
        crate::order_manager::OrderCategory::Linear,
        &symbol,
        &order_link_id,
    )
    .await
    {
        Ok(_) => {
            info!(
                symbol = %symbol,
                order_link_id = %order_link_id,
                reason = "maker_timeout_cancel",
                "PostOnly maker cancel acknowledged / PostOnly 掛單取消已確認"
            );
        }
        Err(err) => {
            // Common benign cases: 110001 order not exists (already filled/cancelled).
            // 常見良性情形：110001 訂單不存在（已成交或已取消）。
            warn!(
                symbol = %symbol,
                order_link_id = %order_link_id,
                error = %err,
                reason = "maker_timeout_cancel_failed",
                "PostOnly maker cancel REST failed — likely already filled/cancelled / PostOnly 取消失敗，很可能已成交或取消"
            );
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// EDGE-P2-3 Phase 1B-3.2: Sweep classifier unit tests.
// classify_pending_sweep is the pure decision core for the pending-order sweep
// loop. These tests pin Market legacy (5s/60s) and PostOnly maker timeout
// branching so a refactor can't silently drop the cancel-by-link-id path
// or bulldoze PostOnly orders with the Market 60s hard remove.
// ═══════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    fn make_market_pending(elapsed_ms_is_zero: bool) -> PendingOrder {
        let _ = elapsed_ms_is_zero;
        PendingOrder {
            order_link_id: "oc_market_1".into(),
            symbol: "BTCUSDT".into(),
            is_long: true,
            qty: 0.01,
            strategy: "ma_crossover".into(),
            sent_ts_ms: 0,
            cum_filled_qty: 0.0,
            is_close: false,
            context_id: String::new(),
            order_type: "market".into(),
            time_in_force: None,
            maker_timeout_ms: None,
            close_maker_audit: None,
            reference_price: None,
            reference_ts_ms: None,
            reference_source: None,
            cancel_requested_ts_ms: None,
            // MAKER-CLOSE-REPRICE-1：test fixture 預設 0（未重掛）。
            reprice_count: 0,
            // W-C Caveat 2 修復（2026-05-11）：test fixture 預設 None。
            spine_order_plan_id: None,
            spine_decision_id: None,
            spine_verdict_id: None,
            spine_stub_report_id: None,
            // P2-ORDERS-INTENT-ID-WRITER-GAP-1（2026-05-19）：sweep classifier
            // 不讀 intent_id，預設 None 保持 fixture 最小化。
            intent_id: None,
        }
    }

    fn make_postonly_pending(maker_timeout_ms: Option<u64>) -> PendingOrder {
        PendingOrder {
            order_link_id: "oc_maker_1".into(),
            symbol: "ETHUSDT".into(),
            is_long: false,
            qty: 0.1,
            strategy: "grid_trading".into(),
            sent_ts_ms: 0,
            cum_filled_qty: 0.0,
            is_close: false,
            context_id: String::new(),
            order_type: "limit".into(),
            time_in_force: Some(crate::order_manager::TimeInForce::PostOnly),
            maker_timeout_ms,
            close_maker_audit: None,
            reference_price: None,
            reference_ts_ms: None,
            reference_source: None,
            cancel_requested_ts_ms: None,
            // MAKER-CLOSE-REPRICE-1：test fixture 預設 0（未重掛）。
            reprice_count: 0,
            // W-C Caveat 2 修復（2026-05-11）：test fixture 預設 None。
            spine_order_plan_id: None,
            spine_decision_id: None,
            spine_verdict_id: None,
            spine_stub_report_id: None,
            // P2-ORDERS-INTENT-ID-WRITER-GAP-1（2026-05-19）：sweep classifier
            // 不讀 intent_id，預設 None 保持 fixture 最小化。
            intent_id: None,
        }
    }

    #[test]
    fn test_classify_market_under_5s_keeps_order() {
        let po = make_market_pending(false);
        // 0s: freshly submitted, nothing to do.
        assert_eq!(classify_pending_sweep(&po, 0), PendingSweepAction::Keep);
        // 5s exact: boundary — legacy condition is `elapsed > 5000`, so 5000 still keeps.
        assert_eq!(classify_pending_sweep(&po, 5_000), PendingSweepAction::Keep);
    }

    #[test]
    fn test_classify_market_between_5s_and_60s_soft_warns() {
        let po = make_market_pending(false);
        // 5001ms: just over soft warn threshold.
        assert_eq!(
            classify_pending_sweep(&po, 5_001),
            PendingSweepAction::LegacySoftWarn
        );
        // 30s mid-range.
        assert_eq!(
            classify_pending_sweep(&po, 30_000),
            PendingSweepAction::LegacySoftWarn
        );
        // 60s exact: boundary — legacy condition is `elapsed > 60000`, so 60000 still warns.
        assert_eq!(
            classify_pending_sweep(&po, 60_000),
            PendingSweepAction::LegacySoftWarn
        );
    }

    #[test]
    fn test_classify_market_over_60s_hard_removes() {
        let po = make_market_pending(false);
        // 60_001ms: one ms past hard timeout → remove tracker row.
        assert_eq!(
            classify_pending_sweep(&po, 60_001),
            PendingSweepAction::LegacyHardRemove
        );
        assert_eq!(
            classify_pending_sweep(&po, 90_000),
            PendingSweepAction::LegacyHardRemove
        );
    }

    #[test]
    fn test_classify_postonly_under_deadline_keeps_order() {
        // Default 45s deadline when maker_timeout_ms is None.
        // 預設 45s 截止時間（None 回退）。
        let po_default = make_postonly_pending(None);
        assert_eq!(
            classify_pending_sweep(&po_default, 0),
            PendingSweepAction::Keep
        );
        // Under default 45s → keep, even above Market's 5s soft-warn band.
        // 未達 45s → Keep，不應誤用 Market 的 5s 軟警告路徑。
        assert_eq!(
            classify_pending_sweep(&po_default, 30_000),
            PendingSweepAction::Keep
        );
        assert_eq!(
            classify_pending_sweep(&po_default, 44_999),
            PendingSweepAction::Keep
        );

        // Per-order override: 15s minimum clamp.
        // 每單覆蓋：15s 下限。
        let po_fast = make_postonly_pending(Some(15_000));
        assert_eq!(
            classify_pending_sweep(&po_fast, 14_999),
            PendingSweepAction::Keep
        );
    }

    #[test]
    fn test_classify_postonly_at_or_past_deadline_cancels() {
        // Default 45s deadline — elapsed ≥ deadline triggers cancel.
        // 預設 45s — elapsed ≥ 截止時間觸發取消。
        let po_default = make_postonly_pending(None);
        assert_eq!(
            classify_pending_sweep(&po_default, 45_000),
            PendingSweepAction::MakerTimeoutCancel
        );
        assert_eq!(
            classify_pending_sweep(&po_default, 300_000),
            PendingSweepAction::MakerTimeoutCancel
        );

        // Custom 60s deadline — Market's 60s hard-remove must NOT apply here.
        // 自訂 60s — 不應走 Market 60s 硬移除路徑。
        let po_60s = make_postonly_pending(Some(60_000));
        assert_eq!(
            classify_pending_sweep(&po_60s, 60_000),
            PendingSweepAction::MakerTimeoutCancel
        );
        // Even far past Market's 60s window, a PostOnly row that has not yet
        // had cancel dispatched stays on MakerTimeoutCancel.
        // 即便遠超 Market 60s，尚未派發 cancel 的 PostOnly 仍走 MakerTimeoutCancel。
        assert_eq!(
            classify_pending_sweep(&po_60s, 120_000),
            PendingSweepAction::MakerTimeoutCancel
        );
    }

    #[test]
    fn test_classify_postonly_cancel_inflight_keeps_during_ack_grace() {
        let mut po = make_postonly_pending(Some(45_000));
        po.cancel_requested_ts_ms = Some(45_000);

        assert_eq!(
            classify_pending_sweep(&po, 45_000),
            PendingSweepAction::Keep
        );
        assert_eq!(
            classify_pending_sweep(&po, 45_000 + MAKER_CANCEL_ACK_GRACE_MS - 1),
            PendingSweepAction::Keep
        );
    }

    #[test]
    fn test_classify_close_postonly_uses_short_cancel_grace() {
        let mut po = make_postonly_pending(Some(30_000));
        po.is_close = true;
        po.cancel_requested_ts_ms = Some(30_000);

        assert_eq!(
            classify_pending_sweep(&po, 30_000 + CLOSE_MAKER_CANCEL_ACK_GRACE_MS - 1),
            PendingSweepAction::Keep
        );
        assert_eq!(
            classify_pending_sweep(&po, 30_000 + CLOSE_MAKER_CANCEL_ACK_GRACE_MS),
            PendingSweepAction::MakerCancelGraceExpired
        );
        assert_eq!(
            close_maker_sweep_fallback_reason(&po, 30_000 + CLOSE_MAKER_CANCEL_ACK_GRACE_MS),
            Some(CloseMakerFallbackReason::CancelGraceExpired)
        );
    }

    #[test]
    fn test_classify_postonly_cancel_inflight_expires_after_ack_grace() {
        let mut po = make_postonly_pending(Some(45_000));
        po.cancel_requested_ts_ms = Some(45_000);

        assert_eq!(
            classify_pending_sweep(&po, 45_000 + MAKER_CANCEL_ACK_GRACE_MS),
            PendingSweepAction::MakerCancelGraceExpired
        );
    }

    #[test]
    fn test_classify_postonly_with_zero_deadline_cancels_immediately() {
        // Defensive: 0ms deadline means "cancel on first sweep".
        // Not a realistic config (clamp lower bound is 15_000) but covers the edge.
        // 防禦：0ms 截止時間代表「首次掃描即取消」；現實中 clamp 下限為 15_000，此處驗證邊界。
        let po_zero = make_postonly_pending(Some(0));
        assert_eq!(
            classify_pending_sweep(&po_zero, 0),
            PendingSweepAction::MakerTimeoutCancel
        );
        assert_eq!(
            classify_pending_sweep(&po_zero, 1),
            PendingSweepAction::MakerTimeoutCancel
        );
    }

    #[test]
    fn test_close_maker_timeout_maps_to_taker_fallback_reason() {
        let mut po = make_postonly_pending(Some(30_000));
        po.is_close = true;

        assert_eq!(
            close_maker_sweep_fallback_reason(&po, 29_999),
            None,
            "under maker timeout should keep waiting"
        );
        assert_eq!(
            close_maker_sweep_fallback_reason(&po, 30_000),
            Some(CloseMakerFallbackReason::TimeoutTaker),
            "close maker timeout must require taker market fallback"
        );
    }

    /// ★ P2 E4 (#4) CONSUMER half: an ENTRY PostOnly maker that does not fill
    /// within `maker_timeout_ms` must convert to a TAKER fill. The mechanism:
    /// below the deadline the resting maker is kept (true maker-preference);
    /// at/after the deadline the sweep classifies `MakerTimeoutCancel`, which
    /// the event loop uses to cancel the stale resting maker so the strategy
    /// re-evaluates and re-submits — the taker fallback. Bound to the SAME
    /// default 45_000ms the ma_crossover producer emits
    /// (`test_ma_crossover_maker_entry_is_opt_in_and_arms_taker_fallback_clock`),
    /// so a drift in either the strategy default or the sweep deadline breaks
    /// one of the paired tests.
    /// ★ 入場 maker 超時 → taker：deadline 前 Keep（真 maker 優先），deadline
    /// 起 MakerTimeoutCancel（取消掛單→策略重評→taker 重送），與 producer 預設
    /// 45s 綁定。
    #[test]
    fn test_entry_maker_postonly_times_out_to_taker_fallback() {
        // Bind to the producer's default maker_limit_timeout_ms (45s).
        const PRODUCER_DEFAULT_TIMEOUT_MS: u64 = 45_000;
        let po = make_postonly_pending(Some(PRODUCER_DEFAULT_TIMEOUT_MS));
        assert!(!po.is_close, "this is an ENTRY maker, not a close maker");

        // Below the deadline: keep resting as a maker (maker-preference holds).
        assert_eq!(
            classify_pending_sweep(&po, PRODUCER_DEFAULT_TIMEOUT_MS - 1),
            PendingSweepAction::Keep,
            "below the maker timeout the entry must keep resting as a maker"
        );
        // At the deadline: cancel the stale resting maker → strategy re-evaluates
        // → taker market re-submission. MakerTimeoutCancel IS the taker-fallback
        // trigger for entries (no close-fallback reason — entries are not closes).
        assert_eq!(
            classify_pending_sweep(&po, PRODUCER_DEFAULT_TIMEOUT_MS),
            PendingSweepAction::MakerTimeoutCancel,
            "at the maker timeout the resting entry maker must be cancelled → taker fallback"
        );
        assert_eq!(
            close_maker_sweep_fallback_reason(&po, PRODUCER_DEFAULT_TIMEOUT_MS),
            None,
            "entry maker timeout is a taker re-entry, not a close-maker fallback"
        );
        // Well past the deadline, an un-cancelled entry maker stays on the
        // taker-fallback trigger (never silently dropped).
        assert_eq!(
            classify_pending_sweep(&po, PRODUCER_DEFAULT_TIMEOUT_MS + 60_000),
            PendingSweepAction::MakerTimeoutCancel,
            "an un-cancelled entry maker stays on the taker-fallback trigger past the deadline"
        );
    }

    #[test]
    fn test_entry_maker_timeout_has_no_close_fallback_reason() {
        let po = make_postonly_pending(Some(30_000));

        assert_eq!(
            classify_pending_sweep(&po, 30_000),
            PendingSweepAction::MakerTimeoutCancel
        );
        assert_eq!(
            close_maker_sweep_fallback_reason(&po, 30_000),
            None,
            "entry maker timeout may miss an entry, but must not be labeled as close fallback"
        );
    }

    #[test]
    fn test_tighten_postonly_entry_after_partial_sets_short_grace() {
        let mut po = make_postonly_pending(Some(45_000));
        po.qty = 1.0;
        po.cum_filled_qty = 0.25;

        assert!(tighten_postonly_entry_after_partial(&mut po, 12_345));
        assert_eq!(po.maker_timeout_ms, Some(PARTIAL_FILL_REMAINDER_GRACE_MS));
        assert_eq!(po.sent_ts_ms, 12_345);
    }

    #[test]
    fn test_tighten_postonly_after_partial_does_not_extend_shorter_timeout() {
        let mut po = make_postonly_pending(Some(2_000));
        po.qty = 1.0;
        po.cum_filled_qty = 0.25;

        assert!(tighten_postonly_entry_after_partial(&mut po, 12_345));
        assert_eq!(po.maker_timeout_ms, Some(2_000));
    }

    #[test]
    fn test_tighten_postonly_after_partial_skips_close_orders() {
        let mut po = make_postonly_pending(Some(45_000));
        po.qty = 1.0;
        po.cum_filled_qty = 0.25;
        po.is_close = true;

        assert!(!tighten_postonly_entry_after_partial(&mut po, 12_345));
        assert_eq!(po.maker_timeout_ms, Some(45_000));
    }

    #[test]
    fn test_tighten_postonly_after_partial_skips_fully_filled() {
        let mut po = make_postonly_pending(Some(45_000));
        po.qty = 1.0;
        po.cum_filled_qty = 1.0;

        assert!(!tighten_postonly_entry_after_partial(&mut po, 12_345));
        assert_eq!(po.maker_timeout_ms, Some(45_000));
    }

    #[test]
    fn test_classify_market_vs_postonly_isolation() {
        // Same elapsed (30s) — Market soft-warns, PostOnly(default 45s) still keeps.
        // 相同 elapsed (30s) — Market 軟警告，PostOnly 預設 45s 仍 Keep。
        let m = make_market_pending(false);
        let p = make_postonly_pending(None);
        let elapsed = 30_000u64;
        assert_eq!(
            classify_pending_sweep(&m, elapsed),
            PendingSweepAction::LegacySoftWarn
        );
        assert_eq!(
            classify_pending_sweep(&p, elapsed),
            PendingSweepAction::Keep
        );
    }

    // ═══════════════════════════════════════════════════════════════════════
    // MAKER-CLOSE-REPRICE-1：close_maker_reprice_decision 純函數測試。
    // 含 survival-gate 互斥的 negative assertion（HARD STOP close 永不 reprice）。
    // ═══════════════════════════════════════════════════════════════════════

    /// 建構帶 audit（原掛價 = initial_limit_price）的 close-maker PostOnly fixture。
    ///
    /// **方向不變量（2026-06-17 E2/E4 RETURN HIGH 修正）**：參數 `position_is_long`
    /// 是 **真實持倉方向**；fixture 鏡射真實 dispatch 路徑（commands.rs `is_long: !is_long`）
    /// 把 `po.is_long` 設為 **訂單側 = !position_is_long**（平多倉=SELL→is_long=false、
    /// 平空倉=BUY→is_long=true）。先前 fixture 直接 `po.is_long = is_long` 把持倉方向
    /// 當成訂單側寫入，與 source 共用同一錯誤假設 → unit test 綠但 runtime 算反。
    fn make_close_maker_pending(
        position_is_long: bool,
        initial_limit_price: f64,
        reprice_count: u32,
        maker_timeout_ms: u64,
    ) -> PendingOrder {
        let mut po = make_postonly_pending(Some(maker_timeout_ms));
        po.is_close = true;
        // 訂單側 = 持倉反向（鏡射真實 close dispatch）。
        po.is_long = !position_is_long;
        po.strategy = "strategy_close:grid_close_long".into();
        po.reprice_count = reprice_count;
        po.close_maker_audit = Some(crate::tick_pipeline::CloseMakerFillAudit {
            initial_limit_price: Some(initial_limit_price),
            eligible_reason: "grid_close_long".into(),
            fallback_reason: None,
            rate_limit_scope: None,
        });
        po
    }

    #[test]
    fn reprice_long_close_sell_triggers_when_new_limit_strictly_higher() {
        // 持倉=LONG → close order = SELL（po.is_long=false）：新 inside 賣價更高
        //（book 上移、賣價朝對我有利）→ 重掛。
        let po = make_close_maker_pending(true, 100.0, 0, 90_000);
        assert!(!po.is_long, "long-position close must register as SELL (is_long=false)");
        // elapsed 在 [30s, 90s) 窗內。
        let now = po.sent_ts_ms + 30_000;
        let decision = close_maker_reprice_decision(&po, now, Some(100.5), 2, 30_000);
        assert_eq!(decision, Some(100.5), "higher SELL reprice should fire");
        // 新限價 <= 原掛價 → 不重掛。
        assert_eq!(
            close_maker_reprice_decision(&po, now, Some(100.0), 2, 30_000),
            None,
            "equal price must not reprice"
        );
        assert_eq!(
            close_maker_reprice_decision(&po, now, Some(99.5), 2, 30_000),
            None,
            "lower SELL price must not reprice"
        );
    }

    #[test]
    fn reprice_short_close_buy_triggers_when_new_limit_strictly_lower() {
        // 持倉=SHORT → close order = BUY（po.is_long=true）：新 inside 買價更低
        //（book 下移、買價朝對我有利）→ 重掛。
        let po = make_close_maker_pending(false, 100.0, 0, 90_000);
        assert!(po.is_long, "short-position close must register as BUY (is_long=true)");
        let now = po.sent_ts_ms + 30_000;
        assert_eq!(
            close_maker_reprice_decision(&po, now, Some(99.5), 2, 30_000),
            Some(99.5),
            "lower BUY reprice should fire"
        );
        assert_eq!(
            close_maker_reprice_decision(&po, now, Some(100.5), 2, 30_000),
            None,
            "higher BUY price must not reprice"
        );
    }

    #[test]
    fn reprice_respects_observation_window_and_timeout() {
        let po = make_close_maker_pending(true, 100.0, 0, 90_000);
        // 觀察窗前（< reprice_after_ms）→ 不重掛（給原掛價成交機會）。
        assert_eq!(
            close_maker_reprice_decision(&po, po.sent_ts_ms + 29_999, Some(100.5), 2, 30_000),
            None,
            "before reprice window must not reprice"
        );
        // 已到 timeout（>= timeout_ms）→ 走 MakerTimeoutCancel→taker，不重掛。
        assert_eq!(
            close_maker_reprice_decision(&po, po.sent_ts_ms + 90_000, Some(100.5), 2, 30_000),
            None,
            "at/after timeout must not reprice (falls to taker)"
        );
    }

    #[test]
    fn reprice_respects_max_reprices_hard_cap_and_kill_switch() {
        // 已達 max_reprices 硬上限 → 不再重掛。
        let po_capped = make_close_maker_pending(true, 100.0, 2, 90_000);
        assert_eq!(
            close_maker_reprice_decision(&po_capped, po_capped.sent_ts_ms + 30_000, Some(100.5), 2, 30_000),
            None,
            "at max_reprices must not reprice"
        );
        // max_reprices=0（降級開關）→ 完全關閉 reprice（退化現狀）。
        let po_fresh = make_close_maker_pending(true, 100.0, 0, 90_000);
        assert_eq!(
            close_maker_reprice_decision(&po_fresh, po_fresh.sent_ts_ms + 30_000, Some(100.5), 0, 30_000),
            None,
            "max_reprices=0 kill switch disables reprice entirely"
        );
    }

    #[test]
    fn reprice_skipped_when_cancel_in_flight() {
        let mut po = make_close_maker_pending(true, 100.0, 0, 90_000);
        po.cancel_requested_ts_ms = Some(po.sent_ts_ms + 30_000);
        assert_eq!(
            close_maker_reprice_decision(&po, po.sent_ts_ms + 30_000, Some(100.5), 2, 30_000),
            None,
            "cancel in-flight must not reprice (avoid double dispatch)"
        );
    }

    #[test]
    fn reprice_skipped_when_no_new_limit_available() {
        // BBO 缺值 / spread guard skip → compute_close_limit_price 回 None → 不重掛。
        let po = make_close_maker_pending(true, 100.0, 0, 90_000);
        assert_eq!(
            close_maker_reprice_decision(&po, po.sent_ts_ms + 30_000, None, 2, 30_000),
            None,
            "no inside-quote price must not reprice"
        );
    }

    /// ★ SURVIVAL-GATE NEGATIVE ASSERTION（A.4 互斥證明的 sweep 端鏡像）：
    /// 一筆「HARD STOP」close 在 dispatch 階段必走 market（tif=None，無 audit），
    /// 結構上不可能是 PostOnly close maker，因此 reprice 分支永不接受它。本測試
    /// 鎖死此不變式 —— 即使所有時間/價格條件都滿足，非 PostOnly close 仍回 None。
    #[test]
    fn reprice_never_fires_for_hard_stop_market_close() {
        // 模擬 HARD STOP close 在 dispatch 後的 PendingOrder 形狀：market、tif=None、
        // 無 close_maker_audit（close_order_dispatch_shape 對負白名單回 market）。
        let mut hard_stop_close = make_postonly_pending(Some(90_000));
        hard_stop_close.is_close = true;
        hard_stop_close.is_long = true;
        hard_stop_close.strategy = "risk_close:HARD STOP: loss".into();
        hard_stop_close.order_type = "market".into();
        hard_stop_close.time_in_force = None; // ★ market close 永遠 tif=None
        hard_stop_close.close_maker_audit = None;
        let now = hard_stop_close.sent_ts_ms + 30_000;
        // 即使餵入「更優」的新限價，Gate 1（tif==PostOnly）就拒絕。
        assert_eq!(
            close_maker_reprice_decision(&hard_stop_close, now, Some(100.5), 2, 30_000),
            None,
            "HARD STOP market close must NEVER reprice (survival gate structural exclusion)"
        );
        // 交叉驗證：HARD STOP 確實在負白名單（強制 market-only）。
        assert!(
            crate::strategies::common::is_close_maker_market_only_reason("risk_close:HARD STOP: loss"),
            "HARD STOP must remain market-only"
        );
        assert!(
            crate::strategies::common::close_maker_price_policy("risk_close:HARD STOP: loss").is_none(),
            "HARD STOP must not be in positive close-maker whitelist"
        );
    }
}
