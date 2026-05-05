---
status: accepted
date: 2026-05-06
supersedes: early-openclaw-as-conductor-interpretation
---

# OpenClaw Gateway is an external communication layer, not the trading conductor

The external OpenClaw Gateway must not host or replace the local trading 5-Agent runtime, must not become a second GUI, and must not enter the trading hot path. The canonical GUI is the existing FastAPI console at `trade-core:8000/console`, now positioned as the OpenClaw Control Console. Gateway usage is limited to Telegram/WebChat/mobile/operator communication, supervisor briefs, cloud escalation, proposal creation, and approval relay into TradeBot APIs.

## Consequences

Scout / Strategist / Guardian / Analyst / Executor remain local TradeBot runtime components. OpenClaw Gateway never holds Bybit credentials, never directly calls order endpoints, never directly mutates live TOML, and never bypasses GovernanceHub, Decision Lease, or Rust `openclaw_engine`. Any older EX-06 or DOC-04 wording that implies OpenClaw itself is the trading conductor is historical and superseded by `docs/architecture/2026-05-06--openclaw_control_plane_repositioning.md`.
