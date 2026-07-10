# PM Request - GLOBAL_QUALIFIED_AUTONOMOUS_LEARNING_SHADOW_V1 WP1 Runtime Gate

Date: 2026-07-10
Authority chain: `PM -> E3 -> BB -> PM`
Exact target HEAD: `5ae414521ca76e34529c97348ce4363efdd3dec6`
State requested: `WP1_AUTHORIZED_ISOLATED_PG_THEN_ALR_SERVICE_ONLY_SOAK`

R1 disposition: `STALE_BEFORE_EXECUTION`. Before the authorized script could
start PostgreSQL, its exact-head guard observed concurrent GUI-only HEAD
`7d1c24794` and exited `1`. No PG process, DB, sync, service, or runtime action
occurred; an independent residue scan was clear. This packet cannot be reused.

This is a fresh, non-retroactive request. The unauthorized QA disposable-PG
probe and all of its observations are retracted and cannot satisfy this gate.
The source/static/unit checkpoint is `c080c552b`; source plus durable RCA is on
the exact target history.

## Fresh preflight

- Mac HEAD/origin/remote main: exact target, dirty unrelated files preserved.
- Linux checkout/origin: clean at `dbc6a936c`; remote main reports target.
- ALR service: active/running, PID `2073347`, restarts `0`, currently pinned to
  stale `8dfa1200a`; it is the only service permitted to restart.
- Engine process: PID `2203280`, start `2026-07-10 08:33:13` local; it must not
  restart or receive a signal.
- Production PG through `alr_shadow`: raw/source/artifact/edge/run/feedback/
  health counts `80727/7309/29609/18738/589/588/10281`; untrained source count
  `0`; equivalent-suppression artifacts `0`; authority mismatches `0/0`.
- Last 60 minutes health: `739` rows and `1,752,908` canonical JSON bytes,
  about one immutable health row per 4.87 seconds.
- Role boundary: scanner `SELECT=true`, scanner `INSERT=false`, ALR health
  `INSERT=true`, ALR health `UPDATE=false`, run `DELETE=false`.
- Derived cache rows/payload: `0/0`; any nonzero pre-restart recheck invalidates
  this packet because the service invokes retention.
- No migration is added or applied; physical V151-V156 remain the schema.

## Requested actions - exact order

1. Run one authorized disposable Mac Homebrew PostgreSQL regression under a
   new `/tmp/alr-wp1-gated.*` directory and a dedicated non-production port/
   Unix socket. Apply only existing V030 and V151-V156 plus the existing
   `alr_shadow` role contract. Use synthetic scanner rows and the three
   canonical isolated-PG harnesses on fresh fixture state. Add an explicit
   two-distinct-source-set equivalent-DEFER probe: first decision persists;
   second identical current-head fingerprint within TTL creates exactly one
   suppression artifact plus all new `training_input` edges and zero new
   run/defer/feedback rows; replay writes zero rows. Add an explicit health
   probe for first persist, semantic suppression before 300 seconds, DB-clock
   heartbeat at/after 300 seconds, and application-clock skew immunity. Stop the temporary
   cluster and remove its directory through an EXIT trap, then independently
   verify no matching process, listener, socket, or directory remains.
2. Stop immediately if that regression, cleanup, or residue audit fails. Do
   not reuse the prior unauthorized observation.
3. If it passes, fast-forward only the clean Linux repository from
   `dbc6a936c` to the exact target with `git pull --ff-only` and verify HEAD,
   origin, worktree, and no migration diff.
4. Render the existing `openclaw-alr-shadow.service` template with the exact
   target pin, preserve a private unit backup, run user `daemon-reload`, and
   restart only `openclaw-alr-shadow.service`. Do not restart or signal the
   engine, trading API, watchdog, scanner writer, or any other unit.
5. Run a bounded `420`-second soak, polling no less often than once per 60
   seconds. Capture service active state/PID/restarts, engine PID/start time,
   health attempts/emits/suppressions and ratio, actual rows/bytes, decision
   suppressions, feedback ratios, training-input cursor consumption, oldest
   untrained source, artifact/run/defer/feedback deltas, scanner row count,
   authority mismatches, and unit resource state.
6. Acceptance requires: source pin exact; service active with zero restart
   loop; engine PID/start unchanged; no scanner mutation beyond independent
   normal scanner production; no authority mismatch; semantic-no-delta health
   suppression materially above zero with a DB-clock heartbeat at or before
   the bounded interval; no hot-loop; no untrained-source starvation; and
   complete durable write metrics, and retention deltas exactly `0`. Isolated equivalent-DEFER evidence must
   show new sources consumed through one suppression artifact without another
   run/defer/feedback write.
7. On service/apply failure, stop the ALR unit, restore the prior unit file for
   audit but do not restart it against a mismatched checkout, preserve all
   append-only evidence, and report RCA. Do not reset source, broaden database
   privileges, touch the engine, or synthesize acceptance evidence.

## Explicit exclusions

No migration creation/apply, production role/credential expansion, scanner
write, engine restart/signal, exchange/API/MCP contact, order/probe/cancel/
modify, fill, Guardian/RiskConfig, Decision Lease, global Cost Gate change,
live/mainnet, serving, promotion, proof/edge/profit claim, `_latest` update,
parameter apply, or protected-evidence deletion is requested.
