//! Replay subsystem — REF-20 Paper Replay Lab Rust surface.
//!
//! Replay 子系統 — REF-20 Paper Replay Lab Rust 平面。
//!
//! MODULE_NOTE (EN): Wave 3 R20-P2b-S7 IMPL re-export. After this commit
//!   the `replay` subsystem exposes:
//!     - `profile::ReplayProfile` — enum with Wave 3 runtime gating method
//!         IMPL (`requires_lease`, `allow_ipc_server`,
//!         `allow_exchange_dispatch`, `allow_db_writer_channels`,
//!         `fail_closed_assert_isolated`).
//!     - `profile::ReplayIsolationError` — narrow error type carried by
//!         `fail_closed_assert_isolated()`. Re-exported at the subsystem
//!         level so the binary entry (`bin/replay_runner.rs`) and future
//!         callers can pattern-match without reaching into the inner
//!         `profile::` path.
//!     - `manifest_signer::*` — Wave 2 P2a-S2 HMAC-SHA256 sign + verify
//!         module (4 fail-mode enum + KeyArchive trait + InMemoryKeyArchive
//!         test stub).
//!
//!   What's still ahead (NOT yet wired):
//!     - Wave 3 R20-P2b-S8 — `forbidden_guard` (startup + runtime
//!         fail-closed guard covering the FULL V3 §6.2 list, not just the
//!         profile assert).
//!     - Wave 3 R20-P2b-S9 — `mac_policy_guard`
//!         (`OPENCLAW_REPLAY_MAC_NO_PRIVATE` enforcer; renamed from
//!         `OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA` per Wave 2 dispatch §2 #1).
//!     - Wave 4 R20-P2b-T1/T2/T3 — isolated process wrapper,
//!         baseline-vs-candidate comparison, canary/diagnostic artifact
//!         registration.
//!
//! MODULE_NOTE (中): Wave 3 R20-P2b-S7 IMPL re-export。本 commit 後 `replay`
//!   子系統暴露：
//!     - `profile::ReplayProfile` — 帶 Wave 3 runtime gating method IMPL
//!         （`requires_lease`、`allow_ipc_server`、`allow_exchange_dispatch`、
//!         `allow_db_writer_channels`、`fail_closed_assert_isolated`）。
//!     - `profile::ReplayIsolationError` — `fail_closed_assert_isolated()`
//!         攜帶的窄範圍 error 型別。在 subsystem 層 re-export 讓 binary
//!         entry（`bin/replay_runner.rs`）與未來 caller 可 pattern-match，
//!         不必伸進內部 `profile::` 路徑。
//!     - `manifest_signer::*` — Wave 2 P2a-S2 HMAC-SHA256 簽名+驗證模組
//!         （4 fail-mode enum + KeyArchive trait + InMemoryKeyArchive
//!         test stub）。
//!
//!   尚未接線：
//!     - Wave 3 R20-P2b-S8 — `forbidden_guard`（startup + runtime
//!         fail-closed guard，覆蓋完整 V3 §6.2 清單，非僅 profile assert）。
//!     - Wave 3 R20-P2b-S9 — `mac_policy_guard`
//!         （`OPENCLAW_REPLAY_MAC_NO_PRIVATE` enforcer；per Wave 2 dispatch
//!         §2 #1 由 `OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA` 改名）。
//!     - Wave 4 R20-P2b-T1/T2/T3 — isolated process wrapper、
//!         baseline-vs-candidate 比較、canary/diagnostic artifact 註冊。
//!
//! SPEC: REF-20 V3 §3 G7/G8 + §6.1/§6.2 + workplan R20-P0-T2/T3/T9 +
//!       R20-P2a-S2 (manifest signer) + R20-P2b-S7 (this commit).

pub mod manifest_signer;
pub mod profile;

// Subsystem-level re-export: `ReplayIsolationError` is the public failure
// type carried by `ReplayProfile::fail_closed_assert_isolated()`. Re-exporting
// at the `crate::replay::*` level lets `bin/replay_runner.rs` and future
// callers `match` on it without referencing `profile::` directly.
//
// Subsystem 層 re-export：`ReplayIsolationError` 是
// `ReplayProfile::fail_closed_assert_isolated()` 攜帶的公開失敗型別。在
// `crate::replay::*` 層 re-export，讓 `bin/replay_runner.rs` 與未來 caller
// 可直接 `match`，不必引用 `profile::` 內部路徑。
pub use profile::ReplayIsolationError;
