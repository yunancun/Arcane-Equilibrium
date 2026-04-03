# Phase 6 — 驗收（W19-20，8/14-8/27，10 工作日）

> 前置：Phase 5 完成
> DoD：4 階段放權可流轉 · 壓測 SLA 全通過 · EvolutionEngine deprecated · 4629+ tests · QA 簽核

## 5 路並行

| ID | 任務 | Agent | 依賴 | 並行組 | 時間 |
|----|------|-------|------|--------|------|
| 6-01 | learning.promotion_pipeline 管線（LEARNING→PAPER→DEMO→LIVE） | E1-A | Phase 5 | G1 | 8h |
| 6-02 | 畢業條件判定（Paper 14d/100t/PnL>0/DD<10%/Sharpe>0.5 → Demo 21d/200t/DD<8%/Sharpe>0.8） | E1-B | 6-01 | G1 | 6h |
| 6-03 | Live 審批（Claude AI 評估報告 + Operator 手動批准門控） | E1-C | 6-01 | G1 | 6h |
| 6-04 | 全管線回放測試（30 天歷史數據端到端重播） | E1-D | Phase 5 | G1 | 8h |
| 6-05 | 壓測（FeatureCollector <0.1ms + PG 不阻塞 + ONNX <1ms，100k tick 連續） | E1-E | Phase 5 | G1 | 6h |
| 6-06 | Live sync_commit 策略驗證（orders/fills ON + 其餘 OFF） | E1-A | 6-01 | G2 | 3h |
| 6-07 | EvolutionEngine 標記 deprecated（Optuna TPE 取代） | E1-B | 3b | G2 | 2h |
| 6-08 | 完整文檔（Schema registry + ML pipeline + 運維手冊） | TW+R4 | all | G2 | 10h |
| 6-09 | **E2 代碼審查** | E2 | all | — | 4h |
| 6-10 | **E4 全量回歸** + 壓測通過 | E4 | 6-09 | — | 4h |
| 6-11 | **QA 端到端驗收** | QA | 6-10 | — | 6h |
| 6-12 | **E5 最終優化審查** | E5 | 6-11 | — | 4h |
| 6-13 | PM 最終確認 + 版本 tag | PM | 6-12 | — | 2h |

## 驗收量化指標

| 指標 | 目標 |
|------|------|
| Tests | 4629+（新增 200+） |
| FeatureCollector | < 0.1ms/tick |
| ONNX 推理 | < 1ms |
| PG 寫入 | 不阻塞 tick |
| 日存儲量 | ~0.17 GB/day ±20% |
| PG 活躍數據 | < 20 GB |
| Scorer AUC | > 0.55 |
| ONNX 精度 | max abs err < 1e-3 |
| Context 完整率 | > 95% signals have context |
