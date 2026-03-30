# Phase 6 Task Book — Test Hardening & Bug Fix
# 第六階段任務書 — 測試強化與 Bug 修復

**日期：** 2026-03-30
**主題：** 修復 P0 bug + 為 Phase 5 補齊整合測試 + E2E 訂單生命週期測試
**前置：** Phase 5 PASSED（1765 passed, 0 failed, 2 skipped）
**Worker 模式：** Single Worker-Alpha（sequential）

---

## T6.01 — [P0] 修復 OMS _handle_oms_reconciliation 方法名不匹配

**Gap：** G6.01
**檔案：** `app/governance_hub.py` line 1251-1252
**Bug：** 呼叫 `self._oms_sm.get_orders_by_state("RECONCILING")` 但 OMS 的方法是 `get_by_state(OrderState.RECONCILING)`
**修改：**
1. 修正方法名：`get_orders_by_state` → `get_by_state`
2. 修正參數：`"RECONCILING"` → 使用 OMS 的 OrderState enum
3. 需 import OrderState from oms_state_machine
4. 同時檢查 reconciliation_pass / reconciliation_fail 的參數是否正確

**驗收標準：** 對賬完成後 OMS 訂單實際從 RECONCILING 轉換

---

## T6.02 — 整合測試：SM 轉換 → ChangeRecord

**檔案：** `tests/test_integration_phase5.py`（新建）
**測試：**
- IT-P5-01: Authorization SM transition → ChangeRecord with correct who/what
- IT-P5-02: DecisionLease SM transition → ChangeRecord
- IT-P5-03: OMS SM transition → ChangeRecord
- IT-P5-04: RiskGovernor SM transition → ChangeRecord

**方法：** 建立 SM 實例 → 注入 ChangeAuditLog → 執行轉換 → 驗證 get_change_history() 包含記錄

---

## T6.03 — 整合測試：OMS 對賬聯動

**檔案：** `tests/test_integration_phase5.py`
**測試：**
- IT-P5-05: Reconciliation PASS → OMS RECONCILING → COMPLETED
- IT-P5-06: Reconciliation FAIL → OMS RECONCILING → REJECTED

**前置：** T6.01 修復完成

---

## T6.04 — 整合測試：Whitelist 拒絕

**檔案：** `tests/test_integration_phase5.py`
**測試：**
- IT-P5-07: 白名單內 symbol (BTCUSDT) → 通過 risk check
- IT-P5-08: 白名單外 symbol (XYZUSDT) → 被 risk check 拒絕

**方法：** 建立 RiskManager → 設定 whitelist → 呼叫 check_order_allowed()

---

## T6.05 — 整合測試：De-escalation Flow

**檔案：** `tests/test_integration_phase5.py`
**測試：**
- IT-P5-09: request_de_escalation() 產生 pending request
- IT-P5-10: approve_de_escalation() 執行後風險級別降低

**方法：** GovernanceHub → escalate to DEFENSIVE → request_de_escalation(CAUTIOUS) → approve → 驗證級別

---

## T6.06 — 整合測試：FATAL Mismatch → CIRCUIT_BREAKER Cascade

**檔案：** `tests/test_integration_phase5.py`
**測試：**
- IT-P5-11: FATAL mismatch → risk escalate to CIRCUIT_BREAKER
- IT-P5-12: CIRCUIT_BREAKER → Auth frozen + Lease revoked (cascade)

---

## T6.07 — 整合測試：ScannerRateLimiter get_stats()

**檔案：** `tests/test_integration_phase5.py`
**測試：**
- IT-P5-13: 初始 stats 全部為 0
- IT-P5-14: scan 後 stats 反映正確累計

---

## T6.08 — E2E Order Lifecycle Test

**檔案：** `tests/test_integration_phase5.py`
**測試：**
- IT-P5-15: 完整生命週期 Auth → Lease → Risk → OMS → Fill → Reconcile → Complete
- 驗證每一步治理閘門都被通過，非跳過

---

## T6.09 — 回歸測試 + PM 驗收

**前置：** T6.01–T6.08 全部完成
**執行：** `pytest tests/ -q` → 0 failures
**產出：** PM 驗收報告

---

## 執行計畫

| 順序 | 任務 | 類型 |
|------|------|------|
| 1 | T6.01 P0 bug fix | Code fix |
| 2 | T6.02 SM→ChangeRecord tests | Test |
| 3 | T6.03 OMS reconciliation test | Test |
| 4 | T6.04 Whitelist test | Test |
| 5 | T6.05 De-escalation test | Test |
| 6 | T6.06 FATAL cascade test | Test |
| 7 | T6.07 Scanner stats test | Test |
| 8 | T6.08 E2E lifecycle test | Test |
| 9 | T6.09 Regression + Report | Verification |

**每個任務完成後立即 commit + push。**

---

*任務書由 PM（via Cowork PM）於 2026-03-30 產出*
