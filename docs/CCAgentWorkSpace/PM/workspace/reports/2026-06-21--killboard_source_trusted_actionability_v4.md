# Killboard Source-Trusted Actionability v4

Date: 2026-06-21  
Role: PM local implementation checkpoint  
Status: source/test/docs complete; runtime still unsynced

## Finding

After v350, killboard artifacts exposed source readiness, but top-level
`actionable_alpha_found` still did not require source readiness. That could let
a dirty/behind/mismatched runtime checkout produce an "actionable" flag while
the artifact itself says the source is not activation-ready.

## Change

Runtime killboard schema is now:

```text
alpha_discovery_runtime_killboard_v4
```

The fields are separated:

- `promotion_ready_count`: raw profitability-scorecard promotion-ready rows
- `promotion_ready_candidate_found`: raw `promotion_ready_count > 0`
- `actionable_alpha_found`: true only when `promotion_ready_count > 0` and
  `runtime_source_activation_ready=true`
- `actionable_probe_found`: true only when a probe is ready and source is
  activation-ready

Candidate evidence remains visible. It is just not called actionable until the
source checkout is clean, synced, and expected-head matched.

## Verification

- `python3 -m pytest helper_scripts/research/tests/test_alpha_discovery_throughput.py -q` -> `41 passed`
- `python3 -m py_compile helper_scripts/research/alpha_discovery_throughput/runtime_runner.py helper_scripts/research/tests/test_alpha_discovery_throughput.py`
- `git diff --check`

Regression coverage proves:

- untrusted source can have `promotion_ready_count=1` while
  `actionable_alpha_found=false`
- trusted clean source with matching expected head can set
  `actionable_alpha_found=true`

## Boundary

No runtime source sync, artifact refresh, crontab edit/install, env edit,
deploy/rebuild/restart, PG write/schema migration, Bybit private/signed call,
credential/auth/risk/order/strategy mutation, order authority, or promotion
proof.

## PM Read

This is a correctness gate on operator-facing language. It does not create
profit, but it prevents stale source from being mistaken for an actionable
profit opportunity.

Runtime still needs operator-approved source reconcile/sync and alpha-discovery
rerun before this v4 artifact can exist on `trade-core`.
