//! Post-submit maker-order rejection classification.
//! 提交後 maker 掛單拒絕分類。
//!
//! MODULE_NOTE (EN): EDGE-P2-3 Phase 1B-2 extraction. Bybit signals maker-path
//! rejections (notably `EC_PostOnlyWillTakeLiquidity`) via the Private WS
//! `order` event's `rejectReason` field — REST returns `retCode=0` on submit
//! because the order was structurally accepted before the matching engine
//! discovered it would cross the book. This module maps the free-form string
//! into a coarse semantic category so downstream (audit log, strategy
//! cooldown, learning pipeline) can switch without re-parsing. Strategy
//! wiring to consume the classification lands in Phase 1B-3 alongside the
//! timeout-sweep / cancel-by-link-id plumbing; Phase 1B-2 is observability +
//! classification only (zero behavior change in strategies).
//!
//! MODULE_NOTE (中): EDGE-P2-3 Phase 1B-2 抽離。Bybit 對 maker 路徑的拒絕
//! （尤其 `EC_PostOnlyWillTakeLiquidity`）透過 Private WS `order` 事件的
//! `rejectReason` 傳達——REST 回 retCode=0 是因下單結構接受、匹配引擎才發現
//! 會越過 book。本模組把自由字串映射為粗分類，下游（審計日誌、策略 cooldown、
//! 學習管線）可直接 switch。策略消費接線延後到 1B-3，本次僅 observability +
//! classification（策略行為零變更）。
//!
//! Canonical strings — sourced from Bybit V5 docs cross-referenced with BB
//! sub-agent audit (`docs/audits/2026-04-20--edge_p2_3_phase1b_bybit_postonly_audit.md`):
//! 標準字串（參見 Bybit V5 官文 + BB 審計）：
//!
//! | rejectReason | Category |
//! |--------------|----------|
//! | `EC_PostOnlyWillTakeLiquidity` | PostOnlyCross |
//! | `EC_PerCancelRequest`          | SelfCancel    |
//! | `EC_CancelForNoFullFill`       | FokCancel     |
//! | `EC_ReachMaxPendingOrders`     | TooManyPending|
//! | `EC_Others` / empty            | Other         |

/// Coarse semantic category for a Bybit-side maker rejection reason string.
///
/// **Never** depend on byte-equality of the raw string downstream — Bybit has
/// occasionally rotated its reason enum without doc-releasing first. Match on
/// this category instead. Unknown strings fall into `Other(raw)` so the raw
/// payload is still auditable.
///
/// 粗分類。下游禁止直接 byte 比較原始字串——Bybit 有時未預告就換 enum。
/// 未知字串歸到 `Other(raw)`，原始值仍可被審計。
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum MakerRejectionCategory {
    /// PostOnly limit order would have executed as taker — Bybit rejected it
    /// to preserve maker semantics. Strategy should back off and recompute
    /// maker offset; usually paired with `reject_cooldown_until_ms`.
    /// PostOnly 限價單會以 taker 成交——Bybit 為保 maker 語意而拒絕。
    /// 策略應退避並重算 maker offset，通常伴隨 `reject_cooldown_until_ms`。
    PostOnlyCross,

    /// Caller-initiated cancel (our own cancel request completed). Noop at the
    /// strategy level — the cancel path already handles state reconciliation.
    /// 我方主動 cancel 的最終確認。策略層 noop。
    SelfCancel,

    /// PostOnly FOK failed to fully fill and was auto-cancelled. Treat as a
    /// non-fill; strategy may try again after cooldown. Distinct from
    /// PostOnlyCross because the order DID partially sit in the book.
    /// PostOnly FOK 未完全成交而被自動取消。策略視為未成交。
    FokCancel,

    /// Account-level backpressure — too many resting orders. Strategy must
    /// pause new maker submissions until existing orders clear.
    /// 帳戶級背壓——掛單數超上限。策略需暫停新 maker 提交直到現存訂單清空。
    TooManyPending,

    /// Unclassified / unknown string (includes `EC_Others`). Preserve raw
    /// payload so operator / audit log can inspect without guessing.
    /// 未分類（含 `EC_Others`）。保留原字串供審計檢視。
    Other(String),
}

impl MakerRejectionCategory {
    /// Whether this category represents a PostOnly-cross — the one case where
    /// maker strategies MUST back off to avoid burning the reject budget.
    /// 是否為 PostOnly-cross（maker 策略必須退避）。
    pub fn is_post_only_cross(&self) -> bool {
        matches!(self, MakerRejectionCategory::PostOnlyCross)
    }

    /// Whether this is a terminal account-level backpressure signal — every
    /// maker strategy should pause new submits until it clears.
    /// 是否為帳戶級背壓（所有 maker 策略皆須暫停）。
    pub fn is_backpressure(&self) -> bool {
        matches!(self, MakerRejectionCategory::TooManyPending)
    }

    /// Stable short label for logs / DB `reason` column. Keeps audit grep-able
    /// without requiring the raw Bybit string. `Other(raw)` preserves the raw
    /// payload for forensic inspection.
    /// 穩定短標籤（日誌/DB reason 欄）。`Other(raw)` 保留原字串便於鑑識。
    pub fn label(&self) -> String {
        match self {
            Self::PostOnlyCross => "post_only_cross".to_string(),
            Self::SelfCancel => "self_cancel".to_string(),
            Self::FokCancel => "fok_cancel".to_string(),
            Self::TooManyPending => "too_many_pending".to_string(),
            Self::Other(raw) => {
                if raw.is_empty() {
                    "other_empty".to_string()
                } else {
                    format!("other:{}", raw)
                }
            }
        }
    }
}

/// Classify a Bybit WS `order.rejectReason` string into a coarse category.
/// Matching is case-sensitive against Bybit's canonical `EC_*` enum; unknown
/// strings (including empty) fall through to `Other`.
///
/// 將 Bybit WS `order.rejectReason` 字串分類。大小寫敏感地匹配 `EC_*` enum；
/// 未知（含空字串）落到 `Other`。
pub fn classify(reject_reason: &str) -> MakerRejectionCategory {
    match reject_reason {
        "EC_PostOnlyWillTakeLiquidity" => MakerRejectionCategory::PostOnlyCross,
        "EC_PerCancelRequest" => MakerRejectionCategory::SelfCancel,
        "EC_CancelForNoFullFill" => MakerRejectionCategory::FokCancel,
        "EC_ReachMaxPendingOrders" => MakerRejectionCategory::TooManyPending,
        other => MakerRejectionCategory::Other(other.to_string()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_classify_post_only_cross() {
        assert_eq!(
            classify("EC_PostOnlyWillTakeLiquidity"),
            MakerRejectionCategory::PostOnlyCross
        );
        assert!(classify("EC_PostOnlyWillTakeLiquidity").is_post_only_cross());
        assert!(!classify("EC_PostOnlyWillTakeLiquidity").is_backpressure());
    }

    #[test]
    fn test_classify_self_cancel() {
        assert_eq!(
            classify("EC_PerCancelRequest"),
            MakerRejectionCategory::SelfCancel
        );
        assert!(!classify("EC_PerCancelRequest").is_post_only_cross());
    }

    #[test]
    fn test_classify_fok_cancel() {
        assert_eq!(
            classify("EC_CancelForNoFullFill"),
            MakerRejectionCategory::FokCancel
        );
    }

    #[test]
    fn test_classify_too_many_pending() {
        let c = classify("EC_ReachMaxPendingOrders");
        assert_eq!(c, MakerRejectionCategory::TooManyPending);
        assert!(c.is_backpressure());
    }

    #[test]
    fn test_classify_ec_others_preserves_raw() {
        let c = classify("EC_Others");
        match &c {
            MakerRejectionCategory::Other(raw) => assert_eq!(raw, "EC_Others"),
            _ => panic!("expected Other(EC_Others), got {:?}", c),
        }
        assert_eq!(c.label(), "other:EC_Others");
    }

    #[test]
    fn test_classify_empty_falls_through() {
        let c = classify("");
        assert_eq!(c, MakerRejectionCategory::Other(String::new()));
        assert_eq!(c.label(), "other_empty");
    }

    #[test]
    fn test_classify_unknown_string_preserved_verbatim() {
        // Regression guard: if Bybit rotates the enum (e.g. adds EC_FutureFeature),
        // the raw string must survive into the audit path.
        // 退化守護：Bybit 若輪替 enum，原字串必須倖存到審計。
        let c = classify("EC_SomeFutureBybitCode");
        assert!(matches!(c, MakerRejectionCategory::Other(_)));
        assert_eq!(c.label(), "other:EC_SomeFutureBybitCode");
    }

    #[test]
    fn test_labels_are_stable_short_strings() {
        // Tests downstream may grep / match these prefixes in the DB
        // `reason` column. Changing them is a behavior change.
        // 下游測試會 grep / match DB reason 欄的這些前綴。修改即行為變更。
        assert_eq!(
            classify("EC_PostOnlyWillTakeLiquidity").label(),
            "post_only_cross"
        );
        assert_eq!(classify("EC_PerCancelRequest").label(), "self_cancel");
        assert_eq!(classify("EC_CancelForNoFullFill").label(), "fok_cancel");
        assert_eq!(
            classify("EC_ReachMaxPendingOrders").label(),
            "too_many_pending"
        );
    }

    #[test]
    fn test_case_sensitivity() {
        // Bybit docs specify exact camelCase-prefixed `EC_*`. Lowercase should
        // NOT match — falls through to Other with raw preserved.
        // Bybit 文件指定精確 `EC_*` 格式，小寫不匹配（落到 Other）。
        let c = classify("ec_postonlywilltakeliquidity");
        assert!(matches!(c, MakerRejectionCategory::Other(_)));
    }
}
