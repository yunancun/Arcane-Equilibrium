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
- when using the `improve-codebase-architecture` skill, answer in Chinese by default for candidate lists, grilling questions, and follow-up summaries; preserve the skill's exact architecture vocabulary (`Module`, `Interface`, `Implementation`, `Depth`, `Seam`, `Adapter`, `Leverage`, `Locality`) and use `CONTEXT.md` domain terms unchanged
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
- GitHub Issues is the active issue tracker for mattpocock engineering skills and new issue/PRD workflow as of the 2026-05-08 operator decision. Linear is historical/passive unless the operator explicitly reopens it. Notion is frozen; Drive is passive; Coupler, MotherDuck, and Slack are declined unless the operator explicitly reopens them.
- Governance register path in this repo is `docs/governance_dev/SPECIFICATION_REGISTER.md`. The older shorthand `docs/SPECIFICATION_REGISTER.md` is not present.
- P2-AUDIT-VERIFY-1 DOCS-1 is source/test closed as of 2026-05-09: `docs/README.md` indexes `docs/agents/`, `../helper_scripts/SCRIPT_INDEX.md`, all top-level `docs/archive/*.md`, and CCAgentWorkSpace now says 19 agents with MIT/BB rows; MIT/BB also have `workspace/README.md`; static guard is `tests/structure/test_docs_readme_index_static.py`.

## GitHub Actions cost policy (2026-05-09)

- Repo is private; free tier is 2000 billable minutes per month.
- macOS runners cost a **10x multiplier**; running Linux + macOS on every `push to main` will exhaust the monthly quota within days at current commit velocity (~99 commits / day in early May 2026, hit 90% quota by 2026-05-09).
- Active workflow `srv/.github/workflows/ci.yml`:
  - `push to main` → Linux only (`x86_64-unknown-linux-gnu`)
  - `pull_request` → Linux + macOS (`aarch64-apple-darwin`)
  - `schedule` weekly Monday 03:00 UTC → Linux + macOS smoke
  - implementation: job-level `if: ${{ matrix.os != 'macos-latest' || github.event_name != 'push' }}` skips the macOS matrix entry on push events.
- Do **not** revert macOS to push-trigger without operator approval; the future Apple Silicon runtime invariant is satisfied by the weekly schedule plus on-demand PR coverage.
- If a change genuinely needs macOS verification mid-cycle outside the schedule, open a PR (triggers macOS matrix) instead of pushing direct to main; or trigger the workflow manually after adding a `workflow_dispatch:` event if needed.
- Do not assume budget is unlimited and do not enable additional macOS jobs without recomputing the multiplier impact.

## Architecture and deployment invariants

- Formal project/product name is `玄衡 · Arcane Equilibrium`; do not use `OpenClaw Bybit` as the total project name in new docs
- Bybit is the only exchange target
- Rust `openclaw_engine` is the canonical trading / risk / config authority
- Python is the control plane, GUI, bridge, and auxiliary surface, not the trading truth layer
- OpenClaw 2026-05-06 repositioning: external OpenClaw Gateway is only communication / mobile / supervisor / cloud-escalation / proposal relay; it is not the trading conductor, not the local 5-Agent runtime, and not a second GUI
- canonical GUI is the existing FastAPI console at `trade-core:8000/console`, now treated as the OpenClaw Control Console
- local 5-Agent runtime stays inside TradeBot; cloud L2 should be reached through a supervisor escalation packet, not by every runtime agent independently
- TODO v25 is the active dispatch queue as of 2026-05-15. PM/PA/FA 5-day audit synchronized TODO/README/CLAUDE/active-plan/MEMORY around these facts: paper promotion is frozen by AMD-2026-05-15-01; A4-C Stage 0R remains GATE-RED; `bb_breakout_oi_confirmed_5m` is spec-only and not execution evidence; `[55]` is source-cleared by the fully-filled plan invariant; `[67]` feature baselines are restored to 646 active rows / 19 symbols / 34 features; latest full passive healthcheck still fails `[27] intents_counter_freeze`; V079 is applied on `trade-core` and `learning.strategy_trial_ledger` has 16,212 rows. Do not start proposal/mobile/second-GUI/Stage 3/4/true-live work from older AgentTodo/TODO/MEMORY text.
- W-AUDIT-2 source close (2026-05-09): Phase4 weekly review, Scout signal/event, and Layer2 trigger mutating routes now require operator+scope gates; restart scripts/docs no longer default Trading API to all-interface bind; AI service Unix socket chmods to `0600`; Rust boot wires `spawn_lease_transition_pipeline` into Paper/Demo/Live GovernanceCore audit emitters. Follow-up P0-NEW-VULN-1 tailnet correction makes lifecycle scripts default to concrete Tailscale IPv4 when available, otherwise loopback.
- P1-REPLAY-2 is runtime-applied: on 2026-05-08 Linux `trade-core` applied V066 twice via `linux_bootstrap_db.sh --apply V066` for idempotency, verified `replay_report` and `byte_size >= 0` constraints, passed a rollback smoke insert/reject test, and reloaded runtime with `restart_all.sh --keep-auth`. Post-reload watchdog returned `engine_alive=true`; passive healthcheck was `SUMMARY: WARN` with no hard FAIL.
- P2-PYDANTIC-1 is complete for replay surfaces: `@validator` callsites in `replay/experiment_registry.py` and `replay/replay_models.py` were migrated to Pydantic V2 `@field_validator`; `pytest.ini` pins `asyncio_default_fixture_loop_scope=function` so deprecation warnings can be treated as errors in targeted replay tests.
- P2-SEC-1 is complete for replay finalize: 503 responses now return a generic internal persistence error under `replay_finalize_failed` without exposing backend exception class/message to clients.
- AgentTodo Sprint A through M8 are historical. MAG-015..082 are closed; W-C MAG-082 Stage 2 reached WINDOW_PASS on 2026-05-11, and W-D MAG-083/MAG-084 were signed/closed on 2026-05-11. Proposal/approval/channel relay, Stage 3/4, and true-live autonomy remain blocked by separate W-AUDIT / edge / LG / ops gates; do not treat old MAG-083/MAG-084 blocked handoff text as current.
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

P1 healthcheck FAIL queue 2026-05-07:
- Operator inserted current Linux healthcheck FAILs ahead of P1 Important work: `[Xb]`, `[42]`/`[42b]`/`[42c]`, `[50]`, `[51]`.
- Queue is now cleared to PASS/WARN as of Linux passive healthcheck `2026-05-07T17:51:38Z` (`SUMMARY: WARN`): `[Xb]` and `[42]` no longer emitted; `[42b/c]`, `[50]`, `[51]` are explained WARNs.
- RCA/fixes: `c8240b6a` drains unaudited LG5 candidates; `4654964d` aligns attribution drift to settled samples; `898f4a90` downgrades replay failures superseded by newer completed runs; `84f63706` separates scanner exploration from calibrated `opportunity_positive`; `4f437ea1` scopes pipeline triangulation to close-fill-linked intent contexts while keeping raw scanner intent volume diagnostic.
- Current P1/W-B/W-C order: `P1-FAKE-1`, `P1-OPENCLAW-3`, `P1-OPENCLAW-6/7`, source-level `P1-AGENT-OBS-1`, and runtime `P1-AGENT-RUNTIME-1` are closed; W-C MAG-082 Stage 2 evidence collection is active, not complete. On 2026-05-08 Linux `trade-core` first deployed `3d6f62dd` with `OPENCLAW_AGENT_SPINE_RUNTIME_MODE=shadow`, then `8f8fb252` with `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1`, then `503eeb33` retiring scanner legacy hard-gate authority via `restart_all.sh --rebuild --keep-auth`; engine PID `3854831`, API PID `3854909`. Process env proved both shadow spine and lease-router gate flags; `scanner_config.toml` no longer has `[authority]`; scanner is always-on market context/evidence only and cannot hard-gate opens/closes/live auth/order dispatch. Engine log showed `agent_spine_writer started`; `[55] agent_decision_spine_lineage` PASSed with `MAG-082 readiness=LINEAGE_READY_NOT_WINDOW_PASS`, objects=290/290, edges=232/232, idempotency=58/58, types strategy_signal/strategist_decision/guardian_verdict/execution_plan/execution_report all 58, chains=58, chains_with_idempotency=58, chains_with_lease=33, chains_with_report=58, bad_report_quality=0. This is shadow/bypass lineage only and does not grant live authority; W-C still needs the 24h window PASS before MAG-083/MAG-084. P1-DATA-1 source fixes are in place: `[14]` distinguishes risk/cost gate suppression from writer-health evidence while still warning on stalled sample accumulation; `[37]` treats historical failures as recovered when later non-failed rows exist and no recent failures remain; `[40]` catches negative strategy/symbol cells combined across demo/live_demo; `LABUSDT` is source-configured in grid_trading.blocked_symbols across paper/demo/live to block new grid entries only; `[45]` accepts recent AccountManager fee-use proof during rejected-only demo/live_demo no-fill windows. P1-DATA-2 source fix is in place: `[42b]`/`[42c]` now render low-sample attribution strategies as `LOW_SAMPLE(n, need)` sample-maturity watch instead of misleading `0.000` ratio drift while preserving hard FAIL bands for mature ratio regressions. P1-DATA-3 source fix is in place: `[51]` now requires mature `opportunity_positive` samples before PASS, reports `MATURE/LOW_SAMPLE(n, need)`, and keeps scanner opportunity shadow-only for exploration-only or immature calibrated samples. P1-DATA-4 source fix is in place: `[41] scanner_market_gate_confirmation` is legacy scanner would-block evidence calibration; contradictions are WARN only, because scanner is always-on evidence and cannot hard-gate opens/closes/live auth/order dispatch. P1-EDGE-1 source fix is in place: runtime 7d ma_crossover combined demo/live_demo was negative mainly from `LABUSDT` (`n=6 avg=-244.54bps`), so `LABUSDT` is source-blocked for ma_crossover new entries in risk configs; bb_breakout 1m rescue is retired and revised to real 5m indicators, demo-only active, live disabled pending fresh net-positive evidence.
- P2 maintenance closeout 2026-05-08: `P2-MIG-1` added V054 migration sibling tests; `P2-REPLAY-1` added V067 `replay.run_state.subprocess_started_at_ms` plus spawn/finalize PID start-time verification; `P2-RUST-1` split `intent_processor/tests.rs` to 1556 LOC and moved larger nested suites to `tests_predictor_router.rs` (1363 LOC). Targeted checks passed: migration tests, replay PID/finalize tests, `py_compile`, `cargo test -q --lib intent_processor`, and `cargo fmt --check`.
- Boundary after W-C activation: engine/API were rebuilt/restarted with `--keep-auth` for shadow Agent Spine, Decision Lease router-gate evidence, and scanner always-on evidence semantics only. No live auth mutation, real live API enablement, strategy/risk parameter change, scanner hard authority, executor order authority, Stage 3/4 approval, or MAG-083/MAG-084 approval was performed.
- W-AUDIT-1 source-closed 2026-05-09: CLAUDE §三/§四/§五/§十 synced to current runtime facts; W-C authorization file added at `docs/governance_dev/2026-05-08--w_c_lease_router_authorized.md`; AMD-2026-05-02-01 gained §5.4.1; ADR-0015..0019, CONTEXT glossary, SPECIFICATION_REGISTER LG-X/SM-03/EX-03/ARCH-02/03/AUDIT-13, docs/README addendum, SCRIPT_INDEX, and MIT/BB README files were added/updated. This was docs/governance only: no rebuild/restart/live auth/order authority/strategy-risk change/MAG-083/MAG-084.

Current strategy-edge packet:
- The 2026-05-02 source/runtime sync and `[40]`/`[42]`/`[42b]` FAIL notes are historical; current active state is the 2026-05-09 W-AUDIT-1 / TODO v16 state above. Do not use the older LG5-W3-FUP queue as current dispatch order.
- Current runtime passive healthcheck is WARN, not FAIL. Remaining active edge/observation risk is tracked by TODO v16 W-C/W-AUDIT/P0/P1 rows plus `[33]`, `[38]`, `[40]`, `[41]`, `[42b/c]`, `[45]`, and `[51]` watch conditions.
- Treat strategy/data follow-ups as pre-live governance and observation work unless CLAUDE/TODO explicitly grants a later live authority gate.
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

W-AUDIT-3 F-01 current fact:
- as of 2026-05-09, `ExecutorAgent.__init__` no longer installs a hidden
  `lambda: True` fallback for missing `shadow_mode_provider`
- production wiring remains explicit through
  `ExecutorConfigCache.shadow_mode_provider()` in `strategy_wiring.py`
- provider missing/exception paths are fail-closed in `_read_shadow_mode()`
  before IPC submit authority; source/test only, no rebuild/restart

W-AUDIT-6 current fact:
- as of 2026-05-09, `bb_breakout` cooldown drift is source/test closed:
  `BbBreakoutParams::default()` and `BbBreakout::new()` share
  `DEFAULT_COOLDOWN_MS=300_000`, and tests assert both `cooldown_ms` and
  `TrendCooldown` duration match the params default
- as of 2026-05-09, Kelly tier fraction config is source/test closed:
  `RiskConfig.kelly.{young,mature,established}_fraction` defaults to
  `1/8`, `1/6`, `1/4`, `ml::kelly_sizer::compute_kelly_qty()` consumes those
  fields instead of hardcoded divisors, and risk TOMLs expose the same
  behavior-preserving defaults
- as of 2026-05-09, fast_track held-drop thresholds are source/test closed:
  `RiskConfig.fast_track.{extreme_drop_pct,moderate_drop_pct,outlier_sigma_threshold}`
  defaults to `15.0`, `5.0`, `3.0`; Step 0 fast_track decisions, scoped-reduce
  classification, and sigma-scaled reduce cooldown consume that snapshot; the
  90% margin-crisis guard remains a code safety constant; risk TOMLs expose the
  same behavior-preserving defaults
- as of 2026-05-09, F-13 selection-bias promotion gate is source/test closed:
  `program_code/learning_engine/promotion_gate.py` composes existing DSR(K) and
  PBO/CSCV math into a JSON-safe fail-closed result, and
  `promotion_pipeline.py` now requires `demo_selection_bias_report.passes=true`
  for Demo→LivePending graduation; missing CV returns, insufficient PBO power,
  high PBO, DSR block, or DSR borderline prevent promotion
- as of 2026-05-09, per_trade_risk_pct SSOT is source/test closed:
  shared `MIN/MAX/DEFAULT_PER_TRADE_RISK_PCT` constants define the
  `0.001..=0.20` validation/runtime clamp bounds; `KellyConfig::from_risk_config()`
  derives Kelly cold-start `risk_pct` plus tier fractions from
  `RiskConfig`; replay runner and `IntentProcessor::update_risk_config()` now
  consume that RiskConfig-derived snapshot
- as of 2026-05-09, funding_arb RiskConfig cleanup is source/test closed:
  all four `settings/risk_control_rules/risk_config*.toml` files contain no
  `funding_arb`, while `strategy_params_{paper,demo,live}.toml` remain the
  retirement authority with `funding_arb.active=false`; real TOML Rust
  regressions lock this split; the same checkpoint cleaned existing lib-test
  warnings and wired `grid_trading` PostOnly reject callback to its cooldown
  helper
- as of 2026-05-09, ma_crossover R:R trailing/TP is source/test closed:
  `StrategyOverride.take_profit_enforced_override` enables MA-only TP
  enforcement without globally enabling TP for grid / BB; four
  `settings/risk_control_rules/risk_config*.toml` files bind MA exits to
  stop-loss `2.5%`, take-profit `8.0%`, TP enforcement `true`, trailing
  activation `0.6%`, and trailing distance `0.4%`; Rust lib tests cover
  per-strategy TP enforcement and real TOML wire shape
- as of 2026-05-09 post-rebuild, `[40] realized_edge_acceptance` surfaced a
  `grid_trading/BILLUSDT` 24h negative cell (`n=11 avg=-49.67bps`); `BILLUSDT`
  is source-blocked for new grid entries across
  `strategy_params_{paper,demo,live}.toml`, while close/reduce remains allowed;
  the 24h healthcheck may remain FAIL until historical rows roll off
- as of 2026-05-09, bb_breakout 5m RFC/IMPL is source/test closed at
  `6d3ea046`:
  `TickContext` carries `indicators_5m`, `TickPipeline` computes 5m indicators
  from `KlineManager`, initial kline bootstrap seeds 1m + 5m REST bars,
  `BbBreakoutParams` and `strategy_params_*.toml` expose `signal_timeframe`,
  and runtime `bb_breakout` skips when configured 5m data is not warm instead
  of falling back to 1m. Demo is active on the 5m family; paper/live stay
  inactive.
- as of 2026-05-09, `P0-V2-NEW-1-DONCHIAN-LEAK-BIAS` is source/test closed:
  runtime `IndicatorEngine::compute_all_with_lambda()` emits Donchian snapshots
  via `donchian_prior()`; `donchian()` remains the explicit inclusive helper.
  Regression tests prove current-bar high/low spikes are excluded from runtime
  snapshots and `bb_breakout` 5m hard-gate entry uses the prior-bar upper. No
  runtime reload/rebuild, strategy pause, DB write, or live auth mutation was
  performed.
- as of 2026-05-09, `P0-V2-NEW-2-STRATEGIST-CAP-NO-GATE` is source/test
  closed by operator decision: keep the 50% maximum freedom, do not add a new
  hard/supervised gate, and do not revert to 30%. Rust strategist evaluation
  payloads now include `strategist_skill.name=wide_parameter_adjustment`,
  `normal_delta_pct=0.30`, and `max_delta_pct=<RiskConfig snapshot>`; Python
  prompts render `normal_range` and `wide_skill_range`, teaching <=30% as
  ordinary tuning and 30%-50% as a deliberate skill. Rust still validates only
  the configured max envelope. No runtime reload/rebuild/provider call.
- as of 2026-05-09, W-AUDIT-6c portfolio VaR/CVaR/EVT is source/test closed at
  `cc6476dd`: `program_code/learning_engine/cvar.py` implements historical
  VaR/CVaR, EVT/GPD tail fit, and stationary block-bootstrap VaR/CVaR
  confidence intervals; `portfolio_var.py` implements portfolio return
  composition, LUNA/FTX/COVID stress scenarios, and `PortfolioTailRiskGate`;
  `PromotionGate` now requires `demo_tail_risk_report.passes=true` before
  DEMO_ACTIVE can graduate to LIVE_PENDING. Missing stress exposures,
  insufficient observations, EVT low confidence, historical VaR/CVaR breach,
  or stress breach fail closed.
- as of 2026-05-09, W-AUDIT-5 F-12 true-file mismatch is source/test closed:
  `rust/openclaw_engine/src/replay/runner.rs` was split from 2469 LOC to 1166
  LOC by moving module-internal tests to sibling `runner_tests.rs` (1299 LOC).
  `tests/structure/test_replay_runner_split_static.py` now guards both files
  under the 2000 LOC cap; this is source/test only, no rebuild/restart.
- as of 2026-05-09, A3 NEW-1 / `P2-AUDIT-VERIFY-6` openConfirmModal a11y is
  source/test closed: both `common.js` and legacy `app.js` confirm modal paths
  support dialog role/`aria-modal`, Esc cancel, Tab focus trap, initial cancel
  focus, and previous-focus restore. Static regression and JS syntax checks
  passed; no backend/runtime change.
- as of 2026-05-09, `P2-AUDIT-VERIFY-7` NEW-VULN-3/4 is source/test closed:
  auth cookie Secure auto mode treats positive HTTPS proxy hints as a
  fail-closed Secure signal even without trust-proxy env, and Phase4 router is
  mounted in Control API `main.py` so the weekly-review operator+scope gates are
  reachable. No runtime reload/restart was performed.
- runtime apply note: the operator-requested post-sync rebuild loaded the MA R:R
  checkpoint, and the follow-up rebuild/restart loaded the BILLUSDT grid
  blocklist. The later bb_breakout 5m and W-AUDIT-6c portfolio tail-risk
  checkpoints are source/test only until the next explicitly authorized
  rebuild/restart.
- as of 2026-05-09, `P0-V2-NEW-3-DSR-PBO-EVIDENCE-CRON` is source/test
  closed: James-Stein cycles return real per-cell raw return series;
  `ml_training.promotion_evidence` builds DSR/PBO/tail-risk evidence from those
  real series; `edge_estimator_scheduler.py` pushes Demo-only promotion
  evidence; V079 adds `learning.strategy_trial_ledger` and promotion report
  JSON columns. Superseded 2026-05-15: `trade-core` now has migrations through
  V090 applied, V079 is present, and `learning.strategy_trial_ledger` has
  16,212 rows. This does not grant promotion/live authority.
- as of 2026-05-09, `P2-AUDIT-VERIFY-5` is source/test closed:
  `docs/governance_dev/strategy_blocked_symbols_freeze.json` freezes the
  current grid 17-symbol and MA 4-symbol blocklists, and
  `tests/structure/test_strategy_blocked_symbols_freeze.py` fails if source
  config grows the lists without updating the freeze policy. Future blocked
  cells require RFC + 7d counterfactual/rejected-outcome evidence + DSR/PBO or
  explicit QC waiver. Read-only Linux evidence showed blocked MA rejections
  currently have `decision_outcomes=0`, so true rejected-outcome
  counterfactual power is not yet available; do not add more blocked symbols as
  a quick negative-cell reaction.

P0-NEW-VULN-1 bind-host rule:
- lifecycle scripts must not default to `0.0.0.0`
- default `OPENCLAW_BIND_HOST=auto` resolves the node's concrete Tailscale IPv4
  when available, otherwise `127.0.0.1`
- `OPENCLAW_BIND_HOST=tailscale` forces tailnet-only binding; `0.0.0.0` / `::`
  are rejected by `helper_scripts/lib/api_bind_host.sh`

Detailed 2026-04-29 A-F remediation and redeploy context was compacted out of this file and preserved in:
- `.codex/archive/2026-04-29--pre-compaction-memory-snapshot.md`

## Maintenance rule

- keep this file concise, durable, and reusable across sessions
- move long batch logs to `WORKLOG.md`, reports, or archive snapshots
- update this file only for lasting workflow rules, topology, or project-state facts
