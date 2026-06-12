# AEG-S3 sidecar matrix wiring

Code checkpoint: `66a9e511` (`[skip ci] Wire AEG-S3 sidecar matrix inputs`)

Completed:

- `aeg_s3_matrix_inputs` can now consume existing sidecar artifacts:
  - `--breadth-run-dir`
  - `--execution-realism-json`
- If sidecars are missing, it keeps the old fail-closed placeholder behavior.
- Candidate/parameter mismatches fail closed before matrix use.
- Mac and Linux focused regression: `24 passed` each.

Linux true artifact smoke:

- funding_revive event breadth was consumed as `provided_breadth_artifact`
- formal matrix row_count `24`
- coverage `PASS`
- survivorship `pit_fnd2_delisted_proof`
- execution still `unverified_missing_missing`
- final labels: `16 insufficient evidence`, `8 kill`

This finishes the guest/sidecar wiring. It does not make funding_revive promotable: DSR/PBO remain failed and empirical execution still needs `>=30` matched observations.
