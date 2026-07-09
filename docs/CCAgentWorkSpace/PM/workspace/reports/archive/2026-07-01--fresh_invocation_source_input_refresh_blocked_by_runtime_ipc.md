# Fresh Invocation Source-Input Refresh Blocked By Runtime IPC

## Summary

PM advanced `P0-CURRENT-CANDIDATE-FRESH-INVOCATION-WINDOW-SOURCE-INPUT-REFRESH-GATE` for current candidate `grid_trading|ETHUSDT|Buy` and produced fresh no-order source inputs:

- Session loop state: `/tmp/openclaw/session_loop_state_20260630T225427Z_fresh_invocation_source_input_refresh/session_loop_state.json`, sha `ca616b86b252bac4cdfdfcc99402be9706d7834815be48848be36a5bbe06be76`.
- Accepted Demo equity: `/tmp/openclaw/fresh_invocation_source_input_refresh_20260630T2254Z/equity/demo_account_equity_artifact_tailscale_runtime_only.json`, sha `b807478957cce36ca270b9dec6bc8f33f31c2c01ba8bdaa16bf9636a3a8d9892`, status `DEMO_FAST_BALANCE_EQUITY_ARTIFACT_READY_NO_AUTHORITY`.
- No-authority envelope: `/tmp/openclaw/fresh_invocation_source_input_refresh_20260630T2254Z/envelope/current_candidate_no_order_refresh_envelope_noauth_ready.json`, sha `5e1a7102dd23d203b1162f876d3da2ee0becd8f0ccfbc896c1e1ce2aa4604a65`, status `CURRENT_CANDIDATE_NO_ORDER_REFRESH_ENVELOPE_READY_NO_CAPTURE_NO_AUTHORITY`.
- E3/BB-reviewed public quote/construction: `/tmp/openclaw/fresh_invocation_source_input_refresh_20260630T2254Z/quote/current_candidate_public_quote_construction_refresh.json`, sha `523dd1ac711f2f03798d289aa461312df9ad512b1addeca39aa6ad9925f6c9ba`, status `CURRENT_CANDIDATE_PUBLIC_QUOTE_CONSTRUCTION_REFRESH_READY_NO_ORDER`.
- Guardian-adjusted sizing: `/tmp/openclaw/fresh_invocation_source_input_refresh_20260630T2254Z/sizing/current_candidate_guardian_adjusted_sizing_proposal_ready.json`, sha `65fed2d356c1841baa99aa4b43077e80abef6922de07691e68e75d39cf585745`, status `CURRENT_CANDIDATE_GUARDIAN_ADJUSTED_SIZING_PROPOSAL_READY_NO_ORDER`.

## Blocker

E3 approved one exact read-only governance IPC snapshot command. The helper failed closed:

- Snapshot: `/tmp/openclaw/fresh_invocation_source_input_refresh_20260630T2254Z/governance/runtime_governance_snapshot.json`
- Sha: `8a9e85db5550d18b0a3c3cf887f2202f095e6c2e4a33ba7cf3026ee4c2634db3`
- Status: `RUNTIME_GOVERNANCE_IPC_READONLY_SNAPSHOT_BLOCKED_BY_RUNTIME`
- Runtime blockers: `governance.get_status_not_ok`, `governance.list_leases_not_ok`, `governance.get_risk_state_not_ok`
- Stderr symptom: `Response ID mismatch: expected=1 got=None`

The downstream gate packet was therefore generated as machine-checkable blocked evidence:

- Gate packet: `/tmp/openclaw/fresh_invocation_source_input_refresh_20260630T2254Z/gate/current_candidate_decision_lease_guardian_gate_evidence_with_sizing_blocked_by_runtime_snapshot.json`
- Sha: `1add6236ced9922f92b489fd7a3983d60d9a60b834b47edf18aa19e5f3e29c49`
- Status: `CURRENT_CANDIDATE_DECISION_LEASE_GUARDIAN_GATE_BLOCKED_BY_LOSS_CONTROL`

## Boundary

No order, lease acquire/release, private endpoint, PG access, runtime mutation, service restart, Cost Gate change, live/mainnet, fill/PnL, or profit proof occurred. Public Bybit activity was limited to the E3/BB-approved Demo market-data GETs.

## Next

State transition: `BLOCKED_BY_RUNTIME`.

Next blocker: `P0-RUNTIME-GOVERNANCE-IPC-READONLY-SNAPSHOT-REPAIR`. Diagnose and repair the read-only IPC response/auth contract, then rerun governance snapshot under reviewed scope, rebuild the sizing-aware gate, and rerun the corrected dry-run before any active lease/BBO `--run`.
