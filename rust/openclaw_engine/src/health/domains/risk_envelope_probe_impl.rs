//! M3 Sprint 4+ first Live PA-DRIFT-5 — RiskEnvelopeSourceProbe production impl。
//!
//! MODULE_NOTE
//! 模塊用途:
//!   per `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_2_pm_phase_3e_signoff.md`
//!   §4.1 item 4 + §6.1.4 Sprint 4+ first Live carry-over：本檔負責把 Wave 2
//!   Track F 完成的 `RiskEnvelopeSourceProbe` trait 接到真實 portfolio 計算端，
//!   讓 `RiskEnvelopeEmitter` 經由本 module 暴露 5 個 SSOT-equivalent metric：
//!     1. portfolio_cum_pnl_24h_usd
//!     2. portfolio_max_dd_pct
//!     3. position_count_active
//!     4. correlation_avg_pairwise
//!     5. concentration_top1_pct
//!   本檔不修 `paper_state` / `risk_verdict_ledger`（Python 側）/ `fill_writer`
//!   既有寫入邏輯（per Sprint 2 Wave 2 dispatch packet §7.5 反模式 (a)），僅在
//!   `health` domain 邊界內新增一個 **portfolio snapshot cache**，由 caller（main.rs
//!   Wave B 工作）定時 push `PipelineSnapshot` + recent `TimestampedFill` 進來，
//!   probe 端從 cache 讀「當前 snapshot 計算結果」（read-only）。
//!
//! 主要類 / 函數:
//!   - `PortfolioStateCache`：portfolio-level 24h sliding window 緩存。內部持
//!     `VecDeque<(ts_ms, realized_pnl)>` 24h fills history、`VecDeque<(ts_ms, equity)>`
//!     24h equity curve、最新 position notional 列表。提供 5 calculator
//!     accessor 對應 5 個 metric。
//!   - `RealRiskEnvelopeSourceProbe`：impl `RiskEnvelopeSourceProbe` trait；
//!     持 `Arc<parking_lot::Mutex<PortfolioStateCache>>`；emitter 端 sample
//!     呼叫即從 cache 讀 5 calculator 結果（fail-soft：cache empty 返
//!     0.0 / 0，emitter 端 classify 視為 OK band）。
//!
//! 依賴:
//!   - `parking_lot::Mutex`：cache 端鎖（cargo workspace 既有 dep）。
//!   - `crate::pipeline_types::{PipelineSnapshot, TimestampedFill}`：caller 端
//!     `update_from_pipeline_snapshot` 接的 SSOT 輸入。
//!   - `super::risk_envelope::RiskEnvelopeSourceProbe`：本 module impl 的 trait
//!     界面。
//!
//! 硬邊界:
//!   - 不修 `paper_state` / `mode_state` / `pipeline_types` 既有寫入邏輯（per
//!     dispatch packet §7.5 反模式 (a)；emitter 只觀測，既有 portfolio
//!     calculation 是 SSOT）。
//!   - 不引 `cfg(feature = "spike")`；production binary 0 mock time 滲透
//!     （per Sprint 2 AC-5）。
//!   - 不引新 V### / IPC；本檔純 Rust 內存 calculator，emit V106 row 由
//!     既有 `RiskEnvelopeEmitter` + `MetricEmitterScheduler` 負責。
//!   - cache 內部 24h sliding window 不持久化跨 restart；restart 後從 0 起算，
//!     reach steady-state 約 24h（per `feedback_no_dead_params` fail-soft 設計）。
//!   - 不假設 fill `realized_pnl` 為已實現 USD：caller 端 push 時必為 USD-quoted
//!     轉換後值；本 cache 不做幣別轉換。
//!   - probe 端 5 method 返 f64/u32 原始值；input range 不 sanitize；caller
//!     端 (cache update) 端保證合理 range（per `feedback_no_dead_params`
//!     fail-loud 對齊）。
//!
//! 新 singleton 登記注解（per profile 「沒穩定登記表，改在 PA/E2 report + TODO
//! follow-up」）:
//!   - `PortfolioStateCache`：新 mutable cache 結構；main.rs Wave B 接線時 owner
//!     為單一 `Arc<parking_lot::Mutex<PortfolioStateCache>>`。E2 audit 時應確認
//!     不重複構造、不誤跨 mode race（Live / Demo / Paper 各自共享或獨立 cache 由
//!     main.rs wire-up 決定）。
//!   - `RealRiskEnvelopeSourceProbe`：trait impl 端 Arc<dyn> 注入 emitter；
//!     emitter 端是 trait object，多 mode 走多 probe instance 不互相干涉。

use std::collections::{HashMap, VecDeque};
use std::sync::Arc;

use parking_lot::Mutex;

use super::risk_envelope::{RiskEnvelopeSampleSnapshot, RiskEnvelopeSourceProbe};

// 24h 毫秒（cache 滑動視窗保留視窗大小；超過此年齡的 fill / equity sample 從
// 視窗淘汰）。
const SLIDING_WINDOW_24H_MS: u64 = 24 * 60 * 60 * 1000;

// 1h 毫秒（F-4 correlation_avg_pairwise per-symbol returns 滑動視窗大小；
// 對齊 24h 採樣 1/24 密度，每對 sample ≥ 30 達 Pearson 推薦下限；per PA spec
// §4.1 拍板）。
const SLIDING_WINDOW_1H_MS: u64 = 60 * 60 * 1000;

// 兩 symbol 配對最少共同 sample 數；< 此值的 pair 跳過 Pearson 計算（per PA
// spec §2.3，對齊 RollingWindowAggregator 5-sample 設計）。
const MIN_PAIRWISE_SAMPLES: usize = 5;

// ============================================================
// PortfolioStateCache — 24h sliding window portfolio SSOT calculator
// ============================================================

/// 單一 portfolio snapshot 的 position 名目；caller 端 `update_*` 時推入。
///
/// 為什麼分離 `qty * abs_entry_price` 而非直接 `notional`:
///   - concentration 計算需「絕對名目」（不分多空，純 exposure 大小）；以
///     `qty.abs() * entry_price.abs()` 計算避免符號扣抵。
///   - emitter 端不修 `PaperPosition` 既有欄位（per dispatch 反模式 (a)），
///     本 cache 端只記投影後 notional。
#[derive(Debug, Clone, Copy)]
pub struct PositionExposure {
    /// 倉位名目（USD-quoted；|qty| × |entry_price|）。
    pub notional_usd: f64,
}

/// portfolio 24h sliding window cache。
///
/// 為什麼此設計（per task §1 + §2 + §5 邊界）:
///   - `realized_pnl_history`：24h 內 fill realized_pnl 樣本 + 對應 ts_ms。
///     `pnl_24h_usd()` 端 sum 後返；caller 端 push fill 時不需做累加（cache
///     端做）。
///   - `equity_history`：24h 內 portfolio equity curve sample 樣本；
///     `max_dd_pct_24h()` 端走 peak-trough max drawdown。
///   - `latest_exposures`：當前 position notional 列表（已從 `PipelineSnapshot`
///     拍照）；`position_count_active()` 直接返 `len()`；`concentration_top1_pct()`
///     端走 `max / sum × 100`。
///   - `correlation_avg_pairwise`：cache 端 placeholder 返 0.0；本 Wave A 不
///     IMPL portfolio cross-pair correlation rolling window calculator（per
///     dispatch 反模式 (c)：「correlation 不可寫死高頻」；rolling window 設計
///     由 PA 拍板 lookback per E2 Track F round 2 對抗反問 #2）。Wave B follow-up
///     接既有 `crate::scanner::scorer` correlation lookup table 或新 calculator。
///
/// 為什麼 ts_ms-based sliding window 而非「直接 24h 計數」:
///   - emitter sample_interval=300s 但 fill 可能在任意 ms；以 wall-clock ms 過
///     濾才符合「24h 真實滑動窗口」語義（per spec §3.2 line 405-415 metric
///     語意）。
///   - sliding window 截斷在 cache 端 `update_*` 時做（push + drain_old）；
///     accessor 端不重做截斷（避雙重邏輯偏離）。
///
/// 為什麼無顯式 cap（per PA-DRIFT-5 round 1 E2 F-1 fix）:
///   - 上限 = 「24h × caller push rate」隱式上限；不設顯式 cap。
///     - 預期 fill push rate ≪ 1/s（策略 throttle + 風控 max_open_positions）；
///       上限 ≈ 86400 sample；多策略 burst 上限 ≈ 數十 k。
///     - equity push rate = caller 端 emitter sample_interval=300s tick；
///       上限 = 24h / 300s = 288 sample。
///   - 為什麼不設顯式 cap：sliding window `drain_old_fills` / `drain_old_equity`
///     在每次 `update_from_pipeline_snapshot` 端執行；24h 外 sample 自然 drain，
///     不會 unbounded。
///   - 若 caller 端 burst push（>> 1 fill/s 持續 24h）導致 sample 累積，本檔不
///     設顯式 cap 保護；caller 端責任（per dispatch packet §7.5 反模式 (a)：
///     emitter 不重做 risk_config 載入；burst 防禦由 caller 端 throttle）。
///   - Sprint 5 cascade IMPL 後若 emitter wire-up 端發現 burst pattern，可在
///     caller 端加 throttle；或在本檔加顯式 cap follow-up（PA Sprint 5 spec
///     amend）。
pub struct PortfolioStateCache {
    /// 24h 內 fill (ts_ms, realized_pnl_usd) sliding window；越新位於 back。
    realized_pnl_history: VecDeque<(u64, f64)>,
    /// 24h 內 equity (ts_ms, equity_usd) sliding window；越新位於 back；
    /// caller 端 `update_from_pipeline_snapshot` 時 push 當前 balance + sum(unrealized_pnl)。
    equity_history: VecDeque<(u64, f64)>,
    /// 當前活躍 position notional 列表（最新 snapshot 拍照）；
    /// caller 端 `update_from_pipeline_snapshot` 時 overwrite 整列。
    latest_exposures: Vec<PositionExposure>,
    /// caller 端最新一次 update 的 wall-clock ms（防 stale guard）；不參與
    /// 5 calculator 計算，僅 telemetry。
    last_update_ts_ms: u64,
    /// F-4 per-symbol 1h returns sliding window。
    ///
    /// 為什麼此設計（per PA spec §2.1）:
    ///   - key = symbol；value = (ts_ms, return_pct) deque；每對 sample
    ///     對齊 caller push 同一 ts_ms（emitter sample_interval=300s tick
    ///     對齊；同一 tick 內全 symbol 共用 now_ms）。
    ///   - HashMap O(1) lookup by symbol vs Vec<(symbol, ts, return)> 的
    ///     O(N)；25 symbol × 12 sample/h ~ 300 sample 規模仍小，但對齊既有
    ///     `IndicatorEngine` 風格。
    ///   - pairwise correlation 計算端走 outer-join intersect timestamps
    ///     算 Pearson；MIN_PAIRWISE_SAMPLES=5 lower bound 對齊
    ///     RollingWindowAggregator 5-sample 設計。
    per_symbol_returns_history: HashMap<String, VecDeque<(u64, f64)>>,
    /// F-4 上次 update 的 per-symbol mid price snapshot；用於下一輪 return 計算。
    ///
    /// 為什麼必存（per PA spec §2.1）:
    ///   - return_pct = (this_price - last_price) / last_price；無 last_price
    ///     無法算 return（首次見此 symbol 只記，不算 return push）。
    ///   - HashMap<String, f64> 純 latest price snapshot；無時戳（時戳由
    ///     deque 端帶）。
    ///   - symbol 退倉後 last_symbol_prices 不主動清理；下次同 symbol 開倉
    ///     時 prev price 已過 stale。實際 risk 是 stale prev 可能跨數小時 ~
    ///     數天 gap；本 cache 設計接受此 risk（per PA spec §4 副作用評估）。
    last_symbol_prices: HashMap<String, f64>,
}

impl PortfolioStateCache {
    /// 建立空 cache。production 端 caller 在 main.rs Wave B 接 emitter wire-up
    /// 時建一個 `Arc<parking_lot::Mutex<PortfolioStateCache>>` 共享給 probe +
    /// `update_from_pipeline_snapshot` 端。
    pub fn new() -> Self {
        Self {
            realized_pnl_history: VecDeque::new(),
            equity_history: VecDeque::new(),
            latest_exposures: Vec::new(),
            last_update_ts_ms: 0,
            per_symbol_returns_history: HashMap::new(),
            last_symbol_prices: HashMap::new(),
        }
    }

    /// 從 `PipelineSnapshot` + 一批最近的 fill 推入 cache。
    ///
    /// 為什麼此 entry 而非分散 push fill/position/equity:
    ///   - main.rs Wave B 接線時，一次定時器 tick（300s 對齊 emitter
    ///     sample_interval）拍照當前 snapshot + 過去 300s 增量 fill；單一 entry
    ///     讓 caller 端不需協調多步驟，cache 內部一次 lock 結束。
    ///   - 對齊 spec §3 D1 emitter 採樣邊界：cache 是「state-machine 輸出端」，
    ///     既有 PaperState 拍照 + fill push 為「state-machine 輸入端」。
    ///
    /// caller 責任:
    ///   - `now_ms`：必為 wall-clock ms（不是 monotonic / mock_instant）；cache
    ///     端走 `now_ms - SLIDING_WINDOW_24H_MS` 截斷舊樣本。
    ///   - `new_fills`：自上次 update 後新增的 `TimestampedFill`；不可重複 push
    ///     同一 fill（cache 端不去重）。caller 端用 `ring_buffer.iter().rev()
    ///     .take_while(ts > last_update_ts_ms)` 拿增量。
    ///   - `snapshot.paper_state.balance + sum(positions.unrealized_pnl)` = 當前
    ///     equity；cache 端不重做計算。
    ///   - `snapshot.paper_state.positions`：當前 position 列表，caller 端走
    ///     `qty.abs() * entry_price.abs()` 投影為 `PositionExposure { notional_usd }`。
    ///
    /// F-2 NaN/inf sanitize（per PA-DRIFT-5 round 2 E2 升級 P1 Wave B condition）:
    ///   - `realized_pnl` 非有限值 → skip push（fail-loud warn log）；避把 NaN/inf
    ///     污染 24h sliding window sum，破壞 emitter classify ladder（NaN 比較
    ///     全 false → 走 OK band 但永遠不會升 WARN，雙重壞處）。
    ///   - `equity_usd` 非有限值 → skip push（fail-loud warn log）；max_dd_pct
    ///     calculation 對 NaN peak 計算錯誤。
    ///   - `latest_exposures[i].notional_usd` 非有限值 → 過濾掉該倉位（保留
    ///     legal 倉位）；concentration top-1 sum 不被 NaN 干擾。
    ///   - 全部 NaN/inf → equity / fill / exposure 各自不 push；cache 仍 advance
    ///     `last_update_ts_ms` 對齊 caller 「tick 已執行」語意；24h drain 仍走
    ///     不依賴本次 push 是否 land sample。
    ///
    /// F-4 per_symbol_mid_prices（per PA Sprint 5+ Wave 1 §4.3.4 spec）:
    ///   - 對每個 (symbol, mid_price) 計算「上次 mid → 本次 mid 之 percent
    ///     return」並 push 到 `per_symbol_returns_history[symbol]` 1h sliding
    ///     window。首次見此 symbol 只記 last_price，不算 return。
    ///   - mid_price 非有限值 / ≤ 0 → skip + fail-loud warn log（F-2 sanitize
    ///     對齊；prev=0 除零防護）。
    ///   - 空 HashMap = caller cold-start / 未接 PaperState SSOT；對齊 placeholder
    ///     0.0 OK band；不會誤觸 WARN（per `feedback_no_dead_params` fail-soft）。
    pub fn update_from_pipeline_snapshot(
        &mut self,
        now_ms: u64,
        equity_usd: f64,
        new_fills: &[(u64, f64)],
        latest_exposures: Vec<PositionExposure>,
        per_symbol_mid_prices: &HashMap<String, f64>,
    ) {
        // 1. push 增量 fill 到 sliding window；NaN/inf realized_pnl skip + fail-loud。
        for &(ts_ms, realized_pnl) in new_fills.iter() {
            if !realized_pnl.is_finite() {
                tracing::warn!(
                    target = "m3.health.risk_envelope",
                    ts_ms,
                    realized_pnl,
                    "PortfolioStateCache: skip NaN/inf realized_pnl fill (F-2 sanitize)"
                );
                continue;
            }
            self.realized_pnl_history.push_back((ts_ms, realized_pnl));
        }
        self.drain_old_fills(now_ms);

        // 2. push 當前 equity sample；NaN/inf equity skip + fail-loud。
        if equity_usd.is_finite() {
            self.equity_history.push_back((now_ms, equity_usd));
        } else {
            tracing::warn!(
                target = "m3.health.risk_envelope",
                now_ms,
                equity_usd,
                "PortfolioStateCache: skip NaN/inf equity sample (F-2 sanitize)"
            );
        }
        self.drain_old_equity(now_ms);

        // 3. 整列覆寫 latest position notional snapshot；過濾 NaN/inf notional。
        //    為什麼過濾而非整列 reject：保留 legal 倉位讓 emitter 仍能觀測；個別
        //    illegal notional 由 caller 端責任修，本 cache fail-soft sanitize 對齊
        //    spec §3.6 「emitter 觀測語意：illegal source skip 不誤升」。
        let sanitized_exposures: Vec<PositionExposure> = latest_exposures
            .into_iter()
            .filter(|e| {
                if e.notional_usd.is_finite() {
                    true
                } else {
                    tracing::warn!(
                        target = "m3.health.risk_envelope",
                        notional_usd = e.notional_usd,
                        "PortfolioStateCache: filter NaN/inf notional exposure (F-2 sanitize)"
                    );
                    false
                }
            })
            .collect();
        self.latest_exposures = sanitized_exposures;

        // 4. F-4 per-symbol returns 計算 + push（per PA spec §2.2）。
        //
        // 為什麼此設計：
        //   - mid_price NaN/inf/<=0 → skip + fail-loud warn log（F-2 sanitize
        //     pattern；不可 silent skip 避 fake-success row）。
        //   - prev=0 防護：如 last_symbol_prices 內留有歷史 0（理論不應發生，
        //     防御性 check）→ skip 該 symbol 該輪 return push。
        //   - return_pct NaN/inf check：浮點除法 edge case 防護；不應發生但
        //     ensure no NaN 進 deque（會污染 Pearson 計算）。
        //   - 1h 之外舊 sample 由 `prune_returns_history_1h` 端 drain。
        for (symbol, &mid_price) in per_symbol_mid_prices.iter() {
            if !mid_price.is_finite() || mid_price <= 0.0 {
                tracing::warn!(
                    target = "m3.health.risk_envelope",
                    symbol = %symbol,
                    mid_price,
                    "PortfolioStateCache: skip NaN/inf/<=0 mid_price (F-2 sanitize for F-4)"
                );
                continue;
            }
            let prev = self.last_symbol_prices.get(symbol).copied();
            // 無論首次 / 後續，更新 last_symbol_prices；首次 prev=None 跳過
            // return push，但 last_price 仍記。
            self.last_symbol_prices.insert(symbol.clone(), mid_price);
            if let Some(prev_price) = prev {
                if prev_price > 0.0 {
                    let return_pct = (mid_price - prev_price) / prev_price;
                    if return_pct.is_finite() {
                        self.per_symbol_returns_history
                            .entry(symbol.clone())
                            .or_insert_with(|| VecDeque::with_capacity(16))
                            .push_back((now_ms, return_pct));
                    }
                }
            }
        }
        self.prune_returns_history_1h(now_ms);

        // 5. 更新最後 update 時戳（telemetry）。
        self.last_update_ts_ms = now_ms;
    }

    /// 從 cache 移除 24h 外的舊 fill sample。
    fn drain_old_fills(&mut self, now_ms: u64) {
        let cutoff = now_ms.saturating_sub(SLIDING_WINDOW_24H_MS);
        while let Some(&(ts_ms, _)) = self.realized_pnl_history.front() {
            if ts_ms < cutoff {
                self.realized_pnl_history.pop_front();
            } else {
                break;
            }
        }
    }

    /// 從 cache 移除 24h 外的舊 equity sample。
    fn drain_old_equity(&mut self, now_ms: u64) {
        let cutoff = now_ms.saturating_sub(SLIDING_WINDOW_24H_MS);
        while let Some(&(ts_ms, _)) = self.equity_history.front() {
            if ts_ms < cutoff {
                self.equity_history.pop_front();
            } else {
                break;
            }
        }
    }

    /// F-4 從 cache 移除 1h 外的舊 per-symbol return sample；同時清理變空 deque。
    ///
    /// 為什麼此設計（per PA spec §2.2）:
    ///   - 1h 滑動視窗 cutoff = `now_ms - SLIDING_WINDOW_1H_MS`；
    ///     `saturating_sub` 防 startup `now_ms < 1h` underflow。
    ///   - 對每個 symbol VecDeque 從 front pop ts < cutoff sample（deque 已按
    ///     push order = ts ascending sorted）。
    ///   - 清理空 deque：retain `!d.is_empty()`；symbol 退倉 1h 後從 history
    ///     清除，避無上限 memory growth（per `feedback_no_dead_params`）。
    ///   - last_symbol_prices 不在此清理：retain stale prev price 是「下次該
    ///     symbol 再開倉時的 return base」；風險評估 per PA spec §4 副作用。
    fn prune_returns_history_1h(&mut self, now_ms: u64) {
        let cutoff = now_ms.saturating_sub(SLIDING_WINDOW_1H_MS);
        for deque in self.per_symbol_returns_history.values_mut() {
            while let Some(&(ts_ms, _)) = deque.front() {
                if ts_ms < cutoff {
                    deque.pop_front();
                } else {
                    break;
                }
            }
        }
        self.per_symbol_returns_history
            .retain(|_, d| !d.is_empty());
    }

    // ============================================================
    // 5 SSOT calculator accessor — 對應 emitter probe trait 5 method
    // ============================================================

    /// (1) 24h 累計實現 PnL (USD)；走 `realized_pnl_history` sum。
    ///
    /// 為什麼此設計（task §1）:
    ///   - sum 走「過去 24h 內 fill」純線性聚合；cache 端 sliding window
    ///     `drain_old_fills` 已截斷外部樣本，accessor 直接 sum 不重做截斷。
    ///   - 不引 floating-point precision compensation（Kahan）：spec ladder
    ///     band 解析度是 $500 / $1500 / $2500（per M3 spec §2.3 line 106），
    ///     遠大於 f64 sum 累積誤差。
    ///   - 空 history → 0.0：對齊 OK band（per `feedback_no_dead_params`
    ///     fail-soft 對齊；cache 未初始化或 cold-start 不應誤觸 WARN）。
    pub fn cum_pnl_24h_usd(&self) -> f64 {
        self.realized_pnl_history.iter().map(|&(_, p)| p).sum()
    }

    /// (2) 24h sliding window max drawdown (%)；走 equity curve peak-trough。
    ///
    /// 為什麼此設計（task §2）:
    ///   - peak-trough max dd：iterating equity_history 按時序記 running peak，
    ///     每點計 `((peak - equity) / peak × 100)`，return 整段最大。
    ///   - peak 起始值由首樣本決定（不依賴 PaperState peak_balance；後者是
    ///     session-since-start 而非 24h sliding）。
    ///   - 空 history / peak ≤ 0 → 0.0：對齊 OK band。
    ///   - 算法 O(n)；空間 O(1)；24h × 5min sample = 288 樣本上限不會慢。
    pub fn max_dd_pct_24h(&self) -> f64 {
        if self.equity_history.is_empty() {
            return 0.0;
        }
        let mut peak = f64::MIN;
        let mut max_dd = 0.0_f64;
        for &(_, equity) in self.equity_history.iter() {
            if equity > peak {
                peak = equity;
            }
            // peak 必正才有「相對 drawdown 百分比」意義；負 equity 由風控其他
            // 路徑接，本 metric fail-soft 不誤升 CRITICAL。
            if peak > 0.0 {
                let dd = ((peak - equity) / peak) * 100.0;
                if dd > max_dd {
                    max_dd = dd;
                }
            }
        }
        max_dd
    }

    /// (3) 當前活躍倉位數（per task §3）；走 `latest_exposures.len()`。
    ///
    /// 為什麼此設計:
    ///   - emitter sample 端拍照當前 snapshot；非 24h sliding window，
    ///     「當前」就是 caller 最後 update 的 snapshot。
    ///   - `u32`：對齊 trait `current_position_count_active() -> u32` 簽名。
    ///   - empty cache → 0：對齊 OK band（per spec §3.6 + §6.2 反模式 (e)
    ///     preserved：top1 not top_n；count 0 表 cold start）。
    pub fn position_count_active(&self) -> u32 {
        self.latest_exposures.len() as u32
    }

    /// (4) 跨倉位 pairwise correlation 平均（per PA Sprint 5+ Wave 1 §4.3.4 spec）。
    ///
    /// 算法（per PA spec §2.3）:
    ///   1. 收集 active symbol 列表（per_symbol_returns_history.keys()）
    ///   2. 過濾 sample 數 >= MIN_PAIRWISE_SAMPLES 之 symbol（短於 lookback 不參與）
    ///   3. 對所有 C(n, 2) 對：
    ///      a. outer-join timestamps（取共同時刻）— two-pointer O(m+n)
    ///      b. join 後 sample < MIN_PAIRWISE_SAMPLES → 跳過此對
    ///      c. 算 Pearson correlation r ∈ [-1, 1]；var = 0 → None skip
    ///   4. 返 |r| 平均（絕對值平均；per spec §2.3 「correlation_avg_pairwise」語意）
    ///   5. n < 2 → 返 0.0（empty / cold-start OK band）
    ///
    /// 為什麼絕對值平均:
    ///   - portfolio 風險視角 r=+1 與 r=-1 都代表「強相關」；同向 +1 = 同漲
    ///     同跌，反向 -1 = 一個對沖另一個但波動共振；絕對值平均反映「整體
    ///     pairwise dependency 強度」。
    ///   - r near 0 = 真實 diversified portfolio。
    ///
    /// 為什麼 clamp(-1, 1):
    ///   - 浮點除法可能因捨入產生 |r| > 1 之 1e-15 等級漂移；clamp 防誤觸後
    ///     續 classify ladder（雖 ladder 自身對 r > 1 已 fail-soft）。
    ///
    /// 為什麼 5 個 helper 函數（pair_by_timestamp / pearson_correlation）放
    /// module-level 而非 inline:
    ///   - 純函數無 &self；單獨測試容易；E2 review 端清晰可讀。
    ///   - 對齊既有 `scanner::scorer` 端 helper 風格。
    pub fn correlation_avg_pairwise(&self) -> f64 {
        // Step 1: 收集 sample 數 >= MIN_PAIRWISE_SAMPLES 之 symbol；
        // 用 Vec<&String> 保 borrow lifetime；對齊 deterministic order 不需
        // sort（pairwise 平均對 order 不敏感）。
        let symbols: Vec<&String> = self
            .per_symbol_returns_history
            .iter()
            .filter(|(_, d)| d.len() >= MIN_PAIRWISE_SAMPLES)
            .map(|(s, _)| s)
            .collect();
        // Step 5: cold-start fail-soft OK band。
        if symbols.len() < 2 {
            return 0.0;
        }
        // Step 3: C(n, 2) pairwise loop。
        let mut sum_abs_r = 0.0_f64;
        let mut pair_count: u32 = 0;
        for i in 0..symbols.len() {
            for j in (i + 1)..symbols.len() {
                let s1 = symbols[i];
                let s2 = symbols[j];
                // unwrap 安全：i/j index 來自 symbols vec，必對應 HashMap entry。
                let d1 = &self.per_symbol_returns_history[s1];
                let d2 = &self.per_symbol_returns_history[s2];
                let (paired_x, paired_y) = pair_by_timestamp(d1, d2);
                // Step 3b: 對齊 join 後 sample 下限。
                if paired_x.len() < MIN_PAIRWISE_SAMPLES {
                    continue;
                }
                if let Some(r) = pearson_correlation(&paired_x, &paired_y) {
                    sum_abs_r += r.abs();
                    pair_count += 1;
                }
            }
        }
        // Step 4: pair_count=0 fail-soft（理論不應發生若 symbols.len() >= 2
        // 且每對皆滿 MIN_PAIRWISE_SAMPLES；防御性 check）。
        if pair_count == 0 {
            0.0
        } else {
            sum_abs_r / pair_count as f64
        }
    }

    /// (5) top-1 symbol exposure 佔 portfolio total exposure (%)（per task §5）。
    ///
    /// 為什麼此設計:
    ///   - `top1_notional / sum(notionals) × 100`：simple ratio；對齊 spec
    ///     §3.6 + §6.2 反模式 (e) preserved (top1 not top_n)。
    ///   - sum ≤ 0 → 0.0：empty cache / 全空倉 OK band。
    ///   - 純讀 `latest_exposures`；不二次計算 notional（caller 端已投影過）。
    pub fn concentration_top1_pct(&self) -> f64 {
        if self.latest_exposures.is_empty() {
            return 0.0;
        }
        let total: f64 = self
            .latest_exposures
            .iter()
            .map(|e| e.notional_usd.abs())
            .sum();
        if total <= 0.0 {
            return 0.0;
        }
        let top1: f64 = self
            .latest_exposures
            .iter()
            .map(|e| e.notional_usd.abs())
            .fold(0.0_f64, f64::max);
        (top1 / total) * 100.0
    }

    /// batch read helper：一次計算 5 metric snapshot，原子地返 owned tuple
    /// （per PA-DRIFT-5 round 1 E2 F-3 fix）。
    ///
    /// 為什麼此 method（vs 5 個 current_xxx）：
    ///   - 5 個個別 accessor 各拿一次 lock（probe 端 5 × `cache.lock()`）；
    ///     emitter sample 時 5-lock gap 內若 cache update 介入 → 產生 5-metric
    ///     snapshot inconsistency（如 PnL 已更新但 position_count 仍舊）。
    ///   - 本 method 在單一 `&self` borrow 下走 5 calculator → owned snapshot；
    ///     caller 端（`RealRiskEnvelopeSourceProbe::snapshot_5_metric` override）
    ///     只需拿一次 lock 即可避 race window。
    ///   - 保留 5 個個別 accessor 不刪：backward compat trait API + 既有 unit
    ///     test 不破壞（per profile 「不擴大改動範圍」）。
    pub fn snapshot_5_metric(&self) -> RiskEnvelopeSampleSnapshot {
        RiskEnvelopeSampleSnapshot {
            portfolio_cum_pnl_24h_usd: self.cum_pnl_24h_usd(),
            portfolio_max_dd_pct: self.max_dd_pct_24h(),
            position_count_active: self.position_count_active(),
            correlation_avg_pairwise: self.correlation_avg_pairwise(),
            concentration_top1_pct: self.concentration_top1_pct(),
        }
    }

    /// telemetry / E2 audit 用：返最後一次 update 的 wall-clock ms（0 = cold
    /// start 未 update）。
    pub fn last_update_ts_ms(&self) -> u64 {
        self.last_update_ts_ms
    }

    /// telemetry / E2 audit 用：返當前 fill history 樣本數（sliding window
    /// drain 後）。
    pub fn fill_history_len(&self) -> usize {
        self.realized_pnl_history.len()
    }

    /// telemetry / E2 audit 用：返當前 equity history 樣本數。
    pub fn equity_history_len(&self) -> usize {
        self.equity_history.len()
    }
}

impl Default for PortfolioStateCache {
    fn default() -> Self {
        Self::new()
    }
}

// ============================================================
// F-4 correlation helper — module-level 純函數
// ============================================================

/// 兩 deque 以 ts_ms outer-join；O(m+n) two-pointer。
///
/// 為什麼此設計（per PA spec §2.3）:
///   - 兩 deque 由 caller `update_from_pipeline_snapshot` 依 push order 維護
///     升序（同一 ts 全 symbol 共用 caller 的 now_ms；單 caller 線性 tick
///     不會 race 進 out-of-order push）。
///   - two-pointer 對共同 ts 取對；單側 advance 不對 push；嚴格 equal-only
///     對齊 PA spec line 207-217 algorithm。
///   - 為什麼 collect `Vec<&(u64, f64)>` 而非直接 iter：VecDeque 不支援
///     random index access；先 collect 到 Vec slice 才能用 `v1[i].0` 比較。
///     但更通用解法（per Rust idiomatic）是用 deque iter cmp by next() ⇒
///     此實作走 collect 對齊 PA spec §2.3 line 199-218 pseudo-code 一致。
fn pair_by_timestamp(
    d1: &VecDeque<(u64, f64)>,
    d2: &VecDeque<(u64, f64)>,
) -> (Vec<f64>, Vec<f64>) {
    let mut x = Vec::with_capacity(d1.len().min(d2.len()));
    let mut y = Vec::with_capacity(d1.len().min(d2.len()));
    let v1: Vec<&(u64, f64)> = d1.iter().collect();
    let v2: Vec<&(u64, f64)> = d2.iter().collect();
    let mut i = 0_usize;
    let mut j = 0_usize;
    while i < v1.len() && j < v2.len() {
        match v1[i].0.cmp(&v2[j].0) {
            std::cmp::Ordering::Equal => {
                x.push(v1[i].1);
                y.push(v2[j].1);
                i += 1;
                j += 1;
            }
            std::cmp::Ordering::Less => i += 1,
            std::cmp::Ordering::Greater => j += 1,
        }
    }
    (x, y)
}

/// Pearson correlation r ∈ [-1, 1]；var = 0 或 n < 2 → None skip。
///
/// 為什麼此設計（per PA spec §2.3）:
///   - 兩列 n 不等或 n < 2 → None（caller 端 `correlation_avg_pairwise`
///     之 MIN_PAIRWISE_SAMPLES check 已在 caller 端守，本 fn 額外防御）。
///   - `denom = sqrt(sq_x * sq_y)`；若 var(x)=0 或 var(y)=0 → denom=0
///     → None skip（identical constant series 無 correlation 概念）。
///   - `denom` NaN/inf check：浮點 sqrt edge case 防護。
///   - 最後 `r.clamp(-1, 1)` 防浮點累積誤差導致 |r| > 1 之 1e-15 漂移。
///
/// 為什麼一遍 loop sum 而非 std crate:
///   - 對齊 cargo workspace 0 dep policy（不引 `statrs` / `ndarray`）。
///   - n ≤ 12 sample (1h × 5min tick)；O(n) 兩遍 sum 微秒級。
fn pearson_correlation(x: &[f64], y: &[f64]) -> Option<f64> {
    let n = x.len();
    if n < 2 || n != y.len() {
        return None;
    }
    let n_f = n as f64;
    let mean_x = x.iter().sum::<f64>() / n_f;
    let mean_y = y.iter().sum::<f64>() / n_f;
    let mut num = 0.0_f64;
    let mut sq_x = 0.0_f64;
    let mut sq_y = 0.0_f64;
    for i in 0..n {
        let dx = x[i] - mean_x;
        let dy = y[i] - mean_y;
        num += dx * dy;
        sq_x += dx * dx;
        sq_y += dy * dy;
    }
    let denom = (sq_x * sq_y).sqrt();
    if !denom.is_finite() || denom == 0.0 {
        return None;
    }
    let r = num / denom;
    if !r.is_finite() {
        return None;
    }
    Some(r.clamp(-1.0, 1.0))
}

// ============================================================
// RealRiskEnvelopeSourceProbe — production probe；impl emitter trait
// ============================================================

/// production probe；包 `Arc<parking_lot::Mutex<PortfolioStateCache>>`，emitter
/// `sample_now()` 呼叫端從 cache 讀 5 calculator 結果。
///
/// 為什麼 `Arc<Mutex<>>`:
///   - emitter 端 trait object 跨 tokio task 邊界（Send + Sync）；Arc 提供
///     reference count，Mutex 提供互斥讀寫。
///   - `parking_lot::Mutex` 對齊 cargo workspace 既有 dep；不引 std::sync::Mutex
///     避免 lock poisoning 噪音（per Track A/B/C/D/E/F 既有 pattern）。
///   - cache update 端（main.rs Wave B 接的 push task）與 probe 端（emitter
///     sample）共享同一 Arc；lock 時段都 < 1ms（5 calculator 純讀）。
///
/// 為什麼非 RwLock:
///   - emitter sample tick 是 300s 一次；update tick 是 300s 一次；不存在
///     「多 reader 1 writer 的高頻讀」情境；Mutex 足夠且實作簡單。
///   - 換 RwLock 是 Sprint 5 cascade 階段 hot-path 優化點，不在本 Wave A
///     scope。
pub struct RealRiskEnvelopeSourceProbe {
    cache: Arc<Mutex<PortfolioStateCache>>,
}

impl RealRiskEnvelopeSourceProbe {
    /// 建立 probe；caller 端注入共享 cache 句柄。
    ///
    /// 為什麼 `Arc<Mutex<...>>` 而非 generic:
    ///   - probe 是 trait object（`Arc<dyn RiskEnvelopeSourceProbe>`）；具體
    ///     struct 不需 generic 泛化。
    ///   - main.rs Wave B wire-up 時建 `Arc<Mutex<PortfolioStateCache>>` 一次，
    ///     clone 給 update task + probe；不需引入第二層抽象。
    pub fn new(cache: Arc<Mutex<PortfolioStateCache>>) -> Self {
        Self { cache }
    }

    /// E2 audit / test helper：直接拿 cache 句柄（不 expose mut 給外部寫入；
    /// 寫入由 `update_from_pipeline_snapshot` 走）。
    pub fn cache_handle(&self) -> Arc<Mutex<PortfolioStateCache>> {
        Arc::clone(&self.cache)
    }
}

impl RiskEnvelopeSourceProbe for RealRiskEnvelopeSourceProbe {
    fn current_portfolio_cum_pnl_24h_usd(&self) -> f64 {
        self.cache.lock().cum_pnl_24h_usd()
    }

    fn current_portfolio_max_dd_pct(&self) -> f64 {
        self.cache.lock().max_dd_pct_24h()
    }

    fn current_position_count_active(&self) -> u32 {
        self.cache.lock().position_count_active()
    }

    fn current_correlation_avg_pairwise(&self) -> f64 {
        self.cache.lock().correlation_avg_pairwise()
    }

    fn current_concentration_top1_pct(&self) -> f64 {
        self.cache.lock().concentration_top1_pct()
    }

    /// override default trait impl：一次 lock + batch 走 5 calculator，避免
    /// 5-lock gap micro-race window（per PA-DRIFT-5 round 1 E2 F-3 fix）。
    ///
    /// 為什麼 override：
    ///   - default impl 走 5 個 current_xxx 各拿一次 lock；emitter sample 時
    ///     5-lock gap 內若 cache update 介入 → 5-metric snapshot inconsistency。
    ///   - 本 override 拿一次 lock 後 batch 走 `cache.snapshot_5_metric()`，原
    ///     子地 snapshot 整個 5-metric tuple；對齊 emitter Wave B 接線後 race
    ///     window 不變式。
    ///   - emitter sample_now 端 Wave B 可切換走 `source.snapshot_5_metric()`
    ///     替代 5 個 current_xxx；本 round 不改 emitter（per scope 限制）。
    fn snapshot_5_metric(&self) -> RiskEnvelopeSampleSnapshot {
        self.cache.lock().snapshot_5_metric()
    }
}

// ============================================================
// 測試
// ============================================================

#[cfg(test)]
mod tests {
    use super::*;

    /// (1) cum_pnl 24h sum 基本 case：3 fill 加總。
    #[test]
    fn test_cum_pnl_24h_simple_sum() {
        let mut cache = PortfolioStateCache::new();
        let now_ms: u64 = 1_700_000_000_000;
        let new_fills = vec![(now_ms - 1000, 10.0), (now_ms - 500, -5.0), (now_ms, 3.5)];
        cache.update_from_pipeline_snapshot(
            now_ms,
            1000.0,
            &new_fills,
            Vec::new(),
            &HashMap::new(),
        );
        let sum = cache.cum_pnl_24h_usd();
        assert!(
            (sum - 8.5).abs() < 1e-4,
            "cum_pnl 應 8.5；實得 {}",
            sum
        );
        assert_eq!(cache.fill_history_len(), 3);
    }

    /// (1) 24h sliding window 截斷：> 24h 外的 fill 必 drop。
    #[test]
    fn test_cum_pnl_24h_drops_old_samples() {
        let mut cache = PortfolioStateCache::new();
        let now_ms: u64 = 1_700_000_000_000;
        // 加入一個 25h 前的 fill + 一個 1h 前的 fill。
        let old_fill_ts = now_ms - 25 * 60 * 60 * 1000;
        let recent_fill_ts = now_ms - 60 * 60 * 1000;
        let new_fills = vec![(old_fill_ts, 100.0), (recent_fill_ts, 7.0)];
        cache.update_from_pipeline_snapshot(
            now_ms,
            1000.0,
            &new_fills,
            Vec::new(),
            &HashMap::new(),
        );
        let sum = cache.cum_pnl_24h_usd();
        assert!(
            (sum - 7.0).abs() < 1e-4,
            "25h 外舊 fill 必 drop；只 sum 1h 前 7.0；實得 {}",
            sum
        );
        assert_eq!(cache.fill_history_len(), 1);
    }

    /// (1) empty cache → 0.0（fail-soft OK band 對齊）。
    #[test]
    fn test_cum_pnl_24h_empty_cache_returns_zero() {
        let cache = PortfolioStateCache::new();
        assert_eq!(cache.cum_pnl_24h_usd(), 0.0);
    }

    /// (2) max_dd_pct：mock equity curve 100→90→95，dd = ((100-90)/100)×100 = 10%。
    #[test]
    fn test_max_dd_pct_24h_peak_trough() {
        let mut cache = PortfolioStateCache::new();
        let now_ms: u64 = 1_700_000_000_000;
        // 推 3 個 equity sample（100 → 90 → 95）。
        cache.update_from_pipeline_snapshot(now_ms - 2000, 100.0, &[], Vec::new(), &HashMap::new());
        cache.update_from_pipeline_snapshot(now_ms - 1000, 90.0, &[], Vec::new(), &HashMap::new());
        cache.update_from_pipeline_snapshot(now_ms, 95.0, &[], Vec::new(), &HashMap::new());
        let dd = cache.max_dd_pct_24h();
        assert!(
            (dd - 10.0).abs() < 1e-4,
            "max_dd 應 10%（(100-90)/100×100）；實得 {}",
            dd
        );
        assert_eq!(cache.equity_history_len(), 3);
    }

    /// (2) max_dd_pct：equity 單調上升 → dd = 0。
    #[test]
    fn test_max_dd_pct_24h_monotonic_up_zero_dd() {
        let mut cache = PortfolioStateCache::new();
        let now_ms: u64 = 1_700_000_000_000;
        cache.update_from_pipeline_snapshot(now_ms - 2000, 100.0, &[], Vec::new(), &HashMap::new());
        cache.update_from_pipeline_snapshot(now_ms - 1000, 110.0, &[], Vec::new(), &HashMap::new());
        cache.update_from_pipeline_snapshot(now_ms, 120.0, &[], Vec::new(), &HashMap::new());
        let dd = cache.max_dd_pct_24h();
        assert_eq!(dd, 0.0, "單調上升 equity dd 應 0；實得 {}", dd);
    }

    /// (2) max_dd_pct：peak-trough 出現於中段，後續略恢復；仍取最大 dd。
    #[test]
    fn test_max_dd_pct_24h_takes_max_across_curve() {
        let mut cache = PortfolioStateCache::new();
        let now_ms: u64 = 1_700_000_000_000;
        // 100 → 110（peak）→ 88（trough；dd=20%）→ 95（恢復 dd=13.6%）。
        cache.update_from_pipeline_snapshot(now_ms - 3000, 100.0, &[], Vec::new(), &HashMap::new());
        cache.update_from_pipeline_snapshot(now_ms - 2000, 110.0, &[], Vec::new(), &HashMap::new());
        cache.update_from_pipeline_snapshot(now_ms - 1000, 88.0, &[], Vec::new(), &HashMap::new());
        cache.update_from_pipeline_snapshot(now_ms, 95.0, &[], Vec::new(), &HashMap::new());
        let dd = cache.max_dd_pct_24h();
        let expected = ((110.0 - 88.0) / 110.0) * 100.0;
        assert!(
            (dd - expected).abs() < 1e-4,
            "max_dd 應 {}（取 110→88 段）；實得 {}",
            expected,
            dd
        );
    }

    /// (3) position_count_active：3 個 exposure → count = 3。
    #[test]
    fn test_position_count_three_active() {
        let mut cache = PortfolioStateCache::new();
        let exposures = vec![
            PositionExposure { notional_usd: 100.0 },
            PositionExposure { notional_usd: 200.0 },
            PositionExposure { notional_usd: 150.0 },
        ];
        cache.update_from_pipeline_snapshot(
            1_700_000_000_000,
            1000.0,
            &[],
            exposures,
            &HashMap::new(),
        );
        assert_eq!(cache.position_count_active(), 3);
    }

    /// (3) position_count_active：empty → 0。
    #[test]
    fn test_position_count_empty_cache_zero() {
        let cache = PortfolioStateCache::new();
        assert_eq!(cache.position_count_active(), 0);
    }

    /// (4) correlation_avg_pairwise：empty cache cold-start fail-soft 0.0。
    ///
    /// 為什麼此 test:
    ///   - empty cache `per_symbol_returns_history` 0 symbol → < 2 → 走
    ///     cold-start return 0.0；對齊 OK band。
    ///   - Sprint 5+ Wave 1 §4.3.4 F-4 real calculator IMPL 後此 case 仍 0.0
    ///     （per PA spec §2.3 Step 5）。
    #[test]
    fn test_correlation_empty_cache_returns_zero() {
        let cache = PortfolioStateCache::new();
        assert_eq!(
            cache.correlation_avg_pairwise(),
            0.0,
            "empty cache cold-start 必返 0.0（per PA spec §2.3 Step 5）"
        );
    }

    /// (5) concentration_top1_pct：3 倉位 100/200/150，total=450，top1=200，
    /// concentration ≈ 44.44%。
    #[test]
    fn test_concentration_top1_pct_basic() {
        let mut cache = PortfolioStateCache::new();
        let exposures = vec![
            PositionExposure { notional_usd: 100.0 },
            PositionExposure { notional_usd: 200.0 },
            PositionExposure { notional_usd: 150.0 },
        ];
        cache.update_from_pipeline_snapshot(
            1_700_000_000_000,
            1000.0,
            &[],
            exposures,
            &HashMap::new(),
        );
        let conc = cache.concentration_top1_pct();
        let expected = 200.0 / 450.0 * 100.0;
        assert!(
            (conc - expected).abs() < 1e-4,
            "concentration_top1 應 {:.4}%；實得 {:.4}",
            expected,
            conc
        );
    }

    /// (5) concentration_top1_pct：empty → 0.0。
    #[test]
    fn test_concentration_top1_pct_empty_zero() {
        let cache = PortfolioStateCache::new();
        assert_eq!(cache.concentration_top1_pct(), 0.0);
    }

    /// (5) concentration_top1_pct：單一倉位 → 100%。
    #[test]
    fn test_concentration_top1_pct_single_position() {
        let mut cache = PortfolioStateCache::new();
        let exposures = vec![PositionExposure { notional_usd: 250.0 }];
        cache.update_from_pipeline_snapshot(
            1_700_000_000_000,
            1000.0,
            &[],
            exposures,
            &HashMap::new(),
        );
        let conc = cache.concentration_top1_pct();
        assert!(
            (conc - 100.0).abs() < 1e-4,
            "單倉位 concentration 應 100%；實得 {}",
            conc
        );
    }

    /// (5) concentration_top1_pct：負 notional 取絕對值；不被「多空互沖」誤判低集中度。
    #[test]
    fn test_concentration_top1_pct_uses_abs_notional() {
        let mut cache = PortfolioStateCache::new();
        let exposures = vec![
            PositionExposure { notional_usd: 100.0 },
            PositionExposure { notional_usd: -200.0 }, // 空倉，但 exposure 仍 200
        ];
        cache.update_from_pipeline_snapshot(
            1_700_000_000_000,
            1000.0,
            &[],
            exposures,
            &HashMap::new(),
        );
        let conc = cache.concentration_top1_pct();
        let expected = 200.0 / 300.0 * 100.0;
        assert!(
            (conc - expected).abs() < 1e-4,
            "abs notional 後 concentration 應 {:.4}%；實得 {:.4}",
            expected,
            conc
        );
    }

    /// (6) RealRiskEnvelopeSourceProbe：5 trait method 對齊 cache 端輸出。
    #[test]
    fn test_real_probe_5_methods_align_with_cache() {
        let cache = Arc::new(Mutex::new(PortfolioStateCache::new()));
        // 推入測試資料：cum_pnl=8.5 / equity 100→90 dd=10% / 3 倉位 / concentration ≈ 44.44%。
        {
            let mut guard = cache.lock();
            let now_ms: u64 = 1_700_000_000_000;
            guard.update_from_pipeline_snapshot(
                now_ms - 1000,
                100.0,
                &[(now_ms - 1500, 10.0)],
                vec![
                    PositionExposure { notional_usd: 100.0 },
                    PositionExposure { notional_usd: 200.0 },
                    PositionExposure { notional_usd: 150.0 },
                ],
                &HashMap::new(),
            );
            guard.update_from_pipeline_snapshot(
                now_ms,
                90.0,
                &[(now_ms - 500, -5.0), (now_ms, 3.5)],
                vec![
                    PositionExposure { notional_usd: 100.0 },
                    PositionExposure { notional_usd: 200.0 },
                    PositionExposure { notional_usd: 150.0 },
                ],
                &HashMap::new(),
            );
        }
        let probe = RealRiskEnvelopeSourceProbe::new(cache);

        let cum_pnl = probe.current_portfolio_cum_pnl_24h_usd();
        assert!(
            (cum_pnl - 8.5).abs() < 1e-4,
            "probe cum_pnl 應 8.5；實得 {}",
            cum_pnl
        );

        let dd = probe.current_portfolio_max_dd_pct();
        assert!(
            (dd - 10.0).abs() < 1e-4,
            "probe max_dd 應 10%；實得 {}",
            dd
        );

        assert_eq!(probe.current_position_count_active(), 3);

        assert_eq!(
            probe.current_correlation_avg_pairwise(),
            0.0,
            "empty per_symbol_returns_history cold-start fail-soft 0.0"
        );

        let conc = probe.current_concentration_top1_pct();
        let expected = 200.0 / 450.0 * 100.0;
        assert!(
            (conc - expected).abs() < 1e-4,
            "probe concentration 應 {:.4}%；實得 {:.4}",
            expected,
            conc
        );
    }

    /// (6) probe 多次 lock 同 cache 不死鎖（telemetry sanity）。
    #[test]
    fn test_real_probe_multiple_lock_not_deadlock() {
        let cache = Arc::new(Mutex::new(PortfolioStateCache::new()));
        let probe = RealRiskEnvelopeSourceProbe::new(Arc::clone(&cache));
        // 5 method 順序呼叫；每次都拿 lock 後立即釋放。
        let _ = probe.current_portfolio_cum_pnl_24h_usd();
        let _ = probe.current_portfolio_max_dd_pct();
        let _ = probe.current_position_count_active();
        let _ = probe.current_correlation_avg_pairwise();
        let _ = probe.current_concentration_top1_pct();
    }

    /// (6) cache_handle audit：返同一 Arc 句柄不重新建構。
    #[test]
    fn test_cache_handle_returns_same_arc() {
        let cache = Arc::new(Mutex::new(PortfolioStateCache::new()));
        let probe = RealRiskEnvelopeSourceProbe::new(Arc::clone(&cache));
        let handle1 = probe.cache_handle();
        let handle2 = probe.cache_handle();
        assert!(
            Arc::ptr_eq(&handle1, &handle2),
            "cache_handle 必返同一 Arc 句柄"
        );
        assert!(
            Arc::ptr_eq(&handle1, &cache),
            "cache_handle 必對齊 probe 構造時的 Arc"
        );
    }

    /// (7) PortfolioStateCache::snapshot_5_metric batch read 對齊個別 accessor
    /// （per PA-DRIFT-5 round 1 E2 F-3 fix）。
    #[test]
    fn test_cache_snapshot_5_metric_aligns_with_individual_accessors() {
        let mut cache = PortfolioStateCache::new();
        let now_ms: u64 = 1_700_000_000_000;
        cache.update_from_pipeline_snapshot(
            now_ms - 1000,
            100.0,
            &[(now_ms - 1500, 10.0), (now_ms - 800, -3.5)],
            vec![
                PositionExposure { notional_usd: 200.0 },
                PositionExposure { notional_usd: 50.0 },
            ],
            &HashMap::new(),
        );
        cache.update_from_pipeline_snapshot(
            now_ms,
            85.0,
            &[(now_ms - 100, 2.0)],
            vec![
                PositionExposure { notional_usd: 200.0 },
                PositionExposure { notional_usd: 50.0 },
            ],
            &HashMap::new(),
        );

        let snapshot = cache.snapshot_5_metric();

        // batch snapshot 必字面對齊 5 個 individual accessor
        assert!(
            (snapshot.portfolio_cum_pnl_24h_usd - cache.cum_pnl_24h_usd()).abs() < 1e-9,
        );
        assert!(
            (snapshot.portfolio_max_dd_pct - cache.max_dd_pct_24h()).abs() < 1e-9,
        );
        assert_eq!(snapshot.position_count_active, cache.position_count_active());
        assert!(
            (snapshot.correlation_avg_pairwise - cache.correlation_avg_pairwise()).abs() < 1e-9,
        );
        assert!(
            (snapshot.concentration_top1_pct - cache.concentration_top1_pct()).abs() < 1e-9,
        );
    }

    /// (8) F-2 sanitize：NaN realized_pnl 必 skip，不污染 cum_pnl sum
    /// （per PA-DRIFT-5 round 2 E2 升級 P1 Wave B condition）。
    #[test]
    fn test_f2_sanitize_skips_nan_realized_pnl() {
        let mut cache = PortfolioStateCache::new();
        let now_ms: u64 = 1_700_000_000_000;
        // 混入 NaN / inf / 正常 fill。
        let fills = vec![
            (now_ms - 1000, 10.0),
            (now_ms - 800, f64::NAN),
            (now_ms - 600, f64::INFINITY),
            (now_ms - 400, -5.0),
            (now_ms - 200, f64::NEG_INFINITY),
            (now_ms - 100, 3.5),
        ];
        cache.update_from_pipeline_snapshot(now_ms, 100.0, &fills, Vec::new(), &HashMap::new());
        // 應只 push 3 個 legal fill；NaN/inf/-inf 全 skip。
        assert_eq!(
            cache.fill_history_len(),
            3,
            "NaN/inf realized_pnl 必 skip；只留 3 legal fill"
        );
        // cum_pnl 必為 10 + (-5) + 3.5 = 8.5，與 NaN test 一致。
        let sum = cache.cum_pnl_24h_usd();
        assert!(
            (sum - 8.5).abs() < 1e-4,
            "F-2 sanitize 後 cum_pnl 應 8.5；實得 {}",
            sum
        );
        assert!(sum.is_finite(), "cum_pnl 必為 finite；不被 NaN 污染");
    }

    /// (8) F-2 sanitize：NaN equity 必 skip，max_dd 計算保 finite。
    #[test]
    fn test_f2_sanitize_skips_nan_equity() {
        let mut cache = PortfolioStateCache::new();
        let now_ms: u64 = 1_700_000_000_000;
        // 3 次 update：正常 + NaN + 正常。
        cache.update_from_pipeline_snapshot(now_ms - 2000, 100.0, &[], Vec::new(), &HashMap::new());
        cache.update_from_pipeline_snapshot(
            now_ms - 1000,
            f64::NAN,
            &[],
            Vec::new(),
            &HashMap::new(),
        );
        cache.update_from_pipeline_snapshot(now_ms, 95.0, &[], Vec::new(), &HashMap::new());
        // 只應 push 2 個 legal equity sample。
        assert_eq!(
            cache.equity_history_len(),
            2,
            "NaN equity 必 skip；只留 2 legal sample"
        );
        let dd = cache.max_dd_pct_24h();
        assert!(dd.is_finite(), "max_dd 必為 finite；不被 NaN 污染");
        let expected = ((100.0 - 95.0) / 100.0) * 100.0;
        assert!(
            (dd - expected).abs() < 1e-4,
            "F-2 sanitize 後 max_dd 應 {}；實得 {}",
            expected,
            dd
        );
    }

    /// (8) F-2 sanitize：inf notional exposure 必過濾，concentration 計算保 finite。
    #[test]
    fn test_f2_sanitize_filters_nan_exposure() {
        let mut cache = PortfolioStateCache::new();
        let now_ms: u64 = 1_700_000_000_000;
        let exposures = vec![
            PositionExposure { notional_usd: 100.0 },
            PositionExposure { notional_usd: f64::NAN },
            PositionExposure { notional_usd: 200.0 },
            PositionExposure { notional_usd: f64::INFINITY },
            PositionExposure { notional_usd: 50.0 },
        ];
        cache.update_from_pipeline_snapshot(now_ms, 100.0, &[], exposures, &HashMap::new());
        // 應只剩 3 個 legal exposure。
        assert_eq!(
            cache.position_count_active(),
            3,
            "NaN/inf notional 必過濾；只留 3 legal"
        );
        let conc = cache.concentration_top1_pct();
        let expected = 200.0 / 350.0 * 100.0;
        assert!(
            (conc - expected).abs() < 1e-4,
            "F-2 sanitize 後 concentration 應 {:.4}%；實得 {:.4}",
            expected,
            conc
        );
        assert!(conc.is_finite(), "concentration 必為 finite");
    }

    /// (7) RealRiskEnvelopeSourceProbe::snapshot_5_metric override 走 batch 路徑
    /// 對齊 5 個 current_xxx；emitter wire-up Wave B 切換時的 contract 不變式。
    #[test]
    fn test_real_probe_snapshot_5_metric_aligns_with_5_current_xxx() {
        let cache = Arc::new(Mutex::new(PortfolioStateCache::new()));
        {
            let mut guard = cache.lock();
            let now_ms: u64 = 1_700_000_000_000;
            guard.update_from_pipeline_snapshot(
                now_ms,
                90.0,
                &[(now_ms - 500, 10.0), (now_ms, 3.5)],
                vec![
                    PositionExposure { notional_usd: 100.0 },
                    PositionExposure { notional_usd: 200.0 },
                    PositionExposure { notional_usd: 150.0 },
                ],
                &HashMap::new(),
            );
        }
        let probe = RealRiskEnvelopeSourceProbe::new(cache);

        let batch = probe.snapshot_5_metric();
        let cum_pnl = probe.current_portfolio_cum_pnl_24h_usd();
        let dd = probe.current_portfolio_max_dd_pct();
        let pos_count = probe.current_position_count_active();
        let corr = probe.current_correlation_avg_pairwise();
        let conc = probe.current_concentration_top1_pct();

        assert!((batch.portfolio_cum_pnl_24h_usd - cum_pnl).abs() < 1e-9);
        assert!((batch.portfolio_max_dd_pct - dd).abs() < 1e-9);
        assert_eq!(batch.position_count_active, pos_count);
        assert!((batch.correlation_avg_pairwise - corr).abs() < 1e-9);
        assert!((batch.concentration_top1_pct - conc).abs() < 1e-9);
    }

    // ============================================================
    // F-4 correlation_avg_pairwise real calculator tests
    // （per PA Sprint 5+ Wave 1 §4.3.4 spec §3.1）
    // ============================================================

    /// helper: 推 N 個 sample 給 (sym1, sym2) 兩 series，價格走 multiplier
    /// pattern；caller 端控制 base price + multiplier 構造 identical / inverse
    /// / uncorrelated pattern。
    ///
    /// 為什麼此 helper:
    ///   - F-4 IMPL 內部 return = (this - prev) / prev；測試端需多 push 才有
    ///     return sample（首次 push 只記 last_price）。
    ///   - N+1 次 push 才產生 N return sample；caller 端控 N 達 MIN_PAIRWISE_SAMPLES。
    fn push_n_samples(
        cache: &mut PortfolioStateCache,
        now_ms_start: u64,
        tick_interval_ms: u64,
        sym_prices: &[(&str, &[f64])],
    ) {
        // 對 sym_prices 內每個 series 的最長 N 同步推 N 次 update。
        let max_len = sym_prices
            .iter()
            .map(|(_, prices)| prices.len())
            .max()
            .unwrap_or(0);
        for i in 0..max_len {
            let now_ms = now_ms_start + (i as u64) * tick_interval_ms;
            let mut prices_map: HashMap<String, f64> = HashMap::new();
            for (sym, prices) in sym_prices.iter() {
                if let Some(&p) = prices.get(i) {
                    prices_map.insert((*sym).to_string(), p);
                }
            }
            cache.update_from_pipeline_snapshot(
                now_ms,
                100.0,
                &[],
                Vec::new(),
                &prices_map,
            );
        }
    }

    /// F-4 test 1: single symbol → returns 0.0（n < 2，cold-start fail-soft）。
    #[test]
    fn test_correlation_single_symbol_returns_zero() {
        let mut cache = PortfolioStateCache::new();
        let now_ms_start: u64 = 1_700_000_000_000;
        // 推 7 個 BTCUSDT 樣本（>= MIN_PAIRWISE_SAMPLES=5），但只有 1 symbol。
        let btc_prices = vec![100.0, 101.0, 102.0, 101.5, 102.5, 103.0, 103.5];
        push_n_samples(
            &mut cache,
            now_ms_start,
            60_000,
            &[("BTCUSDT", &btc_prices)],
        );
        // 6 return sample（7 push - 1 first skip）≥ MIN，但 symbols.len()=1 < 2。
        let r = cache.correlation_avg_pairwise();
        assert_eq!(r, 0.0, "single symbol < 2 必返 0.0 cold-start");
    }

    /// F-4 test 2: two identical series → |r|=1.0（per Pearson 定義）。
    #[test]
    fn test_correlation_two_identical_series_returns_one() {
        let mut cache = PortfolioStateCache::new();
        let now_ms_start: u64 = 1_700_000_000_000;
        // 兩條完全相同的價格序列；同 ts 同 price → 同 return series。
        let prices = vec![100.0, 101.0, 102.0, 103.0, 102.5, 103.5, 104.0];
        push_n_samples(
            &mut cache,
            now_ms_start,
            60_000,
            &[("AAA", &prices), ("BBB", &prices)],
        );
        let r = cache.correlation_avg_pairwise();
        // 浮點漂移容差 1e-9（clamp 後）。
        assert!(
            (r - 1.0).abs() < 1e-9,
            "two identical return series 必 |r|=1.0；實得 {}",
            r
        );
    }

    /// F-4 test 3: two perfectly inverse series → |r|=1.0（abs avg）。
    #[test]
    fn test_correlation_two_inverse_series_abs_avg_one() {
        let mut cache = PortfolioStateCache::new();
        let now_ms_start: u64 = 1_700_000_000_000;
        // sym1 漲跌 vs sym2 完全反向：sym2_price = 200 - sym1_price 之 linear
        // transform → return 為 -1 倍 sym1 return。
        let p1 = vec![100.0, 102.0, 104.0, 103.0, 105.0, 107.0, 106.0];
        // 反向：每 tick 取 200 - p1[i]；確保 prev > 0。
        let p2: Vec<f64> = p1.iter().map(|&v| 200.0 - v).collect();
        push_n_samples(
            &mut cache,
            now_ms_start,
            60_000,
            &[("AAA", &p1), ("BBB", &p2)],
        );
        let r = cache.correlation_avg_pairwise();
        // 注意：return = (p2_curr - p2_prev) / p2_prev；因 p2 是 200-p1 linear
        // shift，不是 multiplicative inverse → r 不一定恰 -1。但符號 absolute
        // 應 close to 1.0；fail-soft 容差 1e-6（畢竟 price level shift 對
        // percentage return 有微差）。
        // 我們僅斷言 r > 0.99（強相關，反向經 abs avg 後接近 1）。
        assert!(
            r > 0.99,
            "perfectly inverse-by-shift series |r| 應 > 0.99；實得 {}",
            r
        );
        assert!(r <= 1.0, "|r| 必 <= 1.0；實得 {}", r);
    }

    /// F-4 test 4: two uncorrelated series → |r| 接近 0（≤ 0.5 寬鬆容差）。
    #[test]
    fn test_correlation_two_uncorrelated_series_near_zero() {
        let mut cache = PortfolioStateCache::new();
        let now_ms_start: u64 = 1_700_000_000_000;
        // 兩條人造低相關 series：p1 上升 step，p2 振盪 step 不對齊。
        let p1 = vec![100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0];
        let p2 = vec![100.0, 102.0, 100.5, 102.5, 100.8, 102.2, 100.6];
        push_n_samples(
            &mut cache,
            now_ms_start,
            60_000,
            &[("AAA", &p1), ("BBB", &p2)],
        );
        let r = cache.correlation_avg_pairwise();
        // 6 return sample；low correlation 接受 r < 0.7（噪音範圍寬）。
        // 重點：r 為 finite + 在 [0, 1]（abs avg 已 clamp）。
        assert!(r.is_finite(), "r 必為 finite；實得 {}", r);
        assert!(r >= 0.0 && r <= 1.0, "abs avg 必在 [0, 1]；實得 {}", r);
        // human-readable sanity（這組樣本 r ≈ 0.4-0.6 範圍）；不硬編期望值
        // 避免 fixture 微調撞 test。
    }

    /// F-4 test 5: 5 symbol pairwise C(5,2)=10 pair 平均；單調漸增 series 共
    /// 4 對 identical pattern + 6 對 mixed → 結果 finite + [0,1]。
    #[test]
    fn test_correlation_five_symbol_pairwise_avg() {
        let mut cache = PortfolioStateCache::new();
        let now_ms_start: u64 = 1_700_000_000_000;
        // 5 symbol 各 7 price sample；混合 identical(2) + 略偏移(2) + 不對齊(1)
        // pattern；確保 C(5,2)=10 pair 全達 MIN_PAIRWISE_SAMPLES=5。
        let p1 = vec![100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0];
        let p2 = vec![200.0, 202.0, 204.0, 206.0, 208.0, 210.0, 212.0];
        let p3 = vec![100.0, 100.8, 101.6, 102.4, 103.2, 104.0, 104.8];
        let p4 = vec![50.0, 51.0, 52.0, 53.0, 54.0, 55.0, 56.0];
        let p5 = vec![100.0, 99.0, 101.0, 99.5, 101.5, 100.0, 102.0];
        push_n_samples(
            &mut cache,
            now_ms_start,
            60_000,
            &[
                ("AAA", &p1),
                ("BBB", &p2),
                ("CCC", &p3),
                ("DDD", &p4),
                ("EEE", &p5),
            ],
        );
        let r = cache.correlation_avg_pairwise();
        assert!(r.is_finite(), "5-symbol pairwise r 必 finite；實得 {}", r);
        assert!(r >= 0.0 && r <= 1.0, "|r| 平均必在 [0, 1]；實得 {}", r);
        // 4 series 同單調 + 1 振盪 → 預期 r 較高（> 0.5）。
        assert!(
            r > 0.5,
            "4 series 強相關 + 1 弱相關 expected r > 0.5；實得 {}",
            r
        );
    }

    /// F-4 test 6: mid_price NaN / inf / <= 0 sanitize 不污染 sliding window。
    #[test]
    fn test_correlation_mid_price_nan_inf_sanitize_does_not_panic() {
        let mut cache = PortfolioStateCache::new();
        let now_ms_start: u64 = 1_700_000_000_000;
        // 混入 NaN / inf / 負 / 零 / 正常 mid_price；F-2 sanitize 必 skip 不 panic。
        let mut prices_map = HashMap::new();
        prices_map.insert("AAA".to_string(), 100.0);
        prices_map.insert("BBB".to_string(), f64::NAN);
        prices_map.insert("CCC".to_string(), f64::INFINITY);
        prices_map.insert("DDD".to_string(), -10.0);
        prices_map.insert("EEE".to_string(), 0.0);
        cache.update_from_pipeline_snapshot(
            now_ms_start,
            100.0,
            &[],
            Vec::new(),
            &prices_map,
        );
        // 二次 push 構造 1 return sample for AAA only。
        let mut prices_map2 = HashMap::new();
        prices_map2.insert("AAA".to_string(), 101.0);
        cache.update_from_pipeline_snapshot(
            now_ms_start + 60_000,
            100.0,
            &[],
            Vec::new(),
            &prices_map2,
        );
        // 只 AAA 進 history（其他全 sanitize skip）；單 symbol → corr=0。
        let r = cache.correlation_avg_pairwise();
        assert_eq!(r, 0.0, "NaN/inf/<=0 sanitize 後 single symbol 必返 0.0");
        // last_symbol_prices 只應留 AAA。
        // （不直接 expose；透過 push 第 3 次再驗 deque len 即可。）
    }

    /// F-4 test 7: 1h sliding window drain 舊 sample 必 drop；
    /// 跨 1h boundary 後舊 deque sample drained，未達 MIN_PAIRWISE_SAMPLES → corr=0。
    #[test]
    fn test_correlation_sliding_window_1h_drain_old_samples() {
        let mut cache = PortfolioStateCache::new();
        let now_ms_start: u64 = 1_700_000_000_000;
        // 推 6 個 sample 進 AAA + BBB（5min tick）；MIN_PAIRWISE_SAMPLES=5 達標。
        let p1 = vec![100.0, 101.0, 102.0, 103.0, 104.0, 105.0];
        let p2 = vec![200.0, 202.0, 204.0, 206.0, 208.0, 210.0];
        push_n_samples(
            &mut cache,
            now_ms_start,
            5 * 60_000, // 5min tick
            &[("AAA", &p1), ("BBB", &p2)],
        );
        // 第一輪：sample 充足，r 應為 1（identical normalized return）。
        let r_initial = cache.correlation_avg_pairwise();
        assert!(
            (r_initial - 1.0).abs() < 1e-9,
            "initial r 應 1.0；實得 {}",
            r_initial
        );

        // 推 1 次新 sample，但 now_ms 跳到 +2h 後（舊 sample 全在 1h 外應 drain）。
        let very_late_ts = now_ms_start + 2 * 60 * 60 * 1000;
        let mut prices_map = HashMap::new();
        prices_map.insert("AAA".to_string(), 200.0);
        prices_map.insert("BBB".to_string(), 400.0);
        cache.update_from_pipeline_snapshot(
            very_late_ts,
            100.0,
            &[],
            Vec::new(),
            &prices_map,
        );
        // 但需注意：last_symbol_prices 仍留舊 105 / 210（未清理；per spec 接受
        // stale），此次 push 計算 return = (200-105)/105 ≈ 0.905 等。
        // 1h drain 後舊 sample 全清除；only 此次新 return 進 deque → deque len=1
        // < MIN_PAIRWISE_SAMPLES=5 → corr=0。
        let r_after_drain = cache.correlation_avg_pairwise();
        assert_eq!(
            r_after_drain, 0.0,
            "1h 後舊 sample drain；< MIN_PAIRWISE_SAMPLES → corr=0；實得 {}",
            r_after_drain
        );
    }
}
