# IBKR Dual Engine No-Contact Infrastructure Completion

Date: 2026-07-07
Role: PM local implementation
Status: INFRASTRUCTURE_COMPLETE_STOP
Scope: IBKR `stock_etf_cash` source/no-contact module foundation

## Implemented

- Added deterministic dual-engine contract fixture:
  - `ibkr_demo_engine`
  - `ibkr_live_engine`
- Attached the fixture to `ibkr_demo_ready_api_absent_engineering_packet_v1`
  as `dual_engine_fixture`.
- Exported the dual-engine fixture, profile type, contract type, and engine IDs
  from `program_code/broker_connectors/ibkr_connector/`.
- Added `settings/broker/ibkr_dual_engine_contract.template.toml` as the
  source-only template for engine identities, trade-core port reservations,
  broker Gateway/TWS port references, interface policy, and Phase2 seal policy.
- Updated IBKR connector README and broker settings README to describe the new
  source surface and denied movement paths.

## Contract Shape

`ibkr_demo_engine`:

- role: `paper_demo_execution_and_evidence`
- API binding kind: `paper_or_demo`
- local engine IPC reserved port: `18790`
- broker Gateway port reference: `4002`
- true-live binding: denied by design

`ibkr_live_engine`:

- role: `live_grade_gate_risk_session_rehearsal`
- API binding kind: `live_or_second_paper_for_comparison`
- local engine IPC reserved port: `18791`
- broker Gateway/TWS port references: `4001`, `7496`
- true-live binding: possible only after future governance and gate PASS
- current true-live binding: false

Shared local port plan:

- Bybit control API reference: `8710`
- Bybit OpenClaw proxy reference: `18789`
- IBKR control API reserved: `8711`
- No service was started and no listener was bound.

## Interface Boundary

The source interface is read/write-capable at the contract level so future
paper or authorized order flows can share the same API shape. Current runtime
authority remains false.

Denied movement paths are pinned:

- `account_transfer`
- `cash_withdrawal`
- `internal_transfer`
- `external_transfer`

Python broker write authority remains false. Rust authority, Decision Lease,
risk guard, idempotency, and audit remain required before any broker write can
become effect-capable.

## Phase2 Seal Model

The fixture pins the latency-safe model:

- full Phase2 seal before session/admission epoch,
- cached epoch and capability check per call,
- no full Phase2 artifact revalidation per order,
- per-order Decision Lease, risk guard, and audit event remain required,
- re-seal on engine profile, API binding, account fingerprint, slot capability,
  Gateway process/port, risk policy, Decision Lease policy, or operator epoch
  changes.

## Verification

- `python3 -m py_compile ...`
- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_ibkr_api_absent_engineering.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_ibkr_connector_skeleton.py -q`
  - result: `18 passed`
- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_*.py -q`
  - result: `187 passed`
- `RUSTC=/Users/ncyu/.rustup/toolchains/stable-aarch64-apple-darwin/bin/rustc RUSTDOC=/Users/ncyu/.rustup/toolchains/stable-aarch64-apple-darwin/bin/rustdoc /Users/ncyu/.rustup/toolchains/stable-aarch64-apple-darwin/bin/cargo test -p openclaw_types`
  - result: PASS, including doc-tests
- `RUSTC=/Users/ncyu/.rustup/toolchains/stable-aarch64-apple-darwin/bin/rustc RUSTDOC=/Users/ncyu/.rustup/toolchains/stable-aarch64-apple-darwin/bin/rustdoc /Users/ncyu/.rustup/toolchains/stable-aarch64-apple-darwin/bin/cargo test -p openclaw_engine stock_etf`
  - result: PASS, `32 passed`

## Boundary Proof

- No IBKR SDK import.
- No IBKR network contact.
- No Gateway/TWS startup.
- No credential or secret content read.
- No connector runtime start.
- No service listener bind.
- No paper/live order route.
- No fill import.
- No DB/evidence writer start.
- No runtime MCP execution.
- No Bybit order-path reuse.
- No withdraw or transfer path.

## External Verification Pending

Only future external items remain:

- operator-provided paper/demo credential or account slot metadata,
- operator-provided Gateway/TWS session evidence,
- operator approval for first real contact,
- immutable Phase2 PASS artifact before contact,
- future governance update before any true-live IBKR binding.

This is not an engineering blocker for the completed no-contact infrastructure
target. It is the correct stop point for this session.
