//! Edge predictor gate — §7.3 core decision logic.
//! 預測器 gate — §7.3 核心決策邏輯。
//!
//! MODULE_NOTE (EN): Pure function mapping (features, predictor store, config)
//!   to a `PredictorGateOutcome`. Follows the F2 correct ordering from spec:
//!   invariant #12 feature sanity → load_for → invariant #11 staleness →
//!   predict → monotone rearrangement → cost margin check → ε-greedy
//!   exploration branch (paper engine only). Returns Fallback (reason code)
//!   whenever the caller must defer to the existing JS shrinkage gate, keeping
//!   this module side-effect free — the caller is responsible for emitting any
//!   `PipelineCommand::EmitShadowFill` or incrementing metrics.
//! MODULE_NOTE (中): (features, store, config) → `PredictorGateOutcome` 的純函數。
//!   按 §7.3 F2 修正的順序實施：feature sanity → load_for → staleness →
//!   predict → 單調重排 → cost margin → ε-greedy 分支（僅 paper）。任何
//!   回退場景返回 Fallback(reason)，由 caller 負責派發 IPC 命令與 metric 增量，
//!   使本模組保持純函數無副作用。
//!
//! Spec: docs/references/2026-04-15--edge_predictor_spec.md v1.4 §7.3 · §7.4

use rand::{rngs::SmallRng, Rng};

use super::rearrangement::enforce_monotone;
use super::{EdgePredictorStore, FeatureVectorV1, PredictError, PredictorArtifactBinding};
use crate::config::risk_config::EdgePredictor as EdgePredictorCfg;
use crate::tick_pipeline::PipelineKind;

/// ADR-0051 A3 action contract. Quantity uses the baseline instrument's units.
/// This pure contract does not select a quantile-to-size policy or activate serving.
#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
#[serde(
    tag = "action",
    rename_all = "SCREAMING_SNAKE_CASE",
    deny_unknown_fields
)]
pub enum AdvisoryAction {
    #[serde(alias = "ALLOW")]
    NoOp,
    Veto {
        reason: String,
    },
    SizeDown {
        max_quantity: f64,
        reason: String,
    },
}

/// Derived by the Rust caller, never by a model-supplied classification.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AdvisoryPositionEffect {
    RiskIncreasingEntry,
    RiskReduction,
    Unknown,
}

/// Scalar decision after all existing gates; a denial retains its original reason.
#[derive(Debug, Clone, PartialEq)]
pub struct AdvisoryDecision {
    pub allowed: bool,
    pub quantity: f64,
    pub reason: Option<String>,
}

/// Apply an already-selected advisory action to an authoritative baseline.
/// `identity_matches` must come from the caller's scope/artifact checks; false
/// disables all model contribution. This is not a qualification/activation check.
/// The action cannot mutate instrument, side, price, venue or order attributes.
pub fn apply_advisory_action(
    mut baseline: AdvisoryDecision,
    action: &AdvisoryAction,
    position_effect: AdvisoryPositionEffect,
    identity_matches: bool,
) -> AdvisoryDecision {
    // Preserve superior denials and bypass even malformed actions on protection
    // paths or unknown identity. Model input cannot delay or shrink a reduction.
    if !baseline.allowed
        || position_effect != AdvisoryPositionEffect::RiskIncreasingEntry
        || !identity_matches
    {
        return baseline;
    }
    match action {
        AdvisoryAction::NoOp => {}
        AdvisoryAction::Veto { reason } => {
            baseline.allowed = false;
            baseline.quantity = 0.0;
            baseline.reason = Some(reason.clone());
        }
        AdvisoryAction::SizeDown {
            max_quantity,
            reason,
        } => {
            if !max_quantity.is_finite() || *max_quantity < 0.0 {
                return AdvisoryDecision {
                    allowed: false,
                    quantity: 0.0,
                    reason: Some("predictor_size_down_invalid_quantity".into()),
                };
            }
            if !baseline.quantity.is_finite() || baseline.quantity <= 0.0 {
                return AdvisoryDecision {
                    allowed: false,
                    quantity: 0.0,
                    reason: Some("predictor_size_down_invalid_baseline_quantity".into()),
                };
            }
            if *max_quantity < baseline.quantity {
                baseline.quantity = *max_quantity;
                baseline.allowed = *max_quantity > 0.0;
                baseline.reason = Some(reason.clone());
            }
        }
    }
    baseline
}

/// Identifiers every predictor gate call needs independent of features.
/// gate 除 features 外每次調用需要的識別資訊。
#[derive(Debug, Clone)]
pub struct GateInputs<'a> {
    /// Independently frozen expected artifact identity; absent disables contribution.
    pub expected_binding: Option<PredictorArtifactBinding>,
    /// Engine calling into the gate. Paper uniquely honours ε-greedy exploration.
    /// 呼叫 gate 的引擎種類。僅 Paper 走 ε-greedy 探索分支。
    pub engine_kind: PipelineKind,
    /// Strategy name used to look up the per-strategy predictor slot.
    /// 用於查 per-strategy predictor 的策略名。
    pub strategy: &'a str,
    /// Symbol forwarded to `ShadowFillPayload` when the exploration branch fires.
    /// 探索分支觸發時轉發給 `ShadowFillPayload` 的 symbol。
    pub symbol: &'a str,
    /// DCS context_id (see §5.3) — used by the Python consumer to join
    /// `decision_shadow_fills` back to the original feature snapshot.
    /// DCS context_id（§5.3），Python 消費者用它 join 回特徵快照。
    pub context_id: &'a str,
    /// Round-trip cost in bps (caller computes as `2·(fee+slippage)·1e4`).
    /// 來回成本 bps；caller 依 `2·(fee+slippage)·1e4` 計算。
    pub cost_bps: f64,
    /// `true` iff this intent adds to an existing position (vs first entry).
    /// Only set by the caller when `require_q10_positive_for_adds` could fire.
    /// 是否為加倉意圖；用於 `require_q10_positive_for_adds` 分支。
    pub is_add_to_existing: bool,
    /// Wallclock ms at gate-evaluation time; placed into `ShadowFillPayload`.
    /// gate 評估時的 wallclock ms；寫入 `ShadowFillPayload`。
    pub now_ms: u64,
}

/// Reason the predictor gate could not decide. Caller falls through to the
/// JS shrinkage gate and typically emits a counter under the same name.
/// predictor gate 無法決斷的原因；caller 回退 JS shrinkage，通常以同名 metric 計數。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FallbackReason {
    /// Missing/incomplete expected or actual artifact identity.
    UnboundModel,
    /// Engine, strategy, model IDs or consumed artifact bytes differ.
    ModelIdentityMismatch,
    /// One or more features out of invariant #12 range or NaN/Inf.
    /// 一個或多個 feature 越界或 NaN/Inf（違反不變量 #12）。
    FeatureOutOfRange,
    /// No model loaded for this strategy (Stage 0 default state).
    /// 此策略無模型載入（Stage 0 預設）。
    NoModel,
    /// Schema / definition hash mismatch — model expects a different feature set.
    /// Schema / definition hash 不匹配。
    SchemaMismatch,
    /// Predictor is older than `model_max_age_seconds` (invariant #11).
    /// 模型早於 `model_max_age_seconds`（不變量 #11）。
    ModelStale,
    /// Runtime inference error (NaN output, ONNX backend fault, etc).
    /// 推理運行時錯誤（NaN 輸出 / ONNX backend 故障等）。
    InferenceError,
    /// Post-rearrangement prediction still invalid (e.g. NaN input).
    /// 重排後 prediction 仍無效（例如 NaN 輸入）。
    QuantileCrossingFatal,
}

impl FallbackReason {
    /// Canonical metric name — matches spec §10.1 counters.
    /// 對應 §10.1 metric 名稱。
    pub fn metric_name(&self) -> &'static str {
        match self {
            Self::UnboundModel => "predict_model_unbound",
            Self::ModelIdentityMismatch => "predict_model_identity_mismatch",
            Self::FeatureOutOfRange => "feature_out_of_range",
            Self::NoModel => "predict_no_model",
            Self::SchemaMismatch => "predict_schema_error",
            Self::ModelStale => "model_stale",
            Self::InferenceError => "predict_errors",
            Self::QuantileCrossingFatal => "quantile_crossing_fatal",
        }
    }
}

/// Payload the caller forwards into `PipelineCommand::EmitShadowFill`.
/// Kept separate from the IPC variant so this module stays IPC-agnostic and
/// so the caller can add emission-site metadata without touching the gate.
/// caller 轉發到 `PipelineCommand::EmitShadowFill` 的負載；與 IPC 變體解耦，使
/// 本模組無 IPC 依賴，且 caller 可在發送站點加 metadata 而不動 gate。
#[derive(Debug, Clone)]
pub struct ShadowFillPayload {
    pub context_id: String,
    pub strategy: String,
    pub symbol: String,
    /// +1 long / -1 short — pulled from `FeatureVectorV1::side`. Carried
    /// as a typed field (not re-parsed from JSONB) so the writer can bind
    /// directly into the SMALLINT column without JSON round-tripping.
    /// +1 多 / -1 空，取自 `FeatureVectorV1::side`；typed 攜帶避免 writer
    /// 從 JSONB 再解析，直接 bind SMALLINT 即可。
    pub side: i8,
    pub features_jsonb: String,
    pub prediction_q10: f32,
    pub prediction_q50: f32,
    pub prediction_q90: f32,
    pub cost_bps: f64,
    pub ts_ms: u64,
}

/// Outcome of a single predictor-gate evaluation.
/// 單次預測器 gate 評估結果。
#[derive(Debug, Clone)]
pub enum PredictorGateOutcome {
    /// Safety margin ≥ cost; intent may proceed.
    /// 安全 margin ≥ 成本；意圖放行。
    Accept,
    /// Safety margin < cost; hard reject (first-entry case).
    /// 安全 margin < 成本；一般拒絕（首次進場）。
    Reject(String),
    /// q10 < 0 with `require_q10_positive_for_adds=true`; reject add-only.
    /// q10 < 0 且配置要求 q10 非負方可加倉；僅拒絕加倉。
    RejectAdd(String),
    /// ε-greedy exploration fired (paper only); caller must emit the shadow
    /// fill IPC and still treat the intent as rejected for execution.
    /// ε-greedy 探索觸發（僅 paper）；caller 需派發 shadow-fill IPC 並視意圖為拒絕。
    ShadowFill(ShadowFillPayload),
    /// Predictor cannot decide; caller falls through to the JS shrinkage gate.
    /// Pair the reason with `FallbackReason::metric_name()` for counters.
    /// 預測器無法決斷；caller 回退 JS shrinkage。以 metric_name 記數。
    Fallback(FallbackReason),
}

/// Round-trip cost in bps: `(fee_rate + slippage) × 2 legs × 10_000`.
/// Helper kept here so the gate and caller share an identical definition.
/// 來回成本 bps；與 caller 共享單一定義，避免分歧。
pub fn estimate_round_trip_cost_bps(fee_rate: f64, slippage: f64) -> f64 {
    2.0 * (fee_rate + slippage) * 10_000.0
}

/// §7.3 predictor gate — pure. Caller handles Fallback / ShadowFill side-effects.
/// §7.3 純預測器 gate；Fallback / ShadowFill 的副作用由 caller 處理。
pub fn edge_predictor_gate(
    inputs: &GateInputs<'_>,
    features: &FeatureVectorV1,
    store: &EdgePredictorStore,
    rng: &mut SmallRng,
    cfg: &EdgePredictorCfg,
    features_jsonb_for_shadow: impl FnOnce() -> String,
) -> PredictorGateOutcome {
    // Step 1 · invariant #12 feature sanity (no predictor needed).
    // 步驟 1 · 不變量 #12 feature 完整性檢查。
    if !features.all_in_range() {
        return PredictorGateOutcome::Fallback(FallbackReason::FeatureOutOfRange);
    }

    // Step 2 · load predictor (F9 discipline internal to EdgePredictorStore).
    // 步驟 2 · 載入 predictor（F9 discipline 已封裝於 store）。
    let predictor = match store.load_for(inputs.strategy) {
        Some(p) => p,
        None => return PredictorGateOutcome::Fallback(FallbackReason::NoModel),
    };

    let actual_binding = predictor.artifact_binding();
    if let Some(actual) = &actual_binding {
        let expected = match &inputs.expected_binding {
            Some(expected) if expected.is_complete() && actual.is_complete() => expected,
            _ => return PredictorGateOutcome::Fallback(FallbackReason::UnboundModel),
        };
        if actual.engine_mode != inputs.engine_kind.db_mode()
            || actual.strategy_name != inputs.strategy
            || actual != expected
            || predictor.model_id() != actual.model_ids[1]
        {
            return PredictorGateOutcome::Fallback(FallbackReason::ModelIdentityMismatch);
        }
    }

    // An unidentified successful backend has no model contribution, even when
    // stale. Cache errors once so NoModel/error fallback and stale precedence
    // stay intact without invoking inference twice.
    let unidentified_error = if actual_binding.is_none() {
        match predictor.predict(features) {
            Ok(_) => return PredictorGateOutcome::Fallback(FallbackReason::UnboundModel),
            Err(error) => Some(error),
        }
    } else {
        None
    };

    // Step 3 · invariant #11 staleness.
    // 步驟 3 · 不變量 #11 模型陳舊檢查。
    if predictor.age_seconds() > cfg.model_max_age_seconds {
        return PredictorGateOutcome::Fallback(FallbackReason::ModelStale);
    }

    // Step 4 · inference.
    // 步驟 4 · 推理。
    let prediction = match unidentified_error {
        Some(error) => Err(error),
        None => predictor.predict(features),
    };
    let pred = match prediction {
        Ok(p) => p,
        Err(PredictError::NoModel) => {
            return PredictorGateOutcome::Fallback(FallbackReason::NoModel)
        }
        Err(PredictError::SchemaHashMismatch { .. })
        | Err(PredictError::DefinitionHashMismatch { .. }) => {
            return PredictorGateOutcome::Fallback(FallbackReason::SchemaMismatch)
        }
        Err(PredictError::InferenceFailed(_)) => {
            return PredictorGateOutcome::Fallback(FallbackReason::InferenceError)
        }
    };

    // Validate successful backend output against the authoritative contract.
    // Keep errors (including NullPredictor's NoModel) on their existing path;
    // a backend returning Ok must not decide using drifted names/definitions.
    if predictor.schema_hash() != super::features::feature_schema_hash()
        || predictor.definition_hash() != super::features::feature_definition_hash()
    {
        return PredictorGateOutcome::Fallback(FallbackReason::SchemaMismatch);
    }

    // Step 5 · C1 monotone rearrangement (idempotent sort).
    // 步驟 5 · C1 單調重排（冪等 sort）。
    let pred = enforce_monotone(pred);
    if !pred.is_valid() {
        return PredictorGateOutcome::Fallback(FallbackReason::QuantileCrossingFatal);
    }

    // Step 6 · cost gate.
    // safety_margin = q50 − k · (q50 − q10); default k=0.5.
    // 步驟 6 · 成本門；safety_margin = q50 − k·(q50 − q10)。
    let k = cfg.quantile_safety_k as f32;
    let safety_margin = pred.q50 - k * (pred.q50 - pred.q10);
    let cost_bps_f32 = inputs.cost_bps as f32;

    if safety_margin < cost_bps_f32 {
        // Step 7 · C13 ε-greedy (paper only). Non-paper engines always reject
        // to avoid polluting demo/live with exploration noise.
        // 步驟 7 · C13 ε-greedy（僅 paper）；其它引擎直接拒絕避免污染 demo/live。
        let is_paper = matches!(inputs.engine_kind, PipelineKind::Paper);
        if is_paper && cfg.exploration_rate > 0.0 && rng.gen_bool(cfg.exploration_rate) {
            return PredictorGateOutcome::ShadowFill(ShadowFillPayload {
                context_id: inputs.context_id.to_string(),
                strategy: inputs.strategy.to_string(),
                symbol: inputs.symbol.to_string(),
                side: features.side,
                features_jsonb: features_jsonb_for_shadow(),
                prediction_q10: pred.q10,
                prediction_q50: pred.q50,
                prediction_q90: pred.q90,
                cost_bps: inputs.cost_bps,
                ts_ms: inputs.now_ms,
            });
        }
        return PredictorGateOutcome::Reject(format!(
            "predictor_cost_margin_insufficient: safety_margin={:.2}bps < cost={:.2}bps \
             (q10={:.2}, q50={:.2}, q90={:.2}, k={:.2})",
            safety_margin, cost_bps_f32, pred.q10, pred.q50, pred.q90, cfg.quantile_safety_k,
        ));
    }

    // Step 8 · q10-positive check for add-to-existing intents.
    // 步驟 8 · 加倉意圖的 q10-非負檢查。
    if inputs.is_add_to_existing && cfg.require_q10_positive_for_adds && pred.q10 < 0.0 {
        return PredictorGateOutcome::RejectAdd(format!(
            "q10_negative_on_add: q10={:.2}bps",
            pred.q10,
        ));
    }

    PredictorGateOutcome::Accept
}

/// Per-engine RNG seed — §7.3 F9 prescribes `engine_startup_nanos ^
/// engine_kind_discriminant`. Non-crypto; hot path avoids OsRng syscalls.
/// 依 §7.3 F9：startup_nanos ^ kind_discriminant；非 crypto；避免 OsRng。
pub fn seed_for_engine(startup_instant_nanos: u128, kind: PipelineKind) -> u64 {
    let discr = match kind {
        PipelineKind::Paper => 0xA1u64,
        PipelineKind::Demo => 0xB2u64,
        PipelineKind::Live => 0xC3u64,
    };
    (startup_instant_nanos as u64).wrapping_mul(0x9E3779B97F4A7C15) ^ discr
}

// ============================================================
// Tests
// ============================================================
#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::risk_config::{EdgePredictor as Cfg, EdgePredictorFallback};
    use crate::edge_predictor::{
        features::FeatureVectorV1, null_backend::NullPredictor, EdgePredictor, EdgePredictorStore,
        Prediction,
    };
    use rand::SeedableRng;
    use std::sync::Arc;

    #[test]
    fn test_d1_advisory_action_serialization_contract() {
        let legacy: AdvisoryAction = serde_json::from_str(r#"{"action":"ALLOW"}"#).unwrap();
        assert_eq!(legacy, AdvisoryAction::NoOp);
        assert_eq!(
            serde_json::to_string(&legacy).unwrap(),
            r#"{"action":"NO_OP"}"#
        );
        for invalid in [
            r#"{"action":"BUY"}"#,
            r#"{"action":"SIZE_DOWN","reason":"missing cap"}"#,
            r#"{"action":"SIZE_DOWN","max_quantity":0.001,"reason":"cap","symbol":"OTHER"}"#,
            r#"{"action":"SIZE_DOWN","max_quantity":null,"reason":"invalid"}"#,
        ] {
            assert!(
                serde_json::from_str::<AdvisoryAction>(invalid).is_err(),
                "{invalid}"
            );
        }
    }

    #[test]
    fn test_d1_advisory_caps_and_invalid_values() {
        let baseline = AdvisoryDecision {
            allowed: true,
            quantity: 0.001,
            reason: Some("baseline_reason".into()),
        };
        let entry = AdvisoryPositionEffect::RiskIncreasingEntry;
        assert_eq!(
            apply_advisory_action(baseline.clone(), &AdvisoryAction::NoOp, entry, true),
            baseline
        );
        assert_eq!(
            apply_advisory_action(
                baseline.clone(),
                &AdvisoryAction::Veto {
                    reason: "model_veto".into()
                },
                entry,
                true
            ),
            AdvisoryDecision {
                allowed: false,
                quantity: 0.0,
                reason: Some("model_veto".into())
            }
        );
        for cap in [0.001, 10.0, f64::MAX] {
            let action = AdvisoryAction::SizeDown {
                max_quantity: cap,
                reason: "cap".into(),
            };
            assert_eq!(
                apply_advisory_action(baseline.clone(), &action, entry, true),
                baseline
            );
        }
        let zero = AdvisoryAction::SizeDown {
            max_quantity: 0.0,
            reason: "zero_cap".into(),
        };
        assert_eq!(
            apply_advisory_action(baseline.clone(), &zero, entry, true),
            AdvisoryDecision {
                allowed: false,
                quantity: 0.0,
                reason: Some("zero_cap".into())
            }
        );
        for cap in [-0.1, f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
            let action = AdvisoryAction::SizeDown {
                max_quantity: cap,
                reason: "untrusted".into(),
            };
            assert_eq!(
                apply_advisory_action(baseline.clone(), &action, entry, true),
                AdvisoryDecision {
                    allowed: false,
                    quantity: 0.0,
                    reason: Some("predictor_size_down_invalid_quantity".into())
                }
            );
        }
        for quantity in [0.0, -0.001, f64::NAN, f64::INFINITY] {
            let invalid_baseline = AdvisoryDecision {
                quantity,
                ..baseline.clone()
            };
            assert_eq!(
                apply_advisory_action(invalid_baseline, &zero, entry, true),
                AdvisoryDecision {
                    allowed: false,
                    quantity: 0.0,
                    reason: Some("predictor_size_down_invalid_baseline_quantity".into())
                }
            );
        }
    }

    #[test]
    fn test_d1_advisory_bypasses_unknown_identity_and_risk_reduction() {
        let baseline = AdvisoryDecision {
            allowed: true,
            quantity: 0.001,
            reason: None,
        };
        let actions = [
            AdvisoryAction::NoOp,
            AdvisoryAction::Veto {
                reason: "must_not_block_protection".into(),
            },
            AdvisoryAction::SizeDown {
                max_quantity: 0.0001,
                reason: "must_not_shrink_protection".into(),
            },
            AdvisoryAction::SizeDown {
                max_quantity: f64::NAN,
                reason: "invalid_but_bypassed".into(),
            },
        ];
        for action in actions {
            for effect in [
                AdvisoryPositionEffect::RiskReduction,
                AdvisoryPositionEffect::Unknown,
            ] {
                assert_eq!(
                    apply_advisory_action(baseline.clone(), &action, effect, true),
                    baseline
                );
            }
            assert_eq!(
                apply_advisory_action(
                    baseline.clone(),
                    &action,
                    AdvisoryPositionEffect::RiskIncreasingEntry,
                    false
                ),
                baseline
            );
            let denied = AdvisoryDecision {
                allowed: false,
                quantity: 0.0,
                reason: Some("superior_gate_deny".into()),
            };
            assert_eq!(
                apply_advisory_action(
                    denied.clone(),
                    &action,
                    AdvisoryPositionEffect::RiskIncreasingEntry,
                    true
                ),
                denied
            );
        }
    }

    fn make_features() -> FeatureVectorV1 {
        // all-zero feature vector is in-range for FeatureVectorV1::zeroed().
        FeatureVectorV1::zeroed()
    }

    fn make_inputs<'a>(
        kind: PipelineKind,
        strategy: &'a str,
        cost_bps: f64,
        is_add: bool,
    ) -> GateInputs<'a> {
        GateInputs {
            expected_binding: Some(super::super::test_artifact_binding(
                kind.db_mode(),
                strategy,
            )),
            engine_kind: kind,
            strategy,
            symbol: "BTCUSDT",
            context_id: "ctx-test",
            cost_bps,
            is_add_to_existing: is_add,
            now_ms: 1_700_000_000_000,
        }
    }

    #[test]
    fn test_fallback_feature_out_of_range() {
        let mut f = make_features();
        f.basis_bps = f32::NAN;
        let store = EdgePredictorStore::new();
        let mut rng = SmallRng::seed_from_u64(0);
        let cfg = Cfg::default();
        let out = edge_predictor_gate(
            &make_inputs(PipelineKind::Paper, "ma_crossover", 5.0, false),
            &f,
            &store,
            &mut rng,
            &cfg,
            || "{}".into(),
        );
        assert!(matches!(
            out,
            PredictorGateOutcome::Fallback(FallbackReason::FeatureOutOfRange)
        ));
    }

    #[test]
    fn test_fallback_no_model() {
        // Store registered but no predictor swapped in yet.
        let store = EdgePredictorStore::new();
        let mut rng = SmallRng::seed_from_u64(0);
        let cfg = Cfg::default();
        let out = edge_predictor_gate(
            &make_inputs(PipelineKind::Paper, "ma_crossover", 5.0, false),
            &make_features(),
            &store,
            &mut rng,
            &cfg,
            || "{}".into(),
        );
        assert!(matches!(
            out,
            PredictorGateOutcome::Fallback(FallbackReason::NoModel)
        ));
    }

    /// NullPredictor always returns `Err(NoModel)` so the gate folds it to
    /// FallbackReason::NoModel. Confirms predict-error plumbing.
    /// NullPredictor 永返 NoModel；驗證 predict-error 連線。
    #[test]
    fn test_fallback_null_predictor_maps_to_no_model() {
        let store = EdgePredictorStore::new();
        store.swap("ma_crossover", Arc::new(NullPredictor::new()));
        let mut rng = SmallRng::seed_from_u64(0);
        let cfg = Cfg::default();
        let out = edge_predictor_gate(
            &make_inputs(PipelineKind::Paper, "ma_crossover", 5.0, false),
            &make_features(),
            &store,
            &mut rng,
            &cfg,
            || "{}".into(),
        );
        assert!(matches!(
            out,
            PredictorGateOutcome::Fallback(FallbackReason::NoModel)
        ));
    }

    // Stub predictor returning a fixed Prediction — lets us test all the
    // post-inference branches without a real model.
    // 固定 Prediction 的 stub，測試 inference 後各分支無需真實模型。
    struct StubPredictor {
        binding: PredictorArtifactBinding,
        pred: Prediction,
        age_secs: u64,
    }

    impl EdgePredictor for StubPredictor {
        fn artifact_binding(&self) -> Option<PredictorArtifactBinding> {
            Some(self.binding.clone())
        }
        fn predict(&self, _f: &FeatureVectorV1) -> Result<Prediction, PredictError> {
            Ok(self.pred)
        }
        fn age_seconds(&self) -> u64 {
            self.age_secs
        }
        fn schema_hash(&self) -> &str {
            super::super::features::feature_schema_hash()
        }
        fn definition_hash(&self) -> &str {
            super::super::features::feature_definition_hash()
        }
        fn model_id(&self) -> &str {
            "stub"
        }
    }

    fn stubbed(store: &EdgePredictorStore, strategy: &str, pred: Prediction, age_secs: u64) {
        stubbed_for_engine(store, strategy, pred, age_secs, PipelineKind::Paper);
    }

    fn stubbed_for_engine(
        store: &EdgePredictorStore,
        strategy: &str,
        pred: Prediction,
        age_secs: u64,
        kind: PipelineKind,
    ) {
        store.swap(
            strategy,
            Arc::new(StubPredictor {
                pred,
                age_secs,
                binding: super::super::test_artifact_binding(kind.db_mode(), strategy),
            }),
        );
    }

    struct ContractMismatchPredictor(bool);

    impl EdgePredictor for ContractMismatchPredictor {
        fn artifact_binding(&self) -> Option<PredictorArtifactBinding> {
            Some(super::super::test_artifact_binding("demo", "ma_crossover"))
        }
        fn predict(&self, _: &FeatureVectorV1) -> Result<Prediction, PredictError> {
            Ok(Prediction {
                q10: 100.0,
                q50: 200.0,
                q90: 300.0,
            })
        }
        fn age_seconds(&self) -> u64 {
            0
        }
        fn schema_hash(&self) -> &str {
            if self.0 {
                "wrong-feature-order"
            } else {
                super::super::features::feature_schema_hash()
            }
        }
        fn definition_hash(&self) -> &str {
            if self.0 {
                super::super::features::feature_definition_hash()
            } else {
                "wrong-definition"
            }
        }
        fn model_id(&self) -> &str {
            "stub"
        }
    }

    #[test]
    fn test_d1_pure_gate_rejects_backend_contract_mismatch() {
        for wrong_schema in [true, false] {
            let store = EdgePredictorStore::new();
            store.swap(
                "ma_crossover",
                Arc::new(ContractMismatchPredictor(wrong_schema)),
            );
            let out = edge_predictor_gate(
                &make_inputs(PipelineKind::Demo, "ma_crossover", 20.0, false),
                &make_features(),
                &store,
                &mut SmallRng::seed_from_u64(0),
                &Cfg::default(),
                || "{}".into(),
            );
            assert!(
                matches!(
                    out,
                    PredictorGateOutcome::Fallback(FallbackReason::SchemaMismatch)
                ),
                "schema/definition drift cannot become Accept: {:?}",
                out
            );
        }
    }

    #[test]
    fn test_fallback_stale_model() {
        let store = EdgePredictorStore::new();
        stubbed(
            &store,
            "ma_crossover",
            Prediction {
                q10: 1.0,
                q50: 5.0,
                q90: 10.0,
            },
            Cfg::default().model_max_age_seconds + 1,
        );
        let mut rng = SmallRng::seed_from_u64(0);
        let cfg = Cfg::default();
        let out = edge_predictor_gate(
            &make_inputs(PipelineKind::Paper, "ma_crossover", 2.0, false),
            &make_features(),
            &store,
            &mut rng,
            &cfg,
            || "{}".into(),
        );
        assert!(matches!(
            out,
            PredictorGateOutcome::Fallback(FallbackReason::ModelStale)
        ));
    }

    #[test]
    fn test_accept_when_margin_above_cost() {
        // q50=10, q10=2 → safety=10-0.5*(10-2)=6 > cost=3 → Accept.
        // q50=10, q10=2 → safety=6 > cost=3 → 放行。
        let store = EdgePredictorStore::new();
        stubbed(
            &store,
            "ma_crossover",
            Prediction {
                q10: 2.0,
                q50: 10.0,
                q90: 15.0,
            },
            0,
        );
        let mut rng = SmallRng::seed_from_u64(0);
        let cfg = Cfg::default();
        let out = edge_predictor_gate(
            &make_inputs(PipelineKind::Paper, "ma_crossover", 3.0, false),
            &make_features(),
            &store,
            &mut rng,
            &cfg,
            || "{}".into(),
        );
        assert!(matches!(out, PredictorGateOutcome::Accept));
    }

    #[test]
    fn test_reject_non_paper_no_shadow_even_at_full_exploration() {
        // exploration_rate=0.2 (max), but engine=Demo → must be Reject, not ShadowFill.
        // Demo/live 不走探索分支，即使 exploration_rate 拉滿也必須拒絕。
        let store = EdgePredictorStore::new();
        stubbed_for_engine(
            &store,
            "ma_crossover",
            Prediction {
                q10: -5.0,
                q50: -1.0,
                q90: 2.0,
            },
            0,
            PipelineKind::Demo,
        );
        let mut rng = SmallRng::seed_from_u64(0);
        let mut cfg = Cfg::default();
        cfg.exploration_rate = 0.2;
        let out = edge_predictor_gate(
            &make_inputs(PipelineKind::Demo, "ma_crossover", 10.0, false),
            &make_features(),
            &store,
            &mut rng,
            &cfg,
            || "{}".into(),
        );
        assert!(matches!(out, PredictorGateOutcome::Reject(_)));
    }

    #[test]
    fn test_paper_shadow_fill_fires_with_forced_rng() {
        // Seed chosen so gen_bool(1.0) → true regardless; we use rate=1.0 to
        // force the branch without relying on RNG internals.
        // 用 exploration_rate=1.0 強制進入探索分支，繞開 RNG 細節。
        let store = EdgePredictorStore::new();
        stubbed(
            &store,
            "ma_crossover",
            Prediction {
                q10: -5.0,
                q50: -1.0,
                q90: 2.0,
            },
            0,
        );
        let mut rng = SmallRng::seed_from_u64(42);
        let mut cfg = Cfg::default();
        cfg.exploration_rate = 1.0;
        let out = edge_predictor_gate(
            &make_inputs(PipelineKind::Paper, "ma_crossover", 10.0, false),
            &make_features(),
            &store,
            &mut rng,
            &cfg,
            || r#"{"ok":true}"#.into(),
        );
        match out {
            PredictorGateOutcome::ShadowFill(p) => {
                assert_eq!(p.strategy, "ma_crossover");
                assert_eq!(p.symbol, "BTCUSDT");
                assert_eq!(p.context_id, "ctx-test");
                assert_eq!(p.features_jsonb, r#"{"ok":true}"#);
                assert_eq!(p.prediction_q50, -1.0);
                assert!((p.cost_bps - 10.0).abs() < 1e-9);
            }
            other => panic!("expected ShadowFill, got {:?}", other),
        }
    }

    #[test]
    fn test_paper_reject_when_exploration_rate_zero() {
        let store = EdgePredictorStore::new();
        stubbed(
            &store,
            "ma_crossover",
            Prediction {
                q10: -5.0,
                q50: -1.0,
                q90: 2.0,
            },
            0,
        );
        let mut rng = SmallRng::seed_from_u64(7);
        let mut cfg = Cfg::default();
        cfg.exploration_rate = 0.0;
        let out = edge_predictor_gate(
            &make_inputs(PipelineKind::Paper, "ma_crossover", 10.0, false),
            &make_features(),
            &store,
            &mut rng,
            &cfg,
            || "{}".into(),
        );
        assert!(matches!(out, PredictorGateOutcome::Reject(_)));
    }

    #[test]
    fn test_reject_add_on_negative_q10() {
        // Margin passes (cost tiny), but q10 < 0 + is_add + require_q10_positive_for_adds → RejectAdd.
        // margin 過關但 q10 負且為加倉且 require_q10_positive_for_adds → 拒絕加倉。
        let store = EdgePredictorStore::new();
        stubbed(
            &store,
            "ma_crossover",
            Prediction {
                q10: -0.5,
                q50: 5.0,
                q90: 10.0,
            },
            0,
        );
        let mut rng = SmallRng::seed_from_u64(0);
        let cfg = Cfg::default();
        let out = edge_predictor_gate(
            &make_inputs(
                PipelineKind::Paper,
                "ma_crossover",
                0.1,
                /*is_add=*/ true,
            ),
            &make_features(),
            &store,
            &mut rng,
            &cfg,
            || "{}".into(),
        );
        assert!(matches!(out, PredictorGateOutcome::RejectAdd(_)));
    }

    #[test]
    fn test_accept_on_negative_q10_when_not_add() {
        // Same fixture but is_add=false → the q10-positive check shouldn't fire.
        // 相同 fixture 但 is_add=false → q10-非負檢查不應觸發。
        let store = EdgePredictorStore::new();
        stubbed(
            &store,
            "ma_crossover",
            Prediction {
                q10: -0.5,
                q50: 5.0,
                q90: 10.0,
            },
            0,
        );
        let mut rng = SmallRng::seed_from_u64(0);
        let cfg = Cfg::default();
        let out = edge_predictor_gate(
            &make_inputs(
                PipelineKind::Paper,
                "ma_crossover",
                0.1,
                /*is_add=*/ false,
            ),
            &make_features(),
            &store,
            &mut rng,
            &cfg,
            || "{}".into(),
        );
        assert!(matches!(out, PredictorGateOutcome::Accept));
    }

    #[test]
    fn test_accept_on_negative_q10_when_require_flag_off() {
        // is_add=true but require_q10_positive_for_adds=false → Accept.
        let store = EdgePredictorStore::new();
        stubbed(
            &store,
            "ma_crossover",
            Prediction {
                q10: -0.5,
                q50: 5.0,
                q90: 10.0,
            },
            0,
        );
        let mut rng = SmallRng::seed_from_u64(0);
        let mut cfg = Cfg::default();
        cfg.require_q10_positive_for_adds = false;
        let out = edge_predictor_gate(
            &make_inputs(PipelineKind::Paper, "ma_crossover", 0.1, true),
            &make_features(),
            &store,
            &mut rng,
            &cfg,
            || "{}".into(),
        );
        assert!(matches!(out, PredictorGateOutcome::Accept));
    }

    #[test]
    fn test_successful_unidentified_backend_cannot_veto() {
        struct Unknown;
        impl EdgePredictor for Unknown {
            fn predict(&self, _: &FeatureVectorV1) -> Result<Prediction, PredictError> {
                Ok(Prediction {
                    q10: -100.0,
                    q50: -50.0,
                    q90: -10.0,
                })
            }
            fn age_seconds(&self) -> u64 {
                0
            }
            fn schema_hash(&self) -> &str {
                super::super::features::feature_schema_hash()
            }
            fn definition_hash(&self) -> &str {
                super::super::features::feature_definition_hash()
            }
            fn model_id(&self) -> &str {
                "unknown"
            }
        }
        let store = EdgePredictorStore::new();
        store.swap("ma_crossover", Arc::new(Unknown));
        let out = edge_predictor_gate(
            &make_inputs(PipelineKind::Paper, "ma_crossover", 20.0, false),
            &make_features(),
            &store,
            &mut SmallRng::seed_from_u64(0),
            &Cfg::default(),
            || "{}".into(),
        );
        assert!(matches!(
            out,
            PredictorGateOutcome::Fallback(FallbackReason::UnboundModel)
        ));
    }

    struct D1UnidentifiedPredictor {
        result: Result<Prediction, PredictError>,
        age: u64,
        calls: Arc<std::sync::atomic::AtomicUsize>,
    }

    impl EdgePredictor for D1UnidentifiedPredictor {
        fn predict(&self, _: &FeatureVectorV1) -> Result<Prediction, PredictError> {
            self.calls.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
            self.result.clone()
        }
        fn age_seconds(&self) -> u64 {
            self.age
        }
        fn schema_hash(&self) -> &str {
            super::super::features::feature_schema_hash()
        }
        fn definition_hash(&self) -> &str {
            super::super::features::feature_definition_hash()
        }
        fn model_id(&self) -> &str {
            "unidentified-test-backend"
        }
    }

    #[test]
    fn test_d1_unidentified_stale_success_is_no_op() {
        for age in [0, 11] {
            let calls = Arc::new(std::sync::atomic::AtomicUsize::new(0));
            let store = EdgePredictorStore::new();
            store.swap(
                "ma_crossover",
                Arc::new(D1UnidentifiedPredictor {
                    result: Ok(Prediction {
                        q10: -100.0,
                        q50: -50.0,
                        q90: -10.0,
                    }),
                    age,
                    calls: calls.clone(),
                }),
            );
            let cfg = Cfg {
                model_max_age_seconds: 10,
                ..Default::default()
            };
            let out = edge_predictor_gate(
                &make_inputs(PipelineKind::Paper, "ma_crossover", 20.0, false),
                &make_features(),
                &store,
                &mut SmallRng::seed_from_u64(51),
                &cfg,
                || "{}".into(),
            );
            eprintln!("D1_UNKNOWN_STALE_GATE age={age} expected=UnboundModel actual={out:?}");
            assert!(matches!(
                out,
                PredictorGateOutcome::Fallback(FallbackReason::UnboundModel)
            ));
            assert_eq!(calls.load(std::sync::atomic::Ordering::SeqCst), 1);
        }
    }

    #[test]
    fn test_d1_unidentified_errors_keep_existing_fallbacks() {
        for (error, fresh_reason) in [
            (PredictError::NoModel, FallbackReason::NoModel),
            (
                PredictError::InferenceFailed("fixture fault".into()),
                FallbackReason::InferenceError,
            ),
            (
                PredictError::SchemaHashMismatch {
                    expected: "expected".into(),
                    got: "wrong".into(),
                },
                FallbackReason::SchemaMismatch,
            ),
            (
                PredictError::DefinitionHashMismatch {
                    expected: "expected".into(),
                    got: "wrong".into(),
                },
                FallbackReason::SchemaMismatch,
            ),
        ] {
            for age in [0, 11] {
                let store = EdgePredictorStore::new();
                let calls = Arc::new(std::sync::atomic::AtomicUsize::new(0));
                store.swap(
                    "ma_crossover",
                    Arc::new(D1UnidentifiedPredictor {
                        result: Err(error.clone()),
                        age,
                        calls: calls.clone(),
                    }),
                );
                let cfg = Cfg {
                    model_max_age_seconds: 10,
                    ..Default::default()
                };
                let out = edge_predictor_gate(
                    &make_inputs(PipelineKind::Paper, "ma_crossover", 20.0, false),
                    &make_features(),
                    &store,
                    &mut SmallRng::seed_from_u64(51),
                    &cfg,
                    || "{}".into(),
                );
                let expected = if age == 0 {
                    fresh_reason
                } else {
                    FallbackReason::ModelStale
                };
                assert!(
                    matches!(out, PredictorGateOutcome::Fallback(reason) if reason == expected)
                );
                assert!(calls.load(std::sync::atomic::Ordering::SeqCst) <= 1);
            }
        }
    }

    #[test]
    fn test_fallback_reason_metric_names_stable() {
        // Metric names land in §10.1 — any accidental rename will be caught here.
        // 對應 §10.1 metric 名稱，誤改名會在此失敗。
        assert_eq!(
            FallbackReason::FeatureOutOfRange.metric_name(),
            "feature_out_of_range"
        );
        assert_eq!(FallbackReason::NoModel.metric_name(), "predict_no_model");
        assert_eq!(
            FallbackReason::SchemaMismatch.metric_name(),
            "predict_schema_error"
        );
        assert_eq!(FallbackReason::ModelStale.metric_name(), "model_stale");
        assert_eq!(
            FallbackReason::InferenceError.metric_name(),
            "predict_errors"
        );
        assert_eq!(
            FallbackReason::QuantileCrossingFatal.metric_name(),
            "quantile_crossing_fatal"
        );
    }

    #[test]
    fn test_estimate_round_trip_cost_matches_intent_processor() {
        // Sanity: 5.5bps fee + 5bps slip → (0.00055+0.0005)*2*1e4 = 21bps.
        // 健全性檢查：與 intent_processor 計算一致。
        let bps = estimate_round_trip_cost_bps(0.000_55, 0.000_5);
        assert!((bps - 21.0).abs() < 1e-6, "got {}", bps);
    }

    #[test]
    fn test_seed_for_engine_is_deterministic_per_kind() {
        let s_paper = seed_for_engine(123_456_789, PipelineKind::Paper);
        let s_demo = seed_for_engine(123_456_789, PipelineKind::Demo);
        let s_live = seed_for_engine(123_456_789, PipelineKind::Live);
        // All three distinct for the same startup instant.
        // 同一啟動時刻下三 kind 種子互異。
        assert_ne!(s_paper, s_demo);
        assert_ne!(s_demo, s_live);
        assert_ne!(s_paper, s_live);
        // Stable across calls.
        // 多次呼叫穩定。
        assert_eq!(s_paper, seed_for_engine(123_456_789, PipelineKind::Paper));
    }

    #[test]
    fn test_fallback_config_enum_default() {
        // Sanity: RiskConfig default uses Shrinkage fallback (spec v1.4).
        assert_eq!(
            Cfg::default().fallback_on_error,
            EdgePredictorFallback::Shrinkage
        );
    }
}
