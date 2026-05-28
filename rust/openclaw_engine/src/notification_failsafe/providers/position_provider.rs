//! Wave 5 Packet C / C3 — `RestPositionProvider` 真實 `PositionSnapshotProvider` 實作。
//!
//! 模塊用途：
//!   從 Bybit V5 REST `/v5/position/list` 拉真實 linear 倉位，map 為
//!   `openclaw_core::sm::risk_gov::PositionSnapshot`，餵給 `FailsafeWatcher` 計算
//!   active lock-profit `StopAdjustment`。
//!
//! 為什麼採 REST 而非 paper_state：
//!   - C3 task spec §Phase 2 操作員指示「走 PositionManager::get_positions（既有 REST 路徑）」
//!     — 與「不繞 PositionManager」邊界對齊；
//!   - paper engine 不會經過 ExchangeStopSync（C3 spec §Phase 3 paper noop），故 paper
//!     的倉位來源由獨立路徑 wire（不在本 C3 範圍）。
//!
//! 不變量（per CLAUDE.md §二 原則 5+6 + 本 task §Phase 2 規格）：
//!   - trait 是 sync（`fn snapshot_positions(&self) -> Vec<PositionSnapshot>`）；
//!     內部用 `tokio::runtime::Handle::block_on` wrap async REST；
//!   - REST 失敗 / timeout / parse error → 回 empty Vec fail-soft（survival 優先）；
//!   - timeout 5s 硬限避免 fail-safe watcher 30s tick 卡住；
//!   - `PositionInfo.side` ∈ {"Buy", "Sell", "None"}；只 map "Buy" / "Sell" 兩個
//!     `&'static str`，其他（包含 "None" 無倉狀態）跳過不入快照；
//!   - ATR 是「位置生命 ATR」（per `PositionSnapshot::atr` doc），不在 Bybit REST
//!     回應；本 provider 設 `atr=0.0` 讓 `active_lock_profit_per_position` 自然
//!     fail-closed 過濾（pos.atr <= 0.0 跳過）。**真實 ATR 注入由 C4 從
//!     `PriceHistoryTracker` / `paper_state` 旁路傳入時補**，此屬已知 known-limitation。
//!
//! ref:
//!   - docs/execution_plan/specs/2026-05-28--packet_c_3way_dispatcher_wire_spec.md §4.3
//!   - `position_manager.rs::PositionManager::get_positions`
//!   - `openclaw_core::sm::risk_gov::PositionSnapshot`

use std::sync::Arc;
use std::time::Duration;

use openclaw_core::sm::risk_gov::PositionSnapshot;
use tokio::runtime::Handle;
use tracing::{debug, warn};

use crate::notification_failsafe::PositionSnapshotProvider;
use crate::order_manager::OrderCategory;
use crate::position_manager::{PositionInfo, PositionManager};

/// REST 倉位 provider — 對應 spec §4.3 `RestPositionProvider`。
///
/// 為什麼持 `tokio::runtime::Handle`：
///   `PositionSnapshotProvider::snapshot_positions` 是 sync trait（核心邏輯
///   `active_lock_profit_per_position` 非 async），但 REST call 是 async；
///   `Handle::block_on` 把 future 在當前 runtime 上 driving 到完成。
///   呼叫端必須在 tokio runtime context 內呼叫本 provider（per C4 spawn task）。
///
/// 為什麼 timeout 5s：
///   `FailsafeWatcher::check_timer` 每 30s 跑一次，內含一次 snapshot；5s 上限
///   保證最壞情況下 tick latency 加 5s 仍 < 30s 週期，不影響 1h fail-safe timer 邊界。
pub struct RestPositionProvider {
    manager: Arc<PositionManager>,
    runtime: Handle,
    category: OrderCategory,
    timeout: Duration,
}

impl RestPositionProvider {
    /// 預設 timeout — per task spec §Phase 2「timeout 5s 硬限」。
    pub const DEFAULT_TIMEOUT: Duration = Duration::from_secs(5);

    /// 建構 — 預設 Linear category（與 Bybit V5 fail-safe 對象一致）。
    pub fn new(manager: Arc<PositionManager>, runtime: Handle) -> Self {
        Self {
            manager,
            runtime,
            category: OrderCategory::Linear,
            timeout: Self::DEFAULT_TIMEOUT,
        }
    }

    /// 顯式設定 category（測試 / 未來 spot fail-safe 用）。
    pub fn with_category(mut self, category: OrderCategory) -> Self {
        self.category = category;
        self
    }

    /// 顯式設定 timeout — 主要供測試覆蓋。
    pub fn with_timeout(mut self, timeout: Duration) -> Self {
        self.timeout = timeout;
        self
    }

    /// 內部：async REST + timeout 包裹。
    ///
    /// 為什麼吃 timeout：avoid blocking watcher 30s tick；REST hang 不該影響其他
    /// 倉位風控。回 `Vec<PositionInfo>`（empty on timeout / err，fail-soft）。
    async fn fetch_positions_with_timeout(&self) -> Vec<PositionInfo> {
        let fut = self.manager.get_positions(self.category, None);
        match tokio::time::timeout(self.timeout, fut).await {
            Ok(Ok(positions)) => positions,
            Ok(Err(err)) => {
                // REST error 走 fail-soft 路徑（不 propagate panic）。
                warn!(
                    error = %err,
                    category = self.category.as_str(),
                    "notification_failsafe REST snapshot failed; returning empty Vec"
                );
                Vec::new()
            }
            Err(_) => {
                // tokio::time::timeout Elapsed
                warn!(
                    timeout_ms = self.timeout.as_millis() as u64,
                    category = self.category.as_str(),
                    "notification_failsafe REST snapshot timed out; returning empty Vec"
                );
                Vec::new()
            }
        }
    }
}

impl PositionSnapshotProvider for RestPositionProvider {
    fn snapshot_positions(&self) -> Vec<PositionSnapshot> {
        // 為什麼 `Handle::block_on`：trait 為 sync；呼叫端在 tokio runtime worker
        // 內，必須在 spawn_blocking 包裹或新 thread 上跑 block_on（避免 panic
        // "block_on cannot be called from within a runtime"）。
        // 本層假設呼叫端是 `tokio::task::spawn_blocking` 包過的閉包，或是非
        // current_thread runtime；watcher C4 task 須遵循該契約。
        let infos = self.runtime.block_on(self.fetch_positions_with_timeout());
        map_position_infos(&infos)
    }
}

/// 把 Bybit REST `PositionInfo` map 為 risk_gov `PositionSnapshot`。
///
/// 為什麼獨立 pub(crate) fn：
///   - 純函數，方便獨立 unit test（不需 mock REST）；
///   - C4 spawn task 整合 ATR 注入時可重用同樣 mapping。
///
/// 過濾規則（per task spec §Phase 2 + risk_gov fail-closed 語義）：
///   - `side == "Buy"` → `&'static str "Buy"`；
///   - `side == "Sell"` → `&'static str "Sell"`；
///   - 其他（"None" / 未知）跳過 — 對應 spec「**注意 PositionSnapshot.side 必須在
///     caller 端 match "Buy" / "Sell"，其他 side 跳過**」；
///   - `size == 0.0` 跳過（無持倉 row）。
///
/// ATR 設 0.0：known-limitation，下游 `active_lock_profit_per_position` 自動跳過
/// （`pos.atr <= 0.0` fail-closed 過濾），不會觸發無效 SL 調整。
pub(crate) fn map_position_infos(infos: &[PositionInfo]) -> Vec<PositionSnapshot> {
    let mut out = Vec::with_capacity(infos.len());
    for info in infos {
        // 跳過 zero-size 持倉（Bybit 在 cleanup 期間可能回 size=0 row）。
        if info.size == 0.0 || !info.size.is_finite() {
            continue;
        }
        // 跳過未知 side（"None" 無倉 / 異常字串）— 對齊 risk_gov 只認 Buy/Sell。
        let side: &'static str = match info.side.as_str() {
            "Buy" => "Buy",
            "Sell" => "Sell",
            other => {
                debug!(
                    symbol = info.symbol.as_str(),
                    side = other,
                    "notification_failsafe skipping unknown position side"
                );
                continue;
            }
        };
        let current_sl = if info.stop_loss > 0.0 && info.stop_loss.is_finite() {
            Some(info.stop_loss)
        } else {
            None
        };
        out.push(PositionSnapshot {
            symbol: info.symbol.clone(),
            side,
            entry_price: info.avg_price,
            qty: info.size,
            current_sl,
            // ATR known-limitation：REST 不回 ATR；下游 fail-closed 過濾。
            atr: 0.0,
        });
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    /// helper：建一筆 `PositionInfo`，只填 fail-safe 需要的欄位。
    fn make_info(symbol: &str, side: &str, size: f64, avg_price: f64, sl: f64) -> PositionInfo {
        PositionInfo {
            symbol: symbol.to_string(),
            side: side.to_string(),
            size,
            avg_price,
            mark_price: avg_price,
            unrealised_pnl: 0.0,
            leverage: 1.0,
            liq_price: 0.0,
            take_profit: 0.0,
            stop_loss: sl,
            position_idx: 0,
            trailing_stop: 0.0,
            position_value: size * avg_price,
            cum_realised_pnl: 0.0,
            created_time: "0".to_string(),
            updated_time: "0".to_string(),
        }
    }

    /// T2.1：Buy 倉正常 map → snapshot side == "Buy"，current_sl Some。
    #[test]
    fn map_buy_position_to_snapshot() {
        let infos = vec![make_info("BTCUSDT", "Buy", 0.5, 50_000.0, 49_000.0)];
        let snaps = map_position_infos(&infos);
        assert_eq!(snaps.len(), 1);
        assert_eq!(snaps[0].symbol, "BTCUSDT");
        assert_eq!(snaps[0].side, "Buy");
        assert!((snaps[0].entry_price - 50_000.0).abs() < 1e-9);
        assert!((snaps[0].qty - 0.5).abs() < 1e-9);
        assert_eq!(snaps[0].current_sl, Some(49_000.0));
        assert_eq!(snaps[0].atr, 0.0); // known-limitation
    }

    /// T2.2：Sell 倉正常 map → snapshot side == "Sell"。
    #[test]
    fn map_sell_position_to_snapshot() {
        let infos = vec![make_info("ETHUSDT", "Sell", 2.0, 3_000.0, 3_100.0)];
        let snaps = map_position_infos(&infos);
        assert_eq!(snaps.len(), 1);
        assert_eq!(snaps[0].side, "Sell");
        assert_eq!(snaps[0].current_sl, Some(3_100.0));
    }

    /// T2.3：side == "None" 無倉應跳過（不入快照）。
    #[test]
    fn skip_none_side_position() {
        let infos = vec![
            make_info("BTCUSDT", "None", 0.0, 0.0, 0.0),
            make_info("ETHUSDT", "Buy", 1.0, 3_000.0, 0.0),
        ];
        let snaps = map_position_infos(&infos);
        assert_eq!(snaps.len(), 1);
        assert_eq!(snaps[0].symbol, "ETHUSDT");
    }

    /// T2.4：side 為未知字串（"buy" 小寫 / "Long"）跳過。
    #[test]
    fn skip_unknown_side_strings() {
        let infos = vec![
            make_info("BTCUSDT", "buy", 1.0, 50_000.0, 0.0),
            make_info("ETHUSDT", "Long", 1.0, 3_000.0, 0.0),
            make_info("SOLUSDT", "Sell", 5.0, 100.0, 0.0),
        ];
        let snaps = map_position_infos(&infos);
        assert_eq!(snaps.len(), 1);
        assert_eq!(snaps[0].symbol, "SOLUSDT");
    }

    /// T2.5：size == 0 即使 side 合法仍跳過。
    #[test]
    fn skip_zero_size_position() {
        let infos = vec![make_info("BTCUSDT", "Buy", 0.0, 50_000.0, 49_000.0)];
        let snaps = map_position_infos(&infos);
        assert!(snaps.is_empty());
    }

    /// T2.6：stop_loss == 0 → current_sl 為 None（Bybit 未設 SL 約定）。
    #[test]
    fn sl_zero_maps_to_none() {
        let infos = vec![make_info("BTCUSDT", "Buy", 1.0, 50_000.0, 0.0)];
        let snaps = map_position_infos(&infos);
        assert_eq!(snaps.len(), 1);
        assert_eq!(snaps[0].current_sl, None);
    }

    /// T2.7：NaN size 必須 fail-closed 跳過（survival 優先）。
    #[test]
    fn skip_nan_size() {
        let infos = vec![make_info("BTCUSDT", "Buy", f64::NAN, 50_000.0, 0.0)];
        let snaps = map_position_infos(&infos);
        assert!(snaps.is_empty());
    }

    /// T2.8：混合多筆 → 只有合法 Buy / Sell + size>0 入快照。
    #[test]
    fn mixed_positions_filtered_correctly() {
        let infos = vec![
            make_info("BTCUSDT", "Buy", 0.5, 50_000.0, 49_000.0),
            make_info("ETHUSDT", "None", 0.0, 0.0, 0.0),
            make_info("SOLUSDT", "Sell", 10.0, 100.0, 0.0),
            make_info("ADAUSDT", "buy", 1.0, 0.5, 0.0),
            make_info("DOGEUSDT", "Buy", 0.0, 0.1, 0.0),
        ];
        let snaps = map_position_infos(&infos);
        assert_eq!(snaps.len(), 2);
        let symbols: Vec<&str> = snaps.iter().map(|s| s.symbol.as_str()).collect();
        assert!(symbols.contains(&"BTCUSDT"));
        assert!(symbols.contains(&"SOLUSDT"));
    }

    /// T2.9：負數 stop_loss 視為未設（防禦性；Bybit 不應回但 fail-closed）。
    #[test]
    fn negative_stop_loss_maps_to_none() {
        let infos = vec![make_info("BTCUSDT", "Buy", 1.0, 50_000.0, -1.0)];
        let snaps = map_position_infos(&infos);
        assert_eq!(snaps.len(), 1);
        assert_eq!(snaps[0].current_sl, None);
    }

    /// T2.10：empty input → empty output（trivial 不變量）。
    #[test]
    fn empty_input_empty_output() {
        let snaps = map_position_infos(&[]);
        assert!(snaps.is_empty());
    }
}
