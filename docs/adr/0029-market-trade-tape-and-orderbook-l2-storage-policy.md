# ADR 0029: market.public_trades + market.orderbook_l2_snapshot Storage Policy (Trade Tape & L2 Orderbook Fidelity Upgrade)

Date: 2026-05-21
Status: **Proposed**（需 MIT cross-review storage 細節 + QC 驗證 fidelity uplift 假設後 promote 至 Accepted；Track A/B 拆分留給 MIT calibration）
Operator Sign-off: TBD
Related: V002 (`market.trade_agg_1m` + `market.ob_snapshots`) / `phase_1b_sweep_replay.py:187-191` BBO-cross-proxy comment / 2026-05-20 FA P2-ENTRY-CLOSE-MAKER analysis EVID-1 / ADR-0010 (TimescaleDB hypertable + Guard migrations)

## Context

### 起源

2026-05-20 FA 對 EDGE-P2-3 Phase 1b close-maker-first observation fidelity 做 EVID 層審計，識別出 fill rate 估算的**結構性 fidelity bottleneck**：

> 當前 close-maker fill rate 系統依賴 BBO-cross-proxy 判斷 — 「BBO 反向側越過 limit_price = 視為 fill 成立」。這是**必要條件但非充分條件**。真實 fill 需要 trade actually print 才能確認；BBO cross 而 trade 未印 → fill rate 樂觀高估。

FA EVID-1 推估該 proxy 系統性樂觀 ~10-15pp（per `phase_1b_calibration_cell_selection_report.md §5.1` 與 `phase_1b_sweep_replay.py:347-350` queue-aware adjustment 補償邏輯所引用的估計）。

### BBO-cross-proxy 局限的證據錨點

`helper_scripts/calibration/phase_1b_sweep_replay.py` 已在三處註釋顯式承認此局限：

1. **Line 187-191（`simulate_cell_against_fill()` docstring）**：
   ```
   為什麼用 BBO cross 替代 trade tape：
     PG 無 tick-level trade tape；用 BBO 反向側越過 limit 視為「會被 fill」
     （保守模型 — 真實 fill 需 trade actually print，BBO cross 是 necessary
     condition 但非 sufficient）；對 calibration 用途足夠。spec §2.3.5 標
     future enhancement 用 trade tape 精化。
   ```

2. **Line 82-87（`FillSimulationResult` docstring）**：BBO-cross-proxy 在 queue-aware adjustment 補強前 systematic 樂觀；P2-SIM-QUEUE-AWARE-ADJUSTMENT v55 用 ob_snapshots L5 depth proxy 修正——但 ob_snapshots 是 **1m L5 summary**，非真實 L2 orderbook 在 fill_ts ± 60s 的 tick-level snapshot；補強精度有限。

3. **Line 347-350（queue-aware adjustment 邏輯）**：補償系統性樂觀預期下調 ~10-15pp。

### 既有 V002 market 表覆蓋與 fidelity gap

| 既有表 | 粒度 | Storage 估計（V002 comment） | Fidelity gap |
|---|---|---|---|
| `market.trade_agg_1m` | **1m aggregated** trades（buy_volume / sell_volume / count / vwap） | ~5 MB/day | 缺 tick-level trade tape；無法重建單筆 trade 的 ts / px / qty / side |
| `market.ob_snapshots` | **1m L5 summary**（imbalance / weighted_mid / bid_depth_5 / ask_depth_5） | ~6 MB/day | 缺 tick-level L2 snapshot；無法重建 fill_ts ± 60s 窗口內的 queue position / true depth-at-price |
| `market.market_tickers` | **5s snapshot**（last / mark / index / best_bid / best_ask / spread_bps） | ~50 MB/day | tick 不精細；fill_ts ms 級事件需 sub-second granularity |

**Phase 1b BBO-cross-proxy 用 `market_tickers` 5s 數據反推 — 兩個結構性不足**：
1. **5s 粒度盲區** — 在 5s 內可能發生「BBO 跨 limit → trade 不 print」的真實 fill failure 但 proxy 看不到
2. **無 trade tape 對齊** — 即使 BBO 確實跨 limit，沒有 trade 確認意味著 maker queue 還沒被消化到 fill；只看 BBO 等於假設 queue ahead 為 0

### 為什麼這是 EDGE-P2-3 Phase 1b 的 calibration 結構性 bottleneck

Phase 1b candidate selection report 已用 queue-aware adjustment 補強 BBO-cross-proxy，但 queue factor 用的 depth proxy 仍是 1m aggregated 的 ob_snapshots，**而非 fill_ts ± 60s 的真實 L2 snapshot**。這形成兩層 proxy 套娃：

```
真實 fill rate
  ↑ uplift +10-15pp accuracy (推測)
BBO-cross-proxy + queue-aware adjustment
  ↑ 補強系統性樂觀
BBO-cross-proxy (5s tickers + 1m ob_snapshots)
```

Trade tape + L2 orderbook snapshot 是把第 1 層替換為**直接驗證**：「fill_ts ± timeout_ms 內是否有 trade 在 maker 同側 price level print = fill 確認」。

### 為什麼 P2 而非 P1 立即動工

1. **不是 live trading correctness blocker** — BBO-cross-proxy 保守樂觀；現有 calibration 報告 + queue-aware adjustment 已是 ops-safe 的 fail-closed 設計（樂觀偏差不會導致超賣／超風險），是 fidelity 升級而非安全修補
2. **storage 成本顯著** — tick-level trade tape + L2 snapshot 從現有 ~61 MB/day（trade_agg_1m + ob_snapshots + market_tickers 合計）升到 GB/day 級別；MIT 必須先 calibrate sample rate 才能定 budget
3. **與 Phase 1b 14d freeze timing 衝突** — V094 schema 還在 14d observation 期；新 migration 不應 land 在 freeze window，需 freeze 結束後 land
4. **Bybit WS 需要新接線** — `publicTrade.{symbol}` + `orderbook.50.{symbol}` 是當前 engine **未訂閱**的 topic（per `multi_interval_topics.rs` topic 函數 + dispatch.rs parser），是非平凡的 WS subscription / parser 工程量

## Decision

**Proposed**：為 EDGE-P2-3 fidelity 升級立 2 個新 market 表 + 對應 WS 接線 + 治理 storage policy。**本 ADR 不 commit schema 細節**，因 MIT cross-review sample rate 與 storage budget 後才能 finalize；本 ADR 為**設計意圖 + 待解決問題 + 治理基線**的鎖定。

### 設計意圖（待 MIT calibrate 後 promote 至 Accepted）

#### `market.public_trades` 寫盤策略（tick-level trade tape）

**候選 schema（待 calibrate）**：

```sql
CREATE TABLE IF NOT EXISTS market.public_trades (
    ts              TIMESTAMPTZ NOT NULL,    -- Bybit trade ts (ms granularity, may collide)
    symbol          TEXT        NOT NULL,
    trade_id        TEXT        NOT NULL,    -- Bybit unique trade id per symbol
    price           REAL        NOT NULL,
    qty             REAL        NOT NULL,
    side            TEXT        NOT NULL,    -- 'Buy' / 'Sell' (taker side)
    is_block_trade  BOOLEAN     NOT NULL DEFAULT FALSE,
    PRIMARY KEY (symbol, ts, trade_id)
);
```

**PK 設計理由**：對齊 V095 `market.liquidations` 的 lossy-pk 教訓——`(symbol, ts)` 在 ms 級 collision 會丟事件；`trade_id` 必入 PK 保證 idempotency。

**TimescaleDB hypertable**：`chunk_time_interval => INTERVAL '1 day'`（對齊 V002 既有 pattern）。

**Compression policy**（待 MIT calibrate）：
- 候選：`add_compression_policy('market.public_trades', INTERVAL '7 days')`
- 假設 ratio 5-10x（per Track-based attribution 既有 hypertable compression 觀察；尚未在 trade tape 樣本驗）

**Retention policy**（待 MIT calibrate）：
- 候選 A：30d full retention + compressed
- 候選 B：14d full + 30d trade_agg_1m 已涵蓋的時間段降採樣

**Sample rate decision**（待 MIT + PA calibrate）：
- **Option T-1：Full tape**（每筆 Bybit `publicTrade` 都寫）—— 最高 fidelity，最大 storage
- **Option T-2：Threshold-filtered tape**（qty >= per-symbol threshold 才寫，配置在 risk_config）—— 中等 fidelity，1/10–1/100 storage
- **Option T-3：Symbol-tier 採樣**（active cohort full tape，其餘 symbol qty-threshold filter）—— 平衡方案

MIT calibration 範圍包含：估算 25-symbol cohort 在 ~100 trades/s peak 與 ~5 trades/s avg 下的 daily volume；驗證 PG 4-8GB shared_buffers 限制下 hypertable insert path 不阻塞 hot 寫入路徑（per `project_hardware_constraints` memory 4-8GB PG 限制）。

#### `market.orderbook_l2_snapshot` 寫盤策略（L2 orderbook snapshot）

**候選 schema（待 calibrate）**：

```sql
CREATE TABLE IF NOT EXISTS market.orderbook_l2_snapshot (
    ts              TIMESTAMPTZ NOT NULL,
    symbol          TEXT        NOT NULL,
    bids            REAL[]      NOT NULL,    -- flat [price, qty, price, qty, ...] up to L20
    asks            REAL[]      NOT NULL,    -- flat [price, qty, price, qty, ...] up to L20
    levels          SMALLINT    NOT NULL,    -- actual depth captured (5 / 20 / 50)
    seq             BIGINT,                   -- Bybit u (orderbook seq) for ordering
    update_kind     TEXT        NOT NULL,    -- 'snapshot' / 'delta_collapsed'
    PRIMARY KEY (symbol, ts, seq)
);
```

**為什麼 REAL[] 而非 JSONB**：(a) PG REAL[] storage 比 JSONB 緊湊 ~30-40%；(b) TimescaleDB compression 對 array column 效果優於 JSONB；(c) ML / replay 不需要 JSON-query semantics，flat array 對齊 numpy ingestion。

**Sample rate decision**（待 MIT + PA calibrate）：
- **Option L-1：Tick-level**（每筆 `orderbook.50` delta 都重建 snapshot 並寫）—— 最高 fidelity；storage 估 50-200 MB/day/symbol = ~5 GB/day 全 cohort
- **Option L-2：1s sampled**（每 1s 取最後一筆 delta collapse 寫）—— 中等 fidelity；storage 估 5-10 MB/day/symbol = ~150 MB/day 全 cohort
- **Option L-3：5s sampled**（每 5s collapse 寫，與 `market_tickers` 對齊）—— 低 fidelity 但 storage 對齊既有 budget；storage 估 1-2 MB/day/symbol = ~30 MB/day 全 cohort
- **Option L-4：Event-triggered**（只在 fill_ts ± timeout_ms 窗口寫；其餘時段不寫）—— Phase 1b 專用；storage 最小

**Levels decision**（待 MIT calibrate）：
- **L-5（top 5）**：對齊既有 ob_snapshots 但 tick-level；不夠用於 queue position 估算
- **L-20（top 20）**：足以重建 fill_ts queue ahead；建議 default
- **L-50（full）**：Bybit `orderbook.50` 完整深度；queue position + far-side absorption 估算最完整

MIT calibration 範圍包含：對齊 Bybit WS `orderbook.50.{symbol}` snapshot + delta 序列化 cost；驗證 delta-collapsed 寫盤路徑不引入 fill_ts critical-path latency（per ADR-0001 Rust 為唯一交易權威 — orderbook snapshot writer 不可阻塞 trading thread）

### 對齊既有 writer pattern 的可重用元素

- **TimescaleDB hypertable 創建**：對齊 V002 `DO $$ BEGIN IF EXISTS (...) PERFORM create_hypertable(...) END $$;` pattern
- **Guard A/B/C migration 範式**：對齊 V094 / V095 三 Guard layer（表存在 + 欄位型別 + DDL 結果驗證）— per `feedback_v_migration_pg_dry_run.md` Linux PG dry-run mandatory
- **WS parser**：對齊 `rust/openclaw_engine/src/ws_client/parsers.rs` 既有 `publicTrade` / `orderbook.50` parse 函數（per grep 結果 line 在 parsers.rs）；不需新接入 WS subscription，只需新加寫盤 sink
- **Topic subscription**：對齊 `multi_interval_topics.rs` `public_trade_topic()` / `orderbook_topic()` 既有函數；只需在 main_ws.rs subscription list 加入

### 治理 storage policy（待 finalize）

| Tier | 採樣策略 | 預期 daily MB（25 symbol cohort） | PG shared_buffers 4-8GB 影響 |
|---|---|---|---|
| 高 fidelity | T-1 + L-1 | ~5-8 GB/day | **不可接受**——hot insert path 超過 PG buffer capacity；需 partition 策略 + write batching |
| 平衡 fidelity（建議起點） | T-2/T-3 + L-2 | ~150-300 MB/day | **可接受**——對齊既有 V002 ~61 MB/day budget 的 2-5x；compression 後落到 1.5-2x |
| 低 fidelity | T-3 + L-3/L-4 | ~30-100 MB/day | **保守可接受**——但 fidelity uplift 可能不達 ~10-15pp 目標 |

**建議起點**：Track A（trade tape T-2/T-3）+ Track B（L2 snapshot L-2，levels L-20）；Track A/B 可獨立 land 並獨立 calibrate。MIT 在 calibration 階段決定是否合併為一個 migration 或分兩個 worktree。

### 治理基線（lock）

1. **Schema 不在本 ADR finalize** — `CREATE TABLE` DDL 候選 schema 待 MIT 提供 calibration report 後 Accepted ADR-0029 補件或 ADR-0030 / 0031 拆分
2. **Migration land timing** — V094 14d freeze 結束後（per 2026-05-20 FA 報告 freeze 期估算）才 land；不可 disturb Phase 1b observation 期
3. **Storage budget hard cap** — daily insert volume 不可超過 PG shared_buffers 4-8GB 的 ~50%（per `project_hardware_constraints`）；超過需 partition / batch write / compression 加固
4. **WS subscription enablement** — `publicTrade` + `orderbook.50` 加入 main_ws.rs subscription list 需獨立 risk_config gate（默認 disabled），enablement gate 對齊 ADR-0003 paper pipeline disabled by default pattern
5. **三引擎適用**（per 3E-ARCH） — paper / demo / live 三模式都接線；live 模式必須驗 trade tape write path 不引入 critical-path latency（per ADR-0001）
6. **Fail-closed writer** — trade tape / L2 snapshot insert 失敗不可阻塞 fill 路徑（per 原則 6 失敗默認收縮 + 原則 9 雙重防線）；degraded 落到 `market.market_tickers` + `market.ob_snapshots` fallback

## Open Questions（不在本 ADR resolve）

### OQ-1: Sample rate（tick / 1s / 5s）

**待 MIT + PA calibrate**。Decision matrix 需含：
- 在 25-symbol cohort × Bybit V5 WS 真實流量下的 daily volume 估算（MIT 跑 1-2d shadow capture 取樣）
- PG TimescaleDB hypertable insert throughput 在 4-8GB shared_buffers 下的 ceiling 測量
- Fidelity uplift 推估 — sample rate 從 tick → 1s → 5s 的 fill rate accuracy 退化量
- QC review：sample rate 是否影響後續 ML training feature 完整性

**建議起點**：Track A trade tape 用 T-2 threshold-filtered（節省 90%+ storage）；Track B L2 用 L-2 1s sampled。MIT calibration 結果若顯示 fidelity 不足才升級到 T-1 / L-1。

### OQ-2: Bybit WS topic 接線

**待 BB（Bybit liaison）review**：
- 是否需要 `publicTrade.{symbol}` + `orderbook.50.{symbol}` 雙 topic（per `multi_interval_topics.rs` 既有 helper）
- WS rate limit 對 25 symbol × 2 topic 是否觸及（per `docs/references/2026-04-04--bybit_api_reference.md` WS subscription quota）
- 與既有 `orderbook.50` subscription（若已開）是否重複 — `multi_interval_topics.rs` 提供 `orderbook_topic()` 函數但實際是否被訂閱需 BB verify

### OQ-3: 與既有 `market.trade_agg_1m` / `market.ob_snapshots` 共存

- 是否同時保留兩套寫盤？（建議：保留，因 ML feature pipeline 已對齊 1m aggregated；新表服務 fill calibration）
- Retention policy 是否錯位？（建議：trade_agg_1m / ob_snapshots 永久；public_trades / orderbook_l2_snapshot 30d-90d retention）
- 查詢路徑分流規則 — replay 用新表 vs ML training 用既有表 — 需 QC 定義

### OQ-4: Phase 1b calibration 升級 timing

- 14d freeze 結束日（per FA 2026-05-20 報告估算）— 確切日期需 PM confirm
- Migration land + WS subscription enable + 14d 樣本累積 + Phase 1b replay rerun 全鏈路時程 — MIT 需出 calibration timeline
- 是否需要 dual-write 過渡期（舊 BBO-cross-proxy + 新 trade-tape-verified 並存對齊）— QC review

### OQ-5: 與 ADR-0010 TimescaleDB hypertable + Guard migration 範式對齊

- 新 migration 用 V0XX 編號（待 PM 分配）
- Guard A/B/C 範式對齊 V094/V095 完整三層 — per `feedback_v_migration_pg_dry_run.md` Linux PG dry-run mandatory；E1 IMPL 前必先做 dry-run

## Alternatives Considered

| Alternative | 棄因 |
|---|---|
| **直接升級 `market.trade_agg_1m` 為 tick-level**（rename + schema 改造） | (a) breaking 既有 ML feature pipeline；(b) ML 已對齊 1m aggregated semantics，rename 需 downstream cascade migration；(c) tick-level 與 1m aggregated 是兩種不同 use case（fill calibration vs ML feature），應正交並存 |
| **只開 trade tape，不開 L2 snapshot** | Fidelity uplift 不對稱：trade tape 提供「fill 是否真實 print」，L2 提供「queue ahead-of-me size」；單獨 trade tape 仍需 ob_snapshots 1m L5 補強 queue position，補強精度有限；建議 Track A + Track B 並行 calibrate |
| **用既有 `market.market_tickers` 5s 數據估算** | 已知 5s 粒度盲區是 BBO-cross-proxy 局限的核心成因（per `phase_1b_sweep_replay.py:187-191`）；繼續用相同數據源無法 uplift fidelity |
| **不升級，繼續用 BBO-cross-proxy + queue-aware adjustment** | Phase 1b candidate selection report 已標 fidelity bottleneck；不升級等於接受 ~10-15pp fill rate accuracy gap 為永久限制；違反原則 12 系統行為應由 evidence 驅動演化 |
| **走 Bybit REST `/v5/market/recent-trade` 補齊歷史 trade tape** | (a) REST endpoint rate limit + 1000 trade per request 限制 — 不可重建 14d 歷史；(b) 只能向前補不能向後補；(c) WS publicTrade 即時接線是更直接路徑 |

## Consequences

### Positive

- **Fill rate accuracy uplift 推估 +10-15pp**（per FA EVID-1 + queue-aware adjustment 補償邏輯估計）—— Phase 1b candidate selection 報告與下游 EDGE-P2-3 promotion gate 可去除「樂觀偏差需手動 down-adjust」配套
- **ML feature pipeline 升級空間** — tick-level trade tape + L2 snapshot 解鎖 microstructure feature（如 order flow imbalance / queue position / aggressive fill ratio）；ADR-0021 Alpha Source Architecture Upgrade R-1 可受益
- **Replay fidelity 對齊 live 行為** — `phase_1b_sweep_replay.py` 升級為 trade-tape-verified replay；對齊 ADR-0026 direct-exploit bypass CPCV 的 evidence quality
- **Audit trail 完整性** — 每筆 close-maker fill 可追溯到對應 tick-level trade print，per 原則 8 交易可解釋
- **與既有 V002 表正交並存** — trade_agg_1m / ob_snapshots 服務 ML feature；public_trades / orderbook_l2_snapshot 服務 fill calibration；無 breaking change

### Negative / Risk

- **Storage 成本 2-5x** — 既有 ~61 MB/day 升至 150-300 MB/day（compression 後），mitigation = storage budget hard cap §治理基線 + sample rate calibration matrix
- **PG hot insert path 阻塞風險** — 4-8GB shared_buffers 限制下 tick-level insert 可能阻塞，mitigation = fail-closed writer + batch insert + TimescaleDB compression
- **WS subscription quota 風險** — `publicTrade` + `orderbook.50` 加上既有 subscription 可能觸 Bybit V5 quota，mitigation = BB review OQ-2 + risk_config gate（default disabled）
- **Migration land timing 對 Phase 1b freeze 的擾動** — 不可 land 在 14d freeze window，mitigation = freeze 結束後 land + dual-write 過渡期 OQ-3
- **Sample rate calibration 不確定性** — MIT calibration 結果可能要求 T-1 / L-1 高 fidelity，超過 storage hard cap，mitigation = ADR-0029 補件 + storage 升級決策（NAS offload / 分區 retention）
- **Dual-write 過渡期 ML training 取樣對齊** — 新舊兩套表 schema 不同，ML training pipeline 需明確路由規則，mitigation = QC review §OQ-3 定義

### 與既存設計協作

| 既存元素 | 與本 ADR 關係 |
|---|---|
| `market.trade_agg_1m` + `market.ob_snapshots`（V002） | **正交並存**；1m aggregated 服務 ML feature，新表服務 fill calibration |
| `market.market_tickers`（V002） | **保留**；5s snapshot 服務 dashboard / 一般 ML feature；新表服務高 fidelity replay |
| V094 close-maker audit schema | **下游 fidelity 升級 enabler**；本 ADR land 後 V094 `close_maker_fallback_reason` 樣本 + Phase 1b replay 可走 trade-tape-verified 路徑 |
| `phase_1b_sweep_replay.py:187-191` BBO-cross-proxy comment | **本 ADR 目標 = 移除該 comment 的 future enhancement 標籤**；replay 升級為 trade-tape-verified |
| ADR-0001 Rust 為唯一交易權威 | **trade tape / L2 snapshot writer 必須不阻塞 trading thread**；fail-closed writer 設計對齊原則 |
| ADR-0003 paper pipeline disabled by default | **WS subscription enablement 對齊同 pattern**；risk_config gate 默認 disabled |
| ADR-0010 TimescaleDB hypertable + Guard migrations | **新 migration 對齊 Guard A/B/C 三層範式**；per `feedback_v_migration_pg_dry_run.md` Linux PG dry-run mandatory |
| ADR-0021 Alpha Source Architecture Upgrade R-1 | **下游 enabler**；tick-level trade tape 解鎖 OrderFlow / Spread alpha source upgrade（C2/C3 worktree） |
| `project_hardware_constraints`（4-8GB PG shared_buffers） | **storage budget 強約束**；本 ADR §治理基線「storage budget hard cap」對齊該 memory |

## §二 16 根原則合規確認

| # | 原則 | 是否相容 | 說明 |
|---|---|---|---|
| 1 | 單一寫入口 | ✅ | 不觸 IntentProcessor / submit_intent；純 market data writer |
| 2 | 讀寫分離 | ✅ | market 表是 read-heavy 數據層；新表延續同 pattern |
| 3 | AI 輸出 ≠ 命令 | ✅ | 不創造任何 AI → trade 路徑 |
| 4 | 策略不繞風控 | ✅ | 純 market data fidelity 升級；不影響策略 → 風控門控 |
| 5 | 生存 > 利潤 | ✅ | trade tape writer fail-closed 不阻塞 fill 路徑；對齊原則 5 |
| 6 | 失敗默認收縮 | ✅ | writer insert 失敗 degraded 到既有 market_tickers + ob_snapshots fallback |
| 7 | 學習 ≠ Live | ✅ | 純 market data；不影響 live state |
| 8 | 交易可解釋 | ✅ | tick-level trade tape 補齊 audit trail；對齊原則 8 |
| 9 | 雙重防線 | ✅ | writer fail-closed 不阻塞 trading；對齊本地 + exchange 雙重防線 |
| 11 | Agent 最大自主 | ✅ | 不限縮 Agent 行為；提供更完整 market data 數據源 |
| 13 | cost 感知 | ✅ | 不增加 AI call 成本；storage cost 已在治理基線管理 |
| 14 | 零外部成本 | ✅ | 數據源是 Bybit WS（已有訂閱基礎設施）；不依賴外部付費服務 |

## Cross-References

- **Phase 1b BBO-cross-proxy comment**：`helper_scripts/calibration/phase_1b_sweep_replay.py:187-191` 與 line 82-87 + line 347-350
- **V002 既有 market 表 baseline**：`sql/migrations/V002__market_tables.sql`（`market.trade_agg_1m` + `market.ob_snapshots` + `market.market_tickers`）
- **V094 close-maker audit schema**：`sql/migrations/V094__fills_close_maker_audit.sql`（fidelity 升級下游目標）
- **V095 market.liquidations lossy-pk 教訓**：`sql/migrations/V095__market_liquidations_identity.sql`（PK 必含 trade_id idempotency baseline）
- **WS topic helper**：`rust/openclaw_engine/src/multi_interval_topics.rs`（`public_trade_topic()` / `orderbook_topic()` 既有函數）
- **WS parser**：`rust/openclaw_engine/src/ws_client/parsers.rs`（既有 publicTrade / orderbook.50 解析能力）
- **FA 2026-05-20 P2-ENTRY-CLOSE-MAKER analysis EVID-1**：本 ADR 起源（FA 報告位置由 FA workspace 提供）
- **ADR-0010**：TimescaleDB hypertable + Guard migrations 範式
- **ADR-0021**：Alpha Source Architecture Upgrade R-1（下游 enabler）
- **ADR-0023**：SourceAvailability schema（同 alpha surface upgrade 鏈條）
- **`feedback_v_migration_pg_dry_run.md`**：V### migration PG dry-run mandatory（本 ADR 後續 IMPL 階段強制）
- **`project_hardware_constraints`**：4-8GB PG shared_buffers 強約束

## Sign-off

| Role | Source | Date | Status |
|---|---|---|---|
| Operator | 主會話 PM dispatch via 2026-05-20 FA P2-ENTRY-CLOSE-MAKER analysis EVID-1 closure | 2026-05-21 | 🟡 PROPOSED-pending-MIT-cross-review |
| PA | 本文件作者（EVID-1 ADR 起草） | 2026-05-21 | ✅ Drafted (Proposed) |
| FA | 2026-05-20 P2-ENTRY-CLOSE-MAKER analysis EVID-1 提出 ADR 訴求 | 2026-05-20 | ✅ ORIGINATING |
| MIT | Storage budget + sample rate calibration（OQ-1 / OQ-3 / OQ-4） | TBD | 🟡 PENDING |
| QC | Replay fidelity uplift 驗證 + 三引擎影響（OQ-4 dual-write） | TBD | 🟡 PENDING |
| BB | Bybit WS subscription quota + topic 接線（OQ-2） | TBD | 🟡 PENDING |
| PM | MIT + QC + BB review 完成後 promote 至 Accepted；可能 ADR-0029 補件或 ADR-0030/0031 拆分 Track A/B | TBD | 🟡 PENDING |

---

*OpenClaw / Arcane Equilibrium ADR-0029 — market.public_trades + market.orderbook_l2_snapshot Storage Policy (Proposed)*
