# Current Candidate Active Decision Lease Gate Window

Date: 2026-06-27

Status: `BLOCKED_BY_LOSS_CONTROL`

## Summary

Implemented and deployed a bounded no-order active Decision Lease gate-window helper for the current AVAX Sell candidate. The helper keeps GUI/Rust RiskConfig as the source of truth, opens a short Demo `TRADE_ENTRY` lease only with explicit runtime opt-in, evaluates Decision Lease / Guardian gates while the lease is live, and releases the lease before the artifact is finalized.

The active Decision Lease gate now passes during the bounded window, but runtime admission remains blocked by Guardian `CAUTIOUS` (`guardian_risk_state_not_normal`). No order authority, execution, live/mainnet authority, Cost Gate lowering, or profit proof was produced.

## Source And Runtime

- Source commits:
  - `2d381e9e75a088e097fe6b28d8a84c16f8bcde3d` (`Add active lease gate window helper`)
  - `efa92a88886f1d353d4e4baf82491cfacea1887f` (`Fix active gate runtime IPC reads`)
- Runtime source: `efa92a88886f1d353d4e4baf82491cfacea1887f`
- Runtime sync manifest: `/tmp/openclaw/runtime_source_sync_active_decision_lease_gate_window_fix_20260627T070541Z/runtime_sync_manifest.json`
- Runtime sync manifest sha256: `1803bc0d73c6717caf31b0b3c65a1a8ba6b48fa62b1f5583cd7375f51537258c`
- Crontab expected-head pins: old `2d381e9e75a088e097fe6b28d8a84c16f8bcde3d` count `0`, new `efa92a88886f1d353d4e4baf82491cfacea1887f` count `11`
- No engine/API/watchdog restart. Runtime PIDs remained engine `3795702`, API `3727506`, watchdog `1538268`.

## Verification

- Local focused tests: `14 passed`
- Runtime focused tests: `14 passed`
- Local `py_compile`: passed
- Local `git diff --check`: passed
- Runtime `governance.get_status` after run: `lease_live_count=0`, Guardian `Cautious`
- Runtime `governance.list_leases` after run: empty
- Session state: `/tmp/openclaw/session_loop_state_20260627T070600Z_current_candidate_active_decision_lease_gate_window/session_loop_state.json`
- Session state sha256: `487d9c33ae857092a0fc1d32840aab6a60ce1caa074c9f938d6b51aeb99106f1`

## Runtime Artifacts

- Active-window artifact: `/tmp/openclaw/current_candidate_active_decision_lease_gate_window_20260627T070600Z/current_candidate_active_decision_lease_gate_window.json`
- Active-window artifact sha256: `dfcf9152f78ed2b6f1370ebc73b7e5a9cfa6d041941df952279525f239e296a0`
- Active-window nested gate evidence: `/tmp/openclaw/current_candidate_active_decision_lease_gate_window_20260627T070600Z/active_window_gate_evidence.json`
- Active-window nested gate evidence sha256: `de3f1a21e1c7efee9d2279e7d08a2a6b960d0cbfa97b07bc85a8db1d2139df63`
- Active runtime snapshot sha256: `76a40ec18fd5757b7fedebc0dc6094af4815b3162a0fa1b0eedb23d510b67311`
- Post-run governance snapshot: `/tmp/openclaw/current_candidate_active_decision_lease_gate_window_20260627T070600Z/post_run_governance_snapshot.json`
- Post-run governance snapshot sha256: `973da8c9e9a24e3987c76fbafaba72eac58f9a5c5533bd0a01d6c5468fdef0d2`

## Risk Semantics

- GUI `P1 Risk/Trade=10.0%` maps to `per_trade_risk_pct=0.1`, not `10 USDT`.
- Accepted Demo equity remains `9552.43426257`.
- GUI per-trade cap is `955.24342626 USDT`.
- GUI max-single-position budget is `2388.10856564 USDT`.
- Effective single-order cap in the current proposed sizing remains `668.67039838 USDT`, the min of GUI per-trade cap, GUI max-single-position budget, and Guardian-adjusted cap.

## Gate Result

- Acquired lease: `lease:caa9dcc3fac8`
- Release outcome: `Failed` release, `release_ok=true`
- Decision Lease gate during active window: valid for `grid_trading|AVAXUSDT|Sell`
- Guardian gate: blocked by `guardian_risk_state_not_normal`
- Overall status: `CURRENT_CANDIDATE_ACTIVE_DECISION_LEASE_GATE_WINDOW_BLOCKED_BY_LOSS_CONTROL`
- Post-run lease state: `lease_live_count=0`, `list_leases=[]`

## Boundary

No order, cancel, modify, Bybit private/order call, PG write, runtime config/env/service mutation, Cost Gate lowering, risk expansion, writer/adapter enablement, live/mainnet authority, execution, or profit proof occurred. The bounded active lease is not persistent authority after release.

## Next Action

Do not repeat this active-window evidence while Guardian state is unchanged. Wait for or diagnose Guardian `CAUTIOUS` / `reconciler_drift`; after Guardian returns to a reviewed valid state, reacquire a fresh active lease and rerun gate evidence inside the final actual-admission BBO window.
