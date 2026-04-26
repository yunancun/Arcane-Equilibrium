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
