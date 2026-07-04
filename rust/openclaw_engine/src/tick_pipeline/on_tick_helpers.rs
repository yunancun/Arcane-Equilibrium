//! FIX-29: Extracted helper methods for on_tick — keeps on_tick.rs under §九 1200-line hard limit.
//! FIX-29：on_tick 抽出的輔助方法 — 讓 on_tick.rs 保持在 §九 1200 行硬上限以下。

use super::*;
use crate::scanner::types::ScannerAuthorityMode;
use std::collections::{HashMap, VecDeque};

pub(crate) fn liquidation_msg_from_event(
    event: &PriceEvent,
) -> Option<crate::database::MarketDataMsg> {
    if event.event_kind.as_ref() != Some(&PriceEventKind::Liquidation) {
        return None;
    }
    let side = event
        .metadata
        .get("side")
        .filter(|s| matches!(s.as_str(), "Buy" | "Sell"))?;
    let qty = event
        .metadata
        .get("qty")
        .and_then(|s| s.parse::<f64>().ok())
        .filter(|v| v.is_finite() && *v > 0.0)?;
    if !event.last_price.is_finite() || event.last_price <= 0.0 {
        return None;
    }
    Some(crate::database::MarketDataMsg::Liquidation {
        ts_ms: event.ts_ms,
        symbol: event.symbol.clone(),
        side: side.clone(),
        qty,
        price: event.last_price,
    })
}

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
/// of halving determines the recovery window: `base × (sigma / trigger_sigma)`,
/// clamped to `[base, FT_REDUCE_COOLDOWN_MAX_MS]`. The default divisor `3.0`
/// is the legacy fast_track trigger threshold itself.
///
/// At sigma = 3.0 (just triggered) the cooldown equals the base 60s; at
/// sigma = 6.0 it doubles to 120s; extreme sigma ≥ 30 saturates at 600s.
/// Below trigger sigma the caller should not be invoking this path, but as a
/// defense we floor at the base to avoid shrinking the guard window. Invalid
/// trigger values fall back to 3.0; `RiskConfig` validation should reject them
/// before runtime.
/// B2：半倉冷卻按觸發 sigma 成比例縮放，下限為基準，上限為 600s。
#[cfg(test)]
#[inline]
pub(crate) fn sigma_scaled_reduce_cooldown_ms(held_drop_sigma: f64) -> i64 {
    sigma_scaled_reduce_cooldown_ms_with_trigger(held_drop_sigma, 3.0)
}

#[inline]
pub(crate) fn sigma_scaled_reduce_cooldown_ms_with_trigger(
    held_drop_sigma: f64,
    trigger_sigma: f64,
) -> i64 {
    let safe_trigger = if trigger_sigma.is_finite() && trigger_sigma > 0.0 {
        trigger_sigma
    } else {
        3.0
    };
    let ratio = (held_drop_sigma / safe_trigger).max(1.0);
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
pub(crate) fn make_strategy_signal_id(
    em: &str,
    strategy: &str,
    symbol: &str,
    ts_ms: u64,
) -> String {
    format!("sig-{}-{}-{}-{}", em, strategy, symbol, ts_ms)
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
//
// Round 2 finding 3：本 helper 是 close-audit intent（push_display_intent 顯示用，
// 不走 IntentProcessor / 不送交易所），但 OrderIntent struct 與 trade-path 共享 →
// 必須由 is_long 派生 intent_type，否則 caller 傳 is_long=false 會殘留 OpenLong
// 占位（finding 3 反模式重犯）。
//
// 不變量：本 helper 只構造 trading audit intent；caller（step_4_5_dispatch 1615 /
// step_6_risk_checks）傳 is_long 後此處派生對齊。Earn 路徑不會走此 helper。
#[inline]
pub(crate) fn build_intent(
    symbol: &str,
    is_long: bool,
    qty: f64,
    confidence: f64,
    strategy: String,
) -> crate::intent_processor::OrderIntent {
    // Round 2 finding 3：由 is_long 派生 intent_type，消除 caller 傳 is_long=false
    // 卻殘留 OpenLong 字面占位的矛盾（即便此 intent 不走 process，仍須 self-consistent）。
    let intent_type = if is_long {
        crate::intent_processor::IntentType::OpenLong
    } else {
        crate::intent_processor::IntentType::OpenShort
    };
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
        intent_type,
        earn_payload: None,
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

/// Scanner-side audit metadata attached to strategy intents.
/// Scanner 側審計 metadata，隨策略 intent 寫入 details。
#[derive(Debug, Clone)]
pub(crate) struct IntentScannerContext {
    pub authority_mode: ScannerAuthorityMode,
    pub legacy_would_block: bool,
    pub legacy_block_reason: Option<String>,
    pub scan_id: String,
    pub best_strategy: String,
    pub intent_strategy: String,
    pub market_regime: String,
    pub trend_phase: String,
    pub trend_score: f64,
    pub range_score: f64,
    pub shock_score: f64,
    pub close_alignment: f64,
    pub range_position: f64,
    pub crowding_score: f64,
    pub reversal_risk_score: f64,
    pub directional_efficiency: f64,
    pub dir_pct: f64,
    pub signed_dir_pct: f64,
    pub range_pct: f64,
    pub fr_bps: f64,
    pub f_ma: f64,
    pub f_grid: f64,
    pub f_bbrv: f64,
    pub f_bkout: f64,
    pub f_funding_arb: f64,
    pub edge_bps: Option<f64>,
    pub edge_n: u32,
    pub edge_status: String,
    pub route_mode: String,
    pub market_status: String,
    pub route_reason: String,
    pub opportunity: Option<crate::scanner::types::OpportunityDecision>,
    pub final_score: f64,
    pub raw_score: f64,
}

/// Scanner evidence audit for legacy would-block calculations.
/// scanner legacy would-block 計算的 evidence 審計。
#[derive(Debug, Clone)]
pub(crate) struct ScannerGateAudit {
    pub authority_mode: ScannerAuthorityMode,
    pub legacy_would_block: bool,
    pub legacy_block_reason: Option<String>,
}

impl ScannerGateAudit {
    pub(crate) fn new(
        authority_mode: ScannerAuthorityMode,
        legacy_block_reason: Option<String>,
    ) -> Self {
        Self {
            authority_mode,
            legacy_would_block: legacy_block_reason.is_some(),
            legacy_block_reason,
        }
    }
}

pub(crate) fn scanner_opportunity_canary_reason(
    scanner_ctx: &IntentScannerContext,
) -> Option<String> {
    let opportunity = scanner_ctx.opportunity.as_ref()?;
    if !opportunity.canary_block_new_entry {
        return None;
    }
    let lcb = opportunity
        .opportunity_lcb_bps
        .map(|v| format!("{v:.2}"))
        .unwrap_or_else(|| "none".to_string());
    Some(format!(
        "scanner_opportunity_canary:hint={} lcb={} {}",
        opportunity.admission_hint, lcb, opportunity.reason
    ))
}

pub(crate) fn scanner_legacy_new_open_block_reason(
    intent_strategy: &str,
    scanner_ctx: Option<&IntentScannerContext>,
    active_universe_block_reason: Option<&str>,
    demo_live_gate: bool,
) -> Option<String> {
    if let Some(reason) = active_universe_block_reason {
        return Some(reason.to_string());
    }
    if !demo_live_gate {
        return None;
    }
    let sctx = scanner_ctx?;
    let market_blocked = matches!(
        sctx.route_mode.as_str(),
        "market_gate" | "exploration_only" | "risk_policy_gate"
    ) || (intent_strategy == "funding_arb"
        && sctx.route_mode == "exploration");
    if market_blocked {
        return Some(format!(
            "scanner_market_gate:{}:{}",
            sctx.market_status, sctx.route_reason
        ));
    }
    scanner_opportunity_canary_reason(sctx)
}

/// Persist a strategy-generated signal used as the attribution anchor for a
/// concrete open intent. This is separate from Step 3 market-observation
/// signals, which remain paper-only under Signal Diamond V015.
/// 持久化「策略已準備開倉」信號，作為具體 intent 的歸因錨點；不同於 Step 3
/// market-observation signal（仍依 Signal Diamond V015 只由 paper 寫）。
#[inline]
pub(crate) fn persist_strategy_signal(
    trading_tx: &Option<tokio::sync::mpsc::Sender<crate::database::TradingMsg>>,
    signal_id: &str,
    context_id: &str,
    ts_ms: u64,
    engine_mode: &str,
    intent: &crate::intent_processor::OrderIntent,
) {
    if let Some(ref tx) = trading_tx {
        let msg = crate::agent_spine::signal_adapter::trading_msg_from_open_intent(
            signal_id,
            context_id,
            ts_ms,
            engine_mode,
            intent,
        );
        let _ = crate::database::try_send_trading_msg(tx, msg, "strategy_signal");
    }
}

/// Persist an approved intent to the trading writer channel.
/// 將已批准的意圖持久化到交易寫入器通道。
///
/// `hurst`：gate 同 tick 消費的 Hurst regime 判定（`IndicatorSnapshot.hurst`
/// 共享引用，純值搬運零重算）。缺失（暖機期/資料不足）映 JSON null ——
/// fail-soft，絕不擋 intent 持久化或執行（P1-BB-REVERSION-REGIME-OBSERVABILITY）。
#[inline]
#[allow(clippy::too_many_arguments)]
pub(crate) fn persist_intent(
    trading_tx: &Option<tokio::sync::mpsc::Sender<crate::database::TradingMsg>>,
    em: &str,
    ts_ms: u64,
    signal_id: &str,
    context_id: &str,
    intent: &crate::intent_processor::OrderIntent,
    approved_qty: f64,
    price: f64,
    engine_mode: &str,
    scanner: Option<&IntentScannerContext>,
    scanner_gate: Option<&ScannerGateAudit>,
    hurst: Option<&openclaw_core::indicators::HurstResult>,
) {
    if let Some(ref tx) = trading_tx {
        // FUP-8: populate details so trading.intents.details stops being 100% NULL.
        // Currently carries only what OrderIntent exposes (strategy + confidence);
        // edge/funding_rate/basis will be added once G-1 Strategist wires
        // those fields into OrderIntent. Root principle #8「交易可解釋」requires
        // at minimum the strategy identifier + confidence score to be persisted.
        // FUP-8：填充 details 避免 trading.intents.details 100% NULL。
        // 2026-06-11 更新：regime 已由 dispatch 層 hurst 參數搬運落地
        // （hurst_label/hurst_value 兩鍵，見下），無須等 OrderIntent 改動。
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
        let scanner_details = scanner.map(|s| {
            serde_json::json!({
                "scan_id": s.scan_id,
                "best_strategy": s.best_strategy,
                "intent_strategy": s.intent_strategy,
                "market_regime": s.market_regime,
                "trend_phase": s.trend_phase,
                "trend_score": s.trend_score,
                "range_score": s.range_score,
                "shock_score": s.shock_score,
                "close_alignment": s.close_alignment,
                "range_position": s.range_position,
                "crowding_score": s.crowding_score,
                "reversal_risk_score": s.reversal_risk_score,
                "directional_efficiency": s.directional_efficiency,
                "dir_pct": s.dir_pct,
                "signed_dir_pct": s.signed_dir_pct,
                "range_pct": s.range_pct,
                "fr_bps": s.fr_bps,
                "f_ma": s.f_ma,
                "f_grid": s.f_grid,
                "f_bbrv": s.f_bbrv,
                "f_bkout": s.f_bkout,
                "f_funding_arb": s.f_funding_arb,
                "edge_bps": s.edge_bps,
                "edge_n": s.edge_n,
                "edge_status": s.edge_status,
                "route_mode": s.route_mode,
                "market_status": s.market_status,
                "route_reason": s.route_reason,
                "opportunity": s.opportunity.as_ref(),
                "final_score": s.final_score,
                "raw_score": s.raw_score,
                "authority_mode": s.authority_mode.as_str(),
                "legacy_would_block": s.legacy_would_block,
                "legacy_block_reason": s.legacy_block_reason.as_deref(),
            })
        });
        let scanner_gate_details = scanner_gate.map(|g| {
            serde_json::json!({
                "authority_mode": g.authority_mode.as_str(),
                "legacy_would_block": g.legacy_would_block,
                "legacy_block_reason": g.legacy_block_reason.as_deref(),
            })
        });
        let details = serde_json::json!({
            "strategy": intent.strategy,
            "confidence": intent.confidence,
            "submitted_qty": if is_sentinel { serde_json::Value::Null } else { serde_json::json!(approved_qty) },
            "is_sentinel": is_sentinel,
            "is_long": intent.is_long,
            "limit_price": intent.limit_price,
            "time_in_force": intent.time_in_force.map(|tif| tif.as_str()),
            "post_only": matches!(intent.time_in_force, Some(crate::order_manager::TimeInForce::PostOnly)),
            "maker_timeout_ms": intent.maker_timeout_ms,
            // P1-BB-REVERSION-REGIME-OBSERVABILITY（2026-06-11）：持久化 gate 同
            // tick 消費的 Hurst regime 判定，讓 QA 可正面驗證 mean_reverting hard
            // gate（如 bb_reversion Track B fix 324001c3）fire 時的 regime 是什麼。
            // 值域 = HurstResult.regime legacy 字串原樣（"mean_reverting"|"trending"
            // |"random_walk"）；缺失映 null（誠實，不 fabricate）；non-finite f64
            // 由 serde_json 映 null（不 panic）。hurst_ 前綴釘死軸別，與 scanner
            // 的 market_regime（趨勢/震盪軸）、AEG main_regime（日線研究軸）區隔。
            "hurst_label": hurst.map(|h| h.regime.as_str()),
            "hurst_value": hurst.map(|h| h.hurst),
            "signal_id": signal_id,
            "context_id": context_id,
            "scanner": scanner_details,
            "scanner_gate": scanner_gate_details,
        });
        let _ = crate::database::try_send_trading_msg(
            tx,
            crate::database::TradingMsg::Intent {
                intent_id: make_intent_id(em, &intent.symbol, ts_ms),
                ts_ms,
                signal_id: signal_id.to_string(),
                context_id: context_id.to_string(),
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
    pub(super) fn compute_indicators_for_timeframe(
        &self,
        symbol: &str,
        timeframe: &str,
    ) -> Option<IndicatorSnapshot> {
        let ohlcv = self.kline_manager.get_ohlcv(symbol, timeframe, Some(100))?;
        if ohlcv.close.len() < 30 {
            return None;
        }
        let ewma_lambda = self
            .risk_store
            .as_ref()
            .map(|store| store.load().ewma_vol.lambda_for_timeframe(timeframe))
            .unwrap_or(openclaw_core::indicators::DEFAULT_EWMA_VOL_LAMBDA);
        Some(IndicatorEngine::compute_all_with_lambda(
            &ohlcv.high,
            &ohlcv.low,
            &ohlcv.close,
            &ohlcv.volume,
            ewma_lambda,
        ))
    }

    pub(super) fn compute_indicators(&self, symbol: &str) -> Option<IndicatorSnapshot> {
        self.compute_indicators_for_timeframe(symbol, "1m")
    }

    /// PERF-1 (2026-06-14)：bar-close gated 5m 指標。epoch 不變則回快取 clone，
    /// epoch 變化（新 5m 收盤 OR ewma_lambda 熱重載）則重算並刷新快取 + epoch。
    ///
    /// 為什麼 gate：5m 指標只在新 5m K 線收盤或 lambda 熱重載時改變；同一根 5m bar
    /// 內每 tick 重算結果完全相同，純屬熱路徑浪費。本 gate 只省掉「指標重算」，
    /// 不改變下游策略每 tick 對 live `ctx.price` 的比較（PERF-1 scope fence）。
    ///
    /// 不變量（fail-closed / 正確性不弱化）：
    ///   - epoch key = (5m 最後收盤 bar 的 `open_time_ms`, ewma_lambda)。用
    ///     `open_time_ms` 而非緩衝長度（緩衝滿後長度凍結，見 klines.rs）；lambda
    ///     入 key 因其經 RiskConfig TOML 熱重載，漏掉會服務過期快照。
    ///   - **只快取 `Some`**：重算回 `None`（暖機 / 無 OHLCV）時不動快取，向下游
    ///     傳 `None`，絕不寫入 `None` → 暖機後不會服務過期 `Some`。
    ///   - 回傳值與每 tick 直接重算 bit-identical（同 bar 內輸入相同）。
    pub(super) fn cached_or_recompute_indicators_5m(
        &mut self,
        symbol: &str,
    ) -> Option<IndicatorSnapshot> {
        // epoch 缺 5m 已關閉 K 線（暖機期 / 未知幣種）→ 無法形成穩定 key。
        // 退回直接重算（compute 端自己會在資料不足時回 None），不寫快取。
        let last_open_time_ms = self
            .kline_manager
            .last_closed_open_time_ms(symbol, "5m")?;
        let ewma_lambda = self
            .risk_store
            .as_ref()
            .map(|store| store.load().ewma_vol.lambda_for_timeframe("5m"))
            .unwrap_or(openclaw_core::indicators::DEFAULT_EWMA_VOL_LAMBDA);
        let epoch = (last_open_time_ms, ewma_lambda);

        // epoch 未變且有快取 → 回 clone（bit-identical 於重算）。
        if self.perf1_indicators_5m_epoch.get(symbol) == Some(&epoch) {
            if let Some(cached) = self.perf1_indicators_5m_cache.get(symbol) {
                return Some(cached.clone());
            }
        }

        // epoch 變化 OR 尚無快取 → 重算。
        match self.compute_indicators_for_timeframe(symbol, "5m") {
            Some(snapshot) => {
                // 只快取 Some + 同步 epoch。
                self.perf1_indicators_5m_cache
                    .insert(symbol.to_string(), snapshot.clone());
                self.perf1_indicators_5m_epoch
                    .insert(symbol.to_string(), epoch);
                Some(snapshot)
            }
            // 重算回 None：不動快取（保留先前 Some 不被污染為 None，也不服務過期
            // Some —— 因為下游收到的是本次的 None），向下游傳 None。
            None => None,
        }
    }

    /// P1-11 (2026-07-04)：bar-close gated 1m 指標。PERF-1 (2026-06-14) 當時只
    /// gate 了 5m 半邊，1m 側仍每 tick 無條件重算 —— 本函數把同一機制補到 1m。
    ///
    /// 語義與 `cached_or_recompute_indicators_5m` 完全同構（timeframe="1m"）：
    ///   - epoch key = (1m 最後收盤 bar 的 `open_time_ms`, ewma_lambda("1m"))。
    ///   - epoch 不變則回快取 clone（與每 tick 重算 bit-identical）；新 1m 收盤
    ///     或 lambda 熱重載則重算並刷新快取 + epoch。
    ///   - **只快取 `Some`**：重算回 `None`（暖機 / 未知幣種）不動快取、向下游傳 `None`。
    ///   - scope fence：只 gate「指標重算」。呼叫端（step_1_2）每 tick 仍在回傳
    ///     的 clone 上執行 hurst 滯回打標（`detector.push` 頻率不變）/
    ///     latest_indicators 鏡像 / FeatureSnapshot 發送 —— 快取內永遠是未打標
    ///     的原始快照，clone 上的 mutation 不可能污染快取。
    pub(super) fn cached_or_recompute_indicators_1m(
        &mut self,
        symbol: &str,
    ) -> Option<IndicatorSnapshot> {
        // 無 1m 已關閉 K 線（暖機期 / 未知幣種）→ 無法形成穩定 epoch key，直接回
        // None 不寫快取。此時直接重算也必回 None（compute 端 <30 根 fail-closed），
        // 兩路徑等價。
        let last_open_time_ms = self
            .kline_manager
            .last_closed_open_time_ms(symbol, "1m")?;
        let ewma_lambda = self
            .risk_store
            .as_ref()
            .map(|store| store.load().ewma_vol.lambda_for_timeframe("1m"))
            .unwrap_or(openclaw_core::indicators::DEFAULT_EWMA_VOL_LAMBDA);
        let epoch = (last_open_time_ms, ewma_lambda);

        // epoch 未變且有快取 → 回 clone（bit-identical 於重算）。
        if self.perf1_indicators_1m_epoch.get(symbol) == Some(&epoch) {
            if let Some(cached) = self.perf1_indicators_1m_cache.get(symbol) {
                return Some(cached.clone());
            }
        }

        // epoch 變化 OR 尚無快取 → 重算（compute_indicators = 1m 全套指標）。
        match self.compute_indicators(symbol) {
            Some(snapshot) => {
                // 只快取 Some + 同步 epoch。
                self.perf1_indicators_1m_cache
                    .insert(symbol.to_string(), snapshot.clone());
                self.perf1_indicators_1m_epoch
                    .insert(symbol.to_string(), epoch);
                Some(snapshot)
            }
            // 重算回 None：不動快取，向下游傳 None（同 5m 側 never-cache-None）。
            None => None,
        }
    }

    /// Session 11: Feed trade & orderbook events into 1-minute aggregators.
    /// Flushes happen at minute boundaries → MarketDataMsg::TradeAgg1m / ObSnapshot.
    /// Session 11：將 trade/orderbook 事件餵入 1 分鐘聚合器，跨分鐘時 flush。
    pub(super) fn process_market_events(&mut self, event: &PriceEvent) {
        // FIX-31: Use typed event_kind, fall back to legacy metadata["type"].
        let kind = event.event_kind.as_ref();
        match kind {
            Some(PriceEventKind::Liquidation) => {
                if let Some(msg) = liquidation_msg_from_event(event) {
                    if let Some(ref tx) = self.market_data_tx {
                        let _ = tx.try_send(msg);
                    }
                }
            }
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
                    // Sub-second 前向錄製（additive）：record_ticks ON 時把逐筆成交原樣
                    // try_send 進既有 writer。非阻塞（channel 滿即丟 = fail-soft，不回壓
                    // tick loop），無 await/無鎖；side 直接用枚舉的標準形 Buy/Sell。
                    if self.record_ticks {
                        if let Some(ref tx) = self.market_data_tx {
                            let _ = tx.try_send(crate::database::MarketDataMsg::RawTrade {
                                ts_ms: event.ts_ms,
                                symbol: event.symbol.clone(),
                                side: match side {
                                    crate::database::aggregators::TradeSide::Buy => "Buy".into(),
                                    crate::database::aggregators::TradeSide::Sell => "Sell".into(),
                                },
                                price: event.last_price,
                                qty,
                            });
                        }
                    }
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
                // recorder-v2（additive，獨立於 v1 的 record_ticks）：record_l1_events ON 時，
                // 把 orderbook 全變更檔 + type/u/seq 餵入有狀態 L1BookTracker 重建本地簿，
                // 僅在解析後 BBO 真變化時 emit 一筆 L1Event try_send。非阻塞 fail-soft、無
                // await/無鎖；BTreeMap apply 為 O(log 50) bounded。本分支用「全變更檔」
                // （ob_changed_bids/asks）而非截斷的 bids5/asks5——這是 recorder-v2 能正確
                // 重建 BBO（含 qty=0 刪除 / 亂序 / u==1 reset）的前提，故與 v1 路徑解耦獨立。
                // flag-OFF（默認）時整個分支跳過，零行為改變、tracker 不建簿。
                if self.record_l1_events {
                    let changed_bids = event.ob_changed_bids.as_deref().unwrap_or(&[]);
                    let changed_asks = event.ob_changed_asks.as_deref().unwrap_or(&[]);
                    if let Some(msg) = self.l1_book_tracker.record(
                        &event.symbol,
                        event.ob_msg_type.as_deref(),
                        changed_bids,
                        changed_asks,
                        event.ob_update_id,
                        event.ob_seq,
                        event.ts_ms,
                    ) {
                        if let Some(ref tx) = self.market_data_tx {
                            let _ = tx.try_send(msg);
                        }
                    }
                }
                if !bids.is_empty() && !asks.is_empty() {
                    // Sub-second 前向錄製（additive）：record_ticks ON 時把 L1 top-of-book
                    // 過取樣節流（ObTopSampler，~250ms 硬上界）後 try_send。非阻塞 fail-soft，
                    // 無 await/無鎖；節流的 HashMap 查詢與 ob_aggregator.record 同量級開銷。
                    if self.record_ticks {
                        if let Some(msg) =
                            self.ob_top_sampler
                                .record(&event.symbol, &bids, &asks, event.ts_ms)
                        {
                            if let Some(ref tx) = self.market_data_tx {
                                let _ = tx.try_send(msg);
                            }
                        }
                    }
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

#[cfg(test)]
mod liquidation_tests {
    use super::*;

    fn liquidation_event(side: &str) -> PriceEvent {
        let mut event = PriceEvent::new("BTCUSDT".into(), 64_000.0, 1_700_000_000_123);
        event.event_kind = Some(PriceEventKind::Liquidation);
        event.metadata.insert("side".into(), side.into());
        event.metadata.insert("qty".into(), "0.25".into());
        event
    }

    #[test]
    fn liquidation_msg_preserves_buy_side_qty_price() {
        let msg = liquidation_msg_from_event(&liquidation_event("Buy")).unwrap();
        match msg {
            crate::database::MarketDataMsg::Liquidation {
                ts_ms,
                symbol,
                side,
                qty,
                price,
            } => {
                assert_eq!(ts_ms, 1_700_000_000_123);
                assert_eq!(symbol, "BTCUSDT");
                assert_eq!(side, "Buy");
                assert!((qty - 0.25).abs() < f64::EPSILON);
                assert!((price - 64_000.0).abs() < f64::EPSILON);
            }
            _ => panic!("expected liquidation msg"),
        }
    }

    #[test]
    fn liquidation_msg_preserves_sell_side_qty_price() {
        let msg = liquidation_msg_from_event(&liquidation_event("Sell")).unwrap();
        match msg {
            crate::database::MarketDataMsg::Liquidation {
                side, qty, price, ..
            } => {
                assert_eq!(side, "Sell");
                assert!((qty - 0.25).abs() < f64::EPSILON);
                assert!((price - 64_000.0).abs() < f64::EPSILON);
            }
            _ => panic!("expected liquidation msg"),
        }
    }

    #[test]
    fn liquidation_msg_rejects_invalid_payload_metadata() {
        assert!(liquidation_msg_from_event(&liquidation_event("Unknown")).is_none());

        let mut event = liquidation_event("Buy");
        event.metadata.insert("qty".into(), "0".into());
        assert!(liquidation_msg_from_event(&event).is_none());

        let mut event = liquidation_event("Buy");
        event.last_price = f64::NAN;
        assert!(liquidation_msg_from_event(&event).is_none());
    }
}
