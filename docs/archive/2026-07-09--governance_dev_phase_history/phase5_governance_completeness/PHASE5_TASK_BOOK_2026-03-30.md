# Phase 5 Task Book — Governance Completeness
# 第五階段任務書 — 治理完備性

**日期：** 2026-03-30
**主題：** 將 exists-but-not-wired 模式歸零：TTL 觸發、SM 審計、OMS 對賬聯動、風險聯動
**前置：** Phase 4 PASSED（1765 passed, 0 failed, 2 skipped）
**Worker 模式：** Single Worker-Alpha（sequential）

---

## T5.01 — TTL Enforcer 回調實際觸發 SM 轉換

**Gap：** G5.01
**檔案：** `app/paper_trading_routes.py` lines 110-129
**修改：**
1. 在 `_make_ttl_expiry_callback()` 內，取得模組級 SM 實例（AUTH_SM, LEASE_SM, RISK_SM）
2. Authorization + `auto_reject` → 呼叫 `AUTH_SM.reject(entry.object_id, initiator=SYSTEM, reason="TTL expired")`（需確認實際方法名）
3. DecisionLease + `auto_expire` → 呼叫 `LEASE_SM.expire_lease(entry.object_id)`（需確認實際方法名）
4. RiskGovernor + `escalate` → 呼叫 `RISK_SM.escalate_to(next_level, ...)`
5. 每次 SM 呼叫後 log 實際轉換結果
6. 包裹 try/except 防止 SM 調用失敗阻塞 TTL daemon

**驗收標準：** TTL 到期後 SM 狀態實際改變（非僅 log）

---

## T5.02 — ChangeAuditLog 注入四個 SM 並記錄轉換

**Gap：** G5.02
**檔案：**
- `app/paper_trading_routes.py`（注入點）
- `app/authorization_state_machine.py`
- `app/decision_lease_sm.py`
- `app/oms_state_machine.py`
- `app/risk_governor_state_machine.py`
**修改：**
1. 四個 SM 各加 `set_change_audit_log(cal)` 方法 + `_change_audit_log = None` 屬性
2. 在每個 SM 的轉換方法（transition / approve / reject / escalate_to / de_escalate_to 等）中，若 `_change_audit_log` 不為 None，呼叫 `record_change(change_type="STATE_CHANGE", who=initiator, what=f"{old_state}→{new_state}", reason=reason)`
3. 在 `paper_trading_routes.py` 初始化區塊中，呼叫各 SM 的 `set_change_audit_log(CHANGE_AUDIT_LOG)`

**驗收標準：** 任何 SM 轉換均產出 ChangeRecord

---

## T5.03 — OMS RECONCILING → ReconciliationEngine 聯動

**Gap：** G5.03
**檔案：**
- `app/governance_hub.py`（reconcile() 方法）
- `app/oms_state_machine.py`（reconciliation_pass / reconciliation_fail）
**修改：**
1. 在 GovernanceHub 注入 OMS SM 引用（`set_oms_sm(oms_sm)`）
2. 在 `reconcile()` 完成後，遍歷 RECONCILING 狀態的訂單：
   - 對賬結果 MATCH / MISMATCH_MINOR → `oms_sm.reconciliation_pass(order_id, ...)`
   - 對賬結果 MISMATCH_MAJOR / FATAL → `oms_sm.reconciliation_fail(order_id, ...)`
3. `paper_trading_routes.py` 中注入 `GOV_HUB.set_oms_sm(OMS_SM)`（需先確認 OMS_SM 實例位置）

**驗收標準：** 對賬完成後 OMS 訂單從 RECONCILING 轉移至 COMPLETED 或 REJECTED

---

## T5.04 — Symbol Whitelist 初始化填充

**Gap：** G5.04
**檔案：** `app/paper_trading_routes.py`
**修改：**
1. 在 RISK_MANAGER 初始化之後，呼叫 `update_category_config()` 為各類別填入白名單：
   - `linear`: `["BTCUSDT", "ETHUSDT"]`（初始最小集）
   - 其他類別保持 `enabled=False`（spot/inverse/option 尚未啟用）
2. 確保 check_order_allowed() 對不在白名單中的 symbol 返回 rejected

**驗收標準：** 非白名單幣對被拒絕（測試驗證）

---

## T5.05 — GovernanceHub 降級路徑串接 RecoveryApprovalGate

**Gap：** G5.05
**檔案：** `app/governance_hub.py`
**修改：**
1. 新增 `request_de_escalation(target_level, requested_by, reason)` 公開方法
2. 內部呼叫 `_recovery_gate.submit_recovery_request(...)` 產生待審批請求
3. 新增 `approve_de_escalation(request_id, approved_by)` 方法：
   - 呼叫 `_recovery_gate.approve_recovery(request_id, ...)`
   - 成功後呼叫 `_risk_sm.de_escalate_to(target_level, approved_by=approved_by, ...)`
4. 記錄至 ChangeAuditLog

**驗收標準：** 降級需先 submit → approve → 實際執行，無法直接跳過審批

---

## T5.06 — 對賬 Mismatch 嚴重度驅動風險升級

**Gap：** G5.06
**檔案：** `app/governance_hub.py`
**修改：**
1. 在 reconcile() 結果處理中，根據 mismatch severity：
   - `MISMATCH_MINOR` → log warning, 不升級
   - `MISMATCH_MAJOR` → `_risk_sm.escalate_to(DEFENSIVE/REDUCED, reason="reconciliation major mismatch")`
   - `FATAL` → `_risk_sm.escalate_to(CIRCUIT_BREAKER, reason="reconciliation fatal mismatch")`
2. 同時觸發 cross-SM cascade（Auth freeze if CIRCUIT_BREAKER）
3. 記錄至 ChangeAuditLog

**驗收標準：** FATAL mismatch 導致 CIRCUIT_BREAKER + Auth frozen

---

## T5.07 — ScannerRateLimiter 統計暴露

**Gap：** G5.07
**檔案：** `app/scanner_rate_limiter.py`
**修改：**
1. 新增 `get_stats() -> Dict` 方法，返回：
   - `total_scans`, `throttled_count`, `error_count`
   - `last_scan_ts`, `next_allowed_ts`
   - `current_state`（idle / scanning / cooldown）
2. 不需 REST 端點，僅供內部狀態查詢即可

**驗收標準：** get_stats() 返回正確的累計統計

---

## T5.08 — 回歸測試 + PM 驗收

**前置：** T5.01–T5.07 全部完成
**執行：**
1. `pytest tests/ -q` → 確認 0 failures
2. 驗證新增功能：
   - TTL 到期實際觸發 SM 轉換
   - SM 轉換產出 ChangeRecord
   - OMS 對賬聯動工作
   - 白名單拒絕非授權幣對
   - 降級需 RecoveryApprovalGate 審批
   - FATAL mismatch → CIRCUIT_BREAKER
3. 產出 PM 驗收報告

**驗收標準：** 全套測試通過 + PM 報告簽發

---

## 執行計畫

| 順序 | 任務 | 預計影響檔案 |
|------|------|-------------|
| 1 | T5.01 TTL Enforcer | paper_trading_routes.py |
| 2 | T5.02 ChangeAuditLog SM | 4 SM files + paper_trading_routes.py |
| 3 | T5.03 OMS Reconciliation | governance_hub.py + paper_trading_routes.py |
| 4 | T5.04 Whitelist | paper_trading_routes.py |
| 5 | T5.05 De-escalation | governance_hub.py |
| 6 | T5.06 Mismatch → Risk | governance_hub.py |
| 7 | T5.07 Scanner Stats | scanner_rate_limiter.py |
| 8 | T5.08 Regression + Report | tests/ |

**每個任務完成後立即 commit + push，避免堆積。**

---

*任務書由 PM（via Cowork PM）於 2026-03-30 產出*
