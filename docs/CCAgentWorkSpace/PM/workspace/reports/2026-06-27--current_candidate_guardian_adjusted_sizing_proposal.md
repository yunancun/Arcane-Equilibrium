# Current Candidate Guardian-Adjusted Sizing Proposal

## Status

`DONE_WITH_CONCERNS`.

This checkpoint implements and deploys a no-order reduced sizing proposal for the current AVAX candidate under the Guardian-adjusted cap. It does not clear runtime admission or grant order authority.

## Operator Correction Applied

All risk parameters must follow GUI/Rust RiskConfig.

- GUI `P1 Risk/Trade=10.0%` maps to Rust `per_trade_risk_pct=0.1`, not `10 USDT`.
- GUI `Max Single Position=25%` maps to Rust `position_size_max_pct=25.0`.
- The current accepted Demo equity is `9552.43426257`, so the GUI per-order cap is `955.24342626 USDT`.
- The max-single-position budget is `2388.10856564 USDT`; it is a GUI percentage-derived exposure budget, not a fixed local cap.

## What Changed

- Added `helper_scripts/research/cost_gate_learning_lane/current_candidate_guardian_adjusted_sizing_proposal.py`.
- Added focused tests in `helper_scripts/research/tests/test_current_candidate_guardian_adjusted_sizing_proposal.py`.
- Updated `helper_scripts/SCRIPT_INDEX.md`.
- Runtime source fast-forwarded to `b51f7602192b5f312c231ddbb0e16a34112746b7`.
- Crontab expected-head pins replaced `fed85508ad10d46c1f4962199b66e7076cf6377d` with `b51f7602192b5f312c231ddbb0e16a34112746b7` in `11` locations.

The helper revalidates GUI cap lineage before producing any proposal:

- `cap_source == current_candidate_envelope.cap_resolution.resolved_cap_usdt`
- `per_trade_risk_pct_fraction <= 1`
- `per_trade_risk_pct_fraction * 100 == per_trade_risk_pct_display`
- local/bounded `10 USDT` authority flags are false
- admission, Guardian, and construction GUI caps match
- Guardian-adjusted cap does not exceed GUI cap

## Evidence

- Runtime GUI RiskConfig read-only artifact: `/tmp/openclaw/demo_risk_config_gui_limits_readonly_20260627T051018Z/demo_risk_config_gui_limits_readonly.json`
- Runtime GUI RiskConfig sha256: `3316ef7f8029c44e1f6af5c6b5df393304cbd47f18cbd9d770cadcd2db2fe4be`
- Runtime sync manifest: `/tmp/openclaw/runtime_source_sync_guardian_adjusted_sizing_proposal_20260627T051212Z/runtime_sync_manifest.json`
- Runtime sync manifest sha256: `c7668d090fedf0ce3d6a59c763f0daabe98dd1d62be02de82b4aba9951027c1f`
- Proposal JSON: `/tmp/openclaw/current_candidate_guardian_adjusted_sizing_proposal_20260627T051233Z/current_candidate_guardian_adjusted_sizing_proposal.json`
- Proposal JSON sha256: `6fb60dfab8967209910aa8ffa34148abe9a24ac0b6b18cf954f63b12692d1a29`
- Proposal Markdown: `/tmp/openclaw/current_candidate_guardian_adjusted_sizing_proposal_20260627T051233Z/current_candidate_guardian_adjusted_sizing_proposal.md`
- Proposal Markdown sha256: `f4363814a3e860ebf70303054f99773957b43fa628359c5c8d5873ae33ab2b60`
- Session state: `/tmp/openclaw/session_loop_state_20260627T051329Z_guardian_adjusted_sizing_proposal.json`
- Session state sha256: `3081575e5892fa5002bacda99daa2f8f907b99508d7a7a51734676fbfbb90cfe`

## Proposal

- Candidate: `grid_trading|AVAXUSDT|Sell`
- GUI cap: `955.24342626 USDT`
- Guardian risk level: `CAUTIOUS`
- Guardian multiplier: `0.7`
- Guardian-adjusted cap: `668.67039838 USDT`
- Original order shape: `145.7 AVAX / 954.6264 USDT`
- Proposed reduced shape: `102.0 AVAX / 668.304 USDT`
- Proposal status: `CURRENT_CANDIDATE_GUARDIAN_ADJUSTED_SIZING_PROPOSAL_READY_NO_ORDER`

## Verification

- Local focused tests: `30 passed`
- Runtime focused tests after sync: `18 passed`
- `py_compile`: passed locally and on runtime
- `git diff --check`: passed
- Runtime source clean at `b51f7602192b5f312c231ddbb0e16a34112746b7`

## Boundary

No Decision Lease acquire/release, no Guardian/Rust authority grant, no fresh actual-admission BBO, no order/cancel/modify, no PG write, no service restart, no writer/adapter enablement, no Cost Gate lowering, no risk expansion, no live/mainnet authority, no execution, and no profit proof occurred.

## Next Action

Do not repeat this proposal unless candidate, risk state, lease state, GUI cap/equity lineage, or order shape changes. Next no-order work should validate a real current-candidate Demo Decision Lease and produce Guardian gate evidence for the proposed reduced sizing. Fresh actual-admission BBO remains after those gates pass.
