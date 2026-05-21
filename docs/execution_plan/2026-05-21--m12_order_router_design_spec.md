---
spec: M12 OrderRouter — Trait Interface Design (Sprint 1A-δ partial spec; 6 method per ADR-0039)
date: 2026-05-21
author: PA (interface stub design per v5.8 §2 M12 + ADR-0039；草稿 v0 5-method 修訂為 6-method authoritative 對齊 ADR-0039 §Decision 1)
phase: Sprint 1A-δ deliverable — DESIGN initial / IMPL phased Sprint 6+
status: SPEC-PARTIAL-V0（trait 6 method interface signature + maker_fill_rate_30d metric scaffold lock；IMPL `unimplemented!()` stub Sprint 1A-δ；adaptive logic Sprint 6+ per ADR-0039 §Decision 6）
parent specs:
  - srv/docs/adr/0039-m12-order-router-trait-and-maker-fill-rate-metric.md
  - srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md §2 M12
  - srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md (V### range + Guard 範式 reference)
related ADRs:
  - ADR-0001 (Rust 為唯一交易權威 — OrderRouter Rust hot path actor)
  - ADR-0029 (market.public_trades + L2 snapshot — maker_fill_rate calculation 數據源)
  - ADR-0033 (ADR-0006 amendment — Binance Y2 trading defer；本 spec cross_venue_position Y2 對齊)
  - ADR-0034 (Decision Lease LAL — 越 bounds 走 LAL 3 protected)
  - ADR-0030 (Copy Trading evidence-gated — 平台內 Copy Trading 不影響本 spec routing)
related V###:
  - V094 (fills_close_maker_audit — maker_fill 計算上游 column 範式)
  - V107 (M11 replay_divergence_log — 與 V115 dedup 範式)
  - V115 (M12 adaptive routing audit schema — 本 spec reference)
scope:
  - Trait interface signature 5 method（含 maker_fill_rate_30d）
  - Default panic IMPL Sprint 1A-δ（do not panic in production；only stub）
  - V115 schema reference outline（full DDL 在 V115 placeholder spec）
  - Sprint 6+ IMPL phase split + cross-module integration placeholder
out-of-scope:
  - 完整 trait method body IMPL（Sprint 6+）
  - V115 full DDL（V115 placeholder spec 單獨 land；本 spec 只 reference）
  - Reverse-snipe defense 完整邏輯（ADR-0039 Decision 4；Sprint 6 IMPL）
  - Slicing IMPL TWAP / iceberg（Sprint 7-8）
  - Cross-venue routing（Y2 conditional per ADR-0033）
---

# M12 OrderRouter Trait Interface Design Spec（Sprint 1A-δ partial；6 method per ADR-0039）

## §1 Context

### 1.1 起源

v5.8 §2 M12 列「Adaptive Order Routing」module，spec engineering scope：

```
Sprint 1A-δ: OrderRouter trait interface + ADR-0039 (interface stub only) (20-30 hr)
Sprint 6: Maker-vs-taker adaptive logic IMPL (Bybit only) (80-120 hr)
Sprint 7-8: Slicing IMPL (TWAP / iceberg) (60-100 hr)
Y2: Cross-venue routing (when Binance trading enabled per ADR-0006 amendment) (100-160 hr)
```

ADR-0039（Proposed-pending-commit）已 land：
- 6 method trait signature（v5.8 initial 5 + NEW `maker_fill_rate_30d` per BB 5.21 audit push back）
- `maker_fill_rate_30d` metric definition + Rebate tier 對照表（T1 ≥ 80% / T2 ≥ 70% / Default ≥ 50%）
- V115 三表 audit schema 候選（pending CR-14 finalize）
- 5 Open Question + Sign-off chain

operator dispatch Sprint 1A-δ deliverable：interface stub level design spec（350-500 行）+ V115 frontmatter placeholder（50-100 行）。

### 1.2 為什麼 Sprint 1A-δ 落地 DESIGN（IMPL 延後）

per ADR-0039 §Context「為什麼 Sprint 1A-δ DESIGN initial / IMPL delayed」：

1. **DESIGN cost 20-30 hr 相對 IMPL cost 240-380 hr（Y1-Y2）** — early DESIGN lock interface 避免後續 IMPL drift
2. **maker rebate eligibility 監控不可等到 Sprint 6 IMPL** — Sprint 1A-δ trait stub 中 `maker_fill_rate_30d` interface 可先接 V094 既有 per-strategy data 作 degraded 計算入口
3. **與 ADR-0029 trade tape land 同步**（per ADR-0029 §OQ-4 Phase 1b calibration timing）
4. **避免 V### Guard B 範式違反**（per ADR-0011 V-migration PG dry-run mandatory）— 後續 add trait method = signature 變更 = 違反「interface 一旦 lock 不變」原則

### 1.3 與 v5.8 既有 module 的依賴

| 依賴 | 關係 |
|---|---|
| M1 Decision Lease LAL | OrderRouter 在 lease 通過後執行 routing；越 bounds 升 LAL 2 audit |
| M3 HEALTH_WARN | maker_fill_rate tier 跌出 emit M3 alert（per CR-7 dedup contract M3 = single health authority）|
| M9 A/B Test Framework | A/B test variant routing 通過本 trait `route` method 分流（IMPL Sprint 6+）|
| M11 Replay Engine | Replay 時 routing decision 從 V115 audit log 回放比對（per V107 / V115 dedup OQ-4）|

### 1.4 本 spec 範圍邊界

- ✅ 5 method trait signature lock + 1 helper struct definition（`RoutingDecision` / `RoutingContext` / `Fill` / `M12Error` / `RoutingMetricsSummary`）
- ✅ `maker_fill_rate_30d` metric definition reference（per ADR-0039 §Decision 2）
- ✅ Default panic IMPL pattern（Sprint 1A-δ stub level；Sprint 6 IMPL 階段 override）
- ✅ V115 schema reference outline（指向 V115 placeholder spec）
- ✅ Cross-module integration placeholder（M1 / M3 / M9 / M11）
- ✅ Acceptance criteria 5-7 條
- ✅ IMPL phase split（Sprint 6 read-only / Y2 Q1 Advisory / Y2 Q2+ auto-gate）
- ✅ Cross-V### dependency placeholder + Open Q ≥ 3
- ❌ Trait method body IMPL（Sprint 6+）
- ❌ V115 full DDL（V115 placeholder spec）
- ❌ Reverse-snipe 完整邏輯（Sprint 6）
- ❌ Slicing IMPL（Sprint 7-8）
- ❌ Cross-venue routing 完整 IMPL（Y2）

---

## §2 OrderRouter Trait — 6 Method（Sprint 1A-δ；對齊 ADR-0039 §Decision 1）

> **草稿修訂 note (PA 2026-05-21 review)**：本 spec 早期草稿（v0）trait surface 為 5 method（route / record_fill / maker_fill_rate_30d / adaptive_routing_enabled / routing_metrics）。
> 但 **ADR-0039 §Decision 1 表格列 6 method**（route_order / venue_health / cross_venue_position / forecast_slippage / reverse_snipe / maker_fill_rate_30d），是 v5.8 §2 M12 spec line 425-458 原 5 method + BB 5.21 audit push back 增加的 maker_fill_rate_30d = 5+1 = 6。
> PA dispatch packet 行 164 同樣描述「5 method slots default panic + maker_fill_rate_30d metric」即 5+1=6 對齊。
> **本 §2 對齊 ADR-0039 6 method authoritative signature**；草稿 v0 的 `record_fill` / `adaptive_routing_enabled` / `routing_metrics` 變更為 OrderRouter 周邊 helper trait（候選）或留 Sprint 6+ IMPL phase 期決定（per §8 OQ-6）。
> ADR-0039 是 trait surface 權威來源；本 spec land 後 ADR-0039 不需 amendment。

### 2.1 Trait signature lock（per ADR-0039 §Decision 1 全表）

```rust
// File location candidate: rust/openclaw_engine/src/order_router.rs
// Module: openclaw_engine::order_router::OrderRouter
// per ADR-0001 Rust 為唯一交易權威；OrderRouter 是 hot path actor

/// M12 Adaptive Order Routing trait — 6 method per ADR-0039 §Decision 1
///
/// Sprint 1A-δ scope: trait interface + default body panic stub only（per §2.2）
/// Sprint 6+ scope: Bybit-only adaptive logic IMPL（per ADR-0039 §Decision 6 IMPL phase）
/// Y2 scope: cross-venue routing IMPL（per ADR-0033 Binance Y2 enable）
pub trait OrderRouter: Send + Sync {
    /// Method 1 — 主路由決策入口
    /// 返回 venue + order_type + slicing + time-in-force routing decision
    ///
    /// Sprint 1A-δ: `unimplemented!("M12 OrderRouter::route_order Sprint 6+ IMPL pending — Sprint 1A-δ interface stub only per ADR-0039 §Decision 1 + §Decision 6")`
    /// Sprint 6: maker-vs-taker adaptive logic IMPL（Bybit only；per ADR-0039 §Decision 4 reverse-snipe defense）
    /// 必含 §4.6 D1a + §4.7 Y2 guard rails hardcode 拒絕路徑
    fn route_order(&self, order_request: OrderRequest) -> Result<RoutingDecision, RoutingError>;

    /// Method 2 — venue 健康度
    /// 返回 rejection rate / latency p99 / ws connectivity
    ///
    /// Sprint 1A-δ: `unimplemented!("M12 OrderRouter::venue_health Sprint 6+ IMPL pending")`
    /// Sprint 6: per-venue 健康度 calculation + caching
    fn venue_health(&self, venue: VenueId) -> VenueHealth;

    /// Method 3 — 跨 venue 淨倉位
    /// Y1 Bybit only → 單 venue position；Y2 Binance trading enable 後生效（per ADR-0033 Decision 2）
    ///
    /// Sprint 1A-δ: `unimplemented!("M12 OrderRouter::cross_venue_position Y2 IMPL per ADR-0033")`
    /// Y2: Binance trading enable 後對齊 ADR-0033 Decision 2 timeline
    fn cross_venue_position(&self, asset: Asset) -> NetPosition;

    /// Method 4 — 滑點預測
    /// 對齊 ADR-0029 L2 snapshot fidelity
    ///
    /// Sprint 1A-δ: `unimplemented!("M12 OrderRouter::forecast_slippage Sprint 6+ IMPL pending")`
    /// Sprint 6: L2 order book depth-based slippage 預測 + per-venue calibration
    fn forecast_slippage(&self, order: &Order, market_snapshot: &MarketSnapshot) -> SlippageEstimate;

    /// Method 5 — Reverse-snipe defense
    /// per Q3 market-driven trigger insight；預設 PostOnly maker（per ADR-0039 §Decision 4）
    ///
    /// Sprint 1A-δ: `unimplemented!("M12 OrderRouter::reverse_snipe Sprint 6+ IMPL pending per ADR-0039 §Decision 4")`
    /// Sprint 6: signal confidence + market direction confirmed threshold → 切換 PostOnly → taker
    fn reverse_snipe(&self, market_event: MarketEvent) -> Option<DefensiveAction>;

    /// Method 6 (NEW per BB 5.21 audit push back) — Rebate eligibility 持續監控
    /// per ADR-0039 §Decision 1 method 6 + §Decision 2 計算規範
    /// per Bybit ToS 4-tier rebate eligibility（T1 ≥ 80% / T2 ≥ 70% / Default ≥ 50%）
    ///
    /// Sprint 1A-δ: `unimplemented!("M12 OrderRouter::maker_fill_rate_30d Sprint 6+ IMPL pending — scaffold struct + enum reserved per §3")`
    /// Sprint 6: V094 fills_close_maker_audit 30d 採樣 + tier 計算 + in-memory ring buffer + EOD snapshot（per V115 Part 2 schema）
    fn maker_fill_rate_30d(&self, venue: VenueId, asset_class: AssetClass) -> MakerFillRateStats;
}
```

### 2.1.1 Trait surface lock 紀律

ADR-0039 §Decision 1 表格列 6 method 為 authoritative signature。本 spec 在 §2.1 完整對齊 6 method 名稱 + 參數類型 + 返回類型。**Sprint 1A-δ E1 IMPL 必對齊此 signature，不可改名 / 增減 method**。

method name / param / return 變更 = 違反 ADR-0011 V-migration interface lock 範式 = 觸發 ADR-0039 amendment（需 PA + PM sign-off）。

### 2.2 Default panic IMPL pattern（Sprint 1A-δ stub）

per §二 16 根原則 #6 失敗默認收縮 + #8 交易可解釋 + memory `feedback_no_dead_params`，default body 用 `unimplemented!()` panic 而非 noop / fake-success：
- noop default → Sprint 6+ IMPL 前 caller 誤以為 routing 成功 → silent miss-route
- fake-success default → 違反根原則 #6 + #8
- `unimplemented!()` panic at runtime → caller 在 dev / test 階段必發現未 IMPL；對齊 Rust idiom

```rust
/// Sprint 1A-δ scope：interface stub only；production 永不接線此 struct
/// 任何 production caller 觸發 panic = bug，必須 follow-up 改接 BybitOrderRouter（Sprint 6+ IMPL）
pub struct UnimplementedOrderRouter;

impl OrderRouter for UnimplementedOrderRouter {
    fn route_order(&self, order_request: OrderRequest) -> Result<RoutingDecision, RoutingError> {
        // §4.6 D1a + §4.7 Y2 guard rails 必含 hardcode（Sprint 1A-δ E1 IMPL 必補；不可省）
        match order_request.venue {
            VenueId::Dex | VenueId::Hyperliquid => {
                return Err(RoutingError::VenueNotApproved(
                    "DEX/Hyperliquid not approved per D1a + ADR-0040".to_string()
                ));
            }
            VenueId::BinancePerp | VenueId::BinanceSpot => {
                // Y1 Binance market-data only per ADR-0033 Decision 2；trade route Y3+
                return Err(RoutingError::VenueDeferred("Y3+ per ADR-0033".to_string()));
            }
            _ => {}
        }
        unimplemented!(
            "M12 OrderRouter::route_order — Sprint 6+ adaptive logic IMPL pending；\
             Sprint 1A-δ scope = guard rails + interface stub only；\
             per ADR-0039 §Decision 1 method 1 + §Decision 6 IMPL phase"
        )
    }

    fn venue_health(&self, _venue: VenueId) -> VenueHealth {
        unimplemented!(
            "M12 OrderRouter::venue_health — Sprint 6+ IMPL pending；\
             per ADR-0039 §Decision 1 method 2"
        )
    }

    fn cross_venue_position(&self, _asset: Asset) -> NetPosition {
        unimplemented!(
            "M12 OrderRouter::cross_venue_position — Y2 IMPL pending per ADR-0033 Binance Y2 enable；\
             Y1 stub return single-venue position；\
             per ADR-0039 §Decision 1 method 3"
        )
    }

    fn forecast_slippage(&self, _order: &Order, _market_snapshot: &MarketSnapshot) -> SlippageEstimate {
        unimplemented!(
            "M12 OrderRouter::forecast_slippage — Sprint 6+ IMPL pending；\
             對齊 ADR-0029 L2 snapshot fidelity；\
             per ADR-0039 §Decision 1 method 4"
        )
    }

    fn reverse_snipe(&self, _market_event: MarketEvent) -> Option<DefensiveAction> {
        unimplemented!(
            "M12 OrderRouter::reverse_snipe — Sprint 6+ IMPL pending；\
             per ADR-0039 §Decision 4 PostOnly default + threshold-based taker switch；\
             per ADR-0039 §Decision 1 method 5"
        )
    }

    fn maker_fill_rate_30d(&self, _venue: VenueId, _asset_class: AssetClass) -> MakerFillRateStats {
        unimplemented!(
            "M12 OrderRouter::maker_fill_rate_30d — Sprint 6+ IMPL pending；\
             scaffold struct + enum reserved per §3；\
             per ADR-0039 §Decision 1 method 6 (NEW per BB 5.21 audit push back)"
        )
    }
}
```

**注意**：`unimplemented!()` 只用於 Sprint 1A-δ stub；任何 production 接線 `UnimplementedOrderRouter` 觸發 = bug。生產碼 default fallback 應走 `LegacyDirectOrderRouter`（v5.7 既有不走 M12 trait 的 direct PostOnly 邏輯）或 `BybitOrderRouter`（Sprint 6+ IMPL）。本 spec 不設計 fallback；Sprint 6 IMPL 階段定（per §8 OQ-2）。

### 2.3 Helper struct / enum candidate signature（per ADR-0039 §Decision 1 對齊）

```rust
/// per ADR-0040 sibling Sprint 1A-δ M13 spec land；本 spec 引用
pub enum VenueId {
    BybitPerp,
    BybitSpot,
    BybitOption,
    BinancePerp,    // Y1 market-data only per ADR-0033；Y3+ trade enable
    BinanceSpot,    // 同上
    Dex,            // §4.6 hardcode 拒絕路徑（D1a + ADR-0040）
    Hyperliquid,    // 同上
}

pub enum AssetClass { Perp, Spot, Option, Earn, Structured }

pub struct OrderRequest {
    pub venue: VenueId,
    pub asset: Asset,
    pub side: OrderSide,
    pub qty: f64,
    pub price: Option<f64>,                // None = Market；Some = Limit/PostOnly
    pub time_in_force: TimeInForce,
    pub notional_usdt: f64,                // per §5 bounds check
    pub strategy: String,
    pub urgency: UrgencyLevel,             // Low / Medium / High (per signal confidence)
    pub market_snapshot: MarketSnapshot,   // per ADR-0029 L2 / trade tape source
    pub engine_mode: EngineMode,           // per ADR-0005 paper / demo / live_demo / live
    /* IMPL 階段定 */
}

pub enum UrgencyLevel { Low, Medium, High }

pub struct RoutingDecision {
    pub venue: VenueId,
    pub order_type: OrderType,             // PostOnlyLimit / Limit / Market / etc.
    pub slicing: SlicingPlan,              // SingleShot / TWAP { slices, interval } / Iceberg { display_qty }
    pub time_in_force: TimeInForce,
    pub route_reason: RouteReason,         // 'default_postonly' / 'reverse_snipe_confirmed' / 'rebate_protection' etc.
    pub decision_id: String,               // UUID per route_order() call；V115 PK
}

pub enum RouteReason {
    DefaultPostOnly,
    ReverseSnipeConfirmed,
    UrgencyTaker,
    RebateProtection,
    OperatorOverride,
    /* Sprint 6+ extension */
}

pub struct VenueHealth {
    pub venue: VenueId,
    pub rejection_rate_24h: f64,
    pub latency_p99_ms: f64,
    pub ws_connectivity_ok: bool,
    /* IMPL 階段定 */
}

pub struct NetPosition {
    pub asset: Asset,
    pub net_qty: f64,
    pub by_venue: HashMap<VenueId, f64>,   // Y2 Binance enable 後 cross-venue 顯現
    /* IMPL 階段定 */
}

pub struct SlippageEstimate {
    pub estimated_bps: f64,
    pub confidence: f64,                   // 0.0..1.0 model confidence
    /* IMPL 階段定 */
}

pub struct DefensiveAction {
    pub trigger_reason: String,
    pub recommended_action: DefensiveActionType,
    /* IMPL 階段定 */
}

pub enum DefensiveActionType {
    SwitchToTaker,
    CancelOrder,
    Throttle,
}

pub enum RoutingError {
    /// §4.6 D1a 拒絕路徑（DEX / Hyperliquid not approved per ADR-0040）
    VenueNotApproved(String),
    /// §4.7 Y2 trade defer（Binance market-data only per ADR-0033 Decision 2）
    VenueDeferred(String),
    /// §5.4 bounds 越界（require operator confirm + LAL Tier 3）
    BoundsExceeded {
        requested: f64,
        cap: f64,
        required_lal_tier: LalTier,
    },
    VenueUnreachable,
    InsufficientData,
    InvalidContext,
    /* Sprint 6+ extension */
}

/// per ADR-0034 LAL Tier reference
pub enum LalTier {
    Tier0,    // 自動
    Tier1,    // reparam
    Tier2,    // reweight
    Tier3,    // protected（routing bounds 越界走此 tier per §5.2）
    Tier4,    // budget
}

/// MakerFillRateStats struct — per §3.2 詳論
/// 此處列 summary；完整定義在 §3
pub struct MakerFillRateStats {
    pub venue: VenueId,
    pub asset_class: AssetClass,
    pub window_start_ts: DateTime<Utc>,
    pub window_end_ts: DateTime<Utc>,
    pub maker_fill_notional_usdt: f64,
    pub total_fill_notional_usdt: f64,
    pub maker_fill_ratio: f64,             // NaN for cold start <7d
    pub current_tier: RebateTier,
    pub days_in_current_tier: u32,
}
```

**注意**：上述 struct / enum 為 ADR-0039 §Decision 1 對齊的 candidate signature；Sprint 6 IMPL 階段可微調 field name / variant；trait method signature（§2.1）lock 不變。

### 2.4 草稿 v0 的 record_fill / adaptive_routing_enabled / routing_metrics — 移到 OrderRouter 周邊 helper trait（候選）

PA 草稿 v0 列的 3 個 method 不在 ADR-0039 §Decision 1 表內，理由：

| 草稿 v0 method | 為什麼不在 OrderRouter trait | Sprint 1A-δ 安置 |
|---|---|---|
| `record_fill(order_id, fill)` | Fill ingest 是 `execution_listener.rs` 既有職責；OrderRouter 不直接寫 fills 表；違反根原則 #1 單一寫入口 | 透過 `MakerFillRateCounter::on_fill_observed(fill_event)`（per §3.4 scaffold）；execution_listener.rs Sprint 6+ wire-up |
| `adaptive_routing_enabled(symbol) -> bool` | 不是獨立 method，而是 `route_order()` 內部 IMPL detail（Sprint 6+ adaptive logic 是否在 bounds 內走 PostOnly default vs adaptive） | 變為 Sprint 6+ IMPL phase 內部 helper；不暴露於 trait |
| `routing_metrics() -> RoutingMetricsSummary` | 對應 GUI dashboard / governance audit；可放 OrderRouter 周邊獨立 trait `RoutingMetricsProvider`（Sprint 6+ IMPL） | Sprint 6+ wire-up `RoutingMetricsProvider` 周邊 trait；本 spec OQ-6 列出 |

**結論**：本 §2 trait surface 對齊 ADR-0039 6 method 為 authoritative signature；草稿 v0 3 method 移為周邊 helper（per §8 OQ-6 + ADR-0039 §Decision 6 Sprint 6+ IMPL phase）。

---

## §3 maker_fill_rate_30d Metric Definition（per ADR-0039）

### 3.1 計算規範速查（reference ADR-0039 §Decision 2）

per ADR-0039 §Decision 1 method 6：`maker_fill_rate_30d(venue: VenueId, asset_class: AssetClass) -> MakerFillRateStats`。

| 元素 | 設計 | 理由 |
|---|---|---|
| 窗口 | Rolling 30d | per Bybit rebate tier evaluation period |
| 維度 | per-venue × per-asset-class（trait method signature 對齊 ADR-0039 §Decision 1） | trait 入口為 venue × asset_class；per-symbol view 走應用層 aggregate（per OQ-5）|
| 分子 | maker fill notional USDT (30d sum) | per V094 既有 `close_maker_attempt = TRUE AND close_maker_fallback_reason IN ('maker_filled', NULL)` 條件 |
| 分母 | total fill notional USDT (30d sum) | per fills table 30d window 全 fill |
| 更新頻率 | 每 fill 觸發增量更新 + 每日 EOD snapshot | per V115 Part 2 schema |
| Cold start (< 7d) | 返回 `MakerFillRateStats { maker_fill_ratio: f64::NAN, current_tier: RebateTier::Unknown, ... }` + warn flag | 30d 窗口未滿；ADR-0039 §Decision 2 cold start fallback |
| Cold start (7d-30d) | 返回計算值；`current_tier: RebateTier::Provisional` | per ADR-0039 §Decision 2 |
| ≥ 30d | full tier classification（T1 / T2 / Default / BelowDefault） | per ADR-0039 §Decision 2 |

### 3.2 MakerFillRateStats struct（per ADR-0039 §Decision 1）

完整 struct definition + RebateTier ENUM + 採樣 source 預留指向見 §2.3（candidate signature 已 land）+ ADR-0039 §Decision 2 計算規範。

**Sprint 1A-δ E1 IMPL scope**：struct + enum reserve only；採樣 SQL（V094 query）禁實作（per §1.4 scope 排除）。

### 3.3 採樣源預留指向（V094 既有 column 範式）

per ADR-0039 §Context.v5.7 既有半成品：

- V094 `fills_close_maker_audit` schema 提供 `close_maker_attempt boolean NOT NULL` + `close_maker_fallback_reason text` enum 10 值
- 分子計算邏輯（**Sprint 6+ IMPL phase**；本 spec **禁實作真實 SQL**）：
  ```sql
  -- 概念性 query；Sprint 6+ 才寫真實 SQL
  SELECT SUM(notional_usdt) FROM fills
  WHERE close_maker_attempt = TRUE
    AND close_maker_fallback_reason IN ('maker_filled', NULL)
    AND fill_ts >= now() - INTERVAL '30 days'
    AND venue = $1 AND asset_class = $2;
  ```
- 分母計算邏輯：
  ```sql
  -- 概念性 query；Sprint 6+ 才寫真實 SQL
  SELECT SUM(notional_usdt) FROM fills
  WHERE fill_ts >= now() - INTERVAL '30 days'
    AND venue = $1 AND asset_class = $2;
  ```

### 3.4 In-memory ring buffer scaffold（Sprint 1A-δ stub only）

per ADR-0039 §Decision 2 持久層：

```rust
/// In-memory 30d maker fill rate counter scaffold（Sprint 1A-δ stub only）
/// Sprint 6+ 才 IMPL 真實 ring buffer + V094 SQL 採樣 + EOD snapshot persist 到 V115 Part 2
pub struct MakerFillRateCounter {
    /// per venue × asset_class 維度持有獨立 counter
    /// 真實 IMPL Sprint 6+：HashMap<(VenueId, AssetClass), RingBuffer<FillRecord>>
    _venue_asset_counters_placeholder: (),
}

impl MakerFillRateCounter {
    /// Sprint 1A-δ stub：未 IMPL
    /// Sprint 6+ IMPL：每 fill 觸發 push +1 row 到 ring buffer；evict expired rows
    /// 由 execution_listener.rs Sprint 6+ wire-up（草稿 v0 record_fill 改入此 helper）
    pub fn on_fill_observed(&mut self, _fill_event: &FillEvent) {
        unimplemented!("M12 MakerFillRateCounter::on_fill_observed Sprint 6+ IMPL")
    }

    /// Sprint 1A-δ stub：未 IMPL
    /// Sprint 6+ IMPL：query ring buffer aggregate → MakerFillRateStats（含 tier 計算）
    pub fn snapshot_for_venue(&self, _venue: VenueId, _asset_class: AssetClass) -> MakerFillRateStats {
        unimplemented!("M12 MakerFillRateCounter::snapshot_for_venue Sprint 6+ IMPL")
    }

    /// Sprint 1A-δ stub：未 IMPL
    /// Sprint 6+ IMPL：每日 EOD trigger → write 1 row 到 V115 Part 2 maker_fill_rate_30d_snapshots
    pub fn persist_eod_snapshot(&self) -> Result<(), PersistError> {
        unimplemented!("M12 MakerFillRateCounter::persist_eod_snapshot Sprint 6+ IMPL")
    }
}
```

### 3.5 Cold start window enum（per ADR-0039 §Decision 2）

```rust
/// Cold start window classification（Sprint 1A-δ scope = enum reserve only）
pub enum ColdStartWindow {
    InsufficientData,    // < 7d data：返回 NaN + Unknown tier + warn flag
    Provisional,         // 7d-30d data：計算 ratio 但 tier 標記 Provisional
    FullWindow,          // ≥ 30d data：full tier classification
}
```

具體 behavior 待 Sprint 6+ IMPL 期 stub 設計確認；本 spec 不 commit 細節（per ADR-0039 OQ-3）。

### 3.6 Alert 觸發 + Tier transition log（per ADR-0039 §Decision 2）

per ADR-0039 §Decision 2 末段：

- `maker_fill_ratio < 0.60` sustained 3d → M3 HEALTH_WARN（per CR-7 dedup contract M3 為 single health authority）
- 任何 `current_tier` 變化 → emit 1 row 到 V115 Part 3 `routing.routing_tier_transitions`

Sprint 1A-δ scope = trait method `maker_fill_rate_30d` 簽名 + enum；alert dispatch wiring 是 Sprint 6+ IMPL 期 land（per §1.4 scope 排除）。

### 3.7 Y2 Threshold > 70% → Adaptive Routing 觸發鏈

per ADR-0039 §Decision 2 + §Decision 5（LAL 3 protection）：

```
maker_fill_rate_30d(venue, asset_class) ≥ 0.70 (持續 7d)
    ↓
(Sprint 6+ IMPL phase；本 Sprint 1A-δ scope = trait signature reserve only)
adaptive routing decision toggle inside route_order() — Sprint 6+ IMPL detail
    ↓
LAL Tier 2 audit triggered（cross-strategy routing 變更 governance approval）
    ↓
record adaptive routing flip event 到 V115 Part 3 routing_tier_transitions
    ↓
emit M3 HEALTH_INFO（非 WARN；adaptive enable 是 positive event）
```

**Alert 觸發（負向）**：

```
maker_fill_rate_30d < 0.60 sustained 3d
    ↓
emit M3 HEALTH_WARN（per CR-7 dedup contract M3 為 single health authority）
    ↓
emit Slack alert + record V115 Part 3 routing_tier_transitions row
    ↓
若 sustained 7d 跌出 Tier 2 → days_in_current_tier reset；cooldown 期限制 reverse_snipe 過頻
```

### 3.8 Rebate tier 對照表（per ADR-0039 + crypto-microstructure-knowledge skill）

| Tier | Threshold | rebate behavior | Sprint 1A-δ stub return |
|---|---|---|---|
| Tier 1 | ≥ 80% | Tier 1 rebate（per Bybit ToS）| `RebateTier::Tier1` |
| Tier 2 | ≥ 70% | Tier 2 rebate（adaptive routing eligible Y2）| `RebateTier::Tier2` |
| Default | ≥ 50% | Default fee schedule | `RebateTier::Default` |
| BelowDefault | < 50% | Full taker rate（Alert）| `RebateTier::BelowDefault` |
| Provisional | 7d ≤ data < 30d | Cold start 期；不分類 | `RebateTier::Provisional` |
| Unknown | data < 7d | 數據不足；返回 NaN | `RebateTier::Unknown` |

**注意**：精確 threshold（80% / 70% / 50%）待 BB Sprint 6 IMPL 期 confirm（per ADR-0039 OQ-1）；本 spec 採 skill 表作 Sprint 1A-δ 默認。

> **草稿 v0 對齊 note**：本 spec 早期草稿 trait `RebateTier` enum 在 §2.3 已 land 4-tier；§3.5 ColdStartWindow 列額外 3-variant；§3.8 表合併列 6 row。Sprint 1A-δ E1 IMPL 期 OQ-3 review 是否 fold ColdStartWindow 進 RebateTier enum（per ADR-0039 OQ-3 + §8 OQ-3）。

---

## §4 Adaptive Routing Audit Schema → V115 Reference

### 4.1 V115 三表結構（per ADR-0039 §Decision 3；完整 DDL 在 V115 placeholder spec）

| Table | 用途 | 量級估算 | PK |
|---|---|---|---|
| `routing.adaptive_routing_audit`（V115 Part 1）| per-decision audit log；每次 `route()` call emit 1 row | ~1000-10000 row/day（per-strategy × per-symbol routing decision frequency）| `decision_id` UUID |
| `routing.maker_fill_rate_30d_snapshots`（V115 Part 2）| 每日 EOD snapshot；venue × asset_class 維度 | ~3-5 row/day（per venue × asset_class combinations）| `(snapshot_date, venue, asset_class)` |
| `routing.routing_tier_transitions`（V115 Part 3）| tier transition event log | ~10-50 row/yr（rebate tier 不頻繁切換）| `transition_id` UUID |

### 4.2 V115 schema location 命名約定

per ADR-0039 §Decision 3 候選 schema 用 `learning.*`；本 spec 與 V115 placeholder spec **改用 `routing.*` schema**：

- `learning.*` 屬學習層（hypothesis registry / pre-registration / earn audit per V103）
- `routing.*` 是新 schema namespace（M12 audit log 是 routing decision 而非 learning data）
- 對齊 §二原則 7「學習 ≠ Live」+ DOC-08 §12 #2「Lease 必在執行前已 acquired」（routing audit 是 execution 層 audit）

**待 V115 placeholder spec 確認 schema 命名 + 與 ADR-0039 §Decision 3 reconcile（OQ-4 衍生）**。

### 4.3 與 V107（M11 replay_divergence_log）dedup（per ADR-0039 OQ-4）

V107 是 M11 replay 結果比對 log；V115 是 M12 routing decision audit log：

- **兩表正交並存**；無 explicit FK
- Replay 階段透過 `asset + ts ± window` 做 fuzzy join；CR-14 review 後決定是否加 explicit cross-reference column
- V115 `decision_id` 在 M11 replay 時可作 join key（per `asset + ts` window 內 candidate decision lookup）

詳見 V115 placeholder spec §4。

---

## §5 Cross-Module Integration Placeholder

### 5.1 M1 LAL Tier 2 Audit 整合

per ADR-0034 + ADR-0039 §Decision 5：

| 場景 | LAL Tier | 路徑 |
|---|---|---|
| `route_order()` 在 bounds 內（cap + tolerance）| **無 lease 升級** | OrderRouter 自主決策；emit V115 Part 1 audit row |
| `route_order()` 越 single-order USD cap（initial $500）| **LAL 3 protected** | require operator confirm + emit `guardian_block_log` row with `block_reason='router_bounds_exceeded'`；fail-closed reject |
| `route_order()` 越 per-strategy slippage tolerance | **LAL 3 protected** | 同上 |
| adaptive routing toggle 內部觸發（Y2 Q2+ 70% threshold sustained 7d）| **LAL Tier 2** | cross-strategy routing 變更；emit governance approval audit；Sprint 6+ IMPL phase 期 land |
| `MakerFillRateCounter::on_fill_observed()` 引發 tier transition | **無 lease**（純 metric event）| emit V115 Part 3 row + 條件 emit M3 HEALTH_WARN；execution_listener.rs Sprint 6+ wire-up |

**IMPL phase split**（per §7）：Sprint 6 read-only logging；Y2 Q1 Advisory；Y2 Q2+ auto-gate。

### 5.2 M9 A/B Test Variant Routing

per v5.8 §2 M9 A/B Test Framework：

- M9 variant routing 通過 M12 trait `route_order()` method 分流（IMPL Sprint 6+）
- A/B variant 分配在 `OrderRequest` 添加 `variant_id` field（Sprint 6 IMPL 階段加；per OQ-4）
- M9 variant evaluation 引用 V115 Part 1 `route_reason` 過濾 variant-specific decisions

**Sprint 1A-δ 不 IMPL**；`OrderRequest` struct candidate 預留 extension slot。

### 5.3 M11 Replay Routing Decision Compare

per v5.8 §2 M11 + ADR-0038（M11 continuous counterfactual replay）：

- Replay 期間從 V115 Part 1 `routing.adaptive_routing_audit` 取 historical `decision_id + venue + order_type + route_reason`
- 比對 replay 重算 routing decision；divergence 記入 V107 `replay_divergence_log`
- 兩表 fuzzy join 透過 `asset + ts ± window`（per §4.3 OQ-4）

**Sprint 1A-δ 不 IMPL**；M11 replay 與 V115 audit 兩表結構獨立並存。

### 5.4 與 IntentProcessor / Guardian 的關係

per §二原則 1 + 4 + 9：

```
IntentProcessor.submit_intent(intent)
    ↓
Guardian.approve(intent) [risk envelope + bounds check]
    ↓
Decision Lease.acquire_lease()
    ↓
OrderRouter.route_order(order_request) [M12 — 本 spec；per ADR-0039 §Decision 1 method 1]
    ↓
Bybit API submit_order(routing_decision.venue, routing_decision.order_type, ...)
    ↓
fill 回報 → execution_listener.rs → MakerFillRateCounter.on_fill_observed(fill_event) [per §3.4 scaffold；Sprint 6+ wire-up；V115 Part 1 audit row INSERT]
```

OrderRouter 是 Guardian 通過後的 routing decision 層；**不繞 IntentProcessor 寫入口 + Guardian 風控**（符合§二原則 1 + 4）。

---

## §6 Acceptance Criteria（Sprint 1A-δ）

| # | Criterion | 驗證方法 |
|---|---|---|
| 1 | OrderRouter trait **6 method signature** land in Rust module `openclaw_engine::order_router::OrderRouter`（route_order / venue_health / cross_venue_position / forecast_slippage / reverse_snipe / maker_fill_rate_30d）對齊 ADR-0039 §Decision 1 全表 | `cargo build --release` PASS + `cargo doc` 6 method 可見；method name + param + return 100% 對齊 ADR-0039 |
| 2 | `UnimplementedOrderRouter` default impl **6 method** 全 `unimplemented!("M12 ... Sprint 6+ IMPL pending ...")` | `cargo test --release order_router::tests::unimplemented_panics`：每 method 觸發 panic 必含 "M12 OrderRouter" + "Sprint 6+ IMPL pending" + "per ADR-0039" substring |
| 3 | `maker_fill_rate_30d(venue: VenueId, asset_class: AssetClass) -> MakerFillRateStats` signature 對齊 ADR-0039 §Decision 1 method 6 + §Decision 2 MakerFillRateStats struct 含 8 field（venue / asset_class / window_start_ts / window_end_ts / maker_fill_notional_usdt / total_fill_notional_usdt / maker_fill_ratio / current_tier / days_in_current_tier） | 對照 ADR-0039 §Decision 1 + §Decision 2 |
| 4 | Helper struct + enum land（`OrderRequest` / `RoutingDecision` / `VenueHealth` / `NetPosition` / `SlippageEstimate` / `DefensiveAction` / `MakerFillRateStats` / `RebateTier` / `ColdStartWindow` / `RoutingError`）| `cargo build --release` PASS + struct field count match §2.3 + enum variant match |
| 5 | `RouteReason` enum 含 5 variant（DefaultPostOnly / ReverseSnipeConfirmed / UrgencyTaker / RebateProtection / OperatorOverride）+ `RebateTier` 含 4 variant（Tier1 / Tier2 / Default / BelowDefault）+ `ColdStartWindow` 獨立 3-variant per §3.5 | `cargo doc` enum variant 列表對齊 |
| 6 | **§4.6 D1a hardcode + §4.7 Y2 defer hardcode 拒絕路徑驗證**：`route_order(Venue::Dex)` / `route_order(Venue::Hyperliquid)` → `Err(VenueNotApproved)`；`route_order(Venue::BinancePerp / Spot)` → `Err(VenueDeferred("Y3+"))` | `cargo test --release order_router::tests::dex_hyperliquid_rejected` + `binance_y2_deferred` empirical PASS |
| 7 | V115 schema reference outline land 在 V115 placeholder spec（separate file）| V115 placeholder spec file exists + frontmatter status `SPEC-PLACEHOLDER` |
| 8 | 本 spec land 不破 0 既有 Rust hot path（OrderRouter 是 NEW trait；無 existing code 強制 implement）| `cargo build --release` PASS + `cargo test --release --workspace` PASS（既有 test 0 regression）|
| 9 | 中文注釋為主；無新增 English-only 注釋（per memory `feedback_chinese_only_comments`）| code review；新增注釋默認中文 |
| 10 | File size < 800 行（per `srv/CLAUDE.md` Code Structure Guardrails）| `wc -l rust/openclaw_engine/src/order_router.rs` < 800 |

**Sprint 6 IMPL 階段補加 acceptance criteria**：
- `maker_fill_rate_30d` calculation 1e-4 fixture（per V094 既有 maker_fill 計算範式 + 30d window sum semantics）
- Y2 threshold 70% trigger empirical（per ADR-0039 Y2 timeline）
- Adaptive routing audit log INSERT 對齊 V115 Part 1 schema
- BB Sprint 6 IMPL 期 confirm Bybit rebate tier precise threshold（per ADR-0039 OQ-1）

### 6.1 E1 IMPL Dispatch Brief（Sprint 1A-δ）

per Sprint 1A-δ workload 75-110 hr / 3-4 並行 sub-agent / 1 wall-clock week（per PA report 行 161-167）。

#### 6.1.1 Rust crate path 判斷

兩候選：

| Path | 優點 | 缺點 | 建議 |
|---|---|---|---|
| `rust/openclaw_engine/src/order_router.rs` | 與既有 execution module（execution_listener.rs / fast_track.rs）並列；對齊 ADR-0001 hot path actor | trait + struct 同 file；cross-crate share 受限 | **推薦**：對齊既有 module pattern |
| `rust/openclaw_types/src/order_router.rs`（trait）+ `rust/openclaw_engine/src/order_router_impl.rs`（IMPL）| trait 跨 crate share；types crate 不依賴 engine crate | 多 file；Sprint 1A-δ scope 過大 | 不推薦（Sprint 6+ IMPL 期視 cross-crate share 需要再拆） |

**E1 建議**：Sprint 1A-δ 採 candidate 1 — single file `rust/openclaw_engine/src/order_router.rs`；Sprint 6+ adaptive IMPL 期視 cross-crate share 需要再拆。

#### 6.1.2 E1 IMPL scope（Sprint 1A-δ 8-12 hr）

1. **新建 `rust/openclaw_engine/src/order_router.rs`** file：
   - `pub trait OrderRouter`（§2.1 6 method full signature）
   - `pub struct UnimplementedOrderRouter`（§2.2 default impl + 6 method `unimplemented!()` + §4.6/§4.7 guard rails hardcode）
   - 完整 helper struct + enum 集（§2.3 candidate signature；含 `OrderRequest` / `RoutingDecision` / `VenueHealth` / `NetPosition` / `SlippageEstimate` / `DefensiveAction` / `MakerFillRateStats` / `RebateTier` / `ColdStartWindow` / `RoutingError` / `RouteReason` / `LalTier`）
   - `pub struct MakerFillRateCounter` scaffold（§3.4；3 method 全 `unimplemented!()`）
   - 中文注釋為主（per `srv/CLAUDE.md` Code And Docs Rules + memory `feedback_chinese_only_comments`）

2. **`rust/openclaw_engine/src/lib.rs`** 或對應 mod 入口加 `pub mod order_router;`

3. **`rust/openclaw_engine/tests/order_router_tests.rs`** 或 inline `#[cfg(test)]` 新增 2-3 test：
   - test 1：trait signature compile-time check（trait object dyn safe + Send + Sync）
   - test 2：DEX / Hyperliquid 拒絕 path（觸發 `route_order` 用 `Venue::Dex` → 必 return `Err(VenueNotApproved)`）
   - test 3：Binance Y2 defer 路徑（觸發 `route_order` 用 `Venue::BinancePerp` → 必 return `Err(VenueDeferred("Y3+"))`）
   - test 4（可選）：default body `unimplemented!()` panic 驗（用 `#[should_panic(expected = "...")]` annotation）+ MakerFillRateStats struct + RebateTier enum round-trip

#### 6.1.3 ADR + V115 placeholder reference 必含

per `srv/CLAUDE.md` Code And Docs Rules，在 `order_router.rs` 頭部 doc comment include：

```rust
//! # M12 OrderRouter Trait
//!
//! per ADR-0039 — M12 OrderRouter Trait + maker_fill_rate metric
//! per V115 placeholder schema spec — Sprint 6+ IMPL phase 期 land
//! per Sprint 1A-δ interface reservation — Sprint 6+ adaptive logic IMPL；本 file scope = stub only
//!
//! Trait surface 對齊 ADR-0039 §Decision 1 表 6 method（v5.8 initial 5 + BB 5.21 audit push back maker_fill_rate_30d = 6）
```

#### 6.1.4 預估工時（per §7.1 + dispatch packet 行 161）

| Sub-task | 估時 |
|---|---|
| Trait 6 method signature + UnimplementedOrderRouter default impl | 3-4 hr |
| §4.6 D1a + §4.7 Y2 guard rails hardcode（route_order 內部 match） | 1-2 hr |
| Helper struct + enum 集（11 types + RouteReason / LalTier） | 2-3 hr |
| MakerFillRateCounter scaffold + ColdStartWindow / RebateTier enum | 1 hr |
| Test 2-4 條 IMPL | 1-2 hr |
| Doc comment 中文注釋 | 1 hr |
| **Total** | **8-12 hr** |

#### 6.1.5 E2 / E4 / QA review focus（per PA dispatch brief 建議）

- **E2 review 3 點**：
  1. trait 6 method signature 100% 對齊 ADR-0039 §Decision 1 全表（method name + param + return type）
  2. §4.6 D1a + §4.7 Y2 guard rails hardcode（非 config-driven；不可被 risk_config TOML override）
  3. default body `unimplemented!()` panic message descriptive（含 method 名 + Sprint phase + ADR ref）
- **E4 regression**：`cargo test --workspace` PASS（既有 test 全綠 + 新 test 全綠）；既有 Rust hot path 0 regression
- **QA review**：對齊 ADR-0039 §16 根原則合規 + AMD-2026-05-15-01 Stage 升級紀律 + ADR-0034 LAL Tier 3 protected boundary + DOC-08 §12 9 條安全不變量

---

## §7 IMPL Phase Split（per ADR-0039）

### 7.1 Sprint 1A-δ — DESIGN initial（本 spec 範圍）

- Trait signature lock（§2.1）
- `UnimplementedOrderRouter` default panic stub（§2.2）
- Helper struct candidate signature（§2.3）
- V115 placeholder spec frontmatter（separate file）
- ADR-0039 promoted from Proposed-pending-commit → Accepted（PA + PM sign-off）

**估時**：20-30 hr（per ADR-0039 + v5.8 §2 M12）；本 spec 約 5-8 hr 完成 80%。

### 7.2 Sprint 6 — Read-only logging（per ADR-0039）

- `route_order()` IMPL Bybit-only routing decision logic（PostOnly default + reverse_snipe 觸發切 taker）
- `MakerFillRateCounter::on_fill_observed()` wire-up（execution_listener.rs）+ V115 Part 1 INSERT + in-memory ring buffer 增量更新
- `maker_fill_rate_30d()` IMPL V115 Part 2 query + ring buffer hot read（per ADR-0039 §Decision 2 cold start fallback）
- `venue_health()` IMPL per-venue 健康度 calculation + caching
- `forecast_slippage()` IMPL L2 order book depth-based slippage 預測（對齊 ADR-0029 L2 snapshot fidelity）
- `reverse_snipe()` IMPL signal confidence + market direction confirmed threshold → 切換 PostOnly → taker
- adaptive routing toggle 內部 helper：read-only logging 階段不 enable adaptive routing（always default PostOnly）
- `routing_metrics()` 周邊 helper trait（per §2.4 OQ-6）IMPL V115 三表 aggregate query
- V115 三表 sqlx migration land（Linux PG dry-run mandatory per ADR-0011）
- M3 HEALTH_WARN dispatch hook（tier 跌出 < 0.60 sustained 3d）

**估時**：80-120 hr（per ADR-0039 + v5.8 §2 M12）。

### 7.3 Y2 Q1 — Advisory adaptive routing

- adaptive routing toggle 內部 helper return true（per venue × asset_class threshold > 70% sustained 7d）
- 但 advisory mode：only log audit；不實際改 routing behavior
- Operator 手動 review V115 Part 3 tier_transitions + Part 1 routing decisions 評估 adaptive 是否值得 enable
- LAL Tier 2 governance approval flow 設計 land

### 7.4 Y2 Q2+ — Auto-gate adaptive routing

- adaptive routing toggle 內部 helper return true → 實際改 routing behavior（per venue × asset_class routing profile shift）
- LAL Tier 2 audit before flip（governance approval required）
- 自動 reverse_snipe defense（per ADR-0039 §Decision 4 連續 N 筆切 taker 過頻 → throttle + alert）
- `cross_venue_position()` Y2 IMPL（per ADR-0033 Binance Y2 trading enable timeline）

---

## §8 Cross-V### Dependency Placeholder + Open Questions

### 8.1 Cross-V### Dependency

| V### | 關係 |
|---|---|
| V094 (fills_close_maker_audit) | **既有 column 範式 baseline**；`close_maker_attempt` + `close_maker_fallback_reason` 是 `maker_fill_rate_30d` 計算上游 |
| V107 (M11 replay_divergence_log per ADR-0038) | **與 V115 dedup OQ-4**；兩表正交並存 |
| V115 (M12 routing audit) | **本 spec reference**；frontmatter + outline 在 V115 placeholder spec；full DDL 待 Sprint 6+ IMPL 階段 |
| V103 (learning.hypotheses / preregistration / earn_movement_log) | **無直接 dependency**；V103 是 learning schema；本 spec 是 routing schema |
| V### range | V115 candidate；具體 number 待 V103 / V104 / V### head 對齊後確認 |

### 8.2 Open Questions（≥ 3 per operator requirement）

#### OQ-1: V115 schema 命名 `routing.*` vs `learning.*`

- ADR-0039 §Decision 3 候選 schema 用 `learning.*`
- 本 spec §4.2 提議改 `routing.*` 分離 routing audit 與 learning data
- **待 V115 placeholder spec finalize + PA / MIT review**：採 `routing.*` 還是 `learning.*`？

#### OQ-2: `UnimplementedOrderRouter` production fallback path

- Sprint 1A-δ stub `panic!` 不可進 production
- Sprint 6 IMPL 階段 default fallback 路徑：`LegacyDirectOrderRouter`（v5.7 既有不走 trait 的 PostOnly 邏輯）還是直接 `BybitOrderRouter`？
- **待 Sprint 6 IMPL 階段 PA 設計**

#### OQ-3: Sprint 1A-δ trait method 是否預留 async 簽名

- 當前 §2.1 trait method 全 sync signature（per ADR-0039 §Decision 1 全表 sync return）
- Bybit API submit_order 是 async I/O；Sprint 6 IMPL 階段是否需改 `async fn` + `Pin<Box<dyn Future<...>>>`？
- **待 BB + E1 Sprint 6 IMPL 階段確認**：是否 wrap async runtime adapter（tokio）vs trait method 直接 async；trait async signature 對 Rust async trait + dyn dispatch 設計影響重大
- **建議起點**：Sprint 1A-δ 保 sync per ADR-0039 §Decision 1；Sprint 6 IMPL 階段視 Bybit client API 實際 signature decide async 改造

#### OQ-4: `OrderRequest` 是否預留 `variant_id` field for M9 A/B test

- M9 A/B test framework 需 routing variant 分流（per §5.2）
- Sprint 1A-δ `OrderRequest` candidate signature 不含 `variant_id`
- Sprint 6 IMPL 階段 add field = struct binary layout 變更（若 trait method param by value vs by reference 影響）
- **建議起點**：Sprint 1A-δ 不加；Sprint 6 IMPL 階段 add 走 struct extension 範式

#### OQ-5: `maker_fill_rate_30d(venue, asset_class)` 與 per-symbol view 的 reconciliation

- Trait method signature expose `(venue: VenueId, asset_class: AssetClass) -> MakerFillRateStats`（per ADR-0039 §Decision 1 method 6）
- per-symbol view（GUI dashboard 場景需要）如何 derive？應用層 aggregate 邏輯走 helper module 或 SQL group-by
- V115 Part 2 schema 持 per-venue × per-asset-class snapshot（§4.1）
- **建議起點**：Sprint 1A-δ 保 trait `(venue, asset_class)` signature 不增 per-symbol method；Sprint 6 IMPL 期視 GUI dashboard 需要設計 helper aggregate

#### OQ-6: 草稿 v0 `record_fill` / `adaptive_routing_enabled` / `routing_metrics` 是否 promote 為周邊 helper trait

per §2.4 草稿 v0 3 method 不在 ADR-0039 §Decision 1 表內：

- `record_fill(order_id, fill)`：Fill ingest 是 `execution_listener.rs` 既有職責；不應在 OrderRouter trait；Sprint 6+ 透過 `MakerFillRateCounter::on_fill_observed(fill_event)` wire-up
- `adaptive_routing_enabled(symbol) -> bool`：不暴露於 trait；變為 `route_order()` 內部 IMPL detail（Sprint 6+ adaptive logic 是否在 bounds 內走 PostOnly default vs adaptive）
- `routing_metrics() -> RoutingMetricsSummary`：可放周邊獨立 trait `RoutingMetricsProvider`（Sprint 6+ IMPL phase）對應 GUI dashboard

**建議起點**：Sprint 1A-δ 不加 3 method 進 OrderRouter trait；Sprint 6+ IMPL 期 PA + E5 review 是否需 `RoutingMetricsProvider` 周邊 trait
**Owner**：PA Sprint 6 IMPL 期決議

#### OQ-7: Sprint 6+ adaptive IMPL 是否復用 既有 `execution_listener.rs` 路徑

- 既有 execution module 與 OrderRouter actor 邊界
- OrderRouter 是 routing decision layer，execution_listener 是 fill listener；理論上正交
- **建議起點**：Sprint 6+ IMPL 期 PA + E5 review；wire-up `MakerFillRateCounter::on_fill_observed()` 經 execution_listener.rs
- **Owner**：PA Sprint 6 IMPL 期決議

---

## §9 §二 16 原則合規確認

| # | 原則 | 是否相容 | 說明 |
|---|---|---|---|
| 1 | 單一寫入口 | ✅ | OrderRouter 在 IntentProcessor + Guardian 通過後執行 routing；不繞單一寫入口 |
| 2 | 讀寫分離 | ✅ | V115 三表 audit log；不寫 live state |
| 3 | AI 輸出 ≠ 命令 | ✅ | OrderRouter 在 Decision Lease 通過後執行；不繞 lease |
| 4 | 策略不繞風控 | ✅ | bounds + LAL 3 protection 雙層 gate；越界 fail-closed |
| 5 | 生存 > 利潤 | ✅ | rebate tier 跌出 emit M3 HEALTH_WARN 是 cost edge 結構性保護 = 生存紀律 |
| 6 | 失敗默認收縮 | ✅ | bounds 越界 fail-closed reject；reverse_snipe 過頻 throttle |
| 7 | 學習 ≠ Live | ✅ | V115 audit log（routing schema）不寫 live state；trait 計算純讀 |
| 8 | 交易可解釋 | ✅ | V115 Part 1 `route_reason` enum；audit「為什麼這 order 是 maker/taker」可 back-trace |
| 9 | 雙重防線 | ✅ | bounds（本地）+ LAL 3 protection（governance）雙層 |
| 11 | Agent 最大自主 | ✅ | Auto-routing 在 bounds 內 Agent 自主；越界走 operator confirm + LAL 3 |
| 13 | cost 感知 | ✅ | **本 spec 核心**；`maker_fill_rate_30d` 是 cost-edge structural protection |
| 14 | 零外部成本 | ✅ | Bybit 既有市場訂閱基礎設施；不依賴外部付費服務 |
| 16 | Portfolio > 孤立 trade | ✅ | venue × asset_class 矩陣 + cross_venue_position（Y2）是 portfolio thinking 的 routing-level 體現 |

### 9.1 DOC-08 §12 安全不變量（9 條）

| # | 不變量 | 本 spec 是否觸碰 |
|---|---|---|
| 1 | Pre-trade audit/replay 必開 | ✅ V115 Part 1 routing audit log；M11 replay 對照 |
| 2 | Lease 必在執行前已 acquired | ✅ §5.4 OrderRouter 在 Decision Lease acquire 後 route |
| 3 | 執行回報必落 fills 表 | ✅ `MakerFillRateCounter::on_fill_observed()` 經 execution_listener.rs Sprint 6+ wire-up + V115 Part 1 routing decision audit row |
| 4 | 風控降級 → engine 自動止血 | ✅ §5.1 bounds 越界 fail-closed |
| 5 | Authorization 過期/失效 → engine cancel_token shutdown | 🟡 OrderRouter 不直接管 authorization；Guardian 上游負責 |
| 6 | Mainnet 無 OPENCLAW_ALLOW_MAINNET → spawn 拒絕 | 🟡 Engine spawn 層負責；OrderRouter 是 hot path actor |
| 7 | Bybit retCode != 0 → fail-closed 不重試 | ✅ §2.1 `route_order()` 返回 `Result<RoutingDecision, RoutingError>`；error 不重試 |
| 8 | Reconciler 對賬差異 → 自動降級 paper | 🟡 Reconciler 層負責；OrderRouter 不直接管 |
| 9 | Operator 角色與 live_reserved 缺一即拒 | 🟡 Engine 啟動層 + Python control_api 層負責 |

### 9.2 §四 硬邊界

本 spec **不觸碰任何硬邊界**：
- 不改 `execution_state` / `execution_authority` / `live_execution_allowed`
- 不改 `decision_lease_emitted` / `max_retries`
- 不改 `OPENCLAW_ALLOW_MAINNET` / `live_reserved` / `authorization.json`
- 不加 hidden retry path

---

## §10 Cross-References

- **ADR-0039**：`srv/docs/adr/0039-m12-order-router-trait-and-maker-fill-rate-metric.md`（trait 6 method + V115 三表 audit infrastructure；本 spec 直接父）
- **v5.8 §2 M12**：`srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md`（engineering scope）
- **V115 placeholder spec**：`srv/docs/execution_plan/2026-05-21--v115_m12_order_router_reserved_schema_spec.md`（本 spec 同日 land；frontmatter + outline）
- **V103/V104 spec**：`srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md`（V### range + Guard 範式 reference）
- **V094 (fills_close_maker_audit)**：`srv/sql/migrations/V094__fills_close_maker_audit.sql`（既有 `close_maker_attempt` + `close_maker_fallback_reason` 範式 baseline）
- **ADR-0001 (Rust 為唯一交易權威)**：`srv/docs/adr/0001-rust-as-trading-authority.md`（OrderRouter Rust hot path actor）
- **ADR-0029 (market.public_trades + L2 snapshot)**：`srv/docs/adr/0029-market-trade-tape-and-orderbook-l2-storage-policy.md`（maker_fill 計算數據源）
- **ADR-0033 (ADR-0006 amendment)**：`srv/docs/adr/0033-adr-0006-bybit-binance-amendment.md`（Y2 cross-venue routing 對齊）
- **ADR-0034 (Decision Lease LAL)**：`srv/docs/adr/0034-decision-lease-layered-approval-lal.md`（LAL 3 越 bounds protection）
- **ADR-0038 (M11 replay)**：`srv/docs/adr/0038-m11-continuous-counterfactual-replay-and-liquidations-source.md`（V107 與 V115 dedup OQ-4 來源）
- **crypto-microstructure-knowledge skill**：rebate tier 對照表 + PostOnly fee 計算 + reverse_snipe cost trade-off
- **`docs/references/2026-04-04--bybit_api_reference.md`**：Bybit V5 maker/taker fee + rebate tier reference

---

## §11 Sign-off

| Role | Source | Date | Status |
|---|---|---|---|
| PA | 本 spec 起草 + 草稿 v0 5-method trait surface 修正對齊 ADR-0039 6 method authoritative（Sprint 1A-δ deliverable per v5.8 §2 M12 + ADR-0039）| 2026-05-21 | ✅ Drafted (SPEC-PARTIAL-V0; 6-method 對齊修訂後) |
| Operator | 主會話 PM dispatch via Sprint 1A-δ deliverable | 2026-05-21 | 🟡 PROPOSED-pending-commit |
| E1 | OrderRouter trait Sprint 1A-δ interface stub IMPL owner — `rust/openclaw_engine/src/order_router.rs` 新建 file + 6-method trait + UnimplementedOrderRouter default impl `unimplemented!()` + §4.6 D1a + §4.7 Y2 guard rails hardcode + Helper struct/enum 11 types + MakerFillRateCounter scaffold + 2-4 unit test | TBD（Sprint 1A-δ）| 🟡 PENDING |
| E2 | Sprint 1A-δ E1 IMPL review focus = trait 6 method signature 100% 對齊 ADR-0039 §Decision 1 + guard rails hardcode 不可 config-driven + default body panic message descriptive（per §6.1.5） | TBD（Sprint 1A-δ）| 🟡 PENDING |
| E4 | `cargo test --workspace` regression（per §6.1.5 + AC-1 + AC-2 + AC-6 + AC-8 + AC-10） | TBD（Sprint 1A-δ）| 🟡 PENDING |
| QA | 16 根原則合規 + AMD-2026-05-15-01 Stage 升級紀律 + ADR-0034 LAL Tier 3 protected boundary review + DOC-08 §12 9 條安全不變量 | TBD（Sprint 1A-δ）| 🟡 PENDING |
| QC | mSPRT / AVI / Bonferroni 校正不適用（M9 spec 域）；本 spec maker_fill_rate 採樣計算對齊（OQ-3 cold start enum） | TBD（Sprint 6） | 🟡 PENDING |
| BB | Bybit rebate tier precise threshold confirm（ADR-0039 OQ-1）+ ToS posture 對齊 ADR-0033 §4.2 + async signature 評估（OQ-3） | TBD（Sprint 6） | 🟡 PENDING |
| E5 | Slippage forecast performance review（Sprint 6+）+ slicing IMPL（Sprint 7-8 sub-spec）+ MakerFillRateCounter actor-internal vs cross-process IPC（per Sprint 6+ IMPL phase） | TBD（Sprint 6+） | 🟡 PENDING |
| FA | Per-strategy reverse-snipe threshold（per ADR-0039 OQ-2）+ slicing market impact 估算 + Copy Trading aggregator 不影響 routing（per ADR-0030） | TBD（Sprint 6+） | 🟡 PENDING |
| MIT | V094 既有 schema audit + V115 三表 cross-V### dependency review（per ADR-0010 + V094/V095 對齊）+ V115 schema 命名 reconciliation（OQ-1 `routing.*` vs `learning.*`） | TBD（Sprint 1A-δ V115 placeholder finalize / Sprint 6 IMPL）| 🟡 PENDING |
| PM | Sprint 1A-δ closure → ADR-0039 promote Proposed-pending-commit → Accepted；V115 schema commit | TBD（Sprint 1A-δ 結束）| 🟡 PENDING |

---

*OpenClaw / Arcane Equilibrium M12 OrderRouter Design Spec — Sprint 1A-δ deliverable; trait interface stub level; IMPL phased Sprint 6+ per ADR-0039*

---

Sub-agent dispatch: PA Sprint 1A-δ M12 track
完成時間: 2026-05-21
