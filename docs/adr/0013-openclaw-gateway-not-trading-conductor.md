---
status: accepted
date: 2026-05-06
supersedes: early-openclaw-as-conductor-interpretation
---

# OpenClaw Gateway is an external communication layer, not the trading conductor

> ⚠️ **PREMISE RETIRED（记于 2026-07-18 文档审计）**：本 ADR 的规范结论「外部 OpenClaw Gateway 永不成为 trading conductor、不持 credentials、不入热路径」仍有效；但其**前提**「外部 OpenClaw Gateway 是一个 active 通信 surface」已失效——external OpenClaw Gateway / reverse proxy / GUI 集成已于 2026-07-16 retired 并移除（见 `CLAUDE.md` §一）。现存的是本地 authenticated `/api/v1/openclaw/*` 只读控制/监控路由 + 本地 5-Agent runtime。下文对 Gateway 通信用途的描述按历史阅读。

The external OpenClaw Gateway must not host or replace the local trading 5-Agent runtime, must not become a second GUI, and must not enter the trading hot path. The canonical GUI is the existing FastAPI console at `trade-core:8000/console`, now positioned as the OpenClaw Control Console. Gateway usage is limited to Telegram/WebChat/mobile/operator communication, supervisor briefs, cloud escalation, proposal creation, and approval relay into TradeBot APIs.

## Consequences

Scout / Strategist / Guardian / Analyst / Executor remain local TradeBot runtime components. OpenClaw Gateway never holds Bybit credentials, never directly calls order endpoints, never directly mutates live TOML, and never bypasses GovernanceHub, Decision Lease, or Rust `openclaw_engine`. Any older EX-06 or DOC-04 wording that implies OpenClaw itself is the trading conductor is historical and superseded by `docs/architecture/2026-05-06--openclaw_control_plane_repositioning.md`.
