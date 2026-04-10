//! Per-engine-mode state — paper / demo / live isolation (Phase 3).
//! 每引擎模式獨立狀態 — paper / demo / live 隔離。
//!
//! MODULE_NOTE (EN): Extracted from tick_pipeline.rs to support simultaneous
//!   multi-mode execution (Signal Diamond architecture). Each ModeState owns
//!   the per-mode trading lifecycle: PaperState, IntentProcessor, GovernanceCore,
//!   risk config, consecutive losses, session/pause flags, recent intents/fills.
//!   Shared state (market data, klines, indicators, signals) stays in TickPipeline.
//! MODULE_NOTE (中): 從 tick_pipeline.rs 抽取，以支持多模式同步運行
//!   （Signal Diamond 架構）。每個 ModeState 持有模式獨立的交易生命週期：
//!   PaperState、IntentProcessor、GovernanceCore、風控配置、連虧計數、
//!   暫停標誌、近期意圖/成交。共享狀態留在 TickPipeline。

use crate::config::{ConfigStore, RiskConfig, TradingMode};
use crate::intent_processor::IntentProcessor;
use crate::paper_state::{PaperState, PaperStateSnapshot};
use crate::pipeline_types::{TimestampedFill, TimestampedIntent};
use openclaw_core::governance_core::GovernanceCore;
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet, VecDeque};
use std::sync::Arc;

/// Per-mode trading state — one instance per active engine mode.
/// 每模式交易狀態 — 每個活躍引擎模式一個實例。
pub struct ModeState {
    /// Which mode this state belongs to / 此狀態對應的模式
    pub mode: TradingMode,
    /// Independent paper/simulated state (balance, positions, stops).
    /// 獨立紙盤/模擬狀態（餘額、持倉、止損）。
    pub paper_state: PaperState,
    /// Independent intent processor (guardian, kelly, risk gates, cost gate).
    /// 獨立意圖處理器（守護者、Kelly、風控門、成本門）。
    pub intent_processor: IntentProcessor,
    /// Independent governance core (circuit breaker, risk governor).
    /// 獨立治理核心（熔斷器、風控治理器）。
    pub governance: GovernanceCore,
    /// Per-mode risk config store (PerEngineRiskStores routes here).
    /// 每模式風控配置 store。
    pub risk_store: Option<Arc<ConfigStore<RiskConfig>>>,
    /// Last seen RiskConfig version — sync intent_processor on change.
    /// 上一次見到的 RiskConfig 版本號。
    pub risk_config_version_seen: u64,
    /// Recent intents ring buffer (max 50) / 最近意圖環形緩衝
    pub recent_intents: VecDeque<TimestampedIntent>,
    /// Recent fills ring buffer (max 50) / 最近成交環形緩衝
    pub recent_fills: VecDeque<TimestampedFill>,
    /// Per-symbol consecutive loss counter / 每交易對連虧計數器
    pub consecutive_losses: HashMap<String, u32>,
    /// Session halted by risk circuit breaker / 風控熔斷暫停
    pub session_halted: bool,
    /// Paper trading paused by operator / 紙盤交易被 operator 暫停
    pub paper_paused: bool,
    /// Symbols with pending exchange close orders / 待處理平倉訂單交易對
    pub pending_close_symbols: HashSet<String>,
    /// Sequence counter for unique order_link_id / 唯一訂單 ID 序列號
    pub exchange_seq: u64,
}

impl ModeState {
    /// Create a new ModeState with default configuration.
    /// 使用預設配置創建新的 ModeState。
    pub fn new(mode: TradingMode, balance: f64) -> Self {
        Self {
            mode,
            paper_state: PaperState::new(balance),
            intent_processor: IntentProcessor::new(),
            governance: GovernanceCore::new(),
            risk_store: None,
            risk_config_version_seen: 0,
            recent_intents: VecDeque::new(),
            recent_fills: VecDeque::new(),
            consecutive_losses: HashMap::new(),
            session_halted: false,
            paper_paused: false,
            pending_close_symbols: HashSet::new(),
            exchange_seq: 0,
        }
    }

    /// DB-canonical engine_mode string for this mode.
    /// 此模式的 DB 標準 engine_mode 字串。
    #[inline]
    pub fn db_mode(&self) -> &'static str {
        self.mode.db_mode()
    }

    /// Push a timestamped intent, keeping max 50.
    /// 推入帶時間戳意圖，保留最多 50 個。
    pub fn push_intent(&mut self, intent: TimestampedIntent) {
        self.recent_intents.push_back(intent);
        if self.recent_intents.len() > 50 {
            self.recent_intents.pop_front();
        }
    }

    /// Push a timestamped fill, keeping max 50.
    /// 推入帶時間戳成交，保留最多 50 個。
    pub fn push_fill(&mut self, fill: TimestampedFill) {
        self.recent_fills.push_back(fill);
        if self.recent_fills.len() > 50 {
            self.recent_fills.pop_front();
        }
    }

    /// Check if risk config store version bumped since last sync.
    /// Returns Some(snapshot) if changed, None otherwise.
    /// Caller (TickPipeline) owns the apply logic (complex multi-step).
    /// 檢查 risk config store 版本是否更新。更新則返回 Some(snapshot)，否則 None。
    /// 呼叫方（TickPipeline）負責 apply 邏輯（多步驟複雜操作）。
    pub fn check_risk_config_changed(&mut self) -> Option<crate::config::RiskConfig> {
        let store = self.risk_store.as_ref()?;
        let v = store.version();
        if v == self.risk_config_version_seen {
            return None;
        }
        self.risk_config_version_seen = v;
        Some((*store.load()).clone())
    }

    /// Remove a symbol's cached state (for scanner symbol removal).
    /// 移除交易對的緩存狀態（用於掃描器移除交易對）。
    pub fn remove_symbol(&mut self, symbol: &str) {
        self.consecutive_losses.remove(symbol);
        self.pending_close_symbols.remove(symbol);
    }
}

/// Serializable snapshot of per-mode state for IPC / Phase 4.
/// 每模式狀態的可序列化快照，用於 IPC / Phase 4。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModeStateSnapshot {
    /// Paper/simulated state snapshot / 紙盤/模擬狀態快照
    pub paper_state: PaperStateSnapshot,
    /// Recent intents / 近期意圖
    pub recent_intents: Vec<TimestampedIntent>,
    /// Recent fills / 近期成交
    pub recent_fills: Vec<TimestampedFill>,
    /// Per-symbol consecutive loss counters / 每交易對連虧計數
    pub consecutive_losses: HashMap<String, u32>,
    /// Session halted by circuit breaker / 熔斷暫停
    pub session_halted: bool,
    /// Paper paused by operator / 紙盤暫停
    pub paper_paused: bool,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_mode_state_new_defaults() {
        let ms = ModeState::new(TradingMode::PaperOnly, 10_000.0);
        assert_eq!(ms.mode, TradingMode::PaperOnly);
        assert_eq!(ms.db_mode(), "paper");
        assert!(!ms.session_halted);
        assert!(!ms.paper_paused);
        assert!(ms.recent_intents.is_empty());
        assert!(ms.recent_fills.is_empty());
        assert!(ms.consecutive_losses.is_empty());
    }

    #[test]
    fn test_mode_state_db_mode_variants() {
        assert_eq!(ModeState::new(TradingMode::PaperOnly, 0.0).db_mode(), "paper");
        assert_eq!(ModeState::new(TradingMode::Demo, 0.0).db_mode(), "demo");
        assert_eq!(ModeState::new(TradingMode::Live, 0.0).db_mode(), "live");
    }

    #[test]
    fn test_push_intent_ring_buffer_cap() {
        let mut ms = ModeState::new(TradingMode::PaperOnly, 1000.0);
        for i in 0..60 {
            ms.push_intent(TimestampedIntent {
                timestamp_ms: i,
                intent: crate::intent_processor::OrderIntent {
                    symbol: "BTC".into(),
                    is_long: true,
                    qty: 0.1,
                    strategy: "test".into(),
                    order_type: "market".into(),
                    confidence: 0.5,
                    limit_price: None,
                },
                result: "ok".into(),
            });
        }
        assert_eq!(ms.recent_intents.len(), 50);
        // Oldest should be i=10
        assert_eq!(ms.recent_intents.front().unwrap().timestamp_ms, 10);
    }

    #[test]
    fn test_push_fill_ring_buffer_cap() {
        let mut ms = ModeState::new(TradingMode::PaperOnly, 1000.0);
        for i in 0..60 {
            ms.push_fill(TimestampedFill {
                timestamp_ms: i,
                symbol: "BTC".into(),
                is_long: true,
                qty: 0.1,
                price: 50000.0,
                fee: 0.01,
                strategy: "test".into(),
            });
        }
        assert_eq!(ms.recent_fills.len(), 50);
        assert_eq!(ms.recent_fills.front().unwrap().timestamp_ms, 10);
    }

    #[test]
    fn test_remove_symbol() {
        let mut ms = ModeState::new(TradingMode::PaperOnly, 1000.0);
        ms.consecutive_losses.insert("BTC".into(), 3);
        ms.pending_close_symbols.insert("BTC".into());
        ms.remove_symbol("BTC");
        assert!(!ms.consecutive_losses.contains_key("BTC"));
        assert!(!ms.pending_close_symbols.contains("BTC"));
    }
}
