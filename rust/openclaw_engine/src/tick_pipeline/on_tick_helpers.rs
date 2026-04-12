//! FIX-29: Extracted helper methods for on_tick — keeps on_tick.rs under §九 1200-line hard limit.
//! FIX-29：on_tick 抽出的輔助方法 — 讓 on_tick.rs 保持在 §九 1200 行硬上限以下。

use super::*;
use std::collections::VecDeque;

// ── S-01: Confidence clamp helper — replaces inline .clamp(0.0, 1.0) across strategies ──
// S-01：信心值鉗位工具 — 替代策略中分散的 .clamp(0.0, 1.0) 調用。
#[inline]
pub(crate) fn clamp_confidence(raw: f64) -> f64 {
    raw.clamp(0.0, 1.0)
}

// ── S-02: Ring buffer push helper — replaces 9+ inline len>cap/pop_front patterns ──
// S-02：環形緩衝推入工具 — 替代 9+ 處內聯 len>cap/pop_front 模式。
#[inline]
pub(crate) fn push_capped<T>(buf: &mut VecDeque<T>, item: T, cap: usize) {
    buf.push_back(item);
    if buf.len() > cap {
        buf.pop_front();
    }
}

// ── S-03: ID factory functions — replaces 12+ inline format!("ctx-/intent-/vrd-…") ──
// S-03：ID 工廠函數 — 替代 12+ 處內聯 format! ID 構造。
#[inline]
pub(crate) fn make_context_id(em: &str, symbol: &str, ts_ms: u64) -> String {
    format!("ctx-{}-{}-{}", em, symbol, ts_ms)
}
#[inline]
pub(crate) fn make_intent_id(em: &str, symbol: &str, ts_ms: u64) -> String {
    format!("intent-{}-{}-{}", em, symbol, ts_ms)
}
#[inline]
pub(crate) fn make_verdict_id(em: &str, symbol: &str, ts_ms: u64) -> String {
    format!("vrd-{}-{}-{}", em, symbol, ts_ms)
}
#[inline]
pub(crate) fn make_signal_id(source: &str, ts_ms: u64) -> String {
    format!("sig-{}-{}", source, ts_ms)
}
#[inline]
pub(crate) fn make_fill_id(em: &str, symbol: &str, ts_ms: u64) -> String {
    format!("fill-{}-{}-{}", em, symbol, ts_ms)
}
#[inline]
pub(crate) fn make_order_id(em: &str, symbol: &str, ts_ms: u64) -> String {
    format!("order-{}-{}-{}", em, symbol, ts_ms)
}

// ── S-03: Build a synthetic market OrderIntent — shared helper for close / audit intents ──
// S-03：構建合成市價 OrderIntent — 供平倉/審計意圖共用，消除 on_tick 中的重複結構字面量。
#[inline]
pub(crate) fn build_intent(
    symbol: &str,
    is_long: bool,
    qty: f64,
    confidence: f64,
    strategy: String,
) -> crate::intent_processor::OrderIntent {
    crate::intent_processor::OrderIntent {
        symbol: symbol.to_string(),
        is_long,
        qty,
        confidence,
        strategy,
        order_type: "market".into(),
        limit_price: None,
    }
}

// ── S-01: Extracted helpers — deduplicate Exchange vs Paper verdict/intent/display persistence ──
// S-01：提取輔助函數 — 去重交易所 vs 紙盤的裁定/意圖/顯示持久化邏輯。

/// Persist a Guardian verdict to the trading writer channel.
/// 將 Guardian 裁定持久化到交易寫入器通道。
#[inline]
pub(crate) fn persist_verdict(
    trading_tx: &Option<tokio::sync::mpsc::Sender<crate::database::TradingMsg>>,
    em: &str,
    symbol: &str,
    ts_ms: u64,
    vi: &crate::intent_processor::VerdictInfo,
    engine_mode: &str,
) {
    if let Some(ref tx) = trading_tx {
        let _ = tx.try_send(crate::database::TradingMsg::RiskVerdict {
            verdict_id: make_verdict_id(em, symbol, ts_ms),
            ts_ms,
            intent_id: make_intent_id(em, symbol, ts_ms),
            context_id: make_context_id(em, symbol, ts_ms),
            symbol: symbol.to_string(),
            verdict: vi.verdict.clone(),
            risk_score: vi.risk_score,
            reasons: vi.reasons.clone(),
            modified_qty: vi.modified_qty,
            engine_mode: engine_mode.to_string(),
        });
    }
}

/// Persist an approved intent to the trading writer channel.
/// 將已批准的意圖持久化到交易寫入器通道。
#[inline]
pub(crate) fn persist_intent(
    trading_tx: &Option<tokio::sync::mpsc::Sender<crate::database::TradingMsg>>,
    em: &str,
    ts_ms: u64,
    intent: &crate::intent_processor::OrderIntent,
    approved_qty: f64,
    price: f64,
    engine_mode: &str,
) {
    if let Some(ref tx) = trading_tx {
        let _ = tx.try_send(crate::database::TradingMsg::Intent {
            intent_id: make_intent_id(em, &intent.symbol, ts_ms),
            ts_ms,
            signal_id: String::new(),
            context_id: make_context_id(em, &intent.symbol, ts_ms),
            symbol: intent.symbol.clone(),
            side: if intent.is_long { "Buy".into() } else { "Sell".into() },
            qty: approved_qty,
            price,
            order_type: intent.order_type.clone(),
            strategy_name: intent.strategy.clone(),
            engine_mode: engine_mode.to_string(),
        });
    }
}

/// Push a display intent into the recent_intents ring buffer.
/// `display_qty` overrides the intent's qty if Some (M-2 audit: post-Guardian cap).
/// 推入顯示意圖到 recent_intents 環形緩衝。
/// `display_qty` 若 Some，覆蓋 intent 的 qty（M-2 審計：Guardian 治理後數量）。
#[inline]
pub(crate) fn push_display_intent(
    buf: &mut VecDeque<TimestampedIntent>,
    ts_ms: u64,
    intent: &crate::intent_processor::OrderIntent,
    display_qty: Option<f64>,
    result: String,
) {
    let mut di = intent.clone();
    if let Some(q) = display_qty {
        di.qty = q;
    }
    push_capped(buf, TimestampedIntent {
        timestamp_ms: ts_ms,
        intent: di,
        result,
    }, 50);
}

impl TickPipeline {
    /// Canary record builder — emit per-tick diagnostic when canary_mode is on.
    /// 灰度記錄構建器 — canary_mode 開啟時發射每 tick 診斷。
    pub(super) fn maybe_canary_record(
        &self,
        event: &PriceEvent,
        indicators: Option<IndicatorSnapshot>,
        signals: Vec<Signal>,
        intents: Vec<crate::intent_processor::OrderIntent>,
        tick_duration_us: u64,
    ) -> Option<CanaryRecord> {
        if !self.canary_mode {
            return None;
        }
        Some(CanaryRecord {
            schema_version: "1.0.0".into(),
            source: "rust_engine".into(),
            tick_number: self.stats.total_ticks,
            timestamp_ms: event.ts_ms,
            symbol: event.symbol.clone(),
            price: event.last_price,
            indicators,
            signals,
            order_intents: intents,
            paper_state: self.paper_state.export_state(),
            stats: self.stats.clone(),
            tick_duration_us,
        })
    }

    /// Compute indicator snapshot from aggregated klines.
    /// 從聚合 K 線計算指標快照。
    pub(super) fn compute_indicators(&self, symbol: &str) -> Option<IndicatorSnapshot> {
        let ohlcv = self.kline_manager.get_ohlcv(symbol, "1m", Some(100))?;
        if ohlcv.close.len() < 30 {
            return None;
        }
        Some(IndicatorEngine::compute_all(
            &ohlcv.high,
            &ohlcv.low,
            &ohlcv.close,
            &ohlcv.volume,
        ))
    }

    /// Session 11: Feed trade & orderbook events into 1-minute aggregators.
    /// Flushes happen at minute boundaries → MarketDataMsg::TradeAgg1m / ObSnapshot.
    /// Session 11：將 trade/orderbook 事件餵入 1 分鐘聚合器，跨分鐘時 flush。
    pub(super) fn process_market_events(&mut self, event: &PriceEvent) {
        // FIX-31: Use typed event_kind, fall back to legacy metadata["type"].
        let kind = event.event_kind.as_ref();
        match kind {
            Some(PriceEventKind::Trade) => {
                // P-02: Read from structured fields first, fall back to legacy metadata.
                // P-02：優先讀結構化欄位，回退到舊版 metadata。
                let side = event
                    .trade_side
                    .as_deref()
                    .or_else(|| event.metadata.get("side").map(|s| s.as_str()))
                    .and_then(crate::database::aggregators::TradeSide::parse);
                let qty = event
                    .trade_qty
                    .or_else(|| {
                        event
                            .metadata
                            .get("qty")
                            .and_then(|s| s.parse::<f64>().ok())
                    })
                    .unwrap_or(0.0);
                if let Some(side) = side {
                    if let Some(msg) = self.trade_aggregator.record(
                        &event.symbol,
                        side,
                        qty,
                        event.last_price,
                        event.ts_ms,
                    ) {
                        if let Some(ref tx) = self.market_data_tx {
                            let _ = tx.try_send(msg);
                        }
                    }
                }
            }
            Some(PriceEventKind::Orderbook) => {
                // P-02: Read from structured fields first, fall back to legacy metadata JSON.
                // P-02：優先讀結構化欄位，回退到舊版 metadata JSON 反序列化。
                let bids: Vec<(f64, f64)> = event
                    .bids5
                    .clone()
                    .or_else(|| {
                        event
                            .metadata
                            .get("bids5")
                            .and_then(|s| serde_json::from_str(s).ok())
                    })
                    .unwrap_or_default();
                let asks: Vec<(f64, f64)> = event
                    .asks5
                    .clone()
                    .or_else(|| {
                        event
                            .metadata
                            .get("asks5")
                            .and_then(|s| serde_json::from_str(s).ok())
                    })
                    .unwrap_or_default();
                if !bids.is_empty() && !asks.is_empty() {
                    if let Some(msg) = self.ob_aggregator.record(
                        &event.symbol,
                        &bids,
                        &asks,
                        event.ts_ms,
                    ) {
                        if let Some(ref tx) = self.market_data_tx {
                            let _ = tx.try_send(msg);
                        }
                    }
                }
            }
            _ => {}
        }
    }

    /// GAP-7: Emit PositionSnapshot for every open position every 1000 ticks.
    /// Populates trading.position_snapshots for ML training.
    /// GAP-7：每 1000 ticks 發射持倉快照以填充 position_snapshots 表。
    pub(super) fn emit_periodic_snapshots(&self, event: &PriceEvent) {
        if let Some(ref tx) = self.trading_tx {
            for pos in self.paper_state.positions() {
                let mark_price = *self
                    .latest_prices
                    .get(&pos.symbol)
                    .unwrap_or(&pos.entry_price);
                let unrealized_pnl = if pos.is_long {
                    (mark_price - pos.entry_price) * pos.qty
                } else {
                    (pos.entry_price - mark_price) * pos.qty
                };
                let msg = crate::database::TradingMsg::PositionSnapshot {
                    ts_ms: event.ts_ms,
                    symbol: pos.symbol.clone(),
                    side: if pos.is_long {
                        "long".to_string()
                    } else {
                        "short".to_string()
                    },
                    qty: pos.qty,
                    entry_price: pos.entry_price,
                    mark_price,
                    unrealized_pnl,
                    engine_mode: self.pipeline_kind.db_mode().to_string(),
                };
                let _ = tx.try_send(msg);
            }
        }
    }
}
