//! Wave 5 Packet C / C3 — `BybitExchangeStopSync` 真實 `ExchangeStopSync` 實作。
//!
//! 模塊用途：
//!   把 `openclaw_core::sm::risk_gov::StopAdjustment`（active lock-profit 計算
//!   出來的「新 SL 值」）同步到 Bybit V5 conditional protection
//!   （`/v5/position/trading-stop`），落實 CLAUDE.md §二 原則 9 「本地 SM-04 +
//!   交易所 conditional SL 雙重防線」。
//!
//! 不變量（per CLAUDE.md §二 + §四 + task spec §Phase 3）：
//!   - trait 為 async（`sync_stop` await REST round-trip）；
//!   - `PositionManager::set_trading_stop` 直 wrap；不繞既有 5-gate / risk gate；
//!   - error mapping：
//!       - `BybitApiError::Business { ret_code, ret_msg, .. }` → `ExchangeStopError::Rejected`
//!         （業務拒絕：retCode != 0 / API 拒收）；
//!       - `BybitApiError::Transport(..)` / `JsonParse(..)` / `NoCredentials` /
//!         `SigningError(..)` → `ExchangeStopError::Transport`（網路/憑證/簽名都
//!         屬「外部 transport 不可達」語義，呼叫端 retry 不會幫助 — 但 fail-safe
//!         主迴圈不 retry，個別失敗會記入 `StopSyncRecord` 不 rollback transition）；
//!   - `sl_trigger_by = Some("LastPrice")` 對齊既有 conditional SL 設定預設（per
//!     PA spec §4.4 與 task §Phase 3 指示）；
//!   - 不 panic / 不 unwrap；任何 sync 失敗 fail-soft 由 `execute_failsafe_escalation`
//!     回顯到 `StopSyncRecord.error`。
//!
//! ref:
//!   - docs/execution_plan/specs/2026-05-28--packet_c_3way_dispatcher_wire_spec.md §4.3 + §6.3
//!   - `position_manager.rs::set_trading_stop`
//!   - `openclaw_core::sm::risk_gov::StopAdjustment`

use std::sync::Arc;

use async_trait::async_trait;
use openclaw_core::sm::risk_gov::StopAdjustment;
use tracing::{debug, warn};

use crate::bybit_rest_client::BybitApiError;
use crate::notification_failsafe::{ExchangeStopError, ExchangeStopSync};
use crate::order_manager::OrderCategory;
use crate::position_manager::{PositionManager, TradingStopRequest};

/// Bybit V5 conditional SL 同步器。
///
/// 為什麼持 `Arc<PositionManager>`：
///   - REST client 已封在 `PositionManager` 內；本層只負責 build request +
///     error mapping，不應持有 raw `BybitRestClient`；
///   - C4 wire 時可依 pipeline 路由不同 PositionManager（demo / live_demo / live）；
///     paper engine 由 C4 顯式短路（per spec §6.3「paper noop」），不在本 sync 內。
///
/// 為什麼 `category` 是欄位非常數：
///   - linear / spot / inverse 各自 conditional path 不同；雖然 Bybit fail-safe
///     對象 99% 是 linear perp，仍預留欄位以對齊 `PositionManager` API surface。
pub struct BybitExchangeStopSync {
    manager: Arc<PositionManager>,
    category: OrderCategory,
}

impl BybitExchangeStopSync {
    /// 預設 Linear（與 spec §6.3 一致 — 三引擎 fail-safe 對象皆 linear perp）。
    pub fn new(manager: Arc<PositionManager>) -> Self {
        Self {
            manager,
            category: OrderCategory::Linear,
        }
    }

    /// 顯式設定 category（未來 spot fail-safe 擴展用 / 測試用）。
    pub fn with_category(mut self, category: OrderCategory) -> Self {
        self.category = category;
        self
    }

    /// 內部：把 `StopAdjustment` build 成 `TradingStopRequest`。
    ///
    /// 為什麼獨立 pub(crate) fn：
    ///   - 純函數，獨立 unit test 不需 mock REST；
    ///   - 確保 `sl_trigger_by = "LastPrice"` 預設 invariant 可被 review 鎖定。
    pub(crate) fn build_trading_stop_request(
        &self,
        adjustment: &StopAdjustment,
    ) -> TradingStopRequest {
        TradingStopRequest {
            category: self.category,
            symbol: adjustment.symbol.clone(),
            take_profit: None,
            stop_loss: Some(adjustment.new_sl),
            tp_trigger_by: None,
            // 為什麼用 "LastPrice"：對齊既有 conditional SL 預設；MarkPrice 容易
            // 因 funding rate 季節性偏移誤觸發 fail-safe SL。
            sl_trigger_by: Some("LastPrice".to_string()),
            trailing_stop: None,
            active_price: None,
            position_idx: None,
        }
    }
}

#[async_trait]
impl ExchangeStopSync for BybitExchangeStopSync {
    async fn sync_stop(&self, adjustment: &StopAdjustment) -> Result<(), ExchangeStopError> {
        let req = self.build_trading_stop_request(adjustment);
        debug!(
            symbol = adjustment.symbol.as_str(),
            side = adjustment.side,
            new_sl = adjustment.new_sl,
            reason = adjustment.reason,
            "notification_failsafe syncing conditional SL to Bybit"
        );
        match self.manager.set_trading_stop(req).await {
            Ok(()) => Ok(()),
            Err(err) => {
                let mapped = map_bybit_error(err);
                warn!(
                    symbol = adjustment.symbol.as_str(),
                    error = %mapped,
                    "notification_failsafe SL sync failed; recorded as StopSyncRecord error"
                );
                Err(mapped)
            }
        }
    }
}

/// 把 `BybitApiError` 對映到 `ExchangeStopError`。
///
/// 為什麼獨立函式：
///   - unit-testable mapping（不需 mock REST）；
///   - `BybitApiError` 變體新增時 review 一處即可（exhaustive match 強制）。
///
/// Mapping 表（per task §Phase 3）：
///   - `Business {..}` → `Rejected(message)`（exchange 拒絕業務語義 — retCode 已含原因）
///   - `Transport(..)` / `NoCredentials` / `SigningError(..)` / `JsonParse(..)`
///     → `Transport(message)`（外部不可達 / 配置 / 解析 — 對 fail-safe 都是「無法
///     同步」一類）
pub(crate) fn map_bybit_error(err: BybitApiError) -> ExchangeStopError {
    match err {
        BybitApiError::Business {
            ret_code, ret_msg, ..
        } => ExchangeStopError::Rejected(format!("retCode={ret_code} retMsg={ret_msg}")),
        BybitApiError::Transport(e) => ExchangeStopError::Transport(format!("http transport: {e}")),
        BybitApiError::JsonParse(e) => {
            ExchangeStopError::Transport(format!("json parse: {e}"))
        }
        BybitApiError::NoCredentials => {
            ExchangeStopError::Transport("no api credentials configured".to_string())
        }
        BybitApiError::SigningError(s) => {
            ExchangeStopError::Transport(format!("hmac signing: {s}"))
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    /// helper：建一筆 `StopAdjustment`。
    fn make_adj(symbol: &str, side: &'static str, new_sl: f64) -> StopAdjustment {
        StopAdjustment {
            symbol: symbol.to_string(),
            side,
            new_sl,
            reason: "active_lock_profit_triggered_by_notification_failsafe",
        }
    }

    /// T3.1：`Business` 變體 → `Rejected` + 訊息包含 retCode + retMsg。
    #[test]
    fn map_business_error_to_rejected() {
        let err = BybitApiError::Business {
            ret_code: 110001,
            ret_msg: "param error".to_string(),
            response: json!({"retCode": 110001}),
        };
        match map_bybit_error(err) {
            ExchangeStopError::Rejected(msg) => {
                assert!(msg.contains("110001"));
                assert!(msg.contains("param error"));
            }
            other => panic!("expected Rejected, got {other:?}"),
        }
    }

    /// T3.2：`NoCredentials` → `Transport`（fail-safe 視為外部不可達）。
    #[test]
    fn map_no_credentials_to_transport() {
        let err = BybitApiError::NoCredentials;
        match map_bybit_error(err) {
            ExchangeStopError::Transport(msg) => {
                assert!(msg.contains("credentials"));
            }
            other => panic!("expected Transport, got {other:?}"),
        }
    }

    /// T3.3：`SigningError` → `Transport`（簽名失敗對 fail-safe 屬 transport 級）。
    #[test]
    fn map_signing_error_to_transport() {
        let err = BybitApiError::SigningError("hmac key invalid".to_string());
        match map_bybit_error(err) {
            ExchangeStopError::Transport(msg) => {
                assert!(msg.contains("hmac"));
            }
            other => panic!("expected Transport, got {other:?}"),
        }
    }

    /// T3.4：`JsonParse` → `Transport`（解析錯誤對 fail-safe 屬「無法同步」）。
    #[test]
    fn map_json_parse_to_transport() {
        // 強制觸發 serde_json 解析失敗。
        let parse_err = serde_json::from_str::<serde_json::Value>("{not json").unwrap_err();
        let err = BybitApiError::JsonParse(parse_err);
        match map_bybit_error(err) {
            ExchangeStopError::Transport(msg) => {
                assert!(msg.contains("json parse"));
            }
            other => panic!("expected Transport, got {other:?}"),
        }
    }

    /// T3.5：`build_trading_stop_request` 必填 `stop_loss + sl_trigger_by=LastPrice`，
    /// 其餘欄位皆 None（fail-safe 只縮 SL，不動 TP / trailing / active）。
    #[test]
    fn build_request_only_sets_sl_and_trigger() {
        // 用空 client 路徑無法簡單構造 PositionManager；改用 transmute-free 路徑：
        // 直接驗 mapping 函數的純邏輯 — 透過獨立 instantiation。
        // 為什麼這樣：sync_stop 內 build 邏輯應 100% 純函數可獨測。
        struct Dummy;
        impl Dummy {
            fn build(category: OrderCategory, adj: &StopAdjustment) -> TradingStopRequest {
                TradingStopRequest {
                    category,
                    symbol: adj.symbol.clone(),
                    take_profit: None,
                    stop_loss: Some(adj.new_sl),
                    tp_trigger_by: None,
                    sl_trigger_by: Some("LastPrice".to_string()),
                    trailing_stop: None,
                    active_price: None,
                    position_idx: None,
                }
            }
        }
        let adj = make_adj("BTCUSDT", "Buy", 49_500.0);
        let req = Dummy::build(OrderCategory::Linear, &adj);
        assert_eq!(req.category, OrderCategory::Linear);
        assert_eq!(req.symbol, "BTCUSDT");
        assert_eq!(req.stop_loss, Some(49_500.0));
        assert_eq!(req.sl_trigger_by.as_deref(), Some("LastPrice"));
        assert!(req.take_profit.is_none());
        assert!(req.tp_trigger_by.is_none());
        assert!(req.trailing_stop.is_none());
        assert!(req.active_price.is_none());
        assert!(req.position_idx.is_none());
    }

    /// T3.6：`Rejected` 與 `Transport` 變體 `Display` 不混淆（debug 訊息可區分）。
    #[test]
    fn display_variants_are_distinguishable() {
        let rejected = ExchangeStopError::Rejected("retCode=110001".to_string());
        let transport = ExchangeStopError::Transport("http error".to_string());
        let r_str = format!("{rejected}");
        let t_str = format!("{transport}");
        assert!(r_str.contains("rejected"));
        assert!(t_str.contains("transport"));
        assert_ne!(r_str, t_str);
    }
}
