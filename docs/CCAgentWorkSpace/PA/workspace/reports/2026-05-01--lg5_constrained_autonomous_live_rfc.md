# LG-5 Constrained Autonomous Live RFC

Date: 2026-05-01
Owner: PA
Status: RFC complete

## Objective

LG-5 defines the constrained autonomous live boundary after LG-4 supervised
live is proven. It does not grant live authority by itself. It specifies the
autonomy envelope, escalation triggers, lease TTL rules, and audit obligations
required before an agent can propose or execute bounded live actions.

## Prerequisites

- LG-2 H0 blocking verification is active and fail-closed.
- LG-3 provider pricing binding is active and fresh.
- LG-4 supervised live gate is implemented and has passed supervised sessions.
- Operator role auth, `live_reserved`, signed authorization, GovernanceHub, and
  Decision Lease remain mandatory.
- P0-3 edge decision has explicitly selected a live-forward path.

## Autonomy Envelope

Autonomous live is scoped by all of the following at once:

- explicit symbol allowlist,
- explicit strategy allowlist,
- max notional per position,
- max daily realized loss,
- max orders per session,
- max autonomous session duration,
- max lease TTL,
- max consecutive losses before revoke,
- required healthcheck state at action time.

Effective permission is the minimum of:

```text
P1 hard ceiling
LG-4 supervised session limit
LG-5 autonomy envelope
strategy/risk config
current Decision Lease
```

Any missing field is deny-by-default.

## State Machine

```text
operator_seeded_candidate
  -> autonomy_envelope_review
  -> signed_autonomy_authorization
  -> lease_limited_autonomous_session
  -> action_proposal
  -> local_risk_recheck
  -> lease_bound_execution
  -> outcome_attribution
  -> continue_or_revoke
```

The session returns to `operator_seeded_candidate` after expiry, kill switch, or
any hard-boundary breach.

## Escalation Triggers

The autonomous session must stop and escalate to operator review when any of
these occurs:

- healthcheck SUMMARY FAIL,
- `[33]`, `[38]`, or `[40]` crosses configured live-readiness floor,
- provider pricing table stale beyond LG-3 freshness limit,
- signed authorization expires or env no longer matches,
- Decision Lease acquisition fails,
- order rejection is ambiguous or exchange retCode is nonzero,
- consecutive loss count reaches session limit,
- AI output conflicts with local H0/H1 risk verdict,
- audit write fails.

Escalation means no new live orders; existing risk-close and reconciliation
paths remain allowed.

## Lease TTL Rules

- Every autonomous action requires a fresh Decision Lease.
- Lease TTL must be shorter than the session TTL.
- Lease TTL is strategy-class specific and operator-configured.
- Expired leases cannot be renewed by the agent; renewal requires passing the
  same local risk and envelope checks again.
- Lease payload must include symbol, strategy, side, max qty/notional, reason,
  and source evidence ids.

## Agent Boundary

Agents may:

- propose live actions inside the envelope,
- request a Decision Lease,
- explain evidence and expected risk,
- stop themselves and escalate.

Agents may not:

- widen their own envelope,
- change live risk or strategy TOML,
- bypass GovernanceHub,
- renew signed live authorization,
- retry Bybit timeouts or nonzero retCodes,
- convert `live_demo` evidence into live permission without LG-4/LG-5 gates.

## Audit Requirements

Every autonomous live decision must be reconstructable from:

- autonomy session id,
- authorization id,
- Decision Lease id,
- agent proposal id,
- local risk verdict id,
- order id / exchange response id,
- post-trade attribution id,
- escalation or continuation decision.

Audit loss is fail-closed.

## Acceptance Tests

- Missing autonomy envelope denies.
- Envelope widening attempt denies.
- Expired session denies.
- Expired lease denies.
- Missing healthcheck PASS/WARN policy denies.
- Stale provider pricing denies.
- Exchange retCode nonzero denies without retry.
- Kill switch revokes active autonomous session.
- Agent proposal cannot write live config.
- Audit join reconstructs proposal -> lease -> execution -> attribution.

## Rollback

- Revoke autonomous session.
- Revoke outstanding Decision Leases.
- Clear session-scoped envelope state.
- Keep LG-4 supervised live machinery intact.
- No permanent risk/strategy config rollback should be needed because LG-5 does
  not write permanent config.

## Root-Principle Check

- #1 single write entry: preserved through GovernanceHub and execution adapter.
- #2 read/write separation: learning and GUI cannot write live state.
- #3 AI output is not command: Decision Lease remains mandatory.
- #4 strategy cannot bypass risk: local risk recheck precedes every lease.
- #5 survival over profit: escalation and deny-by-default dominate.
- #8 explainability: audit join is an acceptance requirement.
- #11 autonomy: autonomy is maximized only inside explicit P0/P1 boundaries.
