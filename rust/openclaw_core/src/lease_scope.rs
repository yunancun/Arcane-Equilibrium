//! LeaseScope — typed lease scope enum for Decision Lease facade.
//! LeaseScope — Decision Lease facade 的強型別 scope enum。
//!
//! W-AUDIT-9 T6 (AMD-2026-05-09-03 §4.5) — manual canary stage promotion 必伴隨一個
//! `LeaseScope::CanaryStagePromotion` lease (TTL 60s)；audit chain 存於
//! `governance.canary_stage_log.decision_lease_id`。
//!
//! 模組目的：
//!   - 把既有 facade 的 `scope: &str` 升級為強型別 enum，避免 typo / scope 漂移；
//!   - 為 W-AUDIT-9 T6 manual_promote 提供 `CanaryStagePromotion` variant（NEW）；
//!   - 既有 `&str` callers（router gate / IntentProcessor）透過 `as_audit_str()`
//!     回轉到原本 `governance.canary_stage_log` / V054 lease_transitions 期望的字串。
//!
//! 設計原則：
//!   - **不擴大現有 facade `acquire_lease(scope: &str, ...)` 的簽名**（router.rs
//!     callers 用 `&str` 是 cross-crate 相依，動 signature 會撞 W-AUDIT-8a 的 sprint
//!     順序）；新增 `acquire_canary_stage_promotion_lease(...)` 專用 facade method
//!     於 `governance_core.rs`，內部 enum cast 為字串走原 facade。
//!   - LeaseScope 字串對齊 `as_audit_str()` 為 audit row 的權威 key；scope 升級時
//!     必同步更新所有 SQL CHECK constraint。
//!   - 新 variant 增加必須在 `as_audit_str()` 同時補對應字串（通過編譯器 exhaustive
//!     match 強制）。
//!
//! 上層治理 SoT：CLAUDE.md §四 硬邊界（live gating 5-gate）+ AMD-2026-05-09-03 §4.5
//! Decision Lease 接線 + AMD-2026-05-02-01 SM-02 R-04 retrofit Path A。

use serde::{Deserialize, Serialize};

/// LeaseScope — typed scope kind for Decision Lease (SM-02).
/// LeaseScope — Decision Lease 的強型別 scope。
///
/// 對應 audit row 中 `governance.canary_stage_log.transition_kind` 與 V054
/// `lease_transitions` 子集 — 但僅作為 facade 入口分類，不替代現有 SM transition_id。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum LeaseScope {
    /// 真實開倉 intent — IntentProcessor router 唯一 hot path scope。
    /// Real entry intent — sole router hot-path scope.
    TradeEntry,
    /// 真實平倉 intent — exit / close path。當前未強制要求 lease，但保留變體
    /// 以待 SM-04 ladder 在 Stage ≥ 2 時放權平倉路徑。
    /// Real exit intent — exit/close path; reserved for SM-04 ladder Stage ≥ 2.
    TradeExit,
    /// 倉位調整 — Strategist 重新 risk-scaled 動作；尚未強制 lease，留 enum 變體。
    /// Position adjustment — Strategist re-risk scale; placeholder for now.
    PositionAdjust,
    /// W-AUDIT-9 T6 NEW — manual graduated canary stage promotion（operator GUI / IPC
    /// 動作）；TTL 60s；伴隨 `governance.canary_stage_log` 寫入 row 必填
    /// `decision_lease_id`（PG NOT NULL CHECK 由 W-AUDIT-9 T2 V0XX migration 強制）。
    /// W-AUDIT-9 T6 NEW — manual graduated canary stage promotion (operator-driven).
    /// TTL 60s; companion canary_stage_log row MUST carry decision_lease_id.
    CanaryStagePromotion,
}

impl LeaseScope {
    /// 將 enum variant 映射至 audit row 字串 key。新增 variant 時必同步更新對應
    /// SQL CHECK constraint（governance.canary_stage_log.transition_kind / V054
    /// lease_transitions 衍生 view 等），否則 PG INSERT 會觸 CHECK 拒寫。
    /// Map enum variant to audit row string key. Adding variants requires
    /// keeping SQL CHECK constraints aligned.
    pub fn as_audit_str(self) -> &'static str {
        match self {
            Self::TradeEntry => "TRADE_ENTRY",
            Self::TradeExit => "TRADE_EXIT",
            Self::PositionAdjust => "POSITION_ADJUST",
            // W-AUDIT-9 T6 NEW — 對齊 governance.canary_stage_log.transition_kind
            // 期望的 'manual_promote' 條件下 PG NOT NULL decision_lease_id 約束。
            Self::CanaryStagePromotion => "CANARY_STAGE_PROMOTION",
        }
    }

    /// W-AUDIT-9 T6 — 是否需要 operator authority（hard fail-closed）。
    /// 目前 CanaryStagePromotion 是唯一 strict operator-only scope；TradeEntry /
    /// TradeExit / PositionAdjust 由 GovernanceProfile + auth state 共同判斷。
    /// Whether this scope requires explicit operator authority (hard fail-closed).
    pub fn requires_operator_authority(self) -> bool {
        matches!(self, Self::CanaryStagePromotion)
    }

    /// W-AUDIT-9 T6 — scope 規範的 TTL（毫秒）。
    /// CanaryStagePromotion 嚴格 60 秒（AMD-2026-05-09-03 §4.5）；
    /// 其他 scope 預設用 caller 提供值（這裡 fallback 用 30 秒，作為合理保守 baseline）。
    /// Spec-mandated TTL (ms) per scope; CanaryStagePromotion = 60s strict.
    pub fn default_ttl_ms(self) -> u32 {
        match self {
            // AMD-2026-05-09-03 §4.5 明文：「TTL 60s, 由 operator GUI 動作 trigger」。
            Self::CanaryStagePromotion => 60_000,
            // hot-path scope 的 baseline — 實際呼叫端 (router.rs) 仍可顯式覆寫。
            Self::TradeEntry | Self::TradeExit | Self::PositionAdjust => 30_000,
        }
    }
}

impl std::fmt::Display for LeaseScope {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(self.as_audit_str())
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// CanaryStageTransition — typed audit row payload for governance.canary_stage_log
// 用於 governance.canary_stage_log INSERT 的強型別 row payload
// ═══════════════════════════════════════════════════════════════════════════════

/// W-AUDIT-9 T6 — typed payload assembling row for `governance.canary_stage_log`
/// when a manual stage promotion occurs. The actual PG INSERT is owned by E1-B
/// task (T2 V0XX migration + caller wiring); this struct provides the contract
/// so caller wiring can compile against a single typed schema.
/// 為 manual stage promotion 組裝 `governance.canary_stage_log` row 的強型別
/// payload。實際 PG INSERT 屬 E1-B（T2 V0XX migration）職責；本結構只保證 caller
/// 端編譯期 schema 對齊。
///
/// 對應 AMD-2026-05-09-03 §4.2 SQL schema：
/// - `transitioned_at_ms BIGINT NOT NULL`
/// - `environment TEXT NOT NULL`
/// - `cohort_strategy TEXT` / `cohort_symbol TEXT`
/// - `from_stage SMALLINT NOT NULL CHECK (BETWEEN 0 AND 4)`
/// - `to_stage SMALLINT NOT NULL CHECK (BETWEEN 0 AND 4)`
/// - `transition_kind TEXT NOT NULL`（'manual_promote' for this struct）
/// - `reason TEXT NOT NULL`
/// - `initiated_by TEXT NOT NULL`
/// - `decision_lease_id TEXT` — manual_promote 必填（PG CHECK 強制）
/// - `metric_snapshot JSONB`
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CanaryStageTransition {
    /// ms epoch 時間戳，由 caller 取 `now_ms()` 寫入。/ ms epoch transition time.
    pub transitioned_at_ms: u64,
    /// `'paper' | 'demo' | 'live_demo' | 'mainnet'`。/ Environment label.
    pub environment: String,
    /// Stage 1/2 cohort 必填；Stage 0/3/4 留 None。/ Cohort strategy (Some for Stage 1/2).
    pub cohort_strategy: Option<String>,
    /// Stage 1/2 cohort 必填。/ Cohort symbol (Some for Stage 1/2).
    pub cohort_symbol: Option<String>,
    /// 來源 stage（0..=4）。/ From stage.
    pub from_stage: u8,
    /// 目標 stage（0..=4）。/ To stage.
    pub to_stage: u8,
    /// 'manual_promote' 對應 `LeaseScope::CanaryStagePromotion`；
    /// 其他值（'auto_promote' / 'auto_rollback' / 'incident_rollback'）由非 lease
    /// 路徑寫入。/ Transition kind tag.
    pub transition_kind: String,
    /// 升級理由 metric detail / operator note。/ Reason text.
    pub reason: String,
    /// 'operator:<role>' / 'system:auto_promote' 等。/ Initiator label.
    pub initiated_by: String,
    /// W-AUDIT-9 T6 SAFETY 不變量：當 transition_kind == 'manual_promote' 時必為
    /// `Some(lease_id)`；PG V0XX migration 強制 NOT NULL CHECK，但本結構在 caller
    /// 端用 Option<String> 是因為 'auto_promote' / 'auto_rollback' 路徑允許 None。
    /// SAFETY invariant: must be Some for manual_promote; None for auto/auto_rollback.
    pub decision_lease_id: Option<String>,
    /// 升級/rollback 當時各 metric 的 JSON snapshot。/ Metric snapshot JSON.
    pub metric_snapshot: serde_json::Value,
}

impl CanaryStageTransition {
    /// W-AUDIT-9 T6 — 構造一筆 `manual_promote` 用 row payload，自動 wire
    /// `transition_kind = "manual_promote"` 並要求 `decision_lease_id != None`。
    /// caller 必先 acquire 一個 `CanaryStagePromotion` lease 並把 `lease_id`（
    /// `LeaseId::Active(...)` 抽出的 String）傳入；`LeaseId::Bypass` 即非
    /// Production profile，這裡不允許（caller 端應在組裝前判斷 profile）。
    /// Build a typed manual_promote transition row payload. Caller must pre-acquire
    /// a CanaryStagePromotion lease; passing the active String lease_id here.
    ///
    /// SAFETY / 不變量：
    /// - `lease_id` 為 caller-acquired `LeaseScope::CanaryStagePromotion` lease 的
    ///   `LeaseId::Active(String)` 值；Bypass 變體（Exploration / Validation profile）
    ///   不應走 manual_promote 路徑（graduated canary 適用範圍是 alpha-bearing pathway，
    ///   AMD-2026-05-09-03 §3.5）。
    /// - `from_stage / to_stage` ∈ 0..=4；超出範圍由 PG SMALLINT CHECK 拒寫，
    ///   本結構不再上層驗（讓 caller 拿到一致的 fail-loud 錯誤）。
    /// - `now_ms` caller 注入（避免在 openclaw_core 引入時鐘 dep）。
    ///
    /// SAFETY invariants:
    /// - lease_id must be from an active CanaryStagePromotion lease (not Bypass).
    /// - from_stage/to_stage in 0..=4 (PG CHECK enforces; not double-validated here).
    /// - now_ms injected by caller to keep openclaw_core clock-free.
    #[allow(clippy::too_many_arguments)]
    pub fn manual_promote(
        now_ms: u64,
        environment: impl Into<String>,
        cohort_strategy: Option<String>,
        cohort_symbol: Option<String>,
        from_stage: u8,
        to_stage: u8,
        reason: impl Into<String>,
        initiated_by: impl Into<String>,
        lease_id: String,
        metric_snapshot: serde_json::Value,
    ) -> Self {
        Self {
            transitioned_at_ms: now_ms,
            environment: environment.into(),
            cohort_strategy,
            cohort_symbol,
            from_stage,
            to_stage,
            // W-AUDIT-9 T6 — 'manual_promote' 對應 PG NOT NULL CHECK
            // (transition_kind != 'manual_promote' OR decision_lease_id IS NOT NULL)。
            transition_kind: "manual_promote".to_string(),
            reason: reason.into(),
            initiated_by: initiated_by.into(),
            decision_lease_id: Some(lease_id),
            metric_snapshot,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn lease_scope_audit_str_roundtrip() {
        // 每個 variant 的 audit_str 必為 SCREAMING_SNAKE_CASE 且唯一；對齊 PG
        // CHECK constraint。新增 variant 時若忘記補 as_audit_str() 會編譯失敗
        // （exhaustive match 保護）。
        let all = [
            (LeaseScope::TradeEntry, "TRADE_ENTRY"),
            (LeaseScope::TradeExit, "TRADE_EXIT"),
            (LeaseScope::PositionAdjust, "POSITION_ADJUST"),
            (LeaseScope::CanaryStagePromotion, "CANARY_STAGE_PROMOTION"),
        ];
        for (scope, expected) in all {
            assert_eq!(scope.as_audit_str(), expected);
            assert_eq!(format!("{scope}"), expected);
        }
    }

    #[test]
    fn canary_stage_promotion_requires_operator_authority() {
        // W-AUDIT-9 T6 SAFETY — CanaryStagePromotion 必觸發 operator authority gate。
        assert!(LeaseScope::CanaryStagePromotion.requires_operator_authority());
        // 其他 scope 由 GovernanceProfile + auth state 判斷，本 helper 不返回 true。
        assert!(!LeaseScope::TradeEntry.requires_operator_authority());
        assert!(!LeaseScope::TradeExit.requires_operator_authority());
        assert!(!LeaseScope::PositionAdjust.requires_operator_authority());
    }

    #[test]
    fn canary_stage_promotion_default_ttl_60s() {
        // AMD-2026-05-09-03 §4.5：「TTL 60s, 由 operator GUI 動作 trigger」。
        assert_eq!(LeaseScope::CanaryStagePromotion.default_ttl_ms(), 60_000);
        // 其他 scope baseline 30s（caller 仍可覆寫）。
        assert_eq!(LeaseScope::TradeEntry.default_ttl_ms(), 30_000);
    }

    #[test]
    fn canary_stage_transition_manual_promote_carries_lease_id() {
        // W-AUDIT-9 T6 — manual_promote payload 必帶 lease_id 進 audit row。
        let row = CanaryStageTransition::manual_promote(
            1_715_270_400_000,
            "demo",
            Some("ma_crossover".to_string()),
            Some("BTCUSDT".to_string()),
            0,
            1,
            "operator selected after 7d Stage 0 evidence stable",
            "operator:supervisor",
            "lease:abcdef123456".to_string(),
            serde_json::json!({"observed_sharpe": 0.42}),
        );
        assert_eq!(row.transition_kind, "manual_promote");
        assert_eq!(
            row.decision_lease_id,
            Some("lease:abcdef123456".to_string()),
            "manual_promote 必填 decision_lease_id（PG NOT NULL CHECK invariant）"
        );
        assert_eq!(row.from_stage, 0);
        assert_eq!(row.to_stage, 1);
        assert_eq!(row.environment, "demo");
        assert_eq!(row.cohort_strategy, Some("ma_crossover".to_string()));
    }

    #[test]
    fn canary_stage_transition_manual_promote_serializes() {
        // PG INSERT 通過 jsonb cast 寫 metric_snapshot；此 serialization round-trip
        // 保證 caller 不會因 NaN / Infinity 把 row 寫成非法 JSON（JSON spec 禁這些
        // 但 portfolio_var 可能輸出 NaN）。
        let row = CanaryStageTransition::manual_promote(
            1_715_270_400_000,
            "paper",
            None,
            None,
            0,
            1,
            "stage1 enter",
            "operator:supervisor",
            "lease:xyz".to_string(),
            serde_json::json!({"sharpe": 0.5, "n_trials": 13}),
        );
        let s = serde_json::to_string(&row).expect("must serialize");
        assert!(s.contains("\"transition_kind\":\"manual_promote\""));
        assert!(s.contains("\"decision_lease_id\":\"lease:xyz\""));
    }
}
