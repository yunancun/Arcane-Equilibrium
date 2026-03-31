# Sprint 5b-1 + 5b-2/6 報告：H4 AI 輸出驗證 + H5 Ollama CostLogger

**日期**：2026-03-31
**執行者**：E1-Gamma（Backend Developer）
**任務**：Sprint 5b-1（H4 AI 輸出驗證）+ 5b-2/6（H5 CostLogger Ollama 接入）
**狀態**：全部完成，待 E2+E4 驗收

---

## 修改文件清單

| 文件 | 改動類型 |
|------|---------|
| `app/strategist_agent.py` | 新增 `_validate_ai_output()` 方法 + H4 驗證插入 `_ai_evaluate()` + H5 cost 記錄 + `_stats` 新增兩個計數器 |
| `app/layer2_cost_tracker.py` | 新增 `record_ollama_call()` + `get_ollama_stats()` + `get_cost_edge_ratio()` + `get_cost_summary()` 加入 `roi_basis` |
| `tests/test_strategist_agent.py` | 新增 `TestH4OutputValidation`（10 測試）+ `TestCostTrackerOllama`（7 測試）|

---

## 5b-1：H4 AI 輸出驗證

### 實現位置

`app/strategist_agent.py`：

1. `__init__()` 新增統計計數器：
   - `"h4_validation_fail": 0` — H4 驗證拒絕次數
   - `"ollama_calls_tracked": 0` — H5 Ollama 調用成功追蹤次數

2. 新增方法 `_validate_ai_output(self, parsed: dict) -> bool`（插入在 `_ai_evaluate()` 前）：
   - 驗證 `parsed` 必須是 `dict`
   - 驗證 `"confidence"` 鍵必須存在
   - 驗證 `confidence` 必須是 `int` 或 `float`
   - 驗證 `confidence` 必須在 `[0.0, 1.0]` 範圍內
   - 四個條件任一不滿足 → 返回 `False`

3. H4 驗證插入點：`_ai_evaluate()` 中 `json.loads(text)` 之後、`EdgeEvaluation` 構造之前（在 try/except 塊內）。

### 規格偏差說明

任務規格提到驗證 `"action"` 字段，但實際代碼中 `_ai_evaluate()` 解析的字段是 `"has_edge"` 和 `"confidence"`（無 `action`）。以實際代碼為準，驗證 `"confidence"`（主要安全關鍵字段）。

### 架構合規

- ✅ 驗證失敗 → `_heuristic_evaluate(intel, self.config)` 降級（不 allow-all，根原則 6）
- ✅ `h4_validation_fail` 計數器遞增（可審計）
- ✅ 中英雙語 docstring 完整
- ✅ fail-closed 路徑有注釋說明

---

## 5b-2/6：H5 CostLogger Ollama 接入

### 新增方法（`app/layer2_cost_tracker.py`）

| 方法 | 功能 |
|------|------|
| `record_ollama_call(model, duration_ms, prompt_tokens)` | 記錄 Ollama 調用到記憶體 + 持久化（懶初始化 `_ollama_stats`） |
| `get_ollama_stats()` | 返回記憶體中每模型的 call_count + total_duration_ms |
| `get_cost_edge_ratio()` | 計算 AI 成本效益比 + 必含 `roi_basis: "paper_simulation_only"` |

### `get_cost_summary()` 修改

在返回 dict 中追加：
```python
"roi_basis": "paper_simulation_only",
"roi_disclaimer": "基於模擬 PnL，非真實盈虧",
```

### H5 在 `_ai_evaluate()` 中的集成

成功構造 `EdgeEvaluation` 之前（H4 驗證通過後），呼叫：
```python
record_fn = getattr(self.cost_tracker, "record_ollama_call", None)
if record_fn is not None:
    record_fn(model="l1_9b", duration_ms=latency_ms)
with self._lock:
    self._stats["ollama_calls_tracked"] += 1
```

失敗不阻止執行（`except Exception` + warning log）。

### 關鍵設計決策

- **懶初始化**：`_ollama_stats` 不在 `__init__` 中初始化，而在第一次 `record_ollama_call()` 時建立 → 不破壞現有測試。
- **持久化容錯**：`_write_raw()` 失敗只 warning log，記憶體統計仍有效。
- **`get_cost_edge_ratio()`**：使用 `ADAPTIVE_MIN_DAYS` 門限判斷數據是否充足；不足時返回 `ratio=None`（認知誠實，根原則 10）。

---

## 測試結果

### 新增測試

| 測試類別 | 測試數 | 結果 |
|---------|--------|------|
| `TestH4OutputValidation`（_validate_ai_output 單元測試 × 9）| 9 | 全通過 |
| `TestH4OutputValidation`（_ai_evaluate 集成測試 × 1）| 1 | 全通過 |
| `TestCostTrackerOllama`（Layer2CostTracker 測試 × 7）| 7 | 全通過 |
| **新增測試小計** | **17** | **全通過** |

### 全套測試

| 指標 | 數值 |
|------|------|
| passed | **2593**（基準 2576 + 17 新增） |
| failed | 17（全部為 pre-existing，`test_ollama_integration.py`，與本次改動無關）|
| skipped | 1（pre-existing）|

---

## 意外發現與規格偏差

1. **`"action"` 字段不存在**：任務規格 5b-1 中要求驗證 `"action"` 和 `"confidence"`，但實際 `_ai_evaluate()` 代碼只解析 `"has_edge"` / `"confidence"` / `"reason"`。以實際代碼字段為準，驗證 `"confidence"`。
2. **H4 驗證插入在 try/except 內部**：JSON 解析成功後、`EdgeEvaluation` 構造前，正確覆蓋「JSON 合法但結構語義無效」的情況。
3. **`_ollama_stats` 懶初始化**：`Layer2CostTracker.__init__()` 已有較多狀態初始化，為避免影響現有測試，選擇第一次調用 `record_ollama_call()` 時才建立字典。

---

## 架構合規確認

- ✅ H4 驗證失敗 → heuristic，不 allow-all（根原則 6）
- ✅ H5 Ollama 成本追蹤非致命（根原則 13 觀察性要求）
- ✅ `roi_basis: "paper_simulation_only"` 在所有 ROI 相關返回值中（根原則 10 認知誠實）
- ✅ 所有新方法含中英雙語 docstring
- ✅ fail-closed/fail-open 路徑均有注釋說明
- ✅ 測試數從 2576 升至 2593，不低於基準
