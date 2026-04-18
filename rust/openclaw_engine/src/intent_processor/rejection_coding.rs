//! Intent rejection reason codes — unified representation.
//! 意圖拒絕原因碼 — 統一表示。
//!
//! MODULE_NOTE (EN): E5-P1-8 extraction — consolidates every rejection
//! reason string constructed by the intent_processor pipeline into one
//! enum with formatter helpers. Each `format()` branch is byte-identical
//! to the literal `format!(...)` that previously lived inline in
//! `router.rs` / `gates.rs`, because the emitted strings are surfaced to
//! the Operator GUI, written into `trading.risk_verdicts.reason`, and
//! asserted on by test suites (`contains` / `starts_with`). Changing
//! them would silently regress audit-log semantics.
//!
//! MODULE_NOTE (中): E5-P1-8 抽離——將 intent_processor 管線所有拒絕原因
//! 字串統一成單一 enum + 格式化輔助方法。每一分支的輸出與原本 inline
//! 在 `router.rs` / `gates.rs` 的 `format!(...)` 逐 byte 一致：拒絕字串
//! 會流到 Operator GUI、寫入 `trading.risk_verdicts.reason`、且被測試
//! 以 `contains` / `starts_with` 釘住，任何字面改動會靜默破壞審計語義。
//!
//! Classification helpers (e.g. `is_cost_gate_reject`) are added so downstream
//! (Python API / learning pipeline) can switch on the coarse family without
//! re-parsing free-form prefixes.
//! 分類輔助（例如 `is_cost_gate_reject`）讓下游不必重新解析字串前綴即可區分
//! 大類。

use openclaw_core::guardian::GuardianResult;

/// Unified intent rejection code. Every variant maps to exactly one
/// byte-identical format string (see `format()`). No free-form strings —
/// callers outside this module should not construct rejection reasons
/// except through this enum.
/// 統一的意圖拒絕碼。每個 variant 對應唯一、逐 byte 固定的格式字串。
/// 本模組外不應再手寫拒絕原因。
#[derive(Debug, Clone)]
pub(super) enum RejectionCode {
    /// Gate 1: governance hub not authorized (paper or exchange path).
    /// Gate 1：治理授權未取得。
    GovernanceNotAuthorized,

    /// Gate 1.5: same-direction duplicate open.
    /// Gate 1.5：同向重複開倉。
    DuplicatePosition {
        symbol: String,
        existing_is_long: bool,
        existing_qty: f64,
    },

    /// Gate 1.6: paper-mode negative-balance guard.
    /// Gate 1.6：paper 模式負餘額守門。
    InsufficientBalance { balance: f64 },

    /// Gate 2: Guardian verdict == Rejected. Upstream reasons preserved
    /// via `Debug` format on `Vec<String>`.
    /// Gate 2：Guardian 判定拒絕；上游 reasons 以 Debug 格式保留。
    GuardianRejected { reasons: Vec<String> },

    /// PNL-1: post-sizing qty rounded to 0 (dust / tiny balance).
    /// PNL-1：sizing 後 qty 為 0（塵埃倉位）。
    QtyZero {
        final_qty: f64,
        kelly_qty: f64,
        p1_max_qty: f64,
        balance: f64,
        price: f64,
    },

    /// Gate 2.7: order admission check rejected (daily loss / leverage / etc.).
    /// Upstream reason string from `check_order_allowed` preserved.
    /// Gate 2.7：訂單准入檢查拒絕；上游 reason 原樣透傳。
    RiskGate { reason: String },

    /// BLOCKER-3 D15: cross-engine global notional cap breach.
    /// BLOCKER-3 D15：跨引擎全局名目上限。
    GlobalNotionalCap {
        projected: f64,
        cap: f64,
        current: f64,
    },

    /// Gate 3: confidence below min_confidence threshold.
    /// Gate 3：confidence 低於最小門檻。
    CostGateConfidence { confidence: f64, min_confidence: f64 },

    /// Gate 3 · SEC-11: ATR unavailable fail-closed.
    /// Gate 3 · SEC-11：ATR 不可用失敗關閉。
    CostGateAtrUnavailable,

    /// Gate 3 cost-gate JS variant — paper mode positive-edge below threshold.
    /// Gate 3 cost-gate JS — paper 正 edge 未達門檻。
    CostGateJsPaper {
        edge_bps: f64,
        threshold_bps: f64,
        fee_bps: f64,
        win_rate: f64,
        slippage_bps: f64,
    },

    /// Gate 3 cost-gate JS variant — demo mode positive-edge below threshold.
    /// Gate 3 cost-gate JS — demo 正 edge 未達門檻。
    CostGateJsDemoThreshold {
        edge_bps: f64,
        threshold_bps: f64,
        fee_bps: f64,
        win_rate: f64,
    },

    /// Gate 3 cost-gate JS variant — demo mode negative edge blocked.
    /// Gate 3 cost-gate JS — demo 負 edge 阻擋。
    CostGateJsDemoNegative { estimated_bps: f64 },

    /// Gate 3 cost-gate JS variant — live mode positive-edge below threshold.
    /// Gate 3 cost-gate JS — live 正 edge 未達門檻。
    CostGateJsLiveThreshold {
        edge_bps: f64,
        threshold_bps: f64,
        fee_bps: f64,
        win_rate: f64,
    },

    /// Gate 3 cost-gate JS variant — live mode negative edge fail-closed.
    /// Gate 3 cost-gate JS — live 負 edge 失敗關閉。
    CostGateJsLiveNegative { estimated_bps: f64 },

    /// Gate 3 cost-gate JS variant — live mode cold-start fail-closed.
    /// Gate 3 cost-gate JS — live 冷啟動失敗關閉。
    CostGateJsLiveColdStart,
}

impl RejectionCode {
    /// Produce the audit / DB / GUI reason string. Byte-identical to the
    /// previous inline `format!(...)` expressions in the intent_processor.
    /// Any change here is a behavior change — tests assert by substring
    /// (`contains` / `starts_with`) and DB rows are compared in analyses.
    ///
    /// 產生審計 / DB / GUI 所用的 reason 字串，與抽離前 inline 寫法
    /// 逐 byte 一致。更動任一格式 = 行為變更。
    pub(super) fn format(&self) -> String {
        match self {
            RejectionCode::GovernanceNotAuthorized => "governance_not_authorized".to_string(),

            RejectionCode::DuplicatePosition {
                symbol,
                existing_is_long,
                existing_qty,
            } => format!(
                "duplicate_position: {} already {} {}",
                symbol,
                if *existing_is_long { "LONG" } else { "SHORT" },
                existing_qty,
            ),

            RejectionCode::InsufficientBalance { balance } => {
                format!("insufficient_balance: {:.2}", balance)
            }

            RejectionCode::GuardianRejected { reasons } => {
                format!("guardian_rejected: {:?}", reasons)
            }

            RejectionCode::QtyZero {
                final_qty,
                kelly_qty,
                p1_max_qty,
                balance,
                price,
            } => format!(
                "qty_zero: final_qty={:.8} (kelly={:.8}, p1_cap={:.8}, balance=${:.2}, price=${:.2})",
                final_qty, kelly_qty, p1_max_qty, balance, price,
            ),

            RejectionCode::RiskGate { reason } => format!("risk_gate: {}", reason),

            RejectionCode::GlobalNotionalCap {
                projected,
                cap,
                current,
            } => format!(
                "global_notional_cap: projected {:.2} USDT > cap {:.2} USDT (current {:.2})",
                projected, cap, current,
            ),

            RejectionCode::CostGateConfidence {
                confidence,
                min_confidence,
            } => format!(
                "cost_gate: confidence {:.2} < min {:.2}",
                confidence, min_confidence,
            ),

            RejectionCode::CostGateAtrUnavailable => {
                "cost_gate: ATR unavailable (fail-closed, SEC-11)".to_string()
            }

            RejectionCode::CostGateJsPaper {
                edge_bps,
                threshold_bps,
                fee_bps,
                win_rate,
                slippage_bps,
            } => format!(
                "cost_gate(JS): edge={:.2}bps < threshold={:.2}bps \
                 (fee={:.2}bps, wr={:.2}, slip={:.1}bps)",
                edge_bps, threshold_bps, fee_bps, win_rate, slippage_bps,
            ),

            RejectionCode::CostGateJsDemoThreshold {
                edge_bps,
                threshold_bps,
                fee_bps,
                win_rate,
            } => format!(
                "cost_gate(JS-demo): edge={:.2}bps < threshold={:.2}bps \
                 (fee={:.2}bps, wr={:.2})",
                edge_bps, threshold_bps, fee_bps, win_rate,
            ),

            RejectionCode::CostGateJsDemoNegative { estimated_bps } => format!(
                "cost_gate(JS-demo): estimated={:.2}bps < 0 — blocked / 負估計阻擋",
                estimated_bps,
            ),

            RejectionCode::CostGateJsLiveThreshold {
                edge_bps,
                threshold_bps,
                fee_bps,
                win_rate,
            } => format!(
                "cost_gate(JS-live): edge={:.2}bps < threshold={:.2}bps \
                 (fee={:.2}bps, wr={:.2})",
                edge_bps, threshold_bps, fee_bps, win_rate,
            ),

            RejectionCode::CostGateJsLiveNegative { estimated_bps } => format!(
                "cost_gate(JS-live): estimated={:.2}bps < 0 — fail-closed / 負估計失敗關閉",
                estimated_bps,
            ),

            RejectionCode::CostGateJsLiveColdStart => {
                "cost_gate(JS-live): no edge estimate — fail-closed (cold-start) / 無估計失敗關閉"
                    .to_string()
            }
        }
    }

    // ─── Classification helpers (coarse family predicates) ───
    // 分類輔助（粗類型判定）

    /// Any `cost_gate*` family rejection (confidence / ATR / JS variants).
    /// 任一 `cost_gate*` 家族拒絕。
    #[allow(dead_code)]
    pub(super) fn is_cost_gate_reject(&self) -> bool {
        matches!(
            self,
            RejectionCode::CostGateConfidence { .. }
                | RejectionCode::CostGateAtrUnavailable
                | RejectionCode::CostGateJsPaper { .. }
                | RejectionCode::CostGateJsDemoThreshold { .. }
                | RejectionCode::CostGateJsDemoNegative { .. }
                | RejectionCode::CostGateJsLiveThreshold { .. }
                | RejectionCode::CostGateJsLiveNegative { .. }
                | RejectionCode::CostGateJsLiveColdStart
        )
    }

    /// Guardian verdict == Rejected.
    /// Guardian 判定為拒絕。
    #[allow(dead_code)]
    pub(super) fn is_guardian_reject(&self) -> bool {
        matches!(self, RejectionCode::GuardianRejected { .. })
    }

    /// Pre-Guardian gate (governance / duplicate / insufficient balance).
    /// Pre-Guardian gate 系列。
    #[allow(dead_code)]
    pub(super) fn is_pre_guardian_gate(&self) -> bool {
        matches!(
            self,
            RejectionCode::GovernanceNotAuthorized
                | RejectionCode::DuplicatePosition { .. }
                | RejectionCode::InsufficientBalance { .. }
        )
    }

    /// Post-Guardian sizing / admission (qty_zero / risk_gate / global cap).
    /// Guardian 後的 sizing / admission 系列。
    #[allow(dead_code)]
    pub(super) fn is_sizing_or_admission_reject(&self) -> bool {
        matches!(
            self,
            RejectionCode::QtyZero { .. }
                | RejectionCode::RiskGate { .. }
                | RejectionCode::GlobalNotionalCap { .. }
        )
    }

    /// Coarse classification label used by analytics / test assertions as a
    /// short stable tag (not written to DB — the `format()` string is the
    /// canonical audit payload). Useful when downstream code wants to bucket
    /// rejections without substring-matching the formatted reason.
    /// 粗分類標籤（給分析 / 測試當短標籤用，不是 DB canonical 原因）。
    #[allow(dead_code)]
    pub(super) fn family(&self) -> &'static str {
        match self {
            RejectionCode::GovernanceNotAuthorized => "governance",
            RejectionCode::DuplicatePosition { .. } => "duplicate_position",
            RejectionCode::InsufficientBalance { .. } => "insufficient_balance",
            RejectionCode::GuardianRejected { .. } => "guardian",
            RejectionCode::QtyZero { .. } => "qty_zero",
            RejectionCode::RiskGate { .. } => "risk_gate",
            RejectionCode::GlobalNotionalCap { .. } => "global_notional_cap",
            RejectionCode::CostGateConfidence { .. }
            | RejectionCode::CostGateAtrUnavailable
            | RejectionCode::CostGateJsPaper { .. }
            | RejectionCode::CostGateJsDemoThreshold { .. }
            | RejectionCode::CostGateJsDemoNegative { .. }
            | RejectionCode::CostGateJsLiveThreshold { .. }
            | RejectionCode::CostGateJsLiveNegative { .. }
            | RejectionCode::CostGateJsLiveColdStart => "cost_gate",
        }
    }
}

/// Build a `GuardianRejected` rejection code from a `GuardianResult`.
/// Placed on the review side to keep callers terse:
///     `RejectionCode::from_guardian_review(&guardian_result)`
/// Clones `reasons` so the original review can still be captured into
/// `VerdictInfo` alongside.
/// 由 `GuardianResult` 建 `GuardianRejected`；clone reasons 不影響上游 capture。
impl RejectionCode {
    pub(super) fn from_guardian_review(review: &GuardianResult) -> Self {
        RejectionCode::GuardianRejected {
            reasons: review.reasons.clone(),
        }
    }
}

// ─── Unit tests — pin byte-identity of every variant's format string. ───
// 單元測試——釘住每個 variant 的 `format()` 輸出與抽離前字面完全一致。
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn governance_not_authorized_matches() {
        assert_eq!(
            RejectionCode::GovernanceNotAuthorized.format(),
            "governance_not_authorized",
        );
    }

    #[test]
    fn duplicate_position_matches() {
        let code = RejectionCode::DuplicatePosition {
            symbol: "BTCUSDT".into(),
            existing_is_long: true,
            existing_qty: 0.5,
        };
        assert_eq!(code.format(), "duplicate_position: BTCUSDT already LONG 0.5");

        let code_short = RejectionCode::DuplicatePosition {
            symbol: "ETHUSDT".into(),
            existing_is_long: false,
            existing_qty: 1.25,
        };
        assert_eq!(
            code_short.format(),
            "duplicate_position: ETHUSDT already SHORT 1.25",
        );
    }

    #[test]
    fn insufficient_balance_matches() {
        let code = RejectionCode::InsufficientBalance { balance: -12.3456 };
        assert_eq!(code.format(), "insufficient_balance: -12.35");
    }

    #[test]
    fn guardian_rejected_debug_format() {
        let code = RejectionCode::GuardianRejected {
            reasons: vec!["drawdown_breach".into(), "correlated_exposure".into()],
        };
        // {:?} on Vec<String> produces the Debug form used by the pre-extraction path.
        // {:?} 對 Vec<String> 的輸出與抽離前一致。
        assert_eq!(
            code.format(),
            "guardian_rejected: [\"drawdown_breach\", \"correlated_exposure\"]",
        );
    }

    #[test]
    fn qty_zero_matches() {
        let code = RejectionCode::QtyZero {
            final_qty: 0.0,
            kelly_qty: 0.00000001,
            p1_max_qty: 0.00000002,
            balance: 9.99,
            price: 123.45,
        };
        assert_eq!(
            code.format(),
            "qty_zero: final_qty=0.00000000 (kelly=0.00000001, p1_cap=0.00000002, \
             balance=$9.99, price=$123.45)",
        );
    }

    #[test]
    fn risk_gate_passthrough() {
        let code = RejectionCode::RiskGate {
            reason: "daily_loss_pct 3.00 > 2.00".into(),
        };
        assert_eq!(code.format(), "risk_gate: daily_loss_pct 3.00 > 2.00");
    }

    #[test]
    fn global_notional_cap_matches() {
        let code = RejectionCode::GlobalNotionalCap {
            projected: 10_100.0,
            cap: 10_000.0,
            current: 9_500.0,
        };
        assert_eq!(
            code.format(),
            "global_notional_cap: projected 10100.00 USDT > cap 10000.00 USDT (current 9500.00)",
        );
    }

    #[test]
    fn cost_gate_confidence_matches() {
        let code = RejectionCode::CostGateConfidence {
            confidence: 0.42,
            min_confidence: 0.50,
        };
        assert_eq!(code.format(), "cost_gate: confidence 0.42 < min 0.50");
    }

    #[test]
    fn cost_gate_atr_unavailable_matches() {
        assert_eq!(
            RejectionCode::CostGateAtrUnavailable.format(),
            "cost_gate: ATR unavailable (fail-closed, SEC-11)",
        );
    }

    #[test]
    fn cost_gate_js_paper_matches() {
        let code = RejectionCode::CostGateJsPaper {
            edge_bps: 5.0,
            threshold_bps: 10.5,
            fee_bps: 11.0,
            win_rate: 0.55,
            slippage_bps: 5.0,
        };
        assert_eq!(
            code.format(),
            "cost_gate(JS): edge=5.00bps < threshold=10.50bps \
             (fee=11.00bps, wr=0.55, slip=5.0bps)",
        );
    }

    #[test]
    fn cost_gate_js_demo_threshold_matches() {
        let code = RejectionCode::CostGateJsDemoThreshold {
            edge_bps: 2.0,
            threshold_bps: 6.5,
            fee_bps: 5.0,
            win_rate: 0.5,
        };
        assert_eq!(
            code.format(),
            "cost_gate(JS-demo): edge=2.00bps < threshold=6.50bps \
             (fee=5.00bps, wr=0.50)",
        );
    }

    #[test]
    fn cost_gate_js_demo_negative_matches() {
        let code = RejectionCode::CostGateJsDemoNegative {
            estimated_bps: -12.5,
        };
        assert_eq!(
            code.format(),
            "cost_gate(JS-demo): estimated=-12.50bps < 0 — blocked / 負估計阻擋",
        );
    }

    #[test]
    fn cost_gate_js_live_threshold_matches() {
        let code = RejectionCode::CostGateJsLiveThreshold {
            edge_bps: 1.0,
            threshold_bps: 9.99,
            fee_bps: 7.7,
            win_rate: 0.6,
        };
        assert_eq!(
            code.format(),
            "cost_gate(JS-live): edge=1.00bps < threshold=9.99bps \
             (fee=7.70bps, wr=0.60)",
        );
    }

    #[test]
    fn cost_gate_js_live_negative_matches() {
        let code = RejectionCode::CostGateJsLiveNegative {
            estimated_bps: -3.1,
        };
        assert_eq!(
            code.format(),
            "cost_gate(JS-live): estimated=-3.10bps < 0 — fail-closed / 負估計失敗關閉",
        );
    }

    #[test]
    fn cost_gate_js_live_cold_start_matches() {
        assert_eq!(
            RejectionCode::CostGateJsLiveColdStart.format(),
            "cost_gate(JS-live): no edge estimate — fail-closed (cold-start) / 無估計失敗關閉",
        );
    }

    #[test]
    fn classification_helpers() {
        let cost_gate = RejectionCode::CostGateAtrUnavailable;
        assert!(cost_gate.is_cost_gate_reject());
        assert!(!cost_gate.is_guardian_reject());
        assert!(!cost_gate.is_pre_guardian_gate());
        assert!(!cost_gate.is_sizing_or_admission_reject());
        assert_eq!(cost_gate.family(), "cost_gate");

        let guardian = RejectionCode::GuardianRejected {
            reasons: vec!["x".into()],
        };
        assert!(guardian.is_guardian_reject());
        assert!(!guardian.is_cost_gate_reject());
        assert_eq!(guardian.family(), "guardian");

        let gov = RejectionCode::GovernanceNotAuthorized;
        assert!(gov.is_pre_guardian_gate());
        assert_eq!(gov.family(), "governance");

        let qty = RejectionCode::QtyZero {
            final_qty: 0.0,
            kelly_qty: 0.0,
            p1_max_qty: 0.0,
            balance: 0.0,
            price: 0.0,
        };
        assert!(qty.is_sizing_or_admission_reject());
        assert_eq!(qty.family(), "qty_zero");
    }
}
