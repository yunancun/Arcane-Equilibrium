# Current Candidate Decision Lease / Guardian Gate Evidence

## Status

`BLOCKED_BY_LOSS_CONTROL`.

This checkpoint implemented and deployed machine-checkable no-order evidence for the current AVAX bounded Demo admission gates. It did not clear runtime admission.

## What Changed

- Added `helper_scripts/research/cost_gate_learning_lane/current_candidate_decision_lease_guardian_gate_evidence.py`.
- Hardened `current_candidate_bounded_demo_admission_envelope_review.py` so generic hand-written `ACTIVE` lease or `PASS` guardian JSON cannot clear admission gates.
- Admission now accepts only:
  - `current_candidate_decision_lease_gate_evidence_v1`
  - `current_candidate_guardian_risk_gate_evidence_v1`
  - source `runtime_governance_ipc_readonly_snapshot`
- Runtime source was fast-forwarded to `fed85508ad10d46c1f4962199b66e7076cf6377d`.
- Crontab expected-head pins were replaced from `2a7bfa5b603052638d35a20acf0516da752ca0db` to `fed85508ad10d46c1f4962199b66e7076cf6377d` (`11` replacements).

## Evidence

- Final packet: `/tmp/openclaw/current_candidate_decision_lease_guardian_gate_evidence_20260627T045251Z/current_candidate_decision_lease_guardian_gate_evidence.json`
- Packet sha256: `d5643f440a575fbeef1b95aa542ecdd9eace1b11428620c4e54ef700a3af0896`
- Decision gate sha256: `5cdd135f41131dfd83d83c2aa3beefd201a441248aae17d5016f36d813b4338f`
- Guardian gate sha256: `32abf563b8a6a23f2c9e0d437bcc18fdfe760b995f843b47bc0935e58ec94801`
- Runtime governance snapshot sha256: `4e18e332abd69fa16f926ae835e635eb7048537956023ab457d5f5405c64a716`
- Runtime sync manifest: `/tmp/openclaw/runtime_source_sync_decision_lease_guardian_gate_20260627T045116Z/runtime_sync_manifest.json`
- Runtime sync manifest sha256: `dcbbfa81c4038adceab7cbeae6f0759d77aa6f981db5bc91929e4f58842995ab`
- Session state: `/tmp/openclaw/session_loop_state_20260627T045251Z_decision_lease_guardian_gate_evidence.json`
- Session state sha256: `2f950c97708d86d30c4ab9c4d7230e99653e737d1a5976a7e0ff93a1d88084e1`

## Runtime Finding

- Current candidate: `grid_trading|AVAXUSDT|Sell`
- GUI/Rust/equity cap: `955.24342626 USDT`
- Current rounded notional: `954.6264 USDT`
- Runtime lease live count: `0`
- Guardian risk level: `CAUTIOUS`
- Guardian `position_size_multiplier`: `0.7`
- Guardian-adjusted cap: `668.6703983819999 USDT`

Result: Decision Lease is not valid, and Guardian gate is not valid because the current rounded notional exceeds the Guardian-adjusted cap.

## Verification

- Local focused tests: `12 passed`
- Local `py_compile`: passed
- Runtime focused tests after sync: `12 passed`
- Runtime `py_compile`: passed
- Runtime source clean at `fed85508ad10d46c1f4962199b66e7076cf6377d`
- `openclaw-trading-api.service`: active/running PID `3727506`
- `openclaw-watchdog.service`: active/running PID `1538268`

## Boundary

No Decision Lease acquire/release, no Guardian/Rust authority grant, no fresh BBO admission, no order/cancel/modify, no PG write, no service restart, no writer/adapter enablement, no Cost Gate lowering, no risk expansion, no live/mainnet authority, no execution, and no profit proof occurred.

## Next Action

Do not repeat this evidence generation unless candidate, risk state, lease state, or order shape changes. Next no-order work should produce a reviewed reduced order shape or parameter proposal under the Guardian-adjusted cap, or verify Guardian has returned to `NORMAL`; then validate a real current-candidate Demo Decision Lease before any fresh actual-admission BBO step.
