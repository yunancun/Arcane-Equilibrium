# 62-Finding Remediation Tracking

Created: 2026-04-28
Owner: PM
Source: `docs/audit/final_record_zh.md`
Status values: `open`, `in_progress`, `fixed`, `false_positive`, `accepted_risk`

## Batch Status

| Batch | Theme | Count | Status |
| --- | --- | ---: | --- |
| A | Live write boundary freeze | 5 | fixed |
| B | Critical auth / secrets / API exposure | 14 | open |
| C | Trading record durability | 12 | open |
| D | Risk and config fail-closed | 8 | open |
| E | Operator / runtime ownership | 13 | open |
| F | ML and agent autonomy readiness | 10 | open |
| Total | all audit findings | 62 | 62 represented exactly once |

## Finding Ledger

| ID | Sev | Batch | Status | Owner Chain | Fix Commit | Verification |
| --- | --- | --- | --- | --- | --- | --- |
| LP-001 | P1 | A | fixed | PM -> CC/E3/BB/PA -> E1/E1a -> E2 -> E4 -> PM | uncommitted | pytest auth/live gate suite + Rust live_authorization |
| OE-007 | P1 | A | fixed | PM -> CC/E3/BB/PA -> E1/E1a -> E2 -> E4 -> PM | uncommitted | pytest live_gate_fallback + rg no direct live REST fallback |
| OS-001 | P1 | A | fixed | PM -> CC/E3/BB/PA -> E1/E1a -> E2 -> E4 -> PM | uncommitted | pytest operator_live_flatten_boundary + rg no mainnet script flatten |
| RC-001 | P1 | A | fixed | PM -> CC/E3/BB/PA -> E1/E1a -> E2 -> E4 -> PM | uncommitted | cargo dual_rail_dispatch + Rust emergency close tests |
| SW-002 | P1 | A | fixed | PM -> CC/E3/BB/PA -> E1/E1a -> E2 -> E4 -> PM | uncommitted | cargo strategist_scheduler/edge_reload/live_auth_watcher dynamic slot tests |
| DAPI-001 | P1 | B | open | TBD | TBD | TBD |
| DAPI-002 | P2 | B | open | TBD | TBD | TBD |
| DAPI-003 | P2 | B | open | TBD | TBD | TBD |
| DAPI-004 | P2 | B | open | TBD | TBD | TBD |
| DAPI-005 | P2 | B | open | TBD | TBD | TBD |
| DAPI-006 | P2 | B | open | TBD | TBD | TBD |
| RC-003 | P1 | B | open | TBD | TBD | TBD |
| SC-001 | P1 | B | open | TBD | TBD | TBD |
| SC-002 | P1 | B | open | TBD | TBD | TBD |
| SC-003 | P1 | B | open | TBD | TBD | TBD |
| SC-004 | P2 | B | open | TBD | TBD | TBD |
| SC-005 | P2 | B | open | TBD | TBD | TBD |
| SC-006 | P2 | B | open | TBD | TBD | TBD |
| SC-007 | P2 | B | open | TBD | TBD | TBD |
| OE-001 | P1 | C | open | TBD | TBD | TBD |
| OE-002 | P1 | C | open | TBD | TBD | TBD |
| OE-003 | P1 | C | open | TBD | TBD | TBD |
| OE-004 | P1 | C | open | TBD | TBD | TBD |
| OE-005 | P2 | C | open | TBD | TBD | TBD |
| OE-008 | P2 | C | open | TBD | TBD | TBD |
| OE-009 | P2 | C | open | TBD | TBD | TBD |
| DBW-001 | P1 | C | open | TBD | TBD | TBD |
| DBW-002 | P1 | C | open | TBD | TBD | TBD |
| DBW-003 | P1 | C | open | TBD | TBD | TBD |
| DBW-004 | P2 | C | open | TBD | TBD | TBD |
| DBW-005 | P2 | C | open | TBD | TBD | TBD |
| RC-002 | P1 | D | open | TBD | TBD | TBD |
| RC-004 | P1 | D | open | TBD | TBD | TBD |
| RC-005 | P1 | D | open | TBD | TBD | TBD |
| RC-006 | P2 | D | open | TBD | TBD | TBD |
| SADF-002 | P2 | D | open | TBD | TBD | TBD |
| SADF-003 | P1 | D | open | TBD | TBD | TBD |
| LP-002 | P2 | D | open | TBD | TBD | TBD |
| OE-006 | P2 | D | open | TBD | TBD | TBD |
| SW-001 | P1 | E | open | TBD | TBD | TBD |
| SW-003 | P2 | E | open | TBD | TBD | TBD |
| SW-004 | P2 | E | open | TBD | TBD | TBD |
| SW-005 | P2 | E | open | TBD | TBD | TBD |
| SW-006 | P2 | E | open | TBD | TBD | TBD |
| SW-007 | P3 | E | open | TBD | TBD | TBD |
| OS-002 | P1 | E | open | TBD | TBD | TBD |
| OS-003 | P2 | E | open | TBD | TBD | TBD |
| OS-004 | P2 | E | open | TBD | TBD | TBD |
| OS-005 | P2 | E | open | TBD | TBD | TBD |
| OS-006 | P2 | E | open | TBD | TBD | TBD |
| OS-007 | P3 | E | open | TBD | TBD | TBD |
| DAPI-007 | P2 | E | open | TBD | TBD | TBD |
| MLM-001 | P1 | F | open | TBD | TBD | TBD |
| MLM-002 | P1 | F | open | TBD | TBD | TBD |
| MLM-003 | P1 | F | open | TBD | TBD | TBD |
| MLM-004 | P1 | F | open | TBD | TBD | TBD |
| MLM-005 | P1 | F | open | TBD | TBD | TBD |
| SADF-001 | P1 | F | open | TBD | TBD | TBD |
| SADF-004 | P2 | F | open | TBD | TBD | TBD |
| SADF-005 | P2 | F | open | TBD | TBD | TBD |
| SADF-006 | P3 | F | open | TBD | TBD | TBD |
| LP-003 | P3 | F | open | TBD | TBD | TBD |

## Preflight Notes

- Linux `trade-core` repo state at Batch A start: `main...origin/main`, clean.
- Linux watchdog at Batch A start: `engine_alive=true`, `demo/live=true`, `paper=false`. This runtime/docs drift must be handled before deploy or restart.
- Mac worktree is dirty from prior Codex/user work. Batch A implementation must preserve unrelated edits and avoid broad rewrites.

## Batch A Verification Notes

- Python: `/tmp/openclaw-batch-a-venv/bin/python -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_live_authorization_signing.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_executor_shadow_toggle_api.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_promote_api.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_live_auth_recheck_trigger.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_live_gate_fallback.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_operator_live_flatten_boundary.py` -> 69 passed.
- Rust release checks (E4): `cargo test --release -p openclaw_engine live_authorization --lib` -> 18 passed; `tick_pipeline::tests::dual_rail_dispatch --lib` -> 13 passed; `strategist_scheduler::tests --lib` -> 26 passed; `main_boot_tasks::edge_reload_tests --bin openclaw-engine` -> 13 passed; `live_auth_watcher --bin openclaw-engine` -> 10 passed.
- Static hygiene: `python3 -m py_compile` on touched Python files passed; `git diff --check` passed.
- E2 adversarial review initially blocked on Python v1 auth verifier drift; follow-up review accepted after `executor_routes.py` and auth signing tests were upgraded to schema v2.
- No deploy/restart performed. Linux `trade-core` runtime drift from preflight remains out of scope for Batch A implementation.
