# 融合工作方案 v0.5：DB + ML/DL + 新聞 Agent 統一實施計劃
# Unified Work Plan v0.5: DB + ML/DL + News Agent
# 狀態：兩輪審計 + DB 專題 + 四角色聯合驗證完成
# 日期：2026-04-04

---

## Context

三條獨立的設計線融合為一條可執行路線：
1. **DB-1**：數據存儲架構（JSON → TimescaleDB + Parquet）
2. **ML-1**：ML/DL Agent 自主學習架構（LightGBM + Optuna + DL×3）
3. **新聞 Agent**：外部情報採集 + 三層接入

交叉比對發現 DB-1 對 ML-1 覆蓋率僅 25%，需 **13 張新表 + 9 個新欄位**。

**前置文件：**
- DB 設計：`docs/references/2026-04-03--data_storage_architecture_optimal_draft_v0.1.md`
- ML/DL 架構：`docs/references/2026-04-03--ml_dl_learning_architecture_v0.4.md`
- 調參設計：`docs/references/2026-04-03--agent_param_tuning_design_draft_v0.2.md`
- DB 代碼審計：`docs/architecture/DATA_STORAGE_ARCHITECTURE_V1.md`

---

## 一、Schema 設計（第一輪審計修正版）

### 1.1 Schema 結構（8 個，合併 monitoring+quality → observability）

```
market       — 市場數據 + 新聞事件（外部世界）
trading      — 交易 + 決策數據
agent        — Agent 通信 + AI 調用
learning     — 學習系統 + 模型管理 + 實驗追蹤
features     — 特徵存儲 + 版本管理
observability — 數據質量 + 模型性能 + 漂移監控（合併 monitoring+quality）
risk         — 黑天鵝檢測 + 極端事件記錄
optuna       — Optuna 自管表（RDBStorage 自建）
```

### 1.2 新增 13 張表（審計後調整）

| Schema | 表名 | 用途 | Hyper? | 審計修正 |
|--------|------|------|--------|---------|
| **learning** | bayesian_posteriors | TS 後驗分佈 + 信任域 | 否(UPSERT) | — |
| **learning** | cpcv_results | CPCV 6-fold OOS 指標 | 否 | — |
| **learning** | james_stein_estimates | 跨幣部分池化 | 否(UPSERT) | — |
| **learning** | symbol_clusters | k-means 聚類 | 否 | — |
| **learning** | teacher_directives | Claude Learning Directive | **否（普通表）** | ★ 日均 0.14 行不該是 hypertable |
| **learning** | directive_executions | Directive 執行追蹤 | 否 | — |
| **observability** | scorer_predictions | Scorer 推理結果 | 是(1d) | — |
| **observability** | model_performance | Rolling Brier/AUC | 是(**7d**) | ★ 日均 50 行，改 7d chunk |
| **observability** | drift_events | PSI + AV + ADWIN | 是(1d) | — |
| **observability** | feature_baselines | 特徵分佈歷史基線 | 否(UPSERT) | ★ 增加 valid_from/valid_until 版本管理 |
| **market** | news_signals | 新聞事件 | 是(**7d**) | ★ 日均 5-20 行，改 7d chunk |
| **risk** | black_swan_events | 黑天鵝永久記錄 | **否（普通表）** | ★ 日均 0.01 行不該是 hypertable |
| **risk** | black_swan_votes | 4 信號投票 | 是(7d) | — |

**刪除 `learning.optuna_metadata`：** Optuna study 命名約定 `{strategy}_{symbol}_{regime}` 即可查詢，無需額外映射表。

### 1.3 現有表新增欄位（9 個）

| 表 | 新欄位 | 類型 | 用途 | 審計修正 |
|----|--------|------|------|---------|
| trading.decision_context_snapshots | `news_severity` | REAL | 近 24h 最高新聞嚴重度 | — |
| 同上 | `hours_since_last_major_news` | REAL | 距上次重大新聞小時數 | — |
| 同上 | `news_driven` | BOOLEAN | 歸因標籤 | — |
| 同上 | `scorer_ev_prediction` | REAL | Scorer 預測值 | — |
| 同上 | `scorer_divergence` | REAL | 多 Scorer 分歧度 | — |
| learning.model_registry | `calibration_params` | JSONB | **isotonic regression 參數** | ★ Platt→isotonic |
| 同上 | `onnx_artifact_path` | TEXT | ONNX 路徑 | — |
| features.online_latest | `foundation_model_features` | REAL[] | 時序基礎模型特徵 | — |
| market.news_signals | `severity_source` | TEXT | 產出 severity 的 AI 模型 | ★ 跨模型校準用 |

### 1.4 Decision Context Snapshot 改為混合方案（審計 PA-2 修正）

原方案 ~80 欄位全扁平化 → 改為混合：
```sql
-- ~15 核心查詢欄位扁平化（WHERE/JOIN/GROUP BY 常用）
ts, context_id, decision_type, symbol, strategy_name,
last_price, mark_price, spread_bps,
regime_5m, regime_1h, ind_5m_adx, ind_5m_rsi, ind_5m_atr_14_pct,
position_side, position_qty, total_equity, drawdown_pct,
news_severity, hours_since_last_major_news, news_driven,
scorer_ev_prediction, scorer_divergence,

-- 其餘放 JSONB（特徵增減不需要 ALTER TABLE）
indicators_snapshot JSONB,    -- 全 TF 所有指標
microstructure JSONB,         -- orderbook + funding + OI
position_detail JSONB,        -- 完整持倉狀態
recent_sequences JSONB,       -- REAL[60] 序列數據
decision_payload JSONB,       -- 決策本身

-- 事後回填
outcome_returns JSONB,        -- {1m, 5m, 15m, 1h, 4h, 24h 的 return}
outcome_extremes JSONB,       -- {max_favorable, max_adverse, regime_1h, vol_1h}
outcome_backfilled BOOLEAN DEFAULT FALSE
```
優勢：核心查詢性能不變 + 特徵增刪不需 ALTER TABLE + JSONB GIN 索引支持靈活查詢。

### 1.5 Hypertable FK 處理（審計 QA-1 修正）

TimescaleDB hypertable 不支持外鍵約束。改為：
- **應用層 CHECK**：寫入時驗證 FK 存在性
- **文檔化**：所有邏輯 FK 記錄在 schema 文檔中
- **週度一致性檢查** cron：掃描孤立記錄

### 1.6 sync_commit 分層策略（審計 QA-3 修正）

```sql
-- 全局設置：off（高吞吐）
SET synchronous_commit = 'off';

-- critical 表寫入時覆蓋為 on：
-- trading.orders, trading.fills → Live 階段必須 sync_commit='on'
-- 實現：per-session SET LOCAL synchronous_commit = 'on'
```

Demo/Paper 階段：全部 off（最壞丟 ~3s 可接受）。
Live 階段：orders/fills 改 on，其餘保持 off。

### 1.7 ETL 歸檔表清單（審計 QA-5 修正）

每日 02:00 UTC ETL 歸檔以下表到 Parquet：
```
market.raw_ticks          → parquet/market/ticks/YYYY-MM-DD/
market.orderbook_l2       → parquet/market/orderbook/YYYY-MM-DD/
market.public_trades      → parquet/market/trades/YYYY-MM-DD/
market.indicators         → parquet/market/indicators/YYYY-MM-DD/  ★ 必須歸檔
trading.decision_context  → parquet/trading/contexts/YYYY-MM-DD/
trading.signals           → parquet/trading/signals/YYYY-MM-DD/
```

### 1.8 feature_baselines 版本管理（審計 QA-10 修正）

```sql
CREATE TABLE observability.feature_baselines (
    baseline_id     SERIAL PRIMARY KEY,
    symbol          TEXT NOT NULL,
    feature_name    TEXT NOT NULL,
    bin_edges       REAL[] NOT NULL,
    bin_counts      INT[] NOT NULL,
    valid_from      TIMESTAMPTZ NOT NULL,    -- ★ 新增
    valid_until     TIMESTAMPTZ,             -- ★ 新增，NULL=當前有效
    created_ts      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(symbol, feature_name, valid_from)
);
```
重建策略：每季度用最近 6 個月 rolling 分位數重建 bin_edges。

### 1.9 跨幣相關性矩陣（審計 QA-9 修正）

50×50 = 2500 REAL = ~10KB/行。數據量極小，**直接存 PG**：
```sql
CREATE TABLE risk.correlation_snapshots (
    ts              TIMESTAMPTZ PRIMARY KEY,
    matrix          REAL[] NOT NULL,         -- flatten 50x50 = 2500 elements
    symbols_order   TEXT[] NOT NULL,          -- 矩陣的 symbol 順序
    method          TEXT DEFAULT 'pearson'
);
```
不再用 Parquet 文件路徑。

---

## 二、ML/DL 技術修正（第一輪審計）

### 2.1 Signal Quality Scorer 標籤修正（CRITICAL MIT-1）

**問題：** y = net_pnl / ATR 在 ATR→0 時爆炸。

**修正：**
```python
ATR_FLOOR = {
    'BTCUSDT': 50.0,    # $50 最小合理 ATR
    'ETHUSDT': 5.0,
    'default': entry_price * 0.001  # 0.1% 作為兜底
}
Y_MAX = 5.0  # 最多 5 倍 ATR

y = clip(net_pnl / max(atr, ATR_FLOOR[symbol]), -Y_MAX, Y_MAX)

# 訓練時檢查：
if skewness(y) > 3 or kurtosis(y) > 20:
    use_huber_loss = True  # 替代 L2
```

### 2.2 校準方法修正（HIGH MIT-2）

**問題：** Platt scaling 是分類器校準方法，不適用於回歸模型。

**修正：** 改為 **isotonic regression**（non-parametric，適合連續值）。
- 將 LightGBM 回歸輸出轉為二元分類（y > 0 → profitable）
- 用 isotonic regression 校準 predicted probability
- 校準必須用 CPCV 的 OOS folds，絕不用 in-sample
- 驗證：Expected Calibration Error (ECE) < 0.05

### 2.3 TPE + Thompson Sampling 分層（HIGH MIT-4）

**問題：** TPE 和 TS 是兩種不同的 BO 策略，不能混用。

**修正：** 明確兩層分離：
```
Layer 1 — Within-strategy 參數優化（Optuna TPE）
  輸入：一個 (strategy, symbol, regime) 的交易歷史
  輸出：最優參數配置
  方法：TPE（Expected Improvement）

Layer 2 — Across-strategy 資源分配（Thompson Sampling）
  輸入：所有 (strategy, symbol, regime) pair 的歷史表現
  輸出：下一個 trial 分配給哪個 pair
  方法：Thompson Sampling on Normal-InverseGamma posterior
  （Optuna trial outcome 是連續值，不是二元，所以用 NIG 不用 Beta）
```

Optuna study 命名：`{strategy}_{symbol}_{regime}`。TS 維護每個 study 的 NIG posterior。

### 2.4 CPCV Embargo 分級（HIGH MIT-5）

**問題：** Embargo 未區分 purge 和 embargo，未按策略分級。

**修正：**
```
Purge = 移除 label 覆蓋跨 fold 邊界的樣本
Embargo = 額外安全緩衝

按策略分級：
  趨勢（MA/Breakout）: embargo = 24h（持倉 12-72h，outcome 用 24h return）
  回歸（BB Reversion）: embargo = 4h（持倉 1-8h）
  套利（Funding Arb）: embargo = 8h（跨 funding period）
  網格（Grid）: embargo = 72h（持倉可達數天）

6-fold CPCV + 24h embargo 的有效樣本損失：
  5 edges × 24h × 2 sides = 240h ≈ 10 天
  6 個月數據（180 天）→ 損失 5.5%，可接受
```

### 2.5 ONNX 熱加載線程安全（CRITICAL MIT-10）

**問題：** tick pipeline 是 sole-owner 無鎖設計，RwLock 會打破此設計。

**修正：** 使用 `ArcSwap<ort::Session>`：
```rust
use arc_swap::ArcSwap;

pub struct OnnxScorer {
    session: ArcSwap<Option<ort::Session>>,  // 原子指標交換
    model_version: AtomicU64,
}

impl OnnxScorer {
    // tick 路徑：原子讀取，~1ns，零鎖
    pub fn predict(&self, features: &[f32]) -> Option<f32> {
        let guard = self.session.load();
        guard.as_ref().map(|s| s.run(features))
    }
    
    // 後台線程：原子替換，舊 session 由 Arc 引用計數自動釋放
    pub fn hot_reload(&self, path: &Path) -> Result<()> {
        let new_session = ort::Session::new(path)?;
        self.session.store(Arc::new(Some(new_session)));
        Ok(())
    }
}
```
- 推理時 reload 不會 crash（atomic swap）
- 加載期間 1-2 tick 用 old model = 可接受的 staleness
- 加載失敗保留舊模型（fail-safe）
- `arc-swap` 已在現有依賴中

### 2.6 DL-3 時序基礎模型定位修正（HIGH PM-6 + MIT-9）

**問題：** 「零訓練成本」不準確，zero-shot 表現是假設非結論。

**修正：**
- DL-3 從 Phase 1 **移到 Phase 4**（實驗性質，不在 critical path）
- 推理 **不在 tick 路徑**，改為異步批次預測（每 5min 更新）
- Phase 4 必須做 A/B 驗證：含 vs 不含 foundation model 特徵的 Scorer AUC 差異 < 0.01 → 棄用
- 基線比較必須包含簡單替代：EMA 預測殘差 + historical volatility
- GPU 需求：TimesFM 需 ~2GB GPU RAM，CPU 推理 1-5s（只能異步）

### 2.7 現有模組處置策略（HIGH PA-5）

| 模組 | 處置 | 理由 |
|------|------|------|
| EvolutionEngine | Phase 3 後標記 deprecated | Optuna TPE 取代其 grid search |
| DreamEngine | 保留，不接線 | Monte Carlo 概念可取但搜索空間不對，未來可能重新設計 |
| CognitiveModulator | 保留作 L0 快速調製 | 與 ML Scorer（L1）並行不衝突，提供 <1ms 的壓力反應 |

### 2.8 teacher_directives 融入 ExperimentLedger（HIGH PA-6）

**問題：** teacher_directives 與 ExperimentLedger/TruthSourceRegistry 語義重疊。

**修正：**
- Claude 的 Learning Directive 作為 ExperimentLedger 的 `source_type = 'claude_teacher'`
- Directive → ExperimentLedger hypothesis → 驗證 → TruthSourceRegistry claim
- `learning.teacher_directives` 表保留用於存儲 Claude API 的原始結構化輸出（audit trail）
- 但執行追蹤走 ExperimentLedger 的既有流程，不另立系統
- Claude 輸出永遠不能標記為 FACT（原則 #10 認知誠實）

### 2.9 Adversarial Validation 閾值校準（MEDIUM MIT-6）

**修正：** 不硬編碼 0.6，改為數據驅動：
```
1. Permutation test：打亂時間標籤 100 次，計算 null AUC 分佈
2. 閾值 = null_95th_percentile + margin
3. 雙級：
   WARNING = null_95th + 0.03
   ALERT = null_95th + 0.06
```

### 2.10 ADWIN 參數校準（MEDIUM MIT-7）

**修正：**
- 起始 delta = 0.005
- 輸入：EMA-smoothed Brier score（不是 raw accuracy，太噪聲）
- 校準方法：在已知穩定期跑 ADWIN，調 delta 直到 false positive rate < 5%
- ADWIN 監控模型性能漂移，PSI 監控輸入特徵漂移（角色分離）

### 2.11 funding_cost 精確化（MEDIUM CROSS-2）

**修正：**
```
avg_funding_rate = 最近 3 期（24h）funding rate 均值
Funding Arb 策略：用當前實際 funding rate（不用均值）

funding_cost 精確計算：
  不用 ceil(t/8h)（不準確）
  改用 floor(funding_settlement_crossings(open_time, close_time))
  即：計算開倉到平倉之間實際跨越了幾次 funding settlement
```

### 2.12 ONNX 精度驗證要求（MEDIUM MIT-3）

Phase 2 ONNX PoC 必須包含：
- Python LightGBM predict vs Rust ONNX predict，1000+ 樣本逐一比較
- max absolute error < 1e-3
- 所有特徵顯式轉 f32，不依賴隱式轉換
- 不使用 LightGBM native categorical — 全部手動 one-hot encode
- NaN 處理在應用層做（填充 sentinel），不依賴 ONNX runtime NaN 行為

### 2.13 news_signals severity 跨模型校準（LOW QA-6）

- 增加 `severity_source TEXT` 欄位
- 週度校準：檢查不同 source 的 severity 分佈是否一致
- 保留連續值（ML 友好）

---

## 三、新聞 Agent Schema 設計（審計修正版）

### 表結構：`market.news_signals`

```sql
CREATE TABLE market.news_signals (
    signal_id       BIGSERIAL,
    ts              TIMESTAMPTZ NOT NULL,
    receive_ts      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source          TEXT NOT NULL,
    source_url      TEXT,
    severity        REAL NOT NULL CHECK (severity BETWEEN 0 AND 1),
    severity_source TEXT,                            -- ★ 產出 severity 的 AI 模型
    category        TEXT NOT NULL,
    affected_symbols TEXT[] NOT NULL DEFAULT '{}',
    is_market_wide  BOOLEAN DEFAULT FALSE,
    sentiment       REAL CHECK (sentiment BETWEEN -1 AND 1),
    confidence      REAL CHECK (confidence BETWEEN 0 AND 1),
    summary         TEXT NOT NULL,
    raw_content     TEXT,
    ai_model_used   TEXT,
    processing_cost_usd NUMERIC(10,6) DEFAULT 0,
    attributed_trade_count INTEGER DEFAULT 0,
    PRIMARY KEY (signal_id, ts)
);

SELECT create_hypertable('market.news_signals', 'ts',
       chunk_time_interval => INTERVAL '7 days');   -- ★ 7d chunk（日均 <20 行）
CREATE INDEX idx_news_severity ON market.news_signals (severity DESC, ts DESC);
CREATE INDEX idx_news_symbols ON market.news_signals USING GIN (affected_symbols);
-- 永久保留（年均 <100MB）
```

### 三層路由規則（不變）

```
severity >= 0.8 → Guardian + Regime Detector + Learning
severity 0.5-0.8 → Regime Detector + Learning
severity < 0.5 → Learning only
category == 'listing' → 新幣特殊處理（Global prior + 7 天加寬）
```

---

## 四、實施路線（審計修正版：20 週 + buffer）

### 核心修正（PM-1/PM-3）：
- 16 週 → **20 週**（每 Phase 後 0.5 週 buffer）
- Phase 0 **必須等 R-07 Go/No-Go（4/10）後開始**，最早 4/11
- Phase 3 拆分為 3a（update_params 改造）+ 3b（Optuna + TS）
- DL-3 從 Phase 1 移到 Phase 4（實驗性質）
- 引入遷移框架：版本化 SQL 文件 `V001__base_schemas.sql` 等

```
Phase 0  (W1-3,  4/11-4/30):  DB 基礎 + Schema + DDL
Phase 1  (W4-5,  5/01-5/14):  市場數據止血 + FeatureCollector + PSI
Phase 2  (W6-8,  5/15-6/04):  交易鏈 + Decision Context + Scorer + ONNX PoC
Phase 3a (W9-10, 6/05-6/18):  update_params() 改造（Python 5 策略 + Rust 5 策略）
Phase 3b (W11-12, 6/19-7/02): Optuna TPE + Thompson Sampling + CPCV + 黑天鵝
Phase 4  (W13-15, 7/03-7/23): Claude Teacher + LinUCB + 新聞接口 + DL-3 實驗
Phase 5  (W16-18, 7/24-8/13): James-Stein + DL-1 + DL-2
Phase 6  (W19-20, 8/14-8/27): 漸進放權 + 驗收 + 壓測 + 文檔

起算日：2026-04-11（R-07 Go/No-Go 後）
預計完成：2026-08-27
```

### Phase 0: DB 基礎（W1-3）

- 安裝 TimescaleDB（Docker image 切換：`timescale/timescaledb:latest-pg16`）
- pg_dump 備份現有數據
- CREATE 8 個 Schema + optuna schema
- 現有 11 表加 `_legacy` 後綴凍結
- 創建全部新表（DB-1 + ML 13 張 + news + correlation_snapshots）
- 版本化遷移文件：`migrations/V001__base_schemas.sql` ~ `V005__ml_tables.sql`
- 壓縮 + retention + PgBouncer
- **不建 ML 邏輯，只建空表**

### Phase 1: 市場數據止血 + ML 基礎（W4-5）

**DB：** klines / indicators / raw_ticks / regime → PG
**ML：** FeatureCollector（純記憶體 ring buffer + 異步 batch flush）+ PSI 漂移檢測
**依賴：** `requirements-ml.txt` 引入 scikit-learn + lightgbm（try/except 降級）

### Phase 2: 交易鏈 + Scorer（W6-8）

**DB：** signals / verdicts / messages / fills / orders / Decision Context（混合方案：15 欄位扁平 + JSONB）+ outcome 回填 cron
**ML：** LightGBM Scorer 訓練 + isotonic regression 校準 + TabPFN 基線 + ONNX 精度 PoC
**Rust：** ml_scorer.rs（ArcSwap + ort + notify）+ ONNX 推理整合

### Phase 3a: update_params 改造（W9-10）

**Python：** StrategyBase.update_params() + 5 子類實現（~3d） + 測試（~1.5d）
**Rust：** Strategy trait update_params + 5 實現（~3d） + 測試（~1.5d）
**總計 ~9 工作日**，獨立 Phase 確保不被擠壓

### Phase 3b: 參數優化 + 黑天鵝（W11-12）

**ML：** Optuna TPE（within-strategy）+ Thompson Sampling NIG（across-strategy）+ CPCV（分級 embargo）+ BH-FDR
**Grid：** 多目標 Pareto（Grid_Efficiency × Inventory_Risk_Ratio）
**Risk：** 黑天鵝 4 信號投票 → `risk.black_swan_events`（普通表永久保留）
**DB：** PG → Parquet 每日 ETL cron + DuckDB label 生成

### Phase 4: 整合層 + DL-3 實驗（W13-15）

**ML：** Claude-as-Teacher（Learning Directive → ExperimentLedger source_type='claude_teacher'）+ LinUCB + Model Performance 監控 + Adversarial Validation（permutation 校準閾值）
**News：** NewsSignal Pydantic + market.news_signals 寫入 + 三層路由 + mock fixture
**DL-3：** TimesFM/Chronos 部署（異步 5min 批次，不在 tick 路徑）+ A/B 驗證（AUC 提升 < 0.01 則棄用）

### Phase 5: 跨幣遷移 + DL（W16-18）

**ML：** James-Stein 部分池化 + k-means 聚類
**DL-1：** Symbol Embedding Autoencoder（4D/8D/12D 三版對比，Denoising）
**DL-2：** Regime LSTM Shadow 運行 vs 規則式 detector 對比

### Phase 6: 驗收（W19-20）

- 漸進放權管線
- 全管線回放測試
- 壓測：FeatureCollector < 0.1ms + PG 寫入不阻塞 tick + ONNX 推理 < 1ms
- Live 階段 sync_commit 策略驗證
- 文檔

---

## 五、開放項（全部已解決，見 §一~§二 各修正項）

| 原開放項 | 解決方案 | 對應節 |
|---------|---------|--------|
| 遷移策略 | 全新建 + 舊表凍結 | §四 Phase 0 |
| Optuna 隔離 | 同 DB 獨立 schema | §一 1.1 |
| 新聞數據源 | 暫緩，接口先行 | §三 |
| 模型存儲 | PG 元數據 + NVMe + NAS | §一 下方不變 |
| 畢業 vs ML | 分離生命週期 | 不變 |
| Rust ONNX | ArcSwap + notify + ort | §二 2.5 |

---

## 六、第一輪審計修正追蹤

| 編號 | 嚴重度 | 修正內容 | 對應節 |
|------|--------|---------|--------|
| MIT-1 | CRITICAL | y=net_pnl/ATR 加 ATR_FLOOR + clamp ±5 | §二 2.1 |
| MIT-10 | CRITICAL | ONNX 熱加載改 ArcSwap，不用 RwLock | §二 2.5 |
| PM-1 | CRITICAL | 16→20 週 + Phase 3 拆分 | §四 |
| PM-3 | CRITICAL | Phase 0 等 R-07 Go/No-Go 後（≥4/11） | §四 |
| QA-1 | HIGH | 刪 optuna_metadata + FK 改應用層 CHECK | §一 1.2/1.5 |
| QA-3 | HIGH | Live 階段 orders/fills sync_commit=on | §一 1.6 |
| QA-5 | HIGH | ETL 歸檔表清單明確（含 indicators） | §一 1.7 |
| MIT-2 | HIGH | Platt scaling → isotonic regression | §二 2.2 |
| MIT-4 | HIGH | TPE+TS 分兩層：within-strategy vs across-strategy | §二 2.3 |
| MIT-5 | HIGH | CPCV embargo 區分 purge/embargo + 按策略分級 | §二 2.4 |
| MIT-9 | HIGH | DL-3 移到 Phase 4 + 必須 A/B 驗證 | §二 2.6 |
| PA-2 | HIGH | 80 欄位 → 混合（15 扁平 + JSONB） | §一 1.4 |
| PA-5 | HIGH | 三模組處置策略明確 | §二 2.7 |
| PA-6 | HIGH | teacher_directives 融入 ExperimentLedger | §二 2.8 |
| FA-1 | HIGH | update_params() 獨立 Phase 3a（9 工作日） | §四 Phase 3a |
| FA-3 | HIGH | requirements-ml.txt + try/except 降級 | §四 Phase 1 |
| FA-4 | HIGH | TimescaleDB Docker image 切換 | §四 Phase 0 |
| QA-2 | MEDIUM | 低頻表改普通表（directives/black_swan_events） | §一 1.2 |
| QA-7 | MEDIUM | black_swan_events 改普通表 | §一 1.2 |
| QA-10 | MEDIUM | feature_baselines 加 valid_from/until | §一 1.8 |
| QA-9 | LOW→修正 | 相關性矩陣改存 PG（數據量小） | §一 1.9 |
| MIT-3 | MEDIUM | ONNX PoC 精度驗證要求 | §二 2.12 |
| MIT-6 | MEDIUM | AV 閾值 permutation test 校準 | §二 2.9 |
| MIT-7 | MEDIUM | ADWIN delta 校準 + smoothed 輸入 | §二 2.10 |
| CROSS-2 | MEDIUM | funding_cost 精確化 | §二 2.11 |
| QA-6 | LOW | severity_source 欄位 | §二 2.13 |
| PM-6 | HIGH | DL-3 移到 Phase 4 + 異步 | §二 2.6 |
| PA-1 | MEDIUM | monitoring+quality 合併為 observability | §一 1.1 |
| FA-2 | HIGH | FeatureCollector 純記憶體 + 異步 flush | §四 Phase 1 |

---

## 七、文件關係圖

```
本文件（融合方案 v0.3）
  ├── 整合自 DB-1 v0.1
  │     docs/references/2026-04-03--data_storage_architecture_optimal_draft_v0.1.md
  ├── 整合自 ML-1 v0.4
  │     docs/references/2026-04-03--ml_dl_learning_architecture_v0.4.md
  ├── 前置 Agent 調參 v0.2
  │     docs/references/2026-04-03--agent_param_tuning_design_draft_v0.2.md
  ├── 參考 DB 代碼審計 V1
  │     docs/architecture/DATA_STORAGE_ARCHITECTURE_V1.md
  └── 第一輪審計報告（嵌入本文 §六）
```

---

---

## 八、第二輪深度審計修正（v0.4 整合）

### 8.1 CRITICAL：Echo Chamber / Selective Labels（MIT-7）

Scorer 門控自己的訓練數據 → 覆蓋面單調收縮 → 長期退化。

**修正：**
- **強制探索信號 5-10%**：隨機繞過 confidence gate，最小倉位執行，結果作為無偏標籤
- **Inverse Propensity Weighting (IPW)**：重訓練時按選擇概率的倒數加權
- **Virtual outcome**：被拒信號追蹤後續價格走勢，作為 `was_executed=FALSE` 訓練樣本
- **Coverage 監控**：追蹤特徵空間覆蓋率（KDE/PCA），跨週期下降 >20% 觸發警報

### 8.2 HIGH 修正

**Y_MAX clamp → Winsorize + is_extreme 特徵（QA2-2）：**
```python
Y_LO, Y_HI = np.percentile(y_raw, [1, 99])
y = np.clip(y_raw, Y_LO, Y_HI)
is_extreme = np.abs(y_raw) > Y_HI  # 作為額外特徵，保留黑天鵝學習信號
```

**NIG Prior Empirical Bayes 初始化（QA2-4）：**
```python
mu_0 = mean(paper_returns)
lambda_init = 3.0        # 3 筆交易即可偏離先驗
alpha_init = 3.0          # > 2 確保方差均值存在
beta_init = var(paper_returns) * (alpha_init - 1)
# 前 10 個 trial 強制 50% exploitation
```

**CPCV 改 4-fold + Power Guard（QA2-6）：**
- 6-fold → **4-fold**（每 fold 37 筆，SE 降 ~20%）
- 啟動前檢查 power > 0.5，不足則 CPCV 結果只作參考，不作拒絕依據

**PSI 校準改重疊滑動窗口（QA2-8）：**
- 30d 窗口 × 7d 步長 → 12 個月 46 個 PSI 值（非 5-11 個）
- Block bootstrap（block_size=4）計算分位數 CI
- CI 過寬時退化為保守默認值 0.25/0.50

**JSONB Feature Leakage 防護（MIT-1）：**
- 建立 `learning.scorer_training_features` VIEW（顯式排除 outcome_* 欄位）
- 訓練管線用 JSONB key **白名單**，匹配 `/^outcome_/` 硬斷言失敗
- CI 靜態分析：grep 訓練代碼中對 outcome 欄位的引用

**Scorer Ensemble Consensus Reliability（MIT-2）：**
- 追蹤「全變體一致」時的條件準確率
- `P(correct | all_agree)` 滑動窗口 < 60% → 觸發 consensus penalty
- 至少一個變體用 orderbook 微觀結構特徵（非價格衍生），提供真正的信息多樣性

**Phase 2 數據 Bootstrap（PM-R2-2）：**
- Phase 1 立即開始 Paper Trading 數據採集
- Phase 2 前半段用 **BacktestEngine 歷史數據** bootstrap Scorer 初始訓練集
- Phase 2 後半段用 live 增量更新

**ExperimentLedger Hypothesis 擴展（PA-R2-2）：**
```python
# 新增字段
source_type: str = "manual"           # manual / claude_teacher / auto_detected
metadata: Dict[str, Any] = {}         # suggested_experiment / evaluation_metric
trigger_condition: Optional[str] = None  # "50 trades or 7 days"
```
- ml_review 不進 ExperimentLedger → 寫入 `observability.model_performance`
- PG teacher_directives 表保留（audit trail），通過 directive_id↔hypothesis_id 關聯

### 8.3 MEDIUM 修正

- **ATR_FLOOR**：靜態值 → `rolling_quantile(ATR_history, q=0.05, window=30d)`（QA2-1）
- **James-Stein**：統一 B → **per-parameter** 獨立 shrinkage（QA2-5）
- **Grid Inventory_Risk_Ratio**：simple max → **time-weighted 95th percentile**，排除重平衡 settling period（QA2-7）
- **相關性矩陣**：REAL[2500] → **長表** `(ts, symbol_a, symbol_b, correlation)`（QA2-10）
- **Isotonic 校準穩定性**：加 Gaussian 平滑 + 新舊混合 damping（α=0.3）+ confidence gate 遲滯（MIT-4）
- **Feature Importance**：LightGBM 原生 → **SHAP TreeExplainer** + temporal stability + OOS permutation（MIT-6）
- **Grid Pareto**：加 live vs backtest frontier 比較 + dynamic fee floor（MIT-8）
- **Claude Teacher 效果追蹤**：confirmation_rate < 35%/20+ 假設 → 自動暫停 + 語義去重（MIT-10）
- **OU Grid Bug**：Python + Rust 都缺 `sqrt(2)`，`sigma/sqrt(theta)` → `sigma/sqrt(2*theta)`（QA 代碼審查）

### 8.4 集成測試 Milestone（INTEG-1）

- **Phase 2 結束**：`test_scorer_feature_alignment`（FeatureCollector 維度 == ONNX 輸入維度）
- **Phase 3b 結束**：`test_optuna_to_ts_pipeline`（合成數據跑完整 TPE→TS 迴路）
- **Phase 4 結束**：`test_full_learning_loop`（FeatureCollector → Scorer → Optuna → TS → Claude → ExperimentLedger 端到端）

### 8.5 排期修正

- Phase 2 **增加 1 週 buffer**（W6-9，從 Phase 5 壓縮）
- Phase 0 增加 **TimescaleDB Docker 切換 checklist**（備份 → 切 image → 保持容器名 → Grafana datasource 改 timescaledb:true → 驗證）
- Phase 1 增加 **ExperimentLedger JSON→PG 遷移**（0.5-1 天）
- 融合方案 Phase 3a = TODO.md **AGT-1**，交叉引用

### 8.6 ML 降級分層策略

```
Level 0: lightgbm 可用 → LightGBM Scorer
Level 1: lightgbm 不可用但 sklearn 可用 → sklearn GBR
Level 2: 兩者都不可用 → CognitiveModulator L0 + 硬編碼 EV 閾值
Scorer 不可用時 Optuna/TS suspend（保持最後已知最佳參數）
FeatureCollector 始終運行（即使 ML 降級也繼續收集）
```

### 8.7 FeatureCollector 規格

- Ring buffer = 5 分鐘 = ~3000 條（~600 KB）
- 溢出策略：drop-oldest（tick SLA 不允許 back-pressure）
- 連續 3 次 flush 失敗 → 文件 fallback（JSONL），PG 恢復後回灌
- 特徵版本號綁定 ONNX 模型（維度不匹配時 fallback 截斷/填充）

---

## 九、第二輪審計修正追蹤

| 編號 | 嚴重度 | 修正內容 | 對應節 |
|------|--------|---------|--------|
| MIT-7 | CRITICAL | Echo Chamber：5-10% 強制探索 + IPW + virtual outcome + coverage 監控 | §八 8.1 |
| QA2-2 | HIGH | clamp → winsorize + is_extreme 特徵 | §八 8.2 |
| QA2-4 | HIGH | NIG Prior Empirical Bayes 初始化 | §八 8.2 |
| QA2-6 | HIGH | CPCV 6→4 fold + power guard | §八 8.2 |
| QA2-8 | HIGH | PSI 重疊滑動窗口 + block bootstrap | §八 8.2 |
| MIT-1 | HIGH | JSONB feature leakage VIEW + 白名單 + CI check | §八 8.2 |
| MIT-2 | HIGH | Ensemble consensus reliability monitor | §八 8.2 |
| PM-R2-2 | HIGH | Phase 2 回測 bootstrap 訓練數據 | §八 8.2 |
| PA-R2-2 | HIGH | ExperimentLedger Hypothesis 擴展 3 字段 | §八 8.2 |
| QA2-1 | MEDIUM | ATR_FLOOR rolling 5th percentile | §八 8.3 |
| QA2-5 | MEDIUM | James-Stein per-parameter shrinkage | §八 8.3 |
| QA2-7 | MEDIUM | Grid Inventory time-weighted 95th pct | §八 8.3 |
| QA2-10 | MEDIUM | 相關性矩陣改長表 | §八 8.3 |
| MIT-4 | MEDIUM | Isotonic 平滑 + damping + 遲滯 | §八 8.3 |
| MIT-6 | MEDIUM | SHAP + temporal stability + OOS permutation | §八 8.3 |
| MIT-8 | MEDIUM | Grid Pareto live vs backtest + dynamic fee | §八 8.3 |
| MIT-10 | MEDIUM | Claude Teacher effectiveness + 語義去重 | §八 8.3 |
| OU-BUG | MEDIUM | Python+Rust OU 公式缺 sqrt(2) | §八 8.3 |
| INTEG-1 | CRITICAL | 3 個集成測試 milestone | §八 8.4 |
| PM-R2-1 | HIGH | Phase 2 +1 週 buffer | §八 8.5 |
| PM-R2-3 | HIGH | AGT-1 交叉引用 | §八 8.5 |
| FA-R2-1 | HIGH | ML 降級分層策略 | §八 8.6 |
| FA-R2-2 | HIGH | FeatureCollector ring buffer 規格 | §八 8.7 |
| FA-R2-3 | MEDIUM | TimescaleDB Docker 切換 checklist | §八 8.5 |
| PA-R2-1 | MEDIUM | decision_context_repo.py 封裝 | 待 Phase 2 實現 |
| PA-R2-3 | MEDIUM | Schema registry 文檔 | 待 Phase 0 實現 |
| INTEG-2 | MEDIUM | 特徵版本號 + ONNX schema 校驗 | §八 8.7 |
| INTEG-3 | MEDIUM | ExperimentLedger JSON→PG 遷移 | §八 8.5 |

**兩輪審計合計：5 CRITICAL + 21 HIGH + 18 MEDIUM + 7 LOW = 51 項，全部已有修正方案。**

---

---

## 十、數據庫專題重大修正（v0.5 · 8 角色 + 4 角色聯合驗證）

### 10.1 存儲量重新估算：砍 97%（四角色聯合驗證 APPROVE WITH CONDITIONS）

**原方案 5.6GB/day 過度設計。三大消費者可砍，alpha 損失 < 0.1% AUC。**

| 被砍數據源 | 原始成本 | 替代方案 | 替代成本 | ML 影響 |
|-----------|---------|---------|---------|--------|
| raw_ticks 3/sec | ~1 GB/d | market_tickers 5s 快照 | ~50 MB/d | 0%（Scorer 14 特徵全基於 klines） |
| orderbook L2 25 levels 1/sec | ~2.5 GB/d | ob_snapshot_1m L5 summary | ~6 MB/d | 0%（系統只用 L5 summary） |
| raw trade tape ~50/sec | ~2 GB/d | trade_agg_1m 每分鐘聚合 | ~5 MB/d | 0%（系統不用逐筆 TFI） |

```
原方案：5.6 GB/day → 158 GB/year → 790 GB/5year
修正後：0.17 GB/day → 6.2 GB/year → 31 GB/5year（節省 97%）
```

**31 GB/5year 可永久保留在 PG 中，大幅簡化 Parquet 歸檔的必要性。**
（Parquet ETL 仍保留作為 ML 訓練的列存讀取優化，但不再是容量管理的必需品。）

### 10.2 聯合驗證的 4 個必須條件

| # | 條件 | 理由 |
|---|------|------|
| 1 | **Outcome 窗口改 5 個**（1m/5m/1h/4h/**24h**），不刪 24h | 趨勢策略持倉 12-72h，4h 不足以覆蓋完整週期 |
| 2 | **黑天鵝檢測明確用 kline return** | 4 個信號（MAD/相關性/量/速度）全部基於 kline，不依賴 tick-level |
| 3 | **PSI 基線切換後 7 天重建** | 數據源切換會導致特徵分佈微移，需重建 feature_baselines |
| 4 | **指標重算用 DuckDB 向量化** | 純 Python 循環 3.7h → DuckDB 向量化 5-20min |

### 10.3 Schema 替代表設計

**原 `market.raw_ticks` → 改為 `market.market_tickers`（5s 快照）：**
```sql
CREATE TABLE market.market_tickers (
    ts              TIMESTAMPTZ NOT NULL,
    symbol          TEXT NOT NULL,
    last_price      REAL, mark_price REAL, index_price REAL,
    best_bid        REAL, best_ask REAL, bid_size REAL, ask_size REAL,
    volume_24h      REAL, turnover_24h REAL, spread_bps REAL,
    open_interest   REAL,
    PRIMARY KEY (symbol, ts)
);
SELECT create_hypertable('market.market_tickers', 'ts', chunk_time_interval => INTERVAL '1 day');
-- 壓縮 2h 後 | 保留 30d
```

**原 `market.orderbook_l2`（25 levels）→ 改為 `market.ob_snapshots`（L5 1m summary）：**
```sql
CREATE TABLE market.ob_snapshots (
    ts              TIMESTAMPTZ NOT NULL,
    symbol          TEXT NOT NULL,
    imbalance_ratio REAL,    -- bid_depth / (bid+ask)
    weighted_mid    REAL,
    spread_bps      REAL,
    bid_depth_5     REAL,    -- sum of top 5 bid sizes
    ask_depth_5     REAL,
    depth_ratio     REAL,    -- bid_depth_5 / ask_depth_5
    PRIMARY KEY (symbol, ts)
);
SELECT create_hypertable('market.ob_snapshots', 'ts', chunk_time_interval => INTERVAL '1 day');
-- 壓縮 2h 後 | 保留 30d
```

**原 `market.public_trades`（逐筆）→ 改為 `market.trade_agg_1m`（分鐘聚合）：**
```sql
CREATE TABLE market.trade_agg_1m (
    ts              TIMESTAMPTZ NOT NULL,  -- 分鐘開始時間
    symbol          TEXT NOT NULL,
    buy_volume      REAL, sell_volume REAL,
    buy_count       INT, sell_count INT,
    large_buy_count INT, large_sell_count INT,  -- > threshold 的大單
    vwap            REAL,
    max_single_qty  REAL,  -- 分鐘內最大單筆成交
    PRIMARY KEY (symbol, ts)
);
SELECT create_hypertable('market.trade_agg_1m', 'ts', chunk_time_interval => INTERVAL '1 day');
-- 壓縮 1d 後 | 保留 90d
```

### 10.4 indicators 歷史持久化改為按需重算

**不再存 `market.indicators` 90 天歷史。** 改為：
- `features.online_latest`：只存最新值 cache（UPSERT，per symbol × timeframe）
- ML 回測需要歷史指標時：從 `market.klines` Parquet + DuckDB 向量化重算
- 首次重算 6 個月 50 symbols：DuckDB ~5-20 min，之後每日增量 < 1 min
- 指標參數版本存入 `features.versions`（確保可重現性）

### 10.5 Outcome Backfill 表分離（DBA 建議）

不在壓縮 hypertable chunk 上做 UPDATE（需 decompress-update-recompress）。改為獨立表 JOIN：

```sql
CREATE TABLE trading.decision_outcomes (
    context_id      TEXT PRIMARY KEY,
    outcome_1m      REAL, outcome_5m REAL, outcome_1h REAL,
    outcome_4h      REAL, outcome_24h REAL,  -- ★ 保留 24h
    max_favorable   REAL, max_adverse REAL,
    backfilled_ts   TIMESTAMPTZ
);
-- 普通表，非 hypertable（低頻 UPDATE，無需壓縮）
-- 查詢時 JOIN: decision_context_snapshots c JOIN decision_outcomes o ON c.context_id = o.context_id
```

### 10.6 DB 技術選型確認：PG + TimescaleDB（E5+DBA 共識）

**結論：維持方案 A，拒絕 QuestDB/ClickHouse/DuckDB-only。**

| 否決方案 | 否決理由 |
|---------|---------|
| QuestDB | 不支持 JSONB、FK、UPDATE（outcome backfill 無法實現） |
| ClickHouse | 非 ACID、UPDATE 代價極高、記憶體貪婪（LLM 競爭） |
| DuckDB-only | 不支持並發寫入、無 WAL、Grafana 無法直連 |
| 混合 3 系統 | 單開發者維護 3 個 DB 服務 = 每個都維護不好 |

**核心論點：2,700 rows/sec 只佔 PG+TimescaleDB 極限吞吐的 1-3%。引入其他引擎是解決不存在的問題。**

TimescaleDB 核心價值 = 自動壓縮 + retention policy + 連續聚合（不是吞吐）。

### 10.7 運維精簡

| 原方案組件 | v0.5 決策 | 理由 |
|-----------|----------|------|
| PgBouncer | **砍掉** | 當前 <5 並發連接，max_connections=100 遠夠 |
| Parquet ETL cron | **保留但降級** | 不再是容量管理必需品，改為 ML 訓練優化路徑 |
| DuckDB | **保留** | 嵌入式零運維，ML 訓練 + 指標重算引擎 |

### 10.8 Phase 0 拆分（PM+FA 建議）

```
Phase 0a (W1, 4/11-4/17): 標準 PG 16 上建 8-schema 結構（零風險）
  → ML Phase 1 可立即開始，不等 TimescaleDB
Phase 0b (W2-3, 4/18-4/30): 切換 TimescaleDB Docker image + 啟用 hypertable
  → Grafana VIEW 橋接（零停機遷移）
  → 6 個 docker exec psql 腳本改為 psycopg2 直連
```

### 10.9 Grafana 零停機遷移（PA 建議）

```sql
-- 舊表加 _legacy 後綴
ALTER TABLE public.market_tickers RENAME TO market_tickers_legacy;
-- 新表在 market schema
CREATE TABLE market.market_tickers (...);
-- VIEW 透明代理
CREATE VIEW public.market_tickers AS SELECT ... FROM market.market_tickers;
-- Grafana Dashboard SQL 不需改動
```

### 10.10 ETL 工具選型：DuckDB COPY（FA 建議）

```python
import duckdb
con = duckdb.connect()
con.execute("INSTALL postgres; LOAD postgres")
con.execute("ATTACH 'dbname=trading_ai ...' AS pg (TYPE POSTGRES)")
con.execute("""
  COPY (SELECT * FROM pg.market.market_tickers WHERE ts::date = current_date - 1) 
  TO '/data/parquet/tickers/2026-04-03.parquet' (FORMAT PARQUET, COMPRESSION ZSTD)
""")
```
DuckDB 的 PG scanner 用 COPY protocol（二進制），比 psycopg2 fetchall 快 3-5x。

### 10.11 數據價值矩陣（QA+MIT+QDE 共識）

| 數據 | Alpha | 成本 | 建議 |
|------|-------|------|------|
| klines (all TF) | HIGH | 14 MB/d | **MUST-HAVE** |
| funding_rates | HIGH | 極低 | **MUST-HAVE** |
| decision_context | HIGH | 10 MB/d | **MUST-HAVE** |
| trading chain | HIGH | 5 MB/d | **MUST-HAVE** |
| open_interest | MED-HIGH | 20 MB/d | **MUST-HAVE** |
| trade_agg_1m | MEDIUM | 5 MB/d | **MUST-HAVE** |
| market_tickers 5s | MEDIUM | 50 MB/d | **MUST-HAVE** |
| liquidations | MEDIUM | 10 MB/d | NICE-TO-HAVE |
| ob_snapshot_1m L5 | LOW-MED | 6 MB/d | NICE-TO-HAVE |
| long_short_ratio | LOW | 7 MB/d | NICE-TO-HAVE |
| raw_ticks 3/sec | LOW | 1 GB/d | **CAN-DROP** |
| orderbook L25 1/sec | LOW | 2.5 GB/d | **CAN-DROP** |
| raw trade tape | LOW | 2 GB/d | **CAN-DROP** |

**未來高 alpha 數據源（Phase 3+ 考慮）：** On-chain flow（Glassnode/CryptoQuant）、Cross-exchange basis。

---

## 十一、完整審計歷程

```
v0.1 (2026-04-04) — 初稿：DB+ML+News 交叉比對
v0.2 (2026-04-04) — 6 開放項解決
v0.3 (2026-04-04) — 第一輪審計修正（QA+MIT: 2C+9H+7M+4L · PM+PA+FA: 2C+4H+6M+2L）
v0.4 (2026-04-04) — 第二輪深度審計修正（QA2: 4H+5M+2L · MIT2: 1C+3H+5M+2L · PM+PA+FA R2: 整合風險）
v0.5 (2026-04-04) — DB 專題：8 角色技術選型 + 4 角色聯合驗證存儲精簡（APPROVE WITH CONDITIONS）

兩輪審計 + DB 專題合計：5 CRITICAL + 29 HIGH + 23 MEDIUM + 10 LOW = 67 項
全部已有修正方案。
```

---

*v0.5 · 2026-04-04 · DB 專題完成 · 存儲 5.6→0.17 GB/day（-97%）· PG+TimescaleDB 確認 · 砍 PgBouncer*
*下一步：確認後納入 TODO.md*
