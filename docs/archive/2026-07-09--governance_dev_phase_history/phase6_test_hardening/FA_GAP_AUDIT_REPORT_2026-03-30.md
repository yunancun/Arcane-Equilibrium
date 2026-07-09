# Phase 6 FA Gap Audit Report
# 第六階段 FA 差距審計報告

**日期：** 2026-03-30
**角色：** FA (First Auditor)
**基準：** Phase 1–5 完成後（36 tasks, 1765 tests passed）

---

## 審計重點

1. Phase 5 新增 7 功能但零新測試 → 需補測試
2. 代碼層面 bug：OMS 方法名不匹配
3. 剩餘 unwired 模式

---

## Gap 清單

### G6.01 — [P0 BUG] OMS _handle_oms_reconciliation 方法名不匹配
- **現況：** `governance_hub.py:1251` 呼叫 `get_orders_by_state("RECONCILING")`
- **實際：** OMS 的方法是 `get_by_state(OrderState.RECONCILING)`
- **影響：** hasattr 檢查永遠返回 False，OMS 對賬聯動完全失效（T5.03 成為死代碼）
- **修復：** 修正方法名 + 參數類型

### G6.02 — Phase 5 Integration Tests [P1]
- **現況：** Phase 5 新增 7 個功能，0 個新測試
- **需要測試：**
  1. TTL 到期 → SM 狀態實際改變
  2. SM 轉換 → ChangeRecord 被建立
  3. 對賬結果 → OMS 從 RECONCILING 轉換（依賴 G6.01 修復）
  4. 非白名單 symbol 被拒絕
  5. 降級 request → approve → 實際執行
  6. FATAL mismatch → CIRCUIT_BREAKER cascade
  7. get_stats() 返回正確數據

### G6.03 — E2E Order Lifecycle Test [P2]
- **現況：** 無端到端測試覆蓋完整訂單生命週期
- **需要：** Signal → Auth → Lease → Risk → OMS → Fill → Protective Order → Reconcile → Complete

---

## 優先級排序

| 優先級 | Gap | 類型 |
|--------|-----|------|
| P0 | G6.01 | Bug fix |
| P1 | G6.02 | Test coverage (7 tests) |
| P2 | G6.03 | E2E test |

**建議 Phase 6 範圍：** 1 P0 fix + 7 P1 tests + 1 P2 E2E test + regression = T6.01–T6.10

---

*報告由 FA（via Cowork PM）於 2026-03-30 產出*
