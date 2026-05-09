# 玄衡 · Arcane Equilibrium

Arcane Equilibrium is a Rust-core, Python-bridge agentic trading governance system that runs paper / demo / live pipelines as one process against Bybit, with a multi-agent decision loop gated by formal state machines (Decision Lease, Authorization, Risk Governor, OMS Execution).

This `CONTEXT.md` is the project's domain glossary. Every architectural suggestion, ADR, refactor, or review should use these terms exactly — don't substitute "service," "component," "module" (in the generic sense), or "API" when one of these names applies. Generic programming concepts (timeout, retry, lock, queue) are deliberately omitted — only Arcane Equilibrium / OpenClaw-specific terms belong here.

## Product naming

**玄衡 · Arcane Equilibrium**:
The formal project and product name after the 2026-05-06 soft rename. "玄衡" names the whole trading governance system: autonomous cognition, risk equilibrium, auditability, and bounded execution authority.
_Avoid_: using OpenClaw Bybit as the total project name in new docs.

**OpenClaw**:
The retained service-family name for the control-plane surface: OpenClaw Control Console, OpenClaw Gateway, OpenClaw API aggregation routes, and related communication/proposal relay services.
_Avoid_: treating OpenClaw as the total project brand, Rust engine name target, or trading brain.

**Bybit**:
The sole exchange venue and the correct label for venue adapters, connector paths, API references, secrets slots, exchange endpoint behavior, and compliance notes.
_Avoid_: including Bybit in the formal product name unless discussing the venue adapter.

## Language

### Engine modes

**Paper mode**:
Fully simulated trading with synthetic fills, no exchange calls — used for strategy exploration and parameter coverage.
_Avoid_: simulation, backtest (REF-20 Replay Lab is a separate construct).

**Demo mode**:
Bybit demo endpoint trading with real API calls but Bybit play-money — primary source of truth for edge estimation.
_Avoid_: testnet (Bybit specifically calls this "demo"), sandbox.

**Live mode**:
Real Bybit Mainnet trading with real money — requires `OPENCLAW_ALLOW_MAINNET=1` plus full 5-gate authorization chain.
_Avoid_: production, real trading.

**LiveDemo**:
The Live code pipeline pointed at the Bybit demo endpoint — meets the full Live authorization standard (TTL, signing, governance gates) and is **never degraded** because the endpoint is non-mainnet.
_Avoid_: "live demo" (two words), treating it as a relaxed Live. Historical 43k DB rows tagged `engine_mode='live'` are actually LiveDemo.

**3E-ARCH**:
The three-engine architecture — paper / demo / live as one Rust binary spawning three pipelines with three independent risk-config TOML files.
_Avoid_: "multi-mode engine" (loses the "three independent configs" connotation).

**3-Config**:
The independent TOML/config ownership model for paper / demo / live. A setting
being safe in one engine mode does not imply the same value or authority in the
other two modes.
_Avoid_: "shared config" when the code path must respect per-mode authority.

### Alpha source taxonomy

**Alpha Surface Bundle**:
The proposed (ADR-0021 R-1) data-rich strategy input bundle: TA indicators + funding curve + basis curve + OI delta panel + orderflow + liquidation pulse + event alerts + sentiment panel. Replaces TickContext-only strategy interface.
_Avoid_: "context bundle" (loses alpha semantics), "feature vector" (suggests ML feature, not policy input).

**AlphaSourceTag**:
A declared dependency on a specific alpha source (TA1m, TA5m, FundingSkew, Basis, OIDeltaPanel, OrderflowImbalance, LiquidationCascade, EventDriven, CrossAsset). Every strategy must declare its alpha sources at registration; Strategy Registry rejects all-`[TA1m]` proposals without QC waiver.
_Avoid_: "feature tag" (ML-specific), "data source" (too generic).

**AlphaSourceRegistry**:
The proposed (ADR-0021 R-2) Python class tracking active / observing / deprecated / sunset alpha sources, used by Strategist Agent for inventory tracking and dynamic Sharpe-by-regime allocation.
_Avoid_: "strategy registry" (already overloaded).

**Hypothesis (governance object)**:
The proposed (ADR-0021 R-3) first-class governance object at parity with Decision Lease. Records statement / null hypothesis / evidence contract / experiment target / verdict / audit chain. Every new strategy / parameter / risk budget must have an originating Hypothesis. State machine: DRAFT → REGISTERED → EXPERIMENTING → EVIDENCE_GATE → PROMOTED / REJECTED / EXPIRED.
_Avoid_: "experiment" (loses governance weight), "test" (generic).

**Per-alpha-source Live Promotion Gate**:
The proposed (ADR-0021 R-4) replacement for "system-wide live_reserved" promotion model. LiveBudget(alpha_source_id, slice) allocates capital_cap_usd / max_concurrent_positions / max_drawdown_pct per alpha source. Each alpha source has independent promotion clock concurrent to others.
_Avoid_: "per-strategy live promotion" (alpha-source != strategy), "live budget" alone.

### Decision Lease state machine (SM-02)

**Decision Lease**:
A timed, revocable, scope-limited authorization wrapping a single trading intent. AI output never becomes an order — it becomes a Lease that must be activated, risk-approved, bridged, and consumed. Per-intent TTL 0.1–300s.
_Avoid_: lease (alone), intent token, trade ticket, signal.

**Feature flag**:
A named runtime or config switch that changes evidence collection, routing, or
behavior only inside its documented authority boundary. A feature flag is never
an operator sign-off, never a live authorization, and never a substitute for
MAG-082/083/084 evidence.
_Avoid_: treating a flag flip as a release decision.

**DRAFT**:
Lease draft formed by H5 / Strategist but not yet accepted by the Lease Control Plane; cannot bridge downstream.

**REGISTERED**:
Formally accepted as a control object but not yet in its active window — waiting on activation conditions.

**ACTIVE** (Lease):
Within effective window and may be evaluated by Risk Governor for downstream bridging; cannot self-execute or skip Risk Governor.

**BRIDGED**:
Formally handed off to the downstream governance chain (Risk Governor → Execution); does NOT mean risk approved or order placed.

**CONSUMED**:
Terminal — the bridged Lease has been fully consumed by the downstream execution lifecycle.

**REVOKED / EXPIRED / REJECTED** (Lease):
Three terminal failure states. REVOKED = formally cancelled, no revival. EXPIRED = TTL or condition timeout, no auto-extend. REJECTED = approval denied at draft.

**FROZEN** (Lease):
Temporarily frozen — cannot bridge during freeze; thaws back to a restricted state, never auto-active.

### Authorization state machine (SM-01)

**Authorization** (formal object):
A versioned, audited governance permission object stating what an Agent may do within a scope/phase/mode. Distinct from H0–H5 market judgment, Risk Governor verdicts, or Control Plane snapshots. Stored at `$OPENCLAW_SECRETS_DIR/live/authorization.json` with HMAC-SHA256 signing.
_Avoid_: permission, role, ACL.

**EarnedTrust T0/T1/T2/T3**:
The session-scope Authorization TTL ladder (24h–360h) governing how long a Live session runs before re-authorization. Complements Decision Lease (Lease = "may this single intent fire"; T0–T3 = "how long does the session live").

**Authorization states** (PENDING_APPROVAL / ACTIVE / RESTRICTED / FROZEN / REVOKED / EXPIRED / REJECTED):
RESTRICTED = scope shrunk vs ACTIVE (e.g. near-miss recovery window). REVOKED is terminal, not pause. Authorizations cannot silently auto-expand without versioned re-approval.

**GovernanceHub**:
The Python coordinator object that bundles SM-01 Authorization + SM-02 Lease + SM-04 Risk + EX-04 Reconciliation. Owns `acquire_lease()` / `release_lease()`.

**H0_GATE**:
The local <1ms deterministic kernel performing freshness / health / eligibility / risk-envelope checks before any AI layer runs. First non-bypassable gate; outputs PASS or NO; never generates ideas.
_Avoid_: prefilter, validator.

### Risk Governor state machine (SM-04)

**Risk Governor**:
The formal risk-control state machine — a versioned, auditable, replayable state object, not a config string or ad-hoc mode flag.
_Avoid_: risk module, risk engine.

**NORMAL → CAUTIOUS → REDUCED → DEFENSIVE → CIRCUIT_BREAKER**:
The five-step progressive de-risking ladder. Tightening is automatic; loosening requires explicit conditions and typically approval. CAUTIOUS = higher gates / more downsize. REDUCED = scope/symbol/strategy restriction. DEFENSIVE = reduce-only, no new risk. CIRCUIT_BREAKER = emergency stop, only protective actions allowed.

**MANUAL_REVIEW**:
Orthogonal state — system not fully halted but specific decisions blocked pending human review (used for novel anomalies, conflicting verdicts, recovery gates).

**near-miss**:
Formally recorded prior-to-incident risk signal that triggers RESTRICTED Authorization or CAUTIOUS→REDUCED escalation.

### OMS / Execution state machine (SM-03)

**Execution object**:
The in-flight process object for an action that the governance chain has allowed to proceed. Distinct from the Lease, the order fact, the fill fact, and the position fact.
_Avoid_: order, trade.

**PENDING → APPROVED → SUBMITTED → PARTIALLY_FILLED / FILLED → COMPLETED**:
Happy-path execution lifecycle. SUBMITTED ≠ filled; FILLED ≠ position closed; COMPLETED is the only formal closure.

**CANCEL_REQUESTED → CANCELLED**:
Cancellation pair — the request being sent does not equal cancellation confirmed.

**RECONCILING**:
Mandatory holding state when local execution view diverges from external truth; the system MUST enter RECONCILING rather than guess.

**FAILED / ABORTED**:
FAILED = a step failed and cannot close as success. ABORTED = governance-driven stop. Neither may auto-revert to APPROVED/SUBMITTED — a fresh Execution object is required.

### Architectural planes & seams

**Engine** (vs **Bridge**):
"Engine" = the Rust `openclaw_engine` binary owning paper / demo / live as one process. "Bridge" = the Python FastAPI Control API + GUI layer with read-only authority over engine state.
_Avoid_: calling the Python side "the engine."

**Hot path** (vs **Cold path**):
Hot path = Rust tick pipeline / IntentProcessor / governance gate (sub-ms SLA). Cold path = Python ML / learning / GUI / scheduled audits.

**Pipeline Slot**:
A late-injectable Rust component slot inside `ipc_server/slots.rs` (e.g. `HStateCacheSlot`, `CostEdgeAdvisorDbSlot`) — env-gated; coded but typically OFF.

**Control Plane / Operator Console** (EX-03):
The unified human-governance entry surface for observation, mode switching, approvals, freezes, recoveries — explicitly NOT a truth source for market/account/order/fill/position state, NOT a trading write path, NOT a strategy brain.
_Avoid_: GUI, dashboard, admin panel (these are *implementations* of the Control Plane).

**OpenClaw Control Console**:
The canonical GUI implementation of the Control Plane: the existing FastAPI console at `trade-core:8000/console`. It is the only operator trading GUI. It may show OpenClaw Gateway status and proposals, but it remains a TradeBot/FastAPI surface backed by existing auth and governance.
_Avoid_: treating the external OpenClaw dashboard as the canonical trading console.

**OpenClaw Gateway**:
External self-hosted agent gateway used for Telegram/WebChat/mobile/operator communication, multi-channel alerting, supervisor briefs, cloud escalation, and proposal/approval relay into TradeBot APIs. It is not the trading conductor, not the hot path, and not a second GUI.
_Avoid_: OpenClaw engine, OpenClaw trading brain, OpenClaw GUI.

**LG-X**:
The Live Gate foundation specification family aligned to the historical
LG-1..LG-5 gate sequence: evidence window, H0 blocking verification, provider
pricing binding, supervised-live gate, and constrained autonomous live.
Operational prerequisites such as HTTPS, credential rotation, legal/geography,
and first-day runbooks are tracked separately as OPS-X.
_Avoid_: treating LG-X as a single runtime gate.

**Gateway Agent**:
An LLM/session hosted through OpenClaw Gateway for operator interaction, brief generation, diagnosis, or proposal creation. Gateway Agents may read bounded state packets and create proposals; they may not hold Bybit credentials or call trading write APIs.
_Avoid_: confusing Gateway Agents with the local 5-Agent runtime.

**Data Plane / Perception** (EX-07):
The external-data ingestion layer that tags every inflow with source, freshness, cognitive level, and quality dimensions; un-tagged inference may not enter the decision chain.
_Avoid_: market data layer, ingestion.

**Reconciliation** (EX-04):
The independent fact-governance layer that adjudicates consistency between local process view, sync-chain fact view, and exchange truth — designed to force the system to admit "unknown" rather than self-convince.
_Avoid_: sync, reconciler.

**Venue Adapter**:
The exchange adapter shim sitting between OMS/Execution and the exchange — not authoritative for any state.

### Truth-source ownership (DOC-05)

**Source of Truth (SoT)**:
The single formal fact source for a given object class; downstream may cache/project/derive but may not claim SoT status.
_Avoid_: master record.

**Primary Writer**:
The unique module/chain authorized to write or transition the formal state of an object.

**Advisory Writer**:
A module that may propose drafts, candidates, or suggestions but cannot become a Primary Writer (e.g. H1–H5 vs Lease lifecycle, Learning Plane vs live config).

**Forbidden Writer**:
A module explicitly prohibited from writing the formal state of an object (typically: GUI, Learning, H0–H5 against fact objects).

**Human Override Path**:
The formally controlled route by which a human Operator may act on an object — must use governance objects + audit trail, never direct-edit.

**Display layer reverse contamination** (DOC-05 §3.5):
The forbidden anti-pattern of letting GUI labels / front-end state / report aggregates write back into formal state objects.

### Multi-Agent runtime (EX-06)

**Operator**:
The single human supervisor (cloud@ncyu.me). Sets only global stop-loss / take-profit, batches confirmations, drives strategy evolution; everything else is Agent autonomy within P0/P1 hard bounds.

**Conductor** (local runtime role):
The local coordination role for Scout / Strategist / Guardian / Analyst / Executor. It is NOT a sixth Agent and is NOT the external OpenClaw Gateway. It coordinates local runtime agent lifecycle and arbitration inside the TradeBot stack.
_Avoid_: OpenClaw Gateway, master agent.

**Local 5-Agent runtime**:
Scout / Strategist / Guardian / Analyst / Executor running inside TradeBot's FastAPI + Postgres + Rust-engine-adjacent stack. This is the trading cognition layer; it remains independent from external OpenClaw Gateway availability.
_Avoid_: moving these Agents into OpenClaw Gateway unless a future ADR explicitly reverses the 2026-05-06 decision.

**Agent Decision Spine**:
The typed, durable lineage chain for trade-relevant decisions:
StrategySignal -> StrategistDecision -> GuardianVerdict -> ExecutionPlan ->
Decision Lease / idempotency -> ExecutionReport -> AnalystInsight. It
supersedes free-text MessageBus traces for promotion evidence.
_Avoid_: using MessageBus rows alone as execution lineage proof.

**Scout Agent** (情報):
"Eyes and ears" — news search, event calendar, sentiment, exchange anomaly monitoring. Emits `intel_object` and `event_alert`; never produces trade signals or modifies risk parameters.

**Strategist Agent** (策略):
"Brain" — symbol selection, strategy matching, parameter optimization, portfolio allocation. Emits `trade_intent` and `portfolio_allocation`; may not bypass Guardian or H0.

**Guardian Agent** (風控):
"Safety officer" — owns P2 dynamic risk; has veto, downsize, downgrade, and circuit-breaker authority over Strategist; cannot loosen P0/P1.

**Analyst Agent** (進化):
"Evolution engine" — runs the observation/lesson/hypothesis/experiment/verdict pipeline + the L1–L5 maturity ladder. Can deploy paper experiments autonomously but cannot directly modify live config.

**Executor Agent** (執行):
The only Agent permitted to call exchange write APIs, and only when holding a valid Decision Lease; cannot generate its own intents.

**Cognitive Modulator**:
Pressure-response design pattern: under stress, Agents raise decision thresholds rather than disable capability. Virtual scarcity (energy / credits / internal currency) is explicitly rejected.
_Avoid_: throttle, rate-limiter.

**Conflict Arbitration** (EX-06 §2.3):
Formal rule that Guardian veto overrides Strategist proposals; Strategist may "appeal" via the learning pipeline but not by retry.

### Compute tiers & H-pipeline

**H0**:
Local deterministic judgment kernel — first non-bypassable gate; pure in-memory, sub-millisecond; only outputs PASS or NO; never generates ideas.

**H1–H5**:
The five-stage AI governance pipeline — Thought Gate / Budget Gate / Model Router / Governor / Cost Logger; reframed in DOC-02 V2 as Multi-Agent precursors mapped onto Strategist / Guardian / Analyst.

**L0 / L1 / L1.5 / L2** (compute tiers):
Cost-routed inference tiers. L0 = local deterministic (zero-cost, <1ms). L1 = local Ollama. L1.5 = low-cost cloud (Haiku + Perplexity). L2 = full cloud (Sonnet/Opus). Lowest-cost tier capable of the task wins; the Budget Gate (H2) approves tier BEFORE computation.

**Cognitive level** (data tag):
The mandatory `fact / inference / hypothesis` tag attached to every inflow; un-tagged inference may not enter decision chains.

**Four-layer search degradation**:
L0 cache → L1 local → L1.5 Perplexity → L2 full search; information retrieval always tries cheapest source first.

### Trading domain

**Edge**:
Expected per-trade net basis-points after fees and slippage — the system's primary survival metric.
_Avoid_: alpha, PnL (PnL is the realized aggregate, not edge).

**Cost Gate**:
Cost-versus-edge threshold blocking new fills when `cost_edge_ratio` exceeds the cap. Demo can be relaxed; Live is fail-closed.

**cost_edge_ratio**:
Ratio of AI inference cost (or holding cost) to expected trading edge — when ≥ 0.8 the system recommends closing positions.

**AI Attention Tax** (DOC-04 capability I):
Every open position consumes AI compute; the position is graded A–F by `cost_edge_ratio`, F-grade triggers auto-close review.

**Funding Arb (funding_arb)**:
A delta-neutral perpetual-funding-rate harvesting strategy; V2 is on the deprecation path due to QC math infeasibility plus Bybit demo lacking spot lending.

**Maker fill rate**:
% of fills hitting as maker (PostOnly TIF) — gate target ≥40% PASS / ≥60% fee-drop tier.

**Realized edge**:
Empirical net bps after fee per fill, aggregated over a window.

**Symbol**:
A single Bybit instrument (e.g. BTCUSDT, BUSDT) — the unit of strategy attention.

**Strategy**:
A code-defined trading rule set; current 5 = `grid_trading`, `ma_crossover`, `funding_arb`, `bb_breakout`, `bb_reversion`.

**Tick pipeline**:
The Rust hot-path pipeline (in `openclaw_engine`) fanning market ticks out to IntentProcessor, paper_state, governance, and stop_manager.

**IntentProcessor**:
Rust component converting strategy intents into orders; holds the `apply_fill` fee/slippage byte-equal logic for replay.

**StopManager**:
Rust component handling Hard / Trailing / Time stop and ATR-based dynamic position sizing.

**dust clear**:
The SOP for cleaning up sub-min-notional residual positions.

### Risk control framework (EX-01)

**P0 / P1 / P2 three-tier**:
P0 = product-family-specific hard limits (Operator-only). P1 = system-wide hard limits (Operator-only). P2 = Agent-adjustable parameters with `effective = min(P0 ?? P1, P1)`. Higher tiers always win; P2 may only tighten.

**Hard Stop / Soft Stop**:
Dual-layer adversarial stop architecture. Hard stop = absolute defense, P1-capped, never disabled. Soft stop = Agent-evaluated conditional stop, ATR + regime-adjusted.

**Stop concealment**:
Mandatory rule that stop orders are NEVER placed on the exchange order book — all stops are local tick()-triggered to defend against stop-hunting.

### Bybit-specific

**Mainnet**:
Bybit production endpoint — gated by `OPENCLAW_ALLOW_MAINNET=1`; current flow = 0 by design.

**PostOnly**:
Order TIF requiring the order to be a maker; if it would cross the book it's rejected. Drives `liquidity_role='maker'` fee accounting.

**IOC**:
Immediate-Or-Cancel TIF; produces taker fills.

**Funding rate**:
Periodic perpetual-swap payment between long and short holders — the source signal for `funding_arb`.

**Master / Sub account**:
Bybit account hierarchy; covered by the `bybit-policy-compliance` skill.

### Learning & replay

**MLDE** (ML Decision Engine):
Cold-path learning component; consumes `mlde_shadow_recommendations` filtered by `evidence_source_tier`.

**Dream Engine**:
Cold-path counterfactual / what-if exploration component — emits advisories, never commands.

**Shadow vs Live model**:
Shadow = model running in parallel for evaluation, no execution effect. Live = model whose output drives orders. Per principle #7, the two planes are isolated.

**Teacher–Student**:
The v0.4 ML/DL self-learning architecture — Teacher labels, Student trains; combined with LightGBM + Optuna + 3 DL.

**REF-20 Paper Replay Lab**:
The reality-calibrated fast-replay subsystem (Sprint A–D) for backtest evidence. Data tagged `evidence_source_tier='synthetic_replay'` is **non-training** by design.

**REF-19 Reality-Calibrated Fast Replay Governance**:
The governance boundary for replay as an experiment and evidence surface.
Replay may accelerate diagnostics and preflight evidence; it cannot directly
authorize demo/live mutation or true-live promotion.

**REF-21 Full-Chain Replay Engine**:
The full-chain replay foundation with dedicated `replay_runner`, preflight
coverage, scanner timeline, calibration overlays, and read-only advisory
surfaces. Remaining trust depends on empirical recorder history and calibration
maturity.

**evidence_source_tier**:
Column on `replay.simulated_fills` ∈ {`synthetic_replay`, `calibrated_replay`, `counterfactual_replay`} — only the latter two may feed MLDE / Dream / attribution writers.

**Learning Pipeline**:
The five-stage funnel: Observation → Lesson → Hypothesis → Experiment → Verdict.

**Strategy Incubation Pipeline**:
Idea → Design → Paper Deployment → Validation Gate → Live Promotion → Live Monitoring → Retirement. Paper deployment is autonomous; live promotion is gated.

**Validation Gate** (EX-05 §4):
The 5-criteria simultaneous gate for paper→live promotion: 4 weeks + 500 trades + positive net PnL + >30% win rate + Sharpe > 0.5.

**Cross-strategy transfer learning**:
Applying parameters / filters / regime knowledge / exit rules learned in one strategy to others; each transfer is a fresh hypothesis requiring fresh validation.

**Analyst Evolution L1–L5**:
Post-Trade Review → Pattern Discovery → Hypothesis & Experiment → Strategy Evolution → Meta-Learning; each level requires demonstrated competence at the prior one.

### Product family taxonomy (DOC-04 §3)

**Product family**:
Independent governance unit — `spot / margin / perp_linear / perp_inverse / options / other_derivatives`. Each progresses independently with its own P0 config.

**Capability Level Progression**:
`unsupported → observe_only → shadow_ready → demo_ready → live_guarded_ready → live_ready` — each promotion requires demonstrated competence.

### Reconciliation consistency states (EX-04)

**IN_SYNC / LAGGING / MISMATCH_DETECTED / STATE_UNKNOWN / MANUAL_REVIEW_REQUIRED**:
The five formal verdicts Reconciliation may emit. STATE_UNKNOWN is a valid "I don't know" outcome that must NOT be guess-resolved.

### Common governance terms

**audit_event**:
The append-only formal audit log entry — every state transition, override, and approval must emit one. Reports/GUI may not write audit results directly.

**reason_code**:
Required structured field on every governance action (mode change, lease freeze, restriction, etc.) — free text alone is insufficient.

**Lease TTL**:
Configurable expiry on every Decision Lease (0.1–300s); expiry is automatic and untouchable by GUI/Learning.

**Freshness ladder** (EX-07 §2.1):
`FRESH (<5m) / RECENT (5–30m) / STALE (30m–2h) / EXPIRED (>2h)` — STALE blocks new entries; EXPIRED forces CAUTIOUS mode.

### Operator workflow

**SSH bridge workflow**:
Pattern where the Mac Claude session is SSOT and triggers Linux runtime tasks via `ssh trade-core`; replaces synchronizing two parallel Claude sessions.

**Mac=dev / Linux=runtime split**:
Mac is read/write/RCA only; Engine + Python + Postgres run only on the Linux trade-core box. `engine: not_running` on Mac is expected.

**`restart_all.sh --rebuild`**:
The deploy command that rebuilds engine binary + PyO3 in one step (post 2026-04-14 semantics).

**18 Live blockers**:
The Operator-tracked panorama of remaining gaps before true Live trading (currently 13 unresolved; #5 Decision Lease just closed).

## Relationships

- A **Strategy** produces signals on a **Symbol**, which generate intents that flow into the Rust **IntentProcessor**.
- An intent is gated by **GovernanceHub**, which consults SM-01 **Authorization**, SM-04 **Risk Governor**, and SM-02 **Decision Lease** before the **IntentProcessor** emits an order.
- The **Decision Lease** is acquired per-intent (sub-second TTL); the **Authorization** lives at session scope (T0–T3 ladder, 24h–360h).
- The **Strategist** runs in cold-path Python and proposes parameter changes; the **Executor** is the only Agent permitted to call exchange write APIs, and only while holding a valid Lease.
- **Guardian** holds veto, downsize, and circuit-breaker authority over **Strategist**; **Strategist** may "appeal" only through the learning pipeline.
- The **Tick pipeline** (hot path, Rust) feeds prices to the **Strategy** layer; intents return via the Python **Bridge** and back into Rust via PyO3 IPC.
- A fill writes to `trading.fills` and (if cell-calibrated) to `replay.simulated_fills` for **REF-20** scoring.
- **MLDE** and **Dream Engine** consume `mlde_shadow_recommendations` filtered by `evidence_source_tier IN ('calibrated_replay','counterfactual_replay')` — they emit advisories, never commands.
- **Cost Gate** enforces `cost_edge_ratio < 0.8`; if violated, the **Cognitive Modulator** raises decision thresholds rather than disabling capability.
- **LiveDemo** uses the Live code pipeline against Bybit's demo endpoint — same Decision Lease + Authorization checks as Mainnet; only the `OPENCLAW_ALLOW_MAINNET=1` env requirement separates them.
- The **Operator** sets only the global stop-loss / take-profit envelope; Agents pick symbols, strategies, parameters, and timing within P0/P1 hard bounds.
- **18 Live blockers** are project-management gates tracked outside Decision Lease state — they are not runtime gates.
- The **Control Plane / GUI** is a **Forbidden Writer** for every fact object; it may only act on objects via the **Human Override Path** (versioned governance + audit_event).
- **Reconciliation**'s STATE_UNKNOWN verdict must enter **MANUAL_REVIEW**, not be guess-resolved.

## Flagged ambiguities

- **`engine_mode='live'` historical 43k rows are actually LiveDemo** — resolved: ML filters now use `engine_mode IN ('live','live_demo')`; new INSERTs write `'live_demo'` for the LiveDemo pipeline.
- **"Engine" can mean the Rust process OR the whole Python+Rust stack** — resolved: in this codebase, "engine" without qualification = the Rust `openclaw_engine` binary; the Python side is "Bridge" or "Control API." Note "Dream Engine" is a separate subsystem.
- **"Demo" means the engine_mode OR the Bybit endpoint** — resolved: `demo` (lowercase) = engine_mode; "Bybit demo endpoint" = the API target. **LiveDemo** always means "Live pipeline → Bybit demo endpoint."
- **Decision Lease deployment status** — Path A retrofit IMPL landed (commit `dbcf845b`). As of W-C, Linux `trade-core` runs `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1` only for shadow Agent Spine evidence collection; this does not grant true-live auth, Executor order authority, MAG-083, or MAG-084.
- **`replay.simulated_fills.evidence_source_tier='synthetic_replay'`** looks usable but is explicitly non-training data. Always filter `IN ('calibrated_replay','counterfactual_replay')` before feeding MLDE / Dream / attribution.
- **5-Agent runtime set (Scout / Strategist / Guardian / Analyst / Executor) vs 18-Agent dev role tiers (PM / FA / PA / CC / E1 / E2 …)** — different vocabularies. The 5-Agent set is a runtime trading construct (DOC-01); the 18 are dev workflow personas living under `.claude/agents/`.
- **`OPENCLAW_BASE_DIR` vs `OPENCLAW_SRV_ROOT`** — `SRV_ROOT` is a legacy alias; new code must use `OPENCLAW_BASE_DIR`. They do not fall back to each other; Mac dev must export both to the same value.
- **"Agent" overloaded** — can mean the 5 runtime trading Agents (Strategist etc.), the 18 development sub-agents (E1, FA, PM…), or a generic LLM agent. Always qualify: "Strategist Agent," "E1 sub-agent," "LLM agent." Never bare "Agent" in new prose.
- **OpenClaw Gateway vs OpenClaw Control Console** — Gateway is the external communication/session layer; Control Console is the existing FastAPI GUI. There is no second trading GUI.
- **MessageBus vs Agent Decision Spine** — MessageBus is legacy/advisory local routing; the authoritative spine is typed persisted objects plus Decision Lease and Rust enforcement.
