//! REF-20 Wave 3 R20-P2b-S9 — `mac_policy_guard` acceptance proofs.
//! REF-20 Wave 3 R20-P2b-S9 — `mac_policy_guard` acceptance 證明。
//!
//! MODULE_NOTE (EN):
//!   This integration test enumerates 4 acceptance proofs for the V3 §6.3
//!   Mac fail-closed policy gate (per workplan §4 Wave 3 R20-P2b-S9 row +
//!   V3 §12 #12 binding).
//!
//!   The four proofs:
//!     1. macOS host + ENV var unset → returns
//!        `EnvVarMissingOrZero { value: None }`. Operator must explicitly
//!        opt into fail-closed (V3 §6.3 #7).
//!     2. macOS host + ENV var = "1" + profile = Isolated → returns
//!        `Ok(())`. The production-default success path on Mac.
//!     3. macOS host + ENV var = "1" + profile = Live → returns
//!        `RealDataAttemptedOnMac`. Profile mismatch wins over ENV check
//!        (audit log priority; non-Isolated profiles can never run on Mac
//!        regardless of ENV).
//!     4. Non-macOS host (cfg!(not(target_os = "macos"))) → returns
//!        `Ok(())` regardless of ENV value. V3 §6.3 scopes the policy to
//!        Mac; Linux runs are governed by other guards.
//!
//!   Conditional compilation note:
//!     - Proofs 1/2/3 are Mac-only (gated `#[cfg(target_os = "macos")]`).
//!       On Linux CI runs they compile-out and contribute 0 test cases.
//!     - Proof 4 is non-Mac-only (gated `#[cfg(not(target_os = "macos"))]`).
//!       On Mac CI runs it compiles-out.
//!     - The cross-platform test count therefore differs by host but the
//!       contract is fully covered by the union of macOS + Linux runs (CI
//!       matrix runs both). Cargo on Mac dev gives 1 PASS (proof 4 is
//!       absent); Linux CI gives 1 PASS (proofs 1/2/3 are absent). On a
//!       single host it is impossible to test both branches because
//!       `cfg!(target_os)` resolves at compile time.
//!     - Wave 2 dispatch §2 #5 (PM final): macOS PRIMARY, Linux SECONDARY
//!       CI runner. CI matrix MUST include both for full coverage.
//!
//!   ENV var serial-mutation safety:
//!     - Tests in this file mutate `OPENCLAW_REPLAY_MAC_NO_PRIVATE` env
//!       var. Same pattern as `replay_forbidden_guard_acceptance.rs`:
//!       acquire `Mutex` + `EnvVarRestore` RAII helper.
//!
//! MODULE_NOTE (中):
//!   本整合測試列舉 V3 §6.3 Mac fail-closed 政策 gate 的 4 個 acceptance proof
//!   （依 workplan §4 Wave 3 R20-P2b-S9 row + V3 §12 #12 binding）。
//!
//!   四個 proof：
//!     1. macOS host + ENV var 未設 → 回 `EnvVarMissingOrZero { value: None }`。
//!        Operator 必顯式選入 fail-closed（V3 §6.3 #7）。
//!     2. macOS host + ENV var = "1" + profile = Isolated → 回 `Ok(())`。
//!        Mac 上的 production 預設成功路徑。
//!     3. macOS host + ENV var = "1" + profile = Live → 回
//!        `RealDataAttemptedOnMac`。Profile 不匹配優先於 ENV 檢查（audit log
//!        優先順序；non-Isolated profile 不論 ENV 永不可在 Mac 上跑）。
//!     4. 非 macOS host（cfg!(not(target_os = "macos"))）→ 不論 ENV 值皆回
//!        `Ok(())`。V3 §6.3 將政策限於 Mac；Linux 由其他 guard 管轄。
//!
//!   條件編譯註記：
//!     - Proof 1/2/3 為 Mac 專屬（`#[cfg(target_os = "macos")]`）。Linux CI run
//!       時編譯排除，0 test case。
//!     - Proof 4 為非 Mac 專屬（`#[cfg(not(target_os = "macos"))]`）。Mac CI
//!       run 時編譯排除。
//!     - 跨平台 test 數因 host 不同；契約完整覆蓋 = macOS + Linux run 的聯集
//!       （CI matrix 兩者都跑）。Mac dev 上 cargo 給 1 PASS（proof 4 缺）；
//!       Linux CI 給 1 PASS（proof 1/2/3 缺）。單一 host 無法 test 兩分支，
//!       因 `cfg!(target_os)` 於 compile time 解析。
//!     - Wave 2 dispatch §2 #5（PM final）：macOS PRIMARY、Linux SECONDARY
//!       CI runner。CI matrix 必含兩者方能完整覆蓋。
//!
//!   ENV var serial-mutation 安全性：
//!     - 本檔 test mutate `OPENCLAW_REPLAY_MAC_NO_PRIVATE` env var。模式與
//!       `replay_forbidden_guard_acceptance.rs` 相同：取 `Mutex` +
//!       `EnvVarRestore` RAII helper。
//!
//! Run / 執行:
//!   `cargo test -p openclaw_engine --features replay_isolated --test replay_mac_policy_acceptance -- --nocapture`

use std::env;
use std::sync::{Mutex, OnceLock};

use openclaw_engine::replay::mac_policy_guard::{
    self, MacPolicyError, ENV_VAR_NAME, ENV_VAR_REQUIRED_VALUE,
};
use openclaw_engine::replay::profile::ReplayProfile;

// ─────────────────────────────────────────────────────────────────────────
// Serial-mutation guard / 序列化 mutate 守衛
// ─────────────────────────────────────────────────────────────────────────

fn env_lock() -> &'static Mutex<()> {
    static LOCK: OnceLock<Mutex<()>> = OnceLock::new();
    LOCK.get_or_init(|| Mutex::new(()))
}

struct EnvVarRestore {
    name: &'static str,
    original: Option<String>,
}

impl EnvVarRestore {
    fn capture(name: &'static str) -> Self {
        Self {
            name,
            original: env::var(name).ok(),
        }
    }
}

impl Drop for EnvVarRestore {
    fn drop(&mut self) {
        // SAFETY: env mutation is single-threaded under env_lock() acquired
        // by the test that constructed this guard.
        // SAFETY：本 guard 由持有 env_lock() 的 test 構造，env mutate 為單執行緒。
        unsafe {
            match &self.original {
                Some(v) => env::set_var(self.name, v),
                None => env::remove_var(self.name),
            }
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Mac-only proofs (1/2/3)
// ─────────────────────────────────────────────────────────────────────────

/// Proof 1 (macOS) — ENV unset → EnvVarMissingOrZero { value: None }.
///
/// V3 §6.3 #7 fail-closed acceptance: operator must explicitly set
/// `OPENCLAW_REPLAY_MAC_NO_PRIVATE=1` on Mac.
#[cfg(target_os = "macos")]
#[test]
fn proof_1_mac_env_unset_fails_closed() {
    let _g = env_lock().lock().unwrap_or_else(|e| e.into_inner());
    let _restore = EnvVarRestore::capture(ENV_VAR_NAME);

    // SAFETY: env_lock acquired; single-threaded mutation.
    unsafe {
        env::remove_var(ENV_VAR_NAME);
    }

    let result = mac_policy_guard::enforce(ReplayProfile::Isolated);
    match result {
        Err(MacPolicyError::EnvVarMissingOrZero { var_name, value }) => {
            assert_eq!(var_name, ENV_VAR_NAME);
            assert!(
                value.is_none(),
                "ENV unset must produce value=None, got {:?}",
                value
            );
        }
        other => panic!(
            "expected EnvVarMissingOrZero{{value:None}}, got {:?}",
            other
        ),
    }
}

/// Proof 2 (macOS) — ENV="1" + profile=Isolated → Ok(()).
///
/// V3 §6.3 production-default success path on Mac.
#[cfg(target_os = "macos")]
#[test]
fn proof_2_mac_env_one_isolated_ok() {
    let _g = env_lock().lock().unwrap_or_else(|e| e.into_inner());
    let _restore = EnvVarRestore::capture(ENV_VAR_NAME);

    // SAFETY: env_lock acquired; single-threaded mutation.
    unsafe {
        env::set_var(ENV_VAR_NAME, ENV_VAR_REQUIRED_VALUE);
    }

    let result = mac_policy_guard::enforce(ReplayProfile::Isolated);
    assert!(
        result.is_ok(),
        "ENV={} + profile=Isolated must pass on macOS, got {:?}",
        ENV_VAR_REQUIRED_VALUE,
        result
    );
}

/// Proof 3 (macOS) — ENV="1" + profile=Live → RealDataAttemptedOnMac.
///
/// V3 §6.3 #2/#3: Mac may not run non-Isolated profiles regardless of ENV.
/// Profile mismatch is reported BEFORE the ENV check (audit-log priority).
#[cfg(target_os = "macos")]
#[test]
fn proof_3_mac_env_one_live_fails_real_data() {
    let _g = env_lock().lock().unwrap_or_else(|e| e.into_inner());
    let _restore = EnvVarRestore::capture(ENV_VAR_NAME);

    // SAFETY: env_lock acquired; single-threaded mutation.
    unsafe {
        env::set_var(ENV_VAR_NAME, ENV_VAR_REQUIRED_VALUE);
    }

    let result = mac_policy_guard::enforce(ReplayProfile::Live);
    match result {
        Err(MacPolicyError::RealDataAttemptedOnMac { found_profile }) => {
            assert_eq!(
                found_profile,
                ReplayProfile::Live,
                "found_profile payload must match the caller's profile"
            );
        }
        other => panic!("expected RealDataAttemptedOnMac, got {:?}", other),
    }

    // Sanity: also verify LiveDemo and PaperLegacy fail with the same variant.
    // 完整性：同樣驗 LiveDemo 與 PaperLegacy 走相同 variant。
    for &profile in &[ReplayProfile::LiveDemo, ReplayProfile::PaperLegacy] {
        let r = mac_policy_guard::enforce(profile);
        match r {
            Err(MacPolicyError::RealDataAttemptedOnMac { found_profile }) => {
                assert_eq!(found_profile, profile);
            }
            other => panic!(
                "expected RealDataAttemptedOnMac for {:?}, got {:?}",
                profile, other
            ),
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Non-Mac proof (4)
// ─────────────────────────────────────────────────────────────────────────

/// Proof 4 (non-macOS) — ENV irrelevant; all profiles return Ok(()).
///
/// V3 §6.3 scopes the Mac policy to Mac. Linux runs are governed by other
/// guards (Wave 4 R20-P2b-T1). This proof verifies the non-Mac passthrough
/// path on Linux/other CI runners.
#[cfg(not(target_os = "macos"))]
#[test]
fn proof_4_non_mac_passthrough() {
    let _g = env_lock().lock().unwrap_or_else(|e| e.into_inner());
    let _restore = EnvVarRestore::capture(ENV_VAR_NAME);

    // ENV unset / set to "1" / set to anything — all should pass on non-Mac.
    // ENV 未設 / 設為 "1" / 設為任何值 — 非 Mac 上皆應 pass。
    let env_states: &[Option<&str>] = &[None, Some("1"), Some("0"), Some("any")];

    for state in env_states {
        // SAFETY: env_lock acquired; single-threaded mutation.
        unsafe {
            match state {
                None => env::remove_var(ENV_VAR_NAME),
                Some(v) => env::set_var(ENV_VAR_NAME, v),
            }
        }
        // Try every profile variant on non-Mac.
        // 非 Mac 上對每個 profile variant 試一次。
        for &profile in &[
            ReplayProfile::Isolated,
            ReplayProfile::Live,
            ReplayProfile::LiveDemo,
            ReplayProfile::PaperLegacy,
        ] {
            let result = mac_policy_guard::enforce(profile);
            assert!(
                result.is_ok(),
                "non-macOS host with profile={:?}, ENV={:?} must return Ok(()), got {:?}",
                profile,
                state,
                result
            );
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Cross-platform invariants (always run)
// ─────────────────────────────────────────────────────────────────────────

/// Const-export invariant — ENV name MUST be the renamed 14-word form per
/// Wave 2 dispatch §2 #1 (PM final). This proof runs on EVERY host so the
/// rename can never silently regress.
///
/// V3 §12 #12 + Wave 2 dispatch §2 #1 alignment.
#[test]
fn cross_platform_const_export_uses_renamed_env_var() {
    assert_eq!(ENV_VAR_NAME, "OPENCLAW_REPLAY_MAC_NO_PRIVATE");
    assert_eq!(ENV_VAR_REQUIRED_VALUE, "1");
    // Hard guard: old long name must not appear.
    // 硬 guard：舊長名不得出現。
    assert!(!ENV_VAR_NAME.contains("FORBID_REAL_DATA"));
}
