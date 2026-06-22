# Runtime Source Reconcile Blocker Manifest

Read-only check result：`trade-core` is still at `917be4cc`, its local `origin/main` is stale `1401848b`, while GitHub/local main is `e2b90306`. The runtime tree is dirty with 55 paths.

Useful split:

- 43 paths already equal current main and are selective-restore residue.
- 7 tracked files still differ from current main.
- 3 untracked files conflict with current-main paths.
- `helper_scripts/research/cost_gate_learning_lane/` is untracked and contains 2 files that differ from current main plus 2 pycache files.

Demo-learning stack is still not installed: no matching crontab entries and no healthcheck/latest/status/heartbeat artifacts.

No runtime change was made. No fetch/pull/reset/clean, no crontab install, no restart/deploy, no PG/Bybit write, no Cost Gate lowering.

Before source reconcile, preserve/review the conflict paths listed in:

`docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-22--runtime_source_reconcile_blocker_manifest.md`
