//! Decision Lease retrofit HIGH-2 / HIGH-3 unit tests (E-1 round 2 retrofit).
//! Decision Lease retrofit HIGH-2 / HIGH-3 單元測試（E-1 round 2 retrofit）。
//!
//! MODULE_NOTE (EN): External integration tests for AMD-2026-05-02-01 Track H
//!   E-1 retrofit. Verifies (1) HIGH-2: GovernanceCore::check_expiry() actually
//!   transitions Active leases past their TTL into the Expired terminal state
//!   (proving that the periodic sweeper Arm in event_consumer/mod.rs has a
//!   functional SM transition path to invoke); and (2) HIGH-3: release_lease()
//!   removes the corresponding lease_id_to_idx HashMap entry after terminal
//!   transition (proving the reverse-map heap leak is closed). Tests live as
//!   external integration tests so the fixture LOC does not push
//!   src/governance_core.rs further past its §9 1500-line hard cap (current
//!   baseline 1491 is a pre-existing violation introduced by Track H E-3+E-4
//!   round 1 — see report §9.X push back to PM).
//!
//! MODULE_NOTE (中)：AMD-2026-05-02-01 Track H E-1 retrofit 對 (1) HIGH-2 與
//!   (2) HIGH-3 兩條補丁的覆蓋測試。HIGH-2：驗 `check_expiry()` 真會把過 TTL
//!   的 Active lease 轉到 Expired 終態（證明 event_consumer/mod.rs 的 60s
//!   sweeper Arm 呼叫 path 有效）；HIGH-3：驗 `release_lease()` 終態 transition
//!   後會清掉 `lease_id_to_idx` 對應條目（證明反查表 heap leak 已關閉）。本
//!   測試刻意置於外部 integration test 而非 governance_core.rs lib test，避免
//!   進一步把 src/governance_core.rs 推離 §九 1500 行 hard cap（目前 baseline
//!   1491 為 Track H E-3+E-4 round 1 引入的 pre-existing violation，已於報告
//!   §9.X push back PM）。

use openclaw_core::governance_core::{
    GovernanceCore, GovernanceProfile, LeaseId, LeaseOutcome,
};
use openclaw_core::sm::lease::LeaseState;

// ═════════════════════════════════════════════════════════════════════════════
// HIGH-3 — release_lease() must clean reverse-map after terminal transition.
// HIGH-3 — release_lease() 終態 transition 後必須清反查表。
// ═════════════════════════════════════════════════════════════════════════════

/// HIGH-3 happy path: Production acquire+release(Consumed) leaves 0 entry in
/// the lease_id_to_idx reverse map; SM still has the lease object (terminal
/// state Consumed) but the String → idx lookup has been pruned to prevent
/// per-trade heap leak.
/// HIGH-3 主路徑：Production acquire+release(Consumed) 後反查表 0 殘留條目；
/// SM 仍持有 lease 物件（終態 Consumed）但 String→idx 反查已清理。
#[test]
fn test_high3_release_consumed_cleans_reverse_map() {
    // Production needs explicit auth; grant_paper_authorization satisfies
    // is_authorized() (the SM only checks for any effective auth, not its
    // semantic mode tag). This mirrors the lib-internal facade tests.
    // Production 需顯式授權；grant_paper_authorization 可滿足 is_authorized()。
    let mut core = GovernanceCore::new();
    core.grant_paper_authorization(None).unwrap();

    let lease = core
        .acquire_lease(
            "intent-high3-1",
            "TRADE_ENTRY",
            30_000,
            GovernanceProfile::Production,
            "router_test",
        )
        .expect("acquire must succeed");
    let lease_id_str = match &lease {
        LeaseId::Active(s) => s.clone(),
        LeaseId::Bypass => panic!("Production must not Bypass"),
    };

    // Pre-condition: get_lease_by_id must succeed (proves entry exists).
    // 前置條件：get_lease_by_id 必成功（證明條目存在）。
    let pre = core.get_lease_by_id(&lease_id_str);
    assert!(pre.is_ok(), "lease must be findable before release");

    core.release_lease(&lease, LeaseOutcome::Consumed)
        .expect("release(Consumed) must succeed");

    // Post-condition: get_lease_by_id by the same lease_id must now return
    // LeaseNotFound — proves reverse map entry is gone.
    // 後置條件：get_lease_by_id 必回 LeaseNotFound — 證明反查條目已清。
    let post = core.get_lease_by_id(&lease_id_str);
    assert!(
        post.is_err(),
        "lease_id_to_idx entry must be pruned after Consumed terminal transition"
    );
}

/// HIGH-3 Failed path: release_lease(Failed) also prunes reverse map.
/// HIGH-3 Failed 路徑：release_lease(Failed) 同樣清反查表。
#[test]
fn test_high3_release_failed_cleans_reverse_map() {
    // Production needs explicit auth; grant_paper_authorization satisfies
    // is_authorized() (the SM only checks for any effective auth, not its
    // semantic mode tag). This mirrors the lib-internal facade tests.
    // Production 需顯式授權；grant_paper_authorization 可滿足 is_authorized()。
    let mut core = GovernanceCore::new();
    core.grant_paper_authorization(None).unwrap();

    let lease = core
        .acquire_lease(
            "intent-high3-2",
            "TRADE_ENTRY",
            30_000,
            GovernanceProfile::Production,
            "router_test",
        )
        .expect("acquire must succeed");
    let lease_id_str = match &lease {
        LeaseId::Active(s) => s.clone(),
        LeaseId::Bypass => panic!("Production must not Bypass"),
    };

    core.release_lease(&lease, LeaseOutcome::Failed)
        .expect("release(Failed) must succeed");

    let post = core.get_lease_by_id(&lease_id_str);
    assert!(
        post.is_err(),
        "lease_id_to_idx entry must be pruned after Failed → Revoked terminal transition"
    );
}

/// HIGH-3 Cancelled path: release_lease(Cancelled) also prunes reverse map.
/// HIGH-3 Cancelled 路徑：release_lease(Cancelled) 同樣清反查表。
#[test]
fn test_high3_release_cancelled_cleans_reverse_map() {
    // Production needs explicit auth; grant_paper_authorization satisfies
    // is_authorized() (the SM only checks for any effective auth, not its
    // semantic mode tag). This mirrors the lib-internal facade tests.
    // Production 需顯式授權；grant_paper_authorization 可滿足 is_authorized()。
    let mut core = GovernanceCore::new();
    core.grant_paper_authorization(None).unwrap();

    let lease = core
        .acquire_lease(
            "intent-high3-3",
            "TRADE_ENTRY",
            30_000,
            GovernanceProfile::Production,
            "router_test",
        )
        .expect("acquire must succeed");
    let lease_id_str = match &lease {
        LeaseId::Active(s) => s.clone(),
        LeaseId::Bypass => panic!("Production must not Bypass"),
    };

    core.release_lease(&lease, LeaseOutcome::Cancelled)
        .expect("release(Cancelled) must succeed");

    let post = core.get_lease_by_id(&lease_id_str);
    assert!(
        post.is_err(),
        "lease_id_to_idx entry must be pruned after Cancelled → Revoked terminal transition"
    );
}

/// HIGH-3 multi-lease no-leak: 5 sequential acquire+release pairs do not
/// accumulate residual entries (closes "1 yr × 1000 trade/day = 18MB heap
/// leak" from the PM prompt's HIGH-3 衝擊 calculation).
/// HIGH-3 多 lease 無洩漏：5 次序列 acquire+release 後反查表 0 殘留條目。
#[test]
fn test_high3_sequential_acquire_release_no_residual() {
    // Production needs explicit auth; grant_paper_authorization satisfies
    // is_authorized() (the SM only checks for any effective auth, not its
    // semantic mode tag). This mirrors the lib-internal facade tests.
    // Production 需顯式授權；grant_paper_authorization 可滿足 is_authorized()。
    let mut core = GovernanceCore::new();
    core.grant_paper_authorization(None).unwrap();

    let mut lease_ids: Vec<String> = Vec::with_capacity(5);
    for i in 0..5 {
        let intent_id = format!("intent-high3-multi-{i}");
        let lease = core
            .acquire_lease(
                &intent_id,
                "TRADE_ENTRY",
                30_000,
                GovernanceProfile::Production,
                "router_test",
            )
            .expect("acquire must succeed");
        let lease_id_str = match &lease {
            LeaseId::Active(s) => s.clone(),
            LeaseId::Bypass => panic!("Production must not Bypass"),
        };
        lease_ids.push(lease_id_str);
        core.release_lease(&lease, LeaseOutcome::Consumed)
            .expect("release must succeed");
    }

    // Each lease_id must now LeaseNotFound — 0 residual reverse-map entries.
    // 每個 lease_id 都必 LeaseNotFound — 反查表 0 殘留。
    for lease_id_str in &lease_ids {
        assert!(
            core.get_lease_by_id(lease_id_str).is_err(),
            "lease_id {lease_id_str} must have 0 residual entry"
        );
    }
}

/// HIGH-3 same-intent reuse: same intent_id acquire+release+acquire+release
/// produces 2 distinct lease_ids (acquire mints unique id), both reverse-map
/// entries pruned after release. Defends against a logical bug where a
/// caller reusing the same intent_id might leak the first entry when the
/// second acquire overwrites the HashMap key.
/// HIGH-3 同 intent 重用：相同 intent_id 兩輪 acquire+release 產生 2 個獨立
/// lease_id；兩條反查表條目均被清。防止 caller 重用 intent_id 時第二次
/// acquire 覆蓋 HashMap key 導致首條 leak 的邏輯 bug。
#[test]
fn test_high3_same_intent_reuse_no_leak() {
    // Production needs explicit auth; grant_paper_authorization satisfies
    // is_authorized() (the SM only checks for any effective auth, not its
    // semantic mode tag). This mirrors the lib-internal facade tests.
    // Production 需顯式授權；grant_paper_authorization 可滿足 is_authorized()。
    let mut core = GovernanceCore::new();
    core.grant_paper_authorization(None).unwrap();

    let lease1 = core
        .acquire_lease(
            "intent-reuse",
            "TRADE_ENTRY",
            30_000,
            GovernanceProfile::Production,
            "router_test",
        )
        .expect("first acquire must succeed");
    let id1 = match &lease1 {
        LeaseId::Active(s) => s.clone(),
        LeaseId::Bypass => panic!("must not Bypass"),
    };
    core.release_lease(&lease1, LeaseOutcome::Consumed).unwrap();

    let lease2 = core
        .acquire_lease(
            "intent-reuse",
            "TRADE_ENTRY",
            30_000,
            GovernanceProfile::Production,
            "router_test",
        )
        .expect("second acquire must succeed (intent_id reuse)");
    let id2 = match &lease2 {
        LeaseId::Active(s) => s.clone(),
        LeaseId::Bypass => panic!("must not Bypass"),
    };
    assert_ne!(id1, id2, "each acquire must mint a unique lease_id");

    core.release_lease(&lease2, LeaseOutcome::Consumed).unwrap();

    assert!(core.get_lease_by_id(&id1).is_err(), "id1 must be pruned");
    assert!(core.get_lease_by_id(&id2).is_err(), "id2 must be pruned");
}

// ═════════════════════════════════════════════════════════════════════════════
// HIGH-2 — check_expiry() must transition expired leases past TTL.
// HIGH-2 — check_expiry() 必須把過 TTL 的 lease 轉換到終態。
// ═════════════════════════════════════════════════════════════════════════════

/// HIGH-2 happy path: Active lease past TTL gets transitioned by check_expiry()
/// into the Expired terminal state. Proves event_consumer/mod.rs's 60s sweeper
/// Arm (calling pipeline.governance.check_expiry()) has a functional SM
/// transition path — without this, RouterLeaseGuard Drop release-failures
/// would leak Active leases until engine restart.
/// HIGH-2 主路徑：過 TTL 的 Active lease 經 check_expiry() 轉到 Expired 終態。
/// 證明 event_consumer/mod.rs 的 60s sweeper Arm（呼叫
/// pipeline.governance.check_expiry()）有效 — 否則 RouterLeaseGuard Drop
/// release 失敗的 lease 會永久卡住直到 engine 重啟。
#[test]
fn test_high2_check_expiry_transitions_active_lease_past_ttl() {
    // Production needs explicit auth; grant_paper_authorization satisfies
    // is_authorized() (the SM only checks for any effective auth, not its
    // semantic mode tag). This mirrors the lib-internal facade tests.
    // Production 需顯式授權；grant_paper_authorization 可滿足 is_authorized()。
    let mut core = GovernanceCore::new();
    core.grant_paper_authorization(None).unwrap();

    // Acquire a lease with the minimum legal TTL (100ms per spec §3 point 1).
    // 取最小合法 TTL（100ms，spec §3 點 1）以縮短測試延遲。
    let lease = core
        .acquire_lease(
            "intent-high2-expiry",
            "TRADE_ENTRY",
            100, // minimum TTL
            GovernanceProfile::Production,
            "router_test",
        )
        .expect("acquire must succeed");
    let lease_id_str = match &lease {
        LeaseId::Active(s) => s.clone(),
        LeaseId::Bypass => panic!("must not Bypass"),
    };

    // Pre-sweep: lease state must be Active.
    // 掃描前：lease 狀態必為 Active。
    let pre_obj = core
        .get_lease_by_id(&lease_id_str)
        .expect("pre-sweep lookup must succeed");
    assert_eq!(
        pre_obj.state,
        LeaseState::Active,
        "lease must be Active before TTL elapses"
    );

    // Wait past TTL boundary (100ms TTL + 50ms safety).
    // 等過 TTL 邊界（100ms TTL + 50ms 安全餘量）。
    std::thread::sleep(std::time::Duration::from_millis(150));

    // Invoke the same sweeper path event_consumer/mod.rs's 60s Arm uses.
    // 呼叫 event_consumer/mod.rs 60s Arm 使用的同一掃描 path。
    let (auth_expired, lease_expired) = core.check_expiry();

    // Auth has no TTL in this fixture (None); expect 0 auth expiries.
    // 本 fixture 中 auth 無 TTL（None），預期 0 個 auth 過期。
    assert!(
        auth_expired.is_empty(),
        "auth has no TTL — sweep must not transition any auth"
    );
    // At least one lease must have expired (the one we acquired).
    // 至少一個 lease（我們剛取得的）必過期。
    assert!(
        !lease_expired.is_empty(),
        "lease past TTL must be transitioned by check_expiry sweeper"
    );

    // Post-sweep: get_live() returns indices; the lease must no longer be in
    // the live set. We dereference each idx through `get(idx)` to compare
    // lease_id, then assert "no Live entry matches our lease_id". The exact
    // terminal state is governed by DecisionLeaseSm::check_expiry() — we
    // assert "no longer Live" rather than a specific terminal state to keep
    // the contract robust against SM tweaks.
    // 掃描後：get_live() 回 idx vec；本 lease 不應在 live 集中。透過 get(idx)
    // 解 idx → lease_id 比對；斷言「Live 集中 0 條目匹配本 lease_id」。終態
    // 由 DecisionLeaseSm::check_expiry() 決定，我們僅斷言「不再 Live」以保持
    // 契約對 SM 微調穩定。
    let sm = core.lease.lock();
    let live_indices = sm.get_live();
    let live_has_our_lease = live_indices
        .iter()
        .filter_map(|&idx| sm.get(idx))
        .any(|obj| obj.lease_id == lease_id_str);
    assert!(
        !live_has_our_lease,
        "lease past TTL must not be in get_live() after sweep"
    );
}

/// HIGH-2 multi-lease sweep: 3 leases with TTLs 100ms / 200ms / 30000ms —
/// after 250ms wait + check_expiry(), exactly the first 2 are out of Live;
/// the 3rd remains Live. Proves selective per-TTL transition (not blanket
/// purge).
/// HIGH-2 多 lease 掃描：TTL 100ms / 200ms / 30000ms 各 1 lease — 250ms 等待
/// 後掃描，僅前兩者離開 Live，第三個維持 Live。證明 per-TTL 選擇性轉換
/// （非一刀切清除）。
#[test]
fn test_high2_check_expiry_selective_per_ttl() {
    // Production needs explicit auth; grant_paper_authorization satisfies
    // is_authorized() (the SM only checks for any effective auth, not its
    // semantic mode tag). This mirrors the lib-internal facade tests.
    // Production 需顯式授權；grant_paper_authorization 可滿足 is_authorized()。
    let mut core = GovernanceCore::new();
    core.grant_paper_authorization(None).unwrap();

    let lease_short = core
        .acquire_lease(
            "intent-short",
            "TRADE_ENTRY",
            100,
            GovernanceProfile::Production,
            "router_test",
        )
        .unwrap();
    let lease_mid = core
        .acquire_lease(
            "intent-mid",
            "TRADE_ENTRY",
            200,
            GovernanceProfile::Production,
            "router_test",
        )
        .unwrap();
    let lease_long = core
        .acquire_lease(
            "intent-long",
            "TRADE_ENTRY",
            30_000,
            GovernanceProfile::Production,
            "router_test",
        )
        .unwrap();
    let id_short = match &lease_short {
        LeaseId::Active(s) => s.clone(),
        _ => panic!(),
    };
    let id_mid = match &lease_mid {
        LeaseId::Active(s) => s.clone(),
        _ => panic!(),
    };
    let id_long = match &lease_long {
        LeaseId::Active(s) => s.clone(),
        _ => panic!(),
    };

    std::thread::sleep(std::time::Duration::from_millis(250));
    let (_, lease_expired) = core.check_expiry();
    assert_eq!(
        lease_expired.len(),
        2,
        "exactly 2 leases (TTL 100ms + 200ms) must expire after 250ms"
    );

    let sm = core.lease.lock();
    let live_indices = sm.get_live();
    let live_ids: Vec<String> = live_indices
        .iter()
        .filter_map(|&idx| sm.get(idx))
        .map(|obj| obj.lease_id.clone())
        .collect();
    assert!(
        !live_ids.contains(&id_short),
        "short-TTL lease must be out of Live"
    );
    assert!(
        !live_ids.contains(&id_mid),
        "mid-TTL lease must be out of Live"
    );
    assert!(
        live_ids.contains(&id_long),
        "long-TTL lease must remain in Live (TTL 30s, only 250ms elapsed)"
    );
}
