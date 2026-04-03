# Phase 0a — PG Schema 基礎（W1，4/11-4/17，5 工作日）

> 前置：R-07 Go/No-Go 通過（4/10）
> DoD：8 Schema 可查 · 全部新表可 INSERT/SELECT · Grafana VIEW 正常 · 4429 tests 全綠

## 工作分解

| ID | 任務 | Agent | 依賴 | 並行組 | 時間 |
|----|------|-------|------|--------|------|
| 0a-01 | pg_dump 完整備份現有 11 表 | E1-A | — | G1 | 1h |
| 0a-02 | CREATE 8 個 Schema DDL（market/trading/agent/learning/features/observability/risk/optuna） | E1-B | — | G1 | 2h |
| 0a-03 | 版本化遷移框架 `sql/migrations/V001~V005` | E1-C | — | G1 | 2h |
| 0a-04 | Schema registry 文檔 | PA | — | G1 | 3h |
| 0a-05 | 現有 11 表加 `_legacy` 後綴 | E1-A | 0a-01 | G2 | 1h |
| 0a-06 | Grafana VIEW 橋接（零停機遷移） | E1-B | 0a-05 | G2 | 2h |
| 0a-07 | market.* 表（tickers/ob/trade_agg/klines/funding/OI/LSR/liq/regime） | E1-C | 0a-02 | G2 | 4h |
| 0a-08 | trading.* 表（context_snapshots 混合版/outcomes/signals/intents/verdicts/orders/fills） | E1-D | 0a-02 | G2 | 4h |
| 0a-09 | agent.* 表（messages/ai_invocations/state_changes） | E1-E | 0a-02 | G2 | 1h |
| 0a-10 | learning.* 表（10 張） | E1-A | 0a-02 | G3 | 3h |
| 0a-11 | features.* 表（online_latest/versions） | E1-B | 0a-02 | G3 | 1h |
| 0a-12 | observability.* 表（scorer_predictions/model_performance/drift_events/feature_baselines） | E1-C | 0a-02 | G3 | 2h |
| 0a-13 | risk.* 表（black_swan_events 普通表 + votes + correlation_pairs 長表） | E1-D | 0a-02 | G3 | 1h |
| 0a-14 | market.news_signals（7d chunk hypertable） | E1-E | 0a-02 | G3 | 1h |
| 0a-15 | 全部索引（B-tree + GIN） | E1-A | G2+G3 | G4 | 2h |
| 0a-16 | scorer_training_features VIEW（排除 outcome_*，防 leakage） | E1-B | 0a-10 | G4 | 1h |
| 0a-17 | **E2 代碼審查**：全部 DDL + VIEW + 索引 | E2 | G4 | — | 3h |
| 0a-18 | **E4 回歸**：4429 tests + Grafana dashboard 驗證 | E4 | 0a-17 | — | 2h |
| 0a-19 | CC/E3 安全審查：PG 連接密碼不硬編碼 | CC+E3 | 0a-17 | — | 1h |

## 工作鏈

```
Day 1: G1（4路）→ 0a-01/02/03 + PA 04
Day 2: G2（5路）→ 0a-05/06/07/08/09
Day 3: G3（5路）→ 0a-10/11/12/13/14
Day 4: G4（2路）→ 0a-15/16
Day 5: E2 + E4 + CC/E3
```

## 關鍵設計參考

- Decision Context 混合方案（15 扁平 + JSONB）：見融合方案 v0.5 §一 1.4
- Hypertable FK 改應用層 CHECK：見融合方案 v0.5 §一 1.5
- 完整表清單：見融合方案 v0.5 §一 1.2
