# E1 · P1-PORTFOLIO-RESTING-EXPOSURE-1 IMPL Self-Report

**Date**：2026-05-16
**Agent**：E1（isolation worktree `worktree-agent-ac285607fa3c51402`）
**Ticket**：`P1-PORTFOLIO-RESTING-EXPOSURE-1`
**Status**：🟡 **IMPL DONE — 待 A3 + E2 + E4 + PM 對抗審查鏈**
**Branch**：`worktree-agent-ac285607fa3c51402`（git tracked，等 PM 統一 commit）

---

## §1 Code diff summary（檔 + LOC）

| 檔案 | 變更類型 | LOC delta | post-IMPL 大小 |
|---|---|---:|---:|
| `rust/openclaw_engine/src/paper_state/resting_orders.rs` | 新增 `pub(crate) fn resting_limit_orders_iter()` 跨 symbol 唯讀迭代器 | +11 | 681 / 2000 |
| `rust/openclaw_engine/src/intent_processor/mod.rs` | 新增 helper `compute_effective_long_short_notional`；改 `compute_exposure_pct` / `compute_correlated_exposure_pct` / `compute_leverage` 全部共用 helper | +118 | 1650 / 2000 |
| `rust/openclaw_engine/src/intent_processor/tests.rs` | 新增 7 unit test（baseline / entry-only / close-only / mixed multi-symbol / capped-at-filled / same-direction-is-entry / finite guards）+ 2 test helper | +208 | 1793 / 2000 |
| **合計** | | **+337** | — |

**未動到的檔案（confirmed read-only verify）**：
- `rust/openclaw_engine/src/intent_processor/router.rs:438-450 / 904-916`：caller 端 — 行為不變（呼同名 helper，內部邏輯改）
- `rust/openclaw_engine/src/replay/risk_adapter.rs`：`ReplayPaperSnapshot.exposure_pct/correlated_exposure_pct` 是 `runner.rs` 直接寫入的 parallel surface（doc comment 仍說 "mirrors `IntentProcessor::compute_exposure_pct`"，但 runtime 不共用 helper）。replay-side resting-aware enhancement 是後續另案，不在本 P1 scope。
- `risk_checks.rs:467-1027` 27 個 `check_order_allowed` unit test：用 hardcoded exposure 數字直測，不 mock helper，0 影響 — confirmed PASS 在 lib regression 內。
- `intent_processor/tests_predictor_router.rs`：未引用 `compute_exposure_pct` 系列，0 影響。
- 任何 `risk_config*.toml` / `correlated_exposure_max_pct` config：**未動**（per CLAUDE.md §四 硬邊界）。
- 任何 live / authorization / lease 邏輯：**未動**。

**沒做的事**：
- 沒加 healthcheck `[58] portfolio_resting_exposure_lineage`（A3 §8 設計選項 A 建議的 passive monitor）— scope 內未要求；PM 若要可派下一輪。
- 沒處理 `correlation.max_pairwise_r` dead config（A3 §3 finding）— 與本 ticket 解耦，是另案。
- 沒對 exchange path 真實 cum_filled_qty 處理 partial cancel race（A3 §5 P2 advisory）。

---

## §2 Logic 證明：why entry resting 加 + close resting 減

### 名詞對齊
- `PaperPosition.qty` = 已成交 filled qty（per `containers.rs:18-21`；fill events 累計，per `event_consumer/loop_exchange.rs:192`）。
- `RestingLimitOrder.qty` = 已 enqueue 但尚未 fill 的 PostOnly maker 預期數量（per `resting_orders.rs:261-298`）。

### 動機（A3 verify report §2 / §7）
修前 `compute_exposure_pct` + `compute_correlated_exposure_pct` 只看 `paper_state.positions()`，對 `paper_state.resting_limit_orders` **完全 invisible**。後果分兩方向：

| Scenario | 修前 | 為什麼 |
|---|---|---|
| entry-side resting 等待 fill | **under-estimate** | filled 邊 = 0 仍走 portfolio gate，後續 entry 計算偏低，可能誤准風險超標的新單 |
| close-side resting 等待 fill | **over-estimate** | filled 邊保留 full，後續 entry 計算偏高，可能誤拒不該拒的新單 |

### 修後設計：per-symbol netting
1. **Filled** 直接加入對應 long / short bucket（與舊行為一致）。
2. **Resting**，視「相對於該 symbol 已有 filled position」的方向：
   - **同向 / symbol 無倉**：entry-side → resting notional 加入同方向 bucket（風險預期增加）。
   - **反向（i.e. `is_reducing == true` 與 `router.rs:261-265 / 752-756` 判定對齊）**：close-side → 從對立 filled 邊**扣減** resting notional，封頂於對立 filled 餘額（避免出現負值）。
3. 整體 effective notional 仍 `≥ 0`（負值被 `.max(0.0)` clamp）。

### 形式驗證（單 symbol）
```
filled_long, filled_short  ∈ [0, ∞)
entry_long, entry_short    ∈ [0, ∞)
red_long, red_short        ∈ [0, ∞)   // 來自反向 resting（red_long ← short resting；red_short ← long resting）

eff_long  = max(0, filled_long  + entry_long  - min(red_long, filled_long))
eff_short = max(0, filled_short + entry_short - min(red_short, filled_short))
```
觀察：
- `min(red_long, filled_long) ≤ filled_long` → `filled_long - min(...) ≥ 0` → `eff_long ≥ entry_long ≥ 0`。同理 eff_short。
- **不變式 1**：close-side resting 永遠不能讓 long / short 翻面（避免 view inverted）。
- **不變式 2**：entry-side resting 永遠加進對應方向（即使該 symbol 無倉，也能反映預期新倉）。

### 為什麼這方向「更保守」（CLAUDE.md §二 原則 5 / 6 / 16）
- entry-side under-estimate 修正 → 更可能拒絕風險超標 entry（生存 > 利潤）。
- close-side over-estimate 修正 → 可能放行更多 entry，但僅當對立 close pending 真實存在；不是無條件放鬆，而是反映「該 symbol 預期會減倉」這一已下單事實。
- 不跨 symbol 假設對沖（A3 §8 設計要點 1 保留「同方向風險疊加」核心）。

### 邊界處理
- `qty <= 0 / NaN / limit_price <= 0` → resting 行被靜默過濾（test 7 涵蓋）。
- `balance <= 0` → 早回 0%（與舊行為一致）。
- `.min(999.0)` 上限保留（與舊行為一致）。

---

## §3 Test list + result（Mac PASS）

### 新增 7 unit tests（全 PASS）
```
running 7 tests
test intent_processor::tests::test_p1_portfolio_resting_baseline_no_resting_unchanged ... ok
test intent_processor::tests::test_p1_portfolio_resting_entry_only_added_to_long ... ok
test intent_processor::tests::test_p1_portfolio_resting_same_direction_resting_is_entry_not_close ... ok
test intent_processor::tests::test_p1_portfolio_resting_close_only_reduces_filled ... ok
test intent_processor::tests::test_p1_portfolio_resting_entry_plus_close_mixed_multi_symbol ... ok
test intent_processor::tests::test_p1_portfolio_resting_finite_guards_filter_bad_inputs ... ok
test intent_processor::tests::test_p1_portfolio_resting_close_reduces_capped_at_filled ... ok

test result: ok. 7 passed; 0 failed; 0 ignored; 0 measured; 2909 filtered out
```

### 場景覆蓋對照表（per dispatch §「Step 3」要求）
| 場景 | Test name | 期望 / 實際 |
|---|---|---|
| baseline 無 resting | `..._baseline_no_resting_unchanged` | exposure=0.5%、correlated=0.5%、leverage=0.005 ✓ |
| entry-only（無倉 + entry resting） | `..._entry_only_added_to_long` | exposure=1.0%、correlated=1.0% ✓ |
| close-only（filled + 反向 resting） | `..._close_only_reduces_filled` | exposure=1.0%、correlated=1.0%（filled 2% → close 半 → 1%） ✓ |
| entry + close mixed（多 symbol） | `..._entry_plus_close_mixed_multi_symbol` | exposure=2.5%、correlated=1.5% ✓ |
| reduces 量 > filled 量（封頂） | `..._close_reduces_capped_at_filled` | exposure≈0、correlated≈0（不會負值）✓ |
| same-direction resting = entry 非 close | `..._same_direction_resting_is_entry_not_close` | exposure=1.5%、correlated=1.5% ✓ |
| 防禦性 finite guards | `..._finite_guards_filter_bad_inputs` | 3 個垃圾 row 全跳過、結果與 baseline 同 ✓ |

容差全部 1e-4（per `regression-testing-protocol` 與 IPC 浮點一致性對齊）。

### 全 lib regression（per `regression-testing-protocol`）
```
test result: ok. 2915 passed; 0 failed; 1 ignored; 0 measured; 0 filtered out; finished in 0.71s
```
**Baseline 2908 + 新增 7 = 2915，0 regression。1 ignored 是既有 socket-permission test（Mac 限制，與本 IMPL 無關）。**

---

## §4 Cross-platform check（Mac aarch64）

```
$ cargo check --target aarch64-apple-darwin -p openclaw_engine --lib
warning: unused import: `super::LEAD_WINDOW_SECS_MAIN` (panel_aggregator/btc_lead_lag/db_writer.rs)
warning: method `make_intent` is never used (strategies/ma_crossover/helpers.rs)
warning: `openclaw_engine` (lib) generated 2 warnings
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 25.57s
```
**PASS**。2 warning 是 pre-existing dead code，與本 IMPL 無關。

### 跨平台合規（CLAUDE.md §七 ★★）
- `grep -E '(/home/ncyu|/Users/[^/]+)' <new files>` → **0 命中**。
- 無 Linux-only 依賴新增。
- `use std::collections::HashMap` / `HashSet` 純 std。
- `use std::collections::HashMap` 在 fn 內局部 import（避免污染 mod 命名空間）。
- 無 path 字面值；無 OS-specific syscall；無 env-gated 行為。

---

## §5 Pre-existing baseline / files 大小

| 檔案 | Pre-IMPL | Post-IMPL | hard cap | 餘額 |
|---|---:|---:|---:|---:|
| `paper_state/resting_orders.rs` | 670 | 681 | 2000 | 1319 |
| `intent_processor/mod.rs` | 1532 | 1650 | 2000 | 350 |
| `intent_processor/tests.rs` | 1585 | 1793 | 2000 | 207 |

無 §九「Pre-existing baseline exception clause」觸發。tests.rs 餘額 207 LOC，若下一輪 A3/E2 要求加 test 仍有 headroom；接近 cap 時建議拆 `tests_p1_portfolio_resting.rs` 並 `include!` 進來。

---

## §6 Sign-off prereq（per `feedback_impl_done_adversarial_review.md`）

**E1 IMPL DONE ≠ Sign-off**。E1 不自評 sign-off，留下列審查鏈：

| Reviewer | 範圍 | 預期判定點 |
|---|---|---|
| **A3** | 對抗審 — 反問 logic：close-side 扣減的封頂語意是否完整？同 symbol 雙 leg / hedge mode 是否有 hidden assumption？多 reducing resting 累加是否會 silently 互蝕？ | A3 reframe 可能會發現未涵蓋場景 → 反饋給 E1 補測 |
| **E2** | 代碼審查 — comment 中文 only 合規？`pub(crate)` 暴露範圍合理？helper 命名是否與 codebase pattern 一致？兩階段 HashMap 是否有更省 alloc 寫法？`Self::compute_*` 私有性保留？| 補 minor optimization、code style 對齊 |
| **E4** | regression — Mac 2915 PASS、Linux PG 真實 environment 跑（per `feedback_v_migration_pg_dry_run.md` 雖然本 IMPL 不涉 V### migration，但 Linux runtime 是 SoT）、確認 `risk_checks` 27 個 unit test 仍 PASS。| E4 跑 Linux trade-core 端、給 GREEN 後 PM 才能 commit |
| **PM** | 統一 commit + push（per CLAUDE.md §七 強制鏈 E1→E2→E4→QA→PM） | PM 拍板 |

**未被驗證的場景（請 A3 reviewer 重點驗）**：
1. `compute_leverage` 因為內部呼 `compute_exposure_pct`，間接吃 effective notional。原 RG-2 設計是看 filled。是否所有 leverage caller（如 `risk_checks::check_order_allowed`）對 effective leverage 的解讀仍正確？— 我認為是的（leverage 不變式：總 notional / balance；resting 既是 pending 風險，納入更保守），但 A3 應對抗驗證。
2. 同 symbol 多 reducing resting 累加（例：long 100 filled + 3 short resting 各 60 → total reduces=180 > filled=100）會被封頂於 100。這是 conservative correct，但 close-maker-first 設計時應留意：若連續派多筆 close pending，effective view 不會比 filled 更悲觀（不會 over-reduce）。Test (4) 已釘住此不變式。
3. ReplayPaperSnapshot 是否需要平行改？我判定 **NO**（runner.rs 直接寫 snapshot，replay 路徑用自己的 ReplayPosition struct，沒有 resting_limit_orders 概念）。若 replay 後續要 resting-aware → 另案 P2。

**Operator 下一步**：
1. 派 A3 對抗審（focus §6 三個未驗場景）
2. 派 E2 代碼審查
3. A3 + E2 GREEN → 派 E4 Linux runtime regression
4. E4 GREEN → PM 統一 commit `worktree-agent-ac285607fa3c51402` branch

---

## 附錄 A：關鍵 diff 摘錄

### A.1 `paper_state/resting_orders.rs:+11`
```rust
/// P1-PORTFOLIO-RESTING-EXPOSURE-1：跨 symbol 唯讀迭代所有掛單。
/// intent_processor 的 portfolio gate（`compute_exposure_pct` /
/// `compute_correlated_exposure_pct`）需要在計算 effective notional 時把
/// resting maker（含尚未有 PaperPosition 的純 entry-side）一併納入；保留
/// `pub(crate)` 限縮在 engine crate 內，避免外部 module 越界擴張使用範圍。
pub(crate) fn resting_limit_orders_iter(
    &self,
) -> impl Iterator<Item = &RestingLimitOrder> + '_ {
    self.resting_limit_orders.values().flat_map(|q| q.iter())
}
```

### A.2 `intent_processor/mod.rs` 新增 helper（精簡版簽名）
```rust
fn compute_effective_long_short_notional(paper_state: &PaperState) -> (f64, f64) {
    // 三階段：
    // 1. 收 filled 邊（per symbol，long / short 兩 bucket）
    // 2. 掃 resting：依「同 symbol 對立 filled 是否存在」分流 entry-side / close-side
    // 3. per-symbol 收口：close 扣減封頂於對立 filled 餘額 → 累加 total
    ...
}
```

### A.3 `intent_processor/mod.rs` `compute_*` 兩 caller 改共用 helper
```rust
fn compute_exposure_pct(paper_state: &PaperState) -> f64 {
    let balance = paper_state.balance();
    if balance <= 0.0 { return 0.0; }
    let (eff_long, eff_short) = Self::compute_effective_long_short_notional(paper_state);
    ((eff_long + eff_short) / balance * 100.0).min(999.0)
}

fn compute_correlated_exposure_pct(paper_state: &PaperState) -> f64 {
    let balance = paper_state.balance();
    if balance <= 0.0 { return 0.0; }
    let (eff_long, eff_short) = Self::compute_effective_long_short_notional(paper_state);
    (eff_long.max(eff_short) / balance * 100.0).min(999.0)
}
```

---

**E1 IMPLEMENTATION DONE: 待 A3 + E2 + E4 + PM 對抗審查鏈 — report path：`srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-16--p1_portfolio_resting_exposure_impl_self_report.md`**
