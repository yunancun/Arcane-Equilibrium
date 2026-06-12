# AEG-S3 Gate-B evidence chain wrapper

Code checkpoint: `75ed19c8` (`[skip ci] Add AEG-S3 Gate-B evidence chain`)

Completed:

- Added artifact-only `aeg_s3_gate_b_chain`.
- It turns a Gate-B listing run into the standard chain:
  - listing_fade evidence
  - candidate direct rows
  - candidate metrics
  - execution observations
  - event execution realism
  - optional event breadth and formal matrix when FND2/regime artifacts are supplied
- Mac and Linux focused regression: `52 passed` each.
- Compile/static checks passed.
- No CI, deploy, rebuild, restart, DB write, auth, risk, or trading path touched.

Linux true smoke on old run:

- source: `/tmp/openclaw/aeg_gate_b_runs/listing_24h_20260602_1847`
- artifact: `/tmp/openclaw/alpha_history_runs/aeg_s3_gate_b_chain_listing_smoke_20260612`
- listing_sample_count: `2`
- execution_observation_count: `2`
- chain_status: `COMPLETE_EXECUTION_REALISM_FAIL`
- reject: `sample_count_below_30`

Interpretation:

- The one-click chain works on real artifact paths.
- The old run is still not promotion evidence.
- Fresh Gate-B still needs `>=30` matched observations before execution realism can pass.

Next trigger:

- Wait for `[GATE-B-WATCH]` fresh Pre-Market / PreLaunch / conversion alert or latest artifact `ACTIONABLE_*`.
- Run isolated 24h Gate-B probe.
- Run `aeg_s3_gate_b_chain.harness` on that probe output.
