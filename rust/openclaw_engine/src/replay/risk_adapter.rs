//! REF-20 Sprint B2 R5-T2 — `ReplayRiskAdapter` (REPLAY-PURE).
//! REF-20 Sprint B2 R5-T2 — `ReplayRiskAdapter`（REPLAY-PURE）。
//!
//! MODULE_NOTE (EN): Replay-side mini-pipeline that mirrors the 8-Gate risk
//!   path in `intent_processor::router::process_with_features` (router.rs:184-455)
//!   without importing any V3 §6.2 forbidden surface.
//!
//!   Coverage (PA design §4.2):
//!     * Reproduced (replay-pure):
//!         Gate 1.5 (DuplicatePosition) / Gate 1.6 (InsufficientBalance) /
//!         Gate 2.0 (Guardian 4-check via `openclaw_core::guardian`) /
//!         Gate 2.5 (Kelly via `ml::kelly_sizer::compute_kelly_qty`) /
//!         Gate 2.6 (P1 hard cap = balance * p1_risk_pct / price) /
//!         Gate 2.7 (`risk_checks::check_order_allowed`).
//!     * Skipped (V3 §6.2):
//!         Gate 1.0 (governance auth) — replay assumes always-authorized
//!         since the binary entry has already passed
//!         `fail_closed_assert_isolated` + `forbidden_guard::enforce_at_startup`;
//!         calling `governance.is_authorized()` would force a forbidden
//!         `GovernanceCore` dependency.
//!         Gate 1.4 (Decision Lease) — V3 §6.2 #1 forbidden;
//!         `ReplayProfile::Isolated::requires_lease()` returns `false`,
//!         AMD-2026-05-02-01 retrofit feature flag is hard-OFF for replay.
//!
//!   Forbidden surface audit (V3 §6.2 — MUST stay green):
//!     - NO `crate::paper_state` (mutable global)
//!     - NO `crate::canary_writer` / `crate::database`
//!     - NO `crate::ipc_server`
//!     - NO `crate::governance_hub` / `governance_core::GovernanceCore`
//!       (Guardian from `openclaw_core::guardian` is allowed because it is
//!       itself a pure deterministic 4-check — not the live dispatcher)
//!     - NO `crate::live_authorization` / `crate::decision_lease`
//!     - NO `crate::bybit_rest_client` / `crate::bybit_private_ws`
//!     - NO `crate::intent_processor::router` (no transitive re-import)
//!
//!   Lifecycle: `new(profile, ...)` → `evaluate(intent, snapshot, atr)` (pure).
//!   State mutation (apply_fill etc.) belongs to R5-T3 `runner::IsolatedPipeline`.
//!
//! MODULE_NOTE (中)：replay 端 mini-pipeline，鏡射 `intent_processor::router::
//!   process_with_features`（router.rs:184-455）的 8-Gate 風控路徑，**不**匯入
//!   V3 §6.2 任一 forbidden surface。
//!
//!   覆蓋（PA design §4.2）：
//!     復刻：Gate 1.5（DuplicatePosition）/ Gate 1.6（InsufficientBalance）/
//!     Gate 2.0（Guardian 4-check 透過 `openclaw_core::guardian`）/
//!     Gate 2.5（Kelly 透過 `ml::kelly_sizer::compute_kelly_qty`）/
//!     Gate 2.6（P1 硬上限 = balance * p1_risk_pct / price）/
//!     Gate 2.7（`risk_checks::check_order_allowed`）。
//!     跳過（V3 §6.2）：
//!     Gate 1.0（治理授權）— replay 假設「永遠授權」（binary entry 已過
//!     `fail_closed_assert_isolated` + `forbidden_guard::enforce_at_startup`）；
//!     呼叫 `governance.is_authorized()` 會強引入禁忌的 `GovernanceCore` 依賴。
//!     Gate 1.4（Decision Lease）— V3 §6.2 #1 禁；
//!     `ReplayProfile::Isolated::requires_lease()` 回 `false`、
//!     AMD-2026-05-02-01 retrofit flag 對 replay 永為 OFF。
//!
//!   Forbidden surface 稽核（V3 §6.2，**必**保綠燈）：
//!     不引 `crate::paper_state`（可變全域）、不引 `crate::canary_writer` /
//!     `crate::database`、不引 `crate::ipc_server`、不引
//!     `crate::governance_hub` / `governance_core::GovernanceCore`
//!     （`openclaw_core::guardian` 純 helper 可引；Guardian 本身就是純確定性
//!     4-check）、不引 `crate::live_authorization` / `crate::decision_lease`、
//!     不引 `crate::bybit_rest_client` / `crate::bybit_private_ws`、
//!     不引 `crate::intent_processor::router`（不可遞迴 re-import）。
//!
//!   生命週期：`new(profile, ...)` → `evaluate(intent, snapshot, atr)`（純）。
//!   State mutation（apply_fill 等）屬 R5-T3 `runner::IsolatedPipeline`。
//!
//! SPEC: REF-20 V3 §3 G7/G8 + §6.2 + §12 #11 + §12 #14 + plan §6.R5 + PA §4.2.

use crate::config::RiskConfig;
use crate::intent_processor::OrderIntent;
use crate::ml::kelly_sizer::{compute_kelly_qty, KellyConfig, TradeStats};
use crate::replay::profile::{ReplayIsolationError, ReplayProfile};
use crate::risk_checks::check_order_allowed;
use openclaw_core::guardian::{
    ExistingPosition, Guardian, GuardianConfig, PortfolioContext, TradeIntentCheck, Verdict,
};

// ─────────────────────────────────────────────────────────────────────────
// Public types / 公開型別
// ─────────────────────────────────────────────────────────────────────────

/// Per-symbol position snapshot — replay-pure mirror of `paper_state::PaperPosition`.
/// 逐 symbol 持倉 snapshot — `paper_state::PaperPosition` 的 replay-pure 鏡射。
///
/// Sprint N+1 D+1 Tier A T2.5：`owner_strategy` 新增 — 為了讓 cross-strategy
/// attribution（例如 ma_crossover 打開 BTCUSDT、bb_reversion 後續 tick 看見
/// `ctx.position_state.owner_strategy == "ma_crossover"` → fail-closed skip）
/// 在 replay 內可重現，對齊 production `PaperPosition.owner_strategy` 語義。
/// `apply_fill_open` 寫入 `intent.strategy.clone()`，未提供時 fallback 空串
/// （與 production pre-Phase-2A 舊快照行為一致）。
#[derive(Debug, Clone)]
pub struct ReplayPosition {
    pub symbol: String,
    pub is_long: bool,
    pub qty: f64,
    pub entry_price: f64,
    /// Sprint N+1 D+1 Tier A T2.5：策略歸屬，鏡射 `PaperPosition.owner_strategy`。
    /// 由 `apply_fill_open` 從 `OrderIntent.strategy` 寫入。
    pub owner_strategy: String,
}

/// In-memory snapshot of paper state at evaluation time. R5-T3 owns
/// lifecycle (open/close, balance arithmetic). R5-T2 adapter is stateless.
///
/// 評估時 paper state 的 in-memory snapshot。R5-T3 擁有生命週期（開/平倉、
/// balance 算術）。R5-T2 adapter 無狀態。
///
/// SAFETY / 不變量：此 struct **絕不可** 匯入 `crate::paper_state::PaperState`，
/// 是 runner 從 in-memory replay 帳戶狀態建構的刻意並行 surface。
/// SAFETY: this struct **MUST NOT** import `crate::paper_state::PaperState`;
/// it is a deliberate parallel surface built by the runner from the
/// in-memory replay account state.
#[derive(Debug, Clone)]
pub struct ReplayPaperSnapshot {
    pub balance: f64,
    pub drawdown_pct: f64,
    pub positions: Vec<ReplayPosition>,
    /// Last-touched 全域 price 錨（pre-Tier A 既存 field；保留作 backward-compat
    /// fallback 與 with_adapter_pipeline fail-loud guard 條件）。
    /// 新代碼應優先寫入 `latest_price_by_symbol`，evaluate 端優先 per-symbol query。
    pub latest_price: Option<f64>,
    /// Sprint N+1 D+1 Tier A T5：per-symbol price anchor。鏡射 live
    /// `PaperState::latest_price(symbol)` 的逐 symbol 語意，避免 Gate 2.6
    /// P1 cap（`balance * p1_risk_pct / price`）誤用其他 symbol 的 last-touched
    /// price 當 anchor（原 bug：ETHUSDT intent 用 ADAUSDT 0.2717 算 cap → 3 億
    /// ETH-equivalent qty）。
    /// `runner.rs` 在 tick event ingestion 時 `insert(symbol, event.close)`；
    /// `apply_fill_open` / `apply_fill_close` 在 fill 後 `insert(symbol, fill_price)`。
    pub latest_price_by_symbol: std::collections::HashMap<String, f64>,
    /// Aggregate exposure %% (mirrors `IntentProcessor::compute_exposure_pct`).
    /// 總曝險 %（鏡射 `IntentProcessor::compute_exposure_pct`）。
    pub exposure_pct: f64,
    /// Correlated exposure % (mirrors `compute_correlated_exposure_pct`).
    /// 相關曝險 %（鏡射 `compute_correlated_exposure_pct`）。
    pub correlated_exposure_pct: f64,
    /// Notional leverage (mirrors `compute_leverage`).
    /// 名義槓桿（鏡射 `compute_leverage`）。
    pub leverage: f64,
    /// Daily realised loss % (mirrors `daily_loss_pct`).
    /// 每日已實現虧損 %（鏡射 `daily_loss_pct`）。
    pub daily_loss_pct: f64,
    /// Per-symbol Kelly stats (R5-T3 mutates; adapter reads only).
    /// 逐 symbol Kelly 統計（R5-T3 變更；adapter 僅讀）。
    pub trade_stats: Option<TradeStats>,
}

impl ReplayPaperSnapshot {
    /// Find existing position; mirrors `PaperState::get_position`.
    /// 查既有持倉；鏡射 `PaperState::get_position`。
    pub fn get_position(&self, symbol: &str) -> Option<&ReplayPosition> {
        self.positions.iter().find(|p| p.symbol == symbol)
    }

    /// Sprint N+1 D+1 Tier A T5：per-symbol price 查詢（fallback chain）。
    ///
    /// 優先 `latest_price_by_symbol.get(symbol)`（per-symbol anchor）；
    /// 缺值時 fallback 到全域 `latest_price`（last-touched，backward-compat）；
    /// 兩者皆缺時回 `None`（caller 端 `unwrap_or(0.0)` 觸發 Gate 2.6 fallback 至 kelly_qty）。
    ///
    /// 鏡射 live `PaperState::latest_price(symbol)` 的 per-symbol 語意，
    /// 與 `intent_processor::router.rs:364 paper_state.latest_price(&intent.symbol)`
    /// 對齊。
    pub fn latest_price_for(&self, symbol: &str) -> Option<f64> {
        self.latest_price_by_symbol
            .get(symbol)
            .copied()
            .or(self.latest_price)
    }
}

/// Final risk decision per `evaluate` call. R5-T3 will translate `Accepted`
/// into `SimulatedFill` and `Rejected` into a per-decision evidence row
/// (PA design §6.1, into `replay.simulated_fills.payload jsonb`).
///
/// 每次 `evaluate` 的最終風控裁定。R5-T3 會將 `Accepted` 轉為
/// `SimulatedFill`，`Rejected` 轉為 per-decision evidence row（PA design
/// §6.1，寫入 `replay.simulated_fills.payload jsonb`）。
#[derive(Debug, Clone, serde::Serialize)]
pub enum RiskDecision {
    Accepted {
        final_qty: f64,
        verdict: String, // "Approved" | "Modified"
        guardian_score: f64,
        kelly_qty: f64,
        p1_max_qty: f64,
    },
    Rejected {
        gate: String, // "1.5_dup" / "1.6_neg_balance" / "2.0_guardian" / ...
        reason: String,
    },
}

impl RiskDecision {
    /// Whether the decision was accepted (test + R5-T3 caller helper).
    /// 裁定是否接受（test + R5-T3 caller helper）。
    pub fn is_accepted(&self) -> bool {
        matches!(self, RiskDecision::Accepted { .. })
    }
}

/// Replay-side risk adapter; pure read-only `evaluate(...)` API.
/// Replay 端風控 adapter；純唯讀 `evaluate(...)` API。
pub struct ReplayRiskAdapter {
    profile: ReplayProfile,
    /// Reused `Guardian` from `openclaw_core` — same deterministic 4-check
    /// as live engine. NOT the live `GovernanceCore` (which would pull in
    /// IPC + lease + audit-writer dependencies forbidden by V3 §6.2).
    /// 復用 `openclaw_core` 的 `Guardian` — 與 live engine 同確定性 4-check。
    /// **非** live `GovernanceCore`（會拉入 V3 §6.2 禁的 IPC + lease + audit
    /// writer 依賴）。
    guardian: Guardian,
    /// RiskConfig snapshot fixed at construction (matches what
    /// `IntentProcessor` would have at the equivalent live tick).
    /// RiskConfig snapshot 構造時固定（對應 live 同 tick `IntentProcessor` 持有）。
    risk_config: RiskConfig,
    /// P1 hard-cap balance fraction (mirrors `IntentProcessor.p1_risk_pct`).
    /// P1 硬上限 balance 比例（鏡射 `IntentProcessor.p1_risk_pct`）。
    p1_risk_pct: f64,
    /// Optional Kelly config (None disables Gate 2.5; pass-through).
    /// 選用 Kelly 配置（None 停用 Gate 2.5，穿透）。
    kelly_config: Option<KellyConfig>,
}

impl ReplayRiskAdapter {
    /// Build new adapter; refuses non-`Isolated` profile.
    /// 建立新 adapter；拒絕非 `Isolated` profile。
    pub fn new(
        profile: ReplayProfile,
        guardian_config: GuardianConfig,
        risk_config: RiskConfig,
        p1_risk_pct: f64,
        kelly_config: Option<KellyConfig>,
    ) -> Result<Self, ReplayIsolationError> {
        if !matches!(profile, ReplayProfile::Isolated) {
            return Err(ReplayIsolationError::WrongProfile { found: profile });
        }
        Ok(Self {
            profile,
            guardian: Guardian::new(guardian_config),
            risk_config,
            p1_risk_pct,
            kelly_config,
        })
    }

    /// Read-only profile getter.
    /// 唯讀 profile getter。
    pub fn profile(&self) -> ReplayProfile {
        self.profile
    }

    /// Evaluate one intent through the 6 reproduced gates. Pure: `&self` and
    /// `&snapshot` — no mutation. `atr` is the same raw-price-unit ATR that
    /// `router.rs:373-385` uses to compute `atr_pct = atr / price`; pass
    /// `0.0` to skip volatility scaling (match live behaviour).
    ///
    /// 通過 6 個復刻 gate 評估一個 intent。純函式：`&self` 與 `&snapshot` —
    /// 無 mutation。`atr` 為 `router.rs:373-385` 計算 `atr_pct = atr / price`
    /// 用的原始價格單位 ATR；傳 `0.0` 即跳過波動率縮放（對齊 live）。
    pub fn evaluate(
        &self,
        intent: &OrderIntent,
        snapshot: &ReplayPaperSnapshot,
        atr: f64,
    ) -> RiskDecision {
        // ─── Gate 1.5: same-direction duplicate ───
        // ─── Gate 1.5：同向重複 ───
        if let Some(existing) = snapshot.get_position(&intent.symbol) {
            if existing.is_long == intent.is_long {
                return RiskDecision::Rejected {
                    gate: "1.5_dup".into(),
                    reason: format!(
                        "DuplicatePosition existing_is_long={} qty={}",
                        existing.is_long, existing.qty
                    ),
                };
            }
        }

        // ─── Gate 1.6: negative-balance guard ───
        // ─── Gate 1.6：負餘額守衛 ───
        // Opposite-side reduction stays allowed (matches router.rs:249).
        // 反向減倉路徑仍允許穿越（對齊 router.rs:249）。
        let opposite_existing_qty = snapshot
            .get_position(&intent.symbol)
            .filter(|p| p.is_long != intent.is_long)
            .map(|p| p.qty);
        let is_reducing = opposite_existing_qty.is_some();

        if snapshot.balance <= 0.0 && snapshot.get_position(&intent.symbol).is_none() {
            return RiskDecision::Rejected {
                gate: "1.6_neg_balance".into(),
                reason: format!("InsufficientBalance balance={}", snapshot.balance),
            };
        }

        // pre_guardian_qty mirrors router.rs:267-271.
        // pre_guardian_qty 鏡射 router.rs:267-271。
        let pre_guardian_qty = match opposite_existing_qty {
            Some(existing_qty) => intent.qty.min(existing_qty),
            None => intent.qty,
        };

        // ─── Gate 2.0: Guardian 4-check ───
        // Mirror router.rs:274-294 — reducing path clears positions + zeroes
        // leverage so Guardian's deterministic vetoes (designed for adding
        // risk) don't block survival path.
        // 鏡射 router.rs:274-294 — 減倉路徑清空 positions + 槓桿歸零，使
        // Guardian 防止「加槓桿」之確定性否決不擋住生存路徑。
        let positions_for_guardian: Vec<ExistingPosition> = if is_reducing {
            Vec::new()
        } else {
            snapshot
                .positions
                .iter()
                .map(|p| ExistingPosition {
                    symbol: p.symbol.clone(),
                    side: if p.is_long {
                        "Buy".into()
                    } else {
                        "Sell".into()
                    },
                })
                .collect()
        };
        let guardian_leverage = if is_reducing { 0.0 } else { snapshot.leverage };
        let drawdown = if is_reducing {
            0.0
        } else {
            snapshot.drawdown_pct
        };

        let ctx = PortfolioContext {
            drawdown_pct: drawdown,
            positions: positions_for_guardian,
        };
        let check = TradeIntentCheck {
            symbol: intent.symbol.clone(),
            side: if intent.is_long {
                "Buy".into()
            } else {
                "Sell".into()
            },
            leverage: guardian_leverage,
            qty: pre_guardian_qty,
        };
        let guardian_result = self.guardian.review(&check, &ctx);

        match guardian_result.verdict {
            Verdict::Rejected => {
                return RiskDecision::Rejected {
                    gate: "2.0_guardian".into(),
                    reason: guardian_result.reasons.join("; "),
                };
            }
            Verdict::Modified | Verdict::Approved => {}
        }

        let guardian_qty = guardian_result.modified_qty.unwrap_or(pre_guardian_qty);

        // ─── Gate 2.5: Kelly position sizing ───
        // ─── Gate 2.5：Kelly 倉位 ───
        // Tier A T5：per-symbol price anchor — 取 `latest_price_for(intent.symbol)`
        // 對齊 live `paper_state.latest_price(&intent.symbol)`；缺值時 fallback
        // 0.0 觸發 Gate 2.6 P1 cap fallback 至 kelly_qty 路徑（原本既有行為）。
        // 若 caller 未對該 symbol 預種任何 price 且未全域 fallback，會在
        // `with_adapter_pipeline` 守衛階段 fail-loud。
        let price = snapshot.latest_price_for(&intent.symbol).unwrap_or(0.0);
        let kelly_qty = if let Some(ref kelly_cfg) = self.kelly_config {
            let stats = snapshot.trade_stats.clone().unwrap_or_default();
            // GAP-4 mirror: real ATR% from atr param.
            // GAP-4 鏡射：從 atr 參數轉換為 ATR%。
            let atr_pct = if price > 0.0 && atr > 0.0 {
                atr / price
            } else {
                0.0
            };
            compute_kelly_qty(
                kelly_cfg,
                &stats,
                snapshot.balance,
                price,
                atr_pct,
                guardian_qty,
            )
        } else {
            guardian_qty
        };

        // ─── Gate 2.6: P1 hard cap = balance * p1_risk_pct / price ───
        // ─── Gate 2.6：P1 硬上限 = balance * p1_risk_pct / price ───
        let p1_max_qty = if price > 0.0 {
            snapshot.balance * self.p1_risk_pct / price
        } else {
            kelly_qty
        };
        let final_qty_pre_admission = if is_reducing {
            guardian_qty
        } else {
            kelly_qty.min(p1_max_qty)
        };

        // PNL-1 mirror: reject qty=0 ghost positions.
        // PNL-1 鏡射：拒絕 qty=0 幽靈倉。
        if !(final_qty_pre_admission > 0.0) {
            return RiskDecision::Rejected {
                gate: "2.6_qty_zero".into(),
                reason: format!(
                    "QtyZero final_qty={} kelly_qty={} p1_max_qty={} balance={} price={}",
                    final_qty_pre_admission, kelly_qty, p1_max_qty, snapshot.balance, price
                ),
            };
        }

        // ─── Gate 2.7: order admission risk check ───
        // ─── Gate 2.7：訂單准入風控 ───
        let admission = check_order_allowed(
            final_qty_pre_admission,
            price,
            snapshot.balance,
            snapshot.exposure_pct,
            snapshot.correlated_exposure_pct,
            snapshot.leverage,
            snapshot.daily_loss_pct,
            is_reducing,
            &self.risk_config,
        );
        if !admission.allowed {
            return RiskDecision::Rejected {
                gate: "2.7_admission".into(),
                reason: admission.reason,
            };
        }

        let verdict_str = match guardian_result.verdict {
            Verdict::Approved => "Approved".to_string(),
            Verdict::Modified => "Modified".to_string(),
            Verdict::Rejected => unreachable!("rejected handled above"),
        };

        RiskDecision::Accepted {
            final_qty: final_qty_pre_admission,
            verdict: verdict_str,
            guardian_score: guardian_result.risk_score,
            kelly_qty,
            p1_max_qty,
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Module-internal unit tests / 模組內部 unit test
//
// Acceptance-level proof (cross-language parameter delta, full 8-Gate wire-up)
// lives in `tests/replay/test_risk_param_delta.py` (Sprint B2 R5-T7).
//
// 契約層 acceptance proof（跨語言 parameter delta、完整 8-Gate 接線）在
// R5-T7 `tests/replay/test_risk_param_delta.py`。
// ─────────────────────────────────────────────────────────────────────────
#[cfg(test)]
mod tests {
    use super::*;

    fn mk_intent(symbol: &str, is_long: bool, qty: f64) -> OrderIntent {
        OrderIntent {
            symbol: symbol.into(),
            is_long,
            qty,
            confidence: 0.5,
            strategy: "stub".into(),
            order_type: "market".into(),
            limit_price: None,
            confluence_score: None,
            persistence_elapsed_ms: None,
            time_in_force: None,
            maker_timeout_ms: None,
        }
    }

    fn mk_snapshot(balance: f64, positions: Vec<ReplayPosition>) -> ReplayPaperSnapshot {
        // Tier A T5：default test snapshot 預種全域 latest_price=100.0 + 同值寫入
        // per-symbol map for "BTCUSDT" / "ETHUSDT" 兩個常用 test symbol；既有 test
        // 多以 BTCUSDT 為主，per-symbol lookup hit → 100.0；其他 symbol fallback
        // 走全域 latest_price=Some(100.0) 不變。
        let mut latest_price_by_symbol = std::collections::HashMap::new();
        latest_price_by_symbol.insert("BTCUSDT".to_string(), 100.0);
        latest_price_by_symbol.insert("ETHUSDT".to_string(), 100.0);
        ReplayPaperSnapshot {
            balance,
            drawdown_pct: 0.0,
            positions,
            latest_price: Some(100.0),
            latest_price_by_symbol,
            exposure_pct: 0.0,
            correlated_exposure_pct: 0.0,
            leverage: 0.0,
            daily_loss_pct: 0.0,
            trade_stats: None,
        }
    }

    fn mk_adapter(profile: ReplayProfile) -> Result<ReplayRiskAdapter, ReplayIsolationError> {
        ReplayRiskAdapter::new(
            profile,
            GuardianConfig::default(),
            RiskConfig::default(),
            0.02, // p1_risk_pct = 2% balance
            None, // skip Kelly to keep test deterministic
        )
    }

    #[test]
    fn happy_path_accepts_open() {
        // V3 §12 #11 invariant + plan §6.R5 acceptance: clean small open
        // qty=0.5 with balance=10000 + price=100 → P1 cap=2.0 (room left).
        // V3 §12 #11 不變量 + plan §6.R5：balance=10000 + price=100 + qty=0.5
        // → P1 cap=2.0（餘地充足）。
        let adapter = mk_adapter(ReplayProfile::Isolated).expect("Isolated accepts");
        assert_eq!(adapter.profile(), ReplayProfile::Isolated);
        let snap = mk_snapshot(10_000.0, Vec::new());
        let intent = mk_intent("BTCUSDT", true, 0.5);
        let decision = adapter.evaluate(&intent, &snap, 0.0);
        assert!(
            decision.is_accepted(),
            "expected Accepted, got {:?}",
            decision
        );
        match decision {
            RiskDecision::Accepted {
                final_qty,
                p1_max_qty,
                ..
            } => {
                assert!((p1_max_qty - 2.0).abs() < 1e-9);
                assert!((final_qty - 0.5).abs() < 1e-9);
            }
            _ => unreachable!(),
        }
    }

    #[test]
    fn gate_1_5_rejects_same_direction_duplicate() {
        // Mirror router.rs:225-238: same-direction position → reject.
        // 鏡射 router.rs:225-238：同向倉位 → 拒絕。
        let adapter = mk_adapter(ReplayProfile::Isolated).unwrap();
        let snap = mk_snapshot(
            10_000.0,
            vec![ReplayPosition {
                symbol: "BTCUSDT".into(),
                is_long: true,
                qty: 0.3,
                entry_price: 100.0,
                owner_strategy: String::new(),
            }],
        );
        let intent = mk_intent("BTCUSDT", true, 0.5);
        let decision = adapter.evaluate(&intent, &snap, 0.0);
        match decision {
            RiskDecision::Rejected { gate, reason } => {
                assert_eq!(gate, "1.5_dup");
                assert!(
                    reason.contains("DuplicatePosition"),
                    "reason should name duplicate, got {:?}",
                    reason
                );
            }
            other => panic!("expected Rejected@1.5_dup, got {:?}", other),
        }
    }

    #[test]
    fn gate_1_6_rejects_brand_new_open_when_balance_zero() {
        // Mirror router.rs:249-256: balance≤0 + no existing position → reject.
        // 鏡射 router.rs:249-256：balance≤0 + 無既有倉位 → 拒絕。
        let adapter = mk_adapter(ReplayProfile::Isolated).unwrap();
        let snap = mk_snapshot(0.0, Vec::new());
        let intent = mk_intent("BTCUSDT", true, 0.5);
        let decision = adapter.evaluate(&intent, &snap, 0.0);
        match decision {
            RiskDecision::Rejected { gate, .. } => {
                assert_eq!(gate, "1.6_neg_balance");
            }
            other => panic!("expected Rejected@1.6_neg_balance, got {:?}", other),
        }
    }

    #[test]
    fn non_isolated_profile_rejected_at_construction() {
        // V3 §6.2 defense-in-depth: refuse Live/LiveDemo/PaperLegacy. Mirrors
        // strategy_adapter parity. Pattern-match explicitly (Ok variant
        // contains a non-Debug field, so unwrap_err() does not compile).
        // V3 §6.2 縱深防禦：拒絕 Live/LiveDemo/PaperLegacy；與 strategy_adapter
        // 對稱。顯式 pattern-match（Ok 變體含非 Debug 欄位，unwrap_err() 不過編）。
        for forbidden in [
            ReplayProfile::Live,
            ReplayProfile::LiveDemo,
            ReplayProfile::PaperLegacy,
        ] {
            match mk_adapter(forbidden) {
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
