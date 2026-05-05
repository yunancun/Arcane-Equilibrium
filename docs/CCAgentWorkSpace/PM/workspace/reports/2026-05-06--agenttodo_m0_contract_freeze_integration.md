# AgentTodo M0 contract-freeze integration

Date: 2026-05-06
Role: PM
Status: Conditional M0 approval; M1 durable event store may start after E1 packet includes listed gates.

## Dispatch

PM dispatched:

- `CC(default)` for MAG-001 compliance review.
- `FA(default)` for MAG-002 formal architecture review.
- `PA(default)` for MAG-003 implementation RFC.

All three roles were read/report-only and did not modify production code.

## Verdicts

- MAG-001: APPROVED.
  Report: `docs/CCAgentWorkSpace/CC/workspace/reports/2026-05-06--agenttodo_m0_mag001_compliance_review.md`
- MAG-002: CONDITIONAL.
  Report: `docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-06--agenttodo_m0_mag002_architecture_review.md`
- MAG-003: CONDITIONAL.
  Report: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-06--agenttodo_m0_mag003_implementation_rfc.md`

## PM Decision

M0 direction is accepted: scanner advisory/evidence, Strategist decision ownership, Guardian non-bypassable veto/modify, Rust execution engine without hidden decision authority.

Implementation is not broadly open. Only M1 Durable Agent Event Store may start first, and only as an observability/audit wave. M2 scanner authority changes and M3 Agent Decision Spine behavior changes remain gated behind:

- MAG-014 Linux row proof for `agent.messages`, `agent.state_changes`, and `agent.ai_invocations`.
- E2 audit of DB failure behavior, prompt/secret redaction, scanner authority semantics, idempotency, and Guardian non-bypassability.
- E4 Linux regression evidence.
- PM reconciliation after FA conditional items are resolved in contracts.

## E1-Blocking Conditions

Before E1 implementation, the implementation packet must make these explicit:

1. Object state transitions and terminal states.
2. Store ownership and writer/updater authority.
3. Durable idempotency and unique submit constraints.
4. Persistence-before-side-effect semantics.
5. Scanner decay and open-position review lifecycle.
6. Protective close vs tactical close/reduce split.
7. Fail-closed healthchecks and complete-chain ratio checks.
8. Feature flag semantics for `advisory_enforced`, `shadow`, `canary`, and `primary`.

## Boundary

This integration did not rebuild, restart, deploy, write DB, alter strategy/risk config, or mutate live authorization.

Untracked `CONTEXT.md` and `docs/adr/` were observed and intentionally left untouched as unrelated WIP.
