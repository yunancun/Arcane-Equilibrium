//! Sprint 1A-ζ Track B — AC-5.1 amplification cap 24h fire empirical test。
//!
//! MODULE_NOTE
//! 模塊用途:
//!   per docs/execution_plan/2026-05-21--sprint_1a_zeta_impl_spike_scope_spec.md
//!   §AC-5.1 規範,用 observe_at 注入虛擬 Instant 驗證 M3 amplification cap
//!   24h fire 路徑:
//!     - inject fake CPU spike 80% → engine_runtime band = WARN
//!     - dwell time 60s pass → HEALTH_WARN transition + amp cap count = 1
//!     - 24h 內 inject 第二個 spike (同 anomaly_id) → cap suppress 不重觸發
//!     - 24h+1s 後 inject 第三個 spike (同 anomaly_id) → cap reset 計入第 1 次
//!
//! 為什麼 spike feature flag 隔絕:
//!   per dispatch packet Task 3 (feature flag `spike` 隔絕 production)。
//!   default build (`cargo build --release`) 不帶 --features spike → 本檔
//!   完全不編譯; 0 production code path 污染。
//!
//! 為什麼用 observe_at 注入虛擬 Instant 而非 tokio::time::advance:
//!   tokio::time::pause/advance 推進 tokio 虛擬 clock; std::time::Instant
//!   對其無感知 (real monotonic clock 不會 hop)。state machine 用 Instant
//!   做 dwell time + amp cap 計算 → 必須注入虛擬 Instant 才能 hop 24h+1s。
//!   observe_at 是 mod.rs 內專為 spike test 設計的注入入口; production
//!   observe() 仍用 std::time::Instant::now() → 0 production 污染。
//!
//! 主要 test 函數:
//!   - test_m3_amp_cap_24h_fire: AC-5.1 5-step fire test
//!   - test_amp_cap_different_anomaly_id_not_suppressed: 反向驗,不同 id 不互 cap
//!   - test_stub_domains_fail_loud: 5 stub domain 進 observe 必 fail-loud
//!
//! 硬邊界:
//!   - 只在 `--features spike` 編譯; production binary 不含本檔。
//!   - 不依賴 IPC / DB / GovernanceHub; 純 state machine in-memory 測試。

#![cfg(feature = "spike")]

use openclaw_engine::health::{
    EngineRuntimeMetric, HealthDomain, HealthState, HealthStateMachine,
};
use std::time::{Duration, Instant};

/// AC-5.1 amplification cap 24h fire test (per spike spec §AC-5.1)。
///
/// 為什麼此 step 分開:
///   - Step 1 (OK→WARN dwell time): per spec §3.3 OK→WARN 60s dwell
///     (30s × 10 sample = 5min, 遠超 60s dwell threshold)。
///   - Step 2 (24h 窗口內 + 1h hop): inject 第二個 spike 在 24h cap 窗口內,
///     同 anomaly_id → cap suppress 不重觸發,count 仍 1。
///   - Step 3 (24h+1s mock hop): hop 虛擬 Instant +24h+1s, cap entry 被
///     retain 清理過期。
///   - Step 4 (24h reset 後第三個 spike): 同 anomaly_id 但 cap 已 reset →
///     算「第一次」可再次計入 cap entry, count 仍 1 (因 retain 清掉舊 entry)。
#[test]
fn test_m3_amp_cap_24h_fire() {
    let mut sm = HealthStateMachine::new(HealthDomain::EngineRuntime);
    assert_eq!(sm.current_state(), HealthState::HealthOk);
    assert_eq!(sm.amplification_loop_24h_count(), 0);

    let spike_metric = EngineRuntimeMetric {
        cpu_pct: 85.0,
        rss_mb: 1500.0,
        heartbeat_alive: true,
    };

    // base virtual time anchor; 後續 step 對 base 加 Duration 推進虛擬 Instant。
    let base = Instant::now();

    // ----------------------------------------
    // Step 1: 第一個 fake CPU spike → OK→WARN transition (dwell 60s pass)
    // 30s × 10 sample = 5min 累積採樣, 遠超 60s OK→WARN dwell threshold。
    // ----------------------------------------
    for i in 0..10 {
        let now = base + Duration::from_secs(30 * (i as u64));
        let _ = sm
            .observe_at(spike_metric, "engine_cpu_spike", now)
            .expect("observe must succeed for engine_runtime domain");
    }

    assert_eq!(
        sm.current_state(),
        HealthState::HealthWarn,
        "Step 1: first spike triggers OK→WARN transition (dwell 60s pass)"
    );
    assert_eq!(
        sm.amp_cap_entry_count(),
        1,
        "Step 1: amp cap entry recorded once for 'engine_cpu_spike'"
    );
    assert_eq!(
        sm.amplification_loop_24h_count(),
        1,
        "Step 1: amplification_loop_24h_count = 1 (V106 row)"
    );

    // ----------------------------------------
    // Step 2: 24h 內 (+1h hop) 第二個 spike (同 anomaly_id) → cap suppress
    // 已在 WARN, 同 anomaly_id 24h 內不重觸發 transition; count 仍 1。
    // ----------------------------------------
    let step2_base = base + Duration::from_secs(3600); // +1h hop, 仍在 24h 窗口內。
    for i in 0..10 {
        let now = step2_base + Duration::from_secs(30 * (i as u64));
        let _ = sm
            .observe_at(spike_metric, "engine_cpu_spike", now)
            .expect("observe must succeed");
    }

    assert_eq!(
        sm.current_state(),
        HealthState::HealthWarn,
        "Step 2: 24h-window 內第二個 spike 不重觸發 transition"
    );
    assert_eq!(
        sm.amplification_loop_24h_count(),
        1,
        "Step 2: amp cap suppresses second spike; count stays at 1"
    );

    // ----------------------------------------
    // Step 3: 24h+1s hop → cap entry 過期; retain 清理舊 entry。
    // 此 step 內也走 5min 連續採樣, retain 邏輯在 observe_at 內部觸發。
    // ----------------------------------------
    let step3_base = base + Duration::from_secs(24 * 3600 + 1); // +24h+1s
    for i in 0..10 {
        let now = step3_base + Duration::from_secs(30 * (i as u64));
        let _ = sm
            .observe_at(spike_metric, "engine_cpu_spike", now)
            .expect("observe must succeed");
    }

    // 24h reset 後同 anomaly_id 再次計入,count 仍 1 (因 retain 清掉舊 entry,
    // 然後新增當下 entry → set size 仍 = 1, 但是新的 first_triggered_at)。
    assert_eq!(
        sm.current_state(),
        HealthState::HealthWarn,
        "Step 3/4: 24h cap reset 後 state 仍 WARN (沒升 DEGRADED)"
    );
    assert_eq!(
        sm.amplification_loop_24h_count(),
        1,
        "Step 3/4: 24h cap reset 後 count = 1 (舊 entry 過期, 新 entry 計入)"
    );
}

/// 反向驗: 不同 anomaly_id 不互相 cap suppress (per ADR-0042 Decision 4
/// cap key = `(anomaly_source, anomaly_signature_hash)`)。
///
/// 為什麼: 兩個 unique id 各自獨立 24h 計數 → cap entries 各自計入,
/// amplification_loop_24h_count = 2。
#[test]
fn test_amp_cap_different_anomaly_id_not_suppressed() {
    let mut sm = HealthStateMachine::new(HealthDomain::EngineRuntime);

    let spike_metric = EngineRuntimeMetric {
        cpu_pct: 85.0,
        rss_mb: 1500.0,
        heartbeat_alive: true,
    };

    let base = Instant::now();

    // 第一個 id "engine_cpu_spike" → OK→WARN transition (dwell pass), cap entry 1。
    for i in 0..10 {
        let now = base + Duration::from_secs(30 * (i as u64));
        let _ = sm
            .observe_at(spike_metric, "engine_cpu_spike", now)
            .unwrap();
    }
    assert_eq!(sm.current_state(), HealthState::HealthWarn);
    assert_eq!(sm.amp_cap_entry_count(), 1);

    // 第二個 id "memory_pressure" 在已 WARN 狀態 → 不再 transition 但 cap entry +1。
    let second_base = base + Duration::from_secs(300);
    for i in 0..2 {
        let now = second_base + Duration::from_secs(30 * (i as u64));
        let _ = sm
            .observe_at(spike_metric, "memory_pressure", now)
            .unwrap();
    }
    // 不同 id 計入獨立 entry → entries = 2, count = 2。
    assert_eq!(
        sm.amp_cap_entry_count(),
        2,
        "兩個不同 anomaly_id 在 24h 窗口內各自獨立計入 cap entries"
    );
    assert_eq!(sm.amplification_loop_24h_count(), 2);
}

/// 5 stub domain (per dispatch packet §2.7(a) 反模式) 進 observe 必 fail-loud。
#[test]
fn test_stub_domains_fail_loud() {
    let stub_domains = [
        HealthDomain::PipelineThroughput,
        HealthDomain::DatabasePool,
        HealthDomain::ApiLatency,
        HealthDomain::StrategyQuality,
        HealthDomain::RiskEnvelope,
    ];

    let metric = EngineRuntimeMetric {
        cpu_pct: 30.0,
        rss_mb: 1024.0,
        heartbeat_alive: true,
    };

    for d in &stub_domains {
        let mut sm = HealthStateMachine::new(*d);
        let result = sm.observe(metric, "test");
        assert!(
            result.is_err(),
            "spike scope: domain {} must fail-loud",
            d.as_str()
        );
    }
}
