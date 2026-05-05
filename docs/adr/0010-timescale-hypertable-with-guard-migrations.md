---
status: accepted
date: 2026-04-03
---

# PostgreSQL + TimescaleDB with mandatory Guard A/B/C migration template

Time-series storage uses PostgreSQL with TimescaleDB hypertables, constrained to ~4–8 GB `shared_buffers` because local Ollama/LMStudio LLMs (~18–54 GB) dominate the 128 GB unified-memory budget. All `V###__*.sql` migrations must apply Guard A (column / function existence check before `CREATE …`), Guard B (`data_type` check before type-sensitive `ADD COLUMN`), and Guard C (`pg_get_indexdef()` comparison for hot-path indexes). Idempotency is enforced — running the migration twice must not RAISE on the second run.

## Consequences

Engine auto-migration is opt-in via `OPENCLAW_AUTO_MIGRATE=1`. The Guard A/B/C convention originated in the V023 silent-noop postmortem (2026-04-24); see ADR 0011 for the Linux PG dry-run rule that complements it.
