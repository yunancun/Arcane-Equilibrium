# Option A Closure: Phase 1b Worktree B + W-AUDIT-8b Round 2 Phase A

Date: 2026-05-16
Role: PM(default)
Decision: operator selected Option A, dispatching `E1(worker)` x2 in parallel.

## Verdict

APPROVED for source/test checkpoint.

Two independent implementation batches are committed:
- `a6e17d5d` `feat(w-audit-8b): add v0.3 sweep tooling`
- `ea4ceca6` `feat(phase1b): wire close maker first dispatch`

No deploy, production SQL migration, runtime restart, auth mutation, paper enablement, live/mainnet enablement, or production `allLiquidation` subscription was performed.

## W-AUDIT-8b Round 2 Phase A

Scope:
- `helper_scripts/reports/w_audit_8b/funding_skew_stage0r_metrics.py`
- `helper_scripts/reports/w_audit_8b/funding_skew_stage0r_report.py`
- `helper_scripts/reports/w_audit_8b/funding_skew_stage0r_smoke.py`

Implemented:
- Backward-compatible `compute_stage0r(z_grid=...)`.
- `compute_stage0r_sweep(...)` wrapper and `wilson_ci_95(...)`.
- CLI `--sweep` and `--z-cells`.
- Four sweep output blocks: `sweep_per_z_cell`, `sweep_per_symbol`, `best_primary_cell_per_z_branch`, and `sweep_cross_z_comparison`.
- Non-sweep remains `funding_skew_directional.v0_2` with `k_new_min=4050`; sweep uses `funding_skew_directional.v0_3` with `k_new_min=5400`.
- Per-symbol eligibility floors, strict monotonic comparisons, branch-specific best-primary packets, and funding-cycle/day concentration gates.

Review chain:
- E1 round 1 -> A3/E2 RETURN.
- E1 round 2 -> A3 APPROVE + E2 APPROVE.
- E4 PASS.

E4 evidence:
- Smoke PASS.
- `py_compile` PASS.
- CLI help PASS.
- Local shape probe confirmed non-sweep and sweep schemas/thresholds.
- `git diff --check` PASS.

Phase B production rerun remains blocked until panel coverage is at least 7 days and the preregistered rerun gates pass.

## Phase 1b Worktree B

Scope:
- V094 close-maker fill audit schema/writer.
- Close-maker pricing and dispatch classification.
- Dynamic reject/backoff plumbing.
- Close-maker healthchecks and tests.
- Demo-only enable surface.

Implemented:
- `compute_close_limit_price(...)` with strict-skip spread guard and per-exit behavior.
- Close dispatcher whitelist routing: positive close reasons use maker-first limit/PostOnly path; all other close reasons keep market path.
- V094 audit payload and writer.
- Close-maker reject/backoff/cooldown plumbing including `rate_limit_scope`.
- Mandatory fallback/terminalization paths for reject, cancelled-after-timeout, deactivated, ack-lost, cancel-grace, no-REST timeout, dispatch failure, DCP, and preflight failures.
- Duplicate fallback guard and market fallback recursion guard.
- `[70]`, AC-18, `[74]`, and close-maker reject sample healthcheck coverage.
- Demo-only enable surface; no live/mainnet enablement.

Review chain:
- E1 rounds 1-3.
- A3/E2 returned twice on fallback and enable-surface gaps.
- E1 round 3 fixed DCP, preflight fallback, and `rate_limit_scope`.
- A3 APPROVE + E2 APPROVE.
- E4 PASS.

E4 evidence:
- `cargo test -p openclaw_engine close_maker --lib`: 23 passed.
- `cargo test -p openclaw_engine market_fallback --lib`: 7 passed.
- `cargo test -p openclaw_engine cancel_grace --lib`: 2 passed.
- `cargo test -p openclaw_engine dcp --lib`: 3 passed.
- `cargo test -p openclaw_engine preflight --lib`: 4 passed.
- `cargo test -p openclaw_engine pending_registration_order_type_tests --lib`: 18 passed.
- `cargo test -p openclaw_engine event_consumer::dispatch::tests --lib`: 33 passed.
- `cargo check -p openclaw_engine`: PASS with 3 existing unrelated warnings.
- `python3 -m pytest helper_scripts/db/test_close_maker_audit_healthcheck.py tests/migrations/test_v094_fills_close_maker_audit.py -q`: 13 passed plus 14 subtests.
- Touched-file `rustfmt` PASS.
- `git diff --check` PASS.
- Forbidden-surface grep PASS for `OPENCLAW_ENABLE_PAPER=1`, production `allLiquidation`, live/mainnet enablement, and close-maker ML/spine lineage.

Residual gates:
- C1 v2 24h proof remains in flight.
- W-AUDIT-8b production rerun waits for panel coverage >= 7 days.
- V094 Linux PG dry-run/apply and runtime deployment are future deploy-chain actions.
- Phase 2a observation must not start until external gates clear.

PM SIGN-OFF: APPROVED for source/test; DEPLOY BLOCKED.
