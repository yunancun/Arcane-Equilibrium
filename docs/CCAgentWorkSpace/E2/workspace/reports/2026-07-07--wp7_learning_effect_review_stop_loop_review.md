# WP7 Learning Effect Review Stop Loop E2 Review

Date: 2026-07-07
Role: E2(explorer/reviewer)
Verdict: `RETURN_TO_E1`

## Scope And Boundary

Reviewed narrow E1 implementation for `WP7-EFFECT-REVIEW-AND-STOP-LOOP`:

- `program_code/ml_training/learning_effect_review.py`
- `program_code/ml_training/tests/test_learning_effect_review.py`
- `program_code/ml_training/reward_ledger.py` as upstream contract
- PA design and E1 implementation report

No product code edits, no staging, no commit, no runtime mutation, no DB/private/exchange/MCP/secret/order/probe/Cost Gate/deploy/live/model reload/symlink action. Existing dirty files under memory, IBKR, and Bybit `control_api_v1` were ignored as unrelated.

## Verdict

`RETURN_TO_E1`

The source-only shape is mostly aligned and the focused suite is green, but three fail-closed contract holes remain. Two allow a packet to stay `valid=True / promote_review_only` after adversarial mutation plus `review_hash` recompute.

## Findings

### MED-1: Top-level proof/mutation/reward refs can be forged or dropped while still promoting

File/lines:

- `program_code/ml_training/learning_effect_review.py:369`
- `program_code/ml_training/learning_effect_review.py:384`

`_evidence_reasons()` checks `inputs.reward_ledger_refs` only by iterating supplied refs; it does not require the ref set to exactly cover every embedded reward record. It also checks `proof_packet_refs` and `mutation_envelope_refs` only for non-empty presence, not equality with lineage/source artifact hashes from the embedded reward records.

Adversarial probe result:

```text
baseline LearningEffectReviewValidation(valid=True, decision='promote_review_only', reason='profitable_after_cost_repeat_ready_for_operator_review', reasons=('profitable_after_cost_repeat_ready_for_operator_review',), review_only=True, authority_boundary_violation=False)
forged_refs LearningEffectReviewValidation(valid=True, decision='promote_review_only', reason='profitable_after_cost_repeat_ready_for_operator_review', reasons=('profitable_after_cost_repeat_ready_for_operator_review',), review_only=True, authority_boundary_violation=False)
dropped_reward_refs LearningEffectReviewValidation(valid=True, decision='promote_review_only', reason='profitable_after_cost_repeat_ready_for_operator_review', reasons=('profitable_after_cost_repeat_ready_for_operator_review',), review_only=True, authority_boundary_violation=False)
```

Why this matters: PA required reward record hashes, refs, and `source_artifacts` not be forgeable by mutating the packet after hash recompute. This also violates the required proof/mutation hash mismatch rejection semantics.

Minimal fix criteria:

- Derive expected reward ref set from `source_artifacts.reward_records` and require exact set equality by `(record_id, record_hash)`.
- Derive expected proof and mutation hash sets from each validated reward record lineage/source artifacts and require exact equality with `inputs.proof_packet_refs` and `inputs.mutation_envelope_refs`.
- Add tests for forged proof refs, forged mutation refs, dropped reward refs, and extra reward refs after recomputing `review_hash`.

### MED-2: Truthy trading/execution authority aliases are not caught

File/lines:

- `program_code/ml_training/learning_effect_review.py:70`
- `program_code/ml_training/learning_effect_review.py:521`
- `program_code/ml_training/tests/test_learning_effect_review.py:193`

The alias scanner catches explicit `order_allowed`, `live_enabled`, `mainnet_allowed`, Cost Gate, model reload, symlink promotion, etc. It misses common trading/execution aliases such as `trade_allowed`, `trading_enabled`, `enable_trading`, and `execution_authority_granted`.

Adversarial probe result:

```text
trade_allowed True promote_review_only False profitable_after_cost_repeat_ready_for_operator_review
trading_enabled True promote_review_only False profitable_after_cost_repeat_ready_for_operator_review
execution_authority_granted True promote_review_only False profitable_after_cost_repeat_ready_for_operator_review
enable_trading True promote_review_only False profitable_after_cost_repeat_ready_for_operator_review
live_enabled False stop_evidence True authority_boundary_violation:$.metadata.live_enabled
mainnet_allowed False stop_evidence True authority_boundary_violation:$.metadata.mainnet_allowed
costGateLowered False stop_evidence True authority_boundary_violation:$.metadata.costGateLowered
symlinkPromotionAllowed False stop_evidence True authority_boundary_violation:$.metadata.symlinkPromotionAllowed
```

Why this matters: PA review focus explicitly says no truthy alias can smuggle order/live/mainnet/Cost Gate/model reload/symlink/direct-promotion authority. In this trading codebase, `trading_enabled`/`trade_allowed`/`execution_authority_granted` are order/execution authority aliases.

Minimal fix criteria:

- Extend authority detection to reject truthy `trade_*`, `trading_*`, `enable_trading`, and `execution_*authority*` style aliases without false-positive blocking inert evidence fields such as `execution_identity`.
- Add parameterized tests for these aliases in nested metadata and source artifacts.

### MED-3: Malformed or truthy-string loss controls can still produce `promote_review_only`

File/lines:

- `program_code/ml_training/learning_effect_review.py:331`
- `program_code/ml_training/learning_effect_review.py:333`
- `program_code/ml_training/learning_effect_review.py:343`

`_loss_limit_reasons()` treats `loss_limits.breach` as a breach only when it is exactly boolean `True`, and it only requires `max_cumulative_loss_bps` and `max_single_record_loss_bps`. Missing/non-numeric `max_consecutive_negative_windows` and missing `max_cumulative_loss_usdt` do not fail closed.

Adversarial probe result:

```text
breach_string_true True promote_review_only profitable_after_cost_repeat_ready_for_operator_review
bad_consecutive True promote_review_only profitable_after_cost_repeat_ready_for_operator_review
missing_consecutive True promote_review_only profitable_after_cost_repeat_ready_for_operator_review
missing_usdt True promote_review_only profitable_after_cost_repeat_ready_for_operator_review
```

Why this matters: PA required missing or malformed `loss_limits`, explicit breaches, cumulative loss, single-record loss, and consecutive negative-window breach to preempt `continue`/`promote_review_only`.

Minimal fix criteria:

- Treat truthy breach aliases/strings as `stop_loss_control`.
- Require all PA loss-control fields to be present and finite unless an explicit policy marks a field optional.
- Add tests for `breach="true"`, missing `max_cumulative_loss_usdt`, missing/non-numeric `max_consecutive_negative_windows`, and ensure each returns `stop_loss_control` before profitable decisions.

## Coverage Assessment

`test_learning_effect_review.py` covers the PA happy path and many required negative cases, but it does not cover the meaningful adversarial matrix around:

- exact ref-set integrity after `review_hash` recompute;
- broader trading/execution authority aliases;
- malformed loss-limit fields and truthy breach values.

Those gaps explain why the focused suite is green while the above probes still promote.

## Verification Commands

Exact requested command outputs:

```text
$ PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m py_compile program_code/ml_training/learning_effect_review.py program_code/ml_training/reward_ledger.py program_code/ml_training/proof_packet_contract.py program_code/ml_training/demo_mutation_envelope.py
```

No output; exit code 0.

```text
$ PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q program_code/ml_training/tests/test_learning_effect_review.py program_code/ml_training/tests/test_reward_ledger.py program_code/ml_training/tests/test_proof_packet_contract.py program_code/ml_training/tests/test_demo_mutation_envelope.py -p no:cacheprovider
........................................................................ [ 61%]
.............................................                            [100%]
117 passed in 1.64s
```

```text
$ git diff --check -- program_code/ml_training/learning_effect_review.py program_code/ml_training/tests/test_learning_effect_review.py docs/CCAgentWorkSpace/E1/workspace/reports/2026-07-07--wp7_learning_effect_review_stop_loop_implementation.md
```

No output; exit code 0.

## Notes

- `learning_effect_review.py` is 635 lines, below the 800-line review-attention threshold.
- `reward_ledger.py` remains 913 lines, already known review-attention but upstream WP6 passed after rework.
- Source-only boundary is clean by static grep: no file/network/DB/subprocess/env/runtime operations in `learning_effect_review.py`.
