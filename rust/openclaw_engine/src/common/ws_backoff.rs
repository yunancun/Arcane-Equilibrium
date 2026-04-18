//! Exponential backoff helper for WebSocket reconnect loops.
//! WebSocket 重連循環的指數退避輔助模組。
//!
//! MODULE_NOTE (EN): Extracted from ws_client.rs + bybit_private_ws.rs (E1-P0-3).
//!   Callers pass `base_delay` at each `next_delay()` call so that ws_client.rs
//!   can re-read `cfg.reconnect_delay_ms` on every loop iteration (FA-1 risk #1).
//!   Semantics are byte-identical to the previous inline formula:
//!     delay_ms = min(base * multiplier.saturating_pow(attempt), max_ms)
//!   First reconnect (attempt=1) therefore = base * multiplier, NOT base.
//!   `jitter_pct` MUST default to 0: any non-zero value introduces RNG and
//!   breaks deterministic replay tests. It is reserved for future opt-in use.
//! MODULE_NOTE (中): 從 ws_client.rs + bybit_private_ws.rs 提取（E1-P0-3）。
//!   調用方在每次 `next_delay()` 傳入 `base_delay`，使 ws_client.rs 可在每次
//!   迴圈重新讀取 `cfg.reconnect_delay_ms`（FA-1 風險 #1）。
//!   語意與先前內嵌公式字節一致：
//!     delay_ms = min(base * multiplier.saturating_pow(attempt), max_ms)
//!   故首次重連（attempt=1）= base * multiplier，並非 base。
//!   `jitter_pct` 必須預設為 0：任何非零值將引入隨機源並破壞確定性重播測試，
//!   此欄位保留給未來 opt-in 使用。

use std::time::Duration;

/// Backoff policy configuration / 退避策略設定。
///
/// EN: `initial_ms` is the base delay (multiplied by `multiplier^attempt`),
///     `max_ms` caps the resulting delay, `multiplier` is the exponent base,
///     `jitter_pct` is reserved (0 = no RNG; non-zero is not used yet).
/// 中文: `initial_ms` 為基礎延遲（被 `multiplier^attempt` 相乘），
///     `max_ms` 為結果延遲上限，`multiplier` 為指數底，
///     `jitter_pct` 為保留欄位（0 = 無隨機；目前不使用非零值）。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct BackoffConfig {
    /// Base delay (ms) used when caller does not override per-call.
    /// 基礎延遲（毫秒），當調用方未於 per-call 覆寫時使用。
    pub initial_ms: u64,
    /// Hard ceiling for computed delay (ms).
    /// 計算延遲的硬上限（毫秒）。
    pub max_ms: u64,
    /// Exponential multiplier (Bybit default 2).
    /// 指數倍數（Bybit 預設為 2）。
    pub multiplier: u64,
    /// Jitter percent (0..=100). 0 = deterministic (no RNG). Reserved.
    /// 抖動百分比（0..=100）。0 = 確定性（無隨機）。保留欄位。
    pub jitter_pct: u8,
}

impl BackoffConfig {
    /// Public-WS default (base configurable at runtime via ConfigManager).
    /// 公共 WS 預設值（base 由 ConfigManager 執行期設定）。
    ///
    /// EN: `base_ms` is supplied by the caller because ws_client.rs reads
    ///     `cfg.reconnect_delay_ms` on every loop iteration; freezing it in
    ///     the struct would defeat hot-reload.
    /// 中文: 因為 ws_client.rs 於每次迴圈讀取 `cfg.reconnect_delay_ms`，
    ///     由調用方提供 `base_ms`；若凍結在結構體內將破壞熱重載。
    pub const fn ws_public_default(base_ms: u64) -> Self {
        Self {
            initial_ms: base_ms,
            max_ms: 60_000,
            multiplier: 2,
            jitter_pct: 0,
        }
    }

    /// Private-WS default (Bybit fixed 3s base) / 私有 WS 預設值（Bybit 固定 3s base）。
    pub const fn ws_private_default() -> Self {
        Self {
            initial_ms: 3_000,
            max_ms: 60_000,
            multiplier: 2,
            jitter_pct: 0,
        }
    }

    /// Compute delay for the given attempt using a caller-supplied base.
    /// 依調用方提供的 base 計算指定嘗試次數的延遲。
    ///
    /// EN: Mirrors the previous inline formula byte-for-byte:
    ///     `min(base * multiplier.saturating_pow(attempt), max_ms)`
    ///     The caller passes `base` so public-WS can reflect hot-reloaded
    ///     `cfg.reconnect_delay_ms`. For private-WS pass `self.initial_ms`.
    /// 中文: 與先前內嵌公式字節一致：
    ///     `min(base * multiplier.saturating_pow(attempt), max_ms)`
    ///     調用方傳入 `base` 以便公共 WS 反映熱重載的 `cfg.reconnect_delay_ms`；
    ///     私有 WS 可直接傳入 `self.initial_ms`。
    pub fn next_delay_with_base(&self, base_ms: u64, attempt: u32) -> Duration {
        let factor = self.multiplier.saturating_pow(attempt);
        let raw = base_ms.saturating_mul(factor);
        let capped = std::cmp::min(raw, self.max_ms);
        Duration::from_millis(capped)
    }

    /// Compute delay using the configured `initial_ms` as base.
    /// 以設定的 `initial_ms` 為 base 計算延遲。
    ///
    /// EN: Convenience for callers (e.g. private WS) that do not hot-reload
    ///     the base delay from an external config source.
    /// 中文: 給予不從外部設定熱重載 base 延遲的調用方（例如私有 WS）的便利包裝。
    pub fn next_delay(&self, attempt: u32) -> Duration {
        self.next_delay_with_base(self.initial_ms, attempt)
    }
}

// ---------------------------------------------------------------------------
// Tests / 測試
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    /// EN: Public-WS default values match the pre-extraction constants.
    /// 中文: 公共 WS 預設值與提取前常量一致。
    #[test]
    fn test_ws_public_default_constants() {
        let cfg = BackoffConfig::ws_public_default(3_000);
        assert_eq!(cfg.initial_ms, 3_000);
        assert_eq!(cfg.max_ms, 60_000);
        assert_eq!(cfg.multiplier, 2);
        assert_eq!(cfg.jitter_pct, 0);
    }

    /// EN: Private-WS default matches pre-extraction constants.
    /// 中文: 私有 WS 預設值與提取前常量一致。
    #[test]
    fn test_ws_private_default_constants() {
        let cfg = BackoffConfig::ws_private_default();
        assert_eq!(cfg.initial_ms, 3_000);
        assert_eq!(cfg.max_ms, 60_000);
        assert_eq!(cfg.multiplier, 2);
        assert_eq!(cfg.jitter_pct, 0);
    }

    /// EN: Formula reproduces the old inline calculation byte-for-byte.
    ///     attempt=1 → base*2; attempt=5 → hits cap.
    /// 中文: 公式與原內嵌計算字節一致。attempt=1 → base*2；attempt=5 → 撞上限。
    #[test]
    fn test_next_delay_byte_identical_to_legacy() {
        let cfg = BackoffConfig::ws_public_default(3_000);
        // attempt 1: 3000 * 2^1 = 6000
        assert_eq!(cfg.next_delay_with_base(3_000, 1), Duration::from_millis(6_000));
        // attempt 5: 3000 * 2^5 = 96000 → capped at 60000
        assert_eq!(
            cfg.next_delay_with_base(3_000, 5),
            Duration::from_millis(60_000)
        );
        // next_delay (no-arg) matches next_delay_with_base(initial_ms,...)
        assert_eq!(cfg.next_delay(1), cfg.next_delay_with_base(3_000, 1));
    }

    /// EN: Saturation protects against overflow at extreme attempts.
    /// 中文: 極端嘗試次數下飽和運算保護避免溢位。
    #[test]
    fn test_saturation_at_extreme_attempt() {
        let cfg = BackoffConfig::ws_private_default();
        // Very large attempt: saturating_pow saturates to u64::MAX,
        // saturating_mul saturates, then cap clamps to max_ms.
        let delay = cfg.next_delay(u32::MAX);
        assert_eq!(delay, Duration::from_millis(60_000));
    }

    /// EN: Monotonic non-decreasing progression until cap.
    /// 中文: 延遲單調非遞減直到上限。
    #[test]
    fn test_monotonic_progression_until_cap() {
        let cfg = BackoffConfig::ws_public_default(3_000);
        let mut prev = Duration::from_millis(0);
        for attempt in 1..=10u32 {
            let d = cfg.next_delay_with_base(3_000, attempt);
            assert!(d >= prev, "delay must be non-decreasing");
            assert!(
                d <= Duration::from_millis(60_000),
                "delay must never exceed cap"
            );
            prev = d;
        }
        assert_eq!(prev, Duration::from_millis(60_000));
    }

    /// EN: Caller-supplied base takes effect (hot-reload path).
    /// 中文: 調用方傳入的 base 生效（熱重載路徑）。
    #[test]
    fn test_caller_supplied_base_overrides_initial_ms() {
        let cfg = BackoffConfig::ws_public_default(3_000);
        // Caller passes a different base (simulating runtime config change).
        // attempt=1 * mult=2 → 1000*2=2000
        assert_eq!(
            cfg.next_delay_with_base(1_000, 1),
            Duration::from_millis(2_000)
        );
    }
}
