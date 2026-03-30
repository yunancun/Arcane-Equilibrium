# Phase 7 Task Book — Demo API Integration
# 第七階段任務書 — Demo API 對接

**日期：** 2026-03-30
**主題：** 將治理管線輸出接入已有的 BybitDemoConnector
**前置：** Phase 6 PASSED（1780 passed, 0 failed, 2 skipped）
**Worker 模式：** Single Worker-Alpha（sequential）

---

## T7.01 — BybitDemoConnector 實例化與注入

**Gap：** G7.01
**檔案：** `app/paper_trading_routes.py`
**修改：**
1. Import BybitDemoConnector
2. 實例化為模組級 singleton：`DEMO_CONNECTOR = BybitDemoConnector()`
3. 用 try/except 包裹，若 API key 不存在則 DEMO_CONNECTOR = None（CI 環境安全）
4. 在 ENGINE 注入 `set_demo_connector(DEMO_CONNECTOR)`（需在 engine 新增 setter）
5. `paper_trading_engine.py` 新增 `set_demo_connector()` setter + `_demo_connector = None`

**驗收標準：** DEMO_CONNECTOR 在啟動時被建立（或 None fallback），ENGINE 持有引用

---

## T7.02 — ProtectiveOrderManager execute callback 對接 Demo API

**Gap：** G7.02
**檔案：** `app/paper_trading_routes.py` callback function
**修改：**
1. 增強 `_protective_order_execute_callback(order, market_state)`:
   - 檢查 DEMO_CONNECTOR 是否可用
   - ProtectiveOrderSide.LONG_POSITION → "Sell"（平多），SHORT_POSITION → "Buy"（平空）
   - HARD_STOP_LOSS / SOFT_STOP_LOSS / EMERGENCY → "Market"，TAKE_PROFIT → "Limit"
   - 呼叫 `DEMO_CONNECTOR.submit_order(symbol, side, order_type, qty, price, reduce_only=True)`
   - Log 結果（retCode, orderId）
   - 失敗時 log error 但不阻塞（non-fatal）
2. READ `app/protective_order_manager.py` 確認 ProtectiveOrderSide 和 ProtectiveOrderType enum 值

**驗收標準：** Protective order 觸發後嘗試向 Demo API 下單

---

## T7.03 — Paper State → Reconciliation Format Adapter

**Gap：** G7.03
**檔案：** `app/paper_trading_engine.py`
**修改：**
1. 新增模組級函數 `_paper_state_to_recon_format(paper_state: dict) -> dict`:
   ```
   snapshot_ts_ms ← meta.updated_ts_ms or now_ms
   orders ← orders list
   positions ← positions dict
   fills ← fills list
   balances ← {"USDT": session.current_paper_balance_usdt}
   ```
2. 在 tick mutator 的 reconciliation 呼叫處，用 adapter 包裹：
   `self._governance_hub.reconcile(_paper_state_to_recon_format(state))`

**驗收標準：** reconcile() 收到正確格式的 paper state

---

## T7.04 — Demo State Snapshot + 雙向對賬

**Gap：** G7.04
**檔案：** `app/bybit_demo_sync.py`, `app/paper_trading_engine.py`, `app/paper_trading_routes.py`
**修改：**
1. `bybit_demo_sync.py` 新增 `get_current_snapshot() -> dict`:
   - 呼叫 `_demo.get_positions()` + `_demo.get_wallet_balance()`
   - 轉換為 reconciliation format `{snapshot_ts_ms, positions, balances, orders:[], fills:[]}`
   - 用 try/except 包裹 API 呼叫，失敗返回 None
2. `paper_trading_engine.py` 新增 `set_demo_sync(sync)` setter
3. 修改 reconciliation 呼叫：
   ```python
   demo_snap = self._demo_sync.get_current_snapshot() if self._demo_sync else None
   self._governance_hub.reconcile(paper_snap, demo_state=demo_snap)
   ```
4. `paper_trading_routes.py` 注入：`ENGINE.set_demo_sync(DEMO_SYNC)`（需確認 DEMO_SYNC 是否存在）

**驗收標準：** 對賬時同時傳入 paper state 和 demo state

---

## T7.05 — 整合測試（Mock API）

**檔案：** `tests/test_integration_phase7.py`（新建）
**測試：**
1. IT-P7-01: DEMO_CONNECTOR 注入 — Engine 持有引用
2. IT-P7-02: Protective callback side 映射 — LONG_POSITION→Sell, SHORT_POSITION→Buy
3. IT-P7-03: Protective callback order_type 映射 — HARD_STOP_LOSS→Market, TAKE_PROFIT→Limit
4. IT-P7-04: Paper state adapter — 輸出包含 snapshot_ts_ms + balances
5. IT-P7-05: Demo snapshot — get_current_snapshot() 返回正確格式
6. IT-P7-06: 雙向 reconcile — paper_snap + demo_snap 同時傳入

**注意：** 使用 mock/patch 模擬 BybitDemoConnector API 呼叫，不觸及真實 API

---

## T7.06 — 回歸測試 + PM 驗收

**前置：** T7.01–T7.05 全部完成
**執行：** `pytest tests/ -q` → 0 failures
**產出：** PM 驗收報告

---

## 執行順序

| 順序 | 任務 | 類型 |
|------|------|------|
| 1 | T7.01 Connector 實例化 | Infrastructure |
| 2 | T7.02 Protective callback | Business logic |
| 3 | T7.03 State adapter | Data contract |
| 4 | T7.04 Demo snapshot | Data flow |
| 5 | T7.05 Integration tests | Test |
| 6 | T7.06 Regression + Report | Verification |

---

*任務書由 PM（via Cowork PM）於 2026-03-30 產出*
