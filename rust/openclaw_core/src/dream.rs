//! R02-9: DreamEngine — Idle Monte Carlo Simulation for Parameter Optimization
//! R02-9: DreamEngine — 閒置蒙特卡洛模擬引擎，用於參數優化
//!
//! MODULE_NOTE (English):
//!   DreamEngine runs Monte Carlo what-if simulations during system idle (SPEC S4):
//!   - Randomly sample segments from recent candle data
//!   - Grid search over strategy parameters (SL/TP/confidence_threshold)
//!   - Each parameter value runs >=30 simulations [Q4]
//!   - Confidence via binomial test [Q5]
//!   - Output DreamInsight for CognitiveModulator stoploss tuning
//!   - Reentrancy guard via Arc<Mutex<bool>> [R1-3]
//!
//! MODULE_NOTE (中文):
//!   DreamEngine 在系統閒置時執行蒙特卡洛 what-if 模擬（認知 SPEC S4）：
//!   - 從最近真實 K 線中隨機抽取片段
//!   - 對策略參數（SL/TP/confidence_threshold）進行網格搜索
//!   - 每個參數值跑 >=30 次模擬 [Q4]
//!   - 用 binomial test 計算信心度 [Q5]
//!   - 輸出 DreamInsight 供 CognitiveModulator 調整止損倍率
//!   - 通過 Arc<Mutex<bool>> 實現可重入防護 [R1-3]

use std::collections::HashMap;
use std::sync::{Arc, Mutex};

use rand::prelude::*;
use rand::rngs::StdRng;
use serde::{Deserialize, Serialize};

// ──────────────────────────── Constants / 常量 ────────────────────────────

/// Minimum simulations per parameter value [Q4].
/// 每個參數值的最小模擬次數 [Q4]。
const MIN_SAMPLES_PER_PARAM: usize = 30;

/// Number of grid points per parameter.
/// 每個參數的網格點數。
const PARAM_GRID_SIZE: usize = 10;

/// Maximum cycles per idle period.
/// 每個閒置期間的最大循環數。
const MAX_CYCLES_PER_IDLE: usize = 10_000;

/// Minimum candles required per symbol.
/// 每個品種所需的最小 K 線數量。
const MIN_CANDLES: usize = 25;

/// Minimum segment length for simulation.
/// 模擬的最小片段長度。
const MIN_SEGMENT: usize = 24;

/// Maximum segment length for simulation.
/// 模擬的最大片段長度。
const MAX_SEGMENT: usize = 72;

/// Minimum improvement percentage to report an insight.
/// 報告洞察的最小改善百分比。
const IMPROVEMENT_THRESHOLD_PCT: f64 = 0.5;

/// Minimum confidence to report an insight.
/// 報告洞察的最小信心度。
const CONFIDENCE_THRESHOLD: f64 = 0.4;

/// Minimum samples for binomial test validity.
/// 二項檢驗有效性的最小樣本數。
const MIN_BINOMIAL_SAMPLES: usize = 5;

// ──────────────────────────── Data Types / 數據類型 ────────────────────────────

/// Single candle (OHLCV) data point.
/// 單根 K 線（OHLCV）數據點。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CandleData {
    pub open: f64,
    pub high: f64,
    pub low: f64,
    pub close: f64,
    pub volume: f64,
}

/// Result of Monte Carlo parameter optimization.
/// 蒙特卡洛參數優化結果。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DreamInsight {
    /// Strategy name / 策略名稱
    pub strategy_name: String,
    /// Parameter name / 參數名稱
    pub param_name: String,
    /// Current parameter value / 當前參數值
    pub current_value: f64,
    /// Suggested optimal value / 建議最優值
    pub suggested_value: f64,
    /// Improvement percentage (must exceed 0.5% to be reported)
    /// 改善百分比（必須超過 0.5% 才會報告）
    pub improvement_pct: f64,
    /// Statistical confidence (must exceed 0.4 to be reported)
    /// 統計信心度（必須超過 0.4 才會報告）
    pub confidence: f64,
    /// Number of simulation samples / 模擬樣本數量
    pub sample_count: usize,
}

/// Result of a single dream cycle.
/// 單次夢境循環的結果。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DreamCycleResult {
    /// Number of new insights found / 發現的新洞察數量
    pub insights_found: usize,
    /// Total simulations run in this cycle / 本次循環運行的總模擬數
    pub simulations_run: usize,
    /// Cycles completed / 完成的循環數
    pub cycles_completed: usize,
}

/// Engine status snapshot.
/// 引擎狀態快照。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DreamStatus {
    /// Whether the engine is currently running / 引擎是否正在運行
    pub is_running: bool,
    /// Total dream cycles completed / 完成的總夢境循環數
    pub total_cycles: u64,
    /// Total simulations across all cycles / 所有循環的總模擬數
    pub total_simulations: u64,
    /// Timestamp (ms) of last run / 最後運行時間戳（毫秒）
    pub last_run_ts_ms: u64,
    /// Number of stored insights / 已存儲的洞察數量
    pub insight_count: usize,
}

// ──────────────────────────── Parameter Grid / 參數網格 ────────────────────────────

/// Parameter grid for Monte Carlo search.
/// 蒙特卡洛搜索的參數網格。
struct ParamGrid {
    /// Stoploss percentage grid: 1.0 to 10.0
    /// 止損百分比網格：1.0 到 10.0
    stoploss_pct: Vec<f64>,
    /// Take-profit percentage grid: 3.0 to 20.0
    /// 止盈百分比網格：3.0 到 20.0
    takeprofit_pct: Vec<f64>,
    /// Confidence threshold grid: 0.3 to 0.9
    /// 信心閾值網格：0.3 到 0.9
    confidence_threshold: Vec<f64>,
}

impl ParamGrid {
    /// Build default parameter grid.
    /// 構建默認參數網格。
    fn build() -> Self {
        Self {
            stoploss_pct: linspace(1.0, 10.0, PARAM_GRID_SIZE),
            takeprofit_pct: linspace(3.0, 20.0, PARAM_GRID_SIZE),
            confidence_threshold: linspace(0.3, 0.9, PARAM_GRID_SIZE),
        }
    }

    /// Get the grid for a named parameter, falling back to a range around `current`.
    /// 獲取指定參數的網格，若未知則以 current 為中心生成範圍。
    fn grid_for(&self, param_name: &str, current: f64) -> Vec<f64> {
        match param_name {
            "stoploss_pct" => self.stoploss_pct.clone(),
            "takeprofit_pct" => self.takeprofit_pct.clone(),
            "confidence_threshold" => self.confidence_threshold.clone(),
            _ => {
                let lo = current * 0.5;
                let hi = current * 2.0;
                if hi <= lo {
                    return vec![current];
                }
                linspace(lo, hi, PARAM_GRID_SIZE)
            }
        }
    }
}

/// Generate `n` evenly spaced values from `start` to `end` (inclusive).
/// 生成從 start 到 end（含端點）的 n 個等距值。
fn linspace(start: f64, end: f64, n: usize) -> Vec<f64> {
    if n == 0 {
        return Vec::new();
    }
    if n == 1 {
        return vec![start];
    }
    let step = (end - start) / (n - 1) as f64;
    (0..n).map(|i| start + step * i as f64).collect()
}

// ──────────────────────────── DreamEngine / 夢境引擎 ────────────────────────────

/// Monte Carlo simulation engine for parameter optimization during idle.
/// 閒置期間的蒙特卡洛模擬引擎，用於參數優化。
///
/// Thread-safe via `Arc<Mutex<bool>>` reentrancy guard [R1-3].
/// 通過 `Arc<Mutex<bool>>` 可重入防護確保線程安全 [R1-3]。
pub struct DreamEngine {
    /// Seeded RNG for reproducibility [R1-10].
    /// 可復現的種子隨機數生成器 [R1-10]。
    rng: StdRng,
    /// Reentrancy guard — prevents concurrent run_cycle calls [R1-3].
    /// 可重入防護 — 防止並發 run_cycle 調用 [R1-3]。
    is_running: Arc<Mutex<bool>>,
    /// Accumulated insights keyed by (strategy_name, param_name).
    /// 按 (strategy_name, param_name) 索引的累積洞察。
    insights: Vec<DreamInsight>,
    /// Total completed dream cycles.
    /// 已完成的夢境循環總數。
    total_cycles: u64,
    /// Total individual simulations across all cycles.
    /// 所有循環中的總模擬次數。
    total_simulations: u64,
    /// Timestamp (ms) of last completed run.
    /// 最後完成運行的時間戳（毫秒）。
    last_run_ts_ms: u64,
}

impl DreamEngine {
    /// Create a new DreamEngine with optional seed for reproducibility.
    /// 創建新的 DreamEngine，可選種子用於可復現性。
    pub fn new(seed: Option<u64>) -> Self {
        let rng = match seed {
            Some(s) => StdRng::seed_from_u64(s),
            None => StdRng::from_entropy(),
        };
        Self {
            rng,
            is_running: Arc::new(Mutex::new(false)),
            insights: Vec::new(),
            total_cycles: 0,
            total_simulations: 0,
            last_run_ts_ms: 0,
        }
    }

    /// Run one dream cycle. Returns insights.
    /// 執行一個夢境循環。返回洞察。
    ///
    /// # Arguments / 參數
    /// * `recent_candles` — symbol -> list of OHLCV candles / 品種 -> K 線列表
    /// * `current_params` — optional current parameter values for comparison / 可選的當前參數值用於比較
    ///
    /// # Reentrancy guard [R1-3] / 可重入防護 [R1-3]
    /// If already running, returns a zero result immediately.
    /// 如果已經在運行，立即返回零結果。
    pub fn run_cycle(
        &mut self,
        recent_candles: &HashMap<String, Vec<CandleData>>,
        current_params: Option<&HashMap<String, f64>>,
    ) -> DreamCycleResult {
        // Reentrancy guard: check and set [R1-3]
        // 可重入防護：檢查並設置 [R1-3]
        {
            let mut running = self.is_running.lock().unwrap();
            if *running {
                return DreamCycleResult {
                    insights_found: 0,
                    simulations_run: 0,
                    cycles_completed: 0,
                };
            }
            *running = true;
        } // lock released here / 鎖在此釋放

        let result = self.run_cycle_inner(recent_candles, current_params);

        // Release reentrancy guard / 釋放可重入防護
        {
            let mut running = self.is_running.lock().unwrap();
            *running = false;
        }

        result
    }

    /// Inner cycle logic, called only when reentrancy guard is acquired.
    /// 內部循環邏輯，僅在獲取可重入防護後調用。
    fn run_cycle_inner(
        &mut self,
        recent_candles: &HashMap<String, Vec<CandleData>>,
        current_params: Option<&HashMap<String, f64>>,
    ) -> DreamCycleResult {
        let grid = ParamGrid::build();

        // Default params if none provided / 若未提供則使用默認參數
        let defaults: HashMap<String, f64> = [
            ("stoploss_pct".to_string(), 5.0),
            ("takeprofit_pct".to_string(), 10.0),
        ]
        .into_iter()
        .collect();
        let params = current_params.unwrap_or(&defaults);

        // Filter symbols with enough candles / 過濾有足夠 K 線的品種
        let valid_symbols: Vec<&String> = recent_candles
            .keys()
            .filter(|s| {
                recent_candles
                    .get(*s)
                    .is_some_and(|c| c.len() >= MIN_CANDLES)
            })
            .collect();

        if valid_symbols.is_empty() {
            self.total_cycles += 1;
            self.last_run_ts_ms = current_time_ms();
            return DreamCycleResult {
                insights_found: 0,
                simulations_run: 0,
                cycles_completed: 1,
            };
        }

        let mut sim_count: usize = 0;
        let mut new_insights: Vec<DreamInsight> = Vec::new();

        for (param_name, &current_value) in params.iter() {
            let param_grid = grid.grid_for(param_name, current_value);
            let mut results: HashMap<usize, Vec<f64>> = HashMap::new();

            for (grid_idx, &grid_val) in param_grid.iter().enumerate() {
                let mut pnls: Vec<f64> = Vec::with_capacity(MIN_SAMPLES_PER_PARAM);

                for _ in 0..MIN_SAMPLES_PER_PARAM {
                    if sim_count >= MAX_CYCLES_PER_IDLE {
                        break;
                    }
                    let pnl = self.simulate_single_run(
                        recent_candles,
                        &valid_symbols,
                        param_name,
                        grid_val,
                    );
                    pnls.push(pnl);
                    sim_count += 1;
                }

                results.insert(grid_idx, pnls);

                if sim_count >= MAX_CYCLES_PER_IDLE {
                    break;
                }
            }

            // Evaluate results for this parameter / 評估此參數的結果
            if let Some(insight) = self.evaluate_results(
                "default_strategy",
                param_name,
                current_value,
                &param_grid,
                &results,
            ) {
                new_insights.push(insight);
            }
        }

        let insights_found = new_insights.len();

        // Merge new insights (replace existing for same strategy+param)
        // 合併新洞察（替換相同策略+參數的舊洞察）
        for new_insight in new_insights {
            let pos = self.insights.iter().position(|i| {
                i.strategy_name == new_insight.strategy_name
                    && i.param_name == new_insight.param_name
            });
            match pos {
                Some(idx) => self.insights[idx] = new_insight,
                None => self.insights.push(new_insight),
            }
        }

        self.total_cycles += 1;
        self.total_simulations += sim_count as u64;
        self.last_run_ts_ms = current_time_ms();

        DreamCycleResult {
            insights_found,
            simulations_run: sim_count,
            cycles_completed: 1,
        }
    }

    /// Run one Monte Carlo simulation for a single parameter value.
    /// 為單個參數值執行一次蒙特卡洛模擬。
    ///
    /// Picks a random symbol, random segment, random direction [E6],
    /// then walks bars checking SL/TP triggers.
    /// 隨機選擇品種、隨機片段、隨機方向 [E6]，然後遍歷 K 線檢查 SL/TP 觸發。
    fn simulate_single_run(
        &mut self,
        candles_by_symbol: &HashMap<String, Vec<CandleData>>,
        valid_symbols: &[&String],
        param_name: &str,
        param_value: f64,
    ) -> f64 {
        if valid_symbols.is_empty() {
            return 0.0;
        }

        // Pick random symbol / 隨機選擇品種
        let sym_idx = self.rng.gen_range(0..valid_symbols.len());
        let symbol = valid_symbols[sym_idx];
        let candles = match candles_by_symbol.get(symbol) {
            Some(c) if c.len() >= MIN_CANDLES => c,
            _ => return 0.0,
        };

        // Random segment length / 隨機片段長度
        let max_seg = MAX_SEGMENT.min(candles.len());
        if max_seg < MIN_SEGMENT {
            return 0.0;
        }
        let seg_len = self.rng.gen_range(MIN_SEGMENT..=max_seg);
        let max_start = candles.len().saturating_sub(seg_len);
        let start = if max_start > 0 {
            self.rng.gen_range(0..=max_start)
        } else {
            0
        };
        let segment = &candles[start..start + seg_len];

        let entry = segment[0].close;
        if entry <= 0.0 {
            return 0.0;
        }

        // Determine SL/TP based on param name / 根據參數名稱確定 SL/TP
        let sl_pct = if param_name == "stoploss_pct" {
            param_value
        } else {
            5.0
        };
        let tp_pct = if param_name == "takeprofit_pct" {
            param_value
        } else {
            10.0
        };

        // [E6] Random direction to eliminate K-line color bias
        // [E6] 隨機方向以消除 K 線顏色偏差
        let is_long: bool = self.rng.gen();

        // Walk through bars / 遍歷 K 線
        for bar in &segment[1..] {
            let pnl_high = if is_long {
                (bar.high - entry) / entry * 100.0
            } else {
                (entry - bar.low) / entry * 100.0
            };
            let pnl_low = if is_long {
                (bar.low - entry) / entry * 100.0
            } else {
                (entry - bar.high) / entry * 100.0
            };

            if pnl_high >= tp_pct {
                return tp_pct;
            }
            if pnl_low <= -sl_pct {
                return -sl_pct;
            }
        }

        // No trigger — use final bar close / 未觸發 — 使用最終 K 線收盤價
        let final_close = segment.last().unwrap().close;
        if is_long {
            (final_close - entry) / entry * 100.0
        } else {
            (entry - final_close) / entry * 100.0
        }
    }

    /// Evaluate simulation results and produce an insight if thresholds are met.
    /// 評估模擬結果，若滿足閾值則產生洞察。
    ///
    /// [Q5] Uses binomial test for confidence.
    /// [Q5] 使用二項檢驗計算信心度。
    fn evaluate_results(
        &self,
        strategy_name: &str,
        param_name: &str,
        current_value: f64,
        param_grid: &[f64],
        results: &HashMap<usize, Vec<f64>>,
    ) -> Option<DreamInsight> {
        let mut best_grid_idx: Option<usize> = None;
        let mut best_exp: f64 = f64::NEG_INFINITY;

        // Find grid index closest to current value / 找到最接近當前值的網格索引
        let current_idx = param_grid
            .iter()
            .enumerate()
            .min_by(|(_, a), (_, b)| {
                ((**a) - current_value)
                    .abs()
                    .partial_cmp(&((**b) - current_value).abs())
                    .unwrap_or(std::cmp::Ordering::Equal)
            })
            .map(|(i, _)| i);

        // Find best expectation across grid / 在網格中找到最佳期望值
        for (idx, pnls) in results.iter() {
            if pnls.len() < MIN_SAMPLES_PER_PARAM {
                continue;
            }
            let exp = pnls.iter().sum::<f64>() / pnls.len() as f64;
            if exp > best_exp {
                best_exp = exp;
                best_grid_idx = Some(*idx);
            }
        }

        let best_idx = best_grid_idx?;

        // Current expectation / 當前期望值
        let current_exp = current_idx
            .and_then(|ci| results.get(&ci))
            .filter(|pnls| !pnls.is_empty())
            .map(|pnls| pnls.iter().sum::<f64>() / pnls.len() as f64)
            .unwrap_or(0.0);

        let improvement = best_exp - current_exp;
        if improvement < IMPROVEMENT_THRESHOLD_PCT {
            return None;
        }

        // [Q5] Binomial test confidence / 二項檢驗信心度
        let best_pnls = results.get(&best_idx)?;
        let confidence = binomial_confidence(best_pnls);
        if confidence < CONFIDENCE_THRESHOLD {
            return None;
        }

        let suggested_value = param_grid.get(best_idx).copied().unwrap_or(current_value);

        Some(DreamInsight {
            strategy_name: strategy_name.to_string(),
            param_name: param_name.to_string(),
            current_value,
            suggested_value,
            improvement_pct: improvement,
            confidence,
            sample_count: best_pnls.len(),
        })
    }

    /// Get all current insights.
    /// 獲取所有當前洞察。
    pub fn get_insights(&self) -> &[DreamInsight] {
        &self.insights
    }

    /// Get engine status snapshot.
    /// 獲取引擎狀態快照。
    pub fn get_status(&self) -> DreamStatus {
        DreamStatus {
            is_running: self.is_running(),
            total_cycles: self.total_cycles,
            total_simulations: self.total_simulations,
            last_run_ts_ms: self.last_run_ts_ms,
            insight_count: self.insights.len(),
        }
    }

    /// Check if the engine is currently running.
    /// 檢查引擎是否正在運行。
    pub fn is_running(&self) -> bool {
        *self.is_running.lock().unwrap()
    }
}

// ──────────────────────────── Statistical Functions / 統計函數 ────────────────────────────

/// [Q5] Binomial test: H0 = p(win) = 0.5 (random). Confidence = 1 - p_value (one-tailed).
/// [Q5] 二項檢驗：H0 = p(win) = 0.5（隨機）。信心度 = 1 - p_value（單尾）。
///
/// Uses normal approximation to binomial distribution.
/// 使用正態近似二項分佈。
fn binomial_confidence(results: &[f64]) -> f64 {
    let n = results.len();
    if n < MIN_BINOMIAL_SAMPLES {
        return 0.0;
    }

    let wins = results.iter().filter(|&&r| r > 0.0).count();
    let p_hat = wins as f64 / n as f64;
    if p_hat <= 0.5 {
        return 0.0;
    }

    let z = (p_hat - 0.5) / (0.25_f64 / n as f64).sqrt();
    let p_value = 0.5 * erfc(z / std::f64::consts::SQRT_2);
    (1.0 - p_value).clamp(0.0, 1.0)
}

/// Complementary error function approximation (Abramowitz and Stegun 7.1.26).
/// 互補誤差函數近似（Abramowitz and Stegun 7.1.26）。
///
/// Accurate to ~1.5e-7 for all x >= 0.
/// 對所有 x >= 0 精確到 ~1.5e-7。
fn erfc(x: f64) -> f64 {
    if x < 0.0 {
        return 2.0 - erfc(-x);
    }
    // Abramowitz and Stegun formula 7.1.26
    let t = 1.0 / (1.0 + 0.3275911 * x);
    let poly = t
        * (0.254829592
            + t * (-0.284496736 + t * (1.421413741 + t * (-1.453152027 + t * 1.061405429))));
    poly * (-x * x).exp()
}

/// Get current time in milliseconds (Unix epoch).
/// 獲取當前時間（毫秒，Unix 紀元）。
fn current_time_ms() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0)
}

// ──────────────────────────── Tests / 測試 ────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    /// Build test candle data: simple uptrend for deterministic testing.
    /// 構建測試 K 線數據：簡單上升趨勢用於確定性測試。
    fn make_test_candles(n: usize) -> Vec<CandleData> {
        (0..n)
            .map(|i| {
                let base = 100.0 + i as f64 * 0.5;
                CandleData {
                    open: base,
                    high: base + 2.0,
                    low: base - 1.0,
                    close: base + 0.5,
                    volume: 1000.0,
                }
            })
            .collect()
    }

    /// Build test candle map with one symbol.
    /// 構建包含一個品種的測試 K 線映射。
    fn make_candle_map(n: usize) -> HashMap<String, Vec<CandleData>> {
        let mut map = HashMap::new();
        map.insert("BTCUSDT".to_string(), make_test_candles(n));
        map
    }

    // ──────────────── Test 1: linspace / 等距數列 ────────────────

    #[test]
    fn test_linspace_basic() {
        let v = linspace(1.0, 10.0, 10);
        assert_eq!(v.len(), 10);
        assert!((v[0] - 1.0).abs() < 1e-10);
        assert!((v[9] - 10.0).abs() < 1e-10);
        // Check uniform spacing / 檢查均勻間距
        for i in 1..v.len() {
            assert!((v[i] - v[i - 1] - 1.0).abs() < 1e-10);
        }
    }

    #[test]
    fn test_linspace_edge_cases() {
        assert!(linspace(0.0, 1.0, 0).is_empty());
        let single = linspace(5.0, 10.0, 1);
        assert_eq!(single.len(), 1);
        assert!((single[0] - 5.0).abs() < 1e-10);
    }

    // ──────────────── Test 2: ParamGrid / 參數網格 ────────────────

    #[test]
    fn test_param_grid_build() {
        let grid = ParamGrid::build();
        assert_eq!(grid.stoploss_pct.len(), PARAM_GRID_SIZE);
        assert_eq!(grid.takeprofit_pct.len(), PARAM_GRID_SIZE);
        assert_eq!(grid.confidence_threshold.len(), PARAM_GRID_SIZE);

        assert!((grid.stoploss_pct[0] - 1.0).abs() < 1e-10);
        assert!((grid.stoploss_pct[9] - 10.0).abs() < 1e-10);
        assert!((grid.takeprofit_pct[0] - 3.0).abs() < 1e-10);
        assert!((grid.takeprofit_pct[9] - 20.0).abs() < 1e-10);
    }

    #[test]
    fn test_param_grid_unknown_param() {
        let grid = ParamGrid::build();
        let custom = grid.grid_for("unknown_param", 10.0);
        assert_eq!(custom.len(), PARAM_GRID_SIZE);
        assert!((custom[0] - 5.0).abs() < 1e-10); // 10.0 * 0.5
        assert!((custom[9] - 20.0).abs() < 1e-10); // 10.0 * 2.0
    }

    // ──────────────── Test 3: Simulation / 模擬 ────────────────

    #[test]
    fn test_simulate_single_run_deterministic() {
        let mut engine = DreamEngine::new(Some(42));
        let candles = make_candle_map(100);
        let valid: Vec<&String> = candles.keys().collect();

        let pnl = engine.simulate_single_run(&candles, &valid, "stoploss_pct", 5.0);
        // With seed, result is deterministic / 有種子時結果是確定的
        let pnl2 = {
            let mut e2 = DreamEngine::new(Some(42));
            e2.simulate_single_run(&candles, &valid, "stoploss_pct", 5.0)
        };
        assert!(
            (pnl - pnl2).abs() < 1e-10,
            "Same seed must produce same result / 相同種子必須產生相同結果"
        );
    }

    #[test]
    fn test_simulate_empty_candles() {
        let mut engine = DreamEngine::new(Some(1));
        let empty: HashMap<String, Vec<CandleData>> = HashMap::new();
        let valid: Vec<&String> = Vec::new();
        let pnl = engine.simulate_single_run(&empty, &valid, "stoploss_pct", 5.0);
        assert!((pnl).abs() < 1e-10);
    }

    #[test]
    fn test_simulate_insufficient_candles() {
        let mut engine = DreamEngine::new(Some(1));
        // Only 10 candles — below MIN_CANDLES (25)
        // 僅 10 根 K 線 — 低於 MIN_CANDLES (25)
        let mut candles = HashMap::new();
        candles.insert("BTCUSDT".to_string(), make_test_candles(10));
        let valid: Vec<&String> = candles
            .keys()
            .filter(|s| candles.get(*s).map_or(false, |c| c.len() >= MIN_CANDLES))
            .collect();
        assert!(valid.is_empty());

        // Even if we force it, simulate returns 0 for empty valid list
        // 即使強制傳入，空的有效列表也會返回 0
        let pnl = engine.simulate_single_run(&candles, &valid, "stoploss_pct", 5.0);
        assert!((pnl).abs() < 1e-10);
    }

    // ──────────────── Test 4: Binomial confidence / 二項信心度 ────────────────

    #[test]
    fn test_binomial_confidence_all_wins() {
        let pnls: Vec<f64> = vec![1.0; 30];
        let conf = binomial_confidence(&pnls);
        assert!(
            conf > 0.99,
            "All wins should give very high confidence, got {conf}"
        );
    }

    #[test]
    fn test_binomial_confidence_all_losses() {
        let pnls: Vec<f64> = vec![-1.0; 30];
        let conf = binomial_confidence(&pnls);
        assert!(conf.abs() < 1e-10, "All losses should give zero confidence");
    }

    #[test]
    fn test_binomial_confidence_fifty_fifty() {
        let mut pnls = vec![1.0; 15];
        pnls.extend(vec![-1.0; 15]);
        let conf = binomial_confidence(&pnls);
        assert!(
            conf < CONFIDENCE_THRESHOLD,
            "50/50 should not meet confidence threshold, got {conf}"
        );
    }

    #[test]
    fn test_binomial_confidence_too_few_samples() {
        let pnls = vec![1.0; 3];
        let conf = binomial_confidence(&pnls);
        assert!(conf.abs() < 1e-10, "Too few samples should return 0.0");
    }

    // ──────────────── Test 5: erfc / 互補誤差函數 ────────────────

    #[test]
    fn test_erfc_known_values() {
        // erfc(0) = 1.0
        assert!((erfc(0.0) - 1.0).abs() < 1e-6);
        // erfc(large) ~ 0
        assert!(erfc(5.0) < 1e-10);
        // erfc(-large) ~ 2
        assert!((erfc(-5.0) - 2.0).abs() < 1e-6);
    }

    // ──────────────── Test 6: Reentrancy guard / 可重入防護 ────────────────

    #[test]
    fn test_reentrancy_guard() {
        let engine = DreamEngine::new(Some(99));
        // Manually set is_running to true / 手動設置 is_running 為 true
        {
            let mut running = engine.is_running.lock().unwrap();
            *running = true;
        }
        assert!(engine.is_running());

        // Release it / 釋放
        {
            let mut running = engine.is_running.lock().unwrap();
            *running = false;
        }
        assert!(!engine.is_running());
    }

    #[test]
    fn test_run_cycle_while_running_returns_zero() {
        let mut engine = DreamEngine::new(Some(99));
        // Set running flag / 設置運行標誌
        {
            let mut running = engine.is_running.lock().unwrap();
            *running = true;
        }

        let candles = make_candle_map(100);
        let result = engine.run_cycle(&candles, None);
        assert_eq!(result.insights_found, 0);
        assert_eq!(result.simulations_run, 0);
        assert_eq!(result.cycles_completed, 0);

        // Clean up / 清理
        {
            let mut running = engine.is_running.lock().unwrap();
            *running = false;
        }
    }

    // ──────────────── Test 7: Full cycle / 完整循環 ────────────────

    #[test]
    fn test_run_cycle_basic() {
        let mut engine = DreamEngine::new(Some(42));
        let candles = make_candle_map(100);

        let result = engine.run_cycle(&candles, None);
        assert_eq!(result.cycles_completed, 1);
        assert!(result.simulations_run > 0, "Should run some simulations");

        let status = engine.get_status();
        assert!(!status.is_running);
        assert_eq!(status.total_cycles, 1);
        assert!(status.total_simulations > 0);
        assert!(status.last_run_ts_ms > 0);
    }

    #[test]
    fn test_run_cycle_empty_candles() {
        let mut engine = DreamEngine::new(Some(42));
        let candles: HashMap<String, Vec<CandleData>> = HashMap::new();

        let result = engine.run_cycle(&candles, None);
        assert_eq!(result.cycles_completed, 1);
        assert_eq!(result.simulations_run, 0);
    }

    // ──────────────── Test 8: Insight thresholds / 洞察閾值 ────────────────

    #[test]
    fn test_insight_threshold_filtering() {
        let engine = DreamEngine::new(Some(42));
        let grid = vec![1.0, 2.0, 3.0];

        // All results identical — no improvement / 所有結果相同 — 無改善
        let mut results = HashMap::new();
        results.insert(0, vec![0.5; MIN_SAMPLES_PER_PARAM]);
        results.insert(1, vec![0.5; MIN_SAMPLES_PER_PARAM]);
        results.insert(2, vec![0.5; MIN_SAMPLES_PER_PARAM]);

        let insight = engine.evaluate_results("test_strat", "stoploss_pct", 1.0, &grid, &results);
        assert!(
            insight.is_none(),
            "No improvement should produce no insight"
        );
    }

    #[test]
    fn test_insight_with_clear_winner() {
        let engine = DreamEngine::new(Some(42));
        let grid = vec![1.0, 5.0, 10.0];

        let mut results = HashMap::new();
        // Current (idx 0): mediocre / 當前（索引 0）：平庸
        results.insert(0, vec![0.1; MIN_SAMPLES_PER_PARAM]);
        // Better (idx 1): clear improvement / 更好（索引 1）：明顯改善
        results.insert(1, vec![2.0; MIN_SAMPLES_PER_PARAM]);
        // Worst (idx 2): poor / 最差（索引 2）：差
        results.insert(2, vec![-1.0; MIN_SAMPLES_PER_PARAM]);

        let insight = engine.evaluate_results("test_strat", "stoploss_pct", 1.0, &grid, &results);
        assert!(insight.is_some(), "Clear winner should produce an insight");
        let ins = insight.unwrap();
        assert!((ins.suggested_value - 5.0).abs() < 1e-10);
        assert!(ins.improvement_pct > IMPROVEMENT_THRESHOLD_PCT);
        assert!(ins.confidence > CONFIDENCE_THRESHOLD);
    }

    // ──────────────── Test 9: Multiple cycles accumulate / 多次循環累積 ────────────────

    #[test]
    fn test_multiple_cycles_accumulate() {
        let mut engine = DreamEngine::new(Some(42));
        let candles = make_candle_map(100);

        engine.run_cycle(&candles, None);
        engine.run_cycle(&candles, None);
        engine.run_cycle(&candles, None);

        let status = engine.get_status();
        assert_eq!(status.total_cycles, 3);
        assert!(status.total_simulations > 0);
    }

    // ──────────────── Test 10: Custom params / 自定義參數 ────────────────

    #[test]
    fn test_run_cycle_with_custom_params() {
        let mut engine = DreamEngine::new(Some(42));
        let candles = make_candle_map(100);

        let mut params = HashMap::new();
        params.insert("stoploss_pct".to_string(), 3.0);

        let result = engine.run_cycle(&candles, Some(&params));
        assert_eq!(result.cycles_completed, 1);
        assert!(result.simulations_run > 0);
    }
}
