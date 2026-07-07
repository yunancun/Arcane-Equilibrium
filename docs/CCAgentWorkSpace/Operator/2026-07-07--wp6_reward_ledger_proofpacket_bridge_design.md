# WP6 Reward Ledger ProofPacket Bridge - Operator Stub

Date: 2026-07-07
Status: E1-READY_SOURCE_ONLY

PA completed the WP6 source-only design. Recommended implementation is additive:

- new `program_code/ml_training/reward_ledger.py`
- new `program_code/ml_training/tests/test_reward_ledger.py`

The bridge must accept only:

- valid `proof_packet_v1` with `PROOF_READY`;
- candidate-matched fills and after-cost fields;
- valid `demo_mutation_envelope_v1` with `STATUS_COUNTABLE`;
- exact proof hash / mutation envelope hash / PIT lineage.

It must reject no-fill, cleanup, unmatched, dry-run, dedupe, non-demo/live, proof-excluded, non-countable envelopes, replay duplicates, and missing PIT/registry lineage.

Boundary: source-only contracts, validators, fixtures, and offline bridge only. No runtime/PG/exchange/private read, order/probe, Cost Gate, deploy, live/mainnet, or learning-state mutation.

Full PA report:

`docs/CCAgentWorkSpace/PA/workspace/reports/2026-07-07--wp6_reward_ledger_proofpacket_bridge_design.md`
