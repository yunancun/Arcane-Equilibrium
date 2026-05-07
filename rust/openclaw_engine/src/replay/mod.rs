//! Replay subsystem — REF-20 Paper Replay Lab Rust surface.
//!
//! Replay 子系統 — REF-20 Paper Replay Lab Rust 平面。
//!
//! MODULE_NOTE (EN): Wave 3 R20-P2b-S7/S8/S9 IMPL re-export. After this commit
//!   the `replay` subsystem exposes:
//!     - `profile::ReplayProfile` — enum with Wave 3 P2b-S7 runtime gating
//!         method IMPL (`requires_lease`, `allow_ipc_server`,
//!         `allow_exchange_dispatch`, `allow_db_writer_channels`,
//!         `fail_closed_assert_isolated`).
//!     - `profile::ReplayIsolationError` — narrow error type carried by
//!         `fail_closed_assert_isolated()`. Re-exported at the subsystem
//!         level so the binary entry (`bin/replay_runner.rs`) and future
//!         callers can pattern-match without reaching into the inner
//!         `profile::` path.
//!     - `forbidden_guard::*` — Wave 3 P2b-S8 fail-closed enforcement covering
//!         the FULL V3 §6.2 forbidden-path list. `enforce_at_startup()` is
//!         called by the binary entry; `enforce_at_runtime(action)` is the
//!         signature Wave 4 R20-P2b-T1 wrapper will plug into. The 7-variant
//!         `ForbiddenPathError` is re-exported.
//!     - `mac_policy_guard::*` — Wave 3 P2b-S9 V3 §6.3 Mac fail-closed gate.
//!         Reads `OPENCLAW_REPLAY_MAC_NO_PRIVATE=1` (renamed per Wave 2
//!         dispatch §2 #1 from `OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA`). The
//!         3-variant `MacPolicyError` is re-exported.
//!     - `manifest_signer::*` — Wave 2 P2a-S2 HMAC-SHA256 sign + verify
//!         module (4 fail-mode enum + KeyArchive trait + InMemoryKeyArchive
//!         test stub).
//!
//!   Three guards composed at the binary entry (per
//!   `bin/replay_runner.rs::main`):
//!     1. `ReplayProfile::Isolated::fail_closed_assert_isolated()`  (S7)
//!     2. `forbidden_guard::enforce_at_startup()`                   (S8)
//!     3. `mac_policy_guard::enforce(profile)`                      (S9)
//!     Any returned `Err` is `.expect(...)`-ed by the binary so the run
//!     aborts before replay logic begins (V3 §12 #10 + #12 binding).
//!
//!   What's still ahead (NOT yet wired):
//!     - Wave 4 R20-P2b-T1 — isolated process wrapper that mediates between
//!         the replay binary and (sandboxed) versions of `intent_processor::router`,
//!         `ipc_server::dispatch`, `bybit_rest_client::place_order`, etc.
//!         That wrapper is where `forbidden_guard::enforce_at_runtime` plugs
//!         into hard-coded interception branches per `action` label.
//!     - Wave 4 R20-P2b-T2 — baseline-vs-candidate comparison route + actual
//!         replay tick loop (manifest signer verify-first-then-hash via
//!         `crate::replay::manifest_signer`, fixture loader, in-memory
//!         TickPipeline + IntentProcessor under Isolated profile).
//!     - Wave 4 R20-P2b-T3 — canary/diagnostic artifact registration.
//!
//! MODULE_NOTE (中): Wave 3 R20-P2b-S7/S8/S9 IMPL re-export。本 commit 後
//!   `replay` 子系統暴露：
//!     - `profile::ReplayProfile` — 帶 Wave 3 P2b-S7 runtime gating method
//!         IMPL（`requires_lease`、`allow_ipc_server`、`allow_exchange_dispatch`、
//!         `allow_db_writer_channels`、`fail_closed_assert_isolated`）。
//!     - `profile::ReplayIsolationError` — `fail_closed_assert_isolated()`
//!         攜帶的窄範圍 error 型別。在 subsystem 層 re-export，使 binary
//!         entry（`bin/replay_runner.rs`）與未來 caller 可 pattern-match，
//!         不必伸進內部 `profile::` 路徑。
//!     - `forbidden_guard::*` — Wave 3 P2b-S8 fail-closed enforcement，覆蓋
//!         完整 V3 §6.2 forbidden-path 清單。`enforce_at_startup()` 由 binary
//!         entry 呼叫；`enforce_at_runtime(action)` 為 Wave 4 R20-P2b-T1
//!         wrapper 接入點之 signature。7-variant `ForbiddenPathError`
//!         re-export。
//!     - `mac_policy_guard::*` — Wave 3 P2b-S9 V3 §6.3 Mac fail-closed gate。
//!         讀取 `OPENCLAW_REPLAY_MAC_NO_PRIVATE=1`（依 Wave 2 dispatch §2 #1
//!         由 `OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA` 改名）。3-variant
//!         `MacPolicyError` re-export。
//!     - `manifest_signer::*` — Wave 2 P2a-S2 HMAC-SHA256 簽名+驗證模組
//!         （4 fail-mode enum + KeyArchive trait + InMemoryKeyArchive
//!         test stub）。
//!
//!   三個 guard 在 binary entry 組合（依 `bin/replay_runner.rs::main`）：
//!     1. `ReplayProfile::Isolated::fail_closed_assert_isolated()`  （S7）
//!     2. `forbidden_guard::enforce_at_startup()`                   （S8）
//!     3. `mac_policy_guard::enforce(profile)`                      （S9）
//!     任一 `Err` 由 binary `.expect(...)` 觸發 panic，使 run 在 replay 邏輯
//!     開始前 abort（V3 §12 #10 + #12 binding）。
//!
//!   尚未接線：
//!     - Wave 4 R20-P2b-T1 — isolated process wrapper，介於 replay binary 與
//!         （sandboxed 版的）`intent_processor::router`、`ipc_server::dispatch`、
//!         `bybit_rest_client::place_order` 等之間。
//!         `forbidden_guard::enforce_at_runtime` 在該 wrapper 接入 per-action
//!         hard-coded 攔截分支。
//!     - Wave 4 R20-P2b-T2 — baseline-vs-candidate 比較 route + 實際 replay
//!         tick loop（透過 `crate::replay::manifest_signer` 做 manifest
//!         verify-first-then-hash、fixture loader、Isolated profile 下的
//!         in-memory TickPipeline + IntentProcessor）。
//!     - Wave 4 R20-P2b-T3 — canary/diagnostic artifact 註冊。
//!
//! Wave 4 R20-P2b-T1 IMPL re-export additions:
//!   - `cli` — hand-rolled CLI parser (replay binary entry).
//!   - `fixture_loader` — S2/S3 fixture file → `MarketEvent` vector.
//!   - `runner` — `IsolatedPipeline` orchestrator; emits `ReplayResult`.
//!   - `report_writer` — `replay_report.json` + summary persister.
//!
//! Wave 4 R20-P2b-T1 IMPL re-export 新增：
//!   - `cli` — 手寫 CLI 解析器（replay binary entry）。
//!   - `fixture_loader` — S2/S3 fixture file → `MarketEvent` vector。
//!   - `runner` — `IsolatedPipeline` 總指揮；發出 `ReplayResult`。
//!   - `report_writer` — `replay_report.json` + summary 持久化器。
//!
//! SPEC: REF-20 V3 §3 G7/G8 + §6.1/§6.2/§6.3 + workplan R20-P0-T2/T3/T9 +
//!       R20-P2a-S2 (manifest signer) + R20-P2b-S7 (profile cfg gate) +
//!       R20-P2b-S8 (forbidden_guard, this commit) +
//!       R20-P2b-S9 (mac_policy_guard, this commit) +
//!       R20-P2b-T1 (cli + fixture_loader + runner + report_writer, Wave 4).

pub mod apply_fill;
// Sprint C R6 W3 R6-T4：校準標籤產出器（純 Rust 函數模組）。
pub mod calibration_label;
pub mod cli;
pub mod context_builder;
pub mod fixture_loader;
pub mod forbidden_guard;
pub mod mac_policy_guard;
pub mod manifest_signer;
pub mod profile;
pub mod report_writer;
pub mod scanner_timeline;
// Sprint B2 R5-T1 / R5-T2: replay-pure adapters reusing live `Strategy` trait
// + 6-of-8 Gate risk pipeline reproduction. Both modules sit under the
// existing `replay::*` re-export pattern; R5-T3 `runner::IsolatedPipeline`
// wire-up will compose them.
// Sprint B2 R5-T1 / R5-T2：replay-pure adapter，復用 live `Strategy` trait
// 與 8-Gate 中復刻的 6 個風控 gate。兩 module 沿用既有 `replay::*` re-export
// 模式；R5-T3 `runner::IsolatedPipeline` 接線會將兩者組合。
pub mod risk_adapter;
pub mod runner;
pub mod strategy_adapter;

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

// Subsystem-level re-export: `ForbiddenPathError` (Wave 3 P2b-S8) is the
// public failure type carried by `forbidden_guard::enforce_at_startup()` and
// `enforce_at_runtime()`. Re-exporting at `crate::replay::*` mirrors the
// `ReplayIsolationError` pattern so callers can pattern-match without
// reaching into `forbidden_guard::` internals.
//
// Subsystem 層 re-export：`ForbiddenPathError`（Wave 3 P2b-S8）是
// `forbidden_guard::enforce_at_startup()` 與 `enforce_at_runtime()` 攜帶的
// 公開失敗型別。在 `crate::replay::*` re-export 對齊 `ReplayIsolationError`
// 模式，使 caller 不必伸進 `forbidden_guard::` 內部即可 pattern-match。
pub use forbidden_guard::ForbiddenPathError;

// Subsystem-level re-export: `MacPolicyError` (Wave 3 P2b-S9) is the public
// failure type carried by `mac_policy_guard::enforce()`. Re-exporting at
// `crate::replay::*` keeps the three Wave 3 guards' error types accessible
// at the same module layer for binary entry + acceptance test imports.
//
// Subsystem 層 re-export：`MacPolicyError`（Wave 3 P2b-S9）是
// `mac_policy_guard::enforce()` 攜帶的公開失敗型別。在 `crate::replay::*`
// re-export，使三個 Wave 3 guard 的 error 型別於同一 module 層可取得，
// 供 binary entry 與 acceptance test import。
pub use mac_policy_guard::MacPolicyError;

// Wave 4 R20-P2b-T1 re-exports — orchestrator / CLI / fixture / report
// types accessible at `crate::replay::*` so the binary entry and integration
// tests can pattern-match without descending into per-module paths.
//
// Wave 4 R20-P2b-T1 re-export — orchestrator / CLI / fixture / report
// 型別於 `crate::replay::*` 可取得，使 binary entry 與 integration test
// 不必下到 per-module 路徑即可 pattern-match。
pub use cli::{parse_cli_args, CliError, ReplayCliArgs};
pub use fixture_loader::{load_fixtures, FixtureError, FixtureSource, MarketEvent};
pub use report_writer::{write_replay_report, ReportError};
pub use runner::{
    build_isolated_pipeline, IsolatedPipeline, PnlSummary, ReplayDiagnostics, ReplayError,
    ReplayResult, ReplayStatus, SimulatedFill,
};
pub use scanner_timeline::{
    replay_default_scanner_config, ReplayScannerTimeline, ReplayScannerTimelineError,
};

// Sprint B2 R5-T1 / R5-T2 re-exports — adapter types accessible at
// `crate::replay::*` so R5-T3 `runner::IsolatedPipeline` wire-up and
// integration tests can pattern-match without descending into per-module
// paths.
// Sprint B2 R5-T1 / R5-T2 re-export — adapter 型別於 `crate::replay::*`
// 可取得，使 R5-T3 `runner::IsolatedPipeline` 接線與 integration test 不必
// 下到 per-module 路徑即可 pattern-match。
pub use risk_adapter::{ReplayPaperSnapshot, ReplayPosition, ReplayRiskAdapter, RiskDecision};
pub use strategy_adapter::{DecisionTraceEntry, ReplayStrategyAdapter, StrategyActionTrace};
