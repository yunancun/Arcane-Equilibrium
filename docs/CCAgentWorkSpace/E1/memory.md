# E1 Memory — 工作記憶

## 項目上下文（2026-03-31）

- 當前 Wave：Wave 5（Sprint 5a-1/5a-2/5a-4 完成）
- 測試基準：2576 passed
- 系統模式：demo_only

## 強制編碼規範（每次寫/改代碼必須遵守）

### 雙語注釋（最高優先，不可省略）
每個新建或修改的函數、類、模塊，必須包含詳細的中英對照注釋，供人類 Operator 閱讀：

```python
# 英文說明（給外部維護者）
# Chinese explanation（給項目 Operator）
def acquire_lease(self, intent_id: str) -> bool:
    """
    Acquire a decision lease before executing any order.
    在執行任何訂單前申請 Decision Lease，確保 AI 輸出不直接等於執行命令。

    Returns False (fail-closed) if governance_hub is None or lease acquisition fails.
    若 governance_hub 為 None 或申請失敗，返回 False（失敗默認收縮）。
    """
```

規則：
- **模塊頂部**：必須有 `MODULE_NOTE`，中英雙語說明模塊用途、所屬層次、主要職責
- **函數/方法**：docstring 必須含中英兩段，說明「做什麼」和「為什麼這樣設計」
- **關鍵邏輯行**：inline comment 說明意圖，而非只是翻譯代碼
- **fail-closed 路徑**：必須注釋說明為什麼選擇這個 fallback 行為
- 純機械性代碼（如簡單 getter）可用單行雙語注釋替代 docstring

### 其他強制規則
- E2+E4 通過前不算完成，不可繞過
- 測試數不得低於任務前基準（目前 2555）
- 新功能必須同步補測試，不欠技術債

## 報告索引

| 日期 | 任務 | 文件位置 |
|------|------|---------|
| 2026-03-31 | G-01 AI 每日硬上限 $15→$2 | `docs/CCAgentWorkSpace/E1/workspace/reports/2026-03-31--g01_ai_daily_cap_fix.md` |
| 2026-03-31 | G-05 ExecutorAgent acquire_lease 插入 | `docs/CCAgentWorkSpace/E1/workspace/reports/2026-03-31--g05_executor_acquire_lease.md` |
| 2026-03-31 | Sprint 5a: H1 ThoughtGate + H2 cost_tracker + H3 ModelRouter | `docs/CCAgentWorkSpace/E1/workspace/reports/2026-03-31--sprint5a_beta.md` |
| 2026-03-31 | Sprint 5a-1/5a-2/5a-4: Scout→Strategist chain + H0 blocking + shadow=False | `docs/CCAgentWorkSpace/E1/workspace/reports/2026-03-31--sprint5a_alpha.md` |
| 2026-03-31 | Sprint 5b-1+5b-2/6: H4 AI輸出驗證 + H5 Ollama CostLogger | `docs/CCAgentWorkSpace/E1/workspace/reports/2026-03-31--sprint5b_gamma.md` |
| 2026-03-31 | Sprint 5b-3+5b-4: apply_ai_consultation 廢棄 + ScoutWorker daemon | `docs/CCAgentWorkSpace/E1/workspace/reports/2026-03-31--sprint5b_delta.md` |
| 2026-03-31 | Wave 6 Sprint 0 TD-1: pipeline_bridge acquire_lease 插入 | `docs/CCAgentWorkSpace/E1/workspace/reports/2026-03-31--sprint0_td1_pipeline_lease.md` |

## 當前測試基準線
2614 passed（Wave 6 Sprint 0 TD-1 完成後，+4 新測試（TestPipelineBridgeDecisionLease），17 pre-existing failures）

## 關鍵發現與教訓

### 2026-03-31 G-01
- `layer2_cost_tracker.py` 的 MODULE_NOTE 中也有 `$15/day` 硬編碼（中英兩處）→ 不在原規格中，但必須一併修改保持一致性
- `tab-ai.html` 第 359 行有第 4 處 `|| 15`（budget display fallback），原規格漏列但屬 AI 預算相關，一併修正
- `tab-ai.html` 第 430、445 行的 `|| 15` 是 `max_iterations` 預設值，與 AI 預算無關，不應修改（已保持不動）
- 測試 `test_layer2.py` 第 201 行直接寫死 `15.0` 而非引用常量 `DEFAULT_DAILY_HARD_CAP_USD`，這是脆弱測試的案例 → 未來建議改為引用常量

### 2026-03-31 Sprint 5a-3/5a-5/5a-6
- `_heuristic_evaluate()` 是模塊頂層函數（非方法），調用時寫 `_heuristic_evaluate(intel, self.config)` 而非 `self._heuristic_evaluate(intel, self.config)` — 任務規格中把它當方法調用是錯誤的
- `Layer2CostTracker.check_daily_budget()` 實際簽名無參數，返回 `(bool, float)` — 任務規格中描述的 `check_daily_budget("l1_9b")` 帶參數版本不存在
- `Layer2CostTracker` 無 `record_call()` 方法 — 使用 `getattr(..., None)` 安全訪問防止 AttributeError
- H1 複雜度跳過測試：`min_relevance` 過濾器在 H1 gate 之前執行，若 `relevance_score < min_relevance` 會 early return — 測試中必須設 `min_relevance` 低於測試 `relevance_score`
- H1 閘門中的 `_evaluate_edge()` 調用必須用 try/except 包裹（外層 `_handle_intel` 沒有捕獲 evaluate_edge 拋出的 TimeoutError 等異常）
- H3 L2 路由：L2 path 在 `threading.Thread` 中執行，立即使用啟發式作為即時結果；需用 `patch("app.strategist_agent.threading.Thread", ...)` 攔截 Thread 創建

### 2026-03-31 Sprint 5a-1/5a-2/5a-4
- `test_strategist_agent.py` was already at 485 lines (from a prior agent session) when I tried to Write ~170 lines. The Write tool PREPENDED my content (merged) rather than overwriting — **Lesson**: always read a file before writing to know what's there and use Edit instead.
- `test_h1_complexity_skip` is flaky when run with the full suite (timing dependent cooldown pollution between tests). Passes when run alone. Pre-existing issue, not caused by my changes.
- H0 Gate blocking change in `pipeline_bridge.py`: replaced warn-only (commented `continue`) with actual `continue` + `intents_h0_blocked` counter. Also updated the comment block to clarify it's now blocking mode.
- `phase2_strategy_routes.py` `StrategistConfig(shadow=True)` → `shadow=False`: added 14-line comment block explaining all pre-conditions (G-05, H0 Gate, Guardian gate) confirmed before switch.
- `_make_h0_gate_mock()` pattern in tests: mock H0Gate `.check()` returns MagicMock with `.allowed`, `.check_name`, `.reason`, `.latency_us` attributes to match the `H0GateResult` interface.
- `intents_h0_blocked` is a new key in `_stats` — used `.get("intents_h0_blocked", 0)` in tests since it won't be in older `get_stats()` that didn't initialize it.

### 2026-03-31 Sprint 5b-1 + 5b-2/6
- `_validate_ai_output()` validates `confidence` in [0.0, 1.0] — the `action` field in task spec doesn't exist in this codebase; actual fields are `has_edge` + `confidence`. Validated `confidence` only (primary safety-critical field).
- H4 validation inserted INSIDE the try/except block in `_ai_evaluate()`, after `json.loads(text)`, before building `EdgeEvaluation`. This correctly handles the case where JSON is valid but structure is semantically invalid.
- H5 cost recording uses `getattr(cost_tracker, "record_ollama_call", None)` pattern — but since we added `record_ollama_call` to `Layer2CostTracker`, the method now exists. Using direct attribute access via `getattr` is still safer for forward compat.
- `_ollama_stats` in `Layer2CostTracker` is lazily initialized (not in `__init__`) to avoid breaking existing tests that create the tracker without calling `record_ollama_call`.
- `get_cost_edge_ratio()` uses `self._adaptive.data_days` + `ADAPTIVE_MIN_DAYS` to determine if ratio is computable; returns `None` when insufficient data (cognitive honesty, principle 10).
- `roi_basis: "paper_simulation_only"` added to both `get_cost_edge_ratio()` and `get_cost_summary()`.

### 2026-03-31 Sprint 5b-3 + 5b-4
- `apply_ai_consultation()` 是 Learning Cockpit Review Queue 占位符，不是現有 AI 管線 — 廢棄方式：
  1. 在函數頂部加 `warnings.warn(DeprecationWarning)` （需先在 main_legacy.py 頂部 import warnings）
  2. 在 `AIConsultationResultData` Pydantic 模型加 `deprecation_notice: str | None = None` 可選字段
  3. 在返回的 dict `data` 中加 `"deprecation_notice": "..."` 字段
  4. 更新路由 docstring 標記 DEPRECATED
  - 兼容性保持：函數簽名不變，Pydantic 模型新增 Optional 字段，現有調用不崩潰
- `AIConsultationResultData` 不接受 `**result["data"]` 中未定義的字段（Pydantic v2 默認 extra="ignore"）
  → 新加的 `deprecation_notice` 必須加入 model 定義才能在 JSON 回傳中出現
- `ScoutWorker` 設計要點：
  1. `interval_seconds` 分段為 1 秒小段睡眠 → `stop()` 可在 ~1 秒內響應
  2. `daemon=True` → 主進程退出時自動終止
  3. `_run_loop` 的 scan 異常用 `except Exception` 吞掉並 `logger.error()` → 不崩潰主程序
  4. `start()` 冪等檢查：`if self._thread is not None and self._thread.is_alive()` → 靜默忽略重複啟動
- `MARKET_SCANNER.start()` 已有自己的 5 分鐘內部循環（`_run_loop` + `time.sleep(interval)`）
  → ScoutWorker 的職責是更高頻（30 分鐘）呼叫 `MARKET_SCANNER.scan()` 並將結果通過 `SCOUT_AGENT.produce_intel()` 注入 Strategist 鏈路
  → `_make_scout_scan_fn()` wrapper 負責：取前 5 機會 → 構建 `symbols` 和 `content` → 調用 `produce_intel()`
- ScoutWorker 初始化失敗是 non-fatal：在 `phase2_strategy_routes.py` 用 `try/except` 包裹，失敗只記 `logger.warning`

### 2026-03-31 Wave 6 Sprint 0 TD-1

- 插入位置：`_process_pending_intents()` 中，邊界過濾器之後（line ~676）、`submit_order()` 之前（line ~701）
  — 這個位置是 Guardian APPROVED 和 MODIFIED 兩條路徑的交匯點，只需插入一次即可覆蓋兩種情況
- `intent` 物件有些是用 `type("StrategyIntent", (), {...})()` 動態創建的，沒有 `intent_id` 屬性
  → 使用 `getattr(intent, "intent_id", None) or f"pb-{intent.symbol}-{intent.side}-{id(intent)}"` 構建穩定的 lease ID
- fail-open vs fail-closed 分層設計（與 G-05 ExecutorAgent 保持一致）：
  - `governance_hub is None` → fail-open（無 Hub 時不阻塞，向後兼容）
  - `acquire_lease() returns None` → fail-closed（Hub 存在但拒絕，跳過 intent）
  - `acquire_lease() raises exception` → fail-closed（治理狀態不明，不允許執行）
- 新增計數器 `intents_lease_failed`：用 `self._stats.get("intents_lease_failed", 0) + 1` 安全遞增
  （不在 `__init__` 中初始化，防止破壞現有測試的 stats 斷言）
- 測試加在 `test_edge_filter_integration.py` 最末：`TestPipelineBridgeDecisionLease` 4 個測試
  — 沿用該文件已有的 `MockIntent`、`mock_paper_engine` 等 fixture 結構，零新增 fixture 依賴

### 2026-03-31 G-05
- `governance_hub.acquire_lease()` 實際簽名為 `(intent_id, scope, ttl_seconds)`，任務規格中描述的 `requester` 參數不存在 → 實際使用 `scope="TRADE_ENTRY"` 正確對應規格意圖
- `governance_hub=None` 採用 fail-open（向後兼容）設計，`governance_hub` 存在但 `acquire_lease()` 返回 `None` 採用 fail-closed — 這兩層行為必須區分，測試 26 和 27 各自覆蓋
- `phase2_strategy_routes.py` 中 `GOV_HUB` 從 `paper_trading_routes` 導入，使用 `_GOV_HUB_FOR_EXECUTOR` 本地別名防止與其他導入衝突
- 測試基準從 2555 升至 2561（新增 6 個 G-05 tests，test_26~31）
- 所有 17 個失敗均為預存在問題（test_batch10_learning_oms/test_ollama_integration/test_integration_phase11/test_learning_tier_gate），與本次改動無關
