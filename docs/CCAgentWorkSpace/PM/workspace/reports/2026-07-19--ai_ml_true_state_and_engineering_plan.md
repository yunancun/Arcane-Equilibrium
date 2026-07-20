# AI/ML True-State Audit And Engineering Arrangement

**Report ID**: `AIML-TRUE-STATE-2026-07-19-V1`
**Collected**: 2026-07-19 16:33-17:05 CEST
**Baseline**: `b486c0718d1c26820cdb6308cccf74c686547b22`
**Boundary**: read-only Mac/Git/Linux/service/process/filesystem/source inspection;
no PG write, broker/private call, order/probe, service restart, process kill,
deploy, CI, push, or runtime mutation
**Formal plan**:
`docs/execution_plan/2026-07-19--ai_ml_long_lived_repair_and_landing_plan.md`

## 1. PM Verdict

**Overall: `NOT_LANDED_RUNTIME_BROKEN`.**

The project has built a broad ALR source foundation, but the active machine is
not autonomously learning. Current answers to the operator's durable standard
are:

| Question | Verdict | Reason |
|---|---|---|
| Automatically collect fresh learning data? | `NO` | Engine/Scanner snapshots are stale since 2026-07-18 and ALR ingestion cannot start. |
| Automatically decide the best learning target? | `NO_RUNTIME` | Arbiter source exists, but no active controller consumes fresh Scanner events. |
| Automatically train? | `NO` | Trusted runner is absent; legacy cron lacks LightGBM and is currently hung. |
| Automatically evaluate? | `PARTIAL_SOURCE_ONLY` | Evaluation components exist; no current qualified real fit/OOS result is flowing. |
| Automatically serve model output? | `NO` | Latest serving artifacts are stale reports and explicitly do not load a model. |
| Automatically feed outcomes back? | `NO_CURRENT_CHAIN` | Contracts/repositories exist, but there is no active model decision to attribute and close. |
| Automatically clean useless derived data safely? | `NO` | PG metadata contracts exist, but actual 28 GB filesystem data is unmanaged. |
| Profit-proven? | `NO` | No current candidate-matched after-cost OOS/Demo evidence with real downstream consumption. |

The practical completion estimate is not a single percentage because that
would hide the failed runtime. A defensible layer view is:

- source contracts/schema/tests: substantial but incomplete;
- current runtime operability: failed;
- current autonomous end-to-end vertical slice: absent;
- profit evidence: absent.

## 2. Evidence Ledger

### 2.1 Source And Three-Head State

- planning worktree: clean `agent/ai-ml-formal-engineering-plan-v1` at
  `b486c071...` before report edits;
- Mac `origin/main`: `b486c071...`;
- Linux `/home/ncyu/BybitOpenClaw/srv`: `b486c071...`;
- equality proves source synchronization only, not runtime freshness.

### 2.2 Trading Engine And Scanner

Read-only `engine_watchdog.py --status` returned:

- `engine_alive=false`;
- primary/Demo snapshot age about 135,950 seconds;
- latest primary and Demo snapshots: 2026-07-18 03:02 CEST.

`watchdog_state.json` returned:

- `circuit_broken=true`;
- `restarts_since_recovery=5`;
- last recovery failure: engine socket not ready after the bounded wait;
- engine-down state has remained active since the failure window.

The watchdog service itself is active. Therefore `watchdog active` is not
evidence that the engine or Scanner is active.

Source inspection confirms the intended upstream design is real:

- `ScannerRunner` is created once and runs until cancellation;
- each cycle emits `TradingMsg::ScannerSnapshot`;
- the trading writer inserts `trading.scanner_snapshots`;
- after durable insert, it sends best-effort `pg_notify` and relies on later ALR
  reconciliation if notification fails.

Conclusion: preserve this upstream design; repair runtime rather than adding a
second scanner/scheduler.

### 2.3 ALR Service

Linux service facts:

- `LoadState=loaded`;
- `ActiveState=activating`, `SubState=auto-restart`;
- `MainPID=0`, `ExecMainStatus=1`;
- `NRestarts=23579` at 16:45 CEST and still increasing;
- journal terminal error: `AlrEventConsumerError: source_head_mismatch`.

Installed unit facts:

- unit `ALR_SOURCE_HEAD=275901baa...`;
- checkout head `b486c071...`;
- `ExecStart=/usr/bin/python3 -m ml_training.alr_event_consumer ...`;
- `RestartSec=5`, with no effective bounded restart policy or dependency
  preflight.

Source facts:

- `run_event_consumer()` calls `verify_runtime_source_head()` before it connects
  to PG or opens the listener;
- the check compares the configured value to the whole checkout HEAD;
- an unrelated source commit therefore stops raw data ingestion.

### 2.4 Controller And Legacy Maintenance

No learning controller or worker service unit is installed. No production
controller/worker implementation was found.

The only recurring generic trainer is the daily
`ml_training_maintenance_cron.sh` monolith:

- source explicitly falls back to system Python;
- current runtime executable is `/usr/bin/python3.12`;
- scorer and quantile jobs failed because LightGBM is not installed;
- the current process has stayed alive for more than 13 hours, sleeping on a PG
  socket with no new log output;
- there is no global per-job timeout around the sequential dispatcher;
- the status JSON remains the prior day's `status=error`;
- its command line exposed the PG DSN. The credential is deliberately redacted;
  remediation must remove it from argv/logs and rotate it through a separately
  reviewed post-attestation effect before service recovery.

This is a concrete counterexample to the claim that current training is
long-lived and self-healing.

### 2.5 Schema, Trusted Fit And Serving

Source includes V151-V160 and extensive disposable-PG tests. A same-day bounded
read-only observation made by the now-stopped runtime-refactor task reported all
ten migrations applied in production. The current task did not repeat PG access
because direct ambient `psql` is forbidden until the approved local-socket,
read-only-identity adapter is used. Production schema must be re-attested at
LR0.3 before any writer/restart/deploy/migration; ML0 then freezes the
post-repair cohort. The old TODO statement that V160 is absent is already stale.

Production source-import/caller inspection found:

- `alr_trusted_fit_handshake.py`: no production importer;
- `alr_local_runner.py`: no production importer;
- `alr_local_runner.py` enforces `max_steps <= 1`, so it is an offline
  diagnostic and not a persistent controller;
- the candidate-board flow retains a filesystem/inotify rendezvous path; it is
  not a substitute for the durable PG queue;
- V158-V160 provide durable schema/functions, not a fit process;
- latest `/tmp/openclaw/learning` model-registry/serving artifacts are dated
  2026-06-30;
- `learning_serving_snapshot.py` is artifact-only and explicitly does not load a
  model.

Conclusion: the project has protected contracts around a missing effectful
vertical slice. The next fit work must implement the runner and consumer, not
another packet or validator.

### 2.6 Retention And Storage

- root filesystem: 94% used during observation;
- cost-gate learning lane: 28 GB;
- `/tmp/openclaw/learning`: 40 KB and stale;
- source `alr_retention_repository.py` can quarantine/sweep rows in
  `learning.alr_derived_cache_entries` and records immutable events;
- no source path binds that PG row deletion to safe reclamation of the actual
  learning-lane files;
- the same-day read-only audit observed zero retention entries/events.

Conclusion: current retention is a metadata state machine and dry-run contract,
not active filesystem lifecycle management.

### 2.7 Stopped Long-Lived Branch

The stopped task obeyed the operator stop. It performed no runtime effect, push,
CI or deploy.

Useful:

- branch `agent/long-lived-learning-runtime-v1`;
- commit `0abbc1cd3`, scoped runtime manifest plus 40 passing tests.

Rejected/not ready:

- eight untracked environment/venv prototypes;
- isolated preflight import fails under `python -I`;
- venv rename breaks generated shebangs;
- mutable alias is consumed after hashing;
- filesystem/receipt reviews found hardlink, parent-swap, cross-device and
  TOCTOU risks;
- three E2 surfaces all returned FAIL.

The branch should be preserved until LR1. Cherry-pick/rework only the manifest
commit after a fresh review; do not stage the untracked prototype wholesale.

## 3. Root-Cause Structure

The apparent development loop was caused by treating different proof layers as
interchangeable:

1. contracts and tests were counted as runtime capability;
2. migrations were counted as a trainer;
3. status/report artifacts were counted as serving;
4. head-repin recovery was counted as long-lived operation;
5. cron completion was counted as an autonomous controller;
6. aggregate/counterfactual rows were repeatedly revisited without an active
   fresh-data and independent-entry path.

The engineering plan removes these category errors by requiring a real event
and model to cross each boundary.

## 4. Formal Arrangement

The work is split into exactly two program blocks:

1. `P0-AIML-LONG-LIVED-RUNTIME-REPAIR`: LR0-LR6, ending only at
   `FOUNDATION_READY`;
2. `P1-AIML-END-TO-END-LANDING`: ML0-ML8, progressing through
   `QUALIFIED_LEARNING`, `SERVING_READY` and `AIML_MODULE_LANDED`;
   `PROFIT_PROVEN` remains a separate, data-dependent evidence state.

The detailed acceptance criteria, dependencies, role routing, CI policy,
three-way synchronization rules, estimates and non-goals are in the formal
plan. Root `TODO.md` owns only the two compact dispatch rows.

## 5. Adversarial Review Status

The initial draft received four substantive independent `REJECT` verdicts:

| Review lens | Highest-risk defects found | PM disposition |
|---|---|---|
| OPS/deploy | PG re-attestation was sequenced after a writer restart; source alignment was treated as deploy identity; recovery lacked quiescence ordering and a sufficient soak. | Accepted. LR0 now has a fixed evidence/quiesce/guards/PG/stage/start/watchdog order, exact rollback identity and a 72-hour/two-cycle gate. |
| Runtime/security | Exactly-once was impossible across PG/workers/files; OCI usernames did not separate PG authority; runtime digest was self-attestable; retention was unsafe across stores. | Accepted. The plan now uses at-least-once plus fencing/CAS/reconciliation, separate host UIDs/PG roles, independent process attestation and tombstone-first deletion. |
| Failure injection | Lease expiry, artifact commit and retention could lose or duplicate effects; gates were prose; E4 preceded E2. | Accepted. Crash protocols, versioned validators and builder -> E2 -> E4 order are normative. |
| Quant/evidence | One Scanner event and duplicated rows could masquerade as profit; utility, sample power, multiplicity, final holdout, drift and cohort epochs were underspecified. | Accepted. Transport is profit-ineligible; ML0/ML2/ML4/ML8 now close those evidence boundaries. |

Two interrupted reviews returned `REJECT (UNVERIFIED)` without substantive
inspection and were excluded as non-evidence. The full ranked finding-to-fix
matrix is in the formal plan §10.

All four substantive correction-verification passes returned
`ACCEPT_AFTER_REWORK`. Runtime/security first found one remaining P1 conflict
between the old V150 migration row and the V151-V160 re-attestation boundary;
PM corrected it to `RUNTIME_UNVERIFIED_PENDING_LR0_3_REATTEST`, prohibited
production apply/double-apply from that row, and received final acceptance. No
reviewed P0/P1 remains open in the engineering arrangement.

## 6. PM Sign-Off

**Disposition**: `ACCEPT_FOR_BOUNDED_DISPATCH_AFTER_ADVERSARIAL_REWORK`.

This signs the engineering arrangement, not runtime readiness. The first legal
dispatch is LR0 evidence capture and quiescence. No writer/restart/deploy/
migration is admitted until the approved hash-bound PG read-only receipt passes;
no trading authority is created by this plan.
