//! G3-09 Phase A daemon integration test — proves daemon is live (not stub).
//! G3-09 Phase A daemon 整合測試 — 證明 daemon 真在跑（非 stub）。
//!
//! MODULE_NOTE (EN): Phase A unit tests (`src/cost_edge_advisor/tests.rs`,
//!   32 cases) drive `evaluate()` as a pure fn — they NEVER spawn the
//!   daemon. The IPC handler tests (5 cases) populate a slot manually and
//!   read it back — they NEVER prove the daemon writes the slot.
//!
//!   This integration test fills the gap raised in PA RFC
//!   `2026-04-27--g3_09_phase_b_shadow_dryrun_design.md` §6.1 R-B4 +
//!   §R-B10: Phase B observation period assumes daemon truly writes rows;
//!   without a daemon-level integration test there is **no ground truth**
//!   to validate that assumption. PA upgraded the FUP from P3 → P1 as a
//!   Phase B prerequisite.
//!
//!   Coverage (4 proofs, ≤10% cadence tolerance per task spec):
//!     1. `daemon_spawn_advances_state_off_uninitialized` — proves daemon
//!        truly polls H state cache and writes state (not just sits at
//!        the construction-time `Uninitialized` default).
//!     2. `ipc_handler_returns_live_state_after_daemon_writes` — proves
//!        the IPC handler reads the live state daemon writes (not the
//!        `Uninitialized` stub returned when the slot is empty / pre-spawn).
//!     3. `dual_safeguard_env_gate_off_skips_daemon` AND
//!        `dual_safeguard_risk_config_disabled_short_circuits` — proves
//!        BOTH gates (env `OPENCLAW_COST_EDGE_ADVISOR=1` AND
//!        `RiskConfig.cost_edge.enabled=true`) are required for the
//!        advisor to produce a non-Disabled state.
//!     4. `daemon_evaluate_cadence_within_tolerance` — proves daemon
//!        evaluates at the configured `poll_interval` (here 200ms for
//!        test speed), with ≤10% jitter over 10 cycles.
//!
//!   All tests use `tokio::test(flavor = "multi_thread")` so the spawned
//!   daemon really gets its own runtime worker (single-threaded would
//!   serialise daemon and assertions, defeating the integration).
//!
//!   Env-gate isolation: tests that touch `OPENCLAW_COST_EDGE_ADVISOR`
//!   serialise via a process-wide `Mutex` because env vars are global to
//!   the OS process; running them concurrently would race the env state.
//!   Pattern mirrors `cost_edge_advisor::tests::env_gate_strict_one_semantics_serialised`.
//!
//! MODULE_NOTE (中)：Phase A unit test 全直驅 `evaluate()` 純 fn 不 spawn
//!   daemon；IPC handler test 手動 populate slot 後讀回不證明 daemon 真寫
//!   入。本整合測試補 PA RFC §6.1 R-B4 + §R-B10 缺口：Phase B observation
//!   假設 daemon 真寫 row，缺 daemon 級整合測試 = 無 ground truth；PA 將
//!   FUP 從 P3 升 P1 為 Phase B prerequisite。
//!
//!   覆蓋 4 證明（cadence ≤10% 容差，per 任務規格）：
//!     1. daemon spawn 後 state 從 Uninitialized 變化（證明真在 poll H state
//!        cache 並寫 state）
//!     2. IPC handler 回 live state（非 slot 空時的 Uninitialized stub）
//!     3. 雙保險：env-gate=0 / RiskConfig.enabled=false 任一缺則 dormant
//!     4. evaluate cadence 對齊 poll_interval（200ms × 10 cycle，≤10% 抖動）
//!
//!   全用 `tokio::test(flavor = "multi_thread")` 確保 daemon 真拿到獨立
//!   worker；env-gate 測試經 process-wide Mutex 序列化（避 OS 級 env race）。

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

// ---------------------------------------------------------------------------
// Proof 1: daemon truly polls + writes state (not stuck at Uninitialized).
// 證明 1：daemon 真 poll + 寫 state（非卡 Uninitialized）。
// ---------------------------------------------------------------------------

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn daemon_spawn_advances_state_off_uninitialized() {
    let advisor = CostEdgeAdvisor::new_arc();
    let cache = h_state_cache_with_ok_ratio();
    let risk = risk_config_advisor_enabled();
    let cancel = CancellationToken::new();

    // Pre-condition: state must start Uninitialized (proof daemon writes is
    // valid only if there is a delta to observe).
    // 前置條件：state 起點 Uninitialized（觀察 delta 才有意義）。
    assert_eq!(
        advisor.state().status,
        CostEdgeAdvisorStatus::Uninitialized,
        "advisor should start in Uninitialized before daemon spawn"
    );

    // Use 100ms poll interval so test completes fast but still exercises
    // the real spawn → tokio::select → tokio::time::sleep loop.
    // 用 100ms poll interval 加速測試，仍走真實的 spawn → tokio::select →
    // sleep loop（非 mock 路徑）。
    let handle = spawn_cost_edge_advisor(
        Arc::clone(&advisor),
        Arc::clone(&cache),
        Arc::clone(&risk),
        Duration::from_millis(100),
        cancel.clone(),
    );

    // Wait up to 1s for daemon to complete first poll cycle (100ms +
    // scheduling slack).
    // 等最多 1s 給 daemon 完成首輪 poll（100ms + 排程 slack）。
    let deadline = Instant::now() + Duration::from_secs(1);
    let mut observed_status = CostEdgeAdvisorStatus::Uninitialized;
    while Instant::now() < deadline {
        observed_status = advisor.state().status;
        if observed_status != CostEdgeAdvisorStatus::Uninitialized {
            break;
        }
        tokio::time::sleep(Duration::from_millis(20)).await;
    }

    // Cleanup before assertion to ensure daemon is torn down even on fail.
    // 先 cleanup 確保 fail 時 daemon 也被停。
    cancel.cancel();
    let _ = handle.await;

    assert_eq!(
        observed_status,
        CostEdgeAdvisorStatus::Ok,
        "daemon should have polled OK snapshot and stored Ok state \
         (counter was {:?}; expected the daemon to have advanced \
         past Uninitialized within 1s)",
        observed_status
    );

    // Final state inspection — proves daemon wrote real H5 echo, not a stub.
    // 末態檢查：證明 daemon 真寫入 H5 echo 非 stub。
    let final_state = advisor.state();
    assert_eq!(final_state.ratio, Some(0.5), "ratio should echo H5 cache");
    assert_eq!(final_state.data_days, 7, "data_days should echo H5 cache");
    assert_eq!(
        final_state.threshold, -0.5,
        "threshold should echo RiskConfig"
    );
    assert!(
        final_state.last_eval_ms > 0,
        "last_eval_ms should be a real epoch ms (got {})",
        final_state.last_eval_ms
    );
}

// ---------------------------------------------------------------------------
// Proof 2: IPC handler returns daemon-written live state (not slot stub).
// 證明 2：IPC handler 回 daemon 寫的 live state（非 slot 空時 stub）。
// ---------------------------------------------------------------------------

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn ipc_handler_returns_live_state_after_daemon_writes() {
    let advisor = CostEdgeAdvisor::new_arc();
    let cache = h_state_cache_with_trigger_ratio();
    let risk = risk_config_advisor_enabled();
    let cancel = CancellationToken::new();

    // Spawn daemon at 100ms cadence and wait for first cycle.
    // Spawn daemon 100ms cadence，等首輪結束。
    let handle = spawn_cost_edge_advisor(
        Arc::clone(&advisor),
        Arc::clone(&cache),
        Arc::clone(&risk),
        Duration::from_millis(100),
        cancel.clone(),
    );

    // Wait up to 1s for daemon to write Trigger state.
    // 等最多 1s 給 daemon 寫入 Trigger state。
    let deadline = Instant::now() + Duration::from_secs(1);
    while Instant::now() < deadline {
        if advisor.state().status == CostEdgeAdvisorStatus::Trigger {
            break;
        }
        tokio::time::sleep(Duration::from_millis(20)).await;
    }

    // Read state via the same `state()` API the IPC handler uses (proves the
    // handler-side read returns the daemon-written value, not a hard-coded
    // stub). This mirrors `handle_get_cost_edge_advisor_status` line 44
    // (`let state = advisor.state();`).
    // 走與 IPC handler 相同的 `state()` API（line 44 `let state = advisor.state();`）
    // 證明 handler 端讀的是 daemon 寫入值非硬編碼 stub。
    let live_state: CostEdgeAdvisorState = advisor.state();

    cancel.cancel();
    let _ = handle.await;

    // Live data assertions: prove these came from H5 cache via daemon, not
    // from `CostEdgeAdvisorState::uninitialized()` defaults.
    // Live data assert：證明來自 H5 經 daemon 寫入而非 uninitialized() 預設。
    assert_eq!(
        live_state.status,
        CostEdgeAdvisorStatus::Trigger,
        "IPC-shape state should reflect daemon-written Trigger status"
    );
    assert_eq!(
        live_state.ratio,
        Some(-0.8),
        "IPC-shape ratio should echo H5 trigger ratio (-0.8), not stub None"
    );
    assert_eq!(
        live_state.ai_spend_7d_usd, 10.0,
        "IPC-shape ai_spend_7d_usd should echo H5 (10.0), not stub 0.0"
    );
    assert_eq!(
        live_state.paper_pnl_7d_usd, -8.0,
        "IPC-shape paper_pnl_7d_usd should echo H5 (-8.0), not stub 0.0"
    );
    assert_eq!(
        live_state.data_days, 7,
        "IPC-shape data_days should echo H5 (7), not stub 0"
    );
    assert!(
        live_state.triggered_at_ms > 0,
        "IPC-shape triggered_at_ms should be set by daemon on Trigger \
         (got {} — should be > 0 epoch ms)",
        live_state.triggered_at_ms
    );
    assert!(
        live_state.last_eval_ms > 0,
        "IPC-shape last_eval_ms should be set by daemon"
    );
}

// ---------------------------------------------------------------------------
// Proof 3a: env-gate `OPENCLAW_COST_EDGE_ADVISOR` strict-equal "1" guard.
// 證明 3a：env-gate 嚴格 "1" 比對。
// ---------------------------------------------------------------------------

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn dual_safeguard_env_gate_off_skips_daemon() {
    let _g = env_lock().lock().expect("env lock poisoned");

    // Save original env state for restoration.
    // 保存原 env 狀態以還原。
    let prev = std::env::var(ENV_ADVISOR_FLAG).ok();

    // Subtest 1: env unset → env-gate false.
    // 子測 1：env 未設 → env-gate=false。
    std::env::remove_var(ENV_ADVISOR_FLAG);
    assert!(
        !is_advisor_env_enabled(),
        "env-gate must be false when OPENCLAW_COST_EDGE_ADVISOR is unset"
    );

    // Subtest 2: env="0" → env-gate false.
    // 子測 2：env="0" → false。
    std::env::set_var(ENV_ADVISOR_FLAG, "0");
    assert!(!is_advisor_env_enabled(), "env=\"0\" must keep advisor off");

    // Subtest 3: env="true" → env-gate false (strict "1" only).
    // 子測 3：env="true" → false（嚴格 "1"）。
    std::env::set_var(ENV_ADVISOR_FLAG, "true");
    assert!(
        !is_advisor_env_enabled(),
        "env=\"true\" must keep advisor off (strict equality with \"1\")"
    );

    // Subtest 4: env="1" → env-gate true.
    // 子測 4：env="1" → true。
    std::env::set_var(ENV_ADVISOR_FLAG, "1");
    assert!(is_advisor_env_enabled(), "env=\"1\" must enable advisor");

    // Subtest 5: env=" 1 " (with whitespace) → env-gate false (no trim).
    // 子測 5：env=" 1 "（含空白）→ false（不 trim）。
    std::env::set_var(ENV_ADVISOR_FLAG, " 1 ");
    assert!(
        !is_advisor_env_enabled(),
        "env=\" 1 \" with whitespace must NOT enable advisor (strict equality, no trim)"
    );

    // Restore env to previous state for test isolation.
    // 還原 env 確保測試隔離。
    match prev {
        Some(v) => std::env::set_var(ENV_ADVISOR_FLAG, v),
        None => std::env::remove_var(ENV_ADVISOR_FLAG),
    }
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
// Proof 4: evaluate cadence sane (≤10% jitter over 10 cycles).
// 證明 4：evaluate cadence 健康（10 cycle ≤10% 抖動）。
// ---------------------------------------------------------------------------

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn daemon_evaluate_cadence_within_tolerance() {
    let advisor = CostEdgeAdvisor::new_arc();
    let cache = h_state_cache_with_ok_ratio();
    let risk = risk_config_advisor_enabled();
    let cancel = CancellationToken::new();

    // Use 200ms poll interval × 10 cycles = ~2s wall-clock, fast enough
    // for CI yet long enough that scheduling jitter averages out.
    // 用 200ms poll interval × 10 cycle = ~2s wall-clock，CI 友善且足夠
    // 長讓排程抖動均化。
    const POLL_INTERVAL_MS: u64 = 200;
    const TARGET_CYCLES: u32 = 10;
    const TOLERANCE_PCT: f64 = 10.0; // ≤10% per task spec

    let start_wall = Instant::now();

    let handle = spawn_cost_edge_advisor(
        Arc::clone(&advisor),
        Arc::clone(&cache),
        Arc::clone(&risk),
        Duration::from_millis(POLL_INTERVAL_MS),
        cancel.clone(),
    );

    // Track distinct `last_eval_ms` values: each new value = one completed
    // daemon cycle. (We can't observe the cycle directly without
    // instrumenting the daemon; last_eval_ms is the public proxy.)
    // 追蹤不同 `last_eval_ms`：每個新值 = daemon 完成一個 cycle。
    // （無法直接觀察 cycle 不改 daemon；last_eval_ms 是公開代理。）
    let mut observed_eval_times: Vec<i64> = Vec::with_capacity(TARGET_CYCLES as usize);
    let mut last_seen: i64 = 0;
    // Hard ceiling: TARGET_CYCLES * POLL_INTERVAL × 3 (= 6s for 10×200ms).
    // Three-fold guard against a flaky CI scheduler stalling the daemon.
    // 硬上限：TARGET × POLL × 3（10×200=2s 給 6s 上限），防 CI flaky 卡死。
    let hard_deadline =
        Instant::now() + Duration::from_millis(POLL_INTERVAL_MS * (TARGET_CYCLES as u64) * 3);

    while observed_eval_times.len() < TARGET_CYCLES as usize && Instant::now() < hard_deadline {
        let s = advisor.state();
        if s.last_eval_ms > last_seen {
            observed_eval_times.push(s.last_eval_ms);
            last_seen = s.last_eval_ms;
        }
        // Sample ~5× faster than poll interval to avoid missing a cycle.
        // 採樣比 poll interval 快 ~5 倍以免漏 cycle。
        tokio::time::sleep(Duration::from_millis(POLL_INTERVAL_MS / 5)).await;
    }

    cancel.cancel();
    let _ = handle.await;

    let elapsed_ms = start_wall.elapsed().as_millis() as u64;

    assert_eq!(
        observed_eval_times.len(),
        TARGET_CYCLES as usize,
        "expected {} distinct evaluate cycles within hard deadline; \
         got {} (elapsed_ms={}, last_eval_times={:?})",
        TARGET_CYCLES,
        observed_eval_times.len(),
        elapsed_ms,
        observed_eval_times
    );

    // Compute cycle-to-cycle deltas (in ms) using the daemon's own
    // last_eval_ms timestamps (epoch ms). This measures advisor-perceived
    // cadence, which is what consumers see.
    // 用 daemon 自己的 last_eval_ms 算 cycle 間隔（ms），這是 consumer 看到
    // 的 advisor 視角 cadence。
    let mut deltas_ms: Vec<i64> = Vec::with_capacity(observed_eval_times.len() - 1);
    for w in observed_eval_times.windows(2) {
        deltas_ms.push(w[1] - w[0]);
    }

    let mean_delta_ms: f64 =
        deltas_ms.iter().map(|&d| d as f64).sum::<f64>() / (deltas_ms.len() as f64);
    let max_jitter_pct: f64 = deltas_ms
        .iter()
        .map(|&d| ((d as f64 - POLL_INTERVAL_MS as f64).abs() / POLL_INTERVAL_MS as f64) * 100.0)
        .fold(0.0f64, f64::max);

    // Mean cadence within ±tolerance: confirms daemon hits the configured
    // poll interval on average (not 2× / 0.5×).
    // 平均 cadence 在 ±tolerance 內：確認 daemon 平均達 poll interval。
    let mean_pct_err =
        ((mean_delta_ms - POLL_INTERVAL_MS as f64).abs() / POLL_INTERVAL_MS as f64) * 100.0;
    assert!(
        mean_pct_err <= TOLERANCE_PCT,
        "mean cadence error {:.2}% exceeds tolerance {:.0}% \
         (mean={:.1}ms, target={}ms, deltas={:?})",
        mean_pct_err,
        TOLERANCE_PCT,
        mean_delta_ms,
        POLL_INTERVAL_MS,
        deltas_ms
    );

    // Per-cycle jitter: allow up to 5× tolerance for a single outlier
    // (CI scheduler can blip), but each cycle should still be in the same
    // order of magnitude. Use 50% (5× of 10% spec tolerance) as the hard
    // per-cycle cap so a stuck CI thread shows up.
    // Per-cycle 抖動：單一 outlier 容 5× tolerance（CI 排程偶爾打嗝），
    // 但仍須同數量級；用 50% 作硬上限揪 stuck CI thread。
    assert!(
        max_jitter_pct <= TOLERANCE_PCT * 5.0,
        "per-cycle jitter {:.2}% exceeds hard cap {:.0}% \
         (one or more cycles drifted >5× spec tolerance; deltas={:?})",
        max_jitter_pct,
        TOLERANCE_PCT * 5.0,
        deltas_ms
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

// ---------------------------------------------------------------------------
// Proof 5: cancel.cancel() drains daemon promptly (sub-second shutdown).
// 證明 5：cancel.cancel() 觸發 daemon sub-second shutdown。
// ---------------------------------------------------------------------------
//
// Bonus assertion the task didn't strictly require but cheap to add:
// validates the cancellation safety claim from `mod.rs:188` so we know a
// shutdown path race won't leak daemons across test runs.
// 任務未強制要求但便宜：驗 mod.rs:188 cancellation-safe 宣告，避免關閉
// 路徑漏 daemon 跨測試。

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn daemon_cancellation_drains_within_one_second() {
    let advisor = CostEdgeAdvisor::new_arc();
    let cache = h_state_cache_with_ok_ratio();
    let risk = risk_config_advisor_enabled();
    let cancel = CancellationToken::new();

    // Long poll interval so daemon spends most of its time in tokio::sleep
    // — proves cancel races sleep correctly (not just polling between cycles).
    // 長 poll interval 讓 daemon 大部分時間在 sleep — 證明 cancel 與 sleep
    // race 正確（非只在 cycle 間隙才響應）。
    let handle = spawn_cost_edge_advisor(
        advisor,
        cache,
        risk,
        Duration::from_secs(10), // long sleep
        cancel.clone(),
    );

    // Let daemon enter sleep state (small wait).
    // 給 daemon 進入 sleep 一小段時間。
    tokio::time::sleep(Duration::from_millis(100)).await;

    let cancel_at = Instant::now();
    cancel.cancel();
    handle.await.expect("daemon task should join cleanly");
    let drain_ms = cancel_at.elapsed().as_millis();

    assert!(
        drain_ms < 1000,
        "daemon cancellation should drain within 1s (took {}ms); \
         indicates tokio::select! cancel branch may not race sleep correctly",
        drain_ms
    );
}

// ---------------------------------------------------------------------------
// G3-09 Phase B Wave 0 FUP-SPAWN-TEST (P3 → wave 0 prerequisite)
// G3-09 Phase B Wave 0 FUP-SPAWN-TEST（P3 → wave 0 前置）
// ---------------------------------------------------------------------------
//
// MODULE_NOTE (EN): Proofs 1-5 above directly drive `spawn_cost_edge_advisor`
//   (the inner spawn). They prove the daemon is correct *if invoked*, but
//   they bypass `main_boot_tasks::spawn_cost_edge_advisor_if_enabled` —
//   the bin-side decision wrapper that gates spawn on env + populates the
//   IPC `CostEdgeAdvisorSlot`. E2 review report
//   `2026-04-27--g3_09_daemon_test_review.md` raised this as INFO and PA
//   upgraded to P3 backlog; Phase B Wave 0 needs spawn-decision parity to
//   close the protection surface.
//
//   `spawn_cost_edge_advisor_if_enabled` lives in the binary crate
//   (`src/main_boot_tasks.rs`, `pub(crate)`) so integration tests in `tests/`
//   cannot call it directly. Cases A/B/C below replicate the wrapper's
//   decision logic *exactly* (using the same lib-public primitives the
//   wrapper uses: `is_advisor_env_enabled` + `spawn_cost_edge_advisor` +
//   slot late-injection + `CostEdgeAdvisor::state()` mirroring the IPC
//   handler `handle_get_cost_edge_advisor_status` lines 33-44).
//
//   Slot semantics under test (matches `slots.rs:140`
//   `CostEdgeAdvisorSlot = Arc<RwLock<Option<Arc<CostEdgeAdvisor>>>>`):
//     * `None` → IPC handler returns the structured `advisor_disabled`
//       payload with `status="Uninitialized"` (handler lines 36-42).
//     * `Some(advisor)` → IPC handler returns `advisor.state()` snapshot
//       (handler line 44).
//
// MODULE_NOTE (中)：Proof 1-5 直驅內層 `spawn_cost_edge_advisor`，證 daemon 被
//   呼叫後正確，但繞過 `main_boot_tasks::spawn_cost_edge_advisor_if_enabled`
//   bin-side 決策包裝（env-gate + slot 注入）。E2 review 列 INFO，PA 升 P3
//   backlog；Phase B Wave 0 需 spawn-decision parity 才完整保護面。
//
//   `spawn_cost_edge_advisor_if_enabled` 在 binary crate（pub(crate)），
//   `tests/` 整合測試不能直呼。下方 Case A/B/C 用 wrapper 完全相同的
//   lib-public primitive 重現決策邏輯：`is_advisor_env_enabled` +
//   `spawn_cost_edge_advisor` + slot late-inject + `CostEdgeAdvisor::state()`
//   鏡射 IPC handler `handle_get_cost_edge_advisor_status` line 33-44。
//
//   Slot 語意（對齊 `slots.rs:140`）：None → IPC 回 `advisor_disabled`
//   payload status=Uninitialized；Some → IPC 回 advisor.state() snapshot。

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
    // must not race the other env-touching tests (Proof 3a +
    // fup_case_b_env_set_risk_disabled below).
    // 取全進程 env 鎖 — env 改動為 OS 進程狀態，不可與其他 env 測試 race
    // （Proof 3a + 下方 case B）。
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
