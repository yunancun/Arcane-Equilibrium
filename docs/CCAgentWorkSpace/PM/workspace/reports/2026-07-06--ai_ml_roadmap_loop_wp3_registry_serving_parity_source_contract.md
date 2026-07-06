# 2026-07-06 AI/ML Roadmap Loop - WP3 Registry Serving Parity Source Contract

PM sign-off: `ADVANCED_WITH_CONCERNS_SOURCE_CONTRACT_READY`

Scope: continuous AI/ML Roadmap Autonomous Completion Loop, source-only WP3.
No runtime mutation, DB read/write, exchange/API/private read, MCP server start,
credential/secret access, order/probe, Cost Gate change, deploy, live, or
mainnet action was performed.

## Selected Work Item

Selected `roadmap_work_item_v1`:

- Work id: `WP3-REGISTRY-SERVING-PARITY-SOURCE-CONTRACT`
- Gate: `G5`
- Priority: `P1`
- Reason: WP2 PIT dataset manifest was green, and registry/advisory serving
  metadata is the next source-only dependency before advisory DreamEngine and
  serving parity work. Runtime/order-capable paths remain blocked by expired
  standing Demo authorization, so this item was limited to source contracts and
  tests.
- Machine-readable artifact:
  `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-06--ai_ml_roadmap_loop_wp3_registry_serving_parity_source_contract.work_item.json`

## Implementation

Added `program_code/ml_training/registry_serving_contract.py`.

The new stdlib-only source contract defines:

- canonical field `registry_serving_contract`;
- schema version `registry_serving_contract_v1`;
- `RegistryServingContractValidation`;
- `compute_registry_serving_contract_hash`;
- `extract_registry_serving_contract`;
- `attach_registry_serving_contract`;
- `validate_registry_serving_contract`.

`advisory_ready` requires `serving_mode=advisory_only`,
`not_authority=true`, `symlink_authority=false`,
`promotion_serving_ready=false`, `dataset_manifest_schema_version` matching
`pit_dataset_manifest_v1`, complete PIT/feature/label/split/leakage/serving
hashes, string policy fields, q10/q50/q90 artifact hashes, q10/q50/q90 quantile
trio metadata, and a stable contract hash.

The validator rejects unknown top-level fields, malformed hashes, partial or
extra quantile maps, non-string policies, research-only mode, and authority
aliases such as order/probe/promotion/runtime/DB/secret/live/mainnet grants.

Updated `program_code/ml_training/model_registry.py`.

When caller-provided registry serving metadata is present, the Python registry
path validates the contract and verifies q10/q50/q90 artifact hashes against
the actual local ONNX artifact sha256 values before DB registration is
attempted. If a contract-backed trio partially persists, the path raises
`registry_trio_persistence_incomplete:<quantile>` instead of silently accepting
a partial registry state.

Updated Rust registry and reload/capability surfaces.

`rust/openclaw_engine/src/ml/registry.rs` now validates advisory serving
metadata fields and compares the resolved row `artifact_sha256` with the
contract artifact hash for the resolved q10/q50/q90 slot. Direct
`reload_edge_predictor` remains fail-closed with
`registry_authorized_serving_contract_required`.

`rust/openclaw_engine/src/ipc_server/dispatch.rs` and the FastAPI capability
aggregation route now keep `reload_edge_predictor=false` even when ORT or stale
IPC data might otherwise imply direct reload availability. Capability metadata
records `reload_edge_predictor_reason` and
`registry_authorized_reload_required=true`.

## Dispatch

Required source feature chain was used:

`PM -> PA -> E1/E1a -> MIT/AI-E -> E2 -> E4 -> QA -> PM`

The first E2 pass found two blocking issues:

- Rust did not compare row `artifact_sha256` to the resolved quantile contract
  artifact hash.
- Python and Rust canonical schemas diverged on extra top-level fields.

Additional reviews then found two lower-level hardening issues:

- Rust capabilities still advertised direct reload in ORT builds.
- FastAPI aggregation could overlay stale/fake IPC
  `reload_edge_predictor=true`.

Remediation closed those findings. Final role results:

- PA: `DESIGN_READY_WITH_CONCERNS`, no source-only blocker.
- E1/E1a implementation: Python and Rust source contract groundwork.
- MIT/AI-E: no authority expansion accepted; residual persistence concern
  carried as future work.
- E2 final: `PASS`.
- E4 final: `PASS`.
- QA final: `ACCEPT_WITH_CONCERNS`.

## Effect Review

Machine-readable `implementation_effect_review_v1`:

`docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-06--ai_ml_roadmap_loop_wp3_registry_serving_parity_source_contract.effect_review.json`

Summary:

- Pre-state: `G5` blocked because registry serving metadata was not
  machine-checkable or artifact-bound.
- Post-state: `G5` is `advisory_source_contract_ready_with_concerns`.
- Gate delta: `blocked_to_advisory_source_contract_ready_with_concerns`.
- Proof delta: registry advisory metadata now requires PIT-derived parity hashes
  and row-bound q10/q50/q90 artifact hashes.
- Verdict: `EFFECTIVE_WITH_CONCERNS`.

State packet:

`docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-06--ai_ml_roadmap_loop_wp3_registry_serving_parity_source_contract.state_packet.json`

State: `ADVANCED_WITH_CONCERNS`.

## Verification

Python compile gate:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile program_code/ml_training/registry_serving_contract.py program_code/ml_training/model_registry.py program_code/ml_training/tests/test_registry_serving_contract.py program_code/ml_training/tests/test_model_registry.py program_code/exchange_connectors/bybit_connector/control_api_v1/app/engine_capabilities_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_engine_capabilities_routes.py
```

Result: PASS.

Focused Python tests:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q program_code/ml_training/tests/test_registry_serving_contract.py program_code/ml_training/tests/test_model_registry.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_engine_capabilities_routes.py -p no:cacheprovider
```

Result: `58 passed`.

Expanded ML source-contract tests:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q program_code/ml_training/tests/test_registry_serving_contract.py program_code/ml_training/tests/test_model_registry.py program_code/ml_training/tests/test_pit_dataset_manifest.py program_code/ml_training/tests/test_pit_dataset_manifest_builder.py program_code/ml_training/tests/test_proof_packet_contract.py program_code/ml_training/tests/test_canary_promoter.py program_code/ml_training/tests/test_model_registry_pg_integration.py -p no:cacheprovider
```

Result: `106 passed, 13 skipped`.

Rust formatting and focused tests:

```bash
PATH="$HOME/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$PATH" rustfmt --edition 2021 --check rust/openclaw_engine/src/ml/registry.rs rust/openclaw_engine/src/event_consumer/handlers/edge_predictor.rs rust/openclaw_engine/src/event_consumer/handlers/tests.rs rust/openclaw_engine/src/ipc_server/dispatch.rs rust/openclaw_engine/src/ipc_server/tests/dispatch.rs
cd rust/openclaw_engine && PATH="$HOME/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$PATH" cargo test ml::registry -- --test-threads=1
cd rust/openclaw_engine && PATH="$HOME/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$PATH" cargo test reload_edge_predictor -- --test-threads=1
cd rust/openclaw_engine && PATH="$HOME/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$PATH" cargo test get_build_capabilities -- --test-threads=1
```

Result: rustfmt PASS; `25 passed`; `4 passed`; `1 passed`.

Final whitespace/diff gate:

```bash
git diff --check
```

Result: PASS.

Known non-blocking warnings: existing Rust warnings for an unused
`async_trait::async_trait` import and `ScriptedSpawn` private interface surfaced
during focused tests. They were not introduced as functional blockers for WP3.

## Concerns

QA accepted WP3 with concerns:

- `registry_trio_persistence_incomplete` is fail-loud after partial write, not a
  transactional rollback.
- Runtime DB JSONB extraction and authorized serving reload integration remain
  future gated work.
- `promotion_serving_ready=false` by design; this checkpoint does not authorize
  model promotion or serving reload.
- Nearby Rust comments still contain stale ORT-readiness wording, while
  executable capability behavior and tests are fail-closed.

## Boundary

No runtime mutation, DB read/write, exchange/API/private read, MCP server start,
credential/secret access, order/probe, Cost Gate change, deploy, live, or
mainnet action was performed.

Pre-existing dirty worktree files under `memory/` were not staged or modified.

## Next Work

Next source-only loop item:

`WP4-ADVISORY-DREAMENGINE-ROLE-HARDENING`

Expected scope: harden L2/LLM/advisory outputs so they are
`not_authority=true`, budgeted/logged, input-hash-bound, and emitted only as
inactive review packets. They must not mutate strategy/config/orders and must
not bypass a separate Demo mutation envelope.
