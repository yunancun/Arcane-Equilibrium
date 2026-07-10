# PM R2 Request - GLOBAL_QUALIFIED_AUTONOMOUS_LEARNING_SHADOW_V1 WP1 Runtime

Date: 2026-07-10
Authority chain: `PM -> E3 -> BB -> PM`
Exact immutable target: `7d1c247947f0fb6c139f8a0583c5e6ed6ae62c70`
State requested: `WP1_R2_ISOLATED_SOURCE_THEN_ALR_SERVICE_ONLY_SOAK`

R2 disposition: `FAILED_PRE_FIXTURE_COMMAND_AND_CLEANED`. The detached source
worktree correctly lacked the gitignored Mac virtualenv, but the R2 script
incorrectly resolved Python under that worktree. It exited `127` before ALR
fixture ingestion. Independent residue audit then found the disposable PG
still running, proving the inner EXIT trap insufficient. The authorized
rollback stopped PID `13949`, removed `/private/tmp/alr-wp1-gated.vZoC1x4V`,
and reverified process/port/directory/worktree residue clear. Linux and
production were untouched. R2 cannot be retried.

R1 stopped before execution when its exact-head guard observed concurrent
GUI-only commits. No PostgreSQL, Linux sync, service, or runtime action ran;
port/process/tmp residue checks were clear. R2 is fresh and non-retroactive.

The target adds only two GUI commits after the previously approved
`5ae414521`; `5ae414521..7d1c24794` has no ALR, migration, role-contract,
service-template, Rust engine, exchange connector, Guardian, Decision Lease,
Cost Gate, order, serving, promotion, or credential diff. WP1 behavioral code
remains `c080c552b`.

## Concurrency-safe target handling

- After approval, create a detached temporary source worktree at the exact
  target for the disposable regression. Shared-main advancement does not
  change the immutable target.
- At execution, fetch remote main read-only for comparison. It may have
  advanced only if `git diff TARGET..origin/main` is empty for
  `program_code/ml_training`, `sql/migrations`, `sql/contracts`,
  `helper_scripts/deploy/openclaw-alr-shadow.service.template`, Rust engine,
  and exchange/authority paths. Any relevant diff invalidates R2.
- Linux must be clean, current HEAD an ancestor of TARGET, and migration/
  contract diff from Linux HEAD to TARGET empty. Merge exactly TARGET with
  `git merge --ff-only TARGET`; never merge a moving branch tip. Reassert Linux
  HEAD equals TARGET and clean. Service pin equals TARGET.

## Exact authorized sequence

1. One Unix-socket-only Homebrew PostgreSQL 16 attempt under fresh
   `/tmp/alr-wp1-gated.*`, `umask 077`, port `55449`, local trust/host reject,
   immediate trap, no ambient DB variables, TCP listener, brew service, or
   container. Recreate `trading_ai`, schema, role, V030/V151-V156, and the
   existing shadow contract independently per canonical harness.
2. Synthetic scanner rows may be inserted only by the disposable admin; ALR
   rows must flow through the real adapter/persistence path as `alr_shadow`.
3. Run canonical health, operational, and outcome-feedback harnesses. The
   feedback fixture's second four rows must have a true semantic delta.
4. Explicit equivalent-DEFER fixture: first four rows produce one run; four
   newer distinct but semantically identical rows, same `"a" * 40` fixture
   head and within 1800 seconds, produce exactly suppression `1`, artifact
   rows `1`, training-input edges `4`, sources consumed `4`, and new
   run/defer/feedback rows `0`; replay writes `0`. All authority values remain
   false/zero.
5. Explicit health proof: first persist; skewed-app-time no-delta suppression
   with zero rows; disposable-admin recorded time older by 301 seconds; skewed
   app time still yields DB-clock HEARTBEAT and two rows; shadow UPDATE denied.
6. Stop/remove the disposable cluster, then independently prove no matching
   process, TCP listener, socket, exact temp directory, or old QA residue.
   Any failure stops before Linux.
7. Recheck production derived cache `0`, exact source/privileges and fresh
   baselines. Perform exact-target Linux merge. Back up/hash the private unit,
   replace only its ALR source pin, atomically install, daemon-reload, and
   restart only `openclaw-alr-shadow.service`.
8. Poll at t=0/60/120/180/240/300/360/420. Require stable new ALR PID,
   restarts `0`; engine/API/watchdog identity unchanged; target-session metrics
   complete; health suppression count >0 and ratio >=0.50; health row and byte
   rates each <50% of the immediately preceding stale-unit hour; 60-120 health
   attempts; no starvation/hot-loop; retention delta 0; authority mismatch
   0/0; scanner INSERT denied; resources within 512M/64 tasks. A natural
   heartbeat is required only after a same-semantic 300-second epoch; the
   deterministic disposable proof is mandatory.
9. On failure after sync, stop only ALR, restore/hash-check the prior unit,
   daemon-reload, leave ALR inactive, preserve append-only evidence, and do not
   reset source, restart stale pin, delete evidence, retry, or signal engine.

No production migration/role/credential change, scanner write, engine/API/
watchdog signal, exchange/API/MCP contact, order/fill/probe, Guardian/RiskConfig,
Decision Lease, global Cost Gate change, live/mainnet, serving, promotion,
latest pointer, parameter apply, proof/profit claim, or protected-evidence
deletion is requested.
