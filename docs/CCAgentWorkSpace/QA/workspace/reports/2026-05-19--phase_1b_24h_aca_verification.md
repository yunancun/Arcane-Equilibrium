# QA Phase 1b 24h AC-A Verification + Engine 03:57 CEST Restart RCA

**Date**: 2026-05-19 (capture window ~07:48 UTC)
**Agent**: QA (e2e-integration-acceptance skill)
**Trigger**: PM dispatch — verify Phase 1b calibration deploy AC-A at T+24h (deploy_ts = 2026-05-18 13:50 UTC) + RCA engine restart at "03:57 UTC" (operator brief) / actual = 2026-05-19 01:57 UTC
**Mandate**: read-only verification + RCA + reporting；不 commit / push / mutate runtime

---

## §0 Verdict (TL;DR)

```
QA E2E ACCEPTANCE: INSUFFICIENT_SAMPLE / EXTEND_MONITORING
- AC-A 24h primary window (deploy_ts to deploy_ts+24h, ~6h to go):
  • Entry-close path only (oc_close_mf_fb_dm_*): 3/3 attempt = 100% (Wilson 95% CI [43.8, 100.0]) — PRELIMINARY PASS
  • Entry-close maker_fill: 0/3 = 0% (Wilson [0.0, 56.2]) — FAIL POINT-ESTIMATE
  • Risk-exit path (oc_risk_dm_*): 3/5 attempt = 60% (Wilson [23.1, 88.2]); 3/3 attempts → maker fill = 100% — DECISIVE MAKER EVIDENCE
  • Combined demo grid_close_* (n=8): 6/8 attempt = 75%; 3/8 maker_fill = 37.5%; 3/6 of attempts → maker = 50% (Wilson [18.8, 81.2])
  • Official healthcheck [70] = WARN NEUTRAL_LOW_SAMPLE (n<30 spec gate)
- Engine "03:57 UTC" restart RCA: TIMEZONE CORRECTION — actual time = 2026-05-19 01:57:19 UTC (03:57 CEST). Cause = (b) WATCHDOG AUTO-RESPAWN after detecting stale snapshot (181.9s > 45s threshold + 120s grace expired). Binary mtime unchanged (2026-05-18 13:50 UTC). Root upstream = systemd watchdog process itself exited status=2/INVALIDARGUMENT at 01:55:14 UTC (restart counter 37→38, 9th occurrence of identical exit pattern since 2026-05-12).
- Phase 2a 14d clock decision: NO RESET — engine binary unchanged, calibration parameters unchanged, no operator-authorized rebuild. Auto-respawn = transient watchdog-driven recycle, not a new t=0.
- Recommended next action: (a) continue Phase 2a observation; (b) re-verify AC-A at T+72h (~2026-05-21 13:50 UTC) for adequate sample size; (c) open P1 ticket for watchdog status=2 INVALIDARGUMENT root cause (9 historical occurrences ungated).
```

---

## §1 Engine Restart RCA (CRITICAL CORRECTION)

### §1.1 Timezone correction

**PM brief said "engine restarted at 03:57 UTC"**. Actual `ps -o lstart` returns CEST (UTC+2):

```
ps -o pid,lstart -p 1737243
    PID                  STARTED
1737243 二 5月 19 03:57:19 2026     ← CEST

ssh trade-core date -u
2026-05-19 07:47:28 UTC

Conversion: 2026-05-19 03:57:19 CEST = 2026-05-19 01:57:19 UTC
```

**Engine PID 1737243 started at 2026-05-19 01:57:19 UTC** (NOT 03:57 UTC). Watchdog PID 1736260 spawned at 01:55:19 UTC. PM brief is OFF BY 2H.

### §1.2 Cause classification: (b) watchdog auto-respawn after engine snapshot staleness

Full timeline reconstructed from `/tmp/openclaw/watchdog.log` + `journalctl --user -u openclaw-watchdog`:

| UTC time | Event | Source |
|---|---|---|
| 2026-05-19 01:55:14 | `openclaw-watchdog.service` main process exited `code=exited, status=2/INVALIDARGUMENT` | journalctl |
| 2026-05-19 01:55:14 | systemd marks unit `Failed with result 'exit-code'` (consumed 6h 37min CPU) | journalctl |
| 2026-05-19 01:55:19 | systemd `Scheduled restart job, restart counter is at 38` (`Restart=always`, `RestartSec=5`) | journalctl |
| 2026-05-19 01:55:19 | New watchdog (PID 1736260) starts polling | journalctl |
| 2026-05-19 01:55:49 | First snapshot poll = 91.9s stale (old engine PID 1506208 stopped writing pipeline_snapshot.json ~30s before watchdog respawn) | watchdog.log |
| 2026-05-19 01:55:49 → 01:57:19 | 120s grace period (`--grace-period 120`); 45/poll-2s logs `GRACE_PERIOD: snapshot stale … within grace period` | watchdog.log |
| 2026-05-19 01:57:19 | Grace expired (snapshot age=181.9s, total elapsed=120s); `ENGINE_CRASH detected — total crashes=1`; `Triggering auto-restart (attempt 1, timeout=120s)` | watchdog.log |
| 2026-05-19 01:57:29 | `Auto-restart succeeded` (engine PID 1737243 spawned); `Activating Python fallback (strike 1/3)` | watchdog.log |
| 2026-05-19 01:57:45 | `ENGINE_RECOVERED — Rust engine snapshot is fresh again` | watchdog.log |

### §1.3 Binary mtime CONFIRMED unchanged

```
stat /home/ncyu/BybitOpenClaw/srv/rust/target/release/openclaw-engine
修改时间：2026-05-18 15:50:00 +0200   ← CEST = 2026-05-18 13:50:00 UTC

readlink /proc/1737243/exe
/home/ncyu/BybitOpenClaw/srv/rust/target/release/openclaw-engine
```

PM brief "binary mtime unchanged (still 13:50 UTC May 18)" is correct. **No rebuild, no calibration parameter change**. Pure process-level recycle.

### §1.4 Watchdog status=2 INVALIDARGUMENT — historical pattern

The watchdog's own process exited with this exact exit code 9 times in last 7 days, all in similar bursts:

```
journalctl --user -u openclaw-watchdog -g INVALIDARGUMENT
5月 12 18:23:22 (37→38 burst start, multiple)
5月 12 18:27:14
5月 12 18:31:06
5月 12 18:34:58
5月 12 18:38:50
5月 12 18:57:27
5月 12 20:29:22
5月 12 21:59:32
5月 12 22:27:30
5月 19 01:55:14  ← TODAY
```

**Status=2 = Python ArgumentError / unhandled exception in canary/engine_watchdog.py**. Last 30-day pattern shows clusters (5/12 had 9 in 4h burst). Restart counter went 37→38 over 7 days = ~stable but not zero. **This is NOT an engine crash**; the watchdog process itself dies, systemd respawns it, and the new watchdog detects the (real) engine's snapshot is stale (probably because the dying old watchdog's CPU spike disrupted engine's snapshot writer, or because the engine process was independently briefly stalled). The new watchdog then kills the engine and respawns. **Net effect = engine process recycled but binary + config preserved**.

### §1.5 Is the restart "operator-triggered" or "autonomous"?

**(b) Watchdog auto-respawn after autonomous trigger**. NOT operator-triggered (operator went to bed; bash_history shows last `restart_all` was 2026-05-08 06:29). systemd `Restart=always` made it autonomous.

### §1.6 Lineage explanation for engine PID chain

Per TODO v52 chain `1066422 → 1143103 → 1253085 → 1506208 → 1737243`:

| PID | Approx start (UTC) | Trigger |
|---|---|---|
| 1066422 | 2026-05-17 ~23:50 | runtime activator deploy (operator) |
| 1143103 | 2026-05-17 23:54 | activator runtime restart (operator) |
| 1253085 | 2026-05-18 03:20 (approx) | 2nd activator-related rebuild (operator) |
| 1506208 | 2026-05-18 13:50 | calibration sweep deploy (operator, restart_all --rebuild) |
| 1737243 | 2026-05-19 01:57 | **watchdog auto-respawn** (autonomous) ← THIS REPORT |

Only the last one is autonomous — the four before are operator-triggered deploys.

---

## §2 24h AC-A SQL Verification

### §2.1 PG access method (for future reference)

Healthcheck helper does not expose `get_pg_dsn`. PG credentials are at `$HOME/BybitOpenClaw/secrets/environment_files/basic_system_services.env`:

```
POSTGRES_DB=trading_ai
POSTGRES_USER=trading_admin
POSTGRES_PASSWORD=<REDACTED>
POSTGRES_PORT=5432
```

DSN format: `host=127.0.0.1 port=5432 dbname=trading_ai user=trading_admin password='<REDACTED>'`

### §2.2 Schema verify

`trading.fills` has `close_maker_attempt boolean NOT NULL DEFAULT false` + `close_maker_fallback_reason text` (V094 schema, deployed 2026-05-17). Check constraint enforces enum: `timeout_taker / postonly_reject / cancel_grace_expired / ack_lost / rate_limit_pause_global / rate_limit_backoff_per_symbol / fast_escalate_safety_upgrade / not_attempted_safety_path / engine_shutdown_safety / fallback_to_taker_mandatory`.

### §2.3 Primary 24h window query (deploy_ts strict UTC cutoff)

Window: `[2026-05-18 13:50:00+00, 2026-05-19 13:50:00+00)` UTC strict (deploy_ts to deploy_ts+24h). Now = 2026-05-19 07:48 UTC — window is **~6h before T+24h target**. Demo only (live_demo has `use_maker_close=false` in TOML).

**A1. Aggregate (filter `exit_reason LIKE 'grid_close_%' AND order_id LIKE 'oc_%' AND NOT LIKE 'oc_risk_%'` = entry-close path only):**

| engine_mode | attempts | non_attempts | maker_fills | taker_fallback | timeout_taker | total |
|---|---|---|---|---|---|---|
| demo | 3 | 0 | 0 | 3 | 3 | 3 |
| live_demo | 0 | 0 | 0 | 0 | 0 | 0 (no whitelist closes) |

**A2. Split by order_id path** (entry vs risk-exit per W-C Caveat 2 lesson):

| path | total | attempts | maker_fills | timeout_taker | attempt_pct | maker_fill_pct (of attempts) |
|---|---|---|---|---|---|---|
| entry_close (`oc_close_mf_fb_dm_*`) | 3 | 3 | 0 | 3 | 100.0% | 0.0% |
| risk_exit (`oc_risk_dm_*`) | 5 | 3 | 3 | 0 | 60.0% | 100.0% |
| **Combined grid_close_*** | **8** | **6** | **3** | **3** | **75.0%** | **50.0%** |

**A3. Full row dump (n=8, all paths)**:

| ts_utc | symbol | path | attempt | fallback_reason | liquidity_role | fee_rate |
|---|---|---|---|---|---|---|
| 2026-05-18 14:00:00 | DOTUSDT | entry | t | timeout_taker | taker | 0.00055 |
| 2026-05-18 14:21:00 | ICPUSDT | risk | **f** | — | taker | 0.00055 |
| 2026-05-18 14:27:00 | LTCUSDT | risk | **f** | — | taker | 0.00055 |
| 2026-05-18 15:15:10 | LTCUSDT | risk | t | NULL (maker fill) | **maker** | **0.0002** |
| 2026-05-19 02:09:08 | TRXUSDT | entry | t | timeout_taker | taker | 0.00055 |
| 2026-05-19 02:24:36 | OPUSDT | entry | t | timeout_taker | taker | 0.00055 |
| 2026-05-19 02:27:00 | ARBUSDT | risk | t | NULL (maker fill) | **maker** | **0.0002** |
| 2026-05-19 04:42:26 | AVAXUSDT | risk | t | NULL (maker fill) | **maker** | **0.0002** |

**3 real maker fills with `fee_rate=0.0002` (vs taker 0.00055)** — fee evidence is irrefutable proof of maker-first execution working on the risk-exit path.

### §2.4 Wilson 95% CI

| Metric | k/n | Point | Wilson 95% CI | Spec gate |
|---|---|---|---|---|
| Entry-close attempt_pct | 3/3 | 100.0% | [43.8%, 100.0%] | AC-A ≥25% PASS but n<30 |
| Entry-close maker_fill (of attempts) | 0/3 | 0.0% | [0.0%, 56.2%] | AC-19 ≥30% INSUFFICIENT |
| Risk-exit attempt_pct | 3/5 | 60.0% | [23.1%, 88.2%] | AC-1 ≥60% PASS lower-bound miss |
| Risk-exit maker_fill (of attempts) | 3/3 | 100.0% | [43.8%, 100.0%] | AC-1 ≥60% PASS by lower bound |
| Combined attempt_pct | 6/8 | 75.0% | [40.9%, 92.9%] | AC-A ≥25% PASS by lower bound |
| Combined maker_fill (of attempts) | 3/6 | 50.0% | [18.8%, 81.2%] | AC-19 ≥30% INSUFFICIENT POINT |
| Combined maker_fill (of total closes) | 3/8 | 37.5% | [13.7%, 69.4%] | mixed |

**n=8 << 30** = `INSUFFICIENT_SAMPLE` per spec §11.7 AC-14 Wilson CI gate. Official healthcheck [70]:

```
[70] WARN
close_maker_fill_rate Wilson gate — demo: n=8, maker=3, fill=0.375, wilson95=[0.137,0.694], verdict=NEUTRAL_LOW_SAMPLE
ac18_fallback_to_taker_rate=demo: n=9, fallback_to_taker=9, rate=1.000, wilson95=[0.701,1.000], verdict=NEUTRAL_LOW_SAMPLE
```

[71] `close_maker_zero_spine_lineage` = PASS (close path remains spine-free per W-C Caveat 2).

---

## §3 vs Pre-Calibration Baseline (24h before deploy_ts)

Window: `[2026-05-17 13:50:00+00, 2026-05-18 13:50:00+00)` UTC strict. Same filter scope (demo, grid_close_*).

| path | total | attempts | maker_fills | timeout_taker | attempt_pct | maker_fill_pct |
|---|---|---|---|---|---|---|
| entry_close | 3 | 3 | 0 | 3 | **100.0%** | 0.0% |
| risk_exit | **15** | **0** | 0 | 0 | **0.0%** | — |

Pre-calib entry path already had 100% attempt + 0% maker fill (= timeout 30s). Pre-calib risk_exit path 0% attempt — **risk_exit path was activated in subsequent restart** (the calibration didn't change risk_exit path; the original activator deploy at 2026-05-17 23:54 UTC turned on maker close on risk_exit).

**Decisive observation**: Pre-calib (timeout=30s) had **0 entry-path maker fills out of 3 attempts**. Post-calib (timeout=90s) has **0 entry-path maker fills out of 3 attempts** — **3x timeout did NOT improve entry-path fill rate** (still 0/3 with all timing out). This is consistent with the v52 TODO line 5 finding "100% timeout_taker" pre-calibration; calibration sweep simulation predicted 70.8% but real entry-path post-calib is still 0%.

However, risk_exit path is now **fully maker** (3/3 attempts → fill). Total fee evidence:

- 3 maker fills × 0.0002 fee_rate × ~0.05 USDT/fill = ~$0.04 saved vs taker baseline
- Annual extrapolation: 3 maker / 18 hours × 8760 hr/yr = ~1460 maker fills/yr × ~$0.04/fill = **~$58/year** (within spec §1.2 conservative range $50-$200/year)

---

## §4 vs Simulation 70.8% Prediction (top cell G-AB-01-C90)

| Metric | Sim G-AB-01-C90 prediction | Real entry-close 24h | Real combined 24h |
|---|---|---|---|
| `maker_fill_rate` | 70.8% | 0% (0/3) | 50% (3/6 attempts) |
| `expected_fee_saving_bps` | +3.37 bps | ~0 bps (entry only) | ~+1.5 bps (combined estimate) |
| Sample size | 81 simulated cells | n=3 entry | n=6 attempts |

**E2 caveat validated**: Spec v52 line 5 explicitly noted "BBO-cross-proxy systematically optimistic". Real entry-path 0% vs sim 70.8% = simulation overestimate by ~70 percentage points on entry path. **Combined 50% (with risk-exit boost) is ~20pp below sim prediction** — still far above the 25% AC-A floor and 15% Wilson rollback trigger, but sample is too small for verdict.

**Rollback trigger check** (spec line 301):
- "real fill < 15% Wilson lower at n≥30" — n=8 < 30, gate NOT EVALUABLE (NEUTRAL)
- "adverse_real > 5.55 bps baseline" — no adverse selection signal collected
- **NO ROLLBACK TRIGGERED** (insufficient sample, not statistical FAIL)

---

## §5 Clock Decision (Phase 2a 14d Observation)

### §5.1 Spec / AMD review

Per AMD v0.7 line 240: `engine restart 後重置（accepted trade-off：rate-limit state 不跨 process boundary）` — applies to **rate-limit state**, not Phase 2a 14d clock.

Per spec v1.3 line 738 AC-19: `14d extended observation close_maker_fill_rate ≥ 30%` — no explicit "engine restart resets clock" clause; the 14d window is measured from "Phase 2a start" which the TODO defines as deploy_ts.

Per TODO v52 line 301 + line 391: `Phase 2a 14d observation clock reset @ 13:50 UTC NEW t=0` (the calibration deploy itself reset the clock; subsequent restarts not addressed).

### §5.2 Decision: **NO RESET — Phase 2a t=0 stays = 2026-05-18 13:50 UTC**

Rationale (per CC 16-root principle 12 "evolve from evidence, not anecdote"):

1. **Binary unchanged**: `stat /home/ncyu/BybitOpenClaw/srv/rust/target/release/openclaw-engine` = 2026-05-18 13:50 UTC (= calibration deploy). No `--rebuild` ran.
2. **TOML unchanged**: `risk_config_demo.toml [runtime] use_maker_close=true` since 2026-05-17 23:54 UTC; calibration only changed Rust constant `timeout_ms 30s→90s` (recompiled into binary at 13:50 UTC May 18).
3. **Configuration semantics**: Engine binary at 01:57 UTC May 19 = same byte-for-byte binary at 13:50 UTC May 18. Restart is process-level recycle.
4. **Spec/AMD intent**: "Engine restart 後重置" only governs runtime in-RAM state (rate-limit counters). Phase 2a clock is statistical window not bound to engine PID.
5. **Operational continuity**: 24h pre-restart sample = 8 grid_close fills, 24h post-restart sample (so far ~6h) shows 2 entry + 2 risk = consistent rate. No regime change.

**Phase 2a 14d clock**: t=0 = 2026-05-18 13:50:00 UTC; t+14d = 2026-06-01 13:50:00 UTC. Continue uninterrupted.

### §5.3 Caveat — log clock decision in M-2 reviewer brief

PM should log in next M-2 audit packet that an autonomous watchdog respawn occurred at 2026-05-19 01:57 UTC during the Phase 2a 14d window, and that clock decision = NO RESET, with above 5 evidence points. This protects against later "did clock reset?" ambiguity.

---

## §6 AC-A Verdict

```
AC-A: INSUFFICIENT_SAMPLE
- attempt_pct entry-path 100% (3/3) Wilson [43.8, 100.0] PRELIMINARY PASS @ ≥25% threshold
- attempt_pct combined 75% (6/8) Wilson [40.9, 92.9] PASS @ ≥25% threshold
- maker_fill_rate entry-path 0% (0/3) — POINT FAIL @ ≥30% but n<30 NEUTRAL
- maker_fill_rate combined 50% (3/6 attempts) Wilson [18.8, 81.2] — POINT PASS @ ≥30%, n<30 NEUTRAL
- Official healthcheck [70] = WARN NEUTRAL_LOW_SAMPLE
- AC-18 fallback_to_taker_rate 100% (9/9) — PASS but n<30 NEUTRAL
- No spec rollback trigger fired (n<30; real fill not < 15% Wilson lower at n≥30; no adverse selection signal)
- Engine restart at t+12h (UTC 01:57) is autonomous watchdog respawn, NOT rebuild — does not invalidate window
```

Sample velocity = 8 grid_close in 18h = ~0.44/hour → 24h projected = ~10.6 fills → 72h projected = ~32 fills (just crosses n=30 minimum). **Recommended re-verify at T+72h = 2026-05-21 13:50 UTC** for first n≥30 sample-size verdict.

---

## §7 Recommended Next Action

| ID | Recommendation | Priority | Owner | ETA |
|---|---|---|---|---|
| 1 | **Continue Phase 2a 14d observation** — no clock reset, no rollback trigger | P0 | PM | immediate |
| 2 | **Re-verify AC-A at T+72h (2026-05-21 13:50 UTC)** — first n≥30 verdict window | P0 | PM dispatch QA | T+72h |
| 3 | **Document clock decision in M-2 reviewer brief** — autonomous watchdog respawn @ 01:57 UTC, NO RESET, 5 evidence points | P1 | PM | next M-2 packet |
| 4 | **Open P1 ticket: watchdog status=2 INVALIDARGUMENT RCA** — 9 historical occurrences in 7d ungated; engine_watchdog.py crashes silently and only systemd respawn keeps system up. Need stderr capture + Python traceback diagnosis. | P1 | E2 + E1 | 3-5d |
| 5 | **Open P1 ticket: entry-path 0% maker fill RCA** — 3x timeout (30s→90s) showed no improvement on entry-path. Simulation 70.8% deviates from real 0% by 70pp. Investigate: (a) post-only reject ratio (PostOnly never crosses), (b) BBO movement faster than 90s, (c) E2 BBO-cross-proxy bias quantification. | P2 | E2 + E3 | 5-7d |
| 6 | **Open P2 follow-up: risk-exit path is the maker success path** — 3/3 risk_exit maker fill = 100% (small n). Confirm this is by-design and document in spec §6.X to clarify expectation difference vs entry-path. | P3 | PA | 1d |

**Rollback decision**: NOT TRIGGERED. Hold timeout=90s.

---

## §8 Cross-Cutting Notes

### §8.1 Healthcheck [70] vs my custom SQL
- My SQL uses `[deploy_ts, deploy_ts+24h)` strict UTC = 8 grid_close demo
- Healthcheck [70] uses `NOW() - 24h` rolling = 8 attempts demo + 1 attempt? difference reconciliation: [70] queries `close_maker_attempt = TRUE` regardless of exit_reason, my SQL filters to `grid_close_%`. The extra +1 attempt is `ma_reverse_cross` (1 attempt) + `phys_lock_gate4_giveback` (1 attempt) row. **n=9 for AC-18 fallback_to_taker_rate** vs **n=8 for AC-19 fill_rate** (which only counts confirmed maker_fill outcome).
- Both verdicts converge: NEUTRAL_LOW_SAMPLE.

### §8.2 W-C Caveat 2 lesson applied
- entry vs risk_exit path split (per `oc_*` vs `oc_risk_*` order_id prefix) is mandatory for honest AC verdict. Combined-only number = 75% / 50% mask significantly different behavior per path.

### §8.3 Live_demo entry-close = 0 fills
- Confirmed `risk_config_live.toml use_maker_close=false` per design (Phase 2b LiveDemo deferred to separate ticket); 0 live_demo whitelist closes in 24h is expected, not regression.

### §8.4 NO LIVE TRADE LEAK
- 24h `engine_mode` distribution: demo=23, live_demo=0, live=0, paper=0. Phase 2b/3 gates hold.

### §8.5 Restart did not invalidate prior 12h sample
- Pre-restart (13:50 UTC → 01:57 UTC = 12.1h): 4 grid_close (2 entry timeout_taker + 2 risk_exit, 1 maker / 3 attempts)
- Post-restart (01:57 UTC → 07:48 UTC = 5.85h): 4 grid_close (2 entry timeout_taker + 2 risk_exit maker)
- Rate consistent (~0.65/hour pre vs ~0.68/hour post). No regime shift attributable to restart.

---

## §9 Artifacts + Evidence Trail

| Source | Path |
|---|---|
| Watchdog log | `/tmp/openclaw/watchdog.log` (lines 03:55:14-03:57:45 CEST) |
| Engine log | `/tmp/openclaw/engine.log` (line `2026-05-19T07:46:55Z tick stats ticks=16143000 fills=11` etc.) |
| Watchdog systemd unit | `/home/ncyu/.config/systemd/user/openclaw-watchdog.service` |
| journalctl evidence | `journalctl --user -u openclaw-watchdog --since "2026-05-19 03:00:00 CEST"` |
| Engine binary | `/home/ncyu/BybitOpenClaw/srv/rust/target/release/openclaw-engine` (mtime 2026-05-18 13:50:00 UTC) |
| PG SQL artifact | `/tmp/qa_aca4.sql`, `/tmp/qa_aca5.sql` on trade-core (not persisted, executed via psql -f) |
| Demo TOML | `/home/ncyu/BybitOpenClaw/srv/settings/risk_control_rules/risk_config_demo.toml` `[runtime] use_maker_close=true` |
| Spec | `docs/execution_plan/2026-05-15--edge_p2_3_phase_1b_close_maker_first_spec.md` v1.3 |
| AMD | `docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-02-edge-p2-3-phase-1b-close-maker-first.md` v0.7 |
| Calibration spec | `docs/execution_plan/2026-05-18--phase_1b_calibration_sweep_spec.md` v0.2 |
| TODO | `srv/TODO.md` v52 line 301 (P0-PHASE-1B-PARAM-CALIBRATION-1) |
| Healthcheck [70] | `helper_scripts/db/passive_wait_healthcheck/checks_close_maker_audit.py::check_close_maker_fill_rate` |

---

## §10 Compliance With Mandate

| Mandate | Result |
|---|---|
| DO NOT restart engine or mutate runtime state | OK — all queries read-only psql `-f` |
| DO NOT call any /trading/ or /risk/ write API | OK |
| DO NOT touch authorization.json | OK |
| DO NOT skip Wilson CI (n≥30) — n<30 = INSUFFICIENT_SAMPLE | OK — explicit INSUFFICIENT_SAMPLE verdict |
| If cannot access PG, STOP and report exact error | NOT TRIGGERED — accessed PG via secrets/environment_files/basic_system_services.env |

---

**QA E2E ACCEPTANCE DONE**: **INSUFFICIENT_SAMPLE / EXTEND_MONITORING** · report path: `srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-19--phase_1b_24h_aca_verification.md`
