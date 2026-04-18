//! `TrendCooldown` — per-symbol "last trade time" gate with `saturating_sub` math.
//! `TrendCooldown` — 以 `saturating_sub` 計算的逐 symbol 冷卻閘門。
//!
//! MODULE_NOTE (EN): Replaces ad-hoc `HashMap<String, u64>` "last trade ms"
//!   trackers in funding_arb / bb_breakout / bb_reversion / ma_crossover.
//!   Semantics MUST match the pre-extraction behavior of each caller:
//!     * unseen symbol → cooled (allowed to trade).
//!     * `now_ms.saturating_sub(last_ms) >= duration_ms` → cooled.
//!     * backward clock skew (`now_ms < last_ms`) → `saturating_sub` returns 0
//!       → NOT cooled → treated as a fresh signal, entry is blocked until the
//!       clock recovers. This is intentional "over-conservative" behavior
//!       carried forward from the extracted code.
//!   `duration_ms` is held on the struct so hot-reloaded config values
//!   (`update_params` / IPC) update the gate without rebuilding the map.
//! MODULE_NOTE (中): 取代 funding_arb / bb_breakout / bb_reversion / ma_crossover
//!   中零散的 `HashMap<String, u64>` 冷卻欄位。語意必須與原本行為一致：
//!     * 未記錄的 symbol → 視為已冷卻（允許交易）。
//!     * `now_ms.saturating_sub(last_ms) >= duration_ms` → 已冷卻。
//!     * 時鐘倒退（`now_ms < last_ms`）→ `saturating_sub` 回 0 → 視為「未冷卻」
//!       → 進場被阻擋直到時鐘恢復，這是原程式碼刻意的保守行為，此處一併沿用。
//!   `duration_ms` 存於 struct，使 IPC / `update_params` 熱更新參數時
//!   不需重建整個 map。

use std::collections::HashMap;

/// Per-symbol cooldown tracker. / 逐 symbol 冷卻追蹤器。
#[derive(Debug, Clone)]
pub struct TrendCooldown {
    last_signal_ms: HashMap<String, u64>,
    duration_ms: u64,
}

impl TrendCooldown {
    /// Build a tracker with the given base cooldown. / 以給定基礎冷卻時間建立追蹤器。
    pub fn new(duration_ms: u64) -> Self {
        Self {
            last_signal_ms: HashMap::new(),
            duration_ms,
        }
    }

    /// Is this symbol currently cooled-down (i.e. eligible to trade)?
    ///
    /// Returns `true` when either the symbol has no prior record, or the
    /// configured duration has elapsed since the last record. Uses
    /// `saturating_sub` so that a backward clock skew never produces a
    /// negative "time since last" — instead the caller sees "not cooled"
    /// until the clock reaches the prior `last_ms`.
    /// 該 symbol 是否已冷卻完畢（可交易）？
    ///
    /// 沒有紀錄或距離上次紀錄已超過冷卻時間 → `true`。
    /// 使用 `saturating_sub` 防止時鐘倒退造成負值；時鐘倒退期間會回 `false`。
    pub fn is_cooled_down(&self, symbol: &str, now_ms: u64) -> bool {
        match self.last_signal_ms.get(symbol) {
            None => true,
            Some(&last_ms) => now_ms.saturating_sub(last_ms) >= self.duration_ms,
        }
    }

    /// Record a trade/signal for the given symbol at `now_ms`.
    /// 為給定 symbol 紀錄交易/信號時間 `now_ms`。
    pub fn record_signal(&mut self, symbol: &str, now_ms: u64) {
        self.last_signal_ms.insert(symbol.to_string(), now_ms);
    }

    /// Forget the last-signal record for a single symbol (used for RC-04
    /// rejection rollback and for `on_external_close`).
    /// 忘記單一 symbol 的最後信號時間（供 RC-04 拒絕回滾與外部平倉使用）。
    pub fn clear(&mut self, symbol: &str) {
        self.last_signal_ms.remove(symbol);
    }

    /// Peek the last recorded time for a symbol. / 查詢該 symbol 最後紀錄時間。
    pub fn last_ms(&self, symbol: &str) -> Option<u64> {
        self.last_signal_ms.get(symbol).copied()
    }

    /// Hot-reload the cooldown duration. The symbol map is NOT cleared —
    /// existing timers are re-evaluated against the new duration on the next
    /// `is_cooled_down` call, matching the hot-reload semantics of every
    /// upstream strategy.
    /// 熱更新冷卻時間。不清空 map — 現存計時會在下次 `is_cooled_down`
    /// 呼叫時用新時長重新判斷，與各策略原本熱更新語意一致。
    pub fn set_duration(&mut self, duration_ms: u64) {
        self.duration_ms = duration_ms;
    }

    /// Current configured duration (primarily for diagnostics / tests).
    /// 當前設定的冷卻時長（主要供診斷與測試）。
    pub fn duration_ms(&self) -> u64 {
        self.duration_ms
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_unseen_symbol_is_cooled() {
        // No prior record → immediately eligible (matches pre-extraction
        // "last_ms == 0" sentinel and funding_arb's HashMap-absent branch).
        // 無紀錄 → 立即可交易。
        let tc = TrendCooldown::new(60_000);
        assert!(tc.is_cooled_down("BTCUSDT", 1_000_000));
    }

    #[test]
    fn test_cooldown_blocks_then_releases() {
        // Within the window → blocked; at exactly the boundary → released.
        // 冷卻期內 → 阻擋；剛好到期 → 放行。
        let mut tc = TrendCooldown::new(60_000);
        tc.record_signal("BTCUSDT", 1_000);
        assert!(!tc.is_cooled_down("BTCUSDT", 1_000 + 59_999));
        assert!(tc.is_cooled_down("BTCUSDT", 1_000 + 60_000));
        assert!(tc.is_cooled_down("BTCUSDT", 1_000 + 120_000));
    }

    #[test]
    fn test_backward_clock_skew_blocks() {
        // now < last → saturating_sub = 0 → "not cooled". This matches the
        // existing over-conservative behavior of every extracted strategy
        // (better to wait than to trade with a time paradox).
        // now < last → saturating_sub 得 0 → 視為未冷卻，此為原策略保守行為。
        let mut tc = TrendCooldown::new(60_000);
        tc.record_signal("BTCUSDT", 1_000_000);
        assert!(!tc.is_cooled_down("BTCUSDT", 999_999));
        assert!(!tc.is_cooled_down("BTCUSDT", 0));
    }

    #[test]
    fn test_clear_forgets_single_symbol() {
        // clear() only affects the named symbol; others remain tracked.
        // clear() 只影響指定 symbol，其餘不受影響。
        let mut tc = TrendCooldown::new(60_000);
        tc.record_signal("BTC", 1_000);
        tc.record_signal("ETH", 1_000);
        tc.clear("BTC");
        assert!(tc.is_cooled_down("BTC", 1_001)); // forgotten → eligible
        assert!(!tc.is_cooled_down("ETH", 1_001)); // still cooling
    }

    #[test]
    fn test_set_duration_hot_reload_reevaluates_in_place() {
        // Hot-reload must NOT clear the last-signal map — the same timestamp
        // is simply compared against the new window. Matches `update_params`
        // semantics in each strategy.
        // 熱更新時長不清空 last-signal map，延用相同時間戳，與策略 update_params 一致。
        let mut tc = TrendCooldown::new(60_000);
        tc.record_signal("BTC", 1_000);
        assert!(!tc.is_cooled_down("BTC", 30_000)); // 29s elapsed < 60s
        tc.set_duration(10_000);
        assert!(tc.is_cooled_down("BTC", 30_000)); // 29s >= 10s → released
        assert_eq!(tc.duration_ms(), 10_000);
    }

    #[test]
    fn test_record_overwrites_previous() {
        // A second record_signal for the same symbol resets the clock.
        // 同一 symbol 第二次 record_signal 重置計時。
        let mut tc = TrendCooldown::new(60_000);
        tc.record_signal("BTC", 1_000);
        tc.record_signal("BTC", 100_000);
        assert_eq!(tc.last_ms("BTC"), Some(100_000));
        assert!(!tc.is_cooled_down("BTC", 150_000)); // 50s < 60s since latest
        assert!(tc.is_cooled_down("BTC", 160_000));
    }
}
