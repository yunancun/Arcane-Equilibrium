use std::collections::{HashMap, VecDeque};

use super::snapshot::BtcLeadLagPanelSnapshot;
use super::{
    LEAD_WINDOW_SECS_MAIN, LEAD_WINDOW_SECS_SHADOW_300, LEAD_WINDOW_SECS_SHADOW_60, ONE_HOUR_SECS,
    ONE_MIN_SECS, REGIME_EXTREME_BPS, SOURCE_TIER, THRESHOLD_X_BPS, THRESHOLD_Y,
    VOLUME_Z_BASELINE_SECS, XCORR_BASELINE_SECS, XCORR_MIN_SAMPLE,
};

/// 單 symbol 1m tick（緩衝區 element 結構）。
#[derive(Debug, Clone, Copy)]
pub(super) struct PriceTick {
    /// 1m bucket end timestamp（epoch ms）— 預留供 sub-task 4 整合
    /// orderbook timestamp alignment / WS subscription latency 分析使用。
    #[allow(dead_code)]
    pub(super) ts_ms: i64,
    /// close price（USD）。
    close: f64,
    /// 1m bucket volume（base asset）。
    volume: f64,
}

/// `BtcLeadLagProducer` — Sprint N+1 W2 sub-task 1 producer 核心。
///
/// 持有 BTC 1m tick 緩衝區（≥ XCORR_BASELINE_SECS 跨度）+ per-alt-symbol 1m
/// tick 緩衝區。`on_tick` 接受一筆 1m grain 對齊的快照（BTC + alt cohort
/// closes），按 spec §3.1-§3.3 計算所有 metric，emit `BtcLeadLagPanelSnapshot`。
///
/// **生命週期**：
/// - `new(cohort_symbols)` 初始化空緩衝區（cohort 鎖定不變）；
/// - 每 1m grain 呼叫 `on_tick(snapshot_ts_ms, btc_close, btc_volume, alt_closes)`
///   一次（caller 對齊 60s bucket）；不對齊 1m grain → producer 端不 enforce，
///   accept 任何 ts，但 metric 計算依 ts diff 自然衰退到不準；
/// - `latest()` 取最近一次 emit 的 snapshot（None 表尚未 emit）。
///
/// **緩衝區大小**：BTC buffer 上限 = `XCORR_BASELINE_SECS / ONE_MIN_SECS = 60`
/// 個 1m tick；alt buffer 同。**不**保留 raw orderbook（本 sub-task
/// `btc_book_imbalance = 0.0`）。
///
/// **strict shift(N) lookahead-free**：每個 metric 在 push current tick 進
/// buffer **之前** 完成計算（return = (close[t-N] vs close[t]) 用 buffer 內已
/// 存 tick 與 caller 傳入 current tick close 的差，不含未來 tick）。
pub struct BtcLeadLagProducer {
    /// Cohort alt symbols（鎖定不變，writer 寫 V088 alt_symbols column 的順序）。
    pub(super) cohort_symbols: Vec<String>,
    /// BTC 1m tick 緩衝區（max XCORR_BASELINE_SECS 跨度）。
    pub(super) btc_buffer: VecDeque<PriceTick>,
    /// Per-alt-symbol 1m tick 緩衝區。
    alt_buffers: HashMap<String, VecDeque<PriceTick>>,
    /// 最近一次 emit 的 snapshot（caller `latest()` 取）。
    latest_snapshot: Option<BtcLeadLagPanelSnapshot>,
    /// Buffer 容量上限（tick 數，預設 = XCORR_BASELINE_SECS / ONE_MIN_SECS = 60）。
    pub(super) buffer_capacity: usize,
    /// V088 source_tier marker. Diagnostic mode uses a distinct non-promotional tier.
    source_tier: &'static str,
}

impl BtcLeadLagProducer {
    /// 構造新 producer。`cohort_symbols` 對應 spec §2.2 7-symbol cohort
    /// （ETHUSDT / SOLUSDT / XRPUSDT / DOGEUSDT / ADAUSDT / AVAXUSDT / DOTUSDT），
    /// 不含 BTCUSDT（BTC 是 lead source 獨立緩衝區）。
    ///
    /// **Caller 責任**：cohort 排除 BUSDT / INXUSDT / frozen symbols（spec §2.3），
    /// producer 端不重複 enforce（信任 caller 已過濾）。
    pub fn new(cohort_symbols: Vec<String>) -> Self {
        Self::new_with_source_tier(cohort_symbols, SOURCE_TIER)
    }

    pub fn new_with_source_tier(cohort_symbols: Vec<String>, source_tier: &'static str) -> Self {
        let buffer_capacity = (XCORR_BASELINE_SECS / ONE_MIN_SECS) as usize;
        let mut alt_buffers = HashMap::with_capacity(cohort_symbols.len());
        for sym in &cohort_symbols {
            alt_buffers.insert(sym.clone(), VecDeque::with_capacity(buffer_capacity));
        }
        Self {
            cohort_symbols,
            btc_buffer: VecDeque::with_capacity(buffer_capacity),
            alt_buffers,
            latest_snapshot: None,
            buffer_capacity,
            source_tier,
        }
    }

    /// 接受 1m grain 對齊的 BTC + alt cohort tick，計算所有 metric，emit
    /// `BtcLeadLagPanelSnapshot` 並更新 `latest_snapshot`。
    ///
    /// **參數**：
    /// - `snapshot_ts_ms`：1m bucket end timestamp（epoch ms）
    /// - `btc_close`：BTCUSDT 當前 1m close
    /// - `btc_volume`：BTCUSDT 當前 1m volume
    /// - `alt_closes`：cohort alt symbol → 1m close map（缺 symbol = 該 symbol
    ///   本 tick 無 update，緩衝區不 push 該 symbol，xcorr 自然算到舊 sample）
    /// - `btc_book_imbalance`：W2-IMPL-1 (2026-05-11) — top-N orderbook imbalance
    ///   snapshot from WS push slot。`None` = 尚無 WS orderbook event，snapshot
    ///   端寫 NaN（panel column NULL-friendly）；`Some(f64)` ∈ [-1, +1] 真實值。
    ///
    /// **返回**：emit 的 snapshot（同時更新 `latest_snapshot`）。
    ///
    /// **lookahead-free 順序**：先用 buffer 內已存 tick + 當前 caller 傳入
    /// 值計算所有 metric，最後才 push current tick 進 buffer。orderbook imbalance
    /// 由 caller 從 slot 讀，WS push 必早於本 sync tick（rate ~100 Hz vs 1/60s），
    /// 對齊 shift(1)「current bucket 完成時最新」哨值。
    pub fn on_tick(
        &mut self,
        snapshot_ts_ms: i64,
        btc_close: f64,
        btc_volume: f64,
        alt_closes: &HashMap<String, f64>,
        btc_book_imbalance: Option<f64>,
    ) -> BtcLeadLagPanelSnapshot {
        // 1. 計算 BTC lead return — 三檔 N=60/120/300 secs（用 buffer 內已存
        //    tick + current btc_close，strict shift(N) 不含 future）
        let btc_lead_return_pct =
            self.compute_btc_lead_return(btc_close, LEAD_WINDOW_SECS_MAIN as u64);
        let btc_lead_return_pct_60s =
            self.compute_btc_lead_return(btc_close, LEAD_WINDOW_SECS_SHADOW_60 as u64);
        let btc_lead_return_pct_300s =
            self.compute_btc_lead_return(btc_close, LEAD_WINDOW_SECS_SHADOW_300 as u64);

        // 2. 計算 BTC volume z-score（rolling 1h baseline，shift(1) 不含 current）
        let btc_volume_z = self.compute_btc_volume_z(btc_volume);

        // 3. 計算 per-alt cross-correlation（rolling 1h，主信號 N=120）
        let mut alt_xcorr = Vec::with_capacity(self.cohort_symbols.len());
        let mut alt_expected_dir = Vec::with_capacity(self.cohort_symbols.len());
        // 預先克隆 cohort 以避開 self 借用，符合 spec 中 alt_symbols 與
        // alt_xcorr / alt_expected_dir 同序對齊不變式。
        let cohort = self.cohort_symbols.clone();
        for sym in &cohort {
            let alt_close_now = alt_closes.get(sym).copied();
            let xcorr = self.compute_alt_xcorr(sym, alt_close_now);
            alt_xcorr.push(xcorr);

            // expected_dir per spec §3.3
            let dir = compute_expected_dir(btc_lead_return_pct, xcorr);
            alt_expected_dir.push(dir);
        }

        // 4. regime_tag — per spec §9 v1.1 #5
        //    用 BTC 1h return shift(1)：current close vs 1h 前的 buffer tick
        let regime_tag = self.compute_regime_tag(btc_close);

        // 5. 構造 snapshot（before push current tick）
        // W2-IMPL-1 (2026-05-11) — `btc_book_imbalance` 從 caller 傳入 slot
        // snapshot 取值。`None` 表 WS orderbook 尚未提供 → 寫 NaN（V088 REAL
        // column 接 NaN literal，下游 evaluator `WHERE NOT btc_book_imbalance =
        // 'NaN'::REAL` 過濾，避免 0.0 假值污染 lost evidence）。
        let snapshot = BtcLeadLagPanelSnapshot {
            snapshot_ts_ms,
            lead_window_secs: LEAD_WINDOW_SECS_MAIN,
            btc_lead_return_pct,
            btc_lead_return_pct_60s,
            btc_lead_return_pct_300s,
            btc_volume_z,
            btc_book_imbalance: btc_book_imbalance.unwrap_or(f64::NAN),
            alt_symbols: cohort.clone(),
            alt_xcorr,
            alt_expected_dir,
            regime_tag,
            source_tier: self.source_tier.to_string(),
        };

        // 6. push current tick 進 buffer（lookahead-free 邊界：metric 已算完）
        self.push_btc_tick(snapshot_ts_ms, btc_close, btc_volume);
        for sym in &cohort {
            if let Some(close) = alt_closes.get(sym) {
                self.push_alt_tick(sym, snapshot_ts_ms, *close, 0.0);
            }
        }

        // 7. 更新 latest + 返回
        self.latest_snapshot = Some(snapshot.clone());
        snapshot
    }

    /// 取最近一次 emit 的 snapshot 引用。None 表 producer 尚未跑過 `on_tick`。
    pub fn latest(&self) -> Option<&BtcLeadLagPanelSnapshot> {
        self.latest_snapshot.as_ref()
    }

    // ── 內部 helper ──

    /// 計算 BTC lead return bps over N seconds，strict shift(N) 不含 current。
    /// `current_close` 是 caller 傳入但 *尚未* push 進 buffer 的 close；
    /// buffer 內 tick 全是 t < current 的 sample。
    ///
    /// 公式：`(current_close - close[t-N]) / close[t-N] * 10000`（bps）
    /// 樣本不足 → NaN。
    fn compute_btc_lead_return(&self, current_close: f64, n_secs: u64) -> f64 {
        // n_secs 對應 n_ticks = n_secs / 60（1m grain）。
        // shift(N) 取 buffer 倒數第 n_ticks 筆 — 不含 current（current 還沒 push）。
        let n_ticks = (n_secs / ONE_MIN_SECS) as usize;
        if self.btc_buffer.len() < n_ticks {
            return f64::NAN;
        }
        // 倒數第 n_ticks 筆 = buffer.len() - n_ticks 索引（0-based）
        let idx = self.btc_buffer.len() - n_ticks;
        let past_close = self.btc_buffer[idx].close;
        if past_close <= 0.0 {
            return f64::NAN;
        }
        ((current_close - past_close) / past_close) * 10_000.0
    }

    /// 計算 BTC volume z-score（rolling 1h baseline，shift(1) 不含 current）。
    /// baseline mean / std 從 buffer 內 tick 算（不含 current）；不足 → NaN。
    fn compute_btc_volume_z(&self, current_volume: f64) -> f64 {
        let n_min = (VOLUME_Z_BASELINE_SECS / ONE_MIN_SECS) as usize;
        if self.btc_buffer.len() < n_min.min(10) {
            // 至少 10 sample 才算 z-score（避免 0 / NaN）
            return f64::NAN;
        }
        let take_n = self.btc_buffer.len().min(n_min);
        // 取最近 take_n 個 tick（不含 current — current 還沒 push）
        let start = self.btc_buffer.len() - take_n;
        let vols: Vec<f64> = self
            .btc_buffer
            .iter()
            .skip(start)
            .map(|t| t.volume)
            .collect();
        let mean = vols.iter().sum::<f64>() / vols.len() as f64;
        let variance = vols.iter().map(|v| (*v - mean).powi(2)).sum::<f64>() / vols.len() as f64;
        let std_dev = variance.sqrt();
        if std_dev <= f64::EPSILON {
            return f64::NAN;
        }
        (current_volume - mean) / std_dev
    }

    /// 計算 per-alt cross-correlation vs BTC lead return（rolling 1h，主 N=120s）。
    /// 對齊 spec §3.2：BTC lead window = past 1h buffer 的 N-step return；
    /// alt follow window = past 1h buffer 的 N-step return（shift forward N）。
    /// 至少 XCORR_MIN_SAMPLE (=30) 個 N-step return pair 才算；不足 → NaN。
    fn compute_alt_xcorr(&self, sym: &str, _alt_close_now: Option<f64>) -> f64 {
        let n_ticks = (LEAD_WINDOW_SECS_MAIN as u64 / ONE_MIN_SECS) as usize; // 2 ticks for N=120s
        if n_ticks < 1 {
            return f64::NAN;
        }
        let alt_buffer = match self.alt_buffers.get(sym) {
            Some(b) => b,
            None => return f64::NAN,
        };
        // 樣本對：past N-step btc return + past N-step alt return
        // shift forward N 對齊：alt[t] vs btc[t-N]
        let min_buffer = XCORR_MIN_SAMPLE + n_ticks;
        if self.btc_buffer.len() < min_buffer || alt_buffer.len() < min_buffer {
            return f64::NAN;
        }
        let pair_count = self.btc_buffer.len().min(alt_buffer.len()) - n_ticks;
        if pair_count < XCORR_MIN_SAMPLE {
            return f64::NAN;
        }

        // 收 btc N-step return 序列（bps）
        let mut btc_returns = Vec::with_capacity(pair_count);
        let mut alt_returns = Vec::with_capacity(pair_count);
        // i 從 n_ticks 開始（避免 shift 越界）
        for i in n_ticks..(n_ticks + pair_count) {
            let btc_past = self.btc_buffer[i - n_ticks].close;
            let btc_now = self.btc_buffer[i].close;
            let alt_past = alt_buffer[i - n_ticks].close;
            let alt_now = alt_buffer[i].close;
            if btc_past <= 0.0 || alt_past <= 0.0 {
                continue;
            }
            btc_returns.push(((btc_now - btc_past) / btc_past) * 10_000.0);
            alt_returns.push(((alt_now - alt_past) / alt_past) * 10_000.0);
        }

        if btc_returns.len() < XCORR_MIN_SAMPLE {
            return f64::NAN;
        }
        pearson_corr(&btc_returns, &alt_returns)
    }

    /// 計算 regime_tag — per spec §9 v1.1 #5。
    /// 公式：BTC 1h return = (current_close - btc_buffer[1h_ago].close) /
    ///                       btc_buffer[1h_ago].close * 10000 (bps)
    ///       |1h return| > 200 bps → "extreme"，否則 "normal"
    /// 樣本不足 → "normal"（保守 default，per spec §9：unknown 不計入 extreme）。
    fn compute_regime_tag(&self, current_close: f64) -> String {
        let n_ticks_1h = (ONE_HOUR_SECS / ONE_MIN_SECS) as usize;
        if self.btc_buffer.len() < n_ticks_1h {
            return "normal".to_string();
        }
        let idx = self.btc_buffer.len() - n_ticks_1h;
        let past_close = self.btc_buffer[idx].close;
        if past_close <= 0.0 {
            return "normal".to_string();
        }
        let return_bps = ((current_close - past_close) / past_close) * 10_000.0;
        if return_bps.abs() > REGIME_EXTREME_BPS {
            "extreme".to_string()
        } else {
            "normal".to_string()
        }
    }

    fn push_btc_tick(&mut self, ts_ms: i64, close: f64, volume: f64) {
        if self.btc_buffer.len() >= self.buffer_capacity {
            self.btc_buffer.pop_front();
        }
        self.btc_buffer.push_back(PriceTick {
            ts_ms,
            close,
            volume,
        });
    }

    fn push_alt_tick(&mut self, sym: &str, ts_ms: i64, close: f64, volume: f64) {
        let buffer = match self.alt_buffers.get_mut(sym) {
            Some(b) => b,
            None => return,
        };
        if buffer.len() >= self.buffer_capacity {
            buffer.pop_front();
        }
        buffer.push_back(PriceTick {
            ts_ms,
            close,
            volume,
        });
    }

    /// Cohort symbols 不可變引用（observability + test helper）。
    pub fn cohort_symbols(&self) -> &[String] {
        &self.cohort_symbols
    }
}

/// 計算 expected_dir per alt symbol — spec §3.3 公式直譯。
///
/// 邏輯：
/// - |xcorr| < THRESHOLD_Y → 0（xcorr 太弱，不 trust BTC 預測力）
/// - btc_lead_return > +THRESHOLD_X_BPS → +1 * sign(xcorr)
/// - btc_lead_return < -THRESHOLD_X_BPS → -1 * sign(xcorr)
/// - 其他 → 0
///
/// xcorr NaN 或 btc_lead_return NaN → 0 fail-closed（未知就保守 0）。
pub fn compute_expected_dir(btc_lead_return_bps: f64, xcorr: f64) -> i8 {
    if xcorr.is_nan() || btc_lead_return_bps.is_nan() {
        return 0;
    }
    if xcorr.abs() < THRESHOLD_Y {
        return 0;
    }
    let xcorr_sign: i8 = if xcorr > 0.0 { 1 } else { -1 };
    if btc_lead_return_bps > THRESHOLD_X_BPS {
        xcorr_sign
    } else if btc_lead_return_bps < -THRESHOLD_X_BPS {
        -xcorr_sign
    } else {
        0
    }
}

/// Pearson correlation — 純函數，相同長度兩 slice 算 r ∈ [-1, 1]。
/// 樣本不足或 std=0 → NaN。
pub fn pearson_corr(x: &[f64], y: &[f64]) -> f64 {
    debug_assert_eq!(x.len(), y.len());
    let n = x.len();
    if n < 2 {
        return f64::NAN;
    }
    let nf = n as f64;
    let mean_x = x.iter().sum::<f64>() / nf;
    let mean_y = y.iter().sum::<f64>() / nf;
    let mut cov = 0.0;
    let mut var_x = 0.0;
    let mut var_y = 0.0;
    for i in 0..n {
        let dx = x[i] - mean_x;
        let dy = y[i] - mean_y;
        cov += dx * dy;
        var_x += dx * dx;
        var_y += dy * dy;
    }
    let denom = (var_x * var_y).sqrt();
    if denom <= f64::EPSILON {
        return f64::NAN;
    }
    cov / denom
}

/// PSR(0) — Bailey-López de Prado 2012 skew/kurt-aware formula
/// （spec §7.1 metric (3) + §8.1 +15 bps gate verification 強制公式）。
///
/// 公式：`PSR(0) = Φ((SR - 0) × √(n-1) / √(1 - skew·SR + (kurt-1)/4·SR²))`
/// 其中：
/// - Φ = standard normal CDF
/// - SR = annualized Sharpe ratio
/// - n = sample size
/// - skew + kurt = 經驗 skewness + excess kurtosis
///
/// 樣本不足 / SR NaN / 分母負（denominator 開根號失敗）→ NaN。
///
/// **使用場景**：D+12 paper edge report 階段對 7d sample 算 PSR(0)，threshold
/// ≥ 0.95；本 producer 不直接呼叫此 function（producer 算 raw return + 緩衝
/// metric），留給 downstream evaluator (replay analyzer / paper edge report
/// generator) 用此 function 對 7d sample 算 final PSR(0)。
///
/// 此處放 producer module 是為集中 spec §7.1 強制公式 一處實作（避免 evaluator
/// 端重抄），方便 unit test 對照 MIT C-3 verify report §4 預估值（σ_net=80
/// + ex_kurt=10 → PSR(0) ≈ 0.94）。
pub fn psr_zero(sharpe_ratio: f64, n: usize, skew: f64, excess_kurt: f64) -> f64 {
    if n < 2 || sharpe_ratio.is_nan() || skew.is_nan() || excess_kurt.is_nan() {
        return f64::NAN;
    }
    let nf = (n as f64) - 1.0;
    if nf <= 0.0 {
        return f64::NAN;
    }
    // denom_inner = 1 - skew·SR + (kurt-1)/4·SR²
    // 注意：spec §7.1 公式 kurt 是 excess kurt + 3（normal baseline）；
    // Bailey-López de Prado 2012 用 (kurt-1)/4 是含 normal=3 的 kurt，因此
    // 內部用 excess_kurt + 3 = kurt 後 (kurt - 1) / 4 = (excess_kurt + 2)/4
    let kurt_full = excess_kurt + 3.0;
    let denom_inner = 1.0 - skew * sharpe_ratio + (kurt_full - 1.0) / 4.0 * sharpe_ratio.powi(2);
    if denom_inner <= 0.0 {
        // 分母 = √負數 → 公式失效，返 NaN（caller 視為 fail）
        return f64::NAN;
    }
    let denom = denom_inner.sqrt();
    let z = sharpe_ratio * nf.sqrt() / denom;
    standard_normal_cdf(z)
}

/// Standard normal CDF — Abramowitz & Stegun 7.1.26 approximation。
/// 精度 ≈ 7.5e-8（足夠 PSR(0) 0.95 threshold 判斷）。
fn standard_normal_cdf(z: f64) -> f64 {
    // erf approximation via Abramowitz & Stegun 7.1.26
    // CDF(z) = 0.5 * (1 + erf(z / √2))
    let a1 = 0.254829592_f64;
    let a2 = -0.284496736_f64;
    let a3 = 1.421413741_f64;
    let a4 = -1.453152027_f64;
    let a5 = 1.061405429_f64;
    let p = 0.3275911_f64;
    let sign: f64 = if z < 0.0 { -1.0 } else { 1.0 };
    let x = (z / std::f64::consts::SQRT_2).abs();
    let t = 1.0 / (1.0 + p * x);
    let y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * (-x * x).exp();
    0.5 * (1.0 + sign * y)
}
