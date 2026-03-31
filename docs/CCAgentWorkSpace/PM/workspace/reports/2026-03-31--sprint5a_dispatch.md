# PM 派發計劃：Sprint 5a — H1-H5 核心接通

**日期**：2026-03-31
**PM**：基於 TODO.md Wave 5 Sprint 5a 區塊 + wave5_final_dispatch.md 制定
**前置**：Sprint 0 完成（commit d57ed05，G-05 + G-01 已清除）
**當前測試基準**：2561 passed（含 Sprint 0 驗收）
**Sprint 5a 目標**：≥ 2575 passed

---

## 一、依賴關係分析

### 任務依賴圖

```
Sprint 0（✅ 已完成）
│
├─ 5a-1：Scout→Strategist 情報鏈路端到端驗證（驗證 + 觀察點補充，純 E4 風格）
│         → 無阻塞其他任務，但 5a-4 需要其「驗證通過」結論
│
├─ 5a-2：H0 Gate warn-only → blocking（修改 pipeline_bridge.py）
│         → 無依賴，可立即開始
│         → 5a-4 須等 5a-2 完成（5a-4 shadow=False 後 TradeIntent 才需要受 H0 攔截）
│
├─ 5a-3：H1 ThoughtGate MVP（strategist_agent.py _handle_intel() 插入三條規則）
│         → 無依賴，可立即開始
│         → 5a-5 必須在 5a-3 完成後（H2 預算門控插入 H1 判斷後的路徑）
│
├─ 5a-4：Strategist shadow=False 驗證 + 正式切換
│   前置：5a-1（情報鏈路驗證通過）+ 5a-2（H0 blocking 已啟用）+ G-05（✅ 已完成）
│         → 此任務必須在兩條流匯合後才能執行
│         → 5a-4 是 Sprint 5a 的集成驗收節點
│
├─ 5a-5：H2 預算門控接入 Strategist
│   前置：5a-3（H1 ThoughtGate 已建立判斷路徑）
│
└─ 5a-6：H3 ModelRouter 路由接入
    前置：5a-5（H2 已建立預算降級邏輯）
```

### 關鍵發現（代碼審查確認）

- `strategist_agent.py` `_handle_intel()` 第 287 行：**已有** Ollama 路徑（`_evaluate_edge` → `_ai_evaluate`），但**無** H1 三條規則（budget/complexity/cooldown）
- `_evaluate_edge()` 第 449 行：已有 Ollama 超時回退到 `_heuristic_evaluate()`，**符合** CC 原則 6 要求，H1 實現需保留此設計
- `pipeline_bridge.py` `_process_pending_intents()`：H0 Gate 第 500-525 行為 warn-only，`if not _h0_result.allowed: logger.warning(...)` 後**繼續執行**（未 `continue`）
- `StrategistConfig.max_pending_intents = 50` 已在代碼中定義，但**未在 `_process_pending_intents` 中強制截斷**
- `phase2_strategy_routes.py` 第 154 行：`StrategistConfig(shadow=True)` 確認
- `multi_agent_framework.py` 第 428 行：`produce_intel()` 已有 `bus.send(msg)` → 5a-1 是驗證任務

---

## 二、並行分組

### E1-Alpha 執行流

```
Sprint 0 完成後立即開始（5a-1、5a-2 並行）：

  5a-1：Scout→Strategist 情報鏈路驗證（1h）
       → 純驗證 + E4 觀察點補充，不修改生產代碼
       → 輸出：verified_flag = True（供 5a-4 前置確認）

  5a-2：H0 Gate warn-only → blocking（1h）
       → 修改 pipeline_bridge.py _process_pending_intents()
       → 同時確認 max_pending_intents 截斷真實生效

  ↓（5a-1 + 5a-2 均完成後）

  5a-4：Strategist shadow=False 驗證 + 正式切換（1.5h）
       → 前置：5a-1（情報鏈路 ✅）+ 5a-2（H0 blocking ✅）+ G-05（✅）
```

### E1-Beta 執行流

```
Sprint 0 完成後立即開始：

  5a-3：H1 ThoughtGate MVP（3h）
       → 修改 strategist_agent.py _handle_intel()
       → 插入 budget / complexity / cooldown 三條規則
       → CC 強制：timeout → _heuristic_evaluate()，不可 allow-all

  ↓（5a-3 完成後）

  5a-5：H2 預算門控接入（1.5h）
       → 在 H1 should_call_ai=True 後接入 layer2_cost_tracker.check_daily_budget()

  ↓（5a-5 完成後）

  5a-6：H3 ModelRouter 路由接入（2h）
       → 基於 complexity + urgency 路由 l1_9b / l1_27b / l2
       → L2 必須在 threading.Thread 執行，不阻塞 on_tick
```

### 並行時序圖

```
時間軸  →  T+0     T+1h    T+2h    T+3h    T+4h    T+5h    T+5.5h  T+7.5h
Alpha:     5a-1                    5a-4
           5a-2
Beta:      ──── 5a-3 ────          5a-5     5a-6
                                            ↓       ↓
匯合節點:                  均完成  ────────────────── E2(2h) → E4(2h)
```

---

## 三、每個任務的具體派發指令

---

### 5a-1：Scout→Strategist 情報鏈路端到端驗證（E1-Alpha，1h）

**性質**：驗證任務，不寫生產代碼。輸出：驗證清單 + E4 測試補充。

**驗證清單（逐項確認）**：

1. 確認 `multi_agent_framework.py` 第 396-436 行 `produce_intel()` 的 `bus.send()` 調用路徑
   → 確認 `relevance_score >= self.config.relevance_threshold`（閾值在 ScoutAgent config 中）

2. 確認 `pipeline_bridge.py` 第 903 行（或附近）`produce_intel()` 調用存在，且帶 `relevance_score` 參數

3. 確認 `MessageBus` 有 Strategist 訂閱（subscribe 到 STRATEGIST role）

4. 確認 `strategist_agent.py` `on_message()` 第 276 行 `MessageType.INTEL_OBJECT` 分支被調用到 `_handle_intel()`

5. 檢查 `_stats["intel_received"]` 計數器是否在集成測試中被遞增

**如發現斷鏈**：立即報告給 PM，不自行修復（5a-1 是驗證不是修復）。

**補充 E4 觀察點**：
- 在 `tests/test_strategist_agent.py`（若存在）補 1-2 個測試：Mock bus.send() 觸發 → 確認 `_stats["intel_received"]` +1
- 若已有此類測試，確認通過即可

**驗收**：輸出一份「5a-1 驗證報告」（簡短，含每個確認點的 True/False）。

---

### 5a-2：H0 Gate warn-only → blocking（E1-Alpha，1h）

**文件**：`/home/ncyu/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/pipeline_bridge.py`

**問題**：`_process_pending_intents()` 第 513-525 行，H0 Gate 返回 `allowed=False` 時只 `logger.warning()`，未 `continue` 跳過該 intent。

**修復步驟**：

1. 在 `_h0_result.allowed == False` 分支中：
   ```python
   # 原代碼（warn-only）：
   if not _h0_result.allowed:
       logger.warning("H0Gate blocked (paper warn-only): ...")
       # intent NOT rejected — continues to submit

   # 修復後（blocking）：
   if not _h0_result.allowed:
       logger.warning(
           "H0Gate blocked intent: %s %s reason=%s latency=%dμs — intent REJECTED"
           " / H0 門控攔截：intent 已拒絕",
           intent.symbol, intent.side, _h0_result.reason, _h0_result.latency_us
       )
       with self._lock:
           self._stats["intents_h0_blocked"] = self._stats.get("intents_h0_blocked", 0) + 1
       continue  # ← 關鍵修復
   ```
   注意：移除原 "paper warn-only" 和 "intent NOT rejected" 字樣，改為明確 "REJECTED"

2. 確認 `max_pending_intents` 截斷真實生效：在 `_process_pending_intents()` 開頭找到 `collect_pending_intents()` 後，確認是否有 `intents = intents[:self._config.max_pending_intents]` 類似截斷。若無，補加：
   ```python
   if len(intents) > 50:  # max_pending_intents
       logger.warning("Pending intents truncated: %d → 50", len(intents))
       intents = intents[:50]
   ```

3. 添加 `intents_h0_blocked` 到 `_stats` 初始化字典（`__init__` 中）

**雙語注釋要求**：修改處補中英雙語 inline comment，說明為何從 warn-only 升級為 blocking。

**E4 測試**：補或確認 `test_pipeline_bridge.py` 中有 H0 Gate blocking 的測試（Mock `h0_gate.check()` 返回 `allowed=False` → 確認 intent 不被提交到 paper engine）。目標 +2 tests。

**驗收**：`max_pending_intents` 截斷有效，H0 blocking 有測試覆蓋。

---

### 5a-3：H1 ThoughtGate MVP（E1-Beta，3h）

**文件**：`/home/ncyu/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategist_agent.py`

**目標**：在 `_handle_intel()` 第 332 行（`evaluation = self._evaluate_edge(intel)` 之前）插入 H1 判斷層。

**H1 三條規則**（按順序，任一 False → 直接 `return`，不繼續）：

**規則 1：Budget Check（是否應呼叫 AI？）**
```python
# H1-1: Budget gate — should we invoke AI at all?
# H1-1：預算門控 — 是否應呼叫 AI？
should_call_ai = self._h1_check_budget(intel)
if not should_call_ai:
    logger.info(
        "H1 budget gate: skipping AI for %s, using heuristic / H1 預算門控：跳過 AI，使用啟發式",
        intel.symbols
    )
    with self._lock:
        self._stats["h1_budget_skip"] = self._stats.get("h1_budget_skip", 0) + 1
    evaluation = _heuristic_evaluate(intel, self.config)
    # Continue to intent production logic below (do not return early)
    # 繼續後續 intent 產出邏輯（不提前 return）
```

**規則 2：Complexity Check（信號是否足夠複雜值得呼叫 AI？）**
```python
def _h1_complexity_score(self, intel: IntelObject) -> float:
    """Rule-based complexity heuristic (no AI call).
    基於規則的複雜度啟發（不呼叫 AI）。
    High complexity: multiple symbols, low data quality, high relevance."""
    score = 0.0
    if len(intel.symbols) > 1:
        score += 0.3
    if intel.data_quality == DataQualityLevel.INFERENCE:
        score += 0.3
    if intel.relevance_score > 0.7:
        score += 0.4
    return min(score, 1.0)
```
若 `complexity_score < 0.3`（threshold 可設為 config 參數，默認 0.3）→ 使用 heuristic，不呼叫 AI。

**規則 3：Cooldown Check（同符號近期是否已評估過？）**
```python
def _h1_check_cooldown(self, intel: IntelObject) -> bool:
    """Check per-symbol cooldown to avoid redundant AI calls.
    檢查每個符號的冷卻時間，避免重複 AI 呼叫。
    Returns True if cooldown cleared (OK to proceed), False if in cooldown."""
    now_ms = int(time.time() * 1000)
    cooldown_ms = 30_000  # 30s 默認冷卻
    with self._lock:
        for sym in intel.symbols:
            last_eval = self._h1_cooldown.get(sym, 0)
            if now_ms - last_eval < cooldown_ms:
                return False  # In cooldown / 冷卻中
        # Update cooldown timestamps
        for sym in intel.symbols:
            self._h1_cooldown[sym] = now_ms
    return True
```

**CC 強制要求（必須完全符合）**：
- `_evaluate_edge()` 中 Ollama `timeout` 路徑（第 462-466 行）已有 `except Exception → _heuristic_evaluate()`，H1 實現**不得改動此路徑**
- H1 本身不呼叫 Ollama，只做純規則判斷（< 1ms）
- `should_call_ai = False` 時必須走 `_heuristic_evaluate()`，**不得 allow-all（直接 return has_edge=False + confidence=0）**
- `should_call_ai` 字段的含義：True = 值得呼叫 AI 評估；False = 直接走 heuristic，但 heuristic 仍可能 has_edge=True

**需新增到 `__init__`**：
```python
self._h1_cooldown: Dict[str, int] = {}  # symbol → last_eval_ms
```
並在 `_stats` 初始化中添加：
```python
"h1_budget_skip": 0,
"h1_complexity_skip": 0,
"h1_cooldown_skip": 0,
```

**PA 架構警示**：`_handle_intel()` 是 MessageBus 同步回調（在 `on_message()` 中調用），**不可使用 `await`**。所有 H1 邏輯必須是同步的。H1 複雜度評分和冷卻檢查都是同步操作，符合要求。

**雙語注釋**：每個 H1 方法必須有中英雙語 docstring。

**E4 測試目標**：+5 tests（budget_skip / complexity_low / cooldown_hit / all_pass_to_ai / timeout_fallback_heuristic）

**驗收**：H1 三條規則各有獨立測試，timeout 路徑測試通過。

---

### 5a-4：Strategist shadow=False 驗證 + 正式切換（E1-Alpha，1.5h）

**前置**：5a-1 verified ✅ + 5a-2 blocking ✅ + G-05 ✅（已完成）

**文件**：
- `phase2_strategy_routes.py` 第 152-158 行（`STRATEGIST_AGENT = StrategistAgent(config=StrategistConfig(shadow=True))`）

**步驟**：

**Step 1：AC-3 確認（shadow=True 狀態下）**
- 在 demo/paper 環境確認 `_stats["intel_received"]` 計數器遞增（有情報到達 Strategist）
- 方法：呼叫 `/scout/stats` 或 `/strategist/stats` 端點（若存在），或查看日誌中 "intel_received" 計數
- 輸出：確認 AC-3（intel_received > 0）

**Step 2：shadow=False 切換**
修改 `phase2_strategy_routes.py`：
```python
# 原：
STRATEGIST_AGENT = StrategistAgent(
    config=StrategistConfig(shadow=True),   # shadow 模式：僅記錄
    ...
)

# 改為（保留 shadow=True 作為安全默認，但通過指令切換）：
# 注意：實際上保持 shadow=True 為啟動默認，需要 Operator 手動切換
# 但需確認 SYSTEM_DIRECTIVE shadow_off 指令能正確切換
```

實際修復點：確認 `strategist_agent.py` 第 438-443 行 `shadow_off` 處理器能正確更新 `self.config.shadow = False`，且 `collect_pending_intents()` 在 `shadow=False` 後真實返回 intents。

如果要從代碼層切換（非 runtime 指令），修改 `phase2_strategy_routes.py` 第 155 行：
```python
config=StrategistConfig(shadow=False),  # 正式啟用 intent 產出
```
並加 MODULE_NOTE 說明此為有意識的切換，需要 H0（已 blocking）+ G-05（已完成）才安全。

**Step 3：完整鏈路驗證**
確認（代碼層 + 測試層）：`TradeIntent → Guardian._handle_trade_intent() → acquire_lease() → execute_order()` 路徑存在且：
- `governance_hub.is_authorized()` 真實檢查
- `acquire_lease()` 在 `executor_agent.py` 中真實被呼叫（G-05 修復確認）

**Step 4：如果 shadow=False 會產生大量 TradeIntent**
確認 5a-2 的 `max_pending_intents` 截斷已生效（不超過 50），Strategist 的 `max_pending_intents: int = 50` 字段在 `collect_pending_intents()` 中有截斷。

**E4 測試**：+2 tests（shadow=False 後 collect_pending_intents() 返回非空列表 / shadow=True 返回空列表）

**驗收**：shadow=False 切換後，測試確認 intent 流向 Guardian。

---

### 5a-5：H2 預算門控接入 Strategist（E1-Beta，1.5h）

**文件**：`strategist_agent.py` `_handle_intel()` + `layer2_cost_tracker.py`

**前置**：5a-3 完成（H1 已建立 should_call_ai=True 路徑）

**實現**：在 H1 判斷 `should_call_ai=True` 後，插入 H2 預算檢查：

```python
# H2: Budget gate — 每日 AI 預算上限檢查
# H2: Budget gate — check daily AI spend cap
if should_call_ai and self._cost_tracker is not None:
    budget_ok, recommended_tier = self._cost_tracker.check_daily_budget("l1_9b")
    if not budget_ok:
        logger.warning(
            "H2 budget exceeded: falling back to heuristic / H2 預算超限：回退啟發式"
        )
        with self._lock:
            self._stats["h2_budget_exceeded"] = self._stats.get("h2_budget_exceeded", 0) + 1
        should_call_ai = False  # Force heuristic path / 強制走啟發式路徑
```

**需新增**：
- `__init__` 新增 `cost_tracker: Optional[Any] = None` 參數
- `self._cost_tracker = cost_tracker`
- `phase2_strategy_routes.py` 中注入 cost_tracker 實例（若 `layer2_cost_tracker` 模塊有全局實例）

**CC 原則 10 確認**：H2 不在 API 回應層，不需要 `roi_basis` 字段（此要求在 Sprint 5b H5 中處理）。

**E4 測試**：+3 tests（budget_ok→proceed_to_AI / budget_exceeded→heuristic / no_cost_tracker→proceed）

---

### 5a-6：H3 ModelRouter 路由接入（E1-Beta，2h）

**文件**：`strategist_agent.py` `_handle_intel()`

**前置**：5a-5 完成（H2 已確定 should_call_ai=True + tier）

**實現**：在 `should_call_ai=True` 且 H2 通過後，基於 complexity + urgency 路由：

```python
# H3: Model router — select appropriate model tier
# H3：模型路由器 — 根據複雜度選擇合適的模型層級
def _h3_route_model(self, intel: IntelObject, complexity: float) -> str:
    """Route to appropriate model tier based on intel complexity.
    根據情報複雜度路由到適當模型層級。

    l1_9b:  fast path, low complexity (complexity < 0.5)
    l1_27b: deep analysis, medium complexity (0.5 <= complexity < 0.8)
    l2:     reserved for highest stakes (complexity >= 0.8) — run in thread
    """
    if complexity >= 0.8:
        return "l2"
    elif complexity >= 0.5:
        return "l1_27b"
    else:
        return "l1_9b"
```

**L2 必須在 threading.Thread 執行**（PA 強制要求）：
```python
if model_tier == "l2":
    # L2 is slow (10-30s) — MUST NOT block on_tick event loop
    # L2 速度慢（10-30s）— 不得阻塞 on_tick 事件循環
    import threading
    t = threading.Thread(
        target=self._async_l2_evaluate,
        args=(intel,),
        daemon=True,
    )
    t.start()
    # Fall back to l1_9b for immediate response / 立即回應用 l1_9b
    model_tier = "l1_9b"
```

**E4 測試**：+3 tests（l1_9b routing / l1_27b routing / l2 → thread spawned + immediate fallback）

---

## 四、E2+E4 驗收節點

### 何時進入 E2？

所有六個任務均完成後（兩條流匯合，E1-Alpha 的 5a-4 和 E1-Beta 的 5a-6 均完成）。

**預計時間點**：T+5h（兩條流最慢的完成時間）。

### E2 審查重點清單

1. **H1 timeout 路徑**：`_evaluate_edge()` 中 except → `_heuristic_evaluate()` 路徑完整保留，H1 新增邏輯不破壞此路徑
2. **H1 `should_call_ai=False`**：必須走 heuristic，不得 allow-all（直接返回 has_edge=False）
3. **L2 在獨立線程**：`model_tier == "l2"` 時 `threading.Thread` 已 spawn，主路徑用 l1_9b
4. **max_pending_intents 截斷**：確認 pipeline_bridge.py 有實際截斷邏輯
5. **H0 blocking 的 `continue`**：確認 intent 在 H0 denied 後真正跳過，不被提交
6. **雙語注釋**：所有新函數、修改函數有中英 docstring
7. **`_stats` 字典**：所有新計數器已在 `__init__` 中初始化
8. **CC 原則 6**（失敗默認收縮）：H1/H2/H3 任何層級失敗 → heuristic，不是 allow-all

### E4 回歸

**目標測試數**：≥ 2575 passed

**E4 測試增量預計**：
- 5a-1：+2 tests（情報鏈路觀察點）
- 5a-2：+2 tests（H0 blocking）
- 5a-3：+5 tests（H1 三條規則各測試）
- 5a-4：+2 tests（shadow=False intent 流）
- 5a-5：+3 tests（H2 預算門控）
- 5a-6：+3 tests（H3 ModelRouter）
- **合計**：+17 tests → 2561 + 17 = **2578 tests**（超過目標 2575）

---

## 五、風險提示

### 風險 1：H1 `_handle_intel()` 是同步方法（PA 警示）
- `_handle_intel()` 從 `on_message()` 同步調用，MessageBus 回調不支持 async
- H1/H2/H3 的所有新增邏輯必須是**純同步**
- 唯一例外：H3 的 L2 路由通過 `threading.Thread` 異步執行，但觸發點是同步的
- **E2 必查**：確認沒有 `await` 出現在 `_handle_intel()` 調用鏈中

### 風險 2：shadow=False 後 650 符號可能大量 TradeIntent（5a-4）
- `max_pending_intents=50` 截斷必須在 `_process_pending_intents()` 中真實執行
- 5a-2 修復時需同步確認此截斷
- 若截斷缺失，650 符號在活躍市場可能每 tick 產生數百個 intent，壓垮 paper engine
- **E4 壓測**：建議在集成測試中 mock 100+ intents 輸入，確認只有 50 個被處理

### 風險 3：H1 budget check 的 `cost_tracker` 可能為 None（5a-5）
- `StrategistAgent.__init__` 新增 `cost_tracker` 參數後，`phase2_strategy_routes.py` 的初始化調用點必須同步更新
- 若不注入 cost_tracker，H2 應退化為「跳過檢查，直接 should_call_ai=True」（fail-open 可接受）
- **E2 確認**：cost_tracker=None 的測試路徑已覆蓋

### 風險 4：CC 強制要求（原則 6 - 失敗默認收縮）
- H1 `should_call_ai=False` 不等於 intent 一定被拒絕
- heuristic 評估可能仍然返回 `has_edge=True`（這是正確的！）
- 錯誤實現：`should_call_ai=False` → 直接 `return`（這是 allow-all 的反面，會漏掉合法交易機會）
- 正確實現：`should_call_ai=False` → `_heuristic_evaluate(intel, config)` → 按評估結果繼續

---

## 六、Sprint 5a 執行 SOP

1. 主 Claude 啟動 E1-Alpha（5a-1 + 5a-2 並行 → 5a-4）
2. 主 Claude 同時啟動 E1-Beta（5a-3 → 5a-5 → 5a-6）
3. E1-Alpha 的 5a-1 完成後輸出驗證報告（不阻塞 5a-2）
4. E1-Alpha 的 5a-2 完成後等待 5a-1 報告，兩者完成後啟動 5a-4
5. E1-Beta 串行執行 5a-3 → 5a-5 → 5a-6
6. 兩條流均完成後，啟動 E2 審查
7. E2 通過後啟動 E4 回歸
8. E4 達到 ≥ 2575 tests → Sprint 5a 完成
9. PM 更新 TODO.md + CLAUDE.md + README.md（Wave 5 Sprint 5a 全部完成）
