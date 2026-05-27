# MIT V104 Supervised Live Audit Migration — Linux PG Empirical Dry-Run

**Date**: 2026-05-27
**Trigger**: LG-3 Wave 2.4.A E1 IMPL dispatch gate (2) — MIT 4-step Linux PG empirical dry-run 9/9 PASS
**Spec**: `srv/docs/execution_plan/specs/2026-05-26--v104-lg3-supervised-live-audit-migration.md` §4 (4 step + 9 query)
**Trade-core PG**: `localhost:5432 / trading_ai / trading_admin` (PostgreSQL 16.11)
**Method**: BEGIN+ROLLBACK transaction protection in main DB (per task spec — no sandbox DB / `OPENCLAW_PG_URL_DRYRUN` unset on trade-core)

## §1 Sandbox vs Main DB Path Selection

`ssh trade-core 'env | grep OPENCLAW_PG_URL'` empirically confirms:
- `OPENCLAW_PG_URL=unset`
- `OPENCLAW_PG_URL_DRYRUN=unset`
- `DATABASE_URL=unset`

Spec §4.1 Step 2 命名的 `$OPENCLAW_PG_URL_DRYRUN` 在 trade-core 並未配置（**spec gap**）。trade-core 無獨立 sandbox DB；唯一 PG = production `trading_ai`。

**選擇**：採 task brief 指定的「`BEGIN; ... ROLLBACK;` 包裹保護」模式，在 main `trading_ai` 內跑但全程不 commit。

**Post-rollback sanity verified**：
- `learning.supervised_live_audit` table 不存在（count=0）
- `_sqlx_migrations` max=112 / count=102 完全不變
- 0 leaked test row（4 boundary INSERT 全 ROLLBACK）

**Spec §4.1 改善建議**：trade-core 未來如建立獨立 dryrun DB，需在 `restart_all.sh` / `.env` 中 export `OPENCLAW_PG_URL_DRYRUN`；目前 SOP 應更新為 transaction rollback 模式。

## §2 4-Step Empirical Results

### Step 1 — Baseline snapshot
```
_sqlx_migrations: max=112 / count=102
V99/100/101/102/103 all success=t (V104 FREE confirmed)
V35 (governance_audit_log) + V54 (lease_transitions) both success=t (Guard A part 1 prereq met)
learning.supervised_live_audit: 0 rows (clean baseline)
```
✓ Step 1 PASS

### Step 2 — CREATE TABLE + Guard A part 1 + idempotent re-apply
Round 1 (single apply within BEGIN/ROLLBACK):
- Guard A part 1 (V054+V035 prereq) — DO block executed, no RAISE ✓
- CREATE TABLE supervised_live_audit (21 col PK=(event_id, created_at)) ✓
- 4 ADD CONSTRAINT (IF NOT EXISTS pattern) ✓
- create_hypertable returned `(88, learning, supervised_live_audit, t)` ✓
- WARNING informational: `column "event_id" should be used for segmenting or ordering` — spec §2.3 設計上選 `session_id` segmentby 是 hot-read pattern；PG hint 不是 error，保留 spec 設計

Round 2 (apply twice in single tx — true idempotency test):
- 2nd CREATE TABLE → `NOTICE: relation "supervised_live_audit" already exists, skipping` ✓
- 2nd CREATE INDEX → `NOTICE: relation "idx_supervised_live_audit_action" already exists, skipping` ✓
- DO `$a1$` 檢查 CHECK constraint 存在 → 無 RAISE ✓
- `=== idempotency PASS (no RAISE) ===`
✓ Step 2 PASS (idempotent — V083/V084 NOTICE-skip gold standard 一致)

### Step 3 — CHECK enforce + 21 col + Guard A part 3 forbidden
- 21 col 全 land（col_count=21；ordinal_position 1..21 完整）✓
- 4 CHECK constraints: chk_supervised_live_audit_action / _engine_mode / _result / _ts_ms_positive ✓
- Guard A part 3 forbidden columns (ml_label/training_label/feature_vector/signal_id) — 0 rows returned ✓ (non-training surface invariant 達成)
- 4 boundary INSERT enforcement:
  - action='BAD_ACTION_NOT_IN_ENUM' → `check_violation` rejected ✓
  - result='xyz_invalid' → `check_violation` rejected ✓
  - engine_mode='paper' → `check_violation` rejected ✓ (LiveDemo 不降級邊界遵守)
  - ts_ms=0 → `check_violation` rejected ✓
- valid row (engine_mode='live_demo', action='request_registered', result='ok', ts_ms=1730000000000) → `INSERT 0 1` ✓
✓ Step 3 PASS

### Step 4 — Hypertable + chunk + policy + index
- hypertable: num_dimensions=1 ✓
- chunk_days: 7 (符合 spec §2.3 INTERVAL '7 days') ✓
- show_chunks 第 1 row insert 後 → `_timescaledb_internal._hyper_90_841_chunk` (chunk auto-create) ✓
- jobs:
  - job_id=1050 policy_compression schedule=12:00:00 config compress_after=30 days ✓
  - job_id=1051 policy_retention schedule=1 day config drop_after=90 days ✓
- 4 indexes + PK + auto hypertable created_at idx = 6 indexes total ✓
- action CHECK constraint pg_get_constraintdef = 17 enum 全在 (request_registered / approval_granted / approval_rejected / expired_pre_auth / auth_file_observed / auth_file_invalid / lease_acquired / lease_released / auth_recheck_fail / drawdown_breach / drawdown_close_complete / kill_api / kill_ipc / session_max_duration / reconcile_force_close / illegal_transition_attempted / session_closed) ✓
✓ Step 4 PASS

## §3 9-Query Verify Pass/Fail Matrix

| # | Spec §4 query | Empirical result | Verdict |
|---|---|---|---|
| Q1 | `_sqlx_migrations` baseline (max≥112) | max=112 / count=102 | **PASS** |
| Q2 | Apply CREATE + Guards (no RAISE) | 0 RAISE / 0 ERROR / hypertable_id=88 | **PASS** |
| Q3 | Idempotency 2nd apply NOTICE-skip | `relation "..." already exists, skipping` × 2 | **PASS** |
| Q4a | 21 column allowlist | col_count=21 / ordinal 1..21 完整 / type 全對 | **PASS** |
| Q4b | 4 CHECK constraint | conname × 4 全在 | **PASS** |
| Q4c | hypertable num_dimensions=1 | num_dimensions=1 / hypertable_id=88 (R1) / 90 (R2) | **PASS** |
| Q4d | Compression + retention policy | job_id 1050 (compress 30d) + 1051 (retention 90d) | **PASS** |
| Q4e | 4 named index + PK + auto idx = 6 | 6 indexname 全在 | **PASS** |
| Q4f | action CHECK 17 enum 完整 | 17 enum text 全在 pg_get_constraintdef 輸出 | **PASS** |

**Bonus（spec §3.1 Guard A part 3 forbidden column）**: 0 forbidden column (ml_label/training_label/feature_vector/signal_id) — non-training surface invariant 達成 ✓
**Bonus（CHECK enforce empirical）**: 4 violating INSERT 全 check_violation rejected + 1 valid INSERT 成功 ✓

**結論**：**9/9 PASS** + 2 bonus verify PASS

## §4 Unblock Verdict

**LG-3 Wave 2.4.A E1 IMPL dispatch — UNBLOCKED ✅**

Gate (2) MIT V104 4-step Linux PG empirical dry-run **9/9 PASS** 達成。
Gate (1) v56 P0 Layer B + 24h (~2026-05-30) **independently pending** — 與本 verdict 不衝突；本 dry-run 在 v56 gate 解除後即可立即派 E1 寫 V104 SQL（per spec §1 file name `V104__supervised_live_audit.sql`）。

**PA dispatch packet 必含**（per spec §7.2）:
- V094 → V104 replacement rule（grep `'V094\|V099' <touched_files>'` must equal 0 before IMPL DONE）
- 採 BEGIN/ROLLBACK 模式（trade-core 無 `OPENCLAW_PG_URL_DRYRUN`；future enhancement TODO）
- spec §4.1 Step 2「`scp + psql -f`」改寫為 transaction rollback 模式
- Round 1+2 candidate SQL 已 archived 在 `/tmp/v104_dryrun_candidate.sql` + `/tmp/v104_round2.sql`（trade-core 本地）+ output 在 `/tmp/v104_round1_output.txt` + `/tmp/v104_round2_output.txt`

**1 informational push back**（非阻 IMPL）:
- PG WARNING `column "event_id" should be used for segmenting or ordering` — spec §2.3 選 `session_id` segmentby 是 hot-read pattern 正確設計；E1 IMPL 時保留 `compress_segmentby = 'session_id'`，可在 SQL header 加 comment 註明 PG WARNING 是 informational

## §5 sqlx_migrations 影響面

| 時點 | max | count |
|---|---|---|
| 本 dry-run 前 | 112 | 102 |
| Round 1 ROLLBACK 後 | 112 | 102 |
| Round 2 ROLLBACK 後 | 112 | 102 |
| 將來 V104 真 apply 後（forecast） | 112（V104=104 < 112 已有 V105/V108/V110/V111 holes 占位）| 103 (+1) |

**Note**: trade-core PG 已 land V105-V112（max=112）；V104 申請的是 V99-V103 後的 free hole。`_sqlx_migrations` 是 unique version table；apply V104 後 count 加 1，max 不變（仍 112）；migration 順序 by version sort 自動處理。

**sqlx checksum drift 風險**（per `project_2026_05_02_p0_sqlx_hash_drift`）:
- 若 V104 file 在 dry-run 後又被 edit（PA 補 amendment / E1 IMPL 改 SQL body）→ 必跑 `bin/repair_migration_checksum --target V104`（per spec §5.1）
- 本 dry-run 在 BEGIN/ROLLBACK 內走，未寫進 `_sqlx_migrations`，不會留 checksum drift hazard

---

**Sign-off**: MIT V104 dry-run 9/9 PASS + 2 bonus PASS — gate (2) 達成。
**Pending**: gate (1) v56 P0 Layer B + 24h (~2026-05-30) — operator/PM 觀察。
**Next**: PA Wave 2.4.A E1 IMPL dispatch（v56 gate 解除後）。

MIT AUDIT DONE: docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-27--v104_supervised_live_audit_dry_run.md
