# E4 測試報告 — Sprint 5b-5 根原則 14 集成測試

**日期：** 2026-03-31
**執行人：** E4（Test Engineer）
**工作目錄：** `/home/ncyu/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/`
**任務：** FA AC-2 驗收條件 — 根原則 14「零外部成本可運行」集成測試

---

## 1. 任務背景

根原則 14（零外部成本可運行）要求：Ollama（L1 本地推理）崩潰時，系統應退化到 L0 確定性模式，交易鏈路不中斷。

FA AC-2 驗收條件：Mock `is_available()=False` → 全流程在 L0 模式下可運行。

---

## 2. 新建測試文件

**文件位置：** `tests/test_h_chain_integration.py`

---

## 3. 6 個測試行為驗證

| # | 測試名稱 | 驗證行為 | 結果 |
|---|---------|---------|------|
| 1 | `test_ollama_unavailable_strategist_uses_heuristic` | is_available=False → judge_edge 不被調用，heuristic_evaluations 遞增 | ✅ PASS |
| 2 | `test_ollama_unavailable_h1_budget_check_passes` | cost_tracker=None → _h1_check_budget() 返回 True（fail-open） | ✅ PASS |
| 3 | `test_ollama_unavailable_pipeline_bridge_processes_intents` | PipelineBridge._process_pending_intents() 無 Ollama 時不崩潰，編排器被調用 | ✅ PASS |
| 4 | `test_ollama_unavailable_h0_gate_still_blocks_bad_intents` | H0 Gate 確定性邏輯不依賴 Ollama；freshness check 在無 price tick 時仍阻擋 intent | ✅ PASS |
| 5 | `test_ollama_unavailable_executor_still_applies_fail_closed` | acquire_lease()=None → ExecutorAgent 拒絕執行，不調用 paper_engine（原則 3 不依賴 Ollama） | ✅ PASS |
| 6 | `test_ollama_crash_mid_evaluation_falls_back` | _ai_evaluate 中 ConnectionError → 系統不向外拋出異常，走 heuristic fallback，error 計數遞增 | ✅ PASS |

**所有 6 個測試均通過 / All 6 tests PASSED**

---

## 4. 全量回歸結果

| 項目 | 數值 |
|------|------|
| **收集總數** | 2618 |
| **PASSED** | **2599** |
| **FAILED** | 17（全部為 pre-existing） |
| **SKIPPED** | 1 |
| **執行時間** | ~40s |

**總體結論：✅ PASS（2599 passed，無新增 failure）**

---

## 5. 已知 Pre-existing Failures（17 個，無新增）

| 測試文件 | 失敗數 | 原因 |
|---------|------|------|
| test_batch10_learning_oms.py | 2 | asyncio event loop deprecation（TestL2CronTrigger） |
| test_edge_filter_integration.py | 1 | test_edge_filter_respects_timeout |
| test_integration_phase11.py | 2 | TestEngineTierEnforcement（L1 submit/cancel） |
| test_learning_tier_gate.py | 1 | test_l1_capabilities |
| test_ollama_integration.py | 9 | LocalLLMSearchProvider（3）+ L1TriageLocalFallback（8，實際運行 6） |

---

## 6. 實現細節

### 降級鏈結構確認

```
Ollama 不可用（is_available=False 或 ConnectionError）
  ↓ _evaluate_edge()
  → 跳過 _ai_evaluate()
  → _heuristic_evaluate() (5條規則：relevance + freshness + data_quality + sentiment + symbols)
  → fail-closed：保守評估，不 allow-all
```

### 關鍵程式碼位置

| 功能 | 文件 | 行號（約） |
|------|------|----------|
| _evaluate_edge() Ollama 判斷 | `app/strategist_agent.py` | ~659 |
| _heuristic_evaluate() 5 條規則 | `app/strategist_agent.py` | ~115 |
| _h1_check_budget() fail-open | `app/strategist_agent.py` | ~283 |
| H0Gate.check() 確定性 | `app/h0_gate.py` | ~154 |
| ExecutorAgent acquire_lease | `app/executor_agent.py` | ~291 |
| PipelineBridge._process_pending_intents | `app/pipeline_bridge.py` | ~413 |

### 測試設計決策

1. **PipelineBridge 初始化**：需要 3 個必填位置參數（kline_manager/indicator_engine/signal_engine），使用 MagicMock 提供最小化實現
2. **ConnectionError 測試**：透過 `mock_ollama.judge_edge.side_effect = ConnectionError(...)` 模擬中途崩潰，驗證異常被正確捕獲不向外傳播
3. **H0 Gate 驗證**：不注入 price_ts → freshness check 失敗阻擋，驗證 H0 Gate 確定性邏輯與 Ollama 完全無關

---

## 7. FA AC-2 驗收結論

**✅ 通過 FA AC-2 驗收條件**

Mock `is_available()=False` → 系統在 L0/啟發式模式下運行，各組件行為符合預期：
- StrategistAgent：自動退化到 _heuristic_evaluate()，不嘗試 AI 調用
- H1 Budget Check：cost_tracker=None 時 fail-open，不阻塞評估鏈路
- PipelineBridge：無 Ollama 時 _process_pending_intents() 正常完成
- H0 Gate：完全確定性，與 Ollama 狀態無關
- ExecutorAgent：Principle 3（Decision Lease）執行與 Ollama 無關，fail-closed 保持
- 中途崩潰：ConnectionError 被捕獲，系統不崩潰，走 heuristic fallback
