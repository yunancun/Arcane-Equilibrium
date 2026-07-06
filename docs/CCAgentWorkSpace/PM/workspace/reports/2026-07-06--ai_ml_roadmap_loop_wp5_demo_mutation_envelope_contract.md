# 2026-07-06 AI/ML Roadmap Loop - WP5 Demo Mutation Envelope Contract

PM sign-off: `STOPPED_AFTER_SOURCE_CONTRACT_READY`

Scope: continuous AI/ML Roadmap Autonomous Completion Loop, source-only WP5.
No runtime mutation, DB read/write, exchange/API/private read, MCP server start,
credential/secret access, provider call, order/probe, Cost Gate change, deploy,
live, mainnet, or bandit runtime action was performed.

## Selected Work Item

Selected `roadmap_work_item_v1`:

- Work id: `WP5-DEMO-MUTATION-ENVELOPE-CONTRACT`
- Gate: `G6`
- Priority: `P1`
- Reason: WP4 advisory role hardening made L2/LLM/MLDE/DreamEngine outputs
  inactive review packets. WP5 needed the equivalent machine-checkable boundary
  for future bounded Demo mutation before any controlled Demo bandit work.
- Machine-readable artifact:
  `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-06--ai_ml_roadmap_loop_wp5_demo_mutation_envelope_contract.work_item.json`

## Implementation

Added `program_code/ml_training/demo_mutation_envelope.py`.

The new stdlib-only source contract defines:

- schema version `demo_mutation_envelope_v1`;
- stable JSON hashing;
- `build_demo_mutation_envelope`;
- `validate_demo_mutation_envelope`;
- `extract_demo_mutation_envelope`;
- bounded-delta construction.

The envelope records source proposal or recommendation id, source payload hash,
application type, target, previous snapshot, proposed patch, bounded delta,
max-delta policy, governance verdict, rollback handle, IPC response hash/status,
post-change review, proof linkage, and explicit no-authority answers.

Countability is fail-closed. `effective_learning_countable=true` requires an
applied Demo row with a non-empty patch, no dedupe, no dry-run, concrete finite
nonnegative `max_delta` or `max_delta_pct` for every bounded-delta row,
`within_policy=true`, rollback evidence, governance review allowance,
post-change review pass, and valid proof linkage.

Rows remain audit-only or invalid when they are empty, dedupe, dry-run, skipped,
failed, non-demo, live, live_demo, missing concrete bounds, missing rollback,
missing proof, or missing review.

Added `program_code/ml_training/demo_mutation_envelope_applier_mapping.py`.

The mapping helper turns existing `mlde_demo_applier._record_application(...)`
inputs into `demo_mutation_envelope_v1`. It is pure source logic: no DB read,
no DB write, no IPC call, no exchange/provider contact, and no rollback action.
`_record_application` now attaches the envelope under
`payload.demo_mutation_envelope` while preserving existing SQL columns, params
shape, status semantics, dedupe behavior, IPC params, and live-candidate flow.

Raw IPC response details stay in the existing `ipc_response` column; the
envelope carries only hash/status.

## Dispatch

Required source feature chain was used:

`PM -> PA -> E1 -> E1a -> E2 -> E1-fix -> E2 -> E4 -> QA -> PM`

E2 initially found two high issues:

- countable envelopes could pass without a concrete max-delta bound;
- authority/scope scanners missed `secretAccess`, `mainnetAccess`,
  `candidateScope="live"`, and `candidateEngineMode="live_demo"` aliases.

E1-fix closed both issues. E2 rereview passed with no findings. E4 regression
passed. QA accepted.

## Effect Review

Machine-readable `implementation_effect_review_v1`:

`docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-06--ai_ml_roadmap_loop_wp5_demo_mutation_envelope_contract.effect_review.json`

Summary:

- Pre-state: `G6` blocked because DemoMutationEnvelope was unformalized.
- Post-state: `G6` is `source_contract_ready`.
- Gate delta: `blocked_to_source_contract_ready`.
- Proof delta: future Demo mutation learning now requires previous/proposed,
  bounded-delta, governance, rollback, review, and proof evidence before
  countability.
- Verdict: `EFFECTIVE`.

State packet:

`docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-06--ai_ml_roadmap_loop_wp5_demo_mutation_envelope_contract.state_packet.json`

State: `STOPPED`.

Stop reason: `STOP_LOSS_CONTROL`.

## Verification

Python compile gate:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile program_code/ml_training/demo_mutation_envelope.py program_code/ml_training/demo_mutation_envelope_applier_mapping.py program_code/ml_training/mlde_demo_applier.py program_code/ml_training/tests/test_demo_mutation_envelope.py program_code/ml_training/tests/test_demo_mutation_envelope_applier_mapping.py
```

Result: PASS.

Envelope and mapping tests:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q program_code/ml_training/tests/test_demo_mutation_envelope.py program_code/ml_training/tests/test_demo_mutation_envelope_applier_mapping.py -p no:cacheprovider
```

Result: `49 passed`.

Existing applier tests:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q program_code/ml_training/tests/test_mlde_demo_applier.py -p no:cacheprovider
```

Result: `31 passed`.

Adjacent contract tests:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q program_code/ml_training/tests/test_advisory_review_packet.py program_code/ml_training/tests/test_proof_packet_contract.py program_code/ml_training/tests/test_pit_dataset_manifest.py -p no:cacheprovider
```

Result: `93 passed`.

Forbidden surface scan:

```bash
rg -n "requests\\.|httpx\\.|urllib\\.|psycopg2|asyncpg|one_shot_ipc_call|INSERT INTO|UPDATE |DELETE FROM|subprocess|place_order|cancel_order|create_order|OPENCLAW_ALLOW_MAINNET=1" program_code/ml_training/demo_mutation_envelope.py program_code/ml_training/demo_mutation_envelope_applier_mapping.py
```

Result: PASS, no actionable forbidden surface matches.

Final whitespace/diff gate:

```bash
git diff --check
```

Result: PASS.

## Concerns

- This remains source-only acceptance; no runtime/deployed E2E, DB
  verification, IPC execution, or live proof was performed.
- Controlled Demo bandit runtime remains blocked until real reward ledger
  exists.
- Runtime/order-capable outcome collection remains blocked by expired standing
  Demo authorization.

## Boundary

No runtime mutation, DB read/write, exchange/API/private read, MCP server start,
credential/secret access, provider call, order/probe, Cost Gate change, deploy,
live, mainnet, or bandit runtime action was performed.

Unrelated dirty worktree files under `memory/*` and non-WP5 ML files were not
staged for this checkpoint.

## Stop

The next highest-priority work is not bandit runtime. It is the standing Demo
loss-control envelope refresh/current-head path under `TODO.md` P0, which
requires PM->E3->BB and runtime/loss-control authorization. This loop stops as
`STOP_LOSS_CONTROL` rather than bypassing that gate.
