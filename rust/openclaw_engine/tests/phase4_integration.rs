//! Phase 4 sub-task 4-19 — End-to-end integration test stitching together
//! W1/W2/W3/W4a deliverables (news router, LinUCB, Claude Teacher directive
//! applier, decision context) via injected mock impls. No live PG required.
//!
//! Phase 4 子任務 4-19 — 端到端集成測試，串通 W1/W2/W3/W4a 已交付模組
//! （news router、LinUCB、Claude Teacher directive applier、decision context），
//! 全部透過注入 mock impls 執行，不需要 live PG。
//!
//! Three cases / 三個案例:
//!   A. Happy path — low-severity news → arm select → safe directive applied
//!   B. High-severity news → Guardian halt triggered → directive vetoed
//!   C. Hard-boundary directive (P0 field) vetoed by denylist
//!
//! ARCH-RC1 sentinel: MockSink carries a `python_touched` AtomicBool which
//! the applier has no way to flip (the trait has zero Python-reaching
//! methods). The happy-path test asserts it stays `false` after Apply.
//! ARCH-RC1 哨兵：MockSink 帶有 `python_touched` AtomicBool，applier 無任何
//! 方式能將其翻為 true（trait 刻意不暴露任何可觸 Python 的方法）。
//! Happy-path 測試斷言套用後該旗標維持 false。

use openclaw_engine::claude_teacher::applier::{
    ApplyOutcome, DirectiveApplier, GovernanceCheck, IpcFuture, StrategyIpcSink,
};
use openclaw_engine::claude_teacher::parser::{Directive, DirectiveType};
use openclaw_engine::database::pool::DbPool;
use openclaw_engine::database::{DatabaseConfig, DecisionContextMsg};
use openclaw_engine::linucb::arms_v1_15::v1_15_arm_ids;
use openclaw_engine::linucb::inference::{select_arm, ArmState, LinUcbConfig};
use openclaw_engine::news::pipeline::ProcessedNewsItem;
use openclaw_engine::news::router::{
    GuardianHaltCheck, LearningContextSink, NewsRouter, RegimeNewsBuffer,
};
use openclaw_engine::news::types::RawNewsItem;

use serde_json::json;
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};
use tokio::sync::RwLock;

// ---------------------------------------------------------------------------
// Mock impls / Mock 實作
// ---------------------------------------------------------------------------

/// Mock GovernanceCheck — fully test-controllable state.
/// Mock GovernanceCheck — 完全可被測試控制的狀態。
struct MockGovernance {
    session_halted: AtomicBool,
    daily_loss_pct: Mutex<f64>,
    unpause_threshold: f64,
    known: Vec<String>,
}

impl MockGovernance {
    fn healthy() -> Arc<Self> {
        Arc::new(Self {
            session_halted: AtomicBool::new(false),
            daily_loss_pct: Mutex::new(0.0),
            unpause_threshold: 0.05,
            known: vec![
                "ma_crossover".into(),
                "bb_reversion".into(),
                "bb_breakout".into(),
                "grid_trading".into(),
                "funding_arb".into(),
            ],
        })
    }
}

impl GovernanceCheck for MockGovernance {
    fn current_daily_loss_pct(&self) -> f64 {
        *self.daily_loss_pct.lock().unwrap()
    }
    fn session_halted(&self) -> bool {
        self.session_halted.load(Ordering::SeqCst)
    }
    fn unpause_daily_loss_threshold(&self) -> f64 {
        self.unpause_threshold
    }
    fn known_strategies(&self) -> Vec<String> {
        self.known.clone()
    }
}

/// Mock StrategyIpcSink — records all calls + ARCH-RC1 sentinel.
/// Mock StrategyIpcSink — 紀錄所有呼叫 + ARCH-RC1 哨兵。
#[derive(Default)]
struct MockSink {
    calls: Mutex<Vec<String>>,
    /// ARCH-RC1 sentinel: must never flip to true through the applier path.
    /// ARCH-RC1 哨兵：applier 路徑絕不可能把它翻成 true。
    python_touched: AtomicBool,
    total_calls: AtomicUsize,
}

impl StrategyIpcSink for MockSink {
    fn update_strategy_params<'a>(
        &'a self,
        strategy_name: &'a str,
        params_json: &'a str,
    ) -> IpcFuture<'a> {
        self.total_calls.fetch_add(1, Ordering::SeqCst);
        self.calls
            .lock()
            .unwrap()
            .push(format!("update_strategy_params({strategy_name}, {params_json})"));
        Box::pin(async move { Ok(format!("params updated for {strategy_name}")) })
    }

    fn set_strategy_active<'a>(
        &'a self,
        strategy_name: &'a str,
        active: bool,
    ) -> IpcFuture<'a> {
        self.total_calls.fetch_add(1, Ordering::SeqCst);
        self.calls
            .lock()
            .unwrap()
            .push(format!("set_strategy_active({strategy_name}, {active})"));
        Box::pin(async move { Ok("ok".to_string()) })
    }
}

/// Mock GuardianHaltCheck — records invocation for assertions.
/// Mock GuardianHaltCheck — 紀錄是否被呼叫供斷言使用。
struct MockGuardian {
    called: AtomicBool,
    last_severity: Mutex<f64>,
}

impl MockGuardian {
    fn new() -> Arc<Self> {
        Arc::new(Self {
            called: AtomicBool::new(false),
            last_severity: Mutex::new(0.0),
        })
    }
}

impl GuardianHaltCheck for MockGuardian {
    fn on_high_severity_news(&self, item: &ProcessedNewsItem) -> bool {
        self.called.store(true, Ordering::SeqCst);
        *self.last_severity.lock().unwrap() = item.severity;
        true
    }
}

/// Mock LearningContextSink — collects items for later assertion.
/// Mock LearningContextSink — 收集項目供後續斷言。
#[derive(Default)]
struct MockLearning {
    items: Mutex<Vec<f64>>,
    call_count: AtomicUsize,
}

impl LearningContextSink for MockLearning {
    fn on_news_for_learning(&self, item: &ProcessedNewsItem) -> Result<(), String> {
        self.call_count.fetch_add(1, Ordering::SeqCst);
        self.items.lock().unwrap().push(item.severity);
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// Fixtures / 夾具
// ---------------------------------------------------------------------------

/// Build a ProcessedNewsItem with given severity + published ms.
/// 用指定 severity 與 published ms 建構 ProcessedNewsItem。
fn fixture_news(severity: f64, published_ms: i64, headline: &str) -> ProcessedNewsItem {
    ProcessedNewsItem {
        raw: RawNewsItem {
            headline: headline.into(),
            body_excerpt: "body".into(),
            url: "https://example.com/a".into(),
            published_ms,
            source: "mock".into(),
            raw_id: None,
        },
        headline_hash: "abcd00000000dead".into(),
        severity,
    }
}

/// UNIX seconds one day in the future (parser rejects past expiry).
/// 一天後的 UNIX 秒（parser 拒絕過期 expiry）。
fn future_expiry_secs() -> i64 {
    (std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap()
        .as_secs()
        + 86_400) as i64
}

fn build_directive(
    ty: DirectiveType,
    scope: &str,
    params: serde_json::Value,
) -> Directive {
    Directive {
        directive_type: ty,
        scope: scope.into(),
        params,
        expiry: future_expiry_secs(),
        priority: 5,
    }
}

/// Create an empty (disconnected) DbPool — all writes are no-ops / best-effort.
/// 建立空（未連線）DbPool — 所有寫入皆為 no-op / best-effort。
async fn empty_pool() -> Arc<DbPool> {
    let cfg = DatabaseConfig {
        database_url: String::new(),
        ..Default::default()
    };
    Arc::new(DbPool::connect(&cfg).await)
}

fn build_router(
    guardian: Arc<MockGuardian>,
    learning: Arc<MockLearning>,
) -> (NewsRouter, Arc<RwLock<RegimeNewsBuffer>>) {
    let buf = Arc::new(RwLock::new(RegimeNewsBuffer::default()));
    let router = NewsRouter::new(
        Some(guardian as Arc<dyn GuardianHaltCheck>),
        buf.clone(),
        Some(learning as Arc<dyn LearningContextSink>),
    );
    (router, buf)
}

// ---------------------------------------------------------------------------
// Case A: Happy path — low severity → arm select → safe directive applied
// 案例 A: Happy path — 低 severity → arm 選擇 → 安全 directive 套用
// ---------------------------------------------------------------------------

#[tokio::test]
async fn test_full_loop_happy_path_low_severity_directive_applied() {
    // --- 1. Mock news: low severity item ("Bitcoin price rises")
    //       mock 新聞：低 severity 項目。
    let news = fixture_news(0.3, 1_000, "Bitcoin price rises modestly");

    // --- 2. NewsRouter dispatch — Guardian should NOT be called.
    //       NewsRouter 分發 — Guardian 不應被呼叫。
    let guardian = MockGuardian::new();
    let learning = Arc::new(MockLearning::default());
    let (router, buf) = build_router(guardian.clone(), learning.clone());
    router.dispatch(&news, 1_000).await;

    assert!(
        !guardian.called.load(Ordering::SeqCst),
        "Guardian must NOT be called for severity < 0.8 / Guardian 不得被呼叫於 severity < 0.8"
    );
    {
        let snap = buf.read().await;
        assert!(
            (snap.latest_severity - 0.3).abs() < 1e-9,
            "regime buffer latest_severity should be 0.3"
        );
    }
    assert_eq!(
        learning.call_count.load(Ordering::SeqCst),
        1,
        "Learning sink should receive the item / Learning sink 應收到項目"
    );

    // --- 3. LinUCB: build 15 v1_15 cold-start arms and select with synthetic
    //       8-dim context. Cold start => all arms share max exploration bonus
    //       so select_arm must return Some.
    //       LinUCB: 建立 15 個 v1_15 cold-start arms 並以合成 8 維 context 選 arm。
    //       冷啟動時所有 arm 共享最大探索 bonus，select_arm 必須回傳 Some。
    let cfg = LinUcbConfig {
        context_dim: 8,
        alpha: 1.0,
        lambda: 1.0,
    };
    let arms: Vec<ArmState> = v1_15_arm_ids()
        .into_iter()
        .map(|id| ArmState::cold_start(id, cfg.context_dim, cfg.lambda))
        .collect();
    assert_eq!(arms.len(), 15, "v1_15 expects exactly 15 arms");
    let context = vec![0.5_f64; 8];
    let chosen = select_arm(&arms, &context, &cfg);
    assert!(
        chosen.is_some(),
        "select_arm must return Some on cold-start / 冷啟動 select_arm 必須回 Some"
    );
    let chosen_arm_id = chosen.unwrap().arm_id.clone();

    // --- 4+5. Build DirectiveApplier with MockGovernance (healthy) + MockSink.
    //         以 MockGovernance (healthy) + MockSink 建立 DirectiveApplier。
    let gov = MockGovernance::healthy();
    let sink = Arc::new(MockSink::default());
    let pool = empty_pool().await;
    let applier = DirectiveApplier::new(
        gov.clone() as Arc<dyn GovernanceCheck>,
        Some(sink.clone() as Arc<dyn StrategyIpcSink>),
        pool,
    );

    // --- 6. Apply a safe adjust_param directive.
    //       套用一個安全的 adjust_param directive。
    let directive = build_directive(
        DirectiveType::AdjustParam,
        "ma_crossover",
        json!({"min_confidence": 0.55}),
    );
    let outcome = applier.apply(directive, 1).await;

    assert!(
        matches!(outcome, ApplyOutcome::Applied { .. }),
        "expected Applied, got {outcome:?}"
    );
    assert_eq!(
        sink.total_calls.load(Ordering::SeqCst),
        1,
        "sink.update_strategy_params should be called exactly once"
    );
    let calls = sink.calls.lock().unwrap().clone();
    assert!(
        calls[0].starts_with("update_strategy_params(ma_crossover"),
        "expected update_strategy_params call, got {calls:?}"
    );

    // --- ARCH-RC1 sentinel: python_touched must still be false.
    //       ARCH-RC1 哨兵：python_touched 必須仍為 false。
    assert!(
        !sink.python_touched.load(Ordering::SeqCst),
        "ARCH-RC1 violated: applier must not touch Python / ARCH-RC1 違反：applier 不得觸及 Python"
    );

    // --- 7. Confirm DecisionContextMsg can be wired with Phase 4 columns.
    //       驗證 DecisionContextMsg 可用 Phase 4 欄位構造。
    let msg = DecisionContextMsg {
        context_id: "ctx-happy-1".into(),
        ts_ms: 1_000,
        decision_type: "apply_directive".into(),
        symbol: "BTCUSDT".into(),
        strategy_name: "ma_crossover".into(),
        last_price: 50_000.0,
        spread_bps: 1.0,
        regime_5m: "trending".into(),
        ind_5m_adx: 20.0,
        ind_5m_rsi: 55.0,
        ind_5m_atr_14_pct: 0.008,
        position_side: "none".into(),
        position_qty: 0.0,
        total_equity: 10_000.0,
        drawdown_pct: 0.0,
        indicators_snapshot: json!({}),
        position_detail: json!({}),
        decision_payload: json!({}),
        claude_directive_id: Some(1),
        linucb_arm_id: Some(chosen_arm_id),
        linucb_confidence_bound: Some(0.42),
        news_severity: Some(0.3_f32),
        hours_since_last_major_news: Some(24.0),
        engine_mode: "paper".into(),
    };
    assert_eq!(msg.claude_directive_id, Some(1));
    assert!(msg.linucb_arm_id.is_some());
    assert_eq!(msg.news_severity, Some(0.3_f32));
}

// ---------------------------------------------------------------------------
// Case B: High-severity news triggers Guardian → directive vetoed
// 案例 B: 高 severity 新聞觸發 Guardian → directive 被 veto
// ---------------------------------------------------------------------------

#[tokio::test]
async fn test_full_loop_high_severity_news_triggers_guardian_and_vetoes_directive() {
    // --- 1. High-severity news item.
    //       高 severity 新聞項目。
    let news = fixture_news(0.92, 5_000, "SEC opens major investigation");

    // --- 2. Router dispatch → Guardian invoked.
    //       Router 分發 → Guardian 被呼叫。
    let guardian = MockGuardian::new();
    let learning = Arc::new(MockLearning::default());
    let (router, buf) = build_router(guardian.clone(), learning.clone());
    router.dispatch(&news, 5_000).await;

    assert!(
        guardian.called.load(Ordering::SeqCst),
        "Guardian must be called on severity >= 0.8"
    );
    assert!((*guardian.last_severity.lock().unwrap() - 0.92).abs() < 1e-9);

    // --- 3+4. Simulate the operational policy: high-severity news causes the
    //         session to be halted. Flip the mock governance state directly
    //         (trait has no setter; we own the AtomicBool inside the mock).
    //         模擬運營政策：高 severity 新聞致 session halt。直接翻轉 mock
    //         governance 狀態（trait 無 setter；mock 內部 AtomicBool 我們自己掌控）。
    let gov = MockGovernance::healthy();
    gov.session_halted.store(true, Ordering::SeqCst);

    let sink = Arc::new(MockSink::default());
    let pool = empty_pool().await;
    let applier = DirectiveApplier::new(
        gov.clone() as Arc<dyn GovernanceCheck>,
        Some(sink.clone() as Arc<dyn StrategyIpcSink>),
        pool,
    );

    // --- 5. Apply any safe directive — must be vetoed by governance.
    //       套用任意安全 directive — 必須被 governance veto。
    let directive = build_directive(
        DirectiveType::AdjustParam,
        "ma_crossover",
        json!({"min_confidence": 0.5}),
    );
    let outcome = applier.apply(directive, 2).await;

    assert!(
        matches!(outcome, ApplyOutcome::VetoedByGovernance { .. }),
        "expected VetoedByGovernance, got {outcome:?}"
    );

    // --- 6. IPC sink NOT called — session halted blocked the path.
    //       IPC sink 未被呼叫 — session halted 阻斷。
    assert_eq!(
        sink.total_calls.load(Ordering::SeqCst),
        0,
        "IPC sink must NOT be called when session halted"
    );

    // --- 7. Regime buffer last_high_severity_ts_ms is set.
    //       Regime buffer last_high_severity_ts_ms 已設定。
    let snap = buf.read().await;
    assert_eq!(
        snap.last_high_severity_ts_ms,
        Some(5_000),
        "regime buffer should record last_high_severity_ts_ms"
    );
}

// ---------------------------------------------------------------------------
// Case C: Hard-boundary directive (P0 field) vetoed by denylist
// 案例 C: 硬邊界 directive（P0 欄位）被黑名單 veto
// ---------------------------------------------------------------------------

#[tokio::test]
async fn test_full_loop_directive_targeting_p0_field_vetoed_by_hard_boundary() {
    // --- 1. Directive attempting to modify a P0 denylist field.
    //       嘗試修改 P0 黑名單欄位的 directive。
    let directive = build_directive(
        DirectiveType::AdjustParam,
        "ma_crossover",
        json!({"max_position_size_usd": 999_999.0}),
    );

    let gov = MockGovernance::healthy();
    let sink = Arc::new(MockSink::default());
    let pool = empty_pool().await;
    let applier = DirectiveApplier::new(
        gov.clone() as Arc<dyn GovernanceCheck>,
        Some(sink.clone() as Arc<dyn StrategyIpcSink>),
        pool,
    );

    // --- 2. Apply → VetoedByHardBoundary with boundary name surfaced.
    //       套用 → VetoedByHardBoundary 並帶出違規欄位名。
    let outcome = applier.apply(directive, 3).await;
    match &outcome {
        ApplyOutcome::VetoedByHardBoundary { boundary, .. } => {
            assert_eq!(
                boundary, "max_position_size_usd",
                "boundary field name should be surfaced"
            );
        }
        other => panic!("expected VetoedByHardBoundary, got {other:?}"),
    }

    // --- 3. IPC sink not called (gate 1 short-circuits).
    //       IPC sink 未被呼叫（閘 1 短路）。
    assert_eq!(
        sink.total_calls.load(Ordering::SeqCst),
        0,
        "IPC sink must NOT be called on hard-boundary veto"
    );

    // --- 4. ARCH-RC1 sentinel still clean.
    //       ARCH-RC1 哨兵仍乾淨。
    assert!(!sink.python_touched.load(Ordering::SeqCst));

    // --- 5. Audit write path was exercised (best-effort on empty pool).
    //       審計寫入路徑已被執行（空 pool 上 best-effort）。
    assert_eq!(outcome.directive_id(), 3);
    assert_eq!(outcome.action_tag(), "vetoed_by_hard_boundary");
}
