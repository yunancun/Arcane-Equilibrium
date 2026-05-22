//! M1 LAL — Layered Approval Lease state machine（Sprint 1A-ζ Phase 2 Track A skeleton）。
//!
//! MODULE_NOTE
//! 模塊用途：
//!   實作 M1 Decision Lease LAL Tier 0/1 state machine 骨架：
//!   - `LalTier` enum（5 變體；對齊 V112 governance.lease_lal_tiers 5 row seed +
//!     ADR-0034 對齊矩陣「數字越大越嚴」）
//!   - `LalTier::from_i32(i32) -> Result<LalTier, LalTierError>` 對齊 PG CHECK
//!     `tier_level BETWEEN 0 AND 4`；越界 RAISE 對應 Rust Err。
//!   - `LalTier::numeric_value() -> i32` 嚴格遞增；assert 0 < 1 < 2 < 3 < 4。
//!   - `LalTransition::evaluate_tier_0_to_1()` Tier 0 → Tier 1 升階邏輯 stub
//!     （per M1 design spec §3.4 全 6 條 hard gate；本 spike 只 wire 結構，不真實
//!     query hard gate；hard gate IMPL 留 Sprint 4 LAL 1 IMPL）。
//!   - `Tier0FillBlocker::check_retired()` 接 ADR-0034 Decision 6 — query
//!     `learning.decay_signals.lifecycle_state` → IF 'RETIRED' → fail-closed reject。
//!     本 spike stub 在無 DB pool 時走 Err()，full IMPL Sprint 4 接 sqlx pool。
//!
//! 主要類型 / 函數：
//!   - `LalTier` enum（Lal0Auto / Lal1LightReview / Lal2FullReview /
//!     Lal3OperatorApproval / Lal4OperatorAttestation）
//!   - `LalTierError` thiserror enum（OutOfRange / DecayQueryFailed / RetiredBlocked）
//!   - `Tier0FillBlocker::check_retired(strategy_id)` —— RETIRED blocker query stub
//!   - `LalTransition::evaluate_tier_0_to_1(state)` —— Tier 0/1 升階評估 stub
//!
//! 依賴：
//!   - `thiserror`（workspace dep）
//!   - V112 governance.lease_lal_tiers / lease_lal_assignments（sandbox apply done）
//!   - V113 learning.decay_signals（placeholder；本 spike 不接真實 query）
//!
//! 硬邊界：
//!   - 數字越大越嚴（per ADR-0034 line 41）：numeric_value() 對應 0/1/2/3/4 序。
//!   - Tier 0 fill query 必過 RETIRED blocker；不可繞（per ADR-0034 Decision 6）；
//!     LAL 4 manual override 對 RETIRED 也禁用（per AMD-2026-05-21-01 protected scope）。
//!   - Tier 2/3/4 transition 邏輯本 spike 不寫；未來呼叫 unimplemented!() 立即 panic
//!     防誤啟。
//!   - 任何 from_i32 越界輸入 → Err，不 panic（從 PG row 反序列化路徑必 fail-safe）。
//!
//! 參考：
//!   - ADR-0034 §Decision 1-6（Decision 6 RETIRED blocker 為本 module 硬邊界）
//!   - M1 design spec §3.2 state machine ASCII 圖
//!   - V112 spec §2.1 lease_lal_tiers + §2.2 lease_lal_assignments
//!   - Sprint 1A-ζ spike spec §2.1 Track A + §AC-1.1 反向 assert 矩陣

use thiserror::Error;

// ---------------------------------------------------------------------------
// LalTier enum + numeric_value + from_i32
// ---------------------------------------------------------------------------

/// M1 Decision Lease Layered Approval Level（per ADR-0034 對齊矩陣）。
///
/// 為什麼 enum：
///   - 5 LAL 值的數字方向「越大越嚴」是治理硬邊界；用 enum 防止 `i32::MIN..-1`
///     或 `5..i32::MAX` 越界輸入污染 state machine。
///   - 對 V112 `governance.lease_lal_tiers.tier_level` `INT PRIMARY KEY CHECK
///     (tier_level BETWEEN 0 AND 4)` 嚴格對齊。
///
/// 序：Lal0Auto(0) < Lal1LightReview(1) < Lal2FullReview(2) < Lal3OperatorApproval(3)
///   < Lal4OperatorAttestation(4)
///
/// 數字越大 = approval depth 越嚴：
///   - 0 = per-fill autonomous（Guardian fast path）
///   - 1 = intra-strategy reparam（Stage 4 + 30d stable + 6 hard gate）
///   - 2 = cross-strategy reweight（Y2 gate + Console opt-in）
///   - 3 = new strategy promotion（永遠 operator approve）
///   - 4 = capital structure / venue change（永遠 operator attestation + 2FA + 0 clawback）
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum LalTier {
    /// LAL 0 — per-fill autonomous（既有 Guardian auto；always on）。
    Lal0Auto,
    /// LAL 1 — intra-strategy reparam（Stage 4 + 30d stable + 6 hard gate auto-approve）。
    Lal1LightReview,
    /// LAL 2 — cross-strategy reweight（Y2 gate + Console opt-in；Y1 仍 manual）。
    Lal2FullReview,
    /// LAL 3 — new strategy promotion（永遠 operator approve；never auto）。
    Lal3OperatorApproval,
    /// LAL 4 — capital structure / venue change（永遠 operator attest + 2FA + 0 clawback）。
    Lal4OperatorAttestation,
}

impl LalTier {
    /// LAL tier 對應的 `tier_level` 整數（與 V112 `lease_lal_tiers.tier_level` 對齊）。
    ///
    /// 為什麼：persistence 寫入 PG 必走 i32；MV / FK / CHECK 都以 integer 為 key。
    /// 不變量：返回值嚴格在 \[0,4\]；assert 0/1/2/3/4 嚴格遞增（per ADR-0034 line 41）。
    pub fn numeric_value(&self) -> i32 {
        match self {
            LalTier::Lal0Auto => 0,
            LalTier::Lal1LightReview => 1,
            LalTier::Lal2FullReview => 2,
            LalTier::Lal3OperatorApproval => 3,
            LalTier::Lal4OperatorAttestation => 4,
        }
    }

    /// 從 PG `tier_level` 整數反序列化 LalTier。
    ///
    /// 為什麼 Result：PG 端 CHECK constraint `BETWEEN 0 AND 4` 保證合法輸入；但 Rust
    /// 端讀任意 i32（程式錯 / sqlx mapping 漂移 / 跨環境 schema drift）必 fail-safe，
    /// 不 panic、不 fallback 到 default（fallback 會掩蓋治理問題）。
    /// 對齊 spike spec §AC-1.1 反向 assert：from_i32(-1) 必 Err、from_i32(5) 必 Err。
    pub fn from_i32(value: i32) -> Result<LalTier, LalTierError> {
        match value {
            0 => Ok(LalTier::Lal0Auto),
            1 => Ok(LalTier::Lal1LightReview),
            2 => Ok(LalTier::Lal2FullReview),
            3 => Ok(LalTier::Lal3OperatorApproval),
            4 => Ok(LalTier::Lal4OperatorAttestation),
            other => Err(LalTierError::OutOfRange { provided: other }),
        }
    }

    /// PG row 寫入時對應的 `tier_name` 字串（與 V112 CHECK constraint 5 值對齊）。
    pub fn tier_name(&self) -> &'static str {
        match self {
            LalTier::Lal0Auto => "LAL_0_AUTO",
            LalTier::Lal1LightReview => "LAL_1_LIGHT_REVIEW",
            LalTier::Lal2FullReview => "LAL_2_FULL_REVIEW",
            LalTier::Lal3OperatorApproval => "LAL_3_OPERATOR_APPROVAL",
            LalTier::Lal4OperatorAttestation => "LAL_4_OPERATOR_ATTESTATION",
        }
    }
}

// ---------------------------------------------------------------------------
// LalTierError
// ---------------------------------------------------------------------------

/// M1 LAL state machine 錯誤類型。
///
/// 為什麼集中 enum：governance / persistence / RETIRED blocker 三條路徑共用
/// 同一 error surface，sub-agent IMPL Sprint 4+ 可直接用。
#[derive(Debug, Error, PartialEq, Eq)]
pub enum LalTierError {
    /// 從 PG i32 → LalTier 越界（合法區間 0..=4）。
    #[error("LAL tier_level out of range: provided={provided}, expected 0..=4 per ADR-0034")]
    OutOfRange { provided: i32 },

    /// Tier 0 fill RETIRED blocker query 失敗（DB / IPC / pool exhausted）。
    /// fail-closed：query 失敗時必 reject fill（不 fallback「假定 not retired」）。
    #[error("Tier 0 RETIRED blocker query failed: {0}")]
    DecayQueryFailed(String),

    /// Tier 0 fill blocked — strategy_id 已進 RETIRED lifecycle（per ADR-0034 Decision 6）。
    #[error(
        "Tier 0 fill blocked: strategy '{strategy_id}' is RETIRED per M7 decay_signals; \
         only operator manual re-promotion through Stage 0R can lift this block."
    )]
    RetiredBlocked { strategy_id: String },

    /// Tier 2/3/4 升階 / 降階 / 任何 transition：本 spike 不 IMPL；後續呼叫直接 Err。
    #[error("LAL Tier {tier} transition not implemented in Sprint 1A-ζ spike; defer to Sprint 4+")]
    TransitionNotImplemented { tier: i32 },

    /// Tier 0 → Tier 1 升階所需的 6 條 hard gate 任一失敗。
    #[error("Tier 0→1 promotion gate failed: {reason}")]
    PromotionGateFailed { reason: String },
}

// ---------------------------------------------------------------------------
// Tier 0 fill RETIRED blocker（per ADR-0034 Decision 6）
// ---------------------------------------------------------------------------

/// ADR-0034 Decision 6：LAL Tier 0 fill query path 必 fail-closed on M7 RETIRED。
///
/// Spec：
///   - Query 目標：`SELECT lifecycle_state FROM learning.mv_latest_decay_state_per_strategy
///     WHERE strategy_id=$1`（per ADR-0034 Decision 6；V113 + materialized view land
///     後 stub 升級為實 query）。
///   - IF lifecycle_state = 'RETIRED' → reject fill + audit log + alert operator。
///   - 已開倉位走 SL/TP path（不強制 immediate close）。
///   - LAL 4 manual override 也禁用（per AMD-2026-05-21-01 protected scope）。
///   - 僅 operator manual Stage 0R 路徑可從 RETIRED 拉回 NORMAL_LIVE。
///
/// 本 Sprint 1A-ζ spike 範圍：
///   - stub 路徑：本 module 不接真實 sqlx pool；caller 端 IMPL Sprint 4+。
///   - 提供 trait `DecayStateProvider` + 預設 fail-closed 實作 `FailClosedDecayProvider`
///     供 spike 測試與 IMPL Sprint 4 接 PG pool 兩用。
pub trait DecayStateProvider {
    /// 查 strategy 當前 lifecycle_state（per V113 learning.decay_signals）。
    /// 返回 `Some("RETIRED" | "NORMAL_LIVE" | ...)`；query 失敗 Err。
    fn lifecycle_state(&self, strategy_id: &str) -> Result<Option<String>, LalTierError>;
}

/// 預設 fail-closed provider：Sprint 1A-ζ spike 不接 PG pool；任何 query 視為「DB 不可用」
/// 立即 fail-closed reject。Sprint 4+ 換成接 sqlx pool 的真實 provider。
///
/// 為什麼 fail-closed：M7 RETIRED 是 alpha-deficient 永久退役（per ADR-0044 Decision 1）；
/// 若 DB query 失敗時放行 fill = 等同 retire 形同虛設；違反 §二 原則 5「生存 > 利潤」+
/// 原則 6「Uncertainty defaults to conservative」。
pub struct FailClosedDecayProvider;

impl DecayStateProvider for FailClosedDecayProvider {
    fn lifecycle_state(&self, _strategy_id: &str) -> Result<Option<String>, LalTierError> {
        Err(LalTierError::DecayQueryFailed(
            "Sprint 1A-ζ spike stub: no PG pool wired; full IMPL Sprint 4+ — fail-closed".into(),
        ))
    }
}

/// Tier 0 fill RETIRED blocker — 接 `DecayStateProvider` 做 fail-closed gate。
pub struct Tier0FillBlocker<P: DecayStateProvider> {
    provider: P,
}

impl<P: DecayStateProvider> Tier0FillBlocker<P> {
    pub fn new(provider: P) -> Self {
        Self { provider }
    }

    /// 檢查 strategy_id 是否 RETIRED；RETIRED → Err(RetiredBlocked) fail-closed。
    ///
    /// 不變量：
    ///   - query 失敗 → Err(DecayQueryFailed)（不放行）；
    ///   - lifecycle_state = "RETIRED" → Err(RetiredBlocked)（reject fill）；
    ///   - lifecycle_state != "RETIRED" → Ok(())（fill allowed pass to Guardian）；
    ///   - lifecycle_state = None（無 row）→ Ok(())（strategy 不在 decay_signals；
    ///     新策略或 Stage 0R 前合理視為 not RETIRED；但 Sprint 4 IMPL 必複核此假設
    ///     是否仍對齊 ADR-0044 Decision 1 single decay authority）。
    pub fn check_retired(&self, strategy_id: &str) -> Result<(), LalTierError> {
        match self.provider.lifecycle_state(strategy_id)? {
            Some(state) if state == "RETIRED" => {
                Err(LalTierError::RetiredBlocked {
                    strategy_id: strategy_id.to_string(),
                })
            }
            _ => Ok(()),
        }
    }
}

// ---------------------------------------------------------------------------
// LAL Tier 0 → Tier 1 transition stub
// ---------------------------------------------------------------------------

/// 本 spike 用的 Tier 0/1 升階評估 stub。
///
/// per M1 design spec §3.4 全 6 條 hard gate（per ADR-0034 Decision 5）：
///   1. Prior approval threshold（rolling 30d ≥ 30 advisory + yes_rate > 80%）
///   2. Incident-free window（90d 無 M7 decay / Guardian block / 5-gate kill / M8）
///   3. Risk envelope check（per AMD-2026-05-09-03 RuntimeMaxEnvelope）
///   4. Operator opt-in（Console toggle ON per ADR-0034 Decision 4）
///   5. 24h undo path 可用（pre-proposal snapshot + handler 健康）
///   6. Post-hoc transparency（Slack + email + Console notification dry-run）
///
/// 本 spike 範圍：
///   - 結構 wire（caller 傳 PromotionEvidence struct）；
///   - 不真實 query DB；不接 governance audit_log；
///   - 完整 IMPL Sprint 4 LAL 1（40-60 hr per ADR-0034 落地估）。
#[derive(Debug, Clone)]
pub struct PromotionEvidence {
    pub prior_approval_pass: bool,
    pub incident_free_pass: bool,
    pub risk_envelope_pass: bool,
    pub operator_opt_in: bool,
    pub undo_path_healthy: bool,
    pub transparency_dryrun_pass: bool,
}

pub struct LalTransition;

impl LalTransition {
    /// Tier 0 → Tier 1 升階評估 stub：全 6 條 hard gate 必 PASS 才升 Tier 1 active。
    ///
    /// 為什麼用 PromotionEvidence struct：本 spike 不 query DB；caller（後續 Sprint 4
    /// LAL gate writer）自行收 6 條 evidence；本 module 只做布林 AND。
    ///
    /// 不變量：
    ///   - current_tier 必 Lal0Auto；其他 tier 升階走另外 path（Tier 2/3/4 在 Sprint 4+）；
    ///   - 全 6 條 PASS → Ok(Lal1LightReview)；任一 fail → Err(PromotionGateFailed)。
    pub fn evaluate_tier_0_to_1(
        current_tier: LalTier,
        evidence: &PromotionEvidence,
    ) -> Result<LalTier, LalTierError> {
        if current_tier != LalTier::Lal0Auto {
            return Err(LalTierError::TransitionNotImplemented {
                tier: current_tier.numeric_value(),
            });
        }
        if !evidence.prior_approval_pass {
            return Err(LalTierError::PromotionGateFailed {
                reason: "gate#1 prior_approval rolling 30d threshold not met".into(),
            });
        }
        if !evidence.incident_free_pass {
            return Err(LalTierError::PromotionGateFailed {
                reason: "gate#2 incident_free 90d window not clean".into(),
            });
        }
        if !evidence.risk_envelope_pass {
            return Err(LalTierError::PromotionGateFailed {
                reason: "gate#3 risk_envelope outside Stage 4 historical".into(),
            });
        }
        if !evidence.operator_opt_in {
            return Err(LalTierError::PromotionGateFailed {
                reason: "gate#4 Console toggle Auto-Approve OFF".into(),
            });
        }
        if !evidence.undo_path_healthy {
            return Err(LalTierError::PromotionGateFailed {
                reason: "gate#5 24h undo path not healthy".into(),
            });
        }
        if !evidence.transparency_dryrun_pass {
            return Err(LalTierError::PromotionGateFailed {
                reason: "gate#6 post-hoc transparency dryrun fail".into(),
            });
        }
        Ok(LalTier::Lal1LightReview)
    }

    /// Tier 2/3/4 transition stub：本 spike 不 IMPL；呼叫即 Err。
    /// Sprint 4 LAL 1 IMPL / Sprint 7-8 LAL 2 IMPL / LAL 3-4 永遠 operator manual。
    pub fn evaluate_tier_2_or_above(
        current_tier: LalTier,
    ) -> Result<LalTier, LalTierError> {
        Err(LalTierError::TransitionNotImplemented {
            tier: current_tier.numeric_value(),
        })
    }
}

// ---------------------------------------------------------------------------
// Tests — AC-1.1 reverse assert（per spike spec §AC-1.1 + dispatch packet §1.4 AC-4）
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    /// AC-1.1 #1：LalTier::from_i32(-1) 必 Err。
    #[test]
    fn test_lal_tier_from_negative() {
        let result = LalTier::from_i32(-1);
        assert!(result.is_err(), "expected Err for lal_level=-1, got {:?}", result);
        match result {
            Err(LalTierError::OutOfRange { provided }) => assert_eq!(provided, -1),
            other => panic!("expected OutOfRange, got {:?}", other),
        }
    }

    /// AC-1.1 #2：LalTier::from_i32(5) 必 Err。
    #[test]
    fn test_lal_tier_from_overflow() {
        let result = LalTier::from_i32(5);
        assert!(result.is_err(), "expected Err for lal_level=5, got {:?}", result);
        match result {
            Err(LalTierError::OutOfRange { provided }) => assert_eq!(provided, 5),
            other => panic!("expected OutOfRange, got {:?}", other),
        }
    }

    /// AC-1.1 #3：數字越大越嚴對齊 ADR-0034 line 41 — 0 < 1 < 2 < 3 < 4 全鏈。
    #[test]
    fn test_lal_tier_numeric_strictness_order() {
        assert!(LalTier::Lal0Auto.numeric_value() < LalTier::Lal1LightReview.numeric_value());
        assert!(LalTier::Lal1LightReview.numeric_value() < LalTier::Lal2FullReview.numeric_value());
        assert!(LalTier::Lal2FullReview.numeric_value() < LalTier::Lal3OperatorApproval.numeric_value());
        assert!(
            LalTier::Lal3OperatorApproval.numeric_value()
                < LalTier::Lal4OperatorAttestation.numeric_value()
        );
        // 全鏈 0 < 1 < 2 < 3 < 4 = 數字越大越嚴對齊 ADR-0034 line 41
        assert_eq!(LalTier::Lal0Auto.numeric_value(), 0);
        assert_eq!(LalTier::Lal4OperatorAttestation.numeric_value(), 4);
    }

    /// ADR-0034「數字越大越嚴」 — derive(PartialOrd, Ord) 排序必嚴格對齊 numeric_value()。
    /// 為什麼：LalTier 同時走兩條 ordering 軌道（derive per variant declaration order +
    /// numeric_value() per ADR-0034）；未來在 enum 中間插入新 variant（例 Lal0_5HumanCheck）
    /// 會被 derive 自動排在 Lal0Auto 之後 Lal1 之前，**改變既存比較行為而 0 compile-time fail**。
    /// 本 test 確保兩條軌道 lock-step；任何 silent ordering drift 即時 fail（per E2 audit
    /// OBSERVE-3 2026-05-22）。
    #[test]
    fn test_partial_ord_derive_matches_numeric_value() {
        let tiers = [
            LalTier::Lal0Auto,
            LalTier::Lal1LightReview,
            LalTier::Lal2FullReview,
            LalTier::Lal3OperatorApproval,
            LalTier::Lal4OperatorAttestation,
        ];
        for i in 0..tiers.len() {
            for j in 0..tiers.len() {
                let derive_cmp = tiers[i].cmp(&tiers[j]);
                let numeric_cmp = tiers[i].numeric_value().cmp(&tiers[j].numeric_value());
                assert_eq!(
                    derive_cmp, numeric_cmp,
                    "derive PartialOrd 與 numeric_value() 不對齊 — i={} j={} tier_i={:?}={} tier_j={:?}={}",
                    i,
                    j,
                    tiers[i],
                    tiers[i].numeric_value(),
                    tiers[j],
                    tiers[j].numeric_value()
                );
            }
        }
    }

    /// from_i32 5 條合法輸入全 Ok。
    #[test]
    fn test_lal_tier_from_i32_legal_inputs() {
        assert_eq!(LalTier::from_i32(0).unwrap(), LalTier::Lal0Auto);
        assert_eq!(LalTier::from_i32(1).unwrap(), LalTier::Lal1LightReview);
        assert_eq!(LalTier::from_i32(2).unwrap(), LalTier::Lal2FullReview);
        assert_eq!(LalTier::from_i32(3).unwrap(), LalTier::Lal3OperatorApproval);
        assert_eq!(LalTier::from_i32(4).unwrap(), LalTier::Lal4OperatorAttestation);
    }

    /// tier_name 對齊 V112 lease_lal_tiers CHECK constraint 5 值。
    #[test]
    fn test_lal_tier_name_alignment() {
        assert_eq!(LalTier::Lal0Auto.tier_name(), "LAL_0_AUTO");
        assert_eq!(LalTier::Lal1LightReview.tier_name(), "LAL_1_LIGHT_REVIEW");
        assert_eq!(LalTier::Lal2FullReview.tier_name(), "LAL_2_FULL_REVIEW");
        assert_eq!(LalTier::Lal3OperatorApproval.tier_name(), "LAL_3_OPERATOR_APPROVAL");
        assert_eq!(
            LalTier::Lal4OperatorAttestation.tier_name(),
            "LAL_4_OPERATOR_ATTESTATION"
        );
    }

    /// from_i32 extra 越界：MIN / 100 / 1000。
    #[test]
    fn test_lal_tier_from_i32_extreme_out_of_range() {
        assert!(LalTier::from_i32(i32::MIN).is_err());
        assert!(LalTier::from_i32(100).is_err());
        assert!(LalTier::from_i32(1000).is_err());
        assert!(LalTier::from_i32(i32::MAX).is_err());
    }

    /// FailClosedDecayProvider 必 fail-closed（spike stub 無 PG pool）。
    #[test]
    fn test_fail_closed_provider_rejects() {
        let provider = FailClosedDecayProvider;
        let result = provider.lifecycle_state("test_strategy");
        assert!(result.is_err(), "FailClosedDecayProvider must return Err");
        match result {
            Err(LalTierError::DecayQueryFailed(_)) => {}
            other => panic!("expected DecayQueryFailed, got {:?}", other),
        }
    }

    /// Tier0FillBlocker 接 RETIRED provider 必 Err(RetiredBlocked)。
    #[test]
    fn test_tier_0_blocker_retired_path() {
        // 自定 mock provider 模擬 lifecycle_state='RETIRED'
        struct RetiredProvider;
        impl DecayStateProvider for RetiredProvider {
            fn lifecycle_state(&self, _strategy_id: &str) -> Result<Option<String>, LalTierError> {
                Ok(Some("RETIRED".into()))
            }
        }
        let blocker = Tier0FillBlocker::new(RetiredProvider);
        let result = blocker.check_retired("test_strategy_retired");
        match result {
            Err(LalTierError::RetiredBlocked { strategy_id }) => {
                assert_eq!(strategy_id, "test_strategy_retired");
            }
            other => panic!("expected RetiredBlocked, got {:?}", other),
        }
    }

    /// Tier0FillBlocker 接 NORMAL_LIVE provider 必 Ok。
    #[test]
    fn test_tier_0_blocker_normal_live_allowed() {
        struct NormalLiveProvider;
        impl DecayStateProvider for NormalLiveProvider {
            fn lifecycle_state(&self, _strategy_id: &str) -> Result<Option<String>, LalTierError> {
                Ok(Some("NORMAL_LIVE".into()))
            }
        }
        let blocker = Tier0FillBlocker::new(NormalLiveProvider);
        assert!(blocker.check_retired("test_strategy_normal").is_ok());
    }

    /// Tier0FillBlocker 接 None（無 row in decay_signals）→ Ok（新策略合理 pass）。
    #[test]
    fn test_tier_0_blocker_none_state_allowed() {
        struct NoRowProvider;
        impl DecayStateProvider for NoRowProvider {
            fn lifecycle_state(&self, _strategy_id: &str) -> Result<Option<String>, LalTierError> {
                Ok(None)
            }
        }
        let blocker = Tier0FillBlocker::new(NoRowProvider);
        assert!(blocker.check_retired("new_strategy_no_decay_row").is_ok());
    }

    /// Tier 0 → Tier 1 升階全 PASS。
    #[test]
    fn test_tier_0_to_1_all_pass() {
        let evidence = PromotionEvidence {
            prior_approval_pass: true,
            incident_free_pass: true,
            risk_envelope_pass: true,
            operator_opt_in: true,
            undo_path_healthy: true,
            transparency_dryrun_pass: true,
        };
        let result = LalTransition::evaluate_tier_0_to_1(LalTier::Lal0Auto, &evidence);
        assert_eq!(result.unwrap(), LalTier::Lal1LightReview);
    }

    /// Tier 0 → Tier 1 升階任一 gate fail → Err。
    #[test]
    fn test_tier_0_to_1_gate_fail() {
        let mut evidence = PromotionEvidence {
            prior_approval_pass: true,
            incident_free_pass: true,
            risk_envelope_pass: true,
            operator_opt_in: true,
            undo_path_healthy: true,
            transparency_dryrun_pass: true,
        };

        // gate#2 incident_free fail
        evidence.incident_free_pass = false;
        let result = LalTransition::evaluate_tier_0_to_1(LalTier::Lal0Auto, &evidence);
        match result {
            Err(LalTierError::PromotionGateFailed { reason }) => {
                assert!(reason.contains("incident_free"));
            }
            other => panic!("expected PromotionGateFailed, got {:?}", other),
        }
    }

    /// Tier 1/2/3/4 → Tier 1 升階：本 spike 不接受非 Lal0Auto 為起點。
    #[test]
    fn test_tier_promotion_only_from_tier_0() {
        let evidence = PromotionEvidence {
            prior_approval_pass: true,
            incident_free_pass: true,
            risk_envelope_pass: true,
            operator_opt_in: true,
            undo_path_healthy: true,
            transparency_dryrun_pass: true,
        };
        let result = LalTransition::evaluate_tier_0_to_1(LalTier::Lal1LightReview, &evidence);
        match result {
            Err(LalTierError::TransitionNotImplemented { tier }) => assert_eq!(tier, 1),
            other => panic!("expected TransitionNotImplemented, got {:?}", other),
        }
    }

    /// Tier 2/3/4 升階一律 Err（本 spike 不 IMPL）。
    #[test]
    fn test_tier_2_or_above_not_implemented() {
        for tier in [
            LalTier::Lal2FullReview,
            LalTier::Lal3OperatorApproval,
            LalTier::Lal4OperatorAttestation,
        ] {
            let result = LalTransition::evaluate_tier_2_or_above(tier);
            match result {
                Err(LalTierError::TransitionNotImplemented { tier: t }) => {
                    assert_eq!(t, tier.numeric_value());
                }
                other => panic!("expected TransitionNotImplemented for {:?}, got {:?}", tier, other),
            }
        }
    }
}
