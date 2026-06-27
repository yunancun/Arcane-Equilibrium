# Current Candidate Guardian Reconciler Drift Diagnosis

## Status

`BLOCKED_BY_LOSS_CONTROL`

已把 current-candidate `grid_trading|AVAXUSDT|Sell` 的 Guardian / reconciler drift 狀態落成可機器檢查的 no-order diagnosis artifact。GUI cap lineage 正確；runtime admission 仍被 loss-control 擋住。

## Source / Runtime

- Source/runtime head: `d0c04983170a3dfd07b365168e4a31a66c38e510`
- Helper: `helper_scripts/research/cost_gate_learning_lane/current_candidate_guardian_reconciler_drift_diagnosis.py`
- Runtime sync manifest: `/tmp/openclaw/runtime_source_sync_guardian_reconciler_drift_diagnosis_20260627T061746Z/runtime_sync_manifest.json`
- Runtime sync manifest sha: `7c0fa5605dea272289894c9a5323d79cfdd750f1d685dd5d2f43033fa76204a7`
- Runtime tests: `22 passed`
- API/watchdog PIDs stayed `3727506` / `1538268`; no service restart.

## Evidence

- Input proposed-sizing gate packet: `/tmp/openclaw/current_candidate_proposed_sizing_decision_lease_guardian_gate_20260627T053314Z/current_candidate_proposed_sizing_decision_lease_guardian_gate_evidence.json`
- Runtime governance snapshot: `/tmp/openclaw/current_candidate_guardian_reconciler_drift_diagnosis_20260627T061645Z/runtime_governance_snapshot.json`
- Runtime governance snapshot sha: `4d6a60440eeb010fa87fc13c60582bac5ad2243d0c52ad98859fcd3ad4cd8d71`
- Diagnosis artifact: `/tmp/openclaw/current_candidate_guardian_reconciler_drift_diagnosis_20260627T061645Z/current_candidate_guardian_reconciler_drift_diagnosis.json`
- Diagnosis sha: `0d4757bacb87f3bfad94ba97928b40e62f872a3ff841900e49ef5650821eaab8`
- Session state: `/tmp/openclaw/session_loop_state_20260627T061746Z_guardian_reconciler_drift_diagnosis/session_loop_state.json`
- Session state sha: `55f4a4d13b0f8146d7824917ffffe150237ee02365461b326a8fa36a7642508c`

## Result

- GUI `P1 Risk/Trade=10.0%` remains `per_trade_risk_pct=0.1`, not `10 USDT`.
- Accepted Demo equity `9552.43426257` resolves GUI per-trade cap to `955.24342626 USDT`.
- GUI `Max Single Position=25%` resolves to `2388.10856564 USDT`.
- Effective single-order cap remains `668.67039838 USDT`.
- Proposed no-order shape remains `102.0 AVAX / 668.304 USDT`.
- Source blockers: none.
- Authority contamination: none.
- Runtime blockers: `active_decision_lease_missing`, `lease_live_count_zero`, `guardian_risk_state_not_normal`, `position_size_multiplier_below_one`, `guardian_reconciler_drift_active`, `guardian_reconciler_drift_tail_present`, `reconciler_drift_after_recovery`.
- Runtime `governance.get_status`: Guardian `Cautious`, `lease_live_count=0`, `oms_active_count=0`.
- Runtime `governance.get_risk_state`: `CAUTIOUS`, `position_size_multiplier=0.7`, held about `100030244ms`.
- Transition tail latest reconciler event is `reconciler_drift`, after `reconciler_recovery`.

## Verification

- Local focused/adjacent tests: `22 passed`
- Runtime focused/adjacent tests: `22 passed`
- `py_compile` passed locally and on runtime.
- Runtime source and crontab expected-head pins synced to `d0c04983170a3dfd07b365168e4a31a66c38e510`.

## Boundary

No `_latest` overwrite, Decision Lease acquire/release, BBO refresh, Bybit call, order/cancel/modify, PG write, runtime config/env/service mutation, service restart, writer/adapter enablement, Cost Gate lowering, risk expansion, live/mainnet authority, execution, or profit proof occurred.

## Next

Do not repeat this diagnosis unless Guardian state/multiplier, transition tail, Decision Lease state, candidate, GUI RiskConfig/equity, or proposed order shape changes. Next admissible progress requires fresh read-only runtime governance evidence showing Guardian `NORMAL` and no active reconciler drift tail, then a fresh active current-candidate Demo Decision Lease plus valid proposed-sizing gate before actual-admission BBO.
