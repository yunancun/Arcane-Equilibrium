# E4 Regression Report — P1-PORTFOLIO-RESTING-EXPOSURE-1 supplement

**Date**：2026-05-16
**Agent**：E4
**Target commit**：`ad5e609e`（origin/main HEAD）
**Scope**：Wave B-4 +82 LOC `intent_processor/tests.rs`（`test_resting_entry_qty_correlated_pair_blocks_oversize`）
**Sibling Phase 1b dirty files**：14 modified + 4 new（0 `intent_processor/` overlap）

---

## §1 Pre-flight：Linux state + dirty files inventory

| 項 | Value |
|---|---|
| Mac `git log -1` | `ad5e609e docs: wave alpha + impl 3-agent parallel dispatch round 2` |
| Mac dirty | 14 M + 4 ?? sibling Phase 1b — 0 命中 `intent_processor/` |
| Linux `~/BybitOpenClaw/srv` fetch + `git log -1 origin/main` | `ad5e609e ✅` |
| Linux main worktree `git status --porcelain` | **0 dirty**（clean，無 sibling 干擾） |
| Linux engine PID 69581 | 不變動（cargo test 不觸 runtime） |

**Sibling Phase 1b 0 overlap 認定**：sibling 改 `commands.rs / event_consumer/* / strategies/grid_trading/* / strategies/maker_rejection.rs / pending_sweep.rs / step_4_5_dispatch.rs / pipeline_helpers.rs / database/* / passive_wait_healthcheck/*`，**全部** 0 命中 `intent_processor/`。新 test 是純 unit scope（`PaperState::new(10_000.0)` 構造，無 IPC/no global mutation），對 sibling 0 副作用。

---

## §2 intent_processor module test run（Linux）

```
$ cargo test --release -p openclaw_engine --lib intent_processor 2>&1 | tail -3
test result: ok. 135 passed; 0 failed; 0 ignored; 0 measured; 2784 filtered out; finished in 0.01s
```

雙跑同 ≡（run1 + run2 都 135/0/0 finished in 0.01s）→ **非 flaky 確認**。

**P1 portfolio-resting focused（8 expected: 7 既有 + 1 新）**：
```
$ cargo test --release ... test_p1_portfolio_resting    → 7/0 PASS（既有 family prefix）
$ cargo test --release ... test_resting_entry_qty_correlated_pair_blocks_oversize → 1/0 PASS
```

**所有 8 個 P1 portfolio test PASS**（其中新 1 個 `test_resting_entry_qty_correlated_pair_blocks_oversize` 與既有 7 個共存無命名空間衝突）。

---

## §3 cargo check Mac aarch64-apple-darwin

```
$ cd /Users/ncyu/Projects/TradeBot/srv/rust && cargo check --release --target aarch64-apple-darwin -p openclaw_engine --lib
warning: unused import: `super::LEAD_WINDOW_SECS_MAIN`   # pre-existing W2 sibling
warning: method `make_intent` is never used             # pre-existing ma_crossover dead code
warning: `openclaw_engine` (lib) generated 2 warnings
    Finished `release` profile [optimized] target(s) in 8.01s
```

**0 error**，2 pre-existing warning（per E1 §5 已記錄與本 IMPL 無關）。✅

---

## §4 Baseline 對照

| 項 | Linux value | 計算 |
|---|---|---|
| Linux full `--lib --release` | **2918 passed / 0 failed / 1 ignored** | run1 0.64s / run2 0.65s 非 flaky |
| 9980448a baseline（per E2 §1 race #4） | 2915 passed / 0 failed / 1 ignored | — |
| 9980448a → ad5e609e 期間 commit chain | `3b055c98 (F-09 model_tier + [68] healthcheck)` → `ad5e609e (B-4 +82 LOC)` | — |
| delta 全 attribution | 2915 → +2 (3b055c98 risk_config_tests F-09 model_tier) = 2917 → +1 (B-4 supplement) = **2918** ✅ | 0 unexplained delta |
| Mac (per E1 §5) | 2930 / 0 / 1 ignored | Mac+Linux 差 12 = dev_disabled secret slot + platform-specific tier diff（per CLAUDE.md §七 Mac dev-only）|

**0 regression**（pre-existing failed 維持 0；passed 增加 +3 全 attributed；ignored 維持 1 = socket-permission 預期）。

---

## §5 Race protocol 5 條

| # | check | 結果 |
|---|---|---|
| 1 | sibling 並行驗 | PASS — sibling Phase 1b 14 dirty file 全在 `tick_pipeline / event_consumer / strategies / database / passive_wait_healthcheck`，**0 命中 `intent_processor/`**。Linux main worktree 0 dirty，scratch 隔離 N/A（直接走 main 即可）。 |
| 2 | dirty file overlap check | PASS — Mac dirty list `intent_processor/tests.rs` 不在裡面（已 land 進 `ad5e609e`），sibling 全在不重疊路徑。 |
| 3 | test baseline 來源 | PASS — 9980448a Linux 2915 baseline + 3b055c98 +2 F-09 test + ad5e609e +1 B-4 supplement = 2918；全 delta attribute 明確，無 unexplained 增減。 |
| 4 | 跨平台一致性 | PASS — Linux 2918 vs Mac 2930 差 12 = `dev_disabled_*` 3 個 secret slot fail-closed test + platform-specific tier diff（per CLAUDE.md §七 + `feedback_v_migration_pg_dry_run.md` cross-OS expectation）。Mac aarch64 cargo check release 0 error。 |
| 5 | test isolation | PASS — intent_processor module 135/0/0 跑 0.01s（內無 IPC/PG/external IO 依賴），新 test 純 `PaperState::new(10_000.0)` + `IntentProcessor::compute_*` + `risk_checks::check_order_allowed` self-contained，sibling Phase 1b source 即使編譯失敗也不退化本 test 行為。 |

**§5 結論**：5 條全 PASS。

---

## §6 Verdict

### **REGRESSION-PASS → PM commit/push READY**

- **數字**：Linux full `--lib --release` 2918/0/1（雙跑非 flaky）vs baseline 9980448a 2915/0/1 → delta +3 全 attribute（F-09 +2 + B-4 +1）✅
- **新 1 test**：`test_resting_entry_qty_correlated_pair_blocks_oversize` Linux + Mac 雙端 PASS ✅
- **既有 7 P1 portfolio test**：Linux 100% PASS ✅
- **Mock 審查**：新 test 0 mockall / 0 fake / 0 patch，純 real `PaperState` + real `IntentProcessor::compute_*` + real `risk_checks::check_order_allowed`，業務邏輯 100% 真跑（per regression-testing-protocol §5）✅
- **跨平台**：Mac aarch64 cargo check 0 error，2 pre-existing warning 與本 IMPL 無關 ✅
- **SLA**：unit test scope，hot-path N/A（新 test 是端對端 gate chain 整合，非 tick hot path）
- **Cross-language consistency**：N/A（intent_processor 是 Rust SSoT，無 Python dual implementation）

### Advisory（給 PM commit 時 ledger 記）

1. ad5e609e 已 land 在 origin/main HEAD，本 E4 regression 純驗證已 committed code，PM 不必再 commit；同 ticket TODO.md 標 `test coverage hardened` 即可（per E1 §7 選項 A + E2 A-1）。
2. tests.rs 1875/2000（餘 125 LOC），近 cap；下一輪補測前可拆 `tests_p1_portfolio_resting.rs` + `include!`（E2 A-2 / E1 §6 / 已開 `P2-PORTFOLIO-RESTING-TEST-COVERAGE` ticket）。
3. Sibling Phase 1b 由 sibling 自己 E4 chain 驗證，本 report 不涉。

---

**E4 REGRESSION DONE: PASS** · report path: `srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-16--p1_portfolio_resting_exposure_1_supplement_e4_regression.md`
