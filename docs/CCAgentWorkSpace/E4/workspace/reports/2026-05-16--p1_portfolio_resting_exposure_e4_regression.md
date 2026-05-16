# E4 · P1-PORTFOLIO-RESTING-EXPOSURE-1 Linux Regression Report

**Date**：2026-05-16
**Agent**：E4（main session via SSH bridge → `trade-core`）
**Branch under test**：`worktree-agent-ac285607fa3c51402` HEAD `efe14965`
**Linux scratch worktree**：`/tmp/e4-regression-1778919049`（已 cleanup）
**Runtime engine touched**：❌ 否（PID 69581 elapsed 07:14:47 持續跑、demo fresh 13.7s、`live_age_seconds=3.0`）
**Status**：🟢 **REGRESSION PASS — Linux 與 Mac baseline 1:1 對齊；非 flaky；hot path SLA 內**

---

## §1 Branch push + Linux fetch 驗證

### Mac side
- E1 worktree `worktree-agent-ac285607fa3c51402` 內 5 files modified + 1 file untracked（report）staged。`TODO.md` 未 stage（PM 統一 commit 用，per E1 self-report）。
- Commit `efe14965` "P1-PORTFOLIO-RESTING-EXPOSURE-1: include resting maker qty in portfolio exposure"（611 insertions / 22 deletions）。
- Push `origin/worktree-agent-ac285607fa3c51402` 新 branch（不 merge main）。

### Linux side
- `git fetch origin worktree-agent-ac285607fa3c51402:worktree-agent-ac285607fa3c51402` → 新 local branch + remote tracking。
- `git worktree add /tmp/e4-regression-1778919049 worktree-agent-ac285607fa3c51402` → HEAD `efe14965`，與 Mac 對齊。
- `git log --oneline -3` 確認 commit graph 一致。

---

## §2 cargo test --release 結果（兩遍）

### Run #1（cold compile + 跑）

```
$ ssh trade-core 'cd /tmp/e4-regression-1778919049/rust && cargo test --release --lib -p openclaw_engine'
（編譯 ~75s，測試 7.74s）

test result: ok. 2915 passed; 0 failed; 1 ignored; 0 measured; 0 filtered out; finished in 7.74s
```

### Run #2（hot compile，純跑）

```
$ ssh trade-core 'cd /tmp/e4-regression-1778919049/rust && cargo test --release --lib -p openclaw_engine'
（測試 10.00s）

test result: ok. 2915 passed; 0 failed; 1 ignored; 0 measured; 0 filtered out; finished in 10.00s
```

### 對齊 Mac baseline

| 引擎 | passed | failed | ignored | baseline (Mac) | delta |
|---|---:|---:|---:|---:|---:|
| openclaw_engine --lib (Run #1) | 2915 | 0 | 1 | 2915 / 0 / 1 | **0 / 0 / 0** |
| openclaw_engine --lib (Run #2) | 2915 | 0 | 1 | 2915 / 0 / 1 | **0 / 0 / 0** |

**結論**：1:1 對齊 E1 self-report 的 Mac post-IMPL 數字（2915 / 0 / 1）。**Pre-IMPL baseline 2908 + new 7 = 2915，0 regression**。1 ignored 是 pre-existing socket-permission test（Mac 平台限制，per E1 self-report §3，與 P1 IMPL 無關）。

**Flaky check**：Run #1 與 Run #2 數字完全一致 → **非 flaky**。

---

## §3 7 個 P1 new test — Linux 端逐項驗證

聚焦 `intent_processor::tests` 子集（`--test-threads=1`）：

```
$ cargo test --release --lib -p openclaw_engine -- --test-threads=1 intent_processor::tests
test result: ok. 108 passed; 0 failed; 0 ignored; 0 measured; 2808 filtered out; finished in 0.02s
```

7 個 P1 new test 全 PASS（與 E1 self-report §3 對應表一致）：

| # | Test name | 場景 | Linux 結果 |
|---|---|---|---|
| 1 | `test_p1_portfolio_resting_baseline_no_resting_unchanged` | baseline 無 resting → 行為不變 | ✅ ok |
| 2 | `test_p1_portfolio_resting_entry_only_added_to_long` | 無倉 + entry resting → 加 long bucket | ✅ ok |
| 3 | `test_p1_portfolio_resting_close_only_reduces_filled` | filled + 反向 resting → 扣減 filled | ✅ ok |
| 4 | `test_p1_portfolio_resting_entry_plus_close_mixed_multi_symbol` | 多 symbol mixed | ✅ ok |
| 5 | `test_p1_portfolio_resting_close_reduces_capped_at_filled` | close 量 > filled 量 → 封頂於 filled | ✅ ok |
| 6 | `test_p1_portfolio_resting_same_direction_resting_is_entry_not_close` | 同 symbol 同向 resting = entry，非 close | ✅ ok |
| 7 | `test_p1_portfolio_resting_finite_guards_filter_bad_inputs` | qty/price/NaN/Inf 全 filter | ✅ ok |

intent_processor::tests 內共 108 tests（含 cost_gate / router_gate_lease / governor / d15 cap 等 lib regression 鄰居）— 全 PASS，0 regression spill。

---

## §4 浮點容差合規（`regression-testing-protocol` §6, 1e-4）

grep `intent_processor/tests.rs` 內 P1 new test assertion：

| 行 | 容差 | 對象 |
|---|---|---|
| 1646 / 1667 / 1692 / 1721 / 1744 / 1765 / 1788 | `< 1e-4` | exposure_pct |
| 1647 / 1668 / 1693 / 1722 / 1745 / 1766 / 1789 | `< 1e-4` | correlated_exposure_pct |
| 1648 | `< 1e-6` | leverage（**更嚴於 1e-4，合規**） |

**結論**：7 個 P1 new test 全部用 1e-4（exposure / corr）或更嚴的 1e-6（leverage）。**無更鬆容差，符合 cross-language consistency 規定**。本 IMPL 不涉 Python ↔ Rust 雙端跑同算式（compute_exposure_pct 是 Rust-only helper，Python 不平行算），但 1e-4 容差留 future cross-language assertion headroom。

---

## §5 Bench / SLA 結果

### 5.1 既有 hot_path_baseline bench

無專屬 `intent_processor::compute_exposure_pct` micro-bench。跑現有 `hot_path_baseline`（tick_pipeline `on_tick` end-to-end，5 symbols × 10000 ticks）：

```
hot_path_baseline ticks=10000 symbols=5 avg_us=24.918 p50_us=32.070 p99_us=42.279 max_us=55.715
```

| 指標 | 實測 (μs) | SLA (μs) | 結論 |
|---|---:|---:|---|
| avg | 24.918 | < 300 | ✅ 遠在內 |
| p50 | 32.070 | < 300 | ✅ |
| p99 | 42.279 | < 300 | ✅ |
| max | 55.715 | < 300 | ✅ |

**Tick path < 0.3ms SLA（per skill §4.5）顯著滿足**。compute_exposure_pct 是 portfolio gate 內 helper（router.rs:438-450 / 904-916 caller），由 tick_pipeline on_tick → portfolio gate 鏈呼到；新 helper 兩階段（per-symbol HashMap pass + accumulate）alloc 微增，但 hot_path_baseline 顯示 end-to-end 沒 budget 被吃光。

### 5.2 P2 follow-up（建議 E5）

- **Recommended**：加 `intent_processor::compute_exposure_pct` micro-bench harness（`benches/intent_processor_exposure.rs`）。理由：current `hot_path_baseline` 無 resting orders 在 paper_state，所以本 IMPL 的「per-symbol HashMap netting + iterator 掃 resting」這條 new path 沒被壓測涵蓋。Production 上 paper_state.resting_orders 在 PostOnly maker-first 設計下可累積數十個 resting → 應有 micro-bench 給 hot-path budget 留 watchdog。
- 不是 BLOCKER：本 IMPL 端對端 hot path 已驗 < SLA；future load shape 不變的話無 regression 風險。

---

## §6 Regression Verdict

### 必過清單

- ✅ Linux release lib：2915 passed / 0 failed / 1 ignored（與 Mac 1:1）
- ✅ 7 個 P1 new test 全 PASS（intent_processor::tests focused run 確認）
- ✅ intent_processor 鄰居 108 tests 全 PASS（0 spill regression）
- ✅ 跑兩遍同綠（非 flaky）
- ✅ 浮點容差 1e-4 / 1e-6 合規
- ✅ tick path p99 42μs < 300μs SLA
- ✅ Runtime engine PID 69581 未觸動（elapsed 7h14m，demo fresh）
- ✅ Linux scratch dir cleanup（worktree remove --force）
- ✅ Branch `worktree-agent-ac285607fa3c51402` 保留（origin + Linux local + Mac local）給後續 A3 / E2 / PM 用

### 未過清單

- 無。

### 退回 E1 修復清單

- 無。

### Verdict

🟢 **E4 REGRESSION PASS**

P1-PORTFOLIO-RESTING-EXPOSURE-1 Linux trade-core regression 與 Mac baseline 完全對齊，無 regression、非 flaky、hot path SLA 內。允許 A3 / E2 verdict 後 PM 統一 commit + push 到 main。

---

## §7 P2 follow-up（不阻塞 PM commit）

1. **E5 micro-bench**：加 `benches/intent_processor_exposure.rs` micro-bench 覆蓋 compute_effective_long_short_notional 的 per-symbol HashMap netting 階段，給 future paper_state.resting_orders 累積場景留 budget watchdog。
2. **Cross-language assertion deferred**：本 IMPL Rust-only；若後續 Python 端 portfolio gate shadow review 需要對齊，沿用 7 個 unit test 1e-4 容差規範即可（無需重立 baseline）。
3. **Replay-side resting-aware enhancement**：E1 self-report §1 第 2 行已標 — `replay/risk_adapter.rs.ReplayPaperSnapshot.exposure_pct/correlated_exposure_pct` 是 runner.rs 直接寫 parallel surface，doc comment 仍說 "mirrors `IntentProcessor::compute_exposure_pct`" 但 runtime 不共用 helper；replay 端 resting-aware 是另案 P2，不在本 ticket scope。

---

**E4 REGRESSION DONE: PASS · report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-16--p1_portfolio_resting_exposure_e4_regression.md`**
