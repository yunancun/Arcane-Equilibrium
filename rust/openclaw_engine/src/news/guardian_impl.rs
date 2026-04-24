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

/// EN: Default TTL for news-induced session halt: 30 minutes.
///   After this window without a fresh high-severity news event, the halt
///   atomic is auto-cleared by `check_and_clear_expired()` so trading can
///   resume. Headline staleness was the root cause of the 2026-04-24 watchdog
///   crashloop false-positive (G6-FUP-NEWS-HALT-DEDUP-1): the same headline
///   re-emitted by news pipeline every 60s kept tripping halt with no clear
///   path. 30min was chosen because typical market-moving news has decayed in
///   impact within 30min; longer would unnecessarily delay trading resumption.
/// 中文: 新聞觸發 session halt 的預設 TTL：30 分鐘。沒有新的高嚴重度新聞超過
///   此窗口，halt 原子由 `check_and_clear_expired()` 自動清除以恢復交易。
pub const DEFAULT_HALT_TTL_MS: u64 = 30 * 60 * 1000;

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
    /// EN: Wall-clock ms when halt was last fired (0 = never). Used by
    ///   `check_and_clear_expired()` to auto-clear the shared atomic after
    ///   `halt_ttl_ms` elapses without a fresh halt event.
    /// 中文: halt 上次觸發的 wall-clock 毫秒（0 = 未觸發）；TTL 過期由
    ///   `check_and_clear_expired()` 自動清除共享原子。
    last_trigger_ts_ms: AtomicU64,
    /// EN: TTL window in ms. Default = `DEFAULT_HALT_TTL_MS`.
    /// 中文: TTL 窗口（毫秒），預設 30 分鐘。
    halt_ttl_ms: u64,
}

impl GuardianHaltCheckImpl {
    /// EN: Construct with a shared session_halted handle from
    ///     `GovernanceCoreWrapper::halted_handle()`.
    /// 中文: 用 `GovernanceCoreWrapper::halted_handle()` 取得的共享 session_halted
    ///       句柄構造。
    pub fn new(session_halted: Arc<AtomicBool>) -> Self {
        Self::with_ttl(session_halted, DEFAULT_HALT_TTL_MS)
    }

    /// EN: Construct with an explicit halt TTL (for testing / config tuning).
    /// 中文: 帶顯式 TTL 的構造函式（測試 / 配置調整用）。
    pub fn with_ttl(session_halted: Arc<AtomicBool>, halt_ttl_ms: u64) -> Self {
        Self {
            session_halted,
            halt_count: AtomicU64::new(0),
            last_trigger_hash: Mutex::new(None),
            last_trigger_ts_ms: AtomicU64::new(0),
            halt_ttl_ms,
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

    /// EN: Last halt fire timestamp in ms (0 if never fired since boot).
    /// 中文: 最近一次 halt 觸發的毫秒時間戳（0 = 啟動以來未觸發）。
    pub fn last_trigger_ts_ms(&self) -> u64 {
        self.last_trigger_ts_ms.load(Ordering::Relaxed)
    }

    /// EN: G6-FUP-NEWS-HALT-DEDUP-1 (2026-04-25): if `now_ms - last_trigger_ts
    ///   >= halt_ttl_ms` AND the halt atomic is currently true AND a halt has
    ///   been fired at least once, clear the atomic and zero the trigger ts.
    ///   Returns true iff the atomic was actually cleared by this call.
    ///
    ///   Caller (news pipeline scheduler @ tasks.rs:spawn_news_pipeline) invokes
    ///   this every 60s tick BEFORE running providers, so a stale halt window
    ///   self-resolves within ~30min instead of persisting forever (which was
    ///   the 2026-04-24 watchdog false-positive crashloop pathology).
    ///
    ///   Conservative ordering: ttl check + atomic clear happen on the news
    ///   scheduler thread; another news event in the same tick will re-fire
    ///   halt via on_high_severity_news → store(true) on the same atomic, so
    ///   no race window where halt is missed.
    /// 中文: G6-FUP-NEWS-HALT-DEDUP-1：每 60s 由 news scheduler 呼叫；若超過
    ///   TTL 且 halt 仍 true → 自動清除原子並歸零 ts。同 tick 內如有新的高
    ///   嚴重度新聞會立即重觸發 halt，無遺漏窗口。
    pub fn check_and_clear_expired(&self, now_ms: u64) -> bool {
        let last = self.last_trigger_ts_ms.load(Ordering::Relaxed);
        if last == 0 {
            return false;
        }
        if !self.session_halted.load(Ordering::Relaxed) {
            return false;
        }
        if now_ms.saturating_sub(last) < self.halt_ttl_ms {
            return false;
        }
        self.session_halted.store(false, Ordering::Relaxed);
        self.last_trigger_ts_ms.store(0, Ordering::Relaxed);
        info!(
            now_ms,
            last_trigger_ms = last,
            elapsed_ms = now_ms.saturating_sub(last),
            ttl_ms = self.halt_ttl_ms,
            "G6-FUP-NEWS-HALT-DEDUP-1: news halt auto-cleared after TTL \
             / 新聞 halt TTL 過期，自動清除"
        );
        true
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
        // G6-FUP-NEWS-HALT-DEDUP-1: stamp wall-clock ts so the news scheduler's
        // periodic check_and_clear_expired() can auto-clear after the TTL.
        // G6-FUP-NEWS-HALT-DEDUP-1：紀錄 wall-clock 時間戳，讓 news scheduler
        // 的 check_and_clear_expired() 在 TTL 過後自動清除。
        let now_ms = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_millis() as u64)
            .unwrap_or(0);
        self.last_trigger_ts_ms.store(now_ms, Ordering::Relaxed);
        if let Ok(mut guard) = self.last_trigger_hash.lock() {
            *guard = Some(item.headline_hash.clone());
        }
        info!(
            severity = item.severity,
            headline_hash = %item.headline_hash,
            ttl_ms = self.halt_ttl_ms,
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

    // ── G6-FUP-NEWS-HALT-DEDUP-1 (2026-04-25): TTL auto-clear tests ──
    // ── G6-FUP-NEWS-HALT-DEDUP-1：TTL 自動清除測試 ──

    /// On fire, last_trigger_ts_ms gets stamped with wall-clock; the per-fire
    /// invariant the TTL check depends on.
    /// 觸發時 last_trigger_ts_ms 會被 wall-clock 時間戳記，TTL 檢查的前置條件。
    #[test]
    fn test_guardian_fire_stamps_trigger_ts() {
        let halted = Arc::new(AtomicBool::new(false));
        let g = GuardianHaltCheckImpl::with_ttl(halted, 1000);
        assert_eq!(g.last_trigger_ts_ms(), 0);
        let item = fixture_item(0.99, "x");
        g.on_high_severity_news(&item);
        assert!(g.last_trigger_ts_ms() > 0, "ts must be stamped on fire");
    }

    /// check_and_clear_expired is a no-op if halt was never fired (ts=0).
    /// 從未觸發時 TTL 檢查為 no-op。
    #[test]
    fn test_check_expiry_no_op_when_never_fired() {
        let halted = Arc::new(AtomicBool::new(false));
        let g = GuardianHaltCheckImpl::with_ttl(halted, 1000);
        assert!(!g.check_and_clear_expired(99_999));
    }

    /// check_and_clear_expired is a no-op if halt atomic is already false
    /// (e.g. cleared via IPC resume_paper).
    /// halt 已被外部清除（IPC resume_paper）時 TTL 檢查為 no-op。
    #[test]
    fn test_check_expiry_no_op_when_atomic_already_false() {
        let halted = Arc::new(AtomicBool::new(false));
        let g = GuardianHaltCheckImpl::with_ttl(Arc::clone(&halted), 100);
        let item = fixture_item(0.99, "x");
        g.on_high_severity_news(&item);
        assert!(halted.load(Ordering::Relaxed));
        // External clear (e.g. IPC).
        halted.store(false, Ordering::Relaxed);
        // Even after TTL elapsed, check_and_clear_expired should not log a
        // spurious "auto-cleared" event.
        let later = g.last_trigger_ts_ms() + 99_999;
        assert!(!g.check_and_clear_expired(later));
    }

    /// check_and_clear_expired is a no-op while inside the TTL window.
    /// TTL 窗口內 check_and_clear_expired 為 no-op。
    #[test]
    fn test_check_expiry_no_op_within_ttl() {
        let halted = Arc::new(AtomicBool::new(false));
        let g = GuardianHaltCheckImpl::with_ttl(Arc::clone(&halted), 1000);
        let item = fixture_item(0.99, "x");
        g.on_high_severity_news(&item);
        let trigger = g.last_trigger_ts_ms();
        // 500ms after fire, still within 1000ms TTL — no clear.
        assert!(!g.check_and_clear_expired(trigger + 500));
        assert!(halted.load(Ordering::Relaxed));
    }

    /// check_and_clear_expired clears the atomic + zeros the trigger ts when
    /// TTL window has elapsed since the last fire.
    /// TTL 過期時 check_and_clear_expired 清除原子並歸零 ts。
    #[test]
    fn test_check_expiry_clears_after_ttl() {
        let halted = Arc::new(AtomicBool::new(false));
        let g = GuardianHaltCheckImpl::with_ttl(Arc::clone(&halted), 1000);
        let item = fixture_item(0.99, "x");
        g.on_high_severity_news(&item);
        let trigger = g.last_trigger_ts_ms();
        assert!(halted.load(Ordering::Relaxed));
        // 1500ms later — past TTL.
        assert!(g.check_and_clear_expired(trigger + 1500));
        assert!(!halted.load(Ordering::Relaxed));
        // ts is reset so next-tick check is a no-op (no double-clear log spam).
        assert_eq!(g.last_trigger_ts_ms(), 0);
        assert!(!g.check_and_clear_expired(trigger + 99_999));
    }

    /// Refire after expiry restamps ts (lifecycle: fire → expire → fire).
    /// 過期後再觸發會重新時間戳記（生命週期：fire → expire → fire）。
    #[test]
    fn test_guardian_refire_after_expiry_restamps_ts() {
        let halted = Arc::new(AtomicBool::new(false));
        let g = GuardianHaltCheckImpl::with_ttl(Arc::clone(&halted), 100);
        let item = fixture_item(0.99, "first");
        g.on_high_severity_news(&item);
        let first_ts = g.last_trigger_ts_ms();
        // Force expiry.
        assert!(g.check_and_clear_expired(first_ts + 200));
        assert_eq!(g.last_trigger_ts_ms(), 0);
        // Fresh fire.
        let item2 = fixture_item(0.99, "second");
        g.on_high_severity_news(&item2);
        let second_ts = g.last_trigger_ts_ms();
        assert!(second_ts >= first_ts, "second fire must restamp ts");
        assert!(halted.load(Ordering::Relaxed));
    }
}
