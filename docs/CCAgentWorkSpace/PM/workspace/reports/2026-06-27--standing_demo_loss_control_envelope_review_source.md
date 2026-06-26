# Standing Demo Loss-Control Envelope Review Source

| Field | Value |
|---|---|
| `blocker_id` | `P0-STANDING-DEMO-LOSS-CONTROL-ENVELOPE-RUNTIME-MATERIALIZATION-REVIEW` |
| `state_transition` | `DONE_WITH_CONCERNS` |
| `session_state` | `/tmp/openclaw/session_loop_state_20260626T230259Z_standing_demo_loss_control_envelope_review.json` |
| `local_pre_edit_head` | `ec5b255657b0ec231ce6355ae6ed0792b115d476` |
| `runtime_head_before_materialization_review` | `trade-core:e29c96cc754d6599a541ff058aea3a9a20817bf3` |
| `next_blocker_id` | `P0-STANDING-DEMO-LOSS-CONTROL-ENVELOPE-RUNTIME-MATERIALIZATION-E3-REVIEW` |

## Outcome

Added a source-only standing Demo loss-control envelope materialization review helper. It previews a future runtime-readable `standing_demo_operator_authorization_v1` envelope and checks the exact path/env/TTL/cap/operator/candidate scope before any runtime mutation.

The source review checkpoint is complete with concerns because no runtime standing envelope was materialized, no env/crontab wiring was changed, and no bounded execution was authorized.

## Review Contract

Default proposed envelope shape:

- Runtime JSON path: `/tmp/openclaw/cost_gate_learning_lane/standing_demo_operator_authorization.json`
- Env var: `OPENCLAW_COST_GATE_STANDING_DEMO_AUTHORIZATION_JSON`
- Environment/scope: `demo` / `demo_api_only_bounded_probe`
- Candidate scope: exact side-cell, strategy, symbol, side, and horizon from the ranked false-negative packet
- Default TTL: `12h`; validator max TTL: `24h`
- Default probe-order cap: `2`; hard helper cap: `3`
- Scheduled bounded probe operator authorization decision must remain `defer`

The helper reuses `summarize_standing_demo_authorization`, so the preview must pass the same machine-checkable schema/status/Demo scope/candidate scope/TTL/cap/no-authority validation used by false-negative review/preflight.

## Source Changes

- Added `helper_scripts/research/cost_gate_learning_lane/standing_demo_loss_control_envelope_review.py`.
- Added focused tests in `helper_scripts/research/tests/test_cost_gate_standing_demo_loss_control_envelope_review.py`.
- Updated `helper_scripts/SCRIPT_INDEX.md` with the new helper and boundary.

## Local Runtime Artifact Smoke

On this workstation, the canonical local `/tmp/openclaw/cost_gate_learning_lane/*_latest.json` false-negative artifacts were missing. Running the new helper against the expected local latest candidate packet failed closed:

```text
status=FALSE_NEGATIVE_CANDIDATE_PACKET_NOT_READY
envelope_preview={}
materialization_plan={}
runtime_mutation_performed=false
standing_envelope_materialized=false
bounded_demo_probe_authorized=false
order_authority_granted=false
```

This local workstation smoke is not a replacement for the prior `trade-core` runtime evidence in `2026-06-27--standing_demo_false_negative_preflight_runtime_sync_apply.md`; it only verifies the new helper's missing-artifact behavior.

## Verification

```text
PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_standing_demo_loss_control_envelope_review.py
PYTHONPATH=helper_scripts/research python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/standing_demo_loss_control_envelope_review.py
PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_standing_demo_loss_control_envelope_review.py helper_scripts/research/tests/test_cost_gate_false_negative_bounded_probe_preflight.py helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py
git diff --check
```

Results:

- Focused helper tests: `7 passed`.
- py_compile passed.
- Adjacent standing/preflight/policy suites: `107 passed`.
- `git diff --check` passed.

## Boundary

No runtime source sync, standing-envelope materialization, service restart, environment edit, crontab mutation, manual cron run, PG query/write, Bybit/API/order/cancel/modify, Cost Gate lowering, writer/adapter enablement, active probe/order/live authority, or profit/proof claim occurred.

Next work is an E3 runtime materialization review. It must first confirm fresh runtime candidate artifacts and the exact helper-generated plan, then may apply only the reviewed envelope file/env wiring under Demo loss controls. It must not set scheduled bounded auth to `authorize` or submit orders.
