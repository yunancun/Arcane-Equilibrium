---
status: accepted
date: 2026-05-05
---

# V### migrations must be Linux-PG dry-run before E1 implementation design

Any V### migration touching PG reflection functions (`pg_get_function_*`, `pg_proc`, `information_schema`), transaction control inside `PL/pgSQL DO` blocks, or schema assumptions (column existence / type / default) must be empirically dry-run against the Linux PG instance before E1 begins implementation design. Mac mock pytest plus static review is not sufficient.

## Considered alternatives

Continuing with Mac-mock-first was rejected after the V055 retrofit (REF-20 Sprint C R6-T0') took 5 round-fix-review cycles instead of 1 — each round responded to a real PG-side bug masked by the Mac mock layer (PG 16 `identity_arguments` includes arg names, PL/pgSQL forbids `SAVEPOINT`/`COMMIT` inside DO blocks, etc.).

## Consequences

E2 review must include a Linux PG dry-run gate, not just Mac mock pytest. Combined with ADR 0010's Guard A/B/C, this catches migration semantic drift before sqlx hash drift incidents (see `project_2026_05_02_p0_sqlx_hash_drift.md`).
