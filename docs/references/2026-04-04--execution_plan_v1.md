# 融合方案執行計劃 V1：DB + ML/DL + 新聞 Agent
# Execution Plan V1: DB + ML/DL + News Agent
# 基於融合方案 v0.5（兩輪審計 + DB 專題 + 四角色聯合驗證）
# 日期：2026-04-04
# 起算日：2026-04-11（R-07 Go/No-Go 後）
# 預計完成：2026-08-27（20 週 + 21 天 buffer = 105 工作日）

---

## 排期總覽

```
Phase 0a  (W1,    4/11-4/17):  PG Schema 基礎（8 schema + 全部 DDL）
Phase 0b  (W2-3,  4/18-4/30):  TimescaleDB 啟用 + 依賴準備
Phase 1   (W4-5,  5/01-5/14):  市場數據止血 + FeatureCollector + PSI
Phase 2   (W6-9,  5/15-6/11):  交易鏈 + Decision Context + Scorer + ONNX PoC [+1w buffer]
Phase 3a  (W9-10, 6/05-6/18):  update_params() 改造（AGT-1）
Phase 3b  (W11-12,6/19-7/02):  Optuna TPE + Thompson Sampling + CPCV + 黑天鵝
Phase 4   (W13-15,7/03-7/23):  Claude Teacher + LinUCB + 新聞接口 + DL-3 實驗
Phase 5   (W16-18,7/24-8/13):  James-Stein + DL-1 + DL-2
Phase 6   (W19-20,8/14-8/27):  漸進放權 + 驗收 + 壓測 + 文檔

Total: 105 工作日 / 21 週（含 20% buffer）
```

---

## Phase 0a — PG Schema 基礎（W1，5 工作日）

### 工作分解

| ID | 任務 | Agent | 依賴 | 並行組 | 時間 |
|----|------|-------|------|--------|------|
| 0a-01 | pg_dump 完整備份現有 11 表 | E1-A | — | G1 | 1h |
| 0a-02 | CREATE 8 個 Schema DDL | E1-B | — | G1 | 2h |
| 0a-03 | 版本化遷移框架 `sql/migrations/V001~V005` | E1-C | — | G1 | 2h |
| 0a-04 | Schema registry 文檔 | PA | — | G1 | 3h |
| 0a-05 | 現有 11 表加 `_legacy` 後綴 | E1-A | 0a-01 | G2 | 1h |
| 0a-06 | Grafana VIEW 橋接（零停機） | E1-B | 0a-05 | G2 | 2h |
| 0a-07 | market.* 表（tickers/ob/trade_agg/klines/funding/OI/LSR/liq/regime） | E1-C | 0a-02 | G2 | 4h |
| 0a-08 | trading.* 表（context_snapshots 混合版/outcomes/signals/intents/verdicts/orders/fills） | E1-D | 0a-02 | G2 | 4h |
| 0a-09 | agent.* 表 | E1-E | 0a-02 | G2 | 1h |
| 0a-10 | learning.* 表（10 張） | E1-A | 0a-02 | G3 | 3h |
| 0a-11 | features.* 表 | E1-B | 0a-02 | G3 | 1h |
| 0a-12 | observability.* 表（4 張，含 feature_baselines valid_from/until） | E1-C | 0a-02 | G3 | 2h |
| 0a-13 | risk.* 表（black_swan 普通表 + votes + correlation_pairs 長表） | E1-D | 0a-02 | G3 | 1h |
| 0a-14 | market.news_signals（7d chunk） | E1-E | 0a-02 | G3 | 1h |
| 0a-15 | 全部索引 | E1-A | G2+G3 | G4 | 2h |
| 0a-16 | scorer_training_features VIEW（防 leakage） | E1-B | 0a-10 | G4 | 1h |
| 0a-17 | **E2 代碼審查** | E2 | G4 | — | 3h |
| 0a-18 | **E4 回歸**（4429 tests + Grafana 正常） | E4 | 0a-17 | — | 2h |
| 0a-19 | CC/E3 安全審查 | CC+E3 | 0a-17 | — | 1h |

**並行：G1(4路 Day1) → G2(5路 Day2) → G3(5路 Day3) → G4(2路 Day4) → E2/E4(Day5)**

**DoD：** 8 Schema 可查 · 全部新表可 INSERT/SELECT · Grafana VIEW 正常 · 4429 tests 全綠

---

## Phase 0b — TimescaleDB 啟用（W2-3，10 工作日）

### 工作分解

| ID | 任務 | Agent | 依賴 | 並行組 | 時間 |
|----|------|-------|------|--------|------|
| 0b-01 | Docker image 切換腳本 + checklist | E1-A | 0a | G1 | 4h |
| 0b-02 | 備份 → 切 image → 驗證 extension loaded | E1-A | 0b-01 | G1 | 2h |
| 0b-13 | requirements-ml.txt（scikit-learn/lightgbm/duckdb） | E1-B | — | G1 | 2h |
| 0b-15 | OU Grid 公式修正 Python + Rust `sqrt(2)` | E1-D | — | G1 | 2h |
| 0b-03~05 | 啟用 hypertable（3 路並行，market/trading/learning+obs+risk） | E1-B/C/D | 0b-02 | G2 | 2h ea |
| 0b-06 | 壓縮策略（segmentby + compress_after） | E1-E | G2 | G3 | 3h |
| 0b-07 | Retention policy | E1-A | G2 | G3 | 2h |
| 0b-08 | sync_commit 分層配置 | E1-B | 0b-02 | G3 | 1h |
| 0b-12 | PG shared_buffers=8GB + OS 調優 | E1-A | 0b-02 | G3 | 1h |
| 0b-09 | grafana_data_writer 改寫（docker exec → psycopg2 直連 + 新 schema） | E1-C | 0b-06 | G4 | 6h |
| 0b-10 | Grafana datasource timescaledb:true | E1-D | 0b-02 | G4 | 1h |
| 0b-11 | 連續聚合（klines 1m → 5m/15m/1h/4h/1d） | E1-E | 0b-03 | G4 | 4h |
| 0b-14 | ML 降級分層策略（L0/L1/L2 fallback） | E1-C | 0b-13 | G4 | 4h |
| 0b-16 | **E2 代碼審查** | E2 | G4 | — | 4h |
| 0b-17 | **E4 回歸** | E4 | 0b-16 | — | 3h |
| 0b-18 | E3 安全審查 | E3 | 0b-16 | — | 1h |
| 0b-19 | **E5 優化審查**（Phase 0 全體） | E5 | 0b-17 | — | 3h |

**DoD：** TimescaleDB hypertable 可壓縮/retention · 連續聚合正常 · Grafana 正常 · OU 修正 · 4429+ tests

---

## Phase 1 — 市場數據止血 + FeatureCollector + PSI（W4-5，10 工作日）

| ID | 任務 | Agent | 依賴 | 並行組 | 時間 |
|----|------|-------|------|--------|------|
| 1-01 | Ring buffer（5min/3000條/drop-oldest） | E1-A | 0b | G1 | 6h |
| 1-02 | FeatureCollector 主類（tick→buffer→異步 flush→PG） | E1-B | 0b | G1 | 8h |
| 1-03 | klines → market.klines | E1-C | 0b | G1 | 4h |
| 1-04 | WS → market.market_tickers（5s 快照） | E1-D | 0b | G1 | 4h |
| 1-05 | regime → market.regime_snapshots/transitions | E1-E | 0b | G1 | 3h |
| 1-06 | Flush 失敗 JSONL fallback + PG 恢復回灌 | E1-A | 1-01 | G2 | 3h |
| 1-07 | WS → market.ob_snapshots（L5 1m summary） | E1-B | 0b | G2 | 4h |
| 1-08 | 逐筆 trade → market.trade_agg_1m | E1-C | 0b | G2 | 4h |
| 1-09 | funding/OI/LSR → market.* 永久表 | E1-D | 0b | G2 | 3h |
| 1-10 | indicators → features.online_latest（UPSERT） | E1-E | 1-03 | G2 | 4h |
| 1-11 | PSI 漂移檢測（重疊滑動窗口 + block bootstrap） | E1-A | 1-02 | G3 | 6h |
| 1-12 | feature_baselines 初始化（quarterly rolling 6m） | E1-B | 1-10 | G3 | 4h |
| 1-13 | ADWIN 監控（delta=0.005 + EMA-smoothed input） | E1-C | 1-11 | G3 | 4h |
| 1-14 | ExperimentLedger JSON→PG 遷移 | E1-D | 0b | G3 | 6h |
| 1-15 | Hypothesis 擴展 3 字段（source_type/metadata/trigger） | E1-E | 1-14 | G3 | 3h |
| 1-16 | Paper Trading 數據採集啟動 | E1-A | 1-03 | G4 | 2h |
| 1-17 | 特徵版本號機制 | E1-B | 1-10 | G4 | 3h |
| 1-18 | **E2** | E2 | all | — | 4h |
| 1-19 | **E4**（+ FeatureCollector <0.1ms benchmark） | E4 | 1-18 | — | 4h |
| 1-20 | **E5** | E5 | 1-19 | — | 3h |

**DoD：** FeatureCollector <0.1ms · PG 異步不阻塞 tick · PSI+ADWIN 可 WARNING/ALERT · ExperimentLedger PG · Paper 數據採集中 · 4429+30 tests

---

## Phase 2 — 交易鏈 + Scorer + ONNX（W6-9，20 工作日含 buffer）

**最大 Phase，分 5 個並行組 + 2 輪 E2：**

- **G1 (Day1-3):** trading.* 表寫入（signals/intents/verdicts/orders/fills + agent.messages）
- **G2 (Day4-6):** Decision Context 收集器 + repo 封裝 + outcome 回填 cron（5 窗口）
- **G3 (Day7-10):** LightGBM Scorer 訓練 + ATR_FLOOR 動態 + isotonic + TabPFN + Echo Chamber 防護
- **G4 (Day11-13):** JSONB leakage 防護 + Ensemble + SHAP + 回測 bootstrap + ONNX PoC + Parquet ETL
- **G5 (Day14-16):** Rust ml_scorer.rs（ArcSwap+ort+notify）+ 精度校驗 + 集成測試 + DuckDB 重算引擎
- **E2/E4/E5 (Day17-20):** 兩輪審查 + 回歸 + 優化

**DoD：** Context Snapshot 可寫入/查詢 · Scorer AUC>0.55 · ONNX err<1e-3 · Rust推理<1ms · `test_scorer_feature_alignment` 通過 · ETL cron 正常 · 4429+60 tests

---

## Phase 3a — update_params() 改造（W9-10，10 工作日，= AGT-1）

**Rust 與 Python 完全並行：**
- Day 1: PA 設計接口（3a-01/3a-02 並行）
- Day 2-5: Python 5 策略 ‖ Rust 5 策略（5 路 E1）
- Day 6-7: Python tests ‖ Rust tests
- Day 8: Python-Rust 交叉一致性測試
- Day 9-10: E2 + E4

**DoD：** 10 個 update_params() · 50+ 新 tests · Python-Rust 行為一致 · 全量全綠

---

## Phase 3b — Optuna + TS + CPCV + 黑天鵝（W11-12，10 工作日）

**5 路並行：** Optuna TPE / TS NIG / CPCV 4-fold / 黑天鵝 4 信號 / ETL+DuckDB labels
- Day 6: QC 數學驗證（CPCV embargo + NIG 收斂性）
- Day 7: `test_optuna_to_ts_pipeline` 集成測試

**DoD：** TPE+TS 可跑 · CPCV 分級 embargo · 黑天鵝投票 · `test_optuna_to_ts_pipeline` 通過 · 4429+40 tests

---

## Phase 4 — Claude Teacher + LinUCB + News + DL-3（W13-15，15 工作日）

**5 路並行：** Claude Teacher / LinUCB / News 接口 / DL-3 實驗 / Model Performance 監控
- DL-3 Go/No-Go 決策：AUC 提升 < 0.01 → 棄用
- `test_full_learning_loop` 端到端集成測試

**DoD：** Claude Directive → ExperimentLedger · LinUCB 可用 · News mock 接口 · DL-3 決策 · 3 個集成測試全通過 · 4429+50 tests

---

## Phase 5 — James-Stein + DL-1 + DL-2（W16-18，15 工作日）

**5 路並行：** JS per-parameter / k-means / DL-1 Autoencoder / DL-2 LSTM Shadow / correlation_pairs
- QC 驗證 JS shrinkage + DL-1 embedding quality

**DoD：** JS 正確收斂 · DL-1 最優維度選定 · DL-2 Shadow 運行中 · 4429+20 tests

---

## Phase 6 — 驗收（W19-20，10 工作日）

**5 路並行：** 放權管線 / 畢業邏輯 / 回放測試 / 壓測 / 文檔
- QA 端到端驗收 · PM 最終確認 · 版本 tag

**DoD：** 4 階段放權可流轉 · 壓測 SLA 全通過 · EvolutionEngine deprecated · 4629+ tests 全綠 · QA 簽核

---

## 關鍵路徑

```
0a-02(Schema) → 0b-02(TimescaleDB) → 1-02(FeatureCollector) → 2-06(Context Snapshot) 
→ 2-11(Scorer) → 2-21(Rust ONNX) → 3a-01(update_params API) → 3b-02(Optuna TPE) 
→ 3b-05(Thompson Sampling) → 6-01(放權管線)
```
**9 個關鍵任務，耽誤任何一個延遲整體。**

**有 Float：** DL-3(可砍) · DL-1/DL-2(可延後) · News(mock 無真實依賴) · 文檔(可並行)

---

## Contingency

| 超時 | 動作 |
|------|------|
| Phase 0 +50% | 砍 VIEW 橋接，Dashboard 暫斷 |
| Phase 1 +50% | PSI/ADWIN 延到 Phase 3b |
| Phase 2 +50% | ONNX PoC 延到 Phase 4，先 Python-only Scorer |
| Phase 3a +50% | 只做 Python 5 策略，Rust 延到 Phase 5 |
| Phase 3b +50% | 砍 BH-FDR + Grid Pareto，只做 TPE+TS 核心 |
| Phase 4 +50% | 砍 DL-3 + LinUCB |
| Phase 5 +50% | 砍 DL-1 + DL-2，只做 James-Stein |

---

## 量化指標

| 指標 | 目標 |
|------|------|
| Tests | 4629+（新增 200+） |
| FeatureCollector | < 0.1ms/tick |
| ONNX 推理 | < 1ms |
| PG 寫入 | 不阻塞 tick（異步） |
| 日存儲量 | ~0.17 GB/day ±20% |
| PG 活躍數據 | < 20 GB |
| Scorer AUC | > 0.55 |
| ONNX 精度 | max abs err < 1e-3 |
| Context 完整率 | > 95% signals have context |

---

*V1 · 2026-04-04 · 基於融合方案 v0.5 · 67 項審計修正 · 8+4 角色聯合驗證*
*前置文件：docs/references/2026-04-04--unified_db_ml_news_workplan_draft_v0.1.md (v0.5)*
