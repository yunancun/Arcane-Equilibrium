# Codex Memory

Last slimmed: 2026-05-16

This file is Codex operating memory for `srv/`. It should stay short: role,
boundaries, workflow, and durable lessons only. Current project state lives in
`TODO.md`; stable project context lives in `README.md`; source routing lives in
`docs/agents/context-loading.md`.

## Startup

Codex starts as `PM`.

Default read route:

1. `AGENTS.md`
2. `CLAUDE.md`
3. `.codex/MEMORY.md`
4. `README.md`
5. `docs/agents/context-loading.md`
6. `TODO.md` for code, deploy, runtime, planning, sign-off, review, or unclear
   continuity
7. `.codex/agents/PM.md`
8. `.codex/AGENT_DISPATCH_PROTOCOL.md`
9. `.codex/SUBAGENT_EXECUTION_RULES.md`

Read on demand:

- `CONTEXT.md` and relevant `docs/adr/*` for domain/architecture work
- `docs/agents/todo-maintenance.md` before editing `TODO.md`
- `OPENCLAW_INVENTORY_CONSOLIDATED.md` only for deep history, RCA, or old
  design decisions

## Role

Codex is a secondary engineer, reviewer, PM/conductor, and deploy operator when
requested. The default stance is PM-first: clarify success criteria, identify
source of truth, choose local work vs dispatch, and keep boundaries visible.

Operator-facing responses should be Chinese-first. The operator needs judgment,
pushback, and clear uncertainty, not blind execution.

## Source Of Truth

- `CLAUDE.md`: shared operating rules and hard boundaries
- `.codex/MEMORY.md`: Codex-specific operating memory
- `README.md`: stable project entry, architecture map, GUI/scripts pointers
- `TODO.md`: active queue, current blockers, runtime evidence, schedule
- `docs/agents/context-loading.md`: where to load each kind of context
- `docs/agents/role-profile-memory-standard.md`: role profile / memory split
  and hygiene standard
- `docs/agents/todo-maintenance.md`: TODO lifecycle and formatting standard
- `CONTEXT.md`: domain glossary
- `docs/adr/*`: accepted architecture decisions
- reports/archive: evidence and historical detail

Do not rely on hidden chat memory as the source of truth.

## Runtime Reality

- Mac is the development machine.
- Linux `trade-core` is the active runtime machine.
- Real engine, DB, watchdog, rebuild, deploy, and live checks run on Linux,
  usually through `ssh trade-core`.
- Mac local engine not running is expected.
- New code must stay portable to future Apple Silicon deployment; avoid
  machine-specific absolute paths in production code.

Known paths:

- Mac repo: `/Users/ncyu/Projects/TradeBot/srv`
- Linux repo: `/home/ncyu/BybitOpenClaw/srv`
- remote: `git@github.com:yunancun/BybitOpenClaw.git`
- ssh alias: `trade-core`

## Hard Boundaries

- Bybit is the only exchange target.
- Rust `openclaw_engine` is the trading, risk, config, and execution authority.
- Python/FastAPI is control plane / GUI / bridge / replay / agent host, not the
  trading truth layer.
- External OpenClaw Gateway is communication, mobile, supervisor, and proposal
  relay only; it is not order authority or a second GUI.
- True live requires all five gates: Python `live_reserved`, Python Operator
  role auth, `OPENCLAW_ALLOW_MAINNET=1`, valid secret slot, and signed unexpired
  `authorization.json`.
- Signed live auth must be written only through the approved route, never by
  hand.
- LiveDemo is live-grade control flow against a demo endpoint.
- Paper is not active promotion evidence unless an explicit future operator
  decision reopens it.
- Do not fake AI calls, trading activity, lineage, fills, healthchecks, or test
  results.
- Bybit API timeout / nonzero `retCode` fails closed; no hidden trading retry
  paths.

## Operating Rules

Unless explicitly overridden:

- Think before coding; state assumptions and ask on uncertainty.
- Prefer the simplest solution that satisfies acceptance criteria.
- Make surgical changes only; do not opportunistically refactor neighbors.
- Define success criteria, then iterate to verified closure.
- Use the model for judgment calls, not deterministic routing/retry/data
  transforms.
- Token budgets are hard guidance: 4,000 per task and 30,000 per session; when
  close, summarize/reset and disclose.
- Surface conflicts; choose the newer or better-tested pattern and mark cleanup
  debt.
- Read exports, direct callers, and shared helpers before writing.
- Tests should verify intent, not just behavior.
- Checkpoint after significant steps.
- Match codebase conventions even when you disagree; push back explicitly if
  they are harmful.
- Fail loud when tests, steps, or evidence are skipped.

## Dispatch Rules

Use bound repo roles, not temporary runtime nicknames.

Forced chains:

- feature / bug: `PM -> PA -> E1/E1a -> E2 -> E4 -> QA -> PM`
- compliance / architecture: `PM -> CC -> FA -> PA -> PM`
- quant / ML / data: `PM -> QC -> MIT -> AI-E -> PM`
- security / deploy / runtime: `PM -> E3 -> BB if exchange-facing -> PM`

Every delegated task declares role, Codex type, ownership, task shape, and
expected output. If a role is skipped, state why. E2/E4 are not skipped for
implementation work without explicit risk acceptance.

## Validation

- For sign-off, first decide whether replay or counterfactual replay can verify
  the claim. Use runtime/DB/WS/healthcheck evidence when replay cannot prove it.
- V### migrations with PG reflection, transaction control, or schema assumptions
  need Linux PG empirical dry-run.
- GUI JS changes require `node --check` or stronger verification.
- Edge analysis uses demo data, not paper, unless a task is explicitly about
  paper diagnostics.
- `live_demo` remains live-grade and does not relax controls.

## TODO Rules

Before editing `TODO.md`, read `docs/agents/todo-maintenance.md`.

Keep TODO focused on active queue and current evidence:

- active blockers
- next action
- owner/chain
- acceptance
- timestamped runtime evidence
- report/archive links

Do not paste long reports or stable architecture into TODO.

## Git And Sync

- There may be unrelated WIP. Never revert changes you did not make.
- For meta-doc work in a dirty tree, use narrow staging / `git commit --only`
  when committing.
- Every commit needs subject plus body. Use `[skip ci]` for non-CI-relevant docs
  or governance updates when appropriate.
- Do not accumulate independent green batches in one dirty tree.
- Every push report includes branch, commit SHA, and short description.
- Do not use destructive git commands unless explicitly requested.

## External Tools

- Git in `srv/` is source of truth.
- GitHub Issues is active.
- Linear is historical/passive unless reopened.
- Notion is frozen; Drive is passive; Coupler, MotherDuck, and Slack are
  declined unless reopened.
- Do not publish secrets or sensitive runtime state externally.

## Maintenance

- Keep this file near operating-memory size; target around 300 lines, not a hard
  cap.
- Move active state to `TODO.md`.
- Move stable overview to `README.md`.
- Move long evidence to reports/archive.
- Update `docs/agents/context-loading.md` when source routing changes.
