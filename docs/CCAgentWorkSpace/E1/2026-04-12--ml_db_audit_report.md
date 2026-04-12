# ML/DB 基礎設施審計報告
# ML/DB Infrastructure Audit Report
# 日期 / Date: 2026-04-12
# 審計員 / Auditor: MIT (ML Infrastructure / Database Engineer)

---

## 一、總結 / Executive Summary

資料庫 schema 設計為 **A 級** — 8 schema、35+ 表、完整索引、TimescaleDB 壓縮/保留策略、sync_commit 分層均已到位。ML 管線代碼基座 **完備但未端到端運行** — LightGBM/Optuna/CPCV/LinUCB/Thompson Sampling/Claude Teacher 全部有實現，但缺乏實際訓練數據積累和真實模型。**最大阻塞**：V001-V015 DDL 遷移文件標記為 "DRAFT — 尚未執行"（V006 除外，已執行），ML 管線的持久化路徑依賴這些表。2026-04-10 修復 session 已完成接線工作（FeatureCollector、Connection Pool、Parquet ETL），但 DDL 執行狀態仍不確定。

Database schema design is **A-tier** — 8 schemas, 35+ tables, complete indexing, TimescaleDB compression/retention, sync_commit tiering all in place. ML pipeline code base is **complete but not end-to-end operational** — LightGBM/Optuna/CPCV/LinUCB/Thompson Sampling/Claude Teacher all implemented, but lack actual training data accumulation and real models. **Biggest blocker**: V001-V015 DDL migration files marked "DRAFT — not yet executed" (except V006), and ML pipeline persistence paths depend on these tables. The 2026-04-10 remediation session completed wiring work but DDL execution status remains uncertain.

---

## 二、資料庫審計 / Database Audit

### 2.1 Schema 結構總覽 / Schema Structure Overview

```
PostgreSQL Database: trading_ai
├── market (11 tables)     — 市場數據：tickers/klines/OB/funding/OI/LSR/liquidations/regime/news
├── trading (9 tables)     — 交易：context/outcomes/signals/intents/verdicts/orders/state_changes/fills/positions
├── agent (3 tables)       — Agent：messages/ai_invocations/state_changes
├── learning (15+ tables)  — 學習：RL/promotion/suggestions/registry/posteriors/CPCV/JS/clusters/
│                            teacher/executions/experiment_ledger/linucb_state/budget/usage/
│                            foundation_model/weekly_review
├── features (2 tables)    — 特徵：online_latest/versions
├── observability (6 tables) — 監控：scorer_predictions/model_performance/drift/baselines/DQ/engine_events
├── risk (3 tables)        — 風險：black_swan_events/votes/correlation_pairs
├── news (reserved)        — 預留
└── public (legacy 11 + views 11) — Grafana 橋接 VIEW + _legacy 表
```

**遷移文件**：V001-V015 共 15 個 SQL 遷移，覆蓋完整。

### 2.2 索引評估 / Index Assessment — Grade: A

**V005 定義了完整索引策略**：

| 類別 / Category | 索引數量 / Count | 設計質量 / Quality |
|-----------------|------------------|--------------------|
| PK (含 TimescaleDB 時間列) | 35+ | **優秀** — 所有 hypertable PK 含 ts 列 |
| `(symbol, ts DESC)` 時間範圍查詢 | 12 | **優秀** — 覆蓋所有高頻查詢 |
| `ts DESC` 單列快速最新查詢 | 10 | **良好** — 高頻表精簡，減少寫入放大 |
| GIN (JSONB) | 2 | **合理** — 只在 decision_context_snapshots |
| Partial indexes | 3 | **優秀** — `WHERE is_active=TRUE`、`WHERE linucb_arm_id IS NOT NULL`、`WHERE outcome_computed_at IS NULL` |
| Composite indexes | 5+ | **良好** — strategy+symbol、decision_type+ts 等 |
| V015 engine_mode 索引 | 8 | **優秀** — 三引擎模式隔離 |

**發現的問題**：
- **無 N+1 風險**：Rust 端全部批量寫入（`QueryBuilder::push_values()`），Python 端走連接池
- **無缺失索引**：常用查詢模式（symbol+ts、strategy+ts、engine_mode+ts）均已覆蓋
- **潛在冗餘**：`idx_market_tickers_ts_desc` 與 PK `(symbol, ts)` 部分重疊，但 TimescaleDB 場景下 ts DESC 單列索引仍有價值（跨 symbol 最新查詢）

### 2.3 外鍵與約束 / Foreign Keys & Constraints — Grade: B+

**設計決策**：TimescaleDB hypertable **不支持外鍵**，因此採用「邏輯 FK + 應用層 CHECK」模式。

| 約束類型 / Type | 數量 / Count | 評價 / Assessment |
|-----------------|-------------|-------------------|
| CHECK constraints | 3 | `news_signals.severity BETWEEN 0 AND 1`、`sentiment`、`confidence` |
| 真實 FK | 2 | `directive_executions → teacher_directives`、`linucb_migrations.rollback_to` |
| 邏輯 FK (文檔化) | 15+ | `context_id` 跨表關聯、`intent_id`、`order_id` 等 |
| UNIQUE constraints | 2 | `model_registry(model_name, version)`、`feature_baselines(symbol, feature_name, valid_from)` |

**風險點**：
- 邏輯 FK 無資料庫級強制，依賴應用層正確性。但考慮 TimescaleDB 限制，這是正確的設計決策
- `trading.decision_outcomes.context_id` 與 `decision_context_snapshots.context_id` 無 FK — 合理（hypertable）

### 2.4 資料保留策略 / Data Retention — Grade: A

**V006 定義了完整的壓縮+保留策略**（已執行）：

| 資料類別 / Category | 壓縮間隔 / Compress | 保留期限 / Retain | 設計合理性 |
|--------------------|---------------------|-------------------|-----------|
| 高頻市場（tickers/OB/trades） | 7d | 90d | **合理** — 50MB/day |
| K 線 | 14d | 365d | **合理** — 回測需要 |
| Funding/OI/LSR | N/A | 180d | **合理** |
| 信號/意圖 | 2d (signals), 14d (intents) | 180d | **合理** — DB-RUN-7 特殊處理 signals |
| 成交/訂單 | 14d | 365d | **合理** — 審計+學習需要 |
| 監控 | N/A | 90d | **合理** — 可再生 |

**DB-RUN-7 特別修復**：`trading.signals` chunk 從 7 天縮到 1 天 + 2 天壓縮，配合寫入節流解決 19GB 未壓縮問題。

### 2.5 synchronous_commit 驗證 / sync_commit Verification — Grade: A

```sql
-- Database default (V006:90)
ALTER DATABASE trading_ai SET synchronous_commit = 'on';

-- Table-level tiering via COMMENT hint:
-- sync_commit=on:  trading.fills, trading.orders (CRITICAL — 不可丟失)
-- sync_commit=off: market.market_tickers, ob_snapshots, trade_agg_1m, trading.signals (高頻可再生)
```

**評價**：分層正確。關鍵交易數據（fills/orders）強一致，高頻市場數據允許丟失。應用層需讀取 COMMENT 並設置 session 級 sync_commit。

### 2.6 連接池配置 / Connection Pool — Grade: B+

**Rust 端（sqlx PgPool）**：
- `pool_max_connections: 20`（預設）
- `pool_min_connections: 2`（預設）
- `acquire_timeout: 5000ms`
- `DbPool` wrapper 帶失敗追蹤和優雅降級
- 無 PG 時引擎正常運行（pool = None，寫入靜默跳過）

**Python 端（psycopg2）**：
- ✅ 2026-04-10 新增 `db_pool.py`：`ThreadedConnectionPool(min=2, max=10)`
- ✅ Dashboard/API 路由已遷移到連接池
- ✅ ML 訓練腳本保持獨立 `psycopg2.connect()`（batch job，正確設計）
- ✅ `/api/v1/health/db` 健康探測端點已加

**改進建議**：
- Rust pool_max_connections=20 對三引擎場景可能偏多（3 engine × 多 writer task），建議監控 `pg_stat_activity` 確認實際使用量

---

## 三、ML 基座達標檢驗 / ML Infrastructure Readiness

### 3.1 特徵提取管線 / Feature Extraction Pipeline — Grade: A-

**已實現**：
- **34 維特徵向量**（`feature_collector.rs`）：16 指標扁平化
  ```
  sma_20, sma_50, ema_12, ema_26, rsi_14, macd, macd_signal, macd_histogram,
  bb_upper/middle/lower/bandwidth/percent_b, atr_14/14_percent, atr_5/5_percent,
  stoch_k/d, kama/kama_efficiency, adx/plus_di/minus_di, hurst, regime_id,
  ewma_vol, vol_regime_id, volume_ratio, donchian_upper/lower/middle/width, price
  ```
- **Ring buffer**：VecDeque 3000 容量（~5 分鐘 in-memory）
- **DB 持久化**：`features.online_latest` UPSERT（per symbol × timeframe）
- **漂移檢測**：PSI + ADWIN，寫入 `observability.drift_events`

**2026-04-10 修復後狀態**：
- ✅ FeatureCollector → mpsc channel → feature_writer 全鏈路已接通
- ✅ tick_pipeline `try_send(snap)` 非阻塞派發
- ⚠️ 需確認 `features.online_latest` 表已在 DB 中創建

### 3.2 訓練數據可用性 / Training Data Availability — Grade: B-

**已寫入 DB 的數據**：

| 數據類型 | 寫入器 | 狀態 |
|---------|--------|------|
| `trading.fills` | Rust `trading_writer.rs` | ✅ 運行中 |
| `trading.signals` | Rust `trading_writer.rs` | ✅ 運行中（DB-RUN-1 節流） |
| `trading.intents` | Rust `trading_writer.rs` | ✅ 運行中 |
| `trading.decision_context_snapshots` | Rust `context_writer.rs` | ✅ 運行中 |
| `market.*` (klines/tickers/etc) | Rust `market_writer.rs` | ✅ 運行中 |
| `features.online_latest` | Rust `feature_writer.rs` | ✅ 2026-04-10 接通 |
| `trading.decision_outcomes` | **無 writer** | ❌ **關鍵缺失** |
| `trading.orders` / `order_state_changes` | **無 writer** | ❌ 中等缺失 |

**最大問題**：`trading.decision_outcomes`（5 個回報窗口 1m/5m/1h/4h/24h + max favorable/adverse excursion）**無 backfill writer**。這是 `learning.scorer_training_features` VIEW 的核心 JOIN 目標 — 沒有 outcomes，ML 訓練 VIEW 的 `WHERE outcome_backfilled = TRUE` 永遠返回空集。

### 3.3 模型服務基礎設施 / Model Serving Infrastructure — Grade: B

**三級降級鏈**（`ml/scorer.rs`）：
1. **Tier 1**: ONNX 模型 → `OnnxModelManager` → `predict(features)` → calibrated_prob
2. **Tier 2**: 無 ONNX → 規則推理（signal confidence 直透）
3. **Tier 3**: 規則失敗 → 固定 confidence = 0.5

**模型部署路徑**：
```
LightGBM 訓練 → scorer_trainer.py → model.pkl
                → onnx_exporter.py → model.onnx (deferred)
                → learning.model_registry (DB row)
Rust 加載 → OnnxModelManager::load(onnx_path) → ArcSwap 熱交換
```

**當前狀態**：Tier 2/3 降級運行，無真實 ONNX 模型。ONNX 導出代碼存在但 `ort` crate 整合推遲。

### 3.4 EvolutionEngine 狀態 / EvolutionEngine Status — Grade: C+

**定位**：Python 離線工具，非 Rust 引擎組件。

**功能**：
- 網格搜索策略參數空間（`ParameterGrid`）
- 使用 `BacktestEngine` 作為評估函數
- `max_combinations` 上限 50（防資源耗盡）
- 結果可注入 `TruthSourceRegistry`

**問題**：
- ⚠️ BacktestEngine 本身是否準確（PNL-FIX-1/2 揭露所有策略 gross edge 為負）
- ⚠️ 不在 Rust 中，不參與實時推理
- ⚠️ W21 決策：保留用於 DL/AI agent 學習，與 PromotionPipeline 分工明確

### 3.5 Teacher-Student 架構 / Teacher-Student Architecture — Grade: B+

**Claude Teacher（Rust，Phase 4）**：
- ✅ `claude_teacher/` 完整模組：client / parser / writer / applier / consumer_loop / outcome_tracker / governance_impl / strategy_ipc_impl
- ✅ LLM 抽象：`LlmClient` trait（AnthropicClient + MockClient）
- ✅ BudgetTracker fail-closed 成本閘
- ✅ PG 持久化：`learning.teacher_directives` + `learning.experiment_ledger`
- ✅ Directive 成效追蹤：`outcome_tracker.rs` 多窗口 PnL + Sharpe
- ⚠️ 真實 Anthropic API 調用需 `ANTHROPIC_API_KEY`，dev 環境不觸發

**Student 側**：
- 策略通過 IPC 接收 directive 並調整參數
- `strategy_ipc_impl.rs` + `governance_impl.rs` 確保治理合規

### 3.6 LightGBM 整合 / LightGBM Integration — Grade: B

**已實現**：
- `scorer_trainer.py`：完整 LightGBM regression 訓練器
  - 預測目標：ATR 歸一化 PnL
  - 支持 CPCV 驗證路徑 + legacy 80/20 split
  - Feature importance 輸出
- `cpcv_validator.py`：4-fold CPCV + per-strategy embargo（24h/4h/8h/72h）
- `calibration.py`：Platt/isotonic 校準（placeholder）
- `onnx_exporter.py`：LightGBM → ONNX 導出

**未實現**：
- ❌ 無真實訓練數據跑過完整管線
- ❌ ONNX 導出整合推遲
- ❌ 校準尚為 placeholder

### 3.7 Optuna 超參數調優 / Optuna HPO — Grade: B

**已實現**：
- `optuna_optimizer.py`：TPE 策略參數優化
  - JournalFileStorage（非 PG，E5-O4 審計決策）
  - 結果寫入 `learning.ml_parameter_suggestions`
  - 獨立 psycopg2 連接（batch job）
- 兩層優化：Layer 1 = Optuna TPE，Layer 2 = Thompson Sampling

**未實現**：
- ❌ 無自動調度（需手動觸發或 cron）
- ❌ Optuna → IPC → Rust hot-reload 路徑未完成

---

## 四、ML 部署階段評估 / ML Deployment Stage Assessment

| 階段 / Stage | 狀態 | 詳細 / Detail |
|-------------|------|---------------|
| **數據收集 / Data Collection** | ✅ | Rust engine 實時寫入 fills/signals/intents/context/market data。market_writer 7 類型批量刷新 |
| **特徵工程 / Feature Engineering** | ✅ | 34-dim feature vector（16 指標），FeatureCollector → DB UPSERT。PSI/ADWIN 漂移檢測 |
| **模型訓練管線 / Model Training Pipeline** | ⚠️ 部分 | LightGBM scorer + CPCV 驗證代碼完備。**阻塞**：decision_outcomes 無 backfill → scorer_training_features VIEW 空 |
| **模型評估 / Model Evaluation** | ⚠️ 部分 | CPCV 框架 + power estimation 已實現。Brier score / calibration error 表已建但無數據 |
| **線上服務 / Online Serving** | ⚠️ 部分 | 3-tier Scorer（ONNX→rule→fixed）框架就緒。OnnxModelManager ArcSwap 熱交換設計好。無真實 ONNX 模型 |
| **A/B 測試 / A/B Testing** | ⚠️ 部分 | DL-3 Foundation Model A/B runner（`dl3_ab_runner.py`）+ Go-No-Go 決策框架。LinUCB shadow compare 工具 |
| **持續學習 / Continuous Learning** | ❌ | Thompson Sampling posteriors 更新代碼有但未自動化。Outcome backfill 不存在。EvolutionEngine 是離線工具非自動化循環 |

### 階段總評 / Overall ML Stage Rating

```
╔══════════════════════════════════════════════════════════════╗
║  ML Maturity Level:  STAGE 2 of 7 — Feature Engineering    ║
║  ────────────────────────────────────────────────────────── ║
║  ✅ Stage 1: Data Collection        — OPERATIONAL          ║
║  ✅ Stage 2: Feature Engineering     — OPERATIONAL          ║
║  ⚠️ Stage 3: Model Training Pipeline — CODE COMPLETE,       ║
║                                        DATA BLOCKED         ║
║  ⚠️ Stage 4: Model Evaluation        — FRAMEWORK ONLY      ║
║  ⚠️ Stage 5: Online Serving          — DEGRADED (Tier 2/3) ║
║  ⚠️ Stage 6: A/B Testing            — TOOLING EXISTS       ║
║  ❌ Stage 7: Continuous Learning     — NOT OPERATIONAL      ║
╚══════════════════════════════════════════════════════════════╝
```

---

## 五、數據完整性 / Data Pipeline Integrity

### 5.1 市場數據 → DB 寫入路徑

```
Bybit WS (public)
  └→ tick_pipeline.rs (on_tick)
       ├→ KlineManager (bar close) ─→ MarketDataMsg::KlineClose ─→ mpsc ─→ market_writer ─→ market.klines
       ├→ 5s timer ─→ MarketDataMsg::TickerSnapshot ─→ mpsc ─→ market_writer ─→ market.market_tickers
       ├→ 1m timer ─→ MarketDataMsg::ObSnapshot ─→ mpsc ─→ market_writer ─→ market.ob_snapshots
       ├→ 1m timer ─→ MarketDataMsg::TradeAgg1m ─→ mpsc ─→ market_writer ─→ market.trade_agg_1m
       └→ regime change ─→ RegimeSnapshot/Transition ─→ mpsc ─→ market_writer ─→ market.regime_*

Bybit REST (poller, 5-15m)
  └→ rest_poller.rs
       ├→ FundingRate ─→ market.funding_rates
       ├→ OpenInterest ─→ market.open_interest
       └→ LongShortRatio ─→ market.long_short_ratio
```

**狀態**：✅ 全部接通，批量刷新（`batch_flush_interval_ms: 2000ms`），JSONL fallback on PG failure。

### 5.2 Fill/Order → DB 寫入路徑

```
IntentProcessor (signal → intent → risk → execute)
  └→ TradingMsg::Fill ─→ mpsc ─→ trading_writer ─→ trading.fills
  └→ TradingMsg::Signal ─→ mpsc ─→ trading_writer ─→ trading.signals
  └→ TradingMsg::Intent ─→ mpsc ─→ trading_writer ─→ trading.intents
  └→ TradingMsg::RiskVerdict ─→ mpsc ─→ trading_writer ─→ trading.risk_verdicts
  └→ TradingMsg::PositionSnapshot ─→ mpsc ─→ trading_writer ─→ trading.position_snapshots

  ❌ TradingMsg::Order → trading.orders       (writer code exists, OMS state machine gap)
  ❌ TradingMsg::OrderStateChange → trading.order_state_changes (same)
```

**關鍵問題**：
- `trading.orders` 和 `order_state_changes` 有 writer code 但 OMS 生命週期管理未完成
- `engine_mode` 欄位（V015）已加入所有寫入消息，三引擎數據正確隔離

### 5.3 特徵計算 → 存儲

```
tick_pipeline → IndicatorEngine → IndicatorSnapshot
  └→ FeatureCollector.capture(snapshot) → FeatureSnapshot
       └→ mpsc::try_send() → feature_writer → features.online_latest (UPSERT)

  └→ DecisionContextMsg.indicators_snapshot (JSONB)
       └→ context_writer → trading.decision_context_snapshots

  ❌ decision_outcomes backfill — 完全缺失
  ❌ features.history — 刻意不建（DB-RUN-4 決策：歷史走 context JSONB）
```

### 5.4 快照持久化 / Snapshot Persistence

```
Rust 引擎狀態快照：
  paper_state.json / pipeline_snapshot_{paper,demo,live}.json
  └→ 本地 JSON 文件（per-engine 隔離，commit c9d9bc5 修復）

ConfigStore 補丁審計：
  └→ observability.engine_events (IPC handler 寫入)

Reconciler 狀態：
  └→ observability.engine_events (reconciler 審計行)
  └→ Arc<AtomicU8> shared risk level (in-memory)
```

---

## 六、關鍵問題與建議 / Critical Issues & Recommendations

### P0 — 阻塞 ML 訓練的關鍵問題

| # | 問題 | 影響 | 建議修復 |
|---|------|------|----------|
| **DB-1** | V001-V004 DDL 標記 "DRAFT — 尚未執行" | ML 持久化全部阻塞 | **確認並執行所有 DDL**（V006 以外的遷移） |
| **ML-1** | `trading.decision_outcomes` 無 backfill writer | `scorer_training_features` VIEW 永遠空集 | 實現 outcome backfill job（定時掃描 fills，計算 1m/5m/1h/4h/24h 回報窗口） |
| **ML-2** | 所有策略 gross edge 為負（PNL-FIX-1/2） | 即使 ML 管線通暢，訓練出的模型也學到負 edge 信號 | **Phase 5 PAUSED 正確** — 先修策略再跑 ML |

### P1 — 重要但不阻塞

| # | 問題 | 影響 | 建議修復 |
|---|------|------|----------|
| **DB-2** | `trading.orders` / `order_state_changes` 無 writer | 訂單生命週期不可重建 | 接通 Rust OMS → trading_writer |
| **ML-3** | ONNX 導出/加載推遲 | Scorer 降級運行（Tier 2/3） | 待有正 edge 策略後實現 |
| **ML-4** | Calibration 為 placeholder | 模型概率無校準 | 待模型訓練完成後實現 |
| **DB-3** | Python ML scripts 用獨立 `psycopg2.connect()` | Batch job 正確但無超時重試 | 可接受，加超時即可 |

### P2 — 改進建議

| # | 問題 | 建議 |
|---|------|------|
| **DB-4** | `pool_max_connections=20` 三引擎場景偏多 | 監控 `pg_stat_activity` 後調整 |
| **ML-5** | Thompson Sampling posteriors 更新未自動化 | 待策略有正 edge 後實現定時更新 |
| **ML-6** | LinUCB warm-start migration (4-06) 未實現 | 待 v1_15 arm 積累足夠數據 |
| **DB-5** | Grafana VIEW 橋接部分指向 `_legacy` 表 | Phase 0b 遷移完成後改指新表 |

---

## 七、ML 管線代碼清單 / ML Pipeline Code Inventory

### Python ML 模組（`program_code/ml_training/`）

| 文件 | 功能 | 行數(估) | 狀態 |
|------|------|----------|------|
| `scorer_trainer.py` | LightGBM CPCV 訓練 | ~250 | ✅ 可運行 |
| `cpcv_validator.py` | 4-fold CPCV + embargo | ~360 | ✅ 可運行 |
| `optuna_optimizer.py` | TPE 超參數優化 | ~600 | ✅ 可運行 |
| `thompson_sampling.py` | NIG Thompson Sampling | ~480 | ✅ 可運行 |
| `james_stein_estimator.py` | JS 跨幣 partial pooling | ~200 | ✅ 可運行 |
| `linucb_trainer.py` | LinUCB batch 重建 A/b | ~300 | ✅ 可運行 |
| `linucb_arm_migration.py` | Warm-start 遷移 | ~200 | ⚠️ Framework |
| `linucb_shadow_compare.py` | Shadow comparison | ~200 | ✅ 可運行 |
| `parquet_etl.py` | DuckDB PG→Parquet ETL | ~150 | ✅ 可運行 |
| `label_generator.py` | ATR-normalized PnL labels | ~150 | ✅ 可運行 |
| `calibration.py` | Platt/isotonic 校準 | ~100 | ⚠️ Placeholder |
| `onnx_exporter.py` | LightGBM → ONNX | ~100 | ⚠️ Deferred |
| `leakage_check.py` | Outcome leakage 防護 | ~100 | ✅ 可運行 |
| `dl3_foundation.py` | TimesFM/Chronos 推理 | ~280 | ✅ 可運行 |
| `dl3_ab_runner.py` | DL-3 A/B 比較 | ~450 | ✅ 可運行 |
| `dl3_go_no_go.py` | DL-3 Go/No-Go 決策 | ~200 | ✅ 可運行 |
| `run_training_pipeline.py` | 端到端編排 | ~170 | ✅ 可運行 |
| `weekly_report_generator.py` | 週度報告 | ~200 | ✅ 可運行 |
| `realized_edge_stats.py` | 邊際分析 | ~150 | ✅ 可運行 |
| `edge_cluster_analysis.py` | 聚類分析 | ~200 | ✅ 可運行 |

### Rust ML 模組

| 路徑 | 功能 | 狀態 |
|------|------|------|
| `ml/scorer.rs` | 3-tier Scorer | ✅ 運行中（Tier 2/3） |
| `ml/model_manager.rs` | ONNX ArcSwap 管理 | ✅ Framework ready |
| `ml/kelly_sizer.rs` | Kelly 倉位 | ✅ 運行中 |
| `linucb/` (5 files) | LinUCB 推理 + state IO | ✅ 運行中 |
| `claude_teacher/` (8 files) | Teacher pipeline | ✅ 運行中（Mock mode） |
| `ai_budget/` | 成本追蹤 + 預算 | ✅ 運行中 |
| `feature_collector.rs` | 34-dim 特徵 | ✅ 接通 |
| `database/drift_detector.rs` | PSI + ADWIN | ✅ 運行中 |
| `database/feature_writer.rs` | UPSERT online_latest | ✅ 接通 |
| `database/context_writer.rs` | Decision context | ✅ 運行中 |

---

## 八、結論 / Conclusion

### 資料庫：設計優秀，執行待確認

Schema 設計體現了深思熟慮的架構決策（TimescaleDB hypertable 分層、邏輯 FK 文檔化、壓縮/保留策略、sync_commit 分層）。索引覆蓋全面，無 N+1 風險。**唯一不確定**：V001-V004 DDL 是否已從 "DRAFT" 狀態執行到位。

### ML：代碼完備率 ~90%，可運行率 ~30%

ML 管線代碼量約 8500+ 行（Python）+ 3000+ 行（Rust），覆蓋從 ETL 到模型服務的完整鏈路。但受以下阻塞：

1. **DDL 執行不確定** → 持久化路徑可能不通
2. **decision_outcomes backfill 缺失** → 訓練 VIEW 空集
3. **所有策略 gross edge 為負** → 即使訓練也學到錯誤信號

**ML 到達 Stage 3（模型訓練）的前提**：
1. 確認 DDL 全部執行
2. 實現 decision_outcomes backfill
3. 至少一個策略達到正 gross edge

**ML 到達 Stage 5（線上服務）的前提**：
1. Stage 3 完成 + ONNX 導出可用
2. 模型通過 CPCV 驗證
3. OnnxModelManager 加載真實模型

---

*報告結束 / End of Report*
