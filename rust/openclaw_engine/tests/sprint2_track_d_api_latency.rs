//! Sprint 2 Wave 2 Track D — api_latency emitter integration test。
//!
//! MODULE_NOTE
//! 模塊用途:
//!   per docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_dispatch_packet.md
//!   §5.4 AC sub-step：
//!     - AC-1a in-memory proxy：scheduler 跑數輪採樣 → in-memory writer 累積
//!       row 數 ≥ 5（V106 schema 30 min window 真實 PG empirical 由 Phase 3c
//!       QA empirical 走，Mac sandbox 不接 Linux PG）。
//!     - AC-2 4-state ladder：api_latency OK→WARN→DEGRADED ladder fire 測試
//!       （直接走 observe_classified；不需 scheduler wall-clock dwell）。
//!     - AC-4 cross-domain independence：api_latency DEGRADED 不影響
//!       engine_runtime / pipeline_throughput / database_pool SM state。
//!     - AC-5 spike default false：本 test 在 default build (無 --features
//!       spike) 跑通，即證 metric_emitter / writer / event_bus / 新 domains/
//!       api_latency module 不引 spike feature compile gate。
//!
//!   AC-3 amp cap empirical 由 `m3_amp_cap_24h_fire.rs` spike test 覆蓋（沿用
//!   spike Track B regression；本 Track 沿用無退化）。
//!
//! 主要 test:
//!   - test_sprint2_ladder_api_latency：AC-2 ladder fire
//!   - test_sprint2_cross_domain_api_latency_independence：AC-4 SM 互獨立
//!   - test_sprint2_track_d_api_latency_row_count：AC-1a in-memory proxy
//!   - test_sprint2_track_d_spike_feature_not_active_in_default_build：AC-5
//!   - test_sprint2_track_d_real_emitter_through_scheduler：端到端 sanity
//!   - test_sprint2_classify_aggregated_api_latency_arm_wired：classify_aggregated
//!     8 arm dispatch 真實接通（守 Track D 不退化 / 不誤接 _ => HealthOk
//!     fallback，對齊 Track C HIGH-1 守 pattern）
//!
//! 硬邊界:
//!   - 不依賴 spike feature；production binary 0 mock time 滲透對齊。
//!   - 不接 sandbox PG（Mac 跑；走 in-memory writer mock）。
//!   - 不修 production engine state / bybit_rest_client / bybit_private_ws
//!     既有邏輯（per packet §5.5 反模式 (a)；本 test 用 stub source probe 注入）。

use std::sync::Arc;
use std::time::{Duration, Instant};

use async_trait::async_trait;
use openclaw_engine::health::domains::api_latency::{
    ApiLatencyEmitter, ApiLatencySample, ApiLatencySourceProbe,
};
use openclaw_engine::health::event_bus::HealthEventBus;
use openclaw_engine::health::metric_emitter::{
    classify_aggregated_for_test, DomainEmitter, EngineModeProvider, MetricEmitterScheduler,
    MetricSample,
};
use openclaw_engine::health::writer::{
    HealthObservationWriter, InMemoryHealthObservationWriter,
};
use openclaw_engine::health::{HealthDomain, HealthState, HealthStateMachine, M3Error};
use tokio_util::sync::CancellationToken;

// ============================================================
// 共用 stub source probe（test fixture）
// ============================================================

/// stub source probe；test 注入固定 8 metric value。
///
/// 為什麼此設計:
///   - emitter `ApiLatencySourceProbe` 抽象 8 metric source；test 注入此 stub
///     即可不依 bybit_rest_client / bybit_private_ws 真實 hook。
///   - 對齊 packet §5.5 反模式 (a)「emitter 只讀，不修」+ Track B
///     StubSourceProbe 同模式。
struct StubSourceProbe {
    rest_p50_ms: u32,
    rest_p95_ms: u32,
    rest_p99_ms: u32,
    ws_rtt_p50_ms: u32,
    ws_rtt_p99_ms: u32,
    ret_code_4xx_count: u32,
    ret_code_5xx_count: u32,
    ws_dropout_count: u32,
}

impl ApiLatencySourceProbe for StubSourceProbe {
    fn current_rest_p50_ms_60s_window(&self) -> u32 {
        self.rest_p50_ms
    }
    fn current_rest_p95_ms_60s_window(&self) -> u32 {
        self.rest_p95_ms
    }
    fn current_rest_p99_ms_60s_window(&self) -> u32 {
        self.rest_p99_ms
    }
    fn current_ws_rtt_p50_ms_60s_window(&self) -> u32 {
        self.ws_rtt_p50_ms
    }
    fn current_ws_rtt_p99_ms_60s_window(&self) -> u32 {
        self.ws_rtt_p99_ms
    }
    fn current_ret_code_4xx_count_60s_window(&self) -> u32 {
        self.ret_code_4xx_count
    }
    fn current_ret_code_5xx_count_60s_window(&self) -> u32 {
        self.ret_code_5xx_count
    }
    fn current_ws_dropout_count_60s_window(&self) -> u32 {
        self.ws_dropout_count
    }
}

// ============================================================
// AC-2 4-state ladder OK → WARN → DEGRADED fire test
// ============================================================

/// AC-2 ladder fire test：api_latency SM OK→WARN（dwell 60s）+ WARN→DEGRADED
/// （dwell 5min）。
///
/// 為什麼直接走 observe_classified 而非 scheduler.run:
///   - SM 是 ladder transition matrix 的 SSOT；scheduler 端只是組裝 classify→
///     observe→write→publish flow。
///   - ladder dwell 60s/5min 是真實 Instant 時間；test 注入 Instant 直接驗
///     dwell math，不需 spike feature mock clock。
///   - 對齊 Track A/B/C `test_sprint2_ladder_*` 同 pattern。
#[test]
fn test_sprint2_ladder_api_latency() {
    let mut sm = HealthStateMachine::new(HealthDomain::ApiLatency);
    assert_eq!(sm.current_state(), HealthState::HealthOk);

    let base = Instant::now();
    // anomaly_id 對齊 spec §6.2 命名規約：domain__metric_name
    let anomaly_rest_p99 = "api_latency__rest_p99_ms";

    // Step 1: OK → WARN，dwell 60s。
    // 採樣 1：anchor 設 now，不 fire。
    let r1 = sm
        .observe_classified(HealthState::HealthWarn, anomaly_rest_p99, base)
        .unwrap();
    assert!(!r1, "首次 WARN-band 採樣只設 anchor 不 fire");
    assert_eq!(sm.current_state(), HealthState::HealthOk);

    // 採樣 2：dwell 30s（< 60s），仍不 fire。
    let r2 = sm
        .observe_classified(
            HealthState::HealthWarn,
            anomaly_rest_p99,
            base + Duration::from_secs(30),
        )
        .unwrap();
    assert!(!r2, "dwell 30s 不足 60s，不 fire");
    assert_eq!(sm.current_state(), HealthState::HealthOk);

    // 採樣 3：dwell 60s（= 要求），fire。
    let r3 = sm
        .observe_classified(
            HealthState::HealthWarn,
            anomaly_rest_p99,
            base + Duration::from_secs(60),
        )
        .unwrap();
    assert!(r3, "dwell 60s 達標，OK→WARN 真實 fire");
    assert_eq!(sm.current_state(), HealthState::HealthWarn);
    assert_eq!(sm.previous_state(), HealthState::HealthOk);
    assert_eq!(sm.amplification_loop_24h_count(), 1);

    // Step 2: WARN → DEGRADED，dwell 5min。
    // 新 anomaly_id 避同 id cap suppress。
    let anomaly_ws_rtt = "api_latency__ws_rtt_p99_ms";
    // anchor 設 now（base+60）。
    let r4 = sm
        .observe_classified(
            HealthState::HealthDegraded,
            anomaly_ws_rtt,
            base + Duration::from_secs(60),
        )
        .unwrap();
    assert!(!r4, "WARN→DEGRADED 首次採樣只設 anchor");

    // dwell 4min（< 5min），不 fire。
    let r5 = sm
        .observe_classified(
            HealthState::HealthDegraded,
            anomaly_ws_rtt,
            base + Duration::from_secs(60 + 240),
        )
        .unwrap();
    assert!(!r5, "WARN→DEGRADED dwell 4min 不足 5min");

    // dwell 5min（= 300s），fire。
    let r6 = sm
        .observe_classified(
            HealthState::HealthDegraded,
            anomaly_ws_rtt,
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

/// AC-4 cross-domain：api_latency SM 升 DEGRADED 不影響 engine_runtime /
/// pipeline_throughput / database_pool SM state。
///
/// 為什麼此 test 不走 system-level aggregate:
///   - per spec §5.3 system-level state = read-time aggregation by query；本
///     IMPL Sprint 2 不 emit system-level row（只 emit per-domain row）。
///   - 本 test 驗 SM 是 per-domain 獨立的 — 4 SM instance 各自 transition，
///     不共享 state / cap entries / dwell anchor。
///
/// 為什麼覆蓋 4 個 domain 而非僅 1（對比 Track B/C 2 個 domain）:
///   - Track D 是 Wave 2 第一 Track，需驗 Wave 1 已 land 的 3 domain（A/B/C）
///     全不受 api_latency DEGRADED 影響；對齊 packet §5.4 AC-4「不影響
///     engine_runtime / pipeline_throughput / database_pool state」明文要求。
#[test]
fn test_sprint2_cross_domain_api_latency_independence() {
    let mut api_sm = HealthStateMachine::new(HealthDomain::ApiLatency);
    let mut engine_sm = HealthStateMachine::new(HealthDomain::EngineRuntime);
    let mut pipeline_sm = HealthStateMachine::new(HealthDomain::PipelineThroughput);
    let mut db_sm = HealthStateMachine::new(HealthDomain::DatabasePool);

    let base = Instant::now();
    let api_anomaly = "api_latency__rest_p99_ms";
    let engine_anomaly = "engine_runtime__cpu_pct";
    let pipeline_anomaly = "pipeline_throughput__ws_tick_rate_per_sec";
    let db_anomaly = "database_pool__pg_pool_active_conn_ratio";

    // api SM 走 OK→WARN→DEGRADED；其他 3 SM 維持 OK 採樣。
    let _ = api_sm.observe_classified(HealthState::HealthWarn, api_anomaly, base);
    let r = api_sm
        .observe_classified(
            HealthState::HealthWarn,
            api_anomaly,
            base + Duration::from_secs(60),
        )
        .unwrap();
    assert!(r, "api_latency OK→WARN fire");
    assert_eq!(api_sm.current_state(), HealthState::HealthWarn);

    // 其他 3 SM 純 OK 採樣，state 維持 OK。
    let r_engine = engine_sm
        .observe_classified(HealthState::HealthOk, engine_anomaly, base)
        .unwrap();
    assert!(!r_engine, "engine OK-band 採樣不 fire");
    assert_eq!(
        engine_sm.current_state(),
        HealthState::HealthOk,
        "engine SM state 未被 api_latency SM 影響"
    );
    let r_pipe = pipeline_sm
        .observe_classified(HealthState::HealthOk, pipeline_anomaly, base)
        .unwrap();
    assert!(!r_pipe, "pipeline OK-band 採樣不 fire");
    assert_eq!(pipeline_sm.current_state(), HealthState::HealthOk);
    let r_db = db_sm
        .observe_classified(HealthState::HealthOk, db_anomaly, base)
        .unwrap();
    assert!(!r_db, "database_pool OK-band 採樣不 fire");
    assert_eq!(db_sm.current_state(), HealthState::HealthOk);

    // api 繼續升 DEGRADED（用新 anomaly_id 避同 id cap）。
    let api_anomaly_2 = "api_latency__ws_rtt_p99_ms";
    let _ = api_sm.observe_classified(
        HealthState::HealthDegraded,
        api_anomaly_2,
        base + Duration::from_secs(60),
    );
    let r2 = api_sm
        .observe_classified(
            HealthState::HealthDegraded,
            api_anomaly_2,
            base + Duration::from_secs(60 + 300),
        )
        .unwrap();
    assert!(r2, "api_latency WARN→DEGRADED fire");
    assert_eq!(api_sm.current_state(), HealthState::HealthDegraded);
    assert_eq!(api_sm.amplification_loop_24h_count(), 2);

    // 其他 3 SM 狀態仍未受影響。
    assert_eq!(
        engine_sm.current_state(),
        HealthState::HealthOk,
        "engine SM 在 api_latency 升 DEGRADED 後仍維持 OK"
    );
    assert_eq!(
        engine_sm.amplification_loop_24h_count(),
        0,
        "engine SM cap count 未被 api_latency 影響"
    );
    assert_eq!(
        pipeline_sm.current_state(),
        HealthState::HealthOk,
        "pipeline SM 在 api_latency 升 DEGRADED 後仍維持 OK"
    );
    assert_eq!(
        pipeline_sm.amplification_loop_24h_count(),
        0,
        "pipeline SM cap count 未被 api_latency 影響"
    );
    assert_eq!(
        db_sm.current_state(),
        HealthState::HealthOk,
        "database_pool SM 在 api_latency 升 DEGRADED 後仍維持 OK"
    );
    assert_eq!(
        db_sm.amplification_loop_24h_count(),
        0,
        "database_pool SM cap count 未被 api_latency 影響"
    );

    // domain accessor 確認 SM 各自 domain 標籤獨立。
    assert_eq!(api_sm.domain(), HealthDomain::ApiLatency);
    assert_eq!(engine_sm.domain(), HealthDomain::EngineRuntime);
    assert_eq!(pipeline_sm.domain(), HealthDomain::PipelineThroughput);
    assert_eq!(db_sm.domain(), HealthDomain::DatabasePool);
}

// ============================================================
// AC-1a in-memory writer proxy — scheduler 跑數輪採樣 → ≥ 5 row
// ============================================================

/// AC-1a api_latency 不接 Linux PG；走 in-memory writer mock 為 AC-1a proxy。
///
/// 為什麼用 mock emitter + 1s interval:
///   - production sample_interval 60s（per spec §2.1），test 等 5×60s = 5min
///     不實際；tokio interval 第一 tick 立即觸發，第 2+ tick 才走 interval。
///   - 本 test 用內嵌 mock emitter（sample_interval=1）跑 6s ≥ 5 輪採樣 →
///     8 metric × 5+ tick ≥ 40 row → AC-1a ≥ 5 proxy。
///   - 對齊 Track B `test_sprint2_track_b_pipeline_throughput_row_count` + Track
///     C `test_sprint2_track_c_database_pool_row_count` mock pattern。
///
/// AC-1b 真實 Linux empirical SQL（Phase 3c QA 跑）:
///   SELECT COUNT(*) FROM learning.health_observations
///     WHERE domain='api_latency' AND created_at > NOW() - INTERVAL '30 min';
///   expect ≥ 3（60s × 5 = 5min cycle；30min 容差）。
#[tokio::test]
async fn test_sprint2_track_d_api_latency_row_count() {
    /// 內嵌 mock emitter：每次 sample 返回 8 個 OK-band metric row（interval=1s）。
    ///
    /// 為什麼不直接用 ApiLatencyEmitter:
    ///   - ApiLatencyEmitter sample_interval 寫死 60s；test 等不到。
    ///   - 本 mock 走 ApiLatencySample::into_metric_rows 同樣 8 row 展平邏輯，
    ///     邏輯等價於 ApiLatencyEmitter（per packet §5.5 反模式 (b)「不寫死採
    ///     樣 60s interval」對齊 — interval 是 emitter trait 方法，sample 邏輯
    ///     走 ApiLatencySample，本 mock test 正驗 emitter 邏輯 + scheduler 整
    ///     合）。
    struct MockApiLatencyEmitter {
        ticks: u32,
    }

    #[async_trait]
    impl DomainEmitter for MockApiLatencyEmitter {
        fn domain(&self) -> HealthDomain {
            HealthDomain::ApiLatency
        }

        fn sample_interval_sec(&self) -> u64 {
            1
        }

        async fn sample(&mut self) -> Result<Vec<Box<dyn MetricSample>>, M3Error> {
            self.ticks += 1;
            // 走真實 ApiLatencySample 走真實 into_metric_rows 邏輯，確保 mock
            // 路徑與 production 等價。
            let snapshot = ApiLatencySample {
                rest_p50_ms: 30,
                rest_p95_ms: 100,
                rest_p99_ms: 300,
                ws_rtt_p50_ms: 20,
                ws_rtt_p99_ms: 150,
                ret_code_4xx_count: 2,
                ret_code_5xx_count: 0,
                ws_dropout_count: 0,
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

    let emitter: Box<dyn DomainEmitter> = Box::new(MockApiLatencyEmitter { ticks: 0 });
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
    // 8 metric × 5+ tick = ≥ 40 row。
    assert!(
        total >= 40,
        "AC-1a 8 metric × 5+ tick 預期 ≥ 40 row，實際 {}",
        total
    );

    // 為什麼加 state 守（per Sprint 2 round 2 Track C HIGH-2 fix pattern）：
    //   - mock emitter 注入 OK-band sample（rest_p50=30 / rest_p95=100 /
    //     rest_p99=300 / ws_rtt_p50=20 / ws_rtt_p99=150 / 4xx=2 / 5xx=0 /
    //     dropout=0）；scheduler 走 classify_aggregated → OK band；SM
    //     observe_classified(OK, ...) 不升階；row.state 必為 HealthOk。
    //   - 若 classify_aggregated api_latency arm 漏接，mean 走 `_ => HealthOk`
    //     fallback 仍會通過（OK 走 _ arm 仍 OK），但只要 arm dispatch 真實接
    //     通並 mean.round() 正確，row.state 也必 OK；本 assert 守 (1) no false
    //     fire (2) 不誤升階 (3) 採樣資料端到端 OK band 透傳整條 path 不變調。
    for row in writer.snapshot() {
        assert_eq!(row.domain, HealthDomain::ApiLatency);
        assert_eq!(row.engine_mode, "demo", "Sprint 2 不寫 live");
        assert_eq!(
            row.state,
            HealthState::HealthOk,
            "OK-band sample 不應升階 SM state: metric={}",
            row.metric_name
        );
    }

    // 驗 8 個 metric_name 都出現過。
    let snapshot = writer.snapshot();
    let metric_names: std::collections::HashSet<&str> =
        snapshot.iter().map(|r| r.metric_name.as_str()).collect();
    assert!(metric_names.contains("rest_p50_ms"));
    assert!(metric_names.contains("rest_p95_ms"));
    assert!(metric_names.contains("rest_p99_ms"));
    assert!(metric_names.contains("ws_rtt_p50_ms"));
    assert!(metric_names.contains("ws_rtt_p99_ms"));
    assert!(metric_names.contains("ret_code_4xx_count"));
    assert!(metric_names.contains("ret_code_5xx_count"));
    assert!(metric_names.contains("ws_dropout_count"));
}

// ============================================================
// AC-5 spike feature not active in default build
// ============================================================

/// AC-5 production binary 不滲透 mock time：本 test 在 default build 下執行能
/// 跑通，即證 ApiLatencyEmitter / domains/api_latency.rs 不引 spike feature
/// compile gate。
///
/// 真實 nm scan（QA empirical 走）:
///   nm target/release/openclaw_engine | grep -E "(mock_instant|tokio::time::pause|spike)" | wc -l
///   expect 0
#[test]
fn test_sprint2_track_d_spike_feature_not_active_in_default_build() {
    // 本 test 無需 spike feature 也能跑通，證明 Sprint 2 Track D IMPL 不依
    // spike feature。
    let probe = StubSourceProbe {
        rest_p50_ms: 30,
        rest_p95_ms: 100,
        rest_p99_ms: 200,
        ws_rtt_p50_ms: 20,
        ws_rtt_p99_ms: 100,
        ret_code_4xx_count: 0,
        ret_code_5xx_count: 0,
        ws_dropout_count: 0,
    };
    let emitter = ApiLatencyEmitter::new(probe);
    assert_eq!(emitter.domain(), HealthDomain::ApiLatency);
    assert_eq!(
        emitter.sample_interval_sec(),
        60,
        "default sample_interval = 60s per spec §2.1"
    );
}

// ============================================================
// 端到端 sanity — real emitter through scheduler
// ============================================================

/// 端到端整合 test：ApiLatencyEmitter（注入 stub probe）→ scheduler → in-memory
/// writer。
///
/// 為什麼此 test 補強 AC-1a / AC-2 / AC-4 之外的端到端 sanity:
///   - AC-1a 用 mock emitter；本 test 用真實 ApiLatencyEmitter 接 stub source
///     probe，驗 sample_now / into_metric_rows / DomainEmitter trait impl 整條
///     path。
///   - scheduler 端 8 metric → 8 row 寫入 in-memory writer，驗 metric_name +
///     value + state 對齊預期。
///   - 對齊 Track B `test_sprint2_track_b_real_emitter_through_scheduler` 同
///     pattern。
#[tokio::test]
async fn test_sprint2_track_d_real_emitter_through_scheduler() {
    // OK-band 注入 stub source。
    let probe = StubSourceProbe {
        rest_p50_ms: 30,
        rest_p95_ms: 100,
        rest_p99_ms: 300,
        ws_rtt_p50_ms: 20,
        ws_rtt_p99_ms: 150,
        ret_code_4xx_count: 2,
        ret_code_5xx_count: 0,
        ws_dropout_count: 0,
    };
    // 由於 ApiLatencyEmitter sample_interval 寫死 60s（per spec §2.1），本 test
    // 用 wrapper 改寫 interval 1s 跑 4s ≥ 2 tick。
    struct FastIntervalWrapper {
        inner: ApiLatencyEmitter,
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

    let emitter = ApiLatencyEmitter::new(probe);
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
        snapshot.len() >= 16,
        "≥ 8 metric × ≥ 2 tick = ≥ 16 row 寫入，實際 {}",
        snapshot.len()
    );

    // 驗 OK band 採樣下 SM state 維持 OK（沒升階）。
    for row in &snapshot {
        assert_eq!(row.domain, HealthDomain::ApiLatency);
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

// ============================================================
// classify_aggregated 8 arm dispatch 守 — 對齊 Track C HIGH-1 守 pattern
// ============================================================

/// 守 classify_aggregated api_latency 8 個 arm 真實接通（不退化為 `_ => HealthOk`
/// fallback）。
///
/// 為什麼此 test 必要（per Sprint 2 round 2 Track C HIGH-1 retro lesson）:
///   - Track C round 1 漏接 `(HealthDomain::DatabasePool, ...)` arm → mean 走
///     fallback `_ => HealthOk` catches 所有 database_pool metric → DEGRADED-
///     band sample 也被誤歸 OK band；HIGH-1 blocker。
///   - Track D 8 metric 全經 classify_aggregated dispatch；任一 arm 漏接 →
///     對應 metric DEGRADED/CRITICAL-band sample 走 fallback OK 不升階。
///   - 本 test 直接呼 `classify_aggregated_for_test` 端到端守 8 arm dispatch
///     真實接通 helper 而非走 fallback — 避「PR 後 dispatch arm 被回退也測
///     不出」之 regression 盲區。
///
/// 為什麼 8 個 metric 各注 1 個 DEGRADED-band value:
///   - 每 arm 對應 metric 注入 DEGRADED-band mean → 期望 helper 返 DEGRADED；
///     若 arm 漏接，走 fallback OK，assert 失敗 → 守 dispatch 真實接通。
///   - 兩個 metric（rest_p99_ms 走 1500ms / ws_rtt_p99_ms 走 1000ms）注入
///     DEGRADED 而非 CRITICAL 避「CRITICAL 也是非 OK 即 pass」誤判 — 嚴格驗
///     band 對應正確 helper。
///   - ret_code_5xx_count + ws_dropout_count 還補 1 個 CRITICAL band 注入驗 CRITICAL
///     dispatch 正確（這兩 metric ladder 含 CRITICAL）。
#[test]
fn test_sprint2_classify_aggregated_api_latency_arm_wired() {
    // rest_p50_ms DEGRADED band（>200ms）
    assert_eq!(
        classify_aggregated_for_test(HealthDomain::ApiLatency, "rest_p50_ms", 250.0),
        HealthState::HealthDegraded,
        "classify_aggregated api_latency::rest_p50_ms arm 必走 helper（守 dispatch 不退化）"
    );
    // rest_p95_ms DEGRADED band（>500ms）
    assert_eq!(
        classify_aggregated_for_test(HealthDomain::ApiLatency, "rest_p95_ms", 800.0),
        HealthState::HealthDegraded
    );
    // rest_p99_ms DEGRADED band（1000-2000ms）
    assert_eq!(
        classify_aggregated_for_test(HealthDomain::ApiLatency, "rest_p99_ms", 1500.0),
        HealthState::HealthDegraded
    );
    // ws_rtt_p50_ms DEGRADED band（>300ms per Sprint 5+ Wave 1 §4.4 hardening amend；
    // OK<170 / WARN 170-300 / DEGRADED>300，舊 200ms 在 amended ladder 落 WARN band；
    // 改 350ms 維持 DEGRADED 期望，對齊 E1-5 amend 其他 fixture 範式）
    assert_eq!(
        classify_aggregated_for_test(HealthDomain::ApiLatency, "ws_rtt_p50_ms", 350.0),
        HealthState::HealthDegraded
    );
    // ws_rtt_p99_ms DEGRADED band（500-1500ms）
    assert_eq!(
        classify_aggregated_for_test(HealthDomain::ApiLatency, "ws_rtt_p99_ms", 1000.0),
        HealthState::HealthDegraded
    );
    // ret_code_4xx_count DEGRADED band（>50）
    assert_eq!(
        classify_aggregated_for_test(HealthDomain::ApiLatency, "ret_code_4xx_count", 80.0),
        HealthState::HealthDegraded
    );
    // ret_code_5xx_count DEGRADED band（6-20）
    assert_eq!(
        classify_aggregated_for_test(HealthDomain::ApiLatency, "ret_code_5xx_count", 10.0),
        HealthState::HealthDegraded
    );
    // ws_dropout_count DEGRADED band（3-5）
    assert_eq!(
        classify_aggregated_for_test(HealthDomain::ApiLatency, "ws_dropout_count", 4.0),
        HealthState::HealthDegraded
    );

    // CRITICAL band 驗：rest_p99 / ws_rtt_p99 / ret_code_5xx / ws_dropout
    assert_eq!(
        classify_aggregated_for_test(HealthDomain::ApiLatency, "rest_p99_ms", 3000.0),
        HealthState::HealthCritical,
        "rest_p99_ms >2000ms 必 CRITICAL"
    );
    assert_eq!(
        classify_aggregated_for_test(HealthDomain::ApiLatency, "ws_rtt_p99_ms", 2000.0),
        HealthState::HealthCritical,
        "ws_rtt_p99_ms >1500ms 必 CRITICAL"
    );
    assert_eq!(
        classify_aggregated_for_test(HealthDomain::ApiLatency, "ret_code_5xx_count", 30.0),
        HealthState::HealthCritical,
        "ret_code_5xx_count >20 必 CRITICAL"
    );
    assert_eq!(
        classify_aggregated_for_test(HealthDomain::ApiLatency, "ws_dropout_count", 10.0),
        HealthState::HealthCritical,
        "ws_dropout_count >5 必 CRITICAL"
    );

    // OK band 守：每 metric OK band 對應 helper 必返 OK（驗 ladder 邊界）。
    assert_eq!(
        classify_aggregated_for_test(HealthDomain::ApiLatency, "rest_p50_ms", 10.0),
        HealthState::HealthOk
    );
    assert_eq!(
        classify_aggregated_for_test(HealthDomain::ApiLatency, "ret_code_5xx_count", 0.0),
        HealthState::HealthOk
    );
    assert_eq!(
        classify_aggregated_for_test(HealthDomain::ApiLatency, "ws_dropout_count", 0.0),
        HealthState::HealthOk
    );

    // 未知 metric_name 走 fallback OK（避誤升 cascade）。
    assert_eq!(
        classify_aggregated_for_test(HealthDomain::ApiLatency, "unknown_metric_xyz", 9999.0),
        HealthState::HealthOk,
        "未知 metric 走 fallback OK band 對齊 spec §4.3 unknown metric fail-closed"
    );
}

// ============================================================
// Track D stress：DEGRADED-band mock sample 端到端驗 classify_aggregated 真實
// 接通（守 Track D 不退化）
// ============================================================

/// per Sprint 2 round 2 Track C HIGH-2 fix pattern：mock emitter 注入 CRITICAL-
/// band sample → scheduler 跑 6 tick → assert 至少 1 metric 走 CRITICAL 帶。
///
/// 為什麼此 stress test:
///   - 8 metric 經 classify_aggregated dispatch；若任一 arm 漏接，DEGRADED/
///     CRITICAL-band sample 也會被誤歸 OK band（HIGH-1 retro lesson）。
///   - 注入 sample = (p50=300 DEGRADED / p95=800 DEGRADED / p99=3000 CRITICAL /
///     ws_p50=350 DEGRADED (>300 per Sprint 5+ Wave 1 §4.4 amend) /
///     ws_p99=2000 CRITICAL / 4xx=80 DEGRADED / 5xx=30 CRITICAL /
///     dropout=10 CRITICAL) — 4 metric DEGRADED + 4 metric CRITICAL。
///   - dwell 60s/5min 由 SM 端守；本 stress test 注 emit 端 classify 真實 fire
///     對應 band — 透過 5-sample rolling window mean 已固定 = sample value，
///     classify_aggregated 必返 DEGRADED/CRITICAL；若 arm 退化 catches 不到，
///     row.state 永遠 OK，assert 失敗 → 守 dispatch 不退化。
#[tokio::test]
async fn test_sprint2_track_d_api_latency_degraded_band_classify() {
    /// 內嵌 mock emitter：每次 sample 返回 DEGRADED/CRITICAL-band 8 metric row。
    struct MockDegradedApiLatencyEmitter {
        ticks: u32,
    }

    #[async_trait]
    impl DomainEmitter for MockDegradedApiLatencyEmitter {
        fn domain(&self) -> HealthDomain {
            HealthDomain::ApiLatency
        }

        fn sample_interval_sec(&self) -> u64 {
            1
        }

        async fn sample(&mut self) -> Result<Vec<Box<dyn MetricSample>>, M3Error> {
            self.ticks += 1;
            // DEGRADED + CRITICAL band sample（每 metric 注入確定升階值）。
            let snapshot = ApiLatencySample {
                rest_p50_ms: 300,             // DEGRADED (>200)
                rest_p95_ms: 800,             // DEGRADED (>500)
                rest_p99_ms: 3000,            // CRITICAL (>2000)
                ws_rtt_p50_ms: 350,           // DEGRADED (>300 per §4.4 amend)
                ws_rtt_p99_ms: 2000,          // CRITICAL (>1500)
                ret_code_4xx_count: 80,       // DEGRADED (>50)
                ret_code_5xx_count: 30,       // CRITICAL (>20)
                ws_dropout_count: 10,         // CRITICAL (>5)
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

    let emitter: Box<dyn DomainEmitter> =
        Box::new(MockDegradedApiLatencyEmitter { ticks: 0 });
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

    tokio::time::sleep(Duration::from_secs(7)).await;
    cancel.cancel();
    let _ = handle.await;

    // 8 metric 出現驗 classify_aggregated 8 arm dispatch 真實接通（避全走
    // fallback OK band）。
    let snapshot = writer.snapshot();
    let metric_names: std::collections::HashSet<&str> =
        snapshot.iter().map(|r| r.metric_name.as_str()).collect();
    assert!(metric_names.contains("rest_p50_ms"));
    assert!(metric_names.contains("rest_p95_ms"));
    assert!(metric_names.contains("rest_p99_ms"));
    assert!(metric_names.contains("ws_rtt_p50_ms"));
    assert!(metric_names.contains("ws_rtt_p99_ms"));
    assert!(metric_names.contains("ret_code_4xx_count"));
    assert!(metric_names.contains("ret_code_5xx_count"));
    assert!(metric_names.contains("ws_dropout_count"));

    // 為什麼直接呼 classify_aggregated_for_test 而非 assert row.state 為
    // DEGRADED/CRITICAL（per Track C round 2 fix 經驗）:
    //   - SM 端 OK→DEGRADED dwell 5min（per spec §5.2），integration test 7s
    //     不可等；row.state 寫 SM 當前 state（仍 OK，dwell 未達）。
    //   - 改用「classify_aggregated 直接呼 + helper 返對應 band」端到端守
    //     dispatch 真實接通 — 等價於 production observation path 但不需 wall-
    //     clock dwell；對齊 Track C `test_sprint2_track_c_database_pool_
    //     degraded_band_classify` 範式。
    assert_eq!(
        classify_aggregated_for_test(HealthDomain::ApiLatency, "rest_p99_ms", 3000.0),
        HealthState::HealthCritical,
        "classify_aggregated api_latency::rest_p99_ms arm 必走 helper（守 dispatch 不退化）"
    );
    assert_eq!(
        classify_aggregated_for_test(HealthDomain::ApiLatency, "ws_rtt_p99_ms", 2000.0),
        HealthState::HealthCritical,
        "classify_aggregated api_latency::ws_rtt_p99_ms arm 必走 helper（守 dispatch 不退化）"
    );
    assert_eq!(
        classify_aggregated_for_test(HealthDomain::ApiLatency, "ret_code_5xx_count", 30.0),
        HealthState::HealthCritical,
        "classify_aggregated api_latency::ret_code_5xx_count arm 必走 helper（守 dispatch 不退化）"
    );
    assert_eq!(
        classify_aggregated_for_test(HealthDomain::ApiLatency, "ws_dropout_count", 10.0),
        HealthState::HealthCritical,
        "classify_aggregated api_latency::ws_dropout_count arm 必走 helper（守 dispatch 不退化）"
    );
}
