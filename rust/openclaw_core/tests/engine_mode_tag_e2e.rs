//! Integration tests — engine_mode tag end-to-end coverage (HIGH-1 retrofit).
//! 整合測試 — engine_mode tag 端到端覆蓋（HIGH-1 retrofit）。
//!
//! MODULE_NOTE (EN): E2 round 1 verdict HIGH-1 retrofit (2026-05-03):
//!   `set_engine_mode_tag` wires per-pipeline engine_mode tag for V054
//!   `learning.lease_transitions` audit emit. End-to-end coverage =
//!   inject tag → acquire_lease → verify emitted LeaseTransitionMsg
//!   carries the injected tag.
//!
//!   Lives outside `governance_core::tests` so the parent module stays
//!   under the §9 pre-existing baseline exception buffer (the original
//!   E1 facade retrofit baseline 1251 LOC + ATLAS round-1 +247 LOC →
//!   buffer for round-2 minimal). 6 tests cover:
//!     1. paper / 2. demo / 3. live_demo (acquire + release path) /
//!     4. live_mainnet / 5. shadow / 6. fail-soft "unknown" sentinel.
//!
//! MODULE_NOTE (中): E2 round 1 verdict HIGH-1 retrofit（2026-05-03）：
//!   `set_engine_mode_tag` 注入 per-pipeline engine_mode tag 供 V054
//!   `learning.lease_transitions` audit emit 使用。end-to-end 覆蓋 =
//!   注入 tag → acquire_lease → 驗 emit msg 帶該 tag。
//!
//!   置於 `governance_core::tests` 外，使 parent module 維持在 §9
//!   pre-existing baseline exception buffer 內（原 E1 facade retrofit
//!   baseline 1251 + ATLAS round-1 +247 → round-2 緩衝極小）。6 tests：
//!     1. paper / 2. demo / 3. live_demo（acquire + release 路徑）/
//!     4. live_mainnet / 5. shadow / 6. fail-soft "unknown" sentinel。
//!
//! 上層治理 SoT：CLAUDE.md §三 18 Live Blocker #6 + amendment §3 點 5 +
//! §4 AC-1（5 distinct states / 24h）+ E2 round 1 verdict HIGH-1。

use openclaw_core::governance_core::{
    GovernanceCore, GovernanceProfile, LeaseOutcome, LeaseTransitionMsg,
};

/// Helper: build a Production-authorized core with a given engine_mode tag
/// + emit channel; returns (core, receiver) so test can drain emits.
/// Helper：構造帶指定 engine_mode tag + emit channel 的 Production 授權 core；
/// 回 (core, receiver) 供 test drain emit。
fn make_core_with_tag_and_emit(
    tag: &str,
) -> (
    GovernanceCore,
    std::sync::mpsc::Receiver<LeaseTransitionMsg>,
) {
    let mut core = GovernanceCore::new();
    core.grant_paper_authorization(None).unwrap();
    let (tx, rx) = std::sync::mpsc::channel::<LeaseTransitionMsg>();
    core.set_lease_transition_tx(tx);
    core.set_engine_mode_tag(tag.to_string());
    (core, rx)
}

/// HIGH-1 case 1: paper pipeline emits engine_mode='paper'.
/// HIGH-1 case 1：paper 管線 emit engine_mode='paper'。
#[test]
fn test_engine_mode_tag_paper_emit_via_acquire_lease() {
    let (core, rx) = make_core_with_tag_and_emit("paper");
    let _lease = core
        .acquire_lease(
            "intent-paper-1",
            "TRADE_ENTRY",
            30_000,
            GovernanceProfile::Production,
            "test",
        )
        .unwrap();
    // acquire_lease emits 3 msgs (DRAFT / REGISTERED / ACTIVE).
    // acquire_lease emit 3 筆 msg。
    let msgs: Vec<_> = rx.try_iter().collect();
    assert_eq!(msgs.len(), 3, "acquire emits 3 transition msgs");
    for m in &msgs {
        assert_eq!(m.engine_mode, "paper", "engine_mode must be 'paper'");
    }
}

/// HIGH-1 case 2: demo pipeline emits engine_mode='demo'.
/// HIGH-1 case 2：demo 管線 emit engine_mode='demo'。
#[test]
fn test_engine_mode_tag_demo_emit_via_acquire_lease() {
    let (core, rx) = make_core_with_tag_and_emit("demo");
    let _lease = core
        .acquire_lease(
            "intent-demo-1",
            "TRADE_ENTRY",
            30_000,
            GovernanceProfile::Production,
            "test",
        )
        .unwrap();
    let msgs: Vec<_> = rx.try_iter().collect();
    assert_eq!(msgs.len(), 3);
    for m in &msgs {
        assert_eq!(m.engine_mode, "demo");
    }
}

/// HIGH-1 case 3: live_demo pipeline emits engine_mode='live_demo' on both
/// acquire and release paths (5 msgs total: DRAFT / REGISTERED / ACTIVE /
/// BRIDGED / CONSUMED).
/// HIGH-1 case 3：live_demo 管線 acquire + release 兩路徑皆 emit
/// engine_mode='live_demo'（共 5 筆）。
#[test]
fn test_engine_mode_tag_live_demo_emit_via_acquire_and_release() {
    let (core, rx) = make_core_with_tag_and_emit("live_demo");
    let lease = core
        .acquire_lease(
            "intent-livedemo-1",
            "TRADE_ENTRY",
            30_000,
            GovernanceProfile::Production,
            "test",
        )
        .unwrap();
    // acquire emit 3, release Consumed emit 2 (BRIDGED + CONSUMED) = 5 total.
    // acquire emit 3，release Consumed emit 2（BRIDGED + CONSUMED）共 5 筆。
    core.release_lease(&lease, LeaseOutcome::Consumed).unwrap();
    let msgs: Vec<_> = rx.try_iter().collect();
    assert_eq!(msgs.len(), 5, "acquire 3 + release Consumed 2 = 5");
    for m in &msgs {
        assert_eq!(m.engine_mode, "live_demo");
    }
}

/// HIGH-1 case 4: live_mainnet pipeline emits engine_mode='live_mainnet'.
/// HIGH-1 case 4：live_mainnet 管線 emit engine_mode='live_mainnet'。
#[test]
fn test_engine_mode_tag_live_mainnet_emit_via_acquire_lease() {
    let (core, rx) = make_core_with_tag_and_emit("live_mainnet");
    let _lease = core
        .acquire_lease(
            "intent-mainnet-1",
            "TRADE_ENTRY",
            30_000,
            GovernanceProfile::Production,
            "test",
        )
        .unwrap();
    let msgs: Vec<_> = rx.try_iter().collect();
    assert_eq!(msgs.len(), 3);
    for m in &msgs {
        assert_eq!(m.engine_mode, "live_mainnet");
    }
}

/// HIGH-1 case 5: shadow pipeline emits engine_mode='shadow' so AC-1 query
/// `WHERE engine_mode != 'shadow'` filter functions correctly.
/// HIGH-1 case 5：shadow 管線 emit engine_mode='shadow'，AC-1 過濾正確。
#[test]
fn test_engine_mode_tag_shadow_emit_via_acquire_lease() {
    let (core, rx) = make_core_with_tag_and_emit("shadow");
    let _lease = core
        .acquire_lease(
            "intent-shadow-1",
            "TRADE_ENTRY",
            30_000,
            GovernanceProfile::Production,
            "test",
        )
        .unwrap();
    let msgs: Vec<_> = rx.try_iter().collect();
    assert_eq!(msgs.len(), 3);
    for m in &msgs {
        assert_eq!(m.engine_mode, "shadow");
    }
}

/// HIGH-1 case 6 fail-soft: no tag injection + no env var → resolver falls
/// back to "unknown"; emit msg carries 'unknown' (writer-side INSERT layer
/// maps to 'demo' before V054 CHECK kicks in to keep audit row writes
/// never lost).
/// HIGH-1 case 6 fail-soft：無注入 + 無 env var → resolver fallback "unknown"；
/// emit msg 帶 'unknown'（writer-side INSERT layer 在 V054 CHECK 之前
/// 映射為 'demo'，audit row 永不丟）。
#[test]
fn test_engine_mode_tag_no_injection_falls_back_to_unknown() {
    // Save and clear OPENCLAW_ENGINE_MODE to ensure no env var leak.
    // 保存並清空 OPENCLAW_ENGINE_MODE 確保 env var 不洩漏。
    let original = std::env::var("OPENCLAW_ENGINE_MODE").ok();
    std::env::remove_var("OPENCLAW_ENGINE_MODE");

    let mut core = GovernanceCore::new();
    core.grant_paper_authorization(None).unwrap();
    let (tx, rx) = std::sync::mpsc::channel::<LeaseTransitionMsg>();
    core.set_lease_transition_tx(tx);
    // Crucially: NO set_engine_mode_tag call — resolver returns "unknown".
    // 關鍵：無 set_engine_mode_tag 呼叫 — resolver 返 "unknown"。

    let _lease = core
        .acquire_lease(
            "intent-unknown-1",
            "TRADE_ENTRY",
            30_000,
            GovernanceProfile::Production,
            "test",
        )
        .unwrap();
    let msgs: Vec<_> = rx.try_iter().collect();
    assert_eq!(msgs.len(), 3);
    for m in &msgs {
        assert_eq!(
            m.engine_mode, "unknown",
            "no injection + no env → 'unknown' fail-soft sentinel"
        );
    }

    // Restore env var if any.
    // 還原 env var（若存在）。
    if let Some(val) = original {
        std::env::set_var("OPENCLAW_ENGINE_MODE", val);
    }
}
