# FlashDip Execution-Realism Cron/Killboard Arm

Date: 2026-06-20
Runtime host: `trade-core`

## Operator Summary

FlashDip K6 execution-realism is now a durable read-only runtime status source. It runs before the L1 short-exit replay cron and is surfaced in alpha discovery as arm `flash_dip_execution_realism`.

Installed cron:

- `29 6 * * * ... flash_dip_execution_realism_cron.sh`
- Backup before install: `/tmp/openclaw/cron_backups/crontab_before_flash_dip_execution_realism_20260620T175028Z.txt`

Latest execution-realism artifact:

- `/tmp/openclaw/research/tail_dislocation_meanrev/shallow_retune_execution_realism_latest.json`
- SHA256 `68c0c5ad486fbf2c71be95eea41c1861472bd7f03411e0da48d3d0e2cf375aa3`
- K6/N2/C3/nf0.005
- 10bps daily-exit gate: blocked, annret `-2.56%`
- Best short-exit research signal: 240m, annret `1.73%`, maxDD `0.00033`

Latest alpha discovery:

- `/tmp/openclaw/alpha_discovery_throughput/alpha_discovery_latest.json`
- SHA256 `225de153dafec013270530b64883c0c6317082a56f66c118c1c55f042bc4bc2c`
- Global status remains `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`
- Ready/probe remains `0`

## Boundary

This is not a retune, not a strategy enable, and not promotion evidence. It only makes the K6 execution-realism diagnosis durable and visible.

No strategy parameter, order behavior, risk setting, auth state, engine process, API process, PG table, or Bybit account state was changed.

Runtime writes were limited to user crontab plus `/tmp/openclaw` local artifacts/logs/heartbeats.

## Next Practical Research Step

Wait for or deliberately capture K6 candidate windows with L1 overlap, then use the existing L1 short-exit replay arm to test the 240m short-exit path. Any positive L1 replay would still require QC/MIT/AI-E review and a default-off design before any demo/live behavior change.
