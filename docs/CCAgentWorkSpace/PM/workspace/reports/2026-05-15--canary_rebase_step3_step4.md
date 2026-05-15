# 2026-05-15 — Canary Rebase Step 3/4 Close-out

## Scope

PM freeze and AMD-2026-05-15-01 already landed in commit `8889d9b8`.
This close-out covers the follow-on Step 3 runtime/spec rebase and Step 4
fill-lineage gate.

## Step 3 — Runtime Smoke

`trade-core` runtime smoke results:

- RouterLeaseGuard Drop Rust test: PASS
  - command scope: `rust/openclaw_engine`
  - test: `test_router_lease_guard_drop_releases_active_lease_cancelled`
- ExecutorAgent fail-closed pytest: PASS
  - result: `3 passed, 44 deselected`
- `[55] agent_decision_spine_lineage` direct healthcheck:
  - status: `WARN_REAL_FILL_PROPAGATION_PARTIAL`
  - `chains=89`
  - `chains_with_idempotency=89`
  - `chains_with_lease=89`
  - `chains_with_report=89`
  - `chains_with_real_fill_report=15`
  - `bad_report_quality=0`
  - `bad_report_value_quality=0`

Runtime smoke requirement `[55] chains_with_lease > 0` is satisfied.
Demo-canary fill-lineage readiness is not fully satisfied because real-fill
propagation remains below the 50% partial threshold.

## Step 3 — A4-C Rebase

Rebased A4-C from legacy paper promotion to AMD-2026-05-15-01 semantics:

- `docs/execution_plan/2026-05-10--a4c_btc_alt_lead_lag_spec.md` is now v1.4.
- Legacy D+12 paper edge report is diagnostic/read-only only.
- Stage 0R output is `eligible_for_demo_canary=true/false`.
- Stage 1 promotion evidence must be Demo micro-canary evidence.
- `OPENCLAW_ENABLE_PAPER=1` remains blocked for promotion.

W2 report tooling was also downgraded:

- `helper_scripts/reports/w2/w2_paper_edge_report.py` now describes Stage 0R
  diagnostics.
- Metrics emit `eligible_for_demo_canary=true/false`.
- Legacy `promote_n2` is kept only as a compatibility field and remains false.
- Smoke test PASS:
  - `python3 helper_scripts/reports/w2/w2_paper_edge_report.py --smoke-test`

## Step 4 — Fill-lineage Gate

Fill evidence is visible, but the gate is not PASS:

- usable evidence: yes (`chains_with_real_fill_report=15`, value-quality bad rows = 0)
- invariant status: `WARN_REAL_FILL_PROPAGATION_PARTIAL`
- ratio: 15/89 real-fill reports, below the 50% warning threshold

Decision: Stage 1 Demo micro-canary launch remains blocked until `[55]` reaches
PASS or PM/operator explicitly accepts a waiver for this WARN.

