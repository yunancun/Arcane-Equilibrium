//! Production GovernanceCheck wrapper around shared atomics (Phase 4 W-1).
//! 生產環境 GovernanceCheck wrapper，包共享 atomics（Phase 4 W-1）。
//!
//! MODULE_NOTE (EN):
//!   Implements the `GovernanceCheck` trait by reading state from atomic
//!   snapshots that the live tick pipeline keeps refreshed. The Rust
//!   `GovernanceCore` does not directly expose `session_halted` or daily
//!   loss percentage as getters, so this wrapper owns shared
//!   `Arc<AtomicBool>` + `Arc<AtomicU64>` (loss * 1e6 representation) and
//!   exposes setter methods that the pipeline calls each tick.
//!
//!   The same `Arc<AtomicBool>` is shared with `news::guardian_impl` so a
//!   high-severity news halt is immediately visible to the Teacher
//!   `DirectiveApplier` (single source of truth, no double-write).
//!
//! MODULE_NOTE (中):
//!   實作 `GovernanceCheck` trait — 從 live tick pipeline 持續刷新的原子
//!   快照讀狀態。Rust `GovernanceCore` 不直接暴露 `session_halted` 或日虧
//!   getter，因此本 wrapper 持有共享的 `Arc<AtomicBool>` + `Arc<AtomicU64>`
//!   （loss × 1e6 表示），並暴露 pipeline 每 tick 呼叫的 setter。
//!
//!   同一個 `Arc<AtomicBool>` 與 `news::guardian_impl` 共享，使高 severity
//!   新聞 halt 對 Teacher `DirectiveApplier` 立即可見（單一真相源，無雙寫）。

use crate::claude_teacher::applier::GovernanceCheck;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;

/// EN: Live wrapper providing GovernanceCheck via atomic snapshots.
/// 中文: 透過原子快照提供 GovernanceCheck 的 live wrapper。
pub struct GovernanceCoreWrapper {
    /// EN: Shared session_halted flag (also held by news::guardian_impl).
    /// 中文: 共享 session_halted 旗標（news::guardian_impl 也持有）。
    session_halted: Arc<AtomicBool>,
    /// EN: Daily loss percentage × 1e6 (atomic-safe int representation, signed).
    /// 中文: 日虧百分比 × 1e6（原子安全的有號整數表示）。
    daily_loss_pct_micro: Arc<AtomicU64>,
    /// EN: Threshold above which unpause directives are rejected.
    /// 中文: 拒絕 unpause directive 的門檻。
    unpause_threshold: f64,
    /// EN: Known strategy names (immutable after construction).
    /// 中文: 已知策略名（構造後不可變）。
    known_strategies: Vec<String>,
}

impl GovernanceCoreWrapper {
    /// EN: Construct with explicit shared atomics.
    /// 中文: 用顯式共享 atomics 構造。
    pub fn new(
        session_halted: Arc<AtomicBool>,
        daily_loss_pct_micro: Arc<AtomicU64>,
        unpause_threshold: f64,
        known_strategies: Vec<String>,
    ) -> Self {
        Self {
            session_halted,
            daily_loss_pct_micro,
            unpause_threshold,
            known_strategies,
        }
    }

    /// EN: Convenience constructor with fresh atomics — the caller can fetch
    ///     the shared handles via `halted_handle()` / `daily_loss_handle()`
    ///     to share with `news::guardian_impl`.
    /// 中文: 帶全新 atomics 的便利建構子 — caller 可透過 `halted_handle()` /
    ///       `daily_loss_handle()` 取得共享句柄與 `news::guardian_impl` 共享。
    pub fn with_defaults(known_strategies: Vec<String>) -> Self {
        Self::new(
            Arc::new(AtomicBool::new(false)),
            Arc::new(AtomicU64::new(0)),
            0.05, // 5% daily loss unpause threshold (matches RiskManagerConfig default)
            known_strategies,
        )
    }

    /// EN: Set daily loss percentage (called by pipeline tick).
    /// 中文: 設定日虧百分比（pipeline tick 呼叫）。
    pub fn set_daily_loss_pct(&self, pct: f64) {
        // Clamp to [-1, 1] then encode as signed micro-pct stored in u64 bits.
        // 鉗制到 [-1, 1] 然後編碼為 u64 bits 表示的有號 micro-pct。
        let clamped = pct.clamp(-1.0, 1.0);
        let micro_signed: i64 = (clamped * 1_000_000.0) as i64;
        self.daily_loss_pct_micro
            .store(micro_signed as u64, Ordering::Relaxed);
    }

    /// EN: Set session_halted flag.
    /// 中文: 設定 session_halted 旗標。
    pub fn set_session_halted(&self, halted: bool) {
        self.session_halted.store(halted, Ordering::Relaxed);
    }

    /// EN: Borrow shared `session_halted` handle for cross-module sharing.
    /// 中文: 借出共享 `session_halted` 句柄供跨模組共享。
    pub fn halted_handle(&self) -> Arc<AtomicBool> {
        Arc::clone(&self.session_halted)
    }

    /// EN: Borrow shared `daily_loss_pct_micro` handle.
    /// 中文: 借出共享 `daily_loss_pct_micro` 句柄。
    pub fn daily_loss_handle(&self) -> Arc<AtomicU64> {
        Arc::clone(&self.daily_loss_pct_micro)
    }
}

impl GovernanceCheck for GovernanceCoreWrapper {
    fn current_daily_loss_pct(&self) -> f64 {
        let bits = self.daily_loss_pct_micro.load(Ordering::Relaxed);
        let micro_signed = bits as i64;
        (micro_signed as f64) / 1_000_000.0
    }

    fn session_halted(&self) -> bool {
        self.session_halted.load(Ordering::Relaxed)
    }

    fn unpause_daily_loss_threshold(&self) -> f64 {
        self.unpause_threshold
    }

    fn known_strategies(&self) -> Vec<String> {
        self.known_strategies.clone()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn known() -> Vec<String> {
        vec![
            "ma_crossover".to_string(),
            "bb_breakout".to_string(),
            "bb_reversion".to_string(),
        ]
    }

    #[test]
    fn test_default_session_not_halted() {
        let w = GovernanceCoreWrapper::with_defaults(known());
        assert!(!w.session_halted());
    }

    #[test]
    fn test_set_session_halted_reflects() {
        let w = GovernanceCoreWrapper::with_defaults(known());
        w.set_session_halted(true);
        assert!(w.session_halted());
        w.set_session_halted(false);
        assert!(!w.session_halted());
    }

    #[test]
    fn test_daily_loss_pct_round_trip_positive() {
        let w = GovernanceCoreWrapper::with_defaults(known());
        w.set_daily_loss_pct(0.03);
        assert!((w.current_daily_loss_pct() - 0.03).abs() < 1e-6);
    }

    #[test]
    fn test_daily_loss_pct_round_trip_negative() {
        let w = GovernanceCoreWrapper::with_defaults(known());
        w.set_daily_loss_pct(-0.04);
        assert!((w.current_daily_loss_pct() - (-0.04)).abs() < 1e-6);
    }

    #[test]
    fn test_daily_loss_pct_clamped_to_one() {
        let w = GovernanceCoreWrapper::with_defaults(known());
        w.set_daily_loss_pct(5.0);
        assert!((w.current_daily_loss_pct() - 1.0).abs() < 1e-6);
    }

    #[test]
    fn test_daily_loss_pct_clamped_to_neg_one() {
        let w = GovernanceCoreWrapper::with_defaults(known());
        w.set_daily_loss_pct(-5.0);
        assert!((w.current_daily_loss_pct() - (-1.0)).abs() < 1e-6);
    }

    #[test]
    fn test_unpause_threshold_returned() {
        let w = GovernanceCoreWrapper::with_defaults(known());
        assert!((w.unpause_daily_loss_threshold() - 0.05).abs() < 1e-9);
    }

    #[test]
    fn test_known_strategies_returned_as_clone() {
        let w = GovernanceCoreWrapper::with_defaults(known());
        let s = w.known_strategies();
        assert_eq!(s.len(), 3);
        assert!(s.contains(&"ma_crossover".to_string()));
    }

    #[test]
    fn test_shared_halted_handle_visible_to_other_holder() {
        let w = GovernanceCoreWrapper::with_defaults(known());
        let other = w.halted_handle();
        assert!(!other.load(Ordering::Relaxed));
        // Flip the shared atomic from outside the wrapper.
        // 從 wrapper 外部翻轉共享原子。
        other.store(true, Ordering::Relaxed);
        assert!(w.session_halted());
    }
}
