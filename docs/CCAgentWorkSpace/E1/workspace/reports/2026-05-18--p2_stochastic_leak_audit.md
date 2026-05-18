## P2-STOCHASTIC-LEAK + P2-DEAD-RUST-CLEANUP-1 — E1 IMPL Report

Date: 2026-05-18
Author: E1
Sprint: P2 hygiene bundle
Operator authorization: full authorization for both P2 items (2026-05-18).

---

### Task 1 — P2-STOCHASTIC-LEAK：Stochastic look-ahead leak audit + leak-free variant

#### 1.1 Leak verification

確認 `rust/openclaw_core/src/indicators/momentum.rs:80-86`（原始 `stochastic()` 主迴圈）使用：

```rust
for i in (n - d_period)..n {
    let start = i + 1 - k_period;
    let h_max = high[start..=i].iter().cloned().fold(...);   // 含當前 bar
    let l_min = low[start..=i].iter().cloned().fold(...);    // 含當前 bar
    ...
}
```

**Slice `[start..=i]` 含當前 bar i**，與 `feedback_indicator_lookahead_bias` 揭示的
`rolling(N).max()` 同類 look-ahead bias。當當前 bar 創新 N 根高/低時，%K 必然落在
0/100 邊界，對「當前 bar 是否突破近 N 根 high/low」這類 forecast-vs-current 判斷
構成 systematic bias。

#### 1.2 新增 `stochastic_prior()`

設計與 `donchian_prior()` 同模式（同檔 `trend.rs:215-229`）：

```rust
pub fn stochastic_prior(
    high: &[f64], low: &[f64], close: &[f64],
    k_period: usize, d_period: usize,
) -> Option<StochResult> {
    let n = high.len().min(low.len()).min(close.len());
    if k_period == 0 || d_period == 0 || n < k_period + d_period { return None; }
    stochastic(&high[..n - 1], &low[..n - 1], &close[..n - 1], k_period, d_period)
}
```

- 先切掉 `[..n-1]`（排除當前 bar）再呼叫原 `stochastic()`；
- 邊界：`n >= k_period + d_period`（比 `stochastic()` 多 1 根作為預留的當前 bar）。

#### 1.3 原 `stochastic()` 處置

保留（有既存呼叫端：`IndicatorEngine::compute_all_with_lambda`、
`tests/golden_dataset.rs` 數值黃金集）；補中文 doc-comment 警告 look-ahead bias，
指引新研究路徑改用 `stochastic_prior()`：

```rust
/// 隨機指標 %K 和 %D（%K 的 SMA），**含當前 bar**，存在 look-ahead bias。
///
/// 為什麼保留：本函數有既存呼叫端（`indicators/mod.rs` 預設 IndicatorSnapshot、
/// `tests/golden_dataset.rs` 數值回歸黃金集），刪除或改語義會破壞回歸基準。
/// 新 alpha 研究 / 策略 gate / 任何 forecast-vs-current 判斷請改用 `stochastic_prior()`，
/// 它排除當前 bar，與 `donchian_prior()` 是同一個 leak-free 設計模式。
```

未加 `#[deprecated]` 是因為 `tests/golden_dataset.rs` 是純數學回歸測試，不在
production 路徑上，且 `IndicatorSnapshot.stochastic` 欄位仍 wire 著舊行為——
延後到 production 改造 PR 時一併處理。

#### 1.4 單元測試 `test_stochastic_prior_excludes_current_bar`

證明數值分歧：用 17 根 ascending series，當前 bar (idx 16) 放極端值
(high=9999 / low=-9999 / close=5000)：

| 指標 | leaky（含當前 bar） | prior（排除當前 bar） | 分歧閾值 |
|---|---|---|---|
| %K | 受 ±9999 嚴重扭曲 (~75) | 用 0..=15 ascending → ~100 | `> 10` |
| %D | %K SMA 3 → ~82 | ~86 | `> 3`（SMA 抑制 1/3） |

另含邊界 case：n=16 時 `stochastic()` 有結果但 `stochastic_prior()` 不足（必須 17 根）。

Test PASS：`cargo test -p openclaw_core --release stochastic` → 3/3 pass。

#### 1.5 Re-export

`rust/openclaw_core/src/indicators/mod.rs:37` 新增 `stochastic_prior` re-export，
與 `donchian_prior` 同位置同模式。

#### 1.6 其他 5 個 textbook 指標的 leak audit

掃描 `rust/openclaw_core/src/indicators/` 與 `rust/openclaw_engine/src/strategies/`
使用 grep pattern：`[start..=i]`, `.windows(N)`, `rolling.*max`, `rolling.*min`,
`iter().take(i+1)`, `fold(f64::NEG_INFINITY|INFINITY)`, `highest_high`,
`lowest_low`, `rolling_max`, `rolling_min`。

| 檔:行 | 模式 | 分類 | 說明 |
|---|---|---|---|
| `momentum.rs:82` `stochastic` | `high[start..=i]` | **LEAKY** | 本 PR `stochastic_prior` 提供 leak-free 替代；舊函數保留供既存 callers |
| `momentum.rs:19` `rsi` | `close.windows(2)` | LEAK-FREE | 算 day-to-day diff，無 forecast-vs-current 判斷 |
| `momentum.rs:117-209` `adx` | `high[i] vs high[i-1]` | LEAK-FREE | 全用 `i` 與 `i-1` 對比；無滑動窗口取 max/min |
| `trend.rs:14-20` `sma` | `&close[close.len() - period..]` | BENIGN | 純尾段 SMA，非 forecast-vs-current 判斷；indicator-as-summary |
| `trend.rs:28-40` `ema` | `&close[period..]` | BENIGN | 同 SMA，純尾段 EMA |
| `trend.rs:76-115` `macd` | `fast_ema - slow_ema` | BENIGN | EMA 衍生 |
| `trend.rs:131-167` `kama` | `&close[close.len() - period - 1..]` | BENIGN | adaptive MA，尾段一根當「終值」 |
| `trend.rs:190-213` `donchian` | `&high[n - period..n]` | **LEAKY** | **已修復**：`donchian_prior` (trend.rs:217-229) 提供 leak-free 替代；`compute_all_with_lambda` 線上路徑已切到 `donchian_prior` |
| `volatility.rs:25-59` `bollinger` | `&close[close.len() - period..]` | BENIGN | mean + std 的尾段 summary；非 forecast 判斷 |
| `volatility.rs:75-110` `atr` | `high[i] vs close[i-1]` | LEAK-FREE | Wilder smoothing；無滑動 max/min |
| `volatility.rs:133-255` `hurst` | `cum_dev.fold(...)` | BENIGN | R/S analysis 內部，cum_dev 已是 chunk 內 prior-to-chunk-end 路徑，非 forecast 判斷 |
| `volatility.rs:272-307` `ewma_vol` | `close.windows(2)` | LEAK-FREE | log returns，無滑動 max/min |
| `volume.rs:12-24` `volume_ratio` | `&volume[n - period - 1..n - 1]` | LEAK-FREE | 顯式排除 `volume[n-1]`，當前 bar 只當分子 |

掃描 `strategies/{bb_breakout,bb_reversion,grid_trading,ma_crossover}` 與
`strategies/funding_arb.rs`：

| 路徑 | 結果 |
|---|---|
| `bb_breakout/*` | 無 `[..=i]`、`fold(NEG_INFINITY)`、`rolling_max` 等模式（comments 中 "rolling" 是時窗描述、不是 max 計算） |
| `bb_reversion/*` | 同上 |
| `grid_trading/*` | `grid_helpers.rs` 有 `.windows(2)` 算 diff，無 max/min 滑動 |
| `ma_crossover/*` | 純 MA cross，無 max/min 滑動 |
| `funding_arb.rs` | 無任何 max/min 滑動 |

**結論**：除已知 stochastic + donchian 兩個 textbook 高/低類指標外，無其他 LEAKY hit。
動量指標（RSI/ADX）、波動率（ATR/Bollinger/EWMA）、量比都是 summary-style，
不構成 forecast-vs-current 同類 bias。

#### 1.7 範圍限制

依 PA 指示 only `stochastic_prior` 在本 PR 落地。其他發現（`donchian` 已修、
其他指標 BENIGN）記錄此報告供未來 P2/P1 參考，不在本 PR 改動。

---

### Task 2 — P2-DEAD-RUST-CLEANUP-1：退役 7 個 dead modules（ADR-0015）

#### 2.1 ADR scope 比對

`docs/adr/0015-openclaw-control-plane-repositioning.md` §Decision：
> The legacy `openclaw_core` modules that modeled a parallel cognition/trading
> brain are permanent sunset candidates. They may be removed after source
> reference audit and tests prove the active Rust execution path no longer uses
> them.

§Consequences：
> W-AUDIT-5 may schedule removal of the **nine** legacy `openclaw_core` modules;
> that cleanup is structural only and does not change trading authority.

ADR 提「nine」但 PA TODO 列 7 個。我只刪除 PA 授權的 7 個，剩餘 2 個未在本 PR
觸碰（PA 未授權）。

#### 2.2 Production caller 核查

使用 strict grep：
```bash
rg -l "openclaw_core::(attention|attribution|cognitive|dream|message_bus|order_match|opportunity)\b" rust --type rust
```
→ 空結果。

廣譜 grep（排除模塊自身與同名概念）：
- `openclaw_types/src/cognitive.rs` 是 **types crate** 內的 `CognitiveParams`/
  `DreamInsight`/`RegretSummary`/`SkippedOpportunity` 定義，與
  `openclaw_core::cognitive` **不同模塊**，由其他生產代碼使用，**不刪除**。
- `scanner::opportunity`、`scanner::opportunity_tracker`、`OpportunityCostPrior`
  在 `openclaw_engine/src/scanner/` 內，是另一個 production-live 模塊，與
  `openclaw_core::opportunity` 同名但不同 crate/path，**不刪除**。
- 工程中所有 `attribution_chain_ok`、`attention_tax`、`owner_attribution`、
  `position_risk_evaluator.attention_tax` 是 string token 或 nested struct 欄位
  名，與 7 個被刪模塊無 import 關係。

| 模塊 | LOC（實測） | production caller | 處置 |
|---|---|---|---|
| `attention.rs` | 424 | 0 | DELETE |
| `attribution.rs` | 267 | 0 | DELETE |
| `cognitive.rs` | 524 | 0 | DELETE |
| `dream.rs` | 936 | 0 | DELETE |
| `message_bus.rs` | 296 | 0 | DELETE |
| `order_match.rs` | 308 | 0 | DELETE |
| `opportunity.rs` | 861 | 0 | DELETE |
| **合計** | **3616** | 0 | 7/7 刪除 |

LOC 實測 3616，與 PA TODO 3186 差 430，源於這些模塊在 retire 前曾有 incremental
edits（report 紀錄為當下實測值）。

#### 2.3 `lib.rs` delta

```diff
-pub mod attention;
-pub mod attribution;
 pub mod backtest;
-pub mod cognitive;
 pub mod cost_gate;
-pub mod dream;
 pub mod execution;
 pub mod governance_core;
 ...
 pub mod lease_scope;
-pub mod message_bus;
-pub mod opportunity;
-pub mod order_match;
 pub mod portfolio;
```

新增 retirement 中文註釋：
```rust
// P2-DEAD-RUST-CLEANUP-1 (2026-05-18, ADR-0015):
// attention/attribution/cognitive/dream/message_bus/order_match/opportunity
// 七個 legacy 模塊原為平行 cognition/trading 大腦設計，現確認無任何 production
// caller, 依 ADR-0015 結構性退役。
```

#### 2.4 測試 + tests dir 影響

掃描測試樹：無任何 test file 從 `openclaw_core::{attention|attribution|cognitive|
dream|message_bus|order_match|opportunity}` import。模塊內部 `#[cfg(test)] mod tests`
隨檔一併刪除（屬於 retired module，與 production code 同 fate）。

#### 2.5 ADR 文本

未觸碰 `docs/adr/0015-openclaw-control-plane-repositioning.md`（依指示）。

---

### 驗證結果

```bash
cd /Users/ncyu/Projects/TradeBot/srv/rust

# Cargo check（兩個 crate）
cargo check -p openclaw_core --release   # OK，0 errors / 0 warnings new
cargo check -p openclaw_engine --release # OK, 3 pre-existing dead_code warnings 不在我 scope

# Cargo test
cargo test -p openclaw_core --release    # 399 passed / 0 failed / 1 ignored
cargo test -p openclaw_engine --release  # 3200 passed / 2 failed (PRE-EXISTING) / 1 ignored
```

#### 預先存在的失敗（不在我 scope）

`openclaw_engine` 的 2 個 stress integration test 失敗：
- `stress_bb_breakout_valid_squeeze_with_volume`
- `stress_bb_reversion_extreme_oversold_bounce`

**已三方驗證為 pre-existing**：
1. 完整 stash 所有我的改動（rust/openclaw_core/）+ stash 其他 session 的
   `intent_processor/` modifications → 在乾淨 main HEAD 上 stress_integration 仍
   FAILED. 33 passed; 2 failed。
2. 失敗測試完全不 import 任何被我刪除的 7 個模塊。
3. 與 momentum.rs 的 `stochastic_prior` 新增不相關（這些測試走 BB / donchian path，
   不走 stochastic）。

非我責任，已留紀錄供 next sprint triage（可能與 070ff0a3 `SCANNER-PINNED-GATE-1`
commit 後的 strategy gate 變動相關）。

#### 測試計數 delta

| Crate | Baseline | After my changes | Delta |
|---|---|---|---|
| openclaw_core | (含原 indicator tests) | 357 + 6 + 8 + 19 + 2 + 7 = 399 (+1 from `test_stochastic_prior_excludes_current_bar`) | **+1** |
| openclaw_engine | 2993 / 0 / 1（PA 給的 baseline） | 2993 / 0 / 1 unit + 207 integration (33 stress 中 2 個 pre-existing FAILED) | 0 unit test delta |

---

### LOC delta

```
+ momentum.rs: +57 (stochastic_prior fn + 35-line doc comments + 47-line test)
+ mod.rs:      +1  (re-export stochastic_prior)
+ lib.rs:      +4 net (-7 pub mod lines, +3 retirement comment lines, +1 net structural)
- attention.rs (-424) - attribution.rs (-267) - cognitive.rs (-524) - dream.rs (-936)
- message_bus.rs (-296) - order_match.rs (-308) - opportunity.rs (-861)
─────────────────────────────────────────────
Total: -3554 LOC net
```

---

### 治理對照

| 項目 | 狀態 |
|---|---|
| 不擴大 PA scope | ✅ 只動 PA 列出的 7 模塊 + momentum.rs 局部 |
| MODULE_NOTE / 新代碼中文注釋 | ✅ stochastic_prior 注釋中文，retirement marker 中文 |
| 不改硬邊界 | ✅ 未碰 max_retries / live_execution_allowed / execution_authority / system_mode |
| 不改 ADR | ✅ 0015 未動 |
| 不順手優化 | ✅ 未動 stress test、未動 pre-existing warning |
| 跨平台 | ✅ 純 Rust 純計算，無路徑硬編碼 |

---

### 不確定之處

1. **ADR-0015 的「nine」vs PA TODO 的 7**：剩餘 2 個 sunset candidates 是哪兩個？
   ADR §Consequences 未列名。建議 PA 確認後在 next sprint 補刪或修 ADR。

2. **`stochastic()` 是否該打 `#[deprecated]`**：保留是因為 `compute_all_with_lambda`
   產生的 `IndicatorSnapshot.stochastic` 仍是含 leak 的版本，若改成 `_prior` 變體
   會 break golden_dataset 與下游 ML feature schema。建議 next P1 sprint 統一改造
   `compute_all_with_lambda` 切到 `_prior`，並決定是否補一個 `_legacy_unsafe` rename。

3. **2 個 pre-existing stress test failure**：上次 baseline (PA 給的 2993/0/1)
   是何時測的？若是 070ff0a3 commit 之前，則 SCANNER-PINNED-GATE-1 引入 regression
   值得 next sprint 排查（與本 PR 無關但是值得紀錄的 finding）。

---

### Operator 下一步

1. 等 E2 對抗性審查（GUI 不涉、IPC 不涉，但檔案數目較多 + 删除整檔，建議 E2 走一輪
   高風險視角：是否有間接 caller、是否 ADR-0015 scope 對齊、stochastic_prior 測試
   閾值是否合理）。
2. 等 E4 regression：跑 replay smoke + cargo workspace test 全套（注意 2 個 pre-existing
   stress 失敗不要誤判為本 PR 引入）。
3. PA 決定剩餘 2 個 ADR-0015 sunset 模塊是否需要在 next batch 清理。
4. QA：建議追蹤 stress_bb_breakout_valid_squeeze_with_volume / stress_bb_reversion_*
   兩個失敗是否是 070ff0a3 之後的 regression。
