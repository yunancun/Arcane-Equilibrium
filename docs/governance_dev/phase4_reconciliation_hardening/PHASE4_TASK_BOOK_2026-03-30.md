# Phase 4 任務書：對賬強化與跳過測試修復
# Phase 4 Task Book: Reconciliation Hardening & Skip Test Fixes

**版本：** V1.0
**日期：** 2026-03-30
**作者：** PM (via Cowork PM)
**前置條件：** Phase 3 PASSED（1763 tests, 0 failed, 4 skipped）
**Phase 完成標準：** 週期性對賬生效 + 跳過測試解除 + 保護性訂單 execute callback 接入 + 0 failures + 0 skips

---

## FA 審計來源

基於 `PHASE4_GAP_AUDIT_REPORT.md`（2026-03-30），識別 4 個治理缺口。

---

## 任務總覽

| Task ID | 任務名稱 | 優先級 | 工作量 | 依賴 | 對應 GAP |
|---------|---------|--------|--------|------|---------|
| T4.01 | 週期性對賬觸發器 | P1 | M | 無 | GAP-P4-001 |
| T4.02 | 解除 T1.02/T1.03 跳過測試 | P1 | S | 無 | GAP-P4-003 |
| T4.03 | ProtectiveOrderManager execute callback 接入 PaperTradingEngine | P1 | S | 無 | GAP-P4-002 partial |
| T4.04 | Cross-SM 異常處理強化 | P2 | S | 無 | GAP-P4-004 |
| T4.05 | Phase 4 回歸測試 + 驗收 | P0 | S | T4.01-T4.04 | 測試 |

**註：** Bybit API 條件單預掛（GAP-P4-002 的交易所側）需要真實/Demo API 環境，延至 Phase 5。Phase 4 先完成本地執行回調和對賬觸發。

---

## 任務詳情

### T4.01 — 週期性對賬觸發器

**優先級：** P1 | **工作量：** M | **依賴：** 無

#### 問題
`GovernanceHub.reconcile()` 已完整實現（line 564-609），ReconciliationEngine 已在 GovernanceHub 內實例化（line 263），但只在 session stop 時被調用（`paper_trading_engine.py` line 785）。活躍交易期間對賬不執行。

#### 具體修改

**文件 1：** `app/paper_trading_engine.py`
在 tick mutator 中，添加週期性對賬觸發（每 N 次 tick 或每 60 秒）：

```python
# T4.01: Periodic reconciliation trigger (every 60 seconds during active session)
if self._governance_hub:
    now_ms = int(time.time() * 1000)
    last_recon = getattr(self, '_last_reconciliation_ms', 0)
    if now_ms - last_recon >= 60_000:  # 60 seconds
        try:
            recon_report = self._governance_hub.reconcile(state)
            self._last_reconciliation_ms = now_ms
            if recon_report.get("ok") is False:
                self._audit(state, "reconciliation_warning",
                    f"reason={recon_report.get('reason', 'unknown')}")
        except Exception as e:
            logger.error(f"Periodic reconciliation error: {e} (non-fatal)")
```

#### 驗收標準
1. 活躍 session 期間，tick 每 60 秒觸發一次 reconcile()
2. 對賬失敗產生審計記錄
3. 不阻塞交易流程（non-fatal）
4. 不影響現有測試

---

### T4.02 — 解除 T1.02/T1.03 跳過測試

**優先級：** P1 | **工作量：** S | **依賴：** 無

#### 問題
2 個集成測試被 `@pytest.mark.skipif(True, ...)` 標記為跳過：
- `test_lease_denied_order_rejected`（line 1014）— 依賴 T1.02 fail-closed
- `test_governance_hub_exception_order_rejected`（line 1124）— 依賴 T1.03 fail-closed

T1.02 和 T1.03 在 Phase 1 已完成並合併（commit `0763f0e` 和 `6b308d4`），但 skipif 標記未更新。

#### 具體修改

**文件：** `tests/test_integration_governance.py`

1. Line 1014-1017: 移除 `@pytest.mark.skipif(True, ...)` 裝飾器
2. Line 1124-1127: 移除 `@pytest.mark.skipif(True, ...)` 裝飾器
3. 補完測試邏輯（這兩個測試可能是空殼需要補充 assertion）
4. 運行這兩個測試驗證

**注意：** 如果測試需要實際 GovernanceHub + PaperTradingEngine 整合，可能需要添加 fixture 或 mock。重點是：
- `test_lease_denied_order_rejected`：驗證 acquire_lease() 返回 None → order 被 reject
- `test_governance_hub_exception_order_rejected`：驗證 is_authorized() 拋異常 → order 被 reject

#### 驗收標準
1. 兩個測試 PASS（不再 skip）
2. 4 skipped → 2 skipped（剩餘 2 個是 real observer data 依賴，無法在 CI 環境解除）

---

### T4.03 — ProtectiveOrderManager execute callback 接入

**優先級：** P1 | **工作量：** S | **依賴：** 無

#### 問題
`ProtectiveOrderManager.execute_protective_action()` 有 `_on_execute_callback` 但該 callback 未被設置。觸發保護性訂單後，只標記為 EXECUTED 但不實際平倉。

#### 具體修改

**文件 1：** `app/paper_trading_engine.py`
在 `set_protective_order_manager()` 後，設置 execute callback：

```python
def set_protective_order_manager(self, pom):
    self._protective_order_manager = pom
    # Wire execute callback to actually close positions
    if hasattr(pom, 'set_execute_callback'):
        pom.set_execute_callback(self._on_protective_order_execute)
```

添加 `_on_protective_order_execute` 方法，接收觸發的保護性訂單並執行平倉。

**文件 2：** 確認 `protective_order_manager.py` 有 `set_execute_callback()` 或類似設置方法。如果沒有，在 `__init__` 中添加 `on_execute_callback` 參數。

#### 驗收標準
1. 保護性訂單觸發 → 回調被調用
2. 回調記錄在審計日誌
3. 不影響現有測試

---

### T4.04 — Cross-SM 異常處理強化

**優先級：** P2 | **工作量：** S | **依賴：** 無

#### 問題
GovernanceHub 中的 cross-SM callback 有 bare `pass` 或空 except 塊。

#### 具體修改

**文件：** `app/governance_hub.py`
搜索 `except Exception` 後面的 `pass` 語句，替換為有意義的日誌和計數器：

```python
except Exception as e:
    logger.error(f"Cross-SM callback error: {e}")
    with self._lock:
        self._callback_errors += 1
```

#### 驗收標準
1. 所有 cross-SM 異常被記錄
2. 不影響現有測試

---

### T4.05 — Phase 4 回歸測試 + 驗收

**優先級：** P0 | **工作量：** S | **依賴：** T4.01-T4.04

#### 驗收標準
1. 全套測試 0 failures
2. Skipped 從 4 降至 ≤ 2
3. Phase 2 + Phase 3 集成測試繼續 PASS
4. 週期性對賬觸發器驗證

---

## 工作流編排

**單一 Worker-Alpha 順序執行：**

```
T4.01 (對賬觸發) → T4.02 (解除 skip) → T4.03 (execute callback) → T4.04 (異常處理) → T4.05 (回歸)
```

---

*Phase 4 任務書由 PM（via Cowork PM）於 2026-03-30 產出*
