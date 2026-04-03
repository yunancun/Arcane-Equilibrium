# Phase 1 — 市場數據止血 + FeatureCollector + PSI（W4-5，5/01-5/14，10 工作日）

> 前置：Phase 0b 完成
> DoD：FeatureCollector <0.1ms · PG 異步不阻塞 tick · PSI+ADWIN 可 WARNING/ALERT · ExperimentLedger PG · Paper 數據採集中 · 4429+30 tests

## 工作分解

| ID | 任務 | Agent | 依賴 | 並行組 | 時間 |
|----|------|-------|------|--------|------|
| 1-01 | Ring buffer（5min/3000條/600KB/drop-oldest） | E1-A | 0b | G1 | 6h |
| 1-02 | FeatureCollector 主類（tick→buffer→異步 batch flush→PG） | E1-B | 0b | G1 | 8h |
| 1-03 | klines → market.klines（KlineManager cache → PG batch INSERT） | E1-C | 0b | G1 | 4h |
| 1-04 | WS → market.market_tickers（5s 快照） | E1-D | 0b | G1 | 4h |
| 1-05 | regime → market.regime_snapshots/transitions | E1-E | 0b | G1 | 3h |
| 1-06 | Flush ���敗 JSONL fallback + PG 恢復後回灌 | E1-A | 1-01 | G2 | 3h |
| 1-07 | WS orderbook → market.ob_snapshots（L5 1m summary） | E1-B | 0b | G2 | 4h |
| 1-08 | 逐筆 trade → market.trade_agg_1m（每分鐘聚合） | E1-C | 0b | G2 | 4h |
| 1-09 | funding_rates/open_interest/long_short_ratio → market.* | E1-D | 0b | G2 | 3h |
| 1-10 | indicators ��� features.online_latest（UPSERT per symbol×TF） | E1-E | 1-03 | G2 | 4h |
| 1-11 | PSI 漂���檢測（重疊滑動窗口 30d×7d + block bootstrap CI） | E1-A | 1-02 | G3 | 6h |
| 1-12 | feature_baselines 初始化（每季度 rolling 6m 分位數重建 bin_edges） | E1-B | 1-10 | G3 | 4h |
| 1-13 | ADWIN 監控（delta=0.005 + EMA-smoothed Brier score 輸入） | E1-C | 1-11 | G3 | 4h |
| 1-14 | ExperimentLedger JSON→PG 遷移（雙寫→驗證一致性→關 JSON） | E1-D | 0b | G3 | 6h |
| 1-15 | Hypothesis 擴展 3 字段（source_type/metadata/trigger_condition） | E1-E | 1-14 | G3 | 3h |
| 1-16 | Paper Trading 數據採集啟動（為 Phase 2 Scorer bootstrap） | E1-A | 1-03 | G4 | 2h |
| 1-17 | 特徵版本號機制（features.versions 表 + 版本 ID 綁定） | E1-B | 1-10 | G4 | 3h |
| 1-18 | **E2 代碼審查** | E2 | all | — | 4h |
| 1-19 | **E4 回歸**（+ FeatureCollector <0.1ms benchmark） | E4 | 1-18 | — | 4h |
| 1-20 | **E5 優化審查** | E5 | 1-19 | — | 3h |

## FeatureCollector 規格

- Ring buffer = 5min = ~3000 條（~600 KB）
- 溢出策略：drop-oldest（tick SLA 不允許 back-pressure）
- Batch flush 間隔：1s
- 連續 3 次 flush 失敗 → JSONL 文件 fallback，PG 恢復後回灌
- 必須是純記憶體操���（從 pipeline ���� state 讀取，���做 I/O）
- 切入點��PipelineBridge._tick_run_strategies() 末尾
