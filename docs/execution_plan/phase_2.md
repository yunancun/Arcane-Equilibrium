# Phase 2 — 交易鏈 + Scorer + ONNX（W6-9，5/15-6/11，20 工作日含 buffer）

> 前置：Phase 1 完成 + Paper 數據採集中
> DoD：Context Snapshot 可寫入/查詢 · Scorer AUC>0.55 · ONNX err<1e-3 · Rust推理<1ms · `test_scorer_feature_alignment` 通過 · ETL cron 正常 · 4429+60 tests

## 最大 Phase，分 5 個並行組 + 2 輪 E2

### G1 (Day1-3): trading 表寫入
- 2-01: trading.signals 寫入（含 context_id 應用層 CHECK）
- 2-02: trading.intents + risk_verdicts
- 2-03: trading.orders + order_state_changes（事件溯源）
- 2-04: trading.fills + position_snapshots
- 2-05: agent.messages（inter-agent 消息持久化）

### G2 (Day4-6): Decision Context + Outcome
- 2-06: Decision Context Snapshot 收集器（混合：15 扁平 + JSONB）
- 2-07: decision_context_repo.py 封裝模組
- 2-08: agent.ai_invocations + state_changes
- 2-09: Outcome 回填 cron → trading.decision_outcomes（普通表，非 hypertable UPDATE）
- 2-10: Outcome 5 窗口（1m/5m/1h/4h/24h）+ max_favorable/max_adverse

### G3 (Day7-10): LightGBM Scorer
- 2-11: LightGBM Scorer 訓練管線（y = winsorized(net_pnl/max(atr, ATR_FLOOR)), ±Y_MAX, is_extreme 特徵）
- 2-12: ATR_FLOOR 動態化（rolling_quantile q=0.05 window=30d）
- 2-13: Isotonic regression 校準 + Gaussian smoothing + 新舊 damping（α=0.3）
- 2-14: TabPFN 基線 Scorer（零調參對比）
- 2-15: Echo Chamber 防護（5-10% 強制探索 + IPW + virtual outcome + coverage 監控）

### G4 (Day11-13): 防護 + 工具 + ETL
- 2-16: JSONB Feature Leakage 防護（白名單 + CI 靜態分析）
- 2-17: Scorer Ensemble 多變體（含 orderbook 微觀結構）+ consensus reliability monitor
- 2-18: SHAP TreeExplainer + temporal stability + OOS permutation importance
- 2-19: Phase 2 回測 bootstrap（BacktestEngine 歷史數據 → 初始訓練集）
- 2-20: ONNX 精度 PoC（Python vs Rust，1000+ 樣本，max abs err < 1e-3，f32 顯式轉換，無 native categorical）
- 2-24: Parquet ETL 日常 cron（DuckDB COPY PG → Parquet）

### G5 (Day14-16): Rust ONNX
- 2-21: Rust ml_scorer.rs（ArcSwap<ort::Session> + notify hot-reload，零鎖）
- 2-22: ONNX → Rust 推理整合（f32 + NaN sentinel + 維度校驗）
- 2-23: **集成測試** `test_scorer_feature_alignment`（FeatureCollector 維度 == ONNX 輸入維度）
- 2-25: DuckDB 指標重算引擎（klines Parquet → 向量化重算，<20min for 6mo）

### 審查 (Day17-20)
- 2-26: **E2**（兩輪：DB 側 + ML 側）
- 2-27: **E4**（全量 tests + ONNX < 1ms + DB 不阻塞）
- 2-28: **E5**

## 關鍵技術決策

- Scorer 標籤：`y = clip(net_pnl/max(ATR, ATR_FLOOR), Y_LO_1pct, Y_HI_99pct)` + `is_extreme` boolean 特徵
- 校準：isotonic regression（非 Platt），用 CPCV OOS folds，ECE < 0.05
- ONNX：不用 LightGBM native categorical → 全手動 one-hot；NaN 用 sentinel 值處理
- Rust：ArcSwap 零鎖（不用 RwLock），加載失敗保留舊模型
