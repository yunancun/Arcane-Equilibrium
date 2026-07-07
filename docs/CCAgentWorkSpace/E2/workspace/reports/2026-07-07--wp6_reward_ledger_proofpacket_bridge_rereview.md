# WP6 Reward Ledger ProofPacket Bridge E2 Re-review

Date: 2026-07-07
Role: E2(explorer)
Verdict: RETURN_TO_E1

## Scope

Source-only re-review of E1 rework for `WP6-REWARD-LEDGER-PROOFPACKET-BRIDGE`.

Reviewed:

- `program_code/ml_training/reward_ledger.py`
- `program_code/ml_training/tests/test_reward_ledger.py`
- E1 rework report `docs/CCAgentWorkSpace/E1/workspace/reports/2026-07-07--wp6_reward_ledger_proofpacket_bridge_rework.md`

No implementation edits, no staging, no commit. Runtime/loss-control remains blocked.

## Findings

### MEDIUM-1 — Optional registry mode can override contradictory contract-bound source claims

Location: `program_code/ml_training/reward_ledger.py:351`, `program_code/ml_training/reward_ledger.py:431`, `program_code/ml_training/reward_ledger.py:626`

E1 fixed the previous silent-default bug: `build_reward_record_from_proof_and_mutation()` now defaults `registry_required=True`, and omitting both registry contract and explicit optional mode rejects.

However, the optional path is still not limited to an actually execution-only source context. If the caller supplies:

- `registry_required=False`
- `registry_optional_reason="execution_reward_not_training_contract_bound"`
- no `registry_serving_contract`

then the builder/validator accepts the record even when caller-provided source artifacts simultaneously assert a registry/contract-bound run, such as:

- `effect_window.registry_required=True`
- `acceptance_report_ref.registry_required=True`
- `acceptance_report_ref.contract_bound=True`

Adversarial probe:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 - <<'PY'
from ml_training.tests.test_reward_ledger import _valid_proof_packet, _valid_envelope, _valid_effect_window
from ml_training.reward_ledger import build_reward_record_from_proof_and_mutation, validate_reward_record, REGISTRY_OPTIONAL_REASON_EXECUTION_REWARD, RewardLedgerError
p = _valid_proof_packet()
e = _valid_envelope(p)
w = _valid_effect_window(registry_required=True)
acceptance = {'acceptance_report_id':'acc-1','registry_required': True, 'contract_bound': True}
try:
    r = build_reward_record_from_proof_and_mutation(
        proof_packet=p,
        demo_mutation_envelope=e,
        effect_window=w,
        registry_serving_contract=None,
        acceptance_report_ref=acceptance,
        registry_required=False,
        registry_optional_reason=REGISTRY_OPTIONAL_REASON_EXECUTION_REWARD,
    )
except RewardLedgerError as exc:
    print('REJECT', str(exc))
else:
    v = validate_reward_record(r)
    print('ACCEPT', v.reward_ready, v.reason, r['lineage']['registry_required'], r['effect_window'].get('registry_required'), r['source_artifacts']['acceptance_report_ref'].get('contract_bound'))
PY
```

Observed:

```text
ACCEPT True ok False True True
```

This violates the re-review check that explicit `registry_required=False` plus optional reason should pass only for the intended execution-only reward mode. The current implementation treats the caller flag as stronger than contradictory source claims, so a contract-bound acceptance packet can be recorded without registry lineage.

Suggested E1 direction: keep the new fail-closed default, but reject contradictions when optional mode is selected. At minimum, if `registry_required=False`, fail when `effect_window`, `acceptance_report_ref`, PIT binding metadata, or other source artifacts carry `registry_required=True`, `contract_bound=True`, `contract_bound_run=True`, or equivalent contract-bound markers. Add a regression test for the probe above.

## Re-checks Passed

- Previous MED-1 adversarial probe now rejects: mutating ProofPacket/envelope/PIT/registry lineage hashes and recomputing `record_hash` returns `False invalid lineage_proof_packet_hash_source_mismatch` with all four source mismatch reasons present.
- Previous MED-2 adversarial probe now rejects: omitting registry contract and omitting explicit optional mode raises `RewardLedgerError: registry_lineage_missing`.
- Explicit `registry_required=False` plus `registry_optional_reason="execution_reward_not_training_contract_bound"` passes for a clean optional-mode fixture with no contradictory contract-bound source claims.
- `source_artifacts` snapshots now materially participate in validation: lineage fields are recomputed against embedded ProofPacket, envelope, PIT manifest, registry contract, and acceptance report when present. A record-hash-only forged pass is no longer possible for those embedded artifacts.
- No DB/runtime/env/exchange/secret/order/Cost Gate/deploy/live/model reload/symlink side-effect surface found in `reward_ledger.py`.
- `reward_ledger.py` line count is 878. This is above the 800-line review-attention threshold but below the 2000-line hard cap. Treat as non-blocking review attention for this rework; future WP6 additions should split source-artifact helpers instead of growing the file.

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

```bash
wc -l program_code/ml_training/reward_ledger.py program_code/ml_training/tests/test_reward_ledger.py
```

Result: `878` and `698` lines respectively.

## Boundary Statement

This was a source-only E2 re-review. I did not read or mutate product runtime state, DB, migrations, exchange/private endpoints, secrets, environment configuration, order/probe paths, Cost Gate state, deployment state, live/mainnet state, model reloads, symlinks, or real learning outcomes. Unrelated dirty files under memory, IBKR, and Bybit control API were ignored except for appending this E2 report/memory entry.
