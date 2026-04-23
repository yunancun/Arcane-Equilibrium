---
name: 5-Agent + H1-H5 Runtime 實際狀態（2026-04-23 audit）
description: Python 5-Agent + H1-H5 middleware 代碼完整且 live 於 shadow 管線；Rust engine 獨立做真實交易；兩者 intent 不耦合。取代先前「全 stub」過期敘述。
type: project
originSessionId: c75a70d6-970a-40ed-8b18-ef89e6d96e73
---
## 2026-04-23 Linux runtime audit 結論

ssh trade-core + code inspection 實測結果。

### 1. 代碼實現度（非 stub）

| 層 | 組件 | 檔案:行 | 行數 | 測試 |
|---|---|---|---|---|
| 5-Agent 角色層 | StrategistAgent | `strategist_agent.py:85` | 1170 | test_strategist_agent / test_strategist_stress / test_strategist_audit_wiring |
| | GuardianAgent | `guardian_agent.py:87` | 587 | test_guardian_agent_unit / test_guardian_audit_wiring / test_batch8_guardian_integration |
| | AnalystAgent | `analyst_agent.py:162` | 834 | test_analyst_agent_unit / test_analyst_agent_registry / test_batch9_perception_analyst_integration |
| | ExecutorAgent | `executor_agent.py:118` | 630 | test_executor_agent_unit / test_executor_audit_wiring / test_batch11_executor_exchange |
| | ScoutWorker | `scout_worker.py:38` | 194 | test_scout_worker / test_scout_integration / test_scout_audit_wiring |
| | Conductor | `multi_agent_framework.py:675` | 1137 | test_multi_agent_framework / test_message_bus_load / test_batch7_conductor_strategist |
| H1-H5 治理層 | h1_thought_gate | `h1_thought_gate.py` | 185 | test_h_chain_integration |
| | model_router (H3) | `model_router.py` | 292 | |
| | h4_validator | `h4_validator.py` | 103 | |
| | Layer2 系列 | `layer2_{engine,routes,tools,cost_tracker,types}.py` | — | |
| | h0_gate | `h0_gate.py` | — | |

**5-Agent 總計 ~4552 行工作代碼**，audit_bridge 接線到 GovernanceHub，根原則 #8「交易可解釋」有實施。

### 2. Runtime 狀態（2026-04-23 19:36 UTC Linux）

- **uvicorn PID 720867**（4 workers，`app.main:app --host 0.0.0.0 --port 8000`）
- **StrategistAgent**: `config=StrategistConfig(shadow=False)` ← Sprint 5a live mode
- **GuardianAgent**: 已 subscribe MessageBus
- **AnalystAgent**: 已 subscribe + 被 `ai_service.py:480-521` 作 round_trip 歸因（C1）
- **ScoutWorker**: 已 subscribe + 被 `ai_service.py:600` 作情報 forward（C2）
- **ExecutorAgent**: **`_shadow_mode=True`**（`executor_agent.py:482` 默認，`strategy_wiring.py:467` `ExecutorConfig()` 未覆蓋）
- **GUI endpoint**: `/api/v1/paper/shadow/decisions` 被持續查詢（api.log 實證）

### 3. 實際決策流

```
Python 5-Agent（Advisory Shadow）                 Rust engine（Trading Authority）
  ─────────────────────────────                    ──────────────────────────
  ScoutWorker → 情報                                tick_pipeline/on_tick
       ↓                                                  ↓
  StrategistAgent → intent（live）                   strategist_scheduler（Rust 原生）
       ↓                                                  ↓
  GuardianAgent → 審查                                orchestrator + IntentProcessor
       ↓                                                  ↓
  ExecutorAgent → SHADOW LOG（不發 IPC）              risk_checks + Priority 6
       ↓                                                  ↓
  AgentAuditBridge → GovernanceHub                    真實 SubmitOrder → Bybit
       ↓
  GUI `/api/v1/paper/shadow/decisions`
```

兩條管線並行獨立。Python intent 進入 audit/observability 層，不進 trading hot path。

### 4. 關鍵設計意圖引用

`executor_agent.py:382`:
> Default shadow=True: log intent but don't submit, to avoid Path A/B conflicts.

`executor_agent.py:501-507`:
> When shadow_mode=True (default): logs the intent and returns a shadow report
> When shadow_mode=False: sends SubmitOrder IPC to Rust engine, which routes

→ 升級 path 已設計好，只待 G-1 決策時啟動。

### 5. CLAUDE.md §十 敘述修正

舊：「AI 治理層 (W22-W23) ⬜（H1-H5 AI agent 目前全 stub，待 G-1 R-06 展開）」
新（2026-04-23 updated）：「AI 治理層 (W22-W23) 🟡 部分 live」+ 詳細狀態說明

### 6. 待 G-1 真正展開的工作

- ExecutorAgent `_shadow_mode=False` 切換的整合契約（Python intent → Rust IPC）
- Path A（Rust 自主）/ Path B（Python via IPC）決策仲裁
- Layer 2 自主推理循環（新聞/宏觀/工具箱，見 `project_layer2_agent_design.md`）

**Why:** 先前認知「5-Agent 全 stub，需要從 0 寫」為誤，浪費路線圖估算；實際 Python 管線已 live shadow，真正 gap 在整合 + Layer 2 推理。
**How to apply:** 任何提及「開發 5-Agent」「H1-H5 stub」的對話，先檢查此 memory；如 operator 又說「全 stub」請 push back 指向本 audit。
