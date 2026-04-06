//! Production LearningContextSink — buffers news severity for next DecisionContextMsg (Phase 4 W-2).
//! 生產環境 LearningContextSink — 為下一個 DecisionContextMsg 緩存 news severity（Phase 4 W-2）。
//!
//! MODULE_NOTE (EN):
//!   The 4-09 NewsRouter calls `on_news_for_learning` for every processed
//!   item. We do NOT directly call context_writer here — instead we update
//!   an atomic snapshot that the next tick_pipeline DecisionContextMsg
//!   construction reads. This keeps news ingestion (async, sparse) and
//!   tick decisions (synchronous, frequent) loosely coupled.
//!
//!   The snapshot exposes:
//!   - `latest_severity()` — most recent severity score (f32, matches
//!      DecisionContextMsg.news_severity)
//!   - `hours_since_last_major(now_ms)` — hours since the last news with
//!      severity >= GUARDIAN_HALT_THRESHOLD (matches
//!      DecisionContextMsg.hours_since_last_major_news)
//!
//! MODULE_NOTE (中):
//!   4-09 NewsRouter 對每條 processed item 呼叫 `on_news_for_learning`。
//!   本 wrapper 不直接呼叫 context_writer，而是更新原子快照供下一個
//!   tick_pipeline DecisionContextMsg 構造時讀取。新聞攝取（非同步、稀疏）
//!   與 tick 決策（同步、頻繁）保持鬆耦合。
//!
//!   快照暴露：
//!   - `latest_severity()` — 最近 severity 分數（f32，對應
//!      DecisionContextMsg.news_severity）
//!   - `hours_since_last_major(now_ms)` — 距上次 severity >= GUARDIAN_HALT_THRESHOLD
//!      新聞的小時數（對應 DecisionContextMsg.hours_since_last_major_news）

use crate::news::pipeline::ProcessedNewsItem;
use crate::news::router::{LearningContextSink, GUARDIAN_HALT_THRESHOLD};
use std::sync::atomic::{AtomicI64, AtomicU64, Ordering};
use std::sync::Arc;

/// EN: Atomic snapshot read by tick_pipeline DecisionContextMsg producer.
/// 中文: tick_pipeline DecisionContextMsg producer 讀取的原子快照。
pub struct NewsContextSnapshot {
    /// EN: Latest severity * 1e6 stored as u64 (atomic-safe, 0..1_000_000).
    /// 中文: 最近 severity × 1e6 以 u64 存（原子安全，0..1_000_000）。
    latest_severity_micro: AtomicU64,
    /// EN: published_ms of the most recent high-severity news.
    ///     -1 if no high-severity news observed yet.
    /// 中文: 最近一條 high-severity 新聞的 published_ms。
    ///       尚未觀察到 high-severity 時為 -1。
    last_high_severity_ts_ms: AtomicI64,
}

impl Default for NewsContextSnapshot {
    fn default() -> Self {
        Self {
            latest_severity_micro: AtomicU64::new(0),
            last_high_severity_ts_ms: AtomicI64::new(-1),
        }
    }
}

impl NewsContextSnapshot {
    pub fn new() -> Self {
        Self::default()
    }

    /// EN: Get current latest severity as f32.
    /// 中文: 取當前最近 severity 為 f32。
    pub fn latest_severity(&self) -> f32 {
        let micro = self.latest_severity_micro.load(Ordering::Relaxed);
        (micro as f32) / 1_000_000.0
    }

    /// EN: Get current latest severity as f64 (precision-preserved).
    /// 中文: 取當前最近 severity 為 f64（保留精度）。
    pub fn latest_severity_f64(&self) -> f64 {
        let micro = self.latest_severity_micro.load(Ordering::Relaxed);
        (micro as f64) / 1_000_000.0
    }

    /// EN: Hours since the last high-severity news observed at given now_ms.
    ///     None if no high-severity news has been observed yet.
    /// 中文: 距上次 high-severity 新聞的小時數（以 now_ms 計）。
    ///       未觀察到時返回 None。
    pub fn hours_since_last_major(&self, now_ms: i64) -> Option<f64> {
        let ts = self.last_high_severity_ts_ms.load(Ordering::Relaxed);
        if ts < 0 {
            return None;
        }
        let delta_ms = now_ms.saturating_sub(ts);
        Some((delta_ms as f64) / 3_600_000.0)
    }

    /// EN: Direct mutator for testing — set latest severity from f64.
    /// 中文: 測試用直接 mutator — 從 f64 設定 latest severity。
    #[cfg(test)]
    pub fn set_latest_severity(&self, severity: f64) {
        let micro = (severity.clamp(0.0, 1.0) * 1_000_000.0) as u64;
        self.latest_severity_micro.store(micro, Ordering::Relaxed);
    }
}

/// EN: Production LearningContextSink — pushes severity into a shared snapshot.
/// 中文: 生產 LearningContextSink — 把 severity 推入共享快照。
pub struct LearningContextSinkImpl {
    snapshot: Arc<NewsContextSnapshot>,
}

impl LearningContextSinkImpl {
    /// EN: Construct with a shared snapshot. main.rs creates one Arc and
    ///     gives it to both this sink and the tick_pipeline producer.
    /// 中文: 用共享快照構造。main.rs 建一個 Arc 並同時給此 sink 與
    ///       tick_pipeline producer。
    pub fn new(snapshot: Arc<NewsContextSnapshot>) -> Self {
        Self { snapshot }
    }

    /// EN: Borrow the snapshot Arc for sharing with the tick pipeline.
    /// 中文: 借出 snapshot Arc 供 tick pipeline 共享。
    pub fn snapshot_handle(&self) -> Arc<NewsContextSnapshot> {
        Arc::clone(&self.snapshot)
    }
}

impl LearningContextSink for LearningContextSinkImpl {
    fn on_news_for_learning(&self, item: &ProcessedNewsItem) -> Result<(), String> {
        // Always store the freshest item (no max with previous; tick_pipeline
        // can apply its own freshness gate when reading).
        // 永遠存最新項目（不取 max；tick_pipeline 讀取時可套用自己的新鮮度 gate）。
        let micro = (item.severity.clamp(0.0, 1.0) * 1_000_000.0) as u64;
        self.snapshot
            .latest_severity_micro
            .store(micro, Ordering::Relaxed);
        if item.severity >= GUARDIAN_HALT_THRESHOLD {
            self.snapshot
                .last_high_severity_ts_ms
                .store(item.raw.published_ms, Ordering::Relaxed);
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::news::types::RawNewsItem;

    fn fixture_item(severity: f64, published_ms: i64) -> ProcessedNewsItem {
        ProcessedNewsItem {
            raw: RawNewsItem {
                headline: "test".into(),
                body_excerpt: "body".into(),
                url: "https://x".into(),
                published_ms,
                source: "mock".into(),
                raw_id: None,
            },
            headline_hash: "hash".into(),
            severity,
        }
    }

    #[test]
    fn test_snapshot_default_severity_zero() {
        let s = NewsContextSnapshot::default();
        assert_eq!(s.latest_severity(), 0.0);
        assert_eq!(s.latest_severity_f64(), 0.0);
    }

    #[test]
    fn test_snapshot_default_hours_since_returns_none() {
        let s = NewsContextSnapshot::default();
        assert!(s.hours_since_last_major(1_000_000).is_none());
    }

    #[test]
    fn test_snapshot_set_latest_severity_round_trip() {
        let s = NewsContextSnapshot::default();
        s.set_latest_severity(0.42);
        assert!((s.latest_severity_f64() - 0.42).abs() < 1e-6);
    }

    #[test]
    fn test_learning_sink_updates_latest_severity() {
        let snap = Arc::new(NewsContextSnapshot::default());
        let sink = LearningContextSinkImpl::new(Arc::clone(&snap));
        let item = fixture_item(0.55, 1_000);
        sink.on_news_for_learning(&item).expect("ok");
        assert!((snap.latest_severity_f64() - 0.55).abs() < 1e-6);
    }

    #[test]
    fn test_learning_sink_high_severity_updates_last_ts() {
        let snap = Arc::new(NewsContextSnapshot::default());
        let sink = LearningContextSinkImpl::new(Arc::clone(&snap));
        let item = fixture_item(0.92, 5_000);
        sink.on_news_for_learning(&item).expect("ok");
        // Check last_high_severity_ts via hours_since_last_major @ now=5000
        // → 0 hours.
        // 透過 hours_since_last_major @ now=5000 檢查 last_high_severity_ts → 0 小時。
        let hours = snap.hours_since_last_major(5_000);
        assert!(hours.is_some());
        assert!(hours.unwrap() < 1e-6);
    }

    #[test]
    fn test_learning_sink_low_severity_does_not_update_last_ts() {
        let snap = Arc::new(NewsContextSnapshot::default());
        let sink = LearningContextSinkImpl::new(Arc::clone(&snap));
        let item = fixture_item(0.5, 5_000);
        sink.on_news_for_learning(&item).expect("ok");
        // Severity below threshold → last_ts not updated → hours_since None.
        // severity 低於門檻 → last_ts 未更新 → hours_since None。
        assert!(snap.hours_since_last_major(10_000).is_none());
    }

    #[test]
    fn test_snapshot_hours_since_calculation() {
        let snap = NewsContextSnapshot::default();
        snap.last_high_severity_ts_ms.store(0, Ordering::Relaxed);
        // now_ms = 7_200_000 ms = 2 hours
        // now_ms = 7_200_000 ms = 2 小時
        let hours = snap.hours_since_last_major(7_200_000).expect("some");
        assert!((hours - 2.0).abs() < 1e-6);
    }

    #[test]
    fn test_snapshot_handle_shared() {
        let snap = Arc::new(NewsContextSnapshot::default());
        let sink = LearningContextSinkImpl::new(Arc::clone(&snap));
        let h1 = sink.snapshot_handle();
        h1.set_latest_severity(0.7);
        // Original snap sees the update via the shared Arc.
        // 原 snap 透過共享 Arc 看到更新。
        assert!((snap.latest_severity_f64() - 0.7).abs() < 1e-6);
    }
}
