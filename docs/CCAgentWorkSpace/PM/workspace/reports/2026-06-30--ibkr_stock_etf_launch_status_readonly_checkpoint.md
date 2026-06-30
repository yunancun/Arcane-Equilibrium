# PM Checkpoint - IBKR Stock/ETF Launch Status Read-Only Surface

Date: 2026-06-30
Role: PM(default)
Scope: ADR-0048 `stock_etf_cash` Phase 4/5 display-only launch/release blocker status surface.

## Verdict

`DONE_WITH_CONCERNS_SOURCE_ONLY`

This checkpoint exposes launch/release blocker posture to the Stock/ETF GUI through a read-only Rust IPC, authenticated FastAPI route, and static GUI panel. It does not start Phase 2, Phase 3, or Phase 5; contact IBKR; read/create secrets; start an evidence clock; run a scorecard writer; apply DB changes; route orders; authorize paper-shadow launch; authorize tiny-live/live; or alter Bybit runtime behavior.

## Changes

- Rust IPC fixture:
  - Added `stock_etf.get_launch_status`.
  - Registered it in dispatch and method registry as read-only / `IpcSlotRequirement::None`.
  - Returns a blocked `phase5_launch_status_source_fixture` built from existing source contracts: `stock_etf_release_packet_v1`, `stock_etf_kill_switch_and_disable_cleanup_runbook_v1`, and `tiny_live_adr_eligibility_v1`.
  - Preserves `phase3_started=false`, `phase5_started=false`, `paper_shadow_launch_authorized=false`, `tiny_live_or_live_authorized=false`, `connector_runtime_started=false`, `scorecard_writer_started=false`, `db_apply_performed=false`, `evidence_clock_started=false`, `ibkr_call_performed=false`, `secret_slot_touched=false`, `order_routed=false`, and `bybit_ipc_reused=false`.
- FastAPI:
  - Added authenticated no-store `GET /api/v1/stock-etf/launch-status`.
  - Calls only `stock_etf.get_launch_status` with empty params.
  - Ignores query/header supplied launch, Phase 5, live, and side-effect claims.
  - Fail-closes IPC unavailable/errors to `degraded` and converts IPC payload drift, accepted launch artifacts before launch audit, positive proof/hash/count fields, Phase 3/5 start, launch/live authority, connector/evidence/scorecard/DB side effects, IBKR contact, secret access, order routing, and Bybit IPC reuse into `contract_violation_blocked`.
- GUI:
  - Added `Launch Gate` summary metric and `Launch / Release Status` panel to `tab-stock-etf.html`.
  - Renders release packet, disable-cleanup runbook, tiny-live ADR eligibility, launch/live authorization flags, side-effect flags, and blockers.
  - Uses only `ocApi(... method: 'GET' ...)`; no forms, direct `fetch`, browser storage authority, secret widgets, or order widgets.
- Contract:
  - `lane_scoped_ipc_v1` now includes `GetLaunchStatus` as display-only / non-effect-capable.
  - `gui_lane_contract_v1` now requires exact display-only GET `/api/v1/stock-etf/launch-status`.
  - Blocked GUI template and Phase 0 GUI contract documentation were updated with the launch-status endpoint in disabled GET-only state.

## Verification

- `python3 -m py_compile` on touched Stock/ETF route, normalizer, fixture, route tests, and static guard: PASS.
- Rust format check on changed Rust files, with `lib.rs` checked using `skip_children=true` to avoid unrelated module traversal: PASS.
- Node inline script parser for `tab-stock-etf.html`: PASS (`7` scripts).
- `python3 -m pytest` on all Stock/ETF route tests plus static no-write guard: `58 passed`.
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf`: `15 passed` in the targeted unit filter; remaining integration targets were filtered with 0 tests and no failures.
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_gui_lane_contract_acceptance --test stock_etf_lane_scoped_ipc_acceptance`: `17 passed`.
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`: `35` unit/golden + `174` integration/acceptance + `0` doc-tests passed.
- `git diff --check`: PASS.

## Dispatch Note

PA/E1/E2/E4/QA subagents were not spawned because this Codex desktop session does not expose a repo subagent execution tool. PM performed the narrow source-only implementation, local review, and focused regression directly.

## Boundary

No IBKR API call, healthcheck, secret slot access/creation, connector runtime, evidence clock, scorecard writer, scorecard DB apply, paper-shadow launch, paper account snapshot, paper order, cancel/replace, fill import, lifecycle writer, GUI lane selector authority, Phase 2 start, Phase 3 start, Phase 5 start, tiny-live/live permission, or Bybit live execution behavior change. Linux `trade-core` source was not synced, restarted, or fast-forwarded.
