# E1 IMPL Sign-off — REF-20 Sprint D R8 (Maintenance / Retention / 5 Sentinel)

**Date**: 2026-05-05
**Owner**: E1
**Scope**: Sprint D R8 maintenance pass per `docs/execution_plan/2026-05-04--ref20_gap_closure_reality_backtest_plan_v1.md` §6.R8
**Status**: IMPL DONE — pending PM commit + Linux V056 apply + R9 final sign-off

---

## §1. 6 cron task disposition (plan §6.R8 §1.1)

對 6 個 cron-able task 逐一 grep `helper_scripts/cron/` 確認已 land 狀態：

| # | Task | Existing Cron Script | 狀態 |
|---|---|---|---|
| 1 | key rotation check | `replay_key_rotation_check.sh` (REF-20 P2a-S1) | ✅ LAND |
| 2 | key archive cleanup | `replay_key_archive_cleanup.py` (REF-20 P2a-S1) | ✅ LAND |
| 3 | artifact prune | `replay_artifact_prune.py` (REF-20 P2a-S5) | ✅ LAND |
| 4 | Wave9 no-live-mutation watch | `wave9_replay_no_live_mutation_watch.sh` (REF-20 W9-T1) | ✅ LAND |
| 5 | business KPI collector | `wave9_business_kpi_collector.py` (REF-20 W9-T2) | ✅ LAND |
| 6 | audit incident scan | `wave9_audit_incident_scan.py` (REF-20 W9-T3) | ✅ LAND |
| 7 | **mlde_shadow retention (NEW)** | `mlde_shadow_recommendations_retention_cron.sh` | ✅ **LAND R8** |

**結論**：6 個 cron task **既有 land 完整**（Wave 9 已交付）；R8 唯一 net new = mlde_shadow retention cron（plan §6.R8 §1.2 推薦）。**不重做** 既有 cron。

每個 cron suggested crontab entry 已在 script header 註明（operator 手動 `crontab -e` 加）。

---

## §2. V056 retention policy IMPL (plan §6.R8 §1.2)

### §2.1 V056 file
**Path**: `srv/sql/migrations/V056__mlde_shadow_recommendations_retention_policy.sql`
**LOC**: 390（< §九 2000 cap）

### §2.2 IMPL 設計
- `CREATE OR REPLACE FUNCTION learning.prune_mlde_shadow_recommendations(p_replay_retention_days INTEGER DEFAULT 30, p_real_retention_days INTEGER DEFAULT 90, p_apply BOOLEAN DEFAULT false, p_max_rows INTEGER DEFAULT NULL)`
- `SECURITY INVOKER`（mirror V036 pattern；非 DEFINER）
- Returns `TABLE(tier TEXT, candidate_count BIGINT, deleted_count BIGINT)`

### §2.3 PG empirical query (V### governance per 2026-05-05 commit `d7a85932`)
```bash
ssh trade-core "psql -c \"SELECT * FROM timescaledb_information.hypertables WHERE hypertable_name='mlde_shadow_recommendations';\""
# → 0 rows
```

**結論**：`learning.mlde_shadow_recommendations` **NOT a hypertable**。決策：cron-driven DELETE（非 `add_retention_policy`）。V056 含 `RAISE EXCEPTION` 守門「意外是 hypertable」case → 強迫切換 add_retention_policy 路徑（防將來 schema drift）。

### §2.4 Boundary Checks
- `p_replay_retention_days >= 1 day`（防 misconfigured cron 清當日樣本）
- `p_real_retention_days >= 1 day`
- `p_real_retention_days >= p_replay_retention_days`（real 是 ground truth，不可比 replay 短）
- `p_max_rows` hard cap 100k per cycle（防長鎖）

### §2.5 Schema Preflight
驗 V051 paired CHECK + V055 verify function + V038-V040 evidence_source_tier NOT NULL + V051 replay_experiment_id col 全 land。

### §2.6 Guard A 三段
post-create 驗：
1. function existence (`pg_proc` lookup)
2. `pronargs = 4`
3. `pg_get_function_identity_arguments` LIKE 4 expected arg patterns

### §2.7 Idempotency
`CREATE OR REPLACE FUNCTION` 重跑覆寫；preflight schema check 若預備條件已 land 不 RAISE。

---

## §3. 5 healthcheck sentinel `[46]`-`[50]`

### §3.1 sentinel module
**Path**: `srv/helper_scripts/db/passive_wait_healthcheck/checks_replay_maintenance.py`
**LOC**: 655（< §九 2000 cap）

### §3.2 5 sentinel spec

| ID | Name | Probe | Cursor | Verdict |
|---|---|---|---|---|
| `[46]` | `mlde_shadow_retention_status` | V056 cron sentinel mtime + replay-derived candidate count | DB cursor | PASS/WARN/FAIL 雙軸 |
| `[47]` | `replay_runner_binary` | filesystem 5-path priority chain (mirror `route_helpers.resolve_replay_runner_bin`) | post-cursor | PASS/WARN/FAIL |
| `[48]` | `replay_manifest_registry_growth` | `replay.experiments` row growth rate (7d/24h) | DB cursor | stall detection |
| `[49]` | `replay_artifact_retention` | V046 oldest age + total bytes vs storage cap | DB cursor | TTL prune cron 雙重驗證 |
| `[50]` | `replay_run_state_health` | V045 failed_rate (7d) + zombie 'running' age | DB cursor | failure rate + zombie detection |

### §3.3 Verdict thresholds
- `[46]` cron freshness: PASS <26h / WARN <50h / FAIL ≥50h；candidate cap 50k FAIL
- `[47]` workspace release > workspace debug > legacy nested release/debug；release PASS / debug WARN / 4-path missing FAIL
- `[48]` 7d 0 row + total ≥2 → FAIL（runner stalled）；24h 0 row → WARN（quiet）
- `[49]` oldest >30d WARN / >60d FAIL；total >cap FAIL；total >80% cap WARN
- `[50]` failed_rate >10% WARN / >20% FAIL；zombie 'running' >1h WARN / >4h FAIL

### §3.4 Graceful absent fallback
`[46]/[48]/[49]/[50]` 各自驗預備 schema 存在（V056 function / V049 / V046 / V045）；缺即 PASS-skip（pre-deploy 不阻塞，deploy 後自動轉真檢查）。

### §3.5 Wire-up locations
- `srv/helper_scripts/db/passive_wait_healthcheck/__init__.py`：5 sentinel re-export + `__all__` 5 entry
- `srv/helper_scripts/db/passive_wait_healthcheck/runner.py`：[46]/[48]/[49]/[50] 在 cursor 區塊；[47] 在 post-cursor；docstring + `_RUNNER_DESCRIPTION` 同步更新

### §3.6 Sentinel slot allocation
原 [45] (Sprint C R6-T7 LG-3 pricing binding) 接續到 [46]-[50]（mirror 既有 [42]/[42b]/[42c]/[43]/[44]/[45] 連號 pattern）。

---

## §4. Sibling cron `mlde_shadow_recommendations_retention_cron.sh`

**Path**: `srv/helper_scripts/cron/mlde_shadow_recommendations_retention_cron.sh`
**LOC**: 154（< §九 2000 cap）

### §4.1 設計
- **Dry-run default**: `OPENCLAW_MLDE_RETENTION_APPLY=1` 才 flip apply
- 環境變數調節:
  - `OPENCLAW_MLDE_REPLAY_RETENTION_DAYS` (default 30)
  - `OPENCLAW_MLDE_REAL_RETENTION_DAYS` (default 90)
  - `OPENCLAW_MLDE_RETENTION_MAX_ROWS` (default 100000)
- V056 缺即 graceful exit 0（pre-deploy 不阻塞 cron schedule install）
- Touch sentinel file `${OPENCLAW_DATA_DIR}/mlde_shadow_recommendations_retention_last_run` 供 `[46]` 消費
- Overlap lock + PG creds source from `secrets/environment_files/basic_system_services.env`（mirror `edge_label_backfill_cron.sh` pattern）

### §4.2 Suggested crontab entry
```bash
0 4 * * * "$OPENCLAW_BASE_DIR/helper_scripts/cron/mlde_shadow_recommendations_retention_cron.sh"
```

---

## §5. Mac pytest 結果

```bash
pytest helper_scripts/db/test_replay_maintenance_healthchecks.py \
       tests/migrations/test_v056_mlde_shadow_recommendations_retention_policy.py \
       helper_scripts/db/test_pricing_binding_healthcheck.py
# → 54 passed in 0.05s
```

### §5.1 New tests
| File | LOC | Tests | Status |
|---|---|---|---|
| `helper_scripts/db/test_replay_maintenance_healthchecks.py` | 488 | 33 | PASS |
| `tests/migrations/test_v056_mlde_shadow_recommendations_retention_policy.py` | 304 | 11 | PASS |
| **Total** | **792** | **44** | **PASS** |

### §5.2 Sibling regression
- `helper_scripts/db/test_pricing_binding_healthcheck.py` (Sprint C R6-T7 [45] sentinel) 10 tests PASS
- 全 helper_scripts/db + tests/migrations 跑：259 passed, 2 skipped (pre-existing live PG opt-in)

---

## §6. LOC compliance (§九 governance)

| File | LOC | Cap | 狀態 |
|---|---|---|---|
| V056 SQL migration | 390 | 2000 | ✅ |
| sibling cron sh | 154 | 2000 | ✅ |
| 5 sentinel module | 655 | 2000 | ✅ |
| healthcheck test | 488 | 2000 | ✅ |
| V056 migration test | 304 | 2000 | ✅ |
| `runner.py` (+75 LOC) | 869 | 2000 | ✅ (>800 warn line — Sprint D R8 sentinel 接 10 LOC/sentinel 結構性增量；governance exception clause 可申請；R9 PM 評估是否 split runner) |
| `__init__.py` (+15 LOC) | 236 | 2000 | ✅ |

**Total new LOC**: 390 + 154 + 655 + 488 + 304 = **1991** （E1 預估 ~950 ± W4 觀察符合預期擴展）

---

## §7. 0 forbidden / 跨平台 / 注釋語言審計

### §7.1 0 hardcoded user-home paths
```bash
grep -E '(/home/ncyu|/Users/ncyu|/Users/[^/]+)' \
  srv/helper_scripts/db/passive_wait_healthcheck/checks_replay_maintenance.py \
  srv/helper_scripts/cron/mlde_shadow_recommendations_retention_cron.sh \
  srv/sql/migrations/V056__mlde_shadow_recommendations_retention_policy.sql \
  srv/helper_scripts/db/test_replay_maintenance_healthchecks.py \
  srv/tests/migrations/test_v056_mlde_shadow_recommendations_retention_policy.py
# → 0 hits
```

### §7.2 0 hard boundary 觸碰
- `max_retries = 0` 不變
- `live_execution_allowed` / `execution_authority` / `system_mode` 不變
- 0 trading.* mutation
- 0 manifest_signer canonical_bytes 改動
- 0 producer code 改動

### §7.3 注釋默認中文 per CLAUDE.md §七 2026-05-05 governance change
所有新 module / 新 function / 新 healthcheck 注釋：
- MODULE_NOTE 雙語（中文先 + English supplement）
- function docstring 中文 + English supplement（既有 sibling pattern 對齊）
- inline 注釋默認中文（保留必要 English 技術詞如 `cur` / `psycopg2` / `tomllib`）

### §7.4 xlang_consistency 維持
0 Rust 改動 / 0 IPC 改動 / 0 producer 代碼改動 → xlang_consistency 13/13 維持。

### §7.5 No SAVEPOINT/ROLLBACK in PL/pgSQL DO block (V055 round 5 lesson)
V056 SQL 0 SAVEPOINT / 0 ROLLBACK in DO block。Guard A post-INSERT path 由 sibling test 覆蓋。

---

## §8. Pending PM action

### §8.1 Commit chain
1. PM review 本 sign-off + V056 SQL + cron + 5 sentinel + tests + REF-20_RESERVATION.md update
2. PM `git add` + `git commit` + `git push origin main`
3. Linux SSH bridge `git pull --ff-only`

### §8.2 Linux V056 apply
```bash
# Apply V056 migration
ssh trade-core "cd ~/BybitOpenClaw/srv && bash helper_scripts/linux_bootstrap_db.sh --apply"

# Verify V056 function created
ssh trade-core "psql -c \"\\df+ learning.prune_mlde_shadow_recommendations\""

# Verify Guard A passed (function exists with 4 args)
ssh trade-core "psql -c \"SELECT proname, pronargs, pg_get_function_identity_arguments(p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='learning' AND p.proname='prune_mlde_shadow_recommendations';\""
```

### §8.3 cron install (operator manual)
PM 通知 operator 加 crontab entry（per script header 文件指引）：
```
0 4 * * * /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/mlde_shadow_recommendations_retention_cron.sh
```

### §8.4 W1 verify
operator 等 1 週後驗 dry-run 候選計數穩定 → flip `OPENCLAW_MLDE_RETENTION_APPLY=1` apply mode。

### §8.5 R9 final sign-off (PM-led)
plan §6.R9 acceptance criteria：
- ≥5 successful runs / ≥2 strategies / ≥1 parameter-change replay / ≥1 fee-aware report
- 0 live mutation
- UI usable
- MLDE/Dream advisory non-commanding
- confidence labels match calibration

---

## §9. 完成 list

- [x] V056 retention SQL migration
- [x] V056 sibling cron `mlde_shadow_recommendations_retention_cron.sh`
- [x] 5 healthcheck sentinel `[46]`-`[50]` 模組
- [x] Wire-up `__init__.py` + `runner.py` (cursor + post-cursor) + docstring
- [x] V056 migration test (11 PASS)
- [x] sentinel healthcheck test (33 PASS)
- [x] sibling regression test (54 total PASS, 0 broken)
- [x] REF-20_RESERVATION.md V056 row added
- [x] memory.md 教訓 5 條 (Linux PG empirical / Wave 9 既 land / sentinel 雙軸 pattern / filesystem-only post-cursor / 4-arg Guard A)
- [x] cross-platform path audit (0 hits)
- [x] LOC compliance (1991 new < 2000 cap each file)
- [x] xlang_consistency 13/13 維持
- [x] 注釋默認中文 per 2026-05-05 governance
- [x] V055 5-round loop 教訓 applied (Linux PG empirical query first)

---

## §10. R8 → R9 → REF-20 ALL CLOSED 路徑

```
R8 IMPL DONE (本 sign-off)
  ↓
PM commit + push (skip E2 R8 per minimal-loop)
  ↓
Linux V056 apply + verify Guard A
  ↓
operator install cron + W1 dry-run observation
  ↓
flip apply mode + observe 14d retention behavior
  ↓
R9 final sign-off (PM-led, plan §6.R9 acceptance)
  ↓
Sprint D closure → REF-20 ALL CLOSED
```

---

**E1 R8 SIGN-OFF DONE: report path: srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-05--ref20_sprint_d_r8_impl.md; cron task disposition (6 既有 + 1 新 retention) + V056 retention + 5 sentinel + TTL pattern; ~1991 LOC; 44 new test PASS; 0 forbidden import / 0 cross-platform path / 0 hard boundary; pending PM commit + Linux V056 apply + W1 verify + R9 final sign-off**
