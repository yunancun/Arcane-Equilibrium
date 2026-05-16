//! Post-submit maker-order rejection classification.
//! 提交後 maker 掛單拒絕分類。
//!
//! MODULE_NOTE (EN): EDGE-P2-3 Phase 1B-2 extraction. Bybit signals maker-path
//! rejections (notably `EC_PostOnlyWillTakeLiquidity`) via the Private WS
//! `order` event's `rejectReason` field — REST returns `retCode=0` on submit
//! because the order was structurally accepted before the matching engine
//! discovered it would cross the book. This module maps the free-form string
//! into a coarse semantic category so downstream (audit log, strategy
//! cooldown, learning pipeline) can switch without re-parsing. Phase 1b also
//! keeps the close-maker fallback / rate-limit state machine here so entry
//! maker callbacks and close maker callbacks can share classifier vocabulary
//! without sharing cooldown state.
//!
//! MODULE_NOTE (中): EDGE-P2-3 Phase 1B-2 抽離。Bybit 對 maker 路徑的拒絕
//! （尤其 `EC_PostOnlyWillTakeLiquidity`）透過 Private WS `order` 事件的
//! `rejectReason` 傳達——REST 回 retCode=0 是因下單結構接受、匹配引擎才發現
//! 會越過 book。本模組把自由字串映射為粗分類，下游（審計日誌、策略 cooldown、
//! 學習管線）可直接 switch。Phase 1b 同時把 close-maker fallback / 限流退避
//! 狀態機放在這裡，讓 entry maker callback 與 close maker callback 共用分類詞彙，
//! 但不共用 cooldown state。
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

use std::collections::HashMap;

/// Initial close-maker rate-limit backoff for `EC_ReachMaxPendingOrders`.
/// `EC_ReachMaxPendingOrders` 的 close-maker 初始限流退避。
pub(crate) const CLOSE_MAKER_BACKOFF_INITIAL_MS: u64 = 1_000;
/// Exponential backoff cap for one symbol. / 單一 symbol 指數退避上限。
pub(crate) const CLOSE_MAKER_BACKOFF_MAX_MS: u64 = 60_000;
/// A quiet symbol resets to the initial 1s backoff after this age.
/// symbol 靜默超過此時間後重置回 1 秒初始退避。
pub(crate) const CLOSE_MAKER_BACKOFF_RESET_AFTER_MS: u64 = 300_000;
/// Distinct-symbol cascade detection window. / distinct symbol 級聯偵測窗口。
pub(crate) const CLOSE_MAKER_GLOBAL_CASCADE_WINDOW_MS: u64 = 60_000;
/// Distinct symbols in one minute required to trigger a global pause.
/// 1 分鐘內觸發全域暫停所需 distinct symbol 數。
pub(crate) const CLOSE_MAKER_GLOBAL_CASCADE_SYMBOLS: usize = 10;
/// Global close-maker pause duration after a cascade. / 級聯後全域 close-maker 暫停時長。
pub(crate) const CLOSE_MAKER_GLOBAL_PAUSE_MS: u64 = 300_000;

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

/// Which maker path consumed a rejection callback.
///
/// Entry and close maker paths intentionally keep separate cooldown state:
/// missing this side flag was the BB-MF-3 class of regressions where an entry
/// reject could freeze close emission.
///
/// maker 拒絕 callback 的消費側。entry / close maker 必須保留獨立 cooldown
/// state；缺少 side flag 會回到 BB-MF-3「entry reject 凍結 close」問題。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MakerOrderSide {
    Entry,
    Close,
}

/// V094 close-maker fallback reason strings.
///
/// Keep these labels aligned with the audit enum in the Phase 1b schema. They
/// are operational metadata, not a training feature surface.
///
/// V094 close-maker fallback 原因字串。此處需與 Phase 1b audit enum 對齊；
/// 它們是營運審計 metadata，不是訓練特徵。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CloseMakerFallbackReason {
    TimeoutTaker,
    PostOnlyReject,
    CancelGraceExpired,
    AckLost,
    RateLimitPauseGlobal,
    RateLimitBackoffPerSymbol,
    FastEscalateSafetyUpgrade,
    NotAttemptedSafetyPath,
    EngineShutdownSafety,
    FallbackToTakerMandatory,
}

impl CloseMakerFallbackReason {
    /// Stable V094 label for fills/audit details.
    /// 寫入 fills/audit details 的穩定 V094 標籤。
    pub fn as_str(self) -> &'static str {
        match self {
            Self::TimeoutTaker => "timeout_taker",
            Self::PostOnlyReject => "postonly_reject",
            Self::CancelGraceExpired => "cancel_grace_expired",
            Self::AckLost => "ack_lost",
            Self::RateLimitPauseGlobal => "rate_limit_pause_global",
            Self::RateLimitBackoffPerSymbol => "rate_limit_backoff_per_symbol",
            Self::FastEscalateSafetyUpgrade => "fast_escalate_safety_upgrade",
            Self::NotAttemptedSafetyPath => "not_attempted_safety_path",
            Self::EngineShutdownSafety => "engine_shutdown_safety",
            Self::FallbackToTakerMandatory => "fallback_to_taker_mandatory",
        }
    }

    /// Close-maker fallbacks must never silently abandon close execution.
    /// close-maker fallback 不可默默放棄平倉；此 helper 釘住該不變式。
    pub fn requires_market_fallback(self) -> bool {
        !matches!(self, Self::NotAttemptedSafetyPath)
    }
}

/// Rate-limit scope written to `details.rate_limit_scope`.
/// 寫入 `details.rate_limit_scope` 的限流範圍。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CloseMakerRateLimitScope {
    PerSymbol,
    Global,
}

impl CloseMakerRateLimitScope {
    /// Stable JSON label for audit details. / 審計 details JSON 的穩定標籤。
    pub fn as_str(self) -> &'static str {
        match self {
            Self::PerSymbol => "per_symbol",
            Self::Global => "global",
        }
    }
}

/// Deterministic close-maker fallback decision for a race/reject event.
///
/// This is intentionally side-effect free. Dispatch wiring can decide how to
/// cancel/re-submit, while tests can assert that every close-maker terminal
/// branch maps to a taker-market fallback reason.
///
/// close-maker race/reject 事件的純決策結果。dispatch 接線可自行執行 cancel /
/// market re-submit；測試則能釘住每條 close-maker terminal branch 都會映射到
/// taker market fallback 原因。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct CloseMakerFallbackDecision {
    pub reason: CloseMakerFallbackReason,
    pub side: MakerOrderSide,
    pub arm_cooldown: bool,
    pub rate_limit_scope: Option<CloseMakerRateLimitScope>,
    pub market_fallback_required: bool,
}

impl CloseMakerFallbackDecision {
    fn new(
        reason: CloseMakerFallbackReason,
        arm_cooldown: bool,
        rate_limit_scope: Option<CloseMakerRateLimitScope>,
    ) -> Self {
        Self {
            reason,
            side: MakerOrderSide::Close,
            arm_cooldown,
            rate_limit_scope,
            market_fallback_required: reason.requires_market_fallback(),
        }
    }
}

/// Close-maker race inputs for the pure fallback state machine.
/// close-maker fallback 純狀態機的 race/event 輸入。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CloseMakerFallbackEvent {
    FastEscalateSafetyUpgrade,
    Timeout,
    CancelGraceExpired,
    PostOnlyReject,
    TooManyPendingPerSymbol,
    TooManyPendingGlobal,
    EngineShutdown,
    UnknownReject,
}

/// Map a close-maker terminal event to its audit/fallback decision.
/// 將 close-maker terminal event 映射成 audit/fallback 決策。
pub fn close_maker_fallback_decision(event: CloseMakerFallbackEvent) -> CloseMakerFallbackDecision {
    match event {
        CloseMakerFallbackEvent::FastEscalateSafetyUpgrade => CloseMakerFallbackDecision::new(
            CloseMakerFallbackReason::FastEscalateSafetyUpgrade,
            false,
            None,
        ),
        CloseMakerFallbackEvent::Timeout => {
            CloseMakerFallbackDecision::new(CloseMakerFallbackReason::TimeoutTaker, false, None)
        }
        CloseMakerFallbackEvent::CancelGraceExpired => CloseMakerFallbackDecision::new(
            CloseMakerFallbackReason::CancelGraceExpired,
            false,
            None,
        ),
        CloseMakerFallbackEvent::PostOnlyReject => {
            CloseMakerFallbackDecision::new(CloseMakerFallbackReason::PostOnlyReject, false, None)
        }
        CloseMakerFallbackEvent::TooManyPendingPerSymbol => CloseMakerFallbackDecision::new(
            CloseMakerFallbackReason::RateLimitBackoffPerSymbol,
            true,
            Some(CloseMakerRateLimitScope::PerSymbol),
        ),
        CloseMakerFallbackEvent::TooManyPendingGlobal => CloseMakerFallbackDecision::new(
            CloseMakerFallbackReason::RateLimitPauseGlobal,
            true,
            Some(CloseMakerRateLimitScope::Global),
        ),
        CloseMakerFallbackEvent::EngineShutdown => CloseMakerFallbackDecision::new(
            CloseMakerFallbackReason::EngineShutdownSafety,
            false,
            None,
        ),
        CloseMakerFallbackEvent::UnknownReject => {
            CloseMakerFallbackDecision::new(CloseMakerFallbackReason::AckLost, true, None)
        }
    }
}

/// Classify a close-side maker rejection into fallback behavior.
///
/// Entry callbacks should keep using the existing entry cooldown path. Close
/// callbacks use this side-aware helper so `PostOnlyCross` immediately falls
/// back to market, `TooManyPending` enters dynamic backoff, and unknown reject
/// strings fail closed to market instead of abandoning the close.
///
/// 將 close-side maker reject 分類成 fallback 行為。entry callback 繼續使用既有
/// entry cooldown；close callback 走此 side-aware helper：PostOnlyCross 立即
/// market fallback，TooManyPending 進動態退避，未知 reject fail-closed 走 market。
pub fn close_rejection_fallback_decision(
    category: &MakerRejectionCategory,
) -> CloseMakerFallbackDecision {
    match category {
        MakerRejectionCategory::PostOnlyCross => {
            close_maker_fallback_decision(CloseMakerFallbackEvent::PostOnlyReject)
        }
        MakerRejectionCategory::TooManyPending => {
            close_maker_fallback_decision(CloseMakerFallbackEvent::TooManyPendingPerSymbol)
        }
        MakerRejectionCategory::SelfCancel
        | MakerRejectionCategory::FokCancel
        | MakerRejectionCategory::Other(_) => {
            close_maker_fallback_decision(CloseMakerFallbackEvent::UnknownReject)
        }
    }
}

/// Per-symbol close-maker rate-limit state.
/// 單一 symbol 的 close-maker 限流狀態。
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CloseMakerSymbolBackoff {
    pub current_backoff_ms: u64,
    pub next_eligible_ms: u64,
    pub consecutive_count: u32,
    pub last_trigger_ms: u64,
}

/// Result returned after recording `EC_ReachMaxPendingOrders`.
/// 記錄 `EC_ReachMaxPendingOrders` 後回傳的決策。
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CloseMakerBackoffDecision {
    pub symbol: String,
    pub fallback_reason: CloseMakerFallbackReason,
    pub rate_limit_scope: CloseMakerRateLimitScope,
    pub backoff_ms: u64,
    pub next_eligible_ms: u64,
    pub global_pause_until_ms: Option<u64>,
}

/// In-memory dynamic backoff for close-maker `TooManyPending`.
///
/// State is deliberately process-local: exchange backpressure is short lived,
/// and persisting it would make engine restart more conservative than the
/// accepted Phase 1b trade-off. Global pause expiry lazily clears all symbol
/// state, matching the spec's "global pause ends -> reset to 1s" rule.
///
/// close-maker `TooManyPending` 的記憶體內動態退避。狀態刻意不跨 process
/// 持久化：交易所背壓很短，重啟後重置是 Phase 1b 接受的 trade-off。全域暫停
/// 到期時 lazy 清空 symbol state，對齊 spec「global pause 結束後全部重置 1s」。
#[derive(Debug, Clone, Default)]
pub struct CloseMakerBackoffState {
    per_symbol: HashMap<String, CloseMakerSymbolBackoff>,
    recent_symbol_triggers: HashMap<String, u64>,
    global_pause_until_ms: Option<u64>,
}

impl CloseMakerBackoffState {
    /// Create an empty process-local backoff state. / 建立空的本 process 退避狀態。
    pub fn new() -> Self {
        Self::default()
    }

    fn clear_expired_global_pause(&mut self, now_ms: u64) {
        if self
            .global_pause_until_ms
            .is_some_and(|until| now_ms >= until)
        {
            self.global_pause_until_ms = None;
            self.per_symbol.clear();
            self.recent_symbol_triggers.clear();
        }
    }

    fn prune_recent_triggers(&mut self, now_ms: u64) {
        let cutoff = now_ms.saturating_sub(CLOSE_MAKER_GLOBAL_CASCADE_WINDOW_MS);
        self.recent_symbol_triggers
            .retain(|_, last_ts| *last_ts >= cutoff);
    }

    /// Return the current active pause scope for a symbol.
    /// 回傳 symbol 目前生效的暫停範圍。
    pub fn pause_scope(&mut self, symbol: &str, now_ms: u64) -> Option<CloseMakerRateLimitScope> {
        self.clear_expired_global_pause(now_ms);
        if self
            .global_pause_until_ms
            .is_some_and(|until| now_ms < until)
        {
            return Some(CloseMakerRateLimitScope::Global);
        }
        self.per_symbol.get(symbol).and_then(|state| {
            (now_ms < state.next_eligible_ms).then_some(CloseMakerRateLimitScope::PerSymbol)
        })
    }

    /// Current global pause deadline, if active. / 目前全域暫停截止時間。
    pub fn global_pause_until_ms(&mut self, now_ms: u64) -> Option<u64> {
        self.clear_expired_global_pause(now_ms);
        self.global_pause_until_ms
    }

    /// Return a symbol's current backoff state for tests/diagnostics.
    /// 回傳單一 symbol 退避狀態，供測試 / 診斷使用。
    pub fn symbol_state(&self, symbol: &str) -> Option<&CloseMakerSymbolBackoff> {
        self.per_symbol.get(symbol)
    }

    /// Record a close-maker TooManyPending reject and compute the next pause.
    ///
    /// Same-symbol triggers double from 1s to 60s while they remain inside the
    /// 5 minute reset window. Ten distinct symbols in one minute upgrades to
    /// a 5 minute global pause and clears per-symbol state so expiry resets
    /// every symbol back to 1s.
    ///
    /// 記錄 close-maker TooManyPending reject 並計算下一個暫停。單一 symbol 在
    /// 5 分鐘 reset window 內連續觸發時由 1s 倍增至 60s；1 分鐘內 10 個 distinct
    /// symbol 觸發則升級為 5 分鐘全域暫停，並清空 per-symbol state，讓到期後
    /// 全部重置為 1s。
    pub fn record_too_many_pending(
        &mut self,
        symbol: impl Into<String>,
        now_ms: u64,
    ) -> CloseMakerBackoffDecision {
        let symbol = symbol.into();
        self.clear_expired_global_pause(now_ms);

        if let Some(until) = self.global_pause_until_ms {
            if now_ms < until {
                return CloseMakerBackoffDecision {
                    symbol,
                    fallback_reason: CloseMakerFallbackReason::RateLimitPauseGlobal,
                    rate_limit_scope: CloseMakerRateLimitScope::Global,
                    backoff_ms: until.saturating_sub(now_ms),
                    next_eligible_ms: until,
                    global_pause_until_ms: Some(until),
                };
            }
        }

        let previous = self.per_symbol.get(&symbol).cloned();
        let (current_backoff_ms, consecutive_count) = match previous {
            Some(prev)
                if now_ms.saturating_sub(prev.last_trigger_ms)
                    <= CLOSE_MAKER_BACKOFF_RESET_AFTER_MS =>
            {
                (
                    prev.current_backoff_ms
                        .saturating_mul(2)
                        .clamp(CLOSE_MAKER_BACKOFF_INITIAL_MS, CLOSE_MAKER_BACKOFF_MAX_MS),
                    prev.consecutive_count.saturating_add(1),
                )
            }
            _ => (CLOSE_MAKER_BACKOFF_INITIAL_MS, 1),
        };
        let next_eligible_ms = now_ms.saturating_add(current_backoff_ms);
        self.per_symbol.insert(
            symbol.clone(),
            CloseMakerSymbolBackoff {
                current_backoff_ms,
                next_eligible_ms,
                consecutive_count,
                last_trigger_ms: now_ms,
            },
        );

        self.prune_recent_triggers(now_ms);
        self.recent_symbol_triggers.insert(symbol.clone(), now_ms);

        if self.recent_symbol_triggers.len() >= CLOSE_MAKER_GLOBAL_CASCADE_SYMBOLS {
            let until = now_ms.saturating_add(CLOSE_MAKER_GLOBAL_PAUSE_MS);
            self.global_pause_until_ms = Some(until);
            self.per_symbol.clear();
            self.recent_symbol_triggers.clear();
            return CloseMakerBackoffDecision {
                symbol,
                fallback_reason: CloseMakerFallbackReason::RateLimitPauseGlobal,
                rate_limit_scope: CloseMakerRateLimitScope::Global,
                backoff_ms: CLOSE_MAKER_GLOBAL_PAUSE_MS,
                next_eligible_ms: until,
                global_pause_until_ms: Some(until),
            };
        }

        CloseMakerBackoffDecision {
            symbol,
            fallback_reason: CloseMakerFallbackReason::RateLimitBackoffPerSymbol,
            rate_limit_scope: CloseMakerRateLimitScope::PerSymbol,
            backoff_ms: current_backoff_ms,
            next_eligible_ms,
            global_pause_until_ms: None,
        }
    }
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

    #[test]
    fn test_close_fallback_decisions_require_market() {
        let cases = [
            (
                CloseMakerFallbackEvent::FastEscalateSafetyUpgrade,
                CloseMakerFallbackReason::FastEscalateSafetyUpgrade,
                None,
            ),
            (
                CloseMakerFallbackEvent::Timeout,
                CloseMakerFallbackReason::TimeoutTaker,
                None,
            ),
            (
                CloseMakerFallbackEvent::CancelGraceExpired,
                CloseMakerFallbackReason::CancelGraceExpired,
                None,
            ),
            (
                CloseMakerFallbackEvent::PostOnlyReject,
                CloseMakerFallbackReason::PostOnlyReject,
                None,
            ),
            (
                CloseMakerFallbackEvent::TooManyPendingPerSymbol,
                CloseMakerFallbackReason::RateLimitBackoffPerSymbol,
                Some(CloseMakerRateLimitScope::PerSymbol),
            ),
            (
                CloseMakerFallbackEvent::TooManyPendingGlobal,
                CloseMakerFallbackReason::RateLimitPauseGlobal,
                Some(CloseMakerRateLimitScope::Global),
            ),
            (
                CloseMakerFallbackEvent::EngineShutdown,
                CloseMakerFallbackReason::EngineShutdownSafety,
                None,
            ),
        ];

        for (event, reason, scope) in cases {
            let decision = close_maker_fallback_decision(event);
            assert_eq!(decision.side, MakerOrderSide::Close);
            assert_eq!(decision.reason, reason);
            assert_eq!(decision.rate_limit_scope, scope);
            assert!(
                decision.market_fallback_required,
                "close-maker event {:?} must not abandon close execution",
                event
            );
        }
    }

    #[test]
    fn test_close_rejection_dispatch_uses_existing_classifier_categories() {
        let postonly = close_rejection_fallback_decision(&classify("EC_PostOnlyWillTakeLiquidity"));
        assert_eq!(postonly.reason, CloseMakerFallbackReason::PostOnlyReject);
        assert!(!postonly.arm_cooldown);

        let too_many = close_rejection_fallback_decision(&classify("EC_ReachMaxPendingOrders"));
        assert_eq!(
            too_many.reason,
            CloseMakerFallbackReason::RateLimitBackoffPerSymbol
        );
        assert_eq!(
            too_many.rate_limit_scope,
            Some(CloseMakerRateLimitScope::PerSymbol)
        );
        assert!(too_many.arm_cooldown);

        let unknown = close_rejection_fallback_decision(&classify("EC_FutureUnknown"));
        assert_eq!(unknown.reason, CloseMakerFallbackReason::AckLost);
        assert!(unknown.market_fallback_required);
    }

    #[test]
    fn test_close_backoff_is_per_symbol_exponential_and_capped() {
        let mut state = CloseMakerBackoffState::new();

        let d1 = state.record_too_many_pending("BTCUSDT", 1_000);
        assert_eq!(d1.backoff_ms, CLOSE_MAKER_BACKOFF_INITIAL_MS);
        assert_eq!(d1.next_eligible_ms, 2_000);
        assert_eq!(d1.rate_limit_scope, CloseMakerRateLimitScope::PerSymbol);
        assert_eq!(
            state.pause_scope("BTCUSDT", 1_500),
            Some(CloseMakerRateLimitScope::PerSymbol)
        );
        assert_eq!(state.pause_scope("ETHUSDT", 1_500), None);

        let d2 = state.record_too_many_pending("BTCUSDT", 2_000);
        assert_eq!(d2.backoff_ms, 2_000);
        assert_eq!(d2.next_eligible_ms, 4_000);

        let mut last = d2;
        for i in 0..10 {
            last = state.record_too_many_pending("BTCUSDT", 3_000 + i);
        }
        assert_eq!(last.backoff_ms, CLOSE_MAKER_BACKOFF_MAX_MS);
        assert_eq!(
            state
                .symbol_state("BTCUSDT")
                .expect("BTC state")
                .current_backoff_ms,
            CLOSE_MAKER_BACKOFF_MAX_MS
        );
    }

    #[test]
    fn test_close_backoff_resets_after_five_quiet_minutes() {
        let mut state = CloseMakerBackoffState::new();

        assert_eq!(
            state.record_too_many_pending("BTCUSDT", 10_000).backoff_ms,
            1_000
        );
        assert_eq!(
            state.record_too_many_pending("BTCUSDT", 20_000).backoff_ms,
            2_000
        );

        let reset_ts = 20_000 + CLOSE_MAKER_BACKOFF_RESET_AFTER_MS + 1;
        let reset = state.record_too_many_pending("BTCUSDT", reset_ts);
        assert_eq!(reset.backoff_ms, CLOSE_MAKER_BACKOFF_INITIAL_MS);
        assert_eq!(
            state
                .symbol_state("BTCUSDT")
                .expect("BTC state")
                .consecutive_count,
            1
        );
    }

    #[test]
    fn test_close_backoff_global_pause_cascade_and_reset() {
        let mut state = CloseMakerBackoffState::new();
        let now = 100_000;
        let mut last = None;
        for i in 0..CLOSE_MAKER_GLOBAL_CASCADE_SYMBOLS {
            last = Some(state.record_too_many_pending(format!("SYM{i}USDT"), now + i as u64));
        }
        let cascade = last.expect("cascade decision");
        assert_eq!(cascade.rate_limit_scope, CloseMakerRateLimitScope::Global);
        assert_eq!(
            cascade.fallback_reason,
            CloseMakerFallbackReason::RateLimitPauseGlobal
        );
        assert_eq!(
            cascade.global_pause_until_ms,
            Some(
                now + (CLOSE_MAKER_GLOBAL_CASCADE_SYMBOLS as u64 - 1) + CLOSE_MAKER_GLOBAL_PAUSE_MS
            )
        );
        assert_eq!(
            state.pause_scope("UNSEENUSDT", now + 10),
            Some(CloseMakerRateLimitScope::Global)
        );

        let after_pause =
            now + (CLOSE_MAKER_GLOBAL_CASCADE_SYMBOLS as u64 - 1) + CLOSE_MAKER_GLOBAL_PAUSE_MS;
        assert_eq!(state.pause_scope("UNSEENUSDT", after_pause), None);
        let fresh = state.record_too_many_pending("SYM0USDT", after_pause);
        assert_eq!(fresh.backoff_ms, CLOSE_MAKER_BACKOFF_INITIAL_MS);
        assert_eq!(fresh.rate_limit_scope, CloseMakerRateLimitScope::PerSymbol);
    }
}
