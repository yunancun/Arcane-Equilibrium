# Killboard Runtime Source-Readiness Visibility v3

Date: 2026-06-21  
Role: PM local implementation checkpoint  
Status: source/test/docs complete; runtime still unsynced

## Finding

The current runtime problem is not only "no profitable alpha". It is also that
the runtime artifact can be stale because `trade-core` source is behind/dirty.
Before this checkpoint, that source trust state was visible through read-only
operator probes and the cost-gate arm, but not as a top-level alpha killboard
fact.

## Change

`alpha_discovery_throughput.runtime_runner` now emits:

```text
alpha_discovery_runtime_killboard_v3
```

Each run adds a top-level `runtime_source` object from the existing read-only
source/git inspection helper. The killboard also mirrors compact fields:

- `runtime_source_activation_ready`
- `runtime_source_activation_status`
- `runtime_source_git_status`
- `runtime_source_expected_head_status`

The history JSONL row records the same fields.

## Verification

- `python3 -m pytest helper_scripts/research/tests/test_alpha_discovery_throughput.py -q` -> `40 passed`
- `python3 -m py_compile helper_scripts/research/alpha_discovery_throughput/runtime_runner.py helper_scripts/research/tests/test_alpha_discovery_throughput.py`
- `git diff --check`

Regression coverage proves the artifact keeps producing the existing action
counts while also exposing source readiness fields.

## Boundary

No runtime source sync, artifact refresh, crontab edit/install, env edit,
deploy/rebuild/restart, PG write/schema migration, Bybit private/signed call,
credential/auth/risk/order/strategy mutation, order authority, or promotion
proof.

## PM Read

This makes the artifact more self-auditing. Once `trade-core` runs this code,
operators will no longer need a separate git probe to know whether the alpha
killboard was built from a trustworthy source checkout.

It does not fix the current stale runtime artifact by itself. Runtime still
needs operator-approved source reconcile/sync and alpha-discovery rerun.
