# E4 Full Program-Scope Testing Audit — 2026-05-16

**Auditor**: E4 (Test Engineer)
**Scope**: Cold adversarial audit of entire OpenClaw testing infrastructure
**Type**: Coverage gap inventory (NOT a commit-gating regression)

---

## 0. Executive Summary

The OpenClaw test suite is substantial (2889 Rust lib + 4089 Python control_api_v1 + 413 srv/tests = ~7400 tests) but has significant structural coverage gaps. 30% of Rust production files and 55% of Python app modules have zero dedicated test coverage. Critical trading hot-path code (tick pipeline steps, risk checks, fill engine) relies on indirect testing through integration suites rather than targeted unit tests. No property-based testing exists in the Rust codebase. Cross-language float consistency testing is limited to manifest signing and executor decisions -- no indicator/calculation parity tests exist.

---

## 1. Test Execution Results (Mac dev, dual-pass non-flaky verification)

### 1.1 Rust lib tests

| Run | passed | failed | ignored | runtime |
|---|---|---|---|---|
| Pass 1 | 2889 | 0 | 1 | 0.70s |
| Pass 2 | 2889 | 0 | 1 | 0.69s |

**Verdict**: Non-flaky. 1 ignored = LG1-T3 known gap (h0_shadow_mode propagation).

### 1.2 Rust integration tests (--tests)

| Suite | passed | failed | notes |
|---|---|---|---|
| stress_integration | 33 | 2 | stress_bb_breakout_valid_squeeze + stress_bb_reversion_extreme_oversold |
| All other integration suites | 3047 | 0 | 21 test crates all green |
| **Total** | **3080** | **2** | 2 = pre-existing strategy logic drift |

**Failing tests detail**:
- `stress_bb_breakout_valid_squeeze_with_volume`: `left: 0, right: 1` -- expects 1 entry on valid squeeze breakout, gets 0 entries. Strategy signal logic does not trigger under test fixture conditions.
- `stress_bb_reversion_extreme_oversold_bounce`: `left: 0, right: 1` -- expects 1 exit at mean reversion, gets 0 exits. Same root cause class.

### 1.3 Python srv/tests/

| Run | passed | failed | skipped | runtime |
|---|---|---|---|---|
| Pass 1 | 413 | 1 | 2 | 0.76s |
| Pass 2 | 413 | 1 | 2 | 0.76s |

**Failing test**: `test_v072_feature_baseline_writer_static.py::test_writer_cli_defaults_to_dry_run_and_requires_apply_ack`
- **Cause**: Static guard asserts exact string `--apply requires --i-understand-this-modifies-db` but source was refactored to `rejected flag {arg}: --apply requires the explicit acknowledgement flag`.
- **Severity**: HIGH -- test-source drift; not a code bug but test is stale.

### 1.4 Python control_api_v1 tests

| Run | passed | failed | skipped | collection errors | runtime |
|---|---|---|---|---|---|
| Pass 1 | 4089 | 4 | 8 | 4 | 77.86s |
| Pass 2 | 4089 | 4 | 8 | 4 | 76.42s |

**4 collection errors** (tests that cannot even load):
1. `tests/replay/test_calibration_label_python.py` -- `from program_code...` import fails
2. `tests/replay/test_r6_calibration_e2e.py` -- same
3. `tests/replay/test_r6t6_update_execution_confidence.py` -- same
4. `tests/replay/test_r7_e2e_advisory_integration.py` -- same

**Root cause**: These 4 files use `from program_code.exchange_connectors...` absolute imports. This works from `srv/` root with PYTHONPATH but not from the standard `control_api_v1/` pytest execution directory. These tests have NEVER run in the standard workflow.

**4 failing tests** (pre-existing):
1. `test_replay_subtab_static_assets.py::test_demo_and_live_refresh_preserve_existing_dom_on_transient_loading` -- HTML template drift: expects `if (metricsData) _applyLiveTodayPnl(metricsData)` string in live tab.
2. `test_batch_d_risk_fail_closed.py::test_oe_006_close_retry_budget_has_real_timeout_guard` -- expects `test_close_attempt_timeout_constant_is_500ms` string in dispatch.rs source but string was renamed/removed.
3. `test_replay_routes_safe_query_audit.py::test_case2_pg_kill_simulation_returns_200_degraded` -- intermittent; passed in isolation on re-run.
4. `test_symbol_category_registry.py::TestSymbolCategoryRegistryStale::test_is_stale_initially` -- `SymbolCategoryRegistry()` reports `is_stale()=False` immediately after construction; test expects True.

### 1.5 Cross-language parity tests

| Suite | passed | failed | notes |
|---|---|---|---|
| Rust xlang manifest signer | 8 | 0 | HMAC byte-equal |
| Python bybit_rest_client_parity | 20 | 0 | 70/70 agree (100%) |
| Python executor_decision_parity | (included above) | 0 | shadow_mode agreement |

---

## 2. Coverage Gap Analysis

### 2.1 Rust files with ZERO test coverage (top 20 by LOC)

| File | LOC | Criticality |
|---|---|---|
| `tick_pipeline/on_tick/step_4_5_dispatch.rs` | 1663 | CRITICAL -- order dispatch logic |
| `config/risk_config_advanced.rs` | 1261 | HIGH -- advanced risk config |
| `event_consumer/bootstrap.rs` | 982 | MEDIUM -- startup wiring |
| `main_pipelines.rs` | 981 | MEDIUM -- pipeline wiring |
| `tick_pipeline/pipeline_helpers.rs` | 910 | HIGH -- pipeline utility functions |
| `strategies/strategy_params.rs` | 874 | MEDIUM -- param structs |
| `replay/apply_fill.rs` | 761 | HIGH -- fill application logic |
| `ipc_server/dispatch.rs` | 718 | HIGH -- IPC dispatch |
| `paper_state/fill_engine.rs` | 710 | CRITICAL -- fill simulation engine |
| `tick_pipeline/on_tick/step_0_fast_track.rs` | 636 | CRITICAL -- fast track entry |
| `event_consumer/handlers/risk.rs` | 605 | HIGH -- risk event handling |
| `strategies/bb_breakout/params.rs` | 592 | MEDIUM -- config |
| `tick_pipeline/on_tick/step_6_risk_checks.rs` | 561 | CRITICAL -- risk checks |
| `event_consumer/loop_exchange.rs` | 533 | MEDIUM -- exchange event loop |
| `paper_state/accessor.rs` | 502 | HIGH -- state access |
| `ipc_server/server.rs` | 498 | HIGH -- IPC server |
| `panel_aggregator/btc_lead_lag/producer.rs` | 446 | MEDIUM -- panel data |
| `event_consumer/handlers/edge_predictor.rs` | 446 | HIGH -- edge prediction |
| `agent_spine/events.rs` | 402 | MEDIUM -- spine events |
| `bin/replay_runner/manifest.rs` | 401 | MEDIUM -- replay manifest |

**104 of 342 Rust production files (30%) have no tests.**
Note: some of these are exercised indirectly via integration tests (e.g., fill_engine via paper_state/tests.rs with 54 references), but have no targeted unit tests for their internal logic.

### 2.2 Python app modules with ZERO test file (top 20 by LOC)

| Module | LOC | Criticality |
|---|---|---|
| `governance_hub_live_candidate_review.py` | 1552 | HIGH (has test via different filename) |
| `settings_routes.py` | 1226 | MEDIUM |
| `strategy_ai_routes.py` | 1213 | HIGH -- AI strategy integration |
| `paper_trading_routes.py` | 1188 | HIGH -- paper trading routes |
| `live_trust_routes.py` | 1121 | CRITICAL -- live trust management |
| `risk_routes.py` | 1091 | CRITICAL -- risk management routes |
| `h0_gate.py` | 971 | CRITICAL -- H0 gate logic (tested via 37 refs elsewhere) |
| `agents_routes_helpers.py` | 846 | HIGH |
| `layer2_engine.py` | 840 | HIGH -- L2 AI engine |
| `learning_auto_pipeline.py` | 827 | HIGH -- learning pipeline |
| `governance_hub_cascades.py` | 811 | HIGH -- cascade logic |
| `live_session_account_routes.py` | 789 | HIGH |
| `ai_service_dispatch.py` | 767 | HIGH |
| `strategist_promote_routes.py` | 761 | HIGH |
| `provider_client.py` | 757 | MEDIUM |
| `main.py` | 740 | MEDIUM -- app entry |
| `live_session_routes.py` | 734 | HIGH |
| `scout_routes.py` | 724 | MEDIUM |
| `lg5_review_consumer_scheduler.py` | 722 | HIGH |
| `replay_execution_calibration.py` | 668 | MEDIUM |

**107 of 196 Python app modules (55%) have no corresponding test file.**

---

## 3. Test Type Coverage Assessment

### 3.1 Unit tests
- **Rust**: 2889 lib tests cover config, strategies, paper_state, indicators, agent_spine, IPC handlers. Strong.
- **Python**: ~4500 tests combined. Good coverage of route handlers, models, validators. Weak on business logic modules.
- **Gap**: Many tests verify "no crash" rather than business outcomes (see assertion-less tests below).

### 3.2 Integration tests
- **Rust**: 22 integration test crates with 193 tests total. Covers replay, reconciler, cost_edge_advisor, micro_profit, phase4, lease flag, stress.
- **Python**: FastAPI TestClient integration tests throughout. Good API contract coverage.
- **Gap**: No end-to-end tests that exercise Python-to-Rust IPC in a real pipeline flow.

### 3.3 Property-based tests (proptest)
- **Rust**: **ZERO** proptest usage in the entire codebase.
- **Python**: No hypothesis or property-based testing library usage detected.
- **Gap**: CRITICAL. No serde round-trip fuzzing, no state machine transition exhaustion, no numeric edge case exploration.

### 3.4 Concurrency tests
- **Rust**: 339 `#[tokio::test]` functions. Good async coverage for event consumers, IPC, spine.
- **Python**: 32 async test functions across 24 files. Thin relative to the heavily async codebase.
- **Gap**: No dedicated race condition tests for position updates, concurrent order submissions, or multi-agent decision conflicts. Some exist in replay (FOR UPDATE test) but systemic coverage is absent.

### 3.5 SLA / Performance tests
- **Rust**: 1 tick latency benchmark (`stress_tick_latency_benchmark`) with <100us assertion.
- **Gap**: No H0 Gate <1ms benchmark. No IPC round-trip <5ms benchmark. No p50/p95/p99 percentile measurement. Single benchmark exists but only measures tick processing, not the full pipeline.

### 3.6 Cross-language consistency
- **Coverage**: Manifest signer byte-equal (8 tests), executor decision parity (70/70 agree), bybit REST client parity.
- **Gap**: **Zero** cross-language tests for indicator calculations (ATR, Bollinger Bands, Sharpe ratio, RSI). This is a requirement per skill mandate (1e-4 tolerance) but no tests exist.

---

## 4. Test Quality Audit

### 4.1 Tests with zero assertions (AST-verified)

**39 tests** across the Python suite contain no assertions whatsoever. They verify "no exception" at best.

Key examples:
- `test_layer2.py` (15 tests): test_run_session_no_api_key, test_run_session_budget_exceeded, test_l1_triage_no_client, test_full_session_mocked, test_session_with_tool_calls, test_model_upgrade_triage, test_daily_hard_cap_cannot_be_bypassed, etc.
- `test_paper_live_gate.py` (2 tests): test_very_high_drawdown, test_duration_passed, test_duration_failed
- `test_agent_audit_bridge.py` (4 tests): test_signature_accepts_str_and_any, test_none_gov_hub_drops_silently, etc.
- `test_governance_routes_coverage.py`: test_operator_passes
- Others scattered across 10+ files.

### 4.2 Tautological assertions

2 instances of `assert True`:
- `test_bybit_rest_client_parity.py:549`
- `test_v055_evidence_insert_fix.py:1320`

### 4.3 Float exact equality

~15 places in tests compare float values with `==` instead of `pytest.approx()`:
- `test_paper_live_gate.py`: `assert cfg.min_win_rate_percent == 30.0`, `assert cfg.min_sharpe_ratio == 0.5`
- `test_layer2.py`: multiple `assert ... == 0.0`, `assert ... == 0.005`, `assert ... == 1.5`

These work today but are fragile -- any calculation path change could introduce rounding differences.

### 4.4 Mock audit

- **557 mock usage lines** across the test suite.
- No detected mock of core business logic (`should_allow`, `calculate`, `evaluate` etc.).
- All detected mocks target IO boundaries (PG connections, HTTP clients, file system, env vars).
- **Verdict**: Mock usage is clean. No anti-pattern of mocking business logic detected.

### 4.5 Test file naming collision

3 files named `test_pure_utils.py` in different directories:
- `tests/local_model_tools/test_pure_utils.py`
- `tests/ml_training/test_pure_utils.py`
- `tests/misc_tools/test_pure_utils.py`

This causes collection errors with default pytest import mode. Workaround: `--import-mode=importlib`.

---

## 5. Normal Path Coverage Assessment

| Business Path | Covered? | Notes |
|---|---|---|
| Order creation (intent -> order) | PARTIAL | Intent processing well-tested in Rust; Python order routes lack test file |
| Position management | YES | paper_state/tests.rs 172 tests + position_manager tests |
| PnL calculation | PARTIAL | paper_state covers basic PnL; no comprehensive PnL edge case suite |
| Strategy signals | YES | 427 strategy tests across 9 test files |
| Risk checks | PARTIAL | risk_checks_per_strategy_tests exist; step_6_risk_checks.rs has 0 direct tests |
| H0 gate | PARTIAL | 37 references in tests; no dedicated test file for h0_gate.py |
| Decision lease | YES | lease_flag_flip_e2e + governance tests |
| Live authorization | YES | live_auth tests exist + recheck trigger tests |
| Fill processing | PARTIAL | fill_engine.rs no direct tests; paper_state exercises indirectly |

---

## 6. Boundary Testing Assessment

| Boundary | Tested? | Notes |
|---|---|---|
| Zero balance | PARTIAL | Some zero-balance scenarios in paper_state |
| Zero position | YES | adopt_orphan NaN tests, empty position tests |
| Zero price | PARTIAL | NaN/Infinity price rejection tested in paper_state |
| Max position size | NO | No max_position boundary tests found |
| Max leverage | NO | No leverage boundary tests found |
| Min tick size | NO | No minimum tick size tests |
| Min order qty | NO | No minimum order quantity tests |
| Integer overflow | NO | No overflow tests (Rust's type system prevents most, but checked_* is unused) |
| f64 NaN propagation | YES | 10 NaN tests in paper_state + risk_checks + panel_aggregator |
| f64 Infinity | YES | Infinity rejection tests in paper_state + risk_checks |

---

## 7. Error / Abnormal Path Coverage

| Scenario | Tested? | Notes |
|---|---|---|
| Network failure during order | NO | No network failure simulation tests |
| API rate limit (429) | PARTIAL | Rate limit wiring tested; no 429 response simulation |
| Malformed Bybit data | PARTIAL | 78 malformed/invalid data test references |
| DB connection loss | NO | Zero mid-transaction PG failure tests |
| Config corruption | PARTIAL | 35 config error handling test references |
| IPC socket unavailable | YES | Mac tests naturally exercise this (engine not running) |
| Bybit retCode != 0 | PARTIAL | Some error response tests; no systematic coverage |

---

## 8. Regression Prevention Assessment

- Bug-fix commits in recent history (30 checked) generally include accompanying test changes.
- Static guard tests (test_batch_d_risk_fail_closed, test_v072_feature_baseline_writer_static) provide good regression prevention but are fragile to source refactoring.
- 2 of these static guard tests currently FAIL due to source drift, indicating the guard approach needs a more resilient string matching strategy.

---

## 9. Recommendations (Priority-ordered)

### P0 (Fix immediately)
1. Fix 4 collection-error test files: change imports from `from program_code...` to relative or add conftest.py with sys.path setup.
2. Fix test_v072 static guard: update assertion string to match refactored source.
3. Investigate 2 failing stress_integration tests: determine if strategy logic drift or test expectation error.

### P1 (Next sprint)
4. Add proptest to Rust: start with serde round-trip for all IPC message types and state machine transitions.
5. Fix 39 assertion-less Python tests: add meaningful assertions or remove if they add no value.
6. Add cross-language indicator parity tests: ATR, Bollinger Band, RSI at minimum (1e-4 tolerance).
7. Add H0 Gate <1ms and IPC <5ms SLA benchmarks.
8. Add DB connection failure tests: simulate PG drop mid-transaction.

### P2 (Backlog)
9. Add dedicated unit tests for tick_pipeline hot-path steps (step_0_fast_track, step_4_5_dispatch, step_6_risk_checks).
10. Add tests for risk_config_advanced.rs (1261 LOC, 0 tests).
11. Add tests for ws_client/ parsing/connection modules.
12. Eliminate 2 `assert True` tautologies.
13. Resolve test_pure_utils.py naming collision.
14. Replace float `==` with `pytest.approx()` in ~15 places.
15. Add max_position, max_leverage, min_tick, min_qty boundary tests.
16. Add network failure simulation tests for order submission path.

---

## 10. Baseline Summary Table

| Engine | passed | failed | baseline (profile.md) | delta |
|---|---|---|---|---|
| Rust lib (release) | **2889** | **0** | 2555* | +334* |
| Rust integration | **3080** | **2** | N/A | 2 pre-existing |
| Python srv/tests | **413** | **1** | N/A | 1 source drift |
| Python control_api_v1 | **4089** | **4** | 2555* | +1534* |
| Python collection errors | 4 files | | | |

*Note: The profile.md baseline of 2555 is outdated. Current combined Python baseline is ~4502 (413 + 4089). Current Rust lib baseline is 2889.

---

**E4 AUDIT COMPLETE** -- this is a coverage gap inventory, not a commit-gate verdict. No code changes were made.
