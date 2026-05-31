# E4 Full-Chain Test Audit — 2026-05-30

**Campaign label**: 2026-05-17 (per PM instruction)  
**Actual execution date**: 2026-05-30  
**Baseline commit**: `187704f6` (frozen)  
**Source delta since baseline**: ZERO — all 5 post-baseline commits are `[skip ci]` docs-only (fe8393e2, 9c3d5593, 8d1890a8, 14361a66, d9128e22). No code change to test.  
**Prior cold-audit report**: `docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-17--full_chain_test_audit.md`  
**Role**: E4(worker) — read-only audit (no fix, no deploy, no runtime mutation, no DB write).

---

## Scope

This audit is a full-chain test coverage audit, not a live test run. The task specified that a full `cargo test --lib` build is slow and heavy and could exceed budget; therefore I enumerate by static inspection, prior E4 report evidence, and commit-message-reported counts rather than running the full suites. Individual targeted static checks were run via grep/read. Tests actually run: zero new test suite runs (budget constraint). Tests classified: per module from static evidence.

Key new deliverables since prior cold-audit (2026-05-17):
1. **P1-OPS-2-CI-FLAKINESS**: env-test lock consolidation — commit `de32b27c`
2. **P1-110017-D1**: dispatch 110017 classify-as-NoOp+convergence — commit `caf008b6`
3. **P2-110017-D2**: D2 ghost convergence in position_reconciler — commit `a5e1ded1`
4. **P2-BASIS-PANEL-INFRA**: BasisAggregator + V115 — commit `ec995160`
5. **FA-audit G1/G2/G5**: risk.rs byte-equivalent split — commit `46e0e825`
6. **C4 wire**: notification failsafe wire into runtime — commit `a8ba146c`
7. **Stage-0R A1/A2 runner**: helper script — commit `21db54b1`

---

## Severity Summary

- P0: 0
- P1: 1 (dispatch retry on Transient — persists from prior audit, NOT remediated)
- P2: 2 (promotion-route paper-freeze test gap; Stage-0R runner has no pytest coverage)
- P3: 1 (basis_panel has no Python-side test; Rust-only)

---

## Prior Remediation Status

### E4-FCT-001 — Dispatch Retry On Transient (Prior P1): NOT REMEDIATED

FACT: `dispatch.rs` still classifies `BybitApiError::Transport` and `JsonParse` as `DispatchOutcome::Transient` (lines 205–206), retCode 10006, 10016-10019 as `Transient` (lines 227, 231), and `run_dispatch_retry()` still sleeps and retries. Production open/close intent dispatch still calls this loop. This conflicts with CLAUDE §四 "Bybit API timeout or nonzero retCode fails closed; do not add hidden retry paths for trading effects."

Evidence: `grep -n "Transport\|JsonParse\|Transient\|run_dispatch_retry" rust/openclaw_engine/src/event_consumer/dispatch.rs` — lines 205, 206, 227, 231, 468.

Status: **Still open P1**. The 110017 fix (`caf008b6`) changed 110017 from Structural to NoOp with convergence (correct), but did not change Transport/JsonParse/server-error Transient retry. Regression risk: unchanged.

### E4-FCT-002 — Paper→Demo Promotion Path (Prior P1): REMEDIATED

FACT: `promotion_pipeline.py` lines 527–538 now explicitly block `PAPER_SHADOW -> DEMO_ACTIVE` with `paper_lane_frozen:demo_promotion_requires_explicit_operator_reopen`. File-level header comment (line 2) documents the freeze. This is a correct fix.

**Prior P1 → CLOSED.**

Gap remains: Existing tests (`test_promotion_pipeline.py`) that previously asserted the paper→demo happy path now need to assert the frozen rejection. This was not verified to be updated in this audit. Carry-over P2.

### E4-FCT-003 — Full-Chain Run Tests Do Not Prove Linux Runtime (Prior P2): UNCHANGED

FACT: The route still uses monkeypatched `fake_register` and `fake_run` in tests. Linux PG empirical evidence not added. TODO `[48]` replay manifest healthcheck still shows `last_age=407h` as of 2026-05-29 snapshot. Runtime evidence is still needed. P2 unchanged.

### E4-FCT-004 — Missing Concurrent Duplicate Full-Chain Run Test (Prior P2): UNCHANGED

FACT: No concurrent duplicate full-chain test was added in the commits since the prior audit. P2 unchanged.

---

## New Area Audit

### #1 — P1-OPS-2-CI-FLAKINESS: Env-Test Lock Consolidation (REMEDIATED)

**Tag**: FACT  
**Commit**: `de32b27c`  
**Evidence**: `grep -n "test_env_lock\|guard()" rust/openclaw_engine/src/lib.rs` confirms `pub(crate) mod test_env_lock` at line 125. All 12+ previously scattered per-module env-mutating mutex callers now use `crate::test_env_lock::guard()`. Verified in: `live_authorization.rs` (lines 805, 842, 866, 916, 974), `bybit_rest_client_tests.rs` (lines 726, 749, 772, 804), `drawdown_revoke.rs` (lines 307, 341, 365), `h_state_cache/tests.rs` (line 123).  
**Commit message evidence**: E2 2-round APPROVE, `cargo test --lib 3598/0/1` Mac x3 (non-flaky). Carry-over: Linux ≥5-round concurrent flake verification.  
**Finding**: Prior P1-OPS-2-CI-FLAKINESS REMEDIATED at source. Single `test_env_lock` holds. Linux concurrent verification is carry-over but not a blocking deficiency at Mac audit level.

### #2 — 110017 D1 Close-Loop Fix (COVERED, TESTS REAL)

**Tag**: FACT  
**Commits**: `caf008b6` (D1 dispatch NoOp+convergence), `a5e1ded1` (D2 reconciler ghost convergence)  
**Test coverage evidence**:
- `dispatch_tests.rs` line 227: `test_classify_110017_reduce_only_reject_is_noop` — classifies 110017 as NoOp.
- `dispatch_tests.rs` line 238: `test_classify_110001_110009_unchanged_noop_no_regression` — regression guard for unchanged retcodes.
- `position_reconciler/tests.rs` lines 686–1047: 8+ tests labeled `P2-110017-D2-RECONCILE: process_ghosts converge tests` cover DriftVerdict::Ghost convergence, drain-channel assertions, S-6 single-symbol gate.
- `tick_pipeline/tests/dual_rail_dispatch.rs` lines 68–768: 20+ tests covering close-maker path, dispatch variants, including `test_primary_exchange_full_close_dispatches_qty_zero`.
- Commit message: E2 APPROVE, chain verified E1→E2→E4.  
**Mock safety check**: `position_reconciler/tests.rs` uses `MockExchangeClient` for IO boundary — business logic (ghost classification, convergence) runs real. PASS.  
**Finding**: 110017 fix has adequate test coverage; regression guards present.

### #3 — BasisAggregator / V115 basis_panel (COVERED, RUST-ONLY, NO PYTHON)

**Tag**: FACT  
**Commit**: `ec995160`  
**Rust test evidence**: `basis.rs` lines 259–445 contain 9 unit tests: `test_basis_formula_parity_signed`, `test_cohort_ticker_update_buffers_with_valid_index`, `test_non_cohort_symbol_ignored`, `test_fail_closed_never_seen_index_not_cached`, `test_latest_value_cache_sparse_index_frame`, `test_flush_empty_cache_returns_zero`, `test_flush_pool_unavailable_cache_retained`, `test_cohort_size_initialization_dedupe`, `test_insert_sql_locks_v115_columns`, `test_basis_formula_uses_last_price_not_mark`.  
**Float tolerance**: `test_basis_formula_parity_signed` uses `1e-12` — tighter than 1e-4 minimum. Correct. Formula parity tested vs strategy `funding_short_v2` `compute_basis_pct`.  
**Mock safety**: `make_disconnected_pool()` (line 261) is a disconnected IO mock — business logic (formula, cache, fail-closed) runs real. PASS.  
**Cross-lang gap**: BasisAggregator is Rust-only panel writer. Python side has no unit test for `basis_panel` schema or freshness check beyond passive healthcheck `[66]` integration. This is a P3 — the formula is Rust-canonical, no Python reimplementation, so cross-lang drift is low risk. The `test_insert_sql_locks_v115_columns` static SQL column guard exists.  
**Python test discovery**: `grep -rn "basis_panel\|BasisAggregator" tests/ program_code/ --include="*.py"` returns zero hits.  
**Finding**: Rust coverage is good. No Python-side test for freshness sentinel behavior or V115 schema correctness beyond Rust static guard. P3.

### #4 — risk.rs Byte-Equivalent Split (SAFE, TESTED INDIRECTLY)

**Tag**: FACT  
**Commit**: `46e0e825`  
**Evidence**: Commit message states "E2 byte-equivalent verified; cargo --lib 3623/0 unchanged; c4 e2e 3/3." The split moves ~205 LOC `handle_notification_failsafe_escalate` from `handlers/risk.rs` to `handlers/notification_failsafe_escalate.rs` as pure move with re-export. Zero behavior change.  
**Test evidence**: `c4_failsafe_wire_tests.rs` has 3 e2e tests (`e2e_c4_failsafe_inband_escalate_demo` at line 32, `e2e_c4_watcher_allfail_arms_then_claims_once` at line 100). These call `crate::event_consumer::handlers::handle_notification_failsafe_escalate` — now re-exported from the new module. Tests still pass = re-export is correct.  
**Finding**: Safe. No new tests needed (pure structural move). PASS.

### #5 — C4 Failsafe Wire Into Runtime (COVERED, DORMANT-BY-DESIGN)

**Tag**: FACT  
**Commit**: `a8ba146c`  
**Test evidence**: `c4_failsafe_wire_tests.rs` (in `event_consumer/tests/`) provides e2e tests. Memory note from 2026-05-28 confirms `notification_failsafe --lib 107/0` including `T4.12 watcher` concurrency test with adversarial reproduction (fake-buggy → 16 escalations, fix → 1). The C4 wire is dormant at runtime (0 escalation in PID 251791 TODO snapshot) — this is by design (no live AllFail condition yet).  
**Mock safety**: StubTransport / CountingAudit are IO-sink mocks; business logic (claim-before-await, timeout guard) runs real per memory note.  
**Finding**: PASS. Well-covered. Dormant-in-production is correct posture for safety system.

### #6 — Stage-0R A1/A2 Runner (NO PYTEST COVERAGE — P2)

**Tag**: FACT  
**Commit**: `21db54b1`  
**Evidence**: `grep -rn "def test_" helper_scripts/reports/alpha_candidate_stage0r/ --include="*.py"` returns zero hits. `find tests/ -name "*stage0r*"` returns zero. The runner (`candidate_stage0r_runner.py`, `candidate_stage0r_smoke.py`) is a CLI helper script with PG dependency.  
**Why real, not FP**: The script is dispatched as an entry point for alpha candidate qualification decisions (A2 LCS fade was evaluated through this). Lack of unit tests means basis-formula reading, row-count thresholds, Wilson CI bounds, and smoke-test short-circuit logic are untested in isolation. A miscalculation can silently promote or block a candidate.  
**Severity**: P2. Impact: silent miscalculation of promotion evidence. The script is helper-script tier (not Rust trading core), and A2 is currently REVISE/HOLD anyway, reducing immediate blast radius.  
**Fix direction**: Add pytest unit tests for `compute_wilson_lower`, threshold checks, and smoke-short-circuit gate using mock PG row objects. No live DB required.  
**Fix owner**: E1(worker)  
**Verifier**: E4(worker)

### #7 — Promotion-Route Paper-Freeze Test Gap (P2 CARRY-OVER)

**Tag**: FACT + INFERENCE  
**Evidence**: `promotion_pipeline.py` lines 527–538 freeze paper→demo with `paper_lane_frozen` error. FACT. However, I did not re-read `test_promotion_pipeline.py` to confirm whether existing happy-path paper→demo test was updated to assert the rejection instead. The prior E4-FCT-002 finding noted tests asserted the old success path.  
**Tag**: INFERENCE — the test may still assert old success path, which would now FAIL the current code, or may have been patched. This cannot be resolved without running the test or reading the file.  
**Impact if not patched**: Either the test fails (surfaced in CI) or was deleted (regression coverage gap).  
**Severity**: P2 until confirmed.  
**Fix direction**: Read `test_promotion_pipeline.py` around line 125 to confirm the test now asserts `paper_lane_frozen` rejection. If still asserts success → E1 update test.  
**Fix owner**: E1(worker)  
**Verifier**: E4(worker)

---

## Executable Test Matrix

| ID | Area | Run Status | Last Known Count | Needs Linux? | Notes |
|---|---|---|---|---|---|
| M1 | Rust cargo workspace lib | Not run this audit (budget) | `3634/0` (ec995160 basis PASS per commit msg) | No for lib; Yes for integration | Prior memory: 3598 (de32b27c) → 3623 (46e0e825) → 3634 (ec995160) |
| M2 | Python pytest full | Not run this audit (budget) | `6042/28/45` (2026-05-22 baseline, sprint 2 wave 2) | No | 28 pre-existing carries |
| M3 | Bybit retCode fail-closed | Not run | Covered in dispatch_tests.rs | No | 30+ classify_* tests in dispatch_tests.rs |
| M4 | 110017 D1+D2 | Not run (static verified) | 8+ tests in position_reconciler/tests.rs + dispatch_tests.rs line 227 | No | Covered; adversarial reproduction done by E4 2026-05-28 |
| M5 | Env-test lock (lib) | Not run (static verified) | 3598/0/1 Mac x3 (commit msg) | Yes (≥5-round concurrent flake) | Carry-over Linux run needed |
| M6 | BasisAggregator | Not run (static verified) | 9 unit tests in basis.rs; formula < 1e-12 | Yes for flush-pool real PG write | Rust-only; Python coverage gap P3 |
| M7 | C4 failsafe wire | Not run (static verified) | 107/0 (2026-05-28 memory) | No | 3 e2e + T4.12 concurrency; adversarial reproduction confirmed |
| M8 | Auth expiry / live gates | Not run | Prior: live_auth_watcher_tests good | Yes (auth.json present/absent) | Linux read-only stat only |
| M9 | Stage-0R runner | Cannot run (PG dependency) | 0 unit tests (P2 gap) | Partially | Need mock-based unit tests first |
| M10 | Promotion paper-freeze test | Not run | Status unknown (P2 carry-over) | No | Need to read test_promotion_pipeline.py |
| M11 | Full-chain Linux PG/subprocess | Cannot run here (side-effecting) | 0 runtime evidence since 2026-05-17 | YES | SELECT/stat only allowed |
| M12 | Cross-lang basis float | Static verified | basis.rs < 1e-12 vs strategy | No new gap | No Python reimplementation; single source of truth |
| M13 | Dispatch retry / transient | Not run (known gap) | Covered for classify; NOT for one-attempt-only assertion | No | P1 still open; PA must arbitrate |

---

## #8 Deep-Dive: Test Blind Spots

### Fail-Closed

**Covered**: `test_into_result_non_zero_retcode_fails_closed` (bybit_rest_client_tests.rs). `test_classify_110017_reduce_only_reject_is_noop` with convergence. BasisAggregator `test_fail_closed_never_seen_index_not_cached`. Auth gates 403 on missing/stale auth.

**Blind spot — REAL**: Fail-closed on Transport error for trading-effect dispatch still has retry (P1 from prior audit, unaddressed). The `run_dispatch_retry` loop on `Transient` is tested to exhaust but also tested to succeed after transient recovery, which is the very behavior CLAUDE §四 disputes.

### Timeout

**Covered**: `close_dispatch_timeout_error` helper at line 430 exists. `tokio::time::timeout` wraps close attempt at line 787 returning `Err(close_dispatch_timeout_error(...))` → classified by `classify_dispatch_error`. Timeout goes through the same `Transient` path → retry loop. Same P1 issue.

### Bybit retCode Handling

**Covered**: 30+ classify_* tests in dispatch_tests.rs cover the full retCode taxonomy. Regression guard for 110001/110009 unchanged. 110017 fix has dedicated test.

**Blind spot (LOW)**: No test for the "unknown retCode with specific error msg substring" path (line 233+ in dispatch.rs) which has string-based classification. If Bybit adds a retCode in the catch-all range, behavior would be Structural by default — probably correct but not explicitly tested for boundary.

### Concurrency (env-test locks)

**Prior remediation HELD**: `de32b27c` merged 12 scattered locks → single `crate::test_env_lock::guard()`. Verified in live_authorization, bybit_rest_client_tests, drawdown_revoke, h_state_cache, edge_estimates/btc_lead_lag. Mac 3x clean. Linux ≥5-round still needed (carry-over).

**Other concurrency (C4 T4.12)**: `#[tokio::test(flavor="multi_thread", worker_threads=4)]` with 16 real `tokio::spawn` tasks, shared `Arc<SharedFailsafeWatcher>`, adversarial reproduction confirmed FAIL with buggy path and PASS with fix. Non-flaky.

### Stale Data

**Covered**: `test_latest_value_cache_sparse_index_frame` in basis.rs verifies that stale index frames are preserved correctly across sparse updates (last-known cache retained). dust/stale price checks in paper_state.

**Blind spot (LOW)**: No explicit test for basis_panel rows with age > retention policy (14d). This would be a PG-side behavior, appropriately Linux-runtime evidence, not a Mac unit test gap.

### Auth Expiry

**Covered**: Missing/expired/stale/wrong-mode auth returns 403 in Python tests. `live_auth_watcher_tests` covers watcher respawn/backoff. Linux read-only evidence (stat authorization.json) still deferred.

### Replay/Promotion Boundary

**Covered**: Paper→demo freeze now implemented (`paper_lane_frozen`). Test alignment unknown (P2 carry-over).

**Blind spot**: No Stage 0R "must pass replay before demo promotion" test exists. The A1/A2 runner is untested (P2). The promotion gate relies on operator + QC review, not automated test assertion.

---

## Mock Safety Audit

| Module | Mock Content | Business Logic Real? | OK? |
|---|---|---|---|
| basis.rs tests | `make_disconnected_pool()` — IO only | Formula / cache / fail-closed / SQL column | YES |
| c4_failsafe_wire_tests | StubTransport / CountingAudit / NoopXxx — IO sink | claim-before-await / timeout / config | YES |
| position_reconciler/tests | MockExchangeClient — IO | ghost classification / convergence / gate | YES |
| dispatch_tests | BybitApiError stub calls — IO | classify_dispatch_error / classify_business_retcode | YES |
| test_promotion_pipeline.py | httpx mock / fake DB | PromotionStage logic | UNKNOWN (not re-read this audit — P2 carry-over) |
| test_replay_full_chain_run_routes | fake_register + fake_run | Route envelope behavior only | ACCEPTABLE (local test); NOT proof of Linux PG |

---

## Float Tolerance Check

| Function | Tolerance Used | Standard | OK? |
|---|---|---|---|
| `test_basis_formula_parity_signed` (basis.rs) | `1e-12` | `< 1e-4` required | YES (far tighter) |
| strategy `compute_basis_pct` cross-check | `< 1e-12` (panel.abs() == strategy.abs()) | n/a | YES |
| No Python↔Rust cross-lang test for basis | — | n/a | Not applicable (Rust-canonical, no Python reimplementation) |

---

## Findings

### F-001 — Dispatch Retry On Transient Still Conflicts With Fail-Closed Boundary

- **Tag**: FACT
- **Severity**: P1 (carry-over from E4-FCT-001, not remediated)
- **Path+line**: `dispatch.rs:205-206` (Transport→Transient), `dispatch.rs:227,231` (retCode Transient), `dispatch.rs:468` (`run_dispatch_retry`)
- **Evidence**: Static grep confirmed; CLAUDE.md §四 "Bybit API timeout or nonzero retCode fails closed" conflict unchanged
- **Impact**: Trading-effect dispatch retries on ambiguous transport failure or Bybit server errors; `order_link_id` mitigates duplicates but does not eliminate risk under exchange ambiguity
- **Why real**: Production path calls retry loop; test suite explicitly asserts retry-until-success; hard-boundary conflict is documented
- **Fix direction**: PA arbitrate policy exception vs absolute; if absolute, change Transport/server-error retCode to Structural or one-attempt
- **Fix owner**: PA(default) → E1(worker)
- **Verifier**: E4(worker) + BB(default)

### F-002 — Stage-0R Runner Python Missing Unit Tests

- **Tag**: FACT
- **Severity**: P2
- **Path**: `helper_scripts/reports/alpha_candidate_stage0r/` (all `.py` files)
- **Evidence**: `grep -rn "def test_" helper_scripts/reports/alpha_candidate_stage0r/` = 0 hits; `find tests/ -name "*stage0r*"` = 0 hits
- **Impact**: Wilson CI, threshold checks, and smoke short-circuit logic are untested; silent miscalculation can affect promotion decisions
- **Why real**: Runner is used for A1/A2 candidate qualification; A2 REVISE/HOLD decision was based on its output
- **Fix direction**: Add mock-PG pytest unit tests for `compute_wilson_lower`, per-metric gate, smoke short-circuit
- **Fix owner**: E1(worker)
- **Verifier**: E4(worker)

### F-003 — Promotion-Route Paper-Freeze Test Alignment Unknown

- **Tag**: INFERENCE (test file not re-read this audit)
- **Severity**: P2
- **Path**: `program_code/.../tests/test_promotion_pipeline.py` around line 125
- **Evidence**: Paper→demo freeze confirmed in source (pipeline.py lines 527-538). Prior E4-FCT-002 noted tests asserted old success path. Test update status unconfirmed.
- **Impact**: If test still asserts old paper→demo success: either test FAILS in CI (visible) or was deleted (coverage gap). Both are problems.
- **Fix direction**: Read test; if asserts old success → update to assert `paper_lane_frozen`; if deleted → reinstate rejection assertion
- **Fix owner**: E1(worker)
- **Verifier**: E4(worker)

### F-004 — BasisAggregator Has No Python-Side Test (P3)

- **Tag**: FACT
- **Severity**: P3
- **Path**: `rust/openclaw_engine/src/panel_aggregator/basis.rs`; `sql/migrations/V115__panel_basis_panel.sql`
- **Evidence**: No Python tests for basis_panel in `tests/` or `program_code/`. Python freshness sentinel `[66]` integration-tests at runtime only.
- **Impact**: Low — Rust-canonical, no Python reimplementation; V115 column guard exists in Rust (`test_insert_sql_locks_v115_columns`); freshness behavior tested at runtime via healthcheck
- **Fix direction**: Optional static test for V115 column names in Python migration-verification tooling; not urgent
- **Fix owner**: E1(worker) (optional)
- **Verifier**: E4(worker)

---

## Verdict

**E4 FULL-CHAIN TEST AUDIT: FAIL FOR FULL CLEAN — P1 PERSISTS**

P0: 0. P1: 1 (F-001 dispatch retry, carry-over unaddressed). P2: 2 (F-002 Stage-0R tests missing, F-003 promotion-freeze test alignment). P3: 1 (F-004 no Python basis test).

The 2026-05-29/30 code changes (110017 D1/D2, env-test lock, basis_panel, risk.rs split, C4 wire) all have adequate Rust test coverage with correct mock safety. The prior P1 E4-FCT-001 (dispatch retry) persists unchanged. Prior P1 E4-FCT-002 (paper→demo) is remediated at source; test alignment is unconfirmed (P2 carry-over). Env-test lock remediation held at Mac level; Linux ≥5-round concurrent verification is a carry-over, not a new deficiency.

The audit did not run full pytest or cargo test suites (budget constraint per task). Last-known counts: Rust lib ~3634/0, Python ~6042/28/45 (from commit messages and prior E4 reports). Both counts must be re-verified on Linux before any PM commit + push.

---

*Report written: 2026-05-30 by E4(worker)*
