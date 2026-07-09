---
report: E1 — Sprint 1B Pending 3.1 C10 funding harvest Stage 1 Demo · Wave B (B1+B2+B3) IMPL
date: 2026-05-23
author: E1 Backend Developer
phase: Sprint 1B late · Pending 3.1 Wave B
status: IMPL-DONE / 等 E2 審查
upstream:
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_1b_c10_funding_harvest_stage1_demo_dispatch_packet.md (1199 LOC)
files touched:
  new:
    - srv/rust/openclaw_engine/src/strategies/funding_harvest/mod.rs (685 LOC)
    - srv/rust/openclaw_engine/src/strategies/funding_harvest/params.rs (419 LOC)
    - srv/rust/openclaw_engine/src/strategies/funding_harvest/synthetic_spot.rs (299 LOC)
    - srv/rust/openclaw_engine/src/strategies/funding_harvest/tests.rs (488 LOC)
    - srv/rust/openclaw_engine/src/strategies/funding_harvest/tests_synthetic.rs (137 LOC)
  modified:
    - srv/rust/openclaw_engine/src/strategies/mod.rs (+pub mod funding_harvest + re-export)
    - srv/rust/openclaw_engine/src/strategies/params.rs (+StrategyParamsConfig.funding_harvest field + re-export)
    - srv/rust/openclaw_engine/src/strategies/registry.rs (+funding_harvest 構造)
    - srv/rust/openclaw_engine/src/strategies/tests.rs (3 既有 test 同步 5→6 + funding_harvest arm)
    - srv/settings/strategy_params_demo.toml (+[funding_harvest] block)
    - srv/settings/strategy_params_live.toml (+[funding_harvest] block)
    - srv/settings/strategy_params_paper.toml (+[funding_harvest] block)
    - srv/settings/risk_control_rules/risk_config_demo.toml (+[per_strategy.funding_harvest])
    - srv/settings/risk_control_rules/risk_config_live.toml (+[per_strategy.funding_harvest])
    - srv/settings/risk_control_rules/risk_config_paper.toml (+[per_strategy.funding_harvest])
verification:
  - cargo build --release：PASS（28.5s；2 既有 warnings；無新增 error/warn）
  - cargo test --release --lib strategies::funding_harvest：61 PASS / 0 FAIL
  - cargo test --release --lib strategies::（全 strategies module）：518 PASS / 0 FAIL
  - cargo test --release --lib（全 engine lib）：3289 PASS / 0 FAIL / 1 ignored（既有）
---

# E1 IMPL — Sprint 1B Pending 3.1 C10 funding harvest Stage 1 Demo Wave B

## §1 任務摘要

PA dispatch packet §8.2 Wave B 三任務一次性 IMPL：
- **B1** — `strategies/funding_harvest/` 新 module 完整 IMPL（mod.rs + params.rs + synthetic_spot.rs + tests.rs + tests_synthetic.rs）。原 PA spec 拆成 6 file（mod / params / runtime_params / synthetic_spot / tests / tests_synthetic）；實 IMPL 將 IPC runtime_params 邏輯內聯到 mod.rs 內（與既有 funding_arb.rs 範式對齊，後者也是 single-file pattern；bb_breakout 才用 runtime_params.rs 拆分）。
- **B2** — `strategies/mod.rs` + `strategies/params.rs` + `strategies/registry.rs` 三檔接線（pub mod / StrategyParamsConfig field / StrategyFactory 構造）。
- **B3** — 6 TOML 接線：3 個 strategy_params + 3 個 risk_config，per memory `feedback_env_config_independence` 三環境獨立配置（demo / live / paper）。

`funding_harvest` 與既有 `funding_arb` V2（ADR-0018 dormant）並列為新策略 slot，**不動既有 funding_arb 任何 LOC**。預設 `active=false`，Stage 0R replay preflight PASS + operator IPC 顯式 `active=true` 才啟。

## §2 完成回報 4 條

### §2.1 6-file LOC breakdown + funding_harvest module structure

```
srv/rust/openclaw_engine/src/strategies/funding_harvest/
├── mod.rs               685 LOC  — Strategy trait impl + on_tick 三分支 + on_fill/on_close_confirmed/on_external_close/on_close_skipped/import_positions/on_rejection + IPC update_params/get_params/param_ranges + FundingHarvestUpdateParams + helper（annualized_funding / compute_basis_pct / compute_net_edge_bps_per_period / should_enter / should_exit / is_allowed_symbol）
├── params.rs            419 LOC  — FundingHarvestParams（TOML schema + StrategyParams trait impl + Default + validate + param_ranges） + 11 預設常量 + 7 unit test
├── synthetic_spot.rs    299 LOC  — SyntheticSpotLedger（paper-only state machine：open_long / rebalance / close / unrealized_pnl / delta_drift_pct） + 11 unit test
├── tests.rs             488 LOC  — 33 strategy core test：純函數 4 + entry/exit 純函數 9 + on_tick entry 6 + on_tick exit 3 + cross-strategy fence 2 + rejection rollback 1 + IPC tuning 4 + alpha source / conf_scale 2
└── tests_synthetic.rs   137 LOC  — 8 strategy × ledger 整合 test：on_fill 開 / 不同 strategy 忽略 / 0 price/qty fail-closed / on_close_confirmed 清 / on_external_close 清 / on_close_skipped 清 / import_positions 重建 / 他 owner 忽略
                       ─────────
Total                  2028 LOC（PA 估 ~1230 LOC，多出主要在 tests + 完整 validate range）
```

每檔均在 §九 800 行 soft warn 以下（mod.rs 685 < 800）；tests.rs 488 LOC 是雙 file 之一，可容忍。

**funding_harvest vs funding_arb 對比矩陣**（per PA spec §2.3）：
- design：funding_harvest = delta-neutral 雙腿；funding_arb V2 = directional single-leg perp。
- name()："funding_harvest" vs "funding_arb"（互不干擾 owner_strategy）。
- declared_alpha_sources：兩者均 `[FundingSkew, Basis]`（funding_arb dormant 但仍 declare）。
- LeaseScope：不擴 governance 表面，沿用既有 TradeEntry/TradeExit/PositionAdjust。
- OrderIntent：不擴 IntentType，沿用既有 PostOnly limit + maker_timeout_ms。

### §2.2 SyntheticSpotLedger paper-only mechanism + 不發 Bybit order 確認

**核心設計**（synthetic_spot.rs）：
- struct `SyntheticSpotLedger`：state machine `Open / Closed`，欄位 `entry_notional_usd / entry_price / entry_ts_ms / qty / rebalance_count / realized_pnl_usd / close_*`。
- `open_long(notional, spot_price, ts)`：state→Open，qty = notional / spot_price，reset rebalance_count。
- `rebalance(target_notional, spot_price, ts)`：只調 `qty`，**不改 entry_price**（PnL 計算基準保留入場價）；state ≠ Open noop。
- `close(close_price, ts)`：realize PnL = (close - entry) × qty；state→Closed；二次 close noop 回 0。
- `unrealized_pnl_usd(current_spot_price)`：mark-to-market。
- `delta_drift_pct(perp_notional, current_spot_price)`：spot 視角的對沖偏離。

**不發 Bybit order 確認**：
- `synthetic_spot.rs` 整檔 0 `bybit_rest_client::place_order` 引用 / 0 `OrderIntent` 引用 / 0 `IntentProcessor` 引用。
- `mod.rs` 內 `on_fill` 接 perp 腿 real demo fill confirmed 後，**呼叫 `ledger.open_long(perp_notional, fill.fill_price, ts)`**，純內部 mutation。
- 16 root principles 對齊：原則 1（單一寫入口 = IntentProcessor，perp 腿走，spot 腿不繞）/ 原則 4（策略不繞風控 — perp 腿經 Guardian + cost_gate + Kelly sizing；spot 腿不是 trade event 故不必經 governance）。

**Stage 1-3 限制 / Stage 4 升級 path**：
- Stage 1-3 期間 spot 腿 PnL 純 book-keeping，不反映 demo balance。
- Stage 4 LIVE 升級需 Sprint 5+ cascade：spot 腿改 IntentProcessor real spot order（PA spec §11.2），SyntheticSpotLedger retire 為 audit-only shadow。

### §2.3 TOML + registry/mod 接線（funding_arb V2 保留 verify）

**3 個 strategy_params TOML**（per memory `feedback_env_config_independence` 三環境獨立）：

```toml
# settings/strategy_params_demo.toml — 加在 [funding_arb] 之後
[funding_harvest]
active = false              # Stage 0R PASS + operator IPC 顯式 true 才啟
cooldown_ms = 3600000
allowed_symbols = ["BTCUSDT"]
funding_threshold_annualized = 0.05
funding_exit_annualized = 0.02
max_basis_pct = 0.5
entry_basis_ratio = 0.8
max_hold_ms = 259200000
total_cost_bps = 37.0
expected_periods = 3.0
rebalance_check_ms = 7200000
delta_drift_threshold = 0.02
position_cap_usd = 100.0    # Stage 1 hard ceiling
```

- `live` 同 demo 結構但 active=false 永鎖（per ADR-0018 範式 + PA spec §11.2）。
- `paper` 同上 active=false 永鎖（AMD-2026-05-15-01 §2.2 paper 不再做 alpha 樣本）。

**3 個 risk_config TOML**（per_strategy schema 既有欄位接近 PA spec §5.3 意圖）：

```toml
# settings/risk_control_rules/risk_config_demo.toml — 加在 [per_strategy.ma_crossover] 之後
[per_strategy.funding_harvest]
enabled = false              # 雙保險（與 strategy_params_demo.toml active=false 並列）
max_concurrent_positions = 1
stop_loss_max_pct_override = 5.0  # 單筆 perp 腿 5% stop loss（≈ $5 / $100 cap）
```

**注意 PA spec §5.3 落地差異**（per 教訓 3）：PA spec 提的 `max_position_notional_usd / stop_loss_pct / max_positions_per_symbol / cost_gate_min_n_trades_for_block` 不在 `RiskConfig.per_strategy.StrategyOverride` 既有 schema 內，會被 toml deserialize 默默丟棄。改用：
- `max_position_notional_usd=100` → Rust `FundingHarvestParams.position_cap_usd` 內部 validate hard ceiling ≤ 100.0（無法 IPC 繞）。
- `stop_loss_pct=0.05` → `stop_loss_max_pct_override=5.0`（StrategyOverride schema 既有欄位）。
- `max_positions_per_symbol=1` → `max_concurrent_positions=1`（schema 既有）。
- `cost_gate_min_n_trades_for_block` 是全局 `[slippage]` 欄位，非 per_strategy；不接。

**registry / mod 接線**：
- `strategies/mod.rs`：`pub mod funding_harvest;` + `pub use params::{... FundingHarvestParams ...}`
- `strategies/params.rs`：`pub use super::funding_harvest::FundingHarvestParams;` + `StrategyParamsConfig.funding_harvest: FundingHarvestParams`
- `strategies/registry.rs`：`use super::{... funding_harvest ...}` + 在既有 5 策略構造之後加 funding_harvest 完整接線（13 個 field copy from `p.funding_harvest` + `set_active`）。

**funding_arb V2 保留 verify**：
- `strategies/funding_arb.rs` **0 LOC 改動**（grep diff 確認）。
- `strategy_params_demo.toml` 既有 `[funding_arb] active=false` 保留不動，**新加 `[funding_harvest]`** block 在其後（顯式分離 strategy slot）。
- 兩策略 `declared_alpha_sources` 均 `[FundingSkew, Basis]` — 是設計選擇（funding_harvest 也消費 funding skew + basis）；alpha_source dispatch metric 會分 strategy name 累積。

### §2.4 cargo build + test 結果 + E2 重點 3 條

**Verification**（Mac dev box，per memory `project_dev_runtime_split` Linux 才是 runtime authority；Mac build/test 是 IMPL 驗證關卡）：

```
cd /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine
source ~/.cargo/env

# Build
cargo build --release
# → Finished `release` profile [optimized] target(s) in 28.91s
# → 2 既有 warnings（btc_lead_lag/db_writer.rs unused import、ma_crossover/helpers.rs dead_code make_intent）
# → 0 新增 warning / error

# funding_harvest scope
cargo test --release --lib strategies::funding_harvest
# → test result: ok. 61 passed; 0 failed; 0 ignored; 0 measured; 3229 filtered out

# Full strategies module（含修補的 3 個既有 hardcoded `len()==5` test）
cargo test --release --lib strategies::
# → test result: ok. 518 passed; 0 failed; 0 ignored; 0 measured; 2772 filtered out

# Full lib regression
cargo test --release --lib
# → test result: ok. 3289 passed; 0 failed; 1 ignored; 0 measured; 0 filtered out
```

**E2 重點 3 條**（per dispatch packet §10 + 我 IMPL 期間發現的 spec ↔ codebase 差異）：

#### E2 重點 1 — Delta-neutral 數學正確性 + 既有 funding_arb 對比

- `compute_basis_pct(perp_price, index_price)` 使用 `(perp / index − 1).abs() × 100`，與 funding_arb `compute_basis_pct` **完全鏡像**（差異：PA spec §1.2 寫 `spot_price` 變量名，但實際 ctx 提供的是 `index_price`（OC-5 Bybit V5 spot oracle 近似 spot price），funding_arb 範式一致使用 index_price）。E2 必驗：
  - `index_price` 缺失 / ≤ 0 時回 `f64::MAX` → on_tick should_enter / should_exit 必跳過（fail-closed）。
  - 與 funding_arb.rs:88-94 對齊。
- `annualized_funding(f) = f × 3.0 × 365.0` — Bybit V5 funding cycle 為 8h × 3 / day × 365。E2 必驗 Bybit V5 reference doc `docs/references/2026-04-04--bybit_api_reference.md` funding cycle 是 8h（per PA §10.1 BB cross-check）。
- `compute_net_edge_bps_per_period(f) = f.abs() × 10000 - cost_bps / expected_periods`。**注意 funding_harvest only enter when `f > 0`** (design choice per `should_enter` 內 `funding_rate_8h > 0.0` filter)，所以 abs 等同於 f；但 should_exit 用 abs/直 f 兩種視角（funding decay / 反向 trigger）。
- `delta_drift_pct(perp_notional, current_spot_price)` 用 spot notional 分母（spot 視角）— 與 PA §10.1 #4 一致。

#### E2 重點 2 — SyntheticSpotLedger 邊界 + 不繞 governance

- grep `bybit_rest_client::place_order` / `IntentProcessor` / `OrderIntent` 在 `funding_harvest/synthetic_spot.rs` = 0 hit ✓（已驗）。
- mod.rs `on_fill` 在 perp fill confirmed 才開 ledger（fail-safe 同步點）；`on_close_confirmed` / `on_external_close` / `on_close_skipped` 都會清 ledger（無 orphan ledger 累積）。
- **PA spec §3.3 預設 `FillResult` 有 `is_synthetic_spot / parent_perp_fill_id / fill_ts_ms / side` 欄位 — 實際 `openclaw_core::execution::FillResult` 只有 5 個 field**：`fill_price / fill_qty / fee / slippage_bps / is_taker`。**本 IMPL 不擴 FillResult schema**（任務禁忌 / 影響其他策略 / paper_state / event consumer）。改用：
  - `on_fill` ts_ms 從 `self.cooldown.last_ms(sym)` 取（fill 同 tick 已 record_signal）。
  - synthetic spot fill **不寫** `trading.fills.track`（避 ML 訓練集 mis-label；Stage 0R replay harness 從另一條 path 算 PnL）。
  - `parent_perp_fill_id` cross-leg 隱含在 `synthetic_spot: HashMap<symbol, ledger>` 與 paper_state `owner_strategy + symbol` 的 join。
- E2 必驗：`SyntheticSpotLedger.close()` 簽名是 `close(close_price, ts_ms) -> f64`（PnL）；PA §10.2 #4「用 current spot price，**not entry price**」— **本 IMPL 在 `on_close_confirmed` 用 `entry_price` 作 fallback**（因為 trait `on_close_confirmed(&mut self, symbol: &str)` 沒 close_price 參數）。這是接受的妥協：Stage 1-3 期間 synthetic spot PnL 主要供 ledger book-keeping，Stage 0R replay harness 以歷史 spot price 重算 PnL 更精確。Trade-off：本 Wave 不擴 Strategy trait `on_close_confirmed` 簽名（影響 5 既有策略；超範圍）。
- E2 必驗：`import_positions` 從 paper_state 重建 ledger 用 `entry_price` + `entry_ts_ms`（重啟時無 live spot tick），first rebalance check 才以真實 spot price 修正。

#### E2 重點 3 — 16 root principles + AMD-2026-05-15-01 §4.4 rollback

- **原則 1（單一寫入口）**：grep `place_order` outside IntentProcessor 在 funding_harvest module = 0。perp 腿走 `StrategyAction::Open(OrderIntent)` → step_4_5_dispatch → IntentProcessor → bybit_rest_client。
- **原則 4（策略不繞風控）**：perp 腿 `is_long=false / order_type="limit" / time_in_force=Some(PostOnly) / maker_timeout_ms=Some(45000)` 完整經過 Guardian + cost_gate + Kelly sizing。
- **原則 5（生存 > 利潤）**：`stop_loss_max_pct_override=5.0` 在 risk_config_demo.toml；perp 腿觸 stop_loss → `on_external_close` 清 synthetic spot ledger。
- **原則 8（交易可解釋）**：tracing::info! 記錄 entry / fill / rebalance / close（含 funding_rate / basis_pct / qty / pnl）。audit 可重建。
- **AMD-2026-05-15-01 §4.3 Stage 1 demo evidence 6 條**：perp 腿走完整 demo path → fill lineage + Decision Lease lineage + Guardian verdict + ExecutionReport 全經過（同 grid_trading / ma_crossover）。
- **AMD §4.4 rollback**：本 IMPL 不接 `[55]` fill-lineage invariant 監測 / `[58]` canary invariant 監測 / SM-04 L3 escalate hook — 這些由 governance layer 統一處理（funding_harvest set_active(false) 即可）；strategy 層不重複實作。
- **原則 6（保守默認）**：`active=false` 預設、`position_cap_usd=100` hard ceiling、`allowed_symbols=["BTCUSDT"]` Stage 1 限定、`compute_basis_pct` 缺 index_price fail-closed、`compute_post_only_price` 缺 BBO fail-closed skip entry。

## §3 治理對照

- **§四 硬邊界**：
  - max_retries = 0 不可改 — 未觸碰 ✓
  - live_execution_allowed / execution_authority / system_mode — 未觸碰 ✓
  - strategy_params_live.toml `[funding_harvest].active=false` 永鎖 ✓
  - risk_config_*.toml `[per_strategy.funding_harvest].enabled=false` 三環境統一 ✓

- **§七 Code rules**：
  - 新檔 mod.rs / params.rs / synthetic_spot.rs 均有 MODULE_NOTE ✓
  - 注釋默認中文（new code Chinese-first per `feedback_chinese_only_comments`）✓
  - 既有 funding_arb.rs / strategies/mod.rs / params.rs / registry.rs 觸碰範圍最小（registry +20 LOC、mod.rs +3 LOC、params.rs +5 LOC、tests.rs 改 3 既有 test 同步 5→6） ✓
  - 文件行數：mod.rs 685 < 800 soft warn；params.rs 419 < 800；synthetic_spot.rs 299 < 800 ✓

- **§九 Code structure guardrails**：
  - 不新增 mutable singleton ✓
  - 不新增 LeaseScope / IntentType / lease_type（不擴 governance 表面）✓
  - Route handler parse/call/format pattern 不適用（strategy module）

- **AMD-2026-05-15-01 §4**：
  - Stage 1 Demo 限定 BTCUSDT + size cap $100 absolute ✓
  - active=false fail-closed 預設 ✓
  - synthetic spot leg paper-only 不污染 mainnet posture ✓

- **per memory `feedback_env_config_independence`**：
  - 三 strategy_params TOML 獨立 active=false ✓
  - 三 risk_config TOML 獨立 [per_strategy.funding_harvest] ✓
  - 參數值對齊（同 demo）但 active/enabled 三環境統一 false（與 funding_arb 範式一致）✓

## §4 不確定之處

### §4.1 close_price fallback 用 entry_price 的妥協

`on_close_confirmed(&mut self, symbol: &str)` 沒 close_price 參數，本 IMPL 在 synthetic spot ledger close 時用 `ledger.entry_price` 作 fallback（PnL = 0）。E2 可能 push back：「Stage 1 Demo 期間真實 spot PnL 不見」。

替代方案考量：
1. 擴 Strategy trait `on_close_confirmed(&mut self, symbol: &str, close_price: f64)` — **超本 Wave 範圍**（影響 5 既有策略）。
2. 在 `on_close_confirmed` 內持有 ctx 引用 — 違反現有 trait 簽名。
3. 在 mod.rs entry/exit 分支內已知 close_price → `on_tick` exit 分支寫入 strategy 內 cache，`on_close_confirmed` 從 cache 取 — 需新增 `pending_close_price: HashMap<Symbol, f64>` 欄位，**可考慮 Round 2 fix**。

**現狀接受**：Stage 0R replay harness（Wave B4，獨立 sub-agent）以歷史 spot price 重算 PnL，更精確。Stage 1-3 期間 synthetic spot PnL 是 book-keeping shadow 而非 real-money 影響。

### §4.2 funding_harvest 不接 `[55]` fill-lineage invariant 監測

PA dispatch §4.2 提「[55] fill-lineage FAIL → strategy demote Stage 0」。本 IMPL **不在 strategy 層內監測 [55] invariant**，原因：
- `[55]` 是 governance 全局 invariant（trading.fills.track attribution_chain_ok %）；策略層沒有對應 hook。
- 違 fail-closed 邏輯在 governance layer（Guardian / cost_gate）處理；策略 set_active(false) 由 IPC 觸發即可。

E2 可能 push back 要求加 `[55]` monitor hook — 屬於 governance 層 sub-task，本 Wave 不接。

### §4.3 FillResult schema 不擴的影響

PA spec §3.3 設計 synthetic_fill 寫 trading.fills.track 並標 `is_synthetic_spot=true` 防 ML mis-label。本 IMPL **完全不寫 trading.fills.track**（synthetic spot 純策略內 ledger）；如未來要寫 attribution chain，需 Sprint 4+ §4.1.1 base table audit 完成 + B5 V### migration 加 `is_synthetic_spot` column。

E2 可能 push back 要求 Sprint 4+ §4.1.1 結論前先決定本策略 attribution path。**現狀接受**：funding_harvest 是 Sprint 5+ cascade 候選；Stage 1 Demo 期間先驗 perp 腿 attribution（既有 path）即可。

### §4.4 `compute_post_only_price` `is_long=false` SHORT 入場路徑驗證

funding_harvest perp 腿是 SHORT；`compute_post_only_price(false, ...)` 走 best_ask + buffer_ticks × tick_size 公式（SELL 限價）。E2 必驗：
- maker_price.rs 對 `is_long=false`（SELL）的 fallback path 與 funding_arb `is_long = !is_positive` 一致。
- 缺 BBO 時 fail-closed skip entry（已測 `on_tick_missing_bbo_skips_entry` PASS）。

## §5 Operator 下一步

1. **PM**：是否接受本 IMPL 範圍 + §4.1-§4.4 不確定之處妥協 → 若 OK → 派 Wave C E2 review。
2. **E2 audit**：per §2.4 三重點 + §4 妥協 + grep `bybit_rest_client::place_order` / `IntentProcessor` 在 funding_harvest 模組 0 hit 驗證。
3. **E4 regression**：cargo test 全 lib（已 3289 PASS）；pytest replay harness（Wave B4 sub-agent 出後並行）；cross-strategy attribution_chain_ok regression。
4. **Wave B4 sub-agent**（並行）：`helper_scripts/canary/replay_funding_harvest.py` 設計與 IMPL（per dispatch packet §6）。
5. **Wave B5（conditional）**：V### migration 加 `is_synthetic_spot BOOLEAN DEFAULT false` + `parent_perp_fill_id TEXT NULL`（per dispatch packet §8.2 B5）— 取決於 PA 諮詢 MIT 結論。
6. **不 commit**：等 E2 verdict → E4 regression PASS → PM 統一 commit。

---

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-23--sprint1b_c10_funding_harvest_module_impl.md`）
