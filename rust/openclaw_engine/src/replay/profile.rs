//! `ReplayProfile` cfg gate spec — REF-20 V3 §3 G7/G8 + §6.2 contract.
//!
//! REF-20 V3 §3 G7/G8 與 §6.2 契約 — `ReplayProfile` cfg gate 規格。
//!
//! MODULE_NOTE (EN): Wave 1 SPEC ONLY. This module declares the `ReplayProfile`
//!   enum that controls the replay runner's behavioral envelope; runtime IMPL
//!   (path enforcement / fail-closed guards) lands in Wave 3 R20-P2b-S7/S8.
//!   Until then this is a documentation surface — no runtime caller, no
//!   trait impl, no method bodies. The enum exists so that the binary
//!   scaffold (`bin/replay_runner.rs`) and downstream Mac policy guard
//!   (R20-P2b-S9) have a single canonical type to reference in their TODO
//!   markers and forbidden-path comments.
//!
//!   Why this is spec-only:
//!     - V3 §3 G7 mandates dedicated Rust binary `replay_runner` chosen and
//!       wired BEFORE implementation; this enum is the type-level contract
//!       that wiring will hang off.
//!     - V3 §3 G8 mandates fail-closed isolation; that semantics is
//!       enforced in `ReplayProfile::Isolated` runtime IMPL (Wave 3), NOT
//!       in this scaffold.
//!     - Wave 1 Exit Criteria forbids runtime IMPL — anything more than
//!       the bare enum declaration belongs to a later wave.
//!
//!   Profile semantics (forward-looking, NOT enforced here):
//!     - `Live` — production live engine path; never used by replay binary.
//!     - `LiveDemo` — Live pipeline against demo endpoint; never used by
//!       replay binary.
//!     - `PaperLegacy` — pre-REF-20 paper engine surface; preserved for
//!       Paper Tab Session sub-tab continuity (UX subdoc §11.1); replay
//!       binary does NOT enter this profile.
//!     - `Isolated` — REF-20 P2/P2b read-only smoke replay surface. MUST
//!       satisfy V3 §6.2 forbidden list at runtime: no Decision Lease
//!       acquire, no IPC server, no WS client, no exchange dispatch, no
//!       DB writer channels, no live/demo config mutation. Wave 3 IMPL
//!       enforces these via startup + runtime fail-closed guards.
//!
//!   Cross-references:
//!     - SPEC: REF-20 V3 §3 G7/G8 + §6.2 + workplan R20-P2b-S7
//!     - Binary scaffold: `src/bin/replay_runner.rs` (Wave 1 R20-P0-T2)
//!     - Crate boundary allowlist: PA report
//!       `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-03--replay_runner_crate_boundary_allowlist.md`
//!     - Mac policy guard: Wave 3 R20-P2b-S9 (`OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA=1`)
//!     - Symbol audit: Wave 3 R20-P2b-S10 (`nm` / `objdump` CI grep)
//!
//! MODULE_NOTE (中): Wave 1 純規格宣告。本 module 宣告 `ReplayProfile` enum
//!   作為 replay runner 行為包絡的 cfg gate；runtime IMPL（路徑強制 /
//!   fail-closed guard）於 Wave 3 R20-P2b-S7/S8 落地。在此之前這只是
//!   文件層 type — 無 runtime caller、無 trait impl、無方法本體。
//!   enum 存在的目的是讓 binary scaffold（`bin/replay_runner.rs`）與
//!   下游 Mac policy guard（R20-P2b-S9）有一個正規型別可以在 TODO 標記
//!   與 forbidden-path 注釋中引用。
//!
//!   為什麼是 spec-only：
//!     - V3 §3 G7 要求專屬 Rust binary `replay_runner` 在實作前先選定並
//!       接線；此 enum 即接線將吊掛的型別層契約。
//!     - V3 §3 G8 要求 fail-closed 隔離；該語意在 Wave 3 `ReplayProfile::Isolated`
//!       runtime IMPL 強制，不在本 scaffold。
//!     - Wave 1 Exit Criteria 禁止 runtime IMPL — 多於 enum bare 宣告
//!       的東西屬於後續 wave。
//!
//!   Profile 語意（前瞻性，本檔案不強制）：
//!     - `Live` — 正式 live 引擎路徑；replay binary 永不使用。
//!     - `LiveDemo` — Live 管線打 demo endpoint；replay binary 永不使用。
//!     - `PaperLegacy` — 前 REF-20 paper 引擎 surface；保留以維持 Paper
//!       Tab Session sub-tab 既有行為（UX subdoc §11.1）；replay binary
//!       不進此 profile。
//!     - `Isolated` — REF-20 P2/P2b 唯讀 smoke replay surface。Runtime
//!       必滿足 V3 §6.2 forbidden 清單：不取 Decision Lease、不啟 IPC
//!       server、不啟 WS client、不下 exchange dispatch、不接 DB writer
//!       channel、不寫 live/demo config。Wave 3 IMPL 透過 startup +
//!       runtime fail-closed guard 強制。
//!
//! SPEC: REF-20 V3 §3 G7/G8 + workplan R20-P2b-S7

// SPEC: REF-20 V3 §3 G7/G8 + workplan R20-P2b-S7
//
// Spec-only declaration. Runtime IMPL lives in Wave 3 R20-P2b-S7/S8/S9/S10.
// No `impl` block, no trait impl, no method bodies.
//
// 純規格宣告。Runtime IMPL 在 Wave 3 R20-P2b-S7/S8/S9/S10。
// 無 `impl` block、無 trait impl、無方法本體。
//
// `#[allow(dead_code)]` is required — this enum has zero callers in Wave 1
// by design; without the lint suppression `cargo check` would warn
// (warning-zero is a Wave 1 acceptance criterion).
//
// `#[allow(dead_code)]` 必加 — 設計上 Wave 1 此 enum 0 caller；
// 不加 lint 抑制會觸發 warning（warning=0 是 Wave 1 acceptance criterion）。
#[allow(dead_code)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ReplayProfile {
    /// Production live engine path. Replay binary MUST NOT use.
    /// 正式 live 引擎路徑。replay binary 不得使用。
    Live,

    /// Live pipeline against demo endpoint. Replay binary MUST NOT use.
    /// Live 管線打 demo endpoint。replay binary 不得使用。
    LiveDemo,

    /// Pre-REF-20 paper engine surface. Preserved for Paper Tab Session
    /// sub-tab continuity (UX subdoc §11.1). Replay binary MUST NOT use.
    /// 前 REF-20 paper 引擎 surface。保留以維持 Paper Tab Session
    /// sub-tab 既有行為（UX subdoc §11.1）。replay binary 不得使用。
    PaperLegacy,

    /// REF-20 P2/P2b read-only smoke replay surface.
    /// Wave 3 IMPL must enforce V3 §6.2 forbidden list at runtime.
    ///
    /// REF-20 P2/P2b 唯讀 smoke replay surface。
    /// Wave 3 IMPL 須於 runtime 強制 V3 §6.2 forbidden 清單。
    Isolated,
}
