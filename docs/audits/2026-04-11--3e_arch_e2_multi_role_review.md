# 3E-ARCH S0-S11 多角色並行 E2 審查報告

**審查日期**：2026-04-11  
**審查範圍**：3E-ARCH 三引擎並行架構實施（S0-S11）  
**審查方式**：9 個角色並行獨立審查（E2/FA/PA/QC/BB/MIT/E3/E4/E5）  
**commits**：`50b408e` (S0-S7) + `3287d7d` (S8-S9) + `0465605` (S10-S11)  
**計劃文件**：`docs/references/2026-04-11--three_engine_parallel_arch_plan.md` (D1-D26)

---

## 0. 核心結論

**3E-E2 不通過**。發現 **10 個 BLOCKER + 7 個 MAJOR + 多個 MINOR/建議**。此外發現一個 **MEGA-BLOCKER-0** 影響整個架構定位：

> **當前實施實際是「Primary Pipeline（Demo 或 Live，由 `config.trading_mode` 決定）+ Paper alongside」，不是用戶目標的「Paper + Demo + Live 三者無條件同時並行」**。

**用戶 2026-04-11 澄清的正確目標**：
- 唯一一個運行模式 = 三者同時並行
- 每個 Pipeline 的啟動條件 = 自己的 API key 是否存在 + system_mode 允許
- `trading_mode` 全局配置必須徹底消除（連過渡 deprecated 都不要）
- 用戶可以選擇不啟動某些引擎（通過不配 key），但架構不能有「選一個為 primary」的邏輯

這意味著 3E-4「TradingMode 清除」實際上做得不徹底——它保留了 `TradingMode` 作為「主管線選擇器」，而不是真的讓三個 Pipeline 各自獨立存在。

---

## 1. 角色審查一覽

| 角色 | 結論 | 發現總數 | 主要 blocker |
|------|------|---------|--------------|
| E2 | ❌ Fail | 3 🔴 + 3 🟡 + 3 🟢 | 5 個文件超 1200 硬上限 |
| FA | ⚠️ ~70% 實施 | 3 🔴 + 4 🟡 | D6/D15/D17 未實施 |
| PA | ⚠️ 誠實性 85-90% | 7 項需回補 | D15/D17/D7/D9 TOML 缺 |
| QC | ⚠️ 94% 覆蓋 | 5 🛑 + D12 漏遷 | 大文件 + std::sync::RwLock 殘留 |
| BB | ❌ 6 高概率 bug | 6 🔴 + 3 🟡 + 2 🟢 | 啟動競態 + DB pool + Reconciler CB |
| MIT | ❌ 失敗隔離 90% 缺失 | 3 原則違反 | D6 + catch_unwind + shutdown 順序 |
| E3 | ⚠️ Timing attack + 設計縫隙 | 1 🔴 + 3 🟡 | hmac.compare_digest |
| E4 | ❌ 測試覆蓋 43% | 缺 ~23 blocker tests | D1/D2/D6/D21/D23 等測試缺 |
| E5 | ❌ D19/D17 未實施 | 3 🔴 + 1 🟡 | DB 3× 寫入 + Live CPU 爭搶 |

**編譯/測試基線**：
- `cargo check -p openclaw_engine`：✅ pass（11 個 deprecated TradingMode warning）
- `cargo clippy`：115 warnings（可接受）
- `cargo test -p openclaw_engine --lib`：**896 passed**（baseline 879，+17）
- `cargo test -p openclaw_core --lib`：366 passed
- `reconciler_e2e`：18 passed
- Python `pytest --collect-only`：2797 collected
- **0 新破測試**

---

## 2. 🔴 MEGA-BLOCKER-0：三引擎並行實施不完整

**來源**：FA + E3 + PA 交叉發現  
**位置**：`rust/openclaw_engine/src/main.rs:641-713, 1710-1897`

**問題詳述**：
當前 main.rs spawn 邏輯：
1. 讀 `config.trading_mode`（仍是 TradingMode enum）
2. 映射為 `primary_kind`（PaperOnly/Demo/Live 其中一個）
3. Spawn Primary Pipeline（`run_event_consumer(primary_kind, ...)`）
4. 若 `primary_kind != Paper`，額外 spawn Paper alongside

**即是說**：代碼永遠最多 spawn 2 個 Pipeline（Primary + Paper），從不 spawn 3 個。Demo 和 Live 互斥。

**用戶目標反推**：
- 三個 Pipeline 必須獨立判斷啟動條件
- Paper：永遠嘗試 spawn（initial_balance 視 Demo key 存在性決定來源）
- Demo：若 demo slot 有 API key → spawn
- Live：若 live slot 有 API key 且 ≠ demo key → spawn
- 三個判斷獨立，無「選一個當 primary」的邏輯
- `TradingMode` / `primary_kind` / `config.trading_mode` 全部移除

**影響面**：
- BLOCKER-2 / BLOCKER-3 / BLOCKER-4 的實施都要基於這個重構
- 3E-4 必須重做（之前把 TradingMode 標為 deprecated 保留過渡，現在要真的刪）
- Python 側 `ipc_state_reader.py` / `live_session_routes.py` 的向後兼容 trading_mode 引用也要清零
- engine.toml 的 `trading_mode` 字段刪除
- 所有測試和 env var（`TRADING_MODE` 等）清除

**修復工作量**：2-3 天（main.rs spawn 重構 + config 字段移除 + Python 清理 + 測試調整 + 可能影響 D1/D21/D23 的邊界條件）

**建議 TODO**：新增 **3E-10：三引擎無條件並行重構**（MEGA-BLOCKER-0）

---

## 3. 🔴 BLOCKER — 必修才能進 S13

### BLOCKER-1：D19 DB 去重寫入未實施
**來源**：E5  
**位置**：`rust/openclaw_engine/src/main.rs:1824-1825`  
**問題**：Demo/Live Pipeline 的 `EventConsumerDeps` 仍傳 `market_tx.clone()` / `feature_tx.clone()`，未按計劃設 None。  
**後果**：
- market_data 被三管線重複寫入 3×
- 每天額外 ~60-80M 行垃圾寫入（按 25 tick/s × 25 symbols × 86400s 估算）
- PG pool 壓力 3×
- **剛 2026-04-10 執行的 fresh-start reset 會被快速再次污染**
- 計劃宣稱的 -40% I/O 節省完全失效

**修復**：
```rust
// main.rs:1824-1825
market_data_tx: matches!(deps.pipeline_kind, PipelineKind::Paper).then(|| market_tx.clone()),
feature_tx:    matches!(deps.pipeline_kind, PipelineKind::Paper).then(|| feature_tx.clone()),
```
**工作量**：5 分鐘

---

### BLOCKER-2：D6 三級遞減收縮完全未實施
**來源**：FA + MIT + BB  
**位置**：整個架構缺失

**問題**：
- `grep -rn "cross_engine_notify\|EngineEvent::Crashed\|PipelineHealth" rust/openclaw_engine/src/` → 零結果
- 計劃明確要求 Paper crash → Demo Cautious 60s / Demo crash → Live Cautious 120s
- `tokio::spawn` 無 `catch_unwind` → panic 靜默死亡，其他 Pipeline 完全無感知

**違反原則**：#6 失敗默認收縮 / #5 生存 > 利潤

**後果**：
- Paper 激進 CB → Demo/Live 不知情 → 連鎖下單
- Demo panic → Live 繼續 blow up
- 一個 Pipeline 內部 panic → task 靜默消失，外層 handle 誤以為仍在跑

**修復步驟**：
1. 新增 `EngineEvent` enum（`Crashed(PipelineKind)` / `CircuitBreakerTripped(PipelineKind)`）
2. 新增 `cross_engine_event_tx: broadcast::Sender<EngineEvent>`，每個 Pipeline 持有 `subscribe()`
3. Pipeline 主循環在 `tokio::select!` 中監聽 `cross_engine_event_rx`
4. spawn 外層包 `std::panic::AssertUnwindSafe(catch_unwind)`
5. panic/CB 時發送 `EngineEvent`，其他 Pipeline 對應 escalate_to(Cautious)
6. 加 `Arc<AtomicU8> PipelineHealth {Running, Paused, Down}` per-engine

**工作量**：1-2 天

---

### BLOCKER-3：D15 全局資本敞口上限未實施
**來源**：FA + PA + MIT  
**位置**：`rust/openclaw_engine/src/intent_processor.rs` 無跨管線查詢  
**grep 結果**：`grep -rn "global_notional_cap"` 零結果

**問題**：每個引擎只檢查自己的 `total_exposure_max_pct`。Paper 用 Demo 餘額 + Demo 滿倉 + Live 滿倉 = 同資金池 2-3× 名義敞口，無風控攔截。

**修復步驟**：
1. `risk_config.toml` 頂層加 `global_notional_cap_usdt`
2. 新增 `Arc<AtomicU64> global_exposure_usdt`，由 Demo/Live exchange pipeline 各自 add/sub
3. Paper 不計入（本地模擬）
4. `IntentProcessor::check_global_notional_cap()` 在 P1 cap 檢查後執行
5. 超限 → 拒絕 + audit log

**工作量**：半天

---

### BLOCKER-4：D17 Live Pipeline 優先級保護未實施
**來源**：FA + MIT + E5  
**位置**：`rust/openclaw_engine/src/main.rs:210`

**問題**：三管線共享單一 `tokio::runtime::Builder::new_multi_thread()`。Paper 25 symbols × 4 strategies = 100+ pending intents/tick 會搶 Live CPU。

**後果**：Live on_tick P99 延遲可能 +100~500ms，高波動時段滑點擴大、止損失效。

**修復**：
```rust
let live_runtime = tokio::runtime::Builder::new_multi_thread()
    .worker_threads(2)
    .enable_all()
    .thread_name("openclaw-live")
    .build()?;
let live_handle = std::thread::spawn(move || {
    live_runtime.block_on(async {
        tokio::spawn(private_ws_supervisor(live_priv_ws, ...));
        tokio::spawn(run_position_reconciler(live_reconciler, "live", ...));
        run_event_consumer(live_deps).await
    })
});
```

**工作量**：半天（但依賴 MEGA-BLOCKER-0 重構完成）

---

### BLOCKER-5：API Key 衝突檢測 Timing Attack
**來源**：E3  
**位置**：`program_code/exchange_connectors/bybit_connector/control_api_v1/app/settings_routes.py:391`

**問題**：
```python
if existing_key and existing_key.strip() == api_key:  # ❌ 非常數時間
```
Secret equality 應使用 `hmac.compare_digest`。攻擊者可通過 timing side-channel 逐字節探測已存 key。

**修復**：
```python
import hmac
if existing_key and hmac.compare_digest(existing_key.strip(), api_key):
```
**工作量**：5 分鐘

---

### BLOCKER-6：D12 parking_lot 遷移不完整
**來源**：QC + E5  
**位置**：
- `rust/openclaw_engine/src/event_consumer/types.rs:82-83`（`bybit_balance: Arc<RwLock<Option<f64>>>` + `api_pnl: Arc<RwLock<HashMap<...>>>`）
- `main.rs:1040-1041` 構造處

**問題**：這兩個在 Demo/Live pipeline 每 tick 讀寫，若某處 panic 會 poison 導致級聯崩潰。也有 ~2-3× 延遲開銷。

**grep 結果**：`grep -rn "std::sync::RwLock" rust/openclaw_engine/src/ rust/openclaw_core/src/` → 5 處（main.rs:1040/1041、types.rs:88/89、account_manager）

**修復**：全量改 `parking_lot::RwLock`（不需要 `.unwrap()`）。  
**工作量**：15 分鐘

---

### BLOCKER-7：Settings API Key 更新競態
**來源**：BB  
**位置**：`settings_routes.py:382-400`

**問題**：POST `/api/v1/settings/api-key/<slot>` 無 lock。TOC/TOU 場景：
- Thread A: 讀 live key（舊值 `KEY_X`）→ 衝突檢查 passed
- Thread B: 寫 live = `KEY_X` → 讀 demo（舊值 `KEY_Y`）→ 衝突檢查 passed
- Thread A: 寫 demo = 某值 → 兩個 slot 實際寫入後可能形成衝突狀態，D2 保護失效

**修復**：
```python
_SETTINGS_LOCK = asyncio.Lock()

@router.post("/api/v1/settings/api-key/{slot}")
async def update_api_key(slot: str, ...):
    async with _SETTINGS_LOCK:
        # read → conflict check → write 全程原子
        ...
```
**工作量**：15 分鐘

---

### BLOCKER-8：D7/D9 per-engine 配置 TOML 不存在
**來源**：PA + QC  
**位置**：`settings/` 目錄

**問題**：計劃要求的 4 個 TOML 全部未創建：
- `settings/paper_config.toml`（D7：Paper 初始餘額、運行參數）
- `settings/strategy_params_paper.toml`（D9：寬參數範圍）
- `settings/strategy_params_demo.toml`（D9：中等範圍）
- `settings/strategy_params_live.toml`（D9：生產固定值）

GUI `POST /api/v1/paper/config` 端點寫入空文件（因沒有 schema）；D4 策略角色分層完全未生效（所有引擎跑默認參數）。

**修復**：
1. 創建 4 個 TOML 模板（按計劃 §3E-9 的範例格式）
2. 實現 `load_strategy_params(orchestrator, kind)` 函數（計劃 §D8 已給 reference 代碼）
3. 在 event_consumer.rs 策略註冊後調用 load_strategy_params
4. 測試：missing file / 畸形 TOML / 部分 section 各場景

**工作量**：半天

---

### BLOCKER-9：大文件嚴重超 1200 硬上限
**來源**：E2 + QC  
**位置**：5 個文件

| 文件 | 行數 | 超限倍數 |
|------|------|---------|
| `rust/openclaw_engine/src/tick_pipeline.rs` | **3717** | 🛑 309% |
| `rust/openclaw_engine/src/ipc_server.rs` | **3197** | 🛑 266% |
| `rust/openclaw_engine/src/main.rs` | **2004** | 🛑 167% |
| `rust/openclaw_engine/src/intent_processor.rs` | **1614** | 135% |
| `rust/openclaw_engine/src/position_reconciler.rs` | **1397** | 116% |

**CLAUDE.md §九明確規定**：「1200 行硬上限 不允許 merge」

**修復建議拆分方案**：
- `tick_pipeline.rs` → `tick_pipeline/mod.rs` + `tick_pipeline/intent_flow.rs` + `tick_pipeline/paper_state.rs` + `tick_pipeline/snapshot.rs` + `tick_pipeline/commands.rs`
- `ipc_server.rs` → `ipc_server/mod.rs` + `ipc_server/handlers_{strategy,risk,paper,live,snapshot}.rs`
- `main.rs` → `main.rs` + `bootstrap/{pipeline_spawn,fanout,shutdown}.rs`
- `intent_processor.rs` → `intent_processor/{mod,cost_gate,guardian_gate,kelly,p1_cap,global_cap}.rs`
- `position_reconciler.rs` → `position_reconciler/{mod,drift_classify,action_dispatch,cooldown}.rs`

**工作量**：2-3 天（獨立 session，需 E2 + E4 驗收）

---

### BLOCKER-10：測試覆蓋 17/40
**來源**：E4

計劃 §九要求 ~40 新測試覆蓋 D1-D26 + 3E-7/8，實際只新增 17。缺 ~23 blocker tests：

| D項 | 測試缺口 | 建議測試 |
|-----|---------|---------|
| D2/3E-7 | API key 衝突 409 | 3 tests (demo↔live / live↔demo / allow non-conflict) |
| D1 | Live 條件式啟動 | 2 tests (key 有效啟動 / 無 key skip) |
| D6 | 三級遞減收縮 | 3 tests (blocker-2 完成後) |
| D21 | Private WS 路由隔離 | 4 tests |
| D23 | Reconciler 雙實例隔離 | 3 tests |
| D5/D9 | per-engine JS edge | 4 tests |
| D15 | 全局 notional cap | 2 tests |
| D24 | StopManager REST 綁定 | 3 tests |
| D26 | GovernanceCore 多實例 | 2 tests |
| D7 | Paper balance 配置 | 2 tests |

**工作量**：3E-E4 session，1-2 天

---

## 4. 🟡 MAJOR — 強烈建議修

### MAJOR-1：snapshot 文件未 chmod 0600
**來源**：E3  
**位置**：`rust/openclaw_engine/src/persistence.rs:44-50`

**問題**：atomic write (tmp→rename) 正確，但未顯式 `std::fs::set_permissions(path, 0o600)`。檔案預設權限依 umask（通常 644，可讀）。  
`pipeline_snapshot_live.json` 含 live 帳戶餘額（非關鍵但敏感）。  
對比：`settings_routes.py::_write_key_file()` 已實施 chmod 600 ✅

**修復**：
```rust
#[cfg(unix)]
{
    use std::os::unix::fs::PermissionsExt;
    std::fs::set_permissions(&final_path, std::fs::Permissions::from_mode(0o600))?;
}
```

---

### MAJOR-2：啟動競態 — WS tick 可能在 Pipeline 初始化完成前抵達
**來源**：BB  
**位置**：`main.rs:955` WS client 啟動 vs event_consumer 內部 `StrategyFactory::create_all()` + kline_bootstrap

**問題**：Pipeline spawn 後，StrategyFactory::create_all() 和 kline_bootstrap 需要秒級時間。期間 WS tick 已進入 fan-out channel，被 try_send 失敗（1024 buffer）或進入 channel 後策略未註冊時消費 → undefined behavior。

D11 要求「阻塞式初始化」，但現實施未見 barrier 機制。

**修復**：
- 選項 A：Pipeline 初始化完成後才註冊 fan-out sender
- 選項 B：用 tokio `Barrier` 或 `oneshot::channel` 等三個 Pipeline 都 ready 才啟動 WS 消費
- 選項 C：Pipeline 首次 tick 到達時先 drain＋discard 直到 strategy ready

---

### MAJOR-3：shutdown 無 Live→Demo→Paper 分級順序
**來源**：MIT + BB  
**位置**：`main.rs:1922-1928`

**問題**：三個 handle（ws_handle/ipc_handle/event_handle/_paper_handle）並行 `.await`，無嚴格順序。Live 數據最重要但無優先 flush。DB writer buffered writes 未保證 flush。

D6 要求「有序 shutdown：Live 先 drain+flush → Demo → Paper」。

**修復**：
```rust
cancel.cancel();
// 1. 先停 Live（阻塞等它 flush）
if let Some(h) = live_handle { let _ = h.join(); }
// 2. 再停 Demo
if let Some(h) = demo_handle { let _ = h.await; }
// 3. 最後 Paper
let _ = paper_handle.await;
// 4. DB writer 最後 flush + close
```

---

### MAJOR-4：Paper initial_balance 優先級混亂
**來源**：BB  
**位置**：`main.rs:689-699` vs `paper_trading_routes.py` 新端點

**問題**：有三個來源：
1. `OPENCLAW_PAPER_BALANCE` env var
2. GUI 寫入 `settings/paper_config.toml::initial_balance_usdt`（3E-8）
3. Demo API key 存在時讀 `fetch_exchange_balance(Demo)`

優先級不明確。當前代碼 `main.rs:689-699` 是 Live trading_mode 時把 paper_balance 設為 demo balance，但 paper_config.toml 根本還沒創建（BLOCKER-8）。

**修復**：文檔化優先級 = Demo API balance > GUI config > env var > default；所有三處統一在 `resolve_paper_initial_balance()` 函數。

---

### MAJOR-5：IPC engine 參數路由無 per-engine authz
**來源**：E3  
**位置**：`rust/openclaw_engine/src/ipc_server.rs:133-138`

**問題**：
```rust
pub fn select(&self, engine: &str) -> &Option<...> {
    match engine {
        "demo" => &self.demo,
        "live" => &self.live,
        _ => &self.paper,
    }
}
```
G-3 HMAC 已認證連線級，但任何客戶端可發 `{"method":"pause_paper","params":{"engine":"live"}}` 暫停 Live。缺少 per-engine authz。

**修復**：
- 短期：dispatch_request 記錄 audit log（`actor_id=X, engine=Y, method=Z`）
- 長期：引入 role/permission 概念（viewer vs operator vs admin），live 操作需 admin

---

### MAJOR-6：D24 StopManager REST 綁定未驗證測試
**來源**：PA  
**位置**：`rust/openclaw_engine/src/stop_manager.rs`

**問題**：代碼層面 StopManager 構造時接收 `Option<Arc<BybitRestClient>>`（EventConsumerDeps 有），但缺測試確認 Demo StopManager 用 Demo client、Live StopManager 用 Live client、Paper StopManager 為 None。

**修復**：補 3 個單測（BLOCKER-10 的一部分）。

---

### MAJOR-7：Snapshot 寫入無跨管線版本號
**來源**：BB  
**位置**：`persistence.rs`

**問題**：三個 snapshot 文件各自 atomic write，但 Watchdog/GUI 讀時可能：
- 讀到 Paper v1 + Demo v1 + Live v2（Live 剛寫完）
- 導致 UI 顯示混合版本狀態

**修復**：每個 snapshot 加 `schema_version` + `written_at_ms`；reader 檢查時間差 > 閾值時告警；或統一 snapshot 加 `cross_engine_generation` 序號。

---

## 5. 🟢 MINOR — 可後續跟進

### MINOR-1：clippy 115 warnings
**來源**：QC  
主要類型：`negated_cmp_op`, `too_many_arguments`, `unused_dead_code`。可接受但建議清理。

### MINOR-2：`paper_cmd_rx` 變數名殘留
**來源**：E2 + QC  
**位置**：`main.rs:1858, 1877`  
D22 要求全量 rename 為 `pipeline_cmd_rx`，這兩處遺漏（功能正確，僅命名不一致）。

### MINOR-3：Python `trading_mode` serde 向後兼容殘留
**來源**：E2  
**位置**：
- `paper_trading_routes.py:378` — 快照中的 `"trading_mode"` fallback
- `ipc_state_reader.py:182` — 快照路由時檢查 `trading_mode` 匹配
- `live_session_routes.py:252, 257` — 向後兼容檢查主快照的 `trading_mode`

MEGA-BLOCKER-0 修復後應全部清零。

### MINOR-4：11 個 `#[deprecated] TradingMode` warning
**來源**：QC  
3E-4 的過渡 deprecation，MEGA-BLOCKER-0 修復後全部刪除。

### MINOR-5：`paper_trading_routes.py` / `live_session_routes.py` MODULE_NOTE 雙語覆蓋
**來源**：E2  
CLAUDE.md 強制要求雙語 MODULE_NOTE / docstring，新增的 endpoint 需補充中英對照。

### MINOR-6：E2 誤報 Cargo.toml BLOCKER
**來源**：E2（需否決）  
E2 agent 報告「Cargo.toml 工作區成員指向錯誤路徑」導致 cargo check 失敗。**QC agent 實際跑 cargo check PASS**。E2 是看文件內容猜測，QC 是執行命令。採納 QC 結果，E2 這條不採納。

---

## 6. 💡 假設性 / 監控性發現

### BB-A1：Clone 循環 — Arc drop 順序
**位置**：多處 Arc clone  
**假設**：若某 Pipeline 先 panic，其 Arc 立即 drop 但其他 pipeline 仍持有 clone，resource 未釋放。shutdown timeout 10s 內若無法全部 drop → potential memleak。

**監控**：加 `Arc::strong_count()` 監控（shutdown 時 strong_count > 1 告警）。

### BB-A2：Paper Reconciler 防誤啟
**位置**：`main.rs:1647, 1687`  
**現狀**：`if let Some(client) = shared_client.as_ref()` 確保只有 Demo/Live 啟 reconciler。Paper 無 client → 自動跳過。✅ 已有保護。

**強化**：加顯式 `debug_assert!(!matches!(kind, PipelineKind::Paper))` in `run_position_reconciler()` 防禦未來 regression。

### BB-A3：Private WS 重連 REST 洪水
**位置**：`spawn_private_ws_supervisor()` 重連時 WS auth 經 REST  
**假設**：Live 重連洪水可能擋住 Demo REST 查詢（reconciler polling、fee refresh、scanner）。

**監控**：D14 shared rate limiter 是否真共享？或 Demo/Live 各自獨立 limiter？需 code review + 負載測試。

---

## 7. D1-D26 完整實施狀態矩陣

| D項 | 計劃要求 | 實施狀態 | 證據 / 缺口 | blocker 引用 |
|-----|---------|---------|-----------|-------------|
| D1 | 條件式啟動 | ⚠️ 錯誤實施 | `primary_kind` 決定 vs 獨立判斷 | MEGA-BLOCKER-0 |
| D2 | API key 衝突 409 | ✅ logic + ❌ timing | settings_routes.py:391 `==` | BLOCKER-5 |
| D3 | GovernanceProfile 分層 | ✅ | `tick_pipeline.rs:129-135` 硬編碼 | — |
| D4 | 策略角色分層 | ❌ 配置未創建 | StrategyFactory 有，TOML 無 | BLOCKER-8 |
| D5 | 性能指標隔離 | ⚠️ 部分 | Rust engine_mode ✅, Python metrics 未驗證 | — |
| D6 | 三級遞減收縮 | ❌ 完全未實施 | 無 cross_engine_notify | BLOCKER-2 |
| D7 | Paper 初始餘額配置 | ⚠️ 部分 | GUI 端點 ✅, TOML ❌ | BLOCKER-8 + MAJOR-4 |
| D8 | 策略/管線解耦 | ✅ | StrategyFactory::create_all() | — |
| D9 | JS Edge per-engine 隔離 | ⚠️ 部分 | per-engine load ✅, 文件仍共享 | — |
| D10 | Fan-out bounded channel | ✅ | Paper 1024 / Live 512 + Arc<PriceEvent> | — |
| D11 | 阻塞式初始化 | ⚠️ 未驗證 | 無 barrier，有啟動競態風險 | MAJOR-2 |
| D12 | RwLock 類型統一 | ⚠️ 漏遷 | 5 處 std::sync::RwLock 殘留 | BLOCKER-6 |
| D13 | 回滾安全策略 | ⚠️ 需重做 | deprecated 保留的前提被 MEGA-0 推翻 | — |
| D14 | REST Rate Limiter 共享 | ✅ | 單 rest_client 實例 | — |
| D15 | 全局資本敞口上限 | ❌ 未實施 | grep 零結果 | BLOCKER-3 |
| D16 | Paper P0 硬限不可關 | ⚠️ 配置缺 | risk_config_paper.toml 未創建 | BLOCKER-8 |
| D17 | Live 獨立 runtime | ❌ 未實施 | 三管線共享 runtime | BLOCKER-4 |
| D18 | 單一寫入口 per-account | ✅ | 各 pipeline 獨立 BybitRestClient | — |
| D19 | DB 去重寫入 | ❌ 未實施 | market_tx 三管線都傳 | BLOCKER-1 |
| D20 | Arc<WsEvent> fan-out | ✅ | Arc<PriceEvent> 實施 | — |
| D21 | Private WS per-engine | ✅ | `spawn_private_ws_supervisor()` × 2 | — |
| D22 | PipelineCommand rename | ✅ | 全量 rename（2 處漏網）| MINOR-2 |
| D23 | Reconciler per-engine | ✅ | Demo/Live 各 spawn 獨立實例 | — |
| D24 | StopManager REST 綁定 | ✅ code + ❌ test | 綁定實施無測試 | MAJOR-6 |
| D25 | DB pool ≥ 20 | ✅ | `default_pool_max() = 20` | — |
| D26 | GovernanceCore 多實例 | ✅ | 無 static/OnceCell | — |

**實施完成度**：
- ✅ 完整：11 項（D3/D8/D10/D14/D18/D20/D21/D22/D23/D25/D26）
- ⚠️ 部分/需改進：8 項（D1/D5/D9/D11/D12/D13/D16/D24）
- ❌ 未實施：7 項（D2 timing/D4/D6/D7/D15/D17/D19）

---

## 8. 現實可用性評估

### 8.1 當前跑不跑得動？
**答**：跑得動，但不是三引擎並行。現在的運行形態 = 「Primary Pipeline（Demo 或 Live 二選一）+ Paper alongside」，兩個 Pipeline 共享 runtime，Paper 寫 market_data + 主管線也寫 market_data（重複），shutdown 無序，失敗隔離機制 90% 缺失。

### 8.2 能進真實 Live 嗎？
**不能**。在當前狀態進 Live 會面臨：
- 任何一個 Pipeline panic 其他無感知（BLOCKER-2）
- Paper 高頻可能搶 Live CPU 導致延遲失控（BLOCKER-4）
- 全局敞口無上限，極端情況 2-3× 資金池曝險（BLOCKER-3）
- shutdown 不保證 Live fills 先 flush（MAJOR-3）
- API key 衝突檢查可被 timing attack 繞過（BLOCKER-5）
- settings API 競態可繞過 D2 衝突檢查（BLOCKER-7）

### 8.3 GUI 相連功能銜接狀況
- ✅ sidebar `system_mode` 顯示（console.html 讀 system_mode + active_engines）
- ✅ tab-paper 新增 initial_balance 輸入框（但寫入 TOML 不存在 → BLOCKER-8）
- ✅ tab-live 模式 gate 保留
- ⚠️ tab-live/tab-paper metrics 端點 per-engine 隔離 Rust ✅ Python 部分未驗證（D5）
- ✅ Live Grant/Revoke 按鈕（Phase 4）
- ⚠️ Watchdog multi-snapshot 顯示 ✅ 但測試缺失

### 8.4 API Key 讀取路徑
- ✅ `read_secret_file(slot)` 槽位感知（Phase 1）
- ✅ 3 槽位（Demo / Live-Demo / Live）GUI 卡片
- ⚠️ 衝突偵測 logic ✅ 但 timing attack（BLOCKER-5）+ 競態（BLOCKER-7）
- ⚠️ Live slot key 運行中被改 → 運行態無偵測（只在寫入時檢查，D2 限定）
- ✅ Live Pipeline 啟動前 health check（`get_wallet_balance`）

---

## 9. 修復計劃（基於 2026-04-11 用戶澄清）

### 用戶澄清：目標是三者無條件同時並行，trading_mode 徹底消除

### Phase A — 快速修復（1-2 小時，無架構依賴）
- [ ] BLOCKER-1 D19 DB 去重（main.rs:1824-1825 改 2 行）
- [ ] BLOCKER-5 hmac.compare_digest（settings_routes.py:391）
- [ ] BLOCKER-6 parking_lot 漏遷（types.rs + main.rs 5 處）
- [ ] BLOCKER-7 settings API asyncio.Lock
- [ ] MAJOR-1 snapshot chmod 0600
- [ ] MINOR-2 paper_cmd_rx 改名（main.rs:1858, 1877）

### Phase B — 配置層補完（半天）
- [ ] BLOCKER-8 創建 4 個 TOML 文件 + `load_strategy_params()` 實現
- [ ] MAJOR-4 Paper balance 優先級函數統一

### Phase C — 三引擎並行重構（2-3 天，MEGA-BLOCKER-0）
- [ ] 3E-10.1 main.rs spawn 重構：刪除 `primary_kind`，三個 Pipeline 獨立判斷啟動
- [ ] 3E-10.2 刪除 `config.trading_mode` 字段 + engine.toml 清理
- [ ] 3E-10.3 Python 側 trading_mode serde 向後兼容殘留清零
- [ ] 3E-10.4 3E-4 完整清除（`TradingMode` enum 真的刪掉，不是 deprecated）
- [ ] 3E-10.5 env var `TRADING_MODE` 清理
- [ ] 3E-10.6 測試調整（reconciler_e2e + event_consumer/tests）

### Phase D — 架構級補完（2-3 天，依賴 Phase C）
- [ ] BLOCKER-2 D6 三級遞減收縮 + catch_unwind + PipelineHealth
- [ ] BLOCKER-3 D15 global_notional_cap
- [ ] BLOCKER-4 D17 Live 獨立 runtime
- [ ] MAJOR-2 啟動競態 barrier
- [ ] MAJOR-3 shutdown 分級順序
- [ ] MAJOR-5 IPC per-engine audit log
- [ ] MAJOR-7 snapshot 版本號

### Phase E — 測試補完（1-2 天，3E-E4 session）
- [ ] BLOCKER-10 ~23 blocker tests（含 MAJOR-6 StopManager 綁定測試）

### Phase F — 文件拆分（2-3 天，獨立 session）
- [ ] BLOCKER-9 拆 tick_pipeline.rs / ipc_server.rs / main.rs / intent_processor.rs / position_reconciler.rs

### Phase G — 重跑 3E-E2 + 3E-E4 驗收
- [ ] 所有 blocker 清零後重跑 9 角色並行審查
- [ ] 更新 TODO.md 標記 3E-E2 / 3E-E4 為 [x]

---

## 10. 審查方法論

**每個 agent 的 grep 命令均為獨立執行**。關鍵驗證：
- `cargo check -p openclaw_engine 2>&1 | tail -40` → pass
- `cargo test -p openclaw_engine --lib 2>&1 | tail -10` → 896 passed
- `grep -rn "trading_mode\|TradingMode" rust/openclaw_engine/src/` → 15+ 處（含 deprecated）
- `grep -rn "trading_mode" program_code/ --include="*.py"` → 8 處（向後兼容）
- `grep -rn "std::sync::RwLock" rust/openclaw_engine/src/` → 5 處
- `grep -rn "parking_lot::RwLock" rust/openclaw_engine/src/` → 3 處（EdgeEstimates ✅ + InstrumentInfoCache ✅ + scanner runner ✅）
- `grep -rn "PipelineKind" rust/openclaw_engine/src/` → 大量使用 ✅
- `grep -rn "GovernanceProfile" rust/` → 54 處使用 ✅
- `grep -rn "cross_engine_notify\|EngineEvent::Crashed" rust/` → **零結果** ❌
- `grep -rn "global_notional_cap" rust/ settings/` → **零結果** ❌
- `grep -rn "new_multi_thread" rust/openclaw_engine/src/main.rs` → 1 處（共享 runtime，非 Live 獨立）
- `grep -rn "StrategyFactory" rust/openclaw_engine/src/` → 8 處 ✅
- `ls settings/paper_config.toml settings/strategy_params_*.toml 2>&1` → **全部 not found** ❌
- `wc -l` 5 個大文件 → 全部超 1200 🛑

---

## 11. 9 角色原始審查摘要

為避免信息丟失，每個 agent 的核心結論已嵌入本報告對應章節。原始審查的關鍵數字：

- **E2**：編譯狀態（實際 pass，報告誤報）+ 5 個大文件超限 + 15+ trading_mode 殘留 + 2 paper_cmd 殘留 + 5 std::sync::RwLock 殘留 + 0 /home/ncyu 硬編碼
- **FA**：實施 ~70%，D3/D8/D10/D18/D20/D21/D23/D26 完整，D6/D15/D17 完全未實施，D5/D9/D25/D2 部分或未驗證
- **PA**：TODO 誠實性 85-90%，D15/D17/D4/D9 TOML/D7 TOML/D24 驗證/D12 徹底性 共 7 項缺
- **QC**：編譯 pass，測試 896/879 (+17)，0 新破測試。5 文件超 1200，5 處 std::sync::RwLock 漏遷
- **BB**：6 高概率 bug（啟動競態 / DB pool starve / Reconciler CB / WS 重連 REST / settings 競態 / IPC 路由無錯誤）+ 3 中 + 2 假設
- **MIT**：D6 完全未實施（無 cross_engine_notify），tokio::spawn 無 catch_unwind，shutdown 無分級順序。Paper Reconciler 誤殺風險 ✅ 已消除（低）
- **E3**：Timing attack 🔴 + 3 設計縫隙（IPC authz / 共用 client / snapshot 權限）。W19 G-3 HMAC 認證仍有效
- **E4**：17/40（43%），缺 ~23 blocker tests
- **E5**：D19 未實施（DB 3× 寫入）、D17 未實施（CPU 爭搶）、D12 漏遷（latency）；D20/D25/D26 ✅

---

*文件結束 / End of document*
