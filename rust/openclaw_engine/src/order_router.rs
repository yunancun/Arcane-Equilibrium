//! M12 OrderRouter trait stub — Sprint 1A-δ adaptive order routing 介面預留 per ADR-0039。
//!
//! MODULE_NOTE
//! 模塊用途：為 v5.8 §2 M12 Adaptive Order Routing 預留 6 method trait 介面 + 周邊
//!   helper struct / enum；Sprint 1A-δ 階段僅交介面骨架，6 method default body 全為
//!   `unimplemented!()` panic（fail-loud），實際 adaptive routing 邏輯延至 Sprint 6+
//!   IMPL 階段。
//! 主要類/函數：
//!   - `OrderRouter` trait（6 method 對齊 ADR-0039 §Decision 1 authoritative signature）
//!   - `UnimplementedOrderRouter` 純 marker default impl struct（建構合法、呼叫 method 全 panic
//!     但 `route_order` 對 Binance venue 走 Y3+ defer early return；對齊 PA spec §6.1 dispatch brief）
//!   - 周邊 11 helper types/struct/enum：`OrderRequest` / `RoutingDecision` / `VenueHealth`
//!     / `NetPosition` / `SlippageEstimate` / `MarketEvent` / `DefensiveAction`
//!     / `MarketSnapshot` / `MakerFillRateStats` / `MakerTier` / `RoutingError`
//! 依賴：
//!   - `openclaw_types::{Venue, AssetClass}`（M13 Wave 1 已 land；本 module use re-exported path）
//!   - 不引入新 crate dep（per Cargo.toml lean dependency 紀律）
//! 硬邊界：
//!   1. 6 method default body 全 `unimplemented!()`，禁默認 `Ok(...)` no-op
//!      （per PA spec §2.2 + ADR-0039 §Decision 1 fail-loud 紀律）。
//!   2. `route_order(Venue::BinancePerp | Venue::BinanceOption)` 走 `Err(RoutingError::VenueDeferred)`
//!      early return（不 panic）— 對齊 PA spec §4.7 Y2 trade defer hardcode（per ADR-0033 §Decision 2）；
//!      此為 5-gate inheritance 紅線，禁 config-driven，禁可被 risk_config TOML override。
//!   3. 禁實作 `maker_fill_rate_30d` 真實 SQL query（per PA spec §3.3 Sprint 6+ IMPL phase 範圍）；
//!      本 sprint 只定義 `MakerFillRateStats` 純 data carrier。
//!   4. trait 物件必滿足 `Send + Sync` dyn safety（caller 可建構 `Box<dyn OrderRouter>`）。
//!   5. Sprint 6+ IMPL 階段始能改 method body；signature 變更需 ADR-0039 amendment + PA / PM sign-off。
//!
//! 參考：
//!   - ADR-0039：`srv/docs/adr/0039-m12-order-router-trait-and-maker-fill-rate-metric.md`
//!   - PA spec：`srv/docs/execution_plan/2026-05-21--m12_order_router_design_spec.md`
//!   - v5.8 §2 M12 (Sprint 1A-δ interface reservation; Sprint 6+ Bybit-only adaptive IMPL)
//!   - Bybit V5 maker/taker fee + rebate tier reference：
//!     `srv/docs/references/2026-04-04--bybit_api_reference.md`（不直接 IMPL；僅 doc comment ref）

// 對齊 Wave 1 M13 既有 enum；OrderRouter 介面以 venue × asset_class 為 routing 軸。
// `openclaw_types` 已透過 `crate::openclaw_types` re-export，無需修改 Cargo.toml。
use openclaw_types::{AssetClass, Venue};

// ============================================================================
// §1 Helper struct / enum — PA spec §2.3 + §3 candidate signature
// ============================================================================

/// `OrderRequest` — `route_order` 主入口參數。
///
/// 為什麼：routing decision 必須能取得完整 order intent（含 venue / side / qty / price /
/// order_type）以判斷 PostOnly / taker / slicing strategy；Sprint 1A-δ 階段只列代表性
/// field 作介面預留，Sprint 6+ IMPL 期可 amend 新增 `variant_id` / `engine_mode` 等
/// extension slot（per PA spec §8 OQ-4）。
#[derive(Debug, Clone)]
pub struct OrderRequest {
    /// 交易 symbol（如 "BTCUSDT" / "ETHUSDT-PERP"；具體格式 Sprint 6+ IMPL 期對齊）。
    pub symbol: String,
    /// 目標 venue — 用於 5-gate inheritance + adaptive routing decision。
    pub venue: Venue,
    /// asset class（perp / spot / option / earn）— 用於 fee schedule + rebate tier 對齊。
    pub asset_class: AssetClass,
    /// 買 / 賣方向（true = buy / false = sell；簡化型，Sprint 6+ IMPL 期可改 enum `OrderSide`）。
    pub side_is_buy: bool,
    /// 委託數量（合約張數 or USD notional；具體單位 Sprint 6+ IMPL 期對齊）。
    pub qty: f64,
    /// 限價（`None` = Market；`Some(p)` = Limit / PostOnly）— Sprint 6+ IMPL 期決定 PostOnly default。
    pub price: Option<f64>,
    /// 委託類型 hint（"market" / "limit" / "postonly" / "ioc" / "fok"；Sprint 6+ enum 化）。
    pub order_type_hint: String,
}

/// `RoutingDecision` — `route_order` 返回值；含 venue + order_type + slicing + tif。
///
/// 為什麼：routing 結果必須能讓下游 `bybit_rest_client` / `execution_listener` 取得
/// 完整委託指令；`decision_id` 對齊 V115 Part 1 audit log PK（Sprint 6+ IMPL 期 INSERT）。
#[derive(Debug, Clone)]
pub struct RoutingDecision {
    /// 實際選定 venue（Sprint 1A-δ 階段 Bybit-only；Y2+ 可能 cross-venue routing per ADR-0033）。
    pub chosen_venue: Venue,
    /// 實際 order type（"postonly" / "limit" / "market" / "ioc"；Sprint 6+ enum 化）。
    pub chosen_order_type: String,
    /// slicing plan：1 = single-shot；2+ = TWAP / iceberg（per Sprint 7-8 IMPL）。
    pub slice_count: u32,
    /// time-in-force（"GTC" / "IOC" / "FOK" / "PostOnly"；Sprint 6+ enum 化）。
    pub time_in_force: String,
    /// route reason — audit「為什麼是 maker / taker」可解釋（對齊 §二 原則 8）。
    pub route_reason: String,
    /// decision UUID — Sprint 6+ 期作 V115 Part 1 PK + M11 replay join key。
    pub decision_id: String,
}

/// `VenueHealth` — `venue_health` 返回值；含 rejection rate / latency / ws connectivity。
///
/// 為什麼：adaptive routing 必須能根據 venue 健康度切換或 throttle；Sprint 6+ IMPL 期
/// 與 `bybit_private_ws_status_writer` + per-venue rejection telemetry 接線。
#[derive(Debug, Clone)]
pub struct VenueHealth {
    /// 24h rejection rate（0.0..1.0）— Sprint 6+ 期由 fills / order rejects telemetry 聚合。
    pub rejection_rate_24h: f64,
    /// p99 latency 毫秒 — Sprint 6+ 期由 IPC / WS 既有 latency histogram 聚合。
    pub latency_p99_ms: f64,
    /// WS connectivity 是否穩定 — 對齊 `bybit_private_ws` + `ws_client` 健康事件。
    pub connection_stable: bool,
}

/// `NetPosition` — `cross_venue_position` 返回值；asset_class 級 cross-venue 淨倉位。
///
/// 為什麼：Y2 Binance trading enable 後（per ADR-0033 §Decision 2）需 cross-venue netting；
/// Y1 期間 Bybit-only 即 single-venue position；Sprint 1A-δ 階段純預留 data carrier。
#[derive(Debug, Clone)]
pub struct NetPosition {
    /// 該 asset_class 跨 venue 加總後 net quantity（買為正、賣為負）。
    pub net_qty: f64,
    /// net notional in USDT — 對齊 risk envelope + portfolio exposure 計算。
    pub net_notional_usdt: f64,
    /// 計算所用 asset_class（caller 可比對 query input 一致）。
    pub asset_class: AssetClass,
}

/// `SlippageEstimate` — `forecast_slippage` 返回值；對齊 ADR-0029 L2 snapshot fidelity。
///
/// 為什麼：adaptive routing PostOnly vs taker 抉擇必須能評估預期滑點 cost；
/// `confidence_interval` 預留 Sprint 6+ IMPL 期 calibration confidence band。
#[derive(Debug, Clone)]
pub struct SlippageEstimate {
    /// 預測滑點（bps；正值代表預期不利移動）。
    pub predicted_slippage_bps: f64,
    /// confidence interval 寬度（bps；正值；0.0 代表未提供）— Sprint 6+ IMPL 期定義。
    pub confidence_interval_bps: f64,
}

/// `MarketEvent` — `reverse_snipe` 入參；market-driven defensive trigger 來源 enum。
///
/// 為什麼：reverse-snipe defense 必須能依事件類型決策（per ADR-0039 §Decision 4
/// PostOnly default + threshold-based taker switch）；Sprint 1A-δ 階段純枚舉預留，
/// 具體判斷邏輯與 confidence threshold Sprint 6+ IMPL 期對齊。
#[derive(Debug, Clone)]
pub enum MarketEvent {
    /// 連環爆倉訊號 — 對齊既有 liquidation feed（per ADR-0038 liquidations source）。
    LiquidationCascade,
    /// 資金費率反向 — 對齊既有 funding feed。
    FundingFlip,
    /// 大幅長影線 / 異常 wick — 對齊既有 K-line / trade tape 訊號。
    LargeWick,
}

/// `DefensiveAction` — `reverse_snipe` 返回值；defensive routing decision enum。
///
/// 為什麼：reverse-snipe defense 觸發後可採行動的範圍有限（per ADR-0039 §Decision 4）；
/// 列舉式設計避免 caller 自由解釋；Sprint 6+ IMPL 期可 amend 新增 variant。
#[derive(Debug, Clone)]
pub enum DefensiveAction {
    /// 退回 PostOnly fallback — 預設防禦（避免 taker 在不利 wick 中成交）。
    PostOnlyFallback,
    /// 暫停下單 — 嚴重市況下完全 halt routing。
    OrderHalt,
    /// 縮量 — 降低 qty 降低暴露（per `dynamic_risk_sizer` Sprint 6+ 對接）。
    SizeReduction,
}

/// `MarketSnapshot` — `forecast_slippage` 入參 placeholder；對齊 ADR-0029 L2 snapshot。
///
/// 為什麼：滑點預測需即時 L2 order book depth + recent trade tape；Sprint 1A-δ 階段
/// 純預留 zero-sized placeholder type，Sprint 6+ IMPL 期對齊 `orderbook_l2_snapshot`
/// + `market.public_trades` 既有結構。
#[derive(Debug, Clone, Default)]
pub struct MarketSnapshot;

/// `MakerTier` — 4-tier rebate eligibility 分類 enum（per ADR-0039 §Decision 2）。
///
/// 為什麼：Bybit ToS rebate tier 評估走 rolling 30d maker fill rate；本 enum 為 ADR-0039
/// 4-tier 分類（具體 threshold precision 待 BB Sprint 6 IMPL 期 confirm per ADR-0039 OQ-1）。
///
/// 命名 note：task dispatch 用 `MakerTier::Penalty` 對應 ADR-0039 §Decision 1 行 110-116 表的
/// `RebateTier::BelowDefault`（< 50% threshold）；兩者語意一致，僅命名差異；當前以 task
/// dispatch 命名為授權，差異記入 PA spec §8 Open Q 衍生 reconciliation。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MakerTier {
    /// Tier 1 maker rebate — 30d maker fill rate ≥ 80%（per Bybit ToS）。
    Tier1,
    /// Tier 2 maker rebate — 30d maker fill rate ≥ 70%（adaptive routing eligible Y2）。
    Tier2,
    /// Default fee schedule — 30d maker fill rate ≥ 50%。
    Default,
    /// Penalty / below-default — 30d maker fill rate < 50%（fee full taker rate；Alert 觸發）。
    Penalty,
}

/// `MakerFillRateStats` — `maker_fill_rate_30d` 返回值；純 data carrier。
///
/// 為什麼：rebate tier 持續監控需 rolling 30d maker / total notional + tier 分類
/// （per ADR-0039 §Decision 2）；Sprint 1A-δ 階段純預留 data carrier，
/// 採樣 SQL（V094 query）+ tier 計算邏輯延至 Sprint 6+ IMPL phase（per PA spec §3.3）。
///
/// 簡化 note：task dispatch 採 3-field 簡化版（window_30d_maker_notional /
/// window_30d_total_notional / current_tier）；ADR-0039 §Decision 1 行 98-108 列 9 field
/// 完整版（含 venue / asset_class / window_start_ts / window_end_ts / maker_fill_ratio /
/// days_in_current_tier）；當前以 task dispatch 為授權，完整版欄位待 Sprint 6+ IMPL 期
/// amend（per PA spec §3.2 末段）。
#[derive(Debug, Clone)]
pub struct MakerFillRateStats {
    /// rolling 30d maker fill notional in USDT（分子）。
    pub window_30d_maker_notional: f64,
    /// rolling 30d total fill notional in USDT（分母）。
    pub window_30d_total_notional: f64,
    /// 當前 rebate tier 分類（per `MakerTier` enum）— Sprint 6+ 期計算邏輯 land。
    pub current_tier: MakerTier,
}

/// `RoutingError` — `route_order` 返回 `Err` variant 集合。
///
/// 為什麼：routing decision 失敗路徑必須能讓 caller 區分「治理拒絕」（Y3+ defer /
/// venue not approved per ADR-0033 + ADR-0040）vs「執行失敗」（venue unreachable /
/// bounds exceeded）；對齊 §二 原則 6 失敗默認收縮 + 原則 8 交易可解釋。
#[derive(Debug, Clone)]
pub enum RoutingError {
    /// 該 venue 不在 ADR 批准清單（DEX / Hyperliquid 等 hardcode 拒絕；
    /// 然 `Venue` enum 自身已不含 Dex / Hyperliquid variant per M13 ADR-0040 Decision 4，
    /// 此 variant 主要供 Sprint 6+ 期未來新 venue 接入 ADR 流程預留錯誤路徑）。
    VenueNotApproved(Venue),
    /// 該 venue 暫緩交易至 future phase — 主要對應 BinancePerp / BinanceOption Y3+ defer
    /// （per ADR-0033 §Decision 2 + ADR-0040 §Decision 1）。
    /// 字串為 defer 來源（如 "Y3+ per ADR-0033"），便於 audit 解釋。
    VenueDeferred(&'static str),
    /// 一般 routing 失敗 — Sprint 6+ IMPL 期可細分；當前作 catch-all。
    RoutingFailed(String),
}

impl std::fmt::Display for RoutingError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::VenueNotApproved(v) => {
                write!(f, "venue '{}' not approved per ADR-0033 / ADR-0040", v)
            }
            Self::VenueDeferred(s) => write!(f, "venue trade deferred: {}", s),
            Self::RoutingFailed(s) => write!(f, "routing failed: {}", s),
        }
    }
}

impl std::error::Error for RoutingError {}

// ============================================================================
// §2 OrderRouter trait — 6 method per ADR-0039 §Decision 1 authoritative
// ============================================================================

/// M12 OrderRouter trait — Adaptive order routing 統一介面預留。
///
/// 為什麼：Sprint 1A-δ 階段鎖定 6 method signature（per ADR-0039 §Decision 1 全表）以
/// 避免後續 Sprint 6+ IMPL drift（interface 一旦 lock 不變，違反需 ADR-0039 amendment）；
/// 6 method default body 全 `unimplemented!()` panic（fail-loud），但 `route_order` 對
/// Binance venue 走 `Err(RoutingError::VenueDeferred)` early return — 此為 5-gate
/// inheritance 紅線 hardcode（per PA spec §4.7 + ADR-0033 §Decision 2）。
///
/// 紀律：
///   - trait 必為 `Send + Sync`（caller 可建構 `Box<dyn OrderRouter>`）。
///   - 6 method signature 100% 對齊 ADR-0039 §Decision 1；method name / param / return
///     變更 = ADR-0039 amendment（需 PA + PM sign-off）。
///   - Sprint 6+ IMPL 階段始能 override default body 改 Bybit-only adaptive routing 邏輯
///     （per ADR-0039 §Decision 6 IMPL phase split）。
///   - `maker_fill_rate_30d` Sprint 1A-δ 不實作 SQL query；純 data carrier signature
///     預留（per PA spec §3.3 + Sprint 6+ V094 query wire-up）。
pub trait OrderRouter: Send + Sync {
    /// Method 1 — 主路由決策入口。
    ///
    /// 為什麼：所有 order intent 在 Guardian + Decision Lease 通過後走此 entry 決定
    /// venue / order_type / slicing / time-in-force；Sprint 6+ IMPL 期 maker-vs-taker
    /// adaptive logic + reverse_snipe trigger 在此匯入。
    ///
    /// **5-gate inheritance 紅線（per PA spec §4.7 + ADR-0033 §Decision 2）**：
    /// `Venue::BinancePerp` / `Venue::BinanceOption` 走 `Err(RoutingError::VenueDeferred("Y3+ per ADR-0033"))`
    /// early return；不可被 risk_config TOML override，不可走 config-driven 開關。
    /// 違反 = 觸發 Y3+ trade enable 紅線 = fail-closed alert。
    fn route_order(
        &self,
        _order_request: &OrderRequest,
    ) -> Result<RoutingDecision, RoutingError> {
        unimplemented!(
            "M12 OrderRouter::route_order — Sprint 6+ Bybit-only IMPL pending；\
             Sprint 1A-δ 階段僅接口預留 + Binance Y3+ defer hardcode；\
             見 ADR-0039 §Decision 1 method 1 + §Decision 6 IMPL phase + PA spec §4.7"
        )
    }

    /// Method 2 — venue 健康度查詢。
    ///
    /// 為什麼：adaptive routing 需 per-venue 健康度（rejection rate / latency / ws conn）
    /// 以判斷是否切換 fallback / throttle；Sprint 6+ IMPL 期與 `bybit_private_ws_status_writer`
    /// + per-venue rejection telemetry 接線。
    fn venue_health(&self, _venue: Venue) -> VenueHealth {
        unimplemented!(
            "M12 OrderRouter::venue_health — Sprint 6+ IMPL pending；\
             見 ADR-0039 §Decision 1 method 2"
        )
    }

    /// Method 3 — 跨 venue 淨倉位查詢。
    ///
    /// 為什麼：Y2 Binance trading enable 後（per ADR-0033 §Decision 2）跨 venue netting
    /// 與 portfolio exposure 計算需此入口；Y1 Bybit-only 即 single-venue position。
    fn cross_venue_position(&self, _asset_class: AssetClass) -> NetPosition {
        unimplemented!(
            "M12 OrderRouter::cross_venue_position — Y2 IMPL per ADR-0033 §Decision 2；\
             Y1 stub 返回 single-venue；見 ADR-0039 §Decision 1 method 3"
        )
    }

    /// Method 4 — 滑點預測。
    ///
    /// 為什麼：adaptive routing PostOnly vs taker 抉擇需預期 slippage cost；
    /// 對齊 ADR-0029 L2 snapshot fidelity；Sprint 6+ IMPL 期 L2 depth-based 模型 + per-venue
    /// calibration 接線。
    fn forecast_slippage(
        &self,
        _order: &OrderRequest,
        _market_snapshot: &MarketSnapshot,
    ) -> SlippageEstimate {
        unimplemented!(
            "M12 OrderRouter::forecast_slippage — Sprint 6+ IMPL pending；\
             對齊 ADR-0029 L2 snapshot fidelity；見 ADR-0039 §Decision 1 method 4"
        )
    }

    /// Method 5 — Reverse-snipe defense。
    ///
    /// 為什麼：市場連環爆倉 / 資金費反向 / 異常 wick 等事件下需 defensive routing
    /// （per ADR-0039 §Decision 4 PostOnly default + threshold-based taker switch）；
    /// Sprint 6+ IMPL 期 signal confidence + market direction confirmed threshold 接線。
    fn reverse_snipe(&self, _market_event: &MarketEvent) -> Option<DefensiveAction> {
        unimplemented!(
            "M12 OrderRouter::reverse_snipe — Sprint 6+ IMPL pending；\
             per ADR-0039 §Decision 4 PostOnly default + threshold-based taker switch；\
             見 ADR-0039 §Decision 1 method 5"
        )
    }

    /// Method 6 — Rebate eligibility 持續監控（30d rolling maker fill rate）。
    ///
    /// 為什麼：Bybit ToS rebate tier 評估走 rolling 30d maker fill rate；
    /// 若無持續監控 → rebate tier 跌出不自知 → silent cost edge degradation
    /// （per ADR-0039 §Context BB 5.21 audit push back）。
    /// Sprint 6+ IMPL 期 V094 `fills_close_maker_audit` 既有 column 採樣 + tier 計算 +
    /// in-memory ring buffer + EOD snapshot（per V115 Part 2 schema）。
    fn maker_fill_rate_30d(&self, _symbol: &str) -> MakerFillRateStats {
        unimplemented!(
            "M12 OrderRouter::maker_fill_rate_30d — Sprint 6+ IMPL pending；\
             scaffold MakerFillRateStats data carrier reserved per §1；\
             見 ADR-0039 §Decision 1 method 6 (NEW per BB 5.21 audit push back)"
        )
    }
}

// ============================================================================
// §3 UnimplementedOrderRouter — Sprint 1A-δ default marker impl
// ============================================================================

/// 純 marker 預設實作 — 建構合法，呼叫任一 method 全 panic 但 `route_order` 對 Binance
/// venue 走 Y3+ defer early return。
///
/// 為什麼：caller 建構 `Box<dyn OrderRouter>` 需可實例化的 default 型別；Sprint 6+ IMPL
/// 前任何 runtime 試圖建構並呼叫 method 均應 fail-loud（per PA spec §2.2 + ADR-0039
/// §Decision 1 fail-loud 紀律）；唯一例外是 `route_order` 對 BinancePerp / BinanceOption
/// 走 `Err(RoutingError::VenueDeferred)` early return，避免 Y3+ defer 路徑也 panic
/// （該路徑為治理硬編碼，不是「未實作」而是「明確拒絕」，per PA spec §6.1.5 E2 review focus #2）。
#[derive(Debug, Clone, Default)]
pub struct UnimplementedOrderRouter;

impl OrderRouter for UnimplementedOrderRouter {
    /// Override default `route_order` 以加裝 BinancePerp / BinanceOption 的 Y3+ defer
    /// hardcode early return；其他 venue 仍走 trait default panic（fail-loud）。
    ///
    /// 紀律：此 match 路徑為 5-gate inheritance 紅線，不可走 config-driven 開關；
    /// Sprint 6+ IMPL 期改寫此 method body 時必保留此 guard rails（per PA spec §6.1.5
    /// E2 review focus #2）。
    fn route_order(
        &self,
        order_request: &OrderRequest,
    ) -> Result<RoutingDecision, RoutingError> {
        match order_request.venue {
            // Y3+ trade defer per ADR-0033 §Decision 2 + ADR-0040 §Decision 1。
            // Y1 Binance market-data only；trade route 等 Y3+ 6-criteria evaluation pass。
            Venue::BinancePerp | Venue::BinanceOption => {
                Err(RoutingError::VenueDeferred("Y3+ per ADR-0033"))
            }
            // 其他 venue（BybitPerp / BybitSpot / BybitOption）走 trait default panic，
            // 對齊 Sprint 1A-δ scope = interface stub only，Sprint 6+ IMPL 期 Bybit-only
            // adaptive routing 邏輯接線。
            _ => unimplemented!(
                "M12 OrderRouter::route_order — Sprint 6+ Bybit-only IMPL pending；\
                 Sprint 1A-δ 階段僅接口預留 + Binance Y3+ defer hardcode；\
                 見 ADR-0039 §Decision 1 method 1 + §Decision 6 IMPL phase + PA spec §4.7"
            ),
        }
    }

    // 其他 5 method 沿用 trait default body（unimplemented!()）— 任一呼叫均 fail-loud。
}
