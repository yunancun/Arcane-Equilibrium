//! ARCH-RC1 1C-2-D: One-shot migration from legacy operator_risk_config.json
//! to the new risk_config.toml schema.
//! ARCH-RC1 1C-2-D：從舊版 operator_risk_config.json 一次性遷移到新
//! risk_config.toml schema。
//!
//! MODULE_NOTE (EN): Runs once at engine startup from `load_unified_configs`.
//!   - If risk_config.toml already exists → skip (TOML is authoritative).
//!   - If operator_risk_config.json is missing → skip (nothing to migrate).
//!   - Otherwise: parse JSON, map the ~10 well-known fields into a RiskConfig
//!     built from RiskConfig::default(), validate, save_toml, then rename the
//!     legacy JSON to `.legacy` to prevent re-running.
//!   - Unknown JSON fields are ignored (non-fatal) so a partial schema still
//!     produces a valid TOML.
//!   - `max_cost_edge_ratio` is cross-Config (belongs to BudgetConfig); we log
//!     it and leave it for operator to re-apply via `patch_budget_config`.
//! MODULE_NOTE (中)：引擎啟動時在 load_unified_configs 中執行一次。
//!   - 若 risk_config.toml 已存在 → 跳過（TOML 是權威來源）。
//!   - 若 operator_risk_config.json 不存在 → 跳過（無需遷移）。
//!   - 否則：解析 JSON，將 ~10 個已知欄位映射到 RiskConfig::default() 上，
//!     驗證，save_toml，再把舊 JSON rename 為 `.legacy` 防止重跑。
//!   - 未知欄位忽略（非致命），讓部分 schema 仍能產出合法 TOML。
//!   - `max_cost_edge_ratio` 跨 Config（屬 BudgetConfig），log 出來讓
//!     operator 透過 `patch_budget_config` 重新套用。

use super::budget_config::BudgetConfig;
use super::io::save_toml;
use super::RiskConfig;
use std::path::{Path, PathBuf};
use tracing::{info, warn};

/// Outcome of a single migration attempt.
/// 單次遷移嘗試的結果。
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum MigrationOutcome {
    /// TOML already exists — migration skipped.
    /// TOML 已存在 — 跳過遷移。
    TomlExists,
    /// Legacy JSON not present — nothing to migrate.
    /// 舊 JSON 不存在 — 無需遷移。
    NoLegacyJson,
    /// Successfully migrated; path to the produced TOML file.
    /// 成功遷移；產出的 TOML 檔案路徑。
    Migrated(PathBuf),
}

/// Migrate `<dir>/operator_risk_config.json` → `<dir>/risk_config.toml` if the
/// TOML does not yet exist. Returns the outcome or a human-readable error.
///
/// 若 TOML 尚未存在，將 `<dir>/operator_risk_config.json` 遷移到
/// `<dir>/risk_config.toml`。回傳結果或可讀錯誤訊息。
pub fn migrate_legacy_risk_json_if_needed(dir: &Path) -> Result<MigrationOutcome, String> {
    let toml_path = dir.join("risk_config.toml");
    let json_path = dir.join("operator_risk_config.json");

    if toml_path.exists() {
        return Ok(MigrationOutcome::TomlExists);
    }
    if !json_path.exists() {
        return Ok(MigrationOutcome::NoLegacyJson);
    }

    let raw = std::fs::read_to_string(&json_path)
        .map_err(|e| format!("read legacy json '{}': {}", json_path.display(), e))?;
    let parsed: serde_json::Value = serde_json::from_str(&raw)
        .map_err(|e| format!("parse legacy json '{}': {}", json_path.display(), e))?;

    let mut rc = RiskConfig::default();
    let mut mapped_fields: Vec<&'static str> = Vec::new();

    if let Some(g) = parsed.get("global_config").and_then(|v| v.as_object()) {
        if let Some(v) = g.get("max_stop_loss_pct").and_then(|v| v.as_f64()) {
            rc.limits.stop_loss_max_pct = v;
            mapped_fields.push("limits.stop_loss_max_pct");
        }
        if let Some(v) = g.get("max_take_profit_pct").and_then(|v| v.as_f64()) {
            rc.limits.take_profit_max_pct = v;
            mapped_fields.push("limits.take_profit_max_pct");
        }
        if let Some(v) = g.get("tp_enabled").and_then(|v| v.as_bool()) {
            rc.limits.take_profit_enforced = v;
            mapped_fields.push("limits.take_profit_enforced");
        }
        if let Some(v) = g.get("max_single_position_pct").and_then(|v| v.as_f64()) {
            rc.limits.position_size_max_pct = v;
            mapped_fields.push("limits.position_size_max_pct");
        }
        if let Some(v) = g.get("max_total_exposure_pct").and_then(|v| v.as_f64()) {
            rc.limits.total_exposure_max_pct = v;
            mapped_fields.push("limits.total_exposure_max_pct");
        }
        if let Some(v) = g
            .get("max_correlated_exposure_pct")
            .and_then(|v| v.as_f64())
        {
            rc.limits.correlated_exposure_max_pct = v;
            mapped_fields.push("limits.correlated_exposure_max_pct");
        }
        if let Some(v) = g.get("max_leverage").and_then(|v| v.as_f64()) {
            rc.limits.leverage_max = v;
            mapped_fields.push("limits.leverage_max");
        }
        if let Some(v) = g.get("max_session_drawdown_pct").and_then(|v| v.as_f64()) {
            rc.limits.session_drawdown_max_pct = v;
            mapped_fields.push("limits.session_drawdown_max_pct");
        }
        if let Some(v) = g.get("max_daily_loss_pct").and_then(|v| v.as_f64()) {
            rc.limits.daily_loss_max_pct = v;
            mapped_fields.push("limits.daily_loss_max_pct");
        }
        if let Some(v) = g
            .get("consecutive_loss_cooldown_count")
            .and_then(|v| v.as_u64())
        {
            rc.limits.consec_loss_cooldown_count = v as u32;
            mapped_fields.push("limits.consec_loss_cooldown_count");
        }
        if let Some(v) = g
            .get("consecutive_loss_cooldown_minutes")
            .and_then(|v| v.as_f64())
        {
            rc.limits.consec_loss_cooldown_min = v.round().max(0.0) as u32;
            mapped_fields.push("limits.consec_loss_cooldown_min");
        }
        if let Some(v) = g.get("max_holding_hours").and_then(|v| v.as_f64()) {
            rc.limits.holding_hours_max = v;
            mapped_fields.push("limits.holding_hours_max");
        }
        if let Some(arr) = g.get("allowed_categories").and_then(|v| v.as_array()) {
            let cats: Vec<String> = arr
                .iter()
                .filter_map(|c| c.as_str().map(|s| s.to_string()))
                .collect();
            if !cats.is_empty() {
                rc.limits.allowed_categories = cats;
                mapped_fields.push("limits.allowed_categories");
            }
        }
        if let Some(v) = g.get("preferred_margin_mode").and_then(|v| v.as_str()) {
            rc.limits.margin_mode = v.to_string();
            mapped_fields.push("limits.margin_mode");
        }
        if let Some(v) = g.get("preferred_position_mode").and_then(|v| v.as_str()) {
            rc.limits.position_mode = v.to_string();
            mapped_fields.push("limits.position_mode");
        }
        // Cross-Config: cost_edge_max_ratio lives on BudgetConfig.attention_tax.
        // Report it so the operator can re-apply via patch_budget_config.
        // 跨 Config：cost_edge_max_ratio 屬 BudgetConfig.attention_tax，
        // 回報讓 operator 經 patch_budget_config 重新套用。
        if let Some(v) = g.get("max_cost_edge_ratio").and_then(|v| v.as_f64()) {
            warn!(
                value = v,
                "legacy max_cost_edge_ratio belongs to BudgetConfig.attention_tax.cost_edge_max_ratio — re-apply via patch_budget_config / 舊 max_cost_edge_ratio 屬 BudgetConfig，請經 patch_budget_config 重新套用"
            );
        }
    }

    rc.validate()
        .map_err(|e| format!("migrated RiskConfig failed validate: {}", e))?;

    save_toml(&toml_path, &rc).map_err(|e| format!("save {}: {}", toml_path.display(), e))?;

    let legacy_path = json_path.with_extension("json.legacy");
    if let Err(e) = std::fs::rename(&json_path, &legacy_path) {
        warn!(
            from = %json_path.display(),
            to = %legacy_path.display(),
            error = %e,
            "legacy json rename failed (TOML was written successfully) / 舊 JSON 改名失敗（TOML 已寫成功）"
        );
    }

    info!(
        toml = %toml_path.display(),
        legacy = %legacy_path.display(),
        mapped = mapped_fields.len(),
        "ARCH-RC1 1C-2-D legacy JSON → TOML migration complete / 舊 JSON → TOML 遷移完成"
    );

    Ok(MigrationOutcome::Migrated(toml_path))
}

// ---------------------------------------------------------------------------
// MICRO-PROFIT-FIX-1 (2026-04-17): in-memory BudgetConfig sanitisation for
// persisted snapshots whose `cost_edge_max_ratio` predates the range shrink
// from [0, 100] → [0, 10]. Runs after TOML parse, before validate — any value
// beyond the new ceiling is clamped to the default (0.2) with a warn! so the
// engine starts instead of fail-closing on legacy state.
//
// MICRO-PROFIT-FIX-1：對歷史 snapshot 的 BudgetConfig 做一次性記憶體清洗 ——
// 在 TOML parse 之後、validate 之前執行，把超範圍（> 10）的 cost_edge_max_ratio
// clamp 回 default（0.2）並 warn，避免舊 state 讓引擎 fail-close 起不來。
// ---------------------------------------------------------------------------

/// Clamp out-of-range legacy BudgetConfig values back into the current spec.
/// Returns the list of fields that were rewritten (empty = no-op).
/// 把超範圍的舊 BudgetConfig 值 clamp 回當前 spec。回傳被改寫的欄位清單。
pub fn sanitize_legacy_budget_config(cfg: &mut BudgetConfig) -> Vec<String> {
    let mut rewritten: Vec<String> = Vec::new();
    // MICRO-PROFIT-FIX-1: old snapshots may hold cost_edge_max_ratio up to 100.0.
    // Clamp any value > 10.0 (new ceiling) back to the fresh default.
    // MICRO-PROFIT-FIX-1：舊 snapshot 可能持有 100.0 的 cost_edge_max_ratio；> 10 者 clamp 回 default。
    if cfg.attention_tax.cost_edge_max_ratio > 10.0 {
        let old = cfg.attention_tax.cost_edge_max_ratio;
        let new_default = BudgetConfig::default().attention_tax.cost_edge_max_ratio;
        warn!(
            old = old,
            new = new_default,
            "MICRO-PROFIT-FIX-1 legacy cost_edge_max_ratio {old:.2} > 10.0 clamped to default {new_default:.2} / 舊 cost_edge_max_ratio 超範圍，已遷回 default"
        );
        cfg.attention_tax.cost_edge_max_ratio = new_default;
        rewritten.push("attention_tax.cost_edge_max_ratio".to_string());
    }
    rewritten
}

#[cfg(test)]
mod tests {
    use super::*;

    fn write_json(dir: &Path, body: &str) {
        std::fs::write(dir.join("operator_risk_config.json"), body).unwrap();
    }

    #[test]
    fn test_skip_when_toml_exists() {
        let td = tempfile::tempdir().unwrap();
        std::fs::write(td.path().join("risk_config.toml"), "# existing").unwrap();
        write_json(td.path(), r#"{"global_config":{"max_leverage":99.0}}"#);
        let out = migrate_legacy_risk_json_if_needed(td.path()).unwrap();
        assert_eq!(out, MigrationOutcome::TomlExists);
        // Legacy json must not be renamed.
        assert!(td.path().join("operator_risk_config.json").exists());
    }

    #[test]
    fn test_skip_when_no_legacy_json() {
        let td = tempfile::tempdir().unwrap();
        let out = migrate_legacy_risk_json_if_needed(td.path()).unwrap();
        assert_eq!(out, MigrationOutcome::NoLegacyJson);
    }

    #[test]
    fn test_migrates_and_maps_known_fields() {
        let td = tempfile::tempdir().unwrap();
        write_json(
            td.path(),
            r#"{"global_config":{
                "max_stop_loss_pct": 7.5,
                "max_leverage": 11.0,
                "max_total_exposure_pct": 80.0,
                "allowed_categories": ["linear", "spot"],
                "max_cost_edge_ratio": 0.8
            }}"#,
        );
        let out = migrate_legacy_risk_json_if_needed(td.path()).unwrap();
        let toml_path = match out {
            MigrationOutcome::Migrated(p) => p,
            other => panic!("expected Migrated, got {other:?}"),
        };
        assert!(toml_path.exists());
        // Legacy json renamed.
        assert!(!td.path().join("operator_risk_config.json").exists());
        assert!(td.path().join("operator_risk_config.json.legacy").exists());
        // Reload and verify values.
        let body = std::fs::read_to_string(&toml_path).unwrap();
        let rc: RiskConfig = toml::from_str(&body).unwrap();
        assert!((rc.limits.stop_loss_max_pct - 7.5).abs() < f64::EPSILON);
        assert!((rc.limits.leverage_max - 11.0).abs() < f64::EPSILON);
        assert!((rc.limits.total_exposure_max_pct - 80.0).abs() < f64::EPSILON);
        assert_eq!(rc.limits.allowed_categories, vec!["linear", "spot"]);
    }

    #[test]
    fn test_invalid_json_returns_error() {
        let td = tempfile::tempdir().unwrap();
        write_json(td.path(), "{not valid json");
        let out = migrate_legacy_risk_json_if_needed(td.path());
        assert!(out.is_err());
        // Legacy file untouched, no TOML produced.
        assert!(td.path().join("operator_risk_config.json").exists());
        assert!(!td.path().join("risk_config.toml").exists());
    }

    #[test]
    fn test_partial_schema_still_valid() {
        // JSON with only 1 known field — rest come from RiskConfig::default().
        // 只有 1 個已知欄位 — 其餘用 default。
        let td = tempfile::tempdir().unwrap();
        write_json(td.path(), r#"{"global_config":{"max_leverage": 15.0}}"#);
        let out = migrate_legacy_risk_json_if_needed(td.path()).unwrap();
        assert!(matches!(out, MigrationOutcome::Migrated(_)));
        let rc: RiskConfig =
            toml::from_str(&std::fs::read_to_string(td.path().join("risk_config.toml")).unwrap())
                .unwrap();
        assert!((rc.limits.leverage_max - 15.0).abs() < f64::EPSILON);
    }

    #[test]
    fn test_legacy_high_cost_edge_max_ratio_migrated_to_default() {
        // MICRO-PROFIT-FIX-1: persisted snapshot may hold 100.0; sanitizer must
        // rewrite to default (0.2) and report the field, so subsequent validate()
        // succeeds.
        // MICRO-PROFIT-FIX-1：舊 persisted 100.0 必須被 sanitizer 遷回 default(0.2)，
        // 讓後續 validate 通過。
        let mut cfg = BudgetConfig::default();
        cfg.attention_tax.cost_edge_max_ratio = 100.0;
        // Pre-condition: raw legacy value would fail validation.
        assert!(cfg.validate().is_err());
        let rewritten = sanitize_legacy_budget_config(&mut cfg);
        assert_eq!(rewritten, vec!["attention_tax.cost_edge_max_ratio"]);
        assert!((cfg.attention_tax.cost_edge_max_ratio - 0.2).abs() < f64::EPSILON);
        // Post-sanitize: validate must pass.
        assert!(cfg.validate().is_ok());
    }

    #[test]
    fn test_sanitize_noop_when_in_range() {
        // MICRO-PROFIT-FIX-1: in-range value must NOT be rewritten.
        // MICRO-PROFIT-FIX-1：範圍內的值不得被改寫。
        let mut cfg = BudgetConfig::default();
        cfg.attention_tax.cost_edge_max_ratio = 0.5;
        let rewritten = sanitize_legacy_budget_config(&mut cfg);
        assert!(rewritten.is_empty());
        assert!((cfg.attention_tax.cost_edge_max_ratio - 0.5).abs() < f64::EPSILON);
    }
}
