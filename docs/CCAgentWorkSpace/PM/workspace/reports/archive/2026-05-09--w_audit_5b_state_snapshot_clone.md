# W-AUDIT-5b State Snapshot Clone Checkpoint

Date: 2026-05-09
Role: PM
Status: SOURCE/TEST COMPLETE

## Scope

This checkpoint closes the W-AUDIT-5b Python state-machine snapshot
`copy.deepcopy` hotspot without changing state-machine transition semantics.

- `AuthorizationObject`, `DecisionLeaseObject`, `GovernorState`, and
  `TierState` now expose explicit `clone()` snapshots.
- `state_machine_base.MultiObjectStoreMixin` now requires clone-backed snapshot
  objects instead of falling back to generic deepcopy.
- JSON-like mutable fields (`scope`, `intent`, `transitions`, `promotions`) are
  still copied recursively so returned snapshots remain externally isolated.
- Added behavior regressions for nested snapshot isolation and a static guard
  proving these modules no longer use generic `copy.deepcopy`.

## Verification

- `python3 -m py_compile ...state_machine_base.py ...authorization_state_machine.py ...decision_lease_state_machine.py ...risk_governor_state_machine.py ...learning_tier_gate.py`
- `python3 -m pytest .../test_authorization_state_machine.py .../test_decision_lease_state_machine.py .../test_risk_governor_state_machine.py .../test_learning_tier_gate.py -q` -> 250 passed
- `python3 -m pytest tests/structure/test_state_machine_snapshot_clone_static.py -q` -> 1 passed
- `git diff --check`

## Boundary

Source/test/docs only. No rebuild, restart, deploy, DB apply, live auth
mutation, scanner authority change, Executor hard authority, strategy/risk
config mutation, MAG-083/MAG-084 unlock, or true-live API action.

PM SIGN-OFF: APPROVED for this source checkpoint.
