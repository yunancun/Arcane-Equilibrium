# PM 執行計劃：確定性自適應參數 + FA GAP 統一排序
# PM Execution Plan: Deterministic Adaptive Params + FA GAP Unified Priority

> 制定人：PM（Project Manager）
> 日期：2026-04-02
> 輸入：QC 審查報告（2026-04-02）+ FA GAP 審計（2026-04-01）+ operator_risk_config.json
> 測試基準：3,637+ passed
> 系統狀態：demo_only · live_execution_allowed=false

---

## 0. Executive Summary

QC 報告與 FA 報告診斷一致：系統能跑交易但不能從交易中學習，且當前策略缺乏可證明的 edge。本計劃將 QC 的 M1-M4 / S1-S4 / N1-N3 與 FA 的 P0-GAP-1~7 統一排序，分為 4 個批次，總工時約 55h，控制在 2 週內完成。

**核心原則：確定性適應立即做，統計適應架構預留但不啟用。**

---

## 1. 統一優先級排序（QC 建議 × FA GAP 交叉分析）

### 1.1 重疊與新增分析

| QC 項 | FA GAP | 關係 | 說明 |
|--------|--------|------|------|
| M1（trail 利潤 > 成本約束） | — | **新增** | FA 未覆蓋，QC 新發現的止損邏輯漏洞 |
| M2（成本感知入場公式） | — | **新增** | FA 未覆蓋，替代原 2x magic number |
| M3（統計適應硬門檻 200+） | — | **新增（架構預留）** | 當前數據僅 20 筆，暫不啟用，設門檻即可 |
| M4（動態參數寫入 round-trip） | P0-GAP-1（學習閉環斷開） | **重疊** | M4 是 GAP-1 的前置條件——沒有記錄就沒法學習 |
| S1（ATR 快/慢雙窗口） | — | **新增** | 改進 ATR 估計質量 |
| S2（參數空間 step 字段） | — | **新增** | 減少過擬合風險 |
| S3（FundingRateArb 精算） | P0-GAP-1/P1-GAP-6 | **部分重疊** | 策略 edge 驗證需要回測框架（GAP-6） |
| S4（Kelly fraction GUI） | — | **新增** | 讓 Operator 直觀看到策略是否值得交易 |
| N1（Walk-forward harness） | P1-GAP-6（Backtest 未啟用） | **重疊** | N1 是 GAP-6 的高級擴展 |
| N2（Deflated Sharpe Ratio） | — | **新增** | EvolutionEngine 輸出品質保障 |
| N3（Jump detection 加寬止損） | — | **新增** | Crypto 尾部風險防護 |

### 1.2 統一優先級表

| 統一編號 | 來源 | 優先級 | 項目 | 依賴 |
|----------|------|--------|------|------|
| **U-01** | FA P0-GAP-1 | **P0** | 學習反饋閉環：`_apply_pattern_insight()` 接入決策路徑 | 無 |
| **U-02** | FA P0-GAP-2 | **P0** | 進化參數自動重部署：EvolutionEngine → Deployer | 無 |
| **U-03** | QC M1 | **P0** | 追蹤止損利潤約束：`activation - distance > c_round_pct` | 無 |
| **U-04** | QC M2 | **P0** | 成本感知入場門檻：替代 2x magic number | 無 |
| **U-05** | QC M4 | **P0** | 動態參數寫入 round-trip 記錄（原則 8 可審計） | 無 |
| **U-06** | FA P1-GAP-3 | **P1** | H0 Gate warn-only → blocking | 無 |
| **U-07** | FA P1-GAP-5 | **P1** | MarketScanner → Deployer 自動接通 | 無 |
| **U-08** | FA P1-GAP-6 | **P1** | Backtest 生產環境啟用（策略部署前驗證） | 無 |
| **U-09** | QC S1 | **P1** | ATR 快/慢雙窗口：max(ATR_5, ATR_14) | 無 |
| **U-10** | QC S3 | **P1** | FundingRateArb 完整成本模型精算 | U-08（回測框架） |
| **U-11** | FA P1-GAP-4 | **P1** | 交易所條件單（Bybit SL/TP 掛單） | 無 |
| **U-12** | QC M3 | **P2** | 統計適應硬門檻（200+ trades/regime 才啟用） | U-05 |
| **U-13** | QC S2 | **P2** | 參數空間 step 字段 | U-12 |
| **U-14** | QC S4 | **P2** | Kelly fraction 計算 + GUI 展示 | U-05 |
| **U-15** | FA P2-GAP-7 | **P2** | L2 觸發門檻降低（50→20 筆） | 無 |
| **U-16** | QC N1 | **P3** | Walk-forward harness（BacktestEngine 擴展） | U-08 |
| **U-17** | QC N2 | **P3** | Deflated Sharpe Ratio 自動計算 | U-16 |
| **U-18** | QC N3 | **P3** | Jump detection（K 線 body > 3σ → 加寬止損） | U-09 |

---

## 2. 批次分組與並行計劃

### Batch 9A — 確定性風控加固（P0，立即執行）

**目標：** 止損/入場邏輯數學加固，不依賴歷史數據，立即生效。

| 任務 | E1 Agent | 檔案 | 工時 | 並行組 |
|------|----------|------|------|--------|
| U-03：追蹤止損利潤約束 | E1-Alpha | `app/pipeline_bridge.py` + `app/risk_manager.py` | 2h | A |
| U-04：成本感知入場門檻 | E1-Beta | `app/pipeline_bridge.py` + `app/risk_manager.py` | 3h | A |
| U-05：動態參數寫入 round-trip | E1-Gamma | `app/paper_trading_engine.py` | 2h | A |
| U-09：ATR 快/慢雙窗口 | E1-Delta | `program_code/local_model_tools/indicator_engine.py` | 2h | A |

**依賴：** 無。4 個 E1 完全並行。
**工時：** 9h（並行後壁鐘 ~3h）
**E2+E4 審查：** 必須。預期新增測試 20+。

### Batch 9B — 學習閉環接通（P0，9A 完成後或並行）

**目標：** 讓系統從交易中學習並改進，業務完成度 52% → ~65%。

| 任務 | E1 Agent | 檔案 | 工時 | 並行組 |
|------|----------|------|------|--------|
| U-01：學習反饋閉環 | E1-Alpha | `app/strategist_agent.py` | 4h | B |
| U-02：進化參數重部署 | E1-Beta | `app/evolution_engine.py` + `app/strategy_auto_deployer.py` | 4h | B |

**依賴：** U-01 和 U-02 互不依賴，可並行。U-05（Batch 9A）是 U-01 的增強但非硬依賴。
**工時：** 8h（並行後壁鐘 ~4h）
**E2+E4 審查：** 必須。這是 FA 報告的兩個 P0 GAP，需要 FA 額外確認驗收。

### Batch 9C — 管線連通（P1，9A+9B 完成後）

**目標：** 修復管線中的斷點，業務完成度 65% → ~72%。

| 任務 | E1 Agent | 檔案 | 工時 | 並行組 |
|------|----------|------|------|--------|
| U-06：H0 Gate blocking | E1-Alpha | `app/pipeline_bridge.py` | 1h | C |
| U-07：Scanner → Deployer | E1-Beta | `app/market_scanner.py` + `app/strategy_auto_deployer.py` | 2h | C |
| U-08：Backtest 啟用 | E1-Gamma | `app/backtest_routes.py` + `app/strategy_auto_deployer.py` | 2h | C |
| U-15：L2 門檻降低 | E1-Delta | `app/analyst_agent.py` | 1h | C |

**依賴：** 4 項互不依賴，可並行。
**工時：** 6h（並行後壁鐘 ~2h）
**E2+E4 審查：** 必須。U-06 涉及 fail-closed 語義變更，需要 CC 合規確認。

### Batch 9D — 策略 Edge 驗證（P1，9C 完成後）

**目標：** 精算策略成本模型，為淘汰無 edge 策略提供數據依據。

| 任務 | E1 Agent | 檔案 | 工時 | 並行組 |
|------|----------|------|------|--------|
| U-10：FundingRateArb 成本模型 | E1-Alpha | `program_code/local_model_tools/strategies/` + 新建分析腳本 | 6h | D |
| U-11：交易所條件單 | E1-Beta | `app/bybit_demo_connector.py` + `app/executor_agent.py` | 6h | D |
| U-14：Kelly fraction + GUI | E1-Gamma | `app/paper_trading_engine.py` + `static/tab-ai.html` | 3h | D |

**依賴：** U-10 需要 U-08（Backtest 啟用）。U-11 無依賴。U-14 需要 U-05（round-trip 記錄）。
**工時：** 15h（並行後壁鐘 ~6h）
**E2+E4 審查：** 必須。U-11 涉及 Bybit API 新調用，需要 E3 安全審查。

### 延後項（P2-P3，不在本 2 週範圍內）

| 任務 | 理由 |
|------|------|
| U-12：統計適應硬門檻 | QC 明確建議「數據 < 200 不做統計適應」，當前僅 20 筆 |
| U-13：參數空間 step 字段 | 依賴 U-12 |
| U-16：Walk-forward harness | 需要 6+ 個月 K 線數據，BacktestEngine 擴展 |
| U-17：Deflated Sharpe Ratio | 依賴 U-16 |
| U-18：Jump detection | 改進項，非 blocking |

**原則：** 這些項目在架構中預留介面（如 M3 的 200+ 門檻常量），但不實現統計邏輯。

---

## 3. 工時估算匯總

| 批次 | 項目數 | 總工時 | 並行 E1 | 壁鐘時間 | E2+E4 | 累計壁鐘 |
|------|--------|--------|---------|----------|-------|----------|
| **9A** | 4 | 9h | 4 | ~3h | +2h | 5h |
| **9B** | 2 | 8h | 2 | ~4h | +2h | 11h |
| **9C** | 4 | 6h | 4 | ~2h | +2h | 15h |
| **9D** | 3 | 15h | 3 | ~6h | +3h | 24h |
| **合計** | 13 | 38h | — | ~15h | +9h | **24h 壁鐘** |

延後項（P2-P3）：17h，不在本計劃範圍。

---

## 4. 風險評估

### Batch 9A 風險

| 風險 | 嚴重度 | 緩解 |
|------|--------|------|
| ATR 雙窗口改動可能影響現有止損表現 | MEDIUM | 並行跑 A/B：舊邏輯保留為 fallback，新邏輯用 feature flag |
| 成本入場門檻過嚴導致零開倉 | MEDIUM | 設下限：min_move_pct 不超過 ATR 50th percentile（大幣種 ~0.5%） |
| round-trip 記錄格式變更破壞 AnalystAgent 消費 | LOW | AnalystAgent 讀取端用 `.get()` 防禦新增字段 |

### Batch 9B 風險

| 風險 | 嚴重度 | 緩解 |
|------|--------|------|
| **`_apply_pattern_insight()` 過度調整置信度** | HIGH | 權重調整上限 ±10%（已有），加入 min_sample_size=5 守衛 |
| EvolutionEngine → Deployer 自動重部署不受控 | HIGH | 必須經 GovernanceHub 審批（原則 3：AI 輸出 ≠ 即時命令），新參數走 Decision Lease |
| 學習閉環引入因果混淆 | MEDIUM | 所有 insight 標記 `source_type: "statistical"` + `sample_size` + `confidence_interval` |

### Batch 9C 風險

| 風險 | 嚴重度 | 緩解 |
|------|--------|------|
| H0 Gate blocking 誤殺正常交易 | MEDIUM | 先跑 1 週 shadow（記錄 would-have-blocked 但不攔截），確認誤殺率 < 5% 再切 blocking |
| Scanner → Deployer 自動部署過多幣種 | MEDIUM | 受 max_symbols=25 硬上限 + Deployer 自身品質過濾 |
| Backtest 啟用但結果不可信 | LOW | QC 已說明 < 50 筆不可信，Backtest 結果僅供參考標記，不做自動決策 |

### Batch 9D 風險

| 風險 | 嚴重度 | 緩解 |
|------|--------|------|
| FundingRateArb 雙腿同步失敗 | HIGH | Demo 模式先驗證；fail-closed（任一腿失敗 → 全取消） |
| 交易所條件單 API 行為不一致 | MEDIUM | Bybit sandbox 先測試；Demo connector fail-open（本地止損始終存在） |
| Kelly fraction 對小樣本敏感 | LOW | 固定下限 f* = 0（不建議做空策略），GUI 顯示 "insufficient data" 警告 |

---

## 5. 驗收標準

### Batch 9A 驗收

- [ ] 追蹤止損：`activation - distance > c_round_pct` 約束在所有幣種上生效，有 >= 5 個測試覆蓋
- [ ] 成本入場門檻：用公式 `c_round_pct / max(0.3, win_rate) * 1.3` 替代 2x，有 >= 5 個測試（含邊界）
- [ ] round-trip 記錄包含 `atr_pct, stop_distance, trail_activation, trail_distance, c_round_pct` 字段
- [ ] ATR 雙窗口：`max(ATR_5, ATR_14)` 在 IndicatorEngine 中實現，有 >= 3 個測試
- [ ] 所有新代碼有雙語 MODULE_NOTE / docstring
- [ ] E4：3637+ 基準不回歸，新增測試 >= 15

### Batch 9B 驗收

- [ ] `_apply_pattern_insight()` 在 StrategistAgent `_evaluate_signal()` 路徑中被調用
- [ ] TruthSourceRegistry 有 claim 時，策略偏好權重確實被調整（有端到端測試）
- [ ] EvolutionEngine best_params → Deployer `update_params()` 路徑存在且有治理 gate
- [ ] 進化結果重部署必須經 GovernanceHub 審批（原則 3 合規）
- [ ] E4：新增測試 >= 10（含學習路徑 + 進化路徑端到端）
- [ ] FA 確認：業務完成度從 ~52% 提升至 ~65%

### Batch 9C 驗收

- [ ] H0 Gate 失敗的 intent 被真正跳過（非 warn-only），有 counter `intents_h0_blocked`
- [ ] MarketScanner scan 完成後自動通知 Deployer，有集成測試
- [ ] Backtest 在策略部署前自動執行，Sharpe < 0 的策略被標記警告
- [ ] L2 觸發門檻從 50 降至 20（或 Operator 可配）
- [ ] CC 確認 H0 Gate blocking 符合 DOC-02
- [ ] E4：新增測試 >= 10

### Batch 9D 驗收

- [ ] FundingRateArb 成本模型文檔化：手續費 + 滑點 + funding rate + basis risk + 持倉天數
- [ ] 交易所條件單：開倉後 Bybit Demo 側存在 SL/TP 掛單（可驗證）
- [ ] Kelly fraction 在 tab-ai.html 顯示，數據不足時顯示 "N/A (需 50+ 筆)"
- [ ] E3 安全審查通過（條件單 API 調用）
- [ ] E4：新增測試 >= 10

---

## 6. 時間線

```
Week 1（4/2 ~ 4/5）：
  Day 1-2：Batch 9A（4 E1 並行）+ E2 review
  Day 3：Batch 9A E4 回歸 + Batch 9B 啟動（2 E1 並行）
  Day 4：Batch 9B E2 review + E4 回歸
  Day 5：Batch 9C（4 E1 並行）+ E2 review + E4 回歸

Week 2（4/7 ~ 4/11）：
  Day 6-8：Batch 9D（3 E1 並行，FundingRateArb 需較多分析時間）
  Day 9：E2 + E3（條件單安全審查）+ E4 回歸
  Day 10：FA 最終驗收 + PM 確認 + CLAUDE.md 更新 + commit
```

---

## 7. 與 QC「三步路徑」的對應

| QC 建議 | 本計劃對應 | 時機 |
|---------|-----------|------|
| **Step 1：確定性適應** | Batch 9A（ATR 縮放 + 成本門檻 + regime 表） | Week 1 Day 1-2 |
| **Step 2：FundingRateArb 精算** | Batch 9D U-10 | Week 2 |
| **Step 3：統計適應（200+ 後啟用）** | 延後（U-12/U-13），架構預留 M3 門檻 | 數據充足後 |

**QC 的核心判斷「確定性適應立即做，統計適應暫緩」完全採納。**

**QC 的最終建議「把精力花在尋找 alpha 上」部分採納：**
- Batch 9D 包含 FundingRateArb 精算（S3），這是目前唯一有可論證 edge 的策略
- 但同時必須先修復學習閉環（Batch 9B），否則即使有 alpha 的策略也無法自我改進
- Walk-forward + 策略淘汰機制延後到 P3（U-16/U-17），需要更多數據積累

---

## 8. 與現有 TODO.md 的關係

- Wave 8A-8D 已全部完成（3,637+ passed）
- Batch 9A-9D 是 Wave 8 之後的下一個工作批次
- 延後項（U-12~U-18）歸入 Phase 4 或更後
- 本計劃不與 TODO.md 中任何已完成或進行中的項目衝突

---

## 9. Operator 決策點

以下節點需要 Operator 明確確認：

1. **Batch 9A 完成後**：成本門檻公式可能導致部分低波動幣種不開倉，Operator 需確認是否可接受
2. **Batch 9B U-02**：進化參數自動重部署涉及策略參數自動變更，建議初期設為「建議但需人工確認」模式
3. **Batch 9C U-06**：H0 Gate 從 warn-only 切換到 blocking，建議先跑 shadow 觀察期
4. **Batch 9D U-10**：FundingRateArb 若精算結果顯示 edge 顯著，是否優先分配資本？

---

> PM (Project Manager)
> 2026-04-02
