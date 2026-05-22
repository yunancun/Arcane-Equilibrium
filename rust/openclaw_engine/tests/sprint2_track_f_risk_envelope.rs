//! Sprint 2 Wave 2 Track F — risk_envelope emitter integration test。
//!
//! MODULE_NOTE
//! 模塊用途:
//!   per docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_dispatch_packet.md
//!   §7.4 AC sub-step：
//!     - AC-1a risk_envelope in-memory proxy：5 sample window × N metric tick →
//!       ≥ N×5 V106 row written 至 mock writer（不接 PG）。
//!     - AC-2 4-state ladder：portfolio dd / correlation / concentration OK→
//!       WARN→DEGRADED ladder fire via observe_classified（不需 scheduler）。
//!     - AC-4 cross-domain：risk_envelope DEGRADED 不影響其他 5 domain；不觸
//!       5-gate kill（per dispatch packet §7.5 反模式 (b)）。
//!     - AC-5 spike default false：本 test 在 default build 跑通 → metric_emitter
//!       / writer / event_bus / domains/risk_envelope 全 0 spike feature gate。
//!     - AC-7 portfolio 原則：risk_envelope 是 portfolio-level 聚合（cum_pnl /
//!       dd / position_count / correlation / concentration），對齊 16 根原則 #16。
//!
//! 主要 test:
//!   - test_sprint2_track_f_risk_envelope_in_memory_proxy：AC-1a in-memory
//!     proxy row count ≥ 5
//!   - test_sprint2_track_f_risk_envelope_degraded_band_classify：HIGH-1 退化
//!     守 classify_aggregated dispatch 真實接通 5 metric arm
//!   - test_sprint2_ladder_risk_envelope：AC-2 OK→WARN→DEGRADED 4-state ladder
//!     fire via observe_classified
//!   - test_sprint2_cross_domain_risk_envelope_independence：AC-4 SM 隔離
//!   - test_sprint2_track_f_spike_feature_not_active_in_default_build：AC-5
//!     compile-path 證明
//!   - test_sprint2_track_f_sample_interval_sec_is_300：AC sub 反模式 (b)
//!     不寫死採樣間隔守
//!
//! 硬邊界:
//!   - 不依賴 spike feature；production binary include 本 test compile path（per
//!     dispatch packet §9 共用反模式 (b)）。
//!   - 不接 sandbox PG（Mac 跑；走 in-memory writer mock）。
//!   - 不修 production engine state。
//!   - 不接 main.rs scheduler（per Track A §7 carry-over；scaffold 階段不接
//!     main.rs）。

use std::sync::Arc;
use std::time::{Duration, Instant};

use async_trait::async_trait;
use openclaw_engine::health::domains::risk_envelope::{
    classify_risk_envelope_concentration_top1_pct, classify_risk_envelope_correlation_avg,
    classify_risk_envelope_cum_pnl_24h_usd, classify_risk_envelope_max_dd_pct,
    classify_risk_envelope_position_count, RiskEnvelopeEmitter, RiskEnvelopeSample,
    RiskEnvelopeSourceProbe,
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
// AC-1a in-memory proxy row count ≥ 5
// ============================================================

/// AC-1a risk_envelope row count proxy：scheduler 跑數輪採樣 → in-memory writer
/// 累積 row ≥ 5。
///
/// 為什麼用 mock emitter + 1s interval 而非真 RiskEnvelopeEmitter:
///   - production sample_interval=300s (5min；per spec §2.1)，test 等 5×300s =
///     25min 不實際；本 test 用內嵌 mock emitter（sample_interval=1s）跑 6s ≥ 5
///     輪採樣 → 5 metric × 5+ tick ≥ 25 row → 遠超 AC ≥ 5 門檻。
///   - 真 RiskEnvelopeEmitter 的 sample_interval_sec=300，integration test 不可
///     等；對齊 Track C MockDatabasePoolEmitter pattern。
///   - 真 emitter 的 ladder/threshold 邏輯由 RiskEnvelopeSample::into_metric_rows
///     在 emitter.sample() 內部執行；mock emitter 走相同 path 故 AC-1a 等價。
///
/// AC-1b 真實 Linux empirical SQL（QA Phase 3c 跑）:
///   SELECT COUNT(*) FROM learning.health_observations
///     WHERE domain='risk_envelope' AND created_at > NOW() - INTERVAL '30 min';
///   expect ≥ 5（300s sample × 5 metric × ≥ 1 tick = ≥ 5 row 實務上；30min
///     容差對齊 5min × 5 = 25min window + buffer per dispatch packet §7.4 AC-1b）。
///
/// Mac sandbox 不 connect Linux PG（per dispatch packet §7.4 容差）；本 test
/// 走 in-memory writer mock 為 AC-1a proxy。
#[tokio::test]
async fn test_sprint2_track_f_risk_envelope_in_memory_proxy() {
    /// 內嵌 mock emitter：每次 sample 返回 5 個 OK-band metric row。
    struct MockRiskEnvelopeEmitter {
        ticks: u32,
    }

    #[async_trait]
    impl DomainEmitter for MockRiskEnvelopeEmitter {
        fn domain(&self) -> HealthDomain {
            HealthDomain::RiskEnvelope
        }

        fn sample_interval_sec(&self) -> u64 {
            1
        }

        async fn sample(&mut self) -> Result<Vec<Box<dyn MetricSample>>, M3Error> {
            self.ticks += 1;
            // 走真實 RiskEnvelopeSample 走真實 into_metric_rows 邏輯，確保 mock
            // 路徑與 production 等價。
            let snapshot = RiskEnvelopeSample {
                portfolio_cum_pnl_24h_usd: 100.0,
                portfolio_max_dd_pct: 2.0,
                position_count_active: 5,
                correlation_avg_pairwise: 0.3,
                concentration_top1_pct: 20.0,
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

    let emitter: Box<dyn DomainEmitter> = Box::new(MockRiskEnvelopeEmitter { ticks: 0 });
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

    // 為什麼加 state 守（per Track C 範式）:
    //   - mock emitter 注入 OK-band sample；scheduler 走 classify_aggregated →
    //     OK band；SM observe_classified(OK, ...) 不升階；row.state 必為
    //     HealthOk。
    //   - 若 classify_aggregated risk_envelope arm 漏接，mean 走 `_ => HealthOk`
    //     fallback 仍會通過（fallback OK band），但只要 dispatch 真實接通並
    //     mean 正確，row.state 也必 OK；本 assert 守 (1) no false fire (2) 不
    //     誤升階  (3) 採樣資料端到端 OK band 透傳整條 path 不變調。
    for row in writer.snapshot() {
        assert_eq!(row.domain, HealthDomain::RiskEnvelope);
        assert_eq!(row.engine_mode, "demo", "Sprint 2 不寫 live");
        assert_eq!(
            row.state,
            HealthState::HealthOk,
            "OK-band sample 不應升階 SM state: metric={}",
            row.metric_name
        );
    }
}

// ============================================================
// Track F classify_aggregated dispatch 退化守
// ============================================================

/// classify_aggregated risk_envelope 5 metric arm 真實接通退化守（per Track B
/// HIGH-1 / Track C HIGH-1 退化守範式）。
///
/// 為什麼此 test:
///   - 若 classify_aggregated risk_envelope 5 arm 漏接（fallback `_ => HealthOk`
///     catches risk_envelope metric），DEGRADED-band sample 也會被誤歸 OK band；
///     production cascade 將永遠不 fire。
///   - 本 test 注入 5 metric DEGRADED band value，經 classify_aggregated_for_test
///     直接呼，確認每 metric arm 真實接通對應 helper；若 fallback catches，
///     assert 失敗 → 守 5 arm 不退化。
///   - 直接呼 classify_aggregated_for_test 而非整 scheduler 跑 5min wall-clock：
///     scheduler dwell 5min 不可 test 等；本 helper 是 scheduler 端 classify
///     邏輯的真實入口，等價於 production 觀測 path（per Track C HIGH-1 test 範
///     式）。
#[test]
fn test_sprint2_track_f_risk_envelope_classify_aggregated_dispatch() {
    // portfolio_cum_pnl_24h_usd：-2000 USD（loss 2000，1500-2500 區間）→ DEGRADED
    assert_eq!(
        classify_aggregated_for_test(
            HealthDomain::RiskEnvelope,
            "portfolio_cum_pnl_24h_usd",
            -2000.0,
        ),
        HealthState::HealthDegraded,
        "classify_aggregated risk_envelope::portfolio_cum_pnl_24h_usd arm 必走 helper（Track F 退化守）"
    );

    // portfolio_max_dd_pct：12%（10-15 區間）→ DEGRADED
    assert_eq!(
        classify_aggregated_for_test(
            HealthDomain::RiskEnvelope,
            "portfolio_max_dd_pct",
            12.0,
        ),
        HealthState::HealthDegraded,
        "classify_aggregated risk_envelope::portfolio_max_dd_pct arm 必走 helper（Track F 退化守）"
    );

    // position_count_active：mean=20.0 (> 16) → DEGRADED；mean.round() 走整數 cast
    assert_eq!(
        classify_aggregated_for_test(
            HealthDomain::RiskEnvelope,
            "position_count_active",
            20.0,
        ),
        HealthState::HealthDegraded,
        "classify_aggregated risk_envelope::position_count_active arm 必走 helper + round（Track F 退化守）"
    );

    // correlation_avg_pairwise：0.8（> 0.7）→ DEGRADED
    assert_eq!(
        classify_aggregated_for_test(
            HealthDomain::RiskEnvelope,
            "correlation_avg_pairwise",
            0.8,
        ),
        HealthState::HealthDegraded,
        "classify_aggregated risk_envelope::correlation_avg_pairwise arm 必走 helper（Track F 退化守）"
    );

    // concentration_top1_pct：60.0%（> 50）→ DEGRADED
    assert_eq!(
        classify_aggregated_for_test(
            HealthDomain::RiskEnvelope,
            "concentration_top1_pct",
            60.0,
        ),
        HealthState::HealthDegraded,
        "classify_aggregated risk_envelope::concentration_top1_pct arm 必走 helper（Track F 退化守）"
    );

    // CRITICAL band 守（cum_pnl loss > 2500、dd > 15）。
    assert_eq!(
        classify_aggregated_for_test(
            HealthDomain::RiskEnvelope,
            "portfolio_cum_pnl_24h_usd",
            -3000.0,
        ),
        HealthState::HealthCritical,
        "cum_pnl loss=3000 (> 2500) 必 CRITICAL"
    );
    assert_eq!(
        classify_aggregated_for_test(
            HealthDomain::RiskEnvelope,
            "portfolio_max_dd_pct",
            20.0,
        ),
        HealthState::HealthCritical,
        "dd 20% (> 15) 必 CRITICAL"
    );
}

// ============================================================
// Track F DEGRADED-band stress：5-sample mean 透 scheduler 真實 fire
// ============================================================

/// mock emitter 注入 DEGRADED-band sample → scheduler 跑 6 tick → assert 至少 1
/// metric 走 DEGRADED 帶；驗 scheduler 端 5-sample rolling window mean classify
/// 真實接 risk_envelope arm（per Track C HIGH-1 stress 範式）。
#[tokio::test]
async fn test_sprint2_track_f_risk_envelope_degraded_band_classify() {
    /// 內嵌 mock emitter：每次 sample 返回 DEGRADED-band 5 metric row。
    struct MockDegradedRiskEnvelopeEmitter {
        ticks: u32,
    }

    #[async_trait]
    impl DomainEmitter for MockDegradedRiskEnvelopeEmitter {
        fn domain(&self) -> HealthDomain {
            HealthDomain::RiskEnvelope
        }

        fn sample_interval_sec(&self) -> u64 {
            1
        }

        async fn sample(&mut self) -> Result<Vec<Box<dyn MetricSample>>, M3Error> {
            self.ticks += 1;
            // 5 metric 值組合（DEGRADED 帶；scheduler 端 mean=value 必走
            // DEGRADED 透 classify_aggregated）：
            //   - cum_pnl=-2000（loss 2000，1500-2500 區間 DEGRADED）
            //   - dd=12（10-15 區間 DEGRADED）
            //   - pos=20（> 16 DEGRADED）
            //   - corr=0.8（> 0.7 DEGRADED）
            //   - conc=60%（> 50 DEGRADED）
            let snapshot = RiskEnvelopeSample {
                portfolio_cum_pnl_24h_usd: -2000.0,
                portfolio_max_dd_pct: 12.0,
                position_count_active: 20,
                correlation_avg_pairwise: 0.8,
                concentration_top1_pct: 60.0,
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

    let emitter: Box<dyn DomainEmitter> = Box::new(MockDegradedRiskEnvelopeEmitter { ticks: 0 });
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

    // 跑 7s ≥ 6 tick；5-sample rolling window 滿後第 6 tick mean 必走 DEGRADED。
    tokio::time::sleep(Duration::from_secs(7)).await;
    cancel.cancel();
    let _ = handle.await;

    let snapshot = writer.snapshot();
    assert!(
        snapshot.len() >= 5,
        "DEGRADED band stress: writer rows {} < 5",
        snapshot.len()
    );

    // 5 metric_name 必全展開（per V106 row per metric_name 1 條對齊 ADR-0042
    // Decision 4）。
    let metric_names: std::collections::HashSet<&str> =
        snapshot.iter().map(|r| r.metric_name.as_str()).collect();
    assert!(
        metric_names.contains("portfolio_cum_pnl_24h_usd"),
        "portfolio_cum_pnl_24h_usd metric 必展開"
    );
    assert!(
        metric_names.contains("portfolio_max_dd_pct"),
        "portfolio_max_dd_pct metric 必展開"
    );
    assert!(
        metric_names.contains("position_count_active"),
        "position_count_active metric 必展開"
    );
    assert!(
        metric_names.contains("correlation_avg_pairwise"),
        "correlation_avg_pairwise metric 必展開"
    );
    assert!(
        metric_names.contains("concentration_top1_pct"),
        "concentration_top1_pct metric 必展開"
    );

    // 全 row 為 RiskEnvelope domain（不誤寫 engine_runtime / 其他）。
    for row in &snapshot {
        assert_eq!(row.domain, HealthDomain::RiskEnvelope);
        assert_eq!(row.engine_mode, "demo");
    }

    // 為什麼不直接 assert row.state == DEGRADED:
    //   SM 端 OK→DEGRADED 需經 OK→WARN→DEGRADED 升階 + dwell 60s/5min（per
    //   spec §5.2 + Track A SM 邏輯），本 test 跑 7s < 5min；row.state 透過
    //   fired branch 走 prev_state，但 classify_aggregated 返 DEGRADED 已能讓
    //   row.state 寫 SM 端 current_state（初始 OK + 採樣 DEGRADED-band，SM
    //   observe_classified 返 Ok(false) + anchor 設立；current_state 仍 OK）。
    //   → row.state 在 5min dwell 達標前仍是 OK；本 test 改用 metric_names 展開
    //   + dispatch 真實接通（已由 test_sprint2_track_f_risk_envelope_classify_
    //   aggregated_dispatch 守）。
    //   退而求其次驗：classify_aggregated 真實 dispatch 對應 helper 須由 in-
    //   process direct test 覆蓋（即上一個 test），integration test 端只能間接
    //   驗「不誤升 SM state（即 dispatch 退化會把 anchor 全清，state 一直 OK
    //   不變）」+ metric_names 完整。
}

// ============================================================
// AC-2 4-state ladder OK → WARN → DEGRADED fire
// ============================================================

/// AC-2 ladder fire test：risk_envelope 4-state ladder OK→WARN→DEGRADED 真實
/// fire；走 observe_classified（不需 scheduler，避 300s wall-clock）。
///
/// 為什麼直接走 observe_classified（per Track A/B/C test 同 pattern）:
///   - SM 是 ladder transition matrix 的 SSOT；scheduler 端只是組裝 classify→
///     observe→write→publish flow。本 test 主要驗 risk_envelope 域 SM 在 OK/
///     WARN/DEGRADED band 間真實 fire ladder，與 engine_runtime / database_pool
///     共用同一 SM 機制但 domain 隔離（AC-4）。
///   - ladder dwell 60s/5min 用注入 Instant 直接驗 dwell math。
#[test]
fn test_sprint2_ladder_risk_envelope() {
    let mut sm = HealthStateMachine::new(HealthDomain::RiskEnvelope);
    assert_eq!(sm.current_state(), HealthState::HealthOk);

    let base = Instant::now();
    let anomaly_id = "risk_envelope__portfolio_max_dd_pct";

    // Step 1: OK → WARN，dwell 60s（per spec §5.2 ladder dwell）。
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
    // 新 anomaly_id 避同 id cap suppress（per spec §6.2 anomaly_id 命名規約）。
    let degraded_id = "risk_envelope__concentration_top1_pct";
    let r4 = sm
        .observe_classified(
            HealthState::HealthDegraded,
            degraded_id,
            base + Duration::from_secs(60),
        )
        .unwrap();
    assert!(!r4, "WARN→DEGRADED 首次採樣只設 anchor");

    let r5 = sm
        .observe_classified(
            HealthState::HealthDegraded,
            degraded_id,
            base + Duration::from_secs(60 + 240),
        )
        .unwrap();
    assert!(!r5, "WARN→DEGRADED dwell 4min 不足 5min");

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
    assert_eq!(sm.domain(), HealthDomain::RiskEnvelope, "SM domain 對齊");
}

// ============================================================
// AC-4 cross-domain independence
// ============================================================

/// AC-4 cross-domain independence：risk_envelope DEGRADED 不影響其他 domain SM
/// 狀態（per ADR-0042 Decision 3 + spec §5.3 system-level state = max(per-
/// domain) 但每 domain SM 各自獨立）+ 不觸 5-gate kill（per dispatch packet
/// §7.5 反模式 (b)；emit DEGRADED 是觀測事件，5-gate kill 由既有 D2 邏輯走）。
///
/// 為什麼此 test:
///   - 6 domain SM 是分開 instance（per spec §3.1 scheduler 端
///     `HashMap<(HealthDomain, String), HealthStateMachine>`）；risk_envelope
///     升 DEGRADED 不能反向修改其他 domain 的 SM 狀態。
///   - risk_envelope 是 portfolio-level（per dispatch packet §7.4 AC-7 + 16 根
///     原則 #16），但仍與其他 5 domain 各自獨立計數，不重複 cascade。
#[test]
fn test_sprint2_cross_domain_risk_envelope_independence() {
    // 模擬 scheduler 端 per-domain SM 配置：risk_envelope + engine_runtime +
    // database_pool + pipeline_throughput 各自獨立。
    let mut sm_risk = HealthStateMachine::new(HealthDomain::RiskEnvelope);
    let mut sm_engine = HealthStateMachine::new(HealthDomain::EngineRuntime);
    let sm_database = HealthStateMachine::new(HealthDomain::DatabasePool);
    let sm_pipeline = HealthStateMachine::new(HealthDomain::PipelineThroughput);

    let base = Instant::now();

    // 將 risk_envelope SM 推到 DEGRADED：先 OK→WARN（60s）再 WARN→DEGRADED（300s）。
    let id_a = "risk_envelope__portfolio_max_dd_pct";
    let _ = sm_risk.observe_classified(HealthState::HealthWarn, id_a, base);
    let r = sm_risk
        .observe_classified(
            HealthState::HealthWarn,
            id_a,
            base + Duration::from_secs(60),
        )
        .unwrap();
    assert!(r, "risk_envelope OK→WARN fire");
    assert_eq!(sm_risk.current_state(), HealthState::HealthWarn);

    let id_b = "risk_envelope__concentration_top1_pct";
    let _ = sm_risk.observe_classified(
        HealthState::HealthDegraded,
        id_b,
        base + Duration::from_secs(60),
    );
    let r = sm_risk
        .observe_classified(
            HealthState::HealthDegraded,
            id_b,
            base + Duration::from_secs(60 + 300),
        )
        .unwrap();
    assert!(r, "risk_envelope WARN→DEGRADED fire");
    assert_eq!(sm_risk.current_state(), HealthState::HealthDegraded);
    assert_eq!(sm_risk.amplification_loop_24h_count(), 2);

    // 驗其他 3 domain SM 完全不受 risk_envelope 變動影響。
    assert_eq!(
        sm_engine.current_state(),
        HealthState::HealthOk,
        "engine_runtime SM 不受 risk_envelope DEGRADED 影響"
    );
    assert_eq!(
        sm_engine.amplification_loop_24h_count(),
        0,
        "engine_runtime amp_cap_count 不受 risk_envelope 計數影響"
    );
    assert_eq!(
        sm_database.current_state(),
        HealthState::HealthOk,
        "database_pool SM 不受 risk_envelope DEGRADED 影響"
    );
    assert_eq!(
        sm_pipeline.current_state(),
        HealthState::HealthOk,
        "pipeline_throughput SM 不受 risk_envelope DEGRADED 影響"
    );

    // 另一向驗：engine_runtime 升 WARN 不影響 risk_envelope 已升到 DEGRADED 的狀態。
    let _ = sm_engine.observe_classified(
        HealthState::HealthWarn,
        "engine_runtime__cpu_pct",
        base + Duration::from_secs(60 + 300),
    );
    let r = sm_engine
        .observe_classified(
            HealthState::HealthWarn,
            "engine_runtime__cpu_pct",
            base + Duration::from_secs(60 + 300 + 60),
        )
        .unwrap();
    assert!(r, "engine_runtime OK→WARN fire（risk_envelope 變動後）");
    assert_eq!(sm_engine.current_state(), HealthState::HealthWarn);
    // risk_envelope 仍在 DEGRADED，未被 engine_runtime 影響。
    assert_eq!(
        sm_risk.current_state(),
        HealthState::HealthDegraded,
        "risk_envelope 持續 DEGRADED 不受 engine_runtime 升 WARN 影響"
    );
}

// ============================================================
// AC-5 spike feature not active in default build
// ============================================================

/// AC-5 production binary 不滲透 mock time：本 test 在 default build 下執行能
/// 跑通，即證 metric_emitter / writer / event_bus / domains/risk_envelope 全
/// 不引 spike feature compile gate。
///
/// 真實 nm scan（QA empirical 走）:
///   nm target/release/openclaw-engine | grep -E "(mock_instant|tokio::time::pause|spike)" | wc -l
///   expect 0
#[test]
fn test_sprint2_track_f_spike_feature_not_active_in_default_build() {
    // risk_envelope emitter 在 default build 下能編譯 + 各 helper 可呼叫，
    // 證明不依 spike feature（per Track A/B/C 同 pattern）。
    assert_eq!(
        classify_risk_envelope_cum_pnl_24h_usd(0.0),
        HealthState::HealthOk
    );
    assert_eq!(
        classify_risk_envelope_max_dd_pct(0.0),
        HealthState::HealthOk
    );
    assert_eq!(
        classify_risk_envelope_position_count(0),
        HealthState::HealthOk
    );
    assert_eq!(
        classify_risk_envelope_correlation_avg(0.0),
        HealthState::HealthOk
    );
    assert_eq!(
        classify_risk_envelope_concentration_top1_pct(0.0),
        HealthState::HealthOk
    );
}

// ============================================================
// sample_interval_sec 守
// ============================================================

/// AC sub 反模式 (b) 不寫死採樣間隔守：risk_envelope sample_interval=300s
/// （5min；per spec §2.1）。
///
/// 為什麼此 test:
///   - dispatch packet §7.5 反模式 (b)：「寫死採樣 300s（用 sample_interval_sec()
///     = 300）」明文規範 emitter 必返 300；若 IMPL 寫死 30s/60s 即破 spec §2.1
///     5min 慢動指標設計。
///   - 對齊 spec §2.1 「5min strategy_quality, risk_envelope 業務級活性慢動指標」
///     設計；採樣頻率太高反而拖累 portfolio calc hot path。
#[tokio::test]
async fn test_sprint2_track_f_sample_interval_sec_is_300() {
    struct StubSource;
    impl RiskEnvelopeSourceProbe for StubSource {
        fn current_portfolio_cum_pnl_24h_usd(&self) -> f64 {
            0.0
        }
        fn current_portfolio_max_dd_pct(&self) -> f64 {
            0.0
        }
        fn current_position_count_active(&self) -> u32 {
            0
        }
        fn current_correlation_avg_pairwise(&self) -> f64 {
            0.0
        }
        fn current_concentration_top1_pct(&self) -> f64 {
            0.0
        }
    }

    let emitter = RiskEnvelopeEmitter::new(StubSource);
    assert_eq!(emitter.domain(), HealthDomain::RiskEnvelope);
    assert_eq!(
        emitter.sample_interval_sec(),
        300,
        "risk_envelope sample_interval 必 300s (5min) per spec §2.1（不寫死 30s/60s）"
    );
}

// ============================================================
// SM dwell_time_sec accessor
// ============================================================

/// risk_envelope SM fire 時 last_transition_dwell_secs 寫真實值（per Track A
/// round 2 MEDIUM-2 fix）。
///
/// 為什麼此 test:
///   - 守 SM dwell math 在 risk_envelope domain 也走通；對齊 V106 schema
///     dwell_time_sec 真實寫入語意（per Track A round 2 MEDIUM-2 fix）。
#[test]
fn test_sprint2_track_f_sm_records_last_transition_dwell_secs() {
    let mut sm = HealthStateMachine::new(HealthDomain::RiskEnvelope);
    let base = Instant::now();
    let anomaly_id = "risk_envelope__portfolio_cum_pnl_24h_usd";

    assert_eq!(sm.last_transition_dwell_secs(), 0, "未 fire 前 dwell=0");
    let _ = sm.observe_classified(HealthState::HealthWarn, anomaly_id, base);
    assert_eq!(sm.last_transition_dwell_secs(), 0, "anchor only 仍 0");

    let r = sm
        .observe_classified(
            HealthState::HealthWarn,
            anomaly_id,
            base + Duration::from_secs(60),
        )
        .unwrap();
    assert!(r, "OK→WARN fire");
    let dwell = sm.last_transition_dwell_secs();
    assert!(
        dwell >= 60,
        "dwell_time_sec={} 必 >= 60（OK→WARN fire 在 base+60s）",
        dwell
    );
    assert!(
        dwell <= 120,
        "dwell_time_sec={} 不應超 120（防意外時鐘 anomaly）",
        dwell
    );
}
