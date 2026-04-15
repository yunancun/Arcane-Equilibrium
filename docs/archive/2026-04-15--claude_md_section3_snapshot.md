# CLAUDE.md §三 里程碑歸檔 — 2026-04-09 至 2026-04-14

**歸檔日期**：2026-04-15
**原因**：CLAUDE.md §三 每次 session 自動全量載入，超過 2 天的完成里程碑純歷史，不應佔用 context。按 CLAUDE.md §七 §三 衛生規則（>2 天必歸檔）執行首次大批歸檔。
**涵蓋**：2026-04-09 至 2026-04-14 共 22 條里程碑段落。

---

## ARCH-RC1 1C-4 WRAP COMPLETE ✅

Rust ConfigStore 為所有交易/風控/學習/預算參數權威，4 IPC 寫入面 → tick-level hot-reload → 5 engines；Rust `openclaw_engine` 為 paper/demo/live 唯一引擎；Python 風控/紙盤雙退場；Guardian = RiskConfig 純派生視圖。**禁止 restart-to-apply**。

## StrategyAction Enum ✅（2026-04-09）

策略出場死鎖修復。策略 `on_tick()` 返回 `Vec<StrategyAction>`（`Open` 走完整治理，`Close` 輕量路徑繞過 Guardian/cost_gate/Kelly/P1）。5 策略改造完畢 + QC/FA 全修（grid 庫存漂移 P1、exchange Kelly P2、audit logging P2）。830 lib tests pass。

## 3E-ARCH 三引擎並行架構 ✅（2026-04-11）

Paper/Demo/Live 三管線真正獨立並行（MEGA-BLOCKER-0 修復：從「primary+alongside」二管線模型升級為三獨立 spawn）。`determine_primary_kind()` 已刪除 → `build_exchange_pipeline()` 按 API key 獨立構建 `ExchangePipelineBindings`。D1 三獨立判斷 + D21 per-engine Private WS + D23 per-engine Reconciler + D17 Live 獨立 OS thread。`Vec<Sender>` 動態扇出。`TradingMode` 徹底刪除 → `PipelineKind` 不可變。Per-engine TOML 配置 + `PerEngineRiskStores` + `StrategyFactory::create_for_engine()`。D6 三級故障收縮 + D15 全局名義值上限。3E-E2 Fix Rounds Phase A-G 完成：10 BLOCKER + 7 MAJOR 全修 → Phase G 9/9 角色 PASS。**留尾修復**：(a) `with_kind()` 補設 `pipeline_kind` 字段（commit `c9d9bc5`，三引擎搶寫同一份 paper_state.json）；(b) Python `RustSnapshotReader` 路由層 — `get_paper_state()` 預設改讀 per-engine `pipeline_snapshot_paper.json`，paper_trading/risk/strategy_read/live_session 路由顯式 `engine="paper"/"live"`（修 paper-tab 顯示 Live 餘額 bug，因 Live 寫 compat 檔）。930 engine lib + 366 core + 29 e2e = 1325 tests passed · +6 Python ipc_state_reader regression。

## Multi-Symbol Position Tracking ✅（2026-04-11）

4 策略（MaCrossover/BbReversion/BbBreakout/GridTrading）從單一全局 `position: Option<bool>` 改為 `HashMap<String, bool>` per-symbol 獨立追蹤。GridTrading `new()`/`new_geometric()` 移除硬編碼 symbol + 預填 grid，改為 `template_bounds` 延遲初始化。理論併發上限 4→100（4策略×25symbols），實際受 `open_positions_max`/`max_same_direction` 風控約束。879 lib tests pass。

## G-SR-1 Signal Tightening COMPLETE ✅（2026-04-13，7 Sessions）

Phase A 信號源收緊 + Phase B Agent 接線 + Phase C stub + PM 驗收。**Phase A**（S1-S4）：A0-a `grid_helpers.rs` 提取；A0-b `confluence.rs` 共享模組（PersistenceTracker + compute_score 4 分量 65 分制 + score_to_qty_pct 平滑插值）；A0-c 3 策略 TOML Params struct 加 confluence 字段 + factory 接線；A1 時間制持續性過濾器（MA/BBR=120s, BBB=60s）；A2 加權匯合評分；A3 Grid 趨勢冷卻（1x-6x）；S3 param_ranges 擴展 + validation；S4 +41 測試；A-E5 性能審查 PASS。**Phase B S5**：B0 `strategist_scheduler.rs`（tokio 5-min cycle + DB metrics + 指數退避 + validate_recommendation）；B1 `ai_service_client.rs`（100ms connect + per-method TTL + newline JSON-RPC）；B1.5 AIServiceListener 啟動接線。**Phase B S6**：B2 `ai_service.py` stub→real（`_handle_strategist` 接入 Ollama param tuning + `_handle_guardian` 接入 Ollama event classification）；B3 Rust `evaluate_cycle()` 增強（current_params + param_ranges 包含在 IPC 負載）；B4 Guardian L1 信息層（high/critical 事件 MessageBus 中繼 Strategist）。**Phase C S7**：C1 `_handle_analyst()` 接入 AnalystAgent.analyze_trade()；C2 `_handle_scout()` 接入 ScoutAgent intel/alerts；conductor_evaluate 仍為 stub（W23+ R-06）。**PM 驗收 6/6 PASS**：PersistenceTracker 3 策略 / Grid 趨勢冷卻 / Confluence 評分 / Strategist 全鏈路 / Guardian L1 / C1-C2 注入。1086 lib + 33 e2e = 1119 tests pass。計劃文件：`docs/references/2026-04-12--g_sr1_signal_tightening_plan_v2.5.md`。

## OC-5 FundingArb Complete ✅（2026-04-13）

FundingArb `on_tick()` 從 stub 升級為完整實現（~280 行）。數據管線：`index_price: Option<f64>` 加入 PriceEvent → WS tickers `indexPrice` 提取 → `TickPipeline.index_prices` HashMap 緩存 → `TickContext.index_price`。策略邏輯：entry（funding_threshold + edge 計算 + basis 風險 `|perp/index-1|` + H0/cooldown/position guards）→ direction（positive→short, negative→long）→ confidence scaling（capped 0.6）→ RC-04 rejection rollback。Exit on rate flip / basis breach / max hold。22 新測試。TOML: paper/demo `active=true`，live `active=false`。解鎖 G-2。

## Rust 市場掃描器 Phase A-D + QC/FA + P2 ✅（2026-04-09）

ScannerRunner 完整接線 + D2/D3 動態 symbol + C-3 XRP + C-4 pinned cap + M-1 pending_close + adl_alerts + M-2 TOML + M-3 f_ma 閾值 1.5%→0.5% + M-5 edge_bonus +5→+2 + m-1 relay log + m-3 rest_poller Vec<String> + **IPC-SCAN-1 掃描器可觀測性**（get_active_symbols / get_scanner_status）。**系統目標達成度 ~100%**。835 lib tests pass。

## A2 NewsPipeline Scheduler ✅（2026-04-10）

60s 定時排程器接入 main.rs：3 providers（CryptoPanic free + CoinTelegraph RSS + Google News RSS）→ 去重 → severity → DB write → 4-09 三路 fan-out（Guardian/Regime/Learning）。受 `LearningConfig.switches.news_pipeline_enabled` 熱重載 gate 控制。

## DEAD-PY-1 全部完成 ✅（2026-04-10）

Wave A/B/C 標籤 + WP-ARCH-RC1 舊命名 + whitelist UI 全量移除（tab-governance.html 220 行 + governance.js 19 行）。唯一殘留：test_risk_view_client 1 pre-existing fail。

## DEAD-PY-2 全部完成 ✅（2026-04-10）

~4500 行 Python 死代碼清除。Phase A：4 bridge 文件全刪（bridge_core/agents/stats/pipeline_bridge）。Phase B：5 Python 策略類全刪（ma_crossover/bollinger_reversion/funding_rate_arb/grid_trading/bb_breakout）。Phase C：ProtectiveOrderManager 全刪。Phase D：BybitDemoConnector 交易方法全刪（保留 2 個純工具函數）。Phase E：11 死 test 文件刪除 + 10+ 文件外科手術刪 dead class + strategy_wiring.py 瘦身。Python 層**完全無交易邏輯**，僅剩 API 橋接 + GUI 路由 + 輔助工具。872 Rust lib + 2427 Python passed (1 pre-existing fail)。

## LIVE-P0/P1/P2 全部完成 ✅（2026-04-10）

P0: API key 管理 + tab-live 前置條件動態化 + 儀表板框架（commit c680ffd）。P1: `read_secret_file(slot)` 槽位感知 + `TradingMode::Live` variant + Python live session routes（commit 11283c7）。P2: `PerEngineRiskStores` 3 獨立 ConfigStore + IPC engine 路由 + GUI per-engine tab + Live 二次確認彈窗（commit 006d905）。840 lib tests pass。

## Live GUI Phase 4 完成 ✅（2026-04-10）

`_EXECUTION_AUTHORITY_OVERRIDE` 記憶體覆蓋（in-memory gate，重啟清空 fail-closed）+ grant/revoke endpoints + `_ipc_command()` 3 bug 修復 + 實盤端點接入 PyO3 BybitClient（真實交易所數據）+ demo 模式 live session start + tab-live.html Grant/Revoke 按鈕 + 儀表板解析 PyO3 snake_case/Bybit camelCase 雙格式。（commit af392c2）

## SEC-05 innerHTML XSS ✅ + WP-F/AH-06 ✅（2026-04-10）

`safeText()`→`ocEsc()` 委託 + 4 badge/label 函數 fallback 修復 + 逐文件 `ocEsc()` 包裹（app.js / linucb_card / tab-ai）。Risk-tab `_riskFormDirty` 防覆蓋。

## Live GUI Phase 5 完成 ✅（2026-04-10）

紫色主題（live_reserved 所有紅色 → #a855f7 / rgba(168,85,247,..)）+ 擴展儀表板（Account Balance 卡片組：equity/available/wallet/margin-used；PnL Overview：unrealized large + realized from cumRealisedPnl + net；持倉表 + Leverage 列；成交記錄折疊區懶加載 `/api/v1/live/fills`）+ Global Mode Gate（`_get_global_mode_state()` + 409 block if not live_reserved）+ auto-stop on mode exit + `oc-chip-live` 紫色 chip。緊急停止保持紅色。（commit c392220）

## Live GUI Phase 6 完成 ✅（2026-04-10）

Live-Demo 虛擬 API key 槽（`settings_routes.py`：validate via demo server → 寫入 live path，operator 可用 Demo 帳號完整測試 live 路徑，換 key 時零代碼改動）；`tab-settings.html` 3 槽位卡片（Demo / Live-Demo / Live）+ peek 按鈕 + 上下文警示；`GET /api/v1/live/metrics` 新端點；paper_trading_routes `/metrics` 修復（`compute_full_metrics()` 返回完整 trade_metrics / drawdown_metrics / holding_period / sharpe，修復所有欄位顯示 "--"）；`tab-live.html` 新增 Performance Metrics 區塊（10 個指標卡，30s 自動刷新）。Signal Diamond 多引擎數據隔離規劃（共享市場數據 + per-mode intents/fills/positions，5 階段實施）已歸檔至 `docs/references/2026-04-10--signal_diamond_db_todo.md`。（commit 25b5d73）

## Live/Demo GUI 平倉按鈕 + Sidebar 修復 ✅（2026-04-10）

(1) sidebar `refreshSidebar()` 改用 `/api/v1/live/session/status` 修復 "mode unknown auth: Not_Granted" 顯示；(2) live/demo 持倉表各行加單獨「平倉」按鈕（`POST /api/v1/live/positions/{symbol}/close` via IPC `close_position`；`POST /api/v1/strategy/demo/positions/{symbol}/close` via PyO3 `place_order reduce_only`）；(3) Positions 段落 header 加「全部平倉」按鈕，同時移除 control bar 重複按鈕；(4) paper tab 同步加「全部平倉」按鈕；(5) `_normalize_execution()` Rust→Bybit camelCase 映射。（commits c370cd1 / bfc3cea / 81a0acb）

## SM-1 治理授權統一 ✅（2026-04-10）

(1) `max_position_usd` 不再硬編碼：`grant_paper_authorization()` 新增 `max_position_usd` 參數，`post_session_reauth` 改 async 從 Rust `RiskConfig.limits.max_order_notional_usdt` 讀取（commit 4815386）；(2) live SM-1 授權完整生命週期：session start / `grant_execution_authority` → SM-1 DRAFT→PENDING→ACTIVE（mode: live），session stop / `revoke_execution_authority` → SM-1 REVOKED；`governance_hub.get_status()` 多授權並存時優先顯示 mode=live；`_revoke_live_governance_auth()` 新增helper。（commit 435e613）2676 Python tests pass。

## Signal Diamond Fix Round ✅（2026-04-10）

Phase 3+4 審計發現 9 gaps → 全部修復：P0 `set_trading_mode()` 雙向 swap 保存/恢復各模式狀態；P2 `AddMode`/`SwitchMode` IPC command 全鏈路接線；P3 Python IPC 層 mode-aware 參數化 + alias fallback；Phase 3 已知限制記錄（同時多模式需 per-mode Orchestrator，Phase 5+ 工作）。+5 Rust tests。E2 PASS + E4: 850/3/2692 全基線達標。

## Phase 6 Reconciler 自動降級 ✅（2026-04-10）

6-RC-1~5,7,8,9,10 完成。Reconciler 從 AUDIT-ONLY 升級為自動動作層：漂移→escalation（收緊風控）→漂移消失→hybrid 恢復（clean cycles + wall-clock）。觸發：MinorDrift 不動作 / MajorDrift·Orphan·Ghost·SideFlip→Cautious / persistent≥3→Defensive / burst≥5→CB+CloseAll / REST fail≥10→Cautious。恢復：逐級，CB/MR operator only。`ReconcilerState` + `evaluate_actions()` + `ReconcilerEscalate/DeEscalate` IPC + `Arc<AtomicU8>` shared risk level。+27 tests。872 engine lib + 365 core pass。6-RC-7 e2e 集成測試 7 場景 pass。6-RC-8 live blocker 解除。排除：6-RC-6（OC-3 阻塞）。

## W20 完成 ✅（2026-04-10）

SEC-04/06/13 E3 深度審查 PASS · G-9 HMAC 確認（NOT dead，L171 auth token 驗證）· WP-CC/P9 雙軌止損接線（StopRequest→PositionManager.set_trading_stop()）· FS-1 market_data_client tests 提取（1083→742 行）· BI-1 MODULE_NOTE 12 files · SM-1 Singleton 合規 · 6-01~03 漸進放權管線（promotion_pipeline.py + 3 API endpoints + 27 tests）。E2 修復 3 P1（mutable ref / html.escape key / singleton TOCTOU）。879 engine lib + 2787 Python passed。

## W21 6-04~08 Phase 6 驗收 ✅（2026-04-11）

6-04 集成測試：reconciler_e2e.rs 新增 7 場景（MinorDrift 不重設/SideFlip/Ghost/冷卻/全局冷卻/多級恢復 Defensive→Normal/REST 漸進三階段）+ 6-05 壓測 Rust 4 場景（100 cycle 快速翻轉/50 symbols 爆發/handler 快速升降/性能 1000 calls <100ms）+ Python 5 場景（10 線程並發 register/promote/metrics/冪等/100 策略批量）+ 6-06 sync_commit 驗證 PASS（global `synchronous_commit=on` V006:90 已保護 orders/fills）+ 6-07~08 EvolutionEngine 保留決策（用於 DL/AI agent 學習，與 PromotionPipeline 分工文檔化）。E2 修復 3 項（Ghost handler 完整鏈路/promote 並發斷言 ==1/temp 文件碰撞）。879 engine lib + 18 e2e + 2792 Python passed。

## E5 Performance Optimization ✅（2026-04-12）

23 項全部處理（20 fixed / 2 skipped / 1 deferred）。關鍵：`TickContext<'a>` 零拷貝策略接口 + `push_capped<T>()` 環形緩衝工具（13+ 重複消除）+ PriceEvent 5 typed fields + `tokio::join!` 7 表並行 flush + `ShadowOrderRequest`→`OrderDispatchRequest` 重命名 + `now_ms()`/`is_stale()` 工具函數。17 files, net -336 lines。934+366+27 = 1327 tests pass。

## ORPHAN-ADOPT-1 Phase 1 ✅（2026-04-14）

Reconciler 對 orphan 倉「偵測但不動作」的行為修復。新增 `position_reconciler/orphan_handler.rs`（~350 行 + 11 unit tests）：`handle_orphan(ctx) -> OrphanDecision` 純函數按 A1→A4→B1→default 順序評估（A1 距強平 < 10% / A2 已 CB / A3 名義 > `max_order_notional_usdt` / A4 不在 active universe / B1 五策略 shrunk_bps 全非正且 unrealised > 0）；所有 Phase 1 decision 走 `PipelineCommand::CloseSymbol` reduce_only，dispatch 失敗回退 drift 讓 Phase 6 升級階梯兜底。`ReconcilerState.pending_orphan_closes` HashMap + 2 分鐘 TTL dedup 防止 spam。`main.rs` `build_orphan_cfg(engine_key)` closure factory 按引擎綁 `PerEngineRiskStores` + `SymbolRegistry` + `EdgeEstimates` Arc。V014 audit event `orphan_handled`。Phase 2（Adopt 真實路徑）等 G-1 R-02 Strategist Agent。1136 engine lib + 366 core + 33 e2e = 1535 Rust pass。

## QoL-1/QoL-3 ✅（2026-04-14）

**QoL-1**（commits `22a0b36`+`ea25844`）：`PaperState::restore_from_db(pool, engine_mode)` + `apply_restored_counters()` helper；新增 `event_consumer/paper_state_restore.rs` fail-soft glue（None pool → info / SQL error → warn / 成功 → info with values）；按 `engine_mode` 三引擎隔離還原。重啟驗證 PASS：demo=-3.49/29.11/254 · paper=-14.40/58.21/333 · live=0/0/0。解決「GUI 累計 PnL 每次重啟歸零」。**QoL-3**（commits `c510388`+`dc2eec3`）：新增 `helper_scripts/build_pyo3.sh`（285 行）統一 PyO3 .so 雙寫（`~/.venv` + `control_api_v1/.venv`），`maturin build` → `pip install --force-reinstall` → size 比對驗證；`restart_all.sh` 新增 `--rebuild` 旗標。解決「Rust struct 改動需手動 `maturin develop` 到兩個 venv」。engine lib 1136→1144（+8）。

## ENGINE-HEAL 4 Fix ✅（2026-04-14）

2026-04-14 靜默死亡事故驅動（引擎死 18min 無重啟無死前日誌 · ws 死前 14+min 已斷但進程仍「存活」）。**Fix 1** `main.rs` L55-108 panic hook（`std::panic::set_hook` 捕 thread id/location/payload/`Backtrace::force_capture()` + flush → `tracing::error!`，覆蓋所有 tokio worker & std thread）；**Fix 3** crash-only（`run_pipeline_crash_only<F>()` 包 paper/demo spawn + Live thread catch_unwind 後補 `live_cancel.cancel()`，任一 panic → `EngineEvent::Crashed(kind)` + 全局 cancel → ordered shutdown → exit，**不 isolate**，避免三引擎共享 `RiskConfigStore`/`SymbolRegistry`/`EdgeEstimates` 污染帶病繼續）；**Fix 4** WS tick stale 自救（L1108-1155，30s 週期檢 `shared_last_tick_ms: Arc<AtomicU64>`，age > **120_000ms** 且 last!=0 → `cancel.cancel()`，業務層存活斷言防殭屍）；**Fix 2** watchdog 自動重啟 4 道保險（`engine_watchdog.py` + `stop_all.sh` + `restart_all.sh`）：(1) `fcntl.flock` 單例 (2) `engine_maintenance.flag` operator 意圖守則 (3) SIGTERM-first + 5s graceful + SIGKILL fallback（原 `pkill -f` 會在 `paper_state.json` atomic rename 中途殺死留損毀 tmp → 虛假重啟循環）(4) 退避 [60,120,300,600,3600]s + 連續失敗 ≥5 熔斷寫 `canary_events.jsonl` 告警。**Bonus**：`rotate_engine_log()` 保留 10 份 `/tmp/openclaw/engine_logs/engine-<epoch>.log` — 原 `>` truncate 是事故放大器（沒它任何事故都沒死因）。**決策**：D1 全部 crash-only 含 Live / D2 WS stale 120s（60s 誤報太多，worst case ~3min zombie 可接受）/ D3 Phase 0 medium。**驗證**：engine lib 1144 + core 366 + e2e 33 = **1543** 0 fail · watchdog 8/8 unit · shell `bash -n` clean。**留尾**：運行中引擎仍 pre-fix binary（operator 需 `restart_all.sh --rebuild` 部署）· Phase 2（env 覆蓋 stale threshold / per-tier / metric export）延後。詳見 `docs/worklogs/2026-04-14--engine_self_healing.md` + `docs/known_issues/2026-04-14--ws_stale_detector.md`。

## WP-F/UX-07~10 ✅（2026-04-14，commit `19a84da`）

GUI 術語全域統一 `Paper 模拟` / `Demo 演示` / `Live 实盘`；Tab bar `中文 English` 雙語格式；Session 5 語境消歧（AI 推理 / 交易暂停 / 授权租约 Lease）。**Pass-4 Live 槽雙態註解**：tab-live.html 新增雙語資訊區塊明確「Live 槽可填 Mainnet 或 Live-Demo 虛擬 key，兩者統一走 Live 最嚴標準（紫色主題 / Global Mode Gate / 二次確認 / 完整風控棧）」；tab-settings.html Live-Demo 卡片補 `⚠ 等同 Live 待遇` 標示。3 sub-agent 平行 + 主會話 E2 補 legacy `index.html`。16 文件 +160/-143 行。console.html BUILD_TS `20260414.ux07-unify-v1` 強制 iframe 刷新。**零後端改動**（JSON API 鍵 / CSS class / 函數名 / endpoint 未觸碰）。
