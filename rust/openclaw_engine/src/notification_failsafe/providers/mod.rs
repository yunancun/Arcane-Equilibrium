//! Wave 5 Packet C / C3 — runtime providers 真實實作。
//!
//! 模塊用途：
//!   提供 `notification_failsafe::FailsafeWatcher` trait 的 runtime 注入端：
//!     - `wall_clock::WallClock` — `FailsafeClock` 真實時鐘（SystemTime epoch ms）；
//!     - `position_provider::RestPositionProvider` — `PositionSnapshotProvider`
//!        透過 Bybit V5 REST `/v5/position/list` 拉真實倉位；
//!     - `exchange_stop_sync::BybitExchangeStopSync` — `ExchangeStopSync` wrap
//!        `PositionManager::set_trading_stop`；
//!     - `single_watcher::SharedFailsafeWatcher` — operator Q4.1 拍板 single shared
//!        watcher 的單例封裝（OnceLock + parking_lot::Mutex）。
//!
//! C3 範圍邊界：
//!   - 純 provider 實作 + 單例封裝；
//!   - **不 spawn tokio task**（屬 C4 `tasks.rs::spawn_notification_failsafe_watcher`）；
//!   - **不接 pipeline_ctor / main.rs**（屬 C4）；
//!   - **不繞 PositionManager**（exchange sync 全走既有 trait + REST 路徑）。
//!
//! 不變量（per CLAUDE.md §二 + §四 + task spec §Phase 1-4）：
//!   - 不 panic / 不 unwrap；任何 fail-soft 路徑回 empty Vec / fail-soft error；
//!   - REST timeout 5s 硬限；
//!   - 單例語義：`SharedFailsafeWatcher::instance()` 雙呼回同一 `Arc`；
//!   - 鎖跨 await 禁區：`SharedFailsafeWatcher::check_timer` 三段拆分（lock → drop
//!     → await → re-lock）per spec §4.7。
//!
//! ref: docs/execution_plan/specs/2026-05-28--packet_c_3way_dispatcher_wire_spec.md §4

pub mod exchange_stop_sync;
pub mod position_provider;
pub mod single_watcher;
pub mod wall_clock;

// 為什麼 re-export：方便 C4 wire 時 `use notification_failsafe::providers::{...}`
// 一條 import 即可拿到所有真實 impl。
pub use exchange_stop_sync::BybitExchangeStopSync;
pub use position_provider::RestPositionProvider;
pub use single_watcher::SharedFailsafeWatcher;
pub use wall_clock::WallClock;
