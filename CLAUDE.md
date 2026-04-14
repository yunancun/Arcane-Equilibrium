# OpenClaw / Bybit AI Agent 交易系統
# CLAUDE.md — 項目指令文件（核心規則 + 下一步指針）
# 最後更新：2026-04-14

---

## 一、項目定位

長期進化型 AI Agent 自動交易系統。OpenClaw 為中樞、**Bybit 為唯一交易所**（專攻）。

> Agent 自主完成交易決策與執行，對成本與收益有清晰感知，能感知自身狀態，能持續學習，在嚴格風控框架下逐步贏得更高自主權。

人類 Operator 角色：不定時檢查、審閱、矯正、批准關鍵步驟、推動策略演進。

**交易所決策（2026-04-03）：** 早期規劃含 Binance 雙平台，現已明確專攻 Bybit。Binance 僅作為超長期可能方向保留，當前開發、設計、架構決策均不需考慮 Binance 兼容性。

**系統管線：** 市場數據 → H0 本地判斷 → H1-H5 AI 治理 → I Decision Lease → 執行適配層 → 學習/歸因

---

## 二、16 條根原則（DOC-01 項目憲法 §5.1–§5.16，不可違背）

1. **單一寫入口** — 所有訂單/執行動作通過唯一受控入口
2. **讀寫分離** — 研究/GUI/學習：只讀。寫入權限極度受限、可審計、可鎖定
3. **AI 輸出 ≠ 即時命令** — AI → Decision Lease（帶時效、可撤銷）→ 本地復核 → 執行
4. **策略不能繞過風控** — 所有交易意圖必須經 Guardian 審批
5. **生存 > 利潤** — 先判斷「不會螺旋崩潰」，再判斷「能否盈利」
6. **失敗默認收縮** — 不確定時默認保守：不開新倉、降頻率、降風險
7. **學習 ≠ 改寫 Live** — 學習平面與 Live 平面隔離
8. **交易可解釋** — 每筆交易必須可重建：為什麼、何時、風控審批、授權、執行、結果
9. **交易所災難保護** — 本地止損 + 交易所條件單雙重防線
10. **認知誠實** — 所有結論區分事實 / 推斷 / 假設
11. **Agent 最大自主權** — P0/P1 硬邊界內，Agent 完全自主決定：幣種、策略、參數、時機
12. **持續進化** — 系統必須從交易行為中自動學習（當前 demo 階段：Paper 驗證→參數進化，live 自動部署待 Phase 3 放權框架）
13. **AI 資源成本感知** — 每次 AI 調用計費，cost_edge_ratio ≥ 0.8 → 建議關倉
14. **零外部成本可運行** — 基礎運營僅需 L0+L1（Ollama + 免費搜索）
15. **多 Agent 協作** — 5 Agent（Scout/Strategist/Guardian/Analyst/Executor）+ Conductor 編排，正式對象通信
16. **組合級風險意識** — 監控關聯曝險、策略重疊持倉、資金分配合理性

**優先級序：** 帳戶生存 > 風控治理 > 系統健康 > 審計可追溯 > 人類終審 > 真實 Net PnL > 自主能力進化

**實施準則（從根原則衍生，非憲法級但強制遵守）：**
- **認知調製 ≠ 能力限制** — Agent 壓力下更審慎的方式是提高決策門檻，不是關閉能力。虛擬稀缺性（能量/積分/內部貨幣）被明確否決。（衍生自原則 #11，見 `docs/references/2026-04-03--agent_cognitive_adaptation_spec_v1_draft.md`）

---

## 三、當前系統狀態摘要

**ARCH-RC1 1C-4 WRAP COMPLETE** ✅ — Rust ConfigStore 為所有交易/風控/學習/預算參數權威，4 IPC 寫入面 → tick-level hot-reload → 5 engines；Rust `openclaw_engine` 為 paper/demo/live 唯一引擎；Python 風控/紙盤雙退場；Guardian = RiskConfig 純派生視圖。**禁止 restart-to-apply**。

**StrategyAction Enum ✅**（2026-04-09）— 策略出場死鎖修復。策略 `on_tick()` 返回 `Vec<StrategyAction>`（`Open` 走完整治理，`Close` 輕量路徑繞過 Guardian/cost_gate/Kelly/P1）。5 策略改造完畢 + QC/FA 全修（grid 庫存漂移 P1、exchange Kelly P2、audit logging P2）。830 lib tests pass。

**3E-ARCH 三引擎並行架構 ✅**（2026-04-11）— Paper/Demo/Live 三管線真正獨立並行（MEGA-BLOCKER-0 修復：從「primary+alongside」二管線模型升級為三獨立 spawn）。`determine_primary_kind()` 已刪除 → `build_exchange_pipeline()` 按 API key 獨立構建 `ExchangePipelineBindings`。D1 三獨立判斷 + D21 per-engine Private WS + D23 per-engine Reconciler + D17 Live 獨立 OS thread。`Vec<Sender>` 動態扇出。`TradingMode` 徹底刪除 → `PipelineKind` 不可變。Per-engine TOML 配置 + `PerEngineRiskStores` + `StrategyFactory::create_for_engine()`。D6 三級故障收縮 + D15 全局名義值上限。3E-E2 Fix Rounds Phase A-G 完成：10 BLOCKER + 7 MAJOR 全修 → Phase G 9/9 角色 PASS。**留尾修復**：(a) `with_kind()` 補設 `pipeline_kind` 字段（commit `c9d9bc5`，三引擎搶寫同一份 paper_state.json）；(b) Python `RustSnapshotReader` 路由層 — `get_paper_state()` 預設改讀 per-engine `pipeline_snapshot_paper.json`，paper_trading/risk/strategy_read/live_session 路由顯式 `engine="paper"/"live"`（修 paper-tab 顯示 Live 餘額 bug，因 Live 寫 compat 檔）。930 engine lib + 366 core + 29 e2e = 1325 tests passed · +6 Python ipc_state_reader regression。

**Multi-Symbol Position Tracking ✅**（2026-04-11）— 4 策略（MaCrossover/BbReversion/BbBreakout/GridTrading）從單一全局 `position: Option<bool>` 改為 `HashMap<String, bool>` per-symbol 獨立追蹤。GridTrading `new()`/`new_geometric()` 移除硬編碼 symbol + 預填 grid，改為 `template_bounds` 延遲初始化。理論併發上限 4→100（4策略×25symbols），實際受 `open_positions_max`/`max_same_direction` 風控約束。879 lib tests pass。

**G-SR-1 Signal Tightening COMPLETE ✅**（2026-04-13，7 Sessions）— Phase A 信號源收緊 + Phase B Agent 接線 + Phase C stub + PM 驗收。**Phase A**（S1-S4）：A0-a `grid_helpers.rs` 提取；A0-b `confluence.rs` 共享模組（PersistenceTracker + compute_score 4 分量 65 分制 + score_to_qty_pct 平滑插值）；A0-c 3 策略 TOML Params struct 加 confluence 字段 + factory 接線；A1 時間制持續性過濾器（MA/BBR=120s, BBB=60s）；A2 加權匯合評分；A3 Grid 趨勢冷卻（1x-6x）；S3 param_ranges 擴展 + validation；S4 +41 測試；A-E5 性能審查 PASS。**Phase B S5**：B0 `strategist_scheduler.rs`（tokio 5-min cycle + DB metrics + 指數退避 + validate_recommendation）；B1 `ai_service_client.rs`（100ms connect + per-method TTL + newline JSON-RPC）；B1.5 AIServiceListener 啟動接線。**Phase B S6**：B2 `ai_service.py` stub→real（`_handle_strategist` 接入 Ollama param tuning + `_handle_guardian` 接入 Ollama event classification）；B3 Rust `evaluate_cycle()` 增強（current_params + param_ranges 包含在 IPC 負載）；B4 Guardian L1 信息層（high/critical 事件 MessageBus 中繼 Strategist）。**Phase C S7**：C1 `_handle_analyst()` 接入 AnalystAgent.analyze_trade()；C2 `_handle_scout()` 接入 ScoutAgent intel/alerts；conductor_evaluate 仍為 stub（W23+ R-06）。**PM 驗收 6/6 PASS**：PersistenceTracker 3 策略 / Grid 趨勢冷卻 / Confluence 評分 / Strategist 全鏈路 / Guardian L1 / C1-C2 注入。1086 lib + 33 e2e = 1119 tests pass。計劃文件：`docs/references/2026-04-12--g_sr1_signal_tightening_plan_v2.5.md`。

**OC-5 FundingArb Complete ✅**（2026-04-13）— FundingArb `on_tick()` 從 stub 升級為完整實現（~280 行）。數據管線：`index_price: Option<f64>` 加入 PriceEvent → WS tickers `indexPrice` 提取 → `TickPipeline.index_prices` HashMap 緩存 → `TickContext.index_price`。策略邏輯：entry（funding_threshold + edge 計算 + basis 風險 `|perp/index-1|` + H0/cooldown/position guards）→ direction（positive→short, negative→long）→ confidence scaling（capped 0.6）→ RC-04 rejection rollback。Exit on rate flip / basis breach / max hold。22 新測試。TOML: paper/demo `active=true`，live `active=false`。解鎖 G-2。

**Phase 5 PAUSED — strategies broken, not fees + edge data isolation**（2026-04-12 reframe, 04-13 fix）— 兩個 PnL bug 揭露真相：(a) **PNL-FIX-1**（commit `2a422fa`）`on_tick.rs` 5 條 close 路徑誤用 `event.last_price` 跨 symbol 平倉，PnL 被放大 1000-10000×；(b) **PNL-FIX-2**（同日 follow-up）`emit_close_fill` 寫 `fee: 0.0`，所有 risk/strategy/fast_track 平倉根本不收費。乾淨基線後所有活躍策略 gross edge 為負，net 總損 -$2775。**疑似墮落循環（2026-04-13 發現）**：`realized_edge_stats.py` 原先只查 `is_paper=TRUE`（paper+demo 混合），Paper Exploration 模式放行大量負 edge 交易（518 筆 vs Demo 40 筆），這些交易的 fills 反過來成為 JS edge 估計的主要數據源 → shrunk_bps 全部坍塌到 -35.72 → B=1.0 完全池化 → 可能形成 paper 噪音自我強化的負反饋循環。**修復**：edge 數據按 `engine_mode` 隔離 — demo fills → `edge_estimates.json`（production，demo/live cost_gate 使用），paper fills → `edge_estimates_paper.json`（僅供 draft strategy 評估）；已清除被污染的 edge_estimates.json。Phase 5 暫停等策略重做。詳見 `memory/project_phase5_promotion_edge_crisis.md` + `memory/project_edge_data_isolation.md`。

**Rust 市場掃描器 Phase A-D + QC/FA + P2 ✅**（2026-04-09）— ScannerRunner 完整接線 + D2/D3 動態 symbol + C-3 XRP + C-4 pinned cap + M-1 pending_close + adl_alerts + M-2 TOML + M-3 f_ma 閾值 1.5%→0.5% + M-5 edge_bonus +5→+2 + m-1 relay log + m-3 rest_poller Vec<String> + **IPC-SCAN-1 掃描器可觀測性**（get_active_symbols / get_scanner_status）。**系統目標達成度 ~100%**。835 lib tests pass。

**Runtime 狀態**：`Live_Ready` ✅ — 所有前置阻隔已移除。**實際 Live 交易上線條件（唯一）**：`settings/secret_files/bybit/live/{api_key,api_secret}` 配置完畢（OPENCLAW_ALLOW_MAINNET env var 鎖已從 Rust 源碼移除）。execution_authority 在 live session start 時自動授予。**Live 縮倉監控 ✅**：session 啟動後每 5 分鐘輪詢 peak_balance/bybit_sync_balance；回撤 ≥5% → 警告；回撤 ≥15% → 自動撤銷 execution_authority + 平倉 + 凍結 GovernanceHub 授權。

**A2 NewsPipeline Scheduler ✅**（2026-04-10）— 60s 定時排程器接入 main.rs：3 providers（CryptoPanic free + CoinTelegraph RSS + Google News RSS）→ 去重 → severity → DB write → 4-09 三路 fan-out（Guardian/Regime/Learning）。受 `LearningConfig.switches.news_pipeline_enabled` 熱重載 gate 控制。

**DEAD-PY-1 全部完成 ✅**（2026-04-10）— Wave A/B/C 標籤 + WP-ARCH-RC1 舊命名 + whitelist UI 全量移除（tab-governance.html 220 行 + governance.js 19 行）。唯一殘留：test_risk_view_client 1 pre-existing fail。

**DEAD-PY-2 全部完成 ✅**（2026-04-10）— ~4500 行 Python 死代碼清除。Phase A：4 bridge 文件全刪（bridge_core/agents/stats/pipeline_bridge）。Phase B：5 Python 策略類全刪（ma_crossover/bollinger_reversion/funding_rate_arb/grid_trading/bb_breakout）。Phase C：ProtectiveOrderManager 全刪。Phase D：BybitDemoConnector 交易方法全刪（保留 2 個純工具函數）。Phase E：11 死 test 文件刪除 + 10+ 文件外科手術刪 dead class + strategy_wiring.py 瘦身。Python 層**完全無交易邏輯**，僅剩 API 橋接 + GUI 路由 + 輔助工具。872 Rust lib + 2427 Python passed (1 pre-existing fail)。

**LIVE-P0/P1/P2 全部完成 ✅**（2026-04-10）— P0: API key 管理 + tab-live 前置條件動態化 + 儀表板框架（commit c680ffd）。P1: `read_secret_file(slot)` 槽位感知 + `TradingMode::Live` variant + Python live session routes（commit 11283c7）。P2: `PerEngineRiskStores` 3 獨立 ConfigStore + IPC engine 路由 + GUI per-engine tab + Live 二次確認彈窗（commit 006d905）。840 lib tests pass。

**Live GUI Phase 4 完成 ✅**（2026-04-10）— `_EXECUTION_AUTHORITY_OVERRIDE` 記憶體覆蓋（in-memory gate，重啟清空 fail-closed）+ grant/revoke endpoints + `_ipc_command()` 3 bug 修復 + 實盤端點接入 PyO3 BybitClient（真實交易所數據）+ demo 模式 live session start + tab-live.html Grant/Revoke 按鈕 + 儀表板解析 PyO3 snake_case/Bybit camelCase 雙格式。（commit af392c2）

**SEC-05 innerHTML XSS ✅ + WP-F/AH-06 ✅**（2026-04-10）— `safeText()`→`ocEsc()` 委託 + 4 badge/label 函數 fallback 修復 + 逐文件 `ocEsc()` 包裹（app.js / linucb_card / tab-ai）。Risk-tab `_riskFormDirty` 防覆蓋。

**Live GUI Phase 5 完成 ✅**（2026-04-10）— 紫色主題（live_reserved 所有紅色 → #a855f7 / rgba(168,85,247,..)）+ 擴展儀表板（Account Balance 卡片組：equity/available/wallet/margin-used；PnL Overview：unrealized large + realized from cumRealisedPnl + net；持倉表 + Leverage 列；成交記錄折疊區懶加載 `/api/v1/live/fills`）+ Global Mode Gate（`_get_global_mode_state()` + 409 block if not live_reserved）+ auto-stop on mode exit + `oc-chip-live` 紫色 chip。緊急停止保持紅色。（commit c392220）

**Live GUI Phase 6 完成 ✅**（2026-04-10）— Live-Demo 虛擬 API key 槽（`settings_routes.py`：validate via demo server → 寫入 live path，operator 可用 Demo 帳號完整測試 live 路徑，換 key 時零代碼改動）；`tab-settings.html` 3 槽位卡片（Demo / Live-Demo / Live）+ peek 按鈕 + 上下文警示；`GET /api/v1/live/metrics` 新端點；paper_trading_routes `/metrics` 修復（`compute_full_metrics()` 返回完整 trade_metrics / drawdown_metrics / holding_period / sharpe，修復所有欄位顯示 "--"）；`tab-live.html` 新增 Performance Metrics 區塊（10 個指標卡，30s 自動刷新）。Signal Diamond 多引擎數據隔離規劃（共享市場數據 + per-mode intents/fills/positions，5 階段實施）已歸檔至 `docs/references/2026-04-10--signal_diamond_db_todo.md`。（commit 25b5d73）

**Live/Demo GUI 平倉按鈕 + Sidebar 修復 ✅**（2026-04-10）— (1) sidebar `refreshSidebar()` 改用 `/api/v1/live/session/status` 修復 "mode unknown auth: Not_Granted" 顯示；(2) live/demo 持倉表各行加單獨「平倉」按鈕（`POST /api/v1/live/positions/{symbol}/close` via IPC `close_position`；`POST /api/v1/strategy/demo/positions/{symbol}/close` via PyO3 `place_order reduce_only`）；(3) Positions 段落 header 加「全部平倉」按鈕，同時移除 control bar 重複按鈕；(4) paper tab 同步加「全部平倉」按鈕；(5) `_normalize_execution()` Rust→Bybit camelCase 映射。（commits c370cd1 / bfc3cea / 81a0acb）

**SM-1 治理授權統一 ✅**（2026-04-10）— (1) `max_position_usd` 不再硬編碼：`grant_paper_authorization()` 新增 `max_position_usd` 參數，`post_session_reauth` 改 async 從 Rust `RiskConfig.limits.max_order_notional_usdt` 讀取（commit 4815386）；(2) live SM-1 授權完整生命週期：session start / `grant_execution_authority` → SM-1 DRAFT→PENDING→ACTIVE（mode: live），session stop / `revoke_execution_authority` → SM-1 REVOKED；`governance_hub.get_status()` 多授權並存時優先顯示 mode=live；`_revoke_live_governance_auth()` 新增helper。（commit 435e613）2676 Python tests pass。

**Signal Diamond Fix Round ✅**（2026-04-10）— Phase 3+4 審計發現 9 gaps → 全部修復：P0 `set_trading_mode()` 雙向 swap 保存/恢復各模式狀態；P2 `AddMode`/`SwitchMode` IPC command 全鏈路接線；P3 Python IPC 層 mode-aware 參數化 + alias fallback；Phase 3 已知限制記錄（同時多模式需 per-mode Orchestrator，Phase 5+ 工作）。+5 Rust tests。E2 PASS + E4: 850/3/2692 全基線達標。

**Phase 6 Reconciler 自動降級 ✅**（2026-04-10）— 6-RC-1~5,7,8,9,10 完成。Reconciler 從 AUDIT-ONLY 升級為自動動作層：漂移→escalation（收緊風控）→漂移消失→hybrid 恢復（clean cycles + wall-clock）。觸發：MinorDrift 不動作 / MajorDrift·Orphan·Ghost·SideFlip→Cautious / persistent≥3→Defensive / burst≥5→CB+CloseAll / REST fail≥10→Cautious。恢復：逐級，CB/MR operator only。`ReconcilerState` + `evaluate_actions()` + `ReconcilerEscalate/DeEscalate` IPC + `Arc<AtomicU8>` shared risk level。+27 tests。872 engine lib + 365 core pass。6-RC-7 e2e 集成測試 7 場景 pass。6-RC-8 live blocker 解除。排除：6-RC-6（OC-3 阻塞）。

**W20 完成 ✅**（2026-04-10）— SEC-04/06/13 E3 深度審查 PASS · G-9 HMAC 確認（NOT dead，L171 auth token 驗證）· WP-CC/P9 雙軌止損接線（StopRequest→PositionManager.set_trading_stop()）· FS-1 market_data_client tests 提取（1083→742 行）· BI-1 MODULE_NOTE 12 files · SM-1 Singleton 合規 · 6-01~03 漸進放權管線（promotion_pipeline.py + 3 API endpoints + 27 tests）。E2 修復 3 P1（mutable ref / html.escape key / singleton TOCTOU）。879 engine lib + 2787 Python passed。

**W21 6-04~08 Phase 6 驗收 ✅**（2026-04-11）— 6-04 集成測試：reconciler_e2e.rs 新增 7 場景（MinorDrift 不重設/SideFlip/Ghost/冷卻/全局冷卻/多級恢復 Defensive→Normal/REST 漸進三階段）+ 6-05 壓測 Rust 4 場景（100 cycle 快速翻轉/50 symbols 爆發/handler 快速升降/性能 1000 calls <100ms）+ Python 5 場景（10 線程並發 register/promote/metrics/冪等/100 策略批量）+ 6-06 sync_commit 驗證 PASS（global `synchronous_commit=on` V006:90 已保護 orders/fills）+ 6-07~08 EvolutionEngine 保留決策（用於 DL/AI agent 學習，與 PromotionPipeline 分工文檔化）。E2 修復 3 項（Ghost handler 完整鏈路/promote 並發斷言 ==1/temp 文件碰撞）。879 engine lib + 18 e2e + 2792 Python passed。

**E5 Performance Optimization ✅**（2026-04-12）— 23 項全部處理（20 fixed / 2 skipped / 1 deferred）。關鍵：`TickContext<'a>` 零拷貝策略接口 + `push_capped<T>()` 環形緩衝工具（13+ 重複消除）+ PriceEvent 5 typed fields + `tokio::join!` 7 表並行 flush + `ShadowOrderRequest`→`OrderDispatchRequest` 重命名 + `now_ms()`/`is_stale()` 工具函數。17 files, net -336 lines。934+366+27 = 1327 tests pass。

**ORPHAN-ADOPT-1 Phase 1 ✅**（2026-04-14）— Reconciler 對 orphan 倉「偵測但不動作」的行為修復。新增 `position_reconciler/orphan_handler.rs`（~350 行 + 11 unit tests）：`handle_orphan(ctx) -> OrphanDecision` 純函數按 A1→A4→B1→default 順序評估（A1 距強平 < 10% / A2 已 CB / A3 名義 > `max_order_notional_usdt` / A4 不在 active universe / B1 五策略 shrunk_bps 全非正且 unrealised > 0）；所有 Phase 1 decision 走 `PipelineCommand::CloseSymbol` reduce_only，dispatch 失敗回退 drift 讓 Phase 6 升級階梯兜底。`ReconcilerState.pending_orphan_closes` HashMap + 2 分鐘 TTL dedup 防止 spam。`main.rs` `build_orphan_cfg(engine_key)` closure factory 按引擎綁 `PerEngineRiskStores` + `SymbolRegistry` + `EdgeEstimates` Arc。V014 audit event `orphan_handled`。Phase 2（Adopt 真實路徑）等 G-1 R-02 Strategist Agent。1136 engine lib + 366 core + 33 e2e = 1535 Rust pass。

**留尾**（非阻塞）：W1 event_consumer 拆分。governance_routes.py 1172 行（已瘦身至 < 1200 ✅）。D-02 PriceEvent metadata HashMap 移除（待所有 producer 遷移至 structured fields）。

**歷史細節**（不要重複載入）：
- 1A→1C-4 commit 敘事 → `docs/worklogs/2026-04-08--arch_rc1_1c_history_archive.md`
- Phase 0-4 Sprint/Wave → `docs/archive/2026-04-07--claude_md_section3_history_phase0_4.md`
- 逐 commit 行數 → `docs/CLAUDE_CHANGELOG.md`
- 1C-3/1C-4 narrative → `docs/archive/2026-04-08--main_docs_1c3_1c4_narrative.md`

---

## 四、硬邊界（永遠不能違背）

```python
# ── Live_Ready 狀態（2026-04-10 更新）─────────────────────────────
# Live 基礎設施全部實施完畢（LIVE-P0/P1/P2 ✅ + Gov-P1 ✅）。
# 系統行為：完全以 Live 模式運行，前置阻隔已移除。
# 實際 Live 交易上線僅需 operator 提供以下兩個條件：
#   1. OPENCLAW_ALLOW_MAINNET=1   （Rust Mainnet guard，Rust 側硬鎖）
#   2. settings/secret_files/bybit/live/{api_key,api_secret} 配置完畢
#      （trading_mode 引擎配置對應調整）

execution_authority     = "auto_granted_on_start"  # live session start 時自動授予，stop 後重置
decision_lease_emitted  = False
max_retries             = 0

# 永不允許的硬錯誤（不因 Live_Ready 而放寬）：
# - 繞過 Operator 角色認證或 live_reserved global mode 直接啟動 live session
# - 自動修改 engine trading_mode 為 live（需 operator 顯式配置）
# - Bybit API timeout / retCode != 0 → fail-closed，不重試
# - should_call_ai=true 但 invocation 沒發生
# - 偽造 AI 調用或交易活動
# - Live 模式下無 OPENCLAW_ALLOW_MAINNET=1
```

---

## 五、架構總覽

```
[數據與觀察層]           Bybit REST + WS → Postgres + Observer
[H0 本地判斷內核]        freshness / health / eligibility / risk envelope（<1ms SLA）
[GovernanceHub]          SM-01 授權 + SM-04 風控 + SM-02 租約 + EX-04 對賬
[H1-H5 AI 治理層]       thought_gate / budget / model_router / governor / cost_logging
[I Decision Lease]       GovernanceHub.acquire_lease() / release_lease()
[Control API v1]         FastAPI 183 路由
[GUI + Learning]         11-Tab 控制台 + Learning Cockpit + Paper Trading Dashboard
[Rust openclaw_engine]   paper / demo / live 三模式唯一引擎（1C-3-F 後）
                         tick pipeline + IntentProcessor + paper_state + governance + stop_manager
[Layer 2 AI 推理]        L0 確定性 → L1 Ollama → L2 Claude
[風控框架]               P0/P1/P2 三層 + 對抗性止損 + AI 注意力稅
[策略工具包]             KlineManager → IndicatorEngine → SignalEngine → 5 策略 → Orchestrator
[管線橋接]               PipelineBridge: Tick Fan-Out + Intent→Order + 治理 gate
[止損管理器]             StopManager: Hard/Trailing/Time Stop + ATR 動態倉位
```

---

## 六、路徑與啟動

```
GitHub repo:    yunancun/BybitOpenClaw
本地主工作樹:   /home/ncyu/BybitOpenClaw/srv（/home/ncyu/srv ← symlink）
本地-only：     settings/（secrets）  trading_services/（runtime）
```

### 啟動檢查
```bash
git status && git log --oneline -5
```

### ★ 灰度驗證檢查（每次啟動必做，直到 R-07 Go/No-Go 通過）
Rust 引擎灰度驗證正在後台運行。**每次 session 啟動時先跑以下命令確認引擎健康：**
```bash
# 引擎存活？+ canary 記錄數 + 崩潰數 + 最新狀態
python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --stale-threshold 45 --grace-period 120 --status
wc -l /tmp/openclaw/engine_results.jsonl
grep -c "ENGINE_CRASH" /tmp/openclaw/watchdog.log 2>/dev/null || echo "0 crashes"
```
詳細操作指南見 TODO.md 頂部「灰度驗證檢查」段。如引擎掛了按 TODO.md 指引重啟。

### TODO.md 強制規則（每次接手必須遵守）

**接手時：** 必須讀 `TODO.md` 確認當前工作狀態，找第一個 `[ ]` 未完成項作為起點。用戶有明確指令時以用戶為準。

**發現新問題時：** 立即追加到 TODO.md，不等會話結束。

**修復完成後：** `[ ]` → `[x]`，追加完成 commit 號，更新測試基準線。

---

## 七、代碼與文檔規範

### ★★ 跨平台兼容性（強制，所有開發必須遵守）

**大前提：項目必須隨時可以部署在 macOS 上運行。**

1. **路徑不硬編碼** — 所有路徑使用環境變量或 config，禁止硬編碼 `/home/ncyu/`。
   用 `os.environ.get("OPENCLAW_BASE_DIR", ...)` 或 `Path(__file__).parent` 相對路徑。
   E2 必查：grep `/home/ncyu` 新代碼 → 打回。

2. **LocalLLMClient 抽象乾淨** — 不洩漏 Ollama-specific 細節。
   所有 LLM 調用通過 `LocalLLMClient` ABC 接口（Phase 1 任務 1.8）。
   禁止在業務邏輯中直接調用 Ollama HTTP endpoint。

3. **服務部署可遷移** — systemd → launchd 遷移路徑清晰。
   服務配置邏輯寫成文檔或腳本（`helper_scripts/deploy/`）。
   不依賴 systemd-specific 特性（如 `sd_notify`）。

4. **依賴管理乾淨** — `requirements.txt` 保持更新，禁止隱式依賴。
   新增 `import` 時同步更新 requirements。E2 必查。
   避免 Linux-only 依賴（如 `psutil` 的 Linux 特定 API），需要時加平台守衛。

### 雙語注釋（強制）
每個新建/修改的函數、類、模塊必須中英對照注釋（MODULE_NOTE / docstring / inline / fail-closed 路徑 / 安全代碼）。E2 必查。

### 強制同步規則
- **Sprint/Wave 完成**：更新 §三 + §十一 + `docs/CLAUDE_CHANGELOG.md` + README，與生產代碼同 commit
- **Commit 時**：摘要追加到 `docs/CLAUDE_CHANGELOG.md` 頂部，格式 `### 標題（YYYY-MM-DD · commit XXXXXXX）`
- **Context ≥90%**：立即寫 `docs/worklogs/YYYY-MM-DD--session_progress_N.md`（已完成/進行中/未完成/決策/下一步）
- **每日整合**：當天 worklog 碎片合併為 `YYYY-MM-DD--daily_summary.md`，刪碎片
- **新腳本**：MODULE_NOTE 雙語 + latest+dated 輸出 + contract check + 更新 SCRIPT_INDEX.md
- **docs/**：分類目錄 + `YYYY-MM-DD--描述.md` + 更新 `docs/README.md` 索引

---

## 八、16 Agent 角色體系與強制工作鏈

**強制**：所有任務按角色派發，主會話 = PM+Conductor。完整角色定義/激活矩陣見 `docs/CLAUDE_REFERENCE.md`。

**標準鏈**：PM+FA → PA 派發 → E1/E1a 並行 → **E2 代碼審查 → E4 測試回歸**（兩者絕不可跳）→ E5 優化（每 Phase/Wave/≥3 E1 任務強制）→ QA → PM 確認。E3/CC/A3/R4/TW 按需。
**P0 快速通道**：PA → E1 並行（≤5）→ E2 → E4 → PM。

**Bybit API 強制**：所有 Bybit 相關開發（REST/WS/IPC）先查字典手冊 `docs/references/2026-04-04--bybit_api_reference.md`，新增端點同步更新手冊，E2 必查。審計：`docs/audits/2026-04-04--bybit_api_infra_audit.md`。

---

## 九、代碼結構約定

### 文件大小限制
- **800 行** ⚠️ 警告線（E2 必須標記）
- **1200 行** 🛑 硬上限（不允許 merge）

### 模塊依賴方向（禁止循環 import）
```
state_models ← state_compiler ← state_store ← main_legacy ← main.py
其他 route 文件 ← main_legacy（通過 from . import main_legacy as base）
```

### Monkey-patch 安全
被 main.py patch 的函數（compile_state / STORE / envelope_response 等），新模塊必須通過 `main_legacy` 命名空間間接引用，不可直接 import 原始版本。

### Singleton 管理
| Singleton | 創建位置 | 導入方式 |
|-----------|---------|---------|
| `settings` | main_legacy.py | `base.settings` |
| `STORE` | main_legacy.py（main.py 重建） | `base.STORE` |
| `app` | main_legacy.py | `base.app` |
| `limiter` | main_legacy.py | `base.limiter` |
| `_pool` | db_pool.py | `from .db_pool import get_conn` |
| `DEFAULT_LEASE_TTL_CONFIG` | lease_ttl_config.py | `from .lease_ttl_config import DEFAULT_LEASE_TTL_CONFIG` |
| `_backtest_engine` | backtest_routes.py | 內部懶加載 `_get_backtest_engine()` |
| `_scheduler` | evolution_auto_scheduler.py | 內部懶加載 `start_scheduler()` |
| `_evolution_engine` | evolution_routes.py | 內部懶加載 `get_evolution_engine()` |
| `_ledger` | experiment_routes.py | 內部懶加載 `get_experiment_ledger()` |
| `LeaseTTLConfigManager._instance` | lease_ttl_config.py | `LeaseTTLConfigManager.get_instance()` |
| `_RUST_BYBIT_CLIENT` | strategy_ai_routes.py | 內部懶加載 `_get_rust_client()` |
| `KLINE_MANAGER` / `INDICATOR_ENGINE` / `SIGNAL_ENGINE` / `ORCHESTRATOR` 等 12+ | strategy_wiring.py | 模組級全局，import 時初始化 |

新增 singleton 必須在此表登記。禁止子模塊創建未登記的全局可變狀態。

### 其他
- Route Handler 只做 parse → call → format，不含業務邏輯
- 新 Pydantic model 放 `*_models.py` 或所屬模塊，不加入 main_legacy.py

---

## 十、下一步工作指針

**當前焦點（2026-04-10 審計後更新）**：10 個架構 gap 全部入計劃（TODO.md Gap 索引）。
- **W19（04-14~18）**：G-3 IPC 認證 + G-5 Rate Limiting + OC-3 多通道告警 + 6-RC-6 ✅
- **W20（04-21~25）**：SEC-04/06/13 E3 審查 + G-9 HMAC 確認 + WP-CC(FS-1/BI-1/P9/SM-1) + 6-01~03 漸進放權 ✅
- **W21（04-28~05-02）**：6-04~08 ✅ · 6-09~13 Phase 6 PM 驗收 ✅；LG-1 21d paper 到期（05-01）
- **W22（05-05~09）**：G-1 R-02 AI Agent（Strategist/Guardian）+ G-2/OC-5 FundingArb + LG-2/3
- **W23（05-12~16）**：G-1 R-06 全 5 agent + G-7 ClaudeTeacher + G-10 Calibration + LG-4/5 Live

**關鍵路徑**：`~~G-3 → OC-3 → 6-RC-6 → 6-01~13~~ ✅ → LG-1(05-01) → LG-2 → LG-4 → Live`
**最早 Live 日期**：W23 末（～2026-05-16）

**路線圖**：Phase 0-5 ✅ · Live GUI P0~P6 ✅ · **Phase 6 (W19-21) ✅** 自動降級 ✅ · 告警 ✅ · 漸進放權 ✅ · 壓測+驗收 ✅ · PM 端到端 ✅ · **AI 治理層 (W22-W23) ⬜**（H1-H5 AI agent 目前全 stub）。

**Live 前置**：Paper trading ≥21d · ~~G-3 IPC 認證~~ ✅ · ~~G-5 Rate Limiting~~ ✅ · ~~Phase 6 驗收~~ ✅ · provider pricing 綁定。API key 填入即可上線（所有代碼阻隔已移除）。

**關鍵文件指針**（按需 Read，不要全載入）：
- Bybit API 字典/審計：`docs/references/2026-04-04--bybit_api_reference.md` · `docs/audits/2026-04-04--bybit_api_infra_audit.md`
- 融合方案/執行計劃/ML/DB/Rust：`docs/references/2026-04-04--*` · `docs/references/2026-04-03--*` · `docs/rust_migration/README.md`
- 完整參考索引：`docs/CLAUDE_REFERENCE.md`

---

## 十一、一句話狀態

> 截至 2026-04-14：tests engine lib **1136** + core **366** + e2e **33** = **1535** Rust passed **0 fail** · Python **2852** passed · **ORPHAN-ADOPT-1 Phase 1 ✅** · **OC-5 FundingArb COMPLETE ✅** · **G-SR-1 COMPLETE ✅** · **Edge 數據隔離 ✅** · **Phase 5 PAUSED** · **Live_Ready ✅** · **下一步**：G-2 FundingArb 驗證 · LG-1 21d paper 到期（05-01）· Phase 2 Adopt 等 G-1 R-02 Strategist。
