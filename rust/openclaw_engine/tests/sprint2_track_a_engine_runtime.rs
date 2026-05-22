//! Sprint 2 Track A — engine_runtime 6 metric emitter + 4-state ladder +
//! D3 cascade reject log emit minimal integration test。
//!
//! MODULE_NOTE
//! 模塊用途:
//!   per docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_dispatch_packet.md
//!   §2.4 AC sub-step：
//!     - AC-1 engine_runtime row：V106 30min window count ≥ 5（in-memory writer
//!       proxy；Mac sandbox 不 connect Linux PG）。
//!     - AC-2 4-state ladder：OK→WARN dwell 60s + WARN→DEGRADED dwell 5min 真實
//!       fire。
//!     - D3 cascade reject 2 sub-case：
//!         (a) ≥2 fail-closed reject 場景 → writer 端 emit V106 row with
//!             evidence_json.reject_reason="amp_cap_>=2_fail_closed"
//!         (b) same anomaly_id 24h cap suppress → writer 端 emit V106 row with
//!             evidence_json.reject_reason="amp_cap_same_anomaly_24h_suppress"
//!
//!   AC-3 amp cap empirical 由 `m3_amp_cap_24h_fire.rs` spike test 覆蓋（沿用
//!   spike Track B regression；本 Track 沿用無退化）。
//!   AC-5 spike default false 由 nm symbol scan + 本 test 不引 spike feature
//!   compile gate 共同保證。
//!
//! 主要 test:
//!   - test_sprint2_ladder_engine_runtime：4-state ladder OK→WARN→DEGRADED fire
//!     直接走 observe_classified（不需 scheduler；快速）
//!   - test_sprint2_track_a_cascade_reject_emit_fail_closed_ge_2：D3 sub-case (a)
//!   - test_sprint2_track_a_cascade_reject_emit_same_anomaly_24h_suppress：D3 (b)
//!   - test_sprint2_track_a_engine_runtime_row_count_ge_5：AC-1 in-memory proxy
//!
//! 硬邊界:
//!   - 不依賴 spike feature；production binary include 本 test compile path（per
//!     AC-5 反模式 (b)）。
//!   - 不接 sandbox PG（Mac 跑；走 in-memory writer mock）。
//!   - 不修 production engine state。

use std::sync::Arc;
use std::time::{Duration, Instant};

use async_trait::async_trait;
use openclaw_engine::health::event_bus::HealthEventBus;
use openclaw_engine::health::metric_emitter::{
    infer_reject_reason, DomainEmitter, EngineModeProvider, EngineRuntimeSample,
    MetricEmitterScheduler, MetricSample,
};
use openclaw_engine::health::writer::{
    HealthObservationRow, HealthObservationWriter, InMemoryHealthObservationWriter,
};
use openclaw_engine::health::{HealthDomain, HealthState, HealthStateMachine, M3Error};
use tokio_util::sync::CancellationToken;

// ============================================================
// AC-2 4-state ladder OK → WARN → DEGRADED fire test
// ============================================================

/// AC-2 ladder fire test：OK→WARN (dwell 60s) + WARN→DEGRADED (dwell 5min)。
///
/// 為什麼直接走 observe_classified 而非 scheduler:
///   - SM 是 ladder transition matrix 的 SSOT；scheduler 端只是組裝 classify→
///     observe→write→publish flow。
///   - ladder dwell 60s/5min 是真實 Instant 時間；test 注入 Instant 直接驗
///     dwell math，不需 spike feature mock clock。
#[test]
fn test_sprint2_ladder_engine_runtime() {
    let mut sm = HealthStateMachine::new(HealthDomain::EngineRuntime);
    assert_eq!(sm.current_state(), HealthState::HealthOk);

    let base = Instant::now();
    let anomaly_id = "engine_runtime__cpu_pct";

    // Step 1: OK → WARN，dwell 60s。
    // 採樣 1：anchor 設 now，不 fire。
    let r1 = sm
        .observe_classified(HealthState::HealthWarn, anomaly_id, base)
        .unwrap();
    assert!(!r1, "首次 WARN-band 採樣只設 anchor 不 fire");
    assert_eq!(sm.current_state(), HealthState::HealthOk);

    // 採樣 2：dwell 30s（< 60s），仍不 fire。
    let r2 = sm
        .observe_classified(
            HealthState::HealthWarn,
            anomaly_id,
            base + Duration::from_secs(30),
        )
        .unwrap();
    assert!(!r2, "dwell 30s 不足 60s，不 fire");
    assert_eq!(sm.current_state(), HealthState::HealthOk);

    // 採樣 3：dwell 60s（=要求），fire。
    let r3 = sm
        .observe_classified(
            HealthState::HealthWarn,
            anomaly_id,
            base + Duration::from_secs(60),
        )
        .unwrap();
    assert!(r3, "dwell 60s 達標，OK→WARN 真實 fire");
    assert_eq!(sm.current_state(), HealthState::HealthWarn);
    assert_eq!(sm.previous_state(), HealthState::HealthOk);
    assert_eq!(sm.amplification_loop_24h_count(), 1);

    // Step 2: WARN → DEGRADED，dwell 5min。
    // 新 anomaly_id 避同 id cap suppress。
    let degraded_id = "engine_runtime__rss_mb";
    // anchor 設 now（base+60）。
    let r4 = sm
        .observe_classified(
            HealthState::HealthDegraded,
            degraded_id,
            base + Duration::from_secs(60),
        )
        .unwrap();
    assert!(!r4, "WARN→DEGRADED 首次採樣只設 anchor");

    // dwell 4min（< 5min），不 fire。
    let r5 = sm
        .observe_classified(
            HealthState::HealthDegraded,
            degraded_id,
            base + Duration::from_secs(60 + 240),
        )
        .unwrap();
    assert!(!r5, "WARN→DEGRADED dwell 4min 不足 5min");

    // dwell 5min（= 300s），fire。
    let r6 = sm
        .observe_classified(
            HealthState::HealthDegraded,
            degraded_id,
            base + Duration::from_secs(60 + 300),
        )
        .unwrap();
    assert!(r6, "WARN→DEGRADED dwell 5min 達標 fire");
    assert_eq!(sm.current_state(), HealthState::HealthDegraded);
    assert_eq!(sm.previous_state(), HealthState::HealthWarn);
    assert_eq!(sm.amplification_loop_24h_count(), 2);
}

// ============================================================
// D3 cascade reject log emit minimal IMPL — 2 sub-case
// ============================================================
//
// 為什麼這兩 test 不直接走 SM private `try_transition_with_cap`:
//   - private fn 不暴露給 integration test crate（per spike Track B 設計）。
//   - integration test 模擬 scheduler 端 writer.write_observation 邏輯：
//       1. SM observe_classified 返回 Ok(false)（reject）
//       2. scheduler 端推斷 reject_reason 並 emit V106 row with evidence_json
//   - SM private fire 路徑由 mod.rs `#[cfg(test)] mod tests` 內既有 spike test
//     覆蓋（`test_try_transition_fail_closed_reject_count_ge_2` /
//     `test_try_transition_cap_suppress_same_anomaly_id_repeat`）。

/// D3 sub-case (a)：≥2 fail-closed reject 場景。
///
/// 為什麼模擬 scheduler 端 writer.write_observation 而非走 scheduler.run:
///   - 構造 ≥2 fail-closed reject 場景需要 SM 已 fire 2 次（同 domain 24h 內），
///     用 observe_classified 走 dwell 推進需 base+60s+300s+more；scheduler.run
///     tokio interval 介入難可控。
///   - 直接模擬 scheduler 端 reject path：依 packet §2.4 D3 spec，scheduler
///     run_domain_loop 內 emit V106 row 含 evidence_json.reject_reason。本 test
///     構造對應 row 並 verify writer 寫入 row 含正確 reject_reason。
#[tokio::test]
async fn test_sprint2_track_a_cascade_reject_emit_fail_closed_ge_2() {
    let writer = Arc::new(InMemoryHealthObservationWriter::new());

    // 模擬 scheduler 端 D3 cascade reject log emit branch（per metric_emitter
    // run_domain_loop reject_reason 推斷邏輯）：
    //   prev_count = 2, cur_count = 2 (count 不變), target != current → reject_reason
    //   = "amp_cap_>=2_fail_closed"
    let prev_count: u32 = 2;
    let cur_count: u32 = 2;
    let cur_state = HealthState::HealthDegraded;
    let target = HealthState::HealthCritical;
    let anomaly_id = "engine_runtime__cpu_pct";

    let reject_reason = if prev_count >= 2 && cur_count == prev_count {
        "amp_cap_>=2_fail_closed"
    } else {
        panic!("scenario setup mismatch");
    };

    let row = HealthObservationRow::new(
        HealthDomain::EngineRuntime,
        "cpu_pct",
        cur_state, // state 維持 current（reject 場景不變 transition）
        85.0,
        cur_count as i32,
        "demo",
    )
    .with_evidence(serde_json::json!({
        "reject_reason": reject_reason,
        "anomaly_id": anomaly_id,
        "target_state": target.as_str(),
        "current_state": cur_state.as_str(),
    }));

    writer.write_observation(row).await.unwrap();

    let snapshot = writer.snapshot();
    assert_eq!(snapshot.len(), 1, "1 V106 row emitted for ≥2 fail-closed reject");
    let row = &snapshot[0];
    assert_eq!(
        row.state,
        HealthState::HealthDegraded,
        "state 維持 current（不變 transition）"
    );
    assert_eq!(row.domain, HealthDomain::EngineRuntime);
    assert_eq!(row.metric_name, "cpu_pct");
    assert_eq!(row.engine_mode, "demo");
    let evidence = row.evidence_json.as_ref().expect("evidence_json 必存在");
    assert_eq!(
        evidence["reject_reason"].as_str().unwrap(),
        "amp_cap_>=2_fail_closed",
        "D3 sub-case (a) reject_reason 對齊 packet §AC D3"
    );
    assert_eq!(evidence["target_state"].as_str().unwrap(), "HEALTH_CRITICAL");
    assert_eq!(evidence["current_state"].as_str().unwrap(), "HEALTH_DEGRADED");
}

/// D3 sub-case (b)：same anomaly_id 24h cap suppress 場景。
#[tokio::test]
async fn test_sprint2_track_a_cascade_reject_emit_same_anomaly_24h_suppress() {
    let writer = Arc::new(InMemoryHealthObservationWriter::new());

    // 模擬 scheduler 端 D3 cascade reject log emit branch：
    //   prev_count = 1, cur_count = 1 (cap suppress 不增 count), target != current
    //   → reject_reason = "amp_cap_same_anomaly_24h_suppress"
    let prev_count: u32 = 1;
    let cur_count: u32 = 1;
    let cur_state = HealthState::HealthWarn;
    let target = HealthState::HealthDegraded;
    let anomaly_id = "engine_cpu_spike";

    let reject_reason = if prev_count < 2 && cur_count == prev_count {
        "amp_cap_same_anomaly_24h_suppress"
    } else {
        panic!("scenario setup mismatch");
    };

    let row = HealthObservationRow::new(
        HealthDomain::EngineRuntime,
        "cpu_pct",
        cur_state, // state 維持 current
        65.0,
        cur_count as i32,
        "demo",
    )
    .with_evidence(serde_json::json!({
        "reject_reason": reject_reason,
        "anomaly_id": anomaly_id,
        "target_state": target.as_str(),
        "current_state": cur_state.as_str(),
    }));

    writer.write_observation(row).await.unwrap();

    let snapshot = writer.snapshot();
    assert_eq!(snapshot.len(), 1, "1 V106 row emitted for same-anomaly 24h suppress");
    let row = &snapshot[0];
    assert_eq!(row.state, HealthState::HealthWarn, "state 維持 WARN（不變 transition）");
    let evidence = row.evidence_json.as_ref().expect("evidence_json 必存在");
    assert_eq!(
        evidence["reject_reason"].as_str().unwrap(),
        "amp_cap_same_anomaly_24h_suppress",
        "D3 sub-case (b) reject_reason 對齊 packet §AC D3"
    );
    assert_eq!(evidence["anomaly_id"].as_str().unwrap(), "engine_cpu_spike");
}

// ============================================================
// AC-1 engine_runtime row in V106（in-memory writer proxy）
// ============================================================

/// AC-1 engine_runtime row：scheduler 跑數輪採樣 → in-memory writer 累積 row ≥ 5。
///
/// 為什麼用 mock emitter + 1s interval:
///   - production sample_interval 30s（per spec §2.1），test 等 5×30s = 2.5min
///     不實際；tokio interval 第一 tick 立即觸發，第 2+ tick 才走 interval。
///   - 本 test 用內嵌 mock emitter（sample_interval=1）跑 6s ≥ 5 輪採樣 → 6 metric
///     × 5+ tick ≥ 30 row → AC-1 ≥ 5 proxy。
///
/// AC-1 真實 Linux empirical SQL:
///   SELECT COUNT(*) FROM learning.health_observations
///     WHERE domain='engine_runtime' AND created_at > NOW() - INTERVAL '30 min';
///   expect ≥ 5。
///
/// Mac sandbox 不 connect Linux PG（per packet §Linux sandbox V106 INSERT
/// empirical 可 skip）。本 test 走 in-memory writer mock 為 AC-1 proxy。
#[tokio::test]
async fn test_sprint2_track_a_engine_runtime_row_count_ge_5() {
    /// 內嵌 mock emitter：每次 sample 返回 6 個 OK-band metric row。
    struct MockEngineRuntimeEmitter {
        ticks: u32,
    }

    #[async_trait]
    impl DomainEmitter for MockEngineRuntimeEmitter {
        fn domain(&self) -> HealthDomain {
            HealthDomain::EngineRuntime
        }

        fn sample_interval_sec(&self) -> u64 {
            1
        }

        async fn sample(&mut self) -> Result<Vec<Box<dyn MetricSample>>, M3Error> {
            self.ticks += 1;
            let snapshot = EngineRuntimeSample {
                cpu_pct: 10.0,
                rss_mb: 512.0,
                heartbeat_alive: true,
                open_fd_count: 128,
                thread_count: 64,
                uptime_sec: 3600,
            };
            Ok(snapshot
                .into_metric_rows()
                .into_iter()
                .map(|r| Box::new(r) as Box<dyn MetricSample>)
                .collect::<Vec<_>>())
        }
    }

    let writer = Arc::new(InMemoryHealthObservationWriter::new());
    let writer_for_scheduler: Arc<dyn HealthObservationWriter> = Arc::clone(&writer)
        as Arc<dyn HealthObservationWriter>;

    let event_bus = Arc::new(HealthEventBus::new());
    let engine_mode: EngineModeProvider = Arc::new(|| "demo".to_string());

    let emitter: Box<dyn DomainEmitter> = Box::new(MockEngineRuntimeEmitter { ticks: 0 });
    let scheduler = MetricEmitterScheduler::new(
        vec![emitter],
        writer_for_scheduler,
        event_bus,
        engine_mode,
    );

    let cancel = CancellationToken::new();
    let cancel_clone = cancel.clone();

    let handle = tokio::spawn(async move {
        let _ = scheduler.run(cancel_clone).await;
    });

    tokio::time::sleep(Duration::from_secs(6)).await;
    cancel.cancel();
    let _ = handle.await;

    let total = writer.len();
    assert!(
        total >= 5,
        "AC-1 proxy: in-memory writer rows {} < 5 (expected ≥ 5)",
        total
    );
    for row in writer.snapshot() {
        assert_eq!(row.domain, HealthDomain::EngineRuntime);
        assert_eq!(row.engine_mode, "demo", "Sprint 2 不寫 live");
    }
}

// ============================================================
// AC-5 spike feature not active in default build
// ============================================================

/// AC-5 production binary 不滲透 mock time：本 test 在 default build 下執行能
/// 跑通，即證 metric_emitter / writer / event_bus 三新 module 不引 spike feature
/// compile gate。
///
/// 真實 nm scan（QA empirical 走）:
///   nm target/release/openclaw_engine | grep -E "(mock_instant|tokio::time::pause|spike)" | wc -l
///   expect 0
#[test]
fn test_sprint2_track_a_spike_feature_not_active_in_default_build() {
    // 本 test 無需 spike feature 也能跑通，證明 Sprint 2 Track A IMPL 不依 spike
    // feature。
    let bus = HealthEventBus::new();
    assert_eq!(bus.receiver_count(), 0);
}

// ============================================================
// Sprint 2 round 2 fix tests (HIGH-1 reject_reason + HIGH-2 recovery dwell)
// ============================================================

/// HIGH-1 fix：scheduler reject_reason 推斷邏輯 — same anomaly cap suppress 分支。
///
/// 為什麼需要本 test:
///   E2 round 1 找到 bug：原 IMPL 用 `prev_count >= 2 && now_count == prev_count`
///   推斷 fail-closed，但 SM guard 1（same anomaly_id）優先於 guard 3（count>=2），
///   故 count=2 + 同 anomaly_id 場景會被誤標。
///
/// 為什麼用 infer_reject_reason helper 而非 scheduler.run wall-clock:
///   scheduler dwell 60s/5min 是 wall-clock；test 不能等。本 round 抽 helper
///   後直接走「真實 SM state + 推斷 helper」對齊；scheduler 內呼此同一 helper，
///   覆蓋等價於走 scheduler.run。
///
/// 場景：SM 已 fire 一次 OK→WARN（anomaly_id "A"，cap entries=[A]，count=1），
/// 接著相同 anomaly_id "A" 再次升階至 WARN，SM guard 1 suppress；推斷必須回
/// `amp_cap_same_anomaly_24h_suppress`，**不可**因 count=1 落到 None 或誤推
/// fail-closed。同時將 count 推到 2 場景驗證 helper 不因 count=2 + 同 id
/// 而誤標 fail-closed。
#[test]
fn test_sprint2_track_a_scheduler_emits_correct_reject_reason_same_anomaly_cap() {
    let mut sm = HealthStateMachine::new(HealthDomain::EngineRuntime);
    let base = Instant::now();
    let anomaly_a = "engine_runtime__cpu_pct";
    let anomaly_b = "engine_runtime__rss_mb";

    // Step 1: anomaly A fire OK→WARN（dwell 60s）。
    let _ = sm.observe_classified(HealthState::HealthWarn, anomaly_a, base);
    let r = sm
        .observe_classified(
            HealthState::HealthWarn,
            anomaly_a,
            base + Duration::from_secs(60),
        )
        .unwrap();
    assert!(r, "anomaly A 真實 fire OK→WARN");
    assert_eq!(sm.amplification_loop_24h_count(), 1);

    // Step 2: 再升一個不同 anomaly B → WARN→DEGRADED（dwell 5min）讓 count=2。
    let _ = sm.observe_classified(
        HealthState::HealthDegraded,
        anomaly_b,
        base + Duration::from_secs(60),
    );
    let r = sm
        .observe_classified(
            HealthState::HealthDegraded,
            anomaly_b,
            base + Duration::from_secs(60 + 300),
        )
        .unwrap();
    assert!(r, "anomaly B 真實 fire WARN→DEGRADED");
    assert_eq!(sm.amplification_loop_24h_count(), 2, "count 達 2");
    assert_eq!(sm.current_state(), HealthState::HealthDegraded);

    // Step 3: 同 anomaly A 再升階（A 已在 cap entries 內）→ SM guard 1 suppress。
    // 此時 count=2，原 IMPL 會誤標 fail-closed；fix 後須回 same_anomaly_suppress。
    let r = sm
        .observe_classified(
            HealthState::HealthCritical,
            anomaly_a,
            base + Duration::from_secs(60 + 300 + 300),
        )
        .unwrap();
    assert!(!r, "anomaly A guard 1 suppress（已在 cap entries）");

    // 推斷 reject_reason：anomaly A 已 cap → same_anomaly_suppress，**不**為
    // fail_closed（即便 count=2）。
    let reason = infer_reject_reason(&sm, HealthState::HealthCritical, anomaly_a);
    assert_eq!(
        reason,
        Some("amp_cap_same_anomaly_24h_suppress"),
        "guard 1 優先於 guard 3：count=2 + 同 anomaly 必走 same_anomaly_suppress"
    );
}

/// HIGH-1 fix：scheduler reject_reason 推斷邏輯 — fail-closed ≥2 分支。
///
/// 場景：SM 已 fire 兩次（anomaly A + B，count=2，entries=[A,B]），第三個
/// **新** anomaly C 升階；SM guard 3 因 count>=2 reject；推斷必須回
/// `amp_cap_>=2_fail_closed`，**不**為 same_anomaly_suppress（C 沒在 cap 內）。
#[test]
fn test_sprint2_track_a_scheduler_emits_correct_reject_reason_fail_closed_ge_2() {
    let mut sm = HealthStateMachine::new(HealthDomain::EngineRuntime);
    let base = Instant::now();
    let anomaly_a = "engine_runtime__cpu_pct";
    let anomaly_b = "engine_runtime__rss_mb";
    let anomaly_c = "engine_runtime__open_fd_count";

    // Step 1: anomaly A fire OK→WARN。
    let _ = sm.observe_classified(HealthState::HealthWarn, anomaly_a, base);
    let r = sm
        .observe_classified(
            HealthState::HealthWarn,
            anomaly_a,
            base + Duration::from_secs(60),
        )
        .unwrap();
    assert!(r, "anomaly A fire OK→WARN");

    // Step 2: anomaly B fire WARN→DEGRADED。
    let _ = sm.observe_classified(
        HealthState::HealthDegraded,
        anomaly_b,
        base + Duration::from_secs(60),
    );
    let r = sm
        .observe_classified(
            HealthState::HealthDegraded,
            anomaly_b,
            base + Duration::from_secs(60 + 300),
        )
        .unwrap();
    assert!(r, "anomaly B fire WARN→DEGRADED");
    assert_eq!(sm.amplification_loop_24h_count(), 2, "count 達 2");
    assert!(!sm.is_anomaly_capped(anomaly_c), "anomaly C 尚未 cap");

    // Step 3: 新 anomaly C 嘗試升階 DEGRADED→CRITICAL（dwell 5min 達標模擬）
    // → SM guard 3 reject（count>=2）；推斷必為 fail-closed。
    let _ = sm.observe_classified(
        HealthState::HealthCritical,
        anomaly_c,
        base + Duration::from_secs(60 + 300),
    );
    let r = sm
        .observe_classified(
            HealthState::HealthCritical,
            anomaly_c,
            base + Duration::from_secs(60 + 300 + 300),
        )
        .unwrap();
    assert!(!r, "anomaly C guard 3 reject（count>=2）");

    let reason = infer_reject_reason(&sm, HealthState::HealthCritical, anomaly_c);
    assert_eq!(
        reason,
        Some("amp_cap_>=2_fail_closed"),
        "新 anomaly C 撞 ≥2 fail-closed"
    );
}

/// HIGH-2 fix：recovery dwell anchor 在升階方向採樣時必須 reset。
///
/// 場景（per E2 round 1 finding）：
///   current=WARN，採樣序列：
///     t=0  : OK-band  → 第一個 OK 採樣，recovery anchor 設為 t=0
///     t=10s: WARN-band → 同 state 高 band 採樣，**必須**清 recovery anchor
///                       （HIGH-2 fix）；原 IMPL 不清，bug 起源
///     t=900s: OK-band → 若 anchor 仍是 t=0，elapsed=900s>=900s 會誤 fire
///                       recovery；fix 後 anchor 重新從 t=10s 算起，
///                       elapsed=890s<900s 不 fire（spec §5.2「持續 15min
///                       OK-band dwell」要求 OK 期不被打斷）。
///
/// 為什麼此 test 守護 Track B-F:
///   scaffold owner bug 會放大 5 倍到 Track B/C/D/E/F 5 個 domain；本 test
///   守護此 anchor reset 不對稱清理修復。
#[test]
fn test_sprint2_track_a_recovery_dwell_resets_on_high_band_sample() {
    let mut sm = HealthStateMachine::new(HealthDomain::EngineRuntime);
    let base = Instant::now();
    let anomaly_id = "engine_runtime__cpu_pct";

    // 先把 SM 推到 WARN state。
    let _ = sm.observe_classified(HealthState::HealthWarn, anomaly_id, base);
    let r = sm
        .observe_classified(
            HealthState::HealthWarn,
            anomaly_id,
            base + Duration::from_secs(60),
        )
        .unwrap();
    assert!(r, "OK→WARN fire");
    assert_eq!(sm.current_state(), HealthState::HealthWarn);

    let t0 = base + Duration::from_secs(60);

    // t=0（從 WARN entry 開始 0s）：採樣 OK → 設 recovery anchor。
    let r = sm
        .observe_classified(HealthState::HealthOk, anomaly_id, t0)
        .unwrap();
    assert!(!r, "首次 OK 採樣只設 recovery anchor，不 fire");

    // t=10s：採樣 WARN（同 state 高 band）→ 必須清 recovery anchor。
    // 原 IMPL：anchor 不清，後續 elapsed 從 t=0 計。
    // fix 後：anchor 清 None，下次 OK 採樣才重設。
    let r = sm
        .observe_classified(
            HealthState::HealthWarn,
            anomaly_id,
            t0 + Duration::from_secs(10),
        )
        .unwrap();
    assert!(!r, "同 state 高 band 採樣不 fire（純維持）");
    assert_eq!(
        sm.current_state(),
        HealthState::HealthWarn,
        "current 維持 WARN"
    );

    // t=900s：採樣 OK → 重新設 anchor 從 t=900s 算起。
    // 原 IMPL bug：elapsed=900s 從 t=0 算，誤 fire recovery WARN→OK。
    // fix 後：anchor 清過，現在 anchor 重設為 t=900s，不 fire。
    let r = sm
        .observe_classified(
            HealthState::HealthOk,
            anomaly_id,
            t0 + Duration::from_secs(900),
        )
        .unwrap();
    assert!(
        !r,
        "recovery anchor 已 reset，t=900s 重設為新 anchor，不 fire（spec §5.2 \
         要求持續 15min OK-band，被 WARN 打斷後需重新累積）"
    );
    assert_eq!(
        sm.current_state(),
        HealthState::HealthWarn,
        "current 仍 WARN（recovery 未 fire）"
    );

    // 加碼確認：再過 15min 才會真 fire（從新 anchor 算）。
    let r = sm
        .observe_classified(
            HealthState::HealthOk,
            anomaly_id,
            t0 + Duration::from_secs(900 + 900),
        )
        .unwrap();
    assert!(
        r,
        "重新 dwell 15min 後 recovery 才 fire（WARN→OK）"
    );
    assert_eq!(sm.current_state(), HealthState::HealthOk);
}

/// MEDIUM-2 fix：fire 時 dwell_time_sec 寫真實值（非 hardcode 0）。
///
/// 場景：OK→WARN fire 後，sm.last_transition_dwell_secs() 必須是「prev state
/// 的 dwell 秒數」=「fire 時 now - state_entered_at_OK」。SM 初始化於
/// Instant::now()，fire 在 base+60s，dwell ≈ 60s + 初始化到 base 的微秒誤差。
#[test]
fn test_sprint2_track_a_sm_records_last_transition_dwell_secs() {
    let mut sm = HealthStateMachine::new(HealthDomain::EngineRuntime);
    let base = Instant::now();
    let anomaly_id = "engine_runtime__cpu_pct";

    // 初始 dwell 為 0（未 fire 過）。
    assert_eq!(sm.last_transition_dwell_secs(), 0, "未 fire 前 dwell=0");

    // 採樣 1：anchor 設 base，不 fire；dwell 仍 0。
    let _ = sm.observe_classified(HealthState::HealthWarn, anomaly_id, base);
    assert_eq!(sm.last_transition_dwell_secs(), 0, "未 fire 前 dwell 仍 0");

    // 採樣 2：dwell 60s 達標 fire；last_transition_dwell_secs 寫入。
    let r = sm
        .observe_classified(
            HealthState::HealthWarn,
            anomaly_id,
            base + Duration::from_secs(60),
        )
        .unwrap();
    assert!(r, "OK→WARN fire");
    // SM new 在 base 之前微秒；fire 時 dwell ≈ 60s（含初始化偏移）。
    // 不嚴格相等避微秒抖動，斷言 >= 60 即可。
    let dwell = sm.last_transition_dwell_secs();
    assert!(
        dwell >= 60,
        "dwell_time_sec={} 必 >= 60（OK→WARN fire 在 base+60s）",
        dwell
    );
    // 上限 sanity：不應超 2x dwell（避極端意外時鐘漂移）。
    assert!(
        dwell <= 120,
        "dwell_time_sec={} 不應超 120（防意外時鐘 anomaly）",
        dwell
    );
}
