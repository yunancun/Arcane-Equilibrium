# PM 報告：Wave 5 B 方案「多 Agent 正式落地 + H1-H5 接通」

**日期**：2026-03-31
**基準線**：2555 tests passed，Wave 4 全部完成

---

## 現況精確診斷（PM 代碼審計後修訂版）

### 已完成的部分（超出預期）

| 子系統 | 狀態 | 代碼位置 |
|--------|------|---------|
| Scout→Strategist 訂閱 | 已接通：MessageBus 有回調 | phase2_strategy_routes.py:167 |
| Guardian 門控 | 已接通：fail-closed | pipeline_bridge.py:640-667 |
| L1 Ollama Edge Filter | 已接通但 advisory-only | pipeline_bridge.py:673-680 |
| cost_edge_ratio | 已實現：計算 + 等級 + 建議 | risk_manager.py:960-981 |
| Layer2CostTracker | 已實現：session/daily 雙重追蹤 | layer2_cost_tracker.py |

### 真正缺失（B 方案核心工作）

| 缺口 | 描述 | 根因 |
|------|------|------|
| B-MVP-1 | Scout 情報未通過 MessageBus 推送 Strategist | produce_intel() 只存本地列表，未 bus.send |
| B-MVP-2 | Strategist shadow=True：評估後只記錄日誌，不產生 TradeIntent | phase2_strategy_routes.py:155 |
| B-MVP-3 | H1 edge_filter 是 advisory-only，無 Regime 分類 | _check_edge_filter advisory |
| B-MVP-4 | H2-H5 無統一入口（apply_ai_consultation 是 stub）| main_legacy.py:3876 |
| B-MVP-5 | Ollama 調用無成本記錄（L1 免費但調用次數未追蹤）| layer2_cost_tracker 無 Ollama tracking |

---

## Wave 5 計劃

### Sprint 5a（Scout→Strategist + H1，~36h）

| 任務 | 指派 | 工時 |
|------|------|------|
| B-MVP-1：Scout→bus.send(STRATEGIST) | E1-Alpha | 2h |
| B-MVP-3：H1 ThoughtGate blocking + Regime 分類 | E1-Beta | 3h |
| H0 Gate paper warn-only → blocking（同步）| E1-Alpha | 0.5h |
| B-MVP-2：Strategist shadow=False（E4 確認後）| E1-Alpha | 1h |
| E2 代碼審查 | E2 | 2h |
| E4 全量回歸 + 鏈路測試 | E4 | 2h |

目標：2575+ tests passed

### Sprint 5b（H2-H5 薄層 + Ollama Tracking，~28h）

| 任務 | 指派 | 工時 |
|------|------|------|
| B-MVP-4：h_chain.py H1-H5 統一入口 | E1-Gamma | 4h |
| apply_ai_consultation stub → 真實 H 鏈 | E1-Gamma | 1h |
| B-MVP-5：Ollama 調用追蹤 | E1-Delta | 2h |
| E2 代碼審查 | E2 | 1.5h |
| E4 全量回歸 + cost tracking 測試 | E4 | 1.5h |

目標：2600+ tests passed

---

## 3 大風險

1. **Strategist shadow=False 後 TradeIntent 爆炸（HIGH）**：650 符號全掃，需確認 max_pending_intents=50 真實生效 + H0 Gate blocking
2. **H1 Ollama 調用阻塞 on_tick（MEDIUM）**：H1 調用必須在 asyncio.to_thread 或獨立線程，不在 tick 主路徑同步等待
3. **OpenClaw 單點故障（LOW-MEDIUM）**：B-EXT-1 OpenClaw 通信總線延後到 Wave 6，MVP 不包含
