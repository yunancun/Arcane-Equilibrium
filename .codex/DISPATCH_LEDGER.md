# Codex Dispatch Ledger

Last updated: 2026-04-29

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
