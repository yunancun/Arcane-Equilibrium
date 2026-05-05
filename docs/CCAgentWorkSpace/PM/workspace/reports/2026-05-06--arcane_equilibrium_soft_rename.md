# 玄衡 soft rename integration

Date: 2026-05-06
Role: PM
Status: APPROVED

## Decision

The formal project/product name is now **玄衡 · Arcane Equilibrium**.

OpenClaw remains the control-plane service family. Bybit remains the sole exchange adapter label.

## Scope

This batch is documentation and naming only:

- Updated active project entry docs and glossary.
- Added ADR 0014 for the soft rename.
- Updated Codex/PM operating memory and PM prompt wording.
- Added changelog and PM report entries.

## Explicit Non-Scope

No runtime namespace or deployment path was renamed:

- `openclaw_engine`, `openclaw_core`, `openclaw_types`
- `OPENCLAW_*`
- `/tmp/openclaw`
- GitHub repo / Linux runtime path
- Docker/service names
- Bybit connector package paths

## Verification Performed

- `git diff --check` on the staged docs-only batch: PASS.
- Targeted grep confirmed the new project name and retained OpenClaw boundary in active entry docs.
- Runtime namespace preservation was checked in README / CLAUDE / CONTEXT / ADR 0014.
- Commit + push + Linux `trade-core` ff-only pull are the final sync steps for this batch.
