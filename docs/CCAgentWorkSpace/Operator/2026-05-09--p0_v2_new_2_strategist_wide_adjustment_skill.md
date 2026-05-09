# P0-V2-NEW-2 Strategist Wide-Adjustment Skill

Date: 2026-05-09
Status: SOURCE/TEST CLOSED

## What Changed

The 50% Strategist cap was kept as freedom, not turned into a new approval gate.

The 30%-50% zone is now exposed to Strategist as a skill:

- Rust sends `strategist_skill.name = "wide_parameter_adjustment"` with every
  Strategist evaluation payload.
- Python prompt shows:
  - `normal_range`: ordinary <=30% tuning;
  - `wide_skill_range`: deliberate 30%-50% tuning.
- The prompt tells Strategist to use the wider range only when evidence is poor
  enough and the move has a coherent reason.

Rust still enforces the configured maximum envelope. It does not add a new
supervised gate and does not reject 30%-50% moves merely because they are large.

## Verification

- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_p1_audit_smoke.py -q`
- `cargo test -p openclaw_engine --lib strategist_scheduler -- --nocapture`
- `cargo fmt --all --check`
- `git diff --check`

## Boundary

No rebuild/restart, no provider call, no DB write, no live auth mutation, and no
runtime parameter reload.
