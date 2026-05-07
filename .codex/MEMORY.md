# Codex Memory

Last compacted: 2026-04-29

## Purpose

This is Codex's repo-synced operating memory for this project.

Formal project name after the 2026-05-06 soft rename:
- Chinese: `玄衡`
- English: `Arcane Equilibrium`
- OpenClaw remains the control-plane / Gateway / Console / communication service family.
- Bybit remains the sole exchange adapter / connector label.

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

## 2026-05-02 Codex bootstrap alignment

Operator provided an OpenClaw initialization packet and asked Codex to treat it as durable session context. Keep these points active for future sessions:

- Canonical repo root is always `srv/`; the parent workspace is only an entry shim.
- Codex enters as `PM + Conductor`, not an anonymous implementer. PM may plan, dispatch, integrate, sign off, and review diffs, but business-code implementation should go through bound roles such as `E1(worker)`, then `E2(explorer)` and `E4(worker)`.
- Before dispatching real work, run `git fetch` when available and check for existing topic branches; if fetch hangs or fails, record that explicitly instead of assuming remote state.
- The forced chain remains binding: feature / bug work needs `PM -> PA -> E1/E1a -> E2 -> E4 -> QA -> PM` unless PM states a scoped reason to skip a non-hard role. `E2` and `E4` are never skipped.
- For strategy, math, ML, data, live-auth, risk, or deploy work, add the relevant gate roles: `QC`/`MIT` for quant and data, `E3`/`CC` for live or security boundaries, and `BB` for Bybit-facing exchange behavior.
- Mac is development only. Do not start or restart the engine locally on Mac; runtime truth is Linux `trade-core` via SSH. Mac may do `git fetch` and `git pull --ff-only`; do not merge, rebase, reset, force-push, or amend published commits.
- LiveDemo uses the live pipeline and demo endpoint, but remains live-grade for auth, TTL, fail-closed risk, and audit. Do not downgrade controls because the endpoint is demo.
- Rust `openclaw_engine` is the trading, risk, strategy-config, and execution authority. Python is a bridge/API/GUI/control plane and must not become the write authority for trading or risk parameters.
- GUI is Vanilla JS; do not introduce React/Vue/Angular. GUI write surfaces must write through Rust authority, not Python-only fake-success paths.
- Path handling must remain portable for a future Apple Silicon runtime. New code must not hard-code `/home/ncyu`, `/Users/ncyu`, or machine-specific TradeBot paths.
- Meta-doc commits in a dirty multi-session tree should use `git commit --only <file>` so unrelated WIP is not staged.
- Linear is the only active external workflow integration. Notion is frozen; Drive is passive; Coupler, MotherDuck, and Slack are declined unless the operator explicitly reopens them.
- Governance register path in this repo is `docs/governance_dev/SPECIFICATION_REGISTER.md`. The older shorthand `docs/SPECIFICATION_REGISTER.md` is not present.

## Architecture and deployment invariants

- Formal project/product name is `玄衡 · Arcane Equilibrium`; do not use `OpenClaw Bybit` as the total project name in new docs
- Bybit is the only exchange target
- Rust `openclaw_engine` is the canonical trading / risk / config authority
- Python is the control plane, GUI, bridge, and auxiliary surface, not the trading truth layer
- OpenClaw 2026-05-06 repositioning: external OpenClaw Gateway is only communication / mobile / supervisor / cloud-escalation / proposal relay; it is not the trading conductor, not the local 5-Agent runtime, and not a second GUI
- canonical GUI is the existing FastAPI console at `trade-core:8000/console`, now treated as the OpenClaw Control Console
- local 5-Agent runtime stays inside TradeBot; cloud L2 should be reached through a supervisor escalation packet, not by every runtime agent independently
- AgentTodo Sprint A is closed. MAG-015 contract addendum is complete at `docs/architecture/multi_agent_rework_2026-05-05/2026-05-06--mag015_sprint_a_contract_addendum.md`. MAG-010..014 durable event-store source + controlled Linux row proof is closed: strict `[52]` went from FAIL `0/0/0` to PASS `messages=2 state_changes=11 ai_invocations=2` after smoke rows through real `AgentEventStore`/`MessageBus`/`BaseAgent`/`Conductor`. MAG-016/017 read-only OpenClaw foundation is closed at `cbb225b7`: `/api/v1/openclaw/status` and `/api/v1/openclaw/self-state` return backend-authored envelopes; tests lock exactly two GET routes, degraded PG/request-context behavior, zero-row visibility, and no write/proposal route. MAG-018 Agent Control GUI foundation is closed at `12d3f3ff`: `tab-agents.html` mounts `openclaw-agent-control.js`, consumes only the two OpenClaw GET view models, renders authority/gateway/topology/degraded panels, sends required OpenClaw context headers, and static tests prove no manual controls/raw table join/write request. MAG-019 supervisor cloud ledger policy is closed at `65a4279f`: cloud default disabled, explicit budget/model required, bounded supervisor packets, budget-denied diagnosis payloads, and allowed cloud calls must reserve `AgentEventStore.record_ai_invocation` before provider IO; the policy module has no cloud/network call markers. Mac/Linux targeted tests 45/0, node check, and py_compile passed. M2 MAG-020..026 Scanner Advisory Conversion is closed: scanner authority modes, advisory contracts, decay emission, replay proof, churn fixture, shadow wiring, and no-auto-close regression all passed Mac/Linux targeted checks. M3 Agent Decision Spine Shadow MAG-030..035 is closed: Rust `agent_spine` design/adapter/contracts/store/writer surface, V064 durable spine tables, Python client, idempotency audit, and shadow regression all pass Mac/Linux targeted checks while preserving legacy Rust `TradingMsg::Signal` behavior and leaving runtime startup unwired/default-disabled. M4 Strategist V2 MAG-040..045 is closed: matching model, typed StrategistDecision builder, PositionReview builder, Guardian feedback stats, AnalystInsight/TruthRegistry learning weights, and replay-style not-scanner-sorting regression pass targeted checks. M5 MAG-050..054 Guardian V2 is closed: Guardian consumes dynamic correlation, strategy risk, Scout EventAlert, scanner risk evidence, and RISK_PATTERN evidence; soft evidence P2-tightens size/leverage/stop/cooldown while hard evidence pauses new opens without direct close/order authority; ExecutionPlan requires non-empty Guardian verdict lineage and Python/Rust spine regressions distinguish modified Guardian verdicts. M6 MAG-060..064 Executor Planner is closed: ExecutionPlan contracts/generation/lease binding are done; `executor_report_v2.py` and Python/Rust ExecutionReport contracts carry Analyst-consumable slippage, fee, fill latency, qty, price, liquidity role, and quality_metrics fields; AgentSpineClient writes those metrics into executed_by edge details; regression tests prove Executor plan generation and spine persistence cannot choose or alter symbol/direction outside the approved StrategistDecision. M7 MAG-070..074 Analyst Learning Loop is closed. M8 MAG-080 cutover policy and MAG-081 runtime risk review are closed: `2026-05-07--mag080_cutover_policy.md` defines shadow/soak/canary/primary candidate/primary stages, and `2026-05-07--mag081_canary_flag_runtime_risk_review.md` confirms no reviewed single flag can enable true live autonomy without operator approval; `executor.shadow_mode=false` remains the highest-risk surface but live use is still behind the full live 5-gate chain. Next AgentTodo gate is M8 MAG-082 24h canary validation checklist; proposal/approval/channel relay remains later. No service restart, deploy, production continuous event-store flag, live auth, cloud provider call, DB write, runtime submit path change, or trading authority change was applied.
- Scanner Opportunity edge-staunching overlay is closed at commit `98ce3d00`: runtime AccountManager taker-fee cost prior, demo/live_demo new-open canary, and pre-risk rejected intent/verdict row proof are deployed on Linux. That overlay preceded formal AgentTodo M2; formal M2 is now closed separately through MAG-020..026.
- new standalone logic should be Rust-first to avoid adding Python migration debt
- changes must stay cross-platform and Mac-deployable; avoid hard-coded machine paths
- tunable parameters must be real, discoverable, and persistent; no fake knobs
- `bash helper_scripts/restart_all.sh --rebuild` is the default rebuild path for Rust + PyO3 deployments
- operational trading understanding is `demo + live_demo`; paper is not an active trading lane for edge conclusions

## Current context pointers

Primary active-state sources:
- `CLAUDE.md`
- `TODO.md`

REF-21 2026-05-06 empirical gap closure:
- final 8-agent real-code audit accepted; R2/R3 remain BLOCKED
- §10 replay SLA corrected away from pytest `2555/17`
- full-chain prepare now has live-profile `OPENCLAW_REPLAY_BULK_ALLOW_PROD_IP`
  guard
- V057-V060 migration files include Guard A/B/C and passed Linux PG transaction dry-run on `trade-core`; pre-existing objects were absent, all four migrations created expected objects inside the transaction, and rollback left all five target tables absent
- V061 `replay.calculate_promotion_metrics` is now a non-stub SECURITY DEFINER calculator. It derives metrics from `replay.experiments`, `replay.simulated_fills`, and `learning.edge_estimate_snapshots`; includes PSR/DSR, CSCV PBO, stationary bootstrap q10/q50/q90, and fail-closed promotion reasons; Linux transaction dry-run returned `eligible=true` with rollback proof.
- 2026-05-07 S1 replay calibration lift is implemented in source/tests: Rust fills now carry depth partial-fill + latency metadata, Python execution calibration exposes latency q50/q90, reports include balance curve / drawdown / stationary block bootstrap bands / baseline comparison, `/replay/advisory/compare` is read-only, and recorder retention/maturity policy is surfaced. Confidence still depends on local recorder history; do not claim historical L2 for windows before recorder startup.
- GUI/CLAUDE console contract is 13 tabs

Current strategy-edge packet:
- source/runtime sync checkpoint `2026-05-02`: `origin/main`, Mac `main`, and Linux `trade-core` were fast-forwarded through the Codex docs-only memory-sync commits. This is docs/memory only; no rebuild, restart, DB write, risk/strategy config change, or live auth mutation was performed. Check `git log --oneline -3` for the exact latest SHA before committing, because later docs fixes may supersede the first memory-sync commit. A local Codex session may still be on an audit branch after fast-forward; inspect `git status --short --branch` before committing.
- active healthcheck risk `2026-05-02`: Linux watchdog reports demo/live fresh, but passive healthcheck is FAIL because `[40] realized_edge_acceptance`, `[42] live_candidate_eval_contract`, and `[42b] live_candidate_attribution_drift` are red. This matches TODO follow-ups `LG5-W3-FUP-1` and `LG5-W3-FUP-2`.
- immediate high-signal TODO follow-ups: wire `review_live_candidate` consumer scheduler so pending live candidates are audited (`LG5-W3-FUP-1`), and investigate the `attribution_chain_ok` writer gap for grid/ma rows (`LG5-W3-FUP-2`). Treat both as pre-live governance/data quality work, not live-trading authorization.
- P2/P3 backlog from the 2026-05-02 cold audit remains relevant: `MIT-S2-1`, `MIT-S2-2/QC-S2-02`, `QC-S2-01`, `QC-S2-04`, `E3-S2-P2-1/P2-2`, plus P3 cleanup items such as duplicate `is_legacy_close_tag`.
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
- source checkpoint `2026-05-01 22:51 CEST`: `be8fe37` exposes Rust scanner context to Python `/scanner/opportunities`, ScoutWorker intel, MLDE shadow advisor, and DreamEngine; V034 migration file is present but runtime DB apply was not performed. `569e06b` unifies Demo/Paper/Live GUI performance metrics through a backend-authored metric list and shared renderer. Linux source was subsequently synced through doc checkpoint `daca52f`; no rebuild/restart/DB migration apply. Report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-01--todo_continue_scanner_context_gui_metrics.md`
- source checkpoint `2026-05-01 PRE-LIVE-3`: [33]/[38]/[40] are now exposed as a read-only trend/readiness surface via `/api/v1/strategy/prelive/edge-gates`; Live tab renders compact trend cards and a readiness checklist for PostOnly fee-drop, maker-like settlement, grid lifetime/re-entry, realized avg net edge, and active negative cells. This is source/static/API only; no runtime DB write, strategy/risk change, rebuild, restart, or deploy was performed. Report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-01--prelive_edge_gate_trends.md`
- runtime redeploy `2026-05-01 23:17 CEST`: `trade-core` ff-only pulled and redeployed `eaf0c7e` with `PATH=$HOME/.cargo/bin:$PATH bash helper_scripts/restart_all.sh --rebuild --keep-auth`. New Rust engine PID 2455097 and API PID 2455171 are alive; watchdog reports paper/demo/live fresh; `/api/v1/strategy/prelive/edge-gates` returns 401 instead of 404, proving the route is loaded behind auth. Passive wrapper SUMMARY WARN exit 0 with expected edge warnings `[33]`, `[38]`, `[40]` plus `[4]`, `[10]`, `[41]`, `[11]`. No DB migration apply, strategy/risk parameter change, or live auth mutation; `--keep-auth` preserved authorization.
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
