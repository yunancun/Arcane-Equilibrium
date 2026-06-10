# PA DESIGN — Watchdog → Alert Wiring (engine-down non-silent)

Date: 2026-06-05
Author: PA
Risk class: 中 (standalone monitoring process, additive read-only outbound; 0 hard-boundary touch)
Scope discipline: this is a NOTIFICATION WIRE, not a new alerting framework.

---

## 0. Problem statement

2026-06-05 the Rust engine was down ~20h and nobody knew. The watchdog
(`helper_scripts/canary/engine_watchdog.py`) writes `RESTART_CIRCUIT_BROKEN`
/ `RESTART_FAILED` / `ENGINE_CRASH` events to
`$OPENCLAW_DATA_DIR/canary_events.jsonl`, but **nothing consumes that file**
(grep-confirmed: only `fresh_start.sh` rotates it + `test_canary.py` reads it).
Alert infrastructure exists in the FastAPI app but was never wired to the
watchdog.

---

## PART A — Existing alert infrastructure (mapped, read-only)

### A.1 The three alert files (all under `control_api_v1/app/`)

| File | Public interface | Sync/async | Deps |
|---|---|---|---|
| `telegram_alerter.py` | `TelegramAlerter.send(msg, parse_mode, silent) -> bool`; convenience `alert_system(event, detail)`, `alert_trade`, `alert_stop`, `alert_pnl_summary`; `send_async()` = daemon thread | `send()` **sync** (blocking urllib, timeout=10), `send_async()` non-blocking | **stdlib only** (`urllib.request`, `json`, `threading`) |
| `webhook_alerter.py` | `WebhookAlerter.send(payload: dict) -> bool`; same convenience surface; HMAC-SHA256 sign; multi-endpoint fan-out | `send()` **sync** (urllib, timeout=10), `send_async()` non-blocking | **stdlib only** (`urllib`, `hmac`, `hashlib`) |
| `alert_router.py` | `AlertRouter(telegram, webhook)`; `alert_system(event, detail)`, `alert_trade`, `alert_stop`, `alert_pnl_summary`; `get_stats()` | **all sync** (fans out to each channel's convenience methods, which themselves go through `send_async`) | imports the two alerter classes |

### A.2 Is `alert_router.py` the unified dispatcher? — YES

`AlertRouter` IS the single entry point. It fans out to telegram + webhook, each
channel fails independently (`Alert failures do not affect trading` invariant).
There is **no severity/category enum** — the "category" is the method name
(`alert_system` vs `alert_trade` vs `alert_stop` vs `alert_pnl_summary`). For an
engine-down alert the established reuse is `alert_system(event_tag, msg)`.

### A.3 Creds / config source (MECHANISM + KEY NAMES only)

All four are plain env vars, read in each alerter's `__init__`:

- Telegram: `OPENCLAW_TELEGRAM_BOT_TOKEN`, `OPENCLAW_TELEGRAM_CHAT_ID`
  (`is_enabled` requires BOTH non-empty).
- Webhook: `OPENCLAW_WEBHOOK_URLS` (comma-separated), `OPENCLAW_WEBHOOK_SECRET`
  (optional HMAC key; `is_enabled` requires `URLS` non-empty).

Secret file mechanism: `$OPENCLAW_SECRETS_ROOT/environment_files/basic_system_services.env`
is the canonical env file. (No values inspected/printed.)

### A.4 What triggers alerts TODAY?

**Exactly one call site**, and it is trading-domain, NOT system-health:

- `paper_trading_wiring.py:576` —
  `await asyncio.to_thread(ALERT_ROUTER.alert_system, "RISK:<tier>", msg)`
  fired by the Reconciler when risk tier escalates/de-escalates (P0/P1 risk
  halts). Event tags: `RISK:<tier>`.

`ALERT_ROUTER` singleton is constructed in `paper_trading_wiring.py:353` and
referenced only there + an import in `paper_trading_routes.py:68`.
**There is NO existing engine-down / watchdog / liveness alert anywhere.**

### A.5 HTTP alert endpoint? — NO

Grep of `app/routers/` for `alert` returns empty. There is no
`POST /api/v1/alert` (or any alert-triggering endpoint) an external process
could call. (Relevant to option (b) below.)

### A.6 DECISIVE runtime findings (verified via `ssh trade-core`)

1. **NO alert channel is configured.** All four cred keys
   (`OPENCLAW_TELEGRAM_BOT_TOKEN`, `OPENCLAW_TELEGRAM_CHAT_ID`,
   `OPENCLAW_WEBHOOK_URLS`, `OPENCLAW_WEBHOOK_SECRET`) are **ABSENT** from
   `basic_system_services.env`. Consequence: even the existing `RISK:` alert is
   currently a **no-op**, and any new wiring will be silent until the operator
   provides creds. **This is open question #1.**

2. **The production watchdog is NOT running under systemd.**
   `systemctl is-active openclaw-watchdog` = `inactive` (unit not active /
   installed). The live process is a **bare process** spawned by
   `restart_all.sh:758` (observed `--poll-interval 2`, which matches the
   foreground spawn, NOT the systemd unit's `--poll-interval 1`). This is a
   direct contributor to the ~20h outage: a bare process has no
   `Restart=always`, so after a reboot / un-re-run restart_all, nothing
   respawned the watchdog **and** nothing alerted.

3. **Env-inheritance asymmetry (critical design constraint).**
   `restart_all.sh` does NOT do a blanket `set -a; source env`. It reads
   individual keys via `grep '^KEY='` and selectively exports a known whitelist
   (POSTGRES_PASSWORD, OPENCLAW_ALLOW_MAINNET, OPENCLAW_ENABLE_PAPER, ...). It
   does **NOT** export `OPENCLAW_TELEGRAM_*` / `OPENCLAW_WEBHOOK_*`. The uvicorn
   spawn is the same (only specific vars exported), and the app reads the env
   file only for narrow settings/PG/grafana purposes, not to populate
   `os.environ` with alerter creds.
   - Therefore: **creds-from-own-env (option c) is clean only under the systemd
     launch path** (the unit already has `EnvironmentFile=...basic_system_services.env`
     at line 54). The bare-process path needs restart_all.sh to also export
     those keys.
   - The macOS launchd plist passes only `HOME` / `TMPDIR` / `PATH` /
     `OPENCLAW_DATA_DIR` / `OPENCLAW_BASE_DIR` — no creds (dev box; out of scope
     for the live incident but kept symmetric).

### A.7 Watchdog established patterns to REUSE (not reinvent)

- Single best-effort canary write point: `_append_canary_event(data_dir, event)`
  (engine_watchdog.py:487) — try/except OSError, never raises.
- State-persisted dedup we just added (mirror this exactly):
  - `emit_restart_skipped_if_new(data_dir, reason_key, reason_detail, now)` —
    writes once per stable key, marker persisted in `watchdog_state.json`
    (`last_restart_skipped_reason`), survives polls.
  - `clear_restart_skipped_marker(data_dir)` — clears marker on success /
    recovery so a future skip can re-emit.
- `trigger_restart()` circuit-break branch (engine_watchdog.py:698-708) and
  `on_engine_recovery()` (862) are the natural trigger seams.

---

## PART B — DESIGN: watchdog → alert wiring

### B.1 Option evaluation

| Option | Dependency weight | Creds from watchdog env | Failure isolation | Reuse | Verdict |
|---|---|---|---|---|---|
| (a) import a shared alert helper module | HIGH — the alerters live inside the FastAPI app package; importing pulls the app's import chain into the recovery process | n/a | weak (heavy import surface) | high if alerters were extracted to a zero-dep shared module (= scope creep) | **REJECT** unless we first extract alerters to a standalone zero-dep module (out of scope) |
| (b) POST to local control-API endpoint | LOW (stdlib) but **endpoint does not exist — must be added** | n/a | **WEAK — engine-down often coincides with API-down** (same host, same restart_all supervision). Alerting "everything is down" must not depend on another process that may be dead. | medium | **REJECT** (defeats the purpose) |
| (c) watchdog calls webhook/telegram directly over HTTPS (stdlib urllib, short timeout), creds from its own env | **ZERO new deps** (stdlib only) | clean under systemd; bare-process needs a 4-line restart_all export | **STRONG** (no dependency on any other live process) | high (mirrors the alerters' own stdlib-urllib approach) | **RECOMMEND (variant)** |
| (d) separate tail consumer of canary_events.jsonl | LOW but adds a process to supervise ("who watches that watcher?") | n/a | medium | low | **REJECT** (violates minimality; another SPOF) |

### B.2 RECOMMENDATION — Option (c) variant: zero-dep inline emitter

Add a **self-contained, zero-dependency** alert emitter INSIDE
`engine_watchdog.py`. It does NOT import the FastAPI app. It re-states the
alerters' stdlib-urllib send in ~40 lines, reading the SAME env var names
(`OPENCLAW_TELEGRAM_*` / `OPENCLAW_WEBHOOK_*`) so creds and config stay
single-sourced in `basic_system_services.env`.

Rationale:
- The watchdog is the recovery component; it must stay lightweight and have no
  dependency on the app (importing FastAPI/sqlx/governance into the recovery
  loop is exactly what "standalone" forbids).
- The existing alerters are already pure stdlib urllib — so re-stating their
  send in the watchdog is cheap and keeps failure isolation perfect.
- Alerting must not depend on the API being up (option b's fatal flaw).
- No new process to supervise (option d's flaw).

Trade-off accepted: ~40 lines of urllib send are duplicated between the
watchdog and the app alerters. This is deliberate — coupling the recovery
process to the app to save 40 lines is the wrong call. If the operator later
wants DRY, the correct refactor is to extract the alerter cores into a
zero-dep shared module both consume; that is a SEPARATE, optional task, not part
of this wire.

### B.3 Exactly where the code goes (all in `engine_watchdog.py`, app untouched)

1. **`_send_alert_best_effort(subject: str, body: str, severity: str) -> None`**
   - Zero-dep. Reads `OPENCLAW_TELEGRAM_BOT_TOKEN`, `OPENCLAW_TELEGRAM_CHAT_ID`,
     `OPENCLAW_WEBHOOK_URLS`, `OPENCLAW_WEBHOOK_SECRET` from `os.environ`.
   - If NO channel configured: silent no-op + a ONE-TIME `logger.warning`
     ("alert channels unconfigured — engine-down alerts disabled"); never raises.
   - Telegram: POST `https://api.telegram.org/bot<token>/sendMessage`,
     `urllib.request.urlopen(req, timeout=5)`, wrapped in try/except (catch-all),
     fired in a `daemon=True` thread (fire-and-forget).
   - Webhook: POST JSON to each URL in `OPENCLAW_WEBHOOK_URLS`, optional
     HMAC-SHA256 `X-OpenClaw-Signature` header (mirror webhook_alerter `_sign`),
     `timeout=5`, per-URL try/except, also in a daemon thread.
   - **Timeout 5s** (stricter than the app's 10s — the watchdog must never stall).

2. **`emit_engine_down_alert_if_new(data_dir, alert_key, subject, body, now) -> bool`**
   - Mirrors `emit_restart_skipped_if_new` EXACTLY: reads `watchdog_state.json`,
     compares a stable `alert_key` against persisted `last_engine_down_alert_key`,
     writes the marker + `last_engine_down_alert_ts`, then calls
     `_send_alert_best_effort(...)` and ALSO appends a canary event
     (`ENGINE_DOWN_ALERT_SENT`) for audit. Returns False (dedup) if key unchanged.

3. **`clear_engine_down_alert_marker(data_dir)`**
   - Mirrors `clear_restart_skipped_marker`: pops the marker so a future
     down-transition re-emits. Called from the recovery path.

### B.4 Trigger points in the watchdog state machine

| Trigger | Where | alert_key | Severity | Dedup behaviour |
|---|---|---|---|---|
| **Circuit broken** (definite) | `trigger_restart()` circuit-break branch (after the existing `RESTART_CIRCUIT_BROKEN` canary append, ~line 705) | `"circuit_broken"` | CRITICAL | emit ONCE on transition into circuit-broken |
| **Prolonged down re-alert** (optional, recommended given the 20h case) | `on_engine_crash()` level-triggered region (after `should_restart`), gated on `state.circuit_broken AND (now - last_engine_down_alert_ts) >= RE_ALERT_INTERVAL` (e.g. 4h) | `f"circuit_broken_reping_{floor(hours_down)}"` (key changes each interval so dedup allows exactly one per window) | CRITICAL | one re-alert per interval while still down |
| **All-clear** (recovery) | `on_engine_recovery()` (after `clear_restart_skipped_marker`, ~line 878) | n/a (send + `clear_engine_down_alert_marker`) | INFO | only if a down-alert had been emitted |

Note on `ENGINE_CRASH` / `RESTART_FAILED`: do NOT alert on every crash/failed
attempt — those are transient and self-healing (backoff + restart). Alerting on
them would spam during normal restart cycles. The alert-worthy signal is
**circuit-broken (auto-recovery has given up)** + **prolonged-down**. This keeps
"neither spam nor miss" — the design alerts exactly when manual intervention is
actually required.

### B.5 Payload (what the operator needs to act)

```
[CRITICAL] OpenClaw engine DOWN — manual intervention required
engine: <label or "rust openclaw_engine">
down for: <H>h <M>m (since <ts>)
auto-restart: circuit broken after <N> consecutive failures
last failure: <last_failure_reason>   # from watchdog_state.json
action: ssh trade-core; journalctl/engine.log; manual restart_all
```
Recovery: `[INFO] OpenClaw engine RECOVERED — snapshot fresh again (was down <H>h <M>m)`.

### B.6 Failure-isolation design (the load-bearing requirement)

- Every alert call is **fire-and-forget in a daemon thread** with a **5s urllib
  timeout** and a **catch-all try/except**. A hanging/failing/missing endpoint
  can never stall the poll loop or block a restart.
- Alerts are emitted **AFTER** the restart/recovery logic, never on the
  critical path. The monitoring loop's correctness does not depend on any alert
  succeeding.
- Creds absent → silent no-op (one-time warn). Aligns with root principle 14
  (baseline operable with zero external services); the wire is purely additive
  and cannot disable the watchdog.
- Reuses the proven `_append_canary_event` best-effort discipline for the audit
  trail.

### B.7 The bare-process gap (must-fix companion change)

Because the live watchdog is a bare process (B.6 / A.6.2) and restart_all.sh does
NOT export the alerter creds (A.6.3), a **4-line addition to restart_all.sh** is
required so the bare-process watchdog inherits the creds symmetrically with the
systemd unit. Export (when present in env file):
`OPENCLAW_TELEGRAM_BOT_TOKEN`, `OPENCLAW_TELEGRAM_CHAT_ID`,
`OPENCLAW_WEBHOOK_URLS`, `OPENCLAW_WEBHOOK_SECRET` — using the same
`grep '^KEY='` pattern already used for POSTGRES_PASSWORD etc. (Operator should
separately decide whether to also migrate the live watchdog onto the systemd
unit, which would fix BOTH the respawn gap and the env gap; that is an ops
decision, not part of this code wire.)

---

## E1 implementation task breakdown

All four are in-file/in-script; T1-T3 touch only `engine_watchdog.py`, T4 only
`restart_all.sh`. T1 and T4 are independent; T2 depends on T1; T3 depends on T2.

- **T1** — `_send_alert_best_effort(subject, body, severity)`: zero-dep stdlib
  urllib telegram + webhook send; creds-from-env; 5s timeout; daemon-thread
  fire-and-forget; catch-all try/except; one-time "channels unconfigured" warn.
- **T2** — `emit_engine_down_alert_if_new` + `clear_engine_down_alert_marker`:
  mirror `emit_restart_skipped_if_new` / `clear_restart_skipped_marker` exactly
  (state-persisted markers in `watchdog_state.json`; also append
  `ENGINE_DOWN_ALERT_SENT` canary event).
- **T3** — wire trigger points: circuit-break branch in `trigger_restart`,
  recovery in `on_engine_recovery`, optional prolonged-down re-alert in
  `on_engine_crash` level-triggered region (add `RE_ALERT_INTERVAL_SECONDS`
  constant, default 4h). Build the payload from existing `watchdog_state.json`
  fields (`consecutive_failures`, `last_failure_reason`, down-since).
- **T4** — `restart_all.sh`: export the 4 alerter cred keys (grep-from-env
  pattern) before the watchdog spawn so the bare-process path matches systemd.

LOC estimate: ~90-120 (T1 ~45, T2 ~35, T3 ~25, T4 ~8). Pure Python + shell.

---

## What E4 needs to test (in `helper_scripts/canary/test_canary.py`)

1. Circuit-break emits **exactly one** alert (re-poll while circuit_broken does
   NOT re-emit) — assert via `ENGINE_DOWN_ALERT_SENT` canary count == 1 and
   marker persisted.
2. Recovery clears the marker → a subsequent down-transition emits again (no
   permanent dedup swallow).
3. Creds absent → `_send_alert_best_effort` is a no-op and **does not raise**;
   loop continues; one-time warn logged.
4. **Alert hang does not stall the loop**: monkeypatch `urllib.request.urlopen`
   to sleep > timeout / raise; assert the poll loop still advances and
   `trigger_restart` is unaffected (fire-and-forget daemon thread + timeout).
5. Prolonged-down re-alert fires once per `RE_ALERT_INTERVAL_SECONDS` window
   (key changes per window), not every poll.
6. Webhook HMAC header present when `OPENCLAW_WEBHOOK_SECRET` set, absent when
   not.

E2 review focus (3 points):
1. **Failure isolation is airtight** — confirm every send path is daemon-thread
   + timeout + catch-all, and that NO alert call sits on the restart critical
   path (a synchronous send before `trigger_restart` would reintroduce the
   stall risk).
2. **Dedup parity** — confirm the new markers mirror the existing
   `emit_restart_skipped_if_new` semantics (stable key, persisted, cleared on
   recovery) so circuit-broken state cannot spam, and recovery cannot
   permanently swallow.
3. **No secret leakage** — confirm creds are only read from env, never written
   to canary_events.jsonl / logs / payloads (log the channel name, never the
   token).

---

## Risks + OPEN QUESTIONS for the operator

1. **#1 BLOCKER-ish: NO channel is configured.** All four cred keys are ABSENT
   from `basic_system_services.env` (verified on trade-core). Until the operator
   provides at least one of {Telegram bot token + chat id} OR {webhook URL(s)},
   this wire (and the existing `RISK:` alerts) stay silent. **Operator must
   supply creds** for the wire to do anything. The design degrades safely
   (silent no-op) when unconfigured.
2. **Live watchdog runs as a bare process, not systemd.** This is the deeper
   root of the 20h outage (no `Restart=always`). T4 fixes the creds-inheritance
   for the bare path, but the operator should decide whether to migrate the live
   watchdog onto `openclaw-watchdog.service` (which fixes both respawn AND env
   in one move). Recommended, but it is an ops/deploy decision outside this code
   wire.
3. **Telegram vs webhook preference** — which channel does the operator want as
   primary? (Telegram = direct phone push; webhook = integrate with an existing
   pager/Slack/Discord). The design supports both simultaneously; operator only
   needs to populate the keys they want.
4. **Re-alert interval** — is 4h the right prolonged-down cadence, or should it
   be tighter (e.g. 1h) given the 20h precedent? Default proposed 4h; trivially
   tunable via constant.

---

## Hard-boundary / 16-principle compliance

- Hard boundaries: **0 touched.** No `live_execution_allowed`, `max_retries`,
  `OPENCLAW_ALLOW_MAINNET`, `authorization.json`, lease, or `system_mode`
  surface is read or modified. The wire is read-only outbound notification.
- Root principle 14 (operable with zero external services): respected — creds
  absent ⇒ silent no-op, watchdog fully functional without any external alert
  service.
- Root principle 6 (uncertainty defaults conservative) and the watchdog's own
  "alert failures do not affect trading / recovery" invariant: preserved by
  fire-and-forget + timeout + best-effort.

PA DESIGN DONE: report path: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-05--watchdog_alert_wiring_design.md
