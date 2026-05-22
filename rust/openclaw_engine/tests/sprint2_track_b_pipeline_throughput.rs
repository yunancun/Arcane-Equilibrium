//! Sprint 2 Wave 1 Track B — pipeline_throughput emitter integration test。
//!
//! MODULE_NOTE
//! 模塊用途:
//!   per docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_dispatch_packet.md
//!   §3.4 AC sub-step：
//!     - AC-1a in-memory proxy：scheduler 跑數輪採樣 → in-memory writer 累積
//!       row 數 ≥ 5（V106 schema 30 min window 真實 PG empirical 由 Phase 3c
//!       QA empirical 走，Mac sandbox 不接 Linux PG）。
//!     - AC-2 4-state ladder：pipeline_throughput OK→WARN→DEGRADED ladder fire
//!       測試（直接走 observe_classified；不需 scheduler wall-clock dwell）。
//!     - AC-4 cross-domain independence：pipeline_throughput DEGRADED 不影響
//!       engine_runtime SM state。
//!     - AC-5 spike default false：本 test 在 default build (無 --features
//!       spike) 跑通，即證 metric_emitter / writer / event_bus / 新 domains
//!       module 不引 spike feature compile gate。
//!
//!   AC-3 amp cap empirical 由 `m3_amp_cap_24h_fire.rs` spike test 覆蓋（沿用
//!   spike Track B regression；本 Track 沿用無退化）。
//!
//! 主要 test:
//!   - test_sprint2_ladder_pipeline_throughput：AC-2 ladder fire
//!   - test_sprint2_cross_domain_pipeline_engine_independence：AC-4 SM 互獨立
//!   - test_sprint2_track_b_pipeline_throughput_row_count：AC-1a in-memory proxy
//!   - test_sprint2_track_b_spike_feature_not_active_in_default_build：AC-5
//!
//! 硬邊界:
//!   - 不依賴 spike feature；production binary 0 mock time 滲透對齊。
//!   - 不接 sandbox PG（Mac 跑；走 in-memory writer mock）。
//!   - 不修 production engine state / ws_client / IndicatorEngine / IPC 既有
//!     邏輯（per packet §3.5 反模式 (a)；本 test 用 stub source probe 注入）。

use std::sync::Arc;
use std::time::{Duration, Instant};

use async_trait::async_trait;
use openclaw_engine::health::domains::pipeline_throughput::{
    PipelineThroughputEmitter, PipelineThroughputSample, PipelineThroughputSourceProbe,
};
use openclaw_engine::health::event_bus::HealthEventBus;
use openclaw_engine::health::metric_emitter::{
    DomainEmitter, EngineModeProvider, MetricEmitterScheduler, MetricSample,
};
use openclaw_engine::health::writer::{
    HealthObservationWriter, InMemoryHealthObservationWriter,
};
use openclaw_engine::health::{HealthDomain, HealthState, HealthStateMachine, M3Error};
use tokio_util::sync::CancellationToken;

// ============================================================
// 共用 stub source probe（test fixture）
// ============================================================

/// stub source probe；test 注入固定 5 metric value。
///
/// 為什麼此設計:
///   - emitter `PipelineThroughputSourceProbe` 抽象 5 metric source；test
///     注入此 stub 即可不依 ws_client / IndicatorEngine / IPC 真實 hook。
///   - 對齊 packet §3.5 反模式 (a)「emitter 只讀，不修」+ Track A heartbeat
///     probe 注入同模式。
struct StubSourceProbe {
    ws_tick_rate_per_sec: f64,
    ws_heartbeat_lag_ms: u32,
    ws_subscription_drift_count: u32,
    strategy_signal_rate_per_min: f64,
    ipc_roundtrip_ms_p99: f64,
}

impl PipelineThroughputSourceProbe for StubSourceProbe {
    fn current_ws_tick_rate_per_sec(&self) -> f64 {
        self.ws_tick_rate_per_sec
    }
    fn current_ws_heartbeat_lag_ms(&self) -> u32 {
        self.ws_heartbeat_lag_ms
    }
    fn current_ws_subscription_drift_count(&self) -> u32 {
        self.ws_subscription_drift_count
    }
    fn current_strategy_signal_rate_per_min(&self) -> f64 {
        self.strategy_signal_rate_per_min
    }
    fn current_ipc_roundtrip_ms_p99(&self) -> f64 {
        self.ipc_roundtrip_ms_p99
    }
}

// ============================================================
// AC-2 4-state ladder OK → WARN → DEGRADED fire test
// ============================================================

/// AC-2 ladder fire test：pipeline_throughput SM OK→WARN（dwell 60s）+ WARN→
/// DEGRADED（dwell 5min）。
///
/// 為什麼直接走 observe_classified 而非 scheduler.run:
///   - SM 是 ladder transition matrix 的 SSOT；scheduler 端只是組裝 classify→
///     observe→write→publish flow。
///   - ladder dwell 60s/5min 是真實 Instant 時間；test 注入 Instant 直接驗
///     dwell math，不需 spike feature mock clock。
///   - 對齊 Track A `test_sprint2_ladder_engine_runtime` 同 pattern。
#[test]
fn test_sprint2_ladder_pipeline_throughput() {
    let mut sm = HealthStateMachine::new(HealthDomain::PipelineThroughput);
    assert_eq!(sm.current_state(), HealthState::HealthOk);

    let base = Instant::now();
    // anomaly_id 對齊 spec §6.2 命名規約：domain__metric_name
    let anomaly_tick_rate = "pipeline_throughput__ws_tick_rate_per_sec";

    // Step 1: OK → WARN，dwell 60s。
    // 採樣 1：anchor 設 now，不 fire。
    let r1 = sm
        .observe_classified(HealthState::HealthWarn, anomaly_tick_rate, base)
        .unwrap();
    assert!(!r1, "首次 WARN-band 採樣只設 anchor 不 fire");
    assert_eq!(sm.current_state(), HealthState::HealthOk);

    // 採樣 2：dwell 30s（< 60s），仍不 fire。
    let r2 = sm
        .observe_classified(
            HealthState::HealthWarn,
            anomaly_tick_rate,
            base + Duration::from_secs(30),
        )
        .unwrap();
    assert!(!r2, "dwell 30s 不足 60s，不 fire");
    assert_eq!(sm.current_state(), HealthState::HealthOk);

    // 採樣 3：dwell 60s（= 要求），fire。
    let r3 = sm
        .observe_classified(
            HealthState::HealthWarn,
            anomaly_tick_rate,
            base + Duration::from_secs(60),
        )
        .unwrap();
    assert!(r3, "dwell 60s 達標，OK→WARN 真實 fire");
    assert_eq!(sm.current_state(), HealthState::HealthWarn);
    assert_eq!(sm.previous_state(), HealthState::HealthOk);
    assert_eq!(sm.amplification_loop_24h_count(), 1);

    // Step 2: WARN → DEGRADED，dwell 5min。
    // 新 anomaly_id 避同 id cap suppress。
    let anomaly_ipc_p99 = "pipeline_throughput__ipc_roundtrip_ms_p99";
    // anchor 設 now（base+60）。
    let r4 = sm
        .observe_classified(
            HealthState::HealthDegraded,
            anomaly_ipc_p99,
            base + Duration::from_secs(60),
        )
        .unwrap();
    assert!(!r4, "WARN→DEGRADED 首次採樣只設 anchor");

    // dwell 4min（< 5min），不 fire。
    let r5 = sm
        .observe_classified(
            HealthState::HealthDegraded,
            anomaly_ipc_p99,
            base + Duration::from_secs(60 + 240),
        )
        .unwrap();
    assert!(!r5, "WARN→DEGRADED dwell 4min 不足 5min");

    // dwell 5min（= 300s），fire。
    let r6 = sm
        .observe_classified(
            HealthState::HealthDegraded,
            anomaly_ipc_p99,
            base + Duration::from_secs(60 + 300),
        )
        .unwrap();
    assert!(r6, "WARN→DEGRADED dwell 5min 達標 fire");
    assert_eq!(sm.current_state(), HealthState::HealthDegraded);
    assert_eq!(sm.previous_state(), HealthState::HealthWarn);
    assert_eq!(sm.amplification_loop_24h_count(), 2);
}

// ============================================================
// AC-4 cross-domain independence
// ============================================================

/// AC-4 cross-domain：pipeline_throughput SM 升 DEGRADED 不影響 engine_runtime
/// SM state。
///
/// 為什麼此 test 不走 system-level aggregate:
///   - per spec §5.3 system-level state = read-time aggregation by query；本
///     IMPL Sprint 2 不 emit system-level row（只 emit per-domain row）。
///   - 本 test 驗 SM 是 per-domain 獨立的 — 兩 SM instance 各自 transition，
///     不共享 state / cap entries / dwell anchor。
#[test]
fn test_sprint2_cross_domain_pipeline_engine_independence() {
    let mut pipeline_sm = HealthStateMachine::new(HealthDomain::PipelineThroughput);
    let mut engine_sm = HealthStateMachine::new(HealthDomain::EngineRuntime);

    let base = Instant::now();
    let pipeline_anomaly = "pipeline_throughput__ws_tick_rate_per_sec";
    let engine_anomaly = "engine_runtime__cpu_pct";

    // pipeline SM 走 OK→WARN→DEGRADED；engine SM 維持 OK 採樣。
    let _ = pipeline_sm.observe_classified(
        HealthState::HealthWarn,
        pipeline_anomaly,
        base,
    );
    let r = pipeline_sm
        .observe_classified(
            HealthState::HealthWarn,
            pipeline_anomaly,
            base + Duration::from_secs(60),
        )
        .unwrap();
    assert!(r, "pipeline OK→WARN fire");
    assert_eq!(pipeline_sm.current_state(), HealthState::HealthWarn);

    // engine SM 純 OK 採樣，state 維持 OK。
    let r_engine = engine_sm
        .observe_classified(HealthState::HealthOk, engine_anomaly, base)
        .unwrap();
    assert!(!r_engine, "engine OK-band 採樣不 fire");
    assert_eq!(
        engine_sm.current_state(),
        HealthState::HealthOk,
        "engine SM state 未被 pipeline SM 影響"
    );
    assert_eq!(
        engine_sm.amplification_loop_24h_count(),
        0,
        "engine SM cap count 未被 pipeline SM 影響"
    );

    // pipeline 繼續升 DEGRADED（用新 anomaly_id 避同 id cap）。
    let pipeline_anomaly_2 = "pipeline_throughput__ipc_roundtrip_ms_p99";
    let _ = pipeline_sm.observe_classified(
        HealthState::HealthDegraded,
        pipeline_anomaly_2,
        base + Duration::from_secs(60),
    );
    let r2 = pipeline_sm
        .observe_classified(
            HealthState::HealthDegraded,
            pipeline_anomaly_2,
            base + Duration::from_secs(60 + 300),
        )
        .unwrap();
    assert!(r2, "pipeline WARN→DEGRADED fire");
    assert_eq!(pipeline_sm.current_state(), HealthState::HealthDegraded);
    assert_eq!(pipeline_sm.amplification_loop_24h_count(), 2);

    // engine SM 狀態仍未受影響。
    assert_eq!(
        engine_sm.current_state(),
        HealthState::HealthOk,
        "engine SM 在 pipeline 升 DEGRADED 後仍維持 OK"
    );
    assert_eq!(
        engine_sm.previous_state(),
        HealthState::HealthOk,
        "engine SM 從未 transition"
    );
    assert_eq!(
        engine_sm.amplification_loop_24h_count(),
        0,
        "engine SM cap count 在 pipeline 升 DEGRADED 後仍 0"
    );
    // domain accessor 確認 SM 各自 domain 標籤獨立。
    assert_eq!(pipeline_sm.domain(), HealthDomain::PipelineThroughput);
    assert_eq!(engine_sm.domain(), HealthDomain::EngineRuntime);
}

// ============================================================
// AC-1a in-memory writer proxy — scheduler 跑 5 sample window → ≥ 5 row
// ============================================================

/// AC-1a engine sample 不接 Linux PG；走 in-memory writer mock 為 AC-1a proxy。
///
/// 為什麼用 mock emitter + 1s interval:
///   - production sample_interval 30s（per spec §2.1），test 等 5×30s = 2.5min
///     不實際；tokio interval 第一 tick 立即觸發，第 2+ tick 才走 interval。
///   - 本 test 用內嵌 mock emitter（sample_interval=1）跑 6s ≥ 5 輪採樣 →
///     5 metric × 5+ tick ≥ 25 row → AC-1a ≥ 5 proxy。
///   - 對齊 Track A `test_sprint2_track_a_engine_runtime_row_count_ge_5` 同
///     mock pattern。
///
/// AC-1b 真實 Linux empirical SQL（Phase 3c QA 跑）:
///   SELECT COUNT(*) FROM learning.health_observations
///     WHERE domain='pipeline_throughput' AND created_at > NOW() - INTERVAL '30 min';
///   expect ≥ 5。
#[tokio::test]
async fn test_sprint2_track_b_pipeline_throughput_row_count() {
    /// 內嵌 mock emitter：每次 sample 返回 5 個 OK-band metric row（interval=1s）。
    ///
    /// 為什麼不直接用 PipelineThroughputEmitter:
    ///   - PipelineThroughputEmitter sample_interval 寫死 30s；test 等不到。
    ///   - 本 mock 走 PipelineThroughputSample::into_metric_rows 同樣 5 row
    ///     展平邏輯，邏輯等價於 PipelineThroughputEmitter（per packet §3.5
    ///     反模式 (b)「不寫死採樣 30s interval」對齊 — interval 是 emitter
    ///     trait 方法，sample 邏輯走 PipelineThroughputSample，本 mock test
    ///     正驗 emitter 邏輯 + scheduler 整合）。
    struct MockPipelineThroughputEmitter {
        ticks: u32,
    }

    #[async_trait]
    impl DomainEmitter for MockPipelineThroughputEmitter {
        fn domain(&self) -> HealthDomain {
            HealthDomain::PipelineThroughput
        }

        fn sample_interval_sec(&self) -> u64 {
            1
        }

        async fn sample(&mut self) -> Result<Vec<Box<dyn MetricSample>>, M3Error> {
            self.ticks += 1;
            let snapshot = PipelineThroughputSample {
                ws_tick_rate_per_sec: 2.5,
                ws_heartbeat_lag_ms: 50,
                ws_subscription_drift_count: 0,
                strategy_signal_rate_per_min: 1.0,
                ipc_roundtrip_ms_p99: 2.0,
            };
            Ok(snapshot
                .into_metric_rows()
                .into_iter()
                .map(|r| Box::new(r) as Box<dyn MetricSample>)
                .collect::<Vec<_>>())
        }
    }

    let writer = Arc::new(InMemoryHealthObservationWriter::new());
    let writer_for_scheduler: Arc<dyn HealthObservationWriter> =
        Arc::clone(&writer) as Arc<dyn HealthObservationWriter>;

    let event_bus = Arc::new(HealthEventBus::new());
    let engine_mode: EngineModeProvider = Arc::new(|| "demo".to_string());

    let emitter: Box<dyn DomainEmitter> = Box::new(MockPipelineThroughputEmitter { ticks: 0 });
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
        "AC-1a proxy: in-memory writer rows {} < 5 (expected ≥ 5)",
        total
    );
    // 5 metric × 5+ tick = ≥ 25 row。
    assert!(
        total >= 25,
        "AC-1a 5 metric × 5+ tick 預期 ≥ 25 row，實際 {}",
        total
    );

    for row in writer.snapshot() {
        assert_eq!(
            row.domain,
            HealthDomain::PipelineThroughput,
            "row.domain 必為 pipeline_throughput"
        );
        assert_eq!(row.engine_mode, "demo", "Sprint 2 不寫 live");
    }

    // 驗 5 個 metric_name 都出現過。
    let snapshot = writer.snapshot();
    let metric_names: std::collections::HashSet<&str> =
        snapshot.iter().map(|r| r.metric_name.as_str()).collect();
    assert!(metric_names.contains("ws_tick_rate_per_sec"));
    assert!(metric_names.contains("ws_heartbeat_lag_ms"));
    assert!(metric_names.contains("ws_subscription_drift_count"));
    assert!(metric_names.contains("strategy_signal_rate_per_min"));
    assert!(metric_names.contains("ipc_roundtrip_ms_p99"));
}

// ============================================================
// AC-5 spike feature not active in default build
// ============================================================

/// AC-5 production binary 不滲透 mock time：本 test 在 default build 下執行能
/// 跑通，即證 PipelineThroughputEmitter / pipeline_throughput.rs 不引 spike
/// feature compile gate。
///
/// 真實 nm scan（QA empirical 走）:
///   nm target/release/openclaw_engine | grep -E "(mock_instant|tokio::time::pause|spike)" | wc -l
///   expect 0
#[test]
fn test_sprint2_track_b_spike_feature_not_active_in_default_build() {
    // 本 test 無需 spike feature 也能跑通，證明 Sprint 2 Track B IMPL 不依
    // spike feature。
    let probe = StubSourceProbe {
        ws_tick_rate_per_sec: 1.5,
        ws_heartbeat_lag_ms: 10,
        ws_subscription_drift_count: 0,
        strategy_signal_rate_per_min: 0.8,
        ipc_roundtrip_ms_p99: 2.0,
    };
    let emitter = PipelineThroughputEmitter::new(probe);
    assert_eq!(emitter.domain(), HealthDomain::PipelineThroughput);
    assert_eq!(
        emitter.sample_interval_sec(),
        30,
        "default sample_interval = 30s per spec §2.1"
    );
}

// ============================================================
// Sample 路徑端到端 — emitter sample → scheduler → writer 整合
// ============================================================

/// 端到端整合 test：PipelineThroughputEmitter（注入 stub probe）→ scheduler
/// → in-memory writer。
///
/// 為什麼此 test 補強 AC-1a / AC-2 / AC-4 之外的端到端 sanity:
///   - AC-1a 用 mock emitter；本 test 用真實 PipelineThroughputEmitter 接
///     stub source probe，驗 sample_now / into_metric_rows / DomainEmitter
///     trait impl 整條 path。
///   - scheduler 端 5 metric → 5 row 寫入 in-memory writer，驗 metric_name +
///     value + state 對齊預期。
#[tokio::test]
async fn test_sprint2_track_b_real_emitter_through_scheduler() {
    // OK-band 注入 stub source。
    let probe = StubSourceProbe {
        ws_tick_rate_per_sec: 2.5,
        ws_heartbeat_lag_ms: 50,
        ws_subscription_drift_count: 0,
        strategy_signal_rate_per_min: 1.0,
        ipc_roundtrip_ms_p99: 2.0,
    };
    // 由於 PipelineThroughputEmitter sample_interval 寫死 30s（per spec §2.1），
    // 本 test 用 wrapper 改寫 interval 1s 跑 6s ≥ 5 tick。
    struct FastIntervalWrapper {
        inner: PipelineThroughputEmitter,
    }

    #[async_trait]
    impl DomainEmitter for FastIntervalWrapper {
        fn domain(&self) -> HealthDomain {
            self.inner.domain()
        }

        fn sample_interval_sec(&self) -> u64 {
            1
        }

        async fn sample(&mut self) -> Result<Vec<Box<dyn MetricSample>>, M3Error> {
            self.inner.sample().await
        }
    }

    let emitter = PipelineThroughputEmitter::new(probe);
    let wrapper = FastIntervalWrapper { inner: emitter };

    let writer = Arc::new(InMemoryHealthObservationWriter::new());
    let writer_for_scheduler: Arc<dyn HealthObservationWriter> =
        Arc::clone(&writer) as Arc<dyn HealthObservationWriter>;

    let event_bus = Arc::new(HealthEventBus::new());
    let engine_mode: EngineModeProvider = Arc::new(|| "demo".to_string());

    let scheduler = MetricEmitterScheduler::new(
        vec![Box::new(wrapper) as Box<dyn DomainEmitter>],
        writer_for_scheduler,
        event_bus,
        engine_mode,
    );

    let cancel = CancellationToken::new();
    let cancel_clone = cancel.clone();

    let handle = tokio::spawn(async move {
        let _ = scheduler.run(cancel_clone).await;
    });

    tokio::time::sleep(Duration::from_secs(4)).await;
    cancel.cancel();
    let _ = handle.await;

    let snapshot = writer.snapshot();
    assert!(
        snapshot.len() >= 10,
        "≥ 5 metric × ≥ 2 tick = ≥ 10 row 寫入，實際 {}",
        snapshot.len()
    );

    // 驗 OK band 採樣下 SM state 維持 OK（沒升階）。
    for row in &snapshot {
        assert_eq!(row.domain, HealthDomain::PipelineThroughput);
        assert_eq!(row.engine_mode, "demo");
        // OK 採樣下 state 應為 OK（dwell 1s 不足 60s，不可能 fire）。
        assert_eq!(
            row.state,
            HealthState::HealthOk,
            "OK band 採樣下 state 應為 OK: metric={}",
            row.metric_name
        );
    }
}
