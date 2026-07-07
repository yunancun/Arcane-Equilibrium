# WP6 Reward Ledger ProofPacket Bridge Implementation

Date: 2026-07-07
Role: E1(worker)
Status: DONE

## Scope

Implemented `reward_ledger_v1` as a source-only additive bridge between:

- `proof_packet_v1`
- `demo_mutation_envelope_v1`
- optional `registry_serving_contract_v1`
- caller-provided effect window / acceptance report reference

Changed paths:

- `program_code/ml_training/reward_ledger.py`
- `program_code/ml_training/tests/test_reward_ledger.py`
- `docs/CCAgentWorkSpace/E1/workspace/reports/2026-07-07--wp6_reward_ledger_proofpacket_bridge_implementation.md`
- `docs/CCAgentWorkSpace/E1/memory.md`

No staged files, no commit.

## Implementation Notes

- Added constants, `RewardLedgerValidation`, `RewardLedgerError`, `compute_reward_record_hash`, `validate_reward_record`, `build_reward_record_from_proof_and_mutation`, `extract_reward_record`.
- Added source-only batch helpers `dedupe_reward_records` and `validate_reward_batch`, covered by tests.
- Builder calls upstream `validate_proof_packet` and `validate_demo_mutation_envelope`.
- Builder requires ProofPacket `PROOF_READY`, Demo envelope `STATUS_COUNTABLE`, effective learning countable, exact recomputed proof hash, exact recomputed envelope hash, exact `proof_linkage.proof_packet_hash`, Demo engine mode, PIT manifest hash, closed point-in-time effect window, and optional registry contract validation when required.
- Reward record carries candidate identity, execution identity, cost identity, reward, controls, lineage, mutation metadata, effect window, no-authority flags, and deterministic `record_hash`.
- Fail-closed rejection covers no-fill, invalid ProofPacket, cleanup/proof-excluded, non-demo/live envelopes, dry-run, dedupe, audit-only/non-countable envelopes, proof-linkage mismatch, source candidate mismatch, missing PIT lineage, registry-required missing lineage, and authority aliases.

## Verification

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m py_compile program_code/ml_training/reward_ledger.py program_code/ml_training/proof_packet_contract.py program_code/ml_training/demo_mutation_envelope.py program_code/ml_training/registry_serving_contract.py
```

Result: PASS.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q program_code/ml_training/tests/test_reward_ledger.py program_code/ml_training/tests/test_proof_packet_contract.py program_code/ml_training/tests/test_demo_mutation_envelope.py program_code/ml_training/tests/test_demo_mutation_envelope_applier_mapping.py -p no:cacheprovider
```

Result: `104 passed in 0.34s`.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q program_code/ml_training/tests/test_pit_dataset_manifest.py program_code/ml_training/tests/test_registry_serving_contract.py program_code/ml_training/tests/test_run_training_pipeline.py program_code/ml_training/tests/test_model_registry.py -p no:cacheprovider
```

Result: `83 passed in 0.60s`.

```bash
rg -n "psycopg2|asyncpg|requests|httpx|urllib|socket|subprocess|one_shot_ipc_call|ipc_dispatch|place_order|create_order|cancel_order|submit_order|INSERT INTO|UPDATE learning|DELETE FROM|os\.environ|getenv" program_code/ml_training/reward_ledger.py
```

Result: PASS, no matches (`rg` exit 1).

```bash
git diff --check -- program_code/ml_training/reward_ledger.py program_code/ml_training/tests/test_reward_ledger.py
```

Result: PASS.

## Boundary Statement

This implementation is source-only. It does not read or write product runtime state, DB, migrations, exchange/private endpoints, secrets, environment configuration, order/probe paths, Cost Gate state, deployment state, live/mainnet state, model reloads, symlinks, or real learning outcomes.

Runtime/loss-control remains blocked. This artifact is not bounded Demo outcome ingestion, not registry persistence, not serving promotion, and not proof promotion.

## Concerns

- `dedupe_reward_records` is source-only in-memory convenience; durable uniqueness remains out of scope until a future reviewed persistence design.
- Registry lineage is inferred as required from `effect_window.registry_required`, `acceptance_report_ref.registry_required`, `acceptance_report_ref.contract_bound`, or `pit_dataset_manifest_binding.contract_bound_run`. Future callers should keep that requirement explicit.
- `reward_ledger.py` is 796 lines after implementation, intentionally kept below the repo's 800-line review-attention threshold.
