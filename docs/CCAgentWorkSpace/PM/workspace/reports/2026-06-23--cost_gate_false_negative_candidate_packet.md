# 2026-06-23 -- Cost Gate False-Negative Candidate Packet

## Summary

Built `cost_gate_false_negative_candidate_packet_v1` to convert Cost Gate
blocked-outcome review into ranked, machine-checkable profit-learning work.

The packet separates:

- `ranked_false_negative_candidates`: blocked signals whose after-cost markouts
  clear review thresholds and should be operator-reviewed before any bounded
  Demo probe authority.
- `edge_amplification_candidates`: gross-positive but net-insufficient or
  unstable rows that need alpha amplification, friction reduction, retiming, or
  side-cell filtering.
- sample-accumulation rows.
- keep-blocked rows.

This directly addresses the Cost Gate problem without globally lowering the
gate. The system can now identify which blocked signals may be wrongful blocks,
which signals need stronger edge, and which should remain blocked.

## Source Changes

- Added `helper_scripts/research/cost_gate_learning_lane/false_negative_candidate_packet.py`.
- Wired `helper_scripts/cron/cost_gate_learning_lane_cron.sh` to refresh
  `false_negative_candidate_packet_latest.{json,md}` after blocked-outcome
  review.
- Wired `runtime_runner.py` to include packet status and top candidates in the
  Cost Gate arm / killboard detail.
- Wired `discovery_loop.py` so ready false-negative packets route to
  `READY_FOR_PROBE` operator review, while edge-amplification packets remain
  engineering-actionable.
- Wired `learning_worklist.py` so the top Cost Gate learning task mirrors the
  ranked false-negative packet and no-authority answers.
- Added focused packet, alpha/worklist, and cron static coverage.

## Runtime Evidence

Linux artifact-only packet smoke on
`/tmp/openclaw/cost_gate_learning_lane/blocked_outcome_review_latest.json`
generated the packet at `2026-06-23T19:12:22Z`:

- status: `COST_GATE_FALSE_NEGATIVE_CANDIDATES_READY_FOR_OPERATOR_REVIEW`
- false-negative candidates: `16`
- edge-amplification candidates: `0`
- ranked review candidates: `16`
- top false-negative side-cell: `grid_trading|AVAXUSDT|Sell`
- top wrongful-block score: `146.9126`
- top net cost cushion: `73.4563bps`
- `global_cost_gate_lowering_recommended=false`
- `probe_authority_granted=false`
- `order_authority_granted=false`

## Verification

- Mac related research suite: `176 passed`
- Mac cron static suite: `17 passed`
- Linux related research suite: `176 passed`
- Linux cron static suite: `17 passed`
- Mac/Linux `py_compile`, bash syntax, and `git diff --check` passed
- Source commit: `b713c672` pushed with `[skip ci]`
- Linux `trade-core` fast-forwarded clean to `b713c672`

## Profitability Read

The current profit path is now more concrete:

1. Preserve and review blocked demo signals instead of silently discarding them.
2. Rank after-cost false-negative candidates by side-cell and wrongful-block
   score.
3. Send only ranked candidates to operator review before bounded Demo probe
   authority.
4. Require candidate-matched touchability, fill, fee, slippage, and matched
   control evidence before any scoped Cost Gate change.
5. Route gross-positive but net-insufficient rows to edge/alpha amplification
   work instead of lowering the gate.

## Boundary

No CI run. No PG write/schema migration, Bybit private/signed/trading call,
deploy/rebuild/restart, crontab install, env/auth/risk/order/strategy/runtime
mutation, global Cost Gate lowering, probe/order authority, actual order, or
promotion proof.
