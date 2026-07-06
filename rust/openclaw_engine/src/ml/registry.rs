//! Model registry helpers — V023 registry resolver plus source-only advisory
//! serving contract validation for registry row metadata.
//! Model registry helper — 包含 V023 registry 解析器，以及 source-only 的
//! advisory serving metadata 合約驗證。
//!
//! MODULE_NOTE (EN): INFRA-PREBUILD-1 Part B (2026-04-23) originally added the
//! DB-backed resolver. WP3 adds a pure validator for registry-authorized
//! advisory serving metadata: the registry row must carry complete lineage,
//! exact q10/q50/q90 artifact hashes, advisory-only authority flags, and schema
//! parity before any caller may treat it as advisory-serving-ready. This module
//! does not load ONNX, inspect symlinks, or grant promotion/order authority.
//! `_current` filename helpers are legacy convenience only; they are never the
//! serving authority.
//!
//! MODULE_NOTE (中): INFRA-PREBUILD-1 B 部（2026-04-23）最早加入 DB-backed
//! resolver。WP3 在此新增純函式 validator：registry row 必須帶完整 lineage、
//! 精確 q10/q50/q90 artifact hashes、advisory-only 權限旗標與 schema parity，
//! caller 才能把它當作 advisory serving metadata。此模組不載入 ONNX、不檢查
//! symlink、不授予 promotion/order authority。`_current` 檔名 helper 只是
//! legacy convenience，永遠不是 serving authority。
//!
//! Spec: sql/migrations/V023__model_registry.sql · plan INFRA-PREBUILD-1 §B3.

use crate::database::pool::DbPool;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use tracing::{debug, warn};

/// Strategy / engine_mode / quantile identity for a registry lookup.
/// Registry lookup 的 strategy / engine_mode / quantile 身份。
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct ModelSlot {
    pub strategy: String,
    pub engine_mode: String,
    pub quantile: String, // "q10" | "q50" | "q90"
}

impl ModelSlot {
    pub fn new(strategy: &str, engine_mode: &str, quantile: &str) -> Self {
        Self {
            strategy: strategy.to_string(),
            engine_mode: engine_mode.to_string(),
            quantile: quantile.to_string(),
        }
    }
}

/// Resolved artifact metadata from the registry.
/// 從 registry 解析出的 artifact metadata。
#[derive(Debug, Clone, PartialEq)]
pub struct ResolvedArtifact {
    /// Registry row id — echoed back by IPC model_info for observability.
    /// Registry row id — IPC model_info 回傳供觀察。
    pub id: i64,
    /// Absolute or $OPENCLAW_DATA_DIR-relative path to the ONNX blob.
    /// ONNX blob 的絕對或相對路徑（相對於 $OPENCLAW_DATA_DIR）。
    pub artifact_path: String,
    /// "production" or "promoting" — lookup only returns these two states.
    /// "production" 或 "promoting" — lookup 僅回這兩個狀態。
    pub canary_status: String,
    /// "should_ship" or "shadow_only" — never "no_ship" (never registered).
    /// "should_ship" 或 "shadow_only" — 永不會是 "no_ship"（不登記）。
    pub verdict: String,
    /// ISO-8601 train_date string (e.g. "2026-04-23").
    pub train_date: String,
    /// Registry slot quantile ("q10" | "q50" | "q90") for artifact hash
    /// binding against advisory serving contracts.
    /// Registry slot quantile，用於與 advisory serving contract 的 artifact hash 綁定。
    pub quantile: String,
    /// Optional sha256 integrity check — caller may verify on load.
    /// 可選的 sha256 完整性檢查，caller 載入時可校驗。
    pub artifact_sha256: Option<String>,
    /// Hash of the feature schema (feature names + dtypes) used at training
    /// time. Must match the engine's runtime `FEATURE_NAMES_V1_HASH` before
    /// the artifact is loaded — mismatch means feature dim / ordering drift
    /// which would crash `session.run` at inference. `None` for legacy rows
    /// that were registered before the column was populated — caller should
    /// treat `None` as OK (warn-log) to preserve backward compat.
    ///
    /// 訓練時使用的 feature schema（feature names + dtypes）hash。載入前
    /// 必須與 engine 運行時的 `FEATURE_NAMES_V1_HASH` 比對；mismatch 表示
    /// feature dim / 排序漂移，`session.run` 會 panic。legacy row 未填寫時
    /// `None`，caller 應視為 OK（warn-log）以保相容。
    pub feature_schema_hash: Option<String>,
}

/// Advisory serving is metadata-authorized only; this literal is the only
/// accepted serving mode for the WP3 source-only contract.
/// Advisory serving 僅由 metadata 授權；WP3 合約只接受此 serving mode。
pub const REGISTRY_ADVISORY_SERVING_MODE: &str = "advisory_only";
pub const REGISTRY_SERVING_CONTRACT_SCHEMA_VERSION: &str = "registry_serving_contract_v1";
pub const PIT_DATASET_MANIFEST_SCHEMA_VERSION: &str = "pit_dataset_manifest_v1";

const REGISTRY_Q10: &str = "q10";
const REGISTRY_Q50: &str = "q50";
const REGISTRY_Q90: &str = "q90";

/// Optional q10/q50/q90 fields as they may appear on a raw registry metadata
/// row. Validation requires all three fields to be present.
/// 原始 registry metadata row 可能出現的 q10/q50/q90 欄位；驗證要求三者齊全。
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct RegistryQuantileTrioMetadata {
    pub q10: Option<String>,
    pub q50: Option<String>,
    pub q90: Option<String>,
}

/// Validated exact q10/q50/q90 trio.
/// 已驗證的精確 q10/q50/q90 trio。
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RegistryQuantileTrioContract {
    pub q10: String,
    pub q50: String,
    pub q90: String,
}

/// Raw registry row advisory serving metadata. All fields are optional to model
/// source/DB rows that may be missing columns; validation fails closed.
/// 原始 registry advisory serving metadata；欄位用 Option 表示 row 可能缺欄，
/// validator 對缺欄 fail-closed。
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct RegistryAdvisoryServingMetadata {
    pub schema_version: Option<String>,
    pub contract_hash: Option<String>,
    pub dataset_manifest_schema_version: Option<String>,
    pub dataset_manifest_hash: Option<String>,
    pub label_schema_hash: Option<String>,
    pub feature_schema_hash: Option<String>,
    pub feature_definition_hash: Option<String>,
    pub split_hash: Option<String>,
    pub leakage_report_hash: Option<String>,
    pub serving_config_hash: Option<String>,
    pub missingness_policy: Option<String>,
    pub units: Option<String>,
    pub side_handling: Option<String>,
    pub artifact_hashes: Option<RegistryQuantileTrioMetadata>,
    pub quantile_trio: Option<RegistryQuantileTrioMetadata>,
    pub serving_mode: Option<String>,
    pub not_authority: Option<bool>,
    pub symlink_authority: Option<bool>,
    pub promotion_serving_ready: Option<bool>,
}

/// Validated advisory-only serving contract. This remains non-promotable:
/// `promotion_serving_ready` must be false by construction.
/// 已驗證的 advisory-only serving contract；依設計仍不可 promotion serving。
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RegistryAdvisoryServingContract {
    pub schema_version: String,
    pub contract_hash: String,
    pub dataset_manifest_schema_version: String,
    pub dataset_manifest_hash: String,
    pub label_schema_hash: String,
    pub feature_schema_hash: String,
    pub feature_definition_hash: String,
    pub split_hash: String,
    pub leakage_report_hash: String,
    pub serving_config_hash: String,
    pub missingness_policy: String,
    pub units: String,
    pub side_handling: String,
    pub artifact_hashes: RegistryQuantileTrioContract,
    pub quantile_trio: RegistryQuantileTrioContract,
    pub serving_mode: String,
    pub not_authority: bool,
    pub symlink_authority: bool,
    pub promotion_serving_ready: bool,
}

/// Fail-closed validation errors for registry-authorized advisory serving.
/// Registry-authorized advisory serving 的 fail-closed 驗證錯誤。
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RegistryAdvisoryServingValidationError {
    MissingField {
        field: &'static str,
    },
    MissingQuantileField {
        field: &'static str,
        quantile: &'static str,
    },
    QuantileTrioMismatch {
        quantile: &'static str,
        expected: &'static str,
        actual: String,
    },
    SchemaVersionMismatch {
        field: &'static str,
        expected: &'static str,
        actual: Option<String>,
    },
    MalformedHashField {
        field: &'static str,
        actual: String,
    },
    ContractHashMismatch {
        expected: String,
        actual: String,
    },
    ContractHashUncomputable {
        reason: String,
    },
    ServingModeMismatch {
        actual: Option<String>,
    },
    BooleanFieldMismatch {
        field: &'static str,
        expected: bool,
        actual: Option<bool>,
    },
    ResolvedArtifactMissingFeatureSchemaHash {
        registry_id: i64,
    },
    ResolvedArtifactMissingArtifactSha256 {
        registry_id: i64,
    },
    ResolvedArtifactUnknownQuantile {
        registry_id: i64,
        quantile: String,
    },
    FeatureSchemaHashMismatch {
        registry_id: i64,
        contract: String,
        resolved: String,
    },
    ArtifactSha256Mismatch {
        registry_id: i64,
        quantile: String,
        contract: String,
        resolved: String,
    },
}

impl std::fmt::Display for RegistryAdvisoryServingValidationError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::MissingField { field } => {
                write!(f, "registry advisory serving metadata missing {field}")
            }
            Self::MissingQuantileField { field, quantile } => {
                write!(
                    f,
                    "registry advisory serving metadata missing {field}.{quantile}"
                )
            }
            Self::QuantileTrioMismatch {
                quantile,
                expected,
                actual,
            } => write!(
                f,
                "registry advisory serving quantile_trio.{quantile} mismatch: expected {expected}, got {actual}"
            ),
            Self::SchemaVersionMismatch {
                field,
                expected,
                actual,
            } => write!(
                f,
                "registry advisory serving {field} must be {expected}, got {actual:?}"
            ),
            Self::MalformedHashField { field, actual } => write!(
                f,
                "registry advisory serving {field} must be sha256 64-hex, got {actual:?}"
            ),
            Self::ContractHashMismatch { expected, actual } => write!(
                f,
                "registry advisory serving contract_hash mismatch: expected {expected}, got {actual}"
            ),
            Self::ContractHashUncomputable { reason } => write!(
                f,
                "registry advisory serving contract_hash uncomputable: {reason}"
            ),
            Self::ServingModeMismatch { actual } => write!(
                f,
                "registry advisory serving_mode must be {REGISTRY_ADVISORY_SERVING_MODE}, got {actual:?}"
            ),
            Self::BooleanFieldMismatch {
                field,
                expected,
                actual,
            } => write!(
                f,
                "registry advisory serving {field} must be {expected}, got {actual:?}"
            ),
            Self::ResolvedArtifactMissingFeatureSchemaHash { registry_id } => write!(
                f,
                "resolved artifact registry_id={registry_id} has no feature_schema_hash"
            ),
            Self::ResolvedArtifactMissingArtifactSha256 { registry_id } => write!(
                f,
                "resolved artifact registry_id={registry_id} has no artifact_sha256"
            ),
            Self::ResolvedArtifactUnknownQuantile {
                registry_id,
                quantile,
            } => write!(
                f,
                "resolved artifact registry_id={registry_id} has unknown quantile {quantile:?}"
            ),
            Self::FeatureSchemaHashMismatch {
                registry_id,
                contract,
                resolved,
            } => write!(
                f,
                "registry advisory serving feature_schema_hash mismatch for registry_id={registry_id}: contract={contract} resolved={resolved}"
            ),
            Self::ArtifactSha256Mismatch {
                registry_id,
                quantile,
                contract,
                resolved,
            } => write!(
                f,
                "registry advisory serving artifact_sha256 mismatch for registry_id={registry_id} quantile={quantile}: contract={contract} resolved={resolved}"
            ),
        }
    }
}

impl std::error::Error for RegistryAdvisoryServingValidationError {}

/// Validate registry row metadata for advisory-only serving. Pure function:
/// no DB query, filesystem/symlink inspection, ONNX/ORT load, runtime mutation,
/// credential access, order/probe, or Cost Gate change.
///
/// 驗證 registry row 的 advisory-only serving metadata。純函式：不查 DB、不讀
/// 檔案或 symlink、不載入 ONNX/ORT、不碰 runtime/憑證/下單/探測/Cost Gate。
pub fn validate_registry_advisory_serving_metadata(
    metadata: &RegistryAdvisoryServingMetadata,
    resolved_artifact: Option<&ResolvedArtifact>,
) -> Result<RegistryAdvisoryServingContract, RegistryAdvisoryServingValidationError> {
    let schema_version = require_registry_literal(
        "schema_version",
        &metadata.schema_version,
        REGISTRY_SERVING_CONTRACT_SCHEMA_VERSION,
    )?;
    let dataset_manifest_schema_version = require_registry_literal(
        "dataset_manifest_schema_version",
        &metadata.dataset_manifest_schema_version,
        PIT_DATASET_MANIFEST_SCHEMA_VERSION,
    )?;
    let dataset_manifest_hash =
        require_registry_hash("dataset_manifest_hash", &metadata.dataset_manifest_hash)?;
    let label_schema_hash =
        require_registry_hash("label_schema_hash", &metadata.label_schema_hash)?;
    let feature_schema_hash =
        require_registry_hash("feature_schema_hash", &metadata.feature_schema_hash)?;
    let feature_definition_hash =
        require_registry_hash("feature_definition_hash", &metadata.feature_definition_hash)?;
    let split_hash = require_registry_hash("split_hash", &metadata.split_hash)?;
    let leakage_report_hash =
        require_registry_hash("leakage_report_hash", &metadata.leakage_report_hash)?;
    let serving_config_hash =
        require_registry_hash("serving_config_hash", &metadata.serving_config_hash)?;
    let missingness_policy =
        require_registry_text("missingness_policy", &metadata.missingness_policy)?;
    let units = require_registry_text("units", &metadata.units)?;
    let side_handling = require_registry_text("side_handling", &metadata.side_handling)?;
    let artifact_hashes = validate_artifact_hashes(&metadata.artifact_hashes)?;
    let quantile_trio = validate_quantile_trio(&metadata.quantile_trio)?;
    let serving_mode = match metadata.serving_mode.as_deref().map(str::trim) {
        Some(REGISTRY_ADVISORY_SERVING_MODE) => REGISTRY_ADVISORY_SERVING_MODE.to_string(),
        _ => {
            return Err(
                RegistryAdvisoryServingValidationError::ServingModeMismatch {
                    actual: metadata.serving_mode.clone(),
                },
            )
        }
    };
    let not_authority = require_registry_bool("not_authority", metadata.not_authority, true)?;
    let symlink_authority =
        require_registry_bool("symlink_authority", metadata.symlink_authority, false)?;
    let promotion_serving_ready = require_registry_bool(
        "promotion_serving_ready",
        metadata.promotion_serving_ready,
        false,
    )?;
    let computed_contract_hash = compute_registry_advisory_serving_contract_hash_parts(
        &schema_version,
        &dataset_manifest_schema_version,
        &dataset_manifest_hash,
        &label_schema_hash,
        &feature_schema_hash,
        &feature_definition_hash,
        &split_hash,
        &leakage_report_hash,
        &serving_config_hash,
        &missingness_policy,
        &units,
        &side_handling,
        &artifact_hashes,
        &quantile_trio,
        &serving_mode,
        not_authority,
        symlink_authority,
        promotion_serving_ready,
    )?;
    let contract_hash = require_registry_hash("contract_hash", &metadata.contract_hash)?;
    let contract_hash_hex = strip_sha256_prefix(&contract_hash);
    if contract_hash_hex != computed_contract_hash {
        return Err(
            RegistryAdvisoryServingValidationError::ContractHashMismatch {
                expected: computed_contract_hash,
                actual: contract_hash,
            },
        );
    }

    if let Some(resolved) = resolved_artifact {
        validate_resolved_artifact_contract_binding(
            resolved,
            &feature_schema_hash,
            &artifact_hashes,
        )?;
    }

    Ok(RegistryAdvisoryServingContract {
        schema_version,
        contract_hash,
        dataset_manifest_schema_version,
        dataset_manifest_hash,
        label_schema_hash,
        feature_schema_hash,
        feature_definition_hash,
        split_hash,
        leakage_report_hash,
        serving_config_hash,
        missingness_policy,
        units,
        side_handling,
        artifact_hashes,
        quantile_trio,
        serving_mode,
        not_authority,
        symlink_authority,
        promotion_serving_ready,
    })
}

fn validate_resolved_artifact_contract_binding(
    resolved: &ResolvedArtifact,
    feature_schema_hash: &str,
    artifact_hashes: &RegistryQuantileTrioContract,
) -> Result<(), RegistryAdvisoryServingValidationError> {
    match resolved.feature_schema_hash.as_deref().map(str::trim) {
        Some(resolved_hash) if resolved_hash == feature_schema_hash => {}
        Some(resolved_hash) => {
            return Err(
                RegistryAdvisoryServingValidationError::FeatureSchemaHashMismatch {
                    registry_id: resolved.id,
                    contract: feature_schema_hash.to_string(),
                    resolved: resolved_hash.to_string(),
                },
            )
        }
        None => {
            return Err(
                RegistryAdvisoryServingValidationError::ResolvedArtifactMissingFeatureSchemaHash {
                    registry_id: resolved.id,
                },
            )
        }
    }

    let row_hash = match resolved.artifact_sha256.as_deref().map(str::trim) {
        Some(hash) if !hash.is_empty() => hash,
        _ => {
            return Err(
                RegistryAdvisoryServingValidationError::ResolvedArtifactMissingArtifactSha256 {
                    registry_id: resolved.id,
                },
            )
        }
    };
    let quantile = resolved.quantile.trim();
    let contract_hash = match quantile {
        REGISTRY_Q10 => &artifact_hashes.q10,
        REGISTRY_Q50 => &artifact_hashes.q50,
        REGISTRY_Q90 => &artifact_hashes.q90,
        _ => {
            return Err(
                RegistryAdvisoryServingValidationError::ResolvedArtifactUnknownQuantile {
                    registry_id: resolved.id,
                    quantile: quantile.to_string(),
                },
            )
        }
    };
    if strip_sha256_prefix(row_hash) != strip_sha256_prefix(contract_hash) {
        return Err(
            RegistryAdvisoryServingValidationError::ArtifactSha256Mismatch {
                registry_id: resolved.id,
                quantile: quantile.to_string(),
                contract: contract_hash.to_string(),
                resolved: row_hash.to_string(),
            },
        );
    }

    Ok(())
}

fn require_registry_text(
    field: &'static str,
    value: &Option<String>,
) -> Result<String, RegistryAdvisoryServingValidationError> {
    match value.as_deref().map(str::trim) {
        Some(v) if !v.is_empty() => Ok(v.to_string()),
        _ => Err(RegistryAdvisoryServingValidationError::MissingField { field }),
    }
}

fn require_registry_literal(
    field: &'static str,
    value: &Option<String>,
    expected: &'static str,
) -> Result<String, RegistryAdvisoryServingValidationError> {
    match value.as_deref().map(str::trim) {
        Some(actual) if actual == expected => Ok(actual.to_string()),
        _ => Err(
            RegistryAdvisoryServingValidationError::SchemaVersionMismatch {
                field,
                expected,
                actual: value.clone(),
            },
        ),
    }
}

fn require_registry_hash(
    field: &'static str,
    value: &Option<String>,
) -> Result<String, RegistryAdvisoryServingValidationError> {
    let text = require_registry_text(field, value)?;
    if is_sha256_hex(&text) {
        Ok(text)
    } else {
        Err(RegistryAdvisoryServingValidationError::MalformedHashField {
            field,
            actual: text,
        })
    }
}

fn strip_sha256_prefix(value: &str) -> &str {
    value.strip_prefix("sha256:").unwrap_or(value)
}

fn is_sha256_hex(value: &str) -> bool {
    let hex = strip_sha256_prefix(value);
    hex.len() == 64 && hex.bytes().all(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f'))
}

fn require_registry_bool(
    field: &'static str,
    value: Option<bool>,
    expected: bool,
) -> Result<bool, RegistryAdvisoryServingValidationError> {
    match value {
        Some(actual) if actual == expected => Ok(actual),
        _ => Err(
            RegistryAdvisoryServingValidationError::BooleanFieldMismatch {
                field,
                expected,
                actual: value,
            },
        ),
    }
}

fn validate_artifact_hashes(
    artifact_hashes: &Option<RegistryQuantileTrioMetadata>,
) -> Result<RegistryQuantileTrioContract, RegistryAdvisoryServingValidationError> {
    let trio =
        artifact_hashes
            .as_ref()
            .ok_or(RegistryAdvisoryServingValidationError::MissingField {
                field: "artifact_hashes",
            })?;
    Ok(RegistryQuantileTrioContract {
        q10: require_quantile_hash("artifact_hashes", REGISTRY_Q10, &trio.q10)?,
        q50: require_quantile_hash("artifact_hashes", REGISTRY_Q50, &trio.q50)?,
        q90: require_quantile_hash("artifact_hashes", REGISTRY_Q90, &trio.q90)?,
    })
}

fn validate_quantile_trio(
    quantile_trio: &Option<RegistryQuantileTrioMetadata>,
) -> Result<RegistryQuantileTrioContract, RegistryAdvisoryServingValidationError> {
    let trio =
        quantile_trio
            .as_ref()
            .ok_or(RegistryAdvisoryServingValidationError::MissingField {
                field: "quantile_trio",
            })?;
    let q10 = require_quantile_label(REGISTRY_Q10, &trio.q10)?;
    let q50 = require_quantile_label(REGISTRY_Q50, &trio.q50)?;
    let q90 = require_quantile_label(REGISTRY_Q90, &trio.q90)?;
    Ok(RegistryQuantileTrioContract { q10, q50, q90 })
}

fn require_quantile_text(
    field: &'static str,
    quantile: &'static str,
    value: &Option<String>,
) -> Result<String, RegistryAdvisoryServingValidationError> {
    match value.as_deref().map(str::trim) {
        Some(v) if !v.is_empty() => Ok(v.to_string()),
        _ => Err(RegistryAdvisoryServingValidationError::MissingQuantileField { field, quantile }),
    }
}

fn require_quantile_hash(
    field: &'static str,
    quantile: &'static str,
    value: &Option<String>,
) -> Result<String, RegistryAdvisoryServingValidationError> {
    let text = require_quantile_text(field, quantile, value)?;
    if is_sha256_hex(&text) {
        Ok(text)
    } else {
        Err(RegistryAdvisoryServingValidationError::MalformedHashField {
            field,
            actual: text,
        })
    }
}

fn require_quantile_label(
    quantile: &'static str,
    value: &Option<String>,
) -> Result<String, RegistryAdvisoryServingValidationError> {
    let label = require_quantile_text("quantile_trio", quantile, value)?;
    if label == quantile {
        Ok(label)
    } else {
        Err(
            RegistryAdvisoryServingValidationError::QuantileTrioMismatch {
                quantile,
                expected: quantile,
                actual: label,
            },
        )
    }
}

#[allow(clippy::too_many_arguments)]
fn compute_registry_advisory_serving_contract_hash_parts(
    schema_version: &str,
    dataset_manifest_schema_version: &str,
    dataset_manifest_hash: &str,
    label_schema_hash: &str,
    feature_schema_hash: &str,
    feature_definition_hash: &str,
    split_hash: &str,
    leakage_report_hash: &str,
    serving_config_hash: &str,
    missingness_policy: &str,
    units: &str,
    side_handling: &str,
    artifact_hashes: &RegistryQuantileTrioContract,
    quantile_trio: &RegistryQuantileTrioContract,
    serving_mode: &str,
    not_authority: bool,
    symlink_authority: bool,
    promotion_serving_ready: bool,
) -> Result<String, RegistryAdvisoryServingValidationError> {
    let mut artifact_hashes_json = BTreeMap::new();
    artifact_hashes_json.insert(
        REGISTRY_Q10.to_string(),
        serde_json::Value::String(artifact_hashes.q10.clone()),
    );
    artifact_hashes_json.insert(
        REGISTRY_Q50.to_string(),
        serde_json::Value::String(artifact_hashes.q50.clone()),
    );
    artifact_hashes_json.insert(
        REGISTRY_Q90.to_string(),
        serde_json::Value::String(artifact_hashes.q90.clone()),
    );

    let mut payload = BTreeMap::new();
    payload.insert(
        "artifact_hashes".to_string(),
        serde_json::to_value(artifact_hashes_json).map_err(|err| {
            RegistryAdvisoryServingValidationError::ContractHashUncomputable {
                reason: err.to_string(),
            }
        })?,
    );
    payload.insert(
        "dataset_manifest_hash".to_string(),
        serde_json::Value::String(dataset_manifest_hash.to_string()),
    );
    payload.insert(
        "dataset_manifest_schema_version".to_string(),
        serde_json::Value::String(dataset_manifest_schema_version.to_string()),
    );
    payload.insert(
        "feature_definition_hash".to_string(),
        serde_json::Value::String(feature_definition_hash.to_string()),
    );
    payload.insert(
        "feature_schema_hash".to_string(),
        serde_json::Value::String(feature_schema_hash.to_string()),
    );
    payload.insert(
        "label_schema_hash".to_string(),
        serde_json::Value::String(label_schema_hash.to_string()),
    );
    payload.insert(
        "leakage_report_hash".to_string(),
        serde_json::Value::String(leakage_report_hash.to_string()),
    );
    payload.insert(
        "missingness_policy".to_string(),
        serde_json::Value::String(missingness_policy.to_string()),
    );
    payload.insert(
        "not_authority".to_string(),
        serde_json::Value::Bool(not_authority),
    );
    payload.insert(
        "promotion_serving_ready".to_string(),
        serde_json::Value::Bool(promotion_serving_ready),
    );
    payload.insert(
        "quantile_trio".to_string(),
        serde_json::Value::Array(vec![
            serde_json::Value::String(quantile_trio.q10.clone()),
            serde_json::Value::String(quantile_trio.q50.clone()),
            serde_json::Value::String(quantile_trio.q90.clone()),
        ]),
    );
    payload.insert(
        "schema_version".to_string(),
        serde_json::Value::String(schema_version.to_string()),
    );
    payload.insert(
        "serving_config_hash".to_string(),
        serde_json::Value::String(serving_config_hash.to_string()),
    );
    payload.insert(
        "serving_mode".to_string(),
        serde_json::Value::String(serving_mode.to_string()),
    );
    payload.insert(
        "side_handling".to_string(),
        serde_json::Value::String(side_handling.to_string()),
    );
    payload.insert(
        "split_hash".to_string(),
        serde_json::Value::String(split_hash.to_string()),
    );
    payload.insert(
        "symlink_authority".to_string(),
        serde_json::Value::Bool(symlink_authority),
    );
    payload.insert(
        "units".to_string(),
        serde_json::Value::String(units.to_string()),
    );

    let canonical = serde_json::to_string(&payload).map_err(|err| {
        RegistryAdvisoryServingValidationError::ContractHashUncomputable {
            reason: err.to_string(),
        }
    })?;
    let mut hasher = Sha256::new();
    hasher.update(canonical.as_bytes());
    Ok(hex::encode(hasher.finalize()))
}

/// Feature-schema hash mismatch between registry row and engine runtime.
/// Returned by `validate_schema_hash` when the registered artifact was
/// trained against a different feature schema than the engine is currently
/// built with. Caller should treat this as "disable this slot" — loading
/// the ONNX would likely panic on the first `session.run` call due to
/// feature dim / ordering drift.
///
/// Registry row 與 engine 運行時之間的 feature schema hash 不匹配。
/// `validate_schema_hash` 在註冊 artifact 與當前 engine 的 feature schema
/// 不同時回此錯；caller 應 disable 該 slot（直接 load ONNX 會在第一次
/// `session.run` 因 feature dim/排序漂移 panic）。
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SchemaHashMismatch {
    /// The hash stored in `learning.model_registry.feature_schema_hash`.
    /// 存於 `learning.model_registry.feature_schema_hash` 的值。
    pub registry: String,
    /// The hash compiled into the engine (typically `FEATURE_NAMES_V1_HASH`).
    /// 編譯進 engine 的 hash（通常為 `FEATURE_NAMES_V1_HASH`）。
    pub engine: String,
}

impl std::fmt::Display for SchemaHashMismatch {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "feature schema hash mismatch: registry={} engine={} \
             (feature dim/ordering drift — load disabled)",
            self.registry, self.engine,
        )
    }
}

impl std::error::Error for SchemaHashMismatch {}

/// Validate that a resolved artifact's `feature_schema_hash` matches the
/// engine's compiled-in feature schema. Pure function — no side effects.
///
/// Semantics:
/// * `None` on the resolved artifact → `Ok(())` + warn log. Registered
///   before the column was populated; treat as best-effort legacy OK so
///   early adopters aren't locked out at Phase 3 cut-over.
/// * Hash matches → `Ok(())`.
/// * Hash differs → `Err(SchemaHashMismatch)`. Caller should skip loading
///   this slot and fall back to the Disabled path (not panic).
///
/// Phase 3+ integration: the startup sequence / SIGHUP handler in
/// `OnnxModelManager` will call this before every `new(path, ...)` attempt
/// with the engine's `FEATURE_NAMES_V1_HASH` constant. Failure → log +
/// Disabled fallback, never panic.
///
/// 驗 resolved artifact 的 feature_schema_hash 是否匹配 engine 編譯的 schema。
/// 純函式，無副作用。語意：None → Ok + warn（legacy row 當 OK 向後相容）；
/// 相符 → Ok；不符 → Err，caller 應跳過 load 走 Disabled fallback（不 panic）。
/// Phase 3+ 整合時由 `OnnxModelManager::new(...)` 前呼，失敗 → log + Disabled。
pub fn validate_schema_hash(
    resolved: &ResolvedArtifact,
    engine_schema_hash: &str,
) -> Result<(), SchemaHashMismatch> {
    match &resolved.feature_schema_hash {
        None => {
            warn!(
                registry_id = resolved.id,
                engine_hash = %engine_schema_hash,
                "registry row has no feature_schema_hash — legacy row, treating as OK / \
                 legacy row 無 feature_schema_hash，視為 OK"
            );
            Ok(())
        }
        Some(reg_hash) if reg_hash == engine_schema_hash => Ok(()),
        Some(reg_hash) => Err(SchemaHashMismatch {
            registry: reg_hash.clone(),
            engine: engine_schema_hash.to_string(),
        }),
    }
}

/// Resolve the canonical artifact for a slot. Prefers canary_status='production'
/// then 'promoting'; orders by promoted_at DESC NULLS LAST so in-flight promote
/// wins. Returns `Ok(None)` when no matching row exists. `_current` remains a
/// legacy filename convenience only; it is not registry serving authority.
/// `Err` only on DB error — caller should log and treat as `None` equivalent
/// for graceful degradation.
///
/// **Phase 3+ integration contract**: before feeding the returned
/// `ResolvedArtifact.artifact_path` to `OnnxModelManager::new(...)`, the caller
/// MUST invoke `validate_schema_hash(resolved, FEATURE_NAMES_V1_HASH)` to
/// detect feature-schema drift between training time and engine runtime. A
/// mismatch means `session.run` would panic on feature dim / ordering mismatch
/// — on `Err(SchemaHashMismatch)` caller should log + route the slot through
/// the Disabled fallback path, not surface the error or retry.
///
/// 取 slot 的權威 artifact。優先 production → promoting；promoted_at DESC NULLS
/// LAST，進行中的晉升勝出。無匹配 row → Ok(None)；`_current` 只可作
/// legacy filename convenience，不是 registry serving authority。
/// Err 僅 DB 錯誤，caller 應 log 並視為 None（優雅降級）。
/// **Phase 3+ 整合契約**：把 `artifact_path` 餵給 `OnnxModelManager::new(...)`
/// 前必須呼 `validate_schema_hash(resolved, FEATURE_NAMES_V1_HASH)` 檢 schema
/// 漂移；mismatch → `session.run` 會 panic，caller 應 log + 走 Disabled fallback。
pub async fn resolve_latest_production_artifact(
    pool: &DbPool,
    slot: &ModelSlot,
) -> Result<Option<ResolvedArtifact>, sqlx::Error> {
    let pg = match pool.get() {
        Some(p) => p,
        None => {
            debug!(
                strategy = %slot.strategy,
                "registry: pool unavailable — resolver skipped"
            );
            return Ok(None);
        }
    };

    // NOTE on ORDER BY:
    //   canary_status ASC places 'production' before 'promoting' (alpha), which
    //   is the wrong direction — we want production to win. Use CASE expression
    //   to force production=0, promoting=1 so ASC sorts production first.
    //   promoted_at DESC NULLS LAST so newly-promoted (has ts) wins over the
    //   prior production row that might not have promoted_at set if written by
    //   a legacy path.
    // 注意 ORDER BY：canary_status ASC 會是 promoting 先（字母序），但我們
    // 想要 production 贏。用 CASE 強制 production=0 / promoting=1 讓 ASC
    // 排 production 前。promoted_at DESC NULLS LAST 讓新晉升的勝出。
    let row: Option<(
        i64,
        String,
        String,
        String,
        String,
        Option<String>,
        Option<String>,
    )> = sqlx::query_as(
        "SELECT id, artifact_path, canary_status, verdict, \
                to_char(train_date, 'YYYY-MM-DD') AS train_date, \
                artifact_sha256, feature_schema_hash \
         FROM learning.model_registry \
         WHERE strategy = $1 AND engine_mode = $2 AND quantile = $3 \
           AND canary_status IN ('production', 'promoting') \
         ORDER BY \
           CASE canary_status WHEN 'production' THEN 0 ELSE 1 END ASC, \
           promoted_at DESC NULLS LAST, \
           created_at DESC \
         LIMIT 1",
    )
    .bind(&slot.strategy)
    .bind(&slot.engine_mode)
    .bind(&slot.quantile)
    .fetch_optional(pg)
    .await?;

    match row {
        Some((
            id,
            artifact_path,
            canary_status,
            verdict,
            train_date,
            artifact_sha256,
            feature_schema_hash,
        )) => {
            debug!(
                strategy = %slot.strategy,
                engine_mode = %slot.engine_mode,
                quantile = %slot.quantile,
                registry_id = id,
                status = %canary_status,
                "registry resolved / registry 解析完成"
            );
            Ok(Some(ResolvedArtifact {
                id,
                artifact_path,
                canary_status,
                verdict,
                train_date,
                quantile: slot.quantile.clone(),
                artifact_sha256,
                feature_schema_hash,
            }))
        }
        None => {
            debug!(
                strategy = %slot.strategy,
                "registry: no production/promoting row found for slot"
            );
            Ok(None)
        }
    }
}

/// Compose the `_current` symlink filename for a slot (V017 naming convention).
/// The filename matches what `onnx_exporter::_atomic_symlink_swap` writes:
///   edge_predictor_{engine_mode}_{strategy}_{quantile}_{schema_version}_current.onnx
///
/// Pure synchronous helper — does not touch the filesystem and does not grant
/// advisory serving, promotion, order, or runtime authority. Registry serving
/// authority must come from validated registry row metadata, not this filename.
///
/// 組 slot 的 `_current` symlink 檔名（V017 命名規則）。純同步 helper，
/// 不觸及檔案系統，也不授予 advisory serving、promotion、order 或 runtime
/// authority。Serving authority 必須來自已驗證的 registry row metadata。
pub fn symlink_filename(slot: &ModelSlot, schema_version: &str) -> String {
    format!(
        "edge_predictor_{}_{}_{}_{}_current.onnx",
        slot.engine_mode, slot.strategy, slot.quantile, schema_version
    )
}

/// Warn-log a registry lookup failure without propagating. Lightweight wrapper
/// so caller sites stay tidy. This does not authorize `_current` serving.
/// 警告 log registry 查詢失敗；不授權 `_current` serving。
pub fn log_registry_failure(slot: &ModelSlot, err: &sqlx::Error) {
    warn!(
        strategy = %slot.strategy,
        engine_mode = %slot.engine_mode,
        quantile = %slot.quantile,
        error = %err,
        "model registry lookup failed — `_current` filename remains non-authoritative / registry 查詢失敗，`_current` 檔名仍非權威"
    );
}

#[cfg(test)]
mod tests {
    use super::*;

    // Pure-logic tests that don't require a live PG connection. The async
    // resolver is covered by integration tests against a test DB (deferred
    // to B7 healthcheck integration work).
    // 無需活 PG 的純邏輯測試；async resolver 的整合測試留到 B7。

    #[test]
    fn test_symlink_filename_format() {
        let slot = ModelSlot::new("ma_crossover", "demo", "q50");
        let name = symlink_filename(&slot, "v1");
        assert_eq!(name, "edge_predictor_demo_ma_crossover_q50_v1_current.onnx");
    }

    #[test]
    fn test_symlink_filename_all_quantiles() {
        // Aligns with onnx_exporter.py `_atomic_symlink_swap` naming for
        // all three trio members — drift guard for cross-language agreement.
        // 對齊 onnx_exporter.py `_atomic_symlink_swap` 的 3 quantile 命名。
        for q in ["q10", "q50", "q90"] {
            let slot = ModelSlot::new("bb_breakout", "live_demo", q);
            let name = symlink_filename(&slot, "v2");
            assert_eq!(
                name,
                format!("edge_predictor_live_demo_bb_breakout_{q}_v2_current.onnx"),
            );
        }
    }

    #[test]
    fn test_model_slot_equality_and_hash() {
        // HashMap keying — same logical slot must hash identically so a slot
        // map can cache resolved artifacts per tick.
        // HashMap keying：同一 slot 必須 hash 一致，供 per-tick 快取。
        let a = ModelSlot::new("ma_crossover", "demo", "q50");
        let b = ModelSlot::new("ma_crossover", "demo", "q50");
        let c = ModelSlot::new("ma_crossover", "demo", "q10");
        assert_eq!(a, b);
        assert_ne!(a, c);
        let mut map = std::collections::HashMap::new();
        map.insert(a, "artifact_a.onnx");
        assert_eq!(map.get(&b), Some(&"artifact_a.onnx"));
        assert_eq!(map.get(&c), None);
    }

    #[test]
    fn test_resolved_artifact_construction() {
        // Minimal smoke test — ensures the struct literal + Clone + PartialEq
        // stay usable. Production code will construct this from sqlx row.
        // 極簡煙霧測試；production 會從 sqlx row 構造。
        let a = ResolvedArtifact {
            id: 42,
            artifact_path:
                "/tmp/openclaw/models/edge_predictor_demo_ma_crossover_q50_v1_2026-04-23.onnx"
                    .into(),
            canary_status: "production".into(),
            verdict: "should_ship".into(),
            train_date: "2026-04-23".into(),
            quantile: REGISTRY_Q50.into(),
            artifact_sha256: Some("deadbeef".into()),
            feature_schema_hash: Some("abc123".into()),
        };
        let b = a.clone();
        assert_eq!(a, b);
        assert_eq!(a.canary_status, "production");
    }

    fn _valid_advisory_metadata() -> RegistryAdvisoryServingMetadata {
        RegistryAdvisoryServingMetadata {
            schema_version: Some(REGISTRY_SERVING_CONTRACT_SCHEMA_VERSION.into()),
            contract_hash: Some(
                "481ac63e09b545238027e971a6716b6c5f5dcb04161617fc43ae9be1819f403d".into(),
            ),
            dataset_manifest_schema_version: Some(PIT_DATASET_MANIFEST_SCHEMA_VERSION.into()),
            dataset_manifest_hash: Some("a".repeat(64)),
            label_schema_hash: Some("b".repeat(64)),
            feature_schema_hash: Some("c".repeat(64)),
            feature_definition_hash: Some("d".repeat(64)),
            split_hash: Some("e".repeat(64)),
            leakage_report_hash: Some("f".repeat(64)),
            serving_config_hash: Some("1".repeat(64)),
            missingness_policy: Some("fail_closed_missingness_v1".into()),
            units: Some("bps".into()),
            side_handling: Some("explicit_side_v1".into()),
            artifact_hashes: Some(RegistryQuantileTrioMetadata {
                q10: Some(format!("sha256:{}", "2".repeat(64))),
                q50: Some("3".repeat(64)),
                q90: Some(format!("sha256:{}", "4".repeat(64))),
            }),
            quantile_trio: Some(RegistryQuantileTrioMetadata {
                q10: Some("q10".into()),
                q50: Some("q50".into()),
                q90: Some("q90".into()),
            }),
            serving_mode: Some(REGISTRY_ADVISORY_SERVING_MODE.into()),
            not_authority: Some(true),
            symlink_authority: Some(false),
            promotion_serving_ready: Some(false),
        }
    }

    fn _resolved_artifact_with_quantile_hash_and_feature_schema(
        quantile: &str,
        artifact_sha256: Option<String>,
        feature_schema_hash: Option<String>,
    ) -> ResolvedArtifact {
        ResolvedArtifact {
            id: 99,
            artifact_path: "/tmp/source_only_not_read.onnx".into(),
            canary_status: "production".into(),
            verdict: "should_ship".into(),
            train_date: "2026-07-06".into(),
            quantile: quantile.into(),
            artifact_sha256,
            feature_schema_hash,
        }
    }

    fn _resolved_artifact_with_feature_schema(hash: Option<String>) -> ResolvedArtifact {
        _resolved_artifact_with_quantile_hash_and_feature_schema(
            REGISTRY_Q50,
            Some("3".repeat(64)),
            hash,
        )
    }

    #[test]
    fn test_advisory_serving_metadata_valid_contract_passes() {
        // WP3 source-only contract: complete registry metadata passes as
        // advisory-only, still non-promotable and non-authoritative.
        // WP3 純 source 合約：完整 metadata 僅通過 advisory-only，仍不可 promotion。
        let metadata = _valid_advisory_metadata();
        let resolved = _resolved_artifact_with_feature_schema(Some("c".repeat(64)));
        let contract =
            validate_registry_advisory_serving_metadata(&metadata, Some(&resolved)).unwrap();

        assert_eq!(
            contract.schema_version,
            REGISTRY_SERVING_CONTRACT_SCHEMA_VERSION
        );
        assert_eq!(
            contract.dataset_manifest_schema_version,
            PIT_DATASET_MANIFEST_SCHEMA_VERSION
        );
        assert_eq!(contract.dataset_manifest_hash, "a".repeat(64));
        assert_eq!(
            contract.artifact_hashes.q10,
            format!("sha256:{}", "2".repeat(64))
        );
        assert_eq!(contract.quantile_trio.q90, "q90");
        assert_eq!(
            contract.contract_hash,
            "481ac63e09b545238027e971a6716b6c5f5dcb04161617fc43ae9be1819f403d"
        );
        assert_eq!(contract.serving_mode, REGISTRY_ADVISORY_SERVING_MODE);
        assert!(contract.not_authority);
        assert!(!contract.symlink_authority);
        assert!(!contract.promotion_serving_ready);
    }

    #[test]
    fn test_advisory_serving_valid_q50_row_hash_matches_contract_passes() {
        // Row artifact hash must bind to the contract hash for the resolved
        // quantile, after stripping optional sha256 prefixes.
        // Row artifact hash 必須綁到 resolved quantile 的 contract hash。
        let metadata = _valid_advisory_metadata();
        let resolved = _resolved_artifact_with_quantile_hash_and_feature_schema(
            REGISTRY_Q50,
            Some(format!("sha256:{}", "3".repeat(64))),
            Some("c".repeat(64)),
        );

        assert!(validate_registry_advisory_serving_metadata(&metadata, Some(&resolved)).is_ok());
    }

    #[test]
    fn test_advisory_serving_missing_dataset_manifest_hash_fails() {
        // Missing lineage hash must fail closed.
        // 缺 lineage hash 必須 fail-closed。
        let mut metadata = _valid_advisory_metadata();
        metadata.dataset_manifest_hash = None;
        let resolved = _resolved_artifact_with_feature_schema(Some("c".repeat(64)));

        assert_eq!(
            validate_registry_advisory_serving_metadata(&metadata, Some(&resolved)),
            Err(RegistryAdvisoryServingValidationError::MissingField {
                field: "dataset_manifest_hash",
            }),
        );
    }

    #[test]
    fn test_advisory_serving_partial_q50_only_artifact_hashes_fail() {
        // q50-only artifact metadata is not an exact quantile trio.
        // 只有 q50 的 artifact metadata 不是完整 quantile trio。
        let mut metadata = _valid_advisory_metadata();
        metadata.artifact_hashes = Some(RegistryQuantileTrioMetadata {
            q10: None,
            q50: Some("3".repeat(64)),
            q90: None,
        });
        let resolved = _resolved_artifact_with_feature_schema(Some("c".repeat(64)));

        assert_eq!(
            validate_registry_advisory_serving_metadata(&metadata, Some(&resolved)),
            Err(
                RegistryAdvisoryServingValidationError::MissingQuantileField {
                    field: "artifact_hashes",
                    quantile: "q10",
                },
            ),
        );
    }

    #[test]
    fn test_advisory_serving_authority_flags_fail_closed() {
        // `_current` authority or promotion-serving readiness must never pass
        // this advisory-only source contract.
        // `_current` 權威或 promotion serving ready 均不可通過此 advisory 合約。
        let resolved = _resolved_artifact_with_feature_schema(Some("c".repeat(64)));

        let mut symlink_authority = _valid_advisory_metadata();
        symlink_authority.symlink_authority = Some(true);
        assert_eq!(
            validate_registry_advisory_serving_metadata(&symlink_authority, Some(&resolved)),
            Err(
                RegistryAdvisoryServingValidationError::BooleanFieldMismatch {
                    field: "symlink_authority",
                    expected: false,
                    actual: Some(true),
                },
            ),
        );

        let mut promotion_ready = _valid_advisory_metadata();
        promotion_ready.promotion_serving_ready = Some(true);
        assert_eq!(
            validate_registry_advisory_serving_metadata(&promotion_ready, Some(&resolved)),
            Err(
                RegistryAdvisoryServingValidationError::BooleanFieldMismatch {
                    field: "promotion_serving_ready",
                    expected: false,
                    actual: Some(true),
                },
            ),
        );
    }

    #[test]
    fn test_advisory_serving_resolved_feature_schema_mismatch_fails() {
        // Contract/registry parity check rejects feature schema drift before
        // any ONNX load could happen.
        // Contract/registry parity 在載入 ONNX 前拒絕 feature schema drift。
        let metadata = _valid_advisory_metadata();
        let resolved = _resolved_artifact_with_feature_schema(Some("9".repeat(64)));

        assert_eq!(
            validate_registry_advisory_serving_metadata(&metadata, Some(&resolved)),
            Err(
                RegistryAdvisoryServingValidationError::FeatureSchemaHashMismatch {
                    registry_id: 99,
                    contract: "c".repeat(64),
                    resolved: "9".repeat(64),
                },
            ),
        );
    }

    #[test]
    fn test_advisory_serving_resolved_artifact_sha256_mismatch_fails() {
        let metadata = _valid_advisory_metadata();
        let resolved = _resolved_artifact_with_quantile_hash_and_feature_schema(
            REGISTRY_Q50,
            Some("9".repeat(64)),
            Some("c".repeat(64)),
        );

        assert_eq!(
            validate_registry_advisory_serving_metadata(&metadata, Some(&resolved)),
            Err(
                RegistryAdvisoryServingValidationError::ArtifactSha256Mismatch {
                    registry_id: 99,
                    quantile: REGISTRY_Q50.into(),
                    contract: "3".repeat(64),
                    resolved: "9".repeat(64),
                },
            ),
        );
    }

    #[test]
    fn test_advisory_serving_resolved_artifact_sha256_missing_fails() {
        let metadata = _valid_advisory_metadata();
        let resolved = _resolved_artifact_with_quantile_hash_and_feature_schema(
            REGISTRY_Q50,
            None,
            Some("c".repeat(64)),
        );

        assert_eq!(
            validate_registry_advisory_serving_metadata(&metadata, Some(&resolved)),
            Err(
                RegistryAdvisoryServingValidationError::ResolvedArtifactMissingArtifactSha256 {
                    registry_id: 99,
                },
            ),
        );
    }

    #[test]
    fn test_advisory_serving_resolved_artifact_unknown_quantile_fails() {
        let metadata = _valid_advisory_metadata();
        let resolved = _resolved_artifact_with_quantile_hash_and_feature_schema(
            "q95",
            Some("3".repeat(64)),
            Some("c".repeat(64)),
        );

        assert_eq!(
            validate_registry_advisory_serving_metadata(&metadata, Some(&resolved)),
            Err(
                RegistryAdvisoryServingValidationError::ResolvedArtifactUnknownQuantile {
                    registry_id: 99,
                    quantile: "q95".into(),
                },
            ),
        );
    }

    #[test]
    fn test_advisory_serving_dataset_manifest_schema_version_required() {
        let resolved = _resolved_artifact_with_feature_schema(Some("c".repeat(64)));

        let mut missing = _valid_advisory_metadata();
        missing.dataset_manifest_schema_version = None;
        assert_eq!(
            validate_registry_advisory_serving_metadata(&missing, Some(&resolved)),
            Err(
                RegistryAdvisoryServingValidationError::SchemaVersionMismatch {
                    field: "dataset_manifest_schema_version",
                    expected: PIT_DATASET_MANIFEST_SCHEMA_VERSION,
                    actual: None,
                },
            ),
        );

        let mut wrong = _valid_advisory_metadata();
        wrong.dataset_manifest_schema_version = Some("dataset_manifest_v0".into());
        assert_eq!(
            validate_registry_advisory_serving_metadata(&wrong, Some(&resolved)),
            Err(
                RegistryAdvisoryServingValidationError::SchemaVersionMismatch {
                    field: "dataset_manifest_schema_version",
                    expected: PIT_DATASET_MANIFEST_SCHEMA_VERSION,
                    actual: Some("dataset_manifest_v0".into()),
                },
            ),
        );
    }

    #[test]
    fn test_advisory_serving_hash_fields_must_be_sha256_hex() {
        let resolved = _resolved_artifact_with_feature_schema(Some("c".repeat(64)));
        let mut metadata = _valid_advisory_metadata();
        metadata.leakage_report_hash = Some("leakage_report_hash_v1".into());

        assert_eq!(
            validate_registry_advisory_serving_metadata(&metadata, Some(&resolved)),
            Err(RegistryAdvisoryServingValidationError::MalformedHashField {
                field: "leakage_report_hash",
                actual: "leakage_report_hash_v1".into(),
            },),
        );
    }

    #[test]
    fn test_advisory_serving_artifact_hashes_must_be_sha256_hex() {
        let resolved = _resolved_artifact_with_feature_schema(Some("c".repeat(64)));
        let mut metadata = _valid_advisory_metadata();
        metadata.artifact_hashes = Some(RegistryQuantileTrioMetadata {
            q10: Some("2".repeat(64)),
            q50: Some("not_a_hash".into()),
            q90: Some("4".repeat(64)),
        });

        assert_eq!(
            validate_registry_advisory_serving_metadata(&metadata, Some(&resolved)),
            Err(RegistryAdvisoryServingValidationError::MalformedHashField {
                field: "artifact_hashes",
                actual: "not_a_hash".into(),
            },),
        );
    }

    #[test]
    fn test_advisory_serving_contract_hash_malformed_or_mismatch_fails() {
        let resolved = _resolved_artifact_with_feature_schema(Some("c".repeat(64)));

        let mut malformed = _valid_advisory_metadata();
        malformed.contract_hash = Some("not_a_hash".into());
        assert_eq!(
            validate_registry_advisory_serving_metadata(&malformed, Some(&resolved)),
            Err(RegistryAdvisoryServingValidationError::MalformedHashField {
                field: "contract_hash",
                actual: "not_a_hash".into(),
            },),
        );

        let mut mismatch = _valid_advisory_metadata();
        mismatch.contract_hash = Some("0".repeat(64));
        assert_eq!(
            validate_registry_advisory_serving_metadata(&mismatch, Some(&resolved)),
            Err(
                RegistryAdvisoryServingValidationError::ContractHashMismatch {
                    expected: "481ac63e09b545238027e971a6716b6c5f5dcb04161617fc43ae9be1819f403d"
                        .into(),
                    actual: "0".repeat(64),
                },
            ),
        );
    }

    #[test]
    fn test_advisory_serving_empty_policy_field_fails() {
        let resolved = _resolved_artifact_with_feature_schema(Some("c".repeat(64)));
        let mut metadata = _valid_advisory_metadata();
        metadata.units = Some("   ".into());

        assert_eq!(
            validate_registry_advisory_serving_metadata(&metadata, Some(&resolved)),
            Err(RegistryAdvisoryServingValidationError::MissingField { field: "units" }),
        );
    }

    #[test]
    fn test_current_symlink_helper_is_filename_only_not_authority() {
        // The helper remains a pure filename formatter. Advisory serving
        // authority comes only from validated registry metadata.
        // helper 只格式化檔名；advisory serving 權威只來自已驗證 metadata。
        let slot = ModelSlot::new("ma_crossover", "demo", "q50");
        let name = symlink_filename(&slot, "v1");
        assert_eq!(name, "edge_predictor_demo_ma_crossover_q50_v1_current.onnx");

        let resolved = _resolved_artifact_with_feature_schema(Some("c".repeat(64)));
        let mut metadata = _valid_advisory_metadata();
        metadata.symlink_authority = Some(false);
        assert!(validate_registry_advisory_serving_metadata(&metadata, Some(&resolved)).is_ok());

        metadata.symlink_authority = Some(true);
        assert!(matches!(
            validate_registry_advisory_serving_metadata(&metadata, Some(&resolved)),
            Err(
                RegistryAdvisoryServingValidationError::BooleanFieldMismatch {
                    field: "symlink_authority",
                    expected: false,
                    actual: Some(true),
                }
            )
        ));
    }

    #[test]
    fn test_slot_display_via_debug() {
        // Debug output is used in trace/log; spot-check key fields appear.
        // Debug 輸出用於 trace/log；抽檢關鍵欄位出現。
        let slot = ModelSlot::new("funding_arb", "live", "q90");
        let s = format!("{:?}", slot);
        assert!(s.contains("funding_arb"));
        assert!(s.contains("live"));
        assert!(s.contains("q90"));
    }

    // ───── L2-9: feature_schema_hash validation ─────────────────────
    // INFRA-PREBUILD-1 audit L2-9 (2026-04-23): ResolvedArtifact must carry
    // feature_schema_hash so Phase 3+ callers can detect feature-schema drift
    // between training and runtime before loading the ONNX. Missing → panic
    // in session.run at inference time.
    // L2-9 審計：ResolvedArtifact 必須帶 feature_schema_hash，Phase 3+ caller
    // 載入 ONNX 前偵測 schema 漂移；無此驗證 → runtime session.run panic。

    fn _make_resolved(feature_schema_hash: Option<String>) -> ResolvedArtifact {
        // Helper: build ResolvedArtifact with only feature_schema_hash varying.
        // 測試 helper：固定其他欄位、只變動 feature_schema_hash。
        ResolvedArtifact {
            id: 7,
            artifact_path: "/tmp/x.onnx".into(),
            canary_status: "production".into(),
            verdict: "should_ship".into(),
            train_date: "2026-04-23".into(),
            quantile: REGISTRY_Q50.into(),
            artifact_sha256: Some("sha".into()),
            feature_schema_hash,
        }
    }

    #[test]
    fn test_resolved_artifact_has_schema_hash_field() {
        // Field existence + struct literal compile — drift guard against
        // accidental field removal that would silently disable L2-9.
        // 欄位存在 + struct literal 可編譯；守意外移除欄位後 L2-9 失效。
        let a = _make_resolved(Some("hash_v1".into()));
        assert_eq!(a.feature_schema_hash.as_deref(), Some("hash_v1"));
        let b = _make_resolved(None);
        assert_eq!(b.feature_schema_hash, None);
    }

    #[test]
    fn test_validate_schema_hash_match_ok() {
        // Happy path: registry hash == engine hash → Ok(()).
        // 快樂路徑：registry hash 等於 engine hash → Ok(())。
        let resolved = _make_resolved(Some("feat_hash_v1".into()));
        assert!(validate_schema_hash(&resolved, "feat_hash_v1").is_ok());
    }

    #[test]
    fn test_validate_schema_hash_none_ok_with_warn() {
        // Legacy row (feature_schema_hash NULL pre-backfill) → Ok(()) with
        // warn log. Preserves backward compat so early rows don't lock out
        // the Phase 3+ cut-over.
        // Legacy row（feature_schema_hash NULL）→ Ok + warn；保向後相容。
        let resolved = _make_resolved(None);
        assert!(validate_schema_hash(&resolved, "feat_hash_v1").is_ok());
    }

    #[test]
    fn test_validate_schema_hash_mismatch_err() {
        // Mismatch → Err with both hashes populated for logging.
        // 不匹配 → Err，兩邊 hash 都帶回供 log。
        let resolved = _make_resolved(Some("registry_hash_old".into()));
        let result = validate_schema_hash(&resolved, "engine_hash_new");
        assert!(result.is_err());
        let err = result.unwrap_err();
        assert_eq!(err.registry, "registry_hash_old");
        assert_eq!(err.engine, "engine_hash_new");
    }

    #[test]
    fn test_schema_hash_mismatch_display() {
        // Display trait must include both hashes so log output is actionable
        // — operator needs to see which hash rolled forward / rolled back.
        // Display 必含兩邊 hash；operator log 才能診斷哪邊動了。
        let err = SchemaHashMismatch {
            registry: "abc123".into(),
            engine: "def456".into(),
        };
        let s = format!("{}", err);
        assert!(s.contains("abc123"), "display missing registry hash: {s}");
        assert!(s.contains("def456"), "display missing engine hash: {s}");
        // std::error::Error trait implementation must compile.
        // std::error::Error trait 需能編譯。
        let _: &dyn std::error::Error = &err;
    }
}
