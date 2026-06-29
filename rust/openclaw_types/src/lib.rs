//! OpenClaw Type Definitions
//! OpenClaw 類型定義
//!
//! Unified type system for the OpenClaw trading engine.
//! Covers price events, trade intents, agent protocol, governance states,
//! risk control, cognitive parameters, and engine configuration.

pub mod agent;
pub mod asset_venue;
pub mod cognitive;
pub mod ibkr_feature_flag_secret_auth;
pub mod ibkr_paper_lifecycle;
pub mod ibkr_phase2_artifact;
pub mod ibkr_phase2_gate;
pub mod ibkr_phase2_policies;
pub mod ibkr_phase2_runtime;
pub mod intent;
pub mod price;
pub mod risk;
pub mod state;
pub mod stock_etf_lane;
pub mod stock_etf_phase3_evidence;
pub mod stock_etf_release_packet;
pub mod stock_etf_scorecard_inputs;
pub mod stock_etf_tiny_live_eligibility;

pub use agent::{AgentMessage, AgentRole, MessageType};
pub use asset_venue::{AssetClass, Venue, VenueParseError};
pub use cognitive::{CognitiveParams, DreamInsight, RegretSummary, SkippedOpportunity};
pub use ibkr_feature_flag_secret_auth::{
    evaluate_feature_flag_secret_auth_matrix, FeatureFlagSecretAuthBlocker,
    FeatureFlagSecretAuthMatrixV1, FeatureFlagSecretAuthVerdict, StockEtfAuthorizationEnvelopeV1,
};
pub use ibkr_paper_lifecycle::{
    classify_ibkr_paper_restart_recovery, is_transition_allowed, BrokerLifecycleEventLogV1,
    IbkrPaperLifecycleEventBlocker, IbkrPaperLifecycleEventVerdict, IbkrPaperRestartRecoveryAction,
    IbkrPaperRestartRecoveryInputV1,
};
pub use ibkr_phase2_artifact::{
    is_sha256_hex, IbkrPhase2GateArtifactBlocker, IbkrPhase2GateArtifactV1,
    IbkrPhase2GateArtifactVerdict,
};
pub use ibkr_phase2_gate::{
    classify_non_bybit_api_action, is_loopback_or_unix_local_host, IbkrApiBaseline,
    IbkrExternalSurfaceGateBlocker, IbkrExternalSurfaceGateStatus, IbkrExternalSurfaceGateV1,
    IbkrExternalSurfaceGateVerdict, IbkrGatewayMode, IbkrHostPolicy, IbkrPortPolicy,
    IbkrSecretSlotMode, IbkrSessionAttestationBlocker, IbkrSessionAttestationStatus,
    IbkrSessionAttestationV1, IbkrSessionAttestationVerdict, NonBybitApiAction,
    NonBybitApiAllowlistDecision, NonBybitApiDenialReason, IBKR_LIVE_GATEWAY_PORT,
    IBKR_LIVE_TWS_PORT, IBKR_PAPER_GATEWAY_DEFAULT_PORT, IBKR_PHASE2_ADR, IBKR_PHASE2_AMD,
};
pub use ibkr_phase2_policies::{
    IbkrAuditEventPolicyBlocker, IbkrAuditEventPolicyV1, IbkrPaperAttestationPolicyBlocker,
    IbkrPaperAttestationPolicyV1, IbkrPhase2GatePrerequisiteFlags, IbkrPhase2PolicyBundleBlocker,
    IbkrPhase2PolicyBundleV1, IbkrPolicyVerdict, IbkrPythonWriteGuardPolicyBlocker,
    IbkrPythonWriteGuardPolicyV1, IbkrRateLimitPolicyBlocker, IbkrRateLimitPolicyV1,
    IbkrRateLimitScope, IbkrRedactionPolicyBlocker, IbkrRedactionPolicyV1,
};
pub use ibkr_phase2_runtime::{
    IbkrApiSessionTopologyBlocker, IbkrApiSessionTopologyV1, IbkrApiSessionTopologyVerdict,
    IbkrGatewayProcessMode, IbkrSecretSlotContractBlocker, IbkrSecretSlotContractV1,
    IbkrSecretSlotContractVerdict, IbkrSecretSlotPosture,
};
pub use intent::{DataQualityLevel, OrderIntent, RiskVerdict, TradeIntent};
pub use price::{Kline, KlineBar, PriceEvent, PriceEventKind, OHLCV};
pub use risk::{
    H0CheckResult, H0GateConfig, H0GateHealthSnapshot, H0GateRiskSnapshot, PricingConfig,
};
pub use state::{AgentState, GovernanceMode, OmsState, OrderInitiator, RiskInitiator, RiskLevel};
pub use stock_etf_lane::{
    evaluate_broker_operation, AssetLane, AuthorityScope, Broker, BrokerCapabilityDecision,
    BrokerCapabilityRequest, BrokerEnvironment, BrokerOperation, IbkrPaperOrderLifecycleState,
    InstrumentKind, StockEtfConfigError, StockEtfContractParseError, StockEtfDenialReason,
    StockEtfFeatureFlags, StockEtfGateInputs, StockEtfReadiness,
};
pub use stock_etf_phase3_evidence::{
    StockEtfAdjustmentMarker, StockEtfDailyDqManifestV1, StockEtfEvidenceClockDayV1,
    StockEtfEvidenceClockStatus, StockEtfFrozenEvidenceInputsV1, StockEtfPhase3Blocker,
    StockEtfPhase3Verdict, StockMarketDataProvenanceV1,
};
pub use stock_etf_release_packet::{
    StockEtfKillDisableCleanupProofV1, StockEtfPgMigrationEvidenceV1,
    StockEtfReleaseManifestHashV1, StockEtfReleasePacketBlocker, StockEtfReleasePacketV1,
    StockEtfReleaseVerdict, STOCK_ETF_RELEASE_ADR_PATH, STOCK_ETF_RELEASE_AMD_PATH,
    STOCK_ETF_RELEASE_SPEC_PATH,
};
pub use stock_etf_scorecard_inputs::{
    BrokerAccountPortfolioCashLedgerV1, StockEtfBenchmarkVersionV1, StockEtfCostModelVersionV1,
    StockEtfOrderSide, StockEtfScorecardInputBlocker, StockEtfScorecardInputBundleV1,
    StockEtfScorecardInputVerdict, StockEtfStorageCapacityV1, StockShadowFillModelV1,
};
pub use stock_etf_tiny_live_eligibility::{
    TinyLiveAdrEligibilityBlocker, TinyLiveAdrEligibilityDecision, TinyLiveAdrEligibilityV1,
    TinyLiveAdrEligibilityVerdict, STOCK_ETF_TINY_LIVE_ADR_PATH, STOCK_ETF_TINY_LIVE_AMD_PATH,
    STOCK_ETF_TINY_LIVE_SPEC_PATH,
};

// ---------------------------------------------------------------------------
// Golden schema validation (CI) / 黃金基準驗證（CI 用）
// ---------------------------------------------------------------------------
#[cfg(test)]
mod schema_golden_tests {
    //! Validate Rust types against rust/schemas/shared_types.json golden file.
    //! 驗證 Rust 類型定義與黃金基準 JSON 一致。

    use super::*;
    use serde_json::Value;
    use std::collections::HashMap;

    fn load_golden() -> Value {
        let schema_path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .unwrap()
            .join("schemas")
            .join("shared_types.json");
        let content = std::fs::read_to_string(&schema_path)
            .unwrap_or_else(|e| panic!("Cannot read golden schema at {:?}: {}", schema_path, e));
        serde_json::from_str(&content).expect("Invalid JSON in golden schema")
    }

    /// Helper: serialize a default instance and return its field names + JSON types.
    /// 輔助：序列化預設實例，回傳欄位名稱及 JSON 類型。
    fn struct_fields(val: &Value) -> HashMap<String, String> {
        let obj = val.as_object().expect("Expected JSON object");
        obj.iter()
            .map(|(k, v)| {
                let t = match v {
                    Value::Bool(_) => "bool",
                    Value::Number(n) if n.is_f64() => "float",
                    Value::Number(_) => "int",
                    Value::String(_) => "string",
                    Value::Array(_) => "list_string",
                    Value::Null => "null",
                    Value::Object(_) => "object",
                };
                (k.clone(), t.to_string())
            })
            .collect()
    }

    #[test]
    fn test_h0_gate_config_matches_golden() {
        let golden = load_golden();
        let gtype = &golden["types"]["H0GateConfig"];
        assert_eq!(gtype["kind"], "struct");

        let default_json = serde_json::to_value(H0GateConfig::default()).unwrap();
        let rust_fields = struct_fields(&default_json);
        let golden_fields = gtype["fields"].as_object().unwrap();

        for (fname, _fdef) in golden_fields {
            assert!(
                rust_fields.contains_key(fname),
                "H0GateConfig: Rust missing field '{}'",
                fname
            );
        }
        for fname in rust_fields.keys() {
            assert!(
                golden_fields.contains_key(fname),
                "H0GateConfig: Rust has extra field '{}'",
                fname
            );
        }
    }

    #[test]
    fn test_h0_gate_health_snapshot_matches_golden() {
        let golden = load_golden();
        let gtype = &golden["types"]["H0GateHealthSnapshot"];
        assert_eq!(gtype["kind"], "struct");

        let default_json = serde_json::to_value(H0GateHealthSnapshot::default()).unwrap();
        let rust_fields = struct_fields(&default_json);
        let golden_fields = gtype["fields"].as_object().unwrap();

        for (fname, _) in golden_fields {
            assert!(
                rust_fields.contains_key(fname),
                "H0GateHealthSnapshot: Rust missing field '{}'",
                fname
            );
        }
    }

    #[test]
    fn test_h0_gate_risk_snapshot_matches_golden() {
        let golden = load_golden();
        let gtype = &golden["types"]["H0GateRiskSnapshot"];
        assert_eq!(gtype["kind"], "struct");

        let default_json = serde_json::to_value(H0GateRiskSnapshot::default()).unwrap();
        let rust_fields = struct_fields(&default_json);
        let golden_fields = gtype["fields"].as_object().unwrap();

        for (fname, _) in golden_fields {
            assert!(
                rust_fields.contains_key(fname),
                "H0GateRiskSnapshot: Rust missing field '{}'",
                fname
            );
        }
    }

    #[test]
    fn test_h0_check_result_matches_golden() {
        let golden = load_golden();
        let gtype = &golden["types"]["H0GateCheckResult"];
        assert_eq!(gtype["kind"], "struct");

        let result = H0CheckResult::allowed();
        let result_json = serde_json::to_value(&result).unwrap();
        let rust_fields = struct_fields(&result_json);
        let golden_fields = gtype["fields"].as_object().unwrap();

        for (fname, _) in golden_fields {
            assert!(
                rust_fields.contains_key(fname),
                "H0CheckResult: Rust missing field '{}'",
                fname
            );
        }
    }

    // ARCH-RC1 1C-1 Batch 6: StopConfig golden test removed; the type now lives
    // only in `openclaw_core::stop_manager::StopConfig`. The Python-side golden
    // schema still carries a StopConfig entry for cross-language contract purposes,
    // but the Rust-side validation no longer applies (core-crate type is not
    // reachable from openclaw_types tests due to crate dependency direction).
    // 1C-1 Batch 6：StopConfig 黃金測試移除；該型別只存在 openclaw_core::stop_manager。

    #[test]
    fn test_golden_schema_version() {
        let golden = load_golden();
        assert_eq!(golden["version"], 1, "Golden schema version must be 1");
    }
}
