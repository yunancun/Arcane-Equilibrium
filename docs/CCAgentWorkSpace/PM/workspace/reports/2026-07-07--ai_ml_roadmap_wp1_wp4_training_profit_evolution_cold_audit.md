# AI/ML Roadmap WP1-WP4 Training / Profit / Evolution Cold Audit

Date: 2026-07-07

PM sign-off: FAIL-STRICT-AS-STATED / PASS-AS-PREREQUISITES

This audit tests the stronger claim: completed WP1-WP4 can effectively train, derive the desired profit-seeking result when data supports it, and provide self-learning / training / evolution capability.

Strict verdict:

- WP1-WP4 are valuable and hardened prerequisites.
- They do not, by themselves, constitute a complete profit-seeking self-learning system.
- The stronger claim is not confirmed because the actual training pipeline is not contract-bound to WP1-WP4 and the reward/mutation/evolution loop is still downstream work.

No runtime mutation, DB write, exchange/private read, MCP server/config, secret access, order/probe, Cost Gate change, deploy, live, or mainnet action was performed.

## Frozen State

- Audit target snapshot HEAD: `798843f23b2fda66117cf95bfe7c996f97fdf543`
- Audit target snapshot `origin/main`: `798843f23b2fda66117cf95bfe7c996f97fdf543`
- Worktree had pre-existing WP5/memory dirty files; this audit did not touch them.
- Note: after the audit snapshot, a separate WP5 local commit advanced the working branch. This report's code/test evidence is scoped to the frozen WP1-WP4 target snapshot above.

## WP1-WP4 Actual Capability

| WP | Provides | Does not provide yet |
|---|---|---|
| WP1 ProofPacket | Candidate-matched after-cost proof contract; rejects no-fill/reward pollution and authority aliases. | Does not create fills, train a model, or prove profit without real candidate-matched outcomes. |
| WP2 PIT Dataset Manifest | Point-in-time dataset contract; rejects leakage-prone/unpinned/malformed dataset evidence. | Is not currently enforced inside `run_training_pipeline.py`; training can run without producing or consuming a PIT manifest. |
| WP3 Registry Serving Contract | Advisory-only serving metadata contract; q10/q50/q90 persistence is atomic when contract is supplied. | `run_training_pipeline.py` does not generate/pass `registry_serving_contract`; registry rows can be written without the WP3 contract path. |
| WP4 AdvisoryReviewPacket | Inactive, input-hash-bound, no-authority advisory packet for L2/MLDE/DreamEngine outputs. | Does not produce a mutation envelope, reward update, strategy change, or self-learning loop. |

## Evidence

### Contract + Training / Bandit Tests

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q \
  program_code/ml_training/tests/test_run_training_pipeline.py \
  program_code/ml_training/tests/test_quantile_trainer.py \
  program_code/ml_training/tests/test_regime_bandit_allocator.py \
  program_code/ml_training/tests/test_proof_packet_contract.py \
  program_code/ml_training/tests/test_pit_dataset_manifest.py \
  program_code/ml_training/tests/test_registry_serving_contract.py \
  program_code/ml_training/tests/test_advisory_review_packet.py \
  -p no:cacheprovider
=> 165 passed, 1 skipped
```

### Static Integration Probe

Probe result:

```text
run_training_pipeline:
  pit_dataset_manifest: False
  registry_serving_contract: False
  proof_packet: False
  advisory_review_packet: False
  demo_mutation_envelope: False

quantile_trainer:
  pit_dataset_manifest: False
  registry_serving_contract: False
  proof_packet: False
  advisory_review_packet: False
  demo_mutation_envelope: False

mlde_shadow_advisor:
  advisory_review_packet: True
  pit_dataset_manifest / registry_serving_contract / proof_packet / demo_mutation_envelope: False

regime_bandit_allocator:
  pit_dataset_manifest / registry_serving_contract / proof_packet / advisory_review_packet / demo_mutation_envelope: False
```

Interpretation:

- WP4 is wired into MLDE/advisory output.
- WP1/WP2/WP3 are not yet wired into the actual training pipeline as mandatory pre/post contracts.
- Bandit/self-learning allocation exists separately, but it is not coupled to WP1-WP4.

### Quantile Dry-Run Pipeline Probe

System Python:

```text
RESULT success=False
RESULT stages=['etl', 'labels']
RESULT error=quantile training failed: lightgbm not installed
```

Project venv has the required training/export deps:

```text
lightgbm 4.6.0
onnx 1.21.0
skl2onnx 1.20.0
```

Using the project venv, a quantile dry-run did train and export three ONNX files plus an acceptance report, but final pipeline success was fail-loud blocked by missing registry DB connectivity:

```text
RESULT success=False
RESULT stages=['etl', 'labels']
RESULT error=required registry persistence unavailable for grid_trading/demo verdict=shadow_only: DB connectivity precheck failed

Generated:
- edge_predictor_demo_grid_trading_q10_edge_p3_v1_2026-07-06.onnx
- edge_predictor_demo_grid_trading_q50_edge_p3_v1_2026-07-06.onnx
- edge_predictor_demo_grid_trading_q90_edge_p3_v1_2026-07-06.onnx
- grid_trading_demo_ALL_acceptance_report.json
```

Acceptance report excerpt:

```text
training_success=true
verdict=shadow_only
all_hard_gates_pass=false
verdict_reason="sample >= prod but gate(s) failed: ['crossing_rate', 'lgbm_vs_linear_qr'] -> downgrade to shadow"
n_samples_labeled=600
n_holdout=60
pinball_skill passed
decile_lift passed
coverage_error passed
crossing_rate failed
lgbm_vs_linear_qr failed
embargo_enforced=false
```

The produced acceptance report contained no WP contract binding fields:

```text
pit_dataset_manifest=False
registry_serving_contract=False
proof_packet=False
advisory_review_packet=False
demo_mutation_envelope=False
reward_ledger=False
self_learning_state=False
```

## Findings

### P1 - Training is not PIT-manifest-gated

`run_training_pipeline.py` can load data, train, generate acceptance reports, and export ONNX without requiring `pit_dataset_manifest_v1`.

Required next work:

- Add `training_run_contract_v1` or equivalent wrapper that requires a valid `pit_dataset_manifest_v1` before quantile training starts.
- Persist the manifest hash into acceptance reports and registry metadata.

### P1 - Registry serving contract is not generated by the training pipeline

WP3 is implemented and atomic when supplied, but `run_training_pipeline.py` currently calls `register_quantile_trio_from_onnx_out(...)` without `registry_serving_contract`.

Required next work:

- Generate `registry_serving_contract_v1` from acceptance report + PIT manifest + ONNX artifact hashes.
- Pass it into `register_quantile_trio_from_onnx_out()`.
- Fail closed if registry contract validation fails.

### P1 - ProofPacket is outcome proof, not training proof

WP1 proves candidate-matched after-cost outcomes or blocks no-fill. It is not emitted by the training pipeline.

Required next work:

- After bounded Demo execution, generate ProofPacket from actual candidate-matched fills, fees, slippage, controls, and PIT/registry lineage.
- Feed only valid ProofPackets into promotion/outcome review.

### P1 - Self-learning / evolution loop is not complete in WP1-WP4

Useful machinery exists outside WP1-WP4:

- `quantile_trainer.py`: supervised q10/q50/q90 training and gates.
- `run_training_pipeline.py`: ETL -> train -> CQR -> acceptance -> ONNX -> registry persistence.
- `regime_bandit_allocator.py`: learns to allocate positive arms and flat when all arms are negative.
- `adaptive_demo_profit_engine/reward_source.py`: read-only demo reward source.

But WP1-WP4 do not connect these into a closed evolution loop.

Missing bridge:

- DemoMutationEnvelope / reward ledger / mutation applier / adjudicator lifecycle.
- Fresh bounded Demo outcomes feeding rewards.
- Contract-bound retraining trigger.
- Drift/effect review that decides continue, rollback, or stop.

### P2 - Dry-run training can produce shadow models but not profit proof

The venv dry-run produced model artifacts and an acceptance report, but the synthetic run downgraded to `shadow_only`.

This is good fail-closed behavior, not a failure of the direction. It proves the trainer can learn from synthetic signal; it does not prove profitability, microstructure realism, fees/slippage, repeat/OOS, or candidate-matched PnL.

## Direct Answer

Can WP1-WP4 effectively train?

- Not by themselves.
- The codebase has a trainable quantile path, and WP1-WP4 can make it much safer.
- But WP2/WP3/WP1 are not yet mandatory inside the training pipeline.

Can WP1-WP4 derive the desired result, depending on data?

- They can help prevent false positives and bad promotion.
- They cannot guarantee profitable results.
- If data contains real, stable, after-cost edge, the existing quantile trainer and bandit allocator are capable of detecting/using signal under gates, but WP1-WP4 are not yet the full data-to-profit loop.

Can WP1-WP4 pursue profit?

- Only indirectly.
- They improve proof quality and advisory safety.
- They do not execute bounded Demo, allocate capital, mutate strategy, or close a reward loop.

Do WP1-WP4 provide self-learning / training / evolution?

- They provide the contract substrate for future self-learning.
- They do not yet provide the closed learning/evolution system.

## Cold Verdict

`FAIL-STRICT-AS-STATED`

Reason:

- The completed WP1-WP4 are necessary prerequisites, not sufficient system capability.
- A mature claim requires:
  1. PIT manifest mandatory in `run_training_pipeline`.
  2. Registry serving contract generated and persisted for q10/q50/q90.
  3. Advisory packets chained to mutation envelopes, not just inactive output.
  4. Reward ledger consumes candidate-matched ProofPackets only.
  5. Bounded Demo execution outcomes feed bandit/training under loss controls.
  6. Effect review decides promote / continue / rollback / stop.

`PASS-AS-PREREQUISITES`

Reason:

- WP1-WP4 now enforce the right boundaries for proof, PIT data, advisory serving metadata, and inactive AI advisory output.
- They reduce false proof and unauthorized mutation risk.
- They are the right next layer to build on.

## Recommended Next Engineering Direction

Do not restart the roadmap. Tighten the next work item order:

1. `WP2.1-TRAINING-RUN-PIT-MANIFEST-GATE`
2. `WP3.1-TRAINING-REGISTRY-CONTRACT-EMISSION`
3. `WP5-DEMO-MUTATION-ENVELOPE-CONTRACT`
4. `WP6-REWARD-LEDGER-PROOFPACKET-BRIDGE`
5. `WP7-EFFECT-REVIEW-AND-STOP-LOOP`

Only after these can the project honestly claim a source-level autonomous learning loop. Real trading-profit claims still require bounded Demo outcomes and later promotion review.
