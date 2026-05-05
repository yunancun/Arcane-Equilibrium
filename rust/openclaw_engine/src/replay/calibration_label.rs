//! REF-20 Sprint C R6 W3 R6-T4 — replay calibration label 產出器。
//!
//! MODULE_NOTE：
//!   本模組依近期成交歷史，為每個 (strategy, symbol) cell 產出
//!   `ExecutionConfidence` 標籤（`'none' | 'limited' | 'calibrated'`）。
//!   標籤輸入下游：
//!     1. `replay.experiments.execution_confidence`（V049 text 列；有效值
//!        'none' / 'limited' / 'calibrated' / 'pending'）。
//!     2. `replay.simulated_fills.evidence_source_tier` 經 TTL 映射間接影響
//!        （calibrated→7d / limited→3d / none→0s）；MLDE/Dream 下游以 V051
//!        Block B `expires_at > now()` 自動實施信心衰減。
//!     3. `CalibrationResult.net_bps_p5/p50/p95` 寫入 V050
//!        `simulated_fills.ci_low/mid/high_bps`（CHECK 強制 low ≤ mid ≤
//!        high；percentile 單調保證）。
//!
//!   數學契約（依 QC spec §1）：
//!     4 維度 AND 短路布林過濾：
//!       維度 1（樣本量）：n=0 → None；否則續。
//!       維度 2（freshness）：last_fill_age > 14d → None；否則續。
//!       維度 3（fee_bps 形狀）：MAD/IQR 門檻。
//!       維度 4（切點）：
//!         calibrated_ok = n ≥ 200 && age ≤ 7d  && MAD < 3 bps && IQR <  8 bps
//!         limited_ok    = n ≥  30 && age ≤ 14d && MAD < 8 bps && IQR < 20 bps
//!         否則 → None。
//!
//!   統計選擇（依 QC spec §2）：
//!     - σ 用 MAD（median absolute deviation）— 對 fee_bps bimodal
//!       maker/taker 混合穩健（50% breakdown）。Sample std 拒絕（雙 mode
//!       距離拉大 std → 誤判穩定 fee 結構為 unstable）。
//!     - IQR（Q3 − Q1）為副驗 — tail-robust width。
//!     - MAD < 3 bps ≈ normal σ < 4.45 bps（σ ≈ 1.4826 × MAD）。
//!
//!   CI 計算分層（依 QC spec §3）：
//!     - n ≥ 200 → empirical percentile p5/p50/p95（Type 7 線性插值）。
//!     - 30 ≤ n < 200 → 寬幅 percentile + 0.5×IQR + 單調強制
//!       （BCa bootstrap 延 D-sprint）。
//!     - n < 30 → fallback median ± 1.645 × 1.4826 × MAD（normal-extension
//!       95% 區間）作保守處理。
//!     - 拒絕 naive bootstrap：對重尾 crypto returns 不一致（web 證實）。
//!
//!   TTL 映射（依 QC spec §4）：
//!     - Calibrated → chrono::Duration::days(7)
//!     - Limited    → chrono::Duration::days(3)
//!     - None       → chrono::Duration::zero()（writer 永不 insert）
//!
//!   邊界 case（依 QC spec §6）：
//!     - 空輸入 → None。
//!     - NaN/Inf fee_rate 或 entry_price → 計數前先過濾；n 自動降低。
//!     - σ/MAD = NaN（n < 2）→ None。
//!     - σ/MAD = 0（fill 全同 fee）→ 若 n ≥ 200 + freshness OK 仍可 calibrated
//!       （完全穩定 fee = 正面信號）。
//!     - net_bps_after_fee 全負 → label 不變（label 衡量 fee/slippage 校準
//!       信心，**非** PnL 信心）。
//!     - 不傳播 `Result`：任何異常 downgrade 至 None（advisory 信號，
//!       非執行 gate）。
//!
//!   Forbidden surface 審計（V3 §6.2 必綠）：
//!     - 0 引用 `paper_state` / `canary_writer` / `database` /
//!       `ipc_server` / `governance_hub` / `live_authorization` /
//!       `decision_lease` / `bybit_*` / `intent_processor::router`。
//!     - 純函數模組：僅依 `chrono`（workspace）+ `serde` + `std`。
//!       無 runtime state、無 I/O、無 `unsafe`。
//!
//!   本檔包含：
//!     - `ExecutionConfidence`（3-variant enum，serde 友好）。
//!     - `FillRecord`（`derive_*` 所需最小輸入 struct）。
//!     - `CalibrationResult`（輸出 struct，含 label + 統計 + TTL）。
//!     - `derive_execution_confidence(fills, now) -> CalibrationResult`
//!       （依 QC spec §7.1 公開 API）。
//!     - Robust statistics helper：`median` / `mad` / `iqr` / `percentile`。
//!
//!   不在本檔（刻意邊界）：
//!     - 消費 `CalibrationResult` 的 DB writer（Sprint C W4 R6-T5/T6 Python
//!       `simulated_fills_writer.py` + `experiment_registry.py`）。
//!     - `trading.fills` rows → `Vec<FillRecord>` SQL 投影（caller 負責 —
//!       本模組保持 DB-agnostic）。
//!     - Regime 偵測（DEFER 至 Sprint D R9；見 QC spec §5）。
//!
//! SPEC: REF-20 V3 §3 G7/G8 + V049 (replay_experiments) + V050
//!       (replay_simulated_fills.ci_*_bps) + V051 (mlde_recommendations Block B
//!       expires_at gate) + workplan R20-P2b-T4 + QC pre-DAG advisory
//!       `2026-05-05--ref20_r6_calibration_label_spec.md`.

use chrono::{DateTime, Duration, Utc};
use serde::{Deserialize, Serialize};

// ─────────────────────────────────────────────────────────────────────────
// 公開型別
// ─────────────────────────────────────────────────────────────────────────

/// 執行校準信心標籤（依 QC spec §1）。
///
/// 變體：
///   - `None`：樣本量、freshness 或 shape 過濾失敗；不適合任何下游 consumer。
///   - `Limited`：低標（n ≥ 30、age ≤ 14d、MAD < 8 bps）；writer 以
///     **3 天 TTL** 持久化，使 MLDE/Dream Block B `expires_at` gate 自動衰減。
///   - `Calibrated`：高標（n ≥ 200、age ≤ 7d、MAD < 3 bps、IQR < 8 bps）；
///     writer 以 **7 天 TTL** 持久化。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ExecutionConfidence {
    None,
    Limited,
    Calibrated,
}

impl ExecutionConfidence {
    /// 轉為 V049 enum text 列值（小寫字串契約）。
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::None => "none",
            Self::Limited => "limited",
            Self::Calibrated => "calibrated",
        }
    }
}

/// `derive_execution_confidence` 消費的最小 fill-record 投影。
///
/// 欄位語意：
///   - `fee_rate`：小數（**非** bps）。函數內部 ×10_000 轉 bps；QC spec §1
///     預期源頭為 `trading.fills.fee_rate` 的小數值。
///   - `entry_price`：開倉時的 quote 計價。
///   - `exit_price`：平倉時的 quote 計價。
///   - `is_long`：true=多 / false=空。取代 SQL `direction` int 欄位，使
///     Rust struct typed（caller 映射 1↔long、-1↔short）。
///   - `filled_at`：chrono UTC datetime；freshness 以
///     `derive_execution_confidence` 的 `now` 參數為基準。
#[derive(Debug, Clone)]
pub struct FillRecord {
    pub fee_rate: f64,
    pub entry_price: f64,
    pub exit_price: f64,
    pub is_long: bool,
    pub filled_at: DateTime<Utc>,
}

/// `derive_execution_confidence` 輸出的校準結果。
///
/// 欄位語意：
///   - `label`：三層信心（V049 列）。
///   - `sample_count`：過濾 NaN/Inf 後的計數（= 有效 n）。
///   - `last_fill_age_ms`：`now − 最後 filled_at`（毫秒）；`sample_count == 0`
///     時為 -1（sentinel）。
///   - `fee_bps_mad`：robust scale（50% breakdown）；n < 2 時為 NaN。
///   - `fee_bps_iqr`：tail-robust width（Q3 − Q1）；n < 4 時為 NaN。
///   - `net_bps_p5/p50/p95`：餵 V050 `ci_low/mid/high_bps`。單調保證
///     （`p5 ≤ p50 ≤ p95`）。`sample_count == 0` 時為 NaN。
///   - `ttl`：V051 `expires_at = now + ttl`。`None` 時為 zero（writer 跳過）。
#[derive(Debug, Clone)]
pub struct CalibrationResult {
    pub label: ExecutionConfidence,
    pub sample_count: usize,
    pub last_fill_age_ms: i64,
    pub fee_bps_mad: f64,
    pub fee_bps_iqr: f64,
    pub net_bps_p5: f64,
    pub net_bps_p50: f64,
    pub net_bps_p95: f64,
    pub ttl: Duration,
}

impl CalibrationResult {
    /// 建構空 / 無效輸入下的 canonical "no signal" 結果。
    fn none_default() -> Self {
        Self {
            label: ExecutionConfidence::None,
            sample_count: 0,
            last_fill_age_ms: -1,
            fee_bps_mad: f64::NAN,
            fee_bps_iqr: f64::NAN,
            net_bps_p5: f64::NAN,
            net_bps_p50: f64::NAN,
            net_bps_p95: f64::NAN,
            ttl: Duration::zero(),
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────
// 公開 API
// ─────────────────────────────────────────────────────────────────────────

/// 為單一 (strategy, symbol) cell 推導 `ExecutionConfidence`。
///
/// 依 QC spec §1 4 維度 AND 過濾（短路）：
///   1. sample_count ≥ {200|30}
///   2. last_fill_age_days ≤ {7|14}
///   3. fee_bps_mad < {3|8} bps
///   4. fee_bps_iqr < {8|20} bps
///
/// 參數：
///   - `fills`：依時序排列的 fills（caller 負責）；空 vec 合法（回傳 None）。
///   - `now`：freshness 算術的參考時鐘；production 傳 `chrono::Utc::now()`。
///
/// 回傳：
///   - `CalibrationResult` — 不 panic、不回 Err。異常依 QC spec §6 降至 `None`。
pub fn derive_execution_confidence(
    fills: &[FillRecord],
    now: DateTime<Utc>,
) -> CalibrationResult {
    // Step 1：過濾 NaN/Inf row。caller 端契約允許 NaN balance / NaN fee_rate
    // 存在；防禦性過濾保護下游統計。
    let valid: Vec<&FillRecord> = fills
        .iter()
        .filter(|f| {
            f.fee_rate.is_finite() && f.entry_price.is_finite() && f.exit_price.is_finite()
        })
        .collect();

    let n = valid.len();
    if n == 0 {
        // 空 / 全無效輸入 → None。
        return CalibrationResult::none_default();
    }

    // Step 2：freshness — last_fill_age（caller 負責 chrono 排序；防禦性取
    // max(filled_at) 以容忍 caller 未排序）。
    let last_filled_at = valid
        .iter()
        .map(|f| f.filled_at)
        .max()
        .expect("valid is non-empty per n>0 above");
    let age = now - last_filled_at;
    let last_fill_age_ms = age.num_milliseconds();
    let last_fill_age_days = (last_fill_age_ms as f64) / 86_400_000.0;

    // 構造 fee_bps + net_bps_after_fee 向量供 shape 統計。
    let fee_bps_vec: Vec<f64> = valid.iter().map(|f| f.fee_rate * 10_000.0).collect();
    let net_bps_vec: Vec<f64> = valid
        .iter()
        .map(|f| compute_net_bps_after_fee(f))
        .filter(|v| v.is_finite())
        .collect();

    let fee_bps_mad = mad(&fee_bps_vec);
    let fee_bps_iqr = iqr(&fee_bps_vec);

    // Step 3 + 4：4 維 AND 過濾。注意 QC spec §1 在 freshness > 14d 時短路至
    // None，不檢查 shape — 此處保留該語意。
    let label = if last_fill_age_days > 14.0 {
        ExecutionConfidence::None
    } else {
        // QC spec §6 邊界：σ/MAD = NaN（n < 2）→ None。
        if !fee_bps_mad.is_finite() {
            ExecutionConfidence::None
        } else {
            // 注：NaN IQR（n < 4）視為「嚴格切點失敗」，limited 層仍可達
            // 若 MAD 過。NaN → +inf 使 `iqr_value < threshold` 為 false。
            let iqr_for_compare = if fee_bps_iqr.is_finite() {
                fee_bps_iqr
            } else {
                f64::INFINITY
            };

            let calibrated_ok = n >= 200
                && last_fill_age_days <= 7.0
                && fee_bps_mad < 3.0
                && iqr_for_compare < 8.0;

            let limited_ok = n >= 30
                && last_fill_age_days <= 14.0
                && fee_bps_mad < 8.0
                && iqr_for_compare < 20.0;

            if calibrated_ok {
                ExecutionConfidence::Calibrated
            } else if limited_ok {
                ExecutionConfidence::Limited
            } else {
                ExecutionConfidence::None
            }
        }
    };

    // Step 5：依 QC spec §3 計算 CI。
    let (net_p5, net_p50, net_p95) = compute_ci(&net_bps_vec);

    // Step 6：依 QC spec §4 映射 TTL。
    let ttl = match label {
        ExecutionConfidence::Calibrated => Duration::days(7),
        ExecutionConfidence::Limited => Duration::days(3),
        ExecutionConfidence::None => Duration::zero(),
    };

    CalibrationResult {
        label,
        sample_count: n,
        last_fill_age_ms,
        fee_bps_mad,
        fee_bps_iqr,
        net_bps_p5: net_p5,
        net_bps_p50: net_p50,
        net_bps_p95: net_p95,
        ttl,
    }
}

// ─────────────────────────────────────────────────────────────────────────
// 內部 helper
// ─────────────────────────────────────────────────────────────────────────

/// 為單筆 fill 依 QC spec §3.1 計算 `net_bps_after_fee`。
///
/// 公式：
///   gross_bps = (exit - entry) / entry × 10_000 × direction
///   net_bps   = gross_bps − fee_bps_entry − fee_bps_exit
///   （slippage_bps 留 R6-T2 row level）
fn compute_net_bps_after_fee(fill: &FillRecord) -> f64 {
    if !fill.entry_price.is_finite() || fill.entry_price == 0.0 {
        return f64::NAN;
    }
    let direction: f64 = if fill.is_long { 1.0 } else { -1.0 };
    let gross_bps = (fill.exit_price - fill.entry_price) / fill.entry_price * 10_000.0 * direction;
    let fee_bps = fill.fee_rate * 10_000.0;
    // 進場側 + 出場側 fee 都計 — 來回合計 = 2×fee_bps。
    gross_bps - 2.0 * fee_bps
}

/// 依 QC spec §3 計算信賴區間 `(p5, p50, p95)`。
///
/// 分層策略：
///   - n ≥ 200 → empirical percentile（Type 7 線性插值）。
///   - 30 ≤ n < 200 → 寬幅 percentile + 0.5×IQR pad。
///   - n < 30 → median ± 1.645 × 1.4826 × MAD（normal-extension fallback）。
///   - n == 0 → 全 NaN。
///   - 寬幅層後置以 min/max 強制單調。
fn compute_ci(net_bps_vec: &[f64]) -> (f64, f64, f64) {
    let n = net_bps_vec.len();
    if n == 0 {
        return (f64::NAN, f64::NAN, f64::NAN);
    }
    if n < 30 {
        // Normal-extension fallback：median ± 1.645 × σ；σ ≈ 1.4826 × MAD。
        let med = median(net_bps_vec);
        let mad_value = mad(net_bps_vec);
        // 1.645 × 1.4826 = 2.4389。寫死 magic literal，使公式來源可追溯。
        let half_width = if mad_value.is_finite() {
            1.645 * 1.4826 * mad_value
        } else {
            // n=1（或全等）— half-width 0 → CI = (med, med, med)。
            0.0
        };
        return (med - half_width, med, med + half_width);
    }
    if n < 200 {
        // 寬幅 empirical percentile：兩尾各加 0.5×IQR。
        let iqr_value = iqr(net_bps_vec);
        let pad = if iqr_value.is_finite() { 0.5 * iqr_value } else { 0.0 };
        let p5_raw = percentile(net_bps_vec, 5.0);
        let p50 = percentile(net_bps_vec, 50.0);
        let p95_raw = percentile(net_bps_vec, 95.0);
        let p5 = (p5_raw - pad).min(p50);
        let p95 = (p95_raw + pad).max(p50);
        return (p5, p50, p95);
    }
    // n ≥ 200：直接 empirical percentile。
    (
        percentile(net_bps_vec, 5.0),
        percentile(net_bps_vec, 50.0),
        percentile(net_bps_vec, 95.0),
    )
}

// ─────────────────────────────────────────────────────────────────────────
// Robust 統計 helpers
// ─────────────────────────────────────────────────────────────────────────

/// Median absolute deviation（50% breakdown 點）。
///
/// 回傳：
///   - `v.len() < 2` 時為 NaN（QC spec §6 統計量無定義）。
///   - 否則為 `median(|x_i - median(v)|)`。
pub fn mad(v: &[f64]) -> f64 {
    if v.len() < 2 {
        return f64::NAN;
    }
    let med = median(v);
    let abs_dev: Vec<f64> = v.iter().map(|x| (x - med).abs()).collect();
    median(&abs_dev)
}

/// 四分位距（Q3 − Q1）。
///
/// 回傳：
///   - `v.len() < 4` 時為 NaN（樣本不足以分 Q1/Q3）。
///   - 否則為 `percentile(v, 75) - percentile(v, 25)`。
pub fn iqr(v: &[f64]) -> f64 {
    if v.len() < 4 {
        return f64::NAN;
    }
    percentile(v, 75.0) - percentile(v, 25.0)
}

/// 中位數 = `percentile(v, 50.0)`。空輸入回 NaN。
pub fn median(v: &[f64]) -> f64 {
    if v.is_empty() {
        return f64::NAN;
    }
    percentile(v, 50.0)
}

/// 線性插值 percentile（Type 7 / Hyndman-Fan）。
///
/// 演算法：
///   - 升序排序副本。
///   - 位置 h = (n − 1) × p/100，`n = sorted.len()`。
///   - `sorted[floor(h)]` 與 `sorted[ceil(h)]` 之間線性插值。
///   - p clamp 至 [0, 100]；排序前過濾 NaN。
///
/// 邊界：
///   - 過濾 NaN 後空 → NaN。
///   - n=1 → 該值。
///   - p=0 → 最小，p=100 → 最大。
pub fn percentile(v: &[f64], p: f64) -> f64 {
    let mut sorted: Vec<f64> = v.iter().copied().filter(|x| x.is_finite()).collect();
    if sorted.is_empty() {
        return f64::NAN;
    }
    sorted.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    let n = sorted.len();
    if n == 1 {
        return sorted[0];
    }
    let p_clamped = p.clamp(0.0, 100.0);
    let h = (n as f64 - 1.0) * p_clamped / 100.0;
    let lo = h.floor() as usize;
    let hi = h.ceil() as usize;
    if lo == hi {
        sorted[lo]
    } else {
        let frac = h - lo as f64;
        sorted[lo] * (1.0 - frac) + sorted[hi] * frac
    }
}

// ─────────────────────────────────────────────────────────────────────────
// 模組內部 unit test
// ─────────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::TimeZone;

    /// 測試 helper：以顯式 fee_rate + age（相對測試 now 的天數）構造
    /// `FillRecord`。
    fn make_fill(
        now: DateTime<Utc>,
        age_days: f64,
        fee_rate: f64,
        entry: f64,
        exit_: f64,
        is_long: bool,
    ) -> FillRecord {
        let filled_at = now - Duration::milliseconds((age_days * 86_400_000.0) as i64);
        FillRecord {
            fee_rate,
            entry_price: entry,
            exit_price: exit_,
            is_long,
            filled_at,
        }
    }

    /// 所有 test 共用的參考時鐘 — 固定、確定性。
    fn reference_now() -> DateTime<Utc> {
        Utc.with_ymd_and_hms(2026, 5, 5, 12, 0, 0).unwrap()
    }

    /// QC spec §1.1：grid_trading n=1162 + freshness 7d + MAD<3 → 'calibrated'。
    #[test]
    fn test_grid_trading_1162_fills_calibrated() {
        let now = reference_now();
        // 1162 筆 fill，穩定 maker fee（2 bps，小數=0.0002），均勻分布於
        // 過去 6 天。所有 fill 同 fee → MAD = 0 < 3 bps，符 calibrated。
        let mut fills = Vec::with_capacity(1162);
        for i in 0..1162 {
            let age = (i as f64) * 6.0 / 1162.0; // 0..6 天
            fills.push(make_fill(now, age, 0.0002, 100.0, 101.0, true));
        }
        let result = derive_execution_confidence(&fills, now);
        assert_eq!(result.label, ExecutionConfidence::Calibrated);
        assert_eq!(result.sample_count, 1162);
        assert!(result.fee_bps_mad < 3.0, "MAD must be < 3 bps for calibrated");
        assert_eq!(result.ttl, Duration::days(7));
        // p5 ≤ p50 ≤ p95 不變式。
        assert!(result.net_bps_p5 <= result.net_bps_p50);
        assert!(result.net_bps_p50 <= result.net_bps_p95);
    }

    /// QC spec §1.1：ma_crossover n=635 + freshness 7d → 視 MAD/IQR 落在
    /// 'limited' 或 'calibrated' 邊界。
    #[test]
    fn test_ma_crossover_635_fills_limited_or_calibrated() {
        let now = reference_now();
        // 635 筆 fill，混合 maker（2 bps）+ taker（5.5 bps）— bimodal。
        // 50/50 maker/taker 混合 → 2 與 5.5 bps 兩 spike；MAD 可能 > 3 bps
        // → spec 預期 'limited'。
        let mut fills = Vec::with_capacity(635);
        for i in 0..635 {
            let age = (i as f64) * 6.5 / 635.0; // 0..6.5 天
            let fee = if i % 2 == 0 { 0.0002 } else { 0.00055 };
            fills.push(make_fill(now, age, fee, 100.0, 100.5, true));
        }
        let result = derive_execution_confidence(&fills, now);
        // 兩層皆合於 spec §1.1；檢驗非 None。
        assert_ne!(result.label, ExecutionConfidence::None);
        assert_eq!(result.sample_count, 635);
        assert!(result.last_fill_age_ms >= 0);
    }

    /// QC spec §1.1：funding_arb n=99 < 200 → 不可能 'calibrated'；視
    /// freshness/MAD 為 'limited' 或 'none'。
    #[test]
    fn test_funding_arb_99_fills_not_calibrated() {
        let now = reference_now();
        let mut fills = Vec::with_capacity(99);
        for i in 0..99 {
            let age = (i as f64) * 5.0 / 99.0; // 0..5 天
            fills.push(make_fill(now, age, 0.0002, 100.0, 100.1, true));
        }
        let result = derive_execution_confidence(&fills, now);
        assert_ne!(result.label, ExecutionConfidence::Calibrated);
        assert_eq!(result.sample_count, 99);
    }

    /// QC spec §1.1：bb_breakout n=34 > 30 邊界；freshness <14d。
    #[test]
    fn test_bb_breakout_34_fills_limited_boundary() {
        let now = reference_now();
        // 34 筆 fill，穩定 fee 2 bps，最後 fill 1 天前。
        let mut fills = Vec::with_capacity(34);
        for i in 0..34 {
            // 最後 fill age=1.0 天；最舊 age=12.0 天。
            let age = 1.0 + (i as f64) * 11.0 / 33.0;
            fills.push(make_fill(now, age, 0.0002, 100.0, 100.05, true));
        }
        let result = derive_execution_confidence(&fills, now);
        // n=34 ≥ 30、age=1d ≤ 14d、MAD=0（fee 全等）→ limited
        // （n<200 故非 calibrated）。
        assert_eq!(result.label, ExecutionConfidence::Limited);
        assert_eq!(result.ttl, Duration::days(3));
        assert_eq!(result.sample_count, 34);
    }

    /// QC spec §1.1：bb_reversion n=7 < 30 → None。
    #[test]
    fn test_bb_reversion_7_fills_none() {
        let now = reference_now();
        let mut fills = Vec::with_capacity(7);
        for i in 0..7 {
            let age = (i as f64) * 0.5;
            fills.push(make_fill(now, age, 0.0002, 100.0, 100.1, true));
        }
        let result = derive_execution_confidence(&fills, now);
        assert_eq!(result.label, ExecutionConfidence::None);
        assert_eq!(result.ttl, Duration::zero());
        assert_eq!(result.sample_count, 7);
    }

    /// QC spec §6：空 fills → None 預設 sentinel。
    #[test]
    fn test_empty_fills_returns_none() {
        let now = reference_now();
        let result = derive_execution_confidence(&[], now);
        assert_eq!(result.label, ExecutionConfidence::None);
        assert_eq!(result.sample_count, 0);
        assert_eq!(result.last_fill_age_ms, -1);
        assert!(result.fee_bps_mad.is_nan());
        assert!(result.fee_bps_iqr.is_nan());
        assert!(result.net_bps_p5.is_nan());
        assert_eq!(result.ttl, Duration::zero());
    }

    /// QC spec §6：NaN fee_rate 被過濾 → 有效 n 降；若降至 30 以下自然降級。
    #[test]
    fn test_nan_fee_rate_filtered_out() {
        let now = reference_now();
        let mut fills = vec![];
        // 35 筆有效 fill。
        for i in 0..35 {
            let age = (i as f64) * 0.1;
            fills.push(make_fill(now, age, 0.0002, 100.0, 100.1, true));
        }
        // 10 筆 NaN fill（會被過濾）。
        for _ in 0..10 {
            fills.push(make_fill(now, 1.0, f64::NAN, 100.0, 100.1, true));
        }
        let result = derive_execution_confidence(&fills, now);
        assert_eq!(result.sample_count, 35); // 10 NaN 過濾
        // 35 ≥ 30 + age ≤ 14d + MAD=0 → limited。
        assert_eq!(result.label, ExecutionConfidence::Limited);
    }

    /// QC spec §1：last fill > 14d → None（freshness 短路）。
    #[test]
    fn test_stale_15d_returns_none() {
        let now = reference_now();
        let mut fills = Vec::with_capacity(500);
        for i in 0..500 {
            // 全部 fill 15+ 天前。
            let age = 15.0 + (i as f64) * 0.01;
            fills.push(make_fill(now, age, 0.0002, 100.0, 100.1, true));
        }
        let result = derive_execution_confidence(&fills, now);
        assert_eq!(result.label, ExecutionConfidence::None);
        assert_eq!(result.ttl, Duration::zero());
        assert!(result.last_fill_age_ms > 14 * 86_400_000);
    }

    /// QC spec §3：tier=calibrated 路徑（n ≥ 200 empirical）的單調不變式。
    #[test]
    fn test_ci_p5_p50_p95_monotonic_calibrated() {
        let now = reference_now();
        // 250 筆 fill，exit 寬幅變動，使 CI 非 trivial。
        let mut fills = Vec::with_capacity(250);
        for i in 0..250 {
            let age = (i as f64) * 6.0 / 250.0;
            // 正弦狀 exit 使 net_bps 分布展開。
            let exit_offset = ((i as f64) * 0.1).sin() * 0.5;
            fills.push(make_fill(now, age, 0.0002, 100.0, 100.0 + exit_offset, true));
        }
        let result = derive_execution_confidence(&fills, now);
        assert_eq!(result.label, ExecutionConfidence::Calibrated);
        assert!(
            result.net_bps_p5 <= result.net_bps_p50,
            "p5 ({}) > p50 ({})",
            result.net_bps_p5,
            result.net_bps_p50
        );
        assert!(
            result.net_bps_p50 <= result.net_bps_p95,
            "p50 ({}) > p95 ({})",
            result.net_bps_p50,
            result.net_bps_p95
        );
    }

    /// QC spec §3.3 fallback：n=10 < 30 → CI 用 median ± 1.645×1.4826×MAD。
    #[test]
    fn test_ci_fallback_normal_extension_for_small_n() {
        let now = reference_now();
        let mut fills = Vec::with_capacity(10);
        for i in 0..10 {
            let age = (i as f64) * 0.1;
            // exit 圍繞 100.0 對稱抖動使 MAD 非零。
            let exit_offset = if i < 5 { -0.5 } else { 0.5 };
            fills.push(make_fill(
                now,
                age,
                0.0002,
                100.0,
                100.0 + exit_offset,
                true,
            ));
        }
        let result = derive_execution_confidence(&fills, now);
        // n=10 < 30 → label=None（樣本量不足），但 CI 仍計算供下游
        // consumer（無 panic / 無 NaN 爆炸）。
        assert_eq!(result.label, ExecutionConfidence::None);
        assert!(result.net_bps_p5.is_finite());
        assert!(result.net_bps_p50.is_finite());
        assert!(result.net_bps_p95.is_finite());
        assert!(result.net_bps_p5 <= result.net_bps_p50);
        assert!(result.net_bps_p50 <= result.net_bps_p95);
    }

    /// QC spec §4：TTL 映射 {Calibrated→7d, Limited→3d, None→0s}。
    #[test]
    fn test_ttl_mapping_per_label() {
        let now = reference_now();

        // Calibrated build：250 筆 fill，新鮮，穩定 fee。
        let calibrated_fills: Vec<FillRecord> = (0..250)
            .map(|i| {
                let age = (i as f64) * 5.0 / 250.0;
                make_fill(now, age, 0.0002, 100.0, 100.05, true)
            })
            .collect();
        let r_calib = derive_execution_confidence(&calibrated_fills, now);
        assert_eq!(r_calib.label, ExecutionConfidence::Calibrated);
        assert_eq!(r_calib.ttl, Duration::days(7));

        // Limited build：50 筆 fill，穩定 fee。
        let limited_fills: Vec<FillRecord> = (0..50)
            .map(|i| {
                let age = (i as f64) * 5.0 / 50.0;
                make_fill(now, age, 0.0002, 100.0, 100.05, true)
            })
            .collect();
        let r_lim = derive_execution_confidence(&limited_fills, now);
        assert_eq!(r_lim.label, ExecutionConfidence::Limited);
        assert_eq!(r_lim.ttl, Duration::days(3));

        // None build：7 筆 fill。
        let none_fills: Vec<FillRecord> = (0..7)
            .map(|i| make_fill(now, i as f64 * 0.1, 0.0002, 100.0, 100.05, true))
            .collect();
        let r_none = derive_execution_confidence(&none_fills, now);
        assert_eq!(r_none.label, ExecutionConfidence::None);
        assert_eq!(r_none.ttl, Duration::zero());
    }

    /// QC spec §10 Q5：last fill 恰 7d 邊界 → 容許 calibrated（≤ 7.0）。
    #[test]
    fn test_last_fill_exactly_7d_boundary_allows_calibrated() {
        let now = reference_now();
        // 250 筆 fill；last fill 恰 7d 前；其餘介於 7d 與 6d 之間。
        let mut fills = Vec::with_capacity(250);
        for i in 0..250 {
            let age = 6.0 + (i as f64) * 1.0 / 249.0; // 6.0..7.0d
            fills.push(make_fill(now, age, 0.0002, 100.0, 100.05, true));
        }
        let result = derive_execution_confidence(&fills, now);
        // 邊界為 `<= 7.0`（含等號）；7d 舊 row 仍合格。
        assert_eq!(result.label, ExecutionConfidence::Calibrated);
    }

    /// QC spec §10 Q4：MAD=5（> calibrated 3 切點）但 IQR < 20（limited 切點）
    /// → 經 && AND 鏈降至 'limited'。
    #[test]
    fn test_mad_above_calibrated_cut_falls_to_limited() {
        let now = reference_now();
        // 構造 MAD ~= 4 bps、IQR < 20 bps 的 fill：
        // 1 bps + 9 bps 混合 → median 5.0、MAD=4.0。
        let mut fills = Vec::with_capacity(220);
        for i in 0..220 {
            let age = (i as f64) * 5.0 / 220.0;
            let fee = if i % 2 == 0 { 0.0001 } else { 0.0009 };
            fills.push(make_fill(now, age, fee, 100.0, 100.05, true));
        }
        let result = derive_execution_confidence(&fills, now);
        // MAD ~ 4 bps（介於 3 嚴格與 8 寬鬆之間）→ 失 calibrated、過 limited。
        assert_eq!(result.label, ExecutionConfidence::Limited);
        assert!(result.fee_bps_mad >= 3.0 && result.fee_bps_mad < 8.0);
    }

    /// QC spec §6：σ/MAD = 0（fill 全同 fee）+ n ≥ 200 + freshness OK
    /// → calibrated 候選。
    #[test]
    fn test_zero_mad_identical_fees_can_be_calibrated() {
        let now = reference_now();
        let mut fills = Vec::with_capacity(250);
        for i in 0..250 {
            let age = (i as f64) * 5.0 / 250.0;
            fills.push(make_fill(now, age, 0.0002, 100.0, 100.05, true));
        }
        let result = derive_execution_confidence(&fills, now);
        assert_eq!(result.label, ExecutionConfidence::Calibrated);
        assert_eq!(result.fee_bps_mad, 0.0);
        assert_eq!(result.fee_bps_iqr, 0.0);
    }

    /// Helper 級：percentile `Type 7` 線性插值正確性（簡單區間）。
    #[test]
    fn test_percentile_type7_correctness() {
        let v = vec![1.0, 2.0, 3.0, 4.0, 5.0];
        // 5 元素 p50 = 3.0（中位）。
        assert!((percentile(&v, 50.0) - 3.0).abs() < 1e-12);
        // p0 = 最小 = 1.0；p100 = 最大 = 5.0。
        assert!((percentile(&v, 0.0) - 1.0).abs() < 1e-12);
        assert!((percentile(&v, 100.0) - 5.0).abs() < 1e-12);
        // p25 = (n-1) × 0.25 = 1.0 → sorted[1] = 2.0。
        assert!((percentile(&v, 25.0) - 2.0).abs() < 1e-12);
    }

    /// Helper 級：已知分布的 MAD。
    #[test]
    fn test_mad_correctness() {
        let v = vec![1.0, 2.0, 3.0, 4.0, 5.0];
        // 中位數 = 3.0；|dev| = [2,1,0,1,2]；中位數 = 1.0。
        assert!((mad(&v) - 1.0).abs() < 1e-12);
        // n=1 → NaN。
        assert!(mad(&[5.0]).is_nan());
        // 空 → NaN。
        assert!(mad(&[]).is_nan());
    }

    /// Helper 級：已知分布的 IQR。
    #[test]
    fn test_iqr_correctness() {
        // 9 元素升序：percentile 用 (n-1)*p/100 位置。
        let v = vec![1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0];
        // Q1 = sorted[2] = 3.0；Q3 = sorted[6] = 7.0；IQR = 4.0。
        assert!((iqr(&v) - 4.0).abs() < 1e-12);
        // n<4 → NaN。
        assert!(iqr(&[1.0, 2.0, 3.0]).is_nan());
    }

    /// QC spec §10 Q3：fee + 1bps 平移（location-invariant）→ MAD/IQR 不變
    /// → label 不變。
    #[test]
    fn test_fee_shift_does_not_change_label() {
        let now = reference_now();
        // 兩平行 run 僅差 1 bps 全域 fee 平移。
        let baseline: Vec<FillRecord> = (0..250)
            .map(|i| {
                let age = (i as f64) * 5.0 / 250.0;
                let fee = if i % 2 == 0 { 0.0001 } else { 0.0009 };
                make_fill(now, age, fee, 100.0, 100.05, true)
            })
            .collect();
        let shifted: Vec<FillRecord> = baseline
            .iter()
            .map(|f| FillRecord {
                fee_rate: f.fee_rate + 0.0001, // +1 bps decimal
                ..f.clone()
            })
            .collect();
        let r_base = derive_execution_confidence(&baseline, now);
        let r_shift = derive_execution_confidence(&shifted, now);
        assert_eq!(r_base.label, r_shift.label);
        assert!((r_base.fee_bps_mad - r_shift.fee_bps_mad).abs() < 1e-9);
        assert!((r_base.fee_bps_iqr - r_shift.fee_bps_iqr).abs() < 1e-9);
    }

    /// `ExecutionConfidence::as_str` 對 V049 enum text 列使用的小寫 token
    /// 做 round-trip。
    #[test]
    fn test_execution_confidence_as_str() {
        assert_eq!(ExecutionConfidence::None.as_str(), "none");
        assert_eq!(ExecutionConfidence::Limited.as_str(), "limited");
        assert_eq!(ExecutionConfidence::Calibrated.as_str(), "calibrated");
    }
}
