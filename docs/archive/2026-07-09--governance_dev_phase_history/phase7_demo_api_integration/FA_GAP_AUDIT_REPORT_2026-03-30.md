# Phase 7 FA Gap Audit Report
# 第七階段 FA 差距審計報告

**日期：** 2026-03-30
**角色：** FA (First Auditor)
**基準：** Phase 1–6 完成後（44 tasks, 1780 tests passed）
**主題：** 治理管線輸出 → BybitDemoConnector 對接

---

## 審計發現

### G7.01 — BybitDemoConnector 未在 paper_trading_routes.py 實例化 [P0]
- **現況：** phase2_strategy_routes.py 已有 `DEMO_CONNECTOR = BybitDemoConnector()`，但 paper_trading_routes.py 沒有
- **影響：** 治理管線無法提交訂單到 Demo API
- **修復：** 實例化 + 注入 ENGINE 和 GOV_HUB

### G7.02 — ProtectiveOrderManager execute callback 僅 log 未下單 [P0]
- **現況：** callback 只有 `logger.info()`，未呼叫 `DEMO_CONNECTOR.submit_order()`
- **需要：** ProtectiveOrderSide → "Buy"/"Sell" 映射，order_type → "Market"/"Limit" 映射，reduce_only=True
- **修復：** 增強 callback 實現，加入 Demo Connector 下單

### G7.03 — Paper State 格式不匹配 ReconciliationEngine [P1]
- **現況：** Engine 傳 `state`（內部格式），ReconciliationEngine 期望 `{snapshot_ts_ms, orders, positions, fills, balances}`
- **影響：** 對賬引擎收到錯誤格式，靜默失敗
- **修復：** 新增 adapter 函數轉換格式

### G7.04 — Demo State 未被收集用於對賬 [P1]
- **現況：** `governance_hub.reconcile(paper_state, demo_state=None)` — demo_state 永遠是 None
- **需要：** 從 BybitDemoConnector 即時拉取 positions + wallet balance 組成 snapshot
- **修復：** 新增 snapshot 方法 + 注入 engine

### G7.05 — 整合測試 [P1]
- **需要：** 測試 connector 注入、callback 映射邏輯、state adapter 正確性
- **注意：** 不能在 CI 中呼叫真實 API，需用 mock

---

## 優先級排序

| 優先級 | Gap | 類型 |
|--------|-----|------|
| P0 | G7.01 | Connector 實例化 |
| P0 | G7.02 | Protective order 下單 |
| P1 | G7.03 | State format adapter |
| P1 | G7.04 | Demo state snapshot |
| P1 | G7.05 | Integration tests |

**Phase 7 範圍：** T7.01–T7.06

---

*報告由 FA（via Cowork PM）於 2026-03-30 產出*
