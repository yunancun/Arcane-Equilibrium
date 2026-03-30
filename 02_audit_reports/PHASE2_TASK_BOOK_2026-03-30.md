# Phase 2 任務書：風控強化（Risk Hardening）
# Phase 2 Task Book: Risk Hardening

**版本：** V1.0
**日期：** 2026-03-30
**作者：** PM (via Cowork PM)
**前置條件：** Phase 1 PASSED（1729 tests, 0 failed）
**Phase 完成標準：** Portfolio 級風控生效 + 認知誠實強制 + 保護性訂單在位 + 變更審計統一 + 恢復需審批

---

## 代碼現狀：模組存在但未接入（與 Phase 1 同一模式）

| 模組 | 文件 | 行數 | 實現狀態 | 接入狀態 |
|------|------|------|---------|---------|
| PortfolioRiskControl | `portfolio_risk_control.py` | 558 | ✅ 完整（相關性矩陣+行業集中度+準備金） | ❌ 未接入 |
| PerceptionPlane | `perception_data_plane.py` | 588 | ✅ 完整（fact/inference 標記+拒絕邏輯） | ❌ 未接入交易管線 |
| ProtectiveOrderManager | `protective_order_manager.py` | 867 | ✅ 本地完整 | ❌ 無 Bybit API 整合 |
| ChangeAuditLog | `change_audit_log.py` | 617 | ✅ 完整（WHO/WHEN/APPROVAL） | ❌ 未接入 |
| RecoveryApprovalGate | `recovery_approval_gate.py` | 584 | ✅ 完整 | ❌ 未接入 GovernanceHub |
| ScannerRateLimiter | `scanner_rate_limiter.py` | 272 | ✅ 5 分鐘強制 | ❌ 未啟用 |
| OMS RECONCILING | `oms_state_machine.py` | 671 | ✅ 轉換規則已定義 | ❓ 與 ReconciliationEngine 連接未確認 |

---

## 任務總覽

| Task ID | 任務名稱 | 優先級 | 工作量 | 依賴 | 對應 GAP |
|---------|---------|--------|--------|------|---------|
| T2.01 | Portfolio 級風控接入實時管線 | P0 | L | 無 | GAP-H2 |
| T2.02 | 認知誠實：unmarked inference 阻止交易 | P0 | M | 無 | GAP-M1 |
| T2.03 | 保護性訂單接入（本地觸發層） | P1 | L | 無 | GAP-M3 |
| T2.04 | 變更審計統一持久化 | P1 | M | T1.04 | GAP-M2 |
| T2.05 | RecoveryApprovalGate 接入 GovernanceHub | P1 | S | 無 | GAP-M5 |
| T2.06 | OMS RECONCILING 閘門驗證 + ReconciliationEngine 連接 | P1 | S | 無 | GAP-M7 |
| T2.07 | ScannerRateLimiter 接入掃描管線 | P2 | S | 無 | GAP-M6 |
| T2.08 | Phase 2 集成測試 | P0 | L | T2.01-T2.03 | 測試缺口 |

---

## 任務詳情

### T2.01 — Portfolio 級風控接入實時管線

**優先級：** P0 | **工作量：** L（1.5 sessions）| **依賴：** 無

#### 問題
`PortfolioRiskControl`（558 行）完整實現了相關性矩陣、行業集中度、準備金緩衝，但未被 `risk_manager.py`、`paper_trading_engine.py` 或 `pipeline_bridge.py` 導入。

#### 治理要求（DOC-01 §5.16）
- 多倉位相關性監控（高相關性限制新開倉）
- 行業集中度上限（代碼默認 40%）
- 準備金緩衝強制（代碼默認 30%，不可協商）
- 全場回撤觸發縮減

#### 具體修改

**文件 1：** `app/risk_manager.py`
- 導入 `PortfolioRiskControl`
- 在 `RiskManager.__init__()` 中創建 `PortfolioRiskControl` 實例
- 在風控檢查流程中調用 `check_new_entry(symbol, side, qty, positions)` — 返回 False 時阻止新開倉
- 每次價格更新時調用 `record_price(symbol, price)`

**文件 2：** `app/paper_trading_engine.py`
- 在下單前（`is_authorized` 檢查之後、`acquire_lease` 之前），調用 portfolio risk check
- 或：通過 `RiskManager` 的整合間接調用

**文件 3：** `app/paper_trading_routes.py`
- 在 `RISK_MANAGER` 初始化後，配置 portfolio risk 參數

#### 驗收標準
1. 高相關性倉位被阻止新開倉（相關係數 > 0.7 時）
2. 行業集中度超過 40% 時阻止
3. 準備金低於 30% 時阻止
4. 現有單倉位風控不受影響
5. 新增 3 個 portfolio risk 集成測試

#### 角色分配
FA → E1b → E2 → E4

---

### T2.02 — 認知誠實：unmarked inference 阻止交易

**優先級：** P0 | **工作量：** M（1 session）| **依賴：** 無

#### 問題
`PerceptionPlane` 有完整的 fact/inference 標記和 `validate_for_decision()` 方法（拒絕未標記數據），但未接入交易決策管線。

#### 治理要求（DOC-01 §5.10, EX-07 §1）
- 所有進入決策鏈的數據必須標記 CognitiveLevel（FACT/INFERENCE/HYPOTHESIS）
- 未標記數據不可進入決策
- 搜索引擎數據自動標記為 INFERENCE（不等同於交易所數據）

#### 具體修改

**文件 1：** `app/pipeline_bridge.py`
- 在 `on_tick()` 的 intent 處理前，對信號數據調用 `PerceptionPlane.validate_for_decision()`
- 未通過認知誠實檢查的 intent 被 skip

**文件 2：** `app/paper_trading_routes.py`
- 創建 `PerceptionPlane` 實例並注入 PipelineBridge

#### 驗收標準
1. 未標記 CognitiveLevel 的數據無法生成交易信號
2. INFERENCE 級數據不能作為唯一決策依據（需搭配 FACT）
3. 審計記錄包含每筆交易的認知級別鏈
4. 新增 2 個認知誠實集成測試

#### 角色分配
E1b → E3 → E2 → E4

---

### T2.03 — 保護性訂單接入（本地觸發層）

**優先級：** P1 | **工作量：** L（1.5 sessions）| **依賴：** 無

#### 問題
`ProtectiveOrderManager`（867 行）完整實現了硬止損、軟止損、追蹤止損、保護性平倉，但：
1. 未接入交易管線（開倉後不自動建立保護）
2. 未連接 Bybit API（觸發時只有本地邏輯）

#### 治理要求（DOC-01 §5.9）
- 本地智能止損為第一層防線
- 交易所側預掛條件單為災難防線（Phase 2 先實現本地層，Bybit API 接入延至 Phase 3）
- 硬止損不可取消（`can_be_disabled = False`，代碼已實現）

#### 具體修改

**文件 1：** `app/paper_trading_engine.py`
- 開倉成功後，自動調用 `ProtectiveOrderManager.create_protective_order()` 建立硬止損
- 每次 tick 調用 `check_triggers()` 檢查是否觸發

**文件 2：** `app/paper_trading_routes.py`
- 創建 `ProtectiveOrderManager` 實例並注入 PaperTradingEngine

**Phase 2 範圍：** 本地觸發層（stealth mode — 不預掛到交易所）
**Phase 3 範圍：** Bybit API 條件單預掛

#### 驗收標準
1. 每筆開倉自動建立硬止損
2. 硬止損不可取消（`cancel_order()` 拒絕）
3. 價格觸及止損 → 自動平倉
4. `emergency_close_all()` 在 CIRCUIT_BREAKER 時觸發
5. 新增 3 個保護性訂單集成測試

#### 角色分配
FA → E1b → E3 → E4

---

### T2.04 — 變更審計統一持久化

**優先級：** P1 | **工作量：** M（1 session）| **依賴：** T1.04（AuditPipeline 已建立）

#### 問題
`ChangeAuditLog`（617 行）完整實現了 WHO/WHEN/APPROVAL 追蹤，但未接入任何模組。

#### 治理要求（DOC-06）
- L0-L3 四級變更需對應審批流程
- 所有變更記錄 WHO/WHEN/APPROVAL
- 不可變記錄（append-only）
- 緊急變更需 24 小時內回顧

#### 具體修改

**文件 1：** `app/paper_trading_routes.py`
- 創建 `ChangeAuditLog` 實例
- 連接到 AuditPipeline（T1.04 已建立）

**文件 2：** `app/governance_hub.py`
- SM 狀態轉換時調用 `ChangeAuditLog.record_change()`
- 特別是：Auth 狀態變更、Risk 級別變更、配置變更

#### 驗收標準
1. SM 狀態轉換產生 ChangeRecord
2. 每條記錄包含 WHO/WHEN/WHAT/APPROVAL
3. 記錄不可修改（frozen dataclass）
4. 緊急變更標記為 EMERGENCY_BYPASSED
5. 可查詢變更歷史（`get_change_history()`）

#### 角色分配
E1b → E2 → E4

---

### T2.05 — RecoveryApprovalGate 接入 GovernanceHub

**優先級：** P1 | **工作量：** S（0.5 session）| **依賴：** 無

#### 問題
`RecoveryApprovalGate`（584 行）完整實現了降級恢復審批流程，但 GovernanceHub 的降級路徑未調用它。

#### 治理要求（DOC-07）
- CIRCUIT_BREAKER → NORMAL 不可直接跳轉
- 每級降級恢復需 Operator 審批 + 觀察期
- 恢復路徑：CB → MANUAL_REVIEW → DEFENSIVE → REDUCED → CAUTIOUS → NORMAL

#### 具體修改

**文件：** `app/governance_hub.py`
- 在風控降級方法中，調用 RecoveryApprovalGate
- Auth FROZEN → RESTRICTED 需要 `approve_recovery()`
- Risk 降級需要 `submit_recovery_request()` + `approve_recovery()`

#### 驗收標準
1. Risk 降級必須經過 RecoveryApprovalGate
2. 無 Operator 審批 → 降級被拒
3. 觀察期內再次觸發 → 恢復失敗
4. 審計記錄完整

#### 角色分配
E1b → E3 → E4

---

### T2.06 — OMS RECONCILING 閘門驗證

**優先級：** P1 | **工作量：** S（0.5 session）| **依賴：** 無

#### 問題
OMS SM 定義了 FILLED → RECONCILING → COMPLETED 路徑，但 `reconciliation_pass()` 是否被 ReconciliationEngine 實際調用未確認。

#### 治理要求（EX-04）
- 不可跳過 RECONCILING（FILLED → COMPLETED 被禁止）
- RECONCILING 期間不可新開倉
- 交易所狀態為權威真相源

#### 具體修改

**文件 1：** 確認 `reconciliation_engine.py` 調用 `oms_state_machine.reconciliation_pass()`
**文件 2：** 如未調用，在 ReconciliationEngine 的對賬通過路徑中添加調用

#### 驗收標準
1. 對賬通過 → OMS 從 RECONCILING 轉 COMPLETED
2. 對賬失敗 → OMS 觸發 CANCELED 或 REJECTED
3. FILLED → COMPLETED 直接轉換被拒
4. RECONCILING 期間新開倉被阻止

#### 角色分配
CC → E1b → E4

---

### T2.07 — ScannerRateLimiter 接入掃描管線

**優先級：** P2 | **工作量：** S（0.5 session）| **依賴：** 無

#### 問題
`ScannerRateLimiter`（272 行）已實現 5 分鐘最小間隔，但未接入任何掃描流程。

#### 治理要求（DOC-02 §9.2）
- 掃描最小間隔 5 分鐘（`min_scan_interval_seconds = 300`）
- 錯誤後冷卻 10 分鐘

#### 具體修改

**文件：** `app/pipeline_bridge.py` 或掃描器入口
- 在掃描觸發前調用 `ScannerRateLimiter.can_scan()`
- 掃描開始/完成/錯誤時調用對應記錄方法

#### 驗收標準
1. 掃描間隔 < 5 分鐘被阻止
2. 錯誤後 10 分鐘冷卻
3. 審計記錄掃描事件

#### 角色分配
E1b → E4

---

### T2.08 — Phase 2 集成測試

**優先級：** P0 | **工作量：** L（1 session）| **依賴：** T2.01-T2.03

#### 新增測試用例

| ID | 測試場景 | 預期結果 |
|----|---------|---------|
| IT-P2-01 | 高相關性倉位阻止新開倉 | 被 PortfolioRiskControl 拒絕 |
| IT-P2-02 | 行業集中度超限阻止 | 被 sector check 拒絕 |
| IT-P2-03 | 未標記 inference 阻止交易 | 被 PerceptionPlane 拒絕 |
| IT-P2-04 | 開倉後自動建立硬止損 | ProtectiveOrder 存在 |
| IT-P2-05 | 硬止損觸發自動平倉 | 倉位已平 |
| IT-P2-06 | 硬止損不可取消 | cancel_order 被拒 |
| IT-P2-07 | 變更記錄包含 WHO/WHEN | ChangeRecord 完整 |
| IT-P2-08 | 恢復降級需審批 | 無審批則拒 |
| IT-P2-09 | RECONCILING 不可跳過 | 直接 COMPLETED 被拒 |
| IT-P2-10 | 掃描間隔 < 5min 被阻止 | can_scan() 返回 False |

#### 角色分配
E4 → E2 → PM 驗收

---

## 工作流編排

### Sprint 1（P0 — 並行）

```
Worker-A (FA+E1b): T2.01 Portfolio Risk 接入
Worker-B (E1b+E3): T2.02 認知誠實 + T2.05 Recovery Gate
Worker-C (E4+CC):  T2.06 OMS 驗證 + T2.07 Scanner + T2.08 測試設計
```

### Sprint 2（P1 — 並行）

```
Worker-D (FA+E1b): T2.03 保護性訂單接入
Worker-B (E1b):    T2.04 變更審計
Worker-C (E4):     T2.08 集成測試實現 + 全面回歸
```

---

## Worker 分配（4 對話）

| Worker | 角色 | Sprint 1 | Sprint 2 |
|--------|------|----------|----------|
| Worker-A | FA + E1b | T2.01 | T2.03 |
| Worker-B | E1b + E3 | T2.02 + T2.05 | T2.04 |
| Worker-C | E4 + CC | T2.06 + T2.07 + T2.08 設計 | T2.08 實現 + 回歸 |
| Worker-D | — | — | （合併到 Worker-A）|

**實際 3 Worker 即可。**

---

*Phase 2 任務書由 PM（via Cowork PM）於 2026-03-30 產出*
