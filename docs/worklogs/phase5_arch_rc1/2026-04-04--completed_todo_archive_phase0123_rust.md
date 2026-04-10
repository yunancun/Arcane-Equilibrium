# 已完成項歸檔：Phase 0-3 + Rust R-00~R-06
# 歸檔日期：2026-04-04
# 歸檔原因：融合方案 v0.5 更新 TODO.md，將已完成的 26 個 Phase 0-3 任務 + 7 個 Rust 遷移階段歸檔

---

## Phase 0-A（6 項全部完成）
- [x] 0A-1：學習反饋閉環
- [x] 0A-2：進化參數自動重部署
- [x] 0A-3：H0 Gate shadow 觀察
- [x] 0A-4：Scanner→Deployer 自動接通
- [x] 0A-5：Backtest 生產環境啟用
- [x] 0A-6：L2 觸發門檻降低 50→20

## Phase 0-B（3 項全部完成）
- [x] 0B-1：FundingRateArb 完整成本模型精算
- [x] 0B-2：交易所條件單 SL/TP
- [x] 0B-3：Kelly fraction + GUI + Agent 自動資本分配

## Phase 1（10 項全部完成）
- [x] 1-1~1-10：PositionSizer / StrategyHealthMonitor / EWMAVolEstimator / Hurst / IndicatorEngine擴展 / CognitiveModulator / OpportunityTracker / DreamEngine / LocalLLMClient / 影子決策追蹤

## Phase 2（10 項全部完成 + L1 凍結）
- [x] 2-1~2-9：MA_Crossover V2 / BB_Reversion V2 / BB_Breakout V2 / FundingRateArb V2 / GridTrading V2 / Regime Detection / Strategist 雙軌 / ContextDistiller(Rust) / Ollama prompt
- [x] 2-L1：L1 接口凍結

## Phase 3（8 項全部完成 + L2 凍結）
- [x] 3-1~3-7：Claude API / L1→L2 路由 / Claude→TSR 閉環 / HedgingEngine(Rust) / PnLAttributor / OB Imbalance / 四階段放權
- [x] 3-L2：L2 接口凍結

## Rust 遷移 R-00~R-06（7 階段全部完成）
- [x] R-00：Cargo workspace + PyO3 + types + CI
- [x] R-01：IPC + shared_types + WS
- [x] R-02：core 上半（感知+認知+風控，302 tests）
- [x] R-03：core 下半（SM+執行+回測，468 tests）
- [x] R-04：Engine 完整交易路徑（517 tests）
- [x] R-05：Conditional Go 簽核
- [x] R-06：Python IPC 改造（53 tests）

## 同時歸檔的舊 TODO 條目
- DB-1 待打磨項（DB-1a~DB-1h）→ 已整合入融合方案 v0.5
- ML-1 待打磨項（ML-1a~ML-1h）→ 已整合入融合方案 v0.5
- AGT-1 → 已整合為融合方案 Phase 3a
- Phase 4 條件項 4-4/4-6/4-7/4-8/4-9/4-11 → 已整合入融合方案各 Phase
