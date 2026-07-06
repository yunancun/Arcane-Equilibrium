# 2026-07-06 AI/ML Roadmap Loop — WP2 PIT Dataset Manifest

PM sign-off: `ADVANCED_SOURCE_CONTRACT_READY`

Scope: continuous AI/ML Roadmap Autonomous Completion Loop, source-only WP2.
No runtime mutation, DB read/write, exchange/API/private read, MCP server start,
credential/secret access, order/probe, Cost Gate change, deploy, live, or
mainnet action was performed.

## Selected Work Item

Selected `roadmap_work_item_v1`:

- Work id: `WP2-PIT-DATASET-MANIFEST`
- Gate: `G3`
- Priority: `P0`
- Reason: WP1 ProofPacket was source-contract-ready, and E2 carried a real
  concern that ProofPacket provenance was too generic until named PIT dataset,
  rebuild evidence, feature/schema lineage, matched-control artifact hash, and
  row-backed fill source artifact hash existed.
- Machine-readable artifact:
  `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-06--ai_ml_roadmap_loop_wp2_pit_dataset_manifest.work_item.json`

## Implementation

Added `program_code/ml_training/pit_dataset_manifest.py`.

The new stdlib-only source contract defines:

- canonical field `pit_dataset_manifest`;
- schema version `pit_dataset_manifest_v1`;
- `PitDatasetManifestValidation`;
- `compute_pit_dataset_manifest_hash`;
- `extract_pit_dataset_manifest`;
- `validate_pit_dataset_manifest`.

`dataset_ready` requires explicit point-in-time fields: `as_of_ts`,
`point_in_time=true`, `future_data_allowed=false`, candidate scope, source query
window and hashes, row-set hashes, feature lineage, label lineage, split
lineage, leakage evidence, matched controls, row-backed fill source, rebuild
evidence, provenance, and `manifest_hash`.

Unpinned query shapes such as `now()`, `CURRENT_TIMESTAMP`, `latest`, or
`max_age_days` are not promotion-grade and return `research_only`.

Added `program_code/ml_training/pit_dataset_manifest_builder.py`.

The builder consumes only caller-provided source mappings and synthetic rows. It
does not read env, DB, files, runtime, network, exchange state, or secrets. It
provides deterministic row-id and dataset hashing plus manifest build/validation
output.

Updated `program_code/ml_training/proof_packet_contract.py`.

`PROOF_READY` now requires `provenance.pit_dataset_manifest` to validate as
dataset-ready. The embedded manifest must cross-bind to ProofPacket
`candidate_identity` for `candidate_id`, `strategy_name`, `symbol`, and `side`.
ProofPacket also rejects broader authority aliases such as `order_allowed`,
`promotion_allowed`, `live_enabled`, `cost_gate_lower_allowed`, and
`runtime_write_allowed` when truthy.

`NO_MATCHED_FILLS` remains a blocker artifact and does not require a PIT
manifest.

## Dispatch

Required source feature chain was used:

`PM -> PA -> E1 -> E1a -> E2 -> E4 -> QA -> PM`

The first E2 pass found two medium ProofPacket integration issues:

- valid PIT manifest for the wrong candidate still passed;
- ProofPacket authority alias scanning was narrower than PIT manifest scanning.

E1a fixed both. The fixed patch then passed E2, E4, and QA.

Final role results:

- PA: `DESIGN_READY_WITH_CONCERNS`, no source-only blocker.
- E1: `PASS`, PIT manifest validator + 9 focused tests.
- E1a: `PASS`, builder + initial ProofPacket integration.
- E2 fixed review: `PASS`, high confidence.
- E4 fixed regression: `PASS`, high confidence.
- QA fixed acceptance: `ACCEPT`, findings=0.

## Effect Review

Machine-readable `implementation_effect_review_v1`:

`docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-06--ai_ml_roadmap_loop_wp2_pit_dataset_manifest.effect_review.json`

Summary:

- Pre-state: `G3` blocked because PIT manifest contract did not exist and
  ProofPacket provenance could rely on generic hashes.
- Post-state: `G3` is `source_contract_ready`.
- Gate delta: `blocked_to_source_contract_ready`.
- Proof delta: ProofPacket `PROOF_READY` now needs a valid named PIT manifest
  cross-bound to candidate identity.
- Verdict: `EFFECTIVE`.

State packet:

`docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-06--ai_ml_roadmap_loop_wp2_pit_dataset_manifest.state_packet.json`

State: `ADVANCED`.

## Verification

Focused verification:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile program_code/ml_training/pit_dataset_manifest.py program_code/ml_training/pit_dataset_manifest_builder.py program_code/ml_training/proof_packet_contract.py program_code/ml_training/tests/test_pit_dataset_manifest.py program_code/ml_training/tests/test_pit_dataset_manifest_builder.py program_code/ml_training/tests/test_proof_packet_contract.py
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q program_code/ml_training/tests/test_pit_dataset_manifest.py program_code/ml_training/tests/test_pit_dataset_manifest_builder.py program_code/ml_training/tests/test_proof_packet_contract.py -p no:cacheprovider
```

Result: py_compile PASS; `36 passed`.

Adjacent ML evidence verification:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q program_code/ml_training/tests/test_pit_dataset_manifest.py program_code/ml_training/tests/test_pit_dataset_manifest_builder.py program_code/ml_training/tests/test_proof_packet_contract.py program_code/ml_training/tests/test_candidate_evidence_manifest.py program_code/ml_training/tests/test_candidate_evidence_source_contract.py program_code/ml_training/tests/test_parquet_etl.py -p no:cacheprovider
```

Result: `81 passed, 1 skipped`.

Adjacent cost-gate proof/promotion verification:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_learning_candidate_proof_evidence.py helper_scripts/research/tests/test_cost_gate_learning_proof_promotion_gate.py -p no:cacheprovider
```

Result: `20 passed`.

Final whitespace/diff gate:

```bash
git diff --check
```

Result: PASS.

## Boundary

No runtime mutation, DB read/write, exchange/API/private read, MCP server start,
credential/secret access, order/probe, Cost Gate change, deploy, live, or
mainnet action was performed.

Pre-existing dirty worktree files under `memory/` were not staged or modified.

## Next Work

Next source-only loop item:

`WP3-REGISTRY-SERVING-PARITY`

Expected scope: registry-authorized advisory serving metadata/parity. It may
only harden source contracts and fail-closed metadata requirements. It must not
claim promotion-serving readiness beyond registry-row contracts, start runtime,
read DB/private/exchange state, start MCP, access secrets, route orders/probes,
change Cost Gate, deploy, or touch live/mainnet.
