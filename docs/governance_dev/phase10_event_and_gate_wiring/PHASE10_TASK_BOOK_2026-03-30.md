# Phase 10 Task Book — Event & Gate Wiring
# 第十階段任務書 — 事件全覆蓋 + 等級閘強制執行

**日期：** 2026-03-30
**主題：** GovernanceEvent 4 SM 全覆蓋 + LearningTierGate 管線強制
**前置：** Phase 9 PASSED（1816 passed, 0 failed, 2 skipped）
**Worker 模式：** Single Worker-Alpha（sequential）

---

## T10.01 — Auth SM GovernanceEvent 發射

**檔案：** `app/governance_hub.py`
**修改：**
1. Import `auth_event` from `.governance_events`
2. 在 `_on_risk_escalation()` 中 restrict/freeze auth 後，發射 `auth_event()`
   - restrict → `auth_event(action="restrict", target_state="RESTRICTED", ...)`
   - freeze → `auth_event(action="freeze", target_state="FROZEN", ...)`
3. 在 `_on_auth_frozen()` 中，發射 `auth_event()` 記錄凍結觸發
4. 每個 event 透過 `_append_governance_event(event.to_dict())` 加入事件流

**驗證：** `/governance/events?category=authorization` 返回 auth 事件

---

## T10.02 — Lease SM GovernanceEvent 發射

**檔案：** `app/governance_hub.py`
**修改：**
1. Import `lease_event` from `.governance_events`
2. 在 `_on_auth_frozen()` 中 revoke lease 後，發射 `lease_event()`
   - revoke → `lease_event(action="revoke", target_state="REVOKED", lease_id=lid, ...)`
3. 每個 event 透過 `_append_governance_event(event.to_dict())` 加入事件流

**驗證：** `/governance/events?category=decision_lease` 返回 lease 事件

---

## T10.03 — LearningTierGate 管線強制執行

**檔案：** `app/governance_hub.py`
**修改：**
1. 新增 `_check_learning_tier(capability: str) -> bool` 輔助方法
   - 若 `_learning_tier_gate` is None → return True（向後相容）
   - 呼叫對應 `can_*()` method
2. 在 GovernanceHub 相關方法中加入 tier check：
   - `request_de_escalation()` → 需要 `can_evolve_strategies()` (L4+)
   - `approve_de_escalation()` → 需要 operator 角色（已有）+ tier check
3. 在控制流暴露點加入能力檢查

**檔案：** `app/paper_trading_engine.py`
**修改：**
1. 在 `_execute_order_lifecycle()` 或相關方法前加入 tier capability check
2. `can_record_observations()` (L1+) — 觀察記錄前
3. `can_discover_patterns()` (L2+) — 模式發現前
4. `can_auto_deploy_to_paper()` (L3+) — 自動部署前

**驗證：** 低 tier 的操作被正確拒絕

---

## T10.04 — LearningTierGate REST 端點

**檔案：** `app/governance_routes.py`
**新增端點：**
1. `GET /api/v1/governance/learning-tier/status` — 查詢當前 tier 狀態
   - 返回 tier level, capabilities, promotion history
2. `POST /api/v1/governance/learning-tier/promote` — 手動晉升（operator only）
   - Body: `{target_tier, reason, approved_by}`
   - 呼叫 `_learning_tier_gate.promote_tier()`

---

## T10.05 — OMS 狀態查詢端點

**檔案：** `app/governance_routes.py`
**新增端點：**
1. `GET /api/v1/governance/oms/orders` — 查詢 OMS 訂單狀態
   - Query params: `state=?`, `limit=50`
   - 從 GovernanceHub 讀取 OMS SM 狀態

---

## T10.06 — Integration Tests

**檔案：** `tests/test_integration_phase10.py`（新建）
**測試：**
1. IT-P10-01: Auth 事件在 risk escalation 後出現在事件流
2. IT-P10-02: Lease 事件在 auth frozen 後出現在事件流
3. IT-P10-03: `/governance/events?category=authorization` 過濾正確
4. IT-P10-04: `/governance/events?category=decision_lease` 過濾正確
5. IT-P10-05: LearningTierGate L1 — can_record_observations=True
6. IT-P10-06: LearningTierGate L1 — can_discover_patterns=False
7. IT-P10-07: LearningTierGate capability check via hub helper
8. IT-P10-08: GET /learning-tier/status 返回完整狀態
9. IT-P10-09: POST /learning-tier/promote 晉升成功
10. IT-P10-10: GET /oms/orders 返回訂單列表
11. IT-P10-11: 事件流 bounded buffer 不超過 max size
12. IT-P10-12: 全 4 SM 事件在 cascade 場景中均出現

---

## T10.07 — 回歸測試 + PM 驗收

**前置：** T10.01–T10.06 全部完成
**執行：** `pytest tests/ -q` → 0 failures
**產出：** PM 驗收報告

---

## 執行順序

| 順序 | 任務 | 類型 |
|------|------|------|
| 1 | T10.01 Auth Event 發射 | Event Wiring |
| 2 | T10.02 Lease Event 發射 | Event Wiring |
| 3 | T10.03 LearningTierGate 強制執行 | Gate Enforcement |
| 4 | T10.04 LearningTierGate REST | REST |
| 5 | T10.05 OMS REST | REST |
| 6 | T10.06 Integration Tests | Test |
| 7 | T10.07 Regression + Report | Verification |

---

*任務書由 PM（via Cowork PM）於 2026-03-30 產出*
