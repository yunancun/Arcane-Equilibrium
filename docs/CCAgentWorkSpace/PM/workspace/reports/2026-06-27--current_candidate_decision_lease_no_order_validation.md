# Current Candidate Decision Lease No-Order Validation

## Status

`DONE_WITH_CONCERNS`

We validated the current-candidate Decision Lease IPC/Rust SM path for `grid_trading|AVAXUSDT|Sell` without admitting an order. The validation lease was acquired and immediately released; it is not an active lease and cannot clear runtime admission.

## Source / Runtime

- Source/runtime head: `0122e83d0851ca3d64ad86a35e812c71e0ba7ccc`
- Helper: `helper_scripts/research/cost_gate_learning_lane/current_candidate_decision_lease_no_order_validation.py`
- Runtime sync manifest: `/tmp/openclaw/runtime_source_sync_decision_lease_no_order_validation_20260627T055338Z/runtime_sync_manifest.json`
- Runtime sync manifest sha: `13b7fd265c515ea9872f27d393514ecfa52884c4b348c8b733cab7d24df0a291`
- Runtime tests: `17 passed`
- API/watchdog PIDs stayed `3727506` / `1538268`; no service restart.

## Evidence

- Input gate packet: `/tmp/openclaw/current_candidate_proposed_sizing_decision_lease_guardian_gate_20260627T053314Z/current_candidate_proposed_sizing_decision_lease_guardian_gate_evidence.json`
- Input gate packet sha: `f404626f6ecea7e028160ed17739d9c4d0e0d818acb59ef88cf5980297e0903f`
- Input sizing proposal: `/tmp/openclaw/current_candidate_guardian_adjusted_sizing_proposal_20260627T053254Z/current_candidate_guardian_adjusted_sizing_proposal.json`
- Input sizing proposal sha: `cd44795d4510e3c04ff4b273505825893308ca6089bf8a17f87b85ea323086bc`
- Lease validation artifact: `/tmp/openclaw/current_candidate_decision_lease_no_order_validation_20260627T055522Z/current_candidate_decision_lease_no_order_validation.json`
- Lease validation sha: `c073cd4fbec9e19d2770226310d39cb91245141e8c3e598e4377f4490be59b11`
- Post-validation governance snapshot: `/tmp/openclaw/post_lease_validation_runtime_governance_snapshot_20260627T055540Z/runtime_governance_snapshot.json`
- Post-validation snapshot sha: `a7022cb1ca758b762d24a5855f6a4af67821a956bc4b95c273a248b815304a70`
- Session state: `/tmp/openclaw/session_loop_state_20260627T055600Z_decision_lease_no_order_validation/session_loop_state.json`
- Session state sha: `012eea209141eef497c9a42763778f35ba25179dff550b3d852edf52ff19e0ad`

## Result

- GUI/Rust cap lineage preserved: GUI `10.0%` is `per_trade_risk_pct=0.1`, GUI max-single-position `25%` becomes `2388.10856564 USDT`.
- Effective single-order cap remains `668.67039838 USDT`.
- Proposed no-order shape remains `102.0 AVAX / 668.304 USDT`.
- First runtime mutating attempt without IPC secret failed before acquire with engine `first message must be __auth`.
- Rerun with `OPENCLAW_IPC_SECRET_FILE=/home/ncyu/BybitOpenClaw/secrets/environment_files/ipc_secret.txt` succeeded.
- Lease `lease:e2675fc4b8b1` was acquired and immediately released with outcome `Failed`.
- Post-validation `governance.get_status` reports `lease_live_count=0`.
- Post-validation `governance.list_leases` is empty.
- Guardian remains `CAUTIOUS`; `position_size_multiplier=0.7`.

## Boundary

No Bybit call, order/cancel/modify, PG write, runtime config/env/service mutation, Cost Gate lowering, risk expansion, live/mainnet authority, execution, or profit proof occurred.

## Next

Do not use this released lease to clear runtime admission. Next no-order work should diagnose or wait for Guardian `CAUTIOUS` / reconciler drift to resolve, then obtain a fresh active current-candidate Demo Decision Lease plus Guardian `NORMAL` or valid proposed-sizing gate before refreshing actual-admission BBO.
