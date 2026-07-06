# IBKR Demo Ready Loop - L0 Baseline Gap Report

Date: 2026-07-07
Loop: `L0_BASELINE_AUDIT`
Role: PM local source audit
Repo root: `/Users/ncyu/Projects/TradeBot/srv`

## Scope

This report audits the current IBKR Stock/ETF state against the requested Demo Ready definition:

- real IBKR paper API integration
- read-only runtime running
- paper order lifecycle running
- paper/shadow evidence loop running
- live-equivalent risk, audit, Decision Lease, Guardian, and risk gate controls
- live environment, live secret, and live order path hard-denied

No IBKR contact, connector runtime, gateway startup, secret-slot read, order route, database write, MCP runtime execution, or live/tiny-live path was performed.

## Sources Reviewed

- `docs/adr/0048-ibkr-stock-etf-paper-shadow-lane.md`
- `docs/governance_dev/amendments/2026-06-29--AMD-2026-06-29-01-ibkr-stock-etf-paper-shadow-lane.md`
- `docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md`
- `program_code/broker_connectors/ibkr_connector/`
- `rust/openclaw_types/src/stock_etf_lane.rs`
- `rust/openclaw_types/src/stock_etf_lane_scoped_ipc.rs`
- `rust/openclaw_types/src/stock_etf_broker_capability_registry.rs`
- `rust/openclaw_types/src/stock_etf_paper_order_request.rs`
- `rust/openclaw_types/src/ibkr_phase2_gate.rs`
- `rust/openclaw_types/src/ibkr_phase2_artifact.rs`
- `rust/openclaw_types/src/ibkr_phase2_runtime.rs`
- `rust/openclaw_types/src/ibkr_feature_flag_secret_auth.rs`
- `rust/openclaw_types/src/ibkr_paper_lifecycle.rs`
- `rust/openclaw_engine/src/ipc_server/dispatch.rs`
- `rust/openclaw_engine/src/ipc_server/method_registry.rs`
- `rust/openclaw_engine/src/ipc_server/handlers/stock_etf.rs`
- `rust/openclaw_engine/src/ipc_server/handlers/stock_etf/request_summaries.rs`
- `rust/openclaw_engine/src/ipc_server/tests/stock_etf/request_contracts.rs`
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-05--official_mcp_exchange_tool_review.md`
- `settings/broker/README.md`

## Baseline Findings

Current repo state is source-only guarded scaffolding, not Demo Ready runtime.

The accepted governance path is clear and internally consistent: ADR-0048 and AMD-2026-06-29-01 allow only `stock_etf_cash` IBKR read-only, paper, and shadow research under fail-closed gates. They explicitly deny IBKR live, tiny-live, margin, short, options, CFD, transfers, account-management writes, live secret slots, and direct Python broker write authority.

The Python IBKR package is intentionally inert. It exposes blocked previews and readiness payloads, but it imports no IBKR SDK, opens no socket or HTTP session, reads no secrets, and exposes no write-capable broker method.

The Rust type layer contains the core contracts needed for a future runtime boundary: Phase2 external surface gate, immutable gate artifact, secret-slot/topology/session evidence, feature flag plus scoped authorization matrix, broker capability registry, lane-scoped IPC, paper order request envelope, and paper lifecycle event log. These are validators and fixtures, not active runtime.

The Stock/ETF IPC namespace is separate from the existing crypto paper path. `stock_etf.submit_paper_order` is not the legacy `submit_paper_order` method; the legacy method still dispatches to the existing channel path and is not an IBKR alias.

The official MCP review blocks runtime MCP replacement for both IBKR and Bybit. MCP tools may inform offline taxonomy or UX only; no credentialed read, order path, proof lane, Cost Gate, or runtime integration is authorized without future ADR/AMD plus E3/BB review.

## Gap Matrix

| Loop | Current state | Demo Ready gap |
|---|---|---|
| L1 Phase2 external surface gate | Templates/checkpoints only; no immutable PASS artifact found. | Real secret-slot, topology, session, redaction, rate-limit, audit, policy, and PM/Operator-reviewed PASS artifact required before first IBKR contact. |
| L2 read-only IBKR runtime | Connector package is blocked preview-only. | No real IB Gateway/TWS loopback session, no read-only health/account/market-data runtime, no session attestation. |
| L3 data foundation | Source contracts exist for PIT universe, instrument identity, reference data, market-data provenance, and DB evidence shape. | No accepted market data vendor/tier, collector ingestion, DQ run, storage application, or evidence DB runtime. |
| L4 shadow collector | Shadow request/reconciliation/evidence contracts exist. | No collector start, no shadow signal emission, no shadow fill reconstruction, no evidence-clock runtime. |
| L5 paper order lifecycle | Paper request envelope and lifecycle event-log validators exist. | No paper account attestation, scoped paper authority, Rust broker-paper routing, broker acknowledgements, fill import, or lifecycle writer. |
| L6 evidence AI/ML loop | Scorecard and evidence source contracts exist. | No 6-8 week paper/shadow evidence clock, no paper-shadow reconciliation output, no scorecard derivation/verdict. |
| L7 release/disable packet | Release and disable/cleanup templates exist. | No validated shakedown packet, no cleanup execution proof, no release-disable packet. |

## Boundary Proof

- Live API required: no.
- Live endpoint required: no.
- Live secret required: no.
- Live order path required: no.
- Phase2 Gate PASS before IBKR contact: not present, so no IBKR contact was made.
- Python broker write authority: denied by source contracts and Python static guard.
- Bybit order path pollution: no evidence; `stock_etf.*` remains separate from legacy `submit_paper_order`.
- Runtime MCP execution: none performed and repo review blocks it.
- New ADR/AMD required for this audit: no.
- Secrets/session/operator approval used: none.
- IBKR connector runtime started: no.
- Paper order/fill/import/DB/evidence clock started: no.

## Tests

Passed:

```text
python3 -m pytest -q \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_ibkr_connector_skeleton.py \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_ibkr_connector_action_matrix.py \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_surface_coverage_static_guard.py

26 passed in 0.40s
```

Not run:

```text
/Users/ncyu/.cargo/bin/cargo test --manifest-path rust/Cargo.toml ...
```

Reason: the local Rust toolchain is unavailable. `which cargo` returned no executable; `/Users/ncyu/.cargo/bin/cargo` is a symlink to `rustup`, and `/Users/ncyu/.cargo/bin/rustup` is a broken symlink to `/opt/homebrew/bin/rustup-init`. This is an environment blocker for Rust verification, not an acceptance failure of the source contracts.

## LOOP_DECISION

- current_loop: `L0_BASELINE_AUDIT`
- verdict: `ADVANCE`
- evidence_artifacts:
  - `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-07--ibkr_demo_ready_l0_baseline_gap_report.md`
- tests:
  - Python Stock/ETF IBKR guard subset: `26 passed`
  - Rust focused guard subset: not run because local `cargo`/`rustup` is broken
- boundary_proof:
  - No IBKR contact, no secret read, no connector runtime, no paper order, no fill import, no DB/evidence writer, no MCP runtime execution, no live/tiny-live path, and no Bybit order path reuse.
- next_loop_or_exit: `L1_PHASE2_EXTERNAL_SURFACE_GATE`
- reason:
  - No repo-boundary conflict was found in L0. The next decisive gate is the required immutable `phase2_ibkr_external_surface_gate_v1` PASS artifact before any IBKR contact.
