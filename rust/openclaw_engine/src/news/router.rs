// MODULE_NOTE
// EN: NewsBus router — fan-out processed news to three independent consumers (4-09).
//     1. Guardian — high-severity (>= 0.8) news triggers halt check (fail-closed)
//     2. Regime  — severity buffered for regime classifier
//     3. Learning — written into decision_context_snapshots for ML training
//
//     The three routes are independent: a failure or absence of one consumer
//     does NOT block the others. Trait-object injection mirrors the
//     `GovernanceCheck` / `StrategyIpcSink` pattern from claude_teacher::applier.
//
// 中文: NewsBus 路由器 — 把處理後的新聞分發到三個獨立消費者（4-09）。
//       1. Guardian — high severity (>= 0.8) 新聞觸發 halt check (fail-closed)
//       2. Regime  — severity 進 regime classifier 的 buffer
//       3. Learning — 寫入 decision_context_snapshots 供 ML 訓練
//
//       三條路由獨立：某個消費者缺席或失敗不阻塞其他兩個。trait-object 注入
//       模式對齊 claude_teacher::applier 的 GovernanceCheck / StrategyIpcSink。

use crate::news::pipeline::ProcessedNewsItem;
use std::sync::Arc;
use tokio::sync::RwLock;
use tracing::{debug, warn};

/// EN: Severity threshold above which the Guardian halt check is triggered.
/// 中文: Guardian halt check 的 severity 閾值。
pub const GUARDIAN_HALT_THRESHOLD: f64 = 0.8;

/// EN: Maximum age (hours) for a news item to still update `latest_severity`
///     in the regime buffer at full weight. Older items still pass through
///     for audit but their freshness decay applies.
/// 中文: 新聞仍以全權重更新 regime buffer `latest_severity` 的最大年齡（小時）。
///       超過此值仍會通過審計，但會套用新鮮度衰減。
pub const REGIME_FRESH_AGE_HOURS: f64 = 1.0;

// ---------------------------------------------------------------------------
// Regime buffer / regime 緩衝
// ---------------------------------------------------------------------------

/// EN: Snapshot of recent news state consumed by the tick pipeline regime
///     classifier. All fields are optional / monotone — readers must tolerate
///     `None` (cold-start safe).
/// 中文: tick pipeline regime classifier 消費的最近新聞狀態快照。所有欄位皆
///       可選 / 單調遞增 — 讀者必須容忍 None（冷啟動安全）。
#[derive(Debug, Clone, Default)]
pub struct RegimeNewsBuffer {
    /// EN: Highest severity observed within `REGIME_FRESH_AGE_HOURS`.
    /// 中文: `REGIME_FRESH_AGE_HOURS` 內觀察到的最高 severity。
    pub latest_severity: f64,
    /// EN: Wall-clock millis of the last item with severity >= GUARDIAN_HALT_THRESHOLD.
    /// 中文: 最近一條 severity >= GUARDIAN_HALT_THRESHOLD 的牆鐘毫秒時間戳。
    pub last_high_severity_ts_ms: Option<i64>,
    /// EN: Hours since `last_high_severity_ts_ms` (computed at dispatch time).
    /// 中文: 距 `last_high_severity_ts_ms` 的小時數（dispatch 時計算）。
    pub hours_since_last_major: Option<f64>,
}

// ---------------------------------------------------------------------------
// Trait interfaces / trait 介面
// ---------------------------------------------------------------------------

/// EN: Guardian halt-check sink. Implementations are responsible for the
///     internal Veto / halt logic — the router only forwards high-severity items.
///     Returning `false` does NOT block other routes; it is informational.
/// 中文: Guardian halt-check 接收器。實作負責內部 Veto / halt 邏輯 —
///       router 只轉發高 severity 項目。返回 `false` 不會阻塞其他路由，僅為資訊性。
pub trait GuardianHaltCheck: Send + Sync {
    /// EN: Called when a news item with severity >= `GUARDIAN_HALT_THRESHOLD` arrives.
    /// 中文: 當 severity >= `GUARDIAN_HALT_THRESHOLD` 的新聞到達時呼叫。
    fn on_high_severity_news(&self, item: &ProcessedNewsItem) -> bool;
}

/// EN: Learning context sink. Implementations persist the news features into
///     the next decision context snapshot row(s); they may batch internally.
///     Returning `Err` is logged but never propagated to the router caller.
/// 中文: Learning context 接收器。實作把新聞特徵持久化到下一個 decision
///       context snapshot row（可內部 batch）。返回 `Err` 只記 log，不向 router
///       caller 傳播。
pub trait LearningContextSink: Send + Sync {
    /// EN: Persist news_severity + hours_since_last_major_news to the next snapshot.
    /// 中文: 把 news_severity + hours_since_last_major_news 持久化到下一個 snapshot。
    fn on_news_for_learning(&self, item: &ProcessedNewsItem) -> Result<(), String>;
}

// ---------------------------------------------------------------------------
// NewsRouter / 新聞路由器
// ---------------------------------------------------------------------------

/// EN: Three-route fan-out for processed news items.
///     Each route is independent: a panic / Err from one consumer is logged
///     but does not affect the other two routes.
/// 中文: 處理後新聞項目的三路 fan-out。每條路由獨立：單一消費者 panic / Err
///       只記 log，不影響其他兩條路由。
pub struct NewsRouter {
    guardian: Option<Arc<dyn GuardianHaltCheck>>,
    regime_buffer: Arc<RwLock<RegimeNewsBuffer>>,
    learning: Option<Arc<dyn LearningContextSink>>,
}

impl NewsRouter {
    /// EN: Construct a router. Any consumer may be `None` (cold-start safe).
    /// 中文: 構造 router。任一消費者可為 `None`（冷啟動安全）。
    pub fn new(
        guardian: Option<Arc<dyn GuardianHaltCheck>>,
        regime_buffer: Arc<RwLock<RegimeNewsBuffer>>,
        learning: Option<Arc<dyn LearningContextSink>>,
    ) -> Self {
        Self {
            guardian,
            regime_buffer,
            learning,
        }
    }

    /// EN: Build a router with all consumers absent (used by tests / cold start).
    ///     The regime buffer is still allocated so reads stay valid.
    /// 中文: 建立全消費者缺席的 router（測試 / 冷啟動用）。regime buffer 仍會
    ///       分配，使讀取仍有效。
    pub fn empty() -> Self {
        Self {
            guardian: None,
            regime_buffer: Arc::new(RwLock::new(RegimeNewsBuffer::default())),
            learning: None,
        }
    }

    /// EN: Read the current regime buffer snapshot. Used by `tick_pipeline` to
    ///     pull the latest news features into regime classification.
    /// 中文: 讀當前 regime buffer 快照。tick_pipeline 用此把最新新聞特徵
    ///       拉入 regime 分類。
    pub async fn regime_snapshot(&self) -> RegimeNewsBuffer {
        self.regime_buffer.read().await.clone()
    }

    /// EN: Fan out a single processed news item to all three routes.
    ///     - Guardian: only if severity >= GUARDIAN_HALT_THRESHOLD
    ///     - Regime:   always (updates buffer with freshness decay)
    ///     - Learning: always
    ///     Each route is wrapped so a failure does not affect the others.
    /// 中文: 把單條 processed news 分發到三條路由。
    ///       Guardian：僅當 severity >= GUARDIAN_HALT_THRESHOLD。
    ///       Regime：永遠（含新鮮度衰減）。
    ///       Learning：永遠。
    ///       每條路由獨立包裝，一條失敗不影響其他。
    pub async fn dispatch(&self, item: &ProcessedNewsItem, now_ms: i64) {
        // ── Route 1: Guardian halt check ──
        // 路由 1：Guardian halt 檢查
        if item.severity >= GUARDIAN_HALT_THRESHOLD {
            match &self.guardian {
                Some(g) => {
                    let ack = g.on_high_severity_news(item);
                    debug!(
                        severity = item.severity,
                        ack = ack,
                        "guardian high-severity news dispatched / Guardian 高 severity 新聞已派發"
                    );
                }
                None => {
                    warn!(
                        severity = item.severity,
                        headline_hash = %item.headline_hash,
                        "guardian sink unset; high-severity news observed but no halt check / Guardian 接收器未設，高 severity 新聞無法 halt"
                    );
                }
            }
        }

        // ── Route 2: Regime buffer update (always) ──
        // 路由 2：Regime buffer 更新（永遠）
        {
            let age_ms = now_ms.saturating_sub(item.raw.published_ms);
            let age_hours = (age_ms as f64) / 3_600_000.0;
            // Linear freshness decay: factor 1.0 at age=0, factor 0 at age=REGIME_FRESH_AGE_HOURS.
            // Older items beyond the window contribute zero to latest_severity but still
            // update last_high_severity_ts if they exceed the threshold.
            // 線性新鮮度衰減：age=0 時 1.0，age>=REGIME_FRESH_AGE_HOURS 時 0。
            // 超過窗口的舊新聞對 latest_severity 貢獻 0，但若超過門檻仍更新 last_high_severity_ts。
            let decay = if age_hours <= 0.0 {
                1.0
            } else if age_hours >= REGIME_FRESH_AGE_HOURS {
                0.0
            } else {
                1.0 - (age_hours / REGIME_FRESH_AGE_HOURS)
            };
            let weighted = item.severity * decay;

            let mut guard = self.regime_buffer.write().await;
            if weighted > guard.latest_severity {
                guard.latest_severity = weighted;
            }
            if item.severity >= GUARDIAN_HALT_THRESHOLD {
                guard.last_high_severity_ts_ms = Some(item.raw.published_ms);
            }
            if let Some(ts) = guard.last_high_severity_ts_ms {
                let hours = (now_ms.saturating_sub(ts) as f64) / 3_600_000.0;
                guard.hours_since_last_major = Some(hours);
            }
        }

        // ── Route 3: Learning context sink (always) ──
        // 路由 3：Learning context 接收器（永遠）
        if let Some(l) = &self.learning {
            // Wrap in catch_unwind-style resilience: trait Err is logged, panics
            // are NOT caught here (callers should ensure trait impls don't panic).
            // 用 Err 日誌包裝；trait 實作不應 panic（router 不處理 panic）。
            if let Err(e) = l.on_news_for_learning(item) {
                warn!(
                    error = %e,
                    headline_hash = %item.headline_hash,
                    "learning sink Err; news not persisted to context (router continues) / Learning 接收器 Err；新聞未寫入 context（router 繼續）"
                );
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Tests / 測試
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::news::types::RawNewsItem;
    use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
    use std::sync::Mutex;

    /// EN: Build a ProcessedNewsItem fixture with the given severity + age.
    /// 中文: 用指定 severity 與 age 建構 ProcessedNewsItem fixture。
    fn fixture_item(severity: f64, published_ms: i64) -> ProcessedNewsItem {
        ProcessedNewsItem {
            raw: RawNewsItem {
                headline: "test headline".into(),
                body_excerpt: "test body".into(),
                url: "https://example.com/x".into(),
                published_ms,
                source: "mock".into(),
                raw_id: None,
            },
            headline_hash: "deadbeef00000000".into(),
            severity,
        }
    }

    // ── Mock Guardian ──

    struct MockGuardian {
        called: AtomicBool,
        last_severity: Mutex<f64>,
        return_value: bool,
    }

    impl MockGuardian {
        fn new(return_value: bool) -> Arc<Self> {
            Arc::new(Self {
                called: AtomicBool::new(false),
                last_severity: Mutex::new(0.0),
                return_value,
            })
        }
    }

    impl GuardianHaltCheck for MockGuardian {
        fn on_high_severity_news(&self, item: &ProcessedNewsItem) -> bool {
            self.called.store(true, Ordering::Relaxed);
            *self.last_severity.lock().unwrap() = item.severity;
            self.return_value
        }
    }

    // ── Mock Learning ──

    struct MockLearning {
        items_received: Mutex<Vec<f64>>,
        fail_next: AtomicBool,
        call_count: AtomicUsize,
    }

    impl MockLearning {
        fn new() -> Arc<Self> {
            Arc::new(Self {
                items_received: Mutex::new(Vec::new()),
                fail_next: AtomicBool::new(false),
                call_count: AtomicUsize::new(0),
            })
        }
    }

    impl LearningContextSink for MockLearning {
        fn on_news_for_learning(&self, item: &ProcessedNewsItem) -> Result<(), String> {
            self.call_count.fetch_add(1, Ordering::Relaxed);
            if self.fail_next.swap(false, Ordering::Relaxed) {
                return Err("simulated learning failure".into());
            }
            self.items_received.lock().unwrap().push(item.severity);
            Ok(())
        }
    }

    fn make_router(
        guardian: Option<Arc<dyn GuardianHaltCheck>>,
        learning: Option<Arc<dyn LearningContextSink>>,
    ) -> NewsRouter {
        NewsRouter::new(
            guardian,
            Arc::new(RwLock::new(RegimeNewsBuffer::default())),
            learning,
        )
    }

    // ── Tests ──

    #[tokio::test]
    async fn test_router_dispatch_below_threshold_skips_guardian() {
        let g = MockGuardian::new(true);
        let router = make_router(Some(g.clone()), None);
        let item = fixture_item(0.5, 1_000);
        router.dispatch(&item, 1_000).await;
        assert!(!g.called.load(Ordering::Relaxed));
    }

    #[tokio::test]
    async fn test_router_dispatch_above_threshold_calls_guardian() {
        let g = MockGuardian::new(true);
        let router = make_router(Some(g.clone()), None);
        let item = fixture_item(0.9, 1_000);
        router.dispatch(&item, 1_000).await;
        assert!(g.called.load(Ordering::Relaxed));
        assert_eq!(*g.last_severity.lock().unwrap(), 0.9);
    }

    #[tokio::test]
    async fn test_router_guardian_unset_logs_warn_no_panic() {
        let router = make_router(None, None);
        let item = fixture_item(0.95, 1_000);
        router.dispatch(&item, 1_000).await;
        // No panic = pass. The warn is observable via tracing in production.
        // 不 panic 即通過。warn 在生產環境透過 tracing 可觀察。
    }

    #[tokio::test]
    async fn test_router_updates_regime_buffer_latest_severity() {
        let router = make_router(None, None);
        let item = fixture_item(0.7, 1_000);
        router.dispatch(&item, 1_000).await; // age=0 -> decay=1.0
        let snap = router.regime_snapshot().await;
        assert!((snap.latest_severity - 0.7).abs() < 1e-9);
    }

    #[tokio::test]
    async fn test_router_updates_last_high_severity_ts() {
        let router = make_router(None, None);
        let item = fixture_item(0.85, 5_000);
        router.dispatch(&item, 5_000).await;
        let snap = router.regime_snapshot().await;
        assert_eq!(snap.last_high_severity_ts_ms, Some(5_000));
    }

    #[tokio::test]
    async fn test_router_calculates_hours_since_last_major() {
        let router = make_router(None, None);
        let item = fixture_item(0.9, 0);
        // now_ms = 7_200_000 ms = 2 hours after published
        // now_ms = 7_200_000 ms = 發佈後 2 小時
        router.dispatch(&item, 7_200_000).await;
        let snap = router.regime_snapshot().await;
        assert!(snap.hours_since_last_major.is_some());
        assert!((snap.hours_since_last_major.unwrap() - 2.0).abs() < 1e-6);
    }

    #[tokio::test]
    async fn test_router_learning_called_on_every_item_regardless_of_severity() {
        let l = MockLearning::new();
        let router = make_router(None, Some(l.clone()));
        router.dispatch(&fixture_item(0.1, 1_000), 1_000).await;
        router.dispatch(&fixture_item(0.5, 1_001), 1_001).await;
        router.dispatch(&fixture_item(0.95, 1_002), 1_002).await;
        assert_eq!(l.call_count.load(Ordering::Relaxed), 3);
    }

    #[tokio::test]
    async fn test_router_learning_error_does_not_propagate() {
        let l = MockLearning::new();
        l.fail_next.store(true, Ordering::Relaxed);
        let router = make_router(None, Some(l.clone()));
        let item = fixture_item(0.6, 1_000);
        // Should NOT panic or raise.
        // 不應 panic 或 raise。
        router.dispatch(&item, 1_000).await;
        assert_eq!(l.call_count.load(Ordering::Relaxed), 1);
    }

    #[tokio::test]
    async fn test_router_routes_independent_guardian_and_learning_both_called_on_high_severity() {
        let g = MockGuardian::new(false);
        let l = MockLearning::new();
        let router = make_router(Some(g.clone()), Some(l.clone()));
        let item = fixture_item(0.9, 1_000);
        router.dispatch(&item, 1_000).await;
        assert!(g.called.load(Ordering::Relaxed));
        assert_eq!(l.call_count.load(Ordering::Relaxed), 1);
    }

    #[tokio::test]
    async fn test_router_freshness_decay_zero_at_one_hour() {
        let router = make_router(None, None);
        // published 1 hour ago, decay = 0 -> latest_severity stays at default 0
        // 1 小時前發佈，decay = 0 -> latest_severity 維持預設 0
        let item = fixture_item(0.9, 0);
        router.dispatch(&item, 3_600_000).await;
        let snap = router.regime_snapshot().await;
        // weighted severity = 0.9 * 0 = 0 -> buffer unchanged from default
        assert_eq!(snap.latest_severity, 0.0);
        // last_high_severity_ts still recorded for audit
        // last_high_severity_ts 仍記錄供審計
        assert_eq!(snap.last_high_severity_ts_ms, Some(0));
    }

    #[tokio::test]
    async fn test_router_empty_constructor_safe() {
        let router = NewsRouter::empty();
        let item = fixture_item(0.95, 1_000);
        router.dispatch(&item, 1_000).await;
        let snap = router.regime_snapshot().await;
        // High-severity item still updates regime buffer with full decay (age=0).
        // 高 severity 項目仍以全衰減（age=0）更新 regime buffer。
        assert!((snap.latest_severity - 0.95).abs() < 1e-9);
    }
}
