//! ModelClient trait stub — M5 online learning interface reservation per ADR-0035 §Decision 1 (6-method authoritative)。
//!
//! MODULE_NOTE
//! 模塊用途：為 M5 online learning / streaming model update 預留統一介面；Sprint
//!   1A-δ 僅交 trait 骨架 + placeholder type，6 method 全為 `unimplemented!()`
//!   panic（fail-loud）；Y3+ activation 期才寫真實 IMPL。
//! 主要類/函數：
//!   - `ModelClient` trait（6 method default panic，與 canonical spec 2026-05-21
//!     m5_online_learning_design_spec.md §2 line 84-138 對齊）
//!   - `UnimplementedModelClient` default impl struct（純 marker，呼叫任一 method
//!     即 panic）
//!   - placeholder type：`FeatureVector` / `DistributionMetrics` / `ModelVersion`
//!     / `ModelHealth` / `ModelHealthStatus` / `StreamingPrediction`
//!   - `M5Error` enum（手動 impl `Display` + `std::error::Error`，不引 thiserror）
//!   - `Prediction` 自 `crate::edge_predictor` re-export 對齊既有 daily-batch
//!     baseline 輸出型別
//! 依賴：crate::edge_predictor::Prediction（既有 LightGBM/3DL baseline 統一輸出
//!   型別）。
//! 硬邊界：
//!   1. 6 method default body 全 `unimplemented!()`，禁默認 `Ok(())` no-op
//!      （per canonical spec §2.3 反模式 + ADR-0035 §Decision 1 反模式 (b)）。
//!   2. 不寫 streaming 算法 / drift detection / rollback 演算
//!      （per ADR-0035 §Decision 1 + canonical spec §1.3；Y3+ activation 才 IMPL）。
//!   3. trait 物件必滿足 `Send + Sync + 'static` dyn safety（caller 可建構
//!      `Box<dyn ModelClient>`）。
//!   4. Y3+ activation 6 條件全 PASS 前禁實裝 method body
//!      （per ADR-0035 §Decision 3）。
//!
//! 參考：
//!   - ADR-0035：`srv/docs/adr/0035-m5-online-learning-interface-reserved.md`
//!   - canonical spec：`srv/docs/execution_plan/2026-05-21--m5_online_learning_design_spec.md`
//!   - v5.8 §2 M5 (lines 188-217)

// 對齊既有 daily-batch baseline 推論輸出（canonical spec §1.2 表格 LightGBM 列）。
// 既有 EdgePredictor trait 已使用 `Prediction`，ModelClient 是其 superset；
// sync prediction 結果型別必須一致，避免 caller 看到兩個 Prediction。
pub use crate::edge_predictor::Prediction;

use std::error::Error;
use std::fmt;

/// M5 Online Learning 錯誤型別。
///
/// 為什麼：6 method 全走 `Result<T, M5Error>`，caller 必須能在 streaming
/// pipeline 未 activation 時取得結構化錯誤而非裸 panic（Y3+ activation 後）。
/// 不引 thiserror，沿用 M13 IMPL 已採的 `std::error::Error` + 手動 `Display` 模式。
#[derive(Debug, Clone)]
pub enum M5Error {
    /// streaming pipeline 未 activation；caller 應 fallback 至 baseline。
    /// 內含 method 名稱以供 audit 定位。
    NotActivated(String),
}

impl fmt::Display for M5Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            M5Error::NotActivated(method) => write!(
                f,
                "M5 online learning not activated (method={}); see ADR-0035 §Decision 3",
                method
            ),
        }
    }
}

impl Error for M5Error {}

/// FeatureVector — Sprint 1A-δ 階段 placeholder struct。
///
/// 為什麼：trait 簽名需穩定，但 Y3+ activation 前不綁定具體 FeatureCollector
/// 型別；Y3+ activation 期再對齊 `feature_collector`（per canonical spec §2.1 line
/// 140 placeholder 註記）。提前綁定具體 struct 會導致 trait breaking change。
#[derive(Debug, Clone, Default)]
pub struct FeatureVector {
    /// 預留 placeholder field；Y3+ activation 期由 FeatureCollector 對齊定義。
    /// 不在 Sprint 1A-δ 階段開放給 caller 寫入。
    pub _placeholder: (),
}

/// DistributionMetrics — feature distribution 漂移度量 placeholder。
///
/// 為什麼：`drift_callback` method 需接收結構化 drift 訊號（KL divergence /
/// EDDM / DDM 等），Y3+ activation 期才選型；Sprint 1A-δ 階段僅佔位
/// （per canonical spec §2.1 line 143 placeholder 註記）。
#[derive(Debug, Clone, Default)]
pub struct DistributionMetrics {
    /// 預留 placeholder field；Y3+ activation 期 algorithm 選型後定義。
    pub _placeholder: (),
}

/// 模型版本識別 — 對齊 V114 `learning.model_versions` 表 schema 預留。
///
/// 為什麼：streaming 與 baseline 兩條版本軌道並存，audit 必須能同時指認；
/// Sprint 1A-δ 不鎖 field stability，Y3+ activation 期可 amend。
#[derive(Debug, Clone, Default)]
pub struct ModelVersion {
    /// baseline 模型版本（LightGBM / 3DL daily-batch）。
    pub baseline_version: String,
    /// streaming 模型版本（Y3+ activation 後才有值；Y1+Y2 為 None）。
    pub streaming_version: Option<String>,
    /// 版本登記時間（Unix epoch 秒）。
    pub version_ts: i64,
}

/// 模型健康狀態 enum — 對齊 ADR-0034 LAL Tier 3 / 4 gate eligibility。
///
/// 為什麼：health degrade 是 streaming rollback 的觸發訊號之一
/// （per canonical spec §2.2 表格 `health` 列）。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ModelHealthStatus {
    /// 健康 — streaming 誤差與 drift 皆在閾值內。
    Healthy,
    /// 降級 — 觀察期；streaming 預測仍可用，但 caller 應降低權重。
    Degraded,
    /// 不健康 — caller 必須 fallback 至 daily-batch baseline。
    Unhealthy,
}

/// 模型健康度報告 placeholder — streaming 誤差 + drift score + 樣本量綜合。
///
/// 為什麼：LAL Tier 3 / 4 promotion gate 需要結構化 health evidence；Sprint
/// 1A-δ 列代表性 field，Y3+ activation 期可 amend。
#[derive(Debug, Clone)]
pub struct ModelHealth {
    /// 綜合健康狀態 enum。
    pub status: ModelHealthStatus,
    /// streaming 模型對 baseline 的誤差分數（具體公式 Y3+ activation 期定）。
    pub streaming_error_score: Option<f64>,
    /// feature 漂移分數（如 KL divergence；Y3+ activation 期定義）。
    pub drift_score: Option<f64>,
    /// 自上次模型更新以來累積樣本量。
    pub samples_since_last_update: u64,
    /// 報告產生時間（Unix epoch 秒）。
    pub reported_at_ts: i64,
}

impl Default for ModelHealth {
    fn default() -> Self {
        // Y3+ activation 前不該有人讀此預設；保留 conservative `Unhealthy` 預設
        // 以對齊原則 6（失敗默認收縮 / fail-closed）。
        Self {
            status: ModelHealthStatus::Unhealthy,
            streaming_error_score: None,
            drift_score: None,
            samples_since_last_update: 0,
            reported_at_ts: 0,
        }
    }
}

/// streaming 推論結果 placeholder — baseline 預測 + streaming delta + drift。
///
/// 為什麼：streaming prediction 必須能讓 caller 同時取得 baseline 與
/// streaming 的差異（per canonical spec §2.2 表格 `get_predict_streaming` 列）；
/// degrade 時 caller 可主動降權或 fallback 至 baseline。
#[derive(Debug, Clone)]
pub struct StreamingPrediction {
    /// baseline 預測（daily-batch wrapper 路徑）。
    pub baseline: Prediction,
    /// streaming 相對 baseline 的調整量（單位與 Prediction 一致；bps）。
    pub streaming_delta_bps: Option<f64>,
    /// streaming 模型版本（呼叫當下 active streaming version）。
    pub streaming_version: Option<String>,
    /// 當下 drift score（Y3+ activation 期定義）。
    pub drift_score: Option<f64>,
}

/// M5 ModelClient trait — ML 模型推論統一介面預留。
///
/// 為什麼：online learning / streaming 更新與既有 daily-batch baseline 必須
/// 共享統一推論介面，避免 caller 重複處理兩條 ML 路徑；Y3+ activation 期
/// 才寫真 body，Sprint 1A-δ 階段 6 method 全 `unimplemented!()` panic
/// （fail-loud，per canonical spec §2.3 反模式 Gate 2 + ADR-0035 §Decision 1
/// 反模式 (b)）。
///
/// 6 method 對齊 canonical spec §2.1 line 79-137 rust block：
///   1. `get_predict(features) -> Result<Prediction, M5Error>`
///   2. `get_predict_streaming(features) -> Result<StreamingPrediction, M5Error>`
///   3. `drift_callback(distribution_metrics) -> Result<(), M5Error>`
///   4. `rollback(version) -> Result<(), M5Error>`
///   5. `throttle(rate_per_sec) -> Result<(), M5Error>`
///   6. `health() -> Result<ModelHealth, M5Error>`
///
/// 紀律：
///   - trait 必為 `Send + Sync` + `'static`（dyn safety；caller 可建構
///     `Box<dyn ModelClient>`）。
///   - 任一 Y1+Y2 caller 誤呼必 panic，強制 fail-loud（per canonical spec §2.3
///     反模式 Gate 1）。
///   - Y3+ activation 6 條件全 PASS 前禁實裝 method body
///     （per ADR-0035 §Decision 3）。
pub trait ModelClient: Send + Sync + 'static {
    /// 同步預測（既有 daily-batch baseline 統一包裝介面）。
    ///
    /// 為什麼：caller 取得 baseline 預測時走同一條路徑；Y3+ activation 後將
    /// 包裝既有 EdgePredictor 為真 body + 加 streaming fallback chain
    /// （per canonical spec §2.2 表格第 1 列）。Sprint 1A-δ 階段保持 panic。
    fn get_predict(&self, _features: &FeatureVector) -> Result<Prediction, M5Error> {
        unimplemented!(
            "M5 ModelClient::get_predict stub — Y3+ activation 後 IMPL（per ADR-0035 §Decision 1）"
        )
    }

    /// streaming 推論 — Y3+ activation 後 streaming weight 增量更新後即時推論。
    ///
    /// 為什麼：streaming 模型在 Y3+ activation 前完全停用；任何 Y1+Y2 caller
    /// 呼叫此 method 均應立即 fail-loud，避免 silent dummy 通過
    /// （per canonical spec §2.2 表格第 2 列 + §2.3 反模式 Gate 1）。
    fn get_predict_streaming(
        &self,
        _features: &FeatureVector,
    ) -> Result<StreamingPrediction, M5Error> {
        unimplemented!(
            "M5 ModelClient::get_predict_streaming stub — Y3+ activation 後 IMPL（per ADR-0035 §Decision 1）"
        )
    }

    /// feature distribution 漂移回呼（KL divergence trigger）。
    ///
    /// 為什麼：Y3+ activation 後實作 drift detection → 觸發 Strategist propose
    /// model rollback path（per canonical spec §2.2 表格第 3 列 + §4.3 M11
    /// integration placeholder）。Y1+Y2 panic 是因為無 drift detection 路徑。
    fn drift_callback(
        &self,
        _distribution_metrics: &DistributionMetrics,
    ) -> Result<(), M5Error> {
        unimplemented!(
            "M5 ModelClient::drift_callback stub — Y3+ activation 後 IMPL（per ADR-0035 §Decision 1）"
        )
    }

    /// 回滾到指定模型版本（safety net）。
    ///
    /// 為什麼：streaming 模型 degrade 時 caller 透過此 method 退回 daily-batch
    /// baseline version（per canonical spec §2.2 表格第 4 列）。Y1+Y2 panic 是因為
    /// 無 streaming model state，亦無 rollback target。
    fn rollback(&self, _version: ModelVersion) -> Result<(), M5Error> {
        unimplemented!(
            "M5 ModelClient::rollback stub — Y3+ activation 後 IMPL（per ADR-0035 §Decision 1）"
        )
    }

    /// streaming 更新速率限流（防 over-fit single fill）。
    ///
    /// 為什麼：Y3+ activation 後實作 rate-limited streaming update + cooldown
    /// （per canonical spec §2.2 表格第 5 列 + §4.2 M6 reward integration
    /// placeholder）。Y1+Y2 panic 是因為無 streaming update 路徑。
    fn throttle(&self, _rate_per_sec: f64) -> Result<(), M5Error> {
        unimplemented!(
            "M5 ModelClient::throttle stub — Y3+ activation 後 IMPL（per ADR-0035 §Decision 1）"
        )
    }

    /// 模型健康度（per ADR-0034 LAL gate criteria 對齊 evidence）。
    ///
    /// 為什麼：LAL Tier 3 / 4 promotion gate 需要結構化 health evidence
    /// （per canonical spec §2.2 表格第 6 列）。Y1+Y2 panic 是因為無 streaming
    /// 模型 evidence 可彙整。
    fn health(&self) -> Result<ModelHealth, M5Error> {
        unimplemented!(
            "M5 ModelClient::health stub — Y3+ activation 後 IMPL（per ADR-0035 §Decision 1）"
        )
    }
}

/// 純 marker 預設實作 — 任一 method 呼叫均觸發 default panic。
///
/// 為什麼：caller 建構 `Box<dyn ModelClient>` 時需要可實例化的 default
/// 型別；Y3+ activation 前任何 runtime 試圖建構 ModelClient 並呼叫 method
/// 均應 fail-loud（per canonical spec §2.3 反模式 Gate 1 + ADR-0035 §Decision 1
/// fail-loud 紀律）。構造此 struct 本身合法（不 panic），呼叫任一 method 才 panic。
#[derive(Debug, Clone, Default)]
pub struct UnimplementedModelClient;

impl ModelClient for UnimplementedModelClient {
    // 全部 6 method 沿用 trait default body（unimplemented!()），不複寫；
    // 任一呼叫均 fail-loud。
}
