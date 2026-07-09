# Phase 5 FA Gap Audit Report
# 第五階段 FA 差距審計報告

**日期：** 2026-03-30
**角色：** FA (First Auditor)
**基準：** Phase 1–4 完成後（29 tasks, 1765 tests passed）

---

## 審計方法

逐一比對 22 份治理文件與 runtime 代碼，聚焦於：
1. 模組存在但未接入（exists-but-not-wired）
2. 回調只記錄但未執行（log-but-not-execute）
3. 狀態機轉換未被審計（unaudited transitions）

---

## Gap 清單

### G5.01 — TTL Enforcer 回調只 log 未觸發 SM 轉換 [P1]
- **治理文件：** SM-01 §4, DOC-07
- **要求：** TTL 到期必須實際執行 SM 轉換（Auth reject / Lease expire / Risk escalate）
- **現況：** `paper_trading_routes.py:112-127` callback 只有 `logger.info()`，無 SM 方法調用
- **修復：** 在 callback 中調用 AUTH_SM / LEASE_SM / RISK_SM 的對應轉換方法

### G5.02 — ChangeAuditLog 未覆蓋四個 SM 狀態轉換 [P1]
- **治理文件：** DOC-06 §5（Change Governance）
- **要求：** 所有 SM 狀態轉換必須產出 ChangeRecord（WHO/WHEN/APPROVAL）
- **現況：** ChangeAuditLog 僅在 RiskManager + GovernanceHub 2 處被調用；4 個 SM 零調用
- **修復：** 將 ChangeAuditLog 注入 4 個 SM，在轉換方法中調用 record_change()

### G5.03 — OMS RECONCILING 狀態未連接 ReconciliationEngine [P1]
- **治理文件：** EX-04（Reconciliation Boundary）
- **要求：** 對賬結果必須驅動 OMS 狀態轉換（RECONCILING → COMPLETED / REJECTED）
- **現況：** OMS 定義了 reconciliation_pass()/reconciliation_fail()，但無外部調用
- **修復：** GovernanceHub.reconcile() 完成後根據結果調用 OMS 對應轉換

### G5.04 — Symbol Whitelist 已檢查但未填充 [P1]
- **治理文件：** DOC-01 §5.7, EX-01 §2.3
- **要求：** 各類別（linear/spot/inverse/option）必須設定允許交易的幣對白名單
- **現況：** RiskManager 有 allowed_symbols 欄位，check_order_allowed() 有驗證邏輯，但初始化時未 SET
- **修復：** 在 paper_trading_routes.py 初始化時呼叫 update_category_config() 填入白名單

### G5.05 — Recovery Gate 已存在但 de-escalation 從未觸發 [P1]
- **治理文件：** DOC-07, SM-04 §6.2
- **要求：** 風險降級必須通過 RecoveryApprovalGate 審批
- **現況：** de_escalate_to() 方法存在於 RiskGovernorSM，但 GovernanceHub 無自動降級觸發路徑
- **修復：** 在 GovernanceHub 加入 request_de_escalation() 方法，串接 RecoveryApprovalGate

### G5.06 — 對賬 Mismatch 嚴重度未驅動風險升級 [P1]
- **治理文件：** EX-04 §5, DOC-07
- **要求：** MISMATCH_MAJOR → 風險升級，FATAL → 立即 CIRCUIT_BREAKER
- **現況：** governance_hub.py 對賬 mismatch 回調只 log，未調用 risk_sm.escalate_to()
- **修復：** 在 _on_reconciliation_mismatch() 中根據嚴重度觸發風險升級

### G5.07 — ScannerRateLimiter 無統計暴露 [P2]
- **治理文件：** DOC-02 §9.2
- **要求：** Scanner 頻率限制必須可觀測
- **修復：** 增加 get_stats() 方法，透過治理狀態端點暴露

### ~~G5.08~~ — PerceptionPlane 驗證已阻塞（VERIFIED OK）
- **現況：** pipeline_bridge.py:307-314 驗證失敗 → `continue` 跳過 intent + 計數器增加
- **結論：** 已正確實現 fail-closed，無需修復

---

## 優先級排序

| 優先級 | Gap 數量 | 任務 |
|--------|---------|------|
| P1 | 6 | G5.01, G5.02, G5.03, G5.04, G5.05, G5.06 |
| P2 | 1 | G5.07 |
| OK | 1 | G5.08（已驗證正常） |

**建議 Phase 5 範圍：** 6 個 P1 任務 + 1 個 P2 = 7 個任務 + 1 個回歸測試任務 = T5.01–T5.08

---

*報告由 FA（via Cowork PM）於 2026-03-30 產出*
