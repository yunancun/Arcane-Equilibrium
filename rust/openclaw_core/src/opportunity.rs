//! R02-8: OpportunityTracker — Virtual PnL Tracking / 虛擬 PnL 追蹤（遺憾追蹤）
//! ================================================================================
//!
//! MODULE_NOTE (中文):
//!   OpportunityTracker 追蹤被跳過的交易機會的虛擬表現：
//!   - record_skipped()：記錄被過濾/拒絕的信號及其入場價
//!   - update_virtual_pnl()：每次 tick 更新虛擬 PnL
//!   - get_regret_summary()：計算 bullets_dodged（避開的虧損）vs regret（錯過的盈利）
//!
//!   [Q2] 虛擬 PnL 扣除 2× 預估費用（0.075%×2 = 0.15%）防止假性後悔偏差
//!   [Q3] 方向判斷使用歸一化比較（avg_regret vs avg_dodged），非絕對值
//!   [R1-8] 每側至少 5 個樣本才判斷方向
//!
//! MODULE_NOTE (English):
//!   OpportunityTracker tracks virtual performance of skipped trading opportunities:
//!   - record_skipped(): record filtered/rejected signals with entry price
//!   - update_virtual_pnl(): update virtual PnL every tick
//!   - get_regret_summary(): compute bullets_dodged vs regret_from_undertrading
//!
//!   [Q2] Virtual PnL deducts 2× estimated fee (0.075%×2 = 0.15%) to suppress false regret
//!   [Q3] Direction uses normalized comparison (avg_regret vs avg_dodged), not absolute
//!   [R1-8] Minimum 5 samples per side for direction judgment

use std::collections::{HashMap, VecDeque};

use serde::{Deserialize, Serialize};
use uuid::Uuid;

// ── Constants / 常量 ──────────────────────────────────────────────────

/// Virtual stop-loss percentage / 虛擬止損百分比
const VIRTUAL_SL_PCT: f64 = -5.0;
/// Virtual take-profit percentage / 虛擬止盈百分比
const VIRTUAL_TP_PCT: f64 = 10.0;
/// TTL in days / 有效期天數
const TTL_DAYS: u64 = 7;
/// Round-trip friction cost: 2 × 0.075% = 0.15% / 往返摩擦成本
const FRICTION_PCT: f64 = 0.15;
/// Maximum active opportunities / 最大活躍機會數
const MAX_ACTIVE: usize = 100;
/// Maximum settled history / 最大結算歷史
const MAX_SETTLED: usize = 500;
/// [R1-8] Minimum samples per side for direction judgment / 每側最少樣本數
const MIN_SAMPLES_PER_DIRECTION: usize = 5;
/// TTL in milliseconds / 有效期毫秒
const TTL_MS: u64 = TTL_DAYS * 24 * 3600 * 1000;

// ── Structs / 結構體 ─────────────────────────────────────────────────

/// A single skipped trading opportunity with virtual PnL tracking.
/// 單個被跳過的交易機會，含虛擬 PnL 追蹤。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SkippedOpportunity {
    /// Unique opportunity ID / 唯一機會 ID
    pub opp_id: String,
    /// Trading symbol / 交易對
    pub symbol: String,
    /// Direction: "long" or "short" / 方向
    pub direction: String,
    /// Entry price at signal time / 信號時入場價
    pub entry_price: f64,
    /// Entry timestamp in milliseconds / 入場時間戳（毫秒）
    pub entry_ts_ms: u64,
    /// Signal confidence at skip time / 跳過時的信號置信度
    pub signal_confidence: f64,
    /// Reason the opportunity was skipped / 跳過原因
    pub skip_reason: String,
    /// Source that skipped it (e.g. "guardian", "h0_gate") / 跳過來源
    pub skip_source: String,
    /// Strategy that generated the signal / 產生信號的策略
    pub strategy_name: String,
    /// Current virtual PnL percentage / 當前虛擬 PnL 百分比
    pub current_pnl_pct: f64,
    /// Peak favorable PnL percentage / 最大有利 PnL 百分比
    pub peak_favorable_pct: f64,
    /// Peak adverse PnL percentage / 最大不利 PnL 百分比
    pub peak_adverse_pct: f64,
    /// Whether the opportunity has been settled / 是否已結算
    pub is_settled: bool,
    /// Settlement reason: "virtual_sl" / "virtual_tp" / "ttl_expired" / ""
    /// 結算原因
    pub settle_reason: String,
}

impl SkippedOpportunity {
    /// Create a new skipped opportunity record.
    /// 創建新的跳過機會記錄。
    #[allow(clippy::too_many_arguments)]
    fn new(
        opp_id: String,
        symbol: &str,
        direction: &str,
        entry_price: f64,
        signal_confidence: f64,
        skip_reason: &str,
        skip_source: &str,
        strategy_name: &str,
        ts_ms: u64,
    ) -> Self {
        Self {
            opp_id,
            symbol: symbol.to_string(),
            direction: direction.to_string(),
            entry_price,
            entry_ts_ms: ts_ms,
            signal_confidence,
            skip_reason: truncate(skip_reason, 80),
            skip_source: skip_source.to_string(),
            strategy_name: strategy_name.to_string(),
            current_pnl_pct: 0.0,
            peak_favorable_pct: 0.0,
            peak_adverse_pct: 0.0,
            is_settled: false,
            settle_reason: String::new(),
        }
    }
}

/// Top missed opportunity entry for the summary.
/// 摘要中的頂級錯過機會條目。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TopMissed {
    /// Trading symbol / 交易對
    pub symbol: String,
    /// Direction / 方向
    pub direction: String,
    /// PnL percentage / PnL 百分比
    pub pnl_pct: f64,
    /// Strategy name / 策略名稱
    pub strategy_name: String,
}

/// Regret summary: bullets dodged vs missed profits.
/// 遺憾摘要：避開的虧損 vs 錯過的盈利。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RegretSummary {
    /// Count of settled opportunities that would have lost money.
    /// 結算後會虧損的機會數量。
    pub bullets_dodged: usize,
    /// Count of settled opportunities that would have profited.
    /// 結算後會盈利的機會數量。
    pub regret_from_undertrading: usize,
    /// "undertrading" / "overtrading" / "balanced"
    /// 淨遺憾方向
    pub net_regret_direction: String,
    /// Average regret PnL from profitable missed opportunities.
    /// 錯過的盈利機會的平均遺憾 PnL。
    pub avg_regret: f64,
    /// Average dodged PnL from losing missed opportunities.
    /// 避開的虧損機會的平均避開 PnL。
    pub avg_dodged: f64,
    /// Total tracked (active + settled in window).
    /// 總追蹤數（窗口內活躍 + 已結算）。
    pub total_tracked: usize,
    /// Total settled count.
    /// 總結算數。
    pub total_settled: usize,
    /// Hit rate if all skipped opportunities had been taken.
    /// 若所有跳過機會都被執行的勝率。
    pub hit_rate_if_taken: f64,
    /// Top missed profitable opportunities (up to 5).
    /// 頂級錯過的盈利機會（最多 5 個）。
    pub top_missed: Vec<TopMissed>,
}

impl Default for RegretSummary {
    fn default() -> Self {
        Self {
            bullets_dodged: 0,
            regret_from_undertrading: 0,
            net_regret_direction: "balanced".into(),
            avg_regret: 0.0,
            avg_dodged: 0.0,
            total_tracked: 0,
            total_settled: 0,
            hit_rate_if_taken: 0.0,
            top_missed: Vec::new(),
        }
    }
}

/// OpportunityTracker — tracks skipped trading opportunities with virtual PnL.
/// 機會追蹤器 — 追蹤被跳過的交易機會的虛擬 PnL。
pub struct OpportunityTracker {
    /// Active (unsettled) opportunities / 活躍（未結算）機會
    active: VecDeque<SkippedOpportunity>,
    /// Settled opportunity history / 已結算機會歷史
    settled: VecDeque<SkippedOpportunity>,
    /// Cached regret summary, invalidated on mutation / 緩存遺憾摘要，變更時失效
    cached_summary: Option<RegretSummary>,
}

impl OpportunityTracker {
    /// Create a new empty tracker.
    /// 創建新的空追蹤器。
    pub fn new() -> Self {
        Self {
            active: VecDeque::with_capacity(MAX_ACTIVE),
            settled: VecDeque::with_capacity(MAX_SETTLED),
            cached_summary: None,
        }
    }

    /// Record a skipped opportunity. Returns the opp_id.
    /// 記錄一個被跳過的機會。返回 opp_id。
    #[allow(clippy::too_many_arguments)]
    pub fn record_skipped(
        &mut self,
        symbol: &str,
        direction: &str,
        entry_price: f64,
        signal_confidence: f64,
        skip_reason: &str,
        skip_source: &str,
        strategy_name: &str,
        ts_ms: u64,
    ) -> String {
        let opp_id = Uuid::new_v4().to_string();

        let opp = SkippedOpportunity::new(
            opp_id.clone(),
            symbol,
            direction,
            entry_price,
            signal_confidence,
            skip_reason,
            skip_source,
            strategy_name,
            ts_ms,
        );

        self.active.push_back(opp);

        // Enforce max active capacity / 強制最大活躍容量
        while self.active.len() > MAX_ACTIVE {
            self.active.pop_front();
        }

        // Invalidate cache / 失效緩存 [R1-2]
        self.cached_summary = None;

        opp_id
    }

    /// Update virtual PnL for all active opportunities.
    /// 更新所有活躍機會的虛擬 PnL。
    ///
    /// [Q2] Virtual PnL deducts 2× fee (FRICTION_PCT) to suppress false regret.
    /// 虛擬 PnL 扣除 2× 費用以抑制虛假遺憾偏差。
    pub fn update_virtual_pnl(&mut self, current_prices: &HashMap<String, f64>, ts_ms: u64) {
        let mut any_settled = false;

        for opp in self.active.iter_mut() {
            if opp.is_settled {
                continue;
            }

            let price = match current_prices.get(&opp.symbol) {
                Some(&p) if p > 0.0 => p,
                _ => continue,
            };

            if opp.entry_price <= 0.0 {
                continue;
            }

            // Raw PnL calculation / 原始 PnL 計算
            let raw_pnl = if opp.direction == "long" {
                (price - opp.entry_price) / opp.entry_price * 100.0
            } else {
                (opp.entry_price - price) / opp.entry_price * 100.0
            };

            // [Q2] Deduct friction cost / 扣除摩擦成本
            let adjusted_pnl = raw_pnl - FRICTION_PCT;

            opp.current_pnl_pct = adjusted_pnl;

            // Update peaks / 更新峰值
            if adjusted_pnl > opp.peak_favorable_pct {
                opp.peak_favorable_pct = adjusted_pnl;
            }
            if adjusted_pnl < opp.peak_adverse_pct {
                opp.peak_adverse_pct = adjusted_pnl;
            }

            // Settlement triggers / 結算觸發條件
            if adjusted_pnl <= VIRTUAL_SL_PCT {
                opp.is_settled = true;
                opp.settle_reason = "virtual_sl".into();
                any_settled = true;
            } else if adjusted_pnl >= VIRTUAL_TP_PCT {
                opp.is_settled = true;
                opp.settle_reason = "virtual_tp".into();
                any_settled = true;
            } else if ts_ms.saturating_sub(opp.entry_ts_ms) > TTL_MS {
                opp.is_settled = true;
                opp.settle_reason = "ttl_expired".into();
                any_settled = true;
            }
        }

        // Flush settled to history / 批量移動已結算到歷史
        if any_settled {
            self.flush_settled();
            self.cached_summary = None;
        }
    }

    /// Move settled opportunities from active to history.
    /// 將已結算機會從活躍移到歷史。
    fn flush_settled(&mut self) {
        let mut remaining = VecDeque::with_capacity(self.active.len());

        while let Some(opp) = self.active.pop_front() {
            if opp.is_settled {
                self.settled.push_back(opp);
                // Enforce max settled capacity / 強制最大結算容量
                while self.settled.len() > MAX_SETTLED {
                    self.settled.pop_front();
                }
            } else {
                remaining.push_back(opp);
            }
        }

        self.active = remaining;
    }

    /// Get regret summary over a window. Returns cached if valid.
    /// 獲取指定窗口的遺憾摘要。有效時返回緩存。
    ///
    /// [Q3] Normalized direction comparison. [R1-8] Min 5 samples per side.
    pub fn get_regret_summary(&mut self, window_days: u64) -> &RegretSummary {
        if let Some(ref summary) = self.cached_summary {
            return summary;
        }

        let window_ms = window_days * 24 * 3600 * 1000;
        // Use the latest entry_ts_ms as "now" reference for deterministic tests,
        // falling back to 0 (which means the cutoff will be 0 — include everything).
        // 使用最新的 entry_ts_ms 作為「現在」參考以便確定性測試。
        let now_ms = self
            .active
            .iter()
            .chain(self.settled.iter())
            .map(|o| o.entry_ts_ms)
            .max()
            .unwrap_or(0);
        let cutoff_ms = now_ms.saturating_sub(window_ms);

        // Gather relevant opportunities within window / 收集窗口內相關機會
        let relevant: Vec<&SkippedOpportunity> = self
            .active
            .iter()
            .chain(self.settled.iter())
            .filter(|o| o.entry_ts_ms >= cutoff_ms)
            .collect();

        let mut would_profit: Vec<f64> = Vec::new();
        let mut would_loss: Vec<f64> = Vec::new();
        let mut top_candidates: Vec<TopMissed> = Vec::new();

        for opp in &relevant {
            let pnl = opp.current_pnl_pct;
            if pnl > 0.0 {
                would_profit.push(pnl);
                top_candidates.push(TopMissed {
                    symbol: opp.symbol.clone(),
                    direction: opp.direction.clone(),
                    pnl_pct: pnl,
                    strategy_name: opp.strategy_name.clone(),
                });
            } else {
                would_loss.push(pnl.abs());
            }
        }

        // Sort top missed descending by pnl / 按 PnL 降序排列
        top_candidates.sort_by(|a, b| {
            b.pnl_pct
                .partial_cmp(&a.pnl_pct)
                .unwrap_or(std::cmp::Ordering::Equal)
        });
        top_candidates.truncate(5);

        // [Q3] Normalized averages / 歸一化平均值
        let avg_regret = if would_profit.is_empty() {
            0.0
        } else {
            would_profit.iter().sum::<f64>() / would_profit.len() as f64
        };

        let avg_dodged = if would_loss.is_empty() {
            0.0
        } else {
            would_loss.iter().sum::<f64>() / would_loss.len() as f64
        };

        // [R1-8] Direction with minimum sample requirement / 帶最少樣本要求的方向判斷
        let net_regret_direction = if avg_regret > avg_dodged * 1.3
            && would_profit.len() >= MIN_SAMPLES_PER_DIRECTION
        {
            "undertrading"
        } else if avg_dodged > avg_regret * 1.3
            && would_loss.len() >= MIN_SAMPLES_PER_DIRECTION
        {
            "overtrading"
        } else {
            "balanced"
        };

        let total = relevant.len();
        let hit_rate = if total > 0 {
            would_profit.len() as f64 / total as f64
        } else {
            0.0
        };

        let summary = RegretSummary {
            bullets_dodged: would_loss.len(),
            regret_from_undertrading: would_profit.len(),
            net_regret_direction: net_regret_direction.into(),
            avg_regret,
            avg_dodged,
            total_tracked: self.active.len(),
            total_settled: self.settled.len(),
            hit_rate_if_taken: hit_rate,
            top_missed: top_candidates,
        };

        self.cached_summary = Some(summary);
        self.cached_summary.as_ref().unwrap()
    }

    /// Get current active count / 獲取當前活躍數量
    pub fn active_count(&self) -> usize {
        self.active.len()
    }

    /// Get current settled count / 獲取當前結算數量
    pub fn settled_count(&self) -> usize {
        self.settled.len()
    }
}

impl Default for OpportunityTracker {
    fn default() -> Self {
        Self::new()
    }
}

// ── Helpers / 輔助函數 ───────────────────────────────────────────────

/// Truncate a string to at most `max_len` bytes (safe at char boundary).
/// 截斷字串至最多 `max_len` 字節（安全字符邊界）。
fn truncate(s: &str, max_len: usize) -> String {
    if s.len() <= max_len {
        s.to_string()
    } else {
        let mut end = max_len;
        while end > 0 && !s.is_char_boundary(end) {
            end -= 1;
        }
        s[..end].to_string()
    }
}

// ── Tests / 測試 ─────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    const BASE_TS: u64 = 1_700_000_000_000;

    /// Helper: create a tracker with N skipped long BTCUSDT opportunities.
    /// 輔助：創建含 N 個做多 BTCUSDT 跳過機會的追蹤器。
    fn make_tracker_with_longs(n: usize, entry_price: f64) -> OpportunityTracker {
        let mut t = OpportunityTracker::new();
        for i in 0..n {
            t.record_skipped(
                "BTCUSDT",
                "long",
                entry_price,
                0.7,
                "low_confidence",
                "guardian",
                "ma_cross",
                BASE_TS + i as u64 * 1000,
            );
        }
        t
    }

    // ── 1. record_skipped basic / 基本記錄 ──

    #[test]
    fn test_record_skipped_returns_uuid() {
        let mut t = OpportunityTracker::new();
        let id = t.record_skipped(
            "BTCUSDT", "long", 65000.0, 0.7, "low_confidence", "guardian", "ma_cross", BASE_TS,
        );
        assert!(!id.is_empty());
        // UUID v4 format: 8-4-4-4-12
        assert_eq!(id.len(), 36);
        assert_eq!(t.active_count(), 1);
    }

    // ── 2. record_skipped increments active / 記錄增加活躍數 ──

    #[test]
    fn test_record_multiple() {
        let t = make_tracker_with_longs(5, 65000.0);
        assert_eq!(t.active_count(), 5);
        assert_eq!(t.settled_count(), 0);
    }

    // ── 3. update_virtual_pnl long profit / 做多盈利 ──

    #[test]
    fn test_update_pnl_long_profit() {
        let mut t = make_tracker_with_longs(1, 100.0);
        let mut prices = HashMap::new();
        prices.insert("BTCUSDT".to_string(), 110.0);
        t.update_virtual_pnl(&prices, BASE_TS + 1000);

        let opp = &t.active[0];
        // raw = (110-100)/100*100 = 10.0%, adjusted = 10.0 - 0.15 = 9.85%
        assert!((opp.current_pnl_pct - 9.85).abs() < 1e-10);
        assert!(!opp.is_settled); // 9.85 < 10.0, not yet TP
    }

    // ── 4. update_virtual_pnl short profit / 做空盈利 ──

    #[test]
    fn test_update_pnl_short_profit() {
        let mut t = OpportunityTracker::new();
        t.record_skipped("ETHUSDT", "short", 100.0, 0.8, "test", "h0", "strat", BASE_TS);

        let mut prices = HashMap::new();
        prices.insert("ETHUSDT".to_string(), 90.0);
        t.update_virtual_pnl(&prices, BASE_TS + 1000);

        let opp = &t.active[0];
        // raw = (100-90)/100*100 = 10.0%, adjusted = 9.85%
        assert!((opp.current_pnl_pct - 9.85).abs() < 1e-10);
    }

    // ── 5. settlement via virtual_sl / 虛擬止損結算 ──

    #[test]
    fn test_settlement_virtual_sl() {
        let mut t = make_tracker_with_longs(1, 100.0);
        let mut prices = HashMap::new();
        // adjusted <= -5.0 → raw <= -4.85 → p <= 95.15
        // Use p = 94.0: raw = -6.0, adjusted = -6.15
        prices.insert("BTCUSDT".to_string(), 94.0);
        t.update_virtual_pnl(&prices, BASE_TS + 1000);

        assert_eq!(t.active_count(), 0);
        assert_eq!(t.settled_count(), 1);
        assert_eq!(t.settled[0].settle_reason, "virtual_sl");
    }

    // ── 6. settlement via virtual_tp / 虛擬止盈結算 ──

    #[test]
    fn test_settlement_virtual_tp() {
        let mut t = make_tracker_with_longs(1, 100.0);
        let mut prices = HashMap::new();
        // adjusted >= 10.0 → raw >= 10.15 → p >= 110.15
        prices.insert("BTCUSDT".to_string(), 111.0);
        t.update_virtual_pnl(&prices, BASE_TS + 1000);

        assert_eq!(t.active_count(), 0);
        assert_eq!(t.settled_count(), 1);
        assert_eq!(t.settled[0].settle_reason, "virtual_tp");
    }

    // ── 7. settlement via ttl_expired / TTL 過期結算 ──

    #[test]
    fn test_settlement_ttl_expired() {
        let mut t = make_tracker_with_longs(1, 100.0);
        let mut prices = HashMap::new();
        prices.insert("BTCUSDT".to_string(), 101.0); // small move, no SL/TP

        let expired_ts = BASE_TS + TTL_MS + 1;
        t.update_virtual_pnl(&prices, expired_ts);

        assert_eq!(t.active_count(), 0);
        assert_eq!(t.settled_count(), 1);
        assert_eq!(t.settled[0].settle_reason, "ttl_expired");
    }

    // ── 8. regret direction: undertrading / 遺憾方向：交易不足 ──

    #[test]
    fn test_regret_direction_undertrading() {
        let mut t = OpportunityTracker::new();
        // Create 6 profitable (will be settled via TP) + 2 losing (settled via SL)
        for i in 0..6 {
            t.record_skipped(
                "BTCUSDT", "long", 100.0, 0.8, "test", "guardian", "strat",
                BASE_TS + i * 1000,
            );
        }
        for i in 0..2 {
            t.record_skipped(
                "ETHUSDT", "long", 100.0, 0.5, "test", "guardian", "strat",
                BASE_TS + (6 + i) * 1000,
            );
        }

        let mut prices = HashMap::new();
        prices.insert("BTCUSDT".to_string(), 112.0); // TP trigger
        prices.insert("ETHUSDT".to_string(), 93.0);  // SL trigger
        t.update_virtual_pnl(&prices, BASE_TS + 10_000);

        let summary = t.get_regret_summary(7).clone();
        // 6 profitable (avg ~11.85) vs 2 losses (avg ~6.85)
        // avg_regret (11.85) > avg_dodged (6.85) * 1.3 = 8.905 → yes
        // profitable count (6) >= 5 → yes
        assert_eq!(summary.net_regret_direction, "undertrading");
        assert_eq!(summary.regret_from_undertrading, 6);
        assert_eq!(summary.bullets_dodged, 2);
    }

    // ── 9. regret direction: overtrading / 遺憾方向：交易過度 ──

    #[test]
    fn test_regret_direction_overtrading() {
        let mut t = OpportunityTracker::new();
        // 1 small profitable (TTL expired, small gain)
        t.record_skipped(
            "BTCUSDT", "long", 100.0, 0.8, "test", "guardian", "strat", BASE_TS,
        );
        // 6 losing (SL hit)
        for i in 0..6 {
            t.record_skipped(
                &format!("COIN{}USDT", i), "long", 100.0, 0.5, "test", "guardian", "strat",
                BASE_TS + (1 + i as u64) * 1000,
            );
        }

        let mut prices = HashMap::new();
        prices.insert("BTCUSDT".to_string(), 101.0); // small gain
        for i in 0..6 {
            prices.insert(format!("COIN{}USDT", i), 93.0); // SL
        }
        // TTL expire for BTC, SL for coins
        t.update_virtual_pnl(&prices, BASE_TS + TTL_MS + 1);

        let summary = t.get_regret_summary(30).clone();
        // BTC: adjusted=0.85 → profit; COINs: adjusted=-7.15 → loss
        // avg_regret=0.85, avg_dodged=7.15
        // 7.15 > 0.85*1.3=1.105 → yes, loss count=6 >= 5 → yes
        assert_eq!(summary.net_regret_direction, "overtrading");
        assert!(summary.bullets_dodged >= 6);
    }

    // ── 10. regret direction balanced with insufficient samples / 樣本不足時平衡 ──

    #[test]
    fn test_regret_direction_balanced_insufficient_samples() {
        let mut t = OpportunityTracker::new();
        // Only 3 profitable (< MIN_SAMPLES_PER_DIRECTION = 5)
        for i in 0..3 {
            t.record_skipped(
                "BTCUSDT", "long", 100.0, 0.8, "test", "guardian", "strat",
                BASE_TS + i * 1000,
            );
        }

        let mut prices = HashMap::new();
        prices.insert("BTCUSDT".to_string(), 112.0); // TP
        t.update_virtual_pnl(&prices, BASE_TS + 5000);

        let summary = t.get_regret_summary(7).clone();
        assert_eq!(summary.net_regret_direction, "balanced");
    }

    // ── 11. cache invalidation on record / 記錄時緩存失效 ──

    #[test]
    fn test_cache_invalidation_on_record() {
        let mut t = make_tracker_with_longs(3, 100.0);

        // Build cache
        let _s1 = t.get_regret_summary(7).clone();
        assert!(t.cached_summary.is_some());

        // Record new → cache invalidated
        t.record_skipped("XRPUSDT", "short", 0.5, 0.6, "test", "h0", "rsi", BASE_TS + 10_000);
        assert!(t.cached_summary.is_none());
    }

    // ── 12. cache invalidation on settlement / 結算時緩存失效 ──

    #[test]
    fn test_cache_invalidation_on_settlement() {
        let mut t = make_tracker_with_longs(1, 100.0);

        // Build cache
        let _s1 = t.get_regret_summary(7).clone();
        assert!(t.cached_summary.is_some());

        // Trigger SL → cache invalidated
        let mut prices = HashMap::new();
        prices.insert("BTCUSDT".to_string(), 94.0);
        t.update_virtual_pnl(&prices, BASE_TS + 1000);
        assert!(t.cached_summary.is_none());
    }

    // ── 13. max active capacity enforcement / 最大活躍容量限制 ──

    #[test]
    fn test_max_active_enforcement() {
        let t = make_tracker_with_longs(120, 65000.0);
        assert_eq!(t.active_count(), MAX_ACTIVE);
    }

    // ── 14. peak tracking / 峰值追蹤 ──

    #[test]
    fn test_peak_tracking() {
        let mut t = make_tracker_with_longs(1, 100.0);
        let mut prices = HashMap::new();

        // First tick: price up
        prices.insert("BTCUSDT".to_string(), 105.0);
        t.update_virtual_pnl(&prices, BASE_TS + 1000);
        let peak_fav = t.active[0].peak_favorable_pct;
        assert!(peak_fav > 4.5); // ~4.85

        // Second tick: price down
        prices.insert("BTCUSDT".to_string(), 98.0);
        t.update_virtual_pnl(&prices, BASE_TS + 2000);
        let opp = &t.active[0];
        // Peak favorable should remain from first tick
        assert!((opp.peak_favorable_pct - peak_fav).abs() < 1e-10);
        // Peak adverse should reflect current drawdown
        assert!(opp.peak_adverse_pct < -1.5); // ~-2.15
    }

    // ── 15. skip_reason truncation / 跳過原因截斷 ──

    #[test]
    fn test_skip_reason_truncation() {
        let mut t = OpportunityTracker::new();
        let long_reason = "a".repeat(200);
        t.record_skipped(
            "BTCUSDT", "long", 65000.0, 0.7, &long_reason, "guardian", "strat", BASE_TS,
        );
        assert!(t.active[0].skip_reason.len() <= 80);
    }

    // ── 16. top_missed ordering / 頂級錯過排序 ──

    #[test]
    fn test_top_missed_ordering() {
        let mut t = OpportunityTracker::new();
        let symbols = ["AAUSDT", "BBUSDT", "CCUSDT"];
        for (i, sym) in symbols.iter().enumerate() {
            t.record_skipped(
                sym, "long", 100.0, 0.7, "test", "guardian", "strat",
                BASE_TS + i as u64 * 1000,
            );
        }

        let mut prices = HashMap::new();
        prices.insert("AAUSDT".to_string(), 103.0); // +2.85%
        prices.insert("BBUSDT".to_string(), 108.0); // +7.85%
        prices.insert("CCUSDT".to_string(), 105.0); // +4.85%
        t.update_virtual_pnl(&prices, BASE_TS + 5000);

        let summary = t.get_regret_summary(7).clone();
        assert_eq!(summary.top_missed.len(), 3);
        assert_eq!(summary.top_missed[0].symbol, "BBUSDT");
        assert_eq!(summary.top_missed[1].symbol, "CCUSDT");
        assert_eq!(summary.top_missed[2].symbol, "AAUSDT");
    }

    // ── 17. empty tracker summary / 空追蹤器摘要 ──

    #[test]
    fn test_empty_tracker_summary() {
        let mut t = OpportunityTracker::new();
        let summary = t.get_regret_summary(7).clone();
        assert_eq!(summary.net_regret_direction, "balanced");
        assert_eq!(summary.total_tracked, 0);
        assert_eq!(summary.total_settled, 0);
        assert!((summary.hit_rate_if_taken - 0.0).abs() < f64::EPSILON);
    }

    // ── 18. missing price skipped / 缺少價格時跳過更新 ──

    #[test]
    fn test_missing_price_skipped() {
        let mut t = make_tracker_with_longs(1, 100.0);
        let prices = HashMap::new(); // empty
        t.update_virtual_pnl(&prices, BASE_TS + 1000);

        assert!((t.active[0].current_pnl_pct - 0.0).abs() < f64::EPSILON);
        assert!(!t.active[0].is_settled);
    }
}
