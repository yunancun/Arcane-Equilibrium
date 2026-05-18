# E4 Regression Report — 2026-05-18 13-task cleanup sprint (4 E1 batches + 4 PM inline edits)

- **Branch**: working tree (uncommitted)
- **Base**: main HEAD `8d2b2866 docs(todo): v49 → v50 — W-AUDIT-8c Stage 0R tooling merged + 三端同步`
- **Date**: 2026-05-18 (Mac M-series, release profile)
- **Scope**:
  - Rust: `intent_processor` mod/router/tests +50/+19/+45 LOC + new bench 178 LOC + Cargo.toml +7
  - Rust `openclaw_core`: stochastic_prior +57 LOC + indicators/mod.rs +1 + lib.rs -7 + **DELETE 7 dead modules −3616 LOC**
  - Python: perception DeprecationWarning + 3 test filterwarnings + 8 control_api files reason_code cleanup (23×)
  - SQL: new `V096__drop_dead_learning_tables.sql` (RESTRICT + Guard A/B + idempotent DO $$)
  - GUI: `trading.html` SRI integrity hash add
  - Tests: new `test_v096_drop_dead_learning_tables.py` 22 + `test_cron_heartbeat_healthchecks.py` 42 + intent_processor tests +1 + momentum +1
  - Skill / config / docs / cron wrappers

---

## §0 Verdict

**REGRESSION-PASS → pass to PM commit**

| 維度 | 結果 |
|---|---|
| cargo openclaw_engine --lib | 2993/0/1 ✅ (= task brief baseline) |
| cargo openclaw_core --lib | 357/0/0 ✅ (446 pre-PR – 90 retired tests + 1 stochastic_prior; explicit dead-module retirement, NOT silent deletion) |
| cargo openclaw_engine --tests (integration) | 33/2 ✅ (2 pre-existing fails identical signature pre-PR ↔ post-PR) |
| V096 + cron heartbeat new tests | **64/64** ✅ |
| 3 perception tests (DeprecationWarning) | **107/107** ✅ |
| 8-file wider batch (risk/strategist_promote/edge/live_session/live_trust/paper_trading/strategy_ai/layer2) | 421/3 ✅ (same 3 pre-existing fails confirmed via pre-PR stash probe — wider-batch test pollution) |
| Mock anti-pattern audit | 0 hit (new test uses real production helpers + 1e-4 tolerance) ✅ |
| bash -n × 6 (5 cron wrappers + compute_sri_hashes.sh) | 6/6 PASS ✅ |
| HTML parse trading.html | OK (674 lines, no parse error) ✅ |
| 2nd run non-flaky verification | all identical × 2 ✅ |
| Cross-language float consistency | N/A — no Python ↔ Rust shared compute introduced this sprint |

**0 BLOCKER · 0 new regression · 0 silent test deletion**

---

## §1 cargo test --release per crate

```
$ cd /Users/ncyu/Projects/TradeBot/srv/rust && cargo test --release -p openclaw_engine --lib
test result: ok. 2993 passed; 0 failed; 1 ignored; 0 measured; 0 filtered out; finished in 0.70s

$ cargo test --release -p openclaw_core --lib
test result: ok. 357 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.01s
```

### Delta attribution (critical — task brief discrepancy resolved)

| Crate | Pre-PR baseline (stash probe) | Post-PR actual | Delta | Attribution |
|---|---|---|---|---|
| openclaw_engine --lib | 2992 (per `2026-05-18--phase_1b_calibration_timeout_90s_e4_regression.md`) | 2993 | +1 | Batch A's `test_p2_portfolio_resting_multi_close_summed_capped_at_filled` ✅ |
| openclaw_core --lib | **446** (`git stash` + cargo test) | 357 | **−89** | 7 retired modules contributed **90 tests** + 1 new `stochastic_prior` = net −89 ✅ |

#### Retired-module test attribution (sum = 90)
| Deleted module | Tests removed |
|---|---|
| attention | 11 |
| attribution | 10 |
| cognitive | 13 |
| dream | 20 |
| message_bus | 7 |
| opportunity | 18 |
| order_match | 11 |
| **Sum** | **90** |

446 − 90 + 1 = **357** ✅ exact match. Each retired test belongs to an explicitly retired dead module marked in `rust/openclaw_core/src/lib.rs`. **No silent test deletion**.

> Task brief wrote "openclaw_core previously 399/0/1 after Batch B +1" — that number does **not** account for the same-sprint 7-module retirement (-90). The true delta is `(446 → 357) = −89`, not `(399 → ???) = +1`. E4 trusts the empirical stash probe over brief-written numbers per regression-testing-protocol §1.

---

## §2 Integration tests (`cargo test --release -p openclaw_engine --tests`)

```
test result: FAILED. 33 passed; 2 failed; 0 ignored; 0 measured
failures:
    stress_bb_breakout_valid_squeeze_with_volume
    stress_bb_reversion_extreme_oversold_bounce
```

### Pre-existing failure signature verification (stash probe)

| Test | Line | Assertion | Pre-PR (stash) | Post-PR | Match? |
|---|---|---|---|---|---|
| `stress_bb_breakout_valid_squeeze_with_volume` | 536 | `left: 0, right: 1` "should enter on valid squeeze breakout" | FAILED | FAILED | ✅ identical |
| `stress_bb_reversion_extreme_oversold_bounce` | 483 | `left: 0, right: 1` "should exit at mean reversion" | FAILED | FAILED | ✅ identical |

**33 passed / 2 failed both pre-PR and post-PR** — 0 new fail. These match the task brief statement "2 pre-existing stress test fails confirmed on clean main `8d2b2866` (NOT PR-introduced)".

---

## §3 Pytest — new test files

```
$ pytest helper_scripts/db/test_v096_drop_dead_learning_tables.py helper_scripts/db/test_cron_heartbeat_healthchecks.py -v
64 passed in 0.05s
```

| File | Tests | Result |
|---|---|---|
| `helper_scripts/db/test_v096_drop_dead_learning_tables.py` | 22 | 22/22 PASS |
| `helper_scripts/db/test_cron_heartbeat_healthchecks.py` | 42 | 42/42 PASS |

2nd run identical (64/64 in 0.05s).

---

## §4 Pytest — 3 perception tests

```
$ pytest test_perception_data_plane.py test_integration_phase2.py test_batch9_perception_analyst_integration.py -v
107 passed, 13 warnings in 0.32s
```

DeprecationWarnings emitted (expected — they come from production callsite emitting the new warning) but the `pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning:app.perception_data_plane")` setup in test files filters warnings sourced from `app.perception_data_plane` module while still allowing tests to run. The shown warnings actually come from the **test file's own** `validate_for_decision` call lines (test files exercise the deprecated path on purpose). This is the correct semantic — production callers are 0, tests are exempt. **No PASS/FAIL impact**.

2nd run identical (107/107 in 0.25s).

---

## §5 Wider batch (8 cleaned-up Python files coverage)

```
$ pytest -k "risk or strategist_promote or edge_estimator or live_session or live_trust or paper_trading or strategy_ai or layer2"
3 failed, 421 passed, 3716 deselected, 48 warnings in 11.28s
```

### Stash probe — pre-PR baseline same batch

```
$ git stash push -- program_code/.../app/ && pytest <same -k filter>
3 failed, 421 passed, 3716 deselected, 48 warnings in 10.79s
```

| Failing test | Pre-PR (stash) | Post-PR | Match? |
|---|---|---|---|
| `tests/static/test_replay_subtab_static_assets.py::test_demo_and_live_tabs_have_risk_shortcuts` | FAILED | FAILED | ✅ pre-existing |
| `tests/test_phase2_strategy_routes_coverage.py::TestDynamicRiskRoutes::test_status_no_deployer` | FAILED | FAILED | ✅ pre-existing (PASSES in isolation — test pollution in wider batch) |
| `tests/test_phase2_strategy_routes_coverage.py::TestDynamicRiskRoutes::test_status_happy` | FAILED | FAILED | ✅ pre-existing (PASSES in isolation — test pollution in wider batch) |

**0 new fail introduced by this sprint**. Note: when `TestDynamicRiskRoutes` tests are run in isolation `pytest <file>::TestDynamicRiskRoutes -v` they PASS — confirming it is wider-batch test pollution (cross-test fixture / module state leak), an orthogonal pre-existing issue. Cleanup tracked as separate work; **not a blocker for this commit**.

> Task brief said "213 pass / 3 pre-existing fail baseline" — actual wider-batch count is **421/3** (larger scope), but the same 3 failures, all pre-existing per stash probe. The 213 figure may have been from a narrower `-k` filter; the verification logic still holds.

2nd run identical (3 fail / 421 pass).

---

## §6 Mock anti-pattern audit

New test `test_p2_portfolio_resting_multi_close_summed_capped_at_filled` (`rust/openclaw_engine/src/intent_processor/tests.rs:1875-1917`):

| Mock vector | Status |
|---|---|
| `PaperState::new(10_000.0)` | **real** production constructor ✅ |
| `state.set_latest_price("BTC", 50_000.0)` | **real** production method ✅ |
| `state.import_positions(...)` | **real** production method ✅ |
| `seed_resting(&mut state, ...)` | **real** test helper using production state mutation ✅ |
| `IntentProcessor::compute_effective_long_short_notional(&state)` | **real** production helper under test ✅ |
| `IntentProcessor::compute_exposure_pct(&state)` | **real** production helper ✅ |
| `IntentProcessor::compute_correlated_exposure_pct(&state)` | **real** production helper ✅ |
| External IO (HTTP/PG/file) | None — pure in-memory state ✅ |

**0 mock of business logic**. Assertions use `< 1e-4` float tolerance. This is exactly the regression-testing-protocol §5.2 correct pattern — mock IO boundary (none here), exercise real business logic.

---

## §7 bash -n + HTML parse

```
$ for f in helper_scripts/cron/{blocked_symbols_30d_unblock_check,feature_baseline_writer,panel_aggregator_health,replay_key_rotation_check,wave9_replay_no_live_mutation_watch}*.sh helper_scripts/security/compute_sri_hashes.sh; do bash -n "$f"; done
all 6 PASS

$ python3 -c "from html.parser import HTMLParser; HTMLParser().feed(open('.../trading.html').read())"
HTML parse OK, 674 lines, no parse error
```

---

## §8 Cross-language float consistency

**N/A this sprint** — no Python ↔ Rust shared computation introduced. `compute_effective_long_short_notional` is Rust-only; Python only passes intent payload via IPC. The 1e-4 tolerance is applied internally to Rust test assertion (eff_long, eff_short = 0 ± 1e-4) ✅.

Stochastic indicator: `stochastic_prior` is the new Rust leak-free variant. Confirmed in source the test `test_stochastic_prior_excludes_current_bar` directly compares against `stochastic` (leaky) in the same Rust code path — both Rust-side, no Python counterpart. No cross-language consistency check required this sprint.

---

## §9 Non-flaky verification

| Test set | 1st run | 2nd run | flaky? |
|---|---|---|---|
| cargo openclaw_engine --lib | 2993/0/1 in 0.70s | 2993/0/1 in 0.70s | N |
| cargo openclaw_core --lib | 357/0/0 in 0.01s | 357/0/0 in 0.01s | N |
| V096 + cron heartbeat | 64/64 in 0.05s | 64/64 in 0.05s | N |
| 3 perception tests | 107/107 in 0.32s | 107/107 in 0.25s | N |
| Wider 8-file batch | 421/3 in 11.28s | 421/3 in 10.58s | N |

---

## §10 Boundary / cross-PR deferrals

- New bench `intent_processor_exposure.rs` — `cargo build --release --bench intent_processor_exposure` PASS. Not run as bench (bench output belongs to E5 micro-bench scope, not E4 regression).
- V096 migration source/test landed; **apply to Linux PG is operator-gated downstream** (not E4 scope).
- 5 cron wrappers `touch sentinel` line added; **installation in Linux crontab is P1-CRON-INSTALL-WAVE-1 next step** (separate operator action).

---

## §11 BLOCKER / MUST-FIX / NTH

- **0 BLOCKER**
- **0 MUST-FIX**
- **NTH (P2, not blocking this commit)**: 2 `TestDynamicRiskRoutes` tests show wider-batch test pollution (pass in isolation, fail when batched with risk/strategist tests). Pre-existing; not introduced by this sprint. Suggest separate cleanup PR to identify and fix the fixture / module-state leak. Reference: file `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_phase2_strategy_routes_coverage.py::TestDynamicRiskRoutes` lines 1-50.

---

## §12 Final verdict

**E4 REGRESSION PASS → pass to PM commit**

All required validations completed:
1. ✅ cargo test counts ≥ baseline (engine +1, core −89 fully attributed to dead-module retirement, NOT silent deletion)
2. ✅ pre-existing fails identical signatures (2 Rust stress + 3 Python wider-batch pollution)
3. ✅ no new regression introduced
4. ✅ mock anti-pattern audit clean (real helpers used)
5. ✅ shell scripts + HTML all parse
6. ✅ 2nd-run non-flaky verification confirmed
7. ✅ no silent test deletion (every −1 attributed)
