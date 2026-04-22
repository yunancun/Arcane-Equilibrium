//! v2 non-linear giveback consumer: `ExitConfig` + `non_linear_giveback_fn` +
//! `physical_micro_profit_lock_v2`（4-Gate 依序過濾的 pure fn）。
//! v2 non-linear giveback consumer: `ExitConfig` + `non_linear_giveback_fn`
//! + `physical_micro_profit_lock_v2` (pure fn running the 4-Gate sequence).
//!
//! ### Gate 1 semantics — v2 corrects v1 (2026-04-21)
//!
//! DUAL-TRACK-EXIT-1 design intent (§三 L108-111): "prevent exiting on any
//! micro-profit above fee; let trailing-stop capture the trajectory; pursue
//! the maximum single-close PnL." Therefore **only Gate 4 (trailing) is a
//! legal Lock path**. When `est_net_bps` is below the floor we must **Hold**
//! so the position keeps running until either edge climbs above floor and
//! a later gate fires, or the peak is hit and Gate 4 triggers on giveback.
//!
//! v1 (`risk_checks::physical_micro_profit_lock` Priority 6) was corrected
//! in-place by `GATE1-REVERSAL-1` hotfix A (commit `d0f0c21`, 2026-04-21)
//! so v1 and v2 now share the same Gate 1 Hold semantics; v2 still carries
//! the non-linear giveback threshold which v1's `PhysLockConfig` lacks. The
//! pending `TRACK-P-V2-SWAP-1` TODO swaps Priority 6 from v1 linear to v2
//! non-linear at which point v1 can be retired.
//!
//! ### Gate 1 語意 — v2 對齊設計（2026-04-21）
//!
//! DUAL-TRACK-EXIT-1 設計意圖（§三 L108-111）：「防止剛有大於 fee 的微利就
//! 套利離場；保證 trailing stop；追求最高單筆 close 盈利。」因此**只有 Gate 4
//! (trailing) 才是合法的 Lock 路徑**。`est_net_bps` 低於底線時必須 **Hold**
//! 讓 position 繼續跑，直到 edge 爬到底線上方再經後續 gate 評估，或 peak
//! 成形後 Gate 4 因 giveback 觸發。v1 由 hotfix A（commit `d0f0c21`）原地反轉
//! Gate 1 與 v2 對齊；v2 額外保留非線性 giveback 閾值（v1 `PhysLockConfig` 無
//! 此能力），未來 `TRACK-P-V2-SWAP-1` 完成後 Priority 6 改餵 v2、退役 v1。

use super::core::{ExitFeatures, PhysicalDecision};

/// Physical-layer micro-profit lock configuration with a **non-linear**
/// giveback threshold. Unlike `PhysLockConfig` (single fixed threshold),
/// this encodes the designer intent: as `peak_atr_norm` grows, a relatively
/// smaller giveback already signals momentum decay; for shallow peaks a
/// larger retracement is required before locking. The mapping is
/// `threshold(peak_atr_norm) = max(giveback_base - giveback_slope * peak_atr_norm,
/// giveback_floor)` — linear decay bounded below by `giveback_floor`.
///
/// Units are the same as `PhysLockConfig`:
/// - `min_net_floor_bps` : basis points on `est_net_bps`
/// - `min_hold_secs`     : seconds (f64 for test ergonomics)
/// - `min_peak_atr_norm` : dimensionless ratio (peak_pnl_pct / atr_pct)
/// - `stale_peak_ms`     : milliseconds
/// - `giveback_*`        : ATR-normalised retracement units
///
/// ConfigStore binding is **intentionally deferred**: this struct has a
/// `Default` impl + `validate()` method only; there is no ArcSwap/hot-reload
/// plumbing yet. The next wave replaces `PhysLockConfig` in
/// `config::risk_config` with this struct (and retires the linear threshold),
/// at which point hot-reload follows the existing RiskConfig machinery.
///
/// 物理層微利鎖定參數（**非線性** giveback 閾值版）。語義：peak 越高 → 相對較小的
/// giveback 就應鎖定；peak 較淺時需更大回吐才鎖定。公式：
/// `threshold(peak_atr_norm) = max(base - slope × peak_atr_norm, floor)`。
///
/// 單位同 `PhysLockConfig`（min_net_floor_bps bps / min_hold_secs 秒 /
/// stale_peak_ms 毫秒 / giveback_* 為 ATR 正規化單位）。
///
/// **ConfigStore 綁定故意留到下一波**：此 struct 僅有 Default 與 validate()，
/// 無 ArcSwap/hot-reload 接線，下一波以本 struct 取代 `PhysLockConfig` 並
/// 退役舊線性閾值。
#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct ExitConfig {
    /// Gate 1 net-edge floor (bps). `est_net_bps <= this` → **Hold** (not a
    /// lock path). Semantics: while edge is still below floor we protect the
    /// micro-profit phase by letting the position run, so edge can climb
    /// above floor before any later-gate (2/3/4) evaluation considers a lock.
    /// Default 5.0.
    /// Gate 1 淨邊緣底線（bps），低於此值 → **Hold**（不走鎖定路徑）。語意：
    /// edge 仍在底線以下時保護微利期，讓 position 繼續跑直到 edge 爬到此值
    /// 以上才考慮 Gate 2-4 評估。Default 5.0。
    #[serde(default = "default_min_net_floor_bps")]
    pub min_net_floor_bps: f64,
    /// Gate 2 minimum hold time (seconds). Too-fresh positions held regardless.
    /// Gate 2 最短持有秒數。Default 30s。
    #[serde(default = "default_min_hold_secs")]
    pub min_hold_secs: f64,
    /// Gate 3 peak height threshold in ATR units. Default 0.5.
    /// Gate 3 peak 高度（ATR 倍數）閾值。Default 0.5。
    #[serde(default = "default_min_peak_atr_norm")]
    pub min_peak_atr_norm: f64,
    /// Gate 4b stale-peak time (ms). Default 60_000 (1 min).
    /// Gate 4b peak 陳舊毫秒門檻。Default 60_000。
    #[serde(default = "default_stale_peak_ms")]
    pub stale_peak_ms: i64,
    /// Non-linear giveback intercept — threshold for `peak_atr_norm = 0`.
    /// Default 1.0 (shallow peaks require a full ATR retracement).
    /// 非線性 giveback 截距 — peak_atr_norm=0 時的閾值。Default 1.0。
    #[serde(default = "default_giveback_base")]
    pub giveback_base: f64,
    /// Non-linear giveback slope — threshold decrement per unit peak_atr_norm.
    /// Default 0.15.
    /// 非線性 giveback 斜率 — 每單位 peak_atr_norm 遞減。Default 0.15。
    #[serde(default = "default_giveback_slope")]
    pub giveback_slope: f64,
    /// Non-linear giveback floor — minimum threshold (high peaks do not drop
    /// below this). Default 0.3.
    /// 非線性 giveback 下限 — 高 peak 時 threshold 不低於此值。Default 0.3。
    #[serde(default = "default_giveback_floor")]
    pub giveback_floor: f64,
    /// P0-14 Option A — Gate 1 fallback bps when `est_net_bps` is `None`.
    /// Runtime owner_strategy values for sync-label positions (bybit_sync /
    /// orphan_* / dust_frozen) miss `edge_estimates.json` cells ~99% of the
    /// time (per P0-14 RCA), so pre-fix Gate 1 always Held and Priority 6
    /// never evaluated trailing for those positions. This fallback lets
    /// operators treat missing edge as a weak prior: default `-10.0` keeps
    /// fail-safe (still `<= min_net_floor_bps=5.0` → Hold), matching the
    /// pre-fix conservative behavior; raise to a value `> min_net_floor_bps`
    /// to allow sync-label positions to reach Gate 2+ before the Option B
    /// proxy-cell fill lands. Complementary to P0-14 Option B which populates
    /// the JSON from `grand_mean_bps` — A is the runtime safety net, B is
    /// the source-of-truth fill.
    /// P0-14 Option A — Gate 1 在 `est_net_bps` 為 `None` 時的 fallback bps。
    /// Runtime sync-label 倉位（bybit_sync / orphan_* / dust_frozen）的
    /// owner_strategy 在 `edge_estimates.json` 約 99% miss（P0-14 RCA），
    /// 修復前 Gate 1 永遠 Hold、Priority 6 從未為這些倉位評估 trailing。
    /// 此 fallback 讓 operator 把「邊緣缺值」視為弱先驗：預設 `-10.0` 保守
    /// 仍 Hold（`<= min_net_floor_bps=5.0`），與修復前 fail-safe 行為一致；
    /// 設 > `min_net_floor_bps` 則允許 sync-label 倉位在 Option B proxy
    /// cells 填入前也進 Gate 2+。與 P0-14 Option B 用 `grand_mean_bps`
    /// 回填 JSON 互補：A 是 runtime 兜底，B 是 source-of-truth 填補。
    #[serde(default = "default_missing_edge_fallback_bps")]
    pub missing_edge_fallback_bps: f64,
}

fn default_min_net_floor_bps() -> f64 {
    5.0
}
fn default_min_hold_secs() -> f64 {
    30.0
}
fn default_min_peak_atr_norm() -> f64 {
    0.5
}
fn default_stale_peak_ms() -> i64 {
    60_000
}
fn default_giveback_base() -> f64 {
    1.0
}
fn default_giveback_slope() -> f64 {
    0.15
}
fn default_giveback_floor() -> f64 {
    0.3
}
fn default_missing_edge_fallback_bps() -> f64 {
    // Conservative: stays below default `min_net_floor_bps` (5.0) so Gate 1
    // continues to Hold for missing edge, preserving pre-fix fail-safe.
    // 保守值：仍低於預設 `min_net_floor_bps` (5.0)，故 edge 缺值時 Gate 1
    // 繼續 Hold，維持修復前 fail-safe 行為。
    -10.0
}

impl Default for ExitConfig {
    fn default() -> Self {
        Self {
            min_net_floor_bps: default_min_net_floor_bps(),
            min_hold_secs: default_min_hold_secs(),
            min_peak_atr_norm: default_min_peak_atr_norm(),
            stale_peak_ms: default_stale_peak_ms(),
            giveback_base: default_giveback_base(),
            giveback_slope: default_giveback_slope(),
            giveback_floor: default_giveback_floor(),
            missing_edge_fallback_bps: default_missing_edge_fallback_bps(),
        }
    }
}

impl ExitConfig {
    /// Validate numeric invariants. Returns `Err(msg)` on first violation.
    /// 驗證數值不變量；違反時回傳第一個錯誤。
    pub fn validate(&self) -> Result<(), String> {
        if !self.min_net_floor_bps.is_finite() || self.min_net_floor_bps < 0.0 {
            return Err("exit.min_net_floor_bps must be finite and >= 0".into());
        }
        if !self.min_hold_secs.is_finite() || self.min_hold_secs < 0.0 {
            return Err("exit.min_hold_secs must be finite and >= 0".into());
        }
        if !self.min_peak_atr_norm.is_finite() || self.min_peak_atr_norm < 0.0 {
            return Err("exit.min_peak_atr_norm must be finite and >= 0".into());
        }
        if self.stale_peak_ms < 0 {
            return Err("exit.stale_peak_ms must be >= 0".into());
        }
        if !self.giveback_base.is_finite() || self.giveback_base <= 0.0 {
            return Err("exit.giveback_base must be finite and > 0".into());
        }
        if !self.giveback_slope.is_finite() || self.giveback_slope < 0.0 {
            return Err("exit.giveback_slope must be finite and >= 0".into());
        }
        if !self.giveback_floor.is_finite() || self.giveback_floor <= 0.0 {
            return Err("exit.giveback_floor must be finite and > 0".into());
        }
        if self.giveback_floor > self.giveback_base {
            return Err("exit.giveback_floor must be <= giveback_base".into());
        }
        if !self.missing_edge_fallback_bps.is_finite() {
            return Err("exit.missing_edge_fallback_bps must be finite".into());
        }
        Ok(())
    }
}

/// Non-linear giveback threshold as a function of `peak_atr_norm`.
///
/// Intent (designer doc §三): when the peak is high in ATR units a relatively
/// small giveback already signals momentum decay; for shallow peaks we need
/// a larger retracement before locking. Implemented as a **linear** decay
/// bounded below by `giveback_floor`:
///
/// ```text
/// threshold = max(giveback_base − giveback_slope × peak_atr_norm, giveback_floor)
/// ```
///
/// Guards: any non-finite `peak_atr_norm` or negative input clamps to 0.0
/// (i.e. returns `giveback_base`), keeping the function total over all f64
/// inputs without poisoning the exit policy with NaN.
///
/// 依 peak_atr_norm 計算非線性 giveback 閾值（實作為線性遞減、以 floor 保底）。
/// 設計意圖：peak 高時小 giveback 即鎖；peak 淺時需大 giveback 才鎖。
/// 非法輸入 (NaN/Inf/負值) 夾回 0.0 → 回傳 `giveback_base`，避免污染 exit 決策。
pub(crate) fn non_linear_giveback_fn(peak_atr_norm: f64, cfg: &ExitConfig) -> f64 {
    let norm = if peak_atr_norm.is_finite() && peak_atr_norm >= 0.0 {
        peak_atr_norm
    } else {
        0.0
    };
    (cfg.giveback_base - cfg.giveback_slope * norm).max(cfg.giveback_floor)
}

/// Physical-layer micro-profit lock (v2, non-linear giveback).
///
/// Applies the Track P designer-doc §三 4-gate sequence against an
/// `ExitFeatures` snapshot. Conservative semantics: any required `Option::None`
/// returns `Hold`. Design intent (§三 L108-111): **only Gate 4 (trailing) is
/// a legal Lock path**; Gate 1 is a conservative early-return that Holds
/// when edge is insufficient (protects the micro-profit phase and lets
/// edge climb before any later gate considers a lock).
///
/// ### Gate sequence
/// 1. **Edge floor** — `est_net_bps <= min_net_floor_bps` → Hold
///    (not a lock path; lets edge climb before later gates evaluate).
///    `None` → Hold.
/// 2. **Min hold** — `entry_age_secs < min_hold_secs` → Hold.
///    `None` → Hold.
/// 3. **Peak / ATR threshold** — `peak_pnl_pct / atr_pct < min_peak_atr_norm`
///    → Hold. `atr_pct: None | Some(0.0)` → Hold.
/// 4. **Lock trigger** (only Lock path) — either
///    - a. giveback ≥ `non_linear_giveback_fn(peak_atr_norm, cfg)`
///         → Lock (`phys_lock_gate4_giveback`)
///    - b. `time_since_peak_ms >= stale_peak_ms` AND `price_roc_short < 0`
///         → Lock (`phys_lock_gate4_stale_roc_neg`)
///    else → Hold.
///
/// Returns reason strings compatible with the existing `parse_exit_tag`
/// downstream parser (same `phys_lock_*` prefix + exact suffix used by the
/// legacy linear-threshold version in `risk_checks.rs`).
///
/// Pure function — no I/O, no allocation outside the returned reason `String`.
///
/// 物理層微利鎖定（v2 非線性 giveback 版）。依設計文檔 §三 4 Gate 依序過濾：
/// edge 底（Hold）→ 最短持有（Hold）→ peak/ATR 閾值（Hold）→ giveback 或
/// stale-peak+negROC（唯一 Lock 路徑）。設計意圖（§三 L108-111）：**只有
/// Gate 4 (trailing) 才是合法的 Lock 路徑**；Gate 1 為保守 early-return，
/// edge 不夠時 Hold（保護微利期、讓 edge 爬升）。
/// reason 字串沿用既有 `phys_lock_*` 前綴，與 `risk_checks.rs` 舊版相容，
/// 方便下一波直接替換 Priority 6 而不破 `parse_exit_tag`。
/// Pure fn — 無 I/O、除回傳 reason `String` 外零分配。
pub fn physical_micro_profit_lock_v2(
    f: &ExitFeatures,
    cfg: &ExitConfig,
) -> PhysicalDecision {
    // Gate 1: est_net_bps floor — conservative Hold when edge insufficient.
    // P0-14 Option A: when `est_net_bps` is None (sync-label / proxy-miss),
    // substitute `missing_edge_fallback_bps` as a weak prior; default is a
    // conservative negative value that still Holds via the floor comparison,
    // preserving pre-fix fail-safe. Raising the fallback above the floor
    // escalates sync-label positions to evaluate Gate 2+.
    // Gate 1：淨邊緣底線 — edge 不足時保守 Hold（防止微利即套離場）。
    // P0-14 Option A：`est_net_bps` 為 None（sync-label / proxy 缺值）時
    // 以 `missing_edge_fallback_bps` 作弱先驗；預設保守負值透過 floor 比較
    // 仍 Hold，維持修復前 fail-safe；若 fallback 調高於 floor，則允許
    // sync-label 倉位進入 Gate 2+ 評估。
    let effective_edge = f
        .est_net_bps
        .map(f64::from)
        .unwrap_or(cfg.missing_edge_fallback_bps);
    if effective_edge <= cfg.min_net_floor_bps {
        return PhysicalDecision::Hold;
    }

    // Gate 2: minimum hold time.
    // Gate 2：最短持有時間。
    let age_secs = match f.entry_age_secs {
        Some(a) => f64::from(a),
        None => return PhysicalDecision::Hold,
    };
    if age_secs < cfg.min_hold_secs {
        return PhysicalDecision::Hold;
    }

    // Gate 3: peak height in ATR units.
    // Gate 3：peak 高度（ATR 正規化）。
    let atr = match f.atr_pct {
        Some(a) if a > 0.0 && a.is_finite() => a,
        _ => return PhysicalDecision::Hold,
    };
    let peak_atr_norm = f64::from(f.peak_pnl_pct) / atr;
    if peak_atr_norm < cfg.min_peak_atr_norm {
        return PhysicalDecision::Hold;
    }

    // Gate 4a: non-linear giveback threshold.
    // Gate 4a：非線性 giveback 閾值。
    let giveback_threshold = non_linear_giveback_fn(peak_atr_norm, cfg);
    if let Some(gb) = f.giveback_atr_norm {
        if f64::from(gb) >= giveback_threshold {
            return PhysicalDecision::Lock("phys_lock_gate4_giveback".to_string());
        }
    }

    // Gate 4b: stale peak + negative short-ROC.
    // Gate 4b：peak 陳舊 + 短窗 ROC 為負。
    match (f.time_since_peak_ms, f.price_roc_short) {
        (Some(dt), Some(roc)) if dt >= cfg.stale_peak_ms && roc < 0.0 => {
            PhysicalDecision::Lock("phys_lock_gate4_stale_roc_neg".to_string())
        }
        _ => PhysicalDecision::Hold,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // ═══════════════════════════════════════════════════════════════════════
    // DUAL-TRACK-EXIT-1 Phase 1b — physical_micro_profit_lock_v2 (non-linear)
    // DUAL-TRACK-EXIT-1 Phase 1b — 非線性 giveback 物理鎖定測試
    //
    // Tests 1-18 below map 1-to-1 to the operator's acceptance checklist
    // (Gate 1/2/3/4 coverage + non-linear giveback fn monotonicity + bounds
    // + ExitConfig validation + Option=None conservative paths).
    //
    // 下列 18 個測試對應 operator 驗收清單：Gate 1-4 覆蓋、non-linear giveback
    // 單調性、邊界、ExitConfig 驗證、Option=None 保守路徑。
    // ═══════════════════════════════════════════════════════════════════════

    /// Construct an all-pass ExitFeatures for v2 gating (Gate 4a disarmed, 4b disarmed).
    /// 構造 v2 全通 ExitFeatures；Gate 4a/4b 均未觸發。
    pub(super) fn mk_pass_features() -> ExitFeatures {
        ExitFeatures {
            est_net_bps: Some(50.0),          // >> 5.0 floor
            peak_pnl_pct: 2.0,                // 2% peak
            current_pnl_pct: 1.5,
            atr_pct: Some(1.0),               // 1% ATR → peak_atr_norm=2.0
            giveback_atr_norm: Some(0.0),     // zero giveback
            time_since_peak_ms: Some(0),      // peak just now
            price_roc_short: Some(0.01),      // positive (rising)
            entry_age_secs: Some(120.0),      // > 30s min_hold
        }
    }

    // ──────────────────────── Gate 1: net edge floor ────────────────────────

    /// Test 1 — Gate 1: est_net_bps below floor → Hold (design §三: only
    /// Gate 4 is a legal Lock path; low edge → protect micro-profit phase).
    /// 測試 1：淨邊緣低於底線 → Hold（設計 §三：只有 Gate 4 可鎖；低 edge
    /// 時保護微利期讓 edge 爬升）。
    #[test]
    fn test_v2_gate1_edge_below_floor_holds() {
        let cfg = ExitConfig::default();
        let mut f = mk_pass_features();
        f.est_net_bps = Some(1.0); // < 5.0 floor
        assert_eq!(
            physical_micro_profit_lock_v2(&f, &cfg),
            PhysicalDecision::Hold
        );
    }

    /// Test 2 — Gate 1 boundary: est_net_bps exactly at floor → Hold (<=).
    /// 測試 2：Gate 1 邊界 — 正好等於 floor → Hold（使用 <=）。
    #[test]
    fn test_v2_gate1_edge_exactly_floor_holds() {
        let cfg = ExitConfig::default();
        let mut f = mk_pass_features();
        f.est_net_bps = Some(5.0); // == 5.0 floor → <= → Hold (design-correct)
        assert_eq!(
            physical_micro_profit_lock_v2(&f, &cfg),
            PhysicalDecision::Hold
        );
    }

    // ──────────────────────── Gate 2: min hold time ────────────────────────

    /// Test 3 — Gate 2: entry_age_secs < min_hold → Hold (too fresh).
    /// 測試 3：持倉過短 → Hold。
    #[test]
    fn test_v2_gate2_fresh_entry_holds() {
        let cfg = ExitConfig::default();
        let mut f = mk_pass_features();
        f.entry_age_secs = Some(5.0);       // < 30s
        f.giveback_atr_norm = Some(10.0);   // would fire 4a otherwise
        assert_eq!(
            physical_micro_profit_lock_v2(&f, &cfg),
            PhysicalDecision::Hold
        );
    }

    /// Test 4 — Gate 2 boundary: entry_age_secs == min_hold → passes gate 2.
    /// 測試 4：Gate 2 邊界 — 正好等於 min_hold → 通過 (不因 gate2 Hold)。
    #[test]
    fn test_v2_gate2_exactly_at_min_hold_passes() {
        let cfg = ExitConfig::default();
        let mut f = mk_pass_features();
        f.entry_age_secs = Some(30.0);      // == 30s; `<` test → false → passes
        f.giveback_atr_norm = Some(10.0);   // far above threshold → fire 4a
        // With age exactly at bound, gate 2 passes → gate 4a fires because
        // giveback=10 >> threshold. If gate 2 wrongly blocked, we'd see Hold.
        // 若 gate 2 誤擋，此處會回 Hold；實際應因 gate 4a 觸發 Lock。
        assert_eq!(
            physical_micro_profit_lock_v2(&f, &cfg),
            PhysicalDecision::Lock("phys_lock_gate4_giveback".to_string())
        );
    }

    // ──────────────────────── Gate 3: peak height ────────────────────────

    /// Test 5 — Gate 3: peak_pnl_pct / atr_pct < min_peak_atr_norm → Hold.
    /// 測試 5：peak 高度（ATR 單位）不足 → Hold。
    #[test]
    fn test_v2_gate3_peak_below_atr_threshold_holds() {
        let cfg = ExitConfig::default();
        // cfg default: min_peak_atr_norm=0.5, atr=1.0 → required peak=0.5
        // cfg 預設：min_peak_atr_norm=0.5，atr=1.0，需 peak >= 0.5
        let mut f = mk_pass_features();
        f.peak_pnl_pct = 0.3;              // 0.3% < 0.5% required
        f.giveback_atr_norm = Some(10.0);  // would fire 4a otherwise
        assert_eq!(
            physical_micro_profit_lock_v2(&f, &cfg),
            PhysicalDecision::Hold
        );
    }

    // ──────────────────────── Gate 4a: non-linear giveback ────────────────

    /// Test 6 — Gate 4a: giveback ≥ non-linear threshold → Lock.
    /// 測試 6：Gate 4a — giveback ≥ 非線性閾值 → Lock。
    #[test]
    fn test_v2_gate4a_giveback_triggers_lock() {
        let cfg = ExitConfig::default();
        let mut f = mk_pass_features();
        // peak_atr_norm = 2.0; threshold = max(1.0 - 0.15*2.0, 0.3) = max(0.7, 0.3) = 0.7
        // Giveback 0.75 > 0.7 → Lock.
        // peak_atr_norm=2.0，閾值=0.7，giveback=0.75 → Lock。
        f.giveback_atr_norm = Some(0.75);
        assert_eq!(
            physical_micro_profit_lock_v2(&f, &cfg),
            PhysicalDecision::Lock("phys_lock_gate4_giveback".to_string())
        );
    }

    // ──────────────────────── Gate 4b: stale peak + neg ROC ────────────────

    /// Test 7 — Gate 4b: stale peak AND negative short-ROC → Lock (AND both).
    /// 測試 7：peak 陳舊 + 短 ROC 為負 (雙條件) → Lock。
    #[test]
    fn test_v2_gate4b_stale_and_decaying_locks() {
        let cfg = ExitConfig::default();
        let mut f = mk_pass_features();
        f.time_since_peak_ms = Some(120_000);   // >> 60_000
        f.price_roc_short = Some(-0.005);       // decaying
        assert_eq!(
            physical_micro_profit_lock_v2(&f, &cfg),
            PhysicalDecision::Lock("phys_lock_gate4_stale_roc_neg".to_string())
        );
    }

    /// Test 8 — Gate 4b: stale peak BUT ROC positive → Hold (not decaying).
    /// 測試 8：peak 陳舊但 ROC 為正 → Hold（仍在上行）。
    #[test]
    fn test_v2_gate4b_stale_but_positive_roc_holds() {
        let cfg = ExitConfig::default();
        let mut f = mk_pass_features();
        f.time_since_peak_ms = Some(120_000);   // stale
        f.price_roc_short = Some(0.008);        // rising
        assert_eq!(
            physical_micro_profit_lock_v2(&f, &cfg),
            PhysicalDecision::Hold
        );
    }

    /// Test 9 — Spike-wick scenario: fresh peak (low ts) + large giveback
    /// still fires 4a (by design — giveback is decisive). Proves 4a doesn't
    /// require peak staleness; 4b is the time-gated variant.
    /// 測試 9：spike wick — ts 很小（剛 peak）+ 大 giveback 仍觸 Gate 4a
    /// （設計如此，giveback 足夠就鎖）。驗證 4a 不依賴 peak 陳舊，4b 才是
    /// 時間門控變體。
    #[test]
    fn test_v2_spike_wick_giveback_fires_4a_not_4b() {
        let cfg = ExitConfig::default();
        let mut f = mk_pass_features();
        f.time_since_peak_ms = Some(100);       // very recent peak
        f.giveback_atr_norm = Some(1.5);        // large giveback
        f.price_roc_short = Some(0.0);          // flat — 4b disarmed
        let decision = physical_micro_profit_lock_v2(&f, &cfg);
        // Must fire 4a (giveback path), not 4b (stale+decaying).
        // 必須觸 4a 而非 4b。
        assert_eq!(
            decision,
            PhysicalDecision::Lock("phys_lock_gate4_giveback".to_string())
        );
    }

    /// Test 10 — Long-term winner: high peak + small giveback → Hold.
    /// (High peak lowers the threshold but a tiny retracement still clears it.)
    /// 測試 10：長期 winner — 高 peak + 小 giveback → Hold（雖閾值因高 peak
    /// 下調，但 giveback 仍未達）。
    #[test]
    fn test_v2_long_winner_small_giveback_holds() {
        let cfg = ExitConfig::default();
        let mut f = mk_pass_features();
        f.peak_pnl_pct = 3.0;                   // peak_atr_norm = 3.0
        f.giveback_atr_norm = Some(0.2);        // threshold = max(1-0.45, 0.3) = 0.55
        f.time_since_peak_ms = Some(0);
        f.price_roc_short = Some(0.0);
        assert_eq!(
            physical_micro_profit_lock_v2(&f, &cfg),
            PhysicalDecision::Hold
        );
    }

    // ─────────────────── Volatility normalisation boundary ───────────────────

    /// Test 11 — Same peak_pnl_pct but different atr_pct yield different
    /// decisions (volatility normalisation works).
    /// 測試 11：相同 peak_pnl_pct、不同 atr_pct → 判決不同（ATR 歸一化生效）。
    #[test]
    fn test_v2_volatility_normalisation_boundary() {
        let cfg = ExitConfig::default();
        // Same peak of 0.4%; low-vol symbol (atr=0.5%) → peak_atr_norm=0.8
        //   → threshold = max(1-0.12, 0.3) = 0.88 → giveback=0.9 > 0.88 → Lock.
        // High-vol symbol (atr=2.0%) → peak_atr_norm=0.2 → below gate3 (0.5)
        //   → Hold.
        // 同 peak=0.4%：低 vol (ATR=0.5%) → peak_atr_norm=0.8 → 閾值 0.88，
        // giveback=0.9 觸鎖；高 vol (ATR=2.0%) → peak_atr_norm=0.2 → Gate 3 擋。
        let mut f_low = mk_pass_features();
        f_low.peak_pnl_pct = 0.4;
        f_low.atr_pct = Some(0.5);
        f_low.giveback_atr_norm = Some(0.9);
        let d_low = physical_micro_profit_lock_v2(&f_low, &cfg);
        assert_eq!(
            d_low,
            PhysicalDecision::Lock("phys_lock_gate4_giveback".to_string()),
            "low-vol same-peak should trigger lock"
        );

        let mut f_high = mk_pass_features();
        f_high.peak_pnl_pct = 0.4;
        f_high.atr_pct = Some(2.0);
        f_high.giveback_atr_norm = Some(0.9);
        let d_high = physical_micro_profit_lock_v2(&f_high, &cfg);
        assert_eq!(
            d_high,
            PhysicalDecision::Hold,
            "high-vol same-peak should Hold via gate 3"
        );
    }

    // ────────────────── Non-linear giveback function properties ──────────────

    /// Test 12 — `non_linear_giveback_fn` at high peak returns floor.
    /// 測試 12：高 peak → 回傳 floor。
    #[test]
    fn test_non_linear_giveback_high_peak_returns_floor() {
        let cfg = ExitConfig::default();
        // base=1.0, slope=0.15 → at peak=10.0 raw value = 1 - 1.5 = -0.5, clamped to floor=0.3.
        // base=1.0、slope=0.15：peak=10 時原始值 -0.5，夾到 floor=0.3。
        let t = non_linear_giveback_fn(10.0, &cfg);
        assert!((t - cfg.giveback_floor).abs() < 1e-9, "got {t}");
    }

    /// Test 13 — `non_linear_giveback_fn` at zero peak returns base.
    /// 測試 13：peak=0 → 回傳 base。
    #[test]
    fn test_non_linear_giveback_zero_peak_returns_base() {
        let cfg = ExitConfig::default();
        let t = non_linear_giveback_fn(0.0, &cfg);
        assert!((t - cfg.giveback_base).abs() < 1e-9, "got {t}");
    }

    /// Test 14 — `non_linear_giveback_fn` is monotonically non-increasing
    /// across a sweep of peak_atr_norm values.
    /// 測試 14：peak_atr_norm 掃描下，閾值單調不遞增。
    #[test]
    fn test_non_linear_giveback_monotonic_non_increasing() {
        let cfg = ExitConfig::default();
        let mut last = non_linear_giveback_fn(0.0, &cfg);
        let mut peak = 0.0;
        while peak <= 10.0 {
            let t = non_linear_giveback_fn(peak, &cfg);
            assert!(
                t <= last + 1e-12,
                "giveback threshold must be non-increasing: peak={peak} t={t} last={last}"
            );
            last = t;
            peak += 0.25;
        }
    }

    // ─────────────────── ExitFeatures Option=None conservative ───────────────

    /// Test 15 — Missing est_net_bps → conservative Hold (NOT Lock).
    /// 測試 15：est_net_bps 缺失 → Hold（不 Lock，保守）。
    #[test]
    fn test_v2_missing_est_net_bps_is_conservative_hold() {
        let cfg = ExitConfig::default();
        let mut f = mk_pass_features();
        f.est_net_bps = None;
        f.giveback_atr_norm = Some(10.0); // would fire 4a if reached
        assert_eq!(
            physical_micro_profit_lock_v2(&f, &cfg),
            PhysicalDecision::Hold
        );
    }

    /// Test 16 — Missing atr_pct → Hold (cannot normalise peak).
    /// 測試 16：atr_pct 缺失 → Hold（無法正規化 peak）。
    #[test]
    fn test_v2_missing_atr_pct_holds() {
        let cfg = ExitConfig::default();
        let mut f = mk_pass_features();
        f.atr_pct = None;
        f.giveback_atr_norm = Some(10.0);
        assert_eq!(
            physical_micro_profit_lock_v2(&f, &cfg),
            PhysicalDecision::Hold
        );
    }

    // ─────────────────── ExitConfig validation ──────────────────────────────

    /// Test 17 — ExitConfig::default passes validate; sensible seed values.
    /// 測試 17：ExitConfig::default 通過 validate；基準值合理。
    #[test]
    fn test_exit_config_default_validates() {
        let cfg = ExitConfig::default();
        assert!(cfg.validate().is_ok(), "default cfg must validate");
        // Spot-check defaults match designer doc §三 seed values.
        // 抽查預設值與設計文檔 §三 對齊。
        assert!((cfg.min_net_floor_bps - 5.0).abs() < 1e-9);
        assert!((cfg.min_hold_secs - 30.0).abs() < 1e-9);
        assert!((cfg.min_peak_atr_norm - 0.5).abs() < 1e-9);
        assert_eq!(cfg.stale_peak_ms, 60_000);
        assert!(cfg.giveback_floor < cfg.giveback_base);
    }

    /// Test 18 — ExitConfig validate rejects floor > base (logical error).
    /// 測試 18：floor > base 為邏輯錯誤，validate 拒絕。
    #[test]
    fn test_exit_config_validate_rejects_floor_above_base() {
        let mut cfg = ExitConfig::default();
        cfg.giveback_floor = 2.0;
        cfg.giveback_base = 1.0;
        let r = cfg.validate();
        assert!(r.is_err(), "floor > base must be rejected");
        let msg = r.unwrap_err();
        assert!(msg.contains("giveback_floor"), "err msg: {msg}");
    }

    // ─────────────────── Extra coverage (defensive) ───────────────────────────

    /// Test 20 — ExitConfig serde round-trip preserves every field.
    /// 測試 20：ExitConfig serde 往返保留每個欄位。
    #[test]
    fn test_exit_config_serde_round_trip() {
        let cfg = ExitConfig {
            min_net_floor_bps: 7.5,
            min_hold_secs: 45.0,
            min_peak_atr_norm: 0.6,
            stale_peak_ms: 90_000,
            giveback_base: 1.25,
            giveback_slope: 0.2,
            giveback_floor: 0.4,
            missing_edge_fallback_bps: -7.5,
        };
        let j = serde_json::to_string(&cfg).expect("ser");
        let back: ExitConfig = serde_json::from_str(&j).expect("de");
        assert_eq!(cfg, back);
    }

    /// Test 21 — `non_linear_giveback_fn` rejects NaN / negative peak_atr_norm
    /// gracefully (clamp to 0 → returns base; never NaN).
    /// 測試 21：non_linear_giveback_fn 在 NaN / 負值輸入下夾到 0，絕不回 NaN。
    #[test]
    fn test_non_linear_giveback_handles_bad_input() {
        let cfg = ExitConfig::default();
        let t_nan = non_linear_giveback_fn(f64::NAN, &cfg);
        assert!(t_nan.is_finite(), "must be finite, got {t_nan}");
        assert!(
            (t_nan - cfg.giveback_base).abs() < 1e-9,
            "NaN clamps to 0 → base, got {t_nan}"
        );
        let t_neg = non_linear_giveback_fn(-5.0, &cfg);
        assert!(
            (t_neg - cfg.giveback_base).abs() < 1e-9,
            "negative clamps to 0 → base, got {t_neg}"
        );
        let t_inf = non_linear_giveback_fn(f64::INFINITY, &cfg);
        assert!(t_inf.is_finite());
    }

    /// Test 22 — Gate ordering precedence: Gate 1 early-returns Hold before
    /// any later gate evaluates. Verifies the short-circuit stays intact
    /// under v2 semantics (Gate 1 Hold instead of Lock).
    /// 測試 22：Gate 順序 — Gate 1 低 edge 時 early-return Hold，後續 gate
    /// 不執行。驗證 v2 語意下 Gate 1 的短路仍成立（Hold 取代原 Lock）。
    #[test]
    fn test_v2_gate_ordering_gate1_beats_later_holds() {
        let cfg = ExitConfig::default();
        let mut f = mk_pass_features();
        f.est_net_bps = Some(0.5);          // below floor → Gate 1 Hold
        f.entry_age_secs = Some(1.0);       // would Hold at Gate 2 too
        f.atr_pct = None;                   // would Hold at Gate 3 too
        // Gate 1 short-circuits → Hold (without touching gates 2/3/4).
        // Gate 1 短路 → Hold（不碰 Gate 2/3/4）。
        assert_eq!(
            physical_micro_profit_lock_v2(&f, &cfg),
            PhysicalDecision::Hold
        );
    }

    /// Test 23 — Gate 4b boundary: time_since_peak_ms exactly at stale_peak_ms
    /// and roc < 0 → Lock (use `>=`).
    /// 測試 23：Gate 4b 邊界 — time_since_peak_ms 正好等於 stale_peak_ms 且
    /// ROC 負 → Lock（使用 >=）。
    #[test]
    fn test_v2_gate4b_stale_boundary_equal_locks() {
        let cfg = ExitConfig::default();
        let mut f = mk_pass_features();
        f.time_since_peak_ms = Some(60_000);  // == default stale_peak_ms
        f.price_roc_short = Some(-0.001);
        assert_eq!(
            physical_micro_profit_lock_v2(&f, &cfg),
            PhysicalDecision::Lock("phys_lock_gate4_stale_roc_neg".to_string())
        );
    }

    /// Test 24 — All-pass features → Hold (no lock triggers).
    /// 測試 24：全通特徵 → Hold（無鎖定觸發）。
    #[test]
    fn test_v2_all_pass_features_hold() {
        let cfg = ExitConfig::default();
        let f = mk_pass_features();
        assert_eq!(
            physical_micro_profit_lock_v2(&f, &cfg),
            PhysicalDecision::Hold
        );
    }

    /// P0-14 Option A — Gate 1: `est_net_bps=None` uses the configured
    /// `missing_edge_fallback_bps`; when fallback ≤ floor → Hold (default).
    /// 預設 fallback (-10.0) ≤ floor (5.0) → Hold（與修復前 fail-safe 一致）。
    #[test]
    fn test_v2_gate1_missing_edge_uses_fallback_below_floor() {
        let cfg = ExitConfig {
            missing_edge_fallback_bps: -10.0,
            min_net_floor_bps: 5.0,
            ..ExitConfig::default()
        };
        let mut f = mk_pass_features();
        f.est_net_bps = None;
        // fallback=-10 ≤ floor=5 → Gate 1 Holds (preserves fail-safe).
        // fallback=-10 ≤ floor=5 → Gate 1 Hold（維持 fail-safe）。
        assert_eq!(
            physical_micro_profit_lock_v2(&f, &cfg),
            PhysicalDecision::Hold
        );
    }

    /// P0-14 Option A — Gate 1: `est_net_bps=None` with a fallback raised
    /// above the floor escalates past Gate 1 so later gates can evaluate.
    /// Here we use `mk_pass_features` (all-pass) → Gate 1 passes, 2/3 pass,
    /// Gate 4a/4b unarmed (giveback=0, roc>0, ts=0) → final Hold; the key
    /// assertion is that Gate 1 does NOT short-circuit Hold on missing edge
    /// when fallback > floor. Same decision as `test_v2_all_pass_features_hold`.
    /// P0-14 A：fallback 調高於 floor 時 missing edge 不再於 Gate 1 短路，
    /// 流入後續 gate；本例 mk_pass_features 其他 gate 全 pass、4a/4b 未觸發
    /// → 最終 Hold，關鍵是不因 Gate 1 missing edge 被 Hold。
    #[test]
    fn test_v2_gate1_missing_edge_fallback_above_floor_passes_to_gate2() {
        let cfg = ExitConfig {
            missing_edge_fallback_bps: 20.0,
            min_net_floor_bps: 5.0,
            ..ExitConfig::default()
        };
        let mut f = mk_pass_features();
        f.est_net_bps = None; // Gate 1 falls back to 20 bps > 5 floor → pass
        // If Gate 1 still short-circuited Hold on None, we'd not reach Gate
        // 4a. Confirm we pass Gate 1 by arming Gate 4a and asserting Lock.
        // 透過武裝 Gate 4a 反向證明 Gate 1 未短路 Hold — 若仍 Hold 則退化。
        f.giveback_atr_norm = Some(0.75); // threshold @ peak_atr_norm=2 is 0.7
        assert_eq!(
            physical_micro_profit_lock_v2(&f, &cfg),
            PhysicalDecision::Lock("phys_lock_gate4_giveback".to_string()),
            "fallback above floor must pass Gate 1 so Gate 4a can fire"
        );
    }

    /// Test 25 — End-to-end design intent: after Gate 1 Hold (edge just
    /// above floor post-climb), Gate 4a trailing Lock still fires on a
    /// giveback. Verifies the Gate 1→Hold change does not block the legal
    /// Lock path.
    ///
    /// 場景：edge 剛過底線（10 bps > 5 bps floor），peak 拉高 + 回吐觸發 trailing。
    /// Scenario: edge just above floor after climbing, peak high with giveback → Gate 4a Lock.
    /// 驗證 Gate 1 改 Hold 後仍能走到 Gate 4 trailing 路徑。
    /// Verify Gate 1→Hold change does not break the Gate 4a trailing Lock path.
    #[test]
    fn test_v2_gate1_hold_then_gate4_trailing_locks() {
        let cfg = ExitConfig::default();
        let f = ExitFeatures {
            est_net_bps: Some(10.0),           // 10 bps > 5.0 floor → pass Gate 1
            peak_pnl_pct: 2.5,
            current_pnl_pct: 1.2,
            atr_pct: Some(1.0),                 // peak_atr_norm = 2.5 > 0.5 min
            giveback_atr_norm: Some(1.3),       // > threshold @ peak_atr_norm=2.5 which is max(1.0-0.15*2.5, 0.3)=0.625
            time_since_peak_ms: Some(5_000),
            price_roc_short: Some(-0.001),
            entry_age_secs: Some(120.0),
        };
        assert_eq!(
            physical_micro_profit_lock_v2(&f, &cfg),
            PhysicalDecision::Lock("phys_lock_gate4_giveback".to_string())
        );
    }
}
