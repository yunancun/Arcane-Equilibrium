# Scanner-Driven ALR Controller Contracts

Date: 2026-07-09
Owner: PM
Status: `ADVANCED`
Boundary label: `SOURCE_ONLY_OFFLINE_P0_P1`

## PM Sign-Off

PM SIGN-OFF: APPROVED.

`P0-AIML-ALR-CONTROLLER-CONTRACTS` is complete as a source-only controller
contract checkpoint. It adds ALR work-item, effect-review, and loop-state packet
contracts plus focused tests.

## Selection

The prior boundary packet state was `ADVANCED_WITH_CONCERNS`, and the stub queue
marked `P0-AIML-ALR-CONTROLLER-CONTRACTS` as the first `ACTIVE` row.

## Role Chain

Required implementation chain completed:

| Role | Status | Verdict |
|---|---|---|
| `PA(default)` | `DONE_WITH_CONCERNS` | design approved two-file scope |
| `E1(worker)` | `DONE` | implemented, then reworked E2 findings |
| `E2(explorer)` | `DONE` | final PASS |
| `E4(worker)` | `DONE_WITH_CONCERNS` | PASS; requested cached diff-check after staging |
| `QA(worker)` | `DONE_WITH_CONCERNS` | ACCEPT; requested exact staging only |

E2 initially found three issues: queue status support, `NOT_APPLIED` concern
strictness, and durable state-packet minimum fields. E1 reworked them. E2 then
found two remaining medium issues: missing `schema` and mixed concern
permissiveness. E1 reworked again. Final E2 passed.

## Implementation Delta

New source:

- `program_code/ml_training/alr_controller_contracts.py`
  - defines `alr_work_item_v1`, `alr_effect_review_v1`, and
    `alr_loop_state_packet_v1`;
  - builds, hashes, extracts, and validates each contract;
  - supports actual ALR queue statuses including `ACTIVE`,
    `DONE_WITH_CONCERNS`, `WAITING_*`, and `DEFERRED_P0`;
  - selects the first unblocked row;
  - validates loop-state minimum fields including exact `schema`;
  - requires all `BOUNDARY_VALIDATED_WITH_CONCERNS` concern entries to carry
    ADR/AMD + `NOT_APPLIED` + no-governance/no-authority wording;
  - recursively rejects truthy authority aliases.
- `program_code/ml_training/tests/test_alr_controller_contracts.py`
  - covers `ADVANCED`, `ADVANCED_WITH_CONCERNS`, `DEFER_EVIDENCE`, `ROTATED`,
    `STOP_NO_EDGE`, `STOP_RETENTION_RISK`, and `BLOCKED_BOUNDARY`;
  - covers real queue status flow, hash mismatch, unknown status, wrong
    boundary, truthy authority, false/disabled authority strings, and required
    state packet fields.

## Verification

PM accepted:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m py_compile program_code/ml_training/alr_controller_contracts.py program_code/ml_training/learning_effect_review.py program_code/ml_training/reward_ledger.py
```

Result: `PASS`.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q program_code/ml_training/tests/test_alr_controller_contracts.py program_code/ml_training/tests/test_learning_effect_review.py program_code/ml_training/tests/test_reward_ledger.py -p no:cacheprovider
```

Result: `110 passed`.

Executable runtime/network/DB/order import scan on
`program_code/ml_training/alr_controller_contracts.py`: `PASS`, no matches.

`git diff --check` on the source/test files: `PASS`. E4 noted the new files were
untracked during its run, so PM must run `git diff --cached --check` after exact
staging before commit.

## Boundary

No denied action was performed or introduced:

- no runtime mutation;
- no PG read/write or migration;
- no IPC;
- no Bybit or official MCP contact;
- no Decision Lease;
- no order/probe;
- no Cost Gate change;
- no `_latest` overwrite;
- no serving/proof/promotion authority;
- no delete/apply;
- no cron/daemon/scheduler/service/env mutation;
- no live/mainnet.

The source contains denial vocabulary such as runtime, bybit, mcp, latest,
serving, and promotion only to fail closed on authority expansion.

## State

State packet:
`docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-09--scanner_driven_alr_controller_contracts.state_packet.json`

Status: `ADVANCED`

Next row:

`P0-AIML-ALR-LEARNING-TARGET-ARBITER`

Required next chain:

`PM -> PA -> E1/E1a -> E2 -> E4 -> QA -> PM`

The next row remains source-only and must not touch runtime, PG, IPC, Bybit/MCP,
scheduler, service/env, `_latest`, proof/promotion, delete/apply, Cost Gate,
order/probe, or live/mainnet.
