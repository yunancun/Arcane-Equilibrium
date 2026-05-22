//! M3 Sprint 2 Wave 2 Track F — risk_envelope domain emitter。
//!
//! MODULE_NOTE
//! 模塊用途:
//!   per docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_design_spec.md
//!   §2.1 + §3.2 + §3.6 + §6.2 + dispatch packet §7：本 module 為 Wave 2 Track F
//!   risk_envelope domain 採樣 emitter。300s (5min) sample interval，5 metric：
//!     - `portfolio_cum_pnl_24h_usd`：portfolio 24h 累計實現 PnL (USD)。
//!     - `portfolio_max_dd_pct`：portfolio 24h sliding window max drawdown (%)。
//!     - `position_count_active`：當前活躍倉位數。
//!     - `correlation_avg_pairwise`：跨倉位 pairwise 相關係數平均。
//!     - `concentration_top1_pct`：top-1 symbol exposure 佔 portfolio total exposure 比例。
//!
//!   為什麼 300s (5min) sample interval（per spec §2.1）:
//!     portfolio dd / correlation / concentration 是慢動業務指標；5min 採樣足夠
//!     反映 24h sliding window 級異常，避高頻 sample 對既有 portfolio calculation
//!     hot path 干擾（per dispatch packet §7.5 反模式 (c)：correlation 不可寫死
//!     高頻）。對齊 5-sample × 300s = 25min window，匹配 §3.3 dwell time 設計。
//!
//!   為什麼此 5 metric（spec §3.2 line 405-415 規範 + operator sign-off
//!   2026-05-22）:
//!     - `portfolio_cum_pnl_24h_usd`：cum loss > $1500/24h 即 WARN，> $2500/24h
//!       即 DEGRADED，> $3000/24h 由既有 5-gate kill 觸發 CATASTROPHIC（per M3
//!       spec line 106 + line 228 ladder）；emitter 只觀測，不直接 trigger kill。
//!     - `portfolio_max_dd_pct`：24h sliding window max drawdown；< 5% OK / 5-10%
//!       WARN / 10-15% DEGRADED / > 15% CRITICAL（per M3 spec line 106 ladder）。
//!     - `position_count_active`：當前活躍倉位數；上限對齊 risk_config
//!       max_open_positions 既有設計；超過 80% 上限 WARN，超過上限 DEGRADED。
//!     - `correlation_avg_pairwise`：跨倉位 pairwise correlation 平均；< 0.5 OK /
//!       0.5-0.7 WARN / > 0.7 DEGRADED（per M3 spec line 106 ladder）。
//!     - `concentration_top1_pct`：top-1 symbol exposure 佔 portfolio total
//!       exposure；< 30% OK / 30-50% WARN / > 50% DEGRADED（per M3 spec line 106）。
//!
//! 主要類 / 函數:
//!   - `RiskEnvelopeSample`：5 metric snapshot struct（per spec §3.2 line 405-415）。
//!   - `RiskEnvelopeMetricRow`：MetricSample 投影；5 row per sample tick 對齊 V106
//!     schema 1 row = 1 metric_name 設計。
//!   - `RiskEnvelopeSourceProbe` trait：抽象 5 metric source；emitter 經此 trait
//!     觀測，不修 risk_verdict_ledger / position_snapshot / fill_writer 既有
//!     SSOT 邏輯（per dispatch packet §7.5 反模式 (a)）。
//!   - `classify_risk_envelope_*` × 5：per-metric classify_band 函數，threshold
//!     來自 M3 design spec §2.3 line 106 ladder。
//!   - `RiskEnvelopeEmitter`：impl `DomainEmitter`；sample_interval=300s。
//!
//! 依賴:
//!   - 全部沿用 Track A scaffold（`DomainEmitter` / `MetricSample` trait /
//!     `RollingWindowAggregator` / `HealthStateMachine::observe_classified`）。
//!   - 不依賴具體 portfolio calc 模組；經 trait 抽象注入（main.rs Wave 2 後 wire
//!     既有 risk_verdict_ledger / position_snapshot 計算）。
//!   - 不依賴 spike feature（per AC-5 production binary 0 mock time 滲透）。
//!
//! 硬邊界:
//!   - emitter 只讀，不修 risk_verdict_ledger / position_snapshot / fill_writer
//!     既有邏輯（per dispatch packet §7.5 反模式 (a)；emitter 只觀測，既有
//!     portfolio calc 是 SSOT）。
//!   - sample_interval=300s 走 spec §2.1 規約（不寫死 30s/60s；per dispatch
//!     packet §7.5 反模式 (b/c)）。
//!   - emit V106 row 不寫 `engine_mode='live'`（Sprint 2 走 paper/demo/live_demo
//!     only；per dispatch packet §9 反模式 (d)）。
//!   - 5 metric 各自 anomaly_id = `risk_envelope__<metric_name>`（per spec §6.2
//!     命名規約）；5 個獨立 cap window，不互 cap。
//!   - threshold 對齊 M3 design spec §2.3 line 106 ladder：先 hardcode，Sprint 5
//!     ArcSwap 熱更新（per spec §4.3 注 + Track A/B/C 同 pattern）。
//!   - 不同步 5-gate kill threshold（per dispatch packet §7.2 step 6 + parent
//!     spec §2.3；Sprint 5 Tier 1 IMPL 前 confirm）；emit DEGRADED 不觸 5-gate
//!     kill 行為（per dispatch packet §7.5 反模式 (b)）。
//!   - VaR / parametric / Monte Carlo / leverage / margin_util 等延伸 metric
//!     不在本 sprint 5 metric scope（per dispatch packet §7.5 反模式 (d/e) 預
//!     留 config + 待 PA spec amend，本 Sprint 2 不引擴 metric）。

use std::sync::Arc;

use async_trait::async_trait;

use super::super::metric_emitter::{DomainEmitter, MetricSample};
use super::super::{HealthDomain, HealthState, M3Error};

// ============================================================
// RiskEnvelopeSample — 5 metric snapshot
// ============================================================

/// risk_envelope domain 採樣輸出（per spec §3.2 line 405-415）。
///
/// 為什麼這 5 個 metric:
///   - 對齊 M3 design spec §2.3 line 106 ladder + ADR-0042 + dispatch packet §7。
///   - 5 metric 全 portfolio-level 聚合，不 per-symbol（per dispatch packet §7.4
///     AC-7 portfolio 原則對齊 16 根原則 #16）。
///   - 不含 leverage / margin_util / VaR：dispatch packet §7.5 反模式 (d/e) 預
///     留 config + 待 PA spec amend；本 Sprint 2 emitter 5 metric scope 固定。
///
/// 為什麼 Clone + Copy:
///   - 5 個 numeric primitive；Copy 0 cost；emitter sample() 端拷貝後可 Box 走
///     trait object（對齊 Track A `EngineRuntimeSample` / Track B
///     `PipelineThroughputSample` pattern）。
#[derive(Debug, Clone, Copy)]
pub struct RiskEnvelopeSample {
    /// portfolio 24h 累計實現 PnL (USD)；負值為虧損。
    pub portfolio_cum_pnl_24h_usd: f64,
    /// portfolio 24h sliding window max drawdown (%)；非負；越大越嚴。
    pub portfolio_max_dd_pct: f64,
    /// 當前活躍倉位數。
    pub position_count_active: u32,
    /// 跨倉位 pairwise correlation 平均；範圍 [-1.0, 1.0]，越大越同步。
    pub correlation_avg_pairwise: f64,
    /// top-1 symbol exposure 佔 portfolio total exposure 比例 (%)；範圍 [0, 100]。
    pub concentration_top1_pct: f64,
}

/// MetricSample wrapper：每 metric 個別投影為 row；scheduler 端列表處理。
///
/// 為什麼一 emitter sample → 5 MetricSample row:
///   - V106 row 是 per-metric_name 一條（per ADR-0042 Decision 4 anomaly_id =
///     domain × metric_name）；5 metric → 5 row + 5 SM 各自 transition。
///   - 對齊 Track A `EngineRuntimeMetricRow` / Track B `PipelineThroughputMetricRow`
///     / Track C `DatabasePoolMetricRow` 同樣 1 sample → multi-row 範式，
///     scaffold reuse；scheduler 端 `run_domain_loop` 統一處理 5 metric × 1 SM。
#[derive(Debug, Clone, Copy)]
pub struct RiskEnvelopeMetricRow {
    pub metric_name: &'static str,
    pub value: f64,
    pub band: HealthState,
}

impl MetricSample for RiskEnvelopeMetricRow {
    fn metric_name(&self) -> &'static str {
        self.metric_name
    }

    fn numeric_value(&self) -> f64 {
        self.value
    }

    fn classify_band(&self) -> HealthState {
        self.band
    }

    // extra_evidence 走 trait default None；risk_envelope domain 無 disconnected
    // 類採樣語意，emitter 端 fail-soft probe 直接回 0.0 / 0（fail-closed OK band）
    // 而非寫 evidence_json audit trail。
}

impl RiskEnvelopeSample {
    /// 將 sample 展為 5 個 metric row（每 metric_name 一條）。
    ///
    /// 為什麼此設計:
    ///   - 對齊 V106 schema：1 row = 1 metric_name；不展平就無法各 metric 獨立
    ///     classify_band + SM transition（per ADR-0042 Decision 4 anomaly_id 命
    ///     名規約）。
    ///   - 對齊 Track A/B/C `into_metric_rows()` 模式，scaffold reuse；scheduler
    ///     端 `run_domain_loop` 統一處理 5 metric × 1 SM each。
    ///
    /// 為什麼 max_open_positions 上限不寫死:
    ///   - position_count_active classify 走「靜態 8 + 16 上下限」對齊 spec line
    ///     106 規範；max_open_positions 取自 risk_config 邏輯由 caller (main.rs)
    ///     Wave 2 後接 emitter wire-up 時注入（per dispatch packet §7.5 反模式
    ///     (a) emitter 不重做 risk_config 載入）。本 helper 採 static threshold
    ///     literal 對齊 spec line 106 8/16 ladder；caller 端注入動態 threshold
    ///     由 Sprint 5 Tier 1 ArcSwap 熱更新（per spec §4.3 規約）。
    pub fn into_metric_rows(self) -> Vec<RiskEnvelopeMetricRow> {
        let cum_pnl_band = classify_risk_envelope_cum_pnl_24h_usd(self.portfolio_cum_pnl_24h_usd);
        let dd_band = classify_risk_envelope_max_dd_pct(self.portfolio_max_dd_pct);
        let pos_count_band = classify_risk_envelope_position_count(self.position_count_active);
        let corr_band = classify_risk_envelope_correlation_avg(self.correlation_avg_pairwise);
        let concentration_band =
            classify_risk_envelope_concentration_top1_pct(self.concentration_top1_pct);

        vec![
            RiskEnvelopeMetricRow {
                metric_name: "portfolio_cum_pnl_24h_usd",
                value: self.portfolio_cum_pnl_24h_usd,
                band: cum_pnl_band,
            },
            RiskEnvelopeMetricRow {
                metric_name: "portfolio_max_dd_pct",
                value: self.portfolio_max_dd_pct,
                band: dd_band,
            },
            RiskEnvelopeMetricRow {
                metric_name: "position_count_active",
                value: self.position_count_active as f64,
                band: pos_count_band,
            },
            RiskEnvelopeMetricRow {
                metric_name: "correlation_avg_pairwise",
                value: self.correlation_avg_pairwise,
                band: corr_band,
            },
            RiskEnvelopeMetricRow {
                metric_name: "concentration_top1_pct",
                value: self.concentration_top1_pct,
                band: concentration_band,
            },
        ]
    }
}

// ============================================================
// classify_band threshold helper × 5
// ============================================================
//
// 為什麼 threshold 集中於 5 個 pub fn:
//   - Sprint 5 ArcSwap 熱更新時改 5 fn 內部即可，不破壞 caller signature。
//   - scheduler 端 `classify_aggregated` match arm 直接呼此 5 fn，DRY。
//   - 對齊 Track A `classify_engine_runtime_*` / Track B
//     `classify_pipeline_throughput_*` / Track C `classify_database_pool_*` 同
//     樣 pub fn pattern。
//
// 為什麼 threshold 來源 M3 design spec §2.3 line 106 + line 228:
//   - 設計階段 ladder spec 已確定 4 band 邊界；emitter IMPL 不重設計，僅
//     literal 落地。
//   - dispatch packet §7.5 反模式 (b)：emit DEGRADED 不觸 5-gate kill（Sprint 5
//     才同步），但 ladder 數值 1:1 對齊 spec ladder（避免雙重設計衝突）。

/// `portfolio_cum_pnl_24h_usd` classify（per M3 design spec §2.3 line 106 +
/// line 228）。
///
/// ladder（cum_pnl 是負值為虧損；ladder 看「虧損強度」/ -1 × cum_pnl）:
///   OK       : cum_loss < $500/24h   （pnl > -500；正常運營區）
///   WARN     : $500 - $1500/24h       （pnl in [-1500, -500]；告警觀測）
///   DEGRADED : $1500 - $2500/24h      （pnl in [-2500, -1500]；接近 kill 邊界）
///   CRITICAL : > $2500/24h            （pnl < -2500；待 5-gate CATASTROPHIC 走
///                                       既有 D2 kill 觸發；emitter 只標記）
///
/// 為什麼 CRITICAL band 與既有 5-gate kill 數值對齊但**不直接觸 kill**:
///   - per dispatch packet §7.5 反模式 (b)：「emit DEGRADED 不觸 5-gate kill」；
///     emitter 是觀測層，5-gate kill 由既有 D2 邏輯走（per M3 spec §17.3 D3
///     Sprint 5 Tier 1 IMPL 前 confirm）。
///   - emitter 標 CRITICAL band 仍只 emit V106 row 不啟動 cascade；Sprint 5
///     cascade 才走 5-gate kill 同步 mechanism。
///
/// 為什麼 threshold 對齊 M3 spec line 106 ladder 既有設計:
///   - spec ladder 已對齊既有 `risk_config` cum_loss 5-gate kill threshold；
///     避雙重設計衝突（per ADR-0042 反模式）。
///   - threshold dynamic update 走 Sprint 5 Tier 1 ArcSwap；本 Sprint 2 hardcode
///     對齊 spec §4.3「Sprint 2 IMPL 先 hardcode threshold」決議。
pub fn classify_risk_envelope_cum_pnl_24h_usd(cum_pnl_usd: f64) -> HealthState {
    // cum_pnl 是負值為虧損；判 loss_magnitude = max(0, -cum_pnl)。
    let loss_magnitude = (-cum_pnl_usd).max(0.0);
    if loss_magnitude > 2500.0 {
        HealthState::HealthCritical
    } else if loss_magnitude > 1500.0 {
        HealthState::HealthDegraded
    } else if loss_magnitude > 500.0 {
        HealthState::HealthWarn
    } else {
        HealthState::HealthOk
    }
}

/// `portfolio_max_dd_pct` classify（per M3 design spec §2.3 line 106）。
///
/// ladder（dd 是非負百分比；越大越嚴）:
///   OK       : < 5%      （正常波動）
///   WARN     : 5 - 10%    （告警觀測）
///   DEGRADED : 10 - 15%   （顯著回撤）
///   CRITICAL : > 15%      （CATASTROPHIC dd；待 5-gate kill）
///
/// 為什麼此 threshold:
///   - spec line 106 ladder 明文「dd < 5% OK / 5-10% WARN / 10-15% DEGRADED /
///     > 15% CRITICAL」；emitter IMPL literal 落地。
///   - dd 是 portfolio-level sliding window 計算結果（per dispatch packet §7.5
///     反模式 (a)：emitter 只觀測，既有 risk_verdict_ledger / position_snapshot
///     計算 dd SSOT）。
pub fn classify_risk_envelope_max_dd_pct(dd_pct: f64) -> HealthState {
    if dd_pct > 15.0 {
        HealthState::HealthCritical
    } else if dd_pct > 10.0 {
        HealthState::HealthDegraded
    } else if dd_pct >= 5.0 {
        HealthState::HealthWarn
    } else {
        HealthState::HealthOk
    }
}

/// `position_count_active` classify。
///
/// ladder（per M3 spec §2.3 line 106 amend，PA Sprint 2 Wave 2 2026-05-22 amend；
/// 對齊 risk_config max_open_positions 既有設計）:
///   OK       : 0 - 8     （穩態運營區）
///   WARN     : 9 - 16     （高位但可控）
///   DEGRADED : > 16       （超過正常 max_open_positions 上限）
///
/// 為什麼此 threshold（per E2 round 1 Track F MED-1 fix Option A — PA spec
/// amend + E1 doc 對齊）:
///   - 移除原 `feedback_position_sizing` 自定 magic number rationale；threshold
///     literal 統一以 M3 spec §2.3 line 106 amend 為 SSOT。
///   - 不設 CRITICAL band：位數本身不致命，致命層由 cum_pnl / dd / concentration
///     反映；避雙 metric 同時升 CRITICAL 重複觸發 cascade（per ADR-0042 反模式）。
///   - threshold 由 Sprint 5 Tier 1 ArcSwap 熱更新（per spec §4.3 規約）；
///     production wire-up 時 caller 端可注入動態 max_open_positions（per
///     `feedback_rust_authoritative_config`）。
pub fn classify_risk_envelope_position_count(count: u32) -> HealthState {
    if count > 16 {
        HealthState::HealthDegraded
    } else if count >= 9 {
        HealthState::HealthWarn
    } else {
        HealthState::HealthOk
    }
}

/// `correlation_avg_pairwise` classify（per M3 design spec §2.3 line 106）。
///
/// ladder（correlation 越大越同步，分散失效）:
///   OK       : < 0.5      （倉位有效分散）
///   WARN     : 0.5 - 0.7   （部分同步）
///   DEGRADED : > 0.7      （高度同步，分散失效）
///
/// 為什麼此 threshold:
///   - spec line 106 ladder 明文「corr < 0.5 OK / 0.5-0.7 WARN / > 0.7 DEGRADED」。
///   - 不設 CRITICAL band：correlation 本身不致命，致命層由 cum_pnl / dd 反映；
///     避雙 metric 同時升 CRITICAL（per ADR-0042 反模式）。
///   - 範圍處理：input 範圍應 [-1, 1]；超出範圍由 caller (probe) 端保證；
///     classify 端不額外 sanitize，避隱藏 calculator bug（per
///     `feedback_no_dead_params` fail-loud 對齊）。
pub fn classify_risk_envelope_correlation_avg(corr: f64) -> HealthState {
    if corr > 0.7 {
        HealthState::HealthDegraded
    } else if corr >= 0.5 {
        HealthState::HealthWarn
    } else {
        HealthState::HealthOk
    }
}

/// `concentration_top1_pct` classify（per M3 design spec §2.3 line 106）。
///
/// ladder（top-1 exposure 佔 portfolio total；越大越集中）:
///   OK       : < 30%     （倉位分散合理）
///   WARN     : 30 - 50%   （部分集中）
///   DEGRADED : > 50%     （高度集中，single-symbol concentration risk）
///
/// 為什麼此 threshold:
///   - spec line 106 ladder 明文「top1 < 30% OK / 30-50% WARN / > 50% DEGRADED」。
///   - 不設 CRITICAL band：concentration 本身不致命，致命層由 cum_pnl / dd 反映。
///   - 預留 config 可調 per ADR-0042（dispatch packet §7.5 反模式 (e)）：
///     threshold dynamic update 走 Sprint 5 Tier 1 ArcSwap；本 Sprint 2 hardcode
///     對齊 spec literal。
///   - 「top-N」延伸（top-3 / top-5 etc）為 Sprint 5+ 擴展點；本 Sprint 2 emitter
///     只走 top-1 對齊 spec literal scope。
pub fn classify_risk_envelope_concentration_top1_pct(pct: f64) -> HealthState {
    if pct > 50.0 {
        HealthState::HealthDegraded
    } else if pct >= 30.0 {
        HealthState::HealthWarn
    } else {
        HealthState::HealthOk
    }
}

// ============================================================
// RiskEnvelopeSourceProbe trait — 5 metric source 注入點
// ============================================================

/// 5 metric source 抽象 trait；emitter 只呼此 trait 取值，**不修**
/// risk_verdict_ledger / position_snapshot / fill_writer 既有邏輯（per
/// dispatch packet §7.5 反模式 (a)）。
///
/// 為什麼 trait 注入而非直接 import:
///   - emitter「只觀測，不修」：emitter struct 持有 trait object，main.rs Wave 2
///     後接 emitter wire-up 時注入真實 portfolio calculation wrapper；test 注
///     入 mock。
///   - 對齊 Track B `PipelineThroughputSourceProbe` / Track C `WriterQueueProbe`
///     注入模式；5 metric → 5 method 整合單一 trait 比 5 個獨立 closure 乾淨。
///   - 對齊 spec §3 D1 emitter 採樣邊界：emitter 只負責採樣 + classify，不負責
///     metric 計算機制（既有 portfolio calc 是 SSOT）。
///
/// 接線分工（Wave 2 後 main.rs 注入）:
///   - `current_portfolio_cum_pnl_24h_usd()`：main.rs 接 risk_verdict_ledger /
///     trading.fills 24h 累計實現 PnL 聚合（既有計算邏輯，emitter 只讀）。
///   - `current_portfolio_max_dd_pct()`：main.rs 接 position_snapshot 24h sliding
///     window max drawdown 計算（既有計算邏輯，emitter 只讀）。
///   - `current_position_count_active()`：main.rs 接 position_snapshot active
///     count（既有計算邏輯，emitter 只讀）。
///   - `current_correlation_avg_pairwise()`：main.rs 接既有 cross-pair correlation
///     計算（per `crate::scanner::scorer::apply_correlation_filter` 或專屬
///     portfolio correlation helper；既有計算邏輯，emitter 只讀）。
///   - `current_concentration_top1_pct()`：main.rs 接 position_snapshot 計算 top-1
///     symbol exposure 佔 portfolio total exposure 比例（既有計算邏輯，emitter
///     只讀）。
///
/// 硬邊界:
///   - probe 失敗（如 source 未接線）返 0.0/0 不 panic；emitter 端視 0 為 OK
///     band，不誤升級（per `feedback_no_dead_params` fail-soft 對齊）。
///   - test 注入 mock 走實作；production 接線責任 Wave 2+ 或 Sprint 5 cascade
///     IMPL 時由 main.rs caller 補。
///   - emitter 不持有 risk_verdict_ledger / position_snapshot / fill_writer 既
///     有 struct 的 mut reference；只透過此 trait 取「當前 snapshot 計算結果」
///     （read-only access）。
pub trait RiskEnvelopeSourceProbe: Send + Sync {
    /// portfolio 24h 累計實現 PnL (USD)；負值為虧損。
    fn current_portfolio_cum_pnl_24h_usd(&self) -> f64;
    /// portfolio 24h sliding window max drawdown (%)；非負。
    fn current_portfolio_max_dd_pct(&self) -> f64;
    /// 當前活躍倉位數。
    fn current_position_count_active(&self) -> u32;
    /// 跨倉位 pairwise correlation 平均；範圍 [-1.0, 1.0]。
    fn current_correlation_avg_pairwise(&self) -> f64;
    /// top-1 symbol exposure 佔 portfolio total exposure 比例 (%)；範圍 [0, 100]。
    fn current_concentration_top1_pct(&self) -> f64;

    /// batch read helper：一次取得 5 metric snapshot（per PA-DRIFT-5 round 1
    /// E2 F-3 fix）。
    ///
    /// 為什麼此 default method（per E2 round 1 F-3 micro-race window 修復）：
    ///   - 5 個 current_xxx accessor 各拿一次 lock；emitter sample 時 5-lock
    ///     gap 內若 cache update 介入 → 產生 5-metric snapshot inconsistency
    ///     micro-race window。
    ///   - 本 method 讓 impl override 走「一次 lock + 一次拷 5 metric」batch
    ///     read，原子地 snapshot 整個 5-metric tuple；emitter Wave B 接線後可
    ///     切換走 `snapshot_5_metric()` 避免 race window。
    ///   - default impl 走 5 個 current_xxx 對齊 backward compat（既有 mock /
    ///     test fixture 不需改）；具體 impl（`RealRiskEnvelopeSourceProbe`）
    ///     override 走 batch path。
    ///
    /// 為什麼 default 而非 required：
    ///   - 既有 mock / test fixture（如 `StubSource` / `MockMutexRiskProbe`）已
    ///     impl trait；強制要求新 method 會破壞 backward compat。default 走 5
    ///     個 current_xxx 結果語意等價（單 thread test 無 race）。
    ///   - production `RealRiskEnvelopeSourceProbe` override 走 batch；emitter
    ///     wire-up 端不需感知 impl 差異。
    fn snapshot_5_metric(&self) -> RiskEnvelopeSampleSnapshot {
        RiskEnvelopeSampleSnapshot {
            portfolio_cum_pnl_24h_usd: self.current_portfolio_cum_pnl_24h_usd(),
            portfolio_max_dd_pct: self.current_portfolio_max_dd_pct(),
            position_count_active: self.current_position_count_active(),
            correlation_avg_pairwise: self.current_correlation_avg_pairwise(),
            concentration_top1_pct: self.current_concentration_top1_pct(),
        }
    }
}

/// 5 metric batch snapshot；trait `snapshot_5_metric()` 返值型別（per
/// PA-DRIFT-5 round 1 E2 F-3 fix）。
///
/// 為什麼這 5 個欄位順序對齊 `RiskEnvelopeSample`：
///   - emitter `sample_now()` 端可直接從 `RiskEnvelopeSampleSnapshot` 投影為
///     `RiskEnvelopeSample`（field-wise 1:1 mapping），不需重新打包。
///   - Copy + Clone：5 個 numeric primitive；emitter Box<dyn MetricSample>
///     端拷貝 0 成本。
#[derive(Debug, Clone, Copy)]
pub struct RiskEnvelopeSampleSnapshot {
    pub portfolio_cum_pnl_24h_usd: f64,
    pub portfolio_max_dd_pct: f64,
    pub position_count_active: u32,
    pub correlation_avg_pairwise: f64,
    pub concentration_top1_pct: f64,
}

// ============================================================
// RiskEnvelopeEmitter — Track F IMPL
// ============================================================

/// risk_envelope domain emitter；300s (5min) sample；經 trait 抽象觀測 5 metric。
///
/// 為什麼 Arc<dyn ...>:
///   - main.rs scheduler 接線時可能共享 portfolio source probe（同一 portfolio
///     calculator 可被多 emitter 觀測），Arc 允許 reference count；Box 需移轉
///     所有權。
///   - tokio task 跨 spawn 邊界需 Send + Sync；Arc<dyn ... + Send + Sync> 對齊。
///
/// 為什麼採 trait 注入而非直接持有具體 portfolio calc struct:
///   - emitter「只觀測，不修」（per dispatch packet §7.5 反模式 (a)）；trait
///     注入讓 emitter 不依賴具體 portfolio calc 實作，main.rs Wave 2 wire-up 時
///     可注入既有 risk_verdict_ledger / position_snapshot wrapper。
///   - 對齊 Track B `PipelineThroughputEmitter` 同樣 Arc<dyn ...> 注入模式；
///     scaffold reuse。
pub struct RiskEnvelopeEmitter {
    source: Arc<dyn RiskEnvelopeSourceProbe>,
}

impl RiskEnvelopeEmitter {
    /// 建立 emitter；caller 注入 5 metric source probe。
    ///
    /// 為什麼 generic + Arc::new:
    ///   - test 注入 in-line struct impl trait 不需 caller 端 Arc::new。
    ///   - production main.rs 注入 Arc<RealPortfolioSource> 由 generic 自動接受。
    pub fn new<S>(source: S) -> Self
    where
        S: RiskEnvelopeSourceProbe + 'static,
    {
        Self {
            source: Arc::new(source),
        }
    }

    /// 採當前 5 metric snapshot（test 可直接呼此 helper）。
    ///
    /// 為什麼 &self 而非 &mut self（對比 Track A `sample_now` mut self）:
    ///   - sysinfo refresh_processes 需 mut；trait probe 是純讀 accessor 不需
    ///     mut，故 emitter sample 端可走 &self（對齊 Track B
    ///     `PipelineThroughputEmitter::sample_now` 同模式）。
    pub fn sample_now(&self) -> Result<RiskEnvelopeSample, M3Error> {
        Ok(RiskEnvelopeSample {
            portfolio_cum_pnl_24h_usd: self.source.current_portfolio_cum_pnl_24h_usd(),
            portfolio_max_dd_pct: self.source.current_portfolio_max_dd_pct(),
            position_count_active: self.source.current_position_count_active(),
            correlation_avg_pairwise: self.source.current_correlation_avg_pairwise(),
            concentration_top1_pct: self.source.current_concentration_top1_pct(),
        })
    }
}

#[async_trait]
impl DomainEmitter for RiskEnvelopeEmitter {
    fn domain(&self) -> HealthDomain {
        HealthDomain::RiskEnvelope
    }

    fn sample_interval_sec(&self) -> u64 {
        // per spec §2.1：risk_envelope 300s (5min) sample（業務級慢動指標；
        // portfolio dd 5min 採樣足夠；不可寫死 30s/60s per dispatch packet §7.5
        // 反模式 (b/c)）。
        300
    }

    async fn sample(&mut self) -> Result<Vec<Box<dyn MetricSample>>, M3Error> {
        let snapshot = self.sample_now()?;
        let rows = snapshot.into_metric_rows();
        Ok(rows
            .into_iter()
            .map(|r| Box::new(r) as Box<dyn MetricSample>)
            .collect())
    }
}

// ============================================================
// 測試
// ============================================================

#[cfg(test)]
mod tests {
    use super::*;

    /// 內嵌 mock source；test fixture 用（對齊 Track B `StubSource` pattern）。
    struct StubSource {
        portfolio_cum_pnl_24h_usd: f64,
        portfolio_max_dd_pct: f64,
        position_count_active: u32,
        correlation_avg_pairwise: f64,
        concentration_top1_pct: f64,
    }

    impl RiskEnvelopeSourceProbe for StubSource {
        fn current_portfolio_cum_pnl_24h_usd(&self) -> f64 {
            self.portfolio_cum_pnl_24h_usd
        }
        fn current_portfolio_max_dd_pct(&self) -> f64 {
            self.portfolio_max_dd_pct
        }
        fn current_position_count_active(&self) -> u32 {
            self.position_count_active
        }
        fn current_correlation_avg_pairwise(&self) -> f64 {
            self.correlation_avg_pairwise
        }
        fn current_concentration_top1_pct(&self) -> f64 {
            self.concentration_top1_pct
        }
    }

    #[test]
    fn test_classify_cum_pnl_24h_usd_ladder() {
        // OK band：cum_loss < $500
        assert_eq!(
            classify_risk_envelope_cum_pnl_24h_usd(0.0),
            HealthState::HealthOk
        );
        assert_eq!(
            classify_risk_envelope_cum_pnl_24h_usd(100.0),
            HealthState::HealthOk,
            "正向 cum_pnl (賺) 必 OK band"
        );
        assert_eq!(
            classify_risk_envelope_cum_pnl_24h_usd(-100.0),
            HealthState::HealthOk
        );
        assert_eq!(
            classify_risk_envelope_cum_pnl_24h_usd(-500.0),
            HealthState::HealthOk,
            "邊界值 -500（loss=500，閾值 > 500）仍 OK"
        );
        // WARN band：$500 - $1500
        assert_eq!(
            classify_risk_envelope_cum_pnl_24h_usd(-501.0),
            HealthState::HealthWarn
        );
        assert_eq!(
            classify_risk_envelope_cum_pnl_24h_usd(-1500.0),
            HealthState::HealthWarn,
            "邊界值 -1500（loss=1500，閾值 > 1500）仍 WARN"
        );
        // DEGRADED band：$1500 - $2500
        assert_eq!(
            classify_risk_envelope_cum_pnl_24h_usd(-1501.0),
            HealthState::HealthDegraded
        );
        assert_eq!(
            classify_risk_envelope_cum_pnl_24h_usd(-2500.0),
            HealthState::HealthDegraded,
            "邊界值 -2500（loss=2500，閾值 > 2500）仍 DEGRADED"
        );
        // CRITICAL band：> $2500
        assert_eq!(
            classify_risk_envelope_cum_pnl_24h_usd(-2501.0),
            HealthState::HealthCritical
        );
        assert_eq!(
            classify_risk_envelope_cum_pnl_24h_usd(-5000.0),
            HealthState::HealthCritical
        );
    }

    #[test]
    fn test_classify_max_dd_pct_ladder() {
        // OK band：< 5%
        assert_eq!(
            classify_risk_envelope_max_dd_pct(0.0),
            HealthState::HealthOk
        );
        assert_eq!(
            classify_risk_envelope_max_dd_pct(4.9),
            HealthState::HealthOk
        );
        // WARN band：5% - 10%
        assert_eq!(
            classify_risk_envelope_max_dd_pct(5.0),
            HealthState::HealthWarn
        );
        assert_eq!(
            classify_risk_envelope_max_dd_pct(10.0),
            HealthState::HealthWarn,
            "邊界值 10%（> 10% 才升 DEGRADED）仍 WARN"
        );
        // DEGRADED band：> 10% 且 <= 15%
        assert_eq!(
            classify_risk_envelope_max_dd_pct(10.1),
            HealthState::HealthDegraded
        );
        assert_eq!(
            classify_risk_envelope_max_dd_pct(15.0),
            HealthState::HealthDegraded,
            "邊界值 15%（> 15% 才升 CRITICAL）仍 DEGRADED"
        );
        // CRITICAL band：> 15%
        assert_eq!(
            classify_risk_envelope_max_dd_pct(15.1),
            HealthState::HealthCritical
        );
        assert_eq!(
            classify_risk_envelope_max_dd_pct(30.0),
            HealthState::HealthCritical
        );
    }

    #[test]
    fn test_classify_position_count_ladder() {
        // OK band：0 - 8
        assert_eq!(
            classify_risk_envelope_position_count(0),
            HealthState::HealthOk
        );
        assert_eq!(
            classify_risk_envelope_position_count(8),
            HealthState::HealthOk
        );
        // WARN band：9 - 16
        assert_eq!(
            classify_risk_envelope_position_count(9),
            HealthState::HealthWarn
        );
        assert_eq!(
            classify_risk_envelope_position_count(16),
            HealthState::HealthWarn
        );
        // DEGRADED band：> 16
        assert_eq!(
            classify_risk_envelope_position_count(17),
            HealthState::HealthDegraded
        );
        assert_eq!(
            classify_risk_envelope_position_count(30),
            HealthState::HealthDegraded
        );
    }

    #[test]
    fn test_classify_correlation_avg_ladder() {
        // OK band：< 0.5
        assert_eq!(
            classify_risk_envelope_correlation_avg(0.0),
            HealthState::HealthOk
        );
        assert_eq!(
            classify_risk_envelope_correlation_avg(0.49),
            HealthState::HealthOk
        );
        assert_eq!(
            classify_risk_envelope_correlation_avg(-0.5),
            HealthState::HealthOk,
            "負相關（反向倉位）必 OK band"
        );
        // WARN band：0.5 - 0.7
        assert_eq!(
            classify_risk_envelope_correlation_avg(0.5),
            HealthState::HealthWarn
        );
        assert_eq!(
            classify_risk_envelope_correlation_avg(0.7),
            HealthState::HealthWarn,
            "邊界值 0.7（> 0.7 才升 DEGRADED）仍 WARN"
        );
        // DEGRADED band：> 0.7
        assert_eq!(
            classify_risk_envelope_correlation_avg(0.71),
            HealthState::HealthDegraded
        );
        assert_eq!(
            classify_risk_envelope_correlation_avg(1.0),
            HealthState::HealthDegraded
        );
    }

    #[test]
    fn test_classify_concentration_top1_pct_ladder() {
        // OK band：< 30%
        assert_eq!(
            classify_risk_envelope_concentration_top1_pct(0.0),
            HealthState::HealthOk
        );
        assert_eq!(
            classify_risk_envelope_concentration_top1_pct(29.9),
            HealthState::HealthOk
        );
        // WARN band：30 - 50%
        assert_eq!(
            classify_risk_envelope_concentration_top1_pct(30.0),
            HealthState::HealthWarn
        );
        assert_eq!(
            classify_risk_envelope_concentration_top1_pct(50.0),
            HealthState::HealthWarn,
            "邊界值 50%（> 50% 才升 DEGRADED）仍 WARN"
        );
        // DEGRADED band：> 50%
        assert_eq!(
            classify_risk_envelope_concentration_top1_pct(50.1),
            HealthState::HealthDegraded
        );
        assert_eq!(
            classify_risk_envelope_concentration_top1_pct(100.0),
            HealthState::HealthDegraded
        );
    }

    #[test]
    fn test_sample_into_metric_rows_emits_5_rows() {
        // OK band sample（cum_pnl=0 / dd=0 / pos=5 / corr=0.3 / conc=20）
        let sample = RiskEnvelopeSample {
            portfolio_cum_pnl_24h_usd: 0.0,
            portfolio_max_dd_pct: 0.0,
            position_count_active: 5,
            correlation_avg_pairwise: 0.3,
            concentration_top1_pct: 20.0,
        };
        let rows = sample.into_metric_rows();
        assert_eq!(rows.len(), 5, "5 metric → 5 row 對齊 V106 schema");
        let names: Vec<&str> = rows.iter().map(|r| r.metric_name).collect();
        assert!(names.contains(&"portfolio_cum_pnl_24h_usd"));
        assert!(names.contains(&"portfolio_max_dd_pct"));
        assert!(names.contains(&"position_count_active"));
        assert!(names.contains(&"correlation_avg_pairwise"));
        assert!(names.contains(&"concentration_top1_pct"));
        // OK band sample 各 metric band = OK
        for row in rows {
            assert_eq!(
                row.band,
                HealthState::HealthOk,
                "OK band 採樣每 metric 必 OK band: {}",
                row.metric_name
            );
        }
    }

    #[test]
    fn test_sample_into_metric_rows_degraded_sample_propagates() {
        // DEGRADED-band 注入：cum_pnl=-2000 / dd=12 / pos=20 / corr=0.8 / conc=60
        let sample = RiskEnvelopeSample {
            portfolio_cum_pnl_24h_usd: -2000.0,
            portfolio_max_dd_pct: 12.0,
            position_count_active: 20,
            correlation_avg_pairwise: 0.8,
            concentration_top1_pct: 60.0,
        };
        let rows = sample.into_metric_rows();
        assert_eq!(rows.len(), 5);
        let cum = rows
            .iter()
            .find(|r| r.metric_name == "portfolio_cum_pnl_24h_usd")
            .unwrap();
        assert_eq!(cum.band, HealthState::HealthDegraded);
        assert_eq!(cum.value, -2000.0);
        let dd = rows
            .iter()
            .find(|r| r.metric_name == "portfolio_max_dd_pct")
            .unwrap();
        assert_eq!(dd.band, HealthState::HealthDegraded);
        let pos = rows
            .iter()
            .find(|r| r.metric_name == "position_count_active")
            .unwrap();
        assert_eq!(pos.band, HealthState::HealthDegraded);
        let corr = rows
            .iter()
            .find(|r| r.metric_name == "correlation_avg_pairwise")
            .unwrap();
        assert_eq!(corr.band, HealthState::HealthDegraded);
        let conc = rows
            .iter()
            .find(|r| r.metric_name == "concentration_top1_pct")
            .unwrap();
        assert_eq!(conc.band, HealthState::HealthDegraded);
    }

    #[tokio::test]
    async fn test_risk_envelope_emitter_returns_5_metric_samples() {
        let source = StubSource {
            portfolio_cum_pnl_24h_usd: 0.0,
            portfolio_max_dd_pct: 2.0,
            position_count_active: 5,
            correlation_avg_pairwise: 0.3,
            concentration_top1_pct: 20.0,
        };
        let mut emitter = RiskEnvelopeEmitter::new(source);
        assert_eq!(emitter.domain(), HealthDomain::RiskEnvelope);
        assert_eq!(
            emitter.sample_interval_sec(),
            300,
            "risk_envelope 必 300s (5min) sample interval per spec §2.1"
        );
        let samples = emitter.sample().await.unwrap();
        assert_eq!(samples.len(), 5);
        // 每 metric band 是 OK（注入值在 OK band）
        for s in &samples {
            assert_eq!(s.classify_band(), HealthState::HealthOk);
        }
    }

    #[tokio::test]
    async fn test_risk_envelope_emitter_critical_sample_propagates() {
        // CRITICAL 注入：cum_pnl=-3000（loss=3000 > 2500）+ dd=20（> 15）
        let source = StubSource {
            portfolio_cum_pnl_24h_usd: -3000.0,
            portfolio_max_dd_pct: 20.0,
            position_count_active: 5,
            correlation_avg_pairwise: 0.3,
            concentration_top1_pct: 20.0,
        };
        let mut emitter = RiskEnvelopeEmitter::new(source);
        let samples = emitter.sample().await.unwrap();
        assert_eq!(samples.len(), 5);
        let cum = samples
            .iter()
            .find(|s| s.metric_name() == "portfolio_cum_pnl_24h_usd")
            .unwrap();
        assert_eq!(cum.classify_band(), HealthState::HealthCritical);
        let dd = samples
            .iter()
            .find(|s| s.metric_name() == "portfolio_max_dd_pct")
            .unwrap();
        assert_eq!(dd.classify_band(), HealthState::HealthCritical);
        // 其他 3 metric 仍 OK（domain 內各 metric 獨立 classify）
        let pos = samples
            .iter()
            .find(|s| s.metric_name() == "position_count_active")
            .unwrap();
        assert_eq!(pos.classify_band(), HealthState::HealthOk);
    }

    #[test]
    fn test_metric_sample_extra_evidence_default_none() {
        // risk_envelope 無 disconnected 類採樣 audit；extra_evidence 走 trait
        // default None（per Track A engine_runtime / Track B pipeline_throughput
        // 同模式；不破壞 scheduler 端 extra_evidence 互斥優先級設計）。
        let row = RiskEnvelopeMetricRow {
            metric_name: "portfolio_cum_pnl_24h_usd",
            value: -100.0,
            band: HealthState::HealthOk,
        };
        assert!(
            row.extra_evidence().is_none(),
            "risk_envelope MetricRow extra_evidence 必 None（無 disconnected 類採樣語意）"
        );
    }
}
