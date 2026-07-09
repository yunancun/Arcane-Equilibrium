# FA 全系統完成度與 GAP 審核報告
**審計日期：2026-04-01 | 測試基準：3,630 passed / 29 failed / 17 errors**

---

## 總體結論

| 維度 | 完成度 | 說明 |
|------|--------|------|
| **代碼完成度** | ~80% | 架構完整，模組齊全 |
| **業務功能真正能用** | **~52%** | 核心交易管線 90%，學習+進化閉環 ~10% |
| **測試健康度** | 98.7% | 3,630 passed / 29 failed / 17 errors（均為 pre-existing） |

**一句話：系統可以完整執行交易（掃描→決策→風控→下單→止損→記錄），但不會從交易中學習改進。**

---

## 七環節逐項審計

### 1. 自動掃描 — 90% ✅
| 有效 | 缺失 |
|------|------|
| ScoutWorker 30min daemon 線程真實運行 | MarketScanner → Deployer callback **未接通**（掃描到機會但不自動部署） |
| MarketScanner 4 類機會評分 + MessageBus 鏈路 | 需手動 POST `/phase2/scan` 觸發 |
| SymbolCategoryRegistry API 啟動填充 | |

### 2. 策略選擇 — 40% ⚠️
| 有效 | 缺失 |
|------|------|
| StrategistAgent 接收 intel → 生成 TradeIntent | **無可證明的 alpha**（僅 RSI/MACD/BB 基礎指標） |
| StrategyAutoDeployer 動態 qty + 自動暫停 | 回測引擎已建但**生產環境未啟用** |
| H1 cooldown 去重 + 5 策略品類 | TruthSourceRegistry → 權重調整路徑**從未被調用** |

### 3. AI 風險評估 — 55% ⚠️
| 有效 | 缺失 |
|------|------|
| H0-H5 六層門控全部存在且有測試 | **H0 Gate 為 warn-only，未真正阻斷**（DOC-02 要求 fail-closed） |
| Guardian review_intent() APPROVED/REJECTED | Guardian 無法動態調整 RiskManager 參數 |
| Decision Lease acquire_lease() fail-closed | |
| RiskManager P0/P1/P2 真實拒絕 | |

### 4. 下單 — 90% ✅
| 有效 | 缺失 |
|------|------|
| Paper Engine 7-state 生命週期 + OMS 11-state 映射 | **交易所條件單 = STUB**（Bybit Demo 側無 SL/TP 掛單） |
| Bybit Demo 雙重執行 + HMAC 簽名 | Demo sync 偶爾失敗（fail-open，可分歧） |
| ExecutorAgent lease + audit trail | |

### 5. 止損 — 90% ✅
| 有效 | 缺失 |
|------|------|
| 3 類止損（Hard/Trailing/Time）+ ATR sizing | **Demo 側無條件單**（僅本地止損） |
| `_check_stops()` 每 tick 觸發 + 學習信號發射 | time_stop_minutes 參數鮮少設定 |
| Wave 7 `_sync_close_to_demo()` 修復 | |

### 6. 學習 — 25% ❌
| 有效 | 缺失 |
|------|------|
| AnalystAgent 消費 ROUND_TRIP_COMPLETE | **CRITICAL：學習結果不反饋策略**（`_apply_pattern_insight()` 從未在決策路徑中調用） |
| L1 統計 + L2 Qwen 模式發現 | L2 需 ≥50 筆交易才觸發（多數 session 達不到） |
| TruthSourceRegistry 持久化 + TTL | L3-L5 學習層不存在 |

### 7. 進化 — 30% ❌
| 有效 | 缺失 |
|------|------|
| ExperimentLedger 假設追蹤 + 持久化 | **CRITICAL：進化結果不自動重部署**（EvolutionEngine → Deployer 完全無交叉引用） |
| EvolutionEngine 網格搜索 + 50 組合上限 | Backtest 引擎生產環境未啟用 |
| EvolutionScheduler 週日自動 + 每小時清理 | 無 regime-aware 策略選擇 |
| PaperLiveGate 11 項準入已部署 | |

---

## 關鍵 GAP 排序

| # | 嚴重度 | GAP | 影響 | 預估工時 |
|---|--------|-----|------|----------|
| 1 | **P0** | 學習反饋閉環斷開 | 策略權重永遠不更新，交易經驗白費 | 4h |
| 2 | **P0** | 進化參數不自動重部署 | 優化結果無法改善實際交易 | 4h |
| 3 | **P1** | H0 Gate warn-only | 失敗檢查不阻斷，違反 DOC-02 | 1h |
| 4 | **P1** | 交易所條件單未實作 | Bybit 側無止損保護（原則 9 缺口） | 6h |
| 5 | **P1** | MarketScanner → Deployer 未接通 | 掃描機會不自動部署 | 2h |
| 6 | **P1** | Backtest 生產環境未啟用 | 策略未經驗證就部署 | 2h |
| 7 | **P2** | L2 觸發門檻過高 | 學習系統長期休眠 | 1h |

---

## 測試健康度

```
3,630 passed / 29 failed / 17 errors / 1 skipped / 352 warnings

Failed 分類：
  Ollama 整合      12 個（本地 LLM provider mock 問題）
  GovernanceHub     7 個（lease/thread safety 競態）
  Learning/OMS      2 個（cron timing）
  Connector 級      5 個（edge filter/H0/inverse）
  本地模型工具      3 個（session9/strategies）

Errors（17 個）：
  全部在 test_session9_fixes.py（fixture/import 缺失）
```

所有 failure/error 均為 **pre-existing**，非新回歸。

---

## 結論與建議

**可用於：** 有人監督的 Paper Trading 觀察（數據收集階段）

**不可用於：** 自主進化交易（學習閉環未通）

**建議優先級：**
1. **本週必修（P0）：** 接通 #1 學習反饋 + #2 進化重部署 → 業務完成度可跳至 ~65%
2. **下週：** 修復 #3 H0 blocking + #5 Scanner→Deployer + #6 Backtest 啟用 → ~72%
3. **Phase 4 前：** 補 #4 交易所條件單 → 原則 9 合規 → ~80%

---

## 詳細代碼級發現

### P0-GAP-1：學習反饋閉環斷開

**問題：** AnalystAgent 收集交易記錄並通過 TruthSourceRegistry 存儲模式洞察，但 StrategistAgent 的 `_apply_pattern_insight()` 從未在決策路徑中被調用。

**影響鏈路：**
```
ROUND_TRIP_COMPLETE → AnalystAgent._register_pattern_claims() → TruthSourceRegistry.register_claim() ✅
TruthSourceRegistry → StrategistAgent._apply_pattern_insight() → adjusted_confidence ❌ 從未調用
```

**修復方向：** 在 StrategistAgent 的 `_evaluate_signal()` 中讀取 TruthSourceRegistry，應用權重至策略偏好。

### P0-GAP-2：進化參數不自動重部署

**問題：** EvolutionEngine 生成最優參數組合，但 StrategyAutoDeployer 與 EvolutionEngine 完全無交叉引用。

**影響鏈路：**
```
EvolutionEngine.run() → EvolutionResult（best_params） ✅
EvolutionResult → StrategyAutoDeployer.update_strategy_params() ❌ 不存在
```

**修復方向：** EvolutionEngine 輸出 best_params → StrategyAutoDeployer 消費並更新已部署策略。

### P1-GAP-3：H0 Gate warn-only

**問題：** `pipeline_bridge.py` 中 H0 Gate 檢查結果為 advisory，失敗的 intent 仍繼續處理。

**修復方向：** 將 `continue` 改為 `if not h0_result.allowed: skip intent + increment counter`。

### P1-GAP-4：交易所條件單未實作

**問題：** ExecutorAgent 中交易所條件單回調為 STUB，Bybit Demo 側無 SL/TP 保護。原則 9 要求「本地止損 + 交易所條件單雙重防線」。

**修復方向：** BybitDemoConnector 新增 `place_conditional_order()` 方法，在開倉後同步建立交易所側 SL/TP。

### P1-GAP-5：MarketScanner → Deployer 未接通

**問題：** MarketScanner 有 `register_on_scan()` 回調機制，但 StrategyAutoDeployer 從未註冊。

**修復方向：** 啟動時 `deployer.register_on_scan(scanner)` 接通自動部署。

### P1-GAP-6：Backtest 生產環境未啟用

**問題：** BacktestEngine 已建（531 行 + 57 測試），但 `backtest_mode=False` 安全守衛阻止生產使用。僅可通過手動 POST API 觸發。

**修復方向：** 在策略部署前自動執行回測驗證（Sharpe > 閾值才允許部署）。
