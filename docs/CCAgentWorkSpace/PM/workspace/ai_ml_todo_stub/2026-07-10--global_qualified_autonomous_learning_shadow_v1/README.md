# Global Qualified Autonomous Learning Shadow V1

Date: 2026-07-10
Owner: PM
Goal: `GLOBAL_QUALIFIED_AUTONOMOUS_LEARNING_SHADOW_V1`
Codex Goal thread: `019f4b6d-1e5b-7551-9fce-7a2f029a1675`
Status: `ACTIVE_WP2B_LINEAGE_PROPAGATION`

This is the durable PM-owned queue and state surface for the active Goal. It
supersedes the old ALR P2 completion/terminal interpretation, but does not edit
or erase the historical P2 queue, AMD-2026-07-10-02, exact SUI packet, or their
reviews.

The Goal is an engineering and learning-shadow mandate. It is not standing,
generic, candidate, Demo, exchange, or order authority. ALR may write only
validated `learning.alr_*` evidence, challenger-registry, health/state, and
gated derived-cache retention records. It has no exchange, trading,
order/probe, Decision Lease, Guardian mutation, RiskConfig mutation, global
Cost Gate, live/mainnet, serving, promotion, `_latest`, protected-evidence
deletion, or direct parameter-apply authority.

`ProofPacket`/Reward generation is evidence production, not promotion
authority. `CHALLENGER_ACCEPT` is not serving, deployment, live eligibility, or
order authority.

## Durable loop files

- `queue.md`: WP0-WP7 order, gates, transitions, retries, and next actions.
- `gap_matrix.md`: G1-G9 evidence and terminal eligibility.
- `baseline_state_packet.json`: immutable WP0 read-only source/runtime baseline.
- `loop_state_packet.json`: current Goal state and safe-work inventory.
- `effect_review.json`: delta and anti-repeat verdict for the current loop.
- `manifest.json`: machine-readable directory contract.

Every completed loop refreshes `queue.md`, `manifest.json`,
`loop_state_packet.json`, and `effect_review.json`, plus a PM report and an
Operator summary. `ADVANCED`, `DEFER_EVIDENCE`, `NO_ELIGIBLE_CACHE`,
`WAIT_OPERATOR_DEMO_AUTH_EXACT`, `DONE_SOURCE_ONLY`,
`DONE_OPERATIONAL_SHADOW`, and `BACKLOG_EXHAUSTED` are never Goal terminals.

## Goal terminals

- `DONE_QUALIFIED_AUTONOMOUS_LEARNING_SHADOW`: G1-G9 all machine-verified.
- `HARD_BLOCKED_OPERATOR_ACTION_REQUIRED_CURRENT`: same current external
  operator-only blocker proven for three consecutive Goal turns, with no safe
  source/test/data/governance work remaining.
- `SAFETY_ABORT_BOUNDARY_CONFLICT`: a concrete requested action conflicts with
  a hard boundary and no safe narrowing exists.

The Goal remains active while any safe WP0-WP7 action exists.
