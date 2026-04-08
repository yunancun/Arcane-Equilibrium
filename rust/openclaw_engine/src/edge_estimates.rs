//! PH5-WIRE-1: JS shrunk realized-edge estimate cache for cost_gate.
//! PH5-WIRE-1：用於成本門的 JS 收縮實現邊際估計緩存。
//!
//! MODULE_NOTE (EN): Loads the JSON snapshot written by james_stein_estimator.py
//!   (settings/edge_estimates.json). Provides O(1) lookup by (strategy, symbol).
//!   If the file is absent (cold-start), returns an empty set — callers fall back
//!   to ATR×conf×0.2. Designed to be refreshed via set_edge_estimates() after
//!   Python re-runs the estimator.
//! MODULE_NOTE (中): 加載 james_stein_estimator.py 寫出的 JSON 快照
//!   (settings/edge_estimates.json)。提供 (策略, 幣種) O(1) 查詢。
//!   文件不存在時（冷啟動）返回空集——調用者回退到 ATR×conf×0.2。
//!   Python 重新運行估計器後可通過 set_edge_estimates() 刷新。

use std::collections::HashMap;
use std::path::Path;

/// Shrunk realized-edge estimates per (strategy, symbol) cell.
/// 每 (策略, 幣種) 格子的收縮實現邊際估計。
#[derive(Debug, Clone, Default)]
pub struct EdgeEstimates {
    /// Maps "strategy::symbol" → shrunk_bps (James-Stein shrunk realized edge).
    /// 映射 "策略::幣種" → 收縮 bps（James-Stein 收縮實現邊際）。
    data: HashMap<String, f64>,
    /// Grand mean across all cells at snapshot time.
    /// 快照時所有格子的全域均值。
    grand_mean_bps: f64,
    /// Number of cells with estimates.
    /// 有估計的格子數。
    n_cells: usize,
}

impl EdgeEstimates {
    /// Create an empty (cold-start) estimates set.
    /// 創建空（冷啟動）估計集。
    pub fn empty() -> Self {
        Self::default()
    }

    /// Load from the JSON snapshot written by james_stein_estimator.py.
    /// Format: {"strategy::symbol": {"shrunk_bps": X, "n": N, ...}, "_meta": {...}}
    /// Returns None if file not found or JSON invalid — caller uses empty fallback.
    /// 從 james_stein_estimator.py 寫出的 JSON 快照加載。
    /// 文件不存在或 JSON 無效時返回 None，調用者使用空回退。
    pub fn load_from_file(path: impl AsRef<Path>) -> Option<Self> {
        let path = path.as_ref();
        let content = std::fs::read_to_string(path).ok()?;
        let parsed: serde_json::Value = serde_json::from_str(&content).ok()?;
        let obj = parsed.as_object()?;

        let mut data = HashMap::new();
        let mut grand_mean_bps = 0.0;

        if let Some(meta) = obj.get("_meta").and_then(|v| v.as_object()) {
            grand_mean_bps = meta
                .get("grand_mean_bps")
                .and_then(|v| v.as_f64())
                .unwrap_or(0.0);
        }

        for (key, val) in obj {
            if key.starts_with('_') {
                continue;
            }
            if let Some(bps) = val.get("shrunk_bps").and_then(|v| v.as_f64()) {
                data.insert(key.clone(), bps);
            }
        }

        let n_cells = data.len();
        tracing::info!(
            n_cells,
            grand_mean_bps,
            path = %path.display(),
            "PH5-WIRE-1: edge estimates loaded / 邊際估計已加載"
        );

        Some(Self { data, grand_mean_bps, n_cells })
    }

    /// Load from OPENCLAW_EDGE_SNAPSHOT env var or default path.
    /// Silently returns empty on missing file (cold-start).
    /// 從環境變量或默認路徑加載。文件缺失時靜默返回空值（冷啟動）。
    pub fn load_from_env_or_default(base_dir: impl AsRef<Path>) -> Self {
        let default_path = base_dir.as_ref().join("settings").join("edge_estimates.json");
        let path = std::env::var("OPENCLAW_EDGE_SNAPSHOT")
            .map(std::path::PathBuf::from)
            .unwrap_or(default_path);

        Self::load_from_file(&path).unwrap_or_else(|| {
            tracing::debug!(
                path = %path.display(),
                "PH5-WIRE-1: no edge snapshot — cold-start ATR fallback active / 無快照，冷啟動 ATR 回退"
            );
            Self::empty()
        })
    }

    /// Look up shrunk edge estimate for a (strategy, symbol) pair.
    /// Returns None if no estimate available (unknown pair or cold-start).
    /// 查找 (策略, 幣種) 對的收縮邊際估計。無估計時返回 None。
    pub fn get(&self, strategy: &str, symbol: &str) -> Option<f64> {
        let key = format!("{}::{}", strategy, symbol);
        self.data.get(&key).copied()
    }

    /// Whether estimates have been loaded (non-empty).
    /// 估計是否已加載（非空）。
    pub fn is_populated(&self) -> bool {
        self.n_cells > 0
    }

    /// Number of (strategy, symbol) cells with estimates.
    /// 有估計的 (策略, 幣種) 格子數。
    pub fn n_cells(&self) -> usize {
        self.n_cells
    }

    /// Grand mean shrunk bps across all cells.
    /// 所有格子的全域均值收縮 bps。
    pub fn grand_mean_bps(&self) -> f64 {
        self.grand_mean_bps
    }
}
