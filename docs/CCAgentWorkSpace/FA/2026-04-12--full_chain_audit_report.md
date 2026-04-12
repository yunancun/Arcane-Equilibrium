# FA 全鏈路審計報告 — Full Program Chain Audit
**日期**: 2026-04-12
**審計範圍**: Rust openclaw_engine (121 .rs / 54,952 行) + Python program_code (141,249 行 excl .venv)
**基線**: CLAUDE.md §三 所有宣稱功能 vs 實際代碼

---

## 一、功能規格驗證 — Feature Specification Verification

### 1.1 3E-ARCH 三引擎並行架構

**宣稱**: Paper/Demo/Live 三管線獨立並行，`build_exchange_pipeline()` 按 API key 獨立構建。

**驗證結果**: **PASS**
- `main.rs:202-213` — `build_exchange_pipeline()` 分別為 Live/Demo 構建，Paper 始終啟動
- `main.rs:232-244` — 每管線獨立 `UnboundedChannel` 命令通道
- `startup.rs:149-191` — `PerEngineRiskStores` 三獨立 ConfigStore
- `pipeline_types.rs` — `PipelineKind` enum (Paper/Demo/Live)
- `TradingMode` 已徹底刪除，確認無殘留

### 1.2 StrategyAction Enum

**宣稱**: 策略 `on_tick()` 返回 `Vec<StrategyAction>`，Close 走輕量路徑。

**驗證結果**: **PASS**
- `strategies/mod.rs:61` — `fn on_tick(&mut self, ctx: &TickContext) -> Vec<StrategyAction>`
- 5 策略全部實作 `on_tick()` 返回 `Vec<StrategyAction>`:
  - `ma_crossover.rs:299`
  - `bb_reversion.rs:214`
  - `bb_breakout.rs:242`
  - `grid_trading.rs:630`
  - `funding_arb.rs:124` (stub — 返回 `vec![]`)

### 1.3 Scanner Phase A-D

**宣稱**: ScannerRunner 完整接線，動態 symbol 管理。

**驗證結果**: **PASS**
- `scanner/runner.rs` — `ScannerRunner` 完整實作：REST fetch → score → registry → WS topic change
- `scanner/scorer.rs` — 評分邏輯 + correlation filter
- `scanner/registry.rs` — SymbolRegistry + anti-churn
- `scanner/config.rs` — ScannerConfig TOML
- `main.rs:127-188` — Scanner 完整接線到 startup

### 1.4 Phase 6 Reconciler 自動降級

**宣稱**: Reconciler 從 AUDIT-ONLY 升級為自動動作層，漂移→escalation→恢復。

**驗證結果**: **PASS**
- `position_reconciler/mod.rs` — 完整 MODULE_NOTE 描述 Phase 6 自動降級
- `position_reconciler/escalation.rs` — `ReconcilerState` + `evaluate_actions()` + 升降級
- 5 級分類 (Match/MinorDrift/MajorDrift/Orphan/Ghost) 確認存在

### 1.5 News Pipeline (A2)

**宣稱**: 60s 定時排程器，3 providers → 去重 → severity → fan-out。

**驗證結果**: **PASS**
- `news/mod.rs` — 完整模組：cryptopanic/rss/dedup/severity/router/pipeline
- `tasks.rs:282` — `news_pipeline_enabled` switch 實際 gate 控制
- `news/router.rs` — Guardian/Regime/Learning 三路 fan-out

### 1.6 Claude Teacher Pipeline

**宣稱**: Phase 4 sub-task 4-01，directive fetch/parse/persist。

**驗證結果**: **PASS（結構完整，但需 API key 才能真正運行）**
- `claude_teacher/mod.rs` — 完整子模組：client/parser/writer/applier/consumer_loop/outcome_tracker
- `claude_teacher/consumer_loop.rs` — `TeacherConsumerLoop` 完整實作
- `tasks.rs:217` — IPC handle injection，default-off
- `claude_teacher/applier.rs:477` — `boost_arm` 仍為 stub（4-06 留尾）

### 1.7 LinUCB Contextual Bandit

**宣稱**: 純 Rust 推理層。

**驗證結果**: **PASS**
- `linucb/mod.rs` — 完整子模組：inference/runtime/state_io/schema_hash/arms_v1_15
- `linucb/inference.rs` — ridge-regression LinUCB 推理實作
- `decision_context_producer.rs` — 運行時使用 `LinUcbRuntime::select_for_intent()`

### 1.8 ConfigStore + Hot-Reload

**宣稱**: ArcSwap 熱加載，4 IPC 寫入面。

**驗證結果**: **PASS**
- `config/store.rs` — `ConfigStore<T>` with `ArcSwap`
- `ipc_server/mod.rs` — `set_config_stores()` 注入
- `ipc_server/handlers.rs` — `patch_risk_config` / `patch_learning_config` IPC handlers

### 1.9 Live GUI Phase 1-6

**宣稱**: 完整 Live 操作面板。

**驗證結果**: **PASS（Python 側確認）**
- `live_session_routes.py` (1203 行) — 完整 live session lifecycle
- `live_trust_routes.py` — earned trust engine endpoints
- `settings_routes.py` — API key 管理
- `strategy_wiring.py` — DI wiring for all agents

### 1.10 Multi-Symbol Position Tracking

**宣稱**: 4 策略從單一 `Option<bool>` 改為 `HashMap<String, bool>`。

**驗證結果**: **PASS**
- `strategies/ma_crossover.rs` — `positions: HashMap<String, bool>`
- `strategies/bb_reversion.rs` — 同上
- `strategies/bb_breakout.rs` — 同上
- `strategies/grid_trading.rs` — `active_grids: HashMap<String, ...>`

---

## 二、Gap 分析 — Implementation Gap Analysis

### 2.1 [BLOCKER] AI 治理層 H1-H5 — Rust 引擎完全未接入

**嚴重程度**: BLOCKER（與憲法原則 #3 "AI 輸出 ≠ 即時命令" 矛盾）

**現狀**:
- CLAUDE.md §十 明確標註「H1-H5 AI agent 目前全 stub」
- `ai_service.py:124-128` — 所有 5 個 handler 返回 stub response：
  - `_handle_strategist`: 返回 `action: "hold", confidence: 0.0`
  - `_handle_analyst`: 返回空 analysis
  - `_handle_conductor`: 返回 `maintain_current`
  - `_handle_scout`: 返回空 intel
  - `_handle_guardian`: 返回 `approved` (stub 通過一切！)
- **Rust 引擎根本不調用 `ai_service.sock`** — grep `ai_service|strategist_evaluate|guardian_check` 在 Rust 源碼中零結果
- Python 側 Agent 類存在且接線完整（`strategy_wiring.py` 實例化 Scout/Strategist/Guardian/Analyst/Executor + Conductor），但**僅運行在 Python 管線內**，與 Rust 引擎完全隔離

**影響**:
- Rust 引擎的交易決策完全由確定性策略驅動，無 AI 治理層介入
- 原則 #3 (Decision Lease) 在 Rust 引擎路徑中未執行
- 原則 #13 (AI 資源成本感知) 對 Rust 路徑無效

**文件位置**:
- `ai_service.py:231-260` (stub handlers)
- `strategy_wiring.py:110-269` (Python agent wiring)
- CLAUDE.md §十 路線圖確認 W22-W23 才計劃接入

### 2.2 [BLOCKER] Fast Track ReduceToHalf / PauseNewEntries 未實作

**嚴重程度**: BLOCKER（風控閉環缺口）

**現狀**:
- `fast_track.rs:17-18` — `ReduceToHalf` 和 `PauseNewEntries` 兩個 enum variant 已定義
- `fast_track.rs:46,51` — `evaluate_fast_track()` 會返回這兩個值
- **但 `tick_pipeline/on_tick.rs` 僅處理 `CloseAll`**:
  ```
  on_tick.rs:161: if ft_action == FastTrackAction::CloseAll { ... }
  ```
  `ReduceToHalf` 和 `PauseNewEntries` 被完全忽略（沒有 else if 分支）
- 即使 `CloseAll` 路徑，`price_drop_pct` 和 `margin_utilization_pct` 永遠傳入 `0.0` (`on_tick.rs:158-159`)，
  閃崩和保證金危機分支永遠不會觸發

**影響**:
- Defensive 模式下不會自動減倉
- Reduced 模式下不會暫停新開倉
- 唯一可觸發的風控動作是 `risk_level >= CircuitBreaker` → CloseAll

**文件位置**:
- `fast_track.rs:17-18,46,51`
- `tick_pipeline/on_tick.rs:148-161`

### 2.3 [MAJOR] Decision Lease 系統 — Python 實作完整但 Rust 未使用

**嚴重程度**: MAJOR

**現狀**:
- `decision_lease_state_machine.py` — 9 狀態、20+ 遷移的完整狀態機（553 行）
- `governance_hub.py` — `acquire_lease()` / `release_lease()` 已實作
- `executor_agent.py` — `ExecutorAgent.execute_order()` 調用 `acquire_lease()`
- **但 Rust IntentProcessor 直接處理 Open/Close 而不經過 Decision Lease**
- Rust 引擎的 `intent_processor/router.rs` 有 Guardian/cost_gate/Kelly 門控，但無 lease 概念

**影響**: Rust 引擎路徑缺少 "帶時效、可撤銷" 的決策租約機制

**文件位置**:
- `decision_lease_state_machine.py:1-553`
- `intent_processor/router.rs:209` (cost gate 存在但無 lease)

### 2.4 [MAJOR] FundingArb 策略 — 完整 stub

**嚴重程度**: MAJOR

**現狀**:
- `strategies/funding_arb.rs:6-9` — MODULE_NOTE 明確標註 "Currently stub (on_tick returns vec![])"
- `funding_arb.rs:124-138` — `on_tick()` 返回 `vec![]`（空動作）
- 所有內部邏輯（`compute_edge`, `should_exit` 等）標註 `#[allow(dead_code)]`
- 等待 OC-5 REST wiring + R-06 Python IPC 提供資金費率

**影響**: 5 策略中僅 4 個活躍，FundingArb 佔位但無功能

**文件位置**: `strategies/funding_arb.rs:124-138`

### 2.5 [MAJOR] Phase 5 Cost Gate / James-Stein — 暫停（策略 edge 為負）

**嚴重程度**: MAJOR

**現狀**:
- `edge_estimates.rs` — PH5-WIRE-1 JS shrunk edge cache 代碼完整
- `intent_processor/gates.rs:7-139` — cost gate helper 代碼完整
- `intent_processor/router.rs:209` — Gate 3 cost gate 已接線
- **但**: PNL-FIX-1/2 揭露所有策略 gross edge 為負
  - bb_reversion -0.46 bps / ma_crossover -2.64 bps / grid_trading -0.67 bps
- 代碼保留但等正向 edge 策略接入才有意義

**影響**: Cost gate 機械正確但餵的是污染/負 edge 輸入

**文件位置**:
- `edge_estimates.rs:1-171`
- `intent_processor/gates.rs:7-139`
- CLAUDE.md Phase 5 PAUSED 段落

### 2.6 [MAJOR] Learning Pipeline — 部分實作

**嚴重程度**: MAJOR

**現狀**:
- LinUCB 推理層：完整 (**PASS**)
- Claude Teacher pipeline：結構完整，default-off (**PASS**)
- Decision Context Snapshots：完整寫入通道 (**PASS**)
- **缺失**:
  - LinUCB online update（4-06 warm-start 明確標註 NOT included）
  - `boost_arm` 在 `applier.rs:477` 仍為 stub
  - `linucb_enabled` config switch 從未在運行時代碼中讀取（僅定義+測試）
  - `thompson_enabled` config switch 未使用
  - `scorer_enabled` config switch 未使用
  - `directive_apply_enabled` config switch 未使用

**影響**: Learning 管線建設中，核心骨架在但離 "自動學習" 仍有距離

### 2.7 [MINOR] Claude Teacher `boost_arm` — Stub

**現狀**: `claude_teacher/applier.rs:477-521` — `boost_arm` 明確標註 stub，留給 4-06

**文件位置**: `claude_teacher/applier.rs:477`

---

## 三、死代碼檢驗 — Dead Code Analysis

### 3.1 [MAJOR] Rust 孤立模組 — 3 個模組從未被引用（1,612 行）

| 模組 | 行數 | 說明 |
|------|------|------|
| `leverage_token_client.rs` | 503 | Bybit 槓桿代幣 API 封裝，`lib.rs` 聲明但無任何其他文件引用 |
| `spot_margin_client.rs` | 534 | Bybit 現貨保證金 API 封裝，`lib.rs` 聲明但無引用 |
| `batch_order_manager.rs` | 575 | 批量訂單管理器，`lib.rs` 聲明但無引用 |

**影響**: 1,612 行完全未使用的代碼，增加編譯時間和維護負擔

**文件位置**:
- `leverage_token_client.rs` (全文)
- `spot_margin_client.rs` (全文)
- `batch_order_manager.rs` (全文)

### 3.2 [MAJOR] `Orchestrator::dispatch_tick()` — 生產環境死碼

**現狀**:
- `orchestrator.rs:38` — `dispatch_tick()` 標註 `#[allow(dead_code)]`
- 註釋明確說明 "Not called in production since RC-04 (per-strategy loop in tick_pipeline)"
- 生產環境使用 `tick_pipeline` 直接逐策略循環

**文件位置**: `orchestrator.rs:32-47`

### 3.3 [MAJOR] MlSwitches 死 config — 4 個開關從未在運行時讀取

| Config 欄位 | 文件:行 | 運行時使用 |
|-------------|---------|-----------|
| `linucb_enabled` | `learning_config.rs:86` | 僅在測試中 assert，運行時無人讀取 |
| `thompson_enabled` | `learning_config.rs:89` | 零使用 |
| `scorer_enabled` | `learning_config.rs:106` | 零使用 |
| `directive_apply_enabled` | `learning_config.rs:101` | 零使用 |

**對比**: `news_pipeline_enabled` 和 `teacher_loop_enabled` 確實在運行時被讀取使用

**影響**: Operator 可通過 IPC 修改這些開關值，但引擎不會有任何行為變化（假功能）

**違反規則**: MEMORY.md `feedback_no_dead_params.md` — "Agent 可調參數必須真實被發現/調整/持久化"

### 3.4 [MAJOR] `fast_track::ReduceToHalf` / `PauseNewEntries` — 定義但未處理

**現狀**: enum variant 已定義，`evaluate_fast_track()` 會返回，但 `on_tick.rs` 僅處理 `CloseAll`

**文件位置**: `fast_track.rs:17-18` + `tick_pipeline/on_tick.rs:148-161`

### 3.5 [MINOR] FundingArb 內部邏輯 — 9 處 `#[allow(dead_code)]`

**現狀**: `strategies/funding_arb.rs` 有 9 個 `#[allow(dead_code)]` 標註
- 所有常量 (TOTAL_COST_BPS / DEFAULT_EXPECTED_PERIODS / FUNDING_THRESHOLD / MAX_BASIS_PCT / MAX_HOLD_MS)
- struct 欄位
- `compute_edge()` / `should_exit()` 函數

**文件位置**: `strategies/funding_arb.rs:15-66`

### 3.6 [MINOR] Python `PIPELINE_BRIDGE = None` / `STOP_MANAGER = None`

**現狀**:
- `strategy_wiring.py:285-286` — 兩者設為 None
- `strategy_read_routes.py:369` — `PIPELINE_BRIDGE` 仍被判 None 後返回空
- DEAD-PY-2 清理後的殘留引用

**文件位置**: `strategy_wiring.py:285-286`, `strategy_read_routes.py:369-372`

### 3.7 [MINOR] Python `delegation_framework.py` — 562 行未被引用

**現狀**: 完整的四階段放權框架實作（562 行），但無任何文件 import 它

**文件位置**: `delegation_framework.py` (全文)

### 3.8 [MINOR] Python `backtest_engine.py` — 1,352 行未被運行時引用

**現狀**: 回測引擎，僅在測試中可能使用，非運行時代碼

**文件位置**: `local_model_tools/backtest_engine.py` (全文)

---

## 四、文件大小違規 — File Size Violations

### 4.1 [MAJOR] 超過 1200 行硬上限的源文件

**Rust 源文件**:

| 文件 | 行數 | 超標量 | 說明 |
|------|------|--------|------|
| `config/risk_config.rs` | 1,381 | +181 | Config 定義 + 驗證 + 測試 |
| `event_consumer/mod.rs` | 1,302 | +102 | 事件消費者主體 |
| `claude_teacher/applier.rs` | 1,257 | +57 | Directive 應用器 + 測試 |
| `tick_pipeline/on_tick.rs` | 1,228 | +28 | 核心 tick 處理 |

**Python 源文件**:

| 文件 | 行數 | 超標量 | 說明 |
|------|------|--------|------|
| `governance_routes.py` | 1,914 | +714 | **嚴重超標** — CLAUDE.md 已標記為 pre-existing 留尾 |
| `governance_hub.py` | 1,812 | +612 | GovernanceHub 核心 |
| `signal_generator.py` | 1,452 | +252 | 信號生成器 |
| `backtest_engine.py` | 1,352 | +152 | 回測引擎 |
| `live_session_routes.py` | 1,203 | +3 | Live session 路由 |

### 4.2 [MINOR] 超過 800 行警告線的 Rust 文件

| 文件 | 行數 |
|------|------|
| `ipc_server/handlers.rs` | 1,192 |
| `tick_pipeline/mod.rs` | 1,192 |
| `tick_pipeline/tests.rs` | 1,190 |
| `strategies/grid_trading.rs` | 1,158 |
| `order_manager.rs` | 1,151 |
| `ipc_server/tests.rs` | 1,059 |
| `bybit_rest_client.rs` | 1,054 |
| `database/drift_detector.rs` | 1,010 |
| `ipc_server/mod.rs` | 994 |
| `bybit_private_ws.rs` | 992 |
| `main.rs` | 950 |
| `ws_client.rs` | 923 |
| `event_consumer/tests.rs` | 887 |
| `startup.rs` | 856 |
| `position_manager.rs` | 839 |

---

## 五、其他發現

### 5.1 [INFO] Python Agent 層 vs Rust 引擎 — 雙軌運行確認

Python 側 5-Agent 框架（`multi_agent_framework.py` 1,104 行）已完整實作：
- `ScoutAgent` — 市場情報收集
- `StrategistAgent` — 策略評估（含 H1 ThoughtGate / H3 ModelRouter / H4 Validator）
- `GuardianAgent` — 風控審查
- `AnalystAgent` — 交易分析
- `ExecutorAgent` — 執行代理
- `Conductor` — 編排器
- `MessageBus` — 結構化通信

所有 Agent 在 `strategy_wiring.py:110-269` 中實例化並接線至 MessageBus。
但這套系統**僅運行在 Python GUI/API 管線中**，Rust 引擎的核心交易路徑完全不經過這些 Agent。

### 5.2 [INFO] Earned Trust Engine / Promotion Pipeline — 獨立但就緒

- `earned_trust_engine.py` (EarnedTrustEngine) — 贏得信任引擎，完整
- `promotion_pipeline.py` (PromotionPipeline) — 5 階段漸進放權，完整
- `evolution_engine.py` — 演化引擎，完整
- 三者獨立運行，等待 Agent 層接入

### 5.3 [INFO] `price_drop_pct` / `margin_utilization_pct` 硬編 0 — 已知已標記

`on_tick.rs:149-159` 已有 PNL-4 標記和詳細 tracing::warn，已進入 TODO 追蹤

---

## 六、總結表 — Summary Table

| # | 嚴重性 | 類別 | 發現 | 影響範圍 | 文件位置 |
|---|--------|------|------|----------|----------|
| 1 | BLOCKER | Gap | H1-H5 AI 治理層全 stub，Rust 引擎未接入 | 原則 #3/#13 未執行 | `ai_service.py:231-260` |
| 2 | BLOCKER | Gap | FastTrack ReduceToHalf/PauseNewEntries 未處理 | 風控閉環缺口 | `on_tick.rs:148-161` |
| 3 | MAJOR | Gap | Decision Lease Python 完整但 Rust 未使用 | 原則 #3 部分失效 | `decision_lease_state_machine.py` |
| 4 | MAJOR | Gap | FundingArb 策略完整 stub | 5 策略僅 4 活躍 | `funding_arb.rs:124-138` |
| 5 | MAJOR | Gap | Phase 5 Cost Gate 暫停（策略 edge 負） | 成本感知無效 | `edge_estimates.rs` |
| 6 | MAJOR | Gap | Learning Pipeline 部分實作（4 死 switch） | 學習能力受限 | `learning_config.rs:86-106` |
| 7 | MAJOR | Dead | 3 Rust 孤立模組（1,612 行） | 編譯/維護負擔 | `leverage_token_client.rs` 等 |
| 8 | MAJOR | Dead | 4 MlSwitches config 欄位未運行時讀取 | 假功能違反規則 | `learning_config.rs:86-106` |
| 9 | MAJOR | Size | governance_routes.py 1,914 行 | 超 1200 硬上限 +714 | `governance_routes.py` |
| 10 | MAJOR | Size | governance_hub.py 1,812 行 | 超 1200 硬上限 +612 | `governance_hub.py` |
| 11 | MAJOR | Size | 4 Rust 文件超 1200 行 | §九硬上限違規 | 見 §四.1 表 |
| 12 | MINOR | Gap | boost_arm stub（4-06 留尾） | Teacher 功能不完整 | `applier.rs:477` |
| 13 | MINOR | Dead | Orchestrator::dispatch_tick() 生產死碼 | 維護混淆 | `orchestrator.rs:38` |
| 14 | MINOR | Dead | PIPELINE_BRIDGE/STOP_MANAGER None 殘留 | 清理不完整 | `strategy_wiring.py:285-286` |
| 15 | MINOR | Dead | delegation_framework.py 未被引用 | 562 行孤立代碼 | `delegation_framework.py` |
| 16 | MINOR | Dead | backtest_engine.py 非運行時代碼 | 1,352 行非必要 | `backtest_engine.py` |
| 17 | INFO | Arch | Python Agent 層與 Rust 引擎完全隔離 | 雙軌架構確認 | `strategy_wiring.py` |
| 18 | INFO | Note | price_drop/margin_util 硬編 0 已標記 | PNL-4 追蹤中 | `on_tick.rs:149-159` |

---

## 七、建議優先級

1. **W22 G-1 AI Agent 接入**（BLOCKER #1）：Rust IPC → Python AIService 接入是最高優先級
2. **FastTrack 補完**（BLOCKER #2）：`on_tick.rs` 添加 ReduceToHalf/PauseNewEntries 處理分支
3. **死 config switch 清理**（MAJOR #8）：要麼接線要麼刪除，消滅假功能
4. **孤立模組清理**（MAJOR #7）：從 `lib.rs` 移除 3 個 `pub mod` 聲明
5. **governance_routes.py 拆分**（MAJOR #9）：已知留尾，需排入近期計劃
6. **price_drop_pct/margin_utilization 接線**（INFO #18）：計算閃崩和保證金使用率

---

*報告由 FA (Functional Architect) 角色生成，審計時間 2026-04-12*
