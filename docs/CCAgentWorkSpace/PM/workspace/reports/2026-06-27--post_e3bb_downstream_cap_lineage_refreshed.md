# Post-E3/BB Downstream Cap-Lineage Refreshed

- Date: 2026-06-27
- State transition: `DONE_WITH_CONCERNS`
- Candidate: `grid_trading|AVAXUSDT|Sell`
- Scope: runtime no-order artifact generation, read-only governance IPC, and dry-run only

## Result

The stale downstream cap-lineage blocker from v650 is cleared. GUI/Rust RiskConfig remains the risk source of truth:

- Demo equity: `9549.38926928 USDT`
- GUI P1 risk/trade: `10.0%` (`per_trade_risk_pct=0.1`)
- Per-trade/effective single-order cap: `954.93892693 USDT`
- GUI max single position: `25%`
- Max-single-position budget: `2387.34731732 USDT`
- Proposed order shape: `144.0 AVAX / 954.576 USDT`
- Local `10 USDT` authority: `false`

The final dry-run is `CURRENT_CANDIDATE_ACTUAL_ADMISSION_BBO_LEASE_WINDOW_DRY_RUN_READY`; source blockers and authority contamination are empty.

## Runtime Artifacts

- Fresh equity: `/tmp/openclaw/post_e3bb_downstream_lineage_refresh_20260627T1515Z/fresh_inputs/demo_account_equity_artifact.json`
  - sha256: `a064fb1f9681034bc01506e463db943c1ed307cfcbe87807e2986d804431002a`
- Fresh no-order envelope: `/tmp/openclaw/post_e3bb_downstream_lineage_refresh_20260627T1515Z/fresh_inputs/current_candidate_no_order_refresh_envelope.json`
  - sha256: `6abd74b84335771d1e205db915d9dae42694fc93ccc727b41fb414da7bdc6a88`
- Public quote / construction refresh: `/tmp/openclaw/post_e3bb_downstream_lineage_refresh_20260627T1515Z/public_quote_construction_refresh/current_candidate_public_quote_construction_refresh.json`
  - sha256: `27537a58b07b66e4b45355d6686af3ad08159a0b61b798798b43f8a705e51a6c`
- Admission review: `/tmp/openclaw/post_e3bb_downstream_lineage_refresh_20260627T1515Z/admission_review/current_candidate_bounded_demo_admission_envelope_review.json`
  - sha256: `0fad5441b5fb25612eee100f28fd896bd4d2454695c9e795d144d5fb35d2f205`
- Runtime governance snapshot: `/tmp/openclaw/post_e3bb_downstream_lineage_refresh_20260627T1515Z/runtime_governance_snapshot_after_sizing/runtime_governance_snapshot.json`
  - sha256: `dfb994d7f97983f77fb78db0a2458d080a77cc617d495f2a52eec0b84b678f92`
  - Guardian: `NORMAL`, multiplier `1.0`, lease counts `0/0`
- Guardian-adjusted sizing: `/tmp/openclaw/post_e3bb_downstream_lineage_refresh_20260627T1515Z/sizing/current_candidate_guardian_adjusted_sizing_proposal.json`
  - sha256: `a15b3cd118bd9374b0fa3edb02b0e2e8f042358abe44ebe7a81eb6aa242ebbf4`
- Sizing-aware Decision Lease / Guardian gate: `/tmp/openclaw/post_e3bb_downstream_lineage_refresh_20260627T1515Z/gate_with_sizing/current_candidate_decision_lease_guardian_gate_evidence.json`
  - sha256: `1eec35e17d46f65e6f67f237cf1085ed8abf8c580f6686cc3244a67551595e8c`
- Final dry-run: `/tmp/openclaw/post_e3bb_downstream_lineage_refresh_20260627T1515Z/final_window_dry_run/current_candidate_actual_admission_bbo_lease_window_dry_run.json`
  - sha256: `3781835ce67b88ead05197d68e922715567ac21733fd8d4e3c356e07ba3ad575`
- Session state: `/tmp/openclaw/session_loop_state_20260627T151500Z_downstream_cap_lineage_refresh/session_loop_state.json`
  - sha256: `8ffeeaaed4d0bcb8f6a4ceef84877a71002544567eff12b969c402df3224c6a9`

## Remaining Blockers

- Standing Demo authorization expired at `2026-06-27T15:31:18.539071+00:00`.
- No active current-candidate Demo Decision Lease exists.
- No actual-admission BBO was refreshed inside an active lease window.
- Runtime admission and order authority remain false.

## Boundary

E3 rejected the initial public quote helper run because the input envelope was too close to expiry, then accepted the same no-order public GET scope after a fresh envelope. BB approved the public GET shape with strict freshness and no-authority constraints.

No Decision Lease acquire/release, private Bybit call, order/cancel/modify, PG query/write, runtime mutation, service restart, Cost Gate lowering, risk expansion, writer/adapter enablement, live/mainnet authority, execution, fill, PnL, or profit proof occurred.

## Next

Per operator request, pause here and do not continue loop dispatch. On resume, first refresh or revalidate standing/auth evidence, then rerun fresh same-window Decision Lease, Guardian, Rust authority, actual BBO, GUI cap, book-clean, auditability, and reconstructability gates before any order-capable Demo invocation.
