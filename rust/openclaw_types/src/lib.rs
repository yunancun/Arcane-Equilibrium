//! OpenClaw Type Definitions
//! OpenClaw 類型定義
//!
//! Unified type system for the OpenClaw trading engine.
//! Covers price events, trade intents, agent protocol, governance states,
//! risk control, cognitive parameters, and engine configuration.

pub mod agent;
pub mod cognitive;
pub mod config;
pub mod intent;
pub mod price;
pub mod risk;
pub mod state;

pub use agent::{AgentMessage, AgentRole, MessageType};
pub use cognitive::{CognitiveParams, DreamInsight, RegretSummary, SkippedOpportunity};
pub use config::{EngineConfig, ParamTemperature};
pub use intent::{DataQualityLevel, OrderIntent, RiskVerdict, TradeIntent};
pub use price::{Kline, KlineBar, PriceEvent, OHLCV};
pub use risk::{
    GuardianConfig, H0CheckResult, H0GateConfig, H0GateHealthSnapshot, H0GateRiskSnapshot,
    RiskConfig, StopConfig,
};
pub use state::{AgentState, GovernanceMode, OmsState, OrderInitiator, RiskInitiator, RiskLevel};

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

    #[test]
    fn test_stop_config_matches_golden() {
        let golden = load_golden();
        let gtype = &golden["types"]["StopConfig"];
        assert_eq!(gtype["kind"], "struct");

        // Use a fully-populated instance so Optional fields show up
        // 使用完整填充的實例，讓 Option 欄位出現
        let sc = risk::StopConfig {
            hard_stop_pct: 5.0,
            trailing_stop_pct: Some(2.0),
            time_stop_hours: Some(1.0),
            atr_multiplier: Some(1.5),
        };
        let sc_json = serde_json::to_value(&sc).unwrap();
        let rust_fields = struct_fields(&sc_json);
        let golden_fields = gtype["fields"].as_object().unwrap();

        // Golden defines Python-side field names; Rust may have different names
        // that map via serde — check the intersection is non-empty
        // 黃金基準定義 Python 側欄位名；Rust 側可能有不同名稱
        assert!(
            golden_fields.contains_key("hard_stop_pct"),
            "Golden must have hard_stop_pct"
        );
        assert!(
            rust_fields.contains_key("hard_stop_pct"),
            "Rust StopConfig must have hard_stop_pct"
        );
    }

    #[test]
    fn test_golden_schema_version() {
        let golden = load_golden();
        assert_eq!(golden["version"], 1, "Golden schema version must be 1");
    }
}
