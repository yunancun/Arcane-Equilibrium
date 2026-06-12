# AEG-S3 Gate-B preflight locator

Code checkpoints:

- `44a30afa` (`[skip ci] Add Gate-B preflight locator`)
- `f4a58b3c` (`[skip ci] Tighten Gate-B preflight artifact validation`)

Completed:

- Added artifact-only `aeg_s3_gate_b_preflight`.
- It finds Gate-B, FND2, and regime artifacts, previews listing sample/PBO readiness, and outputs the full-chain command.
- It distinguishes runnable-but-not-promotable from blocked:
  - `READY_BUT_SAMPLE_BELOW_GATE`
  - `BLOCKED_PRECHECK_FAILED`
  - `PASS_READY_FOR_FULL_CHAIN`
- Mac and Linux focused regression: `58 passed` each.
- No CI, deploy, rebuild, restart, DB write, auth, risk, or trading path touched.

Linux smoke:

- explicit run: `aeg_s3_gate_b_preflight_explicit_final_20260612`
- auto run: `aeg_s3_gate_b_preflight_auto_final_20260612`
- both returned `READY_BUT_SAMPLE_BELOW_GATE`
- sample_count: `2`
- pbo_status: `produced_candidate_grid`
- recommended command generated

Interpretation:

- Fresh Gate-B 後，先跑 preflight；它會給出 full-chain command。
- 舊 run 仍不是 promotion evidence，原因是樣本只有 2。
- 真 gate 仍是 fresh 24h probe 取得 `>=30` matched observations，然後 E2/MIT/QC 審。
