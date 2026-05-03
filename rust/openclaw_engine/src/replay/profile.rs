//! `ReplayProfile` cfg gate runtime IMPL — REF-20 V3 §3 G7/G8 + §6.2 contract.
//!
//! REF-20 V3 §3 G7/G8 與 §6.2 契約 — `ReplayProfile` cfg gate runtime 實作。
//!
//! MODULE_NOTE (EN): Wave 3 R20-P2b-S7 lands the runtime IMPL. The
//!   `ReplayProfile` enum is now equipped with five gating methods that the
//!   `replay_runner` binary (and any future caller of the `Isolated` profile)
//!   uses to assert V3 §6.2 forbidden-list compliance at runtime. The methods
//!   are declarative — they answer yes/no questions about whether a profile
//!   may take Decision Lease, run an IPC server, dispatch to the exchange, or
//!   plug into DB writer channels. The fifth method (`fail_closed_assert_isolated`)
//!   is the runtime guard the binary uses on entry to refuse any non-Isolated
//!   profile.
//!
//!   Wave 3 P2b-S7 scope (this commit):
//!     - 5 method bodies on `impl ReplayProfile` (per Wave 2 dispatch §2 #4):
//!         `requires_lease`, `allow_ipc_server`,
//!         `allow_exchange_dispatch`, `allow_db_writer_channels`,
//!         `fail_closed_assert_isolated`.
//!     - `ReplayIsolationError` enum (`WrongProfile { found }`) for the
//!         fifth method's `Result` return; kept module-private-by-narrow-export
//!         so it does not leak into a wider error type used by Live hot path.
//!     - 5 acceptance unit tests live in
//!         `rust/openclaw_engine/tests/replay_profile_acceptance.rs`
//!         (V3 §12 #8 / #9 / #10 / #11 binding).
//!
//!   What stays out of scope (deferred to Wave 4 R20-P2b-T2):
//!     - Wiring `intent_processor::router` to consult these methods on dispatch.
//!     - Wiring `replay_runner::main` to run actual replay logic past the
//!         fail-closed assert (current main only runs the assert + prints a
//!         stub line).
//!     - Plugging into `manifest_signer` verify-first-then-hash flow.
//!     - Mac policy guard (`OPENCLAW_REPLAY_MAC_NO_PRIVATE=1`) — that is
//!         R20-P2b-S9's responsibility.
//!
//!   Why these five methods (and only these five):
//!     - V3 §6.2 forbidden list contains exactly these four runtime surfaces
//!         (lease / IPC server / exchange dispatch / DB writer channels) plus
//!         a meta surface (the profile itself must be `Isolated`).
//!     - The methods are intentionally NOT generic — they hardcode the Wave 2
//!         dispatch §2 #4 decision: `Isolated => false / 其餘 => true`. Future
//!         profile additions MUST update both the method match arms and the
//!         acceptance suite (the test file enumerates all four current
//!         variants explicitly to catch silent default-arm drift).
//!
//!   Cross-references:
//!     - SPEC: REF-20 V3 §3 G7/G8 + §6.2 + §12 #8/#9/#10/#11
//!     - Workplan: docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md
//!         §4 Wave 3 R20-P2b-S7 row
//!     - Wave 2 dispatch §2 ambiguity #4: `Isolated => requires_lease=false`
//!     - PA boundary allowlist:
//!         docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-03--replay_runner_crate_boundary_allowlist.md
//!     - Sibling module: `crate::replay::manifest_signer` (Wave 2 P2a-S2)
//!     - Binary entry: `src/bin/replay_runner.rs` (Wave 1 scaffold; Wave 3
//!         calls `fail_closed_assert_isolated` on entry)
//!     - Acceptance tests: `tests/replay_profile_acceptance.rs`
//!
//! MODULE_NOTE (中): Wave 3 R20-P2b-S7 落地 runtime IMPL。`ReplayProfile`
//!   enum 現在配備五個 gating method，供 `replay_runner` binary（以及任何未來
//!   `Isolated` profile 的 caller）在 runtime 強制 V3 §6.2 forbidden 清單。
//!   方法為宣告式 — 回答「該 profile 可否取 Decision Lease / 啟 IPC server /
//!   下 exchange dispatch / 接 DB writer channel」的 yes/no 問題。第五個方法
//!   （`fail_closed_assert_isolated`）是 binary entry 的 runtime guard，拒絕
//!   任何 non-Isolated profile。
//!
//!   Wave 3 P2b-S7 範圍（本 commit）：
//!     - `impl ReplayProfile` 上的 5 個 method body（per Wave 2 dispatch §2 #4）：
//!         `requires_lease`、`allow_ipc_server`、
//!         `allow_exchange_dispatch`、`allow_db_writer_channels`、
//!         `fail_closed_assert_isolated`。
//!     - `ReplayIsolationError` enum（`WrongProfile { found }`），供第五
//!         方法的 `Result` 回傳；以最窄 export 範圍呈現，避免污染 Live hot
//!         path 既有的更廣 error type。
//!     - 5 個 acceptance unit test 落於
//!         `rust/openclaw_engine/tests/replay_profile_acceptance.rs`
//!         （V3 §12 #8 / #9 / #10 / #11 binding）。
//!
//!   不在本範圍（延 Wave 4 R20-P2b-T2）：
//!     - Wire `intent_processor::router` 在 dispatch 時參考這些 method。
//!     - Wire `replay_runner::main` 在 fail-closed assert 通過後跑實際 replay
//!         邏輯（當前 main 只跑 assert + 印 stub 行）。
//!     - 接 `manifest_signer` 的 verify-first-then-hash 流程。
//!     - Mac policy guard（`OPENCLAW_REPLAY_MAC_NO_PRIVATE=1`）— 屬 R20-P2b-S9。
//!
//!   為什麼是這五個方法（且僅這五個）：
//!     - V3 §6.2 forbidden 清單恰好 = 這四個 runtime surface（lease /
//!         IPC server / exchange dispatch / DB writer channel）加一個 meta
//!         surface（profile 自身須為 `Isolated`）。
//!     - 方法刻意不泛型 — 直接 hardcode Wave 2 dispatch §2 #4 決議：
//!         `Isolated => false / 其餘 => true`。未來新增 profile variant
//!         必同步更新 method match arm 與 acceptance suite（test 檔列舉
//!         所有四個現有 variant，以捕捉 silent default-arm 漂移）。
//!
//!   Cross-references：
//!     - SPEC：REF-20 V3 §3 G7/G8 + §6.2 + §12 #8/#9/#10/#11
//!     - Workplan：docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md
//!         §4 Wave 3 R20-P2b-S7 row
//!     - Wave 2 dispatch §2 ambiguity #4：`Isolated => requires_lease=false`
//!     - PA boundary allowlist：
//!         docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-03--replay_runner_crate_boundary_allowlist.md
//!     - Sibling module：`crate::replay::manifest_signer`（Wave 2 P2a-S2）
//!     - Binary entry：`src/bin/replay_runner.rs`（Wave 1 scaffold；Wave 3
//!         在 entry 呼叫 `fail_closed_assert_isolated`）
//!     - Acceptance tests：`tests/replay_profile_acceptance.rs`
//!
//! SPEC: REF-20 V3 §3 G7/G8 + §6.2 + §12 #8/#9/#10/#11

// SPEC: REF-20 V3 §3 G7/G8 + §6.2 + workplan R20-P2b-S7
//
// Wave 3 IMPL — `#[allow(dead_code)]` removed because every variant is now
// matched in `impl ReplayProfile` and exercised by acceptance tests.
//
// Wave 3 IMPL — `#[allow(dead_code)]` 已移除，因每個 variant 現皆在
// `impl ReplayProfile` 中被 match 並由 acceptance test 演練。
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
    /// Wave 3 IMPL enforces V3 §6.2 forbidden list at runtime via the
    /// gating methods on `impl ReplayProfile`.
    ///
    /// REF-20 P2/P2b 唯讀 smoke replay surface。
    /// Wave 3 IMPL 透過 `impl ReplayProfile` 上的 gating method 於 runtime
    /// 強制 V3 §6.2 forbidden 清單。
    Isolated,
}

/// Runtime guard error for `fail_closed_assert_isolated`.
///
/// `fail_closed_assert_isolated` 用的 runtime guard 錯誤型別。
///
/// Scope/作用域 (EN):
///   This enum is declared narrowly so that the `replay` subsystem can carry
///   its own typed failure mode WITHOUT plugging into the wider engine error
///   types (`crate::error::*` / `thiserror`-based types in the live hot
///   path). That isolation is intentional — V3 §6.2 forbids the replay binary
///   from leaking into Live error surfaces, and a wider error type would force
///   replay-side dependencies onto the live path or vice versa.
///
/// Scope/作用域 (中)：
///   此 enum 刻意宣告為窄範圍，使 `replay` 子系統能攜帶自有具型別失敗模式，
///   而**不**插入到 Live hot path 用的更廣引擎錯誤型別（`crate::error::*` /
///   `thiserror`-based 型別）。此隔離有意為之 — V3 §6.2 禁止 replay binary
///   洩漏進 Live error surface；引入更廣型別會迫使 replay 端依賴 live path
///   或反之。
///
/// Naming rationale (EN):
///   `WrongProfile` is the precise semantic — the binary intends `Isolated`
///   but received another profile. The `found` payload carries the actual
///   profile so callers can log/audit which non-Isolated profile leaked.
///
/// 命名理由（中）：
///   `WrongProfile` 為精準語義 — binary 本意 `Isolated` 卻收到其他 profile。
///   `found` payload 攜帶實際 profile 供 caller log/audit 哪個 non-Isolated
///   profile 洩漏。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ReplayIsolationError {
    /// Profile was not `Isolated`.
    /// Profile 非 `Isolated`。
    WrongProfile { found: ReplayProfile },
}

impl std::fmt::Display for ReplayIsolationError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::WrongProfile { found } => write!(
                f,
                "ReplayIsolationError::WrongProfile {{ found: {:?} }} \
                 — replay_runner refuses non-Isolated profile (V3 §6.2)",
                found
            ),
        }
    }
}

impl std::error::Error for ReplayIsolationError {}

impl ReplayProfile {
    /// Whether this profile requires acquiring a Decision Lease before any
    /// trade intent dispatch.
    ///
    /// 此 profile 在派發任何交易意圖前是否需取 Decision Lease。
    ///
    /// Semantics (EN):
    ///   - `Isolated` => `false`. The replay binary MUST NEVER acquire a
    ///     lease (V3 §6.2 forbidden list, V3 §12 #9 acceptance binding).
    ///   - All other variants (`Live`, `LiveDemo`, `PaperLegacy`) => `true`.
    ///     They keep the existing Decision Lease contract documented in
    ///     CLAUDE.md §五 footnote (*) and AMD-2026-05-02-01.
    ///
    /// 語意（中）：
    ///   - `Isolated` => `false`。replay binary 絕不可取 lease（V3 §6.2
    ///     forbidden list、V3 §12 #9 acceptance binding）。
    ///   - 其餘 variant（`Live` / `LiveDemo` / `PaperLegacy`）=> `true`。
    ///     維持 CLAUDE.md §五 footnote (*) 與 AMD-2026-05-02-01 中既有的
    ///     Decision Lease 契約。
    ///
    /// SPEC: Wave 2 dispatch §2 ambiguity #4 (PM final).
    pub fn requires_lease(&self) -> bool {
        // 不變量 / Invariant: `Isolated` 是唯一無需 lease 的 profile；
        // 其餘三 variant 維持既有 Decision Lease 路徑承諾。
        // Invariant: `Isolated` is the only lease-free profile; the other
        // three variants keep their pre-existing Decision Lease commitment.
        !matches!(self, ReplayProfile::Isolated)
    }

    /// Whether this profile may run the JSON-RPC IPC server that bridges
    /// the engine to the Python control_api_v1 process.
    ///
    /// 此 profile 是否可啟用銜接引擎與 Python control_api_v1 行程的
    /// JSON-RPC IPC server。
    ///
    /// Semantics (EN):
    ///   - `Isolated` => `false`. V3 §6.2 forbidden list bans IPC server in
    ///     replay (V3 §12 #8 acceptance binding).
    ///   - Other variants => `true`. Live + LiveDemo + PaperLegacy all
    ///     keep their existing IPC bridge wiring.
    ///
    /// 語意（中）：
    ///   - `Isolated` => `false`。V3 §6.2 forbidden list 禁 replay 內 IPC
    ///     server（V3 §12 #8 acceptance binding）。
    ///   - 其餘 variant => `true`。Live + LiveDemo + PaperLegacy 維持既有
    ///     IPC 橋接接線。
    pub fn allow_ipc_server(&self) -> bool {
        !matches!(self, ReplayProfile::Isolated)
    }

    /// Whether this profile may dispatch live exchange calls (REST POST /
    /// WS subscribe / order placement).
    ///
    /// 此 profile 是否可派發真實交易所呼叫（REST POST / WS subscribe /
    /// 下單）。
    ///
    /// Semantics (EN):
    ///   - `Isolated` => `false`. V3 §6.2 forbids exchange dispatch in
    ///     replay; V3 §12 #14 (`replay_no_live_mutation`) is the strongest
    ///     contractual bind.
    ///   - Other variants => `true`. They keep their pre-existing exchange
    ///     dispatch path (subject to live gates 1-5 in CLAUDE.md §四).
    ///
    /// 語意（中）：
    ///   - `Isolated` => `false`。V3 §6.2 禁 replay 中 exchange dispatch；
    ///     V3 §12 #14（`replay_no_live_mutation`）為最強契約綁定。
    ///   - 其餘 variant => `true`。維持既有 exchange dispatch 路徑（仍受
    ///     CLAUDE.md §四 live gate 1-5 把關）。
    pub fn allow_exchange_dispatch(&self) -> bool {
        !matches!(self, ReplayProfile::Isolated)
    }

    /// Whether this profile may plug into DB writer channels that mutate
    /// `trading.*`, `learning.*`, or `replay.*` tables (the canary writer
    /// path in particular).
    ///
    /// 此 profile 是否可接入會修改 `trading.*` / `learning.*` / `replay.*`
    /// 表的 DB writer channel（特別是 canary writer 路徑）。
    ///
    /// Semantics (EN):
    ///   - `Isolated` => `false`. The runner runs in-memory only; it MUST
    ///     NOT acquire a `sqlx::Pool` writer handle, and it MUST NOT plug
    ///     into `crate::canary_writer::*`. Replay-derived advisory rows go
    ///     through the `verify_replay_evidence_and_insert()` PL/pgSQL
    ///     function (Wave 3 R20-P2a-S4) instead, which is invoked by
    ///     `replay_routes.py` server-side, NOT by the replay binary.
    ///   - Other variants => `true`. They keep their existing writer path.
    ///
    /// 語意（中）：
    ///   - `Isolated` => `false`。runner 僅 in-memory 運行；不得取
    ///     `sqlx::Pool` writer handle，不得接入 `crate::canary_writer::*`。
    ///     Replay 衍生 advisory row 改走 `verify_replay_evidence_and_insert()`
    ///     PL/pgSQL function（Wave 3 R20-P2a-S4），由 server-side
    ///     `replay_routes.py` 呼叫，**不**由 replay binary 呼叫。
    ///   - 其餘 variant => `true`。維持既有 writer 路徑。
    pub fn allow_db_writer_channels(&self) -> bool {
        !matches!(self, ReplayProfile::Isolated)
    }

    /// Fail-closed runtime guard: the replay binary calls this on entry to
    /// refuse any non-Isolated profile.
    ///
    /// Fail-closed runtime guard：replay binary 在 entry 呼叫此方法以拒絕
    /// 任何 non-Isolated profile。
    ///
    /// Semantics (EN):
    ///   - `Isolated` => `Ok(())`.
    ///   - All other variants => `Err(WrongProfile { found })`. The caller
    ///     (`replay_runner::main`) is expected to `expect()`-panic on
    ///     `Err`, satisfying V3 §12 #10 (`replay_forbidden_wiring_fail_closed`):
    ///     forbidden path aborts run, NOT log-only.
    ///
    /// 語意（中）：
    ///   - `Isolated` => `Ok(())`。
    ///   - 其餘 variant => `Err(WrongProfile { found })`。caller
    ///     （`replay_runner::main`）預期對 `Err` `expect()`-panic，
    ///     滿足 V3 §12 #10（`replay_forbidden_wiring_fail_closed`）：
    ///     forbidden 路徑 abort run，**非** log-only。
    ///
    /// SAFETY / 不變量：
    ///   - This method is the only authoritative runtime gate on entry to
    ///     the replay binary. Any caller that bypasses this method violates
    ///     V3 §6.2.
    ///   - 此方法是 replay binary entry 唯一具權威性的 runtime gate。任何
    ///     繞過此方法的 caller 違反 V3 §6.2。
    pub fn fail_closed_assert_isolated(&self) -> Result<(), ReplayIsolationError> {
        if !matches!(self, ReplayProfile::Isolated) {
            return Err(ReplayIsolationError::WrongProfile { found: *self });
        }
        Ok(())
    }
}
