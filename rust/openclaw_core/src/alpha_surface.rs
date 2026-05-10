//! W-AUDIT-8a Phase A — Alpha Surface 一等公民接口契約。
//!
//! MODULE_NOTE：把非-TA alpha source（funding curve / OI delta panel /
//!   orderflow features / liquidation pulse / event alerts / sentiment panel /
//!   regime tag）從「策略自己 buffer」升為架構一等公民。Phase A 僅落 trait/struct
//!   契約 + 5 既存策略 explicit declare alpha sources，**0 行為變化**：
//!   - Tier 1（TA / OHLCV）：`indicators` / `indicators_5m` 由 `TickPipeline`
//!     正常 wire 進；
//!   - Tier 2（funding curve / basis curve / OI delta panel）：本 wave **永遠
//!     `None`**，collector 留給 Phase B；
//!   - Tier 3（orderflow / liquidation pulse）：本 wave **永遠 `None`**，
//!     collector / WS handler 留給 Phase C；
//!   - Tier 4（event alerts / regime tag / sentiment panel）：event_alerts 用
//!     `&[]`，regime 用 `RegimeTag::Unknown`，sentiment_panel 永遠 `None`，
//!     真實 wire 留給 Phase D。
//!
//! Spec 來源：
//! `docs/execution_plan/2026-05-09--w_audit_8a_alpha_surface_foundation_spec.md`
//! §2 + §3 Phase A Deliverable。
//!
//! 設計約束：
//! - **生命週期 `'a` 與 `TickContext<'a>` 同源**：surface 只是把 collector/IPC
//!   slot 的引用打包，永不 own / 永不 deep clone；策略端 `surface.<field>` 取得
//!   的引用在 `on_tick` scope 結束即失效；
//! - **`Optional::None` = 「該 alpha source 在當前 phase 尚未 wire 或 collector
//!   暫時 stale」**；策略 ctor 若聲稱吃此 tag，必須在 `on_tick` 內 fail-closed
//!   跳過自身 alpha source（不可 fallback 到 TA1m）；
//! - **`AlphaSourceTag` enum 變更必經 ADR**：本 enum 是 alpha source SoT，添加 /
//!   刪除 / 重命名都觸發 ADR；W-AUDIT-8a 落地後 enum 為權威。
//!
//! Sprint N+1 W2 BtcLeadLagPanel paper-only fence（trait 不知此 fence）：
//! - paper-only fence 由 `tick_pipeline/on_tick/step_4_5_dispatch.rs`
//!   `effective_engine_mode()` gate 主防線實施（demo / live_demo / live →
//!   `surface.btc_lead_lag = None`）。trait 端對 fence 不知情；
//! - 策略消費端 `surface.btc_lead_lag.is_none()` → skip 即可，不需查
//!   engine_mode；契約 = AlphaSurface::None 永遠是 fail-closed signal；
//! - Python writer 端 + Strategy guard 是第二、三層深度防禦
//!   （per PA `2026-05-10--alpha_surface_trait_final_shape_w1_w2_coord.md` §5）。

use serde::{Deserialize, Serialize};

use crate::indicators::IndicatorSnapshot;

/// AlphaSourceTag — 聲明性枚舉，給 Strategy 在 ctor 階段表態「我吃哪幾個 alpha
/// source」。Orchestrator 用此做 dispatch tracking 與 promotion gate 對齊。
///
/// Display / Serialize 採 lowercase snake_case，與 PG schema 對齊。
///
/// 各 variant 顯式 `#[serde(rename = "...")]`：因 serde 的 `snake_case` 規則
/// 無法把 `Ta1m` 拆成 `ta_1m`（digit 不觸發 word boundary，會輸出 `ta1m`），
/// 顯式 rename 讓 serialize 與 `as_metric_label` 一致。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum AlphaSourceTag {
    // ── Tier 1 — TA / OHLCV（向後相容） ──
    /// 1m kline-derived TA snapshot（既有 IndicatorSnapshot）。
    #[serde(rename = "ta_1m")]
    Ta1m,
    /// 5m kline-derived TA snapshot（既有 indicators_5m）。
    #[serde(rename = "ta_5m")]
    Ta5m,
    // ── Tier 2 — 跨資產 / 截面 panel ──
    /// 25-symbol funding rate cross-section panel。
    #[serde(rename = "funding_skew")]
    FundingSkew,
    /// Perp vs index basis curve cross-section（**`requires_spot_capability: true`**）。
    #[serde(rename = "basis")]
    Basis,
    /// Cross-symbol open interest delta panel。
    #[serde(rename = "oi_delta_panel")]
    OiDeltaPanel,
    // ── Tier 3 — Microstructure ──
    /// Microprice / queue imbalance / large-trade tape rolling stats。
    #[serde(rename = "orderflow_imbalance")]
    OrderflowImbalance,
    /// Bybit `allLiquidation` pulse cluster（**`requires_revival: true`** —
    /// handler 已於 2026-04-06 移除，復活前永遠 `None`）。
    #[serde(rename = "liquidation_cascade")]
    LiquidationCascade,
    // ── Tier 4 — Information flow ──
    /// Scout `intel_objects` 派出的 EventAlert（事件驅動）。
    #[serde(rename = "event_driven")]
    EventDriven,
    /// BTC→Alt lead-lag / cross-pair correlation（候選 C，留給 W-AUDIT-8c）。
    #[serde(rename = "cross_asset")]
    CrossAsset,
    /// SentimentPanel from external feeds（W-AUDIT-8a stub-only）。
    #[serde(rename = "sentiment")]
    Sentiment,
}

impl AlphaSourceTag {
    /// 回傳 lowercase snake_case 字串，對齊 PG / Prometheus label。
    /// 與 `serde::Serialize` 輸出一致（後者 enum→Value::String）。
    pub const fn as_metric_label(self) -> &'static str {
        match self {
            Self::Ta1m => "ta_1m",
            Self::Ta5m => "ta_5m",
            Self::FundingSkew => "funding_skew",
            Self::Basis => "basis",
            Self::OiDeltaPanel => "oi_delta_panel",
            Self::OrderflowImbalance => "orderflow_imbalance",
            Self::LiquidationCascade => "liquidation_cascade",
            Self::EventDriven => "event_driven",
            Self::CrossAsset => "cross_asset",
            Self::Sentiment => "sentiment",
        }
    }
}

impl std::fmt::Display for AlphaSourceTag {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.as_metric_label())
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Tier 2 — 跨資產 / 截面 panel stub（Phase B IMPL）
// ─────────────────────────────────────────────────────────────────────────

/// FundingCurveSnapshot — 25-symbol funding rate cross-section panel。
///
/// 字段對齊 spec §2.3 Tier 2.1：本 wave 為 stub TYPE（field 完整定義方便
/// Phase B caller 直接 populate；`AlphaSurface` 在 Phase A 永遠 None 不構造）。
///
/// 來源（Phase B）：Bybit `tickers` WS + Python collector aggregator → PG 表
/// `market.funding_rates_panel`（V### migration 新增；retention 14d）。
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct FundingCurveSnapshot {
    /// 同步 vector：symbols[i] 對應 funding_rates_bps[i] 與 next_funding_ms[i]。
    pub symbols: Vec<String>,
    /// 各 symbol 當前 funding rate，單位 basis points（bps）。
    pub funding_rates_bps: Vec<f64>,
    /// 各 symbol 下次 funding 時間戳（ms）。
    pub next_funding_ms: Vec<i64>,
    /// 本快照採集時間戳（ms）。Phase B freshness check 來源。
    pub snapshot_ts_ms: i64,
    /// Source tier 標記（與 V050 simulated_fills.evidence_source_tier 對齊
    /// 命名語義；Phase B 帶值，本 phase stub 為空字串）。
    pub source_tier: String,
}

/// BasisCurveSnapshot — Perp vs index basis curve cross-section panel。
///
/// **執行邊界（spec §2.3 Tier 2.2）**：basis 在 mainnet 接通 spot account 前
/// 永遠是 observation-only signal。Bybit demo 不支援 spot lending，吃 `Basis`
/// tag 的策略必須宣告 `requires_spot_capability: true`，IntentRouter 在
/// demo / live_demo 環境下對其 `StrategyAction` fail-closed。
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct BasisCurveSnapshot {
    pub symbols: Vec<String>,
    /// (perp - index) / index × 100，單位 percent。
    pub basis_pct: Vec<f64>,
    pub perp_price: Vec<f64>,
    pub index_price: Vec<f64>,
    pub snapshot_ts_ms: i64,
    pub source_tier: String,
}

/// OIDeltaPanel — cross-symbol open interest delta panel（5m / 15m / 1h 三檔）。
///
/// 來源（Phase B）：Bybit `tickers` WS open_interest field + Python writer 寫
/// `market.open_interest`，aggregator 算 delta → 寫 `market.oi_delta_panel`
/// （V### migration；retention 14d）。
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct OIDeltaPanel {
    pub symbols: Vec<String>,
    /// 5 分鐘 OI 變化百分比。
    pub oi_delta_5m_pct: Vec<f64>,
    pub oi_delta_15m_pct: Vec<f64>,
    pub oi_delta_1h_pct: Vec<f64>,
    /// 各 symbol 當前 OI 絕對值（合約張數）。
    pub oi_abs: Vec<f64>,
    pub snapshot_ts_ms: i64,
    pub source_tier: String,
}

// ─────────────────────────────────────────────────────────────────────────
// Tier 3 — Microstructure stub（Phase C IMPL）
// ─────────────────────────────────────────────────────────────────────────

/// OrderflowFeatures — per-symbol microstructure（microprice / queue imbalance
/// / large-trade tape rolling stats）。
///
/// 來源（Phase C / W-AUDIT-8d 真接）：Bybit V5 WS `orderbook.50.{symbol}`
/// （**真實 levels 1/50/200/1000，沒有 L25 — spec §2.3 Tier 3.1**）。
/// Phase C 為 stub mock；真接留給 W-AUDIT-8d。
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct OrderflowFeatures {
    pub symbol: String,
    /// Microprice = (bid_size × ask + ask_size × bid) / (bid_size + ask_size)。
    pub microprice: f64,
    /// Queue imbalance = bid_size / (bid_size + ask_size) ∈ [0, 1]。
    pub queue_imbalance: f64,
    /// Rolling 60s 大單成交筆數。
    pub large_trade_count_60s: u32,
    /// Rolling 60s 大單成交累計 quantity。
    pub large_trade_volume_60s: f64,
    pub snapshot_ts_ms: i64,
    pub source_tier: String,
}

/// LiquidationSide — 強平方向（多頭被強平 / 空頭被強平）。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum LiquidationSide {
    /// 多頭倉位被強平（賣出）。
    LongLiquidated,
    /// 空頭倉位被強平（買入）。
    ShortLiquidated,
    /// 雙向 / 未明 / 樣本不足。
    #[default]
    Mixed,
}

/// LiquidationEvent — 單筆強平事件（Phase C revival 後填）。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LiquidationEvent {
    pub symbol: String,
    pub side: LiquidationSide,
    /// 強平 quantity（合約張數）。
    pub qty: f64,
    /// 強平成交價。
    pub price: f64,
    pub ts_ms: i64,
}

/// LiquidationPulse — Bybit `allLiquidation` cascade detection（**dormant**）。
///
/// **狀態 dormant** — `allLiquidation` WS handler 於 2026-04-06 已移除（字典
/// 手冊 line 990 證明）。復活前 `AlphaSurface.liquidation_pulse` 永遠 `None`，
/// **禁止 stub mock 數據**（避免「假 alpha source dispatched」污染 dispatch
/// tracking metric）。
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct LiquidationPulse {
    /// Rolling 60s 窗口的強平事件。
    pub recent_events: Vec<LiquidationEvent>,
    /// Cluster score（0.0 – 1.0；Phase C IMPL 算法）。
    pub cluster_score: f64,
    pub dominant_side: LiquidationSide,
    pub snapshot_ts_ms: i64,
}

// ─────────────────────────────────────────────────────────────────────────
// Tier 4 — Information flow（Phase D IMPL；本 phase 用 default placeholder）
// ─────────────────────────────────────────────────────────────────────────

/// ScoutEventId — 對齊 Python `scout_agent` IntelObject id 的封裝型別。
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct ScoutEventId(pub String);

/// EventCategory — Scout intel event 分類（Phase D wire 時對齊 IntelObject schema）。
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum EventCategory {
    /// 宏觀事件（FOMC / CPI / NFP）。
    Macro,
    /// 鏈上資金流動（鯨魚轉帳 / 大額 USDT mint）。
    OnchainFlow,
    /// 衍生品市場（funding 異動 / OI spike / liquidation cascade）。
    Derivatives,
    /// 交易所公告（listing / delisting / 維護）。
    ExchangeEvent,
    /// 未明 / 預設。
    #[default]
    Unknown,
}

/// EventAlert — Scout intel_objects 派出的單筆事件警報（Phase D 真實 wire）。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EventAlert {
    pub event_id: ScoutEventId,
    pub category: EventCategory,
    /// 影響的 symbols（empty = 全市場）。
    pub affected_symbols: Vec<String>,
    /// 嚴重度 0.0 – 1.0（Phase D 由 Scout 評分）。
    pub severity: f64,
    pub emitted_ms: i64,
    /// 事件失效時間戳；策略 on_tick 看 `now < expiry_ms` 的 active 事件。
    pub expiry_ms: i64,
}

/// RegimeTag — market regime 分類（W-AUDIT-8a 用既有 ATR / Hurst / EwmaVol
/// 組合計算，**不新增 ML 模型**）。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum RegimeTag {
    /// 趨勢上行。
    TrendingUp,
    /// 趨勢下行。
    TrendingDown,
    /// 區間震盪。
    Ranging,
    /// 高波動 / 不穩定。
    Volatile,
    /// 未明 / 樣本不足 / 默認。
    #[default]
    Unknown,
}

/// SentimentPanel — 外部社群 / 新聞情緒 panel（**W-AUDIT-8a stub-only，本 wave
/// 永遠 `None`**）。
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct SentimentPanel {
    /// 各 symbol sentiment score（-1.0 = 極度看空，+1.0 = 極度看多）。
    pub per_symbol_score: std::collections::HashMap<String, f64>,
    pub snapshot_ts_ms: i64,
    pub source_tier: String,
}

/// BtcLeadLagPanel — Sprint N+1 W2 BTC→Alt 跨資產 lead-lag panel（候選 C
/// W-AUDIT-8c 落地版 stub）。
///
/// 來源（Sprint N+1 W2 IMPL）：BTCUSDT 1m kline → lead signal（return / volume /
/// orderbook imbalance over N=60-300s window）→ Python writer 寫
/// `panel.btc_lead_lag_panel`（V088 migration；retention 14d）。
///
/// **執行邊界（Sprint N+1 W2 paper-only）**：本 wave Strategy 只在 paper engine
/// mode 接此 panel；demo / live_demo / live → `AlphaSurface.btc_lead_lag = None`
/// （fence 由 `tick_pipeline/on_tick/step_4_5_dispatch.rs` engine_mode gate
/// 主防線實施，trait 端不知此 fence；策略消費端 `surface.btc_lead_lag.is_none()`
/// → skip 即可，不需查 engine_mode）。BUSDT cohort 排除（per ADR-0018）。
///
/// **Lead-lag 信號契約**：`btc_lead_return_pct` 必為 strict `shift(N)` 不含
/// current bar（避免 look-ahead bias，per `feedback_indicator_lookahead_bias`）。
/// `lead_window_secs` 三檔之一（60 / 120 / 300）；`alt_xcorr` 為 rolling 1h
/// cross-correlation；`alt_expected_dir` 三值（−1 / 0 / +1）。
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct BtcLeadLagPanel {
    /// Cohort alt symbols（不含 BTCUSDT；BUSDT 排除 per ADR-0018）。
    pub alt_symbols: Vec<String>,
    /// BTC lead signal：N 秒 return（strict shift(N) 禁含 current bar）。
    pub btc_lead_return_pct: f64,
    /// BTC lead window seconds（60 / 120 / 300 三檔之一）。
    pub lead_window_secs: u32,
    /// 各 alt symbol 對 BTC lead signal 的 cross-correlation（rolling 1h）。
    pub alt_xcorr: Vec<f64>,
    /// 各 alt symbol 預期 mean reversion / momentum direction（−1 / 0 / +1）。
    pub alt_expected_dir: Vec<i8>,
    pub snapshot_ts_ms: i64,
    pub source_tier: String,
}

// ─────────────────────────────────────────────────────────────────────────
// AlphaSurface — Tier 1-4 first-class bundle
// ─────────────────────────────────────────────────────────────────────────

/// AlphaSurface — Tier 1-4 alpha source bundle 的 borrow-only 視圖。
///
/// 生命週期 `'a` 與 `TickContext<'a>` 同源；surface 只是把 collector / IPC slot
/// 的引用打包，永不 own / 永不 deep clone。Phase A 完成後 5 既存策略仍只取
/// Tier 1（`indicators` / `indicators_5m`），Tier 2-4 全 `None` / 預設值；
/// Phase B/C/D 漸進 wire 進真實 collector。
///
/// **策略端契約**：策略 ctor `declared_alpha_sources()` 聲明吃哪些 tag；
/// `on_tick` 內若聲稱吃 Tier 2-4 tag 但對應 field 為 `None` →
/// **fail-closed 跳過自身 alpha source**，**禁** fallback 到 TA1m。
#[derive(Debug, Clone)]
pub struct AlphaSurface<'a> {
    // ── Tier 1 — TA / OHLCV ──
    /// 1m kline-derived TA snapshot（既有 `TickContext.indicators` 子集）。
    pub indicators: Option<&'a IndicatorSnapshot>,
    /// 5m kline-derived TA snapshot（既有 `TickContext.indicators_5m` 子集）。
    pub indicators_5m: Option<&'a IndicatorSnapshot>,

    // ── Tier 2 — 跨資產 / 截面 panel ──
    pub funding_curve: Option<&'a FundingCurveSnapshot>,
    pub basis_curve: Option<&'a BasisCurveSnapshot>,
    pub oi_delta_panel: Option<&'a OIDeltaPanel>,

    // ── Tier 3 — Microstructure ──
    pub orderflow: Option<&'a OrderflowFeatures>,
    pub liquidation_pulse: Option<&'a LiquidationPulse>,

    // ── Tier 4 — 信息流 ──
    /// Active EventAlert slice（empty = 無 active 事件）。
    pub event_alerts: &'a [EventAlert],
    /// Market regime tag。Default `RegimeTag::Unknown`。
    pub regime: RegimeTag,
    pub sentiment_panel: Option<&'a SentimentPanel>,

    // ── Sprint N+1 W2 — 跨資產 lead-lag panel（paper-only） ──
    /// BTC→Alt lead-lag panel 引用（**paper-only**；fence 由 step_4_5_dispatch
    /// engine_mode gate 實施，demo / live_demo / live 永遠 None）。
    pub btc_lead_lag: Option<&'a BtcLeadLagPanel>,
}

impl<'a> AlphaSurface<'a> {
    /// Return whether a declared alpha source has concrete data on this surface.
    ///
    /// This is the single mapping from `AlphaSourceTag` to the corresponding
    /// `AlphaSurface` field. Dispatch metrics, future fail-closed strategy
    /// guards, and tests should use this Interface instead of re-encoding the
    /// match at each call site.
    pub fn is_source_available(&self, tag: AlphaSourceTag) -> bool {
        match tag {
            AlphaSourceTag::Ta1m => self.indicators.is_some(),
            AlphaSourceTag::Ta5m => self.indicators_5m.is_some(),
            AlphaSourceTag::FundingSkew => self.funding_curve.is_some(),
            AlphaSourceTag::Basis => self.basis_curve.is_some(),
            AlphaSourceTag::OiDeltaPanel => self.oi_delta_panel.is_some(),
            AlphaSourceTag::OrderflowImbalance => self.orderflow.is_some(),
            AlphaSourceTag::LiquidationCascade => self.liquidation_pulse.is_some(),
            AlphaSourceTag::EventDriven => !self.event_alerts.is_empty(),
            AlphaSourceTag::CrossAsset => self.btc_lead_lag.is_some(),
            AlphaSourceTag::Sentiment => self.sentiment_panel.is_some(),
        }
    }

    /// 構造 Tier 1 only surface（Phase A 預設用法）：把 `indicators` /
    /// `indicators_5m` 引用搬入 surface，Tier 2-4 全 `None` / 預設值。
    ///
    /// `ctx_indicators` / `ctx_indicators_5m` 通常即 `TickContext.indicators` /
    /// `TickContext.indicators_5m`；borrow scope 與 TickContext 同源。
    pub const fn tier1_only(
        indicators: Option<&'a IndicatorSnapshot>,
        indicators_5m: Option<&'a IndicatorSnapshot>,
    ) -> Self {
        Self {
            indicators,
            indicators_5m,
            funding_curve: None,
            basis_curve: None,
            oi_delta_panel: None,
            orderflow: None,
            liquidation_pulse: None,
            event_alerts: &[],
            regime: RegimeTag::Unknown,
            sentiment_panel: None,
            btc_lead_lag: None,
        }
    }

    /// 構造 empty surface — 全 Tier 為 `None` / 預設；測試與 fallback 用。
    pub const fn empty() -> AlphaSurface<'static> {
        AlphaSurface {
            indicators: None,
            indicators_5m: None,
            funding_curve: None,
            basis_curve: None,
            oi_delta_panel: None,
            orderflow: None,
            liquidation_pulse: None,
            event_alerts: &[],
            regime: RegimeTag::Unknown,
            sentiment_panel: None,
            btc_lead_lag: None,
        }
    }
}

impl Default for AlphaSurface<'static> {
    fn default() -> Self {
        Self::empty()
    }
}

/// Empty AlphaSurface 全域常量 — 測試與所有 callsite 不需要 alpha source
/// 接線時可用此引用，避免每處重複構造。
pub static EMPTY_ALPHA_SURFACE: AlphaSurface<'static> = AlphaSurface {
    indicators: None,
    indicators_5m: None,
    funding_curve: None,
    basis_curve: None,
    oi_delta_panel: None,
    orderflow: None,
    liquidation_pulse: None,
    event_alerts: &[],
    regime: RegimeTag::Unknown,
    sentiment_panel: None,
    btc_lead_lag: None,
};

// ─────────────────────────────────────────────────────────────────────────
// Tests
// ─────────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    /// Tag → metric label 對齊 spec §2.5 lowercase snake_case 命名。
    #[test]
    fn alpha_source_tag_metric_label_lowercase_snake_case() {
        let cases: &[(AlphaSourceTag, &str)] = &[
            (AlphaSourceTag::Ta1m, "ta_1m"),
            (AlphaSourceTag::Ta5m, "ta_5m"),
            (AlphaSourceTag::FundingSkew, "funding_skew"),
            (AlphaSourceTag::Basis, "basis"),
            (AlphaSourceTag::OiDeltaPanel, "oi_delta_panel"),
            (AlphaSourceTag::OrderflowImbalance, "orderflow_imbalance"),
            (AlphaSourceTag::LiquidationCascade, "liquidation_cascade"),
            (AlphaSourceTag::EventDriven, "event_driven"),
            (AlphaSourceTag::CrossAsset, "cross_asset"),
            (AlphaSourceTag::Sentiment, "sentiment"),
        ];
        for (tag, expected) in cases {
            assert_eq!(tag.as_metric_label(), *expected);
            assert_eq!(format!("{}", tag), *expected);
        }
    }

    /// 驗證 `as_metric_label` 與 `serde::Serialize` 輸出語義一致。
    #[test]
    fn alpha_source_tag_serde_matches_metric_label() {
        for tag in [
            AlphaSourceTag::Ta1m,
            AlphaSourceTag::Ta5m,
            AlphaSourceTag::FundingSkew,
            AlphaSourceTag::Basis,
            AlphaSourceTag::OiDeltaPanel,
            AlphaSourceTag::OrderflowImbalance,
            AlphaSourceTag::LiquidationCascade,
            AlphaSourceTag::EventDriven,
            AlphaSourceTag::CrossAsset,
            AlphaSourceTag::Sentiment,
        ] {
            // serde 會用 quoted JSON string，因此 metric label 需 wrap 雙引號比對。
            let json = serde_json::to_string(&tag).unwrap();
            let expected = format!("\"{}\"", tag.as_metric_label());
            assert_eq!(json, expected);
        }
    }

    #[test]
    fn empty_alpha_surface_all_none() {
        let s = AlphaSurface::empty();
        assert!(s.indicators.is_none());
        assert!(s.indicators_5m.is_none());
        assert!(s.funding_curve.is_none());
        assert!(s.basis_curve.is_none());
        assert!(s.oi_delta_panel.is_none());
        assert!(s.orderflow.is_none());
        assert!(s.liquidation_pulse.is_none());
        assert!(s.event_alerts.is_empty());
        assert_eq!(s.regime, RegimeTag::Unknown);
        assert!(s.sentiment_panel.is_none());
        assert!(s.btc_lead_lag.is_none());
    }

    /// Tier 1 only constructor 把 indicator 引用 wire 進，其餘 Tier 維持 default。
    #[test]
    fn tier1_only_wires_indicators_and_keeps_others_none() {
        let snap = IndicatorSnapshot::default();
        let s = AlphaSurface::tier1_only(Some(&snap), None);
        assert!(s.indicators.is_some());
        assert!(s.indicators_5m.is_none());
        // 其餘 Tier 保持 Phase A default。
        assert!(s.funding_curve.is_none());
        assert!(s.basis_curve.is_none());
        assert!(s.oi_delta_panel.is_none());
        assert!(s.orderflow.is_none());
        assert!(s.liquidation_pulse.is_none());
        assert!(s.event_alerts.is_empty());
        assert_eq!(s.regime, RegimeTag::Unknown);
        assert!(s.sentiment_panel.is_none());
        assert!(s.btc_lead_lag.is_none());
    }

    /// Sprint N+1 W2 BtcLeadLagPanel: trait skeleton 預寫 acceptance — 三
    /// constructor 全部 default `btc_lead_lag = None`，paper-only fence 由
    /// step_4_5_dispatch 構造階段控制；trait 端永遠 default None。
    #[test]
    fn btc_lead_lag_default_none() {
        let snap = IndicatorSnapshot::default();
        // empty / tier1_only / EMPTY_ALPHA_SURFACE 三 constructor 全 None
        let e = AlphaSurface::empty();
        assert!(
            e.btc_lead_lag.is_none(),
            "AlphaSurface::empty() must default btc_lead_lag to None"
        );
        let t1 = AlphaSurface::tier1_only(Some(&snap), Some(&snap));
        assert!(
            t1.btc_lead_lag.is_none(),
            "AlphaSurface::tier1_only() must default btc_lead_lag to None"
        );
        let s = &EMPTY_ALPHA_SURFACE;
        assert!(
            s.btc_lead_lag.is_none(),
            "EMPTY_ALPHA_SURFACE static must default btc_lead_lag to None"
        );
        // Default impl 自動繼承
        let d: AlphaSurface<'static> = AlphaSurface::default();
        assert!(d.btc_lead_lag.is_none());

        // 顯式構造一個 panel borrow，確認 lifetime 約束 OK
        let panel = BtcLeadLagPanel {
            alt_symbols: vec!["ETHUSDT".to_string()],
            btc_lead_return_pct: 0.5,
            lead_window_secs: 60,
            alt_xcorr: vec![0.7],
            alt_expected_dir: vec![1],
            snapshot_ts_ms: 1715000000000,
            source_tier: "test".to_string(),
        };
        let s_with_panel = AlphaSurface {
            btc_lead_lag: Some(&panel),
            ..AlphaSurface::empty()
        };
        assert!(s_with_panel.btc_lead_lag.is_some());
        let p = s_with_panel.btc_lead_lag.unwrap();
        assert_eq!(p.lead_window_secs, 60);
        assert_eq!(p.alt_symbols, vec!["ETHUSDT".to_string()]);
    }

    #[test]
    fn alpha_surface_availability_maps_cross_asset_panel() {
        let panel = BtcLeadLagPanel {
            alt_symbols: vec!["ETHUSDT".to_string()],
            btc_lead_return_pct: 0.4,
            lead_window_secs: 60,
            alt_xcorr: vec![0.6],
            alt_expected_dir: vec![1],
            snapshot_ts_ms: 1715000000000,
            source_tier: "test".to_string(),
        };
        let surface = AlphaSurface {
            btc_lead_lag: Some(&panel),
            ..AlphaSurface::empty()
        };

        assert!(surface.is_source_available(AlphaSourceTag::CrossAsset));
        assert!(!AlphaSurface::empty().is_source_available(AlphaSourceTag::CrossAsset));
    }

    /// EMPTY_ALPHA_SURFACE 靜態常量 cheap reference — 測 Default 結果一致。
    #[test]
    fn static_empty_alpha_surface_matches_empty_constructor() {
        let dyn_empty = AlphaSurface::empty();
        let static_empty = &EMPTY_ALPHA_SURFACE;
        assert_eq!(
            dyn_empty.indicators.is_none(),
            static_empty.indicators.is_none()
        );
        assert_eq!(
            dyn_empty.event_alerts.len(),
            static_empty.event_alerts.len()
        );
        assert_eq!(dyn_empty.regime, static_empty.regime);
    }

    #[test]
    fn regime_tag_default_is_unknown() {
        assert_eq!(RegimeTag::default(), RegimeTag::Unknown);
    }

    #[test]
    fn liquidation_side_default_is_mixed() {
        assert_eq!(LiquidationSide::default(), LiquidationSide::Mixed);
    }
}
