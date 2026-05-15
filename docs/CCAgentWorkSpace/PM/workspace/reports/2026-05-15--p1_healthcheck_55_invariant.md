# 2026-05-15 — P1-HEALTHCHECK-55-INVARIANT

## Scope

Investigated `[55] agent_decision_spine_lineage`
`WARN_REAL_FILL_PROPAGATION_PARTIAL` after Step 5b Stage 0R remained GATE-RED.

Boundary: passive healthcheck source/test only plus read-only `trade-core` PG
verification. No runtime config, live auth, engine restart, DB write, or
strategy/risk change.

## RCA

Initial direct `[55]` on `trade-core` reproduced the WARN:

- status: `WARN_REAL_FILL_PROPAGATION_PARTIAL`
- old denominator: `chains=139`
- old numerator: `chains_with_real_fill_report=25`
- quality counters: `bad_report_quality=0`, `bad_report_value_quality=0`
- state changes: `state_changes_24h=745`

Decomposition showed the old denominator was wrong for the current Rust
contract:

- complete decision chains: 139
- chains with any matching `trading.fills` row on the planned order id: 37
- chains with fill-completion ExecutionReport: 25
- chains that reached Rust `fully_filled` threshold
  (`cum_filled_qty >= plan_qty * 0.999`): 25
- fully-filled chains missing fill-completion ER: 0
- partial / near-full chains below the 0.999 threshold: 12 at that snapshot

Fact: most of the `139` chains were legitimate no-fill chains. The apparent
`25/139` failure was a healthcheck/filter bug, not a data-quality failure.

Fact: partial / near-full plan fills exist and are intentionally not emitted as
fill-completion ER by the current Rust path. That is now surfaced separately as
`partial_plan_fill_chains`; it is not mixed into the full-fill denominator.

## Change

`helper_scripts/db/passive_wait_healthcheck/checks_agent_spine.py` now:

- keeps the existing complete-chain, idempotency, lease, report-quality, value
  quality, and state-change checks;
- adds `chains_with_plan_order_fill`;
- adds `chains_with_full_plan_fill`;
- adds `full_plan_fills_missing_report`;
- adds `partial_plan_fill_chains`;
- removes the `chains_with_real_fill_report / complete_chains >= 50%`
  heuristic gate;
- blocks only when a fully-filled plan lacks a real fill-completion ER.

## Verification

Local unit regression:

```text
python3 -m pytest helper_scripts/db/test_agent_spine_healthcheck.py -q
15 passed
```

Patched module executed on `trade-core` against current PG:

```text
PASS
chains=144
chains_with_real_fill_report=25
chains_with_plan_order_fill=38
chains_with_full_plan_fill=25
full_plan_fills_missing_report=0
partial_plan_fill_chains=13
bad_report_quality=0
bad_report_value_quality=0
state_changes_24h=770
```

## Verdict

`[55]` is source-cleared for the current Rust full-fill lineage contract.

Remaining Stage 1 demo blocker is still A4-C Stage 0R GATE-RED
(`eligible_for_demo_canary=false`). Partial per-fill ExecutionReport lineage is
future hardening and should not be confused with this `[55]` full-fill
completion gate.
