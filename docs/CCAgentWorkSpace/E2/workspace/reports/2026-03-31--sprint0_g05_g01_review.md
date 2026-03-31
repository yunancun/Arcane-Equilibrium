# E2 Code Review Report: Sprint 0 (G-05 + G-01)
# E2 代碼審查報告：Sprint 0（G-05 + G-01）

**審查日期**: 2026-03-31
**審查員**: E2（Code Reviewer）
**任務**: G-05 ExecutorAgent acquire_lease() + G-01 daily AI cap $15→$2

---

## 審查摘要

| 改動 | 文件 | 結論 |
|------|------|------|
| G-05: acquire_lease 集成 | executor_agent.py | PASS |
| G-05: ExecutorAgent 初始化 | phase2_strategy_routes.py | PASS |
| G-05: 新測試 TestExecutorAgentDecisionLease | test_batch11_executor_exchange.py | PASS |
| G-01: DEFAULT_DAILY_HARD_CAP_USD | layer2_types.py | PASS |
| G-01: MODULE_NOTE 注釋 | layer2_cost_tracker.py | PASS |
| G-01: 預設值 | tab-ai.html | PASS |
| G-01: 斷言更新 | test_layer2.py | PASS |

**總體結論：PASS（可進入 E4）**

---

## 逐項審查結果

### 【雙語注釋合規】

#### G-05: executor_agent.py __init__ docstring
**PASS**

`__init__` 新增了完整的中英雙語 docstring，說明 governance_hub 參數的用途與根原則 3 的落實。inline comment 也使用雙語（`# GovernanceHub for Decision Lease — principle 3 enforcement`）。

#### G-05: execute_order() docstring
**PASS**

`execute_order()` docstring 新增了完整的中英雙語說明：
- 解釋 Guardian approval（質量門）與 Decision Lease（時效授權）兩個獨立控制層的區別
- fail-closed 路徑有明確的中英注釋說明 fallback 原因（`fail-closed: If governance_hub is present but acquire_lease() returns None, execution is rejected.`）

#### G-05: fail-closed 路徑注釋
**PASS**

拒絕路徑（lease=None）的 logger.warning 使用中英雙語，並列出了失敗的可能原因（hub disabled、not authorized、FROZEN mode）。源代碼注釋清楚解釋了為何 fail-closed。

#### G-01: layer2_types.py DEFAULT_DAILY_HARD_CAP_USD 來源注釋
**PASS**

```python
# DOC-08 §4 specifies $2.00/day hard cap to satisfy root principle 5 (survival > profit)
# DOC-08 §4 規定每日 AI 硬上限為 $2.00，遵從根原則 5（生存 > 利潤），防止 AI 成本失控
DEFAULT_DAILY_HARD_CAP_USD = 2.0
```
DOC-08 §4 來源引用、根原則 5 理由均在注釋中。

#### G-01: layer2_cost_tracker.py MODULE_NOTE 注釋
**PASS**

MODULE_NOTE 中英雙語已有 `($2/day, absolute, per DOC-08 §4)` 明確標記，與 layer2_types.py 的注釋一致。

---

### 【安全審查】

#### acquire_lease 失敗路徑是否 fail-closed
**PASS**

```python
if lease_id is None:
    # fail-closed: lease acquisition failed → reject execution
    report = ExecutionReport(success=False, error="governance_lease_acquisition_failed", ...)
    self._store_report(report)
    return report  # ← early return, submit_order() never called
```
在 return 之前不會走到 `submit_order()`，fail-closed 正確實施。

#### governance_hub=None 時的行為（fail-open，向後兼容）
**PASS — 設計意圖確認**

```python
if self._governance_hub is not None:
    lease_id = self._governance_hub.acquire_lease(...)
    if lease_id is None:
        return report  # fail-closed
# Falls through to submit_order() when hub is None
```
hub=None 時直接跳過 lease 檢查，允許執行。這是明確設計的向後兼容行為（comment 說明：`Missing governance_hub is fail-open (backward compat).`）。測試 26 驗證此路徑。可接受。

#### 是否有新引入的 except: pass 或吞異常
**PASS**（一項 WARN 標記，但不阻擋）

在 conditional order callback 的異常處理中：
```python
except Exception as e:
    logger.warning("Conditional order callback failed: %s / 条件单回调失败", e)
```
這是正確的非吞異常（有 warning log），且 callback 失敗是刻意設計為 non-fatal。

在外層 Exception 捕獲：
```python
except Exception as e:
    error=f"Execution error: {e}",
    logger.error("ExecutorAgent execution failed: %s / 执行失败: %s", e, e)
```
**WARN**: `error=f"Execution error: {e}"` 將異常內容動態插入 error 字段，可能在審計日誌中暴露 Python 異常堆棧細節。但這是 ExecutionReport 內部字段（非 HTTP response），且 Batch 11 原有代碼已存在此模式（未被審查要求的新增行）。此問題已存在，不是 G-05 新引入的，**不阻擋本次審查**。建議在 P2/P3 批次中追蹤。

同樣地，`error=f"Order rejected: {rejected_reason}"` 也有動態內容，原有代碼模式，不阻擋。

#### ExecutionReport 的 error 字段（lease 拒絕路徑）
**PASS**

```python
error="governance_lease_acquisition_failed",
```
lease 失敗路徑使用固定字符串，正確。

---

### 【架構合規】

#### acquire_lease() 調用在 submit_order() 前面
**PASS**

代碼順序明確：
1. `lease_id = self._governance_hub.acquire_lease(...)` (lines 292-296)
2. if lease_id is None → return (lines 297-325)
3. `self._paper_engine.submit_order(...)` (line 344)

acquire_lease 在 submit_order 之前，正確。

#### ttl_seconds=30 是否合理
**PASS**

30 秒 TTL 在 paper/demo 模式下合理（GovernanceHub.acquire_lease 設計中 TTL 表示執行授權的有效期）。既不過短（<1s 可能導致時序問題）也不過長（>300s 可能讓過期意圖執行）。

#### phase2_strategy_routes.py ExecutorAgent 初始化是否正確傳入 governance_hub
**PASS**

```python
_GOV_HUB_FOR_EXECUTOR: Any = None
try:
    from .paper_trading_routes import GOV_HUB as _GOV_HUB_FOR_EXECUTOR
except ImportError:
    pass

EXECUTOR_AGENT = ExecutorAgent(
    config=ExecutorConfig(),
    message_bus=MESSAGE_BUS,
    paper_engine=PAPER_ENGINE,
    governance_hub=_GOV_HUB_FOR_EXECUTOR,  # ← 正確傳入
)
```
從 paper_trading_routes 導入 GOV_HUB，ImportError 時 fallback 為 None（fail-open）。設計合理。

#### scope="TRADE_ENTRY" 與 GovernanceHub 授權設計一致性
**PASS**

`scope="TRADE_ENTRY"` 是明確的業務語義 scope，與 GovernanceHub 的 acquire_lease 接口兼容（GovernanceHub 接受任意 scope 字符串並基於 authorization 判斷）。

---

### 【測試合規】

#### TestExecutorAgentDecisionLease 三場景覆蓋
**PASS**

| 場景 | 測試 | 結果 |
|------|------|------|
| hub=None（fail-open）| test_26 | PASS：submit_order 被調用，report.success=True |
| lease=None（fail-closed，submit_order 未調用）| test_27 | PASS：engine.calls=[], report.success=False, error="governance_lease_acquisition_failed" |
| 有效 lease（正常執行）| test_28 | PASS：submit_order 被調用，acquire_lease 以正確參數調用 |

額外測試：test_29（統計更新）、test_30（report 存檔）、test_31（屬性存儲） — 全部覆蓋邊界用例。

#### test_layer2.py 斷言已更新為 2.0
**PASS**

```python
assert d["daily_hard_cap_usd"] == 2.0  # line 201
assert remaining <= DEFAULT_DAILY_HARD_CAP_USD  # line 242
assert summary["budget"]["daily_hard_cap_usd"] == DEFAULT_DAILY_HARD_CAP_USD  # line 320
```
所有相關斷言已更新，且均使用 `DEFAULT_DAILY_HARD_CAP_USD` 常量引用，不是硬編碼數字（第 201 行是 to_dict() 輸出的字面值斷言，此為合理例外）。

#### 測試總數 ≥ 2561（基準）
**PASS**

實測結果：**2561 passed**（17 pre-existing failed, 1 skipped）。
G-05 新增 6 個 Decision Lease 測試（test_26~31），測試數從 2555 升至 2561，滿足基準要求。

---

### 【G-01 特殊確認】

#### tab-ai.html 中 `max_iterations || 15` 未被修改
**PASS**

```javascript
max_iterations: parseInt($('ai-max-iter').value) || 15,  // saveAIConfig()
['最大迭代', cfg.max_iterations || 15],                  // display
if (!$('ai-max-iter').value) $('ai-max-iter').value = cfg.max_iterations || 15;  // populate
```
這是迭代次數的預設值（MAX_AGENT_ITERATIONS=15），**未被修改**，正確。

#### layer2_types.py 中 Claude 模型定價的 15.00 per_mtok 未被修改
**PASS**

```python
MODEL_SONNET: ModelPricing(
    model_id=MODEL_IDS[MODEL_SONNET],
    input_per_mtok=3.00,
    output_per_mtok=15.00,  # ← 這是 Sonnet 輸出定價，未被修改
    last_verified_date="2026-03-27",
),
MODEL_OPUS: ModelPricing(
    ...
    input_per_mtok=15.00,   # ← 這是 Opus 輸入定價，未被修改
    output_per_mtok=75.00,
),
```
定價表 `15.00` 值未受影響，正確。

---

## 問題彙總

| 嚴重程度 | 問題 | 位置 | 建議 |
|---------|------|------|------|
| WARN（不阻擋，P2 追蹤）| `error=f"Execution error: {e}"` 動態異常字符串 | executor_agent.py:415 | 改為固定字符串 `"execution_engine_error"`，異常細節僅記錄至 logger，不放入審計字段 |
| WARN（不阻擋，P2 追蹤）| `error=f"Order rejected: {rejected_reason}"` | executor_agent.py:366 | 同上建議，或確認 rejected_reason 來源受控（目前為 paper engine 返回值） |

以上兩個 WARN 均為 Batch 11 原有代碼模式（非 G-05 新引入），不阻擋本次 Sprint 0 審查。

---

## 最終結論

**PASS — 可進入 E4**

- G-05 和 G-01 的所有改動均通過審查清單
- 雙語注釋合規（__init__ + execute_order + fail-closed 路徑均有中英注釋）
- 安全：fail-closed 正確，lease=None 時 submit_order 不被調用，固定 error 字符串（lease 路徑）
- 架構：acquire_lease 在 submit_order 前，scope/ttl 合理，governance_hub 正確注入
- 測試：三場景全覆蓋（hub=None, lease=None, lease=valid），總數 2561 達標
- G-01 特殊確認：`|| 15` 迭代預設值及 `15.00` 定價均未被修改

建議 E4 重點回歸：test_26~31（Decision Lease 集成），test_layer2.py 中 hard cap 相關斷言。
