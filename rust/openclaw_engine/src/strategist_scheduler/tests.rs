//! Unit tests for `strategist_scheduler` split out of `mod.rs` by G5-08.
//! G5-08 將 strategist_scheduler 單元測試從 `mod.rs` 拆出。

use super::*;
use crate::ai_service_client::AiServiceClient;
use crate::ipc_server::{DemoCmdSenderSlot, LiveCmdSenderSlot};
use crate::strategies::ParamRange;
use crate::tick_pipeline::{PipelineCommand, PipelineKind};
use std::sync::atomic::Ordering;
use std::sync::Arc;
use std::time::Duration;
use tokio_util::sync::CancellationToken;
#[test]
fn test_pair_metrics_deviation_score() {
    let m = PairMetrics {
        strategy_name: "ma_crossover".into(),
        symbol: "BTCUSDT".into(),
        fill_count: 100,
        avg_pnl: -0.5,
        win_rate: 0.3,
    };
    // pnl_dev = 0.5, wr_dev = |0.3-0.5|*100 = 20.0
    let score = m.deviation_score();
    assert!((score - 20.5).abs() < 0.01);
}

#[test]
fn test_rank_by_deviation() {
    let metrics = vec![
        PairMetrics {
            strategy_name: "a".into(),
            symbol: "BTC".into(),
            fill_count: 50,
            avg_pnl: -0.1,
            win_rate: 0.48,
        },
        PairMetrics {
            strategy_name: "b".into(),
            symbol: "ETH".into(),
            fill_count: 50,
            avg_pnl: -2.0,
            win_rate: 0.2,
        },
    ];
    let ranked = rank_by_deviation(&metrics);
    assert_eq!(ranked[0].strategy_name, "b"); // worse deviation
}

#[test]
fn test_validate_recommendation_passes_valid() {
    let rec = serde_json::json!({
        "cooldown_ms": 55000.0,
        "adx_threshold": 22.0,
    });
    let current = serde_json::json!({
        "cooldown_ms": 50000.0,
        "adx_threshold": 20.0,
    });
    let ranges = vec![
        ParamRange {
            name: "cooldown_ms".into(),
            min: 10000.0,
            max: 120000.0,
            step: Some(1000.0),
            agent_adjustable: true,
            db_persisted: true,
        },
        ParamRange {
            name: "adx_threshold".into(),
            min: 10.0,
            max: 40.0,
            step: Some(1.0),
            agent_adjustable: true,
            db_persisted: true,
        },
    ];
    assert!(validate_recommendation(
        &rec,
        &current,
        &ranges,
        DEFAULT_MAX_PARAM_DELTA_PCT
    ));
}

#[test]
fn test_validate_recommendation_rejects_out_of_range() {
    let rec = serde_json::json!({
        "cooldown_ms": 200000.0,  // above max 120000
    });
    let current = serde_json::json!({
        "cooldown_ms": 50000.0,
    });
    let ranges = vec![ParamRange {
        name: "cooldown_ms".into(),
        min: 10000.0,
        max: 120000.0,
        step: Some(1000.0),
        agent_adjustable: true,
        db_persisted: true,
    }];
    assert!(!validate_recommendation(
        &rec,
        &current,
        &ranges,
        DEFAULT_MAX_PARAM_DELTA_PCT
    ));
}

#[test]
fn test_validate_recommendation_rejects_excessive_delta() {
    let rec = serde_json::json!({
        "cooldown_ms": 100000.0,  // +100% from 50000 > ±50%
    });
    let current = serde_json::json!({
        "cooldown_ms": 50000.0,
    });
    let ranges = vec![ParamRange {
        name: "cooldown_ms".into(),
        min: 10000.0,
        max: 120000.0,
        step: Some(1000.0),
        agent_adjustable: true,
        db_persisted: true,
    }];
    assert!(!validate_recommendation(
        &rec,
        &current,
        &ranges,
        DEFAULT_MAX_PARAM_DELTA_PCT
    ));
}

#[test]
fn test_validate_recommendation_weight_params_exempt_from_delta() {
    // Weight params can change by any amount as long as sum = 65
    // 權重參數可以任意變化，只要總和 = 65
    let rec = serde_json::json!({
        "weight_adx": 30.0,      // was 25, +20% (would fail non-weight delta)
        "weight_regime": 15.0,   // was 20, -25%
        "weight_volume": 12.0,
        "weight_momentum": 8.0,  // sum = 65
    });
    let current = serde_json::json!({
        "weight_adx": 25.0,
        "weight_regime": 20.0,
        "weight_volume": 12.0,
        "weight_momentum": 8.0,
    });
    let ranges = vec![
        ParamRange {
            name: "weight_adx".into(),
            min: 0.0,
            max: 65.0,
            step: Some(1.0),
            agent_adjustable: true,
            db_persisted: true,
        },
        ParamRange {
            name: "weight_regime".into(),
            min: 0.0,
            max: 65.0,
            step: Some(1.0),
            agent_adjustable: true,
            db_persisted: true,
        },
        ParamRange {
            name: "weight_volume".into(),
            min: 0.0,
            max: 65.0,
            step: Some(1.0),
            agent_adjustable: true,
            db_persisted: true,
        },
        ParamRange {
            name: "weight_momentum".into(),
            min: 0.0,
            max: 65.0,
            step: Some(1.0),
            agent_adjustable: true,
            db_persisted: true,
        },
    ];
    assert!(validate_recommendation(
        &rec,
        &current,
        &ranges,
        DEFAULT_MAX_PARAM_DELTA_PCT
    ));
}

#[test]
fn test_validate_recommendation_rejects_bad_weight_sum() {
    let rec = serde_json::json!({
        "weight_adx": 30.0,
        "weight_regime": 20.0,
        "weight_volume": 12.0,
        "weight_momentum": 8.0,  // sum = 70, not 65
    });
    let current = serde_json::json!({});
    let ranges = vec![
        ParamRange {
            name: "weight_adx".into(),
            min: 0.0,
            max: 65.0,
            step: Some(1.0),
            agent_adjustable: true,
            db_persisted: true,
        },
        ParamRange {
            name: "weight_regime".into(),
            min: 0.0,
            max: 65.0,
            step: Some(1.0),
            agent_adjustable: true,
            db_persisted: true,
        },
        ParamRange {
            name: "weight_volume".into(),
            min: 0.0,
            max: 65.0,
            step: Some(1.0),
            agent_adjustable: true,
            db_persisted: true,
        },
        ParamRange {
            name: "weight_momentum".into(),
            min: 0.0,
            max: 65.0,
            step: Some(1.0),
            agent_adjustable: true,
            db_persisted: true,
        },
    ];
    assert!(!validate_recommendation(
        &rec,
        &current,
        &ranges,
        DEFAULT_MAX_PARAM_DELTA_PCT
    ));
}

#[test]
fn test_validate_recommendation_non_adjustable_skipped() {
    // Non-adjustable params in recommendation should be ignored
    // 不可調參數在建議中應被忽略
    let rec = serde_json::json!({
        "active": true,  // not agent_adjustable
        "cooldown_ms": 55000.0,
    });
    let current = serde_json::json!({
        "active": true,
        "cooldown_ms": 50000.0,
    });
    let ranges = vec![
        ParamRange {
            name: "active".into(),
            min: 0.0,
            max: 1.0,
            step: Some(1.0),
            agent_adjustable: false,
            db_persisted: false,
        },
        ParamRange {
            name: "cooldown_ms".into(),
            min: 10000.0,
            max: 120000.0,
            step: Some(1000.0),
            agent_adjustable: true,
            db_persisted: true,
        },
    ];
    assert!(validate_recommendation(
        &rec,
        &current,
        &ranges,
        DEFAULT_MAX_PARAM_DELTA_PCT
    ));
}

#[test]
fn test_validate_empty_recommendation_passes() {
    // Empty recommendation = no changes = valid
    let rec = serde_json::json!({});
    let current = serde_json::json!({});
    let ranges = vec![ParamRange {
        name: "cooldown_ms".into(),
        min: 10000.0,
        max: 120000.0,
        step: Some(1000.0),
        agent_adjustable: true,
        db_persisted: true,
    }];
    assert!(validate_recommendation(
        &rec,
        &current,
        &ranges,
        DEFAULT_MAX_PARAM_DELTA_PCT
    ));
}

#[test]
fn test_backoff_intervals() {
    // Verify the backoff intervals are correct
    // 驗證退避間隔正確
    let ai = Arc::new(AiServiceClient::new());
    let (tx, _rx) = tokio::sync::mpsc::unbounded_channel();
    let pool = Arc::new(crate::database::pool::DbPool::disconnected());
    let cancel = CancellationToken::new();
    let sched = StrategistScheduler::new(ai, tx, PipelineKind::Demo, None, pool, cancel);

    assert_eq!(sched.current_interval(), Duration::from_secs(300));
    sched.consecutive_failures.store(1, Ordering::Relaxed);
    assert_eq!(sched.current_interval(), Duration::from_secs(1_800));
    sched.consecutive_failures.store(2, Ordering::Relaxed);
    assert_eq!(sched.current_interval(), Duration::from_secs(3_600));
    sched.consecutive_failures.store(5, Ordering::Relaxed);
    assert_eq!(sched.current_interval(), Duration::from_secs(14_400));
}

// ═══════════════════════════════════════════════════════════════════
// STRATEGIST-SCHED-CHANNEL-PAPER-ORPHAN-1 regression tests (2026-04-23).
// Verify:
//   1. ctor rejects Paper tune_target (panics)
//   2. ctor accepts Demo / Live
//   3. tune_target() + has_promote_channel() getters
//   4. promote_params_to_live returns Err when no promote channel
//   5. promote_params_to_live sends on the promote channel + awaits response
// STRATEGIST-SCHED-CHANNEL-PAPER-ORPHAN-1 回歸測試（2026-04-23）。
// ═══════════════════════════════════════════════════════════════════

fn mk_deps() -> (
    Arc<AiServiceClient>,
    Arc<crate::database::pool::DbPool>,
    CancellationToken,
) {
    (
        Arc::new(AiServiceClient::new()),
        Arc::new(crate::database::pool::DbPool::disconnected()),
        CancellationToken::new(),
    )
}

#[test]
#[should_panic(expected = "tune_target must be Demo or Live")]
fn test_new_rejects_paper_tune_target() {
    // Paper is drained-and-dropped (PAPER-DISABLE-1) — tuning it is the
    // exact bug we're fixing, so the ctor panics defensively.
    // Paper 是 PAPER-DISABLE-1 後的 drained engine，調它正是 bug 來源，
    // ctor 防禦性 panic 拒絕。
    let (ai, pool, cancel) = mk_deps();
    let (tx, _rx) = tokio::sync::mpsc::unbounded_channel();
    let _ = StrategistScheduler::new(ai, tx, PipelineKind::Paper, None, pool, cancel);
}

#[test]
fn test_new_accepts_demo_without_promote_channel() {
    // Canonical current deployment: Demo tune, no Live promote channel
    // (authorization.json unsigned).
    // 標準部署：Demo tune，Live 未接（authorization.json 未簽）。
    let (ai, pool, cancel) = mk_deps();
    let (tx, _rx) = tokio::sync::mpsc::unbounded_channel();
    let sched = StrategistScheduler::new(ai, tx, PipelineKind::Demo, None, pool, cancel);
    assert_eq!(sched.tune_target(), PipelineKind::Demo);
    assert!(!sched.has_promote_channel());
}

#[test]
fn test_new_accepts_demo_with_live_promote_channel() {
    // Phase 5+ deployment: Demo tune, Live promote wired (auth signed).
    // Phase 5+ 部署：Demo tune，Live 促升已接線（authorization 已簽）。
    let (ai, pool, cancel) = mk_deps();
    let (tune_tx, _tune_rx) = tokio::sync::mpsc::unbounded_channel();
    let (live_tx, _live_rx) = tokio::sync::mpsc::unbounded_channel();
    let sched =
        StrategistScheduler::new(ai, tune_tx, PipelineKind::Demo, Some(live_tx), pool, cancel);
    assert_eq!(sched.tune_target(), PipelineKind::Demo);
    assert!(sched.has_promote_channel());
}

/// WP-13-LEFTOVER-1 (2026-05-16, FA-P1-11 補修) 回歸防禦：
/// scheduler 接 `tune_cmd_slot` 後 `tune_cmd_snapshot()` 必讀 slot 最新值，
/// 而非 ctor 時 owned `tune_cmd_tx`。模擬 pipeline restart：boot 時 slot 與
/// owned 指向 channel A；之後改 slot 指向 channel B；snapshot 必回 B。
#[tokio::test]
async fn test_tune_cmd_snapshot_reads_latest_demo_slot() {
    let (ai, pool, cancel) = mk_deps();
    let (boot_tune_tx, mut boot_rx) = tokio::sync::mpsc::unbounded_channel::<PipelineCommand>();
    let (restart_tune_tx, mut restart_rx) =
        tokio::sync::mpsc::unbounded_channel::<PipelineCommand>();

    let slot: DemoCmdSenderSlot = Arc::new(parking_lot::RwLock::new(Some(boot_tune_tx.clone())));
    let sched = StrategistScheduler::new(ai, boot_tune_tx, PipelineKind::Demo, None, pool, cancel)
        .with_tune_cmd_slot(Arc::clone(&slot));

    // 模擬 demo pipeline restart：slot 改指向新 channel。
    *slot.write() = Some(restart_tune_tx);

    // snapshot 必回最新 slot 值；發送到該 sender 後新 channel 收到，舊 channel 不收。
    let snapshot = sched.tune_cmd_snapshot();
    let (oneshot_tx, _oneshot_rx) = tokio::sync::oneshot::channel::<Result<String, String>>();
    snapshot
        .send(PipelineCommand::GetStrategyParams {
            strategy_name: "probe".to_string(),
            response_tx: oneshot_tx,
        })
        .expect("send to latest slot sender succeeds");

    let msg = restart_rx.try_recv().expect("restart channel must receive");
    assert!(matches!(msg, PipelineCommand::GetStrategyParams { .. }));
    assert!(
        boot_rx.try_recv().is_err(),
        "stale boot-time sender must not receive command after slot rotation"
    );
}

/// WP-13-LEFTOVER-1 (2026-05-16) 回歸防禦：缺 `with_tune_cmd_slot` 時
/// `tune_cmd_snapshot()` 退回 owned `tune_cmd_tx`（測試 / 直接呼叫保留語意）。
#[tokio::test]
async fn test_tune_cmd_snapshot_fallbacks_to_owned_when_slot_absent() {
    let (ai, pool, cancel) = mk_deps();
    let (tune_tx, mut tune_rx) = tokio::sync::mpsc::unbounded_channel::<PipelineCommand>();
    let sched = StrategistScheduler::new(ai, tune_tx, PipelineKind::Demo, None, pool, cancel);

    let snapshot = sched.tune_cmd_snapshot();
    let (oneshot_tx, _oneshot_rx) = tokio::sync::oneshot::channel::<Result<String, String>>();
    snapshot
        .send(PipelineCommand::GetStrategyParams {
            strategy_name: "fallback_probe".to_string(),
            response_tx: oneshot_tx,
        })
        .expect("owned tune_cmd_tx fallback must succeed");

    let msg = tune_rx.try_recv().expect("owned channel must receive");
    assert!(matches!(msg, PipelineCommand::GetStrategyParams { .. }));
}

#[tokio::test]
async fn test_promote_params_to_live_reads_latest_slot_sender() {
    // Production wires a LiveAuthWatcher-rotated slot, not a boot-time
    // fixed sender. Verify promote dispatch uses the current slot value.
    // 生產路徑接 LiveAuthWatcher 輪替 slot；驗證促升發送讀取最新 slot。
    let (ai, pool, cancel) = mk_deps();
    let (tune_tx, _tune_rx) = tokio::sync::mpsc::unbounded_channel();
    let (old_live_tx, mut old_live_rx) = tokio::sync::mpsc::unbounded_channel::<PipelineCommand>();
    let (new_live_tx, mut new_live_rx) = tokio::sync::mpsc::unbounded_channel::<PipelineCommand>();
    let slot: LiveCmdSenderSlot = Arc::new(parking_lot::RwLock::new(Some(old_live_tx)));
    let sched = StrategistScheduler::new(ai, tune_tx, PipelineKind::Demo, None, pool, cancel)
        .with_promote_cmd_slot(Arc::clone(&slot));
    *slot.write() = Some(new_live_tx);

    let handler = tokio::spawn(async move {
        let mut seen_strategy: Option<String> = None;
        if let Some(PipelineCommand::UpdateStrategyParams {
            strategy_name,
            response_tx,
            ..
        }) = new_live_rx.recv().await
        {
            seen_strategy = Some(strategy_name);
            let _ = response_tx.send(Ok("ok".to_string()));
        }
        seen_strategy
    });

    let result = sched
        .promote_params_to_live("slot_rotated_strategy", r#"{"x":1}"#)
        .await;
    assert!(result.is_ok(), "expected Ok, got: {:?}", result.err());
    assert!(
        old_live_rx.try_recv().is_err(),
        "stale boot sender must not receive promote command"
    );
    assert_eq!(
        handler.await.expect("handler panicked").as_deref(),
        Some("slot_rotated_strategy")
    );
}

#[tokio::test]
async fn test_promote_params_to_live_err_when_no_channel() {
    // has_promote_channel() == false → promote is unavailable; return Err
    // without panicking / blocking.
    // 無促升 channel 時應回 Err，不 panic、不 block。
    let (ai, pool, cancel) = mk_deps();
    let (tune_tx, _tune_rx) = tokio::sync::mpsc::unbounded_channel();
    let sched = StrategistScheduler::new(ai, tune_tx, PipelineKind::Demo, None, pool, cancel);
    let result = sched
        .promote_params_to_live("grid_trading", r#"{"cooldown_ms":60000}"#)
        .await;
    assert!(result.is_err());
    let msg = format!("{}", result.unwrap_err());
    assert!(
        msg.contains("Live engine not bound"),
        "expected 'Live engine not bound' in error, got: {}",
        msg,
    );
}

#[tokio::test]
async fn test_promote_params_to_live_sends_and_awaits_response() {
    // With a promote channel wired, verify:
    //   (a) the exact command shape delivered (UpdateStrategyParams with
    //       strategy_name + params_json matching inputs)
    //   (b) the method awaits the oneshot response and returns Ok on Ok(_)
    // 接線後驗證：(a) 命令形狀正確 (b) 等待 oneshot 回應後回 Ok。
    let (ai, pool, cancel) = mk_deps();
    let (tune_tx, _tune_rx) = tokio::sync::mpsc::unbounded_channel();
    let (live_tx, mut live_rx) = tokio::sync::mpsc::unbounded_channel::<PipelineCommand>();
    let sched =
        StrategistScheduler::new(ai, tune_tx, PipelineKind::Demo, Some(live_tx), pool, cancel);

    // Spawn a stub handler that responds with Ok("ok") to any
    // UpdateStrategyParams command on the Live channel.
    // 啟動 stub handler 對 Live channel 上的 UpdateStrategyParams 回 Ok。
    let handler = tokio::spawn(async move {
        let mut seen_strategy: Option<String> = None;
        let mut seen_params: Option<String> = None;
        if let Some(cmd) = live_rx.recv().await {
            if let PipelineCommand::UpdateStrategyParams {
                strategy_name,
                params_json,
                response_tx,
            } = cmd
            {
                seen_strategy = Some(strategy_name);
                seen_params = Some(params_json);
                let _ = response_tx.send(Ok("ok".to_string()));
            }
        }
        (seen_strategy, seen_params)
    });

    let result = sched
        .promote_params_to_live("ma_crossover", r#"{"adx_threshold":22}"#)
        .await;
    assert!(result.is_ok(), "expected Ok, got: {:?}", result.err());

    let (seen_strategy, seen_params) = handler.await.expect("handler panicked");
    assert_eq!(seen_strategy.as_deref(), Some("ma_crossover"));
    assert_eq!(seen_params.as_deref(), Some(r#"{"adx_threshold":22}"#));
}

// E4-4 audit follow-up (2026-04-23): 釘 `PipelineKind::Demo.db_mode()`
// 返回值恆為 `"demo"`（與 `trading.fills.engine_mode` 欄位的 snake_case
// 慣例對齊）。若將來 enum 變成 PascalCase / 改 serde rename 導致回 "Demo"，
// `gather_strategy_metrics` SQL `engine_mode = $2` 會永不命中任何列，
// scheduler 靜默空跑而無任何錯誤。1 行 regression test 可擋此無聲故障。
// E4-4 audit FUP：pin db_mode 返回值，防 snake_case 漂移致 SQL 空跑。
#[test]
fn test_pipeline_kind_db_mode_demo_is_lowercase_snake() {
    assert_eq!(
        PipelineKind::Demo.db_mode(),
        "demo",
        "SQL filter in gather_strategy_metrics depends on db_mode() \
         returning lowercase 'demo' — see STRATEGIST-SCHED-CHANNEL-PAPER-ORPHAN-1"
    );
    // For completeness — these are the currently expected values for all
    // three variants; if anyone changes db_mode() this test trips too.
    // 完整性：另兩個 variant 也 pin。任何人動 db_mode() 都會紅。
    assert_eq!(PipelineKind::Paper.db_mode(), "paper");
    assert_eq!(PipelineKind::Live.db_mode(), "live");
}

#[tokio::test]
async fn test_promote_params_to_live_err_on_handler_failure() {
    // Handler returns Err → promote_params_to_live propagates it.
    // Handler 回 Err → promote 應傳播。
    let (ai, pool, cancel) = mk_deps();
    let (tune_tx, _tune_rx) = tokio::sync::mpsc::unbounded_channel();
    let (live_tx, mut live_rx) = tokio::sync::mpsc::unbounded_channel::<PipelineCommand>();
    let sched =
        StrategistScheduler::new(ai, tune_tx, PipelineKind::Demo, Some(live_tx), pool, cancel);

    tokio::spawn(async move {
        if let Some(cmd) = live_rx.recv().await {
            if let PipelineCommand::UpdateStrategyParams { response_tx, .. } = cmd {
                let _ = response_tx.send(Err("strategy unknown".to_string()));
            }
        }
    });

    let result = sched.promote_params_to_live("unknown_strategy", "{}").await;
    assert!(result.is_err());
}

// ═══════════════════════════════════════════════════════════════════
// STRATEGIST-TUNE-TARGET-CONFIG-1 (2026-04-25): e2e behaviour test for
// the configurable delta clamp. Wires a `ConfigStore<RiskConfig>`,
// mutates `strategist.max_param_delta_pct` via `swap()`, and re-runs
// `validate_recommendation` through the scheduler's
// `current_max_param_delta_pct()` snapshot path. Ensures:
//   - cfg=0.10 → reject a +15% delta (would have passed under 0.50)
//   - cfg=0.70 → accept a +60% delta (would have failed under 0.50)
// This is the integration check the prompt explicitly requires
// ("不要省 e2e behavior 驗證").
// STRATEGIST-TUNE-TARGET-CONFIG-1 e2e：把 max_param_delta_pct 改 0.10
// 餵 +15% 須拒；改 0.70 餵 +60% 須收。驗證 schema → snapshot → validator
// 整鏈通暢。
// ═══════════════════════════════════════════════════════════════════

#[test]
fn test_param_delta_clamp_uses_config_value() {
    use crate::config::risk_config::RiskConfig;
    use crate::config::store::ConfigStore;
    use std::sync::Arc;

    // Helper to build a fresh scheduler with a wired RiskConfig store.
    // 工廠函式：建立帶 RiskConfig store 的 scheduler。
    let make_sched = |max_delta_pct: f64| {
        let mut rc = RiskConfig::default();
        rc.strategist.max_param_delta_pct = max_delta_pct;
        assert!(rc.validate().is_ok(), "test config must validate");
        let store = Arc::new(ConfigStore::new(rc));

        let (ai, pool, cancel) = mk_deps();
        let (tx, _rx) = tokio::sync::mpsc::unbounded_channel();
        StrategistScheduler::new(ai, tx, PipelineKind::Demo, None, pool, cancel)
            .with_risk_store(store)
    };

    // The single agent_adjustable param is `cooldown_ms`. Range is wide
    // enough that out-of-range never triggers — the only gate that
    // changes verdict between cfg values is the delta clamp.
    // 單一 agent_adjustable 參數 cooldown_ms；範圍寬到 out-of-range 不會
    // 觸發，唯有 delta clamp 隨 cfg 變動而切換結果。
    let ranges = vec![ParamRange {
        name: "cooldown_ms".into(),
        min: 1_000.0,
        max: 1_000_000.0,
        step: Some(1_000.0),
        agent_adjustable: true,
        db_persisted: true,
    }];

    // Scenario 1: clamp = 0.10, recommend +15% delta → REJECT.
    // 情境 1：clamp=0.10 拒 +15% delta（在 0.50 預設下原本會通過）。
    let sched_tight = make_sched(0.10);
    let snapshot_tight = sched_tight.current_max_param_delta_pct();
    assert!(
        (snapshot_tight - 0.10).abs() < 1e-12,
        "scheduler must read 0.10 from wired RiskConfig (got {})",
        snapshot_tight
    );

    let current = serde_json::json!({"cooldown_ms": 50_000.0});
    let rec_15pct = serde_json::json!({"cooldown_ms": 57_500.0}); // +15%
    let pass_15pct_at_010 = validate_recommendation(&rec_15pct, &current, &ranges, snapshot_tight);
    assert!(
        !pass_15pct_at_010,
        "+15% delta must be REJECTED when max_param_delta_pct=0.10 \
         (would have passed at default 0.50 — proves clamp config-driven)"
    );

    // Sanity: same +15% delta must PASS at the current 0.50 default,
    // proving scenario 1 actually depends on the configured value
    // (not some unrelated gate).
    // 健全性：同一 +15% 在 0.50 預設下必通過，證明場景 1 拒絕的確由 clamp 驅動。
    let pass_15pct_at_default =
        validate_recommendation(&rec_15pct, &current, &ranges, DEFAULT_MAX_PARAM_DELTA_PCT);
    assert!(
        pass_15pct_at_default,
        "+15% delta must PASS at default 0.50 (clamp difference must be observable)"
    );

    // Scenario 2: clamp = 0.70, recommend +60% delta → ACCEPT.
    // 情境 2：clamp=0.70 收 +60% delta（在 0.50 預設下原本會被拒）。
    let sched_loose = make_sched(0.70);
    let snapshot_loose = sched_loose.current_max_param_delta_pct();
    assert!(
        (snapshot_loose - 0.70).abs() < 1e-12,
        "scheduler must read 0.70 from wired RiskConfig (got {})",
        snapshot_loose
    );

    let rec_60pct = serde_json::json!({"cooldown_ms": 80_000.0}); // +60%
    let pass_60pct_at_070 = validate_recommendation(&rec_60pct, &current, &ranges, snapshot_loose);
    assert!(
        pass_60pct_at_070,
        "+60% delta must be ACCEPTED when max_param_delta_pct=0.70 \
         (would have failed at default 0.50 — proves clamp config-driven)"
    );

    // Symmetric sanity: same +60% must FAIL at the current 0.50 default, so
    // scenario 2 acceptance is genuinely caused by the relaxed clamp.
    // 對稱健全性：+60% 在 0.50 預設下必拒，證明場景 2 通過確由 clamp 放寬驅動。
    let pass_60pct_at_default =
        validate_recommendation(&rec_60pct, &current, &ranges, DEFAULT_MAX_PARAM_DELTA_PCT);
    assert!(
        !pass_60pct_at_default,
        "+60% delta must FAIL at default 0.50 (clamp difference must be observable)"
    );

    // Final scenario: scheduler with NO risk_store wired falls back to
    // DEFAULT_MAX_PARAM_DELTA_PCT (0.50) — the current source default.
    // Ensures direct-call tests / boot-edge cases stay aligned with source.
    // 最後場景：未接 risk_store 時走 0.50 後備（對齊 source 預設）。
    let (ai, pool, cancel) = mk_deps();
    let (tx, _rx) = tokio::sync::mpsc::unbounded_channel();
    let sched_no_store = StrategistScheduler::new(ai, tx, PipelineKind::Demo, None, pool, cancel);
    let snapshot_no_store = sched_no_store.current_max_param_delta_pct();
    assert!(
        (snapshot_no_store - DEFAULT_MAX_PARAM_DELTA_PCT).abs() < 1e-12,
        "no-store scheduler must fall back to DEFAULT_MAX_PARAM_DELTA_PCT (0.50)"
    );
}

#[test]
fn test_param_delta_clamp_hot_reload_via_config_store_replace() {
    // Companion to the e2e test: verify that replacing the wired
    // ConfigStore via `replace()` (the same write API the IPC
    // `patch_risk_config` deep-merge path uses) flips the snapshot
    // mid-flight. Confirms hot-reload works end-to-end without engine
    // restart.
    // 補充：驗證 ConfigStore.replace()（IPC patch_risk_config 寫入路徑同款 API）
    // 即時反映；證明 clamp 真的能熱重載，無須重啟。
    use crate::config::risk_config::RiskConfig;
    use crate::config::store::{ConfigStore, PatchSource};
    use std::sync::Arc;

    let mut rc = RiskConfig::default();
    rc.strategist.max_param_delta_pct = 0.30;
    let store = Arc::new(ConfigStore::new(rc));

    let (ai, pool, cancel) = mk_deps();
    let (tx, _rx) = tokio::sync::mpsc::unbounded_channel();
    let sched = StrategistScheduler::new(ai, tx, PipelineKind::Demo, None, pool, cancel)
        .with_risk_store(Arc::clone(&store));

    assert!(
        (sched.current_max_param_delta_pct() - 0.30).abs() < 1e-12,
        "initial snapshot must be 0.30"
    );

    // Replace with a tighter clamp — simulates IPC patch_risk_config
    // landing through the deep-merge path.
    // 熱替換為較緊 clamp — 模擬 IPC patch_risk_config deep-merge 落入。
    let mut new_rc = RiskConfig::default();
    new_rc.strategist.max_param_delta_pct = 0.15;
    store
        .replace(new_rc, PatchSource::Operator)
        .expect("replace must succeed");

    assert!(
        (sched.current_max_param_delta_pct() - 0.15).abs() < 1e-12,
        "post-replace snapshot must reflect 0.15 (ArcSwap hot-reload visible to scheduler)"
    );
}

// ── G3-11 STRATEGIST-CYCLE-OBSERVABILITY-1 / CycleCounters tests ──
//
// Test matrix:
//   1. record_apply / record_reject / record_cycle_finish basic semantics
//   2. snapshot reflects the live counter values
//   3. concurrent record_reject across N threads tallies correctly
//   4. validate_recommendation_with_reason returns each stable reason
//   5. REJECT_REASONS list covers every error string emitted

#[test]
fn test_cycle_counters_record_apply_and_snapshot() {
    let c = CycleCounters::new();
    c.record_apply(1_700_000_000_000);
    c.record_apply(1_700_000_001_000);
    let snap = c.snapshot();
    assert_eq!(snap.apply_count, 2);
    assert_eq!(snap.last_apply_ts_ms, 1_700_000_001_000);
    assert_eq!(snap.cycle_count, 0);
    assert!(snap.reject_by_reason.is_empty());
}

#[test]
fn test_cycle_counters_record_reject_per_reason() {
    let c = CycleCounters::new();
    c.record_reject("out_of_range");
    c.record_reject("out_of_range");
    c.record_reject("delta_exceeded");
    c.record_reject("ipc_failed");
    let snap = c.snapshot();
    assert_eq!(snap.apply_count, 0);
    assert_eq!(snap.reject_by_reason.get("out_of_range").copied(), Some(2));
    assert_eq!(
        snap.reject_by_reason.get("delta_exceeded").copied(),
        Some(1)
    );
    assert_eq!(snap.reject_by_reason.get("ipc_failed").copied(), Some(1));
    assert_eq!(snap.reject_by_reason.get("weight_sum").copied(), None);
}

#[test]
fn test_cycle_counters_record_cycle_finish_freshness() {
    let c = CycleCounters::new();
    c.record_cycle_finish(1_700_000_000_000);
    c.record_cycle_finish(1_700_000_000_500);
    let snap = c.snapshot();
    assert_eq!(snap.cycle_count, 2);
    assert_eq!(snap.last_cycle_ts_ms, 1_700_000_000_500);
    // Freshness path is independent of apply path (healthcheck [16] reads cycle ts).
    // 即使從未 apply，cycle_finish 仍可前進 — healthcheck [16] 用此判活。
    assert_eq!(snap.last_apply_ts_ms, 0);
}

#[test]
fn test_cycle_counters_concurrent_record_reject() {
    // Spawn N threads × M increments → assert tally consistency.
    // Catches the obvious mutex-lost-update + atomic ordering races.
    // N 線程 × M 次累加 — 抓 mutex / atomic 更新遺失。
    let c = Arc::new(CycleCounters::new());
    let n_threads = 8;
    let increments_per_thread = 250;
    let mut handles = Vec::new();
    for t in 0..n_threads {
        let c2 = Arc::clone(&c);
        handles.push(std::thread::spawn(move || {
            for _ in 0..increments_per_thread {
                // Two reasons, alternating per thread parity, exercises
                // the HashMap entry-or-insert path under contention.
                if t % 2 == 0 {
                    c2.record_reject("out_of_range");
                } else {
                    c2.record_reject("delta_exceeded");
                }
                c2.record_apply(1_000);
            }
        }));
    }
    for h in handles {
        h.join().unwrap();
    }
    let snap = c.snapshot();
    let total = (n_threads * increments_per_thread) as u64;
    assert_eq!(snap.apply_count, total, "apply_count must tally exactly");
    let reject_total: u64 = snap.reject_by_reason.values().sum();
    assert_eq!(reject_total, total, "reject sum must tally exactly");
    // Half-half split per parity rule above.
    assert_eq!(
        snap.reject_by_reason.get("out_of_range").copied(),
        Some(total / 2)
    );
    assert_eq!(
        snap.reject_by_reason.get("delta_exceeded").copied(),
        Some(total / 2)
    );
}

#[test]
fn test_validate_recommendation_with_reason_returns_each_reason() {
    // not_object
    let ranges: Vec<ParamRange> = vec![];
    assert_eq!(
        validate_recommendation_with_reason(
            &serde_json::json!("scalar"),
            &serde_json::json!({}),
            &ranges,
            0.30,
        ),
        Err("not_object")
    );

    // out_of_range
    let ranges_or = vec![ParamRange {
        name: "cooldown_ms".into(),
        min: 10000.0,
        max: 120000.0,
        step: Some(1000.0),
        agent_adjustable: true,
        db_persisted: true,
    }];
    assert_eq!(
        validate_recommendation_with_reason(
            &serde_json::json!({"cooldown_ms": 999_999.0}),
            &serde_json::json!({"cooldown_ms": 50000.0}),
            &ranges_or,
            0.30,
        ),
        Err("out_of_range")
    );

    // delta_exceeded
    assert_eq!(
        validate_recommendation_with_reason(
            &serde_json::json!({"cooldown_ms": 100_000.0}),
            &serde_json::json!({"cooldown_ms": 50_000.0}),
            &ranges_or,
            0.30,
        ),
        Err("delta_exceeded")
    );

    // weight_sum
    let ranges_w = vec![
        ParamRange {
            name: "weight_adx".into(),
            min: 0.0,
            max: 65.0,
            step: Some(1.0),
            agent_adjustable: true,
            db_persisted: true,
        },
        ParamRange {
            name: "weight_regime".into(),
            min: 0.0,
            max: 65.0,
            step: Some(1.0),
            agent_adjustable: true,
            db_persisted: true,
        },
    ];
    assert_eq!(
        validate_recommendation_with_reason(
            &serde_json::json!({"weight_adx": 10.0, "weight_regime": 10.0}),
            &serde_json::json!({}),
            &ranges_w,
            0.30,
        ),
        Err("weight_sum")
    );
}

#[test]
fn test_reject_reasons_list_covers_validate_branches() {
    // Sanity guard: every reason emitted by the validator (and the runtime
    // counters in evaluate_cycle) is enumerated in REJECT_REASONS so
    // documentation + healthcheck matchers stay in sync.
    // 完整性守護：list 必含所有 reason，避免新增分支忘記登記。
    for r in &[
        "not_object",
        "out_of_range",
        "delta_exceeded",
        "weight_sum",
        "ipc_failed",
        "apply_failed",
        // Phase 1（rich-input tuner）server-side quant gate reasons。
        "news_solo_trigger",
        "quant_justification_unverified",
    ] {
        assert!(
            REJECT_REASONS.contains(r),
            "REJECT_REASONS missing reason `{r}`"
        );
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Phase 1（rich-input tuner）：validate_recommendation_with_reason_rich 整合測試
// （quant gate 疊在既有 3 gate 之後；flag-OFF 路徑走 4-arg 版 bit-identical）
// ═══════════════════════════════════════════════════════════════════════════════

use crate::edge_estimates::EdgeEstimates;

const RICH_TEST_TTL: i64 = 172_800; // 48h，對齊 cost_gate 預設
const RICH_TEST_UPDATED_EPOCH: i64 = 1_780_012_800; // 2026-05-29T00:00:00Z

/// 建單 cell EdgeEstimates fixture（runtime_bps + validation_passed 可控）。
fn rich_edge(key: &str, shrunk_bps: f64, validated: bool) -> EdgeEstimates {
    let vp = if validated { "true" } else { "false" };
    let json = format!(
        r#"{{
            "_meta": {{"updated_at": "2026-05-29T00:00:00+00:00"}},
            "{key}": {{"runtime_bps": {shrunk_bps}, "validation_passed": {vp}, "n": 120}}
        }}"#
    );
    EdgeEstimates::load_from_str(&json).unwrap()
}

fn rich_fresh_now() -> i64 {
    RICH_TEST_UPDATED_EPOCH + 100
}

/// 一組 agent_adjustable 範圍（cooldown_ms 落在 ±50% 內）。
fn rich_ranges() -> Vec<ParamRange> {
    vec![ParamRange {
        name: "cooldown_ms".into(),
        min: 10_000.0,
        max: 120_000.0,
        step: Some(1_000.0),
        agent_adjustable: true,
        db_persisted: true,
    }]
}

// ── T-P1-1（rich 變體版）：flag-OFF 路徑與 rich 變體在「無 delta / 既有 3 gate
//    結果」上一致 —— 證 rich 變體只是疊加，不改既有 3 gate 行為 ──
#[test]
fn t_p1_1_rich_variant_preserves_existing_three_gates() {
    let edge = rich_edge("ma_crossover::BTCUSDT", 5.0, true);
    let ranges = rich_ranges();
    let current = serde_json::json!({"cooldown_ms": 50_000.0});

    // out_of_range：rich 變體必須先被既有 gate 擋（與 4-arg 版同 reason）。
    let oor = serde_json::json!({"cooldown_ms": 999_999.0});
    assert_eq!(
        validate_recommendation_with_reason(&oor, &current, &ranges, 0.50),
        Err("out_of_range")
    );
    assert_eq!(
        validate_recommendation_with_reason_rich(
            &oor, &current, &ranges, 0.50, &edge, rich_fresh_now(), RICH_TEST_TTL
        ),
        Err("out_of_range"),
        "rich 變體必須先跑既有 3 gate，out_of_range 早於 quant gate"
    );
}

// ── T-P1-8：cell 真實+fresh+validated+數值對齊 → rich 變體 Ok（可 apply）──
#[test]
fn t_p1_8_rich_variant_valid_cell_passes() {
    let edge = rich_edge("ma_crossover::BTCUSDT", 5.0, true);
    let ranges = rich_ranges();
    let current = serde_json::json!({"cooldown_ms": 50_000.0});
    // +10% delta（在 ±50% 內），帶對齊的 quant_justification。
    let rec = serde_json::json!({
        "cooldown_ms": 55_000.0,
        "quant_justification": {
            "source": "edge_estimates",
            "cell": "ma_crossover::BTCUSDT",
            "claimed_shrunk_bps": 5.0,
            "direction": "tighten",
            "rationale": "edge supports"
        }
    });
    assert_eq!(
        validate_recommendation_with_reason_rich(
            &rec, &current, &ranges, 0.50, &edge, rich_fresh_now(), RICH_TEST_TTL
        ),
        Ok(())
    );
}

// ── T-P1-2（rich 變體版）：有 delta 但無 quant_justification → news_solo_trigger ──
#[test]
fn t_p1_2_rich_variant_delta_without_justification() {
    let edge = rich_edge("ma_crossover::BTCUSDT", 5.0, true);
    let ranges = rich_ranges();
    let current = serde_json::json!({"cooldown_ms": 50_000.0});
    let rec = serde_json::json!({"cooldown_ms": 55_000.0});
    assert_eq!(
        validate_recommendation_with_reason_rich(
            &rec, &current, &ranges, 0.50, &edge, rich_fresh_now(), RICH_TEST_TTL
        ),
        Err("news_solo_trigger")
    );
}

// ── T-P1-11：空 recommendation {} → rich 變體 bypass quant gate（Ok）──
//    證 flag-ON 下 LLM 棄調（回 {}）時行為與既有 empty 一致（不誤觸 quant gate）。
#[test]
fn t_p1_11_rich_variant_empty_rec_bypasses_quant_gate() {
    let edge = rich_edge("ma_crossover::BTCUSDT", 5.0, true);
    let ranges = rich_ranges();
    let current = serde_json::json!({"cooldown_ms": 50_000.0});
    let empty = serde_json::json!({});
    // 既有 4-arg 版：空 rec → Ok（無 param 改）。
    assert_eq!(
        validate_recommendation_with_reason(&empty, &current, &ranges, 0.50),
        Ok(())
    );
    // rich 變體：空 rec → 無 real delta → quant gate bypass → Ok（一致）。
    assert_eq!(
        validate_recommendation_with_reason_rich(
            &empty, &current, &ranges, 0.50, &edge, rich_fresh_now(), RICH_TEST_TTL
        ),
        Ok(())
    );
}

// ── T-P1-11b：rec 只把 param 設成與當前相同值（無實際 delta）→ bypass ──
#[test]
fn t_p1_11b_rich_variant_no_real_delta_bypasses() {
    let edge = rich_edge("ma_crossover::BTCUSDT", 5.0, true);
    let ranges = rich_ranges();
    let current = serde_json::json!({"cooldown_ms": 50_000.0});
    // 設成與當前相同 → 無 delta → 不需 quant_justification。
    let same = serde_json::json!({"cooldown_ms": 50_000.0});
    assert_eq!(
        validate_recommendation_with_reason_rich(
            &same, &current, &ranges, 0.50, &edge, rich_fresh_now(), RICH_TEST_TTL
        ),
        Ok(())
    );
}

// ═══════════════════════════════════════════════════════════════════════════════
// Phase 1 可觀測性：edge 可達面 log（reachable surface）
//
// 測試 `resolve_edge_reachable_surface`（log_edge_reachable_surface 委派的 count
// 解析），它是每輪 log 行的數據來源。`resolve_*` 讀真 wallclock now，故 fresh
// 路徑用「相對當前時間新鮮」的 snapshot 建構（避免固定過去 updated_at 在測試時
// 已 stale 而打不到 fresh 分支）。reachable_surface_counts 對 injected now 的精確
// 計數另由 edge_estimates.rs 單元測試覆蓋。
// ═══════════════════════════════════════════════════════════════════════════════

/// 建多 cell EdgeEstimates，`updated_at` 相對當前 wallclock 偏移 `age_secs` 秒。
/// 為什麼動態時間戳：`resolve_edge_reachable_surface` 讀真 now，要打到 fresh 分支
/// 必須讓 snapshot 相對 now 新鮮（固定 2026-05-29 在測試時早已超 48h TTL）。
fn obs_edge_store(
    age_secs: i64,
) -> Arc<parking_lot::RwLock<EdgeEstimates>> {
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0);
    let updated = now - age_secs;
    let updated_rfc3339 = chrono::DateTime::<chrono::Utc>::from_timestamp(updated, 0)
        .unwrap()
        .to_rfc3339();
    // 3 cells：2 validated（a/b）、1 not（c）。
    let json = format!(
        r#"{{
            "_meta": {{"updated_at": "{updated_rfc3339}"}},
            "ma_crossover::BTCUSDT": {{"runtime_bps": 5.0, "validation_passed": true, "n": 120}},
            "grid_trading::ETHUSDT": {{"runtime_bps": 3.0, "validation_passed": true, "n": 90}},
            "bb_reversion::SOLUSDT": {{"runtime_bps": 1.0, "validation_passed": false, "n": 12}}
        }}"#
    );
    Arc::new(parking_lot::RwLock::new(
        EdgeEstimates::load_from_str(&json).unwrap(),
    ))
}

// ── flag-ON + stubbed fresh edge_store → 正確 n_validated / n_fresh / n_usable ──
#[test]
fn t_p1_obs_flag_on_fresh_store_reports_correct_surface() {
    let (ai, pool, cancel) = mk_deps();
    let (tx, _rx) = tokio::sync::mpsc::unbounded_channel();
    // age=100s，遠小於預設 48h TTL（無 risk store → DEFAULT_EDGE_ESTIMATE_TTL_SECS）→ fresh。
    let store = obs_edge_store(100);
    let sched = StrategistScheduler::new(ai, tx, PipelineKind::Demo, None, pool, cancel)
        .with_rich_input(true)
        .with_edge_store(store);

    let (n_cells, n_validated, n_fresh, n_usable) = sched.resolve_edge_reachable_surface();
    assert_eq!(n_cells, 3, "3 cells in snapshot");
    assert_eq!(n_validated, 2, "2 cells validation_passed=true");
    assert_eq!(n_fresh, 3, "fresh snapshot → all cells fresh");
    assert_eq!(n_usable, 2, "usable = validated AND fresh");
}

// ── flag-ON + stale edge_store → fresh/usable 面歸 0（validated 仍可見）──
#[test]
fn t_p1_obs_flag_on_stale_store_zeroes_fresh_and_usable() {
    let (ai, pool, cancel) = mk_deps();
    let (tx, _rx) = tokio::sync::mpsc::unbounded_channel();
    // age 超過預設 48h TTL → snapshot stale。
    let store = obs_edge_store(DEFAULT_EDGE_ESTIMATE_TTL_SECS + 3_600);
    let sched = StrategistScheduler::new(ai, tx, PipelineKind::Demo, None, pool, cancel)
        .with_rich_input(true)
        .with_edge_store(store);

    let (n_cells, n_validated, n_fresh, n_usable) = sched.resolve_edge_reachable_surface();
    assert_eq!(n_cells, 3);
    assert_eq!(n_validated, 2);
    assert_eq!(n_fresh, 0, "stale snapshot → 0 fresh");
    assert_eq!(n_usable, 0, "validated 但 stale → 0 usable");
}

// ── flag-ON 但 edge_store 未接 → 全 0（明示無可引 edge）──
#[test]
fn t_p1_obs_flag_on_no_store_all_zero() {
    let (ai, pool, cancel) = mk_deps();
    let (tx, _rx) = tokio::sync::mpsc::unbounded_channel();
    let sched = StrategistScheduler::new(ai, tx, PipelineKind::Demo, None, pool, cancel)
        .with_rich_input(true);
    assert_eq!(
        sched.resolve_edge_reachable_surface(),
        (0, 0, 0, 0),
        "flag-ON but edge_store unwired → all zero"
    );
}

// ── flag-OFF：emit 完全不觸發（行為 byte-identical）──
// 證明：(1) flag-OFF scheduler 的 rich_input_enabled=false → evaluate_cycle 的
// `if self.rich_input_enabled` gate 短路，log_edge_reachable_surface 不可達。
// (2) count 解析本身是純函數，flag 與 count 值無耦合（flag 是唯一 emit gate）。
// 用 inspect-source 鎖死「emit site 被 rich_input_enabled gate 包住」這個不變量，
// 防未來有人把 emit 移出 gate（=flag-OFF 不再 byte-identical 的回歸）。
#[test]
fn t_p1_obs_flag_off_emit_is_gated() {
    let (ai, pool, cancel) = mk_deps();
    let (tx, _rx) = tokio::sync::mpsc::unbounded_channel();
    let store = obs_edge_store(100);
    // 預設（不呼 with_rich_input）→ rich_input_enabled=false。
    let sched_off = StrategistScheduler::new(ai, tx, PipelineKind::Demo, None, pool, cancel)
        .with_edge_store(store);
    assert!(
        !sched_off.rich_input_enabled,
        "flag-OFF scheduler must have rich_input_enabled=false → emit site unreachable"
    );

    // 不變量：emit（log_edge_reachable_surface 呼叫）必在 rich_input_enabled gate
    // 內。evaluate.rs 原始碼斷言：呼叫點上方緊鄰 `if self.rich_input_enabled`。
    let src = include_str!("evaluate.rs");
    let gate_idx = src
        .find("if self.rich_input_enabled {\n            self.log_edge_reachable_surface();")
        .expect(
            "log_edge_reachable_surface() must be emitted only inside the \
             `if self.rich_input_enabled` gate (flag-OFF byte-identical)",
        );
    // emit 呼叫只應出現在 gate 之內，不應有 gate 外的裸呼叫。
    let total_calls = src.matches("self.log_edge_reachable_surface()").count();
    assert_eq!(
        total_calls, 1,
        "exactly one emit call site, and it is the gated one (idx {gate_idx})"
    );
}
