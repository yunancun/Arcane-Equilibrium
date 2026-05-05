# MAG-001 Compliance Review — AgentTodo M0

Date: 2026-05-06
Role: CC(default)
Scope owner: `docs/architecture/multi_agent_rework_2026-05-05/ENGINEERING_PLAN.md` and `docs/architecture/multi_agent_rework_2026-05-05/AgentTodo.md`
Repo root: `/Users/ncyu/Projects/TradeBot/srv`
Observed HEAD: `6b667daf` (`main...origin/main`, clean at audit start)

## Verdict

APPROVED

MAG-001 is accepted for M0 contract-freeze progression. I found no boundary violation requiring amendment before MAG-002/FA and MAG-003/PA proceed.

Scope note: the user task cited PM docs-sync commit `41ec03e9`; the local repo was already at `6b667daf`, two commits ahead on the same `main` line. The worktree was clean; the three WIP files named in the task did not appear dirty during this audit. CC completion-sequence writes to `docs/CCAgentWorkSpace/CC/memory.md` and `docs/CCAgentWorkSpace/Operator/` were intentionally skipped because this task explicitly allowed writes only under `docs/CCAgentWorkSpace/CC/workspace/reports/`.

## Required Reads Completed

- Root / operating rules: `AGENTS.md`, `CLAUDE.md`, `TODO.md`, `.codex/MEMORY.md`, `.codex/AGENT_DISPATCH_PROTOCOL.md`, `.codex/SUBAGENT_EXECUTION_RULES.md`
- CC role sources: `.codex/agents/CC.md`, `.claude/agents/CC.md`, `docs/CCAgentWorkSpace/CC/profile.md`, `docs/CCAgentWorkSpace/CC/memory.md`, latest CC report
- Target docs: `ENGINEERING_PLAN.md`, `AgentTodo.md`
- Governance docs: `EX-06`, `DOC-04`, `DOC-01`, `DOC-02`, `EX-01`, `EX-07`, `SM-02`, and `AMD-2026-05-02-01`

## Findings

Blocking findings: none.

LOW-1 — Phase 8 legacy fallback wording needs carry-forward precision, but is not a MAG-001 blocker.

Source: `ENGINEERING_PLAN.md` lines 728-735 say cutover will keep an emergency fallback to the legacy Rust path, while also requiring no trade to execute without StrategistDecision, GuardianVerdict, ExecutionPlan, and Decision Lease. This is acceptable because the global invariants already state Rust is the execution engine, not hidden decision authority, and every trade must pass the spine. MAG-003 should preserve that interpretation explicitly: fallback may be shadow, reduce-only/protective, or wrapped by the same decision chain; it must not reopen a raw Rust autonomous open path.

LOW-2 — `advisory_enforced` flag name should be defined carefully in MAG-020.

Source: `ENGINEERING_PLAN.md` lines 593-616 and 771-781 clearly demote scanner authority: scanner market gate/route mode becomes evidence, open positions stay subscribed, and new opens are blocked only by H0/P0/P1/Guardian. The flag value `advisory_enforced` is therefore acceptable only if it means "enforce advisory-only semantics", not "enforce scanner advice as a gate."

## Compliance Basis

Root principles:

- Single write entry and read/write separation are preserved: DOC-01 lines 196-200 require trading writes to stay behind a controlled execution entry, while research/learning/GUI remain read or advisory.
- AI output is not an immediate command: DOC-01 lines 202-204 and DOC-04 lines 55-67 require H0/governance/Decision Lease/execution gate; the plan repeats this as a non-negotiable invariant at `ENGINEERING_PLAN.md` lines 34-41.
- Strategy cannot bypass risk: DOC-01 lines 206-208 and EX-06 lines 184-203 give Guardian veto/modify/reduce/degrade/circuit authority; the plan preserves this at lines 34-37, 123-128, and 251-264.
- Agent autonomy is preserved within hard boundaries: DOC-01 lines 237-239 and DOC-04 lines 301-310 give tactical autonomy over instrument, strategy, sizing, timing, and exits within P0/P1; the plan assigns open/hold/reduce/close/no_action to Strategist at lines 217-249 and 396-423.
- Auditability and cognitive honesty are covered: DOC-01 lines 222-232 require traceability and fact/inference/hypothesis distinction; the plan requires durable rows, evidence refs, and analyst labels at lines 525-555 and 509-523.

EX-06 / DOC-04 authority boundaries:

- Scout/scanner remains evidence only. EX-06 lines 113-119 say Scout does not produce trading signals or call exchange APIs; the plan makes Scanner Adapter recommend/review only and forbids direct close/open eligibility except true H0-style facts at lines 174-194.
- Strategist owns trading decisions. EX-06 lines 134-153 define Strategist as responsible for instrument, strategy, parameters, allocation, and trade intent. The plan maps this to `StrategistDecision` and `PositionReview` at lines 217-249 and 396-447.
- Guardian is mandatory and higher priority. EX-06 lines 184-203 and 313-326 make Guardian override final; EX-01 lines 29-55 define Guardian/P0/P1/P2 priority. The plan requires GuardianVerdict before ExecutionPlan at lines 123-128, 448-470, 663-680, and AgentTodo MAG-054 line 193.
- Executor cannot choose symbol/direction. EX-06 lines 256-283 and DOC-04 lines 330-344 restrict Executor to execution on approved/leased decisions. The plan preserves this at lines 266-288, 682-700, and AgentTodo MAG-064 line 203.

Decision Lease / H0 / P0/P1 ordering:

- H0 remains independent and non-bypassable. DOC-02 lines 39-56 define H0 as pure local first gate that can only reject or pass; EX-06 lines 39-45 and 359-369 preserve H0 as independent. The plan repeats this at lines 34 and 801-805.
- P0/P1 remain outside agent discretion. EX-01 lines 36-55 define P0/P1 as Operator-only hard limits and P2 as Guardian-tightening only; the plan states this at lines 35-36, 255-256, and 465-470.
- Decision Lease remains a control object, not an order. SM-02 lines 20-39 and 103-118 state Lease is not an order and ACTIVE cannot equal execution. The plan requires Decision Lease plus execution gate before Rust execution at lines 127-129 and line 735.
- SM-02 audit/persistence is acknowledged. SM-02 lines 430-438 forbid silent state changes and GUI/Learning direct state mutation; AMD-2026-05-02-01 lines 44-63 requires Rust lease facade/router gate and bundled agent schema writers. The plan covers current-cycle row requirements at lines 536-555 and Phase 1 gate lines 576-591.

Scanner advisory conversion:

- Current risk is correctly identified: Rust scanner currently acts above intended authority at `ENGINEERING_PLAN.md` lines 58-69.
- Target state is compliant: scanner becomes Scout/Strategist evidence, route mode is evidence not authority, decay is not close command, and scanner removal creates PositionReview rather than execution action (`ENGINEERING_PLAN.md` lines 174-194, 345-377, 593-616, 771-781).
- AgentTodo implements this as tasks MAG-020 to MAG-026, especially MAG-024 shadow comparison and MAG-026 no-close regression (`AgentTodo.md` lines 151-161).

## Explicit Amendments Required

None for MAG-001.

Carry-forward constraints for MAG-002/MAG-003:

1. H0 may reject or pass only; it must not generate trading ideas.
2. Scanner hard invalidity may be H0 eligibility evidence or Guardian risk evidence only when it is a hard fact such as delisted, suspended, missing instrument metadata, impossible order constraints, or equivalent.
3. Scanner ranking absence, route mode, churn, or decay must not directly block opens or close positions.
4. StrategistDecision must be the only source of open/hold/reduce/close/no_action tactical decision authority.
5. GuardianVerdict must be mandatory before ExecutionPlan and must retain reject/modify/circuit authority.
6. Executor must not choose symbol, direction, or thesis; it may only choose execution style for an approved decision.
7. Every real submit must carry a valid Decision Lease id or fail closed.
8. Rust may remain the low-latency execution engine, but any fallback path after cutover must still satisfy the full decision chain or be constrained to protective/reduce-only behavior.

## MAG-001 Acceptance Statement

MAG-001 is APPROVED. The M0 plan is compliant with root principles, EX-06, DOC-04, SM-02 Decision Lease, and H0/P0/P1 boundaries as a contract-freeze input. No required amendments block FA/PA from proceeding to MAG-002 and MAG-003.
