# Phase 5 — James-Stein + DL-1 + DL-2（W16-18，7/24-8/13，15 工作日）

> 前置：Phase 3b 完成（James-Stein）+ Phase 2 完成（DL-1/DL-2）
> DoD：JS 正確收斂 · DL-1 最優維度選定 · DL-2 Shadow 運行中 · 4429+20 tests

## 5 路並行

| ID | 任務 | Agent | 依賴 | 並行組 | 時間 |
|----|------|-------|------|--------|------|
| 5-01 | James-Stein per-parameter 獨立 shrinkage | E1-A | 3b | G1 | 6h |
| 5-02 | k-means 聚類（50 symbols → learning.symbol_clusters） | E1-B | Phase 2 | G1 | 4h |
| 5-03 | learning.james_stein_estimates UPSERT 寫入 | E1-C | 5-01 | G1 | 2h |
| 5-04 | DL-1 Symbol Embedding Autoencoder（4D/8D/12D 三版 + Denoising） | E1-D | Phase 2 | G1 | 10h |
| 5-05 | DL-2 Regime LSTM Shadow（vs 規則式 MarketRegimeTracker） | E1-E | Phase 2 | G1 | 10h |
| 5-06 | DL-1 最優維度選擇（reconstruction loss + downstream Scorer AUC） | E1-A | 5-04 | G2 | 4h |
| 5-07 | DL-2 Shadow 運行框架（LSTM vs 規則式 30 天並行統計比較） | E1-B | 5-05 | G2 | 4h |
| 5-08 | James-Stein + Scorer 整合（shrunk 參數 → update_params） | E1-C | 5-01,3a | G2 | 4h |
| 5-09 | risk.correlation_pairs 長表寫入（每日 50sym 上三角 1225 行） | E1-D | 0a | G2 | 3h |
| 5-10 | **E2 代碼審查** | E2 | all | — | 4h |
| 5-11 | **E4 回歸** | E4 | 5-10 | — | 4h |
| 5-12 | QC 數學驗證（JS shrinkage 正確性 + DL-1 embedding k-NN 驗證） | QC | 5-01,5-04 | — | 3h |
| 5-13 | **E5 優化審查** | E5 | 5-11 | — | 4h |

## James-Stein 注意事項

- 必須 per-parameter 獨立（不是統一 B），避免高/低方差參數 shrinkage 不均
- 策略加權 global mean：按 inverse-embargo weighting，避免 Grid（長 embargo）被低權重
