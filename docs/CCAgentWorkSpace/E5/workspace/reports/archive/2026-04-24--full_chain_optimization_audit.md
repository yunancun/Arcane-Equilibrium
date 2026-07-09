# E5 全程序鏈優化審計報告
# E5 Full-Chain Optimization Audit Report

**日期 / Date**: 2026-04-24
**範圍 / Scope**: Rust `rust/openclaw_engine/` + Python `program_code/` + `helper_scripts/`
**基準對比 / Baseline**: 2026-04-01 optimization_audit（54 問題）+ 2026-04-12 E5-Wave（20 FIXED）
**覆蓋文件 / Files covered**:
- Rust 應用代碼（非 tests）: 55 個 `.rs` 文件
- Python app: 53 個 `.py` 文件（control_api_v1/app）
- Python ai_agents + helper: ~30 個 orchestration/maintenance scripts
- 共計 ~138 個文件；engine lib 約 49k 行 + Python app 約 37k 行 + helper ~11k 行

---

## 執行摘要 / Executive Summary

**重大狀態更新（相對 2026-04-01）**：
- ✅ **Python main_legacy.py 債已解**：5,113 → **468 行**（DEDUP-PY-RUST Tier B Wave A-D 2026-04-16~23 完成，54 routes 分至 5 sibling legacy_routes）
- ✅ **Python f-string logger 大幅改善**：192 → ~47（多在 docs / archived reports；生產代碼 1 處）
- ✅ **int(time.time()*1000) 內聯大減**：156 → 30（全部集中在 `ai_agents/bybit_thought_gate/`）
- ✅ **Rust tick_pipeline/mod.rs**：2274 → 1035 行（TICK-PIPELINE-MOD-SPLIT-1 拆分完成）
- ⚠️ **新熱點浮現**：`event_consumer/mod.rs::run_event_consumer` 單 async fn **1,695 行**（project 最大單 fn，遠超先前 `_process_pending_intents` 462 行紀錄）
- ⚠️ **Rust 硬上限違反新增**：7 檔 ≥1200 行（§三 §七.結構約定 §1200 硬上限）

**優先級分佈 / Priority distribution**:

| 優先級 | 數量 | 覆蓋類別 |
|--------|------|---------|
| **P0 – 硬違反（≥1200 行或結構性阻塞）** | 8 項 | 7 Rust 文件超限 + 1 巨型 async fn |
| **P1 – 性能熱點** | 10 項 | clone / 鎖粒度 / 增量計算 / 並行化 |
| **P2 – 可讀性 + 精簡** | 10 項 | 命名 / 注釋 / 重複代碼 / 魔法數 |

**測試基線**：engine lib 1980 / 0 failed（2026-04-24 P1-11 audit 收尾後）+ bin 38。pytest 2996（最後刷新 2026-04-22）。本報告不觸代碼，不動基線。

---

## 一、精簡 / Code Simplification — Top 10

### [P0] S-1: `rust/openclaw_engine/src/main.rs` **2,062 行 / 3 個頂層 fn**
**位置**: `rust/openclaw_engine/src/main.rs:1-2062`
**結構**:
- `fn main()` 136 行（同步 runtime 啟動 + PG 初始化 + auth 驗證）
- `async fn async_main()` 行 234-？（多個 spawn + relay task + pipeline builder）
- `async fn run_pipeline_crash_only<F>()` 60-？

**問題**：§七「1200 硬上限」明確禁止。`async_main` 混合了 scanner config 載入、SymbolRegistry、Relay task、edge_estimates 初始化、pipeline 裝配、audit pool、cancel wiring；9 個不同職責。
**建議**: 拆為 `bootstrap/{scanner,pipeline,audit,relay,panic_guard}.rs` sibling module；`main.rs` 縮至 <400 行只做頂層編排與 runtime 構造。
**預估收益**: 可讀性大幅提升 · 編譯增量建構時間下降 · 單元測試覆蓋 scanner 啟動/pipeline 裝配各自獨立
**風險**: 中（移動大量 `Arc<T>` 參數，需確保 FnOnce closure 所有權正確）

---

### [P0] S-2: `rust/openclaw_engine/src/event_consumer/mod.rs` **1,762 行 / 1 巨型 async fn (`run_event_consumer` 1,695 行)**
**位置**: `event_consumer/mod.rs:34-1728`
**結構**: `pub async fn run_event_consumer(deps: EventConsumerDeps)` 吃 ~40 個依賴、啟 main select loop、內聯處理 MarketData/Trading/Control/Execution 多個事件分類。已有 sibling `dispatch.rs` / `governor_cooldown.rs` / `paper_state_restore.rs` / `setup.rs` / `types.rs` 但主函式沒拆。
**問題**:
- **project 最大單 async fn 紀錄**（1695 行 > 2026-04-01 `_process_pending_intents` 462 行）
- `select!` macro 內嵌多個 match arm，每 arm 100-200 行，嵌套深度 ≥6 層
- 鎖持有範圍不明確（部分 `.await` 點跨 `config.get()` 與 trading_tx 送出）
**建議**: 抽 `consumer_loop.rs` 持 main `select!`；每個事件分類拆 `handlers/{market,trading,control,execution}.rs`（已有 `handlers/` 目錄但覆蓋不全）。目標：`run_event_consumer` 本體 ≤200 行，純粹做 `EventConsumerDeps` 解構 + loop 調度。
**預估收益**: 維護性大幅提升 · regression 風險可控（保持 select! 語意不變）· 單測可針對每類 handler 獨立寫
**風險**: 高（async 所有權/生命週期約束 + `select!` 必須在同一 fn 中；需仔細切分共享 `tokio::sync::mpsc::Receiver<_>`）

---

### [P0] S-3: `rust/openclaw_engine/src/instrument_info.rs` **1,975 行**
**位置**: 73 個 fn，`impl InstrumentInfoCache` 區塊 286-750（約 464 行，單一 impl 內多達 15+ 方法）
**問題**: single-struct 的巨型 `impl` 塊，方法職責混合（fetch_symbols / parse / cache lookup / inflight dedup / refresh scheduler）。
**建議**: 拆 `instrument_info/{cache,fetch,parse,inflight}.rs`；`InstrumentInfoCache` 保留在 mod.rs 內 <300 行只做狀態與 pub 接口。
**預估收益**: 每個 submodule 獨立測試；parse_instrument_item / decimal_places_from_step 等純函數可輕易 property-test
**風險**: 低（struct 接口不變，僅拆 impl 方法到不同文件）

---

### [P0] S-4: `rust/openclaw_engine/src/bybit_rest_client.rs` **1,725 行**
**位置**: 67 個 fn，1 個巨型 client struct + 眾多 endpoint 方法
**問題**: 單一 `BybitRestClient` impl 混合 spot margin / position / order / wallet / instrument 多類 endpoint；每類自成完整 sub-API。
**建議**: 拆 `bybit_rest_client/{client,spot_margin,position,order,wallet,instrument}.rs`；每檔一類 endpoint。
**預估收益**: 單測可 mock 特定 API 類別；升級 v5→v6 時爆炸半徑受限於 1 個子文件
**風險**: 中（60+ call-sites 全項目；建議保 public re-export 相容）

---

### [P0] S-5: `rust/openclaw_engine/src/order_manager.rs` **1,554 行 / 1 個 174 行 fn (`as_str` 估計是 match arm 群)**
**位置**: 55 個 fn，L108 `as_str` 174 行
**問題**: 174 行的 `fn as_str()` 必然是 enum → string 的 match 表，違反可維護性（新 variant 需兩處改）。
**建議**: 用 `strum::EnumString` / `strum::Display` derive 消除 match；巨型 enum 本身建議按職責拆（Order state vs Order operation）。
**預估收益**: ~200 行 boilerplate 消除；新 variant 只需改 enum 定義
**風險**: 低（derive macro 行為確定）

---

### [P0] S-6: `rust/openclaw_engine/src/startup.rs` **1,377 行 / `build_exchange_pipeline` 401 行**
**位置**: `startup.rs:471-872`
**問題**: 單 async fn 混合 authorization verify / WS client / Intent processor / Position reconciler / PipelineSlot 構造 / task spawn 多職責。
**建議**: 拆為 `startup/{auth_gate,ws_bootstrap,pipeline_assembly,task_supervisor}.rs`
**預估收益**: Live gate 驗證可獨立單測；spawn 邏輯從 business logic 解耦
**風險**: 中（大量 `Arc<T>` + `CancellationToken` 線需維持語意）

---

### [P0] S-7: `rust/openclaw_engine/src/paper_state/resting_orders.rs` **1,367 行**
**位置**: resting order 匹配引擎
**問題**: 單檔混合 maker queue + tick matching + PostOnly reject + TWAP 邏輯
**建議**: 拆 `resting_orders/{queue,match_engine,post_only,twap}.rs`
**預估收益**: 每層邏輯可獨立測；match_engine 是熱路徑，獨立文件更易性能調優
**風險**: 低（paper 引擎隔離，測試套件已綠）

---

### [P0] S-8: `rust/openclaw_engine/src/config/risk_config.rs` **1,328 行**
**位置**: RiskConfig + 所有子配置 struct (ExitConfig / DynamicRiskConfig / HaltSessionConfig / ...)
**問題**: 所有 risk 子結構擠在一檔；新加 config 節導致衝突風險高。
**建議**: 拆 `risk_config/{mod,exit,dynamic,halt_session,budget_share,...}.rs`；mod.rs 只留 top-level `RiskConfig` struct + validate。
**預估收益**: 3E-ARCH 三引擎的 risk config 差異審查更清晰
**風險**: 低（serde derive 可保持 top-level TOML schema 不變）

---

### [P1] S-9: `rust/openclaw_engine/src/tick_pipeline/on_tick/helpers.rs` **1,182 行 / 接近 1200 硬上限**
**位置**: on-tick 輔助函數集合
**問題**: 距離硬上限只有 18 行緩衝；下一波改動極可能撞牆。
**建議**: 預先拆 `on_tick/helpers/{feature_build,gate_eval,logging}.rs` 三子模組，趁尚未觸頂時拆分。
**預估收益**: 防止下輪工作觸碰 1200 行導致緊急拆分
**風險**: 極低（純 fn 集合，無狀態依賴）

---

### [P1] S-10: Python `live_session_routes.py` **1,449 行 / 30 fn**
**位置**: `program_code/.../app/live_session_routes.py`
**問題**: 單文件擠了 live 全部 endpoint（authorization / reconcile / contraction monitor / emergency_stop）+ 後台 monitor loop `_live_contraction_monitor` 130 行。
**建議**: 拆 `live_session/{routes_auth,routes_reconcile,routes_emergency,monitor_contraction}.py`；遵循已完成的 `legacy_routes/` 拆分範式。
**預估收益**: routes 層一致性；monitor loop 可獨立 unit test
**風險**: 低（主 app 已用 `register_*_routes(app)` 聚合器模式）

---

## 二、性能 / Performance — Top 10

### [P1] P-1: `run_event_consumer` 鎖粒度不明 + `select!` 內跨 await 呼叫 `config.get()` 的時機
**位置**: `event_consumer/mod.rs:34-1728`
**問題**: 1,695 行 fn 內部 `config.get()` 呼叫散落各處；難以確認 ArcSwap 原子讀是否能常駐 stack local。每條 event 處理路徑重新讀 config，存在 cache 失效重跑 validate 風險。
**建議**: 拆 fn 後，每個 handler 入口讀一次 `cfg_snapshot` 並用引用傳遞；避免 deep call 中重複呼叫 `config.get()`。
**預估收益**: hot loop 少 10-20 次原子操作/tick · 緩存 friendliness 提升
**風險**: 低（ArcSwap 語意本就 snapshot；只是代碼組織）

---

### [P1] P-2: `startup::build_exchange_pipeline` 內 60+ 個 `await` 串行（可部分並行）
**位置**: `startup.rs:471-872`（async fn 內 60 + await sites）
**問題**: authorization verify → WS client start → PositionReconciler fetch → IntentProcessor init 多為獨立 I/O，當前串行。
**建議**: 用 `tokio::try_join!` 並行 authorization load + instrument fetch + position fetch 三個獨立 bootstrap；estimated 啟動時間 -30~50%。
**預估收益**: engine 啟動/restart-rebuild 快 3-5 秒
**風險**: 中（需確認 PositionReconciler 對 instrument cache 的依賴順序）

---

### [P1] P-3: `.clone()` 熱路徑統計 — tick_pipeline 模組 115 處（subdir total）
**位置**: `tick_pipeline/` 全部
**樣本分佈**:
- `pipeline_config.rs: 8`, `pipeline_helpers.rs: 3`, `pipeline_ctor.rs: 2`
- `commands.rs: 21`, `on_tick_helpers.rs: 11`
- `on_tick/step_4_5_dispatch.rs: 29`（最多，order dispatch 熱路徑）
- `on_tick/step_3_signals.rs: 4`, `on_tick/step_0_fast_track.rs: 7`

**問題**: step_4_5_dispatch.rs 29 處 clone 集中在 order dispatch；typical pattern 是 `symbol.clone()` / `order_intent.clone()` 前到 `try_send`。但通道已是 `Sender<OrderDispatchRequest>` 所有權轉移，部分 clone 是餵 tracing/audit log。
**建議**:
- 審視 step_4_5_dispatch.rs 29 處 clone，把 tracing 點改為借用 `%` (Debug) 或 pre-format 到 `tracing::Span`
- commands.rs 21 處多為 response channel 構建，部分可改 `Arc<str>` 取代 String clone
**預估收益**: tick hot path allocation 減 5-10% · 降低 GC（jemalloc）壓力
**風險**: 低（tracing 借用語法已驗證）

---

### [P1] P-4: 94 處 `SystemTime::now()` / `now_ms()` 混用
**位置**: 40 個 Rust 檔，其中 `ai_budget/tracker.rs: 10` 最多；`event_consumer/mod.rs: 8`
**問題**: E5-Wave 已集中 `now_ms()` helper，但 40 檔散佈；非熱路徑（tasks/supervisors）用 `SystemTime::now()` 混用。一致性缺失使後續注入 mock clock 困難。
**建議**: 全項目統一走 `openclaw_core::now_ms()`；逐步替換。非熱路徑用 `tokio::time::Instant` 也可。
**預估收益**: 測試可注入 fake clock（目前幾處測試靠 `std::thread::sleep` 低效）
**風險**: 低

---

### [P1] P-5: 94 處 `.lock().unwrap()` / `.lock().await` — 鎖熱力圖需檢視
**位置**: 12 檔 Rust
**樣本分佈**:
- `ai_budget/tracker.rs: 16` 最多
- `bybit_rest_client.rs: 7`
- `claude_teacher/applier.rs: 6`
- `news/router.rs: 5`, `tasks.rs: 4`, `ipc_server/handlers/budget.rs: 3`

**問題**: `ai_budget/tracker.rs` 16 處 lock 在 per-tick 記帳路徑；每 tick 多次獲釋鎖。若 parking_lot Mutex 粒度不當，高頻 tick 會觸發 context-switch。
**建議**:
- 審視 `ai_budget/tracker.rs` 鎖持有時間；考慮改 atomic counters 或 `DashMap`
- `claude_teacher/applier.rs` 6 處鎖若同時獲取多個，需檢查死鎖避免順序
**預估收益**: 降低 tick 延遲抖動（p99 latency 穩定性）
**風險**: 中（改鎖結構需仔細驗證 drift_detector / budget snapshot 語意）

---

### [P1] P-6: Python `ai_agents/bybit_thought_gate/` 30 個文件各有 1 處 `int(time.time()*1000)`
**位置**: `program_code/ai_agents/bybit_thought_gate/*.py` 30 檔
**問題**: 雖非熱路徑（AI governance 後台流程），但代碼一致性差，且每次 new governance decision 生成 timestamp 沒走統一 helper。
**建議**: 新建 `ai_agents/_time_utils.py` 提供 `now_ms()`；30 檔批次替換。
**預估收益**: DRY + 測試時可 monkey-patch 單一 helper
**風險**: 極低（30 處機械替換）

---

### [P1] P-7: Python `_live_contraction_monitor` 130 行 async loop — 無 backoff
**位置**: `live_session_routes.py:378`
**問題**: live contraction monitor 當前每 5 分鐘輪詢；若連續錯誤（網路 / 交易所 500）會緊湊重試。
**建議**: 加入指數退避（1s → 60s cap），避免錯誤風暴 → IP ban 風險。
**預估收益**: live 環境穩定性提升；降低觸及 Bybit rate limit 概率
**風險**: 低（monitor 非交易路徑，增量退避不影響平倉功能）

---

### [P1] P-8: Python `strategist_agent._handle_intel` **198 行**（從 2026-04-01 的 246 行縮到 198）
**位置**: `strategist_agent.py:270-？`
**問題**: 雖下降 50 行，仍接近 200 行上限；處理 intel parse / regime check / strategy match / AI consult / intent gen / weight adjust 6 個職責。
**建議**: 拆 `_parse_intel()` + `_evaluate_strategies()` + `_generate_intents()` 三子 method；每段 ≤70 行。
**預估收益**: 單測覆蓋率提升（當前整塊黑盒）
**風險**: 低

---

### [P2] P-9: `instrument_info.rs` InstrumentInfoCache 無過期清理策略證據
**位置**: `instrument_info.rs:286-750`
**問題**: `InstrumentInfoCache` 內部 HashMap 尺寸未見顯式 eviction（看到 `InflightEntry` dedup 但不見 cache eviction）；若 scanner 持續輪替 symbols，cache 可能只增不減。
**建議**: 確認（本次不寫碼）是否已有 LRU / TTL；若無，加 `evict_stale_after(ttl: Duration)`。2026-04-01 的 `truth_source_registry / experiment_ledger` 無界 dict 問題仍適用於此。
**預估收益**: 防止長期運行（數月）memory 緩慢增長
**風險**: 低

---

### [P2] P-10: `event_consumer/mod.rs` 8 處 `.lock()` + 2 處 `.await` 跨鎖呼叫潛在 deadlock 面
**位置**: `event_consumer/mod.rs`
**問題**: 1695 行 fn 內 8 處 lock，無法確認持有順序一致；deadlock 風險難以審計。
**建議**: 拆 fn 後（見 S-2），每個 handler 內 lock 範圍受限 ≤20 行，可逐一審核。
**預估收益**: 符合「P0-6 死鎖反模式」預防（見 memory `project_first_detection_deadlock_pattern.md`）
**風險**: 中（與 S-2 同一改動）

---

## 三、可讀性 / Readability — Top 10

### [P2] R-1: Rust `event_consumer/mod.rs` 巨型 fn 中的 `select!` 內嵌 match arm 嵌套 ≥6 層
**位置**: `event_consumer/mod.rs:34-1728` 內部
**問題**: match arm 層疊 `match msg { TradingMsg::Fill(f) => match f.kind { Open => ... match inner ... } }` pattern，讀碼認知負擔極高。
**建議**: 抽 `handle_fill(msg, ctx) -> Result<()>` 等 helper；每 helper 單一責任。
**預估收益**: 新 engineer ramp-up 時間 -50%
**風險**: 低

---

### [P2] R-2: Python `ai_service.py::_handle_guardian` 127 行 + 其他 `_handle_*` 方法（30 個 fn 總計）
**位置**: `ai_service.py:665-？`
**問題**: guardian handler 127 行處理 AI 回應 parse / validation / retry / budget check / audit write 多職責。
**建議**: 拆 `_parse_guardian_response()` + `_validate_guardian_verdict()` + `_write_guardian_audit()` 三 helper。
**預估收益**: 單測可覆蓋每段 validation
**風險**: 低

---

### [P2] R-3: Rust `strategist_scheduler/mod.rs` **1,166 行** — 接近硬上限
**位置**: scheduler 邏輯
**問題**: 單檔 1166 行，距 1200 硬上限僅 34 行緩衝。
**建議**: 預拆 `strategist_scheduler/{runtime,persist,wiring}.rs` — 已有 `persist.rs` sibling，但主 mod.rs 仍重。
**預估收益**: 防止下一波改動撞牆 → 緊急拆分
**風險**: 低

---

### [P2] R-4: Rust `strategies/bb_reversion.rs` **1,143 行** + `strategies/funding_arb.rs` **982 行**
**位置**: 策略實作檔
**問題**: bb_reversion 1143 行已超 §七 800 行警告、逼近 1200 硬上限。
**建議**: 策略按信號計算 / 入場邏輯 / 出場邏輯 三段；可拆 `bb_reversion/{mod,signals,entry,exit}.rs`。
**預估收益**: 策略 A/B 實驗 diff 更乾淨
**風險**: 低（2026-04-24 P1-11 audit 後 bb 已 well-tested，refactor 安全網好）

---

### [P2] R-5: Rust `ws_client.rs` **1,136 行** + `bybit_private_ws.rs` **1,013 行**
**位置**: WS 連線層
**問題**: 2 檔都超 1000 行；WS 是分散的重連 / ping / subscribe / parse 多職責。
**建議**: 按職責拆 `ws_{connection,ping,subscribe,parse}.rs`；WS-RETIRE-1 已證明 Rust 層能吸收 Python listener 職責，該模組將持續增長。
**預估收益**: 未來新增 private topic 影響範圍限定於 subscribe 子模組
**風險**: 中

---

### [P2] R-6: Rust `intent_processor/mod.rs` **1,100 行** + `ipc_server/mod.rs` **1,192 行**
**位置**: intent 處理 / IPC 入口
**問題**: `ipc_server/mod.rs` 1192 行，距硬上限僅 8 行緩衝；下波改動必觸牆。
**建議**: `ipc_server/mod.rs` 立即拆：把 dispatch routing 保留在 mod.rs，具體 handler 群組移至 `handlers/` 子模組（已部分拆分，但 mod.rs 仍重）。
**預估收益**: 避免下次改動引入緊急拆分
**風險**: 低（大部分 handler 已在 `handlers/` 子目錄）

---

### [P2] R-7: Rust `claude_teacher/applier.rs` **1,068 行 / 6 處 .lock()**
**位置**: `claude_teacher/applier.rs`
**問題**: apply 邏輯 + 6 處鎖持有；命名 `applier.rs` 太泛，不清楚是 apply teacher directive 還是 apply config。
**建議**: 重命名為 `teacher_directive_applier.rs` 或按功能拆 `{config_apply,param_apply,rollback}.rs`。
**預估收益**: grep-ability 大幅提升
**風險**: 低

---

### [P2] R-8: Python `governance_routes.py` **1,172 行**（2026-04-01 已 flagged，仍未動）+ `governance_hub.py` **1,014 行**
**位置**: 治理層入口
**問題**: governance_routes 負責 SM-01/02/04 + EX-04 + lease 全部 HTTP endpoint；單檔 1172 行。
**建議**: 按治理 SM 拆分 `governance_routes/{sm01_authorization,sm02_lease,sm04_risk,ex04_reconciliation}.py`。
**預估收益**: SM 獨立審計；SEC-05 類審查工作量下降
**風險**: 低（既有 legacy_routes 拆分模式成熟）

---

### [P2] R-9: Python `multi_agent_framework.py` **1,137 行** + `strategist_agent.py` **1,170 行** + `analyst_agent.py` **834 行**
**位置**: 5-Agent 代碼
**問題**: Agent 各自成檔，結構一致；但 multi_agent_framework 是 shared base class + message bus + lifecycle，應該有更好的命名/拆分。
**建議**:
- `multi_agent_framework.py` 拆 `{agent_base,message_bus,lifecycle}.py`
- 各 agent 按 `{handler,planner,audit}` 三段拆（2026-04-01 NEW-R4 的建議持續有效）
**預估收益**: 新 agent 增加時模板清晰
**風險**: 中（Agent 是 live 核心 runtime；需 E4 完整回歸測試）

---

### [P2] R-10: Helper `helper_scripts/db/counterfactual_exit_replay.py` **1,216 行**
**位置**: 單檔 1216 行，已超 §七 1200 硬上限
**問題**: counterfactual replay 單腳本，CLAUDE.md §七 1200 硬上限對 script 同樣適用（規範未明示 helper_scripts 豁免）。
**建議**: 拆 `helper_scripts/db/counterfactual/{loader,simulator,reporter}.py`；main 入口薄。
**預估收益**: replay 模組各段可重用於 Phase 4 batch 調優
**風險**: 低（腳本層非 hot path）

---

## 四、按文件熱度交叉索引

### Rust ≥1200 行硬違反（8 項 P0）
| 檔案 | 行數 | 主要責任 | 對策 |
|---|---|---|---|
| `main.rs` | 2062 | runtime + pipeline 裝配 | S-1 拆 bootstrap/ |
| `event_consumer/mod.rs` | 1762 | event loop main | S-2 拆 consumer_loop + handlers/ |
| `instrument_info.rs` | 1975 | instrument cache | S-3 拆 cache/fetch/parse |
| `bybit_rest_client.rs` | 1725 | REST API 全部 endpoint | S-4 按業務區拆 |
| `order_manager.rs` | 1554 | order 生命週期 | S-5 enum 改 derive |
| `paper_state/resting_orders.rs` | 1367 | paper maker queue | S-7 match_engine 獨立 |
| `config/risk_config.rs` | 1328 | Risk config | S-8 子配置拆 sibling |
| `startup.rs` | 1377 | pipeline boot | S-6 拆 bootstrap/ |

### Rust 1000-1200 行邊緣（需預拆）
| 檔案 | 行數 | 建議 |
|---|---|---|
| `ipc_server/mod.rs` | 1192 | 距硬上限 8 行，**立即預拆** |
| `tick_pipeline/on_tick/helpers.rs` | 1182 | S-9 預拆 |
| `strategist_scheduler/mod.rs` | 1166 | R-3 預拆 |
| `strategies/bb_reversion.rs` | 1143 | R-4 |
| `ws_client.rs` | 1136 | R-5 |
| `event_consumer/dispatch.rs` | 1124 | （已是 sibling，考慮再拆 handlers） |
| `intent_processor/mod.rs` | 1100 | R-6 |
| `claude_teacher/applier.rs` | 1068 | R-7 |
| `tick_pipeline/commands.rs` | 1039 | 建議下輪拆 |
| `tick_pipeline/mod.rs` | 1035 | 2026-04-22 已拆過，當前穩定 |
| `bybit_private_ws.rs` | 1013 | R-5 |
| `paper_state/maker_stats.rs` | 1011 | 監視 |
| `database/drift_detector.rs` | 1010 | 監視 |
| `position_reconciler/orphan_handler.rs` | 1009 | 監視 |

### Python ≥1000 行
| 檔案 | 行數 | 對策 |
|---|---|---|
| `live_session_routes.py` | 1449 | S-10 按 routes 域拆 |
| `ai_service.py` | 1258 | R-2 `_handle_*` 拆小 |
| `governance_routes.py` | 1172 | R-8 按 SM 拆 |
| `strategist_agent.py` | 1170 | R-9 |
| `multi_agent_framework.py` | 1137 | R-9 |
| `paper_trading_routes.py` | 1088 | 監視 |
| `governance_hub.py` | 1014 | R-8 |

### Helper ≥800 行
| 檔案 | 行數 | 對策 |
|---|---|---|
| `helper_scripts/db/counterfactual_exit_replay.py` | 1216 | R-10 |
| `helper_scripts/db/passive_wait_healthcheck.py` | 944 | 監視（12 check 增長中） |

---

## 五、與 2026-04-12 Refactor Wave 對照

**已確認閉環的先前改善**：
- `tick_pipeline/mod.rs` 2274 → 1035 行（TICK-PIPELINE-MOD-SPLIT-1 ✅）
- Python `main_legacy.py` 5113 → 468 行（DEDUP-PY-RUST Tier B Wave A-D ✅）
- `push_capped<T>`, `now_ms()`, `is_stale()`, `clamp_confidence()`, `build_intent()` helpers ✅
- `TickContext<'a>` zero-copy ✅
- Parallel DB flush (`tokio::join!` 7 tables) ✅
- OrderDispatchRequest 重命名 ✅
- Python `logger.xxx(f"…")` 生產代碼幾乎清零 ✅
- Python `int(time.time()*1000)` 集中到 `ai_agents/bybit_thought_gate/` ✅

**仍未動的 2026-04-01 殘留**：
- 2026-04-01 #16 `compile_state` 邏輯重複 — 現在 `main_legacy.py` 已 468 行，此條需重新對照新結構
- 2026-04-01 #28 `compile_state` O(n) 列表掃描 — 同上，需重新對照
- 2026-04-01 #29 `_compile_effective_action_permissions` O(n^2) — 同上
- 2026-04-01 #35 前端 `:root` CSS 變量重複 — 本次未採樣前端（範圍外）
- 2026-04-01 NEW-P2/P3 `truth_source_registry / experiment_ledger` 無界 dict — 仍未修復
- 2026-04-01 NEW-P4 `_compute_indicators_pure` 每 bar 從頭計算 EMA — backtest_engine 是否仍在 hot path 值得重測

**本次未採樣（範圍外或無明顯變動）**:
- 前端 HTML/CSS/JS (2026-04-01 有 11 項，本次依指令只審 Rust/Python/helper)
- `main.py` (352 行，未超限)
- `h0_gate.py` (971 行，接近但未突破)

---

## 六、優化建議優先級矩陣

### P0（立即執行，硬違反 1200 行上限）
1. **S-2**: `event_consumer/mod.rs::run_event_consumer` 1695 行拆分 — 預估 1-2 週
2. **S-1**: `main.rs` 2062 行拆 bootstrap/ — 預估 1 週
3. **S-3**: `instrument_info.rs` 1975 行拆 — 預估 3-4 日
4. **S-4**: `bybit_rest_client.rs` 1725 行按業務區拆 — 預估 1 週
5. **S-6**: `startup.rs::build_exchange_pipeline` 401 行拆 — 預估 3-4 日
6. **S-5**: `order_manager.rs` 1554 行 + 174 行 as_str — 預估 2-3 日
7. **S-7**: `paper_state/resting_orders.rs` 1367 行 — 預估 4-5 日
8. **S-8**: `config/risk_config.rs` 1328 行 — 預估 2-3 日

### P1（性能熱點，高收益中風險）
9. **P-1**: event_consumer cfg_snapshot 重複讀 — 隨 S-2 拆分一併做
10. **P-2**: build_exchange_pipeline 串行 await → try_join! — 預估 1 日
11. **P-3**: tick_pipeline 115 處 clone 審視 — 預估 2-3 日
12. **P-5**: `ai_budget/tracker.rs` 16 處鎖審視 — 預估 1 日
13. **P-8**: `strategist_agent._handle_intel` 198 行拆 — 預估半日
14. **R-6**: `ipc_server/mod.rs` 1192 預拆（8 行距硬上限）— 預估 2 日

### P2（可讀性 + 精簡，中收益低風險）
15. **R-1 ~ R-10**: 可讀性組合 — 預估總計 2 週
16. **P-4 / P-6**: SystemTime / time.time() 統一 — 預估 1 日
17. **P-7**: live_contraction_monitor backoff — 預估半日
18. **P-9 / P-10**: instrument_info cache eviction + event_consumer lock audit — 預估 2 日

---

## 七、風險提示與非目標

**不建議現在動的**：
- ~~Python `main_legacy.py`~~ — 已瘦至 468 行純基礎設施，進一步拆 singleton 屬 cosmetic（2026-04-23 audit 已定 α 結案）
- ~~前端~~ — 本次範圍外
- ~~strategies/bb_breakout.rs~~ — 2026-04-24 剛完成 P1-11 audit + FIX-26-DEADLOCK-1，避免連續大改動

**本次報告有意不涵蓋**：
- 功能性 bug fix（E5 只做優化，非功能性審查）
- 架構重大重構（例如 Rust vs Python 邊界調整 — 由 PA/FA 主導）
- 測試套件結構（`tests.rs` 3524 行、`intent_processor/tests.rs` 1905 行、`paper_state/tests.rs` 1362 行等測試檔超限屬 test 特殊性，CLAUDE.md §七 1200 硬上限對應用代碼，但測試檔仍建議監視）

**對抗性驗證反思**：本報告基於**靜態分析 + 行數統計 + 關鍵字搜索**，未跑 profiler / flamegraph。性能建議（clone 熱度、鎖熱力）需 runtime profiling 驗證實際熱點；優先級應由 PM/PA 結合 flamegraph 再確認。測試檔超限未列 P0 是因測試本身的冗長性是可接受（test naming 清晰 > test 長度約束）。

---

## 八、總結

**核心發現**：
1. Rust 側 8 檔超 1200 硬上限（§七 明文禁止），其中 `event_consumer/mod.rs::run_event_consumer` 1695 行單 async fn 是項目史上最大單 fn（超過 2026-04-01 `_process_pending_intents` 462 行紀錄）
2. Python 側巨型 `main_legacy.py`（5113 行）債務 **已解**（→ 468 行），新熱點轉至 `live_session_routes.py` (1449) + `ai_service.py` (1258)
3. 先前 E5-Wave (2026-04-12) 的 helpers (`push_capped`, `now_ms`, `clamp_confidence`, `TickContext<'a>`, parallel DB flush) 已閉環，未見回彈
4. 2026-04-01 多項殘留（truth_source_registry / experiment_ledger 無界 dict、前端 :root 重複、setter 重複、compile_state 重複）仍適用，但因 Rust 側硬違反優先級更高，建議先清 Rust P0

**建議路線**：
- 先清 8 項 Rust P0（2-3 週）→ 再處理 P1 性能（1-2 週）→ 最後 P2 可讀性持續推進
- 與 Live 路徑並行：P0-2 21d demo 期（至 ~2026-05-07）內剛好容納 Rust 拆分工作
- 每次拆分伴隨 engine lib 測試（當前 1980 passed baseline）+ E2 adversarial review

---

*E5 Optimization Engineer · 2026-04-24 04:30 CEST*
*Report location: `docs/CCAgentWorkSpace/E5/workspace/reports/2026-04-24--full_chain_optimization_audit.md`*

E5 AUDIT DONE: docs/CCAgentWorkSpace/E5/workspace/reports/2026-04-24--full_chain_optimization_audit.md
