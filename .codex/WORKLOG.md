# Codex Worklog

Use this file for short rolling notes that are useful across sessions but do not belong in `TODO.md`.

Suggested entry format:

```text
YYYY-MM-DD HH:MM TZ
- what changed
- what remains
- where to look next
```

2026-05-06 00:10 CEST
- synced active docs before AgentTodo M0: TODO.md v10, CLAUDE.md REF-20 all-closed status, AgentTodo MAG-000 marked DONE
- verified Mac/Linux/origin source HEAD `67b95808`; Linux watchdog demo/live fresh, paper inactive by design; no rebuild/restart/deploy
- operator confirmed target architecture: scanner advisory/evidence, Strategist decision ownership, Guardian non-bypassable veto/modify, Rust execution engine without hidden decision authority
- next chain: MAG-001 CC, MAG-002 FA, MAG-003 PA contract freeze

2026-05-06 00:35 CEST
- completed AgentTodo M0 contract-freeze dispatch: MAG-001 CC APPROVED, MAG-002 FA CONDITIONAL, MAG-003 PA CONDITIONAL
- PM reconciled: M0 direction accepted, but E1 cannot start broadly; first implementation wave is limited to M1 durable agent event store
- E1-blocking conditions recorded in AgentTodo: state transitions, store ownership, durable idempotency, persistence-before-side-effect, scanner decay lifecycle, protective close split, fail-closed healthchecks, feature-flag/fallback semantics
- unrelated untracked `CONTEXT.md` and `docs/adr/` left untouched

2026-05-06 CEST
- operator clarified that external OpenClaw GUI has not been substantively used; canonical operator GUI is `trade-core:8000/console`
- accepted new architecture: local 5-Agent runtime remains inside TradeBot; external OpenClaw Gateway becomes communication/mobile/supervisor/cloud-escalation/proposal relay only
- created authoritative overlay and plans: `docs/architecture/2026-05-06--openclaw_control_plane_repositioning.md`, `docs/execution_plan/2026-05-06--openclaw_gateway_development_plan.md`, `docs/execution_plan/2026-05-06--gui_openclaw_control_console_plan.md`
- updated AgentTodo/TODO/CLAUDE/README/CONTEXT/Codex memory so future work does not treat OpenClaw Gateway or MessageBus as the trading conductor

2026-05-06 CEST
- reviewed AgentTodo against the accepted OpenClaw Gateway / Control Console architecture and found the boundary correct but the handoff order too flat
- updated AgentTodo with a dispatch-ready Sprint A order: MAG-015 contract addendum -> MAG-010..014 durable event store -> MAG-016..019 read-only OpenClaw status/self-state and Agent Control foundation
- updated TODO P1-OPENCLAW, CLAUDE, Codex memory, and PM memory so the next session starts with durable agent tables and read-only gateway/GUI, not Telegram/WebChat or proposal approval

2026-04-28 13:00 CEST
- created repo-synced Codex workspace under `.codex/`
- recorded Codex role, startup docs, inventory usage policy, and Mac -> git -> ssh Linux deploy flow
- established rule that Codex durable memory lives in repo files, not hidden session state
- next sync step should keep `.codex` isolated from unrelated working tree changes

2026-04-28 13:20 CEST
- inventoried Claude Code setup: 18 agents and 24 skills
- deployed Codex-side role mirror in `.codex/agents/`
- kept Claude skill corpus as shared SSOT and indexed it in `.codex/skills/INDEX.md`
- wrote comparison and deployment notes in `.codex/DEPLOYMENT.md` and `.codex/reports/`

2026-04-28 13:35 CEST
- added `.codex/AGENT_DISPATCH_PROTOCOL.md`
- set repository default Codex entry role to `PM`
- documented PM-first boot and dispatch chains for implementation, audit, quant, and deploy work

2026-04-28 16:10 CEST
- added git-root `AGENTS.md` so new Codex sessions can auto-load repository-specific PM-first rules
- added `.codex/SUBAGENT_EXECUTION_RULES.md` to require repo-role binding for every delegated task
- hardened reporting rule: temporary runtime nicknames are not authoritative; summaries must use `ROLE(codex_type)`

2026-04-28 22:20 CEST
- added `.codex/DISPATCH_LEDGER.md` for durable PM-first chain records
- promoted `.codex/agents/PM.md` into the mandatory boot order in `AGENTS.md`
- tightened the startup chain so PM role definition is loaded before delegation decisions

2026-04-29 01:20 CEST
- completed 62-finding remediation Batch B locally: `DAPI-001..006`, `RC-003`, `SC-001..007`
- used PM -> E3/PA -> E1/E1a -> E2 -> E4 -> PM flow; E2 blockers were fixed before final verification
- verification: targeted pytest 47 passed, py_compile OK, bash/plist/compose/static checks OK, `cargo check -p openclaw_engine` OK with existing warnings
- no deploy/restart; next remediation batch is Batch C trading record durability

2026-04-29 02:12 CEST
- completed 62-finding remediation Batch C locally: `OE-001..005`, `OE-008`, `OE-009`, `DBW-001..005`
- used PM -> PA/FA -> E1/E1a -> E2 -> E4 -> PM flow; E4 found Python direct-handler auth fixture drift after Batch B, PM fixed and reran green
- verification: Rust targeted tests 77 passed total, `cargo check -p openclaw_engine` OK with existing warnings, Python py_compile OK, targeted pytest 14 passed
- no deploy/restart; next remediation batch is Batch D risk/config fail-closed

2026-04-29 03:05 CEST
- completed 62-finding remediation Batch E locally: `SW-001`, `SW-003`, `SW-004`, `SW-005`, `SW-006`, `SW-007`, `OS-002`, `OS-003`, `OS-004`, `OS-005`, `OS-006`, `OS-007`, `DAPI-007`
- finalized operator/runtime ownership hardening: scheduled restart disabled, maintenance-flag trap lifecycle, cron overlap locks, safe process targeting, launchd preflight, DB reset fingerprint confirmation, least-privilege DB bootstrap, multi-worker leader-election guards
- verification: shell `bash -n` passed for touched scripts, Python `py_compile` passed, new `test_batch_e_runtime_ownership.py` 10 passed, Batch B+E static suite 20 passed
- no deploy/restart; remaining open remediation batches are D and F

2026-04-29 03:30 CEST
- completed 62-finding remediation Batch D locally: `RC-002`, `RC-004`, `RC-005`, `RC-006`, `SADF-002`, `SADF-003`, `LP-002`, `OE-006`
- closed fail-closed gaps in H0 status refresh preservation, startup risk config loading, risk-governor admission, legacy risk IPC semantics, strategy param atomicity, and close retry timeout budget
- verification: new Batch D static pytest 8 passed; Rust targeted tests 9 passed; `cargo check -p openclaw_engine` passed with existing warnings
- no deploy/restart; open remediation queue now Batch F only

2026-04-29 03:45 CEST
- completed Batch F F0 prework only: scope matrix, dirty-file collision map, workstream split, acceptance gates, and verification plan
- report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-29--batch_f_ml_agent_autonomy_prework.md`
- no sub-agents dispatched and no F implementation code changed
- Batch F implementation later completed locally with explicit scope ownership and preservation of existing B/C/D/E dirty changes

2026-04-29 CEST
- completed Batch A-E gap reassessment from operator-supplied review
- stale finding: D/E tracking/sign-off are now present; true gaps fixed: Batch A auth fixture drift, `RC-005`, `RC-006`, `OS-003`, `OS-006`
- verification: A-E Python targeted 128 passed, Rust full lib 2355 passed, `cargo check -p openclaw_engine` passed, `cargo build --release -p openclaw_engine` passed, Batch D+E static 18 passed, `bash -n`/static scan/`git diff --check` passed
- report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-29--batch_a_e_gap_reassessment.md`; no deploy/restart/commit/push

2026-04-29 CEST
- completed 62-finding remediation Batch F locally: `MLM-001..005`, `SADF-001`, `SADF-004`, `SADF-005`, `SADF-006`, `LP-003`
- closed ML/autonomy readiness gaps: feature-definition hash enforcement, model trio serving unit, ETL schema/hash filters, full-close label finality, LinUCB arm/state loop, Teacher Demo routing, observation-only metadata, `boost_arm` unsupported, Strategist Live fail-fast, Paper opt-in script
- verification: Python py_compile OK, `bash -n start_paper_trading.sh` OK, `cargo check -p openclaw_engine` OK with existing warnings, ML targeted pytest 78 passed/7 skipped, Rust targeted tests 47 passed
- no deploy/restart/commit/push; remaining production gaps are live PG integration, real ONNX artifact e2e, LinUCB live boot smoke, and full A-F deployment smoke

2026-04-29 CEST
- added a hard Codex rule that commit operations must use subject + body description, and push operations must be reported with branch, SHA, and description
- recorded the rule in `AGENTS.md`, `.codex/MEMORY.md`, and `.codex/DEPLOYMENT.md`
- future sync reports should no longer omit commit/push description context

2026-04-29 CEST
- added a hard Codex commit cadence rule: do not keep multiple independent green batches in one large dirty worktree by default
- repository rule now prefers one coherent commit per validated checkpoint, with delayed commit allowed only when scopes are still tightly coupled
- future commentary must explain any intentional delay in commit timing

2026-04-29 CEST
- compared Claude memory sources (`memory/MEMORY.md`, `memory/README.md`, `docs/CCAgentWorkSpace/PM/memory.md`, `.claude/agents/PM.md`) against Codex memory
- rewrote `.codex/MEMORY.md` into a compact index-style operating memory aligned to the Claude workflow rather than copying Claude content verbatim
- preserved compacted 2026-04-29 detailed batch/redeploy notes in `.codex/archive/2026-04-29--pre-compaction-memory-snapshot.md`

2026-04-29 17:36 CEST
- implemented `STRATEGY-EDGE-REPAIR-2026-04-29` locally: demo/live_demo/live strategy intents now carry a real `signal_id`/`context_id` attribution chain via a persisted strategy signal
- fixed fee-rate stale root long-term by spawning fee refresh/re-seed tasks per exchange binding AccountManager instead of only the highest-priority shared binding
- added scanner scan snapshots, configurable scanner `edge_routing`, robust-negative exploration-only routing, grid `blocked_symbols`, and strict maker entry skip on unsafe BBO/tick_size
- added passive healthcheck `[34] intent_signal_attribution` and tests; verification: Rust lib 2361/0, scanner 61/0, DB writer 3/0, fast_track_reduce 16/0, maker_price 10/0, `cargo check --bins`, `cargo check openclaw_core`, Python maker/attribution pytest 9/0, and `git diff --check`

2026-04-29 17:51 CEST
- accepted operator decision: demo can use ML/LinUCB/DreamEngine/OpportunityTracker to repair edge before positive edge, while live autonomous execution must pass GovernanceHub + Decision Lease + existing live gates
- wrote PM plan `docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-29--ml_dream_edge_unblock_plan.md`
- reordered TODO around MLDE-0..6: live-autonomy boundary, learning data contract, LinUCB intent-arm/reward loop, ML shadow scorer, Dream/Opportunity read-only producers, demo A/B advisory path, live promotion contract
- no code changes in this docs checkpoint; existing Rust WIP files in the working tree were intentionally left unstaged

2026-04-30 19:12 CEST
- completed dust residual prevention locally after Demo APEUSDT RCA: true residue was below Bybit minNotional and could become REST-only after local dust eviction
- implemented primary exchange full-close `qty=0 + reduceOnly + closeOnTrigger`, partial-reduce dust-residual skip, DUST_FROZEN preservation, REST-only dust GUI/API labeling, and sub-cent Demo PnL display
- verification: Python owner enrichment 34 passed; Rust full lib 2381/0; `cargo check --workspace` passed; `git diff --check` passed
- Linux instruction for this checkpoint: git fast-forward sync only; no rebuild/restart

2026-04-30 21:25 CEST
- completed PM-led active-doc cleanup and progress recalibration using `CC(default)`, `FA(default)`, `E5(explorer)`, `PA(default)`, and `MIT(default)`
- archived full pre-cleanup snapshots for `CLAUDE.md`, `TODO.md`, and `README.md`; README/CLAUDE were trimmed to current state, and TODO was later restored to its v3 record-preserving shape
- verified source/runtime framing at `5ba9b1c`: current active risk is post-deploy edge observation (`[33]`, `[38]`, `[40]`) plus dust close-path proof, not old `[16]` blocker framing
- updated Linear project `OpenClaw 62-Finding Remediation`: Batch A-F issues Done; stale deploy/RCA issues closed; active follow-up issues added for edge observation, dust proof, and Scout heartbeat wiring
- report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-30--active_docs_cleanup_and_progress_recalibration.md`

2026-04-30 21:40 CEST
- corrected the TODO cleanup after operator feedback: restored `TODO.md` to the v3 single-timeline record shape instead of the over-compressed 100-line active queue
- moved only the confirmed stale active-mainline block (`62-finding` as current mainline + Post-Wave-H hotfixes) to `docs/archive/2026-04-30--TODO-stale-active-mainline.md`
- kept GUI static dirty files untouched

2026-05-06 CEST
- started AgentTodo Sprint A from MAG-015 as requested
- completed docs-only MAG-015 contract addendum at `docs/architecture/multi_agent_rework_2026-05-05/2026-05-06--mag015_sprint_a_contract_addendum.md`
- froze local observation, OpenClaw view-model, supervisor escalation, proposal/approval/channel, endpoint allowlist, cloud budget, store ownership, state-transition, and MAG-010..019 implementation-packet contracts
- next order: MAG-010/011/012 durable event store, then MAG-013/014 Linux row proof, then MAG-016/017 read-only OpenClaw status/self-state
- no runtime, DB write/schema, strategy/risk config, live authorization, rebuild, restart, or deploy action
- continued AgentTodo Sprint A MAG-010..014 source wave: added default-off `AgentEventStore`, MessageBus sink, BaseAgent/Conductor state hooks, Strategist/Guardian/Analyst AI invocation hooks, and `[52] agent_event_store_rows`
- verification on Mac: new + affected targeted pytest 215 PASS, `py_compile` PASS, `git diff --check` PASS
- Linux `trade-core` fast-forwarded to `91379cd2`; targeted pytest 215 PASS and py_compile PASS
- status after source wave: MAG-010/011/012 source done but final DONE blocked on Linux runtime fresh rows; next gate is `[52]` row proof
- continued MAG-013/014 row proof: strict `[52]` failed before smoke with `messages=0 state_changes=0 ai_invocations=0`; controlled Linux smoke wrote `messages=2 state_changes=11 ai_invocations=2` through real event-store hooks; strict `[52]` then PASS
- no service restart, production continuous flag, live auth, strategy/risk config, or trading authority change
- continued AgentTodo Sprint A MAG-016/017 read-only OpenClaw foundation: added `openclaw_models.py`, `openclaw_routes.py`, and main router registration for exactly `GET /api/v1/openclaw/status` + `GET /api/v1/openclaw/self-state`
- route envelopes now surface authority posture, gateway/channel posture, runtime summary, event-store recent row proof, governance posture, model-budget posture, open blockers, and self-state sections; PG outage and missing OpenClaw request context return 200 degraded, and required zero rows are fail-visible
- verification: Mac targeted pytest `test_openclaw_routes.py` + `test_agents_routes.py` 33/0, py_compile PASS, `git diff --check` PASS; Linux `trade-core` fast-forward to `cbb225b7`, same targeted pytest 33/0 and py_compile PASS
- boundary: no write/proposal endpoint, no service restart, no deploy/rebuild, no live auth, no strategy/risk config mutation, and no trading authority change
- continued AgentTodo Sprint A MAG-018 Agent Control GUI foundation: `tab-agents.html` now mounts `openclaw-agent-control.js` and renders authority lockdown, gateway/channel posture, topology, and degraded/error panels from `/api/v1/openclaw/status` + `/api/v1/openclaw/self-state`
- verification: Mac targeted pytest `test_openclaw_agent_control_static.py` + `test_openclaw_routes.py` + `test_agents_routes.py` 38/0, `node --check` PASS, py_compile PASS, `git diff --check` PASS; Linux `trade-core` fast-forward to `12d3f3ff`, same pytest 38/0 plus node check and py_compile PASS
- boundary: no browser/server restart, no write/proposal endpoint, no manual order controls, no raw `agent.*` table joins in frontend, no deploy/rebuild, no live auth, and no strategy/risk config mutation
- completed AgentTodo Sprint A MAG-019 supervisor cloud ledger policy: added `openclaw_supervisor_policy.py`, wired OpenClaw `model_budget` to the policy snapshot, and added tests for default-disabled cloud, explicit budget/model requirements, bounded/hashing supervisor packets, budget-denied diagnosis payloads, pre-cloud-call `AgentEventStore.record_ai_invocation` reservation, event-store write failure visibility, and no network call markers
- verification: Mac targeted pytest `test_openclaw_supervisor_policy.py` + OpenClaw frontend/routes + agents routes 45/0, py_compile PASS, `node --check` PASS, `git diff --check` PASS; Linux `trade-core` fast-forward to `65a4279f`, same pytest 45/0 plus py_compile and node check PASS
- boundary: no cloud provider call, no write/proposal endpoint, no service restart, no deploy/rebuild, no live auth, no production continuous event-store flag, and no trading authority change; AgentTodo Sprint A is closed and next AgentTodo gate is M2 MAG-020..026

2026-05-07 CEST
- continued REF-21 P0-REF21-6b with parallel investigation across DB/backfill, scanner data realism, and E2E deploy readiness
- added `helper_scripts/db/ref21_backfill_v058_v059.py` dry-run/apply helper for V058 symbol universe/freeze log and V059 edge snapshots; helper supports `--asof` / `--freeze-asof` split and fetches Trading/PreLaunch/Delivering/Closed statuses
- preserved Bybit public kline `turnover` through Python fixture rows, Rust `MarketEvent`, and scanner timeline ticker reconstruction; legacy fixtures still fall back to `close * volume`
- fixed `/full-chain/run` register to use `embargo_days=14` with `half_life_days=7`, matching V041 `chk_embargo_days` on the real PG path
- verification: Python targeted pytest 10/0, project-venv Bybit instruments dry-run 905 V058-compatible rows after dated-futures symbol filtering, py_compile PASS, Rust scanner timeline 4/0, fixture turnover 1/0, `cargo check -p openclaw_engine --bin replay_runner --features replay_isolated` PASS with pre-existing warnings
- remaining before runtime sign-off: Linux migration apply/backfill, release `replay_runner` rebuild, API reload, and Linux one-click full-chain replay smoke
