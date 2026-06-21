# Cost-Gate Learning Readiness Classification

Date: 2026-06-21

## Problem

The cost-gate demo-learning lane had a shallow status interface in alpha-discovery:

- The plan artifact exposes `gate_status=OPERATOR_REVIEW`.
- The generic discovery logic maps `OPERATOR_REVIEW` to `READY_FOR_PROBE`.
- Runtime evidence showed no `probe_ledger.jsonl` and no blocked-outcome review artifact.

That meant the global killboard could say `actionable_probe_found=true` even though the system had not started accumulating the data needed to justify any demo probe authority.

## Change

`cost_gate_demo_learning_lane` now has a dedicated readiness classifier in `alpha_discovery_throughput.discovery_loop`.

Rules:

- Missing/empty `probe_ledger.jsonl` -> `data_coverage`, next trigger deploy/enable runtime ledger writer and learning-lane cron.
- Admission-only ledger -> `data_coverage`, next trigger run blocked-signal outcome refresh.
- Blocked outcomes below review sample gate -> `sample_gate`, next trigger continue recording and refreshing outcomes.
- `NO_DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATE` -> `rejected_no_edge`, keep the Cost Gate block for reviewed side-cells.
- `DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT` -> `READY_FOR_PROBE`, but only as operator review before demo probe authority, not order authority.

## Verification

- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py -q` = 25 passed.
- `python3 -m pytest helper_scripts/research/tests/test_alpha_discovery_throughput.py -q` = 34 passed.
- `python3 -m py_compile helper_scripts/research/alpha_discovery_throughput/discovery_loop.py helper_scripts/research/alpha_discovery_throughput/runtime_runner.py` passed.

## Boundary

Source/test/docs only.

No PG table write, schema migration, Bybit private/signed/trading call, engine/API rebuild or restart, deploy, credential/auth/risk/order/strategy/runtime mutation, main Cost Gate relaxation, signal proof, execution proof, or promotion proof.

## Read

This makes the alpha killboard tell the truth: a plan is not a probe, and a probe is not justified until the blocked-signal evidence loop has produced reviewable outcomes.
