# AEG-S3 Gate-B full matrix PBO readiness

Test checkpoint: `235858f4` (`[skip ci] Guard Gate-B matrix PBO path`)

Completed:

- Added a regression guard so the Gate-B full formal matrix path must carry listing_fade PBO into candidate rows.
- Mac and Linux focused regression: `54 passed` each.
- Ran Linux full-chain dry-run using old Gate-B + true FND2 + regime artifacts.
- No CI, deploy, rebuild, restart, DB write, auth, risk, or trading path touched.

Linux full formal smoke:

- source Gate-B run: `/tmp/openclaw/aeg_gate_b_runs/listing_24h_20260602_1847`
- FND2: `/tmp/openclaw/alpha_history_runs/fnd2_18mo_real_20260603`
- regime: `/tmp/openclaw/alpha_history_runs/aeg_regime_smoke_20260605`
- chain artifact: `/tmp/openclaw/alpha_history_runs/aeg_s3_gate_b_chain_listing_pbo_formal_smoke_final_20260612`
- listing_sample_count: `2`
- execution_observation_count: `2`
- listing_pbo_status: `produced_candidate_grid`
- formal matrix row_count: `12`
- matrix labels: `7 insufficient evidence`, `5 kill`
- chain_status: `COMPLETE_MATRIX_NON_PROMOTABLE`
- reject: `sample_count_below_30`

Interpretation:

- Fresh Gate-B後要跑的 full chain 已經試通：execution + event breadth + formal matrix + PBO。
- 舊 run 仍不是 promotion evidence，原因是樣本只有 2。
- 下一個真正 gate 是 fresh 24h probe 取得 `>=30` matched observations，再進 E2/MIT/QC。
