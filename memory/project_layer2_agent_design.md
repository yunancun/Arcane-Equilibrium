---
name: Layer 2 开放式 AI 推理循环设计（2026-04-23 状态更正）
description: 交易Agent需要"像人一样思考"的能力——自主搜新闻、理解宏观事件、判断预期差。三层架构 L0/L1/L2 已确定；2026-04-23 更正：H1-H5 及 5-Agent 并非 stub，真正待开发的是 Layer 2 自主推理循环 + ExecutorAgent shadow→live 切换。
type: project
originSessionId: 189878ce-df95-4b97-a566-ea1b4e395fe9
---

## ⚠️ 2026-04-23 重大更正

**先前敘述「H1-H5 全為 stub」與 CLAUDE.md §十 舊描述 均過期**。

2026-04-23 Mac→Linux runtime audit 實測（ssh trade-core + Linux srv/ code inspection）：

### 5-Agent 代碼現況（非 stub）
| Agent | 檔案 | 行數 | Runtime 狀態 |
|---|---|---|---|
| StrategistAgent | `control_api_v1/app/strategist_agent.py:85` | 1170 | `shadow=False`（Sprint 5a live，`strategy_wiring.py:243`） |
| GuardianAgent | `control_api_v1/app/guardian_agent.py:87` | 587 | MessageBus subscribed |
| AnalystAgent | `control_api_v1/app/analyst_agent.py:162` | 834 | MessageBus subscribed |
| ExecutorAgent | `control_api_v1/app/executor_agent.py:118` | 630 | **`_shadow_mode=True` 默認**，`strategy_wiring.py:467` `ExecutorConfig()` 未覆蓋 |
| ScoutWorker | `control_api_v1/app/scout_worker.py:38` | 194 | MessageBus subscribed |
| Conductor | `control_api_v1/app/multi_agent_framework.py:675` | 1137 | 5 角色註冊 |

### H1-H5 Middleware（非 stub）
- `h1_thought_gate.py` 185 行
- `model_router.py` (H3) 292 行
- `h4_validator.py` 103 行
- `layer2_{engine,routes,tools,cost_tracker,types}.py` 全實作
- `h0_gate.py` 本地判斷內核

### 當前實際運行模式
- **Python 5-Agent = Advisory Shadow 管線**：Strategist 產出 intent → MessageBus → Guardian 審 → Executor 僅 log（shadow）
- **Rust engine = Trading Hot Path 權威**：strategist_scheduler（Rust 原生）+ orchestrator + IntentProcessor 獨立跑真實交易
- **兩者不耦合**：Python ExecutorAgent shadow 設計意圖明示於 `executor_agent.py:382`「Default shadow=True: log intent but don't submit, to avoid Path A/B conflicts」
- **GUI 消費**：`/api/v1/paper/shadow/decisions` endpoint 被持續查詢（api.log 確認）
- **Linux runtime**：uvicorn PID 720867（4 workers，2026-04-23 19:36 start）

與根原則 #11「Rust 為交易權威」 + project_openclaw_positioning「Python 無交易邏輯」**一致**。

## 真正待開發（W22+ G-1 工作範圍）

先前理解「從 0 實現 5-Agent」**是錯的**。真正的 gap：

### Gap A: ExecutorAgent shadow→live 切換契約
- `executor_agent.py:505-507` 已定義 `shadow_mode=False` 路徑 = 發 SubmitOrder IPC 到 Rust engine
- 待設計：
  - Rust IPC 接收 Python-generated intent 的對接點
  - 與 Rust 內部 strategist_scheduler 並行/替代 的決策仲裁
  - Path A（Rust 自主）/ Path B（Python 5-Agent via IPC）的衝突避免
  - Operator 審批流程（根原則 #3「AI 輸出 ≠ 即時命令」→ Decision Lease）

### Gap B: Layer 2 自主推理循環（原本就是 W22+ 範圍）
- 能力：自主搜新聞、查鏈上數據、綜合推理、形成交易觀點
- 工具箱：web_search / fetch_url / query_onchain / check_derivatives / read_experience / submit_paper_order / record_reasoning
- 升級條件定義（Layer 0→1→2）
- 推理鏈記錄格式
- 成本控制（$0.50-2.00/次，每日 $1-6）

## 三層架構（不變）

```
Layer 0（確定性監控，零成本，持續運行）
  = H0 + Observer + WebSocket + 日曆感知 + 基礎設施監控
  輸出：事件流 → 觸發升級

Layer 1（情境評估，輕量AI，$0.01/次）
  = H1 thought_gate（已 live，185 行）
  判斷："這個異常值不值得深入？"
  輸出：升級/不升級

Layer 2（深度推理，全能力AI Agent循環，$0.50-2.00/次）
  = 新架構，**核心待設計**（Gap B）
  能力：自主搜新聞、查鏈上數據、綜合推理、形成交易觀點
  工具箱：web_search / fetch_url / query_onchain / check_derivatives / read_experience / submit_paper_order / record_reasoning
  每日觸發 1-10 次，成本 $1-6/天
```

## 現有優先級阻塞（不是代碼）

1. **策略邊界全負**（`project_phase5_promotion_edge_crisis.md`）— Agent 再智能也是優化虧損，先翻正 edge
2. **ML 訓練資料不足** — 最大切片 47/200 labels，~3-5d 自然累積到閾值
3. **架構路線未定** — ExecutorAgent live 後是「Python 取代 Rust 策略層」還是「Python 作 Rust 的建議來源」未拍板

**Why:** Operator 終極目標是「超越腳本的交易 Agent」，不是更好的下單機器人。當前 Python 5-Agent shadow 管線已完整，真正 gap 在 Layer 2 自主推理 + shadow→live 整合。
**How to apply:** W22+ G-1 AI Agent 設計工作展開時，重點不是「寫 5-Agent」（已有），而是 (1) Layer 2 工具箱與推理循環 (2) ExecutorAgent IPC→Rust 整合 (3) 決策仲裁與 Operator 審批流程。
