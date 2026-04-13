//! P2 refactor (2026-04-07): DecisionContextMsg producer extracted from
//! tick_pipeline.rs to keep that file under the §九 1200-line hard limit.
//!
//! P2 重構（2026-04-07）：將 DecisionContextMsg producer 從 tick_pipeline.rs
//! 抽出，使該檔保持在 §九 1200 行硬上限以下。
//!
//! MODULE_NOTE (EN): This module owns the read-only side of the
//!   `learning.decision_context_snapshots` write path. The producer:
//!     1. Maps the strategy whitelist (signal rule → v1_15 strategy name)
//!        and consults the LinUCB runtime for an arm + UCB (metadata only).
//!     2. Reads the news context snapshot (severity + hours since major).
//!     3. Constructs a `DecisionContextMsg` with all 25 columns and
//!        try_sends it down the channel (drop-on-full = back-pressure).
//!   The function takes only immutable refs / Option refs and never mutates
//!   pipeline state, so it is trivially testable in isolation and the
//!   compiler enforces "no hot-path borrow upgrades".
//! MODULE_NOTE (中)：本模組擁有 `learning.decision_context_snapshots`
//!   寫路徑的「唯讀生產端」。Producer 做三件事：
//!     1. 套用策略白名單（signal rule → v1_15 strategy 名）並向 LinUCB
//!        runtime 請求 arm + UCB（純 metadata，不影響交易）。
//!     2. 讀取新聞 context 快照（severity + hours since major）。
//!     3. 構造 25 欄位的 `DecisionContextMsg` 並 try_send 到通道
//!        （滿則丟棄 = back-pressure）。
//!   函數只接受 immutable refs / Option refs、絕不變動 pipeline state，
//!   因此可獨立測試，且編譯器會擋住任何 hot-path borrow 升級。

use crate::database::DecisionContextMsg;
use crate::linucb::LinUcbRuntime;
use crate::news::NewsContextSnapshot;
use crate::paper_state::PaperPosition;
use openclaw_core::indicators::IndicatorSnapshot;
use openclaw_core::signals::Signal;
use openclaw_types::PriceEvent;
use std::sync::Arc;
use tokio::sync::mpsc::Sender;

/// Build LinUCB arm metadata via the static signal-rule → strategy whitelist.
/// Returns `(arm_id, ucb)` or `(None, None)` if the signal rule does not map.
///
/// Whitelist (HOTFIX 2026-04-07 — see tick_pipeline.rs commit `83a9dc7`):
/// `signal.source` is a signal RULE name (rsi_exit / ma_crossover /
/// bollinger_reversion / ...), NOT a v1_15 strategy name. We map conservatively
/// — only signals that clearly belong to one of the 5 registered strategies are
/// mapped; everything else returns None and the arm column is NULL.
///
/// 透過靜態 signal rule → strategy 白名單建構 LinUCB arm metadata。
/// 未映射的 signal rule 回 `(None, None)`。
fn select_linucb_arm(
    rt: &Arc<LinUcbRuntime>,
    signal_source: &str,
    indicators: Option<&IndicatorSnapshot>,
    ts_ms: i64,
) -> (Option<String>, Option<f64>) {
    let mapped_strategy: Option<&'static str> = match signal_source {
        // ma_crossover strategy
        "ma_crossover" => Some("ma_crossover"),
        // bb_reversion strategy
        "bollinger_reversion" => Some("bb_reversion"),
        // bb_breakout / grid_trading / funding_arb have no unique signal rule
        // and are driven via ticks/REST → conservatively None.
        // bb_breakout / grid_trading / funding_arb 沒有專屬 signal rule，
        // 由 tick/REST 驅動 → 保守回 None。
        _ => None,
    };
    let strategy = match mapped_strategy {
        Some(s) => s,
        None => return (None, None),
    };
    let regime = indicators
        .and_then(|i| i.hurst.as_ref())
        .map(|h| h.regime.clone())
        .unwrap_or_else(|| "random_walk".to_string());
    let ctx = LinUcbRuntime::build_context_features(
        indicators.and_then(|i| i.atr_14.as_ref()).map(|a| a.atr_percent),
        indicators.and_then(|i| i.rsi_14),
        indicators.and_then(|i| i.bollinger.as_ref()).map(|b| b.bandwidth),
        indicators.and_then(|i| i.hurst.as_ref()).map(|h| h.hurst),
        indicators.and_then(|i| i.adx.as_ref()).map(|a| a.adx),
        None, // vol_ratio not available in IndicatorSnapshot
        ts_ms,
    );
    match rt.select_for_intent(&regime, strategy, &ctx) {
        Some(sel) => (Some(sel.arm_id), Some(sel.ucb)),
        None => {
            tracing::debug!(
                regime = %regime,
                strategy = %strategy,
                "linucb arm not found despite whitelist, emitting NULL / 白名單已映射但 arm 找不到"
            );
            (None, None)
        }
    }
}

/// Read the latest news severity + hours-since-major from the snapshot.
/// 從新聞快照讀取最新 severity + hours-since-major。
fn read_news_context(
    snap: Option<&Arc<NewsContextSnapshot>>,
    ts_ms: i64,
) -> (Option<f32>, Option<f64>) {
    let snap = match snap {
        Some(s) => s,
        None => return (None, None),
    };
    let sev = snap.latest_severity();
    let sev_opt = if sev > 0.0 { Some(sev) } else { None };
    let hours = snap.hours_since_last_major(ts_ms);
    (sev_opt, hours)
}

/// Construct + try_send a `DecisionContextMsg`. Pure function — never mutates
/// pipeline state, never blocks (drop-on-full back-pressure semantics).
///
/// Caller responsibility: gate this on the DB-RUN-2 piggyback rule (only fire
/// when at least one signal was actually persisted this tick).
///
/// 構造並 try_send `DecisionContextMsg`。純函數 — 不變動 pipeline 狀態、
/// 不阻塞（滿則丟棄）。呼叫方需負責 DB-RUN-2 piggyback 條件
/// （僅在當 tick 實際 persist 至少一個 signal 時觸發）。
#[allow(clippy::too_many_arguments)]
pub(crate) fn emit_decision_context(
    tx: &Sender<DecisionContextMsg>,
    event: &PriceEvent,
    signals: &[Signal],
    indicators: Option<&IndicatorSnapshot>,
    pos: Option<&PaperPosition>,
    total_equity: f64,
    drawdown_pct: f64,
    linucb: Option<&Arc<LinUcbRuntime>>,
    news_snapshot: Option<&Arc<NewsContextSnapshot>>,
    engine_mode: &str,
) {
    let (linucb_arm_id, linucb_confidence_bound) = match linucb {
        Some(rt) => select_linucb_arm(rt, &signals[0].source, indicators, event.ts_ms as i64),
        None => (None, None),
    };
    let (news_severity, hours_since_last_major_news) =
        read_news_context(news_snapshot, event.ts_ms as i64);

    let _ = tx.try_send(DecisionContextMsg {
        context_id: crate::tick_pipeline::on_tick_helpers::make_context_id(engine_mode, &event.symbol, event.ts_ms),
        ts_ms: event.ts_ms,
        decision_type: "signal_generated".into(),
        symbol: event.symbol.clone(),
        strategy_name: signals[0].source.clone(),
        last_price: event.last_price,
        spread_bps: if event.ask_price > 0.0 && event.bid_price > 0.0 {
            (event.ask_price - event.bid_price) / event.last_price * 10_000.0
        } else {
            0.0
        },
        regime_5m: indicators
            .and_then(|i| i.hurst.as_ref())
            .map(|h| h.regime.clone())
            .unwrap_or_default(),
        ind_5m_adx: indicators
            .and_then(|i| i.adx.as_ref())
            .map(|a| a.adx)
            .unwrap_or(0.0),
        ind_5m_rsi: indicators.and_then(|i| i.rsi_14).unwrap_or(50.0),
        ind_5m_atr_14_pct: indicators
            .and_then(|i| i.atr_14.as_ref())
            .map(|a| a.atr_percent)
            .unwrap_or(0.0),
        position_side: pos
            .map(|p| if p.is_long { "Long" } else { "Short" })
            .unwrap_or("None")
            .into(),
        position_qty: pos.map(|p| p.qty).unwrap_or(0.0),
        total_equity,
        drawdown_pct,
        indicators_snapshot: indicators
            .map(|i| serde_json::to_value(i).unwrap_or_default())
            .unwrap_or_default(),
        position_detail: pos
            .map(|p| serde_json::to_value(p).unwrap_or_default())
            .unwrap_or_default(),
        decision_payload: serde_json::to_value(signals).unwrap_or_default(),
        // Phase 4 / V009 columns. claude_directive_id stays NULL until a
        // future directive→tick association path is built.
        // Phase 4 / V009 欄位。claude_directive_id 待未來 directive→tick
        // 關聯路徑建立後接通。
        claude_directive_id: None,
        linucb_arm_id,
        linucb_confidence_bound,
        news_severity,
        hours_since_last_major_news,
        engine_mode: engine_mode.to_string(),
    });
}

// ---------------------------------------------------------------------------
// Tests / 測試
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use openclaw_core::signals::{Signal, SignalDirection};
    use tokio::sync::mpsc;

    fn mk_event(symbol: &str, ts_ms: u64) -> PriceEvent {
        PriceEvent {
            symbol: symbol.into(),
            last_price: 100.0,
            volume_24h: 0.0,
            turnover_24h: 0.0,
            bid_price: 99.5,
            ask_price: 100.5,
            ts_ms,
            event_kind: None,
            trade_side: None,
            trade_qty: None,
            bids5: None,
            asks5: None,
            adl_rank: None,
            funding_rate: None,
            metadata: Default::default(),
        }
    }

    fn mk_signal(symbol: &str, source: &str, ts_ms: u64) -> Signal {
        Signal {
            symbol: symbol.into(),
            source: source.into(),
            direction: SignalDirection::Long,
            confidence: 0.7,
            edge_bps: 5.0,
            ts_ms,
            timeframe: "5m".into(),
            reasoning: "test".into(),
        }
    }

    /// `read_news_context` with no snapshot → (None, None).
    /// 無快照 → (None, None)。
    #[test]
    fn test_read_news_context_no_snapshot() {
        let (sev, hours) = read_news_context(None, 1_000);
        assert!(sev.is_none() && hours.is_none());
    }

    /// `read_news_context` with empty snapshot → severity is None (0.0 filtered).
    /// 空快照 → severity 為 None（0.0 被過濾）。
    #[test]
    fn test_read_news_context_empty_snapshot() {
        let snap = Arc::new(NewsContextSnapshot::new());
        let (sev, _hours) = read_news_context(Some(&snap), 1_000);
        assert!(sev.is_none(), "fresh snapshot has 0.0 severity → filtered to None");
    }

    /// `select_linucb_arm` with unmapped signal rule → (None, None).
    /// 未映射 signal rule → (None, None)。
    #[test]
    fn test_select_linucb_arm_unmapped_rule() {
        let rt = Arc::new(LinUcbRuntime::cold_start_v1_15());
        let (arm, ucb) = select_linucb_arm(&rt, "rsi_exit", None, 1_000);
        assert!(arm.is_none() && ucb.is_none());
    }

    /// `select_linucb_arm` with mapped rule (ma_crossover) → Some(arm).
    /// 已映射 rule → Some(arm)。
    #[test]
    fn test_select_linucb_arm_mapped_rule() {
        let rt = Arc::new(LinUcbRuntime::cold_start_v1_15());
        let (arm, ucb) = select_linucb_arm(&rt, "ma_crossover", None, 1_000);
        assert!(arm.is_some(), "ma_crossover must map to an arm");
        assert!(ucb.is_some());
    }

    /// `emit_decision_context` happy path: msg lands on the channel with
    /// expected fields populated.
    /// happy path：msg 到 channel 且欄位填好。
    #[tokio::test]
    async fn test_emit_decision_context_happy_path() {
        let (tx, mut rx) = mpsc::channel(8);
        let event = mk_event("BTCUSDT", 5_000);
        let signals = vec![mk_signal("BTCUSDT", "ma_crossover", 5_000)];
        emit_decision_context(
            &tx, &event, &signals, None, None, 10_000.0, 0.0, None, None, "paper",
        );
        let msg = rx.try_recv().expect("msg should land");
        assert_eq!(msg.symbol, "BTCUSDT");
        assert_eq!(msg.strategy_name, "ma_crossover");
        assert_eq!(msg.total_equity, 10_000.0);
        assert_eq!(msg.engine_mode, "paper");
        assert!(msg.linucb_arm_id.is_none(), "no linucb runtime → NULL");
        assert!(msg.news_severity.is_none(), "no news snapshot → NULL");
    }

    /// Drop-on-full: emit_decision_context never blocks even when receiver is gone.
    /// 滿則丟棄：receiver 已關時 emit 也不阻塞。
    #[tokio::test]
    async fn test_emit_decision_context_drop_on_closed_receiver() {
        let (tx, rx) = mpsc::channel(1);
        drop(rx);
        let event = mk_event("ETHUSDT", 6_000);
        let signals = vec![mk_signal("ETHUSDT", "ma_crossover", 6_000)];
        // Should not panic, just silently drop.
        emit_decision_context(
            &tx, &event, &signals, None, None, 10_000.0, 0.0, None, None, "paper",
        );
    }
}
