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
    /// P1-09: true ONLY when the JSON `runtime_bps` key was present for this
    /// cell. False means `shrunk_bps` came from the legacy `shrunk_bps` fallback.
    /// The production freshness gate requires a runtime-derived bps before a
    /// positive edge may authorize — a legacy-only positive `shrunk_bps` (no
    /// `runtime_bps`, no validation) must not pass the live gate (root #5/#6).
    /// P1-09：僅當此 cell 的 JSON 含 `runtime_bps` key 時為 true。False 代表
    /// `shrunk_bps` 來自舊格式 `shrunk_bps` 回退。生產新鮮度門要求 bps 為
    /// runtime-derived 才允許正 edge 授權——舊格式正 `shrunk_bps`（無 `runtime_bps`、
    /// 無驗證）不可過 live 門（根原則 #5/#6）。
    pub from_runtime_field: bool,
    /// Track1 demo explore-gate：allocator 是否指示此 arm 仍在探索期（regime-aware）。
    /// 為什麼 fail-closed：JSON 缺欄 → false（不探索，回退現行 gate 行為）。
    /// 此欄**只被 demo gate**（`cost_gate_moderate_with_slippage`）讀；live gate
    /// （`cost_gate_live_with_slippage`）不引用，是 demo↔live 隔離的單一守門點。
    pub explore_eligible: bool,
    /// Track1 demo explore-gate：剩餘探索額度（allocator `explore_budget - n_trials`，
    /// 下限 0）。0 = 探索滿額 → 即使 eligible 仍回現行 block（不無限探索）。
    /// 缺欄 → 0（fail-closed）。同樣只被 demo gate 讀。
    pub explore_remaining: u64,
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
    /// P1-09: `_meta.updated_at` parsed RFC3339 → epoch seconds. None when the
    /// field is absent or unparseable; a None snapshot is treated as NOT fresh
    /// by `is_fresh`, so a legacy snapshot with no timestamp fails the freshness
    /// gate (live → reject) rather than silently passing.
    /// P1-09：`_meta.updated_at` 解析 RFC3339 → epoch 秒。欄位缺失或無法解析時
    /// 為 None；`is_fresh` 將 None 視為「非新鮮」，舊格式無時間戳快照無法通過
    /// 新鮮度門（live → 拒絕）而非靜默放行。
    updated_at: Option<i64>,
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

        let (data, grand_mean_bps, updated_at) = Self::parse_object(obj);

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
            updated_at,
        })
    }

    /// P1-09: shared parse of the JSON top-level object into
    /// (cells, grand_mean_bps, updated_at). Extracted so `load_from_file` and
    /// `load_from_str` share one source of truth for the new `from_runtime_field`
    /// and `_meta.updated_at` semantics (previously the two loops were duplicated
    /// and could drift). `from_runtime_field` is true ONLY when the JSON
    /// `runtime_bps` key is present; `updated_at` parses `_meta.updated_at`
    /// (RFC3339 → epoch secs) and is None when absent/unparseable.
    /// P1-09：抽出共用解析，將 JSON 頂層物件轉成 (cells, grand_mean_bps,
    /// updated_at)，讓 `load_from_file` 與 `load_from_str` 對 `from_runtime_field`
    /// 與 `_meta.updated_at` 共用單一真相來源（先前兩份迴圈重複易漂移）。
    fn parse_object(
        obj: &serde_json::Map<String, serde_json::Value>,
    ) -> (HashMap<String, CellEstimate>, f64, Option<i64>) {
        let mut data = HashMap::new();
        let mut grand_mean_bps = 0.0;
        let mut updated_at: Option<i64> = None;

        if let Some(meta) = obj.get("_meta").and_then(|v| v.as_object()) {
            grand_mean_bps = meta
                .get("grand_mean_bps")
                .and_then(|v| v.as_f64())
                .unwrap_or(0.0);
            // RFC3339 → epoch 秒。解析失敗 / 缺失 → None（is_fresh 視為非新鮮）。
            updated_at = meta
                .get("updated_at")
                .and_then(|v| v.as_str())
                .and_then(|s| chrono::DateTime::parse_from_rfc3339(s).ok())
                .map(|dt| dt.timestamp());
        }

        for (key, val) in obj {
            if key.starts_with('_') {
                continue;
            }
            // P1-09：先判定 runtime_bps key 是否存在（決定 from_runtime_field），
            // 再回退到舊格式 shrunk_bps。
            let runtime_field = val.get("runtime_bps").and_then(|v| v.as_f64());
            let from_runtime_field = runtime_field.is_some();
            if let Some(bps) =
                runtime_field.or_else(|| val.get("shrunk_bps").and_then(|v| v.as_f64()))
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
                // Track1：explore 信號 fail-closed 解析。缺欄 → false / 0，
                // 即「不探索」，舊 JSON（無 explore 欄）行為完全不變（absence=no-explore）。
                let explore_eligible = val
                    .get("explore_eligible")
                    .and_then(|v| v.as_bool())
                    .unwrap_or(false);
                let explore_remaining = val
                    .get("explore_remaining")
                    .and_then(|v| v.as_u64())
                    .unwrap_or(0);
                data.insert(
                    key.clone(),
                    CellEstimate {
                        shrunk_bps: bps,
                        win_rate,
                        n_trades,
                        std_bps,
                        validation_passed,
                        validation_reason,
                        from_runtime_field,
                        explore_eligible,
                        explore_remaining,
                    },
                );
            }
        }

        (data, grand_mean_bps, updated_at)
    }

    /// Load from a JSON string (convenience for tests and inline initialization).
    /// 從 JSON 字符串加載（測試和內聯初始化的便捷方法）。
    pub fn load_from_str(json: &str) -> Option<Self> {
        let parsed: serde_json::Value = serde_json::from_str(json).ok()?;
        let obj = parsed.as_object()?;

        let (data, grand_mean_bps, updated_at) = Self::parse_object(obj);

        let n_cells = data.len();
        Some(Self {
            data,
            grand_mean_bps,
            n_cells,
            updated_at,
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

    /// P1-09: snapshot `_meta.updated_at` as epoch seconds, or None when the
    /// field was absent / unparseable.
    /// P1-09：快照 `_meta.updated_at`（epoch 秒），缺失或無法解析時為 None。
    pub fn updated_at(&self) -> Option<i64> {
        self.updated_at
    }

    /// P1-09: whether the snapshot is fresh relative to `now` (epoch secs) and
    /// `ttl` (secs). A None `updated_at` is NOT fresh — a legacy snapshot with no
    /// timestamp must fail the production freshness gate rather than pass
    /// silently. Pure function: `now` is injected by the caller (never read from
    /// wallclock here) so the gate stays deterministic and unit-testable.
    /// P1-09：快照相對 `now`（epoch 秒）與 `ttl`（秒）是否新鮮。None `updated_at`
    /// 視為非新鮮——無時間戳的舊快照必須無法通過生產新鮮度門而非靜默放行。
    /// 純函數：`now` 由呼叫端注入（此處絕不讀 wallclock），確保門 determinism 與可測。
    pub fn is_fresh(&self, now: i64, ttl: i64) -> bool {
        // 防禦：now <= 0 視為非新鮮（fail-closed）。舊 process() 路徑會以 now=0
        // 委派，若不擋則 0.saturating_sub(updated_at) 下溢成大值並 <= ttl 判 TRUE，
        // 令 STALE cell 誤判為 FRESH。生產不可達，但補此 guard 杜絕潛在 fail-open。
        if now <= 0 {
            return false;
        }
        match self.updated_at {
            Some(updated_at) => now.saturating_sub(updated_at) <= ttl,
            None => false,
        }
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

    // ─── P1-09: freshness / runtime-derived parse + is_fresh ───
    // P1-09：新鮮度 / runtime-derived 解析 + is_fresh

    #[test]
    fn test_updated_at_parses_rfc3339() {
        let json = r#"{
            "_meta": {"grand_mean_bps": 1.0, "updated_at": "2026-05-29T00:00:00+00:00"},
            "strat::SYM": {"runtime_bps": 5.0, "validation_passed": true, "n": 50}
        }"#;
        let e = EdgeEstimates::load_from_str(json).unwrap();
        // 2026-05-29T00:00:00Z = 1780012800 epoch secs.
        assert_eq!(e.updated_at(), Some(1_780_012_800));
    }

    #[test]
    fn test_updated_at_none_when_meta_missing_field() {
        let json = r#"{
            "_meta": {"grand_mean_bps": 1.0},
            "strat::SYM": {"runtime_bps": 5.0, "n": 50}
        }"#;
        let e = EdgeEstimates::load_from_str(json).unwrap();
        assert!(e.updated_at().is_none());
    }

    #[test]
    fn test_updated_at_none_when_unparseable() {
        let json = r#"{
            "_meta": {"updated_at": "not-a-timestamp"},
            "strat::SYM": {"runtime_bps": 5.0, "n": 50}
        }"#;
        let e = EdgeEstimates::load_from_str(json).unwrap();
        assert!(e.updated_at().is_none());
    }

    #[test]
    fn test_from_runtime_field_true_only_when_runtime_bps_present() {
        let json = r#"{
            "with_rt::SYM": {"runtime_bps": 5.0, "shrunk_bps": 9.0, "n": 50},
            "legacy::SYM": {"shrunk_bps": 9.0, "n": 50}
        }"#;
        let e = EdgeEstimates::load_from_str(json).unwrap();
        assert!(e.get_cell("with_rt", "SYM").unwrap().from_runtime_field);
        assert!(!e.get_cell("legacy", "SYM").unwrap().from_runtime_field);
    }

    #[test]
    fn test_is_fresh_within_ttl() {
        let json = r#"{
            "_meta": {"updated_at": "2026-05-29T00:00:00+00:00"},
            "strat::SYM": {"runtime_bps": 5.0, "n": 50}
        }"#;
        let e = EdgeEstimates::load_from_str(json).unwrap();
        let updated = 1_780_012_800;
        let ttl = 172_800; // 48h
        // 正好等於 TTL 邊界 → fresh（<= 比較）。
        assert!(e.is_fresh(updated + ttl, ttl));
        // 超過 TTL 1 秒 → not fresh。
        assert!(!e.is_fresh(updated + ttl + 1, ttl));
    }

    #[test]
    fn test_is_fresh_false_when_no_updated_at() {
        // 無 updated_at 的舊快照永遠視為非新鮮（fail-closed 預設）。
        let json = r#"{"strat::SYM": {"runtime_bps": 5.0, "n": 50}}"#;
        let e = EdgeEstimates::load_from_str(json).unwrap();
        assert!(!e.is_fresh(1_779_667_200, 172_800));
    }

    #[test]
    fn test_is_fresh_false_when_now_non_positive() {
        // now <= 0（如舊 process() 委派 now=0）即使 updated_at 很新也判非新鮮，
        // 杜絕 0.saturating_sub 下溢造成 STALE 誤判 FRESH 的 fail-open。
        let json = r#"{
            "_meta": {"updated_at": "2026-05-29T00:00:00+00:00"},
            "strat::SYM": {"runtime_bps": 5.0, "n": 50}
        }"#;
        let e = EdgeEstimates::load_from_str(json).unwrap();
        let ttl = 172_800; // 48h
        assert!(!e.is_fresh(0, ttl));
        assert!(!e.is_fresh(-1, ttl));
    }
}
