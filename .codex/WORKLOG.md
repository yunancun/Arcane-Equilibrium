# Codex Worklog

Use this file for short rolling notes that are useful across sessions but do not belong in `TODO.md`.

Suggested entry format:

```text
YYYY-MM-DD HH:MM TZ
- what changed
- what remains
- where to look next
```

2026-05-16 22:19 CEST
- completed role profile/memory hygiene across `docs/CCAgentWorkSpace/*`
- added `docs/agents/role-profile-memory-standard.md`, linked it from context loading/docs index, and made every role profile point at the shared contract
- added memory usage contracts to all role memories without deleting historical entries; active state remains `TODO.md`
- cleaned stale profile wording where old March 31 baselines could be misread as current truth

2026-05-15 22:13 CEST
- completed W-AUDIT-8b Funding Skew QC/MIT/BB review integration
- updated spec to v0.2 review/design: 30m primary horizon, branch-separated hypotheses, explicit K_total >= K_prior+4050, DSR>=0.95, PBO fail-closed, raw panel as-of joins, funding attribution excluded, and BB funding interval/source-mode fields
- trade-core panel freshness probe passed: funding=PASS(20929ms), oi=PASS(20969ms)
- next task is PA/E1 read-only Stage 0R query/report packet only; no strategy implementation, demo launch, runtime/config/risk/auth/DB mutation, or funding payment edge credit

2026-05-15 21:53 CEST
- closed `P1-A4C-RCA-1` after QC(default) + MIT(default) both rejected a new preregistered A4-C revive hypothesis
- kept A4-C diagnostic-only; did not open `P1-A4C-REV-1` or authorize a same-feature Stage 0R rerun
- W-AUDIT-8a C1 60s smoke passed as `SMOKE_PASS_NOT_C1_PROOF`; started 24h isolated `allLiquidation.BTCUSDT` proof on `trade-core`, PID `4100789`, log `/tmp/openclaw/audit/liquidation_topic_probe/nohup_20260515T195309Z.log`
- next alpha lane is W-AUDIT-8b Funding Skew QC/MIT/BB review + Stage 0R replay design while C1 runs
- no production WS topic revival, parser/writer restoration, DB write, rebuild/restart, auth renewal, paper/demo launch, risk/sizing/config mutation, or live action

2026-05-15 21:50 CEST
- updated TODO to v30 as a source-only three-side sync checkpoint
- removed active-doc stale sync wording (`TODO.md v28`, `81bc0862`) and aligned CLAUDE/active-plan/Codex memory/docs indexes
- pre-v30 Mac/origin/Linux source was clean/synced at `9a72d054`; runtime binary remains `7b33ab2e`
- no runtime rebuild/restart, DB write, auth change, paper enablement, demo canary, production WS topic revival, risk/sizing/config mutation, or live action

2026-05-15 CEST
- completed P0-MICRO-PROFIT alpha prework per operator request: C1 liquidation-topic proof packet, W-AUDIT-8b Funding Skew spec v0.1, and A4-C archive verdict
- added standalone `helper_scripts/bybit/liquidation_topic_probe.py`; it is isolated public WS only and cannot clear C1 without a 24h run
- updated TODO/CLAUDE/active-plan/docs indexes so A4-C is diagnostic-only and next alpha work is C1 proof + 8b QC/MIT/BB review/replay design
- no runtime rebuild/restart, DB write, auth change, production topic revival, paper enablement, demo canary, or risk/sizing change

2026-05-06 00:10 CEST
- synced active docs before AgentTodo M0: TODO.md v10, CLAUDE.md REF-20 all-closed status, AgentTodo MAG-000 marked DONE
- verified Mac/Linux/origin source HEAD `67b95808`; Linux watchdog demo/live fresh, paper inactive by design; no rebuild/restart/deploy
- operator confirmed target architecture: scanner advisory/evidence, Strategist decision ownership, Guardian non-bypassable veto/modify, Rust execution engine without hidden decision authority
- next chain: MAG-001 CC, MAG-002 FA, MAG-003 PA contract freeze

2026-05-15 CEST
- completed PM/PA/FA 5-day state audit sync: TODO.md v25, README/CLAUDE/.codex memory/active-plan/docs index aligned to current runtime facts
- classified `2026-05-15--stage0r_oi_confirmed_5m_preflight.md` as spec-only; no Stage 0R execution or canary eligibility
- archived stale TODO v24 rows for V079 pending, old engine 5/8 binary, ADR pending, PA spec pushback rows, old demo-state snapshots, and old `[55]`/`[67]` blockers; latest full passive healthcheck now fails `[27] intents_counter_freeze`
- direct trade-core checks before sync showed V079 applied through migration max=90 and `learning.strategy_trial_ledger` rows=16,212; Linux worktree dirty WIP remains a three-side sync blocker

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
- Linux runtime: pulled to `01b9cf59`, applied V060/V061, backfilled V058=905 / freeze=1 / V059=457, rebuilt release `replay_runner`, reloaded API, and completed a current-config full-chain smoke (`run_id=22558afa-3597-4571-b2c2-71b218201085`) with V058 universe + dedicated runner finalize
- remaining: recurring V058 recorder snapshots and historical order-book/ticker fidelity

2026-05-07 CEST
- inserted current Linux healthcheck FAILs into TODO as `P1-FAIL`: `[Xb]`, `[42]`/`[42b]`/`[42c]`, `[50]`, and `[51]` now preempt normal P1 Important work and keep MAG-083/MAG-084 blocked
- source-fixed `P1-FAKE-1`: ExecutorAgent now calls Rust IPC `submit_paper_order` with explicit `engine`, and ExecutorConfigCache's provider can read explicit demo/live/live_demo shadow config
- verification: Mac targeted Executor pytest 25 passed / 7 skipped, Linux targeted Executor pytest 30 passed / 2 skipped, py_compile passed on both sides
- no deploy/restart/live auth/strategy/risk config mutation; Linux pull/deploy verification remains pending

2026-05-07 CEST
- cleared the inserted P1 healthcheck FAIL queue to PASS/WARN: `[Xb]` no longer emitted, `[42]` cleared, `[42b/c]`, `[50]`, and `[51]` are WARN with explicit RCA
- source commits involved: `c8240b6a` LG5 candidate drain, `4654964d` settled attribution denominator, `898f4a90` replay superseded failures, `84f63706` scanner exploration separation, `4f437ea1` pipeline triangulation filled-context denominator
- verification: Mac/Linux targeted P1 healthcheck regression suite 96 passed; Linux passive healthcheck at 2026-05-07T17:51:38Z returned `SUMMARY: WARN`
- updated TODO P1 ordering: finish `P1-FAKE-1` runtime smoke if needed, then work WARN cluster `[14]/[37]/[40]/[45]` plus sample-maturity warnings, then resume P1-OPENCLAW-3 before P1-OPENCLAW-6/7
- boundary: API-only reloads loaded Python source; no engine rebuild, no live auth mutation, no Decision Lease flag flip, no strategy/risk config change

2026-05-09 CEST
- fixed passive healthcheck `[41]` scanner market evidence so legacy scanner would-block contradictions are WARN instead of FAIL; scanner is always-on evidence infrastructure, not a hard authority gate
- verification: Mac targeted scanner opportunity healthcheck pytest 12/0, py_compile PASS, `git diff --check` PASS; Linux fast-forwarded to `b91487f2`
- Linux passive healthcheck after sync returned `SUMMARY: WARN`; direct `[55]` Agent Decision Spine lineage proof PASS with `chains=101`, `chains_with_lease=76`, `chains_with_report=101`, `bad_report_quality=0`, readiness still `LINEAGE_READY_NOT_WINDOW_PASS`
- ran the 3C 7d audit script on Linux: overall WARN, `[40]` current edge delta `-1.12bps`, `[38]` grid lifecycle `-47.6%`, funding_arb hard stops PASS
- completed W-AUDIT-1 docs/governance sync across CLAUDE/TODO/MEMORY/register/glossary/README/script index, recorded W-C lease-router authorization, and added ADR-0015..0019 plus MIT/BB workspace READMEs
- boundary: docs/governance/source-only sync after `[41]`; no rebuild/restart, true-live API/auth, Executor authority, scanner authority, strategy/risk config mutation, or MAG-083/084 unlock

2026-05-09 CEST
- completed W-AUDIT-2 security IMPL source checkpoint: Phase4 weekly review approve/reject now require `learning:manage` operator scope and use server-authenticated actor id; Scout market-signal/event-alert require `learning:write`; Layer2 trigger requires `ai_budget:write`
- changed restart/fresh/clean deploy surfaces to default Trading API bind to `127.0.0.1` through `OPENCLAW_BIND_HOST`, and documented Tailscale Serve / reverse proxy / explicit Tailscale-IP binding instead of default `0.0.0.0`
- hardened `AIServiceListener` Unix socket startup with chmod `0600` after bind, failing closed if chmod fails
- wired Rust `spawn_lease_transition_pipeline` into boot and injected the shared sender into Paper/Demo/Live `GovernanceCore::set_lease_transition_tx`, unblocking W-AUDIT-3 F-15 lease flip→writer e2e work
- verification: Python py_compile PASS, Batch E static pytest 14/0, Phase4 route pytest 29/0, Scout route/audit pytest 46/0, Layer2 route class pytest 12/0, targeted Layer2 trigger test PASS, `cargo check -p openclaw_engine --bin openclaw-engine` PASS with pre-existing unused warnings, `cargo test -p openclaw_engine --lib database::lease_transition_writer -q` 6/0, `git diff --check` PASS
- residual: full `test_layer2.py` still has 5 pre-existing Layer2Engine failures from local Anthropic/local-LLM availability and an older `_model_upgrade_triage` signature expectation; the W-AUDIT-2 route-auth failure in that file is fixed by the route-class/targeted trigger pass above
- boundary: source/test/docs only; no rebuild, restart, runtime env flip, live auth mutation, scanner authority, Executor hard authority, strategy/risk config mutation, MAG-083/084 unlock, or true-live API action

2026-05-09 CEST
- continued W-AUDIT-3 source checkpoint: added F-17 lease-router dynamic status source/API/GUI wiring, F-15 lease flag flip writer/e2e regression coverage, and AMD-2026-05-09-01 draft SM-05 polling design for `ExecutorConfigCache`
- F-01 remains blocked by `P0-DECISION-AUDIT-2`; this checkpoint does not decide whether the 5-Agent Executor is temporary demo-promotion capable or permanently shadow-only
- verification: Python governance route pytest 113/0, Settings static pytest 48/0, Rust F-15 writer regression 1/0, risk runtime status regression 1/0, `cargo check -p openclaw_engine --bin openclaw-engine` PASS with pre-existing warnings, `git diff --check` PASS

2026-05-09 CEST
- started W-AUDIT-4 with source-only V076 Guard A retrofit for legacy V062/V063/V065 contracts
- added read-only `V076__guard_v062_v063_v065.sql` checks for scanner decay advisory table, market ticker funding_rate replay column, and OpenClaw proposal/approval/channel ledger safety constraints/indexes
- verification: V076 migration static pytest 5/0, py_compile PASS; no DB apply, rebuild, restart, live auth, scanner authority change, strategy/risk config mutation, or deploy action

2026-05-09 CEST
- continued W-AUDIT-4 F-29 source checkpoint: Linux read-only query confirmed `trading.fills.engine_mode='demo_archive_20260418'` has 6,616 rows from 2026-04-14 13:07:50.165+02 to 2026-04-18 20:13:54.328+02 and no current engine_mode CHECK
- added `V077__fills_engine_mode_archive_check.sql` to accept only paper/demo/live/live_demo plus bounded pre-2026-04-19 CEST archive rows, with NOT VALID + VALIDATE and no row rewrite
- verification: V077 migration static pytest 4/0, combined V076+V077 migration static pytest 9/0, py_compile PASS, `git diff --check` PASS; no DB apply, rebuild, restart, live auth, scanner authority change, strategy/risk config mutation, or deploy action

2026-05-09 CEST
- continued W-AUDIT-4 F-22 source checkpoint: Linux read-only schema audit showed the 9 planned retention targets are actually 5 hypertables, 2 plain tables, and 2 views
- added corrected `V075__w_audit4_retention_compression.sql`: Timescale retention/compression only for the 5 real hypertables; dry-run-default prune function for `learning.decision_features` and non-live `trading.decision_outcomes`; views are guarded as non-policy targets
- verification: V075 migration static pytest 5/0, combined V075+V076+V077 migration static pytest 14/0, py_compile PASS, `git diff --check` PASS; no DB apply, rebuild, restart, live auth, scanner authority change, strategy/risk config mutation, or deploy action

2026-05-09 CEST
- continued W-AUDIT-4 V073 source checkpoint: added read-only edge snapshot contract guard and executable cron wrapper for recurring V059 snapshot writes via the existing REF-21 helper with instruments/freeze-log disabled
- verification: V073 migration + cron static pytest 6/0, combined V073+V075+V076+V077 pytest 20/0, `bash -n` PASS, py_compile PASS, `git diff --check` PASS
- boundary: source/test only; cron was not installed or run, no DB apply, rebuild, restart, live auth, scanner authority change, strategy/risk config mutation, or deploy action

2026-05-09 CEST
- continued W-AUDIT-4 F-08 source checkpoint: added `ml_training_maintenance_cron.sh` plus a Python runner for the five audit-listed unscheduled ML paths (`linucb_trainer`, `mlde_shadow_advisor`, `mlde_demo_applier`, `scorer_trainer`, `quantile_trainer`)
- wrapper sources PG creds from `basic_system_services.env`, sets repo/program_code `PYTHONPATH`, uses an overlap lock, writes a status JSON, and keeps default training scope to demo while shadow advisory runs demo+live_demo
- verification: F-08 cron static pytest 4/0, `bash -n` PASS, py_compile PASS; source/test only, cron was not installed or run, no DB apply, rebuild, restart, live auth, scanner authority change, strategy/risk config mutation, or deploy action

2026-05-09 CEST
- continued W-AUDIT-4 V074 source checkpoint: added a live/live_demo `decision_outcomes` backfill helper, cron wrapper, and migration guard/index for the engine-mode pending scan
- helper mirrors the fixed Rust `outcome_backfiller` SQL contract (`1m/5m/1h/4h` kline timeframe literals, engine_mode propagated from snapshots, `ON CONFLICT DO UPDATE` repair path for stale/null outcome rows) and supports dry-run rollback
- verification: V074 migration + helper static pytest 7/0, `bash -n` PASS, py_compile PASS; source/test only, cron was not installed or run, no DB apply, rebuild, restart, live auth, scanner authority change, strategy/risk config mutation, or deploy action

2026-05-09 CEST
- continued W-AUDIT-4 V069 source checkpoint after code-reference audit: narrowed observability cleanup to `observability.scorer_predictions` only; retained `model_performance` because `canary_promoter.py` reads it, and retained `feature_baselines`/`drift_events` pending V072 drift contract resolution
- added rowcount/dependency guarded `V069__drop_dead_observability_scorer_predictions.sql` using `DROP TABLE ... RESTRICT`, plus fresh-start reset compatibility for missing dropped tables
- verification: V069 migration + fresh-start missing-table pytest 4/0, py_compile PASS; source/test only, no DB apply, rebuild, restart, live auth, scanner authority change, strategy/risk config mutation, or deploy action

2026-05-09 CEST
- continued W-AUDIT-4 V072 source checkpoint after Linux read-only contract proof: `features.online_latest` has 43 rows at 34 dims, active `observability.feature_baselines` rows are 0, and 7d `learning.decision_features` rows are 51,130 at 17 JSON keys
- added `V072__feature_baselines_contract_guard.sql` to lock active baselines to Rust drift_detector / feature_collector 34-dim names and prevent accidental 17-dim edge_predictor `decision_features` seeding
- remaining V072 work is a real 34-dim historical baseline writer design; this checkpoint intentionally does not seed/write baselines and does not apply DB

2026-05-09 CEST
- continued W-AUDIT-4 V068/V070/V071 source checkpoint: converted the original dead-schema cleanup plan into metadata-only reclassification guards after source audit found active route/cron/Rust writer/Agent Spine references across most targets
- V068 retains or marks review-only learning/agent targets; V070 retains replay handoff/advisory/KPI/incident/tier-approval contracts; V071 retains CostEdgeAdvisor, AI budget/usage, and Claude Teacher tables
- no destructive DB cleanup is included; no DB apply, rebuild, restart, live auth, scanner authority change, strategy/risk config mutation, or deploy action

2026-05-09 CEST
- started W-AUDIT-5a with F-21 source checkpoint: added `rust/Cargo.toml [profile.release] strip = "symbols"` plus a static TOML regression test
- verification: release profile strip pytest 1/0, `cargo metadata --manifest-path rust/Cargo.toml --no-deps`, `cargo check --manifest-path rust/Cargo.toml -p openclaw_engine --bin openclaw-engine` PASS with pre-existing unused/dead_code warnings, `git diff --check` PASS
- no release build, rebuild, restart, deploy, DB apply, live auth, scanner authority change, or strategy/risk config mutation

2026-05-09 CEST
- continued W-AUDIT-5a F-26 source checkpoint: added `.github/workflows/ci.yml` with Rust release-check matrix for `x86_64-unknown-linux-gnu` on ubuntu and `aarch64-apple-darwin` on macOS
- verification: CI workflow + release profile pytest 4/0, Ruby YAML parse PASS, `cargo metadata --manifest-path rust/Cargo.toml --no-deps`, `cargo check --manifest-path rust/Cargo.toml -p openclaw_engine --bin openclaw-engine` PASS with pre-existing unused/dead_code warnings, `git diff --check` PASS
- no CI run, release build, rebuild, restart, deploy, DB apply, live auth, scanner authority change, or strategy/risk config mutation

2026-05-09 CEST
- continued W-AUDIT-5a F-27 source checkpoint: corrected Bybit API dictionary drift for `get_open_interest` Rust `interval` -> Bybit `intervalTime`, added `/v5/user/query-api` Python credential-validation documentation, and added G9-02 UnknownHandlerGuard documentation with the actual runtime env-gate `OPENCLAW_WS_FORCE_RECONNECT_ON_UNKNOWN_ENABLED`
- documented the official Bybit `account-ratio` daily-period contradiction (`1d` on endpoint/api-explorer pages vs `4d` on enum `dataRecordingPeriod`) as exchange-smoke-required before any daily runtime polling; current Rust poller remains `"1h"`
- verification: Bybit dictionary static pytest 4/0, py_compile PASS; source/docs/test only, no Bybit API call, rebuild, restart, deploy, DB apply, live auth, scanner authority change, or strategy/risk config mutation

2026-05-09 CEST
- continued W-AUDIT-5a F-test-h-state source checkpoint: split `test_h_state_query_handler.py` from 2641 LOC into a 9-line compatibility collector plus `tests/h_state_query/common.py`, `test_core.py`, `test_h_buckets.py`, and `test_agent_states.py`
- kept the historical pytest path working while adding `tests/structure/test_h_state_query_split_static.py` to pin the shim and split module LOC ceilings
- verification: split package pytest 90/0, historical shim pytest 90/0, same-session `test_api_contract.py + test_h_state_query_handler.py` pytest 108/0 with pre-existing Pydantic/FastAPI warnings, structure pytest 2/0, py_compile PASS, `git diff --check` PASS; source/test only, no rebuild, restart, deploy, DB apply, live auth, scanner authority change, or strategy/risk config mutation

2026-05-09 CEST
- continued W-AUDIT-5a F-12 source checkpoint: split `rust/openclaw_engine/src/bin/replay_runner.rs` from 1599 LOC into a 626 LOC orchestration entrypoint plus `src/bin/replay_runner/manifest.rs`, `manifest_tests.rs`, `config.rs`, and `calibration.rs`
- kept manifest schema/verification tests under the binary test build and added `tests/structure/test_replay_runner_split_static.py` to pin the entrypoint and sibling module LOC ceilings
- verification: `cargo check --manifest-path rust/openclaw_engine/Cargo.toml --bin replay_runner --features replay_isolated` PASS with pre-existing Rust warnings; `cargo test --manifest-path rust/openclaw_engine/Cargo.toml --bin replay_runner --features replay_isolated` 9/0; W-AUDIT-5a static pytest 12/0; `cargo fmt --check`, py_compile, and `git diff --check` PASS
- boundary: source/test only; no release build, rebuild, restart, deploy, DB apply, live auth, scanner authority change, Executor hard authority, strategy/risk config mutation, MAG-083/084 unlock, or true-live API action

2026-05-09 CEST
- continued W-AUDIT-5b event_consumer source checkpoint: split `dispatch.rs` tests into `dispatch_tests.rs` and moved `loop_handlers.rs` Arm C exchange-event handling into `loop_exchange.rs` while preserving `loop_handlers::handle_exchange_event` via re-export
- reduced `dispatch.rs` 1144→683 LOC and `loop_handlers.rs` 1195→717 LOC; added `tests/structure/test_event_consumer_split_static.py` to pin the split and compatibility exports
- verification: `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine event_consumer -q` PASS (155/0 plus one filtered target test); `cargo check --manifest-path rust/Cargo.toml -p openclaw_engine --bin openclaw-engine` PASS with pre-existing Rust warnings; structure pytest 6/0; `cargo fmt --check`, py_compile, and `git diff --check` PASS
- boundary: source/test only; no release build, rebuild, restart, deploy, DB apply, live auth, scanner authority change, Executor hard authority, strategy/risk config mutation, MAG-083/084 unlock, or true-live API action

2026-05-09 CEST
- continued W-AUDIT-5b state-machine snapshot source checkpoint: removed the 10 generic `copy.deepcopy` snapshot callsites from SM-01 authorization, SM-02 decision lease, SM-04 risk governor, shared `state_machine_base`, and `learning_tier_gate`
- added explicit `clone()` snapshot methods for `AuthorizationObject`, `DecisionLeaseObject`, `GovernorState`, and `TierState`, with `_clone_jsonish()` for mutable dict/list snapshot fields; `MultiObjectStoreMixin` now requires clone-backed snapshots instead of generic deepcopy fallback
- added regression coverage for nested snapshot isolation plus `tests/structure/test_state_machine_snapshot_clone_static.py`; source/test only, no rebuild, restart, deploy, DB apply, live auth, scanner authority change, Executor hard authority, strategy/risk config mutation, MAG-083/084 unlock, or true-live API action

2026-05-09 CEST
- continued W-AUDIT-5b orjson foundation source checkpoint: added `app/json_fast.py` with optional `orjson` fast path and stdlib fallback, added `orjson>=3.10.0` to control_api_v1 requirements, and migrated `ai_service_listener.py` plus `ipc_client_sync.py` newline-delimited JSON IPC hot paths
- kept byte-contract-sensitive signature/hash JSON callsites untouched pending explicit canonical-byte tests; added `test_json_fast.py` and `tests/structure/test_json_fast_hot_paths_static.py`
- verification: py_compile for `json_fast.py`, `ipc_client_sync.py`, and `ai_service_listener.py`; targeted pytest 21/0; `git diff --check` PASS; source/test only, no dependency install, rebuild, restart, deploy, DB apply, live auth, scanner authority change, Executor hard authority, strategy/risk config mutation, MAG-083/084 unlock, or true-live API action

2026-05-09 CEST
- continued W-AUDIT-5b ai_budget source checkpoint: replaced the read-heavy `BudgetTracker.config_cache` async `RwLock<BudgetConfig>` with `ArcSwap<BudgetConfig>` whole-snapshot swaps for refresh/status/remaining/degrade/cost-edge reads
- intentionally left `usage_cache` under async `RwLock<UsageCache>` because spend recording mutates cumulative per-scope counters; no per-strategy budget schema or authority model was introduced in this cache checkpoint
- verification: `cargo fmt --all --manifest-path rust/Cargo.toml --check`; `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine ai_budget -q` PASS (31/0 plus filtered targets); `cargo check --manifest-path rust/Cargo.toml -p openclaw_engine --bin openclaw-engine` PASS with pre-existing Rust warnings; `python3 -m pytest tests/structure/test_ai_budget_arc_swap_static.py -q` 1/0; `git diff --check` PASS; source/test only, no rebuild, restart, deploy, DB apply, live auth, scanner authority change, Executor hard authority, strategy/risk config mutation, MAG-083/084 unlock, or true-live API action

2026-05-09 CEST
- continued W-AUDIT-5b json_fast runtime-hot-path source checkpoint: migrated async `ipc_client.py` JSON-RPC framing and local LLM HTTP JSON paths (`ollama_client.py`, `local_llm_factory.py`) to `app/json_fast.py`
- kept signature/hash/replay-manifest/canonical JSON paths on stdlib JSON pending explicit byte-contract tests
- verification: py_compile for `ipc_client.py`, `ollama_client.py`, and `local_llm_factory.py`; json_fast + static pytest 5/0; governance lease + ipc update-risk pytest 50/0; Ollama + local LLM factory pytest 45/0 with one pre-existing coroutine warning; `git diff --check` PASS; source/test only, no dependency install, rebuild, restart, deploy, DB apply, live auth, scanner authority change, Executor hard authority, strategy/risk config mutation, MAG-083/084 unlock, or true-live API action

2026-05-09 CEST
- started W-AUDIT-7 F-30 source checkpoint: added shared `openPromptModal()` in `common.js` and replaced native `prompt()` in learning experiment completion plus governance audit/live-auth renewal/review flows
- tier/confidence inputs now use modal select pickers; required text inputs validate inside the modal instead of relying on native browser dialogs
- verification: `node --check` for `common.js`, `app-learning.js`, and `governance-tab.js`; `python3 -m pytest tests/structure/test_prompt_modal_static.py -q` 2/0; Edge headless smoke via temporary static server verified governance tier select modal and learning required textarea modal; `git diff --check` PASS; source/test/static-browser only, no backend start, rebuild, restart, deploy, DB apply, live auth mutation, scanner authority change, Executor hard authority, strategy/risk config mutation, MAG-083/084 unlock, or true-live API action

2026-05-09 CEST
- continued W-AUDIT-7 F-system-mode-confirm source checkpoint: `tab-system.html` `live_reserved` mode confirmation now shows a live-only guard, disables confirm for a 5s countdown, rejects single-click confirmation after the countdown, and submits only after a 1.2s hold-to-confirm
- added `tests/structure/test_system_mode_confirm_static.py` to pin the countdown constants, live-only scope, confirm click handler, pointer cancel paths, and keyboard hold/cancel support
- verification: system-mode + prompt modal static pytest 5/0, `git diff --check` PASS, Edge headless smoke via temporary static server verified initial disabled countdown, ready hold state, single-click rejection, and hold-to-confirm submission through stubbed `/api/v1/input/config-change`
- boundary: source/test/static-browser only; no backend start, rebuild, restart, deploy, DB apply, live auth mutation, scanner authority change, Executor hard authority, strategy/risk config mutation, MAG-083/084 unlock, or true-live API action

2026-05-09 CEST
- operator authorized three-side sync plus rebuild/restart after W-AUDIT-7 GUI checkpoint; Mac/origin/Linux synced at `95364596d56dcccca86f5d84e200676b6e6422ce`
- Linux `restart_all.sh --rebuild --keep-auth` rebuilt the release engine and restarted API, but engine startup aborted during auto-migrate V077 because Timescale columnstore-enabled `trading.fills` does not support the CHECK alteration
- verified `_sqlx_migrations` had applied V068-V076 and not V077, then hotfixed V077 to keep CHECK as the preferred path and install a same-predicate trigger fallback on `feature_not_supported`
- verification: V077 static pytest 5/0, `git diff --check` PASS, Linux PG `BEGIN ... ROLLBACK` dry-run of the patched V077 PASS with trigger fallback notice; no live auth mutation, scanner authority change, Executor hard authority, strategy/risk config mutation, MAG-083/084 unlock, or true-live API action
- deployed hotfix `49ceeb61` to Linux and restarted engine-only with `--keep-auth`; V077 is now recorded in `_sqlx_migrations`, `trg_fills_engine_mode_known_values` exists, engine PID `4080150` is alive, passive healthcheck returned `SUMMARY: WARN` with no hard FAIL, and `[55]` PASSed with `chains=121`, `chains_with_lease=96`, `bad_report_quality=0`
- runtime caveat: live authorization file is missing, so the engine refused to spawn LiveDemo/live at boot and is running demo-only; no manual auth renewal/restoration was performed

2026-05-09 CEST
- continued W-AUDIT-7 F-strategy-confirm source checkpoint: added shared `common.js` action risk-zone CSS, separated Strategy Pause/Stop/Delete, separated Paper run/pause/stop/dual-stop, and grouped Live Stop/Emergency Stop plus close-all/row-close destructive controls
- extended `openConfirmModal()` for per-call metadata/classes and replaced Paper dual-stop plus Live close-position native `confirm()` paths with custom modal confirms
- verification: strategy-action + prompt + system-mode static pytest 9/0, `node --check common.js`, `git diff --check`, and Edge headless routed smoke for Strategy/Paper/Live danger zones all PASS; source/test/static-browser only, no rebuild, restart, deploy, DB apply, live auth mutation, scanner authority change, Executor hard authority, strategy/risk config mutation, MAG-083/084 unlock, or true-live API action

2026-05-09 CEST
- continued P0-NEW-ISSUE-1 source checkpoint: added passive healthcheck `[56] live_pipeline_active` because `[Xb]` is already occupied by `pipeline_triangulation`
- `[56]` is read-only/filesystem-only and FAILs when the live slot is configured but signed `live/authorization.json` is missing or `pipeline_snapshot_live.json` is stale; it does not write/renew live auth
- updated CLAUDE §三/TODO/docs to record the current Linux fact: live slot key/secret/endpoint present, `authorization.json` missing, Rust refused LiveDemo at boot and runtime is demo-only
- verification: live pipeline healthcheck pytest 7/0, py_compile PASS, local unconfigured-slot import smoke PASS; no rebuild, restart, deploy, DB apply, live auth mutation, scanner authority change, Executor hard authority, strategy/risk config mutation, MAG-083/084 unlock, or true-live API action

2026-05-09 CEST
- closed P0-AUDIT-NEW-LG-X-05 source/doc checkpoint: SPECIFICATION_REGISTER LG-X table now aligns to historical LG-1..LG-5 and adds LG-X-05 constrained autonomous live
- moved Live Ops Foundation out of LG-X-04 into separate `OPS-X-01`, so LG-X-04 again means Supervised-Live Gate and does not hide the LG-5 RFC family
- updated CONTEXT/docs README/TODO/PM reports; source-doc only, no rebuild, restart, deploy, DB apply, live auth mutation, scanner authority change, Executor hard authority, strategy/risk config mutation, MAG-083/084 unlock, or true-live API action

2026-05-09 CEST
- closed P0-NEW-VULN-1 source/test checkpoint: Mac launchd Trading API plist now binds `127.0.0.1` instead of `0.0.0.0`
- added `launchd_preflight.sh` fail-closed guard against all-interface Trading API plist binds and extended Batch E runtime ownership regression to cover the plist/preflight
- verification: targeted Batch E pytest PASS, plist syntax lint PASS, static grep confirms no `0.0.0.0` in deploy plist/templates except historical reports/docs; no launchd load/unload, rebuild, restart, deploy, DB apply, live auth mutation, scanner authority change, Executor hard authority, strategy/risk config mutation, MAG-083/084 unlock, or true-live API action

2026-05-09 CEST
- closed the operator-requested three main blockers: P0-NEW-VULN-2 lease-bypass audit runtime emit, P0-DECISION-AUDIT-2/4/5 operator decision blockers, and P0-NEW-ISSUE-1 LiveDemo auth_missing restoration
- deployed Linux `trade-core` through `862e79b7` with authorized `restart_all.sh --rebuild --keep-auth`; V078 applied, `learning.lease_transitions` is nonzero with `BYPASS` rows (final spot-check rows=103), watchdog shows demo/live fresh while paper is explicitly disabled by `OPENCLAW_ENABLE_PAPER != 1`, and direct `[56] live_pipeline_active` PASSes
- LiveDemo auth was restored only through signed `/api/v1/live/auth/renew`; no manual auth-file write, true mainnet API enablement, strategy/risk config mutation, scanner authority change, Executor hard authority, MAG-083/084 unlock, or true-live action

2026-05-09 CEST
- closed P0-NEW-ISSUE-1 keep-auth RCA: archived engine log `engine-1778289328.log` shows the 2026-05-09T01:11:28Z boot consumed a `manual` restart sentinel and cleared `authorization.json`; later `--keep-auth` preserved the already-missing state
- added warning-only/read-only `restart_all.sh --keep-auth` preflight for configured live slots with missing signed authorization, plus static regression coverage
- verification: `bash -n helper_scripts/restart_all.sh`, keep-auth preflight static pytest 2/0, `git diff --check` PASS; no restart, auth write/delete, true mainnet enablement, strategy/risk config mutation, MAG-083/084 unlock, or true-live action

2026-05-09 CEST
- continued W-AUDIT-4 / P2-AUDIT-VERIFY-4 source checkpoint: corrected F-08 ML cron scope so `ml_training_maintenance` covers the original audit five (`thompson_sampling`, `optuna_optimizer`, `cpcv_validator`, `dl3_foundation`, `weekly_report_generator`) plus the operational MLDE jobs
- added real source paths from current runtime data into `bayesian_posteriors`, `ml_parameter_suggestions`, `cpcv_results`, `foundation_model_features`, and `weekly_review_log` where DB/dependencies/data exist; wrapper default job list now includes both sets
- updated TODO/MEMORY/PM report/Script Index to mark W-AUDIT-4 as partial and F-08 as source-scope corrected but runtime-cron pending
- verification: py_compile PASS, `tests/helper_scripts/test_ml_training_maintenance_cron_static.py` 4/0 PASS, forced audit-job dry-run PASS, and weekly_report/dl3/thompson targeted pytest 46/0 PASS; no crontab install, DB write, rebuild, restart, deploy, live auth mutation, scanner authority change, strategy/risk config mutation, MAG-083/084 unlock, or true-live action

2026-05-09 CEST
- continued W-AUDIT-3 F-01 source checkpoint: removed the hidden `lambda: True` fallback from `ExecutorAgent.__init__` and made missing `shadow_mode_provider` state explicit
- `_read_shadow_mode()` now handles provider-unavailable and provider-exception paths fail-closed before IPC submit authority; production wiring remains explicit via `ExecutorConfigCache.shadow_mode_provider()`
- updated SM-05/TODO/CLAUDE/register wording plus PM report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-09--w_audit_3_f01_provider_fail_closed.md`
- verification: py_compile PASS; ExecutorAgent unit pytest 30/0; executor config cache + decision parity pytest 17/0 with 7 skipped; agents routes executor/shadow pytest 7/0; source/test/docs only, no rebuild, restart, deploy, DB apply, live auth mutation, scanner authority change, strategy/risk config mutation, MAG-083/084 unlock, or true-live action

2026-05-09 CEST
- corrected P0-NEW-VULN-1 bind-host model after operator clarified Tailscale GUI access requirement: lifecycle scripts no longer need `0.0.0.0`
- added shared `helper_scripts/lib/api_bind_host.sh`: default `OPENCLAW_BIND_HOST=auto` resolves concrete Tailscale IPv4 when available and otherwise loopback; `OPENCLAW_BIND_HOST=tailscale` forces tailnet-only; `0.0.0.0` / `::` fail closed
- updated restart/clean/fresh scripts, deploy docs, Script Index, feedback memory, TODO, and Batch E runtime ownership regressions
- verification: bash -n PASS; Batch E pytest 15/0 on Mac and Linux; helper smoke resolves Tailscale IP and rejects all-interface bind; `git diff --check` PASS
- runtime: pushed `c187fd99`, stashed the prior Linux unsafe hot edit as `codex-preserve-unsafe-0.0.0.0-bind-hotedit`, fast-forwarded Linux, and ran API-only restart; Trading API now listens on `100.91.109.86:8000` instead of `0.0.0.0:8000`, with tailnet curl reaching the authenticated API

2026-05-15 CEST
- PM task: TODO.md cleanup/archive after v21 exceeded the 700-line hygiene cap (754 lines)
- dispatch chain: PM local synthesis + PA(default) read-only reconciliation + FA(default) priority audit + TW-style docs cleanup in main workspace
- result: `TODO.md` v22 reduced to 453 lines; completed sprint ledgers and DONE-row evidence archived to `docs/archive/2026-05-15--todo_v21_completion_cleanup_archive.md`; `docs/README.md` archive index refreshed
- priority verdict: no full W-AUDIT roadmap rewrite; A4-C Stage 1 demo/promotion path stays blocked pending future green Stage 0R plus `[55]` PASS/waiver, while `[55]`, P0-LG/OPS/EDGE, and alternate alpha work stay active
- verification: `git diff --check` PASS; `python3 -m pytest tests/structure/test_docs_readme_index_static.py -q` = 5 passed; docs-only, no `active-plan.md`, runtime code, live auth, rebuild, restart, or deploy

2026-05-15 CEST
- PM task: operator requested replay-first validation default and asked whether W-AUDIT-8a Phase C0 could be checked by replay
- dispatch chain: PM local triage; E2/E4 skipped because this was a narrow validation-policy + targeted unit-test packet
- result: `.codex/MEMORY.md` and PM memory now record replay-first validation as the default; Phase C0 report distinguishes replay-applicable fail-closed checks from BB-only real WS topic safety
- verification intent: added `replay_empty_surface_keeps_liquidation_cascade_fail_closed` to prove isolated replay still gives strategies `EMPTY_ALPHA_SURFACE`, so `LiquidationCascade` remains unavailable and actionless before C1

2026-05-16 CEST
- PM task: close `P1-WAVE-3-5-LINUX-MIGRATION-BACKLOG` on Linux `trade-core`.
- dispatch chain: PM local runtime/deploy execution; PA audit report was the input; E2/E4 equivalents were read-only schema/checksum verification and V092 idempotency rerun.
- result: V092 continuous aggregates applied online; V091/V092/V093 `_sqlx_migrations` rows inserted with source checksums; `_sqlx_migrations` now has `max_applied=93`, `rows=90`.
- verification: V092 second apply idempotency PASS, six cagg views + six refresh jobs exist, aggregate view read smoke returns rows, `repair_migration_checksum --verify` reports `drift_count=0`, engine PID `69581` remained alive.
- boundary: no restart, rebuild, auth write/renewal, strategy/risk config mutation, trading mode change, or order-authority change.

2026-05-16 CEST
- PM task: memory slimming and context-routing standardization for Claude/Codex operating files.
- result: added `docs/agents/context-loading.md` and `docs/agents/todo-maintenance.md`; moved active-state authority to `TODO.md`, stable project entry to `README.md`, and kept `CLAUDE.md` / `.codex/MEMORY.md` as operating memory.
- startup routing updated in `AGENTS.md`, `.claude/agents/PM.md`, `.codex/agents/PM.md`, `.codex/AGENT_DISPATCH_PROTOCOL.md`, and `.codex/SUBAGENT_EXECUTION_RULES.md`.
- boundary: docs-only; no runtime code, deploy, rebuild, restart, DB, auth, strategy/risk, or trading-mode changes.

2026-05-16 CEST
- PM task: refresh all Claude/Codex agent settings after operator rejected reliance on old `CLAUDE.md` section compatibility.
- result: all `.claude/agents/*.md` and `.codex/agents/*.md` now preload operating memory + `README.md` + `docs/agents/context-loading.md`, and route active state to `TODO.md`; Codex role index now records universal preload.
- aligned agent-facing skills and profiles away from stale numbered-memory sections, 11-tab, bilingual-comment, and 1200-line assumptions; current rules use TODO active state, README stable surfaces, Chinese-first comments, and 2000-line hard cap.
- boundary: docs/agent-settings only; no runtime code, deploy, rebuild, restart, DB, auth, strategy/risk, or trading-mode changes.

2026-05-17 CEST
- PM task: W-AUDIT-8c correction-scoped source/test packet after C1 technical PASS and MIT idempotency condition.
- dispatch chain: PM(default) -> E1(worker) -> E2(explorer) -> E4(worker) -> MIT(default) + BB(default) -> PM(default).
- result: V095 source migration preserves liquidation item identity with `(symbol, ts, side, qty, price)`; `allLiquidation` parser/writer fail closed; corrected Bybit side mapping (`Buy` long liquidation / `Sell` short liquidation) is tested; production subscription builders remain disabled for `allLiquidation*`.
- verification: migration pytest 6/0, Rust tests from `rust/` passed for `all_liquidation` 6/0, `liquidation` 14/0, `ws_client::tests` 29/0, forbidden-topic regression 1/0, rustfmt check PASS, scoped `git diff --check` PASS.
- boundary: source/test/docs only; no runtime deploy, Linux DB apply, rebuild, restart, auth mutation, paper/live/mainnet enablement, strategy/risk mutation, or production `allLiquidation*` subscription.
