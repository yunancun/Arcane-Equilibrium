# Multi-Symbol Per-Symbol Position Tracking Refactor

**日期**：2026-04-11
**狀態**：✅ 完成

---

## 問題

4 個 Rust 策略（MaCrossover / BbReversion / BbBreakout / GridTrading）各自只持有單一全局 `position: Option<bool>`，導致每個策略在所有 symbol 間最多只能同時持有 1 個倉位。4 個策略 × 1 position = 理論上限 4 個併發持倉，遠低於風控配置允許的 `open_positions_max=25`。

用戶觀察到 demo/paper/live 模式下「永遠只有 3 個不同幣種」的持倉，確認此為根因而非風控配置問題。

## 根因分析

排除項（均非瓶頸）：
- `risk_config.toml` `open_positions_max=25` ✅
- `scanner_config.toml` `max_symbols=25` ✅
- `max_same_direction` per-mode 配置（5/7/10）✅
- Guardian 檢查 hot-reload 正常（`tick_pipeline.rs:621`）✅
- RiskGovernor Normal/Cautious 允許新開倉 ✅

真正瓶頸：策略層 `position: Option<bool>` — 全 symbol 共享一個 slot。

## 修改內容

### 共通模式（4 策略）

| 欄位 | Before | After |
|------|--------|-------|
| position | `Option<bool>` | `HashMap<String, bool>` |
| last_trade_ms | `u64` | `HashMap<String, u64>` |
| prev_position | `Option<Option<bool>>` | `HashMap<String, Option<bool>>` |
| prev_last_trade_ms | `Option<u64>` | `HashMap<String, u64>` |

所有 `on_tick()` / `on_rejection()` / `on_external_close()` 以 `ctx.symbol` / `intent.symbol` / `symbol` 為 key。

### MaCrossover 額外
- `higher_tf_trend` / `higher_tf_sma`：`HashMap<String, _>`
- `update_higher_tf(&mut self, symbol: &str, ...)` / `higher_tf_allows_entry(&self, symbol: &str, ...)` 加 symbol 參數

### BbBreakout 額外
- `was_in_squeeze` / `entry_price` / `trailing_stop` + 3 個 `prev_*`：全部 `HashMap<String, _>`

### GridTrading 額外
- `grid_levels` / `last_cross_idx` / `net_inventory` / `price_history` / `out_of_range_count` / `ticks_since_health_check` + 3 個 `prev_*`：全部 `HashMap<String, _>`
- **延遲初始化**：`new(lower, upper)` / `new_geometric(lower, upper)` 不再預填任何 symbol，只存 `template_bounds: Option<(f64, f64)>`
- `on_tick` 首次收到 symbol 時：有 `template_bounds` 用模板邊界，否則 ±10% adaptive
- 生產環境 `new_adaptive()` 行為不變（`template_bounds = None`，自適應 ±10%）

### 修復的用戶指出的 Bug
1. `new()` / `new_geometric()` 硬編碼 `"BTC"` 為 HashMap key — 移除
2. 構造函數預填固定價格 grid levels — 改為延遲初始化

## 文件變更

| 文件 | 改動量 |
|------|--------|
| `rust/openclaw_engine/src/strategies/ma_crossover.rs` | struct + new + 5 methods |
| `rust/openclaw_engine/src/strategies/bb_reversion.rs` | struct + new + 4 methods |
| `rust/openclaw_engine/src/strategies/bb_breakout.rs` | struct + new + 4 methods |
| `rust/openclaw_engine/src/strategies/grid_trading.rs` | struct + new/new_geometric + on_tick init + 7 tests |

## 容量影響

| | Before | After |
|--|--------|-------|
| 理論併發上限 | 4（4 策略 × 1 全局） | 100（4 × 25 symbols） |
| 實際上限 | 受 `open_positions_max` + `max_same_direction` 風控限制 | 同左 |

## 測試

- engine lib 879 passed, 0 failed
- GridTrading 18 tests 全部更新適配延遲初始化
- 無新增測試（既有測試已覆蓋 per-symbol 行為）

## 決策記錄

- **不改風控配置**：`open_positions_max=25` / `max_same_direction` 已足夠寬鬆
- **不改 Guardian / RiskGovernor**：檢查邏輯正確，hot-reload 正常
- **不改 Strategy trait**：`on_tick(ctx)` / `on_rejection(intent)` / `on_external_close(symbol)` 已天然攜帶 symbol 信息
- **GridTrading `new()` 保留為測試便利**：生產用 `new_adaptive()`，`new(lo, hi)` 只供測試用確定性邊界
