//! FIX-29: Extracted helper methods for on_tick — keeps on_tick.rs under §九 1200-line hard limit.
//! FIX-29：on_tick 抽出的輔助方法 — 讓 on_tick.rs 保持在 §九 1200 行硬上限以下。

use super::*;

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
    pub(super) fn process_aggregator_events(&mut self, event: &PriceEvent) {
        let event_type = match event.metadata.get("type").map(|s| s.as_str()) {
            Some(t) => t,
            None => return,
        };
        match event_type {
            "trade" => {
                let side = event
                    .metadata
                    .get("side")
                    .and_then(|s| crate::database::aggregators::TradeSide::parse(s));
                let qty = event
                    .metadata
                    .get("qty")
                    .and_then(|s| s.parse::<f64>().ok())
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
            "orderbook" => {
                let bids: Vec<(f64, f64)> = event
                    .metadata
                    .get("bids5")
                    .and_then(|s| serde_json::from_str(s).ok())
                    .unwrap_or_default();
                let asks: Vec<(f64, f64)> = event
                    .metadata
                    .get("asks5")
                    .and_then(|s| serde_json::from_str(s).ok())
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
