//! Sprint 2 Wave 2 round 2 — OBSERVE-4 cross-Wave fix regression test。
//!
//! MODULE_NOTE
//! 模塊用途:
//!   per docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_design_spec.md
//!   §1.x OBSERVE-4 line 199-216 設計合約：M3 emitter 嚴禁在 replay subprocess
//!   內 emit health_observations row（V106 line 259 `engine_mode CHECK IN
//!   ('paper','demo','live_demo','live')` 不含 'replay'）。
//!
//!   本 test 守 cross-Wave invariant：
//!     - MetricEmitterScheduler::run（Track A scaffold，覆 Track B/C/D/F）
//!     - StrategyQualityScheduler::run（Track E 獨立 scheduler）
//!   兩者 engine_mode='replay' 啟動時必 RAISE `M3Error::ReplaySubprocessForbidden`
//!   而非靜默走到 PG CHECK fail 才暴露。
//!
//! 主要 test:
//!   - test_metric_emitter_scheduler_replay_engine_mode_forbidden：
//!     MetricEmitterScheduler::run with engine_mode='replay' → fail-loud Err
//!   - test_strategy_quality_scheduler_replay_engine_mode_forbidden：
//!     StrategyQualityScheduler::run with engine_mode='replay' → fail-loud Err
//!   - test_metric_emitter_scheduler_non_replay_engine_mode_ok_startup：
//!     paper/demo/live_demo/live 4 模式啟動 OK；guard 只攔 'replay'
//!
//! 硬邊界:
//!   - 不依賴 spike feature；production binary 0 mock time 滲透對齊。
//!   - 不接 sandbox PG（in-memory writer）。
//!   - 不修 production engine state / engine_mode global state。

use std::sync::Arc;

use async_trait::async_trait;
use openclaw_engine::health::domains::api_latency::{
    ApiLatencyEmitter, ApiLatencySourceProbe,
};
use openclaw_engine::health::domains::strategy_quality::{
    StrategyQualityEmitter, StrategyQualityScheduler, StrategyQualitySourceProbe,
};
use openclaw_engine::health::event_bus::HealthEventBus;
use openclaw_engine::health::metric_emitter::{
    DomainEmitter, EngineModeProvider, MetricEmitterScheduler,
};
use openclaw_engine::health::writer::InMemoryHealthObservationWriter;
use openclaw_engine::health::M3Error;
use tokio_util::sync::CancellationToken;

// ============================================================
// Stub source probes（min set for scheduler 構造；不走 sample 路徑）
// ============================================================

/// api_latency stub source probe；全返 0（OK band）。
///
/// 為什麼用 stub：scheduler.run 啟動前的 engine_mode guard 在 sample tick 前
/// 就 short-circuit Err；sample probe 不會被呼，但 Box<dyn DomainEmitter>
/// 構造需有真實 emitter。
struct ZeroApiSource;

impl ApiLatencySourceProbe for ZeroApiSource {
    fn current_rest_p50_ms_60s_window(&self) -> u32 {
        0
    }
    fn current_rest_p95_ms_60s_window(&self) -> u32 {
        0
    }
    fn current_rest_p99_ms_60s_window(&self) -> u32 {
        0
    }
    fn current_ws_rtt_p50_ms_60s_window(&self) -> u32 {
        0
    }
    fn current_ws_rtt_p99_ms_60s_window(&self) -> u32 {
        0
    }
    fn current_ret_code_4xx_count_60s_window(&self) -> u32 {
        0
    }
    fn current_ret_code_5xx_count_60s_window(&self) -> u32 {
        0
    }
    fn current_ws_dropout_count_60s_window(&self) -> u32 {
        0
    }
}

/// strategy_quality stub source probe；全返 OK-band 等價值。
struct ZeroStrategyQualitySource;

impl StrategyQualitySourceProbe for ZeroStrategyQualitySource {
    fn current_fill_rate_intent_ratio(&self, _strategy: &str, _symbol: &str) -> f64 {
        0.95
    }
    fn current_slippage_bps_p95(&self, _strategy: &str, _symbol: &str) -> f64 {
        1.0
    }
    fn current_decision_lease_grant_rate(&self, _strategy: &str, _symbol: &str) -> f64 {
        0.95
    }
    fn current_dormant_minutes(&self, _strategy: &str, _symbol: &str) -> u32 {
        0
    }
    fn current_signal_count_24h(&self, _strategy: &str, _symbol: &str) -> u32 {
        10
    }
}

// ============================================================
// MetricEmitterScheduler OBSERVE-4 guard test
// ============================================================

/// MetricEmitterScheduler::run with engine_mode='replay' 必 RAISE
/// `M3Error::ReplaySubprocessForbidden` 不靜默通過。
///
/// 為什麼此 test 守 (per Sprint 2 spec line 199-216 OBSERVE-4 設計合約):
///   - V106 line 259 `engine_mode CHECK` 4 值 white-list 不含 'replay'；
///     replay 啟動 emit 會撞 PG CHECK constraint 走到 audit trail 撕裂。
///   - fail-loud guard 在 scheduler.run 啟動瞬間 short-circuit Err，caller
///     端立即看到設計違反，不需等到 PG INSERT fail。
#[tokio::test]
async fn test_metric_emitter_scheduler_replay_engine_mode_forbidden() {
    let api_emitter = ApiLatencyEmitter::new(ZeroApiSource);
    let emitters: Vec<Box<dyn DomainEmitter>> = vec![Box::new(api_emitter)];
    let writer = Arc::new(InMemoryHealthObservationWriter::new());
    let event_bus = Arc::new(HealthEventBus::new());
    let mode: EngineModeProvider = Arc::new(|| "replay".to_string());

    let scheduler = MetricEmitterScheduler::new(emitters, writer, event_bus, mode);

    let cancel = CancellationToken::new();
    let result = scheduler.run(cancel).await;

    assert!(
        matches!(result, Err(M3Error::ReplaySubprocessForbidden)),
        "engine_mode='replay' 啟動 MetricEmitterScheduler::run 必 RAISE \
         M3Error::ReplaySubprocessForbidden（per Sprint 2 spec line 199-216 \
         OBSERVE-4 guard）；實際 result={:?}",
        result
    );
}

/// StrategyQualityScheduler::run with engine_mode='replay' 必 RAISE
/// `M3Error::ReplaySubprocessForbidden`（cross-Wave invariant 守住）。
#[tokio::test]
async fn test_strategy_quality_scheduler_replay_engine_mode_forbidden() {
    let pairs = vec![("grid".to_string(), "BTCUSDT".to_string())];
    let emitter = StrategyQualityEmitter::new(ZeroStrategyQualitySource, pairs);
    let writer = Arc::new(InMemoryHealthObservationWriter::new());
    let event_bus = Arc::new(HealthEventBus::new());
    let mode: EngineModeProvider = Arc::new(|| "replay".to_string());

    let scheduler = StrategyQualityScheduler::new(emitter, writer, event_bus, mode);

    let cancel = CancellationToken::new();
    let result = scheduler.run(cancel).await;

    assert!(
        matches!(result, Err(M3Error::ReplaySubprocessForbidden)),
        "engine_mode='replay' 啟動 StrategyQualityScheduler::run 必 RAISE \
         M3Error::ReplaySubprocessForbidden（cross-Wave invariant per Sprint 2 \
         spec line 199-216 OBSERVE-4 guard）；實際 result={:?}",
        result
    );
}

/// 4 個合法 engine_mode（paper/demo/live_demo/live）啟動 OK；guard 只攔
/// 'replay'。確保 fix 不過度 break 既有合法 mode。
///
/// 為什麼 cancel_token 立即 cancel：避走入 30s+ sample tick；只驗 startup 階段
/// guard 通過、cancel 後 scheduler graceful break loop 返 Ok(())。
#[tokio::test]
async fn test_metric_emitter_scheduler_non_replay_engine_mode_ok_startup() {
    for legal_mode in &["paper", "demo", "live_demo", "live"] {
        let api_emitter = ApiLatencyEmitter::new(ZeroApiSource);
        let emitters: Vec<Box<dyn DomainEmitter>> = vec![Box::new(api_emitter)];
        let writer = Arc::new(InMemoryHealthObservationWriter::new());
        let event_bus = Arc::new(HealthEventBus::new());
        let mode_str = legal_mode.to_string();
        let mode: EngineModeProvider = Arc::new(move || mode_str.clone());

        let scheduler = MetricEmitterScheduler::new(emitters, writer, event_bus, mode);

        let cancel = CancellationToken::new();
        let cancel_clone = cancel.clone();

        let handle = tokio::spawn(async move { scheduler.run(cancel_clone).await });

        // 立即 cancel 避走 60s sample tick；只驗 startup guard 通過。
        tokio::time::sleep(std::time::Duration::from_millis(50)).await;
        cancel.cancel();

        let result = handle.await.expect("scheduler task panicked");
        assert!(
            matches!(result, Ok(())),
            "engine_mode='{}' 為合法 V106 CHECK white-list 4 值之一，scheduler \
             startup guard 必通過，cancel 後 graceful return Ok(())；實際 \
             result={:?}",
            legal_mode,
            result
        );
    }
}
