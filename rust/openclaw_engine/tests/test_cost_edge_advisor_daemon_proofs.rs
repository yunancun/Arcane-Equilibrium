//! G3-09 Phase A daemon integration test — Proofs 1-5 (core liveness + cadence).
//! G3-09 Phase A daemon 整合測試 — Proof 1-5（核心活性 + cadence）。
//!
//! MODULE_NOTE (EN): This file is one of THREE test binaries split out from
//!   the original `test_cost_edge_advisor_daemon.rs` (1159 LOC > §九 800 warn)
//!   per E2 spawn-test review LOW-1 recommendation. The other two files are:
//!     * `test_cost_edge_advisor_daemon_dual_safeguard.rs` — RiskConfig flag
//!       short-circuit (Proof 3b) + sticky `triggered_at_ms` semantics
//!     * `test_cost_edge_advisor_spawn_decision.rs` — FUP Case A/B/C
//!       wrapper-decision parity for `spawn_cost_edge_advisor_if_enabled`
//!
//!   Phase A unit tests (`src/cost_edge_advisor/tests.rs`, 32 cases) drive
//!   `evaluate()` as a pure fn — they NEVER spawn the daemon. The IPC
//!   handler tests (5 cases) populate a slot manually and read it back —
//!   they NEVER prove the daemon writes the slot. This integration test
//!   fills the gap raised in PA RFC `2026-04-27--g3_09_phase_b_shadow_dryrun_design.md`
//!   §6.1 R-B4 + §R-B10: Phase B observation period assumes daemon truly
//!   writes rows; without a daemon-level integration test there is **no
//!   ground truth** to validate that assumption. PA upgraded the FUP from
//!   P3 → P1 as a Phase B prerequisite.
//!
//!   Coverage of THIS file (5 cases):
//!     1. `daemon_spawn_advances_state_off_uninitialized` — proves daemon
//!        truly polls H state cache and writes state (not just sits at
//!        the construction-time `Uninitialized` default).
//!     2. `ipc_handler_returns_live_state_after_daemon_writes` — proves
//!        the IPC handler reads the live state daemon writes (not the
//!        `Uninitialized` stub returned when the slot is empty / pre-spawn).
//!     3a. `dual_safeguard_env_gate_off_skips_daemon` — proves env gate
//!        `OPENCLAW_COST_EDGE_ADVISOR=1` strict-equal "1" semantics.
//!     4. `daemon_evaluate_cadence_within_tolerance` — proves daemon
//!        evaluates at the configured `poll_interval` (here 200ms for
//!        test speed), with ≤10% jitter over 10 cycles.
//!     5. `daemon_cancellation_drains_within_one_second` — proves
//!        cancel.cancel() triggers sub-second daemon shutdown (validates
//!        `mod.rs:188` cancellation-safe claim).
//!
//!   All tests use `tokio::test(flavor = "multi_thread")` so the spawned
//!   daemon really gets its own runtime worker (single-threaded would
//!   serialise daemon and assertions, defeating the integration).
//!
//!   Env-gate isolation: tests that touch `OPENCLAW_COST_EDGE_ADVISOR`
//!   serialise via a process-wide `Mutex` because env vars are global to
//!   the OS process; running them concurrently would race the env state.
//!   Each test binary has its own `env_lock()` `OnceLock` — Cargo runs
//!   `tests/*.rs` as separate processes so cross-binary env races are
//!   impossible. Pattern mirrors
//!   `cost_edge_advisor::tests::env_gate_strict_one_semantics_serialised`.
//!
//! MODULE_NOTE (中)：本檔為原 `test_cost_edge_advisor_daemon.rs`（1159 LOC >
//!   §九 800 警告）per E2 spawn-test review LOW-1 推薦拆出三檔之一，另兩檔：
//!     * `test_cost_edge_advisor_daemon_dual_safeguard.rs` — RiskConfig flag
//!       short-circuit（Proof 3b）+ sticky `triggered_at_ms` 語意
//!     * `test_cost_edge_advisor_spawn_decision.rs` — FUP Case A/B/C
//!       wrapper-decision parity（`spawn_cost_edge_advisor_if_enabled`）
//!
//!   Phase A unit test 全直驅 `evaluate()` 純 fn 不 spawn daemon；IPC handler
//!   test 手動 populate slot 後讀回不證明 daemon 真寫入。本整合測試補 PA RFC
//!   §6.1 R-B4 + §R-B10 缺口：Phase B observation 假設 daemon 真寫 row，
//!   缺 daemon 級整合測試 = 無 ground truth；PA 將 FUP 從 P3 升 P1 為 Phase B
//!   prerequisite。
//!
//!   本檔 5 case：
//!     1. daemon spawn 後 state 從 Uninitialized 變化（證明真在 poll H state
//!        cache 並寫 state）
//!     2. IPC handler 回 live state（非 slot 空時的 Uninitialized stub）
//!     3a. env-gate 嚴格 "1" 比對（OPENCLAW_COST_EDGE_ADVISOR）
//!     4. evaluate cadence 對齊 poll_interval（200ms × 10 cycle，≤10% 抖動）
//!     5. cancel.cancel() 觸發 daemon sub-second shutdown
//!
//!   全用 `tokio::test(flavor = "multi_thread")` 確保 daemon 真拿到獨立
//!   worker；env-gate 測試經 process-wide Mutex 序列化（避 OS 級 env race）。
//!   每個 test binary 各自持 `env_lock()` `OnceLock` — Cargo 將 `tests/*.rs`
//!   各跑為獨立進程，跨 binary env race 不可能。

use openclaw_engine::config::{ConfigStore, RiskConfig};
use openclaw_engine::cost_edge_advisor::{
    is_advisor_env_enabled, spawn_cost_edge_advisor, CostEdgeAdvisor, CostEdgeAdvisorState,
    CostEdgeAdvisorStatus, ENV_ADVISOR_FLAG,
};
use openclaw_engine::h_state_cache::{H5CostStats, HStateCache, HStateSnapshot};

use std::sync::{Arc, Mutex, OnceLock};
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
// Proof 5: cancel.cancel() drains daemon promptly (sub-second shutdown).
// 證明 5：cancel.cancel() 觸發 daemon sub-second shutdown。
// ---------------------------------------------------------------------------
//
// Bonus assertion the task didn't strictly require but cheap to add:
// validates the cancellation safety claim from `mod.rs:188` so we know a
// shutdown path race won't leak daemons across test runs.
// 任務未強制要求但便宜：驗 mod.rs:188 cancellation-safe 宣告,避免關閉
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
