//! G3-09 Phase A daemon integration test — Proof 3b (RiskConfig flag short-
//! circuit) + sticky `triggered_at_ms` semantics (FUP-STICKY-TS, 2026-04-28).
//! G3-09 Phase A daemon 整合測試 — Proof 3b（RiskConfig flag short-circuit）
//! + sticky `triggered_at_ms` 語意（FUP-STICKY-TS，2026-04-28）。
//!
//! MODULE_NOTE (EN): This file is one of THREE test binaries split out from
//!   the original `test_cost_edge_advisor_daemon.rs` (1159 LOC > §九 800 warn)
//!   per E2 spawn-test review LOW-1 recommendation. The other two files are:
//!     * `test_cost_edge_advisor_daemon_proofs.rs` — Proofs 1, 2, 3a, 4, 5
//!       (core daemon liveness + IPC echo + env-gate + cadence + cancel)
//!     * `test_cost_edge_advisor_spawn_decision.rs` — FUP Case A/B/C
//!       wrapper-decision parity for `spawn_cost_edge_advisor_if_enabled`
//!
//!   Coverage of THIS file (3 cases):
//!     3b. `dual_safeguard_risk_config_disabled_short_circuits` — proves
//!         RiskConfig.cost_edge.enabled=false forces Disabled even when
//!         env=1 + H5 has Trigger-inducing ratio.
//!     S1. `sticky_triggered_at_ms_records_first_entry_into_trigger` —
//!         covers property (a): the first Trigger cycle stamps
//!         `triggered_at_ms` with `now_ms` (regression guard).
//!     S2. `sticky_triggered_at_ms_preserved_across_contiguous_trigger_cycles`
//!         — covers property (b): `triggered_at_ms` stays sticky across
//!         contiguous Trigger→Trigger cycles even though `evaluate()`
//!         returns fresh `now_ms` and `last_eval_ms` advances. Phase B
//!         observation, dedup analytics, and `last_trigger_ms` rolling
//!         counter all depend on this.
//!
//!   All tests use `tokio::test(flavor = "multi_thread")` so the spawned
//!   daemon really gets its own runtime worker.
//!
//! MODULE_NOTE (中)：本檔為原 `test_cost_edge_advisor_daemon.rs`（1159 LOC >
//!   §九 800 警告）per E2 spawn-test review LOW-1 推薦拆出三檔之一,另兩檔：
//!     * `test_cost_edge_advisor_daemon_proofs.rs` — Proof 1, 2, 3a, 4, 5
//!     * `test_cost_edge_advisor_spawn_decision.rs` — FUP Case A/B/C
//!
//!   本檔 3 case：
//!     3b. RiskConfig.cost_edge.enabled=false 即使 env=1 + H5 Trigger ratio
//!         仍強制 Disabled
//!     S1. sticky 性質 (a)：首次進 Trigger cycle 寫 `triggered_at_ms = now_ms`
//!     S2. sticky 性質 (b)：contiguous Trigger→Trigger 跨 cycle 保留原時戳
//!         （Phase B observation / dedup / `last_trigger_ms` rolling counter
//!         全依賴此）

use openclaw_engine::config::{ConfigStore, RiskConfig};
use openclaw_engine::cost_edge_advisor::{
    spawn_cost_edge_advisor, CostEdgeAdvisor, CostEdgeAdvisorStatus,
};
use openclaw_engine::h_state_cache::{H5CostStats, HStateCache, HStateSnapshot};

use std::sync::Arc;
use std::time::{Duration, Instant};
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

// ---------------------------------------------------------------------------
// Proof 3b: RiskConfig flag dormancy (env=1 but config.enabled=false → Disabled).
// 證明 3b：RiskConfig flag dormancy（env=1 但 config.enabled=false → Disabled）。
// ---------------------------------------------------------------------------

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn dual_safeguard_risk_config_disabled_short_circuits() {
    let advisor = CostEdgeAdvisor::new_arc();
    let cache = h_state_cache_with_trigger_ratio(); // ratio < threshold
    let risk = risk_config_advisor_disabled_in_config(); // but cfg.enabled=false
    let cancel = CancellationToken::new();

    // Spawn daemon (note: bypasses `is_advisor_env_enabled()` check by
    // calling the inner `spawn_cost_edge_advisor` directly — the env-gate
    // wraps the spawn decision, but the daemon body itself respects
    // RiskConfig.cost_edge.enabled). This isolates the SECOND safeguard.
    // Spawn daemon（直呼內層 spawn 跳過 env-gate；env-gate 包外層 spawn 決策、
    // daemon body 自己尊重 RiskConfig.cost_edge.enabled）— 隔離第二保險。
    let handle = spawn_cost_edge_advisor(
        Arc::clone(&advisor),
        Arc::clone(&cache),
        Arc::clone(&risk),
        Duration::from_millis(100),
        cancel.clone(),
    );

    // Wait for daemon to complete first cycle.
    // 等 daemon 首輪 cycle。
    let deadline = Instant::now() + Duration::from_secs(1);
    while Instant::now() < deadline {
        if advisor.state().status != CostEdgeAdvisorStatus::Uninitialized {
            break;
        }
        tokio::time::sleep(Duration::from_millis(20)).await;
    }

    let final_state = advisor.state();

    cancel.cancel();
    let _ = handle.await;

    // Despite env=1 (here the implicit assumption from spawn) and a Trigger-
    // inducing H5 ratio (-0.8 <= -0.5), Disabled wins because RiskConfig
    // flag short-circuits BEFORE the H5 read (per advisor::evaluate Step 1).
    // 即使 env=1（spawn 隱含）+ H5 為 Trigger ratio (-0.8 <= -0.5)，
    // Disabled 仍勝出，因 RiskConfig flag 在 H5 讀取前 short-circuit
    // (advisor::evaluate Step 1)。
    assert_eq!(
        final_state.status,
        CostEdgeAdvisorStatus::Disabled,
        "RiskConfig.cost_edge.enabled=false must force Disabled even when \
         env=1 + H5 has Trigger-inducing ratio (got {:?})",
        final_state.status
    );
    assert!(
        final_state.ratio.is_none(),
        "Disabled state must not echo H5 ratio (short-circuit before H5 read); \
         got ratio={:?}",
        final_state.ratio
    );
    assert_eq!(
        final_state.threshold, -0.5,
        "threshold should still be echoed for audit completeness even in Disabled"
    );
}

// ---------------------------------------------------------------------------
// Sticky `triggered_at_ms` proofs (G3-09-PHASE-B-FUP-STICKY-TS, 2026-04-28).
//
// Pure `evaluate()` always returns `triggered_at_ms = now_ms` for any
// Trigger state — that is correct only on the entering transition. The
// daemon (mod.rs ~L240) enforces sticky semantics by overwriting the
// field with the previously stored entry timestamp on contiguous
// Trigger→Trigger cycles. Phase B observation, dedup analytics, and the
// `last_trigger_ms` rolling counter all depend on this. The two tests
// below cover the two essential properties: (a) the first entry captures
// `now_ms`, and (b) successive cycles preserve the original timestamp
// (stickiness) across multiple polls.
// 純 `evaluate()` 對任何 Trigger 永遠回 `triggered_at_ms = now_ms`，僅 entering
// transition 正確。Daemon（mod.rs 約 L240）強制 sticky：contiguous
// Trigger→Trigger 覆寫為前次儲存值。Phase B observation / dedup analytics /
// `last_trigger_ms` rolling counter 全依賴此。下方兩 test 覆蓋兩個核心性質：
// (a) 首次進入抓 `now_ms`、(b) 後續 cycle 跨多 poll 保留原時戳（sticky）。
// ---------------------------------------------------------------------------

/// Build an H state cache populated with a Trigger snapshot whose
/// `fetched_at_ms` is set to a fixed past value so the freshness window
/// stays inside the cache's stale threshold for the duration of the test.
/// Used by the sticky-timestamp tests so multiple daemon cycles all see
/// the same Trigger ratio without a snapshot mutation in between.
/// 建一個含 Trigger snapshot 的 H state cache，`fetched_at_ms` 設為固定值
/// 確保測試期間 cache 不變 stale。Sticky 時戳測試用，讓 daemon 多輪 cycle
/// 看到同一 Trigger ratio。
fn h_state_cache_with_persistent_trigger() -> Arc<HStateCache> {
    let cache = HStateCache::new_arc();
    let store_ms = now_ms();
    let snap = HStateSnapshot {
        version: 1,
        fetched_at_ms: store_ms,
        h5: H5CostStats {
            ai_spend_7d_usd: 12.0,
            paper_pnl_7d_usd: -9.0,
            cost_edge_ratio: Some(-0.75), // <= -0.5 threshold → Trigger
            data_days: 7,
        },
        ..Default::default()
    };
    cache.store_snapshot(snap, store_ms);
    cache
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn sticky_triggered_at_ms_records_first_entry_into_trigger() {
    // Cover property (a): the very first Trigger cycle stamps
    // `triggered_at_ms` with the daemon's current `now_ms` and propagates
    // it through `store_state`. Without sticky enforcement this would
    // already pass (since `evaluate()` returns `now_ms`); this test exists
    // as the regression guard against a future "always zero" or
    // "always epoch 0" mistake when refactoring sticky logic.
    // 覆蓋性質 (a)：首次進 Trigger cycle 把 `triggered_at_ms` 設為 daemon
    // 當下 `now_ms` 並透過 `store_state` 暴露。無 sticky 邏輯本測試也會綠
    // （evaluate 本就回 now_ms），存在價值是 sticky 重構時防退化（避免
    // 未來改成「永遠 0」或「永遠 epoch 0」）。

    let advisor = CostEdgeAdvisor::new_arc();
    let cache = h_state_cache_with_persistent_trigger();
    let risk = risk_config_advisor_enabled();
    let cancel = CancellationToken::new();

    let before_spawn_ms = now_ms();

    let handle = spawn_cost_edge_advisor(
        Arc::clone(&advisor),
        Arc::clone(&cache),
        Arc::clone(&risk),
        Duration::from_millis(100),
        cancel.clone(),
    );

    // Wait up to 1s for daemon to write the first Trigger state.
    // 等最多 1s 給 daemon 寫入首個 Trigger state。
    let deadline = Instant::now() + Duration::from_secs(1);
    while Instant::now() < deadline {
        if advisor.state().status == CostEdgeAdvisorStatus::Trigger {
            break;
        }
        tokio::time::sleep(Duration::from_millis(20)).await;
    }

    let first_state = advisor.state();
    let after_first_ms = now_ms();

    cancel.cancel();
    let _ = handle.await;

    assert_eq!(
        first_state.status,
        CostEdgeAdvisorStatus::Trigger,
        "first poll should land on Trigger (got {:?})",
        first_state.status
    );
    // The entry timestamp must be a real epoch ms inside [before_spawn_ms,
    // after_first_ms] — proving daemon stamped it from `now_ms` at the
    // entering transition, not left it as `0` and not pulled from a stale
    // future/past clock.
    // 進入時戳必為合理 epoch ms 落在 [before_spawn_ms, after_first_ms] —
    // 證明 daemon 於進入 transition 從 `now_ms` 寫入，不是 `0`、也非
    // 未來/過去離譜時鐘。
    assert!(
        first_state.triggered_at_ms >= before_spawn_ms
            && first_state.triggered_at_ms <= after_first_ms,
        "triggered_at_ms ({}) should be within spawn window [{}, {}] — \
         daemon must stamp now_ms at the entering Trigger transition",
        first_state.triggered_at_ms,
        before_spawn_ms,
        after_first_ms
    );
    assert!(
        first_state.triggered_at_ms > 0,
        "triggered_at_ms must be a positive epoch ms (got {})",
        first_state.triggered_at_ms
    );
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn sticky_triggered_at_ms_preserved_across_contiguous_trigger_cycles() {
    // Cover property (b): once in a Trigger run, subsequent Trigger→Trigger
    // cycles MUST keep the original entry `triggered_at_ms` even though
    // `evaluate()` returns a fresh `now_ms` every cycle, AND `last_eval_ms`
    // continues to advance. Without daemon sticky enforcement the field
    // would tick forward each cycle, breaking Phase B `last_trigger_ms`
    // rolling counter and any future dedup logic that fires "once per
    // Trigger episode".
    // 覆蓋性質 (b)：進 Trigger run 後，後續 Trigger→Trigger cycle 必須保留
    // 原進入 `triggered_at_ms` 不變，即使 `evaluate()` 每 cycle 回新
    // `now_ms` 且 `last_eval_ms` 持續推進。無 daemon sticky 強制此欄會每
    // cycle 跟著走，破壞 Phase B `last_trigger_ms` 與任何「per-episode
    // 一次」dedup 邏輯。

    let advisor = CostEdgeAdvisor::new_arc();
    let cache = h_state_cache_with_persistent_trigger();
    let risk = risk_config_advisor_enabled();
    let cancel = CancellationToken::new();

    // Use 100ms cadence so we can collect ≥3 Trigger cycles within ~500ms.
    // 100ms cadence 讓我們在 ~500ms 內收 ≥3 個 Trigger cycle。
    const POLL_MS: u64 = 100;
    let handle = spawn_cost_edge_advisor(
        Arc::clone(&advisor),
        Arc::clone(&cache),
        Arc::clone(&risk),
        Duration::from_millis(POLL_MS),
        cancel.clone(),
    );

    // Capture distinct Trigger cycles by tracking advancing `last_eval_ms`.
    // 用推進的 `last_eval_ms` 抓不同 Trigger cycle。
    let mut trigger_samples: Vec<(i64, i64)> = Vec::with_capacity(3); // (last_eval_ms, triggered_at_ms)
    let mut last_seen_eval_ms: i64 = 0;
    let hard_deadline = Instant::now() + Duration::from_millis(POLL_MS * 12); // ~1.2s ceiling

    while trigger_samples.len() < 3 && Instant::now() < hard_deadline {
        let s = advisor.state();
        if s.status == CostEdgeAdvisorStatus::Trigger && s.last_eval_ms > last_seen_eval_ms {
            trigger_samples.push((s.last_eval_ms, s.triggered_at_ms));
            last_seen_eval_ms = s.last_eval_ms;
        }
        tokio::time::sleep(Duration::from_millis(POLL_MS / 5)).await;
    }

    cancel.cancel();
    let _ = handle.await;

    assert!(
        trigger_samples.len() >= 3,
        "expected ≥3 distinct Trigger cycles within hard deadline; \
         got {} samples (samples={:?})",
        trigger_samples.len(),
        trigger_samples
    );

    // (b1) `last_eval_ms` must advance across cycles — proves we really
    // observed multiple distinct daemon cycles, not the same snapshot
    // sampled three times.
    // (b1) `last_eval_ms` 跨 cycle 必推進 — 證明我們真觀察到多輪不同 daemon
    // cycle 而非同一 snapshot 採樣 3 次。
    for w in trigger_samples.windows(2) {
        assert!(
            w[1].0 > w[0].0,
            "last_eval_ms must advance across Trigger cycles; \
             got identical or regressing sequence {:?}",
            trigger_samples
        );
    }

    // (b2) `triggered_at_ms` MUST be identical across all cycles in this
    // contiguous Trigger run — this is THE sticky-semantics guarantee.
    // (b2) `triggered_at_ms` 在此 contiguous Trigger run 跨所有 cycle 必相同 —
    // 此即 sticky 語意核心保證。
    let first_triggered_at = trigger_samples[0].1;
    for (idx, (eval_ms, triggered_at)) in trigger_samples.iter().enumerate() {
        assert_eq!(
            *triggered_at, first_triggered_at,
            "triggered_at_ms must be sticky across contiguous Trigger cycles; \
             cycle {} has triggered_at_ms={} but cycle 0 had {} \
             (eval_ms={}; full samples={:?})",
            idx, triggered_at, first_triggered_at, eval_ms, trigger_samples
        );
    }
    assert!(
        first_triggered_at > 0,
        "first triggered_at_ms must be positive epoch ms (got {})",
        first_triggered_at
    );
}
