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
- `AE_INVENTORY_CONSOLIDATED.md` only for deep history, RCA, or old
  design decisions

## Role

Codex is a secondary engineer, reviewer, PM/conductor, and deploy operator when
requested. The default stance is PM-first: clarify success criteria, identify
source of truth, choose local work vs dispatch, and keep boundaries visible.

Operator-facing responses should be Chinese-first. The operator needs judgment,
pushback, and clear uncertainty, not blind execution.

文檔與注釋同樣中文優先：新增或修改的設計文檔、報告、實施筆記、
代碼注釋應默認使用中文；只有在 operator 明確要求英文、文件本身已
鎖定英文格式，或必須保留精確 API / protocol wording 時才使用英文。

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
- `engine_dead` incident detection is external-watchdog notify-only by design:
  when the engine is dead, in-process Rust C4 senders are unavailable. Do not
  route it through Rust `AllFail`/Defensive without a separately reviewed
  watchdog-side defensive design.
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
- Cost Gate bounded Demo probe source readiness can be reviewed, but this is
  not authority: as of 2026-06-23 the near-touch Adapter, reject-path placement
  preview wiring, and `bounded_demo_probe_operator_authorization_v1` contract
  grant no Cost Gate lowering, no active probe authority, and no order
  authority unless a future bounded operator authorization object is explicitly
  supplied and accepted by runtime admission.
- Do not fake AI calls, trading activity, lineage, fills, healthchecks, or test
  results.
- Bybit API timeout / nonzero `retCode` fails closed; no hidden trading retry
  paths.
- Alpha promotion evidence is math-primary: bull data is allowed only with
  explicit regime/freshness labels; Bybit market APIs are raw state inputs, not
  prediction; news/X/Reddit agents are secondary corroboration only.
- FlashDip touchability is not promotion evidence. The nf3% shallow-retune
  cells were blocked by adversarial death stress; K6/N2/C3/nf0.5% is only a
  counterfactual survivor-first research candidate and still requires
  QC/MIT/AI-E review before any flag-gated demo parameter change.

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
- For delegated Rust/Cargo or Linux-runtime work, attach
  `docs/agents/sub-agent-hygiene-sop.md` to the dispatch. Sub-agents do Mac
  cargo/source verification and Linux read-only probes only; Linux cargo or
  restart requires PM/operator-owned atomic deploy handling.
- Checkpoint after significant steps.
- Match codebase conventions even when you disagree; push back explicitly if
  they are harmful.
- Fail loud when tests, steps, or evidence are skipped.

## Claude Code Hooks Mirror

Hints mirrored from the Claude Code side; canonical text lives in the pointed
files, not here.

- Claude Code sessions in this repo run an rtk PreToolUse rewrite layer
  (`.claude/settings.json` + `.claude/hooks/rtk-rewrite.sh`): Bash output in
  shared transcripts/reports may be rtk-compressed. If exit != 0 but the
  summary looks green, read the `[full output:]` tee log or rerun via
  `rtk proxy <cmd>`. Canonical: `CLAUDE.md` §八 + `tools/rtk/README.md`.
- `.claude/skills` descriptions are written as trigger conditions; check for a
  matching skill before hand-rolling a procedure.

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
- Funding-cap for funding-harvest / funding-threshold strategies is the
  exchange `instruments-info.upperFundingRate` (SSOT), not the max of a
  funding/history sample window (which always sits inside one regime and
  mis-estimates the cap). 2026-05-31 lesson: a funding_short_v2 audit read the
  +0.0001 IR-baseline floor of a low-premium window as a +10.9% APR structural
  cap and wrongly called the strategy permanently DOA; Bybit real caps are
  +547~2190% APR, so funding_short_v2 is regime-dormant (fires under bull
  premium), not structurally infeasible — see
  `docs/audits/2026-05-31--p0_edge_cost_wall_investigation.md`.

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
- Operator shorthand `三端同步` means: push the intended commit to `main`, then
  pull `main` on Linux `trade-core` (`/home/ncyu/BybitOpenClaw/srv`).
- Unless the operator explicitly asks for CI, `push main` means use a
  non-CI-triggering commit subject/body (`[skip ci]`) where GitHub honors it.
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
