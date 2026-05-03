//! `replay_runner` — REF-20 Paper Replay Lab dedicated Rust binary.
//!
//! `replay_runner` — REF-20 Paper Replay Lab 專屬 Rust binary。
//!
//! MODULE_NOTE (EN): Wave 3 R20-P2b-S7 cfg gate runtime entry. Wave 1 scaffold
//!   established the binary at the type level (Cargo.toml `[[bin]]` registered
//!   + `replay_isolated` feature gated). Wave 3 P2b-S7 wires the runtime
//!   contract: `main()` constructs `ReplayProfile::Isolated`, calls
//!   `fail_closed_assert_isolated()`, and exits 0 with a stub line. Actual
//!   replay logic (manifest verify-first-then-hash, fixture loader, in-memory
//!   TickPipeline + IntentProcessor under Isolated profile) lands in Wave 4
//!   R20-P2b-T2 (per Wave 3 P2b-S7 task spec: "對 既有 `intent_processor::router`
//!   不切換").
//!
//!   Why feature-gated:
//!     - Wave 1 R20-P0-T9 (PA crate boundary white-list) requires that the
//!       binary cannot accidentally pull `intent_processor::router`,
//!       `ipc_server`, `startup::build_exchange_pipeline`, exchange
//!       dispatch, DB writer channels, or Decision Lease wiring. Putting
//!       the binary behind `replay_isolated` makes that contract a
//!       compile-time reality (default `cargo build` does NOT compile it,
//!       so accidental dependency drift on the live engine path is
//!       physically impossible until Wave 4 explicitly opts in).
//!     - V3 §3 G7 + G8 mandate dedicated binary + fail-closed isolation.
//!     - Workplan R20-P2b-S10 will add `nm`/`objdump` symbol grep CI step
//!       to enforce defense-in-depth on top of this feature gate.
//!
//!   Forbidden dependencies (Wave 3 R20-P2b-S8/S9/S10 + Wave 4 must enforce):
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
//!     - Mac policy guard (`OPENCLAW_REPLAY_MAC_NO_PRIVATE=1`, renamed from
//!       `OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA` per Wave 2 dispatch §2 #1).
//!     - serde / serde_json / chrono / clap / tracing.
//!     - `crate::replay::profile::ReplayProfile` (this scaffold's sibling).
//!
//!   Wave 3 P2b-S7 acceptance:
//!     - `cd rust/openclaw_engine && cargo check --bin replay_runner --features replay_isolated`
//!       succeeds with zero warnings.
//!     - `cd rust/openclaw_engine && cargo check` (no feature) succeeds —
//!       this binary must NOT compile by default (verified by absence in
//!       default-feature build target list).
//!     - `target/debug/replay_runner` exits 0 with the stub line and the
//!       fail-closed assert PASSES (because main constructs Isolated).
//!     - V3 §12 #8/#9/#10/#11 acceptance bound to
//!       `tests/replay_profile_acceptance.rs`.
//!
//! MODULE_NOTE (中): Wave 3 R20-P2b-S7 cfg gate runtime entry。Wave 1 骨架
//!   讓 binary 於型別層存在（Cargo.toml `[[bin]]` 註冊 + `replay_isolated`
//!   feature gated）。Wave 3 P2b-S7 接入 runtime 契約：`main()` 建構
//!   `ReplayProfile::Isolated`、呼叫 `fail_closed_assert_isolated()`、印 stub
//!   行後 exit 0。實際 replay 邏輯（manifest verify-first-then-hash、fixture
//!   loader、Isolated profile 下的 in-memory TickPipeline + IntentProcessor）
//!   於 Wave 4 R20-P2b-T2 落地（依 Wave 3 P2b-S7 task spec：「對 既有
//!   `intent_processor::router` 不切換」）。
//!
//!   為什麼 feature-gated：
//!     - Wave 1 R20-P0-T9（PA crate 邊界白名單）要求 binary 不得意外拉入
//!       `intent_processor::router`、`ipc_server`、
//!       `startup::build_exchange_pipeline`、exchange dispatch、DB writer
//!       channel 或 Decision Lease 接線。將 binary 放在 `replay_isolated`
//!       feature 後讓此契約成為 compile-time 事實（預設 `cargo build`
//!       不編譯它 → live engine 路徑的意外依賴漂移在 Wave 4 顯式 opt-in
//!       之前物理上不可能）。
//!     - V3 §3 G7 + G8 要求專屬 binary + fail-closed 隔離。
//!     - Workplan R20-P2b-S10 將加 `nm`/`objdump` symbol grep CI step 在
//!       此 feature gate 之上做縱深防禦。
//!
//!   禁用依賴（Wave 3 R20-P2b-S8/S9/S10 + Wave 4 必強制）：
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
//!     - Mac policy guard（`OPENCLAW_REPLAY_MAC_NO_PRIVATE=1`，per Wave 2
//!       dispatch §2 #1 由 `OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA` 改名）。
//!     - serde / serde_json / chrono / clap / tracing。
//!     - `crate::replay::profile::ReplayProfile`（此 scaffold 的姊妹檔）。
//!
//!   Wave 3 P2b-S7 驗收：
//!     - `cd rust/openclaw_engine && cargo check --bin replay_runner --features replay_isolated`
//!       成功且 0 warning。
//!     - `cd rust/openclaw_engine && cargo check`（無 feature）成功 —
//!       此 binary 預設不編（驗證：default-feature build target list 不含此 binary）。
//!     - `target/debug/replay_runner` 以 stub 行 exit 0，且 fail-closed assert
//!       通過（因為 main 建構 Isolated）。
//!     - V3 §12 #8/#9/#10/#11 acceptance 綁
//!       `tests/replay_profile_acceptance.rs`。
//!
//! SPEC: REF-20 V3 §3 G7/G8 + §6.1/§6.2 + §12 #8/#9/#10/#11
//!     + workplan R20-P2b-S7
//! Owner: PA + E1 (Wave 1 scaffold) → E1 + E2 + E3 (Wave 3 IMPL).

#![cfg(feature = "replay_isolated")]

// TODO REF-20 P2b-S8: forbidden-path fail-closed enforcement
// (startup + runtime panic before any replay tick — full V3 §6.2 list,
//  not just profile assert).
// TODO REF-20 P2b-S8: forbidden-path fail-closed 強制
// （startup + runtime panic，於任何 replay tick 之前 — 完整 V3 §6.2 清單，
//   非僅 profile assert）。
//
// TODO REF-20 P2b-S9: Mac policy guard
// (`OPENCLAW_REPLAY_MAC_NO_PRIVATE=1` default; abort on S0/S1 read).
// TODO REF-20 P2b-S9: Mac policy guard
// （`OPENCLAW_REPLAY_MAC_NO_PRIVATE=1` 預設；偵測 S0/S1 讀取則 abort）。
//
// TODO REF-20 P2b-S10: CI nm/objdump symbol audit step
// (defense-in-depth on top of feature gate).
// TODO REF-20 P2b-S10: CI nm/objdump symbol 稽核步驟
// （feature gate 之上的縱深防禦）。
//
// TODO REF-20 P2b-T2 (Wave 4): wire actual replay logic past the
// fail-closed assert (manifest signer verify-first-then-hash via
// `crate::replay::manifest_signer`, fixture loader, in-memory
// TickPipeline + IntentProcessor under Isolated profile).
// TODO REF-20 P2b-T2 (Wave 4): 在 fail-closed assert 通過後接入實際 replay
// 邏輯（透過 `crate::replay::manifest_signer` 做 manifest verify-first-then-hash、
// fixture loader、Isolated profile 下的 in-memory TickPipeline + IntentProcessor）。

use openclaw_engine::replay::profile::ReplayProfile;

fn main() {
    // Wave 3 P2b-S7 cfg gate runtime entry.
    // Wave 3 P2b-S7 cfg gate runtime entry.
    //
    // 不變量 / Invariant: `replay_runner` MUST run as `ReplayProfile::Isolated`.
    //   The compile-time `replay_isolated` feature gates this binary OUT of
    //   the default build (so Live hot path can never link it). The runtime
    //   assert below is defense-in-depth: if a future caller accidentally
    //   constructs a non-Isolated profile here, the binary aborts
    //   immediately rather than proceeding to replay logic.
    //
    // Invariant: `replay_runner` 必以 `ReplayProfile::Isolated` 跑。
    //   compile-time 的 `replay_isolated` feature 把此 binary 排除在預設
    //   build 之外（故 Live hot path 永不可能 link 它）。下方 runtime
    //   assert 為縱深防禦：若未來 caller 不慎在此構造 non-Isolated
    //   profile，binary 立即 abort 而非繼續跑 replay 邏輯。
    let profile = ReplayProfile::Isolated;

    profile.fail_closed_assert_isolated().expect(
        "REF-20 V3 §6.2 invariant: replay_runner MUST run as Isolated; \
         see crate::replay::profile::ReplayProfile::fail_closed_assert_isolated",
    );

    // Wave 4 R20-P2b-T2 will replace the `eprintln!` below with actual
    // replay logic. Until then, we emit a deterministic stub line and exit
    // 0 so that operators / CI / acceptance tests can confirm the binary
    // built and the runtime gate passed.
    //
    // Wave 4 R20-P2b-T2 將以實際 replay 邏輯取代下方的 `eprintln!`。在此
    // 之前我們發出 deterministic stub 行並 exit 0，讓 operator / CI /
    // acceptance test 確認 binary 已 build 且 runtime gate 通過。
    eprintln!("replay_runner Wave 3 P2b-S7 cfg gate online; Wave 4 logic pending");
}
