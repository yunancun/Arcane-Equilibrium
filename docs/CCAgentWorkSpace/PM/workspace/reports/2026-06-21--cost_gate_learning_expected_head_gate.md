# PM Report: Cost-Gate Learning Expected-Head Gate

Date: 2026-06-21

## Objective

Make cost-gate learning activation verifiable against the exact PM-pushed commit, without relying only on runtime local upstream refs. A `trade-core` checkout may show stale ahead/behind counts if it has not fetched recently; activation needs a direct HEAD-vs-expected-SHA check.

## Change

Extended `helper_scripts/research/cost_gate_learning_lane/status.py`:

- added CLI `--expected-head`
- added env fallback `OPENCLAW_EXPECTED_SOURCE_HEAD`
- added full `git_head`
- added `expected_head`
- added `expected_head_status`
- added `expected_head_matches`
- added `expected_head_error`
- adds `expected_source_head_mismatch`, `expected_source_head_invalid`, or `expected_source_head_unverified` to `activation_blockers` when appropriate

The expected head can be a 7-40 character hex SHA prefix. It is compared against the local git `HEAD`; the preflight does not fetch, pull, reset, clean, deploy, restart, or mutate runtime state.

## Runtime Context

Current Linux `trade-core` remains at `917be4cc`, behind origin/main by its local refs and dirty. Cost-gate learning artifacts remain absent, so demo cost-gate rejects are not yet accumulating learning evidence.

## Verification

- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py -q` = 36 passed
- `python3 -m pytest helper_scripts/research/tests/test_alpha_discovery_throughput.py -q` = 34 passed
- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/status.py` passed
- `PYTHONPATH=helper_scripts/research python3 -m cost_gate_learning_lane.status --data-dir /tmp/openclaw --expected-head 72e9cf8f --print-json` passed and reported `expected_head_status=MATCH` while still blocking activation due dirty local checkout

## Boundary

Source/test/docs + read-only local/runtime probes only. No deploy, restart, PG write/schema migration, Bybit private/signed/trading call, order authority, auth/risk/runtime/config mutation, main Cost Gate lowering, execution proof, signal proof, or promotion proof.
