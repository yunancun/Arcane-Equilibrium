# E4 Regression — W7-3 emergency 1-tick defense · HEAD `d8697c41` · 2026-05-10

> 角色：E4 Test Engineer (W7-3 emergency 補丁式)
> 對象：ma_crossover.on_rejection duplicate_position sync (commit `d8697c41`)
> E1 sign-off: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w7_3_emergency_1tick_defense.md`
>
> **Verdict: PASS** — W7-3 fix 雙端雙跑 deterministic identical · 0 regression · 4 W7-3 unit test 全 PASS · E4 加 1 SLA pressure test PASS · engine binary build clean · 可進 deploy（PM 決定時機）

---

## §1 Verdict

**PASS** — Sprint W7-3 emergency 1-tick defense 全 fix verified · 0 新 regression · cargo lib + ma_crossover focused subset 雙端 (Mac + Linux) 雙跑 deterministic identical · pytest 5 fail 全為 pre-existing + 1 sibling-session swap · cross-language float consistency 不適用（純 string parsing）· 可進 deploy (PM 決定 restart 時機)。

---

## §2 Cargo workspace baseline (Mac + Linux 雙端 + 雙跑)

| Engine | Mac round 1 | Mac round 2 | Linux round 1 | Linux round 2 | W2 third-pass baseline | delta | identical | verdict |
|---|---:|---:|---:|---:|---:|---|---|---|
| openclaw_engine lib (W7-3 only, HEAD `d8697c41`) | **2639 / 0** | **2639 / 0** | **2639 / 0** | **2639 / 0** | 2639 / 0 | unchanged | yes | **PASS** |
| ma_crossover focused (含 4 W7-3 new test) | **58 / 0** | n/a | **58 / 0** | n/a | n/a (W2 沒分 subset) | n/a | yes | **PASS** |
| openclaw_engine lib (W7-3 + E4 SLA test, unstaged Mac) | **2640 / 0** | **2640 / 0** | n/a (unstaged) | n/a | 2639 / 0 | **+1 PASS** | yes | **PASS** |
| ma_crossover focused (W7-3 + E4 SLA test) | **59 / 0** | n/a | n/a | n/a | 58 | **+1 PASS** | yes | **PASS** |
| Mac engine binary `cargo build --release --bin openclaw-engine` | **0 errors / 2 pre-existing dead_code warning** | n/a | n/a | n/a | clean | unchanged | yes | **PASS** |

**雙端 bit-exact 對齊**：Mac (`darwin`) + Linux (`trade-core`) 同 commit `d8697c41`，cargo lib 全 release test 雙跑 deterministic identical。

### 2.1 W7-3 4 unit test acceptance (E1 IMPL DONE 對齊)

```
test strategies::ma_crossover::tests::test_on_rejection_duplicate_position_already_long_syncs_position ... ok
test strategies::ma_crossover::tests::test_on_rejection_duplicate_position_already_short_syncs_position ... ok
test strategies::ma_crossover::tests::test_on_rejection_non_duplicate_position_runs_full_rollback ... ok
test strategies::ma_crossover::tests::test_on_rejection_unknown_duplicate_format_fallback_to_rollback ... ok
```

雙端 Mac + Linux 全 PASS deterministic identical (release 模式 0.00s)。

### 2.2 E4 新增 SLA pressure test

`test_on_rejection_duplicate_position_burst_no_panic_no_hang` (+41 LOC pure test scope at `tests.rs:809-846`)：

- **場景**：1000 次 on_rejection burst with reason `"duplicate_position: INXUSDT already SHORT 1810"` (模擬 INXUSDT 11:34 hot loop 1min 2319 reject 縮量回放)
- **驗證 1**：HashMap stays size=1 (O(1) update 不累積，防 hot loop hashmap leak)
- **驗證 2**：終態 `positions[INXUSDT] = Some(false)` (last reason direction sticks)
- **驗證 3**：wall-clock < 100ms (Mac release 實測 0ms / 100ms 為 CI 噪音 headroom)
- **實測**：Mac `cargo test --release` PASS in 0.00s

**Status**：unstaged at Mac，留 PM 決定 (按 task §邊界「不 deploy」)。PM 可選：
- (a) 併入 W7-3 主 commit chain
- (b) 單獨 `[skip ci]` commit
- (c) 拒絕加入 (W7-3 emergency 補丁不需 SLA test)

---

## §3 Pytest baseline (Linux full 3-dir scope, W2 third-pass scope)

| pytest | passed | failed | skipped | runtime | match W2 third-pass |
|---|---:|---:|---:|---:|---|
| Linux `tests/` + `control_api_v1/tests/` + `ml_training/tests/` | **4744** | **5** | **41** | 81.99s | yes (count + skip identical) |

5 fail 名單對比 W2 third-pass：

| Fail | W2 third-pass | Now | Status |
|---|---|---|---|
| `test_archive_top_level_files_are_all_indexed` | ✓ pre-existing | ✓ | unchanged |
| `test_oe_006_close_retry_budget_has_real_timeout_guard` | ✓ pre-existing | ✓ | unchanged |
| `test_grafana_data_writer.test_start_sets_running` | ✓ pre-existing leader lock | ✓ | unchanged |
| `test_case2_pg_kill_simulation_returns_200_degraded` | ✓ pre-existing | ✓ | unchanged |
| `test_ci_workflow_runs_release_cargo_check_for_openclaw_engine` | ✓ sibling commit `0dc6d659` | n/a | **swapped out** (PM follow-up: 是否 sibling 已修復？) |
| `test_f08_wrapper_invokes_runner_with_all_jobs` | n/a | NEW | **swapped in** (sibling commit `268f9470/da2aba11` audit ml cron 引入；fixture 缺 MOCK_ML_DSN 注入；**非 W7-3 引入**) |

**Sibling-session catalog** (PM follow-up，不阻 W7-3 PASS verdict):
- swap-out: `test_github_ci_workflow_static.py` (W2 third-pass `0dc6d659`)
- swap-in: `test_ml_training_maintenance_cron_static.py::test_f08_wrapper_invokes_runner_with_all_jobs` (commits `268f9470/da2aba11`)

W7-3 source code 改動 (commit `d8697c41`) 範圍**僅** `rust/openclaw_engine/src/strategies/ma_crossover/{strategy_impl.rs, tests.rs}`，0 Python source 改動，故 pytest 5 fail 名單 swap 與 W7-3 commit 因果無關。

---

## §4 SLA pressure test 結果

| Path | implementation | iterations | wall-clock | invariant 1 (HashMap size) | invariant 2 (終態 direction) | invariant 3 (panic) | verdict |
|---|---|---:|---:|---|---|---|---|
| `MaCrossover::on_rejection` (W7-3 duplicate_position branch) | release | 1000 | **0ms (Mac release)** | size=1 (O(1) ✓) | `Some(false)` ✓ | 0 panic ✓ | **PASS** |

**核心 invariant**：1000 次同 symbol burst 後 `positions.len() == 1` (防未來 refactor 把 HashMap insert 換成 Vec push 引入 O(n) leak)。

---

## §5 Engine binary build 結果

```
$ cd rust && cargo build --release --bin openclaw-engine
warning: function `reconciler_label_for_env` is never used
warning: `openclaw_engine` (bin "openclaw-engine") generated 2 warnings
    Finished `release` profile [optimized] target(s) in 23.97s (first build) / 0.10s (incremental)
```

**Build clean** — 0 errors / 2 pre-existing dead_code warning（與 W2 third-pass baseline 一致，非 W7-3 引入）。

---

## §6 Cross-language float consistency

W7-3 fix 純 **string parsing** + **HashMap insert** + **control flow** — 不影響 float。**不適用** 1e-4 容差 verify (E4 邊界 §4.6 cross-language consistency 對 indicator/calculator 才有意義；on_rejection 是 control flow path)。

| Verify | scope | result |
|---|---|---|
| Python pytest `-k "ma_crossover"` (Mac) | 1 test (test_strategy_init.py) | **1/1 PASS in 0.09s** |
| Python ↔ Rust IPC 調用 on_rejection? | 否 (on_rejection 是 Rust-internal callback；Python 端無對應 path) | n/a |

---

## §7 Reason 字串契約 audit

`rejection_coding.rs:55-152` `RejectionCode::DuplicatePosition` format = `"duplicate_position: {symbol} already {LONG|SHORT} {qty}"` byte-identical to ma_crossover W7-3 parsing：

| 設計 | E1 IMPL | E4 acceptance |
|---|---|---|
| `reason.contains("duplicate_position")` 而非 `starts_with()` | ✓ | 防 prefix prepend (e.g. metric tag) — 合規 |
| `reason.contains("already LONG")` / `reason.contains("already SHORT")` | ✓ | direction 解析 byte-identical |
| Contract drift fallback：含 `duplicate_position` 但無 `already LONG/SHORT` → tracing::warn + RC-04 prev_position rollback | ✓ | `test_on_rejection_unknown_duplicate_format_fallback_to_rollback` cover |
| Non-duplicate rejection (cost_gate / risk_gate) → RC-04 完整 rollback (positions + cooldown) | ✓ | `test_on_rejection_non_duplicate_position_runs_full_rollback` cover |

---

## §8 Trait `Strategy` on_rejection signature consistency

| Strategy file | signature | impact from W7-3 |
|---|---|---|
| trait default `mod.rs:106` | `_intent: &OrderIntent, _reason: &str` (default no-op) | unchanged |
| `ma_crossover/strategy_impl.rs:55` | `intent: &OrderIntent, reason: &str` (W7-3) | underscore 拿掉合規 (impl 端覆寫可去 underscore) |
| `bb_breakout/mod.rs:347` | `intent: &OrderIntent, _reason: &str` | unchanged |
| `bb_reversion/mod.rs:345` | `intent: &OrderIntent, _reason: &str` | unchanged |
| `funding_arb.rs:356` | `intent: &OrderIntent, _reason: &str` | unchanged (策略已 retire per ADR-0018) |
| `grid_trading/mod.rs:345` | `intent: &OrderIntent, reason: &str` | unchanged (first opener，無 W7-3 場景) |

**Trait contract clean** — 0 sibling strategy 受影響。

---

## §9 W7-4 systemic fix scope inventory (留給 PA #3 Option A / W-AUDIT-8a)

5 策略 (`ma_crossover` / `bb_breakout` / `bb_reversion` / `funding_arb` / `grid_trading`) 都有 `on_rejection` impl + `self.positions: PerSymbolState<bool>` 各自 buffer。當前 W7-3 補丁僅 ma_crossover；其他策略遇 grid_trading 同 symbol 先開倉時仍可能撞 router gate 1.5 hot loop（W6 baseline 沒看到只因 signal 沒對齊）。W-AUDIT-8a Option A 治本路徑 = TickContext 加 `paper_state` reference 升 5 策略 signature 一次性對齊。**E4 不 dispatch**，僅紀錄。

---

## §10 是否可進 deploy

**可進 deploy — PM 決定 restart 時機**。

按 PA W7-3 deploy SOP 建議：
1. PM 統一 commit chain (E1 IMPL `d8697c41` 已 land；E4 SLA test 留 PM 決定加不加)
2. ssh trade-core `restart_all.sh --rebuild --keep-auth`
3. 30min observation watch INXUSDT ma_crossover risk_verdicts duplicate_position rate (應立即降至 ≤ 1/min/symbol)
4. Rollback plan：`git revert d8697c41 && --rebuild --keep-auth` (純 1 commit revert，0 schema migration，純 Rust 改動)

**Acceptance scope**：本 E4 verdict 僅 verify source code land + lib test + SLA test PASS + engine binary build clean。Runtime hot loop 真實終結 (INXUSDT 11:34 hot loop fix verify) 是 PM operational concern，需 deploy 後 30min observation 才 verify (per PA W7-3 deploy SOP)。

---

## §11 不確定之處 / Push back

1. **Sibling-session pytest fail name swap 不阻 W7-3 PASS** — `test_f08_wrapper_invokes_runner_with_all_jobs` 是 sibling commits `268f9470/da2aba11` (ml training cron audit) 引入的 fixture issue，**非 W7-3 引入**。但建議 PM 後續 dispatch 處理（標 P2 housekeeping）。
2. **E4 SLA test commit 決策權** — 留 PM 決定要不要併入 commit chain。E4 不獨立 push (per task §邊界「不 deploy」)。
3. **W7-4 systemic 5-strategy fix scope** — PA #3 Option A / W-AUDIT-8a 未 dispatch；建議 PM 在 W6 baseline 看到 bb_breakout / bb_reversion 同類 hot loop 之前先 dispatch (預防勝於治療)。

---

**E4 REGRESSION DONE: PASS · report path: `srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-10--w7_3_regression.md`**

Cargo workspace baseline (Mac + Linux 雙跑 deterministic): cargo lib **2639 / 0** unchanged · ma_crossover focused **58 / 0** (含 4 W7-3 new test) · 加 E4 SLA test 後 Mac **2640 / 0** + ma_crossover **59 / 0** · pytest **4744 / 5 fail** (5 fail 全為 pre-existing 4 + sibling-session 1，非 W7-3 引入) · engine binary build **0 errors / 2 pre-existing warning**。
