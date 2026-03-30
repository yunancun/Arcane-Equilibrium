# Phase 8 Task Book — REST API & Alerting
# 第八階段任務書 — REST API 端點與告警整合

**日期：** 2026-03-30
**主題：** 治理操作 REST 化 + 關鍵事件告警
**前置：** Phase 7 PASSED（1788 passed, 0 failed, 2 skipped）
**Worker 模式：** Single Worker-Alpha（sequential）

---

## T8.01 — Recovery Gate REST Endpoints

**檔案：** `app/governance_routes.py`（已有 governance_router）
**新增端點：**
1. `GET /api/v1/governance/recovery/pending` — 查詢待審批恢復請求
   - 呼叫 `_recovery_gate.get_pending_requests()`
2. `POST /api/v1/governance/recovery/{request_id}/approve` — 審批恢復請求
   - Body: `{approved_by, conditions?, observation_period_hours?, notes?}`
   - 呼叫 `_recovery_gate.approve_recovery(request_id, ...)`
3. `GET /api/v1/governance/recovery/{request_id}` — 查詢單一請求狀態

**實作前先 READ：** governance_routes.py 瞭解 endpoint pattern + recovery_approval_gate.py 確認方法簽名

---

## T8.02 — De-escalation REST Endpoints

**檔案：** `app/governance_routes.py`
**新增端點：**
1. `POST /api/v1/governance/risk/de-escalation/request` — 提交降級請求
   - Body: `{target_level, requested_by, reason}`
   - 呼叫 `GOV_HUB.request_de_escalation()`
2. `POST /api/v1/governance/risk/de-escalation/{request_id}/approve` — 審批降級
   - Body: `{approved_by}`
   - 呼叫 `GOV_HUB.approve_de_escalation()`

---

## T8.03 — ChangeAuditLog Query Endpoints

**檔案：** `app/governance_routes.py`
**新增端點：**
1. `GET /api/v1/governance/audit/changes` — 查詢變更記錄
   - Query params: `limit=50`, `change_type=?`
   - 呼叫 `_change_audit_log.get_change_history()`
2. `GET /api/v1/governance/audit/pending` — 查詢待審批變更
   - 呼叫 `_change_audit_log.get_pending_approvals()`

**實作前先 READ：** change_audit_log.py 確認 get_change_history() 和 get_pending_approvals() 返回格式

---

## T8.04 — Symbol Whitelist CRUD Endpoints

**檔案：** `app/risk_routes.py`（已有 risk_router）或 `governance_routes.py`
**新增端點：**
1. `GET /api/v1/governance/symbols/whitelist` — 查詢當前白名單
   - 從 RISK_MANAGER 讀取各 category 的 allowed_symbols
2. `POST /api/v1/governance/symbols/whitelist` — 新增 symbol
   - Body: `{symbol, category="linear"}`
   - 呼叫 RISK_MANAGER.update_category_config() 更新 allowed_symbols
   - 記錄至 ChangeAuditLog
3. `DELETE /api/v1/governance/symbols/whitelist/{symbol}` — 移除 symbol
   - 從 allowed_symbols 移除 + ChangeAuditLog

---

## T8.05 — Detailed Governance Status Endpoint

**檔案：** `app/governance_routes.py`
**新增端點：**
1. `GET /api/v1/governance/status/detailed` — 完整治理儀表板
   - 包含：
     - Risk SM: current level, last escalation time
     - Auth SM: active count, frozen status
     - Lease SM: active lease count
     - OMS: orders by state (PENDING, RECONCILING, etc.)
     - Recovery Gate: pending requests count
     - ChangeAuditLog: pending approvals count
     - Scanner: get_stats()
     - Demo Connector: enabled/disabled, orders submitted

---

## T8.06 — TelegramAlerter 接入治理關鍵事件

**檔案：** `app/paper_trading_routes.py`, `app/governance_hub.py`
**修改：**
1. READ `app/telegram_alerter.py` — 確認 send() 方法簽名和 is_enabled 屬性
2. 在 `paper_trading_routes.py` 實例化 TelegramAlerter（若未實例化）
3. 在 GovernanceHub 新增 `set_alerter(alerter)` setter
4. 在以下位置發送告警：
   - `_on_risk_escalation()` 升級到 CIRCUIT_BREAKER → `alerter.send("🚨 CIRCUIT_BREAKER ...")`
   - `_on_reconciliation_mismatch()` FATAL → `alerter.send("🚨 FATAL mismatch ...")`
   - 降級審批完成 → `alerter.send("✅ Risk de-escalated ...")`
5. 每次告警包裹 try/except（non-fatal，alerter 不可用不應阻塞治理流程）

---

## T8.07 — Integration Tests

**檔案：** `tests/test_integration_phase8.py`（新建）
**測試：**
1. IT-P8-01: GET /recovery/pending 返回空 list
2. IT-P8-02: POST /de-escalation/request 返回 request_id
3. IT-P8-03: GET /audit/changes 返回記錄 list
4. IT-P8-04: GET /symbols/whitelist 返回當前白名單
5. IT-P8-05: GET /status/detailed 包含所有 SM 狀態
6. IT-P8-06: GovernanceHub alerter injection — alerter.send 被呼叫

使用 FastAPI TestClient + mock alerter

---

## T8.08 — 回歸測試 + PM 驗收

**前置：** T8.01–T8.07 全部完成
**執行：** `pytest tests/ -q` → 0 failures
**產出：** PM 驗收報告

---

## 執行順序

| 順序 | 任務 | 類型 |
|------|------|------|
| 1 | T8.01 Recovery Gate REST | REST |
| 2 | T8.02 De-escalation REST | REST |
| 3 | T8.03 ChangeAuditLog REST | REST |
| 4 | T8.04 Whitelist CRUD | REST |
| 5 | T8.05 Detailed Status | REST |
| 6 | T8.06 TelegramAlerter | Alerting |
| 7 | T8.07 Integration tests | Test |
| 8 | T8.08 Regression + Report | Verification |

---

*任務書由 PM（via Cowork PM）於 2026-03-30 產出*
