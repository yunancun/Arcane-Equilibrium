//! REF-20 Sprint C R6 W2 R0-T0 — replay apply_fill module (extracted from runner.rs).
//! REF-20 Sprint C R6 W2 R0-T0 — replay apply_fill 模組（自 runner.rs 抽出）。
//!
//! MODULE_NOTE (EN):
//!   This module hosts the per-intent fill mechanics that the replay
//!   `IsolatedPipeline` invokes during `execute_adapter_pipeline`. It was
//!   carved out of `runner.rs` (1992 LOC pre-W2) so that R6-T4+ logic can
//!   land without breaking the §九 2000-LOC cap. R0-T0 is a **mechanical**
//!   refactor — every byte of behaviour, every test, every public/private
//!   API surface stays byte-equal. No fee/slippage formulas were touched.
//!
//!   What lives here (carved from runner.rs Sprint C R6-T1+T2 IMPL):
//!     1. Fee/slippage helpers (`replay_fee_rate_for_tif`,
//!        `replay_slippage_bps_for_tif`, `apply_slippage_to_price`) +
//!        `DEFAULT_TAKER_FEE_RATE` / `DEFAULT_MAKER_FEE_RATE` constants
//!        mirroring `crate::account_manager` defaults byte-equal.
//!     2. `IsolatedPipeline::process_open_intent` — Strategy `Open` →
//!        6-Gate risk → Accepted (real fill, qty>0) or Rejected
//!        (ghost row, qty=0; PA §6.1 contract).
//!     3. `IsolatedPipeline::process_close_intent` — Strategy `Close` →
//!        realise PnL on existing position (taker-pricing per
//!        `strategies/mod.rs:51` "Close bypasses governance gates").
//!     4. `IsolatedPipeline::apply_fill_open` — open-side snapshot mutation
//!        (extend, reduce, or fresh insert; mirrors `paper_state` semantics
//!        WITHOUT importing `paper_state`).
//!     5. `IsolatedPipeline::apply_fill_close` — close-side snapshot mutation
//!        (realise PnL = (fill - entry) × qty for long; sign-flipped for
//!        short).
//!
//!   What stays in `runner.rs` (this commit's deliberate boundary):
//!     - `IsolatedPipeline` struct + public lifecycle: `build_isolated_pipeline`,
//!       `with_adapter_pipeline`, `with_replay_fee_context`, `execute`,
//!       `execute_synthetic_walker`, `execute_adapter_pipeline`,
//!       `into_result`. R0-T0 deliberately keeps these together so the
//!       lifecycle remains visually contiguous; future extraction (e.g.
//!       `lifecycle.rs` for the synthetic walker) is a separate ticket.
//!
//!   Forbidden surface audit (V3 §6.2 — MUST stay green; 0 byte change vs
//!   pre-extraction baseline):
//!     - 0 use of `crate::paper_state` / `crate::canary_writer` /
//!       `crate::database` / `crate::ipc_server` / `crate::governance_hub` /
//!       `crate::live_authorization` / `crate::decision_lease`.
//!     - 0 use of `crate::bybit_*` / `crate::intent_processor::router`.
//!     - Allowed (replay-pure): `crate::account_manager::AccountManager`
//!       (read-only fee getters; `pub fn maker_fee/taker_fee`),
//!       `crate::config::SlippageConfig` (immutable snapshot;
//!       `pub fn lookup_rate`), `crate::order_manager::TimeInForce`
//!       (enum only — structural type).
//!     - Allowed (replay-pure): `crate::intent_processor::OrderIntent`
//!       (struct only — same posture runner.rs already has, no
//!       `IntentProcessor` logic pulled).
//!
//!   Why an `impl IsolatedPipeline` block in a sibling module:
//!     Rust permits multiple inherent `impl` blocks for one type to live in
//!     different files of the same crate (here: `crate::replay::*`). This
//!     keeps `IsolatedPipeline` field visibility unchanged (private) and
//!     lets the methods access fields directly (`self.paper_snapshot`,
//!     `self.balance`, etc.) without needing `pub(super)` getters/setters
//!     and without widening the public API. Free helpers
//!     (`replay_fee_rate_for_tif` etc.) are `pub(super)` so `runner.rs`
//!     unit tests can keep importing them via `super::*`.
//!
//! MODULE_NOTE (中):
//!   本模組存放 replay `IsolatedPipeline` 在 `execute_adapter_pipeline`
//!   呼叫的 per-intent 成交機制。自 `runner.rs`（W2 前 1992 LOC）抽出，
//!   讓 R6-T4+ 邏輯可在不破 §九 2000 LOC cap 的前提下落地。R0-T0 是
//!   **機械式** refactor — 行為、測試、公私 API 表面位元級不變；
//!   費率/滑點公式 0 改動。
//!
//!   本檔包含（自 runner.rs Sprint C R6-T1+T2 IMPL 抽出）：
//!     1. 費率/滑點輔助（`replay_fee_rate_for_tif` /
//!        `replay_slippage_bps_for_tif` / `apply_slippage_to_price`）+
//!        `DEFAULT_TAKER_FEE_RATE` / `DEFAULT_MAKER_FEE_RATE` 常量
//!        （位元級鏡射 `crate::account_manager` 預設）。
//!     2. `IsolatedPipeline::process_open_intent` — 策略 `Open` →
//!        6-Gate 風控 → Accepted（真 fill，qty>0）或 Rejected
//!        （ghost row，qty=0；PA §6.1 契約）。
//!     3. `IsolatedPipeline::process_close_intent` — 策略 `Close` →
//!        對既有倉位 realise PnL（taker 計價，per `strategies/mod.rs:51`
//!        「Close bypasses governance gates」）。
//!     4. `IsolatedPipeline::apply_fill_open` — 開倉側 snapshot mutation
//!        （加倉、減倉或新開；鏡射 `paper_state` 語意但**不** import）。
//!     5. `IsolatedPipeline::apply_fill_close` — 平倉側 snapshot mutation
//!        （realise PnL = (fill - entry) × qty 多倉；空倉符號反轉）。
//!
//!   仍留 `runner.rs`（本 commit 刻意邊界）：
//!     `IsolatedPipeline` struct + 公開生命週期：`build_isolated_pipeline`、
//!     `with_adapter_pipeline`、`with_replay_fee_context`、`execute`、
//!     `execute_synthetic_walker`、`execute_adapter_pipeline`、
//!     `into_result`。R0-T0 刻意保留這些函式同檔以使生命週期視覺連續；
//!     未來抽出（如 `lifecycle.rs` 抽 synthetic walker）為獨立 ticket。
//!
//!   禁忌 surface 稽核（V3 §6.2，**必**保綠；位元級 0 改動 vs 抽出前
//!   baseline）：
//!     - 0 引 `crate::paper_state` / `crate::canary_writer` /
//!       `crate::database` / `crate::ipc_server` / `crate::governance_hub` /
//!       `crate::live_authorization` / `crate::decision_lease`。
//!     - 0 引 `crate::bybit_*` / `crate::intent_processor::router`。
//!     - 允許（replay-pure）：`crate::account_manager::AccountManager`
//!       （唯讀費率 getter）、`crate::config::SlippageConfig`（不可變
//!       snapshot）、`crate::order_manager::TimeInForce`（純 enum）、
//!       `crate::intent_processor::OrderIntent`（純 struct，不引邏輯）。
//!
//!   為何 `impl IsolatedPipeline` 跨檔：Rust 允許同一型別的多個 inherent
//!   `impl` block 散在同一 crate 不同檔。此處保持 `IsolatedPipeline`
//!   欄位可見度不變（private），讓方法直接存取欄位，不必新增 `pub(super)`
//!   getter/setter，亦不擴大公開 API。自由函式（`replay_fee_rate_for_tif`
//!   等）採 `pub(super)`，使 runner.rs 單元測試能透過 `super::*` 繼續引用。
//!
//! SPEC: REF-20 V3 §6.1 + §6.2 + plan §6.R6 + Sprint C R6 W2 dispatch §1
//!       (R0-T0 LOC budget refactor) + R6-T1+T2 byte-equal contract.

use crate::intent_processor::OrderIntent;
use crate::replay::risk_adapter::{ReplayPosition, RiskDecision};
use crate::replay::runner::{IsolatedPipeline, SimulatedFill};

const ORDERBOOK_DEPTH_PARTICIPATION_CAP: f64 = 0.20;

// ─────────────────────────────────────────────────────────────────────────
// Sprint C R6-T1 fee + R6-T2 slippage helpers / R6-T1 費率 + R6-T2 滑點輔助
// ─────────────────────────────────────────────────────────────────────────
// Mirror the live `IntentProcessor::fee_rate_for_tif` +
// `slippage_rate_for_tif` byte-equal contract into the replay path so
// `simulated_fills.{fee, fee_rate, slippage_bps, liquidity_role}` reflect
// the live maker/taker + turnover-tier model. Replay is non-actionable —
// these helpers MUST NOT mutate live state and MUST NOT call Bybit
// endpoints (no `refresh_fee_rates`).
//
// 把 live `IntentProcessor::fee_rate_for_tif` + `slippage_rate_for_tif`
// 的 byte-equal 契約鏡射至 replay 端，讓
// `simulated_fills.{fee, fee_rate, slippage_bps, liquidity_role}` 反映 live
// 同一套 maker/taker + turnover-tier 模型。Replay 非 actionable — 本輔助
// **不**動 live state、**不**打 Bybit endpoint（無 `refresh_fee_rates`）。

/// Sprint C R6 default fee rates / 預設費率（鏡射 live `account_manager`
/// `DEFAULT_TAKER_FEE = 0.00055` / `DEFAULT_MAKER_FEE = 0.0002`）。
/// Kept local so the binary does not touch private `crate::account_manager`
/// state when the seed path is not wired in.
pub(crate) const DEFAULT_TAKER_FEE_RATE: f64 = 0.00055;
pub(crate) const DEFAULT_MAKER_FEE_RATE: f64 = 0.0002;

/// Sprint C R6-T1 — pick (fee_rate, liquidity_role) by TimeInForce.
/// Mirrors `IntentProcessor::fee_rate_for_tif` (intent_processor/mod.rs:1200).
/// PostOnly TIF → maker / Any other TIF (incl. None) → taker.
/// Resolution: `account_manager.maker_fee/taker_fee` if Some; else
/// `DEFAULT_MAKER_FEE_RATE` / `DEFAULT_TAKER_FEE_RATE`.
///
/// Sprint C R6-T1 — 依 TimeInForce 選 (fee_rate, liquidity_role)。
/// 鏡射 `IntentProcessor::fee_rate_for_tif`。PostOnly→maker / 其他（含 None）
/// →taker。優先序：有 Some 時用 `account_manager.maker_fee/taker_fee`；否則
/// 退回 `DEFAULT_*_FEE_RATE`。
///
/// SAFETY / 不變量：本 helper 不打任何 endpoint；replay 端 AccountManager
/// 由 caller `seed_default_fee_rates` 注入（dispatch §1）。
/// SAFETY: helper does NOT call any endpoint; replay-side AccountManager is
/// caller-pre-seeded via `seed_default_fee_rates` (dispatch §1).
pub(crate) fn replay_fee_rate_for_tif(
    account_manager: Option<&std::sync::Arc<crate::account_manager::AccountManager>>,
    symbol: &str,
    tif: Option<crate::order_manager::TimeInForce>,
) -> (f64, &'static str) {
    if matches!(tif, Some(crate::order_manager::TimeInForce::PostOnly)) {
        let rate = account_manager
            .map(|am| am.maker_fee(symbol))
            .unwrap_or(DEFAULT_MAKER_FEE_RATE);
        (rate, "maker")
    } else {
        let rate = account_manager
            .map(|am| am.taker_fee(symbol))
            .unwrap_or(DEFAULT_TAKER_FEE_RATE);
        (rate, "taker")
    }
}

/// Sprint C R6-T2 — compute signed slippage bps for an intent.
/// Mirrors `IntentProcessor::slippage_rate_for_tif` (intent_processor/mod.rs:1179).
/// PostOnly TIF → 0.0 (rests on book) / Otherwise turnover-tier lookup via
/// `SlippageConfig::lookup_rate`. Sign per dispatch §2: buy → +bps, sell → -bps.
/// `volume_24h <= 0.0` graceful → `default_rate=0.0005` = 5 bps fallback.
///
/// Sprint C R6-T2 — 計算 intent 的有號滑點 bps。鏡射
/// `IntentProcessor::slippage_rate_for_tif`。PostOnly→0；其他經
/// `SlippageConfig::lookup_rate`。符號（dispatch §2）：買 +、賣 -。
/// `volume_24h <= 0.0` graceful → 5 bps default fallback。
pub(crate) fn replay_slippage_bps_for_tif(
    slippage_config: &crate::config::SlippageConfig,
    tif: Option<crate::order_manager::TimeInForce>,
    volume_24h: f64,
    is_long: bool,
) -> f64 {
    if matches!(tif, Some(crate::order_manager::TimeInForce::PostOnly)) {
        return 0.0;
    }
    let bps = slippage_config.lookup_rate(volume_24h) * 10_000.0;
    if is_long {
        bps
    } else {
        -bps
    }
}

/// Sprint C R6-T2 — apply signed slippage_bps to a reference price.
/// fill_price = reference_price × (1 + slippage_bps / 10_000.0).
/// `slippage_bps == 0` (PostOnly) → fill_price == reference_price.
/// Sprint C R6-T2 — 套用有號 slippage_bps 至參考價。
/// `slippage_bps == 0`（PostOnly）→ fill_price == reference_price。
pub(crate) fn apply_slippage_to_price(reference_price: f64, slippage_bps: f64) -> f64 {
    reference_price * (1.0 + slippage_bps / 10_000.0)
}

/// REF-21 Wave C1: anchor taker reference prices to fixture BBO when present.
/// Buy/taker fills must not be priced below best ask; sell/taker fills must
/// not be priced above best bid. Invalid/missing BBO keeps the existing
/// reference price so legacy fixtures remain usable and explicitly rely on
/// slippage floors rather than fabricated microstructure.
pub(crate) fn bbo_anchor_taker_reference_price(
    reference_price: f64,
    best_bid: Option<f64>,
    best_ask: Option<f64>,
    is_buy: bool,
) -> f64 {
    let (Some(bid), Some(ask)) = (best_bid, best_ask) else {
        return reference_price;
    };
    if !bid.is_finite() || !ask.is_finite() || bid <= 0.0 || ask <= 0.0 || bid > ask {
        return reference_price;
    }
    if is_buy {
        reference_price.max(ask)
    } else {
        reference_price.min(bid)
    }
}

#[derive(Debug, Clone, Copy)]
struct PartialFillDecision {
    filled_qty: f64,
    requested_qty: f64,
    fill_ratio: f64,
    fill_status: &'static str,
    model_status: &'static str,
    depth_available_qty: Option<f64>,
}

fn partial_fill_decision(
    requested_qty: f64,
    is_buy: bool,
    tif: Option<crate::order_manager::TimeInForce>,
    bid_size: Option<f64>,
    ask_size: Option<f64>,
    bid_depth_5: Option<f64>,
    ask_depth_5: Option<f64>,
) -> PartialFillDecision {
    let requested_qty = if requested_qty.is_finite() && requested_qty > 0.0 {
        requested_qty
    } else {
        0.0
    };
    if requested_qty <= 0.0 {
        return PartialFillDecision {
            filled_qty: 0.0,
            requested_qty,
            fill_ratio: 0.0,
            fill_status: "rejected",
            model_status: "invalid_requested_qty",
            depth_available_qty: None,
        };
    }
    if matches!(tif, Some(crate::order_manager::TimeInForce::PostOnly)) {
        return PartialFillDecision {
            filled_qty: requested_qty,
            requested_qty,
            fill_ratio: 1.0,
            fill_status: "filled",
            model_status: "not_applicable_maker",
            depth_available_qty: None,
        };
    }
    let depth = if is_buy {
        positive_finite_opt(ask_depth_5).or_else(|| positive_finite_opt(ask_size))
    } else {
        positive_finite_opt(bid_depth_5).or_else(|| positive_finite_opt(bid_size))
    };
    let Some(depth_qty) = depth else {
        return PartialFillDecision {
            filled_qty: requested_qty,
            requested_qty,
            fill_ratio: 1.0,
            fill_status: "filled",
            model_status: "unavailable_without_orderbook_depth",
            depth_available_qty: None,
        };
    };
    let executable_qty = (depth_qty * ORDERBOOK_DEPTH_PARTICIPATION_CAP).max(0.0);
    let filled_qty = requested_qty.min(executable_qty);
    let fill_ratio = if requested_qty > 0.0 {
        (filled_qty / requested_qty).clamp(0.0, 1.0)
    } else {
        0.0
    };
    let fill_status = if filled_qty <= 0.0 {
        "partial_unfilled"
    } else if filled_qty + f64::EPSILON < requested_qty {
        "partial"
    } else {
        "filled"
    };
    let model_status = if fill_status == "filled" {
        "applied_full"
    } else {
        "applied_partial"
    };
    PartialFillDecision {
        filled_qty,
        requested_qty,
        fill_ratio,
        fill_status,
        model_status,
        depth_available_qty: Some(depth_qty),
    }
}

fn positive_finite_opt(value: Option<f64>) -> Option<f64> {
    value.filter(|item| item.is_finite() && *item > 0.0)
}

fn effective_ts_ms(ts_ms: i64, latency_ms: Option<u64>) -> Option<i64> {
    latency_ms
        .and_then(|latency| i64::try_from(latency).ok())
        .and_then(|latency| ts_ms.checked_add(latency))
        .or(Some(ts_ms))
}

// ─────────────────────────────────────────────────────────────────────────
// IsolatedPipeline apply_fill methods (extracted from runner.rs)
// IsolatedPipeline apply_fill 方法（自 runner.rs 抽出）
// ─────────────────────────────────────────────────────────────────────────

impl IsolatedPipeline {
    /// Sprint B2 R5-T3 — process a strategy `Open` intent through the
    /// 6-Gate risk adapter; emit either a real fill (qty>0) on Accepted or
    /// a ghost row (qty=0, per PA §6.1) on Rejected.
    ///
    /// Sprint B2 R5-T3 — 將策略 `Open` intent 經 6-Gate 風控 adapter 處理；
    /// Accepted 發真 fill（qty>0），Rejected 發 ghost row（qty=0，per PA §6.1）。
    pub(super) fn process_open_intent(
        &mut self,
        intent: &OrderIntent,
        ts_ms: i64,
        close_price: f64,
        best_bid: Option<f64>,
        best_ask: Option<f64>,
        bid_size: Option<f64>,
        ask_size: Option<f64>,
        bid_depth_5: Option<f64>,
        ask_depth_5: Option<f64>,
        atr: f64,
        tier_label: &str,
    ) {
        let snapshot = match self.paper_snapshot.as_ref() {
            Some(s) => s,
            None => return, // unreachable — guarded by execute()
        };
        let risk = match self.risk_adapter.as_ref() {
            Some(r) => r,
            None => return, // unreachable — paired with strategy_adapter
        };
        let decision = risk.evaluate(intent, snapshot, atr);
        // Sprint C R6-T1+T2: derive (fee_rate, liquidity_role, slippage_bps)
        // from intent.time_in_force. Used for both Accepted (qty>0) and
        // Rejected (qty=0 ghost) paths so ghost row carries counterfactual
        // fee classification (transparency for downstream attribution).
        // Sprint C R6-T1+T2：從 intent.time_in_force 派生 (fee_rate,
        // liquidity_role, slippage_bps)。Accepted (qty>0) 與 Rejected (qty=0
        // ghost) 兩路徑共用，使 ghost row 帶 counterfactual 費率分類。
        let (fee_rate, liquidity_role) = replay_fee_rate_for_tif(
            self.account_manager.as_ref(),
            &intent.symbol,
            intent.time_in_force,
        );
        let volume_24h = self.volume_24h.unwrap_or(0.0);
        let slippage_bps = replay_slippage_bps_for_tif(
            &self.slippage_config,
            intent.time_in_force,
            volume_24h,
            intent.is_long,
        );
        match decision {
            RiskDecision::Accepted { final_qty, .. } => {
                let partial = partial_fill_decision(
                    final_qty,
                    intent.is_long,
                    intent.time_in_force,
                    bid_size,
                    ask_size,
                    bid_depth_5,
                    ask_depth_5,
                );
                // Reference price: limit if present (PostOnly), else event close.
                // PostOnly slippage_bps=0 → fill_price == limit_price byte-equal
                // to Sprint A/B baseline.
                // 參考價：有 limit_price 取之（PostOnly），否則 event close。
                // PostOnly slippage_bps=0 → fill_price == limit_price byte-equal。
                let raw_reference_price = intent.limit_price.unwrap_or(close_price);
                let reference_price = if matches!(
                    intent.time_in_force,
                    Some(crate::order_manager::TimeInForce::PostOnly)
                ) {
                    raw_reference_price
                } else {
                    bbo_anchor_taker_reference_price(
                        raw_reference_price,
                        best_bid,
                        best_ask,
                        intent.is_long,
                    )
                };
                if matches!(
                    intent.time_in_force,
                    Some(crate::order_manager::TimeInForce::PostOnly)
                ) && !self.should_accept_maker_execution(&intent.symbol, ts_ms)
                {
                    self.fills.push(SimulatedFill {
                        ts_ms,
                        symbol: intent.symbol.clone(),
                        side: if intent.is_long { "long" } else { "short" }.to_string(),
                        qty: 0.0,
                        requested_qty: partial.requested_qty,
                        fill_ratio: 0.0,
                        fill_status: "maker_miss".to_string(),
                        price: reference_price,
                        evidence_source_tier: tier_label.to_string(),
                        fee: 0.0,
                        fee_rate,
                        slippage_bps,
                        liquidity_role: liquidity_role.to_string(),
                        partial_fill_model_status: partial.model_status.to_string(),
                        depth_available_qty: partial.depth_available_qty,
                        latency_ms: self.execution_latency_ms,
                        effective_ts_ms: effective_ts_ms(ts_ms, self.execution_latency_ms),
                    });
                    self.last_action = format!("maker_miss:{}", intent.symbol);
                    return;
                }
                let fill_price = apply_slippage_to_price(reference_price, slippage_bps);
                let fee = partial.filled_qty * fill_price * fee_rate;
                self.fills.push(SimulatedFill {
                    ts_ms,
                    symbol: intent.symbol.clone(),
                    side: if intent.is_long { "long" } else { "short" }.to_string(),
                    qty: partial.filled_qty,
                    requested_qty: partial.requested_qty,
                    fill_ratio: partial.fill_ratio,
                    fill_status: partial.fill_status.to_string(),
                    price: fill_price,
                    evidence_source_tier: tier_label.to_string(),
                    fee,
                    fee_rate,
                    slippage_bps,
                    liquidity_role: liquidity_role.to_string(),
                    partial_fill_model_status: partial.model_status.to_string(),
                    depth_available_qty: partial.depth_available_qty,
                    latency_ms: self.execution_latency_ms,
                    effective_ts_ms: effective_ts_ms(ts_ms, self.execution_latency_ms),
                });
                if partial.filled_qty > 0.0 {
                    // Tier A T2.5：傳入 intent.strategy 寫進 ReplayPosition.owner_strategy。
                    self.apply_fill_open(
                        &intent.symbol,
                        intent.is_long,
                        partial.filled_qty,
                        fill_price,
                        fee,
                        &intent.strategy,
                    );
                }
                self.last_action = if partial.fill_status == "partial" {
                    format!("open_partial:{}", intent.symbol)
                } else if partial.fill_status == "partial_unfilled" {
                    format!("open_unfilled:{}", intent.symbol)
                } else {
                    format!("open:{}", intent.symbol)
                };
            }
            RiskDecision::Rejected { gate, reason } => {
                // Ghost fill row (qty=0) preserves the rejected decision for
                // evidence trail (PA §6.1). qty=0 ⇒ fee=0, but fee_rate /
                // liquidity_role / slippage_bps reflect counterfactual cost.
                // Ghost fill row (qty=0) 保留被拒決策（PA §6.1）。qty=0 ⇒ fee=0；
                // fee_rate / liquidity_role / slippage_bps 反映 counterfactual。
                let _ = reason; // recorded via last_action below.
                let raw_reference_price = intent.limit_price.unwrap_or(close_price);
                let reference_price = if matches!(
                    intent.time_in_force,
                    Some(crate::order_manager::TimeInForce::PostOnly)
                ) {
                    raw_reference_price
                } else {
                    bbo_anchor_taker_reference_price(
                        raw_reference_price,
                        best_bid,
                        best_ask,
                        intent.is_long,
                    )
                };
                self.fills.push(SimulatedFill {
                    ts_ms,
                    symbol: intent.symbol.clone(),
                    side: if intent.is_long { "long" } else { "short" }.to_string(),
                    qty: 0.0,
                    requested_qty: 0.0,
                    fill_ratio: 0.0,
                    fill_status: "rejected".to_string(),
                    price: reference_price,
                    evidence_source_tier: tier_label.to_string(),
                    fee: 0.0,
                    fee_rate,
                    slippage_bps,
                    liquidity_role: liquidity_role.to_string(),
                    partial_fill_model_status: "not_evaluated_risk_reject".to_string(),
                    depth_available_qty: None,
                    latency_ms: self.execution_latency_ms,
                    effective_ts_ms: effective_ts_ms(ts_ms, self.execution_latency_ms),
                });
                self.last_action = format!("reject:{}:{}", intent.symbol, gate);
            }
        }
    }

    /// Sprint B2 R5-T3 — process a strategy `Close` intent: look up the
    /// existing position in `paper_snapshot`, realise PnL, mutate balance.
    /// No-op when symbol has no open position (matches live router behaviour).
    ///
    /// Sprint B2 R5-T3 — 處理策略 `Close` intent：查 `paper_snapshot` 既有
    /// 倉位、realise PnL、mutate balance。symbol 無倉時 no-op（對齊 live
    /// router 行為）。
    pub(super) fn process_close_intent(
        &mut self,
        symbol: &str,
        ts_ms: i64,
        close_price: f64,
        best_bid: Option<f64>,
        best_ask: Option<f64>,
        bid_size: Option<f64>,
        ask_size: Option<f64>,
        bid_depth_5: Option<f64>,
        ask_depth_5: Option<f64>,
        tier_label: &str,
    ) {
        let snapshot = match self.paper_snapshot.as_ref() {
            Some(s) => s,
            None => return,
        };
        let pos = match snapshot.get_position(symbol) {
            Some(p) => p.clone(),
            None => {
                self.last_action = format!("close_skip:{}", symbol);
                return;
            }
        };
        // Sprint C R6-T1+T2: Close has no OrderIntent/TIF — treat as taker
        // (live engine routes Close as market; strategies/mod.rs:51 "Close
        // bypasses governance gates"). Closing leg sign opposite open:
        // long pos→sell→-bps / short pos→buy→+bps.
        // Sprint C R6-T1+T2：Close 無 OrderIntent/TIF — 視為 taker
        // （live 預設 Close 走市價）。平倉方向與開倉相反：多倉→賣→-bps /
        // 空倉→買→+bps。
        let close_is_long = !pos.is_long;
        let (fee_rate, liquidity_role) = replay_fee_rate_for_tif(
            self.account_manager.as_ref(),
            symbol,
            None, // close has no TIF → taker path
        );
        let volume_24h = self.volume_24h.unwrap_or(0.0);
        let slippage_bps =
            replay_slippage_bps_for_tif(&self.slippage_config, None, volume_24h, close_is_long);
        let reference_price =
            bbo_anchor_taker_reference_price(close_price, best_bid, best_ask, close_is_long);
        let fill_price = apply_slippage_to_price(reference_price, slippage_bps);
        let partial = partial_fill_decision(
            pos.qty,
            close_is_long,
            None,
            bid_size,
            ask_size,
            bid_depth_5,
            ask_depth_5,
        );
        let fee = partial.filled_qty * fill_price * fee_rate;
        // Record close-side fill (qty>0 with side opposite to position).
        // 記 close-side fill（qty>0，side 與倉位反向）。
        self.fills.push(SimulatedFill {
            ts_ms,
            symbol: symbol.to_string(),
            side: if pos.is_long { "short" } else { "long" }.to_string(),
            qty: partial.filled_qty,
            requested_qty: partial.requested_qty,
            fill_ratio: partial.fill_ratio,
            fill_status: partial.fill_status.to_string(),
            price: fill_price,
            evidence_source_tier: tier_label.to_string(),
            fee,
            fee_rate,
            slippage_bps,
            liquidity_role: liquidity_role.to_string(),
            partial_fill_model_status: partial.model_status.to_string(),
            depth_available_qty: partial.depth_available_qty,
            latency_ms: self.execution_latency_ms,
            effective_ts_ms: effective_ts_ms(ts_ms, self.execution_latency_ms),
        });
        if partial.filled_qty > 0.0 {
            self.apply_fill_close(symbol, fill_price, fee, partial.filled_qty);
        }
        self.last_action = if partial.fill_status == "partial" {
            format!("close_partial:{}", symbol)
        } else if partial.fill_status == "partial_unfilled" {
            format!("close_unfilled:{}", symbol)
        } else {
            format!("close:{}", symbol)
        };
    }

    /// Sprint B2 R5-T3 — open-side snapshot mutation. Inserts/extends a
    /// position and deducts execution fee from the snapshot balance so
    /// `pnl_summary.net_pnl` is fee-net.
    ///
    /// Tier A T2.5：新增 `owner_strategy` 參數寫進 ReplayPosition，鏡射
    /// production `PaperPosition.owner_strategy` 的 first-write-wins 語義 —
    /// 同向加倉保留首次寫入者，減倉只 net qty 不改 owner。
    pub(super) fn apply_fill_open(
        &mut self,
        symbol: &str,
        is_long: bool,
        qty: f64,
        fill_price: f64,
        fee: f64,
        owner_strategy: &str,
    ) {
        let snap = match self.paper_snapshot.as_mut() {
            Some(s) => s,
            None => return,
        };
        if let Some(idx) = snap.positions.iter().position(|p| p.symbol == symbol) {
            // Same-symbol existing position → extend qty + recompute weighted
            // entry price (rare path — Gate 1.5 should already reject same-
            // direction adds; reducing path nets the qty).
            // 同 symbol 既有倉 → 擴 qty + 重算加權入場價（罕見路徑 — Gate
            // 1.5 應已拒同向加倉；減倉路徑 net qty）。
            // T2.5：first-write-wins — 既有倉位的 owner_strategy 不被覆寫。
            let pos = &mut snap.positions[idx];
            if pos.is_long == is_long {
                let new_qty = pos.qty + qty;
                if new_qty > 0.0 {
                    pos.entry_price = (pos.entry_price * pos.qty + fill_price * qty) / new_qty;
                    pos.qty = new_qty;
                }
            } else {
                // Reducing path: net qty.
                // 減倉路徑：net qty。
                if qty >= pos.qty {
                    let realised_per_unit = if pos.is_long {
                        fill_price - pos.entry_price
                    } else {
                        pos.entry_price - fill_price
                    };
                    snap.balance += realised_per_unit * pos.qty;
                    snap.positions.remove(idx);
                } else {
                    let realised_per_unit = if pos.is_long {
                        fill_price - pos.entry_price
                    } else {
                        pos.entry_price - fill_price
                    };
                    snap.balance += realised_per_unit * qty;
                    let after = &mut snap.positions[idx];
                    after.qty -= qty;
                }
            }
        } else {
            // Fresh open.
            // 全新開倉。
            // T2.5：寫入 owner_strategy（intent.strategy.clone() upstream）。
            snap.positions.push(ReplayPosition {
                symbol: symbol.to_string(),
                is_long,
                qty,
                entry_price: fill_price,
                owner_strategy: owner_strategy.to_string(),
            });
        }
        snap.balance -= fee;
        self.balance = snap.balance;
    }

    /// Sprint B2 R5-T3 — close-side snapshot mutation. Realises PnL =
    /// (fill_price - entry_price) * qty (long; sign-flipped for short),
    /// removes position, updates balance, and deducts the close-side fee.
    pub(super) fn apply_fill_close(
        &mut self,
        symbol: &str,
        fill_price: f64,
        fee: f64,
        filled_qty: f64,
    ) {
        let snap = match self.paper_snapshot.as_mut() {
            Some(s) => s,
            None => return,
        };
        if let Some(idx) = snap.positions.iter().position(|p| p.symbol == symbol) {
            let pos = snap.positions[idx].clone();
            let close_qty = filled_qty.min(pos.qty).max(0.0);
            if close_qty <= 0.0 {
                return;
            }
            // PnL = (fill - entry) * qty for long; (entry - fill) * qty for short.
            // PnL = (fill - entry) * qty 多倉；(entry - fill) * qty 空倉。
            let realised_per_unit = if pos.is_long {
                fill_price - pos.entry_price
            } else {
                pos.entry_price - fill_price
            };
            snap.balance += realised_per_unit * close_qty;
            snap.balance -= fee;
            if close_qty + f64::EPSILON >= pos.qty {
                snap.positions.remove(idx);
            } else if let Some(existing) = snap.positions.get_mut(idx) {
                existing.qty -= close_qty;
            }
        }
        self.balance = snap.balance;
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Module-internal unit tests / 模組內部 unit test
// ─────────────────────────────────────────────────────────────────────────
//
// R0-T0 boundary (R6 W2 §5): test functions are declared as a child module of
// `runner.rs` via sibling file `runner_tests.rs`, so they still reach
// IsolatedPipeline private fields and test helpers through `super::*`. The 4
// helpers (`replay_fee_rate_for_tif`, `replay_slippage_bps_for_tif`,
// `apply_slippage_to_price`, `DEFAULT_*_FEE_RATE`) remain visible via the
// same-crate `pub(crate)` visibility.
//
// R0-T0 邊界（R6 W2 §5）：test 函式透過 sibling `runner_tests.rs` 仍是
// `runner.rs` 的 child module，因此可用 `super::*` 觸碰 IsolatedPipeline
// private field 與 test helper。4 個 helper
//（`replay_fee_rate_for_tif`/`replay_slippage_bps_for_tif`/
// `apply_slippage_to_price`/`DEFAULT_*_FEE_RATE`）維持同 crate `pub(crate)`
// 可見。
