# ML Pipeline TODO — 工作計劃清單
# ML Pipeline TODO — Work Plan
# 基於 2026-04-09 DB R/W + ML 管線全面審計
# Based on 2026-04-09 DB R/W + ML Pipeline Full Audit
# 審計報告：docs/audits/2026-04-09--db_rw_ml_pipeline_full_audit.md

最後更新：2026-04-10（S0+S1+S2+S3-1/2/3+S5-1/2 完成）

> 依賴鏈：Session 0（地基）→ Session 1（Phase 5 P0）→ Session 2（ML 推理管線）→ Session 3（參數優化）→ Session 4（Teacher-Student）→ Session 5（基礎設施）
> 每個 Session 設計為 2-4 小時獨立可交付。Session 0 是所有後續的硬前置。

---

## Session 0 — 地基層 ✅ COMPLETE（2026-04-10）
## Session 0 — Foundation Layer ✅

### 0-1 V004 DDL 審核 + 執行
- [x] **0-1a~e** 所有 V001-V014 DDL 已全部執行。learning(18), features(2), observability(6), risk(3), trading(9) 表全部存在。
  - 審計報告稱 V004 "DRAFT" 是過時信息，表已建好。
  - 小缺口：trading_writer fills 缺 fee_currency/details（nullable，不影響運行），feature_writer 缺 foundation_model_features（nullable）。

### 0-2 LightGBM 安裝
- [x] **0-2a/b** LightGBM 4.6.0 已安裝到 venv
- [x] **0-2c** 無 test_scorer_trainer.py。ML 測試套件：135 passed, 0 failed（label_generator 2 個修復）

### 0-3 基線驗證
- [x] **0-3a** trading.fills: 2837 rows since 2026-04-07（ARCH-RC1 乾淨數據）
- [x] **0-3b** decision_context_snapshots: 18.2M rows
- [x] **0-3c** Engine 未運行但數據完整

**交付物**：所有表可用 ✅，LightGBM 可 import ✅，數據基線確認 ✅。

---

## Session 1 — Phase 5 P0 Edge 危機修復 ✅ COMPLETE（2026-04-10）
## Session 1 — Phase 5 P0 Edge Crisis Fix ✅

### 1-1 cost_gate 邏輯統一
- [x] **1-1a/b** Rust `cost_gate_paper()` + `cost_gate_live()` 已統一：
  - 5-tier slippage lookup（匹配 Python SLIPPAGE_TIERS）
  - ATR% 歸一化（冷啟動路徑：`atr_pct = (atr/price)*100`）
  - win_rate 加權門檻（JS 路徑：`threshold = fee_bps / max(0.3, wr) × 1.3`）
  - 費用計算含滑點：`fee_bps = 2 × (fee_rate + slippage) × 10000`
- [x] **1-1d** 838 lib tests passed（+3 new: slippage_tier, js_win_rate, high_volume）

### 1-2 Realized Edge 數據驗證
- [ ] **1-2a~c** 待引擎重啟後用 `--days 3` 重跑（TODO.md 排程 2026-04-11）

### 1-3 edge_estimates 結構擴展
- [x] **1-3a** `CellEstimate` struct 加入 `win_rate`, `n_trades`, `std_bps`。JSON 解析器讀取 `win_rate_shrunk`/`win_rate`/`n`/`std_bps`。新增 `load_from_str()` 便捷方法。
- [x] **1-3b** cost_gate_paper() + cost_gate_live() 使用 `win_rate` 加權門檻。

**交付物**：Rust cost_gate 與 Python 公式對齊 ✅，edge_estimates 含 win_rate ✅。

---

## Session 2 — ML 推理管線接線 ✅ COMPLETE（2026-04-10）
## Session 2 — ML Inference Pipeline Wiring ✅

### 2-1 FeatureCollector 接線
- [x] **2-1a~d** 審計報告過時 — FeatureCollector 已完整接線：
  - `tick_pipeline.rs:1389` 通過 `try_send()` 分派 FeatureSnapshot
  - `main.rs:1276` 創建 mpsc channel（cap=2048）
  - `main.rs:1294` spawn `run_feature_writer()` 任務
  - `feature_writer.rs` 完整實現 dedup + batch UPSERT

### 2-2 Parquet ETL 修復
- [x] **2-2a** 已加時間窗口過濾：`WHERE updated_ts_ms >= {start_epoch_ms}`
- [ ] **2-2b** 端到端驗證待引擎運行後執行

### 2-3 Scorer 訓練端到端驗證
- [ ] **2-3a~c** 待引擎累積足夠數據後執行

**交付物**：FeatureCollector 已接線 ✅，ETL 已修復 ✅。

---

## Session 3 — 參數優化管線（~3h，Phase 3）
## Session 3 — Parameter Optimization Pipeline (Phase 3)

**前置**：Session 0（V004 DDL）+ Session 2（features 可用）

### 3-1 Optuna 參數持久化 ✅ COMPLETE（2026-04-10）
- [x] **3-1a** 表結構匹配：V004 DDL `learning.ml_parameter_suggestions` 與 `_persist_suggestion()` INSERT 欄位對齊
- [x] **3-1b** `optuna_optimizer.py` DB write path 已實現：`_persist_suggestion()` + `_get_ml_pg_conn()`，fail-soft
- [ ] **3-1c** 跑一次 dry-run（需引擎 fills 數據）

### 3-2 Thompson Sampling 定位釐清 ✅ COMPLETE（2026-04-10）
- [x] **3-2a** 確認 TS 是 **(A) offline 訓練工具**（Python-only，Phase 3b）。Rust inference 延後到 Phase 4 E5-D3。
- [x] **3-2b** `learning.bayesian_posteriors` write path **已存在**：`thompson_sampling.py` 已實現完整 UPSERT + load。
- [ ] **3-2c** 更新文檔消歧（低優先級）

### 3-3 CPCV 結果持久化 ✅ COMPLETE（2026-04-10）
- [x] **3-3a** `cpcv_validator.py` → `_persist_cpcv_result()` 寫入 `learning.cpcv_results`，fail-soft
- [x] **3-3b** Temporal embargo 邏輯正確：`get_embargo_hours()` 按策略類型分級（trending=24h, reversion=4h, arb=8h, grid=72h）

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

### 5-1 Python 連接池 ✅ COMPLETE（2026-04-10）
- [x] **5-1a** 創建 `app/db_pool.py`：`psycopg2.pool.ThreadedConnectionPool`（min=2, max=10），singleton pattern，env var 可配
- [x] **5-1b** 替換調用點：`grafana_data_writer.py` + `strategy_read_routes.py` 委託到 `db_pool.get_conn()`/`put_conn()`
  - `phase4_routes.py` 待確認是否有獨立連接（低優先級）
- [x] **5-1c** E2 + E4：2678 passed, 1 pre-existing fail

### 5-2 Dashboard 靜默失敗改善 ✅ PARTIAL（2026-04-10）
- [x] **5-2a** `strategy_read_routes.py` 三個 PG 路由：DB 失敗返回 HTTP 503 + `{"error": "database_unavailable"}`
- [ ] **5-2b** 前端 JS 識別 503 並顯示告警 banner（低優先級 — 前端 JS 改動）
- [x] **5-2c** `/api/v1/health/db` endpoint 已加入 `legacy_routes.py`：連接池統計 + SELECT 1 探測

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
