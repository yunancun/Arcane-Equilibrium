# GUI Percent Risk Cap Semantics Runtime Sync

| Field | Value |
|---|---|
| `blocker_id` | `P0-GUI-RISK-CAP-RESOLVER-CURRENT-CANDIDATE-DRIFT-RECONCILE` |
| `state_transition` | `DONE_WITH_CONCERNS` |
| `session_loop_state` | `/tmp/openclaw/session_loop_state_20260627T042822Z_gui_percent_risk_cap_semantics_runtime_sync.json` |
| `session_loop_state_sha256` | `6468e1cd20170f0bf89aaea3c1bda16135aa2d0082d31616dd5984f3d571ef13` |
| `source_commit` | `2a7bfa5b603052638d35a20acf0516da752ca0db` |
| `runtime_head` | `2a7bfa5b603052638d35a20acf0516da752ca0db` |

## Decision

The operator correction is accepted and now enforced in source and runtime:

- GUI `P1 Risk/Trade=10.0%` is Rust `per_trade_risk_pct=0.1`, not `10 USDT`.
- GUI `P1 Risk/Trade=0.5%` is Rust `per_trade_risk_pct=0.005`.
- GUI `Max Single Position=25%` remains Rust `position_size_max_pct=25.0`.
- With accepted Demo equity `9552.43426257`, current reviewed per-order cap is `955.24342626 USDT`.

## Source Changes

- `risk_view_client.py` now treats GUI `p1_risk_pct` as percent-native for all numeric values.
- `bbo_freshness_colocated_runner.py` no longer injects a default `cap_usdt=10.0`; PG mode requires an explicit positive GUI/Rust-resolved cap.
- Stale helper/index wording that could imply a current `10 USDT` cap was replaced with GUI-resolved cap language.
- Regression tests cover GUI `10.0 -> 0.1`, GUI `0.5 -> 0.005`, fail-closed missing cap, and stale `10 USDT` authority text.

## Runtime Sync

- Runtime `trade-core` was fast-forwarded to `2a7bfa5b603052638d35a20acf0516da752ca0db`.
- Crontab expected-head pins were replaced from actual old full SHA `523bffa24f4856ac234d9d4ebd87eaf33f2b028b` to `2a7bfa5b...`: `11` replacements, `70` lines preserved.
- Correct service namespace is `systemctl --user`.
- `openclaw-trading-api.service` was restarted to PID `3727506`; watchdog remains PID `1538268`.
- A natural scheduled cost-gate cron process was observed after sync; PM did not manually run cron.

## Verification

Local:

- Risk view tests: `25 passed`.
- Live risk route tests: `8 passed`.
- Equity artifact tests: `9 passed`.
- False-negative gap + co-located runner tests: `19 passed`.
- Current-cap/current-candidate/admission tests: `31 passed`.
- Bounded auth/preflight/authority tests: `68 passed`.
- Combined risk view + live risk route tests: `33 passed`.
- `py_compile` and `git diff --check`: passed.

Runtime:

- Co-located runner + false-negative gap tests: `19 passed`.
- Risk view + live risk route tests: `33 passed`.
- Runtime mapping probe returned `10.0 -> 0.1`, `0.5 -> 0.005`, and `25.0` max single position preserved.

## Boundary

This checkpoint changed source, runtime source checkout, expected-head pins, and the user API service process only. It did not grant active probe/order authority and did not perform order/cancel/modify, adapter/writer enablement, plan mutation, Cost Gate lowering, risk expansion, live/mainnet action, or profit proof.

Runtime admission remains blocked by:

- `decision_lease_valid`
- `guardian_risk_gate_valid`
- `fresh_bbo_refresh_at_actual_admission`

## Next

Generate or implement no-order machine-checkable Decision Lease and Guardian risk gate evidence under the GUI/Rust-resolved cap. Keep fresh actual-admission BBO inside reviewed admission scope; do not execute until all admission gates, auditability, and reconstructability pass.
