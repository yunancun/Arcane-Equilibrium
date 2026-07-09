# 2026-04-11 Daily Summary — 3E-ARCH 三引擎並行架構 · 多角色審計 · Phase A-G 修復

**測試基線（收盤）**：930 engine lib + 366 core + 18 e2e = **1314 passed** / 0 failed / 0 ignored · Python 2792 + 6 ipc_state_reader regression passed。
**今日 commit 數**：20+（`6e42c42` → `c9d9bc5` → 本次 paper-tab 路由修復）

---

## 一、主線工作：3E-ARCH 三引擎並行架構

### 1. 起點（開日狀況）
- 系統為 Signal Diamond Phase 3 中間態：單一 TickPipeline + 模式切換
- 用戶觀察到 demo/paper/live 下「永遠只有 3 個不同幣種」持倉
- `trading_mode` 全局配置是單引擎遺物，與三引擎目標矛盾

### 2. 多交易對持倉重構（commit `6e42c42`）

**問題根因**：4 策略（MaCrossover/BbReversion/BbBreakout/GridTrading）各持單一全局 `position: Option<bool>`，理論併發上限僅 4 倉，遠低於風控 `open_positions_max=25`。

**修復**：
- 4 策略全部改為 `HashMap<String, bool>` per-symbol 追蹤
- GridTrading `new()` / `new_geometric()` 移除硬編碼 `"BTC"` key + 預填 grid，改為 `template_bounds` 延遲初始化
- `on_tick` 首次收到 symbol 時：有 template_bounds 用模板邊界，否則 ±10% adaptive
- 生產路徑 `new_adaptive()` 行為不變
- 7 個測試適配

**影響**：理論上限 4 → 100（4 策略 × 25 symbols），實際受風控約束。

### 3. 計劃與規劃（commits `73e627b`, `fee55b3`, `e46e39c`）

- **v1 → v4** `docs/references/2026-04-11--three_engine_parallel_arch_plan.md`（72KB，26 設計決策 D1-D26，六角色整合）
- **執行計劃** `docs/references/2026-04-11--3e_arch_session_execution_plan.md`（13 sessions S0-S13）
- **system_mode GUI→Rust 同步**：`SystemMode` 枚舉（live_reserved/demo_reserved/shadow_only/observe_only/design_only）+ IPC `set_system_mode` + `sync_ipc_call()` + `live_session_routes.py` session status 新欄位

### 4. 主實施 S0-S13（commits `50b408e`, `3287d7d`, `0465605`）

| Phase | 內容 | commit |
|-------|------|--------|
| S0 | Sidebar 顯示修正 + D12 RwLock 審計 + D26 GovernanceCore 驗證 | 前置 |
| S1-S2 | `PipelineKind` + `GovernanceProfile` 枚舉 + D22 `PipelineCommand` rename + `StrategyFactory` | `50b408e` |
| S3-S4 | IntentProcessor 治理分層 + `cost_gate_moderate` + EventConsumerDeps 重構 | `50b408e` |
| S5-S7 | main.rs spawn 骨架 + bounded fan-out + D12 parking_lot + D25 DB pool + D21 per-engine private WS + D17 Live 獨立 runtime + D23 dual reconciler + D6 三級收縮 + 有序 shutdown | `50b408e` |
| S8 | IPC `EngineCommandChannels` + per-engine 快照路由 | `3287d7d` |
| S9 | `TradingMode` → `PipelineKind` 運行時清除 | `3287d7d` |
| S10 | Python 側 trading_mode 清除 + per-engine metrics 隔離 + `DualStateWriter` | `0465605` |
| S11 | API Key 衝突偵測 409 + Watchdog multi-snapshot + Paper balance GUI 輸入 | `0465605` |

---

## 二、多角色審計 + Fix Rounds Phase A-G

### 審計（commits 列表 `a1c3291` 起）

**報告**：`docs/audits/2026-04-11--3e_arch_e2_multi_role_review.md`（633 行、9 角色平行：E2/FA/PA/QC/BB/MIT/E3/E4/E5）

**初審結論**：S0-S11 編譯/測試 pass，但實施不完整：
1. **MEGA-BLOCKER-0**：當前 spawn 是「Primary + Paper alongside」，非用戶目標的「三者無條件並行」
2. **10 BLOCKER + 7 MAJOR + 6 MINOR** 覆蓋 D1-D26 架構缺口

**用戶架構澄清**：唯一運行模式 = Paper/Demo/Live 三者同時並行（各自依 API key 獨立啟停）；`trading_mode` / `TradingMode` enum / `primary_kind` **徹底刪除**。

### Phase A — 快速修復（commit `a1c3291`）
- **BLOCKER-5** `settings_routes.py` `==` → `hmac.compare_digest()` constant-time
- **BLOCKER-6** 5 處 `std::sync::RwLock` → `parking_lot::RwLock`
- **BLOCKER-7** `_save_api_key_lock: asyncio.Lock` 串行衝突檢查→validate→write
- **MAJOR-1** `persistence.rs` chmod 0600 + `#[cfg(unix)]` 回歸測試

### Phase B+C — 配置層 + MEGA-BLOCKER-0 重構（commit `41d5a71`）
- **BLOCKER-8** 4 個 TOML（`paper_config.toml` + `strategy_params_{paper,demo,live}.toml`）+ `StrategyFactory::create_for_engine(kind)` + 7 tests
- **MAJOR-4** Paper balance 優先級統一（env > TOML > Demo API > default）
- **3E-10.1** `main.rs` `determine_primary_kind()` 基於 API key 偵測
- **3E-10.2** 刪除 `config.trading_mode` 字段 + `engine.toml` 清理
- **3E-10.4** Rust `TradingMode` enum 真正刪除
- **3E-10.5** BLOCKER-1 D19 DB 去重（Demo/Live `market_data_tx` = None）
- **3E-10.6** MINOR-2 `pipeline_cmd_rx_paper` 重命名
- **3E-10.7** reconciler_e2e 測試修復（`StateWriter` → `DualStateWriter`）

### Phase D — 架構級補完（commit `e04c974`）
- **BLOCKER-2** D6 三級收縮（`EngineEvent::Crashed/CircuitBreakerTripped` + `PipelineHealth` atomic + `broadcast::channel`）
- **BLOCKER-3** D15 `global_notional_cap_usdt`（`Arc<AtomicU64>` + `check_global_notional_cap()` Gate 2.7 後）
- **BLOCKER-4** D17 Live 獨立 tokio Runtime（`std::thread` + `worker_threads(2)`）
- **MAJOR-2** 啟動競態（`oneshot::channel` per-pipeline ready + fan-out 60s 超時）
- **MAJOR-3** shutdown 分級（WS+IPC → Primary → Paper，10s + Live thread join）
- **MAJOR-5** IPC per-engine audit log
- **MAJOR-7** snapshot `schema_version: "2.0.0"` + `written_at_ms`

### Phase E — 測試補完（commit `e0a7451`）
- **BLOCKER-10** 25 blocker tests：D2 startup barrier / D6 cross-engine + PipelineHealth / D15 8 tests / D23 versioning 3 tests / cascade

### Phase F — 文件拆分（commit `26b9926`）
- **BLOCKER-9** 5 超 1200 行硬上限文件拆分為目錄模組：
  - `tick_pipeline.rs` 3907 → mod(1122) + on_tick(1172) + commands(708) + tests(930)
  - `ipc_server.rs` 3223 → mod(975) + handlers(1195) + tests(1058)
  - `main.rs` 2243 → main(930) + startup(716) + tasks(488)
  - `intent_processor.rs` 1785 → mod(493) + gates(204) + router(499) + tests(597)
  - `position_reconciler.rs` 1397 → mod(617) + escalation(351) + tests(438)

### Phase G — 重跑驗收（commits `de222bd`, `910d2bc`, `2f93738`）

**9 角色並行 3E-E2 重審**：**9/9 PASS** — 0 BLOCKER / 4 MAJOR 非阻塞 / 10 MINOR

原 10 BLOCKER + 7 MAJOR + MEGA-BLOCKER-0 **全確認修復**。

**殘留 Phase G 修復**（commit `910d2bc`）：
- **M-3** `on_tick.rs:497,616` GovernanceProfile hardcoded → `self.pipeline_kind.governance_profile()`（Demo 現用 Validation cost_gate）
- **M-4** Live pipeline 線程加 `catch_unwind` + panic → `Crashed` 廣播 + health=Down
- **m-1** `handle_get_state()` 合併 2 次 snapshot 讀取為 1 次
- **m-2** `std::ptr::eq` → `primary_label()` 字串比對
- **m-3** `determine_primary_kind()` 3→1 次調用
- **m-5** `.unwrap()` → `.expect()` with context
- **m-8** `AuditWriter` 新建檔案 chmod 0600

**非阻塞殘留**：
- M-1: `handlers.rs` 1195 行（下次加 handler 前拆分）
- M-2: `on_tick.rs` 1170 行（-2 行，監控）

**審計報告**：`docs/audits/2026-04-11--3e_arch_phase_g_reaudit.md`

---

## 三、輔線修復

- `2473efb` fix(demo): GUI 平倉透過 Rust shadow channel
- `6bafa4e` fix(live): 同 close position hint 修復套用 live 路由
- `56c648f` fix(engine): paper_only 模式 + cost_gate 冷啟動 exploration（為數據累積）
- `c9d9bc5` fix(3e-arch): `with_kind()` 必須持久化 `pipeline_kind` 字段（三引擎搶寫同一份 paper_state.json）
- **本次** fix(3e-arch): Paper GUI tab 顯示 Live 引擎數據 — Python `RustSnapshotReader` 路由層修復
  - **根因**：`main.rs:563-708` `is_primary` 優先序 Live > Demo > Paper → Live 寫 compat `pipeline_snapshot.json` → `get_paper_state()` 預設讀 compat → paper-tab 顯示 Live 餘額
  - **修復範圍**：`ipc_state_reader.py` 預設改為 `get_engine_snapshot("paper")` + `paper_trading_routes.py` 9 call site 顯式 `engine="paper"` + `risk_routes.py` 3 call site + `strategy_read_routes.py` + `live_session_routes.py` fills 降級
  - **回歸測試**：`TestPerEngineRouting` class 6 tests，使用 11111.11/22222.22/33333.33 哨兵餘額（避免與真實數據混淆）
  - **驗證**：reader 直讀真實 `/tmp/openclaw/pipeline_snapshot_*.json`，paper 預設返回 9941.47 / 9 倉位（之前 612.95 / 0 倉位）

---

## 四、決策記錄

1. **不留 deprecated 過渡**：`TradingMode` enum 徹底刪除，避免長期技術債
2. **Paper 作為 DB 寫入唯一管線**：Demo/Live `market_data_tx` / `feature_tx` 設為 `None`，避免重複寫入
3. **Live 獨立 tokio runtime**：隔離 std::thread + worker_threads(2)，防止 Paper/Demo 阻塞傳染到實盤
4. **parking_lot::RwLock 跨引擎共享**：非中毒語義，單管線 panic 不會級聯污染其他管線
5. **Phase G 殘留 M-1/M-2 非阻塞**：handlers.rs 1195 / on_tick.rs 1170 暫不拆，下次加 handler 前處理

---

## 五、完成標誌

- **3E-ARCH**：三引擎並行架構 100% 完成，D1-D26 全部實施
- **3E-E2 Fix Rounds**：Phase A-G 全部 PASS，9/9 角色重審通過
- **Live_Ready** ✅：Paper/Demo/Live 各自依 API key 獨立啟停，trading_mode 徹底消失
- **測試基線**：929 engine lib + 366 core + 18 e2e = 1313 / 0 failed · Python 2792 / 0 failed

---

## 六、下一步指針

主線轉回 TODO.md 第一個 `[ ]`：
- **PH5-VERIFY-1** 7d paper observation 窗口（2026-04-10 fresh-start 起算）
- **JS 滾動重跑**（Day 2 = 2026-04-11：`python3 -m program_code.ml_training.james_stein_estimator --days 2`）
- **LG-1** Paper Trading 21 天倒計時（最早 2026-05-01 完成）

詳見 TODO.md。
