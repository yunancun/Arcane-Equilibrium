# Session ARCH-RC1 1C-1 + 1C-2-A/B/Opt-B/F — Pre-Compact Worklog (2026-04-07)

> 接手指引：本 worklog 是 ARCH-RC1 多 session 工程的第 3 + 4 個 session 完成快照（接續 1A/1B 的
> `docs/worklogs/2026-04-07--session_arch_rc1_1a_1b.md`）。**1C-2-C 是下一個 session 的接手點**。
> 讀完此檔 + `memory/project_arch_rc1_unified_config.md` + CLAUDE.md §三 1C-1/1C-2 條目即可無縫續上。

---

## 1. Session 目標與本 session 真實路徑

**開場目標（user 指示）**：跑完 1C-1 call site 遷移（worklog 1A_1B §5 列的 Batches 1-6）。

**實際跑完的**：
1. **1C-1 Batches 0-6 全部完成**（原計劃 3 個 session，實際 1 個 session 跑完，3 個 commit）
2. **1C-2-A（TOML loader）** + **1C-2-B（pipeline wiring 熱重載 LIVE）**
3. **1C-2 Option B**：抽出 `apply_risk_snapshot()` 單一傳播入口，Guardian 進入熱重載迴圈
4. **1C-2-F 執行引擎收編三連**（F1/F3/F2-downgraded）— 這是 session 中段 operator 追加的新批次，把「Engine 層收編」從 Phase 2 提前合進 ARCH-RC1

**風控並行系統軌跡**：
```
1A 前：7 套（Python RiskManager + core::RiskManagerConfig + engine::RuntimeConfig 風控欄位
            + types::EngineConfig + types::risk::{Guardian/Stop/RiskConfig} + core::guardian
            + core::h0_gate）
1A 後：6（types::EngineConfig purged）
1C-1 B0-4 後：4（core::RiskManagerConfig 物理刪除 + call sites 全改讀 engine::RiskConfig）
1C-1 B5 後：3（RuntimeConfig 風控欄位刪除 + 改名 EngineBootstrap）
1C-1 B6 後：2（types::risk 死代碼清理，只剩 H0 gate runtime infra）
1C-2-F 後：★★★ 1 個 Config 權威 + 5 個執行引擎全部共飲 RiskConfig ★★★
剩：Python RiskManager（1C-3 空殼化）
```

---

## 2. Commits（本 session 11 個，全 pushed）

```
# 1C-1（1A/1B worklog §5 的完整執行）
2007b67  refactor(risk): migrate call sites to unified RiskConfig (ARCH-RC1 1C-1 Batch 0-4)
6768381  refactor(config): rename RuntimeConfig → EngineBootstrap, delete risk fields (Batch 5)
ef30bf1  refactor(types): delete dead duplicate risk config types (Batch 6)
39cab10  docs(arch-rc1): sync CLAUDE/TODO/CHANGELOG for 1C-1 completion

# 1C-2-A/B（TOML loader + pipeline wiring）
581e1e2  feat(config): TOML loader + ConfigStore construction (1C-2-A)
e3014ef  feat(config): thread ConfigStore handles through pipeline — hot reload live (1C-2-B)

# Option B（Guardian hot reload）
8240a25  feat(risk): hot-reload Guardian from RiskConfig + engine merge TODO (Option B)

# 1C-2-F engine 收編
1a7fc8b  feat(risk): RiskGovernorSm reads RiskConfig.cascade (F1 / E-Merge-3)
e7f00d4  feat(risk): H0Gate reads RiskConfig.limits via hot-reload (F3 / E-Merge-2)
91b5db8  feat(risk): hot-reload paper_state.stop_config from RiskConfig (F2 downgraded / E-Merge-1)

# 這個 worklog commit（最後一個）
(pending) docs(arch-rc1): sync CLAUDE/TODO/CHANGELOG + pre-compact worklog
```

**Stats**：+1,307 / −1,325（淨 −18 行）· engine 682 → **714** (+32 tests / +6 config/io) · core 386 → 387 · types 30 → 27 · **0 regression**。

---

## 3. 1C-1 關鍵成果（Batches 0-6）

### Batch 0 — AntiCluster.max_same_direction 欄位校齊
問題：新 `RiskConfig.anti_cluster` 在 1B 只建了 `offset_fraction`，但活體掃描發現 `max_same_direction_positions` 在 `guardian.rs::117` + `ipc_server.rs::830` + `claude_teacher/applier.rs::230` + `risk_routes.py::87` GUI API route + 4 個 test 全活用，不能刪。
修法：加 `max_same_direction: u32` 欄位（default 3）+ range validate `[1, 100]` + 3 tests。

### Batch 1 — openclaw_core/src/risk 瘦身
- 刪 `RiskManagerConfig` struct（229 行 + 4 tests）
- 刪 `checks.rs`（17 tests · check_order_allowed + check_position_on_tick）
- 新 `regime.rs`（36 行 + 3 tests）— 保留**無狀態** regime multiplier fallback 供 `stops.rs` 使用（core 不能依賴 engine，不能讀 RiskConfig.regime）
- 更新 `mod.rs` exports

### Batch 1b — 新建 openclaw_engine/src/risk_checks.rs
新檔 502 行 / 16 tests：
- `check_order_allowed(&RiskConfig)` 讀 `limits.*`
- `check_position_on_tick(cost_edge_max_ratio, &RiskConfig)` — cost_edge 變 primitive 參數（契約明確 BudgetConfig 為權威，caller 從 `BudgetConfig.attention_tax.cost_edge_max_ratio` 取出傳入）
- 所有 15+ 欄位映射到新 sub-struct 路徑（`limits.stop_loss_max_pct` / `agent.trailing_enabled` / `dynamic_stop.base_ratio` / `cost_gate.k_base` 等）

### Batches 2+3+4 — 5 檔案 call site 遷移（單一編譯單元，一起 commit）
- `pipeline_types.rs`: 快照欄位 `risk_manager_config: Option<RiskConfig>`
- `tick_pipeline.rs`: import swap + ADX 閾值 `cost_gate.adx_trending` + `evaluate_positions` 加 `cost_edge_max_ratio` 參數
- `intent_processor.rs`: struct 欄位 + 9 個 patch_* 路徑 + 所有 cost_gate k_* 讀取
- `position_risk_evaluator.rs`: 簽名 + 5 處測試重映射
- `event_consumer/setup.rs`: Guardian + IntentProcessor 改用 `RiskConfig::default()` 種子（1C-2-B 改接 ConfigStore）
- `event_consumer/tests.rs`: 8 個 field-path assertion 重寫

### Batch 5 — RuntimeConfig → EngineBootstrap
刪 8 個風控欄位（`p1_risk_pct` / `max_stop_loss_pct` / `max_take_profit_pct` / `max_open_positions` / `max_total_exposure_pct` / `max_leverage` / `max_drawdown_pct` / `max_same_direction_positions`），重寫 validate() 只檢啟動欄位（`reconnect_delay` / `heartbeat` / `ipc_socket`），改名 `RuntimeConfig` → `EngineBootstrap`，保留 `#[deprecated] pub type RuntimeConfig = EngineBootstrap` 過渡 1C-2。刪 3 風控 validate tests + 加 2 bootstrap validate tests。

`ipc_server::handle_get_state` 風控顯示欄位改讀 `RiskConfig::default()` placeholder；`rrc1_audit_tests.rs` 斷言改 `rc.limits.stop_loss_max_pct`。

### Batch 6 — types::risk 死代碼清理
`openclaw_types::risk` 裡刪 `GuardianConfig` / `StopConfig` / composite `RiskConfig`（全 0 consumer，live 版本在 `openclaw_core::guardian` + `openclaw_core::stop_manager`）+ 對應 Default + 2 個 serde tests。保留 `H0GateConfig` / `H0GateHealthSnapshot` / `H0GateRiskSnapshot` / `H0CheckResult`（H0 gate 跨 crate 共享 runtime 類型）。刪 `test_stop_config_matches_golden`（core-crate 型別從 types tests 不可達）。lib.rs re-exports 對應精簡。

---

## 4. 1C-2-A/B 關鍵設計

### config/io.rs 新模組
```rust
pub fn load_toml_or_default<T, F>(path: &Path, validate: F) -> Result<T, String>
where
    T: DeserializeOwned + Default,
    F: FnOnce(&T) -> Result<(), String>,
```
- 檔案不存在 → `T::default()` 並跑 validator（捕捉「預設值無效」啟動期退化）
- 檔案存在 → 解析 + validator 兩階段
- 6 tests（missing file / parse existing / invalid TOML errors / validator runs / round trip / mkdir）

`save_toml`：序列化 + atomic rename（temp file → rename），父目錄自動建立。

### main.rs::load_unified_configs
返回 `(Arc<ConfigStore<RiskConfig>>, Arc<ConfigStore<LearningConfig>>, Arc<ConfigStore<BudgetConfig>>)`。
路徑解析優先順序：
1. 個別 env vars：`OPENCLAW_RISK_CONFIG` / `OPENCLAW_LEARNING_CONFIG` / `OPENCLAW_BUDGET_CONFIG`
2. 目錄 env var：`OPENCLAW_RISK_CONFIG_DIR`
3. 預設：`settings/risk_control_rules/{risk,learning,budget}_config.toml`

`async_main()` signature 擴展為：
```rust
async fn async_main(
    config: Arc<ConfigManager>,
    risk_store: Arc<ConfigStore<RiskConfig>>,
    _learning_store: Arc<ConfigStore<LearningConfig>>,
    budget_store: Arc<ConfigStore<BudgetConfig>>,
)
```
`_learning_store` 目前未消費（1C-2-C 起用），用 `_` 前綴避免 warning。

### TickPipeline 新 fields
```rust
risk_store: Option<Arc<ConfigStore<RiskConfig>>>,
budget_store: Option<Arc<ConfigStore<BudgetConfig>>>,
risk_config_version_seen: u64,
```

### 熱路徑機制
```rust
pub fn on_tick(&mut self, event: &PriceEvent) -> Option<CanaryRecord> {
    let tick_start = Instant::now();
    self.sync_risk_config_if_changed();  // ← 1C-2-B 新加
    // ... rest of tick
}

fn sync_risk_config_if_changed(&mut self) {
    if let Some(ref store) = self.risk_store {
        let v = store.version();
        if v != self.risk_config_version_seen {
            let snap = store.load();
            self.apply_risk_snapshot(&snap);
            self.risk_config_version_seen = v;
            tracing::info!(new_version = v, "ARCH-RC1 risk config hot-reloaded (pipeline + guardian)");
        }
    }
}
```
成本：1 次 atomic AtomicU64::load + 1 次 equality 檢查（版本相同直接 return，極低成本）。

`current_cost_edge_max_ratio()` 從 budget_store 每 tick 快照讀（也是 lock-free ArcSwap），取代 1C-1 的硬編碼 0.8 placeholder。

### EventConsumerDeps
新 fields：
```rust
pub risk_store: Option<Arc<ConfigStore<RiskConfig>>>,
pub budget_store: Option<Arc<ConfigStore<BudgetConfig>>>,
```
`run_event_consumer` 解構時拿出來，`wire_pipeline` 之後立即 `pipeline.set_risk_store(...)` / `set_budget_store(...)`。main.rs `EventConsumerDeps` 構造處新增 2 行 `Arc::clone(&risk_store)` / `Arc::clone(&budget_store)`。

---

## 5. 1C-2 Option B + 1C-2-F — apply_risk_snapshot 單一傳播入口

### 演化軌跡
1. **Option B 前**：1C-2-B 只把 `intent_processor.risk_config` 同步了，Guardian owned copy 會 stale drift
2. **Option B 時**：抽出 `apply_risk_snapshot(&snap)` helper，Guardian 進入迴圈（2 步）
3. **F1 後**：RiskGovernorSm 加入（3 步）
4. **F3 後**：H0Gate 加入（4 步）
5. **F2 降級後**：paper_state.stop_config 加入（5 步 — 終局）

### 最終 apply_risk_snapshot 順序
```rust
fn apply_risk_snapshot(&mut self, snap: &crate::config::RiskConfig) {
    // 1. intent_processor.risk_config (Gate 0 + tick check 主引擎)
    self.intent_processor.update_risk_config(snap.clone());

    // 2. Guardian — RMW 保留 modification_* 欄位
    let mut gc = self.intent_processor.guardian_config().clone();
    gc.max_leverage = snap.limits.leverage_max;
    gc.max_drawdown_pct = snap.limits.session_drawdown_max_pct;
    gc.max_same_direction_positions = snap.anti_cluster.max_same_direction as usize;
    self.intent_processor.update_guardian_config(gc);

    // 3. H0Gate — RMW 保留健康欄位 + shadow_mode
    let mut h0 = self.h0_gate.config().clone();
    h0.max_open_positions = snap.limits.open_positions_max;
    h0.max_total_exposure_pct = snap.limits.total_exposure_max_pct;
    h0.allowed_categories = snap.limits.allowed_categories.clone();
    self.h0_gate.update_config(h0);

    // 4. paper_state.stop_config — H0/pause 保護 fallback 引擎
    self.paper_state.set_hard_stop_pct(snap.limits.stop_loss_max_pct);
    if snap.limits.take_profit_enforced {
        self.paper_state.set_take_profit_pct(Some(snap.limits.take_profit_max_pct));
    } else {
        self.paper_state.set_take_profit_pct(None);
    }

    // 5. RiskGovernorSm — 15 欄位 1-to-1 映射 + 命名差異處理
    let c = &snap.cascade;
    self.governance.risk.thresholds = openclaw_core::sm::risk_gov::EscalationThresholds {
        drawdown_cautious_pct: c.drawdown_cautious_pct,
        drawdown_reduced_pct: c.drawdown_reduced_pct,
        drawdown_defensive_pct: c.drawdown_defensive_pct,
        drawdown_circuit_breaker_pct: c.drawdown_circuit_pct,  // 命名差異
        daily_loss_cautious_pct: c.daily_loss_cautious_pct,
        daily_loss_reduced_pct: c.daily_loss_reduced_pct,
        daily_loss_circuit_breaker_pct: c.daily_loss_circuit_pct,  // 命名差異
        consecutive_loss_cautious: c.consec_loss_cautious,  // 命名差異
        consecutive_loss_reduced: c.consec_loss_reduced,
        consecutive_loss_circuit_breaker: c.consec_loss_circuit,
        pressure_cautious: c.pressure_cautious,
        pressure_reduced: c.pressure_reduced,
        pressure_defensive: c.pressure_defensive,
        pressure_circuit_breaker: c.pressure_circuit,  // 命名差異
        min_hold_time_ms: c.min_hold_ms,  // 命名差異
    };
}
```

`set_risk_store` 也呼叫這個 helper 作為 initial seed，保證 seed 和 hot-reload 路徑完全一致。

### F2 降級的 research agent 關鍵發現
Research agent（Explore subagent，後台派發 ~5 分鐘）回報：

1. **StopManager 不是死代碼**：
   - `backtest.rs` 仍需 `compute_atr_position_size`（sizing helper，不是 stop check）
   - `tick_pipeline.rs:910`（H0-blocked）+ `:1017`（paper_paused）是**故意的保護 fallback**，main engine `evaluate_positions` 在這些 early-return 分支下根本不跑
   - 刪掉會讓持倉在 gate-block / pause 時完全沒有止損保護

2. **真正問題**：`paper_state.stop_config` 啟動後永不同步 — 主引擎用新 RiskConfig 值，保護 fallback 用舊 boot defaults，形成**靜默漂移**

3. **新引擎比 StopManager 強**：9 檢查 vs 4 止損類型。新引擎有 dynamic stop / cost edge / session drawdown / consec loss / daily loss，StopManager 都沒有

4. **Trailing stop RR floor 差異**：新引擎有 `pnl_pct >= dyn_stop * trailing_min_rr` 安全 floor，StopManager 沒有。**這是安全增強不是 bug**

**降級決定**：把「殺 StopManager + port 6-7 小時測試」降為「25 行 config 同步」。StopManager 保留作為 (1) backtest sizing utility + (2) H0/pause 保護 fallback 引擎。

---

## 6. 熱重載終局狀態

```
RiskConfig store.version++ (operator IPC patch / Agent directive / startup seed)
      ↓
apply_risk_snapshot(&snap)
  ├─1→ intent_processor.risk_config         主 Gate 0 + tick 9-check 引擎
  ├─2→ intent_processor.guardian            P0 trade intent modify verdict（直接拒 vs downsize qty/leverage）
  ├─3→ h0_gate.config                       健康門控 + 3 個風控欄位（positions/exposure/categories）
  ├─4→ paper_state.stop_config              H0 阻擋 / paper_paused 時的保護 fallback（hard + TP only）
  └─5→ governance.risk.thresholds           6-tier 級聯狀態機（drawdown/daily_loss/consec/pressure 4×4 grid + min_hold）
```

**所有 5 個執行引擎在下一 tick 自動看到新值，tick-level latency，零 restart**。熱重載成本每 tick：1 次 atomic AtomicU64::load + 1 次 equality 檢查；version bump 時才額外 1 次 ArcSwap load_full + 5 步 struct clone。

---

## 7. Session 1C-2-C 接手清單（下一個 session）

**先讀**：
1. 本 worklog（你正在讀的）
2. `memory/project_arch_rc1_unified_config.md`（永久契約）
3. CLAUDE.md §三 1C-2 條目（本 session 新加）
4. `docs/CLAUDE_CHANGELOG.md` 頂部「Session 1C-2-A/B/Opt-B/F」條目

### 1C-2-C 範圍（~半天）
**目標**：6 個 IPC 寫端點讓 operator/Agent 能在運行時 patch RiskConfig，下個 tick 所有 5 個引擎自動刷新。

1. **IpcServer 注入 ConfigStore handles**
   - `IpcServer` struct 加 3 個 `Arc<ConfigStore<T>>` fields
   - `main.rs::async_main` 構造 IpcServer 時傳入 3 個 store clone
   - 估計檔案：`ipc_server.rs`（~1500 行，先 wc -l 確認）+ `main.rs`

2. **6 個新 IPC 端點**
   - `update_risk_config` / `update_learning_config` / `update_budget_config`
     - Params: `{patch: JSON 物件, source: "operator"|"agent"|"migration"}`（source 必填）
     - Flow: 讀當前 snap → 用 patch 覆寫（部分欄位更新）→ call `ConfigStore.apply_patch(source, mutate, validate)`
     - Return: `{ok: bool, new_version: u64, errors: [string]}` (errors 非空即整批 reject)
   - `get_risk_config` / `get_learning_config` / `get_budget_config`
     - 直接 `store.load()` 序列化成 JSON 回傳

3. **Bulk patch all-or-nothing**
   - `ConfigStore.apply_patch` 已實作（1B）：mutex 序列化 + validate → 通過才 ArcSwap.store
   - 呼叫端只需要構造 mutate closure，validate 閉包呼叫 `config.validate()` 即可
   - all-or-nothing 靠 `apply_patch` 的 write_lock + validate 閉包確保

4. **審計**
   - 每個 update_* 成功後寫 audit 一行（1C-2-E 建 V014 表之前先 log::info 記錄）
   - 欄位：`{ts, source, config_name, old_version, new_version, field_paths_changed: [string]}`

5. **測試**（至少 6 個新）
   - 3 個 get round-trip（update → get → assert 欄位值 == patch 值 + version 已增）
   - 3 個 validate 失敗 reject（patch 無效值 → 整批回退，store 版本不變）
   - 1-2 個熱重載 e2e smoke（update 後 sync_risk_config_if_changed 會拉取新值 — 可能需要 mock tick）

**估計工作量**：300-500 行新代碼 + 20-40 tool calls；fresh session 一氣呵成應該足夠。

### 1C-2-D operator_risk_config.json → TOML 一次性遷移
啟動時檢測舊 JSON（`settings/risk_control_rules/operator_risk_config.json` 仍存在，尺寸 3173 bytes，內容已在 session 中看過）：
- 讀 JSON → 映射到新 RiskConfig v2 schema（field rename + sub-struct 重組）
- 呼叫 `save_toml()` 寫 `risk_config.toml`
- 舊 JSON 檔案 rename 為 `.legacy` 保留備份
- 只執行一次：如果 TOML 已存在則跳過
- 映射表需要仔細做（舊 `global_config.max_stop_loss_pct` → 新 `limits.stop_loss_max_pct`，`category_configs` → `overrides` 等）

### 1C-2-E V014 engine_events audit 表
```sql
-- sql/migrations/V014__engine_events.sql
CREATE TABLE IF NOT EXISTS observability.engine_events (
    id BIGSERIAL PRIMARY KEY,
    ts_ms BIGINT NOT NULL,
    event_type TEXT NOT NULL,  -- 'startup' | 'shutdown' | 'config_patch' | 'reconcile' | 'crash'
    source TEXT,  -- 'operator' | 'agent' | 'migration' | 'startup' | 'system'
    config_name TEXT,  -- 'risk' | 'learning' | 'budget' | NULL
    old_version BIGINT,
    new_version BIGINT,
    payload JSONB,  -- field_paths_changed, error messages, reconcile details
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_engine_events_ts ON observability.engine_events(ts_ms DESC);
CREATE INDEX idx_engine_events_type ON observability.engine_events(event_type, ts_ms DESC);
```
然後 ConfigStore 加 audit hook（callback 或 tokio channel），接 trading writer 或新 audit writer。

### 1C-3 Python 空殼化
`risk_manager.py` 1633 → ~150 行 `RiskViewClient`（純 IPC 讀 + 路由轉發）。32 檔案 import 遷移（13 業務 + 19 tests）。`risk_routes.py` GUI 寫操作轉發 IPC。

### 1C-4 收尾
- Position Reconciler（trading.open_positions 表 V015 + Bybit get_positions 對帳 + peak_price 重建）
- NewsPipeline run_once 60s periodic spawn
- 熱重載 e2e test（tick 跑著 → IPC patch → 下個 tick 行為變化 → 無 restart）
- E2 + E4 + QA audit + 文檔同步

### Phase 2 選做
- **E-Merge-4**：Guardian owned `GuardianConfig` struct 退化為 RiskConfig view（純代碼味清理，低優先級，收益有限）

---

## 8. 關鍵決策記錄（不要被未來 session 翻案）

| 決策 | 結論 | 理由 |
|---|---|---|
| Engine 合併是否要「1 個引擎」 | **不追求** | Guardian modify verdict / H0Gate 健康檢查 / RiskGovernorSm 狀態機 hysteresis 是 3 種不同架構範式，強合會讓主引擎變肥胖。「1 個 config + 多個職責清晰引擎」是健康解耦 |
| StopManager 命運 | **保留作為保護 fallback + backtest utility** | research agent 確認它不是死代碼；殺它會讓 H0/pause 時無止損保護 |
| cost_edge_max_ratio 讀取 | **跨 Config 讀**（熱路徑從 BudgetConfig 每 tick 快照） | 契約 line 43+74 明確：BudgetConfig 為權威，執行時跨讀允許，只禁校準耦合 |
| Guardian 如何熱重載 | **RMW**（保留 modification_* 欄位） | modification_* 不在 RiskConfig schema，強制從 snapshot 覆寫會丟失。RMW 是最小侵入 |
| 命名衝突處理（RiskGovernorSm cascade 同步） | **1-to-1 映射含手動名稱轉換** | 不改任何 struct 定義，只在 apply_risk_snapshot 內部做翻譯；保留兩個 struct 的歷史語義 |
| 熱重載粒度 | **tick-level**（sync_risk_config_if_changed 在 on_tick 頂部） | 不想每個 field 讀都走 ArcSwap（熱路徑多次 load）；tick 開始時一次同步到 owned copy，後續 read-only |
| EngineBootstrap deprecated alias | **保留過渡**（`pub type RuntimeConfig = EngineBootstrap`） | 外部 crate（Python PyO3 bindings）可能仍用舊名；1C-3 之後移除 |
| learning_store 當前狀態 | **構造但未消費** | LearningConfig IPC 寫端點在 1C-2-C，不急；用 `_learning_store` 前綴避免 warning |
| 新測試數量 | **+6** (config/io.rs round trip + error paths) | 其他 hot-reload 行為改動不寫新測試，因為只影響熱重載路徑，初始 boot state 不變（RiskConfig defaults = 舊硬編碼） |

---

## 9. Runtime 狀態

**Live binary 仍是 1C-1 之前的版本**（`83a9dc7` 或 `ee6fd00` Phase 4.1），尚未載入 1C-1 或 1C-2 變動。

**重啟時機**：1C-2-C 完成後（或 1C-4 驗收測試前）首次重啟載入完整 ARCH-RC1。
重啟後應看到的 log：
```
loading ARCH-RC1 unified configs / 載入 ARCH-RC1 統一配置
ARCH-RC1 unified configs loaded (risk_version=0 learning_version=0 budget_version=0)
pipeline wired to live RiskConfig ConfigStore / 接入 RiskConfig 熱重載
pipeline wired to live BudgetConfig ConfigStore / 接入 BudgetConfig 熱重載
```
（0 表示 Startup seed，無 patch）

**TOML 檔案狀態**：`settings/risk_control_rules/` 下只有 `operator_risk_config.json`（舊 3173 bytes）+ `README.md`，**沒有** `.toml` 檔案。1C-2-A 的 fail-soft 路徑會讓引擎用 `RiskConfig::default()` / `LearningConfig::default()` / `BudgetConfig::default()` 啟動，這與 1C-1 之前的行為等價（預設值都對齊舊硬編碼）。

1C-2-D 做完後 TOML 會從舊 JSON 遷移產生。

---

## 10. 此 session 沒做的事（避免未來 session 重做）

- ❌ 沒接通 IPC 寫端點（留 1C-2-C）
- ❌ 沒做 JSON → TOML 一次性遷移（留 1C-2-D）
- ❌ 沒建 V014 engine_events 表（留 1C-2-E）
- ❌ 沒動 Python RiskManager（留 1C-3）
- ❌ 沒做 Position Reconciler（留 1C-4）
- ❌ 沒做 NewsPipeline spawn（留 1C-4 順手任務）
- ❌ 沒做熱重載 e2e 驗收測試（留 1C-4）
- ❌ 沒跑 E2 review + E4 regression + QA audit（留 1C-4）
- ❌ 沒做 LearningConfig 的任何消費者接線（1C-2-C 會為 IPC get/update 接線，其他 ML 消費者改讀 LearningConfig 可能是 Phase 2）
- ❌ 沒實作 StopManager 的完整殺法（研究顯示不該殺）
- ❌ 沒做 E-Merge-4（Guardian owned struct 去 struct 化，Phase 2 可選）

---

## 11. Compact 後接手三步

1. **讀此 worklog**（你正在讀的）— `docs/worklogs/2026-04-07--session_arch_rc1_1c1_1c2.md`
2. **讀 memory**：`project_arch_rc1_unified_config.md` + `feedback_rust_authoritative_config.md`
3. **執行**：跳到 §7 的「1C-2-C 範圍」開始

**第一個具體動作**：`wc -l rust/openclaw_engine/src/ipc_server.rs` 確認檔案大小 → 決定是全讀還是先 grep handler dispatch pattern → 實作第一個 IPC 端點 `get_risk_config`（最簡單的 read-only，作為 smoke test）→ 再推 update 路徑。
