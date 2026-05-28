//! Wave 5 Packet C / C3 — `WallClock` 真實 `FailsafeClock` 實作。
//!
//! 模塊用途：
//!   把 `super::super::FailsafeClock` trait 的 runtime 注入端從 `SystemTime::now()`
//!   讀出 UTC epoch 毫秒，餵給 `FailsafeWatcher` 計算 1h timer expiry。
//!
//! 為什麼獨立檔：
//!   - 測試端可換成 `MockClock` 注入；production 端用 `WallClock`；
//!   - clock 抽象是 fail-safe 邏輯的時間基準，必須與 `Instant`（單調但無 epoch）
//!     區分 — `now_ms()` 是 wall-clock UTC 毫秒，會 jump（NTP 修正、leap）但對 1h
//!     量級的 fail-safe timer 影響可忽略。
//!
//! 不變量（per CLAUDE.md §二 原則 5「survival 優先」 + §四「fail-soft、不 panic」）：
//!   - `SystemTime::now()` 對齊 `UNIX_EPOCH`；極罕見 clock 倒退到 epoch 之前
//!     （`duration_since` 回 Err）時 fail-soft 回 0；
//!   - 0 是合法的「epoch 起點」值；對 `FailsafeWatcher::timer_armed_at_ms`
//!     語義上代表「最遠的過去」，配合 `saturating_sub` 不會誤觸發新武裝；
//!   - 永不 panic、永不 unwrap。
//!
//! ref: docs/execution_plan/specs/2026-05-28--packet_c_3way_dispatcher_wire_spec.md §4.3

use std::time::{SystemTime, UNIX_EPOCH};

use crate::notification_failsafe::FailsafeClock;

/// 真實 wall-clock 注入器。
///
/// 對齊 `SystemTime::UNIX_EPOCH` 毫秒 — `FailsafeWatcherState::timer_armed_at_ms`
/// 與 `now_ms()` 採同樣 epoch 才能正確計算 elapsed。
///
/// 零狀態 / 零分配；可自由 clone / share。
#[derive(Debug, Default, Clone, Copy)]
pub struct WallClock;

impl WallClock {
    /// 顯式 constructor — 對齊既有 `MockClock::new()` 命名一致性。
    pub const fn new() -> Self {
        Self
    }
}

impl FailsafeClock for WallClock {
    fn now_ms(&self) -> u64 {
        // 為什麼用 `unwrap_or(0)`：
        //   `duration_since(UNIX_EPOCH)` 只在「系統時鐘倒退到 1970 之前」失敗，
        //   此情境下 fail-safe 寧可回 0 也不 panic（survival 優先）。
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|d| {
                // u128 -> u64：實務上 2025 ~ 1.7×10^12 ms，距 u64 上限
                // 1.8×10^19 還遠；clamp 保險。
                let ms = d.as_millis();
                if ms > u64::MAX as u128 {
                    u64::MAX
                } else {
                    ms as u64
                }
            })
            .unwrap_or(0)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// T1.1：`now_ms()` 必須回非零值（測試啟動時 system clock 一定 > epoch）。
    #[test]
    fn wall_clock_returns_nonzero_now() {
        let clock = WallClock::new();
        let now = clock.now_ms();
        // 2026-01-01 = 1_767_225_600_000 ms；任何 reasonable system clock 必 > 該值。
        assert!(now > 1_700_000_000_000, "now_ms should be > 2023-11; got {now}");
    }

    /// T1.2：兩次連續呼叫必須單調非遞減（system clock 不會倒退正常運行下）。
    #[test]
    fn wall_clock_monotonic_non_decreasing() {
        let clock = WallClock::new();
        let t1 = clock.now_ms();
        let t2 = clock.now_ms();
        assert!(t2 >= t1, "now_ms should be non-decreasing: t1={t1}, t2={t2}");
    }

    /// T1.3：`WallClock` 必須實作 `Send + Sync`（trait bound 要求）；
    /// 編譯通過即驗證 trait bound 滿足。
    #[test]
    fn wall_clock_is_send_sync() {
        fn assert_send_sync<T: Send + Sync>() {}
        assert_send_sync::<WallClock>();
    }

    /// T1.4：`Default` impl 與 `new()` 等效，皆回零成本實例。
    #[test]
    fn wall_clock_default_equivalent_to_new() {
        let a = WallClock::default();
        let b = WallClock::new();
        // 兩者皆無欄位，現在時間應該幾乎相同（容許 100ms 抖動）。
        let diff = b.now_ms().saturating_sub(a.now_ms());
        assert!(diff < 100, "default/new diff should be tiny: {diff}");
    }
}
