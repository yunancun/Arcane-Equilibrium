# AI/ML Downstream Loop WP6 Reward Ledger ProofPacket Bridge

Date: 2026-07-07

PM status: `ADVANCED_WITH_CONCERNS_SOURCE_ONLY`

Work item: `WP6-REWARD-LEDGER-PROOFPACKET-BRIDGE`

Recovered from:

- Prior state packet: `2026-07-07--ai_ml_downstream_loop_wp3_1_training_registry_contract_emission.state_packet.json`
- Prior completed commit: `8534d716efcbaeb610d9da727db2af94f6f41ef9`
- Neighbor classification: `WP5_MAPPING_READY`, `RUNTIME_LOSS_CONTROL_BLOCKED`

## Selection

WP6 was selected because WP1-WP5 plus WP2.1/WP3.1 made source contracts
available for ProofPacket, PIT manifest, registry serving contract, and
DemoMutationEnvelope countability, but there was still no source-only bridge
that could turn candidate-matched proof plus bounded Demo mutation evidence into
an append-only reward record.

The work was source-safe and did not require runtime, DB, exchange, credential,
order, Cost Gate, deploy, live, model reload, symlink, registry persistence, or
bounded Demo outcome access.

## Dispatch Chain

Required source feature chain was completed:

- PM -> PA: design pass `2026-07-07--wp6_reward_ledger_proofpacket_bridge_design.md`
- PA -> E1: source implementation `2026-07-07--wp6_reward_ledger_proofpacket_bridge_implementation.md`
- E1 -> E2: source review returned to E1 for source-artifact and registry-lineage hardening
- E1 -> E2: re-review returned to E1 for contradictory optional-registry markers
- E1 -> E2: second re-review `PASS_TO_E4`
- E2 -> E4: regression `PASS`
- E4 -> QA: source acceptance `PASS`
- QA -> PM: this PM effect review/state checkpoint

## Implementation Delta

Primary source changes:

- `program_code/ml_training/reward_ledger.py`
  - adds `reward_ledger_v1` constants, hash, builder, validator, extractor,
    in-memory dedupe, and batch validation helpers;
  - builds records only from caller-provided `PROOF_READY` ProofPacket,
    `STATUS_COUNTABLE` DemoMutationEnvelope, effect window, and optional
    registry/acceptance artifacts;
  - embeds source artifacts so validation can recompute ProofPacket,
    DemoMutationEnvelope, PIT manifest, registry contract, acceptance report,
    and reward record hashes;
  - keeps registry lineage required by default;
  - allows explicit execution-only optional registry mode only with
    `registry_optional_reason="execution_reward_not_training_contract_bound"`;
  - rejects optional-registry records if source artifacts contain
    contract-bound markers;
  - rejects no-fill, cleanup, unmatched, dry-run, dedupe, non-demo/live,
    audit-only/non-countable, proof-excluded, missing PIT, missing registry, and
    authority-expansion inputs.
- `program_code/ml_training/tests/test_reward_ledger.py`
  - covers happy path, failure matrix, forged lineage/source-artifact mutation
    after `record_hash` recompute, optional registry contradiction, dedupe, and
    batch validation.

## Verification

PM accepted the following source evidence:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m py_compile program_code/ml_training/reward_ledger.py program_code/ml_training/proof_packet_contract.py program_code/ml_training/demo_mutation_envelope.py program_code/ml_training/registry_serving_contract.py
```

Result: `PASS`.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q program_code/ml_training/tests/test_reward_ledger.py program_code/ml_training/tests/test_proof_packet_contract.py program_code/ml_training/tests/test_demo_mutation_envelope.py program_code/ml_training/tests/test_demo_mutation_envelope_applier_mapping.py -p no:cacheprovider
```

Result: `112 passed` across E1/E2/E4/QA replays.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q program_code/ml_training/tests/test_pit_dataset_manifest.py program_code/ml_training/tests/test_registry_serving_contract.py program_code/ml_training/tests/test_run_training_pipeline.py program_code/ml_training/tests/test_model_registry.py -p no:cacheprovider
```

Result: `83 passed`.

```bash
rg -n "psycopg2|asyncpg|requests|httpx|urllib|socket|subprocess|one_shot_ipc_call|ipc_dispatch|place_order|create_order|cancel_order|submit_order|INSERT INTO|UPDATE learning|DELETE FROM|os\.environ|getenv" program_code/ml_training/reward_ledger.py
```

Result: `PASS`, no matches. `rg` exit 1 is expected for no matches.

```bash
git diff --check -- WP6 scoped source/report paths
```

Result: `PASS`.

## Effect Review

Verdict: `EFFECTIVE_WITH_CONCERNS`

The checkpoint closes the WP6 source gap: candidate-matched ProofPacket and
countable DemoMutationEnvelope evidence can now be represented as a
machine-checkable `reward_ledger_v1` record with source-backed lineage. Forged
lineage/source artifacts fail even after a caller recomputes `record_hash`.

The concern is intentional: this does not ingest real bounded Demo outcomes,
does not persist a durable ledger, does not validate DB uniqueness or registry
persistence, and does not authorize runtime learning. Runtime/loss-control is
still blocked.

## Boundary

No denied action was performed or introduced:

- no runtime mutation;
- no DB empirical read/write or migration;
- no exchange/private read;
- no MCP server/config or credential/secret access;
- no order/probe;
- no Cost Gate change;
- no deploy;
- no live/mainnet action;
- no model reload or symlink promotion;
- no bounded Demo outcome ingestion;
- no registry persistence.

## State

State packet: `2026-07-07--ai_ml_downstream_loop_wp6_reward_ledger_proofpacket_bridge.state_packet.json`

Status: `ADVANCED_WITH_CONCERNS`

Next work id: `WP7-EFFECT-REVIEW-AND-STOP-LOOP`

Concerns:

- `reward_ledger.py` is 913 lines, above the 800-line review-attention
  threshold and below the 2000-line hard cap; E2/E4/QA accepted this as
  non-blocking for the current source-only bridge.
- Runtime/loss-control remains `RUNTIME_LOSS_CONTROL_BLOCKED`; no runtime branch
  was consumed.
- Real bounded Demo outcome evaluation remains unavailable until exact-scope
  PM->E3->BB authorization is READY.
