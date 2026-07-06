# AI/ML Roadmap WP1-WP4 Fixes And Trading-Focused Adversarial Audit

Date: 2026-07-07

PM sign-off: CONDITIONAL PASS - source contract findings from the first strict audit were fixed and the second trading-focused adversarial probe passed. This still does not grant runtime, exchange, private-read, MCP, order/probe, Cost Gate, promotion, live, or mainnet authority.

## Scope

Fixed all findings from `2026-07-07--ai_ml_roadmap_wp1_wp4_strict_adversarial_audit.md`:

1. WP1 ProofPacket malformed `sha256:` references.
2. WP4 AdvisoryReviewPacket provider/private/exchange/MCP contact aliases.
3. WP3 registry serving trio non-atomic persistence.
4. WP4 missing advisory packet self-hash.

Existing WP5 dirty files in the worktree were left untouched.

## Code Changes

### WP1 ProofPacket

- `program_code/ml_training/proof_packet_contract.py`
- `sha256:` references now require exact `sha256:<64 lowercase hex>`.
- Malformed provenance/hash reasons now classify as `INVALID`, not `PENDING_SCHEMA`.
- Added tests proving malformed `sha256:not-a-real-hash` cannot become `proof_ready`.

### WP4 AdvisoryReviewPacket

- `program_code/ml_training/advisory_review_packet.py`
- Added `advisory_review_packet_hash` self-hash and `compute_advisory_review_packet_hash()`.
- Added explicit no-contact fields:
  - `no_provider_call`
  - `no_exchange_contact`
  - `no_private_read`
  - `no_mcp_runtime`
- Validator now rejects truthy provider/exchange/private/MCP/credential contact aliases such as:
  - `provider_call_performed`
  - `exchange_private_read_performed`
  - `private_read_performed`
  - `mcp_server_started`
- Added tests for hash tamper and contact-alias rejection.

### WP3 Registry Serving Trio

- `program_code/ml_training/model_registry.py`
- Registry serving contract path no longer calls three independent `register_model()` transactions.
- It now writes q10/q50/q90 through one connection transaction via `_register_serving_contract_trio_atomic()`.
- If any row returns `None`, the function raises `RegistryServingContractError`, causing the connection context to roll back.
- Added fake-connection tests proving q10/q50/q90 share one transaction and q50 failure rolls back instead of committing q10.

## Verification

Focused TDD suite:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q \
  program_code/ml_training/tests/test_proof_packet_contract.py \
  program_code/ml_training/tests/test_advisory_review_packet.py \
  program_code/ml_training/tests/test_model_registry.py \
  -p no:cacheprovider
=> 116 passed
```

Adjacent ML contract suite:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q \
  program_code/ml_training/tests/test_pit_dataset_manifest.py \
  program_code/ml_training/tests/test_pit_dataset_manifest_builder.py \
  program_code/ml_training/tests/test_registry_serving_contract.py \
  program_code/ml_training/tests/test_mlde_shadow_advisor.py \
  -p no:cacheprovider
=> 39 passed
```

Original WP1-WP4 regression set:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q \
  program_code/ml_training/tests/test_proof_packet_contract.py \
  program_code/ml_training/tests/test_pit_dataset_manifest.py \
  program_code/ml_training/tests/test_pit_dataset_manifest_builder.py \
  program_code/ml_training/tests/test_registry_serving_contract.py \
  program_code/ml_training/tests/test_model_registry.py \
  program_code/ml_training/tests/test_advisory_review_packet.py \
  program_code/ml_training/tests/test_mlde_shadow_advisor.py \
  -p no:cacheprovider
=> 155 passed
```

Control API adjacency:

```text
PYTHONDONTWRITEBYTECODE=1 PATH=venvs/mac_dev/bin:$PATH \
PYTHONPATH=program_code:program_code/exchange_connectors/bybit_connector/control_api_v1 \
python3 -m pytest -q \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_l2_p3a_ml_advisory.py \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_l2_p3b_hypothesize.py \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_l2_ml_advisory_dispatch_route.py \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_engine_capabilities_routes.py \
  -p no:cacheprovider
=> 93 passed
```

Thought-gate / cost adjacency:

```text
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=program_code/exchange_connectors/bybit_connector/misc_tools:program_code/ai_agents/bybit_thought_gate:program_code \
python3 -m pytest -q \
  program_code/ai_agents/bybit_thought_gate/tests/test_advisory_review_packet_thought_gate.py \
  program_code/ai_agents/bybit_thought_gate/tests/test_ai_invocation_ledger.py \
  program_code/ai_agents/bybit_thought_gate/tests/test_ai_invocation_governance.py \
  program_code/ai_agents/bybit_thought_gate/tests/test_ai_cost_log_pricing_gate.py \
  program_code/ai_agents/bybit_thought_gate/tests/test_route_binder_e2e.py \
  -p no:cacheprovider
=> 18 passed
```

Proof/evidence/promotion adjacency:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q \
  program_code/ml_training/tests/test_candidate_evidence_manifest.py \
  program_code/ml_training/tests/test_candidate_evidence_manifest_builder.py \
  program_code/ml_training/tests/test_candidate_evidence_source_contract.py \
  program_code/ml_training/tests/test_promotion_evidence.py \
  program_code/ml_training/tests/test_proof_packet_contract.py \
  -p no:cacheprovider
=> 90 passed
```

Static hygiene:

```text
python3 -m py_compile proof_packet_contract.py advisory_review_packet.py model_registry.py
=> PASS

git diff --check
=> PASS
```

## Second-Round Trading-Focused Adversarial Probe

Custom source-only adversarial payload probe:

- Total payloads: 21
- Failed payloads: 0
- Runtime/exchange/private/MCP/order actions performed: 0

Passed fail-closed cases:

| Attack | Result |
|---|---|
| Malformed ProofPacket provenance `sha256:not-a-real-hash` | Rejected as `INVALID` |
| ProofPacket `order_allowed=true` | Rejected as authority boundary violation |
| ProofPacket `probe_authority_granted=true` | Rejected as authority boundary violation |
| ProofPacket `live_mainnet_performed=true` | Rejected as authority boundary violation |
| ProofPacket `cost_gate_lower_allowed=true` | Rejected as authority boundary violation |
| ProofPacket `exchange_private_read_performed=true` | Rejected as authority boundary violation |
| Cleanup fill disguised as profit proof | Rejected as proof exclusion |
| `NO_MATCHED_FILLS` carrying reward/training label | Rejected as invalid label contamination |
| Valid candidate-matched after-cost proof | Still passes as `proof_ready` |
| Advisory provider call performed | Rejected |
| Advisory exchange/private read performed | Rejected |
| Advisory MCP server started | Rejected |
| Advisory order/live/Cost Gate mutation aliases | Rejected |
| Advisory packet self-hash tamper | Rejected |
| Registry promotion/symlink/not-authority expansion | Rejected |

## Trading-Relevance Verdict

The repaired WP1-WP4 source contracts now better match the trading need:

- They do not prove profitability by narrative; they require candidate-matched after-cost fills and reject cleanup/unattributed/no-fill label pollution.
- They do not let AI/advisory packets become order/probe/live/private-read/MCP authority.
- They do not let registry metadata imply promotion-serving or direct reload authority.
- They preserve the happy path for a valid, candidate-matched, after-cost proof packet.

Residual truth:

- This is still source-contract hardening, not trading outcome evidence.
- No candidate-matched bounded Demo fills, fee/slippage proof, repeat/OOS result, or live-applicable net PnL proof was produced by this work.
- Registry atomicity was verified with fake connection tests on Mac; real PG integration remains governed by Linux PG dry-run/integration gates before runtime serving claims.

PM sign-off:

- `CONDITIONAL PASS`
- Fixed findings: WP1 P1, WP4 P1, WP3 P2, WP4 P3.
- Next safe continuation: continue WP5 only after consuming the repaired WP4 no-contact semantics; any runtime/order-capable path still requires fresh loss-control envelope and E3/BB review.
