# PA Memory — 工作記憶

## 架構狀態快照（2026-03-31）

### 關鍵模塊狀態
- `pipeline_bridge.py`：PipelineBridge 主管線，on_tick 同步，H0 Gate warn-only
- `governance_hub.py`：GovernanceHub 4 SM（SM-01/02/04/EX-04），RLock 可重入
- `multi_agent_framework.py`：MessageBus + 5 Agent 訂閱完整，Scout→Strategist bus.send 已有代碼
- `strategist_agent.py`：shadow=True（只記錄不產生 TradeIntent），Ollama 已注入
- `phase2_strategy_routes.py`：Strategist shadow=True 在 L155，可通過 directive 動態切換

### H1-H5 真實位置（重要）
- `ai_agents/bybit_thought_gate/` = 獨立腳本體系，從 JSON 讀寫，與 app 層完全無連接
- app 層的 H1-H5 功能分散在：
  - H1 雛形：`pipeline_bridge._check_edge_filter()`（advisory-only）
  - H2：`layer2_cost_tracker.check_daily_budget()`
  - H3：`strategist_agent._ai_evaluate()` + `layer2_engine._l1_triage()`
  - H4：Ollama timeout + max_retries=0
  - H5：`layer2_cost_tracker.record_claude_cost()`（無 Ollama tracking）

### OpenClaw 定位決定（2026-03-31）
- OpenClaw = HTTP 反向代理（/openclaw/{path} → 18789）
- **決定**：Wave 5 不把 OpenClaw 改為通信總線，而是作為審計 sidecar
- MessageBus 保留同進程通信主通道
- OpenClaw 接入方式：MessageBus.audit_callback → async fire-and-forget 推送

## 架構教訓

### asyncio/threading 混用邊界（高頻問題）
- FastAPI async 路由 → event loop，不能直接調用 threading.Lock 的阻塞操作
- `pipeline_bridge.on_tick()` 是同步線程，可以用 threading.Lock
- `layer2_engine.run_session()` 是 async，用 asyncio.Lock（Wave 3b 已修）
- **記住**：每次設計方案時，先確認調用者是 async 還是 sync

### Shadow→Active 切換風險
- Strategist shadow=False 後，TradeIntent 量可能爆炸（650 symbols × Scout 情報頻率）
- **記住**：必須確認 `max_pending_intents = 50` 上限真實生效，且 H0 Gate 從 warn-only 改 blocking

### API Schema 變更風險
- 改 governance endpoint 的 response field name = 高風險（前端 JS 讀取失敗）
- GUI 術語友好化應只改顯示文字，不改 API schema

## Wave 5 架構評估結論（2026-03-31 完成後）

### 關鍵新發現：雙執行路徑並存
- **路徑 A（推薦）**：StrategistAgent → MessageBus → APPROVED_INTENT → ExecutorAgent.acquire_lease() → submit_order() — 完整實施 Principle 3
- **路徑 B（遺留）**：pipeline_bridge._process_pending_intents() → Guardian → submit_order() 直接調用 — **缺少 acquire_lease**
- **影響**：Principle 3 在路徑 B 未完整實施；demo_only 模式下 PaperTradingEngine GovernanceHub gate 兜底，影響有限
- **修復**：TD-1 = pipeline_bridge 注入 governance_hub，Guardian APPROVED 後加 acquire_lease（2h）

### Wave 5 完成狀態
- H0 Gate：blocking 模式已啟用（on_tick 中 continue 替換 warn-only）
- H1-H5：全部接入 StrategistAgent，fail-closed，無 allow-all
- ScoutWorker：daemon thread，30min 定期掃描，produce_intel → MessageBus → StrategistAgent
- ExecutorAgent：訂閱 APPROVED_INTENT，acquire_lease → submit_order 路徑閉合
- 測試：2912 passed（24 pre-existing failures + 17 errors）

### 架構健康度評分：7.2/10
- 治理閉環 8.5 / AI 治理 8.0 / Scout 鏈路 8.5 / 執行路徑一致性 5.5 / 技術債 6.0

### 遺留技術債優先級
- TD-1 (P1)：pipeline_bridge 缺 acquire_lease（pipeline_bridge.py:701）
- TD-2 (P2)：StrategistAgent 雙路徑語義模糊（collect vs bus.send）
- TD-3 (P2)：H5 cost_tracker except Exception: pass 無 logger（strategist_agent.py:485）
- TD-4 (P2)：_h1_cooldown 無容量上限（strategist_agent.py）

### 下一步派發建議摘要
Wave 6 第一批（最大並行）：
- E1-Alpha：TD-1 pipeline_bridge acquire_lease（2h）
- E1-Beta：Batch 1B Cooldown 聯動（1.5h）
- E1a：GUI 術語友好化第一批（3h）

## 報告索引

| 日期 | 報告類型 | 文件位置 |
|------|---------|---------|
| 2026-03-31 | Wave 5 B 方案技術設計 | workspace/reports/2026-03-31--wave5_tech_design.md |
| 2026-03-31 | Phase 1 Batch 1B 可行性評估 | workspace/reports/2026-03-31--batch1b_feasibility.md |
| 2026-03-31 | Wave 5 完成後全鏈路評估（本報告）| workspace/reports/2026-03-31--wave5_architecture_review.md |

## 2026-04-24 PA TODO Audit 發現

### 關鍵架構發現（本次 audit）

1. **ConfigStore + IPC hot-reload 基礎完整** — ArcSwap + Mutex + TOML persist 運作；28 字段 (legacy 21 + EDGE-DIAG-1-FUP-IPC 7) 已支持。唯缺 FUP-SHADOW-ENABLED-IPC (1d 補丁) → Phase 2 Combine shadow flip 無需 rebuild。

2. **ExecutorAgent shadow→live 無 GUI 切換路徑** — `_shadow_mode=true` 硬編碼 (line 482)；預設安全但過渡受限。建議新增 ConfigStore<ExecutorConfig> + IPC endpoint (3-4d)。

3. **Path A/B 互斥機制鬆散** — Path A 代碼完整，Path B 仍存活但缺 acquire_lease；demo_only 時 PaperTradingEngine sandbox 兜底，live 時風險提升。設計上無致命缺陷，ExecutorAgent shadow=true 預設降事件發生機率。

4. **Migration Guard 強化** — V023/V021 雙 DO block Guard A/B RAISE EXCEPTION ✅，符合 CLAUDE.md §七新規則 (2026-04-24 強制)。past silent-noop 問題得解。

5. **Combine/Registry 骨架風險降低** — INFRA-PREBUILD-1 Part A/B 完整落地；Phase 1a dormant、Phase 4 延後，但無架構阻塞。

### Leverage Points TOP 3 (PA 視角)

| # | Leverage | 工作量 | ROI | 優先級 |
|---|----------|--------|-----|--------|
| 1 | FUP-SHADOW-ENABLED-IPC (1 字段補丁) | 1d | Phase 2 無需 rebuild (~3min → <60s) | P2 |
| 2 | ExecutorAgent ConfigStore + GUI toggle | 3-4d | Path A→Live 過渡敏捷 + Principle 3 完整 | P1 |
| 3 | Combine shadow 監控自動化 (健檢+cron) | 2d | 量化 Track P vs L 一致性 + Phase 3 前置條件 | P2 |

### 架構健康度溫度計

- **確定性路徑** (Rust + governance): 8.5/10 — SM-01/04/02 完整、H0 Gate blocking ✅
- **AI 治理接線** (H1-H5 + 5-Agent): 7.5/10 — 實裝完、Conductor stub、ExecutorAgent toggle 缺 GUI
- **IPC 邊界清晰度**: 8.0/10 — 28 字段、FUP-SHADOW 待補
- **交易路徑一致性**: 6.5/10 — Path A/B 互斥鬆散、lease 債標示、demo 兜底
- **技術債**: 6.0/10 — P1-6/7/10/11/19、無架構阻塞
- **整體評分**: **7.2/10** (與 2026-03-31 評估同級)

### 遺留待解項

- **EDGE-DIAG-1 Phase 3 auto-gate 前置** — 等 clean window ≥200 rows (ETA ~2026-05-01)
- **P1-10 PostOnly fee 驗證** — 下 2026-04-28 判決
- **Model Registry canary auto-promote** — Phase 4 第二階段待實施
- **Learning pipeline 下游消費** — 21 schema 表無 consumer，experiment_ledger 結構異常

### 報告路徑

📄 `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-24--4.24TodoAudit.md`

- 10 個主題（架構完整性、Path A/B 設計、Leverage 3+、架構債分類、依賴圖、TODO 重組、技術建議、CLAUDE 一致性、風險熱點、PA 最終判決）
- ~3400 字、詳細文件指針與備查表
- 簽核路由：PM → 下一輪 10-agent 審議
