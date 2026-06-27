# Current Candidate Decision Lease / Guardian Gate Evidence

狀態：`BLOCKED_BY_LOSS_CONTROL`。

本輪已把 Decision Lease / Guardian gate 變成可機器檢查的 runtime IPC evidence。重點不是放行，而是明確證明現在不能放行：

- GUI 10% 風控 cap 仍是 `955.24342626 USDT`，不是 `10 USDT`。
- Runtime 沒有 active current-candidate Demo Decision Lease：`lease_live_count=0`。
- Guardian 目前是 `CAUTIOUS`，`position_size_multiplier=0.7`。
- 因此 Guardian-adjusted cap 是 `668.6703983819999 USDT`。
- 現有候選單筆 rounded notional 是 `954.6264 USDT`，超過 Guardian-adjusted cap。

最終 evidence：

- `/tmp/openclaw/current_candidate_decision_lease_guardian_gate_evidence_20260627T045251Z/current_candidate_decision_lease_guardian_gate_evidence.json`
- sha256 `d5643f440a575fbeef1b95aa542ecdd9eace1b11428620c4e54ef700a3af0896`

Source/runtime 已同步到 `fed85508ad10d46c1f4962199b66e7076cf6377d`，crontab expected-head pins 也已更新；API PID `3727506` 和 watchdog PID `1538268` 沒有重啟。

下一步不是 fresh BBO 或下單，而是先做 no-order sizing/parameter adjustment，讓 order shape 落在 Guardian-adjusted cap 內，或等待並驗證 Guardian 回到 `NORMAL`；之後才可在 reviewed scope 內取得/驗證真實 Decision Lease。
