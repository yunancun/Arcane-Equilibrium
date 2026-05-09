# W-AUDIT-8a — Alpha Surface Foundation（Spec Phase）

**Wave 名稱**：W-AUDIT-8a "Alpha Surface Foundation"
**Spec 階段**：Spec Phase（接口契約 + DAG，**不**寫 IMPL 細節）
**起草者**：PA（Project Architect）
**日期**：2026-05-09
**對齊 audit**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_loss_architectural_root_cause_redesign.md` Layer 3.1 + 3.2 + Layer 4 R-1
**讀者**：Operator / PM / E1 / E2 / E4 / QC / MIT
**前置/並行**：W-AUDIT-2 / W-AUDIT-5 純並行；W-AUDIT-6 minimum-only（funding_arb retire + DSR/PBO + Kelly config）並行；AMD-2026-05-09-03 graduated canary 是真 deploy 前置；W-AUDIT-3 fake-live + Decision Lease 不被本 wave 觸碰
**生效範圍**：Rust `openclaw_engine` strategies trait、TickContext、Orchestrator dispatch tracking、Python collector + V### migration（Tier 2/3 panel）；**不**改 GovernanceHub / Decision Lease / Executor 寫入路徑

---

## §1 Wave 範圍 + Goal

### 1.1 North Star

把 `Strategy::on_tick(ctx)` 升級為 `Strategy::on_tick(ctx, surface)`，讓非-TA alpha source（funding curve / OI delta panel / orderflow features / liquidation pulse / event alerts / sentiment panel / regime tag）從「策略自己 buffer」（second-class，每個策略重造輪子）升為 **first-class architectural object**，讓未來孵化非-TA 策略的摩擦從「200 LOC 自維護 panel」降到「`import` + 50 LOC 策略邏輯」。

### 1.2 Wave 範圍邊界

**本 wave 含**：
- Rust `AlphaSurface<'a>` 結構（Tier 1-4 字段定義）+ `AlphaSourceTag` enum
- `Strategy` trait 加 `declared_alpha_sources()` + `on_tick(ctx, surface)` 簽名升級
- `TickContext` 升級加 `alpha_surface_ref: &AlphaSurface<'_>`（Tier 1 wire 進，Tier 2-3 Optional `None` 直到後續 phase）
- 5 既存策略 explicit declare alpha sources（migration only，不改邏輯）
- Orchestrator dispatch tracking metric `alpha_source_dispatched_total{tag=...}`
- Tier 2 panel collector（funding curve / OI delta panel）+ V### migration retention policy
- Tier 3 collector（orderflow stub + liquidation pulse 真接 Bybit `allLiquidation` WS topic）
- Tier 4 wire（EventAlert from Scout `intel_objects`、RegimeTag from existing ATR/Hurst/EwmaVol、SentimentPanel stub）

**本 wave 不含**（明確邊界）：
- 任何具體 alpha source 業務 IMPL（候選 A funding skew / B liquidation cluster / C BTC→Alt lead-lag / D orderbook imbalance）— 這些留給後續 W-AUDIT-8b/c/d
- Strategist 重定義（R-2，留給 W-AUDIT-8e）
- Hypothesis Pipeline first-class object（R-3，留給 W-AUDIT-8f）
- Per-alpha-source Live Promotion Gate（R-4，留給 W-AUDIT-8g）
- 任何對 GovernanceHub / SM-01 / SM-02 / SM-04 / EX-04 / Decision Lease / Authorization 的修改
- 任何對既有 5 策略邏輯的修改（除 trait method 簽名 + alpha source declare）

### 1.3 為什麼這是 Tier-1 leverage

5 策略 7d demo gross **-26.44 USDT**（CLAUDE.md §三 2026-05-08 PA 直查）不是參數問題，是**架構結構性激勵 TA-only 策略**。TickContext 形式上已暴露 `funding_rate` / `index_price` / `open_interest` / `best_bid/ask` raw 值，但**單 symbol、單窗口、無 panel 化** — 寫一個 funding skew spread 策略需要同時看 25 symbols funding curve，當前架構讓策略自己 buffer，摩擦讓任何系統孵化的策略 regress 到 indicator-driven on_tick。

升級 Strategy interface 是改架構激勵：寫 funding skew spread 從「200 LOC 自維護 panel」降到「`surface.funding_curve` → 50 LOC 策略邏輯」。**架構在主動激勵非-TA alpha**，不再只是 TA 高速公路 + 其他泥路。

---

## §2 接口設計（Tier 1-4 Alpha Surface Bundle）

### 2.1 `AlphaSourceTag` enum

聲明性枚舉，給 Strategy 在 ctor 階段表態「我吃哪幾個 alpha source」。Orchestrator 用此做 dispatch tracking 與 promotion gate 對齊。

```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum AlphaSourceTag {
    // Tier 1 — TA / OHLCV (legacy compatible)
    TA1m,
    TA5m,
    // Tier 2 — Cross-asset / cross-section panels
    FundingSkew,        // 25-symbol funding curve cross-section
    Basis,              // perp vs index basis curve
    OIDeltaPanel,       // cross-symbol open interest delta panel
    // Tier 3 — Microstructure
    OrderflowImbalance, // microprice / queue imbalance / large-trade tape
    LiquidationCascade, // Bybit allLiquidation pulse cluster
    // Tier 4 — Information flow
    EventDriven,        // Scout intel_objects → EventAlert
    CrossAsset,         // BTC→Alt lead-lag / cross-pair correlation
    Sentiment,          // SentimentPanel from external feeds (stub-only this wave)
}
```

**設計約束**：
- enum 完整性 = QC must-review — 漏掉某 tag 等於漏掉一條 alpha source 的 governance hook
- enum 變更必經 ADR（添加 / 刪除 / 重命名都觸發 ADR）；W-AUDIT-8a 落地後本 enum 為 SoT
- `Display` + `serde::Serialize` 用 lowercase snake_case（`ta_1m` / `ta_5m` / `funding_skew` ...）— 與 PG schema 對齊

### 2.2 `AlphaSurface<'a>` 結構

```rust
pub struct AlphaSurface<'a> {
    // ── Tier 1 — TA / OHLCV (向後相容；現有 IndicatorSnapshot 升為 surface 子集) ──
    pub indicators: Option<&'a IndicatorSnapshot>,        // 1m kline-derived
    pub indicators_5m: Option<&'a IndicatorSnapshot>,     // 5m kline-derived

    // ── Tier 2 — 跨資產 / 截面（新一等對象） ──
    pub funding_curve: Option<&'a FundingCurveSnapshot>,
    pub basis_curve: Option<&'a BasisCurveSnapshot>,
    pub oi_delta_panel: Option<&'a OIDeltaPanel>,

    // ── Tier 3 — Microstructure（新一等對象） ──
    pub orderflow: Option<&'a OrderflowFeatures>,
    pub liquidation_pulse: Option<&'a LiquidationPulse>,

    // ── Tier 4 — 信息流 ──
    pub event_alerts: &'a [EventAlert],
    pub regime: RegimeTag,
    pub sentiment_panel: Option<&'a SentimentPanel>,
}
```

**生命週期約束**：
- `'a` 與 `TickContext<'a>` 同 lifetime — borrow from `on_tick` scope，避免 deep clone
- Optional `None` = 該 tier 在當前 phase 尚未 wire 或 collector 暫時 stale；strategy **必須** fail-closed 跳過自身 alpha source（不可 fallback 到 TA1m）

### 2.3 Tier 子結構契約（spec 級，不寫 IMPL）

#### Tier 1 — `IndicatorSnapshot`（既有，無變化）
- 來源：`KlineManager` 1m / 5m → `IndicatorEngine`
- Refresh：每 tick
- Staleness rule：絕對年齡 ≤ 90s（current `TickContext.indicators` 規則延用）
- Producer：Rust `feature_collector` + `IndicatorEngine`
- Consumer：本 wave 5 既存策略全部走此

#### Tier 2.1 — `FundingCurveSnapshot`
- 用途：cross-symbol funding rate panel（25 symbols 同時看）— 支撐 funding skew spread / basis arb
- 字段：`symbols: Vec<String>`、`funding_rates_bps: Vec<f64>`、`next_funding_ms: Vec<i64>`、`snapshot_ts_ms: i64`、`source_tier: SourceTier`
- 來源：Bybit `tickers` WS（既有）+ Python collector aggregator → PG 表 `market.funding_rates_panel`（V### migration 新增）
- Refresh 頻率：≥ 1 / 30s（Bybit funding 8h period，過細無意義；30s 足夠 capture cross-section dispersion）
- Staleness rule：
  - WARN：snapshot_ts > 60s
  - FAIL：snapshot_ts > 300s → `surface.funding_curve = None`
- Retention：14 天（V### migration 帶 retention policy；MIT must-review）

#### Tier 2.2 — `BasisCurveSnapshot`（**`requires_spot_capability: true`** — BB v3 NEW-8）
- 用途：perp vs index basis curve cross-section
- 字段：`symbols`、`basis_pct`、`perp_price`、`index_price`、`snapshot_ts_ms`、`source_tier`
- 來源：Bybit `tickers` WS（既有 `funding_arb` 用 single symbol）+ aggregator
- Refresh / Staleness：同 §2.3 Tier 2.1
- Retention：14 天
- **Execution 邊界（明文）**：
  - **basis = observation-only signal until mainnet**
  - Bybit demo 環境**不支援 spot lending execution**（與 funding_arb v2 retire 同因，ADR-0018）；perp 與 spot 之間真 cash-and-carry 在 demo 不可行
  - 吃 `Basis` tag 的策略 ctor 必須 declare `requires_spot_capability: true`
  - 在 demo / live_demo 環境（無 spot account）下，吃 `Basis` 的策略產生的 `StrategyAction` **必須 fail-closed**，不可進 IntentProcessor → IntentRouter 應有 `requires_spot_capability && !env_has_spot` 檢查
  - 只有 mainnet + 真實 spot account 接通 + operator 顯式 sign-off 後才解封 execution path
  - **反模式警示**：若忽略此邊界 → demo 累積 edge sample 全 paper-grade（同 funding_arb v2 demo n=13 -36.76 bps），graduate live 時必死

#### Tier 2.3 — `OIDeltaPanel`
- 用途：cross-symbol open interest delta（5m / 15m / 1h 三檔）
- 字段：`symbols`、`oi_delta_5m_pct`、`oi_delta_15m_pct`、`oi_delta_1h_pct`、`oi_abs`、`snapshot_ts_ms`、`source_tier`
- 來源：Bybit `tickers` WS open_interest field + Python writer 寫 `market.open_interest`（既有 `bb_breakout` 自己 buffer）→ aggregator delta
- Refresh / Staleness：同 §2.3 Tier 2.1
- Retention：14 天

#### Tier 3.1 — `OrderflowFeatures`
- 用途：per-symbol microstructure（microprice / queue imbalance / large-trade tape rolling stats）
- 字段：`symbol`、`microprice`、`queue_imbalance`、`large_trade_count_60s`、`large_trade_volume_60s`、`snapshot_ts_ms`、`source_tier`
- 來源（Bybit V5 真實 levels 對齊；BB v3 NEW-5）：
  - **Bybit V5 WS linear orderbook 真實 depth levels = `1 / 50 / 200 / 1000`，沒有 L25**
  - W-AUDIT-8a 預設使用 `orderbook.50.{symbol}`（已預設訂閱），bids5/asks5 已由 parser extract
  - 若 W-AUDIT-8d 真 IMPL 需要 deeper book（large resting order / queue depth tail），改 `orderbook.200.{symbol}`
  - **禁止**任何「L25」字眼進 spec / IMPL / migration / healthcheck（Bybit endpoint validation 會打回）
  - W-AUDIT-8a Phase C **stub mock** + dummy data 為主，真接留給 W-AUDIT-8d
- Refresh / Staleness：tick-level（best-effort），WARN > 5s，FAIL > 30s
- Retention：N/A（Tier 3 stub 暫不寫 PG）

#### Tier 3.2 — `LiquidationPulse`（**`requires_revival: true`** — BB v3 NEW-6）
- 用途：liquidation cascade detection（cross-symbol）
- 字段：`recent_events: Vec<LiquidationEvent>`（rolling 60s 窗口）、`cluster_score: f64`、`dominant_side: LiquidationSide`、`snapshot_ts_ms`
- **狀態 dormant — 復活前置條件**：
  - OpenClaw 於 **2026-04-06 已刪除** `allLiquidation` WS handler（字典手冊 `docs/references/2026-04-04--bybit_api_reference.md` line 990 證明）
  - `market.liquidations` 表 reserved 保留，但 R-1 IMPL 必須**先付 +1 sprint 重接 WS handler + 重啟 writer**
  - 復活前 surface field 永遠 `None`，**禁止 stub mock 數據**（避免「假 alpha source dispatched」污染 dispatch tracking metric）
  - 策略 ctor declare `LiquidationCascade` 的，在 handler 復活前 strategy `on_tick` 必須觀測到 `surface.liquidation_pulse.is_none()` → fail-closed 跳過自身 alpha source
- 來源（復活後）：Bybit `allLiquidation` WS topic + Python `liquidation_writer.py` 寫 `market.liquidations` PG 表（V### migration 新增）
- Refresh / Staleness（復活後）：tick-level，WARN > 10s，FAIL > 60s
- Retention：30 天（liquidation cascade 樣本稀疏 + 高價值，可獨立保留更久）
- **Sprint 排程影響**：W-AUDIT-8a Phase C 原規劃內含 liquidation 真接，現需拆兩段 — Phase C 先 dormant + schema reserved；Phase C+1 sprint（單獨 sub-phase）做 WS handler revert + writer 重啟 + 真接

#### Tier 4.1 — `EventAlert`
- 用途：Scout `intel_objects` 真實 wire（當前 Scout 跑著但 Strategist 不真依賴）
- 字段：`event_id: ScoutEventId`、`category: EventCategory`、`affected_symbols: Vec<String>`、`severity: f64`、`emitted_ms: i64`、`expiry_ms: i64`
- 來源：Python `scout_agent` IntelObject store → IPC slot → Rust `&[EventAlert]` borrow
- Refresh：event-driven（push）；Strategy on_tick 看 active（now < expiry_ms）events
- Staleness rule：N/A（事件本身有 expiry_ms）

#### Tier 4.2 — `RegimeTag`
- 用途：market regime（trending_up / trending_down / ranging / volatile / unknown）
- 字段：enum + numeric confidence
- 來源：W-AUDIT-8a 用既有 ATR / Hurst / EwmaVol 組合計算（**不新增 ML 模型**；QC 候選 E）
- Refresh：每 tick 重算
- Staleness rule：N/A（無時間維度，仅 confidence）

#### Tier 4.3 — `SentimentPanel`
- 用途：external sentiment feed（社群 / 新聞）— W-AUDIT-8a **僅 stub**，真接留給後續 wave
- 字段：`per_symbol_score: HashMap<String, f64>`、`snapshot_ts_ms`、`source_tier`
- 本 wave 永遠 `None`

### 2.4 Strategy trait 升級

```rust
pub trait Strategy: Send {
    fn name(&self) -> &str;
    fn is_active(&self) -> bool;
    fn set_active(&mut self, active: bool);

    // ── 新增：alpha source declaration ──
    fn declared_alpha_sources(&self) -> &[AlphaSourceTag];

    // ── 升級：on_tick 簽名加 surface ref ──
    fn on_tick(
        &mut self,
        ctx: &TickContext<'_>,
        surface: &AlphaSurface<'_>,
    ) -> Vec<StrategyAction>;

    // 其餘 callback（on_rejection / on_fill / on_external_close / on_close_confirmed
    //   / on_close_skipped / on_post_only_rejected / update_params_json /
    //   get_params_json / param_ranges_json / conf_scale / set_conf_scale）保持不變
}
```

**向後相容默認**：
- `declared_alpha_sources()` 無 default impl — 5 既存策略 must explicit declare（Phase A 強制 migration）
- `on_tick` 簽名升級不向後相容 — Phase A E2E test 必擋舊簽名 callsite

### 2.5 內部 dispatch tracking metric

新增 Prometheus / `feature_collector` 統計：

```
alpha_source_dispatched_total{tag="<lowercase>", strategy="<strategy_name>"}: u64
alpha_source_unavailable_total{tag="<lowercase>", strategy="<strategy_name>"}: u64
```

每次 `Strategy::on_tick` 時：
1. 對 strategy declared sources 內每個 tag，檢查 `surface.<tag>` 是否 `Some` → +1 dispatched
2. 對 `None` → +1 unavailable
3. Orchestrator 每 5 min export 一次 + 寫 PG `observability.alpha_source_health`（V### migration）

**用途**：未來 promotion gate / per-alpha-source budget 對齊；本 wave 僅 dispatch tracking 不做 budget。

---

## §3 Wave 8a 具體 Deliverable（4 Phase × 1 Sprint）

### Phase A — Foundation Schema（Sprint N+0）

**Goal**：升 trait + AlphaSurface 結構 + 5 策略 explicit declare，**0 行為變化**。

**Deliverable**：
1. 新增 Rust mod `openclaw_core::alpha_surface`：`AlphaSurface<'a>` + `AlphaSourceTag` enum + Tier 子結構 stub（field-only，無 collector）
2. `Strategy` trait 改簽名：加 `declared_alpha_sources()` + `on_tick(ctx, surface)`
3. 5 既存策略 explicit declare（`bb_breakout` / `bb_reversion` / `ma_crossover` / `grid_trading` / `funding_arb`）：
   - `bb_breakout`：`[TA1m, TA5m, OIDeltaPanel]`（既有 OI delta 自己 buffer，本 phase 不改邏輯，只 declare）
   - `bb_reversion`：`[TA1m]`
   - `ma_crossover`：`[TA1m]`
   - `grid_trading`：`[TA1m]`（best_bid/ask 屬 TickContext 不屬 AlphaSurface）
   - `funding_arb`：`[FundingSkew, Basis]`（標記 retired per ADR-0018，但保留聲明以便 retire 後 dispatch 可審計）
4. `TickContext<'a>` 升級加 `alpha_surface_ref: &'a AlphaSurface<'a>`（Tier 1 wire 進，Tier 2-4 全 `None`）
5. Orchestrator on_tick callsite 升級：build `AlphaSurface` → pass to `Strategy::on_tick`
6. Dispatch tracking metric `alpha_source_dispatched_total` + `alpha_source_unavailable_total` IMPL
7. E2E baseline binary diff test：5 策略走 `AlphaSurface` 之後產生的 `Vec<StrategyAction>` **byte-identical** to pre-migration baseline（用 fixed seed replay run）

**Owner chain**：`@PA spec sign-off → @E1 IMPL → @E2 review → @E4 regression test → PM sign-off`
**Risk**：5 策略 callsite migration 可能漏邊角（on_external_close 等 callback）；E4 regression 必跑 100% strategy callback coverage
**Sprint estimate**：~10 person-day

### Phase B — Tier 2 Panel Wiring（Sprint N+1）

**Goal**：funding_curve + oi_delta_panel collector 寫 PG，AlphaSurface 真實 populate；5 策略 backward compat（不消費）。

**Deliverable**：
1. V### migration（兩條，可並行）：
   - V0xx: `market.funding_rates_panel`（schema + retention 14d + Guard A/B/C + idempotency）
   - V0xx: `market.oi_delta_panel`（schema + retention 14d + Guard A/B/C + idempotency）
2. Python collector：`tools/alpha_surface/funding_curve_collector.py`（從 Bybit `tickers` WS / 既有 `market.funding_rates` 表 aggregate → 寫 panel 表）
3. Python collector：`tools/alpha_surface/oi_delta_collector.py`（從 `market.open_interest` aggregate 5m/15m/1h delta → 寫 panel 表）
4. Rust `tick_pipeline` 啟動時新增 `FundingCurveProvider` + `OIDeltaProvider` IPC slot（從 PG read，每 30s refresh）
5. `AlphaSurface` Tier 2 字段在 `TickContext` 構造時 populate（freshness check pass → `Some`，否則 `None`）
6. healthcheck `[新-funding_curve_freshness]` + `[新-oi_delta_panel_freshness]` 加入 `helper_scripts/db/passive_wait_healthcheck.py`
7. 5 策略不消費 Tier 2 字段（保持 backward compat）

**Owner chain**：`@PA spec → @MIT review V### migration（強制）→ @E1 collector IMPL + Rust IPC slot → @E2 review → @E4 regression`
**Risk**：collector 寫 PG 過大 → V### migration retention policy 必過 MIT review；30s refresh 對 PG 負荷低（≤ 50 rows/cycle × 25 symbols × 2 panels = 2500 rows/h）
**Sprint estimate**：~10 person-day

### Phase C — Tier 3 Microstructure + Liquidation（Sprint N+2）

**Goal**：liquidation_pulse 真接 Bybit `allLiquidation` WS；orderflow stub 接 mock。

**Deliverable**：
1. V### migration：`market.liquidations` + retention 30d + Guard A/B/C
2. Rust `ws_client/parsers.rs` 加 `allLiquidation` topic parser（既有 file 已含 liquidation 註釋，確認 parser 完整）
3. Rust IPC slot `LiquidationPulseProvider`（rolling 60s 窗口 buffer）
4. Python `liquidation_writer.py`（將 `allLiquidation` event 落 PG）
5. `AlphaSurface.liquidation_pulse` populate（from in-memory rolling buffer，不從 PG read 避免延遲）
6. `OrderflowFeatures` IPC slot stub：mock implementation（microprice = (bid+ask)/2，queue_imbalance = 0.5，large_trade_count = 0），**明確標 stub** — 真接留給 W-AUDIT-8d
7. healthcheck `[新-liquidation_pulse_freshness]`：24h ≥ 100 events 證 WS topic 真接

**Owner chain**：`@PA spec → @MIT review V### migration → @BB review Bybit WS topic 對齊（強制） → @E1 IMPL → @E2 review → @E4 regression`
**Risk**：`allLiquidation` topic Bybit 可能對 IP rate-limit；BB must-review topic spec
**Sprint estimate**：~10 person-day

### Phase D — Tier 4 + Integration（Sprint N+3）

**Goal**：5 策略 onTick callsite 全用 surface（即使僅 Tier 1）；EventAlert + RegimeTag wire；E2E test 5 策略走全部 surface tier。

**Deliverable**：
1. `EventAlert` 從 Scout `intel_objects` 真實 wire：Python `scout_agent` 寫 IPC slot → Rust `EventAlertSlot` borrow → `&[EventAlert]` 傳入 surface
2. `RegimeTag` 從現有 ATR / Hurst / EwmaVol 計算（`combine_layer.rs` 已有部分組合）：定義 `RegimeClassifier` → AlphaSurface populate
3. `SentimentPanel` 永遠 stub `None`（W-AUDIT-8a 不接外部 feed）
4. 5 策略 audit pass：每個策略 explicit 在 on_tick 用 `surface.indicators` / `surface.indicators_5m` 取代既有 `ctx.indicators` / `ctx.indicators_5m`（純 mechanical migration，無邏輯改動）
5. E2E migration test：跑 7d replay session（用 REF-20 replay），證 5 策略全走 surface 後**0 行為變化**
6. `alpha_source_dispatched_total` metric 健康（每 5 min 寫 PG，跑 7d 看 dispatch 分佈）
7. healthcheck `[新-alpha_source_dispatch_health]`：24h dispatch counter > 0 for declared tags

**Owner chain**：`@PA → @E1 IMPL → @E2 review → @E4 regression（含 7d replay E2E）→ PM sign-off`
**Risk**：Scout IntelObject IPC schema 可能與 Rust `EventAlert` mismatch；CC must-review IPC schema
**Sprint estimate**：~10 person-day

### 4 Phase 並行 / 串行關係 DAG

```
Phase A ──┬─→ Phase B ──┐
          │             ├─→ Phase D
          └─→ Phase C ──┘
```

- Phase A 必先（所有後續 phase 依賴 trait 升級 + AlphaSurface struct）
- Phase B 與 Phase C 可並行（不同 collector / 不同 PG 表 / 不同 IPC slot）
- Phase D 必待 Phase B + C 完成

---

## §4 與既有 wave 的關係

| Wave | 衝突 / 並行 / 依賴 | 處理方式 |
|---|---|---|
| W-AUDIT-1 docs sync | 無衝突 | 並行；本 spec 落地後 W-AUDIT-1 docs/README 加 entry，CONTEXT.md glossary 加 `AlphaSurface` / `AlphaSourceTag` 條目 |
| W-AUDIT-2 security IMPL | 無衝突 | 並行 |
| W-AUDIT-3 fake-live + Decision Lease | 無衝突，**正交** | 並行；本 wave 不觸碰 Executor / Decision Lease 寫入路徑 |
| W-AUDIT-4 ML 基座 | **未來併入 R-3 Hypothesis Pipeline**（後續 wave） | 本 wave 不解 W-AUDIT-4；MLDE feature_baselines / outcome backfill 仍走 W-AUDIT-4 既有計劃 |
| W-AUDIT-5 性能/結構 | 無衝突 | 並行；本 wave 新加 Rust struct + LOC，注意 `tick_pipeline/mod.rs` 已 800+ 行，W-AUDIT-5 須延後或並行 split |
| W-AUDIT-6 策略 + 量化 promotion gate | **重要邊界**：W-AUDIT-6 砍剩 minimum（funding_arb retire + DSR/PBO + Kelly config）後並行 | W-AUDIT-6 不重寫 ma / bb_breakout，留帶寬給 8a |
| W-AUDIT-7 GUI/AI/Layer2 | 無衝突 | 並行；Layer2 manual + supervisor-only 維持 ADR-0020 |
| AMD-2026-05-09-03 graduated canary | **真 deploy 前置** | 8a Phase A-D 完成後不能直接進 demo；必走 graduated canary（8a Phase D `--keep-auth` deploy paper → demo → live_demo） |
| W-C / MAG-082 / 083 / 084 | 無衝突 | 並行；本 wave 不影響 lease 路徑 |
| LG-1..LG-5 | **正交** | 8a 不替代 LG baseline；future R-4 per-alpha-source budget 仍依賴 LG-X 1-5 baseline |

### Reframe 策略 audit 報告 R-3 / R-4 / R-5

- **R-1（本 wave 8a）**：Alpha Surface Foundation
- R-2（後續 wave 8e）：Strategist scope reframe + AlphaSourceRegistry
- R-3（後續 wave 8f）：Hypothesis Pipeline first-class object（**併入 W-AUDIT-4 重新設計**）
- R-4（後續 wave 8g）：Per-alpha-source Live Promotion Gate
- R-5（併入 W-AUDIT-1 升級）：Spec-as-Code + Module Lifecycle SM

本 spec 不展開 R-2..R-5。

---

## §5 IMPL Risk + Fallback

### Risk-1：5 策略 migration regression

**症狀**：trait 簽名升級後 5 策略 byte-output 改變（哪怕 1 bit）即 reject
**Detection**：Phase A E2E baseline binary diff（fixed-seed replay 跑 1h paper session，stdout fingerprint 完全相同）
**Fallback**：若 byte-diff 不為零，rollback Phase A patch，PA 重設計 dispatch 邏輯

### Risk-2：collector 寫 PG 過大

**症狀**：funding_curve / oi_delta_panel / liquidations 表寫入率超預期 → PG 4-8 GB 限額溢
**Mitigation**：
- V### migration 強制 retention policy（funding/oi 14d、liquidations 30d）
- MIT must-review 每條 V### migration 的 row-rate 估算
**Fallback**：如 retention 不夠，降 refresh 頻率（30s → 60s）

### Risk-3：TickContext lifetime annotation 複雜

**症狀**：`AlphaSurface<'a>` + `TickContext<'a>` 雙層 lifetime borrow 引發編譯困難
**Mitigation**：
- 採 `&'a` 單層 borrow，避免 deep clone
- AlphaSurface 構造在 `tick_pipeline.on_tick` scope 內，與 TickContext 共 lifetime
**Fallback**：如 borrow checker 太麻煩，AlphaSurface 改為 `Cow<'a, T>` 或 `Arc<T>`（trade-off 一次 Arc clone 換編譯通過）

### Risk-4：Scout IntelObject IPC schema mismatch

**症狀**：Phase D wire EventAlert 時 Python `IntelObject` schema 與 Rust `EventAlert` 字段對不上
**Mitigation**：CC must-review IPC schema；Phase D 開頭先 spec EventAlert 字段 → 對齊 Python `intel_objects` → 再 IMPL
**Fallback**：Phase D `EventAlert` 改為 `&[]` empty slice 直到 Scout schema 對齊

### Risk-5：Bybit `allLiquidation` WS topic rate-limit

**症狀**：subscribe `allLiquidation` 觸 Bybit IP rate-limit
**Mitigation**：BB must-review topic spec；如 rate-limit，降為 per-symbol liquidation 訂閱
**Fallback**：Phase C liquidation_pulse 從 PG 讀 historical（非 real-time），先驗 schema 後再實時

### Risk-6：Phase A 完成後 hold 過久

**Mitigation**：Phase A 完成後可 hold N sprint，Phase B-D 漸進；單 Phase A 即可達成 R-1 80% 價值（trait 升級 + AlphaSurface struct + 5 策略 declare 後，未來孵化新策略已可用 surface ref，即使 Tier 2-4 暫無 collector 也只是 None）

---

## §6 Sprint Resource + Owner

### 6.1 Sprint estimate

| Phase | Person-day | Owner |
|---|---:|---|
| A — Foundation Schema | ~10 | E1 主 IMPL |
| B — Tier 2 panel | ~10 | E1（collector）+ MIT（V###） |
| C — Tier 3 micro + liquidation | ~10 | E1 + BB（Bybit topic）+ MIT（V###） |
| D — Tier 4 + integration | ~10 | E1 + CC（Scout IPC schema） |
| **Total** | **~40** | 4 sprint × 1 active dev |

### 6.2 Mandatory review chain

| Phase | Mandatory reviewer |
|---|---|
| A | `@QC` enum 完整性 + AlphaSurface struct；`@E2` Strategy trait 升級；`@E4` E2E baseline regression |
| B | `@MIT` V### migration（funding_rates_panel + oi_delta_panel schema/retention）；`@E2` collector code；`@E4` |
| C | `@BB` Bybit WS topic spec；`@MIT` V### migration（liquidations）；`@E2`；`@E4` |
| D | `@CC` Scout IntelObject IPC schema；`@E2`；`@E4` 7d replay E2E |
| 全 wave | `@QC` AlphaSourceTag enum SoT；`@PA` 接口 SoT；`@PM` Sign-off |

### 6.3 不涉

- `@E1a`：本 wave 無 GUI 改動 — 不涉
- `@E5`：本 wave 為新接口設計，無優化任務 — Phase D 完成後可選評估
- `@FA`：本 wave 為 spec 落地，FA 已 sign 過 audit 報告 R-1 — Phase D 完成後 FA 可評估後續 R-2 接續
- Layer 2 cloud：本 wave 不涉 — ADR-0020 不變

---

## §7 Acceptance Criteria

### 7.1 Phase A acceptance

- 5 策略全部 `declared_alpha_sources()` 返回非空 slice
- `Strategy::on_tick(ctx, surface)` 簽名落地，0 callsite 用舊簽名
- E2E baseline binary diff test PASS：5 策略走 surface 之後 fixed-seed replay 1h paper session 的 stdout fingerprint **byte-identical** to pre-migration baseline
- Orchestrator dispatch tracking 寫 `observability.alpha_source_health`，Phase A end metric `alpha_source_dispatched_total{tag="ta_1m"} > 0`
- 5 策略所有 callback（`on_rejection` / `on_fill` / `on_external_close` / `on_close_confirmed` / `on_close_skipped` / `on_post_only_rejected`）coverage = 100%

### 7.2 Phase B acceptance

- V### migration `market.funding_rates_panel` + `market.oi_delta_panel` 落地，retention 14d 已驗
- funding_curve_collector / oi_delta_collector 各寫 PG ≥ 1000 rows / day
- `TickContext.alpha_surface.funding_curve.is_some()` ratio ≥ 90%（24h 觀察）
- `TickContext.alpha_surface.oi_delta_panel.is_some()` ratio ≥ 90%
- Freshness < 5 min for both panels
- healthcheck `[新-funding_curve_freshness]` + `[新-oi_delta_panel_freshness]` PASS
- 5 策略 backward compat 0 行為變化（同 7.1 byte-diff test）

### 7.3 Phase C acceptance

- V### migration `market.liquidations` 落地，retention 30d 已驗
- Bybit `allLiquidation` WS topic 訂閱穩定（24h 0 rate-limit error）
- `liquidation_writer.py` 24h ≥ 100 events 落 PG
- `TickContext.alpha_surface.liquidation_pulse.is_some()` ratio ≥ 70%（liquidation 本就稀疏）
- `OrderflowFeatures` stub `is_some() = true`（永遠 mock，不 None）
- healthcheck `[新-liquidation_pulse_freshness]` PASS

### 7.4 Phase D acceptance

- 5 策略 on_tick callsite **全用** `surface.indicators` / `surface.indicators_5m`（grep 驗無 `ctx.indicators` 直接 access）
- `surface.event_alerts.len() > 0` 在 Scout 觸發事件時被 strategy 觀測（即使無消費）
- `surface.regime != RegimeTag::Unknown` 在正常 tick 下 ≥ 80%
- `alpha_source_dispatched_total` 健康：5 策略全部 declared tag 在 24h 內 dispatched_total > 0
- 7d replay E2E PASS：5 策略走全 surface 後與 Phase A baseline 0 行為變化

### 7.5 整 wave acceptance（Phase D 結束）

- DSR/PBO 在 5 策略 + 1 個新 alpha source（候選 C BTC→Alt 或 A funding skew）能跑完一輪 demo evidence accumulation（不要求 graduate）
- AlphaSurface API 文檔（`docs/architecture/2026-XX-XX--alpha_surface_api.md`）落地
- ADR 新增（規範 `AlphaSourceTag` enum 為 SoT + 變更必經 ADR）
- CLAUDE.md §五 reframe 完成（見 §8）
- TODO.md 新加 W-AUDIT-8a block + 4 phase 進度

---

## §8 落地 Side Effect（對既有文檔/治理的影響）

### 8.1 CLAUDE.md §五 架構總覽 reframe

**舊**（line 174）：`[策略工具包]    KlineManager → IndicatorEngine → SignalEngine → 5 策略 → Orchestrator`

**新**：`[策略工具包]    KlineManager → IndicatorEngine → AlphaSurface (TA + Funding/OI/Orderflow/Event/Regime) → SignalEngine → 5 策略 → Orchestrator`

舊 framing 歸檔至 `docs/archive/2026-05-09--claude_md_section5_pre_alpha_surface.md`。

### 8.2 CLAUDE.md §三 加入 W-AUDIT-8a active 行

§三 `Active Blockers` 表加 `W-AUDIT-8a` 一行（INACTIVE → ACTIVE 隨 Phase A 啟動切換）。

### 8.3 TODO.md Dispatch Order

加新 row（rank ≥ 14）：

```
| 14+ | `W-AUDIT-8a` Alpha Surface Foundation | PA → E1 → E2 → E4 → MIT/QC/CC/BB → PM | SPEC PHASE 2026-05-09 / Phase A target Sprint N+0 | Phase A trait + 5 策略 declare → Phase B Tier 2 panel → Phase C Tier 3 micro + liquidation → Phase D Tier 4 + integration; 7d replay E2E + DSR/PBO 1 alpha source 跑通。 |
```

### 8.4 ADR 新增（後續 wave 落地時）

- ADR 規範 `AlphaSourceTag` enum SoT + 變更治理路徑
- ADR 規範 AlphaSurface tier 構造責任邊界（Rust 寫；Python collector 餵 PG；Rust IPC slot read）

### 8.5 PA memory 更新

W-AUDIT-8a spec 落地後 PA memory 加：
- 教訓：spec phase 不寫 IMPL，只寫接口契約 + DAG，避免 overpromise
- 經驗：alpha source registry 設計時 enum SoT 比 string-based tag 安全（Rust enum exhaustive match 可 catch 漏 tag）

---

## §9 後續 Wave 接續路線

| Wave | 預期內容 | Sprint |
|---|---|---|
| W-AUDIT-8b | 候選 A funding skew spread 策略 IMPL（用 Tier 2 panel） | N+4 |
| W-AUDIT-8c | 候選 C BTC→Alt lead-lag 策略 IMPL（用 Tier 4 cross-asset） | N+5 |
| W-AUDIT-8d | 候選 D orderbook imbalance 真接 + Tier 3 真 IMPL | N+6 |
| W-AUDIT-8e | R-2 Strategist scope reframe + AlphaSourceRegistry | N+5 並行 |
| W-AUDIT-8f | R-3 Hypothesis Pipeline first-class object + W-AUDIT-4 重新設計 | N+6 |
| W-AUDIT-8g | R-4 Per-alpha-source Live Promotion Gate | N+7 |
| First per-alpha-source supervised live | 第一個 alpha source 拿到 budget slice 進 supervised live | N+8 |

W-AUDIT-8a 是 8b/c/d/e 的 hard prerequisite。

---

## §10 PM 接收後動作

PM 拿到本 spec 後：
1. 與 operator 確認 Sprint N+0 起始時點（與 W-AUDIT-2 / -5 並行還是 sequential）
2. 派 `@E1` Phase A IMPL（並行派 `@QC` enum review）
3. Phase A 完成後 sign-off → Phase B/C 並行派發
4. Phase D 完成後 PM Sign-off + 報告歸檔 → 進 W-AUDIT-8b/c/d 候選 alpha source 孵化

---

## §11 結語

W-AUDIT-8a 不是「修 5 個策略」也不是「加新策略」 — 是把架構從**TA-only 高速公路**升級為**多 alpha source 並行 highway 系統**。

5 策略 demo gross -26.44 USDT 不是參數 / 訊號質量問題，是**架構結構性激勵 TA-only**。本 wave 是 R-1 的 spec 落地，把激勵改成**寫 funding skew spread / orderflow imbalance / liquidation cascade 策略的成本與寫 TA 策略的成本同階**。

如果 W-AUDIT-8a 成功，後續 8b/c/d 才有意義；如果 8a 失敗（接口設計被打回 / Phase A E2E byte-diff 不過 / lifetime 編譯爆炸），後續所有 alpha 孵化都是 nail-to-board。

`PA DESIGN DONE: report path: srv/docs/execution_plan/2026-05-09--w_audit_8a_alpha_surface_foundation_spec.md`
