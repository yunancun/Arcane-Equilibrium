# Phase 4 — Claude Teacher + LinUCB + News + DL-3（W13-15，7/03-7/23，15 工作日）

> 前置：Phase 3b 完成
> DoD：Claude Directive → ExperimentLedger · LinUCB 可用 · News mock 接口 · DL-3 決策 · 3 集成測試全通過 · 4429+50 tests

## 5 路並行

| ID | 任務 | Agent | 依賴 | 並行組 | 時間 |
|----|------|-------|------|--------|------|
| 4-01 | Claude-as-Teacher → ExperimentLedger source_type='claude_teacher' | E1-A | 3b | G1 | 8h |
| 4-02 | teacher_directives PG 表寫入（audit trail）+ directive_id↔hypothesis_id | E1-B | 4-01 | G1 | 4h |
| 4-03 | Claude Teacher 效果追蹤（confirmation_rate < 35%/20+ → 暫停 + 語義去重） | E1-C | 4-01 | G2 | 4h |
| 4-04 | LinUCB Contextual Bandits | E1-D | 3b | G1 | 8h |
| 4-05 | Model Performance 滾動監控（Brier + AUC → observability.model_performance） | E1-E | Phase 2 | G1 | 4h |
| 4-06 | Adversarial Validation（permutation test 校準閾值，不硬編碼 0.6） | E1-A | Phase 2 | G2 | 4h |
| 4-07 | NewsSignal Pydantic model + market.news_signals 寫入管線 | E1-B | 0a | G2 | 4h |
| 4-08 | 新聞三層路由（severity ≥0.8/0.5-0.8/<0.5） | E1-C | 4-07 | G2 | 3h |
| 4-09 | 新聞 mock fixture（無實際數據源） | E1-D | 4-07 | G2 | 2h |
| 4-10 | decision_context ��增 3 欄位（news_severity/hours_since/news_driven） | E1-E | 4-07 | G2 | 2h |
| 4-11 | DL-3 TimesFM/Chronos 本地部署（異步 5min 批次，不在 tick 路徑） | E1-A | Phase 2 | G3 | 8h |
| 4-12 | DL-3 A/B 驗證（含 vs 不含 foundation model 特徵的 Scorer AUC 差異） | E1-B | 4-11 | G3 | 6h |
| 4-13 | DL-3 基線比較（EMA 預測殘差 + historical volatility） | E1-C | 4-12 | G3 | 3h |
| 4-14 | features.online_latest +foundation_model_features REAL[] | E1-D | 4-11 | G3 | 2h |
| 4-15 | **集成測試** `test_full_learning_loop`（端到端） | E1-E | 4-01,3b | G3 | 6h |
| 4-16 | **E2 代碼審查** | E2 | all | — | 5h |
| 4-17 | **E4 回歸** + 3 集成測試 | E4 | 4-16 | — | 4h |
| 4-18 | CC/E3 安全審查（Claude API key + 新聞 API） | CC+E3 | 4-16 | — | 2h |
| 4-19 | AI-E 評估：DL-3 Go/No-Go（AUC 提升 < 0.01 → 棄用） | AI-E | 4-12 | — | 2h |
| 4-20 | **E5 優化審查** | E5 | 4-17 | — | 4h |

## DL-3 Go/No-Go 規則

- 含 foundation model 特徵的 Scorer AUC - 不含的 Scorer AUC < 0.01 → **棄用 DL-3**
- 必須與簡單替代（EMA 殘差 + historical vol）比較
- 零 shot 表現是假設非結論，必須實測
