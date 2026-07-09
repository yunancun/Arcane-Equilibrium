# PA 技術設計方案：Wave 5 多 Agent 落地 + H1-H5 接通

**日期**：2026-03-31

---

## 關鍵架構發現

### H1-H5 真實位置
- `ai_agents/bybit_thought_gate/` = 獨立腳本，非運行時代碼
- app 層的 H1-H5 分散在：layer2_engine.py / layer2_cost_tracker.py / risk_manager.py / strategist_agent.py

### OpenClaw 定位決定
- MessageBus 保留內部通信主通道
- OpenClaw 作為審計 sidecar（audit_callback → async fire-and-forget）
- Wave 5 不把 OpenClaw 改為通信總線

---

## H1-H5 接入流程

```
[Scout 情報]
  → MessageBus → StrategistAgent.on_message()
      ↓
  H1: should_call_ai(intel)?
      ├─ 否 → _heuristic_evaluate() → TradeIntent(confidence="heuristic")
      └─ 是
          ↓
      H2: check_budget(model_tier)
          ├─ 超預算 → 降級到 L1
          └─ 有餘額
              ↓
          H3: ModelRouter.route(complexity, urgency)
              → l1_ollama_9b / l1_ollama_27b / l2_sonnet
              ↓
          [AI 調用：judge_edge() 或 run_session()]
              ↓
          H4: validate_output(ai_response)
              ↓
          H5: CostLogger.log(model, tokens, cost, intent_id)
              ↓
          TradeIntent + {ai_confidence, model_used, cost_usd}
              ↓
  → Guardian.review_intent() → acquire_lease() → 執行
```

**重要規則**：
- L1 Ollama：Strategist._handle_intel() 中同步執行（有 timeout）
- L2 Sonnet：spawn Thread，結果異步回傳
- H5：同步寫入內存，批量刷寫磁盤

---

## Scout→Strategist 方案

事件驅動，由 Scout API 觸發，MessageBus 回調機制已足夠。
缺失項：ScoutWorker 後台線程（30min 定時掃描）+ produce_intel() 後的 bus.send()。

---

## E2 重點審查高風險點

1. **Strategist shadow=False 副作用**：TradeIntent → OrderIntent 轉換邏輯，max_pending_intents=50 上限
2. **MessageBus 同步回調阻塞**：bus.send() 在 on_tick 主線程中同步調用
3. **asyncio/threading 混用**：Layer2CostTracker.record() 是否有 asyncio 依賴

---

## 派發建議

| 優先級 | 工項 | 估時 |
|--------|------|------|
| P1 | scout_routes produce_intel() 調用路徑確認 | 2h |
| P1 | Strategist shadow=False + max_pending_intents 驗證 | 3h |
| P1 | H1 ThoughtGate 最小可用版（budget/complexity/cooldown 三條規則）| 4h |
| P2 | H5 CostLogger 接入 Layer2CostTracker | 3h |
| P2 | ScoutWorker 後台線程 | 4h |
| P3 | OpenClaw audit_callback sidecar | 5h |
