# 2026-07-06 AI/ML Roadmap Loop - WP4 Advisory DreamEngine Role Hardening

PM sign-off: `ADVANCED_WITH_CONCERNS_SOURCE_CONTRACT_READY`

Scope: continuous AI/ML Roadmap Autonomous Completion Loop, source-only WP4.
No runtime mutation, DB read/write, exchange/API/private read, MCP server start,
credential/secret access, provider call, order/probe, Cost Gate change, deploy,
live, or mainnet action was performed.

## Selected Work Item

Selected `roadmap_work_item_v1`:

- Work id: `WP4-ADVISORY-DREAMENGINE-ROLE-HARDENING`
- Gate: `G6`
- Priority: `P1`
- Reason: WP3 registry serving parity was source-contract ready. WP4 is the
  next source-only dependency and makes L2, LLM, MLDE, DreamEngine, and
  thought-gate outputs review artifacts instead of authority paths.
- Machine-readable artifact:
  `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-06--ai_ml_roadmap_loop_wp4_advisory_dreamengine_role_hardening.work_item.json`

## Implementation

Added `program_code/ml_training/advisory_review_packet.py`.

The new stdlib-only source contract defines:

- schema version `advisory_review_packet_v1`;
- `stable_sha256_json`;
- `build_advisory_review_packet`;
- `validate_advisory_review_packet`.

Valid packets require `not_authority=true`, `inactive_review_packet=true`,
`active=false`, `requires_operator_review=true`, `requires_governance=true`,
`execution_authority=not_granted`, `decision_lease_emitted=false`,
`demo_envelope_required_for_mutation=true`, and
`current_packet_grants_demo_mutation=false`.

The validator requires non-empty sha256 input hashes and rejects truthy nested
authority aliases, including snake_case and camelCase grant forms for order,
probe, live, mainnet, runtime, database, secret, promotion, Cost Gate, strategy
config, config write, and execution.

Updated L2 advisory surfaces.

`l2_ml_advisory_executor.py` now strips any model-supplied
`advisory_review_packet`, rebuilds a fresh local packet, and attaches it to
ledger/sink/result output. Early no-output failures now log inactive error
packets without claiming advisory success. `l2_advisory_orchestrator.py` carries
the packet through `DispatchResult`, and `/ml-advisory/dispatch` response data
now projects it for admitted outputs.

Updated MLDE and DreamEngine advisory producers.

`mlde_shadow_advisor.py` attaches packets to rank/veto recommendation payloads.
`dream_engine.py` attaches packets to parameter proposal insights and replay
candidate outputs. This does not change DB schema or runtime behavior.

Updated thought-gate outputs.

H1-E request envelope, H1-H governed decision, H1-I acceptance suite, and H1
handoff now carry inactive advisory packets and input hashes. Contract checks
validate packets through the shared validator.

## Dispatch

Required source feature chain was used:

`PM -> PA -> E1/E1a -> E2 -> E1-fix -> E2 -> E1-fix2 -> E2 -> E4 -> QA -> PM`

E2 found and drove closure of three substantive issues:

- L2 initially trusted model-supplied packets.
- Validator initially missed nested/camelCase authority aliases.
- Early L2 no-output ledger rows initially had no packet.

E2 rereview then found one remaining medium issue:

- admitted `/ml-advisory/dispatch` responses dropped the packet.

All findings were remediated and E2 final review passed. E4 regression passed.
QA accepted with concerns.

## Effect Review

Machine-readable `implementation_effect_review_v1`:

`docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-06--ai_ml_roadmap_loop_wp4_advisory_dreamengine_role_hardening.effect_review.json`

Summary:

- Pre-state: `G6` blocked because advisory outputs did not share one
  machine-checkable inactive role contract.
- Post-state: `G6` is `source_contract_ready_with_concerns`.
- Gate delta: `blocked_to_source_contract_ready_with_concerns`.
- Proof delta: advisory outputs now carry validator-backed inactive packets
  tied to input hashes and no-mutation fields.
- Verdict: `EFFECTIVE_WITH_CONCERNS`.

State packet:

`docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-06--ai_ml_roadmap_loop_wp4_advisory_dreamengine_role_hardening.state_packet.json`

State: `ADVANCED_WITH_CONCERNS`.

## Verification

Python compile gate:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile <changed WP4 Python files>
```

Result: PASS.

ML/helper tests:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q program_code/ml_training/tests/test_advisory_review_packet.py program_code/ml_training/tests/test_mlde_shadow_advisor.py -p no:cacheprovider
```

Result: `53 passed`.

L2 tests:

```bash
PYTHONDONTWRITEBYTECODE=1 PATH=venvs/mac_dev/bin:$PATH PYTHONPATH=program_code:program_code/exchange_connectors/bybit_connector/control_api_v1 python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_l2_p3a_ml_advisory.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_l2_p3b_hypothesize.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_l2_ml_advisory_dispatch_route.py -p no:cacheprovider
```

Result: `84 passed`.

Thought-gate tests:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code/exchange_connectors/bybit_connector/misc_tools:program_code/ai_agents/bybit_thought_gate:program_code python3 -m pytest -q program_code/ai_agents/bybit_thought_gate/tests/test_advisory_review_packet_thought_gate.py program_code/ai_agents/bybit_thought_gate/tests/test_ai_invocation_ledger.py program_code/ai_agents/bybit_thought_gate/tests/test_ai_invocation_governance.py program_code/ai_agents/bybit_thought_gate/tests/test_ai_cost_log_pricing_gate.py program_code/ai_agents/bybit_thought_gate/tests/test_route_binder_e2e.py -p no:cacheprovider
```

Result: `18 passed`.

Final whitespace/diff gate:

```bash
git diff --check
```

Result: PASS.

## Concerns

QA accepted WP4 with concerns:

- This remains source-only acceptance; no runtime or provider path was exercised.
- Upstream screen rejects and admission rejects are non-proposal gating outcomes,
  not advisory packets.
- Controlled Demo bandit remains blocked until DemoMutationEnvelope and real
  reward ledger prerequisites are accepted.

## Boundary

No runtime mutation, DB read/write, exchange/API/private read, MCP server start,
credential/secret access, provider call, order/probe, Cost Gate change, deploy,
live, or mainnet action was performed.

Pre-existing dirty worktree files under `memory/` were not staged or modified.

## Next Work

Next source-only loop item:

`WP5-DEMO-MUTATION-ENVELOPE-CONTRACT`

Expected scope: define `DemoMutationEnvelope` as a machine-checkable source
contract or explicitly map it to existing applier records. Do not implement
bandit runtime, mutate config, write DB rows, lower Cost Gate, contact provider
or exchange endpoints, deploy, or touch live/mainnet.
