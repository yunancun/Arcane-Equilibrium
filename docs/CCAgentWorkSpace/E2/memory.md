# E2 Memory — 工作記憶

## 項目上下文（2026-03-31 更新）

- 當前 Wave：Wave 5b 完成（H4 validate_output + H5 record_ollama_call + ScoutWorker + Principle 14 集成測試）
- 測試基準：2609 passed（Sprint 5b 後，全量 passed 比 Sprint 5a 多 54 個）
- 系統模式：demo_only

## 審查強制清單（每次 Code Review 必查項）

### 雙語注釋合規（必查，不通過則打回 E1/E1a）
以下情況必須打回重做：
- [ ] 新建函數/類缺少中英雙語 docstring
- [ ] 模塊頂部缺少 `MODULE_NOTE`（中英雙語模塊說明）
- [ ] fail-closed 路徑沒有注釋說明 fallback 原因
- [ ] 安全相關代碼（認證/授權/參數化查詢）沒有注釋說明用意
- [ ] 修改了已有函數但沒更新 docstring（過時的注釋比沒注釋更危險）

注釋質量標準：
- 注釋應說明「為什麼」，而非只是翻譯「是什麼」
- 中英兩段都要有實質內容，不接受機器翻譯式的逐字對照

### 安全審查（必查）
- [ ] innerHTML 賦值：必須有 ocEsc() 包裝
- [ ] SQL 查詢：必須參數化（無字符串拼接）
- [ ] 異常處理：無 `except: pass` / 無吞異常
- [ ] HTTPException：有 `except HTTPException: raise` 穿透

### 架構合規（必查）
- [ ] 新的 governance 路徑：有 `_require_operator_role()` 驗證
- [ ] 任何 `submit_order()` 調用：前面有 `acquire_lease()` 且 fail-closed
- [ ] 治理不可通過環境變量禁用（無 OPENCLAW_GOVERNANCE_ENABLED 類型的 flag）

### 測試合規（必查）
- [ ] 新功能有對應測試，測試數 ≥ 任務前基準（當前 2555）
- [ ] 邊界用例：None 注入、超時、崩潰路徑有測試

## 報告索引

| 日期 | 任務 | 文件位置 |
|------|------|---------|
| 2026-03-31 | Sprint 0 G-05+G-01 審查 | workspace/reports/2026-03-31--sprint0_g05_g01_review.md |
| 2026-03-31 | Sprint 5a 完整審查 | workspace/reports/2026-03-31--sprint5a_review.md |
| 2026-03-31 | Sprint 5b 完整審查 | workspace/reports/2026-03-31--sprint5b_review.md |

## 歷史審查關鍵發現（累積記憶）

### 2026-03-31 Sprint 0 G-05 + G-01
- **結論**: PASS，可進入 E4
- **測試基準**: 2561 passed（G-05 新增 6 個 Decision Lease 測試 test_26~31）
- **G-05 架構確認**: acquire_lease() 在 submit_order() 之前，lease=None 時 early return（fail-closed 正確），hub=None 時 fail-open（向後兼容，設計意圖明確）
- **G-01 確認**: DEFAULT_DAILY_HARD_CAP_USD=2.0，DOC-08 §4 來源注釋在位，tab-ai.html `|| 15` 迭代預設值未被修改，定價 `15.00` per_mtok 未被修改
- **WARN（P2 追蹤）**: `error=f"Execution error: {e}"` 動態異常字符串在外層 exception 捕獲路徑（executor_agent.py:415）。Batch 11 原有代碼模式，建議 P2 改為固定字符串。
- **WARN（P2 追蹤）**: `error=f"Order rejected: {rejected_reason}"` 同上，来源為 paper engine 返回值，風險可控但不理想。

### 2026-03-31 Sprint 5a（H0 blocking + H1 ThoughtGate + shadow=False + H3 ModelRouter）
- **結論**: PASS，可進入 E4
- **測試基準**: 2879 passed（新增 15 個 Sprint 5a 測試）
- **H0 blocking 確認**: pipeline_bridge.py `continue` 已替換 warn-only；`intents_h0_blocked` 統計正確；4 個 TestH0GateBlocking 全部通過
- **H1 ThoughtGate 確認**: 三個 gate（budget/complexity/cooldown）均正確降級到 `_heuristic_evaluate()`；`should_call_ai=False` 路徑無 allow-all
- **架構約束確認**: 整個 H1/H2/H3 鏈路零 `await`；L2 在 `threading.Thread(daemon=True)` 執行
- **shadow=False 確認**: 前置條件（G-05 acquire_lease + H0 blocking）均已驗證
- **WARN-1（P2）**: `cost_tracker.record_call()` 的 `except Exception: pass` 缺少 logger（L485）
- **WARN-2（P2）**: `_h1_cooldown` 字典無容量上限（650 符號場景安全，但建議 P2 追蹤加 LRU cap）
- **重要觀察**: Sprint 5a 代碼順帶修復了 11 個 pre-existing test failures（34 → 23 FAILED）

### 2026-03-31 Sprint 5b（H4 validate_output + H5 record_ollama_call + ScoutWorker + P14 集成測試）
- **結論**: PASS，可進入 E4
- **測試基準**: 2609 passed（新增 54 個 Sprint 5b 測試）
- **H4 fail-closed 確認**: `_validate_ai_output()` 返回 False → `_heuristic_evaluate()`（無 allow-all）；h4_validation_fail + heuristic_evaluations 雙重計數器在位
- **原則 10 roi_basis 確認**: `get_cost_summary()` 和 `get_cost_edge_ratio()` 均含 `roi_basis: "paper_simulation_only"` + `roi_disclaimer` 中文字段
- **ScoutWorker daemon 確認**: daemon=True + except Exception 吞但記錄日誌 + phase2 初始化在 try/except 包裹 + 非致命
- **新 failure 調查**: 18 FAILED = 17 pre-existing + 0 Sprint 5b 新增（git stash diff 驗證）
- **WARN-1（P2）**: `_ollama_stats` 懶初始化在方法體，建議遷移至 `__init__`（功能正確，純可讀性）
- **WARN-2（P2）**: ScoutWorker interval 不可運行時配置（建議 P3 環境變量覆蓋）
- **WARN-3（P2 繼承）**: `cost_tracker.record_call()` 的 `except Exception: pass`（Sprint 5a 遺留）

### 跨審查觀察（模式記憶）
- ExecutorAgent 的異常 error 字段格式問題已出現兩次，建議建立統一規範：審計字段使用固定 snake_case 錯誤碼，動態信息僅進入 logger。
- phase2_strategy_routes.py 的模塊初始化（`try: from ... except ImportError: pass`）模式貫穿全文件，是已驗證的安全 fallback 模式，E2 不需要每次審查都標記。
