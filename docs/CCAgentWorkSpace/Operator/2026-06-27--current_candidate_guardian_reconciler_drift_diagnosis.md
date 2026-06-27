# Current Candidate Guardian Reconciler Drift Diagnosis

## 結論

`BLOCKED_BY_LOSS_CONTROL`

GUI 風控語意已被機器檢查鎖住：目前不是 `cap_usdt=10` 誤用問題。GUI `10.0%` 正確解析為 `955.24342626 USDT` per-trade cap，GUI `25%` max-single-position 正確解析為 `2388.10856564 USDT`，實際 single-order cap 是三者最小值 `668.67039838 USDT`。

runtime admission 仍不能進：Guardian 是 `CAUTIOUS`，latest reconciler event 是 `reconciler_drift`，且目前沒有 active current-candidate Demo Decision Lease。

## 產物

- Diagnosis: `/tmp/openclaw/current_candidate_guardian_reconciler_drift_diagnosis_20260627T061645Z/current_candidate_guardian_reconciler_drift_diagnosis.json`
- Diagnosis sha: `0d4757bacb87f3bfad94ba97928b40e62f872a3ff841900e49ef5650821eaab8`
- Runtime snapshot: `/tmp/openclaw/current_candidate_guardian_reconciler_drift_diagnosis_20260627T061645Z/runtime_governance_snapshot.json`
- Runtime snapshot sha: `4d6a60440eeb010fa87fc13c60582bac5ad2243d0c52ad98859fcd3ad4cd8d71`
- Session state: `/tmp/openclaw/session_loop_state_20260627T061746Z_guardian_reconciler_drift_diagnosis/session_loop_state.json`
- Session state: `BLOCKED_BY_LOSS_CONTROL`

## 驗證

- Local/runtime focused adjacent tests: `22 passed`
- Runtime source synced to `d0c04983170a3dfd07b365168e4a31a66c38e510`
- No service restart; API/watchdog PID stayed `3727506` / `1538268`

## 邊界

沒有 acquire/release Decision Lease、沒有刷新 BBO、沒有下單、沒有改風控、沒有降低 Cost Gate、沒有 live/mainnet、沒有 profit proof。

下一步只能等 fresh read-only governance snapshot 顯示 Guardian `NORMAL` 且沒有 active reconciler drift tail，再取得/驗證 fresh active Demo Decision Lease；之後才可刷新 actual-admission BBO。
