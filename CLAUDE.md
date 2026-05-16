# 玄衡 · Arcane Equilibrium — Claude Operating Memory

This file is operating memory: identity, boundaries, workflow, and durable
lessons. It is not the active project ledger.

## Context Loading

Default route:

1. Read this file.
2. Read `README.md` for stable project shape and source routing.
3. Read `docs/agents/context-loading.md` for where each context class lives.
4. Read `TODO.md` for code, deploy, runtime, planning, sign-off, review, or
   unclear-continuity work.
5. Read `CONTEXT.md` and relevant `docs/adr/*` when naming domain concepts or
   touching architecture.

Current progress, runtime facts, active blockers, and schedules live in
`TODO.md`. Stable project overview lives in `README.md`. Completed detail lives
in reports/archive. Do not mirror long status paragraphs here.

## 一、Product Boundary

- Formal product: `玄衡 · Arcane Equilibrium`.
- `OpenClaw` is the control-plane / Gateway / Console / communication service
  family, not the total product name.
- Bybit is the only exchange target.
- Rust `openclaw_engine` is the trading, risk, strategy-config, and execution
  authority.
- Python/FastAPI is the control plane, GUI backend, bridge, replay surface, and
  local agent host; it must not become the trading truth layer.
- Canonical GUI: existing FastAPI OpenClaw Control Console at
  `http://trade-core:8000/console`.
- External OpenClaw Gateway is communication / mobile / supervisor /
  proposal relay only. It is not a trading conductor, not the local 5-Agent
  runtime, and not a second GUI.

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

Priority order: account survival > risk governance > system health > audit
traceability > human final review > real net PnL > autonomy evolution.

## 三、Active State Routing

`TODO.md` is the active state authority. Anything that used to live in the old
CLAUDE §三 current-state panorama must now be read from:

- `TODO.md` for active blockers, runtime facts, current phase, schedules, and
  next work.
- `docs/CCAgentWorkSpace/*/workspace/reports/` for evidence and sign-off.
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
- Paper is not an active promotion evidence lane unless a future explicit
  operator decision reopens it. Stage 1 alpha-bearing promotion is Demo-only
  after a green Stage 0R replay preflight.

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
6. Token budgets are hard guidance: 4,000 per task and 30,000 per session; when
   close, summarize/reset and disclose.
7. Surface conflicts; choose the newer or better-tested pattern and mark the
   other as cleanup debt.
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
- Files over 800 lines require review attention; 2000 lines is the hard cap
  unless a documented pre-existing exception applies.
- New mutable singletons must be registered in the singleton table's current
  authority location before merge.
- New scripts must update `helper_scripts/SCRIPT_INDEX.md`.
- New docs must follow `docs/README.md` placement and index rules.
- Legacy agent references to old CLAUDE §七 for migration, passive-wait,
  report, or git rules should use this section plus `Data, Migrations, And
  Validation`, `TODO Maintenance`, and `Git And Sync` below.

## 八、Workflow

- Main session role is PM + Conductor.
- Non-trivial work starts with triage: task type, risk, source of truth,
  acceptance criteria, and whether sub-agent dispatch is warranted.
- Feature / bug chain: `PM -> PA -> E1/E1a -> E2 -> E4 -> QA -> PM`.
- Compliance / architecture chain: `PM -> CC -> FA -> PA -> PM`.
- Quant / ML / data chain: `PM -> QC -> MIT -> AI-E -> PM`.
- Security / deploy / runtime chain: `PM -> E3 -> BB if exchange-facing -> PM`.
- E2 review and E4 regression are not skipped for implementation work unless the
  operator explicitly accepts the risk for a narrow emergency.
- Every delegated task must bind a repo role, ownership, expected output, and
  task shape.
- If a role is skipped, say which role and why.
- Bybit-facing REST/WS/IPC work must check
  `docs/references/2026-04-04--bybit_api_reference.md`; new endpoints or
  semantics update that reference. BB review should push back on exchange-side
  violations.

## 九、Code Structure Guardrails

- Files over 800 lines require review attention; 2000 lines is the hard cap
  unless a documented pre-existing exception applies.
- New mutable singletons must be registered in the current singleton authority
  before merge.
- Route handlers parse -> call -> format; business logic belongs below them.
- GUI is Vanilla JS; do not introduce React/Vue/Angular.

If an agent prompt asks for old CLAUDE §九, use this guardrail section plus
`README.md` / relevant module docs for detailed structure.

## Data, Migrations, And Validation

- For V### migrations with PG reflection, transaction control, or schema
  assumptions, do Linux PG empirical dry-run before implementation sign-off.
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
