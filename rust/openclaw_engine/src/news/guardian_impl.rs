//! Production GuardianHaltCheck — flips shared session_halted on high-severity news (Phase 4 W-2).
//! 生產環境 GuardianHaltCheck — 高 severity 新聞觸發共享 session_halted 翻轉（Phase 4 W-2）。
//!
//! MODULE_NOTE (EN):
//!   This wrapper does NOT directly call into governance_core; instead it
//!   shares the same `Arc<AtomicBool>` session_halted instance that the
//!   `claude_teacher::governance_impl::GovernanceCoreWrapper` exposes via
//!   `halted_handle()`. main.rs creates one shared atomic and gives both
//!   the news Guardian and the Teacher GovernanceCheck a clone — single
//!   source of truth, no double-write.
//!
//!   When a news item with severity >= GUARDIAN_HALT_THRESHOLD arrives,
//!   we flip the shared atomic to true. Subsequent Teacher unpause directives
//!   immediately see session_halted == true and are vetoed.
//!
//! MODULE_NOTE (中):
//!   本 wrapper 不直接呼叫 governance_core；改為共享同一個 `Arc<AtomicBool>`
//!   session_halted instance，跟 `claude_teacher::governance_impl::GovernanceCoreWrapper`
//!   的 `halted_handle()` 同源。main.rs 建一個共享原子並讓 news Guardian
//!   與 Teacher GovernanceCheck 都拿到 clone — 單一真相源，無雙寫。
//!
//!   當 severity >= GUARDIAN_HALT_THRESHOLD 的新聞到達時，翻轉共享原子為
//!   true。後續 Teacher unpause directive 立即看到 session_halted == true
//!   並被 veto。

use crate::news::pipeline::ProcessedNewsItem;
use crate::news::router::{GuardianHaltCheck, GUARDIAN_HALT_THRESHOLD};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use tracing::info;

/// EN: Live wrapper that shares session_halted with the Teacher governance wrapper.
/// 中文: 與 Teacher governance wrapper 共享 session_halted 的 live wrapper。
pub struct GuardianHaltCheckImpl {
    /// EN: Shared session_halted flag (also held by GovernanceCoreWrapper).
    /// 中文: 共享 session_halted 旗標（GovernanceCoreWrapper 也持有）。
    session_halted: Arc<AtomicBool>,
    /// EN: Audit counter — incremented every time a news halt is fired.
    /// 中文: 審計計數器 — 每次新聞 halt 觸發時 +1。
    halt_count: AtomicU64,
    /// EN: Last triggering headline hash (for audit / GUI display).
    /// 中文: 最近一次觸發的標題 hash（供審計 / GUI 顯示）。
    last_trigger_hash: Mutex<Option<String>>,
}

impl GuardianHaltCheckImpl {
    /// EN: Construct with a shared session_halted handle from
    ///     `GovernanceCoreWrapper::halted_handle()`.
    /// 中文: 用 `GovernanceCoreWrapper::halted_handle()` 取得的共享 session_halted
    ///       句柄構造。
    pub fn new(session_halted: Arc<AtomicBool>) -> Self {
        Self {
            session_halted,
            halt_count: AtomicU64::new(0),
            last_trigger_hash: Mutex::new(None),
        }
    }

    /// EN: Number of news halts fired since boot.
    /// 中文: 自啟動以來觸發的新聞 halt 次數。
    pub fn halt_count(&self) -> u64 {
        self.halt_count.load(Ordering::Relaxed)
    }

    /// EN: Last triggering headline hash, if any.
    /// 中文: 最近一次觸發的標題 hash（如有）。
    pub fn last_trigger_hash(&self) -> Option<String> {
        self.last_trigger_hash.lock().ok().and_then(|g| g.clone())
    }
}

impl GuardianHaltCheck for GuardianHaltCheckImpl {
    fn on_high_severity_news(&self, item: &ProcessedNewsItem) -> bool {
        // Defensive: only act if severity actually >= threshold (router gates,
        // but double-check at the impl boundary for safety).
        // 防禦性：只在 severity 真的 >= 門檻時動作（router 已 gate，
        // impl 邊界再檢查一次更安全）。
        if item.severity < GUARDIAN_HALT_THRESHOLD {
            return false;
        }
        // Flip the shared atomic. Teacher GovernanceCheck sees this immediately
        // and rejects any subsequent unpause directive.
        // 翻轉共享原子。Teacher GovernanceCheck 立即看到並拒絕任何後續 unpause directive。
        self.session_halted.store(true, Ordering::Relaxed);
        self.halt_count.fetch_add(1, Ordering::Relaxed);
        if let Ok(mut guard) = self.last_trigger_hash.lock() {
            *guard = Some(item.headline_hash.clone());
        }
        info!(
            severity = item.severity,
            headline_hash = %item.headline_hash,
            "guardian halt fired by news / Guardian halt 由新聞觸發"
        );
        true
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::news::types::RawNewsItem;

    fn fixture_item(severity: f64, hash: &str) -> ProcessedNewsItem {
        ProcessedNewsItem {
            raw: RawNewsItem {
                headline: "test".into(),
                body_excerpt: "body".into(),
                url: "https://x".into(),
                published_ms: 1_000,
                source: "mock".into(),
                raw_id: None,
            },
            headline_hash: hash.into(),
            severity,
        }
    }

    #[test]
    fn test_guardian_below_threshold_returns_false_no_halt() {
        let halted = Arc::new(AtomicBool::new(false));
        let g = GuardianHaltCheckImpl::new(Arc::clone(&halted));
        let item = fixture_item(0.5, "low");
        assert!(!g.on_high_severity_news(&item));
        assert!(!halted.load(Ordering::Relaxed));
        assert_eq!(g.halt_count(), 0);
    }

    #[test]
    fn test_guardian_at_threshold_fires_halt() {
        let halted = Arc::new(AtomicBool::new(false));
        let g = GuardianHaltCheckImpl::new(Arc::clone(&halted));
        let item = fixture_item(GUARDIAN_HALT_THRESHOLD, "edge");
        assert!(g.on_high_severity_news(&item));
        assert!(halted.load(Ordering::Relaxed));
        assert_eq!(g.halt_count(), 1);
    }

    #[test]
    fn test_guardian_above_threshold_fires_halt_increments_count() {
        let halted = Arc::new(AtomicBool::new(false));
        let g = GuardianHaltCheckImpl::new(Arc::clone(&halted));
        let item1 = fixture_item(0.92, "first");
        let item2 = fixture_item(0.95, "second");
        assert!(g.on_high_severity_news(&item1));
        assert!(g.on_high_severity_news(&item2));
        assert_eq!(g.halt_count(), 2);
    }

    #[test]
    fn test_guardian_shared_atomic_visible_to_other_holders() {
        let halted = Arc::new(AtomicBool::new(false));
        let other = Arc::clone(&halted);
        let g = GuardianHaltCheckImpl::new(halted);
        let item = fixture_item(0.99, "shared");
        g.on_high_severity_news(&item);
        // Both Arc clones see the same flip.
        // 兩個 Arc clone 看到同一個翻轉。
        assert!(other.load(Ordering::Relaxed));
    }

    #[test]
    fn test_guardian_last_trigger_hash_captured() {
        let halted = Arc::new(AtomicBool::new(false));
        let g = GuardianHaltCheckImpl::new(halted);
        let item = fixture_item(0.88, "captured_hash");
        g.on_high_severity_news(&item);
        assert_eq!(g.last_trigger_hash(), Some("captured_hash".to_string()));
    }
}
