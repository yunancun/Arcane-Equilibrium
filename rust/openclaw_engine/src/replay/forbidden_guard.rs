//! REF-20 Wave 3 R20-P2b-S8 — Forbidden-path fail-closed guard.
//! REF-20 Wave 3 R20-P2b-S8 — Forbidden 路徑 fail-closed guard。
//!
//! MODULE_NOTE (EN):
//!   This module is the spec scaffold + minimal enforcement layer for the FULL
//!   V3 §6.2 forbidden-path list. Wave 3 P2b-S7 already covers the meta-surface
//!   (`profile == Isolated`); this module covers the seven concrete forbidden
//!   surfaces:
//!     1. Decision Lease acquire / release
//!     2. IPC server start (JSON-RPC pipeline to Python control_api_v1)
//!     3. WS client start (Bybit private/public WebSocket)
//!     4. Exchange dispatch (REST POST / order placement / cancel / amend)
//!     5. DB writer channel use (`canary_writer::write` / `database::writer`)
//!     6. Live/demo config mutation
//!     7. Advisory table write (`mlde_shadow_recommendations` / `replay.*` write
//!         outside the verified PL/pgSQL path)
//!
//!   Two-stage enforcement contract:
//!     - `enforce_at_startup()`  is called by `replay_runner::main` BEFORE any
//!         replay logic. It checks for evidence that the runtime state has
//!         already been polluted (env var set, cfg flag, magic file marker).
//!         If detected, panic via caller `.expect(...)`.
//!     - `enforce_at_runtime(action)` is the per-action gate Wave 4 R20-P2b-T1
//!         wrapper will call from inside the replay tick loop. Wave 3 lands the
//!         function signature + same minimal env/cfg/marker check (for unit
//!         testability); Wave 4 R20-P2b-T2 plugs in the actual interception
//!         points around `intent_processor::router`, `ipc_server::dispatch`,
//!         `bybit_rest_client::place_order`, etc.
//!
//!   Why minimal enforcement now (not full IPC/router interception):
//!     - Per Wave 3 P2b-S8 task spec, this is "spec scaffold + minimal
//!         enforcement (check env var + cfg flag + magic file marker)";
//!         "完整 IPC/dispatch/lease 攔截在 Wave 4 R20-P2b-T1 wrapper 加".
//!     - The replay_runner binary at Wave 3 has 0 import of `intent_processor`,
//!         `ipc_server`, `bybit_*`, `governance_hub`. Adding interception now
//!         would force imports that violate PA boundary allowlist §5 forbidden
//!         crate dependencies and the nm symbol audit (S10) would fail.
//!     - Wave 4 R20-P2b-T1 introduces the wrapper layer that mediates between
//!         the replay binary and (sandboxed) versions of these surfaces; that
//!         is where full interception belongs.
//!
//!   Detection mechanisms (all read-only, side-effect free):
//!     - Env var `OPENCLAW_REPLAY_FORBIDDEN_TRIPPED=<variant_name>`. Production
//!         callers do NOT set this; it exists for unit testing and the future
//!         Wave 4 wrapper to record a tripped state.
//!     - Magic file marker `<OPENCLAW_DATA_DIR>/replay_forbidden.tripped` whose
//!         single-line contents matches one of the 7 variant names. Same
//!         purpose as the env var; preferred when the future wrapper emits
//!         the trip-state from a sub-process that cannot mutate the parent
//!         environment.
//!     - Both are checked in deterministic order; if BOTH are set, the env var
//!         wins (lower latency to read; spec parity with how
//!         `manifest_signer::SecretSourceCascade` resolves env-then-file).
//!
//!   What does NOT count as a trip:
//!     - The strings appearing in source comments / module docs / TODO markers
//!         (these are deliberately excluded; the detector reads VALUES not
//!         source text).
//!     - Profile mismatch (covered by Wave 3 P2b-S7
//!         `fail_closed_assert_isolated`; if you reach here, `profile.rs` has
//!         already passed).
//!     - Mac S0/S1 read attempt (covered by Wave 3 P2b-S9 `mac_policy_guard`;
//!         orthogonal axis).
//!
//!   Cross-references:
//!     - SPEC: REF-20 V3 §3 G7/G8 + §6.2 forbidden list + §12 #10 acceptance
//!     - Workplan: docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md
//!         §4 Wave 3 R20-P2b-S8 row (V3 §12 #10 binding)
//!     - PA boundary allowlist:
//!         docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-03--replay_runner_crate_boundary_allowlist.md
//!         §4 allowed deps + §5 forbidden deps + §6 nm symbol allowlist
//!     - Sibling: `crate::replay::profile` (Wave 3 P2b-S7 cfg gate),
//!         `crate::replay::mac_policy_guard` (Wave 3 P2b-S9 Mac gate)
//!     - Acceptance tests: `tests/replay_forbidden_guard_acceptance.rs`
//!
//! MODULE_NOTE (中):
//!   本模組為 V3 §6.2 完整 forbidden-path 清單的 spec scaffold + minimal
//!   enforcement 層。Wave 3 P2b-S7 已蓋住 meta-surface（`profile == Isolated`）；
//!   本模組蓋住七個具體 forbidden surface：
//!     1. Decision Lease acquire / release
//!     2. IPC server 啟動（往 Python control_api_v1 的 JSON-RPC pipeline）
//!     3. WS client 啟動（Bybit private / public WebSocket）
//!     4. Exchange dispatch（REST POST / 下單 / cancel / amend）
//!     5. DB writer channel 使用（`canary_writer::write` / `database::writer`）
//!     6. Live / demo config mutate
//!     7. Advisory 表寫入（`mlde_shadow_recommendations` / `replay.*` 不走
//!         verified PL/pgSQL 的路徑）
//!
//!   兩階段 enforcement 契約：
//!     - `enforce_at_startup()` 由 `replay_runner::main` 在任何 replay 邏輯前
//!         呼叫。檢查 runtime state 是否已被污染（env var 設值、cfg flag、
//!         magic file marker）。若偵測到，由 caller `.expect(...)` panic。
//!     - `enforce_at_runtime(action)` 是 per-action gate；Wave 4 R20-P2b-T1
//!         wrapper 從 replay tick loop 內呼叫。Wave 3 落地 function signature
//!         + 同一套最小 env/cfg/marker 檢查（供 unit test 可行）；Wave 4
//!         R20-P2b-T2 才接入真正的 `intent_processor::router`、
//!         `ipc_server::dispatch`、`bybit_rest_client::place_order` 等
//!         interception 點。
//!
//!   為什麼現在 minimal enforcement 而非完整 IPC/router interception：
//!     - 依 Wave 3 P2b-S8 task spec：「本 Wave 3 是 spec scaffold + minimal
//!         enforcement（檢查 env var + cfg flag + magic file marker），完整
//!         IPC/dispatch/lease 攔截在 Wave 4 R20-P2b-T1 wrapper 加」。
//!     - Wave 3 的 replay_runner binary 對 `intent_processor` / `ipc_server` /
//!         `bybit_*` / `governance_hub` 的 import 數 = 0。現在加 interception
//!         會強制引入違反 PA boundary allowlist §5 的 forbidden crate
//!         dependencies，且 nm symbol audit（S10）會 fail。
//!     - Wave 4 R20-P2b-T1 引入 wrapper 層，介於 replay binary 與這些 surface
//!         的 sandboxed 版本之間 — 那才是完整 interception 的去處。
//!
//!   偵測機制（皆唯讀、無 side-effect）：
//!     - Env var `OPENCLAW_REPLAY_FORBIDDEN_TRIPPED=<variant_name>`。production
//!         caller **不**設此 var；存在純為 unit test 與未來 Wave 4 wrapper
//!         記錄 tripped state 用。
//!     - Magic file marker `<OPENCLAW_DATA_DIR>/replay_forbidden.tripped`，
//!         單行內容對應 7 variant name 之一。用途同 env var；當未來 wrapper
//!         由無法 mutate parent env 的 sub-process emit trip-state 時優先用。
//!     - 兩者依確定性順序檢查；若同時設值，env var 勝（read latency 低；與
//!         `manifest_signer::SecretSourceCascade` 的 env-then-file 解析 spec
//!         一致）。
//!
//!   不算 trip 的情況：
//!     - 字串出現在 source comment / module doc / TODO marker（這些刻意排除；
//!         detector 讀 VALUE 不讀 source text）。
//!     - Profile 不匹配（由 Wave 3 P2b-S7 `fail_closed_assert_isolated` 蓋住；
//!         若已執行到此處，`profile.rs` 已通過）。
//!     - Mac S0/S1 讀取嘗試（由 Wave 3 P2b-S9 `mac_policy_guard` 蓋住；屬
//!         正交軸）。
//!
//!   Cross-references：
//!     - SPEC：REF-20 V3 §3 G7/G8 + §6.2 forbidden list + §12 #10 acceptance
//!     - Workplan：docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md
//!         §4 Wave 3 R20-P2b-S8 row（V3 §12 #10 binding）
//!     - PA boundary allowlist：
//!         docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-03--replay_runner_crate_boundary_allowlist.md
//!         §4 allowed deps + §5 forbidden deps + §6 nm symbol allowlist
//!     - Sibling：`crate::replay::profile`（Wave 3 P2b-S7 cfg gate）、
//!         `crate::replay::mac_policy_guard`（Wave 3 P2b-S9 Mac gate）
//!     - Acceptance tests：`tests/replay_forbidden_guard_acceptance.rs`
//!
//! SPEC: REF-20 V3 §3 G7/G8 + §6.2 + §12 #10

use std::env;
use std::path::PathBuf;

// ─────────────────────────────────────────────────────────────────────────
// Public types / 公開型別
// ─────────────────────────────────────────────────────────────────────────

/// Runtime guard error covering V3 §6.2 forbidden-path list.
///
/// 對應 V3 §6.2 forbidden-path 清單的 runtime guard 錯誤型別。
///
/// Scope/作用域 (EN):
///   This enum is declared narrowly inside the `replay` subsystem (NOT plugged
///   into `crate::error::*` Live hot-path types). Each variant maps 1:1 to a
///   forbidden surface in V3 §6.2; adding a new forbidden surface requires
///   adding a variant here, the detection branch in
///   `current_trip_value()`, and an acceptance proof in
///   `tests/replay_forbidden_guard_acceptance.rs`.
///
/// Scope/作用域 (中)：
///   此 enum 刻意在 `replay` 子系統內窄宣告（**不**插入 `crate::error::*`
///   Live hot-path 型別）。每個 variant 對應 V3 §6.2 forbidden surface 1:1；
///   新增 forbidden surface 必同步新增 variant、`current_trip_value()` 的
///   偵測分支、與 `tests/replay_forbidden_guard_acceptance.rs` 的 acceptance
///   proof。
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ForbiddenPathError {
    /// Decision Lease was acquired (or release attempted). V3 §6.2 #1.
    /// Decision Lease 被取得（或試圖 release）。V3 §6.2 #1。
    AcquireLeaseDetected,

    /// JSON-RPC IPC server was started. V3 §6.2 #2.
    /// JSON-RPC IPC server 被啟動。V3 §6.2 #2。
    IpcServerStarted,

    /// Bybit private/public WebSocket client was started. V3 §6.2 #3.
    /// Bybit private / public WebSocket client 被啟動。V3 §6.2 #3。
    WsClientStarted,

    /// Exchange dispatch invoked (REST POST / order place/cancel/amend).
    /// V3 §6.2 #4 + V3 §12 #14.
    ///
    /// Exchange dispatch 被觸發（REST POST / 下單 / cancel / amend）。
    /// V3 §6.2 #4 + V3 §12 #14。
    ExchangeDispatchInvoked,

    /// DB writer channel (`canary_writer::write` / `database::writer`)
    /// invoked. V3 §6.2 #5 + V3 §4.2.
    ///
    /// DB writer channel（`canary_writer::write` / `database::writer`）被
    /// 觸發。V3 §6.2 #5 + V3 §4.2。
    DbWriterChannelInvoked,

    /// Live or demo config mutated. V3 §6.2 #6 + V3 §12 #14.
    /// Live 或 demo config 被 mutate。V3 §6.2 #6 + V3 §12 #14。
    LiveDemoConfigMutated,

    /// Advisory write (`mlde_shadow_recommendations` / `replay.*` write
    /// outside verified PL/pgSQL function). V3 §6.2 #7 + V3 §12 #6.
    ///
    /// Advisory 寫入（`mlde_shadow_recommendations` / `replay.*` 不走 verified
    /// PL/pgSQL function）。V3 §6.2 #7 + V3 §12 #6。
    AdvisoryWriteAttempted { source: String },
}

impl std::fmt::Display for ForbiddenPathError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::AcquireLeaseDetected => write!(
                f,
                "ForbiddenPathError::AcquireLeaseDetected — replay binary attempted \
                 Decision Lease acquire/release (V3 §6.2 #1)"
            ),
            Self::IpcServerStarted => write!(
                f,
                "ForbiddenPathError::IpcServerStarted — replay binary started \
                 JSON-RPC IPC server (V3 §6.2 #2)"
            ),
            Self::WsClientStarted => write!(
                f,
                "ForbiddenPathError::WsClientStarted — replay binary started \
                 Bybit private/public WS client (V3 §6.2 #3)"
            ),
            Self::ExchangeDispatchInvoked => write!(
                f,
                "ForbiddenPathError::ExchangeDispatchInvoked — replay binary \
                 invoked exchange dispatch (V3 §6.2 #4 + §12 #14)"
            ),
            Self::DbWriterChannelInvoked => write!(
                f,
                "ForbiddenPathError::DbWriterChannelInvoked — replay binary \
                 invoked DB writer channel (V3 §6.2 #5 + §4.2)"
            ),
            Self::LiveDemoConfigMutated => write!(
                f,
                "ForbiddenPathError::LiveDemoConfigMutated — replay binary \
                 mutated live/demo config (V3 §6.2 #6 + §12 #14)"
            ),
            Self::AdvisoryWriteAttempted { source } => write!(
                f,
                "ForbiddenPathError::AdvisoryWriteAttempted{{source={source}}} \
                 — replay binary attempted advisory write outside verified \
                 PL/pgSQL function (V3 §6.2 #7 + §12 #6)"
            ),
        }
    }
}

impl std::error::Error for ForbiddenPathError {}

// ─────────────────────────────────────────────────────────────────────────
// Internal helpers / 內部 helper
// ─────────────────────────────────────────────────────────────────────────

/// Env var name used to signal a tripped forbidden path.
/// Production callers do NOT set this; it exists for unit testing + Wave 4
/// wrapper `enforce_at_runtime` recording.
///
/// 用於發送「forbidden 路徑被觸發」訊號的 env var 名。production caller
/// **不**設此變數；存在純為 unit test 與 Wave 4 wrapper 的
/// `enforce_at_runtime` 記錄用。
pub const TRIP_ENV_VAR: &str = "OPENCLAW_REPLAY_FORBIDDEN_TRIPPED";

/// Magic file basename appended to `$OPENCLAW_DATA_DIR` to signal a tripped
/// forbidden path from a sub-process that cannot mutate parent env.
///
/// 由無法 mutate parent env 的 sub-process 用於發訊的 magic file basename，
/// 以 `$OPENCLAW_DATA_DIR` 拼接。
pub const TRIP_FILE_BASENAME: &str = "replay_forbidden.tripped";

/// Map a recorded trip-value string to its `ForbiddenPathError` variant.
///
/// 將記錄的 trip-value 字串映射到 `ForbiddenPathError` variant。
///
/// Recognition rules (EN):
///   - Trim whitespace. Empty string → `None` (treated as unset).
///   - Match the variant name (case-sensitive). Anything else → `None`
///     (treated as unset; this is fail-open by design — we ONLY trip on
///     known, deliberately-set variant names so a stray env var can't cause
///     spurious panic).
///   - `AdvisoryWriteAttempted` accepts an optional `:<source>` suffix
///     (e.g. `AdvisoryWriteAttempted:mlde_shadow_recommendations`). Empty
///     suffix → `source = "unknown"`.
///
/// 識別規則（中）：
///   - trim 空白。空字串 → `None`（視為未設）。
///   - case-sensitive match variant name；其他 → `None`（視為未設；fail-open
///     by design — 僅在已知、刻意設值的 variant name 才 trip，避免雜散 env
///     var 造成假 panic）。
///   - `AdvisoryWriteAttempted` 接受選用 `:<source>` 後綴
///     （例：`AdvisoryWriteAttempted:mlde_shadow_recommendations`）；空後綴
///     → `source = "unknown"`。
fn parse_trip_value(raw: &str) -> Option<ForbiddenPathError> {
    let trimmed = raw.trim();
    if trimmed.is_empty() {
        return None;
    }
    // Pattern: "VariantName" or "VariantName:source"
    // 模式：「VariantName」或「VariantName:source」
    let (variant, source_opt) = match trimmed.split_once(':') {
        Some((v, s)) => (v, Some(s)),
        None => (trimmed, None),
    };
    match variant {
        "AcquireLeaseDetected" => Some(ForbiddenPathError::AcquireLeaseDetected),
        "IpcServerStarted" => Some(ForbiddenPathError::IpcServerStarted),
        "WsClientStarted" => Some(ForbiddenPathError::WsClientStarted),
        "ExchangeDispatchInvoked" => Some(ForbiddenPathError::ExchangeDispatchInvoked),
        "DbWriterChannelInvoked" => Some(ForbiddenPathError::DbWriterChannelInvoked),
        "LiveDemoConfigMutated" => Some(ForbiddenPathError::LiveDemoConfigMutated),
        "AdvisoryWriteAttempted" => Some(ForbiddenPathError::AdvisoryWriteAttempted {
            source: source_opt
                .map(|s| s.trim().to_string())
                .filter(|s| !s.is_empty())
                .unwrap_or_else(|| "unknown".to_string()),
        }),
        _ => None,
    }
}

/// Read the magic-file marker contents at `<OPENCLAW_DATA_DIR>/replay_forbidden.tripped`.
///
/// 讀取 `<OPENCLAW_DATA_DIR>/replay_forbidden.tripped` magic file 內容。
///
/// Returns `None` when:
///   - `OPENCLAW_DATA_DIR` env var unset or empty.
///   - File does not exist.
///   - File exists but cannot be read (permissions / IO error).
///   - File content does not parse to a known variant (per `parse_trip_value`).
///
/// 回傳 `None` 時：
///   - `OPENCLAW_DATA_DIR` env var 未設或空。
///   - 檔案不存在。
///   - 檔案存在但無法讀（權限 / IO error）。
///   - 內容無法解析為已知 variant（見 `parse_trip_value`）。
fn read_trip_file() -> Option<ForbiddenPathError> {
    let data_dir = env::var("OPENCLAW_DATA_DIR").ok()?;
    if data_dir.trim().is_empty() {
        return None;
    }
    let path = PathBuf::from(data_dir).join(TRIP_FILE_BASENAME);
    let raw = std::fs::read_to_string(&path).ok()?;
    parse_trip_value(&raw)
}

/// Resolve current trip state from env-var first, then magic-file fallback.
///
/// 解析目前 trip 狀態，env-var 優先，magic-file 後備。
///
/// Resolution order (EN):
///   1. If `$OPENCLAW_REPLAY_FORBIDDEN_TRIPPED` is set to a known variant
///      string, return that variant.
///   2. Otherwise read `<OPENCLAW_DATA_DIR>/replay_forbidden.tripped`; if it
///      contains a known variant, return that variant.
///   3. Otherwise `None` (no trip detected → caller proceeds).
///
/// 解析順序（中）：
///   1. 若 `$OPENCLAW_REPLAY_FORBIDDEN_TRIPPED` 設為已知 variant 字串，回傳
///      該 variant。
///   2. 否則讀 `<OPENCLAW_DATA_DIR>/replay_forbidden.tripped`；若內容為已知
///      variant，回傳該 variant。
///   3. 否則 `None`（無 trip → caller 繼續）。
fn current_trip_value() -> Option<ForbiddenPathError> {
    if let Ok(raw) = env::var(TRIP_ENV_VAR) {
        if let Some(err) = parse_trip_value(&raw) {
            return Some(err);
        }
    }
    read_trip_file()
}

// ─────────────────────────────────────────────────────────────────────────
// Public API / 公開 API
// ─────────────────────────────────────────────────────────────────────────

/// Startup-phase fail-closed enforcement.
///
/// Startup 階段 fail-closed 強制。
///
/// Semantics (EN):
///   - Called by `replay_runner::main` BEFORE any replay logic begins.
///   - Returns `Ok(())` when no forbidden trip is recorded in env var nor
///     magic file marker (the production-default state).
///   - Returns `Err(ForbiddenPathError::*)` when either signal is set, naming
///     the surface that was tripped. The caller MUST `.expect(...)` panic so
///     the binary aborts before replay (V3 §12 #10:「forbidden path aborts
///     run, NOT log-only」).
///
/// 語意（中）：
///   - 由 `replay_runner::main` 在 replay 邏輯前呼叫。
///   - 回傳 `Ok(())` 當 env var 與 magic file marker 都未記錄 forbidden trip
///     （production 預設狀態）。
///   - 回傳 `Err(ForbiddenPathError::*)` 當任一訊號設值，並指明哪個 surface 被
///     觸發。caller 必須 `.expect(...)` panic，使 binary 在 replay 前 abort
///     （V3 §12 #10：「forbidden path aborts run, NOT log-only」）。
///
/// SAFETY / 不變量:
///   - This function is read-only on env + filesystem; it does NOT mutate any
///     state. Repeated calls are deterministic given fixed input.
///   - 本函式對 env + filesystem 唯讀；不 mutate 任何狀態。同一輸入下
///     重複呼叫結果確定。
///
/// SPEC: V3 §6.2 fail-closed behavior + V3 §12 #10 acceptance binding.
pub fn enforce_at_startup() -> Result<(), ForbiddenPathError> {
    match current_trip_value() {
        None => Ok(()),
        Some(err) => Err(err),
    }
}

/// Runtime-phase fail-closed enforcement (Wave 4 wiring slot).
///
/// Runtime 階段 fail-closed 強制（Wave 4 接線槽）。
///
/// Semantics (EN):
///   - Called from inside the replay tick loop by Wave 4 R20-P2b-T1 wrapper.
///   - The `action` parameter labels the call site (e.g. "acquire_lease",
///     "ipc_server_bind", "place_order"). Wave 3 uses this label only for
///     diagnostic logging purposes (the function's actual decision is driven
///     by the same env-var + magic-file machinery as `enforce_at_startup`).
///   - Wave 4 R20-P2b-T2 will replace the body with hard-coded interception
///     branches per `action` label (e.g. `match action { "acquire_lease" => ...}`)
///     that consult sibling crate state without flipping env vars.
///   - The signature is fixed in Wave 3 so Wave 4 wrapper code can be drafted
///     against it without re-locking the API.
///
/// 語意（中）：
///   - 由 Wave 4 R20-P2b-T1 wrapper 從 replay tick loop 內呼叫。
///   - `action` 參數標記 call site（例：「acquire_lease」、「ipc_server_bind」、
///     「place_order」）。Wave 3 僅用此 label 做診斷日誌（function 的實際
///     決策仍走與 `enforce_at_startup` 相同的 env-var + magic-file 機制）。
///   - Wave 4 R20-P2b-T2 將以針對 `action` label 的 hard-coded 攔截分支
///     （例：`match action { "acquire_lease" => ...}`）取代 body，
///     諮詢 sibling crate state，不靠翻 env var。
///   - signature 在 Wave 3 即固定，使 Wave 4 wrapper code 可先 draft 不必
///     重鎖 API。
///
/// SPEC: V3 §6.2 forbidden-path runtime detection contract.
pub fn enforce_at_runtime(action: &str) -> Result<(), ForbiddenPathError> {
    // Wave 3 minimal IMPL: same env+file detection as startup. Wave 4
    // R20-P2b-T1 will replace body with per-action interception logic.
    //
    // Wave 3 minimal IMPL：採用與 startup 相同的 env+file 偵測。Wave 4
    // R20-P2b-T1 將以 per-action 攔截邏輯取代 body。
    let _ = action; // future-use; suppress unused warning at Wave 3 baseline.
    match current_trip_value() {
        None => Ok(()),
        Some(err) => Err(err),
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Module-internal unit tests / 模組內部 unit test
//
// These are kept minimal and focused on parser internals; the contract-level
// acceptance proofs live in `tests/replay_forbidden_guard_acceptance.rs`
// (per V3 §12 #10 binding).
//
// 此處 test 著重於 parser 內部；契約層級 acceptance proof 在
// `tests/replay_forbidden_guard_acceptance.rs`（V3 §12 #10 binding）。
// ─────────────────────────────────────────────────────────────────────────
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_known_variants_matches_each_arm() {
        assert_eq!(
            parse_trip_value("AcquireLeaseDetected"),
            Some(ForbiddenPathError::AcquireLeaseDetected)
        );
        assert_eq!(
            parse_trip_value("IpcServerStarted"),
            Some(ForbiddenPathError::IpcServerStarted)
        );
        assert_eq!(
            parse_trip_value("WsClientStarted"),
            Some(ForbiddenPathError::WsClientStarted)
        );
        assert_eq!(
            parse_trip_value("ExchangeDispatchInvoked"),
            Some(ForbiddenPathError::ExchangeDispatchInvoked)
        );
        assert_eq!(
            parse_trip_value("DbWriterChannelInvoked"),
            Some(ForbiddenPathError::DbWriterChannelInvoked)
        );
        assert_eq!(
            parse_trip_value("LiveDemoConfigMutated"),
            Some(ForbiddenPathError::LiveDemoConfigMutated)
        );
    }

    #[test]
    fn parse_advisory_with_and_without_source() {
        // With source / 帶 source。
        assert_eq!(
            parse_trip_value("AdvisoryWriteAttempted:mlde_shadow"),
            Some(ForbiddenPathError::AdvisoryWriteAttempted {
                source: "mlde_shadow".to_string()
            })
        );
        // Without source defaults to "unknown" / 無 source 回 "unknown"。
        assert_eq!(
            parse_trip_value("AdvisoryWriteAttempted"),
            Some(ForbiddenPathError::AdvisoryWriteAttempted {
                source: "unknown".to_string()
            })
        );
        // Empty source after colon also defaults to "unknown".
        // 冒號後空 source 同樣回 "unknown"。
        assert_eq!(
            parse_trip_value("AdvisoryWriteAttempted:"),
            Some(ForbiddenPathError::AdvisoryWriteAttempted {
                source: "unknown".to_string()
            })
        );
    }

    #[test]
    fn parse_unknown_or_empty_returns_none() {
        // Empty + whitespace-only → None (unset).
        // 空 / 純空白 → None（視為未設）。
        assert_eq!(parse_trip_value(""), None);
        assert_eq!(parse_trip_value("   "), None);
        assert_eq!(parse_trip_value("\n\t"), None);
        // Unknown variant name → None (fail-open against stray env var).
        // 未知 variant name → None（對雜散 env var fail-open）。
        assert_eq!(parse_trip_value("Unrelated"), None);
        assert_eq!(parse_trip_value("acquireleasedetected"), None); // case-sensitive
    }
}
