# AI/ML Roadmap WP1-WP4 Strict Adversarial Audit

Date: 2026-07-07

PM sign-off: CONDITIONAL - source-only boundary held, but WP1 and WP4 are not clean enough to be treated as downstream authority-grade gates until the P1 findings below are fixed.

## Scope

Audited completed WP1-WP4 artifacts:

- WP1: `proof_packet_v1`
- WP2: `pit_dataset_manifest_v1`
- WP3: `registry_serving_contract_v1`
- WP4: `advisory_review_packet_v1`

Frozen repo state observed during audit:

- HEAD: `edd6ab3ecdd7789b1aec46c4e091d5b8b3c37cf2`
- `origin/main`: `5d16229948eba555ee415048ad028e11649e3d91`
- Local branch was ahead `origin/main` by 9 commits before this report.
- Existing dirty/untracked WP5 and memory worktree state was left untouched.

Dispatch note:

- No new sub-agent was spawned in this turn. The currently exposed multi-agent tool policy requires an explicit user request for subagents in the current turn; this audit therefore used PM local adversarial review lenses instead of launching E2/E3/E4/CC agents.
- This is a strict source/test/payload audit only. It performed no runtime mutation, DB write/read, exchange/private read, MCP server/config, secret access, order/probe, Cost Gate change, deploy, live, or mainnet action.

## Verification Run

Focused regression passed:

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
=> 138 passed
```

Control API adjacency passed:

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

Thought-gate / cost adjacency passed:

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

Static hygiene:

```text
git diff --check
=> PASS
```

Adversarial payload probe result:

```text
('proof_bad_sha256_refs', 'proof_ready', 'ok', True, ('ok',))
('pit_bad_sha256_refs', 'invalid', 'hash_malformed:provenance.source_hashes.query', False, (...))
('registry_bad_sha256_refs', 'invalid', 'dataset_manifest_hash_malformed', False, (...))
('advisory_provider_call_performed', 'PASS', 'accepted', True, ())
('advisory_exchange_private_read_performed', 'PASS', 'accepted', True, ())
('advisory_private_read_performed', 'PASS', 'accepted', True, ())
('advisory_mcp_server_started', 'PASS', 'accepted', True, ())
```

## Findings

### P1 - WP1 ProofPacket accepts malformed `sha256:` references

Evidence:

- `program_code/ml_training/proof_packet_contract.py:625`
- `program_code/ml_training/proof_packet_contract.py:629`

Current helper:

```python
def _is_stable_hash(value: str) -> bool:
    return _is_hex64(value) or (value.startswith("sha256:") and len(value) > 7)

def _is_stable_ref(value: str) -> bool:
    return bool(_GIT_SHA_RE.match(value)) or _is_stable_hash(value)
```

Adversarial result:

- `code_commit = "sha256:not-a-real-hash"`
- `rust_build_sha = "sha256:not-a-real-hash"`
- `source_hashes = {"ledger": "sha256:not-a-real-hash"}`
- `input_artifact_hashes = {"fill": "sha256:not-a-real-hash"}`
- Validator returned `proof_ready=True`.

Impact:

- WP1 can accept non-hash strings as stable provenance.
- This weakens reconstructability and contradicts WP2/WP3, which correctly reject malformed `sha256:` references.
- This does not grant runtime/order authority by itself, but it is a blocker before treating ProofPacket as a promotion-quality proof gate.

Required fix:

- Change `_is_stable_hash()` to accept either 64 hex or exact `sha256:<64 hex>`.
- Add focused red tests for malformed `sha256:` in `code_commit`, `rust_build_sha`, `source_hashes`, `input_artifact_hashes`, and `pit_dataset_manifest`.
- Keep Git SHA acceptance explicit and separate from SHA-256 digest acceptance.

Recommended status adjustment:

- WP1 should be treated as `ADVANCED_WITH_P1_FIX_REQUIRED`, not fully clean `ADVANCED`, until fixed.

### P1 - WP4 advisory packet accepts truthy external-contact aliases

Evidence:

- Module boundary states no runtime/DB/secret/promotion/Cost Gate/strategy mutation authority at `program_code/ml_training/advisory_review_packet.py:6`.
- Mutation dimensions currently cover order/probe/live/mainnet/runtime/db/database/secret/promotion/strategy/config at `program_code/ml_training/advisory_review_packet.py:22`.
- Builder sets no mutation flags at `program_code/ml_training/advisory_review_packet.py:146`.
- Validator requires those no-mutation flags at `program_code/ml_training/advisory_review_packet.py:249`.
- `_scan_for_truthy_grants()` blocks active/authority/mutation grants but not provider/private/exchange/MCP contact aliases at `program_code/ml_training/advisory_review_packet.py:229`.

Adversarial result:

- `provider_call_performed=True` accepted.
- `exchange_private_read_performed=True` accepted.
- `private_read_performed=True` accepted.
- `mcp_server_started=True` accepted.

Impact:

- The packet remains inactive and does not grant order authority, but it can carry truthy evidence of external/provider/private/MCP contact while still validating.
- This conflicts with the WP4 source-only boundary and the autonomous loop hard boundary.
- This is especially relevant before WP5 DemoMutationEnvelope work consumes advisory outputs for controlled mutation proposals.

Required fix:

- Add explicit no-contact fields, for example:
  - `no_provider_call`
  - `no_exchange_contact`
  - `no_private_read`
  - `no_mcp_runtime`
- Extend forbidden-key scanning to reject truthy `provider`, `exchange`, `private`, `credential`, `mcp`, `server_started`, and contact/read/call aliases unless explicitly under a `no_` / `not_` denial key.
- Add focused tests for accepted false denials and rejected truthy positive aliases.

Recommended status adjustment:

- WP4 should remain `ADVANCED_WITH_CONCERNS`, with a P1 hardening blocker before any downstream advisory-to-mutation or provider-routing integration.

### P2 - WP3 registry trio persistence is fail-loud but not atomic

Evidence:

- `program_code/ml_training/model_registry.py:371`
- `program_code/ml_training/model_registry.py:390`
- `program_code/ml_training/model_registry.py:416`

Current behavior:

- Registry serving contract is attached before q10/q50/q90 DB writes.
- Writes occur in a loop.
- A failed later write raises `RegistryServingContractError`, but earlier inserted rows are not rolled back.

Impact:

- This was already documented in the WP3 effect review.
- It is acceptable for the current source-only contract checkpoint, because WP3 does not claim runtime reload or promotion-serving readiness.
- It is not acceptable before registry-backed serving/reload or any claim that a q10/q50/q90 trio was durably and atomically registered.

Required future gate:

- Move q10/q50/q90 persistence into one DB transaction or add an explicit durable reconciliation/quarantine state that prevents partial trio rows from being consumed.

Recommended status:

- WP3 remains `ADVANCED_WITH_CONCERNS`; no downgrade beyond the already carried concern.

### P3 - WP4 packet lacks top-level self-hash

Evidence:

- Packet construction at `program_code/ml_training/advisory_review_packet.py:146` includes `input_hashes` but no top-level packet digest.
- Validator at `program_code/ml_training/advisory_review_packet.py:249` does not verify packet self-hash.

Impact:

- This is weaker than WP1/WP2/WP3, which carry `proof_packet_hash`, `manifest_hash`, or `contract_hash`.
- The current packet still hash-binds inputs, so this is not a source-only blocker.
- If advisory packets become durable artifacts, external callers must hash the whole packet themselves or the contract should add `advisory_review_packet_hash`.

Recommended fix:

- Add a canonical self-hash before durable storage or cross-process transport.

## WP-by-WP Verdict

| WP | Strict audit verdict | Reason |
|---|---|---|
| WP1 ProofPacket | `ADVANCED_WITH_P1_FIX_REQUIRED` | Contract shape is useful, but malformed `sha256:` provenance can still validate as proof-ready. |
| WP2 PIT Dataset Manifest | `PASS` | This audit did not find a bypass; it rejects malformed hashes, unpinned query/current/latest/max-age patterns, secret/authority fields, row exclusions, and rebuild drift. |
| WP3 Registry Serving Contract | `PASS_WITH_KNOWN_CONCERN` | Source contract holds; known non-transactional trio persistence must be fixed before DB-backed serving/reload claims. |
| WP4 Advisory/DreamEngine Role Hardening | `ADVANCED_WITH_P1_FIX_REQUIRED` | Inactive/no-authority packet holds for direct mutation flags, but external-contact aliases are not explicitly denied. |

## Roadmap Impact

The AI/ML direction remains technically valid, but the dependency graph needs one hardening checkpoint before relying on WP1/WP4 as clean downstream gates:

1. `WP1.1-PROOF-PACKET-HASH-STRICTNESS`
2. `WP4.1-ADVISORY-NO-CONTACT-ALIASES`
3. Then continue WP5 DemoMutationEnvelope contract, unless WP5 is kept fully source-only and explicitly refuses to consume positive provider/private/MCP/contact evidence.

No finding here supports MCP runtime usage, provider execution, private exchange reads, order/probe authority, Cost Gate relaxation, promotion, live, or mainnet.

PM sign-off:

- `CONDITIONAL`
- Boundary: held.
- Tests: green for current suite.
- Blocking fixes before next authority-bearing dependency: WP1 hash strictness and WP4 no-contact alias denial.
