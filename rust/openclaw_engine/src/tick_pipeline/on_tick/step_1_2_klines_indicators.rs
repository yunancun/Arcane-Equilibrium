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
//!
//! R1（根因修復，2026-06-16）：DB `market.klines` 的持久化真值單一源 = WS
//! `KlineConfirm` 事件（Bybit 推送的權威整根 OHLCV+turnover）。tick-synth
//! aggregator（`kline_manager.on_tick`）仍照舊跑，但**只供記憶體 buffer /
//! 指標 / 黑天鵝**（=R2 熱路徑不變），**不再對 market writer 發 `KlineClose`**。
//! 這消除了「退化 tick-synth bar 落盤」這個一-bar offset + dead-wick 的根因。

use openclaw_core::klines::{timeframe_duration_ms, KlineBar};
use openclaw_types::PriceEventKind;
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

        // R1：KlineConfirm 事件 = Bybit 推送的權威整根 OHLCV+turnover。
        // 直接 build 真值 KlineBar → emit KlineClose 落盤（旁路 tick-synth
        // aggregator），然後早退（confirmed candle 不是指標 tick，不參與指標/
        // 黑天鵝計算 = 熱路徑零退化）。DB 真值單一源即此路徑。
        if event.event_kind == Some(PriceEventKind::KlineConfirm) {
            self.persist_confirmed_kline(event);
            return None;
        }

        // Step 1: Kline aggregation — feed in-memory buffer for indicators only.
        // 步驟 1：K 線聚合 — 餵記憶體 buffer 供指標 / 黑天鵝使用（不再落盤）。
        //
        // R1：tick-synth aggregator 仍跑（記憶體 buffer 為指標源，=R2 不變），
        // 但**不再對 market writer 發 KlineClose**——DB 持久化已由上方
        // KlineConfirm 路徑單一源負責，避免退化 bar 與權威 bar 雙寫競 PK。
        //
        // QUOTE-VOL-FIX：只有 publicTrade 事件攜帶真實的「單筆成交量」；ticker 事件
        // 攜帶的是 24h 累計 volume_24h（逐 tick 累加會污染 per-bar 量），其餘事件無量。
        // 故 Trade 事件貢獻 base 量(volume) 與 price×qty(turnover，quote-asset 成交額)，
        // 非 Trade 事件對 volume/turnover 貢獻 0，但仍傳入價格驅動 OHLC 與週期滾動。
        let (tick_volume, tick_turnover) = match event.event_kind {
            Some(PriceEventKind::Trade) => {
                let qty = event.volume_24h; // publicTrade `v`（base 數量），鏡像於 trade_qty
                (qty, event.last_price * qty)
            }
            _ => (0.0, 0.0),
        };
        let closed_bars = self.kline_manager.on_tick(
            sym,
            event.last_price,
            event.ts_ms,
            tick_volume,
            tick_turnover,
        );

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
        //
        // P1-11 (2026-07-04)：改走 bar-close gated 1m 快取（PERF-1 5m 半邊補全）。
        // 同一根 1m bar 內回快取 clone（與每 tick 重算 bit-identical），僅新 1m
        // 收盤或 ewma_lambda 熱重載時重算。回傳為 owned clone，下方 hurst 打標 /
        // latest_indicators 鏡像 / FeatureSnapshot 發送每 tick 照舊在 clone 上
        // 執行 —— 只省「重算」本身，不改任何下游語義（快取不會被打標污染）。
        let mut indicators = self.cached_or_recompute_indicators_1m(sym);

        // G7-03 Phase B: stabilize `hurst.regime` via per-symbol hysteresis when
        // `risk.hurst.enabled = true`. No-op (bit-identical to Phase A) when the
        // flag is off or risk_store is unwired. Must run BEFORE `latest_indicators`
        // mirror + FeatureSnapshot emit so downstream readers see the stabilized
        // label, not the instantaneous one.
        // G7-03 Phase B：當 hurst.enabled=true 時將 regime 標籤套上 per-symbol 滯回。
        // 旗標關閉或 risk_store 未接線時 no-op，bit-identical Phase A。
        // 必須在 latest_indicators 鏡像 + FeatureSnapshot 發送前完成，
        // 讓下游讀的是穩定後標籤而非瞬時標籤。
        if let Some(ref mut ind) = indicators {
            self.apply_hurst_regime_label_for(sym, ind);
        }

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
                ind.clone(),
                self.feature_version.clone(),
            );
            if tx.try_send(snap).is_err() {
                self.feature_tx_dropped += 1;
            }
        }

        indicators
    }

    /// R1：把 WS `KlineConfirm` 事件攜帶的權威整根 OHLCV+turnover 直接落盤。
    ///
    /// 為什麼旁路 tick-synth aggregator：Bybit 在 `confirm==true` 推送的就是真值
    /// 整根，無需（也不應）由稀疏 tick 重新合成。直接 build `KlineBar` →
    /// emit `MarketDataMsg::KlineClose`，DB writer 以 PK (symbol,timeframe,ts)
    /// `ON CONFLICT DO NOTHING` 收。DB 真值單一源 = 此路徑。
    ///
    /// fail-closed：interval 無法映射 timeframe、或 OHLC 任一欄缺失 → 丟棄整根
    /// （parser 已 fail-closed 過一層，這裡是第二道防線，不落半截 bar）。
    fn persist_confirmed_kline(&mut self, event: &PriceEvent) {
        let tx = match &self.market_data_tx {
            Some(tx) => tx,
            None => return, // scanner / paper 路徑未接 market writer → no-op
        };

        // interval → timeframe（與 intraday_kline_backfill bin 的 resolve_interval
        // 映射一致：1→1m / 5→5m / 15→15m / 60→1h / 240→4h）。
        let timeframe = match event.kline_interval.as_deref() {
            Some("1") => "1m",
            Some("5") => "5m",
            Some("15") => "15m",
            Some("60") => "1h",
            Some("240") => "4h",
            _ => return, // 未知 interval → fail-closed
        };

        // OHLC 必須齊全（parser 已保證，這裡二次防線）；close/volume 走既有欄位。
        let (open, high, low) = match (event.kline_open, event.kline_high, event.kline_low) {
            (Some(o), Some(h), Some(l)) => (o, h, l),
            _ => return,
        };
        let close = event.last_price;
        let volume = event.volume_24h;
        let turnover = event.kline_turnover.unwrap_or(0.0);

        let open_time_ms = event.kline_start_ms.unwrap_or(event.ts_ms);
        // close_time：優先用 Bybit `end`；缺則由 timeframe 週期推算。
        let close_time_ms = event.kline_close_ms.unwrap_or_else(|| {
            open_time_ms + timeframe_duration_ms(timeframe).unwrap_or(0)
        });

        let bar = KlineBar {
            open_time_ms,
            close_time_ms,
            open,
            high,
            low,
            close,
            volume,
            turnover,
            // tick_count：WS confirmed candle 是 Bybit 端聚合，本地無 tick 計數；
            // 記 0 表「非本地 tick-synth 而是權威整根」（落盤欄位語義標記）。
            tick_count: 0,
            is_closed: true,
        };

        if tx
            .try_send(crate::database::MarketDataMsg::KlineClose {
                symbol: event.symbol.clone(),
                timeframe: timeframe.to_string(),
                bar,
            })
            .is_err()
        {
            self.market_tx_dropped += 1;
        }
    }
}
