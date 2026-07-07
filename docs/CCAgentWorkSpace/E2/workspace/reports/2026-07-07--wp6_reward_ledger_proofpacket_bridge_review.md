# WP6 Reward Ledger ProofPacket Bridge E2 Review

Date: 2026-07-07
Role: E2(explorer)
Verdict: RETURN_TO_E1

## Scope

Reviewed narrow source scope only:

- `program_code/ml_training/reward_ledger.py`
- `program_code/ml_training/tests/test_reward_ledger.py`
- call contracts in `proof_packet_contract.py`, `demo_mutation_envelope.py`, `registry_serving_contract.py`
- PA design and E1 implementation report

No business-code edits, no stage, no commit.

## Findings

### MEDIUM-1 — Standalone record validation can certify forged upstream lineage hashes

Location: `program_code/ml_training/reward_ledger.py:234`, `program_code/ml_training/reward_ledger.py:280`, `program_code/ml_training/reward_ledger.py:589`

`validate_reward_record()` recomputes only `record_hash`. It checks `lineage.proof_packet_hash`, `lineage.mutation_envelope_hash`, and `lineage.pit_dataset_manifest_hash` for 64-hex shape, but it does not and cannot recompute them against the upstream ProofPacket, DemoMutationEnvelope, PIT manifest, registry contract, or acceptance report. Because `record_hash` is over the record text itself, a caller can rewrite the upstream lineage hashes, recompute `record_hash`, and still receive `reward_ready=True`.

Adversarial probe:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 - <<'PY'
from ml_training.tests.test_reward_ledger import _build_record
from ml_training.reward_ledger import validate_reward_record, compute_reward_record_hash
r = _build_record()
r['lineage']['proof_packet_hash'] = 'f' * 64
r['lineage']['mutation_envelope_hash'] = 'e' * 64
r['lineage']['pit_dataset_manifest_hash'] = 'd' * 64
r['record_hash'] = compute_reward_record_hash(r)
v = validate_reward_record(r)
print(v.reward_ready, v.verdict, v.reason)
PY
```

Observed: `True reward_record_ready ok`.

This violates the review question "Does validation recompute record_hash and upstream hashes, not trust caller text?" Builder-side `_source_rejection_reasons()` does call upstream validators and recompute proof/envelope/registry/acceptance hashes, but the public validator can still accept a text-only reward record that no longer proves those upstream artifacts. Since downstream learning state is expected to consume validated reward records, this is a contract hole, not just a test gap.

Suggested E1 direction: make the public validation boundary explicit and fail-closed. Either require source artifacts for ready validation, split structural validation from source-backed validation so only the latter can return `reward_ready=True`, or embed enough upstream canonical source/hashes in the record to recompute every lineage field. Add a negative test equivalent to the probe above.

### MEDIUM-2 — Registry lineage requiredness is inferred from absent caller flags and defaults to optional

Location: `program_code/ml_training/reward_ledger.py:203`, `program_code/ml_training/reward_ledger.py:406`, `program_code/ml_training/reward_ledger.py:473`

The builder treats registry lineage as required only when `effect_window.registry_required`, `acceptance_report_ref.registry_required`, `acceptance_report_ref.contract_bound`, or `pit_dataset_manifest_binding.contract_bound_run` is present/truthy. If the caller omits these flags and passes no registry contract, the record is still built with:

```text
registry_serving_contract_hash = ""
registry_optional_reason = "execution_reward_not_training_contract_bound"
```

Adversarial probe:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 - <<'PY'
from ml_training.tests.test_reward_ledger import _valid_proof_packet, _valid_envelope, _valid_effect_window
from ml_training.reward_ledger import build_reward_record_from_proof_and_mutation
p = _valid_proof_packet()
e = _valid_envelope(p)
w = _valid_effect_window()
r = build_reward_record_from_proof_and_mutation(proof_packet=p, demo_mutation_envelope=e, effect_window=w)
print(r['lineage']['registry_serving_contract_hash'] == '', r['lineage']['registry_optional_reason'])
PY
```

Observed: `True execution_reward_not_training_contract_bound`.

PA allowed empty registry hash only for pure execution reward records, but WP6 is a bridge from ProofPacket plus countable DemoMutationEnvelope into learning reward state. Treating silence as "not training contract bound" is too loose for a fail-closed contract. A caller omission can erase a required registry lineage precondition without an explicit declaration.

Suggested E1 direction: require an explicit source-of-truth decision for registry lineage, for example `registry_required=True/False` plus a validated optional reason when false. Absence should fail closed, not infer pure execution reward. Add tests for omitted requiredness, explicit optional pure-execution mode, and contract-bound acceptance report.

## Non-Blocking Observations

- Source-only boundary is otherwise intact: `reward_ledger.py` imports only stdlib and local validators; no DB/runtime/env/exchange/secret/order/Cost Gate/deploy/live/model reload/symlink side-effect surface found.
- Builder does require `validate_proof_packet(...).proof_ready`, `verdict == PROOF_READY`, `validate_demo_mutation_envelope(...).status == STATUS_COUNTABLE`, and `effective_learning_countable is True`.
- Fail-closed coverage is broad for no-fill, proof-excluded/cleanup, non-demo/live, audit-only, dry-run, dedupe, proof-linkage mismatch, source candidate mismatch, missing PIT lineage, authority aliases, and batch duplicate record IDs.
- Candidate/envelope matching uses exact `proof_linkage.proof_packet_hash` and exact source candidate fields when present; I did not find symbol-only/latest fallback.
- `dedupe_reward_records()` is in-memory and returns deep copies; it does not mutate input records or external state.
- `reward_ledger.py` is 796 lines. This is below the 800-line review-attention threshold but tight; future additions should split helpers/tests instead of growing the file.
- Tests are focused and pass, but they miss the two adversarial cases above.

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

Result: `83 passed in 0.61s`.

```bash
rg -n "psycopg2|asyncpg|requests|httpx|urllib|socket|subprocess|one_shot_ipc_call|ipc_dispatch|place_order|create_order|cancel_order|submit_order|INSERT INTO|UPDATE learning|DELETE FROM|os\.environ|getenv" program_code/ml_training/reward_ledger.py
```

Result: PASS, no matches (`rg` exit 1).

```bash
git diff --check -- program_code/ml_training/reward_ledger.py program_code/ml_training/tests/test_reward_ledger.py
```

Result: PASS.

Race / dirty-tree notes:

- `git fetch --prune origin` completed.
- `origin/main` had multiple recent sibling commits, including AI/ML and IBKR work; current WP6 implementation files are untracked in this worktree and no overlap was found in `origin/main...HEAD` for the reviewed files.
- Existing unrelated dirty files under memory, IBKR, and control_api_v1 were ignored per operator scope.

## Boundary Statement

This review is source-only. I did not read product runtime state, DB, migrations, exchange/private endpoints, secrets, environment configuration, order/probe paths, Cost Gate state, deployment state, live/mainnet state, model reloads, symlinks, or real learning outcomes.

Runtime/loss-control remains blocked. WP6 remains a source contract/validator/offline bridge only, not bounded Demo outcome ingestion, not registry persistence, not serving promotion, and not proof promotion.
