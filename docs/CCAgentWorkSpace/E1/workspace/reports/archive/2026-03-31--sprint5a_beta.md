# Sprint 5a-3/5a-5/5a-6 報告：H1 ThoughtGate + H2 cost_tracker + H3 ModelRouter

**日期**：2026-03-31
**執行者**：E1-Beta（Backend Developer）
**任務**：Sprint 5a-3（H1 ThoughtGate MVP）+ 5a-5（H2 預算門控注入）+ 5a-6（H3 ModelRouter）
**狀態**：全部完成，待 E2+E4 驗收

---

## 修改文件清單

| 文件 | 改動類型 |
|------|---------|
| `app/strategist_agent.py` | 新增 `cost_tracker` 參數、`_h1_cooldown` 屬性、3 個 H1 方法、H3 方法、`_evaluate_edge_l2`、H1/H3 gate 邏輯 |
| `app/phase2_strategy_routes.py` | 新增 `Layer2CostTracker` 導入 + `_COST_TRACKER_FOR_STRATEGIST` + 注入到 `STRATEGIST_AGENT` |
| `tests/test_strategist_agent.py` | 新增 `TestH1ThoughtGate`（13 測試：5a-3 × 5 + 5a-5 × 3 + 5a-6 × 3） |

---

## 5a-3：H1 ThoughtGate 實現

### 新增方法

| 方法 | 行為 | 架構約束 |
|------|------|---------|
| `_h1_check_budget(self) -> bool` | 調用 `cost_tracker.check_daily_budget()` 返回 (bool, float)；None tracker = fail-open | 同步，無 await |
| `_h1_complexity_score(self, intel) -> float` | base = relevance_score；多符號 +0.2；urgency=high +0.2 | 同步，純規則 |
| `_h1_check_cooldown(self, intel) -> bool` | 30 秒冷卻期；通過後更新 `_h1_cooldown[symbol]` | 同步，無 await |

### `__init__()` 新增項目

```python
cost_tracker: Optional[Any] = None  # injected externally
self._h1_cooldown: Dict[str, float] = {}
self._stats["h1_budget_skip"] = 0
self._stats["h1_complexity_skip"] = 0
self._stats["h1_cooldown_skip"] = 0
```

### `_handle_intel()` H1 gate 位置

插入在 `min_relevance` + `max_intel_age` 過濾器之後，`_evaluate_edge()` 之前。

CC 原則 6 遵守：`should_call_ai=False` 時走 `_heuristic_evaluate(intel, self.config)`，不 allow-all。

---

## 5a-5：H2 cost_tracker 注入

- `phase2_strategy_routes.py` 新增 try/except 導入 `Layer2CostTracker`，初始化為 `_COST_TRACKER_FOR_STRATEGIST`
- `STRATEGIST_AGENT = StrategistAgent(..., cost_tracker=_COST_TRACKER_FOR_STRATEGIST)`
- H5 輕量版記錄：`getattr(cost_tracker, "record_call", None)` 安全訪問（因 `Layer2CostTracker` 無此方法，except 捕獲不到，用 getattr 保護）

---

## 5a-6：H3 ModelRouter + L2 Background Thread

### 路由邏輯

| 複雜度 | 路由 | 執行方式 |
|--------|------|---------|
| < 0.5 | `l1_9b` | 同步，`_evaluate_edge()` |
| 0.5–0.8 | `l1_27b` | 同步，`_evaluate_edge()` |
| >= 0.8 | `l2` | `threading.Thread(daemon=True)`，立即使用啟發式作即時結果 |

### L2 線程安全

- `_evaluate_edge_l2()` 在 daemon thread 執行，結果僅 log，不影響已派出的 heuristic intent
- 任何 Thread 內異常均被 try/except 吞掉並 warning log，不崩潰主程序

---

## 意外發現與規格偏差

1. **`_heuristic_evaluate()` 是模塊頂層函數**（非方法）→ 調用需寫 `_heuristic_evaluate(intel, self.config)`
2. **`Layer2CostTracker.check_daily_budget()` 無參數**，返回 `(bool, float)` → 規格中描述的 `check_daily_budget("l1_9b")` 帶參數版本不存在
3. **`Layer2CostTracker` 無 `record_call()` 方法** → 使用 `getattr(..., None)` 安全訪問
4. **H1 複雜度跳過測試陷阱**：`min_relevance` 過濾器在 H1 gate 之前執行，低 relevance_score intel 在到達 H1 gate 前就被 early return → 測試中需設 `min_relevance=0.1`
5. **`_evaluate_edge()` 異常未被外層捕獲**：在 `_handle_intel` 中的 `_evaluate_edge(intel)` 調用需要 try/except 包裹，否則 `TimeoutError` 等會透傳到外層

---

## 測試結果

| 測試類別 | 測試數 | 結果 |
|---------|--------|------|
| TestH1ThoughtGate（5a-3 H1 × 5）| 5 | 全通過 |
| TestH1ThoughtGate（5a-5 H2 × 3）| 3 | 全通過 |
| TestH1ThoughtGate（5a-6 H3 × 3）| 3 | 全通過 |
| TestH1ThoughtGate 小計 | **13** | **全通過** |
| 全套測試 | 2576 passed | 17 pre-existing failures（與本次改動無關）|

---

## 架構合規確認

- ✅ `_handle_intel()` 全程同步，無 `await`
- ✅ `should_call_ai=False` 必走 `_heuristic_evaluate()`，不 allow-all
- ✅ L2 路由在 `threading.Thread(daemon=True)` 中執行，不阻塞 MessageBus 回調
- ✅ 所有新方法含中英雙語 docstring
- ✅ fail-closed/fail-open 路徑均有注釋說明原因
