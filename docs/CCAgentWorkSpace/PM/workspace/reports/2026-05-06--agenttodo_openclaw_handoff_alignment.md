# AgentTodo OpenClaw Handoff Alignment

Date: 2026-05-06
Owner: PM
Status: APPROVED for handoff after doc sync

## Task

Review the new OpenClaw Gateway plan, GUI Control Console plan, and AgentTodo. Decide whether AgentTodo fully reflects the new architecture and whether work order needs adjustment before the next team starts from AgentTodo.

## Verdict

AgentTodo already reflected the corrected authority boundary:

- local 5-Agent runtime stays inside TradeBot,
- OpenClaw Gateway is communication/mobile/supervisor/proposal relay only,
- the existing FastAPI console is the only canonical GUI,
- `MessageBus` is legacy/advisory trace, not the Agent Decision Spine,
- cloud AI goes through supervisor escalation, not per-agent independent calls.

The gap was work sequencing. OpenClaw implementation was too flat across MAG-015 and TODO P1-OPENCLAW, leaving room for a future agent to start with Telegram/WebChat, proposal relay, or GUI panels before the durable event store and contracts exist.

## Decision

AgentTodo is now the primary handoff source for the next multi-agent phase. The next work starts as AgentTodo Sprint A:

1. MAG-015: contract addendum for local observations, OpenClaw view models, escalation/proposal/channel schemas, endpoint allowlist, cloud budget, store ownership, and state transitions.
2. MAG-010..014: durable `agent.messages`, `agent.state_changes`, and `agent.ai_invocations` wiring with Linux nonzero-row proof.
3. MAG-016..017: OpenClaw Gateway authority lockdown and read-only `/api/v1/openclaw/status` + `/self-state`.
4. MAG-018..019: read-only Agent Control GUI foundation and supervisor cloud escalation ledger policy.
5. After the read-only foundation is proven: proposal/approval queue, then Telegram/WebChat/mobile relay.

M2 Scanner Advisory Conversion and M3 Agent Decision Spine Shadow remain blocked until M1 has Linux row proof and E2/E4 acceptance.

## Updated Files

- `docs/architecture/multi_agent_rework_2026-05-05/AgentTodo.md`
- `TODO.md`
- `CLAUDE.md`
- `.codex/MEMORY.md`
- `.codex/WORKLOG.md`
- `docs/CCAgentWorkSpace/PM/memory.md`

## Boundary

No runtime, DB, strategy/risk, live authorization, rebuild, restart, or deploy action was performed. This is a documentation and handoff-order checkpoint only.
