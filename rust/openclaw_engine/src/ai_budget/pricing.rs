//! Pricing table loader — replaces hardcoded const map (4-17 / FA GAP-10).
//! 定價表載入器 — 取代硬編碼 const map（4-17 / FA GAP-10）。
//!
//! MODULE_NOTE (EN): Loads `settings/ai_pricing.yaml` into a flat
//! `model_name -> ModelPricing` map. Fail-closed on file missing,
//! parse error, or inactive model. Path resolution order:
//!   1. env `OPENCLAW_PRICING_PATH`
//!   2. `settings/ai_pricing.yaml` relative to CWD
//!   3. error
//!
//! MODULE_NOTE (中): 把 `settings/ai_pricing.yaml` 載入為扁平
//! `model_name -> ModelPricing` 映射。檔案缺失/解析錯誤/inactive 模型
//! 一律 fail-closed。路徑解析順序：
//!   1. env `OPENCLAW_PRICING_PATH`
//!   2. CWD 相對 `settings/ai_pricing.yaml`
//!   3. 報錯

use serde::Deserialize;
use std::collections::HashMap;
use std::path::{Path, PathBuf};

/// Pricing for a single model (USD per million tokens).
/// 單一模型定價（每百萬 tokens 美元）。
#[derive(Debug, Clone, Deserialize)]
pub struct ModelPricing {
    pub input_per_mtok: f64,
    pub output_per_mtok: f64,
    pub active: bool,
}

/// Flat pricing table keyed by model name.
/// 以 model name 為鍵的扁平定價表。
#[derive(Debug, Clone, Default)]
pub struct PricingTable {
    map: HashMap<String, ModelPricing>,
}

impl PricingTable {
    /// Load pricing from a YAML file. Fail-closed on any IO/parse error.
    /// 從 YAML 檔載入定價。任何 IO/parse 錯誤一律 fail-closed。
    ///
    /// YAML schema is two-level: `provider -> model_name -> ModelPricing`.
    /// We flatten provider away — only the model_name key matters at lookup time.
    /// YAML 結構為兩層：`provider -> model_name -> ModelPricing`。
    /// 載入時扁平化掉 provider — lookup 只認 model_name。
    pub fn load_from_yaml(path: impl AsRef<Path>) -> Result<Self, String> {
        let path_ref = path.as_ref();
        let raw = std::fs::read_to_string(path_ref)
            .map_err(|e| format!("pricing yaml read failed ({}): {}", path_ref.display(), e))?;
        let nested: HashMap<String, HashMap<String, ModelPricing>> = serde_yaml::from_str(&raw)
            .map_err(|e| format!("pricing yaml parse failed ({}): {}", path_ref.display(), e))?;
        let mut map: HashMap<String, ModelPricing> = HashMap::new();
        for (_provider, models) in nested {
            for (model_name, pricing) in models {
                if !pricing.input_per_mtok.is_finite() || !pricing.output_per_mtok.is_finite() {
                    return Err(format!(
                        "pricing yaml: non-finite rate for model {}",
                        model_name
                    ));
                }
                if pricing.input_per_mtok < 0.0 || pricing.output_per_mtok < 0.0 {
                    return Err(format!(
                        "pricing yaml: negative rate for model {}",
                        model_name
                    ));
                }
                map.insert(model_name, pricing);
            }
        }
        Ok(Self { map })
    }

    /// Lookup pricing. Returns None if model unknown OR inactive (fail-closed).
    /// 查詢定價。模型未知或 inactive 時返回 None（fail-closed）。
    pub fn lookup(&self, model: &str) -> Option<&ModelPricing> {
        let p = self.map.get(model)?;
        if p.active {
            Some(p)
        } else {
            None
        }
    }

    /// Compute USD cost for given token counts. None on missing/inactive model.
    /// 給定 tokens 算 USD 成本。模型缺失/inactive 時返回 None。
    pub fn compute_cost(&self, model: &str, tokens_in: u32, tokens_out: u32) -> Option<f64> {
        let p = self.lookup(model)?;
        Some(
            (tokens_in as f64 / 1_000_000.0) * p.input_per_mtok
                + (tokens_out as f64 / 1_000_000.0) * p.output_per_mtok,
        )
    }

    /// Number of active models. Used for sanity check at boot.
    /// 啟用模型數量。供啟動時 sanity check 用。
    pub fn active_count(&self) -> usize {
        self.map.values().filter(|p| p.active).count()
    }

    /// Total models in table (active + inactive). For diagnostics.
    /// 表內模型總數（active + inactive）。供診斷用。
    pub fn total_count(&self) -> usize {
        self.map.len()
    }

    /// Test-only constructor from a raw map. Skips YAML I/O for unit tests.
    /// 測試專用：直接從 map 構造，跳過 YAML I/O。
    #[cfg(test)]
    pub(crate) fn from_map_for_test(map: HashMap<String, ModelPricing>) -> Self {
        Self { map }
    }
}

/// Resolve the default pricing yaml path.
/// 解析預設定價 yaml 路徑。
fn default_path() -> PathBuf {
    if let Ok(env) = std::env::var("OPENCLAW_PRICING_PATH") {
        return PathBuf::from(env);
    }
    PathBuf::from("settings/ai_pricing.yaml")
}

/// Load default pricing table. Fail-closed on missing/parse error.
/// 載入預設定價表。檔案缺失/解析錯誤一律 fail-closed。
pub fn load_default() -> Result<PricingTable, String> {
    let path = default_path();
    PricingTable::load_from_yaml(&path)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use tempfile::NamedTempFile;

    fn write_yaml(content: &str) -> NamedTempFile {
        let mut f = NamedTempFile::new().expect("tempfile");
        f.write_all(content.as_bytes()).expect("write");
        f
    }

    /// Test 1: valid YAML loads successfully.
    /// 測試 1：合法 YAML 載入成功。
    #[test]
    fn test_load_from_yaml_valid() {
        let yaml = r#"
anthropic:
  claude-sonnet-4-5:
    input_per_mtok: 3.0
    output_per_mtok: 15.0
    active: true
local:
  qwen-3.5-9b:
    input_per_mtok: 0.0
    output_per_mtok: 0.0
    active: true
"#;
        let f = write_yaml(yaml);
        let table = PricingTable::load_from_yaml(f.path()).expect("load");
        assert_eq!(table.total_count(), 2);
        assert_eq!(table.active_count(), 2);
    }

    /// Test 2: missing file is fail-closed.
    /// 測試 2：檔案缺失 fail-closed。
    #[test]
    fn test_load_from_yaml_missing_file_fail_closed() {
        let err = PricingTable::load_from_yaml("/nonexistent/path/__no_such__.yaml").unwrap_err();
        assert!(err.contains("read failed"), "got: {err}");
    }

    /// Test 3: malformed YAML is fail-closed.
    /// 測試 3：YAML 格式錯誤 fail-closed。
    #[test]
    fn test_load_from_yaml_malformed_fail_closed() {
        let yaml = "anthropic:\n  claude-x:\n    input_per_mtok: not-a-number\n    active: true\n";
        let f = write_yaml(yaml);
        let err = PricingTable::load_from_yaml(f.path()).unwrap_err();
        assert!(err.contains("parse failed"), "got: {err}");
    }

    /// Test 4: lookup returns active model pricing.
    /// 測試 4：lookup 返回 active 模型的定價。
    #[test]
    fn test_lookup_active_model_returns_pricing() {
        let yaml = r#"
anthropic:
  claude-sonnet-4-5:
    input_per_mtok: 3.0
    output_per_mtok: 15.0
    active: true
"#;
        let f = write_yaml(yaml);
        let table = PricingTable::load_from_yaml(f.path()).unwrap();
        let p = table.lookup("claude-sonnet-4-5").unwrap();
        assert_eq!(p.input_per_mtok, 3.0);
        assert_eq!(p.output_per_mtok, 15.0);
    }

    /// Test 5: inactive model returns None (fail-closed).
    /// 測試 5：inactive 模型返回 None（fail-closed）。
    #[test]
    fn test_lookup_inactive_model_returns_none() {
        let yaml = r#"
anthropic:
  retired-model:
    input_per_mtok: 5.0
    output_per_mtok: 25.0
    active: false
"#;
        let f = write_yaml(yaml);
        let table = PricingTable::load_from_yaml(f.path()).unwrap();
        assert!(table.lookup("retired-model").is_none());
        assert_eq!(table.active_count(), 0);
        assert_eq!(table.total_count(), 1);
    }

    /// Test 6: cost calculation correctness.
    /// 測試 6：成本計算正確性。
    /// 1000 tokens in × $3/MTok + 500 tokens out × $15/MTok = 0.003 + 0.0075 = 0.0105
    #[test]
    fn test_compute_cost_calculation_correct() {
        let yaml = r#"
anthropic:
  claude-sonnet-4-5:
    input_per_mtok: 3.0
    output_per_mtok: 15.0
    active: true
"#;
        let f = write_yaml(yaml);
        let table = PricingTable::load_from_yaml(f.path()).unwrap();
        let cost = table.compute_cost("claude-sonnet-4-5", 1_000, 500).unwrap();
        assert!((cost - 0.0105).abs() < 1e-9, "cost = {cost}");
    }

    /// Test 7: active_count excludes inactive entries.
    /// 測試 7：active_count 排除 inactive 條目。
    #[test]
    fn test_active_count_excludes_inactive() {
        let yaml = r#"
anthropic:
  active1:
    input_per_mtok: 1.0
    output_per_mtok: 2.0
    active: true
  inactive1:
    input_per_mtok: 1.0
    output_per_mtok: 2.0
    active: false
  active2:
    input_per_mtok: 1.0
    output_per_mtok: 2.0
    active: true
"#;
        let f = write_yaml(yaml);
        let table = PricingTable::load_from_yaml(f.path()).unwrap();
        assert_eq!(table.total_count(), 3);
        assert_eq!(table.active_count(), 2);
    }

    /// Test 8: load_default reads the real settings/ai_pricing.yaml when present.
    /// 測試 8：load_default 在 settings/ai_pricing.yaml 存在時讀取真實檔案。
    /// Skipped if path not present (e.g., running from a different cwd).
    #[test]
    fn test_load_default_uses_repo_settings_path() {
        // This test runs from the workspace root, so settings/ai_pricing.yaml should resolve.
        // 從 workspace root 執行，settings/ai_pricing.yaml 應可解析。
        let path = default_path();
        if !path.exists() {
            eprintln!("skipping: {} not present", path.display());
            return;
        }
        let table = load_default().expect("load_default");
        assert!(
            table.active_count() >= 5,
            "expected at least 5 active models, got {}",
            table.active_count()
        );
        // Spot-check a known model
        // 抽查一個已知模型
        assert!(table.lookup("claude-sonnet-4-5").is_some());
    }

    /// Test 9: negative rate is rejected at load time.
    /// 測試 9：載入時拒絕負費率。
    #[test]
    fn test_load_rejects_negative_rate() {
        let yaml = r#"
anthropic:
  bad:
    input_per_mtok: -1.0
    output_per_mtok: 5.0
    active: true
"#;
        let f = write_yaml(yaml);
        let err = PricingTable::load_from_yaml(f.path()).unwrap_err();
        assert!(err.contains("negative rate"), "got: {err}");
    }
}
