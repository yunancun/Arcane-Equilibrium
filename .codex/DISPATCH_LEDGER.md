# Codex Dispatch Ledger

Last updated: 2026-06-26

Purpose:
- keep a durable record of meaningful PM-first dispatch decisions
- show which repo roles were used for a task
- prevent workflow drift into anonymous `worker/explorer` execution

Entry format:

```text
YYYY-MM-DD HH:MM TZ
Task:
- short task statement

Chain:
- PM -> PA(default) -> E1(worker) -> E2(explorer) -> PM

Ownership:
- PA(default): design / scope / risk framing
- E1(worker): implementation in specific files
- E2(explorer): adversarial review

Result:
- outcome, blocker, or next action
```

2026-06-26 14:31 CEST
Task:
- Close `P1-RUNTIME-HEALTH-HYGIENE-AUTH-TYPED-CONFIRM-GUARD-RUNTIME-SYNC-APPLY` with the reviewed runtime source + expected-head sync.

Chain:
- PM -> E3(explorer, prior review) -> PM

Ownership:
- PM: create session state, verify anti-repeat delta, execute the exact ff-only runtime source sync and exact expected-head-only crontab replacement, run post-checks, update TODO/report/changelog/worklog/memory.
- E3(explorer): prior runtime/security review defining the allowed future apply envelope, forbidden actions, and post-checks.

Result:
- Runtime source fast-forwarded from `dd22810e` to `b224c759`.
- Crontab expected-head pins changed old/target `11/0 -> 0/11` with line count `70`.
- Natural auth artifact now suppresses exact typed confirm while preflight/auth fields are incomplete and still grants no authority.
- Status `DONE_WITH_CONCERNS`; next blocker remains `P0-BOUNDED-PROBE-AUTHORIZATION`, blocked by missing machine-checkable scoped authorization.

2026-06-26 06:36 CEST
Task:
- Close `P1-RUNTIME-HEALTH-HYGIENE-CRON-POST-ALIGNMENT-HYGIENE-SNAPSHOT` with a no-mutation supplied-snapshot hygiene packet.

Chain:
- PM -> E3(explorer) -> PM

Ownership:
- PM: create session state, run anti-repeat, collect timestamped read-only snapshots, run local supplied-snapshot builder, update TODO/report/changelog/worklog/memory.
- E3(explorer): runtime/security review defining allowed read-only command classes, forbidden mutations, target-head constraint, and acceptance checks.

Result:
- Packet `runtime_health_hygiene_packet_v1` is `RUNTIME_HEALTH_HYGIENE_CLEAN_SOURCE_ONLY`.
- Runtime source, cron expected-head, user API/watchdog service ownership, and reduced artifact compatibility are clean.
- Status `DONE_WITH_CONCERNS`; next blocker remains `P0-BOUNDED-PROBE-AUTHORIZATION`, blocked by missing machine-checkable bounded Demo authorization.

2026-06-26 06:24 CEST
Task:
- Close `P1-RUNTIME-HEALTH-HYGIENE-CRON-EXPECTED-HEAD-DRIFT-REVIEW` and normalize TODO back to the active-dispatch standard.

Chain:
- PM -> E3(explorer) -> PM

Ownership:
- PM: create/update session state, collect runtime crontab/source/user-service evidence, apply the reviewed exact expected-head-only crontab replacement, update TODO/report/changelog/worklog/memory.
- E3(explorer): runtime/security review defining the allowed literal replacement, forbidden actions, rollback condition, and post-checks.

Result:
- Crontab expected-head pins now align with runtime code head `0246b263`; old literal count `0`, new literal count `11`, line count `70`.
- User `openclaw-trading-api.service` and `openclaw-watchdog.service` remain active under `systemctl --user`; no restart/rebuild/PG/Bybit/API/Cost Gate/authority/proof action occurred.
- Status `DONE_WITH_CONCERNS`; next blocker is a read-only post-alignment hygiene snapshot, paused until operator resumes.

2026-06-26 06:08 CEST
Task:
- Close `P1-RUNTIME-HEALTH-HYGIENE-68-RUNTIME-SYNC-REVIEW` with a source-only Linux fast-forward and direct [68] runtime verification.

Chain:
- PM -> E3(explorer) -> PM

Ownership:
- PM: create session state, collect runtime preflight, execute exact ff-only source sync, run post-checks, update TODO/report/changelog/worklog/memory.
- E3(explorer): runtime/security review defining allowed command class, forbidden actions, and required post-checks.

Result:
- Linux `trade-core` source is clean at `0246b263`.
- Direct [68] read-only PG check returns `PASS` with local close/risk rows visible as `local_lineage_residual`.
- Status `DONE_WITH_CONCERNS` because crontab expected-head pins still reference `d2cd70d0`; crontab alignment is a separate E3 checkpoint.

2026-06-26 05:50 CEST
Task:
- Close `P1-RUNTIME-HEALTH-HYGIENE-LOCAL-LINEAGE-68-STALE-WORKING` as a source-only health [68] local-lineage residual patch.

Chain:
- PM -> E2(explorer) -> E4(explorer) -> PM

Ownership:
- PM: create/check session state, apply anti-repeat, implement the source/test patch, update TODO/report/changelog/worklog/memory.
- E2(explorer): adversarial source review for exposure-hiding, classifier scope, and fail-closed behavior.
- E4(explorer): verification review and coverage gap check.

Result:
- Health [68] now reports close/risk local `Working` rows without same-symbol local filled position as `local_lineage_residual`, not entry resting exposure.
- Ordinary entry exposure and close/risk rows with filled position still count and fail closed.
- Status `DONE_WITH_CONCERNS` because the patch has not been synced to Linux runtime; next checkpoint is `P1-RUNTIME-HEALTH-HYGIENE-68-RUNTIME-SYNC-REVIEW`.

2026-06-26 05:37 CEST
Task:
- Advance `P0-BOUNDED-PROBE-AUTHORIZATION` to a no-authority AVAX review-ready checkpoint and fix stale TODO next-action state.

Chain:
- PM -> E3(explorer) -> BB(explorer) -> PM

Ownership:
- PM: create/check session state, apply anti-repeat, generate defer-only local helper artifacts, update TODO/report/changelog/worklog/memory.
- E3(explorer): runtime/security authority-boundary review for artifact-only candidate-scoped authorization.
- BB(explorer): exchange/execution-realism authority-boundary review and order-path blockers.

Result:
- First-attempt touchability/bootstrap source blocker was classified `NO-OP_ALREADY_DONE`.
- Fresh defer-only authorization packet is review-ready but emits no authorization object and no active probe/order authority.
- Actual bounded Demo grant remains blocked until a valid structured standing Demo authorization or exact typed confirm exists, followed by fresh E3/BB order-envelope/runtime/reconciliation review.

2026-06-26 05:23 CEST
Task:
- Close `P0-PROFIT-CANDIDATE-SELECTION` with exactly one review-only bounded Demo candidate after the clean exchange-book checkpoint.

Chain:
- PM -> QC(explorer) -> MIT(explorer) -> BB(explorer) -> PM

Ownership:
- PM: create session state, inventory false-negative/MM/AVAX evidence, select exactly one candidate, update TODO/report/changelog.
- QC(explorer): statistical/proof-exclusion review and comparison against MM current-fee path.
- MIT(explorer): lineage, freshness, and overclaim review.
- BB(explorer): cap/min-notional, execution-realism, and later authority-boundary review.

Result:
- Selected `grid_trading|AVAXUSDT|Sell` as review-only candidate; status `DONE_WITH_CONCERNS`.
- No authority was granted. Active bounded probe/order remains blocked by missing candidate-matched touchability.
- Next safe action after the requested pause is source/read-only first-attempt touchability bootstrap under `P0-BOUNDED-PROBE-AUTHORIZATION`.

2026-06-26 04:56 CEST
Task:
- Close `P1-RUNTIME-HEALTH-HYGIENE-CONTROL-API-AUTH-TOKEN-PATH` with a secret-safe runtime-local authenticated read-only control API proof.

Chain:
- PM -> E3(explorer) -> PM

Ownership:
- PM: create session state, choose a read-only authenticated route, execute the one approved runtime-local probe, record TODO/report/changelog.
- E3(explorer): review route safety and token-handling constraints.

Result:
- E3 approved exactly one `GET /api/v1/backtest/status`; runtime-local token-file probe returned HTTP `200` with sanitized artifacts under `/tmp/openclaw/audit/control_api_auth_token_path/20260626T025405Z_*`.
- The prior cleanup `401` is narrowed to Mac-vs-runtime token-source alignment.
- Next action is a fresh `PM -> E3 -> BB -> PM` cleanup envelope plus fresh demo pre-inventory; no cleanup/order authority was granted.

2026-06-26 05:18 CEST
Task:
- Close `P0-PROFIT-EVIDENCE-QUALITY-DEMO-RESIDUAL-CLEANUP-ACTION-REFRESH-E3-BB` with one reviewed demo cleanup action and independent post-action exchange inventory.

Chain:
- PM -> E3(explorer) -> BB(default) -> PM

Ownership:
- PM: create session state, execute the approved one-shot runtime-local cleanup path, collect pre/post full-scan evidence, update TODO/report/changelog.
- E3(explorer): security/runtime review for token, CSRF, helper absence, and one-time inline inventory constraints.
- BB(default): Bybit endpoint/scope review, caps, full-scan pre/post requirements, and proof-exclusion policy.

Result:
- Pre-inventory was inside caps; one `POST /api/v1/strategy/demo/session/stop` returned HTTP `200`, `closed_all=true`, `partial_failure=false`; independent post-inventory shows open orders `0` and nonzero positions `0`.
- Cleanup rows remain risk hygiene only, not Cost Gate, bounded-probe, promotion, or PnL proof.
- Next active blocker is `P0-PROFIT-CANDIDATE-SELECTION`.

2026-06-18 23:42 CEST
Task:
- Close `P3-SUB-AGENT-HYGIENE-SOP-CARGO-TEST-AFTER-ATOMIC` by turning the existing sub-agent hygiene SOP into a Codex dispatch-time requirement.

Chain:
- PM -> PM

Ownership:
- PM: inspect existing SOP and Codex dispatch rules, update governance docs, preserve Linux cargo/atomic restart boundary, and archive the TODO row.

Result:
- `.codex/SUBAGENT_EXECUTION_RULES.md` and `.codex/AGENT_DISPATCH_PROTOCOL.md` now require `hygiene_sop`, `verification_surface`, and Linux write policy for delegated Rust/Cargo/Linux-runtime/PG/deploy work.
- Sub-agents are explicitly barred from Linux cargo and unsupervised restart; Rust delegated work must report focused Mac cargo/source verification or an explicit skip reason.
- No code, runtime, deploy, DB, auth, risk, order, or trading mutation.

2026-05-16 22:19 CEST
Task:
- Normalize all CCAgent role profiles and memories after the memory slimming / TODO-first decision.

Chain:
- PM -> PM

Ownership:
- PM: inspect all role profile/memory files, define shared standard, update role docs, preserve historical memory, and verify stale active-state wording is removed.

Result:
- Added `docs/agents/role-profile-memory-standard.md`.
- All role profiles now point to the shared contract; all role memories now declare historical-memory interpretation.
- Active state remains routed to `TODO.md`; no historical memory body was deleted.

2026-05-15 22:13 CEST
Task:
- Integrate `W-AUDIT-8b` Funding Skew Directional QC/MIT/BB review and define the Stage 0R replay design boundary.

Chain:
- PM -> QC(default) + MIT(default) + BB(default) -> PM

Ownership:
- QC(default): hypothesis/statistical gates, K/DSR/PBO, sample floors
- MIT(default): raw panel data contract, stale/leakage controls, funding attribution, CV protocol
- BB(default): Bybit funding/OI semantics, interval/source-mode fields, REST/WS/rate-limit posture
- PM: integrate verdicts into spec v0.2, TODO/active-plan/memory/report updates

Result:
- `W-AUDIT-8b` conditionally approved for Stage 0R replay design only.
- Strategy implementation and demo spend remain blocked.
- Next task is PA/E1 packet for read-only `funding_skew_directional.v0_2` query/report.

2026-05-15 21:53 CEST
Task:
- Finalize `P1-A4C-RCA-1` revise-or-archive verdict and start the `W-AUDIT-8a C1` standalone proof path.

Chain:
- PM -> QC(default) + MIT(default) -> PM
- PM -> BB proof path (isolated public WS run; BB sign-off still pending)

Ownership:
- QC(default): alpha/statistical verdict on A4-C RCA and threshold probe
- MIT(default): data/methodology verdict on A4-C RCA and acceptable future reopen triggers
- PM: final queue decision, TODO/active-plan/memory sync, and C1 proof start on `trade-core`

Result:
- `P1-A4C-RCA-1` closed no-revive; `P1-A4C-REV-1` not opened.
- 24h isolated `allLiquidation.BTCUSDT` proof started on `trade-core` PID `4100789`; C1 remains blocked until final report + BB/MIT sign-off.
- Active alpha lane shifts to `W-AUDIT-8b` Funding Skew review + Stage 0R replay design while C1 runs.

2026-04-28 22:20 CEST
Task:
- Harden Codex startup and dispatch identity rules for this repository

Chain:
- PM -> PM

Ownership:
- PM: establish git-root `AGENTS.md`, add sub-agent execution rules, make PM role part of mandatory boot order

Result:
- `srv/AGENTS.md` is now the repo-synced entry rule file
- `.codex/SUBAGENT_EXECUTION_RULES.md` forbids anonymous runtime-only role reporting
- `.codex/agents/PM.md` is now in the default boot order

2026-04-29 01:20 CEST
Task:
- Complete 62-finding remediation Batch B: critical auth, secrets, and API exposure.

Chain:
- PM -> E3(explorer) + PA(default) -> E1/E1a(worker) -> E2(explorer) -> E4(worker) -> PM

Ownership:
- PA(default): route-family scope design and implementation split
- E3(explorer): Batch B security surface map and bypass review
- E1/E1a(worker): platform secret surface hardening
- E2(explorer): adversarial review; found live/demo scope, Grafana bind, and SC-005 residual blockers
- E4(worker): verification rounds; PM fixed stale blocker reports and reran final checks

Result:
- Batch B fixed locally and tracked in `docs/audit/remediation_tracking.md`
- Sign-off written to `docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-29--batch_b_critical_auth_secrets_api_signoff.md`
- No deploy/restart performed

2026-04-29 02:12 CEST
Task:
- Complete 62-finding remediation Batch C: trading record durability.

Chain:
- PM -> PA(default) + FA(default) -> E1/E1a(worker) -> E2(explorer) -> E4(worker) -> PM

Ownership:
- PA(default): implementation scope, batch boundaries, and acceptance criteria
- FA(default): trading-record durability risk framing and verification priorities
- E1/E1a(worker): Rust/Python implementation across event consumer, database writers, session stop/close-all, migrations, and DB pool
- E2(explorer): adversarial review of Batch C behavior and residual risk
- E4(worker): read-only Python verification; found Batch B auth fixture drift in direct handler tests
- PM: fixed direct-test authenticated actors, reran verification, and closed tracking/signoff docs

Result:
- Batch C fixed locally and tracked in `docs/audit/remediation_tracking.md`
- Sign-off written to `docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-29--batch_c_trading_record_durability_signoff.md`
- No deploy/restart performed

2026-04-30 21:25 CEST
Task:
- Clean up oversized active docs, archive closed history, recalibrate current engineering progress, and update README + Linear.

Chain:
- PM -> CC(default) + FA(default) + E5(explorer) + PA(default) + MIT(default) -> PM

Ownership:
- CC(default): identify stale/archivable governance content and hard-boundary text that must remain
- FA(default): reassess completed vs active functional work
- E5(explorer): document bloat / archive target audit
- PA(default): latest work arrangement and Linear mirroring plan
- MIT(default): runtime/data calibration against current source and healthcheck state
- PM: archive snapshots, trim active docs, update README/TODO/CLAUDE/Codex memory, update Linear, and preserve dirty GUI files untouched

Result:
- Pre-cleanup snapshots archived under `docs/archive/2026-04-30--*-pre-cleanup-snapshot.md`
- `README.md`, `TODO.md`, and `CLAUDE.md` now describe current 2026-04-30 active state
- Linear project and issues updated as a high-level mirror without publishing secrets or detailed runtime internals
- Correction: after operator feedback, `TODO.md` was restored to its v3 single-timeline record shape; only the stale active-mainline block was removed to `docs/archive/2026-04-30--TODO-stale-active-mainline.md`

2026-05-07 CEST
Task:
- Continue REF-21 replay after operator asked to assess parallel dispatch and proceed.

Chain:
- PM -> MIT(explorer) + BB/E2(explorer) + QA(explorer) -> PM/E1-local integration -> E2(explorer) + E4(worker) -> PM

Ownership:
- MIT(explorer): V058/V059/V061 production DB state and backfill path.
- BB/E2(explorer): Bybit public-data realism and scanner turnover reconstruction.
- QA(explorer): Linux one-click replay execution prerequisites.
- PM/E1-local integration: backfill helper, turnover fixture propagation, docs/TODO update.
- E2(explorer): adversarial review of current diff.
- E4(worker): targeted regression verification.

Result:
- Source/test checkpoint added for V058/V059 backfill helper and Bybit kline turnover preservation.
- E2 returned two P1 findings on status coverage and historical-window timestamp visibility; fixes added `--asof` / `--freeze-asof` split and explicit Trading/PreLaunch/Delivering/Closed status fetch. E2 follow-up verdict closed both.
- E4 follow-up verified Python targeted tests 9/0, project-venv Bybit dry-run 1459 raw rows, and `git diff --check`; Linux apply then exposed dated-futures symbols outside V058 schema, so a follow-up fix filters symbols to the V058 contract and local targeted tests now pass 10/0 with 905 compatible dry-run rows.
- Runtime follow-through completed after source sync: Linux V060/V061 apply, V058/V059 backfill, release `replay_runner` rebuild, API reload, and current-config V058 full-chain smoke all passed. Remaining work is recurring V058 snapshots plus order-book/ticker fidelity, not this checkpoint's deploy path.

2026-05-16 CEST
Task:
- Standardize memory slimming and context loading for Claude/Codex sessions.

Chain:
- PM local docs/governance update; no sub-agent dispatch because this was a
  narrow operating-rule refactor requested by the operator.

Ownership:
- PM: source routing, TODO maintenance standard, startup sequence updates, and
  memory compaction.

Result:
- New source routing docs: `docs/agents/context-loading.md` and
  `docs/agents/todo-maintenance.md`.
- `CLAUDE.md` and `.codex/MEMORY.md` now hold operating memory instead of
  current-state ledgers.
- Startup routing updated in `AGENTS.md`, `.claude/agents/PM.md`,
  `.codex/agents/PM.md`, `.codex/AGENT_DISPATCH_PROTOCOL.md`, and
  `.codex/SUBAGENT_EXECUTION_RULES.md`.

2026-05-16 CEST
Task:
- Refresh all agent settings after operator asked to improve every agent rather
  than preserve old `CLAUDE.md` chapter compatibility.

Chain:
- PM local docs/settings update; no sub-agent dispatch because the task was a
  tightly scoped operating-rule edit and the user asked to inspect then update.

Ownership:
- PM: Claude role files, Codex role files, agent-facing skill settings, role
  profiles, and verification.

Result:
- `.claude/agents/*.md` and `.codex/agents/*.md` now use the same preload
  route: operating memory, `README.md`, `docs/agents/context-loading.md`, and
  conditional `TODO.md`.
- `.codex/agents/INDEX.md` now documents universal Codex preload.
- Agent-facing skills/profiles no longer route active state through stale
  numbered-memory sections, enforce old bilingual comments, depend on 11-tab wording, or
  use the obsolete 1200-line hard cap.
