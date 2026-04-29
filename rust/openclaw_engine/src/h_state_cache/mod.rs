//! H State Cache — Rust端對 Python H1-H5 + 5-Agent state 的本地快照。
//! 對應 PA design plan §4.1 / §6.1（commit `7564d07`）。
//!
//! MODULE_NOTE (EN): Mirrors the G3-03 ExecutorConfigCache pattern but
//!   reversed flow direction:
//!     - G3-03: Rust SSOT → Python pulls
//!     - G3-08: Python SSOT → Rust pulls (this module)
//!
//!   Cache layout:
//!     - Single `parking_lot::RwLock<HStateSnapshot>` holds the latest
//!       successfully-polled snapshot (small, ~50 fields aggregated).
//!     - `AtomicI64 fetched_at_ms` tracks last-success timestamp for
//!       staleness checks (lock-free read on hot path).
//!     - `AtomicU64 poll_{attempts,successes,failures}` for healthcheck
//!       observability (passive_wait_healthcheck `[20]`).
//!
//!   Hot-path read path:
//!     1. Atomic read `fetched_at_ms` for staleness flag (lock-free).
//!     2. RwLock read snapshot, clone H<X> sub-struct, drop guard.
//!     3. Caller queries needed field on the clone.
//!     Estimated p99 < 1μs (RwLock read uncontended + small struct clone).
//!
//!   Crash resilience:
//!     - Python crash → poll fails → snapshot stays at last-good value,
//!       `is_stale()` flips true at 30s. Rust hot path can still read,
//!       must treat data as advisory only.
//!     - Rust startup before first poll → snapshot is `default()` with
//!       `version=0`, `is_stale()` returns `true` (caller should fall
//!       back to fail-closed defaults).
//!
//!   DEFAULT-OFF env-gate:
//!     - `main_boot_tasks::spawn_h_state_poller_if_enabled` checks
//!       `OPENCLAW_H_STATE_GATEWAY == "1"` BEFORE building the cache.
//!     - When env=0: cache never allocated, slot stays `None`, IPC
//!       handler returns `gateway_disabled` (zero overhead path).
//!     - When env=1: cache + poller built, slot late-injected.
//!
//! MODULE_NOTE (中)：鏡射 G3-03 ExecutorConfigCache pattern，但流向相反：
//!     - G3-03：Rust 為 SSOT → Python pull
//!     - G3-08：Python 為 SSOT → Rust pull（本模組）
//!
//!   Cache 佈局：
//!     - 單一 `parking_lot::RwLock<HStateSnapshot>` 持最新成功 poll 的
//!       snapshot（小型，~50 欄位聚合）。
//!     - `AtomicI64 fetched_at_ms` 記最後成功時間，hot-path 用
//!       lock-free read 判 staleness。
//!     - `AtomicU64 poll_{attempts,successes,failures}` 給
//!       passive_wait_healthcheck `[20]` 觀測。
//!
//!   Hot-path read：
//!     1. Atomic 讀 `fetched_at_ms`（lock-free）。
//!     2. RwLock read snapshot → clone H<X> 子 struct → drop guard。
//!     3. Caller 在 clone 上查所需欄位。
//!     估計 p99 < 1μs（無爭用 RwLock read + 小 struct clone）。
//!
//!   Crash 韌性：
//!     - Python crash → poll 失敗 → snapshot 保留 last-good 值，30s 後
//!       `is_stale()` 為 true。Rust hot-path 仍可讀，但應視為純 advisory。
//!     - Rust 啟動到首次 poll 之間 → snapshot 為 `default()` 且
//!       `version=0`，`is_stale()` 回 `true`（caller 應 fail-closed）。
//!
//!   DEFAULT-OFF env-gate：
//!     - `main_boot_tasks::spawn_h_state_poller_if_enabled` 在建 cache
//!       前先檢 `OPENCLAW_H_STATE_GATEWAY == "1"`。
//!     - env=0：cache 永不分配，slot 保持 `None`，IPC handler 回
//!       `gateway_disabled`（zero overhead 路徑）。
//!     - env=1：cache + poller 建立，slot late-inject。

pub mod poller;
pub mod types;

#[cfg(test)]
mod tests;

pub use types::{
    AgentState, H1Stats, H2BudgetState, H3RouteStats, H4ValidationStats, H5CostStats,
    HStateSnapshot, HStateStatus,
};

use parking_lot::RwLock;
use std::sync::atomic::{AtomicI64, AtomicU64, Ordering};
use std::sync::Arc;

/// Env var that gates the H State Gateway (PA §4.5 / §9 Phase 1).
/// 控管 H State Gateway 的環境變數（PA §4.5 / §9 Phase 1）。
///
/// Strict-equality comparison with `"1"` — any other value (including
/// `"true"` / `"yes"` / unset) keeps the gateway off (DEFAULT-OFF).
/// 與 `"1"` 嚴格相等比對 — 其他值（含 `"true"` / `"yes"` / 未設）
/// 一律視為關閉（DEFAULT-OFF）。
pub const ENV_GATEWAY_FLAG: &str = "OPENCLAW_H_STATE_GATEWAY";

/// Staleness threshold — snapshots older than this are flagged advisory-only.
/// 過期門檻 — snapshot 老於此值即視為 advisory only。
///
/// 30s = 3× the default poll interval (10s). Below this we trust the
/// snapshot is recent enough; above this we mark it stale so callers
/// (GUI healthcheck / hot-path observability) can react. Hot-path
/// queries still get the data — it's never withheld — they're just
/// informed of staleness via [`HStateCache::is_stale`].
/// 30s = 3× 預設 poll interval（10s）。低於即視為足夠新；超過則標 stale，
/// caller（GUI healthcheck / hot-path observability）可自行反應。
/// Hot-path 永遠拿得到資料 — 不扣留 — 只是透過 [`HStateCache::is_stale`]
/// 知會 staleness。
pub const STALENESS_THRESHOLD_MS: i64 = 30_000;

/// In-memory cache of Python H1-H5 + 5-Agent state, polled every N seconds
/// via IPC `query_h_state_full`. See module docstring for design.
/// Python H1-H5 + 5-Agent state 的記憶體快照，透過 IPC 每 N 秒 poll。
pub struct HStateCache {
    /// Latest snapshot. RwLock allows concurrent reads, exclusive writes.
    /// 最新快照。RwLock 允許並行 read、獨占 write。
    snapshot: RwLock<HStateSnapshot>,

    /// Unix ms of last successful poll. Hot-path reads this lock-free for
    /// staleness check before deciding whether to read snapshot.
    /// 最後成功 poll 的 unix ms。Hot-path lock-free 讀此值判 staleness。
    fetched_at_ms: AtomicI64,

    /// Number of poll attempts (successes + failures).
    /// poll 次數（成功 + 失敗）。
    poll_attempts: AtomicU64,
    /// Number of successful polls (snapshot updated).
    /// 成功 poll 次數（snapshot 已更新）。
    poll_successes: AtomicU64,
    /// Number of failed polls (IPC error / serde error / Python down).
    /// 失敗 poll 次數（IPC 錯誤 / serde 錯誤 / Python 不在）。
    poll_failures: AtomicU64,
}

impl HStateCache {
    /// Build a fresh empty cache. Snapshot starts at `default()` with
    /// version=0, fetched_at_ms=0 — `is_stale()` will return `true` until
    /// the first successful poll.
    /// 建立空白 cache。Snapshot 為 `default()`、version=0，首次成功 poll
    /// 之前 `is_stale()` 都回 `true`。
    pub fn new() -> Self {
        Self {
            snapshot: RwLock::new(HStateSnapshot::default()),
            fetched_at_ms: AtomicI64::new(0),
            poll_attempts: AtomicU64::new(0),
            poll_successes: AtomicU64::new(0),
            poll_failures: AtomicU64::new(0),
        }
    }

    /// Build a cache wrapped in `Arc` ready for poller + IPC handler clones.
    /// 建立包在 `Arc` 內的 cache，給 poller 與 IPC handler 共享。
    pub fn new_arc() -> Arc<Self> {
        Arc::new(Self::new())
    }

    /// Replace snapshot atomically and bump fetched_at_ms + success counter.
    /// Used by poller after successful IPC parse.
    /// 原子替換 snapshot 並 bump fetched_at_ms + 成功計數。供 poller 用。
    pub fn store_snapshot(&self, new_snap: HStateSnapshot, fetched_at_ms: i64) {
        // Order: bump counter, write snapshot, write timestamp.
        // 順序：bump 計數 → 寫 snapshot → 寫時戳。
        // Reader sees stale fetched_at_ms but fresh snapshot in worst case
        // (false-stale flag) — never the reverse (no torn-data risk).
        // 最壞情況 reader 看到舊 fetched_at_ms 配新 snapshot（誤判 stale），
        // 反向不會發生（無 torn-data 風險）。
        self.poll_successes.fetch_add(1, Ordering::Relaxed);
        *self.snapshot.write() = new_snap;
        self.fetched_at_ms.store(fetched_at_ms, Ordering::Release);
    }

    /// Bump attempts counter (called BEFORE poll body, regardless of outcome).
    /// Bump 嘗試計數（poll 前呼叫，不論成敗）。
    pub fn bump_attempts(&self) {
        self.poll_attempts.fetch_add(1, Ordering::Relaxed);
    }

    /// Bump failure counter (called when poll body errored — IPC fail /
    /// serde fail / timeout). Snapshot stays at last-good value.
    /// Bump 失敗計數（poll body 出錯時 — IPC 失敗 / serde 失敗 / timeout）。
    /// Snapshot 維持 last-good 值。
    pub fn bump_failures(&self) {
        self.poll_failures.fetch_add(1, Ordering::Relaxed);
    }

    /// Read a clone of the current snapshot. Holds the read lock briefly.
    /// 讀當前 snapshot 的 clone。短暫持 read lock。
    pub fn snapshot(&self) -> HStateSnapshot {
        self.snapshot.read().clone()
    }

    /// Lock-free read of the last-success timestamp.
    /// Lock-free 讀最後成功時間。
    pub fn fetched_at_ms(&self) -> i64 {
        self.fetched_at_ms.load(Ordering::Acquire)
    }

    /// Milliseconds since last successful poll. Returns large positive value
    /// if no poll has succeeded yet (since fetched_at_ms is 0 → now).
    /// 最後成功 poll 起的毫秒數。從未成功則回大正值（fetched_at_ms=0 → now）。
    pub fn staleness_ms(&self) -> i64 {
        let now = unix_now_ms();
        let last = self.fetched_at_ms();
        if last == 0 {
            // Never polled successfully; report current epoch as staleness
            // proxy. Caller's `is_stale()` will be `true`.
            // 從未成功 poll；以當前 epoch 作 staleness 代理，
            // caller 的 `is_stale()` 會為 true。
            now
        } else {
            (now - last).max(0)
        }
    }

    /// `true` when staleness exceeds [`STALENESS_THRESHOLD_MS`] (30s).
    /// 過期超過 [`STALENESS_THRESHOLD_MS`]（30s）時為 `true`。
    pub fn is_stale(&self) -> bool {
        self.staleness_ms() > STALENESS_THRESHOLD_MS
    }

    /// Build a [`HStateStatus`] payload for `get_h_state_status` IPC handler.
    /// 為 `get_h_state_status` IPC handler 建構 [`HStateStatus`] payload。
    pub fn build_status(&self, gateway_enabled: bool) -> HStateStatus {
        let snap_version = self.snapshot.read().version;
        HStateStatus {
            version: snap_version,
            staleness_ms: self.staleness_ms(),
            is_stale: self.is_stale(),
            poll_attempts: self.poll_attempts.load(Ordering::Relaxed),
            poll_successes: self.poll_successes.load(Ordering::Relaxed),
            poll_failures: self.poll_failures.load(Ordering::Relaxed),
            gateway_enabled,
        }
    }
}

impl Default for HStateCache {
    fn default() -> Self {
        Self::new()
    }
}

/// Unix epoch in milliseconds — utility for poller + cache.
/// Unix 紀元毫秒 — poller 與 cache 共用工具。
pub(crate) fn unix_now_ms() -> i64 {
    use std::time::{SystemTime, UNIX_EPOCH};
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis() as i64)
        .unwrap_or(0)
}

/// Check whether the H State Gateway env-gate is enabled.
/// Strict comparison with `"1"` — any other value keeps it off.
/// 檢查 H State Gateway env-gate 是否啟用。與 `"1"` 嚴格比較 — 其他值皆視為關。
pub fn is_gateway_enabled() -> bool {
    std::env::var(ENV_GATEWAY_FLAG).as_deref() == Ok("1")
}
