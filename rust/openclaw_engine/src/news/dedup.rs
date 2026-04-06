// MODULE_NOTE
// EN: Headline deduplication — SHA1[:16] hash + 24h sliding window.
//     In-memory only (no PG); pipeline calls check_and_record per item.
// 中文: 標題去重 — SHA1[:16] hash + 24h 滑動窗口。
//       純記憶體（不寫 PG），pipeline 對每條呼叫 check_and_record。

use sha1::{Digest, Sha1};
use std::collections::HashMap;
use std::sync::Mutex;

/// EN: Default sliding window: 24 hours.
/// 中文: 預設滑動窗口：24 小時。
pub const DEFAULT_WINDOW_HOURS: i64 = 24;

/// EN: Sliding-window dedup cache. Thread-safe via Mutex.
/// 中文: 滑動窗口去重快取。Mutex 保證線程安全。
pub struct DedupCache {
    /// EN: hash → first_seen_ms.
    /// 中文: hash → 首次見到的毫秒時間戳。
    seen: Mutex<HashMap<String, i64>>,
    /// EN: Window size in milliseconds.
    /// 中文: 窗口長度（毫秒）。
    window_ms: i64,
}

impl DedupCache {
    /// EN: Create a cache with the given window in hours.
    /// 中文: 用指定窗口（小時）建立快取。
    pub fn with_window_hours(hours: i64) -> Self {
        Self {
            seen: Mutex::new(HashMap::new()),
            window_ms: hours.saturating_mul(3600).saturating_mul(1000),
        }
    }

    /// EN: Default 24h window.
    /// 中文: 預設 24 小時窗口。
    pub fn new() -> Self {
        Self::with_window_hours(DEFAULT_WINDOW_HOURS)
    }

    /// EN: Compute SHA1[:16] of a normalized headline.
    ///     Normalization: trim → lowercase → collapse runs of whitespace to single space.
    /// 中文: 計算標準化標題的 SHA1 前 16 hex chars。
    ///       標準化：trim → lowercase → 連續空白合併為單一空格。
    pub fn hash_headline(headline: &str) -> String {
        let normalized: String = headline
            .trim()
            .to_lowercase()
            .split_whitespace()
            .collect::<Vec<_>>()
            .join(" ");
        let mut hasher = Sha1::new();
        hasher.update(normalized.as_bytes());
        let result = hasher.finalize();
        hex::encode(result)[..16].to_string()
    }

    /// EN: Returns true if this headline is NEW (not seen within window).
    ///     Side effect: records the headline as seen at now_ms.
    /// 中文: 返回 true 表示這條標題是新的（未在窗口內見過）。
    ///       副作用：記錄為 now_ms 已見。
    pub fn check_and_record(&self, headline: &str, now_ms: i64) -> bool {
        let hash = Self::hash_headline(headline);
        self.gc(now_ms);
        let mut guard = self.seen.lock().expect("dedup cache mutex poisoned");
        if let Some(&first) = guard.get(&hash) {
            // EN: Within window → duplicate.
            // 中文: 在窗口內 → 重複。
            if now_ms.saturating_sub(first) <= self.window_ms {
                return false;
            }
        }
        guard.insert(hash, now_ms);
        true
    }

    /// EN: Garbage-collect entries older than window.
    /// 中文: 回收超過窗口的條目。
    fn gc(&self, now_ms: i64) {
        let cutoff = now_ms.saturating_sub(self.window_ms);
        let mut guard = self.seen.lock().expect("dedup cache mutex poisoned");
        guard.retain(|_, &mut first_seen| first_seen >= cutoff);
    }

    /// EN: Current cache size (number of tracked hashes).
    /// 中文: 當前快取大小（追蹤的 hash 數）。
    pub fn cache_size(&self) -> usize {
        self.seen.lock().expect("dedup cache mutex poisoned").len()
    }
}

impl Default for DedupCache {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const T0: i64 = 1_700_000_000_000;
    const HOUR_MS: i64 = 3_600_000;

    #[test]
    fn test_dedup_first_headline_is_new() {
        // EN: A fresh headline returns true on first sight.
        // 中文: 新標題首次出現返回 true。
        let cache = DedupCache::new();
        assert!(cache.check_and_record("Bitcoin halving!", T0));
        assert_eq!(cache.cache_size(), 1);
    }

    #[test]
    fn test_dedup_same_headline_within_window_blocked() {
        // EN: Same headline within window → duplicate (false).
        // 中文: 窗口內相同標題 → 重複（false）。
        let cache = DedupCache::new();
        assert!(cache.check_and_record("SEC filed lawsuit", T0));
        assert!(!cache.check_and_record("SEC filed lawsuit", T0 + HOUR_MS));
        assert!(!cache.check_and_record("SEC filed lawsuit", T0 + 23 * HOUR_MS));
    }

    #[test]
    fn test_dedup_normalized_whitespace_collapses() {
        // EN: Whitespace and case differences hash to the same value.
        // 中文: 空白與大小寫差異 hash 為同一值。
        let h1 = DedupCache::hash_headline("Bitcoin  halving!");
        let h2 = DedupCache::hash_headline("bitcoin halving!");
        let h3 = DedupCache::hash_headline("  BITCOIN\thalving!  ");
        assert_eq!(h1, h2);
        assert_eq!(h2, h3);

        let cache = DedupCache::new();
        assert!(cache.check_and_record("Bitcoin  halving!", T0));
        assert!(!cache.check_and_record("bitcoin halving!", T0 + 1_000));
    }

    #[test]
    fn test_dedup_gc_clears_old_entries() {
        // EN: After 25h, old entry is gc'd; same headline counts as new again.
        // 中文: 25 小時後，舊條目被 gc，同樣標題再次視為新。
        let cache = DedupCache::new();
        assert!(cache.check_and_record("Old news", T0));
        // EN: 25h later — outside 24h window.
        // 中文: 25 小時後 — 在 24h 窗口外。
        assert!(cache.check_and_record("Old news", T0 + 25 * HOUR_MS));
        // EN: gc should have removed the original entry; only the new one remains.
        // 中文: gc 應已移除原條目，僅留新條目。
        assert_eq!(cache.cache_size(), 1);
    }

    #[test]
    fn test_dedup_hash_length_is_16_hex() {
        // EN: hash_headline always returns 16 hex chars.
        // 中文: hash_headline 永遠回 16 個 hex 字元。
        let h = DedupCache::hash_headline("anything");
        assert_eq!(h.len(), 16);
        assert!(h.chars().all(|c| c.is_ascii_hexdigit()));
    }
}
