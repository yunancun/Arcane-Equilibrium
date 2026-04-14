# WS Tick Stale Detector — Known Issue & Design Notes

**Status**: Active (2026-04-14)
**File**: `rust/openclaw_engine/src/main.rs` — search for "Fix 4" block above `signal_loop`
**Related fixes**: Fix 1 (panic hook), Fix 2 (watchdog auto-restart), Fix 3 (crash-only)

---

## Background / 背景

**Incident 2026-04-14**: Rust engine appeared alive to `ps`/logs but snapshot writer and tick processing had frozen for 14+ minutes before a silent exit. Operator discovered via GUI showing stale data. **No automatic recovery — 18 minutes of trading downtime.**

**Root-cause hypothesis** (cannot 100% confirm — engine.log was truncated on restart):
the WS tick stream stopped (disconnect / `event_consumer` zombie state / deadlock in
a downstream task holding shared_last_tick_ms update path), and without a live-tick
assertion, the engine could not self-diagnose its own zombie state.

## What Fix 4 does / 修復 4 做了什麼

Every 30 seconds, a background task checks the shared `AtomicU64` `shared_last_tick_ms`
(updated in `event_consumer/mod.rs:882` on each inbound tick). If:

1. We have ever seen a tick (`last_tick_ms != 0` — skip warmup period), AND
2. The most recent tick is older than **120,000 ms (120 s)**

...then the task calls `cancel.cancel()` on the engine-wide CancellationToken. This
triggers the normal shutdown path (signal_loop exits → ordered shutdown of paper/demo/
live pipelines → snapshot write → socket cleanup → process exit). The external
watchdog (Fix 2) then restarts the engine from a fresh boot — re-subscribing WS
from scratch rather than attempting to reconnect from an unknown zombie state.

## Why 120 s, not 60 s / 為何 120s 而非 60s

The initial design considered 60s. Operator (2026-04-14) chose 120s to reduce
false-positive restarts during:

- **Quiet market hours** (deep night for thin altcoins), where legitimate gaps
  between ticks can exceed 60s on tier-3 symbols.
- **Bybit WS hiccups** that naturally recover in 30–90s without requiring a full
  engine restart (unlucky connection renegotiation, brief CDN failover).
- **Daily maintenance windows** on Bybit (historically have caused 60-90s
  silences).

Trade-off: 120s means in the **worst case we sit zombie for 120s + watchdog grace
period (~45s) + restart time (~15s) = ~3 minutes** before recovery. For a trading
system this is still non-trivial; a 60s threshold would halve the zombie window
at the cost of more false restarts. Re-evaluate after observing production
behaviour for ≥1 week.

## Known false-positive scenarios / 已知誤報場景

1. **Large holiday** (Christmas, Chinese New Year) — global crypto volume drops
   dramatically. Mitigation: during such periods, set `OPENCLAW_TICK_STALE_THRESHOLD_MS`
   (future TODO — not yet env-overridable) to 300000 temporarily.
2. **Scanner universe restart with empty symbols** — first tick may take longer
   than 120s. Mitigation: the `last == 0` guard skips this case.
3. **Cold boot before first tick** — same as above, covered.

## Known true-positive scenarios / 已知真陽性場景

1. **WS disconnect without auto-reconnect** (the 2026-04-14 incident pattern).
2. **`event_consumer` deadlock** holding the `shared_last_tick_ms` update.
3. **tokio runtime stall** (rare, but possible under rust panic in a runtime
   worker without catch_unwind).

## Future improvements / 未來改進

- **Per-tier thresholds**: compute stale only against tier-1 symbols (BTC/ETH)
  which have near-continuous ticks; ignore tier-3 which can be legitimately quiet.
- **Env-var override**: `OPENCLAW_TICK_STALE_THRESHOLD_MS` for operator control
  without rebuild.
- **Metric export**: emit `tick_stale_ms` as a gauge for Grafana/alerting so
  Operator sees drift before the cancel fires.
- **IPC `get_tick_stale_ms`**: expose current stale duration via IPC for GUI
  display so Operator has visibility into WS health.
- **Pre-cancel warning**: at 60s of staleness, emit a WARN log; at 120s, act.
  Gives operator a 60s early window to intervene manually.

## Interaction with other fixes / 與其他修復的互動

- **Fix 1 (panic hook)**: if the watchdog task itself ever panics, panic hook
  logs it. The watchdog does NOT currently run through `run_pipeline_crash_only`
  (it's a single-task diagnostic loop, not a pipeline), but its panic would
  still show up in logs with full backtrace.
- **Fix 2 (watchdog auto-restart)**: when Fix 4 cancels the engine, Fix 2 detects
  the dead snapshot within ~45s and triggers `restart_all.sh --engine-only`.
- **Fix 3 (crash-only)**: Fix 4 uses `cancel.cancel()` (graceful path), not
  `panic!()` (crash-only path). A graceful cancel gives ordered shutdown (write
  final snapshot, drain audits); a panic would trigger Fix 3's crash-only cancel
  anyway but skip the ordered writes. For WS-stale, graceful is preferred.

## How to test / 如何測試

**Synthetic test (during E4)**: inject a `tokio::spawn` that sleeps 130s while
holding a mutex guard that blocks `shared_last_tick_ms.store(...)`. Watch for:

1. `tick-stale watchdog spawned` on startup.
2. After ~120-150s, `WS tick stale — triggering engine cancel (Fix 4)` log line.
3. Ordered shutdown logs follow.
4. Engine exits with code 0 (clean).
5. External watchdog (Fix 2) restarts within its grace window.

**Real-world test**: pull the ethernet cable briefly on the machine (simulates
WS disconnect at network layer). Observe engine detects stale tick after 120s
and auto-restarts once the network is back.
