# Operator — V096 / Cron / Watchdog / Entry-Path Closure

Date: 2026-05-19

PM closure report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-19--v096_cron_watchdog_entry_rca_closure.md`.

## Result

- V096 was manually applied/registered on `trade-core` only. `_sqlx_migrations` has version 96 success=true with checksum `dd4613c384f053b6ff7cff8cea48529790e7e77458e97e3e2d89ca31142c58cfe5a691c367df5a0209812fd36e91b982`; `learning.rl_transitions` and `learning.symbol_clusters` are gone.
- P1 cron install wave was installed. `[75]` has already fired and is PASS; `[76]-[79]` are expected WARN until their first natural schedule fire.
- Watchdog STATUS2 RCA: 2026-05-19 01:52-01:57 UTC was DNS/transport outage misclassified as `ENGINE_CRASH`, not panic/OOM. Current engine/watchdog are alive.
- Entry-path 0% maker-fill RCA: entry-close path has 6/6 attempts and 0/6 maker fills, while risk-exit has 3/3 maker fills. This is path-specific and likely simulation/proxy mismatch, not global PostOnly failure.
- Calibration sweep output under `helper_scripts/calibration/output/` is generated runtime evidence and is now ignored; reports are tracked instead.

No V095 apply, engine restart, allLiquidation revival, risk config edit, or runtime env mutation was performed.
