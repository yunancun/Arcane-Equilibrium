# W-AUDIT-8a Phase B Tier 2 Panel Collector Spec — Sprint N+1 W1 PA Spec Phase v1.1 (WS-first revision)

**Author**: PA (project architect)
**Date**: 2026-05-10
**Phase**: W1 Spec phase Day 1-2 — v1.1 BB WS-first revision；D+1 PA + BB joint sign-off 直接 dispatch W1 IMPL（無需再走 D+1 PA edit + BB integrate cycle）
**Scope**: Sprint N+1 W1 W-AUDIT-8a Phase B Tier 2 panel collector — funding_curve aggregator (B-1) + oi_delta_panel aggregator (B-2) + AlphaSurface consumer 驗收 (B-4)。Spec 拍板後直接派 W1 IMPL E1 sub-agent；D+5-D+6 land + E2/E4 review。
**Reference dispatch**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--sprint_n1_dispatch_draft.md` §3.1 W1
**Reference trait coord**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--alpha_surface_trait_final_shape_w1_w2_coord.md`
**Reference trait skeleton commit**: HEAD `c9fb0b8f` (PA D+0 land — `FundingCurveSnapshot` + `OIDeltaPanel` typedef + `AlphaSurface.{funding_curve,oi_delta_panel}` field + slot insertion anchors)
**Reference alpha surface**: `srv/docs/execution_plan/2026-05-09--w_audit_8a_alpha_surface_foundation_spec.md` §2.3 Tier 2.1 / 2.3
**Reference BB rate budget**: `srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-10--w1_w2_bybit_v5_rate_budget_review.md` §6 HIGH push back（採納 → v1.1 WS-first revision）
**Reference WS code**:
- `srv/rust/openclaw_engine/src/main_ws.rs:47-66` — `enable_extended_ws=true` 預設訂閱 `tickers.{sym}` 25 sym
- `srv/rust/openclaw_engine/src/multi_interval_topics.rs:128-147` — `full_subscription_list()` 含 `ticker_topic()`
- `srv/rust/openclaw_engine/src/ws_client/parsers.rs:190-267` — `parse_ticker_item()` 已 extract `fundingRate` + `openInterest`
- `srv/rust/openclaw_engine/src/ws_client/dispatch.rs:111-114` — `topic.starts_with("tickers.")` route to parser
- `srv/rust/openclaw_types/src/price.rs:30-89` — `PriceEvent` 含 `funding_rate: Option<f64>` + `open_interest: Option<f64>`（**`next_funding_ms` 缺，W1 IMPL 必加**）

---

## Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| v1 | 2026-05-10 | PA | Initial draft — REST polling pattern (25 req/min funding + 75 req/min OI = 100 req/min, 16.7% production budget) |
| **v1.1** | **2026-05-10** | **PA** | **BB HIGH push back 採納 → WS-first pattern**。Producer 從 Python REST writer 切換為 Rust WS aggregator（既有 `tickers` topic broadcast `fundingRate` + `openInterest`，無需新 REST polling）。**真實增量 0 req/s ongoing**，僅 cold-start backfill ~25 req（OI history）。Python writer file 全部 deprecate；Rust 端 `panel_aggregator.rs` 訂閱 event_rx clone 直寫 PG + slot 雙寫。bb_breakout consumer 邏輯不變。WS reconnect gap fill 由既有 RE-2 supervisor 處理 + cold-start backfill 重跑。 |

---

## §1 Background + Scope

### 1.1 Why W1 Phase B now

W-AUDIT-8a Phase A 已 land 全 4 Tier struct typedef + `Strategy::on_tick(ctx, surface)` 接口升級（HEAD `b6ed4975`）。Phase A 階段 `AlphaSurface.funding_curve` / `AlphaSurface.oi_delta_panel` 永遠 `None`（trait 預留 field 但 caller 不 wire）。bb_breakout 已 declare `OiDeltaPanel` tag (`mod.rs:295-300`) 但 silent fallback（surface.oi_delta_panel = None → skip）。

W1 Phase B 的目標：把 `funding_curve` + `oi_delta_panel` 從 stub typedef 升級為**真實 wire panel**。

**v1.1 WS-first design**：Producer = **Rust 端 `panel_aggregator.rs`** 訂閱既有 WS event stream clone（`tickers.{sym}` topic 已預設訂閱 25 sym），filter `Ticker` event variant，60s 一個視窗 flush 一批 `panel.funding_rates_panel` / `panel.oi_delta_panel`，**同時**寫 Rust slot（hot path read）+ PG（audit / ML training data / healthcheck source）。Consumer = `step_4_5_dispatch` 直接讀 slot 構造 `AlphaSurface` borrow → Strategy `on_tick` 真實消費。**REST 僅 cold-start backfill**（OI 5m/15m/1h history; funding 因 8h cycle 不需）。

**為什麼 WS-first 是更好設計**（採納 BB §6 HIGH push back）：
- **Rate budget**：v1 REST polling 100 req/min（16.7% Bybit production budget）；v1.1 ongoing **0 req/s**（WS broadcast 無 REST cost），cold-start backfill 25 req 1 batch ~0.21s
- **Latency**：v1 polling 60s grain；v1.1 WS push 即時（每 tickers update 即進 aggregator buffer）
- **既有資源利用**：`enable_extended_ws=true` 預設 + `parsers.rs:225-263` 已 extract funding_rate + open_interest，**v1.1 reuse 既有 0 額外 connection cost**
- **架構一致**：market data ingestion 全在 Rust（既有 `kline.1` / `publicTrade` / `orderbook.50` writers），panel collector 不應該破例走 Python REST polling

bb_breakout 在 W1 land 後**真實 consume `OiDeltaPanel`**；OI panel unavailable 時 fail-closed 寫 `evaluation_outcome='oi_panel_unavailable'` 入 `learning.decision_features_evaluations`（V082），**不再 silent dormant**。對齊 P1-BB-BREAKOUT-FAIL-CLOSED-1 (dispatch v3.3 §3.5)。

### 1.2 W1 Scope (v1.1 WS-first)

| 子任務 | Owner E1 | 範圍 |
|---|---|---|
| **B-1** | E1-α | Rust `panel_aggregator::funding_curve_aggregator` (新) + `PriceEvent.next_funding_ms: Option<i64>` (新 field on `openclaw_types/src/price.rs`) + `parsers.rs` extract `nextFundingTime` + V085 + Rust `FundingCurvePanelSlot` + dispatch wire + cold-start backfill (no REST poll for funding 因 next_funding_ms 由 WS 即時 broadcast) |
| **B-2** | E1-β | Rust `panel_aggregator::oi_delta_aggregator` (新) + V087 + Rust `OIDeltaPanelSlot` + dispatch wire + cold-start backfill (Rust 啟動跑 1 次 batch `bybit_rest_client::get_open_interest_batch()` 拉 25 sym × 3 interval (5min/15min/1h) history 寫 V087；後續 WS push 即時 oi_abs，aggregator 算 5m/15m/1h delta vs cold-start baseline) |
| **B-3** | BB sub-agent | **DONE** 2026-05-10 → BB report 採納 → v1.1 WS-first 設計（無需 D+1 PA + BB integrate cycle） |
| **B-4** | E1-γ | AlphaSurface consumer 驗收：bb_breakout `OiDeltaPanel` 真實 consume + fail-closed 寫 `oi_panel_unavailable`（**邏輯完全不變，與 producer side WS/REST 無關**）|

**out of scope**：basis_curve（Tier 2.2 Bybit demo 不支援 spot lending，fence by ADR-0018）、Tier 3 Microstructure、Tier 4 Information flow、**Python writer files**（v1.1 deprecate；不寫 `funding_curve_writer.py` / `oi_delta_panel_writer.py`）。

### 1.3 W1 vs W2 對比

| 維度 | W1 (Phase B Tier 2 panel) | W2 (A4-C BTC→Alt Lead-Lag) |
|---|---|---|
| Engine mode | demo + live_demo + live | **paper-only**（fence by `step_4_5_dispatch.rs` engine_mode gate）|
| Rationale | Phase B 是 production foundation；funding/OI 是 well-known signal，無 paper-only 理由 | A4-C 是 fast-track exploration；7d paper edge gate 才升 demo |
| Consumer | bb_breakout 真 consume + 5 策略可選 declare | ma_crossover + grid_trading shadow log only（C-IMPL-3 不直接 trade）|
| Edge gate | 無（直接接 production；evidence 由 healthcheck `[40]` realized_edge 觀察）| ≥ +5 bps paper avg_net 才 promote N+2 demo |

---

## §2 B-1 funding_curve aggregator Spec (v1.1 WS-first)

### 2.1 Bybit V5 Source + Rate Budget

**Primary source (ongoing)**: **既有 WS `tickers.{SYMBOL}` topic broadcast** — `enable_extended_ws=true` 預設訂閱，每 sym 一個 tickers topic（既有 25 sym × tickers = 25 topics，0 額外 connection cost）。每次 ticker update 即推送 `fundingRate` + `nextFundingTime` field（per `parsers.rs:225-263` 已 parse；`nextFundingTime` 待 W1 IMPL 加 extract）。

**Cold-start backfill source**: 不需。`nextFundingTime` 在 WS connect 後第一個 ticker tick 即帶（Bybit 每秒 push tickers update），預期 connect 後 1-5s 內 25 sym 全部 buffer fill。如 cold-start 30s 仍未收到某 sym 的 ticker → fail-closed `next_funding_ms = None` for 該 sym（slot 該 sym 不寫，consumer 看 None 走 fail-closed）。

**REST fallback**: 不啟用（v1.1 完全 WS-first；如未來 WS reconnect gap > 1 funding cycle (8h) 才考慮加 `bybit_rest_client::get_funding_history()` backfill — 留 W-AUDIT-8d 評估）。

**Rate budget (BB §6 採納後)**：
- v1.1 ongoing: **0 req/s** (WS broadcast 無 REST cost)
- v1.1 cold-start: **0 req** (funding 不需 backfill)
- WS reconnect gap fill: 由既有 RE-2 supervisor (`main_ws.rs:75-131`) 自動重連；**WS 重訂閱不計入 REST rate**（WS connection 重建 + topic re-subscribe 為 free operation per Bybit V5 doc）
- Cap headroom: 99%+ (BB §2.5 baseline 0.7 req/s + W1 0 + W2 0 + W3 0 = ~1.2 req/s vs 120 req/s cap)

**Cohort 25 symbol**（per W2 spec §2.2 + Phase B production scope）：
- Active strategy 25-symbol union：grid_trading active set ∪ ma_crossover active set ∪ bb_breakout active set
- 動態源：讀 `strategy_params_demo.toml` + `strategy_params_live.toml` 取 active=true 策略的 `symbols` 並 union
- **Excluded**：BUSDT (ADR-0018 funding_arb retire)、`strategy_blocked_symbols_freeze.json` 列入的 BSBUSDT / PRLUSDT / ZBTUSDT / FARTCOINUSDT 等
- W1 IMPL 期間 cohort 固定 25 個 hardcoded snapshot（D+0 PM 確認最終 list）；後續 W-AUDIT-8c generic 跨資產 panel 再做 dynamic cohort discovery
- **WS subscribe alignment**：cohort 25 sym 必須是 `SymbolRegistry.snapshot()` 的 strict subset（既有 WS supervisor 從 SymbolRegistry 拉 topic list）；如 cohort 含 SymbolRegistry 沒有的 sym → aggregator 寫 audit log + fail-closed 該 sym。SymbolRegistry 動態調整時（add/remove sym）由 `WsTopicChangeRelay` 推送變更，aggregator 跟著調整 buffer cohort（W-AUDIT-8c phase 才完整 dynamic；W1 hardcoded cohort = SymbolRegistry static subset）

### 2.2 PG Table V085 Schema

```sql
-- V085__funding_rates_panel.sql
-- W-AUDIT-8a Phase B Tier 2.1 funding curve panel
-- 對齊 srv/rust/openclaw_core/src/alpha_surface.rs:127-140 FundingCurveSnapshot

CREATE SCHEMA IF NOT EXISTS panel;

CREATE TABLE IF NOT EXISTS panel.funding_rates_panel (
    snapshot_ts_ms     BIGINT      NOT NULL,
    symbol             TEXT        NOT NULL,
    funding_rate_bps   DOUBLE PRECISION NOT NULL,
    next_funding_ms    BIGINT      NOT NULL,
    source_tier        TEXT        NOT NULL DEFAULT 'bybit_v5_public',
    PRIMARY KEY (snapshot_ts_ms, symbol)
);

-- Guard A: 既存表 schema 對齊驗證（per CLAUDE.md §七 Guard A）
-- Guard B: 型別敏感欄位 ADD COLUMN 前驗 data_type（本 wave 全新表，N/A）
-- Guard C: hot-path 索引選用 pg_get_indexdef() 比對

-- TimescaleDB hypertable, 1d chunk
SELECT create_hypertable(
    'panel.funding_rates_panel',
    'snapshot_ts_ms',
    chunk_time_interval => 86400000,
    if_not_exists => TRUE
);

-- Retention 14d
SELECT add_retention_policy(
    'panel.funding_rates_panel',
    INTERVAL '14 days',
    if_not_exists => TRUE
);

-- Hot-path index: 最新 N 秒 snapshot lookup
CREATE INDEX IF NOT EXISTS idx_funding_panel_ts_desc_symbol
    ON panel.funding_rates_panel (snapshot_ts_ms DESC, symbol);
```

**Schema 對齊 trait field**（critical）：
- `funding_rate_bps` (DOUBLE PRECISION) → `FundingCurveSnapshot.funding_rates_bps: Vec<f64>`
- `next_funding_ms` (BIGINT) → `FundingCurveSnapshot.next_funding_ms: Vec<i64>`
- `snapshot_ts_ms` (BIGINT) → `FundingCurveSnapshot.snapshot_ts_ms: i64`
- `source_tier` (TEXT) → `FundingCurveSnapshot.source_tier: String`
- 25 row per snapshot_ts_ms（每 symbol 一 row）；Rust IPC slot pull 時 GROUP BY 最新 snapshot_ts_ms 構造 Vec 並對齊 `symbols[i]`

### 2.3 Rust WS Aggregator (v1.1 WS-first)

**Python writer**: **不寫**（v1.1 deprecate `funding_curve_writer.py`）。Producer 端切換到 Rust，與 v1 設計差異核心點。

**File**: `srv/rust/openclaw_engine/src/panel_aggregator/funding_curve.rs` (新)

**Pattern**: 訂閱既有 WS event stream（`event_tx` / `event_rx` mpsc 在 `main_ws.rs:44`）。改成 broadcast channel 或加一條 spmc fan-out tap（具體實作 W1 IMPL E1-α 決定，PA 推薦 broadcast pattern：`tokio::sync::broadcast::channel(2048)` 既有 dispatch 可同時 fan-out），由 `panel_aggregator` task subscribe 一個 receiver。

```rust
//! W-AUDIT-8a Phase B B-1 funding curve aggregator (WS-first).
//! 訂閱既有 WS event stream，filter Ticker variant，60s 視窗 flush 一批
//! panel.funding_rates_panel。同時寫 PG (audit/training) + slot (hot path)。

pub struct FundingCurveAggregator {
    cohort: Vec<String>,                    // 25 sym hardcoded snapshot
    buffer: HashMap<String, (f64, i64)>,    // sym → (latest_funding_rate_bps, next_funding_ms)
    slot: FundingCurvePanelSlot,            // Arc<RwLock<Option<FundingCurveSnapshot>>>
    pg_pool: Arc<PgPool>,                   // 雙寫 PG
    flush_interval: Duration,               // 60s
}

impl FundingCurveAggregator {
    /// W-AUDIT-8a Phase B B-1: 主迴圈 — 訂閱 WS event_rx，60s 視窗 flush。
    pub async fn run(
        mut self,
        mut event_rx: broadcast::Receiver<PriceEvent>,
        cancel: CancellationToken,
    ) {
        let mut flush_timer = tokio::time::interval(self.flush_interval);
        loop {
            tokio::select! {
                _ = cancel.cancelled() => break,
                _ = flush_timer.tick() => self.flush().await,
                event = event_rx.recv() => match event {
                    Ok(ev) if ev.event_kind == Some(PriceEventKind::Ticker)
                              && self.cohort.contains(&ev.symbol) => {
                        // funding_rate / next_funding_ms 在 WS parser 已 extract（W1 IMPL 加 next_funding_ms）
                        if let (Some(fr), Some(nf)) = (ev.funding_rate, ev.next_funding_ms) {
                            self.buffer.insert(ev.symbol.clone(), (fr * 10000.0, nf));
                        }
                    }
                    Ok(_) => {} // skip non-ticker / non-cohort events
                    Err(broadcast::error::RecvError::Lagged(n)) => {
                        warn!(lag_count = n, "funding_curve_aggregator: broadcast lag");
                    }
                    Err(broadcast::error::RecvError::Closed) => break,
                    _ => {}
                }
            }
        }
    }

    /// flush: snapshot buffer → 寫 PG (audit) + 寫 slot (hot path)
    async fn flush(&mut self) {
        if self.buffer.is_empty() { return; }
        let snapshot_ts_ms = now_ms();
        let symbols: Vec<String> = self.buffer.keys().cloned().collect();
        let funding_rates_bps: Vec<f64> = symbols.iter().map(|s| self.buffer[s].0).collect();
        let next_funding_ms: Vec<i64> = symbols.iter().map(|s| self.buffer[s].1).collect();

        // 1. 寫 PG (audit / ML training data / healthcheck source)
        let _ = self.write_pg(snapshot_ts_ms, &symbols, &funding_rates_bps, &next_funding_ms).await;

        // 2. 寫 slot (hot path, dispatch step_4_5 read)
        let snapshot = FundingCurveSnapshot {
            snapshot_ts_ms,
            symbols,
            funding_rates_bps,
            next_funding_ms,
            source_tier: "bybit_v5_ws_tickers".to_string(),
        };
        *self.slot.write().await = Some(snapshot);
    }
}
```

**WS event_rx broadcast 接線**（critical 設計題）：
- 既有 `main_ws.rs:44` `event_tx: mpsc::Sender<PriceEvent>` 是 single-consumer mpsc
- v1.1 必須改成 broadcast 才能 fan-out 給 aggregator + 既有 dispatch
- E1-α IMPL：在 `main.rs` 既有 `event_tx`/`event_rx` 接線處改成 `tokio::sync::broadcast::channel(2048)`，既有 dispatch 拿一個 `event_rx.resubscribe()`，aggregator 拿另一個
- **副作用**：既有所有 PriceEvent consumer (dispatch / paper_state / strategies tick fan-out) 必須適配 broadcast::Receiver；改動量 ~5-10 caller。E1-α IMPL 必先 grep 全 caller list + 寫 channel migration 驗證
- **Backward compat alternative**: 保留 mpsc，新加 spmc broadcast 從 dispatch 端 tap fan-out（dispatch 收到 PriceEvent 後同步 broadcast.send_blocking 給 aggregator）— 這 pattern 較侵入性低但耦合 dispatch
- **PA 拍板**：E1-α IMPL 採 broadcast channel migration（pattern 一致性 > 侵入度），E2 review 必驗 caller migration 完整性

**Spawn point**：`main.rs` startup phase（既有 RE-2 supervisor spawn 之後 + dispatch 啟動之前）。Aggregator 與 supervisor 共享 `cancel: CancellationToken` graceful shutdown。

**Failure modes**:
- WS 收 ticker 但 funding_rate/next_funding_ms None (parser fail-closed) → buffer 不 insert，slot 該 sym stale 直至下個 ticker tick
- PG insert fail → log ERROR，不 raise，slot 仍寫 (hot path 不被 PG 阻)
- Broadcast lag (n events lost) → log WARN + 計數，下一 ticker tick 自動恢復
- Cohort sym 不在 WS subscribe 列 → log ERROR + cohort drift audit row + fail-closed slot 該 sym 不寫
- Cancel token → flush 一次 + graceful exit

### 2.4 Rust IPC Slot

**File**: `srv/rust/openclaw_engine/src/ipc_server/slots.rs`（PA D+0 已預留 anchor `// === W1 FundingCurvePanelSlot insertion point ===` line 170）

```rust
/// W-AUDIT-8a Phase B B-1: late-injected slot for FundingCurveSnapshot panel.
///
/// MODULE_NOTE (中)：funding_curve panel collector spawn 在 IPC server detach
///   後（Python writer 寫 PG → Rust 端 puller 拉 PG）。Slot 用
///   `Arc<RwLock<Option<FundingCurveSnapshot>>>` 讓 main.rs late-inject。
///   None = uninitialized，dispatch step_4_5 取 None → surface.funding_curve
///   = None → declared 此 tag 的策略 fail-closed 寫
///   evaluation_outcome='funding_panel_unavailable'。
pub type FundingCurvePanelSlot =
    Arc<RwLock<Option<crate::alpha_surface::FundingCurveSnapshot>>>;
```

**Slot 寫入機制 (v1.1)**：**aggregator 直接 write slot**，不需 puller 從 PG round-trip。`panel_puller.rs` 模組 v1.1 不建（v1 設計刪除）。雙寫意義：slot = hot path read（dispatch step_4_5 直接 RwLock::read clone Some/None）；PG = audit trail / ML training data / healthcheck `[57]` freshness query 來源。Latest snapshot age 由 slot 內 `snapshot_ts_ms` 決定，aggregator flush 時 stamp。

### 2.5 step_4_5_dispatch wire

**File**: `srv/rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs`（PA D+0 已預留 anchor）

```rust
let funding_curve_snapshot = self.funding_curve_slot.read().await.clone();
let funding_curve = funding_curve_snapshot.as_ref();  // Option<&FundingCurveSnapshot>

let surface = AlphaSurface {
    // ... existing fields ...
    funding_curve,
    // ... oi_delta_panel: 同模式（B-2 加） ...
};
```

**Freshness gate (v1.1)**：Aggregator flush 時若 buffer 內任 sym 的 `next_funding_ms` 在 +5s 內未收到任何 ticker tick (cohort 該 sym last_seen_ms > 5s 老) → 該 sym 標 `stale_in_buffer`，flush 時不入該 sym 進 snapshot Vec。如整 cohort 全 stale (例如 WS 完全斷) → slot 寫 None（不寫 partial snapshot）。**5s WS-tick freshness threshold** 嚴於 v1 30s 因為 WS 是 push-based（正常每秒 update），5s 已是嚴重落後。Healthcheck `[57]` 監測 PG `panel.funding_rates_panel` 最新 snapshot_ts_ms vs now：30s WARN / 300s FAIL（PG-side 寬鬆閾值，因為 60s flush + WS reconnect gap 可能瞬時 60-120s 落後）。

---

## §3 B-2 oi_delta_panel aggregator Spec (v1.1 WS-first + REST cold-start)

### 3.1 Bybit V5 Source + Rate Budget

**Primary source (ongoing oi_abs)**: **既有 WS `tickers.{SYMBOL}` topic broadcast** — 每 ticker update 帶 `openInterest` field（per `parsers.rs:250-254` 已 extract → `PriceEvent.open_interest: Option<f64>`）。Aggregator 從 WS event stream 取 oi_abs latest snapshot per sym。

**Cold-start backfill source (5m/15m/1h history)**: WS broadcast 只有 instantaneous `openInterest`，**沒有 prior interval 的 OI value 給 delta 算**。Cold-start 必須跑 1 次 batch REST `/v5/market/open-interest?category=linear&symbol={SYM}&intervalTime={5min|15min|1h}&limit=2` 拉 25 sym × 3 interval = 75 req 1 batch (~0.6s burst, 75/600 5s window = 12.5% burst, well under cap)。Cold-start 後 baseline 寫 `oi_baseline_5m / 15m / 1h` 進 aggregator state。

**Ongoing delta 算法**：
- `oi_delta_5m_pct` = (current_oi_abs - oi_baseline_5m_ago) / oi_baseline_5m_ago × 100
- aggregator 維護 sliding window deque per sym：`(ts_ms, oi_abs)` 最近 1h
- flush 時取 5m/15m/1h ago 對應 oi_abs (deque lookup) 算 delta
- WS broadcast 即時更新 oi_abs；無需任何 ongoing REST poll

**REST 加固 (optional)**: 每 5 min 跑 1 次 `bybit_rest_client::get_open_interest_batch()` 25 sym × 1 interval (5min) = 25 req/5min = 0.083 req/s 寫 PG `oi_baseline_5m` 對齊 Bybit official 5min granular value（防 WS rolling delta 與 Bybit 5m close-bar 失步）。**v1.1 預設關**：W3 Stage 2 evidence 顯示 WS-only delta 與 Bybit 5m granular 偏差 > ±0.5% 才開（留 W-AUDIT-8d 評估 + 開 P2 ticket）。

**Rate budget (BB §6 採納後)**：
- v1.1 ongoing: **0 req/s** (WS broadcast 無 REST cost)
- v1.1 cold-start: **75 req in 1 batch** (~0.6s burst, well under 600/5s window)
- WS reconnect gap fill: cold-start backfill 重跑（aggregator 偵測 broadcast Lagged event 觸發 backfill）
- Cap headroom: 99%+

**WS 不夠 5m/15m/1h baseline 的 risk**：
- WS-only oi_delta 是 rolling window 算法（aggregator 自己 maintain 1h deque），與 Bybit 官方 5m close-bar 算法可能小偏差
- 偏差 > ±0.5% 是 WARN signal（W3 Stage 2 evidence + P2 ticket fix）
- bb_breakout 用 oi_delta_5m_pct 是 directional signal (delta > 1% squeeze + delta < -1% drain)，0.5% 偏差不影響 directional decision，但需 healthcheck 監測（[58] freshness + value plausibility）

### 3.2 PG Table V087 Schema

```sql
-- V087__oi_delta_panel.sql
-- W-AUDIT-8a Phase B Tier 2.3 OI delta panel
-- 對齊 srv/rust/openclaw_core/src/alpha_surface.rs:164-175 OIDeltaPanel
-- 注意：trait field 是 5m/15m/1h（NOT 1m/5m/15m）

CREATE SCHEMA IF NOT EXISTS panel;

CREATE TABLE IF NOT EXISTS panel.oi_delta_panel (
    snapshot_ts_ms      BIGINT       NOT NULL,
    symbol              TEXT         NOT NULL,
    oi_delta_5m_pct     DOUBLE PRECISION,  -- nullable: 5m window 不足
    oi_delta_15m_pct    DOUBLE PRECISION,
    oi_delta_1h_pct     DOUBLE PRECISION,
    oi_abs              DOUBLE PRECISION NOT NULL,
    source_tier         TEXT         NOT NULL DEFAULT 'bybit_v5_public',
    PRIMARY KEY (snapshot_ts_ms, symbol)
);

SELECT create_hypertable(
    'panel.oi_delta_panel', 'snapshot_ts_ms',
    chunk_time_interval => 86400000, if_not_exists => TRUE
);
SELECT add_retention_policy(
    'panel.oi_delta_panel', INTERVAL '14 days', if_not_exists => TRUE
);
CREATE INDEX IF NOT EXISTS idx_oi_panel_ts_desc_symbol
    ON panel.oi_delta_panel (snapshot_ts_ms DESC, symbol);
```

**Schema 對齊 trait field**（critical, **schema 與 task scope 描述不一致已校正**）：
- task scope 寫 `oi_delta_1m / 5m / 15m`，但 trait 定義是 `oi_delta_5m_pct / 15m_pct / 1h_pct`（per `alpha_surface.rs:164-175`）。spec **以 trait 為準**。
- 1m delta 不需要：1m 噪音太高，5m/15m/1h 才是 informational tier。
- `oi_abs` (DOUBLE PRECISION) → `OIDeltaPanel.oi_abs: Vec<f64>`

### 3.3 Rust WS Aggregator (v1.1 WS-first)

**Python writer**: **不寫**（v1.1 deprecate `oi_delta_panel_writer.py`）。

**File**: `srv/rust/openclaw_engine/src/panel_aggregator/oi_delta.rs` (新)

**Pattern**: 同 §2.3 funding_curve_aggregator broadcast pattern，差異核心 = aggregator 內 maintain 1h sliding window deque per sym + cold-start backfill 跑 1 次 REST batch 拉 25 sym × 3 interval history。

```rust
//! W-AUDIT-8a Phase B B-2 OI delta panel aggregator (WS-first + cold-start REST backfill).

pub struct OIDeltaAggregator {
    cohort: Vec<String>,
    /// Per-sym 1h sliding window: VecDeque<(ts_ms, oi_abs)>
    windows: HashMap<String, VecDeque<(i64, f64)>>,
    /// Latest WS oi_abs per sym (用於 flush)
    latest: HashMap<String, (i64, f64)>,
    slot: OIDeltaPanelSlot,
    pg_pool: Arc<PgPool>,
    flush_interval: Duration,
}

impl OIDeltaAggregator {
    /// Cold-start backfill: 1 batch REST 拉 25 sym × 3 interval history → fill windows
    pub async fn cold_start_backfill(&mut self, rest_client: &BybitRestClient) -> anyhow::Result<()> {
        for sym in &self.cohort {
            for iv in &["5min", "15min", "1h"] {
                match rest_client.get_open_interest(sym, iv, 12).await {
                    Ok(records) => {
                        let win = self.windows.entry(sym.clone()).or_insert_with(VecDeque::new);
                        for r in records {
                            win.push_back((r.timestamp_ms, r.open_interest));
                        }
                    }
                    Err(e) => {
                        warn!(symbol=%sym, interval=%iv, error=?e, "oi cold-start backfill failed");
                        // fail-closed: this sym 將在 flush 時 oi_delta_*_pct = NaN → consumer 走 fail-closed
                    }
                }
            }
        }
        Ok(())
    }

    pub async fn run(
        mut self,
        mut event_rx: broadcast::Receiver<PriceEvent>,
        cancel: CancellationToken,
    ) {
        let mut flush_timer = tokio::time::interval(self.flush_interval);
        loop {
            tokio::select! {
                _ = cancel.cancelled() => break,
                _ = flush_timer.tick() => self.flush().await,
                event = event_rx.recv() => match event {
                    Ok(ev) if ev.event_kind == Some(PriceEventKind::Ticker)
                              && self.cohort.contains(&ev.symbol) => {
                        if let Some(oi) = ev.open_interest {
                            // 維護 latest + sliding window
                            self.latest.insert(ev.symbol.clone(), (ev.ts_ms as i64, oi));
                            let win = self.windows.entry(ev.symbol.clone()).or_insert_with(VecDeque::new);
                            win.push_back((ev.ts_ms as i64, oi));
                            // Trim window > 1h
                            let cutoff = ev.ts_ms as i64 - 3_600_000;
                            while win.front().map(|(t, _)| *t < cutoff).unwrap_or(false) {
                                win.pop_front();
                            }
                        }
                    }
                    Ok(_) => {}
                    Err(broadcast::error::RecvError::Lagged(n)) => {
                        warn!(lag_count=n, "oi_delta_aggregator: broadcast lag");
                        // P0: Lagged → 視為 reconnect-style gap，下次 flush slot 寫 None
                    }
                    Err(broadcast::error::RecvError::Closed) => break,
                    _ => {}
                }
            }
        }
    }

    async fn flush(&mut self) { /* ... 算 5m/15m/1h delta vs window lookup, 寫 PG + slot ... */ }
}
```

### 3.4 Rust IPC Slot + Dispatch

**File**: `slots.rs`（PA D+0 anchor `// === W1 OIDeltaPanelSlot insertion point ===` line 174）

```rust
pub type OIDeltaPanelSlot =
    Arc<RwLock<Option<crate::alpha_surface::OIDeltaPanel>>>;
```

**step_4_5_dispatch wire** 同 §2.5 pattern（OPanel struct vs FundingCurveSnapshot 差異僅 type）。

**Freshness gate (v1.1)**：Aggregator flush 時若 sym latest_ts < now - 5s → buffer 標 stale，flush 時不入 snapshot。整 cohort 全 stale → slot 寫 None。Healthcheck `[58]` 監測 PG 30s WARN / 300s FAIL（與 [57] 一致 PG-side 寬鬆閾值）。

---

## §4 B-4 AlphaSurface Consumer 驗收（bb_breakout fail-closed）

### 4.1 bb_breakout 真實 consume `OiDeltaPanel`

**Current state**: bb_breakout 已 declare `OiDeltaPanel` tag (`mod.rs:295-300`)，但 `on_tick` 內**未真實 consume `surface.oi_delta_panel`**——還在用既有 `oi_buffer` per-symbol 自己 maintain 的 OI 序列。

**W1 land 後 IMPL**（B-4 E1-γ）：
- bb_breakout `on_tick` 加 `surface.oi_delta_panel` 真實 consume 邏輯
- 用 `oi_delta_5m_pct[i]` / `oi_delta_15m_pct[i]` 替代部分 internal buffer
- internal `oi_buffer` 保留作 fallback（panel unavailable 時 degrade）→ 留 W-AUDIT-8d 才完全移除

### 4.2 Fail-closed 寫 `oi_panel_unavailable`

**觸發 condition**：
1. `surface.oi_delta_panel.is_none()` — slot 未初始化或 puller stale > 300s
2. `surface.oi_delta_panel.is_some()` 但 `symbols` Vec 不含當前 tick 的 symbol — cohort drift
3. `surface.oi_delta_panel.is_some()` 但對應 symbol 的 `oi_delta_5m_pct` is NaN — Bybit endpoint 短暫 404

**處理**：
- bb_breakout `on_tick` early return 不 emit `StrategyAction`
- 寫 `learning.decision_features_evaluations` row：
  - `evaluation_outcome = 'oi_panel_unavailable'`（V082 enum 加新值；E2 review 必檢 V082 enum 列表）
  - `evidence_source_tier = 'panel_fail_closed'`
  - `strategy_name = 'bb_breakout'`
  - `symbol`, `engine_mode`, `ts_ms`
- 不 fallback to internal `oi_buffer`（fail-closed semantics）

**對齊 P1-BB-BREAKOUT-FAIL-CLOSED-1**：dispatch v3.3 §3.5 P1 list 已預留此 ticket；W1 land 同步 close。

### 4.3 5 策略 declare 表（B-4 E1-γ 必確認）

| Strategy | Phase A declared | W1 land 後 declared | W1 真實 consume? |
|---|---|---|---|
| ma_crossover | `[Ta1m]` | 不變（Phase A 留 W2 加 `CrossAsset`） | NO |
| grid_trading | `[Ta1m]` | 不變（W2 加 `CrossAsset`） | NO |
| bb_breakout | `[Ta1m, Ta5m, OiDeltaPanel]` | 不變 | **YES (B-4)** |
| bb_reversion | `[Ta1m, Ta5m]` | 不變 | NO |
| funding_arb | `[Ta1m]`（已 retire by ADR-0018） | 不變（active=false 但 trait declare 保留） | NO（active=false） |

W1 不擴 declare scope；ma_crossover / grid_trading 加 `CrossAsset` 在 W2 IMPL；bb_reversion 加 `OiDeltaPanel` 留 W-AUDIT-8d 評估。

---

## §5 B-3 Bybit V5 Rate-Limit Budget — DONE (BB sub-agent delivered, PA integrated v1.1)

**BB report**: `srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-10--w1_w2_bybit_v5_rate_budget_review.md`（HEAD 2026-05-10）

**BB Verdict**: PASS, ~99% headroom (baseline 0.7 + W1+W2+W3 < 0.5 = ~1.2 req/s vs 120 req/s cap)

**BB §6 HIGH push back 採納**：v1 REST polling pattern (100 req/min) 是 over-engineering — `tickers` WS topic 已 broadcast `fundingRate` + `openInterest`。v1.1 spec 完整切換 WS-first：
- Funding aggregator: **0 req/s ongoing** (WS broadcast 即時 funding_rate + next_funding_ms)
- OI aggregator: **0 req/s ongoing** (WS broadcast 即時 oi_abs) + cold-start REST batch 75 req 1 batch (~0.6s burst, well under 600/5s cap)
- WS reconnect gap: 既有 RE-2 supervisor 自動重連 + cold-start backfill 重跑

**BB §6 MEDIUM 採納項**：
- v1 設計若維持 REST polling 必須加 `is_group_near_limit(Market, 30)` 預警 — v1.1 切 WS-first 後**不需要**（0 ongoing REST cost）
- Cold-start REST batch (75 req) 與既有 baseline (0.7 req/s = 3.5 req/5s) 並發無風險，無需 staggered start

**v1.1 真實 rate budget**：

| 來源 | v1 設計 | **v1.1 設計** |
|---|---|---|
| Funding ongoing | 25 req/min (4.2%) | **0 req/s** |
| OI ongoing | 75 req/min (12.5%) | **0 req/s** |
| Cold-start (1 次 startup) | 0 | **75 req batch (~0.6s burst, 12.5% of 600/5s)** |
| Reconnect gap fill (per event) | 0 | ~75 req batch (cold-start 重跑) |
| **Total ongoing increment** | **100 req/min (16.7% budget)** | **0 req/s (0% budget)** |

**v1.1 對 W2/W3/baseline 加總**: < 1.2 req/s vs 120 req/s cap = **~99% headroom**

---

## §6 Sub-agent 分工 + 衝突避撞 (v1.1 WS-first)

**核心策略**：PA D+0 trait skeleton + slots.rs / step_4_5_dispatch.rs anchor 已 land（HEAD `c9fb0b8f`）。W1 三個 E1 sub-agent **完全並行 0 file 重疊**，但 **E1-α 必須先 land event channel migration (mpsc → broadcast)，E1-β 才 rebase 接 broadcast::Receiver**（aggregator pattern 共享）。

| Sub-agent | Files (不重疊) | 關鍵交付 |
|---|---|---|
| **W1 E1-α (B-1, leader)** | `openclaw_types/src/price.rs` (加 `pub next_funding_ms: Option<i64>` field) + `ws_client/parsers.rs` (`parse_ticker_item` 加 `nextFundingTime` extract → `event.next_funding_ms`) + `main.rs` (event channel mpsc→broadcast migration + `panel_aggregator` task spawn) + `panel_aggregator/mod.rs` (新模組 root) + `panel_aggregator/funding_curve.rs` (新) + `sql/migrations/V085__funding_rates_panel.sql` (新) + `slots.rs` (anchor `// === W1 FundingCurvePanelSlot insertion point ===` 下方加 typedef) + `tick_pipeline/on_tick/step_4_5_dispatch.rs` (對應 anchor 加 surface.funding_curve assignment) + `passive_wait_healthcheck.py` 加 `check_57_funding_curve_panel_freshness()` | Funding aggregator subscribes WS broadcast Ticker events + 60s flush PG + slot + step_4_5 構造 surface.funding_curve = Some + healthcheck [57] PASS |
| **W1 E1-β (B-2)** | `panel_aggregator/oi_delta.rs` (新；rebase E1-α push 後接 broadcast::Receiver pattern) + `sql/migrations/V087__oi_delta_panel.sql` (新) + `slots.rs` (anchor `// === W1 OIDeltaPanelSlot insertion point ===` 下方加 typedef) + `step_4_5_dispatch.rs` (對應 anchor) + `bybit_rest_client.rs` (加 `get_open_interest_batch()` helper if not exist；既有 layer2_tools_g3_07 pattern 對齊) + `passive_wait_healthcheck.py` 加 `check_58_oi_delta_panel_freshness()` | OI aggregator subscribes WS broadcast Ticker events + cold-start REST backfill 75 req batch + 1h sliding window + 60s flush + healthcheck [58] PASS |
| **W1 E1-γ (B-4)** | `bb_breakout/mod.rs` `on_tick` 真實 consume `surface.oi_delta_panel` + fail-closed evaluation_outcome 寫入 + `sql/migrations/V086__decision_features_evaluations_oi_unavailable_outcome.sql` (新；V082 evaluation_outcome enum 加 `'oi_panel_unavailable'` value via Guard A 對齊 check) | bb_breakout 真實 consume + fail-closed lineage 完整 + V082 enum 對齊（**邏輯與 producer side 無關，與 v1 完全相同**） |

**衝突點分析 (v1.1)**：
- `slots.rs` E1-α + E1-β 各加 typedef，PA D+0 anchor 隔離；E1-γ 不動 slots.rs ✓
- `step_4_5_dispatch.rs` E1-α + E1-β 各加 surface field assignment，anchor 隔離；E1-γ 不動 dispatch ✓
- V### migration 編號 V085 / V086 / V087 預先 reserved；V088 留 W2 BtcLeadLagPanel ✓
- `panel_aggregator/mod.rs` (E1-α 建 module root) + `funding_curve.rs` (E1-α) + `oi_delta.rs` (E1-β)，三檔不重疊 ✓
- **`main.rs` event channel migration is gating dependency**：E1-α 先 land migration（mpsc → broadcast + 全 caller 適配），E1-β D+3 等 E1-α push 後 rebase 接 broadcast::Receiver；**強制 sequential**，不能並行寫 main.rs
- **`bybit_rest_client.rs` `get_open_interest_batch()`**：grep 既有；如已存在則 reuse，不 conflict；如不存在 E1-β 加（孤立 helper fn）
- `passive_wait_healthcheck.py` E1-α + E1-β 各加 `check_57_*` / `check_58_*` 不同 fn；可同 commit cycle 內合併 ✓
- **PA dispatch 時間順序**：D+1 dispatch E1-α → D+2-D+3 E1-α land event channel migration + funding aggregator → D+3 dispatch E1-β + E1-γ (parallel) → D+4-D+5 land + E2/E4 review

**E2 重點審查 3 點 (v1.1)**：
1. **Event channel migration 完整性**（critical, v1.1 新增）：E1-α 把 mpsc::Sender<PriceEvent> 改成 tokio::sync::broadcast::Sender<PriceEvent> (capacity 2048)，所有 caller (dispatch / paper_state init / scanner / 其他 tap) 必須改成 broadcast::Receiver + handle Lagged variant。E2 必 grep 全 caller list 比對 migration 是否漏接；漏接 → silent dropped events → 策略 starve。
2. **V085 / V087 schema 對齊 trait struct field + V086 V082 enum 對齊**（critical）：grep `funding_rate_bps`（NOT `funding_rate`）+ grep `oi_delta_5m_pct / 15m_pct / 1h_pct`（NOT `1m / 5m / 15m`）。V086 必加 `oi_panel_unavailable` value to V082 enum via Guard A IF NOT EXISTS + backward-compat 既有 row 不變。
3. **bb_breakout fail-closed 路徑無 silent fallback + Aggregator broadcast Lagged handling**：grep `bb_breakout/mod.rs` `on_tick` 內 `if surface.oi_delta_panel.is_none()` 路徑必走 fail-closed（write evaluation + early return），**禁止 fallback to internal `oi_buffer`**；同時 grep aggregator code 確認 `RecvError::Lagged(n)` 走 WARN log + 計數 + 下次 flush slot 寫 None（不 silent skip）。

---

## §7 Risk + 16 原則合規

### 7.1 Backward compat
- `FundingCurveSnapshot` / `OIDeltaPanel` struct typedef 在 Phase A 已 land；W1 不改 struct shape，只 wire producer
- `AlphaSurface.{funding_curve, oi_delta_panel}` field 在 Phase A 已存在；W1 從 None → Some
- bb_breakout `on_tick` 加新邏輯但保留 `oi_buffer` fallback 路徑（暫時，留 W-AUDIT-8d 完全移除），**不 break existing test**
- E4 regression：5 策略全 retest + bb_breakout 跑 demo 24h surface.oi_delta_panel = Some 路徑 + paper engine 跑 surface.oi_delta_panel = None 路徑（fail-closed evaluation_outcome 寫入驗）

### 7.2 16 原則合規（CLAUDE.md §二 + skill checklist）

| # | 原則 | W1 影響 | 狀態 |
|---|---|---|---|
| 1 | 單一寫入口 | panel writer 只寫 `panel.*` schema；不寫 trading 路徑 | ✅ |
| 2 | 讀寫分離 | producer 寫 PG，consumer 讀 PG（slot pull）；無 GUI 寫入 | ✅ |
| 3 | AI 輸出 ≠ 命令 | bb_breakout 用 panel data 計算 signal，仍走 SM-04 Guardian | ✅ |
| 4 | 策略不繞風控 | bb_breakout intent 仍經 Guardian；fail-closed 是 pre-Guardian gate | ✅ |
| 5 | 生存 > 利潤 | OI panel unavailable → fail-closed 不開新倉 | ✅ |
| 6 | 失敗默認收縮 | panel stale > 300s → slot None → fail-closed | ✅ |
| 7 | 學習 ≠ 改寫 Live | panel data 寫 `panel.*` 學習平面；live 路徑只讀 | ✅ |
| 8 | 交易可解釋 | `evaluation_outcome='oi_panel_unavailable'` lineage 完整 | ✅ |
| 9 | 災難保護 | bb_breakout existing hard_stop / trailing 不變 | ✅ |
| 10 | 認知誠實 | spec 區分「BB B-3 review pending」+「task scope 校正：5m/15m/1h NOT 1m/5m/15m」 | ✅ |
| 11 | Agent 最大自主 | bb_breakout 在 P0/P1 內完全自主 | ✅ |
| 12 | 持續進化 | OI panel 為策略提供新 alpha source；evaluation_outcome 為 ML training data | ✅ |
| 13 | AI 成本感知 | panel writer 是 free public endpoint，無 AI 成本 | ✅ |
| 14 | 零外部成本可運行 | Bybit V5 public endpoint 免費 | ✅ |
| 15 | 多 Agent 協作 | bb_breakout 真實 consume，5 Agent 通信不變 | ✅ |
| 16 | 組合級風險 | 25-symbol cohort funding/OI panel 提供組合視角 | ✅ |

### 7.3 DOC-08 §12 9 條安全不變量
本 wave **不動** lease / authorization / audit / reconciler / mainnet env / Bybit retCode / fail-closed semantic / live_reserved 任何路徑 → 全 9 條不變量無關 → ✅

### 7.4 硬邊界 5 項
本 wave **不動** `live_execution_allowed` / `max_retries=0` / `OPENCLAW_ALLOW_MAINNET` / `decision_lease_emitted` / `authorization.json` → 全 5 項無關 → ✅

### 7.5 已知 risk + 緩解 (v1.1 WS-first)

| Risk | 等級 | 緩解 |
|---|---|---|
| ~~Bybit V5 rate budget 超限~~ | ~~中~~ | **v1.1 解除** — WS-first 0 ongoing REST cost；cold-start 75 req batch 12.5% 5s window |
| V082 evaluation_outcome enum 加 `oi_panel_unavailable` 破既有 query | 低 | V086 ADD VALUE TO ENUM IF NOT EXISTS + Guard A 驗對齊 |
| bb_breakout 真實 consume 後 demo edge 變化（向上或向下） | 中 | E4 regression demo 24h baseline 對比 + 4-agent loss audit framework 可重跑 |
| Aggregator buffer stale (WS broadcast Lagged 或 ticker 5s 未到) but slot 未及時 None | 中 | aggregator flush 內 5s freshness check + 全 cohort stale → slot None；healthcheck [57]/[58] 30s WARN / 300s FAIL 監測 PG-side |
| schema field name 不對齊 trait struct field（task scope 已校正） | **極高** | E2 強制 grep verify；本 spec §2.2 §3.2 已明確列名 |
| **Event channel migration (mpsc → broadcast) silent broke 既有 PriceEvent caller** (v1.1 新) | **極高** | E1-α IMPL 必先 grep 全 caller list 寫 channel migration 表；E2 強制 verify 全部 caller 適配 broadcast::Receiver + Lagged variant handling；漏接 = 策略 silent starve |
| **WS reconnect gap (RE-2 supervisor 重連期間) panel snapshot stale** (v1.1 新) | 中 | aggregator broadcast Lagged → 觸發 cold-start backfill 重跑 (OI) + 下次 flush slot None 直至 WS 恢復；既有 RE-2 supervisor exponential backoff cap 60s 重連，gap window 預期 < 60s |
| **OI WS rolling delta 與 Bybit 5m close-bar 偏差 > ±0.5%** (v1.1 新) | 中 | W3 Stage 2 evidence 監測；超 ±0.5% 開 P2 ticket + W-AUDIT-8d 評估啟用 5min REST baseline 加固（每 5min 25 req = 0.083 req/s 仍 well under cap）|

---

## §8 D+1 PA + BB Joint Sign-off Checklist (v1.1)

v1.1 採納 BB §6 HIGH push back；BB B-3 rate budget review **已 DONE**（HEAD 2026-05-10）。D+1 PA + BB joint sign-off 直接收，**無需 D+1 PA edit + BB integrate 再走一輪**：
1. ✅ Rate budget table 已整合 BB §2.5 final number（v1.1 §5）
2. ✅ Producer 從 Python writer 切換為 Rust panel_aggregator（採 BB §6 推薦 WS-first pattern）
3. ✅ 補入 v1 沒有的 risk: event channel migration silent break + WS reconnect gap stale + OI rolling delta vs Bybit 5m close-bar 偏差（v1.1 §7.5）
4. ✅ §6 sub-agent dispatch 加 sequential gating: E1-α first land event channel migration → E1-β rebase → E1-γ parallel
5. **PM next action**: 接 PA + BB joint sign-off → 整合進 dispatch v3.6 §3.1 W1 update（producer side 從 Python writer 改 Rust aggregator + B-3 status DONE + sub-agent dispatch sequence v1.1 update）→ push spec v1.1 + dispatch v3.6 → D+2 dispatch W1 IMPL E1-α leader

---

## §9 一句總結 (v1.1 WS-first)

**v1.1 採納 BB HIGH push back → producer 從 Python REST writer 切換為 Rust WS aggregator (`panel_aggregator/{funding_curve,oi_delta}.rs` 訂閱既有 `tickers.{sym}` topic broadcast)；ongoing rate budget 從 100 req/min (16.7%) 降為 0 req/s (0%)；cold-start 僅 75 req batch (OI history) for 1 次 startup；WS reconnect gap 由既有 RE-2 supervisor + cold-start backfill 重跑；event channel mpsc → broadcast migration 是 critical gating dependency 由 E1-α leader 先 land；bb_breakout 真實 consume + fail-closed evaluation_outcome lineage 邏輯與 producer side 切換無關，與 v1 完全相同；trait shape 0 改動（PA D+0 已 land HEAD `c9fb0b8f`）；schema 對齊 trait field；3 個 E1 sub-agent E1-α leader → E1-β/γ parallel rebase；16 原則 + DOC-08 §12 + 硬邊界 5 項全 0 觸碰；D+1 PA + BB joint sign-off 直接收，無需再走一輪 integrate cycle。**

---

**Spec end. PA W1 next action (v1.1)**: PM 整合本 spec v1.1 進 dispatch v3.6 §3.1 W1 update → D+1 PA + BB joint sign-off → D+2 dispatch W1 IMPL E1-α leader → D+3 E1-β/γ parallel rebase → D+5-D+6 land + E2/E4 review；W1 land 後 ≥ 24h 再進 W3 Stage 1（dispatch §5.1）。

PA SPEC DONE (v1.1 WS-first revision): report path: srv/docs/execution_plan/2026-05-10--w_audit_8a_phase_b_tier_2_collector_spec.md
