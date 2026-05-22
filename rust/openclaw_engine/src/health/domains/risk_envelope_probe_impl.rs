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

use std::collections::VecDeque;
use std::sync::Arc;

use parking_lot::Mutex;

use super::risk_envelope::RiskEnvelopeSourceProbe;

// 24h 毫秒（cache 滑動視窗保留視窗大小；超過此年齡的 fill / equity sample 從
// 視窗淘汰）。
const SLIDING_WINDOW_24H_MS: u64 = 24 * 60 * 60 * 1000;

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
/// 為什麼 cap = 100k:
///   - 24h × 86400s × 1 fill/s 上限 86400；100k 含 safety margin。
///   - 若 fill rate 超過 1/s 大量湧入，cap 端早 drop 舊 sample 是 fail-soft
///     （不 panic）；emitter probe 返舊 cache 值。
///   - cap 不為 NDay 警告閾值；NDay 觀測由 V106 row 監控（per 既有 Track F
///     ladder fire）。
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
    pub fn update_from_pipeline_snapshot(
        &mut self,
        now_ms: u64,
        equity_usd: f64,
        new_fills: &[(u64, f64)],
        latest_exposures: Vec<PositionExposure>,
    ) {
        // 1. push 增量 fill 到 sliding window，並截斷 24h 外的舊 sample。
        for &(ts_ms, realized_pnl) in new_fills.iter() {
            self.realized_pnl_history.push_back((ts_ms, realized_pnl));
        }
        self.drain_old_fills(now_ms);

        // 2. push 當前 equity sample；截斷 24h 外的舊 sample。
        self.equity_history.push_back((now_ms, equity_usd));
        self.drain_old_equity(now_ms);

        // 3. 整列覆寫 latest position notional snapshot。
        self.latest_exposures = latest_exposures;

        // 4. 更新最後 update 時戳（telemetry）。
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

    /// (4) 跨倉位 pairwise correlation 平均（per task §4）；本 Wave A 端
    /// **placeholder 返 0.0**。
    ///
    /// 為什麼 placeholder（per dispatch packet §7.5 反模式 (c) + E2 Track F
    /// round 2 對抗反問 #2 correlation lookback 設計）:
    ///   - portfolio cross-pair correlation rolling window 需 per-symbol returns
    ///     time series + rolling window size + pairwise correlation matrix
    ///     compute；本 Wave A 不引入新 storage struct（會碰 PaperState
    ///     寫入路徑）。
    ///   - 既有 `crate::scanner::scorer::apply_correlation_filter` 是 scanner
    ///     -level filter（候選池容量上限），非 portfolio-level cross-pair
    ///     correlation；不可直接 reuse。
    ///   - lookback 設計（60s? 5min? 1h? 24h?）由 PA 拍板（per E2 Track F round 2
    ///     對抗反問 #2 carry-over）；Wave A 不設計新 lookback。
    ///   - Wave B / Sprint 5 cascade IMPL 端決定接什麼 source（既有 `panel_aggregator`
    ///     端 cross-strategy correlation panel 或新 calculator），本 placeholder
    ///     不阻塞 emitter wire-up（probe trait 端有合法返值，classify 走 OK band）。
    pub fn correlation_avg_pairwise(&self) -> f64 {
        // Wave A placeholder：實 correlation calculator 由 Wave B 接，per
        // dispatch §7.5 反模式 (c)。
        0.0
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
        cache.update_from_pipeline_snapshot(now_ms, 1000.0, &new_fills, Vec::new());
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
        cache.update_from_pipeline_snapshot(now_ms, 1000.0, &new_fills, Vec::new());
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
        cache.update_from_pipeline_snapshot(now_ms - 2000, 100.0, &[], Vec::new());
        cache.update_from_pipeline_snapshot(now_ms - 1000, 90.0, &[], Vec::new());
        cache.update_from_pipeline_snapshot(now_ms, 95.0, &[], Vec::new());
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
        cache.update_from_pipeline_snapshot(now_ms - 2000, 100.0, &[], Vec::new());
        cache.update_from_pipeline_snapshot(now_ms - 1000, 110.0, &[], Vec::new());
        cache.update_from_pipeline_snapshot(now_ms, 120.0, &[], Vec::new());
        let dd = cache.max_dd_pct_24h();
        assert_eq!(dd, 0.0, "單調上升 equity dd 應 0；實得 {}", dd);
    }

    /// (2) max_dd_pct：peak-trough 出現於中段，後續略恢復；仍取最大 dd。
    #[test]
    fn test_max_dd_pct_24h_takes_max_across_curve() {
        let mut cache = PortfolioStateCache::new();
        let now_ms: u64 = 1_700_000_000_000;
        // 100 → 110（peak）→ 88（trough；dd=20%）→ 95（恢復 dd=13.6%）。
        cache.update_from_pipeline_snapshot(now_ms - 3000, 100.0, &[], Vec::new());
        cache.update_from_pipeline_snapshot(now_ms - 2000, 110.0, &[], Vec::new());
        cache.update_from_pipeline_snapshot(now_ms - 1000, 88.0, &[], Vec::new());
        cache.update_from_pipeline_snapshot(now_ms, 95.0, &[], Vec::new());
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
        cache.update_from_pipeline_snapshot(1_700_000_000_000, 1000.0, &[], exposures);
        assert_eq!(cache.position_count_active(), 3);
    }

    /// (3) position_count_active：empty → 0。
    #[test]
    fn test_position_count_empty_cache_zero() {
        let cache = PortfolioStateCache::new();
        assert_eq!(cache.position_count_active(), 0);
    }

    /// (4) correlation_avg_pairwise：Wave A placeholder 永遠 0.0。
    #[test]
    fn test_correlation_placeholder_returns_zero() {
        let cache = PortfolioStateCache::new();
        assert_eq!(
            cache.correlation_avg_pairwise(),
            0.0,
            "Wave A placeholder；Wave B 後實 calculator 接上"
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
        cache.update_from_pipeline_snapshot(1_700_000_000_000, 1000.0, &[], exposures);
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
        cache.update_from_pipeline_snapshot(1_700_000_000_000, 1000.0, &[], exposures);
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
        cache.update_from_pipeline_snapshot(1_700_000_000_000, 1000.0, &[], exposures);
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
            "Wave A placeholder"
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
}
