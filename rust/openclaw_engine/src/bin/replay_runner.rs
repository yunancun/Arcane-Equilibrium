//! `replay_runner` — REF-20 Paper Replay Lab dedicated Rust binary.
//!
//! `replay_runner` — REF-20 Paper Replay Lab 專屬 Rust binary。
//!
//! MODULE_NOTE (EN): Wave 3 R20-P2b-S7/S8/S9 three-layer fail-closed guard
//!   chain at runtime entry. Wave 1 scaffold established the binary at the
//!   type level (Cargo.toml `[[bin]]` registered + `replay_isolated` feature
//!   gated). Wave 3 P2b-S7 wired the profile cfg gate; Wave 3 P2b-S8 (this
//!   commit) wires the FULL V3 §6.2 forbidden-path enforcement; Wave 3
//!   P2b-S9 (this commit) wires the V3 §6.3 Mac fail-closed gate. `main()`
//!   constructs `ReplayProfile::Isolated`, runs all three guards in order,
//!   and exits 0 with a stub line on success. Actual replay logic (manifest
//!   verify-first-then-hash, fixture loader, in-memory TickPipeline +
//!   IntentProcessor under Isolated profile) lands in Wave 4 R20-P2b-T1/T2
//!   (per Wave 3 P2b-S7 task spec: "對 既有 `intent_processor::router`
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
//!   Wave 3 P2b-S7/S8/S9 acceptance:
//!     - `cd rust/openclaw_engine && cargo check --bin replay_runner --features replay_isolated`
//!       succeeds with zero warnings.
//!     - `cd rust/openclaw_engine && cargo check` (no feature) succeeds —
//!       this binary must NOT compile by default (verified by absence in
//!       default-feature build target list).
//!     - `target/debug/replay_runner` exits 0 with the stub line
//!       "replay_runner Wave 3 P2b-S7/S8/S9 guards online; Wave 4 logic
//!       pending" when invoked with `OPENCLAW_REPLAY_MAC_NO_PRIVATE=1`
//!       (required on macOS host) and no forbidden-trip env / file marker.
//!     - V3 §12 #8/#9/#10/#11 acceptance bound to
//!       `tests/replay_profile_acceptance.rs`.
//!     - V3 §12 #10 forbidden-wiring fail-closed acceptance bound to
//!       `tests/replay_forbidden_guard_acceptance.rs`.
//!     - V3 §12 #12 Mac non-actionable acceptance bound to
//!       `tests/replay_mac_policy_acceptance.rs`.
//!
//! MODULE_NOTE (中): Wave 3 R20-P2b-S7/S8/S9 三層 fail-closed guard 串聯於
//!   runtime entry。Wave 1 骨架讓 binary 於型別層存在（Cargo.toml `[[bin]]`
//!   註冊 + `replay_isolated` feature gated）。Wave 3 P2b-S7 接入 profile
//!   cfg gate；Wave 3 P2b-S8（本 commit）接入完整 V3 §6.2 forbidden-path
//!   強制；Wave 3 P2b-S9（本 commit）接入 V3 §6.3 Mac fail-closed gate。
//!   `main()` 建構 `ReplayProfile::Isolated`，依序跑三 guard，全通過則印 stub
//!   行並 exit 0。實際 replay 邏輯（manifest verify-first-then-hash、fixture
//!   loader、Isolated profile 下的 in-memory TickPipeline + IntentProcessor）
//!   於 Wave 4 R20-P2b-T1/T2 落地（依 Wave 3 P2b-S7 task spec：「對 既有
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
//!   Wave 3 P2b-S7/S8/S9 驗收：
//!     - `cd rust/openclaw_engine && cargo check --bin replay_runner --features replay_isolated`
//!       成功且 0 warning。
//!     - `cd rust/openclaw_engine && cargo check`（無 feature）成功 —
//!       此 binary 預設不編（驗證：default-feature build target list 不含此 binary）。
//!     - `target/debug/replay_runner` 以 stub 行
//!       「replay_runner Wave 3 P2b-S7/S8/S9 guards online; Wave 4 logic
//!       pending」exit 0，需設 `OPENCLAW_REPLAY_MAC_NO_PRIVATE=1`（macOS
//!       host required）且無 forbidden-trip env / file marker。
//!     - V3 §12 #8/#9/#10/#11 acceptance 綁
//!       `tests/replay_profile_acceptance.rs`。
//!     - V3 §12 #10 forbidden-wiring fail-closed acceptance 綁
//!       `tests/replay_forbidden_guard_acceptance.rs`。
//!     - V3 §12 #12 Mac non-actionable acceptance 綁
//!       `tests/replay_mac_policy_acceptance.rs`。
//!
//! SPEC: REF-20 V3 §3 G7/G8 + §6.1/§6.2/§6.3 + §12 #8/#9/#10/#11/#12
//!     + workplan R20-P2b-S7/S8/S9
//! Owner: PA + E1 (Wave 1 scaffold) → E1 + E2 + E3 (Wave 3 IMPL).

#![cfg(feature = "replay_isolated")]

// TODO REF-20 P2b-S10: CI nm/objdump symbol audit step
// (defense-in-depth on top of feature gate).
// TODO REF-20 P2b-S10: CI nm/objdump symbol 稽核步驟
// （feature gate 之上的縱深防禦）。
//
// TODO REF-20 P2b-T1 (Wave 4): isolated process wrapper that mediates
// between this binary and (sandboxed) versions of intent_processor::router,
// ipc_server::dispatch, bybit_rest_client::place_order. The wrapper is
// where forbidden_guard::enforce_at_runtime plugs into per-action
// hard-coded interception branches.
// TODO REF-20 P2b-T1 (Wave 4): isolated process wrapper，介於本 binary 與
// sandboxed 版的 intent_processor::router / ipc_server::dispatch /
// bybit_rest_client::place_order 之間。wrapper 是 forbidden_guard::
// enforce_at_runtime 接入 per-action hard-coded 攔截分支的位置。
//
// TODO REF-20 P2b-T2 (Wave 4): wire actual replay logic past the
// three fail-closed guards (manifest signer verify-first-then-hash via
// `crate::replay::manifest_signer`, fixture loader, in-memory
// TickPipeline + IntentProcessor under Isolated profile).
// TODO REF-20 P2b-T2 (Wave 4): 在三個 fail-closed guard 通過後接入實際
// replay 邏輯（透過 `crate::replay::manifest_signer` 做 manifest
// verify-first-then-hash、fixture loader、Isolated profile 下的 in-memory
// TickPipeline + IntentProcessor）。
//
// Forbidden-path list reminder (V3 §6.2 + PA boundary §5):
//   - Decision Lease acquire/release        (forbidden_guard #1)
//   - IPC server start                       (forbidden_guard #2)
//   - WS client start                        (forbidden_guard #3)
//   - Exchange dispatch                      (forbidden_guard #4)
//   - DB writer channel use                  (forbidden_guard #5)
//   - Live/demo config mutate                (forbidden_guard #6)
//   - Advisory write outside verified PL/pgSQL (forbidden_guard #7)
//
// Forbidden 清單提醒（V3 §6.2 + PA boundary §5）：
//   - Decision Lease 取得/釋放              （forbidden_guard #1）
//   - IPC server 啟動                        （forbidden_guard #2）
//   - WS client 啟動                         （forbidden_guard #3）
//   - Exchange dispatch                      （forbidden_guard #4）
//   - DB writer channel 使用                 （forbidden_guard #5）
//   - Live/demo config mutate                （forbidden_guard #6）
//   - 不走 verified PL/pgSQL 的 advisory 寫入（forbidden_guard #7）

use openclaw_engine::replay::forbidden_guard;
use openclaw_engine::replay::mac_policy_guard;
use openclaw_engine::replay::profile::ReplayProfile;

fn main() {
    // Wave 3 P2b-S7/S8/S9 三層 fail-closed guard 串聯。
    // Wave 3 P2b-S7/S8/S9 three-layer fail-closed guard chain.
    //
    // 不變量 / Invariant: `replay_runner` MUST run as `ReplayProfile::Isolated`,
    //   MUST NOT have any V3 §6.2 forbidden-path tripped, AND MUST satisfy
    //   the V3 §6.3 Mac policy when running on a macOS host. All three
    //   guards run before any replay logic; the binary aborts on the FIRST
    //   guard's `Err` (V3 §12 #10 + #12 binding: forbidden path aborts run,
    //   NOT log-only).
    //
    // Invariant: `replay_runner` 必以 `ReplayProfile::Isolated` 跑、不得有任
    //   何 V3 §6.2 forbidden-path 被觸發、且在 macOS host 上必滿足 V3 §6.3
    //   Mac 政策。三 guard 在任何 replay 邏輯前跑；binary 在「第一個」guard
    //   的 `Err` 即 abort（V3 §12 #10 + #12 binding：forbidden 路徑 abort run，
    //   非 log-only）。
    let profile = ReplayProfile::Isolated;

    // S7 (Wave 3 P2b-S7): profile cfg gate. Refuses non-Isolated profiles.
    // S7（Wave 3 P2b-S7）：profile cfg gate。拒絕 non-Isolated profile。
    profile.fail_closed_assert_isolated().expect(
        "REF-20 V3 §6.2 invariant: replay_runner MUST run as Isolated; \
         see crate::replay::profile::ReplayProfile::fail_closed_assert_isolated",
    );

    // S8 (Wave 3 P2b-S8): forbidden-path enforcement at startup. Reads env
    // var $OPENCLAW_REPLAY_FORBIDDEN_TRIPPED + magic-file marker
    // <OPENCLAW_DATA_DIR>/replay_forbidden.tripped; absence (production
    // default) returns Ok(()).
    //
    // S8（Wave 3 P2b-S8）：startup 階段的 forbidden-path 強制。讀 env var
    // $OPENCLAW_REPLAY_FORBIDDEN_TRIPPED + magic-file marker
    // <OPENCLAW_DATA_DIR>/replay_forbidden.tripped；皆未設（production 預設）
    // 回 Ok(())。
    forbidden_guard::enforce_at_startup().expect(
        "REF-20 V3 §6.2 forbidden path detected at startup; \
         see crate::replay::forbidden_guard::enforce_at_startup",
    );

    // S9 (Wave 3 P2b-S9): Mac policy guard. On macOS requires
    // OPENCLAW_REPLAY_MAC_NO_PRIVATE=1 (renamed per Wave 2 dispatch §2 #1
    // from OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA) and Isolated profile. On
    // non-macOS hosts returns Ok(()) unconditionally (V3 §6.3 scopes the
    // policy to Mac).
    //
    // S9（Wave 3 P2b-S9）：Mac 政策 guard。macOS 上要求
    // OPENCLAW_REPLAY_MAC_NO_PRIVATE=1（依 Wave 2 dispatch §2 #1 由
    // OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA 改名）+ Isolated profile。
    // 非 macOS host 無條件回 Ok(())（V3 §6.3 將政策限於 Mac）。
    mac_policy_guard::enforce(profile).expect(
        "REF-20 V3 §6.3 Mac policy violation; \
         see crate::replay::mac_policy_guard::enforce",
    );

    // Wave 4 R20-P2b-T2 will replace the `eprintln!` below with actual
    // replay logic. Until then, we emit a deterministic stub line and exit
    // 0 so that operators / CI / acceptance tests can confirm the binary
    // built and the three runtime guards passed.
    //
    // Wave 4 R20-P2b-T2 將以實際 replay 邏輯取代下方的 `eprintln!`。在此
    // 之前我們發出 deterministic stub 行並 exit 0，讓 operator / CI /
    // acceptance test 確認 binary 已 build 且三個 runtime guard 通過。
    eprintln!("replay_runner Wave 3 P2b-S7/S8/S9 guards online; Wave 4 logic pending");
}
