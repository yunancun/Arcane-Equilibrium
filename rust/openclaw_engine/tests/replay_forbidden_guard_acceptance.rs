//! REF-20 Wave 3 R20-P2b-S8 — `forbidden_guard` acceptance proofs.
//! REF-20 Wave 3 R20-P2b-S8 — `forbidden_guard` acceptance 證明。
//!
//! MODULE_NOTE (EN):
//!   This integration test enumerates 4 acceptance proofs for the V3 §6.2
//!   forbidden-path enforcement layer (per workplan §4 Wave 3 R20-P2b-S8 row
//!   + V3 §12 #10 binding).
//!
//!   The four proofs:
//!     1. `enforce_at_startup()` returns `Ok(())` on a clean state (no env
//!        var trip + no magic-file trip). This is the production-default
//!        path the `replay_runner` binary takes.
//!     2. Setting the trip env var to a known forbidden variant name
//!        causes `enforce_at_startup()` to return the corresponding
//!        `ForbiddenPathError::*` variant.
//!     3. `enforce_at_runtime("acquire_lease")` returns the same trip
//!        result as `enforce_at_startup()`. Wave 3 minimal IMPL: the
//!        per-action gate uses identical env+file detection; Wave 4
//!        R20-P2b-T1 will replace the body with hard-coded interception
//!        branches per `action` label.
//!     4. The 7 enum variants in `ForbiddenPathError` align 1:1 with V3 §6.2
//!        forbidden surfaces. We exhaustively `match` so the compiler will
//!        reject any future variant addition that is not also reflected
//!        here, preventing silent contract drift.
//!
//!   ENV var serial-mutation safety:
//!     - Tests in this file mutate process env vars to construct trip-state
//!       fixtures. To avoid race conditions with sibling tests in the same
//!       file (cargo test runs tests within a file in parallel by default),
//!       each test acquires a single shared `Mutex` before mutating env, and
//!       restores the original value (or unsets) on Drop via an
//!       `EnvVarRestore` RAII helper.
//!     - We also mutate `OPENCLAW_DATA_DIR` to a per-test temp dir so the
//!       magic-file marker check looks at an isolated location (no
//!       interference with operator's runtime data dir).
//!     - This serial-mutation pattern matches the precedent in
//!       `tests/test_cost_edge_advisor_persistence.rs` and
//!       `tests/replay_manifest_signer_xlang_consistency.rs`.
//!
//! MODULE_NOTE (中):
//!   本整合測試列舉 V3 §6.2 forbidden-path enforcement 層的 4 個 acceptance
//!   proof（依 workplan §4 Wave 3 R20-P2b-S8 row + V3 §12 #10 binding）。
//!
//!   四個 proof：
//!     1. `enforce_at_startup()` 在乾淨狀態（無 env var trip + 無 magic-file
//!        trip）回 `Ok(())`。此為 `replay_runner` binary 的 production 預設
//!        路徑。
//!     2. 將 trip env var 設為已知 forbidden variant name，使
//!        `enforce_at_startup()` 回對應 `ForbiddenPathError::*` variant。
//!     3. `enforce_at_runtime("acquire_lease")` 與 `enforce_at_startup()`
//!        回傳相同 trip 結果。Wave 3 minimal IMPL：per-action gate 採同樣
//!        env+file 偵測；Wave 4 R20-P2b-T1 將以 per-action label 的 hard-coded
//!        攔截分支取代 body。
//!     4. `ForbiddenPathError` 的 7 個 variant 與 V3 §6.2 forbidden surface
//!        1:1 對齊。我們以窮盡 `match` 列舉，使編譯器拒絕任何「新增 variant
//!        但忘了同步本檔」的 silent contract drift。
//!
//!   ENV var serial-mutation 安全性：
//!     - 本檔 test mutate 進程 env var 構造 trip-state fixture。為避免同檔
//!       sibling test 並行 race（cargo test 預設同檔 test 並行），每 test 在
//!       mutate env 前取得共享 `Mutex`，並透過 `EnvVarRestore` RAII helper
//!       於 Drop 時還原原值（或 unset）。
//!     - 同時將 `OPENCLAW_DATA_DIR` mutate 為 per-test 暫存 dir，使 magic-file
//!       marker 檢查看的是隔離位置（不與 operator 的 runtime data dir 相互
//!       干擾）。
//!     - 此 serial-mutation 模式對齊
//!       `tests/test_cost_edge_advisor_persistence.rs`、
//!       `tests/replay_manifest_signer_xlang_consistency.rs` 的先例。
//!
//! Run / 執行:
//!   `cargo test -p openclaw_engine --features replay_isolated --test replay_forbidden_guard_acceptance -- --nocapture`

use std::env;
use std::sync::{Mutex, OnceLock};

use openclaw_engine::replay::forbidden_guard::{
    self, ForbiddenPathError, TRIP_ENV_VAR, TRIP_FILE_BASENAME,
};

// ─────────────────────────────────────────────────────────────────────────
// Serial-mutation guard / 序列化 mutate 守衛
// ─────────────────────────────────────────────────────────────────────────

/// Shared mutex serialising env mutations across tests in this file.
/// 本檔 test 共享、以序列化 env mutate 的 Mutex。
fn env_lock() -> &'static Mutex<()> {
    static LOCK: OnceLock<Mutex<()>> = OnceLock::new();
    LOCK.get_or_init(|| Mutex::new(()))
}

/// RAII helper restoring an env var to its original value (or unsetting it
/// when it was previously unset) on Drop.
///
/// RAII helper：Drop 時還原 env var 至原值（或還原為未設）。
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
// Proof 1 — clean state returns Ok(())
// ─────────────────────────────────────────────────────────────────────────

/// Proof 1 — `enforce_at_startup()` on clean state (no trip env, no magic
/// file) returns `Ok(())`.
///
/// V3 §12 #10 production-default path acceptance.
#[test]
fn proof_1_enforce_at_startup_clean_state_ok() {
    let _g = env_lock().lock().unwrap_or_else(|e| e.into_inner());
    let _restore_trip = EnvVarRestore::capture(TRIP_ENV_VAR);
    let _restore_data = EnvVarRestore::capture("OPENCLAW_DATA_DIR");

    // Arrange: clear trip env + point OPENCLAW_DATA_DIR at a temp dir that
    // does NOT contain the magic file marker.
    // 準備：清 trip env + 將 OPENCLAW_DATA_DIR 指向不含 magic file marker 的
    // 暫存 dir。
    let tmp = tempfile::tempdir().expect("create tempdir");
    // SAFETY: env_lock acquired above; single-threaded mutation.
    unsafe {
        env::remove_var(TRIP_ENV_VAR);
        env::set_var("OPENCLAW_DATA_DIR", tmp.path());
    }

    // Act + Assert / 執行 + 斷言。
    let result = forbidden_guard::enforce_at_startup();
    assert!(
        result.is_ok(),
        "clean-state enforce_at_startup must return Ok(()), got {:?}",
        result
    );
}

// ─────────────────────────────────────────────────────────────────────────
// Proof 2 — env var trip surfaces the matching variant
// ─────────────────────────────────────────────────────────────────────────

/// Proof 2 — Setting the trip env var to a known variant name causes
/// `enforce_at_startup()` to return the corresponding variant.
///
/// V3 §12 #10 forbidden-path detection acceptance.
#[test]
fn proof_2_env_var_trip_surfaces_variant() {
    let _g = env_lock().lock().unwrap_or_else(|e| e.into_inner());
    let _restore_trip = EnvVarRestore::capture(TRIP_ENV_VAR);
    let _restore_data = EnvVarRestore::capture("OPENCLAW_DATA_DIR");

    let tmp = tempfile::tempdir().expect("create tempdir");
    // SAFETY: env_lock acquired; single-threaded mutation.
    unsafe {
        env::set_var("OPENCLAW_DATA_DIR", tmp.path());
    }

    // Map of variant name → expected ForbiddenPathError.
    // variant name → 預期 ForbiddenPathError 的對映。
    let cases: &[(&str, ForbiddenPathError)] = &[
        (
            "AcquireLeaseDetected",
            ForbiddenPathError::AcquireLeaseDetected,
        ),
        ("IpcServerStarted", ForbiddenPathError::IpcServerStarted),
        ("WsClientStarted", ForbiddenPathError::WsClientStarted),
        (
            "ExchangeDispatchInvoked",
            ForbiddenPathError::ExchangeDispatchInvoked,
        ),
        (
            "DbWriterChannelInvoked",
            ForbiddenPathError::DbWriterChannelInvoked,
        ),
        (
            "LiveDemoConfigMutated",
            ForbiddenPathError::LiveDemoConfigMutated,
        ),
        (
            "AdvisoryWriteAttempted:test_source",
            ForbiddenPathError::AdvisoryWriteAttempted {
                source: "test_source".to_string(),
            },
        ),
    ];

    for (raw, expected) in cases {
        // SAFETY: env_lock acquired; single-threaded mutation.
        unsafe {
            env::set_var(TRIP_ENV_VAR, raw);
        }
        let result = forbidden_guard::enforce_at_startup();
        match result {
            Ok(()) => panic!(
                "env trip {:?} must NOT pass enforce_at_startup, but it returned Ok",
                raw
            ),
            Err(actual) => assert_eq!(
                &actual, expected,
                "env trip {:?} must produce {:?}, got {:?}",
                raw, expected, actual
            ),
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Proof 3 — runtime gate matches startup gate (Wave 3 minimal contract)
// ─────────────────────────────────────────────────────────────────────────

/// Proof 3 — `enforce_at_runtime("acquire_lease")` returns the same trip
/// result as `enforce_at_startup()` under identical env+file state.
///
/// Wave 3 minimal IMPL contract: per-action label is informational; the
/// detection mechanism is identical. Wave 4 R20-P2b-T1 wrapper will replace
/// this body with hard-coded per-action interception.
///
/// V3 §12 #10 runtime detection acceptance.
#[test]
fn proof_3_enforce_at_runtime_acquire_lease() {
    let _g = env_lock().lock().unwrap_or_else(|e| e.into_inner());
    let _restore_trip = EnvVarRestore::capture(TRIP_ENV_VAR);
    let _restore_data = EnvVarRestore::capture("OPENCLAW_DATA_DIR");

    let tmp = tempfile::tempdir().expect("create tempdir");
    // SAFETY: env_lock acquired; single-threaded mutation.
    unsafe {
        env::set_var("OPENCLAW_DATA_DIR", tmp.path());
        env::set_var(TRIP_ENV_VAR, "AcquireLeaseDetected");
    }

    // Both gates must surface AcquireLeaseDetected on the same env state.
    // 同一 env 狀態下兩 gate 必同時 surface AcquireLeaseDetected。
    let startup = forbidden_guard::enforce_at_startup();
    let runtime = forbidden_guard::enforce_at_runtime("acquire_lease");

    assert!(
        matches!(startup, Err(ForbiddenPathError::AcquireLeaseDetected)),
        "startup gate must return AcquireLeaseDetected, got {:?}",
        startup
    );
    assert!(
        matches!(runtime, Err(ForbiddenPathError::AcquireLeaseDetected)),
        "runtime gate must return AcquireLeaseDetected, got {:?}",
        runtime
    );

    // Also verify clean-state runtime gate returns Ok.
    // 也驗證 clean-state 下 runtime gate 回 Ok。
    // SAFETY: env_lock acquired; single-threaded mutation.
    unsafe {
        env::remove_var(TRIP_ENV_VAR);
    }
    let runtime_clean = forbidden_guard::enforce_at_runtime("acquire_lease");
    assert!(
        runtime_clean.is_ok(),
        "runtime gate on clean state must return Ok(()), got {:?}",
        runtime_clean
    );
}

// ─────────────────────────────────────────────────────────────────────────
// Proof 4 — variant enum aligns with V3 §6.2 forbidden list (exhaustive
// match catches new-variant drift at compile time)
// ─────────────────────────────────────────────────────────────────────────

/// Proof 4 — `ForbiddenPathError` 7 variants align with V3 §6.2 list.
///
/// We exhaustively `match` every current variant. If a future commit adds an
/// 8th variant without also updating this test, the compiler errors with
/// `non-exhaustive patterns`, surfacing the contract drift.
///
/// V3 §12 #10 cross-method consistency.
#[test]
fn proof_4_variant_consistency_with_v3_section_6_2() {
    // Construct one instance per variant to force exhaustive coverage.
    // 每 variant 建一個實例以強制窮盡覆蓋。
    let all_variants: Vec<ForbiddenPathError> = vec![
        ForbiddenPathError::AcquireLeaseDetected,
        ForbiddenPathError::IpcServerStarted,
        ForbiddenPathError::WsClientStarted,
        ForbiddenPathError::ExchangeDispatchInvoked,
        ForbiddenPathError::DbWriterChannelInvoked,
        ForbiddenPathError::LiveDemoConfigMutated,
        ForbiddenPathError::AdvisoryWriteAttempted {
            source: "audit".to_string(),
        },
    ];
    assert_eq!(
        all_variants.len(),
        7,
        "V3 §6.2 forbidden list must remain 7 surfaces (AcquireLease / IpcServer / \
         WsClient / ExchangeDispatch / DbWriter / LiveDemoConfig / AdvisoryWrite)"
    );

    for variant in all_variants {
        // Exhaustive match — adding a new variant without updating here
        // will compile-fail. This is the "drift catcher" invariant.
        // 窮盡 match — 未更新本處而新增 variant 將編譯失敗。此為「漂移攔截」
        // 不變量。
        let label: &str = match &variant {
            ForbiddenPathError::AcquireLeaseDetected => "AcquireLeaseDetected",
            ForbiddenPathError::IpcServerStarted => "IpcServerStarted",
            ForbiddenPathError::WsClientStarted => "WsClientStarted",
            ForbiddenPathError::ExchangeDispatchInvoked => "ExchangeDispatchInvoked",
            ForbiddenPathError::DbWriterChannelInvoked => "DbWriterChannelInvoked",
            ForbiddenPathError::LiveDemoConfigMutated => "LiveDemoConfigMutated",
            ForbiddenPathError::AdvisoryWriteAttempted { .. } => "AdvisoryWriteAttempted",
        };
        assert!(
            !label.is_empty(),
            "variant {:?} must have a non-empty label",
            variant
        );
        // Display impl must mention the variant name (audit log discriminator).
        // Display impl 必含 variant name（audit log 區分器）。
        let display = format!("{}", variant);
        assert!(
            display.contains(label),
            "Display impl for {:?} must contain '{}', got '{}'",
            variant,
            label,
            display
        );
    }

    // Sanity: const exports referenced by Wave 4 wrapper.
    // 完整性：Wave 4 wrapper 會引用的 const export。
    assert_eq!(TRIP_ENV_VAR, "OPENCLAW_REPLAY_FORBIDDEN_TRIPPED");
    assert_eq!(TRIP_FILE_BASENAME, "replay_forbidden.tripped");
}
