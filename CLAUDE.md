# 玄衡 · Arcane Equilibrium — Claude Operating Memory

This file is operating memory: identity, boundaries, workflow, and durable
lessons. It is not the active project ledger.

## Context Loading

Start from the repository entry rule and compile the task-specific pack instead
of universal preload. Canonical role/pack Interface:
`.codex/agent_registry_v1.json`; router:
`docs/agents/context-loading.md`; executable compiler:
`helper_scripts/maintenance_scripts/agent_governance.py context`.

Exact user scope, acceptance, hard stops, baseline, direct Interface/callers,
and relevant prior failure are never truncated for a token target. Read
`TODO.md` when current state can affect the answer, relevant README/CONTEXT/ADR
when stable shape or architecture matters, and history only on demand.

## 一、Product Boundary

- Formal product: `玄衡 · Arcane Equilibrium`.
- `OpenClaw` is the control-plane / Gateway / Console / communication service
  family, not the total product name.
- Bybit remains the only currently active live execution exchange. Binance is
  market-data-only per ADR-0033/0040. AMD-2026-07-11-01 authorizes development
  of a production-wired IBKR `stock_etf_cash` capability across readonly,
  paper, shadow, tiny-live, and live modes, but it does **not** activate IBKR
  or authorize broker contact. Until a Rust-validated, time-bounded
  `ibkr_activation_envelope_v1` binds the exact lane/broker/environment/
  operation, build SHA, account/session fingerprints, risk/Cost Gate/Guardian/
  Decision Lease lineage, nonce, expiry, revocation, and kill-switch epoch,
  IBKR is inactive and `EXTERNAL_VERIFICATION_PENDING`. Credentials and
  sessions never auto-activate it.
- Rust `openclaw_engine` is the trading, risk, strategy-config, and execution
  authority.
- Python/FastAPI is the control plane, GUI backend, bridge, replay surface, and
  local agent host; it must not become the trading truth layer.
- Canonical GUI: existing FastAPI OpenClaw Control Console at
  `http://trade-core:8000/console`.
- The external OpenClaw Gateway, reverse proxy, and GUI/service integration were
  retired and removed on 2026-07-16. They are not an active communication or
  deployment surface. The authenticated local `/api/v1/openclaw/*` read-only
  control/monitoring routes and the local 5-Agent runtime remain.

## 二、Root Principles

These are non-negotiable project principles:

1. Single controlled write entry for orders/execution.
2. Read/write separation; research, GUI, and learning are mostly read-only.
3. AI output is not an immediate command; it must become a Decision Lease and
   pass local checks.
4. Strategies cannot bypass Guardian/risk approval.
5. Survival is above profit.
6. Uncertainty defaults to conservative behavior.
7. Learning must not rewrite live state directly.
8. Every trade must be reconstructable and explainable.
9. Local stop protection and exchange-side conditional protection both matter.
10. Separate fact, inference, and assumption.
11. Within P0/P1 boundaries, agents may choose symbol, strategy, parameter, and
    timing.
12. System behavior should evolve from evidence, not anecdotes.
13. AI calls have cost and must justify expected edge.
14. The baseline system must be operable without external paid services.
15. Multi-agent collaboration is formal; Conductor is orchestration, not a sixth
    trading agent.
16. Portfolio-level risk matters more than isolated trade attractiveness.

Ultimate objective: sustained real net PnL (long-horizon, compounding). Risk
control is loss-reduction — a component of net PnL, not its opposite. The
safeguards below are the means to that objective, ranked by the irreversibility
of the loss each prevents: account survival > risk governance > system health >
audit traceability > human final review > autonomy evolution. Account survival
ranks first among the safeguards precisely because ruin is irreversible
(unbounded negative PnL) — it maximizes long-term net PnL rather than competing
with it (root principle 5). Fail-closed hard boundaries do not loosen for any
near-term PnL argument.

## Typed Authority Matrix

Authority is a partial order by fact class, not one global winner:

- `normative_policy`: Root Principles, Hard Boundaries, accepted ADR/AMD,
  explicit operator decisions.
- `implementation_contract`: code, schema, migration, tests.
- `active_work_state`: `TODO.md` owner/blocker/next action.
- `runtime_observation`: timestamped host/environment/process/config/PG/artifact.
- `external_policy`: official broker/vendor rule with verification time.
- `claim_evidence`: hash-pinned proof/test/closure artifact.

Compare freshness or strength only within one class. Across classes, preserve
both claims and emit DRIFT/CONFLICT. Runtime can prove what happened; it cannot
decide what policy permits.

Evidence assurance is separate from authority class. `LOCAL_REPRODUCIBLE`
captures bind locally recapturable repository/command bytes;
`ORCHESTRATOR_BOUND` records bind controller-known call/task/context/role/result
facts structurally, but packet-local receipts cannot authenticate their own
execution; `PLATFORM_OR_EXTERNAL_ATTESTED` is required for runtime, external-policy/
outcome, and actual-usage authenticity. A canonical self-digest proves integrity
only, never who produced a result or whether an external fact is true.
Any Closure `PASS` also needs an out-of-band trusted-host capability to verify
the exact Context and delegated/runtime/outcome/effect digests. The standalone
CLI performs offline structure/integrity checks and cannot authenticate PASS.

## 三、Active State Routing

`TODO.md` is the active state authority. Anything that used to live in the old
CLAUDE §三 current-state panorama must now be read from:

- `TODO.md` for active blockers, runtime facts, current phase, schedules, and
  next work.
- Task closure packets and their hash-pinned evidence for current sign-off;
  `docs/CCAgentWorkSpace/*/workspace/reports/` is historical/on-demand context only.
- `docs/archive/` for completed historical detail.

If an agent prompt asks for CLAUDE §三, interpret it as: read this routing note,
then read `TODO.md` and the linked report/archive needed for the task.

## 四、Hard Boundaries

- True live requires all five gates: Python `live_reserved`, Python Operator
  role auth, `OPENCLAW_ALLOW_MAINNET=1`, valid secret slot, and signed
  unexpired `authorization.json` with matching environment.
- Signed live authorization must be written through the approved Python
  renew/approve path. Do not hand-write `authorization.json`.
- LiveDemo uses live-grade control flow against a demo endpoint. It does not
  relax authorization, TTL, risk, or audit rigor.
- Mainnet env-var fallback as the only credential source is closed.
- Bybit API timeout or nonzero `retCode` fails closed; do not add hidden retry
  paths for trading effects.
- `execution_authority` in Rust is a denylist/string constant surface, not the
  real authorization mechanism.
- ML, DreamEngine, ExecutorAgent, and StrategistAgent must not live-order or
  mutate live parameters without GovernanceHub + Decision Lease approval.
- Do not fake AI calls, trading activity, fills, lineage, healthcheck evidence,
  or test results.
- Legacy crypto Paper is not an active promotion evidence lane unless a future
  explicit operator decision reopens it. Stage 1 alpha-bearing promotion is
  Demo-only after a green Stage 0R replay preflight. The ADR-0048 IBKR
  `stock_etf_cash` lane may be developed as live-capable under
  AMD-2026-07-11-01, but it remains inactive and cannot auto-promote, contact a
  broker, or create an order/funds effect. Credentials and sessions never
  activate it; the exact Rust-validated activation envelope is mandatory.
- IBKR `margin`, `short`, `options`, `cfd`, `transfer`, and account-management
  writes remain denied. Python/FastAPI/GUI never become IBKR order/risk/
  activation authority; Guardian, Decision Lease, and the global Cost Gate
  remain mandatory and cannot be weakened.
- Every IBKR real-contact activation must originate from a Rust-owned,
  authenticated Operator activation record. Rust atomically consumes its nonce
  and enforces expiry/revocation/kill-switch epochs; the Phase 2 owner-only
  read-only seal is never activation authority. Credential custody remains
  Rust-only: no Python/FastAPI/GUI plaintext ingress, serialization, logging,
  return, or environment-variable fallback.

## Alpha Evidence Governance

- Alpha promotion evidence is math-primary. News, X, Reddit, and market-commentary
  agents may provide corroborating context only; they cannot be the main signal,
  cannot override failed quantitative gates, and cannot directly drive trading.
- Bull-market data is allowed, but every bull-heavy, rally-only, 2024-dominated,
  or stale-year-dominated result must be labeled as such. Bull-only positive
  results are `regime-bet / learning-only`, not promotion proof.
- Bybit market APIs provide raw state inputs, not prediction. Trend/regime
  labels must be computed locally from leak-free, point-in-time features.
- S4 is a global S1-Sx regime/falsification overlay. It is not a standalone
  bull-data alpha proof track.

## 五、Architecture Pointers

Stable architecture belongs outside memory:

- Overview and GUI/service entry: `README.md`
- Domain terms: `CONTEXT.md`
- Accepted decisions: `docs/adr/*`
- Architecture plans: `docs/architecture/*`
- Execution plans and specs: `docs/execution_plan/*`

If an agent prompt asks for old CLAUDE §五 architecture text, use these sources
instead of expecting long architecture prose in memory.

## 六、Runtime Reality And Startup

- Mac is the development machine.
- Linux `trade-core` is the active runtime machine.
- Real engine, DB, watchdog, rebuild, and deploy checks belong on Linux, usually
  through `ssh trade-core`.
- Mac engine not running is expected. Do not infer runtime failure from Mac-only
  engine status.
- New code must remain portable to future Apple Silicon deployment: no
  hard-coded `/home/ncyu`, `/Users/ncyu`, or machine-specific TradeBot paths in
  production code.

## Operating Style

Unless the operator explicitly overrides this:

1. Think before coding: state assumptions, ask on uncertainty, list plausible
   interpretations when ambiguous, and push back when there is a simpler path.
2. Simplicity first: least code, no speculative implementation, no extra
   features, no one-off abstraction.
3. Surgical changes: only necessary edits, no opportunistic adjacent cleanup,
   and strict local style matching.
4. Goal-driven execution: define acceptance criteria, then iterate until
   verified.
5. Use model judgment only for judgment work; deterministic routing, retries,
   and data transforms belong in code.
6. Context and token budgets use the Registry's elastic target + quality reserve
   + review point. Overrun triggers scoped split/escalation, never deletion of
   mandatory evidence. Optimize cost per durable accepted closure, not raw
   tokens; Full Audit may use a larger justified reserve.
7. Within one authority class, surface conflicts and choose the newer or
   better-tested pattern; mark the other as cleanup debt. Across authority
   classes, preserve both and emit DRIFT/CONFLICT under the Typed Authority
   Matrix above.
8. Read before writing: exports, direct callers, shared helpers.
9. Tests verify intent, not only behavior.
10. Checkpoint after significant steps with done, verified, and remaining work.
11. Codebase conventions outrank personal preference unless they are materially
    harmful; then say so explicitly.
12. Fail loud: skipped steps or tests must be disclosed.

## 七、Code And Docs Rules

- Prefer existing project patterns and helpers over new abstractions.
- Route handlers parse -> call -> format; business logic belongs below them.
- New standalone trading/risk/config logic should be Rust-first unless the local
  design clearly says otherwise.
- GUI is Vanilla JS; do not introduce React/Vue/Angular.
- GUI write surfaces must write through Rust authority, not Python fake-success
  paths.
- LLM business logic must go through `LocalLLMClient`-style abstraction; do not
  leak provider-specific HTTP calls into business code.
- New or modified comments default to Chinese. Existing bilingual blocks are not
  cleaned unless touched; touched bilingual comment blocks should keep Chinese.
- The repository uses one file-size threshold: files at or below 2000 lines
  must not be blocked or forced to split solely because of size; files over
  2000 lines require review unless a documented pre-existing exception
  applies. Current documented pre-existing exceptions are registered in
  `docs/references/2000_line_exception_registry.md`; splitting hot-path/
  execution-entry files there is E5-plan work, not a convention violation.
- New mutable singletons must be registered in the singleton table's current
  authority location before merge.
- New scripts must update `helper_scripts/SCRIPT_INDEX.md`.
- New docs must follow `docs/README.md` placement and index rules.
- Legacy agent references to old CLAUDE §七 for migration, passive-wait,
  report, or git rules should use this section plus `Data, Migrations, And
  Validation`, `TODO Maintenance`, and `Git And Sync` below.

## 八、Workflow

- Main session role is PM/Conductor. The canonical workflow Interface is
  `.codex/agent_registry_v1.json`; executable routing/context/closure lives in
  `helper_scripts/maintenance_scripts/agent_governance.py`; design detail is
  `docs/agents/development-agent-governance.md`.
- Non-trivial work begins with exact objective/scope/acceptance/hard stops,
  task surfaces, risk/uncertainty, evidence scope, head/dirty scope, and allowed
  effects. Any prior or evidence digest used to decide a claim is admitted under
  task-contract `claim_inputs`; free prompt text cannot silently replace it.
- `uncertainty` is required (`low|medium|high|unknown`); omission fails before
  routing. Dispatch binds exact native agent, node class, and permission before
  spawn, including PA/E4 writer-versus-verifier identities.
- Dispatch is a hybrid risk-DAG. Source Implementation has independent E2 then
  E4 hard edges. Authority/security, runtime/OPS, correct BB/IB venue Adapter,
  quant/ML semantics, and end-to-end QA are added when task facts trigger them.
  Other roles are advisory and admitted by expected decision gain after
  preserving quality reserve.
- Read-only reviewers do not modify source, append memory/report, perform
  runtime mutation, or invoke private broker effects. Their Bash calls use the
  Registry command allowlist.
- OPS performs preflight/rollback/postcheck/RCA only. The Deploy Adapter can
  validate an exact PM/operator-approved intent and environment contract.
  `runtime_environment_probe_v1` now exists as a local-only, non-secret,
  fail-closed source capability, and the Adapter independently reruns and
  reconciles it. The probe is not remote transport, platform-attested runtime
  evidence, deploy readiness, or effect authority. Generic deploy apply remains
  disabled before component invocation until exact rollback binding and a
  stable observation-window contract are separately bound and verified; the
  generic Adapter cannot currently support a successful effect closure. The
  separately registered `p0b_alr_rollforward_adapter_v1` is narrowly limited to
  independently admitted ALR stage/cutover phases: exact dynamic HEAD/origin,
  materialized Context, PA/E3/OPS, phase-runtime bindings, uninterrupted stage,
  provisional cutover and observer-v2 PASS are mandatory for the final effect
  receipt; closure PASS then requires a later independent postcheck bound to it.
  It cannot contact a broker, create an order, or widen live authority. BB and IB review
  venue policy only. Development-agent broker contact/private effects have no
  closure-admissible Adapter and therefore route to an unsupported-effect blocker.
- Completion uses one `closure_packet_v1`; work status, gate verdict, and
  disposition are separate. Immutable dissent and unverified scope are
  preserved. Each fragment is bound to a canonical workflow call record; each
  wave retains the full call manifest, retries/nulls, planned lower bounds,
  coverage debt, DAG predecessors/topological wave, producer generation, exact
  native identity/permission, and explicit controller-overhead boundary. Per-role automatic
  report/memory growth is retired. Any orchestrator structural ledger must
  exact-cover all captured waves; ghost/omitted/extra/duplicate wave identity is
  invalid.
- Evidence class must match the claim: repository/command capture can prove
  source/test facts, not runtime or E2E; unit tests are not business outcomes.
  Repository mutation needs exact before/after `repository_change_record_v1`;
  `EXECUTED`/`REUSED` checks need a closure-trusted-replayable
  Context-bound `command_capture_v2`. Its one Adapter call is replayed before
  strong PASS when no host verifier exists, and `repository_policy_only` is not
  no-contact attestation. Repository authority value must equal its exact pinned
  Context-byte identity projection; interpreted claims use typed `claim_inputs`
  or validated evidence. Actual usage needs
  platform/external-attested telemetry; wave accounting remains a planned/
  structural lower bound.
- Multiple admitted writers each produce exactly one node-owned change record in
  canonical writer order; scopes are non-empty/disjoint and every scoped
  after-generation must remain current.
- Post-closure durability uses `closure_quality_followup_v1`; realized metrics are
  measured only from caller-trusted platform/external attestation, never zero-filled.
- Desktop local-agent background waves: a session pause (idle 900s) kills all
  in-flight background subagents, unrecoverable. After dispatching, stay
  in-turn (blocking `TaskOutput` or foreground-parallel Agent calls). The only
  reliable liveness signal is the agent transcript mtime under the session's
  `subagents/` dir; stat it before any TaskStop and suspect death only after
  ≥30 min of silence. Clear zombie `running` tasks after session resume.
  Canonical SOP: `docs/agents/sub-agent-hygiene-sop.md` and
  `.codex/SUBAGENT_EXECUTION_RULES.md`.
- Token hygiene and hooks: `.claude/settings.json` wires a PreToolUse hook
  (`.claude/hooks/rtk-rewrite.sh`) that rewrites Bash commands to `rtk`
  equivalents for compressed output. It fails open (missing rtk/jq or rewrite
  failure = silent passthrough) and never bypasses the permission model. If
  exit != 0 but the compressed summary looks green, read the `[full output:]`
  tee log or rerun via `rtk proxy <cmd>`; escape hatches are `rtk proxy <cmd>`
  and the rtk config `exclude_commands`. Binary install is pinned per
  `tools/rtk/README.md`. A SessionStart hook (`session-start.sh`) injects a
  ≤300-token workflow router and re-injects it after compact. Sub-agent
  fragments follow the closure schema; budget/retry failure never means PASS.
- Every delegated task binds role preset, runtime type, ownership, output,
  task facts, context digest, acceptance, and hard stops. Skips record reason,
  residual risk, and owner.
- Bybit-facing REST/WS/IPC work must check
  `docs/references/2026-04-04--bybit_api_reference.md`; new endpoints or
  semantics update that reference. BB review should push back on exchange-side
  violations.
- IBKR/TWS/stock_etf_cash work uses IB and ADR-0048; BB cannot substitute.

## 九、Code Structure Guardrails

- The repository uses one file-size threshold: files at or below 2000 lines
  must not be blocked or forced to split solely because of size; files over
  2000 lines require review unless a documented pre-existing exception
  applies. Registry: `docs/references/2000_line_exception_registry.md`.
- New mutable singletons must be registered in the current singleton authority
  before merge.
- Route handlers parse -> call -> format; business logic belongs below them.
- GUI is Vanilla JS; do not introduce React/Vue/Angular.

If an agent prompt asks for old CLAUDE §九, use this guardrail section plus
`README.md` / relevant module docs for detailed structure.

## Data, Migrations, And Validation

- For V### migrations with PG reflection, transaction control, or schema
  assumptions, Linux PG empirical evidence is still required before runtime
  sign-off, but delegated development roles cannot obtain it with direct `psql`.
  Use a separately authorized read-only-identity Adapter/operator artifact and
  preserve its platform-attested capture; otherwise keep the claim UNVERIFIED.
- `CREATE TABLE IF NOT EXISTS` needs Guard A; type-sensitive `ADD COLUMN` needs
  Guard B; hot-path indexes should use Guard C where applicable.
- Migration idempotency must be tested by applying twice when relevant.
- Before sign-off, first decide whether replay/counterfactual replay can check
  the claim. Run it when applicable and safe; otherwise state why runtime, DB,
  WS, or healthcheck evidence is required.
- GUI JS changes require `node --check` or a stronger equivalent before
  sign-off.
- Any passive wait in `TODO.md` must have a healthcheck, review date, named
  external action, or explicit reason automation is impossible.
- Direct `psql` is denied by the governance preflight until a local-socket/
  read-only-identity Adapter eliminates ambient `psqlrc` and `PG*` routing.
  Mac mocked tests cannot establish PG runtime semantics.

## 十、Next Work And TODO Maintenance

`TODO.md` is the active dispatch queue. Agents editing it must read
`docs/agents/todo-maintenance.md` first.

Rules:

- Active blockers and next actions stay visible.
- Runtime numbers need timestamped evidence or linked reports.
- DONE detail should be archived once it stops helping immediate handoff.
- Reports are linked, not pasted.
- Do not store stable architecture or agent personality in TODO.

## Git And Sync

- You may be in a dirty multi-session worktree. Never revert changes you did not
  make.
- Meta-doc changes in dirty trees should use narrow staging / `git commit --only
  <files>` when committing.
- Every commit should have subject and body; doc-only or governance-only commits
  should include `[skip ci]` when appropriate.
- Commit each coherent green checkpoint instead of accumulating unrelated
  batches.
- Push reports must include branch, commit SHA, and a short description.
- Do not use destructive git commands unless explicitly requested and approved.

## 十一、External Tools

- Git in `srv/` is the source of truth for code, governance docs, runtime
  policy, and TODO state.
- GitHub Issues is the active issue tracker.
- Linear is historical/passive unless explicitly reopened.
- Notion is frozen; Drive is passive; Coupler, MotherDuck, and Slack are
  declined unless explicitly reopened.
- Never publish secrets, API keys, authorization tokens, or sensitive runtime
  state to external tools.

## Pointers

- Context loading: `docs/agents/context-loading.md`
- Role profile/memory standard: `docs/agents/role-profile-memory-standard.md`
- TODO standard: `docs/agents/todo-maintenance.md`
- Domain vocabulary: `CONTEXT.md`, `docs/agents/domain.md`
- ADRs: `docs/adr/`
- Script index: `helper_scripts/SCRIPT_INDEX.md`
- Active queue: `TODO.md`
