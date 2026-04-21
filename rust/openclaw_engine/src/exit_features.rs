//! Track P 物理層退場特徵 / Track P physical-layer exit features
//!
//! 共享型別：供 T3 (physical_micro_profit_lock) 與 T4 (combine_layer) 使用。
//! Shared types used by T3 and T4 (DUAL-TRACK-EXIT-1 Track P skeleton).
//!
//! ## Phase 1b Track P (a+b+c+e) — 2026-04-21
//!
//! This module exposes the **non-linear giveback** variant of the physical
//! micro-profit lock as a pure function (`physical_micro_profit_lock_v2`) so
//! the same 4-gate logic can be replayed offline / used by Combine Layer
//! without pulling in `risk_checks.rs` state. The legacy linear-threshold
//! version (`risk_checks::physical_micro_profit_lock` + `PhysLockConfig`)
//! remains wired into `check_position_on_tick` Priority 6 unchanged; the next
//! wave swaps Priority 6 to consume `ExitConfig` here.
//!
//! 本模組將 `physical_micro_profit_lock_v2` 以 pure fn 形式曝露（含非線性
//! giveback 閾值），讓相同 4 Gate 邏輯可離線重放 / 供 Combine Layer 使用而
//! 無需 `risk_checks.rs` 狀態。舊線性閾值版 (`risk_checks::physical_micro_profit_lock`
//! + `PhysLockConfig`) 仍在 Priority 6 運作；下一波再替換為讀取本模組 `ExitConfig`。
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
//! v1 (`risk_checks::physical_micro_profit_lock` Priority 6) implements
//! `edge <= floor → Lock`, which contradicts the design doc. v2 here is
//! corrected to `edge <= floor → Hold`; v1's matching fix is deferred to the
//! next wave that replaces Priority 6 with this ExitConfig consumer. Until
//! then, runtime behaviour (Priority 6 unchanged) and v2 behaviour (Hold on
//! low edge) diverge by design — v2 matches the doc, v1 still carries the
//! legacy bug.
//!
//! ### Gate 1 語意 — v2 修正 v1（2026-04-21）
//!
//! DUAL-TRACK-EXIT-1 設計意圖（§三 L108-111）：「防止剛有大於 fee 的微利就
//! 套利離場；保證 trailing stop；追求最高單筆 close 盈利。」因此**只有 Gate 4
//! (trailing) 才是合法的 Lock 路徑**。`est_net_bps` 低於底線時必須 **Hold**
//! 讓 position 繼續跑，直到 edge 爬到底線上方再經後續 gate 評估，或 peak
//! 成形後 Gate 4 因 giveback 觸發。
//!
//! v1（`risk_checks::physical_micro_profit_lock` Priority 6）實作為
//! `edge <= floor → Lock`，違反設計文檔。本模組 v2 已修正為 `edge <= floor → Hold`；
//! v1 的對應修正留待下一波以本 ExitConfig 取代 Priority 6 時統一處理。在此
//! 之前，runtime 行為（Priority 6 不變）與 v2 行為（低 edge 時 Hold）有意
//! 分歧 — v2 對齊文檔，v1 仍留 legacy bug。

/// 物理層退場決策特徵快照 / Physical-layer exit decision feature snapshot.
///
/// 任何 Option 欄位為 None 代表「歷史/樣本不足」，下游 gate 須保守（Hold）。
/// None means insufficient history/samples; downstream gates must be conservative.
///
/// T1-FIX: `serde::Serialize` + `serde::Deserialize` 供未來 EXIT-FEATURES-TABLE 持久化 /
/// consumer。`Deserialize` 包含以支持單元測試的 round-trip，Phase 1b+ 的離線
/// replay/fixture 管線亦會用到。
/// T1-FIX: `Serialize` + `Deserialize` for future EXIT-FEATURES-TABLE persistence
/// consumer. `Deserialize` included to support unit-test round-trips and the
/// Phase 1b+ offline replay/fixture pipeline.
#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct ExitFeatures {
    /// Shrunk JS edge（bps）; None = cell 缺失 / missing cell
    pub est_net_bps: Option<f32>,
    /// 此 position 自 entry 後曾達的最大 favorable PnL %（side-signed）
    /// Position's peak side-signed favorable PnL % since entry
    pub peak_pnl_pct: f32,
    /// 當前 tick 的 side-signed PnL % / Current side-signed PnL %
    pub current_pnl_pct: f64,
    /// ATR %（price_tracker.compute_atr_pct） / ATR percentage
    pub atr_pct: Option<f64>,
    /// 從 peak 回吐幅度以 ATR 正規化 / Giveback from peak normalised by ATR
    pub giveback_atr_norm: Option<f32>,
    /// 自 peak 以來的毫秒 / Milliseconds since peak
    pub time_since_peak_ms: Option<i64>,
    /// 短期 (≈300ms) 價格變化率 / Short-horizon price rate-of-change
    pub price_roc_short: Option<f32>,
    /// Position 存活秒數 / Entry age in seconds
    pub entry_age_secs: Option<f32>,
}

/// Track P 物理層決策 / Track P physical-layer decision.
///
/// T1-FIX: `serde::Serialize` + `serde::Deserialize` 同 ExitFeatures，供持久化
/// 與 round-trip 測試。
/// T1-FIX: `Serialize` + `Deserialize` as ExitFeatures, for persistence and
/// round-trip tests.
#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub enum PhysicalDecision {
    /// 維持持有 / Continue holding
    Hold,
    /// 鎖定退場，附原因字串（寫入 fills.details 供歸因）
    /// Lock-and-exit, reason string persisted to fills.details for audit trail
    Lock(String),
}

// ===========================================================================
// ExitConfig — non-linear giveback parameters for Track P v2
// ExitConfig — Track P v2 非線性 giveback 參數
// ===========================================================================

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
    // Gate 1：淨邊緣底線 — edge 不足時保守 Hold（防止微利即套離場）。
    match f.est_net_bps {
        Some(edge) if f64::from(edge) <= cfg.min_net_floor_bps => {
            return PhysicalDecision::Hold;
        }
        Some(_) => {} // edge above floor → proceed to later gates
        None => return PhysicalDecision::Hold, // unknown → conservative Hold
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

// ===========================================================================
// TRACK-P-T4-WIRING-1 (2026-04-21) — tick-time ExitFeatures builder
// TRACK-P-T4-WIRING-1 (2026-04-21) — 即時 (tick-time) ExitFeatures 建構器
// ===========================================================================

/// DUAL-TRACK-EXIT-1 Track P **T4 wiring** (2026-04-21): assemble an
/// `ExitFeatures` snapshot for a **live** position on every tick (mid-life),
/// so the Priority-6 4-Gate `physical_micro_profit_lock` (v1 linear / v2
/// non-linear) can actually fire. Before T4, `tick_pipeline/on_tick.rs`
/// hard-coded `|_| None` and Priority-6 was inert in production (0 fires
/// observed over the full decision_outcomes history; see
/// `memory/project_track_p_runtime_dead.md`).
///
/// Mirrors the close-time derivation inside `tick_pipeline::build_exit_feature_row`
/// so label/feature semantics stay stable between mid-life decision input and
/// post-close DB row, with one difference: no `realized_net_bps` (the position
/// is still open) and no `exit_source` tag (no close happened yet).
///
/// **Purity**: no I/O, no allocation beyond returning `ExitFeatures`. All six
/// derived fields (peak/current pnl, giveback, time-since-peak, entry age;
/// plus the two caller-supplied market-layer fields `atr_pct` and
/// `price_roc_short`; plus `est_net_bps` from the edge-estimates cache) are
/// computed from scalar inputs. Designed for unit tests that don't spin up a
/// full `TickPipeline`.
///
/// **Fail-soft**: any `Option::None` in outputs propagates to the 4-Gate lock
/// which responds with a conservative Hold (pre-T3 semantics). No panic path.
///
/// ### Inputs
/// - `snap`           : snapshot of the live position (not pre-close — any
///                      call time during the position's life). Use
///                      `PaperState::position_exit_snapshot(symbol)`.
/// - `current_price`  : latest tick price for `snap.symbol`.
/// - `atr_pct`        : `price_tracker.compute_atr_pct(symbol)`; `None` until
///                      the tracker has enough samples.
/// - `price_roc_short`: `price_tracker.compute_roc(symbol, 300)` (300 ms
///                      short-horizon ROC); `None` until ≥ 2 samples in window.
/// - `est_net_bps`    : `EdgeEstimates::get_cell(snap.owner_strategy, symbol)
///                      .map(|c| c.shrunk_bps as f32)`; `None` on cache miss.
/// - `ts_ms`          : wall-clock tick timestamp (same as `event.ts_ms`).
///
/// ### Derivations (match `tick_pipeline::build_exit_feature_row` at close)
/// - `peak_pnl_pct`       = `snap.max_favorable_pnl_pct`
/// - `current_pnl_pct`    = side-signed `(current_price − snap.entry_price) /
///                          snap.entry_price × 100`; defensive 0.0 when
///                          `snap.entry_price ≤ 0` or non-finite.
/// - `giveback_atr_norm`  = `(peak_pnl_pct − current_pnl_pct) / atr_pct`,
///                          clamped to `0` when current exceeds peak (fresh
///                          high); `None` when `atr_pct` is `None | ≤ 0 |
///                          non-finite`.
/// - `time_since_peak_ms` = `max(ts_ms_i64 − snap.peak_reached_ts_ms, 0)`;
///                          `None` when `snap.peak_reached_ts_ms == 0`
///                          (legacy snapshot, no peak tracked yet).
/// - `entry_age_secs`     = `(ts_ms − snap.entry_ts_ms) / 1000`; `None` when
///                          `ts_ms < snap.entry_ts_ms` (clock skew guard).
///
/// DUAL-TRACK-EXIT-1 Track P **T4 接線**（2026-04-21）：對活躍持倉每 tick
/// 計算 ExitFeatures 快照，讓 Priority 6 4-Gate `physical_micro_profit_lock`
/// 實際能 fire。T4 接線前 `tick_pipeline/on_tick.rs` 硬編碼 `|_| None`，
/// Priority 6 在生產 0 次觸發（見 `memory/project_track_p_runtime_dead.md`）。
///
/// 衍生規則鏡像 close-time `tick_pipeline::build_exit_feature_row`，保持
/// mid-life 決策輸入與 post-close DB row 語意一致。差異：無 `realized_net_bps`
/// （持倉未平）、無 `exit_source` 標籤（尚未 close）。
///
/// **純函數**：無 I/O / 除回傳 ExitFeatures 外零分配；可脫離 TickPipeline 單測。
/// **Fail-soft**：任一 `Option::None` 透傳至 4-Gate 保守 Hold（pre-T3 語意）。
pub fn build_exit_features_for_tick(
    snap: &crate::paper_state::PositionExitSnapshot,
    current_price: f64,
    atr_pct: Option<f64>,
    price_roc_short: Option<f32>,
    est_net_bps: Option<f32>,
    ts_ms: u64,
) -> ExitFeatures {
    let ts_ms_i64 = ts_ms as i64;

    // current_pnl_pct (side-signed, in %); defensive against entry_price ≤ 0
    // or non-finite (would have failed the open path, but guard anyway).
    // current_pnl_pct（side-signed，單位 %）；entry_price 非正或非有限時回 0
    // （開倉路徑早已過濾，防禦性守衛）。
    let current_pnl_pct = if snap.entry_price > 0.0 && snap.entry_price.is_finite() {
        let side = if snap.is_long { 1.0f64 } else { -1.0f64 };
        ((current_price - snap.entry_price) / snap.entry_price) * 100.0 * side
    } else {
        0.0
    };

    let peak_pnl_pct = snap.max_favorable_pnl_pct;

    // giveback_atr_norm: (peak − current) / atr in %-normalised units; clamped
    // to 0 if current exceeds peak (fresh high mid-life).
    // giveback_atr_norm：(peak − current) / atr；current 超過 peak 時夾回 0。
    let giveback_atr_norm = match atr_pct {
        Some(atr) if atr > 0.0 && atr.is_finite() => {
            let gb = f64::from(peak_pnl_pct) - current_pnl_pct;
            if gb < 0.0 {
                Some(0.0f32)
            } else {
                Some((gb / atr) as f32)
            }
        }
        _ => None,
    };

    // time_since_peak_ms: None when legacy snapshot with peak_reached_ts_ms=0
    // (pre-EXIT-FEATURES-TABLE-1 before update_best_prices_at ran even once),
    // else saturating non-negative delta.
    // time_since_peak_ms：legacy 快照（peak_reached_ts_ms=0）回 None，否則
    // 以飽和非負差值回傳。
    let time_since_peak_ms = if snap.peak_reached_ts_ms > 0 {
        Some((ts_ms_i64 - snap.peak_reached_ts_ms).max(0))
    } else {
        None
    };

    // entry_age_secs: clock-skew guard — None if ts_ms < entry_ts_ms.
    // entry_age_secs：時鐘倒流守衛 — ts_ms < entry_ts_ms 時回 None。
    let entry_age_secs = if ts_ms >= snap.entry_ts_ms {
        Some(((ts_ms - snap.entry_ts_ms) as f32) / 1000.0)
    } else {
        None
    };

    ExitFeatures {
        est_net_bps,
        peak_pnl_pct,
        current_pnl_pct,
        atr_pct,
        giveback_atr_norm,
        time_since_peak_ms,
        price_roc_short,
        entry_age_secs,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_exit_features_construction_round_trip() {
        let f = ExitFeatures {
            est_net_bps: Some(12.5),
            peak_pnl_pct: 1.75,
            current_pnl_pct: 1.20,
            atr_pct: Some(0.45),
            giveback_atr_norm: Some(0.8),
            time_since_peak_ms: Some(1500),
            price_roc_short: Some(-0.002),
            entry_age_secs: Some(45.0),
        };
        // Debug 可格式化（不 panic）
        let dbg = format!("{:?}", f);
        assert!(dbg.contains("ExitFeatures"));
        // Clone + PartialEq
        let g = f.clone();
        assert_eq!(f, g);
    }

    #[test]
    fn test_exit_features_none_fields_allowed() {
        let f = ExitFeatures {
            est_net_bps: None,
            peak_pnl_pct: 0.0,
            current_pnl_pct: 0.0,
            atr_pct: None,
            giveback_atr_norm: None,
            time_since_peak_ms: None,
            price_roc_short: None,
            entry_age_secs: None,
        };
        // 構造成功且可 clone/eq
        let g = f.clone();
        assert_eq!(f, g);
        assert!(f.est_net_bps.is_none());
        assert!(f.atr_pct.is_none());
        assert!(f.giveback_atr_norm.is_none());
        assert!(f.time_since_peak_ms.is_none());
        assert!(f.price_roc_short.is_none());
        assert!(f.entry_age_secs.is_none());
    }

    #[test]
    fn test_physical_decision_variants_equality() {
        let hold = PhysicalDecision::Hold;
        let lock_a = PhysicalDecision::Lock("a".to_string());
        let lock_b = PhysicalDecision::Lock("b".to_string());
        let lock_x_1 = PhysicalDecision::Lock("x".to_string());
        let lock_x_2 = PhysicalDecision::Lock("x".to_string());

        assert_ne!(hold, lock_a);
        assert_ne!(lock_a, lock_b);
        assert_eq!(lock_x_1, lock_x_2);
    }

    // T1-FIX: Serialize boundary tests / Serialize 邊界測試
    // 驗證 None / 0.0 / stale_peak 邊界條件可安全序列化，未來 EXIT-FEATURES-TABLE
    // 持久化消費者不會在邊界值爆掉。
    // Ensure None / 0.0 / stale_peak boundary values serialise safely; future
    // EXIT-FEATURES-TABLE persistence consumers will not blow up on edges.

    #[test]
    fn test_exit_features_est_net_bps_none_serializes() {
        // est_net_bps=None（cell 缺失）必須序列化為 JSON null，
        // 下游 writer/reader 不可依賴欄位必定為數字。
        // est_net_bps=None (missing cell) must serialise to JSON null; downstream
        // writers/readers must not assume the field is always numeric.
        let f = ExitFeatures {
            est_net_bps: None,
            peak_pnl_pct: 0.0,
            current_pnl_pct: 0.0,
            atr_pct: None,
            giveback_atr_norm: None,
            time_since_peak_ms: None,
            price_roc_short: None,
            entry_age_secs: None,
        };
        let j = serde_json::to_string(&f).expect("serialize");
        assert!(
            j.contains("\"est_net_bps\":null"),
            "expected est_net_bps:null in {}",
            j
        );
    }

    #[test]
    fn test_exit_features_atr_pct_zero_boundary() {
        // atr_pct=Some(0.0) 為合法構造（波動性為 0 的極端邊界），
        // 僅驗證 ctor + serialize 無 panic；gate 語意歸屬 risk_checks。
        // atr_pct=Some(0.0) is a valid boundary (degenerate volatility); we only
        // check that ctor + serialize do not panic. Gate semantics live in
        // risk_checks.
        let f = ExitFeatures {
            est_net_bps: Some(10.0),
            peak_pnl_pct: 1.0,
            current_pnl_pct: 0.5,
            atr_pct: Some(0.0),
            giveback_atr_norm: Some(0.0),
            time_since_peak_ms: Some(0),
            price_roc_short: Some(0.0),
            entry_age_secs: Some(0.0),
        };
        let j = serde_json::to_string(&f).expect("serialize");
        // atr_pct serialises as 0.0 (serde-json renders floats with decimal).
        // atr_pct 序列化為 0.0（serde-json 浮點帶小數點）。
        assert!(
            j.contains("\"atr_pct\":0.0"),
            "expected atr_pct:0.0 in {}",
            j
        );
    }

    #[test]
    fn test_exit_features_time_since_peak_stale_boundary() {
        // stale_peak_ms 預設 60_000ms（risk_config.phys_lock）——邊界等值值的
        // round-trip 必須完全還原。
        // Default stale_peak_ms is 60_000 (risk_config.phys_lock); boundary-equal
        // value must round-trip losslessly.
        let original = ExitFeatures {
            est_net_bps: Some(-25.0),
            peak_pnl_pct: 0.3,
            current_pnl_pct: 0.1,
            atr_pct: Some(0.5),
            giveback_atr_norm: Some(1.2),
            time_since_peak_ms: Some(60_000),
            price_roc_short: Some(-0.001),
            entry_age_secs: Some(120.0),
        };
        let j = serde_json::to_string(&original).expect("serialize");
        let decoded: ExitFeatures = serde_json::from_str(&j).expect("deserialize");
        assert_eq!(original, decoded, "round-trip must be lossless");
    }

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
    fn mk_pass_features() -> ExitFeatures {
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

    /// Test 19 — ExitFeatures + PhysicalDecision composability: a Hold
    /// decision round-trips through serde (no panic, equal after decode).
    /// 測試 19：Hold 決策可經 serde 往返。
    #[test]
    fn test_physical_decision_hold_serde_round_trip() {
        let d = PhysicalDecision::Hold;
        let j = serde_json::to_string(&d).expect("ser");
        let back: PhysicalDecision = serde_json::from_str(&j).expect("de");
        assert_eq!(d, back);
    }

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

    // -----------------------------------------------------------------------
    // TRACK-P-T4-WIRING-1 builder tests
    // TRACK-P-T4-WIRING-1 建構器測試
    // -----------------------------------------------------------------------

    /// Minimal snapshot helper for builder tests. Side + entry_ts_ms +
    /// peak_reached_ts_ms + entry_price + max_favorable_pnl_pct cover the
    /// full derivation surface; remaining fields are harmless defaults.
    /// Builder 測試用最小 snapshot helper。覆蓋 side / entry_ts_ms /
    /// peak_reached_ts_ms / entry_price / max_favorable_pnl_pct 五個衍生源。
    fn mk_snap(
        is_long: bool,
        entry_price: f64,
        max_favorable_pnl_pct: f32,
        entry_ts_ms: u64,
        peak_reached_ts_ms: i64,
    ) -> crate::paper_state::PositionExitSnapshot {
        crate::paper_state::PositionExitSnapshot {
            symbol: "BTCUSDT".to_string(),
            is_long,
            qty_at_snapshot: 0.1,
            entry_price,
            entry_ts_ms,
            entry_fee: 0.0,
            max_favorable_pnl_pct,
            peak_reached_ts_ms,
            owner_strategy: "bb_breakout".to_string(),
            entry_context_id: String::new(),
            entry_notional: 0.1 * entry_price,
        }
    }

    /// Happy path: long in profit, every input populated. All 8 fields emerge
    /// fully populated; arithmetic of current_pnl / giveback matches hand-computed.
    /// 長倉盈利，每個輸入皆有值；8 欄位完整，current_pnl / giveback 對齊手算值。
    #[test]
    fn test_build_for_tick_long_profit_happy() {
        // Entry 100 → current 103 → +3% side=+1, peak already 4% (price hit 104 earlier).
        let snap = mk_snap(true, 100.0, 4.0, 1_000_000, 1_005_000);
        let f = build_exit_features_for_tick(
            &snap,
            103.0,
            Some(1.5),            // atr_pct
            Some(-0.0012),        // price_roc_short
            Some(12.5),           // est_net_bps
            1_010_000,            // ts_ms
        );
        assert_eq!(f.est_net_bps, Some(12.5));
        assert_eq!(f.peak_pnl_pct, 4.0);
        assert!((f.current_pnl_pct - 3.0).abs() < 1e-9);
        assert_eq!(f.atr_pct, Some(1.5));
        // giveback = (4 - 3) / 1.5 ≈ 0.6667
        let gb = f.giveback_atr_norm.expect("giveback should compute");
        assert!((gb - 0.6667).abs() < 1e-3);
        // time_since_peak_ms = 1_010_000 - 1_005_000 = 5_000
        assert_eq!(f.time_since_peak_ms, Some(5_000));
        assert_eq!(f.price_roc_short, Some(-0.0012));
        // entry_age_secs = (1_010_000 - 1_000_000) / 1000 = 10.0
        assert_eq!(f.entry_age_secs, Some(10.0));
    }

    /// Short-side symmetry: entry 100, current 97 → +3% side=-1 still +3.
    /// 空倉對稱：entry 100 / current 97 → +3% PnL。
    #[test]
    fn test_build_for_tick_short_profit_side_sign() {
        let snap = mk_snap(false, 100.0, 3.5, 0, 100);
        let f = build_exit_features_for_tick(&snap, 97.0, Some(1.0), None, None, 1_000);
        assert!((f.current_pnl_pct - 3.0).abs() < 1e-9);
        assert_eq!(f.peak_pnl_pct, 3.5);
        // giveback = (3.5 - 3.0) / 1.0 = 0.5
        let gb = f.giveback_atr_norm.expect("giveback should compute");
        assert!((gb - 0.5).abs() < 1e-6);
    }

    /// Current above peak (fresh high mid-tick) → giveback clamped to 0,
    /// not a negative number. Guards against `physical_micro_profit_lock_v2`
    /// picking a bogus Lock via a negative giveback accidentally matching.
    /// 當前 PnL 高於 peak（tick 中突破新高）→ giveback 夾回 0，不得為負。
    #[test]
    fn test_build_for_tick_giveback_clamped_to_zero_when_fresh_high() {
        let snap = mk_snap(true, 100.0, 2.0, 0, 100);
        let f = build_exit_features_for_tick(&snap, 105.0, Some(1.0), None, None, 1_000);
        // current_pnl = +5%, peak = +2% → raw giveback = -3 → clamp to 0.
        assert_eq!(f.giveback_atr_norm, Some(0.0));
    }

    /// ATR `None` → giveback `None`; all other deterministic fields still filled.
    /// Ensures 4-Gate Gate 3 sees `atr_pct=None` and Holds rather than panicking.
    /// atr=None → giveback=None；其他確定性欄位仍填值。
    #[test]
    fn test_build_for_tick_atr_none_giveback_none() {
        let snap = mk_snap(true, 100.0, 2.0, 0, 100);
        let f = build_exit_features_for_tick(&snap, 101.0, None, None, Some(7.0), 1_000);
        assert_eq!(f.atr_pct, None);
        assert_eq!(f.giveback_atr_norm, None);
        assert_eq!(f.est_net_bps, Some(7.0));
        assert_eq!(f.peak_pnl_pct, 2.0);
    }

    /// ATR ≤ 0 (pathological tracker output) → giveback `None`, no division.
    /// ATR ≤ 0（病態 tracker 回值）→ giveback=None，不做除法。
    #[test]
    fn test_build_for_tick_atr_nonpositive_giveback_none() {
        let snap = mk_snap(true, 100.0, 2.0, 0, 100);
        let f_zero = build_exit_features_for_tick(&snap, 101.0, Some(0.0), None, None, 1_000);
        assert_eq!(f_zero.giveback_atr_norm, None);
        let f_neg = build_exit_features_for_tick(&snap, 101.0, Some(-0.5), None, None, 1_000);
        assert_eq!(f_neg.giveback_atr_norm, None);
        let f_nan = build_exit_features_for_tick(&snap, 101.0, Some(f64::NAN), None, None, 1_000);
        assert_eq!(f_nan.giveback_atr_norm, None);
    }

    /// Legacy snapshot with `peak_reached_ts_ms == 0` → `time_since_peak_ms`
    /// is `None` (rather than a huge number), matching the close-time
    /// derivation in `tick_pipeline::build_exit_feature_row`.
    /// legacy snapshot（peak_reached_ts_ms=0）→ time_since_peak_ms=None，
    /// 與 close-time 衍生對齊，避免泄漏巨大時間差。
    #[test]
    fn test_build_for_tick_legacy_peak_ts_none() {
        let snap = mk_snap(true, 100.0, 1.0, 0, 0);
        let f = build_exit_features_for_tick(&snap, 100.5, Some(1.0), None, None, 5_000);
        assert_eq!(f.time_since_peak_ms, None);
    }

    /// Non-legacy peak-ts; `time_since_peak_ms` is a non-negative delta even
    /// when `ts_ms == peak_reached_ts_ms` (i.e. same tick as peak hit).
    /// 非 legacy；即便 ts_ms == peak_reached_ts_ms 也回 0（不溢位為負）。
    #[test]
    fn test_build_for_tick_peak_same_tick_zero() {
        let snap = mk_snap(true, 100.0, 1.0, 0, 2_000);
        let f = build_exit_features_for_tick(&snap, 101.0, Some(1.0), None, None, 2_000);
        assert_eq!(f.time_since_peak_ms, Some(0));
    }

    /// Clock skew: `ts_ms < snap.entry_ts_ms` (restored from persisted state
    /// whose entry is after tick ts, or out-of-order event) → `entry_age_secs`
    /// is `None`, not a negative/underflowed value. Gate 2 then Holds.
    /// 時鐘倒流：ts_ms < entry_ts_ms → entry_age_secs=None（非負值/下溢）。
    /// Gate 2 將 Hold。
    #[test]
    fn test_build_for_tick_clock_skew_entry_age_none() {
        let snap = mk_snap(true, 100.0, 1.0, 5_000, 6_000);
        let f = build_exit_features_for_tick(&snap, 101.0, Some(1.0), None, None, 2_000);
        assert_eq!(f.entry_age_secs, None);
    }

    /// Entry price 0 → defensive `current_pnl_pct = 0.0` (no divide-by-zero
    /// explosion). peak_pnl_pct preserved from snap since it's pre-computed.
    /// entry_price=0 → 防禦性 current_pnl_pct=0.0；peak_pnl_pct 沿用 snap。
    #[test]
    fn test_build_for_tick_entry_price_zero_defensive() {
        let snap = mk_snap(true, 0.0, 1.5, 0, 100);
        let f = build_exit_features_for_tick(&snap, 123.0, Some(1.0), None, None, 1_000);
        assert_eq!(f.current_pnl_pct, 0.0);
        assert_eq!(f.peak_pnl_pct, 1.5);
        // giveback = (1.5 - 0) / 1.0 = 1.5
        let gb = f.giveback_atr_norm.expect("giveback should compute");
        assert!((gb - 1.5).abs() < 1e-6);
    }

    /// Non-finite entry price (impossible but defensive) → same fallback.
    /// entry_price 非有限 → fallback current_pnl_pct=0.0。
    #[test]
    fn test_build_for_tick_entry_price_nonfinite_defensive() {
        let snap = mk_snap(true, f64::INFINITY, 1.0, 0, 100);
        let f = build_exit_features_for_tick(&snap, 200.0, Some(1.0), None, None, 1_000);
        assert_eq!(f.current_pnl_pct, 0.0);
    }

    /// Builder output feeds `physical_micro_profit_lock_v2` end-to-end:
    /// constructed snapshot with age ≥ min_hold, peak ≥ min_peak_atr_norm,
    /// giveback crossing the non-linear threshold → Lock via Gate 4a.
    /// Documents the happy-path lock chain the T4 wiring unblocks.
    /// Builder 輸出直接餵 `physical_micro_profit_lock_v2` 端對端：age/peak/giveback
    /// 皆滿足 → Lock via Gate 4a。文件化 T4 接線所解鎖的 happy-path。
    #[test]
    fn test_build_for_tick_feeds_v2_gate4_lock() {
        let cfg = ExitConfig::default();
        // entry_ts=0, ts=120_000 → entry_age_secs=120 >> 30 min_hold.
        // peak=2.5 pct with atr=1 → peak_atr_norm=2.5 > 0.5 min.
        // current=1.2 → giveback_raw=1.3 / atr=1 = 1.3.
        // Threshold @ peak_atr_norm=2.5 = max(1.0 - 0.15*2.5, 0.3) = 0.625.
        // 1.3 > 0.625 → Lock gate4_giveback.
        let snap = mk_snap(true, 100.0, 2.5, 0, 60_000);
        let features = build_exit_features_for_tick(
            &snap,
            101.2,          // +1.2% current
            Some(1.0),      // atr_pct
            Some(-0.001),   // price_roc_short (negative, doesn't matter here)
            Some(10.0),     // est_net_bps > 5.0 floor
            120_000,        // ts_ms = entry_ts + 120s
        );
        assert_eq!(
            physical_micro_profit_lock_v2(&features, &cfg),
            PhysicalDecision::Lock("phys_lock_gate4_giveback".to_string())
        );
    }

    /// Same inputs but edge missing (est_net_bps=None) → v2 Gate 1 conservative
    /// Hold, confirming the fail-soft chain: missing edge → no premature lock.
    /// Same inputs 但 edge 缺失 → Gate 1 保守 Hold，驗證 fail-soft 鏈。
    #[test]
    fn test_build_for_tick_none_edge_feeds_v2_hold() {
        let cfg = ExitConfig::default();
        let snap = mk_snap(true, 100.0, 2.5, 0, 60_000);
        let features = build_exit_features_for_tick(
            &snap,
            101.2,
            Some(1.0),
            Some(-0.001),
            None, // ← edge missing
            120_000,
        );
        assert_eq!(
            physical_micro_profit_lock_v2(&features, &cfg),
            PhysicalDecision::Hold
        );
    }
}
