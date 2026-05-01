# Codex Memory

Last compacted: 2026-04-29

## Purpose

This is Codex's repo-synced operating memory for this project.

Claude memory comparison outcome:
- keep this file index-like and durable
- keep reusable rules here
- move long batch logs and one-off session detail to `WORKLOG.md`, `DISPATCH_LEDGER.md`, reports, or archive snapshots

Do not rely on hidden chat memory as the source of truth.

## Role and startup

Codex is used here as:
- secondary engineer
- external reviewer / supervisor
- deploy operator when requested

Default repository entry role:
- `PM`

Default startup read order:
- `AGENTS.md`
- `CLAUDE.md`
- `TODO.md`
- `.codex/MEMORY.md`
- `.codex/agents/PM.md`

For ongoing batch work, sign-off, or unclear continuity, also read:
- `docs/CCAgentWorkSpace/PM/profile.md`
- `docs/CCAgentWorkSpace/PM/memory.md`
- the latest PM report under `docs/CCAgentWorkSpace/PM/workspace/reports/`

Read on demand only:
- `OPENCLAW_INVENTORY_CONSOLIDATED.md`

## Project topology

- Mac is the development machine
- Linux `trade-core` is the active runtime machine
- future target is Apple Silicon Mac deployment, but current production-like runtime remains Linux
- real engine / DB / watchdog / rebuild checks must be run on Linux, usually through `ssh trade-core`

Current known paths and remote:
- Mac repo: `/Users/ncyu/Projects/TradeBot/srv`
- Linux repo: `/home/ncyu/BybitOpenClaw/srv`
- git remote: `git@github.com:yunancun/BybitOpenClaw.git`
- ssh alias: `trade-core`

## Claude-aligned workflow rules

- main session role is `PM + Conductor`; sub-agents handle implementation, review, or research
- use sub-agent-first thinking for non-trivial work; decide early whether the task should be decomposed
- forced work chains remain mandatory:
  - feature / bug: `PM -> PA -> E1/E1a -> E2 -> E4 -> QA -> PM`
  - compliance / architecture: `PM -> CC -> FA -> PA -> PM`
  - quant / ML / data: `PM -> QC -> MIT -> AI-E -> PM`
  - security / deploy / runtime: `PM -> E3 -> BB if exchange-facing -> PM`
- every delegated task must be bound to a repo role such as `PA(default)` or `E1(worker)`; do not treat runtime nicknames as authoritative
- significant dispatches belong in `.codex/DISPATCH_LEDGER.md`
- before dispatch in shared or parallel work, `git fetch` and check whether the topic already exists remotely
- for meta-doc updates in a dirty or multi-session tree, prefer `git commit --only <files>` to avoid index-race collateral staging
- do not keep multiple independent green batches in one large dirty worktree by default
- commit each coherent validated checkpoint once its targeted verification is green, unless scopes are still tightly coupled
- if commit timing is intentionally delayed, state the reason explicitly to the operator
- every commit must use a subject plus a body description
- every push report must include branch, SHA, and a short description
- if root principles, hard boundaries, risky deploys, contradictory evidence, or runtime/docs drift are detected, stop and report first
- always separate fact, inference, and assumption

## Operator preferences

- operator-facing responses should be Chinese-first
- minimize confirmation loops; act unless the risk is truly high
- operator needs pushback and judgment, not blind obedience
- agent autonomy within boundaries is preferred over over-constraining decision logic
- edge analysis should rely on demo data, not paper
- `live_demo` is still live-grade control flow; demo endpoint does not relax auth, TTL, or risk rigor
- risk parameter edits must stay scoped to the requested parameters
- operator-paste shell commands should be robust one-liners rather than heredoc-heavy multi-line snippets

## Architecture and deployment invariants

- Bybit is the only exchange target
- Rust `openclaw_engine` is the canonical trading / risk / config authority
- Python is the control plane, GUI, bridge, and auxiliary surface, not the trading truth layer
- new standalone logic should be Rust-first to avoid adding Python migration debt
- changes must stay cross-platform and Mac-deployable; avoid hard-coded machine paths
- tunable parameters must be real, discoverable, and persistent; no fake knobs
- `bash helper_scripts/restart_all.sh --rebuild` is the default rebuild path for Rust + PyO3 deployments
- operational trading understanding is `demo + live_demo`; paper is not an active trading lane for edge conclusions

## Current context pointers

Primary active-state sources:
- `CLAUDE.md`
- `TODO.md`

Current strategy-edge packet:
- `STRATEGY-EDGE-REPAIR-2026-04-29` is the active trading-strategy follow-up after commits `bd9ae2a` and `f0d21b9`
- primary metric for strategy improvement is post-fee `net_bps_after_fee`; PNL and winrate remain secondary references only
- post-fix sample window starts at `2026-04-29 12:27:53 CEST`, when live strategy params were reloaded with maker-entry enabled
- do not respond to the current losses by adding more risk layers by default; focus on execution fee reduction, maker fill quality, grid regime/spacing repairs, robust negative symbol disable decisions, and MA whipsaw/R:R improvements
- implementation checkpoint `2026-04-29 17:36 CEST`: demo/live_demo strategy-open intents now get a strategy-signal attribution anchor (`signal_id` + `context_id`), scanner scan snapshots are persisted, intent details carry scanner/edge route metadata, fee refresh is per exchange binding instead of single shared priority, maker fallback skips when BBO/tick_size is unsafe, and scanner `edge_routing` / grid `blocked_symbols` are real configurable knobs
- implementation checkpoint `2026-04-30 15:25 CEST`: strategy edge model batch adds execution-aware and regime-aware gates, not a new naked alpha strategy. Key durable facts: TOML-to-runtime wiring for MA/BB/grid maker buffer and grid `blocked_symbols` is fixed; grid OU spacing has `min_grid_step_bps` and `cost_floor_multiplier`; scanner `edge_routing` has posterior LCB gating; MA entry has ATR-normalized `min_trend_snr`; demo/live/paper strategy params share the new edge-protection baseline. Observe `[33]`, `[38]`, and `[40]` for 24h after Linux deploy. Report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-30--strategy_edge_models_engineering_log.md`
- implementation checkpoint `2026-04-30 19:12 CEST`: dust residual prevention adds primary exchange full-close dispatch via Bybit `qty=0 + reduceOnly + closeOnTrigger`, keeps normal zero-qty orders invalid, skips fast-track partial reductions that would leave below-minNotional residuals, preserves `DUST_FROZEN` in paper_state, and labels REST-only below-minNotional GUI/API rows as `orphan_frozen`. Report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-30--dust_residual_prevention_engineering_log.md`
- runtime/documentation recalibration `2026-04-30 22:18 CEST`: Mac/Linux code-bearing runtime checkpoint is `a9fce24`; Linux engine remains from the prior rebuild, and an API-only reload loaded the Scout heartbeat Python wiring. Latest healthcheck is `WARN` rather than FAIL: `[38] grid_trading_lifecycle_drift` and `[40] realized edge` remain real strategy/edge warnings, not pipeline-dead failures. Dust residual prevention is loaded and now has runtime proof: 8 Demo/LiveDemo `qty=0` close orders joined to nonzero fills after the 21:10 CEST rebuild, including Demo `APEUSDT` and LiveDemo `XAGUSDT` `orphan_frozen` residues. LiveDemo/live pipeline is authorized and running under live-grade gates, but true live autonomy remains gated by GovernanceHub, Decision Lease, and the 5 live gates.
- post-deploy edge cutoff `2026-04-30 21:10 CEST`: use cutoff analysis alongside rolling healthchecks. Current cutoff sample is still small: `[33]` entry fills n=15, maker_like 40.0%, fee_drop 39.0%; `[38]` lifecycle demo/live_demo n=1/1 insufficient with re-entry 0; `[40]` MLDE rows=0. Do not promote or reject the edge repair from rolling windows alone while they still mix pre-deploy samples.
- G1-04 as-of compute `2026-04-30 22:17 CEST`: full post-G7-09 window is 5.94d and still diluted by pre-reload samples (entry n=1933, maker_like 26.28%, fee_drop 21.30%). The more relevant post-2026-04-29 12:27 reload slice is n=665, maker_like 73.23%, avg_fee 3.424bps, fee_drop 59.32%; ma_crossover fee_drop 66.37%, grid 57.60%. R:R remains mixed: post-reload grid_close_short net positive with RR 1.454, but ma_reverse_cross remains net negative with RR 1.076 and win rate <40%. Treat this as G1-04 operator-requested as-of compute; G2-01 settlement still happens around 2026-05-07/08.
- source checkpoint `2026-05-01 22:51 CEST`: `be8fe37` exposes Rust scanner context to Python `/scanner/opportunities`, ScoutWorker intel, MLDE shadow advisor, and DreamEngine; V034 migration file is present but runtime DB apply was not performed. `569e06b` unifies Demo/Paper/Live GUI performance metrics through a backend-authored metric list and shared renderer. Linux source is synced to `569e06b`; no rebuild/restart/DB migration apply. Report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-01--todo_continue_scanner_context_gui_metrics.md`
- relevant runtime sentinels: `[32] maker_entry_intent_drift` for intent shape, `[33] maker_fill_rate` for fee-drop / maker-like settlement, and `[34] intent_signal_attribution` for demo/live_demo/live attribution-chain integrity

ML/Dream edge-unblock policy:
- as of `2026-04-29 17:51 CEST`, positive edge is a promotion gate, not a training gate
- demo may run ML / LinUCB / DreamEngine / OpportunityTracker in read-only, shadow, counterfactual, and bounded demo A/B modes to repair edge
- live autonomous trading or live parameter mutation from ML/Dream/agents must pass GovernanceHub approval, Decision Lease, and the existing live gates
- as of `2026-04-29 18:16 CEST`, local MLDE implementation is complete:
  - V031 adds `learning.mlde_edge_training_rows` and `learning.mlde_shadow_recommendations`
  - LinUCB trainer reads valid attribution + post-fee `net_bps_after_fee`; scheduler trains shared state once per cycle on default `demo_live_demo`
  - ML shadow advisor emits advisory `rank`/`veto`; DreamEngine and OpportunityTracker provide read-only inputs to CognitiveModulator
  - healthchecks `[35]` and `[36]` cover the learning data contract and advisory/live lease boundary
  - completion report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-29--ml_dream_edge_unblock_completion.md`
- as of `2026-04-29 18:45 CEST`, demo MLDE autonomy is implemented:
  - V032 adds `learning.mlde_param_applications` as the audit log for demo parameter applications and governed live candidates
  - `ml_training.mlde_demo_applier` consumes `learning.mlde_shadow_recommendations` and only auto-applies bounded changes to `engine_mode=demo`
  - strategy changes use Rust IPC `get_strategy_params` / `get_param_ranges` / `update_strategy_params`; risk and leverage changes use `get_risk_config` / `patch_risk_config(engine=demo, source=agent)`
  - all sample/confidence/delta/promotion thresholds are env-tunable defaults, not hard-coded live policy
  - live/live_demo rows are never auto-applied by this applier; strong demo evidence emits a `requires_governance=true` live `experiment_plan` candidate only
  - healthcheck `[37]` covers the demo applier audit table and the live Decision Lease boundary
  - report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-29--mlde_demo_autonomous_applier.md`
- Rust active LinUCB arm-space remains `v1_15`; richer `mlde_arm_id` exists for shadow/advisory analysis, and switching runtime active arm-space is a separate future migration

Claude memory sources used for alignment:
- `memory/MEMORY.md`
- `memory/README.md`
- `docs/CCAgentWorkSpace/PM/memory.md`
- `.claude/agents/PM.md`

Codex continuity sources:
- `.codex/WORKLOG.md`
- `.codex/DISPATCH_LEDGER.md`
- `.codex/reports/`

Detailed 2026-04-29 A-F remediation and redeploy context was compacted out of this file and preserved in:
- `.codex/archive/2026-04-29--pre-compaction-memory-snapshot.md`

## Maintenance rule

- keep this file concise, durable, and reusable across sessions
- move long batch logs to `WORKLOG.md`, reports, or archive snapshots
- update this file only for lasting workflow rules, topology, or project-state facts
