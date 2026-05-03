//! `replay_runner` — REF-20 Paper Replay Lab dedicated Rust binary scaffold.
//!
//! `replay_runner` — REF-20 Paper Replay Lab 專屬 Rust binary 骨架。
//!
//! MODULE_NOTE (EN): Wave 1 scaffold ONLY. This binary exists at the type
//!   level (Cargo.toml `[[bin]]` registered + feature `replay_isolated` gated)
//!   so that downstream waves have a single canonical entry point to wire
//!   into. No runtime logic lives here yet — `main()` panics with an
//!   explicit "wave-mismatch" message. Compiler must succeed, warning
//!   count must be zero.
//!
//!   Why feature-gated:
//!     - Wave 1 R20-P0-T9 (PA crate boundary white-list) requires that the
//!       binary cannot accidentally pull `intent_processor::router`,
//!       `ipc_server`, `startup::build_exchange_pipeline`, exchange
//!       dispatch, DB writer channels, or Decision Lease wiring. Putting
//!       the binary behind `replay_isolated` makes that contract a
//!       compile-time reality (default `cargo build` does NOT compile it,
//!       so accidental dependency drift on the live engine path is
//!       physically impossible until Wave 3 explicitly opts in).
//!     - V3 §3 G7 + G8 mandate dedicated binary + fail-closed isolation.
//!     - Workplan R20-P2b-S10 will add `nm`/`objdump` symbol grep CI step
//!       to enforce defense-in-depth on top of this feature gate.
//!
//!   Forbidden dependencies (Wave 3 R20-P2b-S7/S8/S9/S10 must enforce):
//!     - `crate::intent_processor::router::*` — live execution dispatch.
//!     - `crate::ipc_server::*` — JSON-RPC pipeline to Python.
//!     - `crate::startup::build_exchange_pipeline` — exchange pipeline
//!       bootstrap (contains live order dispatch wiring).
//!     - GovernanceHub / Decision Lease acquisition path (Python side
//!       `governance_hub.acquire_lease()` is the only legitimate caller;
//!       replay binary must NEVER acquire a lease).
//!     - `crate::bybit_private_ws::*` / `crate::ws_client::*` — WS clients.
//!     - `crate::bybit_rest_client::BybitClient::place_order*` — order POST.
//!     - `crate::live_authorization::*` (read OK for FUTURE manifest sign,
//!       but no `_write_signed_live_authorization` path).
//!     - DB writer channels (Wave 3 spec defines exact list).
//!
//!   Allowed dependencies (Wave 3 IMPL builds on these):
//!     - fixture loader / canonical config parser.
//!     - HMAC-SHA256 signature verifier (P2a-S2 lands the module).
//!     - Mac policy guard (`OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA=1`).
//!     - serde / serde_json / chrono / clap / tracing.
//!     - `crate::replay::profile::ReplayProfile` (this scaffold's sibling).
//!
//!   Wave 1 acceptance:
//!     - `cd rust/openclaw_engine && cargo check --bin replay_runner --features replay_isolated`
//!       succeeds with zero warnings.
//!     - `cd rust/openclaw_engine && cargo check` (no feature) succeeds —
//!       this binary must NOT compile by default (verified by absence in
//!       default-feature build target list).
//!
//! MODULE_NOTE (中): Wave 1 純骨架。此 binary 僅在型別層存在（Cargo.toml
//!   `[[bin]]` 註冊 + feature `replay_isolated` gated），讓下游 wave 有
//!   單一正規 entry point 可接線。此處尚無 runtime 邏輯 — `main()` 會以
//!   明確「wave-mismatch」訊息 panic。Compiler 必通過，warning 必歸零。
//!
//!   為什麼 feature-gated：
//!     - Wave 1 R20-P0-T9（PA crate 邊界白名單）要求 binary 不得意外拉入
//!       `intent_processor::router`、`ipc_server`、
//!       `startup::build_exchange_pipeline`、exchange dispatch、DB writer
//!       channel 或 Decision Lease 接線。將 binary 放在 `replay_isolated`
//!       feature 後讓此契約成為 compile-time 事實（預設 `cargo build`
//!       不編譯它 → live engine 路徑的意外依賴漂移在 Wave 3 顯式 opt-in
//!       之前物理上不可能）。
//!     - V3 §3 G7 + G8 要求專屬 binary + fail-closed 隔離。
//!     - Workplan R20-P2b-S10 將加 `nm`/`objdump` symbol grep CI step 在
//!       此 feature gate 之上做縱深防禦。
//!
//!   禁用依賴（Wave 3 R20-P2b-S7/S8/S9/S10 必強制）：
//!     - `crate::intent_processor::router::*` — live 執行 dispatch。
//!     - `crate::ipc_server::*` — Python JSON-RPC 管線。
//!     - `crate::startup::build_exchange_pipeline` — exchange pipeline
//!       bootstrap（含 live 訂單 dispatch 接線）。
//!     - GovernanceHub / Decision Lease 取得路徑（Python 端
//!       `governance_hub.acquire_lease()` 是唯一合法 caller；replay binary
//!       絕不可取 lease）。
//!     - `crate::bybit_private_ws::*` / `crate::ws_client::*` — WS clients。
//!     - `crate::bybit_rest_client::BybitClient::place_order*` — 訂單 POST。
//!     - `crate::live_authorization::*`（FUTURE manifest 簽名 read OK，
//!       但不可走 `_write_signed_live_authorization` 路徑）。
//!     - DB writer channels（Wave 3 spec 定義完整清單）。
//!
//!   允許依賴（Wave 3 IMPL 立基於此）：
//!     - fixture loader / canonical config parser。
//!     - HMAC-SHA256 signature verifier（P2a-S2 落地 module）。
//!     - Mac policy guard（`OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA=1`）。
//!     - serde / serde_json / chrono / clap / tracing。
//!     - `crate::replay::profile::ReplayProfile`（此 scaffold 的姊妹檔）。
//!
//!   Wave 1 驗收：
//!     - `cd rust/openclaw_engine && cargo check --bin replay_runner --features replay_isolated`
//!       成功且 0 warning。
//!     - `cd rust/openclaw_engine && cargo check`（無 feature）成功 —
//!       此 binary 預設不編（驗證：default-feature build target list 不含此 binary）。
//!
//! SPEC: REF-20 V3 §3 G7/G8 + §6.1/§6.2 + workplan R20-P0-T2/T9
//! Owner: PA + E1 (Wave 1 scaffold) → E1 + E2 + E3 (Wave 3 IMPL).

#![cfg(feature = "replay_isolated")]

// TODO REF-20 P2b-S7: replace this stub with `ReplayProfile::Isolated`
// runtime initialization (fail-closed startup verification, manifest load,
// HMAC signature verify-first-then-hash, fixture loader, in-memory
// TickPipeline + IntentProcessor under Isolated profile).
// Implementation must satisfy V3 §12 acceptance #8 / #9 / #10 / #11 / #12.
//
// TODO REF-20 P2b-S7: 將此 stub 取代為 `ReplayProfile::Isolated` runtime
// 初始化（fail-closed startup 驗證、manifest 載入、HMAC 簽名 verify-first-then-hash、
// fixture loader、Isolated profile 下的 in-memory TickPipeline + IntentProcessor）。
// 實作須滿足 V3 §12 acceptance #8 / #9 / #10 / #11 / #12。
//
// TODO REF-20 P2b-S8: forbidden-path fail-closed enforcement
// (startup + runtime panic before any replay tick).
// TODO REF-20 P2b-S8: forbidden-path fail-closed 強制
// （startup + runtime panic，於任何 replay tick 之前）。
//
// TODO REF-20 P2b-S9: Mac policy guard
// (`OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA=1` default; abort on S0/S1 read).
// TODO REF-20 P2b-S9: Mac policy guard
// （`OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA=1` 預設；偵測 S0/S1 讀取則 abort）。
//
// TODO REF-20 P2b-S10: CI nm/objdump symbol audit step
// (defense-in-depth on top of feature gate).
// TODO REF-20 P2b-S10: CI nm/objdump symbol 稽核步驟
// （feature gate 之上的縱深防禦）。

fn main() {
    // Wave 1 scaffold panic — compiler-only contract.
    // Wave 1 骨架 panic — 純編譯期契約。
    panic!("REF-20 P2b-S7/S8 will land runtime; this is Wave 1 scaffold only");
}
