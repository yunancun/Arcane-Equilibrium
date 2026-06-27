# Actual Admission BBO Runtime Blocked

Status: `BLOCKED_BY_RUNTIME`

This round preserved the operator correction: GUI/Rust RiskConfig is the risk source of truth. GUI `P1 Risk/Trade=10.0%` is `per_trade_risk_pct=0.1`, not a fixed `10 USDT` order cap. GUI `Max Single Position=25%` is an exposure budget derived from accepted Demo equity.

Source delta:

- Commit `64d2c5c6` adds pre-lease admission-review GUI cap lineage validation to `current_candidate_actual_admission_bbo_lease_window.py`.
- A stale admission review with `per_order_cap_usdt=10.0` now blocks before Decision Lease acquire or public quote network calls when the current envelope/gate cap is GUI-derived.

Verification:

- Focused actual-admission helper test: `6 passed`.
- Focused GUI cap/admission/sizing/lease-window suite: `58 passed`.
- `py_compile` passed for the touched helper and test.

Runtime blocker:

- Latest correct-data-dir equity retry: `/tmp/openclaw/current_candidate_actual_bbo_fresh_equity_datadir_20260627T084723Z/demo_account_equity_artifact.json`
- File sha256: `5df49e017fa821fa9a22f57733f1cd9e7b26ae261f57fb4451715ea104329665`
- Status: `DEMO_FAST_BALANCE_EQUITY_ARTIFACT_NOT_READY_NO_AUTHORITY`
- Control API returned `pipeline_status=disconnected`, `read_model=null`, `balance=null`.
- Runtime snapshots under `/Users/ncyu/.openclaw_runtime/` are stale (`pipeline_snapshot_demo.json` mtime `2026-04-21T00:12:06Z`).

Session state:

- `/tmp/openclaw/session_loop_state_20260627T085113Z_actual_admission_bbo_runtime_blocked/session_loop_state.json`
- sha256 `bbbb8c5f469bac1a69ba34843a5091ebf97e3527033a61357ab849be545a8c69`

No order, cancel, modify, Bybit private call, PG write, Cost Gate change, risk expansion, live/mainnet authority, promotion proof, or profit proof occurred.
