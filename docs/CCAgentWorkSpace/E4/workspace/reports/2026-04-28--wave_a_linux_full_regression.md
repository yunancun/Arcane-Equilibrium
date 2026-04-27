# E4 Regression Test Report — Wave A prep-gate trio Linux full regression

**Date**: 2026-04-28
**HEAD**: `528805d` (origin/main)
**Scope**: Linux full regression for Wave A 4 commits
**Verdict**: **PASS** (0 regression, 兩遍同綠 non-flaky, healthcheck 27 PASS / 1 WARN pre-existing / 0 FAIL)

---

## 1. 改動範圍 (commits `82347a5..528805d` = 4)

| Commit | Type | Files | Tests added |
|---|---|---|---|
| `aced662` | Python | analyst + strategist + strategy_wiring + new test 8 cases | +8 (G8-01 FUP losses-wiring) |
| `9303a3b` | Rust | mod.rs (daemon body) + advisor.rs (doc) + types.rs + 2 sticky tests | +2 (G3-09 sticky_triggered_at_ms) |
| `22c57dc` | Rust | test_cost_edge_advisor_daemon.rs (3 cases A/B/C) | +3 (G3-09 spawn-test FUP) |
| `528805d` | Docs | cross-agent memory updates | 0 |

**Production code 改動**：
- Python: `analyst_agent.py` + `strategist_agent.py` + `strategy_wiring.py` (W1 cognitive modulator consecutive_losses 接線)
- Rust: `cost_edge/mod.rs` daemon body (sticky_triggered_at_ms persist across contiguous trigger cycles) + `cost_edge/types.rs` (新欄位)

**E2 已驗**：sticky-ts 改 mod.rs daemon body 屬 production code 但 Phase A advisory-only 路徑 0 trade impact (env=0 dormant)。

---

## 2. Linux Test 結果 (兩遍同綠 non-flaky)

### 2.1 Rust cargo lib (--release)

```
test result: ok. 2290 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.52s
```

| Run | passed | failed | baseline | delta |
|---|---|---|---|---|
| 1st | 2290 | 0 | 2290 | 0 |
| 2nd | 2290 | 0 | 2290 | 0 |

✅ sticky-ts production diff 對 lib test 0 影響（Phase A 路徑 advisory-only）

### 2.2 Rust daemon integration test (test_cost_edge_advisor_daemon)

```
test result: ok. 11 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 2.09s
```

| Run | passed | failed | baseline | delta |
|---|---|---|---|---|
| 1st | 11 | 0 | 6 (Phase A) | +5 |
| 2nd | 11 | 0 | 6 (Phase A) | +5 |

**11 tests 詳列**:
1. `daemon_spawn_advances_state_off_uninitialized` (Phase A baseline)
2. `ipc_handler_returns_live_state_after_daemon_writes` (Phase A baseline)
3. `dual_safeguard_env_gate_off_skips_daemon` (Phase A baseline)
4. `dual_safeguard_risk_config_disabled_short_circuits` (Phase A baseline)
5. `daemon_evaluate_cadence_within_tolerance` (Phase A baseline)
6. `daemon_cancellation_drains_within_one_second` (Phase A baseline)
7. **`sticky_triggered_at_ms_records_first_entry_into_trigger`** (NEW · 9303a3b)
8. **`sticky_triggered_at_ms_preserved_across_contiguous_trigger_cycles`** (NEW · 9303a3b)
9. **`fup_case_a_env_unset_keeps_slot_none_and_ipc_uninitialized`** (NEW · 22c57dc)
10. **`fup_case_b_env_set_risk_disabled_slot_some_ipc_disabled`** (NEW · 22c57dc)
11. **`fup_case_c_env_set_risk_enabled_slot_some_ipc_live_state`** (NEW · 22c57dc)

✅ math 對齊 PA RFC §6.1 R-B4 + R-B10 缺口補完

### 2.3 Python pytest combined Wave A suite (7 modules)

```
199 passed, 5 warnings in 0.29s
```

| Run | passed | failed | Mac local | Linux delta |
|---|---|---|---|---|
| 1st | 199 | 0 | 86 | +113 (Linux env collects more cases) |
| 2nd | 199 | 0 | 86 | +113 |

**Linux > Mac 解讀**:
- PA 報的「Mac 8 fastapi pre-existing failures」屬 Mac dev-only env (CLAUDE.md §七 dev_disabled secret slots)
- Linux env 完整，0 fastapi failures，所有 7 suite 全 collect → 199
- 5 warnings = `record_ollama_call()` DeprecationWarning (pre-existing, not Wave A regression)

✅ Mac 86 → Linux ≥86 預期達成（199 fully expected per env diff）

### 2.4 Healthcheck full sweep

**27 PASS / 1 WARN / 0 FAIL**

WARN [11]: `counterfactual_clean_window_growth post-P013-clean n_rows=226/200 (113%), rate=95rows/2d, ETA ~0d` — pre-existing observation pacing rule，已過 200 rows 但 healthcheck cron 6h 一次重評，即將自然 PASS。Wave A 0 因果。

**新 G2-06 / G3-08 / G3-09 / G7-09c 相關 check 全 PASS**:
- `[18] disabled_strategy_inventory`: `bb_breakout, funding_arb (active count=3: bb_reversion, grid_trading, ma_crossover)` ✓
- `[20] h_state_gateway_freshness`: `OPENCLAW_H_STATE_GATEWAY=unset env=0 dormant by design` ✓
- `[30] cost_edge_advisor_status`: `OPENCLAW_COST_EDGE_ADVISOR=unset env=0 dormant by design (Phase A: 0 trade impact)` ✓
- `[Xa] leader_election_health`: `leader_pid=3090462 alive, lock_age=9.5h` ✓
- `[7] edge_estimates_freshness`: `populated 231/231 (100.0%)` ✓
- `[14] exit_features_accumulation_rate`: `READY_frac=92% of this_week` ✓

✅ 0 FAIL · WARN [11] 與 Wave A 改動無因果

---

## 3. Mock 審查

N/A — 純跑既有測試 + 0 production diff in this E4 run。

新 daemon integration tests (Phase A 已審 + sticky/spawn FUP) 均直驅 `evaluate()` pure fn + 真 `spawn_cost_edge_advisor()` 走 tokio runtime，0 mock 業務邏輯（mock 安全規則 §5.1/§5.2 全綠，與 2026-04-27 Phase A E4 報告同檔）。

---

## 4. 浮點一致性 / SLA 壓測

不適用（本 wave 0 indicator 改動 + 0 hot path 改動）。

---

## 5. 跑兩遍結果（flaky 檢驗）

| Engine | 1st run | 2nd run | flaky? |
|---|---|---|---|
| Rust lib (--release) | 2290/0 in 0.52s | 2290/0 in 0.52s | **N** ✓ |
| Rust daemon integration | 11/0 in 2.09s | 11/0 in 2.09s | **N** ✓ |
| Python pytest combined | 199/0 in 0.29s | 199/0 in 0.29s | **N** ✓ |

**結論**：3/3 引擎兩遍同綠 non-flaky。

---

## 6. 結論

**E4 PASS**

- 0 regression（cargo lib 2290/0 不變，daemon test 11/0 = baseline 6 + 5 expected new，pytest 199/0 全綠）
- 0 production diff in this E4 run（純跑測試）
- Healthcheck 27 PASS / 1 WARN pre-existing / 0 FAIL
- Mock 安全：N/A（無新測試）
- 兩遍同綠 non-flaky

**Operator 下一步**：
- 本 wave 累積屬 prep-gate，可待下次 cron `restart_all.sh --rebuild` 一併 deploy（不需立即重啟 engine PID 1319839）
- 若需立即 propagate sticky-ts 到 runtime: `ssh trade-core "bash helper_scripts/restart_all.sh --rebuild"`，但 Phase A advisory-only 0 trade impact，不緊急

**退回 E1 修復清單**：無

---

## 報告 metadata

- 採集時間: 2026-04-28 (Mac SSOT, Linux runtime via ssh trade-core)
- HEAD: `528805d`
- Linux git status: clean, synced to origin/main
- Mac → Linux ssh bridge: trade-core (Tailscale + key auth)
- Cargo: `/home/ncyu/.cargo/bin/cargo` (non-login shell, full path)
- Python: `/usr/bin/python3` + pytest 9.0.2 (system)
- PG: trading_admin@127.0.0.1:5432/trading_ai
