# WP6 Reward Ledger ProofPacket Bridge Rework

Date: 2026-07-07
Role: E1(worker)
Status: DONE

## Scope

Addressed E2 `RETURN_TO_E1` for `WP6-REWARD-LEDGER-PROOFPACKET-BRIDGE`.

Changed paths:

- `program_code/ml_training/reward_ledger.py`
- `program_code/ml_training/tests/test_reward_ledger.py`
- `docs/CCAgentWorkSpace/E1/workspace/reports/2026-07-07--wp6_reward_ledger_proofpacket_bridge_rework.md`
- `docs/CCAgentWorkSpace/E1/memory.md`

No staged files, no commit.

## Fixes

### MEDIUM-1

`reward_ledger_v1` records now carry canonical `source_artifacts` snapshots:

- `proof_packet`
- `demo_mutation_envelope`
- optional `registry_serving_contract`
- optional `acceptance_report_ref`

`validate_reward_record()` no longer certifies only the outer `record_hash`.
It recomputes and cross-checks:

- ProofPacket hash via `compute_proof_packet_hash`
- DemoMutationEnvelope hash via `compute_demo_mutation_envelope_hash`
- PIT manifest hash via `compute_pit_dataset_manifest_hash`
- Registry serving contract hash via `compute_registry_serving_contract_hash`
- Acceptance report hash via the local canonical acceptance hash helper

It also reruns upstream source validators through `_source_rejection_reasons()`.
Forging lineage fields and recomputing `record_hash` now rejects.

### MEDIUM-2

`build_reward_record_from_proof_and_mutation()` now has explicit registry
requiredness:

```python
registry_required: bool = True
registry_optional_reason: str = ""
```

Default is fail-closed for WP6 mutation-effect learning. If
`registry_required=True`, missing `registry_serving_contract` rejects with
`registry_lineage_missing`. If `registry_required=False`, caller must provide
the explicit allowed source reason
`execution_reward_not_training_contract_bound`; silent omission no longer
passes.

## Tests Added / Updated

- Forged lineage test: mutate proof/envelope/PIT/registry lineage hashes,
  recompute `record_hash`, and assert validation rejects.
- Mutated source artifact test: mutate embedded PIT source snapshot, recompute
  `record_hash`, and assert validation rejects.
- Missing registry contract without explicit optional mode rejects by default.
- Explicit `registry_required=False` without allowed reason rejects.
- Explicit `registry_required=False` with
  `registry_optional_reason="execution_reward_not_training_contract_bound"`
  passes for execution-only reward.
- Contract-bound happy path with registry contract still passes.

## Verification

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m py_compile program_code/ml_training/reward_ledger.py program_code/ml_training/proof_packet_contract.py program_code/ml_training/demo_mutation_envelope.py program_code/ml_training/registry_serving_contract.py
```

Result: PASS.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q program_code/ml_training/tests/test_reward_ledger.py program_code/ml_training/tests/test_proof_packet_contract.py program_code/ml_training/tests/test_demo_mutation_envelope.py program_code/ml_training/tests/test_demo_mutation_envelope_applier_mapping.py -p no:cacheprovider
```

Result: `109 passed in 0.48s`.

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

Line count:

- `program_code/ml_training/reward_ledger.py`: 878 lines
- `program_code/ml_training/tests/test_reward_ledger.py`: 698 lines

`reward_ledger.py` is above the 800-line review-attention threshold because the
E2 fix embeds and revalidates canonical source artifacts inside the source-only
contract. It remains below the 2000-line hard cap. Future WP6 additions should
split helper sections instead of growing this file.

## Boundary Statement

This rework is source-only. It does not read or write product runtime state,
DB, migrations, exchange/private endpoints, secrets, environment configuration,
order/probe paths, Cost Gate state, deployment state, live/mainnet state, model
reloads, symlinks, or real learning outcomes.

Runtime/loss-control remains blocked. This artifact is not bounded Demo outcome
ingestion, not registry persistence, not serving promotion, and not proof
promotion.

## Concerns

- `reward_ledger.py` now exceeds 800 lines. This is acceptable for this E2
  return because source-backed standalone validation is the core fix, but the
  next expansion should split source-artifact helpers.
- Durable append-only persistence, DB uniqueness, registry persistence, and
  actual bounded Demo outcome ingestion remain out of scope.
