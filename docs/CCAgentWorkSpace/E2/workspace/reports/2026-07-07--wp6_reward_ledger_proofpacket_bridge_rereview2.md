# WP6 Reward Ledger ProofPacket Bridge E2 Re-review 2

Date: 2026-07-07
Role: E2(explorer)
Verdict: PASS_TO_E4

## Scope

Source-only second re-review of E1 rework2 for
`WP6-REWARD-LEDGER-PROOFPACKET-BRIDGE`.

Reviewed:

- `program_code/ml_training/reward_ledger.py`
- `program_code/ml_training/tests/test_reward_ledger.py`
- E1 rework2 report
  `docs/CCAgentWorkSpace/E1/workspace/reports/2026-07-07--wp6_reward_ledger_proofpacket_bridge_rework2.md`

No product code edits, no staging, no commit. Runtime/loss-control remains
blocked.

## Findings

No blocking findings.

### REVIEW-ATTENTION-1 -- `reward_ledger.py` is above 800 lines

`program_code/ml_training/reward_ledger.py` is 913 lines. This exceeds the
repo review-attention threshold and remains below the 2000-line hard cap. I do
not classify this as a blocker for this source-only fix because the rework is
localized to optional-registry contradiction detection and tests. Future WP6
growth should split source-artifact / lineage / marker helpers before adding
more behavior to this file.

## Required Checks

1. Prior adversarial optional-registry probe is closed.
   `registry_required=False` plus allowed optional reason rejects when source
   artifacts assert contract-bound state. Direct probe result:
   `CHECK1_BUILDER_REJECT registry_optional_source_contract_bound:$.acceptance_report_ref.contract_bound`.

2. Post-build mutation of `source_artifacts` plus recomputed `record_hash`
   rejects. Direct probe added both
   `source_artifacts.acceptance_report_ref.contract_bound=True` and
   `source_artifacts.proof_packet.metadata.registry_required=True`, recomputed
   `record_hash`, and validation returned:
   `False registry_optional_source_contract_bound:$.acceptance_report_ref.contract_bound`.

3. Clean explicit optional execution-only fixture still passes:
   `CHECK3_CLEAN_OPTIONAL True ok`.

4. Registry-required happy path with registry contract still passes:
   `CHECK4_REQUIRED_REGISTRY True ok`.

5. Previous original probes remain closed:
   forged lineage/source artifact hashes plus recomputed record hash reject with
   `lineage_proof_packet_hash_source_mismatch` and
   `lineage_registry_serving_contract_hash_source_mismatch`; missing registry
   contract without optional mode rejects with `registry_lineage_missing`.

6. No side-effect import/surface found in `reward_ledger.py` by static grep for
   DB, HTTP, socket, subprocess, IPC, order, SQL mutation, and environment
   access terms.

7. Line count: `reward_ledger.py` 913 lines, `test_reward_ledger.py` 752 lines.
   Classified as review-attention, not blocker.

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

```bash
wc -l program_code/ml_training/reward_ledger.py program_code/ml_training/tests/test_reward_ledger.py
```

Result: `913` and `752` lines.

## Boundary Statement

This was a source-only E2 re-review. I did not read or mutate product runtime
state, DB, migrations, exchange/private endpoints, secrets, environment
configuration, order/probe paths, Cost Gate state, deployment state,
live/mainnet state, model reloads, symlinks, registry persistence, or real
learning outcomes. This review does not authorize bounded Demo outcome
ingestion, serving promotion, registry persistence, Cost Gate changes, orders,
probes, runtime mutation, or live/mainnet activity.
