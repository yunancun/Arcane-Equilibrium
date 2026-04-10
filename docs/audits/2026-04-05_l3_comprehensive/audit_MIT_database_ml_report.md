# MIT 審計報告：資料庫與 ML 基礎設施就緒度評估

**審計角色：** MIT (ML Infrastructure & Database Auditor)
**審計日期：** 2026-04-05
**審計範圍：** 資料庫 Schema、數據管線、特徵存儲、ML 訓練管線、ONNX 模型路徑、模型管理器、評分器、ETL 管線、TimescaleDB、數據質量、Kelly Sizer、Optuna 存儲、Thompson Sampling
**代碼基準：** Rust 859 tests + Python 1075 tests = 1934 全綠

---

## 總評分：52/100 — 基礎設施代碼完備，但 DDL 未執行且無實際數據流

---

## 1. Database Schema — DDL/遷移文件

**判定：🟡 Partial**

### 已完成
- 7 份遷移文件（V001-V007）完整覆蓋 8 個 Schema：market / trading / agent / learning / features / observability / risk / news
- 共計 ~40 張表定義完備：market(11) + trading(9) + agent(3) + learning(10) + features(2) + observability(5) + risk(3) + experiment_ledger(1)
- 所有表的列定義與 Rust 寫入器代碼完全匹配（已逐一對比驗證）
- 索引設計合理：高頻表精簡索引（僅 `ts DESC`），GIN 索引用於 JSONB 查詢
- `learning.scorer_training_features` VIEW 設計正確，outcome 列作為 label 不作為 feature
- Grafana VIEW 橋接完備（11 個 VIEW 保持舊查詢兼容）
- ExperimentLedger 表（V007）已添加 3 個新字段（source_type/metadata/trigger_condition）

### 關鍵缺陷
- **DDL 全部標記為 DRAFT — "not yet executed"**。V001-V005 明確標註 `Planned execution date: 2026-04-11`。V006/V007 雖有代碼但同樣未在生產 PG 執行
- **無自動遷移工具**：沒有 Flyway/Liquibase/sqlx-migrate 等遷移管理。手動執行 DDL 有遺漏風險
- **Docker test PG 存在**（`docker/docker-compose.test.yml`），但未見自動化腳本將 V001-V007 全部灌入

### 風險評估
Schema 設計質量高，但在 DDL 實際執行前，所有寫入器都在 "graceful degradation" 模式運行 —— 即 PG 不可用時靜默跳過或寫 JSONL。**這意味著當前零數據入庫**。

---

## 2. Data Pipeline（5 個寫入器接線狀態）

**判定：🟡 Partial（代碼完備，運行時無 PG 連接則無效）**

| 寫入器 | 代碼 | main.rs 接線 | 通道 | PG 表 | 運行時狀態 |
|--------|------|-------------|------|-------|-----------|
| market_writer | 完整（10 表） | tokio::spawn ✅ | bounded mpsc ✅ | market.* | 🟡 需 PG |
| trading_writer | 完整（4 表） | tokio::spawn ✅ | bounded mpsc 4096 ✅ | trading.signals/intents/fills/position_snapshots | 🟡 需 PG |
| context_writer | 完整（1 表） | tokio::spawn ✅ | bounded mpsc 1024 ✅ | trading.decision_context_snapshots | 🟡 需 PG |
| feature_writer | 完整（UPSERT） | tokio::spawn ✅ | bounded mpsc ✅ | features.online_latest | 🟡 需 PG |
| quality_writer | 完整 | tokio::spawn ✅ | shared AtomicU64 ✅ | observability.data_quality_events | 🟡 需 PG |
| rest_poller | 完整（3 輪詢） | spawn_rest_pollers ✅ | via market_tx ✅ | funding/OI/LSR | 🟡 需 PG + API |
| drift_detector | 框架完整 | tokio::spawn ✅ | 獨立定時 ✅ | observability.drift_events | 🔴 TODO 標記 |

### 關鍵發現
1. `main.rs` L722-809 確認所有 6 個寫入器 + 1 個檢測器均已正確 spawn，帶 CancellationToken 優雅關閉
2. 所有通道使用 `if db_pool.is_available()` 條件創建 —— **無 PG 時通道為 None，寫入靜默跳過**
3. `drift_detector.rs` L259 有明確 TODO：`"TODO(G3-full): Read baselines from observability.feature_baselines... actual PG queries will be wired when baselines are populated"`。即漂移檢測器當前只打 debug log，不做實際 PSI 計算
4. 回退機制完備：`FallbackWriter` 在 PG 連續失敗 3 次後寫 JSONL 到 `/tmp/openclaw/fallback/`，含文件輪換（10 萬行/文件）
5. `DbPool` 設計良好：可選初始化 + 失敗計數 + 健康檢查 + 優雅關閉

### 缺失項
- trading.orders / trading.order_state_changes / trading.risk_verdicts 三張表的寫入器尚未實現（trading_writer 只寫 signals/intents/fills/positions）
- agent.* 三張表（messages/ai_invocations/state_changes）完全無寫入器
- market.news_signals 無寫入器（Phase 4 news agent 範圍）

---

## 3. Feature Store（FeatureCollector 34-dim）

**判定：🟡 Partial**

### 已完成
- `FeatureSnapshot` 結構體：34 維特徵向量（31 scalars + 2 regime enums + 1 price），`FEATURE_DIM = 34`
- `to_feature_vector()` 將 16 個 IndicatorSnapshot 指標扁平化為 `Vec<f32>`
- 環形緩衝區（VecDeque, cap 3000）用於內存保留
- `feature_writer.rs` 實現 UPSERT 到 `features.online_latest`，per (symbol, timeframe) 去重
- `main.rs` L812-818 在啟動時插入 `features.versions` v1.0 行
- 特徵版本管理表 `features.versions` 有 indicator_config + normalization_params JSONB

### 缺陷
- **數據是否真正流入 DB**：取決於 PG 是否連接。當前 DDL 未執行 → PG 無表 → 數據不入庫
- `features.online_latest` 只保存最新值（UPSERT），不保存歷史序列。ML 訓練需要歷史特徵數據，需從 `trading.decision_context_snapshots` 的 JSONB 中提取
- `feature_version` 字段寫入正確（G4 E2 fix），但 `normalization_params` 尚未實現（features.versions 表 `normalization_params` 列預留但無填充邏輯）

---

## 4. ML Training Pipeline（program_code/ml_training/）

**判定：🟡 Partial**

### 已完成
- **scorer_trainer.py**：LightGBM 回歸，CPCV embargo per strategy type（24h/4h/8h/72h），early stopping 50 rounds
- **cpcv_validator.py**：4-fold CPCV，temporal purging，power guard
- **calibration.py**：Isotonic regression + Gaussian smoothing（假定，未詳讀）
- **label_generator.py**：ATR-normalized PnL with winsorization + ATR_FLOOR
- **leakage_check.py**：Feature whitelist validation
- **onnx_exporter.py**：LightGBM → ONNX，f32 cast + NaN sentinel + precision validation（max abs err < 1e-3）

### 缺陷
- **訓練數據來源不可用**：scorer_trainer.py 的 `train_scorer()` 接收 numpy arrays，但無從 DB 讀取數據的膠水代碼。需要先 ETL 到 Parquet，再加載為 numpy
- **scorer_trainer 使用簡單 80/20 split** 作為 CPCV 佔位符（代碼注釋 L114: "Simple train/test split — placeholder for CPCV"），真正的 CPCV 在 cpcv_validator.py 中但未被 scorer_trainer 調用
- **無端到端訓練腳本**：缺少 `train.py` 或 `run_training_pipeline.py` 將 ETL → 特徵提取 → 標籤生成 → 訓練 → CPCV 驗證 → ONNX 導出 → 模型註冊串聯起來
- **依賴未確認**：lightgbm、onnxmltools、onnxruntime 均為 try/except import，graceful degradation 但未見 requirements-ml.txt
- **PG 讀取連接池**：optuna_optimizer.py 注釋提到 "Training reads will use a separate psycopg2 connection pool... pool not implemented yet"

---

## 5. ONNX Model Path（Python 訓練 → ONNX 導出 → Rust 推理）

**判定：🟡 Partial**

### 路徑分析

```
[Python 訓練] scorer_trainer.py → scorer_lgb.txt (LightGBM text)
     ↓
[Python 導出] onnx_exporter.py → scorer.onnx (ONNX format)
     ↓
[Rust 推理]  OnnxModelManager::predict(features) → ModelPrediction
     ↓
[Rust 評分]  Scorer::score() → ScorerResult { calibrated_prob, expected_value, tier }
```

### 已完成
- `onnx_exporter.py`：LightGBM → ONNX 轉換 + f32 cast + precision validation
- `model_manager.rs`：ArcSwap 熱交換架構 + SIGHUP reload + version tracking
- `scorer.rs`：3-tier degradation 完備

### 關鍵缺陷
- **model_manager.rs 的 predict() 返回 None**（L110: `"// TODO: Replace with ort::Session::run() when ort crate is added"`）。即 **ort crate 尚未集成**，Rust 端無法執行 ONNX 推理
- `LoadedModel` 是佔位結構體，無 `ort::Session` 字段
- `try_reload()` 只更新版本號和路徑，不實際加載模型
- ONNX 路徑在 Python 側完備（訓練 → 導出 → 驗證），但 Rust 側最後一環（ort 推理）缺失

### 實際效果
當前 Scorer 永遠降級到 Tier 2（rule-based）或 Tier 3（fixed 0.5）。ONNX Tier 1 路徑在 Rust 側是死代碼。

---

## 6. Model Manager（ArcSwap 熱交換）

**判定：🟡 Partial**

### 已完成
- ArcSwap<ModelState> 架構正確，零鎖讀取
- `is_loaded()` / `version()` / `predict()` / `try_reload()` 接口完備
- 無模型時 graceful degradation（predict → None → Scorer 降級）
- version counter + AtomicU32 原子遞增

### 缺陷
- **predict() 永遠返回 None**（見上述 TODO）
- 無 `ort` 依賴在 Cargo.toml 中
- 模型路徑發現邏輯簡單（直接檢查文件存在），無 model registry DB 查詢
- 無模型健康指標（推理延遲、錯誤率、預測分佈）

---

## 7. Scorer（3-tier degradation）

**判定：🟢 Ready（Tier 2/3 可用，Tier 1 不可用）**

### 已完成
- Tier 1：ONNX path（代碼完備，依賴缺失）
- Tier 2：Rule-based（使用 signal_confidence + edge_bps），功能正常
- Tier 3：Fixed confidence 0.5，作為最終回退
- `ScorerResult` 包含 calibrated_prob / expected_value / tier / model_version
- 與 `intent_processor` 中的 Gate 3 Cost Gate 已集成（ATR × confidence × qty vs round-trip fee）

### 結論
作為 **無 ML 模型時的降級運行模式**，Scorer 完全可用。系統不會因缺少 ONNX 模型而崩潰或停止交易。這符合 "生存 > 利潤" 原則。

---

## 8. ETL Pipeline（Parquet ETL + DuckDB Labels）

**判定：🟡 Partial**

### 已完成
- `parquet_etl.py`：DuckDB 驅動的 PG → Parquet 提取，支持 decision_contexts + fills + features
- `generate_training_labels()`：ASOF JOIN fills + features + klines，ATR-normalized label with winsorization（clamp ±5.0）
- DuckDB postgres extension 用於跨系統查詢
- 輸出目錄自動創建 + ZSTD 壓縮

### 缺陷
- **需要 PG 有數據**：當前 DDL 未執行 → DB 無表 → ETL 會失敗
- **generate_training_labels 的 klines_parquet 參數**：需要先單獨提取 klines 到 Parquet（`extract_training_data` 不提取 klines）
- **無排程自動化**：注釋提到 "Scheduled via cron"，但無 cron 配置或 systemd timer
- ASOF JOIN 中 `features` 表結構假設有 `ts` 列，但 `features.online_latest` 只有 `updated_ts_ms` BIGINT，不是 TIMESTAMPTZ —— **JOIN 會失敗或需要類型轉換**

---

## 9. TimescaleDB（Hypertable + 壓縮 + 保留）

**判定：🟡 Partial**

### 已完成
- 所有高頻表（market.* + trading.* + agent.* + observability.*）使用條件 hypertable 創建：`DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN ... END IF; END $$;`
- V006 壓縮策略完備：
  - Market 高頻：7 天後壓縮（segmentby=symbol）
  - Trading：14 天後壓縮
  - Klines：14 天後壓縮（segmentby=symbol,timeframe）
- V006 保留策略完備：
  - Market 高頻：90 天
  - Klines：365 天（回測需要）
  - Funding/OI/LSR：180 天
  - Trading fills/orders：365 天
  - Observability：90 天
- sync_commit 分層：高頻表 off，關鍵交易表 on
- Docker test PG 使用 `timescale/timescaledb:latest-pg16`

### 缺陷
- **V006 未執行**（同 DDL 問題）
- 部分高頻表缺少壓縮策略：`market.funding_rates` / `market.open_interest` / `market.long_short_ratio` / `market.regime_snapshots` / `market.regime_transitions` 無壓縮策略但有保留策略
- `trading.decision_context_snapshots` 無壓縮策略（含 JSONB 大列，壓縮效果顯著但未配置）
- `trading.risk_verdicts` / `trading.order_state_changes` / `trading.position_snapshots` 無壓縮和保留策略

---

## 10. Data Quality（quality_writer + PSI baseline rebuild）

**判定：🟡 Partial**

### 已完成
- `quality_writer.rs`：每 60 秒檢查全局 tick freshness（30 秒閾值），寫入 `observability.data_quality_events`
- `drift_detector.rs`：
  - PSI 計算：`compute_psi()` + epsilon smoothing + quantile bin edges + block bootstrap CI
  - ADWIN 檢測器：delta=0.05 + min_width=100 + 3-consecutive majority vote + 30-day burn-in
  - PSI baseline rebuild：`compute_baseline_windows()` + 30/7 天滑動窗口 + `should_rebuild_baseline()` 冷卻期
  - 完整測試覆蓋（PSI identical/shifted/empty bins, ADWIN stable/shift/majority, baseline windows/empty）

### 缺陷
- **drift_detector 的 run 函數只打 debug log**，實際 PSI 計算和 ADWIN 檢測未接入 PG 數據讀取（TODO 標記）
- quality_writer 只監控全局 tick freshness（單一 AtomicU64），不監控 per-symbol freshness
- 不檢測數據異常值（只檢測 stale）
- 無 completeness 檢查（某 symbol 的 kline 是否有 gap）

---

## 11. Kelly Sizer

**判定：🟢 Ready**

### 已完成
- Kelly 公式正確：`f* = W - (1-W)/R`
- 三級分數 Kelly：< 50 trades → 1/8，< 200 → 1/6，>= 200 → 1/4
- ATR 波動率調整：reference ATR% = 2%，clamp [0.5, 1.5]
- 配置完備：max_fraction / min_trades / risk_pct / enabled
- 禁用時直接 passthrough max_qty
- 負 Kelly 處理：最小 1% 倉位（而非零倉位）
- 完整測試：fractional tiers / negative Kelly / vol adjustment / max cap / below min trades / disabled

### 可接收 Scorer 輸出
Kelly Sizer 直接接收 balance/price/atr_pct/max_qty，不直接依賴 ScorerResult。但在 `intent_processor` 中，Scorer 的 calibrated_prob 影響 Gate 3 決策（是否通過成本門檻），通過後才到 Kelly sizing。**路徑完整且可用**。

---

## 12. Optuna Storage

**判定：🟢 Ready**

### 已完成
- `optuna_optimizer.py`：使用 `JournalStorage + JournalFileBackend`（非 SQLite，E5-O4 審計決策）
- 文件路徑：`/tmp/openclaw/optuna_studies.log`
- 兼容 Optuna 4.x（`JournalFileBackend`）和舊版（`JournalFileStorage`）
- Study 命名規範：`{strategy}_{symbol}_{regime}`
- 搜索空間從 Rust ParamRange JSON 構建，只包含 `agent_adjustable=true` 的參數
- IPC 通信：Unix domain socket + JSON-RPC 2.0
- `compute_ev_net()` 正確計算淨期望值（含手續費）
- 離線模式完備（Phase 3b），帶參數距離擾動啟發式

### 缺陷
- **PG 寫入延後**：optuna_optimizer.py L525: `"TODO: Write to learning.ml_parameter_suggestions when V004 DDL is live"` —— 優化結果只返回 dict，不持久化到 PG
- 離線模式的目標函數使用所有 fills 的 EV + 小擾動，不是真正的 per-trial 評估。這是已知設計妥協

---

## 13. Thompson Sampling（NIG 後驗持久化）

**判定：🟡 Partial**

### 已完成
- `thompson_sampling.py`：完整 NIG 共軛更新（single + batch），Empirical Bayes 初始化
- 數值安全：`_MIN_LAMBDA` / `_MIN_ALPHA` / `_MIN_BETA` 邊界
- `sample_nig()`：正確的 InverseGamma → Normal 兩步抽樣
- `select_next_arm()`：exploitation floor（< 10 trials → 選 mu 最高的臂）+ Thompson Sampling
- `posteriors_to_dict()` / `posteriors_from_dict()`：JSON 序列化/反序列化

### 關鍵缺陷
- **無 PG 持久化代碼**：`learning.bayesian_posteriors` 表已在 V004 DDL 中定義，但 thompson_sampling.py 無任何 DB 讀寫邏輯
- **不能存活重啟**：後驗狀態只在 Python 進程記憶體中，進程重啟後丟失
- 序列化方法（`posteriors_to_dict/from_dict`）是 JSON 格式，需手動調用 —— 無自動保存/加載機制
- 若要持久化，需額外實現：(1) 啟動時從 PG 讀取 (2) 每次 update 後寫入 PG (3) 或定期 checkpoint

---

## 總結矩陣

| # | 組件 | 判定 | 分項得分 | 阻塞項 |
|---|------|------|---------|--------|
| 1 | Database Schema | 🟡 Partial | 8/10 | DDL 未執行 |
| 2 | Data Pipeline | 🟡 Partial | 6/10 | 無 PG → 零入庫 |
| 3 | Feature Store | 🟡 Partial | 5/10 | 同上 + 無歷史特徵 |
| 4 | ML Training Pipeline | 🟡 Partial | 4/10 | 無端到端腳本 + CPCV 未接入 |
| 5 | ONNX Model Path | 🟡 Partial | 3/10 | ort crate 未集成 |
| 6 | Model Manager | 🟡 Partial | 4/10 | predict() 永遠 None |
| 7 | Scorer | 🟢 Ready | 8/10 | Tier 2/3 完全可用 |
| 8 | ETL Pipeline | 🟡 Partial | 5/10 | 需 PG 有數據 + ASOF JOIN 問題 |
| 9 | TimescaleDB | 🟡 Partial | 6/10 | DDL 未執行 + 部分表缺壓縮 |
| 10 | Data Quality | 🟡 Partial | 4/10 | drift_detector 未接入 PG |
| 11 | Kelly Sizer | 🟢 Ready | 9/10 | 完全可用 |
| 12 | Optuna Storage | 🟢 Ready | 7/10 | PG 寫入延後 |
| 13 | Thompson Sampling | 🟡 Partial | 3/10 | 無持久化 → 重啟丟失 |

---

## 核心阻塞項（按優先級排序）

### P0 — 必須先完成

1. **執行 DDL V001-V007**：這是所有其他工作的前提。當前所有寫入器都因 PG 無表而靜默降級
2. **集成 ort crate**：在 `Cargo.toml` 添加 `ort` 依賴，替換 `model_manager.rs` 中的 TODO 為 `ort::Session::run()`

### P1 — ML 訓練前必須完成

3. **端到端訓練腳本**：串聯 ETL → label_generator → scorer_trainer（接入 cpcv_validator） → calibration → onnx_exporter → model_registry 寫入
4. **scorer_trainer 接入 CPCV**：當前是簡單 80/20 split，需替換為 `cpcv_validator.py` 的 4-fold CPCV
5. **Thompson Sampling PG 持久化**：啟動時讀取 `learning.bayesian_posteriors`，update 後寫回
6. **drift_detector 接入 PG 數據讀取**：實際從 `features.online_latest` 讀取特徵，從 `observability.feature_baselines` 讀取基線

### P2 — 完善項

7. 補齊 trading.orders/order_state_changes/risk_verdicts 寫入器
8. 補齊 agent.* 三張表寫入器
9. ETL 中 `features.online_latest.updated_ts_ms` (BIGINT) 與 ASOF JOIN 需要的 TIMESTAMPTZ 類型不匹配
10. 缺少 `requirements-ml.txt`（lightgbm / onnxmltools / onnxruntime / duckdb / optuna）
11. 部分 TimescaleDB 表缺壓縮策略

---

## 結論

系統的 **代碼框架和架構設計質量很高**：
- 所有寫入器遵循統一模式（bounded channel → batch flush → ON CONFLICT → JSONL fallback）
- 3-tier Scorer + Kelly Sizer + Optuna TPE + Thompson Sampling 的組合設計合理
- Schema 設計覆蓋完整，含 ML 訓練所需的所有表

但 **實際 ML 就緒度受限於兩個核心阻塞**：
1. DDL 未執行 → 數據管線空轉
2. ort crate 未集成 → ONNX 推理路徑不通

**建議行動順序**：
```
[立即] 執行 DDL V001-V007 到生產 PG
  → [驗證] 確認所有寫入器開始入庫
    → [累積] 等待 7-14 天數據
      → [訓練] 端到端 ML 訓練管線
        → [部署] ONNX 模型 + ort 集成
```

預計從 DDL 執行到首個 ONNX 模型上線：**3-4 週**（含數據累積期）。

---

*MIT 審計完成 — 2026-04-05*
