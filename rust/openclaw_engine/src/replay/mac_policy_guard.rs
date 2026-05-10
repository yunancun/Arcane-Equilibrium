//! REF-20 Wave 3 R20-P2b-S9 — Mac fail-closed policy guard.
//! REF-20 Wave 3 R20-P2b-S9 — Mac fail-closed 政策 guard。
//!
//! MODULE_NOTE (EN):
//!   This module enforces V3 §6.3 Mac Policy. On macOS the replay binary may
//!   only run S2 public-data smoke and S3 synthetic smoke; it MUST NOT touch
//!   S0/S1 private runtime data, `trading.fills`, `learning.exit_features`,
//!   demo/live_demo fills, or local private orderbook captures (§6.3 #2-#4).
//!
//!   Wave 3 P2b-S9 lands the env-and-profile gate that the Wave 1/3 binary
//!   entry calls before any data load. Wave 4 R20-P2b-T2 will additionally
//!   guard each fixture loader call site, but the entry-point check here is
//!   already the authoritative "Mac cannot read private data" enforcement
//!   point (V3 §12 #12 binding).
//!
//!   Env-var contract (per Wave 2 dispatch §2 ambiguity #1, PM final):
//!     - Variable name: `OPENCLAW_REPLAY_MAC_NO_PRIVATE`
//!         (renamed from the longer `OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA`;
//!          the new 14-char name keeps semantic clarity — "NO_PRIVATE" =
//!          "fixture-only, no S0/S1/private data").
//!     - Production-default value (semantic): `"1"`. Operators on Mac MUST
//!         set this to `"1"` explicitly. The guard is fail-closed against
//!         absence; if the var is unset OR not equal to `"1"`, this module
//!         returns `EnvVarMissingOrZero` so the binary aborts. We do NOT
//!         silently treat absence as "assume `1`" because this is exactly the
//!         class of misconfiguration V3 §6.3 #7 forbids.
//!     - Recognised values: `"1"` (PASS) — anything else (`""`, `"0"`,
//!         `"true"`, mixed case, whitespace) returns `EnvVarMissingOrZero`.
//!
//!   Profile-vs-OS matrix:
//!
//! ```text
//!         OS           | profile        | result
//!         -------------|----------------|---------------------------
//!         macOS        | Isolated       | check ENV; Ok if "1"
//!         macOS        | non-Isolated   | RealDataAttemptedOnMac (regardless of ENV)
//!         non-macOS    | (any)          | Ok (this guard does not enforce on Linux)
//! ```
//!
//!   Why non-macOS is a no-op:
//!     - V3 §6.3 explicitly scopes the policy to Mac; Linux `linux_trade_core`
//!         is the SoT environment for actionable replay (§6.3 #6, §6.4
//!         baseline mechanism).
//!     - Wave 4 R20-P2b-T1 wrapper will add Linux-side checks for OTHER
//!         policies (e.g. baseline_source provenance); those belong in a
//!         sibling guard, not here.
//!     - The `OsNotMacButGuardActive` variant exists for caller-side audit:
//!         if a future caller wraps this guard inside a "mac-only" code path
//!         on the wrong host, the variant lets them surface that as a typed
//!         configuration error instead of silently no-op'ing.
//!
//!   Cross-references:
//!     - SPEC: REF-20 V3 §6.3 + §12 #12 acceptance binding
//!     - Workplan: docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md
//!         §4 Wave 3 R20-P2b-S9 row
//!     - Wave 2 dispatch §2 ambiguity #1: env var rename to
//!         `OPENCLAW_REPLAY_MAC_NO_PRIVATE`
//!     - PA boundary allowlist:
//!         docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-03--replay_runner_crate_boundary_allowlist.md
//!     - Sibling: `crate::replay::profile` (Wave 3 P2b-S7 cfg gate),
//!         `crate::replay::forbidden_guard` (Wave 3 P2b-S8 fail-closed list)
//!     - Acceptance tests: `tests/replay_mac_policy_acceptance.rs`
//!
//! MODULE_NOTE (中):
//!   本模組強制 V3 §6.3 Mac 政策。在 macOS 上 replay binary 僅可跑 S2
//!   public-data smoke 與 S3 synthetic smoke；不得碰 S0/S1 private runtime
//!   data、`trading.fills`、`learning.exit_features`、demo/live_demo fills，
//!   或本地 private orderbook captures（§6.3 #2-#4）。
//!
//!   Wave 3 P2b-S9 落地 env-and-profile gate，Wave 1/3 binary entry 在任何
//!   資料載入前呼叫。Wave 4 R20-P2b-T2 將額外於每個 fixture loader call site
//!   加 guard；但本處的 entry-point 檢查已是「Mac 不得讀 private data」之
//!   權威 enforcement 點（V3 §12 #12 binding）。
//!
//!   Env-var 契約（依 Wave 2 dispatch §2 ambiguity #1, PM final）：
//!     - 變數名：`OPENCLAW_REPLAY_MAC_NO_PRIVATE`
//!         （由較長的 `OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA` 改名；新名 14
//!          字保留語意清晰 — "NO_PRIVATE" = "fixture-only，不含 S0/S1/private
//!          data"）。
//!     - production 預設值（語意）：`"1"`。Mac 上 operator 必顯式設為 `"1"`。
//!         本 guard 對「不存在」fail-closed；若 var 未設**或** 非 `"1"`，本
//!         模組回傳 `EnvVarMissingOrZero`，使 binary abort。我們**不**靜默
//!         地把 absent 當 「假設 `1`」處理 — 這正是 V3 §6.3 #7 所禁的 misconfig
//!         class。
//!     - 認可值：`"1"`（PASS）— 其他（`""`、`"0"`、`"true"`、大小寫混合、
//!         空白）一律回 `EnvVarMissingOrZero`。
//!
//!   Profile-vs-OS 矩陣：
//!
//! ```text
//!         OS           | profile        | 結果
//!         -------------|----------------|---------------------------
//!         macOS        | Isolated       | 檢查 ENV；"1" 則 Ok
//!         macOS        | non-Isolated   | RealDataAttemptedOnMac（不論 ENV）
//!         non-macOS    | (任何)         | Ok（本 guard 在 Linux 不 enforce）
//! ```
//!
//!   為何 non-macOS no-op：
//!     - V3 §6.3 顯式將政策限於 Mac；Linux `linux_trade_core` 是 actionable
//!         replay 的 SoT 環境（§6.3 #6、§6.4 baseline mechanism）。
//!     - Wave 4 R20-P2b-T1 wrapper 會加 Linux 端的 OTHER 政策檢查（例：
//!         baseline_source provenance）；那些屬 sibling guard，不在此處。
//!     - `OsNotMacButGuardActive` variant 存在供 caller-side audit：若未來
//!         caller 把本 guard 包在錯主機上的「mac-only」code path 內，該
//!         variant 讓 caller 將之 surface 成具型別 configuration error，
//!         而非靜默 no-op。
//!
//!   Cross-references：
//!     - SPEC：REF-20 V3 §6.3 + §12 #12 acceptance binding
//!     - Workplan：docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md
//!         §4 Wave 3 R20-P2b-S9 row
//!     - Wave 2 dispatch §2 ambiguity #1：env var 改名為
//!         `OPENCLAW_REPLAY_MAC_NO_PRIVATE`
//!     - PA boundary allowlist：
//!         docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-03--replay_runner_crate_boundary_allowlist.md
//!     - Sibling：`crate::replay::profile`（Wave 3 P2b-S7 cfg gate）、
//!         `crate::replay::forbidden_guard`（Wave 3 P2b-S8 fail-closed list）
//!     - Acceptance tests：`tests/replay_mac_policy_acceptance.rs`
//!
//! SPEC: REF-20 V3 §6.3 + §12 #12

use std::env;

use crate::replay::profile::ReplayProfile;

// ─────────────────────────────────────────────────────────────────────────
// Public types / 公開型別
// ─────────────────────────────────────────────────────────────────────────

/// Mac policy guard error.
///
/// Mac 政策 guard 錯誤型別。
///
/// Scope/作用域 (EN):
///   This enum is declared narrowly inside the `replay` subsystem; it does
///   NOT plug into `crate::error::*` Live hot-path types. The three variants
///   make the failure mode unambiguous so the caller can route audit log
///   accordingly:
///     - `RealDataAttemptedOnMac` — non-Isolated profile run on macOS host;
///         this is the V3 §6.3 #2/#3 violation class.
///     - `EnvVarMissingOrZero` — `OPENCLAW_REPLAY_MAC_NO_PRIVATE` not set or
///         not equal to `"1"`; payload carries `var_name` (always
///         `OPENCLAW_REPLAY_MAC_NO_PRIVATE` per Wave 2 dispatch §2 #1) and
///         `value` (Some/None) so the caller can distinguish unset from
///         mis-set in audit log.
///     - `OsNotMacButGuardActive` — guard invoked on a non-macOS host where
///         the caller expected mac. Wave 3 returns `Ok` on non-macOS by
///         design, so this variant is reserved for callers who explicitly
///         opt into "fail if not on mac" semantics (e.g. test fixture sanity
///         check); production `enforce()` does NOT emit this variant.
///
/// Scope/作用域 (中)：
///   此 enum 刻意在 `replay` 子系統內窄宣告；**不**插入 `crate::error::*`
///   Live hot-path 型別。三個 variant 讓失敗 mode 明確，供 caller 對應路由
///   audit log：
///     - `RealDataAttemptedOnMac` — macOS host 上跑 non-Isolated profile；
///         此屬 V3 §6.3 #2/#3 違規類。
///     - `EnvVarMissingOrZero` — `OPENCLAW_REPLAY_MAC_NO_PRIVATE` 未設或
///         不等於 `"1"`；payload 攜帶 `var_name`（依 Wave 2 dispatch §2 #1
///         必為 `OPENCLAW_REPLAY_MAC_NO_PRIVATE`）與 `value`（Some/None），
///         供 caller 在 audit log 區分 「未設」vs「誤設」。
///     - `OsNotMacButGuardActive` — guard 被呼叫於非 macOS host，但 caller
///         預期 mac。Wave 3 在 non-macOS 預設回 `Ok`；本 variant 保留供
///         顯式選用「不在 mac 上就 fail」語意的 caller（例：test fixture
///         sanity check）；production 的 `enforce()` **不**發此 variant。
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum MacPolicyError {
    /// Non-Isolated profile attempted on macOS host. V3 §6.3 #2/#3.
    /// macOS host 上嘗試 non-Isolated profile。V3 §6.3 #2/#3。
    RealDataAttemptedOnMac { found_profile: ReplayProfile },

    /// `OPENCLAW_REPLAY_MAC_NO_PRIVATE` env var unset or not `"1"`.
    /// V3 §6.3 #7 + Wave 2 dispatch §2 #1.
    ///
    /// `OPENCLAW_REPLAY_MAC_NO_PRIVATE` env var 未設或非 `"1"`。
    /// V3 §6.3 #7 + Wave 2 dispatch §2 #1。
    EnvVarMissingOrZero {
        var_name: String,
        value: Option<String>,
    },

    /// Edge case: guard invoked but host is not macOS. Wave 3 production
    /// `enforce()` returns `Ok` here; this variant is reserved for opt-in
    /// strict callers.
    ///
    /// 邊界情況：guard 被呼叫但 host 非 macOS。Wave 3 production `enforce()`
    /// 此情況回 `Ok`；本 variant 保留供選用嚴格模式的 caller。
    OsNotMacButGuardActive,
}

impl std::fmt::Display for MacPolicyError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::RealDataAttemptedOnMac { found_profile } => write!(
                f,
                "MacPolicyError::RealDataAttemptedOnMac{{found_profile={:?}}} \
                 — replay binary running non-Isolated profile on macOS host \
                 violates V3 §6.3 #2/#3",
                found_profile
            ),
            Self::EnvVarMissingOrZero { var_name, value } => write!(
                f,
                "MacPolicyError::EnvVarMissingOrZero{{var_name=\"{}\", \
                 value={:?}}} — operator must set {}=1 explicitly on macOS \
                 (V3 §6.3 #7 + Wave 2 dispatch §2 #1)",
                var_name, value, var_name
            ),
            Self::OsNotMacButGuardActive => write!(
                f,
                "MacPolicyError::OsNotMacButGuardActive — Mac policy guard \
                 invoked on non-macOS host (informational; production \
                 enforce() returns Ok here)"
            ),
        }
    }
}

impl std::error::Error for MacPolicyError {}

// ─────────────────────────────────────────────────────────────────────────
// Constants / 常數
// ─────────────────────────────────────────────────────────────────────────

/// Env var name for the Mac fail-closed switch.
///
/// Mac fail-closed 開關的 env var 名。
///
/// Per Wave 2 dispatch §2 ambiguity #1 (PM final): the long original name
/// `OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA` is renamed to the 14-char
/// `OPENCLAW_REPLAY_MAC_NO_PRIVATE`. Codebase grep MUST show 0 hit of the
/// old name.
///
/// 依 Wave 2 dispatch §2 ambiguity #1（PM final）：較長的原名
/// `OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA` 改為 14 字
/// `OPENCLAW_REPLAY_MAC_NO_PRIVATE`。codebase grep 必為 0 hit 舊名。
pub const ENV_VAR_NAME: &str = "OPENCLAW_REPLAY_MAC_NO_PRIVATE";

/// The single accepted value for `ENV_VAR_NAME`.
/// Anything else (empty, `"0"`, `"true"`, mixed case, whitespace) is rejected.
///
/// `ENV_VAR_NAME` 的唯一認可值。其他（空、`"0"`、`"true"`、大小寫混合、
/// 空白）一律拒絕。
pub const ENV_VAR_REQUIRED_VALUE: &str = "1";

// ─────────────────────────────────────────────────────────────────────────
// Internal helpers / 內部 helper
// ─────────────────────────────────────────────────────────────────────────

/// `cfg!(target_os = "macos")` indirection so unit tests can reason about it
/// without `#[cfg]` attribute proliferation in the test bodies.
///
/// `cfg!(target_os = "macos")` 的間接層，讓 unit test 推理時不必在 test body
/// 散布 `#[cfg]` attribute。
#[inline]
fn host_is_macos() -> bool {
    cfg!(target_os = "macos")
}

/// Read `ENV_VAR_NAME` and decide whether the operator opted into fail-closed.
///
/// 讀 `ENV_VAR_NAME`，判定 operator 是否已選入 fail-closed。
///
/// Returns `Ok(())` when the var equals `"1"` (exact match, no trim).
/// Returns `Err(EnvVarMissingOrZero{...})` otherwise; the payload preserves
/// whether the env var was unset (`value = None`) or set to a non-`"1"`
/// value (`value = Some(...)`) for audit-log discrimination.
///
/// var 等於 `"1"`（精確比對，不 trim）時回 `Ok(())`。否則回
/// `Err(EnvVarMissingOrZero{...})`；payload 保留 env var 未設（`value = None`）
/// 或設為非 `"1"`（`value = Some(...)`）供 audit log 區分。
fn require_env_one() -> Result<(), MacPolicyError> {
    match env::var(ENV_VAR_NAME) {
        Ok(v) if v == ENV_VAR_REQUIRED_VALUE => Ok(()),
        Ok(v) => Err(MacPolicyError::EnvVarMissingOrZero {
            var_name: ENV_VAR_NAME.to_string(),
            value: Some(v),
        }),
        Err(_) => Err(MacPolicyError::EnvVarMissingOrZero {
            var_name: ENV_VAR_NAME.to_string(),
            value: None,
        }),
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Public API / 公開 API
// ─────────────────────────────────────────────────────────────────────────

/// Enforce V3 §6.3 Mac policy.
///
/// 強制 V3 §6.3 Mac 政策。
///
/// Behavior matrix (EN):
///   - Host is macOS:
///       1. If `profile != ReplayProfile::Isolated` → return
///          `Err(RealDataAttemptedOnMac { found_profile })`. Profile mismatch
///          subsumes any ENV check; we report the mismatch first so audit log
///          captures the strongest violation.
///       2. Else, require `OPENCLAW_REPLAY_MAC_NO_PRIVATE=1`. If unset or not
///          equal to `"1"` → return `Err(EnvVarMissingOrZero{...})`.
///       3. Else, return `Ok(())`.
///   - Host is NOT macOS:
///       Return `Ok(())` unconditionally. V3 §6.3 scopes the policy to Mac;
///       Linux runs are governed by other guards (Wave 4 R20-P2b-T1).
///
/// Behavior matrix (中)：
///   - Host 為 macOS：
///       1. 若 `profile != ReplayProfile::Isolated` → 回
///          `Err(RealDataAttemptedOnMac { found_profile })`。Profile 不匹配
///          先於 ENV 檢查；我們先報 mismatch 使 audit log 抓到最強違規。
///       2. 否則必 `OPENCLAW_REPLAY_MAC_NO_PRIVATE=1`。未設或不等於 `"1"`
///          → 回 `Err(EnvVarMissingOrZero{...})`。
///       3. 否則回 `Ok(())`。
///   - Host 非 macOS：
///       無條件回 `Ok(())`。V3 §6.3 將政策限於 Mac；Linux 由其他 guard
///       管轄（Wave 4 R20-P2b-T1）。
///
/// SAFETY / 不變量:
///   - This function reads `cfg!(target_os = "macos")` at compile time + reads
///     env::var at runtime. It does NOT mutate state. Caller must ensure no
///     concurrent thread mutates the env var during enforce.
///   - 本函式於 compile time 讀 `cfg!(target_os = "macos")` + 於 runtime 讀
///     env::var。不 mutate state。caller 必須確保 enforce 期間無其他 thread
///     mutate env var。
///
/// SPEC: V3 §6.3 fail-closed semantic + V3 §12 #12 acceptance binding.
pub fn enforce(profile: ReplayProfile) -> Result<(), MacPolicyError> {
    if !host_is_macos() {
        // V3 §6.3 scopes policy to Mac; non-macOS callers pass through.
        // V3 §6.3 將政策限於 Mac；非 macOS caller passthrough。
        return Ok(());
    }

    // macOS host: profile mismatch wins over ENV check (audit log priority).
    // macOS host：profile 不匹配優先於 ENV 檢查（audit log 優先順序）。
    if !matches!(profile, ReplayProfile::Isolated) {
        return Err(MacPolicyError::RealDataAttemptedOnMac {
            found_profile: profile,
        });
    }

    // Profile is Isolated; now require explicit operator opt-in via ENV.
    // Profile 為 Isolated；接著要求 operator 透過 ENV 顯式選入。
    require_env_one()
}

// ─────────────────────────────────────────────────────────────────────────
// Module-internal unit tests / 模組內部 unit test
//
// Acceptance proofs covering host_is_macos branching live in
// `tests/replay_mac_policy_acceptance.rs` (V3 §12 #12 binding). These tests
// only assert on parser internals + static facts that don't depend on host OS.
//
// 涵蓋 host_is_macos 分支的 acceptance proof 在
// `tests/replay_mac_policy_acceptance.rs`（V3 §12 #12 binding）。此處僅 assert
// 不依 host OS 的 parser 內部與靜態事實。
// ─────────────────────────────────────────────────────────────────────────
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn env_var_name_matches_dispatch_decision_renamed_form() {
        // 14-char short name decided in Wave 2 dispatch §2 #1.
        // Wave 2 dispatch §2 #1 決定的 14 字短名。
        assert_eq!(ENV_VAR_NAME, "OPENCLAW_REPLAY_MAC_NO_PRIVATE");
        assert_eq!(ENV_VAR_NAME.len(), 30); // length of the var_name string itself
    }

    #[test]
    fn required_value_is_string_one() {
        assert_eq!(ENV_VAR_REQUIRED_VALUE, "1");
    }

    #[test]
    fn old_var_name_grep_self_check() {
        // Hard guard against drift: the old long name MUST NOT appear as a
        // string constant anywhere in this module's source-visible API. We
        // can't grep at compile-time, but we assert the shorter constant is
        // exactly the new name, which is the contract.
        //
        // 防漂移硬 guard：舊長名不得作為字串常數出現於本模組 source-visible API。
        // 編譯期無法 grep，但 assert 較短常數恰為新名 — 即契約本身。
        let constant = ENV_VAR_NAME;
        assert!(!constant.contains("FORBID_REAL_DATA"));
        assert!(constant.contains("NO_PRIVATE"));
    }
}
