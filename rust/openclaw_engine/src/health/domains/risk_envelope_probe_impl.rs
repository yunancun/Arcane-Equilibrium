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

use super::risk_envelope::{RiskEnvelopeSampleSnapshot, RiskEnvelopeSourceProbe};

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
    pub fn update_from_pipeline_snapshot(
        &mut self,
        now_ms: u64,
        equity_usd: f64,
        new_fills: &[(u64, f64)],
        latest_exposures: Vec<PositionExposure>,
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
        );
        cache.update_from_pipeline_snapshot(
            now_ms,
            85.0,
            &[(now_ms - 100, 2.0)],
            vec![
                PositionExposure { notional_usd: 200.0 },
                PositionExposure { notional_usd: 50.0 },
            ],
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
        cache.update_from_pipeline_snapshot(now_ms, 100.0, &fills, Vec::new());
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
        cache.update_from_pipeline_snapshot(now_ms - 2000, 100.0, &[], Vec::new());
        cache.update_from_pipeline_snapshot(now_ms - 1000, f64::NAN, &[], Vec::new());
        cache.update_from_pipeline_snapshot(now_ms, 95.0, &[], Vec::new());
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
        cache.update_from_pipeline_snapshot(now_ms, 100.0, &[], exposures);
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
}
