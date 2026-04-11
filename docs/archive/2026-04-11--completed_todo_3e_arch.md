# 已完成 TODO 歸檔：3E-ARCH 三引擎並行架構 + 3E-E2 Fix Rounds Phase A-G

**歸檔日期**：2026-04-11
**來源**：`TODO.md` §3E-ARCH（S0-S13）+ §3E-E2 Fix Rounds（Phase A-G）
**狀態**：全部 commit 完成，已移出主 TODO.md。
**測試基線**：929 engine lib + 366 core + 18 e2e = 1313 passed / 0 failed / 0 ignored · Python 2792 passed。

---

## 背景與目標

**背景**：系統原本是「單一 TickPipeline + 模式切換」（Signal Diamond Phase 3 中間態）。`trading_mode` 全局配置是單引擎遺物，三引擎世界中無意義。

**用戶 2026-04-11 架構澄清**：
- 唯一運行模式 = Paper/Demo/Live **三者同時並行**（各自依 API key 存在性獨立啟停）
- `trading_mode` / `TradingMode` enum / `primary_kind` **徹底刪除**，不留 deprecated 過渡
- 每個 Pipeline 啟動條件 = 自己的 API key + system_mode 允許

**計劃文件**：
- `docs/references/2026-04-11--three_engine_parallel_arch_plan.md`（v4，26 設計決策 D1-D26）
- `docs/references/2026-04-11--3e_arch_session_execution_plan.md`（13 sessions，S0-S13）

---

## Part 1 — 3E-ARCH 主實施（S0-S13）

### S0：前置
- [x] **3E-6** Sidebar 顯示修正 + D12 RwLock 審計 + D26 GovernanceCore 驗證

### S1-S2：Rust 基礎
- [x] **3E-1** `PipelineKind` + `GovernanceProfile` 枚舉 + D22 `PipelineCommand` rename
- [x] **3E-9** `StrategyFactory` + per-engine 策略參數 TOML（create_all() 替代硬編碼）

### S3-S4：Pipeline 構造
- [x] **3E-2a-α** IntentProcessor 治理分層 + `cost_gate_moderate` + GovernanceProfile param
- [x] **3E-2a-β** EventConsumerDeps 重構 + Pipeline kind-based 構造

### S5-S7：三管線並行（最高風險）
- [x] **3E-2b-α** main.rs spawn 骨架 + bounded fan-out + D12 parking_lot + D25 DB pool
- [x] **3E-2b-β** D21 per-engine private WS supervisor + D17 Live 獨立 runtime
- [x] **3E-2b-γ** D23 dual reconciler + D6 三級遞減收縮 + 有序 shutdown

### S8-S11：IPC + trading_mode 清除
- [x] **3E-3** IPC Server `EngineCommandChannels` + per-engine 快照路由
- [x] **3E-4** `TradingMode` → `PipelineKind` 運行時清除（config 保留過渡橋接）
- [x] **3E-5** Python 側 trading_mode 清除 + per-engine metrics 隔離
- [x] **3E-7** API Key 衝突偵測 409
- [x] **3E-8** Watchdog multi-snapshot + Paper balance GUI 輸入

### S12-S13：驗收
- [x] **3E-E2** Phase G 重審 **9/9 PASS**（0 BLOCKER / 4 MAJOR 非阻塞 / 10 MINOR）
- [x] **3E-E4** E4 測試回歸 PASS — 929 lib + 366 core + 18 e2e = 1313 passed

---

## Part 2 — 3E-E2 Fix Rounds（多角色審計後修復，Phase A-G）

**審計報告**：`docs/audits/2026-04-11--3e_arch_e2_multi_role_review.md`（633 行、9 角色平行審查）
**重審報告**：`docs/audits/2026-04-11--3e_arch_phase_g_reaudit.md`

**初審結論**：3E-ARCH S0-S11 編譯/測試 pass，但實施不完整：
1. **MEGA-BLOCKER-0**：當前 spawn 是「Primary + Paper alongside」，非用戶目標的「三者無條件並行」
2. **10 BLOCKER + 7 MAJOR + 6 MINOR** 覆蓋 D1-D26 架構缺口

### Phase A — 快速修復（commit a1c3291）
- [x] **BLOCKER-5** `settings_routes.py:391` `==` → `hmac.compare_digest()`（constant-time）
- [x] **BLOCKER-6** 5 處 `std::sync::RwLock` → `parking_lot::RwLock`（types.rs + main.rs PrivateWsBindings + account_manager.rs）
- [x] **BLOCKER-7** `settings_routes.py` `_save_api_key_lock: asyncio.Lock` 串行衝突檢查→validate→write
- [x] **MAJOR-1** `persistence.rs` StateWriter chmod 0600（rename 前）+ `#[cfg(unix)]` 回歸測試

### Phase B+C — 配置層補完 + 三引擎並行重構（commit 41d5a71，MEGA-BLOCKER-0）
- [x] **BLOCKER-8** 4 個 TOML 配置文件 + `load_strategy_params()`
  - `settings/paper_config.toml`、`settings/strategy_params_{paper,demo,live}.toml`
  - `StrategyParamsConfig` + `StrategyFactory::create_for_engine(kind)` + 7 tests
- [x] **MAJOR-4** Paper balance 優先級統一（env > TOML > Demo API > hardcoded default）
- [x] **3E-10.1** `main.rs` spawn 邏輯重構 — `determine_primary_kind()` 基於 API key 偵測取代 `config.trading_mode`
- [x] **3E-10.2** 刪除 `config.trading_mode` 字段 + `engine.toml` 清理
- [x] **3E-10.3** Python serde `pipeline_kind` → `"trading_mode"` 向後兼容確認
- [x] **3E-10.4** Rust `TradingMode` enum 真正刪除 + `mode_state.rs` 遷移至 `PipelineKind`
- [x] **3E-10.5** **BLOCKER-1 D19 DB 去重** — Demo/Live 管線 `market_data_tx` / `feature_tx` 設為 `None`
- [x] **3E-10.6** **MINOR-2 paper_cmd_rx 改名** — `pipeline_cmd_tx_paper` / `pipeline_cmd_rx_paper`
- [x] **3E-10.7** reconciler_e2e 測試修復（`StateWriter` → `DualStateWriter`）

### Phase D — 架構級補完（commit e04c974）
- [x] **BLOCKER-2** D6 三級遞減收縮（`EngineEvent::Crashed/CircuitBreakerTripped` + `PipelineHealth` atomic + `broadcast::channel` 跨引擎通知 + 對等管線 Cautious 升級）
- [x] **BLOCKER-3** D15 `global_notional_cap_usdt`（`Arc<AtomicU64>` 跨引擎共享 + `IntentProcessor.check_global_notional_cap()` Gate 2.7 後檢查 + Paper 排除）
- [x] **BLOCKER-4** D17 Live 獨立 tokio Runtime（`std::thread` + `worker_threads(2)` + Demo/Paper 共享 runtime）
- [x] **MAJOR-2** 啟動競態修復（`oneshot::channel` per-pipeline ready 信號 + fan-out 等待 60s 超時）
- [x] **MAJOR-3** shutdown 分級順序（WS+IPC → Primary → Paper，10s 超時 + Live thread join）
- [x] **MAJOR-5** IPC per-engine audit log（`dispatch_request` 入口 `ipc_method` + `target_engine`）
- [x] **MAJOR-7** snapshot 格式版本號（`schema_version: "2.0.0"` + `written_at_ms`）

### Phase E — 測試補完（commit e0a7451）
- [x] **BLOCKER-10** 25 blocker tests（D2 startup barrier / D6 cross-engine events + PipelineHealth / D15 global notional cap 8 tests / D23 snapshot versioning 3 tests / cascade 測試）

### Phase F — 文件拆分（commit 26b9926）
- [x] **BLOCKER-9** 5 個超 1200 硬上限文件拆分：
  - `tick_pipeline.rs` 3907 → mod.rs(1122) + on_tick.rs(1172) + commands.rs(708) + tests.rs(930)
  - `ipc_server.rs` 3223 → mod.rs(975) + handlers.rs(1195) + tests.rs(1058)
  - `main.rs` 2243 → main.rs(930) + startup.rs(716) + tasks.rs(488)
  - `intent_processor.rs` 1785 → mod.rs(493) + gates.rs(204) + router.rs(499) + tests.rs(597)
  - `position_reconciler.rs` 1397 → mod.rs(617) + escalation.rs(351) + tests.rs(438)

### Phase G — 重跑驗收（commits de222bd / 910d2bc / 2f93738）
- [x] 9 角色並行 3E-E2 重審 — **9/9 PASS**（0 BLOCKER / 4 MAJOR 非阻塞 / 10 MINOR）
- [x] 所有原 10 BLOCKER + 7 MAJOR + MEGA-BLOCKER-0 全確認修復
- [x] 更新 `CLAUDE.md` §三 + `docs/CLAUDE_CHANGELOG.md` + 基線測試數
- [x] **殘留修復**：
  - M-3：`on_tick.rs:497,616` GovernanceProfile hardcoded → `self.pipeline_kind.governance_profile()`（Demo 現用 Validation cost_gate）
  - M-4：Live pipeline 線程加 `catch_unwind` + panic → `Crashed` 廣播 + health=Down；shutdown JoinError panic 記錄
  - m-1：`handle_get_state()` 合併 2 次 snapshot 讀取為 1 次
  - m-2：`std::ptr::eq` → `primary_label()` 字串比對
  - m-3：`determine_primary_kind()` 3→1 次調用
  - m-5：`.unwrap()` → `.expect()` with context
  - m-8：`AuditWriter` 新建檔案 chmod 0600
- **殘留 2 MAJOR 非阻塞**（文件大小監控）：
  - M-1: `handlers.rs` 1195 行（下次加 handler 前拆分）
  - M-2: `on_tick.rs` 1170 行（-2 行，監控）

---

## 完成標誌

- **Commit 列表（本日 13 個 3E-ARCH 相關 commit）**：
  - `6e42c42` multi-symbol HashMap refactor + SwitchMode auth re-grant
  - `73e627b` 3E-ARCH plan + system_mode session status
  - `56c648f` paper_only mode + cost_gate cold-start exploration
  - `fee55b3` 3E-ARCH plan v3 — six-role review integrated (D9-D20)
  - `e46e39c` 3E-ARCH plan v4 + 13-session execution plan
  - `2473efb` GUI close position routes through Rust shadow channel (demo)
  - `6bafa4e` apply same close position hint fix to live route
  - `50b408e` 3E-ARCH S0-S7 — multi-pipeline spawn skeleton + fan-out + parking_lot
  - `3287d7d` 3E-3+4 IPC EngineCommandChannels + TradingMode→PipelineKind cleanup
  - `0465605` 3E-5+7+8 per-engine snapshots + Python trading_mode cleanup + API key conflict + Paper GUI
  - `a1c3291` Phase A quick fixes — API key security + parking_lot + snapshot chmod
  - `41d5a71` Phase B+C — per-engine TOML params + TradingMode deletion
  - `e04c974` Phase D — architecture-level hardening (3 BLOCKER + 4 MAJOR)
  - `e0a7451` Phase E — 25 blocker tests for D2/D6/D15/D23
  - `26b9926` Phase F — split 5 oversized files (BLOCKER-9)
  - `de222bd` Phase G — 9-role re-audit PASS
  - `910d2bc` resolve M-3/M-4 + 8 MINORs from Phase G audit
  - `2f93738` docs: update TODO + CHANGELOG for Phase G residual fixes

- **測試基線**：929 engine lib + 366 core + 18 e2e = 1313 passed / 0 failed / 0 ignored
- **架構完成度**：Paper/Demo/Live 三管線各自依 API key 獨立啟停；`TradingMode`/`primary_kind` 徹底刪除；D1-D26 全部實施；9/9 角色審計 PASS。
