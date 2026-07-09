# P1-WATCHDOG-STATUS2-RCA — `openclaw-watchdog.service status=2/INVALIDARGUMENT` RCA

- **Date**: 2026-05-19
- **Author**: QA (single sub-agent dispatch from PM)
- **Scope**: Read-only RCA. No runtime mutation. No restart. No fix applied.
- **Triggering evidence**: yesterday's QA Phase 1b 24h verification report
  (`2026-05-18--phase_1b_24h_post_deploy_verification.md`) flagged
  `openclaw-watchdog.service` exited `status=2/INVALIDARGUMENT` 9 times in 7d
  with auto-respawn by `Restart=always`.
- **Verdict**: **NOT A REGRESSION**. Pre-existing by-design behavior mis-named
  by systemd's exit-code label. **No code fix urgently required**; recommend
  **(b) systemd-unit `SuccessExitStatus=2` cosmetic fix** + **operator decision
  on rollback path semantics**. Optional **(a) E1 ticket** to make rollback
  exit code semantically distinct from argparse failure.

---

## §1 Root cause hypothesis

### Most likely (CONFIRMED — HIGH confidence)

**`status=2/INVALIDARGUMENT` is NOT an argparse / argument error. It is the
designed 3-STRIKE rollback path.** Source:

```python
# srv/helper_scripts/canary/engine_watchdog.py:754-756
if state.rollback_triggered:
    logger.critical("Watchdog exiting — runtime rollback triggered ...")
    sys.exit(2)
```

When `MAX_STRIKES=3` consecutive ENGINE_CRASH detections happen inside
`STRIKE_WINDOW_SECONDS=3600` (1h window), watchdog intentionally exits with
code `2`. systemd's exit-code-to-name table maps integer 2 to the symbolic
name `INVALIDARGUMENT`, which is **purely cosmetic** — it does not mean the
arguments were invalid. Python `sys.exit(2)` simply yields the integer; the
"INVALIDARGUMENT" label is systemd's convention.

The Python ARGPARSE module **also** defaults to `sys.exit(2)` on unrecognized
flags, which makes this name overload natively confusing. Both share the same
integer return code.

**Confirmation evidence**:
- All 36 historical `3-STRIKE TRIGGERED` log lines in
  `/tmp/openclaw/watchdog.log` paired 1:1 with `Watchdog exiting — runtime
  rollback triggered`.
- Last 7d: **10** `3-STRIKE` events (not 9 — yesterday's count was conservative
  by 1) at exact timestamps matching journalctl `status=2/INVALIDARGUMENT`:
  5/12 18:23:22 / 18:27:14 / 18:31:06 / 18:34:58 / 18:38:50 / 18:57:27 / 20:29:22
  / 21:59:32 / 22:27:30, and 5/19 03:55:14.
- **Zero** Python tracebacks, zero `argparse`, zero `usage:` in 2320-line
  `watchdog.log`.

### Alternative 1 (REJECTED — LOW confidence)

argparse "unrecognized argument" — systemd `ExecStart=` mismatch with current
script signature. **Rejected**: `systemctl --user cat` confirms
`ExecStart=/usr/bin/python3 helper_scripts/canary/engine_watchdog.py
--data-dir /tmp/openclaw --stale-threshold 45 --grace-period 120 --poll-interval 2`;
all four flags exist in the current `main()` parser. Manual flag walk-through
PASS. Zero `usage:` lines in `watchdog.log`.

### Alternative 2 (REJECTED — LOW confidence)

Uncaught Python exception in main loop. **Rejected**: `Type=simple` with
`StandardError=append:/tmp/openclaw/watchdog.log` would have captured a
traceback. Zero tracebacks across 2320 lines / 36 rollback events spanning
4/16 → 5/19.

---

## §2 Evidence trail

### 2.1 systemd unit (`systemctl --user cat openclaw-watchdog.service`)

```
[Service]
Type=simple
WorkingDirectory=/home/ncyu/BybitOpenClaw/srv
ExecStart=/usr/bin/python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --stale-threshold 45 --grace-period 120 --poll-interval 2
Restart=always
RestartSec=5
StandardOutput=append:/tmp/openclaw/watchdog.log
StandardError=append:/tmp/openclaw/watchdog.log
```

All four flags valid against `main()`. No `SuccessExitStatus=` set, so any
nonzero exit is logged as failure.

### 2.2 journalctl 7d (10 INVALIDARGUMENT entries — actual count, not 9)

```
5月 12 18:23:22 status=2/INVALIDARGUMENT
5月 12 18:27:14 status=2/INVALIDARGUMENT
5月 12 18:31:06 status=2/INVALIDARGUMENT
5月 12 18:34:58 status=2/INVALIDARGUMENT
5月 12 18:38:50 status=2/INVALIDARGUMENT
5月 12 18:57:27 status=2/INVALIDARGUMENT
5月 12 20:29:22 status=2/INVALIDARGUMENT
5月 12 21:59:32 status=2/INVALIDARGUMENT
5月 12 22:27:30 status=2/INVALIDARGUMENT  (8th — yesterday's report counted up to here = 9 incl. 5/19)
5月 19 03:55:14 status=2/INVALIDARGUMENT  (10th in 7d window — yesterday's report saw 9, actual = 10)
```

Counter Tue 03:55:19: `restart counter is at 38`. Yesterday's QA report noted
37→38; that matches the 5/19 03:55:14 event.

### 2.3 watchdog.log paired evidence (5/19 03:55:14)

```
03:53:05 ENGINE_CRASH detected — snapshot age=46.2s, total crashes=4
03:53:16 Auto-restart succeeded
03:53:16 Activating Python fallback (strike 2/3)
03:54:18 ENGINE_RECOVERED — Rust engine snapshot is fresh again
03:55:04 ENGINE_CRASH detected — snapshot age=46.6s, total crashes=5
03:55:14 Auto-restart succeeded
03:55:14 CRITICAL 3-STRIKE TRIGGERED — 3 crashes in 3600s window → runtime rollback
03:55:14 CRITICAL Watchdog exiting — runtime rollback triggered  <-- sys.exit(2) here
03:55:19 Started openclaw-watchdog.service (systemd Restart=always respawn)
```

This is the 3-STRIKE rollback by design (engine_watchdog.py:526-543, 754-756),
not a crash. The watchdog exited cleanly with intentional exit code 2.

### 2.4 Crash density anomaly (5/12 cluster)

5/12 saw 9 events in ~4 hours (18:23 → 22:27). This was a real engine
instability burst (each watchdog instance only needs to see 3 crashes inside
1h to fire). The watchdog correctly fired each rollback. Engine evidently
stabilized after 5/12 22:27 (next event 5/19, 7 days later — the very event
yesterday's report flagged).

### 2.5 Counter at 38 → it has been respawning since 5/12 18:23 cluster

`restart counter` 32→33 (5/12 18:35) → 38 (5/19 03:55). 6 increments over 7d
match the 6 distinct rollback bursts.

---

## §3 Risk assessment

| Dimension | Impact | Notes |
|---|---|---|
| **Phase 1b observability** | LOW | watchdog log fully captures intent; "INVALIDARGUMENT" name in systemd is misleading but the actual rollback chain is observed end-to-end |
| **Trading authority** | NONE | watchdog exits → systemd respawns within 5s; engine itself was restarted by `restart_all.sh --engine-only` BEFORE rollback exit; engine is fresh post-rollback |
| **Engine availability** | LOW | each 3-STRIKE rollback was followed by successful auto-restart; engine snapshot was fresh within 5-15s; no extended outage |
| **Hard gates / Live** | NONE | 5 hard gates (CLAUDE.md §四) unaffected; live_reserved + Operator role + OPENCLAW_ALLOW_MAINNET + secret slot + authorization.json all independent |
| **Audit / explainability** | MEDIUM | yesterday's QA report had to flag this as "needs RCA" because the systemd name is misleading; future readers will repeat the same investigation cost |
| **Watchdog availability** | LOW | systemd `Restart=always` re-spawns within 5s; PID continuity is broken (state is reset) which means strike count starts fresh — this is actually desired for 3-STRIKE |
| **Strike-count state drift** | LOW-MEDIUM | each rollback resets `crash_timestamps` (no persistence in `WatchdogState` for crash list — only `watchdog_state.json` for restart consecutive_failures). Means an engine that crashes 3x → respawn → 3x → respawn loops forever without escalation. May or may not be intentional. |

**Conclusion**: this is NOT a new Phase 1b regression. The pattern existed
since 4/16 (oldest 3-STRIKE in log). Phase 1b deploy was 5/17 23:54 UTC;
within the 7d window the 5/12 burst is **pre-deploy** by 5 days. Only the
5/19 03:55 event is post-deploy and it was a single isolated rollback (1 of
10), well within the historical baseline.

---

## §4 Recommended fix scope

### Decision: **(d) Accept as low-impact + (b) Cosmetic systemd fix recommended**

This is a **pre-existing by-design behavior** with **misleading systemd
labeling**. Three layered recommendations, ordered by cost / value:

#### Layer 1 — Cosmetic only (operator action, no E1)

Add `SuccessExitStatus=2` to systemd unit so exit code 2 is logged as
`code=exited, status=0/SUCCESS` instead of `status=2/INVALIDARGUMENT`.

**Pro**: stops future QA / observability false alarms on this event.
**Con**: hides any actual argparse error too (rare; 0 in 4+ months of log
history) — would need to use distinct exit codes (see Layer 2).

**Recipe** (operator-applied):
```bash
# Add to [Service] section of ~/.config/systemd/user/openclaw-watchdog.service:
SuccessExitStatus=2
# Then:
systemctl --user daemon-reload
systemctl --user restart openclaw-watchdog.service
```

#### Layer 2 — Code disambiguation (E1 ticket, LOW priority)

Change `sys.exit(2)` for 3-STRIKE rollback (engine_watchdog.py:756) to a
distinct exit code (e.g. `sys.exit(20)` for rollback, leave 2 for argparse
default). Pair with systemd `SuccessExitStatus=20`. This way:
- exit 20 = controlled rollback (success, log as info)
- exit 2 = argparse failure (real misconfiguration, alert-worthy)

**Scope diff** (single-file, single-line):
```diff
- sys.exit(2)
+ sys.exit(20)  # WATCHDOG-ROLLBACK-EXITCODE: distinct from argparse(=2)
```
Plus systemd unit `SuccessExitStatus=20`.

**Cost**: trivial. **Benefit**: future status=2/INVALIDARGUMENT in
journalctl would be a real argparse misconfiguration alert.

#### Layer 3 — Reconsider rollback policy (FA / operator decision, NOT E1)

The current 3-STRIKE rollback simply exits the watchdog → systemd respawns
within 5s → fresh state → strike counter resets to 0. This means: an engine
that crashes 3x/hour in steady state will produce **endless rollback +
respawn cycles**, never escalating. Is that intended?

Options for operator:
- Keep as-is (3-STRIKE = "log loudly + reset", systemd respawn handles
  continuity). Pro: simple, current. Con: no real escalation.
- Add `Restart=on-failure` + `RestartPreventExitStatus=20` so a true rollback
  STOPS the watchdog and requires manual intervention. Pro: real escalation.
  Con: trading governance halt during operator absence.
- Persist `crash_timestamps` to `watchdog_state.json` so strikes survive
  respawn. Pro: meaningful 3-STRIKE rule. Con: lifecycle complexity.

**This is a policy question, not a bug.** Operator should decide based on
desired escalation semantics. **No QA action required**.

---

## §5 Verification plan post-fix

If Layer 1 (cosmetic `SuccessExitStatus=2`) is applied:
1. `systemctl --user cat openclaw-watchdog.service` should show
   `SuccessExitStatus=2`.
2. Wait for next natural 3-STRIKE event (historically 1-2/week) OR force a
   test rollback by killing engine PID 3x within 1h.
3. `journalctl --user -u openclaw-watchdog.service | grep status=` should
   show `status=0/SUCCESS` instead of `status=2/INVALIDARGUMENT`.
4. `restart counter` should still increment (Restart=always still fires).
5. Confirm engine recovery: `passive_wait_healthcheck.py` continues to pass.

If Layer 2 (code change `sys.exit(20)`) is applied:
1. After E1 implementation + E4 sign-off + deploy, future rollback logs
   `status=0/SUCCESS` (assuming `SuccessExitStatus=20`).
2. Manually break argparse (e.g. add `--bogus-flag` to ExecStart) →
   `status=2/INVALIDARGUMENT` should fire correctly (real misconfig signal
   preserved).
3. Roll back the test misconfig.

---

## Appendix A — Watchdog log statistics (4/16 → 5/19)

| Metric | Value |
|---|---|
| Total log lines | 2320 |
| `3-STRIKE TRIGGERED` events | 36 |
| `Watchdog exiting — runtime rollback triggered` events | 36 |
| Python tracebacks | 0 |
| `argparse` / `usage:` lines | 0 |
| systemd `status=2/INVALIDARGUMENT` (7d) | 10 |
| systemd `restart counter` (current) | 38 |
| Watchdog active since (current PID 1736260) | 5/19 03:55:19 CEST (13h uptime) |

## Appendix B — Why yesterday's QA report saw 9 (not 10)

Yesterday's report ran query window ending 2026-05-18 ~UTC. The 10th event
(2026-05-19 03:55:14 CEST = 01:55:14 UTC) was the marginal one — it was
"the trigger that prompted today's RCA" per the PM brief. yesterday's
counter 37→38 observation confirms it was the 5/19 event seen in flight.
Today's 7d window (5/12 → 5/19) captures all 10.

---

**End of report.**
