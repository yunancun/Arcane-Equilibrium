//! `SyntheticSpotLedger` — Stage 1-3 Demo 期 spot 腿 paper-only 內部 ledger。
//!
//! MODULE_NOTE：
//!   模塊用途：因 Bybit demo endpoint 不支援 spot lending / spot order（BB C4 verdict
//!     §2 + memory `project_funding_arb_v2_deprecation_path`），funding harvest 的
//!     delta-neutral spot 腿改在 engine 內部以 ledger 紀錄 open / rebalance / close
//!     + mark-to-market PnL。**不打 Bybit API、不寫 PG balance、不發 OrderIntent**。
//!   主要類函數：SyntheticSpotLedger、open_long、rebalance、close、unrealized_pnl_usd、
//!     delta_drift_pct。
//!   依賴：serde（持久化）；無外部副作用。
//!   硬邊界：
//!     - 不變量：不違反 16 root principles §1（單一寫入口）— ledger 純內部 accounting，
//!       不繞 IntentProcessor。
//!     - 不變量：state machine 只允 Closed → Open（open_long）→ Closed（close）；
//!       重複 open_long / 已 Closed 再 close 由 strategy 層幂等處理（這裡保守覆寫）。
//!     - Stage 4 LIVE 升級時本 module retire；spot leg 改走 IntentProcessor real spot
//!       order（Sprint 5+ cascade window，本 Wave 不做）。
//!     - rebalance 只調 `qty`，**不改 entry_price**（PnL 計算基準保留入場價）。

use serde::{Deserialize, Serialize};

/// SyntheticSpotLedger 狀態枚舉：開倉中 / 已關閉。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SyntheticSpotState {
    /// 持倉中 — open_long 後、close 前。
    Open,
    /// 已平倉或從未開倉（初始狀態）。
    Closed,
}

/// Spot 腿的 in-memory ledger。對應 perp 腿開倉時匹配 notional。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SyntheticSpotLedger {
    pub state: SyntheticSpotState,
    /// 入場時對應的 USD notional（用作 PnL 基準與 rebalance 目標）。
    pub entry_notional_usd: f64,
    /// 入場 spot 價（PnL 計算 baseline）。
    pub entry_price: f64,
    pub entry_ts_ms: u64,
    /// spot 腿 LONG 方向；qty = notional / spot_price。
    pub qty: f64,
    /// 累積 rebalance 次數（observability / unit test 用）。
    pub rebalance_count: u32,
    /// 最近一次 rebalance 的 spot 價與時戳。
    pub last_rebalance_price: f64,
    pub last_rebalance_ts_ms: u64,
    /// close 時 realize 的 PnL（USD）；None 表未平。
    pub realized_pnl_usd: Option<f64>,
    pub close_ts_ms: Option<u64>,
    pub close_price: Option<f64>,
}

impl Default for SyntheticSpotLedger {
    fn default() -> Self {
        Self::new()
    }
}

impl SyntheticSpotLedger {
    /// 全新空 ledger（state=Closed）。
    pub fn new() -> Self {
        Self {
            state: SyntheticSpotState::Closed,
            entry_notional_usd: 0.0,
            entry_price: 0.0,
            entry_ts_ms: 0,
            qty: 0.0,
            rebalance_count: 0,
            last_rebalance_price: 0.0,
            last_rebalance_ts_ms: 0,
            realized_pnl_usd: None,
            close_ts_ms: None,
            close_price: None,
        }
    }

    /// 開 long spot 腿；匹配 perp short 的 notional。
    ///
    /// 為什麼：funding harvest 對 perp short 收 funding，必須以 spot long 對沖
    /// 方向暴露達成 delta-neutral；spot_price 用 ctx.index_price（spot 近似，
    /// 與 funding_arb 的 basis 計算一致）。
    ///
    /// 不變量：
    /// - 已 Open 再呼叫視為覆寫（strategy 層保證不會在持倉中重複入場）。
    /// - spot_price 必 > 0，否則 qty=0、entry_price=0 防 NaN（caller 該過濾）。
    pub fn open_long(&mut self, notional_usd: f64, spot_price: f64, ts_ms: u64) {
        let qty = if spot_price > 0.0 {
            notional_usd / spot_price
        } else {
            0.0
        };
        self.state = SyntheticSpotState::Open;
        self.entry_notional_usd = notional_usd;
        self.entry_price = spot_price;
        self.qty = qty;
        self.entry_ts_ms = ts_ms;
        self.last_rebalance_price = spot_price;
        self.last_rebalance_ts_ms = ts_ms;
        self.rebalance_count = 0;
        self.realized_pnl_usd = None;
        self.close_ts_ms = None;
        self.close_price = None;
    }

    /// rebalance：跟隨 perp 腿 notional 調整 spot 腿 qty。
    ///
    /// 為什麼：spot price 與 perp price 不完全鎖定（basis drift），time-warp 後
    /// 兩腿 notional 偏離；只調 qty 跟隨 target，**不改 entry_price** 保 PnL
    /// 計算基準。
    ///
    /// 不變量：state != Open 直接 noop（防 closed ledger 被誤操作）。
    pub fn rebalance(&mut self, target_notional_usd: f64, spot_price: f64, ts_ms: u64) {
        if self.state != SyntheticSpotState::Open || spot_price <= 0.0 {
            return;
        }
        self.qty = target_notional_usd / spot_price;
        self.last_rebalance_price = spot_price;
        self.last_rebalance_ts_ms = ts_ms;
        self.rebalance_count += 1;
    }

    /// close 平倉：以當前 spot price 計算 realized PnL = (close - entry) × qty。
    ///
    /// 不變量：state != Open 直接 noop 回 0.0（防重複 close）。
    /// 返回值：本次 close 的 realized PnL（USD）。
    pub fn close(&mut self, close_price: f64, ts_ms: u64) -> f64 {
        if self.state != SyntheticSpotState::Open {
            return 0.0;
        }
        let pnl = (close_price - self.entry_price) * self.qty;
        self.state = SyntheticSpotState::Closed;
        self.realized_pnl_usd = Some(pnl);
        self.close_ts_ms = Some(ts_ms);
        self.close_price = Some(close_price);
        pnl
    }

    /// 當前 mark-to-market unrealized PnL（USD）。
    /// state != Open 回 0.0。
    pub fn unrealized_pnl_usd(&self, current_spot_price: f64) -> f64 {
        if self.state != SyntheticSpotState::Open {
            return 0.0;
        }
        (current_spot_price - self.entry_price) * self.qty
    }

    /// 與 perp 腿的 delta drift（spot 視角）：
    ///   delta_pct = |spot_notional - perp_notional| / spot_notional
    ///
    /// 為什麼用 spot 分母：funding harvest spot 腿是 LONG（main asset），以其
    /// notional 為基準衡量 hedge 完整度；perp 視角會給對稱結果但意義不同。
    pub fn delta_drift_pct(&self, perp_notional_usd: f64, current_spot_price: f64) -> f64 {
        if self.state != SyntheticSpotState::Open {
            return 0.0;
        }
        let current_spot_notional = self.qty * current_spot_price;
        if current_spot_notional <= 0.0 {
            return 0.0;
        }
        ((current_spot_notional - perp_notional_usd) / current_spot_notional).abs()
    }

    /// 觀察用 getter：是否處於 open 狀態。
    pub fn is_open(&self) -> bool {
        self.state == SyntheticSpotState::Open
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn new_ledger_is_closed() {
        let l = SyntheticSpotLedger::new();
        assert!(!l.is_open());
        assert_eq!(l.qty, 0.0);
    }

    #[test]
    fn open_long_sets_state_and_qty() {
        let mut l = SyntheticSpotLedger::new();
        l.open_long(100.0, 50_000.0, 1_000);
        assert!(l.is_open());
        assert!((l.qty - 100.0 / 50_000.0).abs() < 1e-12);
        assert_eq!(l.entry_price, 50_000.0);
        assert_eq!(l.entry_ts_ms, 1_000);
        assert_eq!(l.rebalance_count, 0);
    }

    #[test]
    fn open_long_zero_price_does_not_panic() {
        let mut l = SyntheticSpotLedger::new();
        l.open_long(100.0, 0.0, 1_000);
        // qty 應為 0（防 NaN）；caller 該事先過濾 spot_price > 0。
        assert!(l.is_open());
        assert_eq!(l.qty, 0.0);
    }

    #[test]
    fn rebalance_only_when_open() {
        let mut l = SyntheticSpotLedger::new();
        // 未 open 呼叫 rebalance 視為 noop。
        l.rebalance(200.0, 50_000.0, 2_000);
        assert_eq!(l.rebalance_count, 0);
        assert_eq!(l.qty, 0.0);

        l.open_long(100.0, 50_000.0, 1_000);
        let qty_before = l.qty;
        // target notional 120 / spot 52_000 = 0.002307...，與 entry qty=0.002 不同。
        l.rebalance(120.0, 52_000.0, 5_000);
        assert!(l.qty > 0.0);
        assert!((l.qty - 120.0 / 52_000.0).abs() < 1e-12);
        assert!(
            (l.qty - qty_before).abs() > 1e-9,
            "rebalance changed qty (target notional differs)"
        );
        // entry_price 不變（PnL 基準保留）。
        assert_eq!(l.entry_price, 50_000.0);
        assert_eq!(l.rebalance_count, 1);
        assert_eq!(l.last_rebalance_price, 52_000.0);
    }

    #[test]
    fn close_realizes_pnl_long_profit() {
        let mut l = SyntheticSpotLedger::new();
        l.open_long(100.0, 50_000.0, 1_000);
        let pnl = l.close(55_000.0, 10_000);
        // qty = 100 / 50000 = 0.002；profit = (55000 - 50000) × 0.002 = 10 USD。
        assert!((pnl - 10.0).abs() < 1e-9);
        assert!(!l.is_open());
        assert_eq!(l.realized_pnl_usd, Some(pnl));
        assert_eq!(l.close_price, Some(55_000.0));
    }

    #[test]
    fn close_realizes_pnl_long_loss() {
        let mut l = SyntheticSpotLedger::new();
        l.open_long(100.0, 50_000.0, 1_000);
        let pnl = l.close(45_000.0, 10_000);
        // (45000 - 50000) × 0.002 = -10 USD（spot LONG 跌 → 虧）。
        assert!((pnl - (-10.0)).abs() < 1e-9);
    }

    #[test]
    fn double_close_noop() {
        let mut l = SyntheticSpotLedger::new();
        l.open_long(100.0, 50_000.0, 1_000);
        let first = l.close(55_000.0, 10_000);
        let second = l.close(60_000.0, 20_000);
        assert!((first - 10.0).abs() < 1e-9);
        // 第二次 close 應 noop 回 0，不覆寫第一次 realized。
        assert_eq!(second, 0.0);
        assert_eq!(l.realized_pnl_usd, Some(first));
    }

    #[test]
    fn unrealized_pnl_tracks_mark_to_market() {
        let mut l = SyntheticSpotLedger::new();
        l.open_long(100.0, 50_000.0, 1_000);
        // mark-to-market: (52500 - 50000) × 0.002 = 5 USD。
        assert!((l.unrealized_pnl_usd(52_500.0) - 5.0).abs() < 1e-9);
        // closed ledger unrealized 必 0。
        l.close(52_500.0, 2_000);
        assert_eq!(l.unrealized_pnl_usd(60_000.0), 0.0);
    }

    #[test]
    fn delta_drift_pct_basic() {
        let mut l = SyntheticSpotLedger::new();
        l.open_long(100.0, 50_000.0, 1_000);
        // spot notional = qty × current_spot_price = 0.002 × 50500 = 101 USD。
        // perp notional = 100；drift = |101 - 100| / 101 ≈ 0.0099 → ~1%。
        let drift = l.delta_drift_pct(100.0, 50_500.0);
        assert!((drift - 0.009_900_990_099).abs() < 1e-6);
    }

    #[test]
    fn delta_drift_pct_closed_returns_zero() {
        let l = SyntheticSpotLedger::new();
        assert_eq!(l.delta_drift_pct(100.0, 50_000.0), 0.0);
    }

    #[test]
    fn reopen_after_close_resets_counters() {
        let mut l = SyntheticSpotLedger::new();
        l.open_long(100.0, 50_000.0, 1_000);
        l.rebalance(110.0, 52_000.0, 2_000);
        l.close(55_000.0, 3_000);
        assert_eq!(l.rebalance_count, 1);

        l.open_long(150.0, 60_000.0, 10_000);
        // 重新開倉清計數器。
        assert_eq!(l.rebalance_count, 0);
        assert!(l.is_open());
        assert!(l.realized_pnl_usd.is_none());
        assert!(l.close_ts_ms.is_none());
    }
}
