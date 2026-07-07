# WP6 Reward Ledger ProofPacket Bridge QA Acceptance

Date: 2026-07-07
Role: QA(worker)
Status: PASS

## Scope

Source-only acceptance for `WP6-REWARD-LEDGER-PROOFPACKET-BRIDGE`.

Reviewed required context:

- `AGENTS.md`
- `CLAUDE.md`
- `.codex/AGENT_DISPATCH_PROTOCOL.md`
- `.codex/SUBAGENT_EXECUTION_RULES.md`
- PA design report
- E1 implementation, rework, and rework2 reports
- E2 review, re-review, and re-review2 reports
- E4 regression report
- `program_code/ml_training/reward_ledger.py`
- `program_code/ml_training/tests/test_reward_ledger.py`

No product code edits, no staging, no commit. Existing unrelated dirty files under memory, IBKR, and Bybit `control_api_v1` were ignored unless they overlapped; no overlap was found for this source-only acceptance.

## Acceptance Verdict

QA E2E ACCEPTANCE DONE: PASS.

The implementation satisfies the requested source-only acceptance criteria:

1. `reward_ledger_v1` accepts only upstream `PROOF_READY` ProofPacket plus countable DemoMutationEnvelope. Source review and tests confirm rejection for no-fill, cleanup/proof-excluded, unmatched candidate/source, dry-run, dedupe, non-demo/live, audit-only/non-countable, missing PIT, missing registry-required lineage, and authority aliases.
2. Records are source-backed. `validate_reward_record()` requires embedded `source_artifacts`, recomputes `record_hash`, reruns upstream validators, and recomputes ProofPacket, DemoMutationEnvelope, PIT manifest, registry contract, and acceptance report hashes where applicable. Forged lineage/source artifacts fail even after recomputing `record_hash`.
3. Optional registry mode is explicit. Default `registry_required=True` fails closed on missing registry contract. `registry_required=False` requires `registry_optional_reason="execution_reward_not_training_contract_bound"` and rejects contradictory contract-bound markers in source artifacts.
4. Append-only/dedupe helpers are source-only. `dedupe_reward_records()` deep-copies in-memory records by `record_id`; `validate_reward_batch()` validates source records and duplicate IDs only. No external state mutation is present.
5. Source-only boundary holds. Static grep found no DB, runtime IPC, network, subprocess, env, order, SQL mutation, Cost Gate, deploy, live/mainnet, model reload, or symlink surfaces in `reward_ledger.py`.
6. E2 returns are closed and E4 regression is enough. E2 MEDIUM-1 and MEDIUM-2 were closed by E1 rework; E2 re-review optional-registry contradiction was closed by E1 rework2; E2 passed to E4; E4 focused and adjacency regression passed. QA independently reran focused tests and adversarial probes.

## Commands And Results

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q program_code/ml_training/tests/test_reward_ledger.py program_code/ml_training/tests/test_proof_packet_contract.py program_code/ml_training/tests/test_demo_mutation_envelope.py program_code/ml_training/tests/test_demo_mutation_envelope_applier_mapping.py -p no:cacheprovider
```

Result: PASS, `112 passed in 0.50s`.

```bash
rg -n "psycopg2|asyncpg|requests|httpx|urllib|socket|subprocess|one_shot_ipc_call|ipc_dispatch|place_order|create_order|cancel_order|submit_order|INSERT INTO|UPDATE learning|DELETE FROM|os\.environ|getenv" program_code/ml_training/reward_ledger.py
```

Result: PASS, no matches. `rg` exit 1 is expected for no matches.

```bash
git diff --check -- program_code/ml_training/reward_ledger.py program_code/ml_training/tests/test_reward_ledger.py docs/CCAgentWorkSpace/PA/workspace/reports/2026-07-07--wp6_reward_ledger_proofpacket_bridge_design.md docs/CCAgentWorkSpace/E1/workspace/reports/2026-07-07--wp6_reward_ledger_proofpacket_bridge_implementation.md docs/CCAgentWorkSpace/E1/workspace/reports/2026-07-07--wp6_reward_ledger_proofpacket_bridge_rework.md docs/CCAgentWorkSpace/E1/workspace/reports/2026-07-07--wp6_reward_ledger_proofpacket_bridge_rework2.md docs/CCAgentWorkSpace/E2/workspace/reports/2026-07-07--wp6_reward_ledger_proofpacket_bridge_review.md docs/CCAgentWorkSpace/E2/workspace/reports/2026-07-07--wp6_reward_ledger_proofpacket_bridge_rereview.md docs/CCAgentWorkSpace/E2/workspace/reports/2026-07-07--wp6_reward_ledger_proofpacket_bridge_rereview2.md docs/CCAgentWorkSpace/E4/workspace/reports/2026-07-07--wp6_reward_ledger_proofpacket_bridge_regression.md
```

Result: PASS, exit 0, no whitespace errors.

Additional QA adversarial probe:

```text
forged_lineage_ready= False
forged_lineage_reason= lineage_proof_packet_hash_source_mismatch
forged_lineage_has_source_mismatch= True
forged_optional_ready= False
forged_optional_reason= registry_optional_source_contract_bound:$.acceptance_report_ref.contract_bound
forged_optional_contract_bound= True
```

## Boundary Statement

This QA acceptance was source-only. I did not read or mutate product runtime state, DB, migrations, exchange/private endpoints, secrets, environment configuration, order/probe paths, Cost Gate state, deployment state, live/mainnet state, model reloads, symlinks, registry persistence, or real learning outcomes.

Runtime/loss-control remains blocked. This PASS does not authorize bounded Demo outcome ingestion, registry persistence, serving promotion, Cost Gate changes, orders, probes, runtime mutation, or live/mainnet activity.

## Residual Risk

- `program_code/ml_training/reward_ledger.py` is 913 lines, above the repo 800-line review-attention threshold and below the 2000-line hard cap. This is non-blocking for this acceptance; future WP6 growth should split source-artifact, lineage, or marker helpers.
- Durable append-only persistence, DB uniqueness, registry persistence, and actual bounded Demo outcome ingestion remain out of scope and require a future reviewed design plus runtime/loss-control clearance.
