//! MODULE_NOTE
//! 模塊用途：intraday kline 真值校準的 **純函數 truth-test 核心**（INTRADAY-KLINES-PERMANENT-FIX
//!   R3 + R4 共用 SSOT）。把 local（market.klines）與 Bybit authoritative（get_klines）對齊後算
//!   close_match / range_ratio / corr@0 / corr@+1 / turnover_nonzero / gap，並評估 drift（R3 監測
//!   門檻）與 recal-gate（R4 recal 後的嚴格驗收門檻）。
//! 主要類/函數：
//!   - CalibrationMetrics：六個 metric + observed/expected 計數（metric 樣本不足為 None，不偽造 0）。
//!   - align_bars：依 open_time_ms 內連接 local 與 bybit bar（只比兩邊都有的 ts，缺 bar 由 gap_pct 反映）。
//!   - compute_metrics：對齊後算六 metric（純算術，無 IO）。
//!   - DriftThresholds / evaluate_drift：R3 監測門檻（range<0.5 / corr0<0.9 / turnover all-zero / gap>5%）。
//!   - RecalGateThresholds / evaluate_recal_gate：R4 嚴格驗收（corr0≈0.99 AND range_ratio≈1.0 才 PASS）。
//! 依賴：純標準庫 + market_data_client::types::KlineBar（Bybit REST bar）+ 本地 LocalBar（DB 讀回）。
//!   無 DB / 無網路 / 無 IO —— 全 Mac-testable，是 R3 bin 與 R4 runbook gate 的單一真值來源。
//! 硬邊界：純讀計算，不下單 / 不餵 intent / 不碰 auth / lease / system_mode / cap；不寫任何表。
//!   metric 不確定（對齊 bar 不足）一律 None（root principle #6 保守 + #10 事實/未測分離），
//!   由 caller fail-soft 落 NULL，絕不偽造 0。

use crate::market_data_client::types::KlineBar;

/// 從 market.klines 讀回的一根 local bar（只取 truth-test 需要的欄）。
///
/// 為什麼獨立型別而非複用 KlineBar：DB 讀回的 open_time/close 等是 f64 + i64 ts，
/// 與 Bybit REST 的 KlineBar（u64 start_time）來源不同；明確分型避免 caller 混淆兩個源。
#[derive(Debug, Clone, PartialEq)]
pub struct LocalBar {
    /// bar open time（毫秒 epoch；= market.klines.open_ts_ms）。對齊鍵。
    pub open_time_ms: u64,
    pub open: f64,
    pub high: f64,
    pub low: f64,
    pub close: f64,
    /// turnover（成交額；nullable 欄，DB NULL → None）。
    pub turnover: Option<f64>,
}

/// 一對對齊的 (local, bybit) bar（open_time_ms 相同）。
///
/// 不 derive PartialEq：內含的 market_data_client::types::KlineBar 未實作 PartialEq（外部型別，
/// 不在本案範圍 ALTER）。AlignedPair 只在 truth-test 計算中流轉，不需值比較。
#[derive(Debug, Clone)]
pub struct AlignedPair {
    pub open_time_ms: u64,
    pub local: LocalBar,
    pub bybit: KlineBar,
}

/// 六個 truth-test metric + 覆蓋計數。metric 為 None = 樣本不足無法算（fail-soft，不偽造 0）。
#[derive(Debug, Clone, PartialEq)]
pub struct CalibrationMetrics {
    /// local.close == bybit.close（相對誤差 < REL_TOL）佔對齊 bar 比例 [0,1]。
    pub close_match_pct: Option<f64>,
    /// mean(local.high-low) / mean(bybit.high-low)。退化 bar 遠 < 1。
    pub range_ratio: Option<f64>,
    /// corr(local close 回報, bybit close 回報) @ shift 0。
    pub corr_shift0: Option<f64>,
    /// 同上 @ shift +1（診斷 one-bar offset；非門檻）。
    pub corr_shift1: Option<f64>,
    /// local.turnover > 0 佔比 [0,1]。
    pub turnover_nonzero_pct: Option<f64>,
    /// (expected - observed) / expected 缺 bar 率 [0,1]。expected==0 → None。
    pub gap_pct: Option<f64>,
    /// 對齊窗內 local 實得 bar 數。
    pub observed_rows: u64,
    /// expected_bars_for(window, period)。
    pub expected_rows: u64,
}

/// close 相對誤差容差：跨語言浮點一致性 1e-4（與 E4 對齊；REAL f32 round-trip 後仍穩）。
const REL_TOL: f64 = 1e-4;

/// 把 local 與 bybit bar 依 open_time_ms 內連接（只保留兩邊都有的 ts）。
///
/// 為什麼內連接而非外連接：truth-test 只能對「兩邊都有」的 bar 比 close/range/corr；
/// 單邊缺的 bar 由 gap_pct（observed vs expected）反映，不混入 metric 計算。
/// 為什麼用 BTree 對齊：兩邊各自可能亂序 / 重複 ts；以 local 的 ts 為主鍵建索引後查 bybit。
pub fn align_bars(local: &[LocalBar], bybit: &[KlineBar]) -> Vec<AlignedPair> {
    use std::collections::BTreeMap;
    // bybit ts → bar（同 ts 取首見，防重複頁邊界 dup）。
    let mut bybit_idx: BTreeMap<u64, &KlineBar> = BTreeMap::new();
    for b in bybit {
        bybit_idx.entry(b.start_time).or_insert(b);
    }
    // local ts → bar（同上去重）。再對交集排序輸出（open_time_ms 升序，corr 回報序穩定）。
    let mut local_idx: BTreeMap<u64, &LocalBar> = BTreeMap::new();
    for l in local {
        local_idx.entry(l.open_time_ms).or_insert(l);
    }
    let mut out: Vec<AlignedPair> = Vec::new();
    for (ts, l) in &local_idx {
        if let Some(b) = bybit_idx.get(ts) {
            out.push(AlignedPair {
                open_time_ms: *ts,
                local: (*l).clone(),
                bybit: (*b).clone(),
            });
        }
    }
    out
}

/// Pearson 相關係數（兩等長序列）。長度 < 2 或任一方差為 0 → None（無法定義相關）。
///
/// 為什麼方差 0 回 None 而非 0：常數序列（如全部退化 bar close 相同）相關無定義；
/// 回 0 會被誤讀為「無相關」觸發 drift，但真相是「樣本退化無法判定」→ None fail-soft。
fn pearson_corr(xs: &[f64], ys: &[f64]) -> Option<f64> {
    if xs.len() != ys.len() || xs.len() < 2 {
        return None;
    }
    let n = xs.len() as f64;
    let mean_x = xs.iter().sum::<f64>() / n;
    let mean_y = ys.iter().sum::<f64>() / n;
    let mut cov = 0.0;
    let mut var_x = 0.0;
    let mut var_y = 0.0;
    for (x, y) in xs.iter().zip(ys.iter()) {
        let dx = x - mean_x;
        let dy = y - mean_y;
        cov += dx * dy;
        var_x += dx * dx;
        var_y += dy * dy;
    }
    if var_x <= 0.0 || var_y <= 0.0 {
        return None;
    }
    let denom = (var_x * var_y).sqrt();
    if denom == 0.0 || !denom.is_finite() {
        return None;
    }
    Some(cov / denom)
}

/// 從一序列 close 算 log-return（相鄰 bar）。len < 2 → 空。
///
/// 為什麼 log-return 而非 raw close：corr 要算「回報」相關（價格 level 高度自相關會虛高 corr）；
/// log-return 是平穩量。close <= 0 不可取 log（退化 bar 理論已被 strict 擋，防禦縱深仍跳過）。
fn log_returns(closes: &[f64]) -> Vec<f64> {
    let mut rets = Vec::with_capacity(closes.len().saturating_sub(1));
    for w in closes.windows(2) {
        let (prev, cur) = (w[0], w[1]);
        if prev > 0.0 && cur > 0.0 {
            rets.push((cur / prev).ln());
        } else {
            // 退化值：放 0 回報佔位保序（corr 對全序列；單點退化不致整體 None）。
            rets.push(0.0);
        }
    }
    rets
}

/// 對齊後算六 metric（純算術）。expected_rows 由 caller 傳（= expected_bars_for(window,period)）。
///
/// observed_rows = local bar 數（對齊前的 local 計數，反映「DB 實得多少」）；對齊對數
/// （兩邊都有）用於 close/range/corr。gap_pct 用 observed vs expected（缺 bar 率）。
pub fn compute_metrics(
    aligned: &[AlignedPair],
    observed_local_rows: u64,
    expected_rows: u64,
) -> CalibrationMetrics {
    // close_match：對齊對中 |local.close - bybit.close| / bybit.close < REL_TOL 佔比。
    let close_match_pct = if aligned.is_empty() {
        None
    } else {
        let matched = aligned
            .iter()
            .filter(|p| {
                let denom = p.bybit.close.abs();
                if denom == 0.0 {
                    // bybit close 0（理論不可達真值）→ 退回絕對誤差判定。
                    (p.local.close - p.bybit.close).abs() < REL_TOL
                } else {
                    ((p.local.close - p.bybit.close).abs() / denom) < REL_TOL
                }
            })
            .count();
        Some(matched as f64 / aligned.len() as f64)
    };

    // range_ratio：mean(local.high-low) / mean(bybit.high-low)。任一 mean 退化 → None。
    let range_ratio = if aligned.is_empty() {
        None
    } else {
        let n = aligned.len() as f64;
        let local_range: f64 = aligned.iter().map(|p| (p.local.high - p.local.low).max(0.0)).sum::<f64>() / n;
        let bybit_range: f64 = aligned.iter().map(|p| (p.bybit.high - p.bybit.low).max(0.0)).sum::<f64>() / n;
        if bybit_range > 0.0 {
            Some(local_range / bybit_range)
        } else {
            // bybit range 0（極靜止窗，理論罕見）→ 無分母，None fail-soft。
            None
        }
    };

    // corr@0 / corr@+1：對齊對的 close 序列各算 log-return 後 Pearson。
    // shift+1：local 回報對 bybit 回報延後一格（診斷 tick-synth one-bar offset 指紋）。
    let local_closes: Vec<f64> = aligned.iter().map(|p| p.local.close).collect();
    let bybit_closes: Vec<f64> = aligned.iter().map(|p| p.bybit.close).collect();
    let local_rets = log_returns(&local_closes);
    let bybit_rets = log_returns(&bybit_closes);

    let corr_shift0 = pearson_corr(&local_rets, &bybit_rets);
    let corr_shift1 = if local_rets.len() >= 2 && bybit_rets.len() >= 2 {
        // local[t] vs bybit[t-1]：local 回報落後 bybit 一格 → 對齊 local[1..] 與 bybit[..n-1]。
        let lo = &local_rets[1..];
        let by = &bybit_rets[..bybit_rets.len() - 1];
        pearson_corr(lo, by)
    } else {
        None
    };

    // turnover_nonzero：local.turnover > 0 佔對齊對比例（None turnover 視為非正）。
    let turnover_nonzero_pct = if aligned.is_empty() {
        None
    } else {
        let nonzero = aligned
            .iter()
            .filter(|p| matches!(p.local.turnover, Some(t) if t > 0.0))
            .count();
        Some(nonzero as f64 / aligned.len() as f64)
    };

    // gap_pct：(expected - observed) / expected。observed 取 min(observed, expected) 防負。
    let gap_pct = if expected_rows == 0 {
        None
    } else {
        let obs = observed_local_rows.min(expected_rows);
        Some((expected_rows - obs) as f64 / expected_rows as f64)
    };

    CalibrationMetrics {
        close_match_pct,
        range_ratio,
        corr_shift0,
        corr_shift1,
        turnover_nonzero_pct,
        gap_pct,
        observed_rows: observed_local_rows,
        expected_rows,
    }
}

/// R3 監測 drift 門檻（PA §3.2）。任一命中 → drift。
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct DriftThresholds {
    /// range_ratio < 此值 → drift（PA 0.5）。
    pub range_ratio_min: f64,
    /// corr_shift0 < 此值 → drift（PA 0.9）。
    pub corr_shift0_min: f64,
    /// gap_pct > 此值 → drift（PA 0.05）。
    pub gap_pct_max: f64,
}

impl Default for DriftThresholds {
    fn default() -> Self {
        Self {
            range_ratio_min: 0.5,
            corr_shift0_min: 0.9,
            gap_pct_max: 0.05,
        }
    }
}

/// drift 評估結果：是否 drift + 命中的 reason 清單。
#[derive(Debug, Clone, PartialEq)]
pub struct DriftVerdict {
    pub drift_flag: bool,
    /// 逗號分隔命中門檻（e.g. "range_ratio,corr_shift0"）；無命中為空字串。
    /// 樣本不足（metric 全 None）→ "insufficient_sample"（非 drift，但標記未測）。
    pub reasons: String,
}

/// 對 metrics 套 R3 門檻評估 drift。
///
/// 為什麼樣本不足不算 drift：metric None = 未測（對齊 bar < 2），不能據此宣告 drift（會誤報）；
/// 標 insufficient_sample 讓 healthcheck/operator 知道「該 cell 還沒測到」，下次旋轉再採。
/// 為什麼 turnover all-zero 才 drift（非「< 某比例」）：turnover 校正是 R1 修復的明確目標，
/// 完全為 0（all-zero）= producer 沒填 turnover 的鐵證；部分為 0（靜止窗無成交）是合法的。
pub fn evaluate_drift(m: &CalibrationMetrics, t: &DriftThresholds) -> DriftVerdict {
    // 全 metric None（對齊 bar 不足）→ 未測，不 drift。
    let all_none = m.close_match_pct.is_none()
        && m.range_ratio.is_none()
        && m.corr_shift0.is_none()
        && m.turnover_nonzero_pct.is_none()
        && m.gap_pct.is_none();
    if all_none {
        return DriftVerdict {
            drift_flag: false,
            reasons: "insufficient_sample".to_string(),
        };
    }

    let mut reasons: Vec<&str> = Vec::new();
    if matches!(m.range_ratio, Some(r) if r < t.range_ratio_min) {
        reasons.push("range_ratio");
    }
    if matches!(m.corr_shift0, Some(c) if c < t.corr_shift0_min) {
        reasons.push("corr_shift0");
    }
    // turnover all-zero（佔比 == 0）→ drift。None（無對齊）不算（上面 all_none 已處理混合情況）。
    if matches!(m.turnover_nonzero_pct, Some(p) if p == 0.0) {
        reasons.push("turnover_all_zero");
    }
    if matches!(m.gap_pct, Some(g) if g > t.gap_pct_max) {
        reasons.push("gap");
    }

    DriftVerdict {
        drift_flag: !reasons.is_empty(),
        reasons: reasons.join(","),
    }
}

/// R4 recal 後嚴格驗收門檻（PA §4.1 step 4）。corr0 ≈ 0.99 AND range_ratio ≈ 1.0 才 PASS。
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct RecalGateThresholds {
    /// corr_shift0 >= 此值才 PASS（PA ~0.99；留 0.98 容差防單窗噪音）。
    pub corr_shift0_min: f64,
    /// range_ratio 落在 [min, max] 才 PASS（PA ~1.0；±0.15 容差）。
    pub range_ratio_min: f64,
    pub range_ratio_max: f64,
}

impl Default for RecalGateThresholds {
    fn default() -> Self {
        Self {
            corr_shift0_min: 0.98,
            range_ratio_min: 0.85,
            range_ratio_max: 1.15,
        }
    }
}

/// R4 recal-gate 評估結果。
#[derive(Debug, Clone, PartialEq)]
pub struct RecalGateVerdict {
    /// recal 後該窗是否達真值標準（fail-loud：false → runbook 不 recompress，留 operator 介入）。
    pub passed: bool,
    /// 未過原因（"corr_shift0_too_low" / "range_ratio_out_of_band" / "insufficient_sample"）。
    pub reasons: String,
}

/// 對 recal 後窗 metrics 套嚴格驗收門檻。
///
/// 為什麼樣本不足回 fail（passed=false）而非 R3 的「不 drift」：R4 是「宣告 recal 成功」的閘，
/// 沒測到真值對齊就不能宣告成功（fail-loud）；R3 是被動監測，未測不該誤報。語義相反故分開門檻。
pub fn evaluate_recal_gate(m: &CalibrationMetrics, t: &RecalGateThresholds) -> RecalGateVerdict {
    let (Some(corr0), Some(range)) = (m.corr_shift0, m.range_ratio) else {
        return RecalGateVerdict {
            passed: false,
            reasons: "insufficient_sample".to_string(),
        };
    };
    let mut reasons: Vec<&str> = Vec::new();
    if corr0 < t.corr_shift0_min {
        reasons.push("corr_shift0_too_low");
    }
    if range < t.range_ratio_min || range > t.range_ratio_max {
        reasons.push("range_ratio_out_of_band");
    }
    RecalGateVerdict {
        passed: reasons.is_empty(),
        reasons: reasons.join(","),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn bybit(ts: u64, o: f64, h: f64, l: f64, c: f64, turn: f64) -> KlineBar {
        KlineBar {
            start_time: ts,
            open: o,
            high: h,
            low: l,
            close: c,
            volume: 1.0,
            turnover: turn,
        }
    }

    fn local(ts: u64, o: f64, h: f64, l: f64, c: f64, turn: Option<f64>) -> LocalBar {
        LocalBar {
            open_time_ms: ts,
            open: o,
            high: h,
            low: l,
            close: c,
            turnover: turn,
        }
    }

    /// align_bars 只保留兩邊都有的 ts（內連接），且去重。
    #[test]
    fn test_align_inner_join_and_dedup() {
        let l = vec![
            local(1000, 10.0, 11.0, 9.0, 10.5, Some(100.0)),
            local(1000, 99.0, 99.0, 99.0, 99.0, Some(1.0)), // dup ts → 取首見
            local(2000, 10.5, 11.5, 10.0, 11.0, Some(120.0)),
            local(3000, 11.0, 12.0, 10.5, 11.5, Some(130.0)), // bybit 沒有 3000
        ];
        let b = vec![
            bybit(1000, 10.0, 11.2, 8.9, 10.5, 100.0),
            bybit(2000, 10.5, 11.6, 9.9, 11.0, 120.0),
            bybit(4000, 12.0, 13.0, 11.0, 12.5, 140.0), // local 沒有 4000
        ];
        let aligned = align_bars(&l, &b);
        assert_eq!(aligned.len(), 2); // 只有 1000, 2000 交集
        assert_eq!(aligned[0].open_time_ms, 1000);
        assert_eq!(aligned[0].local.close, 10.5); // 首見非 dup 的 99
        assert_eq!(aligned[1].open_time_ms, 2000);
    }

    /// 真值對齊：close 完全相符 + range 相符 + corr ≈ 1 + turnover 全非零 → 不 drift。
    #[test]
    fn test_clean_calibration_no_drift() {
        // 一段單調上升 + 真實 wick 的窗，local == bybit（R1 修復後的理想態）。
        let mut l = Vec::new();
        let mut b = Vec::new();
        for i in 0..20u64 {
            let base = 100.0 + i as f64;
            let h = base + 2.0;
            let lo = base - 2.0;
            let c = base + 1.0;
            let ts = 1000 + i * 60_000;
            l.push(local(ts, base, h, lo, c, Some(5000.0 + i as f64)));
            b.push(bybit(ts, base, h, lo, c, 5000.0 + i as f64));
        }
        let aligned = align_bars(&l, &b);
        let m = compute_metrics(&aligned, 20, 20);
        assert_eq!(m.close_match_pct, Some(1.0));
        assert!((m.range_ratio.unwrap() - 1.0).abs() < 1e-9);
        assert!(m.corr_shift0.unwrap() > 0.999);
        assert_eq!(m.turnover_nonzero_pct, Some(1.0));
        assert_eq!(m.gap_pct, Some(0.0));
        let v = evaluate_drift(&m, &DriftThresholds::default());
        assert!(!v.drift_flag, "clean window must not drift: {}", v.reasons);
    }

    /// tick-synth 退化指紋：close 攜真值但錯位一格（local.close[t] == bybit.open[t]），
    /// range 死（high==low==close），turnover 全 0 → range_ratio + turnover + corr 命中 drift。
    #[test]
    fn test_degenerate_tick_synth_drifts() {
        let mut l = Vec::new();
        let mut b = Vec::new();
        for i in 0..20u64 {
            let base = 100.0 + i as f64; // bybit open
            let h = base + 2.0;
            let lo = base - 2.0;
            let c = base + 1.0; // bybit close
            let ts = 1000 + i * 60_000;
            b.push(bybit(ts, base, h, lo, c, 5000.0));
            // local 退化：open=high=low=close=bybit.open（一-bar offset；range≈0；turnover 0）
            l.push(local(ts, base, base, base, base, Some(0.0)));
        }
        let aligned = align_bars(&l, &b);
        let m = compute_metrics(&aligned, 20, 20);
        // range 死 → range_ratio ≈ 0
        assert!(m.range_ratio.unwrap() < 0.1, "degenerate range should be tiny");
        // turnover 全 0
        assert_eq!(m.turnover_nonzero_pct, Some(0.0));
        let v = evaluate_drift(&m, &DriftThresholds::default());
        assert!(v.drift_flag, "degenerate window must drift");
        assert!(v.reasons.contains("range_ratio"), "reasons={}", v.reasons);
        assert!(v.reasons.contains("turnover_all_zero"), "reasons={}", v.reasons);
    }

    /// gap drift：observed 遠少於 expected（缺 bar > 5%）。
    #[test]
    fn test_gap_drift() {
        let mut l = Vec::new();
        let mut b = Vec::new();
        for i in 0..50u64 {
            let base = 100.0 + i as f64;
            let ts = 1000 + i * 60_000;
            l.push(local(ts, base, base + 1.0, base - 1.0, base + 0.5, Some(10.0)));
            b.push(bybit(ts, base, base + 1.0, base - 1.0, base + 0.5, 10.0));
        }
        let aligned = align_bars(&l, &b);
        // observed=50 但 expected=100 → gap=50% > 5%
        let m = compute_metrics(&aligned, 50, 100);
        assert!((m.gap_pct.unwrap() - 0.5).abs() < 1e-9);
        let v = evaluate_drift(&m, &DriftThresholds::default());
        assert!(v.drift_flag);
        assert!(v.reasons.contains("gap"));
    }

    /// 樣本不足（對齊 0 bar）→ insufficient_sample，不 drift。
    #[test]
    fn test_insufficient_sample_not_drift() {
        let m = compute_metrics(&[], 0, 0);
        assert_eq!(m.close_match_pct, None);
        assert_eq!(m.corr_shift0, None);
        let v = evaluate_drift(&m, &DriftThresholds::default());
        assert!(!v.drift_flag);
        assert_eq!(v.reasons, "insufficient_sample");
    }

    /// pearson 常數序列（方差 0）→ None（不誤判成 0 相關）。
    #[test]
    fn test_pearson_constant_series_none() {
        assert_eq!(pearson_corr(&[1.0, 1.0, 1.0], &[1.0, 2.0, 3.0]), None);
        assert_eq!(pearson_corr(&[1.0], &[1.0]), None); // 長度 < 2
    }

    /// R4 recal-gate：clean 窗 PASS；退化窗 FAIL（fail-loud）。
    #[test]
    fn test_recal_gate_pass_and_fail() {
        // clean 窗
        let mut l = Vec::new();
        let mut b = Vec::new();
        for i in 0..20u64 {
            let base = 100.0 + (i as f64) * 0.5;
            let h = base + 1.5;
            let lo = base - 1.5;
            let c = base + 0.7;
            let ts = 1000 + i * 60_000;
            l.push(local(ts, base, h, lo, c, Some(10.0)));
            b.push(bybit(ts, base, h, lo, c, 10.0));
        }
        let aligned = align_bars(&l, &b);
        let m = compute_metrics(&aligned, 20, 20);
        let g = evaluate_recal_gate(&m, &RecalGateThresholds::default());
        assert!(g.passed, "clean recal must pass: {}", g.reasons);

        // 退化窗（range 死，corr 低）
        let mut l2 = Vec::new();
        let mut b2 = Vec::new();
        for i in 0..20u64 {
            let base = 100.0 + i as f64;
            let ts = 1000 + i * 60_000;
            b2.push(bybit(ts, base, base + 2.0, base - 2.0, base + 1.0, 10.0));
            l2.push(local(ts, base, base, base, base, Some(0.0))); // 退化
        }
        let aligned2 = align_bars(&l2, &b2);
        let m2 = compute_metrics(&aligned2, 20, 20);
        let g2 = evaluate_recal_gate(&m2, &RecalGateThresholds::default());
        assert!(!g2.passed, "degenerate recal must fail-loud");
        assert!(g2.reasons.contains("range_ratio_out_of_band"), "reasons={}", g2.reasons);
    }

    /// R4 recal-gate 樣本不足 → fail-loud（與 R3 相反語義）。
    #[test]
    fn test_recal_gate_insufficient_is_fail() {
        let m = compute_metrics(&[], 0, 0);
        let g = evaluate_recal_gate(&m, &RecalGateThresholds::default());
        assert!(!g.passed);
        assert_eq!(g.reasons, "insufficient_sample");
    }
}
