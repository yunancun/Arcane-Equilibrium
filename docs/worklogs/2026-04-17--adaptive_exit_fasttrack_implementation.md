---
date: 2026-04-17
status: CODE_COMPLETE · TESTS_GREEN · DEPLOYED
proposal: docs/references/2026-04-17--adaptive_exit_fasttrack_proposal.md
base_commit: 68cfcb2 (pre-change)
---

# Adaptive Exit Persistence + Fast-Track Scoping — Implementation Log
# 自適應出場持續性 + 快速通道範圍化 — 實作日誌

## 1. 範圍（Scope）

實作 `docs/references/2026-04-17--adaptive_exit_fasttrack_proposal.md` 四個變更：

| 代號 | 主題 | 模組 |
|---|---|---|
| A1 | KAMA ER 縮放的 exit persistence | `strategies/ma_crossover.rs` |
| A2 | Trend-adaptive cooldown（移植 grid_trading） | `strategies/ma_crossover.rs` |
| B1 | Symbol-scoped ReduceToHalf（僅觸發 symbol 減半） | `fast_track.rs` · `tick_pipeline/on_tick.rs` |
| B2 | Sigma-proportional cooldown（按觸發 σ 縮放冷卻窗） | `tick_pipeline/on_tick_helpers.rs` · `tick_pipeline/mod.rs` · `tick_pipeline/on_tick.rs` |

## 2. 變更文件清單（Diff Surface）

```
M program_code/settings/experiment_ledger_snapshot.json   (實驗台賬 — 非本次 scope，先前已 dirty)
M rust/openclaw_engine/src/fast_track.rs                  (B1 classifier + 7 tests)
M rust/openclaw_engine/src/strategies/funding_arb.rs      (先前已 dirty — 非本次 scope)
M rust/openclaw_engine/src/strategies/ma_crossover.rs     (A1 + A2 + 13 tests)
M rust/openclaw_engine/src/strategies/mod.rs              (先前已 dirty — 非本次 scope)
M rust/openclaw_engine/src/tick_pipeline/mod.rs           (B2: FtReduceStamp 類型遷移)
M rust/openclaw_engine/src/tick_pipeline/on_tick.rs       (B1+B2 wiring，import 更新)
M rust/openclaw_engine/src/tick_pipeline/on_tick_helpers.rs (B2: FtReduceStamp + sigma_scaled helpers)
M rust/openclaw_engine/src/tick_pipeline/tests.rs         (B2 + 冷卻表 stamp 改造測試，+5 tests)
```

> `funding_arb.rs` / `strategies/mod.rs` / `experiment_ledger_snapshot.json` 為進入本次 session 之前已有的 dirty state，**不屬本次實作範圍**，後續 commit 時若要分拆請先 `git stash` 再分別提交。

## 3. 實作要點（Implementation Summary）

### A1 — ER-scaled exit persistence
- 新增 `MaCrossover::exit_persistence: PersistenceTracker` 欄位（與入場 `persistence` 獨立）。
- 新增 `compute_exit_persistence_ms(er) -> u64 = min_persistence_ms × (1 − ER).clamp(0)`。
- 出場路徑（`on_tick` match arm `Some(is_long)`）：先計算 `reverse_signal: Option<bool>`，再用 `exit_persistence.check(...)` 依 ER 縮放的窗口過濾，僅當 `persisted && reverse_signal.is_some()` 才發 Close。
- `on_external_close(symbol)` 同步 `exit_persistence.clear(symbol)`，避免 stale onset。
- **無新參數**；沿用既有 `min_persistence_ms`（入場側參數）作上限，ER 為滑動縮放因子。

### A2 — Trend-adaptive cooldown
- 新增 `MaCrossoverParams::max_cooldown_boost: f64` 參數，default 3.0，range `[0, 10]`，agent_adjustable=true，db_persisted=true。
- 新增 `MaCrossover::compute_trend_adjusted_cooldown(snap) -> u64`：
  - `adx_range = adx_threshold × 1.5` → upper bound = `adx_threshold × 2.5`（由既有 `adx_threshold` 推導，不新增 `adx_high_threshold`）
  - `adx_factor = clamp((adx − adx_threshold) / adx_range, 0, 1)`
  - `hurst_factor = clamp((hurst − 0.50) / 0.25, 0, 1)`
  - `trend_score = 0.6 × adx_factor + 0.4 × hurst_factor`
  - `multiplier = 1 + trend_score × max_cooldown_boost` → default 下最大 4×
- cooldown gate 改為 `last_ms + effective_cooldown` 動態計算。
- param_ranges count 從 15 → **16**；測試 `test_ma_param_ranges_count` 同步更新。

### B1 — Symbol-scoped ReduceToHalf
- `fast_track.rs` 新增 `is_drop_scoped_reduce(risk_level, held_drop_pct, held_drop_sigma) -> bool` classifier：
  - 僅當 `pct ≥ 5 && σ ≥ 3 && risk < Defensive && pct < 15` 回 true。
  - 15% 閘門鏡射在 classifier 內，與 `evaluate_fast_track` 的順序解耦。
- **未更動** `evaluate_fast_track` 簽名 → 14 個既有測試零回歸。
- `on_tick.rs` 在 ReduceToHalf 分支內以 classifier 結果判斷 `drop_scoped`，`positions` filter 加上 `!drop_scoped || p.symbol == held_drop_symbol`：
  - `drop_scoped=true`（Normal/Cautious/Reduced 上的 5%+3σ）→ 僅觸發 symbol 減半。
  - `drop_scoped=false`（Defensive+、margin crisis、≥15% fall-through）→ 全倉減半（系統性防線不弱化）。
- `tracing::warn!` 追加 `drop_scoped` + `effective_cooldown_ms` 欄位供 log 取證。

### B2 — Sigma-proportional cooldown
- `on_tick_helpers.rs`：
  - 新增常數 `FT_REDUCE_COOLDOWN_MAX_MS: i64 = 600_000`（10× base 硬上限，非 tuning surface）。
  - 新增類型 `pub(crate) type FtReduceStamp = (i64, i64)`，承載 `(halving_ts, effective_cooldown_ms)`。
  - `ft_reduce_cooldown_expired` 改為讀取 stamp 中鎖定的冷卻而非全域常數 → 冷卻快照於**觸發當時**鎖定，不受後續 σ 衰減影響。
  - 新增 `sigma_scaled_reduce_cooldown_ms(σ) -> i64 = base × max(1, σ/3)`，clamp 到 `FT_REDUCE_COOLDOWN_MAX_MS`。
- `tick_pipeline/mod.rs`：`ft_reduced_symbols: HashMap<String, i64>` → `HashMap<String, on_tick_helpers::FtReduceStamp>`。
- `on_tick.rs` 在 ReduceToHalf 分支：
  - `effective_cooldown_ms = if drop_scoped { sigma_scaled_reduce_cooldown_ms(σ) } else { FT_REDUCE_COOLDOWN_MS }`
  - `ft_reduced_symbols.insert(sym, (now_ts, effective_cooldown_ms))`
- `tick_pipeline/tests.rs` 內 4 個 P0-5 相關既有測試同步遷移到 tuple 型 stamp（值沿用 60_000 → 等同舊行為）。

## 4. 測試結果（Test Results）

### 單元測試（Unit Tests）

| Suite | 結果 |
|---|---|
| `openclaw_engine --lib` | **1380 passed / 0 failed** · baseline 1351 + 29（含 25 本次新增 + 4 其他） |
| `openclaw_engine --test reconciler_e2e` | 19 passed / 0 failed |
| `openclaw_engine --test phase4_integration` | 3 passed / 0 failed |
| `openclaw_engine --test rrc1_audit_tests` | 4 passed / 0 failed |
| `openclaw_engine --test stress_integration` | 35 passed / 0 failed |
| `openclaw_core --lib` | 380 passed / 0 failed |

### 本次新增 25 個測試（全綠）

**A1（5）**：`test_a1_exit_persistence_formula` · `test_a1_trending_er_exits_immediately` · `test_a1_choppy_er_delays_exit_until_window_elapses` · `test_a1_reverse_flicker_resets_exit_persistence` · `test_a1_external_close_clears_exit_persistence`

**A2（8）**：`test_a2_cooldown_no_indicators_returns_base` · `test_a2_cooldown_at_threshold_no_boost` · `test_a2_cooldown_strong_trend_4x_at_cap` · `test_a2_cooldown_beyond_upper_bound_clamps` · `test_a2_cooldown_mixed_adx_only_partial_boost` · `test_a2_cooldown_missing_adx_uses_zero` · `test_a2_cooldown_respects_max_cooldown_boost_param` · `test_a2_validate_max_cooldown_boost_bounds`

**B1（7）**：`test_b1_scoped_reduce_normal_outlier_true` · `test_b1_scoped_reduce_cautious_outlier_true` · `test_b1_scoped_reduce_reduced_outlier_true` · `test_b1_scoped_reduce_defensive_or_above_false` · `test_b1_scoped_reduce_extreme_drop_false` · `test_b1_scoped_reduce_below_5pct_false` · `test_b1_classifier_boundary_14_99_pct`

**B2（5）**：`test_b2_sigma_scaled_at_trigger_threshold` · `test_b2_sigma_scaled_linear_above_threshold` · `test_b2_sigma_scaled_clamps_at_max` · `test_b2_sigma_scaled_floors_at_base` · `test_b2_cooldown_expiry_uses_stamped_window_not_base`

### 編譯（`cargo build -p openclaw_engine --lib --tests`）

`Finished dev profile in 6.74s` — 0 errors，3 既有 warnings（`make_intent` unused、`entry_funding_rate` dead、`initial_fee` unused）皆非本次引入。

## 5. 部署狀態（Deployment Status）

- **已部署（DEPLOYED）** — 2026-04-17 20:55 local
- `helper_scripts/restart_all.sh --rebuild` 已執行：`rust/target/release/openclaw-engine` mtime = 20:55。
- 當前運行 PID **1771173**（release binary），取代先前 PID 1364222。
- Release binary 已含新符號（`strings` 驗證）：`max_cooldown_boost` · `sigma_scaled_reduce_cooldown_ms` · `is_drop_scoped_reduce` · `compute_exit_persistence_ms` · `compute_trend_adjusted_cooldown`。
- 部署後 watchdog 狀態：engine_alive=true、snapshot_age≈25s、demo+live 兩 engine 活躍、0 新 ENGINE_CRASH。
- **P0-2 LG-1 21d demo 時鐘**：此次為 code fix intentional restart，時鐘從 20:55 重新起算（非基礎設施事件，按 CLAUDE.md §三 規則計為一次觀察期重置）。

## 6. 行為預期（Expected Behavior Post-Deploy）

| 現象 | 變化 |
|---|---|
| choppy 市場（ER→0）MA 反向假信號 | 不再首 tick 平倉，需撐過 `min_persistence_ms × (1 − ER)` |
| 強趨勢（ADX ≥ 2.5× threshold + Hurst ≥ 0.75）剛平倉就被同趨勢打回 | cooldown 最多放大 4×（default max_cooldown_boost=3） |
| 單 symbol 異常跌（Normal+5%+3σ）觸發 ReduceToHalf | 僅減半該 symbol，其餘倉位保留 |
| 6σ 高嚴重度 ReduceToHalf 後 90 秒內再觸發 | 被冷卻擋下（stamped cooldown=120s，舊行為在 60s 後會放行） |
| Defensive+ / margin crisis / ≥15% drop | **行為不變**，仍執行全倉減半或 CloseAll |

## 7. 風險與回退（Risk & Rollback）

- **風險低**：四個變更都在既有 fail-safe ladder 框架內加過濾層，不擴大攻擊面、不新增寫入口、不觸及 RiskConfig 權威。
- **回退**：`git revert` 本次 commit 即恢復舊行為；所有邏輯皆為純新增/替換，無外部狀態依賴（不寫 DB schema、不引入新 IPC 欄位）。
- **hot-reload**：新增 param `max_cooldown_boost` 會進 ArcSwap → tick-level 熱重載，無需重啟即可調整（部署後生效，GUI/IPC 可直接 patch）。

## 8. 後續建議（Follow-ups）

1. 部署後觀察 `tracing::warn!` 中新增的 `drop_scoped` / `effective_cooldown_ms` 欄位，驗證 B1 在 live/demo 上真的被觸發過 scoped 分支（非僅單測綠）。
2. A2 `max_cooldown_boost` 待納入 EDGE-P2 參數搜尋空間，用 paper/demo 真實數據決定最優值（當前 default=3.0 為保守先驗）。
3. 若部署後發現 choppy 市場 exit 拖延導致小幅超額回撤，考慮 A1 設一個 `exit_persistence_max_ms` 硬上限（目前上限 = `min_persistence_ms`，180s default）。

## 9. 時序（Timeline）

| Step | 內容 |
|---|---|
| 讀 proposal | `docs/references/2026-04-17--adaptive_exit_fasttrack_proposal.md` |
| A1 實作 | `MaCrossover::exit_persistence` 欄位 + `compute_exit_persistence_ms` + on_tick 出場路徑改造 + `on_external_close` 清理 |
| A2 實作 | `max_cooldown_boost` 參數 + `compute_trend_adjusted_cooldown` + cooldown gate 改動態 |
| B1 實作 | `fast_track::is_drop_scoped_reduce` 新增 + `on_tick.rs` ReduceToHalf 分支 filter 改造 |
| B2 實作 | `FtReduceStamp` 類型 + `sigma_scaled_reduce_cooldown_ms` + `ft_reduced_symbols` map 型別遷移 + stamp 讀寫改造 |
| 單測撰寫 | 25 新測試（A1:5 · A2:8 · B1:7 · B2:5）+ 4 既有 P0-5 測試遷移到 tuple stamp |
| 編譯驗證 | `cargo build -p openclaw_engine --lib --tests` → clean |
| 全量測試 | engine lib 1380 / core 380 / reconciler_e2e 19 / phase4 3 / rrc1_audit 4 / stress 35 — 全綠 |
| 部署 | 2026-04-17 20:55 local · `restart_all.sh --rebuild` · PID 1364222 → **1771173**（release binary） |
| 部署後驗證 | watchdog engine_alive=true · snapshot_age≈25s · strings 驗證新符號已烘焙 · 0 新 ENGINE_CRASH |
