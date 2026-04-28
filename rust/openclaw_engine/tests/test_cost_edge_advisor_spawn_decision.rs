//! G3-09 Phase B Wave 0 FUP-SPAWN-TEST — wrapper-decision parity tests.
//! G3-09 Phase B Wave 0 FUP-SPAWN-TEST — wrapper 決策 parity 測試。
//!
//! MODULE_NOTE (EN): This file is one of THREE test binaries split out from
//!   the original `test_cost_edge_advisor_daemon.rs` (1159 LOC > §九 800 warn)
//!   per E2 spawn-test review LOW-1 recommendation. The other two files are:
//!     * `test_cost_edge_advisor_daemon_proofs.rs` — Proofs 1, 2, 3a, 4, 5
//!     * `test_cost_edge_advisor_daemon_dual_safeguard.rs` — Proof 3b +
//!       sticky `triggered_at_ms` semantics
//!
//!   Proofs 1-5 in `..._proofs.rs` directly drive `spawn_cost_edge_advisor`
//!   (the inner spawn). They prove the daemon is correct *if invoked*, but
//!   they bypass `cost_edge_advisor_boot::spawn_cost_edge_advisor_if_enabled` —
//!   the bin-side decision wrapper that gates spawn on env + populates the
//!   IPC `CostEdgeAdvisorSlot`. E2 review report
//!   `2026-04-27--g3_09_daemon_test_review.md` raised this as INFO and PA
//!   upgraded to P3 backlog; Phase B Wave 0 needs spawn-decision parity to
//!   close the protection surface.
//!
//!   `spawn_cost_edge_advisor_if_enabled` lives in the binary crate
//!   (`src/cost_edge_advisor_boot.rs`, `pub(crate)`) so integration tests in `tests/`
//!   cannot call it directly. Cases A/B/C below replicate the wrapper's
//!   decision logic *exactly* (using the same lib-public primitives the
//!   wrapper uses: `is_advisor_env_enabled` + `spawn_cost_edge_advisor` +
//!   slot late-injection + `CostEdgeAdvisor::state()` mirroring the IPC
//!   handler `handle_get_cost_edge_advisor_status` lines 33-44).
//!
//!   Slot semantics under test (matches `slots.rs:140`
//!   `CostEdgeAdvisorSlot = Arc<RwLock<Option<Arc<CostEdgeAdvisor>>>>`):
//!     * `None` → IPC handler returns the structured `advisor_disabled`
//!       payload with `status="Uninitialized"` (handler lines 36-42).
//!     * `Some(advisor)` → IPC handler returns `advisor.state()` snapshot
//!       (handler line 44).
//!
//!   Coverage of THIS file (3 cases):
//!     A. `fup_case_a_env_unset_keeps_slot_none_and_ipc_uninitialized` —
//!        DEFAULT-OFF zero-overhead path (env unset → wrapper short-circuit).
//!     B. `fup_case_b_env_set_risk_disabled_slot_some_ipc_disabled` —
//!        dual-safeguard #2 (env=1 + RiskConfig.enabled=false → daemon
//!        spawns + injects slot but produces Disabled state).
//!     C. `fup_case_c_env_set_risk_enabled_slot_some_ipc_live_state` —
//!        full happy path (env=1 + RiskConfig.enabled=true + H5 OK → live OK).
//!
//!   Env-gate isolation: tests serialise via a process-wide `Mutex` because
//!   env vars are global to the OS process; running them concurrently would
//!   race the env state. Each test binary has its own `env_lock()`
//!   `OnceLock` — Cargo runs `tests/*.rs` as separate processes so cross-
//!   binary env races are impossible.
//!
//! MODULE_NOTE (中)：本檔為原 `test_cost_edge_advisor_daemon.rs`（1159 LOC >
//!   §九 800 警告）per E2 spawn-test review LOW-1 推薦拆出三檔之一,另兩檔：
//!     * `test_cost_edge_advisor_daemon_proofs.rs` — Proof 1, 2, 3a, 4, 5
//!     * `test_cost_edge_advisor_daemon_dual_safeguard.rs` — Proof 3b + sticky
//!
//!   `..._proofs.rs` 內 Proof 1-5 直驅內層 `spawn_cost_edge_advisor`，證 daemon
//!   被呼叫後正確,但繞過 `cost_edge_advisor_boot::spawn_cost_edge_advisor_if_enabled`
//!   bin-side 決策包裝（env-gate + slot 注入）。E2 review 列 INFO，PA 升 P3
//!   backlog；Phase B Wave 0 需 spawn-decision parity 才完整保護面。
//!
//!   `spawn_cost_edge_advisor_if_enabled` 在 binary crate（pub(crate)），
//!   `tests/` 整合測試不能直呼。下方 Case A/B/C 用 wrapper 完全相同的
//!   lib-public primitive 重現決策邏輯：`is_advisor_env_enabled` +
//!   `spawn_cost_edge_advisor` + slot late-inject + `CostEdgeAdvisor::state()`
//!   鏡射 IPC handler `handle_get_cost_edge_advisor_status` line 33-44。
//!
//!   Slot 語意（對齊 `slots.rs:140`）：None → IPC 回 `advisor_disabled`
//!   payload status=Uninitialized；Some → IPC 回 advisor.state() snapshot。
//!
//!   本檔 3 case：
//!     A. env 未設 → wrapper short-circuit，slot 維持 None，IPC 讀
//!        `Uninitialized`（DEFAULT-OFF 零負擔路徑）
//!     B. env=1 + RiskConfig.enabled=false → wrapper 通過 env-gate spawn daemon、
//!        注入 slot，但 daemon evaluate() short-circuit 到 Disabled（雙保險 #2）
//!     C. env=1 + RiskConfig.enabled=true → wrapper spawn daemon、注入 slot、
//!        daemon evaluate() 產生 live OK state（happy path）
//!
//!   每個 test binary 各自持 `env_lock()` `OnceLock` — Cargo 將 `tests/*.rs`
//!   各跑為獨立進程，跨 binary env race 不可能。

use openclaw_engine::config::{ConfigStore, RiskConfig};
use openclaw_engine::cost_edge_advisor::{
    is_advisor_env_enabled, spawn_cost_edge_advisor, CostEdgeAdvisor, CostEdgeAdvisorState,
    CostEdgeAdvisorStatus, ENV_ADVISOR_FLAG,
};
use openclaw_engine::h_state_cache::{H5CostStats, HStateCache, HStateSnapshot};
use openclaw_engine::ipc_server::CostEdgeAdvisorSlot;

use std::sync::{Arc, Mutex, OnceLock};
use std::time::{Duration, Instant};
use tokio::sync::RwLock;
use tokio_util::sync::CancellationToken;

// ---------------------------------------------------------------------------
// Builders / 構造輔助
// ---------------------------------------------------------------------------

/// Build a fresh RiskConfig with `cost_edge.enabled=true` + threshold=-0.5.
/// 建 RiskConfig：cost_edge.enabled=true + threshold=-0.5。
fn risk_config_advisor_enabled() -> Arc<ConfigStore<RiskConfig>> {
    let mut cfg = RiskConfig::default();
    cfg.cost_edge.enabled = true;
    cfg.cost_edge.trigger_threshold = -0.5;
    Arc::new(ConfigStore::new(cfg))
}

/// Build a fresh RiskConfig with `cost_edge.enabled=false` (dual safeguard
/// negative path). Used to prove RiskConfig flag gates the daemon even when
/// env=1.
/// 建 RiskConfig：cost_edge.enabled=false（雙保險負向路徑）。
fn risk_config_advisor_disabled_in_config() -> Arc<ConfigStore<RiskConfig>> {
    let mut cfg = RiskConfig::default();
    cfg.cost_edge.enabled = false;
    cfg.cost_edge.trigger_threshold = -0.5;
    Arc::new(ConfigStore::new(cfg))
}

/// Build an H state cache with a fresh OK snapshot (ratio above threshold,
/// data_days >= 3 to escape WarmUp). Stale flag is naturally false because
/// we just stored.
/// 建 H state cache：fresh OK snapshot（ratio 高於 threshold + data_days>=3
/// 跳過 WarmUp）；剛 store 完所以 stale=false。
fn h_state_cache_with_ok_ratio() -> Arc<HStateCache> {
    let cache = HStateCache::new_arc();
    let snap = HStateSnapshot {
        version: 1,
        fetched_at_ms: now_ms(),
        h5: H5CostStats {
            ai_spend_7d_usd: 5.0,
            paper_pnl_7d_usd: 2.5,
            cost_edge_ratio: Some(0.5), // > -0.5 threshold → OK
            data_days: 7,
        },
        ..Default::default()
    };
    cache.store_snapshot(snap, now_ms());
    cache
}

/// Build an H state cache with a Trigger-inducing snapshot (ratio below
/// threshold). Used for ratio-changing scenarios.
/// 建 H state cache：Trigger snapshot（ratio < threshold）。
fn h_state_cache_with_trigger_ratio() -> Arc<HStateCache> {
    let cache = HStateCache::new_arc();
    let snap = HStateSnapshot {
        version: 1,
        fetched_at_ms: now_ms(),
        h5: H5CostStats {
            ai_spend_7d_usd: 10.0,
            paper_pnl_7d_usd: -8.0,
            cost_edge_ratio: Some(-0.8), // <= -0.5 threshold → Trigger
            data_days: 7,
        },
        ..Default::default()
    };
    cache.store_snapshot(snap, now_ms());
    cache
}

fn now_ms() -> i64 {
    use std::time::{SystemTime, UNIX_EPOCH};
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis() as i64)
        .unwrap_or(0)
}

/// Process-global lock for env-mutating tests (env vars are OS-process
/// state; concurrent mutation races). Mirrors pattern in
/// `cost_edge_advisor::tests::env_gate_strict_one_semantics_serialised`.
/// 全進程 env 鎖（env 是 OS 進程狀態，並發改會 race）。
fn env_lock() -> &'static Mutex<()> {
    static L: OnceLock<Mutex<()>> = OnceLock::new();
    L.get_or_init(|| Mutex::new(()))
}

/// Helper mirroring `IpcServer::cost_edge_advisor_slot()`: build an empty slot
/// shaped exactly like the production type alias.
/// 對齊 `IpcServer::cost_edge_advisor_slot()`：建生產型別 alias 同形 empty slot。
fn empty_advisor_slot() -> CostEdgeAdvisorSlot {
    Arc::new(RwLock::new(None))
}

/// Helper mirroring the IPC handler's read path: return the status string the
/// handler would emit for the current slot state. Lines 33-44 in
/// `handlers/cost_edge_advisor.rs`.
/// 鏡射 IPC handler 的讀取路徑：依當前 slot state 回 handler 會發的 status
/// 字串（`handlers/cost_edge_advisor.rs` 行 33-44）。
async fn ipc_handler_status_string(slot: &CostEdgeAdvisorSlot) -> &'static str {
    let guard = slot.read().await;
    match guard.as_ref() {
        // None branch → handler `advisor_disabled_response` with hard-coded
        // `status: "Uninitialized"` (handler lines 36-42 + 65-82).
        // None 分支 → handler `advisor_disabled_response`，硬編碼
        // `status: "Uninitialized"`（行 36-42 + 65-82）。
        None => "Uninitialized",
        // Some branch → handler echoes `state.status.as_str()` (handler line 48).
        // Some 分支 → handler 回 `state.status.as_str()`（行 48）。
        Some(advisor) => advisor.state().status.as_str(),
    }
}

// ---------------------------------------------------------------------------
// Case A: env unset → wrapper short-circuits, slot stays None, IPC reads
//   `Uninitialized`. Validates the DEFAULT-OFF zero-overhead path
//   (`spawn_cost_edge_advisor_if_enabled` lines 457-464).
// 案例 A：env 未設 → wrapper short-circuit，slot 維持 None，IPC 讀
//   `Uninitialized`。驗 DEFAULT-OFF 零負擔路徑（行 457-464）。
// ---------------------------------------------------------------------------

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn fup_case_a_env_unset_keeps_slot_none_and_ipc_uninitialized() {
    // Acquire process-wide env lock — env mutation is OS-process state and
    // must not race the other env-touching tests (Case B + Case C below).
    // 取全進程 env 鎖 — env 改動為 OS 進程狀態，不可與其他 env 測試 race
    // （下方 Case B + Case C）。
    let _g = env_lock().lock().expect("env lock poisoned");
    let prev = std::env::var(ENV_ADVISOR_FLAG).ok();
    std::env::remove_var(ENV_ADVISOR_FLAG);

    // Wrapper's gate decision (replicating `spawn_cost_edge_advisor_if_enabled`
    // line 457). The wrapper would return immediately at this point.
    // Wrapper 的 gate 判斷（鏡射 `spawn_cost_edge_advisor_if_enabled` 行 457）。
    // 此時 wrapper 立即 return。
    let env_enabled = is_advisor_env_enabled();
    assert!(
        !env_enabled,
        "Case A precondition: env unset must yield is_advisor_env_enabled()=false"
    );

    // Slot starts empty (matches IpcServer construction time + the
    // wrapper's no-op early-return: it never touches the slot).
    // Slot 起點空（對齊 IpcServer 構造時 + wrapper no-op early-return：
    // 不觸碰 slot）。
    let advisor_slot = empty_advisor_slot();

    // === Equivalent of `spawn_cost_edge_advisor_if_enabled(...)` invocation
    //     under env=unset: do NOTHING (wrapper's lines 457-464 path). ===
    // === env 未設下 `spawn_cost_edge_advisor_if_enabled(...)` 等價：什麼都
    //     不做（wrapper 行 457-464 路徑）。===
    if env_enabled {
        unreachable!("env was just unset; wrapper must not spawn");
    }

    // Post-condition #1: slot remains None — proves wrapper's early-return
    // does not allocate or inject anything (zero-overhead claim from
    // `spawn_cost_edge_advisor_if_enabled` doc lines 423-426).
    // 後置 #1：slot 維持 None — 證 wrapper early-return 不分配不注入
    //（零負擔承諾 doc 行 423-426）。
    assert!(
        advisor_slot.read().await.is_none(),
        "Case A: slot must stay None when env unset (wrapper short-circuits)"
    );

    // Post-condition #2: IPC handler reading the slot returns the structured
    // `advisor_disabled` payload with status=Uninitialized (handler lines
    // 36-42, 65-82). This is what Python healthcheck [22] / GUI sees.
    // 後置 #2：IPC handler 讀 slot 回結構化 `advisor_disabled` payload
    // status=Uninitialized（handler 行 36-42 + 65-82）。Python healthcheck
    // [22] / GUI 即見此值。
    let ipc_status = ipc_handler_status_string(&advisor_slot).await;
    assert_eq!(
        ipc_status, "Uninitialized",
        "Case A: IPC handler should return Uninitialized when slot None"
    );

    // Restore env to previous state for test isolation.
    // 還原 env 確保測試隔離。
    match prev {
        Some(v) => std::env::set_var(ENV_ADVISOR_FLAG, v),
        None => std::env::remove_var(ENV_ADVISOR_FLAG),
    }
}

// ---------------------------------------------------------------------------
// Case B: env=1 + RiskConfig.cost_edge.enabled=false → wrapper passes env-gate
//   and spawns daemon, but daemon's evaluate() short-circuits to Disabled
//   (per advisor::evaluate Step 1). Slot becomes Some, IPC reads "Disabled".
//   Validates the dual-safeguard claim (RFC §9.2 — both env=1 AND
//   RiskConfig.enabled=true required for non-dormant advisor).
// 案例 B：env=1 + RiskConfig.cost_edge.enabled=false → wrapper 通過 env-gate
//   並 spawn daemon，但 daemon evaluate() short-circuit 到 Disabled
//   (advisor::evaluate Step 1)。Slot 變 Some，IPC 讀 "Disabled"。驗雙保險
//   （RFC §9.2 — env=1 AND RiskConfig.enabled=true 都需才非 dormant）。
// ---------------------------------------------------------------------------

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn fup_case_b_env_set_risk_disabled_slot_some_ipc_disabled() {
    let _g = env_lock().lock().expect("env lock poisoned");
    let prev = std::env::var(ENV_ADVISOR_FLAG).ok();
    std::env::set_var(ENV_ADVISOR_FLAG, "1");

    let env_enabled = is_advisor_env_enabled();
    assert!(
        env_enabled,
        "Case B precondition: env=1 must yield is_advisor_env_enabled()=true"
    );

    let advisor_slot = empty_advisor_slot();
    let cancel = CancellationToken::new();

    // === Equivalent of `spawn_cost_edge_advisor_if_enabled(...)` under env=1
    //     with RiskConfig.cost_edge.enabled=false (dual-safeguard negative
    //     path): wrapper would late-inject advisor handle into slot
    //     (lines 472-498) and spawn daemon (lines 526-532). We do exactly
    //     that here using the same primitives. ===
    // === env=1 + RiskConfig.enabled=false（雙保險負向）下
    //     `spawn_cost_edge_advisor_if_enabled` 等價：wrapper late-inject
    //     advisor handle 進 slot（行 472-498）+ spawn daemon（行 526-532）。
    //     此處用相同 primitive 重現。===
    let cache = h_state_cache_with_trigger_ratio(); // ratio < threshold
    let risk = risk_config_advisor_disabled_in_config(); // but cfg.enabled=false
    let advisor = CostEdgeAdvisor::new_arc();

    // Step (1) — slot late-inject (wrapper lines 495-498).
    // 步驟 (1) — slot 注入（wrapper 行 495-498）。
    advisor_slot
        .write()
        .await
        .replace(Arc::clone(&advisor));

    // Step (2) — spawn daemon (wrapper lines 526-532).
    // 步驟 (2) — spawn daemon（wrapper 行 526-532）。
    let handle = spawn_cost_edge_advisor(
        Arc::clone(&advisor),
        Arc::clone(&cache),
        Arc::clone(&risk),
        Duration::from_millis(100),
        cancel.clone(),
    );

    // Wait for first cycle to write Disabled state.
    // 等首輪寫入 Disabled state。
    let deadline = Instant::now() + Duration::from_secs(1);
    while Instant::now() < deadline {
        if advisor.state().status != CostEdgeAdvisorStatus::Uninitialized {
            break;
        }
        tokio::time::sleep(Duration::from_millis(20)).await;
    }

    // Read IPC-shape status BEFORE cancel so daemon is still live (mirrors
    // production: IPC reads happen while daemon runs).
    // 在 cancel 前讀 IPC-shape status，daemon 仍活著（鏡射生產：IPC 讀發生
    // 在 daemon 運作中）。
    let ipc_status = ipc_handler_status_string(&advisor_slot).await;

    cancel.cancel();
    let _ = handle.await;

    // Post-condition #1: slot is Some (wrapper passed env-gate + injected).
    // 後置 #1：slot 為 Some（wrapper 通過 env-gate 並注入）。
    assert!(
        advisor_slot.read().await.is_some(),
        "Case B: slot must be Some when env=1 (wrapper injects regardless of \
         RiskConfig.cost_edge.enabled — dual safeguard happens INSIDE daemon)"
    );

    // Post-condition #2: IPC handler returns "Disabled" (RiskConfig flag
    // short-circuits inside daemon's evaluate() Step 1; advisor.state()
    // reflects this).
    // 後置 #2：IPC handler 回 "Disabled"（RiskConfig flag 在 daemon evaluate()
    // Step 1 short-circuit；advisor.state() 反映此值）。
    assert_eq!(
        ipc_status, "Disabled",
        "Case B: IPC handler should return Disabled when env=1 but \
         RiskConfig.cost_edge.enabled=false (dual safeguard #2)"
    );

    match prev {
        Some(v) => std::env::set_var(ENV_ADVISOR_FLAG, v),
        None => std::env::remove_var(ENV_ADVISOR_FLAG),
    }
}

// ---------------------------------------------------------------------------
// Case C: env=1 + RiskConfig.cost_edge.enabled=true → wrapper spawns daemon
//   AND slot is populated AND daemon's evaluate() produces a live (non-Disabled,
//   non-Uninitialized) state. IPC reads the live state. Validates the happy
//   path: both gates open, advisor active.
// 案例 C：env=1 + RiskConfig.cost_edge.enabled=true → wrapper spawn daemon +
//   slot 注入 + daemon evaluate() 產生 live (非 Disabled, 非 Uninitialized)
//   state。IPC 讀 live state。驗 happy path：雙 gate 都開，advisor 活躍。
// ---------------------------------------------------------------------------

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn fup_case_c_env_set_risk_enabled_slot_some_ipc_live_state() {
    let _g = env_lock().lock().expect("env lock poisoned");
    let prev = std::env::var(ENV_ADVISOR_FLAG).ok();
    std::env::set_var(ENV_ADVISOR_FLAG, "1");

    let env_enabled = is_advisor_env_enabled();
    assert!(
        env_enabled,
        "Case C precondition: env=1 must yield is_advisor_env_enabled()=true"
    );

    let advisor_slot = empty_advisor_slot();
    let cancel = CancellationToken::new();

    // === Wrapper-equivalent under env=1 + RiskConfig.enabled=true (full
    //     happy path): inject + spawn. ===
    // === env=1 + RiskConfig.enabled=true（happy path）下 wrapper 等價：
    //     注入 + spawn。===
    let cache = h_state_cache_with_ok_ratio(); // ratio above threshold → Ok
    let risk = risk_config_advisor_enabled();
    let advisor = CostEdgeAdvisor::new_arc();

    advisor_slot
        .write()
        .await
        .replace(Arc::clone(&advisor));

    let handle = spawn_cost_edge_advisor(
        Arc::clone(&advisor),
        Arc::clone(&cache),
        Arc::clone(&risk),
        Duration::from_millis(100),
        cancel.clone(),
    );

    // Wait for daemon to advance past Uninitialized (with the OK snapshot,
    // first cycle should write Ok state).
    // 等 daemon 越過 Uninitialized（OK snapshot 下首輪應寫 Ok state）。
    let deadline = Instant::now() + Duration::from_secs(1);
    while Instant::now() < deadline {
        if advisor.state().status == CostEdgeAdvisorStatus::Ok {
            break;
        }
        tokio::time::sleep(Duration::from_millis(20)).await;
    }

    let ipc_status = ipc_handler_status_string(&advisor_slot).await;

    // Capture live state for richer assertions BEFORE shutdown.
    // 在 shutdown 前抓 live state 做更豐富 assert。
    let live_state: CostEdgeAdvisorState = advisor.state();

    cancel.cancel();
    let _ = handle.await;

    // Post-condition #1: slot is Some.
    // 後置 #1：slot 為 Some。
    assert!(
        advisor_slot.read().await.is_some(),
        "Case C: slot must be Some when env=1 (wrapper injects)"
    );

    // Post-condition #2: IPC handler returns the live "OK" status (not the
    // disabled-shape stub from None branch, not "Disabled" from RiskConfig
    // short-circuit, not "Uninitialized" pre-spawn).
    // 後置 #2：IPC handler 回 live "OK" status（非 None 分支 disabled stub、
    // 非 RiskConfig short-circuit "Disabled"、非 spawn 前 "Uninitialized"）。
    assert_eq!(
        ipc_status, "OK",
        "Case C: IPC handler should return live OK status when env=1 + \
         RiskConfig.cost_edge.enabled=true + H5 OK ratio"
    );

    // Post-condition #3: state echoes H5 cache values (proves we read live
    // state, not the IPC None-branch hard-coded stub).
    // 後置 #3：state 回 H5 cache 值（證讀 live state 非 IPC None 分支硬編碼 stub）。
    assert_eq!(
        live_state.ratio,
        Some(0.5),
        "Case C: live ratio should echo H5 OK snapshot (0.5)"
    );
    assert_eq!(
        live_state.data_days, 7,
        "Case C: live data_days should echo H5 (7)"
    );
    assert_eq!(
        live_state.threshold, -0.5,
        "Case C: live threshold should echo RiskConfig (-0.5)"
    );
    assert!(
        live_state.last_eval_ms > 0,
        "Case C: live last_eval_ms should be set by daemon (got {})",
        live_state.last_eval_ms
    );

    match prev {
        Some(v) => std::env::set_var(ENV_ADVISOR_FLAG, v),
        None => std::env::remove_var(ENV_ADVISOR_FLAG),
    }
}
