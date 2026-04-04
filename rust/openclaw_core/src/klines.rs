//! Multi-timeframe K-line (OHLCV) aggregation with Kahan compensated summation.
//! 多時間框架 K 線 (OHLCV) 聚合，使用 Kahan 補償求和。
//!
//! MODULE_NOTE (中文):
//!   KlineManager — 多幣種多時間框架的 K 線聚合器。從原始 tick 數據實時構建
//!   OHLCV 柱狀圖，使用 Kahan 補償求和確保 volume/turnover 的浮點精度。
//!   支持循環緩衝區、間隙檢測、多時間框架同步聚合。
//!
//! MODULE_NOTE (English):
//!   KlineManager — multi-symbol, multi-timeframe K-line aggregator. Builds OHLCV
//!   bars in real-time from raw tick data, using Kahan compensated summation for
//!   volume/turnover floating-point accuracy [V3-QC-2]. Supports circular buffers,
//!   gap detection, and simultaneous multi-timeframe aggregation.
//!
//! Ported from: Python `KlineManager` (~1055 lines, core aggregation subset).
//! 移植自：Python `KlineManager`（約 1055 行，核心聚合子集）。
//!
//! Safety invariant / 安全不變量:
//!   Read-only data aggregation — never places or modifies orders.
//!   僅做只讀數據聚合 — 永不下單或修改訂單。

use serde::{Deserialize, Serialize};
use std::collections::{HashMap, VecDeque};

// ═══════════════════════════════════════════════════════════════════════════════
// Constants / 常量
// ═══════════════════════════════════════════════════════════════════════════════

/// Default timeframes used when none are specified.
/// 未指定時使用的默認時間框架。
pub const DEFAULT_TIMEFRAMES: &[&str] = &["1m", "5m", "15m", "1h", "4h"];

/// Default buffer capacity (number of bars to retain per aggregator).
/// 默認緩衝區容量（每個聚合器保留的 K 線數量）。
pub const DEFAULT_BUFFER_CAPACITY: usize = 500;

// ═══════════════════════════════════════════════════════════════════════════════
// Timeframe helpers / 時間框架工具
// ═══════════════════════════════════════════════════════════════════════════════

/// Convert timeframe string to duration in milliseconds.
/// 將時間框架字串轉換為毫秒級持續時間。
pub fn timeframe_duration_ms(tf: &str) -> Option<u64> {
    match tf {
        "1m" => Some(60_000),
        "5m" => Some(300_000),
        "15m" => Some(900_000),
        "30m" => Some(1_800_000),
        "1h" => Some(3_600_000),
        "4h" => Some(14_400_000),
        "1d" => Some(86_400_000),
        _ => None,
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// KlineBar / 單根 K 線
// ═══════════════════════════════════════════════════════════════════════════════

/// Single OHLCV candle.
/// 單根 OHLCV K 線。
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct KlineBar {
    /// Period open time in epoch milliseconds / 週期開盤時間（毫秒時間戳）
    pub open_time_ms: u64,
    /// Period close time in epoch milliseconds / 週期收盤時間（毫秒時間戳）
    pub close_time_ms: u64,
    /// Opening price / 開盤價
    pub open: f64,
    /// Highest price in period / 週期最高價
    pub high: f64,
    /// Lowest price in period / 週期最低價
    pub low: f64,
    /// Closing (latest) price / 收盤（最新）價
    pub close: f64,
    /// Cumulative volume (Kahan-compensated) / 累計成交量（Kahan 補償）
    pub volume: f64,
    /// Cumulative turnover (Kahan-compensated) / 累計成交額（Kahan 補償）
    pub turnover: f64,
    /// Number of ticks aggregated / 聚合的 tick 數量
    pub tick_count: u32,
    /// Whether this bar's period has ended / 此 K 線的週期是否已結束
    pub is_closed: bool,
}

// ═══════════════════════════════════════════════════════════════════════════════
// OhlcvArrays / OHLCV 陣列
// ═══════════════════════════════════════════════════════════════════════════════

/// Extracted OHLCV arrays for indicator computation.
/// 提取的 OHLCV 陣列，用於指標計算。
#[derive(Debug, Clone)]
pub struct OhlcvArrays {
    pub open: Vec<f64>,
    pub high: Vec<f64>,
    pub low: Vec<f64>,
    pub close: Vec<f64>,
    pub volume: Vec<f64>,
}

// ═══════════════════════════════════════════════════════════════════════════════
// KlineBuffer / K 線循環緩衝區
// ═══════════════════════════════════════════════════════════════════════════════

/// Circular buffer for KlineBars with fixed capacity.
/// 固定容量的 K 線循環緩衝區。
///
/// Oldest bars are evicted when capacity is exceeded, preserving the most
/// recent history. Provides efficient array extraction for indicator engines.
/// 超出容量時淘汰最舊的 K 線，保留最新歷史。提供高效的陣列提取供指標引擎使用。
pub struct KlineBuffer {
    bars: VecDeque<KlineBar>,
    capacity: usize,
}

impl KlineBuffer {
    /// Create a new buffer with the given capacity.
    /// 使用指定容量創建新緩衝區。
    pub fn new(capacity: usize) -> Self {
        Self {
            bars: VecDeque::with_capacity(capacity.min(1024)),
            capacity,
        }
    }

    /// Append a closed bar, evicting the oldest if at capacity.
    /// 追加一根已關閉的 K 線，若已達容量則淘汰最舊的。
    pub fn append(&mut self, bar: KlineBar) {
        if self.bars.len() >= self.capacity {
            self.bars.pop_front();
        }
        self.bars.push_back(bar);
    }

    /// Number of bars currently stored.
    /// 當前存儲的 K 線數量。
    #[inline]
    pub fn len(&self) -> usize {
        self.bars.len()
    }

    /// Whether the buffer is empty.
    /// 緩衝區是否為空。
    #[inline]
    pub fn is_empty(&self) -> bool {
        self.bars.is_empty()
    }

    /// Return a slice of the latest `n` bars (or all if fewer).
    /// 返回最新 `n` 根 K 線的切片（若不足則返回全部）。
    ///
    /// NOTE: VecDeque may not be contiguous, so we call `make_contiguous` first.
    /// 注意：VecDeque 可能不連續，因此先調用 `make_contiguous`。
    pub fn latest(&mut self, n: usize) -> &[KlineBar] {
        let slice = self.bars.make_contiguous();
        let start = slice.len().saturating_sub(n);
        &slice[start..]
    }

    /// Clone the latest `n` bars (immutable, no make_contiguous needed).
    /// 克隆最新 `n` 根 K 線（不可變，無需 make_contiguous）。
    pub fn latest_cloned(&self, n: usize) -> Vec<KlineBar> {
        let len = self.bars.len();
        let skip = len.saturating_sub(n);
        self.bars.iter().skip(skip).cloned().collect()
    }

    /// Extract close prices for the latest `n` bars.
    /// 提取最新 `n` 根 K 線的收盤價。
    pub fn close_array(&self, n: usize) -> Vec<f64> {
        self.extract_field(n, |b| b.close)
    }

    /// Extract high prices for the latest `n` bars.
    /// 提取最新 `n` 根 K 線的最高價。
    pub fn high_array(&self, n: usize) -> Vec<f64> {
        self.extract_field(n, |b| b.high)
    }

    /// Extract low prices for the latest `n` bars.
    /// 提取最新 `n` 根 K 線的最低價。
    pub fn low_array(&self, n: usize) -> Vec<f64> {
        self.extract_field(n, |b| b.low)
    }

    /// Extract open prices for the latest `n` bars.
    /// 提取最新 `n` 根 K 線的開盤價。
    pub fn open_array(&self, n: usize) -> Vec<f64> {
        self.extract_field(n, |b| b.open)
    }

    /// Extract volumes for the latest `n` bars.
    /// 提取最新 `n` 根 K 線的成交量。
    pub fn volume_array(&self, n: usize) -> Vec<f64> {
        self.extract_field(n, |b| b.volume)
    }

    /// Extract all OHLCV arrays at once (single pass).
    /// 一次提取所有 OHLCV 陣列（單次遍歷）。
    pub fn ohlcv_arrays(&self, n: usize) -> OhlcvArrays {
        let count = n.min(self.bars.len());
        let start = self.bars.len().saturating_sub(count);
        let mut open = Vec::with_capacity(count);
        let mut high = Vec::with_capacity(count);
        let mut low = Vec::with_capacity(count);
        let mut close = Vec::with_capacity(count);
        let mut volume = Vec::with_capacity(count);

        for i in start..self.bars.len() {
            let b = &self.bars[i];
            open.push(b.open);
            high.push(b.high);
            low.push(b.low);
            close.push(b.close);
            volume.push(b.volume);
        }

        OhlcvArrays {
            open,
            high,
            low,
            close,
            volume,
        }
    }

    // ── internal ──

    /// Generic field extractor for the latest `n` bars.
    /// 通用欄位提取器，提取最新 `n` 根 K 線的指定欄位。
    fn extract_field(&self, n: usize, f: impl Fn(&KlineBar) -> f64) -> Vec<f64> {
        let count = n.min(self.bars.len());
        let start = self.bars.len().saturating_sub(count);
        (start..self.bars.len())
            .map(|i| f(&self.bars[i]))
            .collect()
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// KlineAggregator / 單時間框架聚合器
// ═══════════════════════════════════════════════════════════════════════════════

/// Single-timeframe aggregator that builds OHLCV bars from ticks.
/// 單時間框架聚合器，從 tick 數據構建 OHLCV K 線。
///
/// Uses **Kahan compensated summation** [V3-QC-2] for volume and turnover
/// to prevent floating-point drift over thousands of tick additions.
/// 使用 **Kahan 補償求和** [V3-QC-2] 累加 volume 和 turnover，
/// 防止數千次 tick 累加時的浮點漂移。
pub struct KlineAggregator {
    /// Timeframe label (e.g. "1m", "5m") / 時間框架標籤
    timeframe: String,
    /// Period duration in milliseconds / 週期持續時間（毫秒）
    duration_ms: u64,
    /// Currently-building bar (None before first tick) / 當前正在構建的 K 線
    current_bar: Option<KlineBar>,
    /// Completed-bar history / 已完成 K 線歷史
    buffer: KlineBuffer,
    /// Kahan compensation term for volume / volume 的 Kahan 補償項
    vol_comp: f64,
    /// Kahan compensation term for turnover / turnover 的 Kahan 補償項
    turn_comp: f64,
    /// Count of detected gap periods (missing data) / 檢測到的間隙週期數
    gap_periods_detected: u64,
}

impl KlineAggregator {
    /// Create a new aggregator for the given timeframe.
    /// 為指定時間框架創建新的聚合器。
    ///
    /// # Panics
    /// Panics if `timeframe` is not a recognized timeframe string.
    /// 若 `timeframe` 不是已知的時間框架字串則 panic。
    pub fn new(timeframe: &str, buffer_capacity: usize) -> Self {
        let duration_ms = timeframe_duration_ms(timeframe)
            .unwrap_or_else(|| panic!("Unknown timeframe: {timeframe}"));
        Self {
            timeframe: timeframe.to_owned(),
            duration_ms,
            current_bar: None,
            buffer: KlineBuffer::new(buffer_capacity),
            vol_comp: 0.0,
            turn_comp: 0.0,
            gap_periods_detected: 0,
        }
    }

    /// Process a single tick. Returns the closed bar if the tick triggered a period roll.
    /// 處理單個 tick。若 tick 觸發了週期滾動，則返回已關閉的 K 線。
    pub fn on_tick(
        &mut self,
        price: f64,
        ts_ms: u64,
        volume: f64,
        turnover: f64,
    ) -> Option<KlineBar> {
        let period_start = self.align_to_period(ts_ms);

        match &mut self.current_bar {
            Some(bar) if bar.open_time_ms == period_start => {
                // Same period — update OHLC / 同一週期 — 更新 OHLC
                if price > bar.high {
                    bar.high = price;
                }
                if price < bar.low {
                    bar.low = price;
                }
                bar.close = price;
                // Kahan compensated summation (inlined to satisfy borrow checker)
                // Kahan 補償求和（內聯以滿足借用檢查器）
                let vy = volume - self.vol_comp;
                let vt = bar.volume + vy;
                self.vol_comp = (vt - bar.volume) - vy;
                bar.volume = vt;
                let ty = turnover - self.turn_comp;
                let tt = bar.turnover + ty;
                self.turn_comp = (tt - bar.turnover) - ty;
                bar.turnover = tt;
                bar.tick_count += 1;
                None
            }
            Some(_) => {
                // New period — close current bar, start new one
                // 新週期 — 關閉當前 K 線，開始新的
                let bar = self.current_bar.as_ref().unwrap();
                let mut closed = bar.clone();
                closed.is_closed = true;

                // Detect gaps (skipped periods) / 檢測間隙（跳過的週期）
                let expected_next = closed.close_time_ms;
                if period_start > expected_next + self.duration_ms {
                    self.gap_periods_detected +=
                        (period_start - expected_next) / self.duration_ms;
                }

                self.buffer.append(closed.clone());
                self.start_new_bar(price, period_start, volume, turnover);
                Some(closed)
            }
            None => {
                // First tick ever — start new bar / 首個 tick — 開始新 K 線
                self.start_new_bar(price, period_start, volume, turnover);
                None
            }
        }
    }

    /// Align a timestamp to its period boundary.
    /// 將時間戳對齊到其週期邊界。
    #[inline]
    fn align_to_period(&self, ts_ms: u64) -> u64 {
        (ts_ms / self.duration_ms) * self.duration_ms
    }

    /// Start a new bar at the given period boundary.
    /// 在指定的週期邊界開始新的 K 線。
    fn start_new_bar(&mut self, price: f64, period_start: u64, volume: f64, turnover: f64) {
        self.vol_comp = 0.0;
        self.turn_comp = 0.0;
        self.current_bar = Some(KlineBar {
            open_time_ms: period_start,
            close_time_ms: period_start + self.duration_ms,
            open: price,
            high: price,
            low: price,
            close: price,
            volume,
            turnover,
            tick_count: 1,
            is_closed: false,
        });
    }

    /// Reference to the currently-building bar, if any.
    /// 當前正在構建的 K 線的引用（若有）。
    #[inline]
    pub fn get_current_bar(&self) -> Option<&KlineBar> {
        self.current_bar.as_ref()
    }

    /// Total gap periods detected since creation.
    /// 自創建以來檢測到的總間隙週期數。
    #[inline]
    pub fn gap_count(&self) -> u64 {
        self.gap_periods_detected
    }

    /// Reference to the completed-bar buffer.
    /// 已完成 K 線緩衝區的引用。
    #[inline]
    pub fn buffer(&self) -> &KlineBuffer {
        &self.buffer
    }

    /// Mutable reference to the completed-bar buffer.
    /// 已完成 K 線緩衝區的可變引用。
    #[inline]
    pub fn buffer_mut(&mut self) -> &mut KlineBuffer {
        &mut self.buffer
    }

    /// Timeframe label (e.g. "1m").
    /// 時間框架標籤（如 "1m"）。
    #[inline]
    pub fn timeframe(&self) -> &str {
        &self.timeframe
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// KlineStats / K 線統計
// ═══════════════════════════════════════════════════════════════════════════════

/// Aggregate statistics across all symbols and timeframes.
/// 所有幣種和時間框架的聚合統計。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KlineStats {
    /// Number of tracked symbols / 追蹤的幣種數量
    pub total_symbols: usize,
    /// Number of timeframes per symbol / 每個幣種的時間框架數量
    pub total_timeframes: usize,
    /// Total completed bars across all buffers / 所有緩衝區中已完成的 K 線總數
    pub total_bars: usize,
    /// Total gap periods detected / 檢測到的總間隙週期數
    pub total_gaps: u64,
}

// ═══════════════════════════════════════════════════════════════════════════════
// KlineManager / 多幣種多時間框架 K 線管理器
// ═══════════════════════════════════════════════════════════════════════════════

/// Multi-symbol, multi-timeframe K-line manager.
/// 多幣種多時間框架 K 線管理器。
///
/// Manages a matrix of `KlineAggregator` instances (symbol x timeframe).
/// Each incoming tick is fanned out to all timeframes for the symbol.
/// 管理一個 `KlineAggregator` 實例矩陣（幣種 x 時間框架）。
/// 每個傳入的 tick 會扇出到該幣種的所有時間框架。
pub struct KlineManager {
    /// symbol -> timeframe -> aggregator / 幣種 -> 時間框架 -> 聚合器
    aggregators: HashMap<String, HashMap<String, KlineAggregator>>,
    /// Ordered list of tracked symbols / 追蹤的幣種有序列表
    symbols: Vec<String>,
    /// Ordered list of timeframes / 時間框架有序列表
    timeframes: Vec<String>,
    /// Buffer capacity for new aggregators / 新聚合器的緩衝區容量
    buffer_capacity: usize,
}

impl KlineManager {
    /// Create a new KlineManager with the given symbols and optional config.
    /// 使用指定幣種和可選配置創建新的 KlineManager。
    pub fn new(
        symbols: &[&str],
        timeframes: Option<&[&str]>,
        buffer_capacity: Option<usize>,
    ) -> Self {
        let tfs: Vec<String> = timeframes
            .unwrap_or(DEFAULT_TIMEFRAMES)
            .iter()
            .map(|s| (*s).to_owned())
            .collect();
        let cap = buffer_capacity.unwrap_or(DEFAULT_BUFFER_CAPACITY);

        let mut aggregators = HashMap::new();
        let mut syms = Vec::new();

        for &sym in symbols {
            let s = sym.to_owned();
            let mut tf_map = HashMap::new();
            for tf in &tfs {
                tf_map.insert(tf.clone(), KlineAggregator::new(tf, cap));
            }
            aggregators.insert(s.clone(), tf_map);
            syms.push(s);
        }

        Self {
            aggregators,
            symbols: syms,
            timeframes: tfs,
            buffer_capacity: cap,
        }
    }

    /// Process a tick for a symbol across all timeframes.
    /// 處理一個幣種在所有時間框架上的 tick。
    ///
    /// Returns a vec of `(timeframe, closed_bar)` for any completed bars.
    /// 返回所有已完成 K 線的 `(timeframe, closed_bar)` 向量。
    pub fn on_tick(
        &mut self,
        symbol: &str,
        price: f64,
        ts_ms: u64,
        volume: f64,
        turnover: f64,
    ) -> Vec<(String, KlineBar)> {
        let tf_map = match self.aggregators.get_mut(symbol) {
            Some(m) => m,
            None => return Vec::new(),
        };

        let mut closed = Vec::new();
        for (tf, agg) in tf_map.iter_mut() {
            if let Some(bar) = agg.on_tick(price, ts_ms, volume, turnover) {
                closed.push((tf.clone(), bar));
            }
        }
        closed
    }

    /// Add a new symbol (creates aggregators for all timeframes).
    /// 添加新幣種（為所有時間框架創建聚合器）。
    pub fn add_symbol(&mut self, symbol: &str) {
        if self.aggregators.contains_key(symbol) {
            return;
        }
        let mut tf_map = HashMap::new();
        for tf in &self.timeframes {
            tf_map.insert(tf.clone(), KlineAggregator::new(tf, self.buffer_capacity));
        }
        self.aggregators.insert(symbol.to_owned(), tf_map);
        self.symbols.push(symbol.to_owned());
    }

    /// Remove a symbol and all its aggregators.
    /// 移除一個幣種及其所有聚合器。
    pub fn remove_symbol(&mut self, symbol: &str) {
        self.aggregators.remove(symbol);
        self.symbols.retain(|s| s != symbol);
    }

    /// Get the completed-bar buffer for a symbol + timeframe.
    /// 獲取指定幣種+時間框架的已完成 K 線緩衝區。
    pub fn get_buffer(&self, symbol: &str, timeframe: &str) -> Option<&KlineBuffer> {
        self.aggregators
            .get(symbol)
            .and_then(|m| m.get(timeframe))
            .map(|a| a.buffer())
    }

    /// Get the currently-building bar for a symbol + timeframe.
    /// 獲取指定幣種+時間框架當前正在構建的 K 線。
    pub fn get_current_bar(&self, symbol: &str, timeframe: &str) -> Option<&KlineBar> {
        self.aggregators
            .get(symbol)
            .and_then(|m| m.get(timeframe))
            .and_then(|a| a.get_current_bar())
    }

    /// Get OHLCV arrays for a symbol + timeframe (latest `n` bars).
    /// 獲取指定幣種+時間框架的 OHLCV 陣列（最新 `n` 根）。
    pub fn get_ohlcv(
        &self,
        symbol: &str,
        timeframe: &str,
        n: Option<usize>,
    ) -> Option<OhlcvArrays> {
        self.aggregators
            .get(symbol)
            .and_then(|m| m.get(timeframe))
            .map(|a| a.buffer().ohlcv_arrays(n.unwrap_or(DEFAULT_BUFFER_CAPACITY)))
    }

    /// Aggregate statistics across all symbols and timeframes.
    /// 所有幣種和時間框架的聚合統計。
    pub fn get_stats(&self) -> KlineStats {
        let mut total_bars = 0usize;
        let mut total_gaps = 0u64;
        for tf_map in self.aggregators.values() {
            for agg in tf_map.values() {
                total_bars += agg.buffer().len();
                total_gaps += agg.gap_count();
            }
        }
        KlineStats {
            total_symbols: self.symbols.len(),
            total_timeframes: self.timeframes.len(),
            total_bars,
            total_gaps,
        }
    }

    /// Ordered list of tracked symbols.
    /// 追蹤的幣種有序列表。
    #[inline]
    pub fn symbols(&self) -> &[String] {
        &self.symbols
    }

    /// Ordered list of timeframes.
    /// 時間框架有序列表。
    #[inline]
    pub fn timeframes(&self) -> &[String] {
        &self.timeframes
    }

    /// Seed historical bars into the buffer (REST bootstrap, eliminates cold start).
    /// 將歷史 K 線注入緩衝區（REST 引導，消除冷啟動）。
    ///
    /// Bars MUST be sorted oldest-first (ascending open_time_ms).
    /// Only bars with `is_closed == true` are appended.
    /// Returns the number of bars actually seeded.
    ///
    /// 傳入的 K 線必須按 open_time_ms 升序排列（最舊在前）。
    /// 僅追加 `is_closed == true` 的 K 線。返回實際注入的數量。
    pub fn seed_bars(&mut self, symbol: &str, timeframe: &str, bars: Vec<KlineBar>) -> usize {
        let agg = match self
            .aggregators
            .get_mut(symbol)
            .and_then(|m| m.get_mut(timeframe))
        {
            Some(a) => a,
            None => return 0,
        };

        let mut count = 0usize;
        for bar in bars {
            if bar.is_closed {
                agg.buffer_mut().append(bar);
                count += 1;
            }
        }
        count
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Tests / 測試
// ═══════════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    // ── helpers ──

    /// Base timestamp for tests: 2024-01-01 00:00:00 UTC.
    const BASE_TS: u64 = 1_704_067_200_000;

    fn make_aggregator(tf: &str) -> KlineAggregator {
        KlineAggregator::new(tf, DEFAULT_BUFFER_CAPACITY)
    }

    // ── 1. Period alignment ──

    #[test]
    fn test_period_alignment_1m() {
        let agg = make_aggregator("1m");
        // 30 seconds into a minute -> aligns to minute start
        assert_eq!(agg.align_to_period(BASE_TS + 30_000), BASE_TS);
        // Exactly on boundary -> stays
        assert_eq!(agg.align_to_period(BASE_TS), BASE_TS);
        // 59.999s -> still same minute
        assert_eq!(agg.align_to_period(BASE_TS + 59_999), BASE_TS);
        // 60s -> next minute
        assert_eq!(agg.align_to_period(BASE_TS + 60_000), BASE_TS + 60_000);
    }

    #[test]
    fn test_period_alignment_5m() {
        let agg = make_aggregator("5m");
        // 2 minutes in -> aligns to 5m boundary
        assert_eq!(agg.align_to_period(BASE_TS + 120_000), BASE_TS);
        assert_eq!(agg.align_to_period(BASE_TS + 300_000), BASE_TS + 300_000);
    }

    // ── 2. First tick creates bar but does not close anything ──

    #[test]
    fn test_first_tick_no_close() {
        let mut agg = make_aggregator("1m");
        let result = agg.on_tick(100.0, BASE_TS + 5_000, 1.0, 100.0);
        assert!(result.is_none());
        let bar = agg.get_current_bar().unwrap();
        assert_eq!(bar.open, 100.0);
        assert_eq!(bar.high, 100.0);
        assert_eq!(bar.low, 100.0);
        assert_eq!(bar.close, 100.0);
        assert_eq!(bar.tick_count, 1);
        assert!(!bar.is_closed);
    }

    // ── 3. Same-period ticks update OHLC correctly ──

    #[test]
    fn test_same_period_ohlc_update() {
        let mut agg = make_aggregator("1m");
        agg.on_tick(100.0, BASE_TS + 1_000, 1.0, 100.0);
        agg.on_tick(105.0, BASE_TS + 2_000, 2.0, 210.0); // new high
        agg.on_tick(95.0, BASE_TS + 3_000, 3.0, 285.0); // new low
        agg.on_tick(102.0, BASE_TS + 4_000, 0.5, 51.0); // close update

        let bar = agg.get_current_bar().unwrap();
        assert_eq!(bar.open, 100.0);
        assert_eq!(bar.high, 105.0);
        assert_eq!(bar.low, 95.0);
        assert_eq!(bar.close, 102.0);
        assert_eq!(bar.tick_count, 4);
        assert!(!bar.is_closed);
    }

    // ── 4. Bar closing on period roll ──

    #[test]
    fn test_bar_close_on_new_period() {
        let mut agg = make_aggregator("1m");
        agg.on_tick(100.0, BASE_TS + 1_000, 1.0, 100.0);
        agg.on_tick(110.0, BASE_TS + 30_000, 2.0, 220.0);

        // Tick in the next minute triggers close
        let closed = agg.on_tick(105.0, BASE_TS + 61_000, 0.5, 52.5);
        assert!(closed.is_some());
        let closed = closed.unwrap();
        assert!(closed.is_closed);
        assert_eq!(closed.open, 100.0);
        assert_eq!(closed.high, 110.0);
        assert_eq!(closed.close, 110.0);
        assert_eq!(closed.tick_count, 2);
        assert_eq!(closed.open_time_ms, BASE_TS);
        assert_eq!(closed.close_time_ms, BASE_TS + 60_000);

        // Buffer should have one bar
        assert_eq!(agg.buffer().len(), 1);

        // New current bar should exist
        let cur = agg.get_current_bar().unwrap();
        assert_eq!(cur.open, 105.0);
        assert_eq!(cur.open_time_ms, BASE_TS + 60_000);
    }

    // ── 5. Gap detection ──

    #[test]
    fn test_gap_detection() {
        let mut agg = make_aggregator("1m");
        agg.on_tick(100.0, BASE_TS + 1_000, 1.0, 100.0);
        // Skip 5 minutes ahead (5 gap periods for 1m)
        let closed = agg.on_tick(200.0, BASE_TS + 360_000, 1.0, 200.0);
        assert!(closed.is_some());
        // gap = (360_000 - 60_000) / 60_000 = 5 periods
        assert_eq!(agg.gap_count(), 5);
    }

    #[test]
    fn test_no_gap_consecutive_periods() {
        let mut agg = make_aggregator("1m");
        agg.on_tick(100.0, BASE_TS, 1.0, 100.0);
        // Immediately next period — no gap
        agg.on_tick(101.0, BASE_TS + 60_000, 1.0, 101.0);
        assert_eq!(agg.gap_count(), 0);
    }

    // ── 6. Buffer capacity eviction ──

    #[test]
    fn test_buffer_capacity_eviction() {
        let mut buf = KlineBuffer::new(3);
        for i in 0..5u64 {
            buf.append(KlineBar {
                open_time_ms: i * 60_000,
                close_time_ms: (i + 1) * 60_000,
                open: i as f64,
                high: i as f64,
                low: i as f64,
                close: i as f64,
                volume: 1.0,
                turnover: 1.0,
                tick_count: 1,
                is_closed: true,
            });
        }
        assert_eq!(buf.len(), 3);
        // Oldest bars (0, 1) were evicted; remaining are (2, 3, 4)
        let closes = buf.close_array(3);
        assert_eq!(closes, vec![2.0, 3.0, 4.0]);
    }

    // ── 7. Array extraction (close, high, low, open, volume) ──

    #[test]
    fn test_array_extraction() {
        let mut buf = KlineBuffer::new(10);
        for i in 0..5u64 {
            buf.append(KlineBar {
                open_time_ms: i * 60_000,
                close_time_ms: (i + 1) * 60_000,
                open: (i + 1) as f64,
                high: (i + 10) as f64,
                low: i as f64 * 0.5,
                close: (i + 2) as f64,
                volume: (i + 1) as f64 * 10.0,
                turnover: 0.0,
                tick_count: 1,
                is_closed: true,
            });
        }
        // Request last 3
        assert_eq!(buf.close_array(3), vec![4.0, 5.0, 6.0]);
        assert_eq!(buf.high_array(3), vec![12.0, 13.0, 14.0]);
        assert_eq!(buf.low_array(3), vec![1.0, 1.5, 2.0]);
        assert_eq!(buf.open_array(3), vec![3.0, 4.0, 5.0]);
        assert_eq!(buf.volume_array(3), vec![30.0, 40.0, 50.0]);
    }

    // ── 8. OhlcvArrays single-pass extraction ──

    #[test]
    fn test_ohlcv_arrays() {
        let mut buf = KlineBuffer::new(10);
        for i in 0..3u64 {
            buf.append(KlineBar {
                open_time_ms: i * 60_000,
                close_time_ms: (i + 1) * 60_000,
                open: (i + 1) as f64,
                high: (i + 10) as f64,
                low: i as f64,
                close: (i + 2) as f64,
                volume: 1.0,
                turnover: 0.0,
                tick_count: 1,
                is_closed: true,
            });
        }
        let arrays = buf.ohlcv_arrays(10);
        assert_eq!(arrays.open, vec![1.0, 2.0, 3.0]);
        assert_eq!(arrays.high, vec![10.0, 11.0, 12.0]);
        assert_eq!(arrays.low, vec![0.0, 1.0, 2.0]);
        assert_eq!(arrays.close, vec![2.0, 3.0, 4.0]);
        assert_eq!(arrays.volume, vec![1.0, 1.0, 1.0]);
    }

    // ── 9. Kahan compensated summation accuracy ──

    #[test]
    fn test_kahan_volume_accuracy() {
        // Summing many small values where naive summation would lose precision.
        // 累加大量小值，樸素求和會損失精度。
        let mut agg = make_aggregator("1m");
        let n = 10_000u32;
        let small = 0.1_f64; // not exactly representable in f64

        for i in 0..n {
            agg.on_tick(100.0, BASE_TS + i as u64, small, small);
        }

        let bar = agg.get_current_bar().unwrap();
        let expected = small * n as f64; // 1000.0
        // Kahan should keep the error extremely small (< 1e-10)
        let error = (bar.volume - expected).abs();
        assert!(
            error < 1e-10,
            "Kahan volume error too large: {error} (got {}, expected {expected})",
            bar.volume
        );
        let turn_error = (bar.turnover - expected).abs();
        assert!(
            turn_error < 1e-10,
            "Kahan turnover error too large: {turn_error}"
        );
    }

    // ── 10. Multi-timeframe via KlineManager ──

    #[test]
    fn test_manager_multi_timeframe() {
        let mut mgr = KlineManager::new(&["BTCUSDT"], Some(&["1m", "5m"]), Some(100));

        // Feed ticks spanning 6 minutes -> should close 6 x 1m bars and 1 x 5m bar
        for min in 0..7u64 {
            let ts = BASE_TS + min * 60_000 + 1_000;
            mgr.on_tick("BTCUSDT", 100.0 + min as f64, ts, 1.0, 100.0);
        }

        let buf_1m = mgr.get_buffer("BTCUSDT", "1m").unwrap();
        assert_eq!(buf_1m.len(), 6); // 6 closed 1m bars

        let buf_5m = mgr.get_buffer("BTCUSDT", "5m").unwrap();
        assert_eq!(buf_5m.len(), 1); // 1 closed 5m bar
    }

    // ── 11. KlineManager add/remove symbol ──

    #[test]
    fn test_manager_add_remove_symbol() {
        let mut mgr = KlineManager::new(&["BTCUSDT"], Some(&["1m"]), Some(50));
        assert_eq!(mgr.symbols().len(), 1);

        mgr.add_symbol("ETHUSDT");
        assert_eq!(mgr.symbols().len(), 2);

        // Adding duplicate is no-op
        mgr.add_symbol("ETHUSDT");
        assert_eq!(mgr.symbols().len(), 2);

        mgr.remove_symbol("BTCUSDT");
        assert_eq!(mgr.symbols().len(), 1);
        assert_eq!(mgr.symbols()[0], "ETHUSDT");

        // Ticks to removed symbol are silently ignored
        let closed = mgr.on_tick("BTCUSDT", 100.0, BASE_TS, 1.0, 100.0);
        assert!(closed.is_empty());
    }

    // ── 12. KlineManager get_stats ──

    #[test]
    fn test_manager_stats() {
        let mut mgr =
            KlineManager::new(&["BTCUSDT", "ETHUSDT"], Some(&["1m", "5m"]), Some(100));

        // Feed 3 minutes of data for both symbols
        for min in 0..4u64 {
            let ts = BASE_TS + min * 60_000 + 500;
            mgr.on_tick("BTCUSDT", 100.0, ts, 1.0, 100.0);
            mgr.on_tick("ETHUSDT", 50.0, ts, 2.0, 100.0);
        }

        let stats = mgr.get_stats();
        assert_eq!(stats.total_symbols, 2);
        assert_eq!(stats.total_timeframes, 2);
        // 3 closed 1m bars per symbol = 6, no closed 5m bars yet
        assert_eq!(stats.total_bars, 6);
        assert_eq!(stats.total_gaps, 0);
    }

    // ── 13. get_current_bar and get_ohlcv via manager ──

    #[test]
    fn test_manager_get_current_bar_and_ohlcv() {
        let mut mgr = KlineManager::new(&["BTCUSDT"], Some(&["1m"]), Some(100));
        mgr.on_tick("BTCUSDT", 100.0, BASE_TS + 1_000, 1.0, 100.0);

        let cur = mgr.get_current_bar("BTCUSDT", "1m").unwrap();
        assert_eq!(cur.open, 100.0);
        assert!(!cur.is_closed);

        // No completed bars yet -> empty ohlcv
        let ohlcv = mgr.get_ohlcv("BTCUSDT", "1m", Some(10)).unwrap();
        assert!(ohlcv.close.is_empty());

        // Unknown symbol -> None
        assert!(mgr.get_current_bar("UNKNOWN", "1m").is_none());
        assert!(mgr.get_ohlcv("UNKNOWN", "1m", None).is_none());
    }

    // ── 14. Timeframe duration lookup ──

    #[test]
    fn test_timeframe_duration_ms() {
        assert_eq!(timeframe_duration_ms("1m"), Some(60_000));
        assert_eq!(timeframe_duration_ms("5m"), Some(300_000));
        assert_eq!(timeframe_duration_ms("15m"), Some(900_000));
        assert_eq!(timeframe_duration_ms("30m"), Some(1_800_000));
        assert_eq!(timeframe_duration_ms("1h"), Some(3_600_000));
        assert_eq!(timeframe_duration_ms("4h"), Some(14_400_000));
        assert_eq!(timeframe_duration_ms("1d"), Some(86_400_000));
        assert_eq!(timeframe_duration_ms("2h"), None);
        assert_eq!(timeframe_duration_ms(""), None);
    }

    // ── 15. Buffer latest() slice ──

    #[test]
    fn test_buffer_latest_slice() {
        let mut buf = KlineBuffer::new(10);
        for i in 0..5u64 {
            buf.append(KlineBar {
                open_time_ms: i * 60_000,
                close_time_ms: (i + 1) * 60_000,
                open: i as f64,
                high: i as f64,
                low: i as f64,
                close: i as f64,
                volume: 1.0,
                turnover: 0.0,
                tick_count: 1,
                is_closed: true,
            });
        }
        let last3 = buf.latest(3);
        assert_eq!(last3.len(), 3);
        assert_eq!(last3[0].close, 2.0);
        assert_eq!(last3[2].close, 4.0);

        // Request more than available -> returns all
        let all = buf.latest(100);
        assert_eq!(all.len(), 5);
    }

    // ── 16. Default timeframes applied by manager ──

    #[test]
    fn test_manager_default_timeframes() {
        let mgr = KlineManager::new(&["BTCUSDT"], None, None);
        let expected: Vec<String> = DEFAULT_TIMEFRAMES.iter().map(|s| s.to_string()).collect();
        // Sort both since HashMap iteration order is non-deterministic
        let mut actual = mgr.timeframes().to_vec();
        actual.sort();
        let mut exp = expected;
        exp.sort();
        assert_eq!(actual, exp);
    }

    // ── 17. seed_bars — REST bootstrap ──

    #[test]
    fn test_seed_bars_basic() {
        let mut mgr = KlineManager::new(&["BTCUSDT"], Some(&["1m"]), Some(500));

        // Create 5 closed bars (oldest-first)
        let bars: Vec<KlineBar> = (0..5u64)
            .map(|i| KlineBar {
                open_time_ms: BASE_TS + i * 60_000,
                close_time_ms: BASE_TS + (i + 1) * 60_000,
                open: 100.0 + i as f64,
                high: 105.0 + i as f64,
                low: 95.0 + i as f64,
                close: 102.0 + i as f64,
                volume: 10.0,
                turnover: 1000.0,
                tick_count: 1,
                is_closed: true,
            })
            .collect();

        let count = mgr.seed_bars("BTCUSDT", "1m", bars);
        assert_eq!(count, 5);

        let buf = mgr.get_buffer("BTCUSDT", "1m").unwrap();
        assert_eq!(buf.len(), 5);
        let closes = buf.close_array(5);
        assert_eq!(closes, vec![102.0, 103.0, 104.0, 105.0, 106.0]);
    }

    #[test]
    fn test_seed_bars_filters_unclosed() {
        let mut mgr = KlineManager::new(&["ETHUSDT"], Some(&["1m"]), Some(500));

        let bars = vec![
            KlineBar {
                open_time_ms: BASE_TS,
                close_time_ms: BASE_TS + 60_000,
                open: 100.0, high: 110.0, low: 90.0, close: 105.0,
                volume: 10.0, turnover: 1000.0, tick_count: 1,
                is_closed: true,
            },
            KlineBar {
                open_time_ms: BASE_TS + 60_000,
                close_time_ms: BASE_TS + 120_000,
                open: 105.0, high: 115.0, low: 95.0, close: 110.0,
                volume: 20.0, turnover: 2000.0, tick_count: 1,
                is_closed: false, // unclosed — should be filtered
            },
        ];

        let count = mgr.seed_bars("ETHUSDT", "1m", bars);
        assert_eq!(count, 1);
        assert_eq!(mgr.get_buffer("ETHUSDT", "1m").unwrap().len(), 1);
    }

    #[test]
    fn test_seed_bars_unknown_symbol_returns_zero() {
        let mut mgr = KlineManager::new(&["BTCUSDT"], Some(&["1m"]), Some(500));
        let count = mgr.seed_bars("UNKNOWN", "1m", vec![]);
        assert_eq!(count, 0);
    }

    #[test]
    fn test_seed_bars_unknown_timeframe_returns_zero() {
        let mut mgr = KlineManager::new(&["BTCUSDT"], Some(&["1m"]), Some(500));
        let count = mgr.seed_bars("BTCUSDT", "15m", vec![]);
        assert_eq!(count, 0);
    }
}
