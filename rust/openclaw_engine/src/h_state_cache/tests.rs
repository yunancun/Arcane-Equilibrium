//! Unit tests for [`super::HStateCache`] + env-gate behaviour.
//! 這裡覆蓋 cache 純函數行為（snapshot store / staleness / build_status /
//! env-gate）。Poller-side tests（fetcher 注入 + invalidation 合併）住在
//! `poller.rs` 的 `mod tests`，types-side tests（forward-compat / null
//! handling）住在 `types.rs` 的 `mod tests` — 三檔覆蓋面互補不重複。
//!
//! MODULE_NOTE (EN): Per PA design plan §10.1 step 5 the Sub-task A
//!   acceptance bar is "12+ unit tests". This file owns the cache /
//!   env-gate slice; together with `types.rs` (3 tests) and `poller.rs`
//!   (4 tests) Sub-task A ships >= 14 tests.
//! MODULE_NOTE (中)：依 PA design plan §10.1 step 5 驗收線是 12+ unit
//!   tests。本檔負責 cache / env-gate 切片，與 `types.rs`（3 tests）+
//!   `poller.rs`（4 tests）合計 ≥ 14 tests，達標。

use super::*;

/// Fresh cache reports `is_stale() == true` (no successful poll yet).
/// 全新 cache 應回 `is_stale() == true`（尚無成功 poll）。
#[test]
fn fresh_cache_is_stale() {
    let cache = HStateCache::new();
    assert!(cache.is_stale());
    assert_eq!(cache.fetched_at_ms(), 0);
    assert_eq!(cache.snapshot().version, 0);
}

/// After `store_snapshot` with current `now`, the cache is fresh
/// (`is_stale() == false` and staleness < threshold).
/// 用當下 `now` 寫 snapshot 後，cache 應 fresh。
#[test]
fn store_snapshot_marks_fresh() {
    let cache = HStateCache::new();
    let now = unix_now_ms();
    cache.store_snapshot(
        HStateSnapshot {
            version: 1,
            ..Default::default()
        },
        now,
    );
    assert!(!cache.is_stale());
    assert!(cache.staleness_ms() < STALENESS_THRESHOLD_MS);
    assert_eq!(cache.snapshot().version, 1);
}

/// A snapshot stored with timestamp older than 30s flips `is_stale()`.
/// 用 30s 前的時戳寫 snapshot，`is_stale()` 應翻 true。
#[test]
fn snapshot_older_than_threshold_marks_stale_but_returns_data() {
    let cache = HStateCache::new();
    // 60s ago → far past the 30s threshold.
    let old_ts = unix_now_ms() - 60_000;
    cache.store_snapshot(
        HStateSnapshot {
            version: 99,
            ..Default::default()
        },
        old_ts,
    );
    // Stale flag flips, but data is still readable (advisory, not withheld).
    // stale flag 翻 true，但資料仍可讀（純 advisory，不扣留）。
    assert!(cache.is_stale());
    assert!(cache.staleness_ms() > STALENESS_THRESHOLD_MS);
    assert_eq!(cache.snapshot().version, 99);
}

/// Build a status payload with gateway_enabled=true reports counters.
/// 建構 gateway_enabled=true 的 status payload，counters 應正確。
#[test]
fn build_status_reports_counters_and_enabled_flag() {
    let cache = HStateCache::new();
    cache.bump_attempts();
    cache.bump_attempts();
    cache.bump_failures();
    cache.store_snapshot(
        HStateSnapshot {
            version: 5,
            ..Default::default()
        },
        unix_now_ms(),
    );

    let status = cache.build_status(true);
    assert_eq!(status.version, 5);
    assert!(status.gateway_enabled);
    // 2 manual bumps + 1 from store_snapshot's success counter
    // 2 次手動 bump + store_snapshot 內的 1 次 success
    assert_eq!(status.poll_attempts, 2);
    assert_eq!(status.poll_successes, 1);
    assert_eq!(status.poll_failures, 1);
    assert!(!status.is_stale);
}

/// Build status with gateway_enabled=false flips the flag.
/// gateway_enabled=false 應翻 flag。
#[test]
fn build_status_respects_gateway_disabled_flag() {
    let cache = HStateCache::new();
    let status = cache.build_status(false);
    assert!(!status.gateway_enabled);
}

/// `is_gateway_enabled()` is `false` by default (DEFAULT-OFF).
/// 預設 `is_gateway_enabled()` 為 false（DEFAULT-OFF）。
///
/// Note: this test cannot reliably set/unset env in parallel with other
/// env-touching tests (cargo runs tests in parallel); we check the
/// current process state. Production env=0 path is the documented default
/// — the harness in `main_boot_tasks` reads this same fn.
/// 注意：此測試無法與其他改 env 的測試並行 set/unset；只驗當前 process
/// 狀態。Production env=0 路徑為文件預設 — `main_boot_tasks` 讀此 fn。
#[test]
fn gateway_default_off_unless_env_strict_one() {
    // Snapshot current state so we don't break parallel tests.
    // 快照當前狀態避免影響並行測試。
    let prev = std::env::var(ENV_GATEWAY_FLAG).ok();

    // Strict comparison: "true" / "yes" / "0" / unset → false.
    // 嚴格比對：上述值皆 false。
    // SAFETY: tests are explicitly serialized for env mutation by sharing
    // a single mutex below. We restore prev on every branch.
    // SAFETY：env 改動透過下方共用 mutex 序列化；每條分支都會 restore prev。
    let _guard = ENV_TEST_LOCK.lock().expect("env test lock");

    std::env::remove_var(ENV_GATEWAY_FLAG);
    assert!(!is_gateway_enabled(), "unset env must be DEFAULT-OFF");

    std::env::set_var(ENV_GATEWAY_FLAG, "0");
    assert!(!is_gateway_enabled(), "env=0 must be DEFAULT-OFF");

    std::env::set_var(ENV_GATEWAY_FLAG, "true");
    assert!(
        !is_gateway_enabled(),
        "env=true must NOT enable (strict comparison)"
    );

    std::env::set_var(ENV_GATEWAY_FLAG, "1");
    assert!(is_gateway_enabled(), "env=1 must enable");

    // Restore / 還原
    match prev {
        Some(v) => std::env::set_var(ENV_GATEWAY_FLAG, v),
        None => std::env::remove_var(ENV_GATEWAY_FLAG),
    }
}

/// Cache supports concurrent reads + a single writer. Spawn 8 read tasks
/// hammering snapshot() while the main thread bumps counters; nothing
/// should panic and the final state should be consistent.
/// Cache 支援並行 read + 單 writer。spawn 8 個 read 任務同時呼 snapshot()
/// 同時 main thread bump counters；不該 panic 且最終狀態一致。
#[test]
fn concurrent_reads_with_writer_do_not_panic() {
    use std::sync::Arc;
    let cache = Arc::new(HStateCache::new());
    cache.store_snapshot(
        HStateSnapshot {
            version: 1,
            ..Default::default()
        },
        unix_now_ms(),
    );

    let mut handles = Vec::new();
    for _ in 0..8 {
        let c = Arc::clone(&cache);
        handles.push(std::thread::spawn(move || {
            for _ in 0..200 {
                let s = c.snapshot();
                assert!(s.version >= 1, "monotone version");
                let _ = c.staleness_ms();
            }
        }));
    }
    for i in 2u64..50 {
        cache.store_snapshot(
            HStateSnapshot {
                version: i,
                ..Default::default()
            },
            unix_now_ms(),
        );
    }
    for h in handles {
        h.join().expect("reader thread panicked");
    }
    let final_v = cache.snapshot().version;
    assert!(final_v >= 1 && final_v < 100);
}

/// Default-constructed cache reports zeros + stale.
/// 預設 cache 應全 0 + stale。
#[test]
fn default_cache_state() {
    let cache = HStateCache::default();
    let status = cache.build_status(false);
    assert_eq!(status.version, 0);
    assert_eq!(status.poll_attempts, 0);
    assert_eq!(status.poll_successes, 0);
    assert_eq!(status.poll_failures, 0);
    assert!(status.is_stale);
    assert!(!status.gateway_enabled);
}

// Process-wide mutex for env-mutating tests so parallel `cargo test` runs
// don't race on `std::env::set_var`. Test-only.
// env-mutating 測試共用的 process-wide mutex，避免並行 `cargo test` 競爭。
// 僅測試用。
static ENV_TEST_LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());
