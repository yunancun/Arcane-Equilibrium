# Session ARCH-RC1 1A + 1B — Pre-Compact Worklog (2026-04-07)

> 接手指引：本 worklog 是 ARCH-RC1 統一 Config 多 session 工程的第 1 + 2 個 session 完成快照。
> 1C 是下一個 session 的接手點，**讀完此檔 + memory/project_arch_rc1_unified_config.md + docs/CLAUDE_CHANGELOG.md 頂部 1A/1B 條目即可無縫續上**。

---

## 1. Session 目標與背景

**起因**：用戶要求啟動 WP-ARCH-RC1（雙風控統一），原以為只有 Python RiskManager + Rust GovernanceCore 兩套。

**真實發現**：盤點 rust/ tree 後發現實際有 **7 套重疊的風控/配置系統**：
1. `program_code/.../risk_manager.py::GlobalRiskConfig`（Python，1633 行，32 檔案使用）
2. `openclaw_core/src/risk/config.rs::RiskManagerConfig`（25 欄位，9 檔案使用）
3. `openclaw_engine/src/config.rs::RuntimeConfig`（含 8 風控欄位 + 5 attention + ml，12 檔案使用）
4. `openclaw_types/src/config.rs::EngineConfig + ParamTemperature`（V3-PA-5 規劃，0 業務 call site，**死**）
5. `openclaw_types/src/risk.rs`（H0GateConfig / GuardianConfig / StopConfig / RiskConfig 4 種，15 檔案使用，**活**）
6. `openclaw_core/src/guardian.rs::GuardianConfig`（max_drawdown_pct / max_same_direction_positions）
7. `openclaw_core/src/h0_gate.rs::H0GateConfig`（max_open_positions）

**用戶決策（永久契約，存進 memory/project_arch_rc1_unified_config.md）**：
- 全部統一為 **3 個熱重載 Config**：RiskConfig / LearningConfig / BudgetConfig
- 加上既有 StrategyParams 系統 = 4 個 IPC 寫入面
- TOML on-disk + JSON IPC，serde 同一 struct
- ArcSwap 熱重載，**禁止 restart-to-apply**
- Python 完全廢掉風控核心，1633 → ~150 行 RiskViewClient（純 IPC 讀）
- AttentionTax 整塊放 BudgetConfig（含 enabled），RiskConfig 完全不持有
- partial_tp 在 RiskConfig.agent（與 take_profit_max_pct 耦合）
- MarketGate 從獨立 Config 沉降為 RiskConfig.market_gate sub-struct（避免 9 欄位撐起獨立 Config 的成本）

**多 session 拆分**：
- **1A**：純清理（砍死代碼）
- **1B**：純加法（建新骨架）
- **1C-1**：危險的 Rust call site 遷移
- **1C-2**：IPC 接通 + JSON→TOML 遷移
- **1C-3**：Python 空殼化
- **1C-4**：Reconciler + News spawn + 驗收 + E2/E4/QA

---

## 2. Session 1A — 死代碼清理（commit `7f59e9b`）

### 範圍
3 個確認為純死代碼的目標：

| 目標 | 驗證方式 | 結論 |
|---|---|---|
| `openclaw_engine::config::MlConfig` (struct + Default + 3 default fns) | grep `kelly_max_fraction\|kelly_min_trades\|kelly_risk_pct\|onnx_model_path\|scorer_enabled\|kelly_enabled` 全 srv/ → 0 業務 call site | 真實 ML 用 `ml::kelly_sizer::KellyConfig` + `Scorer::new(enabled: bool)` 構造參數 |
| `attention_*_ms` 5 欄位 + 5 default fns | grep 全 srv/ → 0 業務 call site | cognitive 系統用 `CognitiveParams::scan_interval_s` 不是 attention intervals |
| `openclaw_types::config::EngineConfig + ParamTemperature` (整檔 187 行) | grep 全 srv/ → 0 代碼引用，僅 2 處設計文檔提及 | V3-PA-5 cold/warm 元資料系統，6 業務欄位全有替代（RuntimeConfig / H0GateConfig / GovernanceMode / CognitiveParams） |

**淨刪除**：~270 行（4 files changed, 25 insertions(+), 289 deletions(-)）

### 驗證
- `cargo build -p openclaw_types -p openclaw_engine` 9.87s 通過，0 新 warning
- `cargo test -p openclaw_engine` lib **624 / integration 36 / 0 fail**
- `cargo test -p openclaw_types` **30 / 0 fail**
- 0 行為改變

---

## 3. Session 1B — ARCH-RC1 統一 Config 骨架（commit `0523f17`）

### 新建檔案 4 個 + 1 個重命名

```
rust/openclaw_engine/src/config/
├── mod.rs                  (was config.rs, git mv)
├── store.rs                (NEW, 305 行 / 7 tests)
├── risk_config.rs          (NEW, 1014 行 / 24 tests)
├── learning_config.rs      (NEW, 414 行 / 13 tests)
└── budget_config.rs        (NEW, 478 行 / 12 tests)
```

### store.rs — 泛型 ConfigStore<T>

```rust
pub struct ConfigStore<T: Clone + Send + Sync + 'static> {
    inner: ArcSwap<T>,
    version: AtomicU64,
    write_lock: Mutex<()>,  // serialises writes only, reads stay lock-free
}
```

關鍵 API：
- `load() -> Arc<T>` 無鎖快照讀（~5ns，tick 熱路徑安全）
- `apply_patch(source, mutate, validate)` mutex 序列化 + all-or-nothing：mutate → validate → 通過才 ArcSwap.store
- `replace(value, source)` 全量替換（用於 startup / migration）
- `PatchSource` enum：Operator / Agent / Migration / Startup（審計用）

7 unit tests 含 **10 thread × increment race 測試**（必須最終 +10，version 必須 10）。

### risk_config.rs — 13 sub-struct

```rust
pub struct RiskConfig {
    pub meta: Meta,
    pub limits: GlobalLimits,             // P1 ~26 欄位
    pub overrides: CategoryOverrides,     // P0 spot/linear/inverse/option
    pub per_strategy: HashMap<String, StrategyOverride>,
    pub agent: AgentParams,               // P2 含 partial_tp_*
    pub cascade: CascadeThresholds,       // RiskGovernor 6 級
    pub regime: RegimeMultipliers,        // 5 regime × 3 mult，從 hardcode 提升
    pub cost_gate: CostGate,
    pub dynamic_stop: DynamicStop,
    pub market_gate: MarketGate,          // 收編原 MarketConfig 9 欄位
    pub anti_cluster: AntiCluster,
    pub correlation: Correlation,
    pub runtime: RuntimeKnobs,
    pub experimental: Experimental,
}
```

關鍵特性：
- **GlobalLimits 26 欄位**：含新搬入的 `min_order_notional_usdt` / `max_order_notional_usdt` / `min_balance_usdt`（從 MarketConfig 移過來，跟 position_size_max_pct 同 Config 避免跨 Config 衝突）
- **跨 sub-struct invariant**：`partial_tp_levels` 各層 ≤ `take_profit_max_pct`；`min_order_notional ≤ max_order_notional`
- **per_strategy 一鍵暫停**：`enabled: bool` 預設 true（手動 impl Default 因為 derive 會給 false）
- **MarketGate 收編**：funding_rate_max_abs / liquidation_buffer_pct / spread_max_bps / slippage_max_bps / ob_depth / volume / fee / rate_limit 9 欄位全部成為 RiskConfig sub-struct
- **RegimeMultipliers 從 hardcode 提升**：5 regime × {stop, tp, time} = 15 個值現在可配置，預設值鎖死 trending/volatile/ranging/squeeze/unknown 現值
- **validate() 對每個 sub-struct 套用嚴格約束**：cascade tier 嚴格遞增、regime mult > 0、margin_mode ∈ {isolated,cross}、position_mode ∈ {one_way,hedge} 等

24 unit tests：default 對齊 Python legacy / 12 種驗證失敗 / partial_tp 邊界 / per_strategy 暫停 / TOML+JSON round-trip / partial TOML 預設保留 / regime lookups。

### learning_config.rs — 5 sub-struct

```rust
pub struct LearningConfig {
    pub meta: Meta,
    pub switches: MlSwitches,    // 6 個 ML/RL 開關
    pub linucb: LinUcbParams,
    pub thompson: ThompsonParams,
    pub agent: AgentBehavior,    // entry_confidence / kelly / regime_whitelist 等
    pub experimental: Experimental,
}
```

**Phase 4.1 default-off 契約收編**：`switches.teacher_loop_enabled = false`（既有 IPC `set_teacher_loop_enabled` 端點 1C 改讀此欄位）。

AgentBehavior **不含 partial_tp**（搬到 RiskConfig.agent）。包含：entry_confidence_min / min_edge_bps / kelly_fraction / max_positions_per_strategy / max_positions_per_symbol / breakeven_trigger_pct / regime_whitelist / order_type_preference / entry_split_chunks。

13 unit tests 含 Phase 4.1 default-off 契約測試。

### budget_config.rs — 5 sub-struct

```rust
pub struct BudgetConfig {
    pub meta: Meta,
    pub caps: BudgetCaps,           // daily/monthly + per_scope_caps
    pub model_costs: ModelCosts,
    pub attention_tax: AttentionTax, // FULLY here, including enabled
    pub experimental: Experimental,
}
```

**AttentionTax 整塊**（避免跨 Config 校準失同步）：
```rust
pub struct AttentionTax {
    pub enabled: bool,
    pub burn_rate_dormant / low / medium / high: f64,  // 強制非遞減
    pub grade_a / b / c / d_threshold: f64,             // 強制嚴格遞增
    pub cost_edge_max_ratio: f64,
}
```

12 unit tests：enable/disable / 跨欄位驗證失敗 / TOML+JSON round-trip / partial TOML 預設保留。

### 驗證
- `cargo build -p openclaw_engine` 8.41s 通過，0 新 warning
- `cargo test -p openclaw_engine` lib **682 (+58 vs 1A) / integration 36 / 0 fail**
- `cargo test -p openclaw_core` **386 + 8 + 19 / 0 fail**
- `cargo test -p openclaw_types` **30 / 0 fail**
- **0 行為改變**（純加法骨架，舊系統繼續跑，雙軌並存）

---

## 4. 累計成果（1A + 1B）

| 項目 | 1A | 1B | 累計 |
|---|---|---|---|
| Commits | `7f59e9b` | `0523f17` | 2 |
| Lines added | 25 | 2632 | +2657 |
| Lines deleted | 289 | 6 | -295 |
| Net change | -264 | +2626 | +2362 |
| Files | 4 | 6 | 10 |
| New tests | 0 | +58 | +58 |
| Engine lib tests | 624 | 682 | 682 |
| Regression | 0 | 0 | 0 |

---

## 5. Session 1C 接手清單（明天起步）

按執行順序與依賴關係：

### 1C-1: Rust call site 遷移（最危險，先做）
**先讀**：`docs/CLAUDE_CHANGELOG.md` Session 1A+1B 條目 + `memory/project_arch_rc1_unified_config.md`

**動作**：
1. 廢棄 `openclaw_core::risk::config::RiskManagerConfig`（全檔標記 `#[deprecated]`）
2. 9 個檔案改用新 RiskConfig（grep `RiskManagerConfig` 找清單）：
   - `tick_pipeline.rs` / `position_risk_evaluator.rs` / `intent_processor.rs`
   - `claude_teacher/governance_impl.rs` / `event_consumer/setup.rs`
   - `openclaw_core/src/risk/checks.rs` / `mod.rs` / `pipeline_types.rs`
3. RuntimeConfig 風控欄位刪除：max_stop_loss_pct / max_take_profit_pct / max_open_positions / max_total_exposure_pct / max_leverage / max_drawdown_pct / max_same_direction_positions / p1_risk_pct
4. RuntimeConfig → EngineBootstrap 改名（12 檔案 use 路徑更新）
5. GuardianConfig / H0GateConfig 改讀 RiskConfig.cascade 對應欄位（保留 H0GateConfig type 但改成 thin wrapper）
6. 預估 ~50 個 call site 改動，每改 5 個跑一次 cargo build

**驗證關卡**：cargo test -p openclaw_engine 必須 ≥ 682 + 0 fail

### 1C-2: IPC 接通 + JSON→TOML 遷移
1. ipc_server.rs 注入 3 個 ConfigStore handle
2. 6 個新 IPC 端點：update_risk_config / update_learning_config / update_budget_config + 對應 get_*
3. bulk patch handler：mutex 序列化 + 全 sub-struct validate + ArcSwap.store + audit
4. operator_risk_config.json 一次性遷移：讀 → v2 schema → 寫 risk_config.toml → 改名 .legacy
5. sql/migrations/V014__engine_events.sql 新增（startup/shutdown/config_patch/reconcile/crash 統一審計）
6. main.rs Phase 4 構造序列前插入「3-Config Loader + Store 構造」區塊

### 1C-3: Python 空殼化
1. 新建 `risk_view_client.py` ~150 行純 IPC 讀
2. `risk_manager.py` 1633 → 30 行 deprecation shim + RiskViewClient re-export
3. 32 個檔案 import 遷移（13 業務 + 19 測試）：
   - `paper_trading_wiring.py` / `paper_trading_engine.py` / `strategy_wiring.py` / `risk_routes.py` / `portfolio_risk_control.py` / `bridge_stats.py`
4. risk_routes.py GUI 寫端點 → 轉發 update_risk_config IPC

### 1C-4: 收尾
1. 熱重載驗收 e2e test：tick 跑著 → IPC update → 下個 tick 行為改變 → 無 restart
2. Position Reconciler：trading.open_positions 表（V015）+ Bybit get_positions 對帳 + cooldown 從 fills 重建
3. NewsPipeline run_once 60s spawn（順手帶）
4. E2 跨平台/安全/邊界 + E4 全 regression + QA Audit（策略改動強制）
5. CLAUDE.md / TODO.md / KNOWN_ISSUES / README / CLAUDE_CHANGELOG / 新 worklog 同步

### 預估
- 1C-1: ~半天
- 1C-2: ~半天
- 1C-3: ~半天
- 1C-4: ~半天
- 總計：1-2 個工作天

---

## 6. 關鍵決策記錄（不要被未來 session 翻案）

| 決策 | 結論 | 理由 |
|---|---|---|
| Config 數量 | 3 個（Risk/Learning/Budget）+ 既有 StrategyParams | MarketConfig 9 欄位太少不值獨立 Config，沉降為 RiskConfig.market_gate |
| AttentionTax 位置 | 完全在 BudgetConfig，包含 enabled | 避免跨 Config 校準失同步（burn_rate 跟 grade 是同一條曲線兩端） |
| partial_tp 位置 | 在 RiskConfig.agent，不在 LearningConfig | 與 take_profit_max_pct 強耦合，同 Config 內 validate 即可 |
| min_order_notional 位置 | 在 RiskConfig.limits，不在 MarketGate | 與 position_size_max_pct 同維度，避免衝突 |
| funding_rate_max_abs 位置 | 在 RiskConfig.market_gate（唯一持有者） | 從 CategoryOverrides.perp_funding_max 砍掉去重 |
| RegimeMultipliers 是否配置化 | 是，從 hardcode 提升 | operator/agent 該能調市況反應曲線 |
| cold/warm 分類機制 | 不要 HashMap 元資料，用 Config-級分類 | RiskConfig/Learning/Budget 全 warm，EngineBootstrap 全 cold，每個 Config 只有一種溫度 |
| on-disk 格式 | TOML | 支援註解，operator SSH 可讀，Rust 生態標準 |
| IPC payload 格式 | JSON | GUI/Python/Agent 通用 |
| 寫路徑序列化 | 單一 mutex，讀走 ArcSwap 不影響 | 避免並發 patch 競態 |
| bulk patch 原子性 | All-or-nothing，任一欄位驗證失敗整批回退 | 確保 audit 一致 |
| Python 命運 | 完全廢掉，1633 → 150 行 RiskViewClient 純讀 | 用戶明確要求 |

---

## 7. 已固化的記憶（永久契約）

- `feedback_rust_authoritative_config.md`：Rust 為唯一交易參數權威 + 熱重載硬要求
- `project_arch_rc1_unified_config.md`：3-Config 完整契約（命名規範 / 跨 Config 原則 / 擴展性 / Python 命運）

---

## 8. Runtime 狀態

**Live binary 仍是 ARCH-RC1 之前的版本**（`83a9dc7` 或更早），尚未載入 1A/1B 變動。1B 是純加法，新 Config 不接通，舊系統繼續跑，restart 引擎也不會讀取新檔案（call site 還沒遷移）。

**重啟時機**：1C 完成後一次性重啟，載入完整 ARCH-RC1。

---

## 9. 此 session 沒做的事（避免未來 session 重做）

- ❌ 沒動 `openclaw_types::risk.rs`（H0GateConfig / GuardianConfig / RiskConfig 等仍在 15 個檔案使用，留 1C 重新規劃整合）
- ❌ 沒接通新 ConfigStore 到 IPC（留 1C-2）
- ❌ 沒遷移任何 call site（留 1C-1）
- ❌ 沒動 Python（留 1C-3）
- ❌ 沒做 NewsPipeline spawn（順手任務，1C-4）
- ❌ 沒做 Position Reconciler（1C-4）

---

## 10. Compact 後接手三步

1. **讀此 worklog**（你正在讀的這份）
2. **讀 memory**：`project_arch_rc1_unified_config.md` + `feedback_rust_authoritative_config.md`
3. **執行**：跳到 §5 的「1C-1 Rust call site 遷移」開始
