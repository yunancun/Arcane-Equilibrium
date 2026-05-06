# AgentTodo OpenClaw Handoff Alignment

Date: 2026-05-06
Owner: PM
Status: APPROVED for handoff after doc sync

## Operator Summary

AgentTodo now fully reflects the new OpenClaw direction and is safe to use as the next starting point.

The key correction was sequencing. We should not start by building Telegram/WebChat, proposal approval relay, or a broad GUI surface. The next phase starts with contract and durable evidence first:

1. MAG-015 contract addendum.
2. MAG-010..014 durable event store and Linux nonzero-row proof.
3. MAG-016..017 OpenClaw authority lockdown and read-only `/status` + `/self-state`.
4. MAG-018..019 read-only Agent Control GUI and supervisor cloud ledger.
5. Proposal/approval/channel relay only after the foundation is proven.

## Boundary

OpenClaw remains Gateway only: no direct order, no Bybit key, no live TOML/risk mutation, no second trading GUI, and no Rust hot-path dependency. Cloud L2 calls are supervisor-compressed and budgeted, not independently triggered by each local agent.

No runtime, DB, rebuild, restart, deploy, live auth, strategy, or risk change was performed.
