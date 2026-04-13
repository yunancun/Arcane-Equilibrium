# CLAUDE_CHANGELOG.md — 開發歷史歸檔

> 從 CLAUDE.md 遷出的 Wave/Sprint/Batch 歷史記錄。新 session 不需要讀此文件，僅供回顧歷史時查閱。
> 最後更新：2026-04-13

### EDGE-P2-1 Close Fill Labeling Fix（2026-04-13）

**Root cause**: `emit_close_fill()` unconditionally wrapped ALL close fills with `strategy_name: format!("risk_close:{reason}")` — including strategy-driven closes. This inflated the apparent risk-forced exit count (327/435 in demo), making it impossible to distinguish strategy exits from risk checks. **Fix**: `close_tag` parameter is now written directly as `strategy_name` — callers pass prefixed tags: `strategy_close:*` / `risk_close:*` / `stop_trigger:*`. order_id changed from `risk_close_{em}_…` to neutral `close_{em}_…`. `realized_edge_stats.py` updated to recognize all three prefixes. Diagnostic SQL script added: `helper_scripts/db/close_fill_analysis.sql`. 5 files changed. E4: 1091 lib + 33 e2e = 1124 Rust · 0 fail.

### G-SR-1 Session 7 — C1-C2 Agent 接線 + PM 端到端驗收 COMPLETE（2026-04-13）

**C1 Analyst wiring** — `_handle_analyst()` 從 stub 升級為接入 AnalystAgent.analyze_trade()：IPC trade_data → TradeRecord 構建 → asyncio.to_thread() L1 分析 → 返回 strategy_metrics + strategy_rankings；agent 不可用時 stub fallback。**C2 Scout wiring** — `_handle_scout()` 接入 ScoutAgent.get_recent_intel()/get_recent_alerts()：IntelObject/EventAlert 序列化為 JSON-safe dicts + symbol 過濾；agent 不可用時 stub fallback。**Injection** — `create_ai_service_listener()` 新增注入 ANALYST_AGENT + SCOUT_AGENT from strategy_wiring（fail-open）。conductor_evaluate 仍為 stub（W23+ R-06）。MODULE_NOTE 精簡（bilingual 合併 -36 行）。ai_service.py 1080→1195 行（+115 net，MODULE_NOTE 精簡抵消新增）。**PM 驗收 6/6 PASS**：(1) PersistenceTracker 3 策略 check()/clear()/Close 免檢 (2) Grid 趨勢冷卻 ADX+Hurst 1x-6x (3) Confluence 4 分量 65 分 + qty 調整 (4) Strategist DB→IPC→Ollama→validate 全鏈路 (5) Guardian L1 分類+MessageBus 中繼 (6) C1-C2 注入+真實調用+fallback。**G-SR-1 計劃全部完成**（7 Sessions，Phase A+B+C）。E4: 1086 lib + 33 e2e = 1119 Rust · 2852 Python · 0 fail。

### G-SR-1 Phase B Session 6 — B2+B3+B4 Agent 真實接線（2026-04-13）

**B2 ai_service.py stub→real wiring** — `_handle_strategist()` 接入 Ollama param tuning（build prompt from metrics + current_params + param_ranges → JSON param recommendations，asyncio.to_thread 非阻塞）；`_handle_guardian()` 接入 Ollama event classification（risk_level low/medium/high/critical + assessment，informational only NOT trade blocking）；OllamaClient lazy singleton + fail-closed（unavailable→retain current params / input severity）。**B3 Rust IPC enhancement** — `evaluate_cycle()` 移動 `fetch_current_params()` 至 IPC 前，`current_params` + `param_ranges` 包含在 `strategist_evaluate` 負載，Python 可基於上下文做更好推薦。**B4 Guardian L1 MessageBus relay** — high/critical 事件通過 MessageBus 中繼給 Strategist（fail-open）；`create_ai_service_listener()` 注入 `MESSAGE_BUS` from strategy_wiring。ai_service.py +350 行（730→1080）；strategist_scheduler.rs +22 行（692→714）。B-E2 10/10 PASS · B-E4 1083+33=1116 Rust · 2852 Python · 0 fail · B-E5 PASS。

### G-SR-1 Signal Tightening Phase A Session 1+2（2026-04-13）

**Phase A S1: A0 基礎模組提取** — `grid_helpers.rs` 純函數提取（build_linear_levels/build_geometric_levels/nearest_grid_idx/compute_ou_step/rebalance）+ `confluence.rs` 共享模組（PersistenceTracker + compute_score 4 分量 65 分制 + score_to_qty_pct 5 段平滑插值 + ConfluenceConfig 三配置 trend/reversion/breakout）。

**Phase A S2: A0-c + A1 + A2 + A3** — A0-c：3 策略 TOML Params struct 加 confluence 字段（serde(default) backward compat）+ build_confluence_config() + StrategyFactory 接線 + R4-7 update_params rebuild。A1：PersistenceTracker.check() 時間制過濾器接入 ma_crossover/bb_reversion/bb_breakout entry path（MA/BBR 120s, BBB 60s），close 免檢 + clear() 清理。A2（提前實施）：weighted confluence scoring（trend 25/20/12/8, reversion 15inv/30/10/10, breakout qty-only 10% 底線），冷啟動 adx&&rsi None→全倉退化，min_notional guard。A3：Grid trend-adaptive cooldown（ADX 60% + Hurst 40%, 1x-6x 動態倍率，3 TOML 參數）。修復：bb_reversion 測試加 ADX 數據、dead `make_entry_intent()` 刪除、stress test pub 可見性、BbBreakoutParams TOML struct 補齊。Engine lib 934→1024 tests（+90），e2e 29→33（+4）= 1057 total, 0 fail。

### 04-12 審計修復 Wave 2：14 角色報告逐一核實 + 代碼修復（2026-04-12）

**A3 GUI 可用性審計全修** (commit `fd0bc45`)：CRITICAL×2 + MAJOR×14 + MINOR×18 + SUGGESTION×2 一次性全修。關鍵：Live/Demo/Paper 持倉「平倉」按鈕確認流程 + 空狀態提示 + 響應式間距 + 按鈕排列一致性。

**QC 量化審計全修** (commit `e03421f`)：Session 3.3+3.3b — 12 hardcoded 參數移至 TOML + 7 risk gap 修補 + 10 action items 全部解決。

**P2 FIX-08 超限文件拆分** (commit `50d7a4b`)：12+ 超過 1200 行硬上限的文件拆分（governance_routes / strategy_ai_routes / paper_trading_routes / strategy_read_routes / strategy_wiring / experiment_routes / live_session_routes / evolution_routes / backtest_routes）。

**P2 FIX-23/34/35/57** (commit `0de58bb`)：FundingArb 策略註冊 + outcome backfiller DDL + budget sync 修復。

**E3+CC 安全/合規修復** (commit `f8685bf`)：5 fixes + 2 報告更新 — Cookie secure flag + HMAC edge cases + error disclosure。

**E5+MIT 報告核實** (commit `c73a3f2`)：5 code fixes + 2 report corrections — 補漏 push_capped 缺失 + budget tracker sync。

**E5 審計收尾** (commit `6e2a01e`)：3 remaining items implemented + P-08 test fixed。

**FA 審計修復** (commit `d16ed08`)：3 orphan Rust files 刪除（batch_order_manager/leverage_token_client/spot_margin_client）+ handlers.rs 拆分 handlers_config.rs + PIPELINE_BRIDGE 死碼清理。

**AI-E 審計報告校正** (commit `4d427f5`)：18 inaccuracies corrected（3 Serious / 8 Medium / 7 Light — 均為報告錯誤非代碼 bug）。

**BB Bybit API 審計驗收** (commit `50a4b1e`)：7/7 P1 全部關閉 — 最終核實 worklog。

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

---

> **歸檔**：2026-04-08 ~ 04-09 條目已移至 `docs/archive/2026-04-13--changelog_archive_0408_0409.md`。
> 2026-03-30 ~ 04-07 條目見 `docs/archive/2026-04-12--changelog_archive_pre_0408.md`。

