---
title: "ENGINE-HEAL-FUP-2 Post-Mortem — Live Pipeline Lagging → Fix 4 Self-Cancel"
date: 2026-04-15
author: Claude Opus 4.6 (PM+Conductor)
status: investigation complete, remediation proposed
inputs:
  - /tmp/openclaw/engine_logs/engine-1776244436.log (18MB, 79,866 lines, 23:56:36 → 02:03:05 UTC)
---

# Post-Mortem: 2026-04-15 02:03 UTC Engine Self-Cancel

## 1. TL;DR

Fix 4 (WS-stale 120s watchdog) triggered at **02:03:05.327Z** because the live pipeline consumer had been chronically dropping ticks for **~2 hours** (not one-shot, as TODO claimed). The cumulative back-pressure starved the WS stale detector's own tick-update path until it crossed the 120s threshold. Root cause is **synchronous file I/O on the live event loop's hot path** (canary JSONL writer with no buffering), compounded by **asymmetric channel sizing** (live 512 vs paper/demo 1024).

The V017 DB schema mismatch (`entry_context_id does not exist`, 337 warns) is a parallel observability gap, not a contributor to the stall — `flush_fills` clears its buffer on error, so it does not back-pressure upstream.

## 2. Corrections to TODO.md Narrative

TODO.md currently states: *"02:00:33 UTC `fan-out: live pipeline lagging, tick dropped` **8,445 條** 一秒內噴發"*.

This is **incorrect**. The log shows:

```
Lagging warnings by minute (>10 / minute):
 3474  00:04   ← FIRST burst, ~2h before Fix 4
   80  00:08
  223  00:20
  152  00:21
  439  00:22
  108  00:23
  436  00:29
  424  00:49
  748  00:53
  876  01:00
   91  01:08
  303  01:09
  504  01:15
  123  01:16
  464  02:00   ← burst immediately preceding Fix 4
```

Total 8,446 drops distributed across **15+ discrete bursts** over 118 minutes. The 02:00 burst is only **464**, not 8,445. The TODO's "single catastrophic stall" framing obscures the real pattern: **chronic, recurrent under-capacity**, not a sudden acute event.

## 3. Timeline Reconstruction

| Time (UTC) | Event |
|---|---|
| 2026-04-14T23:56:36 | Engine boot (`engine-1776244436.log` start) |
| 23:56:39 | **First** `fills flush failed — column "entry_context_id" does not exist` — V017 migration not yet applied |
| 00:04:55 | **First** `fan-out: live pipeline lagging, tick dropped` (3,474 in one minute) |
| 00:04:59 | `fills flush failed` × N interleaved with lagging bursts |
| 00:08 → 01:16 | 14 more bursts, 140 → 876 drops each |
| 02:00:33 | Final burst (464 drops) |
| 02:03:05.327 | `ERROR WS tick stale — triggering engine cancel (Fix 4) stale_ms=135201` |
| 02:03:05 → end | Graceful close: 10 positions market-closed, event consumer saves (ticks=1,753,274, fills=382) |
| 02:03 → 11:13 | **7h10m silent window** — watchdog daemon was never deployed → no restart |
| 09:13:56 | operator manual `restart_all.sh` (new PID 577219) |

## 4. Root-Cause Analysis

### 4.1 Why did Fix 4 trigger?

Fix 4 cancels the engine when `shared_last_tick_ms` has not advanced for ≥120s. In `event_consumer/mod.rs:882-884`, `last_tick_ms` is updated **inside** the `event = event_rx.recv()` arm — i.e., only when the consumer successfully pulls a tick. When the consumer falls behind and the 512-slot channel saturates, the producer drops ticks (fan-out in `main.rs:816-820`). The consumer still eventually drains the queue, but if stalls get long enough that `recv` itself is delayed > 120s, Fix 4 fires.

So Fix 4 is measuring consumer health, not WS health. The stall_ms=135,201 means the consumer could not pull a single tick for 135 seconds — which is entirely consistent with a consumer loop blocked on synchronous I/O.

### 4.2 What blocks the consumer?

The select-arm for `event = event_rx.recv()` at `event_consumer/mod.rs:878-990` does synchronous work including:

1. **`pipeline.on_tick(&ev)`** — full CPU strategy/risk/governance path (acceptable).
2. **Canary write** (line 889-897) —
   ```rust
   let mut f = canary_file;  // &std::fs::File opened with .append(true)
   if let Ok(json) = serde_json::to_string(&record) {
       let _ = writeln!(f, "{}", json);
   }
   ```
   A **synchronous `write` syscall** on a raw `std::fs::File` (no `BufWriter`, no `tokio::fs::File`) for every tick, writing 2–3 KB JSON. At the observed tick rate (~280/sec across 25 symbols), live emits ~700 KB/sec of serialize + syscall work.
3. **`audit_writer.append()`** (line 902-910) — only on new fills, lower volume, but same pattern.
4. Several `parking_lot::RwLock.read()` calls — cheap, not a contributor.

This sync-write pattern on the hot path has three compounding problems on the **live** runtime specifically:

- Live runs only **4 worker threads** (`main.rs:1024`). Any one thread blocked on I/O removes 25% of available CPU for all other live tasks (WS reader, private WS auth, dispatch, reconciler).
- The canary file at the time of the incident was **~42M lines, ~100GB+**. While append-at-end is O(1) in ext4, filesystem cache pressure at that size is non-trivial.
- Live has a **512-slot** fan-out channel, not paper/demo's **1024**. Time to saturate is half.

### 4.3 Why now and not earlier?

2026-04-11 raised `worker_threads(2→4)` for this same class of issue ("1808 lagging warnings in a single session"). That fix reduced frequency but did not remove the underlying sync-I/O on hot path. When canary JSONL grew past ~100GB and/or a burst of ticks arrived coincident with background fsync/writeback pressure, the consumer fell behind again.

## 5. Contributing Issues Discovered

These are real problems but **not** the primary cause:

| Issue | Severity | Evidence |
|---|---|---|
| V017 schema mismatch (337 `fills flush failed`) | High — silent data loss of fills | `flush_fills` at `trading_writer.rs:309` calls `buf.clear()` after any outcome; failed fills are lost. But this is **downstream** of the consumer, so it does not cause lag. V017 was deployed 09:09Z, after this crash. |
| Engine binary shipped with entry_context_id code before V017 applied | Process issue | Deploy order violation; should gate binary hot-swap on migration version. |
| Canary file 111GB unrotated | Disk + I/O pressure | Already tracked as FUP-3. |
| Asymmetric channel sizing (512 vs 1024) | Design smell | No written justification for the split. |

## 6. Remediation Proposal

Ordered by impact vs effort. **All four together** are the right Phase 1 fix — partial fixes will continue to see recurrence.

### R1 — Move canary write off the event loop (highest impact)

Wrap the canary writer in a `BufWriter<File>` behind a bounded `mpsc::channel::<String>(4096)` consumed by a dedicated `tokio::task::spawn_blocking` (or a dedicated OS thread). The event-loop branch becomes a `try_send` → `warn!` on full (same pattern as `trading_tx`). 0 syscalls on the hot path.

Alternative simpler patch: wrap the file in `BufWriter::with_capacity(64 * 1024, file)` and flush on an interval. Reduces syscall count ~30×, cheap to implement, but still blocks on flush ticks.

**Recommendation: full offload.** Canary JSONL is a diagnostic — it must never influence runtime behavior.

### R2 — Symmetric channel sizing

Raise live fan-out channel from **512 → 1024** to match paper/demo (`main.rs:736`). Single-line change. The reason for 512 is not documented in commits — leaning on symmetry unless a concrete reason surfaces.

### R3 — Live worker thread bump or consumer dedicated thread

Two options:

- **R3a (cheap)**: bump `worker_threads(4 → 6)` to add headroom for I/O-bound tasks even if R1 lands.
- **R3b (architectural)**: split event_consumer into a pure-CPU tick handler thread + async service thread. Consumer recv's into a channel consumed by a dedicated `spawn_blocking` closure. Large refactor — defer until R1+R2 are insufficient.

### R4 — Gate Fix 4 on consumer throughput, not just wall-clock

`shared_last_tick_ms` is updated in the consumer arm, making Fix 4 measure "consumer has not drained a tick in 120s" — which is sensitive to the exact stall we need to heal around. Consider adding a separate metric: `producer_last_tick_ms` updated at the WS reader. Fix 4 should fire only when both advance very slowly (real WS loss), not when only the consumer lags (which is R1's job to fix).

Risk: weakening Fix 4. Only change after R1 has eliminated consumer-side stalls as the dominant failure mode.

## 7. Proposed Phase 1 Delivery

Scope (single PR):

1. R1 — offload canary write (largest file + test)
2. R2 — raise live channel to 1024 (1-line)
3. FUP-3 — add `OPENCLAW_DISABLE_CANARY_DUMP=1` flag + size-based rotation (covered separately under FUP-3)

Defer:

- R3a/R3b (wait for telemetry after R1+R2 land)
- R4 (needs R1 to bed in first)

Acceptance:

- 24h paper+demo+live run with 0 `live pipeline lagging` warnings
- `engine_results.jsonl` growth ≤ 5 GB / 24h (or 0 if `OPENCLAW_DISABLE_CANARY_DUMP=1`)
- No new `fills flush failed` (V017 already deployed)

## 8. Open Questions

- Why did 2026-04-11 fix (worker_threads 2→4) mask the issue for 3 days before recurrence?
  - Hypothesis: canary file size threshold crossed sometime between 04-11 and 04-14.
- Are paper and demo also dropping ticks silently?
  - Fan-out `try_send` on paper_tx/demo_tx also logs warn — but paper+demo have 1024-slot channels and may not have crossed threshold. Need to grep.
- Does the same log show WS reader lag independent of consumer lag?
  - Would disambiguate consumer vs network. Not investigated in this PR.

## 9. Artifacts

- Investigation queries and output retained in this document's tables.
- No code changes in this PR (post-mortem only).
- Remediation PRs to be filed per R1–R4 section.
