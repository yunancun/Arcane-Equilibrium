# PM — V096 / Cron / Watchdog / Entry-Path RCA Closure

Date: 2026-05-19
Scope: operator-authorized V096 manual apply/register, operator-authorized P1 cron install wave, and directly-doable RCA/artifact cleanup. No V095 apply, engine restart, allLiquidation revival, risk config edit, runtime env edit, or deploy action was performed.

## §1 Authorized Runtime Actions

### V096 manual apply/register

Verdict: DONE on `trade-core`.

Evidence:

| Item | Result |
|---|---|
| Source migration | `sql/migrations/V096__drop_dead_learning_tables.sql` |
| SHA-384 checksum | `dd4613c384f053b6ff7cff8cea48529790e7e77458e97e3e2d89ca31142c58cfe5a691c367df5a0209812fd36e91b982` |
| Backup dir | `/tmp/openclaw/migration_backups/v096_20260519T103714Z` |
| Precheck rows | `learning.rl_transitions=0`, `learning.symbol_clusters=0` |
| Precheck dependents | `learning.rl_transitions:0`, `learning.symbol_clusters:0` |
| `_sqlx_migrations` | `96|drop dead learning tables|t|dd4613...b982|-1` |
| Postcheck tables | `to_regclass(...)` returns NULL for both target tables |

Rollback path is restore-from-backup only: recreate the two tables from the backup DDL/data if a future query proves runtime dependency. There is no evidence of live dependency; the migration used `DROP ... RESTRICT` and guard checks.

### P1 cron install wave

Verdict: INSTALLED on `trade-core`.

Installed wrappers:

| Check | Cron | Current first-fire state |
|---|---|---|
| `[75] panel_aggregator_health_cron_fires` | `*/5 * * * *` | PASS, sentinel fresh |
| `[76] wave9_replay_no_live_mutation_watch_cron_fires` | `0 * * * *` | WARN until first top-of-hour fire after install |
| `[77] replay_key_rotation_check_cron_fires` | `0 9 * * *` | WARN until next daily fire |
| `[78] feature_baseline_writer_cron_fires` | `41 4 * * *` | WARN until next daily fire |
| `[79] blocked_symbols_30d_unblock_check_cron_fires` | `0 4 * * 0` | WARN until next weekly fire |

Crontab backup: `/tmp/openclaw/crontab_backups/before_p1_cron_install_wave_1_20260519T103745Z.cron`.

Direct heartbeat check at 2026-05-19 12:44 CEST:

```text
75|PASS|panel_aggregator_health.last_fire fresh age=4.9min
76|WARN|wave9_replay_no_live_mutation_watch.last_fire missing
77|WARN|replay_key_rotation_check.last_fire missing
78|WARN|feature_baseline_writer.last_fire missing
79|WARN|blocked_symbols_30d_unblock_check.last_fire missing
```

The WARN states are expected immediately after installation because their schedules had not fired yet. They are not evidence of failed install.

## §2 P1-WATCHDOG-STATUS2-RCA

Verdict: RCA CLOSED. The 2026-05-19 01:52-01:57 UTC watchdog cluster was a transient DNS/transport outage misclassified as `ENGINE_CRASH`, not a Rust panic/OOM.

Current state at recheck:

| Item | Result |
|---|---|
| Watchdog process | alive, PID `1736260` |
| Engine process | alive, PID `1737243` |
| Watchdog status | `engine_alive=true`, demo snapshot fresh (`~11s`) |
| Watchdog state | `consecutive_failures=0`, `circuit_broken=false` |
| OOM/segfault evidence | none in `dmesg` grep |

Timeline:

| CEST | UTC | Evidence |
|---|---|---|
| 03:52:12 | 01:52:12 | engine REST position fetch fails with `HTTP transport error` |
| 03:52:17 | 01:52:17 | scanner `market/tickers` REST fails with `HTTP transport error` |
| 03:52:19 | 01:52:19 | watchdog classifies stale snapshot as `ENGINE_CRASH`; sends restart |
| 03:53:16-03:54:07 | 01:53:16-01:54:07 | demo startup REST/DCP/fee/balance retries fail |
| 03:54:27/03:54:43 | 01:54:27/01:54:43 | WS connect fails: `Temporary failure in name resolution` |
| 03:54:04-03:54:22 | 01:54:04-01:54:22 | host journal shows DNS/bootstrap failures and no DNS fallback candidates |
| 03:55:14 | 01:55:14 | watchdog 3-strike exits; systemd restarts watchdog |
| 03:57:29-03:57:45 | 01:57:29-01:57:45 | auto-restart succeeds, demo snapshot recovers |

Root cause:

1. The engine was externally degraded by DNS/transport outage and startup REST balance failure, not by a panic.
2. `engine_watchdog.py` only classifies `network_outage` when the active `/tmp/openclaw/engine.log` tail has at least 5 consecutive network-error lines and no panic/assertion indicators.
3. The relevant evidence was split across rotated engine logs and interleaved with normal tick/SIGTERM/restart lines, so the classifier defaulted to conservative `engine_crash`.
4. The stale threshold (`45s`) is shorter than outage-time REST retry/startup behavior, so restart loops can accumulate strikes during infrastructure incidents.

Follow-up ticket: `P1-WATCHDOG-NETOUTAGE-CLASSIFIER-FIX` should broaden classification to recent rotated logs/canary events and suppress strike/restart during confirmed DNS/transport outage.

## §3 P2-ENTRY-PATH-0PCT-MAKER-FILL-RCA

Verdict: RCA CLOSED. The 0% maker-fill issue is path-specific to entry-close fallback rows, not a global PostOnly/maker execution failure.

Window: from Phase 1b deploy clock `2026-05-18 13:50:00 UTC` through recheck, `engine_mode='demo'`, `is_paper=true` demo fills, whitelist exits.

| Close path | Total closes | Maker attempts | Maker fills | Timeout taker | Attempt % | Maker fill / attempts |
|---|---:|---:|---:|---:|---:|---:|
| `entry_close` (`oc_close_mf_fb_*`) | 6 | 6 | 0 | 6 | 100.0% | 0.0% |
| `risk_exit` (`oc_risk_*`) | 5 | 3 | 3 | 0 | 60.0% | 100.0% |

Key rows:

```text
2026-05-18 14:00:00 DOTUSDT entry_close attempt=t timeout_taker taker 0.00055
2026-05-19 02:09:08 TRXUSDT entry_close attempt=t timeout_taker taker 0.00055
2026-05-19 02:24:36 OPUSDT  entry_close attempt=t timeout_taker taker 0.00055
2026-05-19 05:42:01 BTCUSDT entry_close attempt=t timeout_taker taker 0.00055
2026-05-19 09:36:10 ARBUSDT entry_close attempt=t timeout_taker taker 0.00055
2026-05-19 09:52:11 DOTUSDT entry_close attempt=t timeout_taker taker 0.00055
```

Counterexample proving maker plumbing works:

```text
2026-05-18 15:15:10 LTCUSDT risk_exit attempt=t maker 0.0002
2026-05-19 02:27:00 ARBUSDT risk_exit attempt=t maker 0.0002
2026-05-19 04:42:26 AVAXUSDT risk_exit attempt=t maker 0.0002
```

Source facts:

| File | Relevant behavior |
|---|---|
| `rust/openclaw_engine/src/tick_pipeline/commands.rs` | `use_maker_close` is Demo-only; close dispatch builds PostOnly limit when reason is whitelisted |
| `rust/openclaw_engine/src/strategies/common/maker_price.rs` | whitelist grid/MA/etc uses `buffer_ticks=1`, `offset_bps=0.5`, `timeout_ms=90_000`; BBO/tick-size strict pricing, no last-price fallback |
| `rust/openclaw_engine/src/event_consumer/pending_sweep.rs` | close maker timeout maps to `timeout_taker`; cancel ack grace is only 2s for close maker |

Root cause:

1. Activator and audit instrumentation are working: entry-close attempts are 6/6.
2. Exchange-side maker capability is working: risk-exit attempts filled maker 3/3 at maker fee.
3. The calibration sweep prediction (`G-AB-01-C90` simulated 70.8%) is over-optimistic for entry-close rows. The BBO-cross proxy does not match real order queue/trade-tape behavior in this path.
4. Entry-close fallback path remains operationally safe but fee-saving ineffective so far; it should not graduate based on simulated fill-rate alone.

Follow-up ticket: `P2-ENTRY-CLOSE-MAKER-REAL-FILL-FIX` should compare entry-close vs risk-exit limit placement, order lifetime, cancel/fallback sequencing, and queue/trade-tape fill evidence before any runtime parameter change.

## §4 Artifact Classification

Local untracked docs are valid evidence and should be tracked:

| Path | Classification |
|---|---|
| `docs/CCAgentWorkSpace/Operator/2026-05-18--phase_1b_calibration_cell_selection_report.md` | Operator evidence report |
| `docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-18--phase_1b_24h_post_deploy_verification_update.md` | QA evidence report |

Linux untracked `helper_scripts/calibration/output/` contains generated sweep cells/CSV/summary artifacts. It is preserved on `trade-core` and ignored via `.gitignore`; it is not deleted and not treated as source of truth. The committed calibration report references the runtime output paths.

## §5 PM Verdict

`READY-TO-CONTINUE-WITH-AUTHORIZATION`: V096 and cron install gates are closed. Cron [76]-[79] still need natural first-fire observation. Watchdog and entry-path RCA items are closed with follow-up implementation tickets. No deploy or runtime restart was executed.
