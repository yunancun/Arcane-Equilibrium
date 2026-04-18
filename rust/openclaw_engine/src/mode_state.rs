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

use crate::bybit_rest_client::BybitEnvironment;
use crate::config::{ConfigStore, RiskConfig};
use crate::intent_processor::IntentProcessor;
use crate::paper_state::{PaperState, PaperStateSnapshot};
use crate::pipeline_types::{TimestampedFill, TimestampedIntent};
use crate::tick_pipeline::PipelineKind;
use openclaw_core::governance_core::{GovernanceCore, GovernanceProfile};
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet, VecDeque};
use std::sync::Arc;

/// Endpoint-aware DB engine_mode tag — reflects the *real* Bybit endpoint the
/// pipeline is bound to, not just the PipelineKind abstraction.
///
/// Live + LiveDemo collapses to `"live_demo"` so the operator and downstream
/// readers can tell "Live pipeline against demo endpoint" apart from "real
/// mainnet live". Without this distinction the engine_mode tag flagged ~952k
/// historical demo-endpoint rows as `"live"`, masking the fact that no live-net
/// order had ever been placed. Keep `Live + Mainnet → "live"` untouched so the
/// real-money semantic survives.
///
/// 端點感知的 engine_mode 標籤：反映管線真實綁定的 Bybit 端點，而不僅是
/// PipelineKind 抽象。Live + LiveDemo 折疊為 `"live_demo"`，讓 operator 與
/// 下游讀者能分辨「Live pipeline 連 demo」與「真正 mainnet live」。
pub fn effective_engine_mode(kind: PipelineKind, env: Option<BybitEnvironment>) -> &'static str {
    match (kind, env) {
        (PipelineKind::Paper, _) => "paper",
        (PipelineKind::Demo, _) => "demo",
        (PipelineKind::Live, Some(BybitEnvironment::Mainnet)) => "live",
        (PipelineKind::Live, Some(BybitEnvironment::Testnet)) => "live_testnet",
        // Live + LiveDemo, Live + Demo, and Live + None all resolve to
        // live_demo — all three are demo-endpoint traffic under a Live
        // PipelineKind. `None` is defensive for pre-wire construction paths
        // (tests, cold start). Cost-gate profile for these is Validation
        // (not Production) — see `effective_governance_profile`.
        // Live + LiveDemo/Demo/None：三者皆為 demo 端點的 Live 流量。
        // None 為構造期防禦性 fallback。Cost-gate profile 採 Validation，
        // 見 `effective_governance_profile`。
        (PipelineKind::Live, _) => "live_demo",
    }
}

/// Endpoint-aware GovernanceProfile for **per-intent cost-gate selection**.
///
/// P0-6 方案 A (2026-04-17): the cost gate must distinguish "Live pipeline
/// against demo endpoint" (LiveDemo — play money, exploratory) from "real
/// mainnet Live" (production — fail-closed without positive edge estimate).
/// Without this split, LiveDemo hit `cost_gate(JS-live): no edge estimate —
/// fail-closed (cold-start)` on every intent, producing 0 fills → 0 edge
/// data → permanent cold-start deadlock (P0-6 RCA 2026-04-17).
///
/// Mapping:
///   * `Paper`                     → `Exploration`
///   * `Demo`                      → `Validation`
///   * `Live + Mainnet`            → `Production` (real money, strict)
///   * `Live + Testnet`            → `Validation` (not real money)
///   * `Live + LiveDemo/Demo/None` → `Validation` (demo endpoint, cold-start allowed)
///
/// **Scope**: only used by `IntentProcessor::process_*` for cost-gate tier
/// selection. Does NOT override the construction-time profile passed to
/// `GovernanceCore::new_with_profile()` — Auth/Lease semantics for the Live
/// pipeline remain unchanged (Python Operator auth still required for
/// real-live traffic).
///
/// P0-6 方案 A：cost gate 必須區分「Live 管線連 demo 端點（LiveDemo，
/// 假錢探索）」與「真 mainnet Live（真錢，無正向估計即 fail-closed）」。
/// 未區分前 LiveDemo 每筆 intent 都撞 cold-start fail-closed → 永久死循環。
/// 僅用於 IntentProcessor cost gate 分層；GovernanceCore 構造時的 profile
/// 保持原樣（Live 管線仍需 Python Operator 授權）。
pub fn effective_governance_profile(
    kind: PipelineKind,
    env: Option<BybitEnvironment>,
) -> GovernanceProfile {
    match (kind, env) {
        (PipelineKind::Paper, _) => GovernanceProfile::Exploration,
        (PipelineKind::Demo, _) => GovernanceProfile::Validation,
        (PipelineKind::Live, Some(BybitEnvironment::Mainnet)) => GovernanceProfile::Production,
        // Live + non-Mainnet = demo-endpoint traffic; treat as Validation so
        // the moderate cost gate (cold-start allowed) runs instead of the
        // strict live gate. Matches `effective_engine_mode` == "live_demo"
        // / "live_testnet". `None` is defensive for pre-wire paths.
        // Live + 非 Mainnet = demo 端點流量；套 Validation 啟用 cold-start
        // 允許的 moderate cost gate。對齊 engine_mode 標籤 "live_demo"。
        (PipelineKind::Live, _) => GovernanceProfile::Validation,
    }
}

/// Per-mode trading state — one instance per active engine mode.
/// 每模式交易狀態 — 每個活躍引擎模式一個實例。
pub struct ModeState {
    /// Which pipeline this state belongs to / 此狀態對應的管線
    pub mode: PipelineKind,
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
    pub fn new(mode: PipelineKind, balance: f64) -> Self {
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

    /// DB-canonical engine_mode string for this pipeline.
    /// 此管線的 DB 標準 engine_mode 字串。
    #[inline]
    pub fn db_mode(&self) -> &'static str {
        self.mode.db_mode()
    }

    /// Push a timestamped intent, keeping max 50.
    /// 推入帶時間戳意圖，保留最多 50 個。
    pub fn push_intent(&mut self, intent: TimestampedIntent) {
        crate::tick_pipeline::on_tick_helpers::push_capped(&mut self.recent_intents, intent, 50);
    }

    /// Push a timestamped fill, keeping max 50.
    /// 推入帶時間戳成交，保留最多 50 個。
    pub fn push_fill(&mut self, fill: TimestampedFill) {
        crate::tick_pipeline::on_tick_helpers::push_capped(&mut self.recent_fills, fill, 50);
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
        let ms = ModeState::new(PipelineKind::Paper, 10_000.0);
        assert_eq!(ms.mode, PipelineKind::Paper);
        assert_eq!(ms.db_mode(), "paper");
        assert!(!ms.session_halted);
        assert!(!ms.paper_paused);
        assert!(ms.recent_intents.is_empty());
        assert!(ms.recent_fills.is_empty());
        assert!(ms.consecutive_losses.is_empty());
    }

    #[test]
    fn test_mode_state_db_mode_variants() {
        assert_eq!(ModeState::new(PipelineKind::Paper, 0.0).db_mode(), "paper");
        assert_eq!(ModeState::new(PipelineKind::Demo, 0.0).db_mode(), "demo");
        assert_eq!(ModeState::new(PipelineKind::Live, 0.0).db_mode(), "live");
    }

    #[test]
    fn test_effective_engine_mode_tagging() {
        // Paper / Demo ignore endpoint / Paper / Demo 不受端點影響
        assert_eq!(effective_engine_mode(PipelineKind::Paper, None), "paper");
        assert_eq!(
            effective_engine_mode(PipelineKind::Paper, Some(BybitEnvironment::Mainnet)),
            "paper"
        );
        assert_eq!(effective_engine_mode(PipelineKind::Demo, None), "demo");
        assert_eq!(
            effective_engine_mode(PipelineKind::Demo, Some(BybitEnvironment::Demo)),
            "demo"
        );
        // Live + Mainnet = real money — keep "live" untouched
        // Live + Mainnet = 真錢 — "live" 語義保留
        assert_eq!(
            effective_engine_mode(PipelineKind::Live, Some(BybitEnvironment::Mainnet)),
            "live"
        );
        // Live + LiveDemo/Demo/None = demo-endpoint Live pipeline = live_demo
        // Live + LiveDemo/Demo/None = demo 端點的 Live 管線 = live_demo
        assert_eq!(
            effective_engine_mode(PipelineKind::Live, Some(BybitEnvironment::LiveDemo)),
            "live_demo"
        );
        assert_eq!(
            effective_engine_mode(PipelineKind::Live, Some(BybitEnvironment::Demo)),
            "live_demo"
        );
        assert_eq!(effective_engine_mode(PipelineKind::Live, None), "live_demo");
        // Live + Testnet = live_testnet (defensive; not currently wired)
        // Live + Testnet = live_testnet（防禦性，目前未使用）
        assert_eq!(
            effective_engine_mode(PipelineKind::Live, Some(BybitEnvironment::Testnet)),
            "live_testnet"
        );
    }

    #[test]
    fn test_effective_governance_profile_p0_6_mapping() {
        // Paper / Demo — trivial mapping / 簡單映射
        assert_eq!(
            effective_governance_profile(PipelineKind::Paper, None),
            GovernanceProfile::Exploration
        );
        assert_eq!(
            effective_governance_profile(PipelineKind::Paper, Some(BybitEnvironment::Mainnet)),
            GovernanceProfile::Exploration
        );
        assert_eq!(
            effective_governance_profile(PipelineKind::Demo, None),
            GovernanceProfile::Validation
        );
        assert_eq!(
            effective_governance_profile(PipelineKind::Demo, Some(BybitEnvironment::Demo)),
            GovernanceProfile::Validation
        );

        // Live + Mainnet = real money = strict Production cost gate.
        // Live + Mainnet = 真錢 = 嚴格 Production cost gate。
        assert_eq!(
            effective_governance_profile(PipelineKind::Live, Some(BybitEnvironment::Mainnet)),
            GovernanceProfile::Production
        );

        // P0-6 crux: Live + LiveDemo/Demo/Testnet/None must collapse to
        // Validation so `cost_gate_moderate` runs (cold-start allowed).
        // Production would invoke `cost_gate_live` which fail-closes on the
        // cold-start path when `edge_estimates.json` is empty.
        // P0-6 關鍵：Live + LiveDemo 等必須折疊到 Validation，讓
        // `cost_gate_moderate` 執行（允許 cold-start）。
        assert_eq!(
            effective_governance_profile(PipelineKind::Live, Some(BybitEnvironment::LiveDemo)),
            GovernanceProfile::Validation,
            "LiveDemo must map to Validation (P0-6 cold-start deadlock fix)"
        );
        assert_eq!(
            effective_governance_profile(PipelineKind::Live, Some(BybitEnvironment::Demo)),
            GovernanceProfile::Validation
        );
        assert_eq!(
            effective_governance_profile(PipelineKind::Live, Some(BybitEnvironment::Testnet)),
            GovernanceProfile::Validation
        );
        assert_eq!(
            effective_governance_profile(PipelineKind::Live, None),
            GovernanceProfile::Validation,
            "None endpoint (pre-wire) must default to Validation, not Production"
        );
    }

    #[test]
    fn test_effective_governance_profile_parity_with_engine_mode() {
        // Any (kind, env) tagged "live" must map to Production; any tagged
        // other than "live" must NOT map to Production. Prevents future
        // drift between the engine-mode string and the cost-gate profile.
        // 任何 engine_mode="live" 的組合必須是 Production；否則不得是
        // Production。防止 tag 與 cost gate profile 漂移。
        for kind in [PipelineKind::Paper, PipelineKind::Demo, PipelineKind::Live] {
            for env in [
                None,
                Some(BybitEnvironment::Mainnet),
                Some(BybitEnvironment::Demo),
                Some(BybitEnvironment::LiveDemo),
                Some(BybitEnvironment::Testnet),
            ] {
                let mode = effective_engine_mode(kind, env);
                let profile = effective_governance_profile(kind, env);
                if mode == "live" {
                    assert_eq!(
                        profile,
                        GovernanceProfile::Production,
                        "engine_mode=live must map to Production for (kind={:?}, env={:?})",
                        kind,
                        env
                    );
                } else {
                    assert_ne!(
                        profile,
                        GovernanceProfile::Production,
                        "engine_mode={} must NOT map to Production for (kind={:?}, env={:?})",
                        mode,
                        kind,
                        env
                    );
                }
            }
        }
    }

    #[test]
    fn test_push_intent_ring_buffer_cap() {
        let mut ms = ModeState::new(PipelineKind::Paper, 1000.0);
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
                    confluence_score: None,
                    persistence_elapsed_ms: None,
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
        let mut ms = ModeState::new(PipelineKind::Paper, 1000.0);
        for i in 0..60 {
            ms.push_fill(TimestampedFill {
                timestamp_ms: i,
                symbol: "BTC".into(),
                is_long: true,
                qty: 0.1,
                price: 50000.0,
                fee: 0.01,
                realized_pnl: 0.0,
                strategy: "test".into(),
            });
        }
        assert_eq!(ms.recent_fills.len(), 50);
        assert_eq!(ms.recent_fills.front().unwrap().timestamp_ms, 10);
    }

    #[test]
    fn test_remove_symbol() {
        let mut ms = ModeState::new(PipelineKind::Paper, 1000.0);
        ms.consecutive_losses.insert("BTC".into(), 3);
        ms.pending_close_symbols.insert("BTC".into());
        ms.remove_symbol("BTC");
        assert!(!ms.consecutive_losses.contains_key("BTC"));
        assert!(!ms.pending_close_symbols.contains("BTC"));
    }
}
