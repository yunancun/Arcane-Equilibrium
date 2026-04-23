//! Combine Layer — Track P 物理層 + Track L ML 退場決策融合
//! Combine Layer — fusion of Track P physical + Track L ML exit decisions
//!
//! 第一原則（不可違背） / Core invariant:
//!   系統永遠 ≥ Track P 下界 — `PhysicalDecision::Lock` 永不被 ML veto 推翻。
//!   System is always ≥ Track P lower bound — a physical Lock is never vetoed
//!   by ML. ML signals can concur (Hybrid) or — in future phases — escalate a
//!   physical Hold to Lock (ML-override) but cannot downgrade a Lock to Hold.
//!
//! Phase 1a（當前）/ Phase 1a (current):
//!   Call-sites pass `ml_opt = None` 且 `CombineConfig::ml_override_high = 2.0`
//!   （不可達 sentinel）→ output 永遠 `(map(physical), Physical)`。雙重保險：
//!   call-site 層 ml_opt=None + layer 層 unreachable override → P-only。
//!   Call-sites supply `ml_opt = None`, and `ml_override_high = 2.0` (unreachable
//!   sentinel) ensures even if ml_opt were supplied it could never escalate Hold
//!   to Lock. Double safety: site-level None + layer-level unreachable override.
//!
//! 字典對齊 / Dictionary alignment:
//!   `ExitSource::as_tag()` 回傳 4 個穩定字串 (Physical / ML / Hybrid / Disabled)，
//!   寫入 `trading.fills.details.exit_source`，供 Python `parse_exit_tag` 對齊。
//!   Stable 4-string tag vocabulary persisted to `fills.details.exit_source`;
//!   must stay byte-identical with Python `parse_exit_tag` dictionary.
//!
//! 安全網 / Safety nets:
//!   - ML score NaN/Inf → degrade to Physical (Disabled { reason="ML score non-finite" })
//!   - ML model age > max_model_age_secs → degrade to Physical (Disabled { reason="ML model stale" })
//!   - ML confidence NaN/Inf → degrade to Physical (Disabled { reason="ML confidence non-finite" })
//!   降級後 ExitSignal 僅由 physical 決定（Lock→Lock / Hold→Hold）。
//!
//! 介面凍結 / Interface freeze:
//!   T4 skeleton. T3 只產生 `PhysicalDecision`，T5 audit 讀 `ExitSource::as_tag()`。
//!   T4 skeleton; T3 feeds `PhysicalDecision`, T5 audit consumes `ExitSource::as_tag()`.

use crate::exit_features::PhysicalDecision;

// ---------------------------------------------------------------------------
// Public types / 公開型別
// ---------------------------------------------------------------------------

/// 最終退場訊號 / Final exit signal emitted to tick dispatch.
///
/// 這是 Combine Layer 唯一對外動作訊號。`Lock` 下游映射到既有
/// `RiskAction::ClosePosition(tag)`，`Hold` 下游保持持倉。
/// Only action signal out of the combine layer; `Lock` maps downstream to
/// `RiskAction::ClosePosition(tag)`; `Hold` keeps position open.
#[derive(Debug, Clone, PartialEq)]
pub enum ExitSignal {
    Hold,
    Lock,
}

/// 退場決策來源 / Decision-source taxonomy.
///
/// 寫入 `trading.fills.details.exit_source`（字典穩定，Python parse_exit_tag 對齊）。
/// Persisted to `fills.details.exit_source`; stable dictionary aligned with Python.
#[derive(Debug, Clone, PartialEq)]
pub enum ExitSource {
    /// 純物理層決策 / Physical-only.
    Physical,
    /// 純 ML 決策（Phase 1a 不可達；unreachable in Phase 1a）.
    ML { model_id: String, score: f32 },
    /// 物理 Lock + ML 高信心確認 / Physical Lock + high-confidence ML concurrence.
    Hybrid {
        physical_reason: String,
        ml_score: f32,
    },
    /// ML 失效降級 / ML unavailable → degraded to Physical decision.
    Disabled { reason: String },
}

impl ExitSource {
    /// 穩定 tag 字串 / Stable tag string for persistence & Python parse alignment.
    ///
    /// 字典鎖定：只有這 4 個 variant 對應到 fills.details.exit_source。
    /// Dictionary frozen: exactly 4 variants map to `fills.details.exit_source`.
    pub fn as_tag(&self) -> &'static str {
        match self {
            ExitSource::Physical => "Physical",
            ExitSource::ML { .. } => "ML",
            ExitSource::Hybrid { .. } => "Hybrid",
            ExitSource::Disabled { .. } => "Disabled",
        }
    }
}

/// ML 推論結果 / ML inference result supplied to combine layer.
///
/// Phase 1a 永遠為 None。Phase 1b+ 由 Track L 推論產生。
/// Always None in Phase 1a; produced by Track L inference from Phase 1b onward.
#[derive(Debug, Clone)]
pub struct MLInference {
    pub id: String,
    pub score: f32,
    pub age_secs: u64,
    pub confidence: f32,
}

/// Combine Layer 行為參數 / Combine Layer behaviour tuning.
///
/// Phase 1a：`ml_override_high = 2.0` 不可達 sentinel（f32 score ∈ [0,1]），
/// 保證即使 call-site 意外傳入 `Some(ml)`，ML 也無法將 Hold 升級為 Lock。
/// Phase 1a: `ml_override_high = 2.0` unreachable sentinel (score domain is
/// [0, 1]); guarantees ML can never escalate Hold→Lock even if `Some(ml)`
/// is accidentally passed.
#[derive(Debug, Clone)]
pub struct CombineConfig {
    /// Physical Lock 時，ML 同意確認的最低 score / Min ML score to confirm a physical Lock (Hybrid).
    pub ml_confirm_threshold: f32,
    /// Physical Hold 時，ML 主動觸發 Lock 的最低 score / Min ML score to escalate Hold→Lock.
    /// Phase 1a = 2.0 (unreachable sentinel).
    pub ml_override_high: f32,
    /// ML veto 邊界（見第一原則：veto **不** 推翻 physical Lock，保留給未來政策）
    /// ML veto bound (per invariant: veto does **not** override physical Lock;
    /// retained for future policy experimentation).
    pub ml_veto_low: f32,
    /// ML model 最大可容忍齡期（秒）/ Max tolerable model age (seconds).
    pub max_model_age_secs: u64,
}

impl Default for CombineConfig {
    fn default() -> Self {
        Self {
            ml_confirm_threshold: 0.70,
            // Phase 1a: unreachable sentinel (scores are in [0, 1]).
            // Phase 1a：不可達 sentinel（分數域為 [0, 1]）。
            ml_override_high: 2.0,
            ml_veto_low: 0.10,
            max_model_age_secs: 7 * 24 * 3600, // 7 days / 7 天
        }
    }
}

// ---------------------------------------------------------------------------
// Core fusion function / 核心融合函數
// ---------------------------------------------------------------------------

/// Combine Layer 核心融合函數 / Core combine function.
///
/// # Invariants / 不變式
/// 1. `physical = Lock(r)` ⇒ `ExitSignal::Lock`（ML veto 永不推翻）
///    Physical Lock always yields ExitSignal::Lock regardless of ML.
/// 2. `ml_opt = None` ⇒ output 僅由 physical 決定，source = `Physical`
///    None ml_opt → output determined solely by physical, source = Physical.
/// 3. ML 失效（NaN/Inf score or confidence, age overflow）⇒ 降級為 Physical，
///    source = `Disabled { reason }`；ExitSignal 仍按 physical 映射。
///    Invalid ml (NaN/Inf or stale) ⇒ downgrade to Physical, source = Disabled.
/// 4. Phase 1a: call-site 層傳 None + layer 層 `ml_override_high = 2.0` → P-only.
///    Phase 1a: site passes None + unreachable sentinel → pure P-only operation.
///
/// # Decision matrix / 決策矩陣
///
/// | physical | ml_opt          | condition                 | signal | source                              |
/// |----------|-----------------|---------------------------|--------|-------------------------------------|
/// | Lock(r)  | None            | —                         | Lock   | Physical                            |
/// | Hold     | None            | —                         | Hold   | Physical                            |
/// | any      | Some(bad_ml)    | NaN / Inf / age overflow  | map(p) | Disabled { reason }                 |
/// | Lock(r)  | Some(ml)        | score ≥ confirm_threshold | Lock   | Hybrid { physical_reason, ml_score }|
/// | Lock(r)  | Some(ml)        | score < confirm_threshold | Lock   | Physical                            |
/// | Hold     | Some(ml)        | score ≥ override_high     | Lock   | ML { model_id, score }              |
/// | Hold     | Some(ml)        | score <  override_high    | Hold   | Physical                            |
///
/// `map(physical)` means: `Lock(_)` → `ExitSignal::Lock`, `Hold` → `ExitSignal::Hold`.
/// `map(physical)` 表示：Lock → Lock，Hold → Hold。
pub fn combine_exit_decision(
    physical: PhysicalDecision,
    ml_opt: Option<MLInference>,
    cfg: &CombineConfig,
) -> (ExitSignal, ExitSource) {
    // ── Safety net: validate & sanitise ML input ──
    // 安全網：檢驗並淨化 ML 輸入
    let (ml_clean, disabled_reason) = match ml_opt {
        None => (None, None),
        Some(m) => {
            if !m.score.is_finite() {
                (None, Some("ML score non-finite".to_string()))
            } else if !m.confidence.is_finite() {
                (None, Some("ML confidence non-finite".to_string()))
            } else if m.age_secs > cfg.max_model_age_secs {
                (
                    None,
                    Some(format!(
                        "ML model stale age={}s > max={}s",
                        m.age_secs, cfg.max_model_age_secs
                    )),
                )
            } else {
                (Some(m), None)
            }
        }
    };

    // ── Degraded path: ML was supplied but invalid → output driven by physical, source = Disabled ──
    // 降級路徑：ML 有提供但失效 → 僅用 physical 驅動，source = Disabled
    if let Some(reason) = disabled_reason {
        let signal = match &physical {
            PhysicalDecision::Lock(_) => ExitSignal::Lock,
            PhysicalDecision::Hold => ExitSignal::Hold,
        };
        return (signal, ExitSource::Disabled { reason });
    }

    // ── Primary fusion / 主融合 ──
    match (physical, ml_clean) {
        // 1. Physical Lock + no ML → Physical-only Lock.
        //    物理鎖 + 無 ML → 純物理鎖。
        (PhysicalDecision::Lock(_r), None) => (ExitSignal::Lock, ExitSource::Physical),

        // 2. Hold + no ML → Physical-only Hold.
        //    Hold + 無 ML → 純物理 Hold。
        (PhysicalDecision::Hold, None) => (ExitSignal::Hold, ExitSource::Physical),

        // 3. Physical Lock + ML concurrence → Hybrid (highest confidence).
        //    物理鎖 + ML 高信心確認 → Hybrid（最高信心）。
        (PhysicalDecision::Lock(r), Some(m)) if m.score >= cfg.ml_confirm_threshold => (
            ExitSignal::Lock,
            ExitSource::Hybrid {
                physical_reason: r,
                ml_score: m.score,
            },
        ),

        // 4. Physical Lock + ML (any score < confirm) → Physical (invariant: ML veto does NOT
        //    override physical Lock; low ML score silently falls through to Physical-only Lock).
        //    物理鎖 + ML 任何 score < confirm → Physical（不變式：ML veto 不推翻物理鎖，
        //    低分 ML 靜默降為 Physical-only Lock）。
        (PhysicalDecision::Lock(_r), Some(_m)) => (ExitSignal::Lock, ExitSource::Physical),

        // 5. Hold + ML override (score ≥ override_high, Phase 1a unreachable).
        //    Hold + ML 主動 override（Phase 1a 不可達）。
        (PhysicalDecision::Hold, Some(m)) if m.score >= cfg.ml_override_high => (
            ExitSignal::Lock,
            ExitSource::ML {
                model_id: m.id,
                score: m.score,
            },
        ),

        // 6. Hold + ML below override → Physical Hold (Phase 1a always-this branch when ml supplied).
        //    Hold + ML 未達 override → 物理 Hold（Phase 1a ml 有提供時的預設分支）。
        (PhysicalDecision::Hold, Some(_m)) => (ExitSignal::Hold, ExitSource::Physical),
    }
}

// ---------------------------------------------------------------------------
// INFRA-PREBUILD-1 Part A (2026-04-23): Shadow-mode MLInference mock builder
// ---------------------------------------------------------------------------

/// Build a mock `MLInference` from a strategy/symbol edge estimate — used only
/// in Phase 2 shadow mode (`RiskConfig.exit.shadow_enabled=true`) to exercise
/// the Combine Layer's Hybrid path without a real ONNX model. Phase 3+ will
/// swap this for the real `edge_predictor::predict_exit(...)` call.
///
/// # Semantics
///
/// Maps `shrunk_bps ∈ [-∞, +∞]` → `score ∈ [0, 1]` via clamp-rescale centred
/// on ±10 bps (the `edge_estimates.json` typical operating range):
///
///   score = clamp01((shrunk_bps + 10) / 20)
///
/// - `shrunk_bps ≤ -10` → `score = 0.0` (ML says "exit urgently")
/// - `shrunk_bps =   0` → `score = 0.5` (neutral)
/// - `shrunk_bps ≥ +10` → `score = 1.0` (ML says "keep running")
///
/// This mapping is intentionally a monotone proxy for "expected net edge" so
/// Combine Layer behaviour in shadow looks roughly like what a trained model
/// would do: positive-edge positions get `score ≥ ml_confirm_threshold=0.70`
/// (i.e. `shrunk_bps ≥ +4`), producing `Hybrid` tags on physical Locks.
///
/// # Invariants
///
/// 1. Returns `None` when `shrunk_bps_opt = None` — caller's `combine_exit_decision`
///    falls back to `ml_opt=None` path (pure Physical).
/// 2. `model_id` is stable `"shadow_mock_v1"` — downstream persistence can
///    distinguish mock from real inference via this tag.
/// 3. `confidence` is a placeholder `0.5` (mid) — mock has no calibration.
/// 4. `ml_override_high=2.0` sentinel still holds: score ≤ 1.0 can never
///    trigger `Hold → Lock` escalation (invariant #4 in `combine_exit_decision`).
///
/// # 語意 / Semantics（中）
///
/// 將 `shrunk_bps` 對應到 `score ∈ [0, 1]`，中心 ±10 bps（edge_estimates.json 典型範圍）。
/// 此為 Phase 2 shadow 模式下的 mock，讓 Combine Layer 走 Hybrid 路徑練兵；
/// Phase 3+ 將切真 ONNX 推論。`ml_override_high=2.0` 不可達 sentinel 仍守
/// Phase 1a 不變式（ML 永遠不能 Hold → Lock）。
pub fn build_ml_inference_shadow(
    shrunk_bps_opt: Option<f64>,
    cell_age_secs: Option<u64>,
) -> Option<MLInference> {
    let shrunk_bps = shrunk_bps_opt?;
    if !shrunk_bps.is_finite() {
        return None;
    }
    // clamp01((x + 10) / 20) — center=0 bps, domain ±10 bps → score ∈ [0, 1]
    let raw = (shrunk_bps + 10.0) / 20.0;
    let score = raw.clamp(0.0, 1.0) as f32;
    Some(MLInference {
        id: "shadow_mock_v1".to_string(),
        score,
        age_secs: cell_age_secs.unwrap_or(0),
        confidence: 0.5,
    })
}

// ---------------------------------------------------------------------------
// Tests / 測試
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn default_cfg() -> CombineConfig {
        CombineConfig::default()
    }

    #[test]
    fn test_combine_phase1a_p_only_lock_when_physical_locks() {
        // Phase 1a invariant: ml_opt=None, physical=Lock → (Lock, Physical).
        // Phase 1a 不變式：ml_opt=None, physical=Lock → (Lock, Physical)。
        let cfg = default_cfg();
        let (signal, source) = combine_exit_decision(
            PhysicalDecision::Lock("PHYS-LOCK: giveback 0.8 ATR".to_string()),
            None,
            &cfg,
        );
        assert_eq!(signal, ExitSignal::Lock);
        assert_eq!(source, ExitSource::Physical);
        assert_eq!(source.as_tag(), "Physical");
    }

    #[test]
    fn test_combine_phase1a_p_only_hold_when_physical_holds() {
        // Phase 1a invariant: ml_opt=None, physical=Hold → (Hold, Physical).
        // Phase 1a 不變式：ml_opt=None, physical=Hold → (Hold, Physical)。
        let cfg = default_cfg();
        let (signal, source) = combine_exit_decision(PhysicalDecision::Hold, None, &cfg);
        assert_eq!(signal, ExitSignal::Hold);
        assert_eq!(source, ExitSource::Physical);
        assert_eq!(source.as_tag(), "Physical");
    }

    #[test]
    fn test_combine_ml_nan_score_degrades_to_physical() {
        // Safety net: NaN score → Disabled source, physical-driven signal.
        // 安全網：NaN score → Disabled source，signal 由 physical 決定。
        let cfg = default_cfg();
        let bad_ml = MLInference {
            id: "m-v0.1".to_string(),
            score: f32::NAN,
            age_secs: 10,
            confidence: 0.9,
        };
        // physical=Lock case
        let (sig, src) = combine_exit_decision(
            PhysicalDecision::Lock("reason".to_string()),
            Some(bad_ml.clone()),
            &cfg,
        );
        assert_eq!(sig, ExitSignal::Lock);
        match &src {
            ExitSource::Disabled { reason } => assert!(reason.contains("non-finite")),
            other => panic!("expected Disabled, got {:?}", other),
        }
        assert_eq!(src.as_tag(), "Disabled");

        // physical=Hold case
        let (sig2, src2) = combine_exit_decision(PhysicalDecision::Hold, Some(bad_ml), &cfg);
        assert_eq!(sig2, ExitSignal::Hold);
        assert_eq!(src2.as_tag(), "Disabled");
    }

    #[test]
    fn test_combine_ml_stale_model_degrades_to_physical() {
        // Safety net: age_secs > max_model_age_secs → Disabled { reason }.
        // 安全網：模型過期 → Disabled { reason }。
        let cfg = default_cfg();
        let stale_ml = MLInference {
            id: "m-old".to_string(),
            score: 0.85,
            age_secs: cfg.max_model_age_secs + 1,
            confidence: 0.9,
        };
        let (sig, src) = combine_exit_decision(
            PhysicalDecision::Lock("reason".to_string()),
            Some(stale_ml),
            &cfg,
        );
        assert_eq!(sig, ExitSignal::Lock);
        match &src {
            ExitSource::Disabled { reason } => assert!(reason.contains("stale")),
            other => panic!("expected Disabled (stale), got {:?}", other),
        }
    }

    #[test]
    fn test_combine_invariant_ml_veto_cannot_override_physical_lock() {
        // CORE INVARIANT: even with score below ml_veto_low, physical Lock must
        // still produce ExitSignal::Lock. ML cannot veto a Track P lock.
        // 核心不變式：即使 ML score < ml_veto_low，physical Lock 仍必須產出 Lock。
        // ML 不得否決 Track P 的物理鎖（系統永遠 ≥ Track P 下界）。
        let cfg = default_cfg();
        assert!(cfg.ml_veto_low > 0.0);
        let veto_ml = MLInference {
            id: "m-veto".to_string(),
            score: 0.01, // well below ml_veto_low = 0.10
            age_secs: 5,
            confidence: 0.99,
        };
        let (signal, source) = combine_exit_decision(
            PhysicalDecision::Lock("PHYS-LOCK: critical".to_string()),
            Some(veto_ml),
            &cfg,
        );
        assert_eq!(
            signal,
            ExitSignal::Lock,
            "invariant violation: ML veto overrode physical Lock"
        );
        // source falls through to Physical (not Disabled — the ml input was valid, just low-score)
        assert_eq!(source, ExitSource::Physical);
    }

    // ---- Additional coverage (not strictly required by task) ----

    #[test]
    fn test_combine_hybrid_when_physical_lock_and_ml_confirms() {
        // Phase 1b future: Physical Lock + ML ≥ confirm → Hybrid.
        // Phase 1b 未來：物理鎖 + ML 確認 → Hybrid。
        let cfg = default_cfg();
        let concur = MLInference {
            id: "m-c".to_string(),
            score: 0.80, // >= 0.70 confirm_threshold
            age_secs: 3,
            confidence: 0.9,
        };
        let (sig, src) = combine_exit_decision(
            PhysicalDecision::Lock("giveback".to_string()),
            Some(concur),
            &cfg,
        );
        assert_eq!(sig, ExitSignal::Lock);
        match &src {
            ExitSource::Hybrid {
                physical_reason,
                ml_score,
            } => {
                assert_eq!(physical_reason, "giveback");
                assert!((*ml_score - 0.80).abs() < 1e-6);
            }
            other => panic!("expected Hybrid, got {:?}", other),
        }
        assert_eq!(src.as_tag(), "Hybrid");
    }

    #[test]
    fn test_combine_phase1a_override_sentinel_is_unreachable() {
        // Any Some(ml) with score in [0, 1] combined with Hold MUST NOT produce
        // ExitSource::ML under Phase 1a defaults (override_high = 2.0 unreachable).
        // Phase 1a 保險：任何 [0,1] 分數 + Hold 都不應產 ExitSource::ML。
        let cfg = default_cfg();
        for &s in &[0.0_f32, 0.5, 0.95, 0.999, 1.0] {
            let ml = MLInference {
                id: "m".to_string(),
                score: s,
                age_secs: 1,
                confidence: 0.9,
            };
            let (sig, src) = combine_exit_decision(PhysicalDecision::Hold, Some(ml), &cfg);
            assert_eq!(sig, ExitSignal::Hold);
            assert_eq!(
                src,
                ExitSource::Physical,
                "Phase 1a unreachable-sentinel invariant broken at score={}",
                s
            );
        }
    }

    #[test]
    fn test_exit_source_tag_alignment() {
        // Dictionary alignment check: the 4 tag strings are frozen.
        // 字典對齊檢查：4 個 tag 字串凍結。
        assert_eq!(ExitSource::Physical.as_tag(), "Physical");
        assert_eq!(
            ExitSource::ML {
                model_id: "x".to_string(),
                score: 0.5
            }
            .as_tag(),
            "ML"
        );
        assert_eq!(
            ExitSource::Hybrid {
                physical_reason: "r".to_string(),
                ml_score: 0.8
            }
            .as_tag(),
            "Hybrid"
        );
        assert_eq!(
            ExitSource::Disabled {
                reason: "stale".to_string()
            }
            .as_tag(),
            "Disabled"
        );
    }

    #[test]
    fn test_combine_config_default_values() {
        // Guardrail: Phase 1a defaults must match the unreachable-sentinel contract.
        // 守護：Phase 1a 預設必須符合不可達 sentinel 契約。
        let cfg = CombineConfig::default();
        assert!((cfg.ml_override_high - 2.0).abs() < 1e-6);
        assert!(cfg.ml_confirm_threshold > 0.0 && cfg.ml_confirm_threshold < 1.0);
        assert!(cfg.ml_veto_low > 0.0 && cfg.ml_veto_low < cfg.ml_confirm_threshold);
        assert_eq!(cfg.max_model_age_secs, 7 * 24 * 3600);
    }
}
