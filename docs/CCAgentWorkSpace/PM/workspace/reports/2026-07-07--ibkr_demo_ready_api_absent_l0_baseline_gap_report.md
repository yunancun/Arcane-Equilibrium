# IBKR Demo Ready API-Absent Loop - L0 Baseline Gap Report

Date: 2026-07-07
Loop: `L0_BASELINE_AUDIT`
Mode: `DEMO_READY_API_ABSENT`
Role: PM local no-contact engineering
Repo root: `/Users/ncyu/Projects/TradeBot/srv`

## Scope

This L0 baseline follows the API-absent loop variant from the attached prompt. The target is not real IBKR API contact. The target is engineering readiness with all real credential, Gateway/TWS session, operator approval, and immutable real Phase2 PASS evidence recorded as `external_verification_pending`.

No IBKR contact, secret read, connector runtime startup, broker paper route, fill import, DB apply, runtime MCP execution, live endpoint, live secret, or live order path was used.

## Baseline

Current source already contains substantial ADR-0048 scaffolding:

- IBKR Python connector package is inert and source-only.
- Rust contracts exist for Phase2 gate/artifact/runtime evidence, feature flag and scoped authorization, lane-scoped IPC, broker capability registry, paper request envelopes, paper lifecycle, evidence clock, scorecards, release packet, and disable cleanup.
- Stock/ETF IPC is in the `stock_etf.*` namespace and is not an alias for legacy crypto `submit_paper_order`.
- Settings templates are default-blocked and secret-free.
- Official MCP review blocks runtime MCP execution and keeps MCP tools out of proof/order paths.

The main API-absent gap was a single no-contact engineering packet that ties L0-L7 together without requiring real IBKR credential/session/contact. That packet now exists in:

- `program_code/broker_connectors/ibkr_connector/api_absent_engineering.py`

## Dirty Worktree Boundary

The worktree contained unrelated user-side changes before and during this loop, including PM/PA memory, console static files, ML training files, and untracked reports/static assets. This loop did not revert or modify those unrelated files.

## Tests

Passed:

```text
python3 -m pytest -q \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_ibkr_api_absent_engineering.py \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_ibkr_connector_skeleton.py \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_ibkr_connector_action_matrix.py \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_surface_coverage_static_guard.py

29 passed in 0.43s
```

Additional check:

```text
python3 -m py_compile program_code/broker_connectors/ibkr_connector/api_absent_engineering.py
```

Passed.

Broader Stock/ETF Python suite:

```text
python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_*.py
```

Result: `183 passed, 1 failed`. The failure is `test_stock_etf_console_tab_registered`, which reads dirty user-edited `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/console.html` and expects `id: 'stock-etf'`. This file is outside the IBKR API-absent connector change set and was already dirty, so this is recorded as an unrelated test blocker with a safe fallback, not an API-absent engineering STOP.

Not run:

```text
cargo test ...
```

Reason: local Rust toolchain is unavailable. `cargo` is not on PATH, and `/Users/ncyu/.cargo/bin/rustup` is a broken symlink to `/opt/homebrew/bin/rustup-init`. This loop did not modify Rust source.

## LOOP_DECISION

- current_loop: `L0_BASELINE_AUDIT`
- verdict: `ADVANCE`
- mode: `DEMO_READY_API_ABSENT`
- implemented_changes:
  - Added no-contact API-absent engineering packet and tests.
  - Recorded existing reusable infrastructure and forbidden Bybit reuse.
- evidence_artifacts:
  - `program_code/broker_connectors/ibkr_connector/api_absent_engineering.py`
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_ibkr_api_absent_engineering.py`
  - `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-07--ibkr_demo_ready_api_absent_l0_baseline_gap_report.md`
- tests:
  - Focused IBKR/API-absent/static guard subset: `29 passed`
  - `py_compile` for new packet: passed
  - Broader Stock/ETF suite: `183 passed, 1 unrelated dirty-console failure`
  - Rust tests: not run due broken local toolchain
- boundary_proof:
  - No IBKR contact, no secret read/serialization, no connector runtime, no broker order route, no fill import, no DB/evidence writer, no runtime MCP, no live/tiny-live, no Bybit path reuse.
- external_verification_pending:
  - Real IBKR paper/read-only credential
  - Gateway/TWS session
  - Operator approval for external contact
  - Immutable real Phase2 PASS artifact
  - Real account fingerprint attestation
  - Real market data entitlement attestation
- next_loop_or_exit: `L1_PHASE2_GATE_SCAFFOLD_NO_CONTACT`
- reason:
  - Missing real IBKR credential/session/approval is not a STOP condition in API-absent mode. No hard engineering blocker was found in L0.
