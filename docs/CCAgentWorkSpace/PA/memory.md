# PA Memory — 工作記憶

## STRATEGY-WIRING-SPLIT P2（2026-04-28）

**結論**：`strategy_wiring.py` 1060 → **784 LOC**（≤800 進入合規），抽 2 sibling：
`strategy_wiring_h_state.py` 133 LOC（H State Invalidator G3-08 Phase 1C，純 leaf top-level）+
`strategy_wiring_scanner.py` 338 LOC（MarketScanner/AutoDeployer/ScoutWorker/scout_routes/Auto-Observation 5 子塊，函數 `wire_market_scanner_and_workers(deps)` 模式）。Pure refactor 0 production behavior change。

**Mac pytest**：143/143 PASS（6 critical wiring suites）+ 25 module-attr smoke 全綠。

**設計選擇**：
1. H state cluster 用 **top-level executable** 模式（無 deps，純 env 驅動），strategy_wiring.py `from .strategy_wiring_h_state import _H_STATE_INVALIDATOR` re-import 保 grep 穩定
2. Scanner cluster 用 **函數 + ScannerWiringResult dataclass** 模式（需 ORCHESTRATOR/KLINE/PAPER_ENGINE/SCOUT_AGENT/MESSAGE_BUS 注入避循環 import），strategy_wiring.py 在原 init 順序位置呼叫並 bind 回 module attribute（`MARKET_SCANNER = _scanner_result.market_scanner` 等）
3. 5-Agent ~440 LOC 塊**故意不抽** — init order 鼓互交織（cognitive_modulator / LOSSES-WIRING lambda / ExecutorConfigCache / 5 audit_callback wires），P2 scope 邊界「strategy_wiring.py only」嚴守

**保 grep 穩定鍵**：
- `app.strategy_wiring.MARKET_SCANNER` / `AUTO_DEPLOYER` 屬性查找不破（strategy_read_routes / strategy_write_routes `from ... import` + h_state_collectors `getattr(_sw, ...)` + tests `sys.modules` patch）
- `app.strategy_wiring._H_STATE_INVALIDATOR` 屬性 sys.modules 反射不破

**保不變量**：W1 cognitive ticking + G8-01-FUP-LOSSES-WIRING lambda（Analyst→Strategist callback）+ ExecutorConfigCache shadow_mode_provider + 5 audit_callback wires + TruthSourceRegistry inject + DEAD-PY-2 paths（PIPELINE_BRIDGE=None / Auto-observation no-op pass / DEMO_CONNECTOR=None）。

**CLAUDE.md §九 同步**：`_H_STATE_INVALIDATOR` row 467 wire site updated `strategy_wiring.py:535` → `strategy_wiring_h_state.py` + re-import 註；新增 `MARKET_SCANNER / AUTO_DEPLOYER / _SCOUT_WORKER` row 顯式登記（前為「12+」隱含覆蓋）。Wave E cost_edge_advisor_boot row 補登先例延續。

**教訓**：sibling-by-function-call 與 sibling-by-top-level-import 兩種 pattern 視 dependency 取捨 — 純 env/讀文件 leaf 用 top-level、需注入 singleton 用函數。Wave E + main_scanner_init + 本次 strategy_wiring split 三個案例累積形成 Python 端 sibling 拆分標準作業：1) leaf cluster 優先 2) caller surface (sys.modules / getattr / from-import) 全盤點 3) singleton bind-back 維持屬性 grep 4) §九 row 同步避 drift。

詳：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-28--strategy_wiring_split.md`

## MAIN-RS-PRE-EXISTING-CLEANUP P2（2026-04-28）

**結論**：main.rs 1210 → **1158 LOC**（§九 1200 hard cap 進入合規），新 sibling `main_scanner_init.rs`（170 LOC）抽出 Scanner D4 pre-init（config + registry + edge estimates + relay channel + tokio relay task spawn）。Pure refactor 0 production behavior change，cargo build 綠 + lib 2308/0 + cost_edge_advisor 11/0 + 2/0。Wave E `cost_edge_advisor_boot` split 後遺留的 governance ambiguity（E2 PB1 MED-1）解除。

**設計選擇**：5 候選中選 Scanner pre-init（67 LOC、最自包含、避開 cost_edge_advisor_boot scope）。Sibling 命名 `main_scanner_init.rs` 對齊既定 main_* sibling pattern（boot_tasks / pipelines / fanout / ws / watchdog / shutdown / instruments）。

**保留 grep stability**：`scanner_store` / `symbol_registry` / `scanner_edge_estimates` / `scanner_ws_tx` / `current_ws_client_tx` 五原變數名透過 destructure pattern 維持，下游 5 個 site 零改動。

**教訓**：`pub(crate) struct + pub(crate) fn` sibling pattern 對 main.rs 1200 cap 維護優於把工作擠回既有 sibling — Wave E 用 cost_edge_advisor_boot 已做對的事，本 P2 同 pattern 完成第二個 sibling。下次小改若再撞 cap，相同 pattern 可重複套（main_phase4_init / main_db_init 等候選仍在）。

詳：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-28--main_rs_pre_existing_cleanup.md`

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

---

## 2026-04-24 PA TODO 完整提案盤點完成

### 關鍵工作

執行**完整的 PA 10 份歷史報告盤點 + 當前 TODO.md + FIX-PLAN 對比分析**，產出：

**輸出**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-24--todo_complete_proposal.md`（333 行）

### 核心發現

1. **未入當前 TODO 的潛在遺漏項**：~5-8 條
   - DI-UNIFY-01：governance_routes DI 模式統一（High/Mid 級）
   - STARTUP-VERIFY-01：依賴完整性 fail-closed check（High 級）
   - PIPELINE-TIMING-WINDOW-01：注入時間窗口防衛（Mid 級）
   - COST-GATE-NEW-01：cost_gate.py 實裝（Mid 級）
   - 5 個 RFC + 文檔 spec（Etc 級）

2. **完整提案表**：~80 條 TODO items
   - High（架構/安全/合規）：19 項
   - Mid（技術債/可讀性）：28 項
   - Low（文檔/QoL）：15 項
   - Etc（RFC/規範）：10 項
   - Backlog：~8 項

3. **架構債分類**（PA 視角）
   - 架構債：7 項（Path A/B、DI、ExecutorAgent toggle、risk_manager 拆分、MessageBus 路徑、startup check、timing window）
   - 功能債：8 項（TruthRegistry 注入/持久化、BacktestEngine 數據、MessageBus 路徑、detail=str、FIX-26、PostOnly、auto-revoke）
   - 參數債：5 項（scheduler、PostOnly、hard_cap、shadow_enabled、FUP-IPC）
   - 文檔債：6 項（CLAUDE.md 同步、Guard retrofit、healthcheck、model canary playbook 等）

4. **3 大 Leverage Points**（確認強化）
   1. FUP-SHADOW-ENABLED-IPC（1d，Phase 2 無 rebuild）
   2. ExecutorAgent ConfigStore + IPC toggle（3-4d，原則 #11 完整）
   3. event_consumer fn 拆分（3-4d，8 檔 refactor 解阻）

5. **當前 TODO.md 對比**
   - ✅ Wave 1-4 + G1-G6 + P0/P1/P2/P3/P4 主軸已覆蓋
   - ✅ healthcheck + 被動等待規則已納入
   - 🆕 新增強調項：DI 統一、startup verify、文檔 RFC 清單明確化

### 方法論

PA 10 份報告盤點流程（可重複使用）：
1. 逐份讀取歷史報告，提取架構發現 + 技術債 + 遺漏項
2. 對比當前 TODO.md + FIX-PLAN，去重+分優先級
3. 按「架構級 vs 功能級」、「High/Mid/Low/Etc」分類
4. 提出新增遺漏項 + 強化 Leverage points + 關鍵決策點
5. 輸出完整提案表（含工時、前置、並行）

### 下次行動

- 【提案交付】：本報告給 PM 審核 + 後續整合核實會
- 【Memory 同步】：記錄新遺漏項 + 10 份報告盤點方法論
- 【Wave 1 啟動】：G1-01~05 + G2-01~05 + G6-01~04 的實施時序確認

---

## 2026-04-26 Wave 3 派發前架構研究

### 觸發

PM 啟動 Wave 3（W20-W23 · 5/22→6/12）派發規劃，要求 4 問題答覆：G8-01 RFC / G8-02 parity 設計 / G8-04 DAG 線性化 ROI / 撞檔風險矩陣。

### 報告路徑

`docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--wave3_dispatch_research.md`

### 3 大關鍵發現

1. **G8-01 範圍 scope drift 風險**：PM profile.md 提及「認知自適應三模組」，但代碼層只 CognitiveModulator（193 LOC）存在，OpportunityTracker / DreamEngine **代碼不存在**（grep 0 命中）。建議完成標準從「80+ coverage」改為「**CognitiveModulator ≥85% line cov + 注入點 integration 綠**」，後二者標 deferred。**派發前必說明**避免 E1 撞 NotImplementedError。

2. **G8-02 decision points 縮窄**：scope 應限 RiskConfig.executor 三欄（shadow_mode / per_symbol_position_cap / max_position_pct），不含 cost_gate / 5-gate auth / Reconciler 降級 / Hurst regime（屬其他 Config 子切片）。建議 70 case golden + replay 混合，case-level binary agree ≥95%（70 中 ≥67）。

3. **G8-04 ROI 太低**：1955 LOC healthcheck 平鋪可讀；隱性依賴只 2 層深 [1] → ratio group；無假 PASS 事件觸發。**降級 backlog**，待真 pain 出現再啟，**Wave 3 完成標準應移除**。

### 撞檔風險矩陣

| 項目 | Isolation | 衝突風險 |
|---|---|---|
| G2-06 bb_breakout calibrate | **必 isolation** | 與 G7-03-Phase-B-FUP-grid（grid 5 檔 WIP）潛在撞區 |
| G8-01 認知 e2e | 主樹 | 純新測試檔，禁改 strategist_agent production |
| G8-02 parity | 主樹 | 純新測試檔，0 Rust diff |
| G8-04 DAG | n/a | 降級 backlog |

### W20 派發建議

第一批並行：**G8-01 + G8-02 主樹同步**（E4 + QA / E2 review / 1-3d）。G2-06 等 healthcheck [12] FAIL ≥7d 才啟（**isolation**）。Wave 3 isolation worktree ≤2 不會撞 §35-39 上限。

### 沒做的事（E1/E2 領域）

- 沒設計實作代碼 / cargo test / pytest
- 沒審查現有 commit
- 純架構決策建議

### 報告索引追加

| 日期 | 報告類型 | 文件位置 |
|------|---------|---------|
| 2026-04-26 | Wave 3 派發前架構研究 | workspace/reports/2026-04-26--wave3_dispatch_research.md |

---

## 2026-04-26 G2-06 bb_breakout disposal RFC

### 觸發

PM Wave 3 第二波派發 G2-06：bb_breakout 7d entries=0（healthcheck [12] FAIL）+ FIX-26-DEADLOCK-1 已 3 次 rebuild 排除 deadlock 嫌疑後，根因 = 1m bandwidth mis-scale CONFIRMED。需二選一決策：disable 永久（C） vs 升 5m + recalibrate（B）。

### 報告路徑

`workspace/reports/2026-04-26--g2_06_bb_breakout_disposal_rfc.md`

### 核心發現

1. **架構級檢查**：5m WS 訂閱 + KlineManager 5m buffer **已就緒**（`multi_interval_topics::DEFAULT_INTERVALS` 含 Min5、`klines.rs:31 DEFAULT_TIMEFRAMES` 含 5m）— 升 5m 不需動 WS 層
2. **真正 5m 改動瓶頸**：`step_1_2_klines_indicators.rs:62` (黑天鵝 1m) + `step_3_signals.rs:108` (`signal_engine.evaluate(sym, "1m", ...)` 寫死) + `on_tick_helpers.rs:299 const TIMEFRAME` + `bb_breakout/mod.rs` squeeze_expiry 換算 — 5 檔 Rust 改動，bit-identical 保證消失
3. **disable 路徑成熟**：`registry.rs:160 set_active(p.bb_breakout.active)` 已是冷啟路徑，TOML flip + rebuild 即生效；無 Rust 代碼改動
4. **sweep 工具 5m bug**：line 686 `horizons_bars = forward_mins if args.timeframe == "1m" else forward_mins` buggy（5m 下需 `[m // 5 for m in forward_mins]`），改造工時 ~1d
5. **量化推薦 C**：B ROI 不利（10d wall-clock 對單策略，擠 EDGE-P3/P1b/Wave 3 主軸），且 F2「signals ≠ edge」對 5m 同樣可能成立（未驗證機制假設），C 是無 regret 路徑（5/03 後仍可改選 B）

### 推薦結論

**選項 C（永久 disable）** — dominated strategy 分析：C 上行小下行也小 vs B 上行大下行也大（且 B 上行有條件機率，C 下行有反悔機制）。架構決策原則「fail-closed + 可逆優先」推 C。

### 沒做的事（E1/E2 領域）

- 沒寫 Rust per-strategy timeframe 接線代碼
- 沒跑 1m vs 5m sweep（資料密集，由 E1 + MIT 接管）
- 沒派 E1 sub-agent（等 PM 拍板 C 後派 4 子任務並行）

### 教訓備忘

- bb_breakout 6 個月內若再啟 → 必先驗 5m sweep 結構級結論（不能再硬調 1m bw）
- F2「signals ≠ edge」是反 replication crisis 紅旗，未來任何「找到能觸發的 bw」提案先問「fee-net forward return 也正嗎」
- §6 自動轉 C 條件（healthcheck [19] cron）為未來「passive 觀察 + 自動兜底」模板，可複用至其他策略 viability 評估

### 報告索引追加

| 日期 | 報告類型 | 文件位置 |
|------|---------|---------|
| 2026-04-26 | G2-06 bb_breakout disposal RFC（推 C disable）| workspace/reports/2026-04-26--g2_06_bb_breakout_disposal_rfc.md |

---

## 2026-04-26 Wave 3 第三波 — 3 C 級 RFC 補 spec

### 觸發

PM 第三波派發指令：FA Wave 3 spec readiness audit 評 EDGE-P1b / EDGE-P2-flip / G2-03 三項為 C 級（核心 spec 缺）。E1 不能開工至 RFC 補完。串行寫 3 RFC。

### 報告路徑

- `workspace/reports/2026-04-26--edge_p1b_7dim_bind_rfc.md`
- `workspace/reports/2026-04-26--edge_p2_flip_sop_rfc.md`
- `workspace/reports/2026-04-26--g2_03_option_b_rfc.md`

### 3 RFC 核心結論（每個 1-2 句）

1. **EDGE-P1b 7 維 bind**：7 維 confirm `est_net_bps / peak_pnl_pct / atr_pct / giveback_atr_norm / time_since_peak_ms / price_roc_short / entry_age_secs`（dim 6 ROC 此 bind 不消費，留 v3）；bind 路徑**不擴 ExitConfig schema**，改現有 5 字段（min_net_floor / min_peak_atr / giveback_base/floor / stale_peak_ms / min_hold_secs）為 percentile-derived；calibrator cron + manual approve（per memory `feedback_env_config_independence` 自動 IPC 寫風控值風險高）；per-strategy stratification + rolling 14d + 7d embargo + ≥200 rows/strategy；ETA ~5/10。

2. **EDGE-P2-flip SOP**：flip 範圍是 **Combine Layer** `RiskConfig.exit.shadow_enabled`（**不是** ExecutorAgent shadow_mode，後者是 G3-02/G3-03）；acceptance = healthcheck [15] 24h agreement ≥95% + per-strategy 分層 ≥95%；推 IPC patch 直接 flip（非灰度，因 Combine 不影響真實決策）+ manual revert SOP（90s 內）；P1-10 並行 = passive 觀察 maker fee（不阻塞）；與 EX-04 / SM-02 物理隔離。

3. **G2-03 Option B**：採 **B2 候選**（擴 `RiskConfig.per_strategy.StrategyOverride` 加 4 個 SL/TP override 字段），非 strategy params 也非 Strategy trait hook；3 道 enforce（validate / runtime cap / calibrator dry-run）守 P1 硬頂；G2-02 counterfactual → G2-03 binding **必 manual approve**（QC §Q2 預期 alpha 結構問題，自動 binding 會掩蓋根本問題）；G2-03 強制依賴 G2-02 完成；per-regime override 留 G2-03-FUP。

### 派發架構建議（給 PM 第三波）

| RFC | E1 子任務 | E1 instance | isolation | 工時 |
|---|---|---|---|---|
| EDGE-P1b | T1 calibrator + T2 summary + T3 IPC restore + T4 healthcheck 升級（4 sub）| Alpha + Beta（並行 2） | 主樹 | 3.5d |
| EDGE-P2-flip | T1 dry-run smoke + T2 healthcheck per-strategy + T3 SOP wrappers（3 sub） | Alpha + Beta（並行 2） | 主樹 | 2.5d |
| G2-03 Option B | T1 schema + T2 risk_checks + T3 TOML + T4 SOP wrapper（4 sub）| Alpha worktree + Beta 主樹 | T1+T2 isolation worktree | 3d |

**啟動順序**：3 RFC schema 部分可並行（T1）；EDGE-P1b + EDGE-P2-flip 可立即派；G2-03 schema 可同步起，但**binding 必等 G2-02 結論**（~5/03+）。

### 關鍵架構發現

1. **MaCrossoverParams 完全無 SL/TP 字段** — 全部走 `RiskConfig.limits` + `RiskConfig.agent`，無 per-strategy 切片；G2-03 是真實 gap（不是 cosmetic）。對比 bb_breakout 已有 trailing_stop_atr_mult 但只控 trailing 距離。
2. **ExitConfig 8 字段 IPC 已通** — `patch_risk_config` deep-merge 直寫 `exit.*` 任意字段（test_g3_05 證明），EDGE-P1b 不需新 IPC method
3. **shadow_enabled 與 shadow_mode 不可混淆** — 兩者分屬 Combine Layer (close-path) vs ExecutorAgent (intent-path)，物理隔離；EDGE-P2-flip 只動前者
4. **G3-03 Phase B 已將 ExecutorAgent `_shadow_mode` 從 hardcoded 改為 IPC provider**（`executor_agent.py:140-181`）— 對齊根原則 #3
5. **per-strategy override 唯一 active 機制是 RiskConfig.per_strategy** — 其他 over-engineering 候選（Strategy trait sl_tp_advice / MaCrossoverParams 內加字段）違反 separation of concerns

### 治理對照亮點

- 3 RFC 全部不觸碰 §四 5 項 live 硬邊界
- §5.7 學習 ≠ 改寫 Live：3 RFC 寫入路徑均經 IPC + manual approve
- §5.4 策略不能繞過風控：G2-03 三道 enforce 確保 override ≤ P1 max
- memory `feedback_risk_changes_scoped`：每個 RFC 範圍精準，不連帶改其他風控

### 沒做的事（E1/E2 領域）

- 沒寫 calibrator 實作代碼（T1）
- 沒寫 risk_checks 接線代碼（T2）
- 沒跑 cargo test / pytest
- 沒 spawn sub-agent（主 agent 串行寫即可）

### 教訓備忘

- **shadow_enabled vs shadow_mode 字面相近但語意完全不同** — 未來任何 RFC 寫此類字段必先註明物理層次與控制平面
- **「per-strategy 定制」3 候選層次** B1/B2/B3 各有 separation of concerns trade-off，B2 (RiskConfig.per_strategy 擴展) 最低架構債（與既有 G3-02 ExecutorConfig 模式對齊）
- **manual approve > 自動 binding** 適用所有 W3 階段風控值寫入（calibrator / counterfactual / shadow flip）— 統一 SOP 模式

### 報告索引追加

| 日期 | 報告類型 | 文件位置 |
|------|---------|---------|
| 2026-04-26 | EDGE-P1b 7 維閾值 bind contract RFC | workspace/reports/2026-04-26--edge_p1b_7dim_bind_rfc.md |
| 2026-04-26 | EDGE-P2-flip shadow→live SOP RFC | workspace/reports/2026-04-26--edge_p2_flip_sop_rfc.md |
| 2026-04-26 | G2-03 ma_crossover SL/TP Option B RFC（推 B2 RiskConfig.per_strategy 擴展）| workspace/reports/2026-04-26--g2_03_option_b_rfc.md |

---

## 2026-04-26 G5-08 strategist_scheduler/mod.rs 拆分計劃

### 觸發

PM 派發 G5-08（P1 Wave 2）：mod.rs 1770 行（§九 1200 hard cap 47% over）。
最近 3 commit（G3-11 CycleCounters + TUNE-TARGET-CONFIG + PERSIST-AUDIT-GAP-COUNTER-1）
累積 ~520 行膨脹回去。已有 sibling persist.rs 446 行（commit 4108849 first-pass 拆完後）。

### 報告路徑

`workspace/reports/2026-04-26--g5_08_strategist_scheduler_split_plan.md`（535 行）

### 推薦結論

**Method A（保守 4-sibling）**：
- mod.rs ~280 行（header + const + StrategistScheduler ctor/getters/builder + 4 mod decl + 4 pub use）
- cycle_counters.rs ~250（CycleCounters atomic 共享單元 + 5 tests）
- validation.rs ~220（pure validate × 2 + 8 tests）
- evaluate.rs ~370（impl: run_forever + evaluate_cycle + 4 helpers + PairMetrics + rank_by_deviation + PairMetricsRow）
- tests.rs ~250（剩餘 13 tests + mk_deps）
- persist.rs 446（不動）

vs Method B（runtime.rs 大塊 + tests.rs 集中 620）— 拒因 tests.rs 接近 800 警告線 + sibling 結構不齊（runtime.rs 用 sibling-child-module，cycle_counters 純 type，pattern 雜）。

### 5 大關鍵架構發現

1. **既有 persist.rs 已是「first-pass 拆」的模型**：commit 4108849 把 mod.rs 從 1342→880，採 `impl StrategistScheduler { pub(super) async fn ... }` sibling-child-module pattern；G5-08 完全沿襲此模板，不創新 pattern
2. **CycleCounters 是 IPC 共享 atomic struct**：ipc_server/mod.rs L103 + L566 + L709 + handlers/misc.rs L210 + main_boot_tasks L170/316 共 5 個外部 callsite，全走 `crate::strategist_scheduler::CycleCounters` path；拆檔 = pub use 維持 path 不動
3. **G5-08 與 G5-FUP-IPC-MOD-SPLIT 完全獨立**：patch_risk_config handler 在 ipc_server/mod.rs 不在本檔；可同時派 2 個 E1（無 isolation 需求）
4. **15 條熱路徑 invariant 全識別**：含 G3-11 cycle_counters Arc + atomic ordering / SCHED-CLOSE-FILTER-1 三條 NOT LIKE filter / FA-1 Demo-only debug_assert / PERSIST-AUDIT-GAP-COUNTER 的 i64 cast bug 規避 / 6 reject reason 字串 / mod.rs 9 條 pub path / run_forever pub async fn 等
5. **31 tests 完整盤點 + 拆分後分布表**：cargo test --release baseline 31 PASS（與 PM 採集相符），分到 cycle_counters 5 / validation 8 / tests 13 / persist 5；任一 sibling test 名變動 = 必打回（healthcheck cron 監控可能讀名）

### 派發架構建議

| 子任務 | E1 instance | isolation | 工時 |
|---|---|---|---|
| G5-08 全 4 step（cycle_counters → validation → evaluate → tests）| 單實例串行 | 主樹 | 2.5-3h |
| G5-FUP-IPC-MOD-SPLIT | 隔壁實例 | 主樹 | ~3-4h（推測）|
| **可並行** | | | |

E2 review 1-1.5h + E4 regression 1.5-2h = 全鏈 5-6.5h。

### 沒做的事（E1/E2 領域）

- 沒寫拆分代碼（4 step 全留 E1）
- 沒實際移動檔案 / 跑 cargo build
- 沒派 sub-agent（純 PA design 主 agent 串行讀+寫）
- 沒擴範圍到 G5-09/10/11/13/FUP-IPC（隔壁 ticket）

### 教訓備忘

- **既有 first-pass 拆過的檔再次膨脹是常態** — persist.rs 拆完後 mod.rs 又被 G3-11 + TUNE-TARGET + PERSIST-AUDIT-GAP-COUNTER 三波加回 ~520 行；§九 拆分需 design 「未來 N 次新功能不撞警告線」的 buffer，A 方案全 sibling <450 留 350+ buffer 是這個考量
- **拆分計劃必含「外部 caller path 全盤點」**：本 design 第一輪寫到 §1.4 才發現 main_boot_tasks 5 個 callsite + ipc_server 4 個 callsite + handlers/misc 1 個 callsite，全走 `pub use` re-export 必須維持；漏一條 = 下游 5 檔同時編譯掛
- **既有 sibling 是最好的 reference 模板** — persist.rs 446 行（doc + use + impl extension + standalone fn + cfg(test) tests）就是教科書級的 sibling-child-module；G5-08 不需要重新發明，evaluate.rs/cycle_counters.rs/validation.rs/tests.rs 都套此模板

### 報告索引追加

| 日期 | 報告類型 | 文件位置 |
|---|---|---|
| 2026-04-26 | G5-08 strategist_scheduler/mod.rs 拆分計劃（推 Method A 保守 4-sibling）| workspace/reports/2026-04-26--g5_08_strategist_scheduler_split_plan.md |

---

## 2026-04-26 G3-08 H1-H5 → Rust IPC Gateway 設計（plan only）

### 觸發

PM 派發 G3-08（Wave 2 P3，TODO.md L223）。前置 G3-03 ExecutorConfigCache（commit `51608fe` 2026-04-25 ✅）。
Layer 2 自主推理 + ExecutorAgent shadow→live 整合需要 Rust hot-path 看到 H1-H5 + 5-Agent state，當前 Python-only ~4552 行隔離。

### 報告路徑

`workspace/reports/2026-04-26--g3_08_h1_h5_ipc_gateway_design.md`（680 行）

### 推薦結論

**Option C 混合模型（cache + invalidation push）** — 鏡射 G3-03 ExecutorConfigCache pattern 但**反向**（Python SSOT，Rust pull）+ 新增 invalidation push 通道。

A push（pure push）/ B pull（pure pull）對比 A IPC 量 5000/min 爆炸 + Python crash 立刻 stale；B 每 hot-path query 1-3ms breach SLA。C 混合：Rust 端 DashMap cache 10s daemon poll + invalidation hint 立刻觸發 ad-hoc poll → hot-path lookup ≤1ms p99 + IPC ~50/min 可控 + Python crash 沿用 last good。

### 5 大關鍵架構發現

1. **G3-03 pattern 反向重用**：G3-08 SSOT 是 Python（H1/H5 stats / Layer2 cost），Rust 端只讀；G3-03 SSOT 是 Rust（RiskConfig.executor），Python 端只讀。**鏡射 cache + poll + fail-closed default 三件套**但流向反 — 命名「鏡射 G3-03」實為反 pattern 反向擴展
2. **DashMap atomic stats 已驗為 Rust hot-path 觀測標配**：commit G3-11 CycleCounters 已示範 5 個外部 callsite + atomic ordering pattern；G3-08 沿用避免 lock-based concurrent struct
3. **Schema 演化用 HashMap<String, i64>** + `#[serde(default)]`：5-Agent stats 不固化 schema（rust struct 一改 Python 必跟，違 G6 漸進可逆），改用 forward-compat dynamic dict
4. **multi-worker uvicorn race 是 Phase 1 接受不一致**：4 worker 各自 STRATEGIST_AGENT singleton 是 worker-local，query_h_state_full 看到隨機某 worker view；Phase 4+ 評估 leader-only flock pattern（沿襲 EDGE-SCHEDULER-LEADER-1 commit `f32629c`）
5. **DEFAULT-OFF env-gate 是大範圍改動的必要保險**：G3-08 ~2180 LOC 若無 phase 切割易堵 Wave 2 主軸；env-gate 確保 wave 2 阻塞時可 unset 立即 zero overhead 不影響其他工作流

### 派發架構建議

| Phase | 子任務 | E1 instance | isolation | 全鏈工時 |
|---|---|---|---|---|
| Phase 1 | A Rust h_state_cache + B Python invalidator + C 接線 | E1-Alpha worktree（A）+ E1-Beta 主樹（B）+ 主 agent 串行（C） | A 必 isolation / B+C 主樹 | 4.5d |
| Phase 2 | H1+H3 接（最高量 query） | E1 主樹 | 主樹 | 3d |
| Phase 3 | H2+H4+H5 接（解阻 G3-09 cost_edge_ratio） | E1 主樹 | 主樹 | 3.5d |
| Phase 4 | 5-Agent state events（解阻 G8-01） | E1 主樹 | 主樹 | 4d |

合計 wall-clock ~13.5d（Phase 1 並行折扣後），LOC ~2180 全鏈。

### Top 3 風險

1. **IPC poll 競態**（10s daemon + invalidation hint 重疊）— 緩解：tokio::sync::watch dedup logic（30s 內 N 次合併為一次 poll）
2. **multi-worker uvicorn 鎖競爭** — Phase 1-3 接受不一致（observability advisory），Phase 4+ 評估 leader-only schema
3. **Schema drift（Python 加新字段 Rust 沒解）** — AgentState 用 HashMap<String, i64> 動態 schema + `#[serde(default)]` 新字段；release notes 記載 14d grace period

### 治理對照亮點

- 16 根原則 #1/#2/#3/#4/#5/#6/#7/#9/#10 全 ✅（純 observability，不繞 lease，fail-closed default + DEFAULT-OFF）
- ★ 直接強化 #13 AI 成本感知（解阻 G3-09 cost_edge_ratio）+ #15 多 Agent 協作（5-Agent → Rust 觀測通道）
- §四 5 項 live 硬邊界全不觸碰（H state 純讀、無 order 路徑、不影響 mainnet gate）

### 沒做的事（E1/E2 領域）

- 沒寫 Rust h_state_cache 任何實作代碼（Phase 1A 全留 E1）
- 沒寫 Python invalidator 實作（spec + prompt template only）
- 沒改 H1-H5 / 5-Agent 業務代碼（Phase 2-4 個別小改）
- 沒跑 cargo test / pytest
- 沒派 sub-agent（純 PA design，主 agent 串行讀+寫）
- 沒擴範圍到 G3-09 cost_edge_ratio 演算法 / G8-01 認知 e2e（隔壁 ticket）

### 教訓備忘

- **「鏡射 G3-03 pattern」命名不嚴謹**：流向相反（Python vs Rust SSOT）但 cache + poll + fail-closed default 三件套通用 — 未來 IPC bridge design 第一句先確定 SSOT 在哪邊
- **Phased rollout + DEFAULT-OFF env-gate** 是大範圍改動（~2000 LOC+）的必要保險：G3-08 4 phase 設計可單獨 rollback、不堵 wave 主軸、unset 立即 zero overhead
- **forward-compat HashMap dynamic schema** 對 observability 字段是 dominated strategy：lock-step Rust+Python deploy 太貴；observability 字段不需強型別保證

### 報告索引追加

| 日期 | 報告類型 | 文件位置 |
|---|---|---|
| 2026-04-26 | G3-08 H1-H5 → Rust IPC Gateway 設計（推 Option C 混合模型，4 phase wall-clock ~13.5d）| workspace/reports/2026-04-26--g3_08_h1_h5_ipc_gateway_design.md |

---

## 2026-04-26 Tier 6 Track 2 — G3-08 H3 schema align A/B/C 決策

- 觸發：E2 Tier 5 batch review T5.3-MED-1（H3 Python 10 keys vs Rust H3RouteStats 7 fields 0/7 對齊；Phase 3 接 real fetcher 前必修，silent regression 隱形地雷）
- 報告：`workspace/reports/2026-04-26--g3_08_h3_schema_align_decision.md`
- Recommend **Option B（Rust rename 對齊 Python + 加 3 缺欄）**：~25 LOC Rust 內部 vs A 的 ~50 LOC Python+test+GUI break vs C 的永久雙詞彙負債；Python 是 SSOT、Rust H3RouteStats 0 hot-path consumer 是黃金時間窗
- 下次 session E1 ready-to-deploy（§7 prompt template + §8 Phase 3 dependency check）
- Phase 3 unblock path：yes（H3 align 完即可派 H2/H4/H5 + RealHStateFetcher + Rust hot-path consumer 一波 ~3.5d）

---

## 2026-04-26 Tier 6 Track 3 — PAPER-STATE-DUST-RESTORE-AUDIT design

推 **Option B**（保持現狀 + 加 healthcheck [19]）— restore_from_db 只還原 counter 不重建倉位；STRKUSDT dust 不來自 restore 是 runtime partial close 殘留；EXIT-FEATURES-FIX A1 fast_track Gate 1 USD floor 已從消費端徹底防 spiral；A 直 evict / C flip owner 對 live user 真實小單有誤刪/誤卡風險（cross-env hard fail）。Healthcheck [19] one-liner SQL：`SELECT COUNT(*) FILTER (WHERE realized_pnl=0) FROM trading.fills WHERE strategy_name LIKE 'risk_close:fast_track%' AND ts > now() - interval '1 hour' AND engine_mode IN ('demo','live','live_demo')` — 0 = PASS / 1-10 = WARN / >10 OR distinct_dust_symbols ≥3 = FAIL。

報告：`workspace/reports/2026-04-26--paper_state_dust_restore_audit.md`

---

## 2026-04-26 Tier 7 Track 3 — G3-08 Phase 3 sub-task split design

推 **Pattern B（per-H 模組整鏈，3 sub-task）** — Pattern A (9 sub-task) 過細空 α / Pattern C (4 sub-task with audit prelude) audit 已併入 RFC §2.3；3-1 H2 + 3-2 H4 並行（不同檔），3-3 H5 串行（同檔 layer2_cost_tracker 避雙修衝突）；ETA 3.5d wall-clock；H4 必補 `validation_pass` counter（Phase 3 前缺，stateless validator 的 stats 由 caller-strategist 維護）；strategist_agent.py 1170+~25=~1195 行接近 §九 1200 硬上限，Phase 4 Strategist sub-task 必先拆檔；Sub-task 3-3 完成 unblock G3-09 cost_edge_ratio + Phase 4 5-Agent 整鏈。報告：`workspace/reports/2026-04-26--g3_08_phase3_subtask_split.md`

---

## 2026-04-26 Tier 8 Track 3 — T7-FUP-DUST-SQL-DEVIATION-DOC RFC §7.4 amend

PM follow-up amend：`2026-04-26--paper_state_dust_restore_audit.md` §7.1 prompt SQL + §7.2 spec SQL 同步 E1 Tier 7 commit `8241133` 落地版本（drop `partial_reduce_real_count` + 加 `FILTER (WHERE realized_pnl = 0)` 到 `COUNT(DISTINCT symbol)`），加雙語 deviation 解釋；新增 §13 Deviation Log 紀錄此 amend 歷史 + slot 編號 [19]→[21] 修正。E2 Tier 7 batch review T7-LOW-1 評為 improvement not regression；Linux production cron 16:09 UTC LIVE PASS 確認。RFC §1-§6 + §8-§12 結論不變。

---

## 2026-04-26 三 P0 fix design（接 STRKUSDT RCA 後 — F3 evict-on-dust / F4 unmatched WS fill drop / F6 edge reload）

### 觸發

PM operator 18:30 派發：af48ee1 涵蓋 STRKUSDT spiral 上游（Gate 1 USD floor + A3 backfill）但 E5 engine.log dive + MIT DB audit 揭發 3 個獨立 P0 bug — F3 phantom dust 殘留 evict-on-dust 缺、F4 trading.fills 7d 0 LIVE rows 但 engine.log 有真 LIVE WS fill、F6 edge_estimator scheduler 寫 hot 但 engine inject boot-only 14h 0 reload。要 read-only 設計（不寫實作碼）。

### 報告路徑

`workspace/reports/2026-04-26--three_p0_fixes_design.md`

### 5 大關鍵架構發現

1. **F4 RCA：trading_writer 無 engine_mode filter**（grep verified `database/trading_writer.rs:259-338` 無條件寫所有 mode）— 真正 drop 點在 **`event_consumer/loop_handlers.rs:555-560` 的 `else { warn!(); }` branch**。LIVE WS fill 全 unmatched（ExecutorAgent shadow_mode hardcoded → 0 SubmitOrder → 0 PendingOrder → 100% unmatched），fallback 路徑 silent return 無 emit `TradingMsg::Fill`。F4 設計：對 unmatched WS fill 落 `unattributed:bybit_auto` audit row（live/live_demo/demo only，paper 不接 WS），同步加 ML pipeline `WHERE strategy_name NOT LIKE 'unattributed:%'` 過濾防污染學習資料。

2. **F6 RCA：PH5-WIRE-1 inject 確認 boot-only**（grep `set_edge_estimates` callsite = bootstrap.rs:586 唯一一處 + intent_processor/mod.rs:480 setter，**無 IPC reload arm**）。`settings/edge_estimates.json` mtime 22:30 28KB scheduler 確實熱寫，但 engine 02:28 boot 後沒 reload 路徑。F6 設計：mirror G3-08 `spawn_h_state_poller_if_enabled` pattern 加 `spawn_edge_estimates_reloader` daemon — 1h periodic + manual IPC `reload_edge_estimates` 雙路徑（advisory pattern 同 PIPELINE-SLOT-1 Phase 3 `trigger_live_auth_recheck`）。3 pipeline (paper/demo/live) 各自 IntentProcessor 需獨立 reload，mode 隔離（paper 讀 `_paper.json`，demo/live 讀 production）必嚴守。

3. **F3 設計：USD-denominated evict-on-dust 4 觸發點 + 不寫 trading.fills**：
   - T1 `reduce_position` 後 / T2 `apply_fill` 反向減倉 / 同向加倉殘餘 / T3 startup boot reaper（在 migrate_legacy_entry_notional 之後）/ T4 status interval 30s 守底 reaper
   - re-use `RiskConfig.limits.ft_dust_qty_floor_usd`（af48ee1 已 land schema），不新增 schema
   - **不寫 trading.fills**（避免污染 ML 學習資料 — `PAPER-STATE-DUST-RESTORE-AUDIT` §4 教訓對齊）；改 `tracing::warn!` 結構化 audit + `pipeline.stats.dust_evictions` counter
   - paper_state 既有 dust_gate.rs（`triage_bybit_sync` + `DUST_FROZEN_STRATEGY`）是 **startup-time triage**，與 F3 runtime evict 互補不衝突

4. **F3-3 與 F4-1 同檔不同 line block**（`event_consumer/loop_handlers.rs` line ~354 status arm vs line 555-560 unmatched else branch）— **必 isolation worktree** 派發避撞。Wave 1 5 個 E1 instance 並行（F3-1/F3-3/F4-1/F6-1/F4-3），3 個必 worktree。

5. **派發 schedule wall-clock**：Wave 1（5 並行 ~2h）+ Wave 2（6 子任務並行 ~2h）+ Wave 3（E2 review + E4 regression 3.5h）= **7.5h 全鏈**。對比串行 23.5h 省 **16h**。

### 推薦結論

3 fix 全 P0 必與 af48ee1 一起 land。F6 是 cost_gate 99.98% reject **真正 root cause**（vs 之前 Phase 5 reframe 假設 strategy gross negative edge）— 部署後 cost_gate reject ratio 應顯著下降，配合 EDGE-DIAG-1 Phase 3 strategy-scoped fallback 雙管齊下。

### 16 原則對照

3 fix 全不觸碰 §四 5 項 live 硬邊界。F4 #6 fail-closed default + #7 ML filter 阻 unattrib 進訓練。F6 #9 災難保護（1h periodic + manual fallback 雙路徑）。F3 #5 生存強化 + #7 evict 不寫 ML 表。

### 沒做的事（E1/E2 領域）

- 沒寫任何實作碼（E1 領域全部留待派發）
- 沒 spawn sub-agent（純 PA design 主 agent 串行讀+寫）
- 沒擴範圍到 ExecutorAgent shadow→live 切換 / ML-TRAINING-DATA-HYGIENE-1 / Reconciler EX-04 對 drift 補正

### 教訓備忘

- **「文件 mtime 新」≠「engine 看到新值」**：F6 RCA 第一波若只看 JSON mtime fresh 會錯判；必驗 engine 內 inject callsite（grep `set_edge_estimates`）。runtime evidence 優於 file system evidence。
- **「writer 沒 silent skip」≠「DB 有 row」**：F4 假設「writer skip live」是 trap；真正 drop 在更上游 `else { warn!(); }` branch。debug fill drop 必順鏈條從 `private_ws emit` → `event_consumer` → `apply_confirmed_fill` → `trading_writer` 全程查，不可只看 last hop。
- **「dust evict via qty threshold」對 funding-accrued residue 無效**：`pos.qty < 1e-12` 對 STRKUSDT 7e-13 生效但對 `qty*price < 1.0 USD` 但 `qty > 1e-12` 的 sub-cent residue 失效。USD-denominated floor 是更穩健 invariant。
- **`spawn_h_state_poller pattern` 是 reusable template**：spawn fn → main.rs spawn call → IPC notification → cancel_token shutdown。F6 reloader 0 創新沿用同 pattern。未來任何 background daemon 先 grep reference 而不是重新發明。
- **多 fix 派發前必 dependency-graph 全攤開**：派發前 `git diff main...HEAD --name-only` 比對所有 fix 主檔，撞區必標 isolation worktree。F3-3 vs F4-1 同檔不同 line block 案例。

### 報告索引追加

| 日期 | 報告類型 | 文件位置 |
|---|---|---|
| 2026-04-26 | 3 P0 fix design（F3 evict-on-dust / F4 unmatched WS fill audit / F6 edge reload daemon）| workspace/reports/2026-04-26--three_p0_fixes_design.md |

---

## 2026-04-26 STRKUSDT dust spiral + Demo silent RCA

### 觸發
PM operator 18:10 報「Demo 引擎自 08:13:59 CEST 0 fills 連續 ~10h，但 watchdog alive=true；07:37→08:13 STRKUSDT 被 risk_close:fast_track_reduce_half 切半 38 次，qty 0.05→7.27e-13，price 全 0.04261」。要 4 問題答覆 + fix design。

### 報告路徑
`workspace/reports/2026-04-26--strkusdt_dust_spiral_rca.md`

### 5 大關鍵發現

1. **Operator 假設「reduce_half 走另一條 path」錯誤** — STRKUSDT 與 BTCUSDT 都走同一條 `step_0_fast_track` ReduceToHalf 分支（trigger_tag = `risk_close:fast_track_reduce_half` 寫死於 step_0_fast_track.rs:454，emit_close_fill + execute_position_close 兩 sink 共用此 tag）。差異是同一 ratio gate 對 STRKUSDT entry_notional=0 fail-open，對 BTCUSDT entry_notional=76.08 正常擋住。
2. **MIT audit + commit `af48ee1` 已 land 完整 cohesive 1+2 RCA fix**（15:48 CEST）但運行 binary mtime 04:29（PID 2033577）**未含此 commit**。Fix 包含 (a) Gate 1 USD floor `ft_dust_qty_floor_usd: 1.0` (b) A3 `migrate_legacy_entry_notional()` defence-in-depth (c) B1 `is_partial_reduce_tag` 跳 EF emit。**部署 = `restart_all.sh --rebuild`** 即 done。
3. **08:13 後 demo silent 不是 STRKUSDT 引起的次生災害** — 假設 A/B/C 全 REJECTED，假設 D 確認：spiral 結束後 BTCUSDT entry_notional 76.08 vs current 9.75 永久 ratio gate 擋（floor 19.02），ma_crossover 沒在發 strategy_close，新開倉 0 entries 是「策略選擇」+ regime 等獨立 question，**不是 engine 故障**。Engine 18:23 仍 print BTCUSDT MICRO-PROFIT-FIX-1 + 04:00/12:00/16:00 三次 funding WS fill = 整路徑 alive。
4. **STRKUSDT entry_notional=0 的具體 path 不可確認** — log 顯示 startup avg_price=0.04261，import_positions line 67 應寫 entry_notional=0.004261，但 ratio gate 0 條 print 證明 entry_notional==0。MIT audit §6.1 已 acknowledge follow-up；不在 PA 範圍但 Gate 1 USD floor 對「path 為何」不依賴（fail-closed 永遠生效）。
5. **paper_state ↔ Bybit drift 對賬 gap** — emit_close_fill 寫 trading.fills 37 條成功 + execute_position_close dispatch 全部被 Bybit min_notional=5.0 reject + dispatch.rs:395 `continue;` 無回滾邏輯。Reconciler EX-04 應 5min 偵測 paper_state qty 0.05→7e-13 vs Bybit 0.1 drift 但實際沒 trigger 降級。F2 follow-up audit。

### 改動風險評級

**部署既有 fix `af48ee1` = 低風險**：
- 純 `--rebuild`，無 schema migration / 無 IPC service breakage / 無 DB write
- 17 new tests 已綠（lib 12 + integration 5）
- Hot-reloadable IPC `patch_risk_config` schema 兼容（new field `ft_dust_qty_floor_usd` 已 serde default + range validate）
- Regression 風險低（real position 名義 ≥5 USD min，1 USD floor 不誤殺）

### 派發架構建議

**已不需派發**（fix 已 in-tree）—— 通知 PM operator 觸發 `restart_all.sh --rebuild`。

但若 PM 仍需 follow-up，3 子任務（**MIT audit §6 acknowledged but not yet done**）：
- F1 (0.5d) STRKUSDT entry_notional=0 path 深查 audit
- F2 (0.5d) Reconciler EX-04 對 spiral 期間 drift 補正 path 驗證
- F3 (0.5d) 加 `[19]` healthcheck dust spiral 偵測（MIT §6.6）

**全 isolation 否**（純 audit + 1 healthcheck check），單 E1 串行 1.5d。

### 16 原則對照

- #6 失敗默認收縮：pre-fix ratio gate 對 entry_notional=0 fail-OPEN **違反**；af48ee1 Gate 1 修正 → 符合
- 其他 15 條無觸碰

### 沒做的事（E1/E2 領域）

- 沒寫 fix patch（已存在於 `af48ee1`）
- 沒派 sub-agent（純 PA RCA + design）
- 沒跑 cargo test（已綠 lib 2210 / 0 failed per E1 report）
- 沒擴範圍到 ML-TRAINING-DATA-HYGIENE-1 P2（隔壁 ticket）

### 教訓備忘

- **Operator 假設「另一條 path」需先驗 grep emit 點** — 本 RCA 一開始就用 grep `risk_close:fast_track_reduce_half` 找到 step_0_fast_track.rs:454+468 single emit 點，立刻證偽假設。任何「不同 strategy_name → 不同 path」假設先 grep 字串 source 而不是相信 reasoning。
- **Binary mtime 是現場第一手證據** — MIT audit + commit + E1 fix report 三邊對齊 fix 已 done 但 `stat openclaw-engine` mtime 04:29 vs commit ts 15:48 證明 binary 未含 fix。runtime 證據優先於 git 證據。
- **「engine silent」不等於「engine broken」** — engine.log tail 18:23 仍持續 print 非 spiral 相關訊息（BTCUSDT MICRO-PROFIT-FIX-1）= alive。「0 fills」可由「無新 strategy 信號」單純解釋，沒必要假設 wedged / 降級 / spiral 鎖死。silent 因果先驗「strategy signal layer 是否 emit」而不是先假設 hot-path lock。
- **fail-OPEN guard pattern 是反 #6 設計** — `if entry_notional > 0.0 { ratio gate } else { pass through }` 是典型反模式：legacy/restored snapshot 的 zero-state 拿到無門檻通行。Fix pattern：Gate 1（絕對 floor）+ Gate 2（相對 ratio）都 active，相對門開不到的場景由絕對門兜底。

### 報告索引追加

| 日期 | 報告類型 | 文件位置 |
|---|---|---|
| 2026-04-26 | STRKUSDT dust spiral + Demo silent RCA + fix 形狀（ack `af48ee1` 已 land 待 deploy）| workspace/reports/2026-04-26--strkusdt_dust_spiral_rca.md |

---

## 2026-04-26 Tier 9 Track 2 — G3-09 cost_edge_ratio design RFC + T8-FUP typo fix

Phase 3 H5 解阻後派發 G3-09 設計 + T8-FUP-RFC-TYPO-FIX 一次合 1 commit。Recommend integration = **新建 cost_edge_advisor 模組**（候選 4 vs intent_processor cost_gate 重疊 / combine_layer 違 Gate-4-only / phys_lock_v2 違 per-position semantic mismatch）。3 Phase rollout: A schema+advisory (4.5d) → B shadow dry-run (1.5d) → C live triggered gate (2.5d) 全鏈 8.5d。CLAUDE.md §二 #13「ratio ≥ 0.8」字面義與公式方向矛盾，採解釋 A 變體 = threshold 為負值（預設 -0.5 保守起點，operator-tunable）。「建議關倉」語意 = Phase C 阻新倉**不**強制關現有倉（fail-soft，避 false-positive 直接虧損）。env-gate `OPENCLAW_COST_EDGE_ADVISOR` + RiskConfig.cost_edge.enabled 雙保險。Phase 4 5-Agent state events 與本 RFC 並行可派（互不阻塞）。報告：`workspace/reports/2026-04-26--g3_09_cost_edge_ratio_design.md`。同 commit T8-FUP typo fix `paper_state_dust_restore_audit.md` §7.2 "improvement not improved spec" → "improvement not regression"（業務內容不變，1 字 amend）。

---

## 2026-04-27 G3-08 Phase 4 5-Agent state events design RFC

### 觸發

PM Tier 8 sign-off `e5f1b2d` next-step：Phase 1+2+3 完成（H1-H5 5-bucket live），Phase 4 = 5-Agent (Strategist/Guardian/Analyst/Executor/Scout) state events 接入 Rust h_state_cache。Strategist sub-task hard pre-condition = G3-08-PHASE-4-STRATEGIST-SPLIT 並行進行中，其他 4 agent 主檔 LOC < 800 無拆檔阻塞。

### 報告路徑

`workspace/reports/2026-04-27--g3_08_phase4_5agent_design_rfc.md`（1415 行）

### 推薦結論

**Pattern B 5 sub-task per-agent**（鏡 Phase 3 Pattern B per-H 模組）：
- 4-1 Strategist (~60 LOC) — hard pre-cond STRATEGIST-SPLIT
- 4-2 Guardian (~35 LOC) — 並行
- 4-3 Analyst (~26 LOC) — 並行（§七 警告）
- 4-4 Executor (~36 LOC) — 並行（shadow_mode wire 注意）
- 4-5 Scout (~27 LOC) — 並行（§九 接近）

ETA 全鏈 **3.75d 並行版**（≤ PA design §11.1 估 4d），順序 5d。

### 5 大關鍵架構發現

1. **query_handler 升級採 Option B 拆兩個 collector**（vs A 同函式擴展 10 參數 / 10-tuple）：`_collect_h_snapshots` Phase 3 簽名不變 + 新增 `_collect_agent_snapshots` 返回 dict 而非 tuple → Phase 5 加 agent 不破壞 caller（forward-compat 模板）

2. **Phase 4 invariant：所有 snapshot 字段必為 int 或 bool→int**（不准 float / string）對齊 Rust `AgentState.stats: HashMap<String, i64>`。Executor `total_slippage_bps` (float)、cognitive/emergency bool / shadow_mode 必 cast int。Phase 5+ 若需 float（如延遲 ms） → 新增 `gauges: HashMap<String, f64>` 兄弟字段不混入 stats

3. **Sub-task 4-4 Executor `_shadow_mode_provider()` call 必在 self._lock 之外**（避 G3-03 ExecutorConfigCache 內部 lock + self._lock 死鎖）+ provider raise 必 fail-closed = 1（shadow on，CLAUDE.md §二 原則 #6）。snapshot vs ConfigStore SSOT 物理層次區分必寫進 docstring（避未來開發者誤改方向破壞 G3-03 契約）

4. **2 條 Backlog FUP 必排**：
   - **G3-08-FUP-ANALYST-SPLIT**：Analyst 主檔 834 LOC（pre-Phase-4 即超 §七 800 警告線），Phase 4 4-3 land 後 ~860；下 wave 拆檔目標 ~480 LOC（鏡 Phase 4 split RFC §6.4 Method A）
   - **G3-08-FUP-MAF-SPLIT**：multi_agent_framework.py 1137 LOC + 27 = ~1164 距 §九 1200 hard cap 僅 36 LOC headroom；下 wave 拆 ScoutAgent (~183 LOC) 出獨立 `scout_agent.py`（建議 P1 優先級避 Phase 5 觸 §九）

5. **healthcheck [20] expected set 漸進式 rollout 是 5 sub-task 並行的關鍵**：每 sub-task 必同 commit 升級 healthcheck（baseline 5 H bucket → Sub-task 4-N land 後 += {對應 agent slot} → 4-5 land 後 expected = 10 bucket）；半途部署 set diff 非空且非全空 → WARN（容忍 missing slot），全空 → PASS。E2 review 必查每 sub-task healthcheck 同步升級

### 派發架構建議（PM Phase 4 wave）

| Sub-task | E1 instance | isolation | 依賴 | ETA |
|---|---|---|---|---|
| 4-1 Strategist | E1-Alpha worktree | YES | STRATEGIST-SPLIT 必先 land | 1d |
| 4-2 Guardian | E1-Beta 主樹 | NO | 4-1 land 後（_collect_agent_snapshots dict skeleton） | 0.75d 並行 |
| 4-3 Analyst | E1-Gamma 主樹 | NO | 同上 | 0.75d 並行 |
| 4-4 Executor | E1-Delta 主樹 | NO | 同上 + G3-03 ConfigStore | 0.75d 並行 |
| 4-5 Scout | E1-Epsilon 主樹 | NO | 同上 | 0.75d 並行 |

**multi-track absorb pattern**（per Phase 3 commit 8cd257e 經驗）：4-1 落主樹 → PM merge → 4-2/3/4/5 同步 fetch → 4 個 E1 並行 worktree → PM 序貫 merge 4 個 commit。`_collect_agent_snapshots` h_state_query_handler.py 共改但每 sub-task 加自己的 `if include_<agent>:` 區塊（互不重疊 dict literal）→ 後 commit `git pull --rebase` 自動合併。

### Top 風險

1. **R1 4 並行 sub-task 同改 h_state_query_handler.py 衝突**（中機率/中影響）→ absorb pattern + per-arm if 區塊隔離
2. **R3 Analyst / multi_agent_framework.py 過 §七 警告線**（高機率/低影響）→ 警告線非 hard cap 不阻塞，Backlog FUP 排下 wave
3. **R4 Executor `_shadow_mode_provider()` 與 self._lock 死鎖**（低機率/高影響）→ 4-4 prompt §高風險警告強制 provider call 在 self._lock 外
4. **R6 strategy_wiring SCOUT_AGENT singleton 名稱**（中機率/中影響）→ 4-5 prompt 前置 grep 步驟強制驗證

### 治理對照亮點

- 16 根原則 #1-#10 全 ✅（純 observability extension）
- ⭐ #13 AI 成本感知：Strategist `ai_evaluations` + Analyst `l2_analyses` 解阻 G3-09 cost_edge_advisor 跨維度判斷
- ⭐⭐ #15 多 Agent 協作：Phase 4 直接強化（5-Agent → Rust 觀測通道全 wired）
- §四 5 項 live 硬邊界全零觸碰
- §九 Singleton table 不需更新（重用 Phase 1C `_H_STATE_INVALIDATOR`）
- §七 文件大小：2 警告（Analyst / multi_agent_framework）→ Backlog FUP

### unblock 下游

- **G8-01 認知自適應 e2e 測試**：Phase 4 4-1 + 4-3 提供 `cognitive_modulator_connected` + `experiment_ledger_connected` Rust fixture 端 ≤1ms p99 即時驗證 wire 接通
- **G3-09 cost_edge_advisor**：Rust hot-path `query_agent_state(cache, "strategist", "ai_evaluations")` + `query_agent_state(cache, "analyst", "l2_analyses")` + `query_h_state(cache, "h5", "cost_edge_ratio")` 三條合判，cost_edge_advisor 規則 = `if cost_edge_ratio >= 0.8 AND ai_evaluations_per_min > 5 AND l2_analyses_per_min > 1: advise(REDUCE_POSITION_SIZING)`
- **未來 GUI 6-pane dashboard**：H1-H5 + 5-Agent 同 IPC pull

### 沒做的事（E1/E2 領域）

- 沒寫 5 sub-task 任何實作代碼（純 design + 5 prompt template）
- 沒派 sub-agent（純 PA 主 agent 串行讀+寫）
- 沒跑 cargo test / pytest
- 沒驗 STRATEGIST-SPLIT 是否已 land（next session PM 派發前驗）
- 沒擴範圍到 G3-09 cost_edge_advisor 演算法 / G8-01 認知 e2e
- 沒實際拆 Analyst / multi_agent_framework.py（屬 Backlog FUP）

### 教訓備忘

1. **Phase 4 比 Phase 3 並行性更高**（5 不同主檔 vs Phase 3 共享 layer2_cost_tracker.py），但仍需 absorb pattern（PM 序貫 merge h_state_query_handler.py 共改）
2. **Phase 4 split RFC 預留 90 LOC headroom 是 plan-ahead 投資**：4-1 用 60 LOC + Phase 5 預留 30 LOC 仍 < 800（per RFC §11.4）。**未來大型 cross-cutting 工作前必先評估各影響檔的 §七/§九 headroom**，提前 split 是最便宜的解法
3. **snapshot vs config cache 物理層次區分**（Sub-task 4-4 Executor 案例）是未來凡 Rust ConfigStore + Python observation 雙資料流共存的標準模式：prompt template 必明確標記方向（read vs write、SSOT vs mirror、cache vs state）
4. **bool→int cast 規則** + **dict-not-tuple collector return value** 兩個 forward-compat 設計原則，Phase 5+ 模板可直接套用
5. **multi_agent_framework.py 1137 LOC 是 Phase 1+2+3 合計擴展副作用**：5 個 agent class 集中一檔的歷史包袱，Phase 4 揭發 §九 距離只剩 36 LOC headroom — ScoutAgent 拆檔（FUP-MAF-SPLIT）優先級提升至 P1
6. **healthcheck expected set 漸進式 rollout** 是 N sub-task 並行的關鍵：每 sub-task 必同 commit 升級，避免半途部署持續 FAIL；rollback 時 expected set 也 reverse

### 報告索引追加

| 日期 | 報告類型 | 文件位置 |
|---|---|---|
| 2026-04-27 | G3-08 Phase 4 5-Agent state events design RFC（推 Pattern B 5 sub-task / ETA 3.75d 並行 / 2 Backlog FUP filed）| workspace/reports/2026-04-27--g3_08_phase4_5agent_design_rfc.md |

---

---

## 2026-04-27 G8-01 認知自適應 e2e RFC

### 核心發現

`CognitiveModulator` (193 LOC) live-wired in `strategy_wiring.py:407-409` 但**邏輯 dead**：
- **BUG-A**：caller `strategist_cognitive.py:160` + `strategist_edge_eval.py:191` 呼 `modulator.get_current_params()`，**該方法不存在**（modulator 只有 `get_all_params`），try/except 靜默吞 → 永遠回 default `(min_confidence, 1.0)`
- **BUG-B**：`modulator.update(...)` production code 0 caller（grep 證），permanent 卡 base value (`confidence_floor=0.60`/`qty_ceiling=1.0`/`update_count=0`)

### 設計決策

不直接派 E4 寫測試（會測 dead code），先派 E1-Alpha W1 production fix：
- FIX-A：rename `get_current_params` → `get_all_params`（2 處）
- FIX-B：`strategist_cognitive.py` 新增 `tick_cognitive_modulator(agent)` helper + `strategist_agent.handle_intel()` 末尾每 N=10 次 tick（Option γ）

W2 unit cov ≥85%（22 case，零 mock）+ W3 integration ≥5 case（7 留 buffer）並行。

### namespace 確認

- `local_model_tools/cognitive_modulator.py` = class (193 LOC)
- `control_api_v1/app/strategist_cognitive.py` = sibling helper (169 LOC, 4 functions, no class)
- 兩者語意分離無 confusion

### ETA

3-3.5d wall-clock（W1 1d → W2/W3 並行 1.5d → E2/E4/QA 1d）

### 報告路徑

`docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-27--g8_01_cognitive_e2e_design.md`

### 教訓（lessons.md candidate）

「test coverage 不等於 live behavior」— G8-01 原 spec「≥85% line cov」若無人發現 BUG-A+B，可能達標但測的全是 dead code。**Coverage RFC 派發前必先 grep call sites + 驗 method-name parity**。屬 `feedback_no_dead_params` 的 corollary。

---

## 2026-04-27 G3-09 Phase B shadow dry-run RFC（cost_edge_advisor 觀察期）

**RFC**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-27--g3_09_phase_b_shadow_dryrun_design.md`

**Phase B 重定義（vs RFC §7.2 原計畫）**：
- RFC §7.2 line 511 寫「IntentProcessor 加 would_reject_intent shadow check」— 違反 Phase B「0 trade impact」原則（即使 pure fn 也改 hot path 形狀且必須 cost_gate 並排 audit）
- 本 Phase B 把「shadow IntentProcessor」整塊移 Phase C，退回純 advisor observability（觀察 advisor 自己的 evaluate cadence + ratio distribution + status transitions）
- 1.5d 工時與工作量匹配後保持

**範圍**（in/out 嚴格切）：
- IN：持久化 evaluate cycle 採樣（V026 hypertable）+ IPC schema 增 4 欄（counter rolling 24h）+ healthcheck [30] 升級從 schema 哨兵 → trigger frequency sanity + observation deliverable
- OUT：IntentProcessor changes / shadow_reject_count / RiskConfig.cost_edge_gate_enabled / per-strategy ratio（屬 Phase C 或 Phase D）

**Phase A FUP 升級**：`G3-09-PHASE-A-DAEMON-INTEGRATION-TEST` 從 P3 升 **P1**，列 Phase B Wave 0 prerequisite — Phase B observation 沒 daemon 整合測試 = 無 ground truth

**避 decision_outcomes 2 bug**：
- `engine_mode` NOT NULL CHECK + INSERT 路徑顯式 bind（避「100% paper」bug）
- 不存 timeframe（Phase B 不依賴 K 線）+ 全欄位 NOT NULL/explicit DEFAULT
- V026 加 Guard A/B（per CLAUDE.md §七 SQL migration 規範）

**Sanity range**（per RFC §2.2）：
- evaluations_24h ≥ 8000 healthy / < 4000 FAIL（10s cycle × 24h × 95% uptime baseline）
- triggers_24h 0-10 healthy / 11-50 WARN noise / >50 FAIL spam
- triggers_per_hour peak ≤ 5 healthy / 6-20 WARN / >20 FAIL
- dead gate detection at 7d：0 trigger + ratio 全離 threshold ≥0.3 → WARN calibrate

**Down-sample 1/min**：daemon 每 10s evaluate 但 INSERT 1/min（24h 1440 row/day），transition row 不 down-sample（保 burst 100% 紀錄）

**新 Rust 程式碼量**：~180 LOC（mod.rs +120 + types.rs +30 + handler +30）+ V026 SQL +120 + Python healthcheck +80 + observation tooling +150 — **不算純 observability tooling**

**派發**：Wave 0 prerequisite (FUP daemon integration test ~2h) → Wave 1 (Rust+SQL+Py 1d) → Wave 2 E2 (0.25d) → Wave 3 E4 (0.25d) → Wave 4 PM Sign-off → Wave 5+6 passive observation → Wave 7 Phase C GO/NO-GO

**E2 必查 3 點**：
1. daemon INSERT 不阻 evaluate cycle（tokio::spawn fire-and-forget）
2. down-sample boundary 1/min 嚴格 + transition 不 down-sample
3. counter rolling 24h 沒 leak（VecDeque pop_front while ts < cutoff）

### 教訓（lessons.md candidate）

「Phase 計畫的 line item 落地時要拆 trade-impact vs observability」— RFC §7.2 把 shadow IntentProcessor 與「觀察 advisor 行為」混在 Phase B 1.5d，落到具體實作才發現前者實質是 Phase C 一半工作量。下次寫 PA RFC §7.x 工時估算前，用「trade impact」 vs 「pure observability」做 binary 切，工時不混算。

---

## 2026-04-28 G3-09-PHASE-B-FUP-STICKY-TS（sticky `triggered_at_ms`）

**RFC / 報告**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-28--g3_09_phase_b_fup_sticky_ts.md`

### 任務性質

E2 Phase A daemon test review (`2026-04-27--g3_09_daemon_test_review.md`) INFO finding 升 P2 prep-gate — `advisor.rs:114-120` 註解聲稱 daemon 會 sticky 覆寫 `triggered_at_ms`，但 `mod.rs` daemon body 0 此邏輯，每 cycle 蓋掉。Phase B Shadow 若 dedup / once-per-trigger 邏輯依賴 sticky 時戳會出 bug，所以列為 Phase B Wave 1 派發前 prep-gate。

主會話授權 PA 三角合一執行（PA design + 自寫 ≤80 LOC Rust + 自寫 ≥2 unit test），不擴 scope。

### 設計決策

選 **A（daemon enforce sticky）** vs B（doc-only 對齊現行非 sticky 行為）：
- A 案 30 LOC daemon 改 + 25 LOC docstring + 175 LOC test = 在 80 LOC 上限內
- 避免 Phase B Wave 1 又要踩雷自己維護 sticky state（重複工作）
- `triggered_at_ms` 命名語意是「進入時間」，非 sticky 行為違反命名
- daemon-local `let mut sticky_triggered_at_ms: i64 = 0;` 0 共享 state、0 race、0 額外 lock
- `evaluate()` 純 fn 簽名/行為/測試全保留 — 32 既存 unit case 不動

### 核心邏輯（mod.rs 4-arm match）

```rust
match (&prev_status, &new_state.status) {
    (Trigger, Trigger) => new_state.triggered_at_ms = sticky_triggered_at_ms,  // sticky preserve
    (_, Trigger)       => sticky_triggered_at_ms = new_state.triggered_at_ms,  // entering: capture now_ms
    (Trigger, _)       => sticky_triggered_at_ms = 0,                          // exit: clear
    _                  => {}                                                   // non-Trigger ↔ non-Trigger
}
```

### 驗收

- cargo build release tests clean
- daemon integration test **6/0 → 8/0**（+2 sticky test）
- lib test **2290 / 0 不變**
- Phase A advisory-only 路徑 0 production behavior change（IPC consumer healthcheck `[30]` schema 哨兵不依賴此欄語意）

### Phase B Wave 1 對接

`triggered_at_ms`（contiguous Trigger 區段進入時戳）與 Phase B RFC `last_trigger_ms`（24h rolling 內最後 Trigger transition）語意正交但不衝突 — Wave 1 可直接讀 `triggered_at_ms` 取「episode 進入時間」，不需自維護 sticky state。Wave 1 工時估 1d 不變。

### 教訓（lessons.md candidate）

「pure fn 表達 stateful semantic 時必有 caller 接 sticky/transition 對手戲」— `evaluate()` 永遠回 `now_ms` 對 first entry 正確，但對 contiguous run 錯。caller (daemon) 必須補 sticky enforcement。如果 doc 與實作其中一邊放鬆，另一邊就成 silent bug 種子。**規則**：pure fn doc 寫「caller 會 X」就必須有 caller 那邊的 enforce + regression test，否則 doc 砍掉等同實作。

### 報告索引追加

| 日期 | 報告類型 | 文件位置 |
|---|---|---|
| 2026-04-28 | G3-09-PHASE-B-FUP-STICKY-TS sticky `triggered_at_ms` 設計+落地+驗收 | workspace/reports/2026-04-28--g3_09_phase_b_fup_sticky_ts.md |

---

## 2026-04-28 — G8-01-FUP-LOSSES-WIRING（P2 prep-gate for W2/W3）

**Topic**：Wire `_stats["consecutive_losses"]` from trade outcome callback so `tick_cognitive_modulator` 真正收到非零輸入；解 RFC `2026-04-27--g8_01_cognitive_e2e_design.md` §3.1 acknowledged limitation。

**模式**：3-合一（PA design + 直派 E1 + sanity test，主會話授權）。Scope 嚴格 bounded — 不碰 W2/W3、regret/dream placeholder、Rust IPC。

### 決策摘要

- **Wiring 模式**：Hybrid Option 1（in-process callback path）
  - Analyst gains `set_strategist_loss_callback(Callable[[float], None])`，於 `analyze_trade` 內 fail-open invoke。
  - Strategist gains `record_trade_outcome(net_pnl)` + `_stats["consecutive_losses"]` + `_stats["trade_outcomes_observed"]`。
  - `strategy_wiring.py` 在 Batch-10 Analyst 重 init 後綁 lambda。
- **Reject Option 2**（新 MessageType）— 擴 ALLOWED_FLOWS 矩陣，無功能優勢。
- **Reject Option 3**（Rust IPC）— 違反 Python-as-SSOT-for-Strategist-stats、touch IPC schema 出 P2 scope。
- **Reject Option 4**（subscribe ROUND_TRIP_COMPLETE）— 現場 0 producer（DEAD-PY-2 後 `pipeline_bridge.py` 已刪），會繼續 dead。
- **Breakeven (net_pnl==0) 視為 loss**：per Principle #5（生存>利潤）+ #13（成本-edge 感知）—— fee-eaten trade 耗資本無 edge，正是 modulator 該調製場景。

### 重要現場發現（archived dead path）

- `MessageType.ROUND_TRIP_COMPLETE` 於 `multi_agent_framework.py:63` 仍定義，AnalystAgent.on_message 仍 dispatch，但 **Python production 0 producer**（`pipeline_bridge._emit_round_trip` 隨 DEAD-PY-2 已刪）；`WIRING_AUDIT_SUMMARY.txt:74`/`L1_01_TRADE_ATTRIBUTION_FIX_SUMMARY.md` 等審計引用全 stale。
- 真實 live trade-outcome 入口 = Rust → IPC `analyst_evaluate(analysis_type="round_trip")` → `AIService._handle_analyst()` (`ai_service_dispatch.py:478`) → `analyst.analyze_trade(record)`。Hook 點選對。

### 數字

- 改動：3 files, +194 LOC business code（analyst +70 / strategist +79 / wiring +45）。
- 測試：1 new file, 8 test cases, ~330 LOC test code。Mac pytest 8/8 + W1 6/6 + 相關套件 157/157 全綠。
- §九 警告：strategist_agent.py 854→933（>800 警告線、<1200 硬上限）— 不本 FUP 拆，留 G3-08 Phase 5 未來處理。

### 教訓（lessons.md candidate）

**「派工前必先 grep『有沒有真實 producer』」**：原 spec 提的 Option 1（Strategist 直接訂 Fill 事件）+ Option 2（Analyst broadcast trade_outcome_processed）若不先 grep `MessageType.ROUND_TRIP_COMPLETE` 的真實 producer，可能設計出「訂閱 dead event 的 PR」浪費一輪 E1 工時。本 FUP 第一步 grep 一次就避開，省下 ~2-3 day rework。應該變成 PA RFC §2 (架構評估) 強制 checklist 一條：「列出 trigger event 的 production producer 與 mtime / 過去 7d 觸發次數」。

---

## 2026-04-28 G8-01-FUP-REGRET-DREAM-WIRING — ESCALATE (concept dead)

### 結論

**不寫碼，escalate 主會話**：`OpportunityTracker` + `DreamEngine` 兩個 producer 已於 2026-04-12 RC-11 Cat A 刪除（~1003 LOC，`docs/archive/2026-04-12--changelog_archive_pre_0408.md:575`）。Production 0 caller / 0 class def / 0 import；只剩 docstring placeholder + Rust roadmap `R02-9 core/dream.rs`（未動工）+ V1.1+R1 SPEC（`docs/references/2026-04-03--agent_cognitive_adaptation_spec_v1_draft.md`，~577 LOC class 設計仍可 reference）。CognitiveModulator `_compute_stoploss_mult` + `direction` 分支結構性不可達；任何 placeholder 都不影響 modulator 行為。

### Wiring 模式選擇

**Path B/C 否決，選 escalate**（per task §3 escalation rule）。3 個推薦 option 留主會話 + operator 判斷：
- **Option A**：刪除 placeholder 參數 + dream branch（~30 LOC，最小 scope）
- **Option B**：依 SPEC 重做 OpportunityTracker + DreamEngine（~600 LOC + tests，3-5d，需新 PA RFC）
- **Option C（PA 推）**：保留接線、加 explicit defer doc + 開 ticket `G8-01-FUP-REGRET-DREAM-DEFERRED P3` 等 R02-9 / 新 wave；零 LOC、honest

### Modulator update() 真實 signature

`update(*, consecutive_losses: int=0, weekly_net_pnl: float=0.0, regret_data: dict|None=None, dream_data: dict|None=None) -> dict`。Schema：`regret_data["net_regret_direction"]` ∈ `{"overtrading","undertrading","balanced"}`；`dream_data["global"]["stoploss_multiplier"]` + `["confidence"]`（>0.6 才生效）。**LOSSES-WIRING 對 update() signature 的假設成立** — `update()` 確實接這 4 個 kwarg，無需改 modulator API。

### 6 個 candidate proxy 全部 fail

(a) H4 missed-opp / (b) Analyst trade outcome / (c) H1 reject log / Scout exploratory / ML registry canary / epsilon-greedy schedule — 6 個 task §2 列舉的潛在源 grep + semantic 比對全 fail：H1 reject ≠ skipped opportunity 虛擬 PnL（spec §3.5 定義）；ML registry 是模型晉升 lifecycle 不是策略 MC 模擬；Scout 無 epsilon-greedy state machine。**任何 fabricated heuristic 都會違反原則 #10 認知誠實 + `feedback_no_dead_params`**。

### 數字

- 改動：0 files, 0 LOC business code（純 escalate 報告）。
- 測試：W1 6/6 + LOSSES 8/8 = 14/14 baseline 全綠（worktree HEAD `e106c5d`）。
- §九 file-size：unchanged。

### 教訓（lessons.md candidate）

**「P2 prep-gate scope 不容忍 fabricated heuristic」**：當 spec'd producer 已被刪、roadmap 未動工，正確回應是 escalate 三選一決策（remove / re-implement / defer），不是「想個 proxy 餵 placeholder」假裝有 wiring。後者是 `feedback_no_dead_params` + 原則 #10 的反模式 — 看似閉環但 `_compute_*` 分支永遠不可達真實 outcome。本 escalation 同模式 LOSSES-WIRING 的「先 grep producer」紀律：**spec docstring ≠ live producer**，`OpportunityTracker.get_regret_summary()` 之類 docstring claim 必須當第一可疑點 grep。

## 2026-04-28 — G3-09 Phase C Intent Gate RFC

- **報告**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-28--g3_09_phase_c_intent_gate_design.md`
- **HEAD**: `decf712`
- **預決策**:
  - Gate 注入點 = Rust IntentProcessor Gate 1.7（在 1.6 negative-balance 後、Guardian 2 前）
  - **Reject 只阻新倉**（is_reducing=true 完全跳過）— 嚴守 CLAUDE.md §二 #5 生存>利潤反向防線
  - 三層 default-off safeguard：env=1 + cost_edge.enabled=true + cost_edge.gate_enabled=true
  - Dedup window 60s 控 V026 INSERT 頻率；reject decision 本身不受 dedup 影響
  - Per-strategy `cost_edge_threshold_override` + `cost_edge_exempt` 給 emergency exit 路徑
  - 重用 Phase B V026 hypertable，`transition_from='GATE_REJECT:<strategy>'` 字面前綴標記
  - **Python ExecutorAgent 0 改動** — 既有 `rejected_reason` 處理 generic
- **拒絕的替代設計**:
  - Alt 1 Python ExecutorAgent 注入 — 漏 Rust 內部 strategy 直發 path（100% intent 必須 Rust 注入）
  - Alt 2 Guardian 內注入 — 違反 SRP + 跨 crate circular dep 風險
  - Alt 3 IPC submit_intent handler 注入 — 漏 tick_pipeline 內部 process path + audit shape 不一致
  - Alt 4 強制關現有倉 — 違反 #5 生存>利潤 + #11 Agent 自主權
- **Wave 拆分**: Wave 1 Rust gate (~2d, 不可並行) → Wave 2 Python metric (~1d, 與 W1 並行) → Wave 3 Linux deploy + 7d observation
- **Top 3 風險**:
  - R-C1 False-positive reject 平倉 — 複用 Gate 2.7 `is_reducing` pattern + unit test 釘死
  - R-C5 Live mainnet 提早啟用 — TOML default false + Phase A RFC §8.3 Operator checklist
  - R-C6 系統凍結 — IPC 60s rollback + healthcheck WARN + per-strategy exempt
- **副作用識別**:
  - V026 重用 `transition_from` field 增 `'GATE_REJECT:<strategy>'` 語意（下游 query LIKE 'GATE_REJECT:%'）
  - RejectionCode enum 新 variant → exhaustive match compiler-enforced E2 catch
  - IntentProcessor 持 `Option<Arc<CostEdgeAdvisor>>` setter pattern 同 risk_config snapshot
- **教訓**:
  - Phase B RFC R-B6 標的「shadow IntentProcessor would_reject」直接整合到 Phase C binding gate，跳過獨立 shadow stage（理由：Phase B observation 已提供等價證據；多 phase 過長 operator UX 差）
  - Gate 注入點選擇強耦合「單一寫入口」原則 — 任何漏 Rust 內部 path 的設計都先排除

---

## 2026-04-28 PA STRATEGIST-SINGLETON-POLLUTION P3 RFC 完成

### 投查結論
- **35 fail in `test_h_state_query_handler.py`** — bisect 確認 polluter 為 `test_api_contract.py:16` `build_client()` 的 `importlib.reload(main_legacy)` + `importlib.reload(main)`
- **Root cause 不是 singleton state pollution**，是 **CPython `from PKG import SUB` attribute precedence**：
  1. test_api_contract reload main → transitive import strategy_wiring → Python 設 `app.__dict__["strategy_wiring"] = <real module>`
  2. test_h_state 的 `_install_fake_strategy_wiring` 只 patch `sys.modules`，未 patch `app.strategy_wiring` attribute
  3. `_collect_h_snapshots()` 內 `from . import strategy_wiring as _sw` 解析到 attribute（真模組），fake bypass
- **Reproducibility**: Python REPL 直驗 attribute precedence 機制；35 fail 在 `pytest control_api_v1/tests/` 100% 重現；Mac/Linux 跨平台一致

### Fix 推薦
- **Option B + A 合**（治本 + defense-in-depth）
  - B (production): `h_state_query_handler.py:334` `from . import strategy_wiring as _sw` → `_sw = sys.modules.get("app.strategy_wiring")`
  - A (test fixture): `_install_fake_strategy_wiring` 同時 patch `app.strategy_wiring` attribute
- 不推 Option C (autouse fixture overkill) / Option D (pytest-forked 新依賴 + CI 開銷)
- ETA: E1 1.5-2h + E2 0.5h

### 教訓
- **「Singleton pollution」命名陷阱**：實際是 module-level import path 污染，與 singleton 物件狀態無關 — 命名引導排錯方向錯誤
- **CPython `from PKG import SUB` 規範**：先讀 `PKG.__dict__["SUB"]` 再落 `sys.modules` → test fixture 必須雙端 patch（W3 fix 已示範但只修一處測試端，未推到 h_state）
- **Bisect 法則**：alphabetical pytest collection + 二分法 30 秒內定位 polluter；future similar issue 可標準化此流程
- **Test fixture audit**：`_install_fake_X` / `_restore_X` helpers 凡 patch `sys.modules[<pkg>.<sub>]` 必同時 patch `<pkg>.<sub>` attribute，否則 `from . import <sub>` 形 import 會繞過

### 報告路徑
📄 `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-28--strategist_singleton_pollution_investigation.md`

---

## 2026-04-28 PA+E1 SINGLETON-SIBLING fix (executor + strategist) 合一完成

### 任務範圍
- 2 ticket：SINGLETON-POLLUTION-EXECUTOR-SHADOW-TOGGLE-API P3 (17 fail) + STRATEGIST-PROMOTE-API P3 (18 fail)
- 主會話授權「PA design + 直接 E1 寫碼 + sanity test」三角合一
- 邊界：嚴禁碰第 3 個 ticket (test_phase2_routes P4 Mac-only)；若 root cause 非 sibling-pollution → escalate

### 結論
- **17→0 + 18→0 = 35 fail 全消** ✅
- **同 sibling-pollution family（同 polluter `test_api_contract::build_client`），但 root cause 與 W3 SINGLETON 不同**：
  - W3：`from PKG import SUB` attribute precedence (h_state_query)
  - 本 wave：**FastAPI `Depends(base.current_actor)` route-build-time freeze callable**，reload main_legacy 後 `current_actor` 變新 fn obj，但 router 內 frozen 仍是舊 → `dependency_overrides` 對不上 → 401
- **Fix = Option A only（test fixture）**：`_make_app` 內 `importlib.reload(executor_routes / strategist_promote_routes)` 重建 router 使 Depends 重新 freeze
- **Option B 不適用**：production code 改 Depends 會破壞 FastAPI introspection — Depends freeze 是設計語意，非 bug
- 0 production code 改動，2 test 檔 +42 -4 line

### 驗證
- 隔離跑：35/35 PASS
- Same-session（含 polluter）：53/53 PASS（test_api_contract 18 + executor 17 + strategist 18）
- 完整 control_api_v1：38 fail → 3 fail（剩 phase2_routes 3 個 out-of-scope per ticket bound）
- W1+W2+W3+SINGLETON regression（h_state + cognitive_integration + api_contract）：116/116 PASS

### 教訓
- **「Sibling-pollution family」不是單一機制** — 同 polluter (importlib.reload) 可觸發**多種**下游模式（attribute precedence、Depends freeze、可能還有更多未發現），future fix 不可預設「同 W3 fix pattern」即可
- **FastAPI Depends + importlib.reload 是已知陷阱**：`Depends(callable)` 在 route 建構期解 callable obj reference，後續 reload 換新 obj 不會傳遞給 frozen Depends
- **Test fixture pattern 必備**：任何 `_make_app(...)` style helper 凡 `app.dependency_overrides[base.X]`，若 sibling 可能 reload base，必先 reload route module 重建 router
- **PA+E1 合一適用情境**：root cause 簡單 + 改動 isolated test 端 + 已有 W3 fix 範本 — 跳過獨立 E1 派發省時，但**仍要驗 baseline 與規劃 fix option 對齊**才動手

### Follow-up（主會話）
- Commit + push 兩 test 檔 + 本報告
- Linux ssh trade-core 端再驗 53 PASS
- 補 memory `feedback_fastapi_depends_reload_freeze.md`（跨 session 偏好）

### 報告路徑
📄 `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-28--singleton_sibling_fix_executor_promote.md`

---

## 2026-04-28 G3-08-FUP-ANALYST-SPLIT P2 — analyst_agent.py 拆分

### 背景
Wave A LOSSES-WIRING (`aced662`) 加 +70 LOC 至 `analyst_agent.py` (874→944)，超過 §九 800 警告線。

### 設計
2 sibling 抽出（鏡 Strategist split / cost_edge_advisor_boot 範式）：
- `analyst_records.py`（142 LOC）：純 dataclass — `TradeRecord` / `PatternInsight` / `AnalystConfig`
- `analyst_pattern_claims.py`（264 LOC）：純函式 helpers — `KNOWN_STRATEGIES` / `extract_strategy_from_pattern` / `register_pattern_claims` / `record_pattern_observations`

### 結果
- `analyst_agent.py`：**944 → 781 LOC**（-17.3%，達 ≤800 首選目標）
- 0 production behavior change
- BWD-compat 4 機制：re-export + class-level alias + staticmethod delegator + instance method delegator
- LOSSES-WIRING callback 接線完整保留（Wave A `aced662` 不破）
- Mac pytest：spec 主測試 22/22 + 擴展回歸 146/146 + 廣度 166/166 全綠

### 教訓
- **Pattern claim helpers 完全 stateless**：原 instance method 看似緊耦 self，實際只讀 `len(self._records)` snapshot + 注入物件 → 可完全提為 module-level free fn，傳 keyword args 即可。Strategist split 已驗範式，此次 100% 重複利用。
- **Class-level frozenset 屬性**：移為 module-level `KNOWN_STRATEGIES` 常量 + class-level `_KNOWN_STRATEGIES = KNOWN_STRATEGIES` 別名，identity check `is` 通過，零 BWD 破壞。
- **Dataclass re-export 用 `__all__`**：明示 `from app.analyst_agent import TradeRecord` 等 import path 是 public API，未來若再拆分務必保此 re-export。

### 報告路徑
📄 `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-28--g3_08_fup_analyst_split.md`

## 2026-04-28 G3-08-FUP-HSQ-SPLIT P2 — h_state_query_handler.py sibling extraction

### 觸發
Wave E SINGLETON fix（commit `b579dae`）+33 LOC dual `sys.modules.get` pattern → handler 826→**859 LOC** 觸 CLAUDE.md §九 800 LOC 警告線。E2 SINGLETON review LOW-1 升 ticket。

### 抽法（PA + E1 + sanity test 三角合一）
新 sibling `app/h_state_collectors.py` 547 LOC（per E2 推薦 + cost_edge_advisor_boot.py split pattern）；handler 859 → **452 LOC**（首選 ≤800 47% under）。

抽 4 函式：`_collect_h_snapshots` / `_collect_agent_snapshots` / `_safe_snapshot` / `_safe_snapshot_self`（+ Wave E `sys.modules.get` 完整 28 行雙語 rationale 原子搬移）。
保留：`build_h_state_full_response` envelope + schema 常數 + `_is_gateway_enabled` env-gate + 完整 MODULE_NOTE。

### Re-export 策略（delegator）
handler 頂部 `from .h_state_collectors import _collect_agent_snapshots, _collect_h_snapshots, _safe_snapshot, _safe_snapshot_self  # noqa: F401`。所有既有 `from app.h_state_query_handler import _safe_snapshot[_self] / _collect_agent_snapshots`（test_h_state_query_handler.py 共 ~50+ patch sites）零修改透明工作。

### 驗證鏈
- `test_h_state_query_handler.py` alone: **90/90 PASS**
- `test_api_contract.py + test_h_state_query_handler.py` same-session: **108/108 PASS**（critical SINGLETON fix integrity — `_install_fake_strategy_wiring` dual patch 機制不破）
- W1+W2+W3 + Strategist 8 檔 regression: **234/234 PASS** 零退化

### 關鍵教訓
- **SINGLETON `sys.modules.get` 字串 literal**：`"app.strategy_wiring"` 這行字串是 fixture-vs-real-module 區分的唯一 anchor，移檔時 1 個 char drift 就會導致 35 個測試讀到 real STRATEGIST_AGENT (zero stats) 而非 fake；新 sibling 內 collector 兩函式各 1 處共 2 字串 literal 必須與原檔字字相符。
- **`noqa: F401` 註記不可省**：handler re-export 4 個 underscore-prefixed symbol 是給下游 test patch site 用，非自身使用；Python style checker 預設會誤報 unused，加 noqa 防 CI 紅。
- **CLAUDE.md §九 800/1200 雙閾值的 sibling extract pattern**：本次第 N 度驗證 — handler 從 859 切到 452 + sibling 547 是「兩半都遠低於 800」的乾淨例；若再加 H6 / 第 6 agent 自然在 sibling 內擴張、handler 仍維持 ≤500。下下次若 sibling 自身觸 800 → 按 H-buckets vs 5-Agent 二度拆。

### 報告路徑
📄 `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-28--g3_08_fup_hsq_split.md`

---

## 2026-04-28 PA+E1 G3-09-DAEMON-TEST-SPLIT P3 合一完成

### 任務範圍
- 拆 `test_cost_edge_advisor_daemon.rs` 1159 LOC > §九 800 警告線
- 三角合一：PA design + E1 寫碼 + sanity test
- 邊界：嚴格 test file split only，0 production code 改

### 結論（5+3+3=11 切分）
- **proofs.rs (534 LOC, 5 tests)**：Proof 1, 2, 3a, 4, 5 — daemon 核心活性 + cadence + cancel
- **dual_safeguard.rs (380 LOC, 3 tests)**：Proof 3b + sticky #1 + sticky #2 — RiskConfig 短路 + 時戳語意
- **spawn_decision.rs (485 LOC, 3 tests)**：FUP Case A/B/C — wrapper-decision parity
- 全 ≤ 800 LOC ✓ · Total 11/0 不變 · lib 2308/0（spec 寫 2299，sibling +9）· persistence 2/0 不變
- 共用 helper 採 **inline 重複** vs `tests/common/mod.rs` — 3 個小 helper × 3 檔 = 120 LOC overhead 可接受

### 教訓
- **Cargo `tests/*.rs` 獨立 binary env race 邊界**：跨 binary process 間 env 不共享，**`OnceLock<Mutex<()>>` 各檔自持是安全的**（無需共用 mutex instance）。糾正任務 spec 中「同 mutex instance 防 race」隱含假設 — 對單 binary 內 parallel test 為真，跨 binary 無意義
- **Test split module-level docstring 必須改寫**：新檔明確標 wave 中位置 + 互相 cross-reference 其他兩檔，避免 future maintainer 不知為何被拆
- **Inline helper 重複 vs tests/common/**：3 個小 helper × 3 檔 = 120 LOC overhead 可接受時 inline 比 Cargo subdir trick 簡單。閾值大概 5+ 檔或 helper > 200 LOC 才值得抽 common module
- **Lib test count drift 不是 regression**：spec 2299 vs actual 2308 — sibling session 在 spec 寫好後加 +9 lib test。判 regression 看 `0 failed` 而非 count number
- **PA+E1 合一適用情境**：純 test split + 0 production diff + 規格邏輯極清晰 — 跳過獨立 E1 派發省時，PA 自寫 Cargo binary 隔離分析 + 直接落地

### 報告路徑
📄 `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-28--g3_09_daemon_test_split.md`

---

## 2026-04-28 — G3-08-FUP-STRATEGIST-DELEGATOR-SLIM P3

### 任務
- 主會話派 PA+E1 合一執行 strategist_agent.py 933 LOC > §九 800 警告線瘦身
- 三角合一：PA design + 直接 lift body + 自寫 sanity test，worktree pattern 不 commit

### 結論（782 LOC，達 ≤800 首選）
- **strategist_agent.py 933 → 782**（-151 / -16.2%）
- 25 method delegator 壓 1-line（16 sibling + 4 H1/H4 + 4 cognitive + record_trade_outcome）
- 2 method body lift：`_produce_intents` (~80 LOC) → strategist_edge_eval.py / `record_trade_outcome` (~55 LOC) → strategist_cognitive.py
- E2 4-1 NIT-1 LOW 附帶：`_handle_intel` 5 early-return 補 `_invalidate_h_state_async` hint
- pytest spec 6 檔 98/98 ✅ / 廣度 251/251 ✅ / 0 production behavior change

### 關鍵技術發現：sibling stub 模式不能完全 lift class method
- **Spec 原建議**「sibling fn + module-level re-export」**對 method-level test patch 失敗**
- 22 處 test 用 `agent.method = MagicMock(wraps=agent.method)` — 純 module re-export 不創建 class attr → instance lookup `AttributeError`
- **正解**：class-level `def` 必留作 1-line delegator；瘦身靠「壓縮 def 形式」+「搬大 body」雙軌
- 範例 anti-pattern：直接 `from .x import _evaluate_edge` 後刪 class method → `agent._evaluate_edge` 取不到 callable wraps

### 教訓
- **Test patch 模式 `MagicMock(wraps=agent.method)` 是 BWD-compat 硬性 contract**：判斷 spec 「lift to module-level」是否可行，必先 grep `agent\.<method>\s*=\s*MagicMock` / `wraps=agent\.<method>`，命中即必保 class-level def
- **`# noqa: E704` 1-line def 是 LOC slim 合法工具**：E5 既有規範允許薄 delegator 此用法（pycodestyle E704 = statement on same line as def），標 noqa 比拆兩行省一半 LOC，header 區段 docstring 解釋意圖即可
- **Body lift 選 sibling 看 producer/consumer 凝聚度**：`_produce_intents` 依 `evaluation` → 進 strategist_edge_eval（與 producer 同檔）；`record_trade_outcome` 寫 `consecutive_losses` → 進 strategist_cognitive（與 consumer `tick_cognitive_modulator` 同檔）。**不要照「方法名前綴」分類，看資料流向**
- **Early-return hint 補完是純診斷利好**：env=0 時 0 負擔；env=1 時讓 Rust h_state cache 對「intel_received++ 但被拒絕」事件保鮮，避免 `intel_received` 動了 stats stale 的誤導。E2 NIT 級 LOW 推薦本 wave 一起做 ROI 高
- **PA+E1 合一適用情境再驗證**：worktree pattern + 純 refactor + 規格清晰 + 既有 sibling 已存在（不需設計新 sibling 結構）— 跳過獨立 E1 派發省時。本 ticket 是 Phase 4 後的「再瘦身」，技術風險已被前 wave 探明

### 報告路徑
📄 `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-28--g3_08_fup_strategist_delegator_slim.md`

---

## 2026-04-29 STRATEGY-NAME-ATTRIBUTION-CLEANUP design

### 觸發
PM operator 報告 GUI Learning tab 24h fills 顯示 demo bucket 25 個 distinct `strategy_name`、live_demo 9 個。實測 PG 確認 cardinality 來自 Rust dispatch 把 funding rate / basis / TRAILING peak / current pct / 6 浮點 trace 拼進 strategy_name（vs 設計上 enum-like 5 strategy）。

### 報告路徑
`workspace/reports/2026-04-29--strategy_name_attribution_cleanup_design.md` + `docs/CCAgentWorkSpace/Operator/2026-04-29--strategy_name_attribution_cleanup_design.md`

### 推薦結論
**Option A（schema migration + new column `exit_reason`）** — 16 emit point 規範 + V033 ADD COLUMN nullable + healthcheck [38] cardinality drift。**估 ~430 LOC / 15h 全鏈 / 4 sub-task isolation pattern**。

### 5 大關鍵架構發現

1. **動態 format!() emit 共 7 點**：funding_arb_exit (6 浮點) + risk_checks 5 條（HARD/DYNAMIC/TRAILING/TIME/TAKE PROFIT）+ halt_session 系列。其餘 9 個 close emit 是 static enum-like（fast_track / phys_lock / ipc_close）。grid_trading / bb_reversion / ma_crossover exit 已是 static 字串。
2. **真實破壞點是 strategist_history.effect**：`WHERE strategy_name = %s` 等值匹配對 close fill 永遠不命中 → 7d edge effect endpoint 從 day 1 就錯（讀 entry 0 元 realized_pnl，不是 close real PnL）。
3. **realized_edge_stats 已 immune**：FIFO pair entry/exit 時 exit 用 prefix detect (`strategy_name.startswith("strategy_close")`) 但**結果 strategy_name 取自 entry 端**，所以 dynamic suffix 不污染輸出。**這是 reusable pattern**。
4. **V031 mlde_edge_training_rows view 已 normalize**：CASE WHEN 把 raw_strategy_name → 5 enum；但 base table 是 trading.intents 不是 trading.fills（intents 寫入 strategy_name 是 entry-only enum）。所以 ML pipeline 自然不被 fills cardinality 影響；GUI passthrough 才暴露。
5. **trading.fills.details JSONB 欄位 V003 早已建但 trading_writer 不寫**：方案 B 走 JSONB 路理論上 0 schema cost，但 GIN index + JSON schema 維護成本超過新 column；本 audit 推 A 不推 B。

### 5 大次要技術發現

- 16 emit 點全集中 `tick_pipeline/on_tick/`、`risk_checks.rs`、`strategies/funding_arb.rs`、`tick_pipeline/commands.rs`、`event_consumer/unattributed_emit.rs`，跨檔但有焦點
- TradingMsg::Fill 加欄位是 compile-time enforced（destructure callsite ~5 處），漏一處 = compile fail，**比 JSONB 安全**
- healthcheck `LIKE 'risk_close:phys_lock_%'` 等 prefix-based 對 fix 後新 row 仍工作（phys_lock / fast_track 是 static prefix），只有 6 個 LIKE 需升級雙語法
- 7d 老 row 自然 phase out — 不需 backfill，rollback 完美
- E1 派發架構：W1-T1（schema + Rust enum，必 isolation）+ W1-T2（16 emit point，必 isolation）+ W1-T3（Python adapt，主樹）+ W1-T4（healthcheck upgrade，主樹）

### 16 原則對照

- ⭐ #8 交易可解釋：直接強化（enum + structured trace 比 dynamic format 易 audit）
- #1 / #3 / #4 / #5 / #6 全 ✅ 0 觸碰
- §四 5 項 live 硬邊界全保（authorization v2 / mainnet env / live_reserved 全不動）
- §七 V033 Guard A/B 強制（template 從 V021 複製，pre-existing pattern 已熟）

### 派發 schedule

| 子任務 | E1 instance | isolation | 依賴 | ETA |
|---|---|---|---|---|
| W1-T1 Rust schema + TradingMsg::Fill | E1-Alpha | YES | 無 | 8h |
| W1-T2 16 emit point 改寫 | E1-Beta | YES | T1 結束 schema 後可重疊 | 10h |
| W1-T3 Python adaptation | E1-Gamma | NO 主樹 | T1+T2 後 | 3h |
| W1-T4 healthcheck upgrade | E1-Delta | NO 主樹 | T1+T2 後（與 T3 並） | 3h |

Wall-clock：~10h parallel + E2/E4 ~5h = **~15h 全鏈**

### 沒做的事（E1/E2 領域）

- 沒寫 V033 migration（純 PA design + audit）
- 沒寫 Rust / Python 業務代碼
- 沒派 sub-agent（純 PA 主 agent 串行讀+寫）
- 沒跑 cargo test / pytest
- 沒擴範圍到 historical backfill（P3 backlog）/ V032 mlde_param_applications schema / G2-01 fee monitoring

### 教訓備忘

- **「動態 trace 拼進 enum 欄位」是反模式**：strategy_name 是 aggregation key（enum dim），funding_arb_exit / TRAILING STOP 動態 reason 是 free-text payload（trace dim）。混淆兩者破壞下游 GROUP BY / equality match / cardinality 衛生 — 屬 `feedback_no_dead_params` 的同族反模式。
- **Cardinality healthcheck 應該成為標配**：對任何「列 enum 的 column」（strategy_name / risk_verdict / exit_source / engine_mode），cron 6h 跑一次 `COUNT(DISTINCT)` = 1 SQL 即可釘死「字面值規範」這條 invisible contract，比逐個 emit 點 grep 強。
- **realized_edge_stats 的 entry-strategy 取法是 reusable pattern**：對「需要 exit prefix detect 但結果歸 entry strategy」的場景，**FIFO pair → 從 entry queue 取 strategy_name** 是 immune to suffix dynamics 的最優設計；未來相關場景優先套此 pattern。
- **view-layer normalize（V031）是好的補丁但不是根因解**：適合「writer 不能改」場景；可改 writer 時優先從根 normalize，view 是次選。

### 報告索引追加

| 日期 | 報告類型 | 文件位置 |
|---|---|---|
| 2026-04-29 | strategy_name attribution cleanup design（推 A schema migration + new exit_reason col + healthcheck [38]）| workspace/reports/2026-04-29--strategy_name_attribution_cleanup_design.md |
| 2026-05-01 | Passive observation proactive plan + TODO archive audit（21d 規劃 34 任務 / 5 軸線；補回 9 active backlog；Top 10 派發優先序）| workspace/reports/2026-05-01--passive_observation_proactive_plan.md |

---

## 2026-05-01 · Passive Observation Proactive Plan + TODO 歸檔審計

### 任務背景

Operator 質疑：(a) PM 把 TODO 從 v3 (713 行) → v4 (197 行) 過程砍掉內容是否全為已完成 (b) 21d passive observation (2026-05-01 → 05-22) 沒真正規劃可主動推進的工作。PA 接手做 audit + 主動規劃。

### 結論摘要

- **歸檔內容無誤**（archive `2026-05-01--completed_waves_1_2_3_and_backlog.md` 完整覆蓋已完成 Wave 1-3 + 60+ backlog 項）
- **v4 漏 9 條 active 條目**（operator 6 條 + PA 額外發現 3 條：G7-04 Phase B/C wiring / STRATEGIST-AUTO-PROMOTE / STRK-FUP-HEALTHCHECK-PRE-EXISTING / ORPHAN-ADOPT-1 / IP-DEDUP-1 / G-7 ClaudeTeacher）
- **規劃 34 任務 / 5 軸線**，~28-35 PA/E1 工作日；並行壓縮 21d 內可完成 ~70%
- **最關鍵 3 行動**：(1) LG-2-RFC PA 1.5d (2) STRK-FUP-HEALTHCHECK-PRE-EXISTING design 1d (3) G4-03 Phase B 部署 3d

### 5 軸線拆分

1. **軸線 1 Wave 4 LG-2/3/4/5 PA Design**（PA 7.5d）：必須 P0-3 (~05-15) 之前寫好，否則 outcome A/C 啟動時阻塞 3-5d；即使 outcome B 也作為 dead-code-prevention 學習材料
2. **軸線 2 條件性獨立工作**（~17.5d）：G4-03 Phase B / G7-04 wiring / G8-05 / LEARNING-COCKPIT / STRK-FUP-HEALTHCHECK-PRE-EXISTING / 3 sibling splits / 2 P4 maintenance
3. **軸線 3 Pre-Live 基礎設施**（~7.5d）：Slack alert decision (~05-15) / HTTPS deploy / Dashboard 強化 / 災難恢復演練
4. **軸線 4 P0-3 決策會準備**（~4.5d）：Edge decision protocol / P0-3-01 報告 outline / agent pre-meeting briefs / adversarial review playbook
5. **軸線 5 Documentation/Test/Maintenance**（~4.5d）：live first-day SOP / Wave 4 deploy runbook / E2E live gate tests / 3 maintenance items

### 教訓備忘

- **「passive observation」不等於閒置**：21d 是準備密集期；CLAUDE.md §八 工作流編排 6 條第 1 條「規劃優先 Plan-First」+「規劃要前瞻」明示
- **PM 砍 TODO 容易誤殺 active backlog**：v3 backlog 表中沒打 ~~strikethrough~~ 的條目被同時砍掉；建議下次 TODO refactor 時 PA + PM 並行 audit，PA 從「active backlog 完整性」視角獨立掃過一次
- **依賴關係圖 / 時序表是架構性內容，不該砍**：即使重複也讓接手 agent 一眼看懂 phase；建議精簡保留而非全砍
- **RFC 寫得早 ≠ 浪費**：P0-3 outcome B 風險下 LG-2/3/4/5 RFC 部分作廢，但 (1) 文件結構保留 (2) 重啟時免重做 (3) 從「P0-3 後阻塞 3-5d」對比 7.5d 投入回報率仍正

### 沒做的事（E1/PM 領域）

- 沒寫業務代碼
- 沒直接 edit TODO.md（建議由 operator 審後派 PM 補）
- 沒派 sub-agent（純 PA 主 agent 串行讀寫）
- 沒派發 LG-2/3/4/5 RFC（建議在 operator 審後再派）

---

## 2026-05-02 · Step 2 Cold Audit — codex 4-day window

**Trigger**：CC step-1 cold audit 收 4 個 P1（5 SQL Guard A/B / stale grep test / .coverage / .codex governance）全 closed 後，operator 要 PA + MIT + QC + E3 並行 step 2 不依賴 commit message 自報的深層 audit。

**Window**：2026-04-28 → 2026-05-01，162 commit / 581 file / +64k LOC（22 Co-Authored-By Claude / 139 非 Claude）。

**Verdict**：0 P1 / 1 P2 / 4 P3。**不需要 stabilization wave**，接 PRE-LIVE-3 邊緣觀察軸線。

**Findings**：
- LOC-GOV-1 P2 — `tick_pipeline/commands.rs` 1343 LOC（baseline 1169）+ `scanner/scorer.rs` 1437 LOC（baseline 901）兩處 §九 1200 硬上限違反；都是 audit window 內把已在限內的檔推過界，不適用 pre-existing exception clause
- DRY-1 P3 — commands.rs 行 203/576 `is_legacy_close_tag` 4-line check 完全複製貼上（commit 854cae1 同時引入兩處）；可同 LOC-GOV-1 一起解
- SCANNER-PAPER-CMD-1 P3（pre-existing 不在 window 內惡化）— scanner 用 paper_cmd_tx query 開倉，PAPER-DISABLE-1 後 oneshot 永不 resolve → 2s timeout → 回空集合
- SCRIPT-PROC-1 P3 — `5db4e29` 引入 `/proc/<pid>/cwd` Linux-only 路徑識別，Mac 沒 /proc，違反 §七 ★★ 跨平台
- TEST-WATCHER-SLOT-1 P3 — live_auth_watcher_tests.rs 缺 end-to-end slot 寫入/清空 assertion

**驗證真接線（無 dead code）**：
- LIVE-AUTH-WATCHER slot pattern 全鏈完整：watcher teardown 清 → spawner closure 寫 → fan-out 每 tick read → IPC `live_snapshot()` try_read non-blocking → position_reconciler closure provider 動態讀 → strategist_scheduler `with_promote_cmd_slot` Arc clone
- close_sizing 接所有 close 路徑：commands.rs 3 處 + step_0_fast_track.rs 1 處
- scanner_snapshots 真有 producer：runner.rs:278 emit → trading_writer.rs:1025 collect → flush_scanner_snapshots 寫 PG
- STRATEGY-WIRING-SPLIT 拆分後 strategy_wiring.py:563/657-659 重新 bind module attribute，下游 grep 穩定
- Schema v2 authorization 雙端對齊：Rust + Python signer 都用 `version|tier|...|approved_system_mode|env_allowed_csv` payload
- per_trade_risk_pct 2%→3% 默認改動只動 Rust default，4 個 risk_config TOML 都顯式 override → 零 effective 改變

**架構 posture 整體健康**：
- Rust SSOT 守住（scanner / scorer / market_judgment 全 Rust；Python 純 normalizer + DB enrichment fail-soft）
- 16 根原則全保（live REST close fallback 移除 強化 原則 1；schema v2 + approved_system_mode 強化 原則 6 fail-closed）
- §四 硬邊界全保（live_execution_allowed / max_retries / OPENCLAW_ALLOW_MAINNET / authorization HMAC — 反而再收緊）
- 16 個新測試 / 0 刪測

**PA 經驗教訓**：
- 「不採信 commit message 自報 Verified ...」原則奏效：若採信則 LOC-GOV-1 P2 會錯過（commit message 沒提 LOC 增量）
- batch-a `b46660a` 13.6k LOC mass commit 真有風險點（schema v2 backward-compat），但 Python signer + Rust verifier 雙端同步 + `unsupported_version` fail-closed 是正確設計，運維已透過 renew 完成切換
- pre-existing 問題（SCANNER-PAPER-CMD-1）audit window 沒惡化即不阻塞接後續工作，但要在 ticket 系統登記避免遺忘
- Mac/Linux 跨平台 (CLAUDE.md §七 ★★) 容易在 helper_scripts 違反 — `/proc` / `lsof` / `ps -E` 差異要 platform guard

**派發建議給 PM**：
1. COMMANDS-RS-LOC-SPLIT P2 (解 LOC-GOV-1 + DRY-1) — PA→E1→E2→E4
2. SCANNER-SCORER-LOC-SPLIT P2 — PA+QC→E1→E2→E4
3. SCRIPT-PROC-1 P3 — E1→E2→E4 Mac+Linux smoke
4. TEST-WATCHER-SLOT-1 P3 — E1→E4
5. SCANNER-PAPER-CMD-1 P3 observe-first — MIT 加 7d healthcheck 再排修

**沒做的事（E1/PM 領域）**：沒寫業務代碼；沒直接 edit TODO.md；沒派 sub-agent（純 PA 主 agent 串行 grep）；沒 commit/push（PA 不寫碼不 commit）

**報告**：
- SoT: `/Users/ncyu/Projects/TradeBot/srv/.claude_reports/20260502_134432_pa_step2_audit.md`
- workspace mirror: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-02--step2_cold_audit_4day_window.md`

## 2026-05-02 · LG-5 Live Candidate Eval Contract RFC

Unified MIT-S2-2 (P2) + QC-S2-02 (P2) into single design spec at
`workspace/reports/2026-05-02--lg5_live_candidate_eval_contract_rfc.md`.

Core design:
- Producer (mlde_demo_applier._insert_live_candidate:587-622) adds payload.demo_cost_baseline + demo_realized_window + demo_attribution_chain_ratio sub-keys (no SQL change, JSONB extension)
- Consumer (new GovernanceHub.review_live_candidate) applies R1 cost regime check / R2 distribution-shift haircut / R3 PSR(0)>=0.95 / R4 multiple-testing deflation / R5 cost_edge_ratio bands (0.5/0.8) / R6 hard veto / R-meta attribution chain >=0.50
- Lease TTL bands: 6h default, 2h if R3 borderline, 1h if R5 warn band; auto-revoke triggers tied to [22]/[33]/[40]/[42]
- 24 pending candidates: bulk re-evaluate via lg5_re_evaluate_pending.py one-off script after IMPL-1+2 land

Implementation breakdown (5 sub-tasks):
- LG-5-IMPL-1 producer schema (E1, parallel safe)
- LG-5-IMPL-2 consumer + backfill (E1, blocked on IMPL-1)
- LG-5-IMPL-3 [42] healthcheck (E1, blocked on IMPL-2 audit)
- LG-5-IMPL-4 unit + integration tests (E4, can scaffold parallel after IMPL-1 schema)
- LG-5-IMPL-5 QC retro 7d post-deploy (QC, wall-clock gated)

Side-effect warnings logged for E2:
- governance_hub.py LOC budget (may need sibling file split)
- Lock contention: review_live_candidate must NOT hold _lock during DB reads
- Audit fail-closed mandatory (defer not approve on audit write failure)

Acceptance gate: PM + QC + MIT 三方 sign-off required before LG-5-IMPL-* dispatch.

Open questions logged for QC/MIT cross-review (R1 thresholds / R2 formula form / R3 sample window / R4 deflation method / R-meta interim threshold given MIT-S2-1 84.6% broken / lease TTL default).

Hard boundary check: untouched (live_execution_allowed / max_retries / OPENCLAW_ALLOW_MAINNET / live_reserved / authorization.json all preserved).

Root principle check: 16/16 preserved or strengthened (especially #3/#5/#6/#8/#10/#13).
