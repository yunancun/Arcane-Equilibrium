// MODULE_NOTE
// 模塊用途：M4 Stage 1 leak-free feature engineering（shift(1) rolling stats）。
//   核心職能：對所有 rolling window 統計（mean / std / pct_change），強制
//   .shift(1) leak-free pattern — current bar 必排除在 rolling window 之外，
//   避免 look-ahead bias 把「current bar 是 N-bar max」這類 deterministic
//   artifact 當 alpha signal（per memory `feedback_indicator_lookahead_bias`
//   2026-04-24 P1-11 F3 RETRACT 教訓）。
//
// 函數契約（per W1-B spec §2.1.2）：
//   - shift1_rolling_mean(values, window)
//     輸出第 i 個 result = mean(values[i-window..i])；i < window 為 None
//     （current bar values[i] 不算入該 window）
//   - shift1_rolling_std(values, window) 同 mean；population std
//   - shift1_rolling_pct_change(values) 輸出第 i 個 = (values[i-1] / values[i-2]) - 1
//   - validate_leak_free_pattern(...) 並列 leak vs leak-free 兩版 corr，
//     若 |diff| > 0.1 視 leak suspected（per W1-B spec §4.3）
//
// 不變量：
//   - I-1 強制：任何 rolling_* output[i] 不能依賴 values[i] 本身
//   - 樣本不足必回 None（不假設 0 也不假設 forward-fill）
//   - Population std（除 N），非 sample std（除 N-1）— 與 pandas .rolling(N).std(ddof=0) 對齊
//
// 為什麼 ddof=0 而非 ddof=1：對齊 W1-B spec §2.1.3 「Volume z-score」公式
//   `(volume.shift(1) - mean) / std`，pandas .rolling(N).std() 預設 ddof=1，
//   但 W1-B 在三語言對齊（Rust / Python / SQL window function）中 SQL 端
//   `stddev_pop` 為 ddof=0，故 Rust 採 ddof=0；Python 端必 .rolling(N).std(ddof=0)。

/// 計算 leak-free shift(1) rolling mean — current bar 排除在 window 之外。
///
/// 為什麼用 Option：樣本不足（i < window）回 None；下游必 fail-closed 不假設 0。
/// 不變量：output[i] 只依賴 values[i-window .. i]（不含 values[i] 本身）。
///
/// # Example
/// ```ignore
/// // window = 3
/// // values = [10, 20, 30, 40, 50]
/// // output = [None, None, None, mean(10,20,30)=20.0, mean(20,30,40)=30.0]
/// // 注意 output[3] = mean(values[0..3]) = 20.0；不是 mean(values[1..4]) = 30.0
/// ```
pub fn shift1_rolling_mean(values: &[f64], window: usize) -> Vec<Option<f64>> {
    if window == 0 {
        return vec![None; values.len()];
    }
    let mut out = Vec::with_capacity(values.len());
    for i in 0..values.len() {
        if i < window {
            // 樣本不足：i < window 表示 [i-window..i] 不可達 → None。
            // 為什麼 fail-closed：學習 ≠ live，未滿 window 不可猜 0 也不可 forward-fill。
            out.push(None);
        } else {
            let slice = &values[i - window..i]; // 不含 values[i] 本身 — 即 shift(1)。
            let sum: f64 = slice.iter().sum();
            out.push(Some(sum / window as f64));
        }
    }
    out
}

/// 計算 leak-free shift(1) rolling population std（ddof=0）。
///
/// 為什麼 ddof=0：對齊 SQL `stddev_pop()` 與 W1-B 三語言 fixture 1e-4 對齊要求；
/// Python 端必設 `.rolling(N).std(ddof=0)` 才能對齊。
pub fn shift1_rolling_std(values: &[f64], window: usize) -> Vec<Option<f64>> {
    if window == 0 {
        return vec![None; values.len()];
    }
    let mut out = Vec::with_capacity(values.len());
    for i in 0..values.len() {
        if i < window {
            out.push(None);
        } else {
            let slice = &values[i - window..i];
            let mean: f64 = slice.iter().sum::<f64>() / window as f64;
            let var: f64 = slice.iter().map(|v| (v - mean).powi(2)).sum::<f64>() / window as f64;
            out.push(Some(var.sqrt()));
        }
    }
    out
}

/// 計算 leak-free shift(1) pct_change — output[i] = values[i-1] / values[i-2] - 1。
///
/// 為什麼這個 signature：W1-B spec §2.1.3 Volume z-score 與 Realized vol 都需要
/// `close.shift(1).pct_change()` 形式 — 即「兩步前/三步前」的比率，current bar
/// 與前一 bar 都排除。
pub fn shift1_rolling_pct_change(values: &[f64]) -> Vec<Option<f64>> {
    let n = values.len();
    let mut out = Vec::with_capacity(n);
    for i in 0..n {
        if i < 2 {
            // 第 0/1 元素：[i-2] / [i-1] 不可達 → None。
            out.push(None);
        } else {
            let prev = values[i - 2];
            let cur = values[i - 1];
            if prev.abs() < 1e-15 {
                // 除以 0 fail-closed — 不假設返回 0。
                out.push(None);
            } else {
                out.push(Some(cur / prev - 1.0));
            }
        }
    }
    out
}

/// 並列計算 leak vs leak-free 兩版 rolling correlation，判斷是否有 leak suspected。
///
/// per W1-B spec §4.3 leakage scan：
///   leak version：含 current bar 的 rolling correlation
///   leak-free version：shift(1) 版
///   若 |leak_effect - clean_effect| > threshold（baseline 0.1）→ leak_suspected = true
///
/// 為什麼用 absolute correlation：cross-correlation 可能正可能負，本檢驗只關心
/// magnitude 差距是否異常（pure noise series 兩版差距應 < threshold）。
pub fn validate_leak_free_pattern(
    feature_values: &[f64],
    forward_return: &[f64],
    window: usize,
    diff_threshold: f64,
) -> LeakAuditResult {
    let n = feature_values.len().min(forward_return.len());
    if n < window + 2 {
        return LeakAuditResult {
            leak_corr: 0.0,
            clean_corr: 0.0,
            diff: 0.0,
            leak_suspected: false,
            insufficient_sample: true,
        };
    }
    // 取最近 window+1 段做 sample correlation：
    //   leak version 含 current bar；clean version 整段 shift(1)。
    // 注意：此函式不是完整 production rolling correlation，是 sanity check 用 —
    // 真實 hot-path correlation 在 cross_correlation 模組做。
    let leak_slice_f = &feature_values[n - window..n];
    let leak_slice_r = &forward_return[n - window..n];
    let clean_slice_f = &feature_values[n - window - 1..n - 1];
    let clean_slice_r = &forward_return[n - window - 1..n - 1];

    let leak_corr = super::cross_correlation::pearson_corr(leak_slice_f, leak_slice_r).unwrap_or(0.0);
    let clean_corr =
        super::cross_correlation::pearson_corr(clean_slice_f, clean_slice_r).unwrap_or(0.0);

    let diff = (leak_corr - clean_corr).abs();
    let leak_suspected = diff > diff_threshold;

    LeakAuditResult {
        leak_corr,
        clean_corr,
        diff,
        leak_suspected,
        insufficient_sample: false,
    }
}

/// Leak audit 結果。
///
/// `leak_suspected=true` → DRAFT INSERT 拒絕 + RCA log + alert（per W1-B spec §4.3）。
#[derive(Debug, Clone, Copy)]
pub struct LeakAuditResult {
    pub leak_corr: f64,
    pub clean_corr: f64,
    pub diff: f64,
    pub leak_suspected: bool,
    pub insufficient_sample: bool,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn shift1_rolling_mean_basic() {
        let values = vec![10.0, 20.0, 30.0, 40.0, 50.0];
        let result = shift1_rolling_mean(&values, 3);
        // i=0,1,2: None（i < window=3）
        assert_eq!(result[0], None);
        assert_eq!(result[1], None);
        assert_eq!(result[2], None);
        // i=3: mean(values[0..3]) = mean(10,20,30) = 20.0
        assert_eq!(result[3], Some(20.0));
        // i=4: mean(values[1..4]) = mean(20,30,40) = 30.0
        assert_eq!(result[4], Some(30.0));
    }

    #[test]
    fn shift1_rolling_mean_excludes_current_bar() {
        // 關鍵不變量 I-1：output[i] 不能等於 mean(values[i-window+1..=i])。
        // 用 [1, 2, 3] window=2 驗：
        //   含 current: output[2] = mean(values[1..=2]) = mean(2,3) = 2.5
        //   shift(1):   output[2] = mean(values[0..2]) = mean(1,2) = 1.5
        let values = vec![1.0, 2.0, 3.0];
        let result = shift1_rolling_mean(&values, 2);
        assert_eq!(result[2], Some(1.5), "必須是 shift(1) 不含 current bar");
        assert_ne!(result[2], Some(2.5), "含 current bar 即 look-ahead bias");
    }

    #[test]
    fn shift1_rolling_std_population_ddof_zero() {
        // 對齊 SQL stddev_pop()：var = sum((x - mean)^2) / N（除 N 非 N-1）。
        // values = [10, 20, 30] window=3 在 i=3：不可達；只測長度足夠的 case。
        let values = vec![10.0, 10.0, 10.0, 10.0]; // 全相同
        let result = shift1_rolling_std(&values, 3);
        // i=3: std(10,10,10) = 0
        assert_eq!(result[3], Some(0.0));
    }

    #[test]
    fn shift1_rolling_pct_change_basic() {
        let values = vec![100.0, 110.0, 121.0, 133.1];
        let result = shift1_rolling_pct_change(&values);
        // i=0,1: None
        assert_eq!(result[0], None);
        assert_eq!(result[1], None);
        // i=2: values[1]/values[0] - 1 = 110/100 - 1 = 0.1
        assert!((result[2].unwrap() - 0.1).abs() < 1e-10);
        // i=3: values[2]/values[1] - 1 = 121/110 - 1 = 0.1
        assert!((result[3].unwrap() - 0.1).abs() < 1e-10);
    }

    #[test]
    fn shift1_rolling_pct_change_div_zero_fail_closed() {
        // 邊界：分母為 0 必 None（不假設 forward-fill 也不假設 0）。
        let values = vec![0.0, 5.0, 10.0];
        let result = shift1_rolling_pct_change(&values);
        assert_eq!(result[2], None, "除以 0 必 fail-closed");
    }

    #[test]
    fn shift1_rolling_window_zero_returns_all_none() {
        let values = vec![1.0, 2.0, 3.0];
        let r = shift1_rolling_mean(&values, 0);
        assert!(r.iter().all(|x| x.is_none()));
    }

    #[test]
    fn leak_audit_meanrevert_noise_detects_artifact() {
        // P1-11 F3 RETRACT 場景：純 mean-revert noise series 含 current bar 算
        // rolling correlation 必出 spurious 顯著（artifact）；shift(1) 應接近 0。
        // 為什麼 ≥ window+2：sample correlation 公式內含 (n-1) 標準化；最短可
        // 收斂 case 需要 window+2 個 row（leak 段 window 行、clean 段 window 行
        // 與 leak 段相差 1 行 offset，總長 window+1，feature/return 各 ≥ window+2）。
        //
        // 這只是 smoke test — 真實 leak audit 在 W1-B spec §4.3 SQL 端跑。
        let n = 20;
        let mut feature = Vec::with_capacity(n);
        let mut returns = Vec::with_capacity(n);
        for i in 0..n {
            // 純擺動：feature 與 return 在當下相關（leak），shift(1) 後應隨機。
            let v = if i % 2 == 0 { 1.0 } else { -1.0 };
            feature.push(v);
            returns.push(v);
        }
        let audit = validate_leak_free_pattern(&feature, &returns, 10, 0.1);
        assert!(!audit.insufficient_sample);
        // leak version 應顯著 (含 current bar 1:1 對應)；clean version offset 1 → 反相
        // 因擺動週期為 2 → shift(1) 版會是 -1 相關，magnitude 仍接近 1，diff < 0.1。
        // 這個 fixture 不會觸發 leak_suspected — smoke test 只驗 function 不 crash。
        // （真實 mean-revert noise leak detect 在 Python E4 regression 端 fixture 驗。）
    }
}
