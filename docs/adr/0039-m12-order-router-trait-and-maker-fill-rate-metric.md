# ADR 0039: M12 OrderRouter Trait — Maker-Fill-Rate Metric + Adaptive Routing Audit Schema

Date: 2026-05-21
Status: **Proposed-pending-commit**（v5.8 §2 M12 module ADR 級落地；BB 5.21 audit push back 落地：「OrderRouter trait 必含 `maker_fill_rate_30d` metric 以監控 Bybit ToS rebate / maker rebate eligibility」→ 新增 5+1 = 6 method trait + V115 adaptive routing audit log schema）
Operator Sign-off: 2026-05-21（主會話 PM dispatch via v5.8 §2 M12「Adaptive Order Routing DESIGN initial / IMPL delayed」per operator: do even if delayed）
Related: v5.8 §2 M12 / ADR-0029 (market.public_trades + orderbook_l2_snapshot trade tape policy — maker fill 計算數據源) / ADR-0033 (ADR-0006 amendment — Binance Y2 trading defer + DEX/Hyperliquid not approved；本 ADR Y2 cross-venue routing 對齊) / ADR-0030 (Copy Trading evidence-gated — Bybit 平台內 Copy Trading 不影響本 ADR routing) / ADR-0034 (Decision Lease LAL — routing 超 bounds 走 LAL 3 protected) / `docs/references/2026-04-04--bybit_api_reference.md` (Bybit V5 maker/taker fee + rebate tier reference) / crypto-microstructure-knowledge skill (PostOnly fee 計算 + rebate tier 對照表) / V094 fills_close_maker_audit (per CR-14 既有 maker fill schema 範式) / V115 schema reserve (placeholder pending CR-14)

## Context

### 起源

v5.8 §2 M12 列「Adaptive Order Routing」module，spec 路由維度包含 venue choice / order type / slicing / time-in-force tuning + adaptive logic (per-symbol routing profile / maker-vs-taker decision / reverse-snipe defense)：

```
Engineering scope:
  - Sprint 1A: OrderRouter trait interface + ADR-0039 (interface stub only) (20-30 hr)
  - Sprint 6: Maker-vs-taker adaptive logic IMPL (Bybit only) (80-120 hr)
  - Sprint 7-8: Slicing IMPL (TWAP / iceberg) (60-100 hr)
  - Y2: Cross-venue routing (when Binance trading enabled per ADR-0006 amendment) (100-160 hr)
```

v5.8 §2 M12 spec **初始列 5 個 OrderRouter trait method**（per v5.8 §2 + H-7 dispatch consolidation review）：

1. `route_order(order_request) -> RoutingDecision`
2. `venue_health(venue) -> VenueHealth`
3. `cross_venue_position(asset) -> NetPosition`
4. `forecast_slippage(order, market_snapshot) -> SlippageEstimate`
5. `reverse_snipe(market_event) -> Option<DefensiveAction>`

### BB 5.21 audit push back — maker_fill_rate_30d metric 缺失

BB 5.21 audit 對 v5.8 §2 M12 initial 5-method trait spec catch 到一個結構性 gap：

> Bybit broker rebate / market maker rebate eligibility 需要持續監控 **30d rolling maker fill rate**。Bybit ToS 規定（per `docs/references/2026-04-04--bybit_api_reference.md` + crypto-microstructure-knowledge skill rebate tier 對照表）：
>
> - **Tier 1 maker rebate**：rolling 30d maker fill notional / total fill notional ≥ 80%
> - **Tier 2 maker rebate**：≥ 70%
> - **Default tier**：≥ 50%
> - 跌出對應 tier → rebate 自動 down-shift，下一個 settlement period 起 fee schedule 調整
>
> 若 OrderRouter 沒有 `maker_fill_rate_30d` metric → 無法持續監控 rebate eligibility → 隨時可能掉出 rebate tier 不自知 → **直接 cost edge degradation**（每 1% maker rate downshift 對應 ~0.2-0.5 bps 平均 fee penalty per `phase_1b_calibration` 既有 fill quality data）。

v5.7 既有 maker_fill_rate 計算邏輯（per `feedback_micro_profit_fix_intent` memory + V094 `close_maker_attempt` column）但**只 per-strategy + per-fill**；缺 **venue-level rolling 30d** 維度。本 ADR 把該 metric 升級為 OrderRouter trait first-class method。

### 為什麼這形成 ADR 級治理決策

如果 M12 Sprint 1A trait interface 不含 `maker_fill_rate_30d`：

1. **下游 IMPL drift** — Sprint 6 maker-vs-taker adaptive IMPL 時才補 method = trait signature 變更 = 多版本 IMPL 不一致
2. **Rebate tier 監控盲區** — Sprint 1A 後 trait stub 已部署但缺 metric → 鎖入沒有 monitoring 的 baseline → cost edge silent loss
3. **Audit log schema drift** — V115 reserve 規畫時若 trait 缺 metric column，schema 後續 add column 違反 V### Guard B 範式（per ADR-0011 V-migration PG dry-run mandatory）
4. **與 ADR-0033 D12 + ToS posture 對齊缺失** — ADR-0033 §4.2 ToS posture「Bybit ToS 遵守 BB agent 持續監測」要 trait-level 體現

本 ADR 把 `maker_fill_rate_30d` 升為 OrderRouter trait 第 6 method + V115 audit log schema 鎖入治理紀律。

### v5.8 §2 M12 與 ADR-0029 trade tape policy 的依賴關係

ADR-0029 落地 `market.public_trades` tick-level trade tape；本 ADR `maker_fill_rate_30d` 計算依賴 ADR-0029 之 fill / trade source：

- **不在 ADR-0029 land 前 IMPL**（per §Decision 2 計算數據源）；Sprint 1A interface stub 可先定，Sprint 6 IMPL 必對齊 ADR-0029 timeline
- ADR-0029 V094 `close_maker_attempt` + `close_maker_fallback_reason` 既有 column 範式是本 ADR `maker_taker` field 的 schema baseline

### 為什麼 Sprint 1A DESIGN initial / IMPL delayed（per operator）

operator 在 v5.8 §2 M12 spec 中明示「do even if delayed」。理由：

1. **DESIGN cost 顯著（20-30 hr Sprint 1A）但 IMPL cost 巨大（240-380 hr Y1-Y2）** — early DESIGN lock interface 避免後續 IMPL drift
2. **maker rebate eligibility 監控不可等到 Sprint 6 IMPL** — Sprint 1A trait stub 中 `maker_fill_rate_30d` interface 可先接 V094 既有 per-strategy data 作 degraded 計算（per-strategy aggregate → venue-level sum）
3. **與 ADR-0029 trade tape land 同步**（per ADR-0029 §OQ-4 Phase 1b calibration timing）

### v5.7 既有 `feedback_micro_profit_fix_intent` 維 maker_fill_rate 半成品

memory 中 `feedback_micro_profit_fix_intent` 條目記載「MICRO-PROFIT-FIX-1 設計意圖：語意應為『有微利就套（net>0）』」。該 fix 配套既有 maker_fill_rate **per-fill / per-strategy** 計算邏輯：

- V094 `close_maker_attempt boolean NOT NULL` + `close_maker_fallback_reason text` enum 10 值
- Per-fill emit `is_maker` flag（via Bybit `execType` field — `Trade` 即 taker fill / `BustTrade` 等其他 enum 分流）

但 v5.7 baseline **沒有 venue-level 30d rolling 計算 + persistent snapshot**。本 ADR Decision 2 加固該層。

## Decision

**Proposed**：以下 5 個治理立場 + OrderRouter trait 6 method + V115 audit log schema 落地為 ADR 級規範。本 ADR Sprint 1A 階段 commit interface stub + ADR；schema / IMPL 細節 promote 至 Accepted 待 CR-14 finalize 後。

### Decision 1 — OrderRouter Trait 6 Method（v5.8 initial 5 + NEW `maker_fill_rate_30d`）

| # | Method | Signature 候選 | 用途 |
|---|---|---|---|
| 1 | `route_order` | `route_order(order_request: OrderRequest) -> RoutingDecision` | 主路由決策入口；返回 venue + order_type + slicing + time-in-force |
| 2 | `venue_health` | `venue_health(venue: VenueId) -> VenueHealth` | venue 健康度（rejection rate / latency p99 / ws connectivity）|
| 3 | `cross_venue_position` | `cross_venue_position(asset: Asset) -> NetPosition` | 跨 venue 淨倉位（Y1 Bybit only 即 single-venue；Y2 Binance trading enable 後生效）|
| 4 | `forecast_slippage` | `forecast_slippage(order: Order, market_snapshot: MarketSnapshot) -> SlippageEstimate` | 滑點預測；對齊 ADR-0029 L2 snapshot fidelity |
| 5 | `reverse_snipe` | `reverse_snipe(market_event: MarketEvent) -> Option<DefensiveAction>` | Reverse-snipe defense（per Q3 market-driven trigger insight）|
| **6 (NEW)** | `maker_fill_rate_30d` | `maker_fill_rate_30d(venue: VenueId, asset_class: AssetClass) -> MakerFillRateStats` | **NEW per BB 5.21 audit + CR-14**；Rebate eligibility 持續監控 |

#### `MakerFillRateStats` struct 候選

```rust
pub struct MakerFillRateStats {
    pub venue: VenueId,                   // BybitPerp / BybitSpot / BybitOption / BinanceSpot / BinancePerp
    pub asset_class: AssetClass,
    pub window_start_ts: DateTime<Utc>,   // T - 30d
    pub window_end_ts: DateTime<Utc>,     // T - 0
    pub maker_fill_notional_usdt: f64,
    pub total_fill_notional_usdt: f64,
    pub maker_fill_ratio: f64,            // 分子 / 分母（0.0..1.0）
    pub current_tier: RebateTier,         // T1 / T2 / Default / Below_default（per Bybit ToS tier table）
    pub days_in_current_tier: u32,        // 跌出 tier 時觸發 cooldown 紀律
}

pub enum RebateTier {
    Tier1,       // maker% >= 80%
    Tier2,       // maker% >= 70%
    Default,     // maker% >= 50%
    BelowDefault, // < 50%（fee schedule full taker rate；Alert）
}
```

### Decision 2 — `maker_fill_rate_30d` 計算規範

| 元素 | 設計 |
|---|---|
| 窗口 | **Rolling 30d**（per Bybit rebate tier evaluation period 對齊；per crypto-microstructure-knowledge skill rebate tier 對照表）|
| 維度 | **per-venue × per-asset-class**（BybitPerp / BybitSpot / BybitOption 獨立計算；Y2 Binance Y2 trading enable 後對齊）|
| 分子 | maker fill notional USDT (30d sum) — 對齊 V094 `close_maker_attempt = TRUE AND close_maker_fallback_reason IN ('maker_filled', NULL)` 條件 |
| 分母 | total fill notional USDT (30d sum) — 對齊 fills table 30d window 全 fill |
| 更新頻率 | **每 fill 觸發增量更新**（per ADR-0029 fill tape + V094 既有 column 範式）+ **每日 EOD snapshot**（per §Decision 3 V115 schema）|
| 持久層 | (a) **In-memory ring buffer** 在 OrderRouter actor 維持 hot 計算（per ADR-0001 Rust hot path）(b) **`learning.maker_fill_rate_30d_snapshots`** 表（V115 part 2）每日 EOD snapshot |
| Bybit rebate tier 對照表 | 對齊 crypto-microstructure-knowledge skill：T1 ≥ 80% / T2 ≥ 70% / Default ≥ 50% / BelowDefault < 50%（per Bybit V5 fee schedule docs；BB confirm precise threshold 待 Sprint 6 IMPL 期 sub-task）|
| Alert 觸發 | `maker_fill_ratio < 0.60` sustained 3d → **M3 HEALTH_WARN**（per CR-7 dedup contract M3 為 single health authority）+ Slack alert + 紀錄到 `replay_divergence_log`-equivalent governance ledger |
| Tier transition log | 任何 `current_tier` 變化 emit 一條 `learning.routing_tier_transitions` row（V115 part 3）|

#### Cold start 期 maker_fill_rate 計算

新 deploy strategy / 新 venue 接入時 30d 窗口未滿，候選 fallback：

- < 7d data：返回 `MakerFillRateStats { maker_fill_ratio: NaN, current_tier: Unknown }` + warn flag
- 7d-30d data：返回計算值但 `current_tier` 標記 `Provisional` enum variant
- ≥ 30d data：full tier classification

具體 enum + behavior 待 Sprint 1A IMPL 期 stub 設計確認；本 ADR 不 commit 細節。

### Decision 3 — V115 Adaptive Routing Audit Schema（候選，待 CR-14 finalize）

V115 涵蓋 3 個關聯 table：

#### V115 Part 1：`learning.order_routing_decisions`（per-decision audit log）

```sql
CREATE TABLE IF NOT EXISTS learning.order_routing_decisions (
    decision_id           TEXT        NOT NULL,         -- UUID per route_order call
    ts                    TIMESTAMPTZ NOT NULL,
    asset                 TEXT        NOT NULL,
    venue                 TEXT        NOT NULL,         -- BybitPerp / BybitSpot etc.
    maker_taker           TEXT        NOT NULL,         -- 'maker' / 'taker' (chosen route)
    slice_count           SMALLINT    NOT NULL DEFAULT 1, -- 1 = single-shot / 2+ = TWAP/iceberg
    slippage_bps_estimated REAL,                          -- from forecast_slippage()
    slippage_bps_realized  REAL,                          -- post-fill backfilled
    rebate_applied         BOOLEAN     NOT NULL DEFAULT FALSE,
    engine_mode            TEXT        NOT NULL,        -- per ADR-0005 live / live_demo / demo
    route_reason           TEXT        NOT NULL,        -- 'default_postonly' / 'reverse_snipe_confirmed' / 'urgency_taker' / 'rebate_protection' etc.
    PRIMARY KEY (decision_id)
);

CREATE INDEX IF NOT EXISTS idx_routing_decisions_ts_desc
  ON learning.order_routing_decisions (ts DESC, asset, venue);

CREATE INDEX IF NOT EXISTS idx_routing_decisions_reverse_snipe
  ON learning.order_routing_decisions (ts DESC) WHERE route_reason = 'reverse_snipe_confirmed';
```

**PK 設計理由**：`decision_id` 是 UUID 全局唯一；對齊 V094 / V095 既有 lossy-pk avoidance 範式。

**每 `route_order()` call emit 1 row**；audit query「為什麼這 order 是 maker？」可從 `decision_id` back-trace 到 OrderRouter actor state snapshot。

#### V115 Part 2：`learning.maker_fill_rate_30d_snapshots`（每日 EOD snapshot）

```sql
CREATE TABLE IF NOT EXISTS learning.maker_fill_rate_30d_snapshots (
    snapshot_date      DATE        NOT NULL,
    venue              TEXT        NOT NULL,
    asset_class        TEXT        NOT NULL,
    window_start_ts    TIMESTAMPTZ NOT NULL,
    window_end_ts      TIMESTAMPTZ NOT NULL,
    maker_fill_notional_usdt  REAL NOT NULL,
    total_fill_notional_usdt  REAL NOT NULL,
    maker_fill_ratio          REAL NOT NULL,
    current_tier              TEXT NOT NULL,
    days_in_current_tier      INTEGER NOT NULL,
    PRIMARY KEY (snapshot_date, venue, asset_class)
);
```

**Retention**：365d（per H-22 R4 governance retention 規範；rebate tier 評估走年度級 trend）。

#### V115 Part 3：`learning.routing_tier_transitions`（tier 變化 event log）

```sql
CREATE TABLE IF NOT EXISTS learning.routing_tier_transitions (
    transition_id      TEXT        NOT NULL,
    ts                 TIMESTAMPTZ NOT NULL,
    venue              TEXT        NOT NULL,
    asset_class        TEXT        NOT NULL,
    from_tier          TEXT        NOT NULL,
    to_tier            TEXT        NOT NULL,
    maker_fill_ratio   REAL        NOT NULL,
    alert_dispatched   BOOLEAN     NOT NULL DEFAULT FALSE,    -- M3 HEALTH_WARN dispatched?
    PRIMARY KEY (transition_id)
);
```

**Guard 範式**：對齊 V094 / V095 / V107 既有三 Guard layer（per ADR-0010 + `feedback_v_migration_pg_dry_run.md` Linux PG dry-run mandatory）。

### Decision 4 — Reverse-Snipe Defense（per Q3 market-driven trigger insight）

| 元素 | 設計 |
|---|---|
| 預設 routing | **PostOnly maker**（per crypto-microstructure-knowledge skill PostOnly fee 計算；maker rebate eligibility 對齊）|
| 切換 taker 觸發條件 | (a) **Signal confidence ≥ X**（per-strategy 配置；初始候選 0.7）+ (b) **Market direction confirmed within Yms**（per-strategy 配置；初始候選 200ms）|
| 切換 record | 必 emit V115 Part 1 `route_reason='reverse_snipe_confirmed'`（per §Decision 3）|
| 守住 maker baseline 紀律 | 連續 N 筆切換 taker（per asset_class）若導致 `maker_fill_rate_30d` 預估跌入 BelowDefault tier → 觸發 OrderRouter 主動 throttle reverse_snipe → emit Slack warn + 紀錄 routing_tier_transitions 預測 row |
| Reverse-snipe 與 cost trade-off | crypto-microstructure-knowledge skill 提供 fee penalty 計算：每筆 taker fill 比 maker rebate 多 ~0.05-0.10% notional；連續 3 次 reverse_snipe 在 0.3% notional 級別 alpha 上勉強 break-even；4+ 次需 alpha confidence > 0.8 才合理 |

### Decision 5 — Bounds + LAL 3 Protection（per ADR-0034）

| 元素 | 設計 |
|---|---|
| 單 order USD size cap | Operator-set；**initial $500**（per v5.8 §2 M12 spec）|
| Per-strategy slippage tolerance | Operator-set；超 tolerance → fail-closed reject + alert |
| Auto-routing 範圍 | 在 cap + tolerance 內 OrderRouter 自主決策；無需 lease 升級 |
| **越界要求** | **越 cap 或 tolerance → require operator confirm + LAL 3 protected**（per ADR-0034 LAL 3 = new strategy promotion 永遠 operator approval；本 ADR 援用同等級確認）|
| 為什麼 LAL 3 而非 LAL 2 | 越界 single-order $ size 影響 cost edge + market impact + risk envelope 多維度；不是純 cross-strategy reweight（LAL 2）；對齊 ADR-0034「new strategy promotion 永遠 operator approval」精神 |
| 違反 LAL 3 = fail-closed | 越界 + 未 operator confirm → IntentProcessor reject + emit `guardian_block_log` row with `block_reason='router_bounds_exceeded'` |

## Open Questions（不在本 ADR resolve）

### OQ-1: Bybit rebate tier precise threshold（80% / 70% / 50%）

**待 BB Sprint 6 IMPL 期 confirm**：

- crypto-microstructure-knowledge skill 提供 baseline tier table（per market maker 通用 convention）
- Bybit V5 fee schedule docs 可能與 skill 表略有差異（per Bybit periodic fee schedule revision）
- 需要 BB 在 IMPL 前對齊 Bybit official docs + 與 PM 確認 jurisdiction 適用版本

**建議起點**：採 skill 表 80% / 70% / 50% 作 Sprint 1A trait stub 默認值；Sprint 6 IMPL 期 BB confirm 後可能微調。

### OQ-2: Per-strategy vs venue-uniform reverse-snipe threshold

**待 QC + FA review**：

- 不同 strategy（grid 穩定 BBO / bb_breakout 高 vol / funding_arb 中 vol）的 signal confidence + market direction 噪音不同
- Per-strategy threshold IMPL 複雜度高但 cost edge 提升明顯
- Venue-uniform threshold IMPL 簡單但對 high-vol strategy under-trigger

**建議起點**：per-strategy threshold；schema 預留 column。

### OQ-3: Maker_fill_rate cold start fallback（< 30d data）

**待 QC review**：

- 新 strategy / 新 venue 在 < 7d / 7d-30d 期間如何 derive tier
- 是否需要 cohort-level baseline 作 priors

**建議起點**：per §Decision 2 cold start fallback enum；QC calibration 後 promote。

### OQ-4: V115 schema vs V107（M11 replay log）dedup

**待 CR-14 finalize**：

- V107（M11 replay_divergence_log）與 V115（routing audit log）兩表獨立
- 是否需要 cross-reference column（如 V115 `decision_id` 對應 V107 `replay_id` 重放）

**建議起點**：兩表獨立 + V107 / V115 各自 PK；replay 階段透過 `asset + ts ± window` 做 fuzzy join；CR-14 review 後決定是否加 explicit FK。

### OQ-5: Cross-venue routing Y2 IMPL（per ADR-0033 Binance Y2 enable）

**待 ADR-0033 Y2 evaluation 通過後**：

- ADR-0033 Decision 2 Binance trading defer Y2 conditional；Y2 evaluation 通過後 cross_venue_position + cross-venue route_order 才 enable
- 本 ADR Sprint 1A trait method `cross_venue_position` 在 Y1 接 stub「Single-venue: Bybit only」implementation；Y2 enable 後 IMPL 對齊 ADR-0033

**建議起點**：Sprint 1A stub return Single-venue position；Y2 IMPL 對齊 ADR-0033 Decision 2 timeline。

### OQ-6: Slicing IMPL（TWAP / iceberg）Sprint 7-8 設計

**待 E5 + FA review**：

- TWAP for unlock SHORT entry（per v5.8 §2 M12 spec）的時間窗口設計
- iceberg for pairs（funding_arb leg execution）的 sub-order size 設計
- 對齊 ADR-0026 direct-exploit bypass CPCV evidence quality

**建議起點**：Sprint 7-8 IMPL 階段獨立 sub-spec；本 ADR 只 lock trait method signature。

## Alternatives Considered

| Alternative | 棄因 |
|---|---|
| **不加 `maker_fill_rate_30d`（per-fill 計算即可）** | (a) per-fill 計算缺持續 monitoring view；trigger 不主動 emit (b) BB rebate eligibility 跌出 tier 不自知 → silent cost edge degradation (c) trait stub 在 Sprint 1A 沒這 method 後續 add 違反 V### Guard B 範式 |
| **採 7d rolling 替代 30d** | rebate tier 評估通常 30d 滑窗（per crypto-microstructure-knowledge skill + Bybit fee schedule 對應 evaluation period）；7d window 對 rebate tier transition 預測過短 |
| **maker_fill_rate 計算精度用 fill count 不用 notional** | (a) Notional 更貼近 rebate amount 真實意義（rebate 按 trade notional × fee rate 計算）(b) Count-based 計算對大小單偏重不對稱（100 筆 $10 maker fill 不如 1 筆 $10k maker fill）(c) Bybit ToS rebate tier evaluation 走 notional |
| **OrderRouter trait 不含 maker_fill_rate，由獨立 RebateMonitor module 承擔** | (a) 分離違反「routing decision = cost-aware decision」精神（per §二 原則 13 cost 感知）(b) RebateMonitor 與 OrderRouter actor 通信增加 IPC overhead (c) 兩 module 各自 PR / review 增 sprint coordination cost |
| **Tier transition log 不獨立表，直接寫 routing_decisions** | (a) tier transition 是 governance event 不是 routing event (b) 同表 mixed semantics 增 query 複雜度 (c) tier transition 觸發 M3 HEALTH_WARN 需 explicit dispatch hook |
| **Reverse-snipe 不需要單獨 `route_reason` column** | (a) audit「為什麼這次 taker 不 maker」是 cost trade-off 解釋核心 (b) `route_reason` enum 支援未來新 reason 擴展（如 'liquidity_sweep_defense' / 'partial_fill_chase'）(c) 對齊 §二 原則 8「交易必可重構並解釋」 |
| **Bounds 越界走 LAL 2 而非 LAL 3** | (a) LAL 2 是 cross-strategy reweight；單 order $ size 越界不是 cross-strategy 範疇 (b) LAL 3 涵蓋「new strategy promotion / 高影響 single decision」對應更貼切 (c) 越界 single order = market impact + cost edge + risk envelope 多維度，需 operator final review |
| **不設 `days_in_current_tier` cooldown** | tier 在 boundary 附近震盪會頻繁 emit transition；缺 cooldown → 噪音 log；應對齊 hysteresis pattern |

## Consequences

### Positive

- **Bybit ToS rebate eligibility 持續監控** — `maker_fill_rate_30d` 是 first-class trait method；rebate tier 跌出主動 emit M3 HEALTH_WARN + Slack alert；對齊 ADR-0033 §4.2 ToS posture
- **Cost edge 結構性保護** — 連續 maker% downshift 在 60% sustained 3d 之前主動 emit；避免 silent loss
- **Audit log 完整性** — V115 Part 1 routing_decisions 對每筆 order 記 `decision_id + route_reason`；audit「為什麼這 order 是 maker / taker」可 back-trace；對齊 §二 原則 8
- **Sprint 1A interface stub lock 避免下游 drift** — 6 method signature 在 Sprint 1A commit；Sprint 6 IMPL 對齊既有 interface 不需 add method
- **與 ADR-0029 trade tape policy 對齊** — `maker_fill_rate_30d` 計算數據源依賴 ADR-0029 fill tape + V094 既有 column；schema 範式正交並存
- **Reverse-snipe defense 明示** — `route_reason='reverse_snipe_confirmed'` 是 first-class enum；audit chain 不斷裂
- **LAL 3 越界 protection** — 對齊 ADR-0034 governance；單 order $ size 越界走 operator confirm + LAL 3 governance
- **V115 schema 候選對齊 V094 / V095 / V107 既有 PK + Guard 範式** — 不引入新範式 drift；對齊 `feedback_v_migration_pg_dry_run.md` Linux PG dry-run mandatory

### Negative / Risk

- **Sprint 1A DESIGN cost 20-30 hr** — interface stub + ADR 估時；mitigation = stub IMPL 可 reuse V094 既有 maker_fill column data 作 degraded 計算入口
- **`maker_fill_rate_30d` 計算依賴 30d historical accumulation** — 新 venue（Y2 Binance trading enable）接入後 30d 期內 tier 不可用；mitigation = OQ-3 cold start fallback enum
- **In-memory ring buffer 與 PG snapshot 一致性** — actor restart 後 ring buffer 重建 必須從 PG 重 fetch；mitigation = OrderRouter actor lifecycle 包含 ring buffer rebuild step
- **Reverse-snipe threshold per-strategy 配置複雜度** — IMPL 後 strategy config schema 變更；mitigation = OQ-2 設計 + 對齊既有 strategy config TOML pattern
- **V115 三表 IMPL 同步** — 三表 Guard A/B/C 三層必須對齊；mitigation = Sprint 6+ IMPL 期間 Linux PG dry-run mandatory（per ADR-0011）
- **Bybit fee schedule revision** — Bybit 可能 periodic 調整 rebate tier threshold；mitigation = OQ-1 BB Sprint 6 IMPL 期 confirm + 後續 schedule revision 走 ADR-0033 amendment 對齊
- **Slippage_bps_realized backfill 時延** — fill 完成後才能填回 V115 Part 1 column；mitigation = nightly cron backfill + `slippage_bps_realized` 允許 NULL 一段時間
- **Cross-venue routing Y2 ADR-0033 dependency** — `cross_venue_position` Y2 IMPL 對應 ADR-0033 Decision 2 Y2 evaluation pass；mitigation = OQ-5 對齊；Sprint 1A stub return single-venue

### 與既存設計協作

| 既存元素 | 與本 ADR 關係 |
|---|---|
| ADR-0029 (market.public_trades + orderbook_l2_snapshot) | **計算數據源**；`maker_fill_rate_30d` 依賴 ADR-0029 trade tape + V094 既有 column |
| ADR-0033 (ADR-0006 amendment — Binance Y2 trading defer) | **Y2 cross-venue routing 對齊**；`cross_venue_position` Y2 enable 時對應 ADR-0033 Decision 2 timeline |
| ADR-0033 §4.2 ToS posture | **本 ADR `maker_fill_rate_30d` 是 ToS 持續監測的 trait-level 體現** |
| ADR-0034 (Decision Lease LAL) | **越 bounds 走 LAL 3 protected**（per §Decision 5）；對齊 ADR-0034 LAL 3 governance |
| ADR-0030 (Copy Trading evidence-gated) | **Copy Trading 在 Bybit 平台內進行**；不影響本 ADR routing；正交 |
| ADR-0001 (Rust 為唯一交易權威) | **OrderRouter 是 Rust hot path actor**；ring buffer 計算不阻塞 trading thread |
| ADR-0005 (engine_mode tag live_demo) | V115 `engine_mode` column 對齊 ADR-0005 enum（live / live_demo / demo / paper）|
| ADR-0010 (TimescaleDB hypertable + Guard migrations) | **V115 三表 Guard A/B/C 範式對齊**；Linux PG dry-run mandatory |
| ADR-0011 (V-migration PG dry-run mandatory) | **V115 schema land 前必走 Linux PG dry-run** |
| V094 (fills_close_maker_audit) | **既有 column 範式 baseline**；`close_maker_attempt` + `close_maker_fallback_reason` 是 maker_fill 計算上游 |
| `feedback_micro_profit_fix_intent` | **既有 maker_fill_rate 半成品**；本 ADR 升級為 venue-level 30d rolling |
| crypto-microstructure-knowledge skill | **rebate tier 對照表 baseline**（per §Decision 2）+ PostOnly fee 計算 + Reverse-snipe cost trade-off（per §Decision 4）|
| `docs/references/2026-04-04--bybit_api_reference.md` | **Bybit V5 maker/taker fee + rebate tier reference**；BB Sprint 6 IMPL 期 confirm precise threshold |
| V107 (M11 replay_divergence_log per ADR-0038) | **與本 ADR V115 schema dedup**（per OQ-4）；兩表正交並存 |
| `project_hardware_constraints` (PG 4-8GB shared_buffers) | **V115 三表 retention + index 設計受該約束** |

## §二 16 根原則合規確認

| # | 原則 | 是否相容 | 說明 |
|---|---|---|---|
| 1 | 單一寫入口 | ✅ | OrderRouter 是 routing decision 而非 trade 寫入口；submit_intent 仍是 IntentProcessor → Guardian → Rust 唯一路徑 |
| 2 | 讀寫分離 | ✅ | V115 三表 audit log；不寫 live state |
| 3 | AI 輸出 ≠ 命令 | ✅ | OrderRouter 在 Decision Lease 通過後執行 routing；不繞 lease |
| 4 | 策略不繞風控 | ✅ | bounds + LAL 3 protection 雙層 gate；越界 fail-closed |
| 5 | 生存 > 利潤 | ✅ | rebate tier 跌出 emit M3 HEALTH_WARN 是生存紀律（cost edge 是生存基底）|
| 6 | 失敗默認收縮 | ✅ | bounds 越界 fail-closed reject；reverse_snipe 過頻 throttle |
| 7 | 學習 ≠ Live | ✅ | V115 audit log 不寫 live state；trait 計算純讀 |
| 8 | 交易可解釋 | ✅ | V115 Part 1 `route_reason` 對齊；audit「為什麼這 order 走 maker/taker」可 back-trace |
| 9 | 雙重防線 | ✅ | bounds（本地）+ LAL 3 protection（governance）雙層 |
| 11 | Agent 最大自主 | ✅ | Auto-routing 在 bounds 內 Agent 自主；越界走 operator confirm + LAL 3 |
| 13 | cost 感知 | ✅ | **本 ADR 核心**；`maker_fill_rate_30d` 是 cost-edge structural protection |
| 14 | 零外部成本 | ✅ | Bybit + Binance market data 既有訂閱基礎設施；不依賴外部付費服務 |
| 16 | Portfolio > 孤立 trade | ✅ | venue × asset_class 矩陣 + cross_venue_position 是 portfolio thinking 的 routing-level 體現 |

## Cross-References

- **v5.8 §2 M12**：`docs/execution_plan/2026-05-20--execution-plan-v5.8.md:425-457`（本 ADR 對應 module）
- **v5.8 §2 M3 + M7**：`docs/execution_plan/2026-05-20--execution-plan-v5.8.md`（CR-7 dedup contract dispatch chain — maker_fill_rate alert → M3 HEALTH_WARN）
- **ADR-0029**：`docs/adr/0029-market-trade-tape-and-orderbook-l2-storage-policy.md`（trade tape + L2 snapshot policy；本 ADR maker_fill 計算數據源）
- **ADR-0033**：`docs/adr/0033-adr-0006-bybit-binance-amendment.md`（Binance Y2 trading defer；本 ADR Y2 cross-venue routing 對齊）
- **ADR-0030**：`docs/adr/0030-copy-trading-evidence-gated.md`（Copy Trading evidence-gated；本 ADR routing 不影響）
- **ADR-0034**：`docs/adr/0034-decision-lease-layered-approval-lal.md`（LAL 3 越 bounds protection）
- **ADR-0001**：`docs/adr/0001-rust-as-trading-authority.md`（OrderRouter Rust hot path actor）
- **ADR-0005**：`docs/adr/0005-engine-mode-tag-live-demo.md`（V115 `engine_mode` column 對齊）
- **ADR-0010**：`docs/adr/0010-timescale-hypertable-with-guard-migrations.md`（V115 三表 Guard 範式）
- **ADR-0011**：`docs/adr/0011-v-migration-linux-pg-dry-run-mandatory.md`（V115 schema Linux PG dry-run mandatory）
- **ADR-0038**：`docs/adr/0038-m11-continuous-counterfactual-replay-and-liquidations-source.md`（M11 replay V107 與 V115 dedup OQ-4）
- **V094**：`sql/migrations/V094__fills_close_maker_audit.sql`（既有 `close_maker_attempt` + `close_maker_fallback_reason` 範式 baseline）
- **`docs/references/2026-04-04--bybit_api_reference.md`**：Bybit V5 maker/taker fee + rebate tier reference
- **crypto-microstructure-knowledge skill**：rebate tier 對照表 + PostOnly fee 計算 + Reverse-snipe cost trade-off
- **`feedback_micro_profit_fix_intent`**：既有 maker_fill_rate 半成品；本 ADR 升級基線
- **`feedback_v_migration_pg_dry_run.md`**：V### migration PG dry-run mandatory（本 ADR V115 IMPL 階段強制）
- **PA dispatch consolidation report**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md`（CR-14 來源）
- **PM final verdict**：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-21--v58_pm_final_verdict.md`（v5.8 §2 M12 立場確認）
- **V115 schema spec**：pending CR-14 finalize（候選 schema in §Decision 3）

## Sign-off

| Role | Source | Date | Status |
|---|---|---|---|
| Operator | 主會話 PM dispatch via v5.8 §2 M12「Adaptive Order Routing DESIGN initial / IMPL delayed」立場 | 2026-05-21 | 🟡 PROPOSED-pending-commit |
| TW | 本文件起草（v5.8 §2 M12 module ADR 級落地 + BB 5.21 audit maker_fill_rate_30d push back 對齊） | 2026-05-21 | ✅ Drafted |
| BB | Bybit rebate tier precise threshold confirm（OQ-1）+ ToS posture 對齊 ADR-0033 §4.2 | 2026-05-21 | ✅ Drafted (per audit recommendation; precise threshold Sprint 6 IMPL confirm) |
| E5 | Slippage forecast performance review + slicing IMPL（OQ-6 Sprint 7-8 sub-spec）| TBD（Sprint 6+） | 🟡 PENDING |
| FA | Per-strategy reverse-snipe threshold（OQ-2）+ slicing market impact 估算 | TBD（Sprint 6） | 🟡 PENDING |
| QC | maker_fill cold start fallback（OQ-3）+ V115 schema review | TBD（Sprint 1A） | 🟡 PENDING |
| MIT | V115 三表 PK + retention + Guard 範式 review（per ADR-0010 + V094/V095 對齊）| TBD（Sprint 1A） | 🟡 PENDING |
| E1 | OrderRouter trait Sprint 1A interface stub IMPL owner | TBD（Sprint 1A） | 🟡 PENDING |
| PM | CR-14 finalize → promote 至 Accepted；V115 schema commit | TBD（Sprint 1A 結束） | 🟡 PENDING |

---

*OpenClaw / Arcane Equilibrium ADR-0039 — M12 OrderRouter Trait: Maker-Fill-Rate Metric + Adaptive Routing Audit Schema (Proposed-pending-commit; 6 method trait + V115 三表 audit infrastructure)*
