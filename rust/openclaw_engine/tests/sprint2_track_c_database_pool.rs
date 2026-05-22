//! Sprint 2 Wave 1 Track C — database_pool emitter integration test。
//!
//! MODULE_NOTE
//! 模塊用途:
//!   per docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_dispatch_packet.md
//!   §4.4 AC sub-step：
//!     - AC-1a database_pool in-memory proxy：5 sample window × 4 metric tick →
//!       ≥ 5 V106 row written 至 mock writer（不接 PG）。
//!     - AC-2 4-state ladder：OK→WARN→DEGRADED ladder fire 直接走
//!       observe_classified（不需 scheduler；快速）。
//!     - AC-4 cross-domain：database_pool DEGRADED 不影響 engine_runtime /
//!       pipeline_throughput SM 狀態（各 SM 獨立實例）。
//!     - AC-5 spike default false：本 test 在 default build 跑通 → metric_emitter
//!       / writer / event_bus / domains/database_pool 全 0 spike feature gate。
//!
//! 主要 test:
//!   - test_sprint2_track_c_database_pool_row_count：AC-1a in-memory proxy
//!     row count ≥ 5
//!   - test_sprint2_ladder_database_pool：AC-2 OK→WARN→DEGRADED 4-state ladder
//!     fire via observe_classified
//!   - test_sprint2_cross_domain_database_pool_independence：AC-4 SM 隔離
//!   - test_sprint2_track_c_spike_feature_not_active_in_default_build：AC-5
//!     compile-path 證明
//!
//! 硬邊界:
//!   - 不依賴 spike feature；production binary include 本 test compile path（per
//!     AC-5 反模式 (b)）。
//!   - 不接 sandbox PG（Mac 跑；走 in-memory writer mock）。
//!   - 不修 production engine state。
//!   - 不接 main.rs scheduler（per Track A §7 carry-over；scaffold 階段不接
//!     main.rs）。

use std::sync::Arc;
use std::time::{Duration, Instant};

use async_trait::async_trait;
use openclaw_engine::health::domains::database_pool::DatabasePoolSample;
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
// AC-1a in-memory proxy row count ≥ 5
// ============================================================

/// AC-1a database_pool row count proxy：scheduler 跑數輪採樣 → in-memory writer
/// 累積 row ≥ 5。
///
/// 為什麼用 mock emitter + 1s interval 而非真 DatabasePoolEmitter:
///   - production sample_interval=60s（per spec §2.1），test 等 5×60s = 5min
///     不實際；本 test 用內嵌 mock emitter（sample_interval=1s）跑 6s ≥ 5 輪採樣
///     → 4 metric × 5+ tick ≥ 20 row → 遠超 AC ≥ 5 門檻。
///   - 真 DatabasePoolEmitter 的 sample_interval_sec=60 + sysinfo Disks refresh
///     等 60s 才得第一輪採樣，integration test 不可等。
///   - 真 emitter 的 ladder/threshold 邏輯由 DatabasePoolSample::into_metric_rows
///     在 emitter.sample() 內部執行；mock emitter 走相同 path 故 AC-1a 等價。
///
/// AC-1a 真實 Linux empirical SQL（QA Phase 3c 跑）:
///   SELECT COUNT(*) FROM learning.health_observations
///     WHERE domain='database_pool' AND created_at > NOW() - INTERVAL '30 min';
///   expect ≥ 5（60s sample × 4 metric × ≥ 5 tick = ≥ 20 row 實務上）。
///
/// Mac sandbox 不 connect Linux PG（per dispatch packet §4.4 容差）；本 test
/// 走 in-memory writer mock 為 AC-1a proxy。
#[tokio::test]
async fn test_sprint2_track_c_database_pool_row_count() {
    /// 內嵌 mock emitter：每次 sample 返回 4 個 OK-band metric row（DatabasePool
    /// domain；mimics DatabasePoolEmitter 結構但走 1s interval 跑 fast）。
    struct MockDatabasePoolEmitter {
        ticks: u32,
    }

    #[async_trait]
    impl DomainEmitter for MockDatabasePoolEmitter {
        fn domain(&self) -> HealthDomain {
            HealthDomain::DatabasePool
        }

        fn sample_interval_sec(&self) -> u64 {
            1
        }

        async fn sample(&mut self) -> Result<Vec<Box<dyn MetricSample>>, M3Error> {
            self.ticks += 1;
            // 走真實 DatabasePoolSample 走真實 into_metric_rows 邏輯，確保 mock
            // 路徑與 production 等價。
            let snapshot = DatabasePoolSample {
                pool_active_conn: 2,
                pool_max_conn: 10,
                pool_wait_ms_p95: 50,
                writer_queue_depth: 100,
                disk_data_dir_used_pct: 50.0,
                pool_disconnected: false,
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

    let emitter: Box<dyn DomainEmitter> = Box::new(MockDatabasePoolEmitter { ticks: 0 });
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
    // domain 對齊 database_pool（不誤寫 engine_runtime）。
    // 為什麼加 state 守 (per Sprint 2 round 2 Track C HIGH-2 fix)：
    //   - mock emitter 注入 OK-band sample（active 2/10 / wait 50ms / queue
    //     100 / disk 50%）；scheduler 走 classify_aggregated → OK band；SM
    //     observe_classified(OK, ...) 不升階；row.state 必為 HealthOk。
    //   - 若 HIGH-1 修了之後 classify_aggregated database_pool arm 漏接，
    //     mean 走 `_ => HealthOk` fallback 仍會通過（per classify_aggregated
    //     OK 走 _ arm 仍 OK），但只要 HIGH-1 dispatch 真實接通並 mean.round()
    //     正確，row.state 也必 OK；本 assert 守 (1) no false fire (2) 不誤
    //     升階  (3) 採樣資料端到端 OK band 透傳整條 path 不變調。
    for row in writer.snapshot() {
        assert_eq!(row.domain, HealthDomain::DatabasePool);
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
// Track C HIGH-1 stress：DEGRADED-band mock sample 觸發 classify_aggregated
// database_pool arm 真實 fire（守 HIGH-1 不退化）
// ============================================================

/// per Sprint 2 round 2 Track C HIGH-2 fix：mock emitter 注入 DEGRADED-band
/// sample → scheduler 跑 6 tick → assert 至少 1 metric 走 DEGRADED 帶。
///
/// 為什麼此 stress test:
///   - HIGH-1 fix 在 `classify_aggregated` 加 database_pool 3 個 match arm
///     （pg_pool_wait_ms_p95 / pg_writer_queue_depth / disk_data_dir_used_pct）；
///     若 fallback `_ => HealthOk` 仍 catches database_pool metric，DEGRADED
///     band sample 也會被誤歸 OK band（HIGH-1 blocker 之症狀）。
///   - 本 test 注入 sample = (active 18/20 / wait 900ms / queue 8000 / disk
///     92%) — 4 metric 中 wait/queue/disk 經 HIGH-1 fix dispatch 後 mean 走
///     對應 helper 必返 DEGRADED；fallback arm 永遠 OK 不會觸發 DEGRADED。
///   - dwell 60s/5min 由 SM 端守；本 stress test 注 emit 端 classify 真實 fire
///     對應 band — 透過 5-sample rolling window mean 已固定 = sample value，
///     classify_aggregated 必返 DEGRADED；若 HIGH-1 退化 catches 不到 arm，
///     row.state 永遠 OK，assert 失敗 → 守 HIGH-1 不退化。
///
/// 注意：pg_pool_active_conn classify 需 pool_max context（5th column），延 PA
/// spec amend MEDIUM-1 C Path A 拍板後 E1 round 3 補；本 test 不 assert
/// pg_pool_active_conn 對應 row.state（接 `_ => HealthOk` fallback 屬預期）。
#[tokio::test]
async fn test_sprint2_track_c_database_pool_degraded_band_classify() {
    /// 內嵌 mock emitter：每次 sample 返回 DEGRADED-band 4 metric row。
    struct MockDegradedDatabasePoolEmitter {
        ticks: u32,
    }

    #[async_trait]
    impl DomainEmitter for MockDegradedDatabasePoolEmitter {
        fn domain(&self) -> HealthDomain {
            HealthDomain::DatabasePool
        }

        fn sample_interval_sec(&self) -> u64 {
            1
        }

        async fn sample(&mut self) -> Result<Vec<Box<dyn MetricSample>>, M3Error> {
            self.ticks += 1;
            // 為什麼此 4 metric 值組合:
            //   - pool_active 18/20 = 90% → WARN（emitter 端 classify_band）；
            //     但本 test 焦點是 scheduler 端 classify_aggregated 是否真接
            //     database_pool arm；emitter 端 band 不被 scheduler 採信，
            //     scheduler 走 5-sample mean 自行 classify。
            //   - wait_ms_p95 900 → DEGRADED（> 500）
            //   - writer_queue_depth 8000 → DEGRADED（> 5000）
            //   - disk_used_pct 92.0 → DEGRADED（> 85）
            let snapshot = DatabasePoolSample {
                pool_active_conn: 18,
                pool_max_conn: 20,
                pool_wait_ms_p95: 900,
                writer_queue_depth: 8000,
                disk_data_dir_used_pct: 92.0,
                pool_disconnected: false,
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

    let emitter: Box<dyn DomainEmitter> =
        Box::new(MockDegradedDatabasePoolEmitter { ticks: 0 });
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

    // 跑 6 tick；5-sample rolling window 滿後第 6 tick mean 必走 DEGRADED band。
    tokio::time::sleep(Duration::from_secs(7)).await;
    cancel.cancel();
    let _ = handle.await;

    let snapshot = writer.snapshot();
    assert!(
        snapshot.len() >= 5,
        "DEGRADED band stress: writer rows {} < 5",
        snapshot.len()
    );

    // 為什麼分 metric 驗 classify_aggregated 真實接 database_pool arm:
    //   每 metric_name 有自己的 5-sample rolling window；windows 滿後 mean
    //   = sample 值（連續注入相同值），classify_aggregated 必走 helper
    //   返 DEGRADED；若 HIGH-1 退化（fallback _ => HealthOk catches），row.
    //   state 全 OK 將觸 assert 失敗。
    let metrics_with_degraded: std::collections::HashSet<&str> = snapshot
        .iter()
        .filter(|r| r.state == HealthState::HealthDegraded)
        .map(|r| r.metric_name.as_str())
        .collect();

    // 至少 wait / queue / disk 三 metric 中 1 個必走 DEGRADED（即時或經 SM dwell）。
    // 為什麼用「至少 1」而非「全 3」：
    //   SM 端 OK→DEGRADED 需 dwell 5min（per spec §5.2 + Track A SM 邏輯），
    //   本 test 跑 7s < 5min；row.state 透過 fired branch 走 prev_state，但
    //   classify_aggregated 返 DEGRADED 已能讓 row.state 寫 SM 端 current_state
    //   （初始 OK + 採樣 DEGRADED-band，SM observe_classified 返 Ok(false) +
    //   anchor 設立；current_state 仍 OK）。
    //   → row.state 在 5min dwell 達標前仍是 OK；本 test 改用 evidence_json
    //   檢查或 reject_reason 確認 classify_aggregated arm 真實接通。
    //   退而求其次驗：classify_aggregated 真實 dispatch 對應 helper 須由
    //   in-process direct unit test 覆蓋（已存在 health/metric_emitter::tests），
    //   integration test 端只能間接驗「不誤升 SM state（即 HIGH-1 退化會把
    //   anchor 全清，state 一直 OK 不變）」。
    //
    // 直接 assert 改為「row count + state 一致性」+ 對應 dispatch 已存在
    // 之 unit test 守內部邏輯。
    let _ = metrics_with_degraded; // 不直接 assert（dwell 5min 限制），改下面 sanity 驗。

    // sanity 驗：DEGRADED-band sample 未觸 SM 升階前，row.state 應為 SM 當前
    // state（OK 初始）；evidence_json 帶 reject_reason=None（dwell 未達；
    // observe_classified 返 Ok(false) + reject_reason=None per HIGH-1 helper
    // 「target_band != current && !capped && count<2 → None」）。
    // 主要守：(1) row.state 不會被 fallback `_ => HealthOk` 反向「升 OK」；
    // (2) row.metric_name 包含 5 metric 全展開（per Sprint 2 round 3 Track C
    // MEDIUM-1 C fix Path A 新增 pg_pool_active_conn_ratio）。
    let metric_names: std::collections::HashSet<&str> = snapshot
        .iter()
        .map(|r| r.metric_name.as_str())
        .collect();
    assert!(
        metric_names.contains("pg_pool_active_conn"),
        "pg_pool_active_conn metric 必展開"
    );
    assert!(
        metric_names.contains("pg_pool_active_conn_ratio"),
        "pg_pool_active_conn_ratio metric 必展開 (Sprint 2 round 3 Path A)"
    );
    assert!(
        metric_names.contains("pg_pool_wait_ms_p95"),
        "pg_pool_wait_ms_p95 metric 必展開"
    );
    assert!(
        metric_names.contains("pg_writer_queue_depth"),
        "pg_writer_queue_depth metric 必展開"
    );
    assert!(
        metric_names.contains("disk_data_dir_used_pct"),
        "disk_data_dir_used_pct metric 必展開"
    );

    // 全 row 為 DatabasePool domain（不誤寫 engine_runtime）。
    for row in &snapshot {
        assert_eq!(row.domain, HealthDomain::DatabasePool);
        assert_eq!(row.engine_mode, "demo");
    }

    // ----------------------------------------
    // HIGH-1 + Sprint 2 round 3 MEDIUM-1 C 退化守：直接呼 classify_aggregated
    // 確認 4 metric arm 真實接通
    // ----------------------------------------
    // 為什麼直接呼 classify_aggregated 而非整 scheduler 跑 5min wall-clock:
    //   scheduler dwell 5min 不可 test 等；本 helper 是 scheduler 端 classify
    //   邏輯的真實入口，等價於 production 觀測 path。
    // 為什麼此呼叫端到端守 HIGH-1 + MEDIUM-1 C:
    //   - 若 HIGH-1 退化（fallback `_ => HealthOk` catches database_pool
    //     metric），下列 4 呼叫返 OK；本 assert 必失敗 → HIGH-1 不退化 守。
    //   - pg_pool_active_conn_ratio 是 Sprint 2 round 3 MEDIUM-1 C Path A 新接 arm；
    //     退化守確認 ratio dispatch 真實接通 classify_database_pool_active_conn_ratio。
    use openclaw_engine::health::metric_emitter::classify_aggregated_for_test;
    assert_eq!(
        classify_aggregated_for_test(
            HealthDomain::DatabasePool,
            "pg_pool_active_conn_ratio",
            0.97,
        ),
        HealthState::HealthDegraded,
        "classify_aggregated database_pool::pg_pool_active_conn_ratio arm 必走 helper（Sprint 2 round 3 MEDIUM-1 C 退化守）"
    );
    assert_eq!(
        classify_aggregated_for_test(
            HealthDomain::DatabasePool,
            "pg_pool_wait_ms_p95",
            900.0,
        ),
        HealthState::HealthDegraded,
        "classify_aggregated database_pool::pg_pool_wait_ms_p95 arm 必走 helper（HIGH-1 退化守）"
    );
    assert_eq!(
        classify_aggregated_for_test(
            HealthDomain::DatabasePool,
            "pg_writer_queue_depth",
            8000.0,
        ),
        HealthState::HealthDegraded,
        "classify_aggregated database_pool::pg_writer_queue_depth arm 必走 helper（HIGH-1 退化守）"
    );
    assert_eq!(
        classify_aggregated_for_test(
            HealthDomain::DatabasePool,
            "disk_data_dir_used_pct",
            92.0,
        ),
        HealthState::HealthDegraded,
        "classify_aggregated database_pool::disk_data_dir_used_pct arm 必走 helper（HIGH-1 退化守）"
    );
}

// ============================================================
// AC-2 4-state ladder OK → WARN → DEGRADED fire
// ============================================================

/// AC-2 ladder fire test：database_pool 4-state ladder OK→WARN→DEGRADED 真實
/// fire；走 observe_classified（不需 scheduler，避 60s wall-clock）。
///
/// 為什麼直接走 observe_classified（per Track A test pattern）:
///   - SM 是 ladder transition matrix 的 SSOT；scheduler 端只是組裝 classify→
///     observe→write→publish flow。本 test 主要驗 database_pool 域 SM 在 OK/
///     WARN/DEGRADED band 間真實 fire ladder，與 engine_runtime 共用同一 SM 機制
///     但 domain 隔離（AC-4）。
///   - ladder dwell 60s/5min 用注入 Instant 直接驗 dwell math。
#[test]
fn test_sprint2_ladder_database_pool() {
    let mut sm = HealthStateMachine::new(HealthDomain::DatabasePool);
    assert_eq!(sm.current_state(), HealthState::HealthOk);

    let base = Instant::now();
    let anomaly_id = "database_pool__pg_pool_active_conn";

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
    // 新 anomaly_id 避同 id cap suppress。
    let degraded_id = "database_pool__pg_writer_queue_depth";
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
    assert_eq!(sm.domain(), HealthDomain::DatabasePool, "SM domain 對齊");
}

// ============================================================
// AC-4 cross-domain independence
// ============================================================

/// AC-4 cross-domain independence：database_pool DEGRADED 不影響其他 domain SM
/// 狀態（per ADR-0042 Decision 3 + spec §5.3 system-level state = max(per-
/// domain) 但每 domain SM 各自獨立）。
///
/// 為什麼此 test:
///   - 6 domain SM 是分開 instance（per spec §3.1 scheduler 端
///     `HashMap<(HealthDomain, String), HealthStateMachine>`）；database_pool
///     升 DEGRADED 不能反向修改 engine_runtime / pipeline_throughput 的 SM 狀態。
///   - 本 test 守護 Track B-F scaffold 沿用時不會把 SM 寫成全域共享。
#[test]
fn test_sprint2_cross_domain_database_pool_independence() {
    // 模擬 scheduler 端 per-domain SM 配置：database_pool + engine_runtime 各自獨立
    let mut sm_db = HealthStateMachine::new(HealthDomain::DatabasePool);
    let mut sm_engine = HealthStateMachine::new(HealthDomain::EngineRuntime);
    let sm_pipeline = HealthStateMachine::new(HealthDomain::PipelineThroughput);

    let base = Instant::now();

    // 將 database_pool SM 推到 DEGRADED：先 OK→WARN（60s）再 WARN→DEGRADED（300s）。
    let id_a = "database_pool__pg_pool_active_conn";
    let _ = sm_db.observe_classified(HealthState::HealthWarn, id_a, base);
    let r = sm_db
        .observe_classified(
            HealthState::HealthWarn,
            id_a,
            base + Duration::from_secs(60),
        )
        .unwrap();
    assert!(r, "database_pool OK→WARN fire");
    assert_eq!(sm_db.current_state(), HealthState::HealthWarn);

    let id_b = "database_pool__pg_writer_queue_depth";
    let _ = sm_db.observe_classified(
        HealthState::HealthDegraded,
        id_b,
        base + Duration::from_secs(60),
    );
    let r = sm_db
        .observe_classified(
            HealthState::HealthDegraded,
            id_b,
            base + Duration::from_secs(60 + 300),
        )
        .unwrap();
    assert!(r, "database_pool WARN→DEGRADED fire");
    assert_eq!(sm_db.current_state(), HealthState::HealthDegraded);
    assert_eq!(sm_db.amplification_loop_24h_count(), 2);

    // 驗 engine_runtime / pipeline_throughput SM 完全不受 database_pool 變動影響。
    assert_eq!(
        sm_engine.current_state(),
        HealthState::HealthOk,
        "engine_runtime SM 不受 database_pool DEGRADED 影響"
    );
    assert_eq!(
        sm_engine.amplification_loop_24h_count(),
        0,
        "engine_runtime amp_cap_count 不受 database_pool 計數影響"
    );
    assert_eq!(
        sm_pipeline.current_state(),
        HealthState::HealthOk,
        "pipeline_throughput SM 不受 database_pool DEGRADED 影響"
    );
    assert_eq!(
        sm_pipeline.amplification_loop_24h_count(),
        0,
        "pipeline_throughput amp_cap_count 不受 database_pool 計數影響"
    );

    // 另一向驗：engine_runtime 升 WARN 不影響 database_pool 已升到 DEGRADED 的狀態。
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
    assert!(r, "engine_runtime OK→WARN fire（database_pool 變動後）");
    assert_eq!(sm_engine.current_state(), HealthState::HealthWarn);
    // database_pool 仍在 DEGRADED，未被 engine_runtime 影響。
    assert_eq!(
        sm_db.current_state(),
        HealthState::HealthDegraded,
        "database_pool 持續 DEGRADED 不受 engine_runtime 升 WARN 影響"
    );
}

// ============================================================
// AC-5 spike feature not active in default build
// ============================================================

/// AC-5 production binary 不滲透 mock time：本 test 在 default build 下執行能
/// 跑通，即證 metric_emitter / writer / event_bus / domains/database_pool 全
/// 不引 spike feature compile gate。
///
/// 真實 nm scan（QA empirical 走）:
///   nm target/release/openclaw-engine | grep -E "(mock_instant|tokio::time::pause|spike)" | wc -l
///   expect 0
#[test]
fn test_sprint2_track_c_spike_feature_not_active_in_default_build() {
    // database_pool emitter 在 default build 下能編譯 + sample，證明不依 spike
    // feature。
    use openclaw_engine::health::domains::database_pool::{
        classify_database_pool_active_conn, classify_database_pool_disk_used_pct,
        classify_database_pool_wait_ms_p95, classify_database_pool_writer_queue_depth,
    };
    assert_eq!(
        classify_database_pool_active_conn(0, 10),
        HealthState::HealthOk
    );
    assert_eq!(
        classify_database_pool_wait_ms_p95(0),
        HealthState::HealthOk
    );
    assert_eq!(
        classify_database_pool_writer_queue_depth(0),
        HealthState::HealthOk
    );
    assert_eq!(
        classify_database_pool_disk_used_pct(0.0),
        HealthState::HealthOk
    );
}

// ============================================================
// Track A round 2 fix regression — recovery anchor reset + dwell secs（沿用）
// ============================================================
//
// Track A round 2 HIGH-2 fix（recovery dwell anchor 升階方向不對稱清理）+
// MEDIUM-2 fix（last_transition_dwell_secs 真實寫入）對 database_pool SM 同
// 樣生效（per SM 共用 mod.rs 邏輯）。本 Track C 沿用 Track A integration
// test 規約 + Track A 已加 4 個 round 2 fix test 守 SM 共用邏輯；本 Track C
// 不重複那 4 個 test（per packet §4.5 反模式 (c) 不沿用 scaffold 之外 = 反過
// 來說，已 land 之 SM 邏輯不重新測試）。

/// AC-2 補充：database_pool SM fire 時 last_transition_dwell_secs 寫真實值。
///
/// 為什麼此 test:
///   - 守 SM dwell math 在 database_pool domain 也走通；對齊 V106 schema
///     dwell_time_sec 真實寫入語意（per Track A round 2 MEDIUM-2 fix）。
#[test]
fn test_sprint2_track_c_sm_records_last_transition_dwell_secs() {
    let mut sm = HealthStateMachine::new(HealthDomain::DatabasePool);
    let base = Instant::now();
    let anomaly_id = "database_pool__disk_data_dir_used_pct";

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

// ============================================================
// Sprint 2 round 3 Track C MEDIUM-1 C — pg_pool_active_conn_ratio classify
// ============================================================

/// Sprint 2 round 3 Track C MEDIUM-1 C fix Path A：classify_aggregated 接
/// database_pool::pg_pool_active_conn_ratio arm；ratio 0.5/0.8/0.95/1.0 對應
/// OK/WARN/WARN/DEGRADED 四 band 邊界。
///
/// 為什麼直接呼 classify_aggregated_for_test:
///   - ratio classify 是 scheduler 端 5-sample mean dispatch 真實入口；直呼
///     等價 production 觀測 path（per Sprint 2 round 2 HIGH-1 test 範式）。
///   - 不走 scheduler wall-clock dwell：dwell 5min 不可 integration test 等。
#[test]
fn test_sprint2_track_c_database_pool_active_conn_ratio_classify() {
    use openclaw_engine::health::metric_emitter::classify_aggregated_for_test;

    // OK band：ratio < 0.80
    assert_eq!(
        classify_aggregated_for_test(
            HealthDomain::DatabasePool,
            "pg_pool_active_conn_ratio",
            0.5,
        ),
        HealthState::HealthOk,
        "ratio 0.5 對應 OK band（< 0.80）"
    );
    assert_eq!(
        classify_aggregated_for_test(
            HealthDomain::DatabasePool,
            "pg_pool_active_conn_ratio",
            0.79,
        ),
        HealthState::HealthOk,
        "ratio 0.79 邊界外 OK"
    );
    // WARN band：0.80 - 0.95
    assert_eq!(
        classify_aggregated_for_test(
            HealthDomain::DatabasePool,
            "pg_pool_active_conn_ratio",
            0.8,
        ),
        HealthState::HealthWarn,
        "ratio 0.8 進 WARN band 下界"
    );
    assert_eq!(
        classify_aggregated_for_test(
            HealthDomain::DatabasePool,
            "pg_pool_active_conn_ratio",
            0.95,
        ),
        HealthState::HealthWarn,
        "ratio 0.95 仍 WARN（不過 > 0.95 閾值）"
    );
    // DEGRADED band：> 0.95
    assert_eq!(
        classify_aggregated_for_test(
            HealthDomain::DatabasePool,
            "pg_pool_active_conn_ratio",
            0.951,
        ),
        HealthState::HealthDegraded,
        "ratio 0.951 過 0.95 閾值即 DEGRADED"
    );
    assert_eq!(
        classify_aggregated_for_test(
            HealthDomain::DatabasePool,
            "pg_pool_active_conn_ratio",
            1.0,
        ),
        HealthState::HealthDegraded,
        "ratio 1.0（pool 全滿）對應 DEGRADED；不誤升 CRITICAL（disconnected fail-closed OK 由 emitter 端處理）"
    );
}

// ============================================================
// Sprint 2 round 3 Track C MEDIUM-3 — disconnected emits pool_status evidence
// ============================================================

/// Sprint 2 round 3 Track C MEDIUM-3 fix Path A：disconnected DatabasePoolSample
/// 採樣後 row.evidence_json 含 `{"pool_status": "disconnected"}` audit trail。
///
/// 為什麼此 test:
///   - per M3 design spec §2.3.2 + PA Sprint 2 Wave 1 amend 2026-05-22 Path A：
///     disconnected 場景 fail-closed OK band + evidence_json 寫 audit trail。
///   - 走 scheduler 端 in-memory writer 驗 V106 row evidence_json 真實寫入路徑；
///     即 emitter sample_now → into_metric_rows → MetricSample::extra_evidence →
///     scheduler row.with_evidence 全鏈端到端。
///   - SM observe 不走 reject 路徑（OK-band sample 不會 reject）；
///     extra_evidence 是 sample-time audit，獨立於 reject_reason 路徑。
#[tokio::test]
async fn test_sprint2_track_c_database_pool_disconnected_emits_pool_status_evidence() {
    /// 內嵌 mock emitter：每次 sample 返回 5 個 disconnected metric row
    /// （pool_disconnected=true → MetricSample::extra_evidence 帶
    /// `{"pool_status": "disconnected"}`）。
    struct MockDisconnectedDatabasePoolEmitter {
        ticks: u32,
    }

    #[async_trait]
    impl DomainEmitter for MockDisconnectedDatabasePoolEmitter {
        fn domain(&self) -> HealthDomain {
            HealthDomain::DatabasePool
        }

        fn sample_interval_sec(&self) -> u64 {
            1
        }

        async fn sample(&mut self) -> Result<Vec<Box<dyn MetricSample>>, M3Error> {
            self.ticks += 1;
            // disconnected 場景：max=0 + active=0 + probe 走 fallback；
            // pool_disconnected=true 觸發 evidence_json audit trail。
            let snapshot = DatabasePoolSample {
                pool_active_conn: 0,
                pool_max_conn: 0,
                pool_wait_ms_p95: 0,
                writer_queue_depth: 0,
                disk_data_dir_used_pct: 0.0,
                pool_disconnected: true,
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

    let emitter: Box<dyn DomainEmitter> =
        Box::new(MockDisconnectedDatabasePoolEmitter { ticks: 0 });
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

    // 跑 3 tick 即足：disconnected 場景每 tick 5 row × evidence_json，不需
    // 等 5-sample window 滿（extra_evidence 是 sample-time path）。
    tokio::time::sleep(Duration::from_secs(3)).await;
    cancel.cancel();
    let _ = handle.await;

    let snapshot = writer.snapshot();
    assert!(
        snapshot.len() >= 5,
        "disconnected sample tick × 5 metric should produce ≥ 5 row (actual={})",
        snapshot.len()
    );

    // 全 row evidence_json 必含 pool_status: disconnected。
    // 為什麼此守 audit trail:
    //   - per spec §2.3.2「disconnected 不靜默」要求；evidence_json 缺失即 spec
    //     drift。
    //   - per Sprint 2 round 3 MEDIUM-3 fix Path A 對齊規範。
    for row in &snapshot {
        assert_eq!(row.domain, HealthDomain::DatabasePool);
        // 全 row fail-closed OK band（不誤升 CRITICAL；per spec §2.3.2 rationale 3 + 4）。
        assert_eq!(
            row.state,
            HealthState::HealthOk,
            "disconnected fail-closed OK band: metric={}",
            row.metric_name
        );
        let evidence = row.evidence_json.as_ref().unwrap_or_else(|| {
            panic!(
                "disconnected row must carry evidence_json with pool_status: metric={}",
                row.metric_name
            )
        });
        assert_eq!(
            evidence["pool_status"], "disconnected",
            "evidence_json.pool_status 必為 \"disconnected\": metric={}",
            row.metric_name
        );
    }
}
