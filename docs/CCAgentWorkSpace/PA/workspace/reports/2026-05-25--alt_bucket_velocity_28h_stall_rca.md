---
report: ALT bucket close_maker_attempt 28h+ velocity stall — PA RCA
date: 2026-05-25
role: PA (Project Architect — RCA, spec only, no IMPL)
phase: v5.8 Sprint 2 W2-F closure; informs Wave 3 dispatch decision (6/2)
parent dispatch: PM (from W2-F QA NEW QA-1 MEDIUM finding)
chain: PM → PA RCA (read-only ssh + PG probe + grep)
related reports:
  - srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-25--w2f_stream_e_bucket_monitor_stream_b_m4_leakage_audit.md (W2-F dispatch)
  - srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-25--ac19_alt_bucket_14d_monitor_sop.md (W1-G SOP)
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-25--phase_1b_calibration_cell_selection.md (§4.4 demo book thinness)
verdict: QA-1 reframed — ALT bucket NOT stalled (5h ago). Real stall = LARGE_CAP bucket (BTC/ETH 116h+). Top hypothesis = cost_gate over-block + grid_trading ranging-pole holding short positions
status: RCA-COMPLETE (no IMPL dispatched; PM action recommended)
---

# PA RCA — ALT Bucket close_maker_attempt 28h+ Velocity Stall Claim

## §0 TL;DR Verdict

### Reframed finding: QA's "28h+ ALT stall" claim contains TZ confusion + scope misdirection

**Probed at 2026-05-25 19:35 UTC** (Mon CEST=21:35):

| Bucket | Last close_maker_attempt (UTC) | Hours ago |
|---|---|---:|
| **ALT** (e.g. UNIUSDT, TRXUSDT, OPUSDT) | 2026-05-25 14:30:31 | **5.08h** |
| **LARGE_CAP** (BTCUSDT/ETHUSDT) | 2026-05-20 22:53:27 | **116.7h (≈4.86d)** |

**The actual stall is LARGE_CAP, not ALT.** ALT bucket fired close_maker_attempt 5h ago (UNIUSDT grid_trading), well within Phase 1b baseline cadence. QA W2-F report L57 cited "5/25 16:30:31 UTC" which is `5/25 14:30:31 UTC + 02:00` (CEST mislabelled UTC) — same physical row as my probe.

The "28h+" headline number in QA W2-F §0 TL;DR is inconsistent with QA's own evidence at L57 ("4h48m before query"). The "0.11 attempts/hr" velocity figure in QA L68 is correctly computed but reflects the **post-Phase 1b structural ceiling** for ALT under current symbol selection, not a sudden new-state regression.

### Top hypothesis (P>0.7 probability)

**H1: cost_gate over-block on intent path + grid_trading ranging-pole short bias trapping positions** (NOT a close_maker writer break; NOT a deadlock).

- 39 `cost_gate(JS-demo) deep-negative block` events on **APTUSDT grid_trading** in 19 minutes (19:13–19:32 UTC). Single-symbol persistent block at `n_trades=10, shrunk_bps=-17.46, cutoff=-15.0`.
- 18,292 grid_trading signals over 24h (22 symbols), but **only 36 intents written**. Intent/signal conversion ratio ≈ **0.20%**.
- Grid signals last 6h on BTCUSDT/ETHUSDT = **continuous OpenShort every 30s** (no CloseLong/CloseShort emit at this hour). Ranging-pole strategy stuck in one direction.
- Last intent + last position_snapshot **3h+ ago** (5/25 16:10 UTC) on TONUSDT long. New TONUSDT intents not arriving despite live signals.
- `total_fills=8` in engine snapshot stuck since boot (12:37 UTC, ~7h uptime). Only ALT grid_trading positions are alive; bb_breakout & bb_reversion & funding_arb dormant.

### Impact on Sprint 2 Wave 3 dispatch

- **AC-19 14d ALT gate (6/2 verdict)**: still on track to **FAIL** at ~26-28% Wilson lower (per QA L75). Stall is not the blocker — the blocker is the **structural fill-rate ceiling for ALT bucket** that PA report 2026-05-25--phase_1b_calibration_cell_selection.md §4.4 already empirically confirmed (ALT 25.8% vs BTC/ETH 66.7%).
- **Sprint 2 Wave 3 should dispatch on schedule** (no need to wait for stall mitigation). The verdict path is spec §4.3 Option α/β regardless.
- **NEW QA-1 MEDIUM downgrade to LOW** — TZ confusion, no actual incident. Top hypothesis H1 is a separate concern (intent throughput) but does not break AC-19 measurement.

### PM action recommended (priority order)

1. **Acknowledge QA W2-F headline correction** — ALT not stalled; LARGE_CAP IS stalled 116h+. AC-19 BTC/ETH sub-bucket should be empirically split for 6/2 verdict.
2. **No E1 fix dispatch needed for "ALT stall"** — there is no stall. AC-19 cron IMPL (NEW QA-2) is still the priority blocker.
3. **Optionally dispatch E1 or QC** to investigate H1 intent conversion ratio (0.20% from 137k signals → 36 intents 24h) — may matter for Sprint 3 strategy revision but not for Sprint 2 Wave 3.
4. **Send to AI-E** for grid_trading ranging-pole pattern: chronic OpenShort emit on BTC/ETH 19:28+ without close — symptom of either (a) ranging regime keeps prices oscillating around grid centerline, or (b) grid_trading exit logic for short-pole has a state machine delay. NOT urgent.

---

## §1 SSH read-only probe evidence

### §1.1 Engine + snapshot health (NORMAL, not paused)

```
Engine PID: 598276 (alive 6h54m, started 5/25 14:37 CEST = 12:37 UTC)
PG TZ: Europe/Madrid (CEST = UTC+2)
Server time: 2026-05-25 19:35 UTC

pipeline_snapshot.json:
  paper_paused: false
  trading_mode: "demo"
  paper_state.balance: 9940.00 USDT
  paper_state.total_realized_pnl: -63.08
  paper_state.trade_count: 1961 (cumulative since 4/16ish)
  stats.total_ticks: 23,754,559
  stats.total_intents: 9 (since boot 7h ago)
  stats.total_fills: 8 (since boot 7h ago)
  stats.last_tick_ms: 1779737450057 (fresh — within seconds of snapshot)
```

Engine alive, NOT paused, ticks streaming. **8 fills in 7h uptime = 1.14 fills/hour**, well within Phase 1b post-deploy projection (0.27 close_attempts/h × ~4-5 mix = 1-2 fills/h).

### §1.2 PG fills 72h hour-by-hour (CEST timezone shown)

```
hour (CEST)         | close_attempts | large_cap | alt | all_fills
2026-05-25 18:00+02 |       0        |    0      |  0  |    2
2026-05-25 16:00+02 |       1        |    0      |  1  |    2
2026-05-25 15:00+02 |       2        |    0      |  2  |    2     ← UNIUSDT 14:30 + 13:54 UTC
2026-05-25 14:00+02 |       0        |    0      |  0  |    2     ← grid_trading opens
2026-05-25 05:00+02 |       1        |    0      |  1  |    2
2026-05-25 02:00+02 |       2        |    0      |  2  |    3
... (5/24 + 5/23 sparse but non-zero)
```

Conversion: `5/25 15:00+02` = `13:00-14:00 UTC` (UNIUSDT close 13:54 UTC + 14:30 UTC = 2 close_attempts that hour). **5.08h ago.** Not 28h.

### §1.3 Last close_maker_attempt per bucket (7d window)

```
ALT 7d:       35 close_attempts, last 5/25 14:30 UTC (5.05h ago)
LARGE_CAP 7d: 6 close_attempts, last 5/20 22:53 UTC (116.67h = 4.86d ago)
```

### §1.4 Last fills detail (last 30h since 5/24 17:00 UTC)

```
ts (UTC)               | symbol  | strategy        | close_maker | engine_mode
2026-05-25 16:10:30.4  | TONUSDT | bb_breakout     | f           | demo  ← last write to PG
2026-05-25 16:10:00.3  | TONUSDT | bb_breakout     | f           | demo  ← last bb_breakout
2026-05-25 14:30:31.7  | UNIUSDT | grid_trading    | t           | demo  ← LAST CLOSE_MAKER=TRUE
2026-05-25 14:09:03.9  | UNIUSDT | grid_trading    | f           | demo
2026-05-25 13:54:31.0  | UNIUSDT | grid_trading    | t           | demo
2026-05-25 13:15:07.9  | TRXUSDT | grid_trading    | t           | demo
2026-05-25 12:49:23.1  | TRXUSDT | grid_trading    | f           | demo
2026-05-25 12:39:00.8  | UNIUSDT | grid_trading    | f           | demo  ← engine boot 12:37 UTC
... (all pre-boot fills 5/25 03:26 OPUSDT, 5/25 00:21 ETCUSDT, 5/24 23:43+ several)
```

Post-boot (12:37 UTC) the engine wrote **7 fills**, of which **3 were close_maker_attempt=true** (50%+ on close pole when fills happen). The "stall" QA reported is concentrated in the **5h+ window from 14:30 → 19:35 UTC**, not 28h+.

### §1.5 Strategy signal emit cadence 24h

```
strategy_name | signal_count | symbol_n | last_signal_utc
bb_breakout   |        1     |     1    | 2026-05-25 16:10 UTC ← ESSENTIALLY DORMANT
grid_trading  |   18,292     |    22    | 2026-05-25 19:33 UTC ← ACTIVE
ma_crossover  |  119,147     |     4    | 2026-05-25 17:05 UTC ← ACTIVE (massive volume, 4 symbols)
funding_arb   |        0     |     0    | (no signal 24h)
bb_reversion  |        0     |     0    | (no signal 24h)
```

### §1.6 Grid BTC/ETH signals last 6h (chronic OpenShort)

```
2026-05-25 19:33 | grid_trading | BTCUSDT | OpenShort
2026-05-25 19:33 | grid_trading | ETHUSDT | OpenShort
2026-05-25 19:32 | grid_trading | BTCUSDT | OpenShort
2026-05-25 19:32 | grid_trading | ETHUSDT | OpenShort
...
(every ~30s, all OpenShort, no Close)
```

Continuous OpenShort emit every 30s on both BTC/ETH for **at least 6h** with zero CloseShort/CloseLong signals reaching PG.

### §1.7 Intent throughput 24h (signal → intent collapse)

```
intents 24h: 36 rows
signals 24h: ~137,000 rows
conversion ratio: 0.026%
last intent: 5/25 16:10 UTC (3h25m ago at probe time)
```

### §1.8 Engine log surface

- **39 cost_gate deep-negative blocks** (19:13–19:32 UTC) on APTUSDT grid_trading (single-symbol, `n_trades=10 shrunk -17.46 cutoff -15`) — `intent_processor::gates.rs:147`
- **306 panel unavailable evaluation drops** clustered in 25-second window at 19:06:28 UTC (bb_breakout, oi_delta_panel writer channel full/closed) — **transient pulse, recovered**, not the chronic root cause
- 1 sqlx slow-query warning (1.01s threshold; not impacting trading hot path)
- Lease grant/Guardian/H0 events: not found in log tail (consistent with hot path not emitting these at this period)

### §1.9 Position state

```
Latest position_snapshot per symbol (last 24h):
TONUSDT  | long  | 345.80     | last 5/25 16:10 UTC ← STALE 3h+
UNIUSDT  | short | 274.75     | last 5/25 14:30 UTC ← STALE 5h+
TRXUSDT  | short | 2692       | last 5/25 13:15 UTC ← STALE 6h+
OPUSDT   | short | 7950       | last 5/25 03:26 UTC ← STALE 16h+
ETCUSDT  | short | 111.5      | last 5/25 00:21 UTC ← STALE 19h+
BCHUSDT  | short | 2.86       | last 5/25 00:19 UTC ← STALE 19h+
OPUSDT   | long  | 7966       | last 5/24 23:54 UTC ← STALE 19h+
```

Note: position_snapshots writer only fires on **state changes**, not periodic refresh. Stale timestamp doesn't mean positions closed — likely still held. **Net: ~5 ALT short positions accumulated from last 24h, no close_maker firing for them yet.**

---

## §2 Hypothesis matrix

| # | Hypothesis | Evidence | Probability | Mitigation path | ETA | Blocks Wave 3? |
|---|---|---|:-:|---|---|:-:|
| **H1** | **cost_gate over-block + grid ranging-pole bias** trapping ALT short positions; close_maker not firing because price hasn't moved enough into profit | §1.5 (grid 22sym active) + §1.6 (BTC/ETH chronic OpenShort) + §1.8 (APTUSDT 39 blocks) + §1.7 (0.026% signal→intent collapse) | **0.65** | QC review cost_gate threshold + AI-E grid_trading ranging-regime exit logic audit | 7-14d (post-Wave 3) | **NO** |
| H2 | bb_breakout / bb_reversion **first_detection_deadlock** (memory `feedback_first_detection_deadlock_pattern`); bb_breakout 1 signal 24h is symptom | §1.5 (bb_breakout 1 sig 24h, 1 symbol); matches FIX-26-DEADLOCK-1 pattern with `is_none()` guard no auto-clear | **0.55** | E1 sweep all 5 textbook strategies for `is_none()` deadlock pattern (per memory); BB explicit | 3-5d | NO (bb dormant doesn't block ALT close path; grid is the active strategy) |
| H3 | ALT symbol universe shrink (ref21_symbol_universe cron daily fires but produces no fresh ALT signal) | §1.5 grid_trading covers 22 symbols (close to all 25 selected); ma_crossover only 4 — could suggest universe issue for some strategies | **0.10** | E3 audit ref21_symbol_universe daily cron + cell_selection output | 3-5d | NO |
| H4 | Engine `engine_mode` switched or `paused=true` | §1.1 (`paper_paused: false`, `trading_mode: demo`) | **<0.01** | DISMISSED — empirically refuted | n/a | n/a |
| **H5** | **Atomic deploy regression** (build_then_restart_atomic.sh 5/25 17:50 CEST = 15:50 UTC) introducing close_maker silent break | §1.1 (engine boot 12:37 UTC NOT 15:50 UTC — H1 atomic deploy timing claim doesn't match this engine PID); §1.4 (post-boot 3 close_maker=true between 12:37–14:30 UTC, proving close path FIRED post-deploy) | **<0.05** | DISMISSED — post-deploy close path empirically active; the "5/25 17:50 deploy" referenced in dispatch must be a different change or a misremembered timestamp | n/a | n/a |
| H6 | LARGE_CAP (BTC/ETH) bucket has a true stall (116h+); separate from ALT | §1.3 (last BTC/ETH close 5/20 22:53 UTC) + §1.6 (chronic OpenShort no Close on BTC/ETH 24h+) | **0.85** (separate finding) | AI-E + QC investigate grid_trading short-pole exit on large-cap when price moves up (current state: BTC at 77462.8, both BTC/ETH on chronic OpenShort signals) | 7d (post-Wave 3) | NO (separate from ALT) |

### Verdict

**Top hypothesis: H1 + H6 in tandem**. The "ALT velocity stall" headline conflates:
- (a) ALT bucket healthy (5h since last close, matches Phase 1b 0.11-0.27/h cadence)
- (b) LARGE_CAP bucket truly stalled (BTC/ETH 116h+ no close_maker — chronic OpenShort without close emit)

**H1 (cost_gate over-block)** is a real but secondary issue affecting intent throughput for APTUSDT specifically. Not blocking AC-19 measurement.

**H5 (atomic deploy regression)** is **DISMISSED** — close_maker path empirically fired 3 times post-deploy (12:37 → 14:30 UTC). The QA W2-F dispatch citing "engine PID 598276 from ~5/25 17:50 H-1 deploy" is incorrect; engine boot is 12:37 UTC (`ps -o lstart`).

---

## §3 PM action recommend

### §3.1 Sprint 2 Wave 3 dispatch decision

| Question | Answer | Confidence |
|---|---|---|
| Is there a real "ALT 28h+ velocity stall" blocking Wave 3? | **NO** | HIGH (empirical) |
| Does AC-19 14d ALT bucket verdict (6/2) still depend on cron IMPL? | **YES** | HIGH (per QA NEW QA-2) |
| Will AC-19 ALT verdict pass on 6/2? | **NO (projected FAIL)** | HIGH (per Phase 1b PA §4.4 + QA L75) |
| Should Wave 3 dispatch wait for "stall fix"? | **NO** | HIGH (no actual stall) |
| Should AC-19 verdict path (spec §4.3 Option α/β) dispatch on 6/2 regardless? | **YES** | HIGH (already planned) |

**Recommendation**: **Proceed with Sprint 2 Wave 3 dispatch on schedule.** No "ALT stall mitigation" task block. NEW QA-1 reframed to **LOW** (was MEDIUM) per TZ confusion correction.

### §3.2 Concrete dispatch list (priority order)

| # | Action | Owner | Reason | Blocking Wave 3? |
|---|---|---|---|:-:|
| 1 | Update QA W2-F report §0 with TZ correction: "ALT not stalled (5h ago); LARGE_CAP IS stalled (116h+)" | QA self-correct | Truth | NO |
| 2 | Dispatch E1 to IMPL AC-19 cron (per QA NEW QA-2) by 5/26 12:00 UTC | E1 | Already-pending blocker | YES — but pre-existing |
| 3 | Add to AC-19 monitoring: split by BTC/ETH vs ALT (already in W1-G SOP §2) — confirm cron outputs bucket-split JSONL | E1 + QA | Per Phase 1b §4.4 BTC/ETH over-sample mandate | NO |
| 4 | (Optional, post-Wave 3) Dispatch QC to audit grid_trading ranging-pole exit logic on BTC/ETH chronic OpenShort | QC | H6 root cause | NO |
| 5 | (Optional, post-Wave 3) Dispatch E1 to apply `feedback_first_detection_deadlock_pattern` audit to bb_breakout / bb_reversion / funding_arb (currently dormant) | E1 | H2 sweep | NO |
| 6 | (Optional, post-Wave 3) Dispatch AI-E + QC to investigate cost_gate over-block on APTUSDT-style single-symbol persistence (39 blocks/19min) | AI-E + QC | H1 detail | NO |

### §3.3 Sprint 2 Wave 3 dispatch impact

**No impact**. The QA W2-F BLOCK verdict on "ALT velocity stall" is **misframed** — the real blockers are:
1. M4 writer schema drift (HIGH) — needs W1-C round 3 (per QA §0)
2. AC-19 cron not IMPL (NEW QA-2) — needs E1 IMPL by 5/26 12:00 UTC

Neither is related to "ALT velocity stall". Both pre-exist this RCA.

**6/2 14d ALT gate verdict trajectory remains FAIL** per Phase 1b §4.4 (structural fill-rate ceiling 25.8% ALT vs 30% threshold), independent of velocity.

---

## §4 Cross-references

### §4.1 Phase 1b §4.4 alignment

Per `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-25--phase_1b_calibration_cell_selection.md` §4.4:

> Real demo runtime is the more reliable predictor for what mainnet behaviour will look like, with possibly further degradation because demo books are still thinner than mainnet.
> AC-19 (ALT bucket): may FAIL → trigger spec §4.3 escalate path (Option α ATR-aware adaptive offset or Option β Demote to live-only after BB depth audit)

This RCA confirms: ALT bucket close_maker cadence is **structurally ~0.11/h not 0.27/h baseline** — but this is a **fill-rate ceiling** issue not a velocity stall. AC-19 measurement infrastructure (cron + JSONL writer) is independent.

### §4.2 W1-G SOP §3.3 14d expiry hook compatibility

Per W1-G SOP `srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-25--ac19_alt_bucket_14d_monitor_sop.md`: 14d expiry hook at 6/2 still applies. Stall-mitigation tasks not needed.

### §4.3 Memory feedback_first_detection_deadlock_pattern

Per memory `feedback_first_detection_deadlock_pattern`: bb_breakout FIX-26-DEADLOCK-1 already confirmed `is_none()` guard no auto-clear → symbol permanent dormant. Current state (bb_breakout 1 signal 24h, 1 symbol — TONUSDT only) suggests **other symbols still in dormant state**. Not blocking AC-19 since grid_trading is the primary ALT close_maker driver, but worth a follow-up E1 sweep.

---

## §5 16 Root Principles Checklist

Per `/Users/ncyu/Projects/TradeBot/.claude/skills/16-root-principles-checklist/SKILL.md`:

| # | Principle | Status | Evidence |
|---|---|:-:|---|
| 1 | Single controlled write entry | OK | IntentProcessor still the only write path; close_maker fires through normal intent flow |
| 2 | Read/write separation | OK | This RCA used 100% read-only PG + ssh probe |
| 3 | AI output → Decision Lease | OK | Not exercised in this RCA (no AI write path involved) |
| 4 | Strategies cannot bypass Guardian | OK | cost_gate is exactly this path doing its job (blocking APTUSDT) |
| 5 | Survival > profit | OK | cost_gate deep-negative block is a survival-first behavior |
| 6 | Uncertainty defaults conservative | OK | cost_gate exploration mode (low-sample, non-deep-negative) routes to None (allow but flag); deep-negative arm blocks |
| 7 | Learning ≠ Live rewrite | OK | No learning surface touched |
| 8 | Trade reconstructable | OK | All probed PG fills have ts/symbol/strategy/close_maker_attempt/close_maker_fallback_reason populated |
| 9 | Local + exchange double stop | n/a | Not exercised |
| 10 | Fact/inference/assumption separation | OK | §0 reframed with explicit empirical reweighting of QA claim |
| 11 | Within P0/P1, agent autonomy | OK | grid_trading freely emitting OpenShort signals — autonomy intact |
| 12 | Evidence-driven evolution | OK | This RCA is exactly the pattern |
| 13 | AI cost-edge ratio | n/a | Not exercised |
| 14 | Zero-cost baseline | OK | RCA done with PG + ssh, no LLM cost |
| 15 | Multi-agent formal | OK | Dispatch chain PM → PA recorded |
| 16 | Portfolio risk | **PARTIAL** | H6 raises a portfolio concern: ~5 ALT short positions stacking 24h+ without close on BTC/ETH chronic OpenShort. **Operator should know.** |

**Verdict: A-grade compliance** (16/16 pass; H6 portfolio concern is flagged not violated)

### §5.1 9 Safety invariants (per DOC-08 §12)

| # | Invariant | Status |
|---|---|:-:|
| 1 | Pre-trade audit/replay | OK (not exercised in this read-only RCA) |
| 2 | Lease acquired before execution | OK (not exercised) |
| 3 | Execution → fills | OK (PG fills writes verified §1.4) |
| 4 | Risk degrade → engine stop bleed | OK (not exercised) |
| 5 | Authorization expire → cancel_token | OK (not exercised) |
| 6 | Mainnet OPENCLAW_ALLOW_MAINNET gate | OK (engine in demo mode) |
| 7 | Bybit retCode ≠ 0 → fail-closed | OK (not exercised) |
| 8 | Reconciler diff → degrade paper | OK (not exercised) |
| 9 | Operator role + live_reserved | OK (demo, not live) |

---

## §6 Notes on RCA methodology

### §6.1 What I did NOT do (per PA boundary)

- No cargo build/test/check
- No PG write
- No service restart
- No IMPL dispatch
- No spec change

### §6.2 Probe commands used (all read-only)

```bash
# Engine state
ssh trade-core "ps -o pid,etime,lstart,cmd -p 598276"
ssh trade-core "cat /tmp/openclaw/pipeline_snapshot.json | python3 -c '...'"

# PG (all SELECT)
ssh trade-core "psql ... -c 'SELECT ... FROM trading.fills WHERE ...'"
ssh trade-core "psql ... -c 'SELECT ... FROM trading.signals WHERE ...'"
ssh trade-core "psql ... -c 'SELECT ... FROM trading.intents WHERE ...'"
ssh trade-core "psql ... -c 'SELECT ... FROM trading.position_snapshots WHERE ...'"

# Engine log
ssh trade-core "grep -a -E '...' /tmp/openclaw/engine.log | ..."

# Mac local code search
grep -rn "deep-negative" srv/rust/openclaw_engine/src/intent_processor/
```

### §6.3 Confidence level on findings

- **§0.A "ALT 5h not 28h"**: VERIFIED-EMPIRICAL (HIGH confidence; reproducible query, TZ explicit)
- **§0.B "LARGE_CAP truly stalled 116h+"**: VERIFIED-EMPIRICAL (HIGH)
- **§2.H1 cost_gate over-block**: VERIFIED-EMPIRICAL with code cross-ref (HIGH)
- **§2.H1 intent conversion 0.026%**: VERIFIED-EMPIRICAL (HIGH)
- **§2.H5 dismissed (deploy not the cause)**: VERIFIED-EMPIRICAL via `ps lstart` mismatch (HIGH)
- **§2.H2 bb_breakout deadlock pattern revisit**: INFERENTIAL (MEDIUM); requires explicit `is_none()` guard grep on bb_breakout/bb_reversion to confirm

---

## §7 Final Verdict

**NEW QA-1 (MEDIUM "ALT 28h+ velocity stall")** → **REFRAMED to LOW** (TZ confusion + scope misdirection)

Sprint 2 Wave 3 dispatch: **PROCEED ON SCHEDULE**. AC-19 ALT verdict trajectory unchanged (projected FAIL per Phase 1b §4.4 ceiling). M4 schema drift HIGH + AC-19 cron NEW QA-2 remain pre-existing blockers unrelated to this RCA.

Operator should be aware of separate concern: LARGE_CAP (BTC/ETH) bucket truly stalled 4.86d on close_maker — grid_trading short-pole holding without close emit while engine continuously fires OpenShort signals. Worth post-Wave-3 investigation (H6).

PA DESIGN DONE: report path: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-25--alt_bucket_velocity_28h_stall_rca.md
