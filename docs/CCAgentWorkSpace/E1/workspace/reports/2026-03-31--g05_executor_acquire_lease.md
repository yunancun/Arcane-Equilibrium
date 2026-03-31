# G-05 報告：ExecutorAgent acquire_lease() 插入

**日期**：2026-03-31
**執行者**：E1（Backend Developer）
**任務**：G-05 — executor_agent.py 插入 acquire_lease()（Sprint 0 BLOCKER）
**狀態**：完成，待 E2+E4 驗收

---

## 修改文件清單

| 文件 | 行範圍 | 改動類型 |
|------|--------|---------|
| `app/executor_agent.py` | ~122–155（`__init__`），~241–325（`execute_order`） | 添加參數 + 插入 lease 邏輯 |
| `app/phase2_strategy_routes.py` | ~491–498（ExecutorAgent 初始化） | 添加 governance_hub 傳入 |
| `tests/test_batch11_executor_exchange.py` | ~536–635（新增 TestExecutorAgentDecisionLease） | 新增 6 個測試 |

---

## 關鍵代碼：executor_agent.py 改動

### 1. `__init__()` 新增 `governance_hub` 參數

```python
def __init__(
    self,
    *,
    config: Optional[ExecutorConfig] = None,
    message_bus: Optional[MessageBus] = None,
    paper_engine: Optional[Any] = None,
    audit_callback: Optional[Callable] = None,
    governance_hub: Optional[Any] = None,  # 新增
):
    ...
    # GovernanceHub for Decision Lease — principle 3 enforcement
    # GovernanceHub 用於 Decision Lease 申請，落實根原則 3
    self._governance_hub = governance_hub
```

### 2. `execute_order()` 在 `submit_order()` 前插入 lease 邏輯

```python
# ── Decision Lease acquisition — principle 3: AI output ≠ immediate command ──
lease_id: Optional[str] = None
if self._governance_hub is not None:
    lease_id = self._governance_hub.acquire_lease(
        intent_id=intent_id,
        scope="TRADE_ENTRY",
        ttl_seconds=30.0,
    )
    if lease_id is None:
        # fail-closed: lease acquisition failed → reject execution
        logger.warning(
            "Decision Lease acquisition failed for intent %s symbol %s — "
            "rejecting execution (fail-closed, principle 3) / ...",
            intent_id, symbol, intent_id, symbol,
        )
        report = ExecutionReport(
            intent_id=intent_id,
            symbol=symbol,
            side=side,
            requested_qty=qty,
            expected_price=expected_price,
            success=False,
            error="governance_lease_acquisition_failed",
            metadata=metadata or {},
        )
        with self._lock:
            self._stats["executions_failed"] += 1
            self._stats["errors"] += 1
        self._store_report(report)
        return report
```

---

## 設計決策

### 1. fail-open vs fail-closed 分層
- `governance_hub=None`：**fail-open**（向後兼容）— 舊代碼、測試、無 hub 的部署均不受影響
- `governance_hub` 存在但 `acquire_lease()` 返回 `None`：**fail-closed** — 拒絕執行

### 2. acquire_lease() 參數適配
- 規格提到 `requester` 參數，但實際 `governance_hub.acquire_lease()` 簽名為 `(intent_id, scope, ttl_seconds)`
- 使用 `scope="TRADE_ENTRY"` 正確對應規格意圖（此 scope 已在 GovernanceHub 中有對應授權檢查）
- `ttl_seconds=30.0` 與規格一致

### 3. phase2_strategy_routes.py 注入點
- 使用本地別名 `_GOV_HUB_FOR_EXECUTOR` 防止與既有 `_GOV_HUB_FOR_GUARDIAN`、`_GOV_HUB_REF` 等名稱衝突
- 使用 try/except ImportError 防止啟動失敗

---

## 新增測試（6 個）

| 測試名 | 覆蓋場景 |
|--------|---------|
| `test_26_no_governance_hub_allows_execution` | governance_hub=None → fail-open，執行成功 |
| `test_27_acquire_lease_returns_none_rejects_execution` | acquire_lease()=None → fail-closed，submit_order() 未調用 |
| `test_28_acquire_lease_success_allows_execution` | 有效 lease_id → 執行成功，acquire_lease 參數正確 |
| `test_29_lease_rejection_stats_updated` | 統計計數器正確（executions_failed/errors 遞增） |
| `test_30_lease_rejection_produces_report` | 拒絕時產生正確的 ExecutionReport 並存檔 |
| `test_31_governance_hub_stored_as_attribute` | _governance_hub 屬性正確存儲 |

---

## 測試結果

- 批次測試（test_batch11_executor_exchange.py）：**31/31 passed**
- 全套測試（含新增）：**2561 passed**（基準 2555 +6）
- 17 個失敗均為預存在問題（與本次改動無關）

---

## 意外情況

無。代碼結構清晰，GovernanceHub 介面已完整實現，無需額外適配。
