---
name: V### migration must validate against real PG before E1 IMPL design
description: Mac mock pytest + static review cannot catch PG runtime semantic differences (PL/pgSQL constraints, reflection function behavior, schema column existence, TimescaleDB compressed-twin grant propagation). V### migrations must do Linux PG dry-run before E1 IMPL — AND the idempotency double-apply is a load-bearing gate (first-apply PASS ≠ re-apply safe; see 2026-05-28 V114 3-round case).
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

---

**2026-05-28 V114 — 升級教訓：first-apply PASS ≠ idempotent；double-apply gate 是 load-bearing 不是裝飾**

V114 (`observability.notification_failsafe_events` TimescaleDB hypertable) MIT 跑了 **3 輪** dry-run 才綠，每輪都靠「雙跑」抓到 first-apply 看不到的 bug：
- R1：column-level `GRANT UPDATE (acked_at_utc, acked_by)` 寫在 `enable compression` **之後** → TimescaleDB 把 column-level grant 傳播到壓縮 twin `_compressed_hypertable_NN`（twin 只有壓縮格式 column 無 `acked_at_utc`）→ first-apply 即 abort。
- R2：E1 把 GRANT 移到 compression 前 → **first-apply PASS**，但 **double-apply FAIL** — first-run 的 compression enable 建了**跨 run 持久存在**的 twin；第二跑重抵 column-level GRANT 撞已存在 twin → 同樣 abort。**reorder 只解 first-run，問題本質沒消失只位移。**
- R3：E1 把 column-level GRANT 包 `BEGIN ... EXCEPTION WHEN undefined_column THEN RAISE NOTICE; END;`（精確捕捉 42703；twin 存在時 skip，grant 已在 first-run 落 `pg_attribute.attacl`）→ 三跑 EXIT 0 終於綠。

**致命後果若漏 double-apply**：engine restart → sqlx migrate 跑 V114 → 表已存在含 twin → 重演 R2 abort → **migration 鏈卡死、engine 起不來**。R2 若沒驗 double-apply 直接 deploy，下次 restart 全系統掛。

**How to apply（升級）**：
1. **idempotency double-apply 是強制 gate 不是可選** — CLAUDE.md §Data 已寫「applying twice」，但實務上容易因 first-apply PASS 就宣告 done。本案三輪每輪都是 double-apply（或更早 first-apply）抓的，缺一不可。
2. **first-apply PASS 只證「fresh DB 能建」，不證「re-apply 安全」** — 任何建 cross-run 持久物件（compressed twin / MV / sequence / 其他 migration 副產物）的 migration，re-apply 路徑與 first-apply 路徑不同，必分別驗。
3. **TimescaleDB landmine**：compressed hypertable + column-level GRANT 是地雷組合（V114 是全 repo 首例）；compressed twin 無 base table 的非壓縮 column，column-level grant/DDL 傳播會撞。避法：column-level GRANT 包 `EXCEPTION WHEN undefined_column` 或改 table-level GRANT + trigger。
4. **dirty 殘留必清**：psql -f dry-run apply 後 table + twin 留在 DB 但不進 `_sqlx_migrations`；每輪 re-test 前 operator 須 `DROP TABLE ... CASCADE` 清 twin，否則重撞同 error。
5. **正式 record 路徑**：dry-run 用 psql -f 不寫 `_sqlx_migrations`；deploy posture `OPENCLAW_AUTO_MIGRATE=0`（deliberate）下，正式記錄 = 暫設 AUTO_MIGRATE=1 → restart（migrator Applied(N) 記 checksum）→ 還原 0。checksum-safe 因從未 sqlx-applied（區別於 2026-05-02 P0 hash-drift incident 需 repair_migration_checksum）。
