# AEG-S3 listing_fade PBO grid wiring

Code checkpoint: `3d03698c` (`[skip ci] Add listing fade PBO grid wiring`)

Completed:

- `listing_fade` now supports explicit PBO grid generation:
  - `--include-default-pbo-grid`
  - `--pbo-grid-json`
- Gate-B chain passes those flags through and reports `listing_pbo_status`.
- Default behavior remains honest: no PBO is produced unless explicitly requested.
- Mac and Linux focused regression: `54 passed` each.
- Compile/static checks passed.
- No CI, deploy, rebuild, restart, DB write, auth, risk, or trading path touched.

Linux true smoke on old run:

- source: `/tmp/openclaw/aeg_gate_b_runs/listing_24h_20260602_1847`
- artifact: `/tmp/openclaw/alpha_history_runs/aeg_s3_gate_b_chain_listing_pbo_smoke_20260612`
- listing_sample_count: `2`
- execution_observation_count: `2`
- listing_pbo_status: `produced_candidate_grid`
- chain_status: `COMPLETE_EXECUTION_REALISM_FAIL`
- reject: `sample_count_below_30`

Interpretation:

- The PBO grid and Gate-B pass-through are wired.
- The old run is still not promotion evidence.
- Fresh Gate-B still needs `>=30` matched observations before execution realism can pass.

Next trigger:

- Wait for `[GATE-B-WATCH]` fresh Pre-Market / PreLaunch / conversion alert or latest artifact `ACTIONABLE_*`.
- Run isolated 24h Gate-B probe.
- Run `aeg_s3_gate_b_chain.harness --include-default-pbo-grid` on that probe output.
