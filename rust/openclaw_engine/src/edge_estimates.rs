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

/// Per-cell edge detail parsed from the JSON snapshot.
/// 從 JSON 快照解析的每格子邊際詳情。
#[derive(Debug, Clone)]
pub struct CellEstimate {
    /// James-Stein shrunk realized edge in basis points.
    /// Runtime edge in basis points. This prefers JSON `runtime_bps`, which
    /// zeros unvalidated positive edge, and falls back to legacy `shrunk_bps`.
    /// 運行時邊際（bps）。優先讀 JSON `runtime_bps`（未驗證正 edge 歸零），
    /// 舊格式則回退到 `shrunk_bps`。
    pub shrunk_bps: f64,
    /// Win rate (shrunk or raw), clamped to [0, 1]. Default 0.5.
    /// 勝率（收縮或原始），限制在 [0, 1]。默認 0.5。
    pub win_rate: f64,
    /// Number of observed trades for this cell.
    /// 此格子的觀測交易數。
    pub n_trades: u64,
    /// Standard deviation of realized edge in bps. 0 if unavailable.
    /// 實現邊際標準差（bps）。不可用時為 0。
    pub std_bps: f64,
    /// Whether the producing estimator marked this cell as validated.
    /// 產生端 estimator 是否標記此格通過驗證。
    pub validation_passed: bool,
    /// Human-readable validation rejection/pass reason.
    /// 驗證通過/拒絕原因。
    pub validation_reason: String,
}

/// Shrunk realized-edge estimates per (strategy, symbol) cell.
/// 每 (策略, 幣種) 格子的收縮實現邊際估計。
#[derive(Debug, Clone, Default)]
pub struct EdgeEstimates {
    /// Maps "strategy::symbol" → full cell estimate.
    /// 映射 "策略::幣種" → 完整格子估計。
    data: HashMap<String, CellEstimate>,
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
            if let Some(bps) = val
                .get("runtime_bps")
                .or_else(|| val.get("shrunk_bps"))
                .and_then(|v| v.as_f64())
            {
                let win_rate = val
                    .get("win_rate_shrunk")
                    .or_else(|| val.get("win_rate"))
                    .and_then(|v| v.as_f64())
                    .unwrap_or(0.5)
                    .clamp(0.0, 1.0);
                let n_trades = val.get("n").and_then(|v| v.as_u64()).unwrap_or(0);
                let std_bps = val.get("std_bps").and_then(|v| v.as_f64()).unwrap_or(0.0);
                let validation_passed = val
                    .get("validation_passed")
                    .and_then(|v| v.as_bool())
                    .unwrap_or(false);
                let validation_reason = val
                    .get("validation_reason")
                    .and_then(|v| v.as_str())
                    .unwrap_or("")
                    .to_string();
                data.insert(
                    key.clone(),
                    CellEstimate {
                        shrunk_bps: bps,
                        win_rate,
                        n_trades,
                        std_bps,
                        validation_passed,
                        validation_reason,
                    },
                );
            }
        }

        let n_cells = data.len();
        tracing::info!(
            n_cells,
            grand_mean_bps,
            path = %path.display(),
            "PH5-WIRE-1: edge estimates loaded / 邊際估計已加載"
        );

        Some(Self {
            data,
            grand_mean_bps,
            n_cells,
        })
    }

    /// Load from a JSON string (convenience for tests and inline initialization).
    /// 從 JSON 字符串加載（測試和內聯初始化的便捷方法）。
    pub fn load_from_str(json: &str) -> Option<Self> {
        let parsed: serde_json::Value = serde_json::from_str(json).ok()?;
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
            if let Some(bps) = val
                .get("runtime_bps")
                .or_else(|| val.get("shrunk_bps"))
                .and_then(|v| v.as_f64())
            {
                let win_rate = val
                    .get("win_rate_shrunk")
                    .or_else(|| val.get("win_rate"))
                    .and_then(|v| v.as_f64())
                    .unwrap_or(0.5)
                    .clamp(0.0, 1.0);
                let n_trades = val.get("n").and_then(|v| v.as_u64()).unwrap_or(0);
                let std_bps = val.get("std_bps").and_then(|v| v.as_f64()).unwrap_or(0.0);
                let validation_passed = val
                    .get("validation_passed")
                    .and_then(|v| v.as_bool())
                    .unwrap_or(false);
                let validation_reason = val
                    .get("validation_reason")
                    .and_then(|v| v.as_str())
                    .unwrap_or("")
                    .to_string();
                data.insert(
                    key.clone(),
                    CellEstimate {
                        shrunk_bps: bps,
                        win_rate,
                        n_trades,
                        std_bps,
                        validation_passed,
                        validation_reason,
                    },
                );
            }
        }

        let n_cells = data.len();
        Some(Self {
            data,
            grand_mean_bps,
            n_cells,
        })
    }

    /// Load from OPENCLAW_EDGE_SNAPSHOT env var or default path.
    /// Silently returns empty on missing file (cold-start).
    /// 從環境變量或默認路徑加載。文件缺失時靜默返回空值（冷啟動）。
    pub fn load_from_env_or_default(base_dir: impl AsRef<Path>) -> Self {
        let default_path = base_dir
            .as_ref()
            .join("settings")
            .join("edge_estimates.json");
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

    /// Load mode-specific edge estimates: paper → edge_estimates_paper.json,
    /// demo/live → edge_estimates.json (production). Paper edge is isolated to prevent
    /// exploration noise from polluting demo/live cost_gate decisions.
    /// 加載模式特定邊際估計：paper → edge_estimates_paper.json，
    /// demo/live → edge_estimates.json（生產）。Paper edge 隔離以防探索噪音污染。
    pub fn load_for_mode(base_dir: impl AsRef<Path>, mode: &str) -> Self {
        let filename = match mode {
            "paper" => "edge_estimates_paper.json",
            _ => "edge_estimates.json", // demo + live share production estimates
        };
        let path = base_dir.as_ref().join("settings").join(filename);

        Self::load_from_file(&path).unwrap_or_else(|| {
            tracing::info!(
                mode,
                path = %path.display(),
                "edge estimates not found for mode — cold-start / 模式邊際估計未找到，冷啟動"
            );
            Self::empty()
        })
    }

    /// Look up shrunk edge bps for a (strategy, symbol) pair (convenience).
    /// Returns None if no estimate available (unknown pair or cold-start).
    /// 查找 (策略, 幣種) 對的收縮邊際 bps（便捷方法）。無估計時返回 None。
    pub fn get(&self, strategy: &str, symbol: &str) -> Option<f64> {
        self.get_cell(strategy, symbol).map(|c| c.shrunk_bps)
    }

    /// Look up full cell estimate for a (strategy, symbol) pair.
    /// 查找 (策略, 幣種) 對的完整格子估計。
    pub fn get_cell(&self, strategy: &str, symbol: &str) -> Option<&CellEstimate> {
        let key = format!("{}::{}", strategy, symbol);
        self.data.get(&key)
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

// ═══════════════════════════════════════════════════════════════════════════════
// FIX-13: Tests for edge_estimates (9 pub fn, JSON parse, edge cases)
// FIX-13：邊際估計測試（9 公開函數、JSON 解析、邊界情況）
// ═══════════════════════════════════════════════════════════════════════════════
#[cfg(test)]
mod tests {
    use super::*;

    fn sample_json() -> &'static str {
        r#"{
            "_meta": {"grand_mean_bps": -1.5, "n_cells": 3},
            "bb_reversion::BTCUSDT": {"shrunk_bps": 2.1, "win_rate_shrunk": 0.55, "n": 120, "std_bps": 3.0},
            "ma_crossover::ETHUSDT": {"shrunk_bps": -0.8, "win_rate": 0.48, "n": 80},
            "grid_trading::SOLUSDT": {"shrunk_bps": 0.0, "n": 5}
        }"#
    }

    #[test]
    fn test_empty_returns_default() {
        let e = EdgeEstimates::empty();
        assert!(!e.is_populated());
        assert_eq!(e.n_cells(), 0);
        assert_eq!(e.grand_mean_bps(), 0.0);
        assert!(e.get("any", "ANY").is_none());
    }

    #[test]
    fn test_load_from_str_valid() {
        let e = EdgeEstimates::load_from_str(sample_json()).unwrap();
        assert!(e.is_populated());
        assert_eq!(e.n_cells(), 3);
        assert!((e.grand_mean_bps() - (-1.5)).abs() < 1e-10);
    }

    #[test]
    fn test_get_existing_cell() {
        let e = EdgeEstimates::load_from_str(sample_json()).unwrap();
        assert!((e.get("bb_reversion", "BTCUSDT").unwrap() - 2.1).abs() < 1e-10);
        let cell = e.get_cell("bb_reversion", "BTCUSDT").unwrap();
        assert!((cell.win_rate - 0.55).abs() < 1e-10);
        assert_eq!(cell.n_trades, 120);
        assert!((cell.std_bps - 3.0).abs() < 1e-10);
    }

    #[test]
    fn test_get_nonexistent_cell() {
        let e = EdgeEstimates::load_from_str(sample_json()).unwrap();
        assert!(e.get("unknown_strat", "BTCUSDT").is_none());
        assert!(e.get("bb_reversion", "UNKNOWN").is_none());
    }

    #[test]
    fn test_win_rate_fallback_to_raw() {
        // ma_crossover::ETHUSDT has "win_rate" not "win_rate_shrunk"
        let e = EdgeEstimates::load_from_str(sample_json()).unwrap();
        let cell = e.get_cell("ma_crossover", "ETHUSDT").unwrap();
        assert!((cell.win_rate - 0.48).abs() < 1e-10);
    }

    #[test]
    fn test_win_rate_default_and_std_default() {
        // grid_trading::SOLUSDT has no win_rate or std_bps
        let e = EdgeEstimates::load_from_str(sample_json()).unwrap();
        let cell = e.get_cell("grid_trading", "SOLUSDT").unwrap();
        assert!((cell.win_rate - 0.5).abs() < 1e-10); // default 0.5
        assert!((cell.std_bps - 0.0).abs() < 1e-10); // default 0.0
    }

    #[test]
    fn test_load_from_str_invalid_json() {
        assert!(EdgeEstimates::load_from_str("not json").is_none());
    }

    #[test]
    fn test_load_from_str_empty_object() {
        let e = EdgeEstimates::load_from_str("{}").unwrap();
        assert!(!e.is_populated());
        assert_eq!(e.n_cells(), 0);
        assert_eq!(e.grand_mean_bps(), 0.0);
    }

    #[test]
    fn test_load_from_str_meta_only() {
        let e = EdgeEstimates::load_from_str(r#"{"_meta": {"grand_mean_bps": 5.0}}"#).unwrap();
        assert!(!e.is_populated());
        assert!((e.grand_mean_bps() - 5.0).abs() < 1e-10);
    }

    #[test]
    fn test_load_from_file_missing() {
        assert!(EdgeEstimates::load_from_file("/nonexistent/path.json").is_none());
    }

    #[test]
    fn test_win_rate_clamped() {
        let json = r#"{"strat::SYM": {"shrunk_bps": 1.0, "win_rate_shrunk": 1.5, "n": 10}}"#;
        let e = EdgeEstimates::load_from_str(json).unwrap();
        let cell = e.get_cell("strat", "SYM").unwrap();
        assert!((cell.win_rate - 1.0).abs() < 1e-10); // clamped to 1.0
    }

    #[test]
    fn test_negative_win_rate_clamped() {
        let json = r#"{"strat::SYM": {"shrunk_bps": 1.0, "win_rate_shrunk": -0.3, "n": 10}}"#;
        let e = EdgeEstimates::load_from_str(json).unwrap();
        let cell = e.get_cell("strat", "SYM").unwrap();
        assert!((cell.win_rate - 0.0).abs() < 1e-10); // clamped to 0.0
    }

    #[test]
    fn test_load_from_env_or_default_missing_file() {
        // With a non-existent base dir, should return empty (cold-start fallback)
        let e = EdgeEstimates::load_from_env_or_default("/nonexistent_base");
        assert!(!e.is_populated());
    }

    #[test]
    fn test_entry_without_shrunk_bps_skipped() {
        let json = r#"{"strat::SYM": {"win_rate": 0.6, "n": 10}}"#;
        let e = EdgeEstimates::load_from_str(json).unwrap();
        assert_eq!(e.n_cells(), 0); // no shrunk_bps → not inserted
    }

    #[test]
    fn test_runtime_bps_overrides_positive_shrunk_bps() {
        let json = r#"{
            "strat::SYM": {
                "shrunk_bps": 12.0,
                "runtime_bps": 0.0,
                "validation_passed": false,
                "validation_reason": "insufficient_oos_samples",
                "n": 3
            }
        }"#;
        let e = EdgeEstimates::load_from_str(json).unwrap();
        let cell = e.get_cell("strat", "SYM").unwrap();
        assert!((cell.shrunk_bps - 0.0).abs() < 1e-10);
        assert!(!cell.validation_passed);
        assert_eq!(cell.validation_reason, "insufficient_oos_samples");
    }

    #[test]
    fn test_load_for_mode_paper_uses_paper_filename() {
        // Paper mode should look for edge_estimates_paper.json, not edge_estimates.json.
        // With a non-existent base dir, both return empty (cold-start).
        let e = EdgeEstimates::load_for_mode("/nonexistent_base", "paper");
        assert!(!e.is_populated());
    }

    #[test]
    fn test_load_for_mode_demo_uses_default_filename() {
        // Demo mode should look for edge_estimates.json (production).
        let e = EdgeEstimates::load_for_mode("/nonexistent_base", "demo");
        assert!(!e.is_populated());
    }

    #[test]
    fn test_load_for_mode_live_uses_default_filename() {
        // Live mode shares production estimates with demo.
        let e = EdgeEstimates::load_for_mode("/nonexistent_base", "live");
        assert!(!e.is_populated());
    }
}
