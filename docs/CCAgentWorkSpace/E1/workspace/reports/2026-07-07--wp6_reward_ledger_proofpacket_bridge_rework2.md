# WP6 Reward Ledger ProofPacket Bridge Rework 2

Date: 2026-07-07
Role: E1(worker)
Status: DONE

## Scope

Addressed the second E2 `RETURN_TO_E1` for
`WP6-REWARD-LEDGER-PROOFPACKET-BRIDGE`.

Changed paths:

- `program_code/ml_training/reward_ledger.py`
- `program_code/ml_training/tests/test_reward_ledger.py`
- `docs/CCAgentWorkSpace/E1/workspace/reports/2026-07-07--wp6_reward_ledger_proofpacket_bridge_rework2.md`
- `docs/CCAgentWorkSpace/E1/memory.md`

No staged files, no commit.

## Fix

Explicit optional registry mode now fails closed when caller-provided source
artifacts contradict the optional lineage.

When `registry_required=False`, both builder and validator recursively inspect
the embedded source inputs for truthy contract-bound markers:

- `registry_required`
- `contract_bound`
- `contract_bound_run`

The scan covers ProofPacket, DemoMutationEnvelope, effect window, registry
contract, acceptance report reference, and nested snapshots such as PIT
manifest or binding metadata. Any marker produces
`registry_optional_source_contract_bound:<path>` and rejects the record even if
`registry_optional_reason` is the allowed
`execution_reward_not_training_contract_bound` reason.

This closes the E2 probe where lineage claimed execution-only optional mode
while `effect_window.registry_required=True` or
`acceptance_report_ref.contract_bound=True` asserted a contract-bound source.
It also closes forged records where `source_artifacts` are mutated after build
and `record_hash` is recomputed.

## Tests Added

- `registry_required=False` + allowed optional reason +
  `effect_window.registry_required=True` rejects.
- `registry_required=False` + allowed optional reason +
  `acceptance_report_ref.contract_bound=True` rejects.
- Forged optional record with mutated
  `source_artifacts.acceptance_report_ref.contract_bound=True` and recomputed
  `record_hash` rejects in `validate_reward_record()`.
- Existing clean execution-only optional fixture still passes.
- Existing registry-required happy path with registry contract still passes.

## Verification

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m py_compile program_code/ml_training/reward_ledger.py program_code/ml_training/proof_packet_contract.py program_code/ml_training/demo_mutation_envelope.py program_code/ml_training/registry_serving_contract.py
```

Result: PASS.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q program_code/ml_training/tests/test_reward_ledger.py program_code/ml_training/tests/test_proof_packet_contract.py program_code/ml_training/tests/test_demo_mutation_envelope.py program_code/ml_training/tests/test_demo_mutation_envelope_applier_mapping.py -p no:cacheprovider
```

Result: `112 passed in 0.51s`.

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

- `program_code/ml_training/reward_ledger.py`: 913 lines
- `program_code/ml_training/tests/test_reward_ledger.py`: 752 lines

`reward_ledger.py` remains above the 800-line review-attention threshold and
below the 2000-line hard cap. This rework kept the E2 fix local; future WP6
expansion should split source-artifact / marker helpers instead of growing the
file further.

## Boundary Statement

This rework is source-only. It does not read or write product runtime state,
DB, migrations, exchange/private endpoints, secrets, environment configuration,
order/probe paths, Cost Gate state, deployment state, live/mainnet state, model
reloads, symlinks, or real learning outcomes.

Runtime/loss-control remains blocked. This artifact is not bounded Demo outcome
ingestion, not registry persistence, not serving promotion, and not proof
promotion.

## Concerns

- The new recursive contract-bound marker scan is intentionally narrow and only
  treats explicit truthy `registry_required`, `contract_bound`, or
  `contract_bound_run` keys as registry-required source evidence.
- `reward_ledger.py` is now 913 lines. Future additions should split helpers.
- Durable append-only persistence, DB uniqueness, registry persistence, and
  actual bounded Demo outcome ingestion remain out of scope.
