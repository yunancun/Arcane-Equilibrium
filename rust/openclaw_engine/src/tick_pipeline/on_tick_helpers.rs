//! FIX-29: Extracted helper methods for on_tick — keeps on_tick.rs under §九 1200-line hard limit.
//! FIX-29：on_tick 抽出的輔助方法 — 讓 on_tick.rs 保持在 §九 1200 行硬上限以下。

use super::*;
use std::collections::{HashMap, VecDeque};

// ── P0-5: ReduceToHalf one-shot cooldown — decouples the guard from governance state ──
// P0-5: ReduceToHalf 一次性保護的冷卻窗 — 將 guard 與 governance 狀態解耦。
//
// FA-PHANTOM-2 fix (commit 348a9c5) opened a `held_drop≥5% && sigma≥3` path that
// fires `ReduceToHalf` at `risk_level < Defensive`. EDGE-P0-1's original clear
// condition (`< Defensive`) then wiped the guard every tick during persistent
// Cautious, yielding 9 ReduceToHalf emissions in 1.3s on ORDIUSDT (2026-04-16
// 18:03:41, see docs/references/2026-04-16--phantom2_fup_reduce_to_half_cascade_rca.md).
// A 60 s cooldown matches the governance Defensive hold window and guarantees
// a per-symbol burst is bounded, without depending on a Cautious→Normal return
// (which `evaluate_risk_context` never automates — risk_gov.rs:617 "Only escalate").
//
// FA-PHANTOM-2 修復開放了 risk<Defensive 下的 ReduceToHalf 路徑；原本
// EDGE-P0-1 在 `< Defensive` 時清空 guard → Cautious 持續時每 tick 清一次 →
// 1.3 秒內同 symbol 連發 9 次 ReduceToHalf。60 秒冷卻窗配合 C 方案（僅
// Normal 才清）封住毫秒連發同時保留自然 episode 邊界。
pub(crate) const FT_REDUCE_COOLDOWN_MS: i64 = 60_000;

/// B2: Upper bound for sigma-scaled cooldown — prevents a freak sigma (e.g.
/// 50σ on a stable coin with near-zero std_dev) from locking a symbol out
/// indefinitely. 600s = 10× base, same ratio ceiling grid_trading tolerates
/// on its own trend multiplier. Not a tuning surface — pure safety clamp.
/// B2：sigma 縮放冷卻上限，防止極端 sigma 把 symbol 永久鎖死。
pub(crate) const FT_REDUCE_COOLDOWN_MAX_MS: i64 = 600_000;

/// P0-5 + B2: Stamp recorded when a symbol is halved. Carries both the
/// timestamp and the effective cooldown that was active at the time, so a
/// later expiry check uses the severity snapshot from the halving event
/// rather than recomputing against current indicators (the trigger sigma
/// may have decayed by then).
/// P0-5 + B2：每次半倉記錄 (時間戳, 有效冷卻 ms)。冷卻依觸發時的 sigma 鎖定。
pub(crate) type FtReduceStamp = (i64, i64);

/// P0-5 + B2: Check whether a symbol is eligible for a fresh ReduceToHalf
/// emit. Returns `true` when the symbol has never been halved OR the
/// *event-specific* cooldown stamped at halving has elapsed.
/// P0-5 + B2：判斷該 symbol 是否可再次觸發 ReduceToHalf（未曾半倉或冷卻已過）。
#[inline]
pub(crate) fn ft_reduce_cooldown_expired(
    ft_reduced_symbols: &HashMap<String, FtReduceStamp>,
    symbol: &str,
    now_ts_ms: i64,
) -> bool {
    match ft_reduced_symbols.get(symbol) {
        None => true,
        Some(&(last_ts, cooldown_ms)) => now_ts_ms.saturating_sub(last_ts) >= cooldown_ms,
    }
}

/// B2: Sigma-proportional cooldown for ReduceToHalf. Severity at the moment
/// of halving determines the recovery window: `base × (sigma / 3.0)`, clamped
/// to `[base, FT_REDUCE_COOLDOWN_MAX_MS]`. The divisor `3.0` is not a new
/// constant — it is the fast_track trigger threshold itself
/// (`held_drop_sigma ≥ 3.0`, see fast_track.rs:89).
///
/// At sigma = 3.0 (just triggered) the cooldown equals the base 60s; at
/// sigma = 6.0 it doubles to 120s; extreme sigma ≥ 30 saturates at 600s.
/// Below sigma = 3.0 the caller should not be invoking this path, but as a
/// defense we floor at the base to avoid shrinking the guard window.
/// B2：半倉冷卻按觸發 sigma 成比例縮放，下限為基準，上限為 600s。
#[inline]
pub(crate) fn sigma_scaled_reduce_cooldown_ms(held_drop_sigma: f64) -> i64 {
    let ratio = (held_drop_sigma / 3.0).max(1.0);
    let scaled = (FT_REDUCE_COOLDOWN_MS as f64 * ratio) as i64;
    scaled.min(FT_REDUCE_COOLDOWN_MAX_MS)
}

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
        // Synthetic close / audit intents have no strategy-side decision state.
        // 合成平倉/審計意圖無策略端決策特徵。
        confluence_score: None,
        persistence_elapsed_ms: None,
        time_in_force: None,
        maker_timeout_ms: None,
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
        let checks_failed = vi.reasons.clone();
        let checks_passed = if checks_failed.is_empty() {
            vec!["guardian_checks".to_string()]
        } else {
            Vec::new()
        };
        let risk_level = risk_score_level(vi.risk_score).map(str::to_string);
        let _ = crate::database::try_send_trading_msg(
            tx,
            crate::database::TradingMsg::RiskVerdict {
                verdict_id: make_verdict_id(em, symbol, ts_ms),
                ts_ms,
                intent_id: make_intent_id(em, symbol, ts_ms),
                context_id: make_context_id(em, symbol, ts_ms),
                symbol: symbol.to_string(),
                verdict: vi.verdict.clone(),
                risk_score: vi.risk_score,
                risk_level,
                checks_passed,
                checks_failed,
                reasons: vi.reasons.clone(),
                modified_qty: vi.modified_qty,
                engine_mode: engine_mode.to_string(),
            },
            "risk_verdict",
        );
    }
}

#[inline]
pub(crate) fn risk_score_level(score: f64) -> Option<&'static str> {
    if !score.is_finite() {
        None
    } else if score >= 0.80 {
        Some("risk_score_high")
    } else if score >= 0.50 {
        Some("risk_score_medium")
    } else {
        Some("risk_score_low")
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
        // FUP-8: populate details so trading.intents.details stops being 100% NULL.
        // Currently carries only what OrderIntent exposes (strategy + confidence);
        // edge/funding_rate/basis/regime will be added once G-1 Strategist wires
        // those fields into OrderIntent. Root principle #8「交易可解釋」requires
        // at minimum the strategy identifier + confidence score to be persisted.
        // FUP-8：填充 details 避免 trading.intents.details 100% NULL。
        //
        // Sentinel guard (safety net post-Phase 2). As of FUP-8 Phase 2 both paper
        // and exchange callers pass `approved_qty` = post-Kelly/P1 sized qty, so
        // this check should never fire in the on_tick.rs normal flow. It remains
        // because (a) the IPC command path in commands.rs still constructs its own
        // call with raw qty, and (b) defense-in-depth for anyone adding a new call
        // site that forgets sizing — an honest `null` + flag beats silent 1e9 in DB.
        // 哨兵旗標（Phase 2 後的安全網）：on_tick 路徑兩側 caller 都已傳入 sized qty，
        // 正常流程此檢查不會觸發；保留以防 IPC 路徑 & 未來新 caller 遺漏 sizing。
        let is_sentinel = approved_qty >= 1e9;
        let details = serde_json::json!({
            "strategy": intent.strategy,
            "confidence": intent.confidence,
            "submitted_qty": if is_sentinel { serde_json::Value::Null } else { serde_json::json!(approved_qty) },
            "is_sentinel": is_sentinel,
            "is_long": intent.is_long,
        });
        let _ = crate::database::try_send_trading_msg(
            tx,
            crate::database::TradingMsg::Intent {
                intent_id: make_intent_id(em, &intent.symbol, ts_ms),
                ts_ms,
                signal_id: String::new(),
                context_id: make_context_id(em, &intent.symbol, ts_ms),
                symbol: intent.symbol.clone(),
                side: if intent.is_long {
                    "Buy".into()
                } else {
                    "Sell".into()
                },
                qty: approved_qty,
                price,
                order_type: intent.order_type.clone(),
                strategy_name: intent.strategy.clone(),
                engine_mode: engine_mode.to_string(),
                details: Some(details),
            },
            "intent",
        );
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
    push_capped(
        buf,
        TimestampedIntent {
            timestamp_ms: ts_ms,
            intent: di,
            result,
        },
        50,
    );
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
    ///
    /// G7-02 (2026-04-24): EWMA Vol lambda is sourced from
    /// `RiskConfig.ewma_vol.lambda_for_timeframe("1m")` when a `risk_store` is
    /// wired; otherwise the core indicator engine's `DEFAULT_EWMA_VOL_LAMBDA`
    /// (0.97) preserves the pre-G7-02 behavior.
    /// G7-02：EWMA Vol lambda 由 RiskConfig.ewma_vol 驅動；未接 store 時回退至
    /// 0.97 保留 G7-02 前行為。
    pub(super) fn compute_indicators(&self, symbol: &str) -> Option<IndicatorSnapshot> {
        const TIMEFRAME: &str = "1m";
        let ohlcv = self.kline_manager.get_ohlcv(symbol, TIMEFRAME, Some(100))?;
        if ohlcv.close.len() < 30 {
            return None;
        }
        let ewma_lambda = self
            .risk_store
            .as_ref()
            .map(|store| store.load().ewma_vol.lambda_for_timeframe(TIMEFRAME))
            .unwrap_or(openclaw_core::indicators::DEFAULT_EWMA_VOL_LAMBDA);
        Some(IndicatorEngine::compute_all_with_lambda(
            &ohlcv.high,
            &ohlcv.low,
            &ohlcv.close,
            &ohlcv.volume,
            ewma_lambda,
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
                    if let Some(msg) =
                        self.ob_aggregator
                            .record(&event.symbol, &bids, &asks, event.ts_ms)
                    {
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
                    engine_mode: self.effective_engine_mode().to_string(),
                };
                let _ = tx.try_send(msg);
            }
        }
    }
}
