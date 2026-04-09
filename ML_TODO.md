# ML Pipeline TODO — 工作計劃清單
# ML Pipeline TODO — Work Plan
# 基於 2026-04-09 DB R/W + ML 管線全面審計
# Based on 2026-04-09 DB R/W + ML Pipeline Full Audit
# 審計報告：docs/audits/2026-04-09--db_rw_ml_pipeline_full_audit.md

最後更新：2026-04-10

> 依賴鏈：Session 0（地基）→ Session 1（Phase 5 P0）→ Session 2（ML 推理管線）→ Session 3（參數優化）→ Session 4（Teacher-Student）→ Session 5（基礎設施）
> 每個 Session 設計為 2-4 小時獨立可交付。Session 0 是所有後續的硬前置。

---

## Session 0 — 地基層（~1h，所有後續的硬前置）
## Session 0 — Foundation Layer (hard prerequisite for everything)

### 0-1 V004 DDL 審核 + 執行
- [ ] **0-1a** E2 審查 V004 DDL（`sql/migrations/V004__learning_features_obs_risk_tables.sql`）
  - 確認表結構與 Rust writer / Python reader 的欄位一致
  - 確認 Hypertable 分塊策略合理
  - 確認 index 覆蓋已知查詢模式
- [ ] **0-1b** E2 審查 V009 DDL（`sql/migrations/V009__phase4_ml_news_tables.sql`）
  - 重點：`learning.linucb_state` composite PK 與 Rust `state_io.rs` UPSERT 對齊
- [ ] **0-1c** 檢查 V005-V014 中哪些已執行、哪些未執行，列出完整缺口
- [ ] **0-1d** 在 dev/paper DB 上執行缺失的 migrations
- [ ] **0-1e** 驗證：每個 Rust writer 的 INSERT 欄位與對應表 DDL 完全匹配

### 0-2 LightGBM 安裝
- [ ] **0-2a** `pip install lightgbm>=4.0.0`
- [ ] **0-2b** 驗證：`python3 -c "import lightgbm; print(lightgbm.__version__)"`
- [ ] **0-2c** 跑一次 `python3 -m pytest program_code/ml_training/tests/test_scorer_trainer.py -v`

### 0-3 基線驗證
- [ ] **0-3a** 確認 `trading.fills` 有 ARCH-RC1 後的乾淨數據（`SELECT count(*), min(ts), max(ts) FROM trading.fills WHERE ts >= '2026-04-07'`）
- [ ] **0-3b** 確認 `trading.decision_context_snapshots` 有數據
- [ ] **0-3c** 確認 Rust engine 正在正常寫入（watchdog + `wc -l /tmp/openclaw/engine_results.jsonl`）

**交付物**：所有 learning/features/observability 表可用，LightGBM 可 import，數據基線確認。
**驗收**：`\dt learning.*` 列出 ≥10 表，`scorer_trainer` 測試 pass。

---

## Session 1 — Phase 5 P0 Edge 危機修復（~3h，當前最高優先級）
## Session 1 — Phase 5 P0 Edge Crisis Fix (current highest priority)

**前置**：Session 0 完成

### 1-1 cost_gate 邏輯統一（Rust 回補 Python 完整公式）
- [ ] **1-1a** 讀取 Python `cost_gate.py`（`program_code/local_model_tools/cost_gate.py:92-185`）提取完整公式
  - ATR% 歸一化：`atr_pct = atr / price`
  - win_rate 加權門檻：`min_move = round_trip_cost / max(0.3, win_rate) * 1.3`
  - slippage tier 查表：`SLIPPAGE_TIERS`（BTC 1bps → Meme 30bps）
  - daily_trade_count 安全閥：零交易日放寬邏輯
- [ ] **1-1b** 修改 Rust `intent_processor.rs::cost_gate_paper()`（~line 450-500）
  - 加入 ATR% 歸一化
  - 加入 slippage tier 查表（可從 ConfigStore 讀或硬編碼初版）
  - 加入 win_rate awareness（從 edge_estimates 擴展結構體）
  - 保留 James-Stein edge 查詢作為 override（edge > 0 時直接用 edge vs fee）
- [ ] **1-1c** E2 審查：確認 Rust 版與 Python 版在相同輸入下產出一致結果
- [ ] **1-1d** E4 回歸：`cargo test` 全量 + 新增 cost_gate 單元測試（≥5 cases）
- [ ] **1-1e** QA Audit：風控參數改動強制 QA

### 1-2 Realized Edge 數據驗證
- [ ] **1-2a** 跑 `realized_edge_stats.py --days 3` 確認 round-trip 配對正確
- [ ] **1-2b** 檢查 fills 中 `strategy_name` 和 `symbol` 填充率（不能有大量 NULL/unknown）
- [ ] **1-2c** 跑 James-Stein 重算：`james_stein_estimator.py --days 3`，更新 `settings/edge_estimates.json`

### 1-3 edge_estimates 結構擴展
- [ ] **1-3a** 擴展 `EdgeEstimate` struct 加入 `win_rate`、`n_trades`、`std_bps`
  - 影響：`edge_estimates.rs`、`james_stein_estimator.py` 輸出格式
- [ ] **1-3b** cost_gate_paper() 使用擴展後的 win_rate 做門檻加權

**交付物**：Rust cost_gate 與 Python 邏輯一致，edge_estimates 含 win_rate。
**驗收**：相同 (symbol, strategy, ATR, price) 輸入，Rust 和 Python 的 reject/accept 決策一致。

---

## Session 2 — ML 推理管線接線（~4h，Phase 2 核心）
## Session 2 — ML Inference Pipeline Wiring (Phase 2 core)

**前置**：Session 0 完成（V004 DDL 中 `features.online_latest` 表可用）

### 2-1 FeatureCollector 接線
- [ ] **2-1a** 在 `tick_pipeline.rs` 中加入 feature dispatch channel（`mpsc::Sender<FeatureSnapshot>`）
  - 在 indicators 計算完成後調用 `feature_collector.to_feature_vector()`
  - 通過 channel 發送到 feature_writer
- [ ] **2-1b** 實現 `feature_writer.rs` batch persistence
  - UPSERT 到 `features.online_latest`（symbol + ts_ms 為 key）
  - 可配置的 flush interval（默認 100ms）
  - 參考 `trading_writer.rs` 的 batch flush 模式
- [ ] **2-1c** 在 `main.rs` 中 spawn feature_writer task，接線 channel
- [ ] **2-1d** E2 審查 + E4 回歸

### 2-2 Parquet ETL 修復
- [ ] **2-2a** `parquet_etl.py` 的 `features.online_latest` 查詢加時間窗口過濾
  - 當前：`SELECT * FROM features.online_latest`（無時間過濾，含過期數據）
  - 修復：加 `WHERE updated_ts_ms >= extract(epoch from now() - interval '7 days') * 1000`
- [ ] **2-2b** 驗證 ETL 端到端：`python3 -m program_code.ml_training.parquet_etl --days 3`

### 2-3 Scorer 訓練端到端驗證
- [ ] **2-3a** 跑完整訓練管線：`python3 -m program_code.ml_training.run_training_pipeline`
  - ETL → Labels → CPCV → LightGBM → model.pkl
- [ ] **2-3b** 檢查輸出 model metrics（AUC、Brier Score、calibration curve）
- [ ] **2-3c** 若 metrics 合格，規劃 ONNX 導出（Phase 4 milestone，此 session 不做）

**交付物**：即時特徵從 tick_pipeline 寫入 DB，ETL 可提取，scorer 可訓練。
**驗收**：`features.online_latest` 有數據 + `run_training_pipeline` 無 error 完成。

---

## Session 3 — 參數優化管線（~3h，Phase 3）
## Session 3 — Parameter Optimization Pipeline (Phase 3)

**前置**：Session 0（V004 DDL）+ Session 2（features 可用）

### 3-1 Optuna 參數持久化
- [ ] **3-1a** 確認 `learning.ml_parameter_suggestions` 表結構與 `optuna_optimizer.py` 寫入欄位匹配
- [ ] **3-1b** 補上 `optuna_optimizer.py` 的 DB write path（目前標記為 TODO/deferred）
- [ ] **3-1c** 跑一次 dry-run：`python3 -m program_code.ml_training.optuna_optimizer --symbol BTCUSDT --strategy ma_crossover --n-trials 5`

### 3-2 Thompson Sampling 定位釐清
- [ ] **3-2a** 確認 TS 是 (A) offline 訓練工具 還是 (B) runtime 探索機制
  - 代碼顯示 (A)，v0.4 文檔暗示 (B)
  - 如果是 (A)：不需要 Rust bridge，只需 DB 持久化
  - 如果是 (B)：需要 Rust consumer + IPC
- [ ] **3-2b** 補上 `learning.bayesian_posteriors` 的 write path
- [ ] **3-2c** 更新文檔消歧

### 3-3 CPCV 結果持久化
- [ ] **3-3a** `cpcv_validator.py` 結果寫入 `learning.cpcv_results`
- [ ] **3-3b** 驗證 temporal embargo（24h gap）邏輯正確

### 3-4 策略參數更新機制
- [ ] **3-4a** 確認 Rust 端 `update_strategy_params` IPC 是否可用
  - 已知 `CONF-D conf scaling` 已完成（TODO.md 標記 ✅）
- [ ] **3-4b** 補上 Optuna best params → IPC patch → Rust hot-reload 的完整路徑
- [ ] **3-4c** E2 + E4

**交付物**：Optuna 可持久化建議，TS 定位明確，參數可從 Python 推送到 Rust。
**驗收**：`learning.ml_parameter_suggestions` 有數據，IPC patch 成功。

---

## Session 4 — Teacher-Student + LinUCB（~3h，Phase 4）
## Session 4 — Teacher-Student + LinUCB (Phase 4)

**前置**：Session 0（V009 DDL）

### 4-1 LinUCB Warm-Start 部署
- [ ] **4-1a** 確認 `linucb/state_io.rs::load_arms()` 能從 DB 讀取
- [ ] **4-1b** 測試冷啟動 → 寫入 → 重啟 → warm-start 完整流程
- [ ] **4-1c** 驗證 `schema_hash` fail-closed 邏輯（hash 不匹配時拒絕加載）
- [ ] **4-1d** 對應 TODO.md `4-06 LinUCB live warm-start deployment`

### 4-2 Teacher Directive 消費端
- [ ] **4-2a** 盤點 `claude_teacher/mod.rs` 現狀：是否有 directive reader？
- [ ] **4-2b** 設計 directive → intent_processor 的影響路徑
  - 選項 A：directive 修改 cost_gate 參數（輕量）
  - 選項 B：directive 直接生成 intent（重量，需完整治理鏈）
- [ ] **4-2c** 實現選定方案 + E2 + E4

### 4-3 Directive Outcome Backfill
- [ ] **4-3a** 確認 `directive_executions.outcome_pnl_*` 欄位（V012）可寫
- [ ] **4-3b** 啟用 `helper_scripts/phase4/backfill_directive_outcomes.py`
- [ ] **4-3c** 跑一次 backfill 驗證

**交付物**：LinUCB 可 warm-start，Teacher directive 有消費端，outcome 可回填。
**驗收**：引擎重啟後 LinUCB 狀態保持，directive count > 0。

---

## Session 5 — DB 基礎設施加固（~2h，非阻塞但重要）
## Session 5 — DB Infrastructure Hardening (non-blocking but important)

**前置**：無硬依賴，可任意時間做

### 5-1 Python 連接池
- [ ] **5-1a** 創建共用的 `db_pool.py` 模組
  - 使用 `psycopg2.pool.ThreadedConnectionPool`（min=2, max=10）
  - 或遷移到 `asyncpg`（如果 FastAPI async 路由夠多）
- [ ] **5-1b** 替換所有 `_get_pg_conn()` 調用點：
  - `strategy_read_routes.py:419-431`
  - `grafana_data_writer.py:69-83`
  - `phase4_routes.py` 中的連接調用
- [ ] **5-1c** E2 + E4

### 5-2 Dashboard 靜默失敗改善
- [ ] **5-2a** DB 連接失敗時返回 HTTP 503 + `{"error": "database_unavailable"}` 而非空數據
- [ ] **5-2b** 前端 JS 識別 503 並顯示告警 banner（而非空白）
- [ ] **5-2c** 添加 `/health/db` endpoint 供監控

### 5-3 trading.orders Writer（Phase 5+ 交付項）
- [ ] **5-3a** 設計 order lifecycle events（Created → Submitted → Filled → Cancelled）
- [ ] **5-3b** 在 Rust `batch_order_manager.rs` 中加入 order_writer channel
- [ ] **5-3c** 實現 order_writer.rs（INSERT + UPDATE on state change）
- [ ] **5-3d** E2 + E4

### 5-4 Deprecated 代碼清理
- [ ] **5-4a** 移除 `grafana_data_writer.py` 中的 deprecated legacy 寫入（Rust 已接管）
- [ ] **5-4b** 清理 `trading_raw` schema auto-creation → 遷移到 V015 managed migration

**交付物**：連接池上線，Dashboard 失敗可見，orders 可追溯。
**驗收**：Dashboard 在 DB 掛掉時顯示 503 告警，連接池 metrics 可查。

---

## Session 6 — Calibration + DL-3 + ONNX（~3h，精度優化，非阻塞）
## Session 6 — Calibration + DL-3 + ONNX (accuracy improvements, non-blocking)

**前置**：Session 2（scorer 可訓練）

### 6-1 Calibration 實現
- [ ] **6-1a** 在 `calibration.py` 中實現 Platt scaling + isotonic regression
- [ ] **6-1b** 整合到 `scorer_trainer.py`：訓練後自動校準
- [ ] **6-1c** 校準器與模型一起序列化（model.pkl + calibrator.pkl）
- [ ] **6-1d** Rust `scorer.rs` 加入 calibration post-processing（或通過 ONNX 內嵌）

### 6-2 DL-3 Foundation Model 評估
- [ ] **6-2a** 跑 `dl3_ab_runner.py` shadow 比較
- [ ] **6-2b** 跑 `dl3_go_no_go.py` 決策（accuracy > 75%? divergence < 10%?）
- [ ] **6-2c** 若通過，規劃 integration path

### 6-3 ONNX 導出 + ort Crate
- [ ] **6-3a** 實現 `onnx_exporter.py`（LightGBM → ONNX）
- [ ] **6-3b** 加 `ort` crate 到 `Cargo.toml`
- [ ] **6-3c** 激活 `model_manager.rs` 的 ONNX hot-swap
- [ ] **6-3d** 端到端：Python 訓練 → ONNX 導出 → Rust 加載 → 推理驗證

**交付物**：校準的模型 + ONNX 推理上線。
**驗收**：Rust `model_manager` 成功加載 ONNX，推理結果與 Python 一致（< 1e-5 diff）。

---

## 依賴圖 / Dependency Graph

```
Session 0 (地基)
  ├──→ Session 1 (Phase 5 P0 cost_gate)     ← 最高優先級
  ├──→ Session 2 (ML 推理管線)
  │       └──→ Session 3 (參數優化)
  │       └──→ Session 6 (Calibration/ONNX)
  ├──→ Session 4 (Teacher-Student/LinUCB)
  └──→ Session 5 (DB 基礎設施)               ← 可任意時間做
```

---

## 交叉引用 / Cross References

- 主 TODO：`TODO.md`（Phase 5/6/Live Gate 主線）
- 審計報告：`docs/audits/2026-04-09--db_rw_ml_pipeline_full_audit.md`
- ML 架構設計：`docs/references/2026-04-03--ml_dl_learning_architecture_v0.4.md`
- DB Schema：`sql/migrations/V001-V014`
- Phase 5 記憶：見 CLAUDE.md §十 + memory `project_phase5_promotion_edge_crisis.md`
