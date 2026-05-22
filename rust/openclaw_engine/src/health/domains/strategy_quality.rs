//! M3 Sprint 2 Wave 2 Track E — strategy_quality domain emitter（per-strategy
//! SM 25 instance + aggregate SM 0.40 rule）。
//!
//! MODULE_NOTE
//! 模塊用途:
//!   per docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_design_spec.md
//!   §2.1 + §3.2 + §3.4 + §4.4 + dispatch packet §6 / M3 spec line 81 + 105
//!   + 207-211：採樣 per-(strategy, symbol) 業務級活性指標，每 5min 一輪，
//!   產 4 個有 band 的 metric row + 1 telemetry-only signal_count_24h row →
//!   `StrategyQualityScheduler` 維護 25 instance per-(strategy, symbol) SM +
//!   aggregate SM（rule: degraded_count / total_count > 0.40 → DEGRADED）。
//!
//!   為什麼 5min sample interval（per spec §2.1 line 245）：
//!     業務級活性慢動指標；strategy dormant > 60min 才升 WARN；fill rate /
//!     slippage / lease grant 分鐘級才有意義，高頻 self-query 對 sqlx Pool
//!     是 hot path 干擾源（per dispatch packet §6.5 反模式 (b)）。對齊 5-sample
//!     × 5min = 25min window；與 §3.3 dwell time（OK→WARN 60s / WARN→DEGRADED
//!     5min）為兩個正交概念（measurement window vs SM dwell；per M3 spec §4.3）。
//!
//!   為什麼 25 instance SM（per spec §3.4 line 207 + §4.4 line 638-643）：
//!     strategy_quality 是業務 domain，不同 (strategy, symbol) 行為獨立；
//!     共用 SM 會導致 grid::BTCUSDT 升 DEGRADED 連帶 ma::ETHUSDT 也被視為
//!     DEGRADED，破壞 cross-strategy 觀測獨立性。25 個 SM 各自獨立 dwell /
//!     cap window；aggregate SM 由獨立計算「degraded_count / total_count」
//!     升降階。
//!
//!   為什麼 aggregate rule 0.40 而非 max(per-strategy state)（per spec §3.4
//!   line 211 + §4.4 line 646-651）：
//!     - max() 過敏感：1 個 strategy::symbol DEGRADED 即全 system-level
//!       DEGRADED，會誤觸 §5 cascade 大規模降階。
//!     - 0.40 threshold 提供策略級觀測的容忍度：40% 以上 (strategy, symbol)
//!       pair DEGRADED 才算 system-level DEGRADED；對齊 portfolio 多元化
//!       原則（per §二 16 根原則 #16）。
//!     - per-strategy DEGRADED 仍可走 M7 DECAY_ENFORCED 路徑（Sprint 5 才接，
//!       per spec §5.1 line 256）；Sprint 2 emit V106 row + StrategyHealthEvent
//!       預埋 event_bus 但不觸 M7 / 不降 LAL Tier。
//!
//! 主要類 / 函數:
//!   - `StrategyQualitySample`：6 field snapshot struct（per spec §3.2 5 field +
//!     pool_disconnected 範式參考；本 emitter 用 strategy_name + symbol 雙鍵
//!     替代 disconnected flag）。
//!   - `StrategyQualityMetricRow`：MetricSample trait 投影（per metric_name × per
//!     (strategy, symbol) pair）；scheduler 端列表處理。
//!   - `StrategyQualitySourceProbe` trait：抽象 per-(strategy, symbol) 採樣源；
//!     main.rs 接線時注入 decision_outcomes / lease audit / strategy event
//!     真實 hook；test 注入 mock。
//!   - `classify_strategy_quality_*` × 4：per-metric classify_band 函數，threshold
//!     來自 M3 spec line 105。
//!   - `StrategyQualityEmitter`：impl `DomainEmitter`；sample_interval=300s；
//!     **sample 端返一個 (strategy, symbol) pair 的全部 row**（caller 端 25 個
//!     emitter or 單 emitter 多 pair 由 scheduler 配置）。
//!   - `StrategyQualityScheduler`：獨立 scheduler（不沿用 `MetricEmitterScheduler`
//!     因 25 instance per-(strategy, symbol) SM 與 single-SM 路徑不同），維護
//!     25 instance SM map + aggregate SM；自走 tokio interval loop；寫 V106 row
//!     帶 strategy_name + symbol 兩列。
//!
//! 依賴:
//!   - 沿用 Track A scaffold（`DomainEmitter` trait / `MetricSample` trait /
//!     `RollingWindowAggregator` / `HealthObservationWriter` / `HealthEventBus`
//!     / `HealthStateMachine::observe_classified` / `classify_aggregated_for_test`
//!     / writer 既有 `with_strategy` + `with_symbol` 兩 builder）。
//!   - 不依賴 decision_outcomes / lease audit / strategy event 具體實作；經 trait
//!     抽象注入。
//!   - 不依賴 spike feature；production binary 0 mock time 滲透（per AC-5）。
//!
//! 硬邊界:
//!   - 不修 strategy_engine / fill_writer / lease audit 既有邏輯（per dispatch
//!     packet §6.5 反模式 (a)；emitter 只觀測，不修復）。
//!   - sample_interval=300s 走 spec §2.1 規約（不寫死 30s/60s，per packet §6.5
//!     反模式 (b)）。
//!   - emit V106 row 不寫 `engine_mode='live'`（Sprint 2 走 paper/demo/live_demo
//!     only；per §9 共用反模式 (d)）。
//!   - per-(strategy, symbol) 各自 anomaly_id =
//!     `strategy_quality__<strategy>__<symbol>__<metric_name>`（per spec §6.2
//!     line 759）；25 instance × 4 metric × 5 sample window，25 個獨立 cap
//!     window，**不互 cap**（per packet §6.5 反模式 (e) (strategy, symbol) tuple
//!     分隔 cap key）。
//!   - threshold 對齊 M3 spec line 105 / spec §4.3：先 hardcode，Sprint 5 ArcSwap
//!     熱更新 + 30d block bootstrap re-estimate。
//!   - dormant 計時 retain 24h cap window（per dispatch packet §6.5 反模式 (d)
//!     + `project_first_detection_deadlock_pattern` 教訓；SM 內部 amp_cap_entries
//!     已有 24h auto-clear 邏輯，本 emitter 不額外加 anchor）。
//!   - 不 emit `StrategyHealthEvent` 給 M7（per spec §3.4 line 256 + packet §6.5
//!     反模式 (b)；Sprint 5 cascade IMPL 才接）。
//!   - 不直接降 LAL Tier（per spec §3.4 + ADR-0042 + 反模式 (a)；aggregate
//!     DEGRADED 由 §5 cascade 在 Sprint 5 才接 system-level state cascade）。
//!   - 不引 V### / spike / 跨進程 IPC（per packet §6.5 + §9 共用反模式）。
//!   - **edge_score / win_rate / drawdown_pct / sharpe_30d 不在本 Sprint 2
//!     IMPL 範圍**：dispatch prompt 文字版描述提及這些，但 design spec §3.2
//!     StrategyQualitySample 權威 SSOT 為 fill_rate_intent_ratio / slippage_bps_p95
//!     / decision_lease_grant_rate / dormant_minutes / signal_count_24h 5 field；
//!     edge_score 等指標屬 multi-timeframe + cumulative PnL 範疇，per spec §6.5
//!     反模式 (g) 預留 multi-timeframe per ADR-0042 不寫死 single-window。
//!
//! 警告 ── probe 注入式設計：未接線 Wave 2 main.rs 前的 production 行為
//!   `StrategyQualitySourceProbe` trait 走 caller 注入：
//!     - Wave 1 IMPL 不在 main.rs 接 scheduler（per Track A §7 carry-over，Wave 2
//!       後或 Sprint 5 cascade IMPL 才接）。
//!     - 在 Wave 2 wire-up 前若 production 已啟用 `StrategyQualityScheduler`，
//!       caller 端必須注入 placeholder probe（per-(strategy, symbol) 返 OK-band
//!       值：fill=1.0 / slippage=0 / lease=1.0 / dormant=0 / signal=0）；emitter
//!       不能假設 probe 已接 source。
//!     - 若 probe 永遠回 OK-band 值，scheduler 端 5-sample mean = OK，必走 OK
//!       band 不會誤升 WARN/DEGRADED — 風險是「永遠看不到 strategy 真實降階」
//!       而非「誤觸 cascade」。
//!   後續 wire-up 由 TODO follow-up entry 「W-XX-Y Sprint 2 Wave 2 wire-up
//!   StrategyQualitySourceProbe (decision_outcomes fill rate / lease audit grant
//!   rate / dormant minute calc / signal count 24h)（per `docs/agents/
//!   todo-maintenance.md` 被動等待 NDay 守則）」追蹤。

use std::collections::HashMap;
use std::sync::Arc;
use std::time::{Duration, Instant};

use async_trait::async_trait;
use chrono::Utc;
use tokio::sync::Mutex;
use tokio_util::sync::CancellationToken;
use uuid::Uuid;

use super::super::event_bus::{HealthEventBus, HealthStateChangeEvent};
use super::super::metric_emitter::{
    classify_aggregated_for_test, DomainEmitter, EngineModeProvider, MetricSample,
    RollingWindowAggregator,
};
use super::super::writer::{HealthObservationRow, HealthObservationWriter};
use super::super::{HealthDomain, HealthState, HealthStateMachine, M3Error};

// ============================================================
// classify_band threshold helper × 4 (per M3 spec line 105 + dispatch §AC-2)
// ============================================================
//
// 為什麼 threshold 集中於 4 個 pub fn:
//   - Sprint 5 ArcSwap 熱更新時改 4 fn 內部即可，不破壞 caller signature。
//   - scheduler 端 `classify_aggregated` match arm 直接呼此 4 fn（per
//     metric_emitter::classify_aggregated strategy_quality 4 arm dispatch），DRY。
//   - 對齊 Track A `classify_engine_runtime_*` + Track B `classify_pipeline_throughput_*`
//     + Track C `classify_database_pool_*` 同樣 pub fn pattern。
//
// 為什麼 threshold 來源 M3 spec line 105:
//   - 設計階段 SLO table 已確定 4 band 邊界；emitter IMPL 不重設計，僅 literal
//     落地。
//   - per spec §4.3 「Sprint 2 IMPL 先 hardcode threshold；Sprint 5 ArcSwap」。

/// `fill_rate_intent_ratio` classify（per M3 spec line 105 SLO + spec §3.2）。
///
/// ladder (fill rate = filled_count / signal_count；越高越健康):
///   OK       : > 0.80      （filled > 80% intent；正常 trading）
///   WARN     : 0.60 - 0.80  （filled 60-80%；可能 maker reject 增多）
///   DEGRADED : 0.20 - 0.60  （filled 20-60%；spec 「持續 15min」由 SM dwell 守）
///   CRITICAL : < 0.20       （filled < 20%；spec 「dormant > 6h OR fill rate
///                              < 20% OR lease grant < 10%」CRITICAL band）
///
/// 為什麼 4 band:
///   - per M3 spec line 105 SLO table 「per-strategy fill rate > 80% / 60-80%
///     / < 60% 持續 15min / < 20%」literal SSOT；CRITICAL band 直接歸到 fill <
///     20% 對齊。
///   - dwell time「持續 15min」由 SM observe_classified 端 dwell 60s WARN +
///     5min DEGRADED 守（per spec §5.2 ladder dwell），classify helper 不混雜
///     dwell 邏輯（per Track B classify_pipeline_throughput_ws_tick_rate
///     注釋同 reasoning）。
pub fn classify_strategy_quality_fill_rate_intent_ratio(value: f64) -> HealthState {
    if value < 0.20 {
        HealthState::HealthCritical
    } else if value < 0.60 {
        HealthState::HealthDegraded
    } else if value < 0.80 {
        HealthState::HealthWarn
    } else {
        HealthState::HealthOk
    }
}

/// `slippage_bps_p95` classify（per M3 spec line 105 SLO）。
///
/// ladder (slippage = (fill_price - intent_price) / intent_price * 10000；越低
/// 越健康):
///   OK       : < 5 bps      （p95 < 5bps；正常 maker-taker 範圍）
///   WARN     : 5 - 10 bps    （p95 5-10bps；rate-limit 或 spread 寬）
///   DEGRADED : > 10 bps      （p95 > 10bps；spec 「持續 15min」由 SM dwell 守）
///
/// 為什麼不設 CRITICAL band:
///   - M3 spec line 105 CRITICAL band 為「dormant > 6h OR fill rate < 20% OR
///     lease grant < 10%」，未包含 slippage；slippage 是 fill 品質指標，極端
///     大 slippage 本身代表 fill 異常（前置 fill_rate 不會通過 OK 帶），故
///     slippage CRITICAL 由 fill_rate metric 端 fail-loud 觸發即可。
///   - 不誤設 CRITICAL band 避免雙 metric 同時升 CRITICAL 重複觸 cascade
///     （per ADR-0042 反模式 + Track B classify_pipeline_throughput_signal_rate
///     注釋同 reasoning「避兩 metric 重複觸 CRITICAL」）。
pub fn classify_strategy_quality_slippage_bps_p95(value: f64) -> HealthState {
    if value > 10.0 {
        HealthState::HealthDegraded
    } else if value >= 5.0 {
        HealthState::HealthWarn
    } else {
        HealthState::HealthOk
    }
}

/// `decision_lease_grant_rate` classify（per M3 spec line 105 SLO）。
///
/// ladder (lease grant rate = granted_count / requested_count；越高越健康):
///   OK       : > 0.70      （lease grant > 70%；M1 LAL 正常 auto-approve）
///   WARN     : 0.50 - 0.70  （lease grant 50-70%；M1 LAL 退化或 risk gate 收緊）
///   DEGRADED : 0.10 - 0.50  （lease grant 10-50%；spec WARN 連續 → 升 DEGRADED）
///   CRITICAL : < 0.10       （lease grant < 10%；spec line 105 「lease grant
///                              < 10%」CRITICAL band literal）
///
/// 為什麼 4 band:
///   - per M3 spec line 105 SLO table 「per-strategy lease grant > 70% / 50-70%
///     / < 10%」literal SSOT；CRITICAL = lease grant < 10%。
///   - WARN→DEGRADED 中段（10-50%）由 dwell time 守。
pub fn classify_strategy_quality_decision_lease_grant_rate(value: f64) -> HealthState {
    if value < 0.10 {
        HealthState::HealthCritical
    } else if value < 0.50 {
        HealthState::HealthDegraded
    } else if value < 0.70 {
        HealthState::HealthWarn
    } else {
        HealthState::HealthOk
    }
}

/// `dormant_minutes` classify（per M3 spec line 105 SLO）。
///
/// ladder (dormant minutes = 距上次 fill / signal 的分鐘數；越低越健康):
///   OK       : < 60 min     （spec 「per-strategy dormant < 60min」SLO target）
///   WARN     : 60 - 120 min  （持續 1h-2h dormant，可能 IPC 死鎖預警）
///   DEGRADED : 120 - 360 min （持續 2h-6h dormant，strategy 級故障）
///   CRITICAL : > 360 min     （> 6h dormant；spec line 105 「dormant > 6h」
///                              CRITICAL band literal）
///
/// 為什麼 4 band:
///   - per M3 spec line 105 SLO table 「per-strategy dormant < 60min」OK +
///     「dormant > 60min」DEGRADED + 「dormant > 6h」CRITICAL literal SSOT。
///   - WARN 60-120 min 中段為設計安插：spec 60min 即 DEGRADED 過於敏感（一個
///     symbol 連續 1h 無 fill 可能是 regime 切換），補 60-120 min WARN band
///     讓 SM dwell 5min 可緩衝。
///   - 6h CRITICAL band 對齊 first-detection deadlock 反模式預警（per
///     `project_first_detection_deadlock_pattern`）：strategy 持續 6h 不動需
///     operator 介入；SM 端 amp_cap_entries 24h retain 避免永久 dormant lock。
///
/// 為什麼此 helper 入參 u32 而非 f64（對比 fill_rate / slippage / lease_grant
/// 的 f64 入參）:
///   - dormant_minutes 是離散整數量（分鐘計），classify 5-sample mean 後
///     scheduler 端 round 為 u32（per `classify_aggregated` strategy_quality
///     arm dispatch 處 `mean.round() as u32`）；helper 端統一 u32 對齊 Track
///     A `classify_engine_runtime_open_fd_count` 範式。
pub fn classify_strategy_quality_dormant_minutes(value: u32) -> HealthState {
    if value > 360 {
        HealthState::HealthCritical
    } else if value >= 120 {
        HealthState::HealthDegraded
    } else if value >= 60 {
        HealthState::HealthWarn
    } else {
        HealthState::HealthOk
    }
}

// ============================================================
// StrategyQualitySample — 5 field snapshot per (strategy, symbol)
// ============================================================

/// strategy_quality domain 採樣輸出（per spec §3.2 5 field 1:1 對齊）。
///
/// 為什麼此 5 field 設計:
///   - strategy_name + symbol：per-(strategy, symbol) cap key + V106 row 兩列
///     必填（per spec §6.2 anomaly_id 命名規約 + writer with_strategy/with_symbol
///     既有 builder）。
///   - fill_rate_intent_ratio：fill 品質指標（per spec §2.1 line 81）。
///   - slippage_bps_p95：fill 品質指標 p95 維度。
///   - decision_lease_grant_rate：M1 LAL 通過率（per spec §2.1 line 81）。
///   - dormant_minutes：strategy 活性（per spec §2.1 line 81）。
///   - signal_count_24h：telemetry-only；spec §2.1 line 81 列為 metric 但 SLO
///     band 待 Sprint 5 block bootstrap re-estimate，本 Sprint 2 走 fallback
///     OK band（per `metric_emitter::classify_aggregated` 注釋）。
///
/// 為什麼 Clone（不 Copy）:
///   - strategy_name + symbol 兩 String 不是 Copy；其餘 5 個 numeric primitive
///     可 Copy 但整 struct 必 Clone。
///   - emitter sample() 端 clone 後可 Box 走 trait object（per Track B
///     PipelineThroughputSample Clone+Copy 範式不同）。
#[derive(Debug, Clone)]
pub struct StrategyQualitySample {
    pub strategy_name: String,
    pub symbol: String,
    pub fill_rate_intent_ratio: f64,
    pub slippage_bps_p95: f64,
    pub decision_lease_grant_rate: f64,
    pub dormant_minutes: u32,
    pub signal_count_24h: u32,
}

/// MetricSample wrapper：1 sample 投影為 5 metric row；scheduler 端列表處理。
///
/// 為什麼一 emitter sample → 5 MetricSample row:
///   - V106 row 是 per-metric_name 一條（per ADR-0042 Decision 4 anomaly_id =
///     domain × metric_name × strategy × symbol）；5 metric → 5 row × per-
///     (strategy, symbol) 各自獨立 SM transition + cap window。
///   - 對齊 Track A/B/C `into_metric_rows` 範式；scaffold reuse。
///
/// 為什麼 strategy_name + symbol 內嵌每 row:
///   - V106 schema 設計 strategy_name + symbol 兩列獨立可寫；scheduler 端
///     `run_strategy_quality_loop` 依此兩 field 走 `row.with_strategy(...)
///     .with_symbol(...)` 兩 builder（writer 既有 API）。
///   - 不擴 `MetricSample` trait 加 `strategy_label()` accessor 因會動 Wave 1
///     scaffold（per packet 反模式禁）；改在 row IMPL 端走 helper。
#[derive(Debug, Clone)]
pub struct StrategyQualityMetricRow {
    pub strategy_name: String,
    pub symbol: String,
    pub metric_name: &'static str,
    pub value: f64,
    pub band: HealthState,
}

impl MetricSample for StrategyQualityMetricRow {
    fn metric_name(&self) -> &'static str {
        self.metric_name
    }

    fn numeric_value(&self) -> f64 {
        self.value
    }

    fn classify_band(&self) -> HealthState {
        self.band
    }
}

impl StrategyQualitySample {
    /// 將 sample 展為 5 個 metric row（每 metric_name 一條；per Track A 範式）。
    ///
    /// 為什麼此設計:
    ///   - 對齊 V106 schema：1 row = 1 metric_name + 1 (strategy, symbol)；
    ///     不展平就無法各 metric 獨立 classify_band + SM transition（per
    ///     ADR-0042 Decision 4 anomaly_id 命名規約 + spec §6.2 line 759
    ///     `strategy_quality__<strategy>__<symbol>__fill_rate_intent_ratio`）。
    pub fn into_metric_rows(self) -> Vec<StrategyQualityMetricRow> {
        let fill_band =
            classify_strategy_quality_fill_rate_intent_ratio(self.fill_rate_intent_ratio);
        let slippage_band = classify_strategy_quality_slippage_bps_p95(self.slippage_bps_p95);
        let lease_band = classify_strategy_quality_decision_lease_grant_rate(
            self.decision_lease_grant_rate,
        );
        let dormant_band = classify_strategy_quality_dormant_minutes(self.dormant_minutes);
        // signal_count_24h 走 OK band（telemetry-only；per spec §3.2 注 +
        // metric_emitter::classify_aggregated fallback path 注釋；Sprint 5 接
        // block bootstrap threshold 才能 classify）。
        let signal_band = HealthState::HealthOk;

        vec![
            StrategyQualityMetricRow {
                strategy_name: self.strategy_name.clone(),
                symbol: self.symbol.clone(),
                metric_name: "fill_rate_intent_ratio",
                value: self.fill_rate_intent_ratio,
                band: fill_band,
            },
            StrategyQualityMetricRow {
                strategy_name: self.strategy_name.clone(),
                symbol: self.symbol.clone(),
                metric_name: "slippage_bps_p95",
                value: self.slippage_bps_p95,
                band: slippage_band,
            },
            StrategyQualityMetricRow {
                strategy_name: self.strategy_name.clone(),
                symbol: self.symbol.clone(),
                metric_name: "decision_lease_grant_rate",
                value: self.decision_lease_grant_rate,
                band: lease_band,
            },
            StrategyQualityMetricRow {
                strategy_name: self.strategy_name.clone(),
                symbol: self.symbol.clone(),
                metric_name: "dormant_minutes",
                value: self.dormant_minutes as f64,
                band: dormant_band,
            },
            StrategyQualityMetricRow {
                strategy_name: self.strategy_name,
                symbol: self.symbol,
                metric_name: "signal_count_24h",
                value: self.signal_count_24h as f64,
                band: signal_band,
            },
        ]
    }
}

// ============================================================
// StrategyQualitySourceProbe trait — per-(strategy, symbol) 採樣源注入點
// ============================================================

/// per-(strategy, symbol) 採樣源抽象 trait；emitter 只呼此 trait 取值，**不修**
/// strategy_engine / fill_writer / lease audit 既有邏輯（per packet §6.5 反
/// 模式 (a)）。
///
/// 為什麼 trait 注入而非直接 import:
///   - emitter「只觀測，不修」：scheduler struct 持有 trait object，main.rs
///     接線時注入真實 decision_outcomes / lease audit / strategy event source；
///     test 注入 mock。
///   - 對齊 Track B `PipelineThroughputSourceProbe` trait 注入範式；不引入
///     5 closure 散布的反模式。
///   - 對齊 spec §3 D1 emitter 採樣邊界：emitter 只負責採樣 + classify，不
///     負責 metric collection 機制。
///
/// 接線分工（Wave 2 main.rs 後或 Sprint 5 cascade IMPL 才接）:
///   - `current_fill_rate_intent_ratio(strategy, symbol)`：接 `decision_outcomes`
///     表 24h 窗 `SUM(filled_count) / SUM(signal_count)` per (strategy, symbol)。
///   - `current_slippage_bps_p95(strategy, symbol)`：接 `decision_outcomes`
///     24h 窗 `percentile_cont(0.95)` of `slippage_bps`。
///   - `current_decision_lease_grant_rate(strategy, symbol)`：接 lease audit
///     `granted / requested` per (strategy, symbol)。
///   - `current_dormant_minutes(strategy, symbol)`：接 `decision_outcomes`
///     `now - last_fill_at` per (strategy, symbol)。
///   - `current_signal_count_24h(strategy, symbol)`：接 strategy event count
///     24h 累計 per (strategy, symbol)。
///
/// 硬邊界:
///   - probe 失敗（如 source 還沒接線）返 OK-band 值（fill=1.0 / slippage=0 /
///     lease=1.0 / dormant=0 / signal=0）不 panic；emitter 端視 OK 為 OK band，
///     不誤升級（per `feedback_no_dead_params` fail-soft 對齊）。
///   - test 注入 mock 走實作；production 接線責任 Wave 2+ 由 main.rs caller 補。
pub trait StrategyQualitySourceProbe: Send + Sync {
    /// 採當前 fill rate (filled_count / signal_count, 24h window)。
    fn current_fill_rate_intent_ratio(&self, strategy: &str, symbol: &str) -> f64;
    /// 採當前 slippage p95 (bps, 24h window)。
    fn current_slippage_bps_p95(&self, strategy: &str, symbol: &str) -> f64;
    /// 採當前 lease grant rate (granted / requested, 24h window)。
    fn current_decision_lease_grant_rate(&self, strategy: &str, symbol: &str) -> f64;
    /// 採當前 dormant minutes (now - last_fill_at)。
    fn current_dormant_minutes(&self, strategy: &str, symbol: &str) -> u32;
    /// 採當前 24h signal count (strategy event 24h 累計)。
    fn current_signal_count_24h(&self, strategy: &str, symbol: &str) -> u32;
}

// ============================================================
// StrategyQualityEmitter — Track E IMPL
// ============================================================

/// strategy_quality domain emitter；5min sample；經 trait 抽象觀測 per-(strategy,
/// symbol) 5 metric。
///
/// 為什麼 Arc<dyn ...> + Vec<(String, String)> pair list:
///   - source probe 為 Arc<dyn ...>，跨 tokio task spawn 邊界需 Send + Sync。
///   - pair list 為 caller 端配置注入（25 pair 默認；可由 main.rs 從 strategy
///     config 動態載入；per packet §6.5 反模式 (d) 不硬編碼 strategy/symbol）。
///   - sample() 端對 pair list 全部跑採樣返多個 (strategy, symbol) row（5 metric
///     × N pair = 5N row）。
///
/// 為什麼 sample 返多 pair × 5 metric 而非單 pair:
///   - DomainEmitter trait `sample()` 返 `Vec<Box<dyn MetricSample>>`；caller 端
///     可平鋪所有 pair × metric。
///   - scheduler 端依 row.strategy_name + row.symbol 走對應 (strategy, symbol)
///     SM observe_classified；25 instance SM 並行不衝突。
pub struct StrategyQualityEmitter {
    source: Arc<dyn StrategyQualitySourceProbe>,
    /// per-(strategy, symbol) pair 列表；caller 端注入（default 25 pair）。
    /// 為什麼 caller 注入而非硬編碼:
    ///   per packet §6.5 反模式 (d)：strategy / symbol 名硬編碼禁；main.rs
    ///   從 strategy_config 動態載入。
    pairs: Vec<(String, String)>,
}

impl StrategyQualityEmitter {
    /// 建立 emitter；caller 注入 source probe + (strategy, symbol) pair list。
    ///
    /// 為什麼 generic + Arc::new:
    ///   - test 注入 in-line struct impl trait 不需 caller 端 Arc::new。
    ///   - production main.rs 注入 Arc<RealSource> 由 generic 自動接受。
    pub fn new<S>(source: S, pairs: Vec<(String, String)>) -> Self
    where
        S: StrategyQualitySourceProbe + 'static,
    {
        Self {
            source: Arc::new(source),
            pairs,
        }
    }

    /// 採當前所有 (strategy, symbol) pair × 5 metric snapshot（test 可直接呼此
    /// helper）。
    ///
    /// 為什麼 &self（對比 Track A `sample_now` mut self）:
    ///   - trait probe 是純讀 accessor 不需 mut；sysinfo 不在本 emitter scope。
    pub fn sample_now(&self) -> Result<Vec<StrategyQualitySample>, M3Error> {
        let samples: Vec<StrategyQualitySample> = self
            .pairs
            .iter()
            .map(|(strategy, symbol)| StrategyQualitySample {
                strategy_name: strategy.clone(),
                symbol: symbol.clone(),
                fill_rate_intent_ratio: self
                    .source
                    .current_fill_rate_intent_ratio(strategy, symbol),
                slippage_bps_p95: self.source.current_slippage_bps_p95(strategy, symbol),
                decision_lease_grant_rate: self
                    .source
                    .current_decision_lease_grant_rate(strategy, symbol),
                dormant_minutes: self.source.current_dormant_minutes(strategy, symbol),
                signal_count_24h: self.source.current_signal_count_24h(strategy, symbol),
            })
            .collect();
        Ok(samples)
    }

    /// pair list accessor — `StrategyQualityScheduler` 端走 pair 初始化 25
    /// instance SM 用。
    pub fn pairs(&self) -> &[(String, String)] {
        &self.pairs
    }
}

#[async_trait]
impl DomainEmitter for StrategyQualityEmitter {
    fn domain(&self) -> HealthDomain {
        HealthDomain::StrategyQuality
    }

    fn sample_interval_sec(&self) -> u64 {
        // per spec §2.1 line 245：strategy_quality 5min sample（300s；不可寫死
        // 30s/60s per packet §6.5 反模式 (b)）。
        300
    }

    async fn sample(&mut self) -> Result<Vec<Box<dyn MetricSample>>, M3Error> {
        let snapshots = self.sample_now()?;
        let rows: Vec<Box<dyn MetricSample>> = snapshots
            .into_iter()
            .flat_map(|s| s.into_metric_rows())
            .map(|r| Box::new(r) as Box<dyn MetricSample>)
            .collect();
        Ok(rows)
    }
}

// ============================================================
// StrategyQualityScheduler — 獨立 scheduler，25 instance SM + aggregate SM
// ============================================================

/// strategy_quality 獨立 scheduler（per spec §4.4 line 638-643）；不沿用
/// `MetricEmitterScheduler::run_domain_loop` 因 25 instance per-(strategy,
/// symbol) SM 與 single-SM 路徑不同。
///
/// 為什麼獨立 scheduler 而非合入 `MetricEmitterScheduler`:
///   - `MetricEmitterScheduler` 內部 `state_machines: HashMap<(HealthDomain,
///     String), HealthStateMachine>` 是 (domain, metric_name) 鍵；strategy_quality
///     需要 (domain, metric_name, strategy, symbol) 4-tuple 鍵，會破壞 scheduler
///     既有 hash key shape。
///   - per spec §4.4 line 638-643 明文給出獨立 `StrategyQualityScheduler` struct；
///     本 IMPL 1:1 對齊 spec。
///   - 沿用 trait + aggregator + writer + event_bus + SM 等 Wave 1 scaffold 組件
///     不衝突（per dispatch packet §6.5 反模式 (c) 沿用 Track A scaffold 解釋）。
///
/// per-(strategy, symbol) SM 25 instance + aggregate SM:
///   - 25 個 SM（5 strategy × 5 symbol typical）各自獨立 dwell / cap window；
///     互不耦合（per packet §6.5 反模式 (e) 25 instance SM 必 (strategy, symbol)
///     tuple 分隔 cap key）。
///   - 1 個 aggregate SM 由 scheduler 端每次 sample 後重算「degraded_count /
///     total_count」決定升 / 降階。
pub struct StrategyQualityScheduler {
    emitter: StrategyQualityEmitter,
    /// 25 instance per-(strategy, symbol) × per-metric_name SM map。
    ///
    /// 為什麼 4-tuple key (strategy, symbol, metric_name, 索引位):
    ///   - per ADR-0042 Decision 4 anomaly_id 命名「domain × metric × strategy
    ///     × symbol」；每 metric 一個 SM 才能各自獨立 ladder transition。
    ///   - 25 pair × 4 active band metric = 100 個 SM 實例（dormant /
    ///     fill_rate / slippage / lease_grant 各 25 SM；signal_count_24h 走
    ///     fallback OK band 不需 SM）。
    ///   - HashMap lookup O(1)，scheduler hot path 不犯 contention（每 SM 各自
    ///     Mutex 鎖；不同 SM 不互鎖）。
    per_pair_sms: HashMap<(String, String, String), Arc<Mutex<HealthStateMachine>>>,
    /// per-(strategy, symbol) × per-metric_name 5-sample 滑窗 aggregator。
    aggregators: HashMap<(String, String, String), Arc<Mutex<RollingWindowAggregator>>>,
    /// aggregate SM：scheduler 端每次 sample 後重算「degraded_count /
    /// total_count > 0.40 → DEGRADED」決定升 / 降階。
    aggregate_sm: Arc<Mutex<HealthStateMachine>>,
    writer: Arc<dyn HealthObservationWriter>,
    event_bus: Arc<HealthEventBus>,
    engine_mode: EngineModeProvider,
}

impl StrategyQualityScheduler {
    /// 建立 scheduler；caller 端注入 emitter + writer + event bus + mode provider。
    ///
    /// 為什麼此初始化:
    ///   - emitter 內含 pair list；scheduler 依此構建 per-pair SM map（25 個
    ///     SM × 4 band metric = 100 個 SM 實例）。
    ///   - aggregate SM 單獨建構，初始 state = OK；rule 0.40 由 run loop 端計算。
    pub fn new(
        emitter: StrategyQualityEmitter,
        writer: Arc<dyn HealthObservationWriter>,
        event_bus: Arc<HealthEventBus>,
        engine_mode: EngineModeProvider,
    ) -> Self {
        let pairs = emitter.pairs().to_vec();

        // 預建 per-pair × per-metric SM + aggregator（4 個 band metric ×
        // pair 數 = e.g. 25 × 4 = 100 個 SM）。
        // 為什麼 pre-create:
        //   scheduler hot path 不再 lazy entry（per Track A run_domain_loop
        //   範式 lazy entry 是 fine 因 single SM map；本 scheduler 25 pair ×
        //   4 metric 全 sample tick 必觸所有 key，pre-create 避 race）。
        let mut per_pair_sms = HashMap::new();
        let mut aggregators = HashMap::new();
        for (strategy, symbol) in &pairs {
            for metric in
                ["fill_rate_intent_ratio", "slippage_bps_p95", "decision_lease_grant_rate", "dormant_minutes"]
            {
                let key = (strategy.clone(), symbol.clone(), metric.to_string());
                per_pair_sms.insert(
                    key.clone(),
                    Arc::new(Mutex::new(HealthStateMachine::new(
                        HealthDomain::StrategyQuality,
                    ))),
                );
                // metric_name 是 &'static str，可直接給 RollingWindowAggregator::new。
                // 為什麼 4 個 'static str literal arm:
                //   `metric_name` 在 `RollingWindowAggregator::new` 簽名為
                //   `&'static str`，每 metric 必各自 literal 對齊；避動態 leak。
                let static_metric: &'static str = match metric {
                    "fill_rate_intent_ratio" => "fill_rate_intent_ratio",
                    "slippage_bps_p95" => "slippage_bps_p95",
                    "decision_lease_grant_rate" => "decision_lease_grant_rate",
                    "dormant_minutes" => "dormant_minutes",
                    _ => unreachable!(),
                };
                aggregators.insert(
                    key,
                    Arc::new(Mutex::new(RollingWindowAggregator::new(static_metric))),
                );
            }
        }
        let aggregate_sm = Arc::new(Mutex::new(HealthStateMachine::new(
            HealthDomain::StrategyQuality,
        )));
        Self {
            emitter,
            per_pair_sms,
            aggregators,
            aggregate_sm,
            writer,
            event_bus,
            engine_mode,
        }
    }

    /// 為 test 開放 per-pair SM 數量讀取（25 × 4 = 100 instance）。
    pub fn per_pair_sm_count(&self) -> usize {
        self.per_pair_sms.len()
    }

    /// 為 test 開放 aggregate SM accessor。
    pub fn aggregate_sm(&self) -> &Arc<Mutex<HealthStateMachine>> {
        &self.aggregate_sm
    }

    /// 跑 scheduler；caller 端 spawn 為 tokio task；cancel 時 graceful shutdown。
    ///
    /// 為什麼 cancel_token 而非 JoinHandle::abort:
    ///   - graceful shutdown：scheduler 在 tick 邊界檢查 cancel，避中斷 INSERT
    ///     寫到一半（per Track A scheduler 範式）。
    pub async fn run(self, cancel_token: CancellationToken) {
        // 為什麼 emitter 不需 `mut`（per cargo lint）:
        //   `sample_now(&self)` 為 &self；emitter 在 run loop 內走 read-only
        //   accessor + trait probe 採樣。對比 Track A `EngineRuntimeEmitter`
        //   需 `mut` 因 sysinfo refresh_processes 為 mut；本 emitter 走 trait
        //   probe 純讀不需 mut。
        let emitter = self.emitter;
        let interval_secs = emitter.sample_interval_sec();
        let mut interval = tokio::time::interval(Duration::from_secs(interval_secs));
        interval.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);

        loop {
            tokio::select! {
                _ = interval.tick() => {
                    // ----------------------------------------
                    // Step 1: emitter.sample() fail-soft
                    // ----------------------------------------
                    let samples = match emitter.sample_now() {
                        Ok(s) => s,
                        Err(e) => {
                            // fail-closed: 寫 V106 row state=OK + evidence_json
                            // sample_error；對齊 Track A scheduler 範式。
                            let mode = (self.engine_mode)();
                            let _ = self.writer
                                .write_sample_error(
                                    HealthDomain::StrategyQuality,
                                    "(sample)",
                                    &e,
                                    &mode,
                                )
                                .await;
                            continue;
                        }
                    };

                    let mode = (self.engine_mode)();
                    let observed_at = Utc::now();
                    let now_instant = Instant::now();

                    // ----------------------------------------
                    // Step 2: per-pair × per-metric 採樣 + classify + SM
                    //         observe + V106 row INSERT
                    // ----------------------------------------
                    //
                    // 為什麼此設計:
                    //   per-pair sample 拆 5 metric row，4 個有 band metric 各
                    //   走自己的 SM；signal_count_24h telemetry-only 直接寫
                    //   row 不經 SM。
                    process_pair_samples(
                        samples,
                        &self.per_pair_sms,
                        &self.aggregators,
                        &self.writer,
                        &self.event_bus,
                        &mode,
                        observed_at,
                        now_instant,
                    )
                    .await;

                    // ----------------------------------------
                    // Step 3: aggregate SM 重算 degraded_count / total_count
                    // ----------------------------------------
                    //
                    // 為什麼此設計:
                    //   per spec §3.4 line 211 + §4.4 line 646-651：aggregate
                    //   rule = degraded_count / total_count > 0.40 → DEGRADED；
                    //   每 sample 後重算，依當前 25 pair × 4 band metric SM
                    //   state 計算 degraded_count。
                    aggregate_observe(
                        &self.per_pair_sms,
                        &self.aggregate_sm,
                        &self.writer,
                        &self.event_bus,
                        &mode,
                        observed_at,
                        now_instant,
                    )
                    .await;
                }
                _ = cancel_token.cancelled() => break,
            }
        }
    }
}

/// 處理單 sample tick 的所有 (strategy, symbol) × metric → V106 row 流程。
///
/// 為什麼抽 helper 而非 inline:
///   - 25 pair × 4 metric = 100 個 SM observe + V106 row INSERT 邏輯複雜，
///     抽 helper 後 test 端可直接呼驗。
///   - SM lock 不跨 await 範式（per Track A round 2 MEDIUM-1 fix）：drop guard
///     後再 await writer。
async fn process_pair_samples(
    samples: Vec<StrategyQualitySample>,
    per_pair_sms: &HashMap<(String, String, String), Arc<Mutex<HealthStateMachine>>>,
    aggregators: &HashMap<(String, String, String), Arc<Mutex<RollingWindowAggregator>>>,
    writer: &Arc<dyn HealthObservationWriter>,
    event_bus: &Arc<HealthEventBus>,
    mode: &str,
    observed_at: chrono::DateTime<chrono::Utc>,
    now_instant: Instant,
) {
    for sample in samples {
        let strategy = sample.strategy_name.clone();
        let symbol = sample.symbol.clone();
        let rows = sample.into_metric_rows();

        for row in rows {
            let metric_name = row.metric_name;
            let value = row.value;
            let instant_band = row.band;

            // signal_count_24h 走 fallback OK 直接 row INSERT，不經 SM
            // observe（per spec §3.2 注 + metric_emitter::classify_aggregated
            // 注釋）。
            if metric_name == "signal_count_24h" {
                let v106_row = HealthObservationRow::new(
                    HealthDomain::StrategyQuality,
                    metric_name.to_string(),
                    HealthState::HealthOk,
                    value,
                    0,
                    mode.to_string(),
                )
                .with_strategy(strategy.clone())
                .with_symbol(symbol.clone());
                let mut v106_row = v106_row;
                v106_row.observed_at = observed_at;
                let _ = writer.write_observation(v106_row).await;
                continue;
            }

            // ----------------------------------------
            // 4 band metric：走 5-sample mean classify + SM observe_classified
            // ----------------------------------------
            let key = (strategy.clone(), symbol.clone(), metric_name.to_string());
            let agg = match aggregators.get(&key) {
                Some(a) => a,
                None => continue,  // 防禦：未預建 key（不應發生）；fail-soft skip
            };
            let band_from_mean = {
                let mut guard = agg.lock().await;
                guard.push(value);
                if guard.current_window_size() < 5 {
                    instant_band
                } else {
                    classify_aggregated_for_test(
                        HealthDomain::StrategyQuality,
                        metric_name,
                        guard.mean().unwrap(),
                    )
                }
            };

            let sm = match per_pair_sms.get(&key) {
                Some(s) => s,
                None => continue,  // 防禦同上
            };

            // SM observe_classified：anomaly_id = strategy_quality__<strategy>__
            // <symbol>__<metric_name>（per spec §6.2 line 759）。
            //
            // 為什麼 anomaly_id 內嵌 strategy + symbol:
            //   25 instance SM 各自獨立 cap window；anomaly_id 走 (strategy,
            //   symbol, metric_name) 三鍵分隔，per packet §6.5 反模式 (e) 25
            //   instance SM 必 (strategy, symbol) tuple 分隔 cap key。
            let anomaly_id = format!(
                "strategy_quality__{}__{}__{}",
                strategy, symbol, metric_name
            );

            // SM lock 不跨 await 範式（per Track A round 2 MEDIUM-1 fix）：
            //   (a) collect SM 結果到 local + (b) drop guard + (c) writer 才 await。
            let (prev_state, current_state, current_count, fired, dwell_secs) = {
                let mut sm_guard = sm.lock().await;
                let prev = sm_guard.current_state();
                let observe_result =
                    sm_guard.observe_classified(band_from_mean, &anomaly_id, now_instant);
                let (fired, dwell) = match observe_result {
                    Ok(true) => (true, sm_guard.last_transition_dwell_secs()),
                    Ok(false) => (false, 0),
                    Err(_) => (false, 0),
                };
                let current = sm_guard.current_state();
                let count = sm_guard.amplification_loop_24h_count();
                (prev, current, count, fired, dwell)
            };

            // V106 row INSERT
            let mut v106_row = HealthObservationRow::new(
                HealthDomain::StrategyQuality,
                metric_name.to_string(),
                current_state,
                value,
                current_count as i32,
                mode.to_string(),
            )
            .with_strategy(strategy.clone())
            .with_symbol(symbol.clone());
            v106_row.observed_at = observed_at;
            if fired {
                v106_row = v106_row.with_transition(prev_state, dwell_secs as i32);
            }
            let _ = writer.write_observation(v106_row).await;

            // event_bus publish (Sprint 5 cascade subscribe 預埋)
            if fired {
                let event = HealthStateChangeEvent {
                    transition_id: Uuid::new_v4(),
                    domain: HealthDomain::StrategyQuality,
                    old_state: prev_state,
                    new_state: current_state,
                    observed_at: observed_at.into(),
                    anomaly_id: anomaly_id.clone(),
                    amplification_loop_24h_count: current_count,
                    reason_summary: format!(
                        "{} crossed band on 5-sample mean → {} (strategy={}, symbol={})",
                        metric_name,
                        current_state.as_str(),
                        strategy,
                        symbol,
                    ),
                };
                event_bus.publish(event);
            }
        }
    }
}

/// aggregate SM 重算：per spec §3.4 + §4.4 line 646-651 rule = degraded_count /
/// total_count > 0.40 → DEGRADED。
///
/// 為什麼此設計:
///   - aggregate SM 是 system-level 觀測；rule 由 scheduler 端每 sample 後計算。
///   - degraded_count = SM 當前 state ∈ {DEGRADED, CRITICAL} 的 SM 計數；
///     total_count = per_pair_sms.len()（25 pair × 4 metric = 100；test 場景
///     可能更少）。
///   - 走 observe_classified 入口讓 aggregate SM 也守 dwell time + amp cap
///     range（per spec §5.2 ladder dwell；aggregate SM 與 per-pair SM 共用
///     `HealthStateMachine` impl）。
///
/// aggregate band classify rule:
///   - degraded_ratio > 0.40 → DEGRADED band
///   - degraded_ratio > 0 但 ≤ 0.40 → WARN band（per Track B classify ladder
///     範式：非 0 即非 OK，預留 dwell 觀測；但本 spec §3.4 只說 > 0.40 升
///     DEGRADED，0 ≤ ratio ≤ 0.40 保 OK 即可）
///   - degraded_ratio = 0 → OK band
///
/// 為什麼不在 SM 升 WARN 中段（per spec §3.4 line 211 literal SSOT）:
///   spec 只說 > 40% 才升 system-level DEGRADED；< 40% 留 OK band，不誤升
///   WARN 過敏感。
async fn aggregate_observe(
    per_pair_sms: &HashMap<(String, String, String), Arc<Mutex<HealthStateMachine>>>,
    aggregate_sm: &Arc<Mutex<HealthStateMachine>>,
    writer: &Arc<dyn HealthObservationWriter>,
    event_bus: &Arc<HealthEventBus>,
    mode: &str,
    observed_at: chrono::DateTime<chrono::Utc>,
    now_instant: Instant,
) {
    // Step 1: 統計 degraded_count + total_count
    let total_count = per_pair_sms.len() as f64;
    if total_count == 0.0 {
        return;  // 防禦：空 pair list 不做任何事
    }
    let mut degraded_count = 0u32;
    for sm in per_pair_sms.values() {
        let guard = sm.lock().await;
        let state = guard.current_state();
        if state == HealthState::HealthDegraded || state == HealthState::HealthCritical {
            degraded_count += 1;
        }
    }
    let degraded_ratio = degraded_count as f64 / total_count;

    // Step 2: classify aggregate band
    let aggregate_band = if degraded_ratio > 0.40 {
        HealthState::HealthDegraded
    } else {
        HealthState::HealthOk
    };

    // Step 3: aggregate SM observe_classified
    //
    // 為什麼 anomaly_id 帶 target band suffix（per spec amp cap 24h-suppression
    // 設計 + V106 spec §1.1 line 77）:
    //   - SM `try_transition_with_cap` 內部按 anomaly_id 24h cap window
    //     suppress。aggregate SM 走 ladder OK→WARN→DEGRADED 跨多次 sample；若
    //     全用同 anomaly_id「strategy_quality__aggregate」，第一次 OK→WARN
    //     fire 後 24h 內 WARN→DEGRADED 會被 same-anomaly cap suppress，aggregate
    //     SM 永困 WARN 不再升。
    //   - 改 per-target-state anomaly_id（aggregate__warn / aggregate__degraded /
    //     aggregate__critical），每次 transition 走獨立 cap window；對齊 Track C
    //     test_sprint2_ladder_database_pool 範例「新 anomaly_id 避同 id cap
    //     suppress」（line 437-438）。
    //   - 此設計仍受 SM 端 cap count >= 2 fail-closed reject 約束（不繞 V106
    //     spec §1.1 line 77）。
    let aggregate_anomaly_id = match aggregate_band {
        HealthState::HealthOk => "strategy_quality__aggregate__ok",
        HealthState::HealthWarn => "strategy_quality__aggregate__warn",
        HealthState::HealthDegraded => "strategy_quality__aggregate__degraded",
        HealthState::HealthCritical => "strategy_quality__aggregate__critical",
    };
    let anomaly_id = aggregate_anomaly_id;
    let (prev_state, current_state, current_count, fired, dwell_secs) = {
        let mut sm_guard = aggregate_sm.lock().await;
        let prev = sm_guard.current_state();
        let observe_result =
            sm_guard.observe_classified(aggregate_band, anomaly_id, now_instant);
        let (fired, dwell) = match observe_result {
            Ok(true) => (true, sm_guard.last_transition_dwell_secs()),
            Ok(false) => (false, 0),
            Err(_) => (false, 0),
        };
        let current = sm_guard.current_state();
        let count = sm_guard.amplification_loop_24h_count();
        (prev, current, count, fired, dwell)
    };

    // Step 4: V106 row INSERT — aggregate row 用 `metric_name="aggregate"`
    // 區隔於 4 band metric row。
    //
    // 為什麼用 metric_name="aggregate":
    //   - V106 schema 沒明文限制 metric_name enum；aggregate row 由 metric_name
    //     語意分隔 per-pair row；query 端 `WHERE metric_name='aggregate'` 可
    //     直接抓 system-level aggregate state。
    //   - 不寫 strategy_name + symbol 兩列（aggregate 是 system-level，不歸
    //     特定 strategy / symbol）。
    let mut v106_row = HealthObservationRow::new(
        HealthDomain::StrategyQuality,
        "aggregate".to_string(),
        current_state,
        degraded_ratio,
        current_count as i32,
        mode.to_string(),
    );
    v106_row.observed_at = observed_at;
    if fired {
        v106_row = v106_row.with_transition(prev_state, dwell_secs as i32);
    }
    // evidence_json 帶 degraded_count + total_count audit trail
    v106_row = v106_row.with_evidence(serde_json::json!({
        "degraded_count": degraded_count,
        "total_count": total_count as u32,
        "degraded_ratio": degraded_ratio,
        "aggregate_rule": "degraded_ratio > 0.40 → DEGRADED",
    }));
    let _ = writer.write_observation(v106_row).await;

    // Step 5: event_bus publish aggregate SM fire
    if fired {
        let event = HealthStateChangeEvent {
            transition_id: Uuid::new_v4(),
            domain: HealthDomain::StrategyQuality,
            old_state: prev_state,
            new_state: current_state,
            observed_at: observed_at.into(),
            anomaly_id: anomaly_id.to_string(),
            amplification_loop_24h_count: current_count,
            reason_summary: format!(
                "aggregate ratio {:.3} crossed 0.40 → {} (degraded={}/{})",
                degraded_ratio,
                current_state.as_str(),
                degraded_count,
                total_count as u32,
            ),
        };
        event_bus.publish(event);
    }
}

// ============================================================
// 測試
// ============================================================

#[cfg(test)]
mod tests {
    use super::*;
    use crate::health::writer::InMemoryHealthObservationWriter;

    /// 內嵌 mock source；test fixture 用。
    ///
    /// 為什麼 HashMap<(String, String), 5-tuple>:
    ///   - 25 pair test 場景需 per-pair 不同 sample 值；HashMap 便利 test 端
    ///     注入特定 (strategy, symbol) 對應值。
    struct StubSource {
        values: HashMap<(String, String), (f64, f64, f64, u32, u32)>,
    }

    impl StubSource {
        fn new() -> Self {
            Self {
                values: HashMap::new(),
            }
        }

        // 為什麼 #[allow(dead_code)]: 此 helper 預留給 future per-pair 注入測試
        // 用；當前 lib mod test 走 default OK-band 值（unwrap_or 走 1.0/0.0），
        // 未直接呼 set。lint 不應誤刪 future test 預留 helper。
        #[allow(dead_code)]
        fn set(
            &mut self,
            strategy: &str,
            symbol: &str,
            fill: f64,
            slippage: f64,
            lease: f64,
            dormant: u32,
            signal: u32,
        ) {
            self.values.insert(
                (strategy.to_string(), symbol.to_string()),
                (fill, slippage, lease, dormant, signal),
            );
        }
    }

    impl StrategyQualitySourceProbe for StubSource {
        fn current_fill_rate_intent_ratio(&self, strategy: &str, symbol: &str) -> f64 {
            self.values
                .get(&(strategy.to_string(), symbol.to_string()))
                .map(|v| v.0)
                .unwrap_or(1.0)
        }
        fn current_slippage_bps_p95(&self, strategy: &str, symbol: &str) -> f64 {
            self.values
                .get(&(strategy.to_string(), symbol.to_string()))
                .map(|v| v.1)
                .unwrap_or(0.0)
        }
        fn current_decision_lease_grant_rate(&self, strategy: &str, symbol: &str) -> f64 {
            self.values
                .get(&(strategy.to_string(), symbol.to_string()))
                .map(|v| v.2)
                .unwrap_or(1.0)
        }
        fn current_dormant_minutes(&self, strategy: &str, symbol: &str) -> u32 {
            self.values
                .get(&(strategy.to_string(), symbol.to_string()))
                .map(|v| v.3)
                .unwrap_or(0)
        }
        fn current_signal_count_24h(&self, strategy: &str, symbol: &str) -> u32 {
            self.values
                .get(&(strategy.to_string(), symbol.to_string()))
                .map(|v| v.4)
                .unwrap_or(0)
        }
    }

    fn make_25_pairs() -> Vec<(String, String)> {
        // 模擬 5 strategy × 5 symbol = 25 pair（per spec §2.1 line 232）。
        let strategies = ["grid", "ma", "bb_breakout", "bb_reversion", "funding_arb"];
        let symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"];
        let mut pairs = Vec::new();
        for s in &strategies {
            for sym in &symbols {
                pairs.push((s.to_string(), sym.to_string()));
            }
        }
        pairs
    }

    // -----------------------------------------------------------
    // classify_band thresholds
    // -----------------------------------------------------------

    #[test]
    fn test_classify_fill_rate_intent_ratio_thresholds() {
        // OK band: > 0.80
        assert_eq!(
            classify_strategy_quality_fill_rate_intent_ratio(0.80),
            HealthState::HealthOk
        );
        assert_eq!(
            classify_strategy_quality_fill_rate_intent_ratio(1.0),
            HealthState::HealthOk
        );
        // WARN band: 0.60 - 0.80
        assert_eq!(
            classify_strategy_quality_fill_rate_intent_ratio(0.79),
            HealthState::HealthWarn
        );
        assert_eq!(
            classify_strategy_quality_fill_rate_intent_ratio(0.60),
            HealthState::HealthWarn
        );
        // DEGRADED band: 0.20 - 0.60
        assert_eq!(
            classify_strategy_quality_fill_rate_intent_ratio(0.59),
            HealthState::HealthDegraded
        );
        assert_eq!(
            classify_strategy_quality_fill_rate_intent_ratio(0.20),
            HealthState::HealthDegraded
        );
        // CRITICAL band: < 0.20
        assert_eq!(
            classify_strategy_quality_fill_rate_intent_ratio(0.19),
            HealthState::HealthCritical
        );
        assert_eq!(
            classify_strategy_quality_fill_rate_intent_ratio(0.0),
            HealthState::HealthCritical
        );
    }

    #[test]
    fn test_classify_slippage_bps_p95_thresholds() {
        // OK band: < 5 bps
        assert_eq!(
            classify_strategy_quality_slippage_bps_p95(0.0),
            HealthState::HealthOk
        );
        assert_eq!(
            classify_strategy_quality_slippage_bps_p95(4.99),
            HealthState::HealthOk
        );
        // WARN band: 5 - 10 bps
        assert_eq!(
            classify_strategy_quality_slippage_bps_p95(5.0),
            HealthState::HealthWarn
        );
        assert_eq!(
            classify_strategy_quality_slippage_bps_p95(10.0),
            HealthState::HealthWarn
        );
        // DEGRADED band: > 10 bps
        assert_eq!(
            classify_strategy_quality_slippage_bps_p95(10.1),
            HealthState::HealthDegraded
        );
        assert_eq!(
            classify_strategy_quality_slippage_bps_p95(100.0),
            HealthState::HealthDegraded
        );
    }

    #[test]
    fn test_classify_decision_lease_grant_rate_thresholds() {
        // OK band: > 0.70
        assert_eq!(
            classify_strategy_quality_decision_lease_grant_rate(0.70),
            HealthState::HealthOk
        );
        assert_eq!(
            classify_strategy_quality_decision_lease_grant_rate(1.0),
            HealthState::HealthOk
        );
        // WARN band: 0.50 - 0.70
        assert_eq!(
            classify_strategy_quality_decision_lease_grant_rate(0.69),
            HealthState::HealthWarn
        );
        assert_eq!(
            classify_strategy_quality_decision_lease_grant_rate(0.50),
            HealthState::HealthWarn
        );
        // DEGRADED band: 0.10 - 0.50
        assert_eq!(
            classify_strategy_quality_decision_lease_grant_rate(0.49),
            HealthState::HealthDegraded
        );
        assert_eq!(
            classify_strategy_quality_decision_lease_grant_rate(0.10),
            HealthState::HealthDegraded
        );
        // CRITICAL band: < 0.10
        assert_eq!(
            classify_strategy_quality_decision_lease_grant_rate(0.09),
            HealthState::HealthCritical
        );
        assert_eq!(
            classify_strategy_quality_decision_lease_grant_rate(0.0),
            HealthState::HealthCritical
        );
    }

    #[test]
    fn test_classify_dormant_minutes_thresholds() {
        // OK band: < 60
        assert_eq!(
            classify_strategy_quality_dormant_minutes(0),
            HealthState::HealthOk
        );
        assert_eq!(
            classify_strategy_quality_dormant_minutes(59),
            HealthState::HealthOk
        );
        // WARN band: 60 - 120
        assert_eq!(
            classify_strategy_quality_dormant_minutes(60),
            HealthState::HealthWarn
        );
        assert_eq!(
            classify_strategy_quality_dormant_minutes(119),
            HealthState::HealthWarn
        );
        // DEGRADED band: 120 - 360
        assert_eq!(
            classify_strategy_quality_dormant_minutes(120),
            HealthState::HealthDegraded
        );
        assert_eq!(
            classify_strategy_quality_dormant_minutes(360),
            HealthState::HealthDegraded
        );
        // CRITICAL band: > 360
        assert_eq!(
            classify_strategy_quality_dormant_minutes(361),
            HealthState::HealthCritical
        );
        assert_eq!(
            classify_strategy_quality_dormant_minutes(10000),
            HealthState::HealthCritical
        );
    }

    // -----------------------------------------------------------
    // StrategyQualitySample into_metric_rows
    // -----------------------------------------------------------

    #[test]
    fn test_strategy_quality_sample_into_metric_rows_5_metrics() {
        let snapshot = StrategyQualitySample {
            strategy_name: "grid".to_string(),
            symbol: "BTCUSDT".to_string(),
            fill_rate_intent_ratio: 0.95,
            slippage_bps_p95: 2.0,
            decision_lease_grant_rate: 0.85,
            dormant_minutes: 5,
            signal_count_24h: 100,
        };
        let rows = snapshot.into_metric_rows();
        assert_eq!(rows.len(), 5);
        let names: Vec<&'static str> = rows.iter().map(|r| r.metric_name).collect();
        assert_eq!(
            names,
            vec![
                "fill_rate_intent_ratio",
                "slippage_bps_p95",
                "decision_lease_grant_rate",
                "dormant_minutes",
                "signal_count_24h",
            ]
        );
        // 全 metric OK band（OK-band sample）。
        for r in &rows {
            assert_eq!(r.band, HealthState::HealthOk);
            assert_eq!(r.strategy_name, "grid");
            assert_eq!(r.symbol, "BTCUSDT");
        }
    }

    #[test]
    fn test_strategy_quality_sample_into_metric_rows_critical_band() {
        // 全 CRITICAL band sample（除 signal_count_24h telemetry-only 走 OK）。
        let snapshot = StrategyQualitySample {
            strategy_name: "ma".to_string(),
            symbol: "ETHUSDT".to_string(),
            fill_rate_intent_ratio: 0.05,        // < 0.20 → CRITICAL
            slippage_bps_p95: 50.0,              // > 10 → DEGRADED（slippage 無 CRITICAL band）
            decision_lease_grant_rate: 0.05,     // < 0.10 → CRITICAL
            dormant_minutes: 500,                // > 360 → CRITICAL
            signal_count_24h: 0,
        };
        let rows = snapshot.into_metric_rows();
        assert_eq!(rows.len(), 5);
        let by_name: HashMap<&str, &StrategyQualityMetricRow> =
            rows.iter().map(|r| (r.metric_name, r)).collect();
        assert_eq!(
            by_name["fill_rate_intent_ratio"].band,
            HealthState::HealthCritical
        );
        assert_eq!(
            by_name["slippage_bps_p95"].band,
            HealthState::HealthDegraded
        );
        assert_eq!(
            by_name["decision_lease_grant_rate"].band,
            HealthState::HealthCritical
        );
        assert_eq!(
            by_name["dormant_minutes"].band,
            HealthState::HealthCritical
        );
        // signal_count_24h telemetry-only 永遠 OK band。
        assert_eq!(by_name["signal_count_24h"].band, HealthState::HealthOk);
    }

    // -----------------------------------------------------------
    // StrategyQualityEmitter — sample_interval + domain
    // -----------------------------------------------------------

    #[tokio::test]
    async fn test_strategy_quality_emitter_interval_300_and_domain() {
        let pairs = make_25_pairs();
        let emitter = StrategyQualityEmitter::new(StubSource::new(), pairs);
        assert_eq!(emitter.domain(), HealthDomain::StrategyQuality);
        assert_eq!(
            emitter.sample_interval_sec(),
            300,
            "per spec §2.1 line 245 strategy_quality 5min sample（不可寫死 30s/60s per packet §6.5 反模式 (b)）"
        );
    }

    #[tokio::test]
    async fn test_strategy_quality_emitter_25_pairs_125_rows() {
        // 25 pair × 5 metric = 125 row per sample tick。
        let pairs = make_25_pairs();
        let mut emitter = StrategyQualityEmitter::new(StubSource::new(), pairs.clone());
        let rows = emitter.sample().await.unwrap();
        assert_eq!(rows.len(), 25 * 5);
        // 第一個 row strategy 為 grid（make_25_pairs() 排序順序）。
        assert_eq!(rows[0].metric_name(), "fill_rate_intent_ratio");
    }

    // -----------------------------------------------------------
    // StrategyQualityScheduler — per_pair_sm_count + aggregate SM init
    // -----------------------------------------------------------

    #[tokio::test]
    async fn test_strategy_quality_scheduler_per_pair_sm_count_25_x_4() {
        let pairs = make_25_pairs();
        let emitter = StrategyQualityEmitter::new(StubSource::new(), pairs);
        let writer: Arc<dyn HealthObservationWriter> =
            Arc::new(InMemoryHealthObservationWriter::new());
        let event_bus = Arc::new(HealthEventBus::new());
        let mode: EngineModeProvider = Arc::new(|| "demo".to_string());
        let scheduler = StrategyQualityScheduler::new(emitter, writer, event_bus, mode);
        // 25 pair × 4 band metric (signal_count_24h 不算) = 100 SM 實例。
        assert_eq!(
            scheduler.per_pair_sm_count(),
            25 * 4,
            "per-pair SM 計數 = 25 pair × 4 band metric = 100"
        );
        // aggregate SM 初始 state = OK。
        let agg_sm = scheduler.aggregate_sm();
        let guard = agg_sm.lock().await;
        assert_eq!(guard.current_state(), HealthState::HealthOk);
    }

    // -----------------------------------------------------------
    // classify_aggregated dispatch arm — 退化守
    // -----------------------------------------------------------

    /// strategy_quality 4 band metric 走 classify_aggregated 真實 dispatch；
    /// 若 dispatch arm 漏接，下列呼叫返 OK 為 fallback，assert 必失敗。
    ///
    /// 為什麼此 test:
    ///   - 對齊 Track C HIGH-1 stress test 範式（per Sprint 2 round 2 Track C
    ///     test_sprint2_track_c_database_pool_degraded_band_classify line 333）
    ///     端到端守 strategy_quality 4 個 arm 不退化。
    #[test]
    fn test_classify_aggregated_strategy_quality_arms_not_fallback() {
        // fill_rate_intent_ratio: mean 0.1 → CRITICAL
        assert_eq!(
            classify_aggregated_for_test(
                HealthDomain::StrategyQuality,
                "fill_rate_intent_ratio",
                0.1,
            ),
            HealthState::HealthCritical,
            "classify_aggregated strategy_quality::fill_rate_intent_ratio arm 必走 helper（不可 fallback OK）"
        );
        // slippage_bps_p95: mean 15.0 → DEGRADED
        assert_eq!(
            classify_aggregated_for_test(
                HealthDomain::StrategyQuality,
                "slippage_bps_p95",
                15.0,
            ),
            HealthState::HealthDegraded,
            "classify_aggregated strategy_quality::slippage_bps_p95 arm 必走 helper（不可 fallback OK）"
        );
        // decision_lease_grant_rate: mean 0.05 → CRITICAL
        assert_eq!(
            classify_aggregated_for_test(
                HealthDomain::StrategyQuality,
                "decision_lease_grant_rate",
                0.05,
            ),
            HealthState::HealthCritical,
            "classify_aggregated strategy_quality::decision_lease_grant_rate arm 必走 helper（不可 fallback OK）"
        );
        // dormant_minutes: mean 500.0 → CRITICAL（mean.round() as u32 → 500）
        assert_eq!(
            classify_aggregated_for_test(
                HealthDomain::StrategyQuality,
                "dormant_minutes",
                500.0,
            ),
            HealthState::HealthCritical,
            "classify_aggregated strategy_quality::dormant_minutes arm 必走 helper + mean.round() 對齊（不可 fallback OK）"
        );
        // dormant_minutes boundary：mean 59.6 → round=60 → WARN
        // 為什麼此 boundary check:
        //   per Sprint 2 round 2 MEDIUM-2 fix「mean.round() 而非 truncate」；
        //   59.6 truncate=59 誤歸 OK；round=60 正確 WARN。本 helper 屬 count 類
        //   metric，必走 round。
        assert_eq!(
            classify_aggregated_for_test(
                HealthDomain::StrategyQuality,
                "dormant_minutes",
                59.6,
            ),
            HealthState::HealthWarn,
            "dormant_minutes mean=59.6 → round=60 → WARN（不可 truncate 為 59 誤歸 OK）"
        );
        // signal_count_24h 走 fallback OK band（telemetry-only）。
        assert_eq!(
            classify_aggregated_for_test(
                HealthDomain::StrategyQuality,
                "signal_count_24h",
                10000.0,
            ),
            HealthState::HealthOk,
            "signal_count_24h 走 fallback OK band 為設計刻意（telemetry-only；Sprint 5 block bootstrap re-estimate 才接 SLO）"
        );
    }
}
