# E4 Isolated PostgreSQL Regression - ALR P2-6

Date: 2026-07-09
Verdict: `PASS`

Disposable PostgreSQL applied V030 through V154 and the reviewed shadow role.
One seeded ALR-owned rebuildable cache row was quarantined on the first guardian
pass, swept only after the grace recheck, and left its `derived_cache` artifact
plus two immutable retention events. The shadow role could not delete
`learning.alr_training_runs`. The container was removed and no production state
changed.
