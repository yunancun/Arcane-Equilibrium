//! CostEdgeConfig — G3-09 Phase A cost_edge_advisor schema sub-struct.
//! G3-09 Phase A：cost_edge_advisor schema 子配置。
//!
//! MODULE_NOTE (EN): Lives in its own sibling under `config/` because
//!   `risk_config_advanced.rs` is already at ~1297 lines (over §九 1200
//!   hard cap). Adding more schema there would compound the violation.
//!   Pattern mirrors `risk_config_regime.rs` (HurstConfig sibling).
//!
//!   Phase A scope (per PA RFC §7.1):
//!     - Schema + TOML section + validation only.
//!     - Defaults: `enabled = false` (Phase A dormant) +
//!       `trigger_threshold = -0.5` (conservative, per PM Tier 9
//!       T9-LOW-1 lock-in, ratio direction §2.4 variant A).
//!     - No IntentProcessor wiring (Phase B/C scope).
//!     - No per_strategy override (Phase C scope).
//!
//!   Threshold direction (per PA RFC §2.4):
//!     - `cost_edge_ratio = paper_pnl_7d_usd / ai_spend_7d_usd` (signed).
//!     - Trigger when `ratio <= trigger_threshold` (variant A — ratio
//!       small/negative = AI burning cash without return).
//!     - PM lock-in: default `-0.5` = "paper PnL loss reaches 50% of AI
//!       spend" — clearly burning, not random noise.
//!     - Operator may calibrate to any value in `[-100.0, 100.0]` after
//!       ≥30d demo data accumulation; auto-calibration explicitly
//!       FORBIDDEN per CLAUDE.md §二 #7 (learning ≠ rewriting Live).
//!
//!   Validation invariants:
//!     - `trigger_threshold` finite (no NaN/Inf).
//!     - `trigger_threshold ∈ [-100.0, 100.0]` — defensive bound; any
//!       value outside is operator config error (e.g. typed `-1000` by
//!       mistake → would never trigger and silently disable advisor).
//!
//! MODULE_NOTE (中)：Cost-edge advisor 的 schema 落在獨立 sibling 檔，
//!   因為 `risk_config_advanced.rs` 已 1297 行，超過 §九 1200 硬上限；
//!   對齊 `risk_config_regime.rs`（HurstConfig）的拆檔方式。
//!
//!   Phase A 範圍（PA RFC §7.1）：僅 schema + TOML section + validation；
//!   預設 `enabled=false`（Phase A 全 dormant）、`trigger_threshold=-0.5`
//!   （per PM Tier 9 T9-LOW-1 lock-in，方向 §2.4 變體 A）；不接
//!   IntentProcessor 與 per_strategy override（Phase B/C 範圍）。
//!
//!   Threshold 方向（PA RFC §2.4）：`ratio = paper_pnl_7d_usd /
//!   ai_spend_7d_usd`（含正負）。`ratio <= trigger_threshold` 即觸發
//!   （變體 A — ratio 越小/越負 = AI 燒錢無回報）。PM 鎖定 `-0.5`
//!   = paper 虧損達 AI 花費 50%（顯著燒錢，非隨機波動）。Operator 可
//!   經 ≥30d demo 資料累積後校準至 `[-100.0, 100.0]`；自動 calibration
//!   明文禁止（CLAUDE.md §二 #7：學習 ≠ 改寫 Live）。
//!
//!   Validate 不變量：`trigger_threshold` 有限 + 落於 `[-100.0, 100.0]`
//!   防 operator 誤配（如 `-1000` 永不觸發 → silent advisor disable）。

use serde::{Deserialize, Serialize};

/// G3-09 Phase A (2026-04-27): canonical cost_edge_advisor control plane.
///
/// Lifts CLAUDE.md §二 原則 #13「AI 資源成本感知」into Rust ConfigStore as
/// a first-class hot-reloadable field. Phase A landing keeps the advisor
/// dormant (enabled=false) so adding this struct has zero runtime impact;
/// Phase B (shadow dry-run) + Phase C (gate 新倉) flip the flag and wire
/// IntentProcessor consumption.
///
/// Per PA RFC §11 the advisor reads `h_state_cache.snapshot().h5.cost_edge_ratio`
/// every 10s, evaluates the threshold, and emits status-transition audit
/// events; it does NOT close existing positions (CLAUDE.md §二 #5 生存>利潤
/// 對 false-positive close 的反向防線).
///
/// G3-09 Phase A：cost_edge_advisor 控制平面 schema。把 CLAUDE.md §二 #13
/// 「AI 成本感知」升為 Rust ConfigStore 一級熱重載欄位。預設
/// `enabled=false` 保留現行為（runtime 零影響）；Phase B/C 後續接
/// IntentProcessor 消費。Advisor 每 10s 讀 H5 snapshot 比對 threshold 並
/// emit 狀態轉換 audit；不關現有倉位（CLAUDE.md §二 #5 生存>利潤）。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CostEdgeConfig {
    /// Master enable flag. `false` = advisor dormant even when env-gate
    /// `OPENCLAW_COST_EDGE_ADVISOR=1` is set; advisor evaluation cycle
    /// emits `Disabled` status and no triggers.
    /// `true` + env-gate ON = full advisor operation. Dual safeguard
    /// pattern (env-gate + RiskConfig flag) mirrors G3-08 H State Gateway.
    /// 主開關。`false` = 即使 env-gate 開啟 advisor 仍 dormant，僅 emit
    /// Disabled 狀態。`true` + env-gate ON = 完整啟用。雙保險 pattern
    /// 對齊 G3-08 H State Gateway。
    #[serde(default = "default_cost_edge_enabled")]
    pub enabled: bool,
    /// Trigger threshold on `cost_edge_ratio` (signed dimensionless).
    /// Advisor enters `Trigger` state when `ratio <= trigger_threshold`.
    /// Default `-0.5` = paper PnL loss reaches 50% of AI spend
    /// (significant burn, not random noise). Range `[-100.0, 100.0]`.
    /// Operator may calibrate after ≥30d demo data; auto-calibration
    /// explicitly forbidden per CLAUDE.md §二 #7.
    /// `cost_edge_ratio` 觸發門檻（含正負，無單位）。`ratio <= trigger_threshold`
    /// 進 Trigger 狀態。預設 `-0.5` = paper 虧損達 AI 花費 50%（顯著燒錢）。
    /// 範圍 `[-100.0, 100.0]`；operator 可 ≥30d 資料後校準，禁自動寫
    /// （CLAUDE.md §二 #7）。
    #[serde(default = "default_cost_edge_trigger_threshold")]
    pub trigger_threshold: f64,
}

fn default_cost_edge_enabled() -> bool {
    // Phase A safe default: advisor dormant. Operator + RiskConfig flag flip
    // (or IPC patch_risk_config) activates evaluation cycle.
    // Phase A 安全默認：advisor dormant，operator IPC flip 啟動。
    false
}

fn default_cost_edge_trigger_threshold() -> f64 {
    // -0.5 — per PM Tier 9 T9-LOW-1 lock-in (PA RFC §5.1):
    //   paper_pnl_7d_usd / ai_spend_7d_usd <= -0.5
    //   = "paper loss reaches 50% of AI spend" = clearly burning cash.
    // Conservative starting point; calibration deferred to Phase D
    // (operator manual approve only).
    // -0.5 — PM Tier 9 T9-LOW-1 lock-in（PA RFC §5.1）：paper 虧損達 AI 花費
    // 50% = 顯著燒錢；保守起點，Phase D 才校準（人工核准）。
    -0.5
}

impl Default for CostEdgeConfig {
    fn default() -> Self {
        Self {
            enabled: default_cost_edge_enabled(),
            trigger_threshold: default_cost_edge_trigger_threshold(),
        }
    }
}

impl CostEdgeConfig {
    /// G3-09 Phase A: validate threshold finiteness + sanity bound.
    ///
    /// Rejects NaN/Inf (would make every comparison `false` → silent
    /// advisor disable) and absurdly out-of-range values (`-1000` typed by
    /// mistake → ratio never reaches it). Range `[-100.0, 100.0]` is wide
    /// enough for any realistic operator calibration (the likely envelope
    /// is `[-2.0, 2.0]` based on demo PnL/spend ratios) yet narrow enough
    /// to catch typos.
    /// G3-09 Phase A：驗證 threshold 為有限值 + 落於合理範圍 `[-100.0,
    /// 100.0]`。NaN/Inf 會讓比較永 false（silent disable），超範圍 = operator
    /// 誤輸（合理校準應落於 `[-2.0, 2.0]`）。
    pub fn validate(&self) -> Result<(), String> {
        let v = self.trigger_threshold;
        if !v.is_finite() {
            return Err(format!(
                "risk.cost_edge.trigger_threshold ({}) must be finite (no NaN/Inf)",
                v
            ));
        }
        if !(-100.0..=100.0).contains(&v) {
            return Err(format!(
                "risk.cost_edge.trigger_threshold ({}) must be in [-100.0, 100.0]",
                v
            ));
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Default values match PM lock-in (Phase A dormant + threshold=-0.5).
    /// 預設值對齊 PM lock-in（Phase A dormant + threshold=-0.5）。
    #[test]
    fn default_matches_pm_lock_in() {
        let cfg = CostEdgeConfig::default();
        assert!(!cfg.enabled, "Phase A defaults to dormant");
        assert_eq!(cfg.trigger_threshold, -0.5);
    }

    /// validate() accepts default + boundary + typical calibration values.
    /// validate() 接受預設值、邊界、與典型校準值。
    #[test]
    fn validate_accepts_typical_values() {
        for v in [-100.0_f64, -2.0, -0.5, 0.0, 0.8, 100.0] {
            let cfg = CostEdgeConfig {
                enabled: true,
                trigger_threshold: v,
            };
            cfg.validate()
                .unwrap_or_else(|e| panic!("threshold {v} should be valid: {e}"));
        }
    }

    /// validate() rejects NaN / Inf to prevent silent advisor disable.
    /// validate() 拒絕 NaN/Inf 以防 silent advisor disable。
    #[test]
    fn validate_rejects_nan_and_inf() {
        for v in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
            let cfg = CostEdgeConfig {
                enabled: true,
                trigger_threshold: v,
            };
            assert!(
                cfg.validate().is_err(),
                "threshold {v} should be rejected (non-finite)"
            );
        }
    }

    /// validate() rejects out-of-range values (operator typo guard).
    /// validate() 拒絕超範圍值（防 operator 誤輸）。
    #[test]
    fn validate_rejects_out_of_range() {
        for v in [-100.001_f64, -1000.0, 100.001, 1000.0] {
            let cfg = CostEdgeConfig {
                enabled: true,
                trigger_threshold: v,
            };
            assert!(
                cfg.validate().is_err(),
                "threshold {v} should be rejected (out of range)"
            );
        }
    }

    /// Serde round-trip preserves defaults + custom values.
    /// Serde 來回保持預設值與自訂值。
    #[test]
    fn serde_roundtrip_preserves_values() {
        let cfg = CostEdgeConfig {
            enabled: true,
            trigger_threshold: -0.3,
        };
        let json = serde_json::to_string(&cfg).expect("serialize");
        let back: CostEdgeConfig = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(back.enabled, true);
        assert_eq!(back.trigger_threshold, -0.3);
    }

    /// `#[serde(default)]` on every field means partial JSON parses cleanly.
    /// 每欄位 `#[serde(default)]` 讓部分 JSON 也能 parse。
    #[test]
    fn serde_partial_uses_defaults() {
        let cfg: CostEdgeConfig = serde_json::from_str("{}").expect("parse empty");
        assert_eq!(cfg.enabled, false);
        assert_eq!(cfg.trigger_threshold, -0.5);
    }
}
