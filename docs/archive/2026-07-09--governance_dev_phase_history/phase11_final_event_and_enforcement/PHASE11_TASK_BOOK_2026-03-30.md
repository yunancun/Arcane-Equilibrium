# Phase 11 Task Book — Final Event & Enforcement
# 第十一階段任務書 — 最終事件覆蓋 + 管線強制

**日期：** 2026-03-30
**前置：** Phase 10 PASSED（1840 passed, 0 failed, 2 skipped, 98.2%）

---

## T11.01 — OMS GovernanceEvent Factory + Emission

**檔案：** `app/governance_events.py`, `app/governance_hub.py`
1. 新增 `oms_event()` factory function（使用 EventCategory.ORDER_MANAGEMENT）
2. 在 GovernanceHub._handle_oms_reconciliation() 中發射 oms_event()
3. 驗證 `/governance/events?category=order_management` 返回 OMS 事件

## T11.02 — LearningTierGate Engine-Level Enforcement

**檔案：** `app/paper_trading_engine.py`
1. 在觀察記錄相關方法前加入 `can_record_observations()` check
2. 在模式發現相關方法前加入 `can_discover_patterns()` check
3. 在假設生成相關方法前加入 `can_generate_hypotheses()` check
4. 在策略演化相關方法前加入 `can_evolve_strategies()` check

## T11.03 — Cross-Event Correlation ID Chaining

**檔案：** `app/governance_hub.py`
1. 在 _on_risk_escalation() 中生成 correlation_id
2. 將 correlation_id 傳遞給下游 auth_event() 和 lease_event()
3. 在 _on_reconciliation_mismatch() 中同樣生成並傳遞 correlation_id

## T11.04 — Integration Tests

**檔案：** `tests/test_integration_phase11.py`

## T11.05 — Regression + PM Acceptance Report

---

*任務書由 PM（via Cowork PM）於 2026-03-30 產出*
