# 3E-ARCH Session 執行計劃
# Three-Engine Parallel Architecture — Session Execution Plan

**日期 / Date**: 2026-04-11  
**排期 / Schedule**: W22（2026-05-05~12），共 8 個工作日  
**前置 / Prerequisite**: 本文件基於 `three_engine_parallel_arch_plan.md` v4（26 個設計決策）  
**狀態 / Status**: ✅ 已完成（2026-04-11 commit 0f3af65）— `TradingMode` 已完全由 `PipelineKind` 取代，文中 `TradingMode` 引用為歷史上下文  

---

## 核心約束

1. **Context compaction**：Claude Code 上下文有限，大任務必須拆成自足 session
2. **Session 自足性**：每個 session 結束時 commit + 更新 TODO.md，下個 session 從 TODO.md 恢復
3. **強制工作鏈**：E1 → E2 審查 → E4 回歸（不可跳過）
4. **每 session ≤5 文件修改**：避免上下文壓力
5. **關鍵路徑**：3E-1 → 3E-9 → 3E-2a → 3E-2b → 3E-4 → 3E-5

## 關鍵文件大小參考

| 文件 | 行數 | 備註 |
|------|------|------|
| `main.rs` | 1769 | 3E-2b 主戰場 |
| `tick_pipeline.rs` | 3723 | 3E-1 修改，超大需分段讀 |
| `intent_processor.rs` | 1473 | 3E-2a 核心 |
| `event_consumer/mod.rs` | 1151 | 3E-2a 策略注入 |
| `ipc_server.rs` | 3176 | 3E-3 路由改造 |
| `position_reconciler.rs` | 1384 | 3E-2b D23 |
| `bybit_private_ws.rs` | 838 | 3E-2b D21 |
| `config/mod.rs` | 527 | 3E-4 TradingMode 清除 |
| `strategies/mod.rs` | 277 | 3E-9 StrategyFactory |
| `governance_core.rs` (core) | 512 | D26 驗證（無 singleton ✅） |

---

## Session 分解

### S0：前置審計 + 3E-6 Sidebar（Day 0 / 可立即做）

**目標**：D12 RwLock 審計 + D26 GovernanceCore 驗證 + 3E-6 GUI 修正（無 Rust 後端依賴）

**入口協議**：
```
讀 TODO.md → 找 3E-6 checkbox → 讀 docs/references/2026-04-11--three_engine_parallel_arch_plan.md §D12/D22/D26
```

**修改文件**（3 個）：
1. `program_code/.../static/js/console.html` — sidebar `refreshSidebar()` 改用 `system_mode` + `active_engines`
2. `docs/references/2026-04-11--three_engine_parallel_arch_plan.md` — 記錄 D12/D26 審計結果
3. `TODO.md` — tick 3E-6

**上下文加載**：
- `console.html` 的 `refreshSidebar()` 函數（~50 行）
- `tab-live.html` 中任何 `trading_mode` 引用

**驗證**：
```bash
grep -rn "trading_mode" program_code/static/ --include="*.html" --include="*.js"  # 確認零殘留
grep -rn "std::sync::RwLock" rust/openclaw_engine/src/ rust/openclaw_core/src/  # D12 記錄
grep -n "static\|OnceCell\|lazy_static" rust/openclaw_core/src/governance_core.rs  # D26 確認
```

**出口協議**：commit `feat(gui): 3E-6 sidebar system_mode + active_engines display`  
**可與其他 session 並行**：是（純 JS，不影響 Rust）  
**估計時間**：30 min

---

### S1：PipelineKind + GovernanceProfile + PipelineCommand rename（Day 1 上午）

**目標**：3E-1 — 新增枚舉 + `#[deprecated]` 舊 API + D22 rename

**入口協議**：
```
讀 TODO.md → 找 3E-1 checkbox
讀 three_engine_parallel_arch_plan.md §3E-1 + §D22 + §D13
```

**修改文件**（4 個）：
1. `tick_pipeline.rs` — 新增 `PipelineKind` enum（~40 行），`#[deprecated]` 標記 `TradingMode` 相關 API，rename `PaperSessionCommand → PipelineCommand`
2. `strategies/mod.rs` 或新文件 — 新增 `GovernanceProfile` enum（~30 行）
3. `config/mod.rs` — `#[deprecated]` 標記 `TradingMode` enum（不刪）
4. 全 crate — `sed` rename `PaperSessionCommand → PipelineCommand` + `paper_cmd_tx → pipeline_cmd_tx`

**上下文加載**：
- `tick_pipeline.rs:90-280`（PaperSessionCommand 定義區）
- `tick_pipeline.rs:350-520`（TickPipeline struct + mode_states）
- `config/mod.rs:40-110`（TradingMode 定義）

**⚠ 注意**：rename 是全 crate 機械替換，用 `sed` 完成後 `cargo check` 驗證編譯。不改邏輯。

**驗證**：
```bash
cargo check --lib  # 編譯通過（deprecated warning 可以）
cargo test --lib   # 879 tests pass
grep -c "PaperSessionCommand" rust/openclaw_engine/src/**/*.rs  # = 0
```

**出口協議**：commit `refactor(engine): 3E-1 PipelineKind + GovernanceProfile + PipelineCommand rename`  
**估計時間**：1.5h

---

### S2：StrategyFactory + per-engine params（Day 1 下午）

**目標**：3E-9 — 策略唯一註冊點 + 參數加載器 + 3 個 TOML 模板

**入口協議**：
```
讀 TODO.md → 找 3E-9
讀 plan §3E-9 + §D8
```

**修改文件**（4 個 + 3 新建）：
1. `strategies/mod.rs`（或新文件 `strategies/factory.rs`）— `StrategyFactory::create_all()` + `load_strategy_params()`
2. `event_consumer/mod.rs:328-333` — 替換硬編碼策略註冊為 `StrategyFactory::create_all()`
3. 新建 `settings/strategy_params_paper.toml`
4. 新建 `settings/strategy_params_demo.toml`
5. 新建 `settings/strategy_params_live.toml`

**上下文加載**：
- `strategies/mod.rs`（全文 277 行）
- `event_consumer/mod.rs:320-340`（策略註冊區）
- 一個策略的 `update_params_json()` 實現（如 `ma_crossover.rs`）了解參數格式

**驗證**：
```bash
cargo test --lib   # 879 tests pass
# 新增測試：StrategyFactory::create_all() 返回 4 個策略
# 新增測試：load_strategy_params 各場景（有/無/畸形文件）
```

**出口協議**：commit `feat(engine): 3E-9 StrategyFactory + per-engine strategy params`  
**估計時間**：1.5h

---

### S3：IntentProcessor 治理分層（Day 2 全天）

**目標**：3E-2a 核心 — IntentProcessor 接受 `GovernanceProfile` 參數，分層 cost_gate

**⚠ 這是最高風險 session**：`intent_processor.rs` 1473 行，`process()` ~900 行。需要精確理解治理管線才能改。

**入口協議**：
```
讀 TODO.md → 找 3E-2a
讀 plan §3E-2a + §D3 + §D16 + §D24 + §D26
讀 intent_processor.rs:1-50（imports + struct）+ process() 函數簽名 + cost_gate 區段
```

**修改文件**（3 個）：
1. `intent_processor.rs` — `process()` 新增 `profile: GovernanceProfile` 參數，authorization/lease gate 條件化，新增 `cost_gate_moderate()`
2. `tick_pipeline.rs` — `process()` 調用點傳入 `self.governance_profile`
3. `governance_core.rs`（core crate）— `GovernanceCore::new_with_profile()` 工廠方法

**上下文加載**（分段，避免一次載滿）：
- Phase A：讀 `intent_processor.rs:1-100`（struct + process 簽名）+ `intent_processor.rs` 中 `authorization` / `lease` / `cost_gate` 關鍵字行號
- Phase B：精讀 cost_gate 區段（~100 行）
- Phase C：讀 `governance_core.rs`（512 行全文）

**子步驟**：
1. `GovernanceCore::new_with_profile()` — `governance_core.rs`（先改 core crate，確保編譯）
2. `process()` 新增 `profile` 參數 + authorization/lease 條件化 — `intent_processor.rs`
3. `cost_gate_moderate()` 新方法 — `intent_processor.rs`
4. 調用點更新 — `tick_pipeline.rs`（搜索 `process(` 調用，加 `self.governance_profile`）
5. 測試 — GovernanceProfile 3 profile × 3 gate 行為

**驗證**：
```bash
cargo test --lib   # 879+ tests pass
# 新增測試：Exploration → requires_authorization() = false
# 新增測試：Production → requires_authorization() = true
# 新增測試：cost_gate_moderate 3 分支
```

**出口協議**：commit `feat(engine): 3E-2a IntentProcessor governance profiling + cost_gate_moderate`  
**估計時間**：3-4h（留整天 buffer）

---

### S4：EventConsumerDeps 重構 + Pipeline 構造（Day 3 上午）

**目標**：3E-2a 下半 — `EventConsumerDeps` struct 重構，Pipeline 構造函數接受 `PipelineKind` + 資源注入

**入口協議**：
```
讀 TODO.md → 確認 S3 (IntentProcessor) 已完成
讀 plan §3E-2a EventConsumerDeps
讀 event_consumer/mod.rs:1-50 + types.rs struct 定義
```

**修改文件**（3 個）：
1. `event_consumer/mod.rs` — `run_event_consumer()` 接受 `EventConsumerDeps`，Pipeline 構造使用 `pipeline_kind`
2. `event_consumer/types.rs` — `EventConsumerDeps` struct 定義（含 `private_ws_rx`, `bybit_client` 等）
3. `tick_pipeline.rs` — `TickPipeline::with_kind()` 構造函數（新增，保留舊 `with_balance` deprecated）

**驗證**：
```bash
cargo check --lib  # 編譯通過
cargo test --lib   # 879+ tests pass
```

**出口協議**：commit `refactor(engine): 3E-2a EventConsumerDeps + Pipeline kind-based construction`  
**估計時間**：2h

---

### S5：三管線 spawn 骨架 + fan-out + DB pool（Day 3 下午 + Day 4 上午）

**目標**：3E-2b-α — main.rs 條件式啟動，bounded fan-out，先只啟 Paper 驗證骨架

**入口協議**：
```
讀 TODO.md → 確認 3E-2a 已完成
讀 plan §3E-2b + §D1 + §D10 + §D11 + §D25
讀 main.rs:550-700（當前 event channel + pipeline spawn 區段）
```

**修改文件**（2 個）：
1. `main.rs` — API key 讀取 + 衝突偵測 + bounded fan-out + 條件式 spawn Paper/Demo/Live
2. `Cargo.toml` — 如需 `parking_lot` 依賴

**子步驟**：
1. D25：PgPool max_connections 20
2. D12：`std::sync::RwLock` → `parking_lot::RwLock`（4 處）
3. API key 讀取 + D2 衝突偵測
4. Bounded fan-out（`mpsc::channel` 1→N + `Arc<WsEvent>` D20）
5. Paper Pipeline spawn（永遠啟動）
6. Demo Pipeline spawn（條件式）
7. 此 session **不做** Live 獨立 runtime — 先用 `tokio::spawn` 統一驗證

**驗證**：
```bash
cargo check --lib
cargo test --lib   # 所有舊 tests pass（新 pipeline 構造不破壞舊路徑）
```

**出口協議**：commit `feat(engine): 3E-2b-α pipeline spawn skeleton + bounded fan-out + parking_lot`  
**估計時間**：3h

---

### S6：Per-engine private WS + Live runtime（Day 4 下午）

**目標**：3E-2b-β — D21 per-engine private WS supervisor + D17 Live 獨立 runtime

**入口協議**：
```
讀 TODO.md → 確認 3E-2b-α 已完成
讀 plan §D21 + §D17
讀 bybit_private_ws.rs:220-260（struct + new + run）
讀 main.rs 的 private WS spawn 區段（S5 新寫的 Demo/Live spawn 區段）
```

**修改文件**（2 個）：
1. `main.rs` — Demo/Live pipeline 各自 spawn private WS supervisor + Live 獨立 runtime
2. `bybit_private_ws.rs` — 確認 `new()` 接受 `event_tx` 參數（已有），無需修改

**上下文加載**：
- `bybit_private_ws.rs:220-280`（constructor + run signature）
- `main.rs` 的 Demo/Live spawn 區段（S5 產出）

**驗證**：
```bash
cargo check --lib
cargo test --lib
```

**出口協議**：commit `feat(engine): 3E-2b-β per-engine private WS supervisors + Live independent runtime`  
**估計時間**：2h

---

### S7：Dual Reconciler + 錯誤隔離 + shutdown（Day 5 上午）

**目標**：3E-2b-γ — D23 dual reconciler + D6 三級遞減 + 有序 shutdown

**入口協議**：
```
讀 TODO.md → 確認 3E-2b-β 已完成
讀 plan §D23 + §D6 + shutdown
讀 position_reconciler.rs:1-50（run_position_reconciler 簽名 + 參數）
讀 main.rs 的 reconciler spawn 區段（當前 L1604-1611）
```

**修改文件**（2 個）：
1. `main.rs` — dual reconciler spawn + cross-engine notify channel + PipelineHealth atomic + 有序 shutdown
2. `position_reconciler.rs` — `run_position_reconciler()` 接受 engine label 參數（V014 audit 標記）

**驗證**：
```bash
cargo check --lib
cargo test --lib
```

**出口協議**：commit `feat(engine): 3E-2b-γ dual reconciler + cascading contraction + ordered shutdown`  
**估計時間**：2.5h

---

### S8：IPC 三管線路由（Day 5 下午，可與 S7 並行）

**目標**：3E-3 — `EngineCommandChannels` + per-engine 快照路由

**入口協議**：
```
讀 TODO.md → 找 3E-3
讀 plan §3E-3
讀 ipc_server.rs:80-120（PerEngineRiskStores）+ 快照路由相關函數
```

**修改文件**（1 個）：
1. `ipc_server.rs` — `EngineCommandChannels` struct + `select()` + per-engine 快照路由 + 移除 `add_engine_mode`/`switch_engine_mode`

**驗證**：
```bash
cargo check --lib
cargo test --lib
```

**出口協議**：commit `refactor(engine): 3E-3 IPC three-pipeline routing + EngineCommandChannels`  
**可與 S7 並行**：是（不同文件）  
**估計時間**：1.5h

---

### S9：TradingMode 完整清除（Day 6 上午）

**目標**：3E-4 — 移除 `TradingMode` enum + `EngineConfig::trading_mode` + `engine.toml` 條目 + 所有 `#[allow(deprecated)]`

**入口協議**：
```
讀 TODO.md → 確認 3E-2b + 3E-3 已完成
讀 plan §3E-4
grep -rn "TradingMode\|trading_mode" rust/ --include="*.rs" | wc -l  # 確認剩餘引用數
```

**修改文件**（~5 個）：
1. `config/mod.rs` — 刪除 `TradingMode` enum
2. `tick_pipeline.rs` — 刪除 `mode_states` / `active_modes` / `set_trading_mode()` / `add_mode()`
3. `event_consumer/mod.rs` — 清除 TradingMode 引用
4. `bybit_rest_client.rs` — 清除 `secret_slot()` 的 TradingMode 引用
5. `engine.toml` — 刪除 `trading_mode = ...` 行

**⚠ 風險**：這是刪除操作，如果 S5-S8 沒有完全替換所有 TradingMode 使用點，這裡會編譯失敗。`cargo check` 是門禁。

**驗證**：
```bash
cargo check --lib  # 零編譯錯誤
cargo test --lib   # 全 pass
grep -rn "TradingMode\|trading_mode" rust/openclaw_engine/src/ --include="*.rs"  # = 0（除了 deprecated 的 mode_state.rs）
```

**出口協議**：commit `refactor(engine): 3E-4 TradingMode complete removal`  
**估計時間**：2h

---

### S10：Python 清除 + 性能指標隔離（Day 6 下午）

**目標**：3E-5 — Python 側 `trading_mode` 清除 + per-engine metrics 端點

**入口協議**：
```
讀 TODO.md → 確認 3E-4 已完成
讀 plan §3E-5
grep -rn "trading_mode" program_code/ --include="*.py" | head -40  # 確認 ~35 處
```

**修改文件**（~4 個）：
1. `live_session_routes.py` — 移除 `_get_trading_mode_from_engine()`，`get_session_status()` 改返回 `active_engines`
2. `paper_trading_routes.py` — 移除 `trading_mode` 字段
3. `ipc_state_reader.py` — 改用 `pipeline_snapshot_{engine}.json`
4. `strategy_ai_routes.py` — 清除 `trading_mode` 引用

**驗證**：
```bash
grep -rn "trading_mode" program_code/ --include="*.py"  # = 0
cd program_code && python3 -m pytest -x -q  # 2792+ pass
```

**出口協議**：commit `refactor(python): 3E-5 trading_mode removal + per-engine metrics isolation`  
**估計時間**：2h

---

### S11：API Key 衝突偵測 + Watchdog + Paper GUI（Day 6，與 S10 並行部分）

**目標**：3E-7 + 3E-8 — Settings 層 409 衝突 + watchdog multi-snapshot + Paper balance GUI

**入口協議**：
```
讀 TODO.md → 找 3E-7, 3E-8
讀 plan §3E-7 + §3E-8
```

**修改文件**（3-4 個）：
1. `settings_routes.py` — API key update 端點 加衝突偵測
2. `helper_scripts/canary/engine_watchdog.py` — multi-snapshot 支持
3. `tab-paper.html` — Initial Balance 輸入框
4. `paper_trading_routes.py` — `POST /api/v1/paper/config` 端點

**驗證**：
```bash
python3 -m pytest program_code/ -x -q  # pass
# 新增測試：API key 衝突 409
```

**出口協議**：commit `feat: 3E-7 API key conflict detection + 3E-8 watchdog multi-snapshot`  
**估計時間**：1.5h

---

### S12：E2 代碼審查（Day 7）

**目標**：3E-E2 — 全量代碼審查，確保符合 26 個設計決策

**入口協議**：
```
讀 TODO.md → 確認 3E-1 ~ 3E-9 全部完成
讀 plan §四（所有 D1-D26）作為 checklist
git diff main~N...HEAD --stat  # 查看所有變更文件列表
```

**E2 Checklist**（從計劃文件衍生）：
- [ ] `PipelineKind` 不可變（無 setter）
- [ ] `GovernanceProfile` 正確映射 3 種 cost_gate 模式
- [ ] `PipelineCommand` rename 零 `PaperSessionCommand` 殘留
- [ ] `StrategyFactory::create_all()` 是唯一策略註冊點
- [ ] 每個 exchange pipeline 有獨立 private WS（D21）
- [ ] StopManager 使用構造時注入的 REST client（D24）
- [ ] GovernanceCore 三實例互不影響（D26）
- [ ] Reconciler 雙實例獨立 baseline/冷卻（D23）
- [ ] DB pool ≥ 20（D25）
- [ ] `parking_lot::RwLock` 替代所有共享 `std::sync::RwLock`（D12）
- [ ] Bounded channel + lag detection（D10）
- [ ] Live 獨立 runtime（D17）
- [ ] API key 衝突偵測 hard block（D2）
- [ ] Paper P0 硬限不可關閉（D16）
- [ ] `grep "trading_mode\|TradingMode" rust/ program_code/` = 0
- [ ] 雙語注釋（MODULE_NOTE / docstring）
- [ ] 路徑無硬編碼 `/home/ncyu/`

**出口協議**：E2 report → 修復 → 重新審查  
**估計時間**：2-3h

---

### S13：E4 測試回歸（Day 7 + Day 8）

**目標**：3E-E4 — 全量測試回歸 + 新增測試覆蓋 D21-D26

**入口協議**：
```
讀 TODO.md → 確認 E2 已通過
```

**驗證命令**：
```bash
# Rust
cargo test --lib                    # ≥879 pass, 0 fail
cargo test --test reconciler_e2e    # ≥18 pass

# Python
cd program_code && python3 -m pytest -x -q  # ≥2792 pass

# ML
cd ml_training && python3 -m pytest -x -q   # ≥135 pass

# 零殘留確認
grep -rn "trading_mode\|TradingMode" rust/openclaw_engine/src/ --include="*.rs"  # = 0
grep -rn "PaperSessionCommand\|paper_cmd_tx" rust/openclaw_engine/src/ --include="*.rs"  # = 0
grep -rn "std::sync::RwLock" rust/openclaw_engine/src/ --include="*.rs"  # 只在非共享用途
```

**新增測試清單**（~40 tests）：
- GovernanceProfile 3 × 3 矩陣（9）
- cost_gate_moderate 3 分支（3）
- StrategyFactory create_all（2）
- load_strategy_params 3 場景（3）
- Pipeline 條件式啟動 4 場景（4）
- Bounded channel 背壓（1）
- 三級遞減收縮（3）
- Private WS 路由隔離（3）
- Reconciler 雙實例獨立（3）
- API key 衝突 409（2）
- TradingMode 零殘留（1）
- PipelineCommand rename 零殘留（1）
- 全局 notional cap（2）
- 有序 shutdown（1）
- DB pool 容量（1）
- Paper P0 硬限（1）

**出口協議**：commit `test: 3E-E4 full regression + ~40 new tests for D1-D26`  
**估計時間**：3-4h

---

## Session 依賴圖

```
S0 (3E-6 GUI) ──────────────────────────────── 獨立，可隨時做
                                                 │
S1 (3E-1 PipelineKind + rename) ─────────┐      │
                                          │      │
S2 (3E-9 StrategyFactory) ───────────────┤      │
                                          │      │
S3 (3E-2a IntentProcessor) ──────────────┤      │
                                          │      │
S4 (3E-2a EventConsumerDeps) ────────────┤      │
                                          │      │
S5 (3E-2b-α spawn skeleton) ────────────┤      │
                                          │      │
S6 (3E-2b-β private WS) ───────────────┤      │
                                          │      │
S7 (3E-2b-γ reconciler + shutdown) ─────┤  S8 (3E-3 IPC) ← 可與 S7 並行
                                          │      │
S9 (3E-4 TradingMode 清除) ──────────────┤      │
                                          │      │
S10 (3E-5 Python) ───────────────────────┤  S11 (3E-7+8) ← 可與 S10 並行
                                          │      │
S12 (E2 審查) ───────────────────────────┘      │
                                                 │
S13 (E4 回歸) ──────────────────────────────────┘
```

## Day-by-Day 排程

| Day | Session | 主要工作 | 估計時間 | 累計 commit |
|-----|---------|---------|---------|------------|
| **Day 0**（可提前）| S0 | 3E-6 Sidebar + D12/D26 審計 | 0.5h | 1 |
| **Day 1 AM** | S1 | 3E-1 PipelineKind + PipelineCommand rename | 1.5h | 2 |
| **Day 1 PM** | S2 | 3E-9 StrategyFactory + per-engine params | 1.5h | 3 |
| **Day 2 全天** | S3 | 3E-2a IntentProcessor 治理分層 | 3-4h | 4 |
| **Day 3 AM** | S4 | 3E-2a EventConsumerDeps 重構 | 2h | 5 |
| **Day 3 PM** | S5 | 3E-2b-α spawn skeleton + fan-out | 3h | 6 |
| **Day 4 PM** | S6 | 3E-2b-β private WS per-engine | 2h | 7 |
| **Day 5 AM** | S7 | 3E-2b-γ reconciler + shutdown | 2.5h | 8 |
| **Day 5 PM** | S8 | 3E-3 IPC 路由（可與 S7 並行） | 1.5h | 9 |
| **Day 6 AM** | S9 | 3E-4 TradingMode 清除 | 2h | 10 |
| **Day 6 PM** | S10 + S11 | 3E-5 Python + 3E-7/8 衝突偵測 | 3.5h | 12 |
| **Day 7** | S12 | E2 代碼審查 | 3h | — |
| **Day 8** | S13 | E4 測試回歸 + 新增 ~40 tests | 4h | 13 |

## Session 間恢復協議（compact 後）

每個 session 結束時：
1. **commit** — 明確的 commit message 描述完成了什麼
2. **TODO.md** — tick 對應 checkbox + 更新測試基準線
3. **plan.md** — 如有計劃偏差，更新計劃文件

每個 session 開始時：
1. `git log --oneline -5` — 確認上一個 session 的 commit
2. `讀 TODO.md` — 找下一個 `[ ]`
3. `讀 plan.md 對應的 §` — 了解具體要做什麼
4. `cargo test --lib 2>&1 | tail -3` — 確認基線健康

**不需要跨 session 記憶的資訊**：
- 每個 session 的改動已在 commit 中
- 每個 session 的計劃在 plan.md 的對應 § 中
- 測試基準線在 TODO.md 頂部

**需要跨 session 記憶的資訊**（通過 TODO.md checkpoint 傳遞）：
- 哪些 task 已完成
- 當前測試基準線數字
- 任何計劃偏差（記在 TODO.md 或 plan.md 中）

---

*文件結束 / End of document*
