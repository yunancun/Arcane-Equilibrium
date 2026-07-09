# QA Phase 1b Post-Deploy Verification UPDATE — T+10.6h (10:36 UTC capture)

**Date**: 2026-05-18
**Agent**: QA (e2e-integration-acceptance skill)
**Trigger**: PM re-dispatch following first partial QA (T+18min) for statistical-significant verdict
**Elapsed since first restart**: **2026-05-17 23:54:36 UTC → 2026-05-18 10:36 UTC = 10h 41min**
**Elapsed since 2nd rebuild restart**: **2026-05-18 03:20 UTC → 10:36 UTC = 7h 16min**
**Scope**: AC-A/B/C + healthcheck [62-65] + [67] + watchdog + Phase 1b activator field test
**Mandate**: read-only verification + reporting；不動 prod config / runtime；不 commit / push

---

## §0 Verdict

```
QA E2E ACCEPTANCE: INSUFFICIENT_SAMPLE / EXTEND_MONITORING
- AC-A (attempt rate)       PRELIMINARY PASS (demo-only post-restart 3/3 = 100%)
                            INSUFFICIENT for full 14d-AC-19 verdict (n=4 < 30)
- AC-B (fallback_reason)    PRELIMINARY PASS (100% timeout_taker non-NULL)
                            INSUFFICIENT n=4 < min_sample=5
- AC-C (negative whitelist) PASS (4/4 halt_session 0% attempt)
- Healthcheck [62][63][65]  INSUFFICIENT_SAMPLE (n=4 < {30, 5, 5})
- Healthcheck [64]          INSUFFICIENT_SAMPLE (0 backoff events)
- Healthcheck [67]          PASS (latest_age=21s post-recheck; transient stale earlier)
- Healthcheck [74]          FAIL (missing PostOnly/max-pending samples blocks promotion)
- Healthcheck [40]          WARN (avg_net=-0.00bps, blocks Phase 2a t=0)
- Engine watchdog           PASS (demo 29.5s; paper expected dead; live_demo 31000s stale = pre-existing)

T+0 Phase 2a 14d observation: NOT YET READY (waits AC-A n>=30 + healthcheck [62] PASS @ 25%/15% AC-19)
T+0 expected ETA: 2026-05-20 (T+48h) at current 0.4 whitelist close/h velocity (demo only)
```

**Recommendation**: **EXTEND_MONITORING** — re-dispatch at **T+24h (2026-05-18 23:54 UTC)** for primary AC-A verdict on full 24h + healthcheck [62] sample maturity. Phase 1b activator mechanism field-verified (demo branch); fill-rate 0% must be investigated before Phase 2a graduation (likely cancel_grace_ms too short or symbol microstructure mismatch — separate IMPL ticket).

---

## §1 Executive Summary

| Dimension | Verdict | Key Number |
|---|---|---|
| **AC-A primary 24h demo** | INSUFFICIENT_SAMPLE | attempts=3/19 (15.79%), CI=[5.5%, 37.6%], lower<25% |
| **AC-A post-restart demo only (10.6h)** | PRELIMINARY PASS | attempts=3/3 (100%), CI=[43.85%, 100%], lower>25% |
| **AC-A combined demo+live_demo 24h** | INSUFFICIENT_SAMPLE + DILUTED | attempts=3/32 (9.38%), live_demo TOML=false by design |
| **AC-B fallback non-NULL** | PRELIMINARY PASS | 4/4 = 100% non-NULL (all timeout_taker) |
| **AC-C negative whitelist 0 attempt** | PASS | 4/4 halt_session, 0 attempt |
| **HC [62] close_maker_fill_rate** | INSUFFICIENT_SAMPLE | n=4 < min=30; fill_rate=0/4=0% in cell |
| **HC [63] fallback_audit** | INSUFFICIENT_SAMPLE | n=4 < min=5; null_rate=0%, enum=timeout_taker x4 (legal) |
| **HC [64] rate_limit_pause** | INSUFFICIENT_SAMPLE | 0 backoff + 0 global-pause events |
| **HC [65] reject_samples** | INSUFFICIENT_SAMPLE | n=4 < min=5; postonly=0, max_pending=0 |
| **HC [67] liquidation pulse** | PASS | latest_age=21s; n_rows=8068; cohort=25/25 (transient FAIL @12:34→PASS @12:35) |
| **Engine watchdog (demo)** | PASS | snapshot_age=29.5s; PID 1253085 uptime 7h |
| **Activator surface deployed** | CONFIRMED | binary mtime 04:11 UTC; use_maker_close=true in demo TOML only |
| **Live_demo activator status** | EXPECTED-OFF | risk_config_live.toml: use_maker_close=false（per AMD design; LiveDemo enabled on separate ticket）|

---

## §2 AC-A Raw Data + Wilson CI

### §2.1 Timing Reality

```
operator_brief_restart_utc   = 2026-05-17 23:54:36 (T+10.6h)
real_engine_pid              = 1253085 (NOT 1143103 in partial report)
binary_mtime                 = 2026-05-18 02:11 UTC (=04:11 +02 Linux local)
real_2nd_restart_utc         = 2026-05-18 03:20 (T+7.16h since 2nd rebuild)
api_uvicorn_pid              = 1253181 (uptime 7h12m)
now_utc                      = 2026-05-18 10:36 UTC
```

**Critical correction to partial report**: PID 1143103 已死，當前 engine PID = **1253085**，binary 在 2026-05-18 02:11 UTC 又 rebuild 一次（commit 92eb8b89 land + restart 機制 verify）。Activator binary 包含 `use_maker_close` symbol 4+ hits in `rust/target/release/openclaw-engine`.

### §2.2 Pre-restart Baseline (17:54-23:54 UTC pre-23:54:36 restart)

```sql
WHERE ts BETWEEN '2026-05-17 17:54:36' AND '2026-05-17 23:54:36' UTC
  AND engine_mode IN ('demo','live_demo')
  AND exit_reason IN (6 whitelist)
```

| engine_mode | closes | attempts | attempt_pct |
|---|---|---|---|
| demo | 11 | 0 | 0.00% |
| live_demo | 11 | 0 | 0.00% |

**Confirmed**: Activator off pre-restart (cold-default false) — matches E2 RCA.

### §2.3 Post-23:54:36 UTC Restart (10.6h)

```sql
WHERE ts > '2026-05-17 23:54:36' UTC
  AND engine_mode IN ('demo','live_demo')
  AND exit_reason IN (6 whitelist)
```

| engine_mode | closes | attempts | attempt_pct |
|---|---|---|---|
| demo | 3 | 3 | **100.00%** |
| live_demo | 2 | 0 | 0.00% (TOML disabled) |

**Detail rows** (UTC timestamps):
```
2026-05-18 01:51 live_demo FILUSDT grid_close_short attempt=f (TOML use_maker_close=false)
2026-05-18 01:56 live_demo POLUSDT grid_close_short attempt=f (TOML use_maker_close=false)
2026-05-18 03:45 demo      ARBUSDT grid_close_short attempt=t fallback=timeout_taker
2026-05-18 03:47 demo      OPUSDT  grid_close_short attempt=t fallback=timeout_taker
2026-05-18 04:21 demo      ARBUSDT grid_close_short attempt=t fallback=timeout_taker
```

### §2.4 Post-05:20 UTC Restart (2nd rebuild restart, 7.16h)

| engine_mode | closes | attempts | attempt_pct |
|---|---|---|---|
| demo | 3 | 3 | **100.00%** |
| live_demo | 0 | 0 | N/A |

All 3 demo whitelist closes attempt; LiveDemo had 0 whitelist closes in window.

### §2.5 24h Primary AC-A SQL (full window, mixed pre/post-restart)

```sql
WHERE ts > NOW() - INTERVAL '24 hours' AND engine_mode IN ('demo','live_demo')
```

| engine_mode | liquidity_role | attempts | exit_total | attempt_pct |
|---|---|---|---|---|
| demo | taker | 3 | 19 | 15.79% |
| live_demo | taker | 0 | 13 | 0.00% |

### §2.6 7d Primary AC-A SQL (aligned with healthcheck [62] window)

| engine_mode | liquidity_role | attempts | exit_total | attempt_pct |
|---|---|---|---|---|
| demo | taker | 3 | 142 | 2.11% |
| live_demo | taker | 0 | 123 | 0.00% |

### §2.7 Wilson 95% CI Verdict Matrix

| Scenario | n | x | p̂ | CI_lo | CI_hi | vs 25% | vs 50% |
|---|---|---|---|---|---|---|---|
| Demo post-23:54:36 (10.6h) | 3 | 3 | 100% | 43.85% | 100% | **PASS** | INSUFFICIENT |
| Demo+LiveDemo post-restart combined | 5 | 3 | 60% | 23.07% | 88.24% | INSUFFICIENT | INSUFFICIENT |
| Demo 24h | 19 | 3 | 15.79% | 5.52% | 37.57% | FAIL/INSUFFICIENT | FAIL/INSUFFICIENT |
| Demo+LiveDemo 24h | 32 | 3 | 9.38% | 3.24% | 24.22% | FAIL/INSUFFICIENT | FAIL/INSUFFICIENT |

**Verdict**: Demo-only post-restart 3/3 attempt rate 100% **passes 25% AC-A threshold** but sample n=3 is below conservative n=30 cutoff. **PRELIMINARY PASS pending n>=30 maturity**.

**Critical methodological correction for operator brief**: AC-A SQL `engine_mode IN ('demo','live_demo')` 結合 livedemo TOML `use_maker_close=false` 會 **dilute** demo-only signal。應改成 demo-only SQL 或在 spec 註明 livedemo cold-default expected baseline。

---

## §3 AC-B + AC-C Results

### §3.1 AC-B: Fallback Reason Distribution (close_maker_attempt=TRUE / 24h)

```
 close_maker_fallback_reason | cnt
-----------------------------+-----
 timeout_taker               |   4
(1 row)
```

| reason | count | % | is_safety_path | is_legal_enum |
|---|---|---|---|---|
| timeout_taker | 4 | 100% | false | true |

**Verdict**: PRELIMINARY PASS — non-NULL rate = 4/4 = 100% ≥ 90% AC threshold. All 4 are legal enum (per V094 CHECK constraint). However **n=4 < min_sample=5** for [63] healthcheck = INSUFFICIENT_SAMPLE.

**Anomaly call-out**: 100% timeout_taker fallback (0% maker_fill) is **operationally significant** — see §6.1 Findings.

### §3.2 AC-C: Negative Whitelist 0% Attempt

```
 engine_mode | exit_reason  | close_maker_attempt | cnt
-------------+--------------+---------------------+-----
 demo        | halt_session | f                   |   4
```

Detail rows (UTC):
```
2026-05-17 21:11:10 demo TRXUSDT halt_session attempt=f (pre-restart)
2026-05-17 21:11:36 demo TRXUSDT halt_session attempt=f (pre-restart)
2026-05-17 23:54:17 demo ATOMUSDT halt_session attempt=f (pre-restart by 19s)
2026-05-17 23:54:39 demo ATOMUSDT halt_session attempt=f (POST-restart by 3s)
```

**Verdict**: **PASS** — 4/4 halt_session 100% close_maker_attempt=FALSE。Critical: row at 23:54:39 UTC is **post-restart** (activator live), confirming negative whitelist gate works in activator-ON path (per commands.rs §91-103 Demo-only veto guard intact).

---

## §4 Healthcheck [62-65] + [67] Results

### §4.1 [62] close_maker_fill_rate (spec default 60/40 threshold)

```json
{
  "metric": "close_maker_fill_rate",
  "window_secs": 604800,
  "engine_modes": ["demo","live_demo"],
  "thresholds": {"min_sample": 30, "pass_lower": 0.6, "warn_lower": 0.4},
  "total_attempts": 4, "total_fills": 0,
  "cells": [{"engine_mode":"demo","n_attempts":4,"n_fills":0,"n_fallbacks":4,
             "fill_rate":0.0,"wilson_lower":0.0,"wilson_upper":0.0,
             "verdict":"INSUFFICIENT_SAMPLE"}],
  "verdict": "INSUFFICIENT_SAMPLE"
}
```

Relaxed re-run (--pass-lower 0.25 --warn-lower 0.10 --min-sample 3 --engine-mode demo):
```json
{ "fill_rate":0.0,"wilson_lower":0.0,"wilson_upper":0.4899,"verdict":"WARN" }
```

**Verdict**: INSUFFICIENT_SAMPLE at spec default; **WARN at AC-19 relaxed**. **fill_rate=0/4=0% is concerning** — see §6.1.

### §4.2 [63] close_maker_fallback_audit

```json
{
  "n_attempts": 4, "n_null_fallback_reason": 0, "null_rate": 0.0,
  "enum_distribution": [{"reason":"timeout_taker","count":4,"is_legal_enum":true}],
  "illegal_reasons": [],
  "verdict": "INSUFFICIENT_SAMPLE",
  "verdict_note": "n_attempts=4 < min_sample=5"
}
```

**Verdict**: INSUFFICIENT_SAMPLE — preliminary PASS on legal-enum + null-rate criteria but n<5.

### §4.3 [64] close_maker_rate_limit_pause_duration

```json
{
  "n_per_symbol_backoff_total": 0, "n_global_pause_total": 0,
  "verdict": "INSUFFICIENT_SAMPLE"
}
```

**Verdict**: INSUFFICIENT_SAMPLE — 0 rate-limit / pause events in 7d (expected at current low volume).

### §4.4 [65] reject_samples_healthcheck

```json
{
  "total_attempts": 4, "total_postonly_samples": 0, "total_max_pending_samples": 0,
  "cells": [{"engine_mode":"demo","n_attempts":4,"postonly_reject_samples":0,
             "max_pending_samples":0,"verdict":"INSUFFICIENT_SAMPLE"}],
  "verdict": "INSUFFICIENT_SAMPLE"
}
```

**Verdict**: INSUFFICIENT_SAMPLE — 0 PostOnly/max-pending samples (n<5). **Combined with [74] FAIL in passive_wait, this is operationally significant** — see §6.2.

### §4.5 [67] liquidation_pulse_freshness

Initial @ 12:34 (latest_age=379s):
```json
{ "freshness": "FAIL", "verdict": "FAIL", "note": "latest_age=379s > fail=300.0s" }
```

Re-run @ 12:35 (after new liquidation row landed):
```json
{ "freshness": "PASS", "verdict": "PASS", "note": "latest_age=21s",
  "n_rows": 8068, "buy_count": 7034, "sell_count": 1034, "cohort_coverage_pct": 100.0 }
```

**Verdict**: PASS post-recheck. **Transient FAIL @12:34 was natural sparse-traffic window** (12:28-12:35 only 3 liq rows, then 12:35:01 new row dropped latest_age to 21s). Writer healthy.

---

## §5 Engine Watchdog Status

```json
{
  "engine_alive": true,
  "snapshot_age_seconds": 29.5,
  "stale_threshold_seconds": 45.0,
  "engines": {
    "paper": {"alive": false, "age_seconds": 26048.2},
    "demo":  {"alive": true,  "age_seconds": 29.5},
    "live":  {"alive": false, "age_seconds": 31004.7}
  }
}
```

| Engine | Status | Note |
|---|---|---|
| demo | PASS alive 29.5s | 1.5× headroom under 45s threshold |
| paper | expected dead | `OPENCLAW_ENABLE_PAPER=0` per project memory |
| live (live_demo) | dead 31004s (8.6h) | **pre-existing P1** in `project_live_auth_watcher_event_consumer_spawn`; LiveDemo pipeline never spawned in restart; passive_wait [56] FAIL confirms `authorization_json_missing` |

---

## §6 Findings + Anomalies

### §6.1 PHASE 1B PRIMARY FINDING: maker fill_rate = 0% (4/4 timeout_taker)

**Evidence**:
- 4/4 demo whitelist close attempts → `close_maker_fallback_reason = timeout_taker`
- 0 maker fills, 0 PostOnly reject samples, 0 max-pending samples
- 100% fall through to taker via cancel_grace timeout

**Hypotheses**:
1. **cancel_grace_ms set too short** — maker order placed but cancelled-to-taker before fill or before PostOnly reject path
2. **Symbol microstructure mismatch** — ARBUSDT/OPUSDT depth/spread incompatible with maker-first at chosen offset
3. **Maker queue position** — orders not reaching top of book within grace window
4. **Order flow logic** — possible misimplementation of maker-first path (not just timeout)

**Acceptance impact**:
- AC-A attempt-rate passes per spec (3/3 100% in demo post-restart)
- AC-B fallback-reason non-NULL passes per spec (4/4 legal enum)
- **But operational maker conversion 0%** = activator achieves "attempt" intent but no real cost saving yet
- Phase 2a 14d observation should NOT start until [62] sample matures to verify fill_rate trend; else 14d observation will document a 0% maker-conversion state which is not what AMD §8 acceptance ladder targets

### §6.2 [74] FAIL: missing PostOnly/max-pending samples

```
[74] close_maker_reject_samples — demo: attempts=4, postonly_reject_samples=0,
     max_pending_samples=0, verdict=FAIL — missing PostOnly or max-pending reject
     samples blocks promotion
```

**Interpretation**: After 4 attempts in 7d, **0** PostOnly veto events + **0** max-pending events recorded. Combined with §6.1 (100% timeout_taker), this suggests:
- Maker order **never reaches** PostOnly veto path (i.e., not even ack'd as PostOnly limit before timeout)
- Maker order **never reaches** max-pending state (insufficient depth at limit price?)
- The cancel_grace_ms timeout fires **before** any liquidity event

**Action**: separate E1 ticket to instrument maker-place → PostOnly-ack → cancel timeline (need order_id-level trace with grace_ms boundary log).

### §6.3 Live_demo activator gating (PRELIMINARY PASS but spec ambiguity)

`risk_config_live.toml:use_maker_close=false`（per comment: "Phase 2b LiveDemo 啟用為獨立 IMPL ticket，本 AMD 不在此回放寬"）。LiveDemo whitelist closes (2 rows) correctly NOT attempted. Operator's combined-SQL AC-A reports false 9.38% — should be demo-only.

**Action**: PA + spec author check AMD-2026-05-15-02 §4.1 AC-A SQL scope: should be `engine_mode = 'demo'` only, not `IN ('demo','live_demo')`, until LiveDemo ticket activates.

### §6.4 [40] WARN realized_edge_acceptance avg_net=-0.00bps

```
[40] WARN — 24h MLDE rows=53325, win_rate=0.0%, avg_net=-0.00bps (target>5.0);
     maker_like=96.7% (target>=50%), fee_drop=95.8% (target>=60%) — avg_net -0.00bps <= target
```

P0-EDGE-1 textbook-alpha-deficient state continues. This is **NOT Phase 1b regression** but it directly blocks Phase 2a 14d observation t=0 (per memory `project_2026_05_10_sprint_n0_closure` Phase 2a graduation criteria includes positive edge signal).

### §6.5 [56] FAIL live_pipeline_active (pre-existing P1)

```
[56] FAIL — live pipeline expected endpoint=live_demo but auth=authorization_json_missing
     path=/home/ncyu/BybitOpenClaw/secrets/secret_files/bybit/live/authorization.json
```

**Pre-existing** in `project_live_auth_watcher_event_consumer_spawn`; restart 不重 spawn LiveDemo; not Phase 1b regression. Counts against [42b], [56], [70-72] sample-maturity since LiveDemo not running. Operator should renew via signed live-auth route.

### §6.6 [42b] FAIL attribution_drift_query_timeout

```
[42b] attribution-ratio query failed: canceling statement due to statement timeout
```

PG perf issue, **not Phase 1b**. May correlate with attribution_chain audit cardinality post-Sprint N+0 (per memory `project_2026_05_10_sprint_n0_closure` 'attribution_chain_ok 0.5%→100%' so query rows ↑↑↑).

### §6.7 API endpoint partial outage (NEW finding)

```
HTTP 500 /openapi.json
HTTP 200 /docs
HTTP 404 /api/v1/system/services/status
HTTP {detail:reason:internal_error} /openapi.json (body)
```

API uvicorn 200 to /docs and 307 to /console root, but /openapi.json returns internal_error. **Pre-existing**: smoke 1 health endpoint未確認 path; passive_wait_healthcheck [49][50][53] all PASS suggests core DB writers + replay still active. **Not Phase 1b regression** but should be filed for E3.

---

## §7 Recommendation (PM)

### §7.1 Phase 2a 14d Observation Clock t=0

**DO NOT START** Phase 2a t=0 yet. Three gates pending:

1. **AC-A sample maturity**: demo whitelist attempts ≥30 (currently n=3 post-restart 10.6h; ETA T+72-120h at current 0.4 close/h velocity if weekday volume returns)
2. **HC [62] fill_rate**: currently 0% (4/4 timeout_taker) — must investigate root cause (cancel_grace_ms? microstructure?) before observation
3. **HC [40] edge gate**: currently avg_net=-0.00bps; P0-EDGE-1 still active

### §7.2 Re-dispatch Schedule

| Window | Action | Owner |
|---|---|---|
| **T+24h (2026-05-18 23:54 UTC)** | QA re-dispatch full AC-A/B/C + HC [62-65] (sample maturity check) | PM main |
| **T+48h (2026-05-19 23:54 UTC)** | QA re-dispatch + Wilson CI lower-bound verdict at n>=15 | PM main |
| **T+72h (2026-05-20 23:54 UTC)** | If n>=30 → primary AC-A verdict + Phase 2a t=0 GO/NO-GO sign-off | PM main + Operator |
| **T+ASAP** | E1 ticket: maker fill_rate 0% RCA (cancel_grace_ms / microstructure / order timeline) | PM main → E1 |
| **T+ASAP** | PA ticket: AC-A SQL scope clarification (demo-only vs demo+live_demo dilution) | PM main → PA |

### §7.3 Non-Blockers (Pre-existing, escalate via owner)

- LiveDemo pipeline absent / `[56]` FAIL: operator renew authorization.json via signed route
- `[42b]` attribution query timeout: filed against E3 (PG perf / cardinality)
- API /openapi.json internal_error: filed against E3 (FastAPI routing)
- `[40]` avg_net=-0.00bps: P0-EDGE-1 root closure pending Phase B/C/D + A群 work (per Sprint N+0 closure)

### §7.4 Activator Surface CONFIRMED DEPLOYED

- ✅ Binary mtime 2026-05-18 02:11 UTC (Linux 04:11 +02)
- ✅ `use_maker_close` symbol embedded in `rust/target/release/openclaw-engine`
- ✅ TOML: `risk_config_demo.toml: use_maker_close = true`, `live = false`, `paper = false`, global default `false`
- ✅ Cold-default false honored (pre-restart 22/22 closes attempt=false)
- ✅ Demo-only veto guard intact (post-restart halt_session 0 attempt; live_demo whitelist 0 attempt)
- ✅ Activator triggers on demo whitelist closes (3/3 post-restart attempt=true)
- ⚠ Maker conversion 0% — need follow-up RCA (§6.1, §6.2)

### §7.5 Verdict

```
QA E2E ACCEPTANCE: PARTIAL PASS / EXTEND_MONITORING / 1 INVESTIGATION TICKET
```

- **No new BLOCKER for activator surface itself**
- **AC-A demo-only mechanism passes 100% on n=3 (CI lower 43.85% > 25% AC-19 conservative)**
- **AC-B 100% non-NULL legal enum passes mechanism**
- **AC-C 100% 4/4 halt_session守住 PASS**
- **Maker fill_rate 0% must be investigated as **operational** finding before Phase 2a t=0** — not deploy-blocker but observation-window-prerequisite

---

## §8 Boundary Adherence Confirmation

QA mandate boundary 全條 ✅:
- ✅ Verify business chain (5 stage + smoke + cross-module)
- ✅ Read-only verification (PG SELECT, healthcheck --report, watchdog --status, curl read)
- ✅ Did NOT modify prod config / TOML / migrations
- ✅ Did NOT commit / push / restart
- ✅ Did NOT enable production deploy or runtime parameter change
- ✅ Did NOT dispatch downstream agent
- ✅ Single QA agent dispatch (no cascading sub-agent)
- ✅ All raw SQL output preserved verbatim
- ✅ Wilson CI computed locally per spec convention
- ✅ Discrepancies between operator prompt elapsed (T+10.6h since 23:54:36) vs real binary mtime (04:11 UTC = 02:11 UTC binary stamp suggests 2nd rebuild after partial QA) flagged transparently

---

**QA E2E ACCEPTANCE DONE: PARTIAL PASS / EXTEND_MONITORING** · report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-18--phase_1b_24h_post_deploy_verification_update.md`

**Recommendation to PM**:
1. **Re-dispatch QA at T+24h** (2026-05-18 23:54 UTC) for primary AC-A verdict on full day + sample maturity
2. **Open E1 RCA ticket**: maker fill_rate 0% (4/4 timeout_taker, 0 PostOnly/max-pending samples) — investigate cancel_grace_ms / microstructure / order placement timing
3. **Open PA ticket**: AMD AC-A SQL scope — clarify demo-only vs demo+live_demo to prevent live_demo cold-default dilution of demo-only signal
4. **Phase 2a 14d observation t=0**: NOT YET — wait n>=30 demo attempts + [62] fill_rate trend visibility + [40] edge gate posture
5. **No deploy-blocker found**: activator surface CONFIRMED LIVE; mechanism (attempt+fallback path) functioning per spec; need fill_rate investigation as operational follow-up
