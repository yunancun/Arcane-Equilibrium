# Learning Proof/Promotion Gate Source Checkpoint

Date: 2026-06-29
Owner: PM
Status: DONE_WITH_CONCERNS

## Summary

PM advanced `P0-LEARN-PROOF-PROMOTION-GATE` source-only at source commits `ad43b638` and `ed8c3595`.

The new helper `helper_scripts/research/cost_gate_learning_lane/learning_proof_promotion_gate.py` emits deterministic `cost_gate_learning_proof_promotion_gate_v1` blocked/ready operator-review verdict packets. It consumes:

- `cost_gate_learning_serving_snapshot_v1`
- `cost_gate_learning_adjudicator_v1`
- `cost_gate_learning_candidate_proof_evidence_v1`
- optional proof-exclusion artifacts

## Contract

The gate requires all of the following before a review-ready verdict can be emitted:

- ready serving snapshot and matching model/snapshot linkage
- matching adjudicator `REVIEW` decision
- row-backed candidate-matched Demo fills
- real fee, slippage, spread, capacity, and net-of-fees evidence
- execution realism and tail-risk review pass
- OOS and repeat validation pass
- matched controls/baseline outperformance
- proof-exclusion pass

Hardened coverage ensures summary counts alone cannot clear proof and that cleanup fills, replay-only rows, unattributed rows, and lineage-broken rows remain proof-excluded.

## Verification

- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/learning_proof_promotion_gate.py`
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_learning_proof_promotion_gate.py` -> `11 passed`
- ML source chain adjacent tests -> `52 passed`
- `PYTHONPATH=helper_scripts/cron:helper_scripts/research python3 -m pytest -q helper_scripts/cron/tests/test_learning_stack_health_snapshot.py` -> `7 passed`
- `git diff --check`

## Boundary

This checkpoint is source/test/docs only. It grants no runtime sync, model load, serving slot write, registry/PG write, runtime/env/service/crontab mutation, Bybit call, order/cancel/modify, Decision Lease action, Cost Gate lowering, probe/order/live authority, promotion authority, or promotion/profit proof.

Runtime remains last verified at `f1d1a26c19954a79d28014f75451c4a882f8d450`. The latest materialized serving snapshot remains blocked by training/registry repair, and strict candidate evidence still has no row-backed candidate-matched fill evidence.

## Next

ML source contract chain is complete through proof/promotion gate. Actual proof and promotion remain blocked until serving repair closes, Demo credential/mode readiness is corrected, final-window execution gates pass, and row-backed candidate-matched Demo fills with full fee/slippage/control evidence exist.
