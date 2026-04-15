---
name: ARCH-RC1 統一 Config 永久契約 (3-Config + StrategyParams)
description: 風控/學習/預算 3 個 Rust 權威 Config + 既有 StrategyParams，所有 GUI/Agent 寫操作走 IPC，TOML on-disk + JSON IPC，熱重載 ArcSwap，2026-04-07 定稿
type: project
---

**ARCH-RC1 最終契約**：所有交易/風控/學習/預算/市場參數由 Rust 權威持有，分 3 個獨立熱重載 Config + 既有 StrategyParams 系統，共 4 個 IPC 寫入面。Python 完全廢掉風控核心，只剩 IPC 讀取 adapter。

**Why:** 雙系統並存（Python RiskManager 1633 行 + Rust RiskManagerConfig + Rust RiskGovernorSm）導致語義分歧、競態、審計困難、Phase 4.1 directive 路徑無單一真相來源。Operator 2026-04-07 明確要求徹底廢 Python 風控，界線一刀切。

**How to apply:**

## 3 個 Config 邊界

### 1. RiskConfig（純風控決策）
sub-structs:
- `meta` (version, saved_ts_ms)
- `limits` (P1 operator hard ceilings, ~26 欄位含 order_notional / min_balance)
- `overrides` (P0 per-category)
- `per_strategy: HashMap<String, StrategyOverride>` (GUI 一鍵暫停策略)
- `agent` (P2 含 partial_tp_enabled / partial_tp_levels)
- `cascade` (RiskGovernor 6 級閾值)
- `regime` (RegimeMultipliers，5 regime × 3 mult，從 hardcode 提升)
- `cost_gate` / `dynamic_stop` / `anti_cluster` / `correlation`
- `market_gate` (原獨立 MarketConfig 沉降為 sub-struct，9 欄位含 funding/liquidation/spread/slippage/ob/volume/fee/rate_limit)
- `runtime` (boot_cooldown_ms / signals_heartbeat_ms / h0_shadow_mode)
- `experimental` (試驗性 namespace)

### 2. LearningConfig（純 ML/RL/Agent 行為）
- linucb_enabled / linucb_exploration_weight
- thompson_enabled / thompson_floor_trials
- teacher_loop_enabled (Phase 4.1 default-off 收編這裡)
- directive_apply_enabled (kill switch)
- scorer_enabled / news_pipeline_enabled
- agent 行為偏好: entry_confidence_min / min_edge_bps / kelly_fraction / max_positions_per_strategy / max_positions_per_symbol / breakeven_trigger_pct / regime_whitelist / order_type_preference / entry_split_chunks
- **不含 partial_tp**（搬到 Risk）

### 3. BudgetConfig（純 AI 成本）
- daily_usd_max / monthly_usd_max
- per_scope_caps: HashMap (teacher / linucb_explain / news / scorer)
- exhaustion_cooldown_minutes / alert_threshold_pct
- model_costs: HashMap (model_name → input_per_1k_usd, output_per_1k_usd)
- **attention_tax 整塊**（含 enabled / burn_rate_dormant/low/medium/high / grade_a-d_threshold / cost_edge_max_ratio）

## 命名規範

- snake_case，無冗餘前綴
- 上限統一用 `_max` 後綴 (`stop_loss_max_pct`)，閾值用 tier 名後綴 (`drawdown_cautious_pct`)
- 百分比 `_pct`，毫秒 `_ms`，分鐘 `_min`，小時 `_hours`
- bool 用形容詞或 `_enabled` 後綴 (`take_profit_enforced` / `trailing_enabled`)
- 移除歷史包袱 (`p1_risk_pct` → `position_size_max_pct`，`hard_stop_pct` → `stop_loss_max_pct`)

## 持久化與 IPC

- **on-disk: TOML**（支援註解，operator SSH 可讀）
- **IPC payload: JSON**（GUI/Python/Agent 通用）
- 同一個 serde struct，`toml::to_string` / `serde_json::to_string` 互換
- 檔案路徑: `settings/risk_control_rules/{risk,learning,budget}_config.toml`
- 舊 `operator_risk_config.json` 啟動時若存在 → 一次性遷移到 v2 → 改名 `.legacy`

## 熱重載硬要求

- **`Arc<ArcSwap<Config>>`** lock-free 讀（tick 熱路徑零鎖等待）
- IPC `update_*` handler: 驗證 → 構造新 Config → `arc_swap.store(Arc::new(new))` → 寫 TOML 持久化 → 立即返回，下個 tick 生效
- **禁止 restart-to-apply**
- 寫路徑單一 mutex 序列化（避免並發 patch 競態），讀走 ArcSwap 不受影響
- bulk patch **all-or-nothing**: 任一欄位驗證失敗整批回退
- 每個 patch 帶遞增 version + source 欄位 (`operator` / `agent` / `migration` / `startup`)
- 全部進審計表 `observability.engine_events`，bulk patch 寫一筆 batch + N 筆 child rows

## 跨 Config 原則

- **絕對禁止**跨 Config 校準耦合（同一概念的兩個欄位必須在同一個 Config 內）
- 執行時跨 Config 讀取（如 DirectiveApplier 讀 Risk + Budget + Learning）允許，但不能引入校準依賴
- 弱耦合（如 liquidation_buffer ↔ leverage_max）由 GUI 視覺鄰近處理，schema 不切

## 擴展性

- 每個 sub-struct 都有 `Default` + `#[serde(default)]`
- 新欄位走 `meta.version` bump + migration 腳本
- `experimental.*` namespace 用於試驗性欄位，穩定後升級到正式 sub-struct
- **禁止** `extras: HashMap<String, Value>` 黑盒（破壞 Rust authoritative 原則）

## Strategy-specific 邊界

- StrategyParams（Phase 3a 已存在）獨立於 3-Config，管「策略行為」（MA period / RSI threshold 等）
- IPC `update_strategy_params` 已存在，不動
- GUI 上分 4 個 panel: Risk / Learning / Budget / StrategyParams

## Python 命運

- RiskManager (1633 行) 完全廢掉，只剩 ~150 行 RiskViewClient（純 IPC 讀）
- operator_risk_config.json Python 載入路徑刪除
- paper_trading_engine 改用 RiskViewClient 拉狀態
- GUI risk_routes 寫操作改 IPC 轉發
- Python 端 grep `_save_*config` / `json.dump.*config` 結果應為 0
