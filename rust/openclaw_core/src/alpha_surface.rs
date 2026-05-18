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
// W-AUDIT-8a B-REM-5 — Source Availability 共享 schema
// ─────────────────────────────────────────────────────────────────────────
//
// 為什麼需要本 enum：
// - 既存 `source_tier` 字段（funding_curve / oi_delta / btc_lead_lag 等
//   snapshot 中）= 自由文本 provenance（如 "bybit_v5_ws_tickers"），用於
//   PG 寫入 lineage 對齊，無分類語意；
// - V050 `evidence_source_tier` = replay lineage enum
//   (`calibrated_replay` / `synthetic_replay` / `counterfactual_replay`)，
//   是 fill-level 不是 surface-level；
// - 下游 6 個 worktree（B-REM-2 funding consumer report / B-REM-3 OI consumer
//   report / C2 orderflow / C3 spread / D1 event / D2 regime / D3 sentiment）
//   的 candidate report `unavailable_reason` 字段需要分類語意，把「為什麼
//   AlphaSurface 對應 field = None」的真正成因標準化，方便 Stage 0R promotion
//   gate 與 healthcheck 做精確分類聚合（不能只看「None vs Some」黑盒）。
//
// 設計約束：
// - `Available { tier: AvailabilitySource }` carries the positive case so
//   downstream report writers do not need a 雙 enum（availability + tier）；
// - Unavailable variants 是 exhaustive 的「為什麼 None」原因清單；
// - **enum 添加 / 刪除 / 重命名觸發 ADR**（per PA spec §6.2 + 配套
//   `docs/adr/0023-source-availability-schema.md`）；
// - Serde 與 metric label snake_case 一致，符合既有 PG / Prometheus 命名。

/// AvailabilitySource — 當 alpha source 可用時，標記「資料來自哪一層 producer」。
///
/// 用於 `SourceAvailability::Available { tier }`。本 enum 描述「可用時的 producer
/// tier」，與既存 `source_tier` 字段（自由文本 provenance string）正交：
/// - 既存 `source_tier` = "bybit_v5_ws_tickers" 描述具體 endpoint；
/// - 本 enum 描述「實時 WS 還是 REST 冷啟動 seed」這一語意層次。
///
/// 下游 candidate report 可同時帶兩者：本 enum 給 promotion gate 做語意分類，
/// 既存字串給 audit trail 對齊 PG row。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AvailabilitySource {
    /// WS-first 實時源（Bybit V5 WS / orderbook.50 / allLiquidation / tickers）。
    WsLive,
    /// REST 冷啟動 seed（pipeline 啟動前 N 分鐘的 REST one-shot 補齊；後續 WS 接管）。
    RestSeed,
}

impl AvailabilitySource {
    /// Snake_case 字串（對齊 Prometheus label / PG enum）。
    pub const fn as_metric_label(self) -> &'static str {
        match self {
            Self::WsLive => "ws_live",
            Self::RestSeed => "rest_seed",
        }
    }
}

impl std::fmt::Display for AvailabilitySource {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.as_metric_label())
    }
}

/// SourceAvailability — alpha source 可用性 + 不可用原因的標準化分類。
///
/// 共享 schema，6 個下游 worktree（B-REM-2 / B-REM-3 / C2 / C3 / D1 / D2 / D3）
/// 在 candidate report 的 `availability` 或 `unavailable_reason` 欄位引用本 enum：
///
/// | 下游 worktree | 引用點 |
/// |---|---|
/// | B-REM-2 (funding consumer report) | `surface.funding_curve` 可用性 |
/// | B-REM-3 (OI consumer report) | `surface.oi_delta_panel` 可用性 + 5 變體（absent / stale / missing-symbol / non-finite-absolute / non-finite-delta） |
/// | C2 (orderflow) | `surface.orderflow` 可用性 |
/// | C3 (spread) | C2 panel spread 欄位可用性 |
/// | D1 (event) | `surface.event_alerts` 可用性 |
/// | D2 (regime) | `surface.regime != Unknown` 可用性 |
/// | D3 (sentiment) | `surface.sentiment_panel` 可用性 |
///
/// 治理：
/// - **添加 variant 必經 ADR**（per ADR-0023 §Decision）；
/// - serde / `as_metric_label` 必同時更新；
/// - 既存字串字段（panel snapshot 的 `source_tier`）**不被本 enum 取代**，兩者並存。
///
/// fail-closed 契約：B-REM-3 unit test 須能合成每條 unavailable variant，
/// 證明 strategy consumer 對每條都 fail-closed（不退化到 TA1m fallback）。
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum SourceAvailability {
    /// Alpha source 在當前 tick 可用；`tier` 標記資料來自哪一層 producer。
    Available { tier: AvailabilitySource },
    /// 該 symbol 不在當前 cohort（如 BUSDT 在 BTCUSDT cohort 外、新上市 symbol
    /// 未進 25-symbol panel）；非錯誤，是定義域排除。
    CohortExcluded,
    /// Panel 存在但 freshness 超 threshold（如 funding 1h-cycle panel 過 75min
    /// 仍未更新；OI 5m panel 過 15min 未更新）。
    StalePanel,
    /// Panel 存在但對應 symbol 缺失（panel 涵蓋部分 cohort 而非全部；新上市未補）。
    MissingSymbol,
    /// 數值非有限（NaN / Inf）— 標記 absolute 值錯誤（如 oi_abs = NaN）。
    NonFiniteAbsolute,
    /// 數值非有限（NaN / Inf）— 標記 delta 值錯誤（如 oi_delta_5m_pct = Inf）。
    NonFiniteDelta,
    /// Panel slot 完全不存在（IPC slot 未 publish / collector 未啟動 / try_read
    /// soft-fail）。Phase A 全 None 的預設原因。
    Absent,
}

impl SourceAvailability {
    /// 為 Prometheus / PG 對齊提供 short label（不含 tier 細節）。
    ///
    /// Available 變體統一回 `"available"`（tier 細節由
    /// `availability_tier_label()` 提供，避免 cardinality 爆炸）。
    pub const fn as_metric_label(&self) -> &'static str {
        match self {
            Self::Available { .. } => "available",
            Self::CohortExcluded => "cohort_excluded",
            Self::StalePanel => "stale_panel",
            Self::MissingSymbol => "missing_symbol",
            Self::NonFiniteAbsolute => "non_finite_absolute",
            Self::NonFiniteDelta => "non_finite_delta",
            Self::Absent => "absent",
        }
    }

    /// Tier 子標籤（Available 時回 ws_live / rest_seed；否則回 None）。
    pub const fn availability_tier_label(&self) -> Option<&'static str> {
        match self {
            Self::Available { tier } => Some(tier.as_metric_label()),
            _ => None,
        }
    }

    /// `is_available()` — Surface field 可被策略安全消費的快速判斷。
    pub const fn is_available(&self) -> bool {
        matches!(self, Self::Available { .. })
    }

    /// `unavailable_reason()` — 不可用時的成因 label（不含 tier 細節）；
    /// Available 時回 None。下游 report unavailable_reason 欄位直接寫入此值。
    pub fn unavailable_reason(&self) -> Option<&'static str> {
        if self.is_available() {
            None
        } else {
            Some(self.as_metric_label())
        }
    }
}

impl std::fmt::Display for SourceAvailability {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Available { tier } => write!(f, "available({})", tier),
            other => write!(f, "{}", other.as_metric_label()),
        }
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

/// LiquidationPulse — per-symbol Bybit `allLiquidation` cluster detection。
///
/// 為什麼是 per-symbol：清算是局部現象（單一 perp symbol 的 long/short 倉位被強平），
/// 策略需要按 symbol 取訊號（如 BTC 強平 cluster 不該影響 ETH 策略決策）。
/// 本結構是「單個 symbol 的當前 pulse 視窗摘要」，由
/// [`LiquidationPulsePanel`] 收納所有 cohort symbol。
///
/// **狀態 revived（2026-05-17）** — C1 24h proof PASS_C1_PROOF_CANDIDATE
/// (commit 82ab71eb) 通過後，2026-05-17 commit 0e8a8ae8 revive
/// `allLiquidation.{symbol}` production 訂閱；market.liquidations 已在
/// V095 (commit ef7ea6c2) 把 PK 升為 `(symbol, ts, side, qty, price)` 不再
/// lossy。本 wave (W-AUDIT-8a C1-LIQ-WRITER) 加 panel provider，alpha source
/// 仍 governance-gated（producer 寫 IPC slot，但 W-AUDIT-8c strategy 才會吃）。
///
/// **BB cor-side 映射不變式**（per C1 v2 proof + ws_client/parsers.rs:344-348）：
///   - Bybit `side = "Buy"`  ⇒ `LiquidationSide::LongLiquidated`（多頭被強平，
///     即 long 倉位被強制買回對手單；通常價格下跌）
///   - Bybit `side = "Sell"` ⇒ `LiquidationSide::ShortLiquidated`（空頭被強平，
///     即 short 倉位被強制賣回對手單；通常價格上漲）
///   寫反 = alpha 訊號反向 = 直接 trade loss。
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct LiquidationPulse {
    /// Rolling 視窗內的單一 symbol 強平事件（5m 視窗，per spec §6.1）。
    pub recent_events: Vec<LiquidationEvent>,
    /// Cluster magnitude — long_liquidation notional + short_liquidation notional
    /// 兩側合計的 5m rolling sum（USD-equivalent = qty × price）；下游策略可
    /// 對其取 z-score / percentile rank 作訊號強度。
    pub cluster_notional_5m: f64,
    /// Long-side 5m rolling notional（Bybit side="Buy" 強平 long 倉位）。
    pub long_notional_5m: f64,
    /// Short-side 5m rolling notional（Bybit side="Sell" 強平 short 倉位）。
    pub short_notional_5m: f64,
    /// Cluster event count — 5m 視窗內事件總筆數（避免 single-large-event 假訊號）。
    pub event_count_5m: u32,
    /// Dominant side — 5m notional 中佔比 ≥ 60% 的方向；否則 `Mixed`。
    pub dominant_side: LiquidationSide,
    /// 本 pulse 快照時間戳（ms epoch）；對齊 panel 整體 snapshot_ts_ms。
    pub snapshot_ts_ms: i64,
}

/// LiquidationPulsePanel — per-symbol 強平 pulse 集合 panel。
///
/// MODULE_NOTE：
///   - 收納 cohort 各 symbol 的當前 `LiquidationPulse` 摘要；以 HashMap 對齊
///     既有 funding_curve / oi_delta_panel 的 cross-symbol panel 命名語義；
///   - 由 `panel_aggregator::liquidation_pulse::LiquidationPulseAggregator`
///     從 `PriceEventKind::Liquidation` 事件流彙整產生，60s 視窗 flush；
///   - **沒有 PG hypertable 寫入** — market.liquidations 已存原始 row-level data
///     (V095)，本 panel 僅為 in-memory IPC slot snapshot；
///   - 為下游 W-AUDIT-8c liquidation cluster reaction strategy 提供 hot path
///     讀取，不主動 trigger 任何 trade（governance gate 仍由 IntentRouter 強制）。
///
/// 設計約束：
///   - panel 內 HashMap 鍵為 symbol（與 cohort 對齊；non-cohort silent ignored）；
///   - snapshot_ts_ms 為 panel 級時間戳，個別 pulse.snapshot_ts_ms 應一致；
///   - source_tier 為 `"bybit_v5_ws_all_liquidation"`（與既有 panel 命名風格對齊）。
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct LiquidationPulsePanel {
    /// 各 symbol 的當前 5m pulse 摘要；HashMap 確保策略端按 symbol O(1) lookup。
    pub pulses: std::collections::HashMap<String, LiquidationPulse>,
    /// Panel 級快照時間戳（ms epoch）；aggregator flush 時統一覆蓋各 pulse。
    pub snapshot_ts_ms: i64,
    /// Source tier 字串（producer endpoint provenance；對齊 PG / Prometheus
    /// label 風格）。固定 `"bybit_v5_ws_all_liquidation"`，B-REM-5
    /// AvailabilitySource 接線後語義升級為 `WsLive`。
    pub source_tier: String,
}

impl LiquidationPulsePanel {
    /// 取單一 symbol 的當前 pulse（不存在或無事件時回 None）。
    ///
    /// 為什麼 borrowing 介面：避免每次 lookup clone HashMap entry；策略 hot path
    /// 直接讀引用，lifetime 與 panel snapshot scope 同源。
    pub fn pulse_for(&self, symbol: &str) -> Option<&LiquidationPulse> {
        self.pulses.get(symbol)
    }

    /// Panel 覆蓋的 symbol 數（test + observability 用）。
    pub fn symbol_count(&self) -> usize {
        self.pulses.len()
    }
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
    /// W-AUDIT-8a C1-LIQ-WRITER (2026-05-18) — per-symbol liquidation pulse panel
    /// 引用；C1 revival 後由 LiquidationPulseAggregator IPC slot 注入。
    /// `None` = aggregator 未 spawn / 視窗內無事件 / slot try_read 失敗，
    /// 策略端必 fail-closed（per AlphaSurface 契約 §設計約束）。
    pub liquidation_pulse: Option<&'a LiquidationPulsePanel>,

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

    // ─────────────────────────────────────────────────────────────────────
    // W-AUDIT-8a B-REM-5 — SourceAvailability schema 測試
    // 為什麼：6 個下游 worktree（B-REM-2/3、C2/3、D1/2/3）都會引用本 enum。
    // 命名 / variant 順序 / serde 序列化都不能事後改 → 必先寫 fixture-style
    // 鎖死 test。
    // ─────────────────────────────────────────────────────────────────────

    #[test]
    fn availability_source_metric_labels_snake_case() {
        // ws_live / rest_seed 是 6 個下游 worktree 共用契約字串。
        assert_eq!(AvailabilitySource::WsLive.as_metric_label(), "ws_live");
        assert_eq!(AvailabilitySource::RestSeed.as_metric_label(), "rest_seed");
        assert_eq!(format!("{}", AvailabilitySource::WsLive), "ws_live");
        assert_eq!(format!("{}", AvailabilitySource::RestSeed), "rest_seed");
    }

    #[test]
    fn availability_source_serde_matches_snake_case() {
        // 為什麼：Python writer 與 Rust consumer 透過 serde JSON 對齊，
        // serde 字串必與 metric label 一致，否則跨語言 round-trip 會 silent drift。
        for s in [AvailabilitySource::WsLive, AvailabilitySource::RestSeed] {
            let json = serde_json::to_string(&s).unwrap();
            let expected = format!("\"{}\"", s.as_metric_label());
            assert_eq!(json, expected);
            // round-trip
            let back: AvailabilitySource = serde_json::from_str(&json).unwrap();
            assert_eq!(back, s);
        }
    }

    #[test]
    fn source_availability_metric_labels_exhaustive() {
        // 鎖死 6 個下游 worktree 引用的 label 字串。改動任一字串需動 ADR-0023。
        let cases: &[(SourceAvailability, &str)] = &[
            (
                SourceAvailability::Available {
                    tier: AvailabilitySource::WsLive,
                },
                "available",
            ),
            (
                SourceAvailability::Available {
                    tier: AvailabilitySource::RestSeed,
                },
                "available",
            ),
            (SourceAvailability::CohortExcluded, "cohort_excluded"),
            (SourceAvailability::StalePanel, "stale_panel"),
            (SourceAvailability::MissingSymbol, "missing_symbol"),
            (SourceAvailability::NonFiniteAbsolute, "non_finite_absolute"),
            (SourceAvailability::NonFiniteDelta, "non_finite_delta"),
            (SourceAvailability::Absent, "absent"),
        ];
        for (avail, expected) in cases {
            assert_eq!(avail.as_metric_label(), *expected);
        }
    }

    #[test]
    fn source_availability_tier_label_only_for_available() {
        // tier label 只在 Available 出現；其他 variant 必 None，否則 Prometheus
        // cardinality 會爆炸（unavailable 不該帶 tier 子分類）。
        assert_eq!(
            SourceAvailability::Available {
                tier: AvailabilitySource::WsLive,
            }
            .availability_tier_label(),
            Some("ws_live")
        );
        assert_eq!(
            SourceAvailability::Available {
                tier: AvailabilitySource::RestSeed,
            }
            .availability_tier_label(),
            Some("rest_seed")
        );
        for unavailable in [
            SourceAvailability::CohortExcluded,
            SourceAvailability::StalePanel,
            SourceAvailability::MissingSymbol,
            SourceAvailability::NonFiniteAbsolute,
            SourceAvailability::NonFiniteDelta,
            SourceAvailability::Absent,
        ] {
            assert!(
                unavailable.availability_tier_label().is_none(),
                "unavailable variant must not carry tier label: {:?}",
                unavailable
            );
        }
    }

    #[test]
    fn source_availability_is_available_and_unavailable_reason_inverse() {
        // is_available() == true 時 unavailable_reason() 必 None；
        // false 時 unavailable_reason() 必 Some。下游 report 字段直接用。
        let available = SourceAvailability::Available {
            tier: AvailabilitySource::WsLive,
        };
        assert!(available.is_available());
        assert!(available.unavailable_reason().is_none());

        for unavailable in [
            SourceAvailability::CohortExcluded,
            SourceAvailability::StalePanel,
            SourceAvailability::MissingSymbol,
            SourceAvailability::NonFiniteAbsolute,
            SourceAvailability::NonFiniteDelta,
            SourceAvailability::Absent,
        ] {
            assert!(!unavailable.is_available());
            assert_eq!(
                unavailable.unavailable_reason(),
                Some(unavailable.as_metric_label())
            );
        }
    }

    #[test]
    fn source_availability_display_format() {
        // Display 字串契約：
        // - Available -> "available(<tier>)" 帶 tier 細節（給日誌人讀）；
        // - 其他 -> 純 snake_case label。
        assert_eq!(
            format!(
                "{}",
                SourceAvailability::Available {
                    tier: AvailabilitySource::WsLive,
                }
            ),
            "available(ws_live)"
        );
        assert_eq!(
            format!(
                "{}",
                SourceAvailability::Available {
                    tier: AvailabilitySource::RestSeed,
                }
            ),
            "available(rest_seed)"
        );
        assert_eq!(format!("{}", SourceAvailability::StalePanel), "stale_panel");
        assert_eq!(format!("{}", SourceAvailability::Absent), "absent");
    }

    #[test]
    fn source_availability_serde_round_trip_internally_tagged() {
        // Internally-tagged enum (serde tag = "kind") 是 6 個下游 worktree
        // 共用 JSON schema：
        // {"kind":"available","tier":"ws_live"} | {"kind":"absent"} ...
        //
        // 任一變動會破跨語言契約（Python writer / Rust consumer）。
        let cases: &[(SourceAvailability, &str)] = &[
            (
                SourceAvailability::Available {
                    tier: AvailabilitySource::WsLive,
                },
                r#"{"kind":"available","tier":"ws_live"}"#,
            ),
            (
                SourceAvailability::Available {
                    tier: AvailabilitySource::RestSeed,
                },
                r#"{"kind":"available","tier":"rest_seed"}"#,
            ),
            (
                SourceAvailability::CohortExcluded,
                r#"{"kind":"cohort_excluded"}"#,
            ),
            (
                SourceAvailability::StalePanel,
                r#"{"kind":"stale_panel"}"#,
            ),
            (
                SourceAvailability::MissingSymbol,
                r#"{"kind":"missing_symbol"}"#,
            ),
            (
                SourceAvailability::NonFiniteAbsolute,
                r#"{"kind":"non_finite_absolute"}"#,
            ),
            (
                SourceAvailability::NonFiniteDelta,
                r#"{"kind":"non_finite_delta"}"#,
            ),
            (SourceAvailability::Absent, r#"{"kind":"absent"}"#),
        ];

        for (value, expected_json) in cases {
            let json = serde_json::to_string(value).unwrap();
            assert_eq!(json, *expected_json, "serialize mismatch for {:?}", value);
            // round-trip
            let back: SourceAvailability = serde_json::from_str(&json).unwrap();
            assert_eq!(&back, value, "round-trip mismatch for {:?}", value);
        }
    }

    /// 下游 worktree 引用 contract 鎖死測試：列舉 6+1 個下游 worktree 與其
    /// 預期使用點。若未來 enum 變動，本 test 不會 fail（純 documentation）
    /// 但提供 ADR-0023 §Decision 的 cross-reference 落地證據。
    #[test]
    fn source_availability_downstream_worktrees_documented() {
        // 6 個下游 worktree 名稱 fixture（per PA report §6.2 + §1 dependency
        // graph）。維護 ADR-0023 必同步更新本列表。
        let downstream = [
            ("B-REM-2", "funding consumer report"),
            ("B-REM-3", "bb_breakout OI consumer report"),
            ("C2-ORDERFLOW", "Tier 3 orderflow panel provider"),
            ("C3-SPREAD", "Tier 3 spread dynamics extension"),
            ("D1-EVENT", "Scout→Rust EventAlert provider"),
            ("D2-REGIME", "RegimeTag provider"),
            ("D3-SENTIMENT", "SentimentPanel provider"),
        ];
        assert_eq!(downstream.len(), 7, "downstream worktree count fixture");
    }

    // ─────────────────────────────────────────────────────────────────────
    // W-AUDIT-8a C1-LIQ-WRITER (2026-05-18) — LiquidationPulsePanel
    // ─────────────────────────────────────────────────────────────────────

    /// 為什麼測 default：panel 空字典是「aggregator 尚未產生 / 視窗無事件」
    /// 的合法狀態，consumer 必能透過 `pulses.is_empty()` / `pulse_for(sym)`
    /// 取到 None 不 panic。
    #[test]
    fn liquidation_pulse_panel_default_is_empty() {
        let panel = LiquidationPulsePanel::default();
        assert!(panel.pulses.is_empty());
        assert_eq!(panel.symbol_count(), 0);
        assert_eq!(panel.snapshot_ts_ms, 0);
        assert!(panel.source_tier.is_empty());
        assert!(panel.pulse_for("BTCUSDT").is_none());
    }

    /// 為什麼測 pulse_for：策略 hot path 按 symbol O(1) lookup；
    /// 不存在 symbol 必回 None 而非 panic。
    #[test]
    fn liquidation_pulse_panel_lookup_per_symbol() {
        let mut pulses = std::collections::HashMap::new();
        pulses.insert(
            "BTCUSDT".to_string(),
            LiquidationPulse {
                recent_events: vec![],
                cluster_notional_5m: 100_000.0,
                long_notional_5m: 80_000.0,
                short_notional_5m: 20_000.0,
                event_count_5m: 3,
                dominant_side: LiquidationSide::LongLiquidated,
                snapshot_ts_ms: 1_700_000_060_000,
            },
        );
        let panel = LiquidationPulsePanel {
            pulses,
            snapshot_ts_ms: 1_700_000_060_000,
            source_tier: "bybit_v5_ws_all_liquidation".to_string(),
        };

        assert_eq!(panel.symbol_count(), 1);
        let btc = panel.pulse_for("BTCUSDT").expect("BTCUSDT present");
        assert_eq!(btc.dominant_side, LiquidationSide::LongLiquidated);
        assert!((btc.cluster_notional_5m - 100_000.0).abs() < f64::EPSILON);

        // 不存在 symbol 必 None — fail-closed 契約
        assert!(panel.pulse_for("ETHUSDT").is_none());
    }

    /// 為什麼測 surface availability：surface 端 `is_source_available` 是
    /// dispatch tracking metric 唯一映射；panel 注入後 `LiquidationCascade`
    /// tag 必 true，否則策略無法被 promotion gate 計入。
    #[test]
    fn alpha_surface_liquidation_pulse_panel_availability() {
        let panel = LiquidationPulsePanel::default();
        let surface = AlphaSurface {
            liquidation_pulse: Some(&panel),
            ..AlphaSurface::empty()
        };
        assert!(surface.liquidation_pulse.is_some());
        assert!(surface.is_source_available(AlphaSourceTag::LiquidationCascade));

        // empty surface 必拒 LiquidationCascade（既有 dormant 不變式）
        assert!(!AlphaSurface::empty().is_source_available(AlphaSourceTag::LiquidationCascade));
    }

    /// 為什麼測 BB cor-side 不變式：side 映射寫反 = alpha 反向 = trade loss。
    /// 本 test 在 alpha_surface struct 層直接 assert LiquidationSide 語義契約，
    /// 與 ws_client/tests.rs 的 parser-level test 形成雙重防線。
    #[test]
    fn liquidation_side_bb_corside_mapping_invariant() {
        // Buy 強平 = LongLiquidated（多頭被強制買回）；
        // Sell 強平 = ShortLiquidated（空頭被強制賣回）。
        // 此處只測 enum 語義不變，parser 層映射 test 見 ws_client/tests.rs。
        let long_liq = LiquidationSide::LongLiquidated;
        let short_liq = LiquidationSide::ShortLiquidated;
        assert_ne!(long_liq, short_liq);
        // serde 必輸出 snake_case，對齊 Prometheus / PG label 風格
        let long_json = serde_json::to_string(&long_liq).unwrap();
        let short_json = serde_json::to_string(&short_liq).unwrap();
        assert_eq!(long_json, "\"long_liquidated\"");
        assert_eq!(short_json, "\"short_liquidated\"");
    }
}
