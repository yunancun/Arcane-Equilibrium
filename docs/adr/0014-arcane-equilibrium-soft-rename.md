---
status: accepted
date: 2026-05-06
supersedes: openclaw-bybit-as-total-project-name
---

# Arcane Equilibrium is the formal project name

The project is soft-renamed to **玄衡 · Arcane Equilibrium**.

OpenClaw is retained as the service-family name for the control plane: OpenClaw Control Console, OpenClaw Gateway, OpenClaw API aggregation routes, communication channels, supervisor briefs, cloud escalation, and proposal/approval relay.

Bybit is retained as the sole venue-adapter label for exchange-specific code, secrets, API references, compliance notes, and connector paths.

## Consequences

New operator-facing and architecture-level documents should use **玄衡 · Arcane Equilibrium** as the total project/product name. New documents should avoid "OpenClaw Bybit" as the total project name.

This is a soft rename only. Runtime names remain stable for compatibility: `openclaw_engine`, `openclaw_core`, `openclaw_types`, `OPENCLAW_*`, `/tmp/openclaw`, GitHub repository naming, Linux runtime paths, Docker/service names, migration comments, and existing Bybit connector package paths are not renamed by this ADR.

Any future deep rename of runtime namespaces requires a separate migration plan with compatibility aliases, Linux deploy rehearsal, and rollback instructions.
