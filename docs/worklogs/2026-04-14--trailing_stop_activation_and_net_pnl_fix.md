# 2026-04-14 · Trailing Stop Activation Gate + net_realized_pnl Fee Attribution

**Scope**: 修復 GUI 「未实现 PnL 恒正 / 已实现 PnL 恒负」反直覺現象的兩條根因 — Rust 跟蹤止損啟動閘缺失，以及 Python `net_realized_pnl` 誤扣仍開倉的 entry fee。
**Role chain**: PM+FA → E1 inline（主會話）→ E2 sub-agent 審查 → E4 回歸 → PM。parallel sub-agent 僅用於審查（主會話內嵌 write 符合 `feedback_subagent_code_writing_refusal.md` 約束）。
**Outcome**: Rust core 366→**372**（+6）· engine lib 1144→**1146**（+2 IPC 回環）· Python 2446 pass / 1 skip · 0 regression。

---

## 一、事故觸發

### 1.1 用戶觀察
> 「我每次看 GUI 未实现盈亏都是正的，但是已实现盈亏都是负的，我懷疑是 trailing stop 沒有成功攔截收益」

### 1.2 首輪診斷（錯誤假設 → 自我矯正）
第一次 Explore sub-agent 假設為「unrealized GROSS vs realized NET 手續費非對稱」。直接 Read `rust/openclaw_engine/src/paper_state.rs:563-567` 與 `708-712`：

```rust
// L563-567：unrealized 計算
unrealized_pnl: (price - p.entry_price) * p.qty  // 純 gross，無扣費

// L708-712：realized 計算
self.total_realized_pnl += (exit_price - p.entry_price) * close_qty  // 純 gross，無扣費
```

兩欄都是 GROSS，fee 單獨記在 `total_fees`。GUI 兩欄對稱，**「手續費不對稱」假設不成立**。

### 1.3 真正的 Smoking Gun
重新審視 `rust/openclaw_core/src/stop_manager.rs` pre-fix 版本：

```rust
// L152-156（pre-fix）
let is_profitable = pos.best_price > pos.entry_price;
if !is_profitable { return None; }
// L162-166（pre-fix）
let trail_price = pos.best_price * (1.0 - trail_pct / 100.0);
```

**致命缺陷**：啟動閘門只要 `best_price > entry_price`（高出 $0.01 就算），但 `trail_price` 可以遠低於 entry。

**數值示範**（long 倉 entry=$100，trailing_stop_pct=2%）：
- 價格上衝 $100.10 → best_price 更新 → 閘門過（100.10 > 100）
- `trail_price = 100.10 × 0.98 = $98.10`（比 entry 低 $1.90）
- 回撤到 $98 → trailing stop 觸發 → **鎖定虧損 $2/qty**

這不是 trailing stop，是「價格碰過 entry 然後回撤就砍倉」的軟版 hard stop。

### 1.4 為何形成 unrealized⁺ / realized⁻ 模式
策略無百分比止盈（`on_tick.rs` 所有 `StrategyAction::Close` 觸發點皆為信號翻轉，非「賺到 X% 就走」）。生存者偏誤 × trailing-at-loss 雙重作用：
1. 贏家留著 → 信號持續利多 → 持續貢獻正 unrealized
2. 每個小上衝後回撤 → trailing stop 在虧損位砍 → 負 realized
3. 明確輸家 → hard stop (5%) 砍 → 負 realized
→ 數學必然：unrealized 正 / realized 負。

---

## 二、修復設計（兩選一 → B）

### 2.1 候選方案
| | A · break-even guard | B · 教科書分離啟動閾值 |
|--|--|--|
| 改動點 | 僅在 `trail_price` 端加 `max(entry)` | 新增 `trailing_activation_pct` 字段 |
| 語意 | 「永不鎖損」但無真實利潤門檻 | 「到達 X% 利潤才啟動，之後回撤 Y% 出場」 |
| 可調性 | 無旋鈕（寫死） | 操盤者可按策略調 activation/trail 比例 |
| 風險 | 閘門一過就貼身跟，仍不是真鎖利 | 向後兼容需 `#[serde(default)]` |

**選 B**（教科書做法）。默認 `activation_pct = trail_pct`：`best_price ≥ entry × (1 + trail_pct/100)` 才啟動 → 保證 `trail_price ≥ entry × (1 + trail_pct/100) × (1 − trail_pct/100) = entry × (1 − trail_pct²/10000)`，最壞 lock-in ~ trail² of entry（2% 時約 0.04%，可忽略）。operator 設 `activation > trail_pct` 得到嚴格鎖利。

### 2.2 net_realized_pnl 附帶 bug
```python
# paper_trading_routes.py (pre-fix L469)
net_realized_pnl = realized - fees  # 把仍開倉的 entry fee 算進 realized
```
修復：`closed_fees = max(0, total_fees - open_entry_fees)` → `net = realized - closed_fees`。這個 bug 讓 net_realized 顯示比實際更負，放大「realized 恒負」的視覺印象。

### 2.3 Structured Logging
Trailing stop 觸發時加 `tracing::info!(event="trailing_stop_triggered", …)`，可以 `grep event=trailing_stop_triggered` 量化 winner/loser 分佈，未來有數據後驗證 Fix B 成效。

---

## 三、實施清單

### 3.1 Rust core（`openclaw_core/src/stop_manager.rs`）
- `StopConfig` 新增 `trailing_activation_pct: Option<f64>`，`#[serde(default)]` 向後兼容既存 TOML/JSON 快照。
- `check_trailing_stop()` 重寫（154-213）：
  ```rust
  let trail_pct = config.trailing_stop_pct?;
  let activation_pct = config.trailing_activation_pct.unwrap_or(trail_pct);
  let activation_price = if pos.is_long {
      pos.entry_price * (1.0 + activation_pct / 100.0)
  } else {
      pos.entry_price * (1.0 - activation_pct / 100.0)
  };
  let activated = if pos.is_long { pos.best_price >= activation_price }
                  else { pos.best_price <= activation_price };
  if !activated { return None; }
  // ... trail_price 計算同前 ...
  if triggered {
      tracing::info!(
          event = "trailing_stop_triggered",
          is_long, entry_price, best_price,
          trigger_price = price, trail_price,
          activation_pct, trail_pct, pnl_pct_approx,
          entry_ts_ms,
          "trailing stop triggered / 跟蹤止損觸發"
      );
      // ...
  }
  ```

### 3.2 Rust 接線（IPC → 熱重載）
| 檔案 | 改動 |
|--|--|
| `paper_state.rs` | `set_trailing_activation_pct(Option<f64>)` + `clamp(0.0, 50.0)` |
| `tick_pipeline/mod.rs` | `PipelineCommand::UpdateRiskConfig { trailing_activation_pct: Option<Option<f64>>, .. }` |
| `event_consumer/handlers.rs` | destructure + `v.clamp(0.0, 0.5)` + info log |
| `ipc_server/handlers.rs` | `parse_opt_opt_f64(params, "trailing_activation_pct")` + `has_any` |
| `event_consumer/tests.rs` | 3 個既存測試的 struct literal 補 `trailing_activation_pct: None` |

### 3.3 Rust 單元測試（`stop_manager.rs`）
| 測試 | 驗證 |
|--|--|
| `test_trailing_stop_below_activation_skip_long` | long 倉 best 未達 activation → 不觸發 |
| `test_trailing_stop_below_activation_skip_short` | short 側同上 |
| `test_trailing_stop_explicit_activation_threshold` | activation=5% trail=2%，+4% best 跳過，+5% best 觸發 |
| `test_trailing_with_higher_activation_locks_profit` | activation=3% trail=2% 的 long 鎖利驗證 |
| `test_trailing_activation_zero_fires_at_entry` ✨ | 顯式 0% 重現舊行為（文檔化語意） |
| `test_trailing_short_higher_activation_locks_profit` ✨ | 空頭側 activation=5% trail=2% 鎖利鏡像 |

（✨ 為本日延後項補齊）

### 3.4 Rust IPC 往返測試（`event_consumer/tests.rs`）
`test_handle_update_risk_config_sets_trailing_activation_pct` ✨：
1. 預設 `stop_config.trailing_activation_pct == None`
2. dispatch `UpdateRiskConfig{trailing_activation_pct: Some(Some(0.3)), trailing_stop_pct: Some(Some(0.2))}`
3. assert `stop_config.trailing_activation_pct == Some(0.3)` & `trailing_stop_pct == Some(0.2)`
4. dispatch `UpdateRiskConfig{trailing_activation_pct: Some(None)}`（顯式清除）
5. assert `stop_config.trailing_activation_pct == None`

**備註**：測試用 0.2/0.3 而非 2.0/3.0 —— `event_consumer/handlers.rs` outer clamp 是 `0.0..=0.5`（fraction 語意），與 setter 的 `0.0..=50.0`（percent 語意）不一致，是 stop family 全家族的既有缺陷（summary 稱 "IPC outer-clamp fraction-vs-percent latent bug"），另案處理。測試註釋已標註。

### 3.5 Python（3 站點同一語意）
| 檔案 : 行 | 端點 / 用途 | 訪問形態 |
|--|--|--|
| `paper_trading_routes.py:441,474` | `/status` 端點 | flat（`p.get("entry_fee", 0)`） |
| `paper_trading_routes.py:631,640` | `/pnl` 端點 | flat |
| `grafana_data_writer.py:208-213` | 持久化 DB 寫入（`paper_pnl_snapshots_legacy`） | nested（`p.get("position", {}).get("entry_fee", 0)` — 匹配 `pipeline_snapshot.json` 的 `PositionSnapshot { position: PaperPosition }` 結構） |
| `paper_trading_metrics.py:185-198` ✨ | `compute_trade_metrics` 無 round-trips 的 fallback | 防禦性：list / dict / None 三路徑都處理 |

（✨ 為本日延後項補齊）

**通用公式**：
```python
open_entry_fees = sum(p.get("entry_fee", 0.0) for p in positions)
closed_fees    = max(0.0, total_fees - open_entry_fees)
net_realized   = realized - closed_fees
```

---

## 四、留尾 & 非目標

### 已知但不在本 PR 範圍
- **IPC outer-clamp fraction-vs-percent bug** — `event_consumer/handlers.rs` 對整個 stop family 的 0.0..=0.5 clamp 與 setter 的 0.0..=50.0 clamp 不一致，pre-existing，另案處理。本 PR 的 `trailing_activation_pct` 沿用同規則以不擴大 blast radius。
- **命名碰撞**：`AgentParams::trailing_activation_pct`（AI agent 層）與 `StopConfig::trailing_activation_pct`（止損層）同名但不同 struct、不同 layer semantic，E2 審查判定 benign。

### 特意不處理
- 策略百分比止盈（缺失的根因另一半）—— 超出本 PR scope，需要策略層產品決策。
- 既有 entry 以下錯砍造成的歷史虧損 —— 無法回溯，只在 `edge_estimates_paper.json` 污染分析中已隔離（見 `memory/project_edge_data_isolation.md`）。

---

## 五、驗證結果

| 項目 | pre-fix baseline | post-fix |
|--|--|--|
| `openclaw_core` lib | 366 | **372**（+6，4 activation 基礎 + 2 本日延後項） |
| `openclaw_engine` lib | 1144 | **1146**（+2 IPC 回環 + 顯式清除） |
| `openclaw_engine` e2e | 33 | 33 |
| Python control_api | 2446 pass / 1 skip | **2446 pass / 1 skip**（0 regression） |
| `paper_trading_metrics` smoke | — | 3/3 PASS（list/dict/None 三種 positions 形態） |

E2 審查結論：`Merge-ready for demo/paper validation`。

---

## 六、部署備註

### 熱重載路徑
`UpdateRiskConfig` IPC command 走既有 tick-level hot-reload 鏈路，無需 restart-to-apply（符合 ARCH-RC1 1C-4 不變量）。GUI 側直接透過 Rust ConfigStore 寫入即可。

### 運行中引擎需重啟
本修復動了 Rust binary（`stop_manager.rs` + IPC handler），運行中引擎仍是 pre-fix binary。Operator 需執行：
```bash
bash helper_scripts/restart_all.sh --rebuild
```
rebuild 旗標會重編 PyO3 .so + 雙寫兩個 venv（QoL-3 鏈路），然後重啟引擎。

### 可觀測性
部署後 24h 內可運行：
```bash
# 統計 trailing stop 觸發的 PnL 分佈
grep 'event="trailing_stop_triggered"' /tmp/openclaw/engine_logs/engine-*.log \
  | jq -s 'group_by(.pnl_pct_approx > 0) | map({profit: .[0].pnl_pct_approx > 0, count: length})'
```
預期分佈：
- Pre-fix: winners ≪ losers, `avg(pnl_pct_approx) < 0`
- Post-fix: winners > losers（或至少不再貼近 0），`avg(pnl_pct_approx) > 0`

---

## 七、時序

| 時間 | 事件 |
|--|--|
| T0 | User 報告 GUI 反直覺現象 |
| T0+5min | Explore sub-agent 誤診為「手續費不對稱」 |
| T0+15min | 直讀源碼推翻首輪假設，定位真實 smoking gun |
| T0+25min | 提出 A/B 兩方案，user 選 B + 要求併修 logging + net_realized_pnl |
| T0+60min | Rust core fix + 接線 + Python 2 站 + 初版測試 |
| T0+75min | E2 sub-agent 審查 → `Merge-ready MINOR FIX` |
| T0+85min | 採納 E2 建議擴展至 `grafana_data_writer.py` |
| 撞 context compact | — |
| T+compact+30min | 按 user 指示補齊 4 項延後：`paper_trading_metrics.py` fallback + IPC 回環測試 + activation=0 邊界 + 空頭側鏡像 |
| 本文產出 | 準備 commit |
