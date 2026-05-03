//! Replay subsystem — REF-20 Paper Replay Lab Rust surface.
//!
//! Replay 子系統 — REF-20 Paper Replay Lab Rust 平面。
//!
//! MODULE_NOTE (EN): Wave 1 scaffold export. This module currently re-exports
//!   only the `ReplayProfile` enum spec (R20-P0-T3). Wave 3 R20-P2b-S7/S8/S9/S10
//!   will add forbidden-path guards, Mac policy guard, and runtime
//!   profile enforcement. Wave 4 R20-P2b-T1/T2/T3 will add the isolated
//!   process wrapper, baseline-vs-candidate comparison, and canary/diagnostic
//!   artifact registration.
//!
//!   Wave 1 scope (this commit):
//!     - `profile` — `ReplayProfile` enum spec (no IMPL).
//!
//!   Wave 3 scope (NOT yet wired):
//!     - `forbidden_guard` — startup + runtime fail-closed guard (R20-P2b-S8).
//!     - `mac_policy_guard` — `OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA` enforcer
//!       (R20-P2b-S9).
//!
//! MODULE_NOTE (中): Wave 1 scaffold 匯出。此 module 目前僅 re-export
//!   `ReplayProfile` enum 規格（R20-P0-T3）。Wave 3 R20-P2b-S7/S8/S9/S10
//!   會加 forbidden-path guard、Mac policy guard 與 runtime profile 強制。
//!   Wave 4 R20-P2b-T1/T2/T3 會加 isolated process wrapper、baseline-vs-candidate
//!   比較與 canary/diagnostic artifact 註冊。
//!
//! SPEC: REF-20 V3 §3 G7/G8 + §6.1/§6.2 + workplan R20-P0-T2/T3/T9
//!
//! Wave 2 P2a-S2 update (this commit):
//!   - Added `manifest_signer` — server-side HMAC-SHA256 sign + verify
//!     module with 4 fail-mode enum + KeyArchive trait + InMemoryKeyArchive
//!     test stub. SQL-backed archive lands Wave 3 R20-P2a-S4.
//!
//! Wave 2 P2a-S2 更新（本 commit）：
//!   - 加 `manifest_signer` — server-side HMAC-SHA256 簽名+驗證模組，
//!     含 4 fail-mode enum + KeyArchive trait + InMemoryKeyArchive 測試 stub。
//!     SQL 版 archive 於 Wave 3 R20-P2a-S4 落地。

pub mod manifest_signer;
pub mod profile;
