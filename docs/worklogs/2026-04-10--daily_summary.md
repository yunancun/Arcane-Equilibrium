# 2026-04-10 Daily Summary

## 完成項目 / Completed

### ML Pipeline Remediation（commit `7178059`，後續 audit gap fix）
基於 2026-04-09 DB R/W + ML 管線全面審計（`docs/audits/2026-04-09--db_rw_ml_pipeline_full_audit.md`）。

#### Session 0 — Foundation ✅
V001-V014 DDL 全部 existing · LightGBM 4.6.0 installed · `trading.fills` + `decision_context_snapshots` Rust writer 確認

#### Session 1 — Phase 5 P0 Edge Crisis Fix ✅
- `cost_gate_paper()` / `cost_gate_live()` 統一於 `intent_processor.rs:845/929`
- `SLIPPAGE_TIERS` 5-tier const `(1B,1bps)(100M,2bps)(10M,5bps)(1M,15bps)(<1M,30bps)`
- ATR% normalization · `win_rate` weighting `threshold = fee_bps / wr.clamp(0.3,1.0) * 1.3`
- `CellEstimate` 擴展 `shrunk_bps/win_rate/n_trades/std_bps`（`std_bps` stored but not consumed — future uncertainty-adjusted gating）
- `load_from_str()` 帶 `win_rate_shrunk` / `win_rate` fallback

#### Session 2 — ML Inference Pipeline Wiring ✅
- FeatureCollector 全鏈：`tick_pipeline.rs:1389` `tx.try_send(snap)` → `mpsc::channel(2048)` → `run_feature_writer` → HashMap dedup + `INSERT ON CONFLICT DO UPDATE`
- Parquet ETL 時間過濾 `WHERE updated_ts_ms >= {start_epoch_ms}`

#### Session 3 — Parameter Optimization Pipeline ✅
- Optuna 持久化：`_persist_suggestion()` INSERT 到 `learning.ml_parameter_suggestions`（DSN/env fallback、standalone 連接不走 pool 因為 batch ML job）
- Thompson Sampling 定位：**(A) offline training tool Python-only Phase 3b**，zero Rust refs（grep 驗證），Rust inference deferred to Phase 4 E5-D3
- CPCV 持久化：`_persist_cpcv_result()` INSERT `learning.cpcv_results` 11 columns；**audit fix**：`model_name/version` 參數化（原硬編碼）

#### Session 5 — DB Infrastructure Hardening ✅
- `db_pool.py`（NEW）：`psycopg2.pool.ThreadedConnectionPool` singleton，min=2/max=10 env-configurable，API `get_conn()`/`put_conn()`/`get_pg_conn()` context manager/`pool_stats()`
- 遷移 consumer：`grafana_data_writer` · `strategy_read_routes` · `phase4_routes`（6 helpers）· `bybit_demo_sync`（pool-first + direct fallback）
- Dashboard silent failure fix：`strategy_read_routes.py` 6 DB failure paths 返回 **HTTP 503** + `{"error": "database_unavailable"}`
- `/api/v1/health/db` endpoint：`pool_stats()` + `SELECT 1` liveness probe

#### Deferred Items（Phase 4/6 or engine-dependent）
- S1-2 realized edge verification — `--days 2` on 2026-04-11
- S2-2b/3 Parquet ETL + scorer training end-to-end（需引擎累積數據）
- S3-1c Optuna dry-run · S3-4 Optuna → IPC → Rust hot-reload
- S4-1 LinUCB warm-start · S4-2 Teacher directive consumer · S4-3 directive outcome backfill
- S5-2b frontend 503 banner · S5-3 trading.orders writer · S5-4 deprecated cleanup
- S6-1 Calibration (Platt + isotonic) · S6-2 DL-3 foundation eval · S6-3 ONNX + ort crate

**測試**：Rust lib 835→838（+3: slippage_tier/js_win_rate/high_volume）· Python control_api 2678/1 fail/15 skip · ml_training 135/6 skip

### Signal Diamond Multi-Engine Data Separation（Phase 1-4 + Fix Round）

**背景**：系統需支持 Paper/Demo/Live 同時運行。核心設計「Signal Diamond」：市場數據→指標→信號（共享）→ Intent 層 fan-out（per-mode 風控/倉位/止損）。規劃文件歸檔：`docs/references/2026-04-10--signal_diamond_db_todo.md`

#### Phase 1 — V015 Migration
- `sql/migrations/V015__engine_mode_separation.sql`：8 交易表加 `engine_mode TEXT NOT NULL DEFAULT 'paper'` + `(engine_mode, ts DESC)` 索引
- `trading.signals` 不改（共享客觀信號）· `agent.ai_invocations` 加 nullable `engine_mode` · 保留 `is_paper` 列（Grafana 向後兼容）

#### Phase 2a — Rust DB Writers
- `TradingMsg::Intent/Fill/PositionSnapshot` + `DecisionContextMsg` 加 `engine_mode: String`
- `trading_writer.rs` + `context_writer.rs` flush 寫 `engine_mode`，`is_paper` 派生自 `engine_mode != "live"`
- `TradingMode::db_mode()`：PaperOnly→"paper" / Demo→"demo" / Live→"live"

#### Phase 3 — ModeState 結構體
- 新檔 `mode_state.rs`（219 行）：`ModeState` struct（PaperState + IntentProcessor + GovernanceCore + risk_store + ring buffers + consecutive_losses + session/pause flags + pending_close + exchange_seq）+ `ModeStateSnapshot` IPC 序列化 + 5 單測
- `TickPipeline` 加 `mode_states: HashMap<TradingMode, ModeState>` + `active_modes: Vec<TradingMode>`
- `PipelineSnapshot.mode_snapshots: HashMap<String, ModeStateSnapshot>`
- `TradingMode` 加 `Hash` derive

#### Phase 4 — IPC + Python
- Rust `ipc_server.rs::get_paper_state` 接受 `engine` 參數（默認 "paper"）+ 新增 `get_mode_snapshot` / `get_active_modes`
- Python `ipc_state_reader.py` mode-aware lookup + `_MODE_ALIASES` fallback
- `ipc_client.py::get_paper_state(mode=)` + 新方法
- `live_session_routes.py` 所有 IPC 調用帶 `{"engine": "live"}`

#### Fix Round — 9 gaps 全修
- **P0 `set_trading_mode()` 雙向 swap**（Critical）：原只改 enum 不保存狀態 → `sync_direct_to_mode_state(old)` → `load_mode_state_to_direct(new)` 雙向 `std::mem::swap`；切換 paper↔demo↔live 時完整保留 PaperState/IntentProcessor/GovernanceCore/consecutive_losses/session_halted/pending_close
- **P2 AddMode/SwitchMode IPC**：`PaperSessionCommand` 加 2 variants + handlers.rs 匹配 + ipc_server.rs 嚴格 enum match + 3s timeout
- **P3 Python IPC mode-aware**：`get_paper_state(mode="paper")` 傳 `{"engine": mode}` + `get_mode_snapshot()` / `get_active_modes()`
- **P1 架構決策（Phase 5+ 記錄）**：策略有內部狀態（grid net_inventory, bb_breakout position flags），同 tick 內多 mode 分別 `on_tick()` 會污染；當前方案支持模式**切換**（state preservation），**不支持同時執行**；未來 per-mode Orchestrator

**新增 5 測試**：`preserves_state` · `same_mode_noop` · `add_mode_and_snapshot` · `mode_snapshot_in_pipeline` · `switch_back_preserves_consecutive_losses`

**E2 OVERALL PASS WITH WARNINGS**：tick_pipeline.rs 3380 行 + ipc_server.rs 3017 行超 §九 1200 限（架構 hub 合理，未來應拆分為 `tick_pipeline_mode_management.rs` + `ipc_dispatch_router.rs`）

**共享 vs 分離決策表**：
| 層級 | 共享 / 分離 |
|---|---|
| market.*/features.*/risk.*/trading.signals/KlineManager/SignalEngine | 共享 |
| trading.intents/fills/orders/position_snapshots/decision_context | **分離** |
| PaperState/IntentProcessor/GovernanceCore/RiskConfig | **分離**（PerEngineRiskStores ✅） |
| Orchestrator（策略） | 共享（Phase 5 分離） |

### 大量 Live/Demo GUI 修復（commits `326a191` → `b4b68c7`）
- 平倉按鈕（per-symbol + 全部平倉）for live/demo/paper
- Sidebar `refreshSidebar()` 改用 `/api/v1/live/session/status` 修復 "mode unknown auth: Not_Granted"
- SM-1 治理授權統一：`grant_paper_authorization(max_position_usd)` 從 Rust `RiskConfig.limits.max_order_notional_usdt` 讀取；live SM-1 授權完整生命週期（DRAFT→PENDING→ACTIVE / REVOKED）
- `_normalize_execution()` Rust→Bybit camelCase 映射
- **DEAD-PY-2**：~4500 行 Python 死代碼清除（bridge/strategies/ProtectiveOrderManager/BybitDemoConnector 交易方法/11 dead tests/10+ surgical class removal）
- **DEAD-PY-1 全部完成**：Wave A/B/C 標籤 + WP-ARCH-RC1 舊命名 + whitelist UI 全量移除（tab-governance.html 220 行 + governance.js 19 行）

### Phase 6 Reconciler 自動降級（commit `a83d73a`）
- 6-RC-1~5,7,8,9,10 完成：Reconciler 從 AUDIT-ONLY 升級為自動動作層
- 觸發：MinorDrift 不動作 / MajorDrift·Orphan·Ghost·SideFlip→Cautious / persistent≥3→Defensive / burst≥5→CB+CloseAll / REST fail≥10→Cautious
- 恢復：逐級，CB/MR operator only；clean cycles + wall-clock
- `ReconcilerState` + `evaluate_actions()` + `ReconcilerEscalate/DeEscalate` IPC + `Arc<AtomicU8>` shared risk level
- **+27 tests** · 872 engine lib + 365 core pass · 6-RC-7 e2e 7 場景 pass · 6-RC-8 live blocker 解除
- 排除 6-RC-6（OC-3 阻塞）

### W19+W20 安全與治理 + SEC-05（commit `a83d73a` + SEC-05 同日）
- G-3 IPC HMAC-SHA256 認證 + G-5 Rate Limiting
- OC-3 多通道告警 + 6-RC-6
- SEC-04/06/13 E3 深度審查 PASS
- G-9 HMAC 確認（NOT dead，L171 auth token 驗證）
- WP-CC/P9 雙軌止損接線（StopRequest→PositionManager.set_trading_stop()）
- FS-1 market_data_client tests 提取（1083→742 行）· BI-1 MODULE_NOTE 12 files
- SM-1 Singleton 合規 · 6-01~03 漸進放權管線（promotion_pipeline.py + 3 API endpoints + 27 tests）
- **SEC-05 innerHTML XSS**：`safeText()`→`ocEsc()` 委託 + 4 badge/label 函數 fallback 修復 + 逐文件 `ocEsc()` 包裹（app.js / linucb_card / tab-ai）+ Risk-tab `_riskFormDirty` 防覆蓋

## 測試基準線 / Test Baseline
- Rust engine lib: **879** + core 365 + e2e 0 fail
- Python: **2792 passed**（1 pre-existing fail `test_risk_view_client`）

## 關鍵決策 / Decisions
1. **Signal Diamond 設計**：共享市場數據 + per-mode intents/fills/positions
2. **Python 層完全無交易邏輯**：DEAD-PY-2 後僅 API 橋接 + GUI 路由 + 輔助工具
3. **ML training scripts 使用 standalone 連接，不走 db_pool**：batch ML job 跨進程，避免不必要耦合
4. **HTTP 503 取代 silent 200**：對前端是 breaking change，S5-2b 銀 banner 作為 follow-up
5. **CPCV model_name/version 參數化**：未來多模型不寫錯誤 metadata
6. **Phase 1 支持模式切換不支持同時執行**：策略內部狀態（grid net_inventory 等）會在多 mode `on_tick()` 間污染，Phase 5+ 解決方案 = per-mode Orchestrator
7. **tick_pipeline.rs / ipc_server.rs 超 1200 行是架構 hub**：未來拆分建議 `tick_pipeline_mode_management.rs` + `ipc_dispatch_router.rs`

## 遺留項 / Remaining
1. Phase 5 Per-Mode Strategy Params（`PerEngineStrategyParams`，複用 `PerEngineRiskStores` 模式）
2. Phase 5+ per-mode Orchestrator 實例（`HashMap<TradingMode, Orchestrator>`）
3. `tick_pipeline.rs` / `ipc_server.rs` 拆分
4. 5 個無 writer 的表：risk_verdicts / orders / order_state_changes / decision_outcomes / ai_invocations 待 writer 實現時帶入 engine_mode
