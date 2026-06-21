# Killboard Actionable-Alpha Semantics v2

Date: 2026-06-21  
Role: PM local implementation checkpoint  
Status: source/test/docs complete; runtime still unsynced

## Finding

After tightening Polymarket promotion readiness, one top-level ambiguity
remained: runtime killboard `actionable_alpha_found` still followed raw
`READY_FOR_AEG_CHAIN`.

That signal is useful, but it means "candidate artifact ready for AEG review",
not "alpha promotion evidence is ready".

## Change

`alpha_discovery_throughput.runtime_runner` now emits runtime killboard schema:

```text
alpha_discovery_runtime_killboard_v2
```

The top-level killboard fields are now separated:

- `ready_for_aeg_chain`: raw candidate-artifact action count
- `aeg_candidate_artifact_found`: true when `ready_for_aeg_chain > 0`
- `promotion_ready_count`: profitability-scorecard promotion-ready count
- `actionable_alpha_found`: true only when `promotion_ready_count > 0`

History JSONL rows now also include promotion/actionability flags.

## Verification

- `python3 -m pytest helper_scripts/research/tests/test_alpha_discovery_throughput.py -q` -> `40 passed`
- `python3 -m py_compile helper_scripts/research/alpha_discovery_throughput/runtime_runner.py helper_scripts/research/tests/test_alpha_discovery_throughput.py`
- `git diff --check`

Regression coverage proves:

- generic MM candidate-review readiness still sets `actionable_alpha_found=true`
- Polymarket `READY_FOR_AEG_CHAIN` with missing replay history sets
  `aeg_candidate_artifact_found=true` but `actionable_alpha_found=false`

## Boundary

No runtime source sync, artifact refresh, crontab edit/install, env edit,
deploy/rebuild/restart, PG write/schema migration, Bybit private/signed call,
credential/auth/risk/order/strategy mutation, order authority, or promotion
proof.

## PM Read

This reduces operator-facing false positives. The system can now say: "we have
a candidate artifact to review" without saying: "we have actionable alpha."

Runtime will continue to show the old v1 semantics until `trade-core` source is
reconciled/synced and alpha-discovery reruns on the new code.
