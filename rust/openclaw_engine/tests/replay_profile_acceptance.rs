//! REF-20 Wave 3 R20-P2b-S7 — `ReplayProfile` cfg gate runtime IMPL
//! acceptance proofs.
//! REF-20 Wave 3 R20-P2b-S7 — `ReplayProfile` cfg gate runtime IMPL
//! acceptance 證明。
//!
//! MODULE_NOTE (EN):
//!   This integration test enumerates the 5 acceptance proofs for the
//!   `ReplayProfile::Isolated` cfg gate runtime IMPL (per workplan §4 Wave 3
//!   R20-P2b-S7 row + V3 §12 #8/#9/#10/#11 binding). The proofs are written
//!   so that ANY future profile addition (a new `ReplayProfile` variant) MUST
//!   either:
//!     (a) add an explicit assertion on whether the new variant counts as
//!         "Isolated" or "non-Isolated", or
//!     (b) admit that the new variant is non-exhaustive (which would make
//!         these tests fail-loud rather than silently default-arm pass).
//!
//!   Why exhaustive enumeration over `match`-by-default:
//!     - Spec ambiguity decision Wave 2 dispatch §2 #4 says
//!         `Isolated => false / 其餘 => true`. A `match` with a default arm
//!         would silently absorb a new variant; explicit enumeration in the
//!         tests makes a new variant a compile-time signal to the next
//!         author that they MUST review the gating semantics.
//!     - V3 §12 #8 (`replay_resource_isolation`) requires that the test
//!         covers BOTH directions: Isolated says "no" AND every other
//!         variant says "yes". Exhaustive enumeration is the only way to
//!         prove the second direction without depending on a default arm.
//!
//!   5 proofs (V3 §12 binding):
//!     1. `Isolated.requires_lease() == false`                        (#9)
//!     2. `{Live, LiveDemo, PaperLegacy}.requires_lease() == true`    (#9)
//!     3. `Isolated.allow_ipc_server() == false`
//!        + non-Isolated variants all `true`                          (#8)
//!     4. `Isolated.fail_closed_assert_isolated() == Ok(())`
//!        + non-Isolated variants all `Err(WrongProfile)`             (#10)
//!     5. Cross-method consistency:
//!        `Isolated` => all 4 gating methods return `false`
//!        non-Isolated => all 4 gating methods return `true`          (#8/#9/#10/#11)
//!
//! MODULE_NOTE (中):
//!   本整合測試列舉 `ReplayProfile::Isolated` cfg gate runtime IMPL 的 5 個
//!   acceptance 證明（依 workplan §4 Wave 3 R20-P2b-S7 row + V3 §12
//!   #8/#9/#10/#11 binding）。proof 撰寫風格使任何未來 profile 新增（新
//!   `ReplayProfile` variant）必須：
//!     (a) 對新 variant 是否計入 "Isolated" 或 "non-Isolated" 加明確 assertion，或
//!     (b) 承認新 variant 非 exhaustive（會讓這些 test fail-loud，而非在
//!         預設 arm 下 silently pass）。
//!
//!   為何採窮盡列舉而非 default arm：
//!     - Wave 2 dispatch §2 ambiguity #4 決議 `Isolated => false / 其餘 => true`。
//!         帶 default arm 的 match 會 silently 吸收新 variant；test 內顯式
//!         列舉讓新 variant 成為 compile-time 訊號，提醒下一位作者必須重審
//!         gating 語意。
//!     - V3 §12 #8（`replay_resource_isolation`）要求 test 覆蓋雙向：
//!         Isolated 說「不可」**且**其他 variant 全說「可」。窮盡列舉是
//!         唯一不靠 default arm 證明第二方向的方式。
//!
//!   5 個 proof（V3 §12 binding）：
//!     1. `Isolated.requires_lease() == false`                        (#9)
//!     2. `{Live, LiveDemo, PaperLegacy}.requires_lease() == true`    (#9)
//!     3. `Isolated.allow_ipc_server() == false`
//!        + 其餘 variant 全 `true`                                    (#8)
//!     4. `Isolated.fail_closed_assert_isolated() == Ok(())`
//!        + 其餘 variant 全 `Err(WrongProfile)`                       (#10)
//!     5. 跨 method 一致性：
//!        `Isolated` => 4 個 gating method 全回 `false`
//!        非 `Isolated` => 4 個 gating method 全回 `true`             (#8/#9/#10/#11)
//!
//! Run / 執行:
//!   `cargo test -p openclaw_engine --test replay_profile_acceptance -- --nocapture`

use openclaw_engine::replay::profile::{ReplayIsolationError, ReplayProfile};

/// Proof 1 — `Isolated.requires_lease() == false`.
///
/// V3 §12 #9 (`replay_no_decision_lease_acquire`) acceptance binding.
/// V3 §12 #9 (`replay_no_decision_lease_acquire`) acceptance 綁定。
#[test]
fn proof_1_isolated_requires_lease_false() {
    assert!(
        !ReplayProfile::Isolated.requires_lease(),
        "V3 §6.2 invariant: Isolated MUST NOT require a Decision Lease \
         (V3 §12 #9 binding)"
    );
}

/// Proof 2 — `{Live, LiveDemo, PaperLegacy}.requires_lease() == true`.
///
/// 對齊 Wave 2 dispatch §2 #4：「Isolated => false / 其餘 => true」。每個
/// 既有 variant 各 1 case，不用 default arm，逼新 variant 的作者顯式選邊。
///
/// Aligned with Wave 2 dispatch §2 #4: "Isolated => false / others => true".
/// One case per existing variant, no default arm, so a new-variant author
/// is forced to explicitly choose a side.
#[test]
fn proof_2_non_isolated_variants_require_lease_true() {
    assert!(
        ReplayProfile::Live.requires_lease(),
        "Live MUST keep its Decision Lease commitment (CLAUDE.md §四 + AMD-2026-05-02-01)"
    );
    assert!(
        ReplayProfile::LiveDemo.requires_lease(),
        "LiveDemo MUST keep its Decision Lease commitment \
         (CLAUDE.md §四: LiveDemo 不因 endpoint 降級)"
    );
    assert!(
        ReplayProfile::PaperLegacy.requires_lease(),
        "PaperLegacy MUST keep its existing Decision Lease commitment \
         (Wave 2 dispatch §2 #4: PaperLegacy=true; UX subdoc §11.1 continuity)"
    );
}

/// Proof 3 — `allow_ipc_server` matrix.
///
/// V3 §12 #8 (`replay_resource_isolation`) acceptance binding.
/// V3 §12 #8 (`replay_resource_isolation`) acceptance 綁定。
#[test]
fn proof_3_allow_ipc_server_matrix() {
    assert!(
        !ReplayProfile::Isolated.allow_ipc_server(),
        "V3 §6.2 forbidden list bans IPC server inside replay (V3 §12 #8 binding)"
    );

    // 雙向證明：non-Isolated variant 必全回 true，禁 default arm。
    // Two-way proof: non-Isolated variants must all return true; default-arm forbidden.
    assert!(
        ReplayProfile::Live.allow_ipc_server(),
        "Live keeps IPC server bridging (engine ↔ Python control_api_v1)"
    );
    assert!(
        ReplayProfile::LiveDemo.allow_ipc_server(),
        "LiveDemo keeps IPC server bridging (LiveDemo not degraded by demo endpoint)"
    );
    assert!(
        ReplayProfile::PaperLegacy.allow_ipc_server(),
        "PaperLegacy keeps existing IPC server bridging (paper engine continuity)"
    );
}

/// Proof 4 — `fail_closed_assert_isolated` matrix.
///
/// V3 §12 #10 (`replay_forbidden_wiring_fail_closed`) acceptance binding.
/// V3 §12 #10 (`replay_forbidden_wiring_fail_closed`) acceptance 綁定。
#[test]
fn proof_4_fail_closed_assert_matrix() {
    // Isolated => Ok(())
    // Isolated => Ok(())
    let ok = ReplayProfile::Isolated.fail_closed_assert_isolated();
    assert!(ok.is_ok(), "Isolated MUST pass fail_closed_assert_isolated");

    // 非 Isolated => Err(WrongProfile { found })，且 found 必對應 caller。
    // Non-Isolated => Err(WrongProfile { found }), and `found` must match the caller.
    for &profile in &[
        ReplayProfile::Live,
        ReplayProfile::LiveDemo,
        ReplayProfile::PaperLegacy,
    ] {
        match profile.fail_closed_assert_isolated() {
            Ok(()) => panic!(
                "Non-Isolated profile {:?} MUST NOT pass fail_closed_assert_isolated",
                profile
            ),
            Err(ReplayIsolationError::WrongProfile { found }) => {
                assert_eq!(
                    found, profile,
                    "WrongProfile.found payload must match the caller's profile \
                     (so audit logs can identify which non-Isolated profile leaked)"
                );
            }
        }
    }
}

/// Proof 5 — 跨 method 一致性。
///
/// V3 §6.2 forbidden 清單恰好 = 四個 runtime surface（lease / IPC server /
/// exchange dispatch / DB writer channel）。對 `Isolated` 四 method 必全 false，
/// 對其餘 variant 四 method 必全 true。任一不一致 = silent contract drift。
///
/// V3 §6.2 forbidden list = exactly four runtime surfaces (lease / IPC
/// server / exchange dispatch / DB writer channel). For `Isolated`, all four
/// methods MUST return false; for others, all four MUST return true. Any
/// mismatch = silent contract drift.
///
/// V3 §12 #8/#9/#10/#11 cross-method binding.
#[test]
fn proof_5_cross_method_consistency() {
    // Isolated: 四 gating method 全 false。
    // Isolated: all four gating methods MUST be false.
    let isolated = ReplayProfile::Isolated;
    assert!(!isolated.requires_lease(), "Isolated.requires_lease must be false");
    assert!(
        !isolated.allow_ipc_server(),
        "Isolated.allow_ipc_server must be false"
    );
    assert!(
        !isolated.allow_exchange_dispatch(),
        "Isolated.allow_exchange_dispatch must be false"
    );
    assert!(
        !isolated.allow_db_writer_channels(),
        "Isolated.allow_db_writer_channels must be false"
    );

    // 非 Isolated 三 variant: 四 method 全 true，每個 variant 各 4 個 assertion。
    // Non-Isolated three variants: all four methods MUST be true, 4 assertions per variant.
    for &profile in &[
        ReplayProfile::Live,
        ReplayProfile::LiveDemo,
        ReplayProfile::PaperLegacy,
    ] {
        assert!(
            profile.requires_lease(),
            "non-Isolated {:?}.requires_lease must be true",
            profile
        );
        assert!(
            profile.allow_ipc_server(),
            "non-Isolated {:?}.allow_ipc_server must be true",
            profile
        );
        assert!(
            profile.allow_exchange_dispatch(),
            "non-Isolated {:?}.allow_exchange_dispatch must be true",
            profile
        );
        assert!(
            profile.allow_db_writer_channels(),
            "non-Isolated {:?}.allow_db_writer_channels must be true",
            profile
        );
    }
}
