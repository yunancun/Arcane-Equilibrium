# PM Checkpoint - IBKR Stock/ETF Scorecard Status Read-Only Surface

Date: 2026-06-30
Role: PM(default)
Scope: ADR-0048 `stock_etf_cash` Phase 4 display-only scorecard verdict status surface.

## Verdict

`DONE_WITH_CONCERNS_SOURCE_ONLY`

This checkpoint exposes scorecard-verdict posture to the Stock/ETF GUI through a read-only Rust IPC, authenticated FastAPI route, and static GUI panel. It does not start Phase 2 or Phase 3, contact IBKR, read/create secrets, start an evidence clock, run a scorecard writer, apply DB changes, route orders, or alter Bybit runtime behavior.

## Changes

- Rust IPC fixture:
  - Added `stock_etf.get_scorecard_status`.
  - Registered it in dispatch and method registry as read-only / `IpcSlotRequirement::None`.
  - Returns a blocked `phase3_scorecard_status_source_fixture` built from `stock_etf_scorecard_verdict_v1`.
  - Preserves `phase3_started=false`, `scorecard_writer_started=false`, `db_apply_performed=false`, `evidence_clock_started=false`, `paper_shadow_window_complete=false`, `live_or_tiny_live_authorized=false`, `ibkr_call_performed=false`, `secret_slot_touched=false`, `order_routed=false`, and `bybit_ipc_reused=false`.
- FastAPI:
  - Added authenticated no-store `GET /api/v1/stock-etf/scorecard-status`.
  - Calls only `stock_etf.get_scorecard_status` with empty params.
  - Ignores query/header supplied scorecard, Phase 3, live, and side-effect claims.
  - Fail-closes IPC unavailable/errors to `degraded` and converts real IPC payload drift, positive artifact/hash presence before writer, nonzero statistical/PnL fields, Phase 3 start, writer/DB/evidence-clock side effects, IBKR contact, secret access, order routing, and Bybit IPC reuse into `contract_violation_blocked`.
- GUI:
  - Added `Scorecard` summary metric and `Scorecard Verdict Status` panel to `tab-stock-etf.html`.
  - Renders contract id/source version, verdict label, artifact/hash/review posture, sample/window thresholds, PnL/cost/LCB fields, PSR/DSR fields, quality labels, side-effect flags, and blockers.
  - Uses only `ocApi(... method: 'GET' ...)`; no forms, direct `fetch`, browser storage authority, secret widgets, or order widgets.
- Contract:
  - `lane_scoped_ipc_v1` now includes `GetScorecardStatus` as display-only / non-effect-capable.
  - `gui_lane_contract_v1` now requires exact display-only GET `/api/v1/stock-etf/scorecard-status`.
  - Blocked GUI template was updated with the scorecard-status endpoint in disabled GET-only state.

## Verification

- `python3 -m py_compile` on touched Stock/ETF route, normalizer, fixture, route tests, and static guard: PASS.
- Rust format check on changed Rust files, with `lib.rs` checked using `skip_children=true` to avoid unrelated module traversal: PASS.
- Node inline script parser for `tab-stock-etf.html`: PASS.
- `python3 -m pytest` on all Stock/ETF route tests plus static no-write guard: `57 passed`.
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf`: `14 passed` in the targeted unit filter; remaining integration targets were filtered with 0 tests and no failures.
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`: `35` unit/golden + `206` integration/acceptance + `0` doc-tests passed.
- `git diff --check`: PASS.

## Dispatch Note

PA/E1/E2/E4/QA subagents were not spawned because this Codex desktop session does not expose a repo subagent execution tool. PM performed the narrow source-only implementation, local review, and focused regression directly.

## Boundary

No IBKR API call, healthcheck, secret slot access/creation, connector runtime, evidence clock, scorecard writer, scorecard DB apply, paper account snapshot, paper order, cancel/replace, fill import, lifecycle writer, GUI lane selector authority, Phase 2 start, Phase 3 start, tiny-live/live permission, or Bybit live execution behavior change. Linux `trade-core` source was not synced, restarted, or fast-forwarded.
