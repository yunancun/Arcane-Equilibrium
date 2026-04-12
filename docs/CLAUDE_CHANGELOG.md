# CLAUDE_CHANGELOG.md — 開發歷史歸檔

> 從 CLAUDE.md 遷出的 Wave/Sprint/Batch 歷史記錄。新 session 不需要讀此文件，僅供回顧歷史時查閱。
> 最後更新：2026-04-12

### E5 Performance Optimization — 23 items（2026-04-12）

P-01 `push_capped<T>()` ring buffer utility（13+ 重複消除）· P-02 PriceEvent 5 structured fields · P-03 hot-path structured reads · P-04 `now_ms()` utility · P-05 `is_stale()` utility · P-06 WS subscriptions Vec→HashSet O(1) · P-08 `TickContext<'a>` zero-copy borrowed refs（5 strategies + orchestrator）· P-09 Arc<RiskConfig> bind-once · P-10 parallel async DB flush `tokio::join!` 7 tables · S-01 confidence clamp · S-02 ring-buffer dedup（+E2 residuals）· S-03 `build_intent()` · S-04 timestamp centralize（+E2 residual）· R-01~R-05 naming（`ShadowOrderRequest`→`OrderDispatchRequest` 等）· D-01/D-03 dead method removal。P-07 skipped（WS SDK managed）· S-05 skipped（fail-closed）· D-02 deferred（HashMap removal post-migration）。17 files changed, +563/-899, net -336。E4: 934+366+27 = 1327 pass 0 fail。

### 審計 P2 Batch A+B：10 項快速修復（2026-04-12）

FIX-21 lib.rs 3 孤立模組移除（batch_order_manager/leverage_token_client/spot_margin_client）· FIX-38 CLAUDE.md §九 Singleton 表補登 6 項（_pool/DEFAULT_LEASE_TTL_CONFIG/_backtest_engine/_scheduler/_evolution_engine/_ledger）· FIX-41 Bearer Token panel 死碼清除（index.html/app-gui.js/app-review.js/styles.css）· FIX-44 tab-learning/monitoring/strategy 加載失敗狀態 UI · FIX-45 Live tab 刷新 30s→15s · FIX-46 tab-risk.html 已達標（510 行，無需拆分）· FIX-51 3 DEPRECATED 文件移至 archive/ · FIX-53 docs/README.md 補 4 子目錄索引 · FIX-54 CHANGELOG 缺失 commit 補錄 · FIX-56 Layer2 定價日期 2026-03-27→04-12。

### PNL-FIX-1/2 + 3 項重要中間修復（2026-04-12）

**PNL-FIX-1** (commit `2a422fa`)：`on_tick.rs` 5 條 close 路徑誤用 `event.last_price` 跨 symbol 平倉 → 改用 per-symbol latest_price。**PNL-FIX-2** (commit `cbb4e45`)：`emit_close_fill` 寫 `fee: 0.0` → 所有平倉路徑收真實費用。**Circuit Breaker 修復** (commit `6ae6e1b`)：3 fixes 防止誤觸 CB + spam。**EA-Persist** (commit `0255a35`)：execution_authority 統一至 T0 trust persistence。**Paper/Demo Session Split** (commit `986d724`)：Paper/Demo 獨立 session 控制。

### 3E-ARCH 中間修復合集（2026-04-11~12）

(commit `d670759`) cross-pipeline DB ID 碰撞修復 — ID 嵌入 engine_mode。(commit `f6e7afc`) paper_state 啟動時從交易所快照 seed。(commit `b5e45f7`+`8e08c34`) private WS topic 環境感知修復。(commit `152d1f6`) demo DCP topic 移除 + live worker_threads 2→4。(commit `660cb75`) scanner/deployed 顯示 Rust active symbols。(commit `87bbe66`) live-gui 條件單顯示 + per-engine session/metrics。(commit `9853845`) paper-metrics 改用 Rust 權威 balance/peak。(commit `35272d3`) IPC 所有命令加顯式 engine 參數修復跨引擎路由。(commit `56c648f`) paper_only 模式 + cost_gate 冷啟動探索。(commit `15203f6`) 動態 is_exchange_mode 防 live WS 覆寫 paper state。(commit `326a191`) 移除 handlePaperAction 硬編碼 initial_balance:10000。(commit `2473efb`+`6bafa4e`) demo/live GUI 平倉路由修復。

### 審計 P2 Rust 7 項修復（2026-04-12 · commit `84f00eb`）

FIX-24 bb_reversion RSI 閾值 30/70→TOML 可配 + ParamRange agent-adjustable · FIX-25 grid_trading fee_rate 字段取代硬編碼常量 · FIX-26 bb_breakout squeeze bool→時間戳 30min 過期 · FIX-27 kelly_sizer 負 edge 拒絕（0.0）非 fallback · FIX-28 intent_processor account_leverage 字段 · FIX-31 PriceEventKind typed enum（Trade/Orderbook/Ticker/Liquidation/PriceLimit/AdlNotice/RestPoll）+ 向後兼容 metadata 雙路徑 · FIX-33 event_consumer exec_id 去重 O(n)→O(1) HashSet+VecDeque。15 files changed, +199/-194。E4: 965+366+27+29+2852 = 4239 pass。

### 全程序鏈審計 P0+P1 全修 + 二輪驗證 + CONCERN 修復（2026-04-12）

**Session 1 (P0 8/8)**：FIX-03 FastTrack ReduceToHalf/PauseNewEntries 實現 · FIX-04 真實 price_drop/margin_util · FIX-09 ocEsc 單引號 · FIX-10 IPC HMAC Live 強制 · FIX-13 edge_estimates +14 tests · FIX-14 REST fail-closed +7 tests · FIX-15 三管線並發 +1 test · FIX-19 execFee taker_fee_rate 估算。

**Session 2 (P1 18/18)**：FIX-05 correlated_exposure_pct 實現 · FIX-06 grid_levels TOML→runtime · FIX-07 OU theta non-OU fallback · FIX-11 Cookie secure auto-detect · FIX-16 startup +5 tests · FIX-17 ConfigStore 並發 +2 tests · FIX-18 Price=0 +2 tests · FIX-20 pre_check_order 刪除 · FIX-22 MlSwitches 4 死欄位刪除 · FIX-29 on_tick 1307→1186 行 · FIX-30 symbol.clone 審查（文檔結論）· FIX-32 risk_config 借用 · FIX-39/40 Danger Zone + 策略刪除 openConfirmModal · FIX-47/48 REFERENCE/KNOWN_ISSUES 更新 · FIX-52 SCRIPT_INDEX 全面重寫 · FIX-55 API paths verified。

**二輪嚴格驗證**：8 組並行 agent 逐行讀碼，26/26 PASS。發現並修復 3 CONCERN：(1) **FIX-03b** ReduceToHalf 缺 `dispatch_close_order()` — Live 模式下本地狀態與交易所倉位脫節 **[HIGH]** → 已補 dispatch；(2) **FIX-19b** 單一 fee rate 近似所有 symbol → 改用 `intent_processor.fee_rate(&symbol)` per-symbol 3 級解析；(3) **FIX-16b** 2/5 tests trivially passing → 替換為 semver 驗證 + env valid/invalid/negative/zero。

**KNOWN_ISSUES**：TRADE-2 → RESOLVED（Rust 同步 tick 無競態）· TRADE-4 → RESOLVED（Rust 每筆 fill 獨立 exec_qty）· 統計修正 OPEN 9 / RESOLVED 15。

965 engine lib + 5 bin + 29 e2e = 999 tests · 0 failures。

### Earned-Trust TTL Ladder + Audit Trail 時間戳修復（2026-04-12）

(1) **Audit Trail 時間戳修復**：`tab-governance.html` JS 讀 `r.timestamp` 改為 `r.when_ms || r.when*1000`，修復 Audit Trail 時間欄永遠顯示 `'--'` 的 bug。(2) **Earned-Trust 授權 TTL 階梯**：新增 `earned_trust_engine.py`（715 行）— T0(24h)/T1(72h)/T2(168h)/T3(360h) 四層階梯，連續乾淨天數晉升，中途降級即時標記（session 繼續），T3 最多自動續期 1 次後強制 Operator 全面審查；新增 `live_trust_routes.py`（484 行）— 3 端點（GET trust-status / POST renew / POST renew-review）；`live_session_routes.py` 新增 session start/stop 鉤子 + `_grant_execution_authority_internal()` 內部輔助；`main.py` 注冊 `live_trust_router`；`tab-live.html` 新增 Trust Status Bar（tier badge + 倒計時 + 續期卡 + T3 全面審查面板）+ 完整 JS（loadTrustStatus / openTrustRenewCard / submitRenew / submitFullReview）。53 新測試 pass。E4: 2852 Python passed。

### Phase 6 PM 驗收 PASS + TODO 歸檔整理（2026-04-12）

6-09~13 最終驗收週期完成。E4: 935 engine lib + 366 core + 18 e2e + 32 promotion = 1351 passed / 0 failed / 0 warnings。E2: Reconciler 0 BLOCKER 0 MAJOR（pre_escalation_level 文檔建議 MINOR）· Promotion Pipeline 0 BLOCKER 0 MAJOR（governance_routes 超限 pre-existing）。QA: 三引擎存活 + 雙 Reconciler 運行 + baseline seeded + API auth enforced。E5: stress PASS。Phase 6 路線圖狀態從 🟡 升為 ✅。TODO.md 歸檔：晚間 Audit BLOCKERs（B-1/B-2/M-1~4）+ Phase 6 驗收詳情移入 `docs/archive/2026-04-11--completed_todo_w19_w20_phase6.md`；3E-ARCH 折疊內容移除（已有專屬歸檔）；排期表更新 W19-21 ✅；Gap 索引標記 G-3/G-5/G-9 完成。

### GUI 指標 DB 降級 + 顯示修復 4 項（2026-04-12）

(1) Live engine badge 顯示「已暫停」— `get_live_session_status()` 改用 `get_engine_snapshot()` 讀頂層 `paper_paused`。(2) Performance Metrics 全 0 — 新增 `fetch_fills_from_db(engine_mode)` DB 降級讀取，paper 1336 fills / demo 68 fills 正確顯示。(3) Live 掛單 Price/Status 顯示 "--" — `OrderInfo` 新增 `trigger_price` 欄位 + JS snake_case 兼容。(4) Demo 夏普比率硬編碼 N/A — 改為從 round-trip PnL 計算。worklog: `docs/worklogs/2026-04-12--gui_metrics_db_fallback_and_display_fixes.md`。935 engine lib + 366 core + 22 paper_metrics pass。

### 3E-ARCH GUI 路由修復：Paper tab 顯示 Live 引擎數據（2026-04-11）

3E-ARCH 上線後 Paper GUI tab 顯示 ~$612 餘額且持倉表為空，實際 paper 引擎是 ~$9941 / 9 倉位。**根因**：`main.rs:563-708` `is_primary` 優先序為 Live > Demo > Paper（`paper.is_primary = !has_live && !has_demo` / `live.is_primary = true`），三引擎並行時 Live 寫入 compat `pipeline_snapshot.json`；而 Python `RustSnapshotReader.get_paper_state()` / 多數 helper 預設讀 compat 檔，因此 paper 路由全部讀回 Live 數據。**On-disk 驗證**：四份檔案內容正確獨立，bug 純粹在 Python 路由層。**修復**：(1) `ipc_state_reader.py` `get_paper_state(mode/engine)` 預設透過 `get_engine_snapshot("paper")` 讀 `pipeline_snapshot_paper.json`；`get_snapshot()` 新增可選 `engine=` 參數（保持預設讀 compat 以維持單元測試 / 單引擎部署兼容）。(2) `paper_trading_routes.py` 9 個 call site 改為顯式 `engine="paper"` / `mode="paper"` + `is_engine_available("paper")` 取代 `is_available()`（涵蓋 session/status、positions、pnl、orders、fills、metrics、export、market-feed/status、shadow/decisions、audit-trail、resume）。(3) `risk_routes.py` 3 個 call site 改 `engine="paper"`（風控儀表板讀 paper 引擎 drawdown/balance/gate stats）。(4) `strategy_read_routes.py` intent reader 改 `mode="paper"`。(5) `live_session_routes.py` fills 降級分支改 `mode="live"`。**回歸測試**：`test_ipc_state_reader.py` 新增 `TestPerEngineRouting`（6 tests）覆蓋三引擎並存路由矩陣，使用 11111.11/22222.22/33333.33 三組哨兵餘額（class 級常數 + docstring 標明刻意用假數值）。**驗證**：21/21 ipc_state_reader + 39/39 ipc_integration + 80/80 paper_live_gate/paper_metrics passed。Reader 直接讀真實 `/tmp/openclaw/pipeline_snapshot_*.json`：`get_paper_state()` 預設返回 9941.47 / 9 倉位（之前是 612.95 / 0 倉位）。

### 3E-ARCH 持久化修復：with_kind() 漏設 pipeline_kind 字段（2026-04-11）

MEGA-BLOCKER-0 commit 0f3af65 留尾 bug：`TickPipeline::with_kind()` 只設 `governance` 不設 `pipeline_kind`，三個引擎全部留在 `with_balance()` 預設的 `PipelineKind::Paper`，導致 demo/live event_consumer 在 `kind_tag = pipeline.pipeline_kind.db_mode()` 時都返回 `"paper"`，三引擎 StateWriter 搶寫同一份 `paper_state.json` / `pipeline_snapshot_paper.json`，產生大量 `state rename failed` ERROR；watchdog 因此誤報 demo/live "not_running"。**修復**：`tick_pipeline/mod.rs:683` `with_kind()` 補一行 `p.pipeline_kind = kind`。**回歸測試**：`test_with_kind_sets_pipeline_kind_field` 鎖定三個 variant。**驗證**：重啟後 `pipeline_snapshot_paper.json` / `pipeline_snapshot_demo.json` / `pipeline_snapshot_live.json` 三檔案各自獨立寫入（balance 10000/793.97/612.95 對應 Paper 默認/Demo Bybit/LiveDemo Bybit），watchdog 三引擎全 alive，0 persistence errors。930 engine lib pass（+1 regression test）。

### 3E-ARCH L3 審計修復：e2e 測試 + 21 warning 清零 + 防御性加固（2026-04-11）

L3 全面審計（PM/PA/FA/CC/E3/E4/E5/MIT/QC 9 角色並行）發現並修復所有問題。**P0**：`stress_integration.rs` 6 個編譯錯誤修復（StrategyAction enum 適配 + IntentProcessor 5th arg GovernanceProfile）。**P2 防御性加固**：(1) event_consumer D19 安全斷言（交易所管線禁止寫入 market/feature DB）；(2) 快照去抖間隔按引擎錯開（Paper 5s/Demo 5.5s/Live 4.5s）避免 I/O 爭用；(3) IPC `extract_engine_tx` 無 engine 參數時 debug 提示；(4) startup.rs 憑證記憶體持留文檔化；(5) fan-out channel buffer 非對稱設計文檔化。**P3 代碼清潔**：21 cargo warning 全部清除 — 6 unused imports + 6 unused variables + 4 unreachable patterns（sector 重複分類）+ 2 dead methods（`cost_gate_k` #[allow] / `make_exit_intent` 刪除）+ 2 never-read fields + 1 unused inner import。**INFO**：Python ipc_client.py `mode` → `engine` 參數重命名語義修正。0 warnings / 929 lib + 366 core + 29 e2e + 2792 Python = 4116 tests passed。

### 3E-ARCH MEGA-BLOCKER-0：真正三引擎獨立並行（2026-04-11 · commit e012faa）

完成原始 3E-ARCH Phase C（3E-10.1）設計中未實現的「三個獨立 spawn」。**startup.rs**：新增 `ExchangePipelineBindings` struct + `build_exchange_pipeline()` 按 API key 獨立構建每條交易所管線（DCP/auto-margin/fee/balance/Private WS 全封裝）；刪除 `determine_primary_kind()` / `detect_available_pipelines()` / `fetch_exchange_balance()`。**main.rs**：刪除「primary+alongside」二管線模型，改為三獨立 spawn（Paper 永遠啟動 + Demo 條件 + Live 條件 D17 OS thread）；`Vec<Sender>` 動態扇出取代固定 primary+paper 雙通道；三獨立 IPC cmd channels 全填充 `EngineCommandChannels`；D23 per-exchange Reconciler（Live + Demo 各自獨立）；有序 shutdown Live→Demo→Paper。2 files, +482/-469 行。929 lib + 366 core + 18 e2e pass。

### 3E-E2 Phase G 殘留修復：M-3/M-4 + 8 MINOR（2026-04-11 · commit 910d2bc）

M-3：`on_tick.rs:497,616` GovernanceProfile hardcoded → `self.pipeline_kind.governance_profile()`（Demo 現用 Validation cost_gate）。M-4：Live pipeline 線程加 `catch_unwind` + panic → `Crashed` 廣播 + health=Down；shutdown JoinError panic 記錄而非靜默丟棄。m-1：`handle_get_state()` 合併 2 次 snapshot 讀取為 1 次。m-2：`std::ptr::eq` → `primary_label()` 字串比對。m-3：`determine_primary_kind()` 3→1 次調用。m-5：`.unwrap()` → `.expect()` with context。m-8：`AuditWriter` 新建檔案 chmod 0600。殘留僅 M-1/M-2 文件大小監控。929 lib + 366 core + 18 e2e pass。

### 3E-E2 Phase G: 9 角色重審 PASS（2026-04-11 · commit de222bd）

Phase A-F 修復完成後重跑 9 角色並行 E2 審查（E2/FA/PA/QC/BB/MIT/E3/E4/E5）。結果：**9/9 PASS — 0 BLOCKER / 4 MAJOR（非阻塞）/ 10 MINOR**。原 10 BLOCKER + 7 MAJOR + MEGA-BLOCKER-0 全部確認修復。測試基線：929 engine lib + 366 core + 18 e2e = 1313 passed / 0 failed / 0 ignored。4 殘留 MAJOR：handlers.rs 1195 行近上限、on_tick.rs 1172 行、GovernanceProfile hardcoded（TODO 3E-2b）、無 catch_unwind 包裹 pipeline（Live 前修）。審計報告：`docs/audits/2026-04-11--3e_arch_phase_g_reaudit.md`。

### 3E-E2 Phase F: 5 超限文件拆分（2026-04-11 · commit 26b9926）

BLOCKER-9：5 個超 1200 行硬上限文件拆分為目錄模組。tick_pipeline.rs 3907→mod.rs(1122)+on_tick.rs(1172)+commands.rs(708)+tests.rs(930)。ipc_server.rs 3223→mod.rs(975)+handlers.rs(1195)+tests.rs(1058)。main.rs 2243→main.rs(930)+startup.rs(716)+tasks.rs(488)。intent_processor.rs 1785→mod.rs(493)+gates.rs(204)+router.rs(499)+tests.rs(597)。position_reconciler.rs 1397→mod.rs(617)+escalation.rs(351)+tests.rs(438)。22 files changed, 11645 insertions(+), 11707 deletions(-)。929 lib + 366 core + 18 e2e pass。

### 3E-E2 Phase E: 25 blocker tests（2026-04-11 · commit e0a7451）

BLOCKER-10：補 25 個 blocker 測試覆蓋 D2（startup barrier）、D6（cross-engine events + PipelineHealth）、D15（global notional cap 8 tests）、D23（snapshot versioning 3 tests）。929 engine lib + 366 core + 18 e2e pass。

### 3E-E2 Phase D: Architecture hardening（2026-04-11 · commit e04c974）

3 BLOCKER + 4 MAJOR：BLOCKER-2（D6 三級故障收縮 EngineEvent/PipelineHealth/broadcast）、BLOCKER-3（D15 全局名義值上限 AtomicU64 + check_global_notional_cap）、BLOCKER-4（D17 Live 獨立 runtime std::thread + worker_threads(2)）、MAJOR-2（startup barrier oneshot 60s timeout）、MAJOR-3（有序 shutdown WS→IPC→primary→paper 10s）、MAJOR-5（IPC audit log）、MAJOR-7（snapshot schema_version 2.0.0 + written_at_ms）。

### 3E-E2 Phase B+C: Per-engine TOML + TradingMode deletion（2026-04-11 · commit 41d5a71）

BLOCKER-8（per-engine TOML params）+ MAJOR-4（TradingMode 殘留清除）+ 3E-10.1~10.7（DB dedup / channel rename / D12 audit / Python env var / config 橋接刪除）。`TradingMode` enum 從 Rust 完全刪除（僅保留 config 反序列化過渡）。PerEngineRiskStores + StrategyFactory::create_for_engine()。

### 3E-E2 Phase A: Quick fixes（2026-04-11 · commit a1c3291）

BLOCKER-5（hmac.compare_digest constant-time）、BLOCKER-6（5 處 std::sync::RwLock→parking_lot::RwLock）、BLOCKER-7（API key save lock 串行）、MAJOR-1（StateWriter chmod 0600 + regression test）。

### 3E-5+7+8: Per-engine snapshots + Python cleanup + API key conflict + Paper GUI（2026-04-11）

**3E-5 (S10) Rust**: `DualStateWriter` wrapper in persistence.rs — per-engine snapshot files (`pipeline_snapshot_{paper|demo|live}.json`) + compat `pipeline_snapshot.json` for primary. `EventConsumerDeps` gains `is_primary: bool`. event_consumer derives filename from `pipeline_kind.db_mode()`. +2 tests (DualStateWriter writes both / no-compat).
**3E-5 (S10) Python**: `_get_trading_mode_from_engine()` → `_get_live_engine_kind()` (live routes always query live/demo engine, no single-mode assumption). `ipc_state_reader.py` rewritten: per-engine cache system, `get_engine_snapshot(engine)`, `get_active_engines()`, `is_engine_available(engine)`, backward-compat primary fallback. `paper_trading_routes.py`: `trading_mode` → `pipeline_kind` in session status response. `strategy_ai_routes.py`: docstring updates.
**3E-7 (S11)**: `settings_routes.py` save_api_key: cross-slot conflict detection — same API key cannot be used by two pipelines (409 response). Checks demo↔live/live_demo pairs.
**3E-8 (S11)**: `engine_watchdog.py`: multi-snapshot monitoring — checks all 4 snapshot files, system alive if ANY engine is fresh. `get_watchdog_status()` returns per-engine status. `tab-paper.html`: Initial Balance input field next to Start button (GUI-configurable, fallback to Demo balance). `POST /api/v1/paper/config` endpoint: persists `initial_balance_usdt` to `settings/paper_config.toml`. `GET /api/v1/paper/config` reads it back.
**Files**: persistence.rs (+32), event_consumer/{mod,types,handlers,tests}.rs, main.rs, ipc_state_reader.py, live_session_routes.py, paper_trading_routes.py, strategy_ai_routes.py, settings_routes.py, engine_watchdog.py, tab-paper.html. **Tests**: 896 engine lib + 366 core + 2792 Python passed.

### 3E-3+4: IPC EngineCommandChannels + TradingMode→PipelineKind cleanup（2026-04-11）

**3E-3 (S8)**：`EngineCommandChannels` struct 取代單一 `pipeline_cmd_tx`。Paper/Demo/Live 各自獨立命令通道。`extract_engine_tx()` helper 按請求 `engine` 參數路由。`handle_set_system_mode_broadcast()` 廣播到所有管線。`add_engine_mode`/`switch_engine_mode` IPC handler 移除 + `PipelineCommand::AddMode`/`SwitchMode` 移除。main.rs 接線：primary_cmd_tx + paper_alongside_cmd_tx → EngineCommandChannels。
**3E-4 (S9)**：`PipelineSnapshot.trading_mode` → `pipeline_kind: PipelineKind`（serde rename 向後兼容）。TickPipeline `trading_mode` field → `pipeline_kind`。mode_states/active_modes/set_trading_mode/add_mode 等多模式基礎設施整體移除。event_consumer runtime TradingMode 引用全部替換為 PipelineKind。config/mod.rs TradingMode 保留（`#[deprecated]`）供 config 反序列化過渡使用。5 個死測試移除，1 個新測試。
**文件**：ipc_server.rs（+60/-80）、tick_pipeline.rs（-180 mode switching）、pipeline_types.rs、event_consumer/mod.rs、handlers.rs、main.rs。
**測試**：894 engine lib（-4 死測試 +1 新）+ 366 core pass。

### 3E-2b-β+γ: Per-engine private WS + reconciler engine label（2026-04-11）

**D21**：`spawn_private_ws_supervisor()` 提取為可重用函數。每交易所管線獨立 BybitPrivateWs + ExecutionListener。日誌含 `engine=` 欄位區分管線。原 inline 130 行 → 函數式結構 `PrivateWsBindings` struct + helper function。
**D23**：`run_position_reconciler()` 新增 `engine_label: String` 參數。V014 audit payload 加 `"engine"` 欄位，區分多對帳器輸出。`spawn_reconcile_audit()` + `spawn_action_audit()` + `dispatch_action()` 全部加 label 參數。
**Ordered shutdown**：Paper-alongside handle 加入 shutdown 等待序列。Private WS handles 通過 CancellationToken 自行退出。
**文件**：main.rs（private WS 提取 +80/-130）、position_reconciler.rs（+15 engine_label 貫穿）。
**測試**：898 lib + 18 e2e pass（無新增，重構保守）。

### 3E-2b-α: Pipeline spawn skeleton + bounded fan-out + parking_lot + DB pool（2026-04-11）

**D25**：`default_pool_max()` 5→20，支撐 3 pipeline + 2 reconciler + scanner 並行。
**D12**：`parking_lot::RwLock` 替換跨管線共享的 `std::sync::RwLock`（EdgeEstimates in main.rs/scanner, InstrumentInfoCache）。非中毒語義，避免單管線 panic 級聯崩潰。
**D10/D20**：有界扇出（bounded fan-out）— 單一 WS event_rx → `Arc<PriceEvent>` 廣播到 N 管線。Paper 1024、Demo 1024、Live 512 buffer。`try_send` 延遲檢測。
**Spawn skeleton**：Paper 管線始終啟動。Demo/Live 管線根據 TradingMode 條件啟動（interim，3E-4 改為直接讀 API key）。Paper-alongside 獨立 pipeline_cmd 通道 + risk_level 原子量。共享 DB writer 通道。
**文件**：main.rs（+120/-50）、instrument_info.rs（parking_lot）、scanner/runner.rs（parking_lot）、database/mod.rs（pool max）、event_consumer/types.rs（Arc<PriceEvent>）、order_manager.rs（test fix）、tick_pipeline.rs（+2 fan-out tests）、Cargo.toml×2（parking_lot dep）。
**測試**：898 lib + 18 e2e pass（+2 新 fan-out tests）。

### system_mode GUI→Rust 同步 + 3E-ARCH 計劃 + GridTrading multi-symbol（2026-04-11）

**system_mode 同步**（6 文件實現）：
- `tick_pipeline.rs`：新增 `SystemMode` 枚舉（live_reserved/demo_reserved/shadow_only/observe_only/design_only），`system_mode` 字段，on_tick gate，`set_system_mode()` 方法（自動平倉 + 暫停 paper）
- `pipeline_types.rs`：`PipelineSnapshot` 新增 `system_mode: String`
- `event_consumer/handlers.rs`：`SetSystemMode` handler arm
- `ipc_server.rs`：`set_system_mode` IPC 命令，`get_state` 改從快照讀 system_mode（移除硬編碼 "demo_only"）
- `ipc_client.py`：`sync_ipc_call()` 同步 IPC 輔助函數
- `control_ops.py`：`apply_config_change` 後 push system_mode 到 Rust（盡力而為）
- `live_session_routes.py`：session status 新增 `system_mode` 字段

**GridTrading multi-symbol 修復**（pre-existing 未修復項）：
- 新增 `template_bounds: Option<(f64, f64)>` 字段，3 個構造函數補齊
- 2 個測試適配 HashMap 索引（lines 1053-1055, 1071）

**3E-ARCH 計劃文件**：
- `docs/references/2026-04-11--three_engine_parallel_arch_plan.md`（PM+PA+FA 三角色分析）
- TODO.md 更新：3E-ARCH 段落 + W22 排期 + 關鍵路徑

**測試基線**：engine lib 879 + e2e 18 + Python 2792 / 0 fail

### Multi-Symbol Position Tracking Refactor（2026-04-11）

**問題**：4 策略各持單一全局 `position: Option<bool>`，理論併發上限僅 4 倉，遠低於風控 `open_positions_max=25`。

**修復**：
- MaCrossover / BbReversion / BbBreakout / GridTrading 全部改為 `HashMap<String, bool>` per-symbol 追蹤
- GridTrading `new()` / `new_geometric()` 移除硬編碼 `"BTC"` key + 預填 grid，改為 `template_bounds` 延遲初始化
- `on_tick` 首次收到 symbol 時：有 template_bounds 用模板邊界，否則 ±10% adaptive
- 生產路徑 `new_adaptive()` 行為不變
- 7 個測試適配延遲初始化

**容量**：理論上限 4 → 100（4 策略 × 25 symbols），實際受風控 `open_positions_max` / `max_same_direction` 約束。

**測試基線**：engine lib 879 + e2e 18 / 0 fail

---

### W21 6-04~08 Phase 6 驗收（2026-04-11）

**6-04 集成測試**（reconciler_e2e.rs +11 場景，7→18）：
- S7: MinorDrift 不重設 clean cycle 計數器（對比 MajorDrift 重設）
- S8: SideFlip → Cautious（完整 handler 鏈路）
- S9: Ghost → Cautious（完整 handler 鏈路，E2 P0 fix）
- S10: Per-symbol 30min 冷卻阻止重複升級
- S11: 全局 5min 冷卻限制快速連續升級（含過期後放行）
- S12: 多級恢復全程 Defensive → Reduced → Cautious → Normal
- S13: REST 失敗漸進三階段（10→Cautious / 30→Reduced / 60→Defensive / 已達目標→跳過）
- S14: Floor rule 阻止恢復低於 pre_escalation_level（原 scenario 7 重編號）

**6-05 壓測**：
- Rust S1: 100 cycle 快速漂移/清除交替 — 狀態一致，max Cautious
- Rust S2: 50 symbols 同時漂移 → CB + CloseAll
- Rust S3: 20 輪 handler 快速升降 — 無死鎖
- Rust S4: 1000 次 evaluate_actions 性能 < 100ms
- Python 5 場景：10 線程並發 register/promote（==1 成功）/冪等/100 策略批量 <1s/並發 metrics

**6-06 sync_commit 驗證 PASS**：
- global `ALTER DATABASE SET synchronous_commit = 'on'`（V006:90）已保護 orders/fills
- MIT/CC/FA 三方確認：per-session 分層優化歸 WP Backlog（當前安全方向偏保守正確）

**6-07~08 EvolutionEngine**：
- 保留（不 deprecate）— 用於 DL/AI agent 學習
- EvolutionEngine = 參數網格搜索優化，PromotionPipeline = 策略生命週期管理，職能不重疊

**6-RC-6 TODO 一致性修復**：6-RC 段標記與 W19 段對齊（`[x]`）

**E2 修復 3 項**：
- P0: Ghost scenario 補完整 handler 鏈路驗證
- P1: Python 並發 promote 斷言從 `>= 1` 改 `== 1`（防漏 lock bug）
- P1: Rust make_writer() temp 路徑加 thread id 防並行碰撞

**測試基線**：engine lib 879 + e2e 18 / Python 2792 / 0 fail

### W20 安全審查 + 漸進放權 + CC 合規（2026-04-10）

**SEC-04/06/13 + G-9 E3 深度審查**
- SEC-04（SQL injection）：全 parameterized queries，PASS
- SEC-06（token in JSON）：已修復為 HttpOnly cookie，PASS
- SEC-13（u32 truncation）：已修復為 saturating cast，PASS
- G-9（HMAC dead import）：NOT dead — `hmac.compare_digest()` 用於 auth token 驗證（L171），PASS

**WP-CC/P9 — 交易所雙軌止損接線（原則 #9）**
- `event_consumer/mod.rs`：StopRequest channel consumer 從 log-only 升級為調用 `PositionManager.set_trading_stop()`
- Paper 模式無 client 時優雅跳過；Demo/Live 調用 Bybit `POST /v5/position/trading-stop`
- Fail-closed：API 失敗時 warn 但本地 StopManager 繼續保護

**WP-CC/FS-1 — market_data_client tests 提取**
- `market_data_client/mod.rs` 從 1083→742 行（低於 800 警告線）
- 18 tests 提取至獨立 `tests.rs`，全部通過

**WP-CC/BI-1 — MODULE_NOTE 雙語補全**
- 12 個 Rust 文件補全 MODULE_NOTE（EN+中文）header

**WP-CC/SM-1 — Singleton 合規確認**
- 審計確認無未登記 singleton

**6-01~03 — 策略漸進放權管線**
- 新增 `promotion_pipeline.py`（~640 行）：PromotionGate class
  - 5 階段：LEARNING → PAPER_SHADOW → DEMO_ACTIVE → LIVE_PENDING → LIVE_ACTIVE
  - Paper 畢業門檻：14d + 100 trades + PnL≥0% + DD<10% + Sharpe>0.5
  - Demo 畢業門檻：21d + 200 trades + DD<8% + Sharpe>0.8 + slippage<15bps + reliability>95%
  - LIVE_ACTIVE 必須 operator 顯式審批（APPROVED/REJECTED/EXTEND）
  - Thread-safe（Lock）+ audit callback + DB 序列化 round-trip
- 3 API endpoints 加入 `governance_routes.py`：
  - `GET /promotion-pipeline/status` — 查詢管線狀態
  - `POST /promotion-pipeline/promote` — 晉升（含畢業門檻預檢）
  - `POST /promotion-pipeline/operator-decision` — Operator 審批
- 27 tests（5 classes：StateMachine/GraduationGates/LiveApproval/Audit/Serialization）

**E2 審查修復**
- P1：`register_strategy()` 返回 copy 而非 mutable ref
- P1：JSON API endpoints 不對 lookup key 做 html.escape（避免 key 不匹配）
- P1：lazy singleton 加 threading.Lock 修復 TOCTOU race
- P2：capital_pct/max_leverage 加類型+範圍驗證

**測試基準線**：Rust engine lib 879 / Python 2787 passed / 0 fail

### W19 安全補強：G-3 IPC 認證 + OC-3/6-RC-6 告警（2026-04-10 · commit W19）

**G-3 / SEC-08 — IPC HMAC-SHA256 認證**
- Rust `ipc_server.rs`：新增 `verify_ipc_token()`（常數時間 `mac.verify_slice`）+ `handle_connection()` auth 區塊：`OPENCLAW_IPC_SECRET` 存在時第一條消息必須是 `__auth` JSON-RPC；時間戳 ±30s 防重放；所有失敗路徑立即斷開
- Python `ipc_client.py`：新增 `_authenticate()` 方法；`import hmac as _hmac_lib` + `hashlib`；`_try_connect()` 在 `_connected=True` 後調用；auth 失敗 fail-closed（關閉連接 + return False）；無 env var 時跳過（向後兼容）
- Python `ipc_client.py`：新增 `get_risk_runtime_status()` 方法（OC-3 輪詢基礎）

**G-5 — API Rate Limiting 全局覆蓋驗證**
- 確認 `main_legacy.py:304-307` `default_limits=[120/min]` + `SlowAPIMiddleware` 已覆蓋全部 214 路由
- Gap 審計誤判（PA 以為只有 3 個路由有 decorator，實際 default_limits 已全局生效）
- Login 端點保留更嚴格的 5/min decorator

**OC-3 + 6-RC-6 — Reconciler governor tier 分級告警**
- `paper_trading_wiring.py`：新增 `reconciler_alert_monitor()` 協程 + 加入 `__all__`
  - 每 30s 輪詢 `get_risk_runtime_status` IPC
  - CIRCUIT_BREAKER / MANUAL_REVIEW → 🛑 P0 alert
  - CAUTIOUS / REDUCED / DEFENSIVE → ⚠️ P1 alert
  - NORMAL 恢復 → ✅ INFO
  - 使用 `asyncio.to_thread` 包裹同步 `ALERT_ROUTER.alert_system`（避免阻塞事件循環）
  - `prev_tier=None` 初始化跳過啟動虛假告警
- `main.py`：startup handler 以 `asyncio.create_task()` 啟動監控（fail-open，不阻斷啟動）

**測試結果**：Rust 879 passed · Python 2760 passed (0 fail · 5 skipped)

### 全系統審計 + Gap 計劃（2026-04-10 · PM/PA/FA/CC）

**背景**：PM/PA/FA/CC 四角色對 Rust engine + Python 控制層 + ML pipeline 進行嚴格完成度審計，發現文檔宣稱「~100%」但實際完成度 72-75%。

**關鍵發現**：
- H1-H5 AI 治理層 5 個 agent handler 全為 stub（ai_service.py），AI 判決層無效
- FundingArb.on_tick() 永遠返回 vec![]（第 5 個策略不產生信號）
- API 203 個路由無全局 Rate Limiting
- HMAC dead import、Calibration.py 骨架
- 以上均未出現在原 TODO.md

**動作**：10 個 gap（G-1~G-10）全部入 TODO.md Gap 索引，排入 W19~W23；CLAUDE.md §十更新排期；最早 Live 日期修正為 W23 末（2026-05-16）。

---

### DB Fresh-Start Reset（2026-04-10 · commit 3acb9cc）

**背景**：開發過程中積累了大量噪音數據（52.9M signals、18.3M decision_context_snapshots、3.6K fills 等），PH5-VERIFY-1 觀察期需要乾淨數據基準。

**執行**：`helper_scripts/db/fresh_start_reset.py --execute` — 71,298,138 行開發噪音清除，耗時 <2s（TimescaleDB chunk drop）。

**保留**：所有 `market.*` 表（klines 44K / market_tickers 1.4M / ob_snapshots / funding_rates 等）完整保留。

**影響**：
- PH5-VERIFY-1 觀察期從 2026-04-10 重新起算（原計劃 2026-04-11 `--days 3` → 改為 `--days 2`）
- JS-1 滾動重跑排程：2026-04-11 `--days 2` → 04-12 `--days 3` → 04-17 `--days 7` → 每週滾動

---

### Python OMS 刪除 + Rust DB 訂單/裁決寫入（2026-04-10 · commit 4cab87c）

**Track A — Rust DB writers**: `TradingMsg::Order` + `OrderStateChange` + `RiskVerdict` 三 variant 加入 `database/mod.rs`；`trading_writer.rs` 新增 `flush_orders` / `flush_order_state_changes` / `flush_verdicts`（INSERT 至 `trading.orders` + `order_state_changes` + `risk_verdicts`）；`event_consumer/mod.rs` 在 pending_reg / Fill / Cancelled / Rejected 四點 emit DB 寫入；`tick_pipeline.rs` 三點 emit RiskVerdict。

**Track B — Python OMS 刪除**: `oms_state_machine.py`（693行）+ `test_oms_state_machine.py`（449行）刪除；`governance_hub.py` 移除 `set_oms_sm` / `get_oms_orders` / `_handle_oms_reconciliation` + OMS reconciliation trigger；`governance_routes.py` GET /oms/orders → stub 空列表 + 遷移說明；`paper_trading_wiring.py` 移除 OMS TTL auto-cancel；`conftest.py` 移除 OMS fixtures + helper；tests 更新。

**結果**: Rust 872 lib tests ✅ / Python 2372 passed / 1 pre-existing fail。

---

### Phase 6: 6-RC-7 e2e 集成測試 + 6-RC-8 Live Blocker 解除（2026-04-10）

**6-RC-7**: `tests/reconciler_e2e.rs` — 7 個端到端場景：(1) MajorDrift→Cautious full chain (2) persistent 3 cycles→Defensive (3) burst 5+→CB+CloseAll (4) recovery Cautious→Normal (clean cycles + wall-clock) (5) CB de-escalation blocked (6) REST failure streak→Cautious (7) floor rule prevents over-recovery。`event_consumer::handlers` 模組升為 pub 供集成測試驅動。`TickPipeline::trading_mode` 升為 `pub(crate)` 修復跨模組訪問。

**6-RC-8**: Reconciler 自動降級功能完整（6-RC-1~5,7,9,10），不再構成 Live 隱含阻塞。唯一排除項：6-RC-6（多通道告警，阻塞 OC-3）。

---

### DEAD-PY-2 大型 Python 死代碼清除（2026-04-10 · commit TBD）

~4500 行 Python 死代碼刪除。Python 層完全無交易邏輯。

**Phase A — PipelineBridge 全刪**：`bridge_core.py`（807）/ `bridge_agents.py`（928）/ `bridge_stats.py`（825）/ `pipeline_bridge.py`（807）全刪。`strategy_wiring.py` 移除全部 Bridge wiring；`paper_trading_wiring.py` / `governance_routes.py` / `main.py` 清理所有引用。`main.py` 移除 SymbolCategoryRegistry→PipelineBridge 背景初始化塊。

**Phase B — Python 策略類全刪**：`strategies/{ma_crossover,bollinger_reversion,funding_rate_arb,grid_trading,bb_breakout}.py` 全刪。`strategy_auto_deployer._deploy_strategy()` stubbed to no-op（DEPRECATED R-07）。

**Phase C — ProtectiveOrderManager 全刪**：`protective_order_manager.py` 刪除。`paper_trading_wiring.py` `PROTECTIVE_ORDER_MANAGER = None`。

**Phase D — BybitDemoConnector 瘦身**：763→~95 行。刪除全部交易方法（BybitDemoConnector 類本身），僅保留 `round_qty_for_exchange()` + `round_price_for_exchange()` 兩個純工具函數。

**Phase E — Tests 清理**：11 個死 test 文件完全刪除（~7000 行）；10+ 個 test 文件外科手術刪除 dead class/method；startup integrity + strategy routes 更新適配 DEAD-PY-2。

**E4**：872 Rust lib + 2427 Python passed（1 pre-existing fail）。

### Phase 6: Reconciler Auto-Contraction（自動降級）（2026-04-10）

**6-RC-1~5,9,10 complete** — Position Reconciler 從 AUDIT-ONLY 升級為自動動作層：漂移→風控收緊（降級）→引擎行為限制→漂移消失→自動恢復。

**risk_gov.rs**：+`RiskInitiator::Reconciler` + `RiskEvent::ReconcilerDrift/RestFailure/Recovery` + `reconciler_escalate_to()`/`reconciler_de_escalate_to()` 便捷方法 + transition rules（CB/MR 不可自動恢復）。+5 tests。

**position_reconciler.rs**：`ReconcilerState`（drift_streak/clean_cycles/cooldowns/pre_escalation_level） + `ReconcilerAction` enum（Escalate/DeEscalate/CloseAll） + `evaluate_actions()` pure function：≥5 burst→CB+CloseAll / persistent ≥3 cycles→Defensive / single→Cautious + per-symbol 30min + global 5min cooldown + hybrid recovery（clean cycles + wall-clock）。`filter_dust()` 6-RC-5（1.5×minQty）。Staleness 6-RC-9（>10min→reseed）。REST failure 6-RC-10（≥10→Cautious）。+17 tests。

**tick_pipeline.rs**：+`ReconcilerEscalate`/`ReconcilerDeEscalate` PaperSessionCommand variants。

**handlers.rs**：+2 command handlers（parse tier → reconciler_escalate/de_escalate → force snapshot）。

**main.rs**：`Arc<AtomicU8>` shared_risk_level 接線：main.rs 創建 → event_consumer 每次 handle_paper_command 後寫入 → reconciler 閉包讀取。

**event_consumer/types.rs + mod.rs**：`shared_risk_level: Option<Arc<AtomicU8>>` 加入 EventConsumerDeps。

**tests**：872 engine lib + 365 core = 1237 all pass（+27 new: 17 reconciler + 5 risk_gov + 5 handler）。

**觸發矩陣**：MinorDrift→no action / MajorDrift/Orphan/Ghost/SideFlip→Cautious / persistent ≥3→Defensive / burst ≥5→CB+CloseAll / REST fail ≥10→Cautious。

**恢復矩陣**：Cautious→Normal: 30 cycles+15min / Reduced→Cautious: 20+10min / Defensive→Reduced: 20+10min / CB/MR: operator only。MinorDrift 不重設 clean cycle。Floor rule：不低於 pre_escalation_level。

**排除**：6-RC-6（多通道告警，阻塞 OC-3）、6-RC-7（e2e 整合測試）、6-RC-8（live blocker）。

---

### Signal Diamond Phase 3+4 Fix Round — Mode Switch + IPC Commands（2026-04-10）

**P0: `set_trading_mode()` state swap** — 替換原 2 行 setter 為完整雙向 `std::mem::swap` 實現：`sync_direct_to_mode_state(old)` 保存舊模式 → `load_mode_state_to_direct(new)` 載入新模式。切換 paper↔demo↔live 時保留各自的 PaperState/IntentProcessor/GovernanceCore/consecutive_losses/session_halted/pending_close。同模式切換為 no-op。新模式自動 `add_mode()` 以當前餘額初始化。

**P2: PaperSessionCommand 擴展** — 新增 `AddMode { mode, balance, response_tx }` 和 `SwitchMode { mode, response_tx }` variants。`event_consumer/handlers.rs` 完整處理：pipeline 操作 + force snapshot write + oneshot response。`ipc_server.rs` 註冊 `add_engine_mode` / `switch_engine_mode` RPC（嚴格 enum match，3s timeout）。

**P3: Python IPC 層** — `ipc_client.py` `get_paper_state(mode=)` 傳遞 `{"engine": mode}` 參數；新增 `get_mode_snapshot()` / `get_active_modes()`。`ipc_state_reader.py` mode-aware lookup + `_MODE_ALIASES` fallback（"paper"↔"paper_only"）。`live_session_routes.py` 所有 IPC call 帶 `{"engine": "live"}`。

**P1 架構決策** — 同時多模式 on_tick 需 per-mode 策略實例（grid/bb_breakout 有內部狀態如 net_inventory）。當前架構支持模式**切換**（state preservation），真正同時執行為 Phase 5+ 工作。

**ModeStateSnapshot** — `mode_state.rs` 新增 IPC 序列化結構體。`PipelineSnapshot.mode_snapshots: HashMap<String, ModeStateSnapshot>` 對主模式讀 direct fields、次模式讀 mode_states。`TradingMode` 加 `Hash` derive。

**測試** — +5 新測試（preserve state / same-mode noop / add_mode+snapshot / pipeline_snapshot / consecutive_losses roundtrip）。**E2 PASS WITH WARNINGS**（僅 file size pre-existing）。**E4: 850 Rust lib / 3 integration / 2692 Python pass, 1 pre-existing fail**。

### SM-1 live 授權統一 + Governance 修復（2026-04-10 · commits 4815386 / 435e613）

**問題 1 — max_position_usd 硬編碼**：`governance_hub.grant_paper_authorization()` scope 中 `max_position_usd: 10000` 為字面量。修復：新增 `max_position_usd: float = 10_000.0` 參數；`post_session_reauth` 改 async，IPC 讀取 Rust `RiskConfig.limits.max_order_notional_usdt`，>0 時覆蓋預設值。

**問題 2 — SM-1 live 授權從未 ACTIVE**：`_submit_live_governance_request()` 只走到 PENDING_APPROVAL，Operator role + live_reserved 雙重門控從未完成 SM-1 批准。修復：(a) `_submit_live_governance_request()` 在 `submit_for_approval` 後立即 `approve()`，使 live auth DRAFT→PENDING→ACTIVE，並 invalidate HUB cache；(b) 新增 `_revoke_live_governance_auth()` — 撤銷所有 mode=live 的 SM-1 auth（ACTIVE/RESTRICTED/PENDING/DRAFT → REVOKED）；(c) `grant_execution_authority()` 同步調用 `_submit_live_governance_request()`；(d) `revoke_execution_authority()` + `post_live_session_stop()` 同步調用 `_revoke_live_governance_auth()`；(e) `governance_hub.get_status()` 多授權並存時優先顯示 `mode=live` 授權。

**效果**：live session start → 治理中心顯示 `mode: live / execution: live_submit / approved_by: <actor>`；stop/revoke → 恢復 `paper only`（若 paper auth 仍有效）；drawdown halt → FROZEN（不變）。2676 Python tests pass。

### Live/Demo GUI 平倉按鈕 + Sidebar mode 修復（2026-04-10 · commits c370cd1 / bfc3cea / 81a0acb）

**Sidebar 修復**：`console.html refreshSidebar()` 改用 `/api/v1/live/session/status` 替代 `governance/status`，正確讀取 `trading_mode` / `execution_authority` / `session.session_state`；live 且 granted 時顯示紫色 mode + `auth: granted`，否則顯示 `Live_Ready`。

**後端新端點**：(a) `POST /api/v1/live/positions/{symbol}/close` — IPC `close_position`，Operator role，session 繼續；(b) `POST /api/v1/live/close-all-positions` — IPC `close_all_positions`，session 繼續；(c) `POST /api/v1/strategy/demo/positions/{symbol}/close` — PyO3 `get_positions` 查 qty/side → `place_order reduce_only=True`；(d) `POST /api/v1/strategy/demo/close-all-positions` — `_close_all_demo_positions()`。

**前端**：live/demo 持倉表各行末尾加「平倉」按鈕（confirm dialog + `ocPost`）；Positions section header 加「全部平倉」按鈕；移除 control bar 原有重複「關閉所有倉位」按鈕；paper tab 同步加「全部平倉」；`_normalize_execution()` 處理 Rust snake_case→Bybit camelCase（execQty/execPrice/execFee）。2280 Python tests pass。

### Signal Diamond Multi-Engine Data Separation — Phase 1-4 Complete（2026-04-10）

**Phase 1: V015 Migration** — `sql/migrations/V015__engine_mode_separation.sql` adds `engine_mode TEXT NOT NULL DEFAULT 'paper'` to 8 trading tables + nullable on `agent.ai_invocations`. Indexes `(engine_mode, ts DESC)`. `trading.signals` untouched (shared). DEPRECATED comments on `is_paper` columns.

**Phase 2a: Rust DB Writers** — `TradingMsg::Intent/Fill/PositionSnapshot` + `DecisionContextMsg` gain `engine_mode: String`. `trading_writer.rs` flush functions write `engine_mode` column; `is_paper` derived as `engine_mode != "live"` (backward-compat Grafana). `context_writer.rs` flush adds `$26 = engine_mode`. `TradingMode::db_mode()` canonical mapping: PaperOnly→"paper", Demo→"demo", Live→"live".

**Phase 3: ModeState Extraction** — New `mode_state.rs`: `ModeState` struct (PaperState + IntentProcessor + GovernanceCore + risk_store + ring buffers + consecutive_losses + session/pause flags + pending_close + exchange_seq) + `ModeStateSnapshot` for IPC. `TickPipeline` gains `mode_states: HashMap<TradingMode, ModeState>` + `active_modes: Vec<TradingMode>`. Primary mode bridge: `mode_snapshot()` reads from direct fields for primary mode, ModeState for secondary. `PipelineSnapshot.mode_snapshots` added. `TradingMode` gets `Hash` derive.

**Phase 4: IPC + Python** — Rust `ipc_server.rs`: `get_paper_state` accepts optional `engine` param (default "paper"); new `get_mode_snapshot` and `get_active_modes` methods. Python `ipc_state_reader.py`: `get_paper_state(mode=)` with `mode_snapshots` lookup + alias handling; new `get_mode_snapshot()`, `get_active_modes()`, mode-aware `get_recent_intents/fills()`. `live_session_routes.py`: all IPC calls pass `{"engine": "live"}`.

845 Rust lib tests pass. 2692 Python tests pass (1 pre-existing fail).

### Live-Demo 槽位 + Live/Paper Metrics 修復 + DB Signal Diamond 規劃（2026-04-10 · commit 25b5d73）

**`settings_routes.py`**：新增 `live_demo` 虛擬槽位（validate via demo server → 寫入 live path；operator 可用 Demo 帳號完整測試 live 路徑，換 key 時零代碼改動）。**`tab-settings.html`**：3 API key 卡片（Demo / Live-Demo / Live）+ peek 遮罩按鈕 + dialog overlay CSS 修復 + 槽位上下文警示。**`live_session_routes.py`**：新增 `GET /api/v1/live/metrics` 端點。**`paper_trading_routes.py`**：`/metrics` 端點修復（呼叫 `compute_full_metrics()`，返回完整 trade_metrics / drawdown_metrics / holding_period_metrics / sharpe_ratio，修復所有指標顯示 "--"）。**`tab-live.html`**：Performance Metrics 區塊（10 個指標卡，30s 刷新）。**`DB_TODO.md`**（新文件）：Signal Diamond 多引擎數據隔離規劃（5 階段實施）。840 Rust lib tests pass。

### Live 縮倉監控 + OPENCLAW_ALLOW_MAINNET 鎖移除（2026-04-10 · commit 25b5d73）

**Rust `bybit_rest_client.rs`**：移除 `OPENCLAW_ALLOW_MAINNET=1` env var guard（9 行），保留主網 warn 日誌；更新 `config/mod.rs` TradingMode::Live docstring + `main.rs` 注釋。840 Rust lib tests pass。

**`live_session_routes.py`**：新增 `_live_contraction_monitor()` async 後台 task — 每 5 分鐘輪詢引擎 `peak_balance + bybit_sync_balance/balance`，計算 session 回撤；`CONTRACTION_WARN_PCT=5.0%` → 警告日誌；`CONTRACTION_HALT_PCT=15.0%` → 撤銷 `execution_authority` + `close_all_positions` IPC + `_freeze_live_governance_auth()`；新增 `_freeze_live_governance_auth()` 凍結 GovernanceHub 中 mode=live 授權（審計留痕）；`post_live_session_start` 啟動 monitor task + 初始化 `_live_contraction_state="normal"`；`post_live_session_stop` 取消 task + 重置狀態；`post_live_session_resume` 重啟 monitor task；`get_live_session_status` 加入 `contraction{}` 字段（state/warn_pct/halt_pct/drawdown_pct/peak_balance/current_balance）。

**`tab-live.html`**：控制欄新增 `#live-contraction-badge`：normal 時隱藏；warned 時顯示黃色警告 + 回撤 %；halted 時顯示紅色 + 禁用 Start 按鈕。

### Gov-P1 + Live_Ready 全阻隔移除（2026-04-10 · commit 045e79c）

**`live_session_routes.py`**：`post_live_session_start` 自動授予 `execution_authority = "granted"`（雙重門控 Operator 角色 + live_reserved 已足夠，不再需要額外 grant 步驟）；`post_live_session_stop` 重置 `_EXECUTION_AUTHORITY_OVERRIDE = None`（fail-closed）；`post_live_session_resume` 移除舊 execution_authority 硬鎖，改為 global_mode 二次確認 + 重授；新增 `_submit_live_governance_request()` — live session start 時向 GovernanceHub 提交 PENDING 授權申請（非阻塞，審計留痕，Operator 可在治理頁確認）。

**`tab-live.html`**：`checkLiveEngineStatus()` detail 行邏輯修改 — active 時顯示 `mode | authority`，idle 時只顯示 `mode`（消除 `authority: not_granted` 噪音）。

**`CLAUDE.md`**：§四 `execution_authority = "auto_granted_on_start"` + 硬錯誤清單更新；§三 Runtime 狀態更新為 Live_Ready ✅ 全阻隔已移除；§十一 一句話更新。

**测试**：840 Rust lib pass · 2280 Python pass · 1 pre-existing fail 不變。

### Live GUI Phase 5 — 紫色主題 + 擴展儀表板 + Global Mode Gate（2026-04-10 · commit c392220）

**tab-live.html**：CSS 全面紅→紫（warn-bar/control-bar/accent borders → rgba(168,85,247,..)）；Account Balance 卡片組（total equity / available / wallet balance / margin used = equity - available）；PnL Overview 卡片組（unrealized large + realized from cumRealisedPnl sum + net PnL）；持倉表新增 Leverage 列；成交記錄折疊區（懶加載 `/api/v1/live/fills`，展開時觸發）；active badge `oc-chip-bad` → `oc-chip-live`；緊急停止按鈕保持紅色。

**tab-system.html**：`live_reserved` 按鈕邊框/圖標 🔴→🟣 + 紫色；`updateModeBtns` chip `oc-chip-bad`→`oc-chip-live`；MODE_CONFIRM warn-box 紅→紫；loadOverview metric class `red`→`purple`（新增 `.purple { color: #a855f7 }` CSS class）；模式升级路径顏色紅→紫。

**live_session_routes.py**：`_get_global_mode_state()` 讀 STORE `global_runtime.derived.global_mode_state`；`post_live_session_start` 新增 409 gate（global mode 必須含 'live'）；`GET /api/v1/live/fills` 新端點（PyO3 `get_executions` + fallback）。

**common.js**：`oc-chip-live` 紫色 chip CSS class（rgba(168,85,247,..)）。

**console.html**：live mode mc-val 顏色改為 `#a855f7` inline style；BUILD_TS → `20260410.live-ui-v2`。

### Live GUI Phase 4 — 授權 gate + PyO3 真實數據 + _ipc_command 修復（2026-04-10 · commit af392c2）

**live_session_routes.py**：`_EXECUTION_AUTHORITY_OVERRIDE` 記憶體覆蓋（重啟清空 fail-closed）；`_get_execution_authority()` 先查 override 再走 governance；`_ipc_command()` 3 bug 修復（錯誤 import / 未 connect / 未 disconnect）；`_get_rust_client_safe()` helper；`POST /api/v1/live/execution-authority/grant` + `/revoke`（operator-only）；live session start 接受 `demo` mode（demo key 測試）；`GET /api/v1/live/balance|positions|orders` 改為 PyO3 BybitClient 優先（真實帳戶數據），IPC 降級。

**tab-live.html**：lock screen 加「Grant Execution Authority」按鈕；dashboard 加「撤銷授權」按鈕；`grantLiveAuthority()` / `revokeLiveAuthority()` JS；balance 解析支援 PyO3 snake_case + Bybit camelCase 雙格式 + unrealized PnL；positions 移除 `p.position` 嵌套（Bybit 扁平格式）；orders 使用真實 Bybit 欄位（orderId/price/orderType/orderStatus）。

E4：840 Rust + 2280 Python passed，1 pre-existing fail。

### Live_Ready 狀態切換 + live 端點上線（2026-04-10 · commit 09a5d02）

CLAUDE.md §四 hard limits 更新：移除 `system_mode=demo_only` / `execution_state=disabled` 硬限制。新 Live 技術門控：OPENCLAW_ALLOW_MAINNET=1 + live API keys + execution_authority=granted（三條件全滿足才真實接入主網）。

新增 3 個實盤端點（`live_session_routes.py`）：`GET /api/v1/live/balance` / `/live/positions` / `/live/orders`，全部走 IPC `get_paper_state`，引擎不可用時優雅降級。

`tab-live.html`：`loadDashboardData()` 呼叫 live 端點（非 demo）；訂單表完整接線（原 LIVE-P1-3 stub）；phase badge 更新為 "✅ Live_Ready"。

`main.rs` 啟動 banner：`demo_only | Execution: disabled` → `Live_Ready | Execution: operator-gated`。

---

### L3 嚴格審計 + 2 bug 修復（2026-04-10 · commit ed26346）

4 路並行 agent 審計 LIVE-P0/P1/P2 所有層次：Rust ipc_server/main、Python risk_routes/live_session、GUI tab-risk/live/settings、LIVE-P1 Rust TradingMode。

**CRITICAL: live_session_routes._ipc_command() 三重斷線**（Python C-1/C-2/C-3）— 原碼 import `get_ipc_client`（不存在）、從未 connect()、從未 disconnect()；所有 live session 端點靜默返回 HTTP 503。修復：EngineIPCClient + connect/call/finally disconnect（同 paper_trading_routes 模式）。

**C2: in-tp-enabled checkbox dirty-tracking 缺失**（GUI）— checkbox 用 change 事件但不在 _RISK_INPUT_IDS forEach 裡；修復：加獨立 change 監聽器。

已驗證乾淨：Rust TradingMode match 窮舉、OPENCLAW_ALLOW_MAINNET 硬鎖、key slot routing、per-engine whitelist、p1_risk_pct 轉換。已確認設計決策（非 bug）：TOML 無磁盤 hot-reload、risk_store 啟動鎖定、tab-live stub 前置條件、execution_authority Python-only guard。

E4：840 Rust lib / 2280 Python + 1 pre-existing fail — 無回歸。

---

### LIVE-P2-1/P2-2/P2-3 per-engine RiskConfig separation（2026-04-10 · commit 006d905）

**LIVE-P2-1 Rust PerEngineRiskStores**:
- New `PerEngineRiskStores` struct bundles 3 `Arc<ConfigStore<RiskConfig>>` (paper/demo/live); replaces single Optional field
- `IpcServer.risk_stores: Option<PerEngineRiskStores>`; `set_config_stores()` takes full struct
- IPC `get_risk_config`/`patch_risk_config` accept optional `engine` param, route to correct store (default paper fail-safe)
- `main.rs`: `load_unified_configs()` loads 3 TOML files with env var overrides; legacy fallback `risk_config.toml` → paper if `risk_config_paper.toml` absent
- `async_main()` selects correct store by `TradingMode` for `EventConsumerDeps.risk_store`
- New TOML: `risk_config_paper.toml`, `risk_config_demo.toml` (same as paper); `risk_config_live.toml` (conservative: leverage 10x, position 5%, drawdown 5%, daily_loss 3%)

**LIVE-P2-2 GUI per-engine tab**:
- `tab-risk.html`: engine selector card (Paper/Demo/Live); live warning banner; confirmation modal before live saves
- `_selectedRiskEngine` state; `loadRiskConfigForEngine()` calls new per-engine endpoint; `_engineSaveUrl()` routes saves; `_wrapLiveSave()` intercepts live saves

**Python per-engine endpoints** (`risk_routes.py`):
- `GET /api/v1/paper/risk/config/engine/{engine}` — direct IPC, bypasses RiskViewClient version tracking
- `POST /api/v1/paper/risk/config/engine/{engine}/global` — direct IPC patch with engine routing
- `_ALLOWED_ENGINES` whitelist prevents path injection

**E2+E4**: zero review issues; 840 Rust lib tests / 2280 Python + 1 pre-existing fail pass.

---

### SEC-05 innerHTML XSS + WP-F/AH-06 risk-tab dirty-tracking（2026-04-10 · commits 19b40dc + b7b7651）

**SEC-05 innerHTML XSS remediation** across GUI:
- `app.js`: `safeText()` now delegates to `ocEsc()` (covers ~20+ call sites at once); 15+ individual `ocEsc()` wraps for paper positions/orders/fills, market feed, learning feed, cost breakdown, risk envelope
- `app.js` supplement (b7b7651): 4 badge/label function fallbacks escaped — `confidenceBadge`, `statusBadge`, `reviewStatusBadge`, `reviewTypeLabel`
- `cards/linucb_card.html`: `ocEsc()` on regime names, arm_id, shadow champion/challenger/decision
- `tab-ai.html`: `ocEsc()` on Kelly strategy keys and tier labels
- Remaining files (tab-governance, tab-settings, tab-system, tab-live, console) audited — already properly escaped or use hardcoded data only

**WP-F/AH-06 risk-tab form overwrite fix**:
- `tab-risk.html`: `_riskFormDirty` flag set on any input event across 16 risk form fields
- `loadRiskConfig()` skips populating inputs when dirty flag is true
- Flag cleared after successful save in all 3 save functions
- Replaces inadequate `document.activeElement` guard that only protected focused element

### A2 NewsPipeline Scheduler + DEAD-PY-1 Complete + 1C-4 Close（2026-04-10）

**A2 NewsPipeline 60s scheduler** wired into `main.rs`:
- 3 providers: CryptoPanic (free tier, 28min self-throttle) + CoinTelegraph RSS + Google News RSS
- 4-09 triple-route NewsRouter: Guardian halt check + regime buffer + learning context sink
- Gated by `LearningConfig.switches.news_pipeline_enabled` (hot-reloadable via ConfigStore)
- Follows existing fee_rate/instrument refresh tokio::spawn pattern with cancel token
- ~95 lines added to `main.rs`

**DEAD-PY-1 whitelist UI removal** (WP-CLEANUP-WHITELIST-UI):
- `tab-governance.html`: removed HTML card + modal + CSS + JS vars/functions + init + explainers (−220 lines)
- `governance.js`: removed 3 dead API wrapper functions (−19 lines)
- All whitelist references eliminated; backend already returns HTTP 410 Gone

**1C-4 final verification**: E2 code review + E4 regression (838 Rust lib / 2692 Python passed / 1 pre-existing fail) + doc sync

### LIVE-P0-1/P0-2/P0-3 — API key mgmt + live page rewrite（2026-04-10 · commit c680ffd）

- `settings_routes.py` (new): GET/POST /api/v1/settings/api-key/{slot}  
  Slot whitelist → HMAC validation → write + chmod 600 → masked hint only  
- `main.py`: registered settings_router  
- `tab-settings.html`: API key management card for demo/live slots  
- `tab-live.html`: full rewrite — dynamic prereq checklist (10 checks, live API queries) + dashboard framework (lock overlay / unlocked with PnL metrics / positions table / emergency stop)  
- Tests: 2692 passed / 1 pre-existing fail (unchanged)

### ML Pipeline Audit Gap Fixes（2026-04-10）

Cold audit of all ML_TODO completed items found 3 real issues + 4 pre-existing test failures:

**Fixes**:
1. `cpcv_validator.py` — `model_name`/`model_version` now parameterized through `validate_cpcv()` (was hardcoded `"lightgbm_scorer"`/`"v1"`)
2. `bybit_demo_sync.py` — `_get_conn()` now prefers db_pool, fallback to direct `psycopg2.connect()`; `_release_conn()` returns to pool or closes
3. `test_phase4_routes.py` — 4 "no PG" tests now mock `db_pool.get_conn` (were broken by previous db_pool migration but not caught)
4. `test_bybit_demo_sync.py` — 2 tests updated to assert `_release_conn` instead of `conn.close`
5. ML_TODO.md archived to `docs/worklogs/2026-04-10--ml_pipeline_remediation_complete.md`, removed from root

**Test baselines**: control_api 2678 passed / 1 pre-existing fail · ml_training 135 passed / 6 skipped

---

### ML Pipeline Remediation — S0-S3+S5（2026-04-10）

基於 2026-04-09 DB R/W + ML Pipeline 全面審計完成大規模修復。

**Rust cost_gate 統一（S1）**：
- `intent_processor.rs`：5-tier slippage lookup、ATR% 正規化、win_rate 加權門檻（`fee_bps / max(0.3, wr) * 1.3`）
- `edge_estimates.rs`：`CellEstimate` struct（win_rate, n_trades, std_bps）、`get_cell()` + `load_from_str()`
- 838 lib tests pass（基準 835→838，+3 new: slippage_tier, js_win_rate, atr_pct）

**ML 推理管線（S2）**：
- `parquet_etl.py`：加時間窗口過濾 `WHERE updated_ts_ms >= start_epoch_ms`
- `label_generator.py`：修復 zero-ATR floor（`np.quantile` on empty array）+ 2 test fixes
- FeatureCollector 已接線確認（審計報告過時）

**參數優化管線（S3）**：
- `optuna_optimizer.py`：`_persist_suggestion()` → `learning.ml_parameter_suggestions`（V004 DDL 已上線）
- `cpcv_validator.py`：`_persist_cpcv_result()` → `learning.cpcv_results`
- Thompson Sampling：確認為 (A) offline 工具，`bayesian_posteriors` UPSERT 已存在

**DB 基礎設施（S5）**：
- `db_pool.py`（NEW）：`ThreadedConnectionPool`（min=2, max=10），singleton + env var 可配
- `grafana_data_writer.py` + `strategy_read_routes.py` + `phase4_routes.py`：全部委託到 db_pool
- `strategy_read_routes.py`：DB 失敗返回 HTTP 503（非 200 空數據）
- `/api/v1/health/db` endpoint：連接池統計 + SELECT 1 探測
- 2692 Python tests pass（基準 2678→2692），1 pre-existing fail · 160 ML tests pass（基準 135→160）

### Scanner QC/FA Audit P0+P1 全修（2026-04-09 · commit `72f6617`）

5 files · +163/-4 行 · 831 lib tests pass（基準 830→831）

**P0 — 掃描器核心 gap（功能性 bug）**：
- **D2 fix**：`event_consumer/mod.rs` 不再 ignore `_symbol_registry`；主循環每 30s（status interval）diff registry 與 known_symbols，調用 `pipeline.add_symbol` / `pipeline.remove_symbol`
- **D3 fix**：新增交易對觸發異步 kline bootstrap（`tokio::spawn` 獲取 200 × 1m 歷史 K 線，通過新 mpsc channel 回傳主循環植入 `kline_manager.seed_bars`）；架構：spawned task → `kline_seed_tx` → 主 select arm `kline_seed_rx.recv()`
- **C-3 fix**：`sectors.rs:29` 移除 XRP 重複（已在 l1_infra，導致 payments_l1 arm 不可達）；XRP 現在正確路由到 payments_l1；補 regression test `test_sector_xrp_is_payments_l1`

**P1 — 可靠性改善**：
- **C-4 fix**：`apply_correlation_filter` 在貪心循環前預佔固定交易對（BTC/ETH）的 high_beta / strategy / sector 計數；原來不計入導致實際選出 10 high_beta（超出 8 上限）+ 6 l1_infra（超出 4 上限）
- **M-1 fix**：`remove_symbol` 補 `pending_close_symbols.remove(symbol)`；防止同名交易對重新加入時繼承過期平倉鎖
- **M-2 fix**：`scanner_config.toml` `50_000_000.0` → `50000000.0`（toml crate v0.8 不支持下劃線數字字面量；原來靜默 fallback 到 Default 恰好等值）

### StrategyAction Enum — QC/FA follow-up 全修（2026-04-09 · commits `fc51439`→`70ce1ed`→`83f9d2e`）

8 files · +572/-110 行 · 830 lib tests pass（基準 769→830）

**核心實現（`fc51439`）**：
- `StrategyAction` enum（`Open(OrderIntent)` / `Close { symbol, confidence, reason }`）替代 `Vec<OrderIntent>` 返回型別
- 5 策略全部改造：MaCrossover（ma_reverse_cross）、BbReversion（bb_mean_revert）、BbBreakout（trailing_stop/regime_shift/pctb_revert/bw_squeeze 4 路出場）、GridTrading（net_inventory 符號判定 Open/Close）、FundingArb（型別變更，仍空 vec）
- `tick_pipeline.rs`：延遲平倉執行（borrow checker 要求收集後在策略循環外執行）
- `on_external_close` trait 回調：風控/止損平倉時通知策略重置內部狀態
- P1 修復：risk-close 路徑漏 `record_trade`（Kelly 統計缺失）

**QC/FA 並行審查修復**：
- **P1**：Grid `net_inventory` 漂移 — Close 不再在 `on_tick` 中即時調整庫存，新增 `on_close_confirmed` / `on_close_skipped` trait 回調，管線確認/跳過後才調整/回滾
- **P2**：Exchange-mode `apply_exchange_fill` 漏 `record_trade` — 非零 realized_pnl 時更新 Kelly
- **P2**：`funding_arb` 缺 `on_external_close` — 新增 `position = None` 重置
- **P2**：管線集成測試 — `test_strategy_close_action_closes_position` + `test_strategy_close_no_position_is_noop`
- **P2**：`recent_intents` 審計日誌覆蓋所有平倉路徑（paper + exchange，成功/跳過/待處理）
- **bonus**：Scanner `remove_symbol` 編譯錯誤（`last_persisted_signal` 複合鍵 `retain`）

### Rust 市場掃描器 Phase C+D — ScannerRunner 完整接線（2026-04-09 · commit `70ce1ed`）

8 files · +647/-21 行 · 830 lib tests pass

**Phase C（ws_client + runner）**：
- `WsTopicChange` enum（Subscribe/Unsubscribe）加入 ws_client.rs
- `WsClient.with_topic_change_channel()` 返回 sender，`run(mut self)` 內部處理 Subscribe/Unsubscribe；subscription list 同步更新供重連重播
- `ScannerRunner`（runner.rs）：warmup → 掃描循環 → score → correlation filter → registry → WsTopicChange → sleep
  - 使用 `ConfigStore<ScannerConfig>.load()`；RwLockReadGuard 在塊內丟棄（非 Send，不可跨 await）
  - `query_open_positions()`: 2s 超時，fail-soft 返回空集合

**Phase D（main.rs 接線）**：
- C3：`TickPipeline::add_symbol / remove_symbol`（委託 KlineManager，清除 per-symbol 緩存）
- D1：`EventConsumerDeps` 新增 `symbol_registry + scanner_store`
- D4 main.rs：
  - 從 `settings/risk_control_rules/scanner_config.toml` 加載 ScannerConfig
  - 用固定交易對（BTC/ETH）初始化 SymbolRegistry
  - 為掃描器評分器加載 EdgeEstimates（與 intent_processor 副本分離）
  - 中繼通道：persistent channel → relay task → current WsClient inner_tx（Arc<Mutex<Option<Sender>>>）
  - 在有 REST client 時 spawn ScannerRunner
  - WS supervisor 每次重啟從 registry.snapshot() 重建訂閱 + 更新中繼通道
  - 質量監控器使用 registry.snapshot() 代替 SYMBOLS
- `scanner_config.toml`：創建默認配置文件

### PH5-WIRE-1 path fix + release build + 引擎確認上線（2026-04-08 · commit `cf77bec`）

1 commit · `+7/-9` 行 · 引擎 log 確認 WIRE-1 激活

**問題**：JS snapshot 和 cluster JSON 被寫入 `/home/ncyu/BybitOpenClaw/settings/`（srv/ 外層），而非正確的 `srv/settings/`。Python 路徑多一層 `../`（3 層應為 2 層）。Rust `event_consumer` 用 `current_exe()+../../..` 計算 base dir 也指向錯誤位置（引擎從 `srv/` 目錄啟動，應用 `current_dir()`）。

**修復**：
- `james_stein_estimator.py` + `edge_cluster_analysis.py`：`"..","..","..","settings"` → `"..","..","settings"`
- `event_consumer/mod.rs`：`current_exe().parent().join("../../..")` → `current_dir()`
- 錯誤位置文件已手動移至 `srv/settings/`
- Release binary 重建（`cargo build --release`，舊 binary 停留在 22:18，WIRE-1 前）
- 引擎重啟後 log 確認：`PH5-WIRE-1: edge estimates loaded n_cells=8`，`cost_gate(JS): negative estimate — exploration mode` 實際觸發

**數據策略決定（session 3 末，已更新）**：歷史 fills 含開發期噪音。原計劃不清空改用滾動窗口，**2026-04-10 已執行 DB fresh-start reset**（見上方 changelog 條目），71.3M 開發噪音行清除，乾淨數據從 2026-04-10 重新起算。JS-1 滾動重跑排程已更新（見 TODO.md）。

---

### PH5-WIRE-1 + 5-01~03: mode-aware cost_gate + k-means cluster analysis（2026-04-08 · commit `5e760be`）

1 commit · `+846/-72` 行 · engine lib 769 / Python 2692 passed · 1 pre-existing fail（無 regression）

**核心問題（上個 session 遺漏）**：WIRE-1 被標記為「等 paper 改善再接」但存在循環依賴——JS 估計全負 → 若接線攔截所有 trades → 無新數據 → 估計永遠負 → paper 無法自己改善。本 session 修正了這個設計缺陷。

**WIRE-1 Rust 實作：**
- NEW `edge_estimates.rs`：`EdgeEstimates` struct，從 `settings/edge_estimates.json` 加載 JS 快照；O(1) (strategy::symbol) 查詢；文件缺失時靜默返回 empty（cold-start 回退）
- `intent_processor.rs`：重構 cost_gate 為兩個 helper：
  - `cost_gate_paper()`：正 JS 估計 → EV vs fee 比較；**負估計 → exploration 模式（允許+記錄，打破循環依賴）**；None → ATR×0.2 cold-start fallback
  - `cost_gate_live()`：無正估計 → fail-closed（根原則 #5 生存 > 利潤）
  - 加 `edge_estimates: EdgeEstimates` field + `set_edge_estimates()` method
- `tick_pipeline.rs`：`set_edge_estimates()` wrapper
- `event_consumer/mod.rs`：啟動時從 `OPENCLAW_EDGE_SNAPSHOT` 或默認路徑加載估計

**5-01 Python 擴展：**
- `realized_edge_stats.py`：`EdgeStats` 新增 `win_rate`, `avg_win_bps`, `avg_loss_bps`；`compute_edge_stats()` 補算
- `james_stein_estimator.py`：新增 `_shrink_and_attach()` helper；對 win_rate/avg_win/avg_loss 分別執行 JS 收縮；計算 `combined_ev_bps = shrunk_wr × shrunk_avg_win + (1-shrunk_wr) × shrunk_avg_loss`；JSON snapshot + PG upsert 各新增 3 個 param_name 行

**5-02~03 Python 新文件：**
- NEW `edge_cluster_analysis.py`：純 stdlib k-means（k=auto，n<6 用 2，否則 3）；歸一化特徵 [shrunk_bps, win_rate, combined_ev_bps]；cluster label candidate/middle/underperformer（按均值 shrunk_bps 命名）；全局排名；輸出 `settings/edge_clusters.json`；支援 `--from-pg` 模式從 PG 直接加載

**E2 flag**：`intent_processor.rs` 現 1295 行（原 1214 已超限，helper 重構有價值但淨 +81 行；tick_pipeline.rs 大重構延後）

### Phase 5 P0 + DEAD-PY-1 完成 + 測試基線清理（2026-04-08 · commits `75d8f36`–`caf2bcc`）

6 commits · `+769/-952` 行（淨 -183）· engine lib 769 / Python 2678 passed · 21→1 pre-existing fail

**動機（Edge 危機）**：paper realized edge ≈ 2 bps，fee = 11 bps，Net EV ≈ −9 bps。`cost_gate` 公式 `EV = atr × conf × qty` 把 ATR（range）誤用為 directional edge，高估 ~13×。Phase 5 從 W16-18 提前到 P0 立即啟動。

**PH5-WIRE-0** `75d8f36`：`intent_processor.rs` cost_gate 加入 `COLD_START_DAMPENING = 0.2`，ATR-based EV 降至 ~2.6×；5 個 Rust 測試 ATR 值調整（500→2000 BTC, 1.5→5.0 SOL）；769 pass。

**PH5-DL-2+JS-1** `1e5a288`：新建 `program_code/ml_training/realized_edge_stats.py`（FIFO pair, per-(strategy,symbol) mean_net_bps）+ `james_stein_estimator.py`（正部 JS 收縮，UPSERT `learning.james_stein_estimates`，原子 JSON 快照 `settings/edge_estimates.json`）。首跑 8 cells 全負（-6.9 to -25 shrunk bps，grand_mean -10.4 bps）→ PH5-WIRE-1 延後。

**DEAD-PY-1 P1+P3+4** `f418e2d`：13 檔案 285 行刪除 — PAPER_STORE/ENGINE dead branches、whitelist 410 stubs、RC-10/11/12 migration markers 全清。

**DEAD-PY-1 P2** `601e035`：刪除 `apply_ai_consultation()` + 路由（0 API hits 確認）+ 2 個對應 test；165 行刪。

**CFG-PERSIST-3 GUI** `6763b38`：`tab-risk.html` Position Limits 卡補入 `max_correlated_exposure_pct`（數字輸入）+ `allowed_categories`（逗號分隔文字），loadAll/savePositionSettings/Current Values 全接線；`preferred_margin_mode`/`preferred_position_mode` 延後（Rust 僅存儲，未執行邏輯）。

**WP-CLEANUP-GRAFANA-TESTS** `caf2bcc`：刪除 20 個調用不存在方法的 test（`_write_pnl`/`_write_market_tickers`/`_write_system_health`/`_write_trade_executions` 已於 ARCH-RC1 移除或重命名）；保留 10 個通過的 lifecycle/pg/loop tests；基線 21→1 pre-existing fail。

**後續**：PH5-WIRE-1 等 paper realized edge 轉正 · PH5-VERIFY-1 7d 觀察期進行中 · test_risk_view_client 1 fail 留待獨立 session · A2 NewsPipeline 等 provider 決策。

---

### ARCH-RC1 1C-4 E-Merge-4 — Guardian = RiskConfig pure derived view（2026-04-08 · commit `06742b3`）

`+90/-27` 行 · core 387 + engine 767 全綠 · 0 regression

**動機**：1C-2-F E-Merge-1/2/3 已把 paper_state.stop_config / h0_gate.config / governance.risk.thresholds 拉成 RiskConfig 派生視圖，但 Guardian 仍持有「3 個 RiskConfig 鏡像欄位 + 2 個 operator-invisible 私有欄位 + 1 個 dead 欄位」的混合結構，apply_risk_snapshot 必須走 RMW 保留私有欄位。E-Merge-4 收尾這個歷史尾巴，讓 Guardian 完全變成 RiskConfig 的純派生視圖。

**改動**：
- `openclaw_core/src/guardian.rs`：
  - 刪除 dead 欄位 `max_correlation`（grep 全 workspace 確認 review() 從未讀取）
  - `GuardianConfig::default()` 的 `max_leverage` 5→20，對齊 `RiskConfig::default().limits.leverage_max`
  - docstring 重寫，明示「pure derived view」契約
  - `test_leverage_over_cap_modified` 改用顯式 cap=5 不再耦合 Default 值
- `openclaw_engine/src/config/risk_config.rs`：
  - `GlobalLimits` 新增 `guardian_modification_size_factor`（default 0.5）+ `guardian_modification_leverage_cap`（default 2.0），把 Guardian「Modified」裁決參數從 operator-invisible 升級為一級 IPC-patchable RiskConfig 欄位
  - `validate()` 新增：`size_factor ∈ [0,1]`、`leverage_cap >= 1`
- `openclaw_engine/src/tick_pipeline.rs apply_risk_snapshot`：
  - **刪除 RMW 模式**（clone 既有 GuardianConfig → 覆蓋 3 欄位 → 推回）
  - 改為從 snap 直接構造全新 GuardianConfig，5 個欄位全部 1:1 來自 RiskConfig，無 Default fallback
  - docstring 重寫記錄 E-Merge-4 契約變更
- `openclaw_engine/src/event_consumer/setup.rs` 初始 Guardian seed：
  - 同步移除 Default fallback，modification_* 欄位也走 default_risk.limits

**契約變更**：Guardian 任何旋鈕的唯一真相源 = `patch_risk_config`。`update_strategy_params` 既有 IPC 路徑仍可 RMW 同樣 3 個欄位（不受影響）。

**測試**：core 360+8+19+0 = **387 passed** / engine **767 passed** / 0 regression。

---

### ARCH-RC1 1C-4 wrap QA polish（2026-04-08 · commit `9811bf3`）

post-degradation E2 + QA 雙審查雙 APPROVE 後，落 4 項 minor follow-up（item #2 demo_only spawn gating 經 operator 確認維持現狀）：
- `position_reconciler.rs` MODULE_NOTE 加 warmup→cycle1 ~30s race window caveat + spawn gating 設計決策說明
- TODO.md 6-RC-5 收緊：強制 per-symbol minQty (1.5 × `lotSizeFilter.minOrderQty`)，禁止全局魔法數
- TODO.md 6-RC-6 標記阻塞依賴 OC-3 多通道告警基礎設施
- TODO.md 新增 6-RC-9：baseline staleness 政策 + `last_fetch_ms` 欄位，6-RC-1 落地前必須完成

---

### ARCH-RC1 1C-4 — Hot-reload e2e + B2 audit-only 降級（2026-04-08 深夜）

**熱重載 e2e (`4780b04`)** — `tick_pipeline.rs` +120 行測試
- `test_arch_rc1_hot_reload_e2e_propagates_to_all_5_consumers`：建一個 RiskConfig ConfigStore → set_risk_store → replace() 模擬 IPC patch_risk_config → 跑一個 on_tick → 斷言 5 個下游消費者全部刷新
  1. `intent_processor.risk_config`（Gate 0 / cost-edge / dynamic_stop）
  2. `intent_processor.guardian_config`（P0 trade veto）
  3. `h0_gate.config`（risk-level RMW）
  4. `paper_state.stop_config`（H0-blocked fallback）
  5. `governance.risk.thresholds`（6-tier cascade SM）
- 驗證 `risk_config_version_seen` 同步推進，下次 tick 為 no-op
- 1C-4 wrap 的硬證據：tick-level hot-reload 端到端可工作，無 restart-to-apply
- engine lib 766 → 767 (+1)

**B2 audit-only 降級（commit 待加）** — `position_reconciler.rs` 重構 + `main.rs` 解線
- **降級背景**：QA + E2 審查發現原 B2 的自動 governor trigger 雙重失效：
  1. **功能性死亡**：`reason_code="reconcile_mismatch"` + `target_tier="auto_step_looser"` 都不在 `tick_pipeline.rs` 的 operator manual override 白名單內，每次觸發都被拒絕進 `governor_de_escalate_rejected` audit 分支
  2. **語義污染風險**：若擴大白名單修復 (1)，B1 `load_governor_cooldown_from_audit` 的 SQL filter 會把 reconciler 自動事件誤計入 24h operator cooldown，違反 B1「cooldown 只約束 operator 動作」的設計
- **降級內容**：
  - 刪除 `trigger_governor_de_escalate` fn + `should_trigger_governor` method + `governor_triggered` cycle flag
  - `reconcile_once` 簽名移除 `paper_cmd_tx` 參數
  - `run_position_reconciler` 簽名移除 `paper_cmd_tx`
  - `main.rs` 移除 `reconciler_cmd_tx` clone 與傳參
  - 新方法 `DriftVerdict::is_drift()` 取代 `should_trigger_governor`
- **新增 first-cycle warmup**（修 QA CV-1 cold-start orphan storm）：
  - `run_position_reconciler` 啟動序列：跳過第一次 interval tick → 一次性 `fetch_current_view` 靜默播種 baseline → 進入主循環
  - warmup 階段也支援 `cancel.cancelled()`
  - warmup REST 失敗時 baseline 留空，下一輪首次成功 fetch 會把既有持倉以 Orphan 各記一次（記錄啟動時 REST 不健康，可接受）
- **保留**：5 級漂移分類（純函數）/ V014 audit 寫入 / 30s 輪詢 / fail-open / single-trigger-per-cycle 不再需要因為已無 trigger
- **MODULE_NOTE 更新**：明示 audit-only / 與 1C-4 wrap 降級理由 / 自動收縮挪至 Phase 6
- **Phase 6 自動收縮目標規格**寫入 TODO.md（6-RC-1~8）：動作通道隔離 / V014 event_type 隔離 / 動作策略 / 自身冷卻 / 絕對 dust floor / 多通道告警 / 整合測試 / Live blocker 解除
- **Live blocker 新增**「多通道告警上線」項，B2 降級後 drift 只進 audit 必須有 operator 通知通道
- 測試調整：`major_drift_at_threshold` → `major_drift_above_threshold`（清掉混亂註釋），`verdict_governor_trigger_classification` → `is_drift_classification`
- engine lib 767 維持 0 regression

### ARCH-RC1 1C-4 B2 SHIPPED — Position Reconciler（2026-04-08 · commit `36335d7`）

**B2 — Bybit 持倉對帳器**（+484 行 / 9 unit tests / 零 migration）
- 新模組 `rust/openclaw_engine/src/position_reconciler.rs`
- 30s 輪詢 Bybit `/v5/position/list` (Linear)，與 reconciler 自持的 in-memory baseline diff
- 漂移分 5 級純函數分類（`classify()`）：
  - `Match` / `MinorDrift` (qty 變化 < 5%) → V014 audit only
  - `MajorDrift` (≥ 5%) / `Orphan` (Bybit 有/baseline 無) / `Ghost` (baseline 有/Bybit 無) → V014 + governor de-escalate
- Side 翻轉（多空互換）直接判 MajorDrift，永不視為噪音
- Governor 觸發走既有 `PaperSessionCommand::ForceGovernorLooser` 通道，`reason_code=reconcile_mismatch` + `target_tier=auto_step_looser`，自動接 B1 的 24h cooldown 路徑
- **每輪只觸發 1 次** governor，避免同源漂移（單次斷線 / 手動操作）轟炸 cooldown
- Fail-open：REST 失敗 → warn + 跳本輪，baseline 保留
- V014 audit pool 可選，缺失時降級為純日誌
- main.rs spawn gated on `Some(shared_client)`；paper-only / no-REST 模式整體跳過
- **零 migration** — V014 `engine_events` 已能裝 `reconcile_{minor_drift,major_drift,orphan,ghost}` 4 種 event_type
- 9 unit tests：`classify()` 7 種路徑 + `build_view_map()` 過濾空倉 + `should_trigger_governor()` 分級
- 測試基準：engine lib 757 → **766** (+9)

### ARCH-RC1 1C-4 A1+B1 SHIPPED — Governor cooldown PG 持久化 + 註釋話術同步（2026-04-08 · commits `03fee49` `e840003`）

**A1 — 註釋話術同步**（`03fee49`，11+/9-）
- 1C-3-F 物理刪除 `paper_trading_engine.py` 後，main.py + paper_trading_wiring.py 仍有 6 行「RC-10 ENGINE removed — Python PaperTradingEngine disabled」舊話術，現在不準確（不是 disabled，是 deleted）
- 統一改為 "ARCH-RC1 1C-3-F: PaperTradingEngine retired (deleted), openclaw_engine is sole engine"
- 純文字 commit，無代碼變更

**B1 — Governor cooldown PG 持久化**（`e840003`，+173 行）
- 1C-3-B-2 known limitation：operator de-escalation 24h cooldown 原本 in-memory，重啟靜默重置
- **關鍵簡化發現**：每次成功降級已經寫 V014 row（`event_type='governor_de_escalate'`, `payload.result='applied'`），V014 已是 source of truth，**無需新 migration / 新 INSERT 路徑**
- 啟動時 query 最近一筆 applied row，若在 24h 窗口內 reseed `TickPipeline.last_governor_de_escalation_ms`
- `EventConsumerDeps` 新增 `audit_pool: Option<sqlx::PgPool>`，`main.rs` deps 構建處 `db_pool.get().cloned()`
- `event_consumer/mod.rs`：`load_governor_cooldown_from_audit()` async helper + `cooldown_ts_if_active()` 純決策函數（5 unit tests：fresh / expired / boundary / clock-skew / negative-ts）
- **fail-soft on PG unavailable / SQL error**：warn + cold-start cooldown。其他守衛（whitelist / step / 5-min hold / CB+MR lockout）持續生效，這只是 defence-in-depth
- 測試：engine lib **752 → 757** (+5) · core 387 · types 27 · 0 regression
- 原 scope agent 估 ~125 行（建議新 V015 migration），實際發現 V014 已可用，最終 173 行含完整中英雙語註釋與測試

**1C-4 進度**：A1 ✅ · B1 ✅ · A2 NewsPipeline scheduler 延後（grep 發現生產代碼從未實例化 NewsPipeline，需先決 4-09 router 接入策略，scope 從 ~50 膨脹到 ~120-200 行）· **B2 Position Reconciler 為下一步**（trading.position_snapshots + Bybit `/v5/position/list` 對帳，scope agent 已 audit 完，可直接開工）



### ARCH-RC1 1C-3-F SHIPPED — Python paper_trading_engine.py 徹底退場（2026-04-08 深夜 · commits `accf625` `8ff93e0` `de1ec69`）

1C-3 收尾終局。Rust openclaw_engine 成為 paper / demo / live 三模式唯一引擎。

**F-a Rust submit_paper_order IPC RPC**（`accf625`，engine lib 748→752）
- `tick_pipeline.rs` 新增 `PaperSessionCommand::SubmitOrder` variant + `submit_external_order()` 方法（~150 行）：檢查 paused/halted、查 latest_price + ATR、構建 OrderIntent 走 IntentProcessor 全 gate（governance/Guardian/Kelly/P1/cost gate）、instrument-aware 取整、apply_fill、stats 累計、推 recent_intents/recent_fills、發 trading_tx Intent+Fill。Order ID `ext-{symbol}-{ts_ms}`
- `event_consumer/handlers.rs` 加 SubmitOrder 分支（解析 side 字串、confidence 默認 1.0、snapshot.force_write）
- `ipc_server.rs` 加 `submit_paper_order` JSON-RPC dispatch + 5s timeout
- 4 個 e2e 測試：happy path / paused rejected / no price rejected / invalid side rejected

**F-b shadow_decision_builder.py rewire 走 IPC**（`8ff93e0`）
- `ipc_client.py` 加 `submit_paper_order` async wrapper
- `shadow_decision_builder.py` 砍 `from .paper_trading_engine import (...)`，常量內聯，`ShadowDecisionConsumer.__init__` 改吃 `EngineIPCClient`，`consume()` 改 async（await get_paper_state + await submit_paper_order），刪 `_engine.store.mutate(...)` 影子審計 append
- `layer2_engine.py` line 669 改 `await self._shadow_consumer.consume(...)`
- `layer2_routes.py` 移除 `from .paper_trading_routes import ENGINE as PAPER_ENGINE, SHADOW_CONSUMER`，加 `_build_shadow_consumer()` helper（lazy resolve EngineIPCClient.get_singleton）

**F-c/d/e Python 紙盤引擎刪除 + wiring 清理 + 回歸**（`de1ec69`，-8915/+16）
- 刪 `app/paper_trading_engine.py` 2248 行
- `paper_trading_routes.py` 內聯 `DEFAULT_INITIAL_BALANCE_USDT = 10_000.0`
- `paper_trading_wiring.py` 刪 `PaperStateStore`/`PaperTradingEngine` import；`PAPER_STORE = None` stub；`ENGINE = None` 維持原狀（main.py / governance_routes.py / strategy_wiring.py 三個 ENGINE 消費者全部已 `is not None` 短路）
- 刪 13 個 paper-engine-specific test：test_paper_trading / test_paper_trading_engine_edge / test_shadow_decision{,_builder} / test_batch10_learning_oms / test_batch12_e2e_smoke / test_winrate_param_fixes / test_integration_phase{7,9,11} / test_integration_governance / local_model_tools/tests/test_session9_fixes
- conftest.py PAPER TRADING ENGINE FIXTURES 整塊刪除（4 fixtures）
- 7 個之前疑似有依賴的 test（test_batch11_executor_exchange / test_edge_filter_integration / test_u05 / test_executor_agent_unit / test_grafana_data_writer / test_evolution_engine / test_pipeline_bridge*）審計後確認只有 mock 註釋無真實 import，無需動
- pytest 回歸：2944→2694 passed / 22→21 fail / **0 regression**（-250 = 13 個被刪測試檔；-1 = 其中一個原本在 22 個 baseline fail 內）

**留尾移交 1C-4**：Position Reconciler / Governor cooldown PG 持久化 / NewsPipeline run_once / 熱重載 e2e 驗收 / E-Merge-4 / 註釋級殘留 sed 清理（main.py / tab-governance.html "RC-10 ENGINE removed" 等舊話術已不再準確）/ E2+E4+QA。

---

### Session ARCH-RC1 1C-3-E F-mini SHIPPED — paper engine 死代碼前置清理（2026-04-08 晚 · commits `d8fb7f2` + 待 commit）

緊接 4/8 PM 1C-3-D session 之後的同日延續 session。目標：開 1C-3-E，盡量收掉 paper_trading_engine.py 死代碼。

**完成項**
- **step 1** (`d8fb7f2`): `bridge_core.py:294` 移除 `self._engine.risk_manager._price_tracker` 死引用 — 1C-3-D 之後 Python RiskManager 是 53 行 RiskViewClient shim 沒有 `_price_tracker`，ATR 由 Rust 引擎權威；此分支因 ENGINE = None since RC-10 已不可達，原本若被觸發會 AttributeError
- **step 2 自動完成**: 6 個 1C-3-C skipped `TestRiskRoutes` 測試在 `test_risk_manager.py` 內，1C-3-D aggressive cull 已整檔刪除
- **F-mini 三小修**（待 commit）：
  - `paper_trading_routes.py` 移除 4 個 dead imports：`PaperStateStore` / `PaperTradingEngine` / `ShadowDecisionFileFeeder` / `build_shadow_decision`（檔內從未使用，僅 `DEFAULT_INITIAL_BALANCE_USDT` 與 `ShadowDecisionConsumer` type-hint 仍消費）
  - `risk_routes.py::unhalt_session` 移除 deprecated `PAPER_STORE.mutate` 並行寫 (1C-3-C 留下的過渡)：Rust ConfigStore + paper_state 現在是 session_halted 唯一權威
  - `paper_trading_wiring.py::_h0_db_probe` 從 `PAPER_STORE.read()`（loads + JSON-decodes 整個 snapshot）改為 `os.stat(_paper_state_path)` — 同樣偵測磁盤 hang，成本一個量級降低 + 解耦待退場的 PaperStateStore

**Rust engine readiness audit**（B-full 前置調研）
為決定是否能徹底刪 `paper_trading_engine.py`，跑了一個 Explore agent 對 Rust 引擎做 13 capabilities 完整性審計：
- ✅ Session lifecycle (7-state) / Order mgmt / PnL / Tick pipeline / Stop manager (hard/trailing/time) / Risk gates (Gate 0 + on-tick) / Demo sync / Persistence / OMS 11-state / Reconcile / Governance lease — **全部 covered**
- ⚠️ State exposure: `get_paper_state` + `get_latest_prices` IPC RPC **已存在** (ipc_server.rs:422-428 via `handle_snapshot_field`)，走 5s debounced snapshot file
- ⚠️ Shadow decision feed: `shadow_decision_builder.py::ShadowDecisionConsumer.consume()` 仍依賴 `PaperTradingEngine.submit_order()`，layer2_engine.py:639,661,669 wire 著但 Layer 2 整體待儀表板就緒才啟動
- **結論**：Rust 引擎已足夠 paper / demo / live 三模式，但 Layer 2 重接 + Rust 補 paper-side `submit_order` RPC 是 1C-3-F 必須的前置工作

**1C-3-F 範圍重估**（從 audit 的 3.5h 修正為 ~5h）
原因：layer2_engine 經 `shadow_decision_builder` 走 paper engine，雖然 Layer 2 還沒啟動，但代碼路徑 wire-ready，刪 paper_trading_engine.py 會破壞它。F-full 必須先 (a) Rust 補 IPC，再 (b) shadow_decision_builder 改走 IPC，最後 (c) 才能刪 2248 行主檔 + 14 個依賴測試。決定拆 session：今天 F-mini 收掉 0 風險的 dead code，F-full 留下個 fresh context window 做。

**測試**
Python control_api: **2944 passed / 22 failed / 1 skipped** — 與 baseline byte-for-byte 一致 / 0 regression caused
Rust 未動 / engine lib 748 持續綠燈

**下個 session 接手指引**
1. 讀 CLAUDE.md §三 1C-3-E F-mini SHIPPED 條目 + 1C-3-F 留尾 5 步
2. 第一步：盤點 Rust 是否已有 paper-side submit_order IPC RPC（grep `submit_order` in `event_consumer/handlers.rs` + `tick_pipeline.rs` PaperSessionCommand enum）
3. 沒有的話 → F-a: 在 `tick_pipeline.rs` 加 `PaperSessionCommand::SubmitOrder { ..., response_tx }` + handlers.rs handler + ipc_server.rs dispatch + tests（template: `GetRiskRuntimeStatus` lines 107-114 / ipc_server 1015-1040）
4. F-b: `shadow_decision_builder.py` 改 EngineIPCClient（layer2_engine.py 注入點不變，只換 consumer 內部實現）
5. F-c-d-e: 刪 paper_trading_engine.py + 14 測試 + wiring 清理 + 文檔
6. 14 個目標測試檔清單見 TODO.md 1C-3-F (c) 條目

**Commits**
- `d8fb7f2` chore(python): 1C-3-E step 1 — drop bridge_core ATR bootstrap dead ref
- 待 commit: F-mini 三小修

---

### Session ARCH-RC1 1C-3 全部 SHIPPED — Python RiskManager 收編完成（2026-04-08 · commits `f8772c0` `a1cf772` `144f46f`）

接續 4/7 斷網 session（已撈回 worklog `docs/worklogs/2026-04-08--session_resume_notes.md`）。本 session 完成 E2 review fix + 1C-3-D 主體 + 文檔同步。

**E2 review** (`docs/audits/2026-04-08--e2_review_1c3_bbc.md`):
- 1C-3-B (`8447fbf`) APPROVED_WITH_NITS · 1C-3-C (`c6fcd13`) APPROVED_WITH_NITS · 1C-3-B-2 (`9f46b06`) CHANGES_REQUIRED
- M-1 (test gap) · M-2 (audit hole) · N-5 (payload shape) 三項 fix 必做

**1C-3-D M-1** (`f8772c0`, +220 行 / engine 740 → 748):
- `event_consumer/tests.rs` 加 8 個 real guard tests using `handle_paper_command` + `tokio::sync::oneshot::channel()` + `rx.blocking_recv()`
- 覆蓋: reason_code 白名單 reject / 單步 reject / 24h cooldown reject / CB+MR lockout / valid path
- 之前 governor manual override 守衛只有 path-level coverage，現在端到端 8 條測試

**1C-3-D M-2 + N-5** (`a1cf772`):
- `spawn_governor_audit_row` 簽名重構：5-positional `(from_tier, to_tier, reason_code, notes, source)` → `(audit_pool, event_type, payload: serde_json::Value)`，調用點直接構造 payload，型別更乾淨
- `Ok(Ok(Err(e)))` rejection branch 也寫 V014：新 event types `governor_escalate_rejected` / `governor_de_escalate_rejected`，payload 含 `result: "applied"|"rejected"` + `error` 欄位
- 之前 audit 只記錄成功的 override，rejected 的（白名單 / 單步 / cooldown / lockout 拒絕）完全沒記錄 → 操作員無從看出 governor 守衛被觸發過

**1C-3-D 主體** (`144f46f`, +46 / -7882 = 淨 -7836 / 14 files):
- approach A: aggressive cull
- `risk_manager.py` **1633 → 53 行** (-97%)：
  - 只剩 `REGIME_TIME_MULTIPLIERS` 常量（bridge_stats / test_winrate_param_fixes 仍消費）
  - `RiskManager(RiskViewClient)` 薄子類 — 建構不需 ipc_client，所有 deprecated 行為走 RiskViewClient 內建 `_warn_deprecated_once` no-op stub
- `paper_trading_wiring.py` 移除三個 RiskManager 注入點 (`set_portfolio_risk_control` / `set_governance_hub` / `set_change_audit_log`) — 都是 RiskViewClient no-op，移除後更乾淨
- 刪除 9 檔 ~6900 行純 Python 風控/H0/Engine 測試（邏輯已 100% 在 Rust 748 tests 覆蓋）：
  - `test_risk_manager.py` (1494) + `test_risk_manager_edge.py` (174)
  - `test_h0_gate.py` (1276) + `test_h0_gate_cooldown_integration.py` (268)
  - `test_paper_trading_engine.py` (989) + `test_paper_trading_engine_inverse.py` (678)
  - `test_trailing_stop_cost_constraint.py` (301)
  - `test_integration_phase5.py` (648) + `test_integration_phase8.py` (378)
- `conftest.py` 移除 4 個 fixtures: `paper_engine_with_risk` / `risk_manager` / `global_risk_config` / `category_risk_config`
- `test_integration_phase2.py::test_portfolio_risk_control_injected` 重寫為 `test_portfolio_risk_control_present`（驗證 wiring singleton 仍存在，不再驗證 RiskManager 注入）

**Regression**: Python 2944 passed / 22 failed / 1 skipped — 22 failures **與 baseline byte-for-byte 一致**（已 git stash 對照驗證），**0 regression caused by 1C-3-D**。22 個 pre-existing failures: 19× test_grafana_data_writer (mock spec issue) + test_paper_trading::test_session_start_via_api (401 auth) + test_symbol_category_registry::test_is_stale_initially (stale check)。Rust 748 持續綠燈（本 session 沒動 Rust workspace 檔案，僅在 M-1/M-2 commits 修改 ipc_server.rs + event_consumer/tests.rs）。

**風控收編軌跡終局**:
```
1A 前：     Python RiskManager (1633) + 6 套並行 = 7 套
1A 後：     Python RiskManager (1633) + 4 套
1C-1 後：   Python RiskManager (1633) + 1 套權威（RiskConfig 13 sub-struct）
1C-2-F 後： 1 Config 權威 + 5 engines 同步熱重載
1C-3-D：    Python RiskManager → 53 行 RiskViewClient shim（Python 風控核心徹底退場）
```

**下一個 session 起點**: 1C-3-E 留尾
- `paper_trading_engine.py` ~15 個 dead `engine.risk_manager.X` 路徑（ENGINE = None since RC-10 的 disabled engine 自身清理，不影響 live）
- `bridge_core.py:294` `self._engine.risk_manager._price_tracker` 死引用
- 6 個 1C-3-C 留下的 skipped `TestRiskRoutes` 重寫
- `PAPER_STORE.mutate` 拆分：session_halted 不再 Python 並行寫，從 Rust snapshot 派生
- 評估是否進一步刪 `RiskManager` 子類符號，讓 paper_trading_wiring 直接 import RiskViewClient

**1C-4 待做**: Position Reconciler · Governor tier override cooldown PG 持久化（live 前必做，1C-3-B-2 known limitation）· NewsPipeline run_once 60s spawn · 熱重載 e2e 驗收測試 · E2 + E4 + QA Audit。




---

> 2026-04-07 及更早的歷史記錄已歸檔至 `docs/archive/2026-04-12--changelog_archive_pre_0408.md`。
