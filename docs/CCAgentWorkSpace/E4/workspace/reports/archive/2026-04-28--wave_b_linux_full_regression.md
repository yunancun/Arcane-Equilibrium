# E4 Wave B Linux Full Regression — `cf34e96..d1fd1cf` (4 commits)

**Verdict**: **FAIL** — 2 BLOCKERS discovered on Linux that did not surface on Mac.

**Linux HEAD**: `d1fd1cf docs(memory): record Wave B (G3-09 PB1 + G8-01 W2 + W3) + REGRET-DREAM defer` (synced via `git reset --hard origin/main`)

**Engine binary NOT rebuilt** (per task spec — Phase B Wave 1 advisory observability, 0 trade impact).

---

## Test 結果

| 引擎 / Suite | passed | failed | baseline | delta | 兩遍同綠 |
|---|---|---|---|---|---|
| Rust cargo lib (release) | **2299** | **0** | 2290 | **+9** ✓ | ✓ (0.52s × 2) |
| Rust daemon integration test (`test_cost_edge_advisor_daemon`) | **11** | **0** | 6 (Phase A) | **+5** ✓ | ✓ (2.06s + 2.07s) |
| **Rust persistence test (`test_cost_edge_advisor_persistence`)** | **0** | **2** | N/A (new) | **BLOCKER** | n/a (didn't reach 2nd run) |
| W3 same-session pytest (test_phase2_strategy_routes_coverage + test_strategist_cognitive_integration) | **51** | **0** | n/a | (PA H-1 KPI) ✓ | ✓ (0.52s + 0.58s) — H-1 fix Linux reproducible CONFIRMED |
| Pytest combined 7-suite (W1+LOSSES+W2+W3+strategist+audit+phase2) | **141** | **0** | Mac 141 | match Mac | ✓ (0.71s + 0.67s) |
| **V026 idempotency** | — | — | — | **BLOCKER (1st apply ERROR + 2nd apply same ERROR)** | — |
| Healthcheck full sweep (32 checks) | **31 PASS / 1 WARN [11] / 0 FAIL** | — | — | including [30] cost_edge_advisor_status PASS, [8] shadow_exits 0 dormant | ✓ |

**Math check** (cargo lib delta): baseline 2290 + Wave A daemon-body sticky-ts inside lib already counted → +9 from Wave B Phase B Wave 1 (V026/INSERT/healthcheck split/DbSlot late-inject lib-side tests: EvalCounters/LogRow build/down-sample/CHECK constraint envelope). 2290 + 9 = **2299 ✓** matches expected.

---

## BLOCKER #1 — V026 retention policy fails on Linux TimescaleDB 2.26.1

**Symptom** (1st apply, fresh DB state):
```
psql:V026__cost_edge_advisor_log.sql:197: ERROR:  invalid value for parameter drop_after
HINT:  Integer duration in "drop_after" with valid "integer_now" function or interval
       time duration in "drop_created_before" is required for hypertables with integer
       time dimension.
[bootstrap] FAILED at migration V026__cost_edge_advisor_log.sql
```

**Root cause** (V026 line 192-198):
```sql
SELECT add_retention_policy(
    'learning.cost_edge_advisor_log',
    BIGINT '2592000000',  -- 30 days in ms
    if_not_exists => TRUE
);
```
`learning.cost_edge_advisor_log.ts_ms` is `bigint` (epoch-ms). TimescaleDB 2.26 requires either:
- `set_integer_now_func()` registered for the hypertable BEFORE `add_retention_policy(BIGINT ...)`, OR
- `add_retention_policy(table, drop_created_before => INTERVAL '30 days')`

V026 does neither → ERROR aborts migration after the table + hypertable were created (partial state on disk).

**Idempotency check (2nd apply)**: Same error at line 197. The earlier `CREATE TABLE IF NOT EXISTS` and `create_hypertable(if_not_exists => TRUE)` correctly NOTICE-skip (Guard A behavior intact), but the retention policy line has no `BEGIN ... EXCEPTION ... WHEN duplicate_object` guard and re-ERRORs. **V026 idempotency BROKEN — violates CLAUDE.md §七 「新 SQL migration 規範 規則 4: Idempotency 驗證」**.

**Production impact**: any Linux env where V026 has not yet succeeded cannot be migrated by `linux_bootstrap_db.sh`. Linux trade-core is now stuck in partial state (table + hypertable exist but no retention policy). Engine running with `OPENCLAW_AUTO_MIGRATE=1` would refuse to start (per CLAUDE.md §七 "Engine 自動遷移" rollback path).

**E1 fix recommendation**:
- Replace line 192-198 with `set_integer_now_func` registration (e.g., `CREATE FUNCTION learning.advisor_log_now_ms() RETURNS BIGINT AS $$ SELECT (extract(epoch from now())*1000)::BIGINT $$ LANGUAGE SQL STABLE;` then `SELECT set_integer_now_func('learning.cost_edge_advisor_log', 'learning.advisor_log_now_ms');`) BEFORE `add_retention_policy(BIGINT ...)`,
- Wrap the retention policy in `DO $$ BEGIN ... EXCEPTION WHEN ... END $$` for true idempotency (or use `add_retention_policy(... if_not_exists => TRUE, ...)` after verifying the policy doesn't exist via `_timescaledb_catalog.bgw_job` lookup).

---

## BLOCKER #2 — Persistence test conflicts with V026 CHECK constraint

**Symptom**:
```
running 2 tests
test daemon_persists_cycle_row_when_pool_provided ... FAILED
test transition_row_carries_transition_from_string ... FAILED

panic: expected daemon to INSERT at least 1 row to learning.cost_edge_advisor_log
       (engine_mode=test_persist_3491398); observed 0
```
- 1st run: 2 failed (10.12s)
- 2nd run not attempted (already-failing test, not flaky)

**Root cause**: V026 schema defines:
```
CHECK ((engine_mode = ANY (ARRAY['paper'::text, 'demo'::text, 'live'::text, 'live_demo'::text])))
```
The persistence test uses isolation tag `format!("test_persist_{}", std::process::id())` to avoid polluting prod rows. The daemon's INSERT (`fire-and-forget tokio::spawn` in `insert_advisor_log_row`, mod.rs:332) hits the CHECK constraint, fails with `cost_edge_advisor_log_engine_mode_check`, and is **silently swallowed** (only `warn!` logged — visible in stderr only, never reaches the assertion path).

**Verified via direct INSERT** (skipping Rust):
```
psql -c "INSERT INTO learning.cost_edge_advisor_log
         (..., engine_mode, ...) VALUES (..., 'test_e4_diag', ...) ON CONFLICT DO NOTHING;"
ERROR: new row for relation "_hyper_62_290_chunk" violates check constraint
       "cost_edge_advisor_log_engine_mode_check"
```

**This is a test-vs-schema design conflict, not a runtime bug** — production engine_mode is always one of the 4 whitelisted values, so prod path is fine.

**E1 fix recommendation** (pick ONE):
- A. Change CHECK to `engine_mode IN (...prod 4...) OR engine_mode LIKE 'test_%'` (allow test isolation tags),
- B. Change persistence test to use one of the prod 4 values + a separate isolation column (e.g., a numeric `pid_tag` field in advisor log), or use `engine_mode='paper'` + cleanup-by-ts_ms range,
- C. Drop the CHECK constraint entirely (engine_mode-typed-domain is not a strong invariant — the writer is the only producer; downstream consumers tolerate unknown values per Phase B observability scope).

Recommend **A** (least invasive, preserves prod CHECK semantics, unblocks test).

---

## Mock 安全 / Mock 審查

N/A — pure regression run on existing test suite, 0 production diff in this E4 run.

---

## 綠色項目（confirm Phase B observation foundation working）

- **Rust cargo lib 2299/0** — Phase B Wave 1 lib-side additions (EvalCounters / CostEdgeAdvisorLogRow / sticky / CHECK envelope) all green; FUP-IPC + DbSlot late-inject contracts verified.
- **Daemon integration test 11/0** — sticky_triggered_at_ms preservation across contiguous trigger cycles + spawn-test FUP cases A/B/C all green; cadence within tolerance.
- **W3 51/51 same-session reproducibility** — H-1 fix (sys.modules → importer-side patch) Linux reproducible, run1 0.52s + run2 0.58s, **PA RFC §6 R-B7 H-1 KPI MET on Linux**.
- **Pytest combined 7-suite 141/0** — Mac 141 vs Linux 141 perfect match (0 fastapi pre-existing failures on Linux as PA RFC predicted).
- **Healthcheck full sweep**: 31 PASS / 1 WARN [11] / 0 FAIL. New checks pass:
  - `[30] cost_edge_advisor_status PASS` — DB-down fallback verified (env=0 → dormant by design, Phase A: 0 trade impact even when activated)
  - `[8] shadow_exits_24h PASS` — 0 row dormant (shadow_enabled=false)
  - `[1]` close_fills 224 / `[2]` label_backfill ratio 1.00 / `[3]` exit_features 1.00 / `[4]` phys_lock 24h=229 7d=467 — Wave A baseline preserved
  - `[18]` disabled_strategy_inventory: bb_breakout + funding_arb (active=3: bb_reversion, grid_trading, ma_crossover)
  - `[Xa]` leader_election_health: leader_pid=3090462 alive, lock_age=11.3h
- **WARN [11]** counterfactual_clean_window_growth 226/200 (113%) ETA ~0d, pre-existing pacing rule (NOT caused by Wave B).

---

## 跑兩遍結果（flakiness check）

| Suite | run1 | run2 | flaky? |
|---|---|---|---|
| cargo lib | 2299/0 (0.52s) | 2299/0 (0.52s) | N |
| daemon test | 11/0 (2.06s) | 11/0 (2.07s) | N |
| W3 51-case | 51/0 (0.52s) | 51/0 (0.58s) | N |
| pytest combined 7-suite | 141/0 (0.71s) | 141/0 (0.67s) | N |
| persistence test | 0/2 (10.12s) | not retried (already-failing, not flaky) | N |

---

## 結論

**FAIL — 退回 E1**

### 退回 E1 修復清單

1. **V026 retention policy bug** (P0 — production migration broken on Linux):
   - File: `srv/sql/migrations/V026__cost_edge_advisor_log.sql` lines 192-198
   - Bug: `add_retention_policy('learning.cost_edge_advisor_log', BIGINT '2592000000', if_not_exists => TRUE)` ERROR on TimescaleDB 2.26 because `bigint` ts_ms hypertable lacks `integer_now_func`.
   - Fix path A (recommended): register `set_integer_now_func()` BEFORE `add_retention_policy`.
   - Idempotency: must pass `psql -f V026 ... ` twice without RAISE on 2nd run (per CLAUDE.md §七 規則 4).
   - Linux trade-core PG state needs cleanup before re-apply: table + hypertable already exist; either DROP and recreate from scratch, or rebuild migration to handle "table exists but no retention policy" path.

2. **Persistence test vs V026 CHECK constraint conflict** (P1 — test infrastructure):
   - File 1: `srv/rust/openclaw_engine/tests/test_cost_edge_advisor_persistence.rs` lines 184, 261 (engine_mode tag construction)
   - File 2: `srv/sql/migrations/V026__cost_edge_advisor_log.sql` `cost_edge_advisor_log_engine_mode_check` constraint
   - Bug: CHECK constraint whitelists 4 prod values; test isolation tag `test_persist_<pid>` rejected; daemon swallows error (fire-and-forget); test sees 0 rows after 5s.
   - Fix path A (recommended): broaden CHECK to allow `engine_mode LIKE 'test_%'`.
   - Verify: `cargo test --release -p openclaw_engine --test test_cost_edge_advisor_persistence` returns 2/0 with PG DSN.

3. **Re-run E4 full Wave B regression** after both fixes deployed:
   - V026 1st + 2nd apply both clean
   - Persistence test 2/0
   - All other green items above must remain green (cargo lib 2299, daemon 11, W3 51, combined 141, healthcheck 31 PASS).

### Wave B prerequisite status

- E2 review (PA spec §6 R-B7 H-1 KPI): **51/51 same-session reproducible on Linux ✓**
- Phase B Wave 1 advisory observability: 0 trade impact confirmed via healthcheck [30] + [8] + cargo lib 2299/0
- BUT: V026 cannot be deployed → Phase B INSERT path (`learning.cost_edge_advisor_log`) not writable on Linux until BLOCKER #1 fixed → Phase B observation effectively dormant

**Operator action**: relay BLOCKER #1 + #2 to PA / E1 via PM Sign-off escalation. Suggest holding `--rebuild` deploy of Phase B Wave 1 binary changes until V026 fix lands (current Linux engine PID still on Wave A binary, Phase B Wave 1 runtime has 0 deploy footprint anyway).

---

## Linux runtime state snapshot

- HEAD `d1fd1cf` (synced `git reset --hard origin/main`)
- Engine binary NOT rebuilt this session (per task spec)
- PG: TimescaleDB 2.26.1 on `trading_ai` (`learning.cost_edge_advisor_log` partial state — table + hypertable exist, no retention policy, 0 rows)
- Healthcheck: 31 PASS / 1 WARN [11] (pre-existing, ETA 0d) / 0 FAIL
- E4 cleanup: removed `test_e4_diag` direct-INSERT diagnostic row (DELETE 0 — earlier INSERT was rejected by CHECK so no row to delete)

---

## 教訓（appended to E4 memory）

1. **Mac PG bypass blind spot**: Mac auto-skip persistence test (no `OPENCLAW_TEST_PG`) hides BOTH the V026 retention bug AND the test-vs-CHECK conflict. PA RFC §6 R-B7 explicitly required Linux verification — without it, Phase B Wave 1 looked PASS on Mac while Linux deployment is blocked. **Rule reinforce**: any V*.sql migration touching TimescaleDB hypertable retention/compression/integer_now MUST be Linux-validated (`linux_bootstrap_db.sh --apply` 2 times) BEFORE PM Sign-off, regardless of Mac result.

2. **Fire-and-forget INSERT swallows test signal**: `tokio::spawn(insert_advisor_log_row)` decouples DB I/O from daemon cadence (correct production design per RFC §6.1 R-B1) but means CHECK / FK / permission errors are warn-only — test panics see "0 rows" with no clue why. **Recommend**: persistence-style integration tests should run an `EXPLAIN` or sentinel direct-INSERT first to verify schema compatibility before relying on async daemon path. Already documented in lessons.md; this incident reaffirms.

3. **CHECK constraints + isolation-tag tests are an anti-pattern**: Test code uses `format!("test_persist_{}", pid)` for isolation but schema CHECK whitelist rejects it. Either schema must allow `test_*` prefix OR test must use prod-valid value + alternative isolation strategy (ts_ms range, separate column). **Pattern to add to PA / E2 checklist**: any new V*.sql with `CHECK` constraint must list current test isolation patterns and confirm compatibility.
