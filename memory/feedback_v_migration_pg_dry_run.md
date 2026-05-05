---
name: V### migration must validate against real PG before E1 IMPL design
description: Mac mock pytest + static review cannot catch PG runtime semantic differences (PL/pgSQL constraints, empirical reflection function behavior, schema column existence). V### migrations must do Linux PG dry-run before E1 IMPL.
type: feedback
originSessionId: ed3e3c59-83a5-44e5-8b28-0f3b83e516a0
---
REF-20 Sprint C R6-T0' V055 retrofit took 5 rounds (E1 round 1-5 + E2 round 1-5) instead of 1 because each round was responding to a real bug masked by the Mac mock layer. The cumulative bug pattern:

| Round | Bug type | Why Mac mock didn't catch |
|---|---|---|
| 1 | INSERT 4 column 設計（實際 schema 只 3 column） | E1 trusted MIT advisory + V036 docstring claim; Mac static-parse pass |
| 2 | Guard A `pg_get_function_arguments` includes DEFAULT clause | Mac mock test 0 actual PG query; static parse pass |
| 3 | phantom column `actor_id` (V045 vs V049 confusion) | Mac mock 0 PG schema cross-validation |
| 4 | PG 16 empirical `pg_get_function_identity_arguments` includes arg names (PG docs claim "stripped-down" 不準) | No way to know without real PG query |
| 5 | PL/pgSQL DO block `SAVEPOINT/ROLLBACK TO` forbidden (PG hard constraint) | Mac mock pytest never executed actual PG DO block |

**Why:** Operator pushed back: "你是不是卡住了？這些 round 究竟在幹什麼？" — round-fix-review pattern was treating symptoms not root cause. Each round was correct response to a real bug, but the cumulative loop was avoidable if V055 had been Linux PG dry-run before E1 IMPL design.

**How to apply:**

1. **Before E1 dispatch for any V### migration**: PM (or PA) must do Linux PG dry-run to verify:
   - Column existence (every column in INSERT/SELECT must `\d table` show exists)
   - Function signature format (run `SELECT pg_get_function_*(oid)` to capture real output before hardcoding expected)
   - Transaction control compatibility (PL/pgSQL DO block restrictions: no SAVEPOINT, no COMMIT, no explicit transaction commands)
   - Reflection function actual behavior on target PG version (PG 13+ identity_arguments includes arg names contrary to docs)

2. **PA dispatch brief must include**: pre-IMPL Linux PG empirical query results (column list / function signature / etc.) so E1 designs against real schema not docstring claims.

3. **E2 review must include Linux PG dry-run gate** before approving for E4 (not just Mac mock pytest). At minimum: `bash helper_scripts/linux_bootstrap_db.sh --apply <V###>` on a test DB or via SAVEPOINT outer transaction (not in PL/pgSQL).

4. **Anti-pattern**: trusting docstring claims ("PR3 will retrofit 4 columns") or PG official docs ("identity_arguments stripped-down") without empirical verification. Both proved wrong in V055 chain.

5. **Pattern that works**: PM-issued direct PG query before dispatch:
   ```bash
   ssh trade-core "psql -c \"SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='X' AND table_name='Y';\""
   ssh trade-core "psql -c \"SELECT pg_get_function_identity_arguments(oid) FROM pg_proc WHERE proname='Z';\""
   ```

**Related**: P0-PROCESS-1 (Mac Python 3.10 / Linux Python 3.12 FastAPI lazy ForwardRef difference, Sprint A R3) — same Mac vs Linux drift class. V### migration is a new instance of the same anti-pattern.

**Bake into governance**: Update CLAUDE.md §七 SQL migration 規範 to include "PG dry-run mandatory before E1 IMPL design" — pending operator decision on whether to make this hard rule or recommended practice.
