# Phase 3b — Optuna + Thompson Sampling + CPCV + 黑���鵝（W11-12，6/19-7/02，10 工作日）

> 前置：Phase 3a 完成
> DoD：TPE+TS 可跑 · CPCV 分級 embargo · 黑天鵝投票 · `test_optuna_to_ts_pipeline` 通過 · 4429+40 tests

## 5 路並行

| ID | 任務 | Agent | 依賴 | 並行組 | 時間 |
|----|------|-------|------|--------|------|
| 3b-01 | Optuna RDBStorage → PG optuna schema + study 命名 `{strategy}_{symbol}_{regime}` | E1-A | 3a | G1 | 4h |
| 3b-02 | TPE within-strategy ���數優���管線（Optuna → update_params） | E1-B | 3b-01 | G1 | 8h |
| 3b-03 | CPCV 4-fold + 分級 embargo（趨勢 24h / 回歸 4h / 套利 8h / 網格 72h）+ purge/embargo 分離 | E1-C | Phase 2 | G1 | 8h |
| 3b-04 | CPCV power guard（power < 0.5 → 結果僅參考） | E1-D | 3b-03 | G2 | 2h |
| 3b-05 | Thompson Sampling NIG posterior（across-strategy 資源分配，非 within-strategy） | E1-E | 3a | G1 | 6h |
| 3b-06 | NIG Empirical Bayes 初始化（kappa=3 + 前 10 trial 50% exploitation floor） | E1-A | 3b-05 | G2 | 3h |
| 3b-07 | BH-FDR 多重比較校正（25幣×5策略×3regime = 375 假設） | E1-B | 3b-02 | G2 | 4h |
| 3b-08 | Grid 多目標 Pareto（Efficiency × Inventory_Risk time-weighted 95th pct）+ live vs backtest frontier | E1-C | 3a | G2 | 6h |
| 3b-09 | 黑天鵝 4 信號投票（6×MAD / corr>0.85 / 5×volume / velocity）全基於 kline return | E1-D | Phase 1 | G2 | 6h |
| 3b-10 | risk.black_swan_events（普通表）+ risk.black_swan_votes 寫入 | E1-E | 3b-09 | G2 | 2h |
| 3b-11 | PG → Parquet 每日 ETL 正式上線 + DuckDB label 生成 | E1-A | Phase 2 | G3 | 4h |
| 3b-12 | **集成測試** `test_optuna_to_ts_pipeline`（合成數據 TPE→TS 完整迴路） | E1-B | 3b-02,3b-05 | G3 | 4h |
| 3b-13 | PSI 基線切換後 7 天重建邏輯 | E1-C | Phase 1 | G3 | 3h |
| 3b-14 | **E2 代碼審查** | E2 | all | — | 5h |
| 3b-15 | **E4 回歸** + 集成測試 | E4 | 3b-14 | — | 4h |
| 3b-16 | **E5 優化審查**（Phase 3 全體） | E5 | 3b-15 | — | 4h |
| 3b-17 | QC 數學驗證（CPCV embargo 正確性 + NIG posterior 收斂性） | QC | 3b-03,3b-05 | — | 3h |

## TPE vs TS 分層（關鍵設計）

```
Layer 1（Optuna TPE）= within-strategy 參數優化
  一個 (strategy, symbol, regime) 內找最優 adx_threshold 等

Layer 2（Thompson Sampling NIG）= across-strategy 資源分配
  決定下一個 trial 分配給哪個 (strategy, symbol, regime) pair
  用 Normal-InverseGamma 而非 Beta（outcome 是連續值非二元）
```
