# CLAUDE_CHANGELOG.md — 開發歷史歸檔

> 從 CLAUDE.md 遷出的 Wave/Sprint/Batch 歷史記錄。新 session 不需要讀此文件，僅供回顧歷史時查閱。
> 最後更新：2026-04-11

### 3E-E2 Phase G: 9 角色重審 PASS（2026-04-11）

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



### Session ARCH-RC1 1C-2-C/D/E SHIPPED + 1C-3 Scoped + 文檔大清理（2026-04-07 PM · commits `5f87bca` `de75191` `950f547` `b0fa2c6`）

**1C-2-C** (`5f87bca`): 6 unified Config IPC endpoints (`get/patch_{risk,learning,budget}_config`). Generic JSON deep-merge → deserialize → validate → `store.replace()` path through `handle_get_config<T>` / `handle_patch_config<T,V>`. All-or-nothing rollback semantics. Source audit (`operator|agent|migration`) parsed from `params.source`. Legacy field-based `update_risk_config` (channel-based) kept untouched for backwards compat — bypasses ConfigStore so does NOT trigger hot-reload, will phase out in 1C-3.
+6 tests · engine 714 → 720.

**1C-2-E schema** (`de75191`): V014 `observability.engine_events` audit table + 3 indexes (`ts DESC`, `(type,ts DESC)`, partial `(config_name,new_version DESC)`). event_type ∈ {startup, shutdown, config_patch, config_reject, reconcile, crash}. Applied to live PG.

**1C-2-D** (`950f547`): New `config/legacy_migration.rs` runs once at startup from `load_unified_configs`. Skip cases: TOML exists, JSON missing. Otherwise: parse JSON, map ~15 known `global_config.*` fields onto `RiskConfig::default()`, validate, save_toml, rename `.legacy`. Cross-Config `max_cost_edge_ratio` → log WARN (belongs to BudgetConfig). Failures non-fatal: WARN log + boot with defaults. +5 tests · engine 720 → 725.

**1C-2-E audit wiring** (`b0fa2c6`): IpcServer gains late-injected `audit_pool: AuditPoolSlot`. main.rs writes `pg.clone()` into the slot after db_pool ready. `handle_patch_config` success branch fire-and-forget `tokio::spawn` INSERT into V014 with payload `{fields_changed: [top-level keys]}`. Fail-soft: db unavailable → audit skipped, patch still succeeds.

**1C-2 終局**: 4 IPC 寫入面 (3 patch + StrategyParams) → ConfigStore.replace() → version++ → tick-level hot-reload 同步 5 engines (intent_processor / guardian / paper_state / h0_gate / risk_governor) + V014 audit row. Config-layer 閉環完成，風控並行系統 7 套 → 1 Config 權威 + 5 engines 同步熱重載 + 完整審計。

**1C-3 Scoping** (`docs/references/2026-04-07--arch_rc1_1c3_scope.md`): Python RiskManager 1633 → ~200 lines RiskViewClient. 8 live methods + 3 setters identified. 5 sub-batch breakdown (A gap analysis / B build / C migrate routes / D migrate importers / E cleanup), 17-20h ≈ 3 sessions.

**文檔大清理**:
- CLAUDE.md 40K → ~25K bytes — §三 Phase 0/1/2/3/4 detail blocks (~180 lines) 歸檔到 `docs/archive/2026-04-07--claude_md_section3_history_phase0_4.md`，新增 1C-2-C/D/E SHIPPED 條目，§十一 one-liner 更新
- MEMORY.md 索引精簡 + 6 個過時 project_* 檔案 (`batch9_decisions`, `rust_cutover_decision`, `rust_migration_status`, `openclaw_deep_analysis`, `local_strategy_plan`, `gui_upgrade_plan`) 移到 `memory/archive/`
- TODO.md 1C-2-C/D/E 標記完成，1C-3 拆成 A-E 5 個子任務

測試：engine lib **714 → 725** (+11 / 0 regression) · core/types 不變 · all green。


### Session 1C-2-A/B/Opt-B/F — ARCH-RC1 熱重載 LIVE + 引擎收編（2026-04-07 · commits `581e1e2`..`91b5db8`）

ARCH-RC1 第四步（在 1C-1 call site 遷移之後）：把 ConfigStore 真正接進運行時，所有下游執行引擎都進入熱重載迴圈。這個 session 從骨架到「真正 live + engine consolidation」一氣呵成，共 6 個生產 commit + 2 個 docs commit。

**風控並行系統軌跡**：1A 前 7 套 → 1C-1 後 2 套（Config + Python）→ **1C-2-F 後 1 套 Config 權威 + 5 個引擎全部喝同一桶水**（Python 仍待 1C-3 空殼化）。

---

**1C-2-A — TOML Loader + ConfigStore 構造**（`581e1e2`，+254 / -2）：
- 新 `openclaw_engine/src/config/io.rs`（+6 tests）：
  - `load_toml_or_default<T, F>(path, validate)` — 讀 TOML，檔案缺失時回退到 `T::default()`，兩條分支都跑 caller validator（捕捉「預設值無效」這類啟動期退化）
  - `save_toml<T>(path, value)` — 序列化 + atomic rename，自動建立父目錄
  - Tests 覆蓋：missing file → default / parse existing / invalid TOML errors / validator runs / save→load round trip / nested mkdir
- `main.rs::load_unified_configs()` helper：解析 `settings/risk_control_rules/{risk,learning,budget}_config.toml`（env 可覆蓋 `OPENCLAW_RISK_CONFIG_DIR` 或各自 `OPENCLAW_{RISK,LEARNING,BUDGET}_CONFIG`），跑 `validate()`，各自包入 `Arc<ConfigStore<T>>`
- 在 EngineBootstrap `ConfigManager` 載入後立即呼叫
- 三個 store 構造但此時尚未穿透到消費者 → 1C-2-B

**1C-2-B — Pipeline Wiring + 熱重載 LIVE**（`e3014ef`，+140 / -13）：
- `TickPipeline` 新 fields：`risk_store` / `budget_store` / `risk_config_version_seen`
- 新 setters：`set_risk_store` / `set_budget_store`；`set_risk_store` 立即呼叫 `apply_risk_snapshot` seed 第一次快照並記錄版本號
- `sync_risk_config_if_changed()` 在 `on_tick()` 頂部：compare store version vs last-seen，變化即 pull 最新快照推到下游（single atomic load + equality，熱路徑零鎖）
- `current_cost_edge_max_ratio()` 取代 1C-1 placeholder 的硬編碼 0.8；從 `BudgetConfig.attention_tax.cost_edge_max_ratio` 每 tick 快照讀
- `evaluate_positions` call site 傳入 live cost_edge 值
- `EventConsumerDeps` 加 2 optional fields；`run_event_consumer` 接線後立即呼叫 pipeline setters
- `async_main()` signature 擴展接 3 個 ConfigStore；`load_unified_configs()` 現在回傳完整 tuple

**1C-2 Option B — Guardian 進入熱重載迴圈**（`8240a25`，+52 / -3）：
- 抽出 `apply_risk_snapshot(&RiskConfig)` 作為**單一傳播入口** — 所有下游同步都經過這裡
- Guardian 從 RiskConfig 拉取 `max_leverage` / `max_drawdown_pct` / `max_same_direction_positions`
- `modification_size_factor` / `modification_leverage_cap` 透過 RMW 保留（不在 RiskConfig schema 中）
- 重要觀察：Guardian **不是** risk_checks 的冗餘 — 它有獨特的 `Modified` verdict 路徑（downsize qty/leverage 而非 reject），以及 `direction_conflict` 檢查

---

**1C-2-F Engine 收編**（3 個 commit，3 個額外執行引擎加入熱重載迴圈）：

**F1 — RiskGovernorSm 讀 RiskConfig.cascade**（`1a7fc8b`，+59 / -12，E-Merge-3）：
- 1B 規劃的漏洞：`RiskConfig.cascade` 創建時**零消費者**，RiskGovernorSm 繼續用自己的 `EscalationThresholds::default()` 硬編碼（15 欄位與 cascade 平行但從未同步）
- grep 發現 RiskGovernorSm 在 `GovernanceCore::new()` 內部（tick_pipeline.governance.risk），且 `thresholds` field 是 `pub`，直接可寫
- 15 欄位 1-to-1 映射（命名差異：`circuit_breaker_pct` ↔ `circuit_pct`, `consecutive_loss_` ↔ `consec_loss_`, `min_hold_time_ms` ↔ `min_hold_ms`）
- 在 `apply_risk_snapshot()` 加第 3 步（後續改為第 5 步）
- 行為影響：只有熱重載路徑 — 初始 boot state 不變（RiskConfig.cascade 預設值 = 硬編碼 default）

**F3 — H0Gate 欄位從 RiskConfig.limits RMW 同步**（`e7f00d4`，+27 / -1，E-Merge-2）：
- H0GateConfig 的 3 個風控欄位（`max_open_positions` / `max_total_exposure_pct` / `allowed_categories`）複製 `RiskConfig.limits`
- 新 `openclaw_core::h0_gate::H0Gate::update_config()` 方法（原本 config field 是 private，無 setter）
- 在 `apply_risk_snapshot()` 加第 4 步 — RMW clone 當前 H0GateConfig，覆寫 3 個風控欄位，其他健康欄位（cpu/memory/db_latency/network/shadow_mode/health_snapshot_max_age_ms）保留
- 行為影響：熱重載路徑 only — operator 提高 `limits.open_positions_max` 時 H0 門控自動跟上，不再卡舊值

**F2 降級 — paper_state.stop_config 同步**（`91b5db8`，+26 / -1，E-Merge-1 downgraded）：
- Research agent（後台派發 ~5 分鐘分析）回報**重大發現**：StopManager 不是死代碼
  - tick_pipeline:910 + :1017 是**故意的保護 fallback**（H0 阻擋 / paper_paused 的 early-return 分支），main engine `evaluate_positions` 在這些分支下根本不跑
  - 刪掉這兩個 call sites 會讓持倉在 gate block / pause 時**完全沒有止損保護**
  - backtest.rs 仍需 `compute_atr_position_size`（那是 sizing helper 不是 stop check）
  - Research 回報的 trailing stop RR floor 差異確認是新引擎的**安全增強**，不是 bug
- **真正問題**是 `paper_state.stop_config` 啟動後**永不同步** — operator 改 RiskConfig 後 main engine 用新值但保護 fallback 用舊 boot defaults，形成靜默漂移
- 修法：`apply_risk_snapshot()` 加第 4 步（F3 後重新編號），同步 `set_hard_stop_pct` + 受 `take_profit_enforced` 控制的 `set_take_profit_pct`（trailing / time 不設，因為主引擎在非 fallback 路徑負責）
- **原計劃降級**：從「殺 StopManager + port 6-7 小時測試」降為 ~25 行 config 同步。StopManager 保留作為 H0/pause 保護 fallback 引擎 + backtest sizing utility

---

**最終熱重載終局**：`apply_risk_snapshot(&RiskConfig)` 單一傳播入口，每次 store version bump 同步 **5 個下游執行引擎**：
```
RiskConfig store.version++
      ↓
apply_risk_snapshot(&snap)
  ├─1→ intent_processor.risk_config         (Gate 0 + tick 主引擎)
  ├─2→ intent_processor.guardian            (P0 trade intent modify verdict)
  ├─3→ paper_state.stop_config              (H0/pause 保護 fallback)
  ├─4→ h0_gate.config                       (健康 + 風控欄位)
  └─5→ governance.risk.thresholds           (6-tier 級聯狀態機)
```

**測試**：
- engine lib 708 → **714**（+6 config/io tests，其他 config-sync 改動不需新測試因為行為只在熱重載路徑）
- core 386 → 387（regime.rs split 留下）
- types 30 → 27（1C-1 B6 刪 3 個死型別）
- integration phase4 3/3 · rrc1_audit 4/4 · stress 29/29 全綠
- 0 regression

**未做（1C-2 剩餘）**：
- 1C-2-C：6 個 IPC write endpoints（update_risk_config / update_learning_config / update_budget_config + 3 個 get_*）+ bulk patch all-or-nothing + mutex 序列化 + version + source 審計 + dispatch wiring
- 1C-2-D：`operator_risk_config.json` → `risk_config.toml` 一次性遷移（讀 → v2 schema → 寫 → 改名 .legacy）
- 1C-2-E：V014 `engine_events` audit 表 + ConfigStore audit hook
- 1C-3 Python 空殼化：`risk_manager.py` 1633 → 150 行 `RiskViewClient`
- 1C-4：Position Reconciler + NewsPipeline spawn + 熱重載 e2e 驗收 + E2 / E4 / QA audit
- E-Merge-4（選做，Phase 2）：Guardian owned `GuardianConfig` struct 退化為 RiskConfig view，純代碼味清理

---

### Session 1C-1 — ARCH-RC1 風控 call site 遷移（2026-04-07 · commits `2007b67` `6768381` `ef30bf1`）

ARCH-RC1 第三步：把 1B 建好的新 Config 真正接進所有 call site，物理刪除重複並行的舊風控類型。Batches 0-6 一個 session 跑完，共 3 個 commit，+747 / −1293（淨 −546 行），0 regression。

**風控並行系統軌跡**：1A 開始 7 套 → 1A 結束 6 套 → 1C-1 B0-4 結束 4 套 → B5 結束 3 套 → **B6 結束 2 套**（RiskConfig 權威 + Python RiskManager 待 1C-3 空殼化）。

**Batch 0 — AntiCluster.max_same_direction 校齊**（`2007b67`）：
- 新 `RiskConfig.anti_cluster` 原本只有 `offset_fraction`，grep 活體掃描發現 `max_same_direction` 在 guardian.rs/ipc_server.rs/claude_teacher applier/GUI API route 全活用，不可刪
- 加欄位 + 範圍驗證 `[1, 100]` + 3 tests（default/zero_rejected/over_limit_rejected）

**Batch 1 — openclaw_core/src/risk 瘦身**（`2007b67`）：
- 刪 `RiskManagerConfig` 整個 struct（229 行 + 4 tests）
- 刪 `checks.rs`（17 tests · check_order_allowed + check_position_on_tick 原址）
- 新建 `regime.rs`（36 行 + 3 tests）— 保留無狀態 regime multiplier fallback 供 `stops.rs` 使用（core 不能依賴 engine）
- mod.rs 重寫 exports

**Batch 1b — 新建 openclaw_engine/src/risk_checks.rs**（`2007b67`，502 行 / 16 tests）：
- `check_order_allowed(&RiskConfig)` — 讀 `limits.*`
- `check_position_on_tick(cost_edge_max_ratio, &RiskConfig)` — cost_edge 變成 primitive 參數（契約明確 BudgetConfig 為權威，caller 從 `BudgetConfig.attention_tax.cost_edge_max_ratio` 取出傳入）
- 所有 15+ 欄位映射到新 sub-struct 路徑（`limits.stop_loss_max_pct` / `agent.trailing_enabled` / `dynamic_stop.base_ratio` / `cost_gate.k_base` 等）

**Batch 2+3+4 — 5 檔案 call site 遷移**（`2007b67` · 單一編譯單元）：
- `pipeline_types.rs`: 快照欄位型別 `Option<RiskConfig>`
- `tick_pipeline.rs`: import swap + ADX 閾值改讀 `cost_gate.adx_trending` + `evaluate_positions` 加 `cost_edge_max_ratio=0.8` 參數（1C-2 改接真 BudgetConfig）
- `intent_processor.rs`: struct 欄位 + 9 個 patch_* 路徑 + 所有 cost_gate k_* 讀取
- `position_risk_evaluator.rs`: 簽名 + 5 處測試重映射
- `event_consumer/setup.rs`: Guardian + IntentProcessor 改用 `RiskConfig::default()` 種子（1C-2 改接 ConfigStore）
- `event_consumer/tests.rs`: 8 個 field-path assertion 重寫

**Batch 5 — RuntimeConfig 改名 EngineBootstrap + 刪風控欄位**（`6768381` · 4 檔案 / +78/−149）：
- 刪 8 個風控欄位：`p1_risk_pct` / `max_stop_loss_pct` / `max_take_profit_pct` / `max_open_positions` / `max_total_exposure_pct` / `max_leverage` / `max_drawdown_pct` / `max_same_direction_positions`（消費者全改讀 RiskConfig.limits 或 anti_cluster）
- `RuntimeConfig` → `EngineBootstrap` 正式改名；保留 `#[deprecated] pub type RuntimeConfig = EngineBootstrap` 過渡 1C-2（外部 crate 繼續編譯）
- 驗證邏輯重寫 — 只檢啟動欄位：reconnect_delay > 0 / heartbeat > 0 / ipc_socket 非空
- 測試重寫：刪 3 風控 validate tests + 加 2 bootstrap validate tests
- ipc_server `handle_get_state` 風控顯示欄位改讀 `RiskConfig::default()` placeholder
- integration test `rrc1_audit_tests.rs` 斷言改 `rc.limits.stop_loss_max_pct`

**Batch 6 — openclaw_types::risk 死代碼清理**（`ef30bf1` · 2 檔案 / +19/−122）：
- 刪 `GuardianConfig`（types 版本，0 consumers · live 版本在 `openclaw_core::guardian`）
- 刪 `StopConfig`（types 版本，0 consumers · live 版本在 `openclaw_core::stop_manager`）
- 刪 composite `RiskConfig`（0 consumers · 由 `openclaw_engine::config::RiskConfig` 取代）
- 刪 `test_stop_config_matches_golden` 黃金 schema 測試（core 側型別從 types 測試不可達，只能刪）
- 刪 `test_risk_config_default_serde` / `test_stop_config_serde`
- 保留 H0 gate 跨 crate 共享 runtime 類型：`H0GateConfig` / `H0GateHealthSnapshot` / `H0GateRiskSnapshot` / `H0CheckResult`
- lib.rs re-exports 對應精簡

**測試與驗證**：
- engine lib 682 → 708 (+26)
- core 386 → 387 (+1 · regime.rs 拆出)
- types 30 → 27 (−3 · 刪 3 個死類型 tests)
- phase4_integration 3/3 · rrc1_audit 4/4 · stress_integration 29/29 全綠
- 0 regression

**1C-1 未做（留後續 session）**：
- 1C-2: ConfigStore 構造 + main.rs 啟動序列注入 + 4 個 update/get IPC 端點 + bulk patch audit + operator_risk_config.json→TOML 一次性遷移 + V014 engine_events 表
- 1C-3: Python `risk_manager.py` 1633 → 150 行 `RiskViewClient` + 32 檔案 import 遷移 + risk_routes.py GUI 寫端點轉發 IPC
- 1C-4: Position Reconciler + NewsPipeline spawn + 熱重載 e2e 驗收 + E2/E4/QA audit

### Session 1B — ARCH-RC1 統一 Config 骨架（2026-04-07）

ARCH-RC1 第二步：純加法建立新 Config 架構骨架，零行為改變，舊系統繼續運行（雙軌並存）。call site 遷移留 1C。

**新增檔案 4 個（~1900 行 + 58 tests）**：

- `rust/openclaw_engine/src/config/store.rs` — 泛型 `ConfigStore<T>` 包裹 `Arc<ArcSwap<T>>`：
  - `load()` 無鎖快照讀（~5ns，tick 熱路徑安全）
  - `apply_patch(source, mutate, validate)` 序列化 mutex + all-or-nothing：驗證通過才 swap
  - `replace(value, source)` 全量替換（用於 startup / migration）
  - `PatchSource` enum：Operator / Agent / Migration / Startup
  - 7 unit tests 含並發 race 測試（10 thread × increment → 必為 +10）

- `rust/openclaw_engine/src/config/risk_config.rs` — RiskConfig 主體：
  - 13 sub-struct：Meta / GlobalLimits (P1) / CategoryOverrides (P0) / StrategyOverride (per-strategy)
    / AgentParams (P2 含 partial_tp) / CascadeThresholds (RiskGovernor 6 級) / RegimeMultipliers (5 regime × 3 mult，從 hardcode 提升)
    / CostGate / DynamicStop / MarketGate (microstructure 收編，9 欄位 funding/liquidation/spread/slippage/ob/volume/fee/rate_limit)
    / AntiCluster / Correlation / RuntimeKnobs / Experimental
  - GlobalLimits ~26 欄位含新搬入的 min_order_notional / max_order_notional / min_balance
  - 跨 sub-struct invariant：partial_tp_levels 各層 ≤ take_profit_max_pct，min_order_notional ≤ max_order_notional
  - validate() 對所有 sub-struct 套用嚴格約束 + 跨欄位檢查
  - 24 unit tests 涵蓋預設值對齊 Python legacy / 各種驗證失敗 / per-strategy 暫停 / TOML JSON round-trip / partial TOML 預設保留

- `rust/openclaw_engine/src/config/learning_config.rs` — LearningConfig 主體：
  - 5 sub-struct：Meta / MlSwitches / LinUcbParams / ThompsonParams / AgentBehavior / Experimental
  - **Phase 4.1 default-off 契約收編**：`switches.teacher_loop_enabled = false` 預設，IPC slot 翻開才生效（既有 set_teacher_loop_enabled IPC 端點 1C 改讀此欄位）
  - AgentBehavior 含 entry_confidence_min / kelly_fraction / regime_whitelist / order_type_preference / breakeven_trigger / max_positions_per_*（partial_tp 不在這裡，搬到 RiskConfig.agent）
  - 13 unit tests 含 Phase 4.1 default-off 契約測試

- `rust/openclaw_engine/src/config/budget_config.rs` — BudgetConfig 主體：
  - 5 sub-struct：Meta / BudgetCaps / ModelCosts / **AttentionTax (整塊含 enabled)** / Experimental
  - AttentionTax 從 RiskConfig 完全遷出（避免跨 Config 校準失同步）：burn_rate × 4 + grade_a/b/c/d_threshold + cost_edge_max_ratio + enabled
  - validate() 強制 burn_rate 非遞減 + grade 嚴格遞增
  - 12 unit tests 含 enable/disable / 跨欄位驗證失敗 / TOML+JSON round-trip / partial TOML 預設保留

**檔案結構變更**：
- `rust/openclaw_engine/src/config.rs` → `config/mod.rs`（git mv，內容不變）
- 新 `config/{store,risk_config,learning_config,budget_config}.rs`
- mod.rs 加 4 個 `pub mod` 宣告 + 4 個 re-export

**驗證**：
- `cargo build -p openclaw_engine` 8.41s 通過，0 新 warning
- `cargo test -p openclaw_engine` lib **682 passed (+58 vs 1A baseline 624) / 0 fail / integration 36**
- `cargo test -p openclaw_core` **386 + 8 + 19 / 0 fail**
- `cargo test -p openclaw_types` **30 / 0 fail**
- 零行為改變（純加法 commit，舊 RuntimeConfig 風控欄位仍在跑）

**下一步（Session 1C）**：
1. 廢棄 `openclaw_core::risk::config::RiskManagerConfig`，所有 call site 遷移到新 RiskConfig
2. RuntimeConfig 風控欄位（max_stop_loss_pct / max_leverage / max_drawdown_pct / p1_risk_pct 等）刪除，call site 改讀 RiskConfig
3. RuntimeConfig 改名 EngineBootstrap
4. operator_risk_config.json → risk_config.toml 一次性遷移
5. IPC update_risk_config / get_risk_config 等 6 端點接通新 ConfigStore
6. Python RiskManager 1633 → ~150 行 RiskViewClient（純 IPC 讀）

### Session 1A — ARCH-RC1 死代碼清理（2026-04-07）

ARCH-RC1 統一 Config 工作的純減法首步：盤點 rust/ tree 後確認 7 套重疊的風控/配置系統，先砍 3 個已驗證為純死代碼的目標，為後續 1B（新建 3-Config 骨架）+ 1C（遷移 call site + Python 空殼化）鋪路。

**砍掉的死代碼**：
- `openclaw_engine::config::MlConfig`（struct + Default + 3 default fns，~50 行）
  - 真實 ML 用 `ml::kelly_sizer::KellyConfig` + Scorer/OnnxModelManager constructor 直傳，從未讀 RuntimeConfig.ml
  - grep `kelly_max_fraction|kelly_min_trades|kelly_risk_pct|onnx_model_path|scorer_enabled|kelly_enabled` → 0 業務 call site
- `openclaw_engine::config::attention_*_ms` 5 欄位 + 5 default fns + Default impl/test 引用（~30 行）
  - cognitive 系統用 `CognitiveParams::scan_interval_s` 不是 attention intervals
  - grep 整個 srv/（含 Python） → 0 業務 call site
- `openclaw_types::config::EngineConfig` + `ParamTemperature`（整檔 187 行 + lib.rs re-export）
  - V3-PA-5 規劃的 cold/warm 元資料系統，但實作改用 `ConfigManager::reload()` 內寫死的欄位級 warn+preserve（型別安全更高）
  - 6 個業務欄位全部已有替代（RuntimeConfig / H0GateConfig / GovernanceMode / CognitiveParams）
  - grep `EngineConfig|ParamTemperature` → 0 代碼引用，僅 2 處設計文檔提及

**淨刪除**：~270 行死代碼。零行為改變（純減法 commit）。

**驗證**：
- `cargo build -p openclaw_types -p openclaw_engine` 9.87s 通過，0 新 warning
- `cargo test -p openclaw_engine` lib **624 / integration 36 / 0 failed**
- `cargo test -p openclaw_types` **30 / 0 failed**

**ARCH-RC1 全貌**：將 7 套重疊配置（Python RiskManager / openclaw_core::RiskManagerConfig / openclaw_engine::RuntimeConfig / openclaw_types::EngineConfig 死 / openclaw_types::risk 活 / GuardianConfig / H0GateConfig）統一為 3 個熱重載 Config（Risk/Learning/Budget）+ StrategyParams，TOML on-disk + JSON IPC + ArcSwap 熱重載，禁止 restart-to-apply。Session 1A 是純清理，1B 建骨架，1C 遷移 call site + Python 空殼化。

### Session 16 — Phase 4.1 SHIPPED + E3 R6 closed + P2 partial（2026-04-07 · commits `ee6fd00`..`aecea27`）

**Phase 4.1 Claude API Consumer Loop（`ee6fd00`）：**
- 新 `claude_teacher/consumer_loop.rs`（~480 行 / 10 tests）：`TeacherConsumerLoop` round-robin 5 strategy scope，
  `ConsumerLoopConfig` (300s poll, max 1/cycle), `ConsumerLoopStatus` 4 計數器, `Arc<AtomicBool> enabled` default-off。
- `mod.rs::fetch_parse_persist` 拆出回傳 `(Directive, i64)`，loop 直接餵 applier 不用 PG 重讀。
- `main.rs` Arc 接線：AnthropicClient → ClaudeTeacher → DirectiveApplier (with PaperSessionCommandSink + GovernanceCoreWrapper) → OutcomeTracker → TeacherConsumerLoop。default-off 依賴 BudgetTracker + db_pool 就緒。

**E3 R6 Security Audit（Explore agent read-only · `docs/audits/2026-04-07_e3_r6_directive_applier_security_audit.md`）：**
- VERDICT: **CONDITIONAL GO**（3 P1 minor，無 P0/blocker）。
- P0 bypass surface 全 SAFE：case-insensitive denylist、one-level JSON traversal、ARCH-RC1 Python 隔離、kill-switch 通配大小寫不敏感。
- P1 minor 全部關閉於 `8762d1d`：5 個 test cases（case-mangled P0 / unknown strategy + empty params / NaN/0/Infinity boost / halted+high-loss / explicit P0 in non-empty params）+ 2 個 doc comments（governance 重檢 race 合約 + kill-switch 大小寫文檔）。
- 副作用發現：`f64::NAN`/`Infinity` 經 serde_json → null → `as_f64()` None → 安全預設 1.0 → Applied（不變式仍保持「>MAX_BOOST_FACTOR 永不到 IPC」）。

**IPC teacher_loop control（`8762d1d`）：**
- `TeacherLoopHandles { enabled, status }` + `TeacherLoopSlot` 鏡像 BudgetTracker 延後注入模式。
- `set_teacher_loop_enabled(enabled: bool)`：fail-soft uninitialized、-32600 missing/non-bool、atomic flip。
- `get_teacher_loop_status`：回傳 enabled + 4 計數器 + last_cycle_ms。
- 5 新 tests + 19 個 dispatch_request callers 同步更新。

**P2 tick_pipeline.rs 拆分（partial · `e7ca473`/`aecea27`）：**
- `decision_context_producer.rs` (294 行 / 6 tests)：`emit_decision_context()` 純函數，含 `select_linucb_arm` + `read_news_context` 助手。tick_pipeline DB-RUN-2 piggyback 點 ~140 行 → 12 行 call。
- `position_risk_evaluator.rs` (247 行 / 9 tests)：`PositionRow` / `PositionDecision` + `evaluate_position` / `evaluate_positions`。policy-vs-mechanism 拆分：純函數計算 RiskAction，dispatch loop 留 tick_pipeline 內聯處理 close/halt/cooldown 副作用。
- tick_pipeline.rs **2211 → 2117**（-94 lines net），仍超 §九 1200 行硬上限 917 行。剩餘 on_tick 區塊（Step 0/0.5/1/4+5/dispatch loop/exchange-confirmed-fill）重度 `&mut self`，留專屬 session 處理。

**Doc sync（`8762d1d` 含部分，本批補完）：**
- CLAUDE.md §三：Phase 4.1 + E3 R6 + P2 partial 區塊
- CLAUDE.md §十一：one-line status 升至 624 tests
- TODO.md：E3 R6 + 4.1 marked [x]，P2 標 partial 含剩餘行數
- CLAUDE_CHANGELOG.md：本條目

**測試變化：**
- engine lib **589 → 624（+35 new this session, +183 vs Phase 4 baseline 441）**
- phase4_integration 3/3（不變）
- 0 regression
- 新 tests 分布：claude_teacher::consumer_loop 10 + claude_teacher::applier (E3 R6) 5 + ipc_server (teacher_loop) 5 + decision_context_producer 6 + position_risk_evaluator 9

**Live blocker 縮減：**
- 前：(1) E3 R6 audit / (2) 4.1 Claude API loop / (3) 7d paper data
- 後：✅ E3 R6 closed · ✅ 4.1 shipped · ⏳ 僅剩 7d paper data（calendar-time）
- 7d 後 operator 一個 IPC call `set_teacher_loop_enabled {"enabled": true}` 即可上線

**Session commits：** `ee6fd00` `8762d1d` `e7ca473` `aecea27`（4 個 + 1 worklog `23e2619`）

---

### Session 14 — WP 整清 + GUI 修正 + Phase 4 Wave 1（2026-04-06 · commit 31fb227）

**WP backlog 稽核：**
- 5-path 並行 Explore 核查 223 項 → 94 已修 + 103 真實 open，TODO.md 替換
- WP-G ✅ Kelly ATR vol-mult + Thompson NIG defaults 提取到 config（`4187da6`）
- WP-BB ✅ 主動限速退讓 + 刪除死碼 WS listener ~2500 行（`44b0eee`）
- WP-I ✅ P1 文檔衛生 7 項（`338b4f9`）
- WP-F ✅ P0 全部 + P1 11/18 GUI bug 修正（`71e4770`）

**GUI 修正：**
- no-cache headers + BUILD_TS bump 解決硬刷新失效（`1846966`）
- 風控輸入框用 Python RM (gc) 取代 Rust snapshot，修正存完即回彈（`f3106d8`）
- WP-ARCH-RC1 雙風控系統 tech debt 正式登記，5 子任務（`b33824f`）

**Phase 4 Wave 0+1（背景 agent，7/22 子任務）：**
- 4-00 Dashboard 骨架 + phase4_routes.py（`d36116f`）
- 4-15 BudgetTracker Rust + V010 DDL + IPC wiring（`b4cfade`）
- W1 5 模組並行：4-01 Teacher / 4-04 LinUCB / 4-07 News / 4-11 DL-3 / 4-17 Pricing（`31fb227`）

**測試：** engine 531 · Python 3279 pass

---

### L3 全系統審計 — 12 路並行 + PA 統一整改（2026-04-05 · commit b25e541）

**12 個審計角色並行：**
- **FA**（功能規格）：8通過/3警告/0失敗 · Exchange 缺 Cost Gate · 3 占位硬編碼 · ML 未接入
- **AI-E**（AI 效果）：42/100 · 架構優秀但運行時 AI 缺失 · ONNX 占位符 · 5 Agent 斷連
- **E5**（優化）：1 Rust + 5 Python 超 1200 行 · intent_processor 120 行重複 gate 邏輯
- **E4**（測試）：4708 tests · 3 P0 編譯回歸 · event_consumer 零測試
- **E3**（安全）：2P0(Exchange 缺 Cost Gate + IPC 無認證) / 5P1
- **CC**（合規）：82.6% 合規 · 10 文件超限 · 雙軌止損未完全接入
- **QC**（數學）：零數學錯誤 · 47 硬編碼值(5 高風險) · ATR 命名誤導
- **MIT**（DB/ML）：52/100 · DDL 未執行(6 寫入器空轉) · ort crate 缺失
- **BB**（Bybit API）：A 級 · 0 P0/P1 · 僅 2 P2 警告
- **TW**（文件盤查）：14 組重複文件 · README 索引停更 · 26 命名違規
- **R4**（索引驗證）：25 項遺漏 · SCRIPT_INDEX.md 不存在
- **A3**（GUI）：11 P0/P1 · 風控輸入被自動覆蓋 · Delete 無確認

**PA 統一整改：** 63 獨立問題（7P0/21P1/25P2/10P3）→ 11 工作包 → 4 波執行

---

### RRC-1：風控運行時接線 — 5 Phase 完成（2026-04-05 · commits aa4d008 + 666815a + afd4c87）

**Phase A — H0Gate 接入 tick_pipeline：**
- tick_pipeline.rs Step 0.5：H0Gate 5-check（freshness/health/eligibility/risk/cooldown）
- event_consumer.rs：每 30s 更新 H0GateRiskSnapshot（position_count + exposure_pct）
- Shadow mode 默認啟用（觀察不阻斷，1 週後切 blocking）

**Phase B — check_order_allowed 接入 IntentProcessor：**
- Gate 2.7：5 項訂單准入檢查（daily loss/leverage/single pos/total exp/correlated exp）
- 放置在 P1 sizing 之後（避免拒絕會被安全縮小的訂單）
- daily_start_balance + UTC midnight 重置

**Phase C — check_position_on_tick 替換 check_stops：**
- 9 項持倉風控（hard/dynamic/TP/trailing/time/cost edge/session DD/consec loss/daily loss）
- PriceHistoryTracker 滾動 ATR + spike 檢測
- RiskAction enum：Hold/ClosePosition/HaltSession/SetCooldown
- entry_price=0 防護（→ -999% PnL 觸發硬止損，防 NaN fail-open）

**Phase D — 風控單一真相源：**
- PipelineSnapshot +8 風控欄位（stop/guardian/risk configs + session_halted + daily_loss + drawdown）
- Python risk_routes.py 全部改從 Rust 快照讀取
- /ai-context 從 Rust snapshot 重建（ENGINE=None safe）

**Phase E — 清理 + IPC 擴展：**
- Strategy trait +set_active() · IPC set_strategy_active 命令
- /unhalt-session → IPC resume_paper → Rust 清除 session_halted
- HaltSession Q1 fix：exchange 模式跳過已 pending close 的 symbol

**3 輪審計：** F1 P0(entry_price=0 NaN) + F2 P1(session_halted 未清除) + F3 P1(consecutive_losses 未重置) + Q1(exchange double-close) 全修復
**測試：** 856 Rust + 4 新 rrc1_audit_tests · 0 failures

---

### Session 9c：realized_pnl Bug + Gate 3 Cost Gate（2026-04-05）

**Bug 修復：**
- `paper_state.rs`：`apply_fill()` 返回 `f64` realized_pnl（之前返回 `()` → DB 永遠記 0）
- `tick_pipeline.rs`：paper + exchange 兩條路徑都使用 apply_fill 返回值寫入 TradingMsg::Fill

**Gate 3 Cost Gate（QC 設計）：**
- `intent_processor.rs`：新增 Gate 3 — EV vs round-trip fee 預檢查
- 公式：`ATR × confidence × qty < k × 2 × fee_rate × notional → 拒絕`
- 常數：min_confidence=0.15（硬地板）/ k=1.5（paper）/ k=2.0（live）/ ATR 不可用→fail-open
- +3 新測試（低信心 / 低 EV / 高 EV 場景）· 379 Rust tests pass
- 生產驗證：低波動市場中全部低 EV 交易被攔截，零無效手續費

**後續待辦：** 策略 confidence 需從固定 0.50 改為動態設置

---

### Session 9b：Operational Fixes + Risk GUI Completion（2026-04-05）

**3 生產 Bug 修復：**
- `trading_writer.rs`：signals flush overflow → batch chunking (5000 rows/batch)
- `tick_pipeline.rs`：BTC/ETH qty=0 → min_qty fallback (10% balance guard)
- `ws_client.rs`：last_tick_ms=0 → unified `now_ms()` SystemTime fallback

**風控 GUI 完善：**
- Bug fix：trailing_stop 輸入框未接入 saveRiskConfig()
- 新增 8 個控件：P1 Risk / ATR Multiplier / Max Single Pos / Total Exposure / Same-Direction / Cooldown Count+Duration / H0 Shadow Mode
- 新增 3 個 GUI 區塊：仓位控制 + 亏损冷却 + H0 Gate
- `risk_routes.py` GlobalConfigUpdate +5 fields + IPC push 映射
- `ipc_client.py` +h0_shadow_mode 參數
- E5+E2+PA+FA 四角色審計 0P0/1P1(fix)/2P2(fix)

**QA 對沖分析：** 暫不啟用同幣種多倉（Bybit net-position 默認模式）

---

### EXT-1：Exchange-as-Truth 實現（2026-04-05 · Session 9）

**核心改動：**
- `config.rs`：TradingMode enum (PaperOnly/Exchange) + trading_mode 冷參數
- `intent_processor.rs`：ExchangeGateResult struct + process_gates_only() 方法（門禁不模擬成交）
- `tick_pipeline.rs`：on_tick 雙模式分叉 + apply_confirmed_fill() + pending_close_symbols 防止重複止損
- `event_consumer.rs`：ExchangeEvent channel + PendingOrder 追蹤 + order_id→order_link_id 映射 + 5s/60s 超時
- `main.rs`：ExchangeEvent channel 從 ExecutionListener 接入 event_consumer
- `ipc_server.rs`：get_state + PipelineSnapshot 加 trading_mode
- `paper_trading_routes.py`：session status 加 trading_mode

**E2 審計修復：**
- P0-1：Fill 匹配改用 order_id→order_link_id 映射（不再 symbol+side 模糊匹配）
- P0-2：交易所模式 zero-qty 防護（精度取整後數量為零跳過派發）
- P0-3：pending_close_symbols 防止交易所模式止損無限循環

**測試基準線：** 852 Rust + 1075 Python = 1927 tests（0 failures · 1 pre-existing grafana test skip）

### Session 9：L3 Audit + Zero-qty Fix + Risk Config（2026-04-05 · commits 5c1c935~d053a51）

**L3 Audit Fixes（commit 5c1c935）：**
- P0-1：paper_state.apply_fill partial close 修復（reduce qty 而非 remove）
- P0-2：exec_id dedup — VecDeque ring buffer（max 500）
- P0-3：DCP/Disconnected events 從 ExecutionListener 接入 event_consumer
- P0-4：pending_close_symbols 在 close order rejection 時清除
- P0-5：Exchange 模式 balance reconciliation（WS wallet，>0.1% drift 觸發）
- SEC-1：Cold params 在 hot-reload (SIGHUP) 時保留
- SEC-5：Mainnet 需 OPENCLAW_ALLOW_MAINNET=1 環境變量

**Zero-qty Ghost Position Fix（commit 66ee29b）：**
- 根因：P1 cap 對 BTC/ETH（$1000 餘額）取整後數量為 0
- 修復：tick_pipeline 跳過 qty=0 + paper_state.apply_fill 拒絕 qty<=0

**P1 Risk Cap Configurable（commit 8103c6f）：**
- P1_RISK_PCT 從硬編碼 const 0.02 改為 engine.toml 可配置欄位

**GUI→IPC→Rust Risk Config 全鏈路（commits f7c9086~d053a51）：**
- PaperSessionCommand::UpdateRiskConfig IPC 命令（9 欄位）
- StopConfig：+take_profit_pct + check_take_profit()
- Guardian：expose config()/update_config() 供運行時更新
- RuntimeConfig：+max_leverage, max_drawdown_pct, max_same_direction_positions
- 全部 GUI 風控參數流向 Rust：Hard Stop / Take Profit / Trailing / Time / ATR / Max DD / Max Lev / Max Pos / P1 Risk
- Agent auto-tuning 路徑：/api/risk/agent-adjust → IPC → Rust engine
- Startup wiring：engine.toml → Guardian + StopConfig + IntentProcessor

**關鍵決策：**
- 所有風控參數必須 runtime-configurable（Agent 學習循環需求）
- Mainnet 需 OPENCLAW_ALLOW_MAINNET=1（防止意外部署）
- Cold params 在 SIGHUP 時保留（防止意外模式切換）

**測試基準線：** 856 Rust + 1075 Python = 1931 tests（+4 new · 0 failures）

### Phase 1 Day 0 + G1 + G2：sqlx PG 層 + FeatureCollector + 10 市場表（2026-04-05 · commits 8e0cccd~pending）

- **Day 0**：event_consumer.rs 提取（main 1123→783）+ database/ 模組 + sqlx 0.8 + Docker test PG
- **G1**：feature_collector.rs 34-dim + market_writer(klines/tickers) + feature_writer(UPSERT) + pipeline channels
- **G1 Audit**：6 角色審計 — 2 FAIL 修復（34-dim docs + dead channel）、3 WARN 記錄
- **G2**：market_writer 全 10 表 + fallback.rs(JSONL) + rest_poller(funding/OI/LSR) + quality_writer
- **架構決策**：Full Rust Option A · sqlx runtime queries · QueryBuilder::push_values · ADWIN delta=0.05
- **G3**：drift_detector.rs 448 lines — PSI(epsilon smoothing) + ADWIN(delta=0.05, 3-vote, Welch t-test) + baselines + versioning
- **G4 Final**：E2(1 P0 fix: feature_writer $5 bind) · E4(800 Rs + 3343 Py 全綠) · E5(PASS)
- **3 輪審計**：9 FAIL 全修復（G1: 2F + G2: 6F + G4: 1F）· 10 WARN 記錄
- **測試**：800 Rust（+30 new）· 0 failures · 0 warnings
- ~3,500 新代碼 · 11 new files · 10 commits

### Phase 2 完成 — Trading + Scorer + Kelly + ML Training（2026-04-05 · commits 41e144d~fb45c95）

- **2a**：trading_writer(4 tables) + context_writer(15 flat+JSONB) + ExperimentLedger PG(V007)
- **2b-infra**：ml/model_manager(ArcSwap ONNX) + ml/scorer(3-tier) + ml/kelly_sizer(fractional Kelly)
- **D+E**：Kelly Gate 2.5 intent_processor 接入 + Python ml_training/ 6 模組（label/trainer/calibration/onnx/leakage/etl）
- **F+G**：Parquet ETL(DuckDB) + E2/E4 final PASS
- 新增 KNOWN_ISSUES：TEST-1(ws tests) + DEBT-2(main.rs 920行) + ML-1(ort placeholder) + ML-2(numpy env)
- **測試**：823 Rust(+53) + 3348 Python + 5 ml_training · 4 pre-existing ws failures
- ~2,200 新 Rust + ~700 新 Python · 7 commits

### Session 6：基礎設施清理 + 告警系統（2026-04-05 · commit 0e2d6a4）

- **KNOWN_ISSUES 修復 4 項**：RE-1(memory audit→RESOLVED), RE-2(WS supervisor+channel-close propagation), ARCH-1(intent dedup), ARCH-4(fail-closed hardening)
- **OC-1 WebhookAlerter**：新建 webhook_alerter.py — HMAC-SHA256 簽名、多端點扇出、滑動窗口限流
- **OC-2 AlertRouter**：新建 alert_router.py — Telegram+Webhook 雙通道統一告警分發，paper_trading_wiring.py 接入
- **Bybit handbook**：§2.3 Shadow Order Sync Channel 完整文檔（架構圖+結構體+觸發點+已知陷阱）
- **Batch D**：RE-3 降級 LOW + DEBT-1 deferral note + IPC-05 範圍記錄延後
- **測試**：770 Rust + 3343 Python = 4113 全綠（1 known flaky excluded）
- **OPEN 11→8 · RESOLVED 3→7**
- 12 files changed, +759/-68 lines

### PYO3-BYBIT 完成 — PyO3 Bybit API 橋接（2026-04-05 · commits e3c9afe~80f68e4）

- **Route C 決策**：採用 PyO3 直接調用（非 IPC 透傳），增量編譯 3.7s 可接受
- **openclaw_pyo3 擴展**：新增 `bybit_bridge/` 模組（4 文件 ~510 行），依賴 `openclaw_engine`
- **BybitClient #[pyclass]**：39 個 Python 方法覆蓋 Account(8) + Order(6) + Position(4) + MarketData(8) + Instrument(6) + Util(7)
- **async→sync 橋接**：每個 BybitClient 持有獨立 tokio::Runtime（2 worker threads），不干擾 Python asyncio
- **序列化**：pythonize crate 自動 Serialize→PyObject，無雙重序列化
- **settleCoin 處理**：查詢無 symbol 時自動添加 settleCoin=USDT（Bybit V5 要求）
- **Python 整合**：strategy_ai_routes.py demo/* 4 端點 Rust-first + BybitDemoConnector fallback
- **API venv 安裝**：openclaw_core 安裝到 FastAPI venv，服務重啟後 `source=rust_engine` 確認生效
- **全盤驗證**：PM/CC 34/34 E2E PASS · FA 37/37 LIVE · PA 4/4 source=rust_engine · E2 0 FAIL · E4 4609 全綠 · E5 0 OPTIMIZE
- **2 Flaky test 修復**：TestGetKlinesRoute 需 mock get_rust_reader（Rust-first 路徑返回真實數據）
- **engine 修改**：order_manager.rs + position_manager.rs 各增 pub parse wrapper（供 PyO3 調用）

### RC-12 + Klines Snapshot + Rust-first 改造 + 全面審計（2026-04-04）

- **RC-12**: 停用 Python MarketDataDispatcher 自動啟動（消除重複 Bybit WS 連接）
- **Klines in snapshot**: Rust 引擎寫 1m K 線到 pipeline_snapshot.json（每 symbol 100 根）
- **Rust-first 改造**: get_klines + get_indicators 所有 timeframe → 10/13 策略讀路由 Rust-first
- **全面審計**: 無活躍重複處理，無重複進程，7 個 Python 交易組件全部休眠

### RC-11 + 既有 Bug 修復 + Governance 清理（2026-04-04）

- **RC-11**: 消除 Python/Rust 止損雙重執行 — `MarketDataDispatcher._trigger_tick()` 移除 `engine.tick()` 調用
- **10 既有 Bug 修復**: 5 個 Rust-first 響應格式 + 5 個測試隔離汙染 → 3345 passed / 0 failed
- **Governance 清理**: governance_hub.py 5 個死方法標記 DEPRECATED (RC-11)，bridge_core.py activate() 精簡
- **分析**: governance_routes 遷移可行性（18/29 可 IPC relay），symbol/gate IPC 暴露風險評估

### Phase 0b 完成（2026-04-04）

- 0b-06~08: 9 compression policies (7d/14d) + 15 retention policies (90d/180d/365d) + sync_commit 分層
- 0b-09~11: grafana_data_writer INSERT 改為 _legacy 表名，Grafana VIEWs 橋接驗證通過
- 0b-13: requirements-ml.txt 創建（lightgbm/optuna/sklearn/onnx/shap/duckdb/pyarrow）
- 0b-14: ML 模型降級策略文檔化（3 級 fallback：rule-based → LightGBM → fixed 0.5）
- 0b-15: OU Grid spacing 修正 σ/√θ → σ·√(2/θ)（首次穿越時間正確推導）
- 0b-16~19: E4 4507 全綠

### Phase 0b TimescaleDB 啟用（2026-04-04）

- Docker image 切換：postgres:16 → timescale/timescaledb:latest-pg16 (v2.26.1)
- shared_preload_libraries 配置 + CREATE EXTENSION timescaledb
- 28 hypertables 啟用（11 market + 7 trading + 3 agent + 1 learning + 4 obs + 2 risk）
- 修復 risk.black_swan_events PK (event_id) → (event_id, ts) 以支持 hypertable
- 修復 V004 risk.correlation_pairs `window` SQL 保留字（加引號）
- 15 張非時序表保持 regular（model_registry, symbol_clusters, bayesian_posteriors 等）
- 舊 postgres:16 Docker image 已刪除

### Phase 0a DDL 執行（2026-04-04）

- V001-V005 DDL 全部執行完成：8 schemas + 43 tables + 87 indexes + 11 Grafana VIEW bridges
- 修復 V004 `window` SQL 保留字問題（加引號）
- 14 張舊表中 11 張重命名為 `*_legacy`，VIEW 橋接確保 Grafana 不斷
- 備份：`backups/trading_ai_pre_phase0a_20260404_180411.dump` (186K)

### R-IPC IPC-01~IPC-06（2026-04-04）

- **IPC-01** Rust PipelineSnapshot 擴展：+indicators(per-symbol) +signals(100) +strategies +recent_intents(50) +recent_fills(50)
- **IPC-02** Python ipc_state_reader.py 5 新方法：get_indicators/get_signals/get_strategies/get_recent_intents/get_recent_fills
- **IPC-03** 8 條 API 路由遷移為 Rust-first + Python fallback（indicators/signals/strategies/intents/fills + summary/list/status）
- **IPC-04** PipelineBridge 降級為 IPC 中繼 + Agent 回調容器（docstring + activate/on_tick DEPRECATED）
- **IPC-05** 分類 B 降級推遲（需 API 寫操作路由遷移到 Rust 命令通道後）
- **IPC-06** 全量測試 4507 全綠
- 測試基準線不變：Python 3877 / Rust 592 / Canary 38 = 4507

### R-CUT Phase 3 Go/No-Go RC-14~RC-15（2026-04-04）

- **RC-14** Go/No-Go 7/7 PASS：新 binary 編譯+重啟，201K tick replay 壓測通過
  - RSS 2.1MB | P50=27μs P95=28μs P99=29μs | 0 crash | 5 fills in 4.97s
- **RC-15** Go/No-Go 評估報告完成
- Rust 引擎正式成為唯一 tick 處理引擎

### R-CUT Phase 2 最小切換 RC-10~RC-13（2026-04-04）

- **RC-10** Python tick_pipeline 停用：2 處 activate() 註釋掉，PIPELINE_BRIDGE 保留供 API/GUI
- **RC-11** Category A dead code 刪除：4 files / 1,003 行（shadow_decision_tracker, dream_engine, opportunity_tracker, strategy_health_monitor）
- **RC-12** 全量測試驗證 4507 全綠零回歸
- **RC-13** E2 + E4 PASS
- 註：原估 187 files 實為 Category B+C，需 R-IPC API 路由遷移後才能大規模清理

### R-CUT Phase 1 策略補齊 RC-01~RC-09（2026-04-04）

- **RC-01** MA Crossover Hurst regime filter：mean_reverting/random_walk 市場阻止入場，cold-start 安全
- **RC-02** MA Crossover multi-TF：EMA of sma_50 (alpha=0.01) 作為 4h 趨勢代理，方向不符阻止入場
- **RC-03** BB Breakout 參數可配置化：squeeze_bw/expansion_bw/volume_threshold 從 const 改為 pub 欄位
- **RC-04** 所有策略 on_rejection() 回滾：prev_* 快照 + 恢復，Strategy trait 新增 default no-op
- **RC-05** 所有策略 on_fill() 回調：trait default no-op，tick_pipeline 接線完成
- **RC-06** Grid Trading geometric spacing + health check + auto-rebalance：GridSpacingMode enum + GridHealth + 200-tick 健康檢查
- **RC-07** BB Reversion limit order 真實實現：use_limit + limit_offset_bps，策略端 REAL（execution 層 Phase 2）
- **RC-08** StrategyParams trait + ParamRange 定義：Phase 3a stub，param_ranges()/validate()
- **RC-09** E2 APPROVE + E4 4507 全綠 + QA Audit CONDITIONAL PASS（0 FAKE features）
- Orchestrator 新增 strategies_mut()，tick_pipeline 改為逐策略處理含 rejection/fill 回調
- Canary watchdog test fix：grace_period=0 修復 test_missing_file_triggers_crash
- 測試基準線：Python 3877 / Rust 592 / Canary 38 = **4507** (+62)

### Rust Cutover Decision + Comprehensive Indicator Alignment（2026-04-04 · commits 2a253d9, 69b03aa, 5ed077b）

- **Operator 決策：放棄修 Python V2，全力 Rust** — QA 嚴格審計 Python V2 真實成熟度 62/100，6 項功能 FAKE/DEAD/UNREACHABLE
- **Replay Mode B**：tick_duration_us + feed_replay_tick() 100% 複用 on_tick，201K tick 完整回放驗證
- **ADX Bug 修復**：Python ADX 返回 DX 而非 ADX — 補 Wilder 平滑第三步
- **Comparator 大幅改進**：key 映射（66 keys）、bar-close filter、paper_state skip、容差放寬（1e-6/1e-2/5e-2）
- **Rust 指標對齊**：Hurst 安全修復（P0）、KAMA SMA seed、IndicatorSnapshot +3（sma_50/ema_26/atr_5）、conservative_atr
- **Rust 策略強化**：BB Breakout ATR trailing stop + regime exit（mean_reverting/random_walk）
- **Python 指標修復**：KAMA per-step SC、Stochastic Fast→Slow、signal_generator 9x NoneType guard
- **Rust 引擎完整度確認**：99.9% 獨立，零 Python 依賴，16 指標 / 8 信號 / 4 策略 / Guardian / Governance
- TODO 全面重構：新增 R-CUT（Rust 切換）和 R-IPC（IPC 擴展）階段，Kelly/FundingArb 雙腿延後到 Phase 2/1

---

### Cold-Start Fix + Phase 0a DDL Draft（2026-04-04 · commit f6ab650）

- **3-STRIKE 崩潰修復**：根因分析確認為 Cold Start Jitter（非代碼 bug），watchdog threshold 45s + grace-period 120s + Rust 引擎 force_write 初始快照
- **Go/No-Go 文檔更新**：INC-001 事件記錄 + 判定條件細化（穩態 0 崩潰，啟動寬限期不計）
- **Phase 0a DDL 草稿**：6 檔案 / 43 表 / 8 Schema / 29 hypertable（conditional）/ V001-V005 遷移框架
- **PYO3-1 推遲**：接口錯位（Rust distill→cycle_data vs Python→IntelObject），推遲到 Phase 2 Decision Context
- E2 審查 5 項修正（index_price NULL bug、scorer VIEW 注釋、unused import、table count、注釋一致性）+ E4 全綠 3839+36

---

### Tech Debt Zero + Engine Launch（2026-04-03 · Session 11 final）

- Rust StateWriter atomic write（.tmp → rename）防止 IPC 讀半寫
- 3 文件 DEPRECATED 標記（governance_hub / paper_trading_engine / strategy_auto_deployer）
- 4 個 IPC 測試修復（Rust reader mock for pipeline_stats + session_status envelope）
- Watchdog threshold 30s→60s（防假告警）
- **Rust 引擎灰度模式啟動**：5 symbols × 4 strategies，Go/No-Go 2026-04-10

---

### R07-1 Replay Runner + Accelerated Canary Plan（2026-04-03 · Session 11）

**replay_runner.py**：歷史回放取代即時灰度（22 天 → ~7 天）
- Bybit REST API 分頁獲取歷史 1m K 線 → 4 tick/bar 合成
- Python KlineManager + IndicatorEngine + SignalEngine 全管線回放
- 已驗證：7 天 × 5 幣種 = 201,600 ticks，300 秒完成
- 輸出 shadow_results.jsonl 匹配 canary schema V1.0.0

**R-07 代碼全部完成**：replay_runner + CanaryRecord + Comparator + Watchdog + Rollback Drill
**剩餘工作**：啟動 Rust 引擎即時灰度 7 天 → Go/No-Go → 正式完成

---

### Test Debt Zero — All 28 Failures + 17 Errors Resolved（2026-04-03 · Session 11）

**28 failed + 17 errors → 0 failed, 0 errors, 3839 passed（+45 淨增）**
- 7 類過期測試斷言（E/F/H/I/K/M/N）：operator config 改變後測試未同步
- 4 類測試隔離缺陷（B/C/D/G）：mock 不完整、config 未隔離、event loop 缺失
- 2 類基礎設施（A: pytest-asyncio 安裝、L: importlib→標準 import）
- 1 類實現追蹤（J: L2 dispatch 從 Thread 改為 model_router）
- FA 確認 + E1 並行修復 + E4 全量回歸驗證

---

### R-07 Canary Tooling — Comparator + Watchdog + Rollback（2026-04-03 · Session 11）

**R07-3 Canary Comparator:**
- `canary_schema.py`：JSONL schema contract (V1.0.0) + 3-tier tolerance mapping + validation
- `canary_comparator.py`：tick-level comparison (indicators, signals, paper state, intents) + boundary divergence escalation (V3-QC-5) + CLI + daily reports

**R07-6 Engine Watchdog:**
- `engine_watchdog.py`：snapshot freshness monitor + crash/recovery detection + 3-strike rollback rule + CLI + status API helper

**R07-5 Rollback Drill:**
- `rollback_drill.sh`：8-step rehearsal script (stop engine → verify fallback → git checkout → restart → health check) + SLA timing + dry-run mode

**35 tests all PASS** covering: schema (5) + comparator (14) + watchdog (11) + integration (5)

---

### R-06 Python IPC Integration Complete（2026-04-03 · Session 11）

**R06-D conftest IPC mock fixtures:**
- 新增 5 個 pytest fixtures（rust_snapshot_dir, rust_reader_available/unavailable, patch 版本）
- SAMPLE_PIPELINE_SNAPSHOT 共享測試數據
- 12 處 SM import TODO 標記保留（SM 仍為 Python，R-07+ 處理）

**R06-E IPC 集成測試 53 個：**
- test_ipc_state_reader.py：14 個基礎讀取器測試（Session 10）
- test_ipc_integration.py：39 個（reader supplement + route logic + source tag + edge cases + rollback simulation）

**R06-F 回滾預演：**
- TestRollbackSimulation 6 個測試：crash → fallback → recovery lifecycle
- SLA 驗證：fallback < 100ms（要求 < 30s）

**R-06 Go/No-Go 門控全部通過：**
- 4/7 routes IPC 改造完成（3 個有意 defer）
- 53 IPC 測試全 PASS
- Python 3794 pass ≥ 3500 基準
- 回滾 SLA < 100ms
- conftest fixtures 已加入

**測試基準線：** Python 3794 passed / 28 failed / 17 errors / 1 skipped + Rust 552 passed / 0 failed

---

### R-05 Engine Integration + Bybit API Compatibility（2026-04-03）

**Engine Live Wiring:**
- main.rs 接入 TickPipeline（替換 placeholder event consumer）
- 5 幣種（BTC/ETH/SOL/XRP/DOGE）× 4 策略（MA/BB-Rev/BB-Break/Grid）
- Paper auth 啟動自動授予 + 定期 status report + JSON/JSONL 持久化
- 10 分鐘 Bybit Live WS 實測：38,389 ticks, 8 fills, 零崩潰
- Fix: check_stops 跨幣種價格污染（BTC price 更新 ETH best_price）
- Fix: Strategy trait 加 Send bound（tokio::spawn 兼容）
- Fix: rustls ring crypto provider 安裝

**29 壓力集成測試（stress_integration.rs）：**
- Fast track 緊急通道（CloseAll/Reduce/Pause + 5%/90% 邊界）
- 多幣種混合（5 幣 500 ticks + 快速交替 1000 ticks）
- 策略邊界（whipsaw/oversold/false squeeze/breakout/grid traversal）
- Guardian + Governance（drawdown/conflict/position limit/no auth）
- 止損邊界 + 管線吞吐（10k ticks + 26.9μs release tick latency）
- PnL 正確性 + 持久化驗證

**QC 數學模型審查：45+ 公式 APPROVED（3 MINOR 非阻塞備註）**

**9 項 Bybit API 兼容性修復：**
1. [CRITICAL] qty_step 精確取整（替代硬編碼 3dp）
2. [CRITICAL] minOrderQty/maxOrderQty/minNotional 驗證
3. [CRITICAL] positionIdx 包含在所有非 spot 訂單中
4. [HIGH] kline confirm 欄位檢查（只處理已確認 K 線）
5. [HIGH] API rate limit 頭部讀取 + 預請求限流
6. [HIGH] 止損價格方向感知取整（long floor / short ceil）
7. [MEDIUM] HTTP vs Bybit retCode 區分（errorType 字段）
8. [MEDIUM] 指數退避重試（瞬態錯誤自動重試）
9. [MEDIUM] accountType 動態檢測（替代硬編碼 UNIFIED）
- 額外：Registry linear 優先（spot 不再覆蓋 linear instrument info）

**V2 Bybit Demo Live 驗證：BTC+ETH 端到端下單 PASS，帳戶模式檢測 PASS**

**測試基準線：3,741 Py (+38 新) + 548 Rust (+31 新) = 4,289 total, 零回歸**

---

### Phase R-04 完成 — Engine 完整交易路徑（2026-04-03）

**Batch 1（核心管線）：**
- `tick_pipeline.rs`：on_tick 6 步編排 + KlineManager→IndicatorEngine→SignalEngine→策略→執行→止損
- `intent_processor.rs`：H0→Guardian→CostGate→Governance→OMS 意圖處理管線
- `fast_track.rs`：緊急路徑（CircuitBreaker→CloseAll / Defensive→ReduceToHalf）

**Batch 2（5 策略）：**
- `strategies/ma_crossover.rs`：KAMA + ADX≥20 + 5min cooldown
- `strategies/bb_reversion.rs`：%B<0+RSI<30 入場 / %B 0.2-0.8 出場
- `strategies/bb_breakout.rs`：壓縮→擴張+Volume≥1.5x+Donchian 確認
- `strategies/grid_trading.rs`：OU 動態間距 + 2×fee floor + 庫存上限
- `strategies/funding_arb.rs`：delta 中性 + 34bps 成本模型 + 72h 最大持倉（等 R-06 IPC 接入資金費率）

**Batch 3（狀態+持久化）：**
- `paper_state.rs`：持倉追蹤 + 止損檢查 + PnL 計算 + 狀態導出
- `persistence.rs`：JSON debounced write + JSONL append-only 審計

**API 適配：**
- `IndicatorSnapshot` 添加 `Default` derive
- `snapshot_to_input()` 適配器：IndicatorSnapshot（nested）→ IndicatorInput（flat）
- 策略 cooldown 修復：首次交易允許通過（`last_trade_ms > 0` guard）

**測試基準線：** Rust 517 (376 core + 8 golden + 19 extreme + 78 engine + 36 types)

---

### Phase R-03 完成 — core 下半：SM + 執行 + 回測（2026-04-03）

**Batch 1（4 SM 狀態機）：**
- `sm/auth.rs`（601 行）：8 狀態 + 16 遷移 + 7 禁止 + 5 守衛 + 過期守護（15 tests）
- `sm/lease.rs`（538 行）：9 狀態 + 18 遷移 + 12 禁止 + revoke_all_live（14 tests）
- `sm/risk_gov.rs`（583 行）：6 級風控 + 23 遷移 + 自動升級 + 持有時間守衛 + 6 級約束（14 tests）
- `sm/oms.rs`（548 行）：11 態訂單生命週期 + 16 遷移 + 12 禁止 + 對賬（11 tests）
- `sm/mod.rs`（90 行）：TransitionRecord + SmError + now_ms

**Batch 2（GovernanceCore 級聯）：**
- `governance_core.rs`（490 行）：all-or-nothing risk→auth→lease 級聯 + evaluate_and_cascade + 紙盤授權（12 tests）

**Batch 3（確定性檢查 + 執行）：**
- `guardian.rs`（270 行）：4 項確定性風控檢查 + 裁決邏輯（7 tests）
- `execution.rs`（262 行）：滑點分層 + 成交價 + 手續費 + 損益（16 tests）
- `order_match.rs`（267 行）：限價單匹配 + 部分成交率（10 tests）

**Batch 4（組合 + 止損 + 消息 + 歸因）：**
- `portfolio.rs`（331 行）：Pearson 相關 + 3 層檢查 + 組合指標（7 tests）
- `stop_manager.rs`（325 行）：hard/trailing/time 3 止損 + ATR 倉位計算（14 tests）
- `message_bus.rs`（257 行）：6 角色消息路由 + 衝突解決（6 tests）
- `attribution.rs`（235 行）：6 因子分解 + 聚合（9 tests）

**Batch 5（回測引擎）：**
- `backtest.rs`（438 行）：逐 K 線回放 + SignalGenerator trait + Sharpe/drawdown（9 tests）

**Batch 6（極端組測試）：**
- `tests/golden_extreme.rs`（287 行）：SM 級聯壓力 + 執行邊界 + 止損邊界 + 組合極端（19 tests）

**測試基準線：** Rust 468 (376 core + 8 golden + 19 extreme + 29 engine + 36 types) · Python 3703/24/17 零回歸

---

### Phase R-02 完成 — core 上半：感知 + 認知 + 風控（2026-04-03）

**Batch 1（小型獨立模組）：**
- `attention.rs`：5 級注意力（Dormant→Critical）+ 波動性跳動檢測 + 訂單接近度（11 tests）
- `cognitive.rs`：CognitiveModulator EMA 平滑 + R1-5 連虧忽略 + dream blend（13 tests）
- `opportunity.rs`：OpportunityTracker 虛擬 PnL + 2x fee + 遺憾方向判定（18 tests）
- `dream.rs`：DreamEngine 蒙特卡洛 + binomial test + 重入鎖（20 tests）

**Batch 2（中型模組）：**
- `klines.rs`：KlineManager 多時間框架聚合 + Kahan 補償求和（18 tests）
- `h0_gate.rs`：H0Gate 5 項門控 fail-fast + shadow mode + <1ms SLA（30 tests）

**Batch 3（13 指標引擎）：**
- `indicators/` 拆分 5 文件：trend(SMA/EMA/MACD/KAMA/Donchian) + momentum(RSI/Stoch/ADX) + volatility(BB/ATR/Hurst/EWMA) + volume(VolumeRatio)
- Kahan 求和：SMA/KAMA/ADX/VolumeRatio/RSI [V3-QC-2]（33 tests）

**Batch 4（信號 + 風控）：**
- `signals/`：8 規則（RSI OB/OS, MA Cross, BB Reversion, MACD, exits, divergence, regime）+ QC 邊界豁免 + SignalEngine 共識（30 tests）
- `cost_gate.rs`：5 級成本分層 + ATR vs 成本門檻（11 tests）
- `risk/`：RiskConfig P0/P1/P2 + 動態止損(ATR+regime) + 8 優先級 tick 檢查 + PriceHistoryTracker（45 tests）

**Batch 5（Golden Dataset）：**
- `tests/golden_dataset.rs`：合成數據 13 指標交叉驗證 + Kahan 精度 + 確定性再現（8 tests）
- `helper_scripts/golden_dataset_gen.py`：Python 對照生成器

**審查：** E2 CONDITIONAL→PASS（移除 opportunity.rs 未用 next_id）· E4 PASS 零回歸
**測試：** Rust 302 passed（+237 vs R-01）/ Python 3703 passed（不變）

---

### Phase R-01 完成 — IPC + shared_types + WS + Workspace 統一（2026-04-03）

**Batch 0 — Rust workspace 合併：**
- PA 評估後建立 `openclaw_pyo3` 獨立 crate（cdylib），隔離 PyO3 extension-module
- 從 `srv/rust/` 遷移 ContextDistiller + HedgingEngine 到 workspace
- 4 crates 統一：openclaw_types / openclaw_core / openclaw_engine / openclaw_pyo3
- `maturin develop --release` 驗證 Python `import openclaw_core` 不變

**R01-1~4 Rust Engine 模組：**
- `config.rs`：ArcSwap<RuntimeConfig> 熱加載 + 冷/熱參數分類 + TOML 解析（7 tests）
- `ipc_server.rs`：Unix domain socket JSON-RPC 2.0 server + 5 方法 handler（11 tests）
- `ws_client.rs`：Bybit WS client + 指數退避重連 + PriceEvent 推送（9 tests）
- `main.rs`：tokio multi-thread runtime + SIGHUP 配置重載 + 優雅關機（2 tests）

**R01-5~7 Python IPC 層：**
- `shared_types.py`：10 types（4 enum + 5 dataclass + PriceEvent），與 Rust 1:1 對齊
- `ipc_client.py`：EngineIPCClient + 自動重連 + 3 次失敗降級 + per-method TTL
- `ai_service.py`：AIService（5 agent handler stubs）+ AIServiceListener（Unix socket 服務端）

**R01-8~9 測試基礎設施：**
- conftest.py：shared_types 導入重定向 + SM 類標記 `TODO R-06`
- Golden schema (`schemas/shared_types.json`) + `schema_diff.py` 驗證 + CI 集成

**審查修復（E2 + E5）：**
- CRITICAL：StopConfig Rust `time_stop_minutes` → `time_stop_hours` + `atr_multiplier` 三方對齊
- HIGH：ai_service.py 從 length-prefix 統一為 newline-delimited 協議
- MEDIUM：ipc_client.py `ping()` 修正匹配 Rust `"pong"` 回應
- E5：ws_client.rs `extract_symbol_from_topic` 零分配 rsplit + ipc_client assert→explicit check

**測試：** Rust 65 passed / Python 3703 passed / 24 failed / 17 errors（零回歸）

---

### Phase 3 完成 — Claude API + 四階段放權 + HedgingEngine Rust（2026-04-03）

**Sub-phase 3A（Claude API 閉環）：**
- **3-1** APIBudgetManager：月度預算 $50 + per-tier 冷卻（l1_5=1800s, l2=3600s） + 持久化
- **3-2** ModelRouter 四級路由：l1_9b / l1_27b / l1_5 / l2 + 升級/阻止條件 + budget_checker 回調
- **3-3** Claude→TSR 閉環：knowledge_update 寫入 TruthSourceRegistry + confidence cap（0.90/0.85）+ prompt 查詢 TSR
- **3-5** PnL Attribution API：4 個只讀端點（summary/strategy/skill-ratio/trade）

**Sub-phase 3B（新模組 + 放權）：**
- **3-4** HedgingEngine **Rust+PyO3**：組合 delta 計算 + 對沖建議（linear/spot/inverse）
- **3-6** OB Imbalance：calculate_ob_imbalance + get_ob_signal 整合到 microstructure_builder
- **3-7** DelegationFramework：四階段遞進放權（FULL_HUMAN→AI_SUGGEST→AI_ACT_VETO→FULL_AI）+ 自動降級

**E5 修復（Phase 2 補跑）：** UTF-8 安全截斷 + paired_state 還原 + HurstHysteresis 提取 + L1 凍結
**審查：** E2 全部 PASS · E4 零回歸 3703/24/17

---

### E5 優化修復 + L1 凍結（2026-04-03）

- **E5-1** context_distiller.rs UTF-8 安全截斷：`summary[..80]` → `summary.chars().take(80).collect()`，防止中文 panic
- **E5-2** funding_rate_arb.py `_paired_state` 重啟還原：`restore_persistent_state()` 補齊 PairedExecutionState 反序列化
- **E5-3** HurstHysteresis 提取：從 market_regime.py（814→706 行）獨立為 hurst_hysteresis.py（129 行）
- **2-L1** L1 接口凍結：`git tag l1-interface-freeze`，Operator 簽核確認
- E2 審查：3/3 PASS · E4 回歸：3704 passed / 23 failed / 17 errors（+1 pass, -1 fail vs 基準）

---

### Phase 2 完成 — 策略 V2 + Agent 整合 + Rust 基礎設施（2026-04-03）

**策略 V2 升級（5 個策略全部完成）：**
- **2-1**：MA_Crossover V2 — KAMA + ADX>20 過濾 + 多時間框架確認
- **2-2**：BB_Reversion V2 — RSI<30 確認 + Hurst Regime 感知（trending 不交易）
- **2-3**：BB_Breakout V2 — Volume ratio>1.5 + Donchian 確認 + ATR trailing stop
- **2-4**：FundingRateArb V2 — PairedExecutionState + filled_qty 回滾（非 requested_qty）
- **2-5**：GridTrading V2 — OU 動態間距（σ/√θ + 2×fee_pct 下限）
- **2-6**：Regime Detection — HurstHysteresis（6 bar 確認）+ EWMA Vol 三維 regime

**Agent 整合（3 個任務）：**
- **2-7**：Strategist 雙軌 — 快速通道/正常通道 + _emergency_mode 競態保護 + CognitiveModulator 閉環
- **2-8**：ContextDistiller — **Rust+PyO3 首個模組** · Mutex 線程安全 · 4 區塊壓縮（market/portfolio/health/events）
- **2-9**：Ollama prompt 模板 — 結構化 JSON + cognitive/dream 欄位 + plain-text fallback

**Rust 基礎設施（R-00-mini）：**
- Cargo workspace (`Cargo.toml`) + `rust/openclaw_core/` crate
- PyO3 0.24 + maturin 構建 → Python 可直接 `import openclaw_core`
- 決策：新獨立模組 Rust+PyO3，修改現有文件繼續 Python

**測試基準**：3703 passed / 24 failed / 17 errors（+1 fail 為 pre-existing async 環境問題）
**業務完成度**：82% → ~93%

---

### Phase 1 完成 — Agent 感知工具箱 + 認知三模組（2026-04-03）

**新建模組（8 個文件）：**
- **1-1**：PositionSizer（已在 0B-3 完成）
- **1-2**：strategy_health_monitor.py — CUSUM 漂移檢測 + rolling Sharpe + 15 連虧硬性兜底
- **1-3**：ewma_vol_estimator.py — EWMA 波動率估計 + vol regime 分類
- **1-4**：hurst_exponent.py — R/S 重標極差分析 + 趨勢/均值回歸分類
- **1-5**：indicators/extended.py — KAMA + ADX + Hurst + EWMA Vol + Volume Ratio + Donchian
- **1-6**：cognitive_modulator.py — L0 決策門檻調製（[Q1] max 單因子 + [Q6] EMA α=0.3）
- **1-7**：opportunity_tracker.py — 虛擬 PnL 追蹤（[Q2] 2x fee + [Q3] 歸一化 + [R1-8] ≥5 樣本）
- **1-8**：dream_engine.py — 蒙特卡洛模擬（[Q4] ≥30 輪 + [Q5] binomial test）
- **1-9**：local_llm_client.py — ABC + OllamaProvider + LMStudioProvider
- **1-10**：shadow_decision_tracker.py — 四階段退出條件比較

**附帶修復**：SMA 改用 math.fsum()（V3-QC-2）+ indicator_engine.py 注冊 6 個新指標
**測試基準**：3704 passed / 23 failed / 17 errors（無回歸）
**業務完成度**：72% → 82%

---

### Phase 0-A + 0-B 完成 — 學習閉環 + 策略 Edge 驗證（2026-04-03）

**Phase 0-A（學習閉環 + 管線連通）：**
- **0A-1**：學習反饋閉環 — StrategistAgent.get_strategy_weight() + PipelineBridge 門控前應用學習權重
- **0A-2**：進化參數自動重部署 — evolution_routes.set_auto_deployer() B13 閉環
- **0A-3**：H0 Gate shadow 觀察模式 — shadow_mode 旗標 + _check_shadow() + shadow stats/log
- **0A-4**：Scanner→Deployer 驗證 — 確認已完整接通（無需修改）
- **0A-5**：Backtest 生產環境啟用 — AutoDeployer.set_backtest_engine() + 部署前回測驗證
- **0A-6**：L2 觸發門檻 50→20 — 加速 AI 模式發現反饋

**Phase 0-B（策略 Edge 驗證）：**
- **0B-1**：FundingRateArb 精算 — 滑點建模 + 基差風險追蹤 + 多周期攤薄 + get_cost_summary()
- **0B-2**：交易所 SL/TP 雙重防線 — SL 5% + TP 8%（PipelineBridge + Executor callback）
- **0B-3**：Kelly 資本配置 — position_sizer.py（Kelly 四層計算）+ tab-ai.html Kelly 卡片 + API 端點

**新建文件**：position_sizer.py（~306 行）
**測試基準**：3704 passed / 23 failed / 17 errors（改善 +1 pass / -1 fail）
**業務完成度**：52% → 72%

---

### Rust 遷移 V3-FINAL + 階段拆分 + 全路線圖定稿（2026-04-03）

- **Rust 遷移 V3-FINAL** 五角色三輪審查通過（V2→V2.5→嚴格論證 21 FAIL→V3 全部納入）
- 32,500 行 Rust · 14 週主開發 · Single-owner actor 零鎖 · QC 分級浮點容差
- Week 8 硬決策點（Go/No-Go · 50% 復用降級路徑）
- 8 個階段執行文件 `docs/rust_migration/R-00~R-07`，每個自包含上下文+進度追蹤
- 全路線圖定稿：Phase 0-3（功能 7 週）→ Phase R（Rust 14 週）→ 灰度 → Live
- Phase 1-3 新增里程碑：R-00 提前並行 · L1 接口凍結（Phase 2 結束）· L2 凍結（Phase 3 結束）
- 16 Agent profiles 已升級 Rust/認知自適應技能
- Live 前置條件新增：Rust 遷移完成或 PyO3 降級穩定

---

### 文檔治理 + 系統快照 + 根原則校準（2026-04-03 · commits 97e152c → edf4627）

**文檔治理（6 commits）：**
- README.md 全面更新：狀態日期→04-03、測試 3440→3704、業務完成度 45%→52%、Phase 路線圖重排
- 修正 "6 Agent" → "5 Agent + Conductor"（CLAUDE.md / README.md / CC profile / governance_extracts）
- 原則 #12 加 demo 階段說明（live 自動部署待 Phase 3 放權框架）
- 新增實施準則：認知調製 ≠ 能力限制（衍生自原則 #11，否決代謝模型和內部經濟體）
- 明確 Bybit 專攻決策：Binance 排除當前開發範圍，僅作超長期可能方向
- 5 個 governance_extracts 標記 OUTDATED + 指向權威文件
- SYSTEM_STATUS_REPORT.md 歸檔到 docs/references/
- 跨平台部署說明加入 README（macOS 遷移路徑）

**系統快照（1 commit）：**
- 生成 SYSTEM_SNAPSHOT.md（8 章節：結構樹 / 15 模組簽名 / 啟動流程 / 數據流 / 線程架構 / 性能路徑 / 配置管理 / 外部依賴）
- 供外部 Claude session 分析系統架構

**跨平台兼容性審計（2 commits，by user）：**
- CLAUDE.md §七新增跨平台強制規則（路徑不硬編碼 / LLM 抽象 / systemd→launchd / 依賴管理）
- XP-1~4 P0 審計任務完成

**其他（by user）：**
- 中期路線圖 Phase 0-3 制定（7 週 · 4-Agent 分析）
- Agent 認知自適應 SPEC V1.1+R1（見下方獨立條目）
- 16 Agent workspace profiles 升級

---

### Agent 認知自適應 SPEC V1.1+R1 五角色審查通過（2026-04-03）

**內容**：V3 報告補充規範，三個 L0 新模組的完整設計（零 API 成本，純本地計算）

- **CognitiveModulator**（0.5d）：根據歷史表現動態調整 confidence floor / qty ceiling / SL multiplier / scan interval
- **OpportunityTracker**（1.0d）：追蹤被 Scout/Strategist/Guardian 篩掉的機會虛擬 PnL → 遺憾歸因
- **DreamEngine**（2.0d）：閒置時用真實 K 線跑蒙特卡洛模擬 → 參數優化建議

**五角色審查（PM/PA/FA/E5/QC）+ 兩輪審計**：
- QC 數學修正 6 項：多因子取 max（防隱性停機）· 虛擬 PnL 扣 fee（防系統性高估）· 歸一化遺憾方向 · 每參數 ≥30 輪模擬 · binomial test 置信度 · EMA 平滑
- E5 代碼修正 6 項：拆分 _compute_*() · bullets_dodged 重命名 · _flush_closed · 緩存 · threading.Lock · 隨機方向
- Round 1 修正 10 項：scan 雙向 · 緩存失效 · 防重入 · asyncio.to_thread · 連虧忽略負向 · import 頂層 · 估時調整 · 最少 5 樣本 · fee 注釋 · 可選 seed
- 最終判定：5/5 APPROVE
- 開發位置：Phase 1 並行組 B（1.10/1.11/1.12），總計 3.5d，不影響關鍵路徑
- SPEC 文件：`docs/references/2026-04-03--agent_cognitive_adaptation_spec_v1_draft.md`

---

## Wave 進度總表（§十三.4 遷出）

```
Wave 0：✅ P0（5 項）全部完成 + P1（5 項）全部完成（E2+E4 通過）
Wave 1：✅ PA-4.3 DI 統一（26 Depends）+ HTTPException 穿透（E2+E4 通過）
Wave 2：✅ P0-8/P1-1/P1-2/P1-6/P1-8/P1-9/P1-13/P1-18 全部完成（E2+E4 通過）
Wave 3a：✅ P0-NEW-1/2/3 全部完成（E2+E4 通過，commit c6a8845）
Wave 3b：✅ P1-NEW-1~7 全部完成（E2+E4 通過，commit 2eda4ec）
Wave 3c：✅ P1-4/P1-10/P1-17 完成（E2+E4 通過，commit bf75254）
P1-16：✅ Day 1+2+3 全部完成，已 merge（commit 03a5b29）
Wave 4 Sprint 4a：✅ P2-NEW-1/2/6（commit a2f4c70）
Wave 4 Sprint 4b：✅ P2-NEW-3/4 + P3-TECH-1/2/3（commit 6c80bc9）
Wave 4 Sprint 4c：✅ P2-NEW-7/8（commit 448f1e7）
Wave 4 Sprint 4d：✅ FA-2/3/4（commit 9cc134a）
Wave 4 Sprint 4e：✅ P2-NEW-9 + P2-NEW-5（commit 87c2651）
Wave 5a：✅ Position Sizing 重構 — 3% risk + 動態 qty + 智能資本再分配（commit 8223eb9）
Wave 5b：✅ Paper/Demo 同步修復 — 3 CRITICAL + 2 MODERATE
Wave 5 Sprint 0：✅ G-05 acquire_lease + G-01 AI daily cap $15→$2（commit d57ed05）
Wave 5 Sprint 5a：✅ H0 blocking + H1 ThoughtGate + shadow=False + H2/H3 ModelRouter（commit ccdff73）
Wave 5 Sprint 5b：✅ H4 validate_output + H5 record_ollama_call + ScoutWorker + P14 集成測試（commit 9478c00）
Wave 6 Sprint 0：✅ TD-1 pipeline_bridge acquire_lease（原則 3 缺口）（commit aafb18b）
Wave 6 Sprint 1a：✅ FA-7 _check_stops 學習管線注入（原則 12）（commit 8f123a7）
Wave 6 Sprint 1b：✅ 1B-1~4 Cooldown + freshness + cost_tracker + LRU cap（commit 8f123a7）
Wave 6 Sprint 2：✅ P2-6/7/8 risk bounds + P2-12/15 pipeline edge（commit 43dd2f5）
Cleanup Sprint：✅ H0 stale→False + GovernanceHub API + startup integrity + MessageBus load tests（commit 973c595）
Phase 2 Batch 2A：✅ TruthSourceRegistry + Agent 集成 + 46 測試（commit cf7ef5d）
Phase 2 Batch 2B：✅ BacktestEngine MVP + 57 測試（commit cf7ef5d）
Phase 2 Batch 2C：✅ _register_pattern_claims 接通 + backtest_routes + 決策權重集成（commit 5794db1）
Demo 停止補強：✅ cancel_all_orders() + 停止序列改進（commit 2fba698）
Wave 7：✅ Demo 同步修復 — Paper 內部平倉 Demo 同步 + stop_session 自動清倉（commit ab31353）
Wave 7a：✅ Spot 品類啟用 — SPOT-1~5（commit 054d1ae）
方案 A：✅ SymbolCategoryRegistry — 啟動時 API 批量填充（commit a0f87b6）
Wave 7b：✅ Inverse 品類完善 — INV-1~5，32 個測試，動態滑點
Phase 3 Batch 3A：✅ ExperimentLedger + ExperimentRoutes + EvolutionEngine — 88 新測試，3289 passed
Phase 3 Batch 3B+3A-4：✅ TruthSourceRegistry 持久化 + auto_seed + EvolutionRoutes — 3310 passed
Phase 3 Batch 3C：✅ 排程器 daemon + GUI 實驗/進化 dashboard — 3330 passed
Governance Auth 修復：✅ get_status() + /session/reauth + startup 自動補授（commit d065453）
April 1 Audit Batch 1-6：✅ 8 份審計 + 6 批次全部完成 — 3387 passed
Batch 7 積壓清掃：✅ 8 並行 Agent — 3440 passed
main_legacy.py 重構 Wave A-D：✅ 5265→423 行（-92%），拆出 8 模塊，3005 tests 零回歸
Wave 8 PA 實況檢查：✅ 69 項審計交叉驗證 → 38/39 項修復，+148 新測試達 3637+
```

---

## §三 詳細開發記錄（按時間順序）

### Round 2 冷酷功能審核（2026-03-30）

代碼完成度 ≈ 80%，業務功能真正能用 ≈ 45%

逐環節完成度：
- 自動掃描 = 90%（ScoutWorker 30min 定時掃描 + Scout→Strategist bus 鏈路已接通）
- 策略選擇 = 40%（標準技術指標，無 AI、無回測、無動態倉位）
- AI 風險評估 = 55%（H0+H1+H2+H3+H4+H5 全部接通）
- 下單 = 90%（治理 gate + OMS SM-03 + ExecutorAgent 包裝）
- 止損 = 90%（本地 3 類止損 + 交易所條件單雙重防線）
- 學習 = 25%（E1 觀察 + L2 自動觸發 + Sunday cron）
- 進化 = 30%（PaperLiveGate 已部署，無策略自動優化）

關鍵發現：
- ✅ 治理 fail-closed 一流 / P0/P1/P2 風控真實執行 / 異常處理防禦性
- ✅ 5/6 Agent 已實現 / ExecutorAgent 接入管線 / L2 自動觸發
- ❌ Perception Plane register_data() 零調用
- ❌ 策略層標準 RSI/MACD/MA，無可證明的 alpha

詳細報告：docs/governance_dev/audits/2026-03-30--round2_cold_functional_audit.md

### Phase 0 Cowork Round 2.5 審計（2026-03-31）

- P0 修復：MessageBus.subscribe() 3→2 參數 bug / layer2_engine "not worth" 文本解析 bug
- 287 條治理規格 Gap 分析：76% 已實施（67A + 18B + 8C + 2D）
- 關鍵缺失：H0 Gate / 回測引擎 / L3-L5 學習
- 詳細報告：docs/governance_dev/audits/2026-03-31--gap_analysis_287_specs.md

### 7-Agent 全系統審計（2026-03-31）

規模：71 測試文件 / 2,480 測試用例 / 53 app 模組 / 全 HTML/JS/CSS
發現：71 項問題（去重）· P0: 8 / P1: 18 / P2: 29 / P3: 16

4 個 CRITICAL 問題（全部已修復）：
1. /openclaw/{path} 反向代理添加認證
2. _require_operator_role() isinstance 類型錯誤
3. GovernanceHub=None 時 submit_order() fail-closed
4. Guardian=None 時 pipeline_bridge.py fail-closed

合規度 CC B 級 / 安全評級 0 CRITICAL / 0 HIGH / 2 MEDIUM / 3 LOW

### Wave 5a Position Sizing 重構（2026-03-31）

- risk_per_trade_pct 2%→3%（每筆最大虧損 = 總額 3%）
- max_symbols 10→25
- 動態 qty + 智能資本再分配 + risk/stop 反推名義金額

### Wave 5b Paper/Demo 同步修復（2026-03-31）

3 CRITICAL + 2 MODERATE：止損同步 / 失敗標記 / 對賬參數名 / qty 統一 / 條件止損 qty

### Wave 5 Sprint 0 BLOCKER 修復（2026-03-31 · commit d57ed05）

- G-05：executor_agent.py 插入 acquire_lease()（原則 3 硬違反修復）
- G-01：DEFAULT_DAILY_HARD_CAP_USD 15.0→2.0

### Wave 5 Sprint 5a H1-H5 核心接通（2026-03-31 · commit ccdff73）

Scout→Strategist bus 鏈路 / H0 blocking / H1 ThoughtGate MVP / shadow=False / H2 預算 / H3 ModelRouter

### Wave 5 Sprint 5b Agent 落地完善（2026-03-31 · commit 9478c00）

H4 AI 輸出驗證 / H5 CostLogger / apply_ai_consultation DEPRECATED / ScoutWorker daemon / P14 集成測試

### Wave 6 Sprint 0-2（2026-03-31）

- Sprint 0：pipeline_bridge acquire_lease（原則 3 缺口）
- Sprint 1a：_check_stops 學習管線注入（原則 12）
- Sprint 1b：Cooldown smoke test + freshness API + cost_tracker + LRU cap
- Sprint 2：RiskManager qty/price bounds + pipeline edge + collect DEPRECATED + GUI null fix

### Cleanup Sprint（2026-03-31 · commit 973c595）

H0 stale→False / GovernanceHub.is_globally_enabled() / startup integrity check / MessageBus load tests

### Phase 2 Batch 2A-2C（2026-03-31 ~ 2026-04-01）

- 2A：TruthSourceRegistry + AnalystAgent/StrategistAgent 集成 + 46 測試
- 2B：BacktestEngine MVP（純函數指標 + _BacktestKlineAdapter + 57 測試）
- 2C：_register_pattern_claims 接通 + backtest_routes API + 決策權重集成

### Demo 停止清倉補強 + Wave 7 Demo 同步（2026-04-01）

- cancel_all_orders()（普通單 + 條件單）
- Paper 內部平倉 Demo 同步：_sync_close_to_demo() / stop_session 雙遍歷清倉

### Wave 7a Spot + 方案 A SymbolCategoryRegistry + Wave 7b Inverse（2026-04-01）

- Spot 品類：SPOT-1~5 全通（634 幣對）
- SymbolCategoryRegistry：啟動時 API 批量填充 + 運行時部署更新雙層架構
- Inverse 品類：INV-1~5 全通（27 幣對）+ 動態滑點分級

### Phase 3 Batch 3A-3C（2026-04-01）

- 3A：ExperimentLedger + ExperimentRoutes + EvolutionEngine（88 新測試）
- 3B+3A-4：TruthSourceRegistry 持久化 + auto_seed + EvolutionRoutes
- 3C：EvolutionScheduler daemon（週進化 + 小時清理）+ GUI dashboard

### Governance Auth 重啟丟失修復（2026-04-01 · commit d065453）

根因：GovernanceHub 授權為純記憶體狀態，重啟後歸零
修復：get_status() auth_pending_approval + /session/reauth 端點 + startup 自動補授

### April 1 全系統審計 + 6 Batch 修復（2026-04-01）

審計：AI-E(B+) / E5(54項) / E4(3310/96files/~68%) / E3(0C/1H/5M/4L) / CC(A-,14/16) / FA(52%) / TW(82.5%) / R4(12項)
Batch 1-6 全部完成：知識閉環 / BacktestEngine 285x / L2 快取 / HttpOnly cookie / 鎖縮窄

### Batch 7 積壓清掃（2026-04-01）

pipeline_bridge 拆分 / Conductor 編排 / 194 logger %s / Pydantic 驗證 / MODULE_NOTE 補全

### main_legacy.py 重構 Wave A-D（2026-04-01）

```
Wave A：state_models + state_compiler + state_store = -1210 行（5265→4056）
Wave B：auth + state_helpers = -297 行（4099→3802）
Wave C：control_ops + pnl_ops + learning_ops = -2363 行（3802→1439）
Wave D：legacy_routes = -1016 行（1439→423）
總計：-92%，拆出 8 模塊，3005 tests 零回歸
```

### Wave 8 PA 實況檢查 + 並行修復（2026-04-01）

PA 交叉驗證：69 項審計結果逐一比對代碼（29 確認/10 部分/20 已修/10 誤報）
6 軌道並行 × 2 批次 = 38/39 項完成
- Wave 8A 安全+正確性（8 項）
- Wave 8B 代碼質量（12 項）
- Wave 8C 架構改進（7 項）：strategist 1152→780 行拆 4 模組
- Wave 8D 文檔清理（5 項）
- B3+B4 核心拆分：on_tick 4 子方法 + mutator 5 子函數
commits: 533a71a + 4782c96 + 6b494a6 · +148 新測試

### FA 完成度與 GAP 審核（2026-04-01）

代碼完成度 ~80%，業務功能真正能用 ~52%
7 項關鍵 GAP：
- P0-GAP-1：學習反饋閉環斷開
- P0-GAP-2：進化參數不自動重部署
- P1-GAP-3：H0 Gate warn-only
- P1-GAP-4：交易所條件單未實作
- P1-GAP-5：MarketScanner → Deployer 未接通
- P1-GAP-6：Backtest 生產環境未啟用
- P2-GAP-7：L2 觸發門檻過高
詳細報告：docs/governance_dev/audits/2026-04-01--fa_completion_gap_audit.md

### P0 ~ Wave 3c 修復記錄（2026-03-31）

- P0 修復（5 E1 並行）：governance_routes isinstance / pipeline_bridge Guardian=None / paper_engine Hub=None / openclaw_proxy 認證 / layer2_engine negation
- Wave 0 P1：ollama max_retries=0 / subprocess 分隔符 / 日誌路徑 / 憑證緩存 / 日誌注入修復
- Wave 1：DI 統一（26 Depends）+ HTTPException 穿透
- Wave 2：compile_state cache / auth 速率限制 / XSS / governance env var / 測試覆蓋補強
- Wave 3a：/reconcile 角色驗證 / detail=str(e)→固定字串
- Wave 3b：proxy header 過濾 / WeakKeyDict / asyncio.Lock / token 統一 / _OC_HOST 緩存
- Wave 3c：lease expires_at_ms / PerceptionPlane 測試 / is_authorized 鎖修復

### H0 Gate（P1-16）三天實現（2026-03-31）

- Day 1：h0_gate.py 651 行，5 個確定性 check，SLA <5μs
- Day 2：H0HealthWorker 背景線程，40 測試，SLA <0.5ms avg
- Day 3：Pipeline/Routes/Risk 集成，18 集成測試

### GUI + Ollama 優化（2026-03-31）

- Paper+Demo 合併為「測試交易」子 Tab + 「實盤交易」鎖定占位 Tab
- think=False 修復：9B 8.7s→1.9s，27B 21s→9.9s
- 模型分配：9B 快速路徑 / 27B 複雜任務 / ScoutWorker daemon
- 後台市場流常駐 / 週報雙層（Ollama + Claude L2）

---

## §十一 已完成的路線圖（歷史歸檔）

```
已完成摘要：
  ✅ A-L 全部章節 + 策略工具包 + 管線橋接 + 全系統審核
  ✅ GUI 三層架構 + 11-Tab 專業控制台
  ✅ 自主交易 Agent（市場掃描器 650 符號 + 策略自動部署）
  ✅ Phase 2 治理模組 T2.01–T2.23（21 模組 · 1,522 測試）
  ✅ Phase 3 GovernanceHub 集成（4SM 接入 + 安全審核）
  ✅ Round 2 Batch 3-12 全部完成（5 Agent + OMS + PaperLiveGate + E2E）
  ✅ L1 本地推理（Ollama + Qwen 3.5）+ 0% 勝率四根因全修復
  ✅ 7-Agent 全系統審計（71 項問題 · 4 CRITICAL · 全部修復）
  ✅ Wave 0-8 全部完成
  ✅ Phase 1-3 開發路線圖全部完成
  ✅ main_legacy.py 重構完成（-92%）

開發路線圖 v2（已完成）：
  Phase 1: H0 Gate ✅ + Cooldown 聯動 ✅
  Phase 2: TruthSourceRegistry ✅ + BacktestEngine ✅
  Phase 3: ExperimentLedger ✅ + EvolutionEngine ✅ + EvolutionScheduler ✅
```
