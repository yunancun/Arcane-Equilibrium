# AgentTodo: Multi-Agent Rework

Date: 2026-05-05
Status: Draft task backlog
Parent plan: `ENGINEERING_PLAN.md`

## 2026-05-06 OpenClaw Repositioning Overlay

This backlog is governed by the 2026-05-06 OpenClaw repositioning decision:

- Local 5-Agent runtime remains inside TradeBot and must not be migrated into the external OpenClaw Gateway.
- OpenClaw Gateway is an external communication / mobile / supervisor / proposal relay layer only.
- The existing FastAPI console is the only canonical GUI and is now the target OpenClaw Control Console.
- `MessageBus` is a legacy/advisory local trace; it may be observed, sampled, and audited, but it must not be promoted into the authoritative Agent Decision Spine.
- Cloud AI is called through a supervisor escalation pattern, not by every local agent independently.

Canonical overlay and implementation plans:

- `docs/architecture/2026-05-06--openclaw_control_plane_repositioning.md`
- `docs/execution_plan/2026-05-06--openclaw_gateway_development_plan.md`
- `docs/execution_plan/2026-05-06--gui_openclaw_control_console_plan.md`

If older EX-06 / DOC-04 wording implies OpenClaw itself is the trading conductor or that OpenClaw's own GUI is the primary console, that wording is superseded by this overlay.

## 2026-05-06 PM Handoff Verdict and Start Order

PM review result: this backlog now reflects the new authority model at the boundary level, but implementation must start from the data and contract foundation. Do not begin with Telegram/WebChat, a second GUI, or a broad cloud-agent buildout.

MAG-015 Sprint A contract addendum is now frozen in `2026-05-06--mag015_sprint_a_contract_addendum.md`. MAG-010..014 may start as the durable event-store wave only; MAG-016..019 must consume the frozen allowlist, view-model, budget, ownership, and state-transition contracts from that addendum.

Dispatch-ready order for the next handoff:

1. **Contract addendum first**: complete MAG-015 before implementation. It must define typed local observations, `SelfStateSnapshot`, `Diagnosis`, `EscalationPacket`, `Proposal`, `ApprovalDecision`, `ChannelEvent`, endpoint allowlist, cloud budget, and store ownership.
2. **Durable event store second**: complete MAG-010..MAG-014 until Linux runtime proves nonzero fresh rows in `agent.messages`, `agent.state_changes`, and `agent.ai_invocations`. This is a P0 governance blocker and a prerequisite for trustworthy OpenClaw views.
3. **Read-only OpenClaw bridge third**: MAG-016..MAG-017 is complete for authority lockdown and `/api/v1/openclaw/status` + `/api/v1/openclaw/self-state` at `cbb225b7`. No proposals, approvals, or mobile relay were added.
4. **Read-only Agent Control GUI fourth**: MAG-018 is complete at `12d3f3ff` on top of backend view models. The GUI does not stitch raw tables in JavaScript and does not add trading controls.
5. **Supervisor escalation fifth**: next complete MAG-019 only after `agent.ai_invocations` is populated. Cloud L2 calls go through one supervisor packet, not five independent agent calls.
6. **Proposal / approval / channel relay last**: use the standalone OpenClaw Gateway and GUI plans for OC-GW-5..7 and GUI-OC-4..7 after the read-only foundation is proven.

This means the first implementation sprint should be **AgentTodo Sprint A: MAG-015 -> MAG-010/011/012 -> MAG-013/014 -> MAG-016/017 -> MAG-018/019**. M2 Scanner Advisory Conversion and M3 Agent Decision Spine Shadow remain blocked until M1 has Linux row proof and E2/E4 acceptance.

## 2026-05-06 Scanner Opportunity Edge-Staunching Overlay

Scanner-specific edge staunching is now closed for this session outside the
formal M2 Agent Decision Spine conversion:

- `98ce3d00` deployed a typed Scanner Opportunity admission canary on Linux
  `trade-core`.
- Scanner opportunity cost now uses the shared `AccountManager` taker-fee
  prior, including conservative AccountManager defaults at cold boot, with
  `components.cost_source` persisted for audit.
- `settings/risk_control_rules/scanner_config.toml [opportunity]` has
  `canary_block_new_entries = true`; this affects demo/live_demo new-open
  intents only.
- Scanner market-gate / per-strategy pre-risk rejects and the new opportunity
  canary reject now persist `trading.intents` + synthetic rejected
  `trading.risk_verdicts` rows with `details.scanner.opportunity`, so `[51]`
  can accumulate counterfactual row proof.
- Linux runtime proof after deploy: latest scanner snapshot route judgments
  `85/85` carry opportunity, `85/85` carry `cost_source=account_manager_taker_fee`,
  `85/85` carry canary fields; last 30m demo/live_demo rejected scanner intents
  `78/78` carried scanner opportunity, including `2` `scanner_opportunity_canary`
  rejects.

This does **not** mark M2 MAG-020..026 done. Formal M2 still means converting
scanner lifecycle into Agent Decision Spine advisory objects (`OpportunityCandidate`,
`OpportunityDecay`, `PositionReview`) after M1 durable agent row proof. The current
overlay is a general Rust-side mathematical new-entry admission guard and row-proof
closure for the existing legacy path.

## Reference Path Index

Canonical repo root:

- `/Users/ncyu/Projects/TradeBot/srv`

This todo is intentionally self-contained. A follow-up agent should start from the paths below and should not need to scan the full repo to find the original design, current audit evidence, or likely implementation files.

### Original Design and Governance Sources

| Area | Path | Why it matters |
|---|---|---|
| Original multi-agent boundary | `docs/decisions/EX-06_OpenClaw_Bybit_Multi-Agent_Orchestration_多Agent编排正式边界定义_V1.md` | Defines Scout / Strategist / Guardian / Analyst / Executor / Conductor authority and structured inter-agent communication. |
| Agent capability blueprint | `docs/decisions/DOC-04_OpenClaw_Bybit_Agent_Capability_Blueprint_Agent能力蓝图_V2.md` | Defines autonomous trading target: instrument, strategy, timing, size, params, scanner, learning, AI cost, anti-adversarial awareness. |
| OpenClaw control-plane overlay | `docs/architecture/2026-05-06--openclaw_control_plane_repositioning.md` | Supersedes the early OpenClaw-as-trading-conductor interpretation; defines one GUI and two agent layers. |
| OpenClaw Gateway development plan | `docs/execution_plan/2026-05-06--openclaw_gateway_development_plan.md` | Defines how to use OpenClaw as communication, mobile, supervisor, proposal, and approval relay. |
| GUI OpenClaw Control Console plan | `docs/execution_plan/2026-05-06--gui_openclaw_control_console_plan.md` | Defines how the existing console absorbs OpenClaw capabilities without creating a second GUI. |
| Sprint A contract addendum | `docs/architecture/multi_agent_rework_2026-05-05/2026-05-06--mag015_sprint_a_contract_addendum.md` | MAG-015 frozen contract for local observations, OpenClaw view models, escalation/proposal/channel schemas, endpoint allowlist, cloud budget, store ownership, and state transitions. |
| Data/perception plane | `docs/decisions/EX-07_OpenClaw_Bybit_Data_Plane_Perception_感知平面正式边界定义_V1.md` | Use when deciding whether scanner evidence belongs to perception, Scout, H0 eligibility, or Guardian risk evidence. |
| Root rules and runtime reality | `CLAUDE.md` | Current root principles, runtime sync rules, active blockers, Rust engine authority, Decision Lease status. |
| Active work list | `TODO.md` | Current P0/P1 blockers, including agent schema zero rows and fake-live/shadow wiring. |
| Codex durable memory | `.codex/MEMORY.md` | Session-level operating memory and current project assumptions. |
| 5-Agent runtime audit | `memory/project_5agent_runtime_state.md` | Key evidence that Python 5-Agent is advisory/shadow and Rust engine is trading authority. |
| R-06 value audit | `docs/references/2026-04-13--r06_deep_analysis_agent_value.md` | Key evidence of Path A / Path B split, Conductor idle methods, Analyst consumer gap. |
| Scout/Conductor initial changelog | `docs/governance_dev/changelogs/2026-03-29_T2.07_scout_agent_conductor.md` | Historical implementation claim for EX-06 Scout + Conductor. |
| Batch 7 multi-agent chain changelog | `docs/governance_dev/changelogs/2026-03-30_Batch7_S2_multi_agent_chain.md` | Historical implementation details for Strategist, Guardian, Analyst, Executor prewrites. |

### Current Python Agent Implementation Paths

| Area | Path | Start here for |
|---|---|---|
| Shared agent contracts and MessageBus | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/multi_agent_framework.py` | AgentRole, MessageType, AgentMessage, IntelObject, TradeIntent, RiskVerdict, MessageBus. |
| Conductor implementation | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/multi_agent_conductor.py` | Registry, lifecycle, arbitration, resource allocation, process_trade_intent. |
| Base lifecycle/audit behavior | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/base_agent.py` | Common agent state, start/stop, audit callback behavior. |
| Agent wiring singleton | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_wiring.py` | How Scout/Strategist/Guardian/Analyst/Executor are instantiated and subscribed. |
| Scanner to Scout wiring | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_wiring_scanner.py` | ScoutWorker scan loop, Rust scanner opportunity ingestion, intel injection. |
| Scout Agent | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/scout_agent.py` | produce_intel, produce_event_alert, Scout authority boundary. |
| Scout worker | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/scout_worker.py` | Periodic Scout scan worker and liveness behavior. |
| Rust scanner reader | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/rust_scanner_reader.py` | Python-side access to Rust scanner opportunities. |
| Strategist main agent | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategist_agent.py` | Intel handling, H1/H3/H4 routing, pattern/risk/directive handlers. |
| Strategist edge evaluation | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategist_edge_eval.py` | AI/heuristic edge eval and TradeIntent production. |
| Strategist weights/insight consumption | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategist_weights.py` | PatternInsight -> strategy preference weights. |
| Strategist cognitive modulation | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategist_cognitive.py` | Consecutive loss handling, emergency channel, cognitive modulation. |
| H1 thought gate | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/h1_thought_gate.py` | Pre-AI budget/complexity/cooldown gate. |
| Model router | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/model_router.py` | L1/L1.5/L2 routing. |
| H4 validator | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/h4_validator.py` | AI output structure validation. |
| Guardian Agent | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/guardian_agent.py` | Current five-check risk review and event alert handling. |
| Analyst Agent | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/analyst_agent.py` | L1 trade analysis, L2 pattern insight, PatternInsight bus emission. |
| Analyst record contracts | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/analyst_records.py` | TradeRecord, PatternInsight, AnalystConfig. |
| Analyst pattern claims | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/analyst_pattern_claims.py` | TruthRegistry pattern claim registration. |
| Executor Agent | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_agent.py` | Decision Lease acquisition, shadow/IPC execution bridge, ExecutionReport. |
| Executor runtime config | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_config_cache.py` | Shadow mode runtime cache and fail-closed default. |
| Agent audit bridge | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/agent_audit_bridge.py` | Current bridge from agent audit callback to GovernanceHub audit log. |
| AI service IPC handlers | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/ai_service.py` | Python IPC entry points used by Rust scheduler/agent-related calls. |
| AI service dispatch | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/ai_service_dispatch.py` | Dispatch path for conductor/agent style requests. |
| GovernanceHub | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_hub.py` | Decision Lease, governance authority, risk upgrade hooks. |
| Lease IPC bridge | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_lease_bridge.py` | Python/Rust Decision Lease bridge. |
| H0 gate | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/h0_gate.py` | Existing Python H0 singleton; check current production caller status before using. |

### Current Rust Trading Engine Paths

| Area | Path | Start here for |
|---|---|---|
| Engine bootstrap | `rust/openclaw_engine/src/main.rs` | Scanner runner spawn, pipeline channels, shared symbol registry wiring. |
| Pipeline spawn and disabled paper behavior | `rust/openclaw_engine/src/main_pipelines.rs` | Paper/demo/live pipeline setup and disabled paper command behavior. |
| Tick pipeline dispatch | `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs` | Current scanner gate, strategy action dispatch, scanner context on intents. |
| Tick H0 gate step | `rust/openclaw_engine/src/tick_pipeline/on_tick/step_0_5_h0_gate.rs` | Hot-path deterministic gate candidate for hard eligibility. |
| Tick risk checks | `rust/openclaw_engine/src/tick_pipeline/on_tick/step_6_risk_checks.rs` | Existing Rust-side risk close/check behavior. |
| Tick strategy signals | `rust/openclaw_engine/src/tick_pipeline/on_tick/step_3_signals.rs` | Current strategy signal collection point. |
| Pipeline commands | `rust/openclaw_engine/src/tick_pipeline/commands.rs` | PipelineCommand variants, SubmitOrder, scanner/query commands. |
| Pipeline helpers | `rust/openclaw_engine/src/tick_pipeline/pipeline_helpers.rs` | Order dispatch helpers, close handling, position helpers. |
| Scanner runner | `rust/openclaw_engine/src/scanner/runner.rs` | Scan loop, open position query, scan result persistence, WS subscription changes. |
| Scanner registry | `rust/openclaw_engine/src/scanner/registry.rs` | Active symbols, pinned symbols, anti-churn, add/remove logic. |
| Scanner types | `rust/openclaw_engine/src/scanner/types.rs` | ScanResult, candidate types, score fields. |
| Scanner scoring | `rust/openclaw_engine/src/scanner/scorer.rs` | Candidate scoring and context generation. |
| Scanner market judgment | `rust/openclaw_engine/src/scanner/market_judgment.rs` | Route mode / market gate style judgments. |
| Scanner config | `rust/openclaw_engine/src/scanner/config.rs` | Scanner thresholds, anti-churn, hard filters. |
| Scanner strategy policy | `rust/openclaw_engine/src/scanner/strategy_policy.rs` | Strategy route eligibility by market/policy. |
| Strategist scheduler | `rust/openclaw_engine/src/strategist_scheduler/mod.rs` | Current Rust-side param tuning loop and IPC to Python strategist_evaluate. |
| Strategist scheduler eval | `rust/openclaw_engine/src/strategist_scheduler/evaluate.rs` | Pair ranking and evaluation input construction. |
| Strategist scheduler persistence | `rust/openclaw_engine/src/strategist_scheduler/persist.rs` | Applied parameter persistence. |
| Orphan handler | `rust/openclaw_engine/src/position_reconciler/orphan_handler.rs` | Important scanner-rotation-not-close behavior and orphan adoption/close logic. |
| Position reconciler | `rust/openclaw_engine/src/position_reconciler/mod.rs` | Drift/orphan/ghost reconciliation path. |

### Database and Migration Paths

| Area | Path | Start here for |
|---|---|---|
| Agent schema DDL | `sql/migrations/V003__trading_agent_tables.sql` | Existing `agent.messages`, `agent.ai_invocations`, `agent.state_changes` definitions. |
| Engine mode DDL changes | `sql/migrations/V015__engine_mode_separation.sql` | Engine mode additions to agent/trading tables. |
| DB helper scripts | `helper_scripts/db/` | Runtime healthchecks and DB operational scripts. |
| Passive wait healthcheck | `helper_scripts/db/passive_wait_healthcheck.sh` | Required style for silent-dead healthchecks. |

### UI and Observability Paths

| Area | Path | Start here for |
|---|---|---|
| Agent routes | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/agents_routes.py` | API surface for agent status. |
| Agent route helpers | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/agents_routes_helpers.py` | Agent response helper logic. |
| Planned OpenClaw routes | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/openclaw_routes.py` | Suggested new home for `/api/v1/openclaw/*` aggregation endpoints; keep backend-authored view models here rather than ad hoc frontend stitching. |
| Planned OpenClaw models | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/openclaw_models.py` | Suggested new home for `SelfStateSnapshot`, `Diagnosis`, `EscalationPacket`, `Proposal`, `ApprovalDecision`, and `ChannelEvent` API contracts. |
| Agent tab HTML | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-agents.html` | Current agent roster UI. |
| Agent tracker JS | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/js/agent-tracker.js` | Frontend agent tracker behavior. |

## Milestone Start Paths

| Milestone | Primary paths |
|---|---|
| M0 Review and Contract Freeze | `ENGINEERING_PLAN.md`, `docs/decisions/EX-06_OpenClaw_Bybit_Multi-Agent_Orchestration_多Agent编排正式边界定义_V1.md`, `docs/decisions/DOC-04_OpenClaw_Bybit_Agent_Capability_Blueprint_Agent能力蓝图_V2.md`, `CLAUDE.md`, `TODO.md` |
| M1 Durable Agent Event Store | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/multi_agent_framework.py`, `program_code/exchange_connectors/bybit_connector/control_api_v1/app/base_agent.py`, `program_code/exchange_connectors/bybit_connector/control_api_v1/app/agent_audit_bridge.py`, `sql/migrations/V003__trading_agent_tables.sql`, `sql/migrations/V015__engine_mode_separation.sql` |
| M1A OpenClaw Read-Only Foundation | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/agents_routes.py`, `program_code/exchange_connectors/bybit_connector/control_api_v1/app/openclaw_routes.py`, `program_code/exchange_connectors/bybit_connector/control_api_v1/app/openclaw_models.py`, `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-agents.html`, `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/js/agent-tracker.js` |
| M2 Scanner Advisory Conversion | `rust/openclaw_engine/src/scanner/runner.rs`, `rust/openclaw_engine/src/scanner/registry.rs`, `rust/openclaw_engine/src/scanner/types.rs`, `rust/openclaw_engine/src/scanner/market_judgment.rs`, `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs`, `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_wiring_scanner.py` |
| M3 Agent Decision Spine Shadow | `rust/openclaw_engine/src/tick_pipeline/on_tick/step_3_signals.rs`, `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs`, `rust/openclaw_engine/src/tick_pipeline/commands.rs`, `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategist_agent.py`, `program_code/exchange_connectors/bybit_connector/control_api_v1/app/guardian_agent.py`, `program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_agent.py` |
| M4 Strategist V2 | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategist_agent.py`, `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategist_edge_eval.py`, `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategist_weights.py`, `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategist_cognitive.py`, `rust/openclaw_engine/src/strategist_scheduler/mod.rs`, `rust/openclaw_engine/src/strategist_scheduler/evaluate.rs` |
| M5 Guardian V2 | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/guardian_agent.py`, `program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_hub.py`, `rust/openclaw_engine/src/tick_pipeline/on_tick/step_6_risk_checks.rs`, `rust/openclaw_engine/src/scanner/market_judgment.rs` |
| M6 Executor Planner | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_agent.py`, `program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_config_cache.py`, `program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_lease_bridge.py`, `rust/openclaw_engine/src/tick_pipeline/commands.rs`, `rust/openclaw_engine/src/tick_pipeline/pipeline_helpers.rs` |
| M7 Analyst Learning Loop | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/analyst_agent.py`, `program_code/exchange_connectors/bybit_connector/control_api_v1/app/analyst_records.py`, `program_code/exchange_connectors/bybit_connector/control_api_v1/app/analyst_pattern_claims.py`, `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategist_weights.py`, `program_code/exchange_connectors/bybit_connector/control_api_v1/app/guardian_agent.py` |
| M8 Canary and Cutover | `CLAUDE.md`, `TODO.md`, `helper_scripts/db/passive_wait_healthcheck.sh`, `program_code/exchange_connectors/bybit_connector/control_api_v1/app/agents_routes.py`, `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/js/agent-tracker.js` |

## Execution Rule

Recommended dispatch chain for this architecture work:

PM -> CC -> FA -> PA -> E1/E1a -> E2 -> E4 -> QA -> PM

Do not start implementation before CC/FA/PA confirm the authority model:

- Scanner advisory vs gate.
- Rust engine as execution engine vs hidden decision authority.
- Agent Decision Spine persistence requirements.
- Guardian/Decision Lease enforcement order.
- OpenClaw Gateway read/proposal/approval boundary and endpoint allowlist.
- Supervisor cloud escalation budget, ledger, and no-per-agent-cloud-call rule.

## Milestone 0: Review and Contract Freeze

| ID | Owner | Priority | Status | Task | Acceptance |
|---|---|---:|---|---|---|
| MAG-000 | PM | P0 | DONE | Review `ENGINEERING_PLAN.md` with operator and confirm target architecture. | Operator confirmed: scanner must be advisory/evidence, Strategist owns open/hold/reduce/close/no_action decisions, Guardian owns non-bypassable veto/modify authority, Rust remains execution engine without hidden decision authority. |
| MAG-001 | CC | P0 | DONE | Compliance review against root principles, EX-06, DOC-04, SM-02 Decision Lease, H0/P0/P1. | APPROVED in `docs/CCAgentWorkSpace/CC/workspace/reports/2026-05-06--agenttodo_m0_mag001_compliance_review.md`; no blocking boundary violation or required amendment. |
| MAG-002 | FA | P0 | CONDITIONAL | Formal architecture review of Agent Decision Spine, object lifecycle, and persistence order. | CONDITIONAL in `docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-06--agenttodo_m0_mag002_architecture_review.md`; canonical order accepted, E1 blocked until state transitions / ownership / idempotency / persistence-before-side-effect / scanner decay / protective-close split / fail-closed healthchecks are explicit. |
| MAG-003 | PA | P0 | CONDITIONAL | Produce implementation RFC with exact module seams, structs, migrations, flags, and rollout order. | CONDITIONAL in `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-06--agenttodo_m0_mag003_implementation_rfc.md`; M1 may start only as durable event-store wave after PM reconciliation, with M2/M3 authority changes gated behind M1 Linux row proof + E2/E4 acceptance. |
| MAG-004 | PM | P0 | DONE | Reconcile OpenClaw external Gateway vs local 5-Agent runtime after operator architecture review. | 2026-05-06 overlay accepted: local 5-Agent remains independent; OpenClaw Gateway becomes communication/supervisor/proposal relay; existing console is the only GUI. |

### M0 Conditional Gate Before E1

PM reconciliation result: M0 contract-freeze direction is approved, but implementation is limited to M1 durable event store only until the following conditions are explicit in the implementation packet and reviewed by E2/E4:

1. Object state transitions, terminal states, parent IDs, and versioning for evidence, StrategistDecision, GuardianVerdict, ExecutionPlan, Decision Lease, ExecutionReport, and AnalystInsight.
2. Store ownership table: DB as durable lineage ledger, Python as reasoning-object producer through adapters, Rust as final execution enforcement, with exactly one writer/updater class per transition.
3. Durable idempotency keys and unique constraints for `decision_id`, verdict version, `order_plan_id`, lease binding, and execution submit.
4. Persistence-before-side-effect rule for every authoritative object; write failure must fail closed or degrade to non-trading shadow behavior.
5. Scanner lifecycle: `OpportunityCandidate` / `OpportunityDecay` / `PositionReview`; scanner decay cannot auto-close or directly block opens except hard H0/Guardian facts.
6. Protective close vs tactical close/reduce split: protective H0/P0/P1 reduce-only paths may bypass Strategist tactical approval only with explicit protective lineage; tactical close/reduce must pass StrategistDecision -> GuardianVerdict -> ExecutionPlan -> Decision Lease.
7. Fail-closed healthchecks for complete-chain ratio, orphan decisions/verdicts/plans, zero-row agent tables, missing AI invocation links, missing lease IDs, scanner decay without review, and duplicate submit attempts.
8. Feature-flag semantics: `advisory_enforced` means enforced advisory-only semantics, and any legacy fallback after cutover must be wrapped by the full spine or constrained to protective/reduce-only behavior.
9. OpenClaw boundary semantics: Gateway allowlist, auth profile, request ID, channel identity, and forbidden direct paths to order/live config/secrets are explicit before any endpoint is exposed.
10. GUI view-model semantics: Agent Control reads backend-authored degraded envelopes and never reconstructs the decision chain from raw tables in JavaScript.

## Milestone 1: Durable Agent Event Store

| ID | Owner | Priority | Status | Task | Acceptance |
|---|---|---:|---|---|---|
| MAG-010 | E1 | P0 | DONE (ROW PROOF SMOKE) | Add legacy/advisory bus trace writer for `agent.messages` without promoting `MessageBus` to authority. | `AgentEventStore.record_message` + `MessageBus(message_sink=...)` landed 2026-05-06 with fail-soft tests. Linux controlled row proof at `bd583edb`: `[52]` PASS with `messages=2`; no service restart or authority change. |
| MAG-011 | E1 | P0 | DONE (ROW PROOF SMOKE) | Persist `agent.state_changes` from agent start/stop/degrade/heartbeat transitions. | `BaseAgent` lifecycle + `Conductor.set_agent_state` write fail-soft state rows. Linux controlled row proof: five agent rows, `conductor`, and `conductor:*` rows present; `[52]` counted `state_changes=11`. |
| MAG-012 | E1a | P0 | DONE (LOCAL ROW PROOF; CLOUD PENDING MAG-019) | Persist `agent.ai_invocations` for local L1/L1.5/L2 and supervisor cloud escalations with model, latency, cost, prompt hash, output hash. | Strategist / Guardian / Analyst local Ollama paths write prompt hash + response hash metadata. Linux controlled row proof wrote two explicit `agenttodo_mag014_row_proof` AI rows; supervisor cloud escalation rows remain MAG-019 scope. |
| MAG-013 | E2 | P0 | DONE (FAILURE MODE OBSERVED) | Audit DB sink failure modes. | Writer default-off, fail-soft on DB/serialization errors, and `[52] agent_event_store_rows` makes enabled-but-empty tables fail-visible. Linux first smoke with wrong PG env produced no writes but did not break lifecycle/message calls; `[52]` strict failed on zero rows, then passed after valid DB env. |
| MAG-014 | E4 | P0 | DONE (LINUX ROW PROOF SMOKE) | Add Linux regression for agent schema nonzero row acceptance. | Mac/Linux targeted tests passed 215/0; strict `[52]` went FAIL before smoke (`0/0/0`) then PASS after controlled smoke (`messages=2 state_changes=11 ai_invocations=2`). |
| MAG-015 | PA | P0 | DONE | Define AgentTodo Sprint A contract addendum: local observations, OpenClaw view models, supervisor escalation packet, proposal/approval/channel schemas, endpoint allowlist, cloud budget, store ownership, and state transitions. | DONE 2026-05-06 in `2026-05-06--mag015_sprint_a_contract_addendum.md`: E1/E1a can implement without guessing contracts; local agents emit structured observations; one supervisor compresses and optionally calls cloud; proposals are persisted before GUI/mobile approval. |
| MAG-016 | E2/E3 | P0 | DONE (MAC/LINUX ROUTE CONTRACT) | Define and test OpenClaw Gateway authority lockdown. | `test_openclaw_routes.py` proves the `/api/v1/openclaw/*` Sprint A allowlist is exactly two GET routes, route paths contain no order/live/secret/config/deploy classes, source has no write SQL or forbidden proxy call markers, and OpenClaw request context missing downgrades reads to degraded posture. |
| MAG-017 | E1 | P0 | DONE (MAC/LINUX ROUTE CONTRACT) | Implement read-only `/api/v1/openclaw/status` and `/api/v1/openclaw/self-state` aggregation endpoints. | `openclaw_models.py` + `openclaw_routes.py` landed at `cbb225b7`: backend-authored envelopes include authority, gateway posture, runtime summary, event-store row proof, governance, budget, blockers, and self-state sections. PG outage returns 200 degraded; zero required rows are fail-visible; no write/proposal endpoint is enabled. Mac/Linux targeted tests 33/0 and py_compile passed; no service restart or deploy. |
| MAG-018 | E1a | P1 | DONE (MAC/LINUX STATIC CONTRACT) | Upgrade `tab-agents.html` into read-only Agent Control foundation: topology, self-state, gateway/channel posture, and degraded/error states. | `tab-agents.html` now mounts `openclaw-agent-control.js` and renders authority, gateway/channel, topology, and degraded/error panels from `/api/v1/openclaw/status` + `/api/v1/openclaw/self-state`. Static tests prove no manual controls, no write methods, no raw `agent.*` table join, required OpenClaw request headers, and exact backend allowlist consumption. Mac/Linux targeted tests 38/0, `node --check`, and py_compile passed; no service restart or deploy. |
| MAG-019 | AI-E/PM | P1 | TODO | Define and wire supervisor cloud escalation ledger policy after `agent.ai_invocations` exists. | No local agent calls cloud independently; every cloud L2 call has budget decision, prompt hash, cost, latency, response summary, and linked diagnosis/proposal IDs. |

## Milestone 2: Scanner Advisory Conversion

| ID | Owner | Priority | Status | Task | Acceptance |
|---|---|---:|---|---|---|
| MAG-020 | PA | P0 | TODO | Define scanner authority modes: `legacy_gate`, `advisory_shadow`, `advisory_enforced`. | Config semantics documented and reviewed. |
| MAG-021 | E1 | P0 | TODO | Add `OpportunityCandidate` and `OpportunityDecay` contracts. | Rust/Python serialization tests pass. |
| MAG-022 | E1 | P0 | TODO | Emit scanner decay when symbol weakens, is displaced, or exits top set. | Open position decay creates review event, not close command. |
| MAG-023 | E1 | P0 | TODO | Preserve active-position market data subscription independent of scanner ranking. | Replay proves open positions remain monitored after scanner drop. |
| MAG-024 | E1 | P0 | TODO | Convert scanner hot-path new-open gate into advisory shadow comparison behind flag. | In shadow mode, legacy gate result is recorded but does not alter spine decision. |
| MAG-025 | QC | P0 | TODO | Build replay set for scanner churn windows and wave profit/loss behavior. | Replay fixture identifies regular scanner-driven waves if present. |
| MAG-026 | E4 | P0 | TODO | Regression: scanner decay -> PositionReview, no auto close. | Test proves no close dispatch is caused solely by scanner removal. |

## Milestone 3: Agent Decision Spine Shadow

| ID | Owner | Priority | Status | Task | Acceptance |
|---|---|---:|---|---|---|
| MAG-030 | PA | P0 | TODO | Finalize `agent_spine` Rust module design. | RFC lists module files, interfaces, stores, and feature flags. |
| MAG-031 | E1 | P0 | TODO | Implement `StrategySignal` adapter for Rust strategies. | Existing strategy outputs can be persisted as signals without executing. |
| MAG-032 | E1 | P0 | TODO | Implement spine store for StrategistDecision, GuardianVerdict, ExecutionPlan, ExecutionReport. | DB chain query can join signal -> decision -> verdict -> plan. |
| MAG-033 | E1a | P0 | TODO | Add Python `agent_spine_client.py` for Strategist/Guardian/Analyst interaction. | Python agents can publish/consume typed objects without free-text routing. |
| MAG-034 | E2 | P0 | TODO | Audit idempotency and double-execution prevention. | Every execution candidate has decision_id and order_plan_id dedupe. |
| MAG-035 | E4 | P0 | TODO | Shadow integration test: legacy Rust path vs spine decisions. | Shadow produces complete chain while legacy behavior remains unchanged. |

## Milestone 4: Strategist V2

| ID | Owner | Priority | Status | Task | Acceptance |
|---|---|---:|---|---|---|
| MAG-040 | PA/QC | P0 | TODO | Define strategy matching model for MA/Grid/Funding/BB/Breakout. | Strategy choice is not `strategist_ai`/`strategist_heuristic` only. |
| MAG-041 | E1a | P0 | TODO | Implement StrategistDecision open/hold/reduce/close/no_action. | Decisions include thesis, invalidation, expected net edge, portfolio impact. |
| MAG-042 | E1a | P0 | TODO | Implement PositionReview for scanner decay and regime shifts. | Scanner decay on open position leads to hold/reduce/tighten/close recommendation. |
| MAG-043 | E1a | P1 | TODO | Consume Guardian rejection stats in next-cycle decision. | High reject rate reduces aggressiveness or raises confidence floor. |
| MAG-044 | E1a | P1 | TODO | Consume AnalystInsight and TruthRegistry in strategy weights. | Losing pattern changes future strategy preference with persisted reason. |
| MAG-045 | E4 | P0 | TODO | Replay test: Strategist decisions are not equivalent to scanner score sorting. | Test compares candidate rank vs chosen action and requires explicit reasoning. |

## Milestone 5: Guardian V2

| ID | Owner | Priority | Status | Task | Acceptance |
|---|---|---:|---|---|---|
| MAG-050 | QC | P0 | TODO | Design dynamic correlation and per-strategy drawdown metrics. | Model inputs and fallback behavior documented. |
| MAG-051 | E1 | P0 | TODO | Replace hardcoded BTC/ETH-only correlation with dynamic matrix or safe fallback. | Correlation verdict works across active symbols. |
| MAG-052 | E1 | P0 | TODO | Add P2 risk modification output to GuardianVerdict. | Guardian can modify size/leverage/stop/cooldown with reason. |
| MAG-053 | E1 | P1 | TODO | Consume Scout event alerts and scanner risk evidence in Guardian. | Event/risk alert can tighten risk without directly ordering. |
| MAG-054 | E4 | P0 | TODO | Regression: Guardian verdict is mandatory before ExecutionPlan. | ExecutionPlan cannot be created without approved/modified verdict. |

## Milestone 6: Executor Planner

| ID | Owner | Priority | Status | Task | Acceptance |
|---|---|---:|---|---|---|
| MAG-060 | PA | P1 | TODO | Define ExecutionPlan interface and allowed order styles. | Executor cannot encode symbol/direction authority. |
| MAG-061 | E1 | P1 | TODO | Implement ExecutionPlan generation. | Approved StrategistDecision becomes plan with max slippage, urgency, maker preference. |
| MAG-062 | E1 | P1 | TODO | Add Decision Lease binding to ExecutionPlan. | Every real submit carries lease id or fails closed. |
| MAG-063 | E1 | P1 | TODO | Persist ExecutionReport with quality metrics. | Analyst receives slippage/fees/fill latency. |
| MAG-064 | E4 | P1 | TODO | Regression: Executor never chooses symbol/direction. | Tests assert symbol/direction come only from approved decision. |

## Milestone 7: Analyst Learning Loop

| ID | Owner | Priority | Status | Task | Acceptance |
|---|---|---:|---|---|---|
| MAG-070 | MIT/QC | P1 | TODO | Define L1/L2/L3 AnalystInsight schemas. | Insights carry fact/inference/hypothesis labels. |
| MAG-071 | E1a | P1 | TODO | Persist AnalystInsight and link to evidence refs. | Insight can be traced to round trips and strategy metrics. |
| MAG-072 | E1a | P1 | TODO | Strategist consumes losing/winning patterns through typed rules. | Next-cycle decision changes are explainable. |
| MAG-073 | E1 | P1 | TODO | Guardian consumes risk patterns. | Risk pattern can tighten P2 without changing P0/P1. |
| MAG-074 | E4 | P1 | TODO | End-to-end test: losing pattern -> Strategist weight change -> persisted reason. | Full chain passes in Linux regression. |

## Milestone 8: Canary and Cutover

| ID | Owner | Priority | Status | Task | Acceptance |
|---|---|---:|---|---|---|
| MAG-080 | PM/PA | P0 | TODO | Define cutover policy: shadow -> canary -> primary. | Operator has exact flags, rollback steps, and thresholds. |
| MAG-081 | E3 | P0 | TODO | Runtime risk review for canary flags and rollback. | No flag can accidentally enable live autonomy without approval. |
| MAG-082 | E4 | P0 | TODO | 24h canary validation checklist. | Complete evidence chain for every canary decision. |
| MAG-083 | QA | P0 | TODO | Final release audit. | No trade reaches execution without StrategistDecision + GuardianVerdict + ExecutionPlan + Decision Lease. |
| MAG-084 | PM | P0 | TODO | Operator sign-off. | Written sign-off updates TODO/CLAUDE/MEMORY as needed. |

## Open Questions

1. Should scanner hard market invalidity be represented under H0 eligibility or Guardian risk evidence?
2. Should Agent Decision Spine be Rust-only authoritative with Python adapters, or DB-authoritative with Rust enforcement?
3. What is the minimum replay window required before scanner advisory mode can become enforced?
4. Should Strategist V2 initially control only new entries, or also existing position reviews?
5. Which UI surface should show the decision chain first: Agent Control tab is now the default; Paper Dashboard and Learning Cockpit should deep-link to it instead of duplicating the chain.
6. Which OpenClaw channels should be enabled first: Telegram only, or Telegram plus WebChat?
7. What daily/monthly cloud L2 budget should gate supervisor escalations?

## Definition of Done

The rework is done only when:

1. Agent event DB tables are populated in production runtime.
2. Scanner no longer directly decides open/close through hidden gates.
3. Every trade or rejection has a full decision chain.
4. Strategist produces real tactical decisions, not generic edge intents.
5. Guardian has mandatory, persisted veto/modification authority.
6. Executor creates execution plans and reports quality.
7. Analyst insights are consumed by Strategist/Guardian.
8. Cutover has shadow/canary evidence and rollback plan.
