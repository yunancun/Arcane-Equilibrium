# Signal Diamond Multi-Engine Data Separation — Phase 1-4 + Fix Round 工程記錄
# 日期：2026-04-10
# 狀態：Phase 1-4 ✅ + Fix Round ✅ · Phase 5 (Per-Mode Strategy Params) 未來工作

---

## 一、背景與目標

系統需支持 Paper / Demo / Live 三模式同時運行。核心設計「Signal Diamond」：市場數據→指標→信號（共享，計算一次）→ Intent 層 fan-out（per-mode 風控/倉位/止損）。

**已完成的 DB_TODO.md 規劃文件已歸檔至：** `docs/references/2026-04-10--signal_diamond_db_todo.md`

---

## 二、Phase 1-4 實施摘要

### Phase 1: V015 Migration ✅
- 文件：`sql/migrations/V015__engine_mode_separation.sql`
- 8 個交易表加 `engine_mode TEXT NOT NULL DEFAULT 'paper'` + `(engine_mode, ts DESC)` 索引
- `trading.signals` 不改（共享客觀信號）
- `agent.ai_invocations` 加 nullable `engine_mode`
- 保留 `is_paper` 列（Grafana 向後兼容）

### Phase 2a: Rust DB Writers ✅
- `TradingMsg::Intent/Fill/PositionSnapshot` + `DecisionContextMsg` 加 `engine_mode: String`
- `trading_writer.rs` flush 函數寫入 `engine_mode` 列；`is_paper` 派生自 `engine_mode != "live"`
- `context_writer.rs` flush 加 `$26 = engine_mode`
- `TradingMode::db_mode()` 規範映射：PaperOnly→"paper", Demo→"demo", Live→"live"

### Phase 3: ModeState 結構體 ✅
- 新文件：`rust/openclaw_engine/src/mode_state.rs`
  - `ModeState` struct：PaperState + IntentProcessor + GovernanceCore + risk_store + ring buffers + consecutive_losses + session/pause flags + pending_close + exchange_seq
  - `ModeStateSnapshot` IPC 序列化結構體
  - 5 單元測試
- `TickPipeline` 新增 `mode_states: HashMap<TradingMode, ModeState>` + `active_modes: Vec<TradingMode>`
- `PipelineSnapshot.mode_snapshots: HashMap<String, ModeStateSnapshot>`
- `TradingMode` 加 `Hash` derive

### Phase 4: IPC + Python ✅
- Rust `ipc_server.rs`：`get_paper_state` 接受 `engine` 參數（默認 "paper"）；新增 `get_mode_snapshot` / `get_active_modes`
- Python `ipc_state_reader.py`：mode-aware lookup + `_MODE_ALIASES` fallback
- Python `ipc_client.py`：`get_paper_state(mode=)` + 新方法
- `live_session_routes.py`：所有 IPC 調用帶 `{"engine": "live"}`

---

## 三、Fix Round — 審計發現 9 gaps → 全部修復

### P0: set_trading_mode() 雙向 swap（Critical）
- **問題**：原 setter 只改 `self.trading_mode` 枚舉值，不保存/恢復狀態
- **修復**：`sync_direct_to_mode_state(old)` → `load_mode_state_to_direct(new)` 雙向 `std::mem::swap`
- **效果**：切換 paper↔demo↔live 時完整保留 PaperState/IntentProcessor/GovernanceCore/consecutive_losses/session_halted/pending_close

### P2: AddMode/SwitchMode IPC 命令（High）
- **問題**：`PaperSessionCommand` 缺少 AddMode/SwitchMode variants
- **修復**：新增 2 個 command variants + `handlers.rs` 匹配處理 + `ipc_server.rs` 嚴格 enum match + 3s timeout

### P3: Python IPC 層 mode-aware（High）
- **問題**：`EngineIPCClient.get_paper_state()` 不傳 mode 參數
- **修復**：`get_paper_state(mode="paper")` 傳遞 `{"engine": mode}`；新增 `get_mode_snapshot()` / `get_active_modes()`

### P1: 架構決策 — 同時多模式（Documented as Phase 5+）
- **結論**：策略有內部狀態（grid net_inventory, bb_breakout position flags），同一 tick 內為多 mode 分別調用 on_tick() 會污染狀態
- **當前方案**：支持模式**切換**（state preservation），不支持同時執行
- **未來方案**：per-mode Orchestrator 實例（`HashMap<TradingMode, Orchestrator>`）

---

## 四、測試基線

| Suite | Count | Status |
|-------|-------|--------|
| Rust lib tests | **850** (+5 新增 mode switch tests) | ✅ 0 failures |
| Rust integration | **3** | ✅ 0 failures |
| Python full suite | **2692** | ✅ 1 pre-existing fail (test_risk_view_client) |

### 新增測試清單（+5）
1. `test_set_trading_mode_preserves_state` — paper→demo→paper 狀態完整恢復
2. `test_set_trading_mode_same_mode_noop` — 同模式切換為 no-op
3. `test_add_mode_and_mode_snapshot` — add_mode + 快照隔離驗證
4. `test_mode_snapshot_in_pipeline_snapshot` — PipelineSnapshot 包含所有模式
5. `test_set_trading_mode_switch_back_preserves_consecutive_losses` — 連續虧損計數 roundtrip

---

## 五、E2 Code Review 結論

**OVERALL: PASS WITH WARNINGS**

- Swap 語義正確（雙向 std::mem::swap，主模式讀 direct fields）
- 所有 enum variants exhaustively matched
- 向後兼容完整（mode 默認 "paper"）
- 雙語註釋 ✅ / 跨平台 ✅ / 安全 ✅（strict enum match, timeouts）
- **Warning**：tick_pipeline.rs (3380行) + ipc_server.rs (3017行) 超 §九 1200行限制，為架構性 hub 合理但未來應拆分

---

## 六、變更文件清單

### 新增文件
| 文件 | 行數 | 說明 |
|------|------|------|
| `rust/openclaw_engine/src/mode_state.rs` | 219 | ModeState + ModeStateSnapshot + 5 tests |
| `sql/migrations/V015__engine_mode_separation.sql` | ~50 | 8 表加 engine_mode 列 |

### 修改文件（按重要性）
| 文件 | +/- 行 | 說明 |
|------|--------|------|
| `tick_pipeline.rs` | +270 | set_trading_mode swap + mode_snapshot + 5 tests |
| `ipc_server.rs` | +144 | add_engine_mode / switch_engine_mode + mode-aware get |
| `ipc_state_reader.py` | +61 | mode-aware methods + alias fallback |
| `trading_writer.rs` | +39/-0 | engine_mode 列寫入 |
| `context_writer.rs` | +26/-0 | engine_mode 列寫入 |
| `ipc_client.py` | +20/-0 | Phase 4 mode methods |
| `handlers.rs` | +18 | AddMode/SwitchMode handlers |
| `config/mod.rs` | +15 | Hash derive + db_mode() |
| `database/mod.rs` | +10 | engine_mode fields on TradingMsg |
| `decision_context_producer.rs` | +7 | engine_mode propagation |
| `pipeline_types.rs` | +4 | mode_snapshots field |
| `lib.rs` | +1 | pub mod mode_state |
| `phase4_integration.rs` | +1 | mode_snapshots: HashMap::new() |

---

## 七、共享 vs 分離決策表

| 層級 | 共享? | 理由 |
|------|-------|------|
| market.* / features.* / risk.* | 共享 | 客觀外部數據 |
| trading.signals | 共享 | 客觀策略觸發 |
| trading.intents/fills/orders | **分離** | 風控配置不同 → 結果不同 |
| trading.position_snapshots | **分離** | 獨立持倉追蹤 |
| trading.decision_context* | **分離** | 快照含倉位狀態 |
| KlineManager / SignalEngine | 共享 | 計算一次 |
| PaperState / IntentProcessor / GovernanceCore | **分離** | 獨立資金/風控/熔斷 |
| RiskConfig | **已分離** | PerEngineRiskStores ✅ |
| Orchestrator（策略） | 共享（Phase 5 分離） | 策略有內部狀態 |

---

## 八、遺留項

1. **Phase 5 — Per-Mode Strategy Params**：複用 `PerEngineRiskStores` 模式建 `PerEngineStrategyParams`
2. **Phase 5+ — 同時多模式執行**：per-mode Orchestrator 實例
3. **tick_pipeline.rs 拆分**：3380 行超限，建議抽取 `tick_pipeline_mode_management.rs`
4. **ipc_server.rs 拆分**：3017 行超限，建議抽取 `ipc_dispatch_router.rs`
5. **5 個無 writer 的表**：risk_verdicts / orders / order_state_changes / decision_outcomes / ai_invocations 待 writer 實現時帶入 engine_mode
