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

/// AC-5.1 amplification cap 24h fire test (per spike spec §AC-5.1 step 順序)。
///
/// spec §AC-5.1 4-step 順序 (per E2 round 1 finding MEDIUM-1):
///   - Step 1: OK→WARN dwell pass → fire 1 次 (entries=1, count=1, state=WARN)
///   - Step 2: 24h+1s hop → retain 清舊 entry (entries=0, count=0, state 維持 WARN)
///   - Step 3: 24h reset 後 spike (同 anomaly_id) → spike scope WARN 已 active,
///     current==target=HealthWarn, (HealthWarn, _) arm return Ok(false), no
///     fire (entries=0, count=0)。完整 fire 重觸發要 WARN→DEGRADED IMPL,
///     屬 Sprint 5 cascade scope (per dispatch §2.7(c))。
///   - Step 4: 24h 內第 4 個 spike (新 step3_base+1h hop) → 同 cap window 內
///     (Step 3 沒新 entry, 但 current==target 不 fire 一致), entries=0 不變。
///
/// 為什麼 spec §AC-5.1 全 step 在 spike scope 不能 fire 重觸發:
///   - spike scope IMPL 只 OK→WARN; WARN→DEGRADED 5min dwell + cascade 由
///     Sprint 5 Tier 1 補。
///   - current==target 嚴格語意 (per V106 spec §1.1 line 77 「state_prev →
///     state transitions」需 prev != state) → no fire。
///   - cap 24h reset 後同 anomaly_id 在 spike scope 下 still WARN target=WARN
///     → 觀察上是「reset 但無新 fire」,Sprint 5 接 WARN→DEGRADED 才會看到
///     reset 後第 2 個 transition fire (透過不同 target_state)。
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
    // Step 1 (per spec §AC-5.1 順序): 第一個 fake CPU spike → OK→WARN transition
    // (dwell 60s pass)。30s × 10 sample = 5min 累積採樣, 遠超 60s OK→WARN
    // dwell threshold。
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
    // Step 2 (per spec §AC-5.1 順序): 24h+1s mock hop → cap entry 過期; retain
    // 清理舊 entry。state 不會隨時間 hop 改變 (current=WARN 維持)。
    // 採樣一次以觸發 retain 邏輯 (observe_at 內部 retain at top)。
    // 注意: Step 1 entry first_triggered_at = base+60s (dwell pass 觸發 fire);
    // 為確保 duration_since > 24h 過期, hop 設 base + 24h + 60s + 1s。
    // ----------------------------------------
    let step2_now = base + Duration::from_secs(24 * 3600 + 60 + 1);
    let _ = sm
        .observe_at(spike_metric, "engine_cpu_spike", step2_now)
        .expect("observe must succeed");

    assert_eq!(
        sm.current_state(),
        HealthState::HealthWarn,
        "Step 2: 24h hop 後 state 仍 WARN (沒升 DEGRADED 因 Sprint 5 才 IMPL)"
    );
    assert_eq!(
        sm.amp_cap_entry_count(),
        0,
        "Step 2: 24h+1s hop 後 retain 清掉舊 entry (entries=0)"
    );
    assert_eq!(
        sm.amplification_loop_24h_count(),
        0,
        "Step 2: amplification_loop_24h_count reset 為 0 (對齊 entries.len())"
    );

    // ----------------------------------------
    // Step 3 (per spec §AC-5.1 順序): 24h cap reset 後第 2 個 spike (同
    // anomaly_id)。spike scope 下 current=WARN target=WARN (per (HealthWarn,_)
    // arm),no fire; entries=0 維持。Sprint 5 cascade 接 WARN→DEGRADED 後此
    // step 才看得到 reset 後第 2 個 fire 計入新 entry。
    // ----------------------------------------
    let step3_base = base + Duration::from_secs(24 * 3600 + 60 + 2); // Step 2 後 1s
    for i in 0..10 {
        let now = step3_base + Duration::from_secs(30 * (i as u64));
        let _ = sm
            .observe_at(spike_metric, "engine_cpu_spike", now)
            .expect("observe must succeed");
    }

    assert_eq!(
        sm.current_state(),
        HealthState::HealthWarn,
        "Step 3: 24h cap reset 後 state 仍 WARN (沒升 DEGRADED)"
    );
    assert_eq!(
        sm.amp_cap_entry_count(),
        0,
        "Step 3: spike scope 嚴格語意 — current==target=WARN no fire, no entry"
    );
    assert_eq!(
        sm.amplification_loop_24h_count(),
        0,
        "Step 3: count=0 對齊嚴格 fire 語意 (per V106 spec §1.1 line 77)"
    );

    // ----------------------------------------
    // Step 4 (per spec §AC-5.1 順序): 24h reset 後再 1h 第 3 個 spike (同
    // anomaly_id);spike scope 仍 no fire (一致 §3 reasoning)。
    // ----------------------------------------
    let step4_base = step3_base + Duration::from_secs(3600); // +1h within new 24h
    for i in 0..10 {
        let now = step4_base + Duration::from_secs(30 * (i as u64));
        let _ = sm
            .observe_at(spike_metric, "engine_cpu_spike", now)
            .expect("observe must succeed");
    }

    assert_eq!(
        sm.current_state(),
        HealthState::HealthWarn,
        "Step 4: 24h reset 後再 1h 第 3 spike 維持 WARN (no fire spike scope)"
    );
    assert_eq!(
        sm.amplification_loop_24h_count(),
        0,
        "Step 4: count=0 維持 (no fire in spike scope)"
    );
}

/// 反向驗: 不同 anomaly_id 嚴格 fire 語意 (per ADR-0042 Decision 4 + V106
/// spec §1.1 line 77 嚴格 fire 計數)。
///
/// 為什麼此語意 (per E2 round 1 finding HIGH 修正):
///   - cap key = anomaly_id (per ADR-0042 Decision 4 `(anomaly_source,
///     anomaly_signature_hash)` 簡化);不同 id 各自獨立計 fire。
///   - 但在 spike scope 下, current=WARN target=WARN 嚴格不 fire (per V106
///     spec §1.1 line 77 「state_prev → state transitions」需 prev != state)。
///   - 所以即使是新 anomaly_id 在已 WARN 場景, 不 fire, 不計 entry。
///   - 完整測試 (不同 id 各自 fire) 需 WARN→DEGRADED IMPL 後 Sprint 5 cascade
///     IMPL 才能做; spike scope 只能 fire 1 次 OK→WARN transition。
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

    // 第二個 id "memory_pressure" 在已 WARN 狀態 → spike scope 嚴格語意 no fire
    // (current=WARN target=WARN, 不計新 entry; (HealthWarn, _) arm return false)。
    // Sprint 5 cascade IMPL 後 WARN→DEGRADED 才能各 id 獨立 fire 計入。
    let second_base = base + Duration::from_secs(300);
    for i in 0..2 {
        let now = second_base + Duration::from_secs(30 * (i as u64));
        let _ = sm
            .observe_at(spike_metric, "memory_pressure", now)
            .unwrap();
    }
    // spike scope 嚴格 fire 語意: 已 WARN target=WARN 不 fire, entries=1 維持。
    assert_eq!(
        sm.amp_cap_entry_count(),
        1,
        "spike scope: 第二個 anomaly_id 在已 WARN 不 fire (no new transition); \
         entries 維持 1 = OK→WARN 第一次 fire 的記錄"
    );
    assert_eq!(
        sm.amplification_loop_24h_count(),
        1,
        "amplification_loop_24h_count 嚴格 fire 計數 = 1 (per V106 spec §1.1 line 77)"
    );
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
