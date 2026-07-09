# PM Remediation Schedule — 62-Finding Full Audit

Date: 2026-04-28
PM scope: remediation planning for `docs/audit/final_record_zh.md`
Source audit: `docs/audit/audit.md`, `docs/audit/final_summary.md`, `docs/audit/remediation_groups.md`, `docs/audit/final_record_zh.md`
Status: PLAN READY

## 0. PM Decision

We will fix all 62 confirmed audit findings. Do not treat this as one large patch. Treat it as six remediation batches with explicit gates.

Facts:
- Total findings: 62
- Severity: P1 29, P2 29, P3 4, P0 0
- Live-release blockers exist even without P0 severity.
- The dominant risk is fragmented authority across Rust engine, FastAPI, scripts, schedulers, secrets, and DB writers.

PM call:
- Batch A must land first.
- Batch B/C/D may be partially parallel after Batch A design is accepted, but final merge order must preserve gates.
- Batch F must remain observation-only until A-E are closed unless a specific ML safety fix is needed by an earlier batch.
- Every implementation batch must include E2 review and E4 regression before PM sign-off.

## 1. Preflight

Before starting fixes:

| Item | Action | Owner | Exit |
|---|---|---|---|
| Branch/worktree state | Preserve current dirty worktree; identify user-owned vs Codex-owned edits before modifying files. | PM | No unrelated changes reverted. |
| Runtime drift | Investigate paper stale in Linux watchdog or record as accepted current runtime state. | PM/E4 | `engine_watchdog` state explained before deploy. |
| Finding ledger | Create a tracked matrix with 62 IDs, batch, owner, status, tests, commit. | PM | 62/62 IDs represented exactly once. |
| Baseline tests | Capture current Rust/Python/control API baseline on Linux. | E4 | Baseline saved in batch report. |

Estimated elapsed: 0.5-1 day.

## 2. Batch A — Live Write Boundary Freeze

Goal: no live close/cancel/flatten/auth renewal path exists outside one signed, mode-aware, operator-authorized boundary.

Findings:
- `LP-001`, `OE-007`, `OS-001`, `RC-001`, `SW-002`

Required chain:
- PM -> CC(default) + E3(explorer) + BB(default) + PA(default) -> E1(worker) + E1a(worker) -> E2(explorer) -> E4(worker) -> QA(worker) -> PM

Work split:
- E1 owns Rust live auth watcher, live pipeline respawn, command sender refresh, exchange reduce-only flatten semantics.
- E1a owns FastAPI live renew/close routes and operator live flatten scripts.
- CC owns 16-principle check, especially #1, #2, #3, #4, #5, #6.
- E3 owns authorization and bypass review.
- BB owns Bybit-side reduce-only / close / cancel compatibility.

Exit gate A:
- Renew live authorization requires exact live-reserved mode.
- Direct REST live fallback is removed or separately emergency-authorized.
- Emergency flatten cannot mark state flat before exchange-aware reduce-only dispatch is confirmed or terminally failed.
- Live respawn refreshes command senders or uses dynamic slots.
- Tests prove fail-closed behavior for non-live-reserved, expired auth, missing sender, and direct script path.

Estimate:
- optimistic 2 days
- median 4 days
- pessimistic 6 days

## 3. Batch B — Critical Auth, Secrets, And API Exposure

Goal: all state-changing routes share operator/scope authorization; reusable privileged credentials disappear from repo/log/proxy/process surfaces.

Findings:
- `DAPI-001`, `DAPI-002`, `DAPI-003`, `DAPI-004`, `DAPI-005`, `DAPI-006`
- `RC-003`
- `SC-001`, `SC-002`, `SC-003`, `SC-004`, `SC-005`, `SC-006`, `SC-007`

Required chain:
- PM -> E3(explorer) + PA(default) -> E1a(worker) -> E2(explorer) -> E4(worker) -> PM

Work split:
- E1a owns FastAPI auth dependencies, dashboard routes, model registry read routes, DB health redaction, reverse proxy headers.
- E1 owns any shell/runtime secret surface touched by scripts.
- E3 owns credential exposure, cookie, bearer, proxy, and route-bypass review.

Exit gate B:
- Mutating budget/risk/config routes require operator identity and route-specific write scope.
- Server decides audit identity; client-supplied actor cannot authorize a write.
- Blank GUI password is rejected.
- Privileged auto-generated bearer is not printed.
- Committed Grafana bearer credential is removed and rotation is documented.
- Dashboard/model/DB detail routes either require auth or expose only coarse liveness.
- Proxy strips cookies and authorization unless explicitly required.

Estimate:
- optimistic 3 days
- median 5 days
- pessimistic 8 days

## 4. Batch C — Trading Record Durability

Goal: WS batches, REST dispatch failures, DB writer failures, and migration gaps cannot silently erase or misstate trading facts.

Findings:
- `OE-001`, `OE-002`, `OE-003`, `OE-004`, `OE-005`, `OE-008`, `OE-009`
- `DBW-001`, `DBW-002`, `DBW-003`, `DBW-004`, `DBW-005`

Required chain:
- PM -> PA(default) + FA(default) -> E1(worker) + E1a(worker) -> E2(explorer) -> E4(worker) -> QA(worker) -> PM

Work split:
- E1 owns Rust private WS parsing, execution listener dispatch, pending order/close terminal failure semantics, fill idempotency, writer channels.
- E1a owns SQL migration ordering, Python/API DB pool reset, migration/audit scripts.
- FA owns trading lifecycle reconstruction acceptance criteria.

Exit gate C:
- Bybit private WS `data` arrays emit all events.
- REST dispatch failure emits terminal events and clears or marks pending state.
- Fill persistence uses Bybit `exec_id` or equivalent exchange-native idempotency.
- Writer insert failures do not clear buffers without durable retry/outbox/alert.
- Bounded channel full/closed conditions expose counters and do not silently drop critical rows.
- `learning.exit_features` migration is in real migration order.
- Explicit auto-migrate fails closed on `NoPool`.
- API DB pool rolls back/reset before returning connections.

Estimate:
- optimistic 5 days
- median 8 days
- pessimistic 12 days

## 5. Batch D — Risk And Config Fail-Closed

Goal: missing config, stale H0 refresh, rejected IPC updates, and partial strategy parameter updates cannot weaken risk enforcement.

Findings:
- `RC-002`, `RC-004`, `RC-005`, `RC-006`
- `SADF-002`, `SADF-003`
- `LP-002`, `OE-006`

Required chain:
- PM -> CC(default) + PA(default) -> E1(worker) + E1a(worker) -> E2(explorer) -> E4(worker) -> PM

Work split:
- E1 owns Rust risk/config admission paths, H0 state persistence, IPC applied-state acknowledgement, timeout behavior.
- E1a owns strategy parameter validation/update atomicity and restart script package ID fixes.
- CC owns fail-closed validation against root principles #4, #5, #6.

Exit gate D:
- Demo/Live missing or broken risk/strategy config refuses unsafe start instead of default-active behavior.
- H0 periodic refresh preserves cooldown and kill-switch state.
- Risk governor cascades and `constraints_for()` apply consistently at order admission.
- Legacy `update_risk_config` returns success only after send/application success.
- Strategy parameter updates validate full payload before mutating runtime state.
- Clean/fresh restart scripts use `openclaw_engine` and have package-ID smoke coverage.
- Close retry timeout behavior matches operator-visible budget.

Estimate:
- optimistic 3 days
- median 5 days
- pessimistic 7 days

## 6. Batch E — Operator And Runtime Ownership

Goal: watchdog, cron, multi-worker startup, API restart, DB reset, launchd, and reporting scripts are idempotent, service-manager aware, and hard to misuse.

Findings:
- `SW-001`, `SW-003`, `SW-004`, `SW-005`, `SW-006`, `SW-007`
- `OS-002`, `OS-003`, `OS-004`, `OS-005`, `OS-006`, `OS-007`
- `DAPI-007`

Required chain:
- PM -> E3(explorer) + PA(default) -> E1(worker) + E1a(worker) + TW(worker) -> E2(explorer) -> E4(worker) -> PM

Work split:
- E1 owns watchdog/maintenance leases, runtime locks, scheduler leader election where Rust/runtime-owned.
- E1a owns shell scripts, launchd preflight, DB reset confirmation, API restart route removal/replacement.
- TW owns operator runbook wording and destructive-action confirmation text.
- E3 owns destructive path and process-kill safety review.

Exit gate E:
- Clean/fresh maintenance sets leases before watchdog can race restart.
- DB reset requires DB/environment fingerprint confirmation that wrappers cannot auto-generate.
- Broad `pkill -f` and port kills are replaced with PID/service/cwd validation.
- Maintenance flags are cleaned with `EXIT`/`ERR`/signal traps.
- API worker no longer starts unmanaged uvicorn.
- Cron wrappers have overlap locks.
- Multi-worker schedulers/monitors/writers have leader election, locks, or explicit single-worker ownership.
- Launchd preflight rejects missing env/secrets/placeholders.
- DB bootstrap removes application-role superuser and quotes passwords safely.
- Telegram/report JSON uses an encoder and avoids token exposure where feasible.

Estimate:
- optimistic 4 days
- median 7 days
- pessimistic 10 days

## 7. Batch F — ML And Agent Autonomy Readiness

Goal: ML, LinUCB, Teacher, and Strategist remain observational or explicitly bounded until schema, labels, promotion, and reward loops are coherent.

Findings:
- `MLM-001`, `MLM-002`, `MLM-003`, `MLM-004`, `MLM-005`
- `SADF-001`, `SADF-004`, `SADF-005`, `SADF-006`
- `LP-003`

Required chain:
- PM -> QC(default) + MIT(default) + AI-E(default) + PA(default) -> E1(worker) + E1a(worker) -> E2(explorer) -> E4(worker) -> QA(worker) -> PM

Work split:
- MIT owns feature schema/hash, training row selection, label finality, model registry consistency.
- QC owns reward/arm definitions and strategy decision integrity.
- AI-E owns model-routing/cost implications if model serving behavior changes.
- E1/E1a split depends on Rust runtime vs Python training/API surface.

Exit gate F:
- Runtime loading enforces feature definition/schema hash compatibility.
- q10/q50/q90 ONNX quantile trio is promoted atomically as one serving unit.
- Training data selection respects row-level schema/hash metadata and does not zero-fill incompatible drift.
- Partial close labels remain provisional until full close quantity coverage is known.
- LinUCB runtime/trainer/persistence use compatible arm-space and reward queries.
- Teacher directives target explicit active recipients; disabled Paper does not silently drain authoritative directives.
- Observation-only metadata is marked as such and cannot be treated as accepted order evidence.
- `boost_arm` returns unsupported/no-op until it has a real side effect.
- Strategist Live promotion has release-mode guards.
- Paper auto-start script is updated or retired.

Estimate:
- optimistic 5 days
- median 8 days
- pessimistic 12 days

## 8. Merge And Deployment Order

Recommended merge sequence:

1. Preflight ledger commit.
2. Batch A fully merged and reviewed.
3. Batch B1 auth writes + B2 secrets lockdown.
4. Batch C core execution durability.
5. Batch D fail-closed config/risk.
6. Batch E runtime ownership.
7. Batch B read exposure leftovers if not already merged.
8. Batch C/D quick wins if not already merged.
9. Batch F ML/agent readiness.
10. Final 62/62 closure report.

Do not deploy a partial live-boundary change without its paired tests. For high-risk batches, deploy to Linux with `--rebuild --keep-auth` only after E4 confirms the current runtime state and PM confirms no hard-boundary drift.

## 9. Wall-Clock Plan

Serial total:
- optimistic 22.5 working days
- median 37 working days
- pessimistic 56 working days

With controlled parallelism after Batch A:
- optimistic 14 working days
- median 22 working days
- pessimistic 34 working days

Parallelism rule:
- Do not parallelize overlapping Rust execution/risk files unless scopes are isolated.
- FastAPI auth, secrets/scripts, DB migrations, and ML can run in parallel only after Batch A interface decisions are frozen.
- E2 and E4 must review the integrated result, not only isolated patches.

## 10. Tracking Matrix

| Batch | Findings | Count |
|---|---|---:|
| A | `LP-001`, `OE-007`, `OS-001`, `RC-001`, `SW-002` | 5 |
| B | `DAPI-001`, `DAPI-002`, `DAPI-003`, `DAPI-004`, `DAPI-005`, `DAPI-006`, `RC-003`, `SC-001`, `SC-002`, `SC-003`, `SC-004`, `SC-005`, `SC-006`, `SC-007` | 14 |
| C | `OE-001`, `OE-002`, `OE-003`, `OE-004`, `OE-005`, `OE-008`, `OE-009`, `DBW-001`, `DBW-002`, `DBW-003`, `DBW-004`, `DBW-005` | 12 |
| D | `RC-002`, `RC-004`, `RC-005`, `RC-006`, `SADF-002`, `SADF-003`, `LP-002`, `OE-006` | 8 |
| E | `SW-001`, `SW-003`, `SW-004`, `SW-005`, `SW-006`, `SW-007`, `OS-002`, `OS-003`, `OS-004`, `OS-005`, `OS-006`, `OS-007`, `DAPI-007` | 13 |
| F | `MLM-001`, `MLM-002`, `MLM-003`, `MLM-004`, `MLM-005`, `SADF-001`, `SADF-004`, `SADF-005`, `SADF-006`, `LP-003` | 10 |
| Total | all findings represented exactly once | 62 |

## 11. Final Acceptance

The audit is not closed until:

- 62/62 findings have status `fixed`, `false-positive`, or explicitly accepted with compensating control.
- Every accepted item has PM + CC/E3 approval when it touches live/auth/security.
- Linux E4 regression passes on the integrated branch.
- Runtime watchdog state is documented after final deploy.
- `TODO.md`, `CLAUDE.md`, PM memory, and operator-facing release checklist are updated.
- Final PM sign-off includes commit range, test baseline, residual risks, and live-release gate status.

PM SIGN-OFF: PLAN READY
