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
use tracing::{info, warn};

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
    /// PostOnly maker: spawn REST cancel + remove (elapsed ≥ maker_timeout_ms)
    /// PostOnly 掛單超時：派發 REST 取消並移除記錄
    MakerTimeoutCancel,
}

pub(crate) fn classify_pending_sweep(po: &PendingOrder, elapsed_ms: u64) -> PendingSweepAction {
    if po.time_in_force == Some(crate::order_manager::TimeInForce::PostOnly) {
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
        }
    }

    #[test]
    fn test_classify_market_under_5s_keeps_order() {
        let po = make_market_pending(false);
        // 0s: freshly submitted, nothing to do.
        assert_eq!(classify_pending_sweep(&po, 0), PendingSweepAction::Keep);
        // 5s exact: boundary — legacy condition is `elapsed > 5000`, so 5000 still keeps.
        assert_eq!(
            classify_pending_sweep(&po, 5_000),
            PendingSweepAction::Keep
        );
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
        // Even far past Market's 60s window, PostOnly stays on MakerTimeoutCancel
        // (cancel dispatch is terminal — next sweep won't see this row anyway).
        // 即便遠超 Market 60s，PostOnly 永遠走 MakerTimeoutCancel。
        assert_eq!(
            classify_pending_sweep(&po_60s, 120_000),
            PendingSweepAction::MakerTimeoutCancel
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
}
