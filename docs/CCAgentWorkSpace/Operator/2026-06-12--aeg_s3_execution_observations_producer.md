# AEG-S3 execution observations producer

Code checkpoint: `9eaad929` (`[skip ci] Add AEG-S3 execution observations producer`)

Completed:

- Added artifact-only `aeg_s3_execution_observations`.
- It converts `listing_fade` candidate evidence plus a Gate-B run into matched `execution_observations.jsonl`.
- The output feeds `aeg_s3_event_execution_realism` directly.
- Unsupported candidates fail closed: `funding_revive` and `oi_delta` are not forced into Gate-B single-symbol observations.
- Mac and Linux focused regression: `31 passed` each.
- Compile/static checks passed; no runtime, DB, Bybit trading, auth, risk, deploy, rebuild, or restart path was touched.

Linux true smoke on old Gate-B run:

- Gate-B source: `/tmp/openclaw/aeg_gate_b_runs/listing_24h_20260602_1847`
- listing_fade evidence: `2` samples
- execution observations: `2` matched rows
- event execution realism at 10 USDT: `FAIL` due `sample_count_below_30` and `participation_rate_p95_above_0_05`
- event execution realism at 1 USDT: `FAIL` due `sample_count_below_30` only

Interpretation:

- The producer wiring works.
- The old run is not promotion evidence.
- Fresh Gate-B evidence still needs `>=30` matched samples before execution realism can pass.

Next operator-relevant trigger:

- Wait for `[GATE-B-WATCH]` fresh Pre-Market / PreLaunch / conversion alert or latest artifact `ACTIONABLE_*`.
- Then run isolated 24h Gate-B probe and rerun the listing_fade evidence -> observations -> execution realism -> formal matrix chain.
