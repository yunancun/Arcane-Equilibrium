# Current Candidate GUI-Derived Proposed-Sizing Gate Evidence

## Status

`BLOCKED_BY_LOSS_CONTROL`.

This checkpoint enforces the operator correction that all risk parameters come from GUI-backed Rust RiskConfig, not a naked `cap_usdt=10`. GUI `P1 Risk/Trade=10.0%` maps to `per_trade_risk_pct=0.1`; GUI `Max Single Position=25%` maps to a max-single-position budget of `2388.10856564 USDT` from accepted Demo equity `9552.43426257`.

## What Changed

- Source commit `04054ac60e685e21eb991a4b2e165a244ce36839` requires Guardian-adjusted sizing proposals to carry GUI per-trade cap, GUI max-single-position budget, and `effective_single_order_cap_usdt`.
- Effective single-order cap is now `min(gui_per_trade_cap_usdt, gui_max_single_position_budget_usdt, guardian_adjusted_cap_usdt)`.
- Admission review now rejects Guardian gate evidence whose rounded notional does not match the admission order shape, preventing reduced-sizing evidence from clearing a stale larger order.
- Runtime `trade-core` fast-forwarded `b51f7602192b5f312c231ddbb0e16a34112746b7 -> 04054ac60e685e21eb991a4b2e165a244ce36839`; crontab expected-head pins replaced old `b51f7602` occurrences `11 -> 0`, new `04054ac6` occurrences `0 -> 11`.
- No service restart occurred; `openclaw-trading-api.service` PID stayed `3727506`, watchdog PID stayed `1538268`.

## Evidence

- Runtime sync manifest: `/tmp/openclaw/runtime_source_sync_proposed_sizing_gate_evidence_20260627T053113Z/runtime_sync_manifest.json`
- Runtime sync manifest sha256: `5fc00925c3685f15946496f2e524ac0ee5c36ad5ca51d4525e16342f382bbded`
- Fresh runtime governance snapshot: `/tmp/openclaw/proposed_sizing_runtime_governance_snapshot_20260627T053225Z/runtime_governance_snapshot.json`
- Snapshot sha256: `ab7a3e387f59e54d808ada1092ad7dcab5c554edd994ec3d418681a01ef23d32`
- New GUI-derived sizing proposal: `/tmp/openclaw/current_candidate_guardian_adjusted_sizing_proposal_20260627T053254Z/current_candidate_guardian_adjusted_sizing_proposal.json`
- Proposal sha256: `cd44795d4510e3c04ff4b273505825893308ca6089bf8a17f87b85ea323086bc`
- Final gate packet: `/tmp/openclaw/current_candidate_proposed_sizing_decision_lease_guardian_gate_20260627T053314Z/current_candidate_proposed_sizing_decision_lease_guardian_gate_evidence.json`
- Packet sha256: `f404626f6ecea7e028160ed17739d9c4d0e0d818acb59ef88cf5980297e0903f`
- Decision gate sha256: `e50c65e77f9ed95aaf96ddb6a8559c2cdc5a69cc222b7e0fe87abfa6f302a8be`
- Guardian gate sha256: `8152094bcd0ac3670f89ff6845abaa1e2a642cdb4167357a46f933287b1a57c3`
- Session state: `/tmp/openclaw/session_loop_state_20260627T053455Z_gui_derived_proposed_sizing_gate_evidence.json`
- Session state sha256: `22795c0bffefcdddf0af83ab85cea2072021cbb52684cc5ce74daea086371490`

## Runtime Finding

- Candidate: `grid_trading|AVAXUSDT|Sell`
- GUI per-trade cap: `955.24342626 USDT`
- GUI max-single-position budget: `2388.10856564 USDT`
- Guardian risk level: `CAUTIOUS`
- Guardian multiplier: `0.7`
- Guardian-adjusted / effective cap: `668.67039838 USDT`
- Proposed shape: `102.0 AVAX / 668.304 USDT`
- Guardian notional breach: removed for proposed sizing
- Remaining Decision Lease blockers: `current_candidate_active_demo_decision_lease_missing`, `decision_lease_missing`, `lease_live_count_zero`
- Remaining Guardian blocker: `guardian_risk_state_not_normal`

## Verification

- Local focused tests: `21 passed`
- Runtime focused tests after sync: `21 passed`
- `py_compile`: passed locally and on runtime
- `git diff --check`: passed before source commit
- Runtime source clean at `04054ac60e685e21eb991a4b2e165a244ce36839`

## Boundary

No Decision Lease acquire/release, no Guardian/Rust authority grant, no fresh actual-admission BBO, no order/cancel/modify, no PG write, no service restart, no writer/adapter enablement, no Cost Gate lowering, no risk expansion, no live/mainnet authority, no execution, and no profit proof occurred.

## Next Action

Do not repeat this proposal/gate evidence unless candidate, GUI RiskConfig/equity, Guardian state/multiplier, Decision Lease state, or order shape changes. Next no-order step is to obtain/validate a real current-candidate Demo Decision Lease and Guardian `NORMAL`/valid proposed-sizing gate before any fresh actual-admission BBO. The reduced Guardian gate cannot clear the old larger admission order shape.
