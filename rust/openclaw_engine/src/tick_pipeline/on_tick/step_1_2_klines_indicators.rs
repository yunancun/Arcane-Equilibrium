//! Step 1+2: kline aggregation + indicator computation + FeatureSnapshot emit.
//! Step 1+2：K 線聚合 + 指標計算 + FeatureSnapshot 發送。
//!
//! Step 1 aggregates closed bars per timeframe, emits `KlineClose` rows to
//! the market writer, and feeds 1m bars into the black-swan detector. Step 2
//! then computes indicators (ATR / BB / MA / RSI / etc.) and emits
//! `FeatureSnapshot` to the feature writer channel. No early exit —
//! `Option<IndicatorSnapshot>` is returned for Step 3 + Step 4+5 to consume.
//!
//! Step 1 逐 timeframe 聚合已收 K 線、發 `KlineClose` 給 market writer、餵
//! 1m bar 給黑天鵝檢測器。Step 2 計算指標並發 `FeatureSnapshot` 給特徵寫入
//! channel。無早退；回傳 `Option<IndicatorSnapshot>` 供 Step 3/4+5 消費。

use tracing::warn;

use super::super::*;

impl TickPipeline {
    /// Execute Step 1 (kline aggregation + black-swan feeding) and Step 2
    /// (indicator compute + FeatureSnapshot emit).
    ///
    /// Returns the computed `IndicatorSnapshot` (or `None` when insufficient
    /// 1m bars). No early exit path.
    ///
    /// 執行 Step 1（K 線聚合 + 黑天鵝檢測）與 Step 2（指標計算 +
    /// FeatureSnapshot 發送）。回傳計算出的 `IndicatorSnapshot`（1m bar
    /// 不足時為 `None`）；不含早退路徑。
    pub(super) fn on_tick_step_1_2_klines_indicators(
        &mut self,
        event: &PriceEvent,
    ) -> Option<IndicatorSnapshot> {
        let sym = &event.symbol;

        // Step 1: Kline aggregation — collect closed bars for DB write.
        // 步驟 1：K 線聚合 — 收集已關閉的 K 線用於 DB 寫入。
        let closed_bars =
            self.kline_manager
                .on_tick(sym, event.last_price, event.ts_ms, event.volume_24h, 0.0);

        // Phase 1: Emit KlineClose for each closed bar to market writer (F-2 audit fix).
        // Phase 1：為每根已關閉 K 線發送 KlineClose 到市場寫入器（F-2 審計修復）。
        if let Some(ref tx) = self.market_data_tx {
            for (timeframe, bar) in &closed_bars {
                if tx
                    .try_send(crate::database::MarketDataMsg::KlineClose {
                        symbol: sym.clone(),
                        timeframe: timeframe.clone(),
                        bar: bar.clone(),
                    })
                    .is_err()
                {
                    self.market_tx_dropped += 1;
                }
            }
        }

        // DB-RUN-5: Feed black-swan detector on 1m bar close.
        // Compute log-return vs previous close, push into rolling window, run
        // 4-signal vote. Severity >= Observe → warn log. DB write deferred.
        // DB-RUN-5：1 分鐘 K 線收盤時餵入黑天鵝檢測器，4 信號投票，severity 達標時 warn。
        for (timeframe, bar) in &closed_bars {
            if timeframe != "1m" {
                continue;
            }
            let prev = self.last_close_price.insert(sym.clone(), bar.close);
            let ret = match prev {
                Some(prev_close) if prev_close > 0.0 => (bar.close - prev_close) / prev_close,
                _ => 0.0,
            };
            self.black_swan.record_bar(sym, ret, bar.volume);
            let result = self.black_swan.check(sym, ret, bar.volume, event.ts_ms);
            use crate::database::black_swan_detector::BlackSwanSeverity;
            if !matches!(result.severity, BlackSwanSeverity::None) {
                warn!(
                    symbol = %sym,
                    severity = ?result.severity,
                    votes = result.votes_for,
                    return_pct = format!("{:.4}%", ret * 100.0),
                    "BLACK SWAN signal / 黑天鵝信號"
                );
            }
        }

        // Step 2: Compute indicators (need enough 1m bars)
        // 步驟 2：計算指標（需要足夠的 1 分鐘 K 線）
        let indicators = self.compute_indicators(sym);

        // Store latest indicators for IPC snapshot / 存儲最新指標供 IPC 快照使用
        if let Some(ref ind) = indicators {
            self.latest_indicators.insert(sym.clone(), ind.clone());
        }

        // Phase 1: Emit FeatureSnapshot to DB writer channel (non-blocking try_send).
        // Phase 1：發送 FeatureSnapshot 到 DB 寫入器通道（非阻塞 try_send）。
        if let (Some(ref tx), Some(ref ind)) = (&self.feature_tx, &indicators) {
            let snap = crate::feature_collector::FeatureSnapshot::new(
                sym.clone(),
                event.ts_ms,
                event.last_price,
                event.volume_24h,
                ind.clone(),
                self.feature_version.clone(),
            );
            if tx.try_send(snap).is_err() {
                self.feature_tx_dropped += 1;
            }
        }

        indicators
    }
}
