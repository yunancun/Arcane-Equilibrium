//! REF-20 Sprint B2 R5-T1 — `ReplayStrategyAdapter` (REPLAY-PURE).
//! REF-20 Sprint B2 R5-T1 — `ReplayStrategyAdapter`（REPLAY-PURE）。
//!
//! MODULE_NOTE (EN): Wraps any production `Strategy` impl (Sprint B2 pilot:
//!   `grid_trading` + `ma_crossover`; rest deferred to Sprint C) so the
//!   **same** strategy logic can run inside `replay_runner` (Isolated
//!   profile, in-memory) without crossing any V3 §6.2 forbidden surface
//!   (no IPC server, no DB writer, no exchange dispatch, no Decision Lease,
//!   no live config mutation, no advisory write).
//!
//!   Pillars (PA design §4.1):
//!     1. Reuse `Strategy` trait directly (0 trait change, 0 strategy code change).
//!     2. `Box<dyn Strategy>` ownership (any current/future strategy fits).
//!     3. 0 side-effect contract — only an in-memory `Vec<DecisionTraceEntry>`.
//!     4. `ReplayProfile::Isolated` enforced at `new()` (defense-in-depth on
//!        top of `bin/replay_runner.rs::main`'s `fail_closed_assert_isolated`).
//!     5. Per-`Open` deterministic SHA-256 `intent_signature` for
//!        plan §6.R5 acceptance A4 (parameter-delta proof).
//!
//!   Lifecycle: `new(strategy, profile)` → `on_tick(ctx)*` → `into_trace()`.
//!
//! MODULE_NOTE (中)：包裝任一 production `Strategy` impl（Sprint B2 pilot：
//!   `grid_trading` + `ma_crossover`；其餘延 Sprint C），使**相同**策略邏輯可
//!   在 `replay_runner` 內執行（Isolated profile、in-memory），**不**跨越
//!   V3 §6.2 任一 forbidden surface（無 IPC server / DB writer / exchange
//!   dispatch / Decision Lease / live config mutation / advisory write）。
//!
//!   支柱（PA design §4.1）：(1) 直接複用 `Strategy` trait（0 trait/strategy 改動）
//!   (2) `Box<dyn Strategy>` 擁有權（任一現有/未來策略適配同 wrap 模式）
//!   (3) 0 副作用 — 僅持 in-memory `Vec<DecisionTraceEntry>`
//!   (4) `ReplayProfile::Isolated` 於 `new()` 強制（為 binary entry
//!   `fail_closed_assert_isolated` 之上的縱深防禦）
//!   (5) 每個 `Open` 計算確定性 SHA-256 `intent_signature`，供 plan §6.R5
//!   acceptance A4（parameter-delta proof）。
//!
//!   生命週期：`new(strategy, profile)` → `on_tick(ctx)*` → `into_trace()`。
//!
//! SPEC: REF-20 V3 §3 G7/G8 + §6.2 + §12 #11 + plan §6.R5 + PA §4.1.

use sha2::{Digest, Sha256};

use crate::intent_processor::OrderIntent;
use crate::replay::profile::{ReplayIsolationError, ReplayProfile};
use crate::strategies::{Strategy, StrategyAction};
use crate::tick_pipeline::TickContext;
use openclaw_core::alpha_surface::AlphaSurface;

// ─────────────────────────────────────────────────────────────────────────
// Public types / 公開型別
// ─────────────────────────────────────────────────────────────────────────

/// Per-tick trace entry (only ticks that emitted ≥1 action are recorded).
/// 逐 tick trace（僅發出 ≥1 個 action 的 tick 才記錄）。
#[derive(Debug, Clone, serde::Serialize)]
pub struct DecisionTraceEntry {
    /// Tick timestamp ms (mirrors `TickContext.timestamp_ms`).
    /// Tick 時間戳 ms（鏡射 `TickContext.timestamp_ms`）。
    pub ts_ms: i64,
    /// Symbol processed (mirrors `TickContext.symbol`).
    /// 處理的 symbol（鏡射 `TickContext.symbol`）。
    pub symbol: String,
    /// Strategy name at trace time (`Strategy::name()`).
    /// 紀錄時策略名（`Strategy::name()`）。
    pub strategy_name: String,
    /// Was `TickContext.indicators` populated (cheap proof of indicator wiring).
    /// `TickContext.indicators` 是否填值（indicator 接線最廉價證明）。
    pub indicators_present: bool,
    /// Per-action trace emitted on this tick.
    /// 此 tick 發出的逐動作 trace。
    pub actions_emitted: Vec<StrategyActionTrace>,
}

/// Lightweight per-action record. `Open` carries a deterministic SHA-256
/// hash so a parameter delta (e.g. `grid_count: 10 → 20`) flips the hash
/// (plan §6.R5 acceptance A4).
///
/// 輕量逐動作記錄。`Open` 攜帶確定性 SHA-256；參數差異（如 `grid_count: 10
/// → 20`）必翻轉 hash（plan §6.R5 acceptance A4）。
#[derive(Debug, Clone, serde::Serialize)]
pub enum StrategyActionTrace {
    Open {
        /// SHA-256 of `(symbol|is_long|strategy|order_type|conf:.4f|qty:.4e)`.
        /// `(symbol|is_long|strategy|order_type|conf:.4f|qty:.4e)` 的 SHA-256。
        intent_signature: String,
        symbol: String,
        is_long: bool,
        confidence: f64,
        qty: f64,
        strategy: String,
        order_type: String,
    },
    Close {
        symbol: String,
        confidence: f64,
        reason: String,
    },
}

/// Replay-side adapter — owns a strategy instance, records per-tick decisions.
/// Replay 端 adapter — 擁有策略 instance，記錄逐 tick 決策。
pub struct ReplayStrategyAdapter {
    /// Wrapped strategy — same type as live engine.
    /// 包裝的策略 — 與 live engine 同型別。
    strategy: Box<dyn Strategy>,
    /// Profile guard fixed at construction (`Isolated` only).
    /// Profile 守衛構造時固定（僅 `Isolated`）。
    profile: ReplayProfile,
    /// Append-only trace; `into_trace()` consumes.
    /// 唯增 trace；`into_trace()` 消費。
    decision_trace: Vec<DecisionTraceEntry>,
}

impl ReplayStrategyAdapter {
    /// Build new adapter; refuses non-`Isolated` profile.
    /// 建立新 adapter；拒絕非 `Isolated` profile。
    ///
    /// SAFETY / 不變量：此構造器是 V3 §6.2 縱深防禦；最權威 gate 仍是
    /// `bin/replay_runner.rs::main` 的 `fail_closed_assert_isolated()`。
    /// SAFETY: defense-in-depth for V3 §6.2; the authoritative gate stays
    /// at `bin/replay_runner.rs::main::fail_closed_assert_isolated()`.
    pub fn new(
        strategy: Box<dyn Strategy>,
        profile: ReplayProfile,
    ) -> Result<Self, ReplayIsolationError> {
        if !matches!(profile, ReplayProfile::Isolated) {
            return Err(ReplayIsolationError::WrongProfile { found: profile });
        }
        Ok(Self {
            strategy,
            profile,
            decision_trace: Vec::new(),
        })
    }

    /// Read-only profile getter (test + R5-T3 wire-up).
    /// 唯讀 profile getter（test + R5-T3 接線）。
    pub fn profile(&self) -> ReplayProfile {
        self.profile
    }

    /// Drive one tick through wrapped strategy, capture actions.
    /// Returned `Vec<StrategyAction>` is byte-equal to live `on_tick`.
    ///
    /// 驅動一個 tick 通過 wrapped strategy 並捕獲 action。回傳的
    /// `Vec<StrategyAction>` 與 live `on_tick` byte-equal。
    pub fn on_tick(&mut self, ctx: &TickContext<'_>) -> Vec<StrategyAction> {
        // W-AUDIT-8a Phase A：取 ctx.alpha_surface_ref（由 build_tick_context 構造）。
        let surface = ctx.alpha_surface_ref;
        let actions = self.strategy.on_tick(ctx, surface);
        // Skip empty-tick records to keep trace bounded.
        // 略過空 tick 以限制 trace 大小。
        if !actions.is_empty() {
            let action_traces: Vec<StrategyActionTrace> = actions
                .iter()
                .map(|a| match a {
                    StrategyAction::Open(intent) => StrategyActionTrace::Open {
                        intent_signature: compute_intent_signature(intent),
                        symbol: intent.symbol.clone(),
                        is_long: intent.is_long,
                        confidence: intent.confidence,
                        qty: intent.qty,
                        strategy: intent.strategy.clone(),
                        order_type: intent.order_type.clone(),
                    },
                    StrategyAction::Close {
                        symbol,
                        confidence,
                        reason,
                    } => StrategyActionTrace::Close {
                        symbol: symbol.clone(),
                        confidence: *confidence,
                        reason: reason.clone(),
                    },
                })
                .collect();
            self.decision_trace.push(DecisionTraceEntry {
                ts_ms: ctx.timestamp_ms as i64,
                symbol: ctx.symbol.to_string(),
                strategy_name: self.strategy.name().to_string(),
                indicators_present: ctx.indicators.is_some(),
                actions_emitted: action_traces,
            });
        }
        actions
    }

    /// Consume self, return accumulated decision trace.
    /// 消費 self，回傳累積決策 trace。
    pub fn into_trace(self) -> Vec<DecisionTraceEntry> {
        self.decision_trace
    }

    /// Number of trace entries collected so far (test helper).
    /// 至此累積的 trace entry 數（test helper）。
    pub fn trace_len(&self) -> usize {
        self.decision_trace.len()
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Helpers / 內部 helper
// ─────────────────────────────────────────────────────────────────────────

/// Compute SHA-256 of an `OrderIntent` for parameter-delta proof
/// (plan §6.R5 acceptance A4). Canonical bytes:
/// `"{symbol}|{is_long}|{strategy}|{order_type}|conf:{conf:.4}|qty:{qty:.4e}"`.
/// `confidence` is rounded to 4 decimals (avoid late-tick float drift),
/// `qty` uses 4-digit scientific (0.001% sizing change still flips hash but
/// 1e-9 noise rounds out). Returns 64-char lowercase hex.
///
/// 計算 `OrderIntent` 的 SHA-256 供 parameter-delta proof（plan §6.R5
/// acceptance A4）。canonical bytes 為
/// `"{symbol}|{is_long}|{strategy}|{order_type}|conf:{conf:.4}|qty:{qty:.4e}"`。
/// `confidence` 四捨五入到 4 位（避免後段 tick 浮點漂移）；`qty` 用 4 位尾數
/// 科學記號（0.001% sizing 改動仍翻轉 hash，1e-9 噪聲被 round out）。
/// 回傳 64 字小寫 hex。
fn compute_intent_signature(intent: &OrderIntent) -> String {
    let canonical = format!(
        "{}|{}|{}|{}|conf:{:.4}|qty:{:.4e}",
        intent.symbol,
        intent.is_long,
        intent.strategy,
        intent.order_type,
        intent.confidence,
        intent.qty,
    );
    let mut hasher = Sha256::new();
    hasher.update(canonical.as_bytes());
    let digest = hasher.finalize();
    // 32 bytes -> 64-char lowercase hex.
    // 32 bytes → 64 字小寫 hex。
    let mut out = String::with_capacity(64);
    for byte in digest.iter() {
        out.push_str(&format!("{:02x}", byte));
    }
    out
}

// ─────────────────────────────────────────────────────────────────────────
// Module-internal unit tests / 模組內部 unit test
//
// Acceptance-level proof (cross-language parameter delta, etc.) lives in
// `tests/replay/test_strategy_param_delta.py` (Sprint B2 R5-T7).
//
// 契約層 acceptance proof（跨語言 parameter delta 等）在 R5-T7
// `tests/replay/test_strategy_param_delta.py`。
// ─────────────────────────────────────────────────────────────────────────
#[cfg(test)]
mod tests {
    use super::*;

    /// Stub strategy: emits one `Open` per call with caller-supplied qty.
    /// 測試 stub：每次發出一個 `Open`，qty 由 caller 指定。
    struct StubStrategy {
        name_str: &'static str,
        active: bool,
        next_qty: f64,
    }

    impl Strategy for StubStrategy {
        fn name(&self) -> &str {
            self.name_str
        }
        fn is_active(&self) -> bool {
            self.active
        }
        fn set_active(&mut self, a: bool) {
            self.active = a;
        }
        fn declared_alpha_sources(&self) -> &[openclaw_core::alpha_surface::AlphaSourceTag] {
            const TAGS: &[openclaw_core::alpha_surface::AlphaSourceTag] =
                &[openclaw_core::alpha_surface::AlphaSourceTag::Ta1m];
            TAGS
        }
        fn on_tick(
            &mut self,
            ctx: &TickContext<'_>,
            _surface: &AlphaSurface<'_>,
        ) -> Vec<StrategyAction> {
            vec![StrategyAction::Open(OrderIntent {
                symbol: ctx.symbol.to_string(),
                is_long: true,
                qty: self.next_qty,
                confidence: 0.42,
                strategy: self.name_str.to_string(),
                order_type: "market".into(),
                limit_price: None,
                confluence_score: None,
                persistence_elapsed_ms: None,
                time_in_force: None,
                maker_timeout_ms: None,
            })]
        }
    }

    fn empty_signals() -> &'static [openclaw_core::signals::Signal] {
        &[]
    }

    fn ctx<'a>(symbol: &'a str, ts: u64) -> TickContext<'a> {
        TickContext {
            symbol,
            price: 100.0,
            timestamp_ms: ts,
            indicators: None,
            indicators_5m: None,
            signals: empty_signals(),
            h0_allowed: true,
            funding_rate: None,
            index_price: None,
            open_interest: None,
            best_bid: None,
            best_ask: None,
            tick_size: None,
            alpha_surface_ref: &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
        }
    }

    #[test]
    fn happy_path_records_open_with_signature() {
        // V3 §12 #11 invariant: Isolated profile is the only acceptable mode.
        // V3 §12 #11 不變量：Isolated profile 是唯一可接受模式。
        let stub = Box::new(StubStrategy {
            name_str: "stub_strat",
            active: true,
            next_qty: 1.0,
        });
        let mut adapter =
            ReplayStrategyAdapter::new(stub, ReplayProfile::Isolated).expect("Isolated accepts");
        assert_eq!(adapter.profile(), ReplayProfile::Isolated);

        let actions = adapter.on_tick(&ctx("BTCUSDT", 1_000));
        assert_eq!(actions.len(), 1);
        assert_eq!(adapter.trace_len(), 1);

        let trace = adapter.into_trace();
        assert_eq!(trace.len(), 1);
        let entry = &trace[0];
        assert_eq!(entry.symbol, "BTCUSDT");
        assert_eq!(entry.ts_ms, 1_000);
        assert_eq!(entry.strategy_name, "stub_strat");
        assert!(!entry.indicators_present);
        match &entry.actions_emitted[0] {
            StrategyActionTrace::Open {
                intent_signature,
                qty,
                ..
            } => {
                assert_eq!(intent_signature.len(), 64);
                assert!(intent_signature.chars().all(|c| c.is_ascii_hexdigit()));
                assert_eq!(*qty, 1.0);
            }
            other => panic!("expected Open trace, got {:?}", other),
        }
    }

    #[test]
    fn parameter_delta_flips_signature() {
        // Plan §6.R5 acceptance A4: same symbol/is_long/strategy/order_type
        // but different qty MUST flip intent_signature (and is deterministic).
        // Plan §6.R5 acceptance A4：symbol/is_long/strategy/order_type 同但
        // qty 不同必使 intent_signature 翻轉（且確定性）。
        let mk_intent = |q: f64| OrderIntent {
            symbol: "BTCUSDT".into(),
            is_long: true,
            qty: q,
            confidence: 0.5,
            strategy: "stub".into(),
            order_type: "market".into(),
            limit_price: None,
            confluence_score: None,
            persistence_elapsed_ms: None,
            time_in_force: None,
            maker_timeout_ms: None,
        };
        let sig_a = compute_intent_signature(&mk_intent(1.0));
        let sig_b = compute_intent_signature(&mk_intent(2.0));
        assert_ne!(sig_a, sig_b, "qty delta must flip signature");
        assert_eq!(sig_a, compute_intent_signature(&mk_intent(1.0)));
    }

    #[test]
    fn non_isolated_profile_rejected() {
        // V3 §6.2 defense-in-depth: refuse Live/LiveDemo/PaperLegacy at construction.
        // Note: `unwrap_err()` would require Debug bound on `Ok` variant; since
        // `Box<dyn Strategy>` is not Debug, we pattern-match explicitly.
        // V3 §6.2 縱深防禦：構造時拒絕 Live/LiveDemo/PaperLegacy。
        // 註：`unwrap_err()` 需 Ok 變體實作 Debug；`Box<dyn Strategy>` 非 Debug，
        // 故顯式 pattern-match。
        for forbidden in [
            ReplayProfile::Live,
            ReplayProfile::LiveDemo,
            ReplayProfile::PaperLegacy,
        ] {
            let stub = Box::new(StubStrategy {
                name_str: "stub",
                active: true,
                next_qty: 1.0,
            });
            match ReplayStrategyAdapter::new(stub, forbidden) {
                Err(ReplayIsolationError::WrongProfile { found }) => {
                    assert_eq!(
                        found, forbidden,
                        "expected WrongProfile{{found:{:?}}}, got found={:?}",
                        forbidden, found
                    );
                }
                Ok(_) => panic!("expected WrongProfile rejection for {:?}", forbidden),
            }
        }
    }
}
